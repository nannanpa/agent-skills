# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""docx-track-changes-wps 自检脚本（跨平台，macOS/Windows 通用）。

两个场景：
A. 基础插入 + settings.xml 结构断言；
B. 撞号回归：文档自带修订史（预置 w:ins id=10001）时，新插入不得与既有 id 重复
   （Windows 侧 2026-10-14 实测复现过的缺陷）。
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
from lxml import etree
from apply_track_changes import open_for_revision, apply, verify


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

    print("SELF-TEST OK")


if __name__ == "__main__":
    main()
