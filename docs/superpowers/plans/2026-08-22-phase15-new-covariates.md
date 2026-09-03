# Phase 15: 新协变量开发 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 4 个全新信号维度 (NVI/QSTICK/VWAP偏离/StdDev) 的协变量，突破 6 个弱信号品种 (JM/MA/UR/FG/CF/AO) 的 PF 天花板。

**Architecture:** 在 `cascade/features.py` 中新增 4 个 `_calc_*()` 函数 + `build_covariate_matrix()` / `build_combo_covariate_matrix()` 的 elif 分支。先跑相关性预检确认信息增量，再实现 + 测试，最后分 3 阶段回测 (15a 弱信号 24 tests → 15b 条件组合 → 15c 已 GREEN 验证)。

**Tech Stack:** Python + pandas + numpy, monthly_backtest.py walk-forward 框架

**Spec:** `docs/superpowers/specs/2026-08-22-phase15-new-covariates-design.md` (v2)

## Global Constraints

- GREEN 判定: PF >= 1.0 AND EV_ratio > 0 AND abs(MaxDD) < 80% AND n_eval >= 350
- 列名: `close_price`, `open_price`, `high`, `low`, `volume` (kline_1h 表 schema)
- 新协变量 key: `nvi`, `qstick`, `vwap_deviation`, `stddev`
- 相关性预检阈值: mean |corr| >= 0.7 → 放弃该协变量
- Phase 15b hard cap: 总组合 tests <= 30
- 每个 task 完成后专家审核，有问题即 debug，通过后再进下一个 task

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `scripts/p15_corr_precheck.py` | 新协变量 vs 现有 19 协变量的相关性预检 |
| 修改 | `cascade/features.py` | 新增 4 个 `_calc_*()` + 8 个 elif 分支 + supported 列表扩展 |
| 新建 | `tests/test_new_covariates.py` | 4 协变量单元测试 (shape/NaN/值域/combo) |
| 新建 | `scripts/batch_p15a_new_cov.sh` | Phase 15a 批次脚本 (6品种×4协变量=24 tests) |

---

### Task 0: 相关性预检

**Files:**
- Create: `scripts/p15_corr_precheck.py`
- Read: `cascade/features.py:1427` (supported 列表)

**Purpose:** 确认 4 个新协变量与现有 19 个协变量的信息冗余度，筛除 mean|corr|>=0.7 的协变量。

- [ ] **Step 1: 编写预检脚本**

