# Task 5 Changelog: 同 cutoff 无协变量基线 (E7)
> **代码基线**: `184d2a7`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

**Commit:** 7328124
**Date:** 2026-09-27
**Status:** 完成

## 实施内容

### 新增
- `cascade/baseline_paths.py`: 文件名约定唯一来源
  - `baseline_filename(symbol, cov=None) -> str`
  - `cov=None` 或 `"none"` -> `baseline_points_{sym}_nocov.jsonl`
  - 其余 -> `baseline_points_{sym}.jsonl`
- `tests/test_nocov_baseline.py`: 5 个测试
- `tests/test_a1_completeness.py`: 5 个测试（Task 7 交付的专项测试）

### 修改
- **scripts/generate_baseline_points.py**:
  - 导入 `baseline_filename`
  - `generate()` 内新增 `effective_cov = "none" if (cov is None or cov == "none") else cov`
  - `cov_override=cov` 改为 `cov_override=effective_cov`
  - 输出路径 `f"baseline_points_{sym_lower}.jsonl"` 改为 `baseline_filename(sym_lower, cov)`
  - 基线记录增 `"protocol_fingerprint": _proto`

- **task_FM/evaluations/fm_eval/evaluator.py**:
  - `load_baseline_points(symbol, root=None, cov=None)` — 增 `cov` 参数
  - 路径改用 `baseline_filename(symbol, cov)`
  - 错误消息使用 `_fname` 变量

- **scripts/aligned_slow_loop.py:153**、**task_FM/evaluations/fm_eval/run.py:109**: 调用点传 `cov=None`

## 关键设计
- **循环 import 规避**: `load_baseline_points` 从 `cascade/baseline_paths.py` 导入，**不从** `scripts.generate_baseline_points` 导入（后者已 import evaluator）
- **M3 修复**: `cov_override=None` 会被 `monthly_backtest` 回落到 scheme 默认（多数品种 "ccl"），使 `_nocov` 文件里装的仍是 ccl 数据 → 必须显式传 `"none"`
- **C1 修复**: 写路径硬编码会导致 `_nocov.jsonl` 永不生成 → 必须切到 `baseline_filename`

## 波及面（6 个既有测试）
| 测试 | 改动 |
|------|------|
| `test_fm_evaluator_gated.py` | monkeypatch lambda 增 `cov=None` 参数 |
| `test_praxist_fm_evaluator.py` | 夹具文件名改 `_nocov` |
| `test_prediction_quality_e2e.py` | `_write_baseline` 文件名改 `_nocov` |
| `test_fm_evaluator_error_paths.py` | 3 处文件名改 `_nocov` |
| `test_generate_baseline_points.py` | 字段集断言增 `protocol_fingerprint` |
| `test_monthly_resume.py` | `_make_point` 补 `roll_in_horizon`（Task 3 波及） |

## 测试结果
- `test_nocov_baseline.py`: 5/5 PASS
- `test_a1_completeness.py`: 5/5 PASS
- 全量回归: 1188 PASS, 12 FAILED（全部为既有问题，已在 `e616ade` 基线验证）

## 已知声明
- **baseline_metrics.json 键冲突**: ccl 与 nocov 基线经同一 `metrics[symbol]` 键互相覆盖，现阶段以 nocov 为准（Task 8 报告声明）
