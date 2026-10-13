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

> 本目录只保留最新版；历史版本见 git 提交记录。

- **2026-10-13 SkillHub 1.0.1**：分发侧补充自定义图标与分类标签（内容无变化）
- **2026-10-12 首发**：macOS 原生 sips 分块降采样，破解 Read 工具读超大图片的压缩失败

## License

MIT