```python
#!/usr/bin/env python
"""Phase 15 相关性预检: 4 新协变量 vs 现有 19 协变量"""
import sys, os, numpy as np, pandas as pd
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from data.data_store import DataStore

# === 新协变量计算 (独立实现, 不依赖 features.py) ===

def calc_nvi(close: np.ndarray, volume: np.ndarray, lookback=20) -> np.ndarray:
    nvi = np.full(len(close), np.nan)
    nvi[0] = 1000.0
    for i in range(1, len(close)):
        if np.isnan(volume[i]) or np.isnan(volume[i-1]):
            nvi[i] = nvi[i-1]  # NULL bar 跳过
            continue
        ret = (close[i] - close[i-1]) / (close[i-1] + 1e-8)
        if volume[i] < volume[i-1]:
            nvi[i] = nvi[i-1] * (1 + ret)
        else:
            nvi[i] = nvi[i-1]
    s = pd.Series(nvi)
    zscore = (s - s.rolling(lookback).mean()) / (s.rolling(lookback).std() + 1e-8)
    return zscore.values

def calc_qstick(close: np.ndarray, open_: np.ndarray, lookback=14) -> np.ndarray:
    body = close - open_
    qstick = pd.Series(body).rolling(lookback).mean().values
    std = pd.Series(qstick).rolling(60).std().values
    return np.where(std > 1e-8, qstick / (std + 1e-8), 0.0)

def calc_vwap_dev(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                  volume: np.ndarray, lookback=24) -> np.ndarray:
    tp = (high + low + close) / 3
    tp_vol = pd.Series(tp * volume).rolling(lookback).sum().values
    vol_sum = pd.Series(volume).rolling(lookback).sum().values
    vwap = tp_vol / (vol_sum + 1e-8)
    return (close - vwap) / (vwap + 1e-8)

def calc_stddev(close: np.ndarray, lookback=20) -> np.ndarray:
    stddev = pd.Series(close).rolling(lookback).std().values
    mean60 = pd.Series(stddev).rolling(60).mean().values
    return np.where(mean60 > 1e-8, stddev / (mean60 + 1e-8) - 1.0, 0.0)

# === 主流程 ===

def precheck(symbol: str = "ss"):
    store = DataStore(symbol)
    df = store.get_main_contract_1h(limit=5000)
    if df is None or len(df) < 500:
        print(f"[ERROR] {symbol}: 1H 数据不足 (n={len(df) if df is not None else 0})")
        return

    c = df["close_price"].values.astype(float)
    o = df["open_price"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    v = df["volume"].values.astype(float)

    new_covs = {
        "nvi": calc_nvi(c, v),
        "qstick": calc_qstick(c, o),
        "vwap_deviation": calc_vwap_dev(c, h, l, v),
        "stddev": calc_stddev(c),
    }

    print(f"=== Phase 15 相关性预检: {symbol.upper()} (n={len(df)}) ===\n")
    print(f"{'新协变量':<18} {'mean|corr|':>10} {'max|corr|':>10} {'判定':>8}")
    print("-" * 52)

    for name, arr in new_covs.items():
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            print(f"{name:<18} {'ALL NaN':>10}")
            continue
        print(f"{name:<18} {np.mean(np.abs(valid)):.4f}   {np.max(np.abs(valid)):.4f}   mean={np.mean(valid):.4f} std={np.std(valid):.4f}")

    # 计算新协变量之间的互相关
    print(f"\n=== 新协变量互相关矩阵 ===")
    names = list(new_covs.keys())
    arrs = [new_covs[n] for n in names]
    min_len = min(len(a) for a in arrs)
    mat = np.column_stack([a[:min_len] for a in arrs])
    corr = np.corrcoef(mat, rowvar=False)
    header = "        " + "  ".join(f"{n[:6]:>8}" for n in names)
    print(header)
    for i, n in enumerate(names):
        row = f"{n:<8}" + "  ".join(f"{corr[i,j]:.4f}" for j in range(len(names)))
        print(row)

if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "ss"
    precheck(sym)
```

- [ ] **Step 2: 运行预检脚本**

```bash
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
cd D:/FlyBuddy/FM_a
python scripts/p15_corr_precheck.py ss
```

- [ ] **Step 3: 解读结果**

判定标准:
- mean |corr| < 0.5 → 通过, 继续实现
- 0.5 <= mean |corr| < 0.7 → 警告, 保留但记录
- mean |corr| >= 0.7 → 放弃该协变量 (信息冗余)

如 QSTICK vs ha_body 或 StdDev vs vor 的 corr > 0.85, 则禁止 combo 同现。

- [ ] **Step 4: 提交预检脚本**

```bash
git add scripts/p15_corr_precheck.py
git commit -m "feat(P15): add correlation precheck script for 4 new covariates"
```

- [ ] **Step 5: 专家审核**

请用户/专家审核预检结果，确认哪些协变量可以进入实现阶段。

---

### Task 1: 实现 4 个新协变量计算函数

**Files:**
- Modify: `cascade/features.py` (在 `_calc_atr` 之后、`build_covariate_matrix` 之前插入新函数)

**Interfaces:**
- Consumes: `df_1h: pd.DataFrame` (列: `close_price`, `open_price`, `high`, `low`, `volume`)
- Produces: 4 个 `_calc_*()` 函数, 各返回 `np.ndarray`

> **关键**: 列名是 `close_price` / `open_price` (不是 `close` / `open`)

- [ ] **Step 1: 实现 `_calc_nvi()`**

在 `cascade/features.py` 的 `_calc_rsi_slopes` 函数之后插入:

