# LESSONS · docx-format-guard（复盘层，随包分发，先读已知坑再上手）

> 本文件记录踩坑与口径修正，随技能包分发——使用者上手前先读本章，避开三个经典暗坑。

## 坑1 · line_spacing 把 Length 当倍数（2026-11 复盘）

- **现象**：想把行距设成固定值 28 磅，结果文档行距被当成“28 倍行高”，整页撑爆。
- **原因**：python-docx 中 `paragraph_format.line_spacing` 赋 **float** 时被解释为“倍数”；赋 **Length**（如 `Pt(28)`）才是绝对距离。若误写成 `line_spacing = Length(28)`（28 EMU≈0）或只给 float，就会错。
- **定式**：固定值行距必须两步一起：
  ```python
  pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
  pf.line_spacing = Pt(28)          # 单位 twips(磅)，非行
  ```
- **自检挂钩**：`selfcheck.py` 断言 `line_spacing_rule == EXACTLY` 且实测磅数 == 参数单。

## 坑2 · 插入段落不继承样式（2026-11 复盘）

- **现象**：生成后回读，标题/正文跑出 Calibri 11 这类默认字体，指定中文字体没生效。
- **原因**：`add_paragraph()` 的新段落按 Normal 样式走，run 不会自动继承“公文样式”；只对段落设样式、不显式设 run.font，字体就回退默认。
- **定式**：每个 run 都显式设置，且**中西文一起设**（否则中文丢字体）：
  ```python
  run.font.name = name
  rfonts.set(qn('w:eastAsia'), name)   # 中文必须单独置 eastAsia
  ```
- **自检挂钩**：`selfcheck.py` 读 `w:eastAsia` 比对；并断言 `run.font.name is not None`（防默认继承漏设）。

## 坑3 · 固定值行距单位“磅”不是“行”（2026-11 复盘）

- **现象**：同坑1 的另一种表述，但强调单位概念错误：把“固定值 28 磅”理解成“28 行”。
- **定式**：固定值行距单位是**磅(pt)**，`line_spacing_rule` 必须 `EXACTLY`（对应 Word 里“行距：固定值”，值填磅数）。`MULTIPLE` 才是“多倍行距（行）”。
- **自检挂钩**：`selfcheck.py` 对非 EXACTLY 直接判 FAIL，并提示“固定值行距单位磅”。

## 口径修正

- 套 A / 套 B 并存：**默认套 A**；“黑体22号”属和欣月端真实做法（annual-report-case-selection 第6条），不是错字；但**技能不自行认文种**，须用户当次明确指定才走套 B。
- “黑体 22” 与 “一级标题黑体 16” 是两码事：文档标题 22pt 用 方正小标宋_GBK（套A）/黑体（套B），一级标题 16pt 用黑体。
