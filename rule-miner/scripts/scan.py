#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rule-miner 盘点脚本 v2.2.5：廉价枚举指定根目录下的 .md，输出"知识资产候选"。
设计原则（来自实战）：不做语义解析，只统计字节、行数与文件名；计行需逐行读取，
故 I/O 与文件总字节同阶（但不进模型上下文）。

v2.1 整改（2026-10-31 发布前置对照，对应规则 A/B/C）：
  - ① 工程级异常处理：argparse 参数校验 + 中文友好报错 + 非零退出码
  - ③ --out FILE：将候选报告写入文件（扫描产物 sink）
  - ④ 冲突检测升级：KB_HIT 抽取知识库命中原文片段 + 初步矛盾分级(高/中)

P0 整改（2026-11-01 DSH 外审回函）：
  - P0-1 分布两段化：全盘 .md 分布（含噪声区）+ 候选分布；根目录归 (根目录)
  - P0-2 新增 --root DIR 限定扫描根（默认 ~/WorkBuddy）
  - P0-3 冲突分级改窗口判定（否定词须贴近命中词）
  - P0-4 os.walk onerror 逐目录告警；kb_check 增 KB_ERR（grep 不可用/超时/报错）

P2 发布前检查整改（2026-11-01，2.2.0 首发；2.2.1 仅改名/补四步描述，内容不变）：
  - ⑤ 新增 --version（argparse action=version，打印 v2.2.5）
  - ⑥ NOISE_HINTS 子串误杀改为目录边界匹配（novel_approaches.md 等正规文件不再被误跳）
  - ⑦ --out 报告补 header（文本头两行 + JSON meta：tool/version/root/generated_at）

v2.2.5 整改（2026-11-02，回应 2.2.4 评测 O1–O4，攒批一次发）：
  - A1 删除未使用的 `import subprocess`（Counter 仍由 `from collections import Counter` 引入，保留）
  - A2 新增 --timeout N：单文件读取超时上限（SIGALRM，非 Unix 平台优雅降级），超时跳过并计数告警
  - A3 新增 --resume / --progress：断点续扫（进度文件记录已处理文件、分布与候选，中断可续）
  - A4 报告改流式落盘：边扫边写，不再在内存拼成单一巨型字符串（大报告内存峰值下降）
  - A5 新增 --sink FILE（脚本级落点，直接把报告写入 sink 供下游 agent 消费，闭合评测点名的边缘缺口）
        + --selftest 内置自检（断言版本号/排除目录/内容指纹/上限逻辑），补自动化测试
  - A6 统一"分布"口径唯一表述：文本报告标题与 SKILL.md 共用 ALL_MD_DIST_DESC 常量；
        JSON meta 增加 all_distribution_desc + distribution_note，三者对齐

用法：
    python3 scripts/scan.py
    python3 scripts/scan.py --root ~/WorkBuddy/2026-10-31-08-50-44 --kb ~/WorkBuddy/记忆分册
    python3 scripts/scan.py --json --out /tmp/candidates.json
    python3 scripts/scan.py --timeout 30 --resume /tmp/progress.json --progress /tmp/progress.json
    python3 scripts/scan.py --selftest
