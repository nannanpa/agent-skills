#!/usr/bin/env python3
"""provenance.py 最小回归测试 — 零依赖、纯本地、不联网。

锁定 2026-10-31 对"自建/改造"判定逻辑的修复，防止回潮：
  T1 裸名自建技能（在 SELF_BUILT）→ 自建/改造（兄姐不识弟妹回归）
  T2 带 __发布方 后缀 + meta 的技能，靠 slug/namespace 命中，不靠剥离后缀
  T3 第三方技能带 __ 后缀不得被错归一成白名单成员（禁止剥离 __）
  T4 本人命名空间(indiv-mabin) meta 应数据驱动识别为 自建/改造
  T5 他人命名空间 meta 不应被认作 自建/改造
  ---- 以下为 DSH 外审 P0 修复闭环（T6–T13）----
  T6 仅 slug（无 namespace）不得命中白名单 → 非自建/改造
  T7 仅 source=marketplace（无 skillId）不得得 A 官方市场
  T8 同名 slug + 他人 namespace 不得误判自建/改造
  T9 空 UPSTREAM-MERGE.md 不得算自建/改造
  T10 非 dict meta（列表）不抛异常、降级而非崩批
  T11 正文仅提及 anthropics/skills 不得得 A+ 厂商官方
  T12 死来源链接 + 可用提及 不得落 D（落 ？ 来源声明未解析）
  T13 目录名含仓库短名子串的提及不得升格为来源（source_repos 为空）
  ---- 以下为第 2 轮终审 C1–C3 新增锁（T14–T18）----
  T14 hash 式 marketplace（含真实 腾讯文档/_skillhub_meta.json）→ A 官方市场
  T15 目录名 claude-code + 正文仅提及 anthropics/claude-code（无 SOURCE_HINT）→ ？ 来源未声明（不得 A+）
  T16 判词含"可被伪造"且 provenance.py 全文无"原创度100%"
  T17 marketplace + skillId 但属预置模板(preinstalledTemplate) → 不得 A 官方市场
  T18 main() 批量：坏 meta + 好 meta → 两行都出、退出码 0
"""
from __future__ import annotations  # P0-5：让 dict | None 在 3.9 只当字符串注解

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provenance as pv


def _mk_skill(tmp: Path, name: str, meta=None, body="# test\n", ledger: str | None = None) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\ndescription: x\n---\n" + body, encoding="utf-8")
    if meta is not None:
        (d / "_skillhub_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if ledger is not None:
        (d / "UPSTREAM-MERGE.md").write_text(ledger, encoding="utf-8")
    return d


# ---- 原有 T1–T5（防回潮） ----

def test_self_built_bare_name():
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "skill-miner"))
        assert r["tier"] == "自建/改造", f"应判自建/改造，实得 {r['tier']}"


def test_slug_based_with_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        d = _mk_skill(Path(tmp), "skill-origin__skillhub",
                      {"slug": "skill-origin", "namespace": "indiv-mabin", "source": "skillhub"})
        r = pv.audit_skill(d)
        assert r["tier"] == "自建/改造", f"应判自建/改造，实得 {r['tier']}"


def test_no_suffix_stripping_thirdparty():
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "skill-origin__evil"))
        assert r["tier"] != "自建/改造", f"不得误判自建，实得 {r['tier']}"


def test_own_namespace_datadriven():
    with tempfile.TemporaryDirectory() as tmp:
        d = _mk_skill(Path(tmp), "my-new-skill",
                      {"slug": "my-new-skill", "namespace": "indiv-mabin", "source": "skillhub"})
        r = pv.audit_skill(d)
        assert r["tier"] == "自建/改造", f"应判自建/改造，实得 {r['tier']}"


def test_other_namespace_not_selfbuilt():
    with tempfile.TemporaryDirectory() as tmp:
        d = _mk_skill(Path(tmp), "someone-skill",
                      {"slug": "someone-skill", "namespace": "someone-else", "source": "skillhub"})
        r = pv.audit_skill(d)
        assert r["tier"] != "自建/改造", f"不得误判自建，实得 {r['tier']}"


