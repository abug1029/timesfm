# FM_a 全系统文档+代码审核计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan is an **audit**, not a feature implementation: workers write reports, they do **not** edit production code, SCHEMES, models, or `.env*`.

**Goal:** 先审文档（合理性、内部矛盾、过期、漏洞），再按文档合同审生产代码，输出按严重度排序的证据型审核报告，不自动改代码、不 push、不启动 Praxist。

**Architecture:** 活仓是 WSL `/home/abug/timesfm`（`wsl -d Ubuntu-22.04 -- bash -c "..."`）。文档先按权威链对账，再按子系统把代码对照合同。每个任务产出独立报告文件；最后一份总报告只综合证据，不发明新结论。

**Tech Stack:** Python 3.11（`.praxist-venv`）、TimesFM 2.5、TqSdk、SQLite、Praxist 0.5.0、pytest。

**Spec:** 本审核的合同权威（冲突时按此顺序，后者不得推翻前者的磁盘事实）：
1. `STATE.md` + 磁盘产物（`task_FM/config/aligned_verdicts.jsonl`、`data/cache/supervisor_state.json`、回测 JSONL）
2. `loop-constraints.md` + `config/praxist_task.yaml` + `config/backtest_config.py` + `config/prediction_scheme.py`
3. `docs/praxist.md` + `docs/runbook_praxist_three_loop.md` + `docs/product_positioning.md` + `docs/validation_criteria.md`
4. `docs/system_design.md`
5. `docs/superpowers/specs/`（现行以 2026-09-10 hardening 与已 merge 的 critical-fixes 为准）
6. `docs/research/` 与更早 spec/plan（历史，可能已落地或已作废）

## Global Constraints

- 活仓：`/home/abug/timesfm`。禁止把 `D:\FlyBuddy\timesfm` 当真相源。禁止读/改 `.praxist-venv` 里的 Praxist 源码。
- 只读生产代码。允许写入：`docs/superpowers/plans/2026-09-11-full-system-audit.md`（本文件）、`docs/superpowers/reports/2026-09-11-audit/` 下的报告。禁止改 `config/prediction_scheme.py`、`cascade/daily_model.py`、`cascade/hourly_model.py`、`cascade/features.py`、`data/config.py`、`.env*`、`aligned_verdicts.jsonl`。
- 不启动 supervisor / praxist / 全量 walk-forward。可以跑已有单测和只读脚本。
- 每条 finding 必须带：文件路径+行号或命令输出、严重度（Critical / Important / Minor）、文档合同原文、代码/磁盘事实、建议（只建议，不落地）。
- IC 合同原文（`loop-constraints.md`）：`ic=2×|dir_acc−0.5|`，不是 Pearson 相关。EV 文档有两套单位（价格点 vs EV_ratio），见 `docs/AGENTS.md` Note on EV unit。
- 可交易方向合同（`docs/product_positioning.md` CF-01 A）：`sign(weighted_1H − base)`，日线斜率只是副标签。
- 硬门合同：n≥350 且 IC≥0.05 且扣滑点 EV>0；慢环是唯一验证器。
- 不要把「文档过期」写成「代码 bug」，也不要把「已修但文档没改」写成「仍存在的致命缺陷」。先对 git 时间线。
- 探索期已观察到、必须在对应任务里证实或证伪的嫌疑（不是结论）：
  - `docs/system_design.md` §5.1/§8 用日线斜率当主方向，可能与 CF-01 A 冲突。
  - `docs/system_design.md` §7.1 把 IC 写成 `corr(预测, 实际)`，可能与 `loop-constraints.md` 冲突。
  - `docs/system_design.md` §7.3 `gate_pass` 含 EV>0，而 `docs/praxist.md` 写硬门只判 n+ic、`i_oi` 亏钱仍 `gate_pass=True`。
  - `docs/research/slow_loop_evaluation_points_research.md` 仍写「前视偏差必须立即修复 / STEP=24」；git 已有 `feat/critical-fixes-v1.4`、`get_safe_daily`、评估网格重构；`config/backtest_config.py` 已是 `STEP=2`、`EVAL_WINDOW_BARS=1200`。
  - 三环原始 spec 仍写 peer diagnostic 筛选；现行合同是方案 A（peer 不评估）。
  - SS 示例协变量：`system_design.md` 写 `calendar_cyclical`，Praxist 快照写过门的是 `ss_vor`。
