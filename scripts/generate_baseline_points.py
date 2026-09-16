"""生成基线 dir_ok 序列用于 DM 配对检验

用法:
    python scripts/generate_baseline_points.py --symbol ss --cov ccl --root /home/abug/timesfm

输出:
    task_FM/config/baseline_points_{symbol}.jsonl  每行 {cutoff, dir_ok, delta_pred, delta_real}
    task_FM/config/baseline_metrics.json          更新 {symbol: {dir_acc, endpoint_mape, n, n_eff}}

约束:
    - 禁止从 evaluator / 慢环调用本脚本
    - 同品种 .lock 排他
    - 生成前 summarize 一次拿标量
    - JSONL 只写 {cutoff, dir_ok, delta_pred, delta_real}
    - cutoff 必须是完整时间戳
"""

import sys
import os
import json
import argparse
import fcntl
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PYTHONIOENCODING'] = 'utf-8'

import scripts.monthly_backtest as mb
from config.backtest_config import SYMBOL_NAMES, CONTEXT_BARS, HORIZON, STEP
from cascade.evaluation_metrics import fallback_n_eff


def generate(symbol: str, cov: str, root: str):
    """生成单品种基线点序列

    Args:
        symbol: 品种代码 (小写, e.g. "ss")
        cov: 协变量类型 (e.g. "ccl")
        root: FM_ROOT 目录
    """
    sym_upper = symbol.upper()
    sym_lower = symbol.lower()
    root_path = Path(root)
    config_dir = root_path / "task_FM" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # 同品种 .lock 排他
    lock_file = config_dir / f".{sym_lower}.lock"
    lock_fp = open(lock_file, "w")
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        raise RuntimeError(f"品种 {sym_upper} 正在生成中（锁冲突）")

    try:
        print(f"[Start] Baseline generation for {sym_upper} with cov={cov}")

        # 调用 monthly_backtest.run_symbol_backtest
        result = mb.run_symbol_backtest(
            symbol=sym_upper,
            daily_model=None,
            hourly_model=None,
            cov_override=cov,
        )

        if result is None:
            print(f"[Error] 品种 {sym_upper} 数据不足，无法生成基线")
            return

        # summarize 一次拿标量
        summary = mb.summarize(result)
        if summary is None:
            print(f"[Error] 品种 {sym_upper} summarize 失败")
            return

        # MEDIUM 4: summary 键存在性验证
        required_keys = {"dir_acc", "endpoint_mape", "n", "n_eff"}
        if not required_keys.issubset(summary.keys()):
            missing = required_keys - set(summary.keys())
            raise ValueError(f"summarize 返回的字典缺少键: {missing}")

        points = result.get("points", [])
        total = len(points)
        print(f"[Info] 品种 {sym_upper} 共 {total} 个评估点")

        # MEDIUM 3: 部分写入文件清理 - 写入临时文件，成功后 rename
        jsonl_file = config_dir / f"baseline_points_{sym_lower}.jsonl"
        temp_file = config_dir / f".baseline_points_{sym_lower}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as fp:
                written = 0
                for i, pt in enumerate(points):
                    if "error" in pt:
                        continue

                    # HIGH: cutoff 时间戳格式验证
                    cutoff_str = pt["cutoff"]
                    try:
                        datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        raise ValueError(f"品种 {sym_upper} 的 cutoff 格式错误: {cutoff_str}")

                    rec = {
                        "cutoff": pt["cutoff"],
                        "dir_ok": bool(pt["dir_ok"]),
                        "delta_pred": float(pt["delta_pred"]),
                        "delta_real": float(pt["delta_real"]),
                    }
                    fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written += 1

                    # 每 50 点打印进度
                    if written % 50 == 0:
                        print(f"[Progress] Baseline generation for {sym_upper}: {written}/{total} points done...")

            temp_file.rename(jsonl_file)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

        print(f"[Progress] Baseline generation for {sym_upper}: {written}/{total} points done...")

        # MEDIUM 1: metrics 文件并发更新保护 - 使用文件锁保护 metrics 更新
        metrics_file = config_dir / "baseline_metrics.json"
        metrics_lock = config_dir / ".metrics.lock"
        with open(metrics_lock, "w") as m_lock_fp:
            fcntl.flock(m_lock_fp.fileno(), fcntl.LOCK_EX)
            try:
                # MEDIUM 2: 空 metrics 文件处理
                if metrics_file.exists() and metrics_file.stat().st_size > 0:
                    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
                else:
                    metrics = {}

                metrics[sym_lower] = {
                    "dir_acc": summary["dir_acc"],
                    "endpoint_mape": summary["endpoint_mape"],
                    "n": summary["n"],
                    "n_eff": summary["n_eff"],
                }

                metrics_file.write_text(
                    json.dumps(metrics, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            finally:
                fcntl.flock(m_lock_fp.fileno(), fcntl.LOCK_UN)

        print(f"[Done] 品种 {sym_upper} 基线生成完成: n={summary['n']}, dir_acc={summary['dir_acc']:.3f}, endpoint_mape={summary['endpoint_mape']:.2f}")

    finally:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        lock_fp.close()
        if lock_file.exists():
            lock_file.unlink()


def main():
    parser = argparse.ArgumentParser(description="生成基线 dir_ok 序列用于 DM 配对检验")
    parser.add_argument("--symbol", required=True, help="品种代码 (小写)")
    parser.add_argument("--cov", required=True, help="协变量类型")
    parser.add_argument("--root", required=True, help="FM_ROOT 目录")
    args = parser.parse_args()

    generate(symbol=args.symbol, cov=args.cov, root=args.root)


if __name__ == "__main__":
    main()
