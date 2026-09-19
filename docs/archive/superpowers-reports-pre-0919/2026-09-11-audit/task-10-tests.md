# Task 10：测试是否锁住合同

- 任务：全系统审核计划 Task 10（只读，写报告）
- 简报：`.superpowers/sdd/2026-09-11-full-system-audit/task-10-brief.md`
- 仓：WSL `/home/abug/timesfm`（venv `.praxist-venv`）
- 审核日：2026-09-11
- 消费：Tasks 5–9 已裁定的 7 条硬合同
- 不改：生产代码、测试、SCHEMES；不 push；不启动 Praxist
- 判定三态：**有测试锁现行合同** / **无测试锁（缺口）** / **测试锁的是过期合同**

**结论先说：** 指定子集 **123 passed, 1 failed, 3 skipped**（10.68s）。唯一失败是 `test_daily_includes_cutoff_calendar_day`：10:00 cutoff 时期望含当日日线，活代码 `hour>=15` 才含，得到 `{'2026-03-09'}`。这是**过期合同被测试锁住且今天会红**，不是代码 bug。七条硬合同里，只有「可交易方向 = `position_from_forecast` 加权 1H」在**函数层**被锁住；入口调用、Copilot 分叉、IC 公式、负 EV 仍过门、实盘日线裸读、peer 禁评估、Vol 默认 OFF、慢环唯一写 verdict，全部没有能在今天失败的测试。缺口不是红测，是绿测给不了的信心。

---

## 0. pytest 现场

命令（venv `.praxist-venv`）：

```bash
python -m pytest tests/test_signal_contract.py tests/test_evaluation_metrics_contract.py \
  tests/test_future_bar_guard.py tests/test_harvest_proposals.py \
  tests/test_praxist_task_contract.py tests/test_system_hardening.py \
  tests/test_backtest_cutoff.py tests/test_daily_freshness.py \
  tests/test_copilot_advisory.py tests/test_vol_threshold_contract.py \
  tests/test_signal_mode_mutex.py -q --tb=line
```

**摘要行：`1 failed, 123 passed, 3 skipped in 10.68s`**

收集：127 tests（123 + 1 + 3）。

| 结果 | 用例 | 判定 |
|------|------|------|
| **FAIL** | `tests/test_backtest_cutoff.py::TestBarExactCutoff::test_daily_includes_cutoff_calendar_day` | 过期合同。断言 10:00 含 `2026-03-10`；活 `BacktestDataStore.get_main_continuous` 在 `hour<15` 把 `end_date` 推到前一日历日。错误原文：`AssertionError: '2026-03-10' not found in {'2026-03-09'}`。Task 4/5 已复现同一方向。 |
| SKIP | `test_vol_threshold_contract.py:104` `test_paths_are_absolute_under_fm_root` | 缺 trained vol pkl（`run train_vol_risk_sector`） |
| SKIP | `:113` `test_resolve_independent_of_cwd` | 同上 |
| SKIP | `:128` `test_black_missing_pkl_falls_back_to_r0_with_source` | R0 fallback 不可用 |

失败不是本计划的修复任务。不要按这只红测去把 10:00 改回含当日。

---

## 1. 合同 × 测试矩阵

行 = Tasks 5–9 硬合同。列 = 指定子集里真正碰到该合同的文件。空单元格 = 缺口。判定只看「今天跑会不会因为合同被破坏而红」。

