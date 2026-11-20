#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xlsx-cross-check · 跨表按键匹配 + 汇总核对
首版只收两项：
  1) 跨表按键匹配 —— 多份表按指定键对齐、逐键比对（命中哪些文件、同键异值 diff）。
  2) 汇总核对     —— 比对后出汇总表，且“汇总数字”必须与“源表数字”逐键核对一致。

门禁（写死）：逐键核对全部一致方可交付；任一键超差即停，删未通过产物并报差异项。

用法：
  python compare.py --files t1.xlsx t2.xlsx --key 团队 --value 论文数 --out summary.xlsx
退出码：0=逐键核对一致可交付；1=用法/输入错或核对不一致即停。
"""
import argparse, os, sys
from collections import Counter
from openpyxl import load_workbook, Workbook

TOL = 1e-6


def die(msg):
    """统一中文报错出口：带“怎么办”提示、退 1、不裸抛堆栈。"""
    print(msg)
    sys.exit(1)


def load_table(path, key, value):
    """读单份源表；文件/表头/数值异常一律中文报错退 1。"""
    if not os.path.exists(path):
        die("[输入] 找不到文件：%s。怎么办：检查 --files 里的路径是否写错或文件是否已移动。退出码 1。" % path)
    if not os.path.isfile(path):
        die("[输入] 不是普通文件：%s。怎么办：--files 只接受 xlsx 文件路径。退出码 1。" % path)
    try:
        wb = load_workbook(path, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as exc:
        die("[输入] 文件读取失败（可能损坏或不是有效 xlsx）：%s（%s）。怎么办：用 Excel/WPS 重新另存为 .xlsx 后再跑。退出码 1."
            % (os.path.basename(path), exc))
    if not rows:
        die("[输入] 空表：%s 无任何行。怎么办：确认源表含表头行与数据行。退出码 1。" % os.path.basename(path))
    header = [str(c) if c is not None else "" for c in rows[0]]
    if not any(header):
        die("[输入] 空表头：%s 首行无列名。怎么办：补齐表头（键列名/值列名）后再跑。退出码 1。" % os.path.basename(path))
    if key not in header:
        die("[源表] %s 缺少键列 %r；表头=%s。怎么办：统一各表键列名为 %r，或用正确的 --key。退出码 1."
            % (os.path.basename(path), key, header, key))
    if value not in header:
        die("[源表] %s 缺少值列 %r；表头=%s。怎么办：统一各表值列名为 %r，或用正确的 --value。退出码 1."
            % (os.path.basename(path), value, header, value))
    ki, vi = header.index(key), header.index(value)

    data = []
    for row_no, r in enumerate(rows[1:], start=2):
        if ki >= len(r) or vi >= len(r) or r[ki] in (None, ""):
            continue
        raw = r[vi]
        try:
            v = float(raw) if isinstance(raw, (int, float)) else (
                float(str(raw).strip()) if str(raw).strip() != "" else 0.0)
        except (TypeError, ValueError):
            die("[源表] %s 第 %d 行值列 %r 不是合法数值：%r。怎么办：把该单元格改为数字或留空后再跑。退出码 1."
                % (os.path.basename(path), row_no, value, raw))
        data.append((str(r[ki]), v))

    # X6：同表内重复键显式警告（保持合并行为但不再静默）
    cnt = Counter(k for k, _ in data)
    for k, n in cnt.items():
        if n > 1:
            print("[警告] 源表 %s 内键 %r 重复 %d 次，已按求和合并。"
                  "怎么办：若不应重复，请先核对源表该键的 %d 行。" % (os.path.basename(path), k, n, n))
    return os.path.basename(path), data


def write_summary(out, key, names, keys, key_to_vals):
    """落盘汇总表；输出路径异常中文报错退 1。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws.append([key] + names + ["合计"])
    summary = []
    for k in keys:
        row = [k] + [key_to_vals[k].get(n, 0.0) for n in names]
        row.append(sum(row[1:]))
        summary.append(row)
    for row in summary:
        ws.append(row)
    ws.append(["合计"] + [sum(r[i + 1] for r in summary) for i in range(len(names))] +
              [sum(r[-1] for r in summary)])
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        wb.save(out)
    except Exception as exc:
        die("[输出] 汇总表写入失败：%s（%s）。怎么办：检查 --out 路径是否可写、是否误指向目录。退出码 1."
            % (out, exc))


