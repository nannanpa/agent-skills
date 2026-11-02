#!/usr/bin/env python3
"""v1.2.2 专项回归测试 — 评测 versionId 478512 点名问题的反例锁定。

零依赖、纯本地、不联网（网络调用一律 mock）。覆盖：
  A. 限流识别全覆盖（403 空 body / 429 / 二次限流 / Retry-After）→ 不得误判"仓库不存在"
  B. 网络不可达与限流分开报（不可达≠无背书）
  C. 最佳仓库选择：厂商官方优先于星数（高星非官方不得压过官方）
  D. 目录/参数异常统一错误码、不吐裸 traceback
  E. 需求匹配三通道（关键词 / bigram / 能力类目）
  F. 判定规则可外部配置
  G. 置信度标注映射
  H. 样例执行期外网阻断（零网络承诺的强隔离）
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import provenance as pv
import praccheck as pq


class FakeHeaders(dict):
    """支持大小写不敏感 .get() 的假 headers。"""

    def get(self, k, default=None):
        for kk, vv in self.items():
            if kk.lower() == k.lower():
                return vv
        return default


def _http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError(
        "https://api.github.com/repos/x/y", code, "mock error",
        FakeHeaders(headers or {}), io.BytesIO(body))


def _mock_urlopen(exc):
    def _f(req, timeout=None):
        raise exc
    return _f


# ── A. 限流识别全覆盖 ─────────────────────────────────────────────────────
def test_403_empty_body_is_rate_limited():
    """v1.2.2 反例：403 且 body 为空、headers 无限流标记 → 旧实现会当成「仓库不存在」→ 误判 D 档。"""
    old = pv.urllib.request.urlopen
    pv.urllib.request.urlopen = _mock_urlopen(_http_error(403))
    try:
        assert pv.fetch_repo("a/b") == "RATE_LIMITED", "403 空 body 应判限流，不得当不存在"
    finally:
        pv.urllib.request.urlopen = old


def test_429_empty_body_is_rate_limited():
    old = pv.urllib.request.urlopen
    pv.urllib.request.urlopen = _mock_urlopen(_http_error(429))
    try:
        assert pv.fetch_repo("a/b") == "RATE_LIMITED", "429 应判限流"
    finally:
        pv.urllib.request.urlopen = old


def test_secondary_rate_limit_detected():
    old = pv.urllib.request.urlopen
    pv.urllib.request.urlopen = _mock_urlopen(
        _http_error(403, b"You have exceeded a secondary rate limit"))
    try:
        assert pv.fetch_repo("a/b") == "RATE_LIMITED", "二次限流应判限流"
    finally:
        pv.urllib.request.urlopen = old


def test_retry_after_header_detected():
    old = pv.urllib.request.urlopen
    pv.urllib.request.urlopen = _mock_urlopen(
        _http_error(403, b"", {"Retry-After": "60"}))
    try:
        assert pv.fetch_repo("a/b") == "RATE_LIMITED", "带 Retry-After 的 403 应判限流"
    finally:
        pv.urllib.request.urlopen = old


def test_404_is_not_rate_limited():
    """404 是「确实不存在」，不得误判成限流（限流≠无背书，但 404 就是没有）。"""
    old = pv.urllib.request.urlopen
    pv.urllib.request.urlopen = _mock_urlopen(_http_error(404))
    try:
        assert pv.fetch_repo("a/b") is None, "404 应返回 None（不存在），不得判限流"
    finally:
        pv.urllib.request.urlopen = old


# ── B. 网络不可达与限流分开 ───────────────────────────────────────────────
def test_network_unreachable_distinguished():
    old = pv.urllib.request.urlopen
    pv.urllib.request.urlopen = _mock_urlopen(
        urllib.error.URLError("Name or service not known"))
    try:
        assert pv.fetch_repo("a/b") == "NETWORK_UNREACHABLE", "网络不可达应单独标记"
    finally:
        pv.urllib.request.urlopen = old


# ── C. 厂商官方优先于星数 ─────────────────────────────────────────────────
def _mk_skill(base: Path, name: str, body: str = "") -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "---\ndescription: x\n---\n# t\n" + body, encoding="utf-8")
    return d


def test_official_org_beats_higher_star_non_official():
    """v1.2.2 反例：高星非官方不得压过厂商官方——官方背书比星数硬。"""
    infos = {
        "openai/toolkit": {"full_name": "openai/toolkit", "stargazers_count": 10,
                           "fork": False, "pushed_at": "2026-01-01T00:00:00Z"},
        "randomuser/toolkit": {"full_name": "randomuser/toolkit", "stargazers_count": 9999,
                               "fork": False, "pushed_at": "2026-01-01T00:00:00Z"},
    }
    old = pv.fetch_repo
    pv.fetch_repo = lambda full_name: infos.get(full_name)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _mk_skill(Path(tmp), "free-notes",
                          "来源：https://github.com/openai/toolkit\n"
                          "来源：https://github.com/randomuser/toolkit\n")
            r = pv.audit_skill(d)
            assert r["tier"] == "A+ 厂商官方", f"官方应优先选中，实得 {r['tier']}"
            assert r["confidence"] == "高", "GitHub 实测应为高置信度"
    finally:
        pv.fetch_repo = old


# ── D. 统一错误码 ─────────────────────────────────────────────────────────
def test_missing_dir_raises_coded_error():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            pq.iter_targets(Path(tmp) / "nope-not-here", "all")
            raise AssertionError("目录不存在应抛受控异常")
        except common.SkillOriginError as e:
            assert e.code == "E_DIR_NOT_FOUND", f"错误码应为 E_DIR_NOT_FOUND，实得 {e.code}"


def test_fail_formats_code():
    buf = io.StringIO()
    rc = common.fail("E_NET_RATE_LIMITED", "测试", stream=buf)
    assert rc == 1, "fail() 应返回退出码 1"
    out = buf.getvalue()
    assert "E_NET_RATE_LIMITED" in out and "GitHub API 限流" in out, f"提示格式不对：{out}"


# ── E. 需求匹配三通道 ─────────────────────────────────────────────────────
def test_need_fit_keyword_channel():
    v, detail = pq.need_fit("我想自动签到领积分", "本技能用于自动签到并领取积分，批量处理。")
    assert v == "高匹配", f"关键词命中应判高匹配，实得 {v}（{detail}）"
    assert "关键词命中" in detail, f"应报告关键词命中情况：{detail}"


def test_need_fit_unrelated_is_low():
    v, _ = pq.need_fit("我想做一个量子化学模拟器", "本技能用于技能溯源与实用度核查。")
    assert v.startswith("低"), f"无关需求应判低匹配，实得 {v}"


# ── F. 规则可外部配置 ─────────────────────────────────────────────────────
def test_rules_load_from_json():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "r.json"
        p.write_text(json.dumps({"top_star": 500, "official_orgs": ["myorg"]}),
                     encoding="utf-8")
        rules, note = common.load_rules(str(p))
        assert rules["top_star"] == 500, f"外部规则应生效，实得 {rules['top_star']}"
        assert rules["official_orgs"] == ["myorg"], "白名单应被外部配置覆盖"
        assert "显式" in note, f"应说明规则来源，实得 {note}"


def test_rules_invalid_falls_back():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "r.json"
        p.write_text("{ this is not json", encoding="utf-8")
        rules, note = common.load_rules(str(p))
        assert rules["top_star"] == common.DEFAULT_RULES["top_star"], "坏配置应回退默认"
        assert "回退" in note, f"应说明已回退，实得 {note}"


# ── G. 置信度映射 ─────────────────────────────────────────────────────────
def test_confidence_mapping():
    assert common.confidence_of("A+ 厂商官方") == "高"
    assert common.confidence_of("自建/改造") == "中"
    assert common.confidence_of("D 无背书") == "低"
    assert common.confidence_of("？ API受限") == "低"
    assert common.confidence_of("未知档位") == "低", "未知档位应保守记低"


# ── H. 样例执行期外网阻断 ─────────────────────────────────────────────────
def test_sandbox_env_blocks_network_and_drops_token():
    os.environ["GITHUB_TOKEN"] = "secret-token-for-test"
    try:
        env = pq._sandbox_env()
        assert env.get("http_proxy") == "http://127.0.0.1:9", "应把代理指向阻断端口"
        assert env.get("https_proxy") == "http://127.0.0.1:9", "https 也应阻断"
        assert "GITHUB_TOKEN" not in env, "子进程不应携带 GITHUB_TOKEN"
        assert env.get("SKILL_ORIGIN_SANDBOX") == "1", "应标记沙箱环境"
    finally:
        os.environ.pop("GITHUB_TOKEN", None)


def test_no_exec_skips_sample_execution():
    """--no-exec 时不得执行任何样例脚本（严格零网络）。"""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "s"
        d.mkdir()
        (d / "SKILL.md").write_text("---\ndescription: x\n---\n# t\n", encoding="utf-8")
        (d / "README.md").write_text("# r\n", encoding="utf-8")
        scripts = d / "scripts"
        scripts.mkdir()
        (scripts / "demo.py").write_text(
            "print('SHOULD NOT RUN')\n"
            "if __name__ == '__main__':\n    print('ran')\n", encoding="utf-8")
        res = pq.example_run(d, [scripts / "demo.py"], exec_ok=False)
        assert res["status"] == "skipped", f"应跳过执行，实得 {res['status']}"
        assert res["bytes"] == 0, "跳过时不应有产出字节"


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
            print(f"  💥 {t.__name__}: 异常 {type(e).__name__}: {e}")
    print(f"\n{'全部通过（%d/%d）' % (len(tests) - failed, len(tests)) if failed == 0 else str(failed) + ' 项失败'}（共 {len(tests)} 项）")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
