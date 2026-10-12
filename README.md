# agent-skills

实战中沉淀的 Agent Skills，来自真实办公场景的反复使用与打磨，而非一次性生成。

**聚焦场景：高校"发展规划与学科建设"条线**——项目申报书、"十五五"规划、上会材料、制度修订、领导讲话。既服务同条线的同行，也欢迎任何想把 AI 用进公文写作的人。

**不绑定特定产品**：遵循开放的 [Agent Skills 规范](https://agentskills.io)，`SKILL.md` + 脚本的结构可在 Claude Code、Claude 桌面版、WorkBuddy、CodeBuddy 等任何支持该规范的 agent 中直接使用；不支持的 agent 也可把 SKILL.md 当作操作手册直接投喂。

## Skills

| Skill | 用途 |
|---|---|
| [read-oversized-image](./read-oversized-image/) | 读取超大图片（展墙长图、测绘图、海报、扫描件 PDF）：降采样解码 + 分块裁切放大，突破 Read 工具的像素限制 |
| [docx-track-changes-wps](./docx-track-changes-wps/) | 用 python-docx + lxml 向 .docx 写入真正的"修订模式"（tracked changes），并规避 WPS 打开时彩虹圈卡死的各种坑 |
| [relation-scope](./relation-scope/) | 人际关系智能分析：聊天记录 / 日记 / 场景重现多输入，输出情感倾向、情绪识别、关系走向、行为模式等多维报告 |
| [grill-me-gongwen](./grill-me-gongwen/) | 方案拷问（公文规划版）：动笔前把方案建模为决策树、分轮盘问、每问必附推荐答案，事实 AI 自查、决策你拍板，收敛后才产出。基于 [Matt Pocock grill-me](https://github.com/mattpocock/skills)（MIT）改造 |
| [minfadian](./minfadian/) | 民法典法条速查：1260 条全文按 7 编 84 章 85 个分册存储，配场景速查表、术语定位、高频判断规则三层导航；零依赖纯文本，拷即用 |

## 实践笔记

| 文档 | 内容 |
|---|---|
| [公文写作风格校准实战笔记](./notes/gongwen-style-calibration.md) | 来自真实申报场景的 10 条措辞口径（每条附机制层理由）+ 表格化材料量化检查的 4 条硬经验 + 口径维护方法，可独立于任何工具使用 |

## 使用

把对应的 skill 文件夹复制到你的 agent skills 目录即可（例如 `~/.workbuddy/skills/` 或 Claude Code 的 `~/.claude/skills/`）。每个文件夹内的 `SKILL.md` 是入口。

## License

MIT
