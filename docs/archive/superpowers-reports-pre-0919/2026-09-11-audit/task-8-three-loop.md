# Task 8：Praxist 三环代码

- 任务：`docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 8
- 简报：`.superpowers/sdd/2026-09-11-full-system-audit/task-8-brief.md`
- 仓：WSL `/home/abug/timesfm`（不把 `D:\FlyBuddy\timesfm` 当真相源）
- 审核日：2026-09-11
- 范围：快环 / 慢环 / 监督环是否仍满足方案 A 硬规则；已知瑕疵 `i_oi` 与 materializer 现状；缺测试记 Important
- 模式：只读生产代码。允许读 `data/cache/supervisor_state.json` 作快照。不改状态、不启 Praxist、不启监督环
- 合同源：`docs/praxist.md`、`docs/spec_hypothesis_driven_fast_loop_20260908.md`、`loop-constraints.md`；runbook 仅作运维对照

**结论先说：** 活路径仍是方案 A。`_harvest_rows` 调 `harvest_proposals` 而不是 `evaluation_summary.json`；`mechanism>=40` 有拒绝计数和测试；慢环没抽干时 `decide_fast_loop` 不开下一轮快环；生产循环里只有 `aligned_slow_loop.py` 往 `aligned_verdicts.jsonl` 追加。同提供商 429 会 stop 再 resume 同一 `run_dir`。真正的洞在三处：peer 不评估只靠提示词，`task.yaml` / `role.yaml` 仍挂着评估入口；`harvest_proposals` 不校验 `schema=fm.hypothesis_proposal.v1`；`gate_pass` 仍不含 EV，磁盘上 `i_oi` 和新增的 `m_ccl` 都是「过硬门但亏钱」，`known_verdicts.inc.md` 仍写 already solved。Task 3 说的 runbook L82「paused_429 不 harvest」与代码矛盾，**坐实**：代码在 429 暂停期间仍然 harvest。

---

## 0. 快照（只读，不推断进程是否在跑）

`data/cache/supervisor_state.json`（mtime 2026-09-10 03:26 +0800）：

| 键 | 值 |
|----|----|
| `phase` | `fast` |
| `cycles_done` | `1` |
| `paused_429` | `false` |
| `last_run_id` | `run_2026-09-10_03-06-50_primary_task_FM` |
| `last_run_dir` | `/home/abug/timesfm/task_FM/experiments/run_2026-09-10_03-06-50_primary_task_FM` |
| `last_harvested_run_id` | `run_2026-09-10_00-44-51_primary_task_FM` |
| `llm_provider` / `llm_route` | `primary` |

`task_FM/config/aligned_verdicts.jsonl`：26 行 / 26 个 unique。经济过门（`gate_pass` 且 `ev>0`）只有 `ss_vor`。`gate_pass=True` 且 `ev<=0`：`i_oi`、`m_ccl`。

`task_FM/known_verdicts.inc.md` mtime **2026-09-10 03:26**，落后于 registry 最后一行 `m_ccl`（2026-09-11 10:27）。文件头仍是 `gate_pass=True: already solved, do NOT re-propose.`

---

## 1. 硬规则对照（方案 A / praxist.md）

缺测试按计划记 Important。活路径是否执行，与有没有测试分开写。

| # | 硬规则 | 代码执行点 | 测试锁 | 判定 |
|---|--------|------------|--------|------|
| R1 | peers 禁止跑 `evaluations/fm_eval/run.py` | **软：** `task_FM/prompt_base.jinja2:5-9`、`prompt_generation.jinja2:40`、`roles/peer_generalist/skill.md:3-6,42-52`、`description.md:6`、`task.yaml` `research_direction`。**硬缺口：** `task.yaml:83-85` 仍 `task_entrypoints.evaluation.command: evaluations/fm_eval/run.py`；`:90-98` `diagnostic.launch_allowed: true`；`:136-137` `praxist_plugins.evaluations: [task_evaluation:fm_eval]`；`roles/peer_generalist/role.yaml` `tool_scope` 含 `evaluation_tools.peer`。`fm_eval/run.py:73-80` 仍会 `DailyModel()` / `HourlyModel()` 并写 `evaluation_summary.json`。 | **无。** `tests/test_praxist_evidence_ladder.py` 不断言「do NOT run TimesFM」。`tests/test_praxist_task_contract.py` 锁的是 2026-09-01 旧契约（`write_paths`=`scripts/praxist_ws`，必须有 `diagnostic` 档），不锁方案 A。 | 提示词对齐；能力面仍能调评估。缺测试 = Important |
| R2 | peers 禁止加载 TimesFM | 同上。活 harvest 不读诊断产物，所以 peer 若违禁加载，浪费内存但**不会**直接写入 `aligned_verdicts.jsonl`。 | **无** | 同 R1 |
| R3 | schema `fm.hypothesis_proposal.v1` | spec §3.2 / §4.3 要求 schema 不符即拒绝。`harvest_proposals`（`scripts/praxist_supervisor.py:603-623`）校验 symbol / cov / mechanism 长度 / 池 / 去重，**从不读 `p["schema"]`**。缺 schema 或写错 schema 只要有 symbol+cov+≥40 字 mechanism 就会入队。 | `tests/test_harvest_proposals.py` 只造合法 schema，**无** `schema_mismatch` 拒绝用例 | 合同未执行。缺测试 = Important |
| R4 | `mechanism` ≥40 字（禁模板） | `praxist_supervisor.py:613-623`：`len(mechanism) < 40` → `_reject("mechanism_too_short")`。没有模板检测（重复菜单句、复制示例 heredoc 只要够长就过）。 | `tests/test_harvest_proposals.py:71-75` `test_short_mechanism_rejected` | 长度有锁；「禁模板」无代码无测试 |
| R5 | `survivors_per_cycle=3` | `scripts/praxist_goal.yaml:21` 为 3。`_harvest_rows`（`praxist_supervisor.py:1291`）`cad.get("survivors_per_cycle", 2)`，活 goal 下 top_k=3。缺 cadence 时默认 **2**，与合同 3 不一致。 | `tests/test_supervisor.py` 多处 fixture 写 `survivors_per_cycle: 2`（如 `:162,:217,:237`）。`test_harvest_proposals.py:139` 用 `top_k=3` 测分层，**不**读 `praxist_goal.yaml`。`test_goal_dsl.py` 不涉及 cadence。 | 活路径过；生产值 3 无测试锁 = Important |
| R6 | phase 互斥：慢环未抽干 → 禁止下一轮快环 | `ensure_phase`（`:929-936`）：队列忙或慢环活则 `phase=slow`。`decide_fast_loop`（`:1151-1152`）：`phase==slow` 直接 return，不 start。`main`（`:1537-1541`）slow 优先于 `decide_fast_loop`。入队后 `_maybe_harvest` 置 `phase=slow`（`:1315`）。 | `tests/test_supervisor.py:322-368` `test_harvest_survivors_enter_slow_no_start_no_cycle`（有提案入队 → phase=slow、本 tick 无 `start`、cycles 不加）；`:422-443` `test_phase_slow_blocks_start_even_in_window` | **有测试** |
| R7 | 只有慢环写 `aligned_verdicts.jsonl` | 生产追加：`scripts/aligned_slow_loop.py:119-122` `rl.append_verdict`。监督环 `REGISTRY`（`praxist_supervisor.py:28`）只 `load_snapshot`。`grep append_verdict` 生产脚本仅慢环。例外：`scripts/praxist_assets_archive.py:281-292` `restore-verdicts` 默认 dest 就是该 jsonl（人工 CLI，不在 300s tick 里）。 | `tests/test_aligned_slow_loop.py:20-38` 断言候选跑完写入临时 registry；`:97-120` 异常不写死亡 verdict。**无**「supervisor 不得 open(REGISTRY,"a")」测试 | 活路径过；缺唯一写者锁 = Important |
| R8 | 429 后 resume 同一 run，禁止开新 run | 同提供商：`decide_fast_loop` 在 `paused_429` 且配额恢复时 `_plan_resume(rd, "primary", ...)`（`:1180-1184`）。测试：`test_429_stop_then_resume`（`:246-272`）、`test_429_stop_via_main_once_then_resume`（`:285-319`）。**例外：** `_failover_can_resume_same_run`（`:320-329`）模型身份不同（claude→qwen）则 FRESH `start`；`test_paused_429_fresh_start_on_identity_wall`（`:823-851`）把开新 run 锁成预期。`praxist.md:81` / runbook L80 未写这条例外。 | 主路径有；例外也被测试锁成「允许开新 run」 | 主路径过；failover 字母违约（见 I6） |
| R9 | harvest = `harvest_proposals`，不是诊断 `evaluation_summary.json` | `_harvest_rows`（`:1283-1294`）只调 `harvest_proposals`，glob `results/**/proposals/*.json`（`:596`）。`harvest_survivors`（`:419-468`）仍在，读 `evaluation_summary.json` + 诊断 EV，**无生产调用点**（仅测试与回滚）。 | `tests/test_harvest_proposals.py` 全文件；`test_supervisor.py:322-368` 主循环造 `proposals/*.json` 入队。`test_harvest_survivors`（`:91-125`）仍测回滚函数，注释写明不走活路径。 | **活路径过，有测试** |
| R10 | runbook L82：`paused_429` 期间不 harvest（Task 3 I4，本任务确认） | 代码相反。`_maybe_harvest` 文档字符串（`:1299-1300`）：`paused_429 / wait_quota / failover do NOT block harvest`。`main`（`:1527-1529`）：`Harvest finished runs even during paused_429 / wait_quota.` 门闩只有 `_run_active()` / 已收割 / 无 `last_run_id`。runbook L82 与 L123（「活 run 结束且非 paused_429 时」才 harvest）都落后于代码。`praxist.md:81-82` 只说 run 结束后 harvest，**没有**禁止 429 期间收割。方案 A 下提案是本地文件，429 时抽干慢环与控制面 L191 一致。 | **无**测试断言「paused_429=True 且 run 已停仍会 harvest」 | 代码有意 harvest；runbook 落后。缺测试 = Important |

---

## 2. 已知瑕疵现状

### 2.1 `i_oi`（以及后来的 `m_ccl`）：`gate_pass` vs 负 EV

硬门实现（`task_FM/evaluations/fm_eval/evaluator.py:199-203`）：

```
def gate(s, min_n=350, min_ic=0.05):
    ic = 2 * abs(m.get("dir_acc", 0.5) - 0.5)
    return m["n"] >= min_n and ic >= min_ic
```

不含 EV。`tests/test_praxist_fm_evaluator.py:23-28` 只测 n 门槛，不测负 EV。

磁盘最新裁决：

| variant | n | ic | ev | pf | gate_pass | 经济过门 |
|---------|---|----|----|----|-----------|----------|
| `ss_vor` | 396 | 0.06 | +11.06 | 1.123 | true | 是（`pass_variants` 收录） |
| `i_oi` | 396 | 0.066 | **−2.46** | 0.818 | **true** | 否 |
| `m_ccl` | 396 | 0.088 | **−3.64** | 0.839 | **true** | 否（2026-09-11 10:27 新写入） |

`scripts/registry_lib.py:39-45` `pass_variants` 要求 `gate_pass and ev>0`，所以目标 DSL 不会把 `i` / `m` 算进 `symbols_hit`。`dead_variants`（`:48-50`）只要 `gate_pass is False`，这两条**既非过门也非 DEAD**。于是：

- harvest 去重用 `passing_ids` ∪ `dead` ∪ in-flight：peer 若再写 `i_oi.json`，**可以再次入队**；
- 提示词和 materializer 却说不要再提议。

`tests/test_verdict_registry.py:39-48` 测了 `gate_pass=True, ev=0.02` 过门，以及 `gate_pass=False` 为 dead，**没有** `gate_pass=True` 且 `ev<0` 的夹具。

### 2.2 materializer / `known_verdicts.inc.md` 仍误导 peer

`materialize_known_verdicts`（`praxist_supervisor.py:473-477`）：

```
gate_pass=True: already solved, do NOT re-propose.
gate_pass=False: DEAD, revive only with PI mechanism correction.
```

只展示 `items[:20]`，按 `(not gate_pass, -ev)` 排序。`tests/test_supervisor.py:565-572` 只断言 `gate_pass=True/False` 出现在文件里，把误导性文案锁成「有 True 就算过」。

`task_FM/prompt_base.jinja2:67-68` 把同一句话写进每代提示：`gate_pass=True = already solved`。

磁盘 `task_FM/known_verdicts.inc.md` 现状（2026-09-10 03:26 物化）：

- 头两句仍是 already solved / DEAD；
- 列出 `ss_vor`（True, ev=+11.06）和 `i_oi`（True, ev=−2.46）；
- **没有** `m_ccl`（registry 已有、inc 未刷新）。

praxist.md:110 与 runbook harvest 节「已知语义瑕疵」描述的就是这件事，**未修**，而且从 1 条变成 2 条。

---

## 3. 429 harvest 确认（Task 3 I4）

| 源 | 说法 |
|----|------|
| runbook L82 | `paused_429` 期间不 harvest、不 start |
| runbook L123 | 活 run 结束且**非** `paused_429` 时才 `harvest_proposals` |
| `praxist_supervisor.py:1299-1300` | `paused_429 / wait_quota / failover do NOT block harvest` |
| `praxist_supervisor.py:1527-1529` | `Harvest finished runs even during paused_429 / wait_quota.` |
| 控制面 L191（Task 3 已引） | harvest 不再因 paused_429 跳过 |

**确认：** 代码在 429 暂停期间**会** harvest。条件是 run 已不 active。方案 A 下这是合理合同（本地 JSON，不烧 TimesFM）；runbook L82/L123 落后。本任务未改文档。

无测试覆盖这条有意行为。

---

## 4. 其他活路径细节（非阻塞，但要写清）

**选座：** `harvest_proposals`（`:650-671`）tier（1 星 n≥350 → 欠样本 → 其余）+ 两遍 family QD。`test_priority_symbols_tiered_seat_fill`（`test_harvest_proposals.py:125-145`）锁了 `top_k=3` 时选 `jd_nvi, m_oi, cj_vor` 而不是 2 星。

**扫描范围：** spec §4.3 曾写「仅本 run」；实现 glob 全部 `run_*`（`:592-596`），注释 `:541` 与 2026-09-09 spec 增补承认 pending-proposals 索引未做、每 cycle 重扫。`test_new_covariate_dedup_across_harvests` 覆盖 backlog 去重。

**cycle：** 有入队则 phase=slow、cycles 不加，直到 `_maybe_finish_slow`（`:1356-1366`）队列空且慢环死；空收割 `harvest_empty` 立刻 +1（`:1325-1330`）。测试：`test_harvest_empty_counts_cycle_and_allows_start`、`test_slow_drain_counts_cycle_then_start`。

**慢环：** `aligned_slow_loop.py` 加载 TimesFM（这是合同允许的唯一验证器），写 verdict，异常不 ack、不写死亡行（`:169-175`）。

---

## 5. Findings

### Critical

无。活 harvest 不是诊断幸存者；监督环不写 registry；同提供商 429 会 resume 同一 run。没有发现「按现行代码执行会伪造 aligned verdict / 把诊断 PF 当裁决」的路径。

### Important

**I1. peer「禁止评估」只写在提示词里，任务包仍暴露评估能力。**

- 证据：`task_FM/task.yaml:83-85,90-98,136-137`；`roles/peer_generalist/role.yaml` `tool_scope` 含 `evaluation_tools.peer`；`audit_rules/scope_and_protocol/audit.yaml` 仍要求 scheduled evaluator 写 `evaluation_summary.json`，可写区仍是 `scripts/praxist_ws`。
- 对照：`prompt_base.jinja2:5-9`、`loop-constraints.md:49`、`docs/praxist.md:67`。
- 为何严重：7.7GiB 宿主上 peer 一旦走入口加载 TimesFM，会和慢环抢内存。方案 A 的「0 次模型加载」没有能力面闸门。
- 建议（不落地）：`diagnostic.launch_allowed: false`；拿掉 peer 的 `evaluation_tools`；审计规则改为提案文件而非 `evaluation_summary.json`。未在 Praxist 0.5.0 源码里证实插件会自动调度评估（见开放问题）。

**I2. `harvest_proposals` 不校验 `schema=fm.hypothesis_proposal.v1`。**

- 证据：`praxist_supervisor.py:603-623` 无 schema 分支。spec `docs/spec_hypothesis_driven_fast_loop_20260908.md` §4.3 要求 schema 不符即拒绝。
- 测试：无 `schema_mismatch` 用例。
- 建议：拒绝非 `fm.hypothesis_proposal.v1` 并计入 `reject_reasons`；补测试。

**I3. `gate_pass` 不含 EV；materializer / 提示词把亏钱组合标成 already solved。未修，且从 `i_oi` 扩到 `m_ccl`。**

- 证据：`evaluator.py:199-203`；`aligned_verdicts.jsonl:19` `i_oi` ev=−2.46；`:26` `m_ccl` ev=−3.64；`praxist_supervisor.py:473-477`；`prompt_base.jinja2:67-68`；`known_verdicts.inc.md:2,6`。
- `pass_variants`（`registry_lib.py:44`）经济过门是对的；DEAD/过门二分把「过硬门但亏钱」弄丢。
- 建议：materializer 三态（经济过门 / 过硬门但亏钱 / DEAD）；提示词同步；测试夹具 `gate_pass=True, ev<0`。不要把 EV 塞进 `evaluator.gate` 除非权威链明确改硬门（Task 1 已区分两层门）。

**I4. 生产 `survivors_per_cycle=3` 没有测试锁；`_harvest_rows` 缺省是 2。**

- 证据：`praxist_goal.yaml:21` vs `praxist_supervisor.py:1291` vs `test_supervisor.py:162` 等。
- 建议：测试读真实 `praxist_goal.yaml` 断言 3；缺省改为 3 或去掉缺省强迫 cadence 必填。

**I5. 唯一写者、禁止评估、429 期间仍 harvest，这三条硬规则没有测试。**

- 唯一写者：无「supervisor 不 append registry」。
- 禁止评估：无「prompt_base / skill.md 含 never run fm_eval」；无「role 不含 evaluation_tools」（当前还含有，测试若去锁会先红）。
- 429 harvest：无 `paused_429=True` + 已停 run → `harvest_proposals` 仍入队。

**I6. 429 failover 在模型身份墙时开新 run，与「禁止开新 run」字面冲突。**

- 证据：`praxist_supervisor.py:320-329,1094-1110`；`tests/test_supervisor.py:823-851` 把 FRESH start 锁成正确。
- 原因：Praxist resume 不允许 claude→qwen。`docs/praxist.md:81` 未记载。
- 建议：合同补一句「failover 且模型 id 不同 → 允许 start 新 run_dir，不得在原 run 上改模型」；或主备改成同一 model id 才能真正 resume。

**I7. `test_praxist_task_contract.py` 锁的是方案 A 之前的契约。**

- `:37-41` `write_paths` ⊆ `{scripts/praxist_ws, reports/praxist}`；`:47-50` 必须有 `diagnostic` 档。`config/praxist_task.yaml:16-27` 仍是这份旧文。
- 对照：`loop-constraints.md:51` peers 可写区是 run 下 `results/`。
- 风险：执行者按这份测试「修契约」会把方案 A 可写区改回去。

**I8. `known_verdicts.inc.md` 落后于 registry。**

- inc mtime 2026-09-10 03:26；`m_ccl` 2026-09-11 10:27 已在 jsonl。物化只在监督环 tick / 慢环抽干时发生（`praxist_supervisor.py:1444,1361`）。快照如此，不推断监督环是否在跑。

### Minor

**M1.** `harvest_proposals` 重扫全部 `run_*`，不是「仅本 run」。spec 增补已承认。未入选提案可在后续 cycle 再占座位（dead/in-flight 去重仍在）。

**M2.** `test_harvest_survivors_enter_slow_no_start_no_cycle` 函数名仍叫 survivors，正文已改走 proposals。

**M3.** mechanism「禁模板」无实现。够 40 字的菜单复读能过。

**M4.** materializer `items[:20]`，26 条 unique 会截断。当前 True 条少，截断主要砍 False 条。

**M5.** `build_snapshot` 的 `families_hit` 用 `cov_override` 当族名（`praxist_supervisor.py:409`），与 QD 的 family 不是同一概念。影响 goal `len(families_hit)>=1` 的语义，不是本任务主合同。

**M6.** `praxist_assets_archive.py:292` `restore-verdicts` 默认写生产 jsonl。人工例外，活 tick 不用；合同「只有慢环可写」在 ops CLI 上不严格。

---

## 6. 硬规则 × 测试（给 Task 10 的一行表）

| 硬规则 | 有没有锁现行合同的测试 |
|--------|------------------------|
| peer 不跑 fm_eval / 不加载 TimesFM | **无**（提示词未断言；role 仍给 evaluation_tools） |
| schema `fm.hypothesis_proposal.v1` | **无**（实现也不校验） |
| mechanism ≥40 | **有** `test_short_mechanism_rejected` |
| 禁模板 | **无** |
| `survivors_per_cycle=3` | **无**（测试用 2；分层测试的 top_k=3 是参数不是 goal 文件） |
| phase 互斥 | **有** `test_phase_slow_blocks_start_even_in_window` 等 |
| 慢环唯一写 aligned_verdicts | **部分**（慢环写入有测；「别人不写」无测） |
| 429 resume 同一 run | **有**（同提供商）；failover 开新 run 也被测成合法 |
| harvest = harvest_proposals | **有** |
| 429 期间仍 harvest | **无** |
| gate 三态 / 负 EV 不得 already solved | **无** |

`tests/test_goal_dsl.py`：成功条件表达式与注入防护，与三环硬规则无关。
`tests/test_praxist_task_contract.py`：锁预注册指标名和旧可写区，**不**锁方案 A。

---

## 7. 开放问题

1. Praxist 0.5.0 是否会仅因 `praxist_plugins.evaluations: [task_evaluation:fm_eval]` 和 `diagnostic.launch_allowed: true` **自动**调度 `fm_eval/run.py`，还是必须 peer 主动调 `evaluation_tools`？未读 `.praxist-venv` 源码（praxist.md 红线：不要改 venv 里的 Praxist）。若会自动调度，I1 应升到 Critical。
2. `last_run_id` ≠ `last_harvested_run_id` 只是快照事实；本任务不判断监督环是否在跑，也不判断那次 run 的提案是否还在磁盘未入队。

---

## 8. 做得对的地方

- `_harvest_rows` 只调 `harvest_proposals`；`harvest_survivors` 留作回滚，注释和 `test_harvest_survivors` 都标明诊断路径已退役。
- 长度不足的 mechanism 会 fail visibly（`reject_reasons`），有测试。
- phase=slow 时窗口够也不 start，有端到端 `--once` 测试。
- 同提供商 429：stop → 解封 resume 同一 `run_dir`，有测试。
- 慢环异常不写死亡 verdict、不 ack，队列可 recover。
- `pass_variants` 已要求 `ev>0`，目标 DSL 不会把 `i_oi` / `m_ccl` 算成功。
- 近失误复测走 `ev>0`（`praxist_supervisor.py:847`），不会把亏钱的 `i_oi` 当欠样本复测。

---

## 9. 建议修复顺序（仍不改代码）

1. materializer + `prompt_base` 三态（I3）：peer 每代都读，成本低。
2. 合同补 failover 身份墙（I6）或改 runbook L82/L123 与代码对齐（R10）。
3. 关掉 peer 评估能力面（I1），再补提示词/role 测试（I5）。
4. harvest 校验 schema（I2）；goal.yaml 的 `survivors_per_cycle=3` 加测试（I4）。

---

## 10. 状态

**DONE_WITH_CONCERNS**

- Critical: 0
- Important: 8
- Minor: 6
- 活路径方案 A：成立（harvest_proposals、phase 互斥、慢环写 verdict、同提供商 429 resume）
- 已知瑕疵：仍在，且 `m_ccl` 是第二条「过硬门但亏钱」
