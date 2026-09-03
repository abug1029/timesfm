"""A2-P2 Orchestrator: 调度 Worker 子进程, 品种级隔离 + 断点续跑 + run manifest.

Usage:
    python scripts/a2_p2_orchestrator.py                          # 全 20 品种, run_id=a2-p2
    python scripts/a2_p2_orchestrator.py ss rb i                  # 指定品种
    python scripts/a2_p2_orchestrator.py --force ss               # 强制重跑
"""
from __future__ import annotations

import pathlib
import sys
import argparse
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config.backtest_config import SYMBOLS
from scripts.a2_p1_runtime import (
    RunConfig,
    build_manifest,
    exclusive_result_lock,
    generate_eval_grid,
)

FM_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _count_jsonl_lines(jsonl_path: pathlib.Path) -> int:
    """统计 JSONL 行数 (已完成的 eval points)"""
    if not jsonl_path.exists():
        return 0
    return sum(1 for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip())


def _expected_eval_points(symbol: str) -> int:
    """从数据库精确计算预期 eval points 数量。"""
    try:
        from scripts.a2_p1_runtime import expected_eval_grid
        return len(expected_eval_grid(symbol))
    except Exception:
        # DataStore 不可用时回退: 用典型值估算
        return len(generate_eval_grid(10000))


def _terminate_subprocess_tree(proc: subprocess.Popen) -> None:
    """Windows 下强制终止子进程及其子树。"""
    try:
        proc.kill()
    except Exception:
        pass
    # Windows: taskkill /F /T /PID
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


def _open_log_append(log_path: pathlib.Path):
    """打开日志文件追加模式; 首次存在时写入分隔符。"""
    existed = log_path.exists()
    f = open(log_path, "a", encoding="utf-8")
    if existed:
        sep = f"=== resume {datetime.now(timezone.utc).isoformat()} ===\n"
        f.write(sep)
    return f


# 终态集合 (必须与测试中的字符串完全一致)
_TERMINAL_STATES = {"DONE", "SKIP", "FAILED", "TIMEOUT", "INVALID"}


def run_orchestrator(symbols: list, force: bool = False, run_id: str = "a2-p2"):
    """调度 Worker 子进程，run_id 参数化。"""
    config = RunConfig.for_run(run_id, symbols, FM_ROOT)
    results_dir = config.results_dir
    logs_dir = config.logs_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # venv Python：跟随当前解释器（由 venv 启动时子进程继承同一环境）
    python = sys.executable
    worker_script = pathlib.Path(__file__).parent / "a2_p2_worker.py"

    # Orchestrator 运行级锁 (与 run_id 对齐)
    orch_lock = logs_dir / f"{run_id}.orchestrator.lock"
    try:
        with exclusive_result_lock(orch_lock, run_id=run_id):
            _run_orchestrator_core(symbols, force, run_id, config, python, worker_script)
    except RuntimeError as exc:
        print(f"[Orchestrator] LOCK FAILED: {exc}", flush=True)
        sys.exit(1)


