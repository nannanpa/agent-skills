#!/usr/bin/env python3
"""技能溯源核验 — 判定已安装技能的来源、权威档位与换源建议。

用法:
    python3 provenance.py <技能目录名>   # 核验单个
    python3 provenance.py all            # 全量核验 ~/.workbuddy/skills/

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

SKILLS_DIR = Path.home() / ".workbuddy" / "skills"
API = "https://api.github.com/repos/{}"
TOP_STAR = 1000      # >= 此星数视为行业顶流
LOW_STAR = 100       # < 此星数视为低星
USER_AGENT = "skill-origin/1.0"

# 厂商官方 org 白名单（A+ 档）：上游仓库属这些 org → 比单纯星数更硬的背书。
# 来源：trustskills 的可信分发根 + 各厂商自营技能仓库（2026-10 核定，新增手动维护）。
OFFICIAL_ORGS = {
    "anthropics", "openai", "google-labs-code", "google-gemini",
    "googleworkspace", "microsoft", "github", "vercel-labs",
}

# 人工核验过的自建/改造技能名单（2026-10-12 首轮全量核验固化；新自建技能手动加进来）
SELF_BUILT = {
    "zhiduku", "hongloumeng", "pdf-to-md", "read-oversized-image",
    "msd-home-manual", "relation-scope", "docx-template-fill",
    "docx-track-changes-wps", "skill-origin", "maoxuan",
}

# 正文链接行中出现这些词 → 视为"来源声明"而非随意提及
SOURCE_HINT = re.compile(r"based on|author|来源|源自|出处|fork|origin|adapted|汉化|原文", re.I)

REPO_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?(?=[/\s\"'\)\]]|$)")
SKIP_REPO = ("user-attachments", "github.com/search")

NAME_RE = re.compile(r"[-_ ]")


def name_of(s: str) -> str:
    """技能名/仓库名归一化（小写、去连字符），用于同名相关性判断。"""
    return NAME_RE.sub("", s.lower())


def collect_repos(skill_dir: Path, skill_name: str):
    """提取 GitHub 仓库，区分'来源链接'与'提及链接'。

    来源判定：① SKILL.md frontmatter 的 author 字段 ② 链接所在行含来源声明词
    ③ 仓库名与技能名同名（归一化后互相包含）。其余为提及，不参与档位判定。
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
                is_source = bool(SOURCE_HINT.search(line)) or (
                    name_of(skill_name) in name_of(repo) or name_of(repo.split("/")[1]) in name_of(skill_name)
                )
                (source_repos if is_source else mention_repos).append(repo)
    # 去重保序，且提及不重复计入来源
    dedup = lambda lst: list(dict.fromkeys(lst))  # noqa: E731
    return dedup(source_repos), dedup(mention_repos)


