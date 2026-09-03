"""Phase 5: reversal_shadow_gated 零回归 + 影线门控单测"""
import numpy as np
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cascade.features import calc_reversal_shadow_ratio


def _make_df(o, h, l, c):
    """构造 1H OHLC DataFrame"""
    return pd.DataFrame({
        "open_price": o, "high_price": h, "low_price": l, "close_price": c,
    })


def test_min_shadow_atr_zero_is_no_op():
    """min_shadow_atr=0.0 必须与不传参字节级一致 (零回归铁律)"""
    rng = np.random.default_rng(42)
    n = 200
    o = rng.uniform(100, 120, n)
    c = rng.uniform(100, 120, n)
    h = np.maximum(o, c) + rng.uniform(0, 3, n)
    l = np.minimum(o, c) - rng.uniform(0, 3, n)
    df = _make_df(o, h, l, c)

    out_default = calc_reversal_shadow_ratio(df)
    out_zero = calc_reversal_shadow_ratio(df, min_shadow_atr=0.0)
    assert np.array_equal(out_default, out_zero), "min_shadow_atr=0.0 改变了默认行为"


def test_independent_silencing_long_upper_short_lower():
    """长上影(0.8 ATR)+短下影(0.15 ATR): 短下影归零, 长上影保留, 空头信号不被稀释"""
    # 构造 110 根: 前 100 根平稳, 后 10 根含目标 K 线
    n, w = 110, 20
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h = np.full(n, 100.5)
    l = np.full(n, 99.5)
    # 第 100 根: 长上影 0.8 ATR, 短下影 0.15 ATR (ATR≈1.0 由平稳段决定)
    o[100], c[100], h[100], l[100] = 100.0, 100.0, 100.8, 99.85

    df = _make_df(o, h, l, c)
    out_raw = calc_reversal_shadow_ratio(df, lookback=w, min_shadow_atr=0.0)
    out_gated = calc_reversal_shadow_ratio(df, lookback=w, min_shadow_atr=0.3)
    # 门控后该根信号应更偏空头(上影保留, 下影归零), 即 out_gated[100] < out_raw[100]
    assert out_gated[100] < out_raw[100], f"独立静默未生效: gated={out_gated[100]} raw={out_raw[100]}"


def test_both_small_shadows_zeroed():
    """双小影线(均 < 0.3 ATR): directional_shadow 归零"""
    n, w = 110, 20
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h = np.full(n, 100.1)  # 上影 0.1
    l = np.full(n, 99.9)   # 下影 0.1
    df = _make_df(o, h, l, c)
    out_gated = calc_reversal_shadow_ratio(df, lookback=w, min_shadow_atr=0.3)
    # 全段均为双小影线, 门控后 directional_shadow 全 0, 经 rolling+sigmoid 后稳定在 0 附近
    assert np.all(np.abs(out_gated[w:]) < 0.01), f"双小影线未归零: {out_gated[w:]}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