- 生产代码范围（「所有代码」在本计划中的边界）：`cascade/`（21 py）、`data/`、`config/`、`scripts/` 生产入口、`tests/`、`task_FM/evaluations/` + `task_FM/config/` + `task_FM/roles/` + `task_FM/audit_rules/`。排除：`.venv` / `.praxist-venv`、`task_FM/experiments/` 跑次产物、一次性 `audit_futures*.py` / `fix_*.py` 除非仍被生产路径 import。
- 报告目录：`docs/superpowers/reports/2026-09-11-audit/`。每个任务一个 `task-N-report.md`。总报告 `SUMMARY.md`。
- 子代理必须用 `wsl -d Ubuntu-22.04 -- bash -c "..."` 读仓。Windows 短路径规则不适用于 WSL 内部。

---

## File map（本计划会创建的文件）

- Create: `docs/superpowers/reports/2026-09-11-audit/task-1-doc-authority.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-2-system-design.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-3-superpower-specs.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-4-research-docs.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-5-data-lookahead.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-6-cascade.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-7-eval-gates.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-8-three-loop.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-9-copilot-vol.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-10-tests.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/SUMMARY.md`

---

### Task 1: 文档权威链与矛盾矩阵

**Files:**
- Read: `docs/README.md`, `docs/AGENTS.md`, `AGENTS.md`, `CLAUDE.md`, `STATE.md`, `loop-constraints.md`, `docs/praxist.md`, `docs/product_positioning.md`, `docs/system_design.md`（目录与日期）, `docs/module_freeze.md`, `docs/validation_criteria.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-1-doc-authority.md`

**Interfaces:**
- Consumes: 无
- Produces: 权威链表；「谁覆盖谁」裁决；文档日期/状态字段过期清单；给 Task 2–4 的必查矛盾列表

- [ ] **Step 1: 列出文档角色**

对每份根/docs 人类文档标：canonical_state / derived_view / 现行合同 / 历史方案 / 过期。至少覆盖上表。

- [ ] **Step 2: 扫日期与状态字段**

记录每份文档的「最后更新 / 状态 / 当前生产姿态」日期。对照 `git log -1 --format=%ci` 与 `STATE.md` 顶部日期。任何「当前」口径早于 2026-09-09 且未被后文取代声明覆盖的，标 Important。

- [ ] **Step 3: 写矛盾矩阵**

至少用证据确认或证伪这些对（每行：文档A原文+文档B原文+你的判定）：
1. 可交易方向：日线斜率 vs 加权 1H
2. IC：Pearson vs `2×|dir_acc−0.5|`
3. gate_pass 是否含 EV
4. SS 主协变量：calendar_cyclical vs vor vs `SCHEMES`
5. 硬门 n：396 vs 600 vs STEP=2 后的实际 n
6. Praxist peer：评估器 vs 假设作者
7. Vol gating：默认 OFF vs system_design 熔断章节读起来像在生产路径上

- [ ] **Step 4: 写报告**

报告必须含：权威链、矛盾矩阵、过期文档清单、不在本次「先审文档」范围内但会误导执行者的文件（例如 `docs/praxist_integration_plan.md` 的 `/root/timesFM_fu`）。

---

### Task 2: 审核 `docs/system_design.md` 合理性与漏洞

