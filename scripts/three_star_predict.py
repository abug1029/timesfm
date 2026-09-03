"""
信用档预测（历史名 three_star）— 一键运行 scheme.stars≥2 品种

2026-08-08 新口径 rebaseline 后系统内无 3 星；本脚本跑 **≥2 星信用档**
（见 reports/research/20260808_g005e_results.md）。

用法:
  python scripts/three_star_predict.py                # stars≥2
  python scripts/three_star_predict.py --collect
  python scripts/three_star_predict.py --horizon 48
  python scripts/three_star_predict.py --show-schemes

输出:
  1. 各品种独立报告: reports/<symbol>/cascade_YYYYMMDD_HHmm.md
  2. 汇总: reports/summaries/YYYYMMDD_HHmm_three_star.md（文件名兼容）
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from config.prediction_scheme import (
    SCHEMES, list_solidified, list_by_stars, get_scheme, is_solidified,
    signal_weight, trend_direction, scheme_summary,
)
from data.config import DEFAULT_SYMBOLS


def ensure_data(symbol: str) -> dict:
    """确保品种数据已采集 (结构化结果, 失败可见)

    2026-08-30 原子化: 返回 {ok, error} 结构, 异常不再向上抛 (调用方按 ok 判断),
    失败打印 [FAIL] 而非仅 [WARN]。原实现内联为 _ensure_data_impl (逻辑零变更)。

    Returns:
        {"symbol": str, "ok": bool, "error": str | None}
    """
    try:
        _ensure_data_impl(symbol)
        return {"symbol": symbol, "ok": True, "error": None}
    except Exception as e:
        print(f"  [FAIL] {symbol.upper()} 数据采集失败: {e}")
        return {"symbol": symbol, "ok": False, "error": str(e)}


def _ensure_data_impl(symbol: str):
    """ensure_data 的原实现 (采集日线/主链/1H, 内置数据量+日期保护)"""
    from data.tqsdk_fetcher import UnifiedFetcher
    from data.indicator_calculator import IndicatorCalculator
    from data.main_chain import MainChainBuilder
    from data.data_store import DataStore

    fetcher = UnifiedFetcher()
    calculator = IndicatorCalculator()

    with DataStore(symbol) as store:
        # 采集主力连续合约日线 (_CONT)
        cont_code = f"{symbol.upper()}_CONT"
        df = fetcher.get_main_continuous_kline(symbol, dur_sec=86400, data_length=3000)
        if not df.empty:
            # 数据量保护: TqSdk 网络异常可能返回部分数据，避免用少量数据覆盖历史
            MIN_DAILY_ROWS = 100  # 健康的主力连续日线应远超此阈值
            if len(df) < MIN_DAILY_ROWS:
                print(f"  [WARN] {symbol.upper()}: 日线新数据仅 {len(df)} 行 (< {MIN_DAILY_ROWS})，"
                      f"可能采集不完整，跳过覆盖")
            else:
                # 日期保护: 新数据最新日期 >= 已有数据最新日期，防止用旧数据覆盖新数据
                existing = store.conn.execute(
                    "SELECT MAX(dt) FROM kline_1d WHERE contract_code = ?", (cont_code,)
                ).fetchone()
                if existing and existing[0]:
                    existing_latest = pd.to_datetime(existing[0])
                    new_latest = pd.to_datetime(df["dt"].max())
                    if new_latest < existing_latest:
                        print(f"  [WARN] {symbol.upper()}: 新数据 ({new_latest.strftime('%Y-%m-%d')}) "
                              f"早于已有数据 ({existing_latest.strftime('%Y-%m-%d')})，跳过覆盖")
                    else:
                        df = df.rename(columns={'dt': 'date'})
                        df['contract_code'] = cont_code
                        df = calculator.calculate_all(df)
                        df = df.rename(columns={'open': 'open_price', 'close': 'close_price'})
                        # store_klines 内部用 INSERT OR REPLACE，安全增量更新，无需 DELETE
                        store.store_klines(cont_code, df)
                else:
                    df = df.rename(columns={'dt': 'date'})
                    df['contract_code'] = cont_code
                    df = calculator.calculate_all(df)
                    df = df.rename(columns={'open': 'open_price', 'close': 'close_price'})
                    store.store_klines(cont_code, df)

        # 主链同步 (kline_1d _CONT → main_continuous_1d)
        kline_contracts = store.discover_contracts_from_kline()
        if kline_contracts:
            builder = MainChainBuilder(symbol)
            builder.build()

        # 1H 数据 (采集主力连续到 _MAIN)
        main_code = f"{symbol.upper()}_MAIN"
        df_1h = fetcher.get_main_continuous_kline(symbol, dur_sec=3600, data_length=10000)
        if not df_1h.empty:
            # 数据量保护
            MIN_1H_ROWS = 500
            if len(df_1h) < MIN_1H_ROWS:
                print(f"  [WARN] {symbol.upper()}: 1H 新数据仅 {len(df_1h)} 行 (< {MIN_1H_ROWS})，"
                      f"可能采集不完整，跳过覆盖")
            else:
                # 日期保护
                existing_1h = store.conn.execute(
                    "SELECT MAX(dt) FROM kline_1h WHERE contract_code = ?", (main_code,)
                ).fetchone()
                if existing_1h and existing_1h[0]:
                    existing_1h_latest = pd.to_datetime(existing_1h[0])
                    new_1h_latest = pd.to_datetime(df_1h["dt"].max())
                    if new_1h_latest < existing_1h_latest:
                        print(f"  [WARN] {symbol.upper()}: 1H 新数据 ({new_1h_latest.strftime('%Y-%m-%d')}) "
                              f"早于已有数据 ({existing_1h_latest.strftime('%Y-%m-%d')})，跳过覆盖")
                    else:
                        df_1h = df_1h.rename(columns={'dt': 'date'})
                        df_1h['contract_code'] = main_code
                        df_1h = calculator.calculate_all(df_1h)
                        df_1h = df_1h.rename(columns={'open': 'open_price', 'close': 'close_price'})
                        # store_klines_1h 内部用 INSERT OR REPLACE，安全增量更新
                        store.store_klines_1h(main_code, df_1h)
                else:
                    df_1h = df_1h.rename(columns={'dt': 'date'})
                    df_1h['contract_code'] = main_code
                    df_1h = calculator.calculate_all(df_1h)
                    df_1h = df_1h.rename(columns={'open': 'open_price', 'close': 'close_price'})
                    store.store_klines_1h(main_code, df_1h)

        # 提取 xreg (注: 当前协变量从 kline_1h 实时计算，xreg_factors 表为历史遗留，
        # 保留写入仅为数据一致性，预测时不读取此表)
        from scripts.predict import _extract_xreg_from_store
        _extract_xreg_from_store(store, symbol)


def run_all_three_star(horizon: int = 24, collect: bool = False, auto_collect: bool = True):
    """运行信用≥2星品种级联预测，返回各品种结果和汇总报告"""
    from scripts.cascade_predict import run_cascade
    from cascade.data_validator import ensure_fresh_data
    from data.data_store import DataStore

    symbols = list_by_stars(2)
    if not symbols:
        print("  [WARN] 无 stars≥2 品种，回退全部固化列表")
        symbols = list_solidified()
    results = {}
    reports = {}

    # 进度日志 (供 Monitor 事件驱动监控)
    reports_base = Path(__file__).resolve().parent.parent / "reports"
    summaries_dir = reports_base / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    progress_log = summaries_dir / "three_star_progress.log"
    with open(progress_log, 'w', encoding='utf-8') as f:
        f.write(f"START {datetime.now().isoformat()}\n")

    # ── 阶段 0: 强制采集 (仅 --collect) ──
    # 2026-08-30 原子化: 结构化结果 + 失败可见 (不再静默 WARN-only)
    if collect:
        force_failed = []
        for symbol in symbols:
            print(f"  采集数据: {symbol.upper()}...")
            r = ensure_data(symbol)
            if not r["ok"]:
                force_failed.append(f"{symbol.upper()}({r['error']})")
        if force_failed:
            print(f"  [WARN] {len(force_failed)} 品种强制采集失败: {', '.join(force_failed)}"
                  f"；阶段 1 ensure_fresh_data 将按需重试")

    # ── 阶段 1: 预检查所有品种数据 + 自动采集 ──
    print(f"  [预检查] 验证 {len(symbols)} 个品种的数据"
          f"{' (auto-collect 已启用)' if auto_collect else ''}...")
    valid_symbols, skipped_symbols = ensure_fresh_data(symbols, auto_collect=auto_collect)

    # 记录跳过信息到进度日志
    with open(progress_log, 'a', encoding='utf-8') as f:
        for skip in skipped_symbols:
            f.write(f"[SKIP] {skip['symbol'].upper()} {skip['error']}\n")
        for s in valid_symbols:
            f.write(f"[OK] {s.upper()} 数据校验通过\n")

    if not valid_symbols:
        print("无有效品种可预测 (全部数据校验失败)")
        return results, reports

    # ── 阶段 2: 预加载共享模型 + 逐品种预测 ──
    from cascade.daily_model import DailyModel
    print(f"\n  加载 TimesFM 2.5 模型 (共享)...")
    bootstrap = DailyModel()
    shared_model = bootstrap.model
    print(f"  模型已加载")

    for i, symbol in enumerate(valid_symbols):
        scheme = get_scheme(symbol)
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(valid_symbols)}] {symbol.upper()} ({scheme.name}) "
              f"— ⭐⭐⭐ {scheme.scheme_type}")
        print(f"{'='*60}")
        with open(progress_log, 'a', encoding='utf-8') as f:
            f.write(f"[{i+1}/{len(valid_symbols)}] {symbol.upper()} START\n")

        try:
            report, result_data = run_cascade(
                symbol, horizon=horizon, visualize=True,
                shared_model=shared_model)
            reports[symbol] = report

            # 直接从 run_cascade 返回的 result_data 提取指标 (不重复加载模型)
            with DataStore(symbol) as store:
                last_1h = store.get_main_contract_1h(limit=1)
                last_close = float(last_1h["close_price"].iloc[-1]) \
                    if not last_1h.empty else result_data.get("t1", 0)

            w = signal_weight(horizon, scheme)
            fc_min = result_data.get("t1", 0)  # T+1 近似最小值
            fc_max = result_data.get("t24", 0)  # T+24 近似最大值

            results[symbol] = {
                "name": scheme.name,
                "scheme_type": scheme.scheme_type,
                "dir_acc": scheme.dir_acc,
                "mape": scheme.mape,
                "decay": scheme.decay,
                "direction": result_data.get("direction", "中性 →"),
                "slope_pct": result_data.get("slope", 0),
                "weighted_pred": result_data.get("weighted_pred"),
                "final_pred": result_data.get("t24", 0),
                "last_close": last_close,
                "change_pct": result_data.get("delta_pct", 0),
                "fc_range": (fc_min, fc_max),
            }
            with open(progress_log, 'a', encoding='utf-8') as f:
                f.write(f"[{i+1}/{len(valid_symbols)}] {symbol.upper()} OK\n")
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
            with open(progress_log, 'a', encoding='utf-8') as f:
                f.write(f"[{i+1}/{len(valid_symbols)}] {symbol.upper()} ERROR {e}\n")

    with open(progress_log, 'a', encoding='utf-8') as f:
        f.write(f"DONE {datetime.now().isoformat()}\n")

    # 保存各品种独立报告 (按品种分类)
    summaries_dir = reports_base / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    for symbol, report in reports.items():
        symbol_dir = reports_base / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        report_path = symbol_dir / f"cascade_{ts}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n  独立报告保存: {report_path}")

    # 生成汇总报告
    summary = _build_summary_report(results, ts)
    summary_path = summaries_dir / f"{ts}_three_star.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"\n  汇总报告保存: {summary_path}")

    return results, reports


def _build_summary_report(results: dict, timestamp: str) -> str:
    """生成三星品种汇总报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 三星品种固化预测汇总报告",
        f"",
        f"| 字段 | 值 |",
        f"|------|-----|",
        f"| 生成日期 | {now} |",
        f"| 模型 | TimesFM 2.5 级联 (日线→1H XReg) |",
        f"| 固化方案版本 | 2026-06 |",
        f"| 三星品种 | SS (不锈钢), UR (尿素), SR (白糖) |",
        f"",
        "---",
        f"",
    ]

    # ── 方案概览 ──
    lines.append("## 固化方案概览")
    lines.append("")
    for symbol, r in results.items():
        scheme = get_scheme(symbol)
        lines.append(f"### {r['name']} ({symbol.upper()}) — {'⭐' * scheme.stars}")
        lines.append("")
        lines.append(f"- 类型: {r['scheme_type']}")
        lines.append(f"- DirAcc: {r['dir_acc']:.0%} | MAPE: {r['mape']:.2f}% | 衰减: {r['decay']:.2f}x")
        lines.append(f"- 信号策略: {'全段' if scheme.use_full_signal else '短段'} | "
                     f"置信乘数: {scheme.confidence_multiplier:.2f}")
        lines.append("")

    # ── 横向对比 ──
    lines.extend(["## 预测结果横向对比", "",
                  "| 品种 | 类型 | 最新价 | 加权预测 | 预期变动 | 方向 | 信号可信度 |",
                  "|------|------|------:|--------:|--------:|:----:|:----------:|"])
    for symbol, r in results.items():
        lines.append(
            f"| {r['name']} {symbol.upper()} | {r['scheme_type']} "
            f"| {r['last_close']:,.0f} | {r['weighted_pred']:,.0f} "
            f"| {r['change_pct']:+.2f}% | {r['direction']} "
            f"| DirAcc={r['dir_acc']:.0%} |"
        )
    lines.append("")

    # ── 各品种核心结论 ──
    lines.extend(["## 各品种核心结论", ""])
    for symbol, r in results.items():
        scheme = get_scheme(symbol)
        w = signal_weight(24, scheme)
        lines.extend([
            f"### {r['name']} ({symbol.upper()})",
            "",
            f"**方向判断**: {r['direction']} (斜率 {r['slope_pct']:+.3f}%/天)",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 最新 1H 收盘 | {r['last_close']:,.0f} |",
            f"| 加权预测价 | {r['weighted_pred']:,.0f} ({r['change_pct']:+.2f}%) |",
            f"| T+24 预测价 | {r['final_pred']:,.0f} |",
            f"| 预测区间 | {r['fc_range'][0]:,.0f} ~ {r['fc_range'][1]:,.0f} |",
            f"| 信号可信度 | DirAcc={r['dir_acc']:.0%}, MAPE={r['mape']:.2f}% |",
            "",
        ])

    # ── 操作建议 ──
    lines.extend([
        "## 操作建议",
        "",
        "| 品种 | 信号等级 | 建议 |",
        "|------|:--------:|------|",
    ])
    for symbol, r in results.items():
        scheme = get_scheme(symbol)
        if r['dir_acc'] >= 0.70:
            advice = "强信号，可直接参考级联预测方向"
        elif r['dir_acc'] >= 0.60:
            advice = "较强信号，配合其他指标使用"
        else:
            advice = "中等信号，建议结合基本面判断"
        lines.append(f"| {r['name']} {symbol.upper()} | {'⭐' * scheme.stars} | {advice} |")
    lines.append("")

    lines.extend([
        "---",
        "",
        "> ⚠️ **风险提示**: 本预测基于 TimesFM 统计模型 + XReg 跨周期协变量，不含基本面信息，仅供参考，不构成投资建议。",
        "> 固化方案参数基于历史回测，未来表现可能与历史不一致。",
        "",
    ])
    return "\n".join(lines)


