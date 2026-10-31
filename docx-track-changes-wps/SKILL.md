---
name: docx-track-changes-wps
version: "1.1.1"
description: 向 .docx 文档写入真正的"修订模式"（tracked changes / redline）与批注（comment）时使用，python-docx + lxml 实现，专为中文公文场景设计——成品必须在 WPS 中干净打开、不触发"彩虹圈/无响应"卡死。涵盖启用 trackChanges、放置 w:ins 插入、w:del 勘误与替换、段内字符偏移插入、插入内容的格式继承（与人工输入观感一致）、批注写入（说明"为什么改"）、导出修订批注清单、规避 WPS 死循环陷阱、保存后校验。触发词：修订模式、插入修订、修改意见标注、发文稿修订、docx 修订、WPS 修订、勘误、改错字、修订格式不匹配、批注、修改意见清单。
---

# docx-track-changes-wps

用 python-docx 加 `lxml` 直接操作 XML，向 Word `.docx` 写入真正的"WPS 安全"修订（tracked changes）。专为**中文公文场景**设计：修改意见报送（如报送规划、要点类文件的修改意见）、在发文稿上以"修订模式"标注修改/新增。

## 适用场景

- 用户要求"另存一份原文稿 / 打开修订模式 / 以修订模式把修改意见修订进去"一个 `.docx`；
- 成品必须在 **WPS** 中打开（政府/高校环境最常见），不能卡在彩虹圈无响应；
- 修订类型是"修改完善"或"新增"——即主要是在既有段落上做**插入**；
- **含勘误的修订**（改错字、删多余字词、改已在文本中间的日期/数字）——用 `w:del` + `w:ins`（见下节）。

## 黄金法则：能用插入就不用删除；确需勘误就用规范的 w:del

中文公文修订场景最安全的模式是**只插入**：保留原文 run，把新增文字作为 `w:ins` 元素紧插在锚点 run 之后。如果"修改"实际是"在原句后补一句"，就建模为在原句后插入，而不是删除+插入。

**但"避免 w:del"不等于"禁用 w:del"**（1.1.0 更正旧表述）。彩虹圈卡死的真正成因是**结构非法**——id 撞号、缺 author/date、run 带新 rPr、误碰 body 级 sectPr——**不是 w:del 本身**。有些修改**无法用插入表达**：

- 改错字（"发辉" → "发挥"）：不删掉错字、只插入正确的，审阅者看到的是"辉发挥"；
- 删多余字词（"其它" → "其他"）、删漏字（"发展咨询委员相关" → "发展咨询委员会相关"）；
- 改年份、日期、电话等**已在文本中间**的数字。

这些场景**必须用 w:del**（删除旧文）+ 可选 w:ins（插入新文）。硬把勘误建模成"只插入"，是把技术风险转成内容错误——**那才是真错误**。1.1.0 起本技能提供 `apply_del()` / `del_insert()` 专门做这件事，并已用真实公文在 WPS 中实测通过（2026-10-30）。

## WPS 彩虹圈规避清单（必查）

