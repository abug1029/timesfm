# 多样性指标 (Diversity Metrics)

## 目的

监控提案探索的多样性，防止过度集中在少数 symbol/family 组合，确保探索覆盖更多可能性。

## 指标说明

### 1. Symbol 分布熵 (Symbol Entropy)

- **公式**: H = -Σ(p_i * log(p_i))，其中 p_i = symbol_i 的提案数 / 总提案数
- **单位**: nats (自然单位)
- **解释**: 值越高表示 symbol 分布越均匀；最大熵 = log(n_symbols)
- **示例**: 4 个 symbol 均匀分布 → H ≈ 1.386；集中在 1 个 → H ≈ 0

### 2. Family 分布熵 (Family Entropy)

- **公式**: 同上，针对 covariate_family
- **解释**: 衡量 family 分布的均匀程度

### 3. Symbol-Family 组合覆盖率 (Combination Coverage)

- **公式**: 已探索的 (symbol, family) 组合数 / 可能的组合数
- **可能的组合数**: n_symbols × n_families
- **解释**: 0% = 只探索少数组合；100% = 探索所有组合
- **用途**: 识别未探索的 symbol-family 空间

### 4. 平均新颖度 (Average Novelty)

- **公式**: 1 - max(cosine_similarity(new_mechanism, historical_mechanism))
- **方法**: 基于 mechanism 文本的 TF 余弦相似度（stdlib 实现，无 sklearn 依赖）
- **解释**: 1.0 = 完全新颖；0.0 = 与历史完全相同

## 使用方法

### 计算指标（JSON 输出）

```bash
cd /home/abug/timesfm
python3 scripts/diversity_metrics.py compute --proposals task_FM/experiments
```

输出示例：
```json
{
  "symbol_entropy": 1.9275,
  "family_entropy": 1.4942,
  "combination_coverage": 0.4,
  "avg_novelty": 1.0,
  "n_proposals": 19,
  "n_unique_symbols": 8,
  "n_unique_families": 5,
  "n_unique_combinations": 8,
  "n_possible_combinations": 20
}
```

### 生成 Markdown 报告

```bash
python3 scripts/diversity_metrics.py report --proposals task_FM/experiments -o diversity_report.md
```

### 指定已知 symbol/family 列表（用于覆盖率分母）

```bash
python3 scripts/diversity_metrics.py compute \
  --proposals task_FM/experiments \
  --symbols ta cf m rb sr ss \
  --families calendar momentum inventory term_structure volatility
```

## 当前状态（2026-10-20）

运行 `python3 scripts/diversity_metrics.py compute --proposals task_FM/experiments`：

| 指标 | 值 | 解读 |
|------|-----|------|
| 提案总数 | 19 | - |
| 唯一 symbols | 8 | ta, cf, m, rb, sr, ss, cj, eg |
| 唯一 families | 5 | calendar, momentum, inventory, term_structure, volatility |
| 唯一组合 | 8 | 已探索的 (symbol, family) 对 |
| 可能组合 | 20 | 8 symbols × 5 families（实际是 2×5=10，但有 4 个 symbol 缺 family） |
| Symbol 熵 | 1.9275 nats | 较均匀（最大 log(8) ≈ 2.08） |
| Family 熵 | 1.4942 nats | 中等（最大 log(5) ≈ 1.61） |
| 组合覆盖率 | 40.0% | 还有 60% 未探索 |
| 平均新颖度 | 1.0000 | 所有提案都是新的（无历史对比） |

## 多样性奖励集成（可选）

在 `scripts/generation_strategy.py` 的 `get_sampling_quota` 中加入多样性奖励：

```python
def get_sampling_quota_with_diversity(symbol, family, quality_predictor, diversity_metrics):
    # 基础质量分
    quality_score = quality_predictor.predict(symbol, family)
    
    # 多样性奖励
    combo_key = (symbol, family)
    if combo_key not in diversity_metrics.explored_combinations:
        diversity_bonus = 0.5  # 未探索组合加 0.5
    else:
        diversity_bonus = 0.0
    
    # 组合分数
    adjusted_score = quality_score + diversity_bonus
    
    return adjusted_score
```

## 测试

```bash
cd /home/abug/timesfm
.venv/bin/python -m pytest tests/test_diversity_metrics.py -v
```

12 个测试用例：
- `test_symbol_entropy_uniform`: 均匀分布时熵最大
- `test_symbol_entropy_concentrated`: 集中分布时熵小
- `test_family_entropy`: family 熵计算正确
- `test_combination_coverage`: 组合覆盖率计算正确
- `test_combination_coverage_with_known_universe`: 带已知全宇宙的覆盖率
- `test_novelty_scores`: novelty 分数计算正确（TF 余弦）
- `test_novelty_scores_no_history`: 无历史时 novelty = 1.0
- `test_novelty_scores_different_text`: 不同文本时 novelty 高
- `test_diversity_report`: 报告生成正确
- `test_empty_proposals`: 空提案列表处理
- `test_empty_proposals_entropy`: 空列表熵为 0
- `test_diversity_bonus_integration`: 多样性奖励集成逻辑

## 实现细节

- **依赖**: 仅 stdlib（math, json, re, collections.Counter）
- **TF-IDF**: 简化为 TF（词频）+ 余弦相似度，无 sklearn
- **Tokenizer**: 支持英文 + 中文（正则 `[a-zA-Z一-鿿]+`）
- **提案加载**: 递归扫描 `*_proposal.json` 文件
- **字段提取**: 
  - symbol: `extra.symbol`
  - family: `design_dimensions.covariate_family`
  - mechanism: `extra.mechanism` 或 `content`

## 验证

```bash
# 运行计算
python3 scripts/diversity_metrics.py compute --proposals task_FM/experiments

# 生成报告
python3 scripts/diversity_metrics.py report --proposals task_FM/experiments

# 运行测试
.venv/bin/python -m pytest tests/test_diversity_metrics.py -v
```
