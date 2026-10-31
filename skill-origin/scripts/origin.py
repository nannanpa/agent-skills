#!/usr/bin/env python3
"""skill-origin 统一入口 — 一次跑完「正宗度 + 实用度」两维，出合并体检报告。

用法:
    python3 origin.py <技能目录名>                  # 单个技能双维体检
    python3 origin.py all                           # 全量体检 ~/.workbuddy/skills/
    python3 origin.py all --dir ~/my-skills          # 自定义目录
    python3 origin.py <名称> --need "你的需求"        # 附需求做匹配度评估
    python3 origin.py all --no-network               # 离线：只跑实用度，跳过联网正宗度

两维独立、互不影响：
  - 正宗度 provenance.audit_skill（联网查 GitHub；离线/失败自动降级跳过）
  - 实用度 prequal.prequal（纯本地零网络，始终可跑）
安全仍转交官方 skills-sec-audit。
"""
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import provenance as pv  # noqa: E402
import prequal as pq      # noqa: E402

SKILLS_DIR = Path.home() / ".workbuddy" / "skills"
_NET_CACHE = None


def network_available(timeout=8):
    """懒探测一次：能否访问 GitHub API。结果缓存，避免每个技能重复探测。"""
    global _NET_CACHE
    if _NET_CACHE is not None:
        return _NET_CACHE
    try:
        req = urllib.request.Request(
            "https://api.github.com",
            headers={"User-Agent": "skill-origin/1.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _NET_CACHE = (r.status == 200)
    except Exception:
        _NET_CACHE = False
    return _NET_CACHE


def audit_origin(d, need="", allow_network=True):
    """合并两维结果，返回 dict。任一维失败都不拖垮整体。"""
    res = {"name": d.name}
    # 实用度（纯本地，始终可跑）
    try:
        res["pq"] = pq.prequal(d, need)
    except Exception as e:  # 兜底：单技能异常不应中断整批
        res["pq"] = {"name": d.name, "tier": "不建议（高风险/玩具）",
                     "score": 0, "three": "?", "over": "?", "run": "?",
                     "findings": [("warn", "实用度预检异常：%s" % e)]}
    # 正宗度（联网；不可用时降级跳过）
    if allow_network and network_available():
        try:
            res["pv"] = pv.audit_skill(d)
        except Exception as e:
            res["pv"] = {"name": d.name, "tier": "？ 核验异常",
                         "verdict": "正宗度核验抛异常：%s" % e}
    else:
        res["pv"] = {"name": d.name, "tier": "⏭ 离线跳过",
                     "verdict": "离线或网络不可用，正宗度未核验；如需核实请联网后单跑 provenance.py"}
    return res


def verdict_of(r):
    """综合两维给一句话建议 + 关键发现摘要。"""
    pq_res = r.get("pq", {})
    pv_res = r.get("pv", {})
    score = pq_res.get("score", 0)
    pv_tier = pv_res.get("tier", "")
    if score < 40:
        advice = "❌ 不建议装（实用度过低）"
    elif score < 65 or "D" in pv_tier or "？" in pv_tier or "跳过" in pv_tier:
        advice = "⚠ 先验证再装"
    else:
        advice = "✅ 可装"
    notes = []
    for sev, msg in pq_res.get("findings", [])[:2]:
        notes.append(msg[:42])
    pv_v = pv_res.get("verdict", "")
    if pv_v:
        notes.append("正宗：" + pv_v[:42])
    key = "；".join(notes) if notes else "无明显短板"
    return advice, key


def main():
    args = sys.argv[1:]
    base = SKILLS_DIR
    need = ""
    allow_network = True
    if "--dir" in args:
        i = args.index("--dir")
        try:
            base = Path(args[i + 1]).expanduser()
        except IndexError:
            print("❌ --dir 需要一个目录路径，例如：origin.py all --dir ~/my-skills")
            sys.exit(1)
        args = args[:i] + args[i + 2:]
    if "--need" in args:
        i = args.index("--need")
        try:
            need = args[i + 1]
        except IndexError:
            print("❌ --need 需要一个需求描述，例如：--need \"我想自动签到领积分\"")
            sys.exit(1)
        args = args[:i] + args[i + 2:]
    if "--no-network" in args:
        allow_network = False
        args = [a for a in args if a != "--no-network"]
    arg = args[0] if args else "all"
    targets = pq.iter_targets(base, arg)
    if not targets:
        print("未找到技能: %s（扫描目录：%s）" % (arg, base))
        return
    if arg != "all" and not (targets[0] / "SKILL.md").exists():
        print("⚠ %s 目录下无 SKILL.md，可能不是有效技能目录" % targets[0].name)

    offline = (not allow_network) or (allow_network and not network_available())
    offline_note = "（离线模式，正宗度跳过）" if offline else ""
    print("# 🧬 skill-origin 双支柱体检报告（%d 个）%s\n" % (len(targets), offline_note))
    print("| 技能 | 正宗度 | 实用度(分) | 综合建议 | 关键发现 |")
    print("|---|---|---|---|---|")
    n = len(targets)
    results = []
    for i, d in enumerate(targets, 1):
        print("[%d/%d] 体检中: %s …" % (i, n, d.name), file=sys.stderr, flush=True)
        r = audit_origin(d, need, allow_network)
        results.append(r)
        advice, key = verdict_of(r)
        pq_tier = r["pq"].get("tier", "?")
        pv_tier = r["pv"].get("tier", "?")
        print("| %s | %s | %s（%d） | %s | %s |" % (
            r["name"], pv_tier, pq_tier, r["pq"].get("score", 0), advice, key[:50]))

    print("\n## 逐技能明细\n")
    for r in results:
        advice, key = verdict_of(r)
        pq_res = r["pq"]
        pv_res = r["pv"]
        print("### %s" % r["name"])
        print("- **正宗度**：%s —— %s" % (pv_res.get("tier", "?"), pv_res.get("verdict", "")))
        print("- **实用度**：%d/100，%s" % (pq_res.get("score", 0), pq_res.get("tier", "?")))
        if pq_res.get("findings"):
            for sev, msg in pq_res["findings"]:
                icon = {"warn": "⚠", "info": "·", "ok": "✓"}.get(sev, "·")
                print("  - %s %s" % (icon, msg))
        else:
            print("  - ✓ 实用度未发现明显短板")
        if need and "fit" in pq_res:
            print("  - 🎯 需求匹配：%s —— %s" % (pq_res["fit"][0], pq_res["fit"][1]))
        print("- **综合建议**：%s" % advice)
        print()

    print("> 分工：本报告「正宗度」由 provenance 提供（联网查 GitHub），「实用度」由 prequal "
          "提供（纯本地）；「安不安全」请对可疑项跑官方 skills-sec-audit。")


if __name__ == "__main__":
    main()
