#!/usr/bin/env python3
"""PDF -> Markdown：逐页提取文本层，页与页之间加页码标记。"""
import sys
from pypdf import PdfReader

src, dst = sys.argv[1], sys.argv[2]
r = PdfReader(src)
parts = [f"# {src.split('/')[-1]} 提取文本\n"]
total = 0
for i, p in enumerate(r.pages):
    t = (p.extract_text() or "").strip()
    total += len(t)
    parts.append(f"\n\n---\n\n<!-- 第 {i+1} 页 -->\n\n{t}")
with open(dst, "w", encoding="utf-8") as f:
    f.write("\n".join(parts))
print(f"完成: {dst}  共{len(r.pages)}页")
avg = total / max(len(r.pages), 1)
if avg < 100:
    print(f"⚠ 平均每页仅 {avg:.0f} 字符——可能无文字层（纯图像扫描件），产物大概率不可用，建议改走视觉识别（页图转写）。")
