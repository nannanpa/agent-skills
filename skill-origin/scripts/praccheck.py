#!/usr/bin/env python3
"""技能实用度核查 — 对已安装技能做“好不好使、值不值得留”，与溯源(provenance)互补。

用法:
    python3 praccheck.py <技能目录名>                         # 核查单个
    python3 praccheck.py all                                  # 批量核查 ~/.workbuddy/skills/
    python3 praccheck.py all --dir ~/my-skills                 # 自定义目录（进度走 stderr）
    python3 praccheck.py <技能目录名> --need "我想自动签到领积分"   # 附需求做匹配度评估

分工：provenance.py 管“正不正宗”（需联网查 GitHub）；本脚本管“实不实用”
（纯本地、零网络、零依赖）。安全疑虑仍转交官方 skills-sec-audit。

判定维度（详见 SKILL.md「实用度核查」章节）：
    ① 结构齐备   ② 三件套(异常处理/FAQ/多场景示例)  ③ 描述诚实度
    ④ 运行风险(第三方依赖/硬编码路径/凭证需求)       ⑤ 需求匹配度(--need)
    ⑥ 实跑验证(骨架→长大中)：内置 compile() 内存编译（零写盘）+ __main__ 入口 --help 启动探测 + 样例脚本实际执行并核对输出非空（纯本地、零网络）
"""
import os
import re
import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402  v1.2.2：统一错误码 / 跨平台目录发现 / 可配置规则

_RULES, _RULES_NOTE = common.load_rules()
_PC = _RULES.get("praccheck", {})

# v1.2.2：默认扫描根改为跨平台自动发现（不再硬绑 ~/.workbuddy/skills 一个落点）
SKILLS_DIR, _ROOT_ORIGIN = common.discover_skills_dir()

# 声称"会动手"的描述词；若技能无实现载体却含这些词 → 疑似口号型/demo。
ACTION_VERBS = tuple(_PC.get("action_verbs") or (
    "自动", "一键", "生成", "调用", "抓取", "爬取", "解析",
    "批量", "导出", "转换", "发送", "部署", "读写", "自动化", "api"))

# 三件套判定词
FAQ_HINT = re.compile(_PC.get("faq_hint") or r"FAQ|常见问题|问答", re.I)
EXAMPLE_HINT = re.compile(_PC.get("example_hint") or r"示例|例子|场景|用法|quick ?start|用例", re.I)

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
    """列出待核查目标。

    v1.2.2 修复：旧版直接 base.iterdir()，目录不存在/不可读时抛裸 traceback，
    与其他入口的友好提示不一致（评测点名"部分 praccheck 参数和目录异常未完整拦截"）。
    现一律转成带错误码的受控异常，由 main() 统一打印。
    """
    if not base.exists():
        raise common.SkillOriginError("E_DIR_NOT_FOUND", str(base))
    if not base.is_dir():
        raise common.SkillOriginError("E_DIR_NOT_FOUND", "不是目录：%s" % base)
    if arg == "all":
        try:
            return sorted(p for p in base.iterdir()
                          if p.is_dir() and (p / "SKILL.md").exists()
                          and not p.name.startswith(".") and ".bak" not in p.name)
        except OSError as e:
            raise common.SkillOriginError("E_DIR_UNREADABLE", "%s：%s" % (base, e))
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
        if s.name.startswith("test_"):
            # v1.2.2：测试夹具里的路径字面量（如 "/Users/whoami/..."）不是运行时风险，
            # 旧版会把它们误报成「换机可能失败」——误报会让使用者不信任本工具的告警。
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
    """凭证需求检查。区分「可选令牌（缺失只降级）」与「必需凭证（缺失跑不了）」。

    v1.2.2 修正措辞过重：旧版只要文档提到 API key/密钥就一律警告「使用前需自备凭证」，
    对「默认匿名、可选配置令牌」的工具是失真告警。现按文档自述的可选性分档。
    """
    if not ENV_HINT.search(text_all):
        return ("ok", "")
    optional_markers = ("可选", "零配置", "默认匿名", "optional", "不设则", "未设则")
    if any(m in text_all for m in optional_markers):
        return ("warn", "文档提及 API key/环境变量/密钥等字样，但自述为可选配置——"
                        "未配置时功能降级而非失效，请按文档确认是否需要自备")
    return ("warn", "文档提及 API key/环境变量/密钥，使用前需自备凭证并注意安全")


