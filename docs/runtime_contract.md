# Praxist 运行合同（runtime_contract）

> **定位**：三环**运行时可执行的合同**——门判据、指纹、family、预注册。
>
> ⚠️ **同名不同物**：[`superpowers/specs/praxist_control_plane.md`](./superpowers/specs/praxist_control_plane.md)
> 是**资源控制 spec**（内存/cgroup 红线 · 429 failover · Session 解卡 · ghost `active_work`），
> 本文**不含**这些。资源红线见该 spec；本文只讲运行合同。
>
> **不重复**（各有归属）：
> - 架构与两层关系 → [praxist.md](./praxist.md)
> - 启停命令与故障速查 → [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md)
> - 任务包与 peer 行为 → [../task_FM/AGENTS.md](../task_FM/AGENTS.md)
> - 运行产物分级 → [run_artifacts.md](./run_artifacts.md)
> - **门判据阈值 → [evaluation.md](./evaluation.md)**（唯一权威）
> - spec 级设计论证 → `superpowers/specs/`
>
> 最后核实：2026-10-05，commit `ee01b56`。**本文档不钉活快照**。

---

## 1. 三环速查

| 维度 | 监督环 | 快环 | 慢环 |
|------|--------|------|------|
| 载体 | `scripts/praxist_supervisor.py` | Praxist 核心（`.venv`，**不可改**） | `scripts/aligned_slow_loop.py` |
| Token | **0**（纯调度） | 有 | 0 |
| 唯一可写 | `data/cache/supervisor_state.json` · `supervisor.lock` | `results/**/proposals/*.json` | **`task_FM/config/aligned_verdicts.jsonl`** |
| 节律 | tick `POLL_S = 300`（秒） | `run_budget_hours: 1.5` | 跑到队列空 |
| 门 | goal DSL 求值 | 提案质量门 | v23 硬门 |

**tick 不是 sleep**：`scripts/praxist_supervisor.py` 的 `POLL_S = 300`，主循环由 `_sleep_interruptible()` 实现——每 1s 检查停止标志，所以 SIGTERM 最迟下个 tick 内生效，不必等满 300s。

---

## 2. Goal DSL（成功条件求值）

`scripts/goal_dsl.py::evaluate_goal()` 用 **AST 白名单**求值 `praxist_goal.yaml` 的 `success_condition`——不是 eval，是受限解释器。

**白名单函数仅 7 个**：`len` · `min` · `max` · `all` · `any` · `abs` · `round`

**禁止**（`_forbidden_nodes()` 逐个 AST 节点检查）：
- 属性访问（`ast.Attribute`）——不能碰对象
- `lambda` / `await` / 海象运算符
- 调用白名单外的函数
- 引用 snapshot 之外的变量名

`min` / `max` 是**特化过的安全版**（`_safe_min` / `_safe_max`）：空序列抛 `_Unmet` 而不是 `ValueError`。

### 当前目标

```yaml
success_condition: ["all_symbols_pass_phase1"]
budgets:
  max_cycles: 2000
  cpu_hours: 2000
  token_budget_m: null      # 2026-10-02 宿主取消上限；null 不参与停机判定
  deadline: "2028-10-02"
cadence:
  survivors_per_cycle: 3
  aligned_max_points: 600
  run_budget_hours: 1.5
  quota_window_hours: 5.0
  quota_margin_min: 30
  retest_min_new_points: 1
  # 2026-10-08：删 sc、增 jm，与候选准入门 ALLOWED_SYMBOLS 归一（evaluator 从本文件派生）
  target_symbols: [m ss sr cj jd lh eg rb i p y cf bu fu ta ma fg ur px oi sh sp ao jm]   # 24 个
```

目标语义：**每品种至少 1 个经 family 封账的确认变体**。
「原方向准确率绝对门槛」与「tier>=8」**已退役**，不再是成功条件；Phase 3 的 `multi_seed` / `decay` **仍未实现，不在目标里发明通过线**。

