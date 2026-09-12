"""
特征工程 — 跨周期协变量构建

核心函数:
- build_daily_slope_covariate(): 防穿越的日线斜率协变量
- calc_ccl_pct(): CCL 变化率 (仓单量价指标, 替代原始 OI)
- build_covariate_matrix(): 完整 XReg 协变量矩阵
- visualize_alignment(): 协变量对齐可视化
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict
from pathlib import Path
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# ── 全局极小值，防除零（quant-trading covariate 修复） ──
EPSILON = 1e-8


def _clip_prediction_drift(
    hist_daily: np.ndarray,
    pred_daily: np.ndarray,
    max_daily_drift_pct: float = 0.05,
) -> np.ndarray:
    """Clip Stage 1 predictions to +/-5% daily drift envelope from last close."""
    last_close = hist_daily[-1]
    t = np.arange(1, len(pred_daily) + 1)
    upper = last_close * (1 + max_daily_drift_pct) ** t
    lower = last_close * (1 - max_daily_drift_pct) ** t
    return np.clip(pred_daily, lower, upper)



def _calc_atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """
    计算 ATR (Average True Range)，纯 numpy 实现

    用于新协变量函数的标准化基准，依赖注入模式：
    - 调用方可预先计算并传入，避免重复计算
    - 未传入时内部调用此函数

    W4 注: 前 period-1 个 bar 的 ATR 用第一个有效值填充 (warmup)，
    非真实 ATR。对近期 bar 的协变量计算影响极小（模型主要关注近期数据）。

    Args:
        df: DataFrame 需含 high_price/low_price/close_price 列
        period: ATR 周期 (默认 14)

    Returns:
        ATR 数组, shape = (len(df),)
    """
    high_col = 'high_price' if 'high_price' in df.columns else 'high'
    low_col = 'low_price' if 'low_price' in df.columns else 'low'
    close_col = 'close_price' if 'close_price' in df.columns else 'close'

    h = df[high_col].values.astype(float)
    l = df[low_col].values.astype(float)
    c = df[close_col].values.astype(float)
    n = len(df)

    if n < 2:
        return np.full(n, 1.0)

    # True Range: max(H-L, |H-prevC|, |L-prevC|)
    prev_c = np.empty(n)
    prev_c[0] = c[0]
    prev_c[1:] = c[:-1]

    tr = np.maximum(h - l,
                    np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))

    # Wilder's smoothed moving average (RMA)
    atr = np.empty(n, dtype=float)
    atr[:period] = np.nan
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        # 前 period-1 个用第一个有效值填充
        atr[:period - 1] = atr[period - 1]

    return atr


def build_daily_slope_covariate(
    historical_daily_closes: np.ndarray,
    predicted_daily_closes: np.ndarray,
    hourly_dates: pd.DatetimeIndex,
    n_context: int,                     # 显式传入 1H context 长度
    daily_dates: pd.DatetimeIndex = None,  # 真实日线日期 (防穿越关键)
    lookback: int = 5,
) -> np.ndarray:
    """
    构建日线斜率协变量 (防穿越版)

    Context 阶段: 用真实日线收盘价的滚动斜率 (无穿越)
    Horizon 阶段: 用预测价格的百分比斜率 (常数)
    对齐方式: 阶梯函数 (forward-fill)
    """
    n_total = len(hourly_dates)
    n_horizon = n_total - n_context
    if n_horizon < 0:
        raise ValueError(f"n_context ({n_context}) 超过总长度 ({n_total})")

    # ── 1. Context 段: 真实历史滚动斜率 ──
    hist = pd.Series(historical_daily_closes, dtype=float)
    n_hist = len(hist)

    daily_slopes = np.full(n_hist, np.nan)
    for i in range(lookback, n_hist):
        window = hist.iloc[i - lookback:i + 1].values
        if np.any(np.isnan(window)) or window[0] == 0:
            continue
        x = np.arange(len(window), dtype=float)
        slope = np.polyfit(x, window, 1)[0]
        daily_slopes[i] = slope / window[0]

    # 构建 context 段: 用真实日线日期映射 (不用合成日期)
    context_slopes = np.zeros(n_context)
    if daily_dates is not None and len(daily_dates) == n_hist:
        # 有真实日期: 精确映射
        slope_by_day = {}
        for i, d in enumerate(daily_dates):
            if i < len(daily_slopes) and not np.isnan(daily_slopes[i]):
                slope_by_day[pd.Timestamp(d).normalize()] = daily_slopes[i]

        context_dates = pd.to_datetime(hourly_dates[:n_context])
        context_dates_day = context_dates.normalize()
        last_valid_slope = 0.0
        for i, d in enumerate(context_dates_day):
            if d in slope_by_day:
                last_valid_slope = slope_by_day[d]
            context_slopes[i] = last_valid_slope
    else:
        # 无真实日期: 简化处理 — 最后 n_context 个日线 slope forward-fill
        valid_slopes = daily_slopes[~np.isnan(daily_slopes)]
        if len(valid_slopes) > 0:
            # 将日线 slope 均匀映射到 context
            step = max(1, len(valid_slopes) // n_context)
            for i in range(n_context):
                idx = min(i * step, len(valid_slopes) - 1)
                context_slopes[i] = valid_slopes[idx]

    # ── 2. Horizon 段: 预测价格的百分比斜率 ──
    pred = np.array(predicted_daily_closes, dtype=float)
    pred_mean = pred.mean()
    if len(pred) >= 2 and pred_mean != 0:
        # 用线性回归而非两点斜率 (更稳健)
        x = np.arange(len(pred), dtype=float)
        reg_slope = np.polyfit(x, pred, 1)[0]
        horizon_slope = reg_slope / pred_mean  # 百分比斜率 (相对均值)
    else:
        horizon_slope = 0.0

    horizon_slopes = np.full(n_horizon, horizon_slope)

    # ── 3. 拼接 ──
    result = np.concatenate([context_slopes, horizon_slopes])
    assert len(result) == n_total, f"Slope length mismatch: {len(result)} != {n_total}"
    return result


def _calc_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    计算 RSI 指标

    Args:
        closes: 收盘价序列
        period: RSI 周期 (默认 14)

    Returns:
        RSI 序列 (0-100 范围)
    """
    n = len(closes)
    rsi = np.full(n, 50.0)  # 默认中性值
    if n < period + 1:
        return rsi

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, n):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - 100 / (1 + rs)

    return np.clip(rsi, 0, 100)


def calc_pca_momentum(closes: np.ndarray,
                      periods: list = None,
                      squash: bool = True) -> np.ndarray:
    """
    多周期 RSI → PCA 降维为一维复合动量

    不同行情下有效 RSI 周期不同 (RSI_5 敏感, RSI_21 稳健)。
    直接全用会导致多重共线性，用 PCA 提取第一主成分 (PC1) 浓缩多时间尺度动量。

    流程:
    1. 计算 RSI(5), RSI(9), RSI(14), RSI(21)
    2. NaN 填充为 50 (中性值)
    3. Z-score 标准化
    4. PCA 提取第一主成分
    5. tanh 压缩到 [-1, 1] (防止极端值破坏模型)

    Args:
        closes: 收盘价序列 (1H 或日线)
        periods: RSI 周期列表 (默认 [5, 9, 14, 21])
        squash: 是否用 tanh 压缩到 [-1, 1]

    Returns:
        一维复合动量序列, shape = closes.shape
    """
    if periods is None:
        periods = [5, 9, 14, 21]

    n = len(closes)

    # 1. 计算多周期 RSI
    rsi_matrix = np.column_stack([_calc_rsi(closes, period=p) for p in periods])

    # 2. NaN → 50 (中性)
    rsi_matrix = np.nan_to_num(rsi_matrix, nan=50.0)

    # 3. Z-score 标准化
    scaler = StandardScaler()
    scaled = scaler.fit_transform(rsi_matrix)

    # 4. PCA 降维至 1 维
    pca = PCA(n_components=1)
    pc1 = pca.fit_transform(scaled).flatten()

    # 5. tanh 压缩到 [-1, 1]
    if squash:
        pc1 = np.tanh(pc1)

    return pc1


def calc_hurst_exponent(returns: np.ndarray, min_scale: int = 5,
                         max_scale_ratio: int = 4) -> float:
    """
    高性能向量化 DFA-1 计算 Hurst 指数

    ⚠️ 输入必须是收益率序列 (returns), 不能是原始价格!
    价格 ≈ 随机游走 (H≈1.5), 收益率才是目标信号。

    使用矩阵运算替代双层 for 循环, 比传统写法快 ~10x。

    Args:
        returns: 收益率序列 (如 pct_change().dropna().values)
        min_scale: 最小窗口 (默认 5, <5 会导致小样本偏差)
        max_scale_ratio: 最大窗口占比 (默认 4, 即 N/4, 学术界铁律)

    Returns:
        Hurst 指数 H (0~1, 0.5=随机游走)
    """
    returns = np.array(returns, dtype=float)
    returns = returns[~np.isnan(returns)]
    N = len(returns)
    max_scale = N // max_scale_ratio

    if N < min_scale * 4 or max_scale < min_scale:
        return 0.5

    # 1. 密集对数分布窗口 (20 个点, 对数坐标均匀)
    scales = np.unique(np.geomspace(min_scale, max_scale, num=20).astype(int))
    if len(scales) < 4:
        return 0.5

    # 2. 累积离差 (Profile)
    Y = np.cumsum(returns - np.mean(returns))

    F = np.zeros(len(scales))

    # 3. 向量化线性去趋势 (矩阵运算替代循环)
    for i, s in enumerate(scales):
        n_seg = N // s
        if n_seg < 1:
            F[i] = np.nan
            continue
        # 截断并重塑为矩阵
        Y_trunc = Y[:n_seg * s].reshape(n_seg, s)
        # 构造自变量矩阵 (s, 2)
        x = np.arange(s, dtype=float)
        X_mat = np.vstack([x, np.ones(s)]).T
        # 伪逆求解所有片段的线性回归 (2, n_seg)
        coeffs = np.linalg.pinv(X_mat) @ Y_trunc.T
        # 趋势线 + 残差
        trend = (X_mat @ coeffs).T
        detrended = Y_trunc - trend
        F[i] = np.sqrt(np.mean(detrended ** 2))

    # 过滤无效值
    valid = F > 0
    if np.sum(valid) < 4:
        return 0.5

    # 4. Log-Log 回归求斜率 (Hurst 指数)
    H = np.polyfit(np.log(scales[valid]), np.log(F[valid]), 1)[0]
    return float(np.clip(H, 0.0, 1.0))


