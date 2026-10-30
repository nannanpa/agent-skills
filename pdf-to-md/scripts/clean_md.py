#!/usr/bin/env python3
"""规整 PDF 提取的 md v3（1.2.0）。

基线：v2 / 1.1.1 发布版的全部规则**一条不丢**——
  · 页码残留清除（含前置过滤，防止被噪声规则抢先打标）
  · 强制断行合并
  · 段首识别重排（PARA 词表）
  · 标题粘连拆分（含「句末标点＋编号、」的泛化起段）
  · 字段标签断行
  · 纯节标题短行独立成段（泛化判定，不依赖写死词表）
  · 标点归一（1.2.0 按验收遗留项收紧：任一侧邻接 CJK 或中文标点即转）
  · 噪声整行打标（长串纯数字行 / 无汉字短行）
1.2.0 新增（均来自实战实测，非设想）：
  · 表格整块保护：连续的 `|` 开头行视为一个不可拆单元，行间不留空行
  · 红头文件报头区拆行（发文机关标志／发文字号／标题／受文机关／落款日期／抄送）
  · 噪声行内打标：疑似噪声串**夹在句中**时同样标记（整行规则覆盖不到）
  · --para-patterns 参数化：用户自定义段首模式，追加进 PARA，不必改脚本
  · 退出码：0 成功；1 参数/文件错；2 输入无可规整内容

用法：
  python3 clean_md.py 中间产物.md 最终文件.md "文档标题（提取文本·规整版）" \
      [--para-patterns "正则|正则"] [--no-punct] [--no-noise] [--no-redhead]
"""
import argparse
import re
import sys

# ── 标点归一 ─────────────────────────────────────────────────────────────
# 半角 → 全角。1.1.0 口径是「两侧均 CJK 才转」；按 1.1.0 验收遗留项收紧为
# 「**任一侧**邻接 CJK 字符或中文标点即转」（引号/书名号/括号邻接处的半角残留）。
# 两侧同为数字或拉丁字母时**保护**（010-66097148、92-111、3.14、SBTI (Test)）。
PUNCT_MAP = {",": "，", ";": "；", ":": "：", "!": "！", "?": "？", ".": "。"}
BRACKET_MAP = {"(": "（", ")": "）", "<": "〈", ">": "〉"}
# 中文标点集合——算作 CJK 侧
ZH_PUNCT = set("，。、；：？！…—·《》〈〉「」『』【】〔〕（）［］｛｝“”‘’～￥％＃＠＆＊＋－／＜＝＞　")


def _is_cjk_side(ch):
    """是否算 CJK 侧：汉字、中文标点、全角符号。"""
    if not ch:
        return False
    if ch in ZH_PUNCT:
        return True
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF


def _is_alnum(ch):
    return bool(ch) and (ch.isdigit() or ("a" <= ch.lower() <= "z"))


def normalize_quotes(line):
    """英文直引号成对转中文引号（2026-10-30 实测：69 号文当年靠手工后处理补上）。

    行内第 1、3、5… 个直引号转左引号「“」，第 2、4、6… 个转右引号「”」；
    数量为奇数时**最后一个保持原样**——不成对就不猜开闭（宁可漏，不可错配）。

    只动 `"` 这一个字符：
    - 已经是 `“”` 的不动；
    - 英文单引号 `'` **不动**——英文缩写（don't、it's）会被误伤，中文公文里
      单引号本就用得少，收益小风险大。
    """
    if '"' not in line:
        return line
    total = line.count('"')
    if total % 2 == 1:
        idx = line.rfind('"')
        return normalize_quotes(line[:idx]) + line[idx:]
    out, n = [], 0
    for ch in line:
        if ch == '"':
            n += 1
            out.append("“" if n % 2 == 1 else "”")
        else:
            out.append(ch)
    return "".join(out)


