#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并多稿 / 按意见逐处改稿的结构化编辑脚本（docx-track-changes-wps 1.2.0 配套）。

与 apply_track_changes.py 的关系：**并行机制，不互相替代**。
  · apply_track_changes.py —— 写入真正的"修订模式"（w:ins / w:del），记录"改了什么"；
  · 本脚本 —— 合并多稿、底纹着色标注来源、按外部意见清单批量落地改稿，
    记录"这处改动来自谁 / 按哪条意见改"，成品同样在 WPS 中干净打开。

来源：2026-11-19 由和欣月端从其历史任务（2026-06-05 合并两稿三色标注、
2026-06-09 按 9 条意见逐处改稿）中提炼原料，脱敏后回传，马斌侧整合。
按 v1.2.1 判据，同一会话目录多文件只算一个场合，共 2 个独立场合。

提供接口：
  · shade_run(run, fill)                 给 run 加 w:shd 底纹（底纹着色）；
  · shaded_run(paragraph, text, ...)     造一个带底纹的 run（按来源分色）；
  · add_legend_page(doc, items, ...)     生成"整合版本 · 标注说明"图例页；
  · replace_paragraph(doc, p_idx, ...)   整段正文替换（保留 pPr 与字体）；
  · insert_paragraph_after(doc, p_idx, ...) / insert_heading_after(...)  段落/标题级插入；
  · apply_opinions(doc, config, ...)     按"意见编号→改动"配置逐处编排落地；
  · merge_by_paragraph(base, incoming)   按段比对拼整合正文（返回结构化清单，
                                         比对逻辑留外部——见 SKILL.md）。