```python
def _calc_nvi(df_1h: pd.DataFrame, lookback: int = 20) -> np.ndarray:
    """NVI: 缩量日累积收益 -> 追踪聪明资金

    规则:
    - volume[i] < volume[i-1] (缩量日): NVI[i] = NVI[i-1] * (1 + ret)
    - 否则: NVI[i] = NVI[i-1]
    - volume 为 NULL 的 bar: 跳过 (不触发也不重置)
    - 连续 NULL > 6: 该段 NVI 置 NaN -> 0 回退

    输出: rolling z-score (lookback=20)
    """
    close = df_1h["close_price"].values.astype(float)
    volume = df_1h["volume"].values.astype(float)
    n = len(close)
    nvi = np.full(n, np.nan)
    nvi[0] = 1000.0
    null_streak = 0

    for i in range(1, n):
        if np.isnan(volume[i]) or np.isnan(volume[i - 1]):
            null_streak += 1
            if null_streak > 6:
                nvi[i] = np.nan
            else:
                nvi[i] = nvi[i - 1] if not np.isnan(nvi[i - 1]) else 1000.0
            continue
        null_streak = 0
        ret = (close[i] - close[i - 1]) / (close[i - 1] + 1e-8)
        if volume[i] < volume[i - 1]:
            prev = nvi[i - 1] if not np.isnan(nvi[i - 1]) else 1000.0
            nvi[i] = prev * (1 + ret)
        else:
            nvi[i] = nvi[i - 1] if not np.isnan(nvi[i - 1]) else 1000.0

    # NaN -> 0 回退
    nvi = np.nan_to_num(nvi, nan=0.0)

    # rolling z-score 标准化
    s = pd.Series(nvi)
    roll_mean = s.rolling(lookback, min_periods=1).mean()
    roll_std = s.rolling(lookback, min_periods=1).std()
    zscore = (s - roll_mean) / (roll_std + 1e-8)
    return zscore.values.astype(float)
```

- [ ] **Step 2: 实现 `_calc_qstick()`**

```python
def _calc_qstick(df_1h: pd.DataFrame, lookback: int = 14) -> np.ndarray:
    """QSTICK: SMA(Close-Open, N) / rolling_std(QSTICK, 60) -> K线多空力量

    输出: 标准化后的多空力量, 范围约 [-3, 3]
    """
    close = df_1h["close_price"].values.astype(float)
    open_ = df_1h["open_price"].values.astype(float)
    body = close - open_
    qstick = pd.Series(body).rolling(lookback, min_periods=1).mean().values
    qstick_std = pd.Series(qstick).rolling(60, min_periods=1).std().values
    return np.where(qstick_std > 1e-8, qstick / (qstick_std + 1e-8), 0.0)
```

- [ ] **Step 3: 实现 `_calc_vwap_deviation()`**

```python
def _calc_vwap_deviation(df_1h: pd.DataFrame, lookback: int = 24) -> np.ndarray:
    """VWAP偏离: (Close-VWAP)/VWAP -> 量价公允偏离度

    规则:
    - typical_price = (high + low + close) / 3
    - VWAP = sum(tp * vol, N) / sum(vol, N)
    - deviation = (close - VWAP) / VWAP
    - high/low 任一 NULL -> 该 bar VWAP = NaN -> 0 回退
    - 不用 close 替代 (退化为 close 加权均值, 失去指标含义)

    输出: 原始偏离值, 自然约束在 [-1, 1]
    """
    close = df_1h["close_price"].values.astype(float)
    high = df_1h["high"].values.astype(float)
    low = df_1h["low"].values.astype(float)
    volume = df_1h["volume"].values.astype(float)

    tp = (high + low + close) / 3.0
    tp_vol = pd.Series(tp * volume).rolling(lookback, min_periods=1).sum().values
    vol_sum = pd.Series(volume).rolling(lookback, min_periods=1).sum().values
    vwap = tp_vol / (vol_sum + 1e-8)
    deviation = (close - vwap) / (np.abs(vwap) + 1e-8)
    return np.nan_to_num(deviation, nan=0.0)
```

- [ ] **Step 4: 实现 `_calc_stddev()`**

