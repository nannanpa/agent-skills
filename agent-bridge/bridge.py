#!/usr/bin/env python3
# agent-bridge v0.2.0 —— 单机多 agent 的零常驻通讯桥（B 档「人工投递查看器」）
#
# 规格：2026-11-27_agent-bridge分发版-核心层规格v0.2.md（2026-11-27 双方签毕定版，签前基线 c54cb10a…）
# 协议：信格式与闸门语义见《WB与DSH消息收发规范》v1.1；本文件只实现，不复述。
#
# 用户只会遇到三样东西：端点（agent 的名字）、收件箱（一个共享目录）、信（一个文件）。
# 用法：
#   python3 bridge.py init              # 首次配置：问三句（本端、对端、收件箱）
#   python3 bridge.py <端点名>           # 收自己名下的信
#   python3 bridge.py <端点名> --ws <目录>  # 临时换收件箱
#
# 退出码：参数/环境错 = 2（中文报错 + 怎么办）；无信、并发让路、闸门转人工 = 0。
import argparse, glob, json, os, re, shutil, string, subprocess, sys, tempfile
from datetime import datetime

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:          # Windows 等无 fcntl 环境：降级无锁，不崩
    fcntl = None
    HAS_FCNTL = False

HOME = os.path.expanduser("~")
IDENT_DIR = os.path.join(HOME, ".agent-bridge")
DEFAULT_WS = "./.bridge"
REG_NAME = "bridge-endpoints.json"
LIMIT = 3                    # 协商限三（一对端点往返合计）
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
# 文件名：<发端>-<YYYY-MM-DD>-<主题>.<md|txt>；发端可含 `-`，故以日期段为锚
LETTER_RE = re.compile(r"^(?P<sender>.+)-(?P<date>\d{4}-\d{2}-\d{2})-(?P<topic>[a-z0-9-]+)\.(?P<ext>md|txt)$")
CLAIMED_RE = re.compile(r"^(?P<ts>\d{6})__to__(?P<to>[a-z0-9-]+)__(?P<orig>.+)$")

USAGE = (
    "用法：\n"
    "  python3 bridge.py init              首次配置（本端、对端、收件箱）\n"
    "  python3 bridge.py <端点名>           收自己名下的信\n"
    "  python3 bridge.py <端点名> --ws <目录>  临时换收件箱\n"
    "  没有信时静默退出（退出码 0）。\n"
)


def die(msg, fix):
    """参数/环境级错误：中文报错 + 怎么办 + exit 2。绝不用于协议闸门。"""
    sys.stderr.write(f"[bridge] {msg}\n怎么办：{fix}\n{USAGE}")
    sys.exit(2)


def say(msg):
    """给人看的话一律走 stderr，stdout 只留给机器可读的 JSON。"""
    sys.stderr.write(msg + "\n")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        die(f"参数不合法：{message}", "对照下面用法；不确定就先跑 `bridge.py init`。")


# ---------- 小工具 ----------

def abspath(p):
    return os.path.abspath(os.path.expanduser(p))


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def empty_registry():
    return {"schema": 1, "endpoints": {}, "aliases": {}}


def load_registry(ws):
    reg = read_json(os.path.join(ws, REG_NAME))
    if not isinstance(reg, dict):
        return None
    reg.setdefault("schema", 1)
    reg.setdefault("endpoints", {})
    reg.setdefault("aliases", {})
    if not isinstance(reg["endpoints"], dict) or not isinstance(reg["aliases"], dict):
        return None
    return reg


def identity_path(slug):
    return os.path.join(IDENT_DIR, f"{slug}.identity")


def load_identity(slug):
    return read_json(identity_path(slug))


def listen_dir(ws, slug):
    return os.path.join(ws, slug)


# ---------- 候选名：从本机名推，但一定清洗 ----------

def clean_host():
    raw = ""
    try:
        out = subprocess.run(["scutil", "--get", "LocalHostName"],
                             capture_output=True, text=True, timeout=2)
        if out.returncode == 0:
            raw = out.stdout.strip()
    except Exception:
        pass
    if not raw:
        import socket
        try:
            raw = socket.gethostname()
        except Exception:
            raw = ""
    raw = raw.lower()
    for suf in (".local", ".localdomain", ".lan", ".home"):
        if raw.endswith(suf):
            raw = raw[: -len(suf)]
    raw = re.sub(r"[^a-z0-9-]+", "-", raw)   # 空格、点号、下划线、中文一律变连字符
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw[:24].strip("-")               # 给 `-<字母>` 留位，总长不超 31