1. **`w:id` 全文唯一**（计数器起号取 max(10000, 文档既有 `w:ins`/`w:del` id 最大值)——固定 10001 起号在自带修订史的稿件上必然撞号，Windows 侧 2026-10-14 实测复现；实现见 `_max_revision_id`，附两轮插入-重开回归测试）。
2. **`w:date` 合法**，ISO 8601 格式，如 `2026-07-23T09:00:00Z`。
3. 每个 `w:ins` 上都要有 **`w:author`**。
4. **正确启用修订**：`word/settings.xml` 里加 `<w:trackChanges w:val="true"/>`；`<w:rsidRoot w:val="..."/>` **必须放在 `w:rsids` 元素内部**（`w:rsidRoot`/`w:rsidRDefault` 都不是 `w:settings` 的直接子元素——用 `settings.find()` 找不到就会误判缺失而重复追加非法元素，这是实测踩过的坑）。新增元素的插入位置要符合 CT_Settings 顺序：`trackChanges` 在 `defaultTabStop` 之前、`rsids` 在 `mathPr`/`themeFontLang` 之前。run 带 `w:rsidR` 而缺 `rsidRoot` 是已知的 WPS 卡死诱因。
5. **插入的 `w:r` 不得凭空造 `w:rPr`，但必须继承锚点已有的 `w:rPr`**（1.1.0 更正）。两者不矛盾，区别在"造"与"复制"：
   - **不要凭空造**：`w:rPr` 里引用文档中不存在的字体/样式（如硬写一个 `w:rFonts` 指向未安装字体）可能让 WPS 死循环；
   - **必须复制锚点已有的**：公文正文普遍用直接格式（实测：标题方正小标宋_GBK 三号、正文仿宋_GB2312 三号、节标题黑体三号），**不继承格式 → 插入的文字掉回文档默认字体，与人工在 Word 里输入的观感不一致**（1.1.0 修掉的缺陷）。
   - 判定口径：**`w:rPr` 要么来自锚点 run／段落标记（复制真实存在的），要么干脆没有（继承段落样式）**——不允许出现"第三种"：手工拼出来的 rPr。
6. **绝不碰 body 级 `w:sectPr`**（它是 `w:body` 的直接子元素，不在最后一段里面），也不把末尾分节符段落包进 `w:ins`/`w:del`。
7. `w:t` 文本保留 `xml:space="preserve"`，保证首尾空格不丢。

## 勘误与替换（w:del + w:ins，1.1.0 新增）

`scripts/apply_track_changes.py` 现提供四个接口，前两个是插入、后两个是勘误：

| 接口 | 用途 | 参数 |
|---|---|---|
| `apply(doc, counter, author, date, p_idx, phrase, text)` | 在锚点短语**后**插入 | 纯插入 |
| `split_insert(run, off, text, counter, author, date)` | 在 run 内部**字符偏移**处插入 | 纯插入 |
| `apply_del(doc, counter, author, date, p_idx, phrase, replacement)` | 按锚点短语**删旧+换新** | 勘误，`replacement=""` 即纯删除 |
| `del_insert(run, off, length, text, counter, author, date)` | 删 run 内 `[off, off+length)` 区间并可插入新文 | 勘误（精确到字符） |

**w:del 的硬规矩**（违反即彩虹圈）：

- `w:del` 内必须是 `w:delText`，**不能残留 `w:t`**——残留会被 Word/WPS 当成未删内容；`make_del()` 已自动转换，`verify()` 已自动断言；
- `w:del` 与 `w:ins` **共用同一个 id 空间**，id 必须**合起来**唯一（只查 ins 会漏掉 del 与 ins 撞号）；
- `w:del` 同样必须带 `w:author` 与 `w:date`；
- 被删 run **保留原 `w:rPr`**（格式要跟着删除线一起走），**不要重新造 rPr**。

**例子**：把"2005年11月18日"的年份改掉——原文里年份是一个独立 run，直接区间替换：

```python
r0 = doc.paragraphs[8].runs[0]        # '2005'
del_insert(r0, 0, 4, "2006", counter, author, date)
```

生成的结构（真实产物）：

```xml
<w:del w:id="10001" w:author="审校" w:date="2026-10-30T10:00:00Z">
  <w:r><w:rPr><w:rFonts w:ascii="仿宋_GB2312" w:eastAsia="仿宋_GB2312"/><w:sz w:val="32"/></w:rPr><w:delText xml:space="preserve">2005</w:delText></w:r>
</w:del>
<w:ins w:id="10002" w:author="审校" w:date="2026-10-30T10:00:00Z">
  <w:r><w:rPr><w:rFonts w:ascii="仿宋_GB2312" w:eastAsia="仿宋_GB2312"/><w:sz w:val="32"/></w:rPr><w:t xml:space="preserve">2006</w:t></w:r>
</w:ins>
```

（两处的 `w:rPr` 都是**从被替换的 run 复制**的——删除线上的字与替换后的新字同格式。1.1.0 之前的产物里 `w:ins` 内不带 `w:rPr`，那正是本版修掉的格式缺陷。）

