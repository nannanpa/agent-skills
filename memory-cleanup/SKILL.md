---
name: memory-cleanup
description: macOS 内存卫生巡检与收尾。先读 config 阈值并每轮打印"本次按什么阈值执行"，再做只读巡检（内存空闲、swap 已用、agent 自动化浏览器实例数、微信类进程数），需要动手时只对白名单路径做精确清理，并给出回收站两段式归档。适用于长跑 agent 任务后内存吃紧、swap 上涨、出现彩虹圈。触发词：内存清理、清理内存、收尾清理、任务收尾、内存巡检、swap 高、彩虹圈、回收站归档、调内存阈值。
---

# memory-cleanup · macOS 内存卫生（只读巡检 ＋ 白名单清理）

> 版本 **1.0.2** ｜ 平台 macOS（Apple Silicon / Intel 通用）｜ 依赖 `bash`、`pgrep`、`sysctl`；`jq` 可选（缺则降级）
> 本技能的判据来源：本机命令行与路径证据。**所有归属类判断（某进程属于哪个程序、某路径属于哪个工具）均为本地证据，不构成对该进程用途或安全性的授权依据**；证据不足时先问用户，不按推断动手。

---

## 一、定位（本技能卖什么）

**一句话**：AI agent 工作机的 macOS 内存卫生方法论技能——卖判据、边界设计与可配置阈值，不卖"清理工具"。

- **赛道**：agent-native。对话触发、**默认只读巡检**、只对白名单路径动手；与 GUI 类清理工具属不同赛道，本技能不与之对标，也不在文档里做功能比较。
- **三根支柱**：
  1. **白名单杀、绝不按大小杀**——边界带机制层理由，不是一张禁令清单；
  2. **杀前基线 → 杀后验证**——可证伪的验收，不靠"感觉快了"；
  3. **可配置阈值 ＋ 首运行诊断建议**——阈值随机器内存档位走，不写死。
- **明确不做**：Windows 版（判据体系不同，属重写不属改造）；进程"优化加速"类泛清理；对任何有用户状态的进程做主动终止。

## 二、适用场景与触发语

| 场景 | 典型触发语 | 动作类型 |
|---|---|---|
| 长跑任务后内存吃紧、彩虹圈 | 内存清理 / 彩虹圈 / 内存不够了 | 只读巡检 ＋（确认后）白名单清理 |
| 单次任务收尾 | 收尾清理 / 任务收尾 | 只读巡检 ＋（确认后）白名单清理 |
| 只想看不想动 | 内存巡检 / 看看内存 / swap 怎么样 | **纯只读**，不终止任何进程 |
| 回收站到期处理 | 回收站归档 / 清回收站 | 搬移 ＋ 报备 ＋（确认后）删超龄归档 |
| 阈值不合适 | 把 swap 警戒线调到 16384 / 改阈值 | 改 config ＋ 复跑报告验证 |

## 三、开跑前：设定技能目录

后续所有命令用 `$SKILL_DIR` 指技能安装目录（`SKILL.md` 所在目录）。由调用方一次性设定，技能本身不猜路径：

```bash
# 例：设为你自己的安装位置，任选其一
export SKILL_DIR="$HOME/.claude/skills/memory-cleanup"
# export SKILL_DIR="$HOME/.agents/skills/memory-cleanup"
```

`SKILL_DIR` 未设时下面的读取块会直接报错停下——**宁可停，不猜**：猜错目录会去读别人的 config，甚至往别人的目录里写模板。

---

## 四、第一步：读阈值（每轮都跑，不只首次）

### 4.1 四个参数（`<SKILL_DIR>/config.json`）

| 参数 | config 键 | 预设 | 可调范围 | 首运行建议逻辑 |
|---|---|---|---|---|
| swap 警戒线 | `swap_warn_mb` | `10240`（MB） | 4096~32768 | 按物理内存档位给建议（见表 4.2） |
| 微信类常驻进程上限 | `wechat_max_procs` | `20` | 10~50 | 微信常开建议 20；不常开建议 12 |
| 回收站归档天数（归档区停留 N 天） | `trash_aged_days` | `7` | 3~30 | 无建议，用默认即可 |
| agent 浏览器路径 | `agent_browser_path` | `""`（空＝跳过清理步） | 任意绝对路径 | 检测常见路径，命中则建议填入 |