def normalize_punct(line):
    """半角句读转全角：任一侧邻接 CJK 侧即转；两侧皆为数字/拉丁则保护。

    括号**成对**处理（1.1.0 口径）：左括号前邻 CJK 侧、右括号后邻 CJK 侧才转。
    末尾再把成对的英文直引号转中文引号（`normalize_quotes`）——同属"标点形态
    归一"，故与本函数同受 `--no-punct` 控制。
    """
    out = []
    for i, ch in enumerate(line):
        left = line[i - 1] if i > 0 else ""
        right = line[i + 1] if i + 1 < len(line) else ""
        side_cjk = _is_cjk_side(left) or _is_cjk_side(right)
        both_alnum = _is_alnum(left) and _is_alnum(right)
        if ch in PUNCT_MAP and side_cjk and not both_alnum:
            out.append(PUNCT_MAP[ch])
            continue
        if ch == "(" and _is_cjk_side(left) and not _is_alnum(left):
            out.append(BRACKET_MAP[ch])
            continue
        if ch == ")" and _is_cjk_side(right) and not _is_alnum(right):
            out.append(BRACKET_MAP[ch])
            continue
        out.append(ch)
    return normalize_quotes("".join(out))


# ── 噪声打标 ─────────────────────────────────────────────────────────────
# 整行规则（1.1.0）：长串纯数字行（≥8 位）、无汉字短行（≤6 字符）。
NOISE_LONG = re.compile(r"^\d{8,}$")
NOISE_JUNK = re.compile(r"^[^\u4e00-\u9fff]{1,6}$")
# 行内规则（1.2.0）：整行规则覆盖不到「夹在句中」的情形——
#   a) 字母与数字交错的短串（如 L1ti）；
#   b) 连续 7 位以上纯数字（如 61202611016，疑似两串编号/号码粘连）。
# 不打标含连字符/斜杠的数字串（010-66097148、92-111）与被汉字隔开的短数字段（2026年10月16日）。
NOISE_ALT = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{1,3}\d{1,4}[A-Za-z]{1,4})(?![0-9A-Za-z])")
NOISE_NUM = re.compile(r"(?<![0-9\-/\.])(\d{7,})(?![0-9\-/\.])")
NOISE_TAG = "〔噪声待核〕"


def _tag_adjacent(text, start, end):
    """匹配区间前后紧邻处是否已有〔噪声待核〕标记。

    整行规则（lines 阶段）已在行尾打过标记时，行内规则必须让位——
    否则同一个串被标两次，出现〔噪声待核〕〔噪声待核〕。
    """
    n = len(NOISE_TAG)
    if text[max(0, start - n):start] == NOISE_TAG:
        return True
    return text[end:end + n] == NOISE_TAG


def mark_noise_inline(text):
    """行内噪声串原地加〔噪声待核〕——只标记，不删除。

    已被整行规则标记过的串**跳过**（两规则互斥），保证每个噪声串只带一个标记。
    """
    if not text:
        return text
    out = text
    for rx in (NOISE_ALT, NOISE_NUM):
        def _rep(m):
            if _tag_adjacent(out, m.start(), m.end()):
                return m.group(1)
            return m.group(1) + NOISE_TAG
        out = rx.sub(_rep, out)
    return out


