---
name: docx-track-changes-wps
description: This skill should be used when inserting tracked changes (修订模式 / redline revisions) into a .docx document with python-docx + lxml, especially for Chinese official documents that must open cleanly in WPS without the "rainbow spinner / 无响应" hang. Covers enabling trackChanges, placing w:ins insertions, avoiding the WPS infinite-loop pitfalls, and verifying the result.
---

# docx-track-changes-wps

Insert real, WPS-safe tracked changes into a Word `.docx` using python-docx plus direct `lxml` manipulation. Designed for Chinese official-document redline workflows (e.g. 报送"两个工作要点"修改意见、在发文稿上以"修订模式"标注修改/新增).

## When to use

- A user asks to "另存一份原文稿 / 打开修订模式 / 以修订模式把修改意见修订进去" on a `.docx`.
- The output must open in **WPS** (common in Chinese government / university environments) without hanging on a rainbow spinner.
- Revisions are "修改完善"(revise) or "新增"(add) — i.e. mostly insertions against an existing paragraph.

## Golden rule: prefer `w:ins` over `w:del`

For Chinese redline workflows the safest pattern is **insertion-only**: keep the original run text and insert the new text as a `w:ins` element right after the anchor run. Avoid `w:del` (deletions) wherever possible — `w:del` with `w:delText` and `w:rPrChange` is the single most common trigger of the WPS rainbow-loop hang. If a "replacement" is really "append a suffix", model it as an insertion after the original phrase, not as delete+insert.

## WPS rainbow-loop avoidance checklist (mandatory)

1. **Unique `w:id`** across the whole document (use a global counter, start high like 10001 to avoid clashing with any existing ids).
2. **Valid `w:date`** in ISO 8601 form, e.g. `2026-07-23T09:00:00Z`.
3. **`w:author`** present on every `w:ins`.
4. **Enable track changes properly**: in `word/settings.xml` add `<w:trackChanges w:val="true"/>` AND add `<w:rsidRoot w:val="..."/>` (reuse the existing `w:rsidRDefault` value if present, else a fixed 8-hex value). Missing `rsidRoot` while runs carry `w:rsidR` is a known WPS hang trigger.
5. **Inserted `w:r` carries NO `w:rPr`** (plain `<w:r><w:t>...</w:t></w:r>` inside the `w:ins`). An `rPr` that references a font/style not present can make WPS loop.
6. **Never touch the body-level `w:sectPr`** (it is a direct child of `w:body`, not inside the last paragraph) and never wrap the final section-break paragraph in `w:ins`/`w:del`.
7. Keep `w:t` text with `xml:space="preserve"` so leading/trailing spaces survive.

## Procedure

1. Copy the original `.docx` to a new filename first (keep the source pristine).
2. Open with python-docx; enable `trackChanges` + `rsidRoot` in `doc.settings.element`.
3. For each revision, locate the target paragraph and the anchor **run** that contains the boundary phrase. All runs in these docs typically have `style=None` (inherited paragraph font) — safe to copy or omit `rPr`.
4. Insert the new text as a `w:ins` element placed as a sibling right after the anchor run. If the boundary phrase ends mid-run, split the run at the offset (copy `rPr` to the new suffix run, set the original run's text to the prefix), then insert the `w:ins` between prefix and suffix.
5. `doc.save(...)` and verify (see below).

## Known pitfalls

- **Hidden characters in anchor phrases.** Chinese documents frequently embed `》（U+300B）`, ``（U+300C）`, `—（U+2014）` etc. inside what looks like plain text (e.g. `《…（2025—2027年）》` ends with `年）》。`). A literal anchor like `"年），"` will NOT match because of the hidden `》`. **Construct tricky anchors with explicit Unicode escapes** (`"年"+"\uFF09"+"\u300B"+"\uFF0C"`) and/or print `repr()` of the candidate run to confirm exact characters before matching.
- **python-docx `paragraph.text` omits `w:ins` content.** After editing, `paragraph.text` will NOT show inserted text (it only concatenates direct `w:r` children, not runs inside `w:ins`). To verify placement, parse `word/document.xml` and concatenate all descendant `w:t` (including those under `w:ins`/`w:del`).
- **Run boundaries**: a phrase often spans multiple runs (e.g. `"一院一策"` split as `一院`+`策`). Anchor on the run that *starts* with the phrase tail, or split at the run boundary, rather than assuming one run.

## Verification (always run after save)

- `zipfile.ZipFile(path).testzip()` is `None` (archive intact).
- `etree.fromstring(z.read('word/document.xml'))` parses (well-formed).
- `trackChanges` value is `true`; `rsidRoot` present.
- Count `w:ins` == expected, `w:del` == 0 (if insertion-only), `w:id` set is unique, each `w:ins` has author+date+inner `w:r`.
- For each target paragraph, full-text (incl. `w:ins`) contains the inserted keywords.

See `scripts/apply_track_changes.py` for a ready-to-use, WPS-safe implementation with an `apply(paragraph_index, anchor_phrase, insert_text)` helper.
