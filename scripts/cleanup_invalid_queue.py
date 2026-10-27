#!/usr/bin/env python3
"""安全清理队列中的无效提案"""
import json
import fcntl
import shutil
from pathlib import Path
from datetime import datetime

def load_supported_covariates():
    """从 covariate_pool.json 读取合法协变量名"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path) as f:
        pool = json.load(f)
    
    supported = {k for k, v in pool.get("covariates", {}).items() if v.get("status") == "active"}
    supported.update({"slope_only", "none", "baseline"})
    family_names = set(pool.get("families", []))
    
    return supported, family_names

def cleanup_queue():
    queue_path = Path("data/cache/aligned_pending.jsonl")
    backup_path = Path(f"data/cache/aligned_pending.jsonl.bak.{datetime.now():%Y%m%d_%H%M%S}")
    lock_path = Path("data/cache/aligned_pending.jsonl.lock")
    
    supported, families = load_supported_covariates()
    
    # 获取文件锁
    with open(lock_path, "w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Error: queue is locked by another process. Stop slow loop first.")
            return
        
        try:
            # 备份原文件
            shutil.copy2(queue_path, backup_path)
            print(f"Backup created: {backup_path}")
            
            # 过滤无效条目
            valid_lines = []
            invalid_count = 0
            
            with open(queue_path) as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    cov = row["cov_override"]
                    symbol = row["symbol"]
                    
                    if cov in families:
                        invalid_count += 1
                        print(f"Removing: {row['variant_id']} (family name: {cov})")
                    elif cov not in supported:
                        invalid_count += 1
                        print(f"Removing: {row['variant_id']} (unregistered: {cov})")
                    elif symbol == "c":
                        invalid_count += 1
                        print(f"Removing: {row['variant_id']} (symbol c has no data)")
                    else:
                        valid_lines.append(line)
            
            # 原子替换
            temp_path = queue_path.with_suffix(".jsonl.tmp")
            with open(temp_path, "w") as f:
                f.writelines(valid_lines)
            
            temp_path.rename(queue_path)
            
            print(f"\nRemoved {invalid_count} invalid entries, {len(valid_lines)} remaining")
            
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

if __name__ == "__main__":
    cleanup_queue()
