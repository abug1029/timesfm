# Baseline Point Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给端点方向和可交易增量各一个写入者，并让每一次基线落盘都通过当前评估网格这同一个后条件，从而停掉「把不合格归档拷回活文件」的死循环。

**Architecture:** `dir_ok` 只由 `endpoint_dir_ok` 产生，可交易增量仍由 `position_from_forecast` 产生。基线 JSONL 只经 `baseline_jsonl_record` 投影。探索基线的身份是 `baseline_eval_cutoffs` 返回的 cutoff 序列。`finalize_baseline_write` 是唯一换名或回滚的函数；监督进程在断路器之前收口。启动失败路径只有规格 Key Decision 9 那一句。

**Tech Stack:** Python 3.11（活仓 `/home/abug/timesfm/.venv`）、pytest、pandas、numpy。不引入新依赖。`cascade/eval_grid.py` 不得导入 torch，不得导入 `monthly_backtest`。

**Spec:** `/home/abug/timesfm/docs/superpowers/specs/2026-11-03-baseline-point-contract-spec.md`

## Global Constraints

规格已经锁定，实施时不得重新打开：

- 不采用方案 A。`delta_pred` 继续是加权可交易增量。覆盖成端点会改 PF / EV / MaxDD，且不修正门控。CF-01 A 是产品规则。
- `dir_ok` 的属主是 `endpoint_dir_ok`。不为它重生 21 个品种，不抬协议指纹。`batch_backtest.py`、`backtest_vol_gating_fullchain.py`、`validate_context_length.py` 只要还用这个字段名，就调用同一个函数。零变动判真不保留。这三个脚本的盈亏算法不改。
- 新行追加 `endpoint_delta` 与 `position_sign`，旧行不必回填。经济指标优先读 `position_sign`，缺键才退回 `sign(delta_pred)`。
- 探索基线的身份是当前 `select_eval_indices` 网格（加与回测相同的日线过滤），不是上一份文件的超集。九月的 588 行不等于今天的 588 行。`STEP` 保持下标步长。
- 回滚目标必须通过同一后条件。未通过的字节不得换名成活文件。没有合格归档时保留换名之前的活文件，删除被拒的临时文件。断路器只在第二次收口为假，或写入中途抛出时记下数据末端。第一次接受失败不记。第一次收口为真不运行 `generate`，也不记停滞。禁止把触发重生的短文件拷回去。禁止 `n < 100` 豁免。禁止留下子集冒充新网格。任一点带 `error` 就不是可发布文件。
- 确认窗缺失只报告。`confirm_from_ts`、1199、986 都不动。`jd` 与 `sr` 不是两套代码。不改 `task_FM/config/preregistry.jsonl`。
- 续跑载荷以 `resumed_points` 为准，不再要求同时出现在 `completed` 里。增量不再用「末笔加两小时」重起相位，也不再于回测外拼接。
- `_valid_n_for_symbol` 不作为验收网格，本规格也不修改它。
- 不改 `compute_effective_min`、`compute_protocol_fingerprint` 的输入、`pair_dir_ok_series`、`calc_prediction_quality` 的公式、Copilot、`neutral_ab_report.py`、`vol_gating_replay.py`。不引入协议第五版。
- 不重启监督进程，不运行 `scripts/restart_three_loop_clean.sh`，不在本计划的任何任务里调用 `generate` 去写活基线，不手改 `baseline_points_*.jsonl`，不加载 TimesFM 权重，不改 `.venv`，不打印 `.env.praxist`。
- 测试只用活仓解释器的点名 pytest：`/home/abug/timesfm/.venv/bin/python -m pytest <节点> -v`。不跑全量 pytest。
- 改 Python 之前用 `superpowers:using-git-worktrees` 在活仓外面开工作树。监督进程正在用检出时，不要在 `/home/abug/timesfm` 里改 `.py`。本计划是 markdown，写在活仓 `docs/superpowers/plans/` 下，与规格相同，不构成重启理由。
- 下面这句是启动失败路径的唯一合同。Task 10 和 Task 11 必须按这句实现，不得另写结尾：`incremental_generate` 返回后：已有可发布临时文件就调用 `finalize_baseline_write`。第一次收口为真就换名、返回网格末笔、不再运行 `generate`。没有可发布临时文件（包括任一评估点带 `error`，或换名前失败），或临时文件未通过，这是第一次接受失败，不是提前结束；没有临时文件且活文件尚未通过时，把第一次收口当成假。只有第一次收口为假，才恰好运行一次 `generate(..., finalize=False)` 并第二次调用 `finalize_baseline_write`。只有第二次收口为假才 `_remember_stall`。第一次为真不记停滞。读网格或写入抛出的异常不是这个 `None`：留在品种循环的 `except` 里记日志；读网格失败不记停滞、不启动全量；写入中途抛出则记停滞，并且不再启动另一次全量。

## 范围

这是一份计划，里面按顺序排了规格的三截审查单位（PR1 = Task 1–5，PR2 = Task 6–10，PR3 = Task 11）。不拆成三份计划。投影函数、后条件和两个写入者是一条合同：只落后条件时，守卫仍会把不合格归档拷回去；只落新字段而留下超集回滚时，下一次启动仍把新文件盖掉。规格自己已经把它们排成前后依赖的三截，而不是三个独立子系统。

## 文件职责

| 文件 | 职责 |
|------|------|
| `cascade/signal_contract.py` | `endpoint_dir_ok` 的新家；`assemble_direction` |
| `scripts/monthly_backtest.py` | 再导出 `endpoint_dir_ok`；回测改走装配；续跑合并不再要求 `completed`；检查点多两个可选键；`select_eval_indices` 变成转发 |
| `cascade/evaluation_metrics.py` | `tradable_sign`；`metrics_from_backtest_points` 改读它 |
| `cascade/baseline_paths.py` | `baseline_jsonl_record`，唯一的基线行投影 |
| `scripts/generate_baseline_points.py` | 调用投影；`finalize=False` 只写临时文件 |
| `scripts/incremental_baseline.py` | 调用投影；不传 `eval_start_ts`；不在回测外拼接；按网格筛选可复用行 |
| `scripts/short_variety_diagnostic.py` | 装配函数；`cutoff` 为完整收盘时间戳；PF12 走 `tradable_sign` |
| `scripts/batch_backtest.py`、`scripts/validate_context_length.py`、`scripts/backtest_vol_gating_fullchain.py` | 只有 `dir_ok` 改走 `endpoint_dir_ok` |
| `cascade/eval_grid.py` | 网格、日线过滤、`baseline_eval_cutoffs`、`accept_baseline_file`。无 torch |
| `scripts/sup_evidence.py` | `finalize_baseline_write`；删除超集守卫；`ensure_baselines` 只问一次后条件 |
| `scripts/praxist_supervisor.py` | 删掉 `_HOMES` 里的 `_guard_confirm_from_ts_after_regen` |
| `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md` | §3.1 加一句勘误，不重写全文 |
| `docs/superpowers/reports/2026-11-03-jd-baseline-operator-note.md` | 五步运维说明。本计划不执行这五步 |

后面任务里的函数签名以这一节为准，不要另起名字：

```python
def endpoint_dir_ok(pred_end: float, real_end: float, base: float, eps: float = 1e-8) -> bool: ...

def assemble_direction(point_forecast, base_price, real_end, scheme, daily_slope=None) -> dict:
    """返回 delta_pred: float, position_sign: float, endpoint_delta: float, dir_ok: bool。"""

def tradable_sign(point) -> float: ...

def baseline_jsonl_record(point, protocol_fingerprint) -> dict: ...

def select_eval_indices(dts, *, eval_start_ts=None, max_points=None,
                        context_bars: int, horizon: int, step: int,
                        eval_window_bars: int) -> list: ...

def filter_by_daily_sufficiency(indices, hourly_dt, daily_df, min_daily_required: int) -> list: ...

def baseline_eval_cutoffs(symbol: str) -> list[str]: ...

def accept_baseline_file(path, expected_cutoffs, current_fingerprint) -> tuple[bool, str]: ...

def finalize_baseline_write(symbol, points_path, root, archive_path) -> bool: ...
```

`scripts/monthly_backtest.py` 里同名的 `select_eval_indices(dts, *, eval_start_ts=None, max_points=None)` 保持现有调用签名，把本模块的 `CONTEXT_BARS`、`HORIZON`、`STEP`、`EVAL_WINDOW_BARS` 传进 `cascade.eval_grid.select_eval_indices`。现有测试打的是 `mb.CONTEXT_BARS` 这些模块全局量，转发之后仍然生效。`baseline_eval_cutoffs` 不接受覆盖参数，它在调用时读取 `config.backtest_config` 的属性。

`generate(symbol, cov, root, finalize=True)` 与 `incremental_generate(symbol, cov=None, root=".", finalize=True)` 的原有位置参数保持不变，`finalize` 只加在关键字上。

---

### Task 1: 把 endpoint_dir_ok 挪到 signal_contract

**Files:**
- Modify: `cascade/signal_contract.py`
- Modify: `scripts/monthly_backtest.py`（删掉 55–65 行的函数体，改为再导出）
- Test: `tests/test_signal_contract.py`
- Test: `tests/test_monthly_backtest_quality.py`

**Interfaces:**
- Consumes: 无
- Produces: `cascade.signal_contract.endpoint_dir_ok(pred_end, real_end, base, eps=1e-8) -> bool`。`monthly_backtest.endpoint_dir_ok` 是同一个函数对象。函数体与今天 `scripts/monthly_backtest.py` 55–65 行相同：真实变动绝对值小于 `1e-8` 返回 `False`，否则比较两端点相对基准价的符号。

- [ ] **Step 1: Write the failing test**

在 `tests/test_signal_contract.py` 的 `TestSignalContract` 里增加：

```python
def test_endpoint_dir_ok_matches_endpoint_and_rejects_zero_move(self):
    from cascade.signal_contract import endpoint_dir_ok
    self.assertTrue(endpoint_dir_ok(101.0, 102.0, 100.0))
    self.assertFalse(endpoint_dir_ok(99.0, 102.0, 100.0))
    self.assertFalse(endpoint_dir_ok(101.0, 100.0, 100.0))
```

在 `tests/test_monthly_backtest_quality.py` 增加：

```python
def test_monthly_backtest_reexports_endpoint_dir_ok():
    from cascade.signal_contract import endpoint_dir_ok as owned
    from monthly_backtest import endpoint_dir_ok as reexported
    assert reexported is owned
    assert reexported(101.0, 102.0, 100.0) is True
    assert reexported(101.0, 100.0, 100.0) is False
```

不要改 `test_dir_ok_formula_endpoint_not_weighted`。它继续 `from monthly_backtest import endpoint_dir_ok`。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_signal_contract.py::TestSignalContract::test_endpoint_dir_ok_matches_endpoint_and_rejects_zero_move tests/test_monthly_backtest_quality.py::test_monthly_backtest_reexports_endpoint_dir_ok -v`

Expected: FAIL，`cascade.signal_contract` 里没有 `endpoint_dir_ok`。

- [ ] **Step 3: Write minimal implementation**

把 `scripts/monthly_backtest.py` 55–65 行的函数原样移到 `cascade/signal_contract.py`，放在 `position_from_forecast` 之前。删掉月度回测里的函数体。该文件已经有 `from cascade.signal_contract import position_from_forecast`，改成：

```python
from cascade.signal_contract import endpoint_dir_ok, position_from_forecast
```

`cascade/signal_contract.py` 不得导入 `monthly_backtest` 或 torch。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_signal_contract.py tests/test_monthly_backtest_quality.py::test_dir_ok_formula_endpoint_not_weighted tests/test_monthly_backtest_quality.py::test_monthly_backtest_reexports_endpoint_dir_ok -v`

Expected: PASS。无方案退化为端点的既有用例仍然通过。

- [ ] **Step 5: Commit**

```bash
git add cascade/signal_contract.py scripts/monthly_backtest.py tests/test_signal_contract.py tests/test_monthly_backtest_quality.py
git commit -m "move endpoint_dir_ok into signal_contract and re-export it"
```

---

### Task 2: assemble_direction，回测和诊断改走它

**Files:**
- Modify: `cascade/signal_contract.py`
- Modify: `scripts/monthly_backtest.py`（约 497–530 行的信号块，562 行起的点字典，108–114 行的 `_CHECKPOINT_POINT_KEYS`，591 行检查点写入）
- Modify: `scripts/short_variety_diagnostic.py`（约 295–340 行的 `run_diagnostic_backtest` 点构造，以及 346 行附近的检查点循环）
- Test: `tests/test_signal_contract.py`
- Test: `tests/test_monthly_backtest_quality.py`（扩展 `test_checkpoint_keys_include_new_metrics`）

