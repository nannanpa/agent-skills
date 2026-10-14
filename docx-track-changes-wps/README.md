# docx-track-changes-wps

用 python-docx + lxml 向 `.docx` 写入真正的"修订模式"（tracked changes / redline revisions），专为**中文公文场景**设计：修改意见报送、发文稿上标注修改/新增，且必须在 **WPS** 中干净打开。

## 解决的问题

WPS 对修订 XML 极其敏感，手写的 `w:ins`/`w:del` 很容易触发"彩虹圈无限转圈"无响应。本 skill 沉淀了完整的避坑清单：

- 全文档唯一 `w:id`、合法 ISO 8601 `w:date`
- `settings.xml` 里 `trackChanges` 必须配合 `rsidRoot`
- 优先**只插不改**（`w:ins` 替代 `w:del`），规避最常见的死循环诱因
- 中文标点（`》`U+300A、`—`U+2014）隐藏字符导致锚点匹配失败的排查法

完整清单、操作流程和验证方法见 [SKILL.md](./SKILL.md)。

## 使用

把整个文件夹复制到你的 agent skills 目录（如 `~/.workbuddy/skills/`），脚本在 `scripts/apply_track_changes.py`。

## 发布记录

> 本目录只保留最新版；历史版本见 git 提交记录。

- **2026-10-15 SkillHub 1.0.4**：双平台交叉验证后修复——①`ensure_child` 按 CT_Settings schema 顺序找锚点插入，`w:rsidRoot` 归位到 `w:rsids` 内部（旧版误插 `w:settings` 直属位置，实测 WPS 卡死诱因）；②新增撞号修复：计数器起号取 max(10000, 文档既有修订 id 最大值)（固定 10001 在自带修订史的稿件上必然撞号，Windows 实测复现）；③`verify()` 内置 settings 结构回归断言；④新增跨平台 `scripts/self_test.py`（基础插入 + 撞号回归两场景）；⑤SKILL.md 新增"适用环境与未验证声明"与已知坑（WPS 个人版修订窗格不显示时间列）；⑥默认修订作者改为中性"审校"（脱敏补漏）。实测：Windows 10 + WPS 12.1.0.29161 self-test 一次全绿，WPS 三点检查两过一判定通过
- **2026-10-13 SkillHub 1.0.3**：脱敏——示例句中内部文件指代改为通用表述（"规划、要点类文件"）
- **2026-10-13 SkillHub 1.0.2**：SKILL.md 全文由英文重写为中文（技术术语与代码不变）——SkillHub 详情页"概述"直接展示 SKILL.md，英文版导致市场页显示英文描述
- **2026-10-13 SkillHub 1.0.1**：分发侧补充自定义图标与分类标签（内容无变化）
- **2026-10-12 首发**：python-docx + lxml 给 .docx 插入修订模式（tracked changes，兼容 WPS）

## License

MIT
