"""
整理历史预测报告，按品种分类保存

将 reports/ 下的旧格式预测报告移动到 reports/history/{symbol}/ 目录:
- 旧日期目录 reports/YYYYMMDD_HHmm/cascade_<symbol>.md → reports/history/<symbol>/
- 旧分析目录 reports/YYYYMMDD_analysis/analysis_<symbol>.md → reports/history/<symbol>/
- 旧散落文件 reports/YYYYMMDD_HHmm_cascade_<symbol>.md → reports/history/<symbol>/

新格式报告 (reports/<symbol>/) 已在正确位置，无需整理。
"""

import os
import re
import shutil
from pathlib import Path
from datetime import datetime

# 品种代码列表 (从 data.config 动态获取)
try:
    from data.config import DEFAULT_SYMBOLS
    SYMBOLS = DEFAULT_SYMBOLS
except ImportError:
    SYMBOLS = [
        'ss', 'ur', 'sr', 'sp', 'fu', 'm', 'jm', 'i', 'rb', 'fg',
        'bu', 'p', 'cf', 'ao', 'jd', 'lh', 'ma', 'eg', 'ta', 'cj',
        'pp', 'px', 'bz', 'eb', 'y', 'oi',
    ]

# 保留的目录名 (不按品种处理)
RESERVED_DIRS = {'history', 'monthly_backtest', 'summaries', 'research'}


def organize_reports():
    """整理报告文件"""
    reports_dir = Path(__file__).resolve().parent.parent / "reports"
    history_dir = reports_dir / "history"

    # 确保历史目录存在
    for symbol in SYMBOLS:
        (history_dir / symbol).mkdir(parents=True, exist_ok=True)

    moved_count = 0

    # 1. 移动旧日期目录中的报告 (reports/YYYYMMDD_HHmm/)
    for subdir in reports_dir.iterdir():
        if not subdir.is_dir():
            continue
        if subdir.name in RESERVED_DIRS:
            continue
        # 跳过品种目录 (reports/<symbol>/)
        if subdir.name.lower() in SYMBOLS:
            continue

        # 旧格式: YYYYMMDD_HHmm 目录
        if re.match(r'^\d{8}_\d{4}$', subdir.name):
            for report_file in subdir.glob('cascade_*.md'):
                match = re.search(r'cascade_([a-z]+)\.md$', report_file.name)
                if match:
                    symbol = match.group(1)
                    if symbol in SYMBOLS:
                        new_name = f"{subdir.name}_cascade_{symbol}.md"
                        dest = history_dir / symbol / new_name
                        if not dest.exists():
                            print(f"移动: {report_file} -> {dest}")
                            shutil.copy2(report_file, dest)
                            moved_count += 1

        # 旧格式: YYYYMMDD_analysis 目录
        if re.match(r'^\d{8}_analysis$', subdir.name):
            for report_file in subdir.glob('analysis_*.md'):
                match = re.search(r'analysis_([a-z]+)\.md$', report_file.name)
                if match:
                    symbol = match.group(1)
                    if symbol in SYMBOLS:
                        new_name = f"{subdir.name}_analysis_{symbol}.md"
                        dest = history_dir / symbol / new_name
                        if not dest.exists():
                            print(f"移动: {report_file} -> {dest}")
                            shutil.copy2(report_file, dest)
                            moved_count += 1

    # 2. 移动散落的旧格式报告文件 (reports/YYYYMMDD_HHmm_cascade_*.md)
    for report_file in reports_dir.glob('*_cascade_*.md'):
        match = re.search(r'(\d{8}_\d{4})_cascade_([a-z]+)\.md$', report_file.name)
        if match:
            symbol = match.group(2)
            if symbol in SYMBOLS:
                dest = history_dir / symbol / report_file.name
                if not dest.exists():
                    print(f"移动: {report_file} -> {dest}")
                    shutil.copy2(report_file, dest)
                    moved_count += 1

    if moved_count == 0:
        print("没有需要整理的旧报告 (所有报告已按品种分类)")
    else:
        print(f"\n共移动 {moved_count} 份报告")

    # 统计每个品种的报告数量
    print("\n各品种历史报告数量:")
    for symbol in SYMBOLS:
        symbol_dir = history_dir / symbol
        count = len(list(symbol_dir.glob('*.md')))
        if count > 0:
            print(f"  {symbol.upper()}: {count} 份")

    # 统计当前按品种分类的报告
    print("\n当前按品种分类的报告目录:")
    for symbol in SYMBOLS:
        symbol_dir = reports_dir / symbol
        if symbol_dir.exists():
            cascade_count = len(list(symbol_dir.glob('cascade_*.md')))
            analysis_count = len(list(symbol_dir.glob('analysis_*.md')))
            if cascade_count or analysis_count:
                print(f"  {symbol.upper()}: {cascade_count} 预测 + {analysis_count} 分析")


if __name__ == '__main__':
    organize_reports()
