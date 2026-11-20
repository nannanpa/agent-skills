#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx-format-guard · 读回自检
生成 docx 后回读，对七项做断言：字体 / 字号 / 行距 / 页边距 / 首行缩进 / 页面尺寸 / 标题加粗。
另含三个坑的显式校验（见 LESSONS.md）。
启动时先做参数一致性校验：params.json 与 references/参数单.md 关键数值须一致。

门禁（写死）：七项读回断言全过才允许交付；任一项不过即停并报
“哪一项、实测多少、参数单写的多少”。

用法：python selfcheck.py --set A|B --docx <path.docx>
退出码：全过 0；任一不过或参数错 1（即停）。
"""
import json, os, sys, re
from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS = os.path.join(SKILL_DIR, "scripts", "params.json")
PARAM_MD = os.path.join(SKILL_DIR, "references", "参数单.md")

TOL_CM = 0.03      # 页边距/页面尺寸容差
TOL_PT = 0.5       # 字号/缩进/行距容差


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


def _grab(pattern, text, label):
    m = re.search(pattern, text)
    if not m:
        print("[一致性校验] 参数单.md 未能解析出“%s”。怎么办：检查 references/参数单.md 表格格式是否被改动。退出码 1。" % label)
        sys.exit(1)
    return m.group(1)


def validate_param_consistency():
    """启动校验：params.json 与 references/参数单.md 关键数值须一致，漂移即停退 1。"""
    with open(PARAMS, encoding='utf-8') as f:
        data = json.load(f)
    with open(PARAM_MD, encoding='utf-8') as f:
        md = f.read()
    if "## 套 A" not in md or "## 套 B" not in md:
        print("[一致性校验] 参数单.md 缺少“## 套 A / ## 套 B”分节。怎么办：恢复参数单.md 分节结构。退出码 1。")
        sys.exit(1)
    sec_a = md.split("## 套 A", 1)[1].split("## 套 B", 1)[0]
    sec_b = md.split("## 套 B", 1)[1]
    sets = data["sets"]

    a = {
        "title_font": _grab(r"文档标题[^\n]*?\|\s*([^\s|]+)\s+\d", sec_a, "套A标题字体"),
        "title_size": _grab(r"文档标题[^\n]*?(\d+(?:\.\d+)?)\s*pt", sec_a, "套A标题字号"),
        "body_size": _grab(r"\|\s*正文\s*\|[^\n]*?(\d+(?:\.\d+)?)\s*pt", sec_a, "套A正文字号"),
        "indent": _grab(r"首行缩进[^\n]*?=\s*(\d+(?:\.\d+)?)\s*pt", sec_a, "套A首行缩进"),
        "line_spacing": _grab(r"行距[^\n]*?固定值\s*(\d+(?:\.\d+)?)\s*磅", sec_a, "套A行距"),
    }
    b = {
        "title_font": _grab(r"文档标题[^\n]*?\|\s*\*\*([^\s*]+)\s*\d", sec_b, "套B标题字体"),
        "title_size": _grab(r"文档标题[^\n]*?(\d+(?:\.\d+)?)\s*号", sec_b, "套B标题字号"),
        "line_spacing": _grab(r"行距[^\n]*?固定值\s*(\d+(?:\.\d+)?)\s*磅", sec_b, "套B行距"),
    }
    ma = re.search(r"页边距[^\n]*?上([\d.]+)／下([\d.]+)／左([\d.]+)／右([\d.]+)", sec_a)
    mb = re.search(r"页边距[^\n]*?上([\d.]+)／下([\d.]+)／左([\d.]+)／右([\d.]+)", sec_b)
    if not ma or not mb:
        print("[一致性校验] 参数单.md 未能解析出页边距。怎么办：检查“上／下／左／右”分隔符是否被改动。退出码 1。")
        sys.exit(1)

    def eq(x, y):
        try:
            return abs(float(x) - float(y)) < 1e-6
        except (TypeError, ValueError):
            return str(x) == str(y)

    checks = [
        ("套A标题字号", a["title_size"], sets["A"]["title"]["size_pt"]),
        ("套A正文字号", a["body_size"], sets["A"]["body"]["size_pt"]),
        ("套A首行缩进", a["indent"], sets["A"]["body"]["first_line_indent_pt"]),
        ("套A行距", a["line_spacing"], sets["A"]["body"]["line_spacing_pt"]),
        ("套A标题字体", a["title_font"], sets["A"]["title"]["font"]),
        ("套A边距上", ma.group(1), sets["A"]["page"]["margin_top_cm"]),
        ("套A边距下", ma.group(2), sets["A"]["page"]["margin_bottom_cm"]),
        ("套A边距左", ma.group(3), sets["A"]["page"]["margin_left_cm"]),
        ("套A边距右", ma.group(4), sets["A"]["page"]["margin_right_cm"]),
        ("套B标题字号", b["title_size"], sets["B"]["title"]["size_pt"]),
        ("套B标题字体", b["title_font"], sets["B"]["title"]["font"]),
        ("套B行距", b["line_spacing"], sets["B"]["body"]["line_spacing_pt"]),
        ("套B边距上", mb.group(1), sets["B"]["page"]["margin_top_cm"]),
        ("套B边距下", mb.group(2), sets["B"]["page"]["margin_bottom_cm"]),
        ("套B边距左", mb.group(3), sets["B"]["page"]["margin_left_cm"]),
        ("套B边距右", mb.group(4), sets["B"]["page"]["margin_right_cm"]),
    ]
    bad = ["%s：参数单.md=%s，params.json=%s" % (name, mdv, jv)
           for name, mdv, jv in checks if not eq(mdv, jv)]
    if bad:
        print("[一致性校验] params.json 与 references/参数单.md 关键数值不一致，即停不交付：")
        for line in bad:
            print("  - " + line)
        print("怎么办：以参数单.md为准把两份数值对齐（改 params.json 或参数单.md），再重跑自检。退出码 1。")
        sys.exit(1)
    print("[一致性校验] 两份参数关键数值一致（套A 标题22/正文16/行距28/边距3.7-3.5-2.8-2.6/缩进32；"
          "套B 黑体22/行距30/边距3.7-3.5-2.7-2.7）。")


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

    nonempty = [pp for pp in paras if pp.runs]
    if len(nonempty) < 3:
        print("[文档结构] 未找到正文段落（需“标题＋一级标题＋至少一段正文”，实测有效段落 %d 段），"
              "无法自检。怎么办：用 gen_gongwen.py 重新生成，或补全段落。退出码 1。" % len(nonempty))
        sys.exit(1)
    title_para, h1_para = nonempty[0], nonempty[1]
    body_paras = nonempty[2:]

    rows = []  # (项, 判据值, 实测值, 是否通过, 备注)

    def add(item, expected, measured, ok, note=""):
        rows.append((item, expected, measured, ok, note))

    # —— 1) 页面尺寸（D5 新增）——
    pg = p["page"]
    w_meas, h_meas = round(sec.page_width.cm, 2), round(sec.page_height.cm, 2)
    wh_expected = (pg["w_cm"], pg["h_cm"])
    wh_ok = abs(w_meas - wh_expected[0]) <= TOL_CM and abs(h_meas - wh_expected[1]) <= TOL_CM
    add("页面尺寸(cm) 宽×高", "%.1f×%.1f" % wh_expected, "%.1f×%.1f" % (w_meas, h_meas), wh_ok,
        note="A4 21.0×29.7")

    # —— 2) 页边距 ——
    m_expected = (pg["margin_top_cm"], pg["margin_bottom_cm"],
                  pg["margin_left_cm"], pg["margin_right_cm"])
    m_measured = (round(sec.top_margin.cm, 2), round(sec.bottom_margin.cm, 2),
                  round(sec.left_margin.cm, 2), round(sec.right_margin.cm, 2))
    m_ok = all(abs(a - b) <= TOL_CM for a, b in zip(m_expected, m_measured))
    add("页边距(cm) 上/下/左/右", "/".join(map(str, m_expected)),
        "/".join(map(str, m_measured)), m_ok)

    # —— 3) 标题（para[0]）字体/字号/加粗（D5 加粗）——
    t = p["title"]
    ea, sz = run_ea_and_size(title_para.runs[0])
    add("标题字体(eastAsia)", t["font"], ea, ea == t["font"])
    add("标题字号(pt)", t["size_pt"], sz, sz is not None and abs(sz - t["size_pt"]) <= TOL_PT)
    bold_expected = bool(t.get("bold", True))
    bold_measured = (title_para.runs[0].font.bold is True)
    add("标题加粗", bold_expected, bold_measured, bold_measured is bold_expected)

    # —— 4) 一级标题（para[1]）字体/字号 ——
    h = p["heading1"]
    ea, sz = run_ea_and_size(h1_para.runs[0])
    add("一级标题字体(eastAsia)", h["font"], ea, ea == h["font"])
    add("一级标题字号(pt)", h["size_pt"], sz, sz is not None and abs(sz - h["size_pt"]) <= TOL_PT)

    # —— 5) 正文字体/字号/首行缩进/行距 ——
    body = p["body"]
    ea_ok = sz_ok = ind_ok = ls_ok = True
    ind_meas, ls_meas, sz_meas = [], [], []
    for pp in body_paras:
        ea, sz = run_ea_and_size(pp.runs[0])
        sz_meas.append(round(sz, 1) if sz is not None else 0.0)
        if ea != body["font"]:
            ea_ok = False
        if sz is None or abs(sz - body["size_pt"]) > TOL_PT:
            sz_ok = False
        fi = pp.paragraph_format.first_line_indent
        fi_pt = (fi.pt if fi is not None else 0.0)
        ind_meas.append(round(fi_pt, 1))
        if abs(fi_pt - body["first_line_indent_pt"]) > TOL_PT:
            ind_ok = False
        ls = pp.paragraph_format.line_spacing
        ls_pt = (ls.pt if ls is not None else 0.0)
        ls_meas.append(round(ls_pt, 1))
        rule = pp.paragraph_format.line_spacing_rule
        if rule != WD_LINE_SPACING.EXACTLY or abs(ls_pt - body["line_spacing_pt"]) > TOL_PT:
            ls_ok = False
        # 坑2：run.font.name 必须被显式设置（不为 None、不为默认继承）
        if pp.runs[0].font.name is None:
            ea_ok = False

    add("正文字体(eastAsia)", body["font"], eastasia_of(body_paras[0].runs[0]), ea_ok)
    add("正文字号(pt)", body["size_pt"], "/".join(map(str, sz_meas)), sz_ok,
        note="逐段全量实测（非末段冒充实测）")
    add("首行缩进(pt)", body["first_line_indent_pt"], "/".join(map(str, ind_meas)), ind_ok,
        note="坑：2字=2×正文字号→32pt")
    add("行距(pt,EXACTLY)", body["line_spacing_pt"], "/".join(map(str, ls_meas)), ls_ok,
        note="坑1/坑3：固定值行距单位磅；rule 须=EXACTLY 而非 MULTIPLE")

    return rows


def main():
    args = sys.argv[1:]
    usage = "python selfcheck.py --set A|B --docx <path.docx>"
    setname = need_value(args, "--set", usage) or "A"
    docx_path = need_value(args, "--docx", usage)
    if docx_path is None:
        print("[参数不足] 缺 --docx 待检文件路径（不提供时不做任何检查）；用法：%s。退出码 1。" % usage)
        sys.exit(1)

    validate_param_consistency()

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
        print("门禁结论：七项读回断言全过 → 允许交付。")
        return 0
    failed = [r for r in rows if not r[3]]
    print("门禁结论：存在未过项 → 即停，不交付。未过明细：")
    for item, expected, measured, ok, note in failed:
        print("  - 项=%s；参数单写=%s；实测=%s" % (item, expected, measured))
    return 1


if __name__ == "__main__":
    sys.exit(main())
