# 慢环评估点位研究：从配置瓶颈到交易机制的深层问题

> **文档状态（2026-09-11）**：**历史研究**。正文当考古，不当施工单。
>
> - `STEP` 现为 **2**，`EVAL_WINDOW_BARS=1200`（`ee1f176`）。
> - 回测无条件含当日日线 **已修**：`hour>=15` 才含当日（`ee1f176`）。不要按本文再改 `BacktestDataStore`。
> - `get_safe_daily` 已存在（`ba361df`），但 `DailyModel.predict` 仍裸读 `get_main_continuous`。
> - 正文里的「必须立即修复 / 待执行」**不是现行待办**。
>
> 部分取代：`ee1f176` + SPEC-003 / `get_safe_daily`。实盘预测缺口见 `docs/superpowers/reports/2026-09-11-audit/SUMMARY.md` CC-1。

**研究日期**：2026-09-09  
**研究者**：Claude Code  
**审核者**：用户（量化交易专家）  
**状态**：历史（2026-09-09 调研；回测 STEP/前视已落地，勿再当待办）

---

## 摘要

本研究从用户提出的"慢环测试点位应该增加到 600 个"出发，经过三轮迭代调研，逐步揭示了三个层次的问题：

1. **配置层**：evaluator 硬顶 500 → 已修复为 600（提交 `feedf44`）
2. **采样层**：STEP=24 导致实际只有 396 评估点 → 建议改为 STEP=2
3. **机制层**：发现两个致命理论隐患
   - 交易日历断点 vs. TimesFM 预训练先验（未验证，需实证）
   - **级联架构的日内前视偏差（当时已确认存在；回测无条件含当日已修，见文首）**

**关键发现（2026-09-09）**：当时回测系统存在严重的前视偏差（lookahead bias），所有日内评估点都使用了"未来"的日线数据。回测无条件含当日已在 `ee1f176` 修复（`hour>=15`）；「必须立即修复」不是现行待办。

---

## 一、研究背景

### 1.1 用户需求

> "慢环测试的点位应该增加到 600 个"

### 1.2 系统架构

```
日线模型 (TimesFM)
  ↓ 用日 K 线预测日级趋势（每天更新一次）
小时模型 (TimesFM + XReg)
  ↓ 用连续 1H 线 + 日线预测 → 预测未来 24 根 1H 线
交易策略
  ↓ 日线定方向 + 小时线定时机（每天决策 3 次）
```

### 1.3 初始状态

- `goal.yaml` 配置 `aligned_max_points: 600`
- 实际慢环只跑了 396 点
- 所有目标品种（eg/ss/rb/jd/sr/m）都是 396 点

---

## 二、第一轮调研：配置层瓶颈

### 2.1 发现：evaluator 硬顶 500

**问题**：
```python
# task_FM/evaluations/fm_eval/evaluator.py:124
"aligned": (350, 500),  # 硬顶 500
```

**修复**：改为 `(350, 600)`，supervisor 默认值 400 → 600

**提交**：`feedf44`

### 2.2 发现：实际仍只有 396 点

即使配置改为 600，所有品种实际都只跑了 396 点。

---

## 三、第二轮调研：采样层瓶颈

### 3.1 根本原因：STEP=24 的采样公式

```python
# scripts/monthly_backtest.py:215
eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))
```

**参数**（来自 `config/backtest_config.py`）：

| 参数 | 值 | 含义 |
|------|---|------|
| CONTEXT_BARS | 480 | 前 480 根 1H bar 作 warmup（=20 天）|
| HORIZON | 24 | 预测未来 24 根 1H bar |
| STEP | 24 | 每 24 根取一个评估起点 |
| total | ~10000 | 数据库 1H bar 总数 |

**计算**：
```
eval_indices = range(480, 10000 - 24 + 1, 24)
             = range(480, 9977, 24)
             = 396 个点
```

### 3.2 第一次修订方案：STEP=16

**用户审核意见**：
> "每 16 根 1H Bar 相当于每 3 到 4 个交易日才采样一次，确实过于稀疏"

**问题**：脱离了国内期货的实际交易时间。

### 3.3 第二次修订方案：STEP=2

**关键认知修正**：

国内商品期货每天只有 5-6 根 1H bar，不是 24 根！

| 品种类型 | 日交易时长 | 日均 1H bar |
|---------|-----------|------------|
| 有夜盘（rb/m/eg/ss/sr）| 5.75h | **5-6 根** |
| 无夜盘（jd）| 3.75h | **4 根** |

