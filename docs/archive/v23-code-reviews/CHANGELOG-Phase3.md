# Phase 3 Changelog - 数据管道层 (Task 7-8)

**日期**: 2026-09-15  
**分支**: `feat/prediction-quality-redesign-v23`  
**状态**: ✅ 完成，代码审核通过

---

## 变更摘要

Phase 3 实现了预测质量评估的数据管道层，包括 Registry 原子写、v2 字段定义、墓碑机制、monthly_backtest 质量口径重构。

---

## Task 7: Registry 原子写 + v2 字段 + 墓碑

### 文件变更
- **修改** `scripts/registry_lib.py` (+241 行)
- **修改** `tests/test_verdict_registry.py` (+96 行)

### 功能实现

#### 1. 路径版 `append_verdict`
- **双态入参**: `str | Path`（路径版）和句柄（保持现有行为）
- **排他锁**: `.lock` 文件 + `fcntl.flock`
- **防重**: 同 `batch_id+variant_id` 拒绝重复写入
- **原子写入**: `.tmp` → `fsync` → `os.replace`
- **临时名**: `f"{path}.{pid}.{time_ns()}.tmp"`

#### 2. `read_verdicts(path) -> list[dict]`
- 共享锁 + 坏行跳过（通过 `_iter_jsonl`）

#### 3. `update_batch_verdicts(path, batch_id, updates) -> None`
- 持锁期间直接调用 `_iter_jsonl`（无锁读取）
- 仅当 `metrics in v and isinstance(dict)` 时同步 metrics 子字典
- 临时文件原子替换

#### 4. 墓碑工厂
- **`make_error_tombstone(symbol, variant_id, batch_id, exception)`**
- **`make_timeout_tombstone(symbol, variant_id, batch_id)`**
- v2 schema，含 `metrics` 子字典
- `gate_pass=False`, `p_value=1.0`

#### 5. `pass_variants` v2-aware
- **v2**: `gate_pass and (fdr_pass or migrated_pass)`
- **v1**: `gate_pass and ev>0`
- tombstone 通过 `status != "ok"` 正确过滤

#### 6. v2 字段定义
- `VERDICT_FIELDS_V2` + `VERDICT_FIELDS_V2_NULLABLE`
- `validate_verdict` 按 schema 分派 v1/v2
- 可空字段：`path_corr, mae, mape, decay, p_value, fdr_pass, migrated_pass, endpoint_mape, endpoint_bias_pct`

### 代码审核结果
- ✅ APPROVE
- 12/12 测试通过（6 新 + 6 旧）
- 原子写入、锁机制、v2 schema 设计正确
- 向后兼容性保持良好
- 🟡 MEDIUM: `append_verdict_path` 建议添加验证（可选改进）
- 🟢 LOW: 临时文件清理（可选改进）

### 测试结果
- 6 个原有测试全部通过（queue_*, snapshot, validate, partial line 等行为零改动）
- 6 个新增 v2 测试全部通过：
  - `test_read_verdicts_skips_bad_line`
  - `test_append_verdict_path_dedup`
  - `test_update_batch_verdicts_metrics_sync`
  - `test_update_batch_no_metrics_key_does_not_invent`
  - `test_pass_variants_v2_needs_fdr`
  - `test_error_tombstone_has_metrics`

### Commits
- `5c81b23` - feat(registry): path-based verdict IO, FDR update, v2 tombstones

---

## Task 8: monthly_backtest 质量口径

### 文件变更
- **修改** `scripts/monthly_backtest.py` (+221 行)
- **新增** `tests/test_monthly_backtest_quality.py` (8 个测试)
- **修改** `tests/test_monthly_resume.py` (`_make_point` 补 3 个新 key)

### 功能实现

#### 1. 逐点 `dir_ok` 保守判定
- `|delta_real_raw| < 1e-8` → False（零变动不算正确）
- 否则 `sign(delta_pred) == sign(delta_real_raw)`
- 与 `calc_prediction_quality` 内部逻辑一致

