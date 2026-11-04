#!/usr/bin/env python3
"""增量基线生成：从现有基线末端继续生成新点"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def load_existing_baselines(symbol: str, cov: str = None, root: str = "."):
    """加载现有基线文件，返回已完成的点"""
    config_dir = Path(root) / "task_FM" / "config"
    
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

def incremental_generate(symbol: str, cov: str = None, root: str = ".", finalize: bool = True):
    """增量生成基线：从现有末端继续。
    返回：新生成的基线末端 cutoff (str)，失败返回 None。
    """
    from scripts import monthly_backtest as mb
    from cascade.daily_model import DailyModel
    from cascade.hourly_model import HourlyModel
    
    sym_lower = symbol.lower()
    sym_upper = symbol.upper()
    
    # 计算当前协议指纹（用于筛选续跑载荷）
    from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint
    _proto = compute_protocol_fingerprint()

    # Task 9: 获取当前评估网格，只复用网格上的行
    from cascade.eval_grid import baseline_eval_cutoffs
    grid_cutoffs = set(baseline_eval_cutoffs(sym_lower))

    # 加载已完成的点（按网格、指纹和必写键筛选）
    raw_points, last_cutoff = load_existing_baselines(sym_lower, cov, root)
    resumed_points = {}
    for key, rec in raw_points.items():
        cutoff = key[1]  # key is (symbol, cutoff)
        if (cutoff in grid_cutoffs
                and "dir_ok" in rec and "delta_pred" in rec and "delta_real" in rec
                and rec.get("protocol_fingerprint") == _proto):
            resumed_points[key] = rec

    if last_cutoff:
        print(f"[INFO] {sym_upper} 已有基线到 {last_cutoff}，共 {len(resumed_points)} 点（指纹匹配）")
    else:
        print(f"[INFO] {sym_upper} 无现有基线，全量生成")

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
            resumed_points=resumed_points,
            checkpoint_fp=checkpoint_fp,
        )
    
    if result is None:
        print(f"[ERROR] {sym_upper} 回测失败")
        return None
    
    # backtest 内部已通过 resumed_points 合并旧点，result["points"] 即最终集合
    all_points = result.get("points", [])
    print(f"[INFO] {sym_upper} 共 {len(all_points)} 点（含续跑合并）")
    
    # Task 8: 先扫描是否有任何错误点
    error_points = [pt for pt in all_points if "error" in pt]
    if error_points:
        cutoffs = [pt.get("cutoff", "?") for pt in error_points[:5]]
        print(f"[ERROR] {sym_upper} 有 {len(error_points)} 个错误点，cutoffs={cutoffs}")
        return None
    
    # 写入基线文件（覆盖）
    
    jsonl_file = config_dir / f"baseline_points_{sym_lower}{cov_suffix}.jsonl"
    temp_file = config_dir / f".baseline_points_{sym_lower}{cov_suffix}.jsonl.tmp"
    
    # 写入时按 cutoff 去重
    from cascade.baseline_paths import baseline_jsonl_record
    seen_cutoffs = set()
    with open(temp_file, "w", encoding="utf-8") as fp:
        for pt in all_points:
            cutoff = pt["cutoff"]
            if cutoff in seen_cutoffs:
                continue
            seen_cutoffs.add(cutoff)
            rec = baseline_jsonl_record(pt, _proto)
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[INFO] {sym_upper} 写入 {len(seen_cutoffs)} 个唯一 cutoff 点")
    
    # Task 8: finalize 逻辑
    if not finalize:
        # finalize=False: 不归档、不收口、不换名
        if len(seen_cutoffs) == 0:
            if temp_file.exists():
                temp_file.unlink()
            # 清理 checkpoint
            if checkpoint_path.exists():
                checkpoint_path.unlink()
            return None
        # 清理 checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        # 读取临时文件最后一笔 cutoff
        last_cutoff = None
        try:
            with open(temp_file, "r", encoding="utf-8") as _fp:
                for _line in _fp:
                    if _line.strip():
                        _rec = json.loads(_line)
                        last_cutoff = _rec.get("cutoff")
        except Exception as _e:
            print(f"[WARN] {sym_upper} 无法读取临时基线末端: {_e}")
        print(f"[DONE] {sym_upper} 临时基线已写入: {temp_file.name}, new_cutoff={last_cutoff}")
        return last_cutoff
    else:
        # finalize=True: 归档活文件，然后收口
        if jsonl_file.exists():
            from scripts.sup_evidence import _archive_baseline_before_regen
            _archive_baseline_before_regen(jsonl_file)
    
        import scripts.sup_evidence
        archive_path = jsonl_file.with_name(jsonl_file.stem + "_archive")
        ok = scripts.sup_evidence.finalize_baseline_write(
            sym_lower, str(jsonl_file), root, str(archive_path)
        )
    
        # 清理 checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()
    
        if not ok:
            print(f"[ERROR] {sym_upper} finalize_baseline_write 返回 False")
            return None
    
        # 读取活文件最后一笔 cutoff
        last_cutoff = None
        try:
            with open(jsonl_file, "r", encoding="utf-8") as _fp:
                for _line in _fp:
                    if _line.strip():
                        _rec = json.loads(_line)
                        last_cutoff = _rec.get("cutoff") or last_cutoff
        except Exception as _e:
            print(f"[WARN] {sym_upper} 无法读取新基线末端: {_e}")
        print(f"[DONE] {sym_upper} 基线已更新: {jsonl_file.name}, new_cutoff={last_cutoff}")
        return last_cutoff
