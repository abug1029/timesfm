#!/usr/bin/env python3
"""
离线验证脚本 - 测试实时 Regime 分类器

验证逻辑：
1. 加载 SS 和 P 过去 3 个月的 1H 历史数据
2. 运行 realtime_regime_classifier.py
3. 可视化 Regime 状态切分图
4. 人工比对 K 线，确认分类器判断符合直觉

使用：
    python scripts/validate_regime_classifier.py --varieties ss p --months 3
"""

import sys
import os
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from cascade.realtime_regime_classifier import RealtimeRegimeClassifier
from data.data_store import DataStore


def load_historical_data(
    variety: str,
    months: int = 3
) -> pd.DataFrame:
    """
    加载历史 1H 数据

    Args:
        variety: 品种代码（如 'ss', 'p'）
        months: 回看月数（默认 3）

    Returns:
        1H OHLCV DataFrame (columns: open, high, low, close, volume, open_interest)
    """
    print(f"正在加载 {variety.upper()} 过去 {months} 个月数据...")

    with DataStore(variety) as store:
        # 计算需要的 bar 数（每月约 30 天，每天 24 bar）
        bars_needed = months * 30 * 24

        # 加载 1H 数据
        df = store.get_main_contract_1h(limit=bars_needed)

    if df is None or df.empty:
        print(f"[ERROR] 无法加载 {variety} 的 1H 数据")
        return None

    # 重命名列以匹配 regime_features.py 的期望
    df = df.rename(columns={
        'open_price': 'open',
        'close_price': 'close'
    })

    print(f"  数据量: {len(df)} bars")
    print(f"  时间范围: {df['dt'].min()} ~ {df['dt'].max()}")

    return df


def validate_single_variety(
    variety: str,
    classifier: RealtimeRegimeClassifier,
    months: int = 3
) -> dict:
    """
    验证单个品种的 Regime 分类

    Returns:
        {
            'variety': str,
            'data': pd.DataFrame,
            'regime_df': pd.DataFrame,
            'stats': dict
        }
    """
    # 加载数据
    hourly_df = load_historical_data(variety, months)

    if hourly_df is None:
        return None

    # 运行分类
    print(f"\n正在对 {variety.upper()} 进行 Regime 分类...")
    regime_df = classifier.classify_history(hourly_df, step=10)

    # 统计信息
    stats = {
        'total_bars': len(hourly_df),
        'classified_bars': len(regime_df),
        'regime_distribution': regime_df['label'].value_counts().to_dict(),
        'avg_confidence': regime_df['confidence'].mean(),
        'stable_ratio': regime_df['stable'].mean()  # 通过迟滞确认的比例
    }

    return {
        'variety': variety,
        'data': hourly_df,
        'regime_df': regime_df,
        'stats': stats
    }


def print_validation_report(results: list):
    """打印验证报告"""
    print("\n" + "=" * 60)
    print("REGIME CLASSIFIER VALIDATION REPORT")
    print("=" * 60)

    for result in results:
        if result is None:
            continue

        variety = result['variety']
        stats = result['stats']

        print(f"\n### {variety.upper()} ###")
        print(f"数据量: {stats['total_bars']} bars")
        print(f"已分类: {stats['classified_bars']} bars")
        print(f"平均置信度: {stats['avg_confidence']:.2%}")
        print(f"迟滞确认率: {stats['stable_ratio']:.2%}")

        print("\nRegime 分布:")
        for label, count in stats['regime_distribution'].items():
            print(f"  - {label}: {count} bars")


def main():
    parser = argparse.ArgumentParser(
        description='离线验证实时 Regime 分类器'
    )

    parser.add_argument(
        '--varieties',
        nargs='+',
        default=['ss', 'p'],
        help='品种列表（默认: ss p）'
    )

    parser.add_argument(
        '--months',
        type=int,
        default=3,
        help='回看月数（默认: 3）'
    )

    parser.add_argument(
        '--hysteresis',
        type=int,
        default=3,
        help='迟滞 bar 数（默认: 3）'
    )

    parser.add_argument(
        '--confidence',
        type=float,
        default=0.6,
        help='置信度阈值（默认: 0.6）'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("OFFLINE VALIDATION: REALTIME REGIME CLASSIFIER")
    print("=" * 60)
    print(f"品种: {', '.join([v.upper() for v in args.varieties])}")
    print(f"回看: {args.months} 个月")
    print(f"迟滞: {args.hysteresis} bars")
    print(f"置信度阈值: {args.confidence:.2f}")
    print("=" * 60)

    # 初始化分类器
    classifier = RealtimeRegimeClassifier(
        hysteresis_bars=args.hysteresis,
        confidence_threshold=args.confidence,
        lookback_window=480  # 20 天
    )

    # 验证每个品种
    results = []
    for variety in args.varieties:
        result = validate_single_variety(variety, classifier, args.months)
        results.append(result)

    # 打印报告
    print_validation_report(results)

    # 可视化
    print("\n" + "=" * 60)
    print("VISUALIZATION")
    print("=" * 60)

    for result in results:
        if result is None:
            continue

        variety = result['variety']
        output_path = f'reports/regime_validation_{variety}_{args.months}m.png'

        print(f"\n正在生成 {variety.upper()} 的可视化图...")
        try:
            classifier.visualize_regimes(
                result['data'],
                result['regime_df'],
                output_path
            )
        except Exception as e:
            print(f"[ERROR] 可视化失败: {e}")

    print("\n" + "=" * 60)
    print("VALIDATION COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    main()
