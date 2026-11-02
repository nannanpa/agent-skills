# skill-origin — 技能溯源核验（Provenance Audit）

判定已安装技能"从哪来、正不正宗、是否该换源"：**管正宗 + 实用，不管安全**（安全疑虑请走各平台的官方安全审计技能）。

## 快速使用

> **推荐：一条命令出双维报告。** 用统一入口 `origin.py`，一次同时给出「正宗度 + 实用度」合并报告与综合建议：
> ```bash
> python3 scripts/origin.py <技能目录名>      # 单技能双维体检
> python3 scripts/origin.py all               # 全量双维体检
> python3 scripts/origin.py all --no-network  # 离线：只跑实用度
> python3 scripts/origin.py all --no-exec     # 严格零网络：连样例脚本都不执行
> ```

```bash
python3 scripts/provenance.py <技能目录名>   # 核验单个（正宗度，联网）
python3 scripts/provenance.py all            # 全量体检 skills 目录
python3 scripts/provenance.py all --rules ./rules.json  # 用外部规则文件覆盖阈值/名单
python3 scripts/praccheck.py <技能目录名>      # 实用度核查（v1.1.0，纯本地零网络）
python3 scripts/praccheck.py all               # 批量核查
python3 scripts/praccheck.py all --no-exec     # 严格零网络：不执行样例脚本
python3 scripts/praccheck.py <名称> --need "需求"  # 附需求做匹配度评估
```

纯 Python 标准库，**零依赖、零配置、开箱即用**；GitHub 公开数据走 api.github.com 匿名调用，限 60 次/时，日常核验足够。
默认扫描根**跨平台自动发现**（WorkBuddy / Claude Code / ~/.config / ~/.codex / ~/.agents / ~/.gemini / Windows %LOCALAPPDATA%、%APPDATA%），报告抬头会写明本次扫的是哪个根；`--dir` 可覆盖。

## 判定矩阵

| 档位 | 置信度 | 判定条件 | 建议 |
|---|---|---|---|
| 自建/改造 | 中 | 满足其一：① `SELF_BUILT` 名单内且非自带元数据 ② 元数据 `slug`+`namespace=indiv-mabin` 双字段自洽 ③ 有非空 `UPSTREAM-MERGE.md` 且无外部来源 ④ frontmatter 声明 `agent_created: true` | **判词去绝对化**：均为本地证据、未与平台核对，可被伪造，不证明原创、不构成授权依据；空台账不计数 |
| A+ 厂商官方 | 高 | 上游仓库属厂商官方 org（anthropics / openai / google / microsoft / vercel-labs 等白名单）；**多个候选仓库时官方优先于星数** | 最高背书，比星数更硬 |
| A 官方背书 | 中 | 元数据 `source=marketplace` **且含 `skillId` 或 `installedContentHash` 且非 `preinstalledTemplate`** | 市场分发记录（本地声明、可被伪造）可放心使用；缺二者或属预置模板不授此档 |
| B 行业顶流 | 高 | 上游仓库 ≥1000★ 且非 fork | 已是最权威版本 |
| B- 中坚来源 | 高 | 上游仓库 100★≤星数<1000★ 且非 fork | 已有权威上游、具一定社区背书，可用；如需官方/最新优先可对比升级 |
| C fork/低星替代 | 高 | 装的是 fork，或 <100★ 而存在更高星同源仓库 | 建议卸载换母仓版（改装母仓前先过安全审计） |
| D 无背书 | 低 | 0~低★ / 无来源标记 / 第三方市场分发但缺 skillId 或 installedContentHash 或属预置模板 | 从未使用→建议卸载；要用→先过安全审计 |
| ？ 来源未声明 | 低 | 正文仅**提及**外部仓库（无来源声明词） | 提及不进档位，需人工确认 |
| ？ 来源声明未解析 | 低 | 声明了上游来源但全部不可解析（改名/删除/网络受限） | 需人工确认 |
| ？ API受限 | 低 | GitHub API 403/429（**全部形态**：二次限流、abuse detection、Retry-After、429 空 body） | **限流≠无背书**，等配额恢复后重跑 |
| ？ 网络不可达 | 低 | DNS 不通 / 被墙 / 超时（与限流分开报） | 不可达≠无背书；先跑离线模式拿本地可判项 |
| ？ 上游未查询 | 低 | 离线模式未查询上游仓库 | 本地可判项已给出，联网后重跑补全 |
| ？ 核验异常 | 低 | 安装元数据损坏（非 dict，如 JSON 列表） | 单技能降级，不中断整批 |