**Files:**
- Read: `docs/system_design.md` 全文, `docs/product_positioning.md`, `cascade/signal_contract.py`, `cascade/daily_model.py`, `cascade/hourly_model.py`, `cascade/vol_risk_filter.py`, `config/prediction_scheme.py`（只读 SCHEMES 字段，不改）, `scripts/copilot.py`（方向与建议相关函数）
- Create: `docs/superpowers/reports/2026-09-11-audit/task-2-system-design.md`

**Interfaces:**
- Consumes: Task 1 矛盾矩阵
- Produces: system_design 逐节（§1–§10）「合理 / 过时 / 与代码不符 / 内部自相矛盾」表

- [ ] **Step 1: 逐节对照代码符号**

对文档里出现的每个函数/类名（`DailyResult`, `HourlyResult`, `_compute_direction`, `signal_weight`, `confidence_band`, `ThrPolicy`, `apply_neutral_override_v2`, `gate_pass`, `craft_advisory`）在仓里 `grep` 是否存在、签名是否一致。不存在或签名已变 = Important（文档漏洞）。

- [ ] **Step 2: 核对关键数值**

核对：context 250/480、horizon 22/24、trend_threshold_pct、decay、stars 列表、SS 协变量、2 星集合、Vol 默认 OFF、v2 neutral override。每一项给代码位置。

- [ ] **Step 3: 合理性（不是风格）**

只问会让人按错系统的问题：
- 把领航员系统画成「开平仓建议」是否诱导自动化误解
- 方向判断若与 CF-01 A 相反，文档是否会让执行者改错信号
- 示例代码 `horizon_slope * 100` 是否单位错误
- 分位数 10 列假设是否与 TimesFM 实际输出列对齐
- 「防穿越」原则 vs 研究文档已确认的日内日线穿越（若 critical-fixes 已修，本节应写「文档未声明已修」而不是「代码仍穿越」——穿越本身归 Task 5）

- [ ] **Step 4: 写报告**

按 § 列出 findings。Critical 仅用于：按该文档执行会改错生产信号、硬门或数据截断。

---

### Task 3: 审核 superpowers specs / plans 过期与冲突

**Files:**
- Read: `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md`, `docs/superpowers/specs/praxist_control_plane.md`, `docs/superpowers/specs/2026-09-10-system-hardening-design.md`, `docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md`, `docs/runbook_praxist_three_loop.md` 的 Spec 绑定解释（若有）, `docs/spec_hypothesis_driven_fast_loop_20260908.md`
- Skim 标题+状态栏：其余 `docs/superpowers/specs/*.md`（忽略同名 `.txt` 副本，在报告里记一笔「md/txt 双份」）
- Read: `docs/superpowers/plans/2026-09-10-system-hardening.md` 头部完成态；`git log --oneline -20`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-3-superpower-specs.md`

**Interfaces:**
- Consumes: Task 1 权威链
- Produces: 每份现行 spec 的「仍约束代码 / 已被取代 / 与 runbook 冲突」标签

- [ ] **Step 1: 分类全部 spec**

表：文件、日期、状态字段、是否已被更新文档取代、是否已 merge（用 git log / CLAUDE.md hardening 能力表交叉）。

- [ ] **Step 2: 三环 spec vs 方案 A**

逐条对比 2026-09-02 spec 的「diagnostic 筛选 / 诊断幸存者」与 `docs/praxist.md` + `docs/spec_hypothesis_driven_fast_loop_20260908.md`。列出仍被执行者当现行合同的句子。

- [ ] **Step 3: Hardening spec vs 已落地**

对照 CLAUDE.md / git：SPEC-004…013 哪些已在 master。文档若仍写「待启动 / 依赖 critical-fixes」而 git 已 merge，标过期。抽 2 个 SPEC 的接口名到代码里点名验证（其余留给 Task 6/7）。

- [ ] **Step 4: 写报告**

重点是「哪份 spec 现在还敢当合同」。不要重写 spec。

---

### Task 4: 审核 research 文档 vs 磁盘/代码

**Files:**
- Read: `docs/research/slow_loop_evaluation_points_research.md` 全文
- Read: `docs/audit_system_efficiency_20260908.md`（预测链性能债，只核对「已落地/未动」清单是否还对）
- Read: `config/backtest_config.py`, `data/data_store.py`（BacktestDataStore / get_safe_daily 或同等符号）, `scripts/monthly_backtest.py`（eval_indices / STEP）
- Read: `git log --oneline --all --grep='lookahead\|前视\|get_safe_daily\|critical-fixes'`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-4-research-docs.md`

