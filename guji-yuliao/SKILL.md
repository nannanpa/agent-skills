---
name: guji-yuliao
displayName: 古籍语料入库器
version: "0.1.1"
description: "把公版章回体古籍（如 Project Gutenberg 电子版）转成按章回分册的原文语料技能：繁转简、自动分册、回目索引、指纹核验。当用户要为《三国演义》《西游记》《水浒传》等古籍建原文语料库、或说'把某本古籍入库/做成语料技能'时使用。与 book-to-skill 平行——book-to-skill 提炼方法论结构，本技能保原文全本。不依赖特定平台。"
---

# 古籍语料入库器（guji-yuliao）

**与 book-to-skill 的分工**：同一本"书→技能"上游，下游分叉——book-to-skill 提炼"作者想教我什么"（框架/原则，明言不保原文）；本技能保"原文到底写了什么"（逐字分册＋回目索引），服务于引用核对。纯方法论书只需前者；需要查原文引文的古籍才值得走本技能。

## 使用流程

### 第 1 步 · 取底本
用户提供电子版文件路径或公版源（如 Gutenberg 编号）。**版权关**：只收公有领域文本；现代校注本有著作权，拒收或仅作私用并永不进发布版。

### 第 2 步 · 探测（必做）
```
python scripts/build_split.py --src <文件> --probe
```
输出单元数、首末回目。**核对三件事**：①回数与期望一致（不一致先查是不是多卷本/选本——用"单回平均字数×回数 vs 文件大小"推算完整性；probe 支持 `--chapters N` 自动比对，不符即 stderr 预警并以 exit 2 退出）；②末回指纹对不对（金本水浒末回=惊恶梦、毛本三国=三分归一统——末回是版本系统的指纹）；③有无楔子/序言。

### 第 3 步 · 入库
```
python scripts/build_split.py --src <文件> --dst <技能>/references/<版本名>_简体 \
  --book <书名> --chapters <N> [--prologue 楔子] [--t2s]
```
脚本内建坑位：UTF-8 BOM／数字写法三态（白圈○作零·数字连写·行首空格）／章回行短前缀容忍（"是第一回"式）／古登堡许可证头尾切除／章回序列断言。产出：ch000（楔子）+ch001…chNNN＋回目索引.md＋_manifest.json。

### 第 4 步 · 骨架三件套
按语料技能模板写 SKILL.md（工作流：回目索引定位→读分册核对→引用注明版本回目）＋LESSONS.md（复盘层，永不发布）。SKILL.md 必须写明**版本口径**（哪个本子、多少回、与其他通行本差异）。

### 第 5 步 · 双安全阀
引用核对抽验（首末回指纹＋随机一回）＋脱敏检查（语料本身无敏感信息，核对 SKILL.md 中的说明文字）。

## 常见报错与处置

| 报错/信号 | 原因 | 处置 |
|---|---|---|
| `序列异常: [2,3]...` 入库中断（exit 1，零产物） | 实际探测回数与 `--chapters` 不符——多为回目行格式变体（前缀/全角冒号）或选本缺回 | 先 `--probe` 看首末回目；确认底本完整后修正期望值；若是格式变体，升级本脚本正则而非改样本 |
| `⚠️ 期望 N 回…探测到 M 单元`（probe，exit 2） | 探测数与期望不符的预警——静默少回在入库前就此暴露 | 同上；这是设计行为，不是故障 |
| `缺 opencc：pip install opencc-python-reimplemented`（exit 1） | 传了 `--t2s` 但未装 opencc | 按提示安装后重跑；不装则去掉 `--t2s`（保留繁体） |
| `FileNotFoundError` | `--src` 路径错 | 用完整绝对路径；Windows 端注意反斜杠转义 |
| 断言 `期待记录列表型 JSON`（build_json） | JSON 源不是记录数组（可能是嵌套 dict） | 检查源结构，必要时先做一层展开 |
| 繁转简后个别字未转 | opencc 词表覆盖盲区 | 记入该技能 LESSONS，不逐字手改（语料以原文为准） |

