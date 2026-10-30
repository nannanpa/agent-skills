#!/usr/bin/env python3
"""guji-yuliao 通用分册入库脚本（古登堡类章回体古籍）
用法：
  探测：python build_split.py --src X.txt --probe
  入库：python build_split.py --src X.txt --dst <dir> --book <书名> --chapters 70 \
        [--prologue 楔子] [--t2s] [--skip-head N] [--skip-tail N] [--source 'Gutenberg #23863']
坑位内建：BOM / 数字写法多态（○作零·连写·行首空格·大写壹贰叁…·廿卅·拾佰）/ 头尾许可证切除 / 断言连续
退出码约定：0=成功；1=环境/输入错误（文件不存在、缺依赖、参数错）；2=数据预警（序列不匹配，零产物，核对后重跑）
"""
import argparse, hashlib, json, re, sys
from datetime import datetime
from pathlib import Path

NUM = {"零":0,"〇":0,"○":0,
       "一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,
       "壹":1,"贰":2,"叁":3,"肆":4,"伍":5,"陆":6,"柒":7,"捌":8,"玖":9}
def cn2int(s):
    s = s.replace("第","").replace("回","")
    if s.isdigit(): return int(s)
    if s and all(ch in NUM for ch in s):
        return int("".join(str(NUM[ch]) for ch in s))
    total, seg = 0, 0
    for ch in s:
        if ch in NUM: seg = NUM[ch]
        elif ch in ("十","拾"): total += (seg or 1) * 10; seg = 0
        elif ch in ("百","佰"): total += (seg or 1) * 100; seg = 0
        elif ch == "廿": total += (seg or 1) * 20; seg = 0
        elif ch == "卅": total += (seg or 1) * 30; seg = 0
        else: raise ValueError(f"未知数字字符 {ch} in {s}")
    return total + seg

def die(msg, code=2):
    """统一退出：code 1=环境/输入错误，2=数据预警（零产物）。"""
    print(msg, file=sys.stderr); sys.exit(code)


