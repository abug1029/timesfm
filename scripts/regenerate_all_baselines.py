#!/usr/bin/env python3
"""重新生成所有品种的 nocov 基线（覆盖到最新数据）"""
import os
import sys
from pathlib import Path

FM_ROOT = Path("/home/abug/timesfm")
sys.path.insert(0, str(FM_ROOT))
sys.path.insert(0, str(FM_ROOT / "scripts"))

from cascade.baselinepaths import baseline_paths
from praxist_supervisor import ensure_baselines

SYMBOLS = ["ss", "sr", "m", "jd", "lh", "cj", "fu", "rb"]

def main():
    print("=== 重新生成基线（覆盖到 Sep 28）===")

    for sym in SYMBOLS:
        print(f"\n处理品种: {sym}")

        # 删除旧基线
        bp = baseline_paths(sym, None)
        if os.path.exists(bp):
            os.remove(bp)
            print(f"  已删除旧基线: {bp}")

        # 重生基线
        try:
            ensure_baselines([sym])
            print(f"  基线重生完成")

            # 验证新基线
            if os.path.exists(bp):
                with open(bp) as f:
                    lines = f.readlines()
                print(f"  新基线行数: {len(lines)}")
                if lines:
                    import json
                    first = json.loads(lines[0])
                    last = json.loads(lines[-1])
                    print(f"  时间范围: {first.get('cutoff')} ~ {last.get('cutoff')}")
            else:
                print(f"  ERROR: 基线未生成")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n=== 完成 ===")

if __name__ == "__main__":
    main()
