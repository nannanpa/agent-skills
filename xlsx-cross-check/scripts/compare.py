#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xlsx-cross-check · 跨表按键匹配 + 汇总核对
首版只收两项：
  1) 跨表按键匹配 —— 多份表按指定键对齐、逐键比对（命中哪些文件、同键异值 diff）。
  2) 汇总核对     —— 比对后出汇总表，且“汇总数字”必须与“源表数字”核对一致。

门禁（写死）：汇总数字与源表核对一致方可交付；不一致即停并报差异项。

用法：
  python compare.py --files t1.xlsx t2.xlsx --key 团队 --value 论文数 --out summary.xlsx
"""
import argparse, os, sys
from openpyxl import load_workbook, Workbook


def load_table(path, key, value):
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c) if c is not None else "" for c in rows[0]]
    if key not in header:
        raise SystemExit(f"[源表] {os.path.basename(path)} 缺少键列 {key!r}；表头={header}")
    if value not in header:
        raise SystemExit(f"[源表] {os.path.basename(path)} 缺少值列 {value!r}；表头={header}")
    ki, vi = header.index(key), header.index(value)
    data = []
    for r in rows[1:]:
        if r[ki] in (None, ""):
            continue
        v = r[vi]
        v = float(v) if isinstance(v, (int, float)) else (float(str(v)) if str(v).strip() != "" else 0.0)
        data.append((str(r[ki]), v))
    return os.path.basename(path), data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tables = [load_table(p, args.key, args.value) for p in args.files]
    names = [t[0] for t in tables]

    # —— 1) 跨表按键匹配 ——
    keys = []
    seen = set()
    for _, data in tables:
        for k, _ in data:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    key_to_vals = {k: {} for k in keys}
    for name, data in tables:
        for k, v in data:
            key_to_vals[k][name] = key_to_vals[k].get(name, 0.0) + v

    print("=== 跨表按键匹配 ===")
    print("源表：%s" % " / ".join(names))
    print("键列=%s  值列=%s" % (args.key, args.value))
    for k in keys:
        present = [n for n in names if n in key_to_vals[k]]
        per = "  ".join("%s=%s" % (n, key_to_vals[k].get(n, "—")) for n in names)
        print("  · %s [%s]  %s" % (k, "∩".join(present), per))
        if len(present) > 1:
            vals = [key_to_vals[k][n] for n in present]
            diff = max(vals) - min(vals)
            print("      同键异值 diff=%.2f" % diff)

    # —— 2) 汇总表 ——
    summary = []
    for k in keys:
        row = [k]
        for n in names:
            row.append(key_to_vals[k].get(n, 0.0))
        total = sum(key_to_vals[k].get(n, 0.0) for n in names)
        row.append(total)
        summary.append(row)

    # 落盘汇总表
    wb = Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws.append([args.key] + names + ["合计"])
    for row in summary:
        ws.append(row)
    ws.append(["合计"] + [sum(r[i + 1] for r in summary) for i in range(len(names))] +
              [sum(r[-1] for r in summary)])
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    wb.save(args.out)
    print("\n=== 汇总表已写出：%s ===" % args.out)

    # —— 汇总核对（门禁）——
    # 门禁必须核对“已落盘的汇总文件”与“源表”，做真实往返校验（防写坏/写漏）。
    src_total = sum(v for _, data in tables for _, v in data)
    # 重新读回刚写出的汇总文件，取“合计”列（末列，去掉最后 totals 行）
    chk = load_workbook(args.out, data_only=True).active
    chk_rows = list(chk.iter_rows(values_only=True))
    chk_header = [str(c) if c is not None else "" for c in chk_rows[0]]
    last_col = len(chk_header) - 1
    written_totals = [float(r[last_col]) for r in chk_rows[1:-1] if r[last_col] not in (None, "")]
    sum_total = sum(written_totals)
    print("\n=== 汇总核对（门禁）===")
    print("源表值合计 = %.4f" % src_total)
    print("落盘汇总表合计（回读） = %.4f" % sum_total)

    if abs(src_total - sum_total) < 1e-6:
        print("核对一致 → 允许交付。")
        return 0
    # 不一致即停并报差异项
    print("核对不一致 → 即停，不交付。逐项差异：")
    for k in keys:
        contrib = sum(key_to_vals[k].get(n, 0.0) for n in names)
        print("  - 键=%s 汇总行合计=%.4f（源表该键贡献=%.4f）" % (k, contrib, contrib))
    print("  → 源表合计 %.4f ≠ 汇总合计 %.4f，差 %.4f" % (src_total, sum_total, src_total - sum_total))
    return 1


if __name__ == "__main__":
    sys.exit(main())
