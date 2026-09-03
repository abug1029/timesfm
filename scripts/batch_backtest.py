"""
批量 1H 回测 + 自动分类分析

**DEPRECATED (CF-20 A)**: 无 scheme 经济全链路 / 无统一 signal_contract。
固化请用 ``scripts/monthly_backtest.py``。本脚本仅遗留扫描，勿作固化依据。

对所有有 1H 数据的品种运行 walk-forward 回测，
按波动特征自动分类品种，输出汇总报告。
"""

import sys, os, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PYTHONIOENCODING'] = 'utf-8'
print(
    "[DEPRECATED] batch_backtest: 勿用于 SCHEMES 固化；请用 monthly_backtest.py",
    file=sys.stderr,
)

import numpy as np
import pandas as pd
import torch
import timesfm
from data.data_store import DataStore
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from data.data_store import BacktestDataStore


def run_backtest(symbol, store, daily_model, hourly_model, context=480, horizon=24, step=24):
    """运行单品种回测，返回详细结果"""
    all_1h = store.get_main_contract_1h(limit=99999)
    if all_1h.empty or len(all_1h) < context + horizon:
        return None

    total = len(all_1h)
    contract = all_1h["contract_code"].iloc[-1]
    eval_indices = list(range(context, total - horizon + 1, step))
    if not eval_indices:
        return None

    points = []
    for idx in eval_indices:
        bar_ts = pd.Timestamp(all_1h["dt"].iloc[idx])
        dt = bar_ts.strftime("%Y-%m-%d")
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        base = float(all_1h["close_price"].iloc[idx])
        real = all_1h["close_price"].iloc[idx+1:idx+1+horizon].values.astype(np.float64)

        bt_store = BacktestDataStore(symbol, cutoff)
        try:
            daily_result = daily_model.predict(symbol, bt_store, context_days=250, horizon_days=22)
            hourly_result = hourly_model.predict(symbol, bt_store, daily_result, horizon=horizon, visualize=False)
            pred = hourly_result.point_forecast
            quant = hourly_result.quantile_forecast

            # 指标
            delta_pred = pred[-1] - base
            delta_real = real[-1] - base
            dir_ok = (np.sign(delta_pred) == np.sign(delta_real)) if delta_real != 0 else True
            mae = np.mean(np.abs(pred - real))
            mape = np.mean(np.abs(pred - real) / np.where(real == 0, 1e-8, np.abs(real))) * 100

            # 前半/后半
            half = horizon // 2
            mae_h1 = np.mean(np.abs(pred[:half] - real[:half]))
            mae_h2 = np.mean(np.abs(pred[half:] - real[half:]))

            # T+12/T+24 方向
            d12_pred = pred[half-1] - base
            d12_real = real[half-1] - base
            dir12_ok = (np.sign(d12_pred) == np.sign(d12_real)) if d12_real != 0 else True

            # 覆盖率
            cov = 0
            if quant is not None and quant.ndim == 2 and quant.shape[1] >= 10:
                for t in range(horizon):
                    if quant[t, 1] <= real[t] <= quant[t, 9]:
                        cov += 1

            points.append({
                "cutoff": dt, "base": base, "pred_end": pred[-1], "real_end": real[-1],
                "delta_pred": delta_pred, "delta_real": delta_real,
                "dir_ok": bool(dir_ok), "dir12_ok": bool(dir12_ok),
                "mae": mae, "mape": mape,
                "mae_h1": mae_h1, "mae_h2": mae_h2,
                "coverage": cov,
                "pred": pred.tolist(), "real": real.tolist(),
                "real_range": float(real.max() - real.min()),
                "real_change_pct": float(abs(delta_real) / base * 100),
            })
        except Exception as e:
            points.append({"cutoff": dt, "error": str(e)})

    return {
        "symbol": symbol.upper(),
        "contract": contract,
        "total_bars": total,
        "eval_points": len(eval_indices),
        "points": points,
    }


def analyze_symbol(data):
    """计算单品种汇总指标"""
    ok = [p for p in data["points"] if "error" not in p]
    if not ok:
        return None

    n = len(ok)
    half = 12

    # 基础指标
    dir_acc = np.mean([p["dir_ok"] for p in ok])
    dir12_acc = np.mean([p["dir12_ok"] for p in ok])
    mae = np.mean([p["mae"] for p in ok])
    mape = np.mean([p["mape"] for p in ok])
    mae_h1 = np.mean([p["mae_h1"] for p in ok])
    mae_h2 = np.mean([p["mae_h2"] for p in ok])
    decay = mae_h2 / mae_h1 if mae_h1 > 0 else 1.0
    coverage = np.mean([p["coverage"] / 24 for p in ok])

    # 波动特征
    avg_real_range = np.mean([p["real_range"] for p in ok])
    avg_base = np.mean([p["base"] for p in ok])
    volatility_pct = avg_real_range / avg_base * 100  # 24-bar 波动幅度占价格比例

    # 大波动占比 (|Δreal|/base > 1%)
    big_move_pct = np.mean([p["real_change_pct"] > 1.0 for p in ok])

    # 前半/后半方向准确率
    first_half_better = np.mean([p["mae_h1"] <= p["mae_h2"] for p in ok])

    return {
        "symbol": data["symbol"],
        "contract": data["contract"],
        "bars": data["total_bars"],
        "n": n,
        "mae": mae,
        "mape": mape,
        "dir_acc": dir_acc,
        "dir12_acc": dir12_acc,
        "mae_h1": mae_h1,
        "mae_h2": mae_h2,
        "decay": decay,
        "coverage": coverage,
        "volatility_pct": volatility_pct,
        "big_move_pct": big_move_pct,
        "first_half_better": first_half_better,
    }


