# 提案质量规格

代码基线：`/home/abug/timesfm` 的 `master`，`50c848b09545230b4f0cc2d87556ca294829841f`。
数据窗口：审计附录 A 的 15 个 run，从 `run_2026-11-17_01-55-15_primary_task_FM` 到 `run_2026-11-18_12-41-11_primary_task_FM`。
方向准确率快照读自当时的 `task_FM/config/aligned_verdicts.jsonl`，只计 `status=ok` 且 `protocol_fingerprint` 以 `f02b2a43` 开头的行。
本文件不授权重启监督环，也不改目标、门禁公式、协议指纹或 `search_policy`。

## 决定

这一轮只改快环提示词里互相矛盾的句子，并加一个只读这些文本的测试。2026-11-18 的审阅不推翻下面的账本和拒绝项。渲染核对表明，同一份快环提示词还会带上角色技能和代次模板，所以同样的句子要在那两个文件里一起改掉。同日后续审阅只加了两件事：技能文件的 kill 示例用英文，并核对第二个同行的角色文件。渲染核对写明没有第三份文件。

快环已经会读到协变量菜单和已知裁决。收割层已经用活跃池白名单、品种白名单和 `dedup` 挡住不能跑的提案。新建协变量注册表、`proposal_id` 硬去重、品种黑名单、配额调度和熔断，这一轮都不做。原因写在下面的核实账本里。

## 核实账本

下表核对的是 `docs/superpowers/reports/2026-11-18-proposal-quality-2day-audit.md`，以及写这份规格时那一版优化建议里的主张。`docs/superpowers/reports/优化建议.txt` 后来改成了对本规格的审阅，不再保存那些主张。下表的「成立」只表示当时磁盘上的计数成立，不表示由此推出的改法成立。

| 主张 | 结论 | 依据 |
|---|---|---|
| 15 个 run 的提案计数，以及 `jd_calendar_cyclical` 出现 31 次这类重复榜 | 成立 | 15 个 run 里假设文件 879 份（另有 15 份不是 `fm.hypothesis_proposal.v1`）。`proposal_id` 271 个。多出来的 608 份占 879 的 69.2%。重复榜前几名与报告一致。报告写 272 个唯一 id，差 1，不影响决定。 |
| 这 69% 是同一段文字反复粘贴 | 不成立 | 134 个重复 id 的机制文本哈希都不止一个。相同机制 0 个。这是同一品种加同一协变量又写了一遍不同机制。 |
| 快环在造慢环跑不了的库存类、日历类假说，执行侧这两类为 0，所以接近一半生成算力从一开始无效 | 生成占比成立，原因不成立 | 879 份里按池中的族：库存 269、日历 150，合计 47.7%。`aligned_pending.done.jsonl` 里 `enqueued_at` 落在 11 月 17 日或 18 日的有 63 行，来源是 peer 40、confirmation 14、manual 7、data_fix 2。协变量只有 `vor` 19、`hourly_slope` 16、`basis_momentum` 15、`vwap_deviation` 7、`rsi6` 2、`stddev` 2、`sar_dist` 2，没有库存类和日历类。报告附录 C 是 62 行、`basis_momentum` 14，差 1 行。这 63 行的 `src_run` 不一定是这 15 个 run。池里 31 个协变量全部是 `active`，包含 `oi`、`ccl`、`nvi`、`calendar_cyclical`。当前协议已有落盘裁决：日历类 14 条、库存类 19 条。慢环跑得了这两类。这个窗口的完成队列没排到它们，不是缺实现。 |
| `eg_oi` 是未知幻觉指标，应拦截 | 不成立 | `eg` 是品种，`oi` 是活跃池里的库存类协变量。窗口内 15 份。 |
| 非法协变量很多 | 不成立 | 879 份里协变量不在活跃池的只有 1 份，而且协变量名是空的。 |
| `cj`、`bu` 已从配置剔除，再出现就是残留 | 不成立 | `scripts/praxist_goal.yaml` 的 `target_symbols` 仍有 24 个品种，包含 `cj` 和 `bu`。`task_FM/config/symbol_status.json` 的 `symbols` 是空的，没有 `DEAD` 或 `HOLD`。窗口内 `cj` 21 份、`bu` 39 份，收获层的 `symbol_not_allowed` 不会拒它们。当前协议 `cj` 是 18 条里 18 条 `gate_pass`，平均 `dir_acc` 0.532。 |
| 历史 `dir_ok=0%` 说明乙二醇、螺纹钢、鸡蛋没有方向准确率，应熔断 | 数字不是方向准确率 | 裁决行没有 `dir_ok` 字段。当前协议 `eg` 5 条，平均 `dir_acc` 0.414，`gate_pass` 0。`rb` 3 条，0.429，0 条过门。`jd` 5 条，0.460，0 条过门。`cf` 5 条，0.479，0 条过门。准确率在 0.41 到 0.48，不是 0。报告里 `ss` 86%、`jm` 75%、`ta` 100%、`sr` 62% 也和这批裁决对不上：`ss` 过门 6/10，`jm` 5/10，`ta` 7/10，`sr` 1/5。这张表不能当配额或熔断的输入。 |
| 生成集中在 `eg`、`rb`、`jd` | 成立 | 155+138+104=397，占 879 的 45.2%。提示词第 5 条另写了一份 8 个品种的短名单 `{m, ss, sr, cj, jd, lh, eg, rb}`，和目标文件的 24 个品种并列。短名单盖住了这三个高产品种，也盖住了 `cj`。`bu` 不在短名单里仍有 39 份，所以短名单不是唯一来源，但它是第二份品种权威。 |
| 预筛 196 次全部降级，备注是超时 | 成立 | 196 个 `.prescreen.json` 的 `status` 都是 `degraded`，`note` 都是 `TypeSafe API 超时`。报告另一处写 163 次，以 196 为准。本规格没有探测预筛服务进程，不把「超时」写成「已确认宕机」。 |
| 预筛一停，白名单和去重就一起失效 | 不成立 | `scripts/sup_harvest.py` 在预筛调分之前已经拒绝 `symbol_not_allowed`、`cov_not_in_active_pool`、`dedup`、`dedup_evaluated`。`_apply_prescreen_score` 只在 `status=success` 时改分。超时不会放行池外协变量。 |
| Session 成功率 60.3%，约 40% 会话失败，所以要上 JSON Schema | 未复现 | 有 `run_summary.json` 的 14 个审计 run，`status` 都是 `succeeded`，`exit_condition` 都是 `max_generations`。`run_2026-11-17_18-07-01_primary_task_FM` 没有这份摘要。找不到与 463 个 session、60.3% 对应的计数。不设 85% 的会话成功率验收。 |
| 报告自身 13 与 15 个 run、759 与 879 份提案两套口径 | 成立 | 附录 A 是 15 个 run，逐 run 提案数与磁盘一致。879 是全窗假设文件数。较早的占比用的是另一截样本。 |