**Interfaces:**
- Consumes: Task 1 矛盾 4/5；研究文档的三个隐患
- Produces: 每个研究主张的现状：仍成立 / 已修复但文档未改 / 从未成立

- [ ] **Step 1: 主张清单**

从 research 文档抽出带断言的句子（STEP=24 导致 396 点；evaluator 硬顶 500；日内前视已确认；STEP=2 建议；日历先验未验证；RevIN 未验证）。每句一行。

- [ ] **Step 2: 对照代码与 git**

对每句给出：当前代码值/函数名、相关 commit、判定。特别是 `get_safe_daily` 是否存在、谁调用、BacktestDataStore 是否仍 `end_date=cutoff_day` 含当日。

- [ ] **Step 3: 写报告**

若前视已修：Critical 是「研究文档仍号召立即修复」这种过期号召，不是「代码仍穿越」。若未修：Critical 留给 Task 5 的代码证据。

---

### Task 5: 数据管线与前视/幽灵 K 线

**Files:**
- Read: `data/data_store.py`, `data/future_bar_guard.py`, `data/tqsdk_fetcher.py`, `data/trading_calendar.py`, `data/indicator_calculator.py`, `cascade/data_validator.py`, `data/config.py`（只读）, `tests/test_future_bar_guard.py`, `tests/test_daily_freshness.py`, `tests/test_ensure_data_result.py`, `tests/test_holidays.py`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-5-data-lookahead.md`

**Interfaces:**
- Consumes: Task 4 关于前视的主张现状
- Produces: 生产路径（copilot / cascade_predict / monthly_backtest）各自的日线截断契约

- [ ] **Step 1: 画出三条生产路径的日线读取**

对 `scripts/copilot.py`、`scripts/cascade_predict.py`、`scripts/monthly_backtest.py` 跟踪到 `get_main_continuous` / `get_safe_daily` / `BacktestDataStore`。每条路径写：cutoff 定义、是否含当日日线、1H 是否截到 cutoff。

- [ ] **Step 2: 幽灵 K 与补采**

核对 `run_guard` 是否仍是唯一批量入口；`ensure_fresh_data` 是否在预测前调用；失败时是否静默用脏数据。

- [ ] **Step 3: 换月/复权（SPEC-011）**

确认 hardening 的截面后复权是否在回测读取路径上，还是只在某一条路径。

- [ ] **Step 4: 写报告**

Critical：仍存在的、会影响回测 PF 或实盘建议的穿越。Important：测试未覆盖的路径分叉。

---

### Task 6: 级联预测核心

**Files:**
- Read: `cascade/daily_model.py`, `cascade/hourly_model.py`, `cascade/features.py`, `cascade/signal_contract.py`, `cascade/walk_forward.py`, `config/prediction_scheme.py`（只读）, `tests/test_signal_contract.py`, `tests/test_compile_skip.py`, `tests/test_calendar_cyclical.py`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-6-cascade.md`

**Interfaces:**
- Consumes: Task 2 符号表；CF-01 A
- Produces: 日线→1H→方向 的真实合同（函数名+单位）

- [ ] **Step 1: 方向与权重**

确认 `position_from_forecast` / `_compute_direction` / `_compute_direction_v2` / `signal_weight` / cosine rolloff 谁在生产路径上。对照 product_positioning 与 system_design。

