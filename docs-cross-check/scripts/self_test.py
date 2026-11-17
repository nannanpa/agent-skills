#!/usr/bin/env python3
"""self_test.py · docs-cross-check 自检（2026-11-17 评测驱动新增）

评测点名"缺少长期稳定的自动验证方式，后续更新可能出现结果不一致"——本脚本就是那个长期验证锚：
在临时目录用 python-docx 构造正反例样本，对 hecha.py 的判据与错误码逐项断言，任何一项不符即 FAIL。
用法：python3 "$SKILL_DIR/scripts/self_test.py"        （退出码 0=全部通过，1=有失败）
依赖：与 hecha.py 相同（python3 + python-docx）。
样本断言口径与 §四判据、§三退出码逐字一致；判据改了这里必须同步改——两处不一致即发布阻断。"""
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
HECHA = os.path.join(HERE, "hecha.py")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (("　| " + detail) if detail and not cond else ""))


def make_docx(path, paras):
    """paras: [(text, style_name_or_None)]；style=None 用默认 Normal。"""
    from docx import Document

    d = Document()
    for text, style in paras:
        p = d.add_paragraph(text)
        if style:
            try:
                p.style = d.styles[style]
            except KeyError:
                pass
    d.save(path)
    return path


def run(args):
    return subprocess.run([sys.executable, HECHA] + args, capture_output=True, text=True, timeout=60)


def main():
    from docx import Document  # noqa: F401  提前暴露 E1：self_test 与 hecha.py 同依赖

    tmp = tempfile.mkdtemp(prefix="dcs_test_")
    try:
        # ── 样本组 1：偶数篇中位（D4 口径，2026-11-16 修复项）──
        # 注意：D4 判据"少于 5 篇不报中位"，须 ≥5 篇且偶数才能触发"两值平均"路径 → 用 6 篇
        sizes = [1000, 2000, 3000, 4000, 5000, 6000]
        paths = []
        for i, n in enumerate(sizes, 1):
            paths.append(make_docx(os.path.join(tmp, f"p{i}.docx"),
                                   [("测试文档" * (n // 4), None)]))
        r = run(["cross"] + paths)
        m = re.search(r"中位[：:\s]*([\d,]+)", r.stdout)
        check("偶数篇中位取两值平均（3000+4000)/2=3500", m and m.group(1).replace(",", "") == "3500",
              f"stdout 片段：{r.stdout[-200:] if r.stdout else r.stderr[-200:]}")
        j = run(["cross"] + paths + ["--json"])
        try:
            payload = json.loads(j.stdout[j.stdout.index("{"):])
            check("--json 篇幅_中位=3500 且字段名逐字一致",
                  payload.get("篇幅_中位") == 3500 and payload.get("篇数") == 6,
                  f"篇幅_中位={payload.get('篇幅_中位')!r} 篇数={payload.get('篇数')!r}")
        except Exception as e:
            check("--json 可解析", False, str(e))

        # ── 样本组 2：D1 跳号（同一列表 2→4；D1/D2 明细只在 doc 模式输出）──
        jump = make_docx(os.path.join(tmp, "jump.docx"), [
            ("一、目标", "Heading 1"),
            ("1. 甲项", None), ("2. 乙项", None), ("4. 丙项", None),
        ])
        good = make_docx(os.path.join(tmp, "good.docx"), [
            ("一、目标", "Heading 1"),
            ("1. 甲项", None), ("2. 乙项", None),
        ])
        r = run(["doc", jump, good])
        check("D1 跳号检出（2→4）", "[D1]" in r.stdout and "应接 3" in r.stdout, r.stdout[-300:])
        r2 = run(["cross", good, jump])
        check("两篇交叉不误报重号（各自从 1 起）", "[D1]" in r2.stdout and "重号" not in r2.stdout.split("[D1]")[1].split("\n")[0] if "[D1]" in r2.stdout else True, "")

        # ── 样本组 3：E3 非 .docx / E4 损坏 / E5 加密（OLE2 魔数）──
        fake_txt = os.path.join(tmp, "notdoc.txt")
        with open(fake_txt, "w") as f:
            f.write("这不是 docx")
        r = run(["doc", fake_txt])
        check("E3 非 .docx 整批中止、退出码 2", r.returncode == 2 and "[E3]" in r.stderr, f"rc={r.returncode}")

        broken = os.path.join(tmp, "broken.docx")
        with open(broken, "wb") as f:
            f.write(b"this is not a zip container at all")
        r = run(["doc", broken])
        check("E4 损坏 .docx 整批中止、退出码 2", r.returncode == 2 and "[E4]" in r.stderr, f"rc={r.returncode}")

        encrypted = os.path.join(tmp, "encrypted.docx")
        with open(encrypted, "wb") as f:
            f.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512)  # OLE2 魔数＝加密/受保护容器
        r = run(["doc", encrypted])
        check("E5 加密 .docx 独立错误码、退出码 2", r.returncode == 2 and "[E5]" in r.stderr, f"rc={r.returncode}")

        mixed = run(["doc", good, fake_txt])
        check("混合输入不静默过滤（E3 优先、无部分结论）", mixed.returncode == 2 and "结论" not in mixed.stdout, "")

        # ── 样本组 4：D2 目标条（关键词段须 ≥10 字符才计入，正文段、全文无——体 → 未归一）──
        d2bad = make_docx(os.path.join(tmp, "d2bad.docx"), [
            ("工作目标如下，明确建设任务与考核指标。", None), ("1. 到2030年完成建设", None), ("2. 完成15项任务", None),
        ])
        r = run(["doc", d2bad])
        check("D2 该用——体但用 1. 体被点名", "[D2]" in r.stdout and "未用目标条体" in r.stdout, r.stdout[-200:])
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== self_test 汇总：{len(RESULTS) - len(fails)}/{len(RESULTS)} 通过 ====")
    if fails:
        print("失败项：", "；".join(fails))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
