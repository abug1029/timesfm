# Task 2 Changelog: bfill 因果化 + cov_fill_version bump 声明 (D4)

**Commit:** 991ff4b
**Date:** 2026-09-27
**Status:** 完成，待补证据

## 实施内容

### 新增
- `tests/test_bfill_causal.py`: 6 个测试
  - `TestCausalFfill`: 3 条行为测试（前导 NaN 用冷启动、内部 NaN 前向填充、全 NaN 回落冷启动）
  - `TestCclPctCausality.test_ccl_pct_leading_segment_is_causal`: 截断不变性测试（真泄漏捕获）
  - `TestAoAccelBfillRemoved`: 2 条源码断言（`calc_ao_acceleration` 和 `calc_ccl_pct` 不再包含 `.bfill()`）

### 修改
- **cascade/features.py**:
  - 新增 `causal_ffill(series: pd.Series, cold_start_fill: float) -> pd.Series`
    - 实现: `series.ffill().fillna(cold_start_fill)`
  - `calc_ccl_pct` (约 line 653): `oi_smooth = oi_smooth.bfill().fillna(1)` 改为 `oi_smooth = causal_ffill(oi_smooth, cold_start_fill=1.0)`
  - `calc_ao_acceleration` (约 line 1984): `scale = mad.bfill()` 改为 `scale = causal_ffill(mad, cold_start_fill=EPSILON)`

## 泄漏分析

| 泄漏点 | 性质 | 是否可观测 | 修复 |
|--------|------|------------|------|
| `calc_ccl_pct` bfill | 真泄漏：oi 前导 0 导致 rolling 产出 NaN，bfill 搬未来值当分母 | 可观测（截断不变性测试） | `causal_ffill(oi_smooth, cold_start_fill=1.0)` |
| `calc_ao_acceleration` bfill | 结构性前视：scale[2..3] = mad[4]，但被 tanh 饱和与近零分子掩盖 | 不可观测（输出级） | `causal_ffill(mad, cold_start_fill=EPSILON)` |

## 测试结果
- `test_bfill_causal.py`: 6/6 PASS
- `test_system_hardening.py`: 47/47 PASS（相关测试）
- 回归: 1139 PASS, 6 失败（`test_timesfm_model_path.py`）, 4 skipped, 3 deselected, 1 xfailed
  - 6 失败确认为既有问题：Task 1 commit `e616ade` 上 `python -m pytest tests/test_timesfm_model_path.py` 同样 6 failed
  - 失败原因：测试期望 `google/timesfm-2.5-200m-pytorch`，实际返回 `google/timesfm-3.0-pytorch`（TimesFM 升级后的模型路径变更）

## cov_fill_version 声明
- `ccl_pct` 语义变更导致协变量矩阵改变，与 `cov_fill_version="v1"` 的旧 verdict/基线不可比
- `COV_FILL_VERSION="v2"` 常量由 Task 6 定义（与 `compute_protocol_fingerprint` 同处，单一来源）
- 旧 `ccl` 基线在 Task 5 须重新生成

## Commit Message 全文

```
fix(features): ccl_pct bfill 因果化 (D4)

calc_ccl_pct 的 bfill 是真泄漏（oi 前导 0 → rolling NaN → 搬未来值当分母），
改用 causal_ffill + 常数冷启动。
calc_ao_acceleration 的 bfill 经实测为结构性前视（scale[2..3]=mad[4]），
但通常被 tanh 饱和与近零分子掩盖而输出级不可观测——仍须修复，检测用源码断言。
cov_fill_version 的 bump 随 Task 6 的 compute_protocol_fingerprint 生效
（ccl_pct 语义变更将使旧 verdict/基线不可比）。

Co-Authored-By: Claude Code <noreply@anthropic.com>
```

## 待补证据
- [x] 12 条 `test_timesfm_model_path.py` 失败的基线对照（在 Task 1 commit `e616ade` 上重跑验证为既有问题）
  - 基线 `e616ade`: 6 failed, 7 passed
  - 当前 `991ff4b`: 6 failed, 7 passed
  - 失败内容相同：模型路径期望 `google/timesfm-2.5-200m-pytorch`，实际 `google/timesfm-3.0-pytorch`
  - 结论：确为 TimesFM 3.0 升级后的既有问题，与本次 bfill 改动无关

## 审核结论
- **Task 2 审核通过**。语义正确、证据链完整、波及面已验证、测试覆盖充分。
- 按既定顺序进入 **Task 3（换月量化与守卫 + 完整传输链 D1/D2）**。
