# A2-P1 Market 特征向量化优化 Spec

**日期**: 2026-08-05
**状态**: 待审核
**前置**: Dense Matrix 缓存断点恢复（Task 1-4 已完成）

---

## 1. 问题陈述

`extract_market_features_at_bar()` 对每个 eval bar 用全量历史 `closes[:t+1]` 重算滚动特征，导致 **O(N²) 累积**：

```
对 396 个 eval bar，每个重算全量滚动特征：
  calc_rolling_hurst(closes[:t+1])  # t=9960 时重算 ~1640 次 DFA
  calc_pca_momentum(closes[:t+1])   # 每次对全量历史做 PCA
```

**实测**: RB market 阶段 30min+ 未完成（预期 4.5min）。`calc_rolling_hurst` 内部 DFA 多项式拟合是 CPU 杀手。

**阻断全量运行**: 单品种 market 30min + tsfm 71min = 101min > Orchestrator 90min timeout，必然超时。

## 2. 防穿越警报（Lookahead Bias）

🚨 **`calc_pca_momentum` 全局 fitting 泄漏**（已确认源码 line 225-230）：

```python
scaler = StandardScaler()
scaled = scaler.fit_transform(rsi_matrix)   # 用传入数组的全局均值/方差
pca = PCA(n_components=1)
pc1 = pca.fit_transform(scaled)             # 用传入数组的全局协方差
```

若对全量 `closes`（含 2026-07 数据）预计算 PCA，则 `pca_full[100]`（2025 年）被未来数据的方差/相关性污染 -> **未来函数泄漏**。

**安全特征**（纯滚动，固定窗口/阈值）：`hurst`、`hourly_slope`、`rsi_state`、`oi_pct_change`、`daily_slope`。预计算全序列后取 `[t]` 在数学上**严格等价**于 `func(closes[:t+1])[-1]`。

## 3. 混合策略设计

| 特征 | 策略 | 理由 |
|------|------|------|
| hurst | **预计算全序列** | 纯滚动窗口，DFA 瓶颈，安全 |
| hourly_slope | 预计算全序列 | window=24 纯滚动 |
| rsi_state | 预计算全序列 | 固定阈值离散化 |
| oi_pct_change | 预计算全序列 | diff/shift 固定 clip |
| daily_slope | 预计算全序列 | 末尾 lookback+1 纯滚动 |
| **pca_momentum** | **保留切片 closes[:t+1]** | StandardScaler+PCA 全局 fitting，泄漏 |
| vol_prob | 保留切片 | VolRiskFilter.evaluate 涉及模型，保守不预计算 |
| hour_of_day / day_of_week | O(1) 取值 | 纯时间 |

**核心**: hurst（瓶颈）预计算，pca_momentum（危险）保留切片。PCA 矩阵运算毫秒级，留在循环不成为瓶颈。

## 4. 接口设计

### 4.1 `extract_market_features_at_bar()` 新增可选预计算参数

```python
def extract_market_features_at_bar(
    df_1h, df_daily, t_idx, symbol, vol_filter=None,
    precomputed: dict | None = None,   # 新增
) -> Dict[str, float]:
```

`precomputed` 字典（可选）含预计算的全序列数组：
```python
{
    "hurst": np.ndarray,          # calc_rolling_hurst(full_closes)
    "hourly_slope": np.ndarray,   # calc_hourly_slope(full_closes, 24)
    "rsi_state": np.ndarray,      # calc_rsi_state(full_closes, 14)
    "oi_pct_change": np.ndarray,  # calc_oi_pct_change(full_oi)
    "daily_slope": np.ndarray,    # 逐 t 预计算的日线斜率序列
}
```

**逻辑**:
- 若 `precomputed` 提供某特征 -> `feats["hurst"] = float(precomputed["hurst"][t_idx])`（O(1) 取值）
- 若未提供 -> 回退到原切片计算（向后兼容，Copilot 等其他调用方不受影响）
- `pca_momentum`、`vol_prob` **始终切片计算**（不进 precomputed）

### 4.2 `build_dense_feature_matrix()` 预计算安全特征

```python
def build_dense_feature_matrix(...):
    ...
    closes_full = df_1h["close_price"].values.astype(float)
    
    # 预计算安全特征全序列（一次，O(N)）
    precomputed = {
        "hurst": calc_rolling_hurst(closes_full, window=120, step=6),
        "hourly_slope": calc_hourly_slope(closes_full, window=24),
        "rsi_state": calc_rsi_state(closes_full, rsi_period=14),
        "oi_pct_change": calc_oi_pct_change(df_1h["open_interest"]),
        "daily_slope": _precompute_daily_slopes(df_daily, valid),  # 逐 t 但用切片日线
    }
    
    # market 循环：传 precomputed，安全特征 O(1) 取值
    for t in valid:
        feats = extract_market_features_at_bar(
            df_1h, df_daily, t, symbol, vol_filter, precomputed=precomputed
        )
```

**注意**: `daily_slope` 的 `_daily_slope_at` 内部过滤 `df_daily[<=t_dt]` 后取末尾，是纯滚动。预计算时逐 t 调用 `_daily_slope_at`（每个 O(lookback)，非 O(N)），总 O(N×lookback) 可接受；或直接预计算全序列。

## 5. 预期收益

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| market 阶段（单品种） | 30min+ | ~1-2min |
| 全量 20 品种 market | 10h+ | ~40min |
| 单品种总时长 | 101min（超时） | ~73min（< 90min ✅） |
| 全量运行 | 无法完成 | ~24h |

## 6. 验收标准

| 测试 | 预期 |
|------|------|
| **数值一致性** | 预计算模式的 `feats["hurst"][t]` == 切片模式 `calc_rolling_hurst(closes[:t+1])[-1]`（对安全特征全验证） |
| **PCA 防穿越** | `pca_momentum` 仍用 `closes[:t+1]` 切片，不被预计算污染 |
| **性能** | RB market 阶段 < 3min（实测） |
| **向后兼容** | `precomputed=None` 时行为与原版完全一致 |
| **断点续算** | tsfm 断点验证通过（market 快速完成后 kill/restart） |

## 7. 不做的事（Scope）

- 不改 `calc_pca_momentum` 内部（保留全局 fitting，靠切片防穿越）
- 不预计算 `vol_prob`（保守，涉及模型）
- 不改 tsfm 断点机制（Task 1-4 已完成）
- 不改 12 维特征池 / step=24 / Gate

---

**下一步**: 用户审核 -> 批准后写 Implementation Plan。
