# Phase 1 Changelog - 核心指标层 (Task 1-2)

**日期**: 2026-09-15  
**分支**: `feat/prediction-quality-redesign-v23`  
**状态**: ✅ 完成，代码审核通过

---

## 变更摘要

Phase 1 实现了预测质量评估的核心指标层，包括路径相关性计算、预测质量综合指标、有效样本量估计。

---

## Task 1: safe_path_corr

### 文件变更
- **修改** `cascade/evaluation_metrics.py` (+18 行，追加函数)
- **新增** `tests/test_evaluation_metrics.py` (5 个测试)

### 功能实现
**`safe_path_corr(pred_path, real_path, eps=1e-8)`**: 带防护的 Pearson 相关系数

**7 层防护**:
1. None 检查 → None
2. `np.asarray(..., dtype=float)` 类型转换
3. `.ravel()` 展平 2D 数组
4. 长度检查（<2 或不匹配 → None）
5. NaN/inf 检查 → 0.0
6. 零方差检查（std < eps → 0.0）
7. `corrcoef` 结果 isfinite 检查 → 0.0

### 代码审核修复
executor 发现并修复了测试断言 bug：
- **问题**: `assert 0.99 < result < 1.0` 要求严格小于 1.0
- **修复**: 改为 `assert 0.99 < result <= 1.0`（完全线性相关应返回 1.0）

### 代码审核结果
- ✅ APPROVE
- 防御性编程优秀
- 数值安全处理完善

### 测试结果
- 5/5 测试通过
- 11/11 旧测试无回归

### Commits
- `bdc98fb` - feat(eval): add safe_path_corr with zero-variance protection

---

## Task 2: calc_prediction_quality + fallback_n_eff

### 文件变更
- **修改** `cascade/evaluation_metrics.py` (+85 行，追加 2 个函数)
- **修改** `tests/test_evaluation_metrics.py` (+8 个测试)

### 功能实现

#### 1. `fallback_n_eff(n, horizon=24, step=24)`
**Bartlett 有效样本量估计**

公式:
```
h = max(1, horizon // step)
factor = 1.0 + 2.0 * sum((1.0 - j/h)^2 for j in range(1, h))
n_eff = max(1, int(n / factor))
```

**关键行为**:
- step=24, horizon=24 → h=1, factor=1.0, n_eff=n（非重叠窗口）
- step=2, horizon=24 → h=12, factor≈8.03, n_eff≈n/8（重叠抽样）

#### 2. `calc_prediction_quality(pred_endpoints, real_endpoints, base_prices, pred_paths=None, real_paths=None)`
**预测质量综合指标**

**返回 dict** (9 个键):
```python
{
    "dir_acc": float,           # 方向准确率
    "endpoint_mape": float,     # 端点 MAPE（分母 max(base, 1.0)）
    "endpoint_bias_pct": float, # 端点偏差百分比
    "path_corr": float|None,    # 路径相关性（有路径时）
    "weighted_dir_acc": float,  # 加权方向准确率
    "mae": float|None,          # 路径 MAE
    "mape": float|None,         # 路径 MAPE
    "decay": float|None,        # 衰减率 mae_h2/mae_h1
    "n": int                    # 样本数
}
```

**关键实现**:
1. **dir_ok 判定**: 
   - `|delta_real| < eps` → False（零变动不算正确）
   - 否则 `sign(delta_pred) == sign(delta_real)`

2. **delta 计算**: 
   - `delta_pred = pred_end - base_raw`（用未截断的 base_raw）
   - `endpoint_mape` 分母用 `max(base_raw, 1.0)`

3. **weighted_dir_acc**: 
   - 分母 `sum(|delta_real|)`，全平时返回 0.5

4. **path_corr**: 
   - 调用 `safe_path_corr` 逐样本计算后取均值

5. **decay**: 
   - `mae_h2 / max(mae_h1, 1e-6)`

### 代码审核结果
- ✅ APPROVE
- 所有 9 项规格要求验证通过
- 数值安全处理完善

### 测试结果
- 13/13 测试通过（5 来自 Task 1 + 8 新测试）
- 11/11 旧测试无回归

### Commits
- `f4d7f9c` - feat(eval): add calc_prediction_quality and Bartlett n_eff

---

## 技术亮点

1. **防御性编程**: safe_path_corr 7 层防护，层层递进
2. **数值安全**: 所有除法都有分母保护（`max(..., 1e-6)` 或 `max(..., 1.0)`）
3. **零变动处理**: `|delta_real| < eps` → False，符合规格 §3.5
4. **Bartlett 因子**: 正确处理非重叠（step=24）和重叠（step=2）抽样
5. **测试覆盖**: 13 个测试覆盖核心逻辑和边界情况

---

## 关键设计决策

### 1. safe_path_corr 返回值语义
- **None**: 输入无效（None、过短、长度不匹配）
- **0.0**: 数据退化（NaN/inf、零方差）
- **float**: 有效相关系数 [-1, 1]

**审核建议**（可选改进）:
- 可考虑补充 docstring 说明返回值语义
- 下游聚合时需区分"无法计算"和"无相关"

### 2. dir_ok 零变动判定
- **规格要求**: `|delta_real| < 1e-8` → False
- **原因**: 价格无变动时，预测方向无意义，不应计入正确率

### 3. delta 计算用 base_raw
- **delta_pred/delta_real**: 用未截断的 `base_raw`（价格增量）
- **endpoint_mape**: 分母用 `max(base_raw, 1.0)`（避免除以接近 0 的数）
- **原因**: 保持经济含义（价格增量），同时保证数值安全

---

## 待审核项

- [ ] Phase 1 代码实现
- [ ] 代码审核修复
- [ ] 测试覆盖率
- [ ] 文档完整性

---

## 下一步

继续执行 **Phase 2: 统计检验层** (Task 3-6)

---

**审核人**: 待指定  
**审核日期**: 待指定
