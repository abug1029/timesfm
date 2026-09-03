"""
CCL 异动预警模块

基于 CCL (仓单量价) 指标检测市场异动，提供 5 种信号:
1. 单 bar 异常放量 (分位数突破 P95/P99)
2. 连续同向 CCL (趋势强化/过热)
3. CCL 累积偏移 (单边力量堆积)
4. 量价背离 (价格极值 vs CCL 方向矛盾)
5. CCL 翻转 (多空 regime 切换)

综合预警等级: NORMAL / WATCH / WARNING / CRITICAL
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class CCLSignal:
    """单个异动信号"""
    signal_type: str       # single_bar / consecutive / cumulative / divergence / regime
    level: str             # WATCH / WARNING / CRITICAL
    description: str       # 人可读描述
    detail: str = ""       # 补充细节
    value: float = 0.0     # 量化值 (用于排序)


@dataclass
class CCLAlert:
    """综合预警结果"""
    symbol: str
    overall_level: str = "NORMAL"   # NORMAL / WATCH / WARNING / CRITICAL
    signals: List[CCLSignal] = field(default_factory=list)
    summary: str = ""

    # 阈值信息 (供报告展示)
    p95: float = 0.0
    p99: float = 0.0
    latest_ccl: float = 0.0
    latest_label: str = ""

    @property
    def emoji(self) -> str:
        return {
            "NORMAL": "🟢", "WATCH": "🟡",
            "WARNING": "🟠", "CRITICAL": "🔴"
        }.get(self.overall_level, "⚪")

    def format_report(self) -> str:
        """生成报告段落 (Markdown)"""
        lines = []
        lines.append(f"### CCL 异动预警 {self.emoji} {self.overall_level}")
        lines.append("")
        lines.append(f"当前: {self.latest_label} (CCL={self.latest_ccl:+,.0f})")
        lines.append(f"阈值: P95={self.p95:,.0f} / P99={self.p99:,.0f}")
        lines.append("")

        if not self.signals:
            lines.append("无异动信号，市场状态正常。")
            return "\n".join(lines)

        lines.append("| 信号 | 等级 | 描述 |")
        lines.append("|------|:----:|------|")
        for s in self.signals:
            emoji = {"WATCH": "🟡", "WARNING": "🟠", "CRITICAL": "🔴"}.get(s.level, "⚪")
            lines.append(f"| {s.signal_type} | {emoji} {s.level} | {s.description} |")

        if self.summary:
            lines.append("")
            lines.append(f"**综合判断**: {self.summary}")

        return "\n".join(lines)


# ── 阈值计算 ─────────────────────────────────────────────

def calc_ccl_percentiles(symbol: str, store, source: str = "1h") -> Tuple[float, float, float]:
    """计算品种 CCL 分位数阈值

    Args:
        symbol: 品种代码
        store: DataStore 实例
        source: "1h" 或 "daily"

    Returns:
        (p50, p95, p99) 基于 |ccl_value| 的绝对值分位数
    """
    table = "kline_1h" if source == "1h" else "main_continuous_1d"
    if source == "1h":
        contract = f"{symbol.upper()}_MAIN"
        rows = store.conn.execute(
            f"SELECT ABS(ccl_value) FROM {table} "
            f"WHERE ccl_value IS NOT NULL AND contract_code = ?",
            (contract,)
        ).fetchall()
    else:
        rows = store.conn.execute(
            f"SELECT ABS(ccl_value) FROM {table} "
            f"WHERE ccl_value IS NOT NULL"
        ).fetchall()

    if not rows:
        return 0.0, 0.0, 0.0

    vals = sorted([r[0] for r in rows])
    n = len(vals)
    p50 = vals[n // 2]
    p95 = vals[int(n * 0.95)]
    p99 = vals[int(n * 0.99)]
    return p50, p95, p99


# ── 信号检测 ─────────────────────────────────────────────

def _detect_single_bar(ccl_values: np.ndarray, p95: float, p99: float,
                       lookback: int = 6) -> List[CCLSignal]:
    """信号 1: 单 bar 异常放量

    检查最近 lookback 根 bar 是否有 |CCL| > P95/P99
    """
    signals = []
    recent = ccl_values[-lookback:]
    abs_recent = np.abs(recent)

    for i, (val, abs_val) in enumerate(zip(recent, abs_recent)):
        bars_ago = lookback - 1 - i
        label = f"{'当前' if bars_ago == 0 else f'{bars_ago}bar前'}"
        if abs_val > p99:
            direction = "多头" if val > 0 else "空头"
            signals.append(CCLSignal(
                signal_type="single_bar",
                level="CRITICAL",
                description=f"{label} CCL={val:+,.0f} 突破P99，{direction}异常放量",
                value=abs_val,
            ))
        elif abs_val > p95:
            direction = "多头" if val > 0 else "空头"
            signals.append(CCLSignal(
                signal_type="single_bar",
                level="WARNING",
                description=f"{label} CCL={val:+,.0f} 突破P95，{direction}显著放量",
                value=abs_val,
            ))

    return signals


def _detect_consecutive(ccl_values: np.ndarray) -> List[CCLSignal]:
    """信号 2: 连续同向 CCL

    从最新 bar 往回看，连续同方向 (同正或同负) 的 bar 数
    """
    signals = []
    if len(ccl_values) < 4:
        return signals

    # 从最新往前数连续同向
    n = len(ccl_values)
    latest_sign = 1 if ccl_values[-1] > 0 else (-1 if ccl_values[-1] < 0 else 0)
    if latest_sign == 0:
        return signals

    count = 0
    for i in range(n - 1, -1, -1):
        if (latest_sign > 0 and ccl_values[i] > 0) or \
           (latest_sign < 0 and ccl_values[i] < 0):
            count += 1
        else:
            break

    direction = "多头" if latest_sign > 0 else "空头"
    if count >= 6:
        signals.append(CCLSignal(
            signal_type="consecutive",
            level="WARNING",
            description=f"连续 {count} 根 {direction}施压，过热预警",
            value=float(count),
        ))
    elif count >= 4:
        signals.append(CCLSignal(
            signal_type="consecutive",
            level="WATCH",
            description=f"连续 {count} 根 {direction}施压，趋势强化",
            value=float(count),
        ))

    return signals


def _detect_cumulative(ccl_values: np.ndarray, oi_values: np.ndarray,
                       p95: float, window: int = 12) -> List[CCLSignal]:
    """信号 3: CCL 累积偏移

    滚动 window 根 bar 的 CCL 累积, 与 OI 均值比较
    """
    signals = []
    if len(ccl_values) < window or len(oi_values) < window:
        return signals

    recent_ccl = ccl_values[-window:]
    recent_oi = oi_values[-window:]
    cum_ccl = np.sum(recent_ccl)
    avg_oi = np.mean(np.abs(recent_oi))

    if avg_oi == 0:
        return signals

    # 归一化累积偏移
    cum_pct = cum_ccl / avg_oi

    # 用历史 CCL 分布估算阈值: window 根 bar 的期望累积
    # 单 bar P95 对应 window 根 bar 的极端累积约 P95 * sqrt(window)
    expected_extreme = p95 * np.sqrt(window) * 0.5  # 保守估计
    if expected_extreme == 0:
        return signals

    abs_cum_pct = abs(cum_pct)
    threshold = expected_extreme / avg_oi if avg_oi > 0 else 0

    if threshold > 0 and abs_cum_pct > threshold * 1.5:
        direction = "多头" if cum_ccl > 0 else "空头"
        signals.append(CCLSignal(
            signal_type="cumulative",
            level="WARNING",
            description=f"近{window}bar {direction}累积偏移 {cum_pct:+.1%}，显著偏离",
            value=abs_cum_pct,
        ))
    elif threshold > 0 and abs_cum_pct > threshold:
        direction = "多头" if cum_ccl > 0 else "空头"
        signals.append(CCLSignal(
            signal_type="cumulative",
            level="WATCH",
            description=f"近{window}bar {direction}累积偏移 {cum_pct:+.1%}",
            value=abs_cum_pct,
        ))

    return signals


def _detect_divergence(ccl_values: np.ndarray, prices: np.ndarray,
                       window: int = 12) -> List[CCLSignal]:
    """信号 4: 量价背离

    价格创 window-bar 新高但 CCL 累积转负 → 多头力竭
    价格创 window-bar 新低但 CCL 累积转正 → 空头力竭
    """
    signals = []
    if len(ccl_values) < window or len(prices) < window:
        return signals

    recent_price = prices[-window:]
    recent_ccl = ccl_values[-window:]
    current_price = prices[-1]

    price_high = np.max(recent_price)
    price_low = np.min(recent_price)
    cum_ccl = np.sum(recent_ccl)

    # 多头力竭: 价格接近高点 (98%+位置) 但 CCL 累积为负
    if price_high > price_low * 1.001:  # 有波动空间
        price_position = (current_price - price_low) / (price_high - price_low)
        if price_position > 0.85 and cum_ccl < 0:
            signals.append(CCLSignal(
                signal_type="divergence",
                level="WARNING",
                description=f"价格处于{window}bar高位({price_position:.0%})但CCL累积为负({cum_ccl:+,.0f})，多头力竭",
                value=abs(cum_ccl),
            ))
        elif price_position < 0.15 and cum_ccl > 0:
            signals.append(CCLSignal(
                signal_type="divergence",
                level="WARNING",
                description=f"价格处于{window}bar低位({price_position:.0%})但CCL累积为正({cum_ccl:+,.0f})，空头力竭",
                value=abs(cum_ccl),
            ))

    return signals


def _detect_regime_change(ccl_values: np.ndarray, p50: float = 0,
                          window: int = 6) -> List[CCLSignal]:
    """信号 5: CCL 翻转 (regime 切换)

    前 window 根 avg(ccl) 显著正/负 → 最近 window 根方向反转
    """
    signals = []
    need = window * 2 + 2
    if len(ccl_values) < need:
        return signals

    # 前段 (较早) vs 后段 (较近)
    prev_block = ccl_values[-(window * 2):-window]
    curr_block = ccl_values[-window:]
    prev_avg = np.mean(prev_block)
    curr_avg = np.mean(curr_block)

    # 阈值: 至少达到 P50 的 10% 才算有明确方向 (避免在噪音级别触发)
    min_magnitude = max(p50 * 0.1, 50)  # 下限 50 防止 P50 极小的品种
    if abs(prev_avg) < min_magnitude or abs(curr_avg) < min_magnitude:
        return signals

    prev_sign = 1 if prev_avg > 0 else -1
    curr_sign = 1 if curr_avg > 0 else -1

    if prev_sign != curr_sign:
        # 翻转确认
        from_label = "多头" if prev_sign > 0 else "空头"
        to_label = "多头" if curr_sign > 0 else "空头"
        signals.append(CCLSignal(
            signal_type="regime",
            level="WARNING",
            description=f"CCL 多空翻转: {from_label}→{to_label} "
                        f"(前{window}bar均值{prev_avg:+,.0f} → 近{window}bar均值{curr_avg:+,.0f})",
            value=abs(curr_avg - prev_avg),
        ))

    return signals


# ── 综合检测 ─────────────────────────────────────────────

_LEVEL_RANK = {"NORMAL": 0, "WATCH": 1, "WARNING": 2, "CRITICAL": 3}


def detect_anomalies(symbol: str, store=None, source: str = "1h",
                     lookback: int = 480,
                     preloaded_df: Optional[pd.DataFrame] = None) -> CCLAlert:
    """综合 CCL 异动检测

    Args:
        symbol: 品种代码
        store: DataStore 实例 (与 preloaded_df 二选一)
        source: "1h" 或 "daily"
        lookback: 读取的 bar 数
        preloaded_df: 预加载的 DataFrame (避免重复 IO)

    Returns:
        CCLAlert 综合预警结果
    """
    alert = CCLAlert(symbol=symbol)

    # 读取数据
    if preloaded_df is not None:
        df = preloaded_df
    elif store is not None:
        if source == "1h":
            df = store.get_main_contract_1h(limit=lookback)
        else:
            df = store.get_main_continuous(limit=lookback)
    else:
        return alert

    if df.empty or "ccl_value" not in df.columns:
        return alert

    # 对齐: 只在 ccl_value 非空的位置上分析, 同时切片 prices/oi
    valid_mask = df["ccl_value"].notna()
    ccl_values = df.loc[valid_mask, "ccl_value"].values.astype(float)
    prices = df.loc[valid_mask, "close_price"].values.astype(float)
    oi_values = (df.loc[valid_mask, "open_interest"].values.astype(float)
                 if "open_interest" in df.columns else np.zeros(len(ccl_values)))
    alert.latest_label = str(df.loc[valid_mask, "ccl_label"].iloc[-1]) \
        if "ccl_label" in df.columns and valid_mask.any() else ""

    if len(ccl_values) < 20:
        return alert

    alert.latest_ccl = float(ccl_values[-1])

    # 计算阈值 (优先用 store, 否则用 df 自身数据)
    if store is not None:
        p50, p95, p99 = calc_ccl_percentiles(symbol, store, source)
    else:
        abs_vals = np.sort(np.abs(ccl_values))
        n = len(abs_vals)
        p50 = float(abs_vals[n // 2]) if n > 20 else 0
        p95 = float(abs_vals[int(n * 0.95)]) if n > 20 else 0
        p99 = float(abs_vals[int(n * 0.99)]) if n > 100 else 0
    alert.p95 = p95
    alert.p99 = p99

    if p95 == 0:
        return alert

    # 运行 5 种信号检测
    all_signals: List[CCLSignal] = []
    all_signals.extend(_detect_single_bar(ccl_values, p95, p99))
    all_signals.extend(_detect_consecutive(ccl_values))
    all_signals.extend(_detect_cumulative(ccl_values, oi_values, p95))
    all_signals.extend(_detect_divergence(ccl_values, prices))
    all_signals.extend(_detect_regime_change(ccl_values, p50=p50))

    # 排序: CRITICAL > WARNING > WATCH
    all_signals.sort(key=lambda s: _LEVEL_RANK.get(s.level, 0), reverse=True)
    alert.signals = all_signals

    # 综合等级: 取最高级信号
    if all_signals:
        alert.overall_level = all_signals[0].level
    else:
        alert.overall_level = "NORMAL"

    # 多信号叠加升级
    high_count = sum(1 for s in all_signals if s.level in ("WARNING", "CRITICAL"))
    if high_count >= 3:
        alert.overall_level = "CRITICAL"

    # 生成综合描述
    sig_count = len(all_signals)
    if alert.overall_level == "NORMAL":
        alert.summary = "CCL 无异动，市场状态正常。"
    elif alert.overall_level == "WATCH":
        alert.summary = f"CCL 出现 {sig_count} 项轻度异动，建议关注后续走向。"
    elif alert.overall_level == "WARNING":
        if sig_count >= 3:
            alert.summary = f"CCL {sig_count} 项异动同时触发，建议降低仓位或收紧止损。"
        else:
            alert.summary = f"CCL 出现 {sig_count} 项异动 ({all_signals[0].signal_type})，建议关注。"
    elif alert.overall_level == "CRITICAL":
        alert.summary = f"CCL {sig_count} 项严重异动，建议暂停操作，密切监控。"

    return alert
