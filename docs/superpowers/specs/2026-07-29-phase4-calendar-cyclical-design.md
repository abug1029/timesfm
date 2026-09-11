# Phase 4: JD 日历周期协变量设计 (calendar_cyclical)

> **文档状态（2026-09-11）**：**历史战役**。正文当考古。活 SCHEMES 以 `config/prediction_scheme.py` 为准。不要按本文改生产方案表。

> 状态: 历史战役（2026-09-11 标注；活 SCHEMES 见 prediction_scheme.py）
> 涉及品种: JD (鸡蛋)为首个验证品种，后续全品种通用
> 依赖: 无(独立协变量类型)

---

## 0. 背景与动机

JD 鸡蛋具有显著的季节性价格规律：
- 春节前后需求激增 → 价格季节性上涨
- 产蛋高峰期(春季/秋季)供给充足 → 价格季节性下跌
- 现有协变量(技术指标/持仓/CCL)均为**反应性**特征，**缺乏前瞻性日历周期信息**

Phase 4 引入确定性日历周期编码，作为 `calendar_cyclical` 协变量类型接入现有 TimesFM XReg 体系，补齐"时间维度先验信息"。

---

## 1. 协变量设计

### 1.1 编码维度 (4 维正余弦)

| 维度 | 公式 | 周期 | 语义 |
|------|------|------|------|
| `doy_sin` | `sin(2π × DayOfYear / 365)` | 年度 | 年内位置(春节/清明/中秋等) |
| `doy_cos` | `cos(2π × DayOfYear / 365)` | 年度 | 同正弦,正交解码 |
| `month_sin` | `sin(2π × Month / 12)` | 月度 | 月内位置(月初/月中/月末) |
| `month_cos` | `cos(2π × Month / 12)` | 月度 | 同正弦,正交解码 |

> **为何不用裸 DayOfYear(1-365)**：正余弦编码保证周期边界连续性(12/31 ≈ 1/1, 12月 ≈ 1月)，避免模型需自学周期拓扑。

### 1.2 输入源
- `df_1h["dt"]` (dtype `datetime64[ns]`, 已有列)
- 由 `pd.DatetimeIndex(df_1h["dt"]).dayofyear` / `.month` 直接计算，**无额外依赖**

### 1.3 Horizon 填充策略 — 精确优先 + 兜底常数

```
For each future step t in 1..horizon:
    future_dt = last_context_dt + t * 1H
    # 交易日历感知: 若 future_dt 落在非交易时段(夜盘休市/周末/节假日),
    # 向前/向后查找最近有效交易日(复用 trading_calendar.py 逻辑)
    if future_dt in valid_trading_sessions:
        compute 4-dim from future_dt
    else:
        fallback = last_valid_4dim  # 常数兜底
```

- **主路径**: 精确未来值 — 确定性日历,无需模型预测
- **兜底**: 交易日历对齐失败(极少见) → 最后已知 4 维常数填充
- **不使用**: 指数衰减/零衰减 — 日历特征非衰减性质

---

## 2. 代码落地位置

### 2.1 `cascade/features.py` — 核心实现

**新增函数** (约 60 行,放在 `calc_ha_body_direction` 之后、`build_covariate_matrix` 之前):

```python
def calc_calendar_cyclical(df_1h: pd.DataFrame, horizon: int) -> np.ndarray:
    """
    计算日历周期协变量 (4 维: doy_sin, doy_cos, month_sin, month_cos)

    Args:
        df_1h: 包含 'dt' 列的 1H 数据框
        horizon: 预测步数 (默认 24)

    Returns:
        np.ndarray shape (len(df_1h) + horizon, 4) — context + horizon 填充
    """
    # 1) Context 部分: 历史每根 bar 的 4 维
    dt_idx = pd.DatetimeIndex(df_1h["dt"])
    doy = dt_idx.dayofyear.values      # 1-365 (闰年 366 自动处理)
    month = dt_idx.month.values        # 1-12
    context_4d = np.column_stack([
        np.sin(2 * np.pi * doy / 365.25),    # doy_sin
        np.cos(2 * np.pi * doy / 365.25),    # doy_cos
        np.sin(2 * np.pi * month / 12),       # month_sin
        np.cos(2 * np.pi * month / 12),       # month_cos
    ])  # (n_bars, 4)

    # 2) Horizon 部分: 精确未来值
    last_dt = dt_idx[-1]
    horizon_4d = []
    for h in range(1, horizon + 1):
        future_dt = last_dt + pd.Timedelta(hours=h)
        # 交易日历兜底: 复用 trading_calendar.is_trading_session (若有)
        # 简化版: 直接用 future_dt 计算,非交易时段自然会有值(模型会学习其权重为 0)
        future_doy = future_dt.timetuple().tm_yday
        future_month = future_dt.month
        horizon_4d.append([
            np.sin(2 * np.pi * future_doy / 365.25),
            np.cos(2 * np.pi * future_doy / 365.25),
            np.sin(2 * np.pi * future_month / 12),
            np.cos(2 * np.pi * future_month / 12),
        ])
    horizon_4d = np.array(horizon_4d)  # (horizon, 4)

    return np.vstack([context_4d, horizon_4d])  # (n_bars + horizon, 4)
```

**注册到 `build_covariate_matrix`**: 在现有 `elif` 链末尾(约 line 1083 之后)加:

```python
    elif covariate_type == "calendar_cyclical":
        # 日历周期协变量 (4 维: doy_sin, doy_cos, month_sin, month_cos)
        ctx = calc_calendar_cyclical(df_1h, horizon)
        last_val = ctx[-horizon-1] if len(ctx) > horizon else np.zeros(4)
        covariate_full = np.concatenate([ctx, np.tile(last_val, (horizon, 1))])
        covariate_name = "calendar_cyclical"
```

