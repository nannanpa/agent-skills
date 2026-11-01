#!/usr/bin/env python3
"""praccheck.py 最小回归测试 — 零依赖、纯本地、不联网。

锁定 v1.2.1「核查功能独立测试」补齐（评测 completeness 点名 praccheck 缺独立测试）：
  T1 结构完整技能 → 优（≥85）
  T2 缺三件套（无 FAQ、无示例）→ three 标缺
  T3 描述含动作词但无载体 → 疑似夸大
  T4 --need 需求匹配返回 fit
  T5 脚本含硬编码路径 → 运行风险 warn
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import praccheck as pq


def _mk(tmp: Path, name: str, *, body: str, readme: str | None = "# r\n", script: str | None = None) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\ndescription: 一个普通技能\n---\n" + body, encoding="utf-8")
    if readme is not None:
        (d / "README.md").write_text(readme, encoding="utf-8")
    if script is not None:
        sd = d / "scripts"
        sd.mkdir(exist_ok=True)
        (sd / "run.py").write_text(script, encoding="utf-8")  # 无 __main__，不会被实跑探测
    return d


def test_full_score_skill():
    body = (
        "# 标题\n## FAQ\n常见问题：如何上手？\n## 示例\n用法示例见下：\n```\npython x.py\n```\n"
        "更多场景：批量处理、定时任务。\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        r = pq.praccheck(_mk(Path(tmp), "good", body=body))
        assert r["score"] >= 85, f"结构完整应≥85，实得 {r['score']}"
        assert "优" in r["tier"], f"应判优，实得 {r['tier']}"
        assert r["three"] == "齐", f"三件套应齐，实得 {r['three']}"


def test_missing_threesome():
    body = "# 标题\n就一句说明，内容很短。\n"
    with tempfile.TemporaryDirectory() as tmp:
        r = pq.praccheck(_mk(Path(tmp), "thin", body=body, readme=None))
        assert "缺" in r["three"], f"应标缺三件套，实得 {r['three']}"


def test_overpromise_no_backing():
    fm = "---\ndescription: 自动批量抓取并转换所有文档\n---\n"
    body = "# 标题\n只是说明型正文，很短。\n"
    with tempfile.TemporaryDirectory() as tmp:
        d = _mk(Path(tmp), "big", body=body)
        (d / "SKILL.md").write_text(fm + body, encoding="utf-8")
        r = pq.praccheck(d)
        assert "疑似" in r["over"], f"应判疑似夸大，实得 {r['over']}"


def test_need_fit_returns():
    body = "# 标题\n## FAQ\n常见问题。\n## 示例\n```\n用法\n```\n场景：自动签到领积分。\n"
    with tempfile.TemporaryDirectory() as tmp:
        r = pq.praccheck(_mk(Path(tmp), "fit", body=body), need="我想自动签到领积分")
        assert "fit" in r, "传 --need 应返回 fit"
        assert r["fit"][0] in ("高匹配", "部分匹配", "低匹配/可能不匹配"), f"fit 异常：{r['fit']}"


def test_hardcoded_path_warn():
    script = "# 引用了本机绝对路径\ncfg = '/Users/whoami/.config/foo.json'\n"
    body = "# 标题\n## FAQ\nq?\n## 示例\n```\nok\n```\n"
    with tempfile.TemporaryDirectory() as tmp:
        r = pq.praccheck(_mk(Path(tmp), "hc", body=body, script=script))
        msgs = [m for _, m in r["findings"]]
        assert any("硬编码" in m for m in msgs), f"应提示硬编码路径，实得 {msgs}"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  💥 {t.__name__}: 异常 {e}")
    print(f"\n{'全部通过（%d/%d）' % (len(tests) - failed, len(tests)) if failed == 0 else str(failed) + ' 项失败'}（共 {len(tests)} 项）")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