def calc_rolling_hurst(closes: np.ndarray, window: int = 120,
                        step: int = 6) -> np.ndarray:
    """
    滚动 Hurst 指数 (向量化 DFA)

    对每个 bar, 用过去 window 个 bars 的收益率计算 Hurst 指数。
    输出缩放到 [-1, 1]: (H - 0.5) * 2
      +1: 强趋势持续性 (H→1, 适合顺势策略)
       0: 随机游走 (H=0.5, 模型依赖其他特征)
      -1: 强均值回归 (H→0, 适合逆势策略)

    Horizon 填充: 常数 (Hurst 代表长程记忆性, 变化极慢)

    Args:
        closes: 1H 收盘价序列
        window: Hurst 计算窗口 (默认 120 bars ≈ 5 天)
        step: 滚动步长 (每 step bars 重算一次)

    Returns:
        缩放后的 Hurst 序列, shape = closes.shape, 值域 [-1, 1]
    """
    n = len(closes)
    # 计算收益率
    ret = np.diff(closes) / np.where(closes[:-1] != 0, closes[:-1], 1.0)
    n_ret = len(ret)

    raw_hurst = np.full(n_ret, 0.5)

    # 滚动计算: 每 step bars 重算一次, 中间 forward-fill
    for i in range(window, n_ret, step):
        h = calc_hurst_exponent(ret[i - window:i])
        raw_hurst[max(0, i - step + 1):i + 1] = h

    # 填充开头 (前 window 个收益率)
    if window < n_ret:
        first_valid = raw_hurst[window]
        raw_hurst[:window] = first_valid

    # 对齐到收盘价长度 (收益率比价格短 1)
    hurst_full = np.empty(n, dtype=float)
    hurst_full[0] = raw_hurst[0]
    hurst_full[1:] = raw_hurst

    # 缩放到 [-1, 1]
    scaled = (hurst_full - 0.5) * 2.0
    return np.clip(scaled, -1.0, 1.0)


def calc_rolling_hurst_raw(closes: np.ndarray, window: int = 120,
                            step: int = 6) -> np.ndarray:
    """
    滚动 Hurst 指数 (原始 H 值, 不缩放)

    返回 H 原始值 (0~1), 0.5=随机游走, >0.5 趋势, <0.5 均值回归。
    用于 gated_slope 等需要原始 H 值做门控的场景。
    """
    n = len(closes)
    ret = np.diff(closes) / np.where(closes[:-1] != 0, closes[:-1], 1.0)
    n_ret = len(ret)
    raw_hurst = np.full(n_ret, 0.5)

    for i in range(window, n_ret, step):
        h = calc_hurst_exponent(ret[i - window:i])
        raw_hurst[max(0, i - step + 1):i + 1] = h

    if window < n_ret:
        raw_hurst[:window] = raw_hurst[window]

    # 对齐到收盘价长度
    hurst_full = np.empty(n, dtype=float)
    hurst_full[0] = raw_hurst[0]
    hurst_full[1:] = raw_hurst
    return hurst_full


def calc_rsi_state(closes: np.ndarray, rsi_period: int = 14) -> np.ndarray:
    """
    RSI 连续值 → 离散状态降维 (5 状态, 范围 [-2, +2])

    模型不需要知道 RSI 是 72.5 还是 73.1 (全是噪声)，
    只需要知道当前处于"极度超买"还是"震荡区"。

    映射规则:
        +2: RSI > 80  (极度超买, 可能面临急跌回调)
        +1: 70 < RSI ≤ 80  (超买/强势)
         0: 30 ≤ RSI ≤ 70  (震荡/中性, 模型应依赖其他特征)
        -1: 20 ≤ RSI < 30  (超卖/弱势)
        -2: RSI < 20  (极度超卖, 可能面临急涨反弹)

    Args:
        closes: 收盘价序列
        rsi_period: RSI 计算周期 (默认 14)

    Returns:
        离散状态数组, 值域 {-2, -1, 0, +1, +2}
    """
    rsi = _calc_rsi(closes, period=rsi_period)

    state = np.zeros(len(rsi), dtype=float)
    state[rsi > 80] = 2
    state[(rsi > 70) & (rsi <= 80)] = 1
    state[(rsi >= 20) & (rsi < 30)] = -1
    state[rsi < 20] = -2
    # 30 <= rsi <= 70 → 0 (已初始化)
    return state


def _generate_rsi_state_horizon(current_state: float, horizon: int = 24,
                                 decay_step: int = 2) -> np.ndarray:
    """
    Horizon 段 RSI 状态: 向均值衰减 (Mean-Reverting Decay)

    模拟动量消散: [+2, +1, +1, 0, 0, ... 0]
    每 decay_step 个 bar 衰减 1 个强度单位，直至归零。

    Args:
        current_state: 最后一个有效的 RSI 状态值
        horizon: 预测时域长度
        decay_step: 每 N 个 bar 衰减 1 级 (默认 2)

    Returns:
        衰减序列, shape (horizon,)
    """
    future = np.zeros(horizon, dtype=float)
    if current_state == 0:
        return future

    current_val = current_state
    for i in range(horizon):
        future[i] = current_val
        if (i + 1) % decay_step == 0:
            if current_val > 0:
                current_val = max(0, current_val - 1)
            elif current_val < 0:
                current_val = min(0, current_val + 1)
    return future