# ── 段首模式 ─────────────────────────────────────────────────────────────
BASE_PARA = (
    r"^(?:[一二三四五六七八九十]+、"
    r"|[\（\(][一二三四五六七八九十]{1,3}[\）\)]"
    r"|\d{1,2}\s*[\.、]"
    r"|联\s*系\s*人|联系人|责任单位|查处重点|整顿重点|主要职责"
    r"|组长[:：]|副组长|组员"
    r"|附件|送[:：]|部内发送|工作提示|邮箱|请各单位"
    r"|专题整顿范围|专题整顿从|专题整顿目标|专题整顿工作从"
    r"|工作要求|范围步骤|组织领导|总体要求)"
)
# 红头文件扩展包（2026-10-30 实测：国务院学位委员会 69 号文）——
# 解决「报头区粘成一大段」的已知边界，给的是可直接用的模式，不是"请自行补本校规则"
REDHEAD_PARA = (
    r"|国务院学位委员会文件"
    r"|学位[〔（(][^〕）)]*[〕）)]"
    r"|^关于[^。；！？]{4,60}$"          # 文件标题：必须是「关于…」且整行无句读
    r"|^有关省"
    r"|^[〇一二三四五六七八九十]{4}年"
    r"|^抄送[:：]"
    r"|^为做好"
    r"|^如下意见"
)
# 1.2.0 修订：原含 r"|[\"“]"（引号作段首），实测会误拆正文——
#   公文中以「“」开头的行多半是引文/续行（例："…可“主动撇销”。" 被切成独立段），
#   误拆比漏拆危险：漏拆只是标题续行并入，误拆会把正文句子切碎。
#   文件标题一律以「关于」开头，已由上列 |关于 覆盖，故此处不再用引号作段首。
#
# 1.2.0 再修订：「|关于」收紧为「^关于[^。；！？]{4,60}$」——
#   裸「|关于」会把正文里以「关于」开头的句子切成独立段（例："关于这个问题，
#   我们认为…"），那是误拆；加"整行无句读"约束后，只有真正的文件标题才命中。
#
# 受文机关行：机关名序列（逗号/顿号分隔）以冒号收尾 → 冒号后断开，正文另起一段。
#   实测（69 号文）原文「有关省（自治区、直辖市）学位委员会，有关主管部门：根据…
#   …」整行未断——受文机关与正文首句粘在一起，读者无法分辨哪句是发文对象。
#   约束取四条：① 段首行；② 冒号收尾；③ 冒号前含分隔符（机关名列表特征）；
#   ④ **冒号后不得紧跟数字**——否则是「政策咨询电话:010-66097148」这类字段标签，
#   切开会把号码甩到下一段（实测踩过）。
REDHEAD_ADDR = re.compile(r"^[^。；！？\n]{2,80}[，,、][^。；！？\n]{0,40}[:：](?![ ]*[0-9])")
# 标题与受文机关分离：「……的通知」紧跟机关列举词 → 在此断开，标题独立成段。
#   实测（《扫描3》报头区）标题与受文机关同处一行，读者看不出哪句是标题。
#   匹配条件极窄：前字必须是「通知」，后接机关列举词——正文里几乎不出现。
REDHEAD_TITLE_ADDR = re.compile(
    r"(?<=[通知])(?=(?:各省|各有关|有关各|各学位授予单位|各有关部门|各有关省|各省市|各高等学校))"
)

PAGENO = re.compile(r"^[-—–\s]*\d{1,3}[-—–\s]*$")
TBLROW = re.compile(r"^\|")
SHORT_TITLE = re.compile(r"^[一二三四五六七八九十]{1,3}、[^，。；！？\n]{1,20}$")
HEADINGS = r"(?:总体要求|组织领导|整顿重点|范围步骤|工作要求|整顿清单|工作进度安排)"
ENUM = r"[\（\(](?:十[一二三四五六七八九]?|[一二三四五六七八九])[\）\)]"


def build_para(user_patterns, redhead=True):
    """基础骨架 + 红头扩展包 + 用户自定义（--para-patterns，| 分隔）。"""
    pat = BASE_PARA + (REDHEAD_PARA if redhead else "")
    if user_patterns:
        extra = "|".join(p for p in user_patterns.split("|") if p.strip())
        pat += "|" + extra
    return re.compile(pat)


