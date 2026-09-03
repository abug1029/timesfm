"""Baseline PF 全品种核实脚本

目标: 对所有 21 个品种运行 monthly_backtest.py --with-baseline,
收集真实 baseline PF, 对比 STATE.md 和 prediction_scheme.py 中的值.

方法:
1. 从 prediction_scheme.py 注释中提取 G005 PF 值
2. 从 STATE.md 中提取记录的 baseline PF
3. 运行 monthly_backtest.py --with-baseline 获取真实值
4. 对比并生成核实报告

用法:
    python scripts/verify_all_baselines.py                    # 全量核实 (42-63 分钟)
    python scripts/verify_all_baselines.py --quick            # 仅核实已知问题品种
    python scripts/verify_all_baselines.py --dry-run          # 仅提取注释值, 不运行回测
"""
import re
import sys
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PYTHONIOENCODING"] = "utf-8"

from config.prediction_scheme import SCHEMES

# 所有 21 个品种
ALL_VARIETIES = list(SCHEMES.keys())

# 已知问题品种 (Phase 15 审核发现 baseline 不一致)
KNOWN_ISSUES = ["jm", "ma", "ur", "fg", "cf", "ao"]

# ── 从 prediction_scheme.py 注释中提取 G005 PF 值 ──
# 这些是人工写入的注释, 格式如: "G005-E: PF=1.15"
G005_PF_REGEX = re.compile(r"G005[–\-][A-E]:\s*PF=([\d.]+)")

def extract_g005_pf_from_scheme() -> dict:
    """从 prediction_scheme.py 源码中提取 G005 PF 注释值"""
    scheme_file = Path(__file__).parent.parent / "config" / "prediction_scheme.py"
    content = scheme_file.read_text(encoding="utf-8")

    pf_values = {}
    for sym in ALL_VARIETIES:
        # 查找该品种的 VarietyScheme 定义块
        pattern = rf'"{sym}":\s*VarietyScheme\((.*?)\),'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            block = match.group(1)
            pf_match = G005_PF_REGEX.search(block)
            if pf_match:
                pf_values[sym] = float(pf_match.group(1))
            else:
                # 尝试从 stars 注释中提取
                stars_match = re.search(r'stars=\d+.*?PF=([\d.]+)', block)
                if stars_match:
                    pf_values[sym] = float(stars_match.group(1))
                else:
                    pf_values[sym] = None

    return pf_values

# ── 从 STATE.md 中提取 baseline PF ──
def extract_state_md_baselines() -> dict:
    """从 STATE.md 中提取记录的 baseline PF"""
    state_file = Path(__file__).parent.parent / "STATE.md"
    content = state_file.read_text(encoding="utf-8")

    # Phase 15 表格 (第 469-476 行附近)
    p15_baselines = {}
    p15_pattern = r'\|\s*(\w+)\s*\|\s*([\d.]+)\s*\|'
    for match in re.finditer(p15_pattern, content):
        sym = match.group(1).lower()
        if sym in ALL_VARIETIES:
            p15_baselines[sym] = float(match.group(2))

    return p15_baselines

