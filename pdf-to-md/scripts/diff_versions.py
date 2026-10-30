#!/usr/bin/env python3
"""diff_versions.py — 比对两个 Markdown 版本的段落差异（pdf-to-md 配套工具，1.2.0 新增）。

用途：规整规则改过一轮之后，需要人工核对"到底哪些字变了"。本工具把两版拆成段，
逐段对齐，输出三类差异：
  · 新增段（新版有、旧版无）
  · 删除段（旧版有、新版无）
  · 改写段（一一配对，相似度达阈值即视为"同一段的两种写法"）

相似度低的配对不硬凑——两段确实无关时，宁可报"新增+删除"，也不谎称"改写"。

用法：
  python3 diff_versions.py 旧.md 新.md [--threshold 0.55] [--max-show 20] [--json]

退出码：0 成功（可能有差异）；1 参数/文件错；2 输入无可比段落。
"""
import argparse
import difflib
import json
import re
import sys


def load_paras(path):
    """读 md，按空行与标题切成段落；表格块按整块保留（不拆行）。"""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"读不到 {path}：{e}", file=sys.stderr)
        sys.exit(1)
    paras, buf, tbl = [], [], []
    for raw in text.splitlines():
        ln = raw.strip()
        if ln.startswith("|"):
            if buf:
                paras.append("\n".join(buf))
                buf = []
            tbl.append(ln)
            continue
        if tbl:
            paras.append("\n".join(tbl))
            tbl = []
        if not ln:
            if buf:
                paras.append("\n".join(buf))
                buf = []
            continue
        if ln.startswith("#"):
            if buf:
                paras.append("\n".join(buf))
                buf = []
            paras.append(ln)
            continue
        buf.append(ln)
    if buf:
        paras.append("\n".join(buf))
    if tbl:
        paras.append("\n".join(tbl))
    return [p for p in paras if p.strip()]


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def main():
    ap = argparse.ArgumentParser(description="比对两个 Markdown 版本的段落差异")
    ap.add_argument("old", help="旧版本 .md")
    ap.add_argument("new", help="新版本 .md")
    ap.add_argument("--threshold", type=float, default=0.55,
                    help="改写判定的相似度阈值（低于此值视为新增+删除，不硬配对）")
    ap.add_argument("--max-show", type=int, default=20, help="每类最多显示多少条")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供程序消费）")
    args = ap.parse_args()

    old = load_paras(args.old)
    new = load_paras(args.new)
    if not old and not new:
        print("两个文件都没有可比段落", file=sys.stderr)
        sys.exit(2)

    sm = difflib.SequenceMatcher(None, old, new)
    added, removed, changed = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            # 先在替换块内做贪心配对，配不上的归为纯新增/纯删除
            used = set()
            for i in range(i1, i2):
                best, best_r = None, 0.0
                for j in range(j1, j2):
                    if j in used:
                        continue
                    r = ratio(old[i], new[j])
                    if r > best_r:
                        best, best_r = j, r
                if best is not None and best_r >= args.threshold:
                    used.add(best)
                    changed.append({"old": old[i], "new": new[best], "sim": round(best_r, 3)})
                else:
                    removed.append(old[i])
            for j in range(j1, j2):
                if j not in used:
                    added.append(new[j])
        elif tag == "delete":
            removed.extend(old[i1:i2])
        elif tag == "insert":
            added.extend(new[j1:j2])

    if args.json:
        print(json.dumps({"old_count": len(old), "new_count": len(new),
                          "added": added, "removed": removed, "changed": changed},
                         ensure_ascii=False, indent=2))
        return

    print(f"=== 段落总数：旧 {len(old)} → 新 {len(new)}")
    print(f"=== 新增 {len(added)} 段｜删除 {len(removed)} 段｜改写 {len(changed)} 段"
          f"（相似度阈值 {args.threshold}）\n")

    if changed:
        print("──── 改写段（同一处的两种写法，逐条核对）────")
        for k, c in enumerate(changed[:args.max_show], 1):
            print(f"[改{k}] 相似度 {c['sim']}")
            print(f"  旧：{c['old']}")
            print(f"  新：{c['new']}\n")
        if len(changed) > args.max_show:
            print(f"…… 另有 {len(changed) - args.max_show} 条改写未显示（--max-show 调整）\n")

    if added:
        print("──── 新增段 ────")
        for k, a in enumerate(added[:args.max_show], 1):
            print(f"[增{k}] {a}")
        if len(added) > args.max_show:
            print(f"…… 另有 {len(added) - args.max_show} 条未显示\n")

    if removed:
        print("──── 删除段 ────")
        for k, r in enumerate(removed[:args.max_show], 1):
            print(f"[删{k}] {r}")
        if len(removed) > args.max_show:
            print(f"…… 另有 {len(removed) - args.max_show} 条未显示\n")

    if not (added or removed or changed):
        print("两版段落内容一致（仅可能存在空白差异）。")


if __name__ == "__main__":
    main()