> 参数是四个。"回收站归档天数"是**单键** `trash_aged_days`：值 N 决定归档区停留天数——文件搬进 `~/.Trash.aged/<日期>/` 后停 N 天、经用户确认才最终删除，**受控后悔期＝N 天**（默认 7）。技能不测量也不要求文件在回收站里先待满 N 天：每次运行把 `~/.Trash` 顶层项整体搬入归档区，日期文件夹名记录的是"搬进归档区那天"而非删除日。因此不能对外承诺 2N；若需两段各 N 天，须另加回收站侧天数判据（注意 `mtime` 是内容修改时间，不能当删除时间用，见 §九第 6 条）。

### 4.2 swap 警戒线档位建议

| 物理内存 | 建议 swap 警戒线 |
|---|---|
| 8GB | 6144 |
| 16GB | 10240 |
| 32GB | 16384 |
| 64GB | 24576 |

非上表档位取"不超过本机内存的最近一档"（≤8GB→6144，≤16GB→10240，≤32GB→16384，>32GB→24576）。128GB 及以上沿用 24576，可自行上调，上限 32768。

### 4.3 读取逻辑（含回退，直接整块跑）

```bash
# ==== memory-cleanup 阈值读取 v1.0.2 · 开始 ====
: "${SKILL_DIR:?请先把 SKILL_DIR 设为 memory-cleanup 技能安装目录}"
CONFIG="${MC_CONFIG:-$SKILL_DIR/config.json}"   # MC_CONFIG 仅供排查：临时指向另一份 config

mc_num_ok() { case "$1" in ''|*[!0-9]*) return 1;; esac; [ "$1" -ge "$2" ] && [ "$1" -le "$3" ]; }

mc_get() {  # 取单键原始值；有 jq 用 jq，无 jq 降级 sed
  if command -v jq >/dev/null 2>&1; then
    jq -r --arg k "$1" 'if (.[$k]|type)=="number" or (.[$k]|type)=="string" then (.[$k]|tostring) else empty end' "$CONFIG" 2>/dev/null | head -1
  else
    sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\{0,1\}\([^",}[:space:]]*\)"\{0,1\}.*/\1/p' "$CONFIG" 2>/dev/null | head -1
  fi
}

mc_load() {
  SWAP_WARN_MB=10240; WECHAT_MAX=20; AGED_DAYS=7; AGENT_PATH=""
  MC_SRC="预设值"; MC_NOTE=""
  [ -f "$CONFIG" ] || { MC_SRC="无 config"; return 0; }
  if command -v jq >/dev/null 2>&1; then
    jq -e . "$CONFIG" >/dev/null 2>&1 || { MC_SRC="config 损坏"; return 0; }
  else
    tr -d '[:space:]' <"$CONFIG" | grep -q '^{.*}$' || { MC_SRC="config 损坏"; return 0; }
  fi
  MC_SRC="config"
  MC_DEPRECATED=0
  if command -v jq >/dev/null 2>&1; then
    jq -e 'has("trash_keep_days")' "$CONFIG" >/dev/null 2>&1 && MC_DEPRECATED=1
  else
    grep -qE '(^|[{,])[[:space:]]*"trash_keep_days"[[:space:]]*:' "$CONFIG" 2>/dev/null && MC_DEPRECATED=1
  fi
  local v
  v=$(mc_get swap_warn_mb)
  if [ -n "$v" ]; then
    if mc_num_ok "$v" 4096 32768; then SWAP_WARN_MB=$v
    else MC_NOTE="${MC_NOTE}swap_warn_mb=$v 超出 4096~32768，回退预设；"; fi
  fi
  v=$(mc_get wechat_max_procs)
  if [ -n "$v" ]; then
    if mc_num_ok "$v" 10 50; then WECHAT_MAX=$v
    else MC_NOTE="${MC_NOTE}wechat_max_procs=$v 超出 10~50，回退预设；"; fi
  fi
  v=$(mc_get trash_aged_days)
  if [ -n "$v" ]; then
    if mc_num_ok "$v" 3 30; then AGED_DAYS=$v
    else MC_NOTE="${MC_NOTE}trash_aged_days=$v 超出 3~30，回退预设；"; fi
  fi
  v=$(mc_get agent_browser_path)
  case "$v" in ""|null) : ;; *) AGENT_PATH=$v ;; esac
}

mc_load

# 首次运行（先读后写）：config 不存在且技能目录可写 → 生成模板；绝不覆盖已有文件
if [ -z "${MC_CONFIG:-}" ] && [ "$MC_SRC" = "无 config" ] && [ -w "$SKILL_DIR" ]; then
  cat >"$CONFIG" <<'JSON'
{
  "schema_version": 1,
  "_comment": "memory-cleanup v1.0.2 配置模板。四个参数，键可缺省：缺省、类型错或越界即回退该键的预设值，不影响其余键，也不中断流程。改后下次运行生效。trash_aged_days 为归档区停留天数：文件搬进归档区后停 N 天、经确认再最终删除；回收站侧停留时长技能不测量、不计入受控后悔期。",
  "swap_warn_mb": 10240,
  "wechat_max_procs": 20,
  "trash_aged_days": 7,
  "agent_browser_path": ""
}
JSON
  [ -f "$CONFIG" ] && MC_GEN="1"
fi
# ==== memory-cleanup 阈值读取 v1.0.2 · 结束 ====
```

