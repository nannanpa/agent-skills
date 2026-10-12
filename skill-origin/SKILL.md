---
name: skill-origin
description: 技能溯源核验——判定已安装技能的原创度、是否官方首发、是否行业权威版本。通过 _skillhub_meta.json 安装元数据 + GitHub API 溯源（星数/是否fork/母仓/最后更新）四级判定，输出核验报告与换源建议。触发词：技能溯源、核验技能、这个skill是不是正版、技能原创度、查技能来源、装的这个skill权威吗。与官方 skills-sec-audit（安全审计）互补：sec-audit 管安全，本技能管正宗。
---

# 技能溯源核验（Provenance Audit）

核验已安装技能"从哪来、正不正宗、是否该换源"。**与安全审计分工明确：本技能不查恶意代码，安全疑虑一律转交官方 skills-sec-audit。**

## 快速使用

```bash
# 核验单个技能
python3 scripts/provenance.py <技能目录名>

# 全量核验（默认扫描 ~/.workbuddy/skills/ 下全部）
python3 scripts/provenance.py all
```

## 核验方法论（按序执行）

1. **收集来源线索**（三处）：
   - `_skillhub_meta.json` → `source` 字段（`marketplace`=官方市场，`skillhub`=第三方市场）＋ `installedAt` 安装时间戳
   - `SKILL.md` 的 `author`/`version` 字段
   - `README.md`/`SKILL.md` 中的 GitHub 仓库链接（排除 `user-attachments`、`github.com/search` 等非仓库链接）
2. **GitHub API 溯源**（`https://api.github.com/repos/{owner}/{repo}`）：星数、`fork` 字段、`parent`（fork 必查母仓）、`pushed_at` 最后更新
3. **套用判定矩阵**（下表）出档位与建议
4. **输出报告**（md 表格：技能 / 来源 / 上游仓库 / 星数 / fork / 最后更新 / 档位 / 建议）

## 判定矩阵（核心规则）

| 档位 | 判定条件 | 含义与建议 |
|---|---|---|
| **自建/改造** | 目录有 `UPSTREAM-MERGE.md` 且无外部仓库来源 | 原创度 100%，不存在"正版"问题；上游更新走台账三方合并 |
| **A+ 厂商官方** | 上游仓库属厂商官方 org（`OFFICIAL_ORGS` 白名单：anthropics、openai、google-labs-code、microsoft、vercel-labs 等） | 最高背书，比星数更硬 |
| **A 官方背书** | `_skillhub_meta.json` 的 source=marketplace（CodeBuddy 官方市场，带 skillId+内容哈希） | 放心使用 |
| **B 行业顶流** | 上游仓库 ≥1000★ 且非 fork（作者本人仓库为最权威形态） | 已是最权威版本 |
| **C fork/低星替代** | 装的是 fork 版（看 parent 母仓星数）或 <100★ 而存在更高星同源仓库 | ⚠️ 建议卸载换母仓版；换装前必须过 skills-sec-audit |
| **D 无背书** | 0~低★仓库 / 无来源标记 / skillhub 第三方分发 | ⚠️ 若从未使用→建议卸载；若要用→必须先过 skills-sec-audit，官方内置同类功能可兜底 |

补充规则：
- **fork 判定只看 GitHub `fork` 字段**，不猜；fork 版一律查 parent，母仓星数远高于 fork（10 倍以上）→ 明确建议换母仓
- **新鲜度**：`pushed_at` 晚于本地 `installedAt` → 提示"上游有更新"（按本地时区日期比较）；改造类技能提示走 UPSTREAM-MERGE 三方合并（上游当底料、本地改造优先、bug 修复直接吸收）
- **限流≠无背书（防冤案铁律）**：GitHub API 未认证限 60 次/时，超限时输出"？ API受限"档而非 D 档；设 `GITHUB_TOKEN` 环境变量可提到 5000 次/时
- **零结论铁律**：GitHub 镜像 0★ 不等于技能没用（SkillHub 等市场可能有大安装量），反之市场热卖也不等于开源侧有审查——两个信号都报，让用户拍板
- API 未限流时优先 api.github.com；github.com 网页在本机可能被限流，不用它

## 输出格式

报告必须包含：档位结论一句话总评 + 明细表 + 每个非 A/B 档技能的具体动作建议（换源/审计/卸载/留观）。

## 维护说明

- 判定阈值（1000★/100★）写在 `scripts/provenance.py` 顶部常量，可随时调
- 新技能安装后建议跑一次：`python3 scripts/provenance.py <名称>`；全量体检跑 `all`
- 本技能为自建（2026-10-12 由实际溯源实战固化），无上游
