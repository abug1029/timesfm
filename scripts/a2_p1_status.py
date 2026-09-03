"""A2-P1 Status: 实时进度查询 (汇总所有 JSONL)。

Usage:
    python scripts/a2_p1_status.py              # 一次性查询
    python scripts/a2_p1_status.py --watch      # 每 10 秒刷新
"""
from __future__ import annotations
import sys, pathlib, json, time, argparse
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config.backtest_config import SYMBOLS


def _count_jsonl_lines(jsonl_path: pathlib.Path) -> int:
    if not jsonl_path.exists():
        return 0
    return sum(1 for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip())


def _get_last_record(jsonl_path: pathlib.Path) -> dict | None:
    """读取 JSONL 最后一行"""
    if not jsonl_path.exists():
        return None
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        if line.strip():
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return None


def print_status():
    """打印进度表"""
    results_dir = pathlib.Path("reports/a2_p1_results")
    print(f"{'Symbol':<8} | {'Done':>5} | {'Status':<12}")
    print(f"{'-'*8}-+-{'-'*5}-+-{'-'*12}")

    total_done = 0
    total_pending = 0

    for sym in SYMBOLS:
        sym_lower = sym.lower()
        jsonl_path = results_dir / f"{sym_lower}.jsonl"
        n_lines = _count_jsonl_lines(jsonl_path)
        total_done += n_lines

        # 估算 pending (假设 ~396 个 eval points)
        estimated_total = 396
        pending = max(0, estimated_total - n_lines)
        total_pending += pending

        if n_lines == 0:
            status = "Pending"
        elif n_lines >= 300:
            status = "Done"
        else:
            status = f"{n_lines}/396"

        print(f"{sym.upper():<8} | {n_lines:>5} | {status:<12}")

    print(f"\nTotal: {total_done} done, {total_pending} pending")


def main():
    p = argparse.ArgumentParser(description="A2-P1 Status: 实时进度查询")
    p.add_argument("--watch", action="store_true", help="每 10 秒刷新")
    args = p.parse_args()

    if args.watch:
        try:
            while True:
                print("\033[2J\033[H", end="")  # 清屏
                print_status()
                time.sleep(10)
        except KeyboardInterrupt:
            print("\nStopped")
    else:
        print_status()


if __name__ == "__main__":
    main()