**Interfaces:**
- Consumes: `endpoint_dir_ok`；`position_from_forecast`；`get_scheme("jd")`（`use_full_signal=True`，`short_horizon_only=False`，`decay=1.42`）
- Produces: `assemble_direction(point_forecast, base_price, real_end, scheme, daily_slope=None) -> dict`，键为 `delta_pred`、`position_sign`、`endpoint_delta`、`dir_ok`。`dir_ok` 只来自 `endpoint_dir_ok(base + endpoint_delta, real_end, base)`。

- [ ] **Step 1: Write the failing test**

在 `TestSignalContract` 增加。价格前 23 根是 90，最后一根是 101，基准价 100。前段权重大，加权结果低于基准价；端点和真实端点都高于基准价。

```python
def test_jd_assemble_direction_uses_endpoint_when_weighted_sign_opposes(self):
    import numpy as np
    from config.prediction_scheme import get_scheme
    from cascade.signal_contract import assemble_direction
    scheme = get_scheme("jd")
    self.assertIsNotNone(scheme)
    self.assertTrue(scheme.use_full_signal)
    self.assertFalse(scheme.short_horizon_only)
    self.assertEqual(scheme.decay, 1.42)
    forecast = np.array([90.0] * 23 + [101.0])
    out = assemble_direction(forecast, 100.0, 103.0, scheme)
    self.assertLess(out["position_sign"], 0)
    self.assertLess(out["delta_pred"], 0)
    self.assertGreater(out["endpoint_delta"], 0)
    self.assertIs(out["dir_ok"], True)

def test_diagnostic_source_does_not_assign_dir_ok_from_delta_pred(self):
    from pathlib import Path
    text = Path("scripts/short_variety_diagnostic.py").read_text(encoding="utf-8")
    self.assertIn("assemble_direction", text)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("dir_ok"):
            self.assertNotIn("delta_pred", stripped)
            self.assertNotIn("else True", stripped)
```

在 `test_checkpoint_keys_include_new_metrics` 的循环里加上 `"endpoint_delta"` 和 `"position_sign"`。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_signal_contract.py::TestSignalContract::test_jd_assemble_direction_uses_endpoint_when_weighted_sign_opposes tests/test_signal_contract.py::TestSignalContract::test_diagnostic_source_does_not_assign_dir_ok_from_delta_pred tests/test_monthly_backtest_quality.py::test_checkpoint_keys_include_new_metrics -v`

Expected: FAIL，`assemble_direction` 不存在；诊断源码 310 行仍是 `dir_ok = bool(np.sign(delta_pred) == np.sign(delta_real)) if delta_real != 0 else True`；检查点键元组还没有这两个名字。

- [ ] **Step 3: Write minimal implementation**

在 `cascade/signal_contract.py` 增加：

```python
def assemble_direction(point_forecast, base_price, real_end, scheme, daily_slope=None):
    sig = position_from_forecast(
        point_forecast, base_price, scheme=scheme, daily_slope=daily_slope,
    )
    endpoint_delta = float(sig["endpoint_delta"])
    real_end_f = float(real_end)
    base = float(base_price)
    return {
        "delta_pred": float(sig["delta_pred"]),
        "position_sign": float(sig["position_sign"]),
        "endpoint_delta": endpoint_delta,
        "dir_ok": endpoint_dir_ok(base + endpoint_delta, real_end_f, base),
    }
```

`scripts/monthly_backtest.py` 里从 `_scheme = get_scheme(symbol)` 到 `dir_ok = endpoint_dir_ok(...)` 的那一段，改成调用 `assemble_direction(pred, base, float(real[-1]), _scheme, daily_slope=getattr(daily_result, "horizon_slope", None))`。`signal_override` 仍在调用前用 `dataclasses.replace` 改方案。`delta_pred`、`position_sign`、`endpoint_delta`、`dir_ok` 都从返回值取出。不要再留第二行 `dir_ok = ...`。`pnl = position_sign * delta_real`（`position_sign == 0` 时为 0）保持原样。`clip_gap` 仍只截断点里的 `delta_real`，不参与 `dir_ok`。`dir12_ok` 的公式不动。点字典加上 `"endpoint_delta": endpoint_delta` 和 `"position_sign": position_sign`。

`_CHECKPOINT_POINT_KEYS` 在 `"delta_real"` 后面加上 `"endpoint_delta"` 和 `"position_sign"`。1166 行已经是 `{k: rec[k] for k in _CHECKPOINT_POINT_KEYS if k in rec}`，保持这个 `if k in rec`。缺这两键的旧检查点继续合并其余字段，不要填 `0`，不要因此丢弃整行。

591 行 `rec[k] = point[k]` 会在点缺键时抛出并被收成 `error` 点。主路径的点必须带上这两键。不要把这两键的缺失写成 `0`。

`scripts/short_variety_diagnostic.py` 的 `run_diagnostic_backtest` 用同一次 `assemble_direction` 替换现在的 `position_from_forecast` 加 `dir_ok = bool(np.sign(delta_pred) ...)`。`delta_real`、`delta_real_12`、`pnl`、`dir12_ok` 的算法不动。点的 `cutoff` 改为该函数已经算好的完整收盘时间戳（今天约 264 行的 `cutoff`），不要再把只有日期的 `dt` 写进 `cutoff`。另留 `"cutoff_date": dt` 给展示。续跑主键仍是 `(symbol, idx)`。

诊断检查点循环今天是 `rec[k] = point.get(k, 0)`。对其余键保持这个写法。`endpoint_delta` 和 `position_sign` 只在点里真有该键时写入，不要靠 `0` 这个默认值把缺键写成零。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_signal_contract.py tests/test_monthly_backtest_quality.py::test_checkpoint_keys_include_new_metrics tests/test_monthly_backtest_quality.py::test_dir_ok_formula_endpoint_not_weighted -v`

Expected: PASS。`test_no_scheme_endpoint_fallback` 和 `test_short_horizon_ignores_second_half_endpoint` 仍然通过。

- [ ] **Step 5: Commit**

```bash
git add cascade/signal_contract.py scripts/monthly_backtest.py scripts/short_variety_diagnostic.py tests/test_signal_contract.py tests/test_monthly_backtest_quality.py
git commit -m "assemble endpoint dir_ok separately from the weighted position"
```

---

### Task 3: tradable_sign，经济指标优先读 position_sign

**Files:**
- Modify: `cascade/evaluation_metrics.py`（192 行附近）
- Modify: `scripts/short_variety_diagnostic.py`（`compute_pf12`，约 174 行）
- Test: `tests/test_monthly_backtest_quality.py`

**Interfaces:**
- Consumes: 点上可选的 `position_sign`，以及必有的 `delta_pred`
- Produces: `tradable_sign(point) -> float`。点里有 `position_sign` 且不是 `None` 时返回 `float(position_sign)`，否则返回 `float(np.sign(point["delta_pred"]))`。

- [ ] **Step 1: Write the failing test**

放在 `test_economic_metrics_still_present` 后面：

```python
def test_tradable_sign_prefers_position_sign_and_falls_back_for_old_rows():
    from cascade.evaluation_metrics import metrics_from_backtest_points, tradable_sign
    from short_variety_diagnostic import compute_pf12

    flipped = {
        "delta_pred": -5.0,
        "position_sign": 1.0,
        "delta_real": 4.0,
        "base": 100.0,
    }
    assert tradable_sign(flipped) == 1.0
    gross = metrics_from_backtest_points([flipped], tick_size=1.0, slippage_ticks=0)
    assert gross["EV_gross"] > 0

    old = {"delta_pred": 3.0, "delta_real": 4.0, "base": 100.0}
    assert tradable_sign(old) == 1.0
    old_gross = metrics_from_backtest_points([old], tick_size=1.0, slippage_ticks=0)
    assert old_gross["EV_gross"] > 0

    pf = compute_pf12(
        [{
            "delta_pred": -5.0,
            "position_sign": 1.0,
            "delta_real_12": 4.0,
            "base": 100.0,
        }],
        tick_size=1.0,
        slippage_ticks=0,
    )
    assert pf["EV12_ratio"] > 0
```

`metrics_from_backtest_points` 今天用 `np.sign(delta_pred)`。上面第一组的毛收益在当前代码上是负的，所以这条测试现在失败。不要改 `neutral_ab_report.py` 或 `vol_gating_replay.py`。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_monthly_backtest_quality.py::test_tradable_sign_prefers_position_sign_and_falls_back_for_old_rows -v`

Expected: FAIL。导入 `tradable_sign` 失败，或者 `EV_gross` 不为正。

- [ ] **Step 3: Write minimal implementation**

```python
def tradable_sign(point) -> float:
    if "position_sign" in point and point["position_sign"] is not None:
        return float(point["position_sign"])
    return float(np.sign(point["delta_pred"]))
```

`metrics_from_backtest_points` 里 `dirs = np.array([np.sign(p["delta_pred"]) for p in ok], dtype=float)` 改为 `dirs = np.array([tradable_sign(p) for p in ok], dtype=float)`。

`compute_pf12` 里 `sign = np.sign(p["delta_pred"])` 改为 `sign = tradable_sign(p)`。文件顶部从 `cascade.evaluation_metrics` 导入 `tradable_sign`。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_monthly_backtest_quality.py::test_tradable_sign_prefers_position_sign_and_falls_back_for_old_rows tests/test_monthly_backtest_quality.py::test_economic_metrics_still_present -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add cascade/evaluation_metrics.py scripts/short_variety_diagnostic.py tests/test_monthly_backtest_quality.py
git commit -m "score economic direction from position_sign when the point has it"
```

---

### Task 4: 唯一的基线行投影，增量不再换相位、不再在回测外拼接

**Files:**
- Modify: `cascade/baseline_paths.py`
- Modify: `scripts/generate_baseline_points.py`（模块文档 7–14 行；148–154 行的记录字面量）
- Modify: `scripts/incremental_baseline.py`（50–56 行、83 行的 `eval_start_ts`；92–97 行的外部拼接；117–124 行的记录字面量）
- Modify: `scripts/monthly_backtest.py`（406–410 行的续跑门闩，以及约 321 行的文档字符串）
- Test: `tests/test_generate_baseline_points.py`
- Create: `tests/test_baseline_record_and_resume.py`

**Interfaces:**
- Consumes: `baseline_filename`；点上的 `cutoff`、`dir_ok`、`delta_pred`、`delta_real`，以及可选的 `endpoint_delta`、`position_sign`
- Produces: `baseline_jsonl_record(point, protocol_fingerprint) -> dict`。必有 `cutoff`、`dir_ok`（bool）、`delta_pred`（float）、`delta_real`（float）、`protocol_fingerprint`。点里有 `endpoint_delta` 或 `position_sign` 才写入对应的 float。没有就省略键，禁止写成 `0` 或 `null`。不写 `pred_end`、`base`。`cutoff` 必须能被 `%Y-%m-%d %H:%M:%S` 解析，否则抛 `ValueError`。

这一截同时改续跑门闩。测试 (e) 禁止外部拼接；若只删拼接、却仍要求 `completed` 里也有该键，增量会把旧点丢掉。合并条件因此放在这一截，而不是留到后条件那一截。

- [ ] **Step 1: Write the failing test**

把 `tests/test_generate_baseline_points.py` 里 `set(rec.keys()) == {五键}` 换成：

```python
required = {"cutoff", "dir_ok", "delta_pred", "delta_real", "protocol_fingerprint"}
assert required <= set(rec.keys())
assert set(rec.keys()) <= required | {"endpoint_delta", "position_sign"}
assert "endpoint_delta" not in rec
assert "position_sign" not in rec
```

这 120 个假点没有新键，文件里也不该出现新键。同一文件再加一个测试，假点带上 `endpoint_delta=0.5` 和 `position_sign=1.0`，断言这两键以 float 出现。这个测试同样 mock `gbp.mb.run_symbol_backtest`，不要打开品种库。mock 的 `generate` 仍会自己 `rename`，本任务先保持这个行为。

新建 `tests/test_baseline_record_and_resume.py`：