def read_written_by_key(path, key):
    """回读落盘汇总表，返回 {键: 该行合计}（X1/X3 真对比的数据源）。"""
    try:
        chk = load_workbook(path, data_only=True).active
        rows = list(chk.iter_rows(values_only=True))
    except Exception as exc:
        die("[核对] 回读落盘汇总表失败：%s（%s）。怎么办：确认 --out 路径与刚写出的文件一致。退出码 1."
            % (path, exc))
    if not rows or not rows[0]:
        die("[核对] 落盘汇总表为空或表头缺失：%s。怎么办：重新运行生成汇总表。退出码 1。" % path)
    header = [str(c) if c is not None else "" for c in rows[0]]
    if key not in header or "合计" not in header:
        die("[核对] 落盘汇总表缺 %r 或 '合计' 列：%s。怎么办：重新运行生成汇总表。退出码 1." % (key, path))
    ki, ti = header.index(key), header.index("合计")
    result = {}
    for r in rows[1:]:
        k = r[ki] if ki < len(r) else None
        if k in (None, "", "合计"):
            continue
        tv = r[ti] if ti < len(r) else None
        try:
            result[str(k)] = float(tv) if tv is not None else 0.0
        except (TypeError, ValueError):
            result[str(k)] = 0.0
    return result


def cleanup(out):
    """核对失败即删除未通过产物（X4）。"""
    try:
        if os.path.exists(out):
            os.remove(out)
            print("未通过产物已删除：%s" % out)
    except OSError as exc:
        print("[警告] 未通过产物删除失败：%s（%s）。怎么办：手工删除该文件避免误用。退出码 1." % (out, exc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # X2：同名输入文件去重校验（basename 相同即报错，防互相覆盖）
    names = [os.path.basename(p) for p in args.files]
    dup = {n: c for n, c in Counter(names).items() if c > 1}
    if dup:
        detail = "；".join("%s（%d 次）" % (n, c) for n, c in dup.items())
        paths = "；".join("%s -> %s" % (n, p) for n, p in zip(names, args.files) if n in dup)
        die("[入参] 输入文件 basename 重名会互相覆盖：%s。完整路径：%s。"
            "怎么办：给文件改名使 basename 唯一后再跑。退出码 1." % (detail, paths))

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
            print("      同键异值 diff=%.2f" % (max(vals) - min(vals)))

    # —— 2) 逐键期望：源表每键求和（门禁真值）——
    src_by_key = {k: sum(key_to_vals[k].get(n, 0.0) for n in names) for k in keys}
    src_total = sum(src_by_key.values())

    # —— 3) 落盘汇总表 ——
    write_summary(args.out, args.key, names, keys, key_to_vals)
    print("\n=== 汇总表已写出：%s ===" % args.out)

    # —— 4) 汇总核对门禁：逐键真对比（X1+X3）——
    written_by_key = read_written_by_key(args.out, args.key)
    sum_total = sum(written_by_key.values())
    print("\n=== 汇总核对（门禁·逐键）===")
    print("源表值合计 = %.4f" % src_total)
    print("落盘汇总表每键合计之和（回读） = %.4f" % sum_total)

    diffs = []
    for k in keys:
        sv = src_by_key[k]
        wv = written_by_key.get(k, 0.0)
        ok = abs(sv - wv) < TOL
        print("  [%s] 键=%s | 源表求和=%.4f | 落盘合计=%.4f" %
              ("PASS" if ok else "FAIL", k, sv, wv))
        if not ok:
            diffs.append((k, sv, wv))

    if not diffs and abs(src_total - sum_total) < TOL:
        print("逐键核对一致 → 允许交付。")
        return 0

    # 不一致即停：列真实两侧值、删未通过产物（X4）
    print("核对不一致 → 即停，不交付。逐键差异（源表求和 vs 落盘合计）：")
    for k, sv, wv in diffs:
        print("  - 键=%s 源表求和=%.4f 落盘合计=%.4f 差=%.4f" % (k, sv, wv, wv - sv))
    if abs(src_total - sum_total) >= TOL:
        print("  - 总合计：源表=%.4f 落盘=%.4f 差=%.4f" %
              (src_total, sum_total, sum_total - src_total))
    cleanup(args.out)
    return 1


if __name__ == "__main__":
    sys.exit(main())
