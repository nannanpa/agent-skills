#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 .docx 的修订与批注为 Markdown 清单——docx-track-changes-wps 配套脚本，版本随 SKILL.md 头部。

为什么需要它：技能的应用场景写的是"修改意见报送"——审校完要给人一份
**看得懂的清单**，而不是丢一个带修订轨的 docx 让对方自己找。
本脚本把 docx 里的两套标记整理成两张表：

    ① 修订标记表（w:ins / w:del）：谁、什么时候、把哪段字删了/插了什么
    ② 批注表（w:comment）：批注挂在哪段文字上、内容是什么

**纯读取，不改文件**——可以放心对任何产物跑。

用法：
    python3 export_markup.py 文件.docx [-o 输出.md]
    python3 export_markup.py 文件.docx --json      # 程序化消费
"""
import json
import os
import sys
import zipfile

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _text_of(el):
    """元素的全部文字（w:t 与 w:delText 都算，修订内外都收）。"""
    return "".join((c.text or "") for c in el.iter()
                   if c.tag in (W + "t", W + "delText"))


def _para_context(p_el, limit=40):
    """段落原文（去掉标记后），用作批注的上下文。"""
    t = _text_of(p_el).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def export(path):
    """返回 {"revisions": [...], "comments": [...]}。"""
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        body = root.find(W + "body")
        comments = {}
        if "word/comments.xml" in z.namelist():
            croot = etree.fromstring(z.read("word/comments.xml"))
            for c in croot.findall(W + "comment"):
                comments[c.get(W + "id")] = {
                    "author": c.get(W + "author") or "",
                    "date": c.get(W + "date") or "",
                    "text": "".join(t.text or "" for t in c.iter(W + "t")),
                }

    revisions = []
    cmts = []
    # 段落号与 python-docx 的 doc.paragraphs 对齐：只取 body 的直接子 w:p
    for p_idx, p_el in enumerate(body.findall(W + "p")):
        # 修订标记
        for kind, tag in (("插入", W + "ins"), ("删除", W + "del")):
            for el in p_el.iter(tag):
                revisions.append({
                    "para": p_idx,
                    "kind": kind,
                    "id": el.get(W + "id"),
                    "author": el.get(W + "author") or "",
                    "date": el.get(W + "date") or "",
                    "text": _text_of(el),
                    "context": _para_context(p_el),
                })
        # 批注锚点：start…end 之间的文字
        anchor_text = {}
        cur = None
        for k in p_el:
            if k.tag == W + "commentRangeStart":
                cur = k.get(W + "id")
                anchor_text[cur] = ""
            elif k.tag == W + "commentRangeEnd":
                cur = None
            elif cur is not None:
                anchor_text[cur] += _text_of(k)
        for cid, atext in anchor_text.items():
            meta = comments.get(cid, {})
            cmts.append({
                "id": cid,
                "para": p_idx,
                "anchor": atext.strip(),
                "text": meta.get("text", ""),
                "author": meta.get("author", ""),
                "date": meta.get("date", ""),
                "context": _para_context(p_el),
            })
    return {"revisions": revisions, "comments": cmts}


def to_markdown(data, src_name):
    revs, cmts = data["revisions"], data["comments"]
    out = [f"# 修订与批注清单 · {src_name}\n"]
    out.append(f"修订标记 {len(revs)} 处 ／ 批注 {len(cmts)} 条\n")
    if revs:
        out.append("## 一、修订标记\n")
        out.append("| # | 段落 | 动作 | 内容 | 作者 | 日期 |")
        out.append("|---|---|---|---|---|---|")
        for i, r in enumerate(revs, 1):
            txt = r["text"].replace("|", "丨").replace("\n", " ")
            out.append(f"| {i} | {r['para']} | {r['kind']} | {txt} "
                       f"| {r['author']} | {r['date']} |")
        out.append("")
    if cmts:
        out.append("## 二、批注\n")
        out.append("| # | 段落 | 锚定文字 | 批注内容 | 作者 | 日期 |")
        out.append("|---|---|---|---|---|---|")
        for i, c in enumerate(cmts, 1):
            a = c["anchor"].replace("|", "丨").replace("\n", " ")
            t = c["text"].replace("|", "丨").replace("\n", " ")
            out.append(f"| {i} | {c['para']} | {a} | {t} "
                       f"| {c['author']} | {c['date']} |")
        out.append("")
    if not revs and not cmts:
        out.append("（该文件没有修订标记，也没有批注。）\n")
    return "\n".join(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("❌ 参数不足")
        print("💡 怎么办：用法：python3 export_markup.py 文件.docx [-o 输出.md] [--json]")
        sys.exit(1)
    path = args[0]
    if not os.path.exists(path):
        print(f"❌ 找不到文件：{path}")
        print("💡 怎么办：检查路径拼写；含空格的路径用引号包住。")
        sys.exit(1)
    try:
        data = export(path)
    except zipfile.BadZipFile:
        print(f"❌ {path} 不是有效的 .docx")
        print("💡 怎么办：扩展名是 .docx 不代表内容是 OOXML；先用 WPS 另存为真正的 .docx。")
        sys.exit(1)
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    md = to_markdown(data, os.path.basename(path))
    if "-o" in sys.argv:
        out = sys.argv[sys.argv.index("-o") + 1]
        with open(out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"完成: {out}  修订 {len(data['revisions'])} 处 / 批注 {len(data['comments'])} 条")
    else:
        print(md)


if __name__ == "__main__":
    main()
