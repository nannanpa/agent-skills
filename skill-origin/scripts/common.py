#!/usr/bin/env python3
"""skill-origin 公共层 — 统一错误码、跨平台技能目录发现、可配置判定规则、置信度标注。

v1.2.2 新增。三个入口（provenance.py / praccheck.py / origin.py）共用本模块，统一解决
评测 v1.2.1（versionId 478512）点名的四类问题：

1. **错误提示不统一** → 本模块提供 ERROR_CODES 与 fail()，所有受控失败都带错误码；
   提示格式全站一致（`❌ [E_XXX] 中文说明：细节`）。
2. **默认扫描目录偏向单一平台** → discover_skills_dir() 跨平台自动发现，不再硬绑
   ~/.workbuddy/skills；发现结果会写进报告，用户看得见本次扫的是哪个根。
3. **判定阈值与名单靠人工改代码** → load_rules() 支持外部 JSON 配置
   （config/rules.json 或环境变量 SKILL_ORIGIN_RULES），默认值保持不变，零配置仍开箱即用。
4. **判定结论缺少置信度** → confidence_of() 依据「结论依赖的证据强度」给出 高/中/低，
   与档位并列输出，避免把「本地未签名声明」与「GitHub 实测」当成同等分量。

纯标准库，零依赖。
"""
import json
import os
import sys
from pathlib import Path

# ── 统一错误码 ────────────────────────────────────────────────────────────
# 约定：E_ 前缀 + 全大写语义名。受控失败一律经 fail() 打印，不抛裸 traceback。
ERROR_CODES = {
    "E_DIR_NOT_FOUND": "扫描目录不存在或不是目录",
    "E_DIR_UNREADABLE": "扫描目录无法读取",
    "E_ARG_MISSING": "缺少必填参数的值",
    "E_ARG_UNKNOWN": "无法识别的参数",
    "E_NET_UNREACHABLE": "网络不可达（GitHub API 未能连通）",
    "E_NET_RATE_LIMITED": "GitHub API 限流",
    "E_META_CORRUPT": "安装元数据损坏",
    "E_EXEC_TIMEOUT": "脚本执行超时",
    "E_EXEC_CRASH": "脚本执行崩溃",
    "E_DEP_MISSING": "缺少依赖",
    "E_COMPILE_FAIL": "脚本编译失败（语法错误）",
}


class SkillOriginError(Exception):
    """带错误码的受控异常——用于把「已知失败」与「未知 bug」区分开。"""

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(self.render())

    def render(self):
        base = ERROR_CODES.get(self.code, self.code)
        return "[%s] %s%s" % (self.code, base, ("：" + self.detail) if self.detail else "")


def fail(code, detail="", stream=None):
    """统一错误出口：打印带错误码的中文提示，返回退出码 1（调用方直接 return 即可）。

    默认走 stdout——本工具的 stdout 就是「报告通道」，错误与报告同源，
    便于用户直接重定向保存；需要单独分流时传 stream=sys.stderr。
    """
    base = ERROR_CODES.get(code, code)
    print("❌ [%s] %s%s" % (code, base, ("：" + detail) if detail else ""),
          file=stream or sys.stdout)
    return 1


# ── 跨平台技能目录发现 ────────────────────────────────────────────────────
# 旧实现硬绑 ~/.workbuddy/skills，用户换平台/换 agent 环境就得手动 --dir。
# 现按优先级探测多个常见落点，并把「本次用的根」与「来源」写进报告。
def _candidate_dirs():
    """返回候选技能目录（按优先级）。环境变量最高优先，便于 CI/批量场景固定根。"""
    cands = []
    for var in ("SKILL_ORIGIN_SKILLS_DIR", "SKILLS_DIR"):
        v = os.environ.get(var)
        if v:
            cands.append(Path(v).expanduser())
    home = Path.home()
    cands += [
        home / ".workbuddy" / "skills",   # WorkBuddy
        home / ".claude" / "skills",      # Claude Code
        home / ".config" / "skills",
        home / ".codex" / "skills",
        home / ".agents" / "skills",
        home / ".gemini" / "skills",
    ]
    local = os.environ.get("LOCALAPPDATA")          # Windows
    if local:
        cands.append(Path(local) / "WorkBuddy" / "skills")
    appdata = os.environ.get("APPDATA")             # Windows
    if appdata:
        cands.append(Path(appdata) / "WorkBuddy" / "skills")
    return cands


def discover_skills_dir(explicit=None):
    """返回 (扫描根 Path, 来源说明 str)。

    explicit 非空 → 直接采用（是否存理由调用方校验）。
    否则跨平台探测首个存在的候选目录；都不存在则回退到首候选并标注「未找到」。
    """
    if explicit:
        p = Path(explicit).expanduser()
        return p, ("显式指定" if p.is_dir() else "显式指定（路径不存在）")
    cands = _candidate_dirs()
    for c in cands:
        if c.is_dir():
            return c, "自动发现"
    return cands[0], "未找到可用的技能目录"


