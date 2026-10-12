#!/usr/bin/env python3
"""WPS-safe tracked-change (修订模式) inserter for .docx.

Usage:
    python apply_track_changes.py SRC.docx OUTPUT.docx [author] [date_iso]

Then call the apply() helper from your own script, or import and drive it.
Insertion-only: keeps original text, adds new text as <w:ins> right after an
anchor run. Avoids <w:del> to prevent the WPS "rainbow spinner" hang.
"""
import copy
import sys
import docx
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def open_for_revision(src, author="发展规划与学科建设处", date_iso="2026-07-23T09:00:00Z"):
    """Open src, enable trackChanges + rsidRoot, return (doc, counter)."""
    doc = docx.Document(src)
    settings = doc.settings.element

    def ensure_child(parent, tag, attrs=None):
        el = parent.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            if attrs:
                for k, v in attrs.items():
                    el.set(qn(k), v)
            parent.append(el)
        elif attrs:
            for k, v in attrs.items():
                el.set(qn(k), v)
        return el

    ensure_child(settings, "w:trackChanges", {"w:val": "true"})
    rsid_default = settings.find(qn("w:rsidRDefault"))
    root_val = rsid_default.get(qn("w:val")) if rsid_default is not None else "00FF1234"
    ensure_child(settings, "w:rsidRoot", {"w:val": root_val})
    counter = [10000]
    return doc, counter, author, date_iso


def make_ins(text, counter, author, date_iso):
    ins = OxmlElement("w:ins")
    counter[0] += 1
    ins.set(qn("w:id"), str(counter[0]))
    ins.set(qn("w:author"), author)
    ins.set(qn("w:date"), date_iso)
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    ins.append(r)
    return ins


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
    """
    p = doc.paragraphs[p_idx]
    for run in p.runs:
        if phrase in run.text:
            off = run.text.find(phrase)
            end = off + len(phrase)
            if end >= len(run.text):
                run._r.addnext(make_ins(text, counter, author, date_iso))
            else:
                split_run_at(run, end)
                run._r.addnext(make_ins(text, counter, author, date_iso))
            return
    raise ValueError(f"anchor phrase not found in paragraph {p_idx}: {phrase!r}")


def verify(path):
    import zipfile
    from lxml import etree
    z = zipfile.ZipFile(path)
    assert z.testzip() is None, "zip corrupted"
    etree.fromstring(z.read("word/document.xml"))  # well-formed
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(qn("w:body"))
    ins = body.findall(".//" + qn("w:ins"))
    dels = body.findall(".//" + qn("w:del"))
    ids = [i.get(qn("w:id")) for i in ins]
    assert len(set(ids)) == len(ids), "duplicate w:id"
    for i in ins:
        assert i.get(qn("w:author")) and i.get(qn("w:date")) and i.find(qn("w:r")) is not None
    print(f"OK: w:ins={len(ins)} w:del={len(dels)} ids_unique={len(set(ids))==len(ids)}")
    return len(ins)


if __name__ == "__main__":
    src = sys.argv[1]
    out = sys.argv[2]
    author = sys.argv[3] if len(sys.argv) > 3 else "发展规划与学科建设处"
    date_iso = sys.argv[4] if len(sys.argv) > 4 else "2026-07-23T09:00:00Z"
    doc, counter, a, d = open_for_revision(src, author, date_iso)
    # Example: insert an addition after the first occurrence of a phrase.
    # apply(doc, counter, a, d, p_idx=5, phrase="规划的任务分解和具体落实。",
    #       text="（此处为示例插入内容）")
    doc.save(out)
    verify(out)
