#!/usr/bin/env python3
"""增量基线生成：从现有基线末端继续生成新点"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from scripts.lock_utils import SymbolLock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def load_existing_baselines(symbol: str, cov: str = None):
    """加载现有基线文件，返回已完成的点"""
    config_dir = Path(__file__).resolve().parent.parent / "task_FM" / "config"
    
    cov_suffix = f"_{cov}" if cov and cov != "none" else "_nocov"
    filename = f"baseline_points_{symbol}{cov_suffix}.jsonl"
    filepath = config_dir / filename
    
    if not filepath.exists():
        return {}, None
    
    points = {}
    last_cutoff = None
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            cutoff = rec["cutoff"]
            points[(symbol, cutoff)] = rec
            last_cutoff = cutoff
    
    return points, last_cutoff

def incremental_generate(symbol: str, cov: str = None, root: str = "."):
    """增量生成基线：从现有末端继续"""
    from scripts import monthly_backtest as mb
    from cascade.daily_model import DailyModel
    from cascade.hourly_model import HourlyModel
    
    sym_lower = symbol.lower()
    
    # 加品种锁（与 gbp 一致）
    with SymbolLock(sym_lower, root):
        sym_upper = symbol.upper()
    
        # 加载已完成的点
        resumed_points, last_cutoff = load_existing_baselines(sym_lower, cov)
    
        if last_cutoff:
            print(f"[INFO] {sym_upper} 已有基线到 {last_cutoff}，共 {len(resumed_points)} 点")
            # 计算下一个起点（last_cutoff + STEP hours）
            last_dt = datetime.strptime(last_cutoff, "%Y-%m-%d %H:%M:%S")
            # STEP is defined in monthly_backtest.py, typically 2 hours for 1H data
            next_start = last_dt + timedelta(hours=2)
            eval_start_ts = next_start.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] 从 {eval_start_ts} 开始增量生成")
        else:
            print(f"[INFO] {sym_upper} 无现有基线，全量生成")
            eval_start_ts = None
    
        # 加载模型
        print("[INFO] 加载模型...")
        daily_m = DailyModel()
        hourly_m = HourlyModel(shared_model=daily_m.model)
    
        # 设置 checkpoint 文件
        config_dir = Path(root) / "task_FM" / "config"
        cov_suffix = f"_{cov}" if cov and cov != "none" else "_nocov"
        checkpoint_path = config_dir / f".{sym_lower}_incremental.checkpoint"
    
        effective_cov = "none" if (cov is None or cov == "none") else cov
    
        print(f"[START] 增量生成 {sym_upper} (cov={effective_cov})")
    
        # 运行回测（带断点续传）
        with open(checkpoint_path, "a", encoding="utf-8") as checkpoint_fp:
            result = mb.run_symbol_backtest(
                symbol=sym_upper,
                daily_model=daily_m,
                hourly_model=hourly_m,
                cov_override=effective_cov,
                eval_start_ts=eval_start_ts,
                resumed_points=resumed_points,
                checkpoint_fp=checkpoint_fp,
            )
    
        if result is None:
            print(f"[ERROR] {sym_upper} 回测失败")
            return False
    
        # 合并新旧点
        all_points = result.get("points", [])
        print(f"[INFO] {sym_upper} 生成 {len(all_points)} 个点（含 {len(resumed_points)} 个已有点）")
    
        # 写入基线文件（覆盖）
        from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint
        _proto = compute_protocol_fingerprint()
    
        jsonl_file = config_dir / f"baseline_points_{sym_lower}{cov_suffix}.jsonl"
        temp_file = config_dir / f".baseline_points_{sym_lower}{cov_suffix}.jsonl.tmp"
    
        with open(temp_file, "w", encoding="utf-8") as fp:
            for pt in all_points:
                if "error" in pt:
                    continue
                rec = {
                    "cutoff": pt["cutoff"],
                    "dir_ok": bool(pt["dir_ok"]),
                    "delta_pred": float(pt["delta_pred"]),
                    "delta_real": float(pt["delta_real"]),
                    "protocol_fingerprint": _proto,
                }
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    
        temp_file.rename(jsonl_file)
    
        # 清理 checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()
    
        # 同步 metrics（与 gbp 对齐）
        _update_baseline_metrics(sym_lower, root, result=result)
        
        print(f"[DONE] {sym_upper} 基线已更新: {jsonl_file.name}")
        return True


def _update_baseline_metrics(symbol: str, root: str, result: dict = None):
    """增量重生后更新 baseline_metrics.json（与 gbp schema 对齐）
    
    Args:
        symbol: 品种代码（小写）
        root: 项目根目录
        result: incremental 生成的结果对象（用于 summarize），若为 None 则从 jsonl 计算
    """
    import json, fcntl
    from pathlib import Path
    
    config_dir = Path(root) / "task_FM" / "config"
    metrics_path = config_dir / "baseline_metrics.json"
    metrics_lock_path = config_dir / ".metrics.lock"  # 与 gbp 一致
    
    # 优先使用 result.summarize()（与 gbp 相同逻辑）
    if result is not None:
        from scripts import monthly_backtest as mb
        metrics_data = mb.summarize(result)
        # 显式并入 vid（与 gbp 一致）
        from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint
        metrics_data["vid"] = compute_protocol_fingerprint()
    else:
        # 降级：仅计算可用指标（jsonl 无 endpoint_mape，不强行计算）
        jsonl_path = config_dir / f"baseline_points_{symbol}_nocov.jsonl"
        with open(jsonl_path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        
        n = len(lines)
        if n == 0:
            raise ValueError(f"品种 {symbol} jsonl 为空，禁止合入")
        
        # vid: 协议指纹（与 gbp 同源，无参调用）
        from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint
        vid = compute_protocol_fingerprint()
        
        # dir_acc: 从 jsonl 计算（jsonl 有 dir_ok 字段）
        dir_acc = _compute_dir_acc_from_jsonl(lines)
        
        # n_eff: 使用行数（简化版，与 gbp 可能略有差异）
        n_eff = n
        
        metrics_data = {
            "n": n,
            "vid": vid,
            "dir_acc": dir_acc,
            "n_eff": n_eff,
            # endpoint_mape 降级时不写入（jsonl 无此字段）
        }
    
    # 使用 .metrics.lock 保护并发写
    with open(metrics_lock_path, "w") as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        try:
            with open(metrics_path, encoding="utf-8") as f:
                metrics = json.load(f)
            metrics[symbol] = metrics_data
            # 原子写
            tmp_path = metrics_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(metrics, f, ensure_ascii=False, indent=2)
            tmp_path.replace(metrics_path)
        finally:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)

def _compute_dir_acc_from_jsonl(lines: list) -> float:
    """从 jsonl 计算方向准确率（禁止返回 0.0）"""
    if not lines:
        raise ValueError("jsonl 为空，无法计算 dir_acc")
    correct = sum(1 for line in lines if line.get("dir_ok", False))
    return correct / len(lines)

# 注意：_compute_endpoint_mape_from_jsonl 已删除
# 原因：现网 jsonl 无 endpoint_mape 字段，强行计算会失败
# 降级时不写入 endpoint_mape，仅走 result.summarize() 路径时才有该指标

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="增量基线生成")
    parser.add_argument("symbols", nargs="+", help="品种代码")
    parser.add_argument("--cov", default=None, help="协变量类型")
    parser.add_argument("--root", default=".", help="项目根目录")
    args = parser.parse_args()
    
    for sym in args.symbols:
        try:
            incremental_generate(sym, args.cov, args.root)
        except Exception as e:
            print(f"[ERROR] {sym} 失败: {e}")
            import traceback
            traceback.print_exc()