- [ ] **Step 2: 协变量与防穿越**

features 构建 context vs horizon：哪些协变量在 horizon 段用未来可知信息（日历），哪些会偷未来（OI/CCL 若 fill 了 cutoff 之后）。点名函数。

- [ ] **Step 3: 模型加载与 compile-skip**

TimesFM 路径是否走 `data.config.get_timesfm_model_path()`；compile-skip 是否只在声称的路径生效。

- [ ] **Step 4: 写报告**

---

### Task 7: 评估指标、硬门、回测入口

**Files:**
- Read: `cascade/evaluation_metrics.py`, `config/backtest_config.py`, `config/praxist_task.yaml`, `scripts/monthly_backtest.py`, `scripts/aligned_slow_loop.py`（gate / harvest 写入）, `task_FM/evaluations/fm_eval/evaluator.py`, `docs/validation_criteria.md`, `tests/test_evaluation_metrics_contract.py`, `tests/test_backtest_cutoff.py`, `tests/test_verdict_registry.py`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-7-eval-gates.md`

**Interfaces:**
- Consumes: IC/EV/gate 合同；Task 1 矛盾 2/3/5
- Produces: 真实公式、单位、gate_pass 布尔条件、主回测入口是否仍是 monthly_backtest

- [ ] **Step 1: 公式对账**

对 PF、EV、EV_ratio、IC、DirAcc、MaxDD（名义 vs 保证金 / stride=12）各找唯一实现。核对 system_design §7 示例是否错。

- [ ] **Step 2: gate_pass**

慢环写入 `aligned_verdicts.jsonl` 时 `gate_pass` 的实际条件。用一份真实 verdict（如 `ss_vor`、`i_oi`）验证文档里「亏钱仍过硬门」是否仍在。

- [ ] **Step 3: 采样网格**

`STEP`、`EVAL_WINDOW_BARS`、`CONTEXT_BARS`、`HORIZON` 的实际值；evaluator 硬顶；goal.yaml `aligned_max_points`。计算理论 n，对照磁盘 verdict 的 n。

- [ ] **Step 4: 写报告**

---

### Task 8: Praxist 三环代码

**Files:**
- Read: `scripts/praxist_supervisor.py`, `scripts/aligned_slow_loop.py`, harvest 相关（supervisor 内或独立模块）, `scripts/praxist_goal.yaml`, `task_FM/evaluations/fm_eval/run.py`, `task_FM` 下 prompts/roles（确认禁止跑评估）, `tests/test_supervisor.py`, `tests/test_harvest_proposals.py`, `tests/test_praxist_task_contract.py`, `tests/test_goal_dsl.py`, `tests/test_aligned_slow_loop.py`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-8-three-loop.md`

**Interfaces:**
- Consumes: `docs/praxist.md` 合同；方案 A spec
- Produces: 快/慢/监督环是否仍满足「peer 不评估、慢环唯一写 verdict、429 resume 同一 run」

- [ ] **Step 1: 合同点名**

对 praxist.md 的每一条硬规则（禁止 fm_eval、禁止加载 TimesFM、schema、mechanism≥40、survivors_per_cycle=3、phase 互斥、aligned_verdicts 唯一写者）到代码/测试找执行点。缺测试 = Important。

- [ ] **Step 2: 已知瑕疵**

`i_oi` gate_pass vs EV；materializer `known_verdicts.inc.md` 是否仍误导 peer。给出现状。

- [ ] **Step 3: 写报告**

不要诊断当前是否在跑（允许读 `supervisor_state.json` 只作快照，不改）。

---

### Task 9: Copilot、纸面、Vol