**2026-10-30 实测**：对一份 35 段真实公文（`关于建议撤销……的报告`）同时施加"年份区间替换 + 锚点短语替换 + 纯插入 + 段内偏移插入"四种操作，产物 WPS 打开正常、修订窗格可见删除线与插入标记、无彩虹圈；`w:ins=4 / w:del=2 / id 全部唯一 / w:del 内无残留 w:t` 全部断言通过。

## 格式继承（1.1.0 新增）

**现象**：脚本插入的文字与正文**字体/字号明显不一致**——像换了个人打的字。人工在 Word/WPS 里输入会自动继承插入点的当前格式，脚本不会。

**根因**：1.1.0 之前的 `make_ins()` 造的 `<w:r>` **不带 `w:rPr`**。正文 run 普遍带直接格式（不是靠段落样式），所以插入的 run 落回文档默认字体。**不是显示问题，是 XML 少了一层。**

**修复**：新增 `_rpr_for(r_el, p_el)` 作为格式继承的唯一入口，取值优先级——

| 优先级 | 来源 | 何时命中 |
|---|---|---|
| ① | 该 run 自身的 `w:rPr` | 正文带直接格式（公文常态：仿宋_GB2312 三号） |
| ② | 段落标记的 `w:rPr`（`w:pPr/w:rPr`） | run 不带直接格式、靠段落排版 |
| ③ | 都没有 → 不带 `w:rPr` | 新 run 自动继承段落样式（正确行为，不是缺陷） |

三个接口的继承规则：

| 接口 | 插入内容的格式取自 |
|---|---|
| `apply()` | 锚点 run（短语所在的那个 run） |
| `split_insert()` | 被拆开的那个 run |
| `del_insert()` 的替换文字 | **被替换文字**（人工改字时新字随原字格式） |

**继承来的 `w:rPr` 必须剔除 `w:rPrChange`**——那是格式修订标记，复制过来会形成嵌套格式修订，Word/WPS 可能拒开文件（与彩虹圈同源的结构性风险）。`_rpr_for()` 已自动处理。

**实测 A/B（真实公文，35 段，`关于建议撤销……的报告`）**：

| | 插入 run 的格式 |
|---|---|
| 修复前 | **无 `w:rPr`** → 掉回文档默认字体 |
| 修复后 | `fonts=仿宋_GB2312 / eastAsia=仿宋_GB2312 / sz=32` —— 与同段正文 run **完全一致** |

自检新增场景 E（四个子项：常规插入 / 段内偏移插入 / 勘误替换 / `w:rPrChange` 剔除），并给 `verify()` 加了 `check_fmt=True` 开关：断言插入 run 与其前一个普通 run 的格式指纹一致。

## 批注（w:comment，1.1.0 新增）

**为什么需要**：真实审校流程里，修订标记与批注是**两套并行**的——

- 修订标记（`w:ins`/`w:del`）：把字改了，Word/WPS 的修订轨能看到；
- 批注（`w:comment`）：把**为什么改**写在旁边。

人工在 WPS 里审校时两者并用（典型形态："删除：2005"、"审核：2026-10-30"、"（复核：2026-10-30）"）。本技能此前只支持修订标记，批注要手工补——补不齐就退回到"只改字、不说理由"，修改意见报送场景不成立。

**批注要动四个地方，缺一个 Word/WPS 就打不开或看不到批注**：

| # | 位置 | 内容 |
|---|---|---|
| ① | `word/comments.xml`（**新部件**） | 批注正文：`w:comment` 带 id/author/date |
| ② | `[Content_Types].xml` | 登记该部件的 ContentType |
| ③ | `word/_rels/document.xml.rels` | 登记关系（指向 `comments.xml`） |
| ④ | `word/document.xml` | 锚点：`commentRangeStart` → 内容 → `commentRangeEnd` → `commentReference` |