#### 2. 逐点写入完整 `cutoff`
- 格式：`%Y-%m-%d %H:%M:%S`（不是只有日期）
- 另留 `cutoff_date=dt` 给报告

#### 3. 逐点新增指标
- `endpoint_mape = abs(pred[-1]-real[-1])/max(base,1.0)*100`
- `endpoint_bias_pct = (delta_pred-delta_real)/max(base,1.0)*100`
- `path_corr = safe_path_corr(pred, real)`（有路径时）

#### 4. `summarize` 新输出
- **`dir_acc`**: 来自 `calc_prediction_quality`（非 `net["DirAcc"]`）
- **`point_dir_ok_list`**: `list[tuple[str, bool]]`（cutoff, dir_ok）
- **`n_eff`**: `fallback_n_eff(n, HORIZON, STEP)`（从 config 读默认值）
- **`endpoint_mape`**: 端点 MAPE
- **`endpoint_bias_pct`**: 端点偏差百分比
- **`path_corr`**: 路径相关性均值
- **`weighted_dir_acc`**: 加权方向准确率

#### 5. 月报保留
- `profit_factor`/`ev`/`max_dd` 仍从 `metrics_from_backtest_points` 取
- 经济秤（PF/EV/MaxDD）与预测质量秤（DirAcc/MAPE）分离

#### 6. `_CHECKPOINT_POINT_KEYS` 扩展
- 新增 `endpoint_mape`、`endpoint_bias_pct`、`path_corr`

### 代码审核结果
- ✅ APPROVE
- 11/11 测试通过（8 新 + 3 旧无回归）
- 6/6 审核点全部通过
- `dir_ok` 保守口径与 `calc_prediction_quality` 一致
- `summarize` 双秤分离清晰
- 3 个非阻塞观察项（一致性）可后续迭代

### 测试结果
- `test_monthly_backtest_quality.py`: 8/8 PASSED
  - `test_summarize_dir_ok_zero_move_is_miss`
  - `test_summarize_none_when_all_errors`
  - `test_checkpoint_keys_include_new_metrics`
  - `test_dir_acc_from_calc_prediction_quality_not_net`
  - `test_path_corr_aggregated_when_present`
  - `test_path_corr_none_when_absent`
  - `test_n_eff_computed`
  - `test_economic_metrics_still_present`
- `test_monthly_resume.py`: 3/3 PASSED（无回归）

### Commits
- `f54145a` - feat(backtest): prediction-quality summarize and conservative dir_ok

---

## 技术亮点

1. **原子写入**: `.tmp → fsync → os.replace` 确保数据持久性
2. **锁机制设计**: 共享锁读、排他锁写，避免重入锁问题
3. **双态接口**: `append_verdict` 支持路径和句柄两种入参
4. **双秤分离**: 预测质量秤（DirAcc/MAPE）与经济秤（PF/EV/MaxDD）独立
5. **保守 `dir_ok`**: 零变动不算正确，与规格一致
6. **完整时间戳**: `cutoff` 用 `%Y-%m-%d %H:%M:%S`，避免同日多根 1H 撞车

---

## 测试汇总

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| `test_verdict_registry.py` | 12 | ✅ 全部通过 |
| `test_monthly_backtest_quality.py` | 8 | ✅ 全部通过 |
| `test_monthly_resume.py` | 3 | ✅ 无回归 |
| **Phase 3 总计** | **23** | ✅ |

---

## 待审核项

- [x] Phase 3 代码实现
- [x] 代码审核（Task 7: APPROVE, Task 8: APPROVE）
- [x] 测试覆盖率（23 tests）
- [x] 向后兼容性（现有测试无回归）

---

## 下一步

继续执行 **Phase 4: 评估与调度层** (Task 9-12):
- Task 9: Evaluator 硬门 + DM 配对
- Task 10: 慢环 tombstone + v2 写入
- Task 11: 基线逐点生成脚本
- Task 12: Supervisor 基线预检 + 批次 FDR