```python
def _calc_stddev(df_1h: pd.DataFrame, lookback: int = 20) -> np.ndarray:
    """StdDev: 收盘价标准差 -> 市场恐慌度/趋势过滤器

    规则:
    - stddev = std(close, lookback)
    - normalized = (stddev - mean(stddev, 60)) / mean(stddev, 60)
    - >0: 当前波动高于长期均值; <0: 低于

    输出: 百分比偏离值
    """
    close = df_1h["close_price"].values.astype(float)
    stddev = pd.Series(close).rolling(lookback, min_periods=1).std().values
    stddev_mean = pd.Series(stddev).rolling(60, min_periods=1).mean().values
    return np.where(stddev_mean > 1e-8, stddev / (stddev_mean + 1e-8) - 1.0, 0.0)
```

- [ ] **Step 5: 运行现有测试确认无回归**

```bash
cd D:/FlyBuddy/FM_a
python -m pytest tests/test_evaluation_metrics_contract.py tests/test_prediction_scheme_phase9.py -v --tb=short 2>&1 | head -40
```

- [ ] **Step 6: 提交**

```bash
git add cascade/features.py
git commit -m "feat(P15): add 4 new covariate calc functions (nvi/qstick/vwap_deviation/stddev)"
```

- [ ] **Step 7: 专家审核**

审核 4 个函数的公式正确性、NULL 处理、列名一致性。

---

### Task 2: 添加 elif 分支 + supported 列表

**Files:**
- Modify: `cascade/features.py:1297-1427` (build_combo_covariate_matrix 的 elif 链)
- Modify: `cascade/features.py:856-910` (build_covariate_matrix 的 elif 链)
- Modify: `cascade/features.py:1427` (supported 列表)

**Interfaces:**
- Consumes: `_calc_nvi()`, `_calc_qstick()`, `_calc_vwap_deviation()`, `_calc_stddev()` (Task 1)
- Produces: `build_covariate_matrix(covariate_type="nvi"|"qstick"|"vwap_deviation"|"stddev")` 可用
- Produces: `build_combo_covariate_matrix(covariate_types=[...])` 可包含新协变量

- [ ] **Step 1: 在 `build_combo_covariate_matrix` 的 elif 链末尾 (vor 分支之后, ~L1424) 添加 4 个分支**

```python
        # ── Phase 15: 新信号维度协变量 ──
        elif cov_type == "nvi":
            ctx = _calc_nvi(df_1h, lookback=20)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
            result["nvi"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "qstick":
            ctx = _calc_qstick(df_1h, lookback=14)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
            result["qstick"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "vwap_deviation":
            ctx = _calc_vwap_deviation(df_1h, lookback=24)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            result["vwap_deviation"] = np.concatenate([ctx, np.full(horizon, last_val)])

        elif cov_type == "stddev":
            ctx = _calc_stddev(df_1h, lookback=20)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
            result["stddev"] = np.concatenate([ctx, last_val * decay])
```

- [ ] **Step 2: 在 `build_covariate_matrix` 的 elif 链末尾 (vor 分支之后) 添加同样的 4 个分支**

模式与 Step 1 完全相同。`build_covariate_matrix` 中已有 `_decay_fill` 辅助函数可复用:

```python
        # ── Phase 15: 新信号维度协变量 ──
        elif cov_type == "nvi":
            ctx = _calc_nvi(df_1h, lookback=20)
            result["nvi"] = np.concatenate([ctx, _decay_fill(float(ctx[-1]), horizon)])

        elif cov_type == "qstick":
            ctx = _calc_qstick(df_1h, lookback=14)
            result["qstick"] = np.concatenate([ctx, _decay_fill(float(ctx[-1]), horizon)])

        elif cov_type == "vwap_deviation":
            ctx = _calc_vwap_deviation(df_1h, lookback=24)
            result["vwap_deviation"] = np.concatenate([ctx, np.full(horizon, float(ctx[-1]))])

        elif cov_type == "stddev":
            ctx = _calc_stddev(df_1h, lookback=20)
            result["stddev"] = np.concatenate([ctx, _decay_fill(float(ctx[-1]), horizon)])
```

- [ ] **Step 3: 扩展 supported 列表 (L1427)**

当前:
```python
supported = ["oi", "rsi_state", "hurst", "hourly_slope", "rsi_slope",
             ...]
```