class _Parser(argparse.ArgumentParser):
    """1.0.9 A3：参数错（含缺必填）统一退 1——2 是"数据预警"码位，
    参数错混进去会让人按码分流时误诊为数据问题。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"参数错误：{message}", file=sys.stderr)
        sys.exit(1)

def main():
    ap = _Parser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst")
    ap.add_argument("--book", default="")
    ap.add_argument("--chapters", type=int, default=0, help="期望回数（0=只探测）")
    ap.add_argument("--prologue", default="", help="楔子/序言标题词（存为 ch000）")
    ap.add_argument("--t2s", action="store_true", help="繁转简（需 opencc）")
    ap.add_argument("--source", default="", help="来源说明（如 'Gutenberg #23863'；默认记 src 文件名）")
    ap.add_argument("--skip-head", type=int, default=0, help="跳过正文开头 N 行（非 Gutenberg 源的版权页；1.0.9 实现）")
    ap.add_argument("--skip-tail", type=int, default=0, help="跳过正文结尾 N 行（1.0.9 实现）")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    # 入库回执（2026-10-19 扩）：底本指纹取原始文件字节，识别"同一书名不同本子/静默截断"
    src_path = Path(args.src)
    if not src_path.exists():
        die(f"找不到底本文件：{src_path}（--src 需完整绝对路径）", 1)
    src_sha256 = hashlib.sha256(src_path.read_bytes()).hexdigest()

    # 编码读取（1.0.7 补）：UTF-8 失败自动回退 GB18030，回执记 source_encoding
    try:
        raw = src_path.read_text(encoding="utf-8-sig"); src_enc = "utf-8-sig"
    except UnicodeDecodeError:
        raw = src_path.read_text(encoding="gb18030"); src_enc = "gb18030"
        print("⚠️ UTF-8 解码失败，已按 GB18030 读取（回执 source_encoding=gb18030）", file=sys.stderr)
    m = re.search(r"\*\*\* START OF.*?\*\*\*", raw)
    raw = raw[m.end():] if m else raw
    m = re.search(r"\*\*\* END OF", raw)
    raw = raw[:m.start()] if m else raw
    # 1.0.9 A5：非 Gutenberg 源的头尾版权页无自动标记，用 --skip-head/--skip-tail 手工裁（许可证切除之后计数）
    if args.skip_head or args.skip_tail:
        rl = raw.split("\n")
        if args.skip_head:
            rl = rl[args.skip_head:]
        if args.skip_tail:
            rl = rl[:len(rl) - args.skip_tail]
        raw = "\n".join(rl)
        print(f"⚠️ 已按 --skip-head {args.skip_head} / --skip-tail {args.skip_tail} 裁掉正文首尾行")
    text = OpenCC("t2s").convert(raw) if args.t2s else raw

    # 1.0.9 B5：字符类扩入 ASCII 0-9 与全角 ０-９（此前 cn2int 的 isdigit 分支永远走不到）
    NUMCH = "0-9０-９零〇○一二三四五六七八九十百廿卅壹贰叁肆伍陆柒捌玖拾佰"
    # 回目行判据（2026-10-19 Windows 回函 3-1 修）：容忍"是/此"等 0-2 字短前缀；
    # "回"后必须紧跟分隔符（全角空/半角空/冒号）——防"此开卷第一回也"这类正文句误判为回目
    # 1.1.0 C3（响亮误拒）：原宽松式容忍"回"后半角空格 → 正文里的"第十二回 且介…"被当成回目行，
    # 合法底本仅因一行正文就被判 exit 2，而诊断只说"序列从第 N 回起"，指不出是哪一行误判。
    # 改「先严后宽」：严格式只认全角空/冒号/行尾；严格式一个都没探到时才放宽（含半角空格）并告警。
    CHAP_STRICT = r"^[\s　]*(?:[^\s第]{0,2})?(第[" + NUMCH + r"]+回)(?=[　：:]|$)[:：]?\s*(\S.*?)\s*$"
    CHAP_LOOSE  = r"^[\s　]*(?:[^\s第]{0,2})?(第[" + NUMCH + r"]+回)(?=[　：:\s])[:：]?\s*(\S.*?)\s*$"
    pro_re  = re.compile(r"^[\s　]*(" + (args.prologue or "∧never∧") + r")[\s　]+(\S.*?)\s*$", re.M) if args.prologue else None

    def parse_chapters(pattern):
        """按给定回目正则切分正文 → (chapters, prologue, hits)。

        hits 记每个回目行的「行号·回号·标题」，供序列异常时把误判行直接指给人看
        （C3：响亮误拒的另一半是"说不出错在哪"，光退 2 等于把排查成本全推给用户）。
        """
        rx = re.compile(pattern, re.M)
        chs, pro, cur, hits = [], None, None, []
        for i, ln in enumerate(text.split("\n"), 1):
            ln = ln.rstrip()
            mm = rx.match(ln)
            if mm:
                if cur: chs.append(cur)
                cur = (cn2int(mm.group(1)), mm.group(2).strip(), [])
                hits.append((i, cur[0], cur[1]))
                continue
            if pro_re:
                pm = pro_re.match(ln)
                if pm and pro is None:
                    pro = (0, pm.group(2).strip(), [])
                    cur = pro
                    hits.append((i, 0, cur[1]))
                    continue
            if cur is not None:
                cur[2].append(ln)
        if cur and chs and cur is not chs[-1]: chs.append(cur)
        elif cur and not chs: chs.append(cur)
        return chs, pro, hits

    chapters, prologue, hits = parse_chapters(CHAP_STRICT)
    if not chapters:
        # 严格式全不命中 → 多半底本用半角空格分隔回目（合法），回退宽松式
        chapters, prologue, hits = parse_chapters(CHAP_LOOSE)
        if chapters:
            print("⚠️ 严格回目判据未命中，已放宽到含半角空格——若随后报序列异常，"
                  "多半是正文含『第X回 』被误判（见下方命中行号）", file=sys.stderr)

    # 楔子与正式回目混排时归位
    if prologue is not None:
        chapters = [c for c in chapters if c[0] != 0 or c is prologue]
        chapters.sort(key=lambda c: c[0])

    nums = [c[0] for c in chapters]
    print(f"探测到 {len(chapters)} 个单元（含楔子={'有' if prologue else '无'}）")
    # 1.0.9 A1：0 单元与回目不连续一律退 2——此前"首回丢失""底本被截断"会静默 exit 0，
    # 用户拿到假绿灯后才发现不对；断言不依赖用户是否给了 --chapters
    if not chapters:
        die("探测到 0 个单元——底本可能不是章回体、回目行格式不匹配、或文件为空/被截断——零产物退出，先核对底本", 2)
    seq = [n for n in nums if n != 0]
    # 1.0.9 补 1（复审）：seq 为空（只有「第〇回」或回号全为 0）时 seq[-1] 越界 → 明确退 2，不抛 traceback
    if not seq:
        die("探测到回目但无有效回号（疑似只有『第〇回』或回号全为 0）——核对回目行，零产物退出", 2)
    if seq != list(range(1, seq[-1] + 1)):
        # 两种成因分开说：起点偏移（节选/续本 or 下载截断）vs 中间断号/重号
        if seq == list(range(seq[0], seq[-1] + 1)):
            # 1.0.9 补 3（复审方案 B）：明确本工具仅支持从第 1 回起的完整底本——
            # 原措辞"请人工确认"但无任何确认入口（无 --start-at 类参数），属叫人确认却无门；
            # 1.1.0 复修：删掉两条假出路（"按回号补齐"会破坏回号与原书错位、"改用 build_json.py"
            # 指向同样只收 1..N 连续卷号、同样是死路），把"下载被截断"提为第一成因，
            # 对真节选本只说"不支持"并明确劝阻重编号。
            # 1.1.0 C3：补一句命中行号，把"响亮误拒"变成"可定位"——只退 2 不指行，等于让用户自己找。
            if hits:
                head = "；命中行号示例：" + "，".join(
                    f"L{n}→第{k}回 {t[:16]}" for n, k, t in hits[:5])
            else:
                head = ""
            die(f"序列从第 {seq[0]} 回起（不是第 1 回）——本工具仅支持从第 1 回起的完整底本。"
                f"最常见成因是下载被截断：按《取底本检查清单》续传后重试。"
                f"若底本本就是节选/续本：本工具不支持，也请勿为凑 1 起而重编号"
                f"（回号重编会让语料回号与原书回号错位，引用核对立即失效）——零产物退出{head}", 2)
        die(f"序列异常: {seq[:5]}...{seq[-5:]}（回目不连续或有重号）——零产物退出，先 --probe 核对回目行格式", 2)
    # 2026-10-19 Windows 回函 3-1 补：probe 对"探测数 vs 期望回数"做预警，静默少回=零产物前就该暴露
    if args.chapters:
        expect = [0] + list(range(1, args.chapters + 1)) if prologue else list(range(1, args.chapters + 1))
        if nums != expect:
            print(f"⚠️ 期望 {args.chapters} 回（{'含' if prologue else '不含'}楔子），探测到 {len(chapters)} 单元、序列 {nums[:6]}...——请核对回目行是否带前缀或格式异常", file=sys.stderr)
            if args.probe:
                sys.exit(2)
    if args.probe or not args.chapters:
        for n, t, _ in chapters[:3]: print(f"  ch{n:03d} {t[:40]}")
        print("  ...")
        for n, t, _ in chapters[-2:]: print(f"  ch{n:03d} {t[:40]}")
        if nums[:-1] and nums[1:] and prologue: print("  序列(除楔子):", nums[1:6], "...", nums[-3:])
        return

    if prologue is None:
        if nums != list(range(1, args.chapters + 1)):
            die(f"序列异常: {nums[:5]}...{nums[-5:]}（期望 1-{args.chapters}）——零产物退出，先 --probe 核对回目", 2)
    else:
        if nums[1:] != list(range(1, args.chapters + 1)):
            die(f"序列异常: {nums[:6]}...{nums[-5:]}（期望楔子+1-{args.chapters}）——零产物退出，先 --probe 核对回目", 2)

    dst = Path(args.dst); dst.mkdir(parents=True, exist_ok=True)
    index = []
    blob = []          # 1.1.0 C1/C2：累计入库正文，用于算"实际入库内容"指纹
    for num, title, body in chapters:
        fn = dst / (f"ch000.txt" if num == 0 else f"ch{num:03d}.txt")
        body_clean = "\n".join(body).strip() + "\n"
        label = (args.prologue or "楔子") if num == 0 else f"第{num:03d}回"
        payload = f"{label}　{title}\n\n{body_clean}"
        fn.write_text(payload, encoding="utf-8")
        blob.append(payload)
        index.append((num, title, len(body_clean)))
    # 1.1.0 C1/C2（指纹边界）：原 source_sha256 只覆盖原始文件字节，不反映"实际入库的正文"——
    # 经 --skip-head/--skip-tail 切除、--t2s 转换后，同一本子可有完全不同的正文，
    # 引用核对时无法确认手上的文本出自哪一阶段。补 content_sha256（入库正文指纹）与
    # content_stage（正文所处处理阶段），两段指纹并存，"引用边界"才说得清。
    content_sha256 = hashlib.sha256("".join(blob).encode("utf-8")).hexdigest()
    content_stage = ("原文" if not args.t2s else "繁转简") + ("+skip切除" if (args.skip_head or args.skip_tail) else "")

    src_label = args.source or src_path.name
    idx = [f"# {args.book}·回目索引（{args.chapters} 回·{'简体' if args.t2s else '原文'}）", "",
           f"> 底本：{src_label}，{'繁体转简体' if args.t2s else '原文照录'}（{'含' if prologue else '不含'}楔子）。", ""]
    for num, title, n in index:
        lab = (args.prologue or "楔子") if num == 0 else f"第{num:03d}回"
        idx.append(f"- {lab}　{title}（约{n}字）")
    # 1.0.9 A4：索引/回执文件名带版本名（④-1 B 方案）——同父目录多版本互不覆盖
    (dst.parent / f"{dst.name}_回目索引.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    opencc_ver = ""
    if args.t2s:
        try:
            from importlib.metadata import version as _pkgver
            opencc_ver = _pkgver("opencc-python-reimplemented")
        except Exception:
            opencc_ver = "unknown"
    # 入库回执：来源如实动态记录（不写死），指纹/时间/参数供日后对账与复现
    manifest = {"book": args.book, "source": src_label,
                "source_sha256": src_sha256, "source_encoding": src_enc,
                "content_sha256": content_sha256, "content_stage": content_stage,
                "ingested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "t2s": args.t2s, "opencc_version": opencc_ver,
                "chapters": len(index),
                "total_chars": sum(n for _,_,n in index),
                "files": sorted(p.name for p in dst.glob("ch*.txt"))}
    (dst.parent / f"{dst.name}_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK 入库 {len(index)} 单元，总字数≈{manifest['total_chars']}")
    print("首单元:", index[0][1][:40]); print("末单元:", index[-1][1][:40])

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None
    if "--t2s" in sys.argv:
        print("缺 opencc：pip install opencc-python-reimplemented；或去掉 --t2s 以原文照录（繁体）入库", file=sys.stderr); sys.exit(1)
main()