def split_redhead_addr(p):
    """报头区两处拆分（都只作用于段首那一行）：

    ① 标题与受文机关分离：「……的通知」紧跟机关列举词 → 断开，标题独立成段；
    ② 受文机关与正文分离：机关名列表以冒号收尾 → 冒号后断开，正文另起一段。

    ② 还要求冒号后确有正文；冒号后是数字时（咨询电话：010-…）不动。
    """
    if not p:
        return p
    lines = p.split("\n")
    m = REDHEAD_TITLE_ADDR.search(lines[0])
    if m:
        lines = [lines[0][:m.start()], lines[0][m.start():]] + lines[1:]
    idx = 1 if m else 0
    if idx < len(lines):
        m2 = REDHEAD_ADDR.match(lines[idx])
        if m2:
            tail = lines[idx][m2.end():]
            if tail.strip():
                lines = lines[:idx] + [lines[idx][:m2.end()], tail] + lines[idx + 1:]
    return "\n".join(lines)


def split_blocks(text):
    """切成有序的两类块：表格块（不可拆）与文本块。

    **文本块 = 连续的非表格行聚成一块**（1.1.1 基线行为：行在块内累积成段，
    只在段首模式命中处才断开）。若逐行拆成独立块，段落会被打碎成
    「一行一段」，与发布版行为不一致——这是 1.2.0 初版踩过的坑。
    表格块 = 连续的 `|` 开头行，块内不插空行（否则 Markdown 表格语法失效）。
    """
    lines = []
    for block in re.split(r"<!--\s*第\s*\d+\s*页\s*-->", text):
        for ln in block.splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or ln == "---":
                continue
            lines.append(ln)

    blocks, cur_tbl, cur_txt = [], [], []

    def flush_txt():
        if cur_txt:
            blocks.append(("txt", list(cur_txt)))
            cur_txt.clear()

    def flush_tbl():
        if cur_tbl:
            blocks.append(("tbl", list(cur_tbl)))
            cur_tbl.clear()

    for ln in lines:
        if TBLROW.match(ln):
            flush_txt()
            cur_tbl.append(ln)
        else:
            flush_tbl()
            cur_txt.append(ln)
    flush_txt()
    flush_tbl()
    return blocks


