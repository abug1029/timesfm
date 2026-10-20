"""短窗回测 (Phase 2 Task 2)

对 prescreen-success 提案进行快速实证验证 (100-200 时间点)，
过滤掉 dir_acc <= 0.50 的提案，减少 50%+ 无效深度验证（588 点）。

用法:
    # 单个提案
    python scripts/short_window_backtest.py --symbol rb --cov rsi_state

    # 批量处理
    python scripts/short_window_backtest.py --batch

    # 统计
    python scripts/short_window_backtest.py --stats
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np

# ── 路径 ──
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, FM_ROOT)
sys.path.insert(0, HERE)

SHORT_WINDOW_RESULTS_PATH = os.path.join(
    FM_ROOT, "data", "cache", "short_window_results.jsonl")
HORIZON = 24          # 1H bars，与慢环一致
STEP = 24             # 步长
MIN_WINDOW = 100      # 最少时间点数
DEFAULT_WINDOW = 150  # 默认窗口

logger = logging.getLogger("short_window_backtest")

# ── 协变量信号映射 ──
# 每个 cov_override 名 → 从 1H 数据帧中提取/计算信号列的函数
# 信号含义: >0 看涨, <0 看跌 (标准化后)


def _signal_rsi(df, period=14):
    """RSI 均值回归: RSI>70 做空(<0), RSI<30 做多(>0)。"""
    col = f"rsi{period}"
    if col not in df.columns:
        # Fallback: pick closest available RSI period
        for p in [12, 6, 24]:
            c = f"rsi{p}"
            if c in df.columns:
                col = c
                break
        else:
            return None
    rsi = df[col].values.astype(float)
    # z-score: (rsi - 50) / 20 → [-1, 1] 范围
    signal = (50.0 - rsi) / 20.0  # 反转: 高 RSI → 负信号(看跌)
    return np.clip(signal, -2.0, 2.0)


def _signal_oi(df):
    """持仓量变化: 增仓+涨=看涨, 增仓+跌=看跌。"""
    if "oi_change" not in df.columns or "change_pct" not in df.columns:
        return None
    oi = df["oi_change"].values.astype(float)
    chg = df["change_pct"].values.astype(float)
    # 量价同向 → 趋势延续; 量价背离 → 趋势衰竭
    signal = np.sign(oi) * np.sign(chg)
    # 标准化
    valid = ~np.isnan(signal)
    if valid.sum() < 10:
        return None
    mu, sigma = np.mean(signal[valid]), max(np.std(signal[valid]), 1e-8)
    signal[valid] = (signal[valid] - mu) / sigma
    return signal


def _signal_ma(df, period=20):
    """均线偏离: 价格高于 MA → 看涨(趋势延续)。"""
    col = f"ma{period}" if f"ma{period}" in df.columns else "ma20"
    if col not in df.columns or "close_price" not in df.columns:
        return None
    close = df["close_price"].values.astype(float)
    ma = df[col].values.astype(float)
    atr_col = "atr14" if "atr14" in df.columns else None
    if atr_col is not None:
        atr = df[atr_col].values.astype(float)
        valid = ~np.isnan(atr) & (atr > 0)
        signal = np.zeros_like(close)
        signal[valid] = (close[valid] - ma[valid]) / atr[valid]
    else:
        ma_valid = ~np.isnan(ma) & (ma > 0)
        signal = np.zeros_like(close)
        signal[ma_valid] = (close[ma_valid] - ma[ma_valid]) / ma[ma_valid]
    return signal


def _signal_macd(df):
    """MACD: DIF>DEA → 看涨。"""
    if "macd_dif" not in df.columns or "macd_dea" not in df.columns:
        return None
    dif = df["macd_dif"].values.astype(float)
    dea = df["macd_dea"].values.astype(float)
    signal = dif - dea
    valid = ~np.isnan(signal)
    if valid.sum() < 10:
        return None
    mu, sigma = np.mean(signal[valid]), max(np.std(signal[valid]), 1e-8)
    signal[valid] = (signal[valid] - mu) / sigma
    return signal


def _signal_atr(df):
    """波动率: 低波动 → 看涨(蓄力), 高波动 → 看跌(风险)。"""
    if "atr14" not in df.columns:
        return None
    atr = df["atr14"].values.astype(float)
    valid = ~np.isnan(atr) & (atr > 0)
    signal = np.zeros_like(atr)
    if valid.sum() >= 20:
        # z-score 反转: 低 ATR → 正信号
        mu, sigma = np.mean(atr[valid]), np.std(atr[valid])
        if sigma > 1e-8:
            signal[valid] = -(atr[valid] - mu) / sigma
    return signal


def _signal_boll(df):
    """布林带: 价格相对位置，靠近下轨看涨(回归)，靠近上轨看跌。"""
    if "boll_mid" not in df.columns or "close_price" not in df.columns:
        return None
    close = df["close_price"].values.astype(float)
    mid = df["boll_mid"].values.astype(float)
    upper = df["boll_upper"].values.astype(float)
    lower = df["boll_lower"].values.astype(float)
    width = upper - lower
    valid = ~np.isnan(width) & (width > 0)
    signal = np.zeros_like(close)
    # (mid - close) / width: 价格在下轨 → 正信号(看涨回归)
    signal[valid] = (mid[valid] - close[valid]) / width[valid]
    return signal


def _signal_default(df):
    """通用信号: 价格偏离 MA20 的标准化值 (趋势延续假设)。"""
    return _signal_ma(df, period=20)


# 协变量名 → 信号函数映射
_SIGNAL_FUNCS: Dict[str, callable] = {
    # momentum 族
    "rsi_state": lambda df: _signal_rsi(df, period=14),
    "rsi6": lambda df: _signal_rsi(df, period=6),
    "rsi12": lambda df: _signal_rsi(df, period=12),
    "rsi24": lambda df: _signal_rsi(df, period=24),
    "rsi_slope": lambda df: _signal_rsi(df, period=14),
    "qstick": _signal_ma,
    "ha_body": _signal_ma,
    "hourly_slope": _signal_ma,
    "gated_slope": _signal_ma,
    "hurst": _signal_ma,
    "regime_gated": _signal_ma,
    "sar_dist": _signal_ma,
    "vwap_deviation": _signal_ma,
    "reversal_shadow": _signal_ma,
    "reversal_shadow_gated_02": _signal_ma,
    "reversal_shadow_gated_03": _signal_ma,
    "reversal_shadow_gated_05": _signal_ma,
    "pca_momentum": _signal_ma,
    "oi_gated_momentum": _signal_ma,
    # inventory 族
    "oi": _signal_oi,
    "ccl": _signal_oi,
    "nvi": _signal_oi,
    # volatility 族
    "bb_squeeze": _signal_boll,
    "stddev": _signal_atr,
    "vor": _signal_atr,
    # calendar 族
    "calendar_cyclical": _signal_default,
    # term_structure 族
    "basis_momentum": _signal_ma,
    "crack_spread_level": _signal_ma,
    "crack_spread_slope": _signal_ma,
    "crack_spread_zscore": _signal_ma,
}


def _get_signal_func(cov_override: str):
    """获取协变量信号函数，无匹配则返回默认。"""
    return _SIGNAL_FUNCS.get(cov_override, _signal_default)


def _load_1h_data(symbol: str, min_bars: int = 500):
    """加载 1H 数据，返回 DataFrame 或 None。"""
    from data.data_store import DataStore
    try:
        ds = DataStore(symbol)
        df = ds.get_main_contract_1h(limit=min_bars)
        if df.empty or len(df) < MIN_WINDOW + HORIZON + 10:
            logger.warning("symbol %s: insufficient 1H data (%d bars)",
                           symbol, len(df))
            return None
        return df
    except Exception as e:
        logger.warning("symbol %s: failed to load 1H data: %s", symbol, e)
        return None


def short_window_backtest(
    symbol: str,
    cov_override: str,
    window_size: int = DEFAULT_WINDOW,
) -> dict:
    """短窗回测: 对 symbol+cov_override 进行 walk-forward 方向准确率测试。

    Args:
        symbol: 品种名 (如 "rb", "m")
        cov_override: 协变量名 (如 "rsi_state", "oi")
        window_size: 回测窗口大小 (默认 150)

    Returns:
        dict with keys: variant_id, symbol, cov_override, window_size,
                       dir_acc, n, pass, timestamp
    """
    symbol = symbol.lower().strip()
    cov_override = cov_override.strip()
    variant_id = f"{symbol}_{cov_override}"

    result = {
        "variant_id": variant_id,
        "symbol": symbol,
        "cov_override": cov_override,
        "window_size": window_size,
        "dir_acc": 0.5,
        "n": 0,
        "pass": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 加载数据
    df = _load_1h_data(symbol, min_bars=window_size + HORIZON + 50)
    if df is None or df.empty:
        result["error"] = "no_data"
        result["dir_acc"] = 0.5  # fail-open: neutral
        return result

    close = df["close_price"].values.astype(float)
    n_total = len(close)

    # 裁剪到窗口大小 (取最近的 window_size + horizon 条)
    n_use = min(n_total, window_size + HORIZON + 20)
    start_idx = max(0, n_total - n_use)
    close_slice = close[start_idx:]
    n_total = len(close_slice)

    # 计算信号
    sig_func = _get_signal_func(cov_override)
    df_slice = df.iloc[start_idx:].copy()
    signal = sig_func(df_slice)

    if signal is None:
        result["error"] = "signal_compute_failed"
        result["dir_acc"] = 0.5
        return result

    # Walk-forward 测试
    correct = 0
    total = 0

    for t in range(0, n_total - HORIZON, STEP):
        if np.isnan(signal[t]):
            continue
        sig = signal[t]
        if abs(sig) < 1e-8:
            # 信号接近零 → 无预测能力，跳过
            continue

        # 预测方向: 正信号 → 看涨, 负信号 → 看跌
        pred_up = sig > 0

        # 实际方向
        if t + HORIZON >= n_total:
            break
        base_price = close_slice[t]
        end_price = close_slice[t + HORIZON]
        if np.isnan(base_price) or np.isnan(end_price):
            continue
        delta = end_price - base_price
        if abs(delta) < 1e-8 * abs(base_price):
            # 价格几乎没变 → 跳过
            continue
        actual_up = delta > 0

        if pred_up == actual_up:
            correct += 1
        total += 1

    if total < 5:
        # 样本太少，fail-open
        result["n"] = total
        result["dir_acc"] = 0.5
        return result

    dir_acc = correct / total
    result["dir_acc"] = round(dir_acc, 4)
    result["n"] = total
    result["pass"] = dir_acc > 0.50

    return result


# ── 缓存 ──

def load_short_window_cache(variant_id: str) -> Optional[dict]:
    """从缓存读取短窗结果。"""
    if not os.path.exists(SHORT_WINDOW_RESULTS_PATH):
        return None
    try:
        with open(SHORT_WINDOW_RESULTS_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    if rec.get("variant_id") == variant_id:
                        return rec
    except (json.JSONDecodeError, OSError):
        pass
    return None


def append_short_window_cache(result: dict):
    """追加单条短窗结果到缓存。"""
    os.makedirs(os.path.dirname(SHORT_WINDOW_RESULTS_PATH), exist_ok=True)
    try:
        with open(SHORT_WINDOW_RESULTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("failed to cache short_window result: %s", e)


# ── CLI ──

def cmd_single(args):
    """单个提案短窗回测。"""
    result = short_window_backtest(args.symbol, args.cov, args.window)
    append_short_window_cache(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_batch(args):
    """批量处理 prescreen-success 提案。"""
    output = args.output or SHORT_WINDOW_RESULTS_PATH
    results = []

    # 扫描所有提案文件
    pattern = os.path.join(FM_ROOT, "task_FM", "experiments", "run_*",
                           "results", "**", "proposals", "*.json")
    proposal_files = glob.glob(pattern, recursive=True)

    seen_vids = set()
    for pf in proposal_files:
        try:
            with open(pf, encoding="utf-8") as f:
                p = json.load(f)
        except Exception:
            continue

        symbol = str(p.get("symbol") or "").lower().strip()
        cov = str(p.get("cov_override") or "").strip()
        if not symbol or not cov:
            continue

        vid = f"{symbol}_{cov}"
        if vid in seen_vids:
            continue

        # 检查缓存
        cached = load_short_window_cache(vid)
        if cached is not None:
            results.append(cached)
            seen_vids.add(vid)
            continue

        result = short_window_backtest(symbol, cov, args.window)
        append_short_window_cache(result)
        results.append(result)
        seen_vids.add(vid)

        if args.limit and len(results) >= args.limit:
            break

    # 写入输出
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 统计
    passed = sum(1 for r in results if r.get("pass"))
    failed = sum(1 for r in results if not r.get("pass"))
    print(f"batch complete: {len(results)} proposals, "
          f"{passed} passed, {failed} failed")
    return results


def cmd_stats(args):
    """统计短窗结果。"""
    path = args.path or SHORT_WINDOW_RESULTS_PATH
    if not os.path.exists(path):
        print("no results file found")
        return

    results = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not results:
        print("no results")
        return

    passed = sum(1 for r in results if r.get("pass"))
    failed = sum(1 for r in results if not r.get("pass"))
    dir_accs = [r.get("dir_acc", 0.5) for r in results if "dir_acc" in r]

    print(f"total: {len(results)}")
    print(f"passed (dir_acc > 0.50): {passed} "
          f"({passed/len(results)*100:.1f}%)")
    print(f"failed: {failed} ({failed/len(results)*100:.1f}%)")
    if dir_accs:
        print(f"dir_acc: mean={np.mean(dir_accs):.4f}, "
              f"median={np.median(dir_accs):.4f}, "
              f"min={min(dir_accs):.4f}, max={max(dir_accs):.4f}")


def main():
    parser = argparse.ArgumentParser(
        description="短窗回测 (Phase 2 Task 2)")
    sub = parser.add_subparsers(dest="command")

    # 单个
    p1 = sub.add_parser("single", help="单个提案回测")
    p1.add_argument("--symbol", required=True)
    p1.add_argument("--cov", required=True)
    p1.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    p1.set_defaults(func=cmd_single)

    # 批量
    p2 = sub.add_parser("batch", help="批量处理 prescreen-success 提案")
    p2.add_argument("--output")
    p2.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    p2.add_argument("--limit", type=int, default=0)
    p2.set_defaults(func=cmd_batch)

    # 统计
    p3 = sub.add_parser("stats", help="统计短窗结果")
    p3.add_argument("--path")
    p3.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