## 场景示例（两类）

### 示例一 · Gutenberg 章回体（水浒传·金本）

```
# 探测：确认 70 回＋无楔子，末回"惊恶梦"= 金本指纹
python scripts/build_split.py --src shuihu.txt --probe --chapters 70
# 入库：繁转简，71 个单元（楔子归 ch000）
python scripts/build_split.py --src shuihu.txt --dst refs/金本70回_简体 \
  --book 水浒传 --chapters 70 --prologue 楔子 --t2s
```
要点：末回指纹不符＝拿错版本系统，立即停；下载大文件用 `curl -C -` 续传，入库前查文件尾（防静默截断＋UTF-8 断字节）。

### 示例二 · JSON 编年体（资治通鉴·四库本）

```
python scripts/build_json.py --src zizhi.json --dst refs/白文本_简体 \
  --book 资治通鉴 --volume volume --title period --content content \
  --strip-brackets --t2s
```
要点：`--strip-brackets` 把【胡注】剥出另存注本；OCR 源元数据不可信——period 空缺/形近异文（记/纪）用 `--title-override '102:晋纪二十四,276:后唐纪五'` 手工修平；卷号全局连续断言兜底。

## 常见问答（FAQ）

- **什么情况不用本技能？**——非章回体也非 JSON 记录列表的文本（如单篇长文）直接存档即可；现代有版权的校注本不收；只想提炼书的方法论去用 book-to-skill。
- **出错怎么办？**——先看上表"常见报错与处置"；所有断言失败都是**零产物退出**，不会写半个坏目录，放心重跑。
- **怎么中途收束？**——probe 之后随时可停：未入库=零残留；已入库想撤销，删产出目录即可（索引/manifest 同在目录旁，一起删）。
- **语料能直接发布吗？**——公版原文可以；但由它产出的技能包发布前仍要走脱敏 grep 与宿主规范（本工具只管"书→分册"，发布审查是另一道闸）。
- **Windows 能用吗？**——能。纯 Python 标准库＋可选 opencc，已在 Windows 10＋Python 3.13 实测（GBK 控制台报错零乱码、中文目录正常）。

## 已知版本系统速查

| 书 | Gutenberg | 本子系统 | 通行本差异 |
|---|---|---|---|
| 三国演义 | #23950 | 毛本 120 回（批语未收） | 与嘉靖本回目文字有异 |
| 西游记 | #23962 | 百回本系统 | — |
| 水浒传 | #23863 | **金本 70 回（腰斩本，末回惊恶梦）** | 无征辽/田虎/王庆/征方腊；与 100/120 回本回目不同 |
| 红楼梦 | （本机另有） | 程高本 120 回＋脂评本 80 回 | — |
| 资治通鉴 | 无（JSON 源） | 四库本 294 卷（正文夹胡注，已拆白文/注本双份） | 无标点连排；卷号全局连续（1 卷=1 纪） |

## 两种源模式

1. **Gutenberg 纯文本源** → `scripts/build_split.py`（章回体：第X回＋回目）；
2. **JSON 记录列表源**（如 gujilab/chinese-classical-corpus，派生数据 CC0）→ `scripts/build_json.py`：字段可映射（volume/title/content）、`--strip-brackets` 剥【】夹注（另存注本）、`--title-override` 修源数据缺漏、卷首样板行剥离、按纪/类分组索引。
   - 古籍 OCR 源教训：元数据不可信（period 空缺/污染、记/纪形近异文），标题必须过正文验证，override 表手工修平。

## 跨宿主说明（信息性）
依赖：python3；`--t2s` 需 opencc（`pip install opencc-python-reimplemented`）。产物为纯文本分册＋md 索引，任何支持技能目录的宿主可用；Windows/macOS/Linux 通用（Windows 10 实测通过）。
