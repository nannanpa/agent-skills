#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多篇同构材料横切复核 · 四维必做

四维：D1 序号连续性 / D2 目标条格式 / D3 跨篇重复指标 / D4 篇幅分布
依赖：python-docx（宿主自带或 DSH 内置运行时均可）

用法：
    python3 hecha.py doc  路径/到/*.docx          # 逐篇体检
    python3 hecha.py cross 路径/到/*.docx         # 横切：重复指标 + 篇幅表
    python3 hecha.py doc f.docx --json            # 机读
退出码：0 全部通过；1 有告警；2 参数/依赖错误
"""
import sys

try:
    import docx  # noqa: F401
except ImportError:
    sys.stderr.write(
        "[E1] 缺 python-docx。\n"
        "  我已做的：未改动任何文件。\n"
        "  需要你做的：换带 python-docx 的解释器，例如 DSH 内置运行时\n"
        "  <python>/bin/python3（见宿主文档），或 pip install python-docx。\n"
    )
    raise SystemExit(2)

import argparse
import json
import re
from collections import Counter
from pathlib import Path

DASH = "——"
SEQ_RE = re.compile(r"^(\d{1,2})[.．、](?!\d)")
SUB_RE = re.compile(r"^[（(][一二三四五六七八九十]+[）)]")
CHA_RE = re.compile(r"^[一二三四五六七八九十]+、")
METRIC_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)(万|亿|%|项|个|家|人|篇|门|种|次|台|套|所|条|万元)")


def load_paras(path):
    doc = docx.Document(str(path))
    out = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            out.append((t, (p.style.name if p.style is not None else "") or ""))
    return out


def is_heading(text, style):
    st = style.lower()
    if "heading" in st or "标题" in st:
        return True
    return bool((SUB_RE.match(text) or CHA_RE.match(text)) and len(text) < 80)


def analyze(path):
    paras = load_paras(path)
    text = "".join(t for t, _ in paras)
    chars = len(re.sub(r"\s", "", text))

    # D1：近似"单条编号列表"——全文顺序扫描，允许重新从 1 起（新列表），
    # 其余必须严格加 1；跳号与重号都会被抓到。
    issues = []
    seq_n = 0
    expect = 1
    for i, (t, st) in enumerate(paras):
        m = SEQ_RE.match(t)
        if not m:
            continue
        n = int(m.group(1))
        seq_n += 1
        if n == 1:
            expect = 2
            continue
        if n != expect:
            issues.append({"段": i + 1, "序号": n, "应为": expect})
        expect = n + 1

    goals = [t for t, _ in paras if t.startswith(DASH)]
    goal_kw = [t for t, _ in paras if ("目标" in t or "指标" in t) and 10 <= len(t) <= 300]
    fmt_bad = bool(goal_kw) and not goals

    metrics = Counter(f"{a}{b}" for a, b in METRIC_RE.findall(text))

    return {
        "文件": Path(path).name,
        "段数": len(paras),
        "字数_去空白": chars,
        "序号项": seq_n,
        "序号问题": issues,
        "目标条_破折号": len(goals),
        "目标条_关键词": len(goal_kw),
        "格式异常": fmt_bad,
        "指标": dict(metrics),
    }


def cmd_doc(paths, as_json):
    rows = [analyze(p) for p in paths]
    bad = [r for r in rows if r["序号问题"] or r["格式异常"]]
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"{'文件':<28}{'段':>4}{'字数':>7}{'序号项':>6}{'目标条':>6}{'问题':>5}")
        for r in rows:
            print(f"{r['文件'][:26]:<28}{r['段数']:>4}{r['字数_去空白']:>7}"
                  f"{r['序号项']:>6}{r['目标条_破折号']:>6}{len(r['序号问题']):>5}")
        for r in bad:
            for it in r["序号问题"]:
                print(f"[D1] {r['文件']} 段{it['段']}: 序号 {it['序号']}，应接 {it['应为']}")
            if r["格式异常"]:
                print(f"[D2] {r['文件']}: 有 {r['目标条_关键词']} 条含'目标/指标'的行，"
                      f"却无一条以'{DASH}'开头 → 未用目标条体")
    return 1 if bad else 0


def cmd_cross(paths, as_json):
    rows = [analyze(p) for p in paths]
    cols = [r["字数_去空白"] for r in rows]
    cs = sorted(cols)
    # §四 D4：少于 5 篇不报中位——两篇时中位就是较大那篇，没有意义，只看极差
    med = cs[len(cs) // 2] if len(cs) >= 5 else 0
    over = [r for r in rows if med and r["字数_去空白"] > med * 1.3]

    # D3 分两层：篇内重复（同一篇同一数值出现 ≥2 次，多为"目标写一遍、举措再写一遍"）
    #            跨篇金额类（万/亿/元，≥3 篇）——占比类不列，同构材料里 90%/70% 属正常。
    def is_metric(k):
        """只把金额/比例，以及两位数以上的数量当"指标"；
        1个/2项 这类通用量词重复无信息量，不报。"""
        num, unit = re.match(r"^(\d+(?:\.\d+)?)(.*)$", k).groups()
        if unit in ("万", "亿", "元", "%", "万元"):
            return True
        return float(num) >= 10 and unit in ("项", "人", "门", "个", "家", "种", "次", "台", "套", "所", "条", "篇")

    within = []
    for r in rows:
        for k, v in r["指标"].items():
            if v >= 2 and is_metric(k):
                within.append({"文件": r["文件"], "数值": k, "次数": v})
    money = {}
    for r in rows:
        for k, v in r["指标"].items():
            if re.search(r"(万|亿|元)$", k):
                money.setdefault(k, {"篇": set(), "次": 0})
                money[k]["篇"].add(r["文件"])
                money[k]["次"] += v
    cross_money = {k: {"出现篇数": len(v["篇"]), "总次数": v["次"]}
                   for k, v in money.items() if len(v["篇"]) >= 3}

    payload = {
        "篇数": len(rows),
        "篇幅": sorted([{"文件": r["文件"], "字数": r["字数_去空白"]} for r in rows],
                     key=lambda x: -x["字数"]),
        "篇幅_最小": min(cols) if cols else 0,
        "篇幅_中位": med,
        "篇幅_最大": max(cols) if cols else 0,
        "超中位1.3倍": [r["文件"] for r in over],
        "篇内重复": within,
        "跨篇金额类": cross_money,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        med_txt = str(payload['篇幅_中位']) if payload['篇幅_中位'] else "未报（少于 5 篇）"
        print(f"[D4] 篇幅：共 {payload['篇数']} 篇，最小 {payload['篇幅_最小']}，"
              f"中位 {med_txt}，最大 {payload['篇幅_最大']}")
        for r in payload["篇幅"]:
            flag = "  ← 超中位 1.3 倍" if r["文件"] in payload["超中位1.3倍"] else ""
            print(f"  {r['字数']:>7}  {r['文件'][:52]}{flag}")
        print(f"\n[D3a] 篇内重复（同篇同数值 ≥2 次）：{len(within)} 处")
        for it in within[:40]:
            print(f"  {it['数值']:<8} ×{it['次数']:<3}{it['文件'][:46]}")
        print(f"\n[D3b] 跨篇金额类（万/亿/元，≥3 篇）：{len(cross_money)} 组")
        for k, v in sorted(cross_money.items(), key=lambda kv: -kv[1]["出现篇数"])[:20]:
            print(f"  {k:<10} {v['出现篇数']} 篇 / {v['总次数']} 次")
    bad = bool(over) or bool(within) or any(r["序号问题"] or r["格式异常"] for r in rows)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="多篇同构材料横切复核")
    ap.add_argument("mode", choices=["doc", "cross"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    paths = [Path(f) for f in a.files]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        sys.stderr.write("[E2] 文件不存在：\n  " + "\n  ".join(missing) + "\n")
        return 2
    # 非 .docx 一律整批中止，不静默过滤：横切判据（篇幅中位、跨篇重复）
    # 依赖同构集完整，跳过一篇就是用错样本集却不报错。
    non_docx = [str(p) for p in paths if p.suffix.lower() != ".docx"]
    if non_docx:
        sys.stderr.write(
            "[E3] 发现非 .docx 输入，已整批中止（没有部分复核）：\n  "
            + "\n  ".join(non_docx) + "\n"
            "  我已做的：未读取任何文件、未输出任何判据结论、未改动任何文件。\n"
            "  需要你做的：先把这些文件转成 .docx，再整批重跑——\n"
            "    .doc → .docx：macOS `textutil -convert docx -output X.docx X.doc`；"
            "Windows 用 Word 另存为；Linux `soffice --headless --convert-to docx`。\n"
            "    PDF：本技能不支持（版面流转文本不可复现，判据会失真），请人工核；"
            "不要转成 docx 充当输入。\n"
            "  为什么整批中止：少一篇，篇幅中位数与跨篇重复就会偏，"
            "跳过＝用错样本集却不报错。\n"
        )
        return 2
    return cmd_doc(paths, a.json) if a.mode == "doc" else cmd_cross(paths, a.json)


if __name__ == "__main__":
    sys.exit(main())
