# FM_a 系统设计文档：从预测到交易建议

> **版本**: 1.0 (2026-09-10)  
> **定位**: 完整描述如何利用 TimesFM 预测模型和协变量系统，在任意时间点给出期货品种的开平仓建议。

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
│  (实时)     (SQLite)   (TimesFM)   (XReg)    (斜率/阈值)   │
│              │                        │            │        │
│              ↓                        ↓            ↓        │
│         技术指标               协变量矩阵      风控熔断      │
│         (RSI/OI等)             (品种特异)     (Vol Gating)  │
│              │                        │            │        │
│              └────────────────────────┴────────────┘        │
│                               │                             │
│                               ↓                             │
│                        交易建议报告                          │
│                    (方向+置信度+风险提示)                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心原则

| 原则 | 说明 |
|------|------|
| **领航员而非自动驾驶** | 系统输出建议，人类做最终决策 |
| **预测永不压平（默认）** | Vol Gating 默认 OFF，仅输出风险标签 |
| **品种异质化** | 每个品种有独立的协变量配置和信用星级 |
| **防穿越** | 所有预测严格使用历史数据，不使用未来信息 |
| **可复现** | 相同输入产生相同输出，所有随机种子固定 |

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

---

## 3. 两阶段级联预测

### 3.1 Stage 1：日线模型

**目标**：预测未来 22 个交易日的价格走势，提取趋势斜率。

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
horizon_slope = 回归系数 / 预测均值  (%/天)
```

**输出**：`DailyResult`
```python
@dataclass
class DailyResult:
    symbol: str
    forecast: np.ndarray           # shape (22,), 22日预测价格
    horizon_slope: float           # 预测段的百分比斜率 (%/天)
    historical_closes: np.ndarray  # 历史真实日线收盘价
    historical_dates: pd.DatetimeIndex
    quantile_forecast: np.ndarray  # shape (22, 10), P10~P90
```

**斜率解读**：
```
horizon_slope > +0.1%/天  → 看多 ↑
horizon_slope < -0.1%/天  → 看空 ↓
|horizon_slope| <= 0.1%   → 中性 →
```

### 3.2 Stage 2：1H 级联模型 (XReg)

**目标**：以日线斜率为条件，结合品种特异协变量，进行 24 小时精细预测。

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
信号生成
```

**XReg 协变量矩阵构建**：
```python
# 以 SS (不锈钢) 为例
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
    xreg_fallback: bool              # 协变量失败回退标记
```

### 3.3 为什么需要两阶段？

| 阶段 | 时间尺度 | 捕捉信息 | 作用 |
|------|----------|----------|------|
| Stage 1 (日线) | 22 天 | 中长期趋势 | 确定大方向 |
| Stage 2 (1H) | 24 小时 | 短期波动 + 协变量 | 精细化入场时机 |

**级联优势**：
- 日线模型不受 1H 噪声干扰，趋势判断更稳
- 1H 模型以日线斜率为条件，避免与大势矛盾
- 协变量在 1H 尺度更有预测力（日内持仓变化 vs 日间）

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

### 4.2 品种特异配置

每个品种有独立的协变量配置，存储在 `config/prediction_scheme.py` 的 `SCHEMES` 字典中。

```python
# 示例：不锈钢 (SS)
"ss": VarietyScheme(
    symbol="ss",
    name="不锈钢",
    scheme_type="trend",
    stars=2,                              # 信用星级
    covariate_type="calendar_cyclical",   # 主协变量
    covariate_types=["calendar_cyclical"], # 组合协变量
    # ... 其他参数
)

# 示例：白糖 (SR)
"sr": VarietyScheme(
    symbol="sr",
    name="白糖",
    scheme_type="stable",
    stars=2,
    covariate_type="rsi_state",
    covariate_types=["rsi_state", "oi", "calendar_cyclical"],  # 三协变量组合
    # ...
)
```

### 4.3 协变量选择依据

协变量配置通过**慢环验证**（`aligned_slow_loop.py`）确定：

```
慢环验证流程:
    │
    ├── 1. Peer 提出假设 (symbol × covariate)
    │
    ├── 2. 慢环回测验证
    │   ├── 计算 PF / EV / IC / MaxDD
    │   └── 硬门判断: n≥350 + IC≥0.05 + EV>0
    │
    └── 3. 过门 → 固化到 SCHEMES
```

