# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""docx-track-changes-wps 自检脚本（跨平台，macOS/Windows 通用）。

五个场景：
A. 基础插入 + settings.xml 结构断言；
B. 撞号回归：文档自带修订史（预置 w:ins id=10001）时，新插入不得与既有 id 重复
   （Windows 侧 2026-10-14 实测复现过的缺陷）。
C. 勘误：w:del + w:delText + 可选 w:ins 替换（1.1.0）。
D. 段内字符偏移插入（1.1.0）。
E. 格式继承（1.1.0）：插入内容必须带锚点 run 的 w:rPr，否则文字掉回文档默认
   字体——与人工在 Word 里输入的观感不一致（真实公文实测发现）。
F. 批注（1.1.0）与导出清单。
G. 合并多稿（1.2.0）：w:shd 三色底纹、图例页、整段替换、段落/标题插入、
   按意见清单批量编排（逐条返回状态不静默）、两稿按段对齐。
G6 整段替换回归（1.2.1）：目标段自带既有 w:ins 修订时，replace_paragraph
   必须连修订包裹一并清掉——1.2.0 只清直系 w:r 致旧修订文字残留
   （v1.2.0 评测点名、代码级实锤）。
G7 merge_markup 命令行（1.2.2）：--replace/--opinions（含 correct 自动注入
   apply_del 并启用修订）实跑，退出码 0/1 分区实测。
跑通 = 全部断言通过。Windows WPS 首次使用前，另需人工完成 SKILL.md
"适用环境与未验证声明"里的三步验收（打开/显示/接受拒绝修订）。
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from lxml import etree
from apply_track_changes import (open_for_revision, apply, apply_del,
                                 split_insert, verify)
from add_comment import add_comment, save_with_comments
from export_markup import export


def _styled_run(doc, text, font="仿宋", pt=16, bold=True):
    """造一个带明确字符格式的段落（模拟公文正文：仿宋三号加粗等）。"""
    p = doc.add_paragraph(text)
    r = p.runs[0]
    r.bold = bold
    r.font.size = Pt(pt)
    r.font.name = font
    r._r.get_or_add_rPr().find(qn("w:rFonts")).set(qn("w:eastAsia"), font)
    return p


def _preset_rpr_change(path):
    """造一个带 w:rPrChange（格式修订标记）的 run。"""
    d = docx.Document()
    p = d.add_paragraph("带格式修订的段落内容。")
    rpr = p.runs[0]._r.get_or_add_rPr()
    chg = OxmlElement("w:rPrChange")
    chg.set(qn("w:id"), "9001")
    chg.set(qn("w:author"), "格式修订者")
    chg.set(qn("w:date"), "2026-10-30T00:00:00Z")
    inner = OxmlElement("w:rPr")
    chg.append(inner)
    rpr.append(chg)
    d.save(path)


def _preset_revision(path, preset_id, text):
    """构造一个自带 w:ins 既有修订的测试文档。"""
    d = docx.Document()
    p = d.add_paragraph("测试段落内容，用于验证修订插入。")
    ins = OxmlElement("w:ins")
    ins.set(qn("w:id"), str(preset_id))
    ins.set(qn("w:author"), "预置修订")
    ins.set(qn("w:date"), "2026-10-14T00:00:00Z")
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    ins.append(r)
    p._p.append(ins)
    d.save(path)


