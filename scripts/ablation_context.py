"""
1H Context Length 消融实验

对比不同 1H context 长度对预测结果的影响:
- 240 bars (10:1 ratio)
- 480 bars (20:1 ratio)
- 1023 bars (43:1 ratio, 当前默认)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
import timesfm
from data.data_store import DataStore
from cascade.daily_model import DailyModel, DailyResult
from cascade.features import build_covariate_matrix


def load_model():
    print("[1/4] 加载 TimesFM 2.5 模型...")
    torch.set_float32_matmul_precision("high")
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        "google/timesfm-2.5-200m-pytorch"
    )
    model.compile(timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=128,
        return_backcast=True,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    ))
    return model


def run_daily_stage(store, symbol):
    print("[2/4] Stage 1: 日线预测...")
    daily_model = DailyModel()
    result = daily_model.predict(symbol, store, context_days=250, horizon_days=22)
    return result, daily_model.model


def run_hourly_with_context(model, store, daily_result, symbol, context_len, horizon=24):
    """用指定 context 长度运行 1H 预测"""
    df_1h = store.get_main_contract_1h(limit=context_len)
    if df_1h.empty:
        raise ValueError(f"{symbol}: 无 1H 数据")

    actual_len = len(df_1h)
    hourly_closes = df_1h["close_price"].dropna().values.astype(np.float64)

    # 构建协变量 (limit 匹配实际 context 长度)
    covariates = build_covariate_matrix(
        symbol=symbol,
        store=store,
        historical_daily_closes=daily_result.historical_closes,
        predicted_daily_closes=daily_result.forecast,
        daily_dates=daily_result.historical_dates,
        horizon=horizon,
        limit=context_len,
    )

    slope_arr = covariates["daily_slope"]
    ccl_arr = covariates["ccl_pct"]
    total_len = actual_len + horizon

    dynamic_covariates = {
        "daily_slope": [slope_arr],
        "ccl_pct": [ccl_arr],
    }

    # XReg 预测
    try:
        point_fc, quant_fc = model.forecast_with_covariates(
            inputs=[hourly_closes],
            dynamic_numerical_covariates=dynamic_covariates,
            xreg_mode="xreg + timesfm",
            normalize_xreg_target_per_input=True,
            ridge=0.0,
        )
        raw_point = point_fc[0]
        raw_quant = quant_fc[0]
        point = raw_point[-horizon:] if len(raw_point) > horizon else raw_point
        quant = raw_quant[-horizon:] if len(raw_quant) > horizon else raw_quant
    except Exception as e:
        print(f"  [WARN] XReg 失败: {e}")
        point, quant = None, None

    # 无协变量 baseline
    try:
        baseline_point, baseline_quant = model.forecast(
            horizon=horizon,
            inputs=[hourly_closes],
        )
        bp = baseline_point[0][-horizon:] if len(baseline_point[0]) > horizon else baseline_point[0]
    except Exception:
        bp = None

    return {
        "context_len": actual_len,
        "point": point,
        "quant": quant,
        "baseline": bp,
        "final_price": hourly_closes[-1],
    }


def compare_results(results):
    """对比不同 context 长度的预测结果"""
    print("\n" + "=" * 70)
    print("  1H Context Length 消融对比")
    print("=" * 70)

    # 过滤掉失败的预测
    valid = [r for r in results if r["point"] is not None]
    if not valid:
        print("所有预测均失败，无法对比")
        return

    # 表头
    horizon = len(valid[0]["point"])
    print(f"\n{'Context':>10} | {'Ratio':>6} | {'Final Pred':>10} | {'Min':>8} | {'Max':>8} | "
          f"{'Range':>8} | {'vs Baseline':>12}")
    print("-" * 80)

    for r in results:
        ctx = r["context_len"]
        ratio = f"{ctx/24:.0f}:1"
        fc = r["point"]
        bl = r["baseline"]
        if fc is not None:
            final = fc[-1]
            fmin = fc.min()
            fmax = fc.max()
            frange = fmax - fmin
            diff_vs_bl = np.abs(fc - bl).mean()
            print(f"{ctx:>10} | {ratio:>6} | {final:>10.1f} | {fmin:>8.1f} | {fmax:>8.1f} | "
                  f"{frange:>8.1f} | {diff_vs_bl:>12.1f}")

    # 逐小时对比表
    print(f"\n逐小时预测对比 (Pred):")
    print(f"{'Hour':>6}", end="")
    for r in results:
        print(f" | ctx={r['context_len']:>4}", end="")
    print()
    print("-" * (6 + 14 * len(results)))

    for t in range(horizon):
        print(f"T+{t+1:<3}", end="")
        for r in results:
            fc = r["point"]
            if fc is not None:
                print(f" | {fc[t]:>10.1f}", end="")
            else:
                print(f" | {'N/A':>10}", end="")
        print()

    # 协变量贡献对比
    print(f"\n协变量贡献 (|XReg - Baseline| 均值):")
    for r in results:
        ctx = r["context_len"]
        fc = r["point"]
        bl = r["baseline"]
        if fc is not None:
            max_diff = np.abs(fc - bl).max()
            mean_diff = np.abs(fc - bl).mean()
            same_dir = np.mean(np.sign(fc) == np.sign(bl))
            print(f"  ctx={ctx:>4}: max_diff={max_diff:.1f}, mean_diff={mean_diff:.1f}, "
                  f"direction_match={same_dir:.0%}")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ss"
    context_lengths = [240, 480, 1023]

    store = DataStore(symbol)
    daily_result, model = run_daily_stage(store, symbol)

    # 重新 compile 为 XReg 配置 (1H 需要 return_backcast)
    model.compile(timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=128,
        return_backcast=True,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    ))

    print(f"[3/4] Stage 2: 1H 消融实验 ({symbol.upper()})...")
    print(f"  测试 context 长度: {context_lengths}")
    print(f"  日线斜率: {daily_result.horizon_slope * 100:+.3f}%/天")

    results = []
    for ctx_len in context_lengths:
        print(f"\n  → context={ctx_len}...")
        r = run_hourly_with_context(model, store, daily_result, symbol, ctx_len)
        results.append(r)
        print(f"    实际 bars: {r['context_len']}, "
              f"final pred: {r['point'][-1]:.1f}" if r['point'] is not None else "    FAILED")

    print("[4/4] 对比分析...")
    compare_results(results)
