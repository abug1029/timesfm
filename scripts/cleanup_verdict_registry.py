#!/usr/bin/env python3
"""Cleanup verdict registry - spec 4.1

One-time script to clean aligned_verdicts.jsonl and aligned_pending.jsonl:
- Archive old protocol records
- Keep current protocol: valid runs, terminal states, n=0 completed (canonicalized)
- Quarantine n=0 incomplete
- Dedup by (symbol, cov, mode) keeping latest (decided_at, line_idx)
- Atomic write with process guard and file lock
"""
import argparse
import fcntl
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.registry_lib import (
    TERMINAL_STATUSES,
    CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov,
    canonical_mode,
    effective_n,
)


def check_process_guard():
    """Check if slow loop processes are running. Abort if so."""
    try:
        import psutil
    except ImportError:
        return
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if any(t in cmdline for t in ["aligned_slow_loop", "praxist_supervisor"]):
                raise RuntimeError(
                    f"Process still running: PID {proc.pid} ({cmdline[:50]}...). "
                    "Stop all slow loop processes first."
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def main(verdict_path, pending_path, current_fp=None, archive_dir=None):
    """Main cleanup function.

    Args:
        verdict_path: Path to aligned_verdicts.jsonl
        pending_path: Path to aligned_pending.jsonl
        current_fp: Current protocol fingerprint
        archive_dir: Directory for archive files (default: same as verdict_path)
    """
    if current_fp is None:
        current_fp = CURRENT_PROTOCOL_FINGERPRINT
    verdict_path = Path(verdict_path)
    pending_path = Path(pending_path)
    archive_dir = Path(archive_dir) if archive_dir else verdict_path.parent

    # 1. Process guard
    check_process_guard()

    # 2. Read verdicts WITH line index
    verdicts_keep = []
    verdicts_archive = []
    verdicts_quarantine = []

    if verdict_path.exists():
        with open(verdict_path, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            for idx, line in enumerate(f):
                if not line.strip():
                    continue
                v = json.loads(line)
                fp = v.get("protocol_fingerprint")
                n_eff_val = effective_n(v)
                status = v.get("status")

                is_valid = fp == current_fp and n_eff_val > 0 and status == "ok"
                is_terminal = fp == current_fp and status in TERMINAL_STATUSES
                is_n0_completed = (
                    fp == current_fp
                    and n_eff_val == 0
                    and (v.get("decided_at") or v.get("completed_at") or v.get("error"))
                )

                if is_valid or is_terminal:
                    verdicts_keep.append((idx, v))
                elif is_n0_completed:
                    v["status"] = "error"
                    verdicts_keep.append((idx, v))
                elif fp == current_fp and n_eff_val == 0:
                    verdicts_quarantine.append(v)
                else:
                    verdicts_archive.append(v)

    # 3. Group by (symbol, cov, mode) with field canonicalization
    groups = defaultdict(list)
    for idx, v in verdicts_keep:
        key = (v.get("symbol"), canonical_cov(v), canonical_mode(v))
        groups[key].append((idx, v))

    # 4. Dedup: keep latest by (decided_at, line_idx) descending
    deduped = []
    for key, group in groups.items():
        group.sort(key=lambda x: (x[1].get("decided_at") or "", x[0]), reverse=True)
        best_idx, best_v = group[0]
        best_v["cov_override"] = key[1]
        best_v["run_mode"] = key[2]
        deduped.append(best_v)

    # 5. Write verdicts (atomic)
    tmp_path = str(verdict_path) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for v in deduped:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
    os.replace(tmp_path, str(verdict_path))

    # 6. Clean pending queue
    cleaned_keys = set()
    for v in deduped:
        cleaned_keys.add((v.get("symbol"), canonical_cov(v), canonical_mode(v)))

    pending_kept = []
    if pending_path.exists():
        seen_pending = set()
        with open(pending_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                p = json.loads(line)
                if p.get("protocol_fingerprint") != current_fp:
                    continue
                key = (p.get("symbol"), canonical_cov(p), canonical_mode(p))
                if key in cleaned_keys or key in seen_pending:
                    continue
                seen_pending.add(key)
                pending_kept.append(p)

        tmp_pending = str(pending_path) + ".tmp"
        with open(tmp_pending, "w", encoding="utf-8") as f:
            for p in pending_kept:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        os.replace(tmp_pending, str(pending_path))

    # 7. Archive (timestamped)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"aligned_verdicts.archive.{ts}.jsonl"
    with open(archive_path, "w", encoding="utf-8") as f:
        for v in verdicts_archive:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")

    # 8. Quarantine (timestamped)
    if verdicts_quarantine:
        quarantine_path = archive_dir / f"aligned_verdicts.quarantine.{ts}.jsonl"
        with open(quarantine_path, "w", encoding="utf-8") as f:
            for v in verdicts_quarantine:
                f.write(json.dumps(v, ensure_ascii=False) + "\n")

    # 9. Summary
    total = len(verdicts_keep) + len(verdicts_archive) + len(verdicts_quarantine)
    print(
        f"Verdicts: {total} -> {len(deduped)} (deduped), "
        f"{len(verdicts_archive)} archived, {len(verdicts_quarantine)} quarantined"
    )
    print(f"Pending: {len(pending_kept)} items")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup verdict registry")
    parser.add_argument(
        "--verdict-path", default="task_FM/config/aligned_verdicts.jsonl"
    )
    parser.add_argument(
        "--pending-path", default="task_FM/config/aligned_pending.jsonl"
    )
    parser.add_argument(
        "--current-fingerprint", default=CURRENT_PROTOCOL_FINGERPRINT
    )
    parser.add_argument("--archive-dir", default=None)
    args = parser.parse_args()
    main(args.verdict_path, args.pending_path, args.current_fingerprint, args.archive_dir)