def main():
    tmpdir = tempfile.mkdtemp(prefix="tc_selftest_")

    # 场景 A：基础插入 + settings 结构断言
    src = os.path.join(tmpdir, "src.docx")
    out = os.path.join(tmpdir, "out.docx")
    d = docx.Document()
    d.add_paragraph("测试段落内容，用于验证修订插入。")
    d.save(src)
    doc, counter, author, date_iso = open_for_revision(src)
    apply(doc, counter, author, date_iso, 0, "测试段落内容", "（此处为修订插入）")
    doc.save(out)
    verify(out)
    s = etree.fromstring(zipfile.ZipFile(out).read("word/settings.xml"))
    order = [etree.QName(e).localname for e in s]
    print("settings顺序:", order)
    assert order.index("trackChanges") < order.index("defaultTabStop")
    assert order.index("rsids") < order.index("mathPr")

    # 场景 B：撞号回归——预置 w:ins id=10001，新插入不得重复
    src2 = os.path.join(tmpdir, "src2.docx")
    out2 = os.path.join(tmpdir, "out2.docx")
    _preset_revision(src2, 10001, "既有修订文字")
    doc2, counter2, author2, date_iso2 = open_for_revision(src2)
    apply(doc2, counter2, author2, date_iso2, 0, "测试段落内容", "（第二处修订）")
    assert counter2[0] > 10001, f"新插入id未避开既有修订id=10001: {counter2[0]}"
    doc2.save(out2)
    verify(out2)
    d2 = etree.fromstring(zipfile.ZipFile(out2).read("word/document.xml"))
    ids = [e.get(qn("w:id")) for e in d2.findall(".//" + qn("w:ins"))]
    print("场景B两处修订 w:id:", ids)
    assert len(set(ids)) == len(ids)

    # 场景 C（1.1.0 新增）：勘误——w:del + w:delText + 可选 w:ins 替换
    src3 = os.path.join(tmpdir, "src3.docx")
    out3 = os.path.join(tmpdir, "out3.docx")
    d3 = docx.Document()
    d3.add_paragraph("测试段落内容，用于验证修订插入。")
    d3.save(src3)
    doc3, counter3, author3, date3 = open_for_revision(src3)
    apply_del(doc3, counter3, author3, date3, 0, "段落", "章节")   # 改错字
    apply_del(doc3, counter3, author3, date3, 0, "修订", "")        # 纯删除
    doc3.save(out3)
    verify(out3, expect_ins=1, expect_del=2)
    d3x = etree.fromstring(zipfile.ZipFile(out3).read("word/document.xml"))
    for de in d3x.findall(".//" + qn("w:del")):
        assert de.find(".//" + qn("w:t")) is None, "w:del 内残留 w:t"
        assert de.find(".//" + qn("w:delText")) is not None, "w:del 内缺 delText"
    ids_all = ([e.get(qn("w:id")) for e in d3x.findall(".//" + qn("w:ins"))] +
               [e.get(qn("w:id")) for e in d3x.findall(".//" + qn("w:del"))])
    assert len(set(ids_all)) == len(ids_all), "ins/del id 撞号"

    # 场景 D（1.1.0 新增）：段内字符偏移插入
    src4 = os.path.join(tmpdir, "src4.docx")
    out4 = os.path.join(tmpdir, "out4.docx")
    d4 = docx.Document()
    d4.add_paragraph("一二三四五六七八九十")
    d4.save(src4)
    doc4, counter4, author4, date4 = open_for_revision(src4)
    split_insert(doc4.paragraphs[0].runs[0], 3, "【插入】", counter4, author4, date4)
    doc4.save(out4)
    verify(out4, expect_ins=1, expect_del=0)
    body4 = etree.fromstring(zipfile.ZipFile(out4).read("word/document.xml"))
    t4 = "".join(t.text or "" for t in body4.findall(".//" + qn("w:t")))
    assert "一二三" in t4 and "【插入】" in t4 and "四五六" in t4, f"偏移插入位置错: {t4}"

    # ── 场景 E（1.1.0 新增）：格式继承 ──────────────────────────────
    # 缺陷现象：插入的文字掉回文档默认字体（人工在 Word 里输入会自动
    # 继承当前格式）。根因：make_ins 造的 w:r 不带 w:rPr。
    # E1 常规插入继承锚点 run 的字体/字号/加粗
    src5 = os.path.join(tmpdir, "src5.docx")
    out5 = os.path.join(tmpdir, "out5.docx")
    d5 = docx.Document()
    _styled_run(d5, "正文测试内容")
    d5.save(src5)
    doc5, counter5, author5, date5 = open_for_revision(src5)
    apply(doc5, counter5, author5, date5, 0, "正文测试内容", "【插入】")
    doc5.save(out5)
    verify(out5, expect_ins=1, expect_del=0, check_fmt=True)
    body5 = etree.fromstring(zipfile.ZipFile(out5).read("word/document.xml"))
    ins_r = body5.find(".//" + qn("w:ins") + "/" + qn("w:r"))
    rpr5 = ins_r.find(qn("w:rPr"))
    assert rpr5 is not None, "插入的 run 未继承 w:rPr（格式不匹配当前格式）"
    assert rpr5.find(qn("w:b")) is not None, "加粗未继承"
    sz5 = rpr5.find(qn("w:sz"))
    assert sz5 is not None and sz5.get(qn("w:val")) == "32", \
        f"字号未继承（期望 32 = 16pt），实得 {sz5 is not None and sz5.get(qn('w:val'))}"
    f5 = rpr5.find(qn("w:rFonts"))
    assert f5 is not None and f5.get(qn("w:ascii")) == "仿宋", "字体未继承"

    # E2 段内偏移插入同样继承
    src6 = os.path.join(tmpdir, "src6.docx")
    out6 = os.path.join(tmpdir, "out6.docx")
    d6 = docx.Document()
    _styled_run(d6, "一二三四五六", pt=14)
    d6.save(src6)
    doc6, counter6, author6, date6 = open_for_revision(src6)
    split_insert(doc6.paragraphs[0].runs[0], 3, "【插入】", counter6, author6, date6)
    doc6.save(out6)
    verify(out6, expect_ins=1, expect_del=0, check_fmt=True)

    # E3 勘误替换：替换文字继承**被替换文字**的格式
    src7 = os.path.join(tmpdir, "src7.docx")
    out7 = os.path.join(tmpdir, "out7.docx")
    d7 = docx.Document()
    _styled_run(d7, "正文测试内容")
    d7.save(src7)
    doc7, counter7, author7, date7 = open_for_revision(src7)
    apply_del(doc7, counter7, author7, date7, 0, "测试", "章节")
    doc7.save(out7)
    verify(out7, expect_ins=1, expect_del=1, check_fmt=True)

    # E4 继承来的 rPr 不得带 w:rPrChange（格式修订标记）——
    #    复制嵌套的格式修订会形成非法结构，Word/WPS 可能拒开文件
    src8 = os.path.join(tmpdir, "src8.docx")
    out8 = os.path.join(tmpdir, "out8.docx")
    _preset_rpr_change(src8)
    doc8, counter8, author8, date8 = open_for_revision(src8)
    apply(doc8, counter8, author8, date8, 0, "段落", "【插入】")
    doc8.save(out8)
    body8 = etree.fromstring(zipfile.ZipFile(out8).read("word/document.xml"))
    for r8 in body8.findall(".//" + qn("w:ins") + "/" + qn("w:r")):
        rp8 = r8.find(qn("w:rPr"))
        if rp8 is not None:
            assert rp8.find(qn("w:rPrChange")) is None, \
                "继承的 rPr 里带 w:rPrChange（会形成嵌套格式修订）"

    # ── 场景 F（1.1.0 新增）：批注 ──────────────────────────────────
    # 批注要动四个地方：comments.xml / [Content_Types].xml / document.xml.rels /
    # document.xml 锚点。缺一个 Word/WPS 就打不开或看不到批注。
    src9 = os.path.join(tmpdir, "src9.docx")
    out9 = os.path.join(tmpdir, "out9.docx")
    d9 = docx.Document()
    _styled_run(d9, "正文测试内容，用于验证批注。")
    d9.save(src9)
    doc9, counter9, author9, date9 = open_for_revision(src9)
    cid1 = add_comment(doc9, 0, "验证批注", "这条批注挂在普通 run 上", author9, date9)
    cid2 = add_comment(doc9, 0, "正文", "第二条批注", author9, date9)
    assert cid2 == cid1 + 1, f"批注 id 应递增: {cid1} -> {cid2}"
    n9 = save_with_comments(doc9, out9)
    assert n9 == 2, f"应注入 2 条批注，实得 {n9}"
    verify(out9, expect_ins=0, expect_del=0, check_comments=True)

    # 批注部件与登记
    z9 = zipfile.ZipFile(out9)
    assert "word/comments.xml" in z9.namelist(), "缺 word/comments.xml"
    assert "/word/comments.xml" in z9.read("[Content_Types].xml").decode(), \
        "comments.xml 未在 [Content_Types].xml 登记"
    assert "comments.xml" in z9.read("word/_rels/document.xml.rels").decode(), \
        "comments.xml 未在 document.xml.rels 登记"
    # 正文锚点：start/end/reference 三者 id 配对
    body9 = etree.fromstring(z9.read("word/document.xml"))
    s9 = [e.get(qn("w:id")) for e in body9.findall(".//" + qn("w:commentRangeStart"))]
    e9 = [e.get(qn("w:id")) for e in body9.findall(".//" + qn("w:commentRangeEnd"))]
    r9 = [e.get(qn("w:id")) for e in body9.findall(".//" + qn("w:commentReference"))]
    assert sorted(s9) == sorted(e9) == sorted(r9), f"批注锚点不配对: {s9} {e9} {r9}"

    # 批注要能锚到**修订标记**上（"给某处删除写批注"是最常见用法）
    src10 = os.path.join(tmpdir, "src10.docx")
    out10 = os.path.join(tmpdir, "out10.docx")
    d10 = docx.Document()
    _styled_run(d10, "正文测试内容")
    d10.save(src10)
    doc10, counter10, author10, date10 = open_for_revision(src10)
    apply_del(doc10, counter10, author10, date10, 0, "测试", "章节")
    add_comment(doc10, 0, "章节", "此处原为错字，已改", author10, date10)
    save_with_comments(doc10, out10)
    verify(out10, expect_ins=1, expect_del=1, check_comments=True)

    # 导出清单
    data = export(out10)
    assert len(data["revisions"]) == 2, f"应导出 2 处修订，实得 {len(data['revisions'])}"
    assert len(data["comments"]) == 1, f"应导出 1 条批注，实得 {len(data['comments'])}"
    assert data["comments"][0]["text"] == "此处原为错字，已改", "批注内容导出错"
    print("导出清单: 修订", len(data["revisions"]), "批注", len(data["comments"]))

    # ── 场景 G（1.2.0 新增）：合并多稿 / 底纹标注 / 意见编排 ──────────
    from merge_markup import (shade_run, shaded_run, add_legend_page,
                              replace_paragraph, insert_paragraph_after,
                              insert_heading_after, apply_opinions,
                              merge_by_paragraph, FILL_GREEN, FILL_BLUE)

    srcg = os.path.join(tmpdir, "srcg.docx")
    outg = os.path.join(tmpdir, "outg.docx")
    dg = docx.Document()
    dg.add_paragraph("甲版本原段落内容。")
    dg.add_paragraph("乙版本原段落内容，需按意见重写。")
    dg.add_paragraph("待补充章节的位置。")
    dg.save(srcg)
    docg = docx.Document(srcg)

    # G1 底纹着色：三色 w:shd，实测结构合法
    pg = docg.add_paragraph()
    shaded_run(pg, "甲版本新增表述", FILL_GREEN)
    shaded_run(pg, "乙版本建议表述", FILL_BLUE, italic=True)

    # G2 图例页
    add_legend_page(docg)

    # G3 整段替换 + 段落/标题插入
    replace_paragraph(docg, 1, "按领导意见重写后的整段正文。")
    insert_paragraph_after(docg, 2, "（新增补充说明）")
    insert_heading_after(docg, 2, "五、征集意见情况")

    docg.save(outg)
    zg = zipfile.ZipFile(outg)
    assert zg.testzip() is None, "场景G zip损坏"
    bg = etree.fromstring(zg.read("word/document.xml"))
    shds = bg.findall(".//" + qn("w:shd"))
    fills = [s.get(qn("w:fill")) for s in shds]
    assert FILL_GREEN in fills and FILL_BLUE in fills, \
        f"底纹着色未写入: {fills}"
    for s in shds:
        assert s.get(qn("w:val")) == "clear" and s.get(qn("w:color")) == "auto", \
            "w:shd 属性不合法（应 val=clear/color=auto）"
    txtg = "".join(t.text or "" for t in bg.findall(".//" + qn("w:t")))
    assert "按领导意见重写后的整段正文。" in txtg, "整段替换失败"
    assert "（新增补充说明）" in txtg and "五、征集意见情况" in txtg, "段落/标题插入失败"
    assert "整合版本" in txtg and "标注说明" in txtg, "图例页未生成"
    print("场景G 底纹数:", len(shds), "fills:", sorted(set(fills)))

    # G4 意见清单编排：逐条返回状态，不静默吞错
    srch = os.path.join(tmpdir, "srch.docx")
    docx.Document().save(srch)
    doch = docx.Document(srch)
    doch.add_paragraph("段落零")
    doch.add_paragraph("段落一")
    cfg = {"opinions": [
        {"id": 1, "op": "replace_para", "p_idx": 0, "text": "改后段落零"},
        {"id": 2, "op": "insert_after", "p_idx": 1, "text": "补充"},
        {"id": 3, "op": "heading_after", "p_idx": 1, "text": "新标题"},
        {"id": 4, "op": "correct", "p_idx": 0, "phrase": "x", "text": "y"},
        {"id": 5, "op": "bogus", "p_idx": 0},
    ]}
    results = apply_opinions(doch, cfg)
    st = {oid: status for oid, op, status in results}
    assert st[1] == "ok" and st[2] == "ok" and st[3] == "ok", f"编排失败: {results}"
    assert st[4] == "skipped:no_apply_del", f"correct 未注入时应标注跳过: {st[4]}"
    assert st[5].startswith("skipped:unknown_op"), f"未知 op 应标注跳过: {st[5]}"
    print("场景G 意见编排:", results)

    # G5 两稿按段对齐（机械对齐，不代判内容）
    aligned = merge_by_paragraph(["甲段", "相同"], ["乙段", "相同", "仅乙有"])
    assert [x["status"] for x in aligned] == ["differ", "both", "incoming_only"], \
        f"按段对齐错: {aligned}"

    # ── G6（1.2.1 新增）：整段替换须清掉段内既有修订 ─────────────────
    # 缺陷（v1.2.0 评测点名、代码级实锤）：旧版 replace_paragraph 只清直系
    # w:r，段内既有 w:ins/w:del 包裹 run 原样残留——"整段替换"后旧修订
    # 文字仍在段里。修复判据：替换后段内零修订标记、零旧文本、pPr 保留。
    srci = os.path.join(tmpdir, "srci.docx")
    outi = os.path.join(tmpdir, "outi.docx")
    di = docx.Document()
    di.add_paragraph("段落零，不动。")
    pi = _styled_run(di, "既有正文")
    pi.paragraph_format.first_line_indent = Pt(32)   # 造出 pPr，验证替换后保留
    ins_i = OxmlElement("w:ins")
    ins_i.set(qn("w:id"), "10001")
    ins_i.set(qn("w:author"), "预置修订")
    ins_i.set(qn("w:date"), "2026-11-19T00:00:00Z")
    r_i = OxmlElement("w:r")
    t_i = OxmlElement("w:t")
    t_i.set(qn("xml:space"), "preserve")
    t_i.text = "旧修订文字"
    r_i.append(t_i)
    ins_i.append(r_i)
    pi._p.append(ins_i)
    # 再预置一个批注锚点（整段替换应连锚点一并清，防残留空锚点）
    crs = OxmlElement("w:commentRangeStart")
    crs.set(qn("w:id"), "9")
    pi._p.append(crs)
    cre = OxmlElement("w:commentRangeEnd")
    cre.set(qn("w:id"), "9")
    pi._p.append(cre)
    di.save(srci)
    doci = docx.Document(srci)
    replace_paragraph(doci, 1, "重写后的整段正文。")
    doci.save(outi)
    zi = zipfile.ZipFile(outi)
    assert zi.testzip() is None, "G6 zip损坏"
    bi = etree.fromstring(zi.read("word/document.xml"))
    paras = bi.findall(".//" + qn("w:p"))
    p0x, p1x = paras[0], paras[1]
    assert p0x.find(".//" + qn("w:ins")) is None, "段落零不应被波及"
    assert p1x.find(".//" + qn("w:ins")) is None and p1x.find(".//" + qn("w:del")) is None, \
        "G6 失败：整段替换后段内残留既有修订标记"
    assert p1x.find(".//" + qn("w:commentRangeStart")) is None, \
        "G6 失败：批注锚点残留（空锚点）"
    ti = "".join(t.text or "" for t in p1x.findall(".//" + qn("w:t")))
    assert ti == "重写后的整段正文。", f"G6 替换后段内文本错: {ti!r}"
    assert p1x.find(qn("w:pPr")) is not None, "G6 pPr 未保留"
    # 字体继承：新 run 的 rPr 应来自段内首个 run（含直接格式 b/仿宋/32）
    new_r = p1x.find(qn("w:r"))
    rpr_i = new_r.find(qn("w:rPr"))
    assert rpr_i is not None and rpr_i.find(qn("w:b")) is not None, \
        "G6 新 run 未继承既有 run 的 rPr"
    txt0 = "".join(t.text or "" for t in p0x.findall(".//" + qn("w:t")))
    assert txt0 == "段落零，不动。", f"G6 邻段被误改: {txt0!r}"
    print("G6 整段替换清场:", ti, "| 修订/批注锚点残留=无 | pPr保留")

    # ── G7（1.2.2 新增）：merge_markup 命令行 ────────────────────────
    import json as _json
    import subprocess
    MM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_markup.py")
    src7 = os.path.join(tmpdir, "srcg7.docx")
    d7 = docx.Document()
    d7.add_paragraph("甲段原文。")
    d7.add_paragraph("乙段原文。")
    d7.save(src7)
    out7 = os.path.join(tmpdir, "outg7.docx")

    rc = subprocess.run([sys.executable, MM, src7, out7, "--replace", "1", "重写后的乙段。"],
                        capture_output=True, text=True)
    assert rc.returncode == 0, f"G7 --replace 失败: rc={rc.returncode} {rc.stdout[-200:]}{rc.stderr[-200:]}"
    b7 = etree.fromstring(zipfile.ZipFile(out7).read("word/document.xml"))
    t7 = "".join(t.text or "" for t in b7.findall(".//" + qn("w:t")))
    assert "重写后的乙段。" in t7 and "甲段原文。" in t7, f"G7 替换文本错: {t7}"

    rc = subprocess.run([sys.executable, MM, src7, out7, "--replace", "abc", "x"],
                        capture_output=True, text=True)
    assert rc.returncode == 1, f"G7 非整数段号应退 1: {rc.returncode}"
    rc = subprocess.run([sys.executable, MM, src7, out7, "--replace", "99", "x"],
                        capture_output=True, text=True)
    assert rc.returncode == 1, f"G7 段号越界应退 1: {rc.returncode}"
    rc = subprocess.run([sys.executable, MM, src7, out7], capture_output=True, text=True)
    assert rc.returncode != 0, "G7 缺操作参数应报错（argparse 互斥组 required）"

    # --opinions 含 correct：自动经 open_for_revision 启用修订并注入 apply_del
    cfg7 = os.path.join(tmpdir, "ops7.json")
    with open(cfg7, "w", encoding="utf-8") as f:
        _json.dump({"opinions": [
            {"id": 1, "op": "replace_para", "p_idx": 0, "text": "按意见重写的甲段。"},
            {"id": 2, "op": "correct", "p_idx": 1, "phrase": "乙段", "text": "乙章"},
        ]}, f, ensure_ascii=False)
    rc = subprocess.run([sys.executable, MM, src7, out7, "--opinions", cfg7],
                        capture_output=True, text=True)
    assert rc.returncode == 0, f"G7 --opinions 失败: rc={rc.returncode} {rc.stdout[-300:]}{rc.stderr[-300:]}"
    z7 = zipfile.ZipFile(out7)
    b7 = etree.fromstring(z7.read("word/document.xml"))
    assert b7.find(".//" + qn("w:del")) is not None, "G7 correct 未写入 w:del"
    s7 = etree.fromstring(z7.read("word/settings.xml"))
    assert s7.find(qn("w:trackChanges")) is not None, "G7 correct 未启用 trackChanges"
    del_texts = [dt.text or "" for dt in b7.findall(".//" + qn("w:delText"))]
    assert "乙段" in "".join(del_texts), f"G7 勘误原句未入 w:delText: {del_texts}"
    print("G7 merge_markup CLI: replace/码位1/越界1/缺参/opinions(correct) 全过")

    print("SELF-TEST OK")

if __name__ == "__main__":
    main()