def runtime_smoke(skill_dir: Path, scripts):
    """实跑冒烟(骨架)：编译 + 启动探测，验证技能脚本至少「能加载、能启动」。

    这是把 praccheck 从「静态词法 lint」推向「真能跑」的起步骨架；不做深度语义 / 输出
    正确性验证（那是行星级质量审计该做的，留待后续长大）。纯本地、零网络；仅对 .py 做
    内置 compile() 内存编译（零写盘）+（含 __main__ 守卫时）`--help` 启动探测，超时 8s。局限：不验证实际功能、
    不核实输出正确，仅证明「脚本不崩、能起」。
    """
    findings = []
    compiles = launches = crashes = timeouts = dep_miss = compile_errs = 0
    for s in scripts:
        if s.suffix.lower() != ".py":
            continue
        # 1) 编译检查：能否解析/加载（抓 SyntaxError/IndentationError）
        try:
            compile(s.read_text(errors="ignore"), str(s), "exec")
            compiles += 1
        except SyntaxError as e:
            compile_errs += 1
            findings.append(("warn", "脚本 %s 编译失败（语法错误）：%s" % (s.name, e.msg)))
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
                cwd=str(skill_dir), env=_sandbox_env(),
                capture_output=True, text=True, timeout=8)
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


# v1.2.2：样例执行期强制阻断外网——把代理指向本机 discard 端口，任何 HTTP(S) 访问
# 立即失败；同时清掉 GITHUB_TOKEN，避免子进程带凭证发请求。
SANDBOX_ENV = {
    "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
    "all_proxy": "http://127.0.0.1:9", "no_proxy": "",
    "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
    "ALL_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
    "SKILL_ORIGIN_SANDBOX": "1",
}


def _sandbox_env():
    env = dict(os.environ)
    env.update(SANDBOX_ENV)
    env.pop("GITHUB_TOKEN", None)   # 子进程不应携带凭证
    return env


def example_run(skill_dir: Path, scripts, exec_ok: bool = True):
    """实跑验证(长大层)：执行技能自带的样例/演示脚本，核对「能跑出东西」。

    runtime_smoke 只证明「能加载、能启动」(--help 不报错)；本层进一步实际运行样例脚本
    (命名约定 demo/example/example_demo/run_example/sample/smoke)，验证其默认调用能产生
    非空输出、退出码为 0、无 Traceback。这是把 praccheck 从「矮行星」推向「质量审计行星」
    的关键一层：不仅不崩，还要真能产出。

    v1.2.2 修正「零网络」承诺：旧版直接继承父进程环境执行样例，样例若发网络请求就真发出去，
    与文档"纯本地、零网络"的承诺不符（评测点名"零网络承诺与样例脚本实际执行之间缺少强隔离"）。
    现执行时注入阻断外网的代理环境并清除凭证；严格零网络场景可加 --no-exec 完全不执行。
    """
    if not exec_ok:
        return {"status": "skipped", "summary": "已按 --no-exec 跳过样例执行",
                "findings": [], "bytes": 0, "rc": None}
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
            [sys.executable, str(s)], cwd=str(skill_dir), env=_sandbox_env(),
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


CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+.-]*")

# 需求 → 能力 的粗粒度同义映射（轻量语义层，补字面重合的盲区）
NEED_SYNONYMS = {
    "签到": ("签到", "打卡", "积分"), "打卡": ("签到", "打卡", "积分"),
    "积分": ("积分", "签到", "奖励"), "批量": ("批量", "全量", "遍历", "目录"),
    "所有": ("批量", "全量", "遍历"), "整个": ("批量", "全量", "遍历"),
    "自动": ("自动", "一键"), "一键": ("一键", "自动"),
    "生成": ("生成", "导出", "输出", "产出"), "导出": ("导出", "生成", "输出"),
    "抓取": ("抓取", "爬取", "采集"), "爬": ("爬取", "抓取"),
    "转换": ("转换", "格式"), "解析": ("解析", "提取"),
    "审计": ("审计", "核查", "核验", "检查"), "核验": ("核验", "核查", "检查", "审计"),
    "溯源": ("溯源", "来源", "核验"), "来源": ("来源", "溯源"),
    "安全": ("安全", "风险", "审计"), "图表": ("图表", "绘图", "可视化"),
    "ppt": ("ppt", "幻灯片"), "幻灯片": ("ppt", "幻灯片"),
    "复习": ("复习", "记忆", "回顾"), "记忆": ("记忆", "复习"),
}


def _need_tokens(need: str):
    """从需求描述抽关键词：英文词 + 中文 3 字组合（比 2 字组合噪音小）。"""
    toks = []
    for w in WORD_RE.findall(need):
        if len(w) >= 2:
            toks.append(w.lower())
    cjk = "".join(CJK_RE.findall(need))
    for i in range(len(cjk) - 2):
        toks.append(cjk[i:i + 3])
    return toks


