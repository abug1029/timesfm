# Phase 8a: Crack Spread 跨品种协变量框架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 FM_a 级联预测系统添加首个跨品种协变量框架,以 PX-TA 裂解价差(PTA 加工费)为首验证标的,三模式(level/slope/zscore)可配,scan 数据裁决。

**Architecture:** 底层纯函数 `calc_crack_spread(df_main, df_leg, ratio, mode, ...)` 做 left-join 对齐 + 三模式数学变换;`hourly_model.predict()` 作 DI 咽喉点构建 `feedstock_cache`(cutoff 感知,防穿越);`build_covariate_matrix`/`build_combo_covariate_matrix` 通过通用 `feedstock_cache` context 参数分发,签名只膨胀一次。BacktestDataStore 下沉到 data 层解层洁癖。

**Tech Stack:** Python 3, pandas, numpy, SQLite (DataStore), TimesFM 2.5 XReg, unittest。虚拟环境 `D:/FlyBuddy/shared/timesfm/.venv/`。

## Global Constraints

- 所有面向用户输出用中文(用户最高指令)。
- 高风险路径保护: `config/prediction_scheme.py` / `cascade/*.py` / `data/config.py` 仅允许加注释或本 spec 批准的新增;不改既有固化方案。
- 零回归铁律: 非 crack_spread 路径字节级不变。
- 路径含 `\Pu chong\` 空格时,读取用 8.3 短名 `\PUCHON~1\`。
- 长 GPU 任务(回测)用 nohup+disown,勿用 run_in_background。
- venv python: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe`
- Phase 8a **不固化** prediction_scheme.py(underpowered n≈178,仅验证)。
- spec 文档: `docs/superpowers/specs/2026-07-31-phase8-crack-spread-design.md`

---

## File Structure

| 文件 | 责任 | 操作 |
|------|------|------|
| `data/data_store.py` | DataStore + **BacktestDataStore**(下沉来) | Modify(加类) |
| `scripts/backtest_1h.py` | walk-forward 回测 | Modify(删类,改 import) |
| `scripts/backtest_vol_gating_fullchain.py` | vol 门控回测 | Modify(import) |
| `scripts/batch_backtest.py` | 批量回测 | Modify(import) |
| `scripts/covariate_scan_new.py` | scan 新版 | Modify(import) |
| `scripts/monthly_backtest.py` | 月度回测 | Modify(import) |
| `scripts/validate_context_length.py` | context 校验 | Modify(import) |
| `config/crack_spread_pairs.py` | 跨品种配对配置 | Create |
| `cascade/features.py` | `calc_crack_spread` + build_* 分发 | Modify |
| `cascade/hourly_model.py` | DI 咽喉点 `_fetch_feedstock_1h` | Modify |
| `scripts/covariate_scan.py` | scan 注册 3 档 | Modify |
| `scripts/phase4d_parse_results.py` | verdict 用 effective_n | Modify |
| `tests/test_crack_spread.py` | 单测 | Create |

---

## Task 1: BacktestDataStore 下沉到 data 层

**Files:**
- Modify: `data/data_store.py`(末尾加类)
- Modify: `scripts/backtest_1h.py:35-70`(删类) + `:26`(改 import)
- Modify: `scripts/backtest_vol_gating_fullchain.py:55`, `scripts/batch_backtest.py:19`, `scripts/covariate_scan_new.py:35`, `scripts/monthly_backtest.py:49`, `scripts/validate_context_length.py:16`(5 处 import)

**Interfaces:**
- Produces: `from data.data_store import BacktestDataStore` 可被 cascade 层 import(解层洁癖)。类签名不变 `BacktestDataStore(symbol: str, cutoff_date: str)`。

- [ ] **Step 1: 先 grep 确认完整 import 列表**

Run: `grep -rn "BacktestDataStore" --include="*.py" .`
Expected: 6 文件(backtest_1h 定义 + 5 import)。若更多,补入下步。

- [ ] **Step 2: 将 BacktestDataStore 类移入 data/data_store.py**

把 `scripts/backtest_1h.py:35-70` 的整个 `class BacktestDataStore(DataStore):` (含 `get_main_continuous` / `get_main_contract_1h` / `_get_main_contract_at_cutoff`) 原样粘贴到 `data/data_store.py` 末尾(`DataStore` 类定义之后)。`data_store.py` 已 import `re` / `datetime` / `pd` / `np`,确认无缺失;若 `_get_main_contract_at_cutoff` 用到 `datetime`,已在文件内。

- [ ] **Step 3: scripts/backtest_1h.py 删类 + 改 import**

