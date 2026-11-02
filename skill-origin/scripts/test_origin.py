#!/usr/bin/env python3
"""origin.py 最小回归测试 — 零依赖、纯本地、不联网（mock 网络/审计）。

锁定 v1.2.1「统一入口独立测试」补齐（评测 completeness 点名 origin 缺独立测试）：
  T1 离线模式：pv 标 ⏭ 离线跳过，整函数不崩、pq 正常
  T2 审计抛异常：pv 降级 ？ 核验异常，不拖垮整体
  T3 正常两维：返回合并 dict 与综合建议
  T4 main() 扫描不存在目录：不抛堆栈、正常退出（P1-6 边缘兜底）
"""
from __future__ import annotations

import io
import sys
import contextlib
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import origin as og
import praccheck as pq


def _mk(tmp: Path, name: str) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "---\ndescription: x\n---\n# t\n## FAQ\nq?\n## 示例\n```\nok\n```\n", encoding="utf-8")
    (d / "README.md").write_text("# r\n", encoding="utf-8")
    return d


def _raise(d):
    raise RuntimeError("boom")


def test_offline_mode():
    """v1.2.2：断网不再整维跳过——本地可判项照给，上游档位标「？ 上游未查询」。"""
    old = og.network_available
    og.network_available = lambda timeout=8: (False, "E_NET_UNREACHABLE", "测试模拟断网")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _mk(Path(tmp), "s")
            r = og.audit_origin(d)
            assert r["pv"]["tier"] == "？ 上游未查询", f"离线应标上游未查询，实得 {r['pv']['tier']}"
            assert "score" in r["pq"], "pq 应正常返回"
            assert r["pv"].get("confidence") == "低", "未能取证应为低置信度"
    finally:
        og.network_available = old


def test_offline_keeps_local_marketplace_tier():
    """v1.2.2 反例：断网时，本地元数据能判的市场件仍应给 A 官方背书（旧版整维跳过→白丢结论）。"""
    old = og.network_available
    og.network_available = lambda timeout=8: (False, "E_NET_UNREACHABLE", "断网")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _mk(Path(tmp), "s")
            (d / "_meta.json").write_text(
                '{"slug": "s", "source": "marketplace", "skillId": "123", "ownerId": "9",'
                ' "publishedAt": 1700000000000, "version": "1.0.0"}', encoding="utf-8")
            r = og.audit_origin(d)
            assert r["pv"]["tier"] == "A 官方背书", f"断网也应保留本地背书判定，实得 {r['pv']['tier']}"
            assert r["pv"].get("confidence") == "中", "本地元数据证据应为中置信度"
    finally:
        og.network_available = old


def test_audit_exception_degrades():
    old_net, old_audit = og.network_available, og.pv.audit_skill
    og.network_available = lambda timeout=8: (True, "", "")
    og.pv.audit_skill = _raise
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _mk(Path(tmp), "s")
            r = og.audit_origin(d)  # 不应抛出
            assert r["pv"]["tier"] == "？ 核验异常", f"异常应降级，实得 {r['pv']['tier']}"
    finally:
        og.network_available, og.pv.audit_skill = old_net, old_audit


def test_normal_merge():
    fake_pv = {"name": "s", "tier": "自建/改造", "verdict": "v"}
    old_net, old_audit = og.network_available, og.pv.audit_skill
    og.network_available = lambda timeout=8: (True, "", "")
    og.pv.audit_skill = lambda d, allow_network=True: dict(fake_pv)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _mk(Path(tmp), "s")
            r = og.audit_origin(d)
            assert r["pv"]["tier"] == "自建/改造"
            advice, _ = og.verdict_of(r)
            assert advice in ("✅ 可放心用", "⚠ 先验证再用于关键场景", "❌ 不建议用"), f"建议异常：{advice}"
    finally:
        og.network_available, og.pv.audit_skill = old_net, old_audit


def test_main_missing_dir_no_crash():
    old_argv, old_dir = sys.argv, og.SKILLS_DIR
    og.SKILLS_DIR = Path("/nonexistent/path/that/does/not/exist/xyz")
    out = io.StringIO()
    try:
        sys.argv = ["origin.py", "all"]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            og.main()
    finally:
        sys.argv, og.SKILLS_DIR = old_argv, old_dir
    assert "不存在" in out.getvalue(), f"应提示目录不存在，实得 {out.getvalue()[:200]}"


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
