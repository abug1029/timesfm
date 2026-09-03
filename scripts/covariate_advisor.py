#!/usr/bin/env python3
"""
covariate_advisor.py — FM_a 自适应协变量重扫描

检测退化品种，对比当前协变量 vs 最优协变量，生成更新提案。
只提案不修改 prediction_scheme.py（高风险路径）。

用法:
    python scripts/covariate_advisor.py
"""

import json
import re
import subprocess
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = FM_ROOT / "reports"
DRIFT_FILE = REPORTS_DIR / "drift_tracking.json"
PROPOSAL_FILE = REPORTS_DIR / "covariate_proposals.json"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES

# 提案门槛: DirAcc 提升 > 3pp 才建议更换
MIN_DIRACC_IMPROVEMENT = 0.03


def load_drift() -> dict:
    if not DRIFT_FILE.exists():
        return {}
    try:
        return json.loads(DRIFT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_scheme_covariates() -> dict:
    """从 prediction_scheme.py 读取各品种的当前协变量类型。"""
    covariates = {}
    scheme_path = FM_ROOT / "config" / "prediction_scheme.py"
    if not scheme_path.exists():
        return covariates
    try:
        text = scheme_path.read_text(encoding="utf-8")
        # 匹配: symbol="ss", ... covariate_type="xxx"
        for m in re.finditer(
            r'symbol=["\'](\w+)["\'].*?covariate_type=["\'](\w+)["\']',
            text, re.DOTALL
        ):
            covariates[m.group(1).lower()] = m.group(2)
    except Exception:
        pass
    return covariates


def find_degraded_symbols(drift_data: dict) -> list[str]:
    """找到处于 warning 或 alert 状态的品种。"""
    degraded = []
    for sym, data in drift_data.get("symbols", {}).items():
        if data.get("status") in ("warning", "alert"):
            degraded.append(sym)
    return degraded


def run_covariate_scan(symbol: str) -> list[dict]:
    """运行 covariate_scan.py 并解析结果。

    返回 [{covariate_type, dir_acc, mape}, ...]
    """
    script = FM_ROOT / "scripts" / "covariate_scan.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), symbol],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300, cwd=FM_ROOT,
        )
        results = []
        # 解析 stdout 中的回测结果表
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c != ""]
            if len(cells) < 3:
                continue
            if re.match(r"^[-:]+$", cells[0]):
                continue
            if cells[0] in ("协变量", "类型"):
                continue
            try:
                results.append({
                    "covariate_type": cells[0],
                    "dir_acc": float(cells[1].replace("%", "")) / 100 if "%" in cells[1] else float(cells[1]),
                    "mape": float(cells[2].replace("%", "")),
                })
            except (ValueError, IndexError):
                continue
        return results
    except Exception:
        return []


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 🔧 协变量优化提案\n")
    print(f"**时间**: {now_str}\n")

    drift_data = load_drift()
    if not drift_data:
        print("> 无漂移数据，请先运行 drift_detector.py\n")
        return

    degraded = find_degraded_symbols(drift_data)
    if not degraded:
        print("✅ 无退化品种，无需协变量优化\n")
        json.dump({"proposals": []}, sys.stderr, ensure_ascii=False)
        return

    print(f"**退化品种**: {len(degraded)} 个 — {', '.join(f'`{s}`' for s in degraded)}\n")

    current_covs = load_scheme_covariates()
    proposals = []

    for sym in degraded:
        print(f"---\n### {sym} ({SYMBOL_NAMES.get(sym, '')})\n")
        current_cov = current_covs.get(sym, "unknown")
        drift_info = drift_data.get("symbols", {}).get(sym, {})

        print(f"- 当前协变量: `{current_cov}`")
        print(f"- 滑动 DirAcc: {drift_info.get('dir_acc', 'N/A')}")
        print(f"- 滑动 MAPE: {drift_info.get('mape', 'N/A')}%\n")

        scan_results = run_covariate_scan(sym)
        if not scan_results:
            print("- 协变量扫描无结果（数据可能不足）\n")
            continue

        # 找最优协变量
        best = max(scan_results, key=lambda x: x["dir_acc"])
        current_result = next((r for r in scan_results if r["covariate_type"] == current_cov), None)
        current_da = current_result["dir_acc"] if current_result else drift_info.get("dir_acc", 0)

        improvement = best["dir_acc"] - current_da
        print(f"- 当前 DirAcc: {current_da:.1%}")
        print(f"- 最优: `{best['covariate_type']}` ({best['dir_acc']:.1%})")
        print(f"- 提升: {improvement:+.1%}")

        if improvement >= MIN_DIRACC_IMPROVEMENT and best["covariate_type"] != current_cov:
            proposals.append({
                "symbol": sym,
                "name": SYMBOL_NAMES.get(sym, ""),
                "current_covariate": current_cov,
                "proposed_covariate": best["covariate_type"],
                "current_dir_acc": round(current_da, 4),
                "proposed_dir_acc": round(best["dir_acc"], 4),
                "improvement": round(improvement, 4),
                "timestamp": now_str,
            })
            print(f"- ✅ **提案**: `{current_cov}` → `{best['covariate_type']}`")
        else:
            print(f"- ⏸️ 提升不足 {MIN_DIRACC_IMPROVEMENT:.0%}，暂不提案")
        print()

    # 保存提案
    if proposals:
        PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROPOSAL_FILE.write_text(
            json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n## 提案汇总 ({len(proposals)} 个)\n")
        print(f"提案已保存到 `{PROPOSAL_FILE.name}`。")
        print(f"需人工确认后修改 `config/prediction_scheme.py`。\n")
        print("| 品种 | 当前协变量 | 提议协变量 | 提升 |")
        print("|------|-----------|-----------|:----:|")
        for p in proposals:
            print(f"| `{p['symbol']}` | `{p['current_covariate']}` | `{p['proposed_covariate']}` | {p['improvement']:+.1%} |")
    else:
        print("\n## 无提案\n")
        print("所有退化品种的当前协变量仍为最优。")

    json.dump({"proposal_count": len(proposals), "proposals": proposals},
              sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
