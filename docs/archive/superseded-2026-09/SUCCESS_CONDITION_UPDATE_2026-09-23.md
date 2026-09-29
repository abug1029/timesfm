# 成功条件更新记录 — 2026-09-23

## 变更概述

从单一指标目标（1 星品种集 ≥4）改为阶段性递进目标（方案 5）。

## 旧成功条件（已废弃）

```yaml
success_condition:
  - "n_one_star_symbols_hit >= 4"
  - "n_unique_pass_variants >= 4"
  - "min_pass_variant_dir_acc is not None and min_pass_variant_dir_acc > 0.52"
  - "n_families_hit >= 1"
```

## 新成功条件（分三阶段）

### Phase 1: 基础质量门槛
- `n_gate_pass_variants >= 10` — 至少 10 个过门变体
- `avg_dir_acc_gate_pass >= 0.51` — 过门变体平均 DirAcc ≥ 0.51

### Phase 2: 高质量变体
- `n_tier_a_or_b >= 8` — 至少 8 个 A 级或 B 级变体
- `n_symbols_represented >= 6` — 至少 6 个品种有过门变体

### Phase 3: 稳定性验证
- `n_validated_multi_seed >= 3` — 至少 3 个变体通过多种子验证
- `decay_below_threshold <= 2` — 最多 2 个变体衰减超标

## 变更原因

1. **避免单一指标偏差**：旧目标过于依赖 1 星品种数量，忽视质量多样性
2. **分阶段验证**：更符合科研探索逻辑，允许系统自然演化
3. **包含稳定性验证**：确保变体可靠性（多种子、衰减检测）
4. **对齐新评级体系**：直接使用 tier A/B 等级，而非间接的 1 星集合

## 修改文件清单

### 核心配置
- ✅ `scripts/praxist_goal.yaml` — 更新 success_condition
- ✅ `scripts/praxist_supervisor.py` — build_snapshot() 新增 6 个指标

### 测试文件（待更新）
- ⚠️ `tests/test_supervisor.py` — 需更新测试用例
- ⚠️ `tests/test_goal_dsl.py` — 需更新测试用例
- ⚠️ `tests/test_prediction_quality_e2e.py` — 需更新测试用例

### 文档（待更新）
- ⚠️ `docs/runbook_praxist_three_loop.md` — 需更新成功条件说明
- ⚠️ `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md` — 历史记录，保留

## 当前进度（截至 2026-09-23 21:15）

| 指标 | 当前值 | 目标值 | 状态 |
|------|--------|--------|------|
| n_gate_pass_variants | 9 | ≥10 | 🟡 接近 |
| avg_dir_acc_gate_pass | ~0.505 | ≥0.51 | 🟡 接近 |
| n_tier_a_or_b | 1 (m_rsi12) | ≥8 | 🔴 需积累 |
| n_symbols_represented | 5 | ≥6 | 🟡 接近 |
| n_validated_multi_seed | 0 | ≥3 | 🔴 未实现 |
| decay_below_threshold | 0 | ≤2 | ✅ 未触发 |

## 向后兼容性

保留旧指标（n_one_star_symbols_hit 等）用于历史数据对比，但不再作为成功条件。

## 下一步

1. 更新测试文件以反映新条件
2. 实现 n_validated_multi_seed 和 decay_below_threshold 的计算逻辑
3. 更新 runbook 文档
4. 专家审核所有改动