**重新计算**：
```
STEP=24 → 每 24 bars ÷ 5.5 bars/day ≈ 4.4 个交易日（每周评估 1-2 次）
STEP=16 → 每 16 bars ÷ 5.5 bars/day ≈ 2.9 个交易日（每 3 天评估 1 次）
STEP=2  → 每 2 bars ÷ 5.5 bars/day ≈ 0.36 个交易日（每天评估 3 次）✓
```

**方案**：
- STEP = 2（每天评估 3 次，匹配日内交易节奏）
- EVAL_WINDOW_BARS = 1200（600 点 × 2 = 1200 bars ≈ 200 交易日 ≈ 1 年）
- 聚焦最近 1 年行情，避免 Concept Drift

**耗时估算**：
- 单变体：600 点 × 0.75s/点 ≈ 7.5 min
- 25 变体：7.5 min × 25 = 3.1 h
- 占 30h 预算：10.3%

---

## 四、第三轮调研：理论隐患（用户审核发现）

### 4.1 隐患 1：交易日历断点 vs. TimesFM 预训练先验

**风险描述**：

TimesFM 在自然时间序列上预训练，内建了 24h/天、7 天/周的周期性先验。国内期货每天仅 5-6 根 1H bar，存在大量时间断点：
- 夜盘→早盘：23:00→09:00（10 小时空白）
- 午休：11:30→13:30（2 小时空白）
- 周末：周五 23:00→周一 09:00（58 小时空白）

**潜在问题**：模型可能将"每 5-6 bar = 1 天"的期货节奏误判为"每 24 bar = 1 天"的自然节奏。

**代码验证**：
- TimesFM 主输入：仅价格序列（`close_price` 数组），**不接收 datetime 特征** ✓
- 协变量构建：使用 datetime 构建技术指标（RSI/MACD 等），标准做法 ✓
- 周期性先验：未经实证验证 ⚠️

**结论**：理论上安全，但需要实证验证。

### 4.2 隐患 2：级联架构的日内前视偏差 ❌ **已确认存在**

**铁证**：

```
日线 bar 2026-09-08:
  close_price = 5925.0
  updated_at  = 2026-09-08 10:39:07  ← 盘中更新！

1H bar 2026-09-08 14:00:
  close_price = 5925.0  ← 与日线收盘一致
```

**问题机制**：

```python
# data/data_store.py:BacktestDataStore
def get_main_continuous(self, limit=None, **kwargs):
    """日线数据: 截断到 cutoff 日历日 (含当日日线 bar)"""
    return super().get_main_continuous(
        end_date=self.cutoff_day, limit=limit  # ← 包含当天！
    )
```

**穿越路径**：
1. 回测 cutoff = `2026-09-08 10:30:00`
2. 查询日线：`end_date='2026-09-08'`
3. 返回日线 bar 2026-09-08，close=5925.0
4. 但这个 close 包含了 10:39 甚至 14:00 的数据（**未来 3.5 小时！**）
5. 日线模型用这个"未来收盘价"生成 daily_result
6. 小时模型用 daily_result 做预测 → **前视偏差**

**影响范围**：

| 场景 | cutoff 时间 | 日线数据包含 | 前瞻量 |
|------|------------|-------------|--------|
| 夜盘初 | 21:00 | 当天日线（含夜盘 21:00-23:00）| 2 小时 |
| 上午盘 | 10:30 | 当天日线（含 10:39 数据）| ~3.5 小时 |
| 下午盘 | 14:00 | 当天日线（含 14:00 数据）| 1 小时 |

**结论**：所有日内评估点都存在前视偏差，必须修复。

### 4.3 隐患 3：RevIN 均值回归偏置（未验证）

TimesFM 内置 RevIN（可逆实例归一化），在 480-bar 长窗口上可能产生均值回归引力，导致趋势预测偏保守。

**状态**：需要实证验证。

---

## 五、修复方案

### 5.1 第一阶段：修复前视偏差（必须立即执行）

**修改**：`data/data_store.py:BacktestDataStore.get_main_continuous`

```python
# 当前（错误）
def get_main_continuous(self, limit=None, **kwargs):
    """日线数据: 截断到 cutoff 日历日 (含当日日线 bar)"""
    return super().get_main_continuous(
        end_date=self.cutoff_day, limit=limit
    )

# 修复后（正确）
def get_main_continuous(self, limit=None, **kwargs):
    """日线数据: 截断到 cutoff 日历日的前一交易日 (防止日内前视)"""
    from datetime import timedelta
    prev_day = (pd.Timestamp(self.cutoff_day) - timedelta(days=1)).strftime('%Y-%m-%d')
    return super().get_main_continuous(
        end_date=prev_day, limit=limit  # ← 改为前一天！
    )
```

