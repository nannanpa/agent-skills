# docx-track-changes-wps

用 python-docx + lxml 向 `.docx` 写入真正的"修订模式"（tracked changes / redline revisions），专为**中文公文场景**设计：修改意见报送、发文稿上标注修改/新增，且必须在 **WPS** 中干净打开。

## 解决的问题

WPS 对修订 XML 极其敏感，手写的 `w:ins`/`w:del` 很容易触发"彩虹圈无限转圈"无响应。本 skill 沉淀了完整的避坑清单：

- 全文档唯一 `w:id`、合法 ISO 8601 `w:date`
- `settings.xml` 里 `trackChanges` 必须配合 `rsidRoot`
- 优先**只插不改**（`w:ins` 优于 `w:del`），但**不禁用 `w:del`**：彩虹圈的真实成因是结构非法（id 撞号、缺 author/date、误碰 body 级 sectPr），不是 `w:del` 本身；改错字、删多余字词、改已在文本中间的日期等场景**无法用插入表达**，必须走 `w:del` + `w:delText`（1.1.0 起提供 `apply_del()` / `del_insert()`）
- **插入内容继承锚点格式**（1.1.0）：公文正文普遍用直接格式（标题方正小标宋、正文仿宋_GB2312 三号、节标题黑体），插入的 `w:r` 若不带 `w:rPr`，文字会掉回文档默认字体——一眼能看出"不是同一个人打的字"。现由 `_rpr_for()` 自动继承（run 自身 → 段落标记 → 段落样式三级取值），并剔除 `w:rPrChange` 防嵌套格式修订
- **批注（comment）写入**（1.1.0）：真实审校流程里修订标记与批注是两套并行的——标记说"改了"，批注说"为什么改"。批注要动四个部件（`word/comments.xml`、`[Content_Types].xml`、`document.xml.rels`、`document.xml` 锚点），`add_comment.py` 用保存后 zip 后处理一次做齐，并支持**把批注锚到 `w:ins`/`w:del` 修订标记上**（"给某处删除写批注"是最常见用法）
- **导出修订批注清单**（1.1.0）：`export_markup.py` 把修订标记与批注整理成两张 Markdown 表——段落／动作／内容／作者／日期，直接就是"修改意见报送"要交的那份清单（纯读取，不改文件）
- 中文标点（`》`U+300A、`—`U+2014）隐藏字符导致锚点匹配失败的排查法

完整清单、操作流程和验证方法见 [SKILL.md](./SKILL.md)。

## 环境

Python 3.8+ 与 python-docx、lxml：

```bash
pip install python-docx lxml
```

安装与运行均在本地完成，无需网络。

## 使用

把整个文件夹复制到你的 agent skills 目录（如 `~/.workbuddy/skills/`），脚本在 `scripts/apply_track_changes.py`。

