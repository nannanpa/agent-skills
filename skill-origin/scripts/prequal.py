#!/usr/bin/env python3
"""技能实用度预检 — 安装前甄别技能“好不好使、值不值得装”，与溯源(provenance)互补。

用法:
    python3 prequal.py <技能目录名>                         # 预检单个
    python3 prequal.py all                                  # 批量预检 ~/.workbuddy/skills/
    python3 prequal.py all --dir ~/my-skills                 # 自定义目录（进度走 stderr）
    python3 prequal.py <技能目录名> --need "我想自动签到领积分"   # 附需求做匹配度评估

分工：provenance.py 管“正不正宗”（需联网查 GitHub）；本脚本管“实不实用”
（纯本地、零网络、零依赖）。安全疑虑仍转交官方 skills-sec-audit。

判定维度（详见 SKILL.md「实用度预检」章节）：
    ① 结构齐备   ② 三件套(异常处理/FAQ/多场景示例)  ③ 描述诚实度
    ④ 运行风险(第三方依赖/硬编码路径/凭证需求)       ⑤ 需求匹配度(--need)
    ⑥ 实跑验证(骨架→长大中)：py_compile 编译 + __main__ 入口 --help 启动探测 + 样例脚本实际执行并核对输出非空（纯本地、零网络）
"""
import re
import sys
import subprocess
import py_compile
from pathlib import Path

SKILLS_DIR = Path.home() / ".workbuddy" / "skills"

# 声称“会动手”的描述词；若技能无实现载体却含这些词 → 疑似口号型/demo。
ACTION_VERBS = ("自动", "一键", "生成", "调用", "抓取", "爬取", "解析",
               "批量", "导出", "转换", "发送", "部署", "读写", "自动化", "api")

# 三件套判定词
FAQ_HINT = re.compile(r"FAQ|常见问题|问答", re.I)
EXAMPLE_HINT = re.compile(r"示例|例子|场景|用法|quick ?start|用例", re.I)

# 常见标准库（用于依赖识别；Python 3.10+ 有 sys.stdlib_module_names，下面兜底）
STD_FALLBACK = {
    "os", "sys", "re", "json", "math", "time", "datetime", "pathlib", "subprocess",
    "argparse", "collections", "itertools", "functools", "typing", "random", "string",
    "textwrap", "shutil", "glob", "hashlib", "base64", "urllib", "csv", "io", "logging",
    "tempfile", "traceback", "warnings", "enum", "dataclasses", "abc", "copy", "html",
    "xml", "sqlite3", "zlib", "gzip", "uuid", "platform", "signal", "threading",
    # 3.9 无 sys.stdlib_module_names，下面这些常用 stdlib 需显式兜底，否则被误判为第三方依赖
    "__future__", "contextlib", "inspect", "types", "functools", "operator",
}

HARDCODED_PATH_RE = re.compile(r'/Users/[^\s\x22\x27)]+|/home/[^\s\x22\x27)]+')
ENV_HINT = re.compile(r"环境变量|API[ _]?KEY|密钥|api[_ ]?key|access[_ ]?key", re.I)

SCRIPT_EXT = (".py", ".sh", ".js", ".ts", ".rb", ".go", ".pl")


def std_modules():
    return getattr(sys, "stdlib_module_names", set()) or STD_FALLBACK


def iter_targets(base: Path, arg: str):
    if arg == "all":
        return sorted(p for p in base.iterdir()
                      if p.is_dir() and (p / "SKILL.md").exists()
                      and not p.name.startswith(".") and ".bak" not in p.name)
    return [base / arg]


def read_text(p: Path) -> str:
    try:
        return p.read_text(errors="ignore")
    except Exception:
        return ""


def collect_scripts(skill_dir: Path):
    out = []
    sd = skill_dir / "scripts"
    if sd.is_dir():
        for f in sd.rglob("*"):
            if f.is_file() and f.suffix.lower() in SCRIPT_EXT:
                out.append(f)
    return out


