#!/usr/bin/env python3
"""scripts/migrate_verdicts_tier.py -- 批量为现有 verdict 添加 tier 评分

幂等: 已有 tier 字段的 verdict 跳过.
原子写入: 写到临时文件然后替换原文件.
输出统计: 各等级数量.

用法:
    python scripts/migrate_verdicts_tier.py
    python scripts/migrate_verdicts_tier.py --registry path/to/verdicts.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)

from cascade.tier_classifier import compute_tier_score

DEFAULT_REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")


def migrate_registry(registry_path: str) -> None:
    if not os.path.exists(registry_path):
        print(f"文件不存在: {registry_path}", file=sys.stderr)
        sys.exit(1)

    records = []
    skipped = 0
    migrated = 0
    tier_counter = Counter()

    with open(registry_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                v = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "tier" in v:
                skipped += 1
                tier_counter[v["tier"]] += 1
                records.append(v)
                continue

            tier_info = compute_tier_score(v)
            v["tier"] = tier_info["tier"]
            v["tier_score"] = tier_info["tier_score"]
            v["tier_label"] = tier_info["tier_label"]
            v["tier_breakdown"] = tier_info["tier_breakdown"]
            tier_counter[v["tier"]] += 1
            migrated += 1
            records.append(v)

    # 原子写入: 临时文件 -> 替换 (MEDIUM-2: try/finally 清理)
    dir_name = os.path.dirname(registry_path) or "."
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=dir_name,
                                          delete=False, suffix=".tmp") as tmp:
            tmp_path = tmp.name
            for v in records:
                tmp.write(json.dumps(v, ensure_ascii=False) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, registry_path)
    except:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    print(f"迁移完成: {registry_path}")
    print(f"  已迁移: {migrated}")
    print(f"  已跳过: {skipped}")
    print(f"  总计: {len(records)}")
    print(f"  等级分布:")
    for tier in ["S", "A", "B", "C", "D"]:
        count = tier_counter.get(tier, 0)
        if count > 0:
            print(f"    {tier}: {count}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", default=DEFAULT_REGISTRY,
                    help="verdict 注册表路径 (默认: task_FM/config/aligned_verdicts.jsonl)")
    args = ap.parse_args(argv)
    migrate_registry(args.registry)


if __name__ == "__main__":
    main()