def need_fit(need: str, text_all: str):
    """需求匹配度：关键词命中 + bigram 重合 + 能力类目 三通道合成。

    v1.2.2 升级：旧版只有 bigram 字面重合率，对"换了说法"的需求不敏感（评测点名的
    "需求匹配主要依赖字面重合"）。现加两条通道，并把未命中的关键词列出来供人工复核。
    仍是启发式，不伪装成语义理解。
    """
    nb = bigrams(need)
    if not nb:
        return ("—", "未提供有效需求")
    low = text_all.lower()
    sb = bigrams(text_all)
    hit = nb & sb
    bi_cov = len(hit) / len(nb)

    toks = _need_tokens(need)
    matched = [t for t in toks if t.lower() in low]
    kw_cov = (len(matched) / len(toks)) if toks else 0.0

    # 能力类目：需求里的意图词 → 技能正文里可能对应的能力词
    cat_hit = False
    for key, caps in NEED_SYNONYMS.items():
        if key in need.lower() and any(c.lower() in low for c in caps):
            cat_hit = True
            break

    score = 0.4 * bi_cov + 0.4 * kw_cov + 0.2 * (1.0 if cat_hit else 0.0)
    if score >= 0.5:
        v = "高匹配"
    elif score >= 0.25:
        v = "部分匹配"
    else:
        v = "低匹配/可能不匹配"
    unmatched = [t for t in toks if t.lower() not in low][:5]
    detail = ("关键词命中 %d/%d（%.0f%%）、bigram 重合 %.0f%%、能力类目%s"
              % (len(matched), len(toks), kw_cov * 100, bi_cov * 100,
                 "命中" if cat_hit else "未命中"))
    if unmatched:
        detail += "；未命中词：" + "/".join(unmatched)
    return (v, detail + "（启发式，仅供参考，最终以人工判断为准）")


def praccheck(skill_dir: Path, need: str = "", exec_ok: bool = True):
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
    ex = example_run(skill_dir, scripts, exec_ok=exec_ok)  # 实跑验证(长大层)：样例执行 + 输出核对

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
        r["tier"] = "优（可放心用）"
    elif score >= 65:
        r["tier"] = "良（可用，注意点见下）"
    elif score >= 40:
        r["tier"] = "慎用（先验证再用于关键场景）"
    else:
        r["tier"] = "不建议用（高风险/玩具）"
    r["score"] = score

    if need:
        r["fit"] = need_fit(need, text_all + read_text(skill_dir / "README.md"))
    return r


def main():
    args = sys.argv[1:]
    base = SKILLS_DIR
    root_origin = _ROOT_ORIGIN
    need = ""
    exec_ok = True
    if "--dir" in args:
        i = args.index("--dir")
        try:
            base = Path(args[i + 1]).expanduser()
            root_origin = "显式指定"
        except IndexError:
            return common.fail("E_ARG_MISSING",
                               "--dir 需要一个目录路径，例如：praccheck.py all --dir ~/my-skills")
        args = args[:i] + args[i + 2:]
    if "--need" in args:
        i = args.index("--need")
        try:
            need = args[i + 1]
        except IndexError:
            return common.fail("E_ARG_MISSING",
                               "--need 需要一个需求描述，例如：--need \"我想自动签到领积分\"")
        args = args[:i] + args[i + 2:]
    if "--no-exec" in args:   # v1.2.2：严格零网络场景——完全跳过样例执行
        exec_ok = False
        args = [a for a in args if a != "--no-exec"]
    arg = args[0] if args else "all"
    try:
        targets = iter_targets(base, arg)
    except common.SkillOriginError as e:
        return common.fail(e.code, e.detail)
    if not targets:
        print("未找到技能: %s（扫描目录：%s）" % (arg, base))
        return
    if arg != "all" and not (targets[0] / "SKILL.md").exists():
        print("⚠ %s 目录下无 SKILL.md，可能不是有效技能目录" % targets[0].name)

    print("# 🧪 技能实用度核查报告（%d 个）\n" % len(targets))
    print("> %s｜规则：%s%s\n" % (
        common.describe_root(base, root_origin), common.load_rules()[1],
        "｜已启用 --no-exec：不执行任何样例脚本" if not exec_ok else ""))
    print("| 技能 | 结构 | 三件套 | 描述诚实 | 运行风险 | 实跑验证 | 实用档位 | 建议 |")
    print("|---|---|---|---|---|---|---|---|")
    n = len(targets)
    results = []
    for i, d in enumerate(targets, 1):
        print("[%d/%d] 核查中: %s …" % (i, n, d.name), file=sys.stderr, flush=True)
        r = praccheck(d, need, exec_ok=exec_ok)
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