**当前过门协变量**（2026-09-10）：
| 品种 | 协变量 | PF | EV | IC | 状态 |
|------|--------|----|----|----|------|
| SS | vor | 1.123 | +11.06 | 0.060 | ✅ 实质性过门 |
| CJ | oi | 1.133 | +19.46 | 0.080 | ⏳ n 不足 (324<350) |
| M | vor | 1.303 | +8.71 | 0.048 | ⏳ IC 边际 (0.048<0.05) |

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

### 5.1 方向判断逻辑

```python
def _compute_direction(horizon_slope: float, scheme: VarietyScheme) -> str:
    """
    基于日线斜率判断方向
    
    Args:
        horizon_slope: 日线预测斜率 (%/天)
        scheme: 品种方案（含阈值配置）
    
    Returns:
        "看多 ↑" / "看空 ↓" / "中性 →"
    """
    thr = scheme.trend_threshold_pct  # 默认 0.1%/天
    
    if horizon_slope * 100 > thr:     # 转换为百分比
        return "看多 ↑"
    elif horizon_slope * 100 < -thr:
        return "看空 ↓"
    else:
        return "中性 →"
```

**阈值说明**：
- `trend_threshold_pct = 0.1` 表示斜率 > 0.1%/天才视为趋势
- 低于阈值视为震荡/中性，不建议开仓

### 5.2 信号权重衰减

不同品种的信号有效时长不同，通过 `decay` 参数控制：

```python
def signal_weight(horizon: int, scheme: VarietyScheme) -> np.ndarray:
    """
    生成信号权重（远端信号衰减）
    
    trend 品种：衰减慢 (decay=1.35)，信号持续性强
    stable 品种：衰减快 (decay=1.60)，短期有效
    """
    if scheme.use_full_signal and not scheme.short_horizon_only:
        # 全段信号：指数衰减
        decay = scheme.decay
        t = np.arange(1, horizon + 1)
        w = decay ** (-t / horizon)  # 权重 = decay^(-t/horizon)
        return w
    else:
        # 短段信号：T+1~T+12 权重 1，T+13~T+24 权重 0
        w = np.zeros(horizon)
        w[:12] = 1.0
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

### 5.3 置信区间调整

```python
def confidence_band(quantile_forecast: np.ndarray, scheme: VarietyScheme) -> np.ndarray:
    """
    根据品种的 confidence_multiplier 调整置信区间
    
    multiplier > 1.0 → 更保守（区间更宽）
    multiplier = 1.0 → 标准
    """
    mult = scheme.confidence_multiplier
    if mult == 1.0:
        return quantile_forecast
    
    median = quantile_forecast[:, 5:6]  # P50
    adjusted = quantile_forecast.copy()
    
    # 展宽低端和高端
    for q_idx in [1, 2, 3, 4]:  # P10~P40
        adjusted[:, q_idx] = median - (median - quantile_forecast[:, q_idx]) * mult
    for q_idx in [6, 7, 8, 9]:  # P60~P90
        adjusted[:, q_idx] = median + (quantile_forecast[:, q_idx] - median) * mult
    
    return adjusted
```

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
    """压平预测 → delta_pred=0 → 空仓建议"""
    horizon = len(point_forecast)
    flat = np.full(horizon, base_price)  # 所有预测 = 当前价格
    q_flat = np.full_like(quantile_forecast, base_price)
    return flat, q_flat
```

---

## 7. 评估指标与门禁

### 7.1 核心指标

| 指标 | 公式 | 含义 | 硬门条件 |
|------|------|------|----------|
| **PF** | sum(盈利) / sum(亏损) | 盈亏比 | > 1.0 |
| **EV** | mean(净盈亏) | 每笔期望收益（扣滑点） | > 0 |
| **IC** | corr(预测, 实际) | 信息系数 | ≥ 0.05 |
| **n** | 样本量 | 统计显著性 | ≥ 350 |
| **MaxDD** | 最大回撤 | 风险控制 | > -40% (建议) |

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

```python
def gate_pass(n: int, ic: float, ev: float) -> bool:
    """
    硬门判断：协变量是否可用于生产
    
    三个条件必须同时满足：
    1. n >= 350: 样本量足够（统计显著性）
    2. ic >= 0.05: 预测有信息量（不是噪声）
    3. ev > 0: 正期望（长期能赚钱）
    """
    return (n >= 350) and (ic >= 0.05) and (ev > 0)
```