def check_structure(skill_dir: Path):
    has_readme = (skill_dir / "README.md").exists() or (skill_dir / "readme.md").exists()
    scripts = collect_scripts(skill_dir)
    has_refs = any((skill_dir / d).is_dir()
                   for d in ("references", "reference", "assets", "templates"))
    return has_readme, scripts, has_refs


def check_threesome(skill_dir: Path, scripts, text_all: str):
    """用户发版纪律：异常处理 / FAQ / 多场景示例，缺一不发。"""
    exc = False
    for s in scripts:
        t = read_text(s)
        if re.search(r"\btry\b|\bexcept\b|\braise\b|catch|错误处理|fallback", t, re.I):
            exc = True
            break
    faq = bool(FAQ_HINT.search(text_all))
    code_blocks = len(re.findall(r"```", text_all))
    multi_example = bool(EXAMPLE_HINT.search(text_all)) or code_blocks >= 2
    missing = []
    if scripts and not exc:
        missing.append("异常处理")
    if not faq:
        missing.append("FAQ")
    if not multi_example:
        missing.append("多场景示例")
    return {"exc": exc, "faq": faq, "example": multi_example,
            "missing": missing, "code_blocks": code_blocks}


def check_overpromise(skill_dir: Path, scripts, description: str, has_refs: bool, body_len: int):
    """描述诚实度：声称自动动作却无实现载体(脚本/参考/详尽说明) → 疑似口号型/demo。
    纯提示词型技能靠 SKILL.md 指令工作，只要正文足够详尽即视为实现支撑，避免误伤。"""
    has_action = any(v.lower() in description.lower() for v in ACTION_VERBS)
    impl_backed = bool(scripts) or has_refs or body_len >= 1000
    if has_action and not impl_backed:
        return ("warn", "描述声称自动动作，但技能无脚本/参考且说明过简，疑似口号型或 demo")
    if has_action and impl_backed:
        return ("ok", "描述含动作词且有实现载体（脚本/参考/详尽说明）")
    return ("ok", "描述偏说明型，无明显夸大")


def check_runnability(scripts):
    findings = []
    third_party = set()
    hardcoded = False
    std = std_modules()
    self_path = Path(__file__).resolve()
    local_mods = {s.stem for s in scripts}  # 技能自带脚本，互 import 不算第三方依赖
    for s in scripts:
        if s.resolve() == self_path:  # 跳过本脚本自身，避免扫描自己的源码产生自匹配
            continue
        t = read_text(s)
        if HARDCODED_PATH_RE.search(t):
            hardcoded = True
        for m in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", t, re.M):
            mod = m.group(1).split(".")[0]
            if mod in std or mod in local_mods:
                continue
            third_party.add(mod)
    if hardcoded:
        findings.append(("warn", "脚本含硬编码绝对路径，换机/换用户可能失败，建议参数化"))
    if third_party:
        findings.append(("warn", "依赖第三方库：%s（需 pip 安装，非开箱即用）" %
                         ", ".join(sorted(third_party))))
    return findings


def check_env_need(text_all: str):
    if ENV_HINT.search(text_all):
        return ("warn", "文档提及 API key/环境变量/密钥，使用前需自备凭证并注意安全")
    return ("ok", "")


