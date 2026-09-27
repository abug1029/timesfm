# Task 3 Changelog: 换月量化与守卫 + 完整传输链 (D1/D2)

**Commit:** 3b02e25
**Date:** 2026-09-27
**Status:** 完成

## 实施内容

### 新增
- `tests/test_roll_guard.py`: 8 个测试
  - `TestRollInHorizon`: 4 条（单合约不算换月、合约切换检出、空序列、第二位切换）
  - `TestDenominatorReporting`: 3 条（计数与比例、full 保留全部点、roll_flags=None 保持旧行为）
  - `TestTransmissionChain.test_field_reaches_verdict`: 端到端传输链验证

### 修改
- **scripts/monthly_backtest.py**:
  - 新增 `roll_in_horizon(contract_codes) -> bool` — 首个元素为基准，任一后续元素不同即为换月
  - `_CHECKPOINT_POINT_KEYS` 增 `"roll_in_horizon"`
  - 逐点构造处新增 `_cc = all_1h["contract_code"].iloc[idx+1:idx+1+HORIZON].tolist()` 与 `_roll = roll_in_horizon(_cc)`
  - point dict 增 `"roll_in_horizon": _roll`
  - `summarize()` 收集 `_roll_flags` 并传给 `calc_prediction_quality(..., roll_flags=...)`
  - `summarize()` 返回 dict 增 4 键

- **cascade/evaluation_metrics.py**:
  - `calc_prediction_quality` 签名增 `roll_flags=None` 关键字参数（前三个位置参数不变）
  - 新增分母口径逻辑：`dir_acc_full`（不剔除）、`dir_acc_ex_roll`（剔除跨换月点）、`n_roll_excluded`、`n_roll_ratio`
  - 返回 dict 增 4 键

- **task_FM/evaluations/fm_eval/evaluator.py**:
  - `map_summary` 返回 dict 增 4 键（含 fallback 到 `dir_acc`）
  - `build_summary` 的 `out` dict 与 `metrics` 子 dict 各增 4 键

- **scripts/registry_lib.py**: `VERDICT_FIELDS_V2` 与 `VERDICT_FIELDS_V2_NULLABLE` 各增 4 键

## 传输链（三段齐备）
```
all_1h["contract_code"][idx+1:idx+HORIZON]
  -> roll_in_horizon(...)
  -> point["roll_in_horizon"]
  -> summarize(): _roll_flags
  -> calc_prediction_quality(..., roll_flags=...)
  -> summarize() 返回 4 键
  -> map_summary(s) 映射 4 键
  -> build_summary() out + metrics 落 4 键
```

## 测试结果
- `test_roll_guard.py`: 8/8 PASS
- 波及面: `test_evaluation_metrics.py` / `test_evaluation_metrics_contract.py` / `test_monthly_backtest_quality.py` / `test_fm_evaluator_gated.py` 71/71 PASS
- `test_monthly_resume.py` 夹具补 `roll_in_horizon`（波及面）
