# Changelog: 提案质量提示词

> **代码基线**: `50c848b09545230b4f0cc2d87556ca294829841f`（改动尚未提交，仍在工作区）
> 日期：2026-11-18
> 规格：`docs/superpowers/specs/2026-11-18-proposal-quality-design.md`
> 施工单：`docs/superpowers/plans/2026-11-18-proposal-quality-plan.md`
> 缘起：`docs/superpowers/reports/2026-11-18-proposal-quality-2day-audit.md`，以及同目录后来改成审阅的 `优化建议.txt`

## TL;DR

快环实际看到的提示词里，有三份文本在用另一套品种名单、一个不存在的协变量族，以及一组已经不用的方向准确率数字。这一轮只改这三份文本里的六处句子，并加一个只读源文件的测试。收割、目标、门禁、`search_policy` 都没有动。监督环没有重启。

## 问题

2026-11-17 到 2026-11-18 的 15 个快环 run 里，假设文件 879 份。生成集中在乙二醇、螺纹钢、鸡蛋，占 45.2%。提示词另写了一份 8 个品种的短名单 `{m, ss, sr, cj, jd, lh, eg, rb}`，和目标文件里的 24 个品种并列。示例提案 `p_oi` 把 `oi` 写成族 `positioning`，活跃池里的族是 `inventory`。Diversity 段和代次模板还点名了池里没有活跃行的 `macro_sentiment`。Domain guidance 仍写着 `n>=350, n_eff>=50, DirAcc>=0.52`，和同一份提示里已经写明的自适应 `effective_min` 冲突。

审计报告里另有几项主张，核对磁盘后不成立，所以没有按那些主张改代码。69% 的重复 `proposal_id` 不是同一段机制反复粘贴。`eg_oi` 不是幻觉指标。`cj`、`bu` 仍在 `target_symbols` 里。裁决行没有 `dir_ok` 字段。预筛 196 次超时不会放行池外协变量。

## 根因

收割层已经有品种白名单、活跃池白名单和 `dedup`。快环同伴拿到的提示词没有读到 `target_symbols`。已核对的渲染 `gen0_peer0_prompt.md` 和 `gen0_peer1_prompt.md` 里，这个词出现 0 次。运行配置的工作目录是 `task_project`，相对路径 `scripts/praxist_goal.yaml` 对不上仓库根。

短名单在渲染结果里出现两次：一次来自 `task_FM/prompt_base.jinja2` 第 5 条，一次来自 `task_FM/roles/peer_generalist/skill.md` 的 Proposal scope。两个同行加载的都是这一份技能文件，渲染哈希相同。`macro_sentiment` 也有两处：基底的 Diversity 段，以及 `task_FM/prompt_generation.jinja2` 的 anti_mainline 句。只改其中一份，快环仍会看到旧句子。

## 修复方案

提示词里新写的句子用英文。已经写在文件里的中文示例不翻译。

`task_FM/prompt_base.jinja2` 改四处：

1. 品种规则改为只使用 `/home/abug/timesfm/scripts/praxist_goal.yaml` 里的 `target_symbols`。文件外品种在收割时以 `symbol_not_allowed` 拒绝。不把 24 个品种名写进提示词。
2. 示例 `p_oi` 的 `covariate_family` 改为 `inventory`。
3. 同一代写了两份及以上提案时，至少一份使用菜单里不同的 ACTIVE 族。单份提案只要协变量是菜单里的 ACTIVE 行就成立。不得发明菜单没有的族。
4. 提案只在慢环现有 aligned gate 通过时成立。这句提示词不另加方向准确率门槛。

`task_FM/roles/peer_generalist/skill.md` 改两处：品种行指向同一个绝对路径；`kill_condition` 改为 `aligned dir_acc below that symbol's adaptive effective_min, or endpoint_mape does not improve (falsifiable)`。

`task_FM/prompt_generation.jinja2` 改一处：anti_mainline 不再列出六族名单，改为覆盖菜单里至少有一行 ACTIVE 的被忽视族，且不得发明菜单没有的族。

## 关键设计决策