def runtime_smoke(skill_dir: Path, scripts):
    """实跑冒烟(骨架)：编译 + 启动探测，验证技能脚本至少「能加载、能启动」。

    这是把 prequal 从「静态词法 lint」推向「真能跑」的起步骨架；不做深度语义 / 输出
    正确性验证（那是行星级质量审计该做的，留待后续长大）。纯本地、零网络；仅对 .py 做
    py_compile +（含 __main__ 守卫时）`--help` 启动探测，超时 8s。局限：不验证实际功能、
    不核实输出正确，仅证明「脚本不崩、能起」。
    """
    findings = []
    compiles = launches = crashes = timeouts = dep_miss = compile_errs = 0
    for s in scripts:
        if s.suffix.lower() != ".py":
            continue
        # 1) 编译检查：能否解析/加载（抓 SyntaxError/IndentationError）
        try:
            py_compile.compile(str(s), doraise=True)
            compiles += 1
        except py_compile.PyCompileError as e:
            compile_errs += 1
            last = str(e).strip().splitlines()[-1][:60] if str(e).strip() else "未知编译错误"
            findings.append(("warn", "脚本 %s 编译失败（语法错误）：%s" % (s.name, last)))
            continue
        # 2) 启动探测：仅对含 __main__ 守卫的入口脚本尝试 --help（限量前 3 个，防卡批）
        if "__main__" not in read_text(s):
            continue
        launches += 1
        if launches > 3:
            break
        try:
            proc = subprocess.run(
                [sys.executable, str(s), "--help"],
                cwd=str(skill_dir), capture_output=True, text=True, timeout=8)
            out = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode == 0:
                continue  # 正常启动并打印帮助
            if "Traceback" in out or "Error" in out or "Exception" in out:
                if "ModuleNotFoundError" in out or "ImportError" in out:
                    dep_miss += 1
                    snippet = out.strip().splitlines()[-1][:60]
                    findings.append(("warn", "脚本 %s 启动缺依赖：%s" % (s.name, snippet)))
                else:
                    crashes += 1
                    snippet = out.strip().splitlines()[-1][:60]
                    findings.append(("warn", "脚本 %s 启动即崩：%s" % (s.name, snippet)))
            # 其余（如 --help 不被识别的参数错误）不记为硬失败
        except subprocess.TimeoutExpired:
            timeouts += 1
            findings.append(("warn", "脚本 %s 启动超时（可能阻塞/需交互），建议人工确认" % s.name))
        except FileNotFoundError:
            pass
    if not scripts:
        summary = "无脚本(纯提示词技能，暂不验证)"
    elif launches == 0:
        summary = "编译%d(无__main__入口，未启探)" % compiles
    else:
        summary = "编译%d/启动探%d" % (compiles, min(launches, 3))
    return {"findings": findings, "summary": summary, "compiles": compiles,
            "launches": launches, "crashes": crashes, "timeouts": timeouts,
            "dep_miss": dep_miss, "compile_errs": compile_errs}


def example_run(skill_dir: Path, scripts):
    """实跑验证(长大层)：执行技能自带的样例/演示脚本，核对「能跑出东西」。

    runtime_smoke 只证明「能加载、能启动」(--help 不报错)；本层进一步实际运行样例脚本
    (命名约定 demo/example/example_demo/run_example/sample/smoke)，验证其默认调用能产生
    非空输出、退出码为 0、无 Traceback。这是把 prequal 从「矮行星」推向「质量审计行星」
    的关键一层：不仅不崩，还要真能产出。纯本地、零网络、超时 8s；不跑主入口无参调用
    (避免副作用)，只跑显式样例脚本。
    """
    EXAMPLE_NAMES = {"demo", "example", "example_demo", "run_example", "sample", "smoke"}
    cands = [s for s in scripts
             if s.suffix.lower() == ".py" and s.stem.lower() in EXAMPLE_NAMES
             and "__main__" in read_text(s)]
    if not cands:
        return {"status": "none", "summary": "无样例脚本(仅启动探)", "findings": [],
                "bytes": 0, "rc": None}
    s = cands[0]
    try:
        proc = subprocess.run(
            [sys.executable, str(s)], cwd=str(skill_dir),
            capture_output=True, text=True, timeout=8)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "summary": "样例执行超时",
                "findings": [("warn", "样例脚本 %s 执行超时（可能阻塞/需交互），建议人工确认" % s.name)],
                "bytes": 0, "rc": None}
    except FileNotFoundError:
        return {"status": "none", "summary": "无样例脚本(解释器缺失)", "findings": [], "bytes": 0, "rc": None}
    out = (proc.stdout or "") + (proc.stderr or "")
    nbytes = len((proc.stdout or "").encode("utf-8", "ignore"))
    if proc.returncode != 0 or "Traceback" in out or "Error" in out:
        snippet = out.strip().splitlines()[-1][:60] if out.strip() else "未知错误"
        return {"status": "fail", "summary": "样例执行失败",
                "findings": [("warn", "样例脚本 %s 执行失败(rc=%s)：%s" % (s.name, proc.returncode, snippet))],
                "bytes": nbytes, "rc": proc.returncode}
    if not (proc.stdout or "").strip():
        return {"status": "empty", "summary": "样例运行无输出",
                "findings": [("info", "样例脚本 %s 运行成功但无输出，实用度存疑" % s.name)],
                "bytes": 0, "rc": proc.returncode}
    return {"status": "ok", "summary": "样例已执行(产出%d字节)" % nbytes,
            "findings": [], "bytes": nbytes, "rc": proc.returncode}