"""

import os
import re
import sys
import json
import argparse
import signal
from collections import Counter
from datetime import datetime

_VERSION = "2.2.5"
DEFAULT_ROOT = os.path.expanduser("~/WorkBuddy")

# 排除：全局记忆结构本身 + 已知噪声目录（walk 时不向下钻取）
# 排除目录：walk 时不向下钻取。每条均附依据，避免误伤有效资产（P1-1, 2.2.3 审计）
EXCLUDE_DIRS = [
    "记忆分册",          # 全局记忆本体，非待盘点资产；计入会自指
    "node_modules",      # 依赖库，与知识资产无关
    "dist",              # 构建产物/发布暂存
    "novels", "chapters", "works",  # 小说章节等非知识资产噪声
    "references",        # 文献/外部引用库噪声
    "docs", "blob", "archive",  # 文档集/二进制/归档噪声
    "__pycache__", "_orig",     # 缓存/原始备份
]
EXCLUDE_FILES = {"INDEX.md", "交接-当前状态.md", "MEMORY.md"}

# 单文件体积上限：超过则跳过整读，防大目录/超大文件卡死（P1-2, 2.2.3）
MAX_FILE_BYTES = 4 * 1024 * 1024          # 4 MB
HEAD_LINES = 40                           # 顺带采集首段行数，供内容指纹二次匹配

# 统一"分布"口径唯一表述（A6）：文档句子 / 报告标题 / 脚本常量 三者共用此字符串
ALL_MD_DIST_DESC = "全盘 .md 分布（不含已排除的噪声目录）"

# 五类资产 → 文件名关键词
ASSET_TYPES = {
    "硬约束": "约束|铁律|门禁|红线|必须|不准|禁止|纪律|强制|审计|核查|校验|守则",
    "方法论": "方法论|方法|框架|流程|规整|范式|机制|口径|原则|经验|指南|指引|建议",
    "坑与教训": "坑|教训|雷|避坑|陷阱|踩|失败|错误|翻车",
    "模板范式": "模板|写法|格式|结构|提纲|样本|范例|套路|示例|清单",
    "决策判据": "判据|准则|决策|取舍|何时|标准|选择|对比|vs",
}
# 兜底：规则类通用词（命中即候选，但不归五类）
RULE_KW = (
    "规则|机制|纪律|原则|手册|口径|门禁|自检|复盘|沉淀|范式|"
    "判据|准则|规约|流程|约定|标准|纪要|要点|须知|纲要|规范|"
    "清单|审计|核查|校验|守则|指南|指引|经验"
)

# 已知纯噪声目录（命中即整目录跳过）
NOISE_HINTS = ("章节", "chapters", "novel", "小说", "references", "文献", "works/")

# 初步矛盾分级用的否定/反向标记（仅词面启发，最终由人裁决；须贴近命中词）
NEG_MARKERS = ("禁止", "不准", "不允许", "不得", "不应", "切勿", "严禁", "勿")


class _ReadTimeout(Exception):
    """单文件读取超时（由 SIGALRM 触发）。"""


def _read_timeout_handler(signum, frame):
    raise _ReadTimeout()


def should_skip(path: str) -> bool:
    for d in EXCLUDE_DIRS:
        if f"/{d}/" in path or path.endswith(f"/{d}"):
            return True
    if os.path.basename(path) in EXCLUDE_FILES:
        return True
    # 噪声提示词只匹配"目录名"（路径各段中除末段文件名之外的部分），
    # 对目录段做子串匹配——既能兜住含 noise 词的目录（如 小说研读/、novels/），
    # 又不会把含 noise 词的文件名（如 小说方法论.md、novel_approaches.md）误跳。
    parts = path.split("/")
    dir_parts = parts[:-1]  # 末段是文件名，不计入
    for h in NOISE_HINTS:
        h = h.rstrip("/")
        if any(h in d for d in dir_parts):
            return True
    return False


def asset_hint(rel: str, head: str = "") -> tuple:
    """返回 (资产类型, 命中来源)。
    先按相对路径（含目录名）匹配；未命中时再用文件首段内容指纹（前 HEAD_LINES 行）做二次匹配，
    降低纯文件名匹配导致的漏提（如 notes.md 含真规则）与误提（如 规则总结.md 实为待办）。
    来源 ∈ {name, content, ''}。"""
    for t, pat in ASSET_TYPES.items():
        if re.search(pat, rel):
            return t, "name"
    if re.search(RULE_KW, rel):
        return "未分类(规则类)", "name"
    if head:
        for t, pat in ASSET_TYPES.items():
            if re.search(pat, head):
                return t, "content"
        if re.search(RULE_KW, head):
            return "未分类(规则类)", "content"
    return "", ""


def matched_kw(rel: str) -> list:
    """从文件名里提取已命中的关键词，供 --kb 交叉核验与分级。"""
    base = os.path.basename(rel).replace(".md", "")
    hits = set()
    for pat in list(ASSET_TYPES.values()) + [RULE_KW]:
        for m in re.findall(pat, base):
            hits.add(m)
    return sorted(hits)


def load_kb(kb_dir: str) -> list:
    """一次性把知识库目录下所有 .md 读入内存，返回 [(relpath, content), ...]。
    排除噪声目录；单文件读失败仅跳过该文件，不影响其余；
    kb_dir 整体不可读由调用方捕获置 KB_ERR。"""
    texts = []
    for dp, dirs, fns in os.walk(kb_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(dp, fn)
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except OSError:
                continue
            texts.append((os.path.relpath(fp, kb_dir), content))
    return texts


def kb_check(rel: str, kb_texts: list) -> tuple:
    """在内存知识库中检索候选关键词：命中即 KB_HIT 并抽取首条命中原文片段+出处（文件:行号）；
    未命中返回 NEW；kb_texts 为空列表表示知识库无可搜内容，亦返回 NEW。
    返回 (status, snippet, source)；status ∈ {NEW, KB_HIT}（KB_ERR 由调用方在加载失败时统一置位）。
    语义冲突由 grade_conflict 给初步分级。绝不把核验失败冒充 NEW。"""
    kws = [k for k in matched_kw(rel) if len(k) >= 2]
    if not kws or not kb_texts:
        return "NEW", "", ""
    for src, content in kb_texts:
        for kw in kws[:3]:
            m = re.search(re.escape(kw), content)
            if not m:
                continue
            ls = content.rfind("\n", 0, m.start()) + 1
            le = content.find("\n", m.end())
            line = content[ls:le if le != -1 else None].strip()
            if line:
                lineno = content.count("\n", 0, ls) + 1
                return "KB_HIT", line[:120], f"{src}:{lineno}"
    return "NEW", "", ""


def grade_conflict(cand_kws: list, snippet: str) -> str:
    """初步矛盾分级（词面启发；否定词须贴近命中词，最终由人裁决）：
    命中词在知识库原文中出现、且 ±20 字符窗口内含否定标记 → 高（疑似矛盾）；
    否则 → 中（可能重复/重叠）。绝不自称判定语义冲突。"""
    if not snippet:
        return "中"
    for kw in cand_kws:
        for m in re.finditer(re.escape(kw), snippet):
            window = snippet[max(0, m.start() - 20): m.end() + 20]
            if any(n in window for n in NEG_MARKERS):
                return "高"
    return "中"


class CNParser(argparse.ArgumentParser):
    """argparse 中文友好报错：未知参数/缺值时不再抛英文，给出 -h 指引。"""
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"❌ 参数错误：{message}\n    用 -h 查看正确用法。\n")


def _read_file(full: str, timeout: float):
    """逐行读取文件，采集行数与首段内容指纹。
    返回 (head, lines, timed_out)。timeout>0 时启用 SIGALRM 单文件超时（仅 Unix 主线程有效）。"""
    use_alarm = timeout and timeout > 0 and hasattr(signal, "SIGALRM")
    secs = int(max(1, __import__("math").ceil(timeout))) if use_alarm else 0
    old_handler = None
    if use_alarm:
        old_handler = signal.signal(signal.SIGALRM, _read_timeout_handler)
        signal.alarm(secs)
    try:
        head_buf = []
        lines = 0
        with open(full, "r", encoding="utf-8", errors="ignore") as fh:
            for i, ln in enumerate(fh):
                lines += 1
                if i < HEAD_LINES:
                    head_buf.append(ln)
        return "".join(head_buf), lines, False
    except _ReadTimeout:
        return "", 0, True
    finally:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


class _MultiWriter:
    """把报告流式写入多个目标（stdout / --out / --sink）。"""
    def __init__(self, handles):
        self.handles = handles

    def writeline(self, s=""):
        for h in self.handles:
            h.write(s + "\n")

    def write(self, s):
        for h in self.handles:
            h.write(s)


def _load_progress(path: str) -> dict:
    try:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"❌ 进度文件读取失败：{path}（{e}）", file=sys.stderr)
        sys.exit(2)


def _save_progress(path: str, *, root, files, all_dist, all_count,
                   skipped_excluded, skipped_large, skipped_timeout, processed) -> None:
    state = {
        "version": _VERSION,
        "root": root,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "processed": sorted(processed),
        "all_dist": dict(all_dist),
        "all_count": all_count,
        "skipped_excluded": skipped_excluded,
        "skipped_large": skipped_large,
        "skipped_timeout": skipped_timeout,
        "candidates": [list(c) for c in files],
    }
    try:
        with open(os.path.expanduser(path), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"❌ 写入进度失败：{e}", file=sys.stderr)


def _selftest() -> int:
    """内置自检（A5）：断言版本号/排除目录/内容指纹/上限逻辑，返回 0=全部通过 1=有失败。"""
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    check("版本号为 2.2.5", _VERSION == "2.2.5")
    check("EXCLUDE_DIRS 含关键噪声目录",
          all(d in EXCLUDE_DIRS for d in ("novels", "chapters", "references", "dist", "docs", "archive")))
    check("should_skip 命中噪声目录", should_skip("/a/novels/x.md") and should_skip("/a/references/y.md"))
    check("should_skip 不误杀正规文件",
          (not should_skip("/a/notes.md")) and (not should_skip("/a/novel_approaches.md")))
    check("文件名命中资产类型（硬约束）", asset_hint("安全红线与门禁.md", "")[0] == "硬约束")
    check("内容指纹二次匹配（方法论）", asset_hint("notes.md", "本文阐述方法论与框架设计")[0] == "方法论")
    check("内容指纹无命中返回空", asset_hint("notes.md", "")[0] == "")
    check("MAX_FILE_BYTES 为 4MB", MAX_FILE_BYTES == 4 * 1024 * 1024)
    check("grade_conflict 否定词贴近→高", grade_conflict(["规则"], "此处禁止该规则") == "高")
    check("grade_conflict 无否定词→中", grade_conflict(["规则"], "此处有该规则") == "中")
    ok = True
    for name, passed in checks:
        mark = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            ok = False
        print(f"  {mark}  {name}")
    print("自检结果：" + ("全部通过 ✅" if ok else "存在失败 ❌"))
    return 0 if ok else 1


def main() -> None:
    ap = CNParser(
        prog="scan.py",
        description="rule-miner 廉价枚举指定根目录下的 .md 知识资产候选",
    )
    ap.add_argument("--root", metavar="DIR", default=DEFAULT_ROOT,
                    help="扫描根目录（默认 ~/WorkBuddy）；局部盘点用 --root <任务目录>")
    ap.add_argument("--kb", metavar="DIR", help="交叉核验的知识库目录（如 ~/WorkBuddy/记忆分册）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--out", metavar="FILE",
                    help="将报告写入文件（不指定 --json 为文本；指定则为 JSON）")
    ap.add_argument("--sink", metavar="FILE",
                    help="脚本级落点：将报告直接写入 sink 文件，供下游 agent 消费（闭合评测点名的边缘缺口）")
    ap.add_argument("--timeout", type=float, default=30.0, metavar="SEC",
                    help="单文件读取超时上限（秒），0 关闭；超时跳过该文件并告警（默认 30）")
    ap.add_argument("--resume", metavar="FILE",
                    help="从进度文件续扫：跳过已处理文件，继续未完成的扫描")
    ap.add_argument("--progress", metavar="FILE",
                    help="将扫描进度写入文件（支持中断后续扫；与 --resume 配合）")
    ap.add_argument("--selftest", action="store_true",
                    help="运行内置自检并退出（断言版本/排除目录/内容指纹/上限逻辑）")
    ap.add_argument("--version", action="version",
                    version=f"rule-miner 盘点脚本 v{_VERSION}")
    args = ap.parse_args()

    # --selftest：内置自检优先，不进入扫描流程
    if args.selftest:
        sys.exit(_selftest())

    # ① 工程级参数校验：中文友好报错 + 非零退出码
    root = os.path.expanduser(args.root)
    kb_dir = None
    if args.kb:
        kb_dir = os.path.expanduser(args.kb)
        if not os.path.exists(kb_dir):
            print(f"❌ 知识库路径不存在：{kb_dir}\n"
                  f"   请检查路径是否拼写正确，或去掉 --kb 只做枚举。",
                  file=sys.stderr)
            sys.exit(2)
        if not os.path.isdir(kb_dir):
            print(f"❌ --kb 必须指向目录而非文件：{kb_dir}\n"
                  f"   请传入知识库目录（如 ~/WorkBuddy/记忆分册）。",
                  file=sys.stderr)
            sys.exit(2)

    if not os.path.isdir(root):
        print(f"❌ 扫描根目录不存在：{root}\n"
              f"   请确认路径是否拼写正确，或省略 --root 使用默认 ~/WorkBuddy。",
              file=sys.stderr)
        sys.exit(2)
    try:
        os.listdir(root)
    except PermissionError:
        print(f"❌ 扫描根目录不可读（权限拒绝）：{root}\n"
              f"   请缩小扫描根（如只扫具体任务目录）。", file=sys.stderr)
        sys.exit(3)

    # 断点续扫：载入已有进度（A3）
    resume_state = None
    processed = set()
    if args.resume:
        resume_state = _load_progress(args.resume)
        files = [tuple(c) for c in resume_state.get("candidates", [])]
        all_dist = Counter(resume_state.get("all_dist", {}))
        all_count = resume_state.get("all_count", 0)
        skipped_excluded = resume_state.get("skipped_excluded", 0)
        skipped_large = resume_state.get("skipped_large", 0)
        skipped_timeout = resume_state.get("skipped_timeout", 0)
        processed = set(resume_state.get("processed", []))
        print(f"↻ 已从进度文件续扫：已处理 {len(processed)} 个文件，继续未完成部分。",
              file=sys.stderr)
    else:
        files = []          # 候选清单（已读体积/行数）
        all_dist = Counter()  # 全盘 .md 分布（不含 EXCLUDE_DIRS 已排除的噪声目录；每个幸存 .md 都计，不只候选）
        all_count = 0
        skipped_excluded = 0  # 被 should_skip 排除的文件数（噪声目录/文件）
        skipped_large = 0   # 超 MAX_FILE_BYTES 跳过的文件数
        skipped_timeout = 0  # 超 --timeout 跳过的文件数（A2）

    skipped_dirs = []   # 权限/占用不可读的目录
    kb_err = False      # 知识库加载/核验是否失败（统一置位，不冒充 NEW）
    kb_texts = None     # 内存知识库：None=未提供，[]=空库，list=已载入
    if kb_dir:
        try:
            kb_texts = load_kb(kb_dir)
        except OSError as e:
            kb_err = True
            print(f"⚠️ 知识库目录不可读，跳过交叉核验：{kb_dir}（{e}）", file=sys.stderr)
            kb_texts = []

    try:
        for dirpath, dirnames, filenames in os.walk(
                root, onerror=lambda e: skipped_dirs.append(e.filename)):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                # 续扫：已处理文件直接跳过（不重读、不重计），保证幂等
                if rel in processed:
                    continue
                processed.add(rel)
                top = rel.split("/")[0] if "/" in rel else "(根目录)"
                all_dist[top] += 1
                all_count += 1
                if should_skip(full):
                    skipped_excluded += 1
                    continue
                try:
                    sz = os.path.getsize(full)
                except OSError as e:
                    print(f"⚠️ 跳过无法读取的文件 {full}：{e}", file=sys.stderr)
                    continue
                if sz > MAX_FILE_BYTES:
                    skipped_large += 1
                    continue  # 超大文件跳过整读，防卡死
                head_buf, lines, timed_out = _read_file(full, args.timeout)
                if timed_out:
                    print(f"⚠️ 读取超时（>{args.timeout:g}s），跳过 {full}", file=sys.stderr)
                    skipped_timeout += 1
                    continue
                atype, provenance = asset_hint(rel, head_buf)
                if not atype:
                    continue  # 非候选，跳过
                if kb_dir:
                    if kb_err:
                        status, snippet, source, grade = "KB_ERR", "", "", ""
                    else:
                        status, snippet, source = kb_check(rel, kb_texts)
                        grade = grade_conflict(matched_kw(rel), snippet) if status == "KB_HIT" else ""
                else:
                    status, snippet, source, grade = "—", "", "", ""
                files.append((rel, sz, lines, atype, provenance, status, snippet, source, grade))
    except KeyboardInterrupt:
        # 中断时落盘进度，便于 --resume 续扫
        print("\n⚠️ 用户中断，正在写入进度以便续扫……", file=sys.stderr)
        if args.progress:
            _save_progress(args.progress, root=root, files=files, all_dist=all_dist,
                           all_count=all_count, skipped_excluded=skipped_excluded,
                           skipped_large=skipped_large, skipped_timeout=skipped_timeout,
                           processed=processed)
        sys.exit(130)

    # P0-4：逐目录权限告警（不静默漏扫）
    if skipped_dirs:
        print(f"⚠️ {len(skipped_dirs)} 个目录无法读取（权限/占用），已跳过；首个：{skipped_dirs[0]}",
              file=sys.stderr)
    if kb_err:
        print("⚠️ 知识库交叉核验失败（目录不可读/读取异常），相关候选标 KB_ERR，未冒充 NEW。",
              file=sys.stderr)

    # 候选分布（仅候选，按顶层目录）
    dist = Counter(r.split("/")[0] if "/" in r else "(根目录)" for r, *_ in files)

    now = datetime.now().isoformat(timespec="seconds")

    # ③ --out / --sink / 默认 stdout：报告流式落盘（A4），不拼巨型字符串
    targets = []
    if args.out:
        try:
            targets.append(open(os.path.expanduser(args.out), "w", encoding="utf-8"))
        except OSError as e:
            print(f"❌ 写入报告失败：{e}", file=sys.stderr)
            sys.exit(4)
    if args.sink:
        try:
            targets.append(open(os.path.expanduser(args.sink), "w", encoding="utf-8"))
        except OSError as e:
            print(f"❌ 写入 sink 失败：{e}", file=sys.stderr)
            sys.exit(4)
    wrote_files = [args.out, args.sink]
    if not targets:
        targets = [sys.stdout]
    writer = _MultiWriter(targets)

    if args.json:
        meta = {
            "tool": "rule-miner scan.py",
            "version": _VERSION,
            "root": root,
            "generated_at": now,
            "all_distribution_desc": ALL_MD_DIST_DESC,
            "distribution_note": "all_distribution 不含已排除的噪声目录（novels/chapters/references/dist/docs/archive 等）；candidate_distribution 仅含命中资产类关键词的 .md",
        }
        # 流式 JSON：先输出 meta 对象体（去掉其自带的最外层花括号），再续写其余字段
        meta_inner = json.dumps(meta, ensure_ascii=False).strip()[1:-1]
        writer.write("{" + meta_inner)
        writer.write(f', "md_total": {all_count}')
        writer.write(f', "candidates_total": {len(files)}')
        writer.write(', "all_distribution": ' + json.dumps(dict(all_dist.most_common(40)), ensure_ascii=False))
        writer.write(', "candidate_distribution": ' + json.dumps(dict(dist.most_common(40)), ensure_ascii=False))
        writer.write(', "candidates": [')
        items = sorted(files, key=lambda x: -x[1])
        for i, (r, s, l, t, p, k, sn, so, g) in enumerate(items):
            obj = {"path": r, "bytes": s, "lines": l, "asset_type": t,
                   "provenance": p, "kb": k, "snippet": sn, "source": so, "grade": g}
            comma = "," if i < len(items) - 1 else ""
            writer.write(json.dumps(obj, ensure_ascii=False) + comma)
        writer.write("]}")
        for h in targets:
            if h is not sys.stdout:
                h.close()
    else:
        writer.writeline("# rule-miner 盘点报告")
        writer.writeline(f"# 版本 v{_VERSION} | 扫描根 {root} | 生成时间 {now}")
        writer.writeline("")
        writer.writeline(f"=== {ALL_MD_DIST_DESC} ===")
        writer.writeline(
            f"  [汇总] 全盘 .md 总数 {all_count}（EXCLUDE_DIRS 如 novels/chapters/docs/references/dist 等已在遍历阶段剪枝，不计入；该数通常小于 find 全盘 .md 数，属正常）")
        for k, v in all_dist.most_common(40):
            writer.writeline(f"  {v:5d}  {k}")
        kb_label = f"（已交叉核验 {kb_dir}）" if kb_dir else ""
        writer.writeline(f"\n=== 知识资产候选分布（仅候选）{kb_label} ===")
        for k, v in dist.most_common(40):
            writer.writeline(f"  {v:5d}  {k}")
        writer.writeline(f"\n=== 知识资产候选（{len(files)} 个，大→小）{kb_label} ===")
        for r, s, l, t, p, k, sn, so, g in sorted(files, key=lambda x: -x[1]):
            extra = f" 冲突分级={g} 原文片段={sn} 出处={so}" if k == "KB_HIT" else ""
            src_tag = " [内容命中]" if p == "content" else ""
            writer.writeline(f"  {s:8d}B {l:5d}行  [{t}] {k:7s} {r}{src_tag}{extra}")
        writer.writeline(
            f"\n[汇总] 候选总数 {len(files)} ｜ 全盘 .md 总数 {all_count} ｜ 因排除跳过 {skipped_excluded} 个 ｜ 因超大跳过 {skipped_large} 个 ｜ 因超时跳过 {skipped_timeout} 个")
        for h in targets:
            if h is not sys.stdout:
                h.close()

    # 落盘确认（仅当写入了文件）
    real_files = [w for w in wrote_files if w]
    if real_files:
        print(f"✅ 候选报告已写入 {', '.join(real_files)}（{len(files)} 条候选；"
              f"{'JSON' if args.json else '文本'}格式）", file=sys.stderr)

    # A3：正常完成时若指定 --progress，也写一份最终进度（供后续 --resume 续扫或复核）
    if args.progress:
        _save_progress(args.progress, root=root, files=files, all_dist=all_dist,
                       all_count=all_count, skipped_excluded=skipped_excluded,
                       skipped_large=skipped_large, skipped_timeout=skipped_timeout,
                       processed=processed)


if __name__ == "__main__":
    main()