### 4.4 首运行报告（每次运行都带，不只首次）

```
本次按以下阈值执行：swap 警戒 10240MB ｜ 微信上限 20 ｜ 回收站 7+7 天 ｜ agent 路径未设（已跳过）。
可调项：swap 警戒线 4096~32768MB ｜ 微信上限 10~50 ｜ 回收站归档天数 3~30 天 ｜ agent 路径填绝对路径（留空即跳过）；改 config.json 对应键，下次运行生效。
内存档位：本机 16GB，swap 线建议 10240MB，与当前值一致。
```

三行缺一不可：**第一行＝本次实际生效的当前值**（不是预设值），**第二行＝可调项与调整方式一句话**，**第三行＝内存档位建议**。

第一行里的 `回收站 N+N 天` 是**两段结构**的写法，沿用既定格式、逐字不改。它**不是"两段各停 N 天"的承诺**：受控的只有归档区那一段 N 天，回收站侧停留时长技能不测量（见 §七 设计句）。档位与当前值不一致时第三行改为"本机 8GB，swap 线建议 6144MB（当前 10240MB），可下调"。

生成这段报告的代码（接上面整块之后跑）：

```bash
# ==== 首运行报告 · 开始 ====
MEM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
if   [ "$MEM_GB" -le 8 ];  then TIER_MB=6144
elif [ "$MEM_GB" -le 16 ]; then TIER_MB=10240
elif [ "$MEM_GB" -le 32 ]; then TIER_MB=16384
else TIER_MB=24576; fi

[ -n "$AGENT_PATH" ] && AGENT_TXT=" $AGENT_PATH" || AGENT_TXT="未设（已跳过）"
printf '本次按以下阈值执行：swap 警戒 %sMB ｜ 微信上限 %s ｜ 回收站 %s+%s 天 ｜ agent 路径%s。\n' \
  "$SWAP_WARN_MB" "$WECHAT_MAX" "$AGED_DAYS" "$AGED_DAYS" "$AGENT_TXT"
printf '可调项：swap 警戒线 4096~32768MB ｜ 微信上限 10~50 ｜ 回收站归档天数 3~30 天 ｜ agent 路径填绝对路径（留空即跳过）；改 %s 对应键，下次运行生效。\n' \
  "config.json"
if [ "$SWAP_WARN_MB" -ne "$TIER_MB" ]; then
  DIR="上调"; [ "$SWAP_WARN_MB" -gt "$TIER_MB" ] && DIR="下调"
  printf '内存档位：本机 %sGB，swap 线建议 %sMB（当前 %sMB），可%s。\n' "$MEM_GB" "$TIER_MB" "$SWAP_WARN_MB" "$DIR"
else
  printf '内存档位：本机 %sGB，swap 线建议 %sMB，与当前值一致。\n' "$MEM_GB" "$TIER_MB"
fi

case "$MC_SRC" in
  "无 config")   printf '提示：未找到 config.json，已按预设值继续运行%s。\n' "$( [ "${MC_GEN:-0}" = 1 ] && echo '，并已生成模板' )" ;;
  "config 损坏") printf '提示：config.json 解析失败（语法错或空文件），已整体回退预设值继续运行；修好后下次生效。\n' ;;
esac
[ -n "$MC_NOTE" ] && printf '提示：%s其余键按 config 执行。\n' "$MC_NOTE"
[ "${MC_DEPRECATED:-0}" = 1 ] && printf '提示：检测到已废弃键 trash_keep_days，已忽略——两段天数由 trash_aged_days 统一管理。\n'
# ==== 首运行报告 · 结束 ====
```

---