def bigrams(s: str):
    s = re.sub(r"\s+", "", s)
    return set(s[i:i + 2] for i in range(len(s) - 1))


def need_fit(need: str, text_all: str):
    nb = bigrams(need)
    if not nb:
        return ("—", "未提供有效需求")
    sb = bigrams(text_all)
    hit = nb & sb
    cov = len(hit) / len(nb)
    if cov >= 0.5:
        v = "高匹配"
    elif cov >= 0.25:
        v = "部分匹配"
    else:
        v = "低匹配/可能不匹配"
    return (v, "需求关键词命中率 %.0f%%（启发式，仅供参考，最终以人工判断为准）" % (cov * 100))


def prequal(skill_dir: Path, need: str = ""):
    r = {"name": skill_dir.name}
    skill_md = skill_dir / "SKILL.md"
    text_all = read_text(skill_md)
    # frontmatter description
    desc = ""
    if text_all.startswith("---"):
        end = text_all.find("\n---", 3)
        fm = text_all[:end] if end > 0 else ""
        m = re.search(r"^description:\s*(.+)$", fm, re.M)
        if m:
            desc = m.group(1).strip().strip('"').strip("'")

    has_readme, scripts, has_refs = check_structure(skill_dir)
    three = check_threesome(skill_dir, scripts, text_all + read_text(skill_dir / "README.md"))
    body_len = len(text_all)
    if text_all.startswith("---"):
        e = text_all.find("\n---", 3)
        if e > 0:
            body_len = len(text_all[e + 4:])
    over = check_overpromise(skill_dir, scripts, desc, has_refs, body_len)
    run = check_runnability(scripts)
    env = check_env_need(text_all)
    smoke = runtime_smoke(skill_dir, scripts)  # 实跑冒烟(骨架)
    ex = example_run(skill_dir, scripts)        # 实跑验证(长大层)：样例执行 + 输出核对

    # 结构档
    r["struct"] = "脚本%d/README%s/参考%s" % (
        len(scripts), "有" if has_readme else "无", "有" if has_refs else "无")
    r["three"] = "齐" if not three["missing"] else "缺:" + "/".join(three["missing"])
    r["over"] = "OK" if over[0] == "ok" else "疑似夸大"
    r["run"] = "无" if not run else "注:%s" % run[0][1][:24]
    r["findings"] = []
    if not has_readme:
        r["findings"].append(("info", "无 README，使用说明缺失"))
    if three["missing"]:
        r["findings"].append(("info", "三件套缺: " + "/".join(three["missing"])))
    if over[0] == "warn":
        r["findings"].append(("warn", over[1]))
    for sev, msg in run:
        r["findings"].append((sev, msg))
    if env[0] == "warn":
        r["findings"].append(("warn", env[1]))
    for sev, msg in smoke["findings"]:
        r["findings"].append((sev, msg))
    for sev, msg in ex["findings"]:
        r["findings"].append((sev, msg))
    r["smoke"] = smoke["summary"] + "｜样例:" + ex["status"]

    # 评分与档位（扣分制，起点 100）
    score = 100
    if not has_readme:
        score -= 10
    score -= 8 * len(three["missing"])
    if over[0] == "warn":
        score -= 25
    score -= 12 * sum(1 for s, _ in run if s == "warn")
    if env[0] == "warn":
        score -= 5
    # 实跑(骨架+长大层)保守扣分：编译错/启动崩/样例失败为硬失败，超时/缺依赖/样例超时轻罚
    score -= 8 * smoke["compile_errs"]
    score -= 10 * smoke["crashes"]
    score -= 5 * smoke["timeouts"]
    score -= 5 * smoke["dep_miss"]
    if ex["status"] == "fail":
        score -= 10
    elif ex["status"] == "timeout":
        score -= 5
    score = max(0, score)

    hard = over[0] == "warn" or any(s == "warn" for s, _ in run)
    if score >= 85 and not hard:
        r["tier"] = "优（可放心装）"
    elif score >= 65:
        r["tier"] = "良（可用，注意点见下）"
    elif score >= 40:
        r["tier"] = "慎用（先验证再装）"
    else:
        r["tier"] = "不建议（高风险/玩具）"
    r["score"] = score

    if need:
        r["fit"] = need_fit(need, text_all + read_text(skill_dir / "README.md"))
    return r