def free_slug(host, reg, taken=()):
    for ch in string.ascii_lowercase:
        cand = f"{host}-{ch}" if host else ch
        if cand in reg["endpoints"] or cand in taken:
            continue
        return cand
    return (host or "a") + "-z"


# ---------- init ----------

def ask(label, default):
    sys.stderr.write(f"{label}？[候选 {default}] " if label != "收件箱" else f"{label}：[{default}]  （回车用默认；也可给已有目录） ")
    sys.stderr.flush()
    line = sys.stdin.readline()
    if not sys.stdin.isatty():
        sys.stderr.write("\n")     # 管道喂入时补个换行，日志才读得清
    if line == "":
        die("需要交互输入，但没读到内容。",
            "在终端里跑 `bridge.py init`；或把三行输入喂进来：`printf 'a\\nb\\n\\n' | bridge.py init`。")
    return line.strip() or default


def cmd_init(argv):
    ap = Parser(prog="bridge.py init", add_help=True,
                description="首次配置：登记本端与对端，建收件箱目录")
    ap.add_argument("--ws", metavar="目录", help="收件箱（默认 ./.bridge）")
    ap.add_argument("--force", action="store_true", help="覆盖已绑定/已存在的条目")
    ap.add_argument("--alias", action="append", default=[], metavar="旧名=端点名",
                    help="登记旧调用别名（可重复），例如 --alias 旧名=<端点名>")
    a = ap.parse_args(argv)

    provisional = abspath(a.ws or DEFAULT_WS)
    reg = load_registry(provisional) or empty_registry()
    if reg["endpoints"]:
        say(f"已登记端点：{', '.join(sorted(reg['endpoints']))}")

    host = clean_host()
    local_c = free_slug(host, reg)
    peer_c = free_slug(host, reg, taken=(local_c,))

    local = ask("本端叫什么", local_c)
    peer = ask("对端叫什么", peer_c)
    ws = abspath(ask("收件箱", a.ws or DEFAULT_WS))

    for name, label in ((local, "本端"), (peer, "对端")):
        if not SLUG_RE.match(name or ""):
            die(f"{label}名不合规：{name!r}",
                "只能用小写字母、数字与连字符，首位不能是连字符，长度 1–31。")
    if local == peer:
        die("本端与对端同名。", "给两个 agent 各起一个名字。")

    # 换了收件箱：以最终 ws 的注册表为准
    if ws != provisional:
        reg = load_registry(ws) or empty_registry()

    ident = load_identity(local)
    if ident and abspath(ident.get("ws", "")) != ws and not a.force:
        die(f"端点名 {local} 已绑定到 {ident.get('ws')}。",
            "换个名字，或加 `--force` 改绑（会把旧绑定改成新收件箱）。")

    entry = reg["endpoints"].get(local)
    if entry and not a.force:
        say(f"已配置：本端 {local}、对端 {peer}、收件箱 {ws}。未做改动（要覆盖加 --force）。")
        say(f"下一步：python3 bridge.py {local}")
        return 0

    # 注册表只增不改；空对象条目保留原样
    reg["endpoints"].setdefault(local, {})
    reg["endpoints"].setdefault(peer, {})
    for item in a.alias:
        if "=" not in item:
            die(f"--alias 写法不对：{item!r}", "写成 `--alias 旧名=端点名`，例如 `--alias 旧名=mac-mini-a`。")
        old, new = item.split("=", 1)
        if new not in reg["endpoints"]:
            die(f"别名指向的端点不存在：{new}", "先登记该端点，或改指向已有端点。")
        reg["aliases"][old] = new

    try:
        os.makedirs(ws, exist_ok=True)
        for d in (local, peer, "claimed", "pending-人工"):
            os.makedirs(os.path.join(ws, d), exist_ok=True)
    except OSError as e:
        die(f"建目录失败：{ws}（{e.strerror}）", "检查父目录权限，或换一个可写目录。")

    write_json(os.path.join(ws, REG_NAME), reg)
    write_json(identity_path(local), {"slug": local, "ws": ws,
                                      "created": datetime.now().isoformat(timespec="seconds")})

    gi = os.path.join(os.getcwd(), ".gitignore")
    try:
        have = open(gi, encoding="utf-8").read() if os.path.isfile(gi) else ""
    except OSError:
        have = ""
    rel = os.path.relpath(ws, os.getcwd())
    if rel.startswith(".") and rel != "." and rel.split(os.sep)[0] not in have:
        say(f"提示：收件箱 {rel} 建议写进 .gitignore（本工具不自动改文件）。")

    say(f"已配置：本端 {local}、对端 {peer}、收件箱 {ws}")
    say(f"下一步：python3 bridge.py {local}")
    return 0