> **置信度**：高＝GitHub 公开数据实测；中＝本地元数据/名单/台账（未与平台核对，可被伪造）；低＝证据不足或未能取证。它不打折，而是告诉你结论有多硬。

两条铁律：

- **限流 ≠ 无背书**：API 超限时输出"？ API受限"档而不是 D 档——不许制造冤案；
- **零结论铁律**：开源 0★ 不等于技能没用（市场可能有大安装量），市场热卖也不等于开源侧有审查——两个信号都报，让使用者拍板。

## 定位

- v1.1.0 起为「正宗 + 实用」双支柱：`provenance.py` 查血统正宗（需联网查 GitHub），`praccheck.py` 查实不实用（纯本地零网络）；
- v1.2.0 起加「统一入口 origin.py」：一条命令同时跑两维、出合并报告与综合建议，离线自动降级（本地可判项照给，上游档位标「？ 上游未查询」）；
- v1.2.2 起加**置信度 + 可配置规则 + 跨平台扫描根 + 统一错误码 + 零网络强隔离**：每条结论标出证据强度；阈值与名单改由 `config/rules.json` 配置（不必改代码）；默认扫描根跨平台自动发现；所有受控失败带 `E_XXX` 错误码；样例执行期阻断外网并清除凭证（`--no-exec` 可彻底不执行）；限流识别覆盖 403/429 全部形态；厂商官方优先于星数；需求匹配从字面重合升级为三通道。
- 与官方 **skills-sec-audit（安全审计）严格分工**：sec-audit 查恶意代码，本技能查血统正宗；
- 核验依据三层交叉：安装元数据（`_skillhub_meta.json`）→ SKILL.md 声明（author/version）→ README 里的上游仓库 → GitHub API 实测（星数 / `fork` 字段 / `parent` 母仓 / `pushed_at` 新鲜度）；
- **自建技能，无上游**（2026-10-12 由实际溯源实战固化，含一次"命名之争"——专业词 provenance 留在括号里，平实词 origin 占名位）。

## 适用范围

任何采用 SKILL.md 格式（Agent Skills 规范）的 agent 环境，拷进技能目录即可；不依赖特定平台 API。

## 发布记录

> 本目录只保留最新版；历史版本见 git 提交记录。
>
> 注：以下历史条目中的 `prequal` / `预检` / `安装前甄别` 等为旧名或旧表述，现行模块名为 `praccheck`、定位为「装后核查」。

- **2026-11-02 v1.2.2（GitHub，SkillHub 同号）**：逐条整改 v1.2.1 评测（versionId 478512，均分 4.753）点名的问题——① **置信度输出**：报告新增置信度列（高＝GitHub 实测／中＝本地元数据名单台账／低＝证据不足），把「结论有多硬」摊开给使用者 ② **断网不丢结论**：离线时本地可判项（自建/改造、市场件背书）照给，只把需联网实测的权威档位标「？ 上游未查询」；断网原因拆分为「？ API受限」与「？ 网络不可达」 ③ **限流识别全覆盖**：403/429 的全部形态（429 空 body、二次限流、abuse detection、Retry-After）一律判受限，不再漏判成「仓库不存在」而冤枉成 D 档 ④ **厂商官方优先于星数**：多候选仓库时官方 org 压过高星非官方 ⑤ **跨平台扫描根自动发现**：不再硬绑 ~/.workbuddy/skills，按环境变量→多平台候选顺序探测，报告抬头写明本次扫描根 ⑥ **判定规则外部可配置**：官方 org 白名单／自建名单／星数阈值／命名空间移至 `config/rules.json`（默认值与 1.2.1 一致，支持 `--rules` 与 `SKILL_ORIGIN_RULES`） ⑦ **统一错误码**：新增公共层 `scripts/common.py`，全站错误形如 `❌ [E_XXX] 说明`；praccheck 补齐目录/参数异常拦截（旧版吐裸 traceback） ⑧ **零网络强隔离**：样例脚本执行时注入阻断外网的代理环境并清除 `GITHUB_TOKEN`；新增 `--no-exec` 彻底不执行 ⑨ **需求匹配三通道**：关键词命中＋bigram 重合＋能力类目同义映射，并列出未命中词 ⑩ **修两处误报/失真**：测试夹具里的路径字面量不再被误报为「硬编码绝对路径」；凭证提示区分「可选配置」与「必需自备」 ⑪ 文档示例换成真实输出（原 100/100 示例早已失真）⑫ 新增 `scripts/test_common.py`（16 用例），四套测试共 50 用例全绿。