```python
import json
from pathlib import Path

import numpy as np
import pandas as pd


def test_record_omits_missing_new_keys_and_rejects_bad_cutoff():
    from cascade.baseline_paths import baseline_jsonl_record
    rec = baseline_jsonl_record(
        {"cutoff": "2026-01-01 10:00:00", "dir_ok": True, "delta_pred": 1, "delta_real": 2},
        "fp",
    )
    assert set(rec) == {"cutoff", "dir_ok", "delta_pred", "delta_real", "protocol_fingerprint"}
    assert rec["dir_ok"] is True
    full = baseline_jsonl_record(
        {"cutoff": "2026-01-01 10:00:00", "dir_ok": False, "delta_pred": -1,
         "delta_real": 2, "endpoint_delta": 0.5, "position_sign": -1},
        "fp",
    )
    assert full["endpoint_delta"] == 0.5
    assert full["position_sign"] == -1.0
    try:
        baseline_jsonl_record(
            {"cutoff": "2026-01-01", "dir_ok": True, "delta_pred": 1, "delta_real": 1},
            "fp",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("日期而不是收盘时间戳时必须拒绝")


def test_both_writers_call_record_and_incremental_does_not_rephase(tmp_path, monkeypatch):
    import scripts.generate_baseline_points as gbp
    import scripts.incremental_baseline as ib
    import scripts.monthly_backtest as mb

    seen = []

    def _rec(point, fp):
        seen.append(point["cutoff"])
        return {
            "cutoff": point["cutoff"],
            "dir_ok": bool(point["dir_ok"]),
            "delta_pred": float(point["delta_pred"]),
            "delta_real": float(point["delta_real"]),
            "protocol_fingerprint": fp,
        }

    monkeypatch.setattr("cascade.baseline_paths.baseline_jsonl_record", _rec)
    monkeypatch.setattr(gbp, "baseline_jsonl_record", _rec, raising=False)
    points = [{
        "cutoff": "2026-02-01 10:00:00", "dir_ok": True,
        "delta_pred": 1.0, "delta_real": 1.0,
    }]
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: {"points": points, "symbol": "SS"})

    class _Model:
        def __init__(self, *a, **k):
            self.model = None

    monkeypatch.setattr("cascade.daily_model.DailyModel", _Model)
    monkeypatch.setattr("cascade.hourly_model.HourlyModel", _Model)
    captured = {}

    def _bt(*a, **k):
        captured.update(k)
        return {"points": points}

    monkeypatch.setattr(mb, "run_symbol_backtest", _bt)
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True)
    (cfg / "baseline_points_jd_nocov.jsonl").write_text(
        json.dumps({"cutoff": "2026-01-01 10:00:00", "dir_ok": True,
                    "delta_pred": 1.0, "delta_real": 1.0,
                    "protocol_fingerprint": "fp"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "task_FM.evaluations.fm_eval.evaluator.compute_protocol_fingerprint",
        lambda: "fp",
    )
    ib.incremental_generate("jd", None, str(tmp_path))
    assert "eval_start_ts" not in captured
    assert "completed" not in captured
    assert captured["resumed_points"]
    gbp.generate("ss", cov="ccl", root=str(tmp_path))
    assert seen, "两个写入者都要调用投影"
    gen_src = Path("scripts/generate_baseline_points.py").read_text(encoding="utf-8")
    inc_src = Path("scripts/incremental_baseline.py").read_text(encoding="utf-8")
    assert "baseline_jsonl_record" in gen_src
    assert "baseline_jsonl_record" in inc_src
    assert '"protocol_fingerprint": _proto' not in gen_src
    assert '"protocol_fingerprint": _proto' not in inc_src
    assert "resumed_as_points" not in inc_src
    assert "timedelta(hours=2)" not in inc_src


def test_resumed_points_merge_without_completed(monkeypatch):
    import scripts.monthly_backtest as mb
    from tests.test_v4_window_anchor import _FakeStore, _hourly_df, _daily_df

    h1 = _hourly_df(80)
    monkeypatch.setattr(mb, "DataStore", lambda symbol: _FakeStore(h1, _daily_df()))
    monkeypatch.setattr(mb, "CONTEXT_BARS", 20)
    monkeypatch.setattr(mb, "CONTEXT_DAYS", 10)
    monkeypatch.setattr(mb, "HORIZON", 4)
    monkeypatch.setattr(mb, "HORIZON_DAYS", 2)
    monkeypatch.setattr(mb, "STEP", 5)
    monkeypatch.setattr(mb, "EVAL_WINDOW_BARS", 40)
    indices = mb.select_eval_indices(h1["dt"])
    cutoffs = []
    for idx in indices:
        bar = pd.Timestamp(h1["dt"].iloc[idx])
        cutoffs.append((bar + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"))
    resumed = {}
    for cutoff in cutoffs:
        resumed[("ss", cutoff)] = {
            "cutoff": cutoff, "base": 100.0, "pred_end": 101.0, "real_end": 101.0,
            "delta_pred": 1.0, "delta_real": 1.0, "dir_ok": True, "dir12_ok": True,
            "mae": 1.0, "mape": 1.0, "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 4,
            "pnl": 1.0, "real_range": 2.0, "roll_in_horizon": False,
            "endpoint_mape": 1.0, "endpoint_bias_pct": 0.0, "path_corr": None,
            "covariates_used": False, "context_hash": "a" * 16, "ablation_mode": "full",
            "protocol_fingerprint": "should-drop", "symbol": "ss", "idx": 0,
        }
    data = mb.run_symbol_backtest(
        "ss", None, None, cov_override="none", resumed_points=resumed,
    )
    assert data is not None
    assert [p["cutoff"] for p in data["points"]] == cutoffs
    assert "protocol_fingerprint" not in data["points"][0]

    completed = {("ss", c) for c in cutoffs}
    skipped = mb.run_symbol_backtest(
        "ss", None, None, cov_override="none", completed=completed,
    )
    assert skipped is not None
    assert skipped["points"] == []
```

`test_resumed_points_merge_without_completed` 在当前门闩上会去调用 `None` 模型并失败。这就是要先看到的失败。不要改 `tests/test_monthly_resume.py` 里那个测试自己写的循环。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_baseline_record_and_resume.py tests/test_generate_baseline_points.py::test_generate_writes_jsonl_and_metrics -v`

Expected: FAIL。`baseline_jsonl_record` 不存在，或增量源码仍有 `timedelta(hours=2)` 与 `resumed_as_points`，或只传 `resumed_points` 时仍进入模型。

- [ ] **Step 3: Write minimal implementation**

`cascade/baseline_paths.py`：

```python
import datetime as _dt


def baseline_jsonl_record(point, protocol_fingerprint) -> dict:
    cutoff = point["cutoff"]
    _dt.datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
    rec = {
        "cutoff": cutoff,
        "dir_ok": bool(point["dir_ok"]),
        "delta_pred": float(point["delta_pred"]),
        "delta_real": float(point["delta_real"]),
        "protocol_fingerprint": protocol_fingerprint,
    }
    if "endpoint_delta" in point and point["endpoint_delta"] is not None:
        rec["endpoint_delta"] = float(point["endpoint_delta"])
    if "position_sign" in point and point["position_sign"] is not None:
        rec["position_sign"] = float(point["position_sign"])
    return rec
```

两处写入都在函数内部写 `from cascade.baseline_paths import baseline_jsonl_record`，再 `rec = baseline_jsonl_record(pt, _proto)`。不要在模块顶部绑定这个名字，否则测试打在 `cascade.baseline_paths.baseline_jsonl_record` 上打不中。删掉五键字面量。`generate_baseline_points.py` 顶部的「JSONL 只写四个字段」改成：必写 `cutoff`、`dir_ok`、`delta_pred`、`delta_real`、`protocol_fingerprint`；点上有 `endpoint_delta` 或 `position_sign` 时一并写入。这一截仍保留 `if "error" in pt: continue` 和写完后的 `rename`。下一截才禁止跳过错误点。

`incremental_generate`：删掉 `last_cutoff + timedelta(hours=2)` 和 `eval_start_ts`。调用 `run_symbol_backtest` 时不传 `eval_start_ts`，不传 `completed`，传 `resumed_points`。`resumed_points` 这一截先收录现有文件里带 `dir_ok`、`delta_pred`、`delta_real` 且 `protocol_fingerprint` 等于当前指纹的行，键是 `(symbol_lower, cutoff)`。写入列表只用 `result["points"]`，按 cutoff 去重。删除 `resumed_as_points + new_points`。仍把临时文件 `rename` 成活文件。Task 9 再按网格筛这些行。

`run_symbol_backtest` 406–410 行换成：

```python
key = (sym_lower, cutoff)
if resumed_points is not None and key in resumed_points:
    pt = dict(resumed_points[key])
    for extra in ("symbol", "idx", "eval_end_ts", "protocol_fingerprint"):
        pt.pop(extra, None)
    points.append(pt)
    continue
if completed is not None and key in completed:
    continue
```

文档字符串 321 行改为：`resumed_points` 里有该 `(symbol, cutoff)` 就合并并跳过模型，不再要求 `completed` 也含有它。只在 `completed` 里、没有载荷的键仍跳过且不进入 `points`。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_baseline_record_and_resume.py tests/test_generate_baseline_points.py tests/test_v4_window_anchor.py -v`

Expected: PASS。`test_v4_window_anchor.py` 仍同时传入 `completed` 和 `resumed_points`，行为不变。

- [ ] **Step 5: Commit**

```bash
git add cascade/baseline_paths.py scripts/generate_baseline_points.py scripts/incremental_baseline.py scripts/monthly_backtest.py tests/test_generate_baseline_points.py tests/test_baseline_record_and_resume.py
git commit -m "project baseline rows once and merge resume payloads on their own"
```

---

### Task 5: 三个脚本的 dir_ok 改属主，并给 2026-09-14 规格加勘误

**Files:**
- Modify: `scripts/batch_backtest.py`（62 行）
- Modify: `scripts/validate_context_length.py`（81 行）
- Modify: `scripts/backtest_vol_gating_fullchain.py`（108 行）
- Modify: `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`（§3.1，约 58 行那张表的 `dir_ok` 行下面）
- Test: `tests/test_dir_ok_owners.py`（新建）

**Interfaces:**
- Consumes: `endpoint_dir_ok(pred_end, real_end, base, eps=1e-8) -> bool`
- Produces: 三个脚本里名为 `dir_ok` 的字段都来自 `endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))`。`batch_backtest` 与 `validate_context_length` 的 `delta_pred` 仍是 `pred[-1] - base`。波动否决仍把 `delta_pred` 压成 0，`position_sign` 和 `pnl` 仍读压平之后的增量。`dir12_ok` 三个文件都不改。

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

import numpy as np


def _dir_ok_lines(path):
    text = Path(path).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip().startswith("dir_ok")]


def test_three_scripts_assign_dir_ok_from_endpoint():
    expected = {
        "scripts/batch_backtest.py": "endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))",
        "scripts/validate_context_length.py": "endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))",
        "scripts/backtest_vol_gating_fullchain.py": "endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))",
    }
    for path, snippet in expected.items():
        lines = _dir_ok_lines(path)
        assert lines, path
        for line in lines:
            assert "endpoint_dir_ok" in line
            assert "else True" not in line
            assert "delta_pred" not in line
            assert snippet in line
        text = Path(path).read_text(encoding="utf-8")
        if path != "scripts/backtest_vol_gating_fullchain.py":
            assert "delta_pred = pred[-1] - base" in text


def test_vol_veto_flats_position_but_dir_ok_stays_endpoint():
    from scripts.backtest_vol_gating_fullchain import _point_from_pred
    pred = np.array([100.0] * 23 + [110.0])
    real = np.array([100.0] * 23 + [110.0])
    point = _point_from_pred("2026-01-01", 100.0, real, pred, None, 0.9, True, scheme=None)
    assert point["delta_pred"] == 0.0
    assert point["dir_ok"] is True
    assert point["position_sign"] == 0.0
    assert point["pnl"] == 0.0