def main():
    args = sys.argv[1:]
    base = SKILLS_DIR
    need = ""
    if "--dir" in args:
        i = args.index("--dir")
        try:
            base = Path(args[i + 1]).expanduser()
        except IndexError:
            print("❌ --dir 需要一个目录路径，例如：prequal.py all --dir ~/my-skills")
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
    arg = args[0] if args else "all"
    targets = iter_targets(base, arg)
    if not targets:
        print("未找到技能: %s（扫描目录：%s）" % (arg, base))
        return
    if arg != "all" and not (targets[0] / "SKILL.md").exists():
        print("⚠ %s 目录下无 SKILL.md，可能不是有效技能目录" % targets[0].name)

    print("# 🧪 技能实用度预检报告（%d 个）\n" % len(targets))
    print("| 技能 | 结构 | 三件套 | 描述诚实 | 运行风险 | 实跑验证 | 实用档位 | 建议 |")
    print("|---|---|---|---|---|---|---|---|")
    n = len(targets)
    results = []
    for i, d in enumerate(targets, 1):
        print("[%d/%d] 预检中: %s …" % (i, n, d.name), file=sys.stderr, flush=True)
        r = prequal(d, need)
        results.append(r)
        verdict = "结构完整、三件套齐备" if r["score"] >= 85 else "详见下方发现"
        print("| %s | %s | %s | %s | %s | %s | **%s** | %s |" % (
            r["name"], r["struct"], r["three"], r["over"], r["run"], r.get("smoke", "—"), r["tier"], verdict))

    print("\n## 逐技能发现\n")
    for r in results:
        print("### %s　评分 %d／100　档位 %s" % (r["name"], r["score"], r["tier"]))
        if r["findings"]:
            for sev, msg in r["findings"]:
                icon = {"warn": "⚠", "info": "·", "ok": "✓"}.get(sev, "·")
                print("- %s %s" % (icon, msg))
        else:
            print("- ✓ 未发现明显短板")
        if "smoke" in r:
            print("- 🔧 实跑验证：%s" % r["smoke"])
        if need and "fit" in r:
            print("- 🎯 需求匹配：%s —— %s" % (r["fit"][0], r["fit"][1]))
        print()

    print("> 分工：本报告只管“实不实用”；“正不正宗”请跑 provenance.py；"
          "“安不安全”请对可疑项跑官方 skills-sec-audit。")


if __name__ == "__main__":
    main()
