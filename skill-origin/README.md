# skill-origin — 技能溯源核验（Provenance Audit）

判定已安装技能"从哪来、正不正宗、是否该换源"：**管正宗 + 实用，不管安全**（安全疑虑请走各平台的官方安全审计技能）。

## 快速使用

> **推荐：一条命令出双维报告。** 用统一入口 `origin.py`，一次同时给出「正宗度 + 实用度」合并报告与综合建议：
> ```bash
> python3 scripts/origin.py <技能目录名>      # 单技能双维体检
> python3 scripts/origin.py all               # 全量双维体检
> python3 scripts/origin.py all --no-network  # 离线：只跑实用度
> ```

```bash
python3 scripts/provenance.py <技能目录名>   # 核验单个（正宗度，联网）
python3 scripts/provenance.py all            # 全量体检 skills 目录
python3 scripts/prequal.py <技能目录名>      # 实用度预检（v1.1.0，纯本地零网络）
python3 scripts/prequal.py all               # 批量预检
python3 scripts/prequal.py <名称> --need "需求"  # 附需求做匹配度评估
```

纯 Python 标准库，**零依赖、零配置、开箱即用**；GitHub 公开数据走 api.github.com 匿名调用，限 60 次/时，日常核验足够。

## 判定矩阵

| 档位 | 判定条件 | 建议 |
|---|---|---|
| 自建/改造 | 满足其一：① `SELF_BUILT` 名单内且非自带元数据 ② 元数据 `slug`+`namespace=indiv-mabin` 双字段自洽 ③ 有非空 `UPSTREAM-MERGE.md` 且无外部来源 | **判词去绝对化**：均为本地证据、未与平台核对、可被伪造，不证明原创、不构成授权依据；空台账不计数 |
| A+ 厂商官方 | 上游仓库属厂商官方 org（anthropics / openai / google / microsoft / vercel-labs 等白名单） | 最高背书，比星数更硬 |
| A 官方背书 | 元数据 `source=marketplace` **且含 `skillId` 且非 `preinstalledTemplate`** | 市场分发记录（本地声明、可被伪造）可放心使用；缺 skillId 或属预置模板不授此档 |
| B 行业顶流 | 上游仓库 ≥1000★ 且非 fork | 已是最权威版本 |
| C fork/低星替代 | 装的是 fork，或 <100★ 而存在更高星同源仓库 | 建议卸载换母仓版（换装前先过安全审计） |
| D 无背书 | 0~低★ / 无来源标记 / 第三方市场分发但缺 skillId 或属预置模板 | 从未使用→建议卸载；要用→先过安全审计 |
| ？ 来源未声明 | 正文仅**提及**外部仓库（无来源声明词） | 提及不进档位，需人工确认 |
| ？ 来源声明未解析 | 声明了上游来源但全部不可解析（改名/删除/网络受限） | 需人工确认 |
| ？ 核验异常 | 安装元数据损坏（非 dict，如 JSON 列表） | 单技能降级，不中断整批 |

两条铁律：

- **限流 ≠ 无背书**：API 超限时输出"？ API受限"档而不是 D 档——不许制造冤案；
- **零结论铁律**：开源 0★ 不等于技能没用（市场可能有大安装量），市场热卖也不等于开源侧有审查——两个信号都报，让使用者拍板。

## 定位

- v1.1.0 起为「正宗 + 实用」双支柱：`provenance.py` 查血统正宗（需联网查 GitHub），`prequal.py` 查实不实用（纯本地零网络）；
- v1.2.0 起加「统一入口 origin.py」：一条命令同时跑两维、出合并报告与综合建议，离线自动降级（正宗度标「⏭ 离线跳过」仍输出实用度）；
- 与官方 **skills-sec-audit（安全审计）严格分工**：sec-audit 查恶意代码，本技能查血统正宗；
- 核验依据三层交叉：安装元数据（`_skillhub_meta.json`）→ SKILL.md 声明（author/version）→ README 里的上游仓库 → GitHub API 实测（星数 / `fork` 字段 / `parent` 母仓 / `pushed_at` 新鲜度）；
- **自建技能，无上游**（2026-10-12 由实际溯源实战固化，含一次"命名之争"——专业词 provenance 留在括号里，平实词 origin 占名位）。

