# docx-template-fill

【仅限 WorkBuddy】通过本地编辑器（内置 skill tencent-local-office-edit 的 edsdk）填报/修改 docx 模板的安全工作流。详见 SKILL.md。

## 发布记录

- **2026-10-18 v1.0.6**：Windows 实测回填（Windows 10 19045 + PS 5.1 + Python 3.13，7 步流程/终验脚本全跑通）——①诚实边界升级"Windows 已实测"②三坑表加平台注记（坑一 macOS 侧、坑二小文件侥幸、坑三 Windows 复现且被分号吞错放大）③Windows 对照表升级为已实测 + 两条硬警告（PS5.1 `&&` 整行 parse error 禁用；move 后必须验证退出状态）④异常诊断表补 3 行 Windows 项⑤参数名提示（doc_find_and_replace 用 old_text/new_text）
- **2026-10-18 v1.0.5**：按首评测报告（4.5 优秀）补短板——①终验脚本化：新增 scripts/final_check.py（多检查项 CLI，替代内联片段）②新增「异常分级诊断」节（8 类现象→根因→处置对照）③新增「Windows 环境对照」节（命令替代表 + 未实测诚实声明）④新增「首次使用：最小路径」⑤FAQ 6→11 问（补跨命令报错/mv 盖错/Windows/回显滞后）；针对评测"只是操作手册"判词，终验脚本化为可运行工具
- **2026-10-17 v1.0.4（SkillHub 独占）**：发布记录表述精简
- **2026-10-17 v1.0.3（SkillHub 独占）**：新增「常见问题（FAQ）」节（连接失败/错填回退/锚点搜不到/占用/终验失败/不适用场景六问）与「两个典型场景」（部门填报方案 / 会签意见）
- **2026-10-16 v1.0.2（SkillHub 独占）**：补充 Skill 图标（金表单+红章，系列同配色）；同日三件打磨已入 main、随下一版发布——终验改 if+sys.exit、Windows 判 CDFV2 写法（certutil）、新增「适用环境与未验证声明」节
- **2026-10-16 v1.0.1（SkillHub 独占）**：撤 GitHub 分发后页脚改为 SkillHub 安装指引；中文名定「DOCX模板填报」
- **2026-10-16 v1.0.0 首发（SkillHub 独占）**：发布前完成四项修订——平台归属与前置条件声明、F 定义收紧为另存填报版、终验代码非零退出码、触发词收窄
