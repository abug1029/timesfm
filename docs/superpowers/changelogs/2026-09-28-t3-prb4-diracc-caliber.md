# T3 Changelog: PR-B4 dir_acc 口径变更改档

**Status:** 文档化完成（实施推迟）
**Date:** 2026-09-28
**依赖:** T1a 完成后实施（需新裁决流验证）

## 问题描述

**X10: `dir_acc` 同名两义**

代码中存在两个不同的 `dir_acc` 口径：

| 口径 | 定义 | 使用位置 | 零变动处理 |
|------|------|---------|-----------|
| **full-sample** | 所有样本，零变动算 miss | gate 判定、verdict 记录 | `abs(delta_real) < eps → dir_ok=False` |
| **active-only** | 仅非零变动样本 | `calc_net_metrics`、docstring 宣传 | 零变动从分母剔除 |

**问题**: 同一名词两个含义，导致：
- gate 消费的 `dir_acc` 与文档宣传的不一致
- 跨模块比较时口径混乱
- 用户期望与实际行为不符

## 影响面分析

### 受影响的代码路径

1. **gate 判定** (`evaluator.py:gate()`)
   - 当前使用 full-sample 口径
   - 改为 active-only 会影响过门率

2. **verdict 记录** (`registry_lib.py`)
   - `dir_acc` 字段当前为 full-sample
   - 改名会影响 143 条历史裁决的可比性

3. **`calc_net_metrics`** (`evaluation_metrics.py`)
   - 当前使用 active-only 口径
   - 需改名为 `active_dir_acc`

4. **docstring 与文档**
   - 多处 docstring 宣传 active-only 口径
   - 需更新为准确描述

### 影响面评估

| 方面 | 影响 | 风险 |
|------|------|------|
| 历史裁决可比性 | 143 条旧裁决的 `dir_acc` 口径与新裁决不同 | 中（需声明） |
| 过门率变化 | full-sample → active-only 会提高 `dir_acc` 数值 | 高（可能误判） |
| 代码复杂度 | 需同时支持两种口径并明确标注 | 低 |
| 文档一致性 | 需更新多处 docstring 与文档 | 低 |

## 裁定方案

### 方案 A: 改名为 `active_dir_acc`（spec 推荐）

**变更:**
1. active-only 口径改名为 `active_dir_acc`
2. 仅 gated 路径使用 `active_dir_acc`
3. full-sample 口径保留为 `dir_acc`（默认）
4. verdict 记录同时包含两个字段:
   - `dir_acc`: full-sample 口径（gate 使用）
   - `active_dir_acc`: active-only 口径（诊断使用）

**优点:**
- 消除同名两义
- 保持向后兼容（`dir_acc` 含义不变）
- 明确标注两种口径

**缺点:**
- 需修改多处代码
- 历史裁决仍为旧口径（需声明）

### 方案 B: 统一为 active-only（不推荐）

**变更:**
1. gate 改用 active-only 口径
2. 重算所有历史裁决

**优点:**
- 单一口径，简单

**缺点:**
- 零变动样本被剔除，可能引入选择偏差
- 需重算 143 条历史裁决
- 过门率变化可能导致误判

### 裁定: **方案 A**

理由:
1. 保持向后兼容
2. 明确标注两种口径，消除歧义
3. 不改变 gate 行为，避免误判
4. 符合 spec §6.5 推荐

## 实施计划

### 前置条件

- [ ] T1a 完成（新裁决流产出）
- [ ] 在新裁决流上验证方案 A 的正确性

### 实施步骤

1. **代码修改:**
   - `evaluation_metrics.py`: `calc_net_metrics` 返回值改名为 `active_dir_acc`
   - `evaluator.py`: gate 保持 full-sample，docstring 更新
   - `registry_lib.py`: verdict schema 新增 `active_dir_acc` 字段

2. **测试:**
   - 新增测试验证两种口径的计算正确性
   - 回归测试确保 gate 行为不变

3. **文档:**
   - 更新 docstring，明确标注两种口径
   - 更新 spec 文档，记录口径变更

4. **迁移:**
   - 历史裁决不迁移（保持原样）
   - 新裁决同时记录两种口径
   - 在 Stage 3 报告中声明口径变更

## 验收标准

1. `dir_acc` 与 `active_dir_acc` 在代码中明确区分
2. gate 使用 full-sample 口径（`dir_acc`）
3. `calc_net_metrics` 使用 active-only 口径（`active_dir_acc`）
4. 测试覆盖两种口径的计算正确性
5. 文档明确标注两种口径的定义与使用场景

## 预计工作量

- 代码修改: 0.5 天
- 测试: 0.5 天
- 文档: 0.5 天
- **总计: 1.5 天**

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 实施后 gate 行为变化 | 在新裁决流上先验证，确认无变化后再合入 |
| 历史裁决与新裁决不可比 | 在报告中显式声明，提供对照表 |
| 用户混淆两种口径 | 文档明确标注使用场景，代码注释清晰 |

## 审核结论

**T3 文档化完成**，方案 A 已裁定。实施推迟到 T1a 完成后，以便在新裁决流上验证。