# ---- T6–T13（DSH 外审 P0 修复闭环） ----

def test_slug_only_not_trusted():
    # T6: 仅 {"slug":"zhiduku"}（无 namespace）→ 不得命中白名单
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes", {"slug": "zhiduku"}))
        assert r["tier"] != "自建/改造", f"仅 slug 不得判自建，实得 {r['tier']}"


def test_marketplace_claim_not_endorsed():
    # T7: 仅 {"source":"marketplace"}（无 skillId）→ 不得得 A 官方市场
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes", {"source": "marketplace"}))
        assert r["tier"] != "A 官方市场", f"缺 skillId 不得 A 官方市场，实得 {r['tier']}"


def test_same_slug_other_author():
    # T8: 同名 slug + 他人 namespace → 不得误判自建/改造
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes",
                                     {"slug": "zhiduku", "namespace": "someone-else"}))
        assert r["tier"] != "自建/改造", f"他人 namespace 不得判自建，实得 {r['tier']}"


def test_empty_ledger():
    # T9: 空 UPSTREAM-MERGE.md → 不算自建/改造
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes", ledger=""))
        assert r["tier"] != "自建/改造", f"空台账不得判自建，实得 {r['tier']}"


def test_malformed_meta_degrades():
    # T10: 非 dict meta（JSON 列表）→ audit_skill 必须抛异常（交由 provenance.py all
    # 的 try/except 降级为「？ 核验异常」），而非被静默吞掉当无 meta
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "bad-meta"
        d.mkdir()
        (d / "SKILL.md").write_text("---\ndescription: x\n---\n# t\n", encoding="utf-8")
        (d / "_skillhub_meta.json").write_text(json.dumps(["x"]), encoding="utf-8")  # 列表，非 dict
        try:
            pv.audit_skill(d)
        except AssertionError:
            raise
        except Exception:
            return  # 预期：抛异常，由 main() 降级为「？ 核验异常」
        raise AssertionError("非 dict meta 应抛异常，但被静默吞掉（未降级为 ？ 核验异常）")


def test_mention_does_not_grant_aplus():
    # T11: 正文仅提及 github.com/anthropics/skills → 不得得 A+ 厂商官方
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes",
                                     body="可参考 https://github.com/anthropics/skills 的写法\n"))
        assert r["tier"] != "A+ 厂商官方", f"提及不得授 A+，实得 {r['tier']}"


def test_dead_source_falls_back():
    # T12: 死来源链接 + 可用提及 → 不落 D（落 ？ 来源声明未解析）
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes",
                                     body="来源：https://github.com/dead/gone123\n另外参考 https://github.com/anthropics/skills 可看\n"))
        assert r["tier"] != "D 无背书", f"死链+提及不得落 D，实得 {r['tier']}"


def test_suffix_substring_no_source():
    # T13: 目录名含仓库短名子串的提及不得升格为来源
    # 用 foo-bar__skillhub + 仓库 x/bar（"bar" 是目录名子串，但非 SOURCE_HINT 词）；
    # 旧代码会把"仓库短名是目录名子串"判为来源，新代码已移除该推断。
    with tempfile.TemporaryDirectory() as tmp:
        d = _mk_skill(Path(tmp), "foo-bar__skillhub",
                      body="see https://github.com/x/bar\n")
        src, _ment = pv.collect_repos(d, d.name)
        assert src == [], f"仓库短名子串匹配不应升格为来源，实得 {src}"


# ---- T14–T18（第 2 轮终审 C1–C3 新增锁） ----

