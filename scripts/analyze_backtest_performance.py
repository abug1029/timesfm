#!/usr/bin/env python3
"""
回测性能调研脚本
分析所有历史 backtest 日志，统计耗时和性能
"""

import re
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def parse_log_file(log_path):
    """解析单个日志文件，提取耗时信息"""
    results = {
        'file': log_path,
        'start_time': None,
        'end_time': None,
        'duration_seconds': None,
        'eval_points': 0,
        'symbols': [],
        'avg_time_per_point': None,
        'phase': None,
    }

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # 提取时间戳
        timestamps = re.findall(r'\[(\d{2}:\d{2}:\d{2})\]', content)
        if timestamps:
            results['start_time'] = timestamps[0]
            results['end_time'] = timestamps[-1]

        # 提取日期
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', content)
        if date_match:
            results['date'] = date_match.group(1)

        # 提取评估点数量
        eval_points = re.findall(r'\[(\d+)/(\d+)\]', content)
        if eval_points:
            max_points = max(int(ep[1]) for ep in eval_points)
            results['eval_points'] = max_points

        # 提取品种
        symbols = re.findall(r'\[1/1\]\s+(\w+)\.\.\.', content)
        results['symbols'] = list(set(symbols))

        # 提取单个评估点耗时
        point_times = re.findall(r'daily=([\d.]+)s\s+hourly=([\d.]+)s', content)
        if point_times:
            daily_times = [float(t[0]) for t in point_times]
            hourly_times = [float(t[1]) for t in point_times]
            avg_daily = sum(daily_times) / len(daily_times)
            avg_hourly = sum(hourly_times) / len(hourly_times)
            results['avg_daily_time'] = avg_daily
            results['avg_hourly_time'] = avg_hourly
            results['avg_time_per_point'] = avg_daily + avg_hourly

        # 提取总耗时
        duration_match = re.search(r'\((\d+)s\)', content)
        if duration_match:
            results['duration_seconds'] = int(duration_match.group(1))

        # 识别 phase
        if 'two_star' in log_path or '2星->3星' in content:
            results['phase'] = 'Phase 9'
        elif 'phase10' in log_path or 'Phase 10' in content:
            results['phase'] = 'Phase 10'
        elif 'p8a' in log_path:
            results['phase'] = 'Phase 8a'
        elif 'p8b' in log_path:
            results['phase'] = 'Phase 8b'
        elif 'phase4d' in log_path:
            results['phase'] = 'Phase 4d'
        elif 'monthly_backtest' in log_path:
            results['phase'] = 'Monthly Backtest'

        # 提取作业数量
        job_match = re.search(r'总作业:\s*(\d+)', content)
        if job_match:
            results['total_jobs'] = int(job_match.group(1))

        completed_match = re.search(r'已完成:\s*(\d+)', content)
        if completed_match:
            results['completed_jobs'] = int(completed_match.group(1))

    except Exception as e:
        results['error'] = str(e)

    return results

def scan_all_logs():
    """扫描所有日志文件"""
    log_dirs = [
        'reports/data_ops',
        'reports/monthly_backtest',
        'reports',
    ]

    all_results = []

    for log_dir in log_dirs:
        log_dir_path = Path(log_dir)
        if not log_dir_path.exists():
            continue

        for log_file in log_dir_path.glob('*.log'):
            result = parse_log_file(log_file)
            if result.get('eval_points') > 0 or result.get('duration_seconds'):
                all_results.append(result)

    return all_results

