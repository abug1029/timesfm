# Task 4 Changelog: 复权策略显式化 + 死表死配置 (D1/D3/C7)

**Commit:** 36893e7
**Date:** 2026-09-27
**Status:** 完成

## 实施内容

### 新增
- `tests/test_backward_adjustment_reachable.py`: 8 个测试
  - `TestAdjustmentPolicyVisible`: 3 条（raw_close 列优先于 empty、无 raw_close 时 eligible、None 为 empty）
  - `TestAttrsPropagation`: 1 条（策略经一次 copy 存活）
  - `TestDeadTableMarked`: 3 条（三个 XReg 方法 docstring 标注）
  - `TestDeadConfigRemoved`: 1 条（xreg_covariates 已删、活字段保留）

### 修改
- **data/data_store.py**:
  - 新增 `resolve_adjustment_policy(df) -> str` — 返回 `"empty"` / `"skipped_raw_close_column_present"` / `"eligible"`
  - `get_main_continuous` 中显式记录 `df.attrs["adjustment_policy"]`
  - `store_xreg_factor` / `get_xreg_factors` / `get_xreg_matrix` 三个 docstring 首行加 `[DEAD TABLE - 预测路径不读取]`

- **config/prediction_scheme.py**: 删除 `xreg_covariates` 字段（仅该字段；`covariate_type` 与 `covariate_types` 保留）

## 关键设计
- 列存在性判断**先于** empty 判断且不特判行数（0 行无 raw_close 的 df 判 "eligible" 而非 "empty"）
- `raw_close` 恒在 `MAIN_COLUMNS` → 生产 SELECT * 必带该列 → `apply_backward_adjustment_robust` 从不执行 —— 这是静默失效，本任务把它变成可见返回值
- 不擅自"修好"复权（那会改变全部历史数值）

## 测试结果
- `test_backward_adjustment_reachable.py`: 8/8 PASS
- 波及面: `test_system_hardening.py` / `test_kb_schemes_consistency.py` / `test_regime_routing.py` 172/172 PASS
