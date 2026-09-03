"""
1H 级联预测 Walk-Forward 回测

**DEPRECATED (CF-20 A)**: 早期脚本；无 scheme 加权信号。固化用 monthly_backtest.py。

对 SS/P/I/UR 四个品种进行 walk-forward 回测:
- context=480 bars → 预测 horizon=24 bars
- 步长=24 bars (约 4~6 个交易日)
- 锁定合约防换月跳空
- 方向准确率 = 终点趋势方向

输出: 汇总 Markdown 报告 + 控制台表格
"""

import sys
import os
import re
import numpy as np
import pandas as pd
import torch
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print(
    "[DEPRECATED] backtest_1h: 勿用于 SCHEMES 固化；请用 monthly_backtest.py",
    file=sys.stderr,
)

import timesfm
from data.data_store import DataStore, BacktestDataStore
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel


# ─────────────────────────────────────────────────────────
# 评估指标
# ─────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    """单个评估点的结果"""
    symbol: str
    cutoff_idx: int
    cutoff_date: str
    contract_code: str
    base_price: float
    # 逐指标
    mae: float = 0.0
    mape: float = 0.0
    direction_correct: bool = False
    coverage_count: int = 0      # P10-P90 覆盖的 bar 数
    slope_sign_match: bool = False
    # 预测值 & 真实值
    pred: Optional[np.ndarray] = None
    real: Optional[np.ndarray] = None
    error: str = ""


def compute_metrics(pred: np.ndarray, real: np.ndarray,
                    quant: Optional[np.ndarray], base_price: float,
                    daily_slope: float, real_22d_change: float) -> dict:
    """计算评估指标"""
    n = min(len(pred), len(real))
    p = pred[:n]
    r = real[:n]

    # MAE
    mae = np.mean(np.abs(p - r))

    # MAPE (避免除零)
    safe_r = np.where(r == 0, 1e-8, r)
    mape = np.mean(np.abs(p - r) / np.abs(safe_r)) * 100

    # 方向准确率: 终点趋势方向
    delta_pred = p[-1] - base_price
    delta_real = r[-1] - base_price
    dir_correct = (np.sign(delta_pred) == np.sign(delta_real)) if delta_real != 0 else True

    # P10-P90 覆盖率
    coverage = 0
    if quant is not None and quant.ndim == 2 and quant.shape[1] >= 10:
        for i in range(n):
            p10 = quant[i, 1]
            p90 = quant[i, 9]
            if p10 <= r[i] <= p90:
                coverage += 1

    # 日线斜率方向匹配
    slope_match = (np.sign(daily_slope) == np.sign(real_22d_change)) if real_22d_change != 0 else True

    return {
        "mae": mae,
        "mape": mape,
        "direction_correct": dir_correct,
        "coverage": coverage,
        "coverage_n": n,
        "slope_match": slope_match,
    }


# ─────────────────────────────────────────────────────────
# 回测主逻辑
# ─────────────────────────────────────────────────────────

def run_backtest_symbol(symbol: str, store: DataStore,
                        daily_model: DailyModel, hourly_model: HourlyModel,
                        context_bars: int = 480, horizon: int = 24,
                        step: int = 24) -> List[EvalResult]:
    """对单个品种执行 walk-forward 回测"""

    # 获取全量 1H 数据 (当前主力合约)
    all_1h = store.get_main_contract_1h(limit=99999)
    if all_1h.empty:
        print(f"  [ERROR] {symbol}: 无 1H 数据")
        return []

    total_bars = len(all_1h)
    contract_code = all_1h["contract_code"].iloc[-1]
    print(f"  总 bars: {total_bars}, 合约: {contract_code}")

    # 评估点: 从 context_bars 开始, 每隔 step 一个评估点
    eval_indices = list(range(context_bars, total_bars - horizon + 1, step))
    if not eval_indices:
        print(f"  [WARN] 数据不足, 无法回测 (需要 > {context_bars + horizon} bars)")
        return []

    print(f"  评估点数: {len(eval_indices)}, 步长: {step} bars")

    results = []
    for i, cutoff_idx in enumerate(eval_indices):
        cutoff_dt_raw = all_1h["dt"].iloc[cutoff_idx]
        bar_ts = pd.to_datetime(cutoff_dt_raw)
        cutoff_date = str(bar_ts)[:10]
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        base_price = float(all_1h["close_price"].iloc[cutoff_idx])

        # 真实值: 锁定同一合约
        real_slice = all_1h["close_price"].iloc[cutoff_idx + 1: cutoff_idx + 1 + horizon]
        if len(real_slice) < horizon:
            continue
        real_values = real_slice.values.astype(np.float64)

        # 创建截断 DataStore (bar-exact，无同日 lookahead)
        bt_store = BacktestDataStore(symbol, cutoff)

        try:
            # Stage 1: 日线预测
            daily_result = daily_model.predict(
                symbol, bt_store, context_days=250, horizon_days=22
            )

            # Stage 2: 1H 预测
            hourly_result = hourly_model.predict(
                symbol, bt_store, daily_result, horizon=horizon, visualize=False
            )

            pred = hourly_result.point_forecast
            quant = hourly_result.quantile_forecast

            # 日线斜率真实值: 22 个交易日后的实际价格变化
            daily_df = bt_store.get_main_continuous(limit=250 + 22)
            if len(daily_df) >= 22:
                # 用已发生的真实数据计算真实斜率
                real_daily = daily_df["close_price"].values[-22:]
                real_22d_change = real_daily[-1] - real_daily[0]
            else:
                real_22d_change = 0.0

            # 计算指标
            metrics = compute_metrics(
                pred, real_values, quant, base_price,
                daily_result.horizon_slope, real_22d_change
            )

            result = EvalResult(
                symbol=symbol,
                cutoff_idx=cutoff_idx,
                cutoff_date=cutoff_date,
                contract_code=contract_code,
                base_price=base_price,
                mae=metrics["mae"],
                mape=metrics["mape"],
                direction_correct=metrics["direction_correct"],
                coverage_count=metrics["coverage"],
                slope_sign_match=metrics["slope_match"],
                pred=pred,
                real=real_values,
            )
            results.append(result)

        except Exception as e:
            result = EvalResult(
                symbol=symbol,
                cutoff_idx=cutoff_idx,
                cutoff_date=cutoff_date,
                contract_code=contract_code,
                base_price=base_price,
                error=str(e),
            )
            results.append(result)

        # 进度
        if (i + 1) % 5 == 0 or i == len(eval_indices) - 1:
            ok = sum(1 for r in results if not r.error)
            print(f"    [{i+1}/{len(eval_indices)}] 成功: {ok}")

    return results