def test_2026_09_14_spec_has_dir_ok_errata():
    text = Path("docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md").read_text(encoding="utf-8")
    assert "endpoint_dir_ok" in text
    assert "加权可交易增量" in text
    assert "2026-11-03-baseline-point-contract-spec.md" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_dir_ok_owners.py -v`

Expected: FAIL。三处赋值仍是零变动判真；否决时 `dir_ok` 为假；勘误句子还不在。

- [ ] **Step 3: Write minimal implementation**

三处 `dir_ok` 赋值都换成：

```python
dir_ok = endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))
```

各文件从 `cascade.signal_contract` 导入 `endpoint_dir_ok`。`backtest_vol_gating_fullchain.py` 保留「Neutral override always flats economic position」和把 `delta_pred` 压成 0 的两行。不要把 `position_from_forecast` 引进 `batch_backtest.py` 或 `validate_context_length.py` 的 `delta_pred`。

在 2026-09-14 规格 §3.1 的 `dir_ok` 那一行下面加一段，不改表里其他行：

```markdown
勘误（2026-11-03）：基线 JSONL 的 `dir_ok` 由 `endpoint_dir_ok` 定义；同文件中的 `delta_pred` 是加权可交易增量，不是该等式里的端点差。等式的现行属主以 `docs/superpowers/specs/2026-11-03-baseline-point-contract-spec.md` 为准。
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_dir_ok_owners.py tests/test_signal_contract.py::TestSignalContract::test_diagnostic_source_does_not_assign_dir_ok_from_delta_pred -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/batch_backtest.py scripts/validate_context_length.py scripts/backtest_vol_gating_fullchain.py docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md tests/test_dir_ok_owners.py
git commit -m "give every dir_ok field the endpoint owner"
```

到这里是 PR1。不要改守卫，不要重写任何 `baseline_points_*.jsonl`。

---

### Task 6: 抽出评估网格

**Files:**
- Create: `cascade/eval_grid.py`
- Modify: `scripts/monthly_backtest.py`（`_bar_dt`、`_close_ts`、`select_eval_indices` 改为转发；370–384 行的日线过滤改为调用 `filter_by_daily_sufficiency`）
- Test: `tests/test_eval_grid.py`（新建）

**Interfaces:**
- Consumes: `config.backtest_config` 的 `CONTEXT_BARS`、`HORIZON`、`STEP`、`EVAL_WINDOW_BARS`、`CONTEXT_DAYS`、`HORIZON_DAYS`；`DataStore.get_main_contract_1h(limit=99999)` 与 `get_main_continuous(limit=99999)`
- Produces: 文件职责一节里的 `select_eval_indices`、`filter_by_daily_sufficiency`、`baseline_eval_cutoffs`。`monthly_backtest.select_eval_indices`、`_bar_dt`、`_close_ts` 仍可从月度回测导入，行为与移动前相同。右边界是 `total - horizon - 1`。空序列或读库失败时 `baseline_eval_cutoffs` 抛 `RuntimeError`，不返回 `[]`。

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
import pytest


def test_select_eval_indices_right_bound_is_not_the_harvest_stop():
    from cascade.eval_grid import select_eval_indices
    total = 10000
    horizon = 24
    dts = (
        pd.date_range("2024-01-01", periods=total, freq="h")
        .strftime("%Y-%m-%d %H:%M:%S")
        .tolist()
    )
    indices = select_eval_indices(
        dts, context_bars=480, horizon=horizon, step=2, eval_window_bars=1200,
    )
    assert indices[-1] <= total - horizon - 1
    assert (total - horizon) not in indices


def test_baseline_eval_cutoffs_rejects_empty_read(monkeypatch):
    import pandas as pd
    from cascade import eval_grid

    class _Empty:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get_main_contract_1h(self, limit=99999):
            return pd.DataFrame()
        def get_main_continuous(self, limit=99999):
            return pd.DataFrame()

    monkeypatch.setattr(eval_grid, "DataStore", lambda symbol: _Empty())
    with pytest.raises(RuntimeError):
        eval_grid.baseline_eval_cutoffs("jd")


def test_eval_grid_does_not_import_torch_or_monthly_backtest():
    from pathlib import Path
    text = Path("cascade/eval_grid.py").read_text(encoding="utf-8")
    assert "import torch" not in text
    assert "monthly_backtest" not in text
```

第一条在函数还不存在时失败。`total=10000`、`horizon=24`、`step=2`、`context_bars=480`、`eval_window_bars=1200` 时，若有人抄 `_valid_n_for_symbol` 的 `range(left, len - HORIZON + 1, step)`，最后一个下标会是 `9976`，也就是 `total - horizon`，两条断言都会失败。不要改 `_valid_n_for_symbol`，也不要在这个测试里调用它。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_eval_grid.py -v`

Expected: FAIL，`cascade.eval_grid` 不存在。

- [ ] **Step 3: Write minimal implementation**

新建 `cascade/eval_grid.py`。把 `scripts/monthly_backtest.py` 里 `_bar_dt`、`_close_ts`、`select_eval_indices` 的函数体移进来。`select_eval_indices` 使用调用方传入的 `context_bars`、`horizon`、`step`、`eval_window_bars`，右边界写 `total - horizon - 1`。不要写 `len(dts) - horizon + 1`。

```python
def filter_by_daily_sufficiency(indices, hourly_dt, daily_df, min_daily_required: int):
    if daily_df is None or daily_df.empty:
        return list(indices)
    import bisect
    daily_dates = sorted(daily_df["dt"].astype(str).str[:10].tolist())
    kept = []
    for idx in indices:
        day = str(_bar_dt(hourly_dt, idx))[:10]
        if bisect.bisect_right(daily_dates, day) >= min_daily_required:
            kept.append(idx)
    return kept


def baseline_eval_cutoffs(symbol: str) -> list[str]:
    import config.backtest_config as bc
    from data.data_store import DataStore
    with DataStore(symbol) as store:
        hourly = store.get_main_contract_1h(limit=99999)
        daily = store.get_main_continuous(limit=99999)
    if hourly is None or hourly.empty:
        raise RuntimeError(f"{symbol} 小时线为空，不能把空网格当成通过")
    indices = select_eval_indices(
        hourly["dt"],
        context_bars=bc.CONTEXT_BARS,
        horizon=bc.HORIZON,
        step=bc.STEP,
        eval_window_bars=bc.EVAL_WINDOW_BARS,
    )
    need = max(bc.CONTEXT_DAYS - bc.HORIZON_DAYS, 100)
    indices = filter_by_daily_sufficiency(indices, hourly["dt"], daily, need)
    if not indices:
        raise RuntimeError(f"{symbol} 评估网格为空，不能把空文件当成通过")
    return [_close_ts(_bar_dt(hourly["dt"], idx)) for idx in indices]
```

不传 `eval_start_ts`、`eval_end_ts`、`max_points`。

`monthly_backtest.py` 改为：

```python
from cascade import eval_grid

def _bar_dt(dts, idx):
    return eval_grid._bar_dt(dts, idx)

def _close_ts(dt) -> str:
    return eval_grid._close_ts(dt)

def select_eval_indices(dts, *, eval_start_ts=None, max_points=None):
    return eval_grid.select_eval_indices(
        dts,
        eval_start_ts=eval_start_ts,
        max_points=max_points,
        context_bars=CONTEXT_BARS,
        horizon=HORIZON,
        step=STEP,
        eval_window_bars=EVAL_WINDOW_BARS,
    )
```

日线过滤那 370–384 行换成计算 `min_daily_required = max(CONTEXT_DAYS - HORIZON_DAYS, 100)`，再调用 `eval_grid.filter_by_daily_sufficiency(eval_indices, all_1h["dt"], daily_df, min_daily_required)`。这样现有测试打在 `mb.CONTEXT_DAYS` 上的补丁仍然生效。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_eval_grid.py tests/test_baseline_regen_loop.py::test_eval_indices_last_point_has_full_horizon tests/test_v4_window_anchor.py -v`

Expected: PASS。右边界测试和既有窗口锚测试都通过。不要为了让测试通过去改 `_valid_n_for_symbol`。

- [ ] **Step 5: Commit**

```bash
git add cascade/eval_grid.py scripts/monthly_backtest.py tests/test_eval_grid.py
git commit -m "move the eval grid next to the backtest and keep its right bound"
```

---

### Task 7: 后条件与唯一收口，四个旧守卫测试改写

**Files:**
- Modify: `cascade/eval_grid.py`
- Modify: `scripts/sup_evidence.py`（新增 `finalize_baseline_write`；这一截先不删 `_guard_confirm_from_ts_after_regen`，Task 10 在切换生产路径时删掉它和 `_HOMES` 那一行）
- Modify: `tests/test_baseline_reanchor.py`（86–131 行四个测试，以及文件头说明）
- Test: `tests/test_accept_baseline_file.py`（新建）

**Interfaces:**
- Consumes: `baseline_eval_cutoffs(symbol) -> list[str]`；`_current_protocol_fingerprint()`；`_prereg_confirm_from_ts(sym_lower, root)`
- Produces: `accept_baseline_file(path, expected_cutoffs, current_fingerprint) -> tuple[bool, str]`。`finalize_baseline_write(symbol, points_path, root, archive_path) -> bool`。后者在函数体内 `from cascade.eval_grid import baseline_eval_cutoffs, accept_baseline_file`，不增加 `expected_cutoffs` 参数。测试要换网格就打 `cascade.eval_grid.baseline_eval_cutoffs`。

这一截的生产调用还是旧守卫。四个直接调用旧名字的测试改成调用 `finalize_baseline_write`，这样 Task 10 删掉旧函数时不会留下仍要求拷回的断言。`_regen_baseline_with_archive` 在 Task 10 之前继续调用旧守卫。

- [ ] **Step 1: Write the failing test**

`tests/test_accept_baseline_file.py`：

```python
import json
from datetime import datetime, timedelta
from pathlib import Path

from cascade.eval_grid import accept_baseline_file


def _grid(n, start="2026-01-01 10:00:00"):
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    return [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def _write(path, cutoffs, fp="fp", **extra):
    with open(path, "w", encoding="utf-8") as f:
        for cutoff in cutoffs:
            row = {"cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                   "delta_real": 1.0, "protocol_fingerprint": fp}
            row.update(extra)
            f.write(json.dumps(row) + "\n")


def test_accept_requires_exact_grid_and_fingerprint(tmp_path):
    grid = _grid(4)
    path = tmp_path / "ok.jsonl"
    _write(path, grid, fp="fp")
    ok, _ = accept_baseline_file(str(path), grid, "fp")
    assert ok is True
    bad, reason = accept_baseline_file(str(path), grid, "")
    assert bad is False
    assert "指纹" in reason
    short, _ = accept_baseline_file(str(path), _grid(5), "fp")
    assert short is False
    superset = tmp_path / "super.jsonl"
    _write(superset, grid + ["2026-03-01 10:00:00"], fp="fp")
    over, _ = accept_baseline_file(str(superset), grid, "fp")
    assert over is False


def test_accept_allows_old_rows_without_new_keys(tmp_path):
    grid = _grid(2)
    path = tmp_path / "old.jsonl"
    _write(path, grid, fp="fp")
    ok, _ = accept_baseline_file(str(path), grid, "fp")
    assert ok is True
```

把 `tests/test_baseline_reanchor.py` 开头「守卫断言 = 重锚不得删除 `>= confirm_from_ts` 的基线 cutoff」改成：确认窗 cutoff 从网格消失是缺失报告；回滚目标必须通过当前网格后条件。

用下面四个函数替换 `test_guard_noop_without_prereg`、`test_guard_passes_when_new_file_keeps_confirm_window`、`test_guard_restores_archive_when_cutoffs_deleted`、`test_guard_noop_when_archive_has_no_confirm_points`。辅助函数 `_write_points` 和 `_write_prereg` 留着。

