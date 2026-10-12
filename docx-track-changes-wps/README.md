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

## License

MIT
