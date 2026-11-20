#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx-format-guard · 读回自检
生成 docx 后回读，对五项做断言：字体 / 字号 / 行距 / 页边距 / 首行缩进。
另含三个坑的显式校验（见 LESSONS.md）。

门禁（写死）：五项读回断言全过才允许交付；任一项不过即停并报
“哪一项、实测多少、参数单写的多少”。

用法：python selfcheck.py --set A|B --docx <path.docx>
退出码：全过 0；任一不过 1（即停）。
"""
import json, os, sys
from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS = os.path.join(SKILL_DIR, "scripts", "params.json")

TOL_CM = 0.03      # 页边距容差
TOL_PT = 0.5       # 字号/缩进/行距容差


def load(setname):
    with open(PARAMS, encoding='utf-8') as f:
        data = json.load(f)
    return data["sets"][setname]


def eastasia_of(run):
    rpr = run._element.find(qn('w:rPr'))
    if rpr is None:
        return None
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        return None
    return rfonts.get(qn('w:eastAsia'))


def run_ea_and_size(run):
    return eastasia_of(run), (run.font.size.pt if run.font.size else None)


def check(setname, docx_path):
    p = load(setname)
    doc = Document(docx_path)
    sec = doc.sections[0]
    paras = doc.paragraphs

    rows = []  # (项, 判据值, 实测值, 是否通过, 备注)

    def add(item, expected, measured, ok, note=""):
        rows.append((item, expected, measured, ok, note))

    # —— 1) 页边距 ——
    pg = p["page"]
    m_expected = (pg["margin_top_cm"], pg["margin_bottom_cm"],
                  pg["margin_left_cm"], pg["margin_right_cm"])
    m_measured = (round(sec.top_margin.cm, 2), round(sec.bottom_margin.cm, 2),
                  round(sec.left_margin.cm, 2), round(sec.right_margin.cm, 2))
    m_ok = all(abs(a - b) <= TOL_CM for a, b in zip(m_expected, m_measured))
    add("页边距(cm) 上/下/左/右", "/".join(map(str, m_expected)),
        "/".join(map(str, m_measured)), m_ok)

    # —— 标题（para[0]）字体/字号 ——
    t = p["title"]
    ea, sz = run_ea_and_size(paras[0].runs[0])
    add("标题字体(eastAsia)", t["font"], ea, ea == t["font"])
    add("标题字号(pt)", t["size_pt"], sz, sz is not None and abs(sz - t["size_pt"]) <= TOL_PT)

    # —— 一级标题（para[1]）字体/字号 ——
    h = p["heading1"]
    ea, sz = run_ea_and_size(paras[1].runs[0])
    add("一级标题字体(eastAsia)", h["font"], ea, ea == h["font"])
    add("一级标题字号(pt)", h["size_pt"], sz, sz is not None and abs(sz - h["size_pt"]) <= TOL_PT)

    # —— 正文（para[2..]）字体/字号/首行缩进/行距 ——
    body = p["body"]
    body_paras = [pp for pp in paras[2:] if pp.runs]
    ea_ok = sz_ok = ind_ok = ls_ok = True
    ind_meas, ls_meas = [], []
    for pp in body_paras:
        ea, sz = run_ea_and_size(pp.runs[0])
        if ea != body["font"]:
            ea_ok = False
        if sz is None or abs(sz - body["size_pt"]) > TOL_PT:
            sz_ok = False
        # 首行缩进
        fi = pp.paragraph_format.first_line_indent
        fi_pt = (fi.pt if fi is not None else 0.0)
        ind_meas.append(round(fi_pt, 1))
        if abs(fi_pt - body["first_line_indent_pt"]) > TOL_PT:
            ind_ok = False
        # 行距 + rule
        ls = pp.paragraph_format.line_spacing
        ls_pt = (ls.pt if ls is not None else 0.0)
        ls_meas.append(round(ls_pt, 1))
        rule = pp.paragraph_format.line_spacing_rule
        if rule != WD_LINE_SPACING.EXACTLY or abs(ls_pt - body["line_spacing_pt"]) > TOL_PT:
            ls_ok = False
        # 坑2：run.font.name 必须被显式设置（不为 None、不为默认继承）
        if pp.runs[0].font.name is None:
            ea_ok = False

    add("正文字体(eastAsia)", body["font"], body_paras[0].runs[0] and eastasia_of(body_paras[0].runs[0]), ea_ok)
    add("正文字号(pt)", body["size_pt"], sz, sz_ok)
    add("首行缩进(pt)", body["first_line_indent_pt"], "/".join(map(str, ind_meas)), ind_ok,
        note="坑：2字=2×正文字号→32pt")
    add("行距(pt,EXACTLY)", body["line_spacing_pt"], "/".join(map(str, ls_meas)), ls_ok,
        note="坑1/坑3：固定值行距单位磅；rule 须=EXACTLY 而非 MULTIPLE")

    return rows


def main():
    setname = "A"
    args = sys.argv[1:]
    if "--set" in args:
        setname = args[args.index("--set") + 1]
    if "--docx" not in args:
        print("[参数不足] 缺 --docx 待检文件路径（不提供时不做任何检查）；"
              "用法：python selfcheck.py --set A|B --docx <path.docx>。退出码 1。")
        sys.exit(1)
    docx_path = args[args.index("--docx") + 1]

    print("=== docx-format-guard 读回自检（套%s）===" % setname)
    print("docx: %s\n" % docx_path)
    rows = check(setname, docx_path)
    all_ok = True
    for item, expected, measured, ok, note in rows:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        line = "[%s] %s | 判据=%s | 实测=%s" % (tag, item, expected, measured)
        if note:
            line += "  (%s)" % note
        print(line)

    print("")
    if all_ok:
        print("门禁结论：五项读回断言全过 → 允许交付。")
        return 0
    # 门禁：不过即停并报“哪一项、实测多少、参数单写的多少”
    failed = [r for r in rows if not r[3]]
    print("门禁结论：存在未过项 → 即停，不交付。未过明细：")
    for item, expected, measured, ok, note in failed:
        print("  - 项=%s；参数单写=%s；实测=%s" % (item, expected, measured))
    return 1


if __name__ == "__main__":
    sys.exit(main())