## 渲染核对

核对对象是 `task_FM/experiments/run_2026-11-18_12-41-11_primary_task_FM/gen_0/gen0_peer0_prompt.md`，也就是快环实际拿到的提示词。

- `target_symbols` 出现 0 次。目标品种没有被渲染进提示词。只写「去读 `scripts/praxist_goal.yaml`」不够：运行配置里的工作目录是 `task_project`，相对路径对不上仓库根。同一份提示词里的结果路径用的是 `/home/abug/timesfm/...` 这种绝对路径。
- 渲染结果是 `cohort 2 peers`。`task.yaml` 的 `generation_policy.cohort_size` 是 2。`prompt_base.jinja2` 里 `default(4)` 在这次渲染中没有生效。`cohort_size` 是同行个数，不是每人写几份提案。同一份提示词要求每位同行写 2 到 4 份提案。
- 八品种短名单在渲染结果里出现两次。一次来自 `task_FM/prompt_base.jinja2` 第 5 条，一次来自 `task_FM/roles/peer_generalist/skill.md` 的 Proposal scope。只改前一个文件，快环仍会看到短名单。
- `macro_sentiment` 也有两处。一处是 `prompt_base.jinja2` 的 Diversity 段，一处是 `task_FM/prompt_generation.jinja2` 的 anti_mainline 句，那句把 `macro_sentiment` 列进应覆盖的族。
- `task.yaml` 的 `research_direction` 里还有同一份短名单和 `DirAcc>=0.52`。这次渲染里 `2-star` 只出现两次，两处都已对上上面的文件，所以这段任务描述没有进入该份提示词。这一轮不改 `task.yaml`。
- 同一次运行的 `gen0_peer1_prompt.md` 也是角色 `task_role:peer_generalist`。两份 layout 里 `task_peer_role_contract` 的 `source_path` 都是 `/home/abug/timesfm/task_FM/roles/peer_generalist/skill.md`，渲染哈希都是 `sha256:b62e6eb60e398803686a34d75ea86b85ac275362c57c957594b79ae9c69179e5`。`task_FM/roles/` 下面只有 `peer_generalist` 这一个角色。peer1 里的短名单仍是上面那两处，没有第三份角色文件要加进来。