**验证**：
- cutoff = `2026-09-08 10:30:00`
- 查询日线：`end_date='2026-09-07'`（前一天）
- 返回日线 bar 2026-09-07，close=5773.0（已收盘，无前瞻）

### 5.2 第二阶段：STEP=2 + 200 交易日窗口

**修改 1**：`config/backtest_config.py`

```python
# 当前
STEP = 24

# 修改为
STEP = 2  # 每天评估 3 次（5.5 bars/day ÷ 3 ≈ 2）
EVAL_WINDOW_BARS = 1200  # 评估窗口：600 点 × STEP=2
```

**修改 2**：`scripts/monthly_backtest.py:215`

```python
# 当前
eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))

# 修改为
eval_start = max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)
eval_indices = list(range(eval_start, total - HORIZON + 1, STEP))
```

### 5.3 第三阶段：实证验证（可选）

1. TimesFM 周期性先验测试
2. RevIN 消融实验
3. Block Bootstrap 统计修正

---

## 六、方案对比

| 方案 | 步长 | 评估点数 | 时间跨度 | 评估频率 | 前视偏差 | 耗时 |
|------|------|---------|---------|---------|---------|------|
| 调研当时（2026-09-09） | STEP=24 | 396 | 7-8 年 | 每周 1-2 次 | **当时存在** | 2.1h |
| 第一次修订（未落地） | STEP=16 | 594 | 7-8 年 | 每 3 天 1 次 | 当时存在 | 3.1h |
| 第二次修订（`ee1f176` 已落地） | STEP=2 | 理论 589（文档当时写 600） | ~200 交易日 | 每天约 3 次 | 回测无条件含当日已修；实盘 predict 仍裸读 | — |

> 上表「调研当时」不是 2026-09-11 的现行配置。现行：`config/backtest_config.py` `STEP=2`。

---

## 七、已完成的工作

### 7.1 代码修改

- ✅ `evaluator.py` aligned 范围：`(350, 500)` → `(350, 600)`
- ✅ `supervisor.py` 默认值：`400` → `600`
- ✅ 提交：`feedf44`

### 7.2 问题诊断

- ✅ 定位了 STEP=24 的采样瓶颈
- ✅ 理解了国内期货交易时间机制
- ✅ 确认了前视偏差的存在
- ✅ 提出了 STEP=2 + 200 交易日的方案

### 7.3 当时待办（2026-09-11：回测项已落地，勿再施工）

- ~~修复前视偏差（`BacktestDataStore.get_main_continuous`）~~ → `ee1f176`：`hour>=15` 才含当日
- ~~修改 STEP=24 → STEP=2~~ → 已是 2
- ~~新增 EVAL_WINDOW_BARS=1200~~ → 已落地
- ~~修改评估窗口截断逻辑~~ → 已落地
- 重新运行慢环评估：可选；磁盘仍混有 n=396 旧行。实盘 `DailyModel.predict` 裸读是另一条债（CC-1），不在本表回测项里。

---

## 八、关键文件清单

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `task_FM/evaluations/fm_eval/evaluator.py` | aligned 范围 500→600 | ✅ 已完成 |
| `scripts/praxist_supervisor.py` | 默认值 400→600 | ✅ 已完成 |
| `data/data_store.py` | 修复前视偏差 | ⏳ 待执行 |
| `config/backtest_config.py` | STEP=2, EVAL_WINDOW_BARS=1200 | ⏳ 待执行 |
| `scripts/monthly_backtest.py` | 评估窗口截断 | ⏳ 待执行 |

---

## 九、参考文献

- TimesFM 2.5 论文：https://arxiv.org/abs/2409.11155
- 国内期货交易时间：https://www.gfqh.com.cn/
- Block Bootstrap：Politis & White (2004), "Two Step Plugin Estimators for Time Series"
- Newey-West HAC：Newey & West (1987), "A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix"

---

## 十、结论

本研究从表面的配置问题出发，逐步深入到交易机制和模型架构的深层问题，最终发现了**前视偏差**这一致命缺陷。

**核心教训**：
1. 量化系统的每个细节都需要从交易实质的角度审视
2. 国内期货的交易时间机制与连续市场截然不同
3. 级联架构中的时间对齐问题极易被忽视

**下一步**：
1. 立即修复前视偏差
2. 执行 STEP=2 + 200 交易日方案
3. 重新评估所有变体，获取真实可靠的评估结果

---

**文档版本**：v1.0  
**最后更新**：2026-09-09  
**作者**：Claude Code
