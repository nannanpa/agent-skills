# grill-me-gongwen · 方案拷问（公文规划版）分享包

**一句话**：装上它，AI 在你动笔前把方案问透——分轮盘问、每问必附推荐答案、事实它自己查、决策你拍板、问完才动笔。

## 来源与致谢

- 方法论原型：Matt Pocock 开源仓库 [`mattpocock/skills`](https://github.com/mattpocock/skills) 的 grill-me / grilling（MIT License）
- 本版改造：面向高校办公与公文写作语境（规划、方案、制度修订、上会材料），中文交互，自带「事实自查 + 分轮拷问」机制
- 本分享包为脱敏通用版：原版的个人资料路径已抽为「自定义区」模板

## 适用场景

- 起草方案 / 规划 / 意见 / 通知 / 报告前，还没想清楚，想先被问透
- 制度文件修订前，问清边界情况与新旧衔接
- 上会材料提交前，预演"可能被问住的地方"
- 有模糊想法，先压力测试"该不该做、能不能做"

## 安装

复制 `SKILL.md` 到对应技能目录（保持文件夹名 `grill-me-gongwen`）：

| 环境 | 路径 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/grill-me-gongwen/SKILL.md` |
| Claude Code | `~/.claude/skills/grill-me-gongwen/SKILL.md` |
| 其他兼容 agent（Copilot CLI / Amp / OpenCode 等） | `~/.agents/skills/grill-me-gongwen/SKILL.md` 或项目 `.agents/skills/` |

装好后重启对应客户端即可触发（说"拷问 / 盘问 / 上会前过一遍"等）。

## 安装后必做：填「自定义区」

打开 `SKILL.md`，找到 **「自定义区（安装后必填）」** 一节，把"去哪查"一列替换为你自己的实际位置，例如：

- 既有文件与历史版本 → 你的云盘工作文件夹
- 单位口径与沉淀结论 → 你的知识库（如 Obsidian vault）总目录
- 常用公文排版参数 → 你的模板文件

填得越具体，AI 自查越准、问你的问题越少越准。不填也能用（AI 会把所有事实都标"待核"问你），但威力减半。

## 用法示例

```
我：上会前过一遍——我想提一个"学院学科特区"试点方案
AI：复述理解 → Q1 文种与体例（附推荐）→ 你答 → Q2 → …
    → 回放共同理解 → 你确认 → 给出骨架与风险清单
```

## 发布记录

> 本目录只保留最新版；历史版本见 git 提交记录。

- **2026-10-15 v1.0.1（GitHub + SkillHub）**：补 Matt Pocock（上游 grill-me 作者）版权行（LICENSE + SKILL.md frontmatter author 字段）；新增 UPSTREAM-MERGE.md 改造台账（上游合并规则）；SKILL.md 新增「云盘同步目录降级分支」（云盘占位文件不得误判为查无记录——多平台交叉验证实践沉淀）
- **2026-10-12 首发**：原型（mattpocock/skills 的 grill-me，MIT）+ 高校规划材料场景 5 项改造

## 分发许可

- 原型 MIT License（© Matt Pocock）；本中文改造版同样按 MIT 精神自由分享，保留本致谢即可
- 请勿用于商业售卖