## 五、第二步：只读巡检（默认动作，不终止任何进程）

### 5.1 采数

```bash
# 内存空闲百分比（无 memory_pressure 时用 vm_stat 估算，见 reference/异常处理.md）
memory_pressure -Q 2>/dev/null | sed -n 's/.*free percentage: \([0-9]*\)%.*/\1/p'

# swap 已用（MB）：不用整数截断以外的处理，避免误读小数
sysctl -n vm.swapusage | awk '{for(i=1;i<=NF;i++) if($i=="used"){u=$(i+2); v=u+0; if(u ~ /G$/) v*=1024; printf "%d\n", v}}'

# agent 自动化浏览器实例数：按**与清理相同的路径**计数（口径同源；未设路径时退回默认串，仅作参考）
APAT="${AGENT_PATH:-agent-browser/browsers}"; pgrep -f "$APAT" 2>/dev/null | wc -l | tr -d ' '

# 微信类进程数（含 Helper/GPU/crashpad 子进程；两产品分列后相加）
P="WeChat.app";    W1=$(pgrep -f "/Applications/$P/" 2>/dev/null | wc -l | tr -d ' ')
Q="企业微信.app";  W2=$(pgrep -f "/Applications/$Q/" 2>/dev/null | wc -l | tr -d ' ')
WX=$(( W1 + W2 ))
```

### 5.2 判据与结论口径

| 指标 | 怎么判 | 结论口径 |
|---|---|---|
| 内存空闲 % | **不设固定线**。读数受系统缓存影响，同机相邻两分钟可差几个点，跨机更不可比；只用它做**前后对比**与趋势观察 | 取两次（基线／收尾）差值说话 |
| swap 已用 | ≥ `swap_warn_mb` 即超线；超线意味着内存压力已经穿透到磁盘，属"该动手"的机制信号 | 超线／未超线，给建议 |
| agent 实例数 | > 0 且用户确认当前没有在跑的任务 → 可进入白名单清理；用户在跑任务 → 只报告不动手 | 有残留／无残留 |
| 微信类进程数 | > `wechat_max_procs` → 建议用户退出重开微信（**只建议，不动手**） | 正常／偏高 |

> 计数口径的坑（`pgrep` 无 `-c`、`-f` 会命中执行者自身、crashpad 子进程算不算）见 `reference/异常处理.md` 第三节。口径不统一时，数字之间没法比较。

---

## 六、第三步：白名单清理（两个前置条件同时满足才动手）

**前置条件（缺一不动手）**：

1. `agent_browser_path` 非空（预设为空＝跳过本步）；
2. 用户明确确认"当前没有正在跑的上传/浏览任务"。

### 6.1 未设路径时：先检测，再问，不自动填

```bash
for d in "$HOME/.agent-browser/browsers" "$HOME/Library/Caches/ms-playwright" "$HOME/.cache/puppeteer"; do
  [ -d "$d" ] && printf '检测到浏览器目录：%s\n' "$d"
done
```

命中则给用户一句话建议（"检测到 …，建议填入 config 的 agent_browser_path"）。**未经用户确认不写入文件**；用户当场说"这次就用它"，则本次以该路径运行，不改 config。

### 6.2 基线 → 清理 → 验证（闭环三步，缺一步则本轮结论不成立）

```bash
# 先判空：空模式串不是"什么都没匹配"，而是"根本没查"（见下方注）
if [ -z "$AGENT_PATH" ]; then
  echo "agent 路径未设：按预设跳过清理步，本轮只出巡检与建议"
else
  TARGET="$AGENT_PATH"

  # 基线
  B_CNT=$(pgrep -f "$TARGET" 2>/dev/null | wc -l | tr -d ' ')
  B_FREE=$(memory_pressure -Q 2>/dev/null | sed -n 's/.*free percentage: \([0-9]*\)%.*/\1/p')
  B_SWAP=$(sysctl -n vm.swapusage | awk '{for(i=1;i<=NF;i++) if($i=="used"){u=$(i+2); v=u+0; if(u ~ /G$/) v*=1024; printf "%d\n", v}}')
  printf '基线：实例 %s ｜ 空闲 %s%% ｜ swap 已用 %sMB\n' "$B_CNT" "$B_FREE" "$B_SWAP"

  # 清理：只按 TARGET 精确匹配（与计数同一口径），不做任何模糊匹配
  pkill -f "$TARGET" && echo "已终止 agent 浏览器实例（目标：$TARGET）"
  sleep 5
  R_CNT=$(pgrep -f "$TARGET" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$R_CNT" -gt 0 ]; then pkill -9 -f "$TARGET"; sleep 3; fi   # 5 秒后仍有残留才补一次 -9

  # 验证
  sleep 2
  E_CNT=$(pgrep -f "$TARGET" 2>/dev/null | wc -l | tr -d ' ')
  E_FREE=$(memory_pressure -Q 2>/dev/null | sed -n 's/.*free percentage: \([0-9]*\)%.*/\1/p')
  E_SWAP=$(sysctl -n vm.swapusage | awk '{for(i=1;i<=NF;i++) if($i=="used"){u=$(i+2); v=u+0; if(u ~ /G$/) v*=1024; printf "%d\n", v}}')
  printf '收尾：实例 %s ｜ 空闲 %s%% ｜ swap 已用 %sMB\n' "$E_CNT" "$E_FREE" "$E_SWAP"
fi
```

