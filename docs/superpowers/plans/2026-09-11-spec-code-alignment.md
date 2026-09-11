# Spec–代码对齐审核计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This is an **audit**: write reports only. Do not edit production code, SCHEMES, `.env*`, or verdicts.

**Goal:** 把仓里每一份 spec 的每条仍有效设计对上活代码；设计已被后续合同废掉的，只标「失效 + 取代来源」，不当代码缺口。

**Architecture:** 先判定有效/失效，再只对有效条款做点名对齐。上一轮 Task 3 只做了文件级分类，本计划补条款级对齐。

**Tech Stack:** 活仓 WSL `/home/abug/timesfm`；Python 3.11；只读。

**Spec:** 本计划的权威链（后者不能推翻前者的磁盘事实）：
1. `STATE.md` + `config/prediction_scheme.py` + `config/backtest_config.py` + `config/praxist_task.yaml` + `loop-constraints.md`
2. `docs/spec_hypothesis_driven_fast_loop_20260908.md`（方案 A）+ `docs/praxist.md`
3. 仍有效的 superpowers spec 接口（hardening SPEC-004…013、compile-skip）
4. 早期协变量 spec：仅当其机制仍在 `SCHEMES` 或 `cascade/features.py` 生产路径上

## Global Constraints

- 活仓 `/home/abug/timesfm`。用 `wsl -d Ubuntu-22.04 -- bash -c "..."`。禁止 `D:\FlyBuddy\timesfm`。
- 只写 `docs/superpowers/reports/2026-09-11-audit/spec-alignment/`。
- **设计失效**的唯一合法理由：后续更高权威明确废止（STATE 结案、loop-constraints 方案 A、后一份 spec 的 Non-Goals / 取代声明、0/N GO 关轨）。仅「状态栏待审核 / 日期早」不够。
- **设计仍有效**即使文件标历史：机制还在生产路径（例如 `calendar_cyclical` 仍在 SCHEMES）就必须对齐。
- 对齐判定四种：`对齐` / `部分对齐` / `缺口`（有效设计代码没有或写反） / `失效`（不评代码对错）。
- 每条缺口：spec 路径+行、代码路径+行或「仓内无此符号」、严重度。Critical 仅当有效 spec 与活生产路径相反且会改错信号/硬门/收割。
- 不启动 Praxist，不改代码。
- 上一轮已证实、可直接引用：IC=`2×|dir_acc−0.5|`；`gate()` 不含 EV；方案 A peer 不评估；`get_safe_daily` 未接 `DailyModel.predict`；SPEC-011 日线 `raw_close` 短路。不要重审整仓，但本任务必须把这些挂到对应 spec 条款。
- 忽略同名 `.txt` 副本当合同（Task 3 已记漂移）。
- 现行 SCHEMES `covariate_type` 集合：`ao_accel, calendar_cyclical, ha_body, hourly_slope, reversal_shadow, rsi_state`；组合里还有 `oi`。features 另有 vor/ccl/crack/nvi/qstick/vwap/stddev 等池内实现。

## Spec 清单（必须每份有一行结论）

`docs/superpowers/specs/`：
1. `2026-09-10-system-hardening-design.md`（SPEC-004…013）
2. `2026-09-09-compile-skip-phase1-design.md`
3. `2026-09-02-praxist-three-loop-design.md`
4. `praxist_control_plane.md`
5. `ACCEPT_flock_20260906.md`
6. `2026-07-28-covariate-optimization-design.md`
7. `2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md`
8. `2026-07-29-followup-4-directions-optimization-design.md`
9. `2026-07-29-phase4-calendar-cyclical-design.md`
10. `2026-07-31-phase8-crack-spread-design.md`
11. `2026-08-04-alpha2-phase1-baseline-gate-design.md`
12. `2026-08-04-phase9-toxic-variety-design.md`
13. `2026-08-05-a2-p1-dense-cache-resume-design.md`
14. `2026-08-05-a2-p1-market-vectorize-design.md`
15. `2026-08-05-a2-p1-runtime-redesign.md`
16. `2026-08-22-phase15-new-covariates-design.md`

仓外但必须当 spec：
17. `docs/spec_hypothesis_driven_fast_loop_20260908.md`

仓外、仅判定失效/残留：
18. `docs/praxist_directive_design.md`
19. `docs/praxist_integration_plan.md`
20. `docs/praxist_peer_evaluation_fix.md`

critical-fixes SPEC-001…003：仓内无独立 spec 文件。在 Task 1 记「无文件」，条款对齐并入 Task 2（`get_safe_daily` / 前视）用 git `cd29bb6` 与代码，不发明一份不存在的 spec。

---

### Task 1: 有效/失效判定表（全清单）