def show_schemes():
    """仅显示固化方案信息"""
    print("\n  三星品种固化预测方案 (2026-06)")
    print("  " + "=" * 50)
    for symbol, scheme in SCHEMES.items():
        print(f"\n  {scheme.name} ({symbol.upper()}) — {'⭐' * scheme.stars}")
        print(f"    类型: {scheme.scheme_type}")
        print(f"    DirAcc: {scheme.dir_acc:.0%} | MAPE: {scheme.mape:.2f}% | 衰减: {scheme.decay:.2f}x")
        print(f"    Context: {scheme.context_bars} bars (1H) / {scheme.context_days} days (日线)")
        print(f"    Horizon: {scheme.horizon_bars} bars (1H) / {scheme.horizon_days} days (日线)")
        print(f"    信号策略: {'全段 T+1~T+24' if scheme.use_full_signal else '短段 T+1~T+12'}")
        print(f"    置信乘数: {scheme.confidence_multiplier:.2f}")
        print(f"    协变量: {', '.join(scheme.xreg_covariates)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="三星品种固化预测 (SS/UR/SR)")
    parser.add_argument("--collect", action="store_true", help="先采集所有品种数据再预测 (显式全量采集)")
    parser.add_argument("--no-auto-collect", action="store_true",
                        help="禁用自动采集 (默认在预校验失败时自动采集过期品种)")
    parser.add_argument("--horizon", type=int, default=24, help="1H 预测时域 (小时, 默认 24)")
    parser.add_argument("--show-schemes", action="store_true", help="仅显示固化方案信息")
    args = parser.parse_args()

    if args.show_schemes:
        show_schemes()
        return

    print("\n" + "=" * 60)
    print("  三星品种固化预测 (SS / UR / SR)")
    print(f"  Horizon: {args.horizon} 小时 | Collect: {args.collect}")
    print("=" * 60)

    auto_collect = not args.no_auto_collect
    run_all_three_star(horizon=args.horizon, collect=args.collect, auto_collect=auto_collect)

    print(f"\n{'='*60}")
    print("  三星品种预测完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
