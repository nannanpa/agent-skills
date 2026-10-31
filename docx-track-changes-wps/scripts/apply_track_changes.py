#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WPS-safe tracked-change (tracked changes / redline) writer for .docx.

Usage:
    python apply_track_changes.py SRC.docx OUTPUT.docx [author] [date_iso]
        # 只启用修订、保存并校验，不修改正文（stdout 明示）
    python apply_track_changes.py SRC.docx OUT.docx --p-idx 5 --phrase "原句尾部。" --text "（新增内容）"
        # 真插入：在段落 5 的锚点短语后写入 w:ins 修订
    python apply_track_changes.py SRC.docx OUT.docx --p-idx 8 --phrase "发辉" --text "发挥" --del
        # 真勘误：删旧换新（--text 缺省=纯删除），走 apply_del()

Or import and drive the apply() helpers from your own script.

Two modes:
  · Insertion (default) — keeps original text, adds new text as <w:ins> right
    after an anchor run. Preferred mode: safest for WPS.
  · Correction — for text that must actually be removed or replaced (errata,
    wrong characters, dropped words). Uses <w:del> + <w:delText>, optionally
    followed by <w:ins> carrying the replacement.

Note on the "avoid w:del" folklore: <w:del> is not inherently unsafe. The
rainbow-spinner hang comes from malformed structures (duplicate w:id, missing
author/date, stray rPr, touching body-level sectPr) — not from w:del itself.
A correction that cannot be expressed as an insertion MUST use w:del;
modelling it as "insert the new text and leave the wrong text" is worse.
"""
import copy
import sys
import docx
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def _max_revision_id(doc):
    """扫描正文既有修订（w:ins / w:del）的 w:id 最大值。

    文档自带修订史时（真实公文常态），固定 10001 起号必然撞号
    （Windows 侧 2026-10-14 实测复现），故起号取 max(10000, 既有最大值)。
    """
    m = 0
    for tag in ("w:ins", "w:del"):
        for el in doc.element.body.iter(qn(tag)):
            v = el.get(qn("w:id"))
            if v and v.lstrip("-").isdigit() and abs(int(v)) > m:
                m = abs(int(v))
    return m


def open_for_revision(src, author="审校", date_iso="2026-07-23T09:00:00Z"):
    """Open src, enable trackChanges + rsidRoot, return (doc, counter)."""
    doc = docx.Document(src)
    settings = doc.settings.element

    def ensure_child(parent, tag, attrs=None, before_tags=()):
        """Find a *direct* child `tag` of parent; create it if missing.

        New elements are inserted before the first present tag listed in
        `before_tags`（CT_Settings schema-order anchors），保持 settings.xml
        元素顺序合法；都不存在时才追加到末尾。
        """
        el = parent.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            if attrs:
                for k, v in attrs.items():
                    el.set(qn(k), v)
            anchor = None
            for bt in before_tags:
                anchor = parent.find(qn(bt))
                if anchor is not None:
                    break
            if anchor is not None:
                anchor.addprevious(el)
            else:
                parent.append(el)
        elif attrs:
            for k, v in attrs.items():
                el.set(qn(k), v)
        return el

    # CT_Settings 顺序：trackChanges 应位于 defaultTabStop 等后继元素之前
    ensure_child(settings, "w:trackChanges", {"w:val": "true"},
                 before_tags=("w:defaultTabStop", "w:characterSpacingControl",
                              "w:savePreviewPicture", "w:compat", "w:docVars",
                              "w:rsids", "w:mathPr"))
    # w:rsidRoot / w:rsidRDefault 不是 w:settings 的直接子元素，而是包在 w:rsids 内；
    # 旧版直接 append 到 settings 下属非法位置（实测 rsidRoot 嵌在 w:rsids 里，
    # settings.find 永远找不到，导致重复追加非法元素），Word/WPS 均可能拒开。
    rsids = ensure_child(settings, "w:rsids",
                         before_tags=("w:mathPr", "w:themeFontLang",
                                      "w:clrSchemeMapping", "w:decimalSymbol",
                                      "w:listSeparator"))
    rsid_default = rsids.find(qn("w:rsidRDefault"))
    root_val = rsid_default.get(qn("w:val")) if rsid_default is not None else "00FF1234"
    ensure_child(rsids, "w:rsidRoot", {"w:val": root_val})
    counter = [max(10000, _max_revision_id(doc))]
    return doc, counter, author, date_iso


def _rpr_for(r_el, p_el=None):
    """取用于新 run 的 <w:rPr> 副本——**格式继承的唯一入口**。

    人工在 Word/WPS 里输入文字，插入点会自动继承"当前格式"（字体、字号、
    加粗、字符样式等）。脚本若新建一个不带 rPr 的 run，插入的文字就掉回
    文档默认字体，与人工操作观感不一致——这正是 1.1.0 修掉的缺陷。

    取值优先级：
      ① 该 run 自身的 rPr（直接格式，最常见）；
      ② 段落标记的 rPr（w:pPr/w:rPr）——正文 run 不带直接格式、靠段落样式
         排版时，段落标记格式才是"当前格式"；
      ③ 都没有 → 返回 None，新 run 不带 rPr，自动继承段落样式（正确行为）。

    **必须剔除 w:rPrChange**：那是格式修订标记，复制过来会形成嵌套修订，
    Word/WPS 可能拒开文件（与"彩虹圈"同源的结构性风险）。
    """
    rpr = r_el.find(qn("w:rPr")) if r_el is not None else None
    if rpr is None and p_el is not None:
        ppr = p_el.find(qn("w:pPr"))
        if ppr is not None:
            rpr = ppr.find(qn("w:rPr"))
    if rpr is None:
        return None
    new = copy.deepcopy(rpr)
    for ch in new.findall(qn("w:rPrChange")):
        new.remove(ch)
    return new


def make_ins(text, counter, author, date_iso, rpr=None):
    """造一个 <w:ins> 修订插入。

    `rpr` 是要继承的 <w:rPr> 元素（由 _rpr_for 提供）；必须作为 <w:r> 的
    **第一个子元素**（OOXML schema：w:rPr 在 w:t 之前）。
    """
    ins = OxmlElement("w:ins")
    counter[0] += 1
    ins.set(qn("w:id"), str(counter[0]))
    ins.set(qn("w:author"), author)
    ins.set(qn("w:date"), date_iso)
    r = OxmlElement("w:r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    ins.append(r)
    return ins


def make_del(r_el, counter, author, date_iso):
    """Wrap a run element in <w:del>, turning its <w:t> into <w:delText>.

    The run keeps its original <w:rPr> (formatting must survive the deletion
    marker); only the text-bearing tag changes. Returns the new w:del element.
    """
    del_el = OxmlElement("w:del")
    counter[0] += 1
    del_el.set(qn("w:id"), str(counter[0]))
    del_el.set(qn("w:author"), author)
    del_el.set(qn("w:date"), date_iso)
    r_el.getparent().replace(r_el, del_el)
    del_el.append(r_el)
    for t in r_el.findall(qn("w:t")):
        t.tag = qn("w:delText")
    return del_el


def _run_text(r_el):
    """Full text of a run element (concatenates all w:t children)."""
    return "".join(t.text or "" for t in r_el.findall(qn("w:t")))


def split_insert(run, off, text, counter, author, date_iso):
    """Insert <w:ins> at character offset `off` inside `run`.

    off == len(run.text) appends right after the run; otherwise the run is
    split at `off` first and the insertion lands between prefix and suffix.

    插入内容**继承该 run 的字符格式**（与人工输入一致，见 _rpr_for）。
    """
    rpr = _rpr_for(run._r, run._r.getparent())
    if off >= len(run.text):
        run._r.addnext(make_ins(text, counter, author, date_iso, rpr))
        return
    if off > 0:
        split_run_at(run, off)      # run keeps prefix, suffix becomes next sibling
    run._r.addnext(make_ins(text, counter, author, date_iso, rpr))


def del_insert(run, off, length, text, counter, author, date_iso):
    """Delete run text [off, off+length) as <w:del>; optionally insert `text` after it.

    `text` empty → pure deletion. Non-empty → the deleted span is marked and the
    replacement follows as <w:ins>, which is how a reviewer sees "wrong → right".
    """
    if not (0 <= off and off + length <= len(run.text)):
        raise ValueError(f"range out of bounds: {run.text!r} [{off},{off+length})")
    # 1) isolate the span as its own run
    if off > 0:
        split_run_at(run, off)                       # run -> prefix, next sibling = target
        target = run._r.getnext()
        if target is None or target.tag != qn("w:r"):
            raise ValueError("failed to locate target run after split")
    else:
        target = run._r
    # 2) if the span does not end the run, cut the remainder off
    tlen = len(_run_text(target))
    if length < tlen:
        class _P:
            pass
        proxy = _P()
        proxy._r = target
        proxy.text = _run_text(target)
        split_run_at(proxy, length)                  # target -> span, suffix follows
    # 3) mark the span deleted, then optionally insert the replacement
    # 替换文字继承**被替换文字**的格式（人工改字时新字随原字格式）
    rpr = _rpr_for(target, target.getparent())
    del_el = make_del(target, counter, author, date_iso)
    if text:
        del_el.addnext(make_ins(text, counter, author, date_iso, rpr))


def split_run_at(run, offset):
    """Truncate run to text[:offset]; return a new sibling run with text[offset:]."""
    r_el = run._r
    full = run.text
    if offset >= len(full):
        return
    prefix = full[:offset]
    suffix = full[offset:]
    new_r = OxmlElement("w:r")
    rpr = r_el.find(qn("w:rPr"))
    if rpr is not None:
        new_r.append(copy.deepcopy(rpr))
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = suffix
    new_r.append(t)
    r_el.addnext(new_r)
    for child in list(r_el):
        if child.tag in (qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")):
            r_el.remove(child)
    t2 = OxmlElement("w:t")
    t2.set(qn("xml:space"), "preserve")
    t2.text = prefix
    r_el.append(t2)


def apply(doc, counter, author, date_iso, p_idx, phrase, text):
    """Insert `text` as a tracked-change right after `phrase` in paragraph p_idx.

    `phrase` must be a substring found within a SINGLE run of that paragraph.
    Anchor on the run that starts with the phrase tail; use Unicode escapes in
    `phrase` when hidden chars (e.g. 》）—) may be present.

    插入内容**继承锚点 run 的字符格式**（字体/字号/加粗/字符样式），
    与人工在 Word 里输入的观感一致（1.1.0 修掉的缺陷）。
    """
    p = doc.paragraphs[p_idx]
    for run in p.runs:
        if phrase in run.text:
            off = run.text.find(phrase)
            end = off + len(phrase)
            rpr = _rpr_for(run._r, run._r.getparent())
            if end >= len(run.text):
                run._r.addnext(make_ins(text, counter, author, date_iso, rpr))
            else:
                split_run_at(run, end)
                run._r.addnext(make_ins(text, counter, author, date_iso, rpr))
            return
    raise ValueError(f"anchor phrase not found in paragraph {p_idx}: {phrase!r}")


def apply_del(doc, counter, author, date_iso, p_idx, phrase, replacement=""):
    """Replace (or delete) `phrase` in paragraph p_idx as a tracked correction.

    `phrase` must sit inside a SINGLE run of that paragraph — same rule as
    apply(). replacement="" means pure deletion. Returns the run that carried
    the phrase, so callers can chain further edits on the same paragraph.
    """
    p = doc.paragraphs[p_idx]
    for run in p.runs:
        if phrase in run.text:
            off = run.text.find(phrase)
            del_insert(run, off, len(phrase), replacement, counter, author, date_iso)
            return run
    raise ValueError(f"anchor phrase not found in paragraph {p_idx}: {phrase!r}")


def _fmt_sig(r_el):
    """run 的关键格式指纹：字体/字号/加粗/斜体/下划线/字符样式。

    返回 None 表示该 run 无直接格式（靠段落样式呈现）。
    """
    if r_el is None:
        return None
    rpr = r_el.find(qn("w:rPr"))
    if rpr is None:
        return None
    sig = {}
    rf = rpr.find(qn("w:rFonts"))
    if rf is not None:
        sig["fonts"] = (rf.get(qn("w:ascii")), rf.get(qn("w:eastAsia")),
                        rf.get(qn("w:hAnsi")))
    for tag in ("w:sz", "w:szCs", "w:b", "w:i", "w:u", "w:rStyle"):
        el = rpr.find(qn(tag))
        if el is not None:
            sig[tag] = el.get(qn("w:val")) if el.get(qn("w:val")) is not None else "1"
    return sig


def verify(path, expect_ins=None, expect_del=None, check_fmt=False,
            check_comments=False):
    import zipfile
    from lxml import etree
    z = zipfile.ZipFile(path)
    assert z.testzip() is None, "zip corrupted"
    etree.fromstring(z.read("word/document.xml"))  # well-formed
    root = etree.fromstring(z.read("word/document.xml"))
    # settings.xml 结构回归（防 rsidRoot 错位复发）
    sroot = etree.fromstring(z.read("word/settings.xml"))
    assert sroot.find(qn("w:trackChanges")) is not None, "trackChanges missing"
    rsids_el = sroot.find(qn("w:rsids"))
    assert rsids_el is not None and rsids_el.find(qn("w:rsidRoot")) is not None, \
        "w:rsidRoot must live inside w:rsids"
    assert sroot.find(qn("w:rsidRoot")) is None, \
        "w:rsidRoot must NOT be a direct child of w:settings"
    body = root.find(qn("w:body"))
    ins = body.findall(".//" + qn("w:ins"))
    dels = body.findall(".//" + qn("w:del"))
    # 1.1.0：w:ins 与 w:del 共用同一 id 空间——必须合起来查唯一性，
    # 只查 ins 会漏掉 del 与 ins 撞号的情况（撞号是彩虹圈卡死首因）。
    all_ids = [i.get(qn("w:id")) for i in ins] + [d.get(qn("w:id")) for d in dels]
    assert len(set(all_ids)) == len(all_ids), "duplicate w:id across w:ins and w:del"
    for i in ins:
        assert i.get(qn("w:author")) and i.get(qn("w:date")) and i.find(qn("w:r")) is not None
    for d in dels:
        assert d.get(qn("w:author")) and d.get(qn("w:date")) and d.find(qn("w:r")) is not None
        # 删除标记内的文本必须是 w:delText；残留 w:t 会被 Word/WPS 当成未删内容
        assert d.find(".//" + qn("w:t")) is None, "w:del contains w:t (must be w:delText)"
        assert d.find(".//" + qn("w:delText")) is not None, "w:del missing w:delText"
    if expect_ins is not None:
        assert len(ins) == expect_ins, f"expected {expect_ins} w:ins, got {len(ins)}"
    if expect_del is not None:
        assert len(dels) == expect_del, f"expected {expect_del} w:del, got {len(dels)}"
    if check_fmt:
        # 格式继承回归（1.1.0 修掉的缺陷）：插入的 run 若不带 rPr，
        # 文字会掉回文档默认字体——与人工在 Word 里输入的观感不一致。
        # 判据：插入 run 与它**前一个普通 run** 的格式指纹必须一致；
        # 前一个 run 本就无直接格式时，两者都靠段落样式，视为一致。
        for i in ins:
            r = i.find(qn("w:r"))
            prev = i.getprevious()
            while prev is not None and prev.tag != qn("w:r"):
                prev = prev.getprevious()
            if prev is None:
                continue
            sig_ins = _fmt_sig(r)
            sig_prev = _fmt_sig(prev)
            if sig_prev is None:
                continue
            assert sig_ins == sig_prev, \
                f"插入内容未继承当前格式: {sig_ins} != {sig_prev}"
    if check_comments:
        # 批注结构回归（1.1.0）：批注要动四个地方，缺一个 Word/WPS 就打不开
        # 或看不到批注——comments.xml / [Content_Types].xml / document.xml.rels /
        # document.xml 的锚点。逐项断言，别等打开才发现。
        names = z.namelist()
        assert "word/comments.xml" in names, "批注部件 word/comments.xml 缺失"
        croot = etree.fromstring(z.read("word/comments.xml"))
        cs = croot.findall(qn("w:comment"))
        for c in cs:
            assert c.get(qn("w:id")) is not None, "批注缺 w:id"
            assert c.get(qn("w:author")), "批注缺 w:author"
            assert c.get(qn("w:date")), "批注缺 w:date"
            assert c.find(".//" + qn("w:t")) is not None, "批注正文为空"
        ct = etree.fromstring(z.read("[Content_Types].xml"))
        ct_parts = [o.get("PartName") for o in ct]
        assert "/word/comments.xml" in ct_parts, \
            "comments.xml 未在 [Content_Types].xml 登记（Word 会打不开文件）"
        rels = etree.fromstring(z.read("word/_rels/document.xml.rels"))
        rel_targets = [r.get("Target") for r in rels]
        assert "comments.xml" in rel_targets, \
            "comments.xml 未在 word/_rels/document.xml.rels 登记（批注与正文无关联）"
        # 锚点配对：start / end / reference 三者的 id 集合必须一致
        starts = body.findall(".//" + qn("w:commentRangeStart"))
        ends = body.findall(".//" + qn("w:commentRangeEnd"))
        refs = body.findall(".//" + qn("w:commentReference"))
        s_ids = sorted(e.get(qn("w:id")) for e in starts)
        e_ids = sorted(e.get(qn("w:id")) for e in ends)
        r_ids = sorted(e.get(qn("w:id")) for e in refs)
        c_ids = sorted(c.get(qn("w:id")) for c in cs)
        assert s_ids == e_ids, f"commentRangeStart/End 不配对: {s_ids} vs {e_ids}"
        assert r_ids == c_ids, f"commentReference 与 comments.xml 不匹配: {r_ids} vs {c_ids}"
        # 顺序：每条批注的 reference 必须排在其 commentRangeEnd **之后**
        # （写反了 WPS 显示不出批注——1.1.0 实战踩到）
        for p in body.iter(qn("w:p")):
            ended = set()
            for k in p:
                if k.tag == qn("w:commentRangeEnd"):
                    ended.add(k.get(qn("w:id")))
                elif k.tag == qn("w:r"):
                    ref = k.find(qn("w:commentReference"))
                    if ref is not None:
                        rid = ref.get(qn("w:id"))
                        assert rid in ended, \
                            f"commentReference(id={rid}) 出现在其 commentRangeEnd 之前"
        print(f"OK: 批注 {len(cs)} 条，锚点配对与顺序正确")
    print(f"OK: w:ins={len(ins)} w:del={len(dels)} ids_unique={len(set(all_ids))==len(all_ids)}")
    return len(ins), len(dels)


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
                _die(f"{flag} 缺少取值", f"{flag} 后必须跟一个值，如 {flag} 5。")
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return None

    p_idx = _take("--p-idx")
    phrase = _take("--phrase")
    text = _take("--text")
    del_mode = "--del" in args
    if del_mode:
        args.remove("--del")

    if p_idx is None and phrase is None and text is None and not del_mode:
        insert_op = None            # 未给任何操作参数 → 只保存并校验
    else:
        # 给了操作参数：插入模式三样齐（--p-idx/--phrase/--text），
        # 勘误模式（--del）两样齐（--p-idx/--phrase；--text 缺省=纯删除）
        if p_idx is None or phrase is None or (text is None and not del_mode):
            _die("修订参数不完整",
                 "插入：--p-idx 段落号 --phrase 锚点短语 --text 新增文字；"
                 "勘误（--del）：--p-idx 段落号 --phrase 待删短语 [--text 替换文字，缺省=纯删除]。"
                 "例：python3 apply_track_changes.py 原件.docx 输出.docx "
                 "--p-idx 5 --phrase \"规划的任务分解和具体落实。\" --text \"（补充说明）\"")
        try:
            p_idx = int(p_idx)
        except (TypeError, ValueError):
            _die("--p-idx 不是整数", f"实得 {p_idx!r}；段落号从 0 起计。")
        insert_op = (p_idx, phrase, text, del_mode)

    if len(args) < 2:
        _die("参数不足", "用法：python3 apply_track_changes.py 原件.docx 输出.docx [作者] [日期ISO] [--p-idx N --phrase 短语 --text 新文 | --del]。前两个路径必填，含空格用引号包住。")
    src, out = args[0], args[1]
    author = args[2] if len(args) > 2 else "审校"
    date_iso = args[3] if len(args) > 3 else "2026-07-23T09:00:00Z"
    try:
        doc, counter, a, d = open_for_revision(src, author, date_iso)
        if insert_op is None:
            doc.save(out)
            verify(out)
            print("ℹ 仅保存并校验，未修改正文（真插入请加 --p-idx N --phrase 短语 --text 新文；勘误加 --del）")
        else:
            p_idx, phrase, text, del_mode = insert_op
            if del_mode:
                apply_del(doc, counter, a, d, p_idx, phrase, text or "")
            else:
                apply(doc, counter, a, d, p_idx, phrase, text)
            doc.save(out)
            verify(out)
    except FileNotFoundError:
        _die(f"找不到文件：{src}", "检查路径拼写；含空格的路径用引号包住。")
    except AssertionError as e:
        _die(f"结构校验未通过：{e}", "先跑 self_test.py 确认环境正常；再对照 SKILL.md「彩虹圈规避清单」逐条排查。原件先用副本，别在原件上重试。")
    except Exception as e:
        m = str(e)
        if "Content_Types" in m or "no such file" in m.lower():
            _die(f"{src} 不是有效的 .docx 文件", "确认扩展名是 .docx 而不是 .doc/.rtf/.wps；必要时先用 WPS 另存为 .docx。")
        _die(f"处理失败：{m}", "先用 self_test.py 验证环境；仍失败时保留原件并到 SKILL.md「已知坑」对照排查。")
