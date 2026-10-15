---
name: docx-track-changes-wps
description: 向 .docx 文档插入真正的"修订模式"（tracked changes / redline）时使用，python-docx + lxml 实现，专为中文公文场景设计——成品必须在 WPS 中干净打开、不触发"彩虹圈/无响应"卡死。涵盖启用 trackChanges、放置 w:ins 插入、规避 WPS 死循环陷阱、保存后校验。触发词：修订模式、插入修订、修改意见标注、发文稿修订、docx 修订、WPS 修订。
---

# docx-track-changes-wps

用 python-docx 加 `lxml` 直接操作 XML，向 Word `.docx` 写入真正的"WPS 安全"修订（tracked changes）。专为**中文公文场景**设计：修改意见报送（如报送规划、要点类文件的修改意见）、在发文稿上以"修订模式"标注修改/新增。

## 适用场景

- 用户要求"另存一份原文稿 / 打开修订模式 / 以修订模式把修改意见修订进去"一个 `.docx`；
- 成品必须在 **WPS** 中打开（政府/高校环境最常见），不能卡在彩虹圈无响应；
- 修订类型是"修改完善"或"新增"——即主要是在既有段落上做**插入**。

## 黄金法则：优先 `w:ins`，避免 `w:del`

中文公文修订场景最安全的模式是**只插入**：保留原文 run，把新增文字作为 `w:ins` 元素紧插在锚点 run 之后。尽量不用 `w:del`（删除）——`w:del` + `w:delText` + `w:rPrChange` 是 WPS 彩虹圈卡死的第一大诱因。如果"修改"实际是"在原句后补一句"，就建模为在原句后插入，而不是删除+插入。

## WPS 彩虹圈规避清单（必查）

1. **`w:id` 全文唯一**（计数器起号取 max(10000, 文档既有 `w:ins`/`w:del` id 最大值)——固定 10001 起号在自带修订史的稿件上必然撞号，Windows 侧 2026-10-14 实测复现；实现见 `_max_revision_id`，附两轮插入-重开回归测试）。
2. **`w:date` 合法**，ISO 8601 格式，如 `2026-07-23T09:00:00Z`。
3. 每个 `w:ins` 上都要有 **`w:author`**。
4. **正确启用修订**：`word/settings.xml` 里加 `<w:trackChanges w:val="true"/>`；`<w:rsidRoot w:val="..."/>` **必须放在 `w:rsids` 元素内部**（`w:rsidRoot`/`w:rsidRDefault` 都不是 `w:settings` 的直接子元素——用 `settings.find()` 找不到就会误判缺失而重复追加非法元素，这是实测踩过的坑）。新增元素的插入位置要符合 CT_Settings 顺序：`trackChanges` 在 `defaultTabStop` 之前、`rsids` 在 `mathPr`/`themeFontLang` 之前。run 带 `w:rsidR` 而缺 `rsidRoot` 是已知的 WPS 卡死诱因。
5. **插入的 `w:r` 不带 `w:rPr`**（`w:ins` 里就是纯 `<w:r><w:t>...</w:t></w:r>`）。rPr 引用了文档里不存在的字体/样式可能让 WPS 死循环。
6. **绝不碰 body 级 `w:sectPr`**（它是 `w:body` 的直接子元素，不在最后一段里面），也不把末尾分节符段落包进 `w:ins`/`w:del`。
7. `w:t` 文本保留 `xml:space="preserve"`，保证首尾空格不丢。

## 适用环境与未验证声明（诚实边界）

- **实测环境**：macOS + WPS。开发、调试、彩虹圈规避清单均来自 macOS 版 WPS 的实测。
- **实测通过（2026-10-14，双平台闭环）**：①macOS + WPS；②Windows 10 Pro 22H2 + WPS Office 12.1.0.29161 个人版——修复版 self_test 一次全绿（Python 3.13.14 / python-docx 1.2.0）；WPS 三点检查：打开【过】、接受/拒绝【过】、修订轨作者与动作可见（时间列不显示，见"已知坑"，判定为窗格显示惯例，不影响验收）；"接受修订"后的 WPS 另存件经 XML 解剖确认：w:ins 归零、插入文本并入正文、行为正确。
- **仍未验证**：Microsoft Word 桌面版、WPS 移动端。设计上应当兼容（输出为标准 OOXML 修订标记、settings 元素顺序符合 ECMA-376、全程不用 `w:del`），用到时按本节三步验收走一遍即可。
- **Windows 首次使用前的三步验收**：
  1. 跑 `scripts/self_test.py` 生成测试件并确认结构校验全绿；
  2. 用 Windows WPS 打开测试件：不卡彩虹圈、修订轨正常显示、作者与日期正确；
  3. 做一次"接受修订 / 拒绝修订"操作无异常。
  任一步失败：本技能产出停用，改人工修订，并把现象记入"已知坑"。
