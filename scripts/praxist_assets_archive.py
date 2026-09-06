#!/usr/bin/env python3
"""Append-only archive of Praxist fast/slow products into /workspace/shared/praxist_assets.

Called from praxist_supervisor after harvest and slow_drain_complete.
Also provides restore helpers for new machines / cleared caches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(os.environ.get("PRAXIST_ASSETS_ROOT", "/workspace/shared/praxist_assets"))
SHANGHAI = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.now(SHANGHAI)


def _ts() -> str:
    return _now().isoformat()


def _sha256_file(path: Path, limit_mb: float = 64.0) -> str | None:
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > limit_mb * 1024 * 1024:
            return None
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _append_timeline(title: str, bullets: list[str]) -> None:
    tl = ASSETS / "timeline.md"
    lines = [f"\n## {title}\n", f"- ts: {_ts()}\n"]
    for b in bullets:
        lines.append(f"- {b}\n")
    with tl.open("a", encoding="utf-8") as f:
        f.writelines(lines)


def _update_index(row: dict) -> None:
    idx = ASSETS / "INDEX.md"
    # rewrite small index table last-row style (file is small)
    header = (
        "# Praxist assets INDEX\n\n"
        "| ts | kind | run_id / cycle | headline |\n"
        "|----|------|----------------|----------|\n"
    )
    old_rows = []
    if idx.exists():
        for line in idx.read_text().splitlines():
            if line.startswith("|") and "ts" not in line and "----" not in line:
                old_rows.append(line)
    new = (
        f"| {row.get('ts','')} | {row.get('kind','')} | "
        f"{row.get('ref','')} | {row.get('headline','').replace('|','/')} |"
    )
    old_rows.append(new)
    # keep last 40
    body = header + "\n".join(old_rows[-40:]) + "\n"
    idx.write_text(body)


def _run_dir(run_id: str | None) -> Path | None:
    if not run_id:
        return None
    p = FM_ROOT / "task_FM" / "experiments" / run_id
    return p if p.is_dir() else None


def _copy_small(src: Path, dest: Path) -> dict:
    meta = {"path": str(src), "copied": False, "sha256": _sha256_file(src)}
    if not src.is_file():
        return meta
    # skip huge
    if src.stat().st_size > 32 * 1024 * 1024:
        meta["note"] = "skipped_large"
        return meta
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    meta["copied"] = True
    meta["asset_path"] = str(dest)
    return meta


def archive_fast_harvest(run_id: str, survivors: list, st: dict | None = None) -> dict:
    """Archive after harvest enqueue (fast ring products + survivor list)."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    run = _run_dir(run_id)
    dest_run = ASSETS / "runs" / (run_id or "unknown")
    dest_run.mkdir(parents=True, exist_ok=True)
    files = {}
    if run:
        for name in (
            "orchestrator_status.final.json",
            "orchestrator_status.json",
            "run_summary.json",
            "run.json",
        ):
            files[name] = _copy_small(run / name, dest_run / name)
        # frontier / gems pointers
        frontier = run / "frontier" / "frontier_manifest.json"
        files["frontier_manifest.json"] = _copy_small(frontier, dest_run / "frontier_manifest.json")
        # findings count
        sf = run / "shared_findings"
        findings_n = len(list(sf.glob("*.json"))) if sf.is_dir() else 0
        # human reports under task_FM/docs
        reports = sorted(
            (FM_ROOT / "task_FM" / "docs" / "praxist_reports").glob(f"*{run_id}*.md")
        ) if run_id else []
        report_paths = [str(p) for p in reports[-5:]]
        for rp in reports[-3:]:
            _copy_small(rp, ASSETS / "reports" / rp.name)
    else:
        findings_n = 0
        report_paths = []

    cycle = int((st or {}).get("cycles_done") or 0)
    rec = {
        "id": f"{_now().strftime('%Y%m%d')}-fm研-harvest-{run_id or 'na'}",
        "ts": ts,
        "kind": "fast_harvest",
        "run_id": run_id,
        "cycle": cycle,
        "survivors": [
            {"variant_id": r.get("variant_id"), "symbol": r.get("symbol"),
             "cov_override": r.get("cov_override"), "max_points": r.get("max_points")}
            for r in (survivors or [])
        ],
        "findings_n": findings_n,
        "reports": report_paths,
        "files": files,
    }
    _append_jsonl(ASSETS / "manifest.jsonl", rec)
    (dest_run / "harvest.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    vids = [s["variant_id"] for s in rec["survivors"]]
    _append_timeline(
        f"fast harvest `{run_id}`",
        [f"survivors ({len(vids)}): {', '.join(vids) or '(none)'}",
         f"findings_n={findings_n}", f"cycle≈{cycle}"],
    )
    _update_index({
        "ts": ts, "kind": "fast_harvest", "ref": run_id or "",
        "headline": f"survivors={vids}",
    })
    return rec


def archive_slow_cycle(st: dict, goal: dict | None = None) -> dict:
    """Archive after slow_drain_complete."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    cycle = int((st or {}).get("cycles_done") or 0)
    run_id = (st or {}).get("last_harvested_run_id") or (st or {}).get("last_run_id")
    cycle_id = f"cycle_{cycle:03d}_{_now().strftime('%Y%m%d_%H%M%S')}"
    dest = ASSETS / "cycles" / cycle_id
    dest.mkdir(parents=True, exist_ok=True)

    # verdicts incremental slice: copy full registry as snapshot + note
    reg = FM_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"
    verdicts_meta = _copy_small(reg, ASSETS / "verdicts" / f"{cycle_id}_aligned_verdicts.jsonl")
    metrics = FM_ROOT / "data" / "cache" / "slow_loop_metrics.jsonl"
    metrics_meta = _copy_small(metrics, dest / "slow_loop_metrics.jsonl")

    # recent checkpoint files mentioned in last metrics lines
    survivors = []
    if metrics.exists():
        for line in metrics.read_text().splitlines()[-10:]:
            if not line.strip():
                continue
            try:
                survivors.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # gate results from registry tail
    gates = []
    if reg.exists():
        for line in reg.read_text().splitlines()[-20:]:
            if not line.strip():
                continue
            try:
                j = json.loads(line)
                gates.append({
                    "variant_id": j.get("variant_id"),
                    "gate_pass": j.get("gate_pass"),
                    "pf": j.get("pf"),
                    "ev": j.get("ev"),
                    "n": j.get("n") or j.get("max_points"),
                    "decided_at": j.get("decided_at"),
                })
            except json.JSONDecodeError:
                continue

    cad = (goal or {}).get("cadence") or {}
    rec = {
        "id": f"{_now().strftime('%Y%m%d')}-fm研-slow-{cycle_id}",
        "ts": ts,
        "kind": "slow_drain",
        "cycle": cycle,
        "run_id": run_id,
        "cadence": {
            "survivors_per_cycle": cad.get("survivors_per_cycle"),
            "aligned_max_points": cad.get("aligned_max_points"),
        },
        "metrics_tail": survivors,
        "gates_tail": gates[-10:],
        "verdicts": verdicts_meta,
        "metrics_file": metrics_meta,
        "phase_after": (st or {}).get("phase"),
    }
    _append_jsonl(ASSETS / "manifest.jsonl", rec)
    (dest / "summary.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    gate_s = ", ".join(
        f"{g.get('variant_id')} gate={g.get('gate_pass')}" for g in gates[-5:]
    ) or "(no new gates)"
    _append_timeline(
        f"slow drain cycle={cycle}",
        [f"run={run_id}", f"gates: {gate_s}", f"phase_after={rec['phase_after']}"],
    )
    _update_index({
        "ts": ts, "kind": "slow_drain", "ref": f"cycle={cycle}",
        "headline": gate_s,
    })
    return rec


def restore_verdicts(assets: Path, dest: Path) -> int:
    """Merge verdicts/*.jsonl into dest (latest variant_id wins)."""
    by_id = {}
    order = []
    if dest.exists():
        for line in dest.read_text().splitlines():
            if not line.strip():
                continue
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = j.get("variant_id") or j.get("variant_name")
            if not vid:
                continue
            if vid not in by_id:
                order.append(vid)
            by_id[vid] = j
    for vp in sorted((assets / "verdicts").glob("*.jsonl")):
        for line in vp.read_text().splitlines():
            if not line.strip():
                continue
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = j.get("variant_id") or j.get("variant_name")
            if not vid:
                continue
            if vid not in by_id:
                order.append(vid)
            by_id[vid] = j
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        for vid in order:
            f.write(json.dumps(by_id[vid], ensure_ascii=False) + "\n")
    return len(order)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("restore-verdicts")
    p1.add_argument("--assets", default=str(ASSETS))
    p1.add_argument("--dest", default=str(FM_ROOT / "task_FM/config/aligned_verdicts.jsonl"))
    p2 = sub.add_parser("smoke-harvest")
    p2.add_argument("--run-id", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "restore-verdicts":
        n = restore_verdicts(Path(args.assets), Path(args.dest))
        print(json.dumps({"restored": n, "dest": args.dest}))
        return 0
    if args.cmd == "smoke-harvest":
        rec = archive_fast_harvest(args.run_id, [])
        print(json.dumps({"ok": True, "id": rec["id"]}))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