def test_hash_only_marketplace_gets_marketplace():
    # T14: marketplace 门槛改为 skillId or installedContentHash 二选一（C1）。
    # 合成：无 skillId、仅有 installedContentHash → 必须 A 官方市场。
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes",
                                     {"source": "marketplace", "installedContentHash": "sha256:abc"}))
        assert r["tier"] == "A 官方市场", f"hash 式 marketplace 应判 A，实得 {r['tier']}"
    # 真实：用本机 腾讯文档/_skillhub_meta.json（source=marketplace、有 installedContentHash、无 skillId）→ A。
    real = Path.home() / ".workbuddy" / "skills" / "腾讯文档" / "_skillhub_meta.json"
    if real.exists():
        meta = json.loads(real.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            r2 = pv.audit_skill(_mk_skill(Path(tmp), "腾讯文档", meta=meta, body="# 腾讯文档\n"))
            assert r2["tier"] == "A 官方市场", f"真实腾讯文档 meta 应判 A，实得 {r2['tier']}"


def test_name_substring_does_not_grant_source():
    # T15: 目录名 claude-code + 正文仅提及 github.com/anthropics/claude-code（无 SOURCE_HINT 词）
    # → ？ 来源未声明（C2：删除名字包含推断后，提及不再升格为来源，更不得 A+）。
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "claude-code",
                                     body="实现参考了 https://github.com/anthropics/claude-code 的设计\n"))
        assert r["tier"] == "？ 来源未声明", f"名字包含官方仓名+提及应为 ？ 来源未声明，实得 {r['tier']}"
        assert r["tier"] != "A+ 厂商官方", f"名字包含不得授 A+，实得 {r['tier']}"


def test_verdict_honest_no_100pct_claim():
    # T16: 自建/改造判词必须含"可被伪造"（诚实免责）；且 provenance.py 全文不得出现"原创度100%"
    # （判词回潮锁定：曾经的绝对化措辞不得复活）。
    src = (Path(__file__).resolve().parent / "provenance.py").read_text(encoding="utf-8")
    assert "原创度100%" not in src, "provenance.py 全文不得出现'原创度100%'"
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "skill-miner"))
        v = r["verdict"]
        assert "可被伪造" in v, f"判词应含'可被伪造'，实得：{v}"


def test_marketplace_template_not_endorsed():
    # T17: marketplace + skillId 但属预置模板(preinstalledTemplate) → 不得 A 官方市场（C1 排除项）。
    with tempfile.TemporaryDirectory() as tmp:
        r = pv.audit_skill(_mk_skill(Path(tmp), "free-notes",
                                     {"source": "marketplace", "skillId": "skill_123",
                                      "preinstalledTemplate": True}))
        assert r["tier"] != "A 官方市场", f"预置模板不得 A 官方市场，实得 {r['tier']}"


def test_main_batch_degrades_both_rows():
    # T18: main() 批量：坏 meta（非 dict 列表）+ 好 meta → 两行都出、退出码 0（P0-4 整批不中断）。
    import io
    import contextlib
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 坏 meta：JSON 列表（非 dict）→ 应降级「？ 核验异常」
        bad = tmp / "badmeta"
        bad.mkdir()
        (bad / "SKILL.md").write_text("---\ndescription: x\n---\n# t\n", encoding="utf-8")
        (bad / "_skillhub_meta.json").write_text(json.dumps(["x"]), encoding="utf-8")
        # 好 meta：marketplace + hash → A 官方市场，证明整批未因坏 meta 停摆
        good = _mk_skill(tmp, "good", {"source": "marketplace", "installedContentHash": "sha256:good"})
        old_argv, old_dir, old_fetch = sys.argv, pv.SKILLS_DIR, pv.fetch_repo
        pv.SKILLS_DIR = tmp
        pv.fetch_repo = lambda full_name: None
        out = io.StringIO()
        rc = None
        try:
            sys.argv = ["provenance.py", "all"]
            with contextlib.redirect_stdout(out):
                pv.main()
        finally:
            sys.argv, pv.SKILLS_DIR, pv.fetch_repo = old_argv, old_dir, old_fetch
        printed = out.getvalue()
    assert rc is None, f"main() 不应触发 SystemExit，实得 {rc}"
    assert "badmeta" in printed and "？ 核验异常" in printed, f"坏 meta 行未出现：{printed}"
    assert "good" in printed, f"好 meta 行未出现：{printed}"


def main():
    # 关键：mock 掉 GitHub 网络调用，保证离线确定性
    pv.fetch_repo = lambda full_name: None
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
