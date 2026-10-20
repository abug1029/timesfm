#!/usr/bin/env python3
"""
backfill_variant_registry.py — 从 live 提案文件回填 variant registry

扫描 task_FM/experiments/run_*/results/**/proposals/*.json，提取每个提案的
stem（文件名去扩展名，与 sup_harvest.py 的 Path(sp).stem 规则一致），写入
data/cache/variant_registry.jsonl。

用法：
    python scripts/backfill_variant_registry.py --dry-run   # 仅打印统计
    python scripts/backfill_variant_registry.py --execute   # 实际写入

幂等：已存在的 stem 不重复写入。
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 仓库根
HERE = Path(__file__).resolve().parent
FM_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from variant_registry import VariantRegistry, _registry_lock  # noqa: E402

EXPERIMENTS_ROOT = FM_ROOT / "task_FM" / "experiments"
REGISTRY_PATH = FM_ROOT / "data" / "cache" / "variant_registry.jsonl"


def _run_id_from_path(filepath: Path) -> str:
    """从提案路径提取 run_id（最近的 run_* 祖先目录名）。"""
    for part in filepath.parts:
        if part.startswith("run_"):
            return part
    return "unknown"


def scan_live_stems():
    """扫描 live 提案，返回 {stem: {first_seen, run_id}}，按最早 mtime 取 first_seen。"""
    pattern = str(EXPERIMENTS_ROOT / "run_*" / "results" / "**" / "proposals" / "*.json")
    stems = {}
    for fp in glob.glob(pattern, recursive=True):
        p = Path(fp)
        stem = p.stem
        try:
            mtime = p.stat().st_mtime
            ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            ts = datetime.now(timezone.utc).isoformat()
        run_id = _run_id_from_path(p)
        rec = stems.get(stem)
        if rec is None or ts < rec["first_seen"]:
            stems[stem] = {"first_seen": ts, "run_id": run_id}
    return stems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="仅统计，不写入")
    ap.add_argument("--execute", action="store_true", help="实际写入 registry")
    ap.add_argument("--registry", default=str(REGISTRY_PATH), help="registry 路径")
    args = ap.parse_args()

    if not args.dry_run and not args.execute:
        ap.error("必须指定 --dry-run 或 --execute")
    if args.dry_run and args.execute:
        ap.error("--dry-run 与 --execute 互斥")

    registry_path = args.registry
    print(f"[scan] experiments root: {EXPERIMENTS_ROOT}")
    print(f"[scan] registry path:    {registry_path}")

    live = scan_live_stems()
    print(f"[scan] unique live stems: {len(live)}")

    reg = VariantRegistry(registry_path)
    reg.load()
    existing = reg.get_stems()
    print(f"[reg]  currently registered: {len(existing)}")

    will_add = sorted(set(live) - existing)
    already = sorted(set(live) & existing)
    stale = sorted(existing - set(live))

    print(f"[diff] will_add:   {len(will_add)}")
    print(f"[diff] already:    {len(already)}")
    print(f"[diff] stale (in registry but not in live): {len(stale)}")
    if stale:
        print(f"[warn] stale stems (前10): {stale[:10]}")

    if args.dry_run:
        if will_add:
            print(f"[dry-run] 前10 will_add: {will_add[:10]}")
        print("[dry-run] 未写入任何内容。使用 --execute 实际写入。")
        return 0

    # --execute
    if not will_add:
        print("[exec] nothing to add, registry already covers all live stems.")
        return 0

    records = []
    for stem in will_add:
        rec = live[stem]
        records.append({
            "stem": stem,
            "first_seen": rec["first_seen"],
            "run_id": rec["run_id"],
        })

    # 单次锁内批量追加，避免 N 次重读磁盘
    parent = os.path.dirname(registry_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _registry_lock(registry_path):
        with open(registry_path, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 验证：重读并对比
    reg2 = VariantRegistry(registry_path)
    reg2.load()
    final_stems = reg2.get_stems()
    live_set = set(live)
    missing = live_set - final_stems
    print(f"[exec] wrote {len(records)} records")
    print(f"[exec] registry unique stems after backfill: {len(final_stems)}")
    print(f"[exec] live stems not in registry: {len(missing)}")
    if missing:
        print(f"[err]  missing (前10): {sorted(missing)[:10]}")
        return 1
    print("[exec] 全部 live stem 已登记")
    return 0


if __name__ == "__main__":
    sys.exit(main())