```python
def _patch_grid(monkeypatch, cutoffs, fp="fp_test"):
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(cutoffs))
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: fp)


def _rising_grid(n=588):
    from datetime import datetime, timedelta
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    return [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def test_guard_noop_without_prereg(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    before = pts.read_bytes()
    scar = tmp_path / "baseline_points_jd_nocov.archive_20261021T1500.jsonl"
    _write_points(scar, ["2026-10-21 10:00:00"])
    # 没有预注册。1 行归档不是恢复目标。活文件已经等于网格时收口为真，字节不变。
    tmp = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    tmp.write_bytes(before)
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(scar)) is True
    assert pts.read_bytes() == before
    assert scar.read_bytes() != pts.read_bytes()


def test_guard_passes_when_new_file_keeps_confirm_window(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    before = pts.read_bytes()
    archive = tmp_path / "baseline_points_jd_nocov.archive_20261021T1500.jsonl"
    _write_points(archive, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                            "2026-10-21 15:00:00"])
    tmp = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    tmp.write_bytes(before)
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(archive)) is True
    assert pts.read_bytes() == before
    assert not tmp.exists()


def test_guard_restores_archive_when_cutoffs_deleted(tmp_path, monkeypatch):
    """网格外的 3 行归档不得盖回一份网格有效的文件。"""
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    before = pts.read_bytes()
    archive = tmp_path / "baseline_points_jd_nocov.archive_20261021T1500.jsonl"
    _write_points(archive, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                            "2026-10-21 15:00:00"])
    rejected = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    _write_points(rejected, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                             "2026-10-21 15:00:00"])
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(archive)) is False
    assert pts.read_bytes() == before
    assert not rejected.exists()


def test_guard_noop_when_archive_has_no_confirm_points(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    archive = tmp_path / "baseline_points_jd_nocov.archive_20260930T1400.jsonl"
    _write_points(archive, ["2026-09-30 14:00:00"])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-10-01 00:00:00"])
    before = pts.read_bytes()
    rejected = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    _write_points(rejected, ["2026-10-01 00:00:00"])
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(archive)) is False
    assert pts.read_bytes() == before
    assert not rejected.exists()


def test_prereg_and_no_prereg_keep_the_same_grid_file(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    for symbol in ("sr", "bu"):
        root = tmp_path / symbol
        root.mkdir()
        if symbol == "sr":
            _write_prereg(str(root), [{"prereg_id": "p-sr", "symbol": "sr",
                                       "confirm_from_ts": "2026-10-03 00:00:00",
                                       "n_confirm_required": 986}])
        pts = root / f"baseline_points_{symbol}_nocov.jsonl"
        _write_points(pts, grid)
        before = pts.read_bytes()
        archive = root / f"baseline_points_{symbol}_nocov.archive_scar.jsonl"
        _write_points(archive, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                                "2026-10-21 15:00:00"])
        tmp = root / f".baseline_points_{symbol}_nocov.jsonl.tmp"
        tmp.write_bytes(before)
        assert sup_evidence.finalize_baseline_write(symbol, str(pts), str(root), str(archive)) is True
        assert pts.read_bytes() == before
    text = Path("tests/test_baseline_reanchor.py").read_text(encoding="utf-8")
    assert 'symbol == "jd"' not in text
    assert "symbol == 'jd'" not in text
```

`test_prereg_and_no_prereg_keep_the_same_grid_file` 就是规格的 (c) 和 (d)：`sr` 有预注册，`bu` 没有，两次都保留网格文件。失败断言不写 `symbol == "jd"`。`jd` 仍出现在上面改写的夹具里，但谓词不按品种分支。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_accept_baseline_file.py tests/test_baseline_reanchor.py::test_guard_restores_archive_when_cutoffs_deleted tests/test_baseline_reanchor.py::test_prereg_and_no_prereg_keep_the_same_grid_file -v`

Expected: FAIL。`accept_baseline_file` 或 `finalize_baseline_write` 还不存在。若旧测试还在，`test_guard_restores_archive_when_cutoffs_deleted` 会要求 `pts.read_bytes() == archive.read_bytes()`，那条断言必须已经被这一步的新函数替换，不能留在文件里。

- [ ] **Step 3: Write minimal implementation**

`accept_baseline_file`：

```python
def accept_baseline_file(path, expected_cutoffs, current_fingerprint):
    if not current_fingerprint:
        return False, "当前指纹为空"
    expected = list(expected_cutoffs)
    if not expected:
        return False, "网格为空"
    for prev, nxt in zip(expected, expected[1:]):
        if not prev < nxt:
            return False, "网格本身未严格递增"
    cutoffs = []
    required = ("cutoff", "dir_ok", "delta_pred", "delta_real", "protocol_fingerprint")
    try:
        with open(path, encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    return False, f"第 {lineno} 行不是对象"
                for key in required:
                    if key not in rec:
                        return False, f"第 {lineno} 行缺 {key}"
                if rec["protocol_fingerprint"] != current_fingerprint:
                    return False, f"第 {lineno} 行指纹不符"
                cutoffs.append(str(rec["cutoff"]))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"无法读取: {exc}"
    for prev, nxt in zip(cutoffs, cutoffs[1:]):
        if not prev < nxt:
            return False, "cutoff 未严格递增"
    if cutoffs != expected:
        return False, f"cutoff 序列与网格不等: 文件 {len(cutoffs)} 行, 网格 {len(expected)} 行"
    return True, "ok"
```

不要求 `endpoint_delta` 或 `position_sign`。不读预注册。

`finalize_baseline_write` 放在 `scripts/sup_evidence.py`：

1. 在函数体内 `from cascade.eval_grid import baseline_eval_cutoffs, accept_baseline_file`。`expected = baseline_eval_cutoffs(symbol)`，`fp = _current_protocol_fingerprint()`。这两步若抛错，函数自己接住，不换名，返回 `False`。不要把这次异常抛回启动循环。指纹为空同样不换名，返回 `False`。
2. 临时文件路径是 `points_path` 同目录的 `".{文件名}.tmp"`，与 `generate_baseline_points.py` 131–134 行一致。临时文件存在就对它做 `accept_baseline_file`。不存在时，若活文件已经通过则返回 `True`，否则返回 `False`。
3. 临时文件通过：`os.replace` 换名到 `points_path`。日志写品种、行数、网格首尾 cutoff、指纹前 16 位。若 `_prereg_confirm_from_ts` 非空，取 `min(confirm_from_ts)`，读 `archive_path` 里 `>=` 该边界且不在 `expected` 里的 cutoff。有这样的 cutoff 就警告，文案包含「确认样本缺失，不回滚探索基线」，并带上品种、边界、缺失条数；列表超过 8 条时只打前 8 条和总数。返回 `True`。
4. 临时文件不通过：不换名。日志写失败原因和临时文件的 cutoff 条数，然后删除临时文件。在同目录找 `baseline_points_{symbol}_nocov.archive_*.jsonl`（文件名以活文件去掉 `.jsonl` 之后的词干加 `.archive_` 开头），按 mtime 从新到旧。第一份自己通过 `accept_baseline_file` 的归档用 `shutil.copy2` 盖到活文件，日志写归档文件名，返回 `False`。一份都没有：活文件保持换名之前的字节，返回 `False`。禁止恢复一份自己通不过的归档。

不要在这个函数里写 `if symbol == "jd"`。不要调用 `_guard_confirm_from_ts_after_regen`。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_accept_baseline_file.py tests/test_baseline_reanchor.py -v`

Expected: PASS。`test_reanchor_reason_*` 仍测原来的纯函数。四个旧名字的测试不再调用 `_guard_confirm_from_ts_after_regen`。`test_ensure_baselines_reanchors_on_stale_baseline` 和 `test_ensure_baselines_no_regen_when_fresh` 这一截先保持原样，它们仍走旧的三条路径；Task 10 再改。若这一步已经因为导入 `finalize_baseline_write` 而让那两个集成测试失败，只修导入，不要提前改它们的断言。

- [ ] **Step 5: Commit**

```bash
git add cascade/eval_grid.py scripts/sup_evidence.py tests/test_accept_baseline_file.py tests/test_baseline_reanchor.py
git commit -m "accept a baseline only when its cutoffs equal the injected grid"
```

---

### Task 8: finalize=False 只写临时文件，错误点不发布子集

**Files:**
- Modify: `scripts/generate_baseline_points.py`
- Modify: `scripts/incremental_baseline.py`
- Modify: `tests/test_generate_baseline_points.py`
- Modify: `tests/test_baseline_record_and_resume.py`

**Interfaces:**
- Consumes: `baseline_jsonl_record`；`finalize_baseline_write(symbol, points_path, root, archive_path) -> bool`；`_archive_baseline_before_regen`
- Produces: `generate(..., finalize: bool = True)` 与 `incremental_generate(..., finalize: bool = True)`。`finalize=False` 不接受、不回滚、不归档。任一评估点带 `error`：删除已写下的临时文件，返回 `None`。没有错误点：写临时文件，不换名，返回最后一笔 cutoff。写失败或零行返回 `None`。`finalize=True` 是命令行默认：写临时文件之前自己归档活文件一次，然后调用 `finalize_baseline_write`。返回假则命令行得到 `None`。返回真则返回已经换上的活文件的最后一笔 cutoff。

- [ ] **Step 1: Write the failing test**

在 `tests/test_generate_baseline_points.py` 增加。现有的 `test_generate_writes_jsonl_and_metrics` 改为把收口桩成「把临时文件换到活文件并返回真」，因为默认 `finalize=True` 不再自己 `rename`：

```python
def _accept_rename(symbol, points_path, root, archive_path):
    live = Path(points_path)
    tmp = live.with_name("." + live.name + ".tmp")
    tmp.replace(live)
    return True


def test_finalize_false_leaves_temp_and_skips_accept(tmp_path, monkeypatch):
    import scripts.generate_baseline_points as gbp
    points = [{"cutoff": "2026-02-01 10:00:00", "dir_ok": True,
               "delta_pred": 1.0, "delta_real": 1.0}]
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: {"points": points})
    called = {"n": 0}

    def _no(symbol, points_path, root, archive_path):
        called["n"] += 1
        return True

    monkeypatch.setattr("scripts.sup_evidence.finalize_baseline_write", _no)
    got = gbp.generate("ss", cov="ccl", root=str(tmp_path), finalize=False)
    live = tmp_path / "task_FM" / "config" / "baseline_points_ss.jsonl"
    tmp = tmp_path / "task_FM" / "config" / ".baseline_points_ss.jsonl.tmp"
    assert got == "2026-02-01 10:00:00"
    assert tmp.exists()
    assert not live.exists()
    assert called["n"] == 0


def test_error_point_is_not_a_publishable_file(tmp_path, monkeypatch):
    import scripts.generate_baseline_points as gbp
    points = [
        {"cutoff": "2026-02-01 10:00:00", "dir_ok": True, "delta_pred": 1.0, "delta_real": 1.0},
        {"cutoff": "2026-02-01 12:00:00", "error": "model failed"},
    ]
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: {"points": points})
    got = gbp.generate("ss", cov="ccl", root=str(tmp_path), finalize=False)
    cfg = tmp_path / "task_FM" / "config"
    assert got is None
    assert not (cfg / ".baseline_points_ss.jsonl.tmp").exists()
    assert not (cfg / "baseline_points_ss.jsonl").exists()
```

`test_generate_writes_jsonl_and_metrics` 在调用 `gbp.generate` 之前加上：

```python
monkeypatch.setattr("scripts.sup_evidence.finalize_baseline_write", _accept_rename)
```

`tests/test_baseline_record_and_resume.py` 的增量测试改为 `incremental_generate(..., finalize=False)`，并断言活文件没有被换成只含回测返回值的那一份之前，临时文件存在、活文件仍是夹具里的旧行。源码断言保持不变。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_generate_baseline_points.py::test_finalize_false_leaves_temp_and_skips_accept tests/test_generate_baseline_points.py::test_error_point_is_not_a_publishable_file -v`

Expected: FAIL。`generate` 不接受 `finalize`，或者带 `error` 的点被跳过后仍然换名。

- [ ] **Step 3: Write minimal implementation**

两个函数都增加 `finalize: bool = True`。写循环里删掉 `if "error" in pt: continue`。先扫描 `result["points"]`：任何一个点含有键 `error`，若临时文件已存在就删掉，日志写品种、错误点数、最多 5 条 cutoff，返回 `None`。没有错误点才用 `baseline_jsonl_record` 写临时文件。

`finalize=False`：不调用 `accept_baseline_file`，不调用 `finalize_baseline_write`，不调用 `_archive_baseline_before_regen`，不 `rename`。临时文件至少一行就返回最后一笔 cutoff，否则返回 `None`。

`finalize=True`：写临时文件之前调用一次 `_archive_baseline_before_regen(活文件路径)`。然后调用 `scripts.sup_evidence.finalize_baseline_write(sym_lower, str(jsonl_file), root, archive_path)`。返回假就让函数返回 `None`。返回真就读活文件最后一笔 cutoff 并返回它。不要在脚本里再 `rename` 一次。

`generate` 里对 `finalize_baseline_write` 的查找必须是运行时属性查找 `scripts.sup_evidence.finalize_baseline_write`，这样测试的 monkeypatch 打在这个名字上就会生效。

增量脚本同样处理。`finalize=False` 时不要再 `temp_file.rename(jsonl_file)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_generate_baseline_points.py tests/test_baseline_record_and_resume.py -v`

Expected: PASS。120 个相同 cutoff 的旧测试仍通过，因为它把收口桩成了换名。它不得因此去打开品种库。

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_baseline_points.py scripts/incremental_baseline.py tests/test_generate_baseline_points.py tests/test_baseline_record_and_resume.py
git commit -m "keep a failed baseline publish off the live filename"
```

---

### Task 9: 增量只复用网格上的当前指纹行

**Files:**
- Modify: `scripts/incremental_baseline.py`
- Test: `tests/test_baseline_record_and_resume.py`

**Interfaces:**
- Consumes: `baseline_eval_cutoffs(symbol) -> list[str]`；Task 4 的续跑合并；Task 8 的 `finalize=False`
- Produces: `resumed_points` 只含 cutoff 属于网格、且带 `dir_ok` / `delta_pred` / `delta_real`、且 `protocol_fingerprint` 等于当前指纹的行。键仍是 `(symbol_lower, cutoff)`。调用仍不传 `eval_start_ts` 和 `completed`。写入仍只用 `result["points"]`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_baseline_record_and_resume.py` 增加：

```python
def test_incremental_reuses_only_grid_rows(tmp_path, monkeypatch):
    import json
    import scripts.incremental_baseline as ib
    import scripts.monthly_backtest as mb

    class _Model:
        def __init__(self, *a, **k):
            self.model = None

    monkeypatch.setattr("cascade.daily_model.DailyModel", _Model)
    monkeypatch.setattr("cascade.hourly_model.HourlyModel", _Model)
    monkeypatch.setattr(
        "task_FM.evaluations.fm_eval.evaluator.compute_protocol_fingerprint",
        lambda: "fp",
    )
    grid = ["2026-02-01 10:00:00", "2026-02-01 12:00:00"]
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    captured = {}

    def _bt(*a, **k):
        captured.update(k)
        return {"points": [
            {"cutoff": c, "dir_ok": True, "delta_pred": 1.0, "delta_real": 1.0}
            for c in grid
        ]}

    monkeypatch.setattr(mb, "run_symbol_backtest", _bt)
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True)
    rows = [
        {"cutoff": "2026-01-01 10:00:00", "dir_ok": True, "delta_pred": 1.0,
         "delta_real": 1.0, "protocol_fingerprint": "fp"},
        {"cutoff": "2026-02-01 10:00:00", "dir_ok": True, "delta_pred": 1.0,
         "delta_real": 1.0, "protocol_fingerprint": "fp"},
        {"cutoff": "2026-02-01 12:00:00", "dir_ok": True, "delta_pred": 1.0,
         "delta_real": 1.0, "protocol_fingerprint": "old"},
    ]
    (cfg / "baseline_points_jd_nocov.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8",
    )
    ib.incremental_generate("jd", None, str(tmp_path), finalize=False)
    assert "eval_start_ts" not in captured
    keys = set(captured["resumed_points"])
    assert keys == {("jd", "2026-02-01 10:00:00")}
