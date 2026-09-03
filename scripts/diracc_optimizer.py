#!/usr/bin/env python3
"""
diracc_optimizer.py — DirAcc 自动优化器

扫描 DirAcc < 70% 的品种，尝试所有协变量配置，自动应用最优方案。
每个品种: 运行 covariate_scan → 找最优协变量 → 更新 prediction_scheme.py

用法:
  python scripts/diracc_optimizer.py                    # 所有 <70% 品种
  python scripts/diracc_optimizer.py sr lh sp           # 指定品种
  python scripts/diracc_optimizer.py --threshold 0.60   # 调整阈值
  python scripts/diracc_optimizer.py --dry-run          # 仅扫描不应用
"""

import json
import os
import re
import subprocess
import sys
import time

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FM_ROOT = SCRIPT_DIR.parent
SCHEME_FILE = FM_ROOT / "config" / "prediction_scheme.py"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES

TARGET_DIRACC = 0.70  # 目标阈值


def get_current_schemes() -> dict:
    """从 prediction_scheme.py 读取所有品种的方案信息。"""
    text = SCHEME_FILE.read_text(encoding="utf-8")
    schemes = {}

    # 匹配每个 VarietyScheme 块
    pattern = r'VarietyScheme\(\s*symbol=["\'](\w+)["\'].*?dir_acc=([\d.]+).*?covariate_type=["\'](\w+)["\']'
    for m in re.finditer(pattern, text, re.DOTALL):
        sym = m.group(1).lower()
        schemes[sym] = {
            "dir_acc": float(m.group(2)),
            "covariate_type": m.group(3),
        }
    return schemes


def run_covariate_scan(symbol: str, timeout: int = 600) -> dict:
    """运行 covariate_scan.py 并解析结果。

    输出格式:
      最优: rsi_state            T+1=   2848.0 bias= +0.06% abl=53.0
      TOP 5:
        #1 rsi_state            : T+1=   2848.0 bias= +0.06% abl=53.0

    Returns: {covariates: [{type, bias}], best: {type, bias}, success: bool}
    """
    script = SCRIPT_DIR / "covariate_scan.py"
    cmd = [sys.executable, str(script), symbol]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=FM_ROOT,
        )
        output = proc.stdout or ""

        # 解析 TOP 5 行
        covariates = []
        for line in output.splitlines():
            line = line.strip()
            # 匹配: #1 rsi_state            : T+1=   2848.0 bias= +0.06% abl=53.0
            m = re.match(r'#\d+\s+(\S+)\s*:\s*T\+1=\s*([\d.]+)\s*bias=\s*([+-]?[\d.]+)%', line)
            if m:
                covariates.append({
                    "type": m.group(1),
                    "t1_pred": float(m.group(2)),
                    "bias": float(m.group(3)),
                })

        # 也解析最优行
        best_match = re.search(
            r'最优:\s*(\S+)\s+T\+1=\s*([\d.]+)\s+bias=\s*([+-]?[\d.]+)%', output
        )
        best = None
        if best_match:
            best = {
                "type": best_match.group(1),
                "t1_pred": float(best_match.group(2)),
                "bias": float(best_match.group(3)),
            }
        elif covariates:
            best = covariates[0]  # TOP 5 第一个就是最优

        return {
            "covariates": covariates,
            "best": best,
            "success": len(covariates) > 0,
        }

    except subprocess.TimeoutExpired:
        return {"covariates": [], "best": None, "success": False, "error": f"超时 ({timeout}s)"}
    except Exception as e:
        return {"covariates": [], "best": None, "success": False, "error": str(e)}


