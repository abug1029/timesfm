#!/usr/bin/env python3
import json, shutil
from collections import defaultdict
from pathlib import Path

EXPERIMENTS = Path("/home/abug/timesfm/task_FM/experiments")
VERDICTS = Path("/home/abug/timesfm/task_FM/config/aligned_verdicts.jsonl")
ASSETS = Path("/home/abug/timesfm/task_FM/assets")

def load_verdicts():
    core, secondary = [], []
    with open(VERDICTS) as f:
        for line in f:
            v = json.loads(line)
            tier = v.get("tier", "")
            da = v.get("dir_acc", 0) or 0
            if tier in ("S", "A") and da >= 0.52:
                core.append(v)
            elif tier == "B" and da >= 0.48:
                secondary.append(v)
    return core, secondary

def build_proposal_index():
    print("Scanning experiment proposals...")
    idx = defaultdict(list)
    count = 0
    for p in EXPERIMENTS.rglob("proposals/*.json"):
        idx[p.stem].append((p.stat().st_mtime, p))
        count += 1
    print(f"  Found {count} proposal files, {len(idx)} unique variant_ids")
    for vid in idx:
        idx[vid].sort(key=lambda x: x[0], reverse=True)
    return idx

def main():
    core, secondary = load_verdicts()
    print(f"Verdicts: {len(core)} core, {len(secondary)} secondary")
    idx = build_proposal_index()

    stats = {
        "core_count": 0, "secondary_count": 0,
        "core_bytes": 0, "secondary_bytes": 0,
        "core_by_sym": defaultdict(int), "secondary_by_sym": defaultdict(int),
        "missing_proposal": 0, "missing_checkpoint": 0, "warnings": [],
    }

    def copy_set(items, label):
        for v in items:
            vid = v["variant_id"]
            sym = v["symbol"]
            dest_dir = ASSETS / label / sym
            dest_dir.mkdir(parents=True, exist_ok=True)
            entries = idx.get(vid)
            if not entries:
                stats["missing_proposal"] += 1
                stats["warnings"].append("MISSING proposal: " + vid)
                continue
            src = entries[0][1]
            dst = dest_dir / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
                stats[label + "_bytes"] += dst.stat().st_size
            stats[label + "_count"] += 1
            stats[label + "_by_sym"][sym] += 1
            cp = v.get("checkpoint_path")
            if cp:
                cp_path = Path(cp)
                if cp_path.exists():
                    cp_dst = dest_dir / cp_path.name
                    if not cp_dst.exists():
                        shutil.copy2(cp_path, cp_dst)
                        stats[label + "_bytes"] += cp_dst.stat().st_size
                else:
                    stats["missing_checkpoint"] += 1

    copy_set(core, "core")
    copy_set(secondary, "secondary")

    total_mb = (stats["core_bytes"] + stats["secondary_bytes"]) / 1024 / 1024
    print()
    print("=== Extraction Report ===")
    print("Core:       %d proposals, %.1f KB" % (stats["core_count"], stats["core_bytes"]/1024))
    print("Secondary:  %d proposals, %.1f KB" % (stats["secondary_count"], stats["secondary_bytes"]/1024))
    print("Total size: %.2f MB" % total_mb)
    print("Missing proposal files:    %d" % stats["missing_proposal"])
    print("Missing checkpoint files:  %d" % stats["missing_checkpoint"])
    print()
    print("Core by symbol:")
    for sym, n in sorted(stats["core_by_sym"].items()):
        print("  %s: %d" % (sym, n))
    print()
    print("Secondary by symbol:")
    for sym, n in sorted(stats["secondary_by_sym"].items()):
        print("  %s: %d" % (sym, n))
    if stats["warnings"]:
        print()
        print("Warnings (%d):" % len(stats["warnings"]))
        for w in stats["warnings"][:20]:
            print("  " + w)
        if len(stats["warnings"]) > 20:
            print("  ... and %d more" % (len(stats["warnings"]) - 20))

if __name__ == "__main__":
    main()