def run_backtest_current_covariate(symbol: str, max_points: int = 396) -> dict:
    """运行 monthly_backtest.py 获取当前固化协变量的 PF

    注意: baseline PF 不是直接运行的, 而是通过对比 ha_body (默认协变量)
    和当前固化协变量的回测结果来获得的.

    这里我们先运行当前固化协变量的回测, 获取当前 PF.
    """
    cmd = [
        sys.executable,
        "scripts/monthly_backtest.py",
        symbol,
        "--max-points", str(max_points),
    ]

    print(f"  运行: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        print(f"  [FAIL] 失败: {result.stderr[:200]}")
        return {"error": result.stderr[:500]}

    # 从文本输出中解析 PF
    # 格式: "396pts DirAcc=50%(ref) MAPE=1.98% decay=1.47x EV_ratio=-0.190 PF=0.68 MaxDD=-26.68% WR=48%"
    pf_match = re.search(r'(\d+)pts.*?PF=([\d.]+)', result.stdout)
    if pf_match:
        n_eval = int(pf_match.group(1))
        pf = float(pf_match.group(2))
        return {
            "current_pf": pf,
            "n_eval": n_eval,
        }
    else:
        return {"error": "无法解析 PF 输出"}

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Baseline PF 全品种核实")
    parser.add_argument("--quick", action="store_true", help="仅核实已知问题品种 (6 个)")
    parser.add_argument("--dry-run", action="store_true", help="仅提取注释值, 不运行回测")
    parser.add_argument("--output", default="reports/data_ops/baseline_verification.json",
                        help="输出 JSON 文件路径")
    args = parser.parse_args()

    varieties = KNOWN_ISSUES if args.quick else ALL_VARIETIES

    print("=" * 80)
    print(f"Baseline PF 全品种核实 ({len(varieties)} 品种)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. 提取注释值
    print("\n[1/3] 从 prediction_scheme.py 提取 G005 PF 注释值...")
    g005_pf = extract_g005_pf_from_scheme()
    print(f"  提取到 {len([v for v in g005_pf.values() if v is not None])}/{len(varieties)} 个品种")

    print("\n[2/3] 从 STATE.md 提取 baseline PF...")
    state_pf = extract_state_md_baselines()
    print(f"  提取到 {len(state_pf)}/{len(varieties)} 个品种")

    if args.dry_run:
        print("\n[3/3] DRY RUN - 跳过回测")
        results = {}
    else:
        print(f"\n[3/3] 运行 monthly_backtest.py 获取当前协变量 PF ({len(varieties)} 品种)...")
        results = {}
        for i, sym in enumerate(varieties, 1):
            print(f"\n[{i}/{len(varieties)}] {sym.upper()}")
            results[sym] = run_backtest_current_covariate(sym)
            if results[sym].get("current_pf"):
                print(f"  [OK] 当前 PF = {results[sym]['current_pf']:.3f} (n={results[sym].get('n_eval', 'N/A')})")
            elif results[sym].get("error"):
                print(f"  [FAIL] 错误: {results[sym]['error'][:100]}")

    # 4. 对比分析
    print("\n" + "=" * 80)
    print("核实结果对比")
    print("=" * 80)
    print(f"{'品种':4s}  {'G005注释':>8}  {'STATE.md':>8}  {'回测当前PF':>10}  {'delta1':>6}  {'delta2':>6}  结论")
    print("-" * 80)

    discrepancies = []
    for sym in varieties:
        g005 = g005_pf.get(sym)
        state = state_pf.get(sym)
        current_pf = results.get(sym, {}).get("current_pf") if not args.dry_run else None

        delta1 = (state - g005) if (g005 and state) else None
        delta2 = (current_pf - g005) if (g005 and current_pf) else None

        # 判断是否一致 (阈值 0.05)
        if delta1 and abs(delta1) > 0.05:
            conclusion = "[X] G005 vs STATE 不一致"
            discrepancies.append((sym, "STATE.md", g005, state, delta1))
        elif delta2 and abs(delta2) > 0.05:
            conclusion = "[X] G005 vs 回测 不一致"
            discrepancies.append((sym, "回测", g005, current_pf, delta2))
        elif delta1 and abs(delta1) <= 0.05:
            conclusion = "[OK] 一致"
        else:
            conclusion = "[?] 数据缺失"

        g005_str = f"{g005:.2f}" if g005 else "N/A"
        state_str = f"{state:.2f}" if state else "N/A"
        current_str = f"{current_pf:.2f}" if current_pf else "N/A"
        delta1_str = f"{delta1:+.2f}" if delta1 else "N/A"
        delta2_str = f"{delta2:+.2f}" if delta2 else "N/A"

        print(f"{sym.upper():4s}  {g005_str:>8s}  {state_str:>8s}  {current_str:>10s}  {delta1_str:>6s}  {delta2_str:>6s}  {conclusion}")

    # 6. 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "varieties": varieties,
        "g005_pf": g005_pf,
        "state_md_pf": state_pf,
        "backtest_results": results if not args.dry_run else {},
        "discrepancies": [
            {"symbol": sym, "source": src, "expected": exp, "actual": act, "delta": d}
            for sym, src, exp, act, d in discrepancies
        ] if discrepancies else [],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n核实报告已保存: {output_path}")
    print("=" * 80)

if __name__ == "__main__":
    main()