### 7.4 信用星级

| 星级 | 标准 | 品种数 | 建议仓位 |
|------|------|--------|----------|
| ⭐⭐⭐ | 无（系统未达 3 星标准） | 0 | — |
| ⭐⭐ | PF > 1.05 + 多维度 GREEN | 8 | 中等仓位 |
| ⭐ | PF ~ 1.0 或 underpowered | 13 | 轻仓或观望 |

**2 星品种**（2026-09-10）：SS, SR, M, RB, EG, LH, CJ, JD

---

## 8. 交易建议生成

### 8.1 建议框架

```
┌─────────────────────────────────────────────────────────────┐
│                    交易建议报告                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  品种: SS (不锈钢)                                          │
│  星级: ⭐⭐ (2星，中等信用)                                  │
│  时间: 2026-09-10 14:30                                     │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                             │
│  【方向判断】看多 ↑                                         │
│  日线斜率: +0.15%/天 (阈值 0.1%)                            │
│  1H 预测: T+1~T+12 均价 14520, T+13~T+24 均价 14580        │
│                                                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                             │
│  【模型底气】                                               │
│  历史胜率: 51% | 盈亏比(PF): 1.12 | 回测 MaxDD: -35%       │
│  协变量: calendar_cyclical (日历周期效应)                   │
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
│  ● 方向看多，但胜率仅 51%，建议轻仓试探                     │
│  ● 短期信号强于长期，建议 T+12 前平仓                       │
│  ● 止损参考: P10=14380 (跌破则趋势失效)                    │
│  ● 止盈参考: P90=14660 (触及则减仓)                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 建议生成逻辑

```python
def craft_advisory(symbol, kb, direction, delta_pct, vol, scheme_type):
    """生成领航员建议（多行文案）"""
    entry = kb_entry(kb, symbol)
    stars = entry.get("credit_stars", 0)
    pf = entry.get("historical_pf")
    dir_acc = entry.get("historical_diracc")
    high_vol = vol.get("high_vol", False)
    
    lines = []
    
    # 1. 底气评估
    if stars >= 2 and pf is not None:
        lines.append(
            f"模型底气: 历史胜率 {dir_acc:.0%}，盈亏比(PF) {pf:.2f}。"
            f"中等信用，仓位适中。"
        )
    else:
        lines.append(
            f"模型底气: 历史胜率 {dir_acc:.0%}，盈亏比(PF) {pf:.2f}。"
            f"弱信号品种，轻仓或观望。"
        )
    
    # 2. 方向建议
    if "多" in direction:
        lines.append(f"方向看多，建议逢低做多。")
    elif "空" in direction:
        lines.append(f"方向看空，建议逢高做空。")
    else:
        lines.append(f"方向中性，建议观望或区间操作。")
    
    # 3. 风险提示
    if high_vol:
        lines.append("⚠️ 极高波动预警，建议减仓或止损。")
    
    # 4. 持仓周期
    hold = entry.get("best_hold_period", "T+1 ~ T+24")
    lines.append(f"建议持仓周期: {hold}")
    
    return lines
```

### 8.3 建议等级

| 等级 | 条件 | 建议动作 |
|------|------|----------|
| **强建议** | 2 星 + PF>1.1 + 方向明确 | 中等仓位开仓 |
| **弱建议** | 1 星 或 PF~1.0 | 轻仓试探或观望 |
| **不建议** | 中性方向 或 Vol 熔断 | 空仓等待 |

---

## 9. 完整流程示例

### 9.1 场景：2026-09-10 14:30，预测 SS (不锈钢)

**Step 1: 数据检查**
```bash
python scripts/cascade_predict.py ss --collect-if-stale 1
# 输出: [DATA] SS 1H 数据时效: 2h, 日线时效: 1d → OK
```

**Step 2: Stage 1 日线预测**
```
[Stage 1] 日线预测 (context=250d, horizon=22d)...
  历史窗口: 250 天
  预测天数: 22 天
  预测范围: 14320.5 ~ 14680.2
  Horizon 斜率: +0.153%/天
  方向: 看多 ↑
```

**Step 3: Stage 2 1H 级联预测**
```
[Stage 2] 1H 级联预测 (XReg, horizon=24h, cov=calendar_cyclical)...
  Context: 480 bars (20 天)
  Horizon: 24 bars (1 天)
  协变量: calendar_cyclical (日历周期效应)
  
  预测结果:
    T+1~T+12 均价: 14520 (方向: 多)
    T+13~T+24 均价: 14580 (方向: 多)
    分位数: P10=14380, P50=14550, P90=14660