删除 line 35-70 的类定义。在 line 26-28 的 import 区加:
```python
from data.data_store import DataStore, BacktestDataStore
```
(原 `from data.data_store import DataStore` 改为同时 import 两者。)

- [ ] **Step 4: 更新其余 5 处 import**

把每处 `from scripts.backtest_1h import BacktestDataStore` 改为 `from data.data_store import BacktestDataStore`(Step 1 grep 命中的全部,不靠记忆枚举):
- `scripts/backtest_vol_gating_fullchain.py:55`
- `scripts/batch_backtest.py:19`
- `scripts/covariate_scan_new.py:35`
- `scripts/monthly_backtest.py:49`
- `scripts/validate_context_length.py:16`

- [ ] **Step 5: 零回归冒烟**

Run:
```bash
cd D:/FlyBuddy/fm_a
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "from data.data_store import BacktestDataStore; print('data layer OK')"
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "from scripts.backtest_1h import BacktestDataStore; print('backtest_1h re-export OK')"
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "from scripts.monthly_backtest import run_symbol_backtest; print('monthly OK')"
```
Expected: 三行 OK,无 ImportError。

- [ ] **Step 6: Commit**

```bash
git add data/data_store.py scripts/backtest_1h.py scripts/backtest_vol_gating_fullchain.py scripts/batch_backtest.py scripts/covariate_scan_new.py scripts/monthly_backtest.py scripts/validate_context_length.py
git commit -m "refactor(phase8): BacktestDataStore 下沉到 data 层解 cascade->scripts 反向依赖"
```

---

## Task 2: config/crack_spread_pairs.py 配对配置

**Files:**
- Create: `config/crack_spread_pairs.py`
- Create: `tests/test_crack_spread_pairs.py`

**Interfaces:**
- Produces: `get_crack_pair(symbol: str) -> Optional[Tuple[str, float]]`,返回 `(feedstock_sym, ratio)` 或 `None`。

- [ ] **Step 1: 写失败测试**

`tests/test_crack_spread_pairs.py`:
```python
import unittest
from config.crack_spread_pairs import get_crack_pair, CRACK_SPREAD_PAIRS

class TestCrackPair(unittest.TestCase):
    def test_ta_pair(self):
        self.assertEqual(get_crack_pair("ta"), ("px", 0.655))
    def test_case_insensitive(self):
        self.assertEqual(get_crack_pair("TA"), ("px", 0.655))
    def test_no_pair_returns_none(self):
        self.assertIsNone(get_crack_pair("ss"))
    def test_ta_in_dict(self):
        self.assertIn("ta", CRACK_SPREAD_PAIRS)
```

- [ ] **Step 2: 运行确认失败**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread_pairs -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 config/crack_spread_pairs.py**

```python
"""跨品种 crack spread 品种配对配置 (Phase 8a)

Phase 8a: PX-TA 芳烃链 (PTA 加工费 = TA - 0.655·PX)
Phase 8b 预留: SC 采集就绪后加 fu/bu -> sc (需 bbl->吨换算)
"""
from typing import Optional, Tuple

CRACK_SPREAD_PAIRS: dict[str, dict] = {
    "ta": {"feedstock": "px", "ratio": 0.655},
    # Phase 8b 预留:
    # "fu": {"feedstock": "sc", "ratio": 6.35},   # bbl->吨 待标定
    # "bu": {"feedstock": "sc", "ratio": 6.35},
}


def get_crack_pair(symbol: str) -> Optional[Tuple[str, float]]:
    """返回 (feedstock_sym, ratio) 或 None(无配对)"""
    cfg = CRACK_SPREAD_PAIRS.get(symbol.lower())
    if cfg is None:
        return None
    return (cfg["feedstock"], cfg["ratio"])
```

- [ ] **Step 4: 运行确认通过**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread_pairs -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add config/crack_spread_pairs.py tests/test_crack_spread_pairs.py
git commit -m "feat(phase8): crack_spread_pairs 配对配置 (TA->PX/0.655)"
```

---

## Task 3: calc_crack_spread 纯函数 + 单测

**Files:**
- Modify: `cascade/features.py`(在 `calc_basis_momentum` 之后,约 line 700 处加函数)
- Create: `tests/test_crack_spread.py`

**Interfaces:**
- Consumes: `EPSILON`(features.py 现有全局,line 17)
- Produces: `calc_crack_spread(df_main, df_leg, ratio=0.655, mode="slope", lookback=20, horizon=24, norm_window=120, max_ffill_gap=4, gain=1.0) -> np.ndarray`,shape `(len(df_main)+horizon,)`,无 NaN。

- [ ] **Step 1: 写失败测试**

`tests/test_crack_spread.py`:
```python
"""crack_spread 协变量单测"""
import unittest
import numpy as np
import pandas as pd
from cascade.features import calc_crack_spread


