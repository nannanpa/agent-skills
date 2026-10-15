# SkillHub 发布脚本测试记录（testing log）

> 本文件记录 `skillhub_publish.py` 发布守卫的可重跑测试配方。
> **证据独立性来自"可被第三方重跑"，不来自日志本身**——所以这里只放配方（改哪处 → 跑哪条 → 看哪个数字），路径一律用占位符。
> 原始输出（含本机路径）留在发布机本地 `<workspace>/backups/injection-tests/`，不入库。
> 文件头标注：本文为 **实时** 归档的配方化重写（原始输出见本地归档）。

## 前置说明

发布流程：从 `agent-skills/<name>/` 组装 dist（注入 SkillHub 必填 frontmatter、LICENSE 改名 LICENSE.txt）→ 调官方 CLI。三层守卫：

| 层 | 守卫对象 | 行为 |
|---|---|---|
| ① 跳过已存在键 | 注入不产生冲突行 | 静默跳过 |
| ② 输出键唯一性断言 | 源文件自身重复键 | 重复即 FAIL，禁止发布 |
| ③ 版本漂移断言 | `skills.json` ↔ SKILL.md 版本不一致且未声明 | FAIL 并打印两值与二选一 |

版本纪律：**真源 = `skills.json`**。漂移时二选一：① 同号——改 SKILL.md 的 version；② 有意分版——发布时显式 `--version <SkillHub侧版本>`，并在技能 README 发布记录中说明。

## 夹具隔离（2026-10-15 立，先于一切配方）

**涉及改写 SKILL.md 的测试（配方 2/3），必须在一次性仓库副本上跑，禁止在正式仓库工作区就地改写。**

原因：就地改写依赖"复原总会执行"，中断（Ctrl-C / 崩溃 / 超时）会让公开仓库里的文件停在改写值，未提交、无人发现。2026-10-15 实测产生过 3 个临时文件残留（temp-file + 原子改名写入法的副产物）。

标准流程：

```
1. TESTROOT=$(mktemp -d)
2. cp -a <workspace>/agent-skills "$TESTROOT/"          # 含 .git，被测对象完整隔离
3. cp -a <workspace>/skillhub-publish "$TESTROOT/"      # 脚本 REPO 按相对路径自动指向副本
4. cd "$TESTROOT/skillhub-publish" 后执行各配方——所有改写只落在副本
5. 结束: rm -rf "$TESTROOT"
6. 正式仓库工作区应保持干净（git status --porcelain -uall 无新增）
```

被审对象不能被测试夹具改写——与"被审对象不能审自己"同一原理。

## 配方 1 · 正常发布预检（同号技能）

```
1. 确认 <repo>/<skill>/SKILL.md 的 version 与 <publish>/skills.json 一致
2. 跑: python3 skillhub_publish.py <skill> --dry-run
3. 看: "✓ Dry-run passed: <skill>@<version>" 且 "✓ 预检通过"
4. 核: grep -c '^version:' dist/<skill>/SKILL.md  → 应为 1
```

## 配方 2 · 漂移守卫（无声明 → FAIL）【先按"夹具隔离"建副本，在副本上跑】

```
1. 临时把 <repo>/<skill>/SKILL.md 的 version 改为与 skills.json 不同的值（如 9.9.9）
2. 跑: python3 skillhub_publish.py <skill> --dry-run
3. 看: 应退出并打印 "版本漂移 —— SKILL.md=9.9.9 ≠ skills.json=<真值>" 与二选一提示
4. 复原 SKILL.md（还原 version 行）
```

## 配方 3 · 有意分版（显式 --version → 放行 + WARN）【同上，副本上跑】

```
1. 同配方 2 步骤 1（制造漂移），或技能本身存在声明过的双通道分版
2. 跑: python3 skillhub_publish.py <skill> --version <SkillHub侧版本> --dry-run
3. 看: "⚠ 检测到有意分版（已声明）" + "✓ 预检通过"
4. 注意: dist frontmatter 的 version 行 = SKILL.md 原值（跳过注入）；SkillHub 侧版本号由 CLI --version 透传覆盖，不经 frontmatter
```

## 实测记录（2026-10-15）

| 场景 | 技能 | 期望 | 结果 |
|---|---|---|---|
| 同号放行 | grill-me-gongwen（1.0.1==1.0.1） | 预检通过 | ✅ |
| 漂移无声明 | grill-me-gongwen（9.9.9 vs 1.0.1） | FAIL + 两值 + 二选一 | ✅ |
| 漂移显式声明 | grill-me-gongwen（9.9.9 + `--version 1.1.3`） | WARN + 放行 | ✅ |
| 有意分版无声明 | hongloumeng（1.1.1 vs 1.1.3） | FAIL（此前该分版仅存在于 README 叙述，脚本不感知） | ✅ |
| 有意分版显式声明 | hongloumeng + `--version 1.1.3` | WARN + 放行；dist frontmatter 1.1.1、CLI 1.1.3 | ✅ |

## 关联

- 背景与失效形态分析：`grill-me-gongwen/SKILL.md` 的发布链审计（2026-10-15）
- 修复原则：**有意分叉与失修分叉在 diff 里长得一样，只能靠显式声明区分**——与上游改造台账（`UPSTREAM-MERGE.md`）的"本地优先 / 公开版泛化"条款同一原则
