# Phase 15: 新协变量开发设计文档

> **文档状态（2026-09-11）**：晋升进 SCHEMES 的目标 **失效**。`STATE.md`：24 tests **0 GREEN**。NVI / QSTICK / VWAP / StdDev 函数仍留在 `cascade/features.py` 池内。**不要写入** `config/prediction_scheme.py`。

> **日期**: 2026-08-22
> **状态**: 固化目标失效（2026-09-11 标注；原「待审核」过期）
> **前置**: Phase 11-13 穷举结论 (协变量组合优化触顶)
> **来源**: 知乎交易指标综合研究报告

---

## 1. 目标

为 FM_a 预测系统引入 4 个全新信号维度的协变量，突破 6 个弱信号品种 (JM/MA/UR/FG/CF/AO) 的 PF 天花板。

**成功标准**:
```
PF >= 1.0 AND EV_ratio > 0 AND abs(MaxDD) < 80% AND n_eval >= 350
```
> n_eval 门槛与 AO full-signal 裁决一致 (AO PF=0.978 但 n=193<350 未固化)。

**失败处理**: 24 tests 全 FAIL → 进入 Phase 15b 组合阶段 (hard cap 见 §5) → 仍 FAIL 则宣告协变量路径彻底穷尽。

---

## 1.5 与已有 Phase 的关系

> 避免重蹈覆辙，明确 Phase 15 的增量空间。

| Phase | 做了什么 | 结论 | Phase 15 的差异 |
|:------|:---------|:-----|:----------------|
| Phase 11 | 单协变量穷举 (~16 类 × 22 品种, 138 tests) | 34 GREEN, 12 品种固化 | Phase 15 的 NVI/VWAP/QSTICK/StdDev 均不在 Phase 11 穷举列表中 |
| Phase 12 | 弱信号品种换协变量 (BU/CF/P 等) | BU→calendar_cyclical+hourly_slope (PF=1.01), P→rsi_state+reversal_shadow (PF=1.01) | Phase 15 针对 Phase 11/12 后仍为 1★ 的 6 个品种 |
| Phase 13 | 弱信号组合优化 | 18 tests 0 GREEN, 宣告天花板 | Phase 15 用"全新维度"而非"旧协变量组合"尝试突破 |

**关键问题**：Phase 13 已宣告"组合优化天花板"，为什么 Phase 15 能突破？
- Phase 13 试的是**现有协变量的组合**，信息维度未扩展
- Phase 15 引入 4 个**新信息维度**（聪明资金流 / K线实体强度 / 量价公允偏离 / 收盘价分布）
- 前提：新协变量与现有 19 个协变量的 rolling correlation < 0.7 (见 §3.4 预检)

**当前协变量全景** (`cascade/features.py` L1427-1432, 共 19 个类型)：

| 维度 | 协变量 |
|:-----|:-------|
| 持仓 | oi |
| 动量 | rsi_state, rsi_slope, hourly_slope, pca_momentum, ao_accel |
| 波动 | vor, bb_squeeze |
| 形态 | ha_body, reversal_shadow (+3 gated 变体), sar_dist |
| 日历 | calendar_cyclical |
| 价差 | crack_spread_slope/level/zscore |
| 其他 | hurst, basis_momentum |

**Phase 15 新增的维度**：
- NVI → 聪明资金流（无重叠）
- QSTICK → K线实体强度（与 ha_body 部分重叠，需预检相关性）
- VWAP偏离 → 量价公允偏离（无重叠）
- StdDev → 收盘价分布（与 vor 可能重叠，需预检相关性）

---

## 2. 新协变量定义

### 2.1 NVI (负成交量指标)

**信息维度**: 聪明资金流 — 缩量日累积收益追踪机构行为

**公式**:
```
NVI[0] = 1000
if volume[i] < volume[i-1]:  # 缩量日
    NVI[i] = NVI[i-1] * (1 + (close[i] - close[i-1]) / close[i-1])
else:
    NVI[i] = NVI[i-1]
```

**输出**: rolling z-score (lookback=20)，标准化为均值为 0、标准差为 1 的序列

> **Trade-off 说明**: rolling z-score 会丢失 NVI 的长期累积信息。这是为了平稳性接受的折衷。如后续发现信号弱，可考虑追加"原始 NVI slope"作为第二特征。

**与现有协变量关系**: 无重叠。现有 19 类协变量均无资金身份识别维度。

**数据依赖**: close_price, volume (`kline_1h` 表确认存在两列)

> **volume 缺失处理**: volume 为 NULL 的 bar **跳过该 bar**（不触发累积也不重置），连续 NULL>6 则该段 NVI 置 NaN→0 回退。**不用 open_interest 替代**——OI 单调性强，无"缩量日"语义，替代会破坏 NVI 定义。

### 2.2 QSTICK (K线优势指标)

