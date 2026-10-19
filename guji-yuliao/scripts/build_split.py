#!/usr/bin/env python3
"""guji-yuliao 通用分册入库脚本（古登堡类章回体古籍）
用法：
  探测：python build_split.py --src X.txt --probe
  入库：python build_split.py --src X.txt --dst <dir> --book <书名> --chapters 70 \
        [--prologue 楔子] [--t2s] [--skip-head N] [--skip-tail N]
坑位内建：BOM / 数字写法三态（○作零·连写·行首空格）/ 头尾许可证切除 / 断言连续
"""
import argparse, json, re, sys
from pathlib import Path

NUM = {"零":0,"〇":0,"○":0,"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
def cn2int(s):
    s = s.replace("第","").replace("回","")
    if s.isdigit(): return int(s)
    if s and all(ch in NUM for ch in s):
        return int("".join(str(NUM[ch]) for ch in s))
    total, seg = 0, 0
    for ch in s:
        if ch in NUM: seg = NUM[ch]
        elif ch == "十": total += (seg or 1) * 10; seg = 0
        elif ch == "百": total += (seg or 1) * 100; seg = 0
        else: raise ValueError(f"未知数字字符 {ch} in {s}")
    return total + seg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst")
    ap.add_argument("--book", default="")
    ap.add_argument("--chapters", type=int, default=0, help="期望回数（0=只探测）")
    ap.add_argument("--prologue", default="", help="楔子/序言标题词（存为 ch000）")
    ap.add_argument("--t2s", action="store_true", help="繁转简（需 opencc）")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    raw = Path(args.src).read_text(encoding="utf-8-sig")
    m = re.search(r"\*\*\* START OF.*?\*\*\*", raw)
    raw = raw[m.end():] if m else raw
    m = re.search(r"\*\*\* END OF", raw)
    raw = raw[:m.start()] if m else raw
    text = OpenCC("t2s").convert(raw) if args.t2s else raw

    NUMCH = "零〇○一二三四五六七八九十百"
    # 回目行判据（2026-10-19 Windows 回函 3-1 修）：容忍"是/此"等 0-2 字短前缀；
    # "回"后必须紧跟分隔符（全角空/半角空/冒号）——防"此开卷第一回也"这类正文句误判为回目
    chap_re = re.compile(r"^[\s　]*(?:[^\s第]{0,2})?(第[" + NUMCH + r"]+回)(?=[　：:\s])[:：]?\s*(\S.*?)\s*$", re.M)
    pro_re  = re.compile(r"^[\s　]*(" + (args.prologue or "∧never∧") + r")[\s　]+(\S.*?)\s*$", re.M) if args.prologue else None

    chapters, prologue, cur = [], None, None
    for ln in text.split("\n"):
        mm = chap_re.match(ln.rstrip())
        if mm:
            if cur: chapters.append(cur)
            cur = (cn2int(mm.group(1)), mm.group(2).strip(), [])
            continue
        if pro_re:
            pm = pro_re.match(ln.rstrip())
            if pm and prologue is None:
                prologue = (0, pm.group(2).strip(), [])
                cur = prologue
                continue
        if cur is not None:
            cur[2].append(ln.rstrip())
    if cur and chapters and cur is not chapters[-1]: chapters.append(cur)
    elif cur and not chapters: chapters.append(cur)

    # 楔子与正式回目混排时归位
    if prologue is not None:
        chapters = [c for c in chapters if c[0] != 0 or c is prologue]
        chapters.sort(key=lambda c: c[0])

    nums = [c[0] for c in chapters]
    print(f"探测到 {len(chapters)} 个单元（含楔子={'有' if prologue else '无'}）")
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
        assert nums == list(range(1, args.chapters + 1)), f"序列异常: {nums[:5]}...{nums[-5:]}"
    else:
        assert nums[1:] == list(range(1, args.chapters + 1)), f"序列异常: {nums[:6]}...{nums[-5:]}"

    dst = Path(args.dst); dst.mkdir(parents=True, exist_ok=True)
    index = []
    for num, title, body in chapters:
        fn = dst / (f"ch000.txt" if num == 0 else f"ch{num:03d}.txt")
        body_clean = "\n".join(body).strip() + "\n"
        label = (args.prologue or "楔子") if num == 0 else f"第{num:03d}回"
        fn.write_text(f"{label}　{title}\n\n{body_clean}", encoding="utf-8")
        index.append((num, title, len(body_clean)))

    idx = [f"# {args.book}·回目索引（{args.chapters} 回·简体）", "",
           f"> 底本：Project Gutenberg 电子版，繁体转简体（{'含' if prologue else '不含'}楔子）。", ""]
    for num, title, n in index:
        lab = (args.prologue or "楔子") if num == 0 else f"第{num:03d}回"
        idx.append(f"- {lab}　{title}（约{n}字）")
    (dst.parent / "回目索引.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    manifest = {"book": args.book, "source": "Gutenberg 电子版", "chapters": len(index),
                "total_chars": sum(n for _,_,n in index),
                "files": sorted(p.name for p in dst.glob("ch*.txt"))}
    (dst.parent / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK 入库 {len(index)} 单元，总字数≈{manifest['total_chars']}")
    print("首单元:", index[0][1][:40]); print("末单元:", index[-1][1][:40])

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None
    if "--t2s" in sys.argv:
        print("缺 opencc：pip install opencc-python-reimplemented", file=sys.stderr); sys.exit(1)
main()
