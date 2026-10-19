# read-oversized-image

读取超大图片（展墙、测绘长图、海报、扫描件等，像素数超百万级）的实战方法。

当 Read 工具报 "Image too large — omitted after compression" 或 PIL 抛 `DecompressionBombError` 时使用。核心思路：

1. `sips` 查原始像素尺寸
2. Pillow 用 `Image.MAX_IMAGE_PIXELS = None` 关闭解压炸弹保护 + `im.draft()` 按 DCT 抽稀降分辨率解码（必须配合全图尺寸，缺一不可）
3. 按比例坐标分块裁切 + LANCZOS 放大到 1500~1800px 宽
4. 扫描件 / 图片型 PDF：先用 PyMuPDF 逐页渲染成 PNG 再走同样的读图流程

详细流程、可复用脚本和踩坑记录见 [SKILL.md](./SKILL.md)。

## 使用

把整个文件夹复制到你的 agent skills 目录（如 `~/.workbuddy/skills/`）。

## 发布记录
- **2026-10-19 v1.0.6（最新）**：触发检测补决策顺序——先判断内置 Read 是否够用（浏览全貌可直接 Read 省一轮，实测 3 亿像素直读可行），需抄录小字才走平台分支；修正测试单 K3-4 坐标笔误
- **2026-10-19 v1.0.5**：Windows 实测回填（Windows 10 + WorkBuddy 客户端 + Pillow 13，20000×15000 测试图）——诚实边界升级"Windows 已实测"；关键发现：Windows 版 Read 可能不报错直接吞下大图；Pillow 替代路径验证可行（全貌 ~0.4s+分块读字，全流程 <1s）；DecompressionBomb 阈值实测；新增「Windows 环境对照」节
- **2026-10-18 v1.0.4**：description 由多行块标量合并为单行（防 SkillHub 卡片描述截断）
- **2026-10-15 v1.0.3（GitHub，SkillHub 同号）**：平台限制（sips 仅 macOS，跨平台走 Pillow）前置到 SKILL.md 开头
- **2026-10-15 v1.0.2（GitHub，SkillHub 同号）**：SKILL.md 新增「常见问题 FAQ」节（跨平台替代方案前置、sips 报错排查、降采样后仍失败的对策、扫描件抽字范围）
- **2026-10-13 SkillHub 1.0.1**：分发侧补充自定义图标与分类标签（内容无变化）
- **2026-10-12 首发**：macOS 原生 sips 分块降采样，破解 Read 工具读超大图片的压缩失败

；历史版本见 git 提交记录。


## License

MIT