**复测触发判据（2026-10-08 裁定 C+a）**：`_retest_candidates` 只认 v2 schema 的
`dir_acc >= 0.50`。v1 legacy 的 `ic>=0.05 / ev>0 / pf_ratio>1.05` 已删除 ——
PF/EV/MaxDD 已在 evaluator 契约中退役，且 `INCUMBENT_PF` 因 L1 经济判决缺失恒空，
`.get(sym, 1.0)` 会把「相对 incumbent 超 105%」**静默改写**为「PF 绝对值 > 1.05」，
导致退化裁决被过度复测。`RETEST_PF_RATIO` / `RETEST_GATE_IC` / `INCUMBENT_PF`
三个符号一并删除；`RETEST_GATE_N=350`（样本量门槛）保留。
守卫：`tests/test_supervisor.py::test_retest_gate_constants_retired` +
`::test_retest_candidates_rejects_v1_legacy_rows`。

**品种集单一来源**：`target_symbols` 是目标品种与候选准入门（`evaluator.ALLOWED_SYMBOLS`）
的唯一来源，两处恒等。守卫见 `tests/test_symbol_universe_20261008.py`。

---

## 3. v23 门判据

慢环唯一的裁决口径。

> ⚠️ **阈值定义见 [`evaluation.md`](./evaluation.md)（唯一权威）**，本文只讲「门在哪、怎么接线」。
> 要改阈值：改 `evaluator.py` / `statistical_tests.py`，然后同步 `evaluation.md`——
> **不要在其他文档复述数字**。

| 门 | 实现 |
|----|------|
| 硬门（n / n_eff / effective_min） | `evaluator.gate()` / `compute_effective_min()`（`task_FM/evaluations/fm_eval/evaluator.py`） |
| 统计检验（DM） | `cascade/statistical_tests.py::diebold_mariano_p` |
| 多重比较（BH-FDR / Bonferroni） | 同上 `bh_fdr_promote()` |

要点：**自适应门槛**（基线差时门槛自动降，低于字面值仍过门是设计）· **fail-closed**（NaN/inf 一律拒）· **旧行缺 `baseline_dir_acc` 时按「未知门槛」读**。

**裁决三态**：`v2_pass` / `hard-gate-but-losing` / 变体级 `DEAD`（`materialize_known_verdicts`）。
品种级 `SYMBOL_DEAD` / `HOLD`（`config/symbol_status.json`）是**另一套状态机**，别与变体级 DEAD 混名。

---

## 4. protocol_fingerprint

### 七组件

| # | 组件 | 来源 |
|---|------|------|
| 1 | `CONTEXT_BARS` / `CONTEXT_DAYS` | `backtest_config` |
| 2 | `EVAL_WINDOW_BARS` | 同上 |
| 3 | `STEP` | 同上 |
| 4 | `HORIZON` | 同上 |
| 5 | cutoff 约定（`bar_close`） | `compute_protocol_fingerprint(cutoff_convention=…)` |
| 6 | cov_fill 版本（`v2`） | `evaluator.COV_FILL_VERSION` |
| 7 | adj_rule（`v1`）+ roll_guard（`v1`） | `evaluator.ADJUSTMENT_RULE_VERSION` / `ROLL_GUARD_VERSION` |

映射表：[fingerprint_component_mapping.md](./fingerprint_component_mapping.md)

### 当前版本

**`protocol_v4`** —— 定义在 `task_FM/evaluations/fm_eval/evaluator.py` 的 `PROTOCOL_FINGERPRINT_VERSION`。
`scripts/restart_readiness_check.py` 的就绪检查有 `assert` 守着，版本不符直接启动失败。

### bump 后的必做动作

指纹一变，**所有基线跨协议不可比**。`praxist_supervisor.py::ensure_baselines` 自动比对，不符即**整品种重生**。

历史教训：原实现只查 `n_lines < 100`，导致 rb 的旧基线（588 行、protocol_v1）被静默保留，表现为 `dm_status=protocol_mismatch` 难以归因。**现在指纹校验已补上**（`_baseline_protocol_fingerprint()`）。

