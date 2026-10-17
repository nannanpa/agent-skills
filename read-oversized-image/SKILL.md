---
name: read-oversized-image
description: 读取超大图片（展墙、测绘长图、海报、扫描件、工地/园区全景等，像素数超百万级）时使用。当 Read 报 "Image too large — omitted after compression" 或 PIL 抛 DecompressionBombError 时，用 macOS 原生 sips 缩略出全貌，再用 Pillow 的 draft 模式降解码分辨率 + 分块裁切放大，逐块读清细节文字。适用于需要从巨幅图里精确抄录文字（如展板、图纸标注、坐标表格）的场景。另含"扫描件/图片型 PDF"场景：pypdf 抽不到文字时，用 PyMuPDF(fitz) 把每页渲染成 PNG 再读。
allowed-tools:
  - Read
  - Bash
  - Write
metadata:
  trigger: Read 报 "Image too large"，或 PIL 报 DecompressionBombError，或 PDF 抽不出文字（扫描件），需从巨幅图/长图/扫描PDF里读文字
  agent_created: true
---

# 读取超大图片（展墙 / 长图 / 巨幅扫描件）

## 何时用

- `Read` 图片返回 `[Image too large — omitted after compression]`（工具内部压缩后仍超限）。
- Python `PIL.Image.open()` 抛 `DecompressionBombError: Image size (N pixels) exceeds limit ...`。
- 需要从**巨幅图**里**精确抄录文字**（展板、总平面图、坐标表、流程图）——直接看缩略图看不清小字。

典型尺寸：如 `28800 × 13319`（约 3.8 亿像素，展墙 6790×3140mm 打印稿）。

## 步骤

### 1. 先出全貌（sips，macOS 原生，最快）
```bash
sips -Z 1600 "<原图路径>" --out "/tmp/overview.jpg"
```
然后 `Read /tmp/overview.jpg`。`-Z` 是长边缩到该值。全貌用于**定位**（哪块面板、哪个区域有目标内容），别指望看清小字。

### 2. 取原始像素尺寸
```bash
sips -g pixelWidth -g pixelHeight "<原图路径>"
```

### 3. 备好 Pillow（首次）
管理版 Python 的隔离 venv（勿污染全局）：
```bash
/Users/mabin/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m venv /Users/mabin/.workbuddy/binaries/python/envs/default 2>/dev/null
/Users/mabin/.workbuddy/binaries/python/envs/default/bin/pip install -q Pillow
```

### 4. 降解码分辨率 + 分块裁切放大（核心）
关键两点，缺一会报错或爆内存：
- `Image.MAX_IMAGE_PIXELS = None` —— 关掉"解压炸弹"保护；
- `im.draft("RGB", (W//4, H//4))` —— JPEG 按 DCT 抽稀解码，先把像素降到 1/2 或 1/4 再操作，**必须配合全图尺寸**。

可复用脚本（按**比例**裁切，改 `save()` 的 frac 即可）：
```python
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
p = "<原图路径>"
im = Image.open(p)
im.draft("RGB", (7200, 3330))          # 目标解码尺寸，约原图 1/2~1/4
im = im.convert("RGB")
W, H = im.size
print("loaded", W, H)

def save(frac, name, target=1700):
    x0, y0, x1, y1 = frac            # 均为 0~1 的比例坐标
    c = im.crop((int(x0*W), int(y0*H), int(x1*W), int(y1*H)))
    w, h = c.size
    c = c.resize((target, int(h*target/w)), Image.LANCZOS)
    c.save(name, quality=92)
    print(name, c.size)

save((0.60, 0.42, 1.00, 1.00), "/tmp/c1.jpg")   # 右半
save((0.35, 0.10, 0.56, 0.55), "/tmp/e1.jpg")   # 中上细节
```
再 `Read` 各分块。**目标宽度 1500~1800px** 通常最易读；太小看不清、太大又可能超 Read 限制。

### 5. 逐步收紧
小字看不清就**再裁更小的一块**、把 `target` 调大（例如只取一整行标题，`target=1700` 对 300px 高的条）。读表格/文字要**逐字确认**，别凭模糊轮廓猜。

### 6. 扫描件 / 图片型 PDF：先渲染成图再读

若目标不是图片而是 PDF，且文字抽不出来，说明是**扫描件（图片型）**：

症状：`pypdf`（或 `fitz`/`pdfplumber` 的 `extract_text()`）返回极短文本（如全文仅十几字符），而 PDF 体积很大（数 MB、多页）——说明页内容都是位图，没有文字层。

解法：用 **PyMuPDF** 把每页渲染成 PNG，再按第 4/5 步读图（比 pypdf 可靠，无需 poppler）：
```bash
/Users/mabin/.workbuddy/binaries/python/envs/default/bin/pip install -q PyMuPDF
```
```python
import fitz, os                       # 老版包名 fitz；新版可 import pymupdf
pdf = "<PDF路径>"
out = "/tmp/pdf_pages"; os.makedirs(out, exist_ok=True)
doc = fitz.open(pdf)
for i, page in enumerate(doc):
    page.get_pixmap(dpi=130).save(f"{out}/p{i+1:02d}.png")   # 130dpi 够看清正文/表格
print("页数:", doc.page_count, "尺寸:", doc[0].rect)
```
然后按需 `Read /tmp/pdf_pages/pNN.png`。**只读含有目标内容的页**，别一次读 15 页（费轮次/上下文）；先读末几页（附件/表格常在文末）或按目录定位。

- 表格/正文用 **120~150 dpi** 通常足够；要抄极小字可对该页单独提高 dpi（如 250）再读。
- 跨页表格、页眉页脚会重复出现，注意去重。
- 同族用途：`.docx` 抽不到内容时，也可先转 PDF 再渲染（docx→pdf→png）。

## 注意

- 比例坐标会因 `draft` 缩放而变，但**分数比例不变**，所以 frac 可直接复用。
- 裁切块别太大（>2000px 宽容易又触发 Read 限制）；宁可多切几块。
- `sips` 只是 macOS 自带，跨平台时改用 Pillow 做全貌缩略。
- 不要把超图直接丢给 `Read` 反复试，浪费轮次；先 sips 再区块化。
- 这是**只读**操作，不改原图。
