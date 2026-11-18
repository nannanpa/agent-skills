#!/usr/bin/env python3
# agent-bridge v0.1.3 —— B 档「人工投递查看器」·零常驻智能体通讯桥
# 协议：四段式＋停函（规则自含于本文件头注释与 SKILL.md，不依赖外部文档）
# 用法：python3 bridge.py wb   收对端信（dsh-*函-*.md）
#       python3 bridge.py dsh  收本端信（wb-prompt-*.txt）
#       --side 前缀可选：bridge.py --side wb 与 bridge.py wb 等价（B2）
#       --ws <目录> 指定收件箱；不传则读环境变量 AGENT_BRIDGE_WS，再退默认值
# v0.1.3 变更（按 SkillHub 评测整改，不改协议闸门逻辑）：
#   1) 收件箱路径可配置（--ws / AGENT_BRIDGE_WS），换机不再必然 exit 2
#   2) fcntl 缺失时降级为无锁运行（Windows 可用），并给出一次提示
#   3) 转人工/读取失败不再全静默，向 stderr 报文件名，退出码语义不变
import argparse, json, os, re, sys, glob, shutil, tempfile
from datetime import datetime

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:      # Windows 等无 fcntl 的环境：降级为无锁，不崩溃
    fcntl = None
    HAS_FCNTL = False

HOME = os.path.expanduser("~")
DEFAULT_WS = os.path.join(HOME, "Documents", "deepseek-harness", "default-workspace")
ENV_WS = "AGENT_BRIDGE_WS"
LIMIT = 3  # 协商限三（两端自动往返合计）

USAGE_HINT = (
    "用法：\n"
    "  python3 bridge.py wb    收对端的信（dsh-*函-*.md）\n"
    "  python3 bridge.py dsh   收本端的信（wb-prompt-*.txt）\n"
    "  --side wb 与 wb 等价；--ws <目录> 指定收件箱（或设 AGENT_BRIDGE_WS）。\n"
    "  无信时静默 exit 0。\n"
)


def die(msg, fix):
    """参数/环境级错误：中文报错 + 怎么办 + exit 2。绝不用于协议闸门。"""
    sys.stderr.write(f"[bridge] {msg}\n怎么办：{fix}\n{USAGE_HINT}")
    sys.exit(2)


class Parser(argparse.ArgumentParser):
    """argparse 的默认报错是英文且不带『怎么办』，这里统一成中文。"""

    def error(self, message):
        # 常见两类：--side 缺值、未知参数
        if "--side" in message:
            die("--side 后面缺值。", "补上 side：`--side wb` 或 `--side dsh`。")
        die(f"参数不合法：{message}", "按上面用法传 wb 或 dsh，二选一。")


def human_move(path, human_dir, name):
    stamp = datetime.now().strftime("%H%M%S")
    try:
        shutil.move(path, os.path.join(human_dir, f"{stamp}-{name}"))
    except OSError as e:
        # 并发已被处理属正常情形；权限/占用则需让人看见。都只提示，不改退出码语义。
        sys.stderr.write(
            f"[bridge] 转人工未成功（{e.strerror}）：{name}，仍留在收件箱，下一轮再试。\n")


def parse_args(argv):
    ap = Parser(prog="bridge.py", add_help=True,
                description="agent-bridge：零常驻智能体通讯桥（B 档人工投递查看器）")
    ap.add_argument("side_pos", nargs="?", metavar="wb|dsh", help="收信侧：wb 或 dsh")
    ap.add_argument("--side", dest="side_opt", metavar="wb|dsh", help="与位置参数等价（B2）")
    ap.add_argument("--ws", dest="ws", metavar="目录",
                    help=f"收件箱目录；缺省读环境变量 {ENV_WS}，再退默认")
    a = ap.parse_args(argv)
    side = a.side_opt or a.side_pos or ""
    if not side:
        die("没有指定收信侧（side）。", "加一个 side：`python3 bridge.py wb` 或 `python3 bridge.py dsh`。")
    if side not in ("wb", "dsh"):
        die(f"side 不合法：{side!r}。", f"只接受 wb 或 dsh，例如 `python3 bridge.py dsh`。")
    if a.side_opt and a.side_pos and a.side_opt != a.side_pos:
        die(f"两处 side 打架：--side={a.side_opt}，位置参数={a.side_pos}。",
            "只留一个；要等价用 `--side wb` 或直接 `wb`。")
    ws = a.ws or os.environ.get(ENV_WS) or DEFAULT_WS
    return side, os.path.abspath(os.path.expanduser(ws))


