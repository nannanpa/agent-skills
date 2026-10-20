#!/usr/bin/env python3
"""guji-yuliao · JSON 语料源入库（记录列表型，如 gujilab/chinese-classical-corpus）
用法：
  python build_json.py --src zizhi-tongjian.json --dst <dir> --book 资治通鉴 \
      --volume volume --title period --content content \
      [--strip-brackets] [--boilerplate '钦定四库全书|資治通鑑巻|胡三省'] [--t2s] [--probe]
坑位内建：卷首样板行剥离／【】夹注剥离（另存注本）／全局卷号断言／纪分组索引
退出码约定：0=成功；1=环境/输入错误（文件不存在、缺依赖、JSON 结构不对）；2=数据预警（卷号不连续，零产物，核对后重跑）
注：--strip-brackets 默认开启（夹注不丢，另存 _注本）；要保留在正文用 --keep-brackets。--boilerplate 不设默认——样板行因本而异，静默删行违背零意外原则，须显式指定。
"""
import argparse, hashlib, json, re, sys
from datetime import datetime
from pathlib import Path

def die(msg, code=2):
    """统一退出：code 1=环境/输入错误，2=数据预警（零产物）。"""
    print(msg, file=sys.stderr); sys.exit(code)

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
    ap.add_argument("--strip-brackets", dest="strip_brackets", action="store_true", default=True,
                    help="剥离【】夹注（默认开启；注不丢，存 _注本 同名文件）")
    ap.add_argument("--keep-brackets", dest="strip_brackets", action="store_false",
                    help="把【】夹注保留在正文中（不另存注本）")
    ap.add_argument("--title-override", default="", help="手工改题，格式 '102:晋纪二十四,276:后唐纪五'")
    ap.add_argument("--boilerplate", default="", help="卷首样板行的正则（|分隔），命中即删该行；因本而异须显式指定，不填则不剥")
    ap.add_argument("--t2s", action="store_true")
    ap.add_argument("--source", default="", help="来源说明（默认记 src 文件名）")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    # 入库回执（2026-10-19 扩）：底本指纹取原始文件字节
    src_path = Path(args.src)
    if not src_path.exists():
        die(f"找不到源文件：{src_path}（--src 需完整绝对路径）", 1)
    src_sha256 = hashlib.sha256(src_path.read_bytes()).hexdigest()

    # 编码读取（1.0.7 补）：UTF-8 失败自动回退 GB18030，回执记 source_encoding
    try:
        records = json.loads(src_path.read_text(encoding="utf-8-sig")); src_enc = "utf-8-sig"
    except UnicodeDecodeError:
        records = json.loads(src_path.read_text(encoding="gb18030")); src_enc = "gb18030"
        print("⚠️ UTF-8 解码失败，已按 GB18030 读取（回执 source_encoding=gb18030）", file=sys.stderr)
    if not isinstance(records, list):
        die("期待记录列表型 JSON（根节点应为数组；当前不是）——检查源结构，必要时先做一层展开", 1)
    # 2026-10-19 Windows 回函 3-3 修：t2s 请求但 opencc 缺失 → 硬报错，不得静默跳过转换
    if args.t2s and OpenCC is None:
        print("缺 opencc：pip install opencc-python-reimplemented；或去掉 --t2s 以原文照录（繁体）入库", file=sys.stderr); sys.exit(1)
    cc = OpenCC("t2s") if args.t2s else None

    boil_re = re.compile(args.boilerplate) if args.boilerplate else None
    bracket_re = re.compile(r"【[^】]*】")

    # 写文件前先做全局卷号预检（1.0.7：卷号异常时真零产物——此前检查在写文件后，会留半成品；预检置于建目录前）
    try:
        pre_vols = [int(rec[args.volume]) for rec in records]
    except (KeyError, ValueError, TypeError) as e:
        die(f"卷号字段读取失败（--volume 映射 '{args.volume}'）：{e}——检查源字段名与取值", 1)
    if pre_vols != list(range(1, len(pre_vols) + 1)):
        die(f"卷号不连续: {pre_vols[:5]}...{pre_vols[-5:]}——零产物退出（未写任何文件），核对源数据卷号", 2)

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

    # 1.0.7：卷号连续性已在写文件前预检（die exit 2），此处不再重复

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
    opencc_ver = ""
    if args.t2s:
        try:
            from importlib.metadata import version as _pkgver
            opencc_ver = _pkgver("opencc-python-reimplemented")
        except Exception:
            opencc_ver = "unknown"
    manifest = {"book": args.book, "source": args.source or src_path.name,
                "source_sha256": src_sha256, "source_encoding": src_enc,
                "ingested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "t2s": args.t2s, "opencc_version": opencc_ver,
                "volumes": len(index),
                "total_chars_main": total_main, "total_chars_notes": total_notes,
                "strip_brackets": args.strip_brackets,
                "files": sorted(p.name for p in out_main.glob("ch*.txt"))}
    (out_main.parent / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK {len(index)} 卷入库，白文≈{total_main} 字" + (f"，注≈{total_notes} 字" if args.strip_brackets else ""))
    print("首卷:", index[0][1], "| 末卷:", index[-1][1])

if __name__ == "__main__":
    main()
