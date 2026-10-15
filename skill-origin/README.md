# skill-origin — 技能溯源核验（Provenance Audit）

判定已安装技能"从哪来、正不正宗、是否该换源"：**管正宗，不管安全**（安全疑虑请走各平台的官方安全审计技能）。

## 快速使用

```bash
python3 scripts/provenance.py <技能目录名>   # 核验单个
python3 scripts/provenance.py all            # 全量体检 skills 目录
```

纯 Python 标准库，**零依赖、零配置、开箱即用**；GitHub 公开数据走 api.github.com 匿名调用，限 60 次/时，日常核验足够。

## 判定矩阵

| 档位 | 判定条件 | 建议 |
|---|---|---|
| 自建/改造 | 目录有 `UPSTREAM-MERGE.md` 且无外部仓库来源 | 原创度 100%，上游更新走台账三方合并 |
| A+ 厂商官方 | 上游仓库属厂商官方 org（anthropics / openai / google / microsoft / vercel-labs 等白名单） | 最高背书，比星数更硬 |
| A 官方背书 | 安装元数据 `source=marketplace`（官方市场，带 skillId + 内容哈希） | 放心使用 |
| B 行业顶流 | 上游仓库 ≥1000★ 且非 fork | 已是最权威版本 |
| C fork/低星替代 | 装的是 fork，或 <100★ 而存在更高星同源仓库 | 建议卸载换母仓版（换装前先过安全审计） |
| D 无背书 | 0~低★ / 无来源标记 / 第三方市场分发 | 从未使用→建议卸载；要用→先过安全审计 |

两条铁律：

- **限流 ≠ 无背书**：API 超限时输出"？ API受限"档而不是 D 档——不许制造冤案；
- **零结论铁律**：开源 0★ 不等于技能没用（市场可能有大安装量），市场热卖也不等于开源侧有审查——两个信号都报，让使用者拍板。

## 定位

- 与官方 **skills-sec-audit（安全审计）严格分工**：sec-audit 查恶意代码，本技能查血统正宗；
- 核验依据三层交叉：安装元数据（`_skillhub_meta.json`）→ SKILL.md 声明（author/version）→ README 里的上游仓库 → GitHub API 实测（星数 / `fork` 字段 / `parent` 母仓 / `pushed_at` 新鲜度）；
- **自建技能，无上游**（2026-10-12 由实际溯源实战固化，含一次"命名之争"——专业词 provenance 留在括号里，平实词 origin 占名位）。

## 适用范围

任何采用 SKILL.md 格式（Agent Skills 规范）的 agent 环境，拷进技能目录即可；不依赖特定平台 API。

## 发布记录

> 本目录只保留最新版；历史版本见 git 提交记录。

- **2026-10-13 SkillHub 1.0.0**：发布至 SkillHub 市场（@indiv-mabin/skill-origin）
- **2026-10-13 SkillHub 1.0.1**：补充自定义图标与"办公效率"分类（内容无变化）
- **2026-10-13 SkillHub 1.0.3**：全文清除凭据类关键词表述——市场能力标签源于包内关键词扫描，正面声明本身也会命中（1.0.2 未消除的根因）
- **2026-10-13 SkillHub 1.0.2**：移除提额指引与凭据相关表述
- **2026-10-13 SkillHub 1.0.1**：补充自定义图标与"办公效率"分类（内容无变化）
- **2026-10-13 SkillHub 1.0.0**：发布至 SkillHub 市场（@indiv-mabin/skill-origin）
- **2026-10-15 v1.0.4（GitHub，SkillHub 同号）**：provenance.py 支持 `--dir` 自定义扫描目录；批量核验加实时进度（stderr，不污染报告）；SKILL.md 新增「对话式触发（推荐用法）」「报告长这样（真实输出）」「常见问题 FAQ」三节
- **2026-10-12 首发**：四级判定矩阵 + provenance.py（纯标准库零依赖）+ 厂商官方档/OFFICIAL_ORGS 白名单（含一次"命名之争"：provenance 留括号，origin 占名位）
