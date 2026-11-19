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
pip install -r requirements.txt   # 1.2.1 起提供依赖清单（python-docx / lxml 最低版本）
```

安装与运行均在本地完成，无需网络。

## 使用

把整个文件夹复制到你的 agent skills 目录（如 `~/.workbuddy/skills/`），脚本在 `scripts/apply_track_changes.py`。

## 发布记录
- **2026-11-20 v1.2.4（复评对账修补）**：v1.2.3 复评（4.80）点名的批注数据丢失缺陷等四项实锤修补。①**修最严重缺陷——批注部件被重建、丢原批注正文**：`_inject_comments` 旧版每次用"本次新增批注"重写 `comments.xml`，文档原有批注正文全部消失；现读出既有条目原样保留后追加新批注，Content_Types 与关系（rel）均判重复用（重复保存不再堆重复关系）；②`add_comment` 段落号 `int()` 纳入异常捕获（非法整数退 1，不再抛堆栈）；③`--anchor`／`anchor_phrase` 未命中改为显式报错（不再静默把批注挂错位置）；④自检新增 G12：预置批注＋追加批注后断言两条正文俱在、id 不撞、rel 只一条、三方 id 仍配对，并覆盖 anchor 报错与非法段落号码位。
- **2026-11-19 v1.2.3（复评对账修补）**：v1.2.2 复评（4.80）五项新扣分点经代码级实锤后逐项修补。①**修批注 id 撞号真缺陷**——`add_comment` 只看本次待写批注、固定 1 起号，文档自带批注史必撞号（与修订 w:id 撞号同源，彩虹圈家族）；现起号取文档既有批注 id 最大值＋1（扫描正文锚点三方＋已有 comments.xml 部件）；②**修拆分 run 丢制表符/换行**——`split_run_at` 旧版把 `w:tab`/`w:br`/`w:cr` 直接丢弃，现按子元素逐个归属（计长口径与 run.text 一致），跨界的 `w:t` 两侧各留一半；③`open_for_revision` docstring 返回值 `(doc, counter)` 改四元组（代码注释与实际不符）；④**四脚本退出码统一 0/1/2**——add_comment 保存后自动跑 `verify(check_comments=True)`（失败退 2），export_markup 补中文报错与 `-o` 缺值处理（只读导出用 0/1）；⑤**apply_opinions 同段冲突检测**——先 correct 后 replace_para 的组合不再执行，标 `skipped:conflict` 并给处置建议（防勘误留痕被清场吞掉）。自检新增批注 id 回归／tab-br 保留／冲突检测／CLI 码位断言。
- **2026-11-19 v1.2.2（复评对账修补）**：v1.2.1 复评（4.8133）新扣分点逐项对账。①**修 SKILL.md 文末 apply 签名行**（accuracy＋usability 两处点名：旧行 `apply(paragraph_index, anchor_phrase, insert_text)` 与真实签名不符，v1.1.1 遗留）——改为真实签名并补参数说明；②**merge_markup.py 加实用命令行**（usability＋func 两处点名）——`--replace／--insert-after／--heading-after／--opinions config.json` 四操作互斥，退出码分区与主脚本同口径（0/1/2），`--opinions` 含 correct 时自动经 open_for_revision 启用修订并注入 apply_del，保存后 zip/XML 完整性断言；③**整段替换清场风险提示前置**（boundary 4.8 扣分点）——"替换会连同段内既有修订与批注一并清除、先导出清单"提升到黄金法则节显式警示。自检增至八场景（新增 G7：CLI 四操作＋码位实测全过）。
- **2026-11-19 v1.2.1（评测驱动修补）**：v1.2.0 评测（4.79）点名缺陷逐项对账修补。①**修真缺陷**——`merge_markup.replace_paragraph()` 整段替换只清直系 `w:r`，段内既有 `w:ins`/`w:del` 修订文字残留（评测点名、代码级实锤）；现按内容性标签清单清除（修订包裹、超链接/域/smartTag、批注锚点三件），只留 pPr 与书签，字体继承改为深查找（修订内 run 也能取到 rPr），新增自检场景 G6 断言"替换后段内零修订残留"；②SKILL.md 加显式目录；③CLI 退出码分区写死文档（0 成功｜1 输入/用法错｜2 结构校验未通过），`verify()` 断言失败改退 2；④补 `requirements.txt`；⑤两处表述改实——"整段替换"补清场语义与留痕须知、"保存后校验"如实说明 settings 校验为关键位置断言而非全量 schema 顺序校验；⑥既有批注/超链接段落处理指引集中进 FAQ。
- **2026-11-19 v1.2.0（马斌侧整合，Windows/WPS 实测通过）**：新增 `merge_markup.py`——合并多稿底纹着色标注（`w:shd` 三色区分来源）、整合说明图例页、按意见编号配置批量改稿、整段替换、段落/标题级插入、两稿按段对齐清单；底纹与修订标记、批注并列为三套并行机制（分别回答"来自谁／改了什么／为什么改"）。作者署名加和欣月（贡献原料，提炼自其端真实任务并经脱敏回传）。Windows 终端中文编码坑（`-X utf8` + `\uXXXX`）入「已知坑」。新增自检场景 G；v1.1.1 原版六场景自检基线全绿。**Windows/WPS 实测已回传并通过**：self_test 场景 G 全绿（EXIT=0），三色底纹经 WPS 官方引擎转 PDF 后从渲染结果提取填充色 `#CCE5FF×5／#CCFFCC×5／#FFFF99×4`、三色独立不串色；三步验收的第③步"接受/拒绝修订"因本机无 GUI、COM 被拦未做，标"需人工确认"，依据链路未改＋1.1.1 已验＋引擎解析通过不阻断发布。
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
