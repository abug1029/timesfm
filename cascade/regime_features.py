"""
Regime-specific rolling feature extraction for market state classification.

Extracts time-varying features that characterize different market regimes:
- VOR (Volume-OI Ratio) skewness
- OI volatility Z-score
- Rolling Hurst exponent
- Rolling ADX
- Volatility cone position
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
from scipy import stats

# 特征契约版本：训练 / 实时 / 校验必须一致；变更时 bump 并重训 pkl
FEATURE_VERSION = "1h_v1"
FEATURE_VERSION_V2 = "1h_v2"  # P1.3.d 路径型扩展特征
DEFAULT_REGIME_WINDOWS = [40, 60]
EXPECTED_FEATURE_COLUMNS = [
    "vor_skew_40", "oi_vol_zscore_40", "rolling_hurst_40", "rolling_adx_40",
    "vol_cone_position_40",
    "vor_skew_60", "oi_vol_zscore_60", "rolling_hurst_60", "rolling_adx_60",
    "vol_cone_position_60",
]
# v2 = v1 + 路径/微观结构特征
EXPECTED_FEATURE_COLUMNS_V2 = EXPECTED_FEATURE_COLUMNS + [
    "ret_skew_40", "ret_skew_60",
    "close_loc_40", "close_loc_60",
    "intraday_rv_40", "intraday_rv_60",
    "hl_range_40", "hl_range_60",
]

# 1H DataFrame 列名别名（DB → 特征提取）
_OHLCV_RENAME = {
    "open_price": "open",
    "high_price": "high",
    "low_price": "low",
    "close_price": "close",
}


def calc_vor(volume: pd.Series, open_interest: pd.Series) -> pd.Series:
    """
    Calculate Volume-OI Ratio (VOR).

    VOR = Volume / Open Interest

    Args:
        volume: Trading volume series
        open_interest: Open interest series

    Returns:
        VOR series
    """
    return volume / open_interest.replace(0, np.nan)


def calc_vor_skewness(vor: pd.Series, window: int) -> pd.Series:
    """
    Calculate rolling skewness of VOR.

    High positive skewness indicates occasional volume spikes (breakout regime).
    Negative skewness suggests consistent volume distribution (range regime).

    Args:
        vor: Volume-OI ratio series
        window: Rolling window size

    Returns:
        Rolling skewness series
    """
    return vor.rolling(window=window).skew()


def calc_oi_volatility_zscore(oi: pd.Series, window: int) -> pd.Series:
    """
    Calculate rolling Z-score of OI changes.

    Identifies unusual OI movements that may signal regime transitions.

    Args:
        oi: Open interest series
        window: Rolling window for mean/std calculation

    Returns:
        Z-score series
    """
    oi_change = oi.pct_change()
    rolling_mean = oi_change.rolling(window=window).mean()
    rolling_std = oi_change.rolling(window=window).std()

    zscore = (oi_change - rolling_mean) / rolling_std.replace(0, np.nan)
    return zscore


def calc_rolling_hurst(prices: pd.Series, window: int) -> pd.Series:
    """
    Calculate rolling Hurst exponent using R/S analysis.

    Hurst > 0.5: Trending regime (persistent)
    Hurst < 0.5: Mean-reverting regime (anti-persistent)
    Hurst ≈ 0.5: Random walk

    Args:
        prices: Price series
        window: Rolling window size

    Returns:
        Rolling Hurst exponent series
    """
    def hurst_rs(series):
        """Calculate Hurst exponent for a single series using R/S method."""
        series = series.dropna()
        if len(series) < 20:
            return np.nan

        # Calculate returns
        returns = np.diff(np.log(series))
        n = len(returns)

        # Try different sub-period lengths
        max_k = n // 2
        ks = np.unique(np.logspace(np.log10(10), np.log10(max_k), 20).astype(int))

        rs_values = []
        for k in ks:
            if k > n // 2:
                continue

            # Split into non-overlapping sub-periods
            n_sub = n // k
            rs_sub = []

            for i in range(n_sub):
                sub = returns[i*k:(i+1)*k]
                mean_sub = np.mean(sub)

                # Cumulative deviation
                cum_dev = np.cumsum(sub - mean_sub)

                # Range
                R = np.max(cum_dev) - np.min(cum_dev)

                # Standard deviation
                S = np.std(sub, ddof=1)

                if S > 0:
                    rs_sub.append(R / S)

            if rs_sub:
                rs_values.append((np.log(k), np.log(np.mean(rs_sub))))

        if len(rs_values) < 2:
            return np.nan

        # Linear regression to find Hurst exponent
        x, y = zip(*rs_values)
        slope, _, _, _, _ = stats.linregress(x, y)

        return slope

    # Calculate rolling Hurst with reduced frequency (every 5 bars) for performance
    # Full calculation every 5 bars, forward-fill intermediate values
    hurst_values = np.full(len(prices), np.nan)
    step = 5  # Calculate every 5 bars instead of every bar

    for i in range(window, len(prices), step):
        window_data = prices.iloc[i-window:i]
        hurst_values[i] = hurst_rs(window_data)

    # Forward-fill intermediate values
    result = pd.Series(hurst_values, index=prices.index)
    result = result.ffill()

    return result


def calc_rolling_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                     window: int = 14) -> pd.Series:
    """
    Calculate rolling Average Directional Index (ADX).

    ADX > 25: Strong trend
    ADX < 20: Weak trend / ranging

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        window: ADX calculation window

    Returns:
        Rolling ADX series
    """
    # Calculate True Range (TR)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate Directional Movement (DM)
    plus_dm = high.diff()
    minus_dm = -low.diff()

    # Keep only positive values
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    # Remove cases where +DM < -DM and vice versa
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0

    # Smooth using Wilder's method (EWM with alpha=1/window)
    atr = tr.ewm(alpha=1/window, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/window, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1/window, adjust=False).mean() / atr.replace(0, np.nan))

    # Calculate DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1/window, adjust=False).mean()

    return adx


def calc_volatility_cone_position(returns: pd.Series, window: int) -> pd.Series:
    """
    Calculate current volatility position within historical cone.

    Position = 0: At historical minimum volatility
    Position = 1: At historical maximum volatility

    Helps identify if current volatility is extreme relative to history.

    Args:
        returns: Return series
        window: Rolling window size

    Returns:
        Volatility position series (0-1)
    """
    # Calculate rolling volatility (annualized)
    rolling_vol = returns.rolling(window=window).std() * np.sqrt(252)

    # Calculate percentile rank within rolling history
    def percentile_rank(series, current_value):
        valid = series.dropna()
        if len(valid) == 0:
            return np.nan
        # Fix: Use <= instead of < to handle equal values correctly
        return (valid <= current_value).sum() / len(valid)

    positions = []
    for i in range(len(rolling_vol)):
        if i < window * 2:  # Need enough history
            positions.append(np.nan)
        else:
            # Look back 4x window for historical context
            history_start = max(0, i - window * 4)
            history = rolling_vol.iloc[history_start:i]
            current = rolling_vol.iloc[i]
            positions.append(percentile_rank(history, current))

    return pd.Series(positions, index=returns.index)


def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将 DB 风格列名规范为 open/high/low/close。"""
    rename = {k: v for k, v in _OHLCV_RENAME.items() if k in df.columns and v not in df.columns}
    out = df.rename(columns=rename) if rename else df
    required = ["open", "high", "low", "close", "volume", "open_interest"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        # high/low 缺失时用 close 填充（部分 1H 表可能无 high/low）
        if "close" in out.columns:
            for c in ("open", "high", "low"):
                if c not in out.columns:
                    out = out.copy()
                    out[c] = out["close"]
        missing = [c for c in required if c not in out.columns]
        if missing:
            raise ValueError(f"1H OHLCV 缺列: {missing}")
    return out


def extract_path_features(df: pd.DataFrame, windows: List[int] = None) -> pd.DataFrame:
    """
    P1.3.d 路径型特征：偏度、收盘位置、实现波动、高低波幅。

    全部 lookback-only（rolling 只用过去窗口）。
    """
    if windows is None:
        windows = list(DEFAULT_REGIME_WINDOWS)
    out = pd.DataFrame(index=df.index)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    rets = close.pct_change()
    # 收盘在当根 bar 的相对位置 (close-low)/(high-low)
    bar_range = (high - low).replace(0, np.nan)
    close_loc = (close - low) / bar_range
    hl_range_pct = bar_range / close.replace(0, np.nan)

    for w in windows:
        out[f"ret_skew_{w}"] = rets.rolling(w, min_periods=max(10, w // 2)).skew()
        out[f"close_loc_{w}"] = close_loc.rolling(w, min_periods=max(10, w // 2)).mean()
        out[f"intraday_rv_{w}"] = rets.rolling(w, min_periods=max(10, w // 2)).std()
        out[f"hl_range_{w}"] = hl_range_pct.rolling(w, min_periods=max(10, w // 2)).mean()
    return out


def extract_1h_regime_features(
    df_1h: pd.DataFrame,
    windows: Optional[List[int]] = None,
    version: str = FEATURE_VERSION,
) -> pd.DataFrame:
    """
    从 1H K 线提取 Regime 特征（与实时分类器同一契约）。

    Args:
        df_1h: 1H OHLCV（支持 open_price/close_price 或 open/close）
        windows: 滚动窗口，默认 [40, 60]
        version: "1h_v1" 基础 10 维；"1h_v2" 追加路径特征

    Returns:
        特征 DataFrame
    """
    if windows is None:
        windows = list(DEFAULT_REGIME_WINDOWS)
    df = _normalize_ohlcv_columns(df_1h)
    base = extract_rolling_features(df, windows=windows)
    if version in (FEATURE_VERSION_V2, "1h_v2", "v2"):
        path = extract_path_features(df, windows=windows)
        out = pd.concat([base, path], axis=1)
        # 保证列序
        cols = [c for c in EXPECTED_FEATURE_COLUMNS_V2 if c in out.columns]
        return out[cols]
    return base


def extract_rolling_features(df: pd.DataFrame, windows: List[int] = [40, 60]) -> pd.DataFrame:
    """
    Extract all rolling features for regime classification.

    Args:
        df: DataFrame with columns: open, high, low, close, volume, open_interest
        windows: List of window sizes (default: [40, 60] for short/long term)
                 Note: Hurst calculation requires window >= 40 for reliable R/S analysis

    Returns:
        DataFrame with rolling features
    """
    features = pd.DataFrame(index=df.index)

    # Calculate base series
    returns = df['close'].pct_change()
    vor = calc_vor(df['volume'], df['open_interest'])

    # Calculate ADX once with fixed 14-period window (optimization: avoid recalculation)
    rolling_adx_14 = calc_rolling_adx(df['high'], df['low'], df['close'], 14)

    # Extract features for each window
    for window in windows:
        # VOR skewness
        vor_skew = calc_vor_skewness(vor, window)
        features[f'vor_skew_{window}'] = vor_skew

        # OI volatility Z-score
        oi_vol_z = calc_oi_volatility_zscore(df['open_interest'], window)
        features[f'oi_vol_zscore_{window}'] = oi_vol_z

        # Rolling Hurst
        rolling_h = calc_rolling_hurst(df['close'], window)
        features[f'rolling_hurst_{window}'] = rolling_h

        # Rolling ADX - apply different smoothing window to pre-calculated ADX
        features[f'rolling_adx_{window}'] = rolling_adx_14.rolling(window=window).mean()

        # Volatility cone position
        vol_pos = calc_volatility_cone_position(returns, window)
        features[f'vol_cone_position_{window}'] = vol_pos

    # Forward fill NaN values from warmup period
    features = features.ffill()

    return features


def summarize_feature_distributions(features: pd.DataFrame) -> pd.DataFrame:
    """
    Generate summary statistics for each feature.

    Args:
        features: DataFrame from extract_rolling_features

    Returns:
        Summary statistics DataFrame
    """
    summary = pd.DataFrame({
        'mean': features.mean(),
        'std': features.std(),
        'min': features.min(),
        '25%': features.quantile(0.25),
        '50%': features.quantile(0.50),
        '75%': features.quantile(0.75),
        'max': features.max(),
        'nan_count': features.isna().sum()
    })

    return summary