def _df(dts, closes):
    return pd.DataFrame({"dt": pd.to_datetime(dts), "close_price": closes})


class TestCrackSpread(unittest.TestCase):
    def test_formula_slope(self):
        """spread = TA - 0.655·PX (slope 模式, 有信号)"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.linspace(5000, 5200, 60)   # TA 单调上行
        leg = np.linspace(3000, 3000, 60)    # PX 平
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), ratio=0.655, mode="slope", lookback=20, horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertFalse(np.any(np.isnan(out)))
        # spread 单调上行 -> slope > 0 -> tanh>0 (后半段)
        self.assertTrue(np.mean(out[-24:]) > 0)

    def test_alignment_partial_overlap(self):
        """TA 10 根(含 3 根 PX 无的夜盘), PX 7 根 -> ffill 用 PX 末值"""
        dts_main = pd.date_range("2024-01-01 09:00", periods=10, freq="h")
        # PX 只有前 7 根
        dts_leg = pd.date_range("2024-01-01 09:00", periods=7, freq="h")
        main = np.full(10, 5000.0)
        leg = np.full(7, 3000.0)
        out = calc_crack_spread(_df(dts_main, main), _df(dts_leg, leg), mode="level", horizon=24)
        self.assertEqual(out.shape, (34,))
        # 后 3 根 ffill 用 PX=3000, spread=5000-0.655*3000=3035, 应非零
        self.assertTrue(np.any(out[:10] != 0))

    def test_ffill_gap_exceeds_limit(self):
        """连续 20 根 PX 缺失 (>max_ffill_gap=4) -> 这些 bar 协变量=0"""
        dts = pd.date_range("2024-01-01 09:00", periods=60, freq="h")
        # PX 前 40 根有, 后 20 根缺 (gap=20 > 4)
        dts_leg = pd.date_range("2024-01-01 09:00", periods=40, freq="h")
        main = np.linspace(5000, 5100, 60)   # TA 单调上行, 产生非零 slope
        leg = np.full(40, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts_leg, leg), mode="slope", lookback=20, horizon=24)
        # bar 0-39: PX 真实命中, runs=0
        # bar 40-43: PX 缺失第 1-4 根, runs=1..4 <= max_ffill_gap=4 -> 信任 -> 非零
        # bar 44-59: runs=5..20 > 4 -> 守卫触发 -> 协变量=0
        self.assertTrue(np.all(out[44:60] == 0))
        self.assertTrue(np.all(out[40:44] != 0))   # ffill 信任窗口内 (slope > 0)
        self.assertTrue(np.any(out[20:40] != 0))   # 有 slope 窗口且 PX 命中

    def test_no_leg_returns_zeros(self):
        """df_leg=None -> 全 0, 不 crash"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        out = calc_crack_spread(_df(dts, np.full(60, 5000.0)), None, mode="slope", horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertTrue(np.all(out == 0))

    def test_level_constant_horizon(self):
        """level 模式 horizon=常数 (末值平铺)"""
        dts = pd.date_range("2024-01-01", periods=150, freq="h")
        main = np.linspace(5000, 5100, 150); leg = np.full(150, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="level", horizon=24)
        self.assertAlmostEqual(out[-1], out[-24], places=5)

    def test_slope_decay_horizon(self):
        """slope 模式 horizon 向 0 衰减"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.linspace(5000, 5200, 60); leg = np.full(60, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="slope", horizon=24)
        # 衰减: |out[-1]| < |out[-24]|
        self.assertLess(abs(out[-1]), abs(out[-24]) + 1e-9)

    def test_slope_tanh_not_saturated(self):
        """大斜率下 rolling_std 归一化后 tanh 未全压缩到 ±1"""
        dts = pd.date_range("2024-01-01", periods=150, freq="h")
        main = np.linspace(5000, 6000, 150)  # 大斜率
        leg = np.full(150, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="slope", lookback=20, horizon=24)
        ctx = out[:150]
        # 不应全为 ±1 (有梯度)
        self.assertFalse(np.all(np.abs(ctx[-20:]) >= 0.999))

    def test_zscore_decay_horizon(self):
        """zscore 模式 horizon 向 0 衰减"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.concatenate([np.full(30, 5000.0), np.linspace(5000, 5200, 30)])
        leg = np.full(60, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="zscore", lookback=20, horizon=24)
        self.assertLess(abs(out[-1]), abs(out[-24]) + 1e-9)

    def test_no_nan_output(self):
        """所有模式无 NaN"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.linspace(5000, 5100, 60); leg = np.linspace(3000, 3050, 60)
        for m in ("level", "slope", "zscore"):
            out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode=m, horizon=24)
            self.assertFalse(np.any(np.isnan(out)), f"{m} has NaN")
```

- [ ] **Step 2: 运行确认失败**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread -v`
Expected: FAIL (ImportError: cannot import calc_crack_spread)

- [ ] **Step 3: 实现 calc_crack_spread**

在 `cascade/features.py` 的 `calc_basis_momentum` 函数之后(约 line 700,`calc_vor` 之前)插入:
```python
def calc_crack_spread(df_main: pd.DataFrame, df_leg: pd.DataFrame,
                      ratio: float = 0.655, mode: str = "slope",
                      lookback: int = 20, horizon: int = 24,
                      norm_window: int = 120, max_ffill_gap: int = 4,
                      gain: float = 1.0) -> np.ndarray:
    """
    跨品种裂解价差协变量 (纯函数, 不开 DB)

    spread = df_main.close - ratio * df_leg.close
    mode: level(常数horizon) / slope(decay_0) / zscore(decay_0)
    返回 shape (len(df_main)+horizon,), 无 NaN
    """
    n = len(df_main)
    total = n + horizon
    result = np.zeros(total, dtype=float)

    if df_leg is None or df_leg.empty:
        return result

    # 1. 对齐: df_main['dt'] 主表, left-join df_leg, ffill + 间隙守卫
    main_dt = pd.to_datetime(df_main["dt"])
    leg = df_leg[["dt", "close_price"]].copy()
    leg["dt"] = pd.to_datetime(leg["dt"])
    leg = leg.rename(columns={"close_price": "leg_close"})
    merged = pd.DataFrame({"dt": main_dt}).merge(leg, on="dt", how="left")
    leg_close = merged["leg_close"].astype(float)
    is_real = leg_close.notna()

    # gap_run: 连续缺失长度 (ffill 前统计)
    gap_run = 0
    runs = np.zeros(n, dtype=int)
    for i in range(n):
        gap_run = 0 if is_real.iloc[i] else gap_run + 1
        runs[i] = gap_run

    leg_ffilled = leg_close.ffill()
    # 超 max_ffill_gap 的 bar 不信任 ffill -> 置 NaN
    trusted = pd.Series(runs <= max_ffill_gap, index=leg_ffilled.index)
    leg_final = leg_ffilled.where(trusted)

    main_close = df_main["close_price"].astype(float).values
    # spread_raw: 含 NaN (守卫触发处)
    spread_raw = pd.Series(main_close - ratio * leg_final.values)
    # guard_zero: 守卫触发的 bar (不受信任) -> 协变量强制 0
    guard_zero = (~trusted).values
    # rolling 计算用填充后的连续序列 (避免 NaN 污染 120 期窗口)
    spread = spread_raw.ffill().fillna(0)

    # 2. mode 分支 (rolling 用 spread, 输出用 guard_zero 清零)
    if mode == "level":
        atr = spread.rolling(norm_window, min_periods=2).std() + EPSILON
        normed = (spread / atr).values
        ctx = np.tanh(gain * normed)
        ctx = np.where(guard_zero, 0.0, ctx)   # 守卫 bar 强制 0
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, np.full(horizon, last_val)])  # constant
    elif mode == "slope":
        slopes = np.zeros(n)
        std = spread.rolling(lookback, min_periods=lookback).std().values + EPSILON
        for i in range(lookback - 1, n):
            w = spread.iloc[i - lookback + 1: i + 1].values
            if np.any(np.isnan(w)):
                continue
            x = np.arange(lookback, dtype=float)
            slopes[i] = np.polyfit(x, w, 1)[0] / std[i]
        ctx = np.tanh(gain * slopes)
        ctx = np.where(guard_zero, 0.0, ctx)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
        covariate_full = np.concatenate([ctx, last_val * decay])  # decay_0
    elif mode == "zscore":
        mu = spread.rolling(lookback, min_periods=lookback).mean().values
        sigma = spread.rolling(lookback, min_periods=lookback).std().values + EPSILON
        z = (spread.values - mu) / sigma
        ctx = np.tanh(gain * z)
        ctx = np.where(guard_zero, 0.0, ctx)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
        covariate_full = np.concatenate([ctx, last_val * decay])  # decay_0
    else:
        raise ValueError(f"未知 crack_spread mode: {mode}")

    return np.nan_to_num(covariate_full, nan=0.0, posinf=1.0, neginf=-1.0)
```

- [ ] **Step 4: 运行确认通过**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread -v`
Expected: 9 PASS。若 `test_ffill_gap_exceeds_limit` 失败,检查 `runs` 统计与 `trusted` 掩码。

- [ ] **Step 5: 零回归 - 现有协变量单测不破坏**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_calendar_cyclical -v`
Expected: 现有 7 PASS 不变。

- [ ] **Step 6: Commit**

```bash
git add cascade/features.py tests/test_crack_spread.py
git commit -m "feat(phase8): calc_crack_spread 纯函数 + 三模式 + ffill 间隙守卫"
```

---

## Task 4: 注册到 build_covariate_matrix + build_combo_covariate_matrix

**Files:**
- Modify: `cascade/features.py`(build_covariate_matrix 签名 line 756 + elif 链 line 1091;build_combo 签名 line 1125 + elif 链 line 1271;两处 supported 列表)

**Interfaces:**
- Consumes: Task 2 `get_crack_pair`, Task 3 `calc_crack_spread`
- Produces: `build_covariate_matrix(..., feedstock_cache=None)` / `build_combo_covariate_matrix(..., feedstock_cache=None)` 支持 `covariate_type="crack_spread_{slope,level,zscore}"`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_crack_spread.py`:
```python
class TestBuildCrackSpread(unittest.TestCase):
    def _fake_store(self):
        class _S:
            def get_main_contract_1h(self, limit=1023):
                dts = pd.date_range("2024-01-01", periods=100, freq="h")
                return pd.DataFrame({"dt": dts, "close_price": np.linspace(5000,5100,100),
                                     "open_price": 5000.0, "high_price": 5100.0, "low_price": 4990.0,
                                     "volume": 1000.0, "open_interest": 5000.0, "contract_code": "TA_MAIN"})
        return _S()

    def test_build_single_crack_spread(self):
        from cascade.features import build_covariate_matrix
        dts = pd.date_range("2024-01-01", periods=100, freq="h")
        px_df = pd.DataFrame({"dt": dts, "close_price": np.full(100, 3000.0)})
        res = build_covariate_matrix("ta", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_type="crack_spread_slope",
            feedstock_cache={"px": px_df})
        self.assertIn("crack_spread_slope", res)
        self.assertEqual(len(res["crack_spread_slope"]), 124)

    def test_build_zero_regression_no_cache(self):
        """非 crack_spread 类型, feedstock_cache=None, 不感知"""
        from cascade.features import build_covariate_matrix
        res = build_covariate_matrix("ta", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_type="ccl", feedstock_cache=None)
        self.assertIn("daily_slope", res)
        self.assertIn("ccl_pct", res)

    def test_build_combo_with_crack_spread(self):
        """combo 模式: bb_squeeze + crack_spread_slope 同时返回"""
        from cascade.features import build_combo_covariate_matrix
        dts = pd.date_range("2024-01-01", periods=100, freq="h")
        px_df = pd.DataFrame({"dt": dts, "close_price": np.full(100, 3000.0)})
        res = build_combo_covariate_matrix("ta", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_types=["bb_squeeze", "crack_spread_slope"],
            feedstock_cache={"px": px_df})
        self.assertIn("bb_squeeze", res)
        self.assertIn("crack_spread_slope", res)
        self.assertEqual(len(res["crack_spread_slope"]), 124)

    def test_build_combo_no_pair_returns_zeros(self):
        """combo 模式 + 无配对品种 (SS) -> crack_spread 全 0"""
        from cascade.features import build_combo_covariate_matrix
        res = build_combo_covariate_matrix("ss", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_types=["bb_squeeze", "crack_spread_slope"],
            feedstock_cache=None)
        self.assertIn("crack_spread_slope", res)
        self.assertTrue(np.all(res["crack_spread_slope"] == 0))
```

- [ ] **Step 2: 运行确认失败**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread.TestBuildCrackSpread -v`
Expected: FAIL (crack_spread_slope 未注册 / TypeError: unexpected kwarg feedstock_cache)

- [ ] **Step 3: 修改 build_covariate_matrix 签名 + 注册 elif**

`cascade/features.py:756` 函数签名加参数:
```python
def build_covariate_matrix(
    symbol: str,
    store,
    historical_daily_closes: np.ndarray,
    predicted_daily_closes: np.ndarray,
    daily_dates: pd.DatetimeIndex = None,
    horizon: int = 24,
    limit: int = 480,
    covariate_type: str = "ccl",
    feedstock_cache: Optional[Dict] = None,
) -> dict:
```
(顶部 `from typing import Optional, Dict` 已有 line 13。)

在 `elif covariate_type == "calendar_cyclical":` 分支之前(line ~1091)插入 3 条:
```python
    elif covariate_type in ("crack_spread_slope", "crack_spread_level", "crack_spread_zscore"):
        from config.crack_spread_pairs import get_crack_pair
        _mode = covariate_type.split("_")[-1]   # slope / level / zscore
        pair = get_crack_pair(symbol)
        if pair:
            fs_sym, _ratio = pair
            df_leg = (feedstock_cache or {}).get(fs_sym)
        else:
            df_leg = None
            _ratio = 0.655
        covariate_full = calc_crack_spread(df_1h, df_leg, ratio=_ratio, mode=_mode,
                                           horizon=horizon)
        covariate_name = covariate_type
```

- [ ] **Step 4: 修改 build_combo_covariate_matrix 签名 + 注册 elif**

`cascade/features.py:1125` 签名加 `feedstock_cache: Optional[Dict] = None`。在 combo 的 `elif cov_type == "calendar_cyclical":` 之前(line ~1271)插入:
```python
        elif cov_type in ("crack_spread_slope", "crack_spread_level", "crack_spread_zscore"):
            from config.crack_spread_pairs import get_crack_pair
            _mode = cov_type.split("_")[-1]
            pair = get_crack_pair(symbol)
            if pair:
                fs_sym, _ratio = pair
                df_leg = (feedstock_cache or {}).get(fs_sym)
            else:
                df_leg = None
                _ratio = 0.655
            result[cov_type] = calc_crack_spread(df_1h, df_leg, ratio=_ratio,
                                                 mode=_mode, horizon=horizon)
```

- [ ] **Step 5: 更新 supported 列表**

combo 末尾 `supported = [...]`(line ~1296)追加 `"crack_spread_slope"`, `"crack_spread_level"`, `"crack_spread_zscore"`。

- [ ] **Step 6: 运行确认通过**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread -v`
Expected: 全 PASS(9 + 2 = 11)。

- [ ] **Step 7: Commit**

```bash
git add cascade/features.py tests/test_crack_spread.py
git commit -m "feat(phase8): 注册 crack_spread 三档到 build_*(feedstock_cache 通用 context)"
```

---

## Task 5: hourly_model.predict DI 咽喉点

**Files:**
- Modify: `cascade/hourly_model.py:18`(import) + `:125-151`(协变量构建前注入)

**Interfaces:**
- Consumes: Task 1 `BacktestDataStore`(data 层), Task 2 `get_crack_pair`, Task 4 `feedstock_cache` 参数
- Produces: `hourly_model.predict` 自动为 crack_spread_* 协变量注入 feedstock_df(cutoff 感知)

- [ ] **Step 1: 写失败测试(集成)**

追加到 `tests/test_crack_spread.py`:
```python
class TestHourlyDI(unittest.TestCase):
    def test_needs_feedstock_detection(self):
        from cascade.hourly_model import _needs_feedstock
        self.assertTrue(_needs_feedstock("crack_spread_slope", None))
        self.assertTrue(_needs_feedstock(None, ["bb_squeeze", "crack_spread_level"]))
        self.assertFalse(_needs_feedstock("ccl", None))
        self.assertFalse(_needs_feedstock(None, ["oi", "hurst"]))
```

- [ ] **Step 2: 运行确认失败**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread.TestHourlyDI -v`
Expected: FAIL (cannot import _needs_feedstock)

- [ ] **Step 3: 实现 _needs_feedstock + _fetch_feedstock_1h + 注入**

`cascade/hourly_model.py:18` import 行改为:
```python
from data.data_store import DataStore, BacktestDataStore
```

在 `HourlyModel` 类之前(line ~36)加模块级辅助函数:
```python
def _needs_feedstock(covariate_type: str, covariate_types: list) -> bool:
    """检测是否用到 crack_spread_* 协变量"""
    types = covariate_types or ([covariate_type] if covariate_type else [])
    return any(t and t.startswith("crack_spread_") for t in types)


def _fetch_feedstock_1h(fs_sym: str, target_store, limit: int = 480):
    """cutoff 感知读取 feedstock 1H (防穿越)

    backtest 路径(cutoff 为真实过去日期): 复用 BacktestDataStore 截止语义, 返回截止前 limit 根
    production/scan 路径: 返回最新 limit 根
    """
    cutoff = getattr(target_store, "cutoff_date", None)
    if cutoff and cutoff != "9999-12-31":
        with BacktestDataStore(fs_sym, cutoff) as s:
            df = s.get_main_contract_1h(limit=limit)
    else:
        with DataStore(fs_sym) as s:
            df = s.get_main_contract_1h(limit=limit)
    # 预热不足 warn: norm_window(120) + horizon(24) = 144 为最低有效长度 (不阻断)
    if df.empty or len(df) < 144:
        print(f"  [WARN] feedstock {fs_sym} 数据不足 ({len(df) if not df.empty else 0} < 144), 协变量前段将填 0")
    return df
```

在 `predict()` 内,构建协变量之前(line ~123,`# 2. 构建协变量` 注释处)插入:
```python
        # Phase 8: crack_spread 跨品种 feedstock 注入 (DI 咽喉点)
        feedstock_cache = None
        if _needs_feedstock(covariate_type, covariate_types):
            from config.crack_spread_pairs import get_crack_pair
            pair = get_crack_pair(symbol)
            if pair:
                feedstock_cache = {pair[0]: _fetch_feedstock_1h(pair[0], store)}
            elif verbose:
                print(f"  [WARN] {symbol}: crack_spread 协变量无配对, 退化为零填充")
```

然后修改两处 build_* 调用,加 `feedstock_cache=feedstock_cache`:
- line 131 `build_combo_covariate_matrix(..., covariate_types=covariate_types, feedstock_cache=feedstock_cache)`
- line 143 `build_covariate_matrix(..., covariate_type=single_type, feedstock_cache=feedstock_cache)`

- [ ] **Step 4: 运行确认通过**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread.TestHourlyDI -v`
Expected: 1 PASS

- [ ] **Step 5: 零回归 - features 单测全跑**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread tests.test_calendar_cyclical -v`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add cascade/hourly_model.py tests/test_crack_spread.py
git commit -m "feat(phase8): hourly_model.predict DI 咽喉点 (cutoff 感知 feedstock 注入)"
```

---

## Task 6: covariate_scan 注册 + effective_n

**Files:**
- Modify: `scripts/covariate_scan.py:33`(COVARIATE_TYPES)
- Modify: `scripts/phase4d_parse_results.py:81`(verdict 用 effective_n)

**Interfaces:**
- Consumes: Task 5 DI 自动生效
- Produces: scan 测 3 档 crack_spread;verdict Rule 5 优先用 effective_n

- [ ] **Step 1: COVARIATE_TYPES 追加 3 档**

`scripts/covariate_scan.py:48`(`'calendar_cyclical',` 之后)追加:
```python
    # ── Phase 8 跨品种 crack spread (2026-07-31) ──
    'crack_spread_slope', 'crack_spread_level', 'crack_spread_zscore',
```

- [ ] **Step 2: verdict 优先用 effective_n**

`scripts/phase4d_parse_results.py:81`:
```python
    n = cand["n"]
```
改为:
```python
    # Phase 8: crack_spread 行带 effective_n (feedstock 覆盖内评估点数);
    # 非跨品种行无此字段, fallback 到 cand["n"]
    n = cand.get("effective_n", cand["n"])
```

- [ ] **Step 3: 写 effective_n helper 测试**

追加到 `tests/test_crack_spread.py`:
```python
class TestEffectiveN(unittest.TestCase):
    def test_verdict_uses_effective_n(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from phase4d_parse_results import verdict
        # baseline 失败, cand 精度持平, n=396 但 effective_n=178 -> UNDERPOWERED
        base = {"n": 396, "ev": 0.0, "pf": 1.0, "maxdd": -0.2, "mape": 2.5, "diracc": 50}
        cand = {"n": 396, "effective_n": 178, "ev": 0.0, "pf": 1.0, "maxdd": -0.2, "mape": 2.5, "diracc": 50}
        status, tag, reasons = verdict(base, cand)
        self.assertEqual(status, "UNDERPOWERED")
        self.assertTrue(any("178" in r for r in reasons))
```

- [ ] **Step 4: 运行确认通过**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread.TestEffectiveN -v`
Expected: 1 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/covariate_scan.py scripts/phase4d_parse_results.py tests/test_crack_spread.py
git commit -m "feat(phase8): scan 注册 crack_spread 3 档 + verdict 用 effective_n (Rule 5)"
```

---

## Task 7: 验证 + 三模式 backtest + 报告(不固化)

**Files:**
- 无代码改动(验证 task)。复用现有 `monthly_backtest.py --cov-override` / `--combo` CLI(已存在,line 585-599)。

**Interfaces:**
- Consumes: Task 1-6 全部
- Produces: scan 结果 + 三模式 backtest 结果 + effective n 报告;**不改 prediction_scheme.py**

- [ ] **Step 1: scan 冒烟(7pt 太慢,先用 3pt)**

Run:
```bash
cd D:/FlyBuddy/fm_a
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/covariate_scan.py ta --points 3
```
Expected: exit 0;结果表含 `crack_spread_slope` / `crack_spread_level` / `crack_spread_zscore` 三行 MAE。若三档 MAE 均 999% 或 >> 基线 bb_squeeze 1.5×,人工排查(可能 bug,也可能 TA 上确无 PX-TA 信号,均有效结论)。

- [ ] **Step 2: 全单测回归**

Run: `D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -m unittest tests.test_crack_spread tests.test_calendar_cyclical tests.test_crack_spread_pairs tests.test_future_bar_guard tests.test_vol_threshold_contract -v`
Expected: 全 PASS(零回归)。

- [ ] **Step 3: backtest 三模式矩阵(长任务,用 nohup)**

三模式各跑一次(现有 CLI,无需改 code)。**默认串行**(GPU 不并发,避免 OOM):
```bash
# 串行链 (&&): baseline -> replace -> additive
nohup bash -c '
PY=D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe
$PY scripts/monthly_backtest.py ta > reports/data_ops/p8_baseline.log 2>&1 && \
$PY scripts/monthly_backtest.py ta --cov-override crack_spread_slope > reports/data_ops/p8_replace.log 2>&1 && \
$PY scripts/monthly_backtest.py ta --combo bb_squeeze,crack_spread_slope > reports/data_ops/p8_additive.log 2>&1
' > reports/data_ops/p8_chain.log 2>&1 &
```
> monthly_backtest 支持 `--resume <checkpoint.jsonl>` 断点续跑(见 SOP `docs/long-task-sop.md`)。用 `tail -f reports/data_ops/p8_chain.log` 看进度。

- [ ] **Step 4: 汇总三模式结果,应用 v2 判据**

对每模式结果(从 log 提取 DirAcc/MAPE/EV/PF/MaxDD/n),用 `scripts/phase4d_parse_results.py` 的 verdict 判定。手动补充 effective_n(PX 覆盖内评估点数 ≈ 178):
```bash
D:/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "
from scripts.phase4d_parse_results import verdict
base = {'n':396,'ev':0.120,'pf':1.27,'maxdd':-0.3,'mape':2.26,'diracc':56}
cand = {'n':396,'effective_n':178,'ev':<replace_ev>,'pf':<replace_pf>,'maxdd':<replace_maxdd>,'mape':<replace_mape>,'diracc':<replace_diracc>}
print(verdict(base, cand))
"
```

- [ ] **Step 5: 写结论报告(不固化)**

创建 `reports/research/20260731_phase8a_summary.md`,记录:
- 三模式 scan MAE + backtest 指标
- effective n (~178) 与 underpowered 标记
- v2 判据结论(PASS/FAIL/GREEN-* / UNDERPOWERED)
- **明确:Phase 8a 不固化 prediction_scheme.py**,固化延后至 n≥350 或 Phase 8b
- PX 数据增长预估(约 2 个月达 n≥350)

- [ ] **Step 6: Commit 结论报告**

```bash
git add reports/research/20260731_phase8a_summary.md
git commit -m "data(phase8): PX-TA crack_spread 三模式验证结论 (underpowered, 不固化)"
```

---

## Self-Review

**Spec coverage:**
- §1.1 三模式公式 → Task 3 ✓
- §1.2 left-join+ffill 对齐 → Task 3 ✓
- §1.3 ffill 间隙守卫 → Task 3 ✓
- §1.4 防穿越 cutoff → Task 5 `_fetch_feedstock_1h` ✓
- §2.1 calc_crack_spread + build_* 注册 + feedstock_cache → Task 3, 4 ✓
- §2.2 crack_spread_pairs.py → Task 2 ✓
- §2.3 hourly_model DI + BacktestDataStore 下沉 → Task 1, 5 ✓
- §2.4 scan 注册 + effective_n → Task 6 ✓
- §3 对齐细则 → Task 3 测试覆盖 ✓
- §4.1 测试用例 → Task 3, 4, 5, 6 测试 ✓
- §4.2 scan 冒烟 → Task 7 Step 1 ✓
- §4.3 三模式 backtest + CLI → Task 7 Step 3(用现有 --cov-override/--combo)✓
- §6 验收标准 → Task 7 ✓

**Placeholder scan:** 无 TBD/TODO;所有 code step 含完整代码。

**Type consistency:** `get_crack_pair` 返回 `(feedstock_sym, ratio)` 元组,Task 4/5 用 `pair[0]`/`pair[1]` 一致;`calc_crack_spread` 签名 Task 3 定义与 Task 4 调用一致;`feedstock_cache: Optional[Dict]` Task 4/5 一致;`_needs_feedstock(covariate_type, covariate_types)` Task 5 定义与调用一致。

**修正:** spec §4.3 写 `--covariate`,实际现有 flag 是 `--cov-override`(monthly_backtest.py:585)。本 plan Task 7 用真实 flag 名,无需新增 CLI code。