# ---------- 收信 ----------

def parse_claimed(name):
    """claimed/ 里的文件名：<HHMMSS>__to__<收端>__<原文件名>。"""
    m = CLAIMED_RE.match(name)
    if not m:
        return None
    orig = m.group("orig")
    lm = LETTER_RE.match(orig)
    if not lm:
        return {"to": m.group("to"), "sender": None, "orig": orig}
    return {"to": m.group("to"), "sender": lm.group("sender"), "orig": orig}


def count_gate(ws, me, sender, thread):
    """按「端点对」计数，旧信（无收端标记）按线程 slug 并计（只紧不松）。"""
    claimed_dir = os.path.join(ws, "claimed")
    seen_pair = seen_legacy = 0
    has_receipt = False
    for path in glob.glob(os.path.join(claimed_dir, "*")):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError:
            continue
        if not re.search(r"^〔线程〕[ \t]*" + re.escape(thread) + r"[ \t]*$", body, re.M):
            continue
        info = parse_claimed(os.path.basename(path))
        if info is None:
            seen_legacy += 1                      # 旧版 claimed 命名：按线程计
        elif info["sender"] and {info["to"], info["sender"]} == {me, sender}:
            seen_pair += 1
        else:
            continue                              # 属于别的端点对，不计
        if re.search(r"^〔类型〕[ \t]*回执", body, re.M):
            has_receipt = True
    return seen_pair + seen_legacy, has_receipt


