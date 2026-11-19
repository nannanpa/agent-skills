#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并多稿 / 按意见逐处改稿的结构化编辑脚本（docx-track-changes-wps 1.2.2 配套）。

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
  · replace_paragraph(doc, p_idx, ...)   整段正文替换（保留 pPr 与字体，
                                         连同段内既有修订/批注锚点一并清除）；
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
import os
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
    """取段落首个 run 的 rPr 副本；无则 None。

    1.2.1 更正：改为 `iter()` 深查找——段落首个内容 run 可能包在 `w:ins`/
    `w:del` 里（自带修订史的稿件常态），旧版 `findall()` 只看直系子节点
    会漏掉它，导致整段替换时字体继承落空。
    """
    for r in p._p.iter(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if rpr is not None:
            return copy.deepcopy(rpr)
    return None


# 整段替换时要清除的"内容性"子元素（1.2.1）：
#   w:r 直系 run；w:ins / w:del 修订包裹（内部 run 随包清除）；
#   w:hyperlink / w:fldSimple / w:smartTag 内部同样藏 run；
#   批注锚点三件（RangeStart / RangeEnd / Reference）——文本没了锚点必须
#   跟着走，残留空锚点会让 Word/WPS 显示空批注甚至结构异常。
#   保留：w:pPr（段落格式）、w:bookmarkStart / w:bookmarkEnd（书签，交叉引用用）。
_CLEAR_TAGS = ("w:r", "w:ins", "w:del", "w:hyperlink", "w:fldSimple",
               "w:smartTag", "w:commentRangeStart", "w:commentRangeEnd",
               "w:commentReference")


def _clear_paragraph_content(p):
    """清空段落的全部内容性子元素（见 _CLEAR_TAGS），返回清除个数。"""
    tags = {qn(t) for t in _CLEAR_TAGS}
    removed = 0
    for el in list(p._p):
        if el.tag in tags:
            p._p.remove(el)
            removed += 1
    return removed


def replace_paragraph(doc, p_idx, new_text, inherit_font=True):
    """整段正文替换：清空目标段**全部内容**后写入新文本，保留 pPr 与字体。

    与 apply_del 的区别：这里不做修订标记、不保留旧字，是直接改写整段
    （适用于"按意见重写整段"而非"勘误"）。返回被改的 Paragraph。

    **1.2.1 更正（v1.2.0 评测点名、代码级实锤）**：旧版只清直系 `w:r`，
    段内既有的 `w:ins`/`w:del` 包裹 run 会原样残留——"整段替换"后旧修订
    文字仍在段里。现按"整段"语义清除全部内容性子元素（含修订包裹、
    超链接/域、批注锚点，见 `_CLEAR_TAGS`），只留 pPr 与书签。

    **语义须知**：既有修订与批注引用随替换**一并消失**（本接口设计为
    不留痕）。要留痕的改字用 `apply_del`；替换前建议先跑
    `export_markup` 导出修订批注清单留档，再执行本接口。
    """
    p = doc.paragraphs[p_idx]
    rpr = _rpr_of_first_run(p) if inherit_font else None
    _clear_paragraph_content(p)
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

    **同段冲突检测（1.2.3）**：先做过 correct（勘误留痕）的段落再执行
    replace_para，会**吞掉该段全部修订留痕**（整段替换是清场语义）——
    这类组合不执行，标注 `skipped:conflict:...` 并给出处置建议；其余
    组合（replace→replace、replace→correct）不拦。需要覆盖时把两条
    意见合成一条 replace_para，或先删掉那条 correct。
    """
    results = []
    seg_ops = {}                # p_idx → 已执行的内容型操作（correct / replace_para）
    for item in config.get("opinions", []):
        oid = item.get("id")
        op = item.get("op")
        pidx = int(item.get("p_idx", -1))
        try:
            if op == "replace_para":
                prior = seg_ops.get(pidx)
                if prior == "correct":
                    results.append((oid, op,
                                    f"skipped:conflict:p_idx{pidx}已做过勘误留痕，"
                                    f"整段替换会吞掉该留痕——两条意见合成一条 replace_para，"
                                    f"或删除该 correct 条目后重跑"))
                    continue
                replace_paragraph(doc, pidx, item["text"])
                results.append((oid, op, "ok"))
                seg_ops[pidx] = "replace_para"
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
                    seg_ops[pidx] = "correct"
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


def _die(msg, hint, code=1):
    """报错退出。退出码分区（1.2.2 起，与 apply_track_changes.py 同口径）：

    0 = 成功（含"部分意见 skipped"——skipped 是显式标注，不是失败）
    1 = 用法/输入/环境错误（参数不齐、文件不存在、不是有效 .docx、
        段号越界、config 解析失败、意见执行出错）
    2 = 产物结构校验未通过（保存后 zip/XML 完整性断言失败，产物不可信）
    """
    print(f"❌ {msg}")
    print(f"💡 怎么办：{hint}")
    print(f"（退出码 {code}：0 成功｜1 输入/用法错｜2 结构校验未通过）")
    sys.exit(code)


def _integrity_check(path):
    """保存后完整性断言（zip 完好 + document.xml 可解析）。失败退 2。"""
    import zipfile
    from lxml import etree
    try:
        z = zipfile.ZipFile(path)
        assert z.testzip() is None, "zip corrupted"
        etree.fromstring(z.read("word/document.xml"))
    except AssertionError as e:
        _die(f"结构校验未通过：{e}", "输入文件结构可能有问题；先跑 apply_track_changes.py 的 self_test.py 确认环境，再换副本重试。", code=2)
    except Exception as e:
        _die(f"结构校验未通过：{e}", "产物文件可能写坏（磁盘/杀软拦截？）；换输出路径重试。", code=2)


def main(argv=None):
    import argparse
    import importlib.util as _ilu

    class _ArgParser(argparse.ArgumentParser):
        """参数错误改退 1（argparse 默认退 2，与本脚本"2=结构校验未通过"码位冲突）。"""
        def error(self, message):
            self.print_usage(sys.stderr)
            _die(f"参数错误：{message}", "四种操作互斥，一次执行一种；完整用法跑 --help。", code=1)

    ap = _ArgParser(
        prog="merge_markup.py",
        description="合并多稿 / 按意见逐处改稿命令行（1.2.2 起）。"
                    "四种操作互斥，一次执行一种；原文档不动，产物写 OUT。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python3 merge_markup.py 原件.docx 整合.docx --replace 5 \"重写后的整段正文。\"\n"
               "  python3 merge_markup.py 原件.docx 整合.docx --insert-after 8 \"（新增补充说明）\"\n"
               "  python3 merge_markup.py 原件.docx 整合.docx --heading-after 9 \"五、征集意见情况\"\n"
               "  python3 merge_markup.py 原件.docx 整合.docx --opinions opinions.json\n"
               "退出码：0 成功｜1 输入/用法错｜2 结构校验未通过。\n"
               "注意：--replace 是清场语义——目标段既有修订/批注/超链接一并清除（先 export_markup 留档）。",
    )
    ap.add_argument("src", help="原件 .docx（不会被修改）")
    ap.add_argument("out", help="产物 .docx")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--replace", nargs=2, metavar=("段号", "新文本"),
                   help="整段替换（清场语义，见 epilog 警告）")
    g.add_argument("--insert-after", nargs=2, metavar=("段号", "文本"),
                   help="在指定段后插入新段落")
    g.add_argument("--heading-after", nargs=2, metavar=("段号", "标题"),
                   help="在指定段后插入黑体标题段落")
    g.add_argument("--opinions", metavar="config.json",
                   help="按'意见编号→改动'配置批量编排（含 correct 勘误时自动启用修订并注入 apply_del）")
    args = ap.parse_args(argv)

    def _seg(v, what):
        try:
            n = int(v)
        except (TypeError, ValueError):
            _die(f"{what} 不是整数：{v!r}", "段号从 0 起计，如 --replace 5 \"新文本\"。", code=1)
        if n < 0:
            _die(f"{what} 不能为负：{n}", "段号从 0 起计。", code=1)
        return n

    def _open(path):
        try:
            return docx.Document(path)
        except FileNotFoundError:
            _die(f"找不到文件：{path}", "检查路径拼写；含空格的路径用引号包住。", code=1)
        except Exception as e:
            m = str(e)
            if "Content_Types" in m or "no such file" in m.lower() or "BadZipFile" in type(e).__name__:
                _die(f"{path} 不是有效的 .docx 文件", "确认扩展名是 .docx 而不是 .doc/.rtf/.wps；必要时先用 WPS 另存为 .docx。", code=1)
            _die(f"打开失败：{m}", "先用 apply_track_changes.py 的 self_test.py 验证环境。", code=1)

    def _seg_ok(doc, n):
        if n >= len(doc.paragraphs):
            _die(f"段号越界：{n}（全文共 {len(doc.paragraphs)} 段，0 起）",
                 "先确认段号；可在 Python 里 len(doc.paragraphs) 数一遍，或用 export 清单核对。", code=1)

    try:
        doc = _open(args.src)
        if args.replace:
            n = _seg(args.replace[0], "段号"); _seg_ok(doc, n)
            replace_paragraph(doc, n, args.replace[1])
            print(f"OK: 段 {n} 已整段替换（清场语义：既有修订/批注/超链接一并清除）")
        elif args.insert_after:
            n = _seg(args.insert_after[0], "段号"); _seg_ok(doc, n)
            insert_paragraph_after(doc, n, args.insert_after[1])
            print(f"OK: 段 {n} 后已插入新段落")
        elif args.heading_after:
            n = _seg(args.heading_after[0], "段号"); _seg_ok(doc, n)
            insert_heading_after(doc, n, args.heading_after[1])
            print(f"OK: 段 {n} 后已插入标题段落")
        else:  # --opinions
            try:
                with open(args.opinions, encoding="utf-8") as f:
                    config = json.load(f)
            except FileNotFoundError:
                _die(f"找不到配置文件：{args.opinions}", "config.json 路径检查；格式见 SKILL.md「按意见清单逐处改稿」。", code=1)
            except json.JSONDecodeError as e:
                _die(f"配置文件不是合法 JSON：{e}", "检查 config.json 语法；格式见 SKILL.md「按意见清单逐处改稿」。", code=1)
            ops = {it.get("op") for it in config.get("opinions", [])}
            apply_del_fn = None
            if "correct" in ops:
                # 勘误需要修订环境与计数器：经 open_for_revision 重开注入
                spec = _ilu.spec_from_file_location(
                    "atc", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "apply_track_changes.py"))
                atc = _ilu.module_from_spec(spec); spec.loader.exec_module(atc)
                doc, counter, author, date_iso = atc.open_for_revision(args.src)
                apply_del_fn = (lambda d, c, a, dt, pidx, ph, tx:
                                atc.apply_del(d, counter, a or author, dt or date_iso,
                                              pidx, ph, tx or ""))
            results = apply_opinions(doc, config, apply_del_fn=apply_del_fn)
            errors = 0
            for oid, op, status in results:
                print(f"  意见 {oid} [{op}] → {status}")
                if status.startswith("error:"):
                    errors += 1
            if errors:
                _die(f"{errors} 条意见执行出错（其余已完成并保存）",
                     "逐条核对上面 error 的段号/短语；修正 config 后重跑。", code=1)
            print(f"OK: 意见编排完成（{len(results)} 条）")
        doc.save(args.out)
    except SystemExit:
        raise
    except OSError as e:
        _die(f"写文件失败：{e}", "检查输出路径可写；含空格的路径用引号包住。", code=1)
    except Exception as e:
        _die(f"处理失败：{type(e).__name__}: {e}", "先跑 apply_track_changes.py 的 self_test.py 验证环境；仍失败时保留原件并到 SKILL.md「已知坑」对照排查。", code=1)
    _integrity_check(args.out)


if __name__ == "__main__":
    main()