`scripts/fingerprint_lib.py` 的**静默回退已退役**（W6.4）：找不到 praxist 二进制会抛异常，不再假装成功。

### 指纹不覆盖的东西 ⚠️

**数据窗口语义不在指纹里**。2026-09-28 的 1-bar 前视 bug（`kline_1h.dt` 是开盘时间，`dt <= cutoff` 会放进目标首根，修法 `_h1_upper_bound = cutoff_ts − 1h`）**指纹完全测不出来**——协议没变，数据语义变了。
→ 修数据窗口类 bug 必须**强制重生**，不能靠指纹 bump 兜底。

---

## 5. 研究 family

`cascade/research_family.py` 是状态机的**唯一家**；`praxist_supervisor.py` 的接线是**薄接线**，别把状态机搬进监督环。

| 规则 | 值 | 为什么 |
|------|---|--------|
| 时间窗 | 90 天 `close_at` | 防止无限探索 |
| 成员上限 | 20 / family | 控制 K 值 |
| 单成员 `T_max` | 180 天 | 兜底，防止单点拖死整族 |
| **abandoned / timeout 计入 K** | — | **防「结果不好就丢掉」式 p-hacking** |
| 封账 | **一次性**跑 BH-FDR | 防止封账时选择性汇报 |

**DEAD 家族判据**（`scripts/praxist_supervisor.py` 的 `_dead_families(snapshot, min_ok=4)`）：
只数 `dm_status ∈ {ok, set_mismatch_ok}` 的 ok 行；`n_ok ≥ 4` 且 `gate_pass == 0` 才算死亡。
`insufficient_common` / `no_common_cutoff` / `set_mismatch_descriptive` 等**描述性 DM 一律不计数**——它们不代表「试过且失败」。

详见 [family_boundary_rules.md](./family_boundary_rules.md)。

---

## 6. 预注册与确认通道

**目的**：确认级裁决必须事先注册参数，防止「跑完挑一个显著的报」。

### prereg_id

32 位 hex（`preregistry.jsonl` 现有 2 条：jd / sr）。
记录**协变量矩阵指纹 + 模型权重指纹 + 预测参数 + kill/promote 条件**。
**改任何预测参数 → 必须新 prereg_id**（append-only，旧记录不可变）。监督环对 `preregistry.jsonl` **只读**。

### 确认通道的三重隔离

1. `confirm_from_ts` 在注册时固定（如 `2026-10-03 00:00:00`），探索期数据不得进确认窗口
2. checkpoint 命名空间隔离：`{vid}__prereg_{id[:8]}.jsonl`——**防 resume 把探索点混进确认 DM**
3. 确认判定：`run_mode == "confirmation"` ∧ `gate_pass` ∧ `fdr_pass` ∧ `p_value` 非空 ∧ `pairing_valid` ∧ `missingness_admissible` ∧ `dm_status ∈ {ok, set_mismatch_ok}`

落盘前还有一道 `fdr_pass_persistable()`：只有**确认运行 + 缺失可接受 + DM 可确认**时 `fdr_pass=True` 才允许写。

---

## 7. 提案质量门（18 道）

监督环 harvest 时逐条筛，任一不满足即拒收。实现：`_proposal_quality_gate()`。

| 门 | 拒收条件 |
|----|---------|
| `missing_symbol_or_cov` / `symbol_not_allowed` | 品种缺失 / 不在允许集 |
| `cov_archived` / `cov_not_in_active_pool` | 协变量已归档 / 不在活跃池 |
| `no_current_baseline` | 该品种无有效基线 |
| `mechanism_too_short` | mechanism < 40 字 |
| `no_failure_delta` | 有失败史却没写 failure_delta（≥ 20 字） |
| `symbol_dead` / `symbol_hold` | 品种已 DEAD / HOLD |
| `dedup` / `backlog_dup` / `duplicate_proposal_id` | 重复提案 |
| `family_dead` | 家族已封账 DEAD（min_ok=4） |
| `schema_mismatch` / `proposal_id_mismatch` | JSON schema 不符 |
| `invalid_covariate_family` | 协变量族不在 6 族词表内 |
| `missing_predicted_direction` | 缺预测方向 |
| `missing_kill_promote` | 缺 kill / promote 条件 |