## 适用范围

任何采用 SKILL.md 格式（Agent Skills 规范）的 agent 环境，拷进技能目录即可；不依赖特定平台 API。

## 发布记录

> 本目录只保留最新版；历史版本见 git 提交记录。

- **2026-10-31 v1.2.0（GitHub / SkillHub 同号，本地，待发布）**：新增 `scripts/origin.py` 统一入口——一条命令同时跑「正宗度(provenance) + 实用度(prequal)」两维、出合并双支柱报告与综合建议；两维独立、离线自动降级；prequal 排除技能自带兄弟脚本互 import 误报、批量扫描跳过 `.bak` 备份目录。后续补丁（同版本内）：provenance 自建判定改为**数据驱动**——优先读 `_skillhub_meta.json` 的 `slug` 作权威名（不再靠剥离 `__` 目录后缀猜测）、补 `skill-miner` 进 SELF_BUILT、新增 `OWN_NAMESPACE=indiv-mabin` 命名空间信号（本人发布的技能自动判自建，免手维护）。**P0 加固（同版本内·本地待发布）**：依据 DSH 终审前回执的 P0-1…P0-6 落实——① 自建/改造判词去绝对化（明示"本地证据、可被伪造、不证明原创"）② meta 需 `slug`+`namespace` 双字段自洽、空台账不计数 ③ 正文仅"提及"仓库不进档位（F-1）④ 坏元数据单技能降级「？ 核验异常」不中断整批（F-3）⑤ 增 `from __future__ import annotations` 保 3.9 兼容 ⑥ marketplace 授 A 档须含 `skillId` 且排除 `preinstalledTemplate`；并补 `scripts/test_provenance.py`（13 用例，3.9.6 通过）锁回归。
- **2026-10-31 v1.1.0（GitHub / SkillHub 同号）**：新增 `scripts/prequal.py` 实用度预检——安装前纯本地零网络甄别技能「好不好使」（结构齐备／三件套／描述诚实／运行风险／需求匹配），与 provenance 的正宗判定形成双支柱；SKILL.md 增加「实用度预检」章节与质量判定矩阵。
- **2026-10-13 SkillHub 1.0.0**：发布至 SkillHub 市场（@indiv-mabin/skill-origin）
- **2026-10-13 SkillHub 1.0.1**：补充自定义图标与"办公效率"分类（内容无变化）
- **2026-10-13 SkillHub 1.0.3**：全文清除凭据类关键词表述——市场能力标签源于包内关键词扫描，正面声明本身也会命中（1.0.2 未消除的根因）
- **2026-10-13 SkillHub 1.0.2**：移除提额指引与凭据相关表述
- **2026-10-13 SkillHub 1.0.1**：补充自定义图标与"办公效率"分类（内容无变化）
- **2026-10-13 SkillHub 1.0.0**：发布至 SkillHub 市场（@indiv-mabin/skill-origin）
- **2026-10-15 v1.0.4（GitHub，SkillHub 同号）**：provenance.py 支持 `--dir` 自定义扫描目录；批量核验加实时进度（stderr，不污染报告）；SKILL.md 新增「对话式触发（推荐用法）」「报告长这样（真实输出）」「常见问题 FAQ」三节
- **2026-10-15 v1.0.4（GitHub，SkillHub 同号）**：provenance.py 支持 `--dir` 自定义扫描目录；批量核验加实时进度（stderr，不污染报告）；SKILL.md 新增「对话式触发（推荐用法）」「报告长这样（真实输出）」「常见问题 FAQ」三节
- **2026-10-12 首发**：四级判定矩阵 + provenance.py（纯标准库零依赖）+ 厂商官方档/OFFICIAL_ORGS 白名单（含一次"命名之争"：provenance 留括号，origin 占名位）