def fetch_repo(full_name: str):
    """GitHub API 查询仓库；返回 dict / None（不存在）/ "RATE_LIMITED"（限流）。

    限流必须与"仓库不存在"区分：限流时无法判定≠无背书，误判 D 档是冤案。
    匿名公开接口即可调用（限额 60 次/时，日常核验足够）。
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    req = urllib.request.Request(API.format(full_name), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            body = ""
            try:
                body = e.read(200).decode("utf-8", "ignore")
            except Exception:
                pass
            if "rate limit" in body.lower() or e.headers.get("X-RateLimit-Remaining") == "0":
                print(f"    ⚠ GitHub API 限流（{e.code}），本次无法完成全部核验", file=sys.stderr)
                return "RATE_LIMITED"
        print(f"    ⚠ API 查询失败 {full_name}: HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    ⚠ API 查询失败 {full_name}: {e}", file=sys.stderr)
        return None


def audit_skill(skill_dir: Path) -> dict:
    """核验单个技能目录，返回结果 dict。"""
    r = {"name": skill_dir.name, "source": None, "version": None,
         "installed": None, "repos": [], "tier": "?", "verdict": "", "upstream_newer": False}

    # 1) 安装元数据
    meta_f = skill_dir / "_skillhub_meta.json"
    installed_at = None
    if meta_f.exists():
        try:
            meta = json.loads(meta_f.read_text())
            r["source"] = meta.get("source")
            r["version"] = meta.get("version")
            if meta.get("installedAt"):
                installed_at = int(meta["installedAt"]) / 1000
                r["installed"] = time.strftime("%Y-%m-%d", time.localtime(installed_at))
        except Exception:
            pass

    # 2) 自建名单（人工核验固化）
    has_ledger = (skill_dir / "UPSTREAM-MERGE.md").exists()
    ledger_note = "；本地有改造，上游更新走 UPSTREAM-MERGE 三方合并" if has_ledger else ""
    source_repos, mention_repos = collect_repos(skill_dir, skill_dir.name)  # 只收集一次
    if skill_dir.name in SELF_BUILT or (has_ledger and not r["source"]):
        r["tier"] = "自建/改造"
        r["verdict"] = "原创度100%，不存在正版问题；改造类上游更新走 UPSTREAM-MERGE 三方合并"
        # 改造类若能定位上游，附上上游信息（不参与档位）
        if source_repos:
            info0 = fetch_repo(source_repos[0])
            if info0 == "RATE_LIMITED":
                r["verdict"] += "（上游信息查询受限流影响，未获取）"
            elif info0 and "full_name" in info0:
                r["repos"].append({"repo": info0["full_name"], "stars": info0.get("stargazers_count", 0),
                                   "fork": info0.get("fork", False), "parent": None, "parent_stars": None,
                                   "pushed": (info0.get("pushed_at") or "")[:10]})
                r["verdict"] += f"；上游={info0['full_name']}({info0.get('stargazers_count', 0)}★)"
        return r

    # 3) GitHub 溯源：仅"来源链接"参与判定，"提及链接"只展示
    repos = source_repos or mention_repos
    is_mention_only = not source_repos and bool(mention_repos)

    best = None  # (repo, info, parent)
    for repo in repos:
        info = fetch_repo(repo)
        if info == "RATE_LIMITED":
            r["tier"] = "？ API受限"
            r["verdict"] = "GitHub API 限流，本次无法判定（限流≠无背书）；稍后重跑即可"
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
        if best is None or info.get("stargazers_count", 0) > best[1].get("stargazers_count", 0):
            best = (repo, info, parent)

    if best is None:
        if r["source"] == "marketplace":
            r["tier"] = "A 官方市场"
            r["verdict"] = f"CodeBuddy 官方市场分发(v{r['version']})，官方背书"
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
    elif r["source"] == "marketplace" and not is_mention_only:
        r["tier"] = "A 官方市场"
        r["verdict"] = f"CodeBuddy 官方市场分发(v{r['version']})，上游 {stars}★"
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
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = ([SKILLS_DIR / arg] if arg != "all"
               else sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").exists()))
    if not targets:
        print(f"未找到技能: {arg}")
        return
    if arg != "all" and not (targets[0] / "SKILL.md").exists():
        print(f"⚠ {targets[0].name} 目录下无 SKILL.md，可能不是有效技能目录")

    print(f"# 🔍 技能溯源核验报告（{len(targets)} 个）\n")
    print("| 技能 | 来源 | 上游仓库(星数) | 档位 | 建议 |")
    print("|---|---|---|---|---|")
    for d in targets:
        r = audit_skill(d)
        # 多仓库全部展示（来源优先，已在前），用 <br> 换行保证 md 表格可读
        lines = [f"{x['repo']}({x['stars']}★)" for x in r["repos"]]
        repo_str = "<br>".join(lines) if lines else "—"
        src = r["source"] or ("UPSTREAM-MERGE" if (d / "UPSTREAM-MERGE.md").exists() else "—")
        print(f"| {r['name']} | {src} | {repo_str} | **{r['tier']}** | {r['verdict']} |")

    print("\n> 分工：本报告只管\"正不正宗\"；\"安不安全\"请对可疑项跑官方 skills-sec-audit。")


if __name__ == "__main__":
    main()
