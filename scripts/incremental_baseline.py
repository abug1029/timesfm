#!/usr/bin/env python3
"""增量基线生成：从现有基线末端继续生成新点"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

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
    
    print(f"[DONE] {sym_upper} 基线已更新: {jsonl_file.name}")
    return True

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
