"""技术指标计算器

基于 pandas + numpy 纯计算，不依赖第三方 TA 库。
输入: DataFrame[date, open, high, low, close, volume, open_interest]
输出: 同一 DataFrame 增加所有技术指标列
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional


class IndicatorCalculator:
    """技术指标计算器"""

    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """一次性计算所有技术指标"""
        if df.empty or len(df) < 2:
            return df

        df = df.copy()
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        open_ = df["open"].astype(float)
        volume = df["volume"].astype(float)
        oi = df["open_interest"].astype(float) if "open_interest" in df.columns else pd.Series(dtype=float)

        # ── 涨跌幅 ──
        df["change_pct"] = close.pct_change() * 100

        # ── 均线 MA ──
        for p in [5, 10, 20, 60]:
            if len(close) >= p:
                df[f"ma{p}"] = close.rolling(p, min_periods=p).mean()

        # ── 指数均线 EMA ──
        for p in [12, 26]:
            if len(close) >= p:
                df[f"ema{p}"] = close.ewm(span=p, adjust=False).mean()

        # ── MACD ──
        if len(close) >= 26:
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            df["macd_dif"] = ema12 - ema26
            df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
            df["macd_bar"] = 2 * (df["macd_dif"] - df["macd_dea"])

        # ── RSI ──
        for p in [6, 12, 24]:
            if len(close) >= p:
                df[f"rsi{p}"] = self._calc_rsi(close, p)

        # ── KDJ ── [H3 fix] guard on minimum length
        if len(close) >= 9:
            df["kdj_k"], df["kdj_d"], df["kdj_j"] = self._calc_kdj(high, low, close)

        # ── BOLL ──
        if len(close) >= 20:
            df["boll_mid"] = close.rolling(20, min_periods=20).mean()
            std20 = close.rolling(20, min_periods=20).std()
            df["boll_upper"] = df["boll_mid"] + 2 * std20
            df["boll_lower"] = df["boll_mid"] - 2 * std20

        # ── ATR ──
        if len(close) >= 14:
            df["atr14"] = self._calc_atr(high, low, close, 14)

        # ── CCI ──
        if len(close) >= 14:
            df["cci14"] = self._calc_cci(high, low, close, 14)

        # ── 持仓分析 ──
        if not oi.empty and oi.notna().any():
            self._calc_oi_analysis(df, close, oi, volume)
            _calc_ccl(df, close, oi)

        return df

    # ── RSI ──────────────────────────────────────────

    @staticmethod
    def _calc_rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta.clip(upper=0))
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)

    # ── KDJ ──────────────────────────────────────────

    @staticmethod
    def _calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series,
                  n: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        lowest_low = low.rolling(n, min_periods=n).min()
        highest_high = high.rolling(n, min_periods=n).max()
        denom = highest_high - lowest_low
        rsv = (close - lowest_low) / denom.replace(0, np.nan) * 100

        k = pd.Series(index=close.index, dtype=float)
        d = pd.Series(index=close.index, dtype=float)

        k.iloc[n-1] = 50
        d.iloc[n-1] = 50
        for i in range(n, len(close)):
            rsv_val = rsv.iloc[i] if not np.isnan(rsv.iloc[i]) else 50
            k.iloc[i] = 2/3 * k.iloc[i-1] + 1/3 * rsv_val
            d.iloc[i] = 2/3 * d.iloc[i-1] + 1/3 * k.iloc[i]

        j = 3 * k - 2 * d
        return k, d, j

    # ── ATR ──────────────────────────────────────────

    @staticmethod
    def _calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                  period: int) -> pd.Series:
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(period, min_periods=period).mean()

    # ── CCI ──────────────────────────────────────────

    @staticmethod
    def _calc_cci(high: pd.Series, low: pd.Series, close: pd.Series,
                  period: int) -> pd.Series:
        tp = (high + low + close) / 3
        ma_tp = tp.rolling(period, min_periods=period).mean()
        mad = tp.rolling(period, min_periods=period).apply(
            lambda x: np.abs(x - x.mean()).mean(), raw=True
        )
        return (tp - ma_tp) / (0.015 * mad.replace(0, np.nan))

    # ── 持仓分析 ─────────────────────────────────────

    @staticmethod
    def _calc_oi_analysis(df: pd.DataFrame, close: pd.Series,
                          oi: pd.Series, volume: pd.Series):
        """持仓量分析"""
        # 持仓日变化
        df["oi_change"] = oi.diff().astype("Int64")

        # 5日持仓趋势 (线性回归斜率)
        def _slope(series):
            if len(series) < 5 or series.isna().any():
                return np.nan
            x = np.arange(len(series))
            return np.polyfit(x, series.values, 1)[0]

        df["oi_trend_5d"] = oi.rolling(5, min_periods=5).apply(_slope, raw=False)

        # 20日持仓-价格相关性
        df["oi_price_corr"] = oi.rolling(20, min_periods=20).corr(close)

        # 成交量/持仓量比
        df["volume_oi_ratio"] = volume / oi.replace(0, np.nan)

        # 综合持仓信号
        df["oi_signal"] = df.apply(
            lambda row: _classify_oi_signal(row), axis=1
        )


def _classify_oi_signal(row) -> str:
    """根据持仓变化、价格变化等综合判断信号"""
    try:
        oi_chg = row.get("oi_change")
        chg_pct = row.get("change_pct")
        oi_trend = row.get("oi_trend_5d")

        if pd.isna(oi_chg) or pd.isna(chg_pct):
            return "NEUTRAL"

        # 持仓大幅增 + 价格上涨 → 多头强势
        if oi_chg > 0 and oi_trend and oi_trend > 0 and chg_pct > 0.5:
            return "STRONG_BULL"
        # 持仓增 + 价格上涨
        if oi_chg > 0 and chg_pct > 0:
            return "MODERATE_BULL"
        # 持仓增 + 价格下跌 → 空头增仓
        if oi_chg > 0 and chg_pct < -0.5:
            return "STRONG_BEAR"
        if oi_chg > 0 and chg_pct < 0:
            return "MODERATE_BEAR"
        # 持仓减 + 价格上涨 → 空头止损（空头回补）
        if oi_chg < 0 and chg_pct > 0:
            return "BULL_COVER"
        # 持仓减 + 价格下跌 → 多头止损（多头平仓）
        if oi_chg < 0 and chg_pct < 0:
            return "BULL_LIQUID"

        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def _calc_ccl(df: pd.DataFrame, close: pd.Series, oi: pd.Series):
    """
    CCL (持仓变化) 指标

    根据价格变化和持仓量变化判断市场力量:
    - 多头增仓: 价格↑ 持仓↑ → ccl_value = +oi_change (红实心)
    - 空头减仓: 价格↑ 持仓↓ → ccl_value = +|oi_change| (绿空心)
    - 空头增仓: 价格↓ 持仓↑ → ccl_value = -oi_change (绿实心)
    - 多头减仓: 价格↓ 持仓↓ → ccl_value = -|oi_change| (红空心)

    新增列:
    - ccl_value: 有符号的 CCL 值 (正=多头占优, 负=空头占优)
    - ccl_label: 文字标签
    """
    price_chg = close.diff()
    oi_chg = oi.diff()

    ccl_values = []
    ccl_labels = []

    for i in range(len(df)):
        if i == 0 or pd.isna(price_chg.iloc[i]) or pd.isna(oi_chg.iloc[i]):
            ccl_values.append(np.nan)
            ccl_labels.append("")
            continue

        p = price_chg.iloc[i]
        o = oi_chg.iloc[i]
        abs_o = abs(o)

        if p > 0 and o > 0:
            # 多头增仓 — 红实心
            ccl_values.append(abs_o)
            ccl_labels.append("多头增仓")
        elif p > 0 and o < 0:
            # 空头减仓 — 绿空心
            ccl_values.append(abs_o)
            ccl_labels.append("空头减仓")
        elif p < 0 and o > 0:
            # 空头增仓 — 绿实心
            ccl_values.append(-abs_o)
            ccl_labels.append("空头增仓")
        elif p < 0 and o < 0:
            # 多头减仓 — 红空心
            ccl_values.append(-abs_o)
            ccl_labels.append("多头减仓")
        else:
            # 价格不变
            ccl_values.append(0)
            ccl_labels.append("中性")

    df["ccl_value"] = ccl_values
    df["ccl_label"] = ccl_labels