def calc_daily_rsi_slope(
    historical_daily_closes: np.ndarray,
    predicted_daily_closes: np.ndarray,
    hourly_dates: pd.DatetimeIndex,
    n_context: int,
    daily_dates: pd.DatetimeIndex = None,
    rsi_period: int = 14,
    slope_lookback: int = 5,
) -> np.ndarray:
    """
    日线 RSI 斜率协变量 (防穿越版)

    Context: 仅从历史日线计算 RSI → 零穿越
    Horizon: 从预测日线 + 4×period 预热 计算 RSI → 充分收敛后取值
    防跳变: 若 horizon 与 context 末端差异 > 阈值, 回退到 context 末端值

    Args:
        historical_daily_closes: 历史日线收盘价
        predicted_daily_closes: 预测日线收盘价
        hourly_dates: 1H 时间轴 (context + horizon)
        n_context: context 长度
        daily_dates: 真实日线日期 (防穿越)
        rsi_period: RSI 计算周期
        slope_lookback: RSI 斜率滚动窗口

    Returns:
        RSI 斜率数组, shape (n_context + n_horizon,)
    """
    hist = np.array(historical_daily_closes, dtype=float)
    pred = np.array(predicted_daily_closes, dtype=float)
    n_hist = len(hist)
    n_pred = len(pred)
    n_total = len(hourly_dates)
    n_horizon = n_total - n_context

    # ── Context: 仅用历史数据计算 RSI 斜率 → 零穿越 ──
    hist_rsi = _calc_rsi(hist, period=rsi_period)
    ctx_rsi_slopes = _calc_rsi_slopes(hist_rsi, slope_lookback)

    # Context 段: forward-fill 到 1H 时间轴
    context_slopes = np.zeros(n_context)
    if daily_dates is not None and len(daily_dates) == n_hist:
        slope_by_day = {}
        for i, d in enumerate(daily_dates):
            if i < len(ctx_rsi_slopes):
                slope_by_day[pd.Timestamp(d).normalize()] = ctx_rsi_slopes[i]

        context_dates = pd.to_datetime(hourly_dates[:n_context])
        context_dates_day = context_dates.normalize()
        last_valid = 0.0
        for i, d in enumerate(context_dates_day):
            if d in slope_by_day:
                last_valid = slope_by_day[d]
            context_slopes[i] = last_valid
    else:
        # 简化: 均匀映射
        valid = ctx_rsi_slopes[ctx_rsi_slopes != 0]
        if len(valid) > 0:
            step = max(1, len(valid) // n_context)
            for i in range(n_context):
                idx = min(i * step, len(valid) - 1)
                context_slopes[i] = valid[idx]

    # ── Horizon: 独立计算, 充分预热 ──
    # Wilder EMA 需要 ~4×period 才能收敛
    warmup_size = min(rsi_period * 4 + slope_lookback, len(hist))
    pred_with_warmup = np.concatenate([hist[-warmup_size:], pred])
    pred_rsi = _calc_rsi(pred_with_warmup, period=rsi_period)
    pred_rsi_slopes = _calc_rsi_slopes(pred_rsi, slope_lookback)
    # 截取属于 pred 的部分 (最后 n_pred 个)
    pred_only_slopes = pred_rsi_slopes[-n_pred:] if n_pred > 0 else np.array([0.0])

    valid_pred = pred_only_slopes[pred_only_slopes != 0]
    if len(valid_pred) >= 2:
        horizon_val = float(np.mean(valid_pred[-slope_lookback:]))
    elif len(valid_pred) > 0:
        horizon_val = float(valid_pred[-1])
    else:
        horizon_val = 0.0

    # ── 防跳变: horizon 与 context 末端差异过大时回退 ──
    last_ctx = float(context_slopes[-1]) if n_context > 0 else 0.0
    if abs(horizon_val - last_ctx) > 1.0:  # RSI slope 单位: 点/天
        horizon_val = last_ctx  # 保守策略: 假设趋势延续

    horizon_slopes = np.full(n_horizon, horizon_val)

    result = np.concatenate([context_slopes, horizon_slopes])
    assert len(result) == n_total
    return result


def _calc_rsi_slopes(rsi: np.ndarray, slope_lookback: int = 5) -> np.ndarray:
    """计算 RSI 序列的滚动线性回归斜率"""
    n = len(rsi)
    slopes = np.full(n, 0.0)
    for i in range(slope_lookback, n):
        window = rsi[i - slope_lookback:i + 1]
        if np.any(np.isnan(window)):
            continue
        x = np.arange(len(window), dtype=float)
        slopes[i] = np.polyfit(x, window, 1)[0]
    return slopes


def calc_hourly_slope(
    hourly_closes: np.ndarray,
    window: int = 24,
    clip_range: float = 0.01,
) -> pd.Series:
    """
    1H 价格滚动斜率 (归一化 %/bar)

    对 1H 收盘价计算滚动线性回归斜率，除以价格均值得到百分比斜率。
    窗口默认 24 bars (约 3 个交易日)。

    Args:
        hourly_closes: 1H 收盘价序列
        window: 滚动窗口大小 (bars)
        clip_range: 截断范围 (防极端值)

    Returns:
        归一化斜率序列 (pd.Series)
    """
    closes = pd.Series(hourly_closes, dtype=float)
    n = len(closes)
    slopes = np.zeros(n)

    for i in range(window - 1, n):
        w = closes.iloc[i - window + 1:i + 1].values
        if np.any(np.isnan(w)) or w[0] == 0:
            continue
        x = np.arange(len(w), dtype=float)
        slope = np.polyfit(x, w, 1)[0]
        slopes[i] = slope / np.mean(w)  # 归一化: %/bar

    slopes = np.clip(slopes, -clip_range, clip_range)
    return pd.Series(slopes, index=closes.index)


def calc_oi_pct_change(oi_series: pd.Series, clip_range: float = 0.30) -> pd.Series:
    """
    OI 变化率: diff(OI) / OI.shift(1)

    处理:
    - clip 到 [-clip_range, clip_range] (防极端爆仓/交割异常值)
    - fillna(0)
    """
    oi = oi_series.astype(float)
    oi_pct = oi.diff() / oi.shift(1)
    oi_pct = oi_pct.replace([np.inf, -np.inf], 0)
    oi_pct = oi_pct.clip(lower=-clip_range, upper=clip_range)
    oi_pct = oi_pct.fillna(0)
    return oi_pct


def calc_ccl_pct(ccl_series: pd.Series, oi_series: pd.Series = None,
                 clip_range: float = 0.30) -> pd.Series:
    """
    CCL 变化率: 仓单量价指标归一化

    CCL (ccl_value) 是有符号的持仓变化量:
    - 正值: 多头占优 (多头增仓 + 空头减仓)
    - 负值: 空头占优 (空头增仓 + 多头减仓)

    归一化方式: ccl_value / OI_base (使跨品种可比)
    若无 OI 数据，则用 ccl_value / ccl_value.abs().mean() 归一化

    处理:
    - clip 到 [-clip_range, clip_range] (防极端值)
    - fillna(0)

    Args:
        ccl_series: ccl_value 序列
        oi_series: 持仓量序列 (用于归一化, 可选)
        clip_range: 截断范围 (默认 30%)

    Returns:
        ccl_pct: 归一化后的 CCL 百分比序列
    """
    ccl = ccl_series.astype(float)

    if oi_series is not None:
        oi_base = oi_series.astype(float)
        # 避免除零: 用 rolling mean 平滑 OI 基数
        oi_smooth = oi_base.replace(0, np.nan).rolling(window=5, min_periods=1).mean()
        oi_smooth = oi_smooth.bfill().fillna(1)
        ccl_pct = ccl / oi_smooth
    else:
        # 无 OI 数据: 用均值归一化
        ccl_mean = ccl.abs().mean()
        if ccl_mean > 0:
            ccl_pct = ccl / ccl_mean
        else:
            ccl_pct = ccl.copy()

    ccl_pct = ccl_pct.replace([np.inf, -np.inf], 0)
    ccl_pct = ccl_pct.clip(lower=-clip_range, upper=clip_range)
    ccl_pct = ccl_pct.fillna(0)
    return ccl_pct


def calc_basis_momentum(
    basis: np.ndarray,
    mode: str = "slope",
    window: int = 48,
    clip_range: float = 0.01,
) -> np.ndarray:
    """
    基差动量协变量: 从近远月价差提取趋势/动量信息

    Basis = (Close_近月 - Close_远月) / Close_远月
      > 0: Backwardation (贴水), 现货紧缺
      < 0: Contango (升水), 现货充裕

    两种模式:
    - "slope": 基差的滚动线性回归斜率 (%/bar), 捕捉基差变化速度
      → 基差扩大 = 现货更紧缺, 做多信号增强
    - "zscore": 基差的滚动 Z-score, 捕捉基差极端程度
      → 极端贴水 = 强做多信号, 极端升水 = 强做空信号

    Args:
        basis: 基差序列 (近月-远月)/远月, 1H 频率
        mode: "slope" (基差斜率) 或 "zscore" (基差 Z-score)
        window: 滚动窗口 (默认 48 bars ≈ 2 交易日)
        clip_range: 截断范围 (防极端值)

    Returns:
        基差动量序列, shape = basis.shape
    """
    n = len(basis)
    result = np.zeros(n, dtype=float)

    if mode == "slope":
        # 基差的滚动线性回归斜率
        for i in range(window - 1, n):
            w = basis[i - window + 1:i + 1]
            if np.any(np.isnan(w)):
                continue
            x = np.arange(len(w), dtype=float)
            slope = np.polyfit(x, w, 1)[0]
            # 归一化: 基差本身是小数 (~0.005), 斜率更小
            # 乘以 1000 放大到合理尺度
            result[i] = slope * 1000
        result = np.clip(result, -clip_range * 1000, clip_range * 1000)

    elif mode == "zscore":
        # 滚动 Z-score: (当前基差 - 窗口均值) / 窗口标准差
        for i in range(window - 1, n):
            w = basis[i - window + 1:i + 1]
            if np.any(np.isnan(w)):
                continue
            mu = np.mean(w)
            sigma = np.std(w)
            if sigma > 1e-8:
                result[i] = (basis[i] - mu) / sigma
        result = np.clip(result, -3.0, 3.0)  # Z-score 截断

    return result


def _align_feedstock(df_main: pd.DataFrame, df_leg: pd.DataFrame,
                     max_ffill_gap: int = 4) -> pd.Series:
    """
    将 feedstock (df_leg) 的 close_price 对齐到 df_main 时间轴。

    1. df_main['dt'] 为主表, left-join df_leg
    2. ffill 填充缺失
    3. 连续缺失 > max_ffill_gap 的 bar 置 NaN (不信任 ffill)

    返回: pd.Series, index 同 df_main, 值为对齐后的 feedstock close (含 NaN)
    """
    n = len(df_main)
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
    return leg_final


def calc_crack_spread(df_main: pd.DataFrame, df_leg: pd.DataFrame,
                      ratio: float = 0.655, mode: str = "slope",
                      lookback: int = 20, horizon: int = 24,
                      norm_window: int = 120, max_ffill_gap: int = 4,
                      gain: float = 1.0,
                      half_life: float = 12.0) -> np.ndarray:
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

    # 1. 对齐: 复用 _align_feedstock
    leg_final = _align_feedstock(df_main, df_leg, max_ffill_gap=max_ffill_gap)
    guard_zero = leg_final.isna().values

    main_close = df_main["close_price"].astype(float).values
    # spread_raw: 含 NaN (守卫触发处)
    spread_raw = pd.Series(main_close - ratio * leg_final.values)
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
        decay = _decay_fill(1.0, horizon, half_life=half_life)
        covariate_full = np.concatenate([ctx, last_val * decay])  # decay_0
    elif mode == "zscore":
        mu = spread.rolling(lookback, min_periods=lookback).mean().values
        sigma = spread.rolling(lookback, min_periods=lookback).std().values + EPSILON
        z = (spread.values - mu) / sigma
        ctx = np.tanh(gain * z)
        ctx = np.where(guard_zero, 0.0, ctx)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        decay = _decay_fill(1.0, horizon, half_life=half_life)
        covariate_full = np.concatenate([ctx, last_val * decay])  # decay_0
    else:
        raise ValueError(f"未知 crack_spread mode: {mode}")

    return np.nan_to_num(covariate_full, nan=0.0, posinf=1.0, neginf=-1.0)


def calc_vor(
    volume: np.ndarray,
    open_interest: np.ndarray,
    zscore_window: int = 480,
    clip_range: float = 3.0,
) -> np.ndarray:
    """
    量仓比动量 (Volume-to-OI Ratio, VOR)

    学术支撑: Kang & Yoon (2019) - VOR 是期货市场效率的重要指标
    VOR = Volume / OI → 市场换手率/投机度

    当 VOR 飙升 (Z-score > 2):
    - 趋势末期的 "高潮": 大量短线投机者涌入, 趋势即将反转
    - 或新趋势爆发: 突破性行情引发跟风盘

    处理:
    1. 计算 VOR = Volume / OI
    2. 滚动 Z-score 标准化: (VOR - mean) / std
    3. clip 到 [-clip_range, clip_range]

    Args:
        volume: 1H 成交量序列
        open_interest: 1H 持仓量序列
        zscore_window: 滚动 Z-score 窗口 (默认 480 ≈ 全 context)
        clip_range: Z-score 截断范围

    Returns:
        VOR Z-score 序列, shape = volume.shape
    """
    n = len(volume)
    vor = np.zeros(n, dtype=float)

    # 避免除零: OI=0 或 NaN 时 VOR=0
    valid = (open_interest > 0) & ~np.isnan(open_interest) & ~np.isnan(volume)
    vor[valid] = volume[valid] / open_interest[valid]

    # 滚动 Z-score
    result = np.zeros(n, dtype=float)
    for i in range(zscore_window - 1, n):
        w = vor[i - zscore_window + 1:i + 1]
        if np.any(np.isnan(w)):
            continue
        mu = np.mean(w)
        sigma = np.std(w)
        if sigma > 1e-8:
            result[i] = (vor[i] - mu) / sigma

    # 开头不足窗口的部分: 填充 0 (避免使用全序列统计量引入 look-ahead)
    # result 已初始化为 0，无需额外操作

    return np.clip(result, -clip_range, clip_range)


# ── Phase 15: 新信号维度协变量 ──

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
    return np.nan_to_num(zscore.values, nan=0.0).astype(float)


def _calc_qstick(df_1h: pd.DataFrame, lookback: int = 14) -> np.ndarray:
    """QSTICK: SMA(Close-Open, N) / rolling_std(QSTICK, 60) -> K线多空力量

    输出: 标准化后的多空力量
    """
    close = df_1h["close_price"].values.astype(float)
    open_ = df_1h["open_price"].values.astype(float)
    body = close - open_
    qstick = pd.Series(body).rolling(lookback, min_periods=1).mean().values
    qstick_std = pd.Series(qstick).rolling(60, min_periods=1).std().values
    return np.where(qstick_std > 1e-8, qstick / (qstick_std + 1e-8), 0.0)


def _calc_vwap_deviation(df_1h: pd.DataFrame, lookback: int = 24) -> np.ndarray:
    """VWAP偏离: (Close-VWAP)/VWAP -> 量价公允偏离度

    规则:
    - typical_price = (high + low + close) / 3
    - VWAP = sum(tp * vol, N) / sum(vol, N)
    - deviation = (close - VWAP) / VWAP
    - high/low 任一 NULL -> 该 bar VWAP = NaN -> 0 回退
    - 不用 close 替代 (退化为 close 加权均值, 失去指标含义)

    输出: 原始偏离值, 自然约束在小范围
    """
    close = df_1h["close_price"].values.astype(float)
    high = df_1h["high"].values.astype(float)
    low = df_1h["low"].values.astype(float)
    volume = df_1h["volume"].values.astype(float)

    # high/low 任一 NaN -> typical_price = NaN
    tp = (high + low + close) / 3.0
    tp_vol = pd.Series(tp * volume).rolling(lookback, min_periods=1).sum().values
    vol_sum = pd.Series(volume).rolling(lookback, min_periods=1).sum().values
    vwap = tp_vol / (vol_sum + 1e-8)
    deviation = (close - vwap) / (np.abs(vwap) + 1e-8)
    # NaN -> 0 回退
    return np.nan_to_num(deviation, nan=0.0)


def _calc_stddev(df_1h: pd.DataFrame, lookback: int = 20) -> np.ndarray:
    """StdDev: 收益率波动率相对长期平均的偏离 (修复价格水平伪信号)

    改用 percentage returns 的 std,而非价格 std。
    在非平稳价格序列上,价格 std 会随价格水平放大,引入伪信号。
    收益率 std 是平稳的,仅反映真实波动率变化。

    Args:
        df_1h: 1H K线数据,含 close_price 列
        lookback: 短期波动率窗口 (默认 20)

    输出: 百分比偏离值
    """
    close = df_1h["close_price"].values.astype(float)

    # 改用收益率 (percentage returns)
    returns = np.zeros_like(close)
    returns[1:] = (close[1:] - close[:-1]) / (close[:-1] + EPSILON)

    # 收益率的标准差 (平稳序列)
    stddev = pd.Series(returns).rolling(lookback, min_periods=1).std().values
    stddev_mean = pd.Series(stddev).rolling(60, min_periods=1).mean().values
    return np.where(stddev_mean > 1e-8, stddev / (stddev_mean + EPSILON) - 1.0, 0.0)



def _decay_fill(last_val, horizon, half_life=12.0):
    """均值回复型协变量的指数衰减 horizon 填充.

    last_val * 0.5^(i/half_life) — half_life bar 后信号减半
    """
    decay = np.array([0.5 ** (i / half_life) for i in range(horizon)])
    return last_val * decay


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
    fill_strategy: str = "default",
    half_life: float = 12.0,
    df_1h: Optional[pd.DataFrame] = None,
) -> dict:
    """
    构建完整的 XReg 协变量矩阵

    Args:
        daily_dates: 真实日线日期序列 (防穿越关键)
        limit: 1H 数据读取上限
        covariate_type: "ccl" (仓单量价) 或 "oi" (持仓变化率)
        feedstock_cache: 跨品种原料缓存 {symbol: DataFrame} (crack_spread 用)
        fill_strategy: Horizon 填充策略, "default" (常数填充) 或 "decay" (12-bar 半衰期衰减)
        df_1h: 已读 1H 帧 (ALIGN 路径传入, None 时仍走 get_main_contract_1h)
    """
    # [H-1 fix] Clip prediction drift at the top, before any covariate uses it
    hist_daily_arr = np.array(historical_daily_closes, dtype=float)
    predicted_daily_closes = _clip_prediction_drift(
        hist_daily_arr, np.array(predicted_daily_closes, dtype=float)
    )

    # 读取 1H 数据 (传入则复用, 避免 ALIGN 帧与 MAIN 分叉)
    if df_1h is None:
        df_1h = store.get_main_contract_1h(limit=limit)
    if df_1h.empty:
        raise ValueError(f"{symbol}: 无 1H 数据")

    context_len = len(df_1h)
    total_len = context_len + horizon

    # 构建 1H 时间轴 (context + horizon, 交易时段感知)
    last_dt = pd.to_datetime(df_1h["dt"].iloc[-1])
    from .data_validator import detect_trading_hours, generate_trading_dates
    valid_hours = detect_trading_hours(df_1h)
    future_dates = generate_trading_dates(last_dt, horizon, valid_hours)
    all_dates = pd.DatetimeIndex(list(pd.to_datetime(df_1h["dt"])) + list(future_dates))

    # 1. 日线斜率 (传入显式 n_context 和真实日期)
    slope = build_daily_slope_covariate(
        historical_daily_closes=historical_daily_closes,
        predicted_daily_closes=predicted_daily_closes,
        hourly_dates=all_dates,
        n_context=context_len,
        daily_dates=daily_dates,
    )

    # 2. 第二协变量: 按 covariate_type 选择
    if covariate_type in ("slope_only", "none", "baseline"):
        # Path2 波动熔断：仅保留 daily_slope，无第二协变量
        return {"daily_slope": slope}
    if covariate_type == "oi":
        # OI 变化率
        if "open_interest" in df_1h.columns and df_1h["open_interest"].notna().any():
            oi_pct = calc_oi_pct_change(df_1h["open_interest"])
        else:
            oi_pct = pd.Series(np.zeros(len(df_1h)), index=df_1h.index)
        covariate_full = np.concatenate([oi_pct.values, np.zeros(horizon)])
        covariate_name = "oi_pct_change"
    elif covariate_type == "rsi_slope":
        # 日线 RSI 斜率 (从日线收盘价计算, 防穿越)
        rsi_slope = calc_daily_rsi_slope(
            historical_daily_closes=historical_daily_closes,
            predicted_daily_closes=predicted_daily_closes,
            hourly_dates=all_dates,
            n_context=context_len,
            daily_dates=daily_dates,
        )
        covariate_full = rsi_slope
        covariate_name = "rsi_slope"
    elif covariate_type == "hourly_slope":
        # 1H 价格滚动斜率 (归一化 %/bar)
        hourly_closes = df_1h["close_price"].values.astype(float)
        h_slope = calc_hourly_slope(hourly_closes, window=24)
        # Horizon: 用最后有效斜率 forward-fill (短期动量延续假设)
        last_valid = float(h_slope.iloc[-1]) if len(h_slope) > 0 else 0.0
        covariate_full = np.concatenate([h_slope.values, np.full(horizon, last_valid)])
        covariate_name = "hourly_slope"
    elif covariate_type in ("rsi_state", "rsi6", "rsi12", "rsi24"):
        # 日线 RSI 离散状态降维 (-2~+2) + 向均值衰减
        # 使用日线收盘价计算 RSI，再 forward-fill 到 1H 时间轴
        # rsi_state=RSI(14), rsi6=RSI(6), rsi12=RSI(12), rsi24=RSI(24)
        _rsi_period_map = {"rsi_state": 14, "rsi6": 6, "rsi12": 12, "rsi24": 24}
        _rsi_period = _rsi_period_map[covariate_type]
        hist_daily = np.array(historical_daily_closes, dtype=float)
        pred_daily = np.array(predicted_daily_closes, dtype=float)
        full_daily = np.concatenate([hist_daily, pred_daily])  # already clipped at top [H-1]

        # 计算全序列日线 RSI 状态
        daily_states = calc_rsi_state(full_daily, rsi_period=_rsi_period)
        n_hist = len(hist_daily)
        hist_states = daily_states[:n_hist]
        pred_states = daily_states[n_hist:]

        # 将日线状态 forward-fill 到 1H context
        context_states = np.zeros(context_len, dtype=float)
        if daily_dates is not None and len(daily_dates) == n_hist:
            state_by_day = {}
            for i, d in enumerate(daily_dates):
                if i < len(hist_states):
                    state_by_day[pd.Timestamp(d).normalize()] = hist_states[i]
            ctx_dates = pd.to_datetime(df_1h["dt"])
            ctx_day = ctx_dates.dt.normalize()
            last_s = 0.0
            for i, d in enumerate(ctx_day):
                if d in state_by_day:
                    last_s = state_by_day[d]
                context_states[i] = last_s
        else:
            # 简化: 最后 n_context 个日线状态直接映射
            step = max(1, len(hist_states) // context_len)
            for i in range(context_len):
                idx = min(i * step, len(hist_states) - 1)
                context_states[i] = hist_states[idx]

        # Horizon: 从 context 最后一个状态衰减 (防跳变)
        # 修复: 之前用 valid_pred[-1] 可能取到远期预测中的非零状态，
        # 导致 context→horizon 边界出现 0→-1 的巨大跳变。
        # 正确做法: 从 context 末端连续衰减。
        last_ctx_state = float(context_states[-1]) if len(context_states) > 0 else 0.0
        horizon_states = _generate_rsi_state_horizon(last_ctx_state, horizon, decay_step=2)
        covariate_full = np.concatenate([context_states, horizon_states])
        covariate_name = covariate_type
    elif covariate_type == "pca_momentum":
        # 多周期 RSI → PCA 复合动量 (一维)
        hourly_closes = df_1h["close_price"].values.astype(float)
        ctx_pca = calc_pca_momentum(hourly_closes, periods=[5, 9, 14, 21], squash=True)
        # Horizon: 零衰减 (未来动量未知, 回归中性)
        covariate_full = np.concatenate([ctx_pca, np.zeros(horizon)])
        covariate_name = "pca_momentum"
    elif covariate_type == "hurst":
        # 滚动 Hurst 指数 (meta 协变量: 趋势/均值回归 regime)
        hourly_closes = df_1h["close_price"].values.astype(float)
        hurst = calc_rolling_hurst(hourly_closes, window=120, step=6)
        # Horizon: 常数填充 (假设短期市场分形特征不变)
        last_hurst = float(hurst[-1]) if len(hurst) > 0 else 0.0
        covariate_full = np.concatenate([hurst, np.full(horizon, last_hurst)])
        covariate_name = "hurst"

    elif covariate_type == "gated_slope":
        # Hurst 门控斜率: daily_slope × Hurst 门控因子
        # H > 0.55 (趋势期): 放大斜率信号 (gate > 1)
        # H < 0.45 (震荡期): 缩小斜率信号 (gate < 1)
        # 逻辑: 趋势市场斜率更可靠, 震荡市场斜率噪声大
        hourly_closes = df_1h["close_price"].values.astype(float)

        # 1. 构建标准 daily_slope (context + horizon)
        slope_cov = build_daily_slope_covariate(
            historical_daily_closes=historical_daily_closes,
            predicted_daily_closes=predicted_daily_closes,
            hourly_dates=all_dates,
            n_context=context_len,
            daily_dates=daily_dates,
        )

        # 2. 计算 rolling Hurst (原始值, 用于门控)
        hurst_raw = calc_rolling_hurst_raw(hourly_closes, window=120, step=6)
        # 映射到 1H 时间轴 (hurst_raw 是降采样后的, 需要 forward-fill)
        if len(hurst_raw) < len(hourly_closes):
            step = max(1, len(hourly_closes) // len(hurst_raw))
            hurst_1h = np.repeat(hurst_raw, step)[:len(hourly_closes)]
        else:
            hurst_1h = hurst_raw[:len(hourly_closes)]

        # 3. 门控因子: sigmoid 映射 H → [0.3, 2.0]
        gate = 0.3 + 1.7 * np.clip((hurst_1h - 0.3) / 0.4, 0, 1)
        gate_full = np.concatenate([gate, np.full(horizon, gate[-1])])

        # 4. 门控后的斜率
        covariate_full = slope_cov * gate_full
        covariate_name = "gated_slope"

    elif covariate_type == "regime_gated":
        # Hurst 特征门控: 根据市场状态动态选择底层协变量
        # 这不是一个独立协变量，而是 "协变量的协变量" (meta-covariate)
        #
        # H > 0.55 (趋势期): 使用 PCA 复合动量 (趋势浓缩)
        # H < 0.38 (震荡期): 使用 RSI 状态 (均值回归信号)
        # 0.38~0.55 (中性):  使用 OI (通用基线)
        hourly_closes = df_1h["close_price"].values.astype(float)

        # 计算 rolling Hurst (原始 H 值)
        hurst_raw = calc_rolling_hurst_raw(hourly_closes, window=120, step=6)
        last_h = float(hurst_raw[-1]) if len(hurst_raw) > 0 else 0.5
        hurst_full = np.concatenate([hurst_raw, np.full(horizon, last_h)])

        # 并行计算 3 种底层协变量 (仅 context 段)
        # 1. PCA 动量 (趋势型)
        ctx_pca = calc_pca_momentum(hourly_closes, periods=[5, 9, 14, 21], squash=True)
        pca_full = np.concatenate([ctx_pca, np.zeros(horizon)])

        # 2. RSI 状态 (均值回归型)
        ctx_rsi = calc_rsi_state(hourly_closes, rsi_period=14).astype(float)
        horizon_rsi = _generate_rsi_state_horizon(
            float(ctx_rsi[-1]) if len(ctx_rsi) > 0 else 0.0, horizon, decay_step=2)
        rsi_full = np.concatenate([ctx_rsi, horizon_rsi])

        # 3. OI 变化率 (通用基线)
        if "open_interest" in df_1h.columns and df_1h["open_interest"].notna().any():
            oi_pct = calc_oi_pct_change(df_1h["open_interest"])
        else:
            oi_pct = pd.Series(np.zeros(len(df_1h)), index=df_1h.index)
        oi_full = np.concatenate([oi_pct.values, np.zeros(horizon)])

        # 门控: 基于 H 值对 3 种协变量做加权融合
        # 权重通过 sigmoid-like 函数平滑过渡
        w_trend = np.clip((hurst_full - 0.48) / 0.12, 0, 1)    # H>0.60 → 1.0
        w_revert = np.clip((0.42 - hurst_full) / 0.12, 0, 1)   # H<0.30 → 1.0
        w_base = np.clip(1.0 - w_trend - w_revert, 0, 1)       # 中间地带

        # 归一化权重 (确保和为 1)
        w_sum = w_trend + w_revert + w_base
        w_sum = np.where(w_sum > 0, w_sum, 1.0)
        w_trend = w_trend / w_sum
        w_revert = w_revert / w_sum
        w_base = w_base / w_sum

        covariate_full = w_trend * pca_full + w_revert * rsi_full + w_base * oi_full
        covariate_name = "regime_gated"

    elif covariate_type == "basis_momentum":
        # 滚动基差动量 (Rolling Basis Momentum)
        # 学术支撑: Erb & Harvey (2006) - 期限结构是商品期货最大超额收益来源之一
        # Basis = (Close_近月 - Close_远月) / Close_远月
        # > 0 = Backwardation (现货紧缺), < 0 = Contango (现货充裕)
        basis_df = store.get_basis_1h(limit=limit)
        if basis_df.empty or len(basis_df) < 48:
            # 无基差数据: 回退到零填充
            covariate_full = np.zeros(total_len)
        else:
            basis_arr = basis_df["basis"].values.astype(float)
            # 对齐到 context_len (取最后 context_len 个)
            if len(basis_arr) >= context_len:
                basis_ctx = basis_arr[-context_len:]
            else:
                # 数据不足: 前面补零
                pad = context_len - len(basis_arr)
                basis_ctx = np.concatenate([np.zeros(pad), basis_arr])

            # 计算基差动量 (slope 模式: 基差变化速度)
            ctx_momentum = calc_basis_momentum(basis_ctx, mode="slope", window=48)

            # Horizon: 基差斜率向 0 衰减 (未来基差变化不可预测, 回归中性)
            last_slope = float(ctx_momentum[-1]) if len(ctx_momentum) > 0 else 0.0
            horizon_momentum = _decay_fill(last_slope, horizon, half_life=24.0)

            covariate_full = np.concatenate([ctx_momentum, horizon_momentum])
        covariate_name = "basis_momentum"

    elif covariate_type == "vor":
        # 量仓比动量 (Volume-to-OI Ratio)
        # 学术支撑: Kang & Yoon (2019)
        # VOR = Volume / OI → 市场投机度/换手率
        # Z-score 标准化后作为协变量
        if "volume" in df_1h.columns and "open_interest" in df_1h.columns:
            vol = df_1h["volume"].values.astype(float)
            oi = df_1h["open_interest"].values.astype(float)
            ctx_vor = calc_vor(vol, oi, zscore_window=min(context_len, 480))
        else:
            ctx_vor = np.zeros(context_len)
        # Horizon: 向 0 衰减 (投机量无法维持)
        last_vor = float(ctx_vor[-1]) if len(ctx_vor) > 0 else 0.0
        horizon_vor = _decay_fill(last_vor, horizon, half_life=half_life)
        covariate_full = np.concatenate([ctx_vor, horizon_vor])
        covariate_name = "vor"

    # ── quant-trading 仓库策略协变量 (2026-07-18) ──
    # W1 修复: ao_accel/bb_squeeze/reversal_shadow/sar_dist 使用 _decay_fill 衰减
    # ha_body 是方向型指标，常数保持合理
    elif covariate_type == "ao_accel":
        # Awesome Oscillator 加速度 (动量二阶差分, 均值回复型)
        ctx = calc_ao_acceleration(df_1h)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "ao_accel"

    elif covariate_type == "bb_squeeze":
        # 布林带收缩 (波动率变化率, 均值回复型)
        ctx = calc_bb_squeeze(df_1h)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "bb_squeeze"

    elif covariate_type == "ha_body":
        # Heikin-Ashi 平滑方向动量 (方向型, 常数保持合理)
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_ha_body_direction(df_1h, atr_arr=atr_arr)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, np.full(horizon, last_val)])
        covariate_name = "ha_body"

    elif covariate_type == "reversal_shadow":
        # K线反转影线压力 (均值回复型, 影线压力短期消散)
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "reversal_shadow"

    elif covariate_type == "reversal_shadow_gated_02":
        # Phase 5 scan 三档: min_shadow_atr=0.2
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.2)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "reversal_shadow_gated_02"

    elif covariate_type == "reversal_shadow_gated_03":
        # Phase 5 scan 三档: min_shadow_atr=0.3
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.3)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "reversal_shadow_gated_03"

    elif covariate_type == "reversal_shadow_gated_05":
        # Phase 5 scan 三档: min_shadow_atr=0.5
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.5)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "reversal_shadow_gated_05"

    elif covariate_type == "sar_dist":
        # Parabolic SAR 趋势距离 (均值回复型, 拉伸终将回归)
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_sar_distance(df_1h, atr_arr=atr_arr)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "sar_dist"

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
                                           horizon=horizon, half_life=half_life)
        covariate_name = covariate_type

    elif covariate_type == "calendar_cyclical":
        # Phase 4: 日历周期 4 维正余弦 (拆成 4 个独立的 1D 协变量)
        cyclical_4d = calc_calendar_cyclical(df_1h, horizon)
        # 返回 4 个独立的 1D 协变量，与其他协变量维度一致
        return {
            "daily_slope": slope,
            "calendar_doy_sin": cyclical_4d[:, 0],
            "calendar_doy_cos": cyclical_4d[:, 1],
            "calendar_month_sin": cyclical_4d[:, 2],
            "calendar_month_cos": cyclical_4d[:, 3],
        }

    # ── Phase 15: 新信号维度协变量 ──
    elif covariate_type == "nvi":
        ctx = _calc_nvi(df_1h, lookback=20)
        covariate_full = np.concatenate([ctx, _decay_fill(float(ctx[-1]), horizon)])
        covariate_name = "nvi"

    elif covariate_type == "qstick":
        ctx = _calc_qstick(df_1h, lookback=14)
        covariate_full = np.concatenate([ctx, _decay_fill(float(ctx[-1]), horizon)])
        covariate_name = "qstick"

    elif covariate_type == "vwap_deviation":
        ctx = _calc_vwap_deviation(df_1h, lookback=24)
        last_val = float(ctx[-1])
        if fill_strategy == "decay":
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            covariate_full = np.concatenate([ctx, last_val * decay])
        else:
            covariate_full = np.concatenate([ctx, np.full(horizon, last_val)])
        covariate_name = "vwap_deviation"

    elif covariate_type == "stddev":
        ctx = _calc_stddev(df_1h, lookback=20)
        covariate_full = np.concatenate([ctx, _decay_fill(float(ctx[-1]), horizon)])
        covariate_name = "stddev"

    elif covariate_type == "ccl":
        # CCL 仓差变化率 (此前为 else 默认，提为显式分支以便未知类型显式报错)
        if "ccl_value" in df_1h.columns and df_1h["ccl_value"].notna().any():
            ccl_pct = calc_ccl_pct(df_1h["ccl_value"], df_1h.get("open_interest"))
        elif "open_interest" in df_1h.columns:
            ccl_pct = calc_ccl_pct(
                pd.Series(np.nan, index=df_1h.index),
                df_1h["open_interest"],
            )
        else:
            ccl_pct = pd.Series(np.zeros(len(df_1h)), index=df_1h.index)
        covariate_full = np.concatenate([ccl_pct.values, np.zeros(horizon)])
        covariate_name = "ccl_pct"

    else:
        # 未知协变量显式报错 (此前静默降级为 CCL，会产出错误结果而不报警)
        raise ValueError(
            f"build_covariate_matrix 不支持 covariate_type='{covariate_type}'；"
            f"请在 features.py 注册分派，或在 covariate_pool.json 中归档。"
        )

    assert len(covariate_full) == total_len

    return {
        "daily_slope": slope,
        covariate_name: covariate_full,
    }