库版本 python-docx 1.2.0 没有内置 comments part 支持，因此 ①②③ 采用**保存后 zip 后处理**（比手工构造 Part/Relationship 对象稳，也不会被 python-docx 的保存流程丢掉）。

**接口**（`scripts/add_comment.py`）：

```python
from add_comment import add_comment, save_with_comments

doc, counter, author, date = open_for_revision(src, author, date_iso)
apply_del(doc, counter, author, date, 8, "科学发展观", "新发展理念")     # 改字
add_comment(doc, 8, "新发展理念", "该表述已过时，按新发展理念修改", author, date,
            anchor_phrase="科学发展观")                                  # 批注锚到被删的那段
save_with_comments(doc, out)          # 保存 + 注入批注
```

| 参数 | 含义 |
|---|---|
| `p_idx` | 段落序号（0 起，与 `doc.paragraphs` 一致） |
| `phrase` | 批注**锚定到哪段文字**（决定批注挂在谁身上） |
| `text` | 批注内容（"为什么这么改"） |
| `anchor_phrase` | 可选：把批注锚到**另一处**——通常是"被删掉的那段字" |

命令行对应：**CLI: `--phrase` / `--anchor`，API: `phrase` / `anchor_phrase`**。`--phrase`（挂载锚点）必填，不传报错；`--anchor`（另锚）可选。

**锚定规则**：

- 锚点落在**普通 run** 上 → 切分 run，批注**只覆盖该短语**（同人工选中一段加批注）；
- 锚点落在 `w:ins`/`w:del` **内部** → **不切分**（切了会破坏修订结构），批注范围包住整个修订标记；
- 查找锚点**穿透 `w:ins`/`w:del`**——`paragraph.runs` 只返回直系 `w:r`，修订标记里的文字用它找不到，而"给某处删除写批注"恰恰是最常见用法。

**两条硬规矩**：

1. `commentReference` 必须排在其 `commentRangeEnd` **之后**（写反了 WPS 显示不出批注——1.1.0 实战踩到）；
2. 批注 id 从 1 起递增，且 `comments.xml` 的 id 与正文锚点三方（start/end/reference）必须完全一致。

**校验**：`verify(path, check_comments=True)` 会逐项断言——部件存在、Content_Types 已登记、rels 已登记、每个批注有 id/author/date/正文、三方 id 配对、reference 顺序正确。

**导出清单**（`scripts/export_markup.py`，纯读取不改文件）：

```bash
python3 scripts/export_markup.py 产物.docx -o 修改意见清单.md
```

产出两张表：**修订标记表**（段落／插入或删除／内容／作者／日期）与**批注表**（段落／锚定文字／批注内容／作者／日期）。这正是"修改意见报送"要交的那份清单。加 `--json` 可程序化消费。

## 适用环境与未验证声明（诚实边界）

- **实测环境**：macOS + WPS。开发、调试、彩虹圈规避清单均来自 macOS 版 WPS 的实测。
- **实测通过（2026-10-14，双平台闭环）**：①macOS + WPS；②Windows 10 Pro 22H2 + WPS Office 12.1.0.29161 个人版——修复版 self_test 一次全绿（Python 3.13.14 / python-docx 1.2.0）；WPS 三点检查：打开【过】、接受/拒绝【过】、修订轨作者与动作可见（时间列不显示，见"已知坑"，判定为窗格显示惯例，不影响验收）；"接受修订"后的 WPS 另存件经 XML 解剖确认：w:ins 归零、插入文本并入正文、行为正确。
- **仍未验证**：Microsoft Word 桌面版、WPS 移动端。设计上应当兼容（输出为标准 OOXML 修订标记、settings 元素顺序符合 ECMA-376、纯插入场景不用 `w:del`，勘误场景见「勘误与替换」节），用到时按本节三步验收走一遍即可。
- **Windows 首次使用前的三步验收**：
  1. 跑 `scripts/self_test.py` 生成测试件并确认结构校验全绿；
  2. 用 Windows WPS 打开测试件：不卡彩虹圈、修订轨正常显示、作者与日期正确；
  3. 做一次"接受修订 / 拒绝修订"操作无异常。
  任一步失败：本技能产出停用，改人工修订，并把现象记入"已知坑"。
