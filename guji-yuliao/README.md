# guji-yuliao（古籍语料入库器）

把公版古籍转成按章回/卷分册的原文语料技能：繁转简、自动分册、回目索引、指纹核验。与 book-to-skill 平行——book-to-skill 提炼方法论结构，本技能保原文全本。

## 它解决什么

为古籍建"可检索、可引用核对"的原文语料库，手工要做：找底本→繁转简→按回切分→建索引→核对版本指纹。每本书重复一遍，且坑密（BOM、数字写法三态、静默截断、OCR 元数据污染、章回行格式变体）。guji-yuliao 把它压成两条命令：探测（probe）＋入库（build）。

## 两种源模式

- **Gutenberg 章回体** → `scripts/build_split.py`（第X回＋回目，支持楔子归位 ch000）
- **JSON 记录列表**（如 gujilab/chinese-classical-corpus，CC0）→ `scripts/build_json.py`（字段映射、【】夹注剥离子存注本、卷号全局断言、title-override 修 OCR 缺漏）

内置产出：分册 txt＋回目索引.md＋_manifest.json。断言失败零产物退出，不会写半个坏目录。

## 源码

GitHub：https://github.com/nannanpa/agent-skills/tree/main/guji-yuliao ——Issue/PR 欢迎。

## 安装

把 `guji-yuliao/` 放进宿主技能根目录（如 `~/.workbuddy/skills/`）。依赖 python3；`--t2s` 需 `pip install opencc-python-reimplemented`。Windows/macOS/Linux 通用（Windows 10＋Python 3.13 实测通过）。

## 发布记录

- 1.0.2（2026-10-19）修复发布包缺 scripts 目录（首评指出"脚本缺失无法运行"）；SKILL.md 补触发说法示例节
- 1.0.1（2026-10-19）补 GitHub 源码仓库引流；内容与 1.0.0 相同
- 1.0.0（2026-10-19）首发定版（0.1.x 开发期号升位；0.1.2 为平台图标补丁版）
- 0.1.1（2026-10-19）修三处：章回行短前缀容忍＋"回"后分隔符闸（防首回静默丢失，Windows 实测回函必修项）；probe 期望值预警（exit 2）；build_json 缺 opencc 硬报错。分册标题补零统一。
- 0.1.0（2026-10-19）首发：双源模式、三态数字写法、许可证切除、序列断言、指纹核验法。