```

网格外的 1 月行和指纹不符的 12:00 行都不得进入 `resumed_points`。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_baseline_record_and_resume.py::test_incremental_reuses_only_grid_rows -v`

Expected: FAIL。当前增量会把所有指纹相符的旧行都放进 `resumed_points`，包括 1 月那一行。

- [ ] **Step 3: Write minimal implementation**

在组装 `resumed_points` 之前调用 `baseline_eval_cutoffs(symbol)`。只保留 cutoff 属于这个列表、三键齐全、指纹等于当前指纹的行。网格函数抛错时让异常离开 `incremental_generate`，不要收成 `None`。监督循环会把它当成写入前的网格失败。读网格失败的「不记停滞、不启动全量」由 Task 10 的品种循环负责；这个函数自己不要吞掉。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_baseline_record_and_resume.py -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/incremental_baseline.py tests/test_baseline_record_and_resume.py
git commit -m "reuse only current-grid baseline rows when extending a file"
```

---

### Task 10: ensure_baselines 只问一次后条件

**Files:**
- Modify: `scripts/sup_evidence.py`（`_incremental_or_regen` 1425–1446 行，`_regen_baseline_with_archive` 1449–1467 行，`ensure_baselines` 1536–1611 行；删除 `_guard_confirm_from_ts_after_regen`）
- Modify: `scripts/praxist_supervisor.py`（92 行 `_HOMES`）
- Modify: `tests/test_baseline_reanchor.py`（154、169 行两个 ensure 测试，以及 `_setup_healthy_baseline`）
- Modify: `tests/test_baseline_archival.py`（78 行）
- Modify: `tests/test_baseline_regen_loop.py`（79、94、116、135、225 行）
- Modify: `tests/test_ensure_baselines_fingerprint.py`（111–179 行的 ensure 测试，以及它们用的 `_write_baseline`）
- Test: `tests/test_ensure_baselines_postcondition.py`（新建，网格失败与写入中途抛出）

**Interfaces:**
- Consumes: `accept_baseline_file`；`finalize_baseline_write`；`baseline_eval_cutoffs`；`incremental_generate(..., finalize=False)`；`generate(..., finalize=False)`；`_archive_baseline_before_regen`；`_stall_still_blocks`；`_remember_stall`；`_current_protocol_fingerprint`
- Produces: `ensure_baselines` 对每个品种先验收。通过就不写。不通过且断路器放行时，先归档一次，再按 Global Constraints 里那句失败路径做。`ensure_baselines` 不再调用 `_baseline_reanchor_reason`。`_regen_baseline_with_archive` 若仍存在，只许 `generate(..., finalize=False)`，不得归档，不得 `copy2`，不得把未收口的 cutoff 返回出去。全量导入保持 `import generate_baseline_points as gbp`，测试继续把假模块放进 `sys.modules["generate_baseline_points"]`。

- [ ] **Step 1: Write the failing test**

新建 `tests/test_ensure_baselines_postcondition.py`。夹具写一份五行齐全、严格递增、指纹为 `fp_test` 的活文件，并打上 `cascade.eval_grid.baseline_eval_cutoffs`。增量替身和全量假模块分开计数。

```python
import json
import os
import sys
from datetime import datetime, timedelta

import sup_evidence
import sup_lifecycle
import sup_state


def _grid(n=4):
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    return [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as handle:
        for cutoff in cutoffs:
            handle.write(json.dumps({
                "cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                "delta_real": 1.0, "protocol_fingerprint": fp,
            }) + "\n")


def _prepare(root, symbol="jd", cutoffs=None, fp="fp_test"):
    config = os.path.join(root, "task_FM", "config")
    os.makedirs(config, exist_ok=True)
    with open(os.path.join(config, "baseline_metrics.json"), "w", encoding="utf-8") as handle:
        json.dump({symbol: {"n": 4}}, handle)
    path = os.path.join(config, f"baseline_points_{symbol}_nocov.jsonl")
    _write_points(path, cutoffs if cutoffs is not None else ["2026-10-21 10:00:00"], fp=fp)
    return path


class _FakeGbp:
    def __init__(self):
        self.calls = []

    def baseline_filename(self, sym, cov):
        return f"baseline_points_{sym}_nocov.jsonl"

    def generate(self, sym, cov, root, finalize=False):
        self.calls.append((sym, cov, finalize))


def _arm(monkeypatch, root, data_dt="2026-10-09 14:00:00", grid=None, incremental=None):
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: data_dt)
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr(sup_lifecycle, "_write_heartbeat", lambda: None)
    chosen = grid if grid is not None else _grid()
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(chosen))
    calls = {"incremental": 0}

    def _incremental(*args, **kwargs):
        calls["incremental"] += 1
        if incremental is not None:
            return incremental(*args, **kwargs)
        return None

    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", _incremental)
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    return fake, calls


def test_incremental_none_runs_generate_once_and_stalls_only_after_it_fails(tmp_path, monkeypatch):
    _prepare(str(tmp_path))
    fake, calls = _arm(monkeypatch, str(tmp_path))
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == [("jd", None, False)]
    fake.calls.clear()
    calls["incremental"] = 0
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 0
    assert fake.calls == []


def test_publishable_temp_does_not_call_generate(tmp_path, monkeypatch):
    grid = _grid()
    path = _prepare(str(tmp_path), cutoffs=["2026-10-21 10:00:00"])

    def _write_temp(symbol, cov, root, finalize=False):
        tmp = os.path.join(root, "task_FM", "config", ".baseline_points_jd_nocov.jsonl.tmp")
        _write_points(tmp, grid)
        return grid[-1]

    fake, calls = _arm(monkeypatch, str(tmp_path), grid=grid, incremental=_write_temp)
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == []
    assert [json.loads(line)["cutoff"] for line in open(path, encoding="utf-8")] == grid
    breaker = os.path.join(str(tmp_path), "data", "cache", "baseline_regen_breaker.json")
    if os.path.exists(breaker):
        assert "jd" not in json.load(open(breaker, encoding="utf-8"))
    calls["incremental"] = 0
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 0
    assert fake.calls == []


def test_grid_read_error_skips_symbol_without_stall(tmp_path, monkeypatch):
    grid = _grid()
    _prepare(str(tmp_path), symbol="bb", cutoffs=grid)
    config = os.path.join(str(tmp_path), "task_FM", "config")
    with open(os.path.join(config, "baseline_metrics.json"), "w", encoding="utf-8") as handle:
        json.dump({"aa": {"n": 4}, "bb": {"n": 4}}, handle)
    _write_points(os.path.join(config, "baseline_points_aa_nocov.jsonl"), ["2026-10-21 10:00:00"])
    state = {"fail_aa": True}

    def _grid_for(symbol):
        if symbol == "aa" and state["fail_aa"]:
            raise RuntimeError("db down")
        return list(grid)

    fake, calls = _arm(monkeypatch, str(tmp_path), grid=grid)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", _grid_for)
    sup_evidence.ensure_baselines(["aa", "bb"], str(tmp_path))
    assert fake.calls == []
    assert calls["incremental"] == 0
    state["fail_aa"] = False
    sup_evidence.ensure_baselines(["aa", "bb"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == [("aa", None, False)]


def test_write_exception_stalls_without_a_second_generate(tmp_path, monkeypatch):
    _prepare(str(tmp_path))

    def _boom(*args, **kwargs):
        raise RuntimeError("write exploded")

    fake, calls = _arm(monkeypatch, str(tmp_path), incremental=_boom)
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 1
    assert fake.calls == []
    calls["incremental"] = 0
    sup_evidence.ensure_baselines(["jd"], str(tmp_path))
    assert calls["incremental"] == 0
    assert fake.calls == []
```

`_arm` 里的增量替身默认返回 `None` 且不留临时文件。`test_publishable_temp_does_not_call_generate` 的替身必须真的把临时文件写在 `task_FM/config/.baseline_points_jd_nocov.jsonl.tmp`。四个测试的断言就是上面这些等式，不要再留注释代替断言。

`test_fingerprint_ok` 到 `test_fingerprint_skips_blank_lines` 保持原样。进入 `ensure_baselines` 的夹具改成下面这样。所有假 `generate` 都要收下 `finalize=False`，调用时追加 `(symbol, cov)`，不要把 `finalize` 算进「有没有调用」的比较，除非断言本身在看它。

`tests/test_ensure_baselines_fingerprint.py` 文件头增加 `from datetime import datetime, timedelta`。然后增加这个写入函数，并让 `fake_env` 在原有指纹桩之外再打两处：

```python
def _write_strict(path: Path, n_lines: int, fp: str):
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    cutoffs = []
    with path.open("w", encoding="utf-8") as handle:
        for i in range(n_lines):
            cutoff = (t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S")
            cutoffs.append(cutoff)
            handle.write(json.dumps({
                "cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                "delta_real": 1.0, "protocol_fingerprint": fp,
            }) + "\n")
    return cutoffs
```

```python
monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)
monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: ["2099-01-01 10:00:00"])
```

`_FakeGBP.generate` 改为 `def generate(self, symbol, cov, root, finalize=False)`，`self.calls.append((symbol, cov))`。然后用这些函数替换原来的 ensure 测试：

```python
def test_regenerates_on_fingerprint_mismatch(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "rb")
    cutoffs = _write_strict(cfg / "baseline_points_rb_nocov.jsonl", 4, OLD_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["rb"], str(root))
    assert fake.calls == [("rb", None)]


def test_skips_when_fingerprint_matches(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "ss")
    cutoffs = _write_strict(cfg / "baseline_points_ss_nocov.jsonl", 4, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["ss"], str(root))
    assert fake.calls == []


def test_regenerates_when_fingerprint_missing(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "m")
    cutoffs = _write_strict(cfg / "baseline_points_m_nocov.jsonl", 4, CUR_FP)
    text = (cfg / "baseline_points_m_nocov.jsonl").read_text(encoding="utf-8")
    (cfg / "baseline_points_m_nocov.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in json.loads(line).items() if k != "protocol_fingerprint"})
                  for line in text.splitlines() if line.strip()) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["m"], str(root))
    assert fake.calls == [("m", None)]