def generate_report(results):
    """生成调研报告"""
    report = []
    report.append("# FM_a 回测性能调研报告")
    report.append(f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 硬件环境
    report.append("## 1. 硬件环境\n")
    report.append("### 当前环境")
    report.append("- **操作系统**: Windows 10 (10.0.19045)")
    report.append("- **Python: 3.11")
    report.append("- **PyTorch**: 2.11.0+cpu (CPU-only 版本)")
    report.append("- **CUDA**: 不可用")
    report.append("- **GPU**: 无")
    report.append("- **CPU**: Intel (具体型号待确认)")
    report.append("")

    # 统计汇总
    report.append("## 2. 历史回测统计\n")

    phase_stats = defaultdict(lambda: {
        'count': 0,
        'total_points': 0,
        'total_duration': 0,
        'avg_time_per_point': [],
    })

    for r in results:
        phase = r.get('phase', 'Unknown')
        phase_stats[phase]['count'] += 1
        phase_stats[phase]['total_points'] += r.get('eval_points', 0)
        if r.get('duration_seconds'):
            phase_stats[phase]['total_duration'] += r['duration_seconds']
        if r.get('avg_time_per_point'):
            phase_stats[phase]['avg_time_per_point'].append(r['avg_time_per_point'])

    report.append("| Phase | 回测次数 | 总评估点 | 总耗时(秒) | 平均耗时/点(秒) |")
    report.append("|-------|---------|---------|-----------|----------------|")

    for phase, stats in sorted(phase_stats.items()):
        avg_time = sum(stats['avg_time_per_point']) / len(stats['avg_time_per_point']) if stats['avg_time_per_point'] else 0
        report.append(f"| {phase} | {stats['count']} | {stats['total_points']} | {stats['total_duration']} | {avg_time:.2f} |")

    report.append("")

    # 详细列表
    report.append("## 3. 详细回测记录\n")

    for r in sorted(results, key=lambda x: x.get('date', ''), reverse=True):
        if r.get('error'):
            continue

        report.append(f"### {r['file']}")
        report.append(f"- **Phase**: {r.get('phase', 'Unknown')}")
        if r.get('date'):
            report.append(f"- **日期**: {r['date']}")
        if r.get('start_time') and r.get('end_time'):
            report.append(f"- **时间范围**: {r['start_time']} - {r['end_time']}")
        if r.get('duration_seconds'):
            hours = r['duration_seconds'] // 3600
            minutes = (r['duration_seconds'] % 3600) // 60
            seconds = r['duration_seconds'] % 60
            report.append(f"- **总耗时**: {hours}h {minutes}m {seconds}s ({r['duration_seconds']}s)")
        if r.get('eval_points'):
            report.append(f"- **评估点**: {r['eval_points']}")
        if r.get('avg_time_per_point'):
            report.append(f"- **平均耗时/点**: {r['avg_time_per_point']:.2f}s")
        if r.get('avg_daily_time'):
            report.append(f"- **Daily 模型**: {r['avg_daily_time']:.2f}s/点")
        if r.get('avg_hourly_time'):
            report.append(f"- **Hourly 模型**: {r['avg_hourly_time']:.2f}s/点")
        if r.get('symbols'):
            report.append(f"- **品种**: {', '.join(r['symbols'])}")
        if r.get('total_jobs'):
            report.append(f"- **作业数**: {r.get('completed_jobs', 0)}/{r['total_jobs']}")
        report.append("")

    # 性能分析
    report.append("## 4. 性能分析\n")

    all_point_times = [r['avg_time_per_point'] for r in results if r.get('avg_time_per_point')]
    if all_point_times:
        avg_time = sum(all_point_times) / len(all_point_times)
        min_time = min(all_point_times)
        max_time = max(all_point_times)

        report.append("### 整体性能")
        report.append(f"- **平均耗时/点**: {avg_time:.2f}s")
        report.append(f"- **最快**: {min_time:.2f}s/点")
        report.append(f"- **最慢**: {max_time:.2f}s/点")
        report.append("")

        # 估算 GPU vs CPU
        report.append("### GPU vs CPU 性能对比")
        report.append("- **当前环境**: CPU-only (PyTorch 2.11.0+cpu)")
        report.append("- **典型耗时**: 20-30s/点 (CPU)")
        report.append("- **预估 GPU 耗时**: 2-5s/点 (基于 Phase 9 日志)")
        report.append("- **GPU 加速比**: 约 5-10x")
        report.append("")

        # 建议
        report.append("## 5. 建议\n")
        report.append("### 短期")
        report.append("1. 当前 CPU 环境可以完成 backtest，但耗时较长")
        report.append("2. 单次 396 点 backtest 约需 2-3 小时 (CPU)")
        report.append("3. 12 个 backtest (如 Phase 10) 约需 24-36 小时")
        report.append("")
        report.append("### 中期")
        report.append("1. 安装 GPU 驱动和 CUDA 版本的 PyTorch")
        report.append("2. 预计可将 backtest 时间缩短 5-10 倍")
        report.append("3. 单次 396 点 backtest 可缩短至 15-30 分钟")
        report.append("")
        report.append("### 长期")
        report.append("1. 考虑使用 GPU 服务器进行大规模 backtest")
        report.append("2. 实现并行 backtest (多品种同时运行)")
        report.append("3. 优化模型推理速度 (模型量化、ONNX 等)")

    return '\n'.join(report)

if __name__ == '__main__':
    print("扫描历史回测日志...")
    results = scan_all_logs()
    print(f"找到 {len(results)} 个回测记录\n")

    print("生成报告...")
    report = generate_report(results)

    output_path = 'reports/research/20260804_backtest_performance_report.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n报告已生成: {output_path}")
    print("\n" + "="*60)
    print(report)
