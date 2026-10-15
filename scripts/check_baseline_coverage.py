#!/usr/bin/env python3
"""检查基线覆盖度

覆盖度定义：有确认窗 cutoff 且基线末端 >= cutoff 的品种比例
"""
import sys
import json
from pathlib import Path

# 添加项目根目录到路径
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from data.config import DEFAULT_SYMBOLS

def check_coverage(root: str = "."):
    """检查基线覆盖度
    
    Returns:
        dict: 覆盖度统计
    """
    config_dir = Path(root) / "task_FM" / "config"
    
    # 读取 metrics
    metrics_path = config_dir / "baseline_metrics.json"
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)
    
    total = len(DEFAULT_SYMBOLS)
    covered = 0
    uncovered = []
    
    for sym in DEFAULT_SYMBOLS:
        sym_lower = sym.lower()
        m = metrics.get(sym_lower)
        if m and m.get("n", 0) > 0:
            covered += 1
        else:
            uncovered.append(sym)
    
    result = {
        "total_symbols": total,
        "covered_symbols": covered,
        "coverage_ratio": covered / total if total > 0 else 0,
        "uncovered": uncovered
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

if __name__ == "__main__":
    check_coverage()
