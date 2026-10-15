#!/usr/bin/env python3
"""PDF -> Markdown：逐页提取文本层，页与页之间加页码标记。"""
import sys
from pypdf import PdfReader


def _die(msg, hint):
    print(f"❌ {msg}")
    print(f"💡 怎么办：{hint}")
    sys.exit(1)


if len(sys.argv) < 3:
    _die("参数不足", "用法：python3 pdf_extract.py 输入.pdf 输出.md —— 两个路径都要给，含空格的路径用引号包住。")

src, dst = sys.argv[1], sys.argv[2]
try:
    r = PdfReader(src)
except FileNotFoundError:
    _die(f"找不到文件：{src}", "检查路径拼写；文件名含空格时命令里要用引号包住。")
except Exception as e:
    m = str(e)
    if "encrypt" in m.lower() or "password" in m.lower():
        _die("这个 PDF 设了密码", "先解除密码（另存为无密码版本）再提取。")
    _die(f"读取 PDF 失败：{m}", "确认它是完整有效的 PDF；文件损坏时重新获取一份。")

parts = [f"# {src.split('/')[-1]} 提取文本\n"]
total = 0
for i, pg in enumerate(r.pages):
    t = (pg.extract_text() or "").strip()
    total += len(t)
    parts.append(f"\n\n---\n\n<!-- 第 {i+1} 页 -->\n\n{t}")
with open(dst, "w", encoding="utf-8") as f:
    f.write("\n".join(parts))
print(f"完成: {dst}  共{len(r.pages)}页")
avg = total / max(len(r.pages), 1)
if avg < 100:
    print(f"⚠ 平均每页仅 {avg:.0f} 字符——可能无文字层（纯图像扫描件），产物大概率不可用，建议改走视觉识别（页图转写）。")