**Files:**
- Read: `scripts/copilot.py`, `cascade/vol_risk_filter.py`, `cascade/live_ledger.py`, `scripts/paper_loop.py`, `docs/copilot.md`, `docs/paper_trading.md`, `docs/vol-risk.md`, `docs/module_freeze.md`, `tests/test_copilot_advisory.py`, `tests/test_vol_risk_filter_v2.py`, `tests/test_vol_threshold_contract.py`, `tests/test_paper_loop.py`, `tests/test_live_ledger.py`, `tests/test_signal_mode_mutex.py`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-9-copilot-vol.md`

**Interfaces:**
- Consumes: 产品红线（永不压平、Vol 预警-only、可交易方向=加权1H）
- Produces: 盘中路径是否仍守红线

- [ ] **Step 1: 压平互斥**

确认 copilot 路径不能打开 Neutral override；cascade_predict 默认 OFF；`--vol-filter-neutral` / `FM_VOL_FILTER` 只影响声明过的入口。

- [ ] **Step 2: 建议文案 vs 信号**

`craft_advisory` 或现行函数是否用日线方向当主句，从而和加权 1H 对不上。

- [ ] **Step 3: 写报告**

---

### Task 10: 测试是否锁住合同

**Files:**
- Read: `tests/AGENTS.md`（若有）, `tests/` 文件名清单 vs Task 5–9 声称的合同
- Run: `wsl -d Ubuntu-22.04 -- bash -lc 'cd /home/abug/timesfm && . .praxist-venv/bin/activate && python -m pytest tests/test_signal_contract.py tests/test_evaluation_metrics_contract.py tests/test_future_bar_guard.py tests/test_harvest_proposals.py tests/test_praxist_task_contract.py tests/test_system_hardening.py -q --tb=no'`
- Create: `docs/superpowers/reports/2026-09-11-audit/task-10-tests.md`

**Interfaces:**
- Consumes: Tasks 5–9 的合同清单
- Produces: 有测试锁 / 无测试锁 / 测试锁的是过期合同

- [ ] **Step 1: 合同-测试矩阵**

行=硬合同（方向、IC 公式、gate、前视、peer 不评估、Vol OFF），列=测试文件。空单元格 = 缺口。

- [ ] **Step 2: 跑上面的子集**

记录 pass/fail。失败不是本计划的修复任务，记入 SUMMARY。不要扩跑全量 monthly。

- [ ] **Step 3: 写报告**

---

### Task 11: 总报告与交叉验证

**Files:**
- Read: `docs/superpowers/reports/2026-09-11-audit/task-*-report.md` 以及本计划里实际写的 `task-N-*.md`
- Create: `docs/superpowers/reports/2026-09-11-audit/SUMMARY.md`

**Interfaces:**
- Consumes: Task 1–10 全部 findings
- Produces: 去重后的严重度表、文档债 vs 代码债分流、建议修复顺序（仍不改代码）

- [ ] **Step 1: 去重合并**

同一缺陷若文档和代码各报一次，合并为一条，同时标注「文档 / 代码 / 两者」。冲突的子代理结论：用磁盘事实和 git 裁决，在 SUMMARY 写 Ruling。

- [ ] **Step 2: 排序**

Critical → Important → Minor。Critical 只保留：错误信号、数据穿越、硬门被绕过、verdict 被非慢环写入。文档过期默认最高 Important，除非它会直接导致改错生产路径。

- [ ] **Step 3: 建议修复顺序**

分两列：只改文档；需要改代码（需另开 plan + 人工确认高风险路径）。不要在本任务改代码。

- [ ] **Step 4: 写 SUMMARY.md**

给人类看：一页结论 + 完整 finding 表 + 每条证据指针。

---

## Execution notes

- 先 Task 1–4（文档，可并行），再 Task 5–10（代码，可并行；5 依赖 4 的前视判定，若 4 未完成则 5 自己重做 git 时间线），最后 Task 11。
- 每个任务的「实现者」是审核子代理：只写报告。任务审核者检查：是否引用了行号/命令、是否把过期文档当成活 bug、是否越权改了代码。
- 本计划不走 finishing-a-development-branch 的 merge/push。报告留在仓内，等用户决定是否提交。
