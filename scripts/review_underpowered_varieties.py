"""监控 AO/UR 等 underpowered 品种的样本量,达到门槛后提醒复评

Phase 15 专家审核发现 (Major #3):
- AO n=199 (56.9% 门槛), UR n=306 (87.4% 门槛)
- GREEN 门槛要求 n_eval >= 350
- 这两个品种的"失败"结论在统计上不可靠

用法:
    python scripts/review_underpowered_varieties.py
    python scripts/review_underpowered_varieties.py --check-ao --check-ur

输出:
    - 各品种的当前样本量 (从 batch_p15a.log 解析)
    - 是否达到门槛
    - 复评命令建议
"""
import argparse
import re
from pathlib import Path

VARIETIES = ["ao", "ur"]
GREEN_THRESHOLD = 350

def parse_n_eval_from_log(log_path: Path, symbol: str) -> int | None:
    """从 batch_p15a.log 中解析某品种的 n_eval

    示例日志行:
        [DONE] P15a-ao-nvi: 199pts DirAcc=47 PF=0.71 EV_ratio=-0.168 MaxDD=-53.07%
    """
    if not log_path.exists():
        return None

    pattern = re.compile(rf"P15a-{symbol}-\w+:\s+(\d+)pts\b")
    max_n = 0

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                n = int(match.group(1))
                max_n = max(max_n, n)

    return max_n if max_n > 0 else None

def check_variety(symbol: str, log_path: Path):
    """检查单个品种的样本量状态"""
    n_eval = parse_n_eval_from_log(log_path, symbol)

    print(f"\n{symbol.upper()}:")
    if n_eval is None:
        print(f"  状态: 未找到回测记录")
        print(f"  建议: 运行 P15 回测")
        return

    pct = (n_eval / GREEN_THRESHOLD) * 100
    status = "达标" if n_eval >= GREEN_THRESHOLD else "不足"

    print(f"  当前 n_eval: {n_eval} ({pct:.1f}% 门槛)")
    print(f"  状态: {status}")

    if n_eval < GREEN_THRESHOLD:
        deficit = GREEN_THRESHOLD - n_eval
        print(f"  缺口: 还需 {deficit} 个评估点")
        print(f"  建议: 等待数据积累后重新采集并回测")
    else:
        print(f"  达到 GREEN 门槛,建议重新运行 P15 测试")
        print(f"  复评命令:")
        for cov in ["nvi", "qstick", "vwap_deviation", "stddev"]:
            print(f"    python scripts/monthly_backtest.py {symbol} --cov-override {cov}")

def main():
    parser = argparse.ArgumentParser(description="Underpowered varieties 样本量监控")
    parser.add_argument("--check-ao", action="store_true", help="仅检查 AO")
    parser.add_argument("--check-ur", action="store_true", help="仅检查 UR")
    args = parser.parse_args()

    varieties = VARIETIES
    if args.check_ao:
        varieties = ["ao"]
    elif args.check_ur:
        varieties = ["ur"]

    log_path = Path("reports/data_ops/batch_p15a.log")

    print("=" * 80)
    print("Underpowered Varieties 样本量监控")
    print("=" * 80)
    print(f"GREEN 门槛: n_eval >= {GREEN_THRESHOLD}")
    print(f"日志文件: {log_path}")

    for sym in varieties:
        check_variety(sym, log_path)

    print("\n" + "=" * 80)
    print("总结:")
    print("=" * 80)
    print("AO/UR 在 Phase 15 中样本量不足 (n < 350),结论统计效力不足。")
    print("待数据积累至 n >= 350 后,重新运行 P15 测试以验证结论。")

if __name__ == "__main__":
    main()
