#!/usr/bin/env python3
"""技能溯源核验 — 判定已安装技能的来源、权威档位与换源建议。

用法:
    python3 provenance.py <技能目录名>   # 核验单个
    python3 provenance.py all            # 全量核验 ~/.workbuddy/skills/
    python3 provenance.py all --dir ~/my-skills   # 核验自定义目录（批量进度显示在终端）

判定矩阵见 SKILL.md。纯标准库，零依赖。
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402  v1.2.2：统一错误码 / 跨平台目录发现 / 可配置规则

API = "https://api.github.com/repos/{}"
USER_AGENT = "skill-origin/1.2.2"

# v1.2.2：默认扫描根改为跨平台自动发现（不再硬绑 ~/.workbuddy/skills 一个落点）。
# 探测顺序见 common._candidate_dirs；可用环境变量 SKILL_ORIGIN_SKILLS_DIR / SKILLS_DIR 固定。
SKILLS_DIR, _ROOT_ORIGIN = common.discover_skills_dir()

# 判定规则：v1.2.2 起可外部配置（config/rules.json / --rules / SKILL_ORIGIN_RULES），
# 默认值与 v1.2.1 内置常量完全一致——零配置行为不变，但不再需要改代码来维护名单。
_RULES, _RULES_NOTE = common.load_rules()
TOP_STAR = _RULES["top_star"]      # >= 此星数视为行业顶流
LOW_STAR = _RULES["low_star"]        # < 此星数视为低星
# 厂商官方 org 白名单（A+ 档）：上游仓库属这些 org → 比单纯星数更硬的背书。
OFFICIAL_ORGS = set(_RULES["official_orgs"])
# 人工核验过的自建/改造技能名单（兜底用；本机命名空间的技能已由 OWN_NAMESPACE 数据驱动识别）。
SELF_BUILT = set(_RULES["self_built"])
# 用户本人在 SkillHub 的发布命名空间（self-built 的数据驱动信号，无需手维护名单）
OWN_NAMESPACE = _RULES["own_namespace"]

# 市场件元数据的两种落地形态（2026-11-02 实证补）：
#   ① _skillhub_meta.json —— SkillHub 安装时写入，含 slug/namespace/skillId/installedAt
#   ② _meta.json          —— 平台市场分发写入，含 ownerId/publishedAt/slug/version
# 原实现只认 ①，导致 ② 形态的市场件（如 smart-charts）被当成"无任何来源线索"而误判 D 档。
# 两种形态都是本地未签名声明、可被伪造，故判词仍须声明"未与平台核对、不构成授权依据"（C1）。
META_FILENAMES = ("_skillhub_meta.json", "_meta.json")

# 用户本人在 SkillHub 的发布命名空间（self-built 的数据驱动信号，无需手维护名单）
# → 已随判定规则一并外置到 common.load_rules()，见文件头部。

# 市场分发记录（marketplace）的锚点：满足其一即视作有市场分发背书。
# ① skillId / installedContentHash —— SkillHub 安装形态（_skillhub_meta.json）
# ② ownerId / publishedAt       —— 平台市场分发形态（_meta.json，2026-11-02 实证补）
# 均为本地未签名 meta，可被伪造，故判词必须显式声明"可被伪造、不构成授权依据"（C1）。
MARKET_EVIDENCE = ("skillId", "installedContentHash", "ownerId", "publishedAt")

# 正文链接行中出现这些词 → 视为"来源声明"而非随意提及
SOURCE_HINT = re.compile(r"based on|author|来源|源自|出处|fork|origin|adapted|汉化|原文", re.I)

REPO_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?(?=[/\s\"'\)\]]|$)")
SKIP_REPO = ("user-attachments", "github.com/search")


def collect_repos(skill_dir: Path, skill_name: str):
    """提取 GitHub 仓库，区分'来源链接'与'提及链接'。

    来源判定仅认两处：① SKILL.md frontmatter 的 author 字段 ② 链接所在行含来源声明词
    （SOURCE_HINT）。不再做"仓库名/技能名同名（含）"的推断（C2：该推断只需发布者起同名即可
    把"提及"升格为来源、绕过 is_mention_only 拿到 A+，属可被利用的薄弱点）。其余为提及，
    不参与档位判定。
    """
    source_repos, mention_repos = [], []
    for name in ("SKILL.md", "README.md", "readme.md"):
        f = skill_dir / name
        if not f.exists():
            continue
        text = f.read_text(errors="ignore")
        is_frontmatter_zone = True  # 粗略跟踪：frontmatter 在首个 --- 对内
        fm_end = 0
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end > 0:
                fm_zone, fm_end = text[:end], end
                m = re.search(r"^author:\s*(\S+)", fm_zone, re.M)
                if m and "github.com/" in m.group(1):
                    repo = REPO_RE.search(m.group(1) + "/")
                    if repo:
                        source_repos.append(repo.group(1))
        for line_no, line in enumerate(text[fm_end:].splitlines(), 1):
            for match in REPO_RE.finditer(line):
                repo = match.group(1)
                if any(s in repo for s in SKIP_REPO):
                    continue
                # gist 链接（第二段为长哈希）不是仓库
                if re.fullmatch(r"[0-9a-f]{16,}", repo.split("/")[1]):
                    continue
                # 来源只认两处：① frontmatter author URL（已在上方处理）② 含来源声明词的行（SOURCE_HINT）。
                # 删除"仓库名/技能名同名（含）"的推断（C2）：该推断只需发布者起同名即可把"提及"升格为
                # 来源、绕过 is_mention_only 拿到 A+，属可被利用的薄弱点。
                is_source = bool(SOURCE_HINT.search(line))
                (source_repos if is_source else mention_repos).append(repo)
    # 去重保序，且提及不重复计入来源
    dedup = lambda lst: list(dict.fromkeys(lst))  # noqa: E731
    return dedup(source_repos), dedup(mention_repos)


RATE_LIMIT_MARKERS = (
    "rate limit", "secondary rate", "abuse detection", "too many requests",
    "temporarily blocked", "please wait a few minutes",
)


def _rate_limit_reason(code, body, headers):
    """判定 403/429 是否为限流，并给出具体形态（供报告说明是哪种限流）。

    v1.2.2 修复：旧实现只认「body 含 rate limit」或「X-RateLimit-Remaining=0」，
    漏掉了 429 空 body、GitHub 二次限流（secondary rate limit）、
    abuse detection、以及带 Retry-After 的 403——这些会被当成「仓库不存在」
    进而误判 D 档，制造冤案。现按保守原则：403/429 一律判为受限。
    """
    low = (body or "").lower()
    hdrs = headers or {}
    if "secondary rate" in low or "abuse detection" in low:
        return "二次限流"
    if "rate limit" in low:
        return "主限流"
    if hdrs.get("Retry-After"):
        return "限流（带 Retry-After）"
    if hdrs.get("X-RateLimit-Remaining") == "0":
        return "主限流"
    if code == 429:
        return "限流"
    return "访问受限（HTTP %s，按限流保守处理）" % code


def fetch_repo(full_name: str):
    """GitHub API 查询仓库；返回 dict / None（确实不存在）/ "RATE_LIMITED" / "NETWORK_UNREACHABLE"。

    限流必须与「仓库不存在」区分：限流或网络不通时无法判定≠无背书，误判 D 档是冤案。
    匿名公开接口即可调用（限额 60 次/时，日常核验足够）。
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")  # P0-3 方案A：可选 token 提额，未设则维持匿名
    if tok:
        headers["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(API.format(full_name), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            body = ""
            try:
                body = e.read(300).decode("utf-8", "ignore")
            except Exception:
                pass
            reason = _rate_limit_reason(e.code, body, e.headers)
            print(f"    ⚠ GitHub API {reason}（HTTP {e.code}），本次无法完成全部核验",
                  file=sys.stderr)
            return "RATE_LIMITED"
        print(f"    ⚠ API 查询失败 {full_name}: HTTP {e.code}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        # 网络不可达（DNS 不通 / 被墙 / 超时）——与「限流」分开报，便于国内网络场景给出正确处置建议
        print(f"    ⚠ 网络不可达 {full_name}: {e.reason}", file=sys.stderr)
        return "NETWORK_UNREACHABLE"
    except Exception as e:
        print(f"    ⚠ API 查询失败 {full_name}: {e}", file=sys.stderr)
        return None


def detect_agent_created(skill_dir: Path) -> bool:
    """检测 SKILL.md frontmatter 是否声明 agent_created: true。

    只认 frontmatter 首个 --- 区块内的 agent_created 字段，避免正文里出现同名字样被误判。
    """
    f = skill_dir / "SKILL.md"
    if not f.exists():
        return False
    try:
        text = f.read_text(errors="ignore")
    except Exception:
        return False
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end < 0:
        return False
    fm = text[:end]
    m = re.search(r"^agent_created:\s*(true|True|yes)", fm, re.M)
    return bool(m)


def _repo_rank(info):
    """仓库排序权重：厂商官方 org 优先，其次比星数。

    v1.2.2 修复：旧实现纯按星数取最大，会让「高星非官方来源」压过「厂商官方来源」——
    官方背书比星数硬，取错主仓库会让 A+ 档掉成 B 档。现官方优先。
    """
    owner = (info.get("full_name") or "").split("/")[0].lower()
    return (1 if owner in OFFICIAL_ORGS else 0, info.get("stargazers_count", 0))


def audit_skill(skill_dir: Path, allow_network: bool = True) -> dict:
    """核验单个技能目录，返回结果 dict（含置信度）。

    allow_network=False → 完全不发网络请求，但仍执行全部「本地可判」的判定
    （自建/改造、市场件背书、来源声明解析），只把「上游实测档位」标为未查询。
    v1.2.2 修复：旧版一断网就整维跳过，导致本地明明能判的自建/市场件也拿不到结论。
    """
    r = _audit_skill_inner(skill_dir, allow_network)
    r["confidence"] = common.confidence_of(r.get("tier", ""))
    if r.get("consistency"):
        r["verdict"] = ((r.get("verdict") or "") + "；⚠ " + r["consistency"]).lstrip("；")
    return r


def _audit_skill_inner(skill_dir: Path, allow_network: bool = True) -> dict:
    """核验单个技能目录，返回结果 dict。"""
    r = {"name": skill_dir.name, "source": None, "version": None,
         "installed": None, "repos": [], "tier": "?", "verdict": "", "upstream_newer": False}

    # 1) 安装元数据
    # 两种落地形态：_skillhub_meta.json（SkillHub 安装写入）/ _meta.json（平台市场分发写入）。
    # 优先取前者；前者不存在时取后者。都带 skill_id 之类的归属信息就都不该被判"无来源线索"。
    installed_at = None
    meta = None
    meta_f = None
    # 两种落地形态：_skillhub_meta.json（SkillHub 安装写入）/ _meta.json（平台市场分发写入）。
    # 两份并存时不能只看第一份就定档——第一份若缺市场锚点（如只有 slug/version），
    # 而第二份带 ownerId/publishedAt，则应以"两份合并后的证据"判定，否则会误判 D 档。
    # 故此处收集全部可用 meta，档位判定按"任一份含市场锚点即成立"（MARKET_EVIDENCE）。
    meta_files = []
    for _fn in META_FILENAMES:
        _f = skill_dir / _fn
        if not _f.exists():
            continue
        try:
            loaded = json.loads(_f.read_text())
        except Exception:
            loaded = None  # 解析失败（损坏）：当无 meta，走正常 D 分支，不崩批
        if isinstance(loaded, dict):
            meta_files.append((_fn, loaded))
        elif loaded is not None:
            # 成功解析但非 dict（列表/字符串）——属异常输入，交由 main() 的 try/except
            # 降级为「？ 核验异常」，既不静默吞掉、也不崩整批（F-3 / P0-4）
            raise ValueError(f"{_fn} 非 dict（实为 {type(loaded).__name__}），核验中止")
    if meta_files:
        _fn, meta = meta_files[0]
        meta_f = _fn
        # 来源与版本：优先取带完整字段的一份
        for _fn2, _m in meta_files:
            if not r["source"]:
                r["source"] = _m.get("source") or ("marketplace" if _fn2 == "_meta.json" else None)
            if not r["version"]:
                r["version"] = _m.get("version")
        if r["source"] is None and any(_fn2 == "_meta.json" for _fn2, _ in meta_files):
            r["source"] = "marketplace"
        # 市场锚点：任一份 meta 含其一即成立（合并证据，不因第一份缺字段而漏判）
        if not any(any(_m.get(k) for k in MARKET_EVIDENCE) for _fn2, _m in meta_files):
            # 合并后仍无锚点 → 把第一份降级为"无市场证据"，避免 MARKET_EVIDENCE 误命中
            meta = {k: v for k, v in meta.items() if k not in MARKET_EVIDENCE}
        # 时间：installedAt（安装时刻）或 publishedAt（市场发布时间）
        for _fn2, _m in meta_files:
            ts = _m.get("installedAt") or _m.get("publishedAt")
            if ts:
                try:
                    installed_at = int(ts) / 1000
                    r["installed"] = time.strftime("%Y-%m-%d", time.localtime(installed_at))
                except Exception:
                    pass
                break

    # 2) 自建判定（数据驱动优先，手维护名单兜底；全部为本地证据、可被伪造）
    has_ledger = (skill_dir / "UPSTREAM-MERGE.md").exists() and \
        (skill_dir / "UPSTREAM-MERGE.md").stat().st_size > 0  # 空台账不计数（P0-2）
    ledger_note = "；本地有改造，上游更新走 UPSTREAM-MERGE 三方合并" if has_ledger else ""
    source_repos, mention_repos = collect_repos(skill_dir, skill_dir.name)  # 只收集一次
    # 权威名：优先 _skillhub_meta.json 的 slug（安装源自带），否则用目录名本身（不剥离 __ 后缀）
    canonical = (meta or {}).get("slug") or skill_dir.name
    # meta 自洽校验：slug 须与目录名同源（目录名 == slug 或 == slug + "__<后缀>"）；
    # is_own_publish 要求 slug+namespace 双字段齐全（杜绝仅 slug 伪造命中白名单，A-2）。
    _slug = (meta or {}).get("slug")
    slug_ok = bool(_slug) and (
        skill_dir.name == str(_slug)
        or re.fullmatch(re.escape(str(_slug)) + r"__.+", skill_dir.name) is not None)
    is_own_publish = (r.get("source") == "skillhub" and slug_ok
                      and (meta or {}).get("namespace")
                      and str((meta or {}).get("namespace")).strip().lower() == OWN_NAMESPACE.lower())
    own_evidence = []
    if canonical in SELF_BUILT and not meta:   # 仅"无 meta"时信任手维护白名单；有 meta 则一律走自洽校验
        own_evidence.append("名单")
    if is_own_publish:
        own_evidence.append("meta 命名空间")
    if has_ledger and not r["source"]:
        own_evidence.append("改造台账")
    # 2026-11-02 补：SKILL.md frontmatter 声明 agent_created: true → 本机 agent 自建。
    # 这是比手维护名单更可靠的数据驱动信号（写技能时自带），故排在名单之前作为独立依据。
    # 局限同其他本地证据：可被伪造，故判词仍声明"不构成授权依据"。
    if detect_agent_created(skill_dir):
        own_evidence.append("frontmatter agent_created")
    if own_evidence:
        r["source_evidence"] = own_evidence
        r["tier"] = "自建/改造"
        r["verdict"] = ("自建/改造（依据：%s；均为本地证据、未与平台核对，可被伪造）"
                        "——未见正版冲突，但本判词不证明原创，也不构成授权依据"
                        % "、".join(own_evidence))
        # 改造类若能定位上游，附上上游信息（不参与档位）
        if source_repos:
            if not allow_network:
                r["verdict"] += "（离线模式：上游信息未获取）"
            else:
                info0 = fetch_repo(source_repos[0])
                if info0 == "RATE_LIMITED":
                    r["verdict"] += "（上游信息查询受限流影响，未获取）"
                elif info0 == "NETWORK_UNREACHABLE":
                    r["verdict"] += "（上游信息查询因网络不可达未获取）"
                elif info0 and "full_name" in info0:
                    r["repos"].append({"repo": info0["full_name"], "stars": info0.get("stargazers_count", 0),
                                       "fork": info0.get("fork", False), "parent": None, "parent_stars": None,
                                       "pushed": (info0.get("pushed_at") or "")[:10]})
                    r["verdict"] += f"；上游={info0['full_name']}({info0.get('stargazers_count', 0)}★)"
        return r

    # 3) GitHub 溯源：仅"来源链接"参与判定，"提及链接"只展示
    repos = source_repos or mention_repos
    is_mention_only = not source_repos and bool(mention_repos)

    # 3a) 跨来源一致性（v1.2.2 新增）：声明了多个来源、或提及了官方仓库却未声明为来源，
    #     都属「人工需确认」的情形——本技能只提示，不下结论。
    if len(source_repos) > 1:
        r["consistency"] = "声明了 %d 个来源仓库（%s），请人工确认是否同一上游" % (
            len(source_repos), "、".join(source_repos))
    if is_mention_only:
        off_mentions = [m for m in mention_repos
                        if m.split("/")[0].lower() in OFFICIAL_ORGS]
        if off_mentions:
            r["consistency"] = "正文提及厂商官方仓库 %s 但未声明为来源（提及不进档位）" % (
                "、".join(off_mentions))

    if is_mention_only:   # 提及不得进档位（F-1 / P0-3）：正文仅提及、未声明上游，需人工确认
        r["tier"] = "？ 来源未声明"
        r["verdict"] = "正文仅提及外部仓库、未声明其为本技能来源；提及不参与档位判定，需人工确认"
        return r

    # 3b) 离线模式：不发网络请求，但「本地可判」的结论照给（市场件背书等），
    #     只把依赖 GitHub 实测的档位标为「未查询」——不因断网丢结论。
    if not allow_network:
        v = r["version"] or "未知版本"
        if r["source"] == "marketplace" and meta and not meta.get("preinstalledTemplate") \
                and any(meta.get(k) for k in MARKET_EVIDENCE):
            r["tier"] = "A 官方背书"
            r["verdict"] = (f"CodeBuddy 官方市场分发(v{v})，市场分发记录（本地声明，未与平台核对、"
                            f"可被伪造）；离线模式未查询上游仓库，联网后重跑可补全")
        else:
            r["tier"] = "？ 上游未查询"
            r["verdict"] = ("离线模式：未查询上游仓库，权威档位（B/B-/A+/C）无法判定"
                            "（离线≠无背书）；联网后重跑即可补全")
        return r

    best = None  # (repo, info, parent)
    for repo in repos:
        info = fetch_repo(repo)
        if info == "RATE_LIMITED":
            r["tier"] = "？ API受限"
            r["verdict"] = "GitHub API 限流，本次无法判定（限流≠无背书）；稍后重跑即可"
            return r
        if info == "NETWORK_UNREACHABLE":
            r["tier"] = "？ 网络不可达"
            r["verdict"] = ("GitHub API 网络不可达（DNS 不通/被墙/超时），本次无法判定"
                            "（不可达≠无背书）；请检查网络或改用离线模式（仅本地可判项）")
            return r
        if not info or "full_name" not in info:
            continue
        parent = info.get("parent")
        r["repos"].append({
            "repo": info["full_name"], "stars": info.get("stargazers_count", 0),
            "fork": info.get("fork", False),
            "parent": (parent or {}).get("full_name") if parent else None,
            "parent_stars": (parent or {}).get("stargazers_count") if parent else None,
            "pushed": (info.get("pushed_at") or "")[:10],
        })
        # v1.2.2：厂商官方优先于星数——官方背书比星数硬，不能让高星非官方压过官方
        if best is None or _repo_rank(info) > _repo_rank(best[1]):
            best = (repo, info, parent)

    if best is None:
        v = r["version"] or "未知版本"
        if r["source"] == "marketplace" and meta and not meta.get("preinstalledTemplate") \
                and any(meta.get(k) for k in MARKET_EVIDENCE):
            r["tier"] = "A 官方背书"
            r["verdict"] = f"CodeBuddy 官方市场分发(v{v})，市场分发记录（本地声明，未与平台核对、可被伪造）"
        elif r["source"] == "marketplace":
            r["tier"] = "D 无背书"
            r["verdict"] = "市场分发记录（本地声明），但缺 skillId 或属预置模板，不视作官方背书；从没用过→建议卸载，要用→先过 skills-sec-audit"
        elif source_repos:   # 声明了来源但全部不可解析（改名/删除/网络受限）
            r["tier"] = "？ 来源声明未解析"
            r["verdict"] = "声明了上游来源但无法解析（可能改名/删除/网络受限）；需人工确认"
        else:
            r["tier"] = "D 无背书"
            r["verdict"] = "无来源线索；从没用过→建议卸载，要用→先过 skills-sec-audit"
        return r

    _, info, parent = best
    stars = info.get("stargazers_count", 0)
    pushed = (info.get("pushed_at") or "")[:10]

    # 4) 新鲜度：上游比本地安装新（统一按本地时区的日期比较，避免时区偏差）
    if installed_at and pushed:
        try:
            installed_day = date.fromtimestamp(installed_at)
            pushed_day = datetime.strptime(pushed, "%Y-%m-%d").date()
            if pushed_day > installed_day:
                r["upstream_newer"] = True
        except ValueError:
            pass

    # 5) 档位判定
    mention_note = "（注意：仓库链接仅出现在正文提及中，非来源声明，建议人工确认）" if is_mention_only else ""
    if info.get("fork") and parent:
        pstars = parent.get("stargazers_count", 0)
        r["tier"] = "C fork/低星替代"
        r["verdict"] = (f"装的是 fork({stars}★)，母仓 {parent['full_name']} 有 {pstars}★"
                        + ("——建议卸载换母仓版（换前过 skills-sec-audit）" if pstars >= max(stars * 10, TOP_STAR)
                           else "——母仓优势不明显，酌情处理") + mention_note)
    elif info["full_name"].split("/")[0].lower() in OFFICIAL_ORGS:
        r["tier"] = "A+ 厂商官方"
        r["verdict"] = f"上游 {info['full_name']} 属厂商官方 org，最高背书（{stars}★）" + mention_note
    elif stars >= TOP_STAR:
        r["tier"] = "B 行业顶流"
        r["verdict"] = f"上游 {stars}★ 非fork，已是最权威版本" + mention_note
    elif r["source"] == "marketplace" and not is_mention_only and meta and not meta.get("preinstalledTemplate") \
            and any(meta.get(k) for k in MARKET_EVIDENCE):
        r["tier"] = "A 官方背书"
        r["verdict"] = f"CodeBuddy 官方市场分发(v{r['version'] or '未知版本'})，市场分发记录（本地声明，未与平台核对、可被伪造），上游 {stars}★"
    elif stars >= LOW_STAR:
        r["tier"] = "B- 中坚来源"
        r["verdict"] = f"上游 {stars}★，有一定社区背书" + mention_note
    else:
        r["tier"] = "D 无背书"
        r["verdict"] = (f"上游仅 {stars}★"
                        + ("（SkillHub 端或有安装量，但开源侧无审查背书）" if r["source"] == "skillhub" else "")
                        + "；从没用过→建议卸载，要用→先过 skills-sec-audit" + mention_note)

    if r["upstream_newer"]:
        r["verdict"] += f"；上游最后更新 {pushed}，晚于本地安装——有新版本可同步{ledger_note}"
    elif has_ledger:
        r["verdict"] += ledger_note
    return r


def main():
    args = sys.argv[1:]
    base = SKILLS_DIR
    root_origin = _ROOT_ORIGIN
    rules_path = None
    if "--dir" in args:  # 自定义扫描目录：all --dir /path/to/skills
        i = args.index("--dir")
        try:
            base = Path(args[i + 1]).expanduser()
            root_origin = "显式指定"
        except IndexError:
            return common.fail("E_ARG_MISSING",
                               "--dir 需要一个目录路径，例如：provenance.py all --dir ~/my-skills")
        args = args[:i] + args[i + 2:]
    if "--rules" in args:  # v1.2.2：外部规则配置（名单/阈值不再必须改代码）
        i = args.index("--rules")
        try:
            rules_path = args[i + 1]
            args = args[:i] + args[i + 2:]
        except IndexError:
            return common.fail("E_ARG_MISSING",
                               "--rules 需要一个配置文件路径，例如：provenance.py all --rules ./rules.json")
    if rules_path:
        _R, _N = common.load_rules(rules_path)
        globals().update({
            "TOP_STAR": _R["top_star"], "LOW_STAR": _R["low_star"],
            "OFFICIAL_ORGS": set(_R["official_orgs"]),
            "SELF_BUILT": set(_R["self_built"]),
            "OWN_NAMESPACE": _R["own_namespace"],
        })
        root_origin += "；规则=%s" % rules_path
    arg = args[0] if args else "all"
    if not base.exists() or not base.is_dir():  # P1-6 边缘兜底：目录不存在/非目录不抛堆栈
        return common.fail("E_DIR_NOT_FOUND", str(base))
    try:
        targets = ([base / arg] if arg != "all"
                   else sorted(p for p in base.iterdir() if p.is_dir() and (p / "SKILL.md").exists()
                               and not p.name.startswith(".") and ".bak" not in p.name))
    except OSError as e:
        return common.fail("E_DIR_UNREADABLE", "%s：%s" % (base, e))
    if not targets:
        print(f"未找到技能: {arg}（扫描目录：{base}）")
        return
    if arg != "all" and not (targets[0] / "SKILL.md").exists():
        print(f"⚠ {targets[0].name} 目录下无 SKILL.md，可能不是有效技能目录")

    print(f"# 🔍 技能溯源核验报告（{len(targets)} 个）\n")
    print(f"> {common.describe_root(base, root_origin)}｜规则：{common.load_rules()[1]}\n")
    print("| 技能 | 来源 | 上游仓库(星数) | 档位 | 置信度 | 建议 |")
    print("|---|---|---|---|---|---|")
    n = len(targets)
    for i, d in enumerate(targets, 1):
        print(f"[{i}/{n}] 核验中: {d.name} …", file=sys.stderr, flush=True)  # 进度走 stderr，不污染报告
        try:
            r = audit_skill(d)
        except Exception as e:   # 单技能坏 meta/异常 → 降级而非中断整批（P0-4 / F-3）
            print(f"| {d.name} | — | — | **？ 核验异常** | 低 | 核验出错（{type(e).__name__}）：{e} |")
            continue
        # 多仓库全部展示（来源优先，已在前），用 <br> 换行保证 md 表格可读
        lines = [f"{x['repo']}({x['stars']}★)" for x in r["repos"]]
        repo_str = "<br>".join(lines) if lines else "—"
        src = r["source"] or ("UPSTREAM-MERGE" if (d / "UPSTREAM-MERGE.md").exists() else "—")
        print(f"| {r['name']} | {src} | {repo_str} | **{r['tier']}** | {r.get('confidence', '低')} | {r['verdict']} |")

    print("> 置信度：高＝GitHub 公开数据实测；中＝本地元数据/名单/台账（未与平台核对，可被伪造）；低＝证据不足或未能取证。")

    print("\n> 分工：本报告只管\"正不正宗\"；\"安不安全\"请对可疑项跑官方 skills-sec-audit。")


if __name__ == "__main__":
    main()