def test_regenerates_when_too_few_lines(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "cj")
    live = _write_strict(cfg / "baseline_points_cj_nocov.jsonl", 50, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: live[:4])
    ensure_baselines(["cj"], str(root))
    assert fake.calls == [("cj", None)]


def test_metrics_gap_does_not_regen_a_file_that_matches_the_grid(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text("{}", encoding="utf-8")
    cutoffs = _write_strict(cfg / "baseline_points_fu_nocov.jsonl", 4, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["fu"], str(root))
    assert fake.calls == []


def test_short_file_equal_to_grid_is_not_rewritten(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "cj")
    cutoffs = _write_strict(cfg / "baseline_points_cj_nocov.jsonl", 4, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["cj"], str(root))
    assert fake.calls == []


def test_fingerprint_check_skipped_when_current_unavailable(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    monkeypatch.setattr("sup_evidence._current_protocol_fingerprint", lambda: None)
    _write_metrics(cfg, "sr")
    before = _write_strict(cfg / "baseline_points_sr_nocov.jsonl", 4, OLD_FP)
    path = cfg / "baseline_points_sr_nocov.jsonl"
    raw = path.read_bytes()
    ensure_baselines(["sr"], str(root))
    assert fake.calls == []
    assert path.read_bytes() == raw
    assert before


def test_no_metrics_entry_regenerates(fake_env):
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text("{}", encoding="utf-8")
    ensure_baselines(["fu"], str(root))
    assert fake.calls == [("fu", None)]


def test_multiple_symbols_mixed(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text(
        json.dumps({"ss": {"n": 4}, "rb": {"n": 4}}), encoding="utf-8")
    ss = _write_strict(cfg / "baseline_points_ss_nocov.jsonl", 4, CUR_FP)
    rb = _write_strict(cfg / "baseline_points_rb_nocov.jsonl", 4, OLD_FP)
    grids = {"ss": ss, "rb": rb}
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: grids[symbol])
    ensure_baselines(["ss", "rb"], str(root))
    assert fake.calls == [("rb", None)]
```

`tests/test_baseline_reanchor.py` 里 `_setup_healthy_baseline` 不再把同一个 cutoff 重复写 n 行。换成写 `_grid(4)` 或写一份与注入网格不同的单行。两个 ensure 测试换成：

```python
def test_ensure_baselines_no_regen_when_fresh(tmp_path, monkeypatch):
    grid = _rising_grid(4)
    config = tmp_path / "task_FM" / "config"
    config.mkdir(parents=True)
    (config / "baseline_metrics.json").write_text(json.dumps({"jd": {"n": 4}}), encoding="utf-8")
    pts = config / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-01 10:00:00")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)
    fake = _FakeGbp()

    def _generate(sym, cov, root, finalize=False):
        fake.calls.append((sym, cov, root))

    fake.generate = _generate
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    sup.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == []
    assert list(config.glob("baseline_points_jd_nocov.archive_*.jsonl")) == []


def test_ensure_baselines_reanchors_on_stale_baseline(tmp_path, monkeypatch):
    config = tmp_path / "task_FM" / "config"
    config.mkdir(parents=True)
    (config / "baseline_metrics.json").write_text(json.dumps({"jd": {"n": 4}}), encoding="utf-8")
    pts = config / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-09-16 15:00:00"])
    order = []
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-09-30 14:00:00")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: _rising_grid(4))

    def _incremental(*a, **k):
        order.append("incremental")
        return None

    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", _incremental)
    fake = _FakeGbp()

    def _generate(sym, cov, root, finalize=False):
        order.append("generate")
        fake.calls.append((sym, cov, root))

    fake.generate = _generate
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    sup.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == [("jd", None, str(tmp_path))]
    archives = list(config.glob("baseline_points_jd_nocov.archive_*.jsonl"))
    assert len(archives) == 1
    assert order == ["incremental", "generate"]
```

`_FakeGbp.generate` 在这个文件里也改成 `def generate(self, sym, cov, root, finalize=False)`。上面两个测试都把不带 `self` 的函数赋给实例。赋到实例上之后，调用不会再自动绑定 `self`；写成 `lambda self, ...` 会把品种名收进第一个参数。

`tests/test_baseline_archival.py` 里 `_FakeGbp.generate` 改为 `def generate(self, sym, cov, root, finalize=False)`，`self.calls.append((sym, cov, root))`。`test_ensure_baselines_archives_before_regen` 整段换成：

```python
def test_ensure_baselines_archives_before_regen(tmp_path, monkeypatch):
    config_dir = tmp_path / "task_FM" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "baseline_metrics.json").write_text(
        json.dumps({"jd": {"n": 4}}), encoding="utf-8")
    pts = config_dir / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2025-09-30 14:00:00"], fp="fp_old")
    grid = [
        "2026-01-01 10:00:00", "2026-01-01 12:00:00",
        "2026-01-01 14:00:00", "2026-01-01 16:00:00",
    ]
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_cur")
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)
    monkeypatch.setattr("sup_state._latest_data_dt", lambda symbol: "2026-10-09 14:00:00")
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    sup.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == [("jd", None, str(tmp_path))]
    archives = list(config_dir.glob("baseline_points_jd_nocov.archive_*.jsonl"))
    assert len(archives) == 1
    assert os.path.basename(archives[0]) == "baseline_points_jd_nocov.archive_20250930T1400.jsonl"
```

这个文件今天没有 `import sup_state`。`monkeypatch.setattr("sup_state._latest_data_dt", ...)` 打的是已经由 `sup_evidence` 载入的模块，用来挡住第二次收口为假时去读活库。旧指纹通不过当前网格，所以会归档一次再调用一次 `generate`。不要再写第二份归档。上面四个纯归档测试保持原样。

`tests/test_baseline_regen_loop.py` 的 `_arm` 增加：

```python
monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: [
    "2026-01-01 10:00:00", "2026-01-01 12:00:00", "2026-01-01 14:00:00", "2026-01-01 16:00:00",
])
monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)
```

`_setup_healthy_baseline` 改成只写一笔 `2026-09-16 15:00:00`，五行齐全，指纹 `fp_test`。这不等于上面的四笔网格。`_FakeGbp.generate` 改为 `def generate(self, sym, cov, root, finalize=False)`。四个停滞测试的次数保持「第一次恰好一次 generate，同一数据末端的下一次为零」。`test_timestamp_spelling_difference_does_not_clear_stall` 删掉对 `_baseline_reanchor_reason` 的 monkeypatch，第二次数据末端仍用 `"2026-10-09T14:00:00.000000000"`。`test_newer_data_end_allows_regen_after_restart` 的三次调用次数仍是 1、1、0。

`test_regen_returns_cutoff` 整段换成：

```python
def test_regen_returns_cutoff(tmp_path, monkeypatch):
    grid = ["2026-01-02 10:00:00", "2026-01-02 12:00:00"]
    config_dir = os.path.join(str(tmp_path), "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    points_path = os.path.join(config_dir, "baseline_points_jd_nocov.jsonl")
    _write_points(points_path, ["2026-09-24 15:00:00"], fp="fp_test")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)

    class _WriteGrid:
        def generate(self, sym, cov, root, finalize=False):
            tmp = os.path.join(config_dir, ".baseline_points_jd_nocov.jsonl.tmp")
            _write_points(tmp, grid, fp="fp_test")

    monkeypatch.setitem(sys.modules, "generate_baseline_points", _WriteGrid())
    result = sup_evidence._incremental_or_regen("jd", points_path, str(tmp_path), None)
    assert result == grid[-1]

def test_short_generate_does_not_become_the_return_value(tmp_path, monkeypatch):
    grid = ["2026-01-02 10:00:00", "2026-01-02 12:00:00", "2026-01-02 14:00:00"]
    config_dir = os.path.join(str(tmp_path), "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    points_path = os.path.join(config_dir, "baseline_points_jd_nocov.jsonl")
    _write_points(points_path, ["2026-09-24 15:00:00"], fp="fp_test")
    before = open(points_path, "rb").read()
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)

    class _WriteShort:
        def generate(self, sym, cov, root, finalize=False):
            tmp = os.path.join(config_dir, ".baseline_points_jd_nocov.jsonl.tmp")
            _write_points(tmp, ["2026-09-25 15:00:00"], fp="fp_test")

    monkeypatch.setitem(sys.modules, "generate_baseline_points", _WriteShort())
    result = sup_evidence._incremental_or_regen("jd", points_path, str(tmp_path), None)
    assert result is None
    assert open(points_path, "rb").read() == before
    assert not os.path.exists(os.path.join(config_dir, ".baseline_points_jd_nocov.jsonl.tmp"))
```

`_write_baseline` 今天的 `2026-01-01 {i:02d}:00:00` 只允许留在不进入 `ensure_baselines` 的指纹纯函数测试里。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_ensure_baselines_postcondition.py tests/test_baseline_regen_loop.py::test_stalled_baseline_is_not_regenerated_after_process_restart tests/test_ensure_baselines_fingerprint.py::test_skips_when_fingerprint_matches tests/test_baseline_reanchor.py::test_ensure_baselines_no_regen_when_fresh -v`

Expected: FAIL。当前启动仍按行数、指纹和重锚分三条路；重复 cutoff 的「健康」夹具会进入重生；网格读取还没有被品种循环接住。

- [ ] **Step 3: Write minimal implementation**

删除 `_guard_confirm_from_ts_after_regen` 整个函数。删除 `scripts/praxist_supervisor.py` `_HOMES` 里 `"_guard_confirm_from_ts_after_regen": sup_evidence` 那一行。`__all__` 里如果也有这个名字，一并删除。不要留一个仍做超集 `copy2` 的包装。

`ensure_baselines` 保留拿锁、函数开头的 `import generate_baseline_points as gbp`、读 `baseline_metrics.json`、以及「metrics 文件读失败且 `pytest` 在 `sys.modules` 里就整函数返回」。不要把这条早退搬到函数顶部，也不要扩大成「点文件已经等于网格也返回」。早退之后仍调用 `_load_regen_breaker(root)`，用这个 root 的磁盘记录替换进程内字典。删掉「metrics 里没有正的 `n` 就直接重生」：缺条目不再单独触发写入；没有点文件时后条件为假，仍会进入一次写入。`metrics` 这次读取留下来，后面不要再用 `metrics.get(sym)` 决定是否重生。`points_path` 仍是 `os.path.join(config_dir, gbp.baseline_filename(sym_lower, None))`。品种循环仍是 `for sym in sorted(symbols)`，每个品种自己 `try` / `finally`，`finally` 里仍写心跳。网格失败用 `continue`，不要让它变成停滞。`scripts/sup_loops.py` 1079–1083 行那个外层 `except` 不是隔离边界，不要改它来充当品种隔离。

```python
_acquire_ensure_lock()
try:
    import generate_baseline_points as gbp
except ImportError:
    return
config_dir = os.path.join(root, "task_FM", "config")
metrics_path = os.path.join(config_dir, "baseline_metrics.json")
try:
    with open(metrics_path, encoding="utf-8") as handle:
        metrics = json.load(handle)
except (OSError, json.JSONDecodeError):
    metrics = {}
    if "pytest" in sys.modules:
        return
_load_regen_breaker(root)
for sym in sorted(symbols):
    try:
        sym_lower = sym.lower()
        points_path = os.path.join(config_dir, gbp.baseline_filename(sym_lower, None))
        try:
            from cascade.eval_grid import accept_baseline_file, baseline_eval_cutoffs
            expected = baseline_eval_cutoffs(sym_lower)
        except Exception as exc:
            print(
                f"[ERROR] ensure_baselines: {sym_lower} 网格读取失败: {exc}。本轮跳过该品种，不记停滞",
                file=sys.stderr,
            )
            continue
        fp = _current_protocol_fingerprint()
        if not fp:
            print(
                f"[WARN] ensure_baselines: {sym_lower} 当前指纹算不出。不重生、不删文件、不记停滞",
                file=sys.stderr,
            )
            continue
        ok, _reason = accept_baseline_file(points_path, expected, fp)
        if ok:
            continue
        if _stall_still_blocks(sym_lower, root):
            continue
        archive = _archive_baseline_before_regen(points_path)
        try:
            new_cutoff = _incremental_or_regen(sym_lower, points_path, root, archive)
        except Exception as exc:
            print(f"[ERROR] ensure_baselines: {sym_lower} 写入中途失败: {exc}", file=sys.stderr)
            _remember_stall(sym_lower, root, sup_state._latest_data_dt(sym_lower))
            continue
        if new_cutoff is None:
            _remember_stall(sym_lower, root, sup_state._latest_data_dt(sym_lower))
    finally:
        sup_lifecycle._write_heartbeat()
```

