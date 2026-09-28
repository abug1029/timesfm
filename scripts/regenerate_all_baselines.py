#!/usr/bin/env python3
"""强制重生全部品种的 nocov 基线。

**为什么需要强制**：`praxist_supervisor.ensure_baselines` 的判据是
「行数 >= 100 且 protocol_fingerprint 匹配」。而 `compute_protocol_fingerprint()`
是**协议配置**哈希，不覆盖数据窗口语义 —— 本次 1-bar 前视修复
（commit 968945f，`_h1_upper_bound = cutoff_ts − 1h`）改变了模型实际
消费的 bar 区间，但指纹不变。故旧基线会被判「有效」而静默跳过。
必须显式删除才能触发重生。

**旧基线已备份**至 `data/archive/baselines_pre_lookahead_fix_2026-09-28/`。

用法:
    .venv/bin/python scripts/regenerate_all_baselines.py            # 只报告
    .venv/bin/python scripts/regenerate_all_baselines.py --force    # 删旧 + 重生
"""
import argparse
import json
import sys
from pathlib import Path

FM_ROOT = Path("/home/abug/timesfm")
sys.path.insert(0, str(FM_ROOT))
sys.path.insert(0, str(FM_ROOT / "scripts"))

CONFIG_DIR = FM_ROOT / "task_FM" / "config"
SYMBOLS = ["ss", "sr", "m", "jd", "lh", "cj", "fu", "rb", "eg"]


def baseline_file(sym: str) -> Path:
    """nocov 基线的实际路径（与 generate_baseline_points 的输出约定一致）。"""
    return CONFIG_DIR / ("baseline_points_%s_nocov.jsonl" % sym)


def _describe(p: Path) -> str:
    if not p.exists():
        return "缺失"
    lines = [ln for ln in p.open(encoding="utf-8") if ln.strip()]
    try:
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        return "%d 行  %s ~ %s" % (
            len(lines), first.get("cutoff"), last.get("cutoff"))
    except Exception as e:
        return "%d 行（解析失败: %s）" % (len(lines), e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="删除旧基线后重生（默认只报告）")
    args = ap.parse_args()

    print("=== 当前 nocov 基线 ===")
    for sym in SYMBOLS:
        print("  %-4s %s" % (sym, _describe(baseline_file(sym))))

    if not args.force:
        print("\n（未改动；加 --force 删除并重生）")
        return 0

    from praxist_supervisor import ensure_baselines

    print("\n=== 删除旧基线 ===")
    for sym in SYMBOLS:
        p = baseline_file(sym)
        if p.exists():
            p.unlink()
            print("  已删 %s" % p.name)

    print("\n=== 重生（逐个，耗时较长）===")
    for sym in SYMBOLS:
        print("\n--- %s ---" % sym, flush=True)
        try:
            ensure_baselines([sym], str(FM_ROOT))
        except Exception as e:
            print("  ERROR: %s" % e, flush=True)
            continue
        print("  %s" % _describe(baseline_file(sym)), flush=True)

    print("\n=== 完成 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
