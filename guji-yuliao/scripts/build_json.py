#!/usr/bin/env python3
"""guji-yuliao · JSON 语料源入库（记录列表型，如 gujilab/chinese-classical-corpus）
用法：
  python build_json.py --src zizhi-tongjian.json --dst <dir> --book 资治通鉴 \
      --volume volume --title period --content content \
      [--strip-brackets] [--boilerplate '钦定四库全书|資治通鑑巻|胡三省'] [--t2s] [--probe]
坑位内建：卷首样板行剥离／【】夹注剥离（另存注本）／全局卷号断言／纪分组索引
"""
import argparse, json, re, sys
from pathlib import Path

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None

NUMCH = "零〇○一二三四五六七八九十百"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--volume", default="volume")
    ap.add_argument("--title", default="title")
    ap.add_argument("--content", default="content")
    ap.add_argument("--strip-brackets", action="store_true", help="剥离【】夹注（注不丢，存 _notes 同名文件）")
    ap.add_argument("--title-override", default="", help="手工改题，格式 '102:晋纪二十四,276:后唐纪五'")
    ap.add_argument("--boilerplate", default="", help="卷首样板行的正则（|分隔），命中即删该行")
    ap.add_argument("--t2s", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    records = json.load(open(args.src, encoding="utf-8-sig"))
    assert isinstance(records, list), "期待记录列表型 JSON"
    # 2026-10-19 Windows 回函 3-3 修：t2s 请求但 opencc 缺失 → 硬报错，不得静默跳过转换
    if args.t2s and OpenCC is None:
        print("缺 opencc：pip install opencc-python-reimplemented", file=sys.stderr); sys.exit(1)
    cc = OpenCC("t2s") if args.t2s else None

    boil_re = re.compile(args.boilerplate) if args.boilerplate else None
    bracket_re = re.compile(r"【[^】]*】")

    out_main = Path(args.dst); out_main.mkdir(parents=True, exist_ok=True)
    out_notes = out_main.parent / (out_main.name + "_注本")

    overrides = {}
    if args.title_override:
        for pair in args.title_override.split(","):
            k, v = pair.split(":"); overrides[int(k)] = v.strip()

    index, total_main, total_notes = [], 0, 0
    for rec in records:
        vol = int(rec[args.volume]); title = str(rec[args.title]).strip()
        content = str(rec[args.content])
        if cc: content = cc.convert(content)
        # 标题兜底：override > 源字段 > 正文提取
        if vol in overrides:
            title = overrides[vol]
        elif not title:
            m = re.search(r"([\u4e00-\u9fff]{1,4}纪[零〇○一二三四五六七八九十百]+)", content)
            title = m.group(1) if m else f"卷{vol}"
        # 剥卷首样板行
        if boil_re:
            lines = [ln for ln in content.split("\n") if not boil_re.search(ln)]
            content = "\n".join(lines).strip()
        # 剥【】夹注
        notes_txt = ""
        if args.strip_brackets:
            notes = bracket_re.findall(content)
            notes_txt = "\n".join(notes)
            content = bracket_re.sub("", content)
        fn = out_main / f"ch{vol:03d}.txt"
        fn.write_text(f"卷{vol:03d}　{title}\n\n{content.strip()}\n", encoding="utf-8")
        if args.strip_brackets:
            out_notes.mkdir(parents=True, exist_ok=True)
            (out_notes / f"ch{vol:03d}.txt").write_text(f"卷{vol:03d}　{title}（胡注汇抄）\n\n{notes_txt.strip()}\n", encoding="utf-8")
            total_notes += len(notes_txt)
        index.append((vol, title, len(content)))
        total_main += len(content)

    vols = [v for v, _, _ in index]
    assert vols == list(range(1, len(vols) + 1)), f"卷号不连续: {vols[:5]}...{vols[-5:]}"

    # 索引按 period（纪）分组，组头去掉中文数字尾（周纪一→周纪）
    groups, order = {}, []
    for vol, title, n in index:
        head = re.sub(r"[零〇○一二三四五六七八九十百]+$", "", title) or title
        if head not in groups: groups[head] = []; order.append(head)
        groups[head].append((vol, title, n))

    idx = [f"# {args.book}·卷目索引（{len(index)} 卷·简体）", ""]
    for head in order:
        idx.append(f"## {head}（{len(groups[head])} 卷）")
        for vol, title, n in groups[head]:
            idx.append(f"- 卷{vol:03d}　{title}（约{n}字）")
        idx.append("")
    (out_main.parent / "卷目索引.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    manifest = {"book": args.book, "source": Path(args.src).name, "volumes": len(index),
                "total_chars_main": total_main, "total_chars_notes": total_notes,
                "strip_brackets": args.strip_brackets,
                "files": sorted(p.name for p in out_main.glob("ch*.txt"))}
    (out_main.parent / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK {len(index)} 卷入库，白文≈{total_main} 字" + (f"，注≈{total_notes} 字" if args.strip_brackets else ""))
    print("首卷:", index[0][1], "| 末卷:", index[-1][1])

if __name__ == "__main__":
    main()
