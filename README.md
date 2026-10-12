# agent-skills

实战中沉淀的 Agent Skills，来自真实办公场景的反复使用与打磨，而非一次性生成。

**不绑定特定产品**：遵循开放的 [Agent Skills 规范](https://agentskills.io)，`SKILL.md` + 脚本的结构可在 Claude Code、Claude 桌面版、WorkBuddy、CodeBuddy 等任何支持该规范的 agent 中直接使用；不支持的 agent 也可把 SKILL.md 当作操作手册直接投喂。

## Skills

| Skill | 用途 |
|---|---|
| [read-oversized-image](./read-oversized-image/) | 读取超大图片（展墙长图、测绘图、海报、扫描件 PDF）：降采样解码 + 分块裁切放大，突破 Read 工具的像素限制 |
| [docx-track-changes-wps](./docx-track-changes-wps/) | 用 python-docx + lxml 向 .docx 写入真正的"修订模式"（tracked changes），并规避 WPS 打开时彩虹圈卡死的各种坑 |
| [relation-scope](./relation-scope/) | 人际关系智能分析：聊天记录 / 日记 / 场景重现多输入，输出情感倾向、情绪识别、关系走向、行为模式等多维报告 |

## 使用

把对应的 skill 文件夹复制到你的 agent skills 目录即可（例如 `~/.workbuddy/skills/` 或 Claude Code 的 `~/.claude/skills/`）。每个文件夹内的 `SKILL.md` 是入口。

## License

MIT
