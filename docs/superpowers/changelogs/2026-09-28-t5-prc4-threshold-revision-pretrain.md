# T5-PR-C4 Changelog: 门槛一致性 + 历史修订防护 + 预训练登记

**Status:** 文档化完成，待实施
**Date:** 2026-09-28
**Spec:** §4.6 W6.6, W6.7, W6.8

## 问题描述

PR-C4 解决三个独立但相关的问题：

1. **X4 门槛一致性**：无基线品种使用 fallback 门槛，不参与跨品种比较
2. **X8 历史修订防护**：context 窗口内容变化后 verdict 应标记为不可信
3. **X11 预训练污染登记**：登记为残余风险，不做诊断性检验

## 实施方案

### W6.6 门槛一致性前置条件（治 X4）

**要求**：成功判定要求 `baseline_dir_acc is not None`。

**实现**：
1. 在 `evaluator.py` 的成功判定逻辑中：
   ```python
   if baseline_dir_acc is None:
       gate_basis = "fallback_0.52"
       # 不参与成功判定
       # 不参与跨品种比较
   else:
       gate_basis = "baseline"
   ```

2. verdict 落 `gate_basis` 字段（`"baseline"` 或 `"fallback_0.52"`）

3. PR-A4 的 `baseline_points_{sym}_nocov.jsonl` 必须覆盖全部有 verdict 的品种（当前缺 cf/i/jm/ma/p/sh 六个）

**测试**（L1 测试 31）：
- `baseline_dir_acc is None` 的 verdict 落 `gate_basis="fallback_0.52"`
- 不参与成功判定与跨品种比较

### W6.7 历史修订防护（治 X8）

**要求**：verdict 落 `context_hash`，后续重算发现哈希变化则标记 `data_revised=true` 并退出成功判定。

**实现**：
1. 在 `evaluator.py` 中计算 context 窗口的内容哈希：
   ```python
   context_hash = hashlib.sha256(
       context_window.tobytes()  # 480 bar 的收盘序列
   ).hexdigest()[:16]
   ```

2. verdict 落 `context_hash` 字段

3. 重算时比对 `context_hash`：
   ```python
   if old_context_hash != new_context_hash:
       data_revised = True
       # 退出成功判定
   ```

4. `future_bar_guard` 只防未来行，历史修订必须靠哈希自证

**测试**（L1 测试 32）：
- context 内容变化后重算的 verdict 落 `data_revised=true`
- 退出成功判定

### W6.8 预训练污染登记（治 X11）

**宿主裁定**：仅登记，不做诊断性检验，不阻塞阶段二。

**理由**：
- 评估窗内时间分半无法证伪泄漏
- 已标注 cutoff 与评估窗间隔 ≥2 年
- 中国期货 1H 合约数据不太可能进入 Google 公开语料

**实现**：
1. verdict 落预训练风险登记字段：
   ```python
   pretrain_risk = {
       "status": "registered",
       "model_card_cutoffs": {
           "wikipedia_pageviews": "Nov 2023",
           "google_trends": "EoY 2022"
       },
       "eval_window": "2026-01 to 2026-09",
       "gap_years": 2,
       "gift_eval_pretrain_cutoff": "unlabeled"
   }
   ```

2. **断言无诊断性检验被强制执行**（已裁定仅登记）

3. 若日后出现"模型在某品种上异常强"且无机制解释，本条作为首选怀疑方向重新审视

**测试**（L1 测试 33）：
- 预训练风险登记字段存在
- 断言无诊断性检验被强制执行

## 实施步骤

### 1. 修改 `evaluator.py`

在 verdict 生成逻辑中添加：

```python
# W6.6: 门槛一致性
if baseline_dir_acc is None:
    gate_basis = "fallback_0.52"
    # 标记不参与成功判定
else:
    gate_basis = "baseline"

# W6.7: 历史修订防护
context_hash = hashlib.sha256(
    context_window.tobytes()
).hexdigest()[:16]

# W6.8: 预训练登记
pretrain_risk = {
    "status": "registered",
    "model_card_cutoffs": {...},
    "eval_window": "...",
    "gap_years": 2
}
```

### 2. 修改 `registry_lib.py`

在 VERDICT_FIELDS 中添加：
- `gate_basis`
- `context_hash`
- `data_revised`
- `pretrain_risk`

### 3. 重算逻辑

在重算脚本中：
```python
if old_verdict["context_hash"] != new_context_hash:
    new_verdict["data_revised"] = True
    # 退出成功判定
```

### 4. 测试

- 测试 `baseline_dir_acc is None` 时 `gate_basis="fallback_0.52"`
- 测试 context 变化后 `data_revised=true`
- 测试预训练登记字段存在
- 测试无诊断性检验被强制执行

## 预计工作量

- 代码实现: 1 天
- 测试: 0.5 天
- **总计: 1.5 天**

## 依赖

- 不依赖 T1a（可并行实施）
- 需要理解当前 verdict 生成逻辑

## 风险

1. **性能风险**：计算 context_hash 需要遍历 480 bar，但这是 O(n) 操作，影响可忽略
2. **兼容性风险**：旧 verdict 无 `context_hash` 字段，重算时需要处理
3. **前视风险**：无，context_hash 仅用于事后验证

## 验收标准

1. 所有 verdict 都有 `gate_basis` 字段
2. 所有 verdict 都有 `context_hash` 字段
3. 所有 verdict 都有 `pretrain_risk` 字段
4. `baseline_dir_acc is None` 的 verdict 不参与成功判定
5. context 变化后 verdict 标记 `data_revised=true`
6. 所有 L1 测试 31/32/33 通过

## 审核结论

**T5-PR-C4 文档化完成**。实施推迟，需 1.5 天工作量。