## 要改的提示

这一轮新写的句子用英文。文件里已经有的中文示例不翻译，包括 `prompt_base.jinja2` 第 34 行。`failure_delta`、`success_delta`、菜单 include、已知裁决 include，以及 `cohort_size` 的 `default(4)`，都不改。

`prompt_base.jinja2` 改四处：

1. 第 5 条品种规则。删掉 `{m, ss, sr, cj, jd, lh, eg, rb}` 和 `2-star`。换成下面这句，使用绝对路径，因为目标名单目前没有被渲染进来，相对路径又会找错目录：`Symbols: only target_symbols in /home/abug/timesfm/scripts/praxist_goal.yaml. Do not use a shorter list. A symbol outside that file is rejected at harvest as symbol_not_allowed.` 手写短名单会把生成压到那 8 个品种上；绝对路径和收割拒绝码放在一起，是为了文件没读到时也不要退回短名单。
2. 示例提案 `p_oi` 的 `covariate_family` 从 `positioning` 改为 `inventory`。`oi` 在活跃池里的族就是 `inventory`。
3. Diversity 段。删掉六族名单和 `macro_sentiment`。换成：`When you write two or more proposals in this generation, at least one must use an ACTIVE covariate family from the menu below that differs from the family of your other proposal. A single proposal is valid when its covariate is an ACTIVE row in that menu. Do not invent a family the menu does not list.` 前半句对着「写了两份以上」才要求跨族，一份提案只要用菜单里的活跃协变量就成立。这样不依赖 `cohort_size` 是 1 还是 2。
4. Domain guidance 里的 `n>=350, n_eff>=50, DirAcc>=0.52` 三个数删掉。换成：`A proposal passes only when the slow loop's existing aligned gate passes. This prompt does not add a direction-accuracy cutoff.` 同一文件第 34 行的示例已经把放弃条件写成该品种的 adaptive `effective_min`，第 107 行的近失段也写了 `effective_min`。第 8 条是 `failure_delta`，不要改。第 34 行现有的中文这一轮留着。

另外两份会进入同一次渲染的文本，改同一件事，否则上面的改动到不了快环：

5. `task_FM/roles/peer_generalist/skill.md` 的 Proposal scope。品种行改成：`symbol: only target_symbols in /home/abug/timesfm/scripts/praxist_goal.yaml. Do not use a shorter list.` 第 26 行整句改成：`aligned dir_acc below that symbol's adaptive effective_min, or endpoint_mape does not improve (falsifiable)`。不要把 `prompt_base.jinja2` 第 34 行的「低于该品种」抄进这个文件。那句是旧示例，这一轮留在 `prompt_base.jinja2`。技能文件里新写的句子用英文，这样验收表的英文锚点才能对上。`symbol_fit` 里的 positioning 一词是微观结构举例，留着。`mechanism` 那一行已有的中文也留着。
6. `task_FM/prompt_generation.jinja2` 的 anti_mainline 句。删掉 `inventory, volatility, calendar, term_structure, macro_sentiment` 这个名单。换成：`Cover a neglected family that has at least one ACTIVE row in the menu. Do not invent a family the menu does not list.` 同一文件里 `adaptive gate (0.50-0.52)` 是在描述现有自适应区间，这一轮不改。

改完后的禁止文字和必须出现的文字：

| 文件 | 不得再出现 | 必须出现 |
|---|---|---|
| `task_FM/prompt_base.jinja2` | `{m, ss, sr, cj, jd, lh, eg, rb}`、`2-star`、`"covariate_family": "positioning"`、`macro_sentiment`、`n>=350`、`n_eff>=50`、`DirAcc>=0.52` | `/home/abug/timesfm/scripts/praxist_goal.yaml`、`target_symbols`、`"covariate_family": "inventory"`、`When you write two or more proposals`、`Do not invent a family the menu does not list`、`the slow loop's existing aligned gate` |
| `task_FM/roles/peer_generalist/skill.md` | `{m, ss, sr, cj, jd, lh, eg, rb}`、`2-star`、`dir_acc<0.52`、`低于该品种` | `/home/abug/timesfm/scripts/praxist_goal.yaml`、`target_symbols`、`below that symbol's adaptive effective_min` |
| `task_FM/prompt_generation.jinja2` | `macro_sentiment` | `Do not invent a family the menu does not list` |

