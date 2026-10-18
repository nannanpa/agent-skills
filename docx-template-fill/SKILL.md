---
name: docx-template-fill
description: 【仅限 WorkBuddy】通过本地编辑器（内置 skill tencent-local-office-edit 的 edsdk）填报/修改 docx 模板的安全工作流。固化了三个实战坑的规避方法：加密保存坏文件、未等待打开导致操作落空、文件被占用时改动被旧版覆盖。触发词：edsdk、doc_insert_text、doc_replace_text、tencent-local-office-edit、WorkBuddy 填报 docx 模板、保存 docx 失败。
---

# docx-template-fill：模板填报安全工作流

**⚠️ 平台归属与前置条件（先看这条）**：本技能**仅限 WorkBuddy 环境使用**——全部命令依赖 WorkBuddy 运行时的本地编辑器服务（editor_sdk，由 `edsdk.py` 封装，自动探测 127.0.0.1:39099–39108 端口）。其他平台（Claude Code 等）**没有这个服务，本技能一步都跑不了**。若在本技能所属宿主之外调用：第 1 步 `open_file` 就会连接失败，此时请回到 WorkBuddy 环境使用，不要尝试改造本流程。

配合内置 skill `tencent-local-office-edit` 的 `edsdk.py` 使用，填报上级模板（如"××方案（部门填报）"）、往既有 Word 文档插内容。**本 skill 是流程纪律，不是新工具**——工具都来自 edsdk，这里固化的是"怎么用不出事"。

## 适用环境与未验证声明（诚实边界）

- **实测环境**：WorkBuddy（macOS）+ 本地编辑器服务 editor_sdk（端口 39099–39108），`edsdk.py` 为该服务的 HTTP 封装。
- **Windows 已实测**（2026-10-18，Windows 10 19045 + PowerShell 5.1 + Python 3.13 venv，editor_sdk 同样监听 39099）：7 步流程、终验脚本、替代命令全部跑通；平台差异见"Windows 环境对照"与三坑表注记。
- **仍未验证**：其他 agent 平台不可用（无本地编辑器服务）。
- **三坑的真实发生率**来自作者实战记录，无法离线复现；CDFV2 的"加密"表述系按现象描述（文件表现为 OLE2 复合容器、编辑器无法重开），精确机制未独立验证。

## 首次使用：最小路径（30 秒上手）

本技能**没有独立工具**——填报动作由 WorkBuddy 内置编辑器完成，这里固化的是流程纪律。你只需要三样东西：

1. **上级模板**（如"××方案（部门填报）".docx）
2. **要填的内容**（本单位对应的措施/意见文本）
3. WorkBuddy 环境（macOS，本地编辑器服务随运行时自带）