- 用绝对路径加收割拒绝码，是因为目标名单没有被渲染进提示词，相对路径又会找错目录。文件没读到时，不要退回短名单。
- `cohort_size` 的 `default(4)` 不改。已核对的那次渲染传入的是 2，这个默认值没有露给快环。`cohort_size` 是同行个数，不是每人写几份提案。多样性按「这一代写了几份提案」来写，不按同行个数来写。
- 技能文件的放弃条件用英文，不把基底第 34 行已有的「低于该品种」抄过去。那句旧示例留在基底里。
- `task.yaml` 的 `research_direction` 里还有短名单和 `DirAcc>=0.52`。这次渲染里没有这段任务描述，所以这一轮不改 `task.yaml`。
- 渲染结果里另一处 `n>=350` 来自 include，不在基底源文件里。include 不改。基底第 7 行的 `n=350-600` 是另一个字符串，留下。
- 代次模板里的 `adaptive gate (0.50-0.52)` 是在描述现有自适应区间，留下。

## 测试覆盖

新增 `tests/test_prompt_symbol_authority_20261118.py`。它只读上述三个源文件，不启动监督环，不读裁决文件。三个测试按文本分开：基底、技能、代次模板。每一段都是先断言失败，再改对应句子，再断言通过。

基底测试钉住禁止串和必须出现的句子，包括多样性的正向句和 aligned gate 的正向句。同时钉住不能被这次改词碰掉的句子：`cohort_size | default(4)`、`n=350-600`、`p_oi.json`、`failure_delta`、`ACTIVE 品种优先`、`success_delta` 拒收原句、第 34 行的「低于该品种 adaptive effective_min」、`positioning/calendar/structure`。

技能测试禁止短名单、`2-star`、`dir_acc<0.52` 和「低于该品种」，并要求英文锚点 `below that symbol's adaptive effective_min`。

代次测试禁止 `macro_sentiment`，要求 `Do not invent a family the menu does not list`，并要求 `adaptive gate (0.50-0.52)` 仍在。

另外重跑了四条已经在读 `prompt_base.jinja2` 的静态测试：`test_prompt_base_selection_discipline`、`test_templates_render_directive_context`、`test_templates_render_without_agenda`、`test_prompt_teaches_search_fields_and_keeps_success_delta`。

## 验收结果

解释器是 `/home/abug/timesfm/.venv/bin/python`。上面五条节点一起是 7 passed，退出码 0。没有跑全量 pytest。

工作区里这次改动的路径是：

- `task_FM/prompt_base.jinja2`
- `task_FM/roles/peer_generalist/skill.md`
- `task_FM/prompt_generation.jinja2`
- `tests/test_prompt_symbol_authority_20261118.py`

`search_policy` 仍是 `shadow`。实施前后 `pgrep` 都没有 `praxist_supervisor.py`。没有杀进程，也没有重启。提示词要等下一次由宿主明确要求启动的快环才会进入新的渲染。

## 明确没做

- 不把 `cj` 或 `bu` 从 `target_symbols` 删掉，也不写成 `DEAD`。
- 不拦截 `oi`、`ccl`、`nvi`、`calendar_cyclical`，不另建协变量注册表。
- 不把 `proposal_id` 做成一次性主键。已有失败时，不足 20 字的 `failure_delta` 仍按原规则拒绝。
- 不用审计报告那张百分比表做配额、多臂老虎机或品种熔断。
- 不加本地预筛模型，也不在这一轮恢复预筛服务。
- 不改 `scripts/sup_harvest.py`、`scripts/praxist_goal.yaml`、`task_FM/config/covariate_pool.json`、评估门禁、`task.yaml`。
- 不清理实验目录里的历史提案。
- 不引入分年切片、跨品种迁移、留出集或模拟盘。
- 不查那 608 份重复 `proposal_id` 在收割时的去向，也不查库存类和日历类为什么没进 11 月 17 日、18 日的完成队列。这两件要做时另写规格。

## 提交

没有提交，没有推送。`HEAD` 仍是 `50c848b`。上面四个路径以及本 changelog、规格、施工单都还在工作区，没有 `git add`。活仓里原先已脏的运行数据保持原样。
