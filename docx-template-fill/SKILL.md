---
name: docx-template-fill
description: 【仅限 WorkBuddy】通过本地编辑器（内置 skill tencent-local-office-edit 的 edsdk）填报/修改 docx 模板的安全工作流。固化了三个实战坑的规避方法：加密保存坏文件、未等待打开导致操作落空、文件被占用时改动被旧版覆盖。触发词：edsdk、doc_insert_text、doc_replace_text、tencent-local-office-edit、WorkBuddy 填报 docx 模板、保存 docx 失败。
---

# docx-template-fill：模板填报安全工作流

**⚠️ 平台归属与前置条件（先看这条）**：本技能**仅限 WorkBuddy 环境使用**——全部命令依赖 WorkBuddy 运行时的本地编辑器服务（editor_sdk，由 `edsdk.py` 封装，自动探测 127.0.0.1:39099–39108 端口）。其他平台（Claude Code 等）**没有这个服务，本技能一步都跑不了**。若在本技能所属宿主之外调用：第 1 步 `open_file` 就会连接失败，此时请回到 WorkBuddy 环境使用，不要尝试改造本流程。

配合内置 skill `tencent-local-office-edit` 的 `edsdk.py` 使用，填报上级模板（如"××方案（部门填报）"）、往既有 Word 文档插内容。**本 skill 是流程纪律，不是新工具**——工具都来自 edsdk，这里固化的是"怎么用不出事"。

## 适用环境与未验证声明（诚实边界）

- **实测环境**：WorkBuddy（macOS）+ 本地编辑器服务 editor_sdk（端口 39099–39108），`edsdk.py` 为该服务的 HTTP 封装。
- **未验证**：Windows 版 WorkBuddy 的可运行性（`file` 等 POSIX 工具不可用，诊断命令需按操作纪律第 6 条替换）；其他 agent 平台不可用（无本地编辑器服务）。
- **三坑的真实发生率**来自作者实战记录，无法离线复现；CDFV2 的"加密"表述系按现象描述（文件表现为 OLE2 复合容器、编辑器无法重开），精确机制未独立验证。

## 为什么需要这个 skill（三个实战坑）

| 坑 | 后果 | 规避 |
|---|---|---|
| save_file 直存原路径 | 可能写成加密 CDFV2 格式，连编辑器自己都无法重新打开，只能重建 | **永远存到临时路径**，关闭后 mv 覆盖 |
| open_file 不等待 | 后续 doc_find 全部落空、看似空文档 | open_file 必须带 `--json '{"wait":true}'` |
| 文件被预览占用后重开编辑器 | 编辑器从磁盘载回旧版，改动被静默冲掉 | 改完立即走"存tmp→close→mv"，不重开 |

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

## 第 7 步终验代码（必跑，这是最后一道防线——检查不过会非零退出，必须停下排查）

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
7. **open→改→存→关必须在同一条命令链里执行**（`&&` 串联）：编辑器会话不保证跨 Bash 调用存活，跨命令续操作会报 "document is not open"；且报错回显可能滞后——**一切以 mv 后的 zip 解包终验为准**，报错后不要凭输出猜状态，先解包看内容再说
8. **mv 前确认 `$TMP` 是本次产物**（`ls -la` 看时间戳）：目录里可能残留旧临时文件，盲目 `mv -f` 会把不知道哪个版本的文件盖到目标上

## 模板结构排查速查

```
列表格？      $ED call doc_list_tables file_id="$F"
读全文结构    $ED call doc_resolve_document_structure file_id="$F"
查工具schema  $ED schema doc_insert_text（先看参数再调用）
```

---

> 📦 **获取最新版**：https://github.com/nannanpa/agent-skills/releases —— 本技能在 GitHub 与 SkillHub **同号发布**，Release 附件可下载任意历史版本。