> 那个 `if [ -z "$AGENT_PATH" ]` 要先判空，因为**空模式串的后果是"假阴性"而不是"没动作"**：
> macOS 上 `pgrep -f ""` 直接报 `Cannot compile regular expression … (empty (sub)expression)`、退出码 2，**一条都不输出**；
> 于是 `wc -l` 得到 `0`，看起来像"没有实例"，实际是"根本没查"。若清理后的验证用了空模式串，验收会永远显示 0，且看不出错在哪。
> （另一些平台的 `pgrep` 实现里空正则匹配全部进程，行为相反。**两种平台的坏法不同，结论相同：先判空**。）
> 凡是把变量交给 `pkill -f` / `pgrep -f` 的地方，先判空、先确认模式串非空，再执行。

**汇报口径**：先结论后数字，用"实例 N→0、空闲 x%→y%、swap a→b MB"三组前后对比说话。**swap 通常不降**——这是正常现象，不是清理失败（理由见 `FAQ.md` Q2）。

---

## 七、第四步：回收站两段式（天数取 config 单键值）

设计：`~/.Trash` 顶层项（除 `.DS_Store`）每次运行整体搬入归档区 `~/.Trash.aged/<当天日期>/`（可回退）；归档区停留 `trash_aged_days` 天（默认 7）后，列清单报体积、经用户确认才最终删除。**受控后悔期＝N 天（默认 7）**：技能不测量回收站侧停留时长，"回收站再停 N 天"没有被执行，不写成 2N。
**绝不直接清空 `~/.Trash`**：清空不可逆，后悔期归零。

### 7.1 归档搬运（进入日期文件夹）

```bash
AGED="${AGED:-$HOME/.Trash.aged}"; TODAY=$(date +%F); mkdir -p "$AGED/$TODAY"
find "$HOME/.Trash" -maxdepth 1 -mindepth 1 ! -name ".DS_Store" -print0 | \
  while IFS= read -r -d '' f; do mv "$f" "$AGED/$TODAY/" 2>/dev/null || printf '搬移失败（保留原位）：%s\n' "$f"; done
```

### 7.2 列出超龄归档（只列出，不删）

```bash
AGED="${AGED:-$HOME/.Trash.aged}"; AGED_DAYS="${AGED_DAYS:-7}"
find "$AGED" -maxdepth 1 -mindepth 1 -type d -name "????-??-??" -mtime +"$AGED_DAYS" -print
```

### 7.3 删前报备 → 用户确认 → 逐个删

对 7.2 列出的每一项，先报**路径与体积**（`du -sh`），用户确认后再逐个 `rm -rf`。**只删本目录下、只删日期命名文件夹**；用户未确认则本轮只报不删。

### 7.4 边界

只碰 `~/.Trash` 与 `~/.Trash.aged`；不碰其他卷的 `.Trashes`；`.DS_Store` 不动；`mv` 或删除失败如实报错，不重试、不硬删。

---

## 八、第五步：报告与建议

报告固定五段（有则写、无则写"无"，不留空白段）：

1. 阈值行三句（见 4.4）；
2. 巡检表（内存空闲／swap／agent 实例／微信类进程，各带判据与结论）；
3. 本轮动作（清理了几个实例、归档搬了几项、删了几个超龄文件夹、有无失败项）；
4. 前后对比（实例数、空闲 %、swap MB）；
5. 建议（仅在有依据时给，最多三条）：
   - swap 超线且居高不下 → 建议择机重启（唯一能清零 swap 的办法）；
   - 微信类进程 > `wechat_max_procs` → 建议退出重开微信；
   - 同一会话并行跑的自动化任务越多，Chromium 实例按任务数线性叠加；**经验上 5 个以上就容易把 16GB 机型推到 swap 上涨**——这是经验值，不是判据，按内存档位收着跑即可。

