#!/usr/bin/env python3
"""检查基线覆盖度

覆盖度定义：基线末端 >= 确认窗起点的品种比例
SPEC 门闩：覆盖度 > 95%
"""
import sys
import json
from pathlib import Path
from datetime import datetime

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from data.config import DEFAULT_SYMBOLS

CONFIRM_WINDOW_START = datetime(2026, 10, 3, 0, 0, 0)

def check_coverage():
    """检查基线覆盖度"""
    config_dir = _repo_root / "task_FM" / "config"
    
    total = len(DEFAULT_SYMBOLS)
    covered = 0
    uncovered = []
    
    for sym in DEFAULT_SYMBOLS:
        bl_file = config_dir / f"baseline_points_{sym.lower()}_nocov.jsonl"
        if not bl_file.exists():
            uncovered.append(sym)
            continue
        
        lines = bl_file.read_text().strip().split("\n")
        if not lines:
            uncovered.append(sym)
            continue
        
        try:
            last = json.loads(lines[-1])
            cutoff_str = last.get("cutoff", "")
            cutoff_dt = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
                try:
                    cutoff_dt = datetime.strptime(cutoff_str, fmt)
                    break
                except ValueError:
                    continue
            
            if cutoff_dt and cutoff_dt >= CONFIRM_WINDOW_START:
                covered += 1
            else:
                uncovered.append(sym)
        except Exception:
            uncovered.append(sym)
    
    coverage_ratio = covered / total if total > 0 else 0
    result = {
        "total_symbols": total,
        "covered_symbols": covered,
        "coverage_ratio": coverage_ratio,
        "coverage_pct": f"{coverage_ratio * 100:.1f}%",
        "spec_gate": "> 95%",
        "gate_passed": coverage_ratio > 0.95,
        "uncovered": uncovered
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

if __name__ == "__main__":
    check_coverage()