```

**Step 4: 风险评估**
```
[Vol Gating] OFF (default static scheme)
  (若启用: Vol_Prob=0.32 < 0.55 → 正常)
```

**Step 5: 生成报告**
```markdown
# SS (不锈钢) 级联预测报告

## 方向判断: 看多 ↑

| 指标 | 值 |
|------|-----|
| 日线斜率 | +0.153%/天 |
| 1H 预测 (T+1~12) | 14520 |
| 1H 预测 (T+13~24) | 14580 |
| 置信区间 P10~P90 | 14380 ~ 14660 |

## 模型信用: ⭐⭐ (2星)

| 指标 | 值 |
|------|-----|
| 历史胜率 | 51% |
| 盈亏比 PF | 1.12 |
| 回测 MaxDD | -35% |
| 协变量 | calendar_cyclical |

## 领航员建议

- 方向看多，胜率 51%，建议轻仓试探
- 短期信号强于长期，建议 T+12 前平仓
- 止损参考: P10=14380
- 止盈参考: P90=14660
```

### 9.2 命令行完整流程

```bash
# 1. 激活环境
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
cd D:/FlyBuddy/FM_a

# 2. 单品种预测（自动补采数据）
python scripts/cascade_predict.py ss --collect-if-stale 1

# 3. 多品种预测
python scripts/cascade_predict.py ss rb sr m jd

# 4. 信用 2 星品种批量预测
python scripts/cascade_predict.py --three-star

# 5. 主观交易领航员（推荐盘中入口）
python scripts/copilot.py ss fu --no-refresh

# 6. 启用 Vol 熔断（实验性）
python scripts/cascade_predict.py ss --vol-filter-neutral
```

---

## 10. 附录：关键配置

### 10.1 品种配置速查表

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

### 10.2 关键参数

| 参数 | 值 | 来源 | 说明 |
|------|-----|------|------|
| `CONTEXT_BARS` | 480 | backtest_config.py | 1H context 长度 |
| `CONTEXT_DAYS` | 250 | backtest_config.py | 日线 context 长度 |
| `HORIZON` | 24 | backtest_config.py | 1H 预测时域 |
| `HORIZON_DAYS` | 22 | backtest_config.py | 日线预测天数 |
| `STEP` | 2 | backtest_config.py | 评估步长（密集） |
| `EVAL_WINDOW_BARS` | 1200 | backtest_config.py | 评估窗口 (~200 交易日) |
| `SLIPPAGE_TICKS` | 2 | backtest_config.py | 双边滑点 tick 数 |
| `TREND_THRESHOLD_PCT` | 0.1 | prediction_scheme.py | 趋势判断阈值 (%/天) |

### 10.3 文件路径

| 文件 | 用途 |
|------|------|
| `config/prediction_scheme.py` | 品种固化方案 SCHEMES |
| `config/backtest_config.py` | 回测参数配置 |
| `config/knowledge_base.json` | Copilot 信用背书 |
| `cascade/daily_model.py` | Stage 1 日线模型 |
| `cascade/hourly_model.py` | Stage 2 1H 级联模型 |
| `cascade/features.py` | 协变量构建 |
| `cascade/vol_risk_filter.py` | 波动率熔断器 |
| `scripts/cascade_predict.py` | 级联预测主入口 |
| `scripts/copilot.py` | 主观交易领航员 |

---

## 总结

FM_a 系统的核心价值在于：

1. **两阶段级联**：日线定方向，1H 定时机，跨周期信息融合
2. **品种异质化**：每个品种有独立的协变量配置和信用评估
3. **严格防穿越**：所有预测使用历史数据，回测结果可复现
4. **风险管理**：Vol 熔断（可选）、置信区间、止损止盈参考
5. **人机协作**：系统输出建议，人类做最终决策

**使用建议**：
- 优先关注 2 星品种（SS/SR/M/RB/EG/LH/CJ/JD）
- 轻仓试探，根据实际表现调整仓位
- 结合基本面和主观判断，不盲从模型
- 定期回顾预测准确率，持续优化

---

*文档维护：本文档随系统迭代更新，最新版本见 `docs/system_design.md`*