> 注: `_decay_fill` 等旧工具**不使用**,日历特征无衰减语义。上述 `np.tile(last_val, ...)` 仅作语法占位,实际 `calc_calendar_cyclical` 已返回完整 `(context+horizon, 4)` 数组,直接返回即可。

**支持列表更新**: `build_covariate_matrix` 顶部 `supported = [...]` 追加 `"calendar_cyclical"`。

**Combo 注册**: `build_combo_covariate_matrix` 的 `elif` 链同步加一条 `"calendar_cyclical"` 分支,逻辑同上。

### 2.2 `scripts/covariate_scan.py` — Scan 注册

在 `COVARIATE_TYPES` 列表(约 line 33)追加:

```python
    # ── Phase 4 日历周期 ──
    'calendar_cyclical',
```

无需改动 scan 逻辑 — 新类型自动被遍历测试。

---

## 3. JD Scheme 配置 (验证用)

`config/prediction_scheme.py` 中 JD 现有 scheme 暂**不改** — 先跑 scan 验证 `calendar_cyclical` 单独/组合效果,再决定是否固化。

验证命令:
```bash
python scripts/covariate_scan.py jd --points 7
python scripts/covariate_scan.py jd --points 7 --combo "calendar_cyclical,gated_slope"
```

---

## 4. 测试验收

### 4.1 单测 `tests/test_calendar_cyclical.py`

```python
"""calendar_cyclical 协变量单测"""
import unittest
import pandas as pd
import numpy as np
from cascade.features import calc_calendar_cyclical


class TestCalendarCyclical(unittest.TestCase):

    def test_four_dim_orthogonality(self):
        """4 维正交: sin^2 + cos^2 = 1 (含浮点误差)"""
        n = 100
        df = pd.DataFrame({"dt": pd.date_range("2024-01-01", periods=n, freq="h")})
        out = calc_calendar_cyclical(df, horizon=0)
        doy_sin, doy_cos, m_sin, m_cos = out.T
        np.testing.assert_allclose(doy_sin**2 + doy_cos**2, 1.0, rtol=1e-10)
        np.testing.assert_allclose(m_sin**2 + m_cos**2, 1.0, rtol=1e-10)

    def test_year_boundary_continuity(self):
        """12/31 23h 与 1/1 0h 的 4 维向量应接近(年度周期连续)"""
        df = pd.DataFrame({"dt": pd.to_datetime(["2024-12-31 23:00", "2025-01-01 00:00"])})
        out = calc_calendar_cyclical(df, horizon=0)
        np.testing.assert_allclose(out[0], out[1], rtol=1e-3)  # 仅相隔 1h

    def test_month_boundary_continuity(self):
        """12/31 与 1/1 的 month_sin/cos 应连续"""
        df = pd.DataFrame({"dt": pd.to_datetime(["2024-12-31 12:00", "2025-01-01 12:00"])})
        out = calc_calendar_cyclical(df, horizon=0)
        np.testing.assert_allclose(out[0, 2:], out[1, 2:], rtol=1e-3)  # 仅 month 维

    def test_horizon_fill_shape(self):
        """horizon 填充后 shape = (n_context + horizon, 4)"""
        df = pd.DataFrame({"dt": pd.date_range("2024-06-15", periods=480, freq="h")})
        out = calc_calendar_cyclical(df, horizon=24)
        self.assertEqual(out.shape, (504, 4))

    def test_horizon_future_values_correct(self):
        """horizon 部分确实是未来时刻的日历值,非重复最后值"""
        df = pd.DataFrame({"dt": pd.date_range("2024-12-31 20:00", periods=10, freq="h")})
        out = calc_calendar_cyclical(df, horizon=5)
        # 最后 5 行对应 2025-01-01 02:00~06:00, month=1, dayofyear=1
        last5_month = out[-5:, 2]  # month_sin
        self.assertTrue(np.all(last5_month > 0))  # sin(2π*1/12) > 0
```

### 4.2 Scan 冒烟
```bash
python -m unittest tests.test_calendar_cyclical -v
python scripts/covariate_scan.py jd --points 3  # exit 0, 输出 MAE/DirAcc
```

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 闰年 DayOfYear=366 | 分母用 `365.25` 近似,误差 < 0.1%,可接受 |
| 交易日历非连续(周末/节假日) | horizon 填充用自然时间推进,模型自学权重为 0;若需严格交易日对齐,后续接入 `trading_calendar.is_trading_session` |
| 4 维向量增加 XReg 宽度 | TimesFM 原生支持多维协变量,无架构变更 |
| Scan 搜索空间 +1 | 仅增 1 类,影响可忽略;若后续 combo 爆炸可加 combo 剪枝 |

---

## 6. 验收标准

- [ ] `tests/test_calendar_cyclical.py` 5/5 PASS
- [ ] `python scripts/covariate_scan.py jd --points 3` 正常输出,`calendar_cyclical` 出现在结果表
- [ ] `build_covariate_matrix(..., covariate_type="calendar_cyclical")` 返回 shape `(n, 4)` 且无 NaN
- [ ] 现有协变量(`ha_body`/`bb_squeeze`/...) 单测不回归

---

## 7. 后续扩展 (Out of Scope 本 Phase)

- **Phase 4b**: `trading_calendar.is_trading_session` 精确交易日对齐
- **Phase 4c**: 组合扫描剪枝(如 `calendar_cyclical` + `gated_slope` 自动进 TOP5 才展开)
- **Phase 4d**: 其他强季节性品种(SR/CF/TA/UR)的 scheme 固化

---

> **文档状态**: 设计完成,待用户审核。审核通过后进入 `writing-plans` 生成实施计划。