**Files:**
- Read: 上表 1–20 的状态栏 + 取代声明；`STATE.md` 中 A2-P2 / Phase 13/15 / Praxist 方案 A；`loop-constraints.md` 预注册段
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/task-1-validity.md`

**Interfaces:**
- Produces: 每份 spec 一行：`仍有效` / `部分有效` / `设计失效`，失效必须引用杀手（文件:行）

- [ ] **Step 1:** 对 1–20 各写一行判定。
- [ ] **Step 2:** 对「部分有效」拆出仍有效条款 vs 失效条款（不要整份扔掉）。
- [ ] **Step 3:** 写报告。预置嫌疑（必须证实或证伪，不是结论）：
  - 09-02 的 diagnostic 收割 = 失效（方案 A）；慢环唯一写 verdict / daily 缓存 / 429 resume = 仍有效
  - A2-P2 残差叠加 / Track B = 失效（STATE 0/5 GO）
  - A2-P1 LGBM 作为生产模型 = 失效；A2-P1 评价秤/JSONL 形态若仍被工具使用 = 部分有效
  - Phase 15「应固化 NVI/QSTICK/VWAP」= 失效（0 GREEN）；`_calc_stddev` 等实现仍在 features = 实现对齐任务，不是固化合同
  - calendar / reversal_shadow / rsi_state / hourly_slope 设计 = 仍有效（在 SCHEMES）
  - crack_spread 设计 = 若 SCHEMES 未用但 `calc_crack_spread` 仍被池/扫描调用，标「池内仍有效，非 SCHEMES 合同」

---

### Task 2: Hardening SPEC-004…013 条款对齐

**Files:**
- Read: `docs/superpowers/specs/2026-09-10-system-hardening-design.md` 每个 `### SPEC-`
- Read: 各 SPEC 点名的 py（evaluator、aligned_slow_loop、prediction_scheme、features、daily_model、copilot、data_store、knowledge_base）
- Read: `tests/test_system_hardening.py`
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/task-2-hardening.md`

**Interfaces:** Consumes Task 1（hardening = 仍有效接口）

- [ ] 每个 SPEC 一张表：条款原文摘要、代码符号、测试、判定。
- [ ] 已知必须核对：SPEC-004 n_eff 不进 gate；SPEC-005 Col 0 隔离；SPEC-008 保证金 MaxDD 输入是否净 PnL（上一轮 I-17）；SPEC-007 cosine 默认关；SPEC-011 raw_close 短路；SPEC-012 `_compute_direction_v2` 只做副标签；SPEC-006 不改 SCHEMES。
- [ ] 写报告。

---

### Task 3: Compile-skip + 效率五条

**Files:**
- Read: `docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md` §3–§9
- Read: `cascade/daily_model.py` `ensure_compiled`；`hourly_model.py`；F-001/010/011/005 点名文件
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/task-3-compile-skip.md`

- [ ] 指纹字段、跳过条件、四条无架构分叉、验收框 vs 代码/测试。
- [ ] 写报告。

---

### Task 4: 方案 A + 三环骨架（有效条款）与失效条款

**Files:**
- Read: `docs/spec_hypothesis_driven_fast_loop_20260908.md` 全文
- Read: `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md`（按 Task 1 拆开的条款）
- Read: `scripts/praxist_supervisor.py` harvest/start/429；`scripts/aligned_slow_loop.py`；`task_FM` prompts
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/task-4-three-loop.md`

- [ ] 方案 A 每条硬规则 → 代码/测试。
- [ ] 09-02 有效骨架 → 代码。失效 diagnostic 条款列出但不评「缺口」。
- [ ] 写报告。

---

### Task 5: 控制面 + flock

**Files:**
- Read: `praxist_control_plane.md`, `ACCEPT_flock_20260906.md`
- Read: mem_guard / supervisor flock 实现
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/task-5-control-plane.md`

- [ ] 2.5GiB / slots=1 / 429 / 启停审批：对齐或文档过期。
- [ ] 15GiB、peer eval 硬顶：标失效或文档缺口，不要改代码去满足 15GiB。
- [ ] 写报告。

---

### Task 6: 仍有效的协变量 spec（生产或池）

**Files:**
- Read: phase4 calendar、phase5-6 shadow/basis、followup-4、phase8 crack、phase9 toxic、covariate-optimization、phase15（只审仍存在的实现，不审「应固化」）
- Read: `cascade/features.py` 对应函数；`config/prediction_scheme.py`；`config/crack_spread_pairs.py`
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/task-6-covariates.md`

- [ ] 每个 spec：设计公式/输入窗口/防穿越 vs 函数实现。SCHEMES 未采用不等于实现失效。
- [ ] 「应固化到 SCHEMES」类目标若被 STATE 否决 → 失效，不报代码缺口。
- [ ] 写报告。

---

### Task 7: Alpha2 与已关轨 spec

**Files:**
- Read: alpha2-phase1、dense-cache、market-vectorize、runtime-redesign；STATE A2-P1/P2
- Read: `scripts/a2_p1_*.py` 是否仍被生产入口 import（copilot / cascade_predict / monthly_backtest / supervisor）
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/task-7-alpha2.md`

- [ ] 生产入口若不再调用：整份标失效 + 残留脚本清单。
- [ ] 若评价合同被 A2-P1 改过且仍被 monthly/slow loop 使用：那些条款改走 Task 2/4，不要在失效 spec 下报缺口。
- [ ] 写报告。

---

### Task 8: 总对齐矩阵

**Files:**
- Read: task-1…7 报告
- Create: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/SUMMARY.md`

- [ ] 20 份 spec 一行总表：有效/失效、对齐/部分/缺口计数。
- [ ] 有效但缺口的条款按严重度列出（去重上一轮已报的 CC-1 等，互相引用）。
- [ ] 失效 spec 只保留杀手引用 + 若代码仍实现死设计（例如 diagnostic 入口仍挂着）标「残留能力面」——引用上一轮 I-03，不新发明。
- [ ] 不改代码。建议分「改文档横幅」vs「有效缺口需另开 plan」。

---

## Execution notes

Task 1 先完成（或与 2–7 并行但 2–7 必须自己写有效/失效判定，不得把失效条款当缺口）。Task 8 最后。
并行域：hardening / compile-skip / three-loop / control-plane / covariates / alpha2。
不走 finishing-a-development-branch 的 push。
