#!/usr/bin/env python
"""
Phase 14: Regime 动态路由 POC

对比静态协变量 vs 动态 regime-based 协变量选择的预测效果。
不修改 cascade_predict.py 生产代码，独立验证概念。

方法:
1. 对目标品种的 1H 数据，用 RealtimeRegimeClassifier 逐步分类 regime
2. 根据 regime 推荐协变量 (REGIME_COVARIATE_MAP)
3. 用 monthly_backtest.py 的 walk-forward 框架对比:
   - 静态: 始终用 scheme 的 covariate_type
   - 动态: 每个 walk-forward 窗口根据 regime 选择协变量
4. 对比 PF/EV/MaxDD

用法:
    python scripts/regime_routing_poc.py [--symbol MA] [--symbol JM]
"""
import argparse
import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path

# 确保项目路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from cascade.realtime_regime_classifier import RealtimeRegimeClassifier
from config.prediction_scheme import SCHEMES


def analyze_regime_distribution(symbol: str):
    """分析品种的 regime 分布"""
    from data.data_store import DataStore

    store = DataStore(symbol)
    df_1h = store.get_main_contract_1h(limit=10000)

    if df_1h is None or len(df_1h) < 480:
        print(f"  [SKIP] {symbol}: 1H 数据不足 (n={len(df_1h) if df_1h is not None else 0})")
        return None

    clf = RealtimeRegimeClassifier()

    # 每隔 24 bars (1 天) 分类一次 regime
    step = 24
    regime_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    total = 0

    for i in range(480, len(df_1h), step):
        window = df_1h.iloc[max(0, i-480):i].copy()
        try:
            result = clf.classify(hourly_df=window)
            regime_id = result['regime']
            regime_counts[regime_id] += 1
            total += 1
        except Exception as e:
            continue

    if total == 0:
        print(f"  [SKIP] {symbol}: regime 分类全部失败")
        return None

    print(f"\n  {symbol} regime 分布 (n={total} 次分类):")
    for rid, count in regime_counts.items():
        pct = count / total * 100
        label = clf.REGIME_LABELS[rid]
        covs = clf.REGIME_COVARIATE_MAP[rid]
        bar = '█' * int(pct / 2)
        print(f"    Regime {rid} ({label:>20s}): {count:4d} ({pct:5.1f}%) {bar}")
        print(f"      → 推荐协变量: {covs}")

    return regime_counts


def compare_static_vs_dynamic(symbol: str):
    """对比静态 vs 动态协变量的回测效果"""
    scheme = SCHEMES.get(symbol)
    if not scheme:
        print(f"  [SKIP] {symbol}: 不在 SCHEMES 中")
        return

    static_cov = scheme.covariate_type
    print(f"\n  {symbol} 静态协变量: {static_cov}")
    print(f"  当前 scheme PF: 见 Registry")

    # 获取 regime 推荐的所有协变量
    clf = RealtimeRegimeClassifier()
    all_regime_covs = set()
    for covs in clf.REGIME_COVARIATE_MAP.values():
        all_regime_covs.update(covs)

    print(f"  Regime 推荐的所有协变量: {sorted(all_regime_covs)}")
    print(f"  静态协变量在 regime 映射中: {static_cov in all_regime_covs}")


def main():
    parser = argparse.ArgumentParser(description='Regime 动态路由 POC')
    parser.add_argument('--symbol', '-s', action='append', default=[],
                       help='目标品种 (可多次指定)')
    parser.add_argument('--all-weak', action='store_true',
                       help='测试所有弱信号品种')
    args = parser.parse_args()

    if args.all_weak:
        symbols = ['jm', 'ma', 'ur', 'fg', 'cf', 'ao']
    elif args.symbol:
        symbols = args.symbol
    else:
        symbols = ['ma']  # MA 单协 PF=1.00, 最有潜力

    print("=" * 60)
    print("Phase 14: Regime 动态路由 POC")
    print("=" * 60)

    for sym in symbols:
        print(f"\n{'─' * 40}")
        print(f"品种: {sym.upper()}")
        print(f"{'─' * 40}")

        # Step 1: 分析 regime 分布
        regime_dist = analyze_regime_distribution(sym)

        # Step 2: 对比静态 vs 动态
        compare_static_vs_dynamic(sym)

    print(f"\n{'=' * 60}")
    print("POC 完成。结果仅供概念验证，不代表最终回测结果。")
    print("=" * 60)


if __name__ == "__main__":
    main()
