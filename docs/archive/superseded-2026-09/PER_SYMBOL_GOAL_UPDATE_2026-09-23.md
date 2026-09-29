# 全品种阶段性目标更新 — 2026-09-23

## 变更概述

从全局聚合指标改为**每个品种都必须达到 Phase 1-3 标准**，确保全面质量覆盖。

## 目标定义

### Phase 1: 基础质量门槛（每品种）
- `n_gate_pass_variants >= 10` — 至少 10 个过门变体
- `avg_dir_acc_gate_pass >= 0.51` — 平均 DirAcc ≥ 0.51

### Phase 2: 高质量变体（每品种）
- `n_tier_a_or_b >= 8` — 至少 8 个 A 级或 B 级变体

### Phase 3: 稳定性验证（每品种）
- `n_validated_multi_seed >= 3` — 至少 3 个变体通过多种子验证
- `decay_below_threshold <= 2` — 最多 2 个变体衰减超标

## 成功条件

```yaml
success_condition:
  - "all_symbols_pass_phase1"
  - "all_symbols_pass_phase2"
  - "all_symbols_pass_phase3"
```

**要求**: 所有 24 个目标品种都必须通过全部三个阶段。

## 目标品种集（24 个）

```
m, ss, sr, cj, jd, lh, eg, rb, i, p, y, cf, 
bu, fu, ta, ma, fg, ur, px, oi, sh, sp, ao, sc
```

## 修改文件清单

### 核心配置
- ✅ `scripts/praxist_goal.yaml` — 更新为 per-symbol 要求
- ✅ `scripts/praxist_supervisor.py` — build_snapshot() 添加 per-symbol 追踪

### 新增指标
- `symbol_stats` — 每个品种的详细统计
- `all_symbols_pass_phase1/2/3` — 全部品种是否通过各阶段
- `n_symbols_pass_phase1/2/3` — 通过各阶段的品种数

## 当前进度（截至 2026-09-23 21:20）

### 阶段达成情况

| 阶段 | 达标品种 | 目标 | 状态 |
|------|---------|------|------|
| Phase 1 | 1/24 | 24/24 | ⚠️ 仅 sr 达标 |
| Phase 2 | 5/24 | 24/24 | ⚠️ cj, m, rb, ss, sr 达标 |
| Phase 3 | 0/24 | 24/24 | ❌ 未实现 |

### 各品种详细状态

#### ✅ Phase 1 & 2 达标（1 个）
- **sr (白糖)**: 13 过门, DirAcc=0.528, 13 A/B级

#### 🟡 Phase 2 达标，Phase 1 接近（4 个）
- **cj (红枣)**: 8 过门 (需 10), DirAcc=0.511, 15 A/B级
- **m (豆粕)**: 7 过门 (需 10), DirAcc=0.511, 18 A/B级
- **rb (螺纹钢)**: 4 过门 (需 10), DirAcc=0.513, 13 A/B级
- **ss (不锈钢)**: 4 过门 (需 10), DirAcc=0.544, 10 A/B级

#### 🔴 无数据或数据不足（19 个）
- **ao, bu, eg, fg, fu, i, jd, lh, ma, oi, px, sc, sp, ta, ur, y**: 0 过门变体
- **cf**: 1 过门, DirAcc=0.531, 1 A/B级
- **p**: 3 过门, DirAcc=0.565, 2 A/B级
- **sh**: 0 过门, 1 A/B级

## 挑战分析

### 当前难度
- **极高**: 需要所有 24 个品种都达到高标准
- **时间成本**: 部分品种（ao, bu, eg 等）目前 0 过门，需要大量探索
- **数据平衡**: 需要确保每个品种都有足够的协变量探索

### 优势品种
- **sr, cj, m, rb, ss**: 已有良好基础，可快速达标
- 这些品种的协变量家族已验证有效

### 劣势品种
- **ao, bu, eg, fg, fu, i, jd, lh, ma, oi, px, sc, sp, ta, ur, y**: 16 个品种 0 过门
- 可能需要：
  1. 增加探索预算
  2. 调整协变量家族
  3. 重新评估品种可行性

## 建议

### 短期策略
1. **优先推进接近达标的品种**: cj, m, rb, ss（Phase 1 差 2-6 个过门）
2. **保持 sr 的领先地位**: 确保不回归
3. **启动零数据品种探索**: 为 ao, bu 等品种分配专门探索周期

### 中期策略
1. **调整品种优先级**: 根据数据可用性动态调整
2. **增加协变量多样性**: 为零数据品种尝试新的协变量家族
3. **实现 Phase 3**: 多种子验证和衰减检测

### 长期策略
1. **评估品种可行性**: 某些品种可能天然难以达到高标准
2. **考虑动态目标**: 根据品种特性设置差异化目标
3. **引入品种权重**: 核心品种（m, sr, rb）可设置更高标准

## 向后兼容性

保留旧指标用于历史对比：
- `n_one_star_symbols_hit`
- `n_unique_pass_variants`
- `n_families_hit`
- `min_pass_variant_dir_acc`

## 下一步

1. ✅ 更新 goal.yaml 为 per-symbol 要求
2. ✅ 更新 supervisor 添加 per-symbol 追踪
3. ⏳ 实现 Phase 3 的多种子验证和衰减检测
4. ⏳ 为零数据品种启动专项探索
5. ⏳ 更新测试文件和文档

## 风险评估

- **高风险**: 16 个品种 0 过门，达标难度大
- **时间风险**: 可能需要数百个周期才能让所有品种达标
- **可行性风险**: 某些品种可能无法达到高标准

**建议**: 考虑是否真的需要"所有品种"都达标，或改为"核心品种"达标即可。
