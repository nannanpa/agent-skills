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

NOISE_LONG = re.compile(r"^\d{8,}$")            # 长串纯数字（登记戳等）
NOISE_JUNK = re.compile(r"^[^\u4e00-\u9fff]{1,6}$")  # 无汉字短行（扫描噪声如 L1ti）
PAGENO = re.compile(r"^[-—–\s]*\d{1,3}[-—–\s]*$")
SHORT_TITLE = re.compile(
    r"^[一二三四五六七八九十]{1,3}、[^，。；！？\n]{1,20}$"  # 纯节标题短行：编号+短标题、无句读
)

lines = []
for block in re.split(r"<!--\s*第\s*\d+\s*页\s*-->", text):
    for ln in block.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln == "---":
            continue
        if PAGENO.match(ln):
            continue   # v1.1.0：页码行前置过滤（防止被噪声规则抢先打标）
        if NOISE_LONG.match(ln) or NOISE_JUNK.match(ln):
            ln += "〔噪声待核〕"   # v1.1.0：打标不删，人工复核后处理
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
    if PARA.match(ln) and buf:
        paras.append("".join(buf))
        buf = [ln]
    else:
        buf.append(ln)
    # v1.1.0：纯节标题短行直接独立成段（泛化判定，不依赖写死词表）
    if len(buf) == 1 and SHORT_TITLE.match(buf[0]):
        paras.append(buf.pop())
if buf:
    paras.append("".join(buf))

HEADINGS = r"(?:总体要求|组织领导|整顿重点|范围步骤|工作要求|整顿清单|工作进度安排)"
ENUM = r"[\（\(](?:十[一二三四五六七八九]?|[一二三四五六七八九])[\）\)]"

PUNCT_MAP = {",": "，", ".": "。", ";": "；", ":": "：", "!": "！", "?": "？"}

def normalize_punct(t):
    # v1.1.0：标点归一——半角句读两侧均 CJK 才转全角（保护 010-66097148、2025—2027 等数字串）；
    # 括号单独处理：'(' 前邻 CJK、')' 后邻 CJK 即转（可覆盖 "(2026年)" 类，括号对成对转换）
    t = re.sub(r"(?<=[\u4e00-\u9fff])([,.;:!?])(?=[\u4e00-\u9fff])",
               lambda m: PUNCT_MAP[m.group(1)], t)
    t = re.sub(r"(?<=[\u4e00-\u9fff])\(", "（", t)
    t = re.sub(r"\)(?=[\u4e00-\u9fff])", "）", t)
    return t

final = []
for p in paras:
    # 文件标题与"根据…"之间断开
    p = re.sub(r"(工作方案)(根据)", r"\1\n\2", p)
    p = re.sub(r"(分工工作方案)(根据)", r"\1\n\2", p)
    # 节标题粘连拆分 v1.1.0：句末+编号泛化起段（标题起段，正文随段）；
    # 已知标题词再做完整的标题独立成行（沿用原词表，扩至"十"）
    p = re.sub(r"(?<=[。；！？])(?=[一二三四五六七八九十]{1,3}、)", "\n", p)
    p = re.sub(r"([一二三四五六七八九十]{1,3}、(?:总体要求|组织领导|整顿重点|范围步骤|工作要求|整顿清单|工作进度安排))", r"\n\1\n", p)
    p = re.sub(r"\n{2,}", "\n", p)
    # 段中粘连的 (一)(二)… 条目编号前断开（排除"（简称"）
    p = re.sub(r"(?=" + ENUM + r"(?!简称))", "\n", p)
    p = re.sub(r"\n{2,}", "\n", p)
    # 段中粘连的字段标签前断开
    for lab in (r"责任单位[:：]", r"联\s*系\s*人[:：]", r"联系人[:：]", r"整顿重点[:：]", r"查处重点[:：]"):
        p = re.sub(r"(?<!\n)(" + lab + r")", r"\n\1", p)
    final.extend(normalize_punct(x.strip()) for x in p.splitlines() if x.strip())

out = [f"# {title}", ""] + [p + "\n" for p in final]
open(dst, "w", encoding="utf-8").write("\n".join(out))
print(f"完成: {dst}  段落数={len(final)}")
