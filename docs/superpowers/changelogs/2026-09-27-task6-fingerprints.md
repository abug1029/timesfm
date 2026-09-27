# Task 6 Changelog: 协议/样本/协变量矩阵指纹与接线 (E8/E9/C2)

**Commit:** a03f5a5
**Date:** 2026-09-27
**Status:** 完成

## 实施内容

### 新增
- `tests/test_protocol_fingerprint.py`: 8 个测试
- `tests/test_cov_fingerprint.py`: 6 个测试

### 修改
- **task_FM/evaluations/fm_eval/evaluator.py**:
  - 新增常量 `PROTOCOL_FINGERPRINT_VERSION = "protocol_v1"`、`COV_MATRIX_HASH_VERSION = "cov_matrix_hash_v1"`、`COV_FILL_VERSION = "v2"`
  - 新增 `compute_protocol_fingerprint(metric_version="v1", cov_fill_version=COV_FILL_VERSION, eval_window_bars=None, step=None, horizon=None) -> str`
  - 新增 `compute_sample_fingerprint(points) -> str`
  - 新增 `compute_cov_fingerprint(matrix, keys) -> dict`
  - `build_summary` 签名增 `points=None, cov_matrix=None, cov_keys=None`
  - `out` dict 增 3 指纹键

- **cascade/hourly_model.py**: 新增 `last_covariate_input: tuple = None` 字段；predict 内赋值 `(past_future_covariates, list(covariate_keys))`；回退分支置 `None`

- **scripts/registry_lib.py**: schema 增 3 键；新增 `comparable(a, b) -> bool`

## 关键设计
- **`COV_FILL_VERSION = "v2"` 唯一来源在此**（D4 语义变更），Task 2 只做 bfill 修复并声明随本函数生效
- **协议指纹只含不随数据增长改变的不变量**：样本量、cutoff 列表、数据截止时间**不**进入（属 sample_fingerprint）
- **协变量矩阵规范序列化**：键序保留（顺序即通道语义）、float32 小端、`-0.0` 归一、Inf fail-loud
- **comparable() 只由 protocol_fingerprint 决定**；sample_fingerprint 不同属正常（前向数据累积）

## 测试结果
- `test_protocol_fingerprint.py`: 8/8 PASS
- `test_cov_fingerprint.py`: 6/6 PASS
- 波及面: `test_fm_evaluator_gated.py` / `test_praxist_fm_evaluator.py` 68/68 PASS
