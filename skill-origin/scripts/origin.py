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
  - 实用度 praccheck.praccheck（纯本地零网络，始终可跑）
安全仍转交官方 skills-sec-audit。
"""
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402  v1.2.2：统一错误码 / 跨平台目录发现
import provenance as pv  # noqa: E402
import praccheck as pq      # noqa: E402

# v1.2.2：默认扫描根改为跨平台自动发现（不再硬绑单一平台）
SKILLS_DIR, _ROOT_ORIGIN = common.discover_skills_dir()
_NET_CACHE = None


def network_available(timeout=8):
    """懒探测一次：能否访问 GitHub API。结果缓存，避免每个技能重复探测。

    v1.2.2：区分失败原因——网络不可达（DNS/被墙/超时）与被限流（403/429）不是一回事，
    给用户的处置建议也不同（前者改网络/走离线，后者等配额恢复）。
    返回 (ok: bool, reason_code: str, detail: str)。
    """
    global _NET_CACHE
    if _NET_CACHE is not None:
        return _NET_CACHE
    try:
        req = urllib.request.Request(
            "https://api.github.com",
            headers={"User-Agent": "skill-origin/1.2.2"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _NET_CACHE = (r.status == 200, "", "")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            _NET_CACHE = (False, "E_NET_RATE_LIMITED", "HTTP %s" % e.code)
        else:
            _NET_CACHE = (False, "E_NET_UNREACHABLE", "HTTP %s" % e.code)
    except urllib.error.URLError as e:
        _NET_CACHE = (False, "E_NET_UNREACHABLE", str(e.reason))
    except Exception as e:
        _NET_CACHE = (False, "E_NET_UNREACHABLE", str(e))
    return _NET_CACHE


def audit_origin(d, need="", allow_network=True, exec_ok=True):
    """合并两维结果，返回 dict。任一维失败都不拖垮整体。

    v1.2.2 修复「国内断网就整维跳过」：旧版网络不可用时直接跳过正宗度，
    连本地就能判的自建/市场件结论也一并丢掉。现改为「本地部分照判、只跳上游实测」——
    断网仍能拿到可用结论，只是权威档位标为未查询。
    """
    res = {"name": d.name}
    # 实用度（纯本地，始终可跑）
    try:
        res["pq"] = pq.praccheck(d, need, exec_ok=exec_ok)
    except Exception as e:  # 兜底：单技能异常不应中断整批
        res["pq"] = {"name": d.name, "tier": "不建议用（高风险/玩具）",
                     "score": 0, "three": "?", "over": "?", "run": "?",
                     "findings": [("warn", "实用度核查异常：%s" % e)]}
    # 正宗度：联网时走完整判定；不联网时仍跑本地可判部分（allow_network=False）
    # v1.2.2：本函数自己探测网络（不依赖 main 是否已探）——直接当库用时行为一致。
    net_reason = ""
    use_net = allow_network
    if allow_network:
        ok, code, detail = network_available()
        if not ok:
            use_net = False
            net_reason = "｜离线：%s%s" % (
                common.ERROR_CODES.get(code, code), ("：" + detail) if detail else "")
    if use_net:
        try:
            res["pv"] = pv.audit_skill(d, allow_network=True)
        except Exception as e:
            res["pv"] = {"name": d.name, "tier": "？ 核验异常",
                         "verdict": "正宗度核验抛异常：%s" % e,
                         "confidence": "低"}
    else:
        try:
            res["pv"] = pv.audit_skill(d, allow_network=False)
        except Exception as e:
            res["pv"] = {"name": d.name, "tier": "？ 核验异常",
                         "verdict": "正宗度核验抛异常：%s" % e,
                         "confidence": "低"}
        if net_reason:
            res["pv"]["verdict"] = ((res["pv"].get("verdict") or "") + net_reason)
    return res


def verdict_of(r):
    """综合两维给一句话建议 + 关键发现摘要。"""
    pq_res = r.get("pq", {})
    pv_res = r.get("pv", {})
    score = pq_res.get("score", 0)
    pv_tier = pv_res.get("tier", "")
    if score < 40:
        advice = "❌ 不建议用（实用度过低）"
    elif score < 65 or "D" in pv_tier or "？" in pv_tier or "跳过" in pv_tier:
        advice = "⚠ 先验证再用于关键场景"
    else:
        advice = "✅ 可放心用"
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
    root_origin = _ROOT_ORIGIN
    need = ""
    allow_network = True
    exec_ok = True
    if "--dir" in args:
        i = args.index("--dir")
        try:
            base = Path(args[i + 1]).expanduser()
            root_origin = "显式指定"
        except IndexError:
            return common.fail("E_ARG_MISSING",
                               "--dir 需要一个目录路径，例如：origin.py all --dir ~/my-skills")
        args = args[:i] + args[i + 2:]
    if "--need" in args:
        i = args.index("--need")
        try:
            need = args[i + 1]
        except IndexError:
            return common.fail("E_ARG_MISSING",
                               "--need 需要一个需求描述，例如：--need \"我想自动签到领积分\"")
        args = args[:i] + args[i + 2:]
    if "--no-network" in args:
        allow_network = False
        args = [a for a in args if a != "--no-network"]
    if "--no-exec" in args:   # v1.2.2：严格零网络——不执行任何样例脚本
        exec_ok = False
        args = [a for a in args if a != "--no-exec"]
    arg = args[0] if args else "all"
    if not base.exists() or not base.is_dir():  # P1-6 边缘兜底：目录不存在/非目录不抛堆栈
        return common.fail("E_DIR_NOT_FOUND", str(base))
    try:
        targets = pq.iter_targets(base, arg)
    except common.SkillOriginError as e:
        return common.fail(e.code, e.detail)
    except OSError as e:
        return common.fail("E_DIR_UNREADABLE", "%s：%s" % (base, e))
    if not targets:
        print("未找到技能: %s（扫描目录：%s）" % (arg, base))
        return
    if arg != "all" and not (targets[0] / "SKILL.md").exists():
        print("⚠ %s 目录下无 SKILL.md，可能不是有效技能目录" % targets[0].name)

    # v1.2.2：断网不再整维跳过——本地可判项照给，上游实测标「未查询」。
    net_ok, net_code, net_detail = (True, "", "") if not allow_network else network_available()
    if allow_network and not net_ok:
        offline_note = "（离线模式：%s%s——仅本地可判项已给出，上游档位未查询）" % (
            common.ERROR_CODES.get(net_code, net_code), ("：" + net_detail) if net_detail else "")
    elif not allow_network:
        offline_note = "（离线模式：仅本地可判项已给出，上游档位未查询）"
    else:
        offline_note = ""
    print("# 🧬 skill-origin 双支柱体检报告（%d 个）%s\n" % (len(targets), offline_note))
    print("> %s｜规则：%s%s\n" % (
        common.describe_root(base, root_origin), common.load_rules()[1],
        "｜已启用 --no-exec：不执行任何样例脚本" if not exec_ok else ""))
    print("| 技能 | 正宗度 | 置信度 | 实用度(分) | 综合建议 | 关键发现 |")
    print("|---|---|---|---|---|---|")
    n = len(targets)
    results = []
    for i, d in enumerate(targets, 1):
        print("[%d/%d] 体检中: %s …" % (i, n, d.name), file=sys.stderr, flush=True)
        r = audit_origin(d, need, allow_network, exec_ok=exec_ok)
        results.append(r)
        advice, key = verdict_of(r)
        pq_tier = r["pq"].get("tier", "?")
        pv_tier = r["pv"].get("tier", "?")
        conf = r["pv"].get("confidence", "低")
        print("| %s | %s | %s | %s（%d） | %s | %s |" % (
            r["name"], pv_tier, conf, pq_tier, r["pq"].get("score", 0), advice, key[:50]))

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

    print("> 分工：本报告「正宗度」由 provenance 提供（联网查 GitHub），「实用度」由 praccheck "
          "提供（纯本地）；「安不安全」请对可疑项跑官方 skills-sec-audit。")


if __name__ == "__main__":
    main()
