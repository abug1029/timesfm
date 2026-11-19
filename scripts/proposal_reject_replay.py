"""只读回放 15 个实验目录的提案拒绝，不入队、不写 backlog。"""
import argparse
import glob
import json
import os
import sys

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_scripts_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import registry_lib as rl
import sup_evidence
import sup_harvest
import sup_paths
import sup_state

RUN_IDS = (
    "run_2026-11-17_01-55-15_primary_task_FM",
    "run_2026-11-17_03-55-34_primary_task_FM",
    "run_2026-11-17_05-56-23_primary_task_FM",
    "run_2026-11-17_07-56-25_primary_task_FM",
    "run_2026-11-17_10-57-34_primary_task_FM",
    "run_2026-11-17_13-50-15_primary_task_FM",
    "run_2026-11-17_16-05-58_primary_task_FM",
    "run_2026-11-17_18-07-01_primary_task_FM",
    "run_2026-11-18_00-28-23_primary_task_FM",
    "run_2026-11-18_02-25-52_primary_task_FM",
    "run_2026-11-18_04-23-37_primary_task_FM",
    "run_2026-11-18_06-22-12_primary_task_FM",
    "run_2026-11-18_08-38-47_primary_task_FM",
    "run_2026-11-18_10-41-10_primary_task_FM",
    "run_2026-11-18_12-41-11_primary_task_FM",
)

REJECT_SOURCE_ORDER = (
    "unparseable_json", "decision_abandon", "backlog_dup", "schema_mismatch",
    "missing_symbol_or_cov", "symbol_not_allowed", "cov_archived",
    "cov_not_in_active_pool", "no_current_baseline", "mechanism_too_short",
    "symbol_dead", "symbol_hold", "family_unresolved", "family_dead",
    "experiment_fp_unavailable", "no_failure_delta", "dedup", "dedup_evaluated",
    "sector_blocked", "cov_cross_fail", "quality_below_threshold",
    "no_success_delta",
)

_LEDGER_COUNTS = {
    "inventory": 269,
    "calendar": 150,
    "term_structure": 102,
    "momentum": 225,
    "volatility": 132,
    "not_in_pool": 1,
}
_TARGET_FAMILIES = ("inventory", "calendar")
_TOP_K = 3


def _search_check(p, symbol, cov, proposal_path):
    return None, None


def _v1_pool_family(proposal, pool):
    """仅假设提案按 cov_override 查活跃池。不读提案自报的族。"""
    if not isinstance(proposal, dict):
        return None, False
    if proposal.get("schema") != "fm.hypothesis_proposal.v1":
        return None, False
    cov = str(proposal.get("cov_override") or "").strip()
    row = pool.get(cov) if isinstance(pool, dict) else None
    if not isinstance(row, dict):
        return None, True
    fam = row.get("family")
    if not fam:
        return None, True
    return str(fam), True