def _run_orchestrator_core(
    symbols: list,
    force: bool,
    run_id: str,
    config: RunConfig,
    python: str,
    worker_script: pathlib.Path,
):
    """Orchestrator 核心逻辑 (必须在 exclusive_result_lock 持有期间调用)"""
    started_at = datetime.now(timezone.utc).isoformat()
    per_symbol_status: dict[str, dict] = {}
    completed = []
    skipped = []
    failed = []
    timed_out = []
    invalid = []

    for sym in symbols:
        sym_lower = sym.lower()
        jsonl_path = config.results_dir / f"{sym_lower}.jsonl"
        log_path = config.logs_dir / f"{sym_lower}.log"

        # 检查是否已完成
        n_lines = _count_jsonl_lines(jsonl_path)
        if not force and n_lines >= _expected_eval_points(sym_lower):
            print(f"[Orchestrator] SKIP {sym.upper()}: already done ({n_lines} eval points)")
            skipped.append(sym)
            per_symbol_status[sym_lower] = {
                "status": "SKIP",
                "rows": n_lines,
                "unique_bars": n_lines,
            }
            continue

        # 启动 Worker 子进程
        print(f"[Orchestrator] START {sym.upper()} (force={force}, prev_lines={n_lines})")
        try:
            with _open_log_append(log_path) as log_file:
                proc = subprocess.Popen(
                    [python, "-u", str(worker_script), sym_lower, "--run-id", run_id],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=FM_ROOT,
                )
                try:
                    proc.wait(timeout=5400)  # 90 分钟
                except subprocess.TimeoutExpired:
                    _terminate_subprocess_tree(proc)
                    status_msg = "TIMEOUT"
                    print(f"[Orchestrator] {status_msg} {sym.upper()}: exceeded 90min limit, killed", flush=True)
                    per_symbol_status[sym_lower] = {
                        "status": status_msg,
                        "rows": _count_jsonl_lines(jsonl_path),
                        "unique_bars": _count_jsonl_lines(jsonl_path),
                    }
                    timed_out.append(sym)
                    continue
        except Exception as exc:
            status_msg = "FAILED"
            print(f"[Orchestrator] {status_msg} {sym.upper()}: {exc}", flush=True)
            per_symbol_status[sym_lower] = {
                "status": status_msg,
                "rows": _count_jsonl_lines(jsonl_path),
                "unique_bars": _count_jsonl_lines(jsonl_path),
            }
            failed.append(sym)
            continue

        # 子进程退出后检查 returncode
        rc = proc.returncode
        if rc != 0:
            status_msg = "FAILED"
            print(f"[Orchestrator] {status_msg} {sym.upper()}: exit code {rc}, log={log_path}")
            per_symbol_status[sym_lower] = {
                "status": status_msg,
                "rows": _count_jsonl_lines(jsonl_path),
                "unique_bars": _count_jsonl_lines(jsonl_path),
                "exit_code": rc,
            }
            failed.append(sym)
            continue

        # rc == 0: 校验结果
        n_final = _count_jsonl_lines(jsonl_path)
        expected = _expected_eval_points(sym_lower)
        if n_final < expected:
            status_msg = "INVALID"
            print(f"[Orchestrator] {status_msg} {sym.upper()}: {n_final} < {expected} expected bars")
            per_symbol_status[sym_lower] = {
                "status": status_msg,
                "rows": n_final,
                "unique_bars": n_final,
            }
            invalid.append(sym)
            continue

        print(f"[Orchestrator] DONE {sym.upper()}: {n_final} eval points, log={log_path}")
        completed.append(sym)
        per_symbol_status[sym_lower] = {
            "status": "DONE",
            "rows": n_final,
            "unique_bars": n_final,
        }

    finished_at = datetime.now(timezone.utc).isoformat()

    # 汇总
    print(f"\n[Orchestrator] SUMMARY: {len(completed)} done, {len(skipped)} skipped, "
          f"{len(failed)} failed, {len(timed_out)} timeout, {len(invalid)} invalid")
    if failed:
        print(f"  Failed: {[s.upper() for s in failed]}")
    if timed_out:
        print(f"  Timeout: {[s.upper() for s in timed_out]}")
    if invalid:
        print(f"  Invalid: {[s.upper() for s in invalid]}")
    print(f"  Logs in {config.logs_dir}/")

    # 逐品种终态打印
    for sym_lower, info in per_symbol_status.items():
        print(f"  {sym_lower.upper()}: {info['status']}")

    # 写入 manifest
    build_manifest(
        run_id=run_id,
        symbols=[s.lower() for s in symbols],
        results_dir=config.results_dir,
        logs_dir=config.logs_dir,
        report_path=config.report_path,
        per_symbol=per_symbol_status,
        started_at=started_at,
        finished_at=finished_at,
        root=FM_ROOT,
    )
    print(f"\n[Orchestrator] manifest written to {config.report_path.parent}/{run_id}.manifest.json")

    # 报告生成前置校验: 只有所有 symbol 都是 DONE 或 SKIP 才调用
    all_ok = all(
        st in ("DONE", "SKIP") for st in
        (info["status"] for info in per_symbol_status.values())
    )
    if all_ok and per_symbol_status:
        print(f"\n[Orchestrator] generating final report...")
        report_script = pathlib.Path(__file__).parent / "a2_p2_generate_report.py"
        if report_script.exists():
            rc = subprocess.run([python, str(report_script), "--run-id", run_id], cwd=FM_ROOT)
            if rc.returncode != 0:
                print(f"[Orchestrator] WARNING: report generator exited {rc.returncode}")
                sys.exit(1)
    else:
        bad = [
            f"{s}={info['status']}" for s, info in per_symbol_status.items()
            if info["status"] not in ("DONE", "SKIP")
        ]
        print(f"\n[Orchestrator] SKIPPING report: {', '.join(bad)}")
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="A2-P2 Orchestrator: 调度 Worker 子进程")
    p.add_argument("symbols", nargs="*", default=SYMBOLS, help="品种列表 (default: 全 20 品种)")
    p.add_argument("--force", action="store_true", help="强制重跑 (忽略已有 JSONL)")
    p.add_argument("--run-id", default="a2-p2", choices=["a2-p2"],
                   help="运行 ID (default: a2-p2)")
    args = p.parse_args()
    run_orchestrator(args.symbols, args.force, args.run_id)


if __name__ == "__main__":
    main()
