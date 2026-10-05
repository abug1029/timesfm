<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-10-05 | Verified: 2026-10-05 (commit ee01b56) -->

# task_FM

FM_a 的 Praxist 任务包：把「找更好的协变量」这件事写成一份**可被 agent 执行的合同**。
本目录不是普通源码目录——它是**科学合同的载体**，改一个字就可能改变生产提案面。

上游：[../docs/praxist.md](../docs/praxist.md)（架构）· [../docs/runbook_praxist_three_loop.md](../docs/runbook_praxist_three_loop.md)（运维）
裁决口径权威：[../docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md](../docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md)（v23）

---

## Purpose

定义方案 A 三环的**科学合同**：peer 提什么假设、慢环怎么裁决、什么条件下提案被拒。
手写合同与机器生成产物严格分离——见下表。

---

## Key Files

### 手写合同（人 / agent 维护，改动即改生产面）

| 文件 | 职责 | 改动后果 |
|------|------|---------|
| **`task.yaml`** | 任务包元数据：schema、capabilities、prompt_layout、evaluation、compute_budget、praxist_plugins | 需重启监督环 |
| `description.md` | 人类可读任务说明（方案 A 合同摘要） | 需重启监督环 |
| **`prompt_base.jinja2`** | 每代 peer 的稳定系统提示词 | **被 peer 提示词内嵌，改动直接影响生产提案面** |
| `prompt_generation.jinja2` | 每代动态指令（agenda / frontier / role 契约） | 运行时渲染 |
| `roles/peer_generalist/role.yaml` | peer 角色：`peer_role_rotation = [exploit, falsifier]` | 需重启监督环 |
| `roles/peer_generalist/skill.md` | peer 技能说明（hypothesis author 协议、禁止事项） | 需重启监督环 |
| `audit_rules/scope_and_protocol/audit.yaml` | 红线审计（`audit.scope_boundary` capability，blocking severity） | 需重启监督环 |
| `.praxist/plugins/panel_topologies/fm_two_peer/plugin.yaml` | 2-peer panel topology | 需重启监督环 |
| `config/covariate_pool.json` | 协变量池权威源（6 族受控词表，active / archived） | 提案可选范围 |
| `config/symbol_status.json` | 品种探索状态机（`ACTIVE` / `DEAD` / `HOLD`） | 直接决定提案是否被拒 |
| `config/preregistry.jsonl` | 预注册唯一家（**append-only**，监督环只读） | 确认通道的唯一凭据 |
| `evaluations/fm_eval/evaluator.py` | 核心评估器 | 见下 §Evaluator |
| `evaluations/fm_eval/run.py` | 评估入口（**peer 禁止跑**） | — |

> **`.venv` 里的 Praxist 源码不可改**——升级会丢。task 侧通过 `task.yaml` 的 `praxist_plugins` 声明拓扑 / roles / audit，**不要改 .venv 的校验器**。

### 运行产物（机器生成，不要手改）

| 文件 | 生成者 |
|------|--------|
| `known_verdicts.inc.md` | 监督环 `materialize_known_verdicts` 每轮物化 |
| `covariate_menu.inc.md` | 监督环 `materialize_covariate_menu` 每轮物化 |
| `config/aligned_verdicts.jsonl` | **仅慢环可写**（行数随慢环增长，实时 `wc -l`） |
| `config/family_registry.jsonl` | family 成员登记 |
| `config/baseline_points_*.jsonl` | `ensure_baselines` 按协议指纹重生 |
| `experiments/run_*/results/**/proposals/*.json` | peer 写的假设提案 |

> `experiments/` 的分级与清理策略见 [../docs/run_artifacts.md](../docs/run_artifacts.md)。

---

## For AI Agents

### 运行时硬约束

1. **peer 不加载 TimesFM**，不跑评估（`evaluations/fm_eval/run.py` 对 peer 禁用）
2. **peer 只写假设**，不碰裁决
3. 提案写入根仅限 `results/**/proposals/*.json`
4. **不得绕过 flock**（`scripts/praxist_supervisor.py` 持锁期间另起监督环会退避）
5. 密钥只进 `.env.praxist`，**不要写进 `task.yaml`**

### 提案质量门（18 道，`_proposal_quality_gate`）

提案被拒的常见原因——改 prompt 前先看这张表：

| 门 | 拒收条件 |
|----|---------|
| `missing_symbol_or_cov` / `symbol_not_allowed` | 品种缺失或不在允许集 |
| `cov_archived` / `cov_not_in_active_pool` | 协变量已归档 / 不在活跃池 |
| `no_current_baseline` | 该品种无有效基线 |
| `mechanism_too_short` | mechanism < 40 字 |
| **`no_failure_delta`** | 有失败史却没写 failure_delta（≥20 字） |
| `symbol_dead` / `symbol_hold` | 品种已 DEAD / HOLD（查 `symbol_status.json`） |
| `dedup` / `backlog_dup` / `duplicate_proposal_id` | 重复提案 |
| `family_dead` | 家族已封账 DEAD（min_ok=4） |
| `schema_mismatch` / `proposal_id_mismatch` | JSON schema 不符 |
| `invalid_covariate_family` | 协变量族不在 6 族词表内 |
| `missing_predicted_direction` | 缺预测方向 |
| `missing_kill_promote` | 缺 kill / promote 条件 |