def apply_covariate_update(symbol: str, new_cov_type: str, new_dir_acc: float) -> bool:
    """更新 prediction_scheme.py 中指定品种的协变量类型。

    使用正则替换 covariate_type 和 dir_acc 字段。
    """
    text = SCHEME_FILE.read_text(encoding="utf-8")

    # 找到该品种的 VarietyScheme 块并更新 covariate_type
    # 匹配: symbol="xx", ... covariate_type="old_value",
    sym_pattern = rf'(symbol=["\']{symbol}["\'].*?)(covariate_type=["\'])(\w+)(["\'])'
    new_text = re.sub(
        sym_pattern,
        rf'\1\2{new_cov_type}\4',
        text,
        count=1,
        flags=re.DOTALL,
    )

    # 同时更新 dir_acc
    da_pattern = rf'(symbol=["\']{symbol}["\'].*?dir_acc=)([\d.]+)'
    new_text = re.sub(
        da_pattern,
        rf'\g<1>{new_dir_acc:.3f}',
        new_text,
        count=1,
        flags=re.DOTALL,
    )

    if new_text != text:
        # 备份原文件
        backup = SCHEME_FILE.with_suffix(".py.bak")
        backup.write_text(text, encoding="utf-8")

        SCHEME_FILE.write_text(new_text, encoding="utf-8")
        return True
    return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="DirAcc 自动优化器")
    parser.add_argument("symbols", nargs="*", help="指定品种 (默认: 所有 <70%)")
    parser.add_argument("--threshold", type=float, default=TARGET_DIRACC,
                        help=f"DirAcc 阈值 (默认: {TARGET_DIRACC})")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描不应用")
    args = parser.parse_args()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 🎯 DirAcc 优化器\n")
    print(f"**时间**: {now_str}  ")
    print(f"**目标**: DirAcc ≥ {args.threshold:.0%}\n")

    # 读取当前方案
    schemes = get_current_schemes()
    if not schemes:
        print("> 无法读取 prediction_scheme.py\n")
        return

    # 筛选需要优化的品种
    if args.symbols:
        targets = {s: schemes[s] for s in args.symbols if s in schemes}
    else:
        targets = {s: d for s, d in schemes.items() if d["dir_acc"] < args.threshold}

    if not targets:
        print("✅ 所有品种 DirAcc 已达标\n")
        return

    # 按 DirAcc 降序排列（优先处理最接近目标的）
    sorted_targets = sorted(targets.items(), key=lambda x: -x[1]["dir_acc"])

    print(f"**待优化**: {len(sorted_targets)} 个品种\n")
    print("| 品种 | 名称 | 当前DirAcc | 当前协变量 |")
    print("|------|------|:---------:|-----------|")
    for sym, d in sorted_targets:
        print(f"| `{sym}` | {SYMBOL_NAMES.get(sym, '')} "
              f"| {d['dir_acc']:.1%} | `{d['covariate_type']}` |")
    print()

    # 逐个扫描优化
    updated = []
    failed = []

    for i, (sym, d) in enumerate(sorted_targets, 1):
        print(f"---\n### [{i}/{len(sorted_targets)}] {sym.upper()} ({SYMBOL_NAMES.get(sym, '')})")
        print(f"当前: DirAcc={d['dir_acc']:.1%}, covariate=`{d['covariate_type']}`\n")

        print(f"扫描协变量中...")
        scan_start = time.time()
        result = run_covariate_scan(sym)
        scan_time = time.time() - scan_start

        if not result["success"] or not result["best"]:
            print(f"  ❌ 扫描失败\n")
            failed.append(sym)
            continue

        best = result["best"]
        is_different = best["type"] != d["covariate_type"]

        print(f"  最优: `{best['type']}` (T+1 bias={best['bias']:+.2f}%)")

        if not is_different:
            print(f"  ✅ 当前协变量已最优，无需更改\n")
            continue

        # 显示 TOP 5 供参考
        if result["covariates"]:
            print(f"  TOP 5:")
            for i, c in enumerate(result["covariates"][:5]):
                mark = " ← 当前" if c["type"] == d["covariate_type"] else ""
                print(f"    #{i+1} `{c['type']}` bias={c['bias']:+.2f}%{mark}")
        print()

        if args.dry_run:
            print(f"  📋 [dry-run] 建议: `{d['covariate_type']}` → `{best['type']}`\n")
            updated.append({
                "symbol": sym,
                "from": d["covariate_type"],
                "to": best["type"],
                "bias": best["bias"],
                "dry_run": True,
            })
        else:
            # 应用更新
            success = apply_covariate_update(sym, best["type"], d["dir_acc"])
            if success:
                print(f"  ✅ 已更新: `{d['covariate_type']}` → `{best['type']}`\n")
                updated.append({
                    "symbol": sym,
                    "from": d["covariate_type"],
                    "to": best["type"],
                    "bias": best["bias"],
                    "dir_acc": d["dir_acc"],
                })
            else:
                print(f"  ❌ 更新失败\n")
                failed.append(sym)

    # 汇总
    print(f"\n## 优化汇总\n")
    print(f"- 扫描品种: {len(sorted_targets)}")
    print(f"- 已更新: {len(updated)}")
    print(f"- 失败: {len(failed)}")

    if updated and not args.dry_run:
        print(f"\n## 更新详情\n")
        print("| 品种 | 原协变量 | 新协变量 | T+1偏差 | 当前DirAcc |")
        print("|------|---------|---------|:-------:|:----------:|")
        for u in updated:
            print(f"| `{u['symbol']}` | `{u['from']}` | `{u['to']}` "
                  f"| {u['bias']:+.2f}% | {u.get('dir_acc', 0):.1%} |")
        print(f"\n> 原文件备份: `config/prediction_scheme.py.bak`")

    # JSON to stderr
    json.dump({
        "total": len(sorted_targets),
        "updated": len(updated),
        "failed": len(failed),
        "updates": updated,
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
