---
name: docx-track-changes-wps
description: 向 .docx 文档插入真正的"修订模式"（tracked changes / redline）时使用，python-docx + lxml 实现，专为中文公文场景设计——成品必须在 WPS 中干净打开、不触发"彩虹圈/无响应"卡死。涵盖启用 trackChanges、放置 w:ins 插入、规避 WPS 死循环陷阱、保存后校验。触发词：修订模式、插入修订、修改意见标注、发文稿修订、docx 修订、WPS 修订。
---

# docx-track-changes-wps

用 python-docx 加 `lxml` 直接操作 XML，向 Word `.docx` 写入真正的"WPS 安全"修订（tracked changes）。专为**中文公文场景**设计：修改意见报送（如报送"两个工作要点"修改意见）、在发文稿上以"修订模式"标注修改/新增。

## 适用场景

- 用户要求"另存一份原文稿 / 打开修订模式 / 以修订模式把修改意见修订进去"一个 `.docx`；
- 成品必须在 **WPS** 中打开（政府/高校环境最常见），不能卡在彩虹圈无响应；
- 修订类型是"修改完善"或"新增"——即主要是在既有段落上做**插入**。

## 黄金法则：优先 `w:ins`，避免 `w:del`

中文公文修订场景最安全的模式是**只插入**：保留原文 run，把新增文字作为 `w:ins` 元素紧插在锚点 run 之后。尽量不用 `w:del`（删除）——`w:del` + `w:delText` + `w:rPrChange` 是 WPS 彩虹圈卡死的第一大诱因。如果"修改"实际是"在原句后补一句"，就建模为在原句后插入，而不是删除+插入。

## WPS 彩虹圈规避清单（必查）

1. **`w:id` 全文唯一**（用全局计数器，从 10001 这类高位起号，避免与文档既有 id 冲突）。
2. **`w:date` 合法**，ISO 8601 格式，如 `2026-07-23T09:00:00Z`。
3. 每个 `w:ins` 上都要有 **`w:author`**。
4. **正确启用修订**：`word/settings.xml` 里加 `<w:trackChanges w:val="true"/>`，同时加 `<w:rsidRoot w:val="..."/>`（有现成 `w:rsidRDefault` 值就复用，没有就用固定 8 位十六进制）。run 带 `w:rsidR` 而缺 `rsidRoot` 是已知的 WPS 卡死诱因。
5. **插入的 `w:r` 不带 `w:rPr`**（`w:ins` 里就是纯 `<w:r><w:t>...</w:t></w:r>`）。rPr 引用了文档里不存在的字体/样式可能让 WPS 死循环。
6. **绝不碰 body 级 `w:sectPr`**（它是 `w:body` 的直接子元素，不在最后一段里面），也不把末尾分节符段落包进 `w:ins`/`w:del`。
7. `w:t` 文本保留 `xml:space="preserve"`，保证首尾空格不丢。

## 操作步骤

1. 先把原 `.docx` 复制为新文件名再改（保持原件不动）。
2. 用 python-docx 打开，在 `doc.settings.element` 里启用 `trackChanges` + 补 `rsidRoot`。
3. 对每条修订：定位目标段落和包含边界短语的锚点 **run**。这类文档里所有 run 通常 `style=None`（继承段落字体）——可安全复制或省略 `rPr`。
4. 把新增文字作为 `w:ins` 元素，作为兄弟节点紧插在锚点 run 之后。如果边界短语在 run 中间结束，先在该偏移处拆分 run（把 `rPr` 复制给新的后缀 run，原 run 文本设为前缀），再把 `w:ins` 插在前缀和后缀之间。
5. `doc.save(...)` 后校验（见下）。

## 已知坑

- **锚点短语里藏隐藏字符。** 中文文档常在看似纯文本的地方嵌着 `》（U+300B）`、`「（U+300C）`、`—（U+2014）` 等（如 `《…（2025—2027年）》` 实际以 `年）》。` 结尾）。直接写锚点 `"年），"` 会匹配失败，因为中间藏着 `》`。**构造复杂锚点时用显式 Unicode 转义**（`"年"+"\uFF09"+"\u300B"+"\uFF0C"`），并且/或者先打印候选 run 的 `repr()` 确认精确字符再匹配。
- **python-docx 的 `paragraph.text` 不含 `w:ins` 内容。** 插入后 `paragraph.text` 不会显示新插入的文字（它只拼接直接的 `w:r` 子节点，不含 `w:ins` 里的 run）。要核验插入位置，需解析 `word/document.xml` 并拼接所有后代 `w:t`（含 `w:ins`/`w:del` 之下的）。
- **run 边界**：一个短语常横跨多个 run（如 `"一院一策"` 被拆成 `一院`+`策`）。要锚定在以短语尾部**开头**的 run，或在 run 边界处拆分，不要假设短语在单个 run 里。

## 保存后必做校验

- `zipfile.ZipFile(path).testzip()` 返回 `None`（压缩包完好）；
- `etree.fromstring(z.read('word/document.xml'))` 可解析（XML 合法）；
- `trackChanges` 为 `true`；`rsidRoot` 存在；
- `w:ins` 数量符合预期、`w:del` 为 0（只插入模式下）、`w:id` 集合唯一、每个 `w:ins` 都有 author+date+内部 `w:r`；
- 逐个目标段落检查全文（含 `w:ins`）包含插入的关键词。

现成的 WPS 安全实现见 `scripts/apply_track_changes.py`，提供 `apply(paragraph_index, anchor_phrase, insert_text)` 辅助函数。