- **兜底底气**：本技能是**插入式修订且原件永不动**（操作步骤第 1 条先复制原件）——最坏情况是显示异常，"拒绝所有修订"或弃用输出文件、重开原件即回到原状，**不存在数据损坏路径**。

## 操作步骤

1. 先把原 `.docx` 复制为新文件名再改（保持原件不动）。
2. 用 python-docx 打开，在 `doc.settings.element` 里启用 `trackChanges` + 补 `rsidRoot`。
3. 对每条修订：定位目标段落和包含边界短语的锚点 **run**。这类文档里所有 run 通常 `style=None`（继承段落字体）——可安全复制或省略 `rPr`。
4. 把新增文字作为 `w:ins` 元素，作为兄弟节点紧插在锚点 run 之后。如果边界短语在 run 中间结束，先在该偏移处拆分 run（把 `rPr` 复制给新的后缀 run，原 run 文本设为前缀），再把 `w:ins` 插在前缀和后缀之间。
5. `doc.save(...)` 后校验（见下）。

- **WPS 个人版修订窗格不显示时间列。** 作者与"插入了内容"动作可见，插入时间默认不展示（Windows 10 + WPS 12.1.0.29161 实测）。验收以"作者+动作+位置可见"为准；需核对时间时读 XML 里的 `w:date`，或测试件把 `w:date` 设为当天当地时刻再人工比对。

## 已知坑

- **锚点短语里藏隐藏字符。** 中文文档常在看似纯文本的地方嵌着 `》（U+300B）`、`「（U+300C）`、`—（U+2014）` 等（如 `《…（2025—2027年）》` 实际以 `年）》。` 结尾）。直接写锚点 `"年），"` 会匹配失败，因为中间藏着 `》`。**构造复杂锚点时用显式 Unicode 转义**（`"年"+"\uFF09"+"\u300B"+"\uFF0C"`），并且/或者先打印候选 run 的 `repr()` 确认精确字符再匹配。
- **python-docx 的 `paragraph.text` 不含 `w:ins` 内容。** 插入后 `paragraph.text` 不会显示新插入的文字（它只拼接直接的 `w:r` 子节点，不含 `w:ins` 里的 run）。要核验插入位置，需解析 `word/document.xml` 并拼接所有后代 `w:t`（含 `w:ins`/`w:del` 之下的）。
- **run 边界**：一个短语常横跨多个 run（如 `"一院一策"` 被拆成 `一院`+`策`）。要锚定在以短语尾部**开头**的 run，或在 run 边界处拆分，不要假设短语在单个 run 里。

## 保存后必做校验

- `zipfile.ZipFile(path).testzip()` 返回 `None`（压缩包完好）；
- `etree.fromstring(z.read('word/document.xml'))` 可解析（XML 合法）；
- `trackChanges` 为 `true`；`rsidRoot` 存在**且位于 `w:rsids` 内**（不得是 `w:settings` 的直接子元素）；settings 子元素顺序符合 schema（`verify()` 已内置断言）；
- `w:ins` 数量符合预期、`w:del` 为 0（只插入模式下）、`w:id` 集合唯一、每个 `w:ins` 都有 author+date+内部 `w:r`；
- 逐个目标段落检查全文（含 `w:ins`）包含插入的关键词。

## 常见问题（FAQ）

- **命令行报"结构校验未通过"**：结构断言失败说明产物 XML 不合法。先跑 `scripts/self_test.py`——它全绿说明环境没问题，问题出在输入文件；再对照「彩虹圈规避清单」逐条排查。校验失败时**不要用原件重试**，另存副本再试。
- **命令行报"不是有效的 .docx 文件"**：扩展名是 .docx 不代表内容是 OOXML（可能是 .doc/.rtf/.wps 改了后缀）。先用 WPS 打开另存为真正的 .docx。
- **WPS 打开产物卡死（彩虹圈）**：99% 是 settings.xml 结构非法（`w:rsidRoot` 位置错误）。本 skill 的 `ensure_child` 已按 schema 顺序插入规避；如果用了旧版脚本或手写 XML，对照本文"正确启用修订"一节检查。
- **WPS 修订窗格里看不到插入时间**：WPS 个人版窗格默认不显示时间列，属显示惯例而非数据缺失。核对时间读 XML 里的 `w:date`，或把测试件的 `w:date` 设为当天当地时刻再比对。
- **找不到锚点短语（apply 无命中）**：锚点必须与正文逐字一致（含全半角标点）。先用工具读出目标段落原文再复制短语，不要手打。

现成的 WPS 安全实现见 `scripts/apply_track_changes.py`，提供 `apply(paragraph_index, anchor_phrase, insert_text)` 辅助函数。