| # | 硬合同（现行） | 子集内相关文件 | 锁的是什么 | 判定 |
|---|----------------|----------------|------------|------|
| 1 | 可交易方向 = `position_from_forecast` 加权 1H；`cascade_predict` / `monthly_backtest` 走它；**Copilot 不走**（走 `_compute_direction_v2`） | `test_signal_contract.py`；`test_copilot_advisory.py`（无关）；`test_system_hardening.py`（锁日线副标签本身）；`test_signal_mode_mutex.py`（CF-06 短段互斥，不是方向入口） | 函数：日线 0.0005 分数/天 → regime 中性、仓位仍看多。**不**断言 `scripts/copilot.py` / `cascade_predict.py` / `monthly_backtest.py` 的 import。Copilot 卡面主方向无对等用例。 | **函数层有锁。入口无锁。Copilot 分叉 = 缺口，不是失败测试。** 若写「Copilot 必须调 `position_from_forecast`」，今天会红。 |
| 2 | IC = `2*\|dir_acc-0.5\|`；`gate_pass` = n≥350 且 IC≥0.05，**不含 EV**；负 EV 仍可 `gate_pass=true` | `test_evaluation_metrics_contract.py`（MaxDD / DirAcc 边角，无 IC、无 gate）；`test_system_hardening.py`（n_eff、stride MaxDD；`sync_slow_loop_status` 用的是 `gate_pass=False` 且 ev<0） | 秤的回撤与 DirAcc 零变动。**没有** `assert ic == 2*abs(dir_acc-0.5)`。**没有** `gate(n=400, dir_acc=0.53, ev=-2) is True`。 | **无测试锁。** 子集外 `test_praxist_fm_evaluator.py:23-28` 只测 n 门槛，默认 ev=0.9、diracc=0.54（IC=0.08 碰巧过）。子集外 `test_aligned_slow_loop.py:95` `ic==0.1` 且 `dir_acc=0.55` 是唯一隐式公式锁，不在本次命令里。磁盘 `i_oi`/`m_ccl` 不是单测。 |
| 3 | 实盘 `DailyModel.predict` 裸 `get_main_continuous`（copilot / cascade 模型日线前视） | `test_daily_freshness.py`（只测 helper `get_safe_daily`）；`test_future_bar_guard.py`（夜盘**故意允许**下一交易日标签） | helper 10:30 剔当日、21:30 留当日；周五夜盘不删周一 daily。**没有**断言 `daily_model.py:104` 走 `get_safe_daily`。没有「predict 读到的最后一根 dt」测试。 | **缺口。没有一只「本应失败却绿」的测试。** helper 绿不能证明模型绿。guard 绿证明幽灵标签被允许留下，正好解释裸读会吃到它。 |
| 4 | `monthly_backtest`：`hour>=15` 含当日日线；**10:00 不含当日** | `test_backtest_cutoff.py` | 1H 10:00 截断（含 10:00、不含 11:00/14:00）= **现行合同，绿**。日线 `test_daily_includes_cutoff_calendar_day` 期望 10:00 **含**当日 = **过期合同，红**。没有「15:00 含当日 / 10:00 不含当日」的正向锁。 | **过期合同被红测锁住。现行 hour≥15 无绿锁。** |
| 5 | peers 禁止跑 `evaluations/fm_eval/run.py` / 禁止加载 TimesFM | `test_harvest_proposals.py`；`test_praxist_task_contract.py` | harvest：mechanism 长度、非法 symbol/cov、去重、选座。task yaml：`write_paths ⊆ {scripts/praxist_ws, reports/praxist}`、必须有 diagnostic 档、full_walkforward.gate 非空（yaml 里含 `ev>0`）。**不断言** prompt/skill「do NOT run TimesFM」；**不断言** role 不含 `evaluation_tools`；**不断言** schema=`fm.hypothesis_proposal.v1`。 | **无测试锁现行方案 A。** `test_praxist_task_contract` **绿着锁 2026-09-01 旧可写区**（方案 A 可写区是 run 下 `results/`）。这是过期合同且今天仍绿。 |
| 6 | Vol/Neutral 压平默认 OFF；Copilot **永不** `apply_neutral_override*` | `test_vol_threshold_contract.py`（ThrPolicy / 校准优先级）；`test_signal_mode_mutex.py`（`short_horizon_only ⇒ use_full_signal=False`）；`test_copilot_advisory.py`（tick / 止损文案） | 阈值解析、CF-06 互斥、风险边界格式。**无** `FM_VOL_FILTER` 默认 `"0"`；**无** `cascade_predict.use_vol_filter is False`；**无** Copilot 源码不含 `apply_neutral_override`。 | **无测试锁。** 子集外 `test_vol_risk_filter_v2.py` 测压平函数本身（研究路径），会让人误以为盘中默认会压平。 |
| 7 | 只有慢环写 `aligned_verdicts.jsonl` | 指定子集：**无** `test_aligned_slow_loop.py`。`test_harvest_proposals.py` 只断言入队 pending，不碰 registry。 | — | **指定子集完全没锁。** 子集外慢环「能写 / 异常不写死亡行」有测；「supervisor / harvest / peer / archive CLI 不得 append」无测。 |

---

## 2. 逐条说明（证据）

### 2.1 方向合同 — 函数有锁，入口和 Copilot 没有

`tests/test_signal_contract.py:66-75` `test_trade_direction_is_weighted_1h_regime_is_daily`：