---

# 独立代码审核修复 (2026-09-15)

根据 `2026-09-15-phase3-code-review.md` 独立审核报告，发现并修复了以下问题：

## Critical 修复

### 统一 dir_ok / dir_acc / point_dir_ok_list
- **问题**: 逐点 `dir_ok` 用加权 delta，硬门 `dir_acc` 用终点价差，两套不一致
- **修复**: 逐点 `dir_ok` 改为用终点价差 `pred[-1]-base` vs `real[-1]-base`
- **加权 delta_pred**: 仍保留给 `pnl` / 经济秤
- **Commit**: `6507cee`
- **新增测试**: `test_dir_ok_uses_endpoint_not_weighted`

## Important 修复

### 逐点 endpoint_mape / endpoint_bias_pct 分母地板
- **问题**: 分母用 `base`，极小值会除零
- **修复**: 分母改为 `max(base, 1.0)`
- **Commit**: `6507cee`
- **新增测试**: `test_endpoint_mape_uses_base_floor`

### 墓碑和 VERDICT_FIELDS_V2 对齐规格
- **问题**: 缺 `cov_family`、`weighted_dir_acc`；`metrics` 字段不全
- **修复**:
  - `VERDICT_FIELDS_V2` 新增 `cov_family`、`weighted_dir_acc`
  - 墓碑填满根字段和 `metrics`（n, n_eff, dir_acc, endpoint_mape 等）
  - 错误字段名 `error` → `error_message`
- **Commit**: `6507cee`

### 路径版 append_verdict 改为真正 append
- **问题**: 整文件重写（读出来写 tmp 再 replace），应该用 append+fsync
- **修复**:
  - 用 `open(p, "a")` + `fsync`
  - 写入前做 `validate_verdict` schema 校验
  - 去重在锁内完成
- **Commit**: `6507cee`

## 修复后测试结果

```
25 passed in 11.90s
```

---

# 复审修复 (2026-09-15 第二轮)

根据 `2026-09-15-phase3-rereview.md` 复审报告，修复剩余问题：

## Important 修复

### 错误点 cutoff 时间戳
- **问题**: 异常点仍写 `"cutoff": dt`（只有日期）
- **修复**: 改为 `"cutoff": cutoff`（完整时间戳）
- **Commit**: `1f864fb`

### dir_ok 公式测试
- **问题**: 测试只验证 summarize，打不到逐点公式
- **修复**: 新增 `test_dir_ok_formula_endpoint_not_weighted`，直接验证逐点 dir_ok 用终点价差
- **Commit**: `1f864fb`

## Minor 修复

### n_eff 测试收紧
- **问题**: 只断言 `1 <= n_eff <= n`，锁不住 STEP=2
- **修复**: 断言改为 `n_eff <= n // 2`
- **Commit**: `1f864fb`

## 第二轮修复后测试结果

```
34 passed, 1 deselected
```

---

# 最终状态

**审核结论**: ✅ APPROVE（独立代码审核 + 复审均通过）  
**测试覆盖**: 34 tests  
**Commits**: 4 个（2 个初始实现 + 1 个第一轮修复 + 1 个第二轮修复）

**待审核项**:
- [x] Phase 3 代码实现
- [x] 代码审核（Task 7: APPROVE, Task 8: APPROVE）
- [x] 独立审核修复（Critical + Important）
- [x] 测试覆盖率（25 tests）
- [x] 向后兼容性

---

## 下一步

继续执行 **Phase 4: 评估与调度层** (Task 9-12):
- Task 9: Evaluator 硬门 + DM 配对
- Task 10: 慢环 tombstone + v2 写入
- Task 11: 基线逐点生成脚本
- Task 12: Supervisor 基线预检 + 批次 FDR

---

**审核人**: 独立代码审核  
**审核日期**: 2026-09-15
