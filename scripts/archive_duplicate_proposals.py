#!/usr/bin/env python3
"""Archive duplicate proposal files, keeping only the latest (by mtime) per stem.

Usage:
    python scripts/archive_duplicate_proposals.py --dry-run     # simulate
    python scripts/archive_duplicate_proposals.py --execute     # move files
    python scripts/archive_duplicate_proposals.py --rollback    # restore
"""

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENTS_DIR = Path("task_FM/experiments")
ARCHIVE_DIR = EXPERIMENTS_DIR / "archive"
MANIFEST_PATH = ARCHIVE_DIR / "archive_manifest.jsonl"


def scan_proposals():
    files = []
    for run_dir in sorted(EXPERIMENTS_DIR.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        for p in run_dir.rglob("proposals/*.json"):
            if p.name.endswith(".prescreen.json"):
                continue
            st = p.stat()
            files.append({
                "path": str(p),
                "stem": p.stem,
                "run_id": run_dir.name,
                "relative": str(p.relative_to(run_dir)),
                "mtime": st.st_mtime,
                "size": st.st_size,
            })
    return files


def group_by_stem(files):
    groups = defaultdict(list)
    for f in files:
        groups[f["stem"]].append(f)
    return dict(groups)


def plan_archive(groups):
    to_keep = []
    to_archive = []
    for stem, entries in groups.items():
        entries_sorted = sorted(entries, key=lambda e: e["mtime"], reverse=True)
        to_keep.append(entries_sorted[0])
        to_archive.extend(entries_sorted[1:])
    return to_keep, to_archive


def archive_path(entry):
    return ARCHIVE_DIR / entry["run_id"] / entry["relative"]


def do_dry_run():
    files = scan_proposals()
    groups = group_by_stem(files)
    to_keep, to_archive = plan_archive(groups)

    total_size = sum(f["size"] for f in to_archive)
    unique_stems = len(groups)

    print("=== Dry Run Report ===")
    print(f"Total proposal files scanned: {len(files)}")
    print(f"Unique stems: {unique_stems}")
    print(f"Files to keep (latest per stem): {len(to_keep)}")
    print(f"Files to archive (duplicates): {len(to_archive)}")
    print(f"Space to reclaim: {total_size / 1024:.1f} KB ({total_size / 1024 / 1024:.2f} MB)")
    print(f"Archive dir: {ARCHIVE_DIR.resolve()}")
    print()

    top_dupes = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]
    print("Top 10 most duplicated stems:")
    for stem, entries in top_dupes:
        print(f"  {stem}: {len(entries)} copies")
    print()

    if to_archive:
        print("First 5 files to archive:")
        for e in to_archive[:5]:
            print(f"  {e['path']}")
    print()
    print("Run with --execute to perform the archive.")
    return to_keep, to_archive


def do_execute():
    if MANIFEST_PATH.exists():
        existing = sum(1 for line in MANIFEST_PATH.open() if line.strip())
        if existing > 0:
            print(f"ERROR: Archive already has {existing} entries. Use --rollback first.")
            sys.exit(1)

    files = scan_proposals()
    groups = group_by_stem(files)
    to_keep, to_archive = plan_archive(groups)

    print(f"Archiving {len(to_archive)} duplicate files (keeping {len(to_keep)} latest)...")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archived_count = 0
    manifest_lines = []

    for entry in to_archive:
        src = Path(entry["path"])
        dst = archive_path(entry)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        src.unlink()
        archived_count += 1
        manifest_lines.append(json.dumps({
            "stem": entry["stem"],
            "run_id": entry["run_id"],
            "original_path": entry["path"],
            "archive_path": str(dst),
            "mtime": entry["mtime"],
            "size": entry["size"],
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))

    with MANIFEST_PATH.open("w") as f:
        for line in manifest_lines:
            f.write(line + "\n")

    total_size = sum(e["size"] for e in to_archive)
    print(f"Done. Archived {archived_count} files, reclaimed {total_size / 1024:.1f} KB.")
    print(f"Manifest: {MANIFEST_PATH}")


def do_rollback():
    if not MANIFEST_PATH.exists():
        print(f"ERROR: No manifest found at {MANIFEST_PATH}")
        sys.exit(1)

    entries = []
    with MANIFEST_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    print(f"Restoring {len(entries)} files from archive...")
    restored = 0
    for entry in entries:
        src = Path(entry["archive_path"])
        dst = Path(entry["original_path"])
        if not src.exists():
            print(f"  WARNING: {src} not found, skipping")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        src.unlink()
        restored += 1

    for dirpath, dirnames, filenames in os.walk(str(ARCHIVE_DIR), topdown=False):
        if not filenames and not dirnames:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass

    if MANIFEST_PATH.exists():
        MANIFEST_PATH.unlink()

    print(f"Restored {restored} files. Archive cleared.")


def main():
    parser = argparse.ArgumentParser(description="Archive duplicate proposal files")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Simulate archive (default)")
    group.add_argument("--execute", action="store_true",
                       help="Actually move files to archive")
    group.add_argument("--rollback", action="store_true",
                       help="Restore archived files")
    args = parser.parse_args()

    os.chdir(Path(__file__).resolve().parent.parent)

    if args.execute:
        do_execute()
    elif args.rollback:
        do_rollback()
    else:
        do_dry_run()


if __name__ == "__main__":
    main()
