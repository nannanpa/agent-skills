# agent-skills

实战中沉淀的 Agent Skills，来自真实办公场景的反复使用与打磨，而非一次性生成。

**聚焦场景：高校"发展规划与学科建设"条线**——项目申报书、"十五五"规划、上会材料、制度修订、领导讲话。既服务同条线的同行，也欢迎任何想把 AI 用进公文写作的人。

**不绑定特定产品**：遵循开放的 [Agent Skills 规范](https://agentskills.io)，`SKILL.md` + 脚本的结构可在 Claude Code、Claude 桌面版、WorkBuddy、CodeBuddy 等任何支持该规范的 agent 中直接使用；不支持的 agent 也可把 SKILL.md 当作操作手册直接投喂。

## Skills

| Skill | 用途 |
|---|---|
| [read-oversized-image](./read-oversized-image/) | 读取超大图片（展墙长图、测绘图、海报、扫描件 PDF）：降采样解码 + 分块裁切放大，突破 Read 工具的像素限制 |
| [docx-track-changes-wps](./docx-track-changes-wps/) | 用 python-docx + lxml 向 .docx 写入真正的"修订模式"（tracked changes），并规避 WPS 打开时彩虹圈卡死的各种坑 |
| [docx-format-guard](./docx-format-guard/) | 按既定公文格式参数生成 Word 并读回自检：标题/正文字体字号、行距、页边距、首行缩进逐项断言落盘，专治"看着生成成功、实际格式偏掉" |
| [docx-template-fill](./docx-template-fill/) | 仅 WorkBuddy：通过本地编辑器（edsdk）填报/修改 docx 模板的安全流程，固化加密保存坏文件、未等待打开、文件占用被旧版覆盖三个坑的规避方法 |
| [xlsx-cross-check](./xlsx-cross-check/) | 多份 Excel 按指定键跨表匹配、逐键比对并汇总，强制汇总数字与源表逐键一致；适合"几个表的数字对不上"的对齐核验 |
| [relation-scope](./relation-scope/) | 人际关系智能分析：聊天记录 / 日记 / 场景重现多输入，输出情感倾向、情绪识别、关系走向、行为模式等多维报告 |
| [grill-me-gongwen](./grill-me-gongwen/) | 方案拷问（公文规划版）：动笔前把方案建模为决策树、分轮盘问、每问必附推荐答案，事实 AI 自查、决策你拍板，收敛后才产出。基于 [Matt Pocock grill-me](https://github.com/mattpocock/skills)（MIT）改造 |
| [minfadian](./minfadian/) | 民法典法条速查：1260 条全文按 7 编 84 章 85 个分册存储，配场景速查表、术语定位、高频判断规则三层导航；零依赖纯文本，拷即用 |
| [hongloumeng](./hongloumeng/) | 红楼梦全本语料：程高本 120 回（简/繁）+ 脂评本 80 回（脂批约 3900 条）双版本对读，配回目/人物/诗词/脂批导航与四批可追溯校勘记录 |
| [guji-yuliao](./guji-yuliao/) | 把公版章回体古籍转成按回分册的原文语料：繁转简、回目索引、指纹核验；与 book-to-skill 分工——后者提方法论，本技能保原文全本供引用核对 |
| [pdf-to-md](./pdf-to-md/) | PDF → 规整 Markdown，专治中文公文/红头文件 OCR 产物：页码残留清除、强制断行合并、`（一）（二）`段首与字段标签重排；零依赖仅 pypdf，规则可读可改 |
| [skill-origin](./skill-origin/) | 技能溯源核验：判定已装技能是官方首发、行业顶流还是 fork/无背书（安装元数据 + GitHub API 四级判定矩阵，含"限流不判死"与"零结论"两条铁律）；管正宗不管安全，与官方安全审计技能互补。纯标准库零依赖 |
| [rule-miner](./rule-miner/) | 知识盘点与挖掘：做知识资产的盘点→核验→萃取→并入四步——廉价枚举 .md、比对全局记忆缺口、提取净增的规则/方法论/坑与教训/模板范式/决策判据五类资产，支持去重冲突检测（抽取双方原文＋初步分级）、溯源标注、可配置落点 |
| [skill-miner](./skill-miner/) | 从日常任务记录中发现可复用技能候选：枚举重复流程、聚类场合与脚本族、与现有技能查重，产出通用 SKILL.md 规范的候选提案与骨架；与 rule-miner 配套（rule-miner 挖规则，skill-miner 挖技能） |
| [memory-cleanup](./memory-cleanup/) | macOS 内存卫生：默认只读巡检（空闲/swap/自动化浏览器实例/常驻通信进程），四参数阈值可配且每次先报当前阈值，白名单路径精确清理、回收站两段式归档；卖判据不卖一键清理 |
| [docs-cross-check](./docs-cross-check/) | 同构多篇 Word 材料交稿前的横切一致性复核：序号连续性、目标条格式、篇幅分布、篇内重复指标四维一次扫完，按篇号给证据；只查横向对不对得齐，只处理 .docx |
| [agent-bridge](./agent-bridge/) | 智能体通讯桥：零常驻的 agent 间消息桥，共享目录互递任务/回执，按〔线程〕限三领信与停函收口（回执即终／第 4 封硬拦），收件箱可配置；纯标准库脚本，由人或定时任务拉起 |

## 实践笔记

| 文档 | 内容 |
|---|---|
| [公文写作风格校准实战笔记](./notes/gongwen-style-calibration.md) | 来自真实申报场景的 10 条措辞口径（每条附机制层理由）+ 表格化材料量化检查的 4 条硬经验 + 口径维护方法，可独立于任何工具使用 |
| [一稿为三：成文后按受众分版](./notes/one-draft-three.md) | 一份写好的公文按看的人切成原件／参谋件／对外件三份，边界写进每份文件头、不靠记性守；三条硬红线（不自动判公开、默认不做红头、示例全虚构），可脱离任何工具使用 |

## 使用

把对应的 skill 文件夹复制到你的 agent skills 目录即可（例如 `~/.workbuddy/skills/` 或 Claude Code 的 `~/.claude/skills/`）。每个文件夹内的 `SKILL.md` 是入口。

## License

MIT