- 1H 线性上升 → `position_sign == 1`、`direction` 看多
- `daily_slope=0.0005`（0.05%/天 < 0.1 thr）→ `regime_direction` 中性
- 这把 CF-01 A 钉在 `cascade.signal_contract` 上，今天绿

没有测试：

- `scripts/cascade_predict.py:209-214` / `:535-536` 调用 `position_from_forecast`（Task 6 源码确认，测试没锁调用点）
- `scripts/monthly_backtest.py:50,329` 同上
- `scripts/copilot.py:384,433-434` 用 `_compute_direction_v2` 当卡面主方向

`test_copilot_advisory.py` 只测 `generate_risk_bounds` / `quantize_price`。日线「中性」字符串会走观望文案（`:18-20`），等于把 Copilot 的日线主方向当成输入，并不检验它不该是日线。

`test_system_hardening.py:170-192` 锁 `_compute_direction_v2` 的 R² 门（低 R²→中性）。这锁的是**副标签函数行为**，会让执行者以为「方向=日线 v2」是合同。

**会不会有一只今天该红却绿的测试？没有。** Copilot 违约是缺口。补「Copilot 日线中性 + 1H 看多时主方向仍看多」今天会失败。

### 2.2 IC 与 gate — 子集零锁；附近测试也不锁负 EV

活代码 `task_FM/evaluations/fm_eval/evaluator.py:199-203`：

```python
ic = 2 * abs(m.get("dir_acc", 0.5) - 0.5)
return m["n"] >= min_n and ic >= min_ic
```

`test_evaluation_metrics_contract.py` 八个用例：名义 MaxDD 复利、−100% 下限、零变动不计胜、空仓不罚。不管 IC，不调 `gate()`。

`config/praxist_task.yaml:20` 的 full_walkforward.gate 仍是 `["n>=350", "ic>=0.05", "ev>0"]`。`test_praxist_task_contract.py:54-59` 只断言这列表非空，等于把「最终裁决含 EV」写进绿测，**并不**断言 `evaluator.gate` 不含 EV。

负 EV 仍过布尔门：磁盘 `i_oi` / `m_ccl`（Task 7）。单测没有 `gate_pass=True, ev<0` 夹具。`test_verdict_registry.py:42` 用 `gate_pass=True, ev=0.02`；`test_system_hardening.py:249-256` 用 `gate_pass=False, ev=-1.5`。重构时给 `gate()` 加上 `ev>0`，指定子集全绿。

### 2.3 实盘日线裸读 — helper 有锁，predict 没有

`cascade/daily_model.py:104`：`df = store.get_main_continuous(limit=context_days)`。copilot `:398`、cascade_predict `:101` 传入活 `DataStore`。

`test_daily_freshness.py` 全部 mock `store.get_main_continuous` 再喂给 `get_safe_daily`。10:30 剔当日（现行 helper 合同，绿）。cascade 报告走 helper，模型不走。测试标题「盘中读到今日日线 → 自动剔除」容易让人以为生产预测已防护。

`test_future_bar_guard.py:49-72`：周五 23:00 **允许**周一 daily 标签，且 `purge_future_bars` 不删。这与 Task 5 一致：夜盘采集留下下一交易日未完成日线是 guard 的设计，不是 guard 失职。没有测试要求 `DailyModel.predict` 丢掉这根。

**没有「本应失败却绿」的 predict 测试。** 缺口是没写「live predict 最后一根 dt == get_safe_daily 最后一根」。

### 2.4 回测 cutoff — 1H 现行绿，日线过期红，hour≥15 无正向锁

活代码 `data/data_store.py:790-802`：`cutoff_hour >= 15` → `end_date=cutoff_day`，否则前一日历日。

| 用例 | 期望 | 今天 |
|------|------|------|
| `test_midday_excludes_later_same_day_bars` | 10:00 的 1H 不含 11:00/14:00 | 绿（现行） |
| `test_old_date_only_eod_behavior_removed` | 日期-only 不当 23:59 | 绿（现行） |
| `test_daily_includes_cutoff_calendar_day` | 10:00 **含** 2026-03-10 日线 | **红**（过期；代码不含） |
| （缺失）10:00 日线 **不含** 当日 | 现行合同 | 无测试 |
| （缺失）15:00/21:00 日线 **含** 当日且价=14:00 收盘 | Task 5 夜盘设计 | 无测试 |

红测不能拿来证明「回测日线截断还没修」。Agent 若为了让它绿而改回 10:00 含当日，会把已修的前视防护拆掉。

### 2.5 peer 禁评估 — 提示词有、测试无；旧 yaml 契约仍绿