- **兜底底气**：本技能是**插入式修订且原件永不动**（操作步骤第 1 条先复制原件）——最坏情况是显示异常，"拒绝所有修订"或弃用输出文件、重开原件即回到原状，**不存在数据损坏路径**。

## 操作步骤

1. 先把原 `.docx` 复制为新文件名再改（保持原件不动）。
2. 用 python-docx 打开，在 `doc.settings.element` 里启用 `trackChanges` + 补 `rsidRoot`。
3. 对每条修订：定位目标段落和包含边界短语的锚点 **run**，并记下它的 `w:rPr`——插入内容要继承它（见「格式继承」）。注意公文 run 虽 `style=None`，但**往往带直接格式**（字体/字号写在 run 上），不能因为 `style=None` 就以为无需继承。
4. 把新增文字作为 `w:ins` 元素，作为兄弟节点紧插在锚点 run 之后。如果边界短语在 run 中间结束，先在该偏移处拆分 run（把 `rPr` 复制给新的后缀 run，原 run 文本设为前缀），再把 `w:ins` 插在前缀和后缀之间。
5. `doc.save(...)` 后校验（见下）。

- **WPS 个人版修订窗格不显示时间列。** 作者与"插入了内容"动作可见，插入时间默认不展示（Windows 10 + WPS 12.1.0.29161 实测）。验收以"作者+动作+位置可见"为准；需核对时间时读 XML 里的 `w:date`，或测试件把 `w:date` 设为当天当地时刻再人工比对。

**命令行直接改**（1.1.1 起）：

    python3 scripts/apply_track_changes.py 原件.docx 输出.docx --p-idx 5 --phrase "原句尾部。" --text "（新增内容）"
    python3 scripts/apply_track_changes.py 原件.docx 输出.docx --p-idx 8 --phrase "发辉" --text "发挥" --del

不给操作参数时只保存并校验（stdout 明示"未修改正文"）；参数不齐退 1。

## 已知坑

- **锚点短语里藏隐藏字符。** 中文文档常在看似纯文本的地方嵌着 `》（U+300B）`、`「（U+300C）`、`—（U+2014）` 等（如 `《…（2025—2027年）》` 实际以 `年）》。` 结尾）。直接写锚点 `"年），"` 会匹配失败，因为中间藏着 `》`。**构造复杂锚点时用显式 Unicode 转义**（`"年"+"\uFF09"+"\u300B"+"\uFF0C"`），并且/或者先打印候选 run 的 `repr()` 确认精确字符再匹配。
- **python-docx 的 `paragraph.text` 不含 `w:ins` 内容。** 插入后 `paragraph.text` 不会显示新插入的文字（它只拼接直接的 `w:r` 子节点，不含 `w:ins` 里的 run）。要核验插入位置，需解析 `word/document.xml` 并拼接所有后代 `w:t`（含 `w:ins`/`w:del` 之下的）。
- **run 边界**：一个短语常横跨多个 run（如 `"一院一策"` 被拆成 `一院`+`策`）。要锚定在以短语尾部**开头**的 run，或在 run 边界处拆分，不要假设短语在单个 run 里。
- **w:del 会让 `paragraph.runs` 索引左移（1.1.0 实战踩到）**：`w:del` 里的 run 不再是段落的**直系** `w:r` 子节点，而 `paragraph.runs` 只返回直系子节点。所以一旦某个 run 被包进 `w:del`，**它后面的 run 索引全部减 1**。对策：**先捕获 run 对象再操作**，不要用 `doc.paragraphs[i].runs[j]` 在改动后重新按序号取；或每步改完都重新按短语定位。
- **`w:del` 内残留 `w:t` = 删除没生效**：删除标记里的文本必须是 `w:delText`。手写 XML 时最容易漏这一处转换，表现是"接受修订后旧字还在"。`make_del()` 自动处理，`verify()` 自动断言，别手改。
- **插入内容格式与正文不一致（1.1.0 实战踩到）**：脚本插入的文字掉回文档默认字体，一眼能看出"不是同一个人打的字"——与人工在 Word 里输入的观感不符。根因是插入的 `w:r` 缺 `w:rPr`（旧版 `make_ins()` 不带 rPr）。对策：`make_ins()` 现已继承锚点 rPr（`_rpr_for()`）；若你手写 XML 或用了旧版脚本，务必把锚点 run 的 `w:rPr` 复制进 `w:ins` 内的 `w:r`，且放在 `w:t` **之前**（schema 要求 rPr 在前）。
- **继承来的 `w:rPr` 里带 `w:rPrChange` 会让文件打不开**：`w:rPrChange` 是格式修订标记，复制过来会形成嵌套修订，Word/WPS 可能拒开。`_rpr_for()` 已自动剔除，手写时也要删。
- **批注找不到锚点，多半是锚点在修订标记里**（1.1.0 实战踩到）：`paragraph.runs` 只返回段落的**直系** `w:r`，`w:ins`/`w:del` 里的 run 它看不到。而"给某处删除写批注"是最常见用法——必然落在 `w:del` 里。对策：`add_comment()` 直接在段落 XML 树上找（穿透 `w:ins`/`w:del`），并自动把批注范围包住整个修订标记；手写锚点时同理。
- **`commentReference` 排在了 `commentRangeEnd` 前面**（1.1.0 实战踩到）：顺序必须是 `start → 内容 → end → reference`。写反了文件能打开、WPS 却不显示批注，排查时容易误判成"批注没写进去"。`verify(check_comments=True)` 已断言顺序。

