#!/usr/bin/env python3
"""
FM 期货品种一站式分析：采集 + 预测 + 预警
融合脚本，优化输出 UI
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

# 设置 UTF-8 编码（Windows）
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# FM_a 项目根目录
FM_ROOT = Path(__file__).parent.parent

# 品种中文名映射
VARIETY_NAMES = {
    'jd': '鸡蛋', 'ss': '不锈钢', 'rb': '螺纹钢', 'cf': '棉花',
    'p': '棕榈油', 'bu': '沥青', 'ao': '氧化铝', 'ur': '尿素',
    'sr': '白糖', 'jm': '焦煤', 'i': '铁矿石', 'sp': '纸浆',
    'fg': '玻璃', 'ma': '甲醇', 'eg': '乙二醇', 'ta': 'PTA',
    'eb': '苯乙烯', 'pp': '聚丙烯', 'lh': '生猪', 'ni': '镍',
    'sn': '锡', 'zc': '动力煤', 'fu': '燃料油', 'hc': '热卷',
    'cu': '铜', 'al': '铝', 'zn': '锌', 'pb': '铅', 'au': '黄金',
    'ag': '白银', 'ru': '橡胶', 'bu': '沥青', 'm': '豆粕',
    'y': '豆油', 'oi': '菜油', 'rm': '菜粕', 'cs': '玉米淀粉',
    'a': '豆一', 'b': '豆二', 'jd': '鸡蛋', 'lj': '淀粉',
    'bb': '胶合板', 'fb': '纤维板', 'l': '塑料', 'v': 'PVC',
}


def print_header(text: str, char: str = '=', width: int = 70):
    """打印分隔线标题"""
    print(f"\n{char * width}")
    print(f"{text:^{width}}")
    print(f"{char * width}\n")


def print_section(title: str, icon: str = '▶'):
    """打印章节标题"""
    print(f"\n{icon} {title}")
    print('─' * 70)


def run_command(cmd: list, description: str, verbose: bool = False) -> tuple[bool, str]:
    """运行命令并返回 (成功, 输出)"""
    print(f"\n[运行] {description}...")
    if verbose:
        print(f"  命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=not verbose,
            text=True,
            cwd=FM_ROOT,
            timeout=300
        )

        if result.returncode != 0:
            error_msg = result.stderr if not verbose else "见上方输出"
            print(f"  ❌ 失败: {error_msg}")
            return False, error_msg

        output = result.stdout if not verbose else ""
        print(f"  ✓ 完成")
        return True, output

    except subprocess.TimeoutExpired:
        print(f"  ❌ 超时 (>5分钟)")
        return False, "超时"
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return False, str(e)


def collect_data(symbol: str, verbose: bool) -> bool:
    """采集数据"""
    print_section('数据采集', '📊')

    # 日线 + 1H
    cmd = [sys.executable, '-m', 'data.cli', 'collect', symbol]
    success, _ = run_command(cmd, f'采集 {symbol.upper()} 日线+1H数据', verbose)

    if success:
        print(f"  📦 数据已保存到 db/futures_{symbol}.db")

    return success


def run_cascade_prediction(symbol: str, verbose: bool) -> tuple[bool, str]:
    """运行级联预测"""
    print_section('级联预测', '🔮')

    cmd = [sys.executable, 'scripts/cascade_predict.py', symbol]
    success, output = run_command(cmd, f'运行 {symbol.upper()} 级联预测', verbose)

    if success:
        # 查找最新报告
        report_dir = FM_ROOT / 'reports' / symbol
        if report_dir.exists():
            reports = sorted(report_dir.glob('cascade_*.md'), reverse=True)
            if reports:
                return True, str(reports[0])

    return False, ""


def run_variety_analysis(symbol: str, verbose: bool) -> tuple[bool, str]:
    """运行指标预警分析"""
    print_section('指标预警分析', '📈')

    cmd = [sys.executable, 'scripts/variety_analysis.py', symbol, '--no-collect']
    success, output = run_command(cmd, f'运行 {symbol.upper()} 指标预警分析', verbose)

    if success:
        # 查找最新报告 - 尝试多种路径模式
        today = datetime.now().strftime('%Y%m%d')
        search_paths = [
            FM_ROOT / 'reports' / f'{today}_analysis',
            FM_ROOT / 'reports' / symbol,
        ]

        for report_dir in search_paths:
            if report_dir.exists():
                # 查找分析类报告
                patterns = [
                    f'analysis_{symbol}.md',
                    f'*analysis*.md',
                    f'{symbol}*.md',
                ]
                for pattern in patterns:
                    reports = sorted(report_dir.glob(pattern), reverse=True)
                    if reports:
                        return True, str(reports[0])

    return False, ""


def generate_summary_report(
    symbol: str,
    cascade_report: str,
    analysis_report: str,
    output_path: Path
):
    """生成融合摘要报告"""
    print_section('生成融合报告', '📝')

    variety_name = VARIETY_NAMES.get(symbol.lower(), symbol.upper())
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# {variety_name}({symbol.upper()}) 一站式分析报告\n\n")
        f.write(f"**生成时间**: {now}\n\n")
        f.write("---\n\n")

        # 级联预测摘要
        if cascade_report and Path(cascade_report).exists():
            f.write("## 一、级联预测结果\n\n")
            cascade_content = Path(cascade_report).read_text(encoding='utf-8')

            # 提取关键章节
            sections_to_extract = [
                '## 二、未来日线走势预测',
                '## 四、1 小时级别走势预测',
                '### 信号解读',
                '### CCL 异动预警',
            ]

            extracted = extract_sections(cascade_content, sections_to_extract, max_chars=3000)
            if extracted:
                f.write(extracted)
            else:
                # 如果提取失败，写入前 2000 字符
                f.write(cascade_content[:2000] + "\n\n... (内容截断)\n\n")

            f.write(f"\n**完整报告**: `{cascade_report}`\n\n")

        f.write("---\n\n")

        # 指标预警摘要
        if analysis_report and Path(analysis_report).exists():
            f.write("## 二、指标预警分析\n\n")
            analysis_content = Path(analysis_report).read_text(encoding='utf-8')

            # 提取关键章节
            sections_to_extract = [
                '## 综合判断',
                '## 价格走势',
                '## 技术指标',
                '## 持仓分析',
                '## CCL',
                '## Copilot',
            ]

            extracted = extract_sections(analysis_content, sections_to_extract, max_chars=3000)
            if extracted:
                f.write(extracted)
            else:
                # 如果提取失败，写入前 2000 字符
                f.write(analysis_content[:2000] + "\n\n... (内容截断)\n\n")

            f.write(f"\n**完整报告**: `{analysis_report}`\n\n")

        f.write("---\n\n")

        # 文件路径汇总
        f.write("## 三、生成文件\n\n")
        f.write(f"- 融合报告: `{output_path}`\n")
        if cascade_report:
            f.write(f"- 级联预测: `{cascade_report}`\n")
        if analysis_report:
            f.write(f"- 指标预警: `{analysis_report}`\n")

        f.write("\n---\n\n")
        f.write("> **风险提示**: 本报告基于 TimesFM 统计模型 + 技术指标，仅供参考，不构成投资建议。\n")

    print(f"  ✓ 融合报告已保存: {output_path}")


def extract_sections(content: str, section_markers: list, max_chars: int = 3000) -> str:
    """从 Markdown 内容中提取指定章节"""
    lines = content.split('\n')
    extracted_sections = []
    current_section = []
    in_section = False
    current_marker = None

    for line in lines:
        # 检查是否进入目标章节
        if any(marker in line for marker in section_markers):
            # 保存之前的章节
            if in_section and current_section:
                extracted_sections.append('\n'.join(current_section))

            # 开始新章节
            in_section = True
            current_section = [line]
            current_marker = line
            continue

        # 如果在章节中，继续收集
        if in_section:
            # 遇到下一个 ## 章节时停止（但保留当前行如果是目标章节）
            if line.startswith('## ') and not any(marker in line for marker in section_markers):
                in_section = False
                extracted_sections.append('\n'.join(current_section))
                current_section = []
            else:
                current_section.append(line)

    # 保存最后一个章节
    if in_section and current_section:
        extracted_sections.append('\n'.join(current_section))

    # 合并所有章节
    result = '\n\n'.join(extracted_sections)

    # 如果超过最大字符数，截断
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n... (内容截断)"

    return result


def main():
    parser = argparse.ArgumentParser(
        description='FM 期货品种一站式分析：采集 + 预测 + 预警',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/fm_collect_analyze.py jd          # 采集 JD 数据并分析
  python scripts/fm_collect_analyze.py ss --no-collect  # 跳过采集，直接分析
  python scripts/fm_collect_analyze.py rb --verbose     # 显示详细输出
        """
    )

    parser.add_argument('symbol', help='品种代码 (如 jd, ss, rb)')
    parser.add_argument('--no-collect', action='store_true', help='跳过数据采集')
    parser.add_argument('--no-predict', action='store_true', help='跳过级联预测')
    parser.add_argument('--no-analysis', action='store_true', help='跳过指标预警')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细输出')

    args = parser.parse_args()

    symbol = args.symbol.lower()
    variety_name = VARIETY_NAMES.get(symbol, symbol.upper())

    # 打印横幅
    print_header(f'{variety_name}({symbol.upper()}) 一站式分析', '=')
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工作目录: {FM_ROOT}")

    # 检查环境
    if not (FM_ROOT / 'CLAUDE.md').exists():
        print(f"\n❌ 错误: 未在 FM_a 项目目录中找到 CLAUDE.md")
        print(f"  请确保在 D:/FlyBuddy/FM_a 目录下运行")
        sys.exit(1)

    cascade_report = ""
    analysis_report = ""

    # 第 1 步：采集数据
    if not args.no_collect:
        if not collect_data(symbol, args.verbose):
            print(f"\n⚠ 数据采集失败，继续尝试使用现有数据...")

    # 第 2 步：级联预测
    if not args.no_predict:
        success, report_path = run_cascade_prediction(symbol, args.verbose)
        if success:
            cascade_report = report_path
        else:
            print(f"\n⚠ 级联预测失败")

    # 第 3 步：指标预警
    if not args.no_analysis:
        success, report_path = run_variety_analysis(symbol, args.verbose)
        if success:
            analysis_report = report_path
        else:
            print(f"\n⚠ 指标预警分析失败")

    # 第 4 步：生成融合报告
    if cascade_report or analysis_report:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        output_path = FM_ROOT / 'reports' / symbol / f'collect_analyze_{timestamp}.md'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        generate_summary_report(symbol, cascade_report, analysis_report, output_path)

        print_header('分析完成', '=')
        print(f"融合报告: {output_path}")

        if cascade_report:
            print(f"级联预测: {cascade_report}")
        if analysis_report:
            print(f"指标预警: {analysis_report}")

    else:
        print("\n❌ 所有分析均失败，请检查日志")
        sys.exit(1)


if __name__ == '__main__':
    main()
