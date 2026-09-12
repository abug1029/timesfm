# FM_a 系统设计文档：从预测到方向性建议

> **合同声明（冲突以后者为准）**
>
> - 可交易方向以 [`docs/product_positioning.md`](product_positioning.md) **CF-01 A** 为准。
> - IC / 硬门以 [`loop-constraints.md`](../loop-constraints.md) 为准。
> - 本文若与上述冲突，以上述为准。不要按本文去改 `signal_contract.py` 或 `evaluator.gate`。
>
> **版本**: 1.2 (2026-09-12)
> **定位**: 方向性建议，不是自动开平仓。描述 TimesFM 两阶段级联如何在任意时刻给出期货品种的方向与置信度。

---

## 目录

1. [系统概览](#1-系统概览)
2. [数据管线](#2-数据管线)
3. [两阶段级联预测](#3-两阶段级联预测)
4. [协变量系统](#4-协变量系统)
5. [信号生成与方向判断](#5-信号生成与方向判断)
6. [风险管理：波动率熔断](#6-风险管理波动率熔断)
7. [评估指标与门禁](#7-评估指标与门禁)
8. [交易建议生成](#8-交易建议生成)
9. [完整流程示例](#9-完整流程示例)
10. [附录：关键配置](#10-附录关键配置)

---

## 1. 系统概览

### 1.1 核心定位

FM_a 是一个**两阶段级联预测系统**，不是自动交易系统。它输出的是**方向性建议和置信度**，最终交易决策由人类交易员做出。

```
┌─────────────────────────────────────────────────────────────┐
│                    FM_a 系统架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  数据层          预测层              决策层          输出层    │
│  ─────          ─────              ─────          ─────     │
│                                                             │
│  TqSdk ──→ SQLite ──→ 日线模型 ──→ 1H级联 ──→ 方向判断     │
│  (实时)     (SQLite)   (TimesFM)   (XReg)    (见下)        │
│              │                        │            │        │
│              ↓                        ↓            ↓        │
│         技术指标               协变量矩阵      风控熔断      │
│         (RSI/OI等)             (品种特异)     (Vol Gating)  │
│              │                        │            │        │
│              └────────────────────────┴────────────┘        │
│                               │                             │
│                               ↓                             │
│                        方向性建议报告                        │
│                    (方向+置信度+风险提示)                     │
│                                                             │
│  可交易方向（CF-01 A；级联/回测/Copilot 已对齐）：            │
│  · 加权 1H（position_from_forecast / copilot_trade_signal）  │
│  · 日线斜率只填 regime_direction（副标签）                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心原则

| 原则 | 说明 |
|------|------|
| **领航员而非自动驾驶** | 系统输出方向性建议，人类做最终决策 |
| **预测永不压平（默认）** | Vol Gating 默认 OFF，仅输出风险标签 |
| **品种异质化** | 每个品种有独立的协变量配置和信用星级 |
| **防穿越** | 回测按 cutoff 截断；实盘 `DailyModel.predict` 经 `read_daily_frame` 走 `get_safe_daily`（见 §2.4） |
| **可复现** | 相同输入产生相同输出，所有随机种子固定 |

### 1.3 当前接线（2026-09-12；C1 / C3 已落地）

| 路径 | 现在怎样 | 不要写成 |
|------|----------|----------|
| `cascade_predict` / `monthly_backtest` | 可交易方向 = `position_from_forecast`（加权 1H） | 日线斜率主方向 |
| Copilot 卡面 / 研报 / 建议文案 | `copilot_trade_signal` → `position_from_forecast`（加权 1H）；日线只填 `regime_direction` | 卡面仍用日线 `_compute_direction_v2` 当主方向 |
| `DailyModel.predict` | 活 store 走 `read_daily_frame` → `get_safe_daily`；`BacktestDataStore` 仍 `get_main_continuous` | 实盘仍裸读 `get_main_continuous` |
| `get_safe_daily` | 接到活 `DailyModel.predict`（收盘掩码） | 只接到 cascade 报告图 |
| 仓内函数名 | 日线副标签活函数仍是 `_compute_direction_v2` | 不存在 `_compute_direction` |

C9–C12（ALIGN 合约、SPEC-011 复权、权重路径、rsi_state 分名）本轮未做，不要写成已落地。

---

## 2. 数据管线

### 2.1 数据流

```
TqSdk API
    │
    ├── 日线数据 (每日收盘后)
    │   └── main_continuous_1d 表
    │       └── 主力连续合约收盘价 (250 天 context)
    │
    └── 1H 数据 (盘中实时)
        └── kline_1h 表
            └── 主力连续 1H K线 (480 bars context)
                    │
                    ↓
            技术指标计算
            (RSI, OI, ATR, HA, ...)
                    │
                    ↓
            SQLite 存储
            (db/futures_<symbol>.db)
```

### 2.2 数据时效性

| 时间 | 1H 最大滞后 | 日线最大滞后 | 说明 |
|------|-------------|--------------|------|
| 周一 | 3 天 | 5 天 | 周五数据 |
| 周二 | 4 天 | 6 天 | 周五数据 |
| 周三 | 3 天 | 5 天 | 覆盖长周末 |
| 周四~五 | 1 天 | 3 天 | 正常交易日 |
| 周末 | 2~3 天 | 4 天 | — |

**自动补采**：预测前调用 `ensure_fresh_data()`，数据过期时自动从 TqSdk 补采。

### 2.3 关键数据表

| 表名 | 内容 | 用途 |
|------|------|------|
| `main_continuous_1d` | 主力连续日线 | Stage 1 日线预测 |
| `kline_1h` | 主力连续 1H | Stage 2 1H 预测 + 协变量计算 |
| `xreg_factors` | 协变量时间序列 | CCL/OI/RSI 等 |
| `metadata` | 数据版本/采集时间 | 审计追踪 |

**换月后复权（C10）**：日线与 1H 活读取都未做截面后复权。`get_main_continuous` 见 `raw_close` 列即跳过（生产 schema 恒有此列）；`get_klines_1h` 从不复权。列保留，不要当已复权。

### 2.4 防穿越：回测 hour>=15；实盘 predict 走 get_safe_daily

**回测**（`BacktestDataStore.get_main_continuous`）：cutoff 为 bar 时刻。`hour>=15` 才包含当日日线（当天已收盘）；15:00 之前回退到前一日历日。

**实盘**（C1，HEAD 已接线）：

- `DailyModel.predict` 经 `read_daily_frame`：无 `cutoff_date` 的活 store 调 `get_safe_daily`；有 `cutoff_date` 的 `BacktestDataStore` 仍 `get_main_continuous`。
- `get_safe_daily` 收盘掩码：`date==today` 且 `hour>=15` 才留当日；`date>today` 剔除。
- Copilot 同样走 `DailyModel.predict`，盘中日线 context 与这条活路径同构。

不要把「回测 cutoff」写成「活预测仍裸读」。

---

## 3. 两阶段级联预测

### 3.1 Stage 1：日线模型

**目标**：预测未来 22 个交易日的价格走势，提取趋势斜率，作为 **regime 副标签**（不是可交易方向）。

```
输入: 250 天历史收盘价
    │
    ↓
TimesFM 2.5 (200M 参数)
    │
    ├── 点预测: forecast[t], t=1..22
    └── 分位数预测: quantile[t, q], q=P10..P90
    │
    ↓
线性回归拟合斜率
    │
    ↓
horizon_slope = 回归系数 / 预测均值   # 存储：分数/天
展示: horizon_slope × 100 = %/天
R² < 0.35 → slope_unreliable（副标签改中性）
```

**输出**：`DailyResult`

```python
@dataclass
class DailyResult:
    symbol: str
    forecast: np.ndarray           # shape (22,), 22日预测价格
    horizon_slope: float           # 存储为分数/天（0.0015 = 0.15%/天）
    historical_closes: np.ndarray  # 历史真实日线收盘价
    historical_dates: pd.DatetimeIndex
    quantile_forecast: np.ndarray  # shape (22, 10), P10~P90
    r_squared: float = 0.0
    slope_unreliable: bool = False  # R² < 0.35
```

**斜率解读（仅日线状态 / regime，不是仓位）**：

```
展示斜率 = horizon_slope × 100
展示斜率 > +0.1%/天 且 R² 可靠  → 日线状态：看多 ↑
展示斜率 < -0.1%/天 且 R² 可靠  → 日线状态：看空 ↓
|展示斜率| <= 0.1% 或 slope_unreliable → 日线状态：中性 →
```

实现：`cascade/daily_model.py` 的 `_compute_direction_v2`。仓内没有名为 `_compute_direction` 的函数。

### 3.2 Stage 2：1H 级联模型 (XReg)

**目标**：以日线斜率为条件，结合品种特异协变量，进行 24 小时精细预测。可交易方向从这条 1H 路径出（级联 / 回测 / Copilot）。

```
输入:
    ├── 480 bars 1H 历史价格 (context)
    ├── daily_slope (来自 Stage 1)
    └── 协变量 (品种特异配置)
    │
    ↓
TimesFM 2.5 XReg (forecast_with_covariates)
    │
    ├── 点预测: point_forecast[t], t=1..24
    └── 分位数预测: quantile_forecast[t, q]
    │
    ↓
信号生成: position_from_forecast（加权 1H）
```

**XReg 协变量矩阵构建**：
```python
# 以 SS (不锈钢) 生产 SCHEMES 为例（不是慢环 ss_vor）
covariate_types = ["calendar_cyclical"]

# 构建矩阵
context段: 真实历史协变量值 (480 bars)
horizon段: 预测协变量值 (24 bars)

# 拼接
X = concat(context_covariates, horizon_covariates)  # shape (504, n_covariates)
```

**输出**：`HourlyResult`
```python
@dataclass
class HourlyResult:
    symbol: str
    point_forecast: np.ndarray       # shape (24,), 24H 预测价格
    quantile_forecast: np.ndarray    # shape (24, 10), P10~P90
    covariates: dict                 # {"daily_slope": ..., "ccl_pct": ...}
    context_len: int
    horizon: int
    xreg_fallback: bool              # 协变量失败回退标记
```

### 3.3 为什么需要两阶段？

| 阶段 | 时间尺度 | 捕捉信息 | 作用 |
|------|----------|----------|------|
| Stage 1 (日线) | 22 天 | 中长期趋势 | **regime 副标签**，不是可交易方向 |
| Stage 2 (1H) | 24 小时 | 短期波动 + 协变量 | 级联/回测的**可交易方向**（加权 1H） |

**级联优势**：
- 日线模型不受 1H 噪声干扰，给盘面一个趋势体制提示
- 1H 模型以日线斜率为 XReg 条件，不把日线阈值写成仓位
- 协变量在 1H 尺度更有预测力（日内持仓变化 vs 日间）

CF-01 A：日线斜率**不得覆盖** `position_sign`。Copilot 卡面目前仍把日线副标签当主方向，见 §5.3。

---

## 4. 协变量系统

### 4.1 协变量家族

| 家族 | 协变量 | 经济含义 | 适用场景 |
|------|--------|----------|----------|
| **calendar** | `calendar_cyclical` | 交割月/季节性周期 | 农产品、交割敏感品种 |
| **oscillator** | `rsi_state`, `rsi6/12/24`, `qstick` | 超买超卖/买卖压力 | 均值回归品种 |
| **positioning** | `ccl`, `oi` | 主力资金流向 | 趋势确认 |
| **price_action** | `ha_body`, `reversal_shadow` | K线形态/反转信号 | 趋势延续/反转 |
| **trend** | `hourly_slope`, `ao_accel` | 短期动能 | 趋势品种 |
| **volatility** | `vor`, `bb_squeeze`, `stddev` | 波动率状态 | 突破/压缩 |

### 4.2 品种特异配置（生产 SCHEMES）

每个品种有独立的协变量配置，存储在 `config/prediction_scheme.py` 的 `SCHEMES` 字典中。**生产入口读这里，不读慢环 verdict。**

```python
# 不锈钢 (SS) — 生产固化，不是 ss_vor
"ss": VarietyScheme(
    symbol="ss",
    name="不锈钢",
    scheme_type="trend",
    stars=2,
    covariate_type="calendar_cyclical",
    covariate_types=["calendar_cyclical"],
)

# 白糖 (SR)
"sr": VarietyScheme(
    symbol="sr",
    name="白糖",
    scheme_type="stable",
    stars=2,
    covariate_type="rsi_state",
    covariate_types=["rsi_state", "oi", "calendar_cyclical"],
)
```

SS 生产协变量是 `calendar_cyclical`。慢环过门的 `ss_vor` **没有**写进 `SCHEMES`。

### 4.3 慢环验证 vs 固化：拆开写

协变量候选通过**慢环验证**（`aligned_slow_loop.py`）写 `aligned_verdicts.jsonl`。过门 ≠ 已固化。

```
慢环验证流程:
    │
    ├── 1. Peer 提出假设 (symbol × covariate) → proposals/*.json
    │
    ├── 2. 慢环回测验证
    │   ├── 计算 PF / EV / DirAcc；IC = 2×|dir_acc−0.5|
    │   ├── gate_pass = n≥350 且 IC≥0.05   （不含 EV）
    │   └── econ_pass = gate_pass and ev>0  （pass_variants()）
    │
    └── 3. 固化到 SCHEMES：须人工，慢环不过这一步
```

**磁盘裁决（2026-09-11）**：

| variant | n | PF | EV | IC | gate_pass | econ_pass | 是否进 SCHEMES |
|---------|---|----|----|----|-----------|-----------|----------------|
| `ss_vor` | 396 | 1.123 | +11.06 | 0.06 | True | **True** | **否**（生产仍是 `calendar_cyclical`） |
| `i_oi` | 396 | 0.818 | −2.46 | 0.066 | True | False | 否 |
| `m_ccl` | 396 | 0.839 | −3.64 | 0.088 | True | False | 否 |
| `cj_oi` | 324 | 1.133 | +19.46 | 0.08 | False（欠样本） | False | 否 |

`gate_pass=True` 不是「赚钱、已解决」。`i_oi` / `m_ccl` 过硬门但 EV 为负。

### 4.4 协变量构建细节

以 `calendar_cyclical` 为例：
```python
def build_calendar_cyclical(df: pd.DataFrame) -> np.ndarray:
    """
    日历周期协变量：捕捉交割月效应

    原理：期货价格在交割月前后可预期地收敛
    计算：month_of_year → sin/cos 变换 → 周期信号
    """
    dates = pd.to_datetime(df['dt'])
    month = dates.dt.month
    # 周期编码
    cal = np.sin(2 * np.pi * month / 12)
    return cal
```

以 `rsi_state` 为例：
```python
def _calc_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    RSI 超买超卖体制

    原理：RSI>70 超买(看空), RSI<30 超卖(看多)
    输出：RSI 值 (0~100)，归一化到 [-1, 1]
    """
    # ... RSI 计算 ...
    return (rsi - 50) / 50  # 归一化
```

---

## 5. 信号生成与方向判断

### 5.1 可交易方向：加权 1H（级联 / 回测 / Copilot）

CF-01 A：**唯一可交易方向** = `sign(weighted_1H − base)`，经 `signal_weight` / `short_horizon`。实现：`cascade/signal_contract.position_from_forecast`。

`cascade_predict`、`monthly_backtest` 与 Copilot 卡面（`copilot_trade_signal`）走这条。日线斜率只填 `regime_direction`，**不得覆盖** `position_sign`。

```python
from cascade.signal_contract import position_from_forecast

sig = position_from_forecast(
    point_forecast,   # 1H 点预测，shape (horizon,)
    base_price,       # T0 收盘
    scheme=scheme,
    daily_slope=daily_result.horizon_slope,  # 分数/天；只填副标签
)
# sig["direction"]        → 可交易方向（加权 1H）
# sig["regime_direction"] → 日线状态（副标签）
# sig["position_sign"]    → +1 / -1 / 0
```

无 scheme 时回退到终点符号 `sign(pred[-1] − base)`（遗留路径）。

### 5.2 日线副标签：`_compute_direction_v2`

活函数在 `cascade/daily_model.py`。仓内**没有** `_compute_direction`。

```python
def _compute_direction_v2(daily_result, scheme) -> str:
    """R² 门控的日线状态（副标签，不是仓位）。"""
    if getattr(daily_result, "slope_unreliable", False):
        return "中性 → (形态分歧)"
    if scheme:
        thr_ratio = scheme.trend_threshold_pct / 100.0  # 0.1%/天 → 0.001
    else:
        thr_ratio = 0.001
    slope = daily_result.horizon_slope  # 分数/天
    if slope > thr_ratio:
        return "看多 ↑"
    elif slope < -thr_ratio:
        return "看空 ↓"
    else:
        return "中性 →"
```

**单位**：`horizon_slope` 存储为分数/天；展示乘 100 才是 %/天。阈值比较在分数空间（`thr_ratio`），不要把存储值直接当百分比。

### 5.3 Copilot 卡面：可交易方向 = 加权 1H（C3）

`scripts/copilot.py::run_one` 调 `copilot_trade_signal` → `position_from_forecast`。卡面「可交易方向」、建议文案、研报主句、止损跟加权 1H。日线斜率只填 `regime_direction`（「日线状态」）。

| 入口 | 主方向 | 日线角色 |
|------|--------|----------|
| `scripts/cascade_predict.py` | `position_from_forecast` | `regime_direction` 副标签（`_compute_direction_v2`） |
| `scripts/monthly_backtest.py` | `position_from_forecast` | 不覆盖仓位 |
| `scripts/copilot.py` | `position_from_forecast`（经 `copilot_trade_signal`） | `regime_direction` 副标签 |

### 5.4 信号权重衰减

不同品种的信号有效时长不同，通过 `decay` 参数控制（`config/prediction_scheme.py::signal_weight`）：

```python
def signal_weight(horizon: int, scheme: VarietyScheme) -> np.ndarray:
    """
    生成信号权重（远端信号衰减）

    trend 品种：衰减慢 (decay=1.35)，信号持续性强
    stable 品种：衰减快 (decay=1.60)，短期有效
    """
    if scheme.use_full_signal and not scheme.short_horizon_only:
        decay = scheme.decay
        t = np.arange(1, horizon + 1)
        w = decay ** (-t / horizon)
        return w
    else:
        # 短段信号：前半段权重 1，其余 0（另有 cosine rolloff，默认关）
        w = np.zeros(horizon)
        half = min(horizon // 2, 12)
        w[:half] = 1.0
        return w
```

**衰减曲线示例**（24H，decay=1.35）：
```
T+1:  0.97  ████████████████████████████████████████
T+6:  0.88  ███████████████████████████████████
T+12: 0.79  █████████████████████████████████
T+18: 0.71  ██████████████████████████████
T+24: 0.64  ████████████████████████████
```

### 5.5 置信区间调整

实现见 `config/prediction_scheme.py::confidence_band`：Col 0 是点预测，不展宽；Col 1~9 在 log 空间按 `confidence_multiplier` 展宽。`multiplier > 1.0` 更保守。

---

## 6. 风险管理：波动率熔断

### 6.1 Vol Gating 定位

**默认 OFF**。启用时，预测未来 24H 高波动则 veto → Neutral Override（压平预测/空仓）。

```python
# 启用方式
python scripts/cascade_predict.py ss --vol-filter-neutral
# 或
export FM_VOL_FILTER=1
```

### 6.2 熔断流程

```
输入: 1H 历史数据 (2000 bars)
    │
    ↓
特征提取 (regime_features.py)
    ├── vol_skew: 波动率偏度
    ├── rolling_hurst: 滚动 Hurst 指数
    ├── rolling_adx: 滚动 ADX 趋势强度
    └── vol_cone_position: 波动率锥位置
    │
    ↓
RandomForest 分类器
    │
    ↓
vol_prob = P(高波动)
    │
    ↓
阈值判断
    ├── vol_prob >= threshold → veto=True → 熔断
    └── vol_prob <  threshold → veto=False → 正常
```

### 6.3 阈值决议优先级

```python
@dataclass
class ThrPolicy:
    global_cli: float | None      # 1. --thr 命令行参数
    sector_cli: dict              # 2. --thr-chem 板块参数
    operational_map: dict         # 3. models/operational_thr.json
    operational_thr_pkl: float    # 4. pkl 内写入的操作阈值
    calibrated_thr: float         # 5. IS 分位（元数据）
    default: float = 0.55         # 6. 默认值
```

### 6.4 熔断动作

| 动作 | 说明 | 使用场景 |
|------|------|----------|
| `neutral` | 预测压平 → 空仓 | **推荐**，保守策略 |
| `slope_only` | 仅保留日线斜率，剥离第二协变量 | 旧版本，不推荐 |

```python
def apply_neutral_override(point_forecast, base_price, quantile_forecast):
    """v1: 压平预测 → delta_pred=0 → 空仓建议 (CI 全部归零)"""
    horizon = len(point_forecast)
    flat = np.full(horizon, base_price)
    q_flat = np.full_like(quantile_forecast, base_price)
    return flat, q_flat

def apply_neutral_override_v2(point_forecast, base_price, quantile_forecast,
                               atr, tick_size=1.0, vol_penalty_mult=1.5):
    """v2 (2026-09-10): 点预测归零 + 分位数波动率扩散 (布朗运动)

    CI 不再归零，而是按 ATR 扩散:
      q_override[t, q_idx] = base_price + z_q * sigma_1 * sqrt(t) * penalty
    10 列 z-score 表: [0, -1.28, -0.84, -0.52, -0.25, 0, +0.25, +0.52, +0.84, +1.28]
    旧函数保留向后兼容，生产路径 (cascade_predict.py) 已切换至 v2。"""
```

---

## 7. 评估指标与门禁

### 7.1 核心指标

| 指标 | 公式 | 含义 | 硬门条件 |
|------|------|------|----------|
| **PF** | sum(盈利) / sum(亏损) | 盈亏比 | > 1.0（经济层 / 星级，不是 `gate_pass`） |
| **EV** | mean(净盈亏) | 每笔期望收益（扣滑点） | `econ_pass` 要求 > 0；**不进** `gate_pass` |
| **IC** | `2×\|dir_acc−0.5\|` | 方向性信息系数（**不是** Pearson） | ≥ 0.05 |
| **n** | 样本量 | 统计显著性 | ≥ 350 |
| **MaxDD** | 最大回撤 | 风险控制 | > -40% (建议) |

`cascade/evaluation_metrics.py` 只产出 DirAcc / PF / EV / MaxDD。IC 由 `task_FM/evaluations/fm_eval/evaluator.py::gate` 从 DirAcc 派生。不要把 IC 写成 `corr(预测, 实际)`。

### 7.2 计算细节

#### PF (Profit Factor)

```python
# 净盈亏（扣滑点）
slippage = tick_size * SLIPPAGE_TICKS  # 如 RB: 1.0 * 2 = 2 点
net = (pred_direction * actual_return) - slippage

# 分组
pos_trades = net[net > 0]  # 盈利交易
neg_trades = net[net < 0]  # 亏损交易

gross_profit = sum(pos_trades)
gross_loss = abs(sum(neg_trades))

PF = gross_profit / gross_loss
```

#### EV (Expected Value)

```python
EV = mean(net)  # 所有交易净盈亏的平均值
# 单位：价格点（如 RB: +0.5 点 = 0.5 元/吨）
```

#### IC（方向性，非相关）

```python
ic = 2 * abs(dir_acc - 0.5)
# DirAcc=0.53 → IC=0.06；DirAcc=0.467 → IC=0.066
```

#### MaxDD (Maximum Drawdown)

```python
# 收益率
r_t = net / base_price

# 资金曲线（复利）
equity[0] = 1.0
equity[t] = equity[t-1] * (1 + r_t)

# 历史峰值
peak[t] = max(equity[0:t+1])

# 回撤
drawdown[t] = (equity[t] - peak[t]) / peak[t]

MaxDD = min(drawdown)  # 最大回撤（负值）
```

### 7.3 硬门逻辑

`gate_pass` **只判 n 和 IC**，不含 EV。经济过门是另一层。

```python
# task_FM/evaluations/fm_eval/evaluator.py
def gate(s, min_n=350, min_ic=0.05):
    """预注册硬门: n 与方向性 IC(=2*|DirAcc-0.5|)"""
    m = s if "dir_acc" in s else map_summary(s)
    ic = 2 * abs(m.get("dir_acc", 0.5) - 0.5)
    return m["n"] >= min_n and ic >= min_ic

# scripts/registry_lib.py
# econ_pass = gate_pass and ev>0
def pass_variants(snapshot):
    out = []
    for v in snapshot.values():
        if v.get("status", "ok") != "ok":
            continue
        if v.get("gate_pass") and v.get("ev", 0) > 0:
            out.append(v)
    return out
```

磁盘：`ss_vor` 经济过门（ev=+11.06）。`i_oi`（ev=−2.46）与 `m_ccl`（ev=−3.64）`gate_pass=True` 但 EV 为负，**不算** `pass_variants()`。

### 7.4 信用星级

| 星级 | 标准 | 品种数 | 建议仓位 |
|------|------|--------|----------|
| ⭐⭐⭐ | 无（系统未达 3 星标准） | 0 | — |
| ⭐⭐ | PF > 1.05 + 多维度 GREEN | 8 | 中等仓位 |
| ⭐ | PF ~ 1.0 或 underpowered | 13 | 轻仓或观望 |

**2 星品种**（SCHEMES，2026-09-10）：SS, SR, M, RB, EG, LH, CJ, JD

---

## 8. 交易建议生成

### 8.1 建议框架

级联报告（`cascade_predict`）按 CF-01 A 拆两行。Copilot 卡面同样：【可交易方向】加权 1H，【日线状态】副标签。

```
┌─────────────────────────────────────────────────────────────┐
│                    方向性建议报告                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  品种: SS (不锈钢)                                          │
│  星级: ⭐⭐ (2星，中等信用)                                  │
│  时间: 2026-09-11 14:30                                     │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                             │
│  【可交易方向】看多 ↑   （加权 1H，position_from_forecast）  │
│  【日线状态】看多 ↑     （斜率 +0.15%/天，副标签）            │
│  1H 预测: T+1~T+12 均价 14520, T+13~T+24 均价 14580        │
│                                                             │
│  注：Copilot 卡面「可交易方向」同样走加权 1H。                │
│      日线只印「日线状态」，不覆盖仓位。                        │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                             │
│  【模型底气】                                               │
│  历史胜率: 51% | 盈亏比(PF): 1.12 | 回测 MaxDD: -35%       │
│  生产协变量: calendar_cyclical（不是慢环 ss_vor）            │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                             │
│  【信号强度】                                               │
│  T+1~T+12: 强 (权重 0.97~0.88)                             │
│  T+13~T+24: 中 (权重 0.79~0.64)                            │
│  建议持仓周期: T+1 ~ T+12 (短期)                            │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                             │
│  【风险提示】                                               │
│  Vol 雷达: 正常 (Vol_Prob: 0.32 < 0.55)                    │
│  置信区间: P10=14380, P90=14660 (宽度 280 点)              │
│  波动率: 中等 (ATR_14: 120 点)                              │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                             │
│  【领航员建议】                                             │
│  ● 可交易方向看多，但胜率仅 51%，建议轻仓试探               │
│  ● 短期信号强于长期，建议 T+12 前平仓                       │
│  ● 止损参考 (多头防线): P10≈14380, 建议止损位 14370        │
│  ● 止盈参考: P90=14660 (触及则减仓)                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 建议生成逻辑

实现见 `scripts/copilot.py::craft_advisory`。`run_one` 传入的 `direction` 来自 `copilot_trade_signal` / `position_from_forecast`（加权 1H）。日线只进 `regime_direction`。文案按星级、历史 PF/DirAcc、Vol 雷达标签拼接；高波分支读 `vol_sensitivity`（HELPS / HURTS / MIXED）。级联报告不走这条，信号表直接印加权 1H 的「可交易方向」。

### 8.3 建议等级

| 等级 | 条件 | 建议动作 |
|------|------|----------|
| **强建议** | 2 星 + PF>1.1 + 方向明确 | 中等仓位开仓 |
| **弱建议** | 1 星 或 PF~1.0 | 轻仓试探或观望 |
| **不建议** | 中性方向 或 Vol 熔断 | 空仓等待 |

---

## 9. 完整流程示例

活仓：`/home/abug/timesfm`。虚拟环境：`.praxist-venv`。不要用 `D:/FlyBuddy/FM_a`。

### 9.1 场景：2026-09-11 14:30，预测 SS (不锈钢)

**Step 1: 数据检查**
```bash
python scripts/cascade_predict.py ss --collect-if-stale 1
# 输出: [DATA] SS 1H 数据时效: 2h, 日线时效: 1d → OK
```

**Step 2: Stage 1 日线预测**（活路径 `read_daily_frame` → `get_safe_daily`）
```
[Stage 1] 日线预测 (context=250d, horizon=22d)...
  历史窗口: 250 天
  预测天数: 22 天
  预测范围: 14320.5 ~ 14680.2
  Horizon 斜率: +0.153%/天     # 存储分数/天，展示 ×100
  日线状态: 看多 ↑             # _compute_direction_v2，副标签
```

**Step 3: Stage 2 1H 级联预测**
```
[Stage 2] 1H 级联预测 (XReg, horizon=24h, cov=calendar_cyclical)...
  Context: 480 bars (20 天)
  Horizon: 24 bars (1 天)
  协变量: calendar_cyclical（生产 SCHEMES；不是 ss_vor）

  预测结果:
    T+1~T+12 均价: 14520
    T+13~T+24 均价: 14580
    分位数: P10=14380, P50=14550, P90=14660
  可交易方向: 看多 ↑           # position_from_forecast
```

**Step 4: 风险评估**
```
[Vol Gating] OFF (default static scheme)
  (若启用: Vol_Prob=0.32 < 0.55 → 正常)
```

**Step 5: 生成报告**
```markdown
# SS (不锈钢) 级联预测报告

## 可交易方向: 看多 ↑
## 日线状态: 看多 ↑

| 指标 | 值 |
|------|-----|
| 日线斜率 | +0.153%/天（副标签） |
| 1H 预测 (T+1~12) | 14520 |
| 1H 预测 (T+13~24) | 14580 |
| 置信区间 P10~P90 | 14380 ~ 14660 |

## 模型信用: ⭐⭐ (2星)

| 指标 | 值 |
|------|-----|
| 历史胜率 | 51% |
| 盈亏比 PF | 1.12 |
| 回测 MaxDD | -35% |
| 生产协变量 | calendar_cyclical |

## 领航员建议

- 可交易方向看多，胜率 51%，建议轻仓试探
- 短期信号强于长期，建议 T+12 前平仓
- 止损参考: P10=14380
- 止盈参考: P90=14660
```

Copilot（`python scripts/copilot.py ss`）卡面目前仍只印日线方向，不会出现上面的「可交易方向」行。

### 9.2 命令行完整流程

```bash
# 1. 激活环境（WSL 活仓）
cd /home/abug/timesfm
source .praxist-venv/bin/activate

# 2. 单品种预测（自动补采数据）
python scripts/cascade_predict.py ss --collect-if-stale 1

# 3. 多品种预测
python scripts/cascade_predict.py ss rb sr m jd

# 4. 信用 2 星品种批量预测
python scripts/cascade_predict.py --three-star

# 5. 主观交易领航员（推荐盘中入口；卡面方向仍是日线 v2）
python scripts/copilot.py ss fu --no-refresh

# 6. 启用 Vol 熔断（实验性）
python scripts/cascade_predict.py ss --vol-filter-neutral
```

---

## 10. 附录：关键配置

### 10.1 品种配置速查表（生产 SCHEMES）

| 品种 | 星级 | 主协变量 | 组合 | 类型 | 衰减 | 信号策略 |
|------|------|----------|------|------|------|----------|
| SS | ⭐⭐ | calendar_cyclical | [calendar_cyclical] | trend | 1.30 | 全段 |
| SR | ⭐⭐ | rsi_state | [rsi_state, oi, calendar_cyclical] | stable | 1.43 | 全段 |
| M | ⭐⭐ | ha_body | [ha_body, calendar_cyclical] | stable | 1.37 | 全段 |
| RB | ⭐⭐ | rsi_state | [rsi_state] | stable | 1.27 | 全段 |
| EG | ⭐⭐ | calendar_cyclical | [calendar_cyclical] | stable | 1.27 | 全段 |
| LH | ⭐⭐ | rsi_state | [rsi_state] | stable | 1.46 | 全段 |
| CJ | ⭐⭐ | hourly_slope | [hourly_slope] | short_range | 1.47 | 短段 |
| JD | ⭐⭐ | rsi_state | [rsi_state] | stable | 1.42 | 全段 |

SS 行是 `calendar_cyclical`。`ss_vor` 只出现在慢环裁决，不在本表。

### 10.2 关键参数

| 参数 | 值 | 来源 | 说明 |
|------|-----|------|------|
| `CONTEXT_BARS` | 480 | backtest_config.py | 1H context 长度 |
| `CONTEXT_DAYS` | 250 | backtest_config.py | 日线 context 长度 |
| `HORIZON` | 24 | backtest_config.py | 1H 预测时域 |
| `HORIZON_DAYS` | 22 | backtest_config.py | 日线预测天数 |
| `STEP` | **2** | backtest_config.py | 评估步长（密集；不是 24） |
| `EVAL_WINDOW_BARS` | 1200 | backtest_config.py | 评估窗口 (~200 交易日) |
| 理论 n | **589** | `range(eval_start, total-HORIZON+1, STEP)` | 窗口足够时；磁盘最高 588 |
| `SLIPPAGE_TICKS` | 2 | backtest_config.py | 双边滑点 tick 数 |
| `TREND_THRESHOLD_PCT` | 0.1 | prediction_scheme.py | 日线副标签阈值（%/天） |

硬门样本量阈值仍是 350，不是 396 也不是 600。

### 10.3 文件路径

| 文件 | 用途 |
|------|------|
| `config/prediction_scheme.py` | 品种固化方案 SCHEMES |
| `config/backtest_config.py` | 回测参数配置 |
| `config/knowledge_base.json` | Copilot 信用背书 |
| `cascade/daily_model.py` | Stage 1 日线模型；`_compute_direction_v2` |
| `cascade/hourly_model.py` | Stage 2 1H 级联模型 |
| `cascade/signal_contract.py` | 可交易方向合同：`position_from_forecast` |
| `cascade/features.py` | 协变量构建 |
| `cascade/vol_risk_filter.py` | 波动率熔断器 |
| `cascade/evaluation_metrics.py` | DirAcc / PF / EV / MaxDD（无 Pearson IC） |
| `scripts/cascade_predict.py` | 级联预测主入口（加权 1H） |
| `scripts/monthly_backtest.py` | 慢环回测（加权 1H；`hour>=15` 含当日日线） |
| `scripts/copilot.py` | 主观交易领航员（卡面加权 1H；日线为 regime） |

---

## 总结

FM_a 系统的核心价值在于：

1. **两阶段级联**：日线给 regime 副标签，级联/回测/Copilot 的可交易方向来自加权 1H
2. **品种异质化**：每个品种有独立的生产 SCHEMES；慢环过门不会自动固化
3. **防穿越**：回测 `hour>=15`；实盘 `DailyModel.predict` 走 `get_safe_daily`
4. **风险管理**：Vol 熔断（可选）、置信区间、止损止盈参考
5. **人机协作**：系统输出方向性建议，人类做最终决策

**使用建议**：
- 优先关注 2 星品种（SS/SR/M/RB/EG/LH/CJ/JD）
- 看【可交易方向】（加权 1H）；【日线状态】只是副标签
- 轻仓试探，根据实际表现调整仓位
- 结合基本面和主观判断，不盲从模型

---

*文档维护：本文档随系统迭代更新，最新版本见 `docs/system_design.md`。冲突以 `product_positioning.md` 与 `loop-constraints.md` 为准。*