删掉现在 1603–1604 行「推进不足 7 天就 `_remember_stall`」。`_baseline_reanchor_reason` 函数留在原地，`ensure_baselines` 不再调用它。

`_incremental_or_regen` 不再在函数开头归档。它只按这一句做，不要改写结尾：`incremental_generate` 返回后：已有可发布临时文件就调用 `finalize_baseline_write`。第一次收口为真就换名、返回网格末笔、不再运行 `generate`。没有可发布临时文件（包括任一评估点带 `error`，或换名前失败），或临时文件未通过，这是第一次接受失败，不是提前结束；没有临时文件且活文件尚未通过时，把第一次收口当成假。只有第一次收口为假，才恰好运行一次 `generate(..., finalize=False)` 并第二次调用 `finalize_baseline_write`。只有第二次收口为假才 `_remember_stall`。第一次为真不记停滞。读网格或写入抛出的异常不是这个 `None`：留在品种循环的 `except` 里记日志；读网格失败不记停滞、不启动全量；写入中途抛出则记停滞，并且不再启动另一次全量。

```python
def _temp_path(points_path):
    directory, name = os.path.split(points_path)
    return os.path.join(directory, "." + name + ".tmp")


def _incremental_or_regen(sym_lower, points_path, root, archive_path):
    from scripts import incremental_baseline as ib
    temp = _temp_path(points_path)
    returned = ib.incremental_generate(sym_lower, None, root, finalize=False)
    publishable = returned is not None and os.path.exists(temp)
    if publishable and finalize_baseline_write(sym_lower, points_path, root, archive_path):
        return _read_last_cutoff(points_path)
    # 第一次收口为假。不再归档。
    try:
        import generate_baseline_points as gbp
        gbp.generate(sym_lower, None, root, finalize=False)
    except Exception as exc:
        print(f"[ERROR] ensure_baselines: {sym_lower} 全量写入失败: {exc}", file=sys.stderr)
        return None
    if finalize_baseline_write(sym_lower, points_path, root, archive_path):
        return _read_last_cutoff(points_path)
    return None
```

`incremental_generate` 自己抛出的异常不要在这里收成 `None`，让它落到品种循环的 `except`：记停滞，并且不要执行后面的 `generate`。`incremental_generate` 返回 `None` 且没有临时文件，才是第一次收口为假，才跑那一次全量。全量 `generate` 的异常在这里收成 `None`，调用方记停滞，不得再启动一次全量。

`_regen_baseline_with_archive` 不再被 `ensure_baselines` 调用。若还留着给命令行以外的旧入口，它只调用 `generate(..., finalize=False)`，不归档，不 `copy2`，不返回未收口的 cutoff。命令行直接跑全量时仍走脚本自己的 `finalize=True`。

成功收口之后返回的是活文件最后一笔 cutoff。文件已经通过序列相等，这一笔就是网格末笔。不要把临时文件或未通过文件的最后一笔交给 `_remember_stall`。`_remember_stall` 仍只接收 `_latest_data_dt`。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_ensure_baselines_postcondition.py tests/test_baseline_reanchor.py tests/test_baseline_archival.py tests/test_baseline_regen_loop.py tests/test_ensure_baselines_fingerprint.py tests/test_accept_baseline_file.py -v`

Expected: PASS。确认 `rg` 不到 `_guard_confirm_from_ts_after_regen`。不要跑全量 pytest，不要启动监督进程。

- [ ] **Step 5: Commit**

```bash
git add scripts/sup_evidence.py scripts/praxist_supervisor.py tests/test_baseline_reanchor.py tests/test_baseline_archival.py tests/test_baseline_regen_loop.py tests/test_ensure_baselines_fingerprint.py tests/test_ensure_baselines_postcondition.py
git commit -m "accept or keep the live baseline with one post-condition"
```

到这里是 PR2。不要重启监督进程，不要生成活基线。

---

### Task 11: 一条不加载模型的回归，加一页运维说明

**Files:**
- Create: `tests/test_baseline_jd_sr_postcondition.py`
- Create: `docs/superpowers/reports/2026-11-03-jd-baseline-operator-note.md`

**Interfaces:**
- Consumes: `finalize_baseline_write`；`baseline_eval_cutoffs` 的 monkeypatch；`_prereg_confirm_from_ts`
- Produces: 一份说明。不产生新的生产函数。

- [ ] **Step 1: Write the failing test**

```python
import json
import os
from datetime import datetime, timedelta

import scripts.sup_evidence as sup_evidence


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as handle:
        for cutoff in cutoffs:
            handle.write(json.dumps({
                "cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                "delta_real": 1.0, "protocol_fingerprint": fp,
            }) + "\n")


def _write_prereg(root, rows):
    config_dir = os.path.join(root, "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "preregistry.jsonl"), "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_jd_and_sr_share_one_postcondition(tmp_path, monkeypatch):
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    grid = [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(8)]
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    _write_prereg(str(tmp_path), [
        {"prereg_id": "jd1", "symbol": "jd", "confirm_from_ts": "2026-10-03 00:00:00",
         "n_confirm_required": 1199},
        {"prereg_id": "sr1", "symbol": "sr", "confirm_from_ts": "2026-10-03 00:00:00",
         "n_confirm_required": 986},
    ])
    scar = ["2026-10-21 10:00:00", "2026-10-21 12:00:00", "2026-10-21 15:00:00"]
    for symbol in ("jd", "sr"):
        pts = tmp_path / f"baseline_points_{symbol}_nocov.jsonl"
        _write_points(pts, grid)
        before = pts.read_bytes()
        archive = tmp_path / f"baseline_points_{symbol}_nocov.archive_scar.jsonl"
        _write_points(archive, scar)
        tmp = tmp_path / f".baseline_points_{symbol}_nocov.jsonl.tmp"
        _write_points(tmp, scar)
        assert sup_evidence.finalize_baseline_write(symbol, str(pts), str(tmp_path), str(archive)) is False
        assert pts.read_bytes() == before
        assert not tmp.exists()
    source = open("scripts/sup_evidence.py", encoding="utf-8").read()
    accept = open("cascade/eval_grid.py", encoding="utf-8").read()
    finalize_src = source.split("def finalize_baseline_write", 1)[1].split("\ndef ", 1)[0]
    assert "jd" not in finalize_src
    assert "sr" not in finalize_src
    assert "jd" not in accept
    assert "sr" not in accept
```

断言的意图是：`cascade/eval_grid.py` 的源码不含品种名 `jd` 或 `sr`；`finalize_baseline_write` 不对 `jd` 写分支。写断言时用读文件后的判断，不要为了让测试变绿而把品种名塞进日志格式以外的条件。若 `sup_evidence.py` 的日志用 `{sym_lower}` 而不是字面量 `"jd"`，源码里可以没有 `"jd"` 这个字面量；有的话，它不能出现在 `if` 条件里。

这条测试在 Task 7 的收口落地后、本任务把文件加进来之前，还没有这个测试文件，所以「失败」指的是测试文件还不在树上。先把测试文件写上并跑通；它保护的是已经落地的行为不被以后的修改拆成两套。若当前收口仍会把 3 行疤痕拷回，这一步必须先看到 FAIL，再回到 Task 7 的实现修，而不是放宽断言。

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_baseline_jd_sr_postcondition.py -v`

Expected: 收口正确时这条会 PASS。若 FAIL 且活文件字节变成了 3 行疤痕，那是实现回归，先修 `finalize_baseline_write`，不要改断言去接受拷回。

- [ ] **Step 3: Write the operator note**

写 `docs/superpowers/reports/2026-11-03-jd-baseline-operator-note.md`。正文用中文，按规格 Rollout Plan 的五步写全，不要缩成口号。必须包含这些事实：

1. 先合并第二截。在此之前不要手删 `task_FM/config/baseline_points_jd_nocov.jsonl`。现行守卫会把疤痕拷回去。
2. 磁盘上没有一份已经等于今天网格的 `jd` 文件。`archive_20260929T1500.jsonl` 是 588 行，窗口是 `2025-10-16` 至 `2026-09-29`，不要把它拷到活文件上。1 行和 3 行归档都不是恢复目标。
3. 代码到位之后，由运维选择时机让监督进程跑启动前检查。会加载模型的是 `jd` 这一趟，属于运维，不是本计划的命令，也不是为了修正 `dir_ok`。这一步原样写入：`incremental_generate` 返回后：已有可发布临时文件就调用 `finalize_baseline_write`。第一次收口为真就换名、返回网格末笔、不再运行 `generate`。没有可发布临时文件（包括任一评估点带 `error`，或换名前失败），或临时文件未通过，这是第一次接受失败，不是提前结束；没有临时文件且活文件尚未通过时，把第一次收口当成假。只有第一次收口为假，才恰好运行一次 `generate(..., finalize=False)` 并第二次调用 `finalize_baseline_write`。只有第二次收口为假才 `_remember_stall`。第一次为真不记停滞。读网格或写入抛出的异常不是这个 `None`：留在品种循环的 `except` 里记日志；读网格失败不记停滞、不启动全量；写入中途抛出则记停滞，并且不再启动另一次全量。3 行文件只在第二次收口仍为假时留在原地。不要把一份少于网格的文件当成这次运维的成功。不要运行 `scripts/restart_three_loop_clean.sh` 作为合并动作。
4. 成功判据：活文件的 cutoff 序列等于 `baseline_eval_cutoffs("jd")`，指纹仍是现行 v4，且没有「已从归档恢复旧档」把行数打回 3。不要求与九月归档的 cutoff 集合相同。
5. `sr` 不必手改，也不要为它新增预注册或移动 `confirm_from_ts`。今天的 637 行是两次恢复之后又拼上 49 个更早 cutoff 的文件，不是未动过的网格。下一次按新后条件落盘会丢掉那 49 行。网格上的 588 行若指纹仍是现行 v4 且字段齐全，增量可以复用，不必为了这 49 行加载模型。

说明里不要出现「重跑 21 个品种」或「为了修正 dir_ok 而重生模型」。不要在这一步执行说明里的任何运维动作。

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/abug/timesfm/.venv/bin/python -m pytest tests/test_baseline_jd_sr_postcondition.py tests/test_accept_baseline_file.py tests/test_baseline_reanchor.py::test_prereg_and_no_prereg_keep_the_same_grid_file tests/test_dir_ok_owners.py tests/test_baseline_record_and_resume.py -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/test_baseline_jd_sr_postcondition.py docs/superpowers/reports/2026-11-03-jd-baseline-operator-note.md
git commit -m "lock jd and sr to one baseline post-condition and record the operator steps"
```

---

## 规格覆盖

| 规格要求 | 任务 |
|----------|------|
| `endpoint_dir_ok` 搬家并再导出 | Task 1 |
| `assemble_direction` 与测试 (a) | Task 2 |
| 诊断 `cutoff` 为完整收盘时间戳；检查点两键可选 | Task 2 |
| `tradable_sign` 与测试 (f) | Task 3 |
| `baseline_jsonl_record`、两处写入、测试 (e)、键集断言 | Task 4 |
| 续跑不要求 `completed`；不传 `eval_start_ts`；删除外部拼接 | Task 4 |
| 三个脚本的 `dir_ok`、测试 (g)、2026-09-14 勘误 | Task 5 |
| `eval_grid`、右边界测试、空网格抛错 | Task 6 |
| `accept_baseline_file`、`finalize_baseline_write`、测试 (b)(c)(d) | Task 7 |
| `finalize=False`、错误点不发布子集 | Task 8 |
| 增量按网格复用 | Task 9 |
| 启动只问一次后条件、断路器、删除旧守卫与再导出 | Task 10 |
| `jd` 与 `sr` 同一回归、五步运维说明 | Task 11 |
| 不改门槛、指纹、确认窗长度、`_valid_n_for_symbol`、活 JSONL | 全部任务都不做 |

## 自检

- 方案 A、钟点步长、`n < 100` 豁免、只为 `jd` 开特例、手删 3 行文件，都没有写成任务。
- `assemble_direction`、`baseline_jsonl_record`、`tradable_sign`、`baseline_eval_cutoffs`、`accept_baseline_file`、`finalize_baseline_write` 在各任务里的参数表一致。
- 失败路径那一句在 Global Constraints、Task 10 的实现和 Task 11 的运维说明里是同一句。
- 没有把「重跑 21 个品种」或 `scripts/restart_three_loop_clean.sh` 写成合并命令。