`prompt_base.jinja2` 第 2 条 `symbol_fit` 里的英文词 positioning 留着，禁止串用的是带引号的族名，不是这个词。

## 明确不做

下面每条都是这一轮的拒绝，不是待办。

- 不把 `cj` 或 `bu` 从 `target_symbols` 删掉，也不把它们写成 `DEAD`。`cj` 的当前协议过门是 18/18。
- 不拦截 `oi`、`ccl`、`nvi`、`calendar_cyclical`，也不另建一份可执行协变量注册表。活跃池就是注册表。
- 不把 `proposal_id` 做成一次性主键。同一对品种和协变量的重提由现有 `failure_delta` 规则处理：已有当前协议失败时，不足 20 字就拒绝。窗口里的重提机制文本并不相同，按 id 硬去重会砍掉这条重提路径。
- 不用审计报告那张百分比表做配额、多臂老虎机或品种熔断。那些百分比不是 `dir_acc`，也不是可复核的过门率。熔断目标品种还会和 `all_symbols_pass_phase1` 冲突。要改座位分配，先另写一份规格，并先改目标合同。
- 不加本地小模型当预筛热备，也不在这一轮恢复预筛服务。超时已经不改收割白名单。服务要不要拉起来，是运维决定，不是本文件的代码改动。
- 不清理实验目录里的历史提案来堵住 `cj`。`cj` 仍是目标品种。
- 不改 `scripts/sup_harvest.py`、`scripts/praxist_goal.yaml`、`task_FM/config/covariate_pool.json`、评估门禁、`search_policy`、`task.yaml`。写这份规格时 `search_policy` 是 `shadow`，实施时不要改这个键。
- 不改提示词开头 `cohort_size` 的默认值 4。已核对的那次渲染传入的是 2，默认值没有露给快环。
- 不引入分年切片、跨品种迁移、留出集或模拟盘。

## 以后再看

这两件不在本轮实施里。后续规格是 `docs/superpowers/specs/2026-11-18-proposal-followup-design.md`。

- 608 份重复 `proposal_id` 在收割时的去向：是 `failure_delta` 放行，还是 `dedup` 拦住但仍先花掉了快环调用。`bu` 不在短名单里仍有 39 份，说明去掉短名单之后，同 id 换一套机制的重提还会发生。
- 库存类加日历类占生成的 47.7%，而 11 月 17 日和 18 日那 63 条完成队列里是 0。慢环跑得了这两类。以后若查调度或打分为什么没排到它们，用这个窗口做题目。

## 验收

1. 新增 `tests/test_prompt_symbol_authority_20261118.py`。模块 docstring 写明它覆盖四条 `prompt_base.jinja2` 规则，以及 `skill.md` 和 `prompt_generation.jinja2` 里会进入同一次渲染的两处对应文字。测试只读这三个文本，不断言运行中的监督环，也不读裁决文件。
2. 测试按上一节的表断言禁止文字不存在、必须出现的文字存在。第 3 处和第 4 处各有正向句子，不能只靠删掉旧词就算通过。
3. 用 `/home/abug/timesfm/.venv/bin/python -m pytest` 跑下面这些测试。除第一条新测试外，下面四条是已经在读 `prompt_base.jinja2` 的静态测试，用来确认这次改词没有碰坏它们：
   - `tests/test_prompt_symbol_authority_20261118.py`
   - `tests/test_praxist_evidence_ladder.py::test_prompt_base_selection_discipline`
   - `tests/test_praxist_evidence_ladder.py::test_templates_render_directive_context`
   - `tests/test_praxist_evidence_ladder.py::test_templates_render_without_agenda`
   - `tests/test_search_peer_surface_20261007.py::test_prompt_teaches_search_fields_and_keeps_success_delta`
4. 这次改动只碰这三个提示词文件和这一个新测试。工作区里已经脏着的运行数据保持原样。不提交，不重启监督环。提示词在下一次由宿主明确要求启动的快环里生效。

## 下一步

实施计划在 `docs/superpowers/plans/2026-11-18-proposal-quality-plan.md`。计划只覆盖上面六个文本改动和这一个测试。执行计划要另一次明确授权。不提交，不重启监督环。
