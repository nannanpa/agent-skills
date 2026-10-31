#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向 .docx 写入批注（comment）——docx-track-changes-wps 配套脚本，版本随 SKILL.md 头部。

为什么需要它：真实审校流程里，修订标记与批注是**两套并行**的——
    · 修订标记（w:ins / w:del）：把字改了，Word/WPS 的修订轨能看到
    · 批注（w:comment）：把**为什么改**写在旁边
人工在 WPS 里审校时两者并用（例："删除：2005"、"审核：2026-10-30"），
而本技能此前只支持修订标记，批注要手工补——补不齐就退回"纯改字不说理由"。

批注在 OOXML 里要动**四个地方**，缺一个 Word/WPS 就打不开或看不到批注：
    ① word/comments.xml（新部件，批注正文）
    ② [Content_Types].xml（登记该部件的类型）
    ③ word/_rels/document.xml.rels（登记关系）
    ④ word/document.xml（锚点：commentRangeStart / commentRangeEnd / commentReference）

库版本 python-docx 1.2.0 没有内置 comments part 支持，因此 ①②③ 采用**保存后 zip 后处理**
（比手工构造 Part/Relationship 对象稳得多，也不会被 python-docx 的保存流程丢掉）。

用法（脚本内调用）：
    from add_comment import add_comment, save_with_comments
    doc, counter, author, date = open_for_revision(src, author, date_iso)
    add_comment(doc, 8, "科学发展观", "该表述已过时，按新发展理念修改", author, date)
    save_with_comments(doc, out)          # 保存 + 注入批注

命令行：
    python3 add_comment.py 原件.docx 输出.docx 段落号 "批注内容" --phrase 挂载锚点 [--anchor 另锚短语] [作者] [日期ISO]
    （--phrase 必填：决定批注挂在谁身上；--anchor 可选：把批注锚到另一处，如被删掉的那段字）