def describe_root(base, origin):
    """报告里用的一句话：本次扫描根 + 来源。"""
    return "扫描根：%s（%s）" % (base, origin)


# ── 可配置判定规则 ────────────────────────────────────────────────────────
# 默认值与 v1.2.1 内置常量完全一致（零配置行为不变），只是搬到可外部覆盖的位置。
DEFAULT_RULES = {
    "top_star": 1000,          # >= 此星数视为行业顶流（B 档）
    "low_star": 100,           # < 此星数视为低星（D 档）
    "official_orgs": [
        "anthropics", "openai", "google-labs-code", "google-gemini",
        "googleworkspace", "microsoft", "github", "vercel-labs",
    ],
    "self_built": [
        "zhiduku", "hongloumeng", "pdf-to-md", "read-oversized-image",
        "msd-home-manual", "relation-scope", "docx-template-fill",
        "docx-track-changes-wps", "skill-origin", "maoxuan", "skill-miner",
        "rule-miner",
    ],
    "own_namespace": "indiv-mabin",
}

_RULES_CACHE = {}


def _skill_root():
    """技能根目录（common.py 的上两级 = 技能目录）。"""
    return Path(__file__).resolve().parent.parent


def _merge(base, override):
    """按 key 浅合并；类型不同的 key 直接以 override 为准。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_rules(explicit_path=None):
    """加载判定规则。

    优先级：显式 --rules 路径 > 环境变量 SKILL_ORIGIN_RULES > 技能根 config/rules.json
    > 内置默认值。任一层加载失败都回退到上一层（不因配置问题让工具不可用），
    并通过返回值里的 note 告知调用方。
    """
    if "rules" in _RULES_CACHE and not explicit_path:
        return _RULES_CACHE["rules"], _RULES_CACHE["note"]

    rules = dict(DEFAULT_RULES)
    note = "内置默认规则"

    if explicit_path:
        # 显式指定的规则文件是「唯一权威」：读不到就回退内置默认并明示，
        # 绝不静默改用别的来源（用户要 A 却拿到 B 是不可接受的行为）。
        p = Path(explicit_path).expanduser()
        if not p.is_file():
            note = "规则配置 %s 不存在，已回退内置默认" % p
        else:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                note = "规则配置 %s 读取失败（%s），已回退内置默认" % (p, e)
                data = None
            if data is not None:
                if not isinstance(data, dict):
                    note = "规则配置 %s 格式非对象，已回退内置默认" % p
                else:
                    rules = _merge(rules, data)
                    note = "规则来源：显式 --rules %s" % explicit_path
    else:
        candidates = []
        env_path = os.environ.get("SKILL_ORIGIN_RULES")
        if env_path:
            candidates.append((Path(env_path).expanduser(), "环境变量 SKILL_ORIGIN_RULES"))
        candidates.append((_skill_root() / "config" / "rules.json", "config/rules.json"))
        for path, src in candidates:
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                note = "规则配置 %s 读取失败（%s），已回退内置默认" % (path, e)
                continue
            if not isinstance(data, dict):
                note = "规则配置 %s 格式非对象，已回退内置默认" % path
                continue
            rules = _merge(rules, data)
            note = "规则来源：%s" % src
            break

    # 数值兜底：阈值必须是正整数，否则回退默认（避免配置写错导致档位全废）
    for key in ("top_star", "low_star"):
        try:
            v = int(rules.get(key))
            if v <= 0:
                raise ValueError
            rules[key] = v
        except Exception:
            rules[key] = DEFAULT_RULES[key]
    for key in ("official_orgs", "self_built"):
        v = rules.get(key)
        rules[key] = [str(x) for x in v] if isinstance(v, (list, tuple)) else list(DEFAULT_RULES[key])

    # 只有「默认来源」的结果才进缓存——显式 --rules 的一次性配置不得污染后续默认读取
    if not explicit_path:
        _RULES_CACHE["rules"] = rules
        _RULES_CACHE["note"] = note
    return rules, note

# ── 置信度 ────────────────────────────────────────────────────────────────
# 依据「结论所依赖的证据强度」给档位配置信度，而不是一律当成同等分量：
#   高 = GitHub 公开数据实测（可复核、有时间戳）
#   中 = 本地元数据 / 名单 / 台账（未与平台核对，可被伪造）
#   低 = 证据不足或未能取证（网络受限、来源未声明、线索缺失）
_CONFIDENCE_MAP = {
    "A+ 厂商官方": "高",
    "B 行业顶流": "高",
    "B- 中坚来源": "高",
    "C fork/低星替代": "高",
    "A 官方背书": "中",
    "自建/改造": "中",
    "D 无背书": "低",
    "？ 来源未声明": "低",
    "？ 来源声明未解析": "低",
    "？ 核验异常": "低",
    "？ API受限": "低",
    "？ 网络不可达": "低",
    "？ 上游未查询": "低",
    "⏭ 离线跳过": "低",
}


def confidence_of(tier):
    """按档位给出置信度档（高/中/低），未知档位一律记「低」（保守）。"""
    return _CONFIDENCE_MAP.get(tier, "低")