def classify_symbols(results):
    """按特征自动分类品种 — 阈值与 monthly 同源 config.backtest_config.THRESHOLDS"""
    from config.backtest_config import THRESHOLDS, CATEGORY_LABELS, MIN_EVAL_POINTS
    th = THRESHOLDS
    # key 对齐 monthly.classify 的 cats 字典
    categories = {k: [] for k in CATEGORY_LABELS}
    # 中文标签视图（报告用）
    label_cats = {CATEGORY_LABELS[k]: [] for k in CATEGORY_LABELS}

    for r in results:
        if r is None:
            continue
        sym = r["symbol"]
        if r["n"] < MIN_EVAL_POINTS:
            key = "insufficient"
        elif r.get("mape", 0) > th["mape_bad"]:
            key = "high_error"
        elif r["dir_acc"] >= th["dir_acc_trend"] and r["decay"] <= th["decay_good"]:
            key = "trend"
        elif r.get("dir12_acc", 0) > r["dir_acc"] + 0.10:
            key = "short_range"
        elif r["dir_acc"] < th["dir_acc_oscillation"]:
            key = "oscillation"
        elif r.get("mape", 99) <= th["mape_good"] or r["dir_acc"] >= 0.55:
            key = "stable"
        else:
            key = "oscillation"
        categories[key].append(sym)
        label_cats[CATEGORY_LABELS[key]].append(sym)
    # 兼容旧报告：返回中文标签 key
    return label_cats

    return categories


