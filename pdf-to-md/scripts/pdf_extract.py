#!/usr/bin/env python3
"""PDF -> Markdown：逐页提取文本层，页与页之间加页码标记。"""
import sys
from pypdf import PdfReader

src, dst = sys.argv[1], sys.argv[2]
r = PdfReader(src)
parts = [f"# {src.split('/')[-1]} 提取文本\n"]
for i, p in enumerate(r.pages):
    t = (p.extract_text() or "").strip()
    parts.append(f"\n\n---\n\n<!-- 第 {i+1} 页 -->\n\n{t}")
with open(dst, "w", encoding="utf-8") as f:
    f.write("\n".join(parts))
print(f"完成: {dst}  共{len(r.pages)}页")
