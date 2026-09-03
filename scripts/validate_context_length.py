"""
Context 长度验证实验: ctx=480 vs ctx=1023

对比真实回测 DirAcc/PF/EV_ratio，补齐消融实验缺失的准确率指标。
不修改任何已固化配置。
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
import torch
from data.data_store import DataStore
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from data.data_store import BacktestDataStore
from config.backtest_config import TICK_SIZES, SLIPPAGE_TICKS
from config.prediction_scheme import get_scheme

# 验证品种: 覆盖 trend/stable/short_range/高衰减
TEST_SYMBOLS = ['ss', 'i', 'p', 'fu']
CONTEXT_LENGTHS = [480, 1023]
HORIZON = 24
STEP = 120  # 加速: 每 5 天一个评估点 (原 step=24 约需 5x 时间)
MIN_EVAL = 10

def run_backtest(symbol, context_bars, daily_model, hourly_model):
    """单品种 walk-forward 回测, 返回汇总指标"""
    store = DataStore(symbol)
    all_1h = store.get_main_contract_1h(limit=99999)
    daily_df = store.get_main_continuous(limit=99999)
    store.close()

    if all_1h.empty or len(all_1h) < context_bars + HORIZON:
        return None

    total = len(all_1h)
    eval_indices = list(range(context_bars, total - HORIZON + 1, STEP))

    # 日线数据覆盖检查
    if not daily_df.empty:
        import bisect
        daily_dates = sorted(daily_df["dt"].astype(str).str[:10].tolist())
        min_daily = max(250 - 22, 100)
        eval_indices = [
            idx for idx in eval_indices
            if bisect.bisect_right(daily_dates, str(all_1h["dt"].iloc[idx])[:10]) >= min_daily
        ]

    if len(eval_indices) < MIN_EVAL:
        return None

    scheme = get_scheme(symbol)
    cov_type = scheme.covariate_type if scheme else "ccl"
    cov_types = scheme.covariate_types if scheme and scheme.covariate_types else None

    points = []
    for idx in eval_indices:
        bar_ts = pd.Timestamp(all_1h["dt"].iloc[idx])
        dt = bar_ts.strftime("%Y-%m-%d")
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        base = float(all_1h["close_price"].iloc[idx])
        real = all_1h["close_price"].iloc[idx+1:idx+1+HORIZON].values.astype(np.float64)

        bt_store = BacktestDataStore(symbol, cutoff)
        try:
            daily_result = daily_model.predict(symbol, bt_store, context_days=250, horizon_days=22)
            hourly_result = hourly_model.predict(
                symbol, bt_store, daily_result,
                horizon=HORIZON, visualize=False,
                covariate_type=cov_type,
                covariate_types=cov_types,
                verbose=False
            )
            pred = hourly_result.point_forecast

            delta_pred = pred[-1] - base
            delta_real = real[-1] - base
            dir_ok = bool(np.sign(delta_pred) == np.sign(delta_real)) if delta_real != 0 else True
            mape = float(np.mean(np.abs(pred - real) / np.where(real == 0, 1e-8, np.abs(real))) * 100)
            position_sign = np.sign(delta_pred)
            pnl = float(position_sign * delta_real) if position_sign != 0 else 0.0

            points.append({
                "dir_ok": dir_ok, "mape": mape, "pnl": pnl,
                "delta_real": delta_real,
            })
        except Exception:
            pass

    if not points:
        return None

    n = len(points)
    dir_acc = np.mean([p["dir_ok"] for p in points])
    mape = np.mean([p["mape"] for p in points])
    avg_abs_real = np.mean([abs(p["delta_real"]) for p in points])

    # 实盘修正: 扣除双边滑点
    tick = TICK_SIZES.get(symbol, 1.0)
    slippage_cost = tick * SLIPPAGE_TICKS
    gross_pnls = [p["pnl"] for p in points]
    net_pnls = [pnl - slippage_cost for pnl in gross_pnls]

    ev_gross = np.mean(gross_pnls)
    ev = np.mean(net_pnls)
    ev_ratio = ev / avg_abs_real if avg_abs_real > 0 else 0.0

    net_wins = [p for p in net_pnls if p > 0]
    net_losses = [abs(p) for p in net_pnls if p <= 0]  # 保守会计: 平局计入亏损
    total_net_win = sum(net_wins) if net_wins else 0.0
    total_net_loss = sum(net_losses) if net_losses else 0.0
    pf = (total_net_win / total_net_loss) if total_net_loss > 0 else float('inf')
    win_rate = len(net_wins) / n if n > 0 else 0.0

    return {
        "n": n, "dir_acc": round(dir_acc, 3), "mape": round(mape, 2),
        "ev": round(ev, 2), "ev_ratio": round(ev_ratio, 3),
        "pf": round(pf, 2) if pf != float('inf') else 99.99, "win_rate": round(win_rate, 3),
        "ev_gross": round(ev_gross, 2),
    }


def main():
    print("=" * 80)
    print("  Context 长度验证实验: ctx=480 vs ctx=1023")
    print(f"  品种: {[s.upper() for s in TEST_SYMBOLS]}")
    print(f"  步长: {STEP} bars, 时域: {HORIZON}h")
    print("=" * 80)

    print("\n[1] 加载模型...")
    torch.set_float32_matmul_precision("high")
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)
    print("  模型加载完成")

    results = {}
    for ctx in CONTEXT_LENGTHS:
        results[ctx] = {}
        print(f"\n[2] ctx={ctx} 回测...")
        for i, symbol in enumerate(TEST_SYMBOLS):
            print(f"  [{i+1}/{len(TEST_SYMBOLS)}] {symbol.upper()}...", end=" ", flush=True)
            t0 = time.time()
            r = run_backtest(symbol, ctx, daily_model, hourly_model)
            elapsed = time.time() - t0
            if r:
                results[ctx][symbol] = r
                print(f"n={r['n']} DA={r['dir_acc']:.0%} MAPE={r['mape']:.2f}% "
                      f"EV={r['ev_ratio']:+.3f} PF={r['pf']:.2f} WR={r['win_rate']:.0%} ({elapsed:.0f}s)")
            else:
                print(f"SKIP ({elapsed:.0f}s)")

    # 对比报告
    print("\n" + "=" * 80)
    print("  对比结果 (PF/EV 含滑点修正)")
    print("=" * 80)
    print(f'\n{"品种":>4} | {"ctx":>5} | {"pts":>4} | {"DirAcc":>6} | {"MAPE":>7} | {"EV_r":>7} | {"PF":>5} | {"WR":>5} | {"判定":>6}')
    print("-" * 78)

    for symbol in TEST_SYMBOLS:
        for ctx in CONTEXT_LENGTHS:
            r = results[ctx].get(symbol)
            if r:
                print(f"{symbol.upper():>4} | {ctx:>5} | {r['n']:>4} | "
                      f"{r['dir_acc']:.0%} | {r['mape']:.2f}% | "
                      f"{r['ev_ratio']:+.3f} | {r['pf']:.2f} | {r['win_rate']:.0%} |")
            else:
                print(f"{symbol.upper():>4} | {ctx:>5} |    0 |      - |       - |       - |     - |     - |")

        # 对比
        r480 = results[480].get(symbol)
        r1023 = results[1023].get(symbol)
        if r480 and r1023:
            da_delta = r480['dir_acc'] - r1023['dir_acc']
            pf_delta = r480['pf'] - r1023['pf']
            ev_delta = r480['ev_ratio'] - r1023['ev_ratio']
            # verdict 基于连续指标 ev_ratio (不受 PF cap 影响)
            verdict = "480优" if (da_delta >= 0 and ev_delta >= -0.05) else ("1023优" if da_delta < -0.02 or ev_delta < -0.1 else "持平")
            print(f"{'':>4} | {'差异':>5} |      | "
                  f"{da_delta:+.0%} | {'':>7} | "
                  f"{ev_delta:+.3f} | {pf_delta:+.2f} | {'':>5} | {verdict:>6}")
        print("-" * 78)

    # 总结
    print("\n总结:")
    win_480 = 0
    win_1023 = 0
    tie = 0
    for symbol in TEST_SYMBOLS:
        r480 = results[480].get(symbol)
        r1023 = results[1023].get(symbol)
        if r480 and r1023:
            da_delta = r480['dir_acc'] - r1023['dir_acc']
            ev_delta = r480['ev_ratio'] - r1023['ev_ratio']
            if da_delta >= 0 and ev_delta >= -0.05:
                win_480 += 1
            elif da_delta < -0.02 or ev_delta < -0.1:
                win_1023 += 1
            else:
                tie += 1
    print(f"  ctx=480 优: {win_480}/{len(TEST_SYMBOLS)} 品种")
    print(f"  ctx=1023 优: {win_1023}/{len(TEST_SYMBOLS)} 品种")
    print(f"  持平: {tie}/{len(TEST_SYMBOLS)} 品种")


if __name__ == "__main__":
    main()