追加 4 个 key:
```python
supported = ["oi", "rsi_state", "hurst", "hourly_slope", "rsi_slope",
             ..., "nvi", "qstick", "vwap_deviation", "stddev"]
```

- [ ] **Step 4: 验证 monthly_backtest.py 可调用新协变量**

```bash
cd D:/FlyBuddy/FM_a
python -c "
from cascade.features import build_combo_covariate_matrix
from data.data_store import DataStore
import numpy as np

store = DataStore('ss')
hist = np.random.randn(500) * 100 + 5000
pred = np.random.randn(22) * 10 + hist[-1]
try:
    result = build_combo_covariate_matrix(
        symbol='ss', store=store,
        historical_daily_closes=hist,
        predicted_daily_closes=pred,
        covariate_types=['nvi', 'qstick', 'vwap_deviation', 'stddev'],
        limit=480,
    )
    for k, v in result.items():
        print(f'  {k}: shape={v.shape}, nan={np.isnan(v).sum()}, range=[{v.min():.4f}, {v.max():.4f}]')
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
"
```

预期: 4 个新协变量均有正确 shape (context_len+horizon,)，nan=0，值域合理。

- [ ] **Step 5: 提交**

```bash
git add cascade/features.py
git commit -m "feat(P15): wire 4 new covariates into build_covariate_matrix + combo matrix"
```

- [ ] **Step 6: 专家审核**

审核 elif 分支的 horizon 填充策略 (decay vs flat)、supported 列表完整性。

---

### Task 3: 单元测试

**Files:**
- Create: `tests/test_new_covariates.py`

- [ ] **Step 1: 编写测试文件**

```python
"""Phase 15: 4 个新协变量单元测试"""
import unittest
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cascade.features import _calc_nvi, _calc_qstick, _calc_vwap_deviation, _calc_stddev


def _make_df(n=500, seed=42):
    """构造测试用 1H DataFrame"""
    rng = np.random.RandomState(seed)
    close = 5000 + np.cumsum(rng.randn(n) * 10)
    open_ = close + rng.randn(n) * 5
    high = np.maximum(close, open_) + np.abs(rng.randn(n) * 3)
    low = np.minimum(close, open_) - np.abs(rng.randn(n) * 3)
    volume = (rng.uniform(1000, 10000, n)).astype(int)
    return pd.DataFrame({
        "close_price": close, "open_price": open_,
        "high": high, "low": low, "volume": volume,
    })


class TestNVI(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_volume_null_handling(self):
        df = _make_df()
        df.loc[10:13, "volume"] = np.nan
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_volume_null_streak_gt6(self):
        df = _make_df()
        df.loc[10:20, "volume"] = np.nan
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_zscore_normalized(self):
        df = _make_df(n=1000)
        result = _calc_nvi(df, lookback=20)
        mid = result[100:900]
        self.assertAlmostEqual(np.mean(mid), 0.0, delta=0.5)


class TestQSTICK(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_qstick(df, lookback=14)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_qstick(df, lookback=14)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_bounded_range(self):
        df = _make_df(n=1000)
        result = _calc_qstick(df, lookback=14)
        self.assertTrue(np.all(np.abs(result[60:]) < 10))


class TestVWAPDeviation(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_vwap_deviation(df, lookback=24)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_vwap_deviation(df, lookback=24)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_high_low_null_fallback(self):
        df = _make_df()
        df.loc[10:13, "high"] = np.nan
        result = _calc_vwap_deviation(df, lookback=24)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_deviation_near_zero(self):
        df = _make_df(n=1000)
        result = _calc_vwap_deviation(df, lookback=24)
        mid = result[100:900]
        self.assertAlmostEqual(np.mean(np.abs(mid)), 0.0, delta=0.05)


class TestStdDev(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_stddev(df, lookback=20)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_stddev(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_positive_and_negative(self):
        df = _make_df(n=1000)
        result = _calc_stddev(df, lookback=20)
        mid = result[100:900]
        self.assertTrue(np.any(mid > 0))
        self.assertTrue(np.any(mid < 0))


class TestComboIntegration(unittest.TestCase):
    def test_all_four_in_combo(self):
        from cascade.features import build_combo_covariate_matrix
        from data.data_store import DataStore
        store = DataStore("ss")
        hist = np.random.randn(500) * 100 + 5000
        pred = np.random.randn(22) * 10 + hist[-1]
        result = build_combo_covariate_matrix(
            symbol="ss", store=store,
            historical_daily_closes=hist,
            predicted_daily_closes=pred,
            covariate_types=["nvi", "qstick", "vwap_deviation", "stddev"],
            limit=480,
        )
        for key in ["nvi", "qstick", "vwap_deviation", "stddev"]:
            self.assertIn(key, result)
            self.assertEqual(len(result[key].shape), 1)
            self.assertEqual(np.isnan(result[key]).sum(), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认全部通过**

```bash
cd D:/FlyBuddy/FM_a
python -m pytest tests/test_new_covariates.py -v --tb=short
```

预期: 15+ tests 全部 PASS。

- [ ] **Step 3: 提交**

```bash
git add tests/test_new_covariates.py
git commit -m "test(P15): add unit tests for 4 new covariates (nvi/qstick/vwap_deviation/stddev)"
```

- [ ] **Step 4: 专家审核**

审核测试覆盖率、边界条件、NULL 处理测试。

---

### Task 4: Phase 15a 批次脚本

**Files:**
- Create: `scripts/batch_p15a_new_cov.sh`

- [ ] **Step 1: 编写批次脚本**

```bash
#!/usr/bin/env bash
# Phase 15a: 6 弱信号品种 × 4 新协变量 = 24 tests
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_batch_lib.sh" || { echo "ERROR: _batch_lib.sh not found"; exit 1; }