WPS 安全约束（与修订脚本同源）：不碰 body 级 sectPr；w:t 保留 xml:space；
底纹 w:shd 只加在 run 的 w:rPr 内、val=clear、color=auto（实测三色 CCFFCC/
CCE5FF/FFFF99 在 WPS 正常显示）；字体继承锚点 run，不凭空造不存在的字体。
"""
import copy
import json
import sys

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph

# 三色底纹（来自原料 A，实测在 WPS 显示正常）
FILL_GREEN = "CCFFCC"   # 校领导甲版本修改/新增
FILL_BLUE = "CCE5FF"    # 校领导乙版本修改/建议
FILL_YELLOW = "FFFF99"  # 两版本均涉及但表述有差异
LEGEND_ITEMS = [
    (FILL_GREEN, "绿色背景：版本甲中的修改/新增内容"),
    (FILL_BLUE, "蓝色背景：版本乙中的修改/建议内容"),
    (FILL_YELLOW, "黄色背景：两版本均涉及但表述有差异"),
]


def _set_font(run, size=16, name="仿宋_GB2312", bold=False, italic=False,
              color=None):
    """给 run 统一设置中英文字体与字号（公文默认仿宋_GB2312 三号=16pt）。"""
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = name
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), name)
    if color is not None:
        run.font.color.rgb = color
    return run


def shade_run(run, fill_color):
    """给一个 python-docx run 加 w:shd 底纹。返回该 run。

    w:shd 放在 w:rPr 内，val=clear / color=auto / fill=颜色。
    """
    rpr = run._r.get_or_add_rPr()
    shd = rpr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        rpr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_color)
    return run


def shaded_run(paragraph, text, fill_color, size=16, name="仿宋_GB2312",
               italic=False, color=None):
    """在段落末尾追加一个带底纹的 run（按来源分色的便捷构造器）。"""
    r = paragraph.add_run(text)
    _set_font(r, size=size, name=name, italic=italic, color=color)
    shade_run(r, fill_color)
    return r


def add_legend_page(doc, items=None, title="【整合版本 · 标注说明】",
                    note="紫色斜体：备注/说明（原文保留）"):
    """在文末新增一页"标注说明"图例（色块→含义表 + 备注写法）。"""
    items = items if items is not None else LEGEND_ITEMS
    doc.add_page_break()
    p0 = doc.add_paragraph()
    p0.alignment = 0  # WD_ALIGN_PARAGRAPH.LEFT
    _set_font(p0.add_run(title), size=14, bold=True)
    for bg, desc in items:
        lp = doc.add_paragraph()
        lp.paragraph_format.first_line_indent = Pt(16)
        lp.paragraph_format.space_after = Pt(0)
        block = lp.add_run("  ■ ")
        _set_font(block, size=13)
        shade_run(block, bg)
        _set_font(lp.add_run(desc), size=13)
    lp2 = doc.add_paragraph()
    lp2.paragraph_format.first_line_indent = Pt(16)
    lp2.paragraph_format.space_after = Pt(6)
    _set_font(lp2.add_run("  ■ " + note), size=13, italic=True,
              color=RGBColor(0x80, 0x00, 0x80))
    return doc


def _clone_ppr(src_p, dst_p):
    """把源段落的 pPr（段落格式）复制给目标段落，保持排版一致。"""
    src_ppr = src_p._p.find(qn("w:pPr"))
    if src_ppr is None:
        return
    dst_ppr = dst_p._p.find(qn("w:pPr"))
    if dst_ppr is not None:
        dst_p._p.remove(dst_ppr)
    dst_p._p.insert(0, copy.deepcopy(src_ppr))


def _rpr_of_first_run(p):
    """取段落首个 run 的 rPr 副本；无则 None。"""
    for r in p._p.findall(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if rpr is not None:
            return copy.deepcopy(rpr)
    return None


def replace_paragraph(doc, p_idx, new_text, inherit_font=True):
    """整段正文替换：清空目标段的 run，写入新文本，保留 pPr 与原字体。

    与 apply_del 的区别：这里不做修订标记、不保留旧字，是直接改写整段
    （适用于"按意见重写整段"而非"勘误"）。返回被改的 Paragraph。
    """
    p = doc.paragraphs[p_idx]
    rpr = _rpr_of_first_run(p) if inherit_font else None
    for r in list(p._p.findall(qn("w:r"))):
        p._p.remove(r)
    r = p.add_run(new_text)
    if rpr is not None:
        r._r.insert(0, rpr)
    return p


def _insert_para_element(ref_para, new_text, font_name="仿宋_GB2312",
                         size=16, heading=False):
    """在 ref_para 对应 XML 元素之后插入一个新段落元素，返回 Paragraph。"""
    body = ref_para._p.getparent()
    new_p = OxmlElement("w:p")
    # 复制锚点段落的 pPr 保持对齐/缩进一致
    src_ppr = ref_para._p.find(qn("w:pPr"))
    if src_ppr is not None:
        new_p.append(copy.deepcopy(src_ppr))
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    rfonts = OxmlElement("w:rFonts")
    face = "黑体" if heading else font_name
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), face)
    rpr.append(rfonts)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    rpr.append(sz)
    r.append(rpr)
    t = OxmlElement("w:t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = new_text
    r.append(t)
    new_p.append(r)
    ref_para._p.addnext(new_p)
    return Paragraph(new_p, ref_para._parent)


def insert_paragraph_after(doc, p_idx, text, size=16, font_name="仿宋_GB2312"):
    """在指定段后插入一个新段落（段内/新段级，非段内字符插入）。"""
    return _insert_para_element(doc.paragraphs[p_idx], text, font_name, size)


def insert_heading_after(doc, p_idx, text, size=16):
    """在指定段后插入一个黑体标题段落。"""
    return _insert_para_element(doc.paragraphs[p_idx], text, size=16, heading=True)


def apply_opinions(doc, config, apply_del_fn=None):
    """按"意见编号→改动"配置逐处落地改稿（批量编排层）。

    config 为 dict，形如：
      {
        "opinions": [
          {"id": 1, "op": "replace_para", "p_idx": 5, "text": "..."},
          {"id": 2, "op": "insert_after", "p_idx": 8, "text": "..."},
          {"id": 3, "op": "heading_after", "p_idx": 9, "text": "五、..."},
          {"id": 4, "op": "correct", "p_idx": 12, "phrase": "发辉", "text": "发挥"}
        ]
      }
    op 取值：replace_para / insert_after / heading_after / correct。
    correct 需要 apply_track_changes.apply_del，可经 apply_del_fn 注入；
    未注入时跳过 correct 并在返回里标注（不静默）。
    """
    results = []
    for item in config.get("opinions", []):
        oid = item.get("id")
        op = item.get("op")
        pidx = int(item.get("p_idx", -1))
        try:
            if op == "replace_para":
                replace_paragraph(doc, pidx, item["text"])
                results.append((oid, op, "ok"))
            elif op == "insert_after":
                insert_paragraph_after(doc, pidx, item["text"])
                results.append((oid, op, "ok"))
            elif op == "heading_after":
                insert_heading_after(doc, pidx, item["text"])
                results.append((oid, op, "ok"))
            elif op == "correct":
                if apply_del_fn is None:
                    results.append((oid, op, "skipped:no_apply_del"))
                else:
                    apply_del_fn(doc, item.get("counter"), item.get("author"),
                                 item.get("date"), pidx, item["phrase"],
                                 item.get("text", ""))
                    results.append((oid, op, "ok"))
            else:
                results.append((oid, op, f"skipped:unknown_op({op})"))
        except Exception as e:
            results.append((oid, op, f"error:{type(e).__name__}:{e}"))
    return results


def merge_by_paragraph(base_paras, incoming_paras):
    """按段比对本稿与另一稿，返回结构化整合清单（不直接改文档）。

    原料 A-3 的原始任务是"两位领导整份稿件按段比对后拼整合正文"。
    **比对取舍是内容判断，脚本不代判**：本函数只按段落 index 对齐，
    标出"仅 base 有 / 仅 incoming 有 / 两者都有"，供人工决定取哪版。
    返回 list of dict：{idx, base, incoming, status}。
    """
    out = []
    n = max(len(base_paras), len(incoming_paras))
    for i in range(n):
        b = base_paras[i] if i < len(base_paras) else None
        v = incoming_paras[i] if i < len(incoming_paras) else None
        if b is not None and v is not None:
            status = "both" if b == v else "differ"
        elif b is not None:
            status = "base_only"
        else:
            status = "incoming_only"
        out.append({"idx": i, "base": b, "incoming": v, "status": status})
    return out


if __name__ == "__main__":
    print(__doc__)
    sys.exit(0 if "--help" in sys.argv or len(sys.argv) == 1 else 0)