def _dominant_reject(rows):
    counts = {}
    for row in rows:
        if row["kind"] != "reject":
            continue
        if row["pool_family"] not in _TARGET_FAMILIES:
            continue
        reason = row["reason"]
        counts[reason] = counts.get(reason, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    for code in REJECT_SOURCE_ORDER:
        if counts.get(code) == best:
            return code
    tied = sorted(code for code, n in counts.items() if n == best)
    return tied[0]


def _seat_tier(symbol, priority, n_cache):
    if not priority:
        return 0
    if symbol not in n_cache:
        n_cache[symbol] = sup_evidence._valid_n_for_symbol(symbol)
    n_now = n_cache[symbol]
    if symbol not in priority:
        return 2
    if n_now is not None and n_now >= sup_paths.RETEST_GATE_N:
        return 0
    return 1


def _select(candidates):
    ordered = sorted(
        candidates,
        key=lambda r: (r["_tier"], -r["_score"], r["_family"], r["variant_id"]),
    )
    selected = []
    used_families = set()
    for row in ordered:
        if len(selected) >= _TOP_K:
            break
        if row["_family"] in used_families:
            continue
        selected.append(row)
        used_families.add(row["_family"])
    if len(selected) < _TOP_K:
        chosen = {row["variant_id"] for row in selected}
        for row in ordered:
            if len(selected) >= _TOP_K:
                break
            if row["variant_id"] not in chosen:
                selected.append(row)
                chosen.add(row["variant_id"])
    return selected


def _ledger_matches(body):
    if body["proposal_json_excluding_prescreen"] != 894:
        return False
    if body["hypothesis_v1"] != 879:
        return False
    counts = body["family_counts"]
    for key, expected in _LEDGER_COUNTS.items():
        if counts.get(key) != expected:
            return False
    return True


def replay(root, output_path, goal_path, expect_ledger=False):
    if os.path.exists(output_path):
        return 0
    goal = sup_state.load_goal(goal_path)
    if sup_state._norm_search_policy(goal) != "shadow":
        return 2
    cadence = goal.get("cadence") or {}
    if sup_state._cad_int(cadence, "survivors_per_cycle") != 3:
        return 2
    priority_symbols = cadence.get("priority_symbols")
    priority = set(priority_symbols or [])

    snap = sup_evidence._active_protocol_snapshot(sup_paths.REGISTRY) or {}
    dead = rl.dead_variants(snap)
    existing = rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS) | set(snap.keys())
    pool = sup_evidence.load_covariate_pool() or {}
    passing_ids = {row["variant_id"] for row in rl.pass_variants(snap or {})}
    evaluated = sup_harvest._load_evaluated_or_queued(
        sup_paths.REGISTRY, sup_paths.QUEUE, rl.CURRENT_PROTOCOL_FINGERPRINT)
    seen_vids = set()
    ev = sup_evidence._load_evaluator()
    status_map = sup_evidence.load_symbol_status()
    archived = getattr(ev, "ARCHIVED_COVARIATES", {}) if ev else {}
    valid_covs = getattr(ev, "VALID_COVARIATES", None) if ev else None
    allowed_syms = getattr(ev, "ALLOWED_SYMBOLS", None) if ev else None
    sg_cache = {}
    dead_fams = sup_evidence._dead_families(snap or {})

    run_dirs = []
    for run_id in RUN_IDS:
        run_dir = os.path.join(root, "task_FM", "experiments", run_id)
        if os.path.isdir(run_dir):
            run_dirs.append(run_dir)
    run_dirs.sort(key=os.path.getmtime, reverse=True)

    files = []
    candidates = []
    family_dead_ok = True
    hypothesis_v1 = 0
    family_counts = {}
    not_in_pool = 0
    n_cache = {}
    proposal_json_excluding_prescreen = 0

    for run_dir in run_dirs:
        paths = glob.glob(
            os.path.join(run_dir, "results", "**", "proposals", "*.json"),
            recursive=True,
        )
        for sp in paths:
            if os.path.basename(sp).endswith(".prescreen.json"):
                continue
            proposal_json_excluding_prescreen += 1
            try:
                with open(sp, encoding="utf-8") as handle:
                    proposal = json.load(handle)
            except Exception:
                files.append({
                    "path": sp,
                    "kind": "reject",
                    "reason": "unparseable_json",
                    "pool_family": None,
                })
                continue
            pool_family, is_v1 = _v1_pool_family(proposal, pool)
            if is_v1:
                hypothesis_v1 += 1
                if pool_family is None:
                    not_in_pool += 1
                else:
                    family_counts[pool_family] = family_counts.get(pool_family, 0) + 1
            kind, reason, extra = sup_harvest.classify_loaded_proposal(
                proposal,
                proposal_path=sp,
                root=root,
                pool=pool,
                snapshot=snap,
                dead=dead,
                existing=existing,
                passing_ids=passing_ids,
                seen_vids=seen_vids,
                evaluated=evaluated,
                status_map=status_map,
                archived=archived,
                valid_covs=valid_covs,
                allowed_syms=allowed_syms,
                sg_cache=sg_cache,
                search_check=_search_check,
            )
            if reason == "family_dead" and extra["family"] not in dead_fams:
                family_dead_ok = False
            recorded_reason = reason
            if kind == "backlog":
                recorded_reason = "backlog"
            files.append({
                "path": sp,
                "kind": kind,
                "reason": recorded_reason,
                "pool_family": pool_family,
            })
            if kind != "ok":
                continue
            symbol = extra["symbol"]
            cov = extra["cov"]
            evaluated.add((symbol, cov, rl.canonical_mode(proposal)))
            seat_family = (
                (pool.get(cov, {}) or {}).get("family")
                or proposal.get("covariate_family")
                or "other"
            )
            repeat_counts = sup_harvest._cross_run_repeat_counts()
            score = sup_harvest._proposal_priority_score(
                proposal, cov, symbol, snap or {},
                status_map=status_map,
                repeat_counts=repeat_counts,
                proposal_path=sp,
            )
            candidates.append({
                "variant_id": extra["vid"],
                "symbol": symbol,
                "_family": seat_family,
                "_score": score,
                "_tier": _seat_tier(symbol, priority, n_cache),
            })

    selected = _select(candidates)
    selected_families = [row["_family"] for row in selected]
    ok_pool = {row["pool_family"] for row in files if row["kind"] == "ok"}
    selected_pool = set(selected_families)
    if (ok_pool & set(_TARGET_FAMILIES)) and not (selected_pool & set(_TARGET_FAMILIES)):
        decision = "reserve_last_seat"
    else:
        decision = "no_selection_change"
    family_counts = dict(family_counts)
    family_counts["not_in_pool"] = not_in_pool
    body = {
        "run_scope": "appendix_a_only",
        "failure_delta_rule": "length_only",
        "decision": decision,
        "dominant_reject_inventory_calendar": _dominant_reject(files),
        "proposal_json_excluding_prescreen": proposal_json_excluding_prescreen,
        "hypothesis_v1": hypothesis_v1,
        "family_counts": family_counts,
        "selected_families": selected_families,
        "files": files,
    }
    publish = family_dead_ok and (not expect_ledger or _ledger_matches(body))
    parent = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = output_path + ".partial"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        if not publish:
            os.remove(tmp)
            return 2
        os.replace(tmp, output_path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/home/abug/timesfm")
    parser.add_argument(
        "--output",
        default="/home/abug/timesfm/docs/superpowers/reports/2026-11-18-proposal-reject-replay.json",
    )
    parser.add_argument("--goal", default="/home/abug/timesfm/scripts/praxist_goal.yaml")
    args = parser.parse_args(argv)
    return replay(args.root, args.output, args.goal, expect_ledger=True)


if __name__ == "__main__":
    sys.exit(main())