## 保存后必做校验

- `zipfile.ZipFile(path).testzip()` 返回 `None`（压缩包完好）；
- `etree.fromstring(z.read('word/document.xml'))` 可解析（XML 合法）；
- `trackChanges` 为 `true`；`rsidRoot` 存在**且位于 `w:rsids` 内**（不得是 `w:settings` 的直接子元素）；settings 子元素顺序符合 schema（`verify()` 已内置断言）；
- `w:ins` 数量符合预期；`w:del` 在**纯插入模式下应为 0**、在**勘误模式下应为预期数**（`verify(path, expect_ins=N, expect_del=M)` 可直接断言）；
- **`w:ins` 与 `w:del` 合起来的 `w:id` 集合唯一**（1.1.0 起 `verify()` 已改为合查）——id 撞号是彩虹圈卡死首因；
- 每个 `w:ins`/`w:del` 都有 author+date+内部 `w:r`；**`w:del` 内不得有 `w:t`，必须有 `w:delText`**；
- **插入的 `w:ins` 内 run 继承了锚点的 `w:rPr`**（格式与正文一致）：`verify(path, check_fmt=True)` 已内置断言；人工核对时看**字体与字号**是否与同段正文相同，不必看修订颜色（颜色是渲染层加的）；`w:rPr` 必须是 `w:r` 的第一个子元素，且不得含 `w:rPrChange`；
- **产物里有批注时**：`verify(path, check_comments=True)` 已内置断言——`word/comments.xml` 存在、`[Content_Types].xml` 与 `word/_rels/document.xml.rels` 均已登记、每个批注有 id/author/date/正文、三方 id（start/end/reference）配对、`commentReference` 排在 `commentRangeEnd` 之后；
- 逐个目标段落检查全文（含 `w:ins`）包含插入的关键词；勘误处另需确认**删除标记确实存在**（不能只看正文，因为被删文字不在 `paragraph.text` 里）。

## 样例：一次插入前后的 XML（真实产物）

**插入前**——正文只有一个 run：

```xml
<w:p>
  <w:r>
    <w:t>本方案的实施路径分为三步。</w:t>
  </w:r>
</w:p>
```

**插入后**——原文 run 原样保留，新内容包在 `<w:ins>` 里（带 author/date，`w:id` 不撞既有修订），正文文本零改动：