### peer 选题顺序（`prompt_base.jinja2` 的纪律）

1. 先读 `known_verdicts.inc.md`（Symbol status / Effective clues / **Do not re-propose**）
2. **禁止优先波动率族**
3. 顺序：Passing families 迁品种 → Near-miss 精炼 → Weak families（**仅带 failure_delta**）

### 门判据（v23）

| 阈值 | 值 | 承载方 |
|------|---|--------|
| n | ≥ 350 | `evaluator.gate(min_n=350)` |
| n_eff | ≥ 50（Bartlett） | `effective_sample_size()` |
| dir_acc | ≥ `effective_min` = `max(0.50, min(0.52, baseline_dir_acc))` | `compute_effective_min()`（`evaluator.py:697`） |
| 统计裁决 | DM（Newey-West HAC + HLN）+ BH-FDR（per-symbol；K<4 降级 Bonferroni α=0.025） | `cascade/statistical_tests.py` |
| PF / EV / MaxDD / IC | **已退役出裁决链**，仅经济报表字段 | v23 spec |

裁决三态：`v2_pass` / `hard-gate-but-losing` / 变体级 `DEAD`。
品种级 `SYMBOL_DEAD` / `HOLD` 是另一套状态机，**不要与变体级 DEAD 混名**。

### protocol_fingerprint 七组件

`CONTEXT_BARS/DAYS`(480/25) · `EVAL_WINDOW_BARS` · `STEP` · `HORIZON` · cutoff(`bar_close`) · cov_fill(`v2`) · adj_rule(`v1`)+roll_guard(`v1`)

- 版本定义：`evaluator.py:284` `PROTOCOL_FINGERPRINT_VERSION = "protocol_v4"`
- 当前值：**`f02b2a433fd572ea…`**
- 组件映射表：[../docs/fingerprint_component_mapping.md](../docs/fingerprint_component_mapping.md)
- **bump 后必须重生基线**：`ensure_baselines` 自动比对，不符即整品种重生（`scripts/fingerprint_lib.py` 的静默回退已退役，会抛异常）

### 研究 family 封账

90 天 `close_at` · ≤20 成员 · 单成员 `T_max` 180 天 · **abandoned / timeout 也计入 K**（防 p-hacking）· 封账时一次性跑 BH-FDR。
DEAD 判据：只数 `dm_status ∈ {ok, set_mismatch_ok}` 的 ok 行，`n_ok ≥ 4` 且 `gate_pass=0`。
详见 [../docs/family_boundary_rules.md](../docs/family_boundary_rules.md)。

### 预注册与确认

- `prereg_id` = 32 位 hex（`md5` 类），例：`6f944c74e2c94ca5a5b70e64676e518b`（jd, n_planned=1199）
- 改任何预测参数 → **新 prereg_id**，旧记录不可变（append-only）
- confirmation 通道：`confirm_from_ts` 注册时固定 + checkpoint 命名空间隔离 `{vid}__prereg_{id[:8]}.jsonl`
- 确认判定：`run_mode == "confirmation"` ∧ `gate_pass` ∧ `fdr_pass` ∧ `p_value` 非空 ∧ `pairing_valid` ∧ `missingness_admissible` ∧ `dm_status ∈ {ok, set_mismatch_ok}`

### Evaluator 对外接口

| 函数 | 职责 |
|------|------|
| `validate_candidate(c) -> (bool, str)` | 校验候选 JSON（symbol / cov_override / pool 合法性） |
| `load_baseline_points(symbol, root, cov) -> list[dict]` | 读 nocov / 协变量基线点 |
| `compute_protocol_fingerprint(...) -> str` | 算七组件指纹（`:293`） |
| **`build_summary(...) -> dict`** | **核心**：逐点聚合 + DM + gate + effective_min，产出 verdict（`:447`） |
| `compute_effective_min(min_dir_acc=0.52, baseline_dir_acc=None) -> float` | 自适应门槛（`:697`） |
| `gate(s, min_n=350, min_n_eff=50, min_dir_acc=0.52, ...) -> dict` | 硬门判定（`:703`） |
| `effective_sample_size(n, horizon, step, ...) -> float` | Bartlett n_eff（`:720`） |
| `active_mask_metrics(points) -> dict` | 零变动剔除后的方向样本量 |

---

## 已知缺口（2026-10-05 核实）

**跨 run 反馈通道未实现** —— `experiments/run_*/memory/research_memory.jsonl` 每个 run 都创建，但**最新 run 为 0 字节**；代码里没有「读上一 run 的 research_memory 并注入下一 run 提示词」的逻辑。
后果：peer 每次提案都是**盲猜**——它只知道本 run 内 materialize 的 `known_verdicts.inc.md`（当前轮物化），不知道历史 cycle 的实际结果。
`shared_store.db` 存在但是 Praxist 运行时内部状态库（session / frontier / gems），**不是**面向 peer 的跨 run 反馈通道。

闭合方案见 `docs/superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md`（D1–D4）与 `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis.md`。

---

<!-- MANUAL: -->