**建议只对"用户可自己动手"的动作给**；本技能不替用户做需要他做决定的事。

---

## 九、安全边界（摘要）

每条禁令后附机制层理由；完整推导见 `reference/安全边界.md`。

1. **只终止路径含 agent 浏览器缓存目录的 Chrome 进程。**
   理由：自动化实例以独立 `--user-data-dir` 启动，该路径写在进程命令行里，是它唯一稳定的标识；用户手动开的 Chrome 不共享这个 user-data-dir，因此路径匹配在机制上排除了误伤，而不是靠"看起来像"。
2. **绝不按内存占用大小挑进程杀。**
   理由：RSS 大与"可安全终止"没有因果关系。微信、办公文档编辑器、用户浏览器占内存多，恰因为其中驻留用户状态（未发送的消息、未保存的文档、登录会话），进程一退状态即丢且不可恢复。大小是资源指标，不是状态归属指标；拿大小当判据，会优先杀掉"占用大的有状态进程"，方向正好反了。
3. **对微信、企业微信、办公套件、用户浏览器，只做只读计数，异常时提示用户、由用户点名。**
   理由同上：这些进程的状态价值高于其内存价值，本技能没有判断"用户此刻是否还需要它"的信息渠道。
4. **执行清理前必须确认没有在跑的任务（先问，不确认不动手）。**
   理由：白名单只证明"这个进程属于自动化浏览器"，不证明"此刻没有任务在用"。终止正在上传/浏览的实例会中断任务并可能留下半提交状态。**归属证据 ≠ 任务状态证据**，两者不能互相顶替。
5. **绝不直接清空 `~/.Trash`；最终删除必须走两段式、必须用户确认。**
   理由：清空不可逆；两段式把"删除"拆成"可回退的搬移"＋"有日期的最终删"，中间这段就是后悔期。
6. **归档区的超龄判据用日期文件夹名，不用文件 mtime。**
   理由：mtime 是内容最后修改时间，与"什么时候被删"无关。一个 2019 年改过、今天刚删的文件，mtime 还是 2019 年，按 mtime 判会当场删掉它，后悔期归零。日期文件夹名记录的是"搬进来的那一天"，是唯一带删除时间归属的判据。
7. **失败如实报，不重试、不硬删。**
   理由：失败码指向不同原因（权限、被占用、跨卷），重试把可诊断的错误变成一堆不可诊断的噪音；`sudo` 硬删则绕过权限边界，让误删范围重新变得不可控。

## 十、异常与回退（速查，展开见 `reference/异常处理.md`）

| 情形 | 处置 |
|---|---|
| config 不存在 | 全用预设值；技能目录可写则生成模板，不可写则只打印模板 |
| config 语法错／空文件 | 整体回退预设值，报告里提示一句，流程继续 |
| 某键缺失／类型错／越界 | **只回退该键**，其余键照 config 执行，提示可调范围 |
| `jq` 不存在 | 降级 `sed` 解析（只认平铺的键值，不支持嵌套与数组） |
| `pgrep` 无 `-c` | 用 `pgrep -f 模式 \| wc -l`；BSD `pgrep` 不接受 `-c` |
| `memory_pressure` 不可用 | 用 `vm_stat` 估算**可用内存占比**（口径不同于 `memory_pressure`，报告须标"估算值"，只与同口径读数比） |
| 技能目录只读 | 不写 config，仅用预设值 + 打印模板，不报错中止 |

## 十一、目录与文件

下图为**技能包正文六项**的结构；交付目录 `memory-cleanup-release/` 另含仓库级 `LICENSE` 与 `上架说明.md`（发布时留仓库根，不进技能包，见 `上架说明.md` §一）。

```
memory-cleanup-release/
├── SKILL.md                 本文件（判据与流程主入口）
├── config.json              四参数模板
├── FAQ.md                   四问 ＋ 双通道复用模式
├── CHANGELOG.md             版本与脱敏记录
├── reference/
│   ├── 异常处理.md           损坏回退、jq 降级、pgrep 口径
│   └── 安全边界.md           每条禁令的机制层理由
└── examples/                五场景：触发语＋执行要点＋验收对比
```