def generate_report(all_results, summary, categories):
    """生成 Markdown 报告"""
    lines = [
        "# 1H 级联预测 — 多品种批量回测报告",
        "",
        f"**生成日期**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"**模型**: TimesFM 2.5 级联 (日线→1H XReg)",
        f"**Context**: 480 bars | **Horizon**: 24 bars | **Step**: 24 bars",
        "",
        "---",
        "",
        "## 一、汇总",
        "",
        "| # | 品种 | 合约 | Bars | 评估点 | MAE | MAPE | DirAcc(T+24) | DirAcc(T+12) | 衰减比 | Coverage | 波动% |",
        "|--:|------|------|-----:|------:|----:|-----:|:------------:|:------------:|:------:|:--------:|------:|",
    ]

    for i, r in enumerate(summary):
        if r is None:
            continue
        lines.append(
            f"| {i+1} | {r['symbol']} | {r['contract']} | {r['bars']} | {r['n']} | "
            f"{r['mae']:.1f} | {r['mape']:.2f}% | {r['dir_acc']:.0%} | {r['dir12_acc']:.0%} | "
            f"{r['decay']:.2f}x | {r['coverage']:.0%} | {r['volatility_pct']:.2f}% |"
        )

    # 分类
    lines.extend([
        "",
        "## 二、品种分类",
        "",
    ])

    for cat, syms in categories.items():
        if syms:
            lines.append(f"### {cat}")
            lines.append("")
            for s in syms:
                r = next((x for x in summary if x and x["symbol"] == s), None)
                if r:
                    lines.append(
                        f"- **{s}**: DirAcc={r['dir_acc']:.0%}, MAPE={r['mape']:.2f}%, "
                        f"衰减={r['decay']:.2f}x, 波动={r['volatility_pct']:.2f}%"
                    )
            lines.append("")

    # 逐品种详情
    lines.extend([
        "## 三、逐品种评估点详情",
        "",
    ])

    for data in all_results:
        if data is None:
            continue
        sym = data["symbol"]
        ok = [p for p in data["points"] if "error" not in p]
        if not ok:
            continue

        lines.append(f"### {sym} ({data['contract']}, {data['total_bars']} bars)")
        lines.append("")
        lines.append("| # | cutoff | base | pred_end | real_end | Δpred | Δreal | dir | MAE |")
        lines.append("|--:|--------|-----:|--------:|--------:|------:|------:|:---:|----:|")

        for j, p in enumerate(ok):
            dir_mark = "Y" if p["dir_ok"] else "N"
            lines.append(
                f"| {j+1} | {p['cutoff']} | {p['base']:.0f} | {p['pred_end']:.0f} | "
                f"{p['real_end']:.0f} | {p['delta_pred']:+.0f} | {p['delta_real']:+.0f} | "
                f"{dir_mark} | {p['mae']:.0f} |"
            )
        lines.append("")

    # 分析结论
    lines.extend([
        "## 四、分析结论",
        "",
        "### 按方向准确率排序",
        "",
    ])

    ranked = sorted([r for r in summary if r], key=lambda x: x["dir_acc"], reverse=True)
    for i, r in enumerate(ranked):
        bar = "█" * int(r["dir_acc"] * 20)
        lines.append(f"{i+1:>2}. {r['symbol']:>3} {r['dir_acc']:>5.0%} {bar}")

    lines.extend([
        "",
        "### 按衰减比排序 (越小越好)",
        "",
    ])

    ranked_decay = sorted([r for r in summary if r], key=lambda x: x["decay"])
    for i, r in enumerate(ranked_decay):
        lines.append(f"{i+1:>2}. {r['symbol']:>3} {r['decay']:.2f}x")

    lines.extend([
        "",
        "### 关键发现",
        "",
        "1. **方向准确率与品种波动特征强相关**: 趋势型品种(如SS/UR)准确率可达70%+, 震荡型品种(如P/I)低于50%",
        "2. **衰减比反映预测有效距离**: 衰减比<1.4x的品种可看T+13~T+24, >1.5x的品种建议只看T+1~T+12",
        "3. **T+12 vs T+24方向准确率差异**: 若T+12远高于T+24, 说明短距有信号但长距失效; 若T+24更高, 说明日线斜率慢信号有效",
        "",
        "---",
        "",
        "> **风险提示**: 回测窗口有限 (2~7 个月), 结果可能存在过拟合。实盘需结合基本面判断。",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    symbols = sys.argv[1:] if len(sys.argv) > 1 else [
        "sp", "bu", "fu", "ta", "m", "jd", "cf", "lh", "sr", "rb", "fg", "jm", "ao"
    ]

    print("=" * 60)
    print("  多品种批量 1H 回测")
    print(f"  品种: {[s.upper() for s in symbols]}")
    print("=" * 60)

    # 加载模型
    print("\n[1] 加载模型...")
    torch.set_float32_matmul_precision("high")
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)

    # 逐品种回测
    all_results = []
    summary = []

    for i, symbol in enumerate(symbols):
        print(f"\n[{i+2}/{len(symbols)+1}] {symbol.upper()}...", end=" ")
        try:
            store = DataStore(symbol)
            data = run_backtest(symbol, store, daily_model, hourly_model)
            store.close()

            if data is None:
                print("SKIP (数据不足)")
                all_results.append(None)
                summary.append(None)
                continue

            s = analyze_symbol(data)
            all_results.append(data)
            summary.append(s)

            if s:
                print(f"{s['n']}pts MAE={s['mae']:.1f} MAPE={s['mape']:.2f}% "
                      f"DirAcc={s['dir_acc']:.0%} decay={s['decay']:.2f}x")
            else:
                print("FAIL")
                summary.append(None)

        except Exception as e:
            print(f"ERROR: {e}")
            all_results.append(None)
            summary.append(None)

    # 分类
    print(f"\n[{len(symbols)+2}] 分类分析...")
    valid_summary = [s for s in summary if s]
    categories = classify_symbols(valid_summary)

    # 生成报告
    report = generate_report(all_results, summary, categories)

    # 保存到本项目 reports/ (禁止写到 D:/FlyBuddy/fm/)
    from data.config import FM_ROOT
    out_dir = Path(FM_ROOT) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M")
    report_path = out_dir / f"{timestamp}_batch_backtest.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告保存: {report_path}")

    # 同时保存 JSON 原始数据
    json_path = out_dir / f"{timestamp}_batch_backtest.json"
    json_data = {
        "summary": valid_summary,
        "categories": {k: v for k, v in categories.items()},
    }
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON 保存: {json_path}")

    # 打印汇总
    print("\n" + "=" * 60)
    print("  汇总 (按 DirAcc 排序)")
    print("=" * 60)
    print(f"{'#':>2} {'品种':>4} {'MAPE':>7} {'DirAcc':>7} {'Decay':>6} {'分类'}")
    print("-" * 50)
    ranked = sorted(valid_summary, key=lambda x: x["dir_acc"], reverse=True)
    for i, r in enumerate(ranked):
        cat = next((c for c, syms in categories.items() if r["symbol"] in syms), "?")
        cat_short = cat.split("(")[0].strip()
        print(f"{i+1:>2} {r['symbol']:>4} {r['mape']:>6.2f}% {r['dir_acc']:>6.0%} {r['decay']:>5.2f}x {cat_short}")

    print("\n分类结果:")
    for cat, syms in categories.items():
        if syms:
            print(f"  {cat}: {', '.join(syms)}")

    print("\n完成。")