然后把任务直接交给 WorkBuddy："按 docx-template-fill 流程，把这份模板填报本单位内容"——执行体按 7 步走，最后一步终验脚本把关。Windows 环境看[命令对照表](#windows-环境对照)；不确定能不能用，看[常见问题](#常见问题faq)。

## 为什么需要这个 skill（三个实战坑）

| 坑 | 后果 | 规避 |
|---|---|---|
| save_file 直存原路径 | **macOS 侧坑**：可能写成加密 CDFV2 格式，连编辑器自己都无法重新打开，只能重建。Windows 实测未复现（直存正常） | **永远存到临时路径**，关闭后 mv/move 覆盖——Windows 下 move 可能因占用失败，见坑三注记 |
| open_file 不等待 | 后续 doc_find 全部落空、看似空文档。Windows 小文件实测可能侥幸命中——**不可依赖** | open_file 必须带 `--json '{"wait":true}'` |
| 文件被预览占用后重开编辑器 | 编辑器从磁盘载回旧版，改动被静默冲掉。**Windows 同样掉坑且更隐蔽**：占用时 Move-Item 覆盖失败，若用 `;` 串联，失败被吞掉→静默丢改动 | 改完立即走"存tmp→close→mv/move"，不重开；**Windows 覆盖后必须验证退出状态** |

## 标准流程（7 步，一步不省）

设 `ED` 为 edsdk.py 完整路径，`TMP` 为同目录临时文件。**`F` 必须是"另存出来的填报版"路径，绝不是上级模板原件**——第 7 步的 `mv -f` 会覆盖 `F`，把原件设为 `F` 等于直接覆盖上级模板（不可逆）。纪律第 1 条"原件只读"落实在 F 的定义上：

```
1. 打开（阻塞）   $ED call open_file file_path="$F" --json '{"wait":true}'
2. 定位           $ED call doc_find file_id="$F" --json '{"text":"锚点文本"}'
                  → 拿到 idx/ranges；全文检索确认涉及哪些位置，别漏简称写法
3. 修改           doc_insert_text（填空位）或 doc_replace_text（带 ranges）
                  → 先改靠后的位置再改靠前的，避免坐标漂移
4. 回读校验       doc_find 逐条确认：新内容在、旧内容清零、无关部分未动
5. 存临时路径     $ED call save_file file_id="$F" file_path="$TMP"
6. 关闭           $ED call close_file file_id="$F"
7. 覆盖+终验      mv -f "$TMP" "$F" 后，用 zipfile 解包逐项验证（见下）
```

## 第 7 步终验（必跑，最后一道防线——不过即非零退出，必须停下排查）

**两种跑法任选**：① 用打包自带的脚本（推荐，支持多检查项）：

```bash
python3 scripts/final_check.py --target "$F" --must "关键新句" --banned "学位授权点" --gone "被删旧句"
```

② 内联版（等价逻辑，四处字面量换成实际内容）：

```python
import sys, zipfile, re

# ↓↓↓ 四处字面量必须换成你的实际内容，直接粘贴原样跑必失败（这是特性不是缺陷）
TARGET = '目标.docx'       # ← 换成 F（填报版路径）
NEW = '关键新句'           # ← 换成本次插入的新内容
OLD = '被删/被改的旧句'    # ← 换成被删/被改的旧内容
BANNED = '禁用词'          # ← 换成需清零的禁用词（如'学位授权点'）

with zipfile.ZipFile(TARGET) as z:
    xml = z.read('word/document.xml').decode('utf-8')
text = re.sub(r'<[^>]+>', '', xml)

checks = [
    ('新内容在', NEW in text),
    ('旧内容清零', text.count(OLD) == 0),
    ('术语合规', text.count(BANNED) == 0),
]
for name, ok in checks:
    print(('✓' if ok else '✗'), name)
failed = [name for name, ok in checks if not ok]
if failed:
    sys.exit(f'终验未通过：{", ".join(failed)} —— ✗ 项即为问题所在，勿交付')
print('终验通过')
```

**mv 前的临时文件是唯一最新版本**——覆盖目标前确认 `$TMP` 和 `$F` 是同一份工作的产物；如不放心，先 `cp "$F" "$F.bak-时间戳"` 再 mv。

## 操作纪律

1. **模板原件不动**：填报类任务一律"打开模板→另存为填报版"，绝不覆盖上级模板
2. **先查后写**：插入前用 doc_find 把模板里所有相关空位/责任部门行摸全（全称+简称都搜），避免漏填或填错位置
3. **插入内容与方面级已有描述不重复**：先读空位前后的正文，自己的条目从部门职责角度切入
4. **坐标漂移**：多处修改时从文档尾部往前改
5. **保存失败（文件占用）**：不要反复重试 save 到原路径——直接换 `$TMP`，走第 5-7 步
6. **发现目标文件已是 CDFV2 加密格式**（`file` 命令显示 CDFV2 而非 Microsoft Word 2007+。`file` 为 POSIX 工具，Windows 下可改用 `certutil -dump 文件名` 看是否为 OLE2 复合文档，或直接以"编辑器能否打开"判定）：编辑器通道读不了，若内容有完整记录则从干净模板重建，坏文件移出备份
7. **open→改→存→关必须在同一条命令链里执行**（`&&` 串联）：编辑器会话不保证跨 Bash 调用存活，跨命令续操作会报 "document is not open"；且报错回显可能滞后——**一切以 mv 后的 zip 解包终验为准**，报错后不要凭输出猜状态，先解包看内容再说。**Windows 分支**：PS 5.1 不认 `&&`（整行 parse error），改用 `;` 时 move 等关键步骤后必须验证退出状态（`;` 不短路，失败会静默继续）
8. **mv 前确认 `$TMP` 是本次产物**（`ls -la` 看时间戳）：目录里可能残留旧临时文件，盲目 `mv -f` 会把不知道哪个版本的文件盖到目标上

## 异常分级诊断（出了问题先对号，再动手）

| 现象 | 根因（按概率排序） | 处置 |
|---|---|---|
| 第 1 步 open 连接失败 | ①不在 WorkBuddy 环境 ②编辑器服务未起 | 回 WorkBuddy；确认 39099–39108 端口有监听 |
| 报 "document is not open" | open/改/存跨了多条 Bash 命令 | 按纪律 7：open→改→存→关 `&&` 串联一次跑完 |
| doc_find 全部落空 | open 没带 `--json '{"wait":true}'`，文档还没开完 | 补 wait 重开；确认 idx 有效再改 |
| save_file 报文件被占用 | 预览窗口占着文件 | 关预览；直接换 `$TMP` 走第 5–7 步，别重试原路径 |
| 终验 ✗ 新内容不在 | 插入没落盘，或被预览旧版覆盖 | 先 `close` 全部句柄再重开确认；重做插入→保存→终验 |
| 终验 ✗ 旧内容未清零 | doc_replace 的 ranges 没对准（坐标漂移） | 重跑 doc_find 拿新 ranges，从后往前再替换 |
| 打开报错/文件打不开，`file` 显示 CDFV2 | 保存环节写坏（三坑之一） | 编辑器读不了；有记录就从干净模板重建，坏文件移出备份 |
| mv 后模板原件"变了" | F 定义错了（把原件当 F） | **不可逆**。教训：F 必须是另存出的填报版；平时留 `.bak-时间戳` 可救 |
| **Windows** move 报"当文件已存在时，无法创建该文件" | 目标被占用（预览/杀毒/索引） | 释放占用后重试 Move-Item；**禁止用 `;` 把 move 和后续步骤串一起**（失败被吞＝静默丢改动） |
| **Windows** 整条命令报 parse error（"&&"不是有效语句分隔符） | PS 5.1 不支持 `&&` | 改用 `;`（不短路）或装 PowerShell 7；注意 parse error 时**整行都不执行** |
| **Windows** doc_find_and_replace 报 -32603 missing required param | 参数名写错：是 `old_text`/`new_text`，不是 `text` | 按 schema（`$ED schema doc_find_and_replace`）核对参数名 |

每格处置动作在上文都有对应纪律条目——先对号，再跳转，不要凭输出猜状态。

## Windows 环境对照（已实测 2026-10-18）

实测环境：Windows 10 19045 + PowerShell 5.1.19041 + Python 3.13，editor_sdk 同样监听 39099。**7 步流程、终验脚本、下表替代命令全部跑通。**

| 用途 | macOS（本技能默认） | Windows 替代（✓ 已实测） |
|---|---|---|
| 判定文件是否 CDFV2/OLE2 加密 | `file 目标.docx` | `certutil -dump 目标.docx`——正常 docx 首行是 zip 头 `50 4b 03 04`（PK），OLE2 加密文件无 PK 头，可据此区分 |
| 临时文件覆盖目标 | `mv -f "$TMP" "$F"` | `Move-Item -Force %TMP% %F%`——⚠️ **文件被占用时会失败**，失败若被 `;` 吞掉＝静默丢改动（实测坑三），**覆盖后必须验证退出状态** |
| 多命令串联（open→改→存→关一条链） | `&&` | ⚠️ **PS 5.1 里 `&&` 是整行 parse error**（前面语句也不会跑）——禁用；用 `;` 则不短路，move 等关键步骤后必须检查 |
| 备份 | `cp "$F" "$F.bak-时间戳"` | `Copy-Item %F% %F%.bak-时间戳` |
| 终验脚本 | `python3 scripts/final_check.py …` | `python scripts/final_check.py …`（✓ Python 3.13 实测正常） |

**Windows 纪律补充**：①禁用 `&&`（PS5.1 整行炸）②move 之后必须验证（占用失败+分号吞错＝坑三放大器）③直存原路径在 Windows 不产生坏文件，但流程纪律不变——跨平台保持同一套习惯，不赌平台差异。

## 模板结构排查速查

```
列表格？      $ED call doc_list_tables file_id="$F"
读全文结构    $ED call doc_resolve_document_structure file_id="$F"
查工具schema  $ED schema doc_insert_text（先看参数再调用）
```

## 常见问题（FAQ）

- **第 1 步就连接失败？** 本地编辑器服务没在监听——回到 WorkBuddy 环境使用（见文首前置条件），不要在宿主外改造本流程。
- **填错位置了怎么回退？** 三层保护：① `F` 是填报版，模板原件从未被动过——大不了删掉填报版从原件重新另存；② mv 前按纪律留了 `$F.bak-时间戳` 备份，直接恢复；③ 小范围错填用 `doc_replace_text`（带 ranges）把错内容精确换回原文。
- **锚点文本搜不到？** 先做全称/简称双搜；再查标点全半角与「．/。」句号风格；表格外框线内的文字用 `doc_list_tables` 走表格通道。
- **save_file 报"文件被占用"？** 不要反复重试——直接换 `$TMP` 走第 5–7 步（预览窗口关掉再 close）。
- **终验失败（非零退出）？** 按 ✗ 项排查：新内容不在=插入未落盘或被预览旧版覆盖；旧内容未清零=替换时 ranges 没对准。修完必须重跑终验，✗ 不清零不交付。
- **报 "document is not open"？** open/改/存跨了多条 Bash 调用——编辑器会话不跨调用存活。按纪律 7 一条链跑完；报错后先解包看内容，别凭输出猜状态。
- **mv 之后发现盖错文件了？** 立即停手检查 `$F.bak-时间戳` 是否在——在则直接恢复；不在则从模板原件重建（模板原件从未被动过，这是纪律 1 的兜底价值）。
- **Windows 能用吗？** 编辑器服务可运行性未实测；命令替换见"Windows 环境对照"节，首跑用测试文件验证。
- **报错回显和实际状态不一致？** 已知现象（纪律 7）——一切以 mv 后的 zip 解包终验为准，终验脚本会给出确定结论。- **什么情况不该用本技能？** 文件不是 .docx（.wps 先另存为 docx）；任务是重写内容而非填报既有模板；目标文件是模板原件（本技能只动填报版）。

## 两个典型场景

**场景 A · 部门填报方案**（"××方案（部门填报）"）：打开模板 → `doc_find` 摸全本单位对应的"落实措施"空位（注意模板可能留了多部门共填行，只动本部门那几行）→ 逐条插入 → 存 tmp → 终验时核对：本单位条目在、他部门占位符未动。

**场景 B · 上会材料会签意见**（通知/纪要的会签单）：定位"部门意见"栏 → `doc_insert_text` 填意见 → 日期栏填成文日期 → 终验核对：意见与日期都在，且其他会签栏空白依旧。

两个场景跑的都是同一条 7 步流程，差别只在锚点选择与终验清单——照"先查后写"纪律先摸清结构再动手。

---

> 📦 **安装（SkillHub 独占）**：https://skillhub.cn/skills/indiv-mabin/docx-template-fill —— 本技能依赖 WorkBuddy 本地编辑器服务，仅经 SkillHub 分发。