class _ArgParser(argparse.ArgumentParser):
    """参数错统一 exit 1（argparse 默认是 2）。

    退出码约定：0 成功 / 1 参数或文件错 / 2 输入无可规整内容——
    2 专门留给「无可规整内容」，参数错不能混进来，调用方才能用
    「非 0 且非 2 = 用法错」做判断。
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"❌ 参数错误：{message}", file=sys.stderr)
        print("💡 怎么办：用法 python3 clean_md.py 输入.md 输出.md 文档标题 [选项]；"
              "三个位置参数都要给，选项见 --help。", file=sys.stderr)
        sys.exit(1)


def main():
    ap = _ArgParser(description="规整 PDF 提取的 Markdown（v3）")
    ap.add_argument("src", help="第 1 步产出的中间产物 .md")
    ap.add_argument("dst", help="规整后的最终 .md")
    ap.add_argument("title", nargs="?", default="", help="文档标题（写入一级标题）")
    ap.add_argument("--para-patterns", default="",
                    help="自定义段首正则，| 分隔；追加进内置骨架（不改脚本即可适配新文体）")
    ap.add_argument("--no-punct", action="store_true", help="关闭标点归一")
    ap.add_argument("--no-noise", action="store_true", help="关闭噪声打标")
    ap.add_argument("--redhead", action="store_true", default=True, help="启用红头报头区扩展包（默认开启）")
    ap.add_argument("--no-redhead", dest="redhead", action="store_false", help="关闭红头扩展包")
    args = ap.parse_args()

    try:
        text = open(args.src, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"❌ 找不到文件：{args.src}", file=sys.stderr)
        print("💡 怎么办：确认 pdf_extract.py 已经跑过、输出路径写对了。", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError:
        print("❌ 输入文件不是 UTF-8 文本", file=sys.stderr)
        print("💡 怎么办：clean_md 只吃 pdf_extract.py 的产物；不要直接喂原始 PDF 或其他编码文件。", file=sys.stderr)
        sys.exit(1)

    para_re = build_para(args.para_patterns, args.redhead)
    blocks = split_blocks(text)
    if not blocks:
        print("❌ 中间产物里没有可规整的内容", file=sys.stderr)
        print("💡 怎么办：确认第 1 步是否真的提取到了文字层；纯扫描件请走 OCR 分支。", file=sys.stderr)
        sys.exit(2)

    paras = []
    for kind, block in blocks:
        if kind == "tbl":
            # 表格块：整体保留为一个段落（行间不插空行，否则 Markdown 表格语法失效）
            rows = []
            for x in block:
                if not args.no_punct:
                    x = normalize_punct(x)
                if not args.no_noise:
                    x = mark_noise_inline(x)
                rows.append(x.rstrip())
            paras.append(("tbl", "\n".join(rows)))
            continue
        # 文本块：页码前置过滤 → 整行噪声打标 → 按段首模式分段
        lines = []
        for ln in block:
            if PAGENO.match(ln):
                continue                      # 页码行前置过滤，防止被噪声规则抢先打标
            if not args.no_noise and (NOISE_LONG.match(ln) or NOISE_JUNK.match(ln)):
                ln += NOISE_TAG             # 整行噪声：打标不删，人工复核后处理
            lines.append(ln)
        buf = []
        for ln in lines:
            if para_re.match(ln) and buf:
                paras.append(("txt", "".join(buf)))
                buf = [ln]
            else:
                buf.append(ln)
            # 纯节标题短行直接独立成段（泛化判定，不依赖写死词表）
            if len(buf) == 1 and SHORT_TITLE.match(buf[0]):
                paras.append(("txt", buf.pop()))
        if buf:
            paras.append(("txt", "".join(buf)))

    final = []
    for kind, p in paras:
        if kind == "tbl":
            final.append(p)
            continue
        p = re.sub(r"(工作方案)(根据)", r"\1\n\2", p)
        p = re.sub(r"(分工工作方案)(根据)", r"\1\n\2", p)
        # 节标题粘连拆分：句末+编号 泛化起段（标题起段，正文随段）；
        # 已知标题词再做完整的标题独立成行
        p = re.sub(r"(?<=[。；！？])(?=[一二三四五六七八九十]{1,3}、)", "\n", p)
        p = re.sub(r"([一二三四五六七八九十]{1,3}、" + HEADINGS + r")", r"\n\1\n", p)
        p = re.sub(r"\n{2,}", "\n", p)
        # 段中粘连的 (一)(二)… 条目编号前断开（排除"（简称"）
        p = re.sub(r"(?=" + ENUM + r"(?!简称))", "\n", p)
        p = re.sub(r"\n{2,}", "\n", p)
        # 段中粘连的字段标签前断开
        for lab in (r"责任单位[:：]", r"联\s*系\s*人[:：]", r"联系人[:：]",
                    r"整顿重点[:：]", r"查处重点[:：]"):
            p = re.sub(r"(?<!\n)(" + lab + r")", r"\n\1", p)
        # 报头区受文机关行：冒号后断开（正文另起一段）
        if args.redhead:
            p = split_redhead_addr(p)
        out_lines = []
        for x in p.splitlines():
            x = x.strip()
            if not x:
                continue
            if not args.no_punct:
                x = normalize_punct(x)
            if not args.no_noise:
                x = mark_noise_inline(x)
            out_lines.append(x)
        final.extend(out_lines)

    out = ([f"# {args.title}", ""] if args.title else []) + [p + "\n" for p in final]
    try:
        open(args.dst, "w", encoding="utf-8").write("\n".join(out))
    except OSError as e:
        print(f"❌ 写入失败 {args.dst}：{e}", file=sys.stderr)
        sys.exit(1)
    print(f"完成: {args.dst}  段落数={len(final)}")


if __name__ == "__main__":
    main()