```xml
<w:p>
  <w:r>
    <w:t>本方案的实施路径分为三步。</w:t>
  </w:r>
  <w:ins w:id="10001" w:author="审校" w:date="2026-10-15T09:00:00Z">
    <w:r>
      <w:rPr><w:rFonts w:ascii="仿宋_GB2312" w:eastAsia="仿宋_GB2312"/><w:sz w:val="32"/></w:rPr>
      <w:t xml:space="preserve">（试点先行，分步推开）</w:t>
    </w:r>
  </w:ins>
</w:p>
```

要点：`w:ins` 位于 `w:p` 直下、紧跟原 run；`w:rPr` 是**从锚点 run 复制**的（1.1.0 起，插入内容与正文同格式），锚点本身无直接格式时这里就不出现 `w:rPr`；真实 XML 中 `w:p` 还带一串 xmlns 声明（此处省略不影响理解）。WPS 打开后显示"审校 插入了内容"，点"拒绝修订"即回到原文。

## 常见问题（FAQ）

- **命令行报"结构校验未通过"**：结构断言失败说明产物 XML 不合法。先跑 `scripts/self_test.py`——它全绿说明环境没问题，问题出在输入文件；再对照「彩虹圈规避清单」逐条排查。校验失败时**不要用原件重试**，另存副本再试。
- **命令行报"不是有效的 .docx 文件"**：扩展名是 .docx 不代表内容是 OOXML（可能是 .doc/.rtf/.wps 改了后缀）。先用 WPS 打开另存为真正的 .docx。
- **WPS 打开产物卡死（彩虹圈）**：99% 是 settings.xml 结构非法（`w:rsidRoot` 位置错误）。本 skill 的 `ensure_child` 已按 schema 顺序插入规避；如果用了旧版脚本或手写 XML，对照本文"正确启用修订"一节检查。
- **WPS 修订窗格里看不到插入时间**：WPS 个人版窗格默认不显示时间列，属显示惯例而非数据缺失。核对时间读 XML 里的 `w:date`，或把测试件的 `w:date` 设为当天当地时刻再比对。
- **找不到锚点短语（apply 无命中）**：锚点必须与正文逐字一致（含全半角标点）。先用工具读出目标段落原文再复制短语，不要手打。
- **要改一个错字，改不了**：用 `apply_del(doc, counter, author, date, p_idx, "发辉", "发挥")`，不要试图用 `apply` 在旁边再插一个字——那会让正文变成"发辉发挥"。
- **改了多处后编号乱了**：因为 `w:del` 会让 `paragraph.runs` 索引左移（见「已知坑」）。**先捕获 run 对象再改**，或每步按短语重新定位，不要按序号。
- **插入的字看着和正文不是一套字体**：见「格式继承」一节。用 1.1.0 以上的脚本（插入内容自动继承锚点 rPr）；若用的是旧版脚本或手写 XML，把锚点 run 的 `w:rPr` 复制进 `w:ins` 内的 `w:r`，并放在 `w:t` 之前。
- **批注在 WPS 里看不见**：①确认 `commentReference` 排在 `commentRangeEnd` **之后**；②确认 `comments.xml` 已在 `[Content_Types].xml` 与 `word/_rels/document.xml.rels` 两处登记（缺任一个，Word 会打不开或静默丢弃批注）；③确认批注正文非空。跑 `verify(path, check_comments=True)` 一遍即可定位。
- **要给"某处删除"配一句批注，锚点找不到**：锚点在 `w:del` 里，`paragraph.runs` 看不到它。用 `add_comment()`（自动穿透 `w:ins`/`w:del` 并把批注范围包住整个修订标记），或手写时把 `commentRangeStart`/`End` 放在 `w:del` 元素**前后**。

现成的 WPS 安全实现见 `scripts/apply_track_changes.py`，提供 `apply(paragraph_index, anchor_phrase, insert_text)` 辅助函数。

---

> 📦 **获取最新版**：https://github.com/nannanpa/agent-skills/releases —— 本技能在 GitHub 与 SkillHub **同号发布**，Release 附件可下载任意历史版本。