`test_harvest_proposals.py`：合法 schema 的提案入队；短 mechanism / 非法 cov / 非法 symbol 拒绝。夹具总是带 `schema=fm.hypothesis_proposal.v1`，没有 `schema_mismatch` 拒绝（Task 8 I2，代码本就不读 `p["schema"]`）。

`test_praxist_task_contract.py:48-51`：

```python
allowed = {"scripts/praxist_ws", "reports/praxist"}
assert set(d["write_paths"]) <= allowed
```

`config/praxist_task.yaml:24-26` 仍是这两条，所以**今天绿**。方案 A（Task 8）可写区是 run 下 `results/`。执行者按这只绿测「修契约」会把方案 A 可写区改回去。

没有任何测试读 `task_FM/prompt_base.jinja2` / `roles/peer_generalist/skill.md` 的「do NOT run TimesFM」，也没有断言 `role.yaml` 不含 `evaluation_tools.peer`（现在还含有；若去锁会先红）。

### 2.6 Vol 默认 OFF / Copilot 永不压平 — 零锁

`test_signal_mode_mutex.py` 锁 SCHEMES 里 short 与 full 互斥（CF-06），与 `--vol-filter-neutral` / `FM_VOL_FILTER` 无关。

`test_vol_threshold_contract.py` 锁 ThrPolicy 优先级与 veto 单调，不碰默认开关。

`test_copilot_advisory.py` 不 import `apply_neutral_override`，也不扫 `scripts/copilot.py` 源码。

Task 9 已确认代码守红线（Copilot 零次 `apply_neutral*`，`use_vol_filter` 默认 False）。测试没把这条红线钉死。给 Copilot 接上 overlay 或把默认改成 ON，指定子集仍绿。

### 2.7 慢环唯一写者 — 指定子集空白

`test_harvest_proposals.py` 的成功路径断言 `source=peer_proposal` 入队，registry 不在视野里。

子集外 `tests/test_aligned_slow_loop.py:20-38` 断言候选跑完写入**临时** registry；`:97-120` 异常不写死亡 verdict。没有「`praxist_supervisor` 不得 `open(REGISTRY,"a")`」「harvest 不得 `append_verdict`」。

---

## 3. 测试债（过期合同，不是代码 bug）

| 测试 | 锁的过期合同 | 今天 | 若按测试去「修」代码会怎样 |
|------|----------------|------|------------------------------|
| `test_daily_includes_cutoff_calendar_day` | 10:00 含当日日线 | **红** | 拆掉 `hour>=15` 日线截断，盘中回测前视回来 |
| `test_praxist_task_contract::test_write_paths_within_redlines` | peers 可写 `scripts/praxist_ws` | **绿** | 方案 A 的 run/`results/` 可写区被改回去 |
| `test_praxist_task_contract::test_evidence_maturity_gates` | 必须有 diagnostic 档；full_wf.gate 任意非空（yaml 含 ev>0） | **绿** | 把最终裁决列表当成 `evaluator.gate`；保住 diagnostic 入口（与 peer 禁评估对冲） |
| `test_system_hardening` craft_advisory v2（`:277-291`） | revoked 冻结句 | 绿，但生产 Copilot 走 `craft_advisory` 不是 v2（Task 9） | 误以为卡面已有 revoked 文案 |

红的那只是可见债。绿着锁旧合同的更危险：重构不会响。

---

## 4. 指定子集里「看起来相关、实际没锁」的文件

| 文件 | 实际锁 | 容易误读成 |
|------|--------|------------|
| `test_evaluation_metrics_contract.py` | MaxDD / DirAcc 边角 | IC 公式、gate_pass |
| `test_future_bar_guard.py` | 交易日标签 + 周末清幽灵 1H/日线 | 实盘 DailyModel 无前视 |
| `test_daily_freshness.py` | `get_safe_daily` helper | `DailyModel.predict` 已安全 |
| `test_harvest_proposals.py` | 收割机制 / 去重 / 选座 | peer 不跑 fm_eval；schema 校验；唯一写者 |
| `test_praxist_task_contract.py` | 2026-09-01 yaml 预注册 | 方案 A 三环硬规则 |
| `test_system_hardening.py` | n_eff、cosine、R² 副标签、复权 detect、advisory v2 | 生产方向、gate、Copilot、Vol OFF |
| `test_copilot_advisory.py` | 止损 tick | Copilot 方向 / 永不压平 |
| `test_vol_threshold_contract.py` | ThrPolicy | 压平默认 OFF |
| `test_signal_mode_mutex.py` | CF-06 | Vol/Neutral 互斥 |