## 发布记录
- **2026-10-31 v1.1.1（GitHub，SkillHub 同号）**：口径修补＋CLI 做实——更正「未验证声明」中“全程不用 `w:del`”的旧表述（纯插入场景不用，勘误场景见「勘误与替换」节）；脚本注释里的遗留版本号改为不绑定具体版本（随 SKILL.md 头部），不再逐版改注释；README 新增「环境」段（依赖安装说明）；批注 CLI 新增 `--phrase`（必填挂载锚点）与 `--anchor`（另锚）双参数，不再缺省静默取首 run；**修订主脚本 CLI 支持真插入**——`--p-idx N --phrase 短语 --text 新文` 走 `apply()` 实际写入 w:ins（`--del` 走 `apply_del()` 勘误），不给操作参数时明示“仅保存并校验，未修改正文”
- **2026-10-30 v1.1.0（GitHub，SkillHub 同号）**：三项合并发布。①**实战勘误扩展**——新增 `apply_del()`（按锚点短语删旧换新）、`del_insert()`（run 内字符区间删除并可插入替换）、`split_insert()`（段内字符偏移插入），以 10-27 真实公文修订脚本为基础整理入技能；`make_del()` 自动将 `w:t` 转为 `w:delText`；`verify()` 的 `w:ins`/`w:del` **合查** id 唯一性、断言 `w:del` 内不得残留 `w:t`、新增 `expect_ins`/`expect_del` 数量断言。②**格式继承**——修一个实战暴露的观感缺陷：插入的文字不继承当前格式（根因：`make_ins()` 造的 `<w:r>` 不带 `w:rPr`，而公文正文普遍用直接格式，插入内容掉回文档默认字体，与人工在 Word 里输入的观感不符）。新增 `_rpr_for()`（run 自身 → 段落标记 → 段落样式三级取值），`apply()`/`split_insert()`/`del_insert()` 分别继承锚点 run、被拆 run、**被替换文字**的格式；继承时剔除 `w:rPrChange`；**更正「彩虹圈规避清单」第 5 条**（原写"插入的 `w:r` 不带 `w:rPr`"，把格式不继承固化成了规范，现更正为"不得凭空造 rPr，但必须继承锚点已有的 rPr"）。③**批注**——补齐人工审校的另一半：修订标记说"改了"，批注说"为什么改"。新增 `add_comment.py`（批注要动四个部件：`word/comments.xml`、`[Content_Types].xml`、`document.xml.rels`、`document.xml` 锚点；python-docx 无内置 comments part，故用保存后 zip 后处理；锚点**穿透 `w:ins`/`w:del`**，"给某处删除写批注"时批注范围包住整个修订标记）与 `export_markup.py`（导出修订标记表＋批注表为 Markdown，即"修改意见报送"要交的那份清单）。`verify()` 新增 `check_fmt`/`check_comments` 两项断言；`self_test.py` 增至六场景。**实测**：35 段真实公文上 `w:ins=3 / w:del=2 / 批注 3` 全绿；格式继承 A/B 对照（修复前插入 run 无 rPr → 修复后 `fonts=仿宋_GB2312 / sz=32`，与同段正文完全一致）
- **2026-10-15 v1.0.6（GitHub，SkillHub 同号）**：SKILL.md 新增「样例：一次插入前后的 XML（真实产物）」节（w:ins 结构与 author/date 直观可见）
- **2026-10-15 v1.0.5（GitHub，SkillHub 同号）**：CLI 入口新增中文友好报错（缺参数、找不到文件、无效 docx、校验未通过逐项给出下一步动作）；SKILL.md 新增「常见问题 FAQ」节
- **2026-10-15 SkillHub 1.0.4**：双平台交叉验证后修复——①`ensure_child` 按 CT_Settings schema 顺序找锚点插入，`w:rsidRoot` 归位到 `w:rsids` 内部（旧版误插 `w:settings` 直属位置，实测 WPS 卡死诱因）；②新增撞号修复：计数器起号取 max(10000, 文档既有修订 id 最大值)（固定 10001 在自带修订史的稿件上必然撞号，Windows 实测复现）；③`verify()` 内置 settings 结构回归断言；④新增跨平台 `scripts/self_test.py`（基础插入 + 撞号回归两场景）；⑤SKILL.md 新增"适用环境与未验证声明"与已知坑（WPS 个人版修订窗格不显示时间列）；⑥默认修订作者改为中性"审校"（脱敏补漏）。实测：Windows 10 + WPS 12.1.0.29161 self-test 一次全绿，WPS 三点检查两过一判定通过
- **2026-10-13 SkillHub 1.0.3**：脱敏——示例句中内部文件指代改为通用表述（"规划、要点类文件"）
- **2026-10-13 SkillHub 1.0.2**：SKILL.md 全文由英文重写为中文（技术术语与代码不变）——SkillHub 详情页"概述"直接展示 SKILL.md，英文版导致市场页显示英文描述
- **2026-10-13 SkillHub 1.0.1**：分发侧补充自定义图标与分类标签（内容无变化）
- **2026-10-12 首发**：python-docx + lxml 给 .docx 插入修订模式（tracked changes，兼容 WPS）

> 本目录只保留最新版；历史版本见 git 提交记录。


## License

MIT