def cmd_receive(slug, argv):
    ap = Parser(prog=f"bridge.py {slug}", add_help=True,
                description=f"以端点 {slug} 的身份，收自己名下的信")
    ap.add_argument("--ws", metavar="目录", help="覆盖收件箱（默认取 init 记录）")
    ap.add_argument("--legacy-scan", action="store_true", help="额外扫收件箱根目录的旧版信")
    ap.add_argument("--legacy-from", action="store_true", help="JSON 的 from/to 输出旧别名（大写）")
    ap.add_argument("--side", dest="side", metavar="端点名", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    if a.side:
        if slug and a.side != slug:
            die(f"两处端点名打架：位置参数={slug}，--side={a.side}。",
                "只留一个；要么 `bridge.py a`，要么 `bridge.py --side a`。")
        slug = a.side

    ident = load_identity(slug)
    if a.ws:
        ws = abspath(a.ws)
    elif ident:
        ws = abspath(ident.get("ws", ""))
    else:
        ws = abspath(DEFAULT_WS)                   # 未登记也能给出「已登记端点」提示

    if not os.path.isdir(ws):
        die(f"收件箱不存在：{ws}",
            "它可能在 init 记录之后被移动/删除了；重跑 `bridge.py init --force` 重新绑定。")

    reg = load_registry(ws)
    if reg is None:
        die(f"这个目录还不是收件箱（没有 {REG_NAME}）：{ws}",
            "先跑 `bridge.py init`，或用 `--ws <目录>` 指向已配置的收件箱。")

    if slug not in reg["endpoints"]:
        target = reg["aliases"].get(slug)
        if target and target in reg["endpoints"]:
            ident = load_identity(target)
            slug = target
        else:
            known = "、".join(sorted(reg["endpoints"])) or "（空）"
            die(f"端点未登记：{slug}",
                f"已登记：{known}；要新增就跑 `bridge.py init`，换名字请重新 init。")

    me = slug
    if not ident:
        ident = load_identity(me)
    if not ident:
        die(f"这台机器还没登记端点 {me}。", "先跑 `bridge.py init`（问三句就配好）。")

    inbox = listen_dir(ws, me)
    if not os.path.isdir(inbox):
        die(f"收件箱缺本端目录：{inbox}", "重跑 `bridge.py init --force` 补齐目录。")

    claimed_dir = os.path.join(ws, "claimed")
    human_dir = os.path.join(ws, "pending-人工")
    for d in (claimed_dir, human_dir):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            die(f"建目录失败：{d}（{e.strerror}）", "检查收件箱权限。")

    if HAS_FCNTL:
        lock = open(os.path.join(tempfile.gettempdir(), "agent-bridge.lock"), "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit(0)                            # 另一进程正在领信：静默让路
    else:
        say("[bridge] 当前系统无 fcntl，已降级为无锁运行：并发调用时可能重复领同一封信。")

    files = sorted(glob.glob(os.path.join(inbox, "*")))
    letters, foreign = [], 0
    for path in files:
        name = os.path.basename(path)
        if not name.lower().endswith((".md", ".txt")):
            continue
        if name.lower().startswith("readme") or name == REG_NAME:
            continue                               # 说明文件与注册表不吭声
        if LETTER_RE.match(name):
            letters.append((path, name))
        else:
            foreign += 1
    if foreign:
        say(f"[bridge] 有 {foreign} 个文件名不合式，未领（应形如 <发端>-YYYY-MM-DD-<主题>.md）。")

    if a.legacy_scan:
        for old, target in reg["aliases"].items():
            if target != me:
                continue
            for pat in (f"{old}-prompt-*.txt", f"{old}-*函-*.md"):
                for path in sorted(glob.glob(os.path.join(ws, pat))):
                    letters.append((path, os.path.basename(path)))

    def to_human(path, name, why):
        stamp = datetime.now().strftime("%H%M%S")
        dst = os.path.join(human_dir, f"{stamp}__to__{me}__{name}")
        try:
            shutil.move(path, dst)
        except OSError as e:
            say(f"[bridge] 转人工未成功（{e.strerror}）：{name}，仍留在收件箱，下一轮再试。")
        say(f"[bridge] 转人工：{name}（{why}）")

    for path, name in letters:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError as e:
            say(f"[bridge] 读信失败（{e.strerror}），留给下一轮：{name}")
            continue

        lm = LETTER_RE.match(name)
        sender = lm.group("sender") if lm else None

        m = re.search(r"^〔线程〕[ \t]*(.+?)[ \t]*$", body, re.M)
        thread = m.group(1) if m else None
        if thread is None:
            to_human(path, name, "缺〔线程〕")
            continue

        mt = re.search(r"^〔类型〕[ \t]*(派发|回执|终结|请示)", body, re.M)
        mtype = mt.group(1) if mt else None
        if mtype is None:
            to_human(path, name, "缺〔类型〕")
            continue

        if sender is None:
            to_human(path, name, "文件名看不出发端")
            continue

        seen, has_receipt = count_gate(ws, me, sender, thread)

        if seen >= LIMIT:
            to_human(path, name, "第 4 封超限（协商限三）")
            continue
        if has_receipt and mtype != "回执":
            to_human(path, name, "该端点对的线程已终结")
            continue
        if mtype == "请示":
            to_human(path, name, "请示只发本端负责人")
            continue
        if seen == LIMIT - 1 and mtype == "派发":
            to_human(path, name, "第 3 封只能是终结/回执")
            continue

        stamp = datetime.now().strftime("%H%M%S")
        claimed = os.path.join(claimed_dir, f"{stamp}__to__{me}__{name}")
        try:
            shutil.move(path, claimed)
        except OSError:
            sys.exit(0)                            # 已被并发进程领走

        out_from, out_to = sender, me
        if a.legacy_from:
            rev = {v: k for k, v in reg["aliases"].items()}
            out_from = (rev.get(sender) or sender).upper()
            out_to = (rev.get(me) or me).upper()
        print(json.dumps({
            "file": name,
            "thread": thread,
            "from": out_from,
            "to": out_to,
            "n": seen + 1,
            "body": body,
        }, ensure_ascii=False))
        sys.exit(0)                                # 一轮只投一封

    sys.exit(0)


# ---------- 入口 ----------

def main(argv):
    if not argv:
        ident = []
        if os.path.isdir(IDENT_DIR):
            ident = [f for f in os.listdir(IDENT_DIR) if f.endswith(".identity")]
        if ident:
            slugs = sorted(f[: -len(".identity")] for f in ident)
            die("没有指定端点名。",
                f"已登记：{'、'.join(slugs)}；照这样接一个名字：`python3 bridge.py {slugs[0]}`。")
        die("还没配置。", "先跑 `bridge.py init`（问三句：本端、对端、收件箱）。")

    head = argv[0]
    if head in ("-h", "--help"):
        sys.stderr.write(USAGE)
        sys.exit(0)
    if head == "--side":
        if len(argv) < 2:
            die("--side 后面缺值。", "补上端点名，例如 `--side mac-mini-a`。")
        return cmd_receive(argv[1], argv[2:])
    if head == "init":
        return cmd_init(argv[1:])
    if head.startswith("-"):
        die(f"未知参数：{head}", "第一条命令只能是 `init` 或一个已登记的端点名。")
    return cmd_receive(head, argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