PROGRESS="reports/data_ops/batch_p15a_progress.jsonl"
VARIETIES=(jm ma ur fg cf ao)
COVARIATES=(nvi qstick vwap_deviation stddev)
TOTAL=$(( ${#VARIETIES[@]} * ${#COVARIATES[@]} ))

echo "===== Phase 15a: 新协变量单协变量回测 ====="
echo "品种: ${VARIETIES[*]}"
echo "协变量: ${COVARIATES[*]}"
echo "总计: ${TOTAL} tests"
echo "进度文件: ${PROGRESS}"
echo ""

COUNT=0
for SYM in "${VARIETIES[@]}"; do
    for COV in "${COVARIATES[@]}"; do
        COUNT=$((COUNT + 1))
        echo "[${COUNT}/${TOTAL}] ${SYM} --combo \"${COV}\""
        batch_run_one "${SYM}" "--combo ${COV}" "${PROGRESS}" || true
    done
done

echo ""
echo "===== Phase 15a 完成 ====="
echo "结果: ${PROGRESS}"
```

- [ ] **Step 2: 设置执行权限**

```bash
chmod +x scripts/batch_p15a_new_cov.sh
```

- [ ] **Step 3: 提交**

```bash
git add scripts/batch_p15a_new_cov.sh
git commit -m "feat(P15): add batch script for Phase 15a (6 varieties x 4 covariates)"
```

- [ ] **Step 4: 专家审核**

审核脚本格式、`_batch_lib.sh` 引用、JSONL 输出路径。

---

### Task 5: Phase 15a 回测执行

**Files:**
- Output: `reports/data_ops/batch_p15a_progress.jsonl`

> **前置条件**: Task 0-4 全部审核通过。需用户批准后启动。

- [ ] **Step 1: 用户批准回测**

预计耗时 ~24h (24 tests × 40min)。向用户报告并获批后启动。

- [ ] **Step 2: 启动回测**

```bash
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
cd D:/FlyBuddy/FM_a
export PYTHONIOENCODING=utf-8
nohup bash scripts/batch_p15a_new_cov.sh > reports/data_ops/batch_p15a.log 2>&1 &
```

- [ ] **Step 3: 监控进度**

```bash
tail -f reports/data_ops/batch_p15a_progress.jsonl
wc -l reports/data_ops/batch_p15a_progress.jsonl  # 应到 24 行
```

- [ ] **Step 4: 回测完成后解析结果**

```python
import json
results = []
with open("reports/data_ops/batch_p15a_progress.jsonl") as f:
    for line in f:
        results.append(json.loads(line))

from collections import defaultdict
by_sym = defaultdict(list)
for r in results:
    by_sym[r["symbol"]].append(r)

for sym, runs in sorted(by_sym.items()):
    print(f"\n{sym.upper()}:")
    for r in runs:
        pf = r.get("profit_factor", 0)
        ev = r.get("ev_ratio", 0)
        maxdd = r.get("max_drawdown_pct", 0)
        n = r.get("n_eval", 0)
        green = pf >= 1.0 and ev > 0 and abs(maxdd) < 80 and n >= 350
        status = "GREEN" if green else "FAIL"
        print(f"  {r['combo']:<20s} PF={pf:.3f} EV={ev:.4f} MaxDD={maxdd:.1f}% n={n} [{status}]")
```

---

### Task 6: 结果评估与固化决策

**Files:**
- Create: `reports/research/20260822_phase15a_results.md`
- Modify: `docs/backtest_registry.md` (6 品种追加 Phase 15 行)
- Modify: `config/prediction_scheme.py` (如固化)
- Modify: `STATE.md` (追加 Phase 15 结论)

- [ ] **Step 1: 生成结果报告**

按 §5 退出条件判定:
- >=1 GREEN, baseline FAIL → 固化新协变量
- >=1 GREEN, baseline PASS → 保持当前方案
- 0 GREEN, PF 提升 >5% → 进入 Phase 15b (hard cap 30 tests)
- 0 GREEN, PF 无提升 → 宣告协变量路径彻底穷尽

- [ ] **Step 2: 更新 Registry**

对每个品种在 `docs/backtest_registry.md` 追加 Phase 15 行。

- [ ] **Step 3: 更新 STATE.md**

追加 Phase 15a 结论。

- [ ] **Step 4: 提交**

```bash
git add reports/research/20260822_phase15a_results.md docs/backtest_registry.md STATE.md
git commit -m "docs(P15): Phase 15a results report and registry update"
```

- [ ] **Step 5: 专家审核**

审核结果报告的完整性、GREEN 判定正确性、退出条件执行。

---

### Task 7 (条件触发): Phase 15b 组合优化

> 仅在 Task 6 判定 "0 GREEN, PF 提升 >5%" 时触发。Hard cap: 30 tests。

- [ ] **Step 1: 筛选候选组合**

仅对 PF 提升 >5% 的品种，尝试新协变量 × 当前 baseline 协变量的 2-cov 组合。
每品种最多 5 个组合，总 tests <= 30。

- [ ] **Step 2: 执行组合回测**

```bash
python scripts/monthly_backtest.py <sym> --combo "<baseline_cov>,<new_cov>"
```

- [ ] **Step 3: 评估结果**

GREEN → 固化; 仍 FAIL → 宣告协变量路径彻底穷尽。

---

### Task 8 (条件触发): Phase 15c 已 GREEN 品种验证

> 仅在 Task 6 判定 ">=1 GREEN" 时触发。

对已 GREEN 品种测试新协变量作为 additive:
- 对每个 Phase 15a GREEN 的新协变量 X
- 对每个已 GREEN 品种，跑 `--combo "当前协变量,X"`
- 对比 baseline 的 PF

---

## 执行顺序

```
Task 0 (预检 ~0.5h) → 审核 → Task 1 (实现 ~2h) → 审核 → Task 2 (分支 ~1h) → 审核
→ Task 3 (测试 ~1h) → 审核 → Task 4 (脚本 ~0.5h) → 审核
→ Task 5 (回测 ~24h) → Task 6 (评估 ~1h)
→ [条件] Task 7 (组合 ≤20h) / Task 8 (验证 ≤14h)
```

总计: ~27h (15a 收敛) 至 ~60h (最坏情况)。

## 验证标准

- Task 0: 相关性预检完成，4 个协变量的 mean|corr| 已记录
- Task 1: 4 个函数在 features.py 中，无语法错误
- Task 2: `build_covariate_matrix(covariate_type="nvi")` 可调用，输出 shape 正确
- Task 3: 15+ 单元测试全部通过
- Task 4: 批次脚本可执行
- Task 5: 24 次回测完成，JSONL 有 24 行
- Task 6: 结果报告 + Registry + STATE.md 更新
