#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx-format-guard · 生成器
唯一取值来源：同目录 params.json（套 A 默认 / 套 B 变体）。
本脚本不写死任何字号、行距、边距——全部从参数单读。
用法：python gen_gongwen.py --set A|B --out <path.docx>
"""
import json, os, sys
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS = os.path.join(SKILL_DIR, "scripts", "params.json")


def set_run_font(run, name):
    """同时写 ascii/hAnsi 与 eastAsia，确保中文与西文字体一致（避免只写 ascii 导致中文丢字体）。"""
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = rpr.makeelement(qn('w:rFonts'), {})
        rpr.append(rfonts)
    rfonts.set(qn('w:ascii'), name)
    rfonts.set(qn('w:hAnsi'), name)
    rfonts.set(qn('w:eastAsia'), name)


def need_value(args, flag, usage):
    """取 --flag 的值；无值或缺参时中文报错退 1，不裸抛 IndexError。"""
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args) or args[i + 1].startswith("--"):
        print("[参数不足] %s 缺值。怎么办：按用法给出取值（%s）。退出码 1。" % (flag, usage))
        sys.exit(1)
    return args[i + 1]


def load(setname):
    with open(PARAMS, encoding='utf-8') as f:
        data = json.load(f)
    if setname not in data["sets"]:
        print("[参数单] 未知套别 '%s'，仅支持 A/B。怎么办：--set 只能传 A 或 B。退出码 1。" % setname)
        sys.exit(1)
    return data["sets"][setname]


ALIGN_MAP = {"center": WD_ALIGN_PARAGRAPH.CENTER, "left": WD_ALIGN_PARAGRAPH.LEFT,
             "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
RULE_MAP = {"EXACTLY": WD_LINE_SPACING.EXACTLY, "MULTIPLE": WD_LINE_SPACING.MULTIPLE,
            "AT_LEAST": WD_LINE_SPACING.AT_LEAST, "SINGLE": WD_LINE_SPACING.SINGLE}


def build(setname, out):
    p = load(setname)
    doc = Document()
    sec = doc.sections[0]

    # —— 页面与页边距（只从参数单读）——
    pg = p["page"]
    sec.page_width = Cm(pg["w_cm"])
    sec.page_height = Cm(pg["h_cm"])
    sec.top_margin = Cm(pg["margin_top_cm"])
    sec.bottom_margin = Cm(pg["margin_bottom_cm"])
    sec.left_margin = Cm(pg["margin_left_cm"])
    sec.right_margin = Cm(pg["margin_right_cm"])

    # —— 文档标题（对齐/加粗均从参数单读，不硬编码）——
    t = doc.add_paragraph()
    align_key = p["title"].get("align", "center")
    if align_key not in ALIGN_MAP:
        print("[参数单] 未知对齐方式 '%s'，仅支持 %s。怎么办：修正 params.json 的 title.align。退出码 1。"
              % (align_key, "/".join(ALIGN_MAP)))
        sys.exit(1)
    t.alignment = ALIGN_MAP[align_key]
    rt = t.add_run("公文格式样例标题（套%s）" % setname)
    set_run_font(rt, p["title"]["font"])
    rt.font.size = Pt(p["title"]["size_pt"])
    rt.font.bold = bool(p["title"].get("bold", False))

    # —— 一级标题 ——
    h = doc.add_paragraph()
    rh = h.add_run("一、一级标题样例")
    set_run_font(rh, p["heading1"]["font"])
    rh.font.size = Pt(p["heading1"]["size_pt"])

    # —— 正文（行距规则 + 首行缩进均从参数单读，不硬编码）——
    body = p["body"]
    rule_key = p.get("line_spacing_rule", "EXACTLY")
    if rule_key not in RULE_MAP:
        print("[参数单] 未知行距规则 '%s'，仅支持 %s。怎么办：修正 params.json 的 line_spacing_rule。退出码 1。"
              % (rule_key, "/".join(RULE_MAP)))
        sys.exit(1)
    for i in range(2):
        para = doc.add_paragraph()
        pf = para.paragraph_format
        pf.first_line_indent = Pt(body["first_line_indent_pt"])
        # 坑1/坑3：固定值行距单位磅；rule 从参数单取（EXACTLY/MULTIPLE...），值用 Length(Pt)
        pf.line_spacing_rule = RULE_MAP[rule_key]
        pf.line_spacing = Pt(body["line_spacing_pt"])
        rb = para.add_run(
            "这是正文样例第%d段。公文正文采用仿宋_GB2312，首行缩进二字符，"
            "行距固定值二十八磅，用以验证读回自检能否如实取回字体、字号、行距与缩进。" % (i + 1)
        )
        # 坑2：插入段落不继承样式，必须显式设置 run.font，否则回读为默认字体
        set_run_font(rb, body["font"])
        rb.font.size = Pt(body["size_pt"])

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    doc.save(out)
    print("GENERATED set=%s -> %s" % (setname, out))


if __name__ == "__main__":
    usage = "python gen_gongwen.py --set A|B --out <path.docx>"
    args = sys.argv[1:]
    setname = need_value(args, "--set", usage) or "A"
    out = need_value(args, "--out", usage)
    if out is None:
        print("[参数不足] 缺 --out 输出路径（不提供时不落任何文件）；"
              "用法：%s。退出码 1。" % usage)
        sys.exit(1)
    build(setname, out)