"""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.run import Run
from lxml import etree

from apply_track_changes import open_for_revision, split_run_at

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENTS_CT = ("application/vnd.openxmlformats-officedocument"
               ".wordprocessingml.comments+xml")
COMMENTS_RT = ("http://schemas.openxmlformats.org/officeDocument"
               "/2006/relationships/comments")


# ── 批注锚点 ─────────────────────────────────────────────────────────────
def _comment_ref_run(cid):
    """造一个只含批注引用的 run（必须放在 commentRangeEnd 之后）。"""
    r = OxmlElement("w:r")
    ref = OxmlElement("w:commentReference")
    ref.set(qn("w:id"), str(cid))
    r.append(ref)
    return r


def _range_start(cid):
    el = OxmlElement("w:commentRangeStart")
    el.set(qn("w:id"), str(cid))
    return el


def _range_end(cid):
    el = OxmlElement("w:commentRangeEnd")
    el.set(qn("w:id"), str(cid))
    return el


def _pending(doc):
    lst = getattr(doc, "_pending_comments", None)
    if lst is None:
        lst = []
        try:
            doc._pending_comments = lst
        except AttributeError:      # 某些 Document 实现不允许挂属性
            pass
    return lst


def _run_text_all(r_el):
    """run 内的全部文本——`w:t` 与 `w:delText` 都算（被删文字在 delText 里）。"""
    out = []
    for child in r_el.iter():
        if child.tag in (qn("w:t"), qn("w:delText")):
            out.append(child.text or "")
    return "".join(out)


def _find_run(p_el, phrase):
    """在段落 XML 树里找含 phrase 的 run。

    **必须穿透 w:ins / w:del**——`paragraph.runs` 只返回直系 w:r，
    修订标记里的文字用它找不到；而"给一处删除写批注"正是最常见的用法。
    """
    for r_el in p_el.iter(qn("w:r")):
        if phrase in _run_text_all(r_el):
            return r_el
    return None


def add_comment(doc, p_idx, phrase, text, author="审校",
                date_iso="2026-10-30T00:00:00Z", anchor_phrase=None):
    """给段落 p_idx 中 `phrase` 锚点处加一条批注，返回批注 id。

    `phrase`   —— **批注锚定到哪段文字**（决定批注挂在谁身上）
    `text`     —— 批注内容（"为什么这么改"）
    `anchor_phrase` —— 可选：**另一个**短语，用途是"这条批注是解释某个删除操作的"
                 ——锚点会落在该短语所在的**修订标记**上（w:del / w:ins），
                 与人工"在旁边写一句说明"的观感一致。

    锚定规则：
      · 锚点落在普通 run 上 → 切分 run，批注**只覆盖该短语**（同人工选中一段加批注）
      · 锚点落在 w:ins / w:del 内 → **不切分**（切了会破坏修订结构），
        批注范围包住整个修订标记
    """
    p = doc.paragraphs[p_idx]
    p_el = p._p
    target_el = _find_run(p_el, phrase)
    if target_el is None:
        raise ValueError(f"批注锚点未找到: 段落 {p_idx} 中不含 {phrase!r}")

    parent = target_el.getparent()
    if parent is not None and parent.tag in (qn("w:ins"), qn("w:del")):
        anchor_el = parent          # 修订标记内：包住整个标记，不切分
    else:
        run = Run(target_el, p)
        off = run.text.find(phrase)
        if off > 0:
            split_run_at(run, off)
            nxt = run._r.getnext()
            if nxt is None or nxt.tag != qn("w:r"):
                raise ValueError("批注锚点切分失败")
            target_el = nxt
        if _run_text_all(target_el)[len(phrase):]:
            split_run_at(Run(target_el, p), len(phrase))
        anchor_el = target_el

    # 批注 id
    lst = _pending(doc)
    cid = max([c[0] for c in lst], default=0) + 1

    # anchor_phrase：批注锚到另一处（通常是"被删掉的那段字"）
    if anchor_phrase:
        other = _find_run(p_el, anchor_phrase)
        if other is not None:
            op = other.getparent()
            anchor_el = op if (op is not None and
                               op.tag in (qn("w:ins"), qn("w:del"))) else other

    # 顺序必须是 start → 被批注内容 → end → reference
    # （commentReference 必须在 commentRangeEnd **之后**，否则 WPS/Word 认不出引用）
    anchor_el.addprevious(_range_start(cid))
    end_el = _range_end(cid)
    anchor_el.addnext(end_el)
    end_el.addnext(_comment_ref_run(cid))

    lst.append((cid, author, date_iso, text))
    return cid


class _RunShim:
    """给 split_run_at 用的轻量代理（它只用到 ._r 和 .text）。"""

    def __init__(self, r_el, text):
        self._r = r_el
        self.text = text



# ── comments.xml 与 zip 后处理 ────────────────────────────────────────────
def _build_comments_xml(comments):
    root = etree.Element("{%s}comments" % W_NS, nsmap={"w": W_NS})
    for cid, author, date_iso, text in comments:
        c = etree.SubElement(root, "{%s}comment" % W_NS)
        c.set("{%s}id" % W_NS, str(cid))
        c.set("{%s}author" % W_NS, author)
        c.set("{%s}date" % W_NS, date_iso)
        c.set("{%s}initials" % W_NS, (author or "审")[:1])
        cp = etree.SubElement(c, "{%s}p" % W_NS)
        # annotationRef：批注首 run 的标准标记，WPS 靠它识别批注起点
        r1 = etree.SubElement(cp, "{%s}r" % W_NS)
        etree.SubElement(r1, "{%s}annotationRef" % W_NS)
        r2 = etree.SubElement(cp, "{%s}r" % W_NS)
        t = etree.SubElement(r2, "{%s}t" % W_NS)
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                          standalone=True)


def _inject_comments(docx_path, comments):
    """把批注部件注入已保存的 docx（Content_Types + 关系 + comments.xml）。"""
    with zipfile.ZipFile(docx_path, "r") as zin:
        items = [(n, zin.read(n)) for n in zin.namelist()]

    # ② Content_Types：登记 comments.xml
    ct = etree.fromstring(dict(items)["[Content_Types].xml"])
    have = any(o.get("PartName") == "/word/comments.xml"
               for o in ct.findall("{%s}Override" % CT_NS))
    if not have:
        ov = etree.SubElement(ct, "{%s}Override" % CT_NS)
        ov.set("PartName", "/word/comments.xml")
        ov.set("ContentType", COMMENTS_CT)

    # ③ 关系：document.xml.rels → comments.xml
    rels_name = "word/_rels/document.xml.rels"
    rels = etree.fromstring(dict(items)[rels_name])
    max_id = 0
    for rel in rels.findall("{%s}Relationship" % REL_NS):
        rid = rel.get("Id") or ""
        if rid.startswith("rId") and rid[3:].isdigit():
            max_id = max(max_id, int(rid[3:]))
    new_rid = "rId%d" % (max_id + 1)
    rel = etree.SubElement(rels, "{%s}Relationship" % REL_NS)
    rel.set("Id", new_rid)
    rel.set("Type", COMMENTS_RT)
    rel.set("Target", "comments.xml")

    data = dict(items)
    data["[Content_Types].xml"] = etree.tostring(
        ct, xml_declaration=True, encoding="UTF-8", standalone=True)
    data[rels_name] = etree.tostring(
        rels, xml_declaration=True, encoding="UTF-8", standalone=True)
    data["word/comments.xml"] = _build_comments_xml(comments)

    # 重写 zip：把 [Content_Types].xml 放在首位（OPC 规范要求它先出现）
    order = [n for n, _ in items if n != "[Content_Types].xml"]
    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("[Content_Types].xml", data["[Content_Types].xml"])
        for n in order:
            zout.writestr(n, data[n])
        zout.writestr("word/comments.xml", data["word/comments.xml"])


def save_with_comments(doc, path):
    """保存 docx；若有待写批注，保存后注入 comments.xml。"""
    doc.save(path)
    lst = getattr(doc, "_pending_comments", None)
    if lst:
        _inject_comments(path, lst)
    return len(lst or [])


# ── CLI ───────────────────────────────────────────────────────────────────
def _die(msg, hint):
    print(f"❌ {msg}")
    print(f"💡 怎么办：{hint}")
    sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]

    def _take(flag):
        """取出 `flag 其值` 对并从位置参数里删掉；返回 None 表示未给。"""
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                _die(f"{flag} 缺少取值", f"{flag} 后必须跟一个短语，如 {flag} \"科学发展观\"。")
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return None

    phrase = _take("--phrase")
    anchor = _take("--anchor")
    if not phrase:
        # 不再静默取首 run 当锚点——锚点必须明示，避免批注挂错地方
        _die("缺少 --phrase（批注挂载锚点，必填）",
             "用法：python3 add_comment.py 原件.docx 输出.docx 段落号 \"批注内容\" "
             "--phrase 挂载锚点 [--anchor 另锚短语] [作者] [日期ISO]。"
             "--phrase 决定批注挂在谁身上；--anchor 是另锚（可选）。")
    if len(args) < 4:
        _die("参数不足",
             "用法：python3 add_comment.py 原件.docx 输出.docx 段落号 \"批注内容\" "
             "--phrase 挂载锚点 [--anchor 另锚短语] [作者] [日期ISO]")
    src, out, p_idx, ctext = args[0], args[1], int(args[2]), args[3]
    author = args[4] if len(args) > 4 else "审校"
    date_iso = args[5] if len(args) > 5 else "2026-10-30T00:00:00Z"
    try:
        doc, counter, a, d = open_for_revision(src, author, date_iso)
        cid = add_comment(doc, p_idx, phrase, ctext, a, d, anchor_phrase=anchor)
        n = save_with_comments(doc, out)
        print(f"完成: {out}  批注 {n} 条（id={cid}）")
    except FileNotFoundError:
        _die(f"找不到文件：{src}", "检查路径拼写；含空格的路径用引号包住。")
    except IndexError:
        _die(f"段落号越界：{p_idx}", "用 python-docx 数一下段落序号（从 0 起）。")
    except ValueError as e:
        _die(f"添加批注失败：{e}",
             "锚点短语必须与正文逐字一致；先打印该段落的 run 列表确认精确字符。")