def ensure_env(ws):
    """环境级检查：路径不存在/不可读 → exit 2（此前是静默 exit 0，会让人以为『没信』）。"""
    if not os.path.isdir(ws):
        die(f"收件箱目录不存在：{ws}",
            f"用 `--ws <目录>` 指定正确路径，或设环境变量 {ENV_WS}；默认 {DEFAULT_WS}。")
    if not os.access(ws, os.R_OK | os.X_OK):
        die(f"收件箱目录不可读：{ws}",
            "检查目录权限（chmod +rx 该目录），或换有权限的账号运行。")
    for d in ("claimed", "pending-人工"):
        p = os.path.join(ws, d)
        try:
            os.makedirs(p, exist_ok=True)
        except OSError as e:
            die(f"无法创建目录：{p}（{e.strerror}）", "检查父目录权限，或手动建好这两个目录再跑。")
    return ws


def main():
    side, ws = parse_args(sys.argv[1:])
    ensure_env(ws)

    pattern = "dsh-*函-*.md" if side == "wb" else "wb-prompt-*.txt"  # B3：回函/回执也收
    inbox = sorted(glob.glob(os.path.join(ws, pattern)))
    claimed_dir = os.path.join(ws, "claimed")
    human_dir = os.path.join(ws, "pending-人工")

    if HAS_FCNTL:
        lock = open(os.path.join(tempfile.gettempdir(), "agent-bridge.lock"), "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # B4：并发互斥
        except OSError:
            sys.exit(0)  # 另一进程正在领信：静默让路（运行时状态，不是错误）
    else:
        sys.stderr.write(
            "[bridge] 当前系统无 fcntl，已降级为无锁运行：并发调用时可能重复领同一封信。\n")

    for path in inbox:
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError as e:
            sys.stderr.write(f"[bridge] 读信失败（{e.strerror}），留给下一轮：{name}\n")
            continue  # 读不走：留给下一轮
        m = re.search(r"^〔线程〕[ \t]*(.+?)[ \t]*$", body, re.M)  # B5：整行取 slug
        thread = m.group(1) if m else None
        if thread is None:
            human_move(path, human_dir, name)
            continue  # B5：缺〔线程〕＝协议违规，拒收转人工，不伪造
        mt = re.search(r"^〔类型〕[ \t]*(派发|回执|终结|请示)", body, re.M)
        mtype = mt.group(1) if mt else None
        if mtype is None:
            human_move(path, human_dir, name)
            continue  # B6：无〔类型〕拒收转人工
        seen = 0
        has_receipt = False
        for c in glob.glob(os.path.join(claimed_dir, "*")):
            try:
                with open(c, encoding="utf-8", errors="replace") as f:
                    cb = f.read()
            except OSError:
                continue
            if re.search(r"^〔线程〕[ \t]*" + re.escape(thread) + r"[ \t]*$", cb, re.M):
                seen += 1  # B5：整行匹配，杜绝空格串线与标点失效
                if re.search(r"^〔类型〕[ \t]*回执", cb, re.M):
                    has_receipt = True  # B6：回执即终的机器可判据
        if seen >= LIMIT:
            human_move(path, human_dir, name)
            continue  # 第 4 封：硬拦转人工（规范 §4.3）
        if has_receipt and mtype != "回执":
            human_move(path, human_dir, name)
            continue  # B6：线程已终结，新信转人工
        if mtype == "请示":
            human_move(path, human_dir, name)
            continue  # B6：请示只发本端负责人，桥不投给对方
        if seen == LIMIT - 1 and mtype == "派发":
            human_move(path, human_dir, name)
            continue  # B6：第 3 封只能是终结/请示，派发拦下
        claimed = os.path.join(claimed_dir, f"{datetime.now().strftime('%H%M%S')}-{name}")
        try:
            shutil.move(path, claimed)
        except OSError:
            sys.exit(0)  # B4：已被并发进程领走：静默，不打断宿主
        print(json.dumps({
            "file": name,
            "thread": thread,
            "n": seen + 1,
            "from": "DSH" if side == "wb" else "WB",
            "body": body,
        }, ensure_ascii=False))
        sys.exit(0)  # 一轮只投一封

    sys.exit(0)  # 无信：静默退出


if __name__ == "__main__":
    main()
