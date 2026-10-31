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

    print("SELF-TEST OK")

if __name__ == "__main__":
    main()