def build_combo_covariate_matrix(
    symbol: str,
    store,
    historical_daily_closes: np.ndarray,
    predicted_daily_closes: np.ndarray,
    daily_dates: pd.DatetimeIndex = None,
    horizon: int = 24,
    limit: int = 480,
    covariate_types: list = None,
    feedstock_cache: Optional[Dict] = None,
    fill_strategy: str = "default",
    half_life: float = 12.0,
    df_1h: Optional[pd.DataFrame] = None,
) -> dict:
    """
    正交协变量组合构建

    与 build_covariate_matrix 不同，此函数同时返回多个第二协变量，
    构成 "趋势 + 均值回归 + 资金流 + 状态门控" 的正交组合。

    Args:
        covariate_types: 第二协变量列表, e.g. ["rsi_state", "oi", "hurst"]
                         daily_slope 自动包含，无需指定
        feedstock_cache: 跨品种原料缓存 {symbol: DataFrame} (crack_spread 用)
        fill_strategy: Horizon 填充策略, "default" (常数填充) 或 "decay" (12-bar 半衰期衰减)
        df_1h: 已读 1H 帧 (ALIGN 路径传入, None 时仍走 get_main_contract_1h)

    Returns:
        dict: {"daily_slope": arr, "rsi_state": arr, "oi_pct_change": arr, ...}
    """
    if covariate_types is None:
        covariate_types = ["oi"]

    # [H-1 fix] Clip prediction drift at the top, before any covariate uses it
    hist_daily_arr = np.array(historical_daily_closes, dtype=float)
    predicted_daily_closes = _clip_prediction_drift(
        hist_daily_arr, np.array(predicted_daily_closes, dtype=float)
    )

    # 读取 1H 数据 (传入则复用, 避免 ALIGN 帧与 MAIN 分叉)
    if df_1h is None:
        df_1h = store.get_main_contract_1h(limit=limit)
    if df_1h.empty:
        raise ValueError(f"{symbol}: 无 1H 数据")

    context_len = len(df_1h)
    total_len = context_len + horizon
    hourly_closes = df_1h["close_price"].values.astype(float)

    # 构建 1H 时间轴 (交易时段感知)
    last_dt = pd.to_datetime(df_1h["dt"].iloc[-1])
    from .data_validator import detect_trading_hours, generate_trading_dates
    valid_hours = detect_trading_hours(df_1h)
    future_dates = generate_trading_dates(last_dt, horizon, valid_hours)
    all_dates = pd.DatetimeIndex(list(pd.to_datetime(df_1h["dt"])) + list(future_dates))

    # 1. daily_slope (固定第一协变量)
    slope = build_daily_slope_covariate(
        historical_daily_closes=historical_daily_closes,
        predicted_daily_closes=predicted_daily_closes,
        hourly_dates=all_dates,
        n_context=context_len,
        daily_dates=daily_dates,
    )

    result = {"daily_slope": slope}

    # 2. 逐个构建第二协变量
    for cov_type in covariate_types:
        if cov_type == "oi":
            if "open_interest" in df_1h.columns and df_1h["open_interest"].notna().any():
                oi_pct = calc_oi_pct_change(df_1h["open_interest"])
            else:
                oi_pct = pd.Series(np.zeros(len(df_1h)), index=df_1h.index)
            result["oi_pct_change"] = np.concatenate([oi_pct.values, np.zeros(horizon)])

        elif cov_type == "rsi_state":
            ctx_rsi = calc_rsi_state(hourly_closes, rsi_period=14).astype(float)
            horizon_rsi = _generate_rsi_state_horizon(
                float(ctx_rsi[-1]) if len(ctx_rsi) > 0 else 0.0, horizon, decay_step=2)
            result["rsi_state"] = np.concatenate([ctx_rsi, horizon_rsi])

        elif cov_type in ("rsi6", "rsi12", "rsi24"):
            # combo 路径补齐 (此前仅单路径 build_covariate_matrix 支持)
            _rsi_p = {"rsi6": 6, "rsi12": 12, "rsi24": 24}[cov_type]
            ctx_rsi = calc_rsi_state(hourly_closes, rsi_period=_rsi_p).astype(float)
            horizon_rsi = _generate_rsi_state_horizon(
                float(ctx_rsi[-1]) if len(ctx_rsi) > 0 else 0.0, horizon, decay_step=2)
            result[cov_type] = np.concatenate([ctx_rsi, horizon_rsi])

        elif cov_type == "hurst":
            hurst = calc_rolling_hurst(hourly_closes, window=120, step=6)
            last_h = float(hurst[-1]) if len(hurst) > 0 else 0.0
            result["hurst"] = np.concatenate([hurst, np.full(horizon, last_h)])

        elif cov_type == "hourly_slope":
            h_slope = calc_hourly_slope(hourly_closes, window=24)
            last_s = float(h_slope.iloc[-1]) if len(h_slope) > 0 else 0.0
            result["hourly_slope"] = np.concatenate([h_slope.values, np.full(horizon, last_s)])

        elif cov_type == "rsi_slope":
            rsi_slope = calc_daily_rsi_slope(
                historical_daily_closes=historical_daily_closes,
                predicted_daily_closes=predicted_daily_closes,
                hourly_dates=all_dates,
                n_context=context_len,
                daily_dates=daily_dates,
            )
            result["rsi_slope"] = rsi_slope

        elif cov_type == "pca_momentum":
            ctx_pca = calc_pca_momentum(hourly_closes, periods=[5, 9, 14, 21], squash=True)
            result["pca_momentum"] = np.concatenate([ctx_pca, np.zeros(horizon)])

        # ── W2 修复: 支持 quant-trading 新协变量 ──
        elif cov_type == "ao_accel":
            ctx = calc_ao_acceleration(df_1h)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["ao_accel"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "bb_squeeze":
            ctx = calc_bb_squeeze(df_1h)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["bb_squeeze"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "ha_body":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_ha_body_direction(df_1h, atr_arr=atr_arr)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            result["ha_body"] = np.concatenate([ctx, np.full(horizon, last_val)])

        elif cov_type == "reversal_shadow":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["reversal_shadow"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "reversal_shadow_gated_02":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.2)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["reversal_shadow_gated_02"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "reversal_shadow_gated_03":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.3)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["reversal_shadow_gated_03"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "reversal_shadow_gated_05":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.5)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["reversal_shadow_gated_05"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "sar_dist":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_sar_distance(df_1h, atr_arr=atr_arr)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["sar_dist"] = np.concatenate([ctx, last_val * decay])

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
                                                 mode=_mode, horizon=horizon, half_life=half_life)

        elif cov_type == "calendar_cyclical":
            # Phase 4: combo 模式下拆成 4 个独立的 1D 协变量
            cyclical_4d = calc_calendar_cyclical(df_1h, horizon)
            result["calendar_doy_sin"] = cyclical_4d[:, 0]
            result["calendar_doy_cos"] = cyclical_4d[:, 1]
            result["calendar_month_sin"] = cyclical_4d[:, 2]
            result["calendar_month_cos"] = cyclical_4d[:, 3]

        # ── VOR 协变量支持 (M 豆粕基线) ──
        elif cov_type == "vor":
            if "volume" in df_1h.columns and "open_interest" in df_1h.columns:
                vol = df_1h["volume"].values.astype(float)
                oi = df_1h["open_interest"].values.astype(float)
                ctx_vor = calc_vor(vol, oi, zscore_window=min(context_len, 480))
            else:
                ctx_vor = np.zeros(context_len)
            # Horizon: 向 0 衰减 (投机量无法维持)
            last_vor = float(ctx_vor[-1]) if len(ctx_vor) > 0 else 0.0
            horizon_vor = _decay_fill(last_vor, horizon, half_life=half_life)
            result["vor"] = np.concatenate([ctx_vor, horizon_vor])

        # ── Phase 15: 新信号维度协变量 ──
        elif cov_type == "nvi":
            ctx = _calc_nvi(df_1h, lookback=20)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["nvi"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "qstick":
            ctx = _calc_qstick(df_1h, lookback=14)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["qstick"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "vwap_deviation":
            ctx = _calc_vwap_deviation(df_1h, lookback=24)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            if fill_strategy == "decay":
                decay = _decay_fill(1.0, horizon, half_life=half_life)
                result["vwap_deviation"] = np.concatenate([ctx, last_val * decay])
            else:  # "default" = constant
                result["vwap_deviation"] = np.concatenate([ctx, np.full(horizon, last_val)])

        elif cov_type == "stddev":
            ctx = _calc_stddev(df_1h, lookback=20)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(1.0, horizon, half_life=half_life)
            result["stddev"] = np.concatenate([ctx, last_val * decay])


        elif cov_type == "basis_momentum":
            # 基差动量: 期限结构变化速度
            basis_df = store.get_basis_1h(limit=limit)
            if basis_df.empty or len(basis_df) < 48:
                # 无基差数据: 回退到零填充
                ctx = np.zeros(context_len)
            else:
                basis_arr = basis_df["basis"].values.astype(float)
                if len(basis_arr) >= context_len:
                    basis_ctx = basis_arr[-context_len:]
                else:
                    pad = context_len - len(basis_arr)
                    basis_ctx = np.concatenate([np.zeros(pad), basis_arr])
                ctx = calc_basis_momentum(basis_ctx, mode="slope", window=48)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = _decay_fill(last_val, horizon, half_life=half_life)
            result["basis_momentum"] = np.concatenate([ctx, decay])

        elif cov_type == "ccl":
            # CCL 仓差变化率
            if "ccl_value" in df_1h.columns and df_1h["ccl_value"].notna().any():
                ccl_pct = calc_ccl_pct(df_1h["ccl_value"], df_1h.get("open_interest"))
            elif "open_interest" in df_1h.columns:
                ccl_pct = calc_ccl_pct(
                    pd.Series(np.nan, index=df_1h.index),
                    df_1h["open_interest"],
                )
            else:
                ccl_pct = pd.Series(np.zeros(len(df_1h)), index=df_1h.index)
            result["ccl"] = np.concatenate([ccl_pct.values, np.zeros(horizon)])

        elif cov_type == "gated_slope":
            # Hurst 门控斜率: daily_slope × Hurst 门控因子
            slope_cov = build_daily_slope_covariate(
                historical_daily_closes=historical_daily_closes,
                predicted_daily_closes=predicted_daily_closes,
                hourly_dates=all_dates,
                n_context=context_len,
                daily_dates=daily_dates,
            )
            hurst_raw = calc_rolling_hurst_raw(hourly_closes, window=120, step=6)
            if len(hurst_raw) < len(hourly_closes):
                step = max(1, len(hourly_closes) // len(hurst_raw))
                hurst_1h = np.repeat(hurst_raw, step)[:len(hourly_closes)]
            else:
                hurst_1h = hurst_raw[:len(hourly_closes)]
            gate = 0.3 + 1.7 * np.clip((hurst_1h - 0.3) / 0.4, 0, 1)
            gate_full = np.concatenate([gate, np.full(horizon, gate[-1])])
            result["gated_slope"] = slope_cov * gate_full

        elif cov_type == "regime_gated":
            # 体制自适应融合: 根据 Hurst 动态加权 PCA/RSI/OI
            hurst_raw = calc_rolling_hurst_raw(hourly_closes, window=120, step=6)
            last_h = float(hurst_raw[-1]) if len(hurst_raw) > 0 else 0.5
            hurst_full = np.concatenate([hurst_raw, np.full(horizon, last_h)])
            
            # PCA 动量 (趋势型)
            ctx_pca = calc_pca_momentum(hourly_closes, periods=[5, 9, 14, 21], squash=True)
            pca_full = np.concatenate([ctx_pca, np.zeros(horizon)])
            
            # RSI 状态 (均值回归型)
            ctx_rsi = calc_rsi_state(hourly_closes, rsi_period=14).astype(float)
            horizon_rsi = _generate_rsi_state_horizon(
                float(ctx_rsi[-1]) if len(ctx_rsi) > 0 else 0.0, horizon, decay_step=2)
            rsi_full = np.concatenate([ctx_rsi, horizon_rsi])
            
            # OI 变化率 (通用基线)
            if "open_interest" in df_1h.columns and df_1h["open_interest"].notna().any():
                oi_pct = calc_oi_pct_change(df_1h["open_interest"])
            else:
                oi_pct = pd.Series(np.zeros(len(df_1h)), index=df_1h.index)
            oi_full = np.concatenate([oi_pct.values, np.zeros(horizon)])
            
            # 权重融合
            w_trend = np.clip((hurst_full - 0.48) / 0.12, 0, 1)
            w_revert = np.clip((0.42 - hurst_full) / 0.12, 0, 1)
            w_base = np.clip(1.0 - w_trend - w_revert, 0, 1)
            w_sum = w_trend + w_revert + w_base
            w_sum = np.where(w_sum > 0, w_sum, 1.0)
            result["regime_gated"] = (w_trend/w_sum) * pca_full + (w_revert/w_sum) * rsi_full + (w_base/w_sum) * oi_full

        else:
            supported = ["oi", "rsi_state", "rsi6", "rsi12", "rsi24", "hurst", "hourly_slope", "rsi_slope",
                         "pca_momentum", "ao_accel", "bb_squeeze", "ha_body",
                         "reversal_shadow", "reversal_shadow_gated_02",
                         "reversal_shadow_gated_03", "reversal_shadow_gated_05",
                         "sar_dist", "vor", "calendar_cyclical",
                         "crack_spread_slope", "crack_spread_level", "crack_spread_zscore",
                         "nvi", "qstick", "vwap_deviation", "stddev",
                         "basis_momentum", "ccl", "gated_slope", "regime_gated"]
            if cov_type not in supported:
                raise ValueError(
                    f"combo 不支持协变量类型 '{cov_type}'。"
                    f"支持的类型: {supported}"
                )

    # 长度校验
    for k, v in result.items():
        assert len(v) == total_len, f"combo {k}: len={len(v)} != {total_len}"

    return result


def visualize_alignment(
    hourly_prices: np.ndarray,
    slope_array: np.ndarray,
    ccl_array: np.ndarray,
    context_len: int,
    save_path: Optional[str] = None,
):
    """
    协变量对齐可视化 (Step 3.5 验证用)

    三子图:
    - Y1: 1H 收盘价
    - Y2: daily_slope (阶梯状，验证无穿越)
    - Y3: ccl_pct (CCL 变化率, 平稳序列)
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
        x = np.arange(len(hourly_prices))

        # 分割线
        axvline_kwargs = dict(color='red', linestyle='--', alpha=0.5, linewidth=1)

        # 价格
        axes[0].plot(x, hourly_prices, 'b-', linewidth=0.8, label='1H Close')
        axes[0].axvline(x=context_len, **axvline_kwargs)
        axes[0].set_ylabel('Price')
        axes[0].legend(loc='upper left')
        axes[0].set_title('Covariate Alignment Check')

        # 斜率
        axes[1].plot(x, slope_array * 100, 'g-', linewidth=0.8, label='Daily Slope (%)')
        axes[1].axvline(x=context_len, **axvline_kwargs)
        axes[1].set_ylabel('Slope (%)')
        axes[1].legend(loc='upper left')

        # CCL 变化率
        axes[2].plot(x, ccl_array * 100, 'purple', linewidth=0.8, label='CCL (%)')
        axes[2].axvline(x=context_len, **axvline_kwargs)
        axes[2].set_ylabel('CCL (%)')
        axes[2].set_xlabel('1H Bar Index')
        axes[2].legend(loc='upper left')

        # Context / Horizon 标注
        axes[0].text(context_len * 0.5, axes[0].get_ylim()[1] * 0.95,
                     'CONTEXT (history)', ha='center', fontsize=9, color='blue', alpha=0.5)
        axes[0].text(context_len + (len(x) - context_len) * 0.5, axes[0].get_ylim()[1] * 0.95,
                     'HORIZON (forecast)', ha='center', fontsize=9, color='red', alpha=0.5)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"  对齐图保存: {save_path}")
        else:
            save_path = str(Path(__file__).resolve().parent.parent / "reports" / "covariate_alignment.png")
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"  对齐图保存: {save_path}")

        plt.close()

    except ImportError:
        print("  [WARN] matplotlib 不可用，跳过可视化")


# ══════════════════════════════════════════════════════════════
# quant-trading 仓库策略协变量 (2026-07-18)
# 来源: https://github.com/je-suis-tm/quant-trading
# 工程修复: EPSILON 防除零, NaN 清洗, ATR 依赖注入
# ══════════════════════════════════════════════════════════════

def calc_ao_acceleration(df: pd.DataFrame) -> np.ndarray:
    """
    Awesome Oscillator 加速度协变量 (US-002)

    来源策略: Awesome Oscillator (je-suis-tm/quant-trading)
    原理: AO 的二阶差分，反映动量加速/减速，是预测趋势拐点的关键维度。
    与 daily_slope 正交: slope 是价格一阶差分，这是 (H+L)/2 均线的二阶差分。

    算法:
    1. median_price = (high + low) / 2
    2. AO = SMA(median, 5) - SMA(median, 34)
    3. ao_accel = AO.diff().diff()  (二阶差分)
    4. 自适应缩放: scale = rolling(100, min_periods=2).std() + EPSILON
    5. tanh 压缩到 [-1, 1]，fillna(0) 兜底

    Args:
        df: 含 high_price, low_price 列的 DataFrame

    Returns:
        np.ndarray, shape=(len(df),), 值域 [-1, 1], 无 NaN
    """
    high_col = 'high_price' if 'high_price' in df.columns else 'high'
    low_col = 'low_price' if 'low_price' in df.columns else 'low'

    h = df[high_col].values.astype(float)
    l = df[low_col].values.astype(float)
    median_price = pd.Series((h + l) / 2.0)

    ao = (median_price.rolling(5, min_periods=1).mean()
          - median_price.rolling(34, min_periods=1).mean())
    ao_accel = ao.diff().diff()

    # 自适应缩放: MAD (median absolute deviation) 比 std 对极端值更稳健
    # S1 修复: std 对 spike 敏感，正常信号会被压缩到接近 0
    ao_accel_vals = ao_accel.values
    median_accel = ao_accel.rolling(100, min_periods=2).median()
    mad = (ao_accel - median_accel).abs().rolling(100, min_periods=2).median() + EPSILON
    scale = mad.bfill()  # 处理序列开头 NaN

    signal = (ao_accel / scale).fillna(0.0)
    result = np.tanh(signal.values)
    return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=-1.0)


def calc_bb_squeeze(df: pd.DataFrame, squeeze_gain: float = 5.0) -> np.ndarray:
    """
    布林带收缩协变量 (US-003)

    来源策略: Bollinger Bands Pattern Recognition (je-suis-tm/quant-trading)
    原理: 布林带宽度变化率，波动收缩后往往伴随大幅突破。
    与 OI/hurst 正交: OI 反映资金流，hurst 反映分形特征，
    bb_squeeze 直接反映价格波动状态的"收缩→扩张"转换。

    算法:
    1. mid = SMA(close, 20), std = STD(close, 20)
    2. bb_width = 4 * std / mid  (带宽百分比)
    3. squeeze = bb_width / bb_width.shift(20) - 1  (收缩速度)
    4. tanh(squeeze_gain * squeeze) 压缩放大，EPSILON 防除零

    Args:
        df: 含 close_price 列的 DataFrame
        squeeze_gain: 放大因子 (默认 5.0，S2 参数化)

    Returns:
        np.ndarray, shape=(len(df),), 值域 [-1, 1], 无 NaN
    """
    close_col = 'close_price' if 'close_price' in df.columns else 'close'
    c = df[close_col].values.astype(float)
    cpd = pd.Series(c)

    std = cpd.rolling(20, min_periods=2).std() + EPSILON
    mid = cpd.rolling(20, min_periods=1).mean() + EPSILON
    bb_width = 4.0 * std / mid

    # 收缩速度: 当前宽度 vs 20bar前宽度
    squeeze = bb_width / (bb_width.shift(20) + EPSILON) - 1.0
    signal = (squeeze * squeeze_gain).fillna(0.0)

    result = np.tanh(signal.values)
    return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=-1.0)


def calc_ha_body_direction(df: pd.DataFrame,
                            atr_arr: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Heikin-Ashi 平滑方向动量协变量 (US-004)

    来源策略: Heikin-Ashi (je-suis-tm/quant-trading)
    原理: HA 变换本质上是一个 IIR 低通滤波器，比直接使用收盘价产生的
    方向信号噪音更低。与 daily_slope 的区别: slope 反映价格变化幅度，
    ha_body_direction 反映过滤噪声后的纯净方向。

    性能: 使用纯 numpy 循环（Numba 可选），比 Pandas .iloc 快 100x+。
    工程修复: ATR 依赖注入 + nan_to_num 统一清洗。

    算法:
    1. ha_close = (O + H + L + C) / 4
    2. ha_open[0] = O[0], ha_open[t] = (ha_open[t-1] + ha_close[t-1]) / 2
    3. ha_body = ha_close - ha_open
    4. signal = tanh(ha_body / ATR)

    Args:
        df: 含 open_price/high_price/low_price/close_price 列的 DataFrame
        atr_arr: 预计算 ATR 数组 (可选，传入则避免重复计算)

    Returns:
        np.ndarray, shape=(len(df),), 值域 [-1, 1], 无 NaN
    """
    o_col = 'open_price' if 'open_price' in df.columns else 'open'
    h_col = 'high_price' if 'high_price' in df.columns else 'high'
    l_col = 'low_price' if 'low_price' in df.columns else 'low'
    c_col = 'close_price' if 'close_price' in df.columns else 'close'

    o = df[o_col].values.astype(np.float64)
    h = df[h_col].values.astype(np.float64)
    l = df[l_col].values.astype(np.float64)
    c = df[c_col].values.astype(np.float64)
    n = len(df)

    # HA close: 四价均值
    ha_close = (o + h + l + c) / 4.0

    # HA open: IIR 递推 (纯 numpy，无 Pandas .iloc 循环)
    # W3 TODO: 若未来 limit 增至 1000+ 或批量全品种，可加 @numba.jit(nopython=True) 加速
    ha_open = np.empty(n, dtype=np.float64)
    if n > 0:
        ha_open[0] = o[0]
        for i in range(1, n):
            ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) * 0.5

    ha_body = ha_close - ha_open

    # ATR 依赖注入
    if atr_arr is not None:
        atr_val = atr_arr.astype(np.float64) + EPSILON
    else:
        # 降级: 用 bar range 近似
        atr_val = (h - l) + EPSILON

    signal = ha_body / atr_val
    signal = np.nan_to_num(signal, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.tanh(signal)


def calc_reversal_shadow_ratio(df: pd.DataFrame,
                                atr_arr: Optional[np.ndarray] = None,
                                lookback: int = 20,
                                min_shadow_atr: float = 0.0) -> np.ndarray:
    """
    K线反转影线压力协变量 (US-005)

    来源策略: Shooting Star (je-suis-tm/quant-trading)
    原理: 影线反映多空力量的瞬时博弈: 长下影=买压，长上影=卖压。
    工程修复: 使用 ATR 而非 body 作为分母，十字星(O=C)不再产生 NaN，
    长影线十字星的最强反转信号得以保留。

    Phase 5 增参 (2026-07-29): min_shadow_atr 独立静默滤除无效小影线。
    - 默认 0.0 → 字节级不变 (零回归)
    - >0 → 上/下影线各自独立, 低于 threshold = min_shadow_atr * ATR 的归零
      双向独立滤除: 单向 Pin Bar 的有效影线不被反向噪音稀释

    算法:
    1. upper_shadow = H - max(O, C)
    2. lower_shadow = min(O, C) - L
    3. [Phase 5] 若 min_shadow_atr>0: 上/下影线各自独立静默
    4. directional_shadow = lower_shadow - upper_shadow  (正=买压，负=卖压)
    5. normalized = directional_shadow / ATR  (ATR 分母，非 body)
    6. rolling(lookback).mean() 去噪 → tanh 压缩

    Args:
        df: 含 open_price/high_price/low_price/close_price 列的 DataFrame
        atr_arr: 预计算 ATR 数组 (可选)
        lookback: 滚动平均窗口 (默认 20)
        min_shadow_atr: 最小有效影线长度 (ATR 倍数, 默认 0.0=不过滤)

    Returns:
        np.ndarray, shape=(len(df),), 值域 [-1, 1], 无 NaN
    """
    o_col = 'open_price' if 'open_price' in df.columns else 'open'
    h_col = 'high_price' if 'high_price' in df.columns else 'high'
    l_col = 'low_price' if 'low_price' in df.columns else 'low'
    c_col = 'close_price' if 'close_price' in df.columns else 'close'

    o = df[o_col].values.astype(float)
    h = df[h_col].values.astype(float)
    l = df[l_col].values.astype(float)
    c = df[c_col].values.astype(float)

    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - l

    # [Phase 5] 独立静默: 上/下影线各自滤除无效小影线
    if min_shadow_atr > 0:
        if atr_arr is not None:
            atr_val_for_thr = atr_arr.astype(float) + EPSILON
        else:
            atr_val_for_thr = (h - l) + EPSILON
        threshold = min_shadow_atr * atr_val_for_thr
        upper_shadow = np.where(upper_shadow < threshold, 0.0, upper_shadow)
        lower_shadow = np.where(lower_shadow < threshold, 0.0, lower_shadow)

    # 方向化影线: 正 = 下影(买压)，负 = 上影(卖压)
    directional_shadow = lower_shadow - upper_shadow

    # ATR 分母 (非 body，十字星安全)
    if atr_arr is not None:
        atr_val = atr_arr.astype(float) + EPSILON
    else:
        atr_val = (h - l) + EPSILON

    normalized = directional_shadow / atr_val
    signal = pd.Series(normalized).rolling(lookback, min_periods=1).mean()

    result = np.tanh(signal.fillna(0.0).values)
    return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=-1.0)


def calc_parabolic_sar(df: pd.DataFrame,
                       initial_af: float = 0.02,
                       step_af: float = 0.02,
                       max_af: float = 0.2) -> np.ndarray:
    """
    Parabolic SAR 完整实现 (US-006 内部函数)

    来源策略: Parabolic SAR (je-suis-tm/quant-trading)
    自包含，无外部依赖。

    算法:
    1. 上升趋势: sar[t] = min(sar[t-1] + AF*(EP-sar[t-1]), Low[t-1], Low[t-2])
    2. 下降趋势: sar[t] = max(sar[t-1] + AF*(EP-sar[t-1]), High[t-1], High[t-2])
    3. 新 EP → AF 加速 (min(max_af, AF+step))
    4. 价格穿越 SAR → 趋势反转，AF 重置为 initial_af

    Args:
        df: 含 high_price/low_price/close_price 列的 DataFrame
        initial_af: 初始加速因子 (默认 0.02)
        step_af: 加速步进 (默认 0.02)
        max_af: 加速上限 (默认 0.2)

    Returns:
        SAR 数组, shape=(len(df),)
    """
    h_col = 'high_price' if 'high_price' in df.columns else 'high'
    l_col = 'low_price' if 'low_price' in df.columns else 'low'
    c_col = 'close_price' if 'close_price' in df.columns else 'close'

    h = df[h_col].values.astype(np.float64)
    l = df[l_col].values.astype(np.float64)
    c = df[c_col].values.astype(np.float64)
    n = len(df)

    if n == 0:
        return np.array([], dtype=np.float64)

    sar = np.empty(n, dtype=np.float64)
    # W3 TODO: SAR 递推含趋势分支，若批量全品种可加 @numba.jit 加速
    ep = np.empty(n, dtype=np.float64)
    af = np.empty(n, dtype=np.float64)
    trend = np.empty(n, dtype=np.int8)  # +1=上升, -1=下降

    # 初始化: 用前 min(3, n) 根 bar 的方向判断初始趋势 (S3 修复)
    sar[0] = l[0]
    ep[0] = h[0]
    af[0] = initial_af
    # S3: 不再硬编码 trend[0]=1，用前几根 bar 收盘价方向判断
    init_bars = min(3, n)
    if init_bars >= 2 and c[init_bars - 1] >= c[0]:
        trend[0] = 1   # 前几根收盘走高 → 初始上升
    else:
        trend[0] = -1  # 前几根收盘走低 → 初始下降

    for i in range(1, n):
        # 计算临时 SAR
        temp_sar = sar[i - 1] + af[i - 1] * (ep[i - 1] - sar[i - 1])

        if trend[i - 1] == 1:  # 上升趋势
            # SAR 不能高于前两根 bar 的低点
            prev_low = l[i - 1]
            prev2_low = l[max(0, i - 2)]
            sar[i] = min(temp_sar, prev_low, prev2_low)

            if h[i] > ep[i - 1]:
                ep[i] = h[i]
                af[i] = min(max_af, af[i - 1] + step_af)
            else:
                ep[i] = ep[i - 1]
                af[i] = af[i - 1]

            # 趋势反转检测: 当根 low 跌破 SAR → 转下降
            if l[i] < sar[i]:
                trend[i] = -1
                sar[i] = ep[i - 1]  # SAR 跳到前 EP
                ep[i] = l[i]
                af[i] = initial_af
            else:
                trend[i] = 1
        else:  # 下降趋势
            prev_high = h[i - 1]
            prev2_high = h[max(0, i - 2)]
            sar[i] = max(temp_sar, prev_high, prev2_high)

            if l[i] < ep[i - 1]:
                ep[i] = l[i]
                af[i] = min(max_af, af[i - 1] + step_af)
            else:
                ep[i] = ep[i - 1]
                af[i] = af[i - 1]

            # 趋势反转检测: 当根 high 突破 SAR → 转上升
            if h[i] > sar[i]:
                trend[i] = 1
                sar[i] = ep[i - 1]
                ep[i] = h[i]
                af[i] = initial_af
            else:
                trend[i] = -1

    return sar


def calc_sar_distance(df: pd.DataFrame,
                      atr_arr: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Parabolic SAR 趋势距离协变量 (US-006)

    来源策略: Parabolic SAR (je-suis-tm/quant-trading)
    原理: 价格与 SAR 的距离反映趋势强度和过度拉伸程度。
    - 距离大(正): 上升趋势强劲但可能过度拉伸
    - 距离趋零: 趋势减弱，可能反转
    与 rsi_state 正交: RSI 基于价格位置，sar_distance 基于趋势结构。

    算法:
    1. 计算完整 SAR 序列
    2. distance = (close - SAR) / ATR
    3. tanh(distance / 3) 压缩 (±3 ATR 归一化)

    Args:
        df: 含 high_price/low_price/close_price 列的 DataFrame
        atr_arr: 预计算 ATR 数组 (可选)

    Returns:
        np.ndarray, shape=(len(df),), 值域 [-1, 1], 无 NaN
    """
    c_col = 'close_price' if 'close_price' in df.columns else 'close'
    c = df[c_col].values.astype(np.float64)

    sar = calc_parabolic_sar(df)

    if atr_arr is not None:
        atr_val = atr_arr.astype(np.float64) + EPSILON
    else:
        h_col = 'high_price' if 'high_price' in df.columns else 'high'
        l_col = 'low_price' if 'low_price' in df.columns else 'low'
        atr_val = (df[h_col].values.astype(np.float64)
                   - df[l_col].values.astype(np.float64)) + EPSILON

    distance = (c - sar) / atr_val
    signal = np.nan_to_num(distance / 3.0, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.tanh(signal)


# ──────────────────────────────────────────────────────────────
# Phase 4: 日历周期协变量 (calendar_cyclical)
# ──────────────────────────────────────────────────────────────

def calc_calendar_cyclical(df_1h: pd.DataFrame, horizon: int, valid_hours=None) -> np.ndarray:
    """
    计算日历周期 4 维正余弦编码: [sin(2π·DOY/365.25), cos(...), sin(2π·Month/12), cos(...)]

    Args:
        df_1h: 含时间列('dt'或'date')的 1H K线 DataFrame,长度 = context_bars
        horizon: 未来预测步数
        valid_hours: 合法交易时段列表 (整数小时). None 时自动从数据检测。

    Returns:
        np.ndarray: shape (len(df_1h) + horizon, 4), dtype=float32
    """
    # 1) 兼容时间列名
    dt_col = 'dt' if 'dt' in df_1h.columns else 'date'
    dt_idx = pd.DatetimeIndex(df_1h[dt_col])

    # 2) Context 部分: 历史每小时的 4 维编码
    doy = dt_idx.dayofyear.values          # 1..366
    month = dt_idx.month.values            # 1..12

    ctx_4d = np.column_stack([
        np.sin(2 * np.pi * doy / 365.25),
        np.cos(2 * np.pi * doy / 365.25),
        np.sin(2 * np.pi * month / 12),
        np.cos(2 * np.pi * month / 12),
    ]).astype(np.float32)

    # 3) Horizon 部分: 交易时段感知的未来时间戳生成
    last_dt = dt_idx[-1]

    if valid_hours is None:
        from .data_validator import detect_trading_hours
        valid_hours = detect_trading_hours(df_1h)

    if not valid_hours:
        # 最终回退: 简单 1h 间隔
        future_dts = pd.date_range(
            start=last_dt + pd.Timedelta(hours=1),
            periods=horizon,
            freq='h'
        )
    else:
        # 只在合法交易时段生成未来 bar
        valid_set = set(int(h) for h in valid_hours)
        future_list = []
        current = last_dt + pd.Timedelta(hours=1)
        current = current.replace(minute=0, second=0, microsecond=0)
        max_iter = horizon * 48
        while len(future_list) < horizon and max_iter > 0:
            max_iter -= 1
            if current.weekday() < 5 and current.hour in valid_set:
                future_list.append(current)
            current += pd.Timedelta(hours=1)
        future_dts = pd.DatetimeIndex(future_list)

    future_doy = future_dts.dayofyear.values
    future_month = future_dts.month.values

    horiz_4d = np.column_stack([
        np.sin(2 * np.pi * future_doy / 365.25),
        np.cos(2 * np.pi * future_doy / 365.25),
        np.sin(2 * np.pi * future_month / 12),
        np.cos(2 * np.pi * future_month / 12),
    ]).astype(np.float32)

    # 4) 拼接并返回
    return np.vstack([ctx_4d, horiz_4d])