`tests/AGENTS.md` 也没把 `test_signal_contract.py` / `test_backtest_cutoff.py` / `test_daily_freshness.py` / `test_copilot_advisory.py` 列进「改评估/Vol 后优先跑」清单。

---

## 5. 子集外、能补洞但不在本次命令里的测试

本任务按简报不扩跑全量 monthly。只记录存在与否：

| 文件 | 对 7 条合同的贡献 | 仍缺 |
|------|---------------------|------|
| `tests/test_praxist_fm_evaluator.py` | n<350 不过门；diracc=0.54 默认过门（未断言公式） | IC 显式公式；负 EV 仍 True |
| `tests/test_aligned_slow_loop.py` | 慢环能写临时 registry；`dir_acc=0.55 → ic==0.1` 隐式锁公式 | 「别人不写」 |
| `tests/test_verdict_registry.py` | `pass_variants` 要 ev>0；dead=`gate_pass is False` | `gate_pass=True, ev<0` 三态 |
| `tests/test_supervisor.py` | phase 互斥、429 resume、harvest 入队 | peer 禁评估；429 期间仍 harvest；`survivors_per_cycle=3` |
| `tests/test_praxist_evidence_ladder.py` | 模板能渲染；**不断言** do NOT run TimesFM | 禁评估 |
| `tests/test_vol_risk_filter_v2.py` | 压平函数数值 | 默认 OFF；Copilot 不调用 |

---

## 6. 矩阵空洞（给 SUMMARY / 后续补测，本任务不写测试）

按风险，不是按文件名：

1. **高 — Copilot 主方向无测试。** 补：日线中性 + 1H 看多时，`run_one` / 卡面 `direction` 仍看多。今天会红。不要为了让它绿去改 `position_from_forecast`。
2. **高 — `gate()` 无 IC 公式、无负 EV。** 补：`dir_acc=0.53 → ic==0.06`；`n=400, ic=0.06, ev=-2 → True`；`n=400, ic=0.04, ev=+10 → False`。否则给 `gate()` 加 EV 或改 Pearson，指定子集无感。
3. **高 — 实盘 predict 裸读无测试。** 补静态：`DailyModel.predict` 源码含 `get_safe_daily`（今天会红，因为没有）。或隔离夹具：predict 读到的最后 `dt` 不得晚于 `get_safe_daily`。不要加载 TimesFM。
4. **中 — 现行 cutoff 日线无正向锁。** 把红测改成 10:00 **不含**当日；另加 15:00 **含**当日。不要让红测指导实现。
5. **中 — peer 禁评估无测试。** 先关 `evaluation_tools` / `diagnostic.launch_allowed`（代码债，Task 8 I1），再锁提示词与 role。现在去锁会先红。
6. **中 — Vol 默认 OFF / Copilot 永不压平无测试。** 静态扫 `scripts/copilot.py` 不含 `apply_neutral_override`；断言 `VolRiskFilter.is_enabled` 在空 env 下 False。
7. **中 — 慢环唯一写者无测试。** grep 生产 `append_verdict` 仅 `aligned_slow_loop.py`（允许 archive restore 作为人工例外）。
8. **低但绿着有害 — `test_praxist_task_contract` 锁旧 write_paths。** 改测试对齐方案 A，或标明该 yaml 不是三环运行时契约。

---

## 7. 范围外 / 未声称

- 未跑 monthly 全量、未加载 TimesFM、未启 Praxist。
- 未把 `test_supervisor.py` / `test_aligned_slow_loop.py` / `test_praxist_fm_evaluator.py` 纳入本次命令（简报核心六文件 + 用户补的 cutoff/freshness/copilot/vol/mutex）。
- 不把红测当 H1 代码回归。
- 不把 123 passed 读成「七条合同已锁」。

---

## 8. 给计划 SUMMARY 的一行

测试健康：**NEEDS ATTENTION**。子集 `1 failed, 123 passed, 3 skipped in 10.68s`。失败 = 过期日线 cutoff 合同（10:00 含当日）。现行七条硬合同只有加权 1H **函数**被锁；Copilot 方向、IC/负 EV 过门、实盘日线裸读、peer 禁评估、Vol 默认 OFF、慢环唯一写者均为缺口。另有绿测锁旧 `write_paths`。

**状态**: `DONE_WITH_CONCERNS`