**信息维度**: K线实体多空力量

**公式**:
```
QSTICK = SMA(close - open, 14)
```

**输出**: QSTICK / rolling_std(QSTICK, 60)，标准化后的多空力量

**与现有协变量关系**: 与 ha_body 部分重叠 (ha_body 是 sign(close-open)，仅编码方向)。QSTICK 同时编码方向和强度，信息更丰富。

> **共线性预检**: 实现前必须跑 rolling corr(QSTICK, ha_body)，若 >0.85 则两者不应同时出现在 combo 中。

**数据依赖**: close_price, open_price

### 2.3 VWAP偏离

**信息维度**: 量价公允偏离度 — 均值回归信号

**公式**:
```
typical_price = (high + low + close) / 3
VWAP = Σ(typical_price × volume, 24) / Σ(volume, 24)
deviation = (close - VWAP) / VWAP
```

**输出**: 原始偏离值 (自然约束在 [-1, 1] 范围)

**与现有协变量关系**: 无重叠。全新均值回归信号，与现有动量类协变量互补。

**数据依赖**: high, low, close_price, volume (`kline_1h` 表确认四列均存在)

> **high/low 缺失处理**: high/low 任一为 NULL 则该 bar 的 VWAP 置 NaN→0 回退。**不用 close 替代**——close-only 时 typical_price = close，VWAP 退化为 volume 加权的 close 均值，与 close 高度共线，不再是原指标。

### 2.4 StdDev (收盘价标准差)

**信息维度**: 市场恐慌度 / 趋势状态过滤器

**公式**:
```
StdDev = std(close, 20)
normalized = (StdDev - mean(StdDev, 60)) / mean(StdDev, 60)  # 百分比偏离
```

**输出**: 标准化偏差值 (>0 表示当前波动高于长期均值, <0 表示低于)

**与现有协变量关系**: vor 基于 high-low range (True Range 的 smoothed mean)，StdDev 基于收盘价分布。两者在高波动期同步抬升，**可能存在相关性**。

> **共线性预检**: 实现前必须跑 rolling corr(StdDev, vor)，若 >0.85 则 StdDev 信息冗余，无法突破天花板。

**数据依赖**: close_price

---

## 3. 实现架构

### 3.1 文件修改

**`cascade/features.py`**:
- 新增 4 个计算函数: `_calc_nvi()`, `_calc_qstick()`, `_calc_vwap_deviation()`, `_calc_stddev()`
- `build_covariate_matrix()` 添加 4 个 elif 分支
- `build_combo_covariate_matrix()` 添加 4 个 elif 分支
- `supported` 列表追加 4 个 key

**`tests/test_new_covariates.py`** (新建):
- 每个协变量的输出 shape / NaN / 值域测试
- 组合模式包含新协变量的集成测试

**`scripts/batch_p15_new_cov.sh`** (新建):
- Phase 15a 批次脚本: 6 品种 × 4 协变量 = 24 tests
- 使用 `_batch_lib.sh` 的 `batch_run_one` 框架

### 3.2 参数表

| 协变量 | lookback | 标准化窗口 | 标准化方式 | 协变量 key |
|:-------|:--------:|:----------:|:----------|:----------|
| NVI | 20 | 20 | z-score | `nvi` |
| QSTICK | 14 | 60 | / rolling std | `qstick` |
| VWAP偏离 | 24 | — | 原始值 | `vwap_deviation` |
| StdDev | 20 | 60 | 百分比偏离 | `stddev` |

### 3.3 数据流

```
monthly_backtest.py --combo "nvi"
  → hourly_model.predict(covariate_types=["nvi"])
    → build_covariate_matrix() / build_combo_covariate_matrix()
      → _calc_nvi(df_1h, lookback=20)
        → 从 SQLite 1H 数据读取 close_price, volume
        → 计算 NVI 累积序列 (volume NULL bar 跳过)
        → rolling z-score 标准化
        → 返回 np.ndarray
```

### 3.4 实现前必做的相关性预检

> Phase 13 教训：组合优化失败的主因是协变量间信息冗余。Phase 15 必须先验证"新维度"确实新。

对每个弱信号品种（以 SS 为 proxy）：
1. 计算 4 个新协变量的原始序列
2. 计算与现有 19 个协变量的 rolling correlation (window=60)
3. 判定：
   - mean |corr| < 0.5 → 通过，继续实现
   - 0.5 ≤ mean |corr| < 0.7 → 警告，保留但记录
   - mean |corr| ≥ 0.7 → 放弃该协变量，信息冗余

**预检脚本**: `scripts/p15_corr_precheck.py` (新建)
**预计耗时**: ~30min (单品种)

---

## 4. 测试矩阵

### Phase 15a: 弱信号品种 (24 tests)