### 板块级 circuit-breaker：`scripts/praxist_supervisor.py` 的 `_sector_filter_check()`

**只有板块成员全集失败才拦。** 这是防饿死设计：

> 若按「≥N 个品种失败」拦截，生产快照中三个板块都 ≥3 失败 → **所有提案被拦 → 慢环饿死**（与 2026-09-24 `no_failure_delta` 饿死同构）。

未观察到的品种视为「未评估」，不计入失败数。2026-10-03 起失败数只认 `_is_confirmable_failure()`——否则描述性行会把板块推向断路器。
T7 追加：失败数 ≥ 板块 50% 但未全失败时打 WARN 预警（部分退化）。

---

## 8. 资源红线

| 项 | 机制 | 载体 |
|----|------|------|
| Token | `token_budget_m: null`（2026-10-02 取消）；`tokens_baseline_m` 仍记录 | `supervisor_state.json` |
| 配额窗口 | `quota_window_hours: 5.0` + `quota_margin_min: 30` 提前量 | `quota_gate()` |
| 429 | `paused_429` 置位；`_failover_configured()` 探备路 | supervisor |
| failover | Ark（primary）/ DashScope（Anthropic 兼容端点，failover） | `FAILOVER_*` / `ANTHROPIC_FAILOVER_*` |
| 内存 | `mem_guard.py` · `praxist_mem_guard_hook.py` | hook + 独立进程 |
| Session 卡死 | `praxist_session_unstick.py` | 独立脚本 |
| 并发 | `supervisor.lock`（`flock LOCK_EX \| LOCK_NB`），抢不到就退避退出 | supervisor |

### 禁止事项

1. **未批准不得启动第二个监督环**——flock 会让第二个立刻退出（这是保护不是故障）
2. **不得清除 `SHUTDOWN` 标志**来强行重启
3. **不得让 peer 绕过 flock 跑评估**（`evaluations/fm_eval/run.py` 对 peer 禁用）
4. **不得改 `.venv` 里的 Praxist 源码**——升级会丢；用 `task.yaml` 的 `praxist_plugins` 声明
5. **不得手改运行产物**（`aligned_verdicts.jsonl` 仅慢环可写；`known_verdicts.inc.md` / `covariate_menu.inc.md` 每轮重新物化，手改会被覆盖）

---

## 9. 已知缺口

### 跨 run 反馈通道未实现 ⚠️

`experiments/run_*/memory/research_memory.jsonl` 每个 run 都创建，但**全部为 0 字节**（2026-10-05 核实 213 个文件，最大 0）。
代码里**没有**「读上一 run 的 research_memory 并注入下一 run 提示词」的逻辑。

后果：**peer 每次提案都是盲猜**——它只知道本轮 materialize 的 `known_verdicts.inc.md`，拿不到历史 cycle 的实际结果。225 cycle 的结果从未回传。
`shared_store.db` 存在但是 Praxist 运行时内部状态库（session / frontier / gems），**不是**面向 peer 的反馈通道。

闭合方案：`superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md`（D1–D4）
分析：`superpowers/reports/2026-10-05-peer-learning-gap-analysis.md`

### Stage 3 三个新模块的接线状态

`experiment_fingerprint` **已接线**：`ef.build_variant_id()` 在 `praxist_supervisor.py` 有 **3 个调用点**（373 / 1167 / 2436）。
另有 2339 行的 `ef.compute_experiment_fingerprint()`——**不同函数**，勿混淆。
历史 `aligned_verdicts.jsonl` 混着两种 vid 格式——旧行 `{symbol}_{cov}`，新行 `{symbol}_{family}_{fp12}`。**读历史行别假设格式统一。**

---

## 10. 变更记录

| 日期 | 内容 |
|------|------|
| 2026-10-05 | 初版。事实基线实测自 commit `ee01b56`，全部经代码核实 |
