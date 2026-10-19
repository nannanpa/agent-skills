# skill-miner（技能孵化器）

从你与 AI 助手的日常任务中，发现并提炼可复用的 Skill 候选。面向所有 Skill 机制宿主（Claude Code / Copilot CLI / OpenCode / WorkBuddy 等），平台中立。

## 它解决什么

非技术用户的流程经验、公文套路、排查手法沉淀在对话里，用完即弃；而"这能变成 skill"的判断门槛又太高。skill-miner 把这件事变成一句话："我让你帮我完成的任务里，能不能提炼 skill？"

## 流程

复盘扫描（三判据：场景重发＋步骤决策点＋模板清单）→ 一页纸提案（只提案不建，批准权在用户）→ 批准后按 skill-creator 规范建档 → 选址＋脱敏双安全阀。

内置：偏差处置预案（越权直建/判据放水/无中生有等五类症状的纠偏与恢复）、两类场景示例＋反例、常见问答。

## 安装

把 `skill-miner/` 目录放进你的宿主技能根目录即可（如 Claude Code `~/.claude/skills/`、WorkBuddy `~/.workbuddy/skills/`）。纯文档实现，零依赖，Windows/macOS/Linux 通用。

## 源码

GitHub：https://github.com/nannanpa/agent-skills/tree/main/skill-miner ——Issue/PR 欢迎。

## 发布记录

- 1.0.3（2026-10-19）SKILL.md 补触发说法示例与降级处理、技术面异常处置表（首评实用性低分项针对性补强）；GitHub 源码仓库引流随本版实际上架
- 1.0.2（2026-10-19）平台 icon 自动补丁版占号（引流版 zip 与其撞号未上架）
- 1.0.1（2026-10-19）SkillHub 实际首发版本号（1.0.0 发布通道报错误判顺延；已过科恩/云鼎安全审核）
- 1.0.0（2026-10-19）首发导入

## 状态

v1.0.3 · 开源发布（GitHub / SkillHub）· SkillHub 首评 4.5。