- **2026-11-01 v1.2.1（GitHub，SkillHub 同号）**：口径对齐（依据评测 versionId 478080）——① A 档市场背书条件补 `installedContentHash`（与代码 `MARKET_EVIDENCE` 一致）② FAQ 限流表述改为"标为 ？ API受限（≠无背书）" ③ 新增可选 `GITHUB_TOKEN` 环境变量提额（默认匿名、零配置）④ 判定矩阵补 `B- 中坚来源` 档（100★≤星数<1000★）⑤ praccheck/origin 补独立回归测试 `test_praccheck.py`/`test_origin.py` ⑥ origin/provenance 入口加目录不存在校验与异常兜底 ⑦ 实用度模块重定位：`prequal.py`→`praccheck.py`（装后核查、非装前预检），全文档「安装前/预检」改「装后/核查」，档位标签「可放心装/先验证再装/不建议装」改「可放心用/先验证再用于关键场景/不建议用」，与溯源同为装后审计、消除口径矛盾。
- **2026-10-31 v1.2.0（GitHub，SkillHub 同号）**：新增 `scripts/origin.py` 统一入口——一条命令同时跑「正宗度(provenance) + 实用度(prequal)」两维、出合并双支柱报告与综合建议；两维独立、离线自动降级；prequal 排除技能自带兄弟脚本互 import 误报、批量扫描跳过 `.bak` 备份目录。后续补丁（同版本内）：provenance 自建判定改为**数据驱动**——优先读 `_skillhub_meta.json` 的 `slug` 作权威名（不再靠剥离 `__` 目录后缀猜测）、补 `skill-miner` 进 SELF_BUILT、新增 `OWN_NAMESPACE=indiv-mabin` 命名空间信号（本人发布的技能自动判自建，免手维护）。**P0 加固（同版本内·本地待发布）**：依据 DSH 终审前回执的 P0-1…P0-6 落实——① 自建/改造判词去绝对化（明示"本地证据、可被伪造、不证明原创"）② meta 需 `slug`+`namespace` 双字段自洽、空台账不计数 ③ 正文仅"提及"仓库不进档位（F-1）④ 坏元数据单技能降级「？ 核验异常」不中断整批（F-3）⑤ 增 `from __future__ import annotations` 保 3.9 兼容 ⑥ marketplace 授 A 档须含 `skillId` 且排除 `preinstalledTemplate`；并补 `scripts/test_provenance.py`（13 用例，3.9.6 通过）锁回归。
- **2026-10-31 v1.1.0（GitHub / SkillHub 同号）**：新增 `scripts/praccheck.py`（时名 prequal.py）实用度核查——装后纯本地零网络核查技能「好不好使」（结构齐备／三件套／描述诚实／运行风险／需求匹配），与 provenance 的正宗判定形成双支柱；SKILL.md 增加「实用度核查」章节与质量判定矩阵。
- **2026-10-15 v1.0.4（GitHub，SkillHub 同号）**：provenance.py 支持 `--dir` 自定义扫描目录；批量核验加实时进度（stderr，不污染报告）；SKILL.md 新增「对话式触发（推荐用法）」「报告长这样（真实输出）」「常见问题 FAQ」三节
- **2026-10-13 SkillHub 1.0.3**：全文清除凭据类关键词表述——市场能力标签源于包内关键词扫描，正面声明本身也会命中（1.0.2 未消除的根因）
- **2026-10-13 SkillHub 1.0.2**：移除提额指引与凭据相关表述
- **2026-10-13 SkillHub 1.0.1**：补充自定义图标与"办公效率"分类（内容无变化）
- **2026-10-13 SkillHub 1.0.0**：发布至 SkillHub 市场（@indiv-mabin/skill-origin）
- **2026-10-12 首发**：四级判定矩阵 + provenance.py（纯标准库零依赖）+ 厂商官方档/OFFICIAL_ORGS 白名单（含一次"命名之争"：provenance 留括号，origin 占名位）
