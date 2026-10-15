#!/usr/bin/env python3
"""规整 PDF 提取的 md v2：去页码、并断行、重排段落、拆分粘连的标题与条目。"""
import re, sys


def _die(msg, hint):
    print(f"❌ {msg}")
    print(f"💡 怎么办：{hint}")
    sys.exit(1)


if len(sys.argv) < 4:
    _die("参数不足", "用法：python3 clean_md.py 输入.md 输出.md 文档标题 —— 三个参数都要给。")

src, dst, title = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    text = open(src, encoding="utf-8").read()
except FileNotFoundError:
    _die(f"找不到文件：{src}", "确认 pdf_extract.py 已经跑过、输出路径写对了。")
except UnicodeDecodeError:
    _die("输入文件不是 UTF-8 文本", "clean_md 只吃 pdf_extract.py 的产物；不要直接喂原始 PDF 或其他编码文件。")

lines = []
for block in re.split(r"<!--\s*第\s*\d+\s*页\s*-->", text):
    for ln in block.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln == "---":
            continue
        lines.append(ln)

PARA = re.compile(
    r"^(?:[一二三四五六七八九十]+、"
    r"|[\（\(][一二三四五六七八九十]{1,3}[\）\)]"
    r"|\d{1,2}\s*[\.、]"
    r"|联\s*系\s*人|联系人|责任单位|查处重点|整顿重点|主要职责"
    r"|组长[:：]|副组长|组员"
    r"|附件|送[:：]|部内发送|工作提示|邮箱|请各单位"
    r"|专题整顿范围|专题整顿从|专题整顿目标|专题整顿工作从"
    r"|工作要求|范围步骤|组织领导|总体要求)"
)
PAGENO = re.compile(r"^[-—–\s]*\d{1,3}[-—–\s]*$")

paras, buf = [], []
for ln in lines:
    if PAGENO.match(ln):
        continue
    if PARA.match(ln) and buf:
        paras.append("".join(buf))
        buf = [ln]
    else:
        buf.append(ln)
if buf:
    paras.append("".join(buf))

HEADINGS = r"(?:总体要求|组织领导|整顿重点|范围步骤|工作要求|整顿清单|工作进度安排)"
ENUM = r"[\（\(](?:十[一二三四五六七八九]?|[一二三四五六七八九])[\）\)]"

final = []
for p in paras:
    # 文件标题与"根据…"之间断开
    p = re.sub(r"(工作方案)(根据)", r"\1\n\2", p)
    p = re.sub(r"(分工工作方案)(根据)", r"\1\n\2", p)
    # "一、总体要求"等节标题后断开
    p = re.sub(r"([一二三四五]、" + HEADINGS + r")", r"\n\1\n", p)
    p = re.sub(r"\n{2,}", "\n", p)
    # 段中粘连的 (一)(二)… 条目编号前断开（排除"（简称"）
    p = re.sub(r"(?=" + ENUM + r"(?!简称))", "\n", p)
    p = re.sub(r"\n{2,}", "\n", p)
    # 段中粘连的字段标签前断开
    for lab in (r"责任单位[:：]", r"联\s*系\s*人[:：]", r"联系人[:：]", r"整顿重点[:：]", r"查处重点[:：]"):
        p = re.sub(r"(?<!\n)(" + lab + r")", r"\n\1", p)
    final.extend(x.strip() for x in p.splitlines() if x.strip())

out = [f"# {title}", ""] + [p + "\n" for p in final]
open(dst, "w", encoding="utf-8").write("\n".join(out))
print(f"完成: {dst}  段落数={len(final)}")