| 品种 | nvi | qstick | vwap_deviation | stddev |
|:-----|:---:|:------:|:--------------:|:------:|
| JM | ✓ | ✓ | ✓ | ✓ |
| MA | ✓ | ✓ | ✓ | ✓ |
| UR | ✓ | ✓ | ✓ | ✓ |
| FG | ✓ | ✓ | ✓ | ✓ |
| CF | ✓ | ✓ | ✓ | ✓ |
| AO | ✓ | ✓ | ✓ | ✓ |

**预计耗时**: ~24h (24 × 40min + 数据准备 + baseline 对比 + 失败重试 overhead)

### Phase 15b: 组合阶段 (条件触发, hard cap)

**触发条件**: Phase 15a 中至少 1 个品种的新协变量 PF 较 baseline 提升 >5%（即使未 GREEN）。

**筛选策略**（防组合爆炸）:
1. 仅对"PF 提升 >5%"的品种进入组合
2. 每个品种最多尝试 5 个组合（优先与 baseline 协变量互补性最强的新协变量）
3. Hard cap: 总组合 tests ≤ 30

**预计耗时**: ≤ 20h (30 × 40min)

### Phase 15c: 已 GREEN 品种验证 (条件触发)

**触发条件**: Phase 15a 中至少 1 个品种达到 GREEN。

对已 GREEN 品种测试新协变量作为 additive:
- 对每个 Phase 15a GREEN 的新协变量 X:
  - 对每个已 GREEN 品种，跑 `--combo "当前协变量,X"`
  - 对比 baseline (当前 scheme) 的 PF

**预计耗时**: 视触发数量, 4-20 tests

---

## 5. 评估标准

### GREEN 判定 (与现有标准一致)

```
PF >= 1.0 AND EV_ratio > 0 AND abs(MaxDD) < 80% AND n_eval >= 350
```

### 固化决策

- 新协变量 GREEN → 跑 baseline 对比 (当前 scheme)
- baseline FAIL → 替换为新协变量
- baseline PASS → 保持当前方案

### 退出条件

| 场景 | 处理 |
|:-----|:-----|
| ≥1 GREEN, baseline FAIL | 固化新协变量 |
| ≥1 GREEN, baseline PASS | 保持当前方案 (新协变量未超越) |
| 0 GREEN, 但 PF 提升 >5% | 进入 Phase 15b 组合 (hard cap 30 tests) |
| 0 GREEN, PF 无提升 | 宣告协变量路径彻底穷尽 |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|:-----|:-----|:-----|
| NVI 对 volume 数据质量敏感 | SQLite 1H volume 可能有 NULL | NULL bar 跳过累积，连续 NULL>6 置 NaN→0 回退。**不用 OI 替代** |
| VWAP 需要 high/low 数据 | 部分 1H 表可能缺失 | high/low 任一 NULL 则 VWAP→NaN→0 回退。**不用 close 替代**（退化为 close 加权均值，失去指标含义） |
| 24 tests 全 FAIL | 浪费 ~24h 算力 | 渐进式策略: 先跑 6 tests (1 品种 × 4 协变量 + 相关性预检), 确认方向后再扩展 |
| 新协变量与现有协变量高度相关 | 信息冗余, 无法突破 | **实现前必做相关性预检** (§3.4), mean |corr| ≥ 0.7 的协变量直接放弃 |
| QSTICK 与 ha_body 共线 | 两者同时 GREEN 时选哪个？ | 预检 corr>0.85 时禁止 combo 同现；若都 GREEN 则选 PF 更高者 |
| StdDev 与 vor 共线 | 信息冗余 | 预检 corr>0.85 时放弃 StdDev |

---

## 7. 交付物

| 交付物 | 路径 |
|:-------|:-----|
| 相关性预检脚本 | `scripts/p15_corr_precheck.py` |
| 相关性预检结果 | `reports/research/20260822_phase15_corr_precheck.md` |
| 4 个新协变量实现 | `cascade/features.py` |
| 单元测试 | `tests/test_new_covariates.py` |
| Phase 15a 批次脚本 | `scripts/batch_p15_new_cov.sh` |
| Phase 15a JSONL 数据 | `reports/data_ops/batch_p15a_progress.jsonl` |
| Phase 15a 结果报告 | `reports/research/20260822_phase15a_results.md` |
| KB 重建 (如固化) | `config/knowledge_base.json` |
| Registry 更新 | `docs/backtest_registry.md` (6 品种追加 Phase 15 行) |

---

## 8. 总耗时估算

| 阶段 | 耗时 |
|:-----|:-----|
| 相关性预检 | 0.5h |
| Phase 15a (24 tests) | 24h |
| Phase 15b (条件触发, ≤30 tests) | ≤20h |
| Phase 15c (条件触发, 4-20 tests) | ≤14h |
| 文档 + KB 重建 | 2h |
| **总计 (最坏情况)** | **~60h** |
| **总计 (15a 即收敛)** | **~27h** |