# ─────────────────────────────────────────────────────────
# 汇总报告
# ─────────────────────────────────────────────────────────

def summarize_results(all_results: dict) -> str:
    """生成汇总 Markdown"""
    lines = [
        "# 1H 级联预测回测报告",
        "",
        f"**生成日期**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"**模型**: TimesFM 2.5 级联 (日线→1H XReg)",
        f"**Context**: 480 bars (1H) + 250 days (日线)",
        f"**Horizon**: 24 bars | **步长**: 24 bars",
        "",
        "## 汇总",
        "",
        "| Symbol | Eval_Points | MAE | MAPE | Dir_Acc | Coverage | Slope_Match |",
        "|--------|------------:|----:|-----:|--------:|---------:|------------:|",
    ]

    for symbol, results in all_results.items():
        ok = [r for r in results if not r.error]
        if not ok:
            lines.append(f"| {symbol.upper()} | 0 | - | - | - | - | - |")
            continue

        n = len(ok)
        mae = np.mean([r.mae for r in ok])
        mape = np.mean([r.mape for r in ok])
        dir_acc = np.mean([r.direction_correct for r in ok])
        total_bars = sum(r.coverage_count for r in ok)
        total_covered = sum(r.coverage_count for r in ok if r.coverage_count > 0)
        # 重新计算 coverage 比率
        coverage_vals = []
        for r in ok:
            if r.coverage_count > 0:
                # coverage_count 是覆盖的 bar 数, 除以 horizon
                coverage_vals.append(r.coverage_count / 24)
        coverage = np.mean(coverage_vals) if coverage_vals else 0
        slope_match = np.mean([r.slope_sign_match for r in ok])

        lines.append(
            f"| {symbol.upper()} | {n} | {mae:.1f} | {mape:.2f}% | "
            f"{dir_acc:.0%} | {coverage:.0%} | {slope_match:.0%} |"
        )

    lines.extend([
        "",
        "## 指标定义",
        "",
        "- **MAE**: 平均绝对误差 (pred vs real)",
        "- **MAPE**: 平均绝对百分比误差",
        "- **Dir_Acc**: 终点趋势方向准确率 (sign(Δpred) == sign(Δreal))",
        "- **Coverage**: P10-P90 置信区间覆盖率 (目标 ~80%)",
        "- **Slope_Match**: 日线斜率方向匹配率",
        "",
        "---",
        "",
        "> **注意**: 回测使用 walk-forward 方式，严格无穿越。真实值锁定同一合约，避免换月跳空。",
    ])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    symbols = sys.argv[1:] if len(sys.argv) > 1 else ["ss", "p", "i", "ur"]
    context_bars = 480
    horizon = 24
    step = 24

    print("=" * 60)
    print("  1H 级联预测 Walk-Forward 回测")
    print(f"  品种: {[s.upper() for s in symbols]}")
    print(f"  Context: {context_bars} bars | Horizon: {horizon} bars | Step: {step} bars")
    print("=" * 60)

    # 加载模型 (共享实例)
    print("\n[1] 加载 TimesFM 2.5 模型...")
    torch.set_float32_matmul_precision("high")

    daily_model = DailyModel()
    # HourlyModel 共享 daily_model 的模型实例
    hourly_model = HourlyModel(shared_model=daily_model.model)

    # 逐品种回测
    all_results = {}
    for symbol in symbols:
        print(f"\n[2] 回测 {symbol.upper()}...")
        store = DataStore(symbol)
        results = run_backtest_symbol(
            symbol, store, daily_model, hourly_model,
            context_bars=context_bars, horizon=horizon, step=step
        )
        all_results[symbol] = results

        # 品种小结
        ok = [r for r in results if not r.error]
        errors = [r for r in results if r.error]
        if ok:
            print(f"  完成: {len(ok)} 成功, {len(errors)} 失败")
            print(f"  MAE={np.mean([r.mae for r in ok]):.1f}, "
                  f"MAPE={np.mean([r.mape for r in ok]):.2f}%, "
                  f"DirAcc={np.mean([r.direction_correct for r in ok]):.0%}")
        else:
            print(f"  [ERROR] 全部失败")

    # 汇总报告
    print("\n[3] 生成汇总报告...")
    report = summarize_results(all_results)

    # 保存报告
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M")
    report_path = Path(__file__).parent.parent / "reports" / f"{timestamp}_backtest_1h.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"  报告保存: {report_path}")

    # 控制台输出
    print("\n" + report)
    print("\n回测完成。")
