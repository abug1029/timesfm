"""Task 15: prediction quality end-to-end fixture tests (no real model runs).

Chains, all IO inside tmp dirs:
1. baseline JSONL -> build_summary (DM test) -> registry append ->
   bh_fdr_promote + update_batch_verdicts -> build_snapshot scalars
2. crash tombstone + FDR collection (first-write-wins dedup, safe_p=1.0)
3. build_snapshot -> evaluate_goal combo (real production praxist_goal.yaml)
4. v1->v2 migration (migrate_verdicts_v1_to_v2.main) output into registry

Loading patterns mirror existing tests:
- evaluator: importlib (task_FM is not a package), like test_praxist_fm_evaluator.py
- supervisor/registry_lib/goal_dsl: scripts dir on sys.path, like test_supervisor.py
- migrate: importlib, like test_migrate_verdicts_v1_to_v2.py
  (note: module has no top-level `migrate` function; full entry point is main(argv))
"""
import copy
import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
for _p in (SCRIPTS, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import praxist_supervisor as sup  # noqa: E402
import registry_lib as rl  # noqa: E402

# evaluator (task_FM is not a package)
_EVAL_SPEC = importlib.util.spec_from_file_location(
    "fm_evaluator_e2e",
    os.path.join(REPO_ROOT, "task_FM", "evaluations", "fm_eval", "evaluator.py"))
fm = importlib.util.module_from_spec(_EVAL_SPEC)
_EVAL_SPEC.loader.exec_module(fm)

# migrate (Task 14)
_MIG_SPEC = importlib.util.spec_from_file_location(
    "migrate_verdicts_v1_to_v2_e2e",
    os.path.join(SCRIPTS, "migrate_verdicts_v1_to_v2.py"))
mig = importlib.util.module_from_spec(_MIG_SPEC)
_MIG_SPEC.loader.exec_module(mig)

from cascade.statistical_tests import bh_fdr_promote  # noqa: E402
from cascade.cov_family import ALLOWED_FAMILIES  # noqa: E402

GOAL_YAML = os.path.join(SCRIPTS, "praxist_goal.yaml")
START = 1_700_000_000  # unix seconds (< 1e11, safe_normalize_cutoff treats as seconds)
STEP = 3600


# ---- fixtures / helpers ----

def _write_baseline(root, symbol="m", n=120):
    """120-point baseline JSONL, dir_ok ratio 0.55 (i%20<11 -> 66/120)."""
    path = os.path.join(root, f"baseline_points_{symbol}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"cutoff": START + i * STEP,
                                "dir_ok": (i % 20) < 11}) + "\n")
    return path


def _summarize(dir_acc=0.56, point_dir_ok_list=None):
    """Fake summarize output (v23 keys, mirrors test_praxist_fm_evaluator fixture)."""
    s = {"n": 400, "n_eff": 400, "dir_acc": dir_acc,
         "endpoint_mape": 0.4, "endpoint_bias_pct": 0.1,
         "path_corr": 0.7, "weighted_dir_acc": 0.57,
         "mae": 1.0, "mape": 0.4, "decay": 1.1}
    if point_dir_ok_list is not None:
        s["point_dir_ok_list"] = point_dir_ok_list
    return s


def _cand(symbol="m", cov="rsi_state"):
    return {"symbol": symbol, "cov_override": cov,
            "max_points": 400, "stage": "aligned"}


def _summary_to_registry_row(summary, vid, **kw):
    """Glue: add registry-required fields onto a build_summary output.

    Only adds transport fields (variant_id/checkpoint_path/slow_loop_pid/
    git_rev/decided_at); never touches metric definitions.
    """
    row = copy.deepcopy(summary)
    row.update({"variant_id": vid, "checkpoint_path": None,
                "slow_loop_pid": None, "git_rev": None,
                "decided_at": "2026-09-16T00:00:00"})
    row.update(kw)
    return row


def _v2_row(vid, bid, *, symbol="m", cov="rsi_state", cov_family="momentum",
            dir_acc=0.56, gate_pass=True, p_value=0.01, fdr_pass=None,
            migrated_pass=None, status="ok"):
    """Complete v2 verdict (mirrors test_verdict_registry._v2_complete)."""
    return {
        "schema": "fm.aligned_verdict.v2", "variant_id": vid,
        "symbol": symbol, "cov_override": cov, "cov_family": cov_family,
        "status": status, "stage": "aligned", "batch_id": bid,
        "n": 400, "n_eff": 400, "dir_acc": dir_acc,
        "weighted_dir_acc": dir_acc + 0.01, "gate_pass": gate_pass,
        "p_value": p_value, "fdr_pass": fdr_pass,
        "migrated_pass": migrated_pass, "endpoint_mape": None,
        "endpoint_bias_pct": None, "path_corr": None, "mae": None,
        "mape": None, "decay": None, "checkpoint_path": None,
        "slow_loop_pid": None, "git_rev": None,
        "decided_at": "2026-09-16T00:00:00",
    }


def _v1_row(**kw):
    """v1 verdict fixture (mirrors test_migrate_verdicts_v1_to_v2)."""
    row = {"schema": "fm.aligned_verdict.v1", "variant_id": "m_rsi_state",
           "symbol": "m", "cov_override": "rsi_state", "stage": "aligned",
           "n": 400, "dir_acc": 0.56, "gate_pass": True,
           "decided_at": "2026-09-14T09:45:01", "git_rev": "abc123",
           "slow_loop_pid": 1}
    row.update(kw)
    return row


def _cp_rows():
    """4 checkpoint points (mirrors test_migrate_verdicts_v1_to_v2 fixture)."""
    return [
        {"cutoff": "2025-12-22", "base": 1000.0, "pred_end": 1010.0,
         "real_end": 1020.0, "delta_pred": 10.0, "delta_real": 20.0},
        {"cutoff": "2025-12-23", "base": 1000.0, "pred_end": 990.0,
         "real_end": 970.0, "delta_pred": -10.0, "delta_real": -30.0},
        {"cutoff": "2025-12-24", "base": 1000.0, "pred_end": 1010.0,
         "real_end": 980.0, "delta_pred": 10.0, "delta_real": -20.0},
        {"cutoff": "2025-12-25", "base": 1000.0, "pred_end": 990.0,
         "real_end": 1020.0, "delta_pred": -10.0, "delta_real": 20.0},
    ]


# ---- Test 1: main chain baseline -> DM -> registry -> FDR -> snapshot ----

def test_e2e_main_chain(tmp_path):
    symbol = "m"
    _write_baseline(str(tmp_path), symbol)
    # baseline loaded through the real evaluator loader
    baseline_points = fm.load_baseline_points(symbol, root=str(tmp_path))
    assert len(baseline_points) == 120

    # fake summarize: point_dir_ok_list partially overlaps baseline
    # (120 points, cutoffs 20..139 -> 100 paired with baseline 0..119)
    variant_pts = [{"cutoff": START + (20 + idx) * STEP,
                    "dir_ok": (idx % 4) < 3} for idx in range(120)]
    batch_id = "batch_e2e_1"
    verdict = fm.build_summary(_summarize(point_dir_ok_list=variant_pts),
                               _cand(symbol), baseline_points=baseline_points,
                               baseline_dir_acc=0.55, batch_id=batch_id)
    assert verdict["schema"] == "fm.aligned_verdict.v2"
    # 100 paired (boundary) -> DM runs, p_value not None and in [0, 1]
    assert verdict["p_value"] is not None
    assert 0.0 <= verdict["p_value"] <= 1.0
    # n=400, n_eff=400, dir_acc=0.56 >= 0.52, aligned stage
    assert verdict["gate_pass"] is True
    assert "point_dir_ok_list" not in verdict

    # 4 v2 verdicts, same symbol and batch, distinct dir_acc,
    # >= 1 gate_pass=True; passing row p fixed to 0.01 so the FDR
    # outcome is deterministic
    rows = [
        _summary_to_registry_row(verdict, "m_rsi_state", dir_acc=0.56,
                                 gate_pass=True, p_value=0.01),
        _summary_to_registry_row(verdict, "m_ha_body", dir_acc=0.51,
                                 gate_pass=False, p_value=0.04),
        _summary_to_registry_row(verdict, "m_ccl", dir_acc=0.49,
                                 gate_pass=False, p_value=0.05),
        _summary_to_registry_row(verdict, "m_oi", dir_acc=0.44,
                                 gate_pass=False, p_value=0.90),
    ]
    reg = str(tmp_path / "verdicts.jsonl")
    for r in rows:
        rl.append_verdict(reg, r)  # path-based append: validate + lock + fsync
    assert len(rl.read_verdicts(reg)) == 4

    batch_verdicts = [v for v in rl.read_verdicts(reg)
                      if v.get("batch_id") == batch_id]
    updates = bh_fdr_promote(batch_verdicts)
    # K=4 BH: gate_fail rows get safe_p=1.0 -> never pass regardless of raw p
    # (only m_rsi_state p=0.01<=0.025 passes); genuine multi-p step-up ladder
    # is covered by test_e2e_tombstone_and_fdr_collection
    assert updates == {"m_rsi_state": {"fdr_pass": True},
                       "m_ha_body": {"fdr_pass": False},
                       "m_ccl": {"fdr_pass": False},
                       "m_oi": {"fdr_pass": False}}
    rl.update_batch_verdicts(reg, batch_id, updates)

    snap = rl.load_snapshot(reg)
    passing = {v["variant_id"] for v in rl.pass_variants(snap)}
    assert passing == {"m_rsi_state"}  # gate_pass AND fdr_pass

    full = sup.build_snapshot(reg, 3, 1.5, 2.7)
    assert full["n_one_star_symbols_hit"] == 1   # m is in the 1-star set
    assert full["n_unique_pass_variants"] == 1
    assert full["n_families_hit"] == 1           # momentum in ALLOWED_FAMILIES
    assert full["min_pass_variant_dir_acc"] == 0.56


def test_e2e_pairing_below_100_pairs(tmp_path):
    """Fewer than 100 paired points -> p_value=None (matches existing unit tests)."""
    symbol = "m"
    _write_baseline(str(tmp_path), symbol)
    baseline_points = fm.load_baseline_points(symbol, root=str(tmp_path))
    # variant has 120 points but cutoffs shifted to 100..219 -> only 20 overlap
    variant_pts = [{"cutoff": START + (100 + idx) * STEP,
                    "dir_ok": (idx % 4) < 3} for idx in range(120)]
    verdict = fm.build_summary(_summarize(point_dir_ok_list=variant_pts),
                               _cand(symbol), baseline_points=baseline_points,
                               baseline_dir_acc=0.55, batch_id="batch_short")
    assert verdict["p_value"] is None


# ---- Test 2: crash tombstone + FDR collection ----

def test_e2e_tombstone_and_fdr_collection(tmp_path):
    reg = str(tmp_path / "verdicts.jsonl")
    bid = "batch_tomb"
    # 1) tombstone (status=error) written first for the batch
    tomb = rl.make_error_tombstone("m", "m_oi", bid, RuntimeError("boom"))
    rl.append_verdict(reg, tomb)
    # 2) successful verdict with same batch_id+variant_id -> dedup rejects
    #    (first write wins)
    late_ok = _v2_row("m_oi", bid, gate_pass=True, p_value=0.01)
    rl.append_verdict(reg, late_ok)
    recs = rl.read_verdicts(reg)
    assert len(recs) == 1
    assert recs[0]["status"] == "error" and recs[0]["variant_id"] == "m_oi"

    # 3 successful verdicts (distinct p values, all gate_pass=True)
    for vid, p in (("m_rsi_state", 0.01), ("m_ccl", 0.02), ("m_ha_body", 0.03)):
        rl.append_verdict(reg, _v2_row(vid, bid, p_value=p))

    batch_verdicts = [v for v in rl.read_verdicts(reg)
                      if v.get("batch_id") == bid]
    assert len(batch_verdicts) == 4  # 1 tombstone + 3 ok
    updates = bh_fdr_promote(batch_verdicts)
    # tombstone gate_pass=False -> safe_p=1.0 sorts last, other 3 pass BH
    assert updates == {"m_rsi_state": {"fdr_pass": True},
                       "m_ccl": {"fdr_pass": True},
                       "m_ha_body": {"fdr_pass": True},
                       "m_oi": {"fdr_pass": False}}
    rl.update_batch_verdicts(reg, bid, updates)

    by_vid = {r["variant_id"]: r for r in rl.read_verdicts(reg)}
    for vid in ("m_rsi_state", "m_ccl", "m_ha_body"):
        assert by_vid[vid]["fdr_pass"] is True
    assert by_vid["m_oi"]["status"] == "error"
    assert by_vid["m_oi"]["fdr_pass"] is False

    passing = {v["variant_id"] for v in rl.pass_variants(rl.load_snapshot(reg))}
    assert passing == {"m_rsi_state", "m_ccl", "m_ha_body"}  # tombstone filtered


# ---- Test 3: build_snapshot -> evaluate_goal combo (production goal yaml) ----

def test_e2e_snapshot_goal_combo(tmp_path):
    goal = sup.load_goal(GOAL_YAML)
    conds = goal["success_condition"]
    cond_min_da = next(c for c in conds if "min_pass_variant_dir_acc" in c)
    assert "is not None" in cond_min_da  # guard still present in production condition

    reg = str(tmp_path / "verdicts.jsonl")
    bid = "batch_goal"
    rl.append_verdict(reg, _v2_row("ss_vor", bid, symbol="ss",
                                   dir_acc=0.56, gate_pass=True, p_value=0.01))
    rl.append_verdict(reg, _v2_row("ss_bad", bid, symbol="ss",
                                   dir_acc=0.40, gate_pass=False, p_value=1.0))
    # K=2 < min_batch_size=4 -> Bonferroni (0.025): 0.01 passes,
    # failing row has gate_pass=False so it never passes
    updates = bh_fdr_promote(rl.read_verdicts(reg))
    assert updates == {"ss_vor": {"fdr_pass": True}, "ss_bad": {"fdr_pass": False}}
    rl.update_batch_verdicts(reg, bid, updates)

    snap = sup.build_snapshot(reg, 1, 0.5, 1.0)
    assert snap["min_pass_variant_dir_acc"] == 0.56
    assert snap["n_one_star_symbols_hit"] == 1  # ss is in the 1-star set
    assert snap["n_unique_pass_variants"] == 1
    assert snap["n_families_hit"] == 1

    ok, reasons = sup.evaluate_goal([cond_min_da], snap)
    assert ok is True and reasons == []  # 0.56 > 0.52 and not None

    ok_all, _ = sup.evaluate_goal(conds, snap)
    assert ok_all is False  # n_one_star_symbols_hit=1 < 4, overall goal unmet

    # no passing record: min_pass_variant_dir_acc=None -> condition unmet,
    # not an eval error
    reg2 = str(tmp_path / "verdicts2.jsonl")
    rl.append_verdict(reg2, _v2_row("ss_bad2", "b2", symbol="ss",
                                    dir_acc=0.40, gate_pass=False, p_value=1.0))
    snap2 = sup.build_snapshot(reg2, 0, 0.0, 0.0)
    assert snap2["min_pass_variant_dir_acc"] is None
    ok2, reasons2 = sup.evaluate_goal([cond_min_da], snap2)
    assert ok2 is False
    assert len(reasons2) == 1 and "eval error" not in reasons2[0]
    assert "unmet" in reasons2[0]


# ---- Test 4: migration smoke - migrate output goes straight into registry ----

def test_e2e_migrate_output_into_registry(tmp_path):
    cp = str(tmp_path / "cp.jsonl")
    with open(cp, "w", encoding="utf-8") as f:
        for row in _cp_rows():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    src = str(tmp_path / "v1.jsonl")
    dst = str(tmp_path / "v2.jsonl")
    with open(src, "w", encoding="utf-8") as f:
        f.write(json.dumps(_v1_row(checkpoint_path=cp), ensure_ascii=False) + "\n")

    # migrate entry point is main(argv) (module has no top-level migrate function)
    assert mig.main(["--src", src, "--dst", dst]) == 0
    rows = [json.loads(l) for l in open(dst, encoding="utf-8") if l.strip()]
    assert len(rows) == 1
    out = rows[0]
    assert out["status"] == "ok"
    assert out["schema"] == "fm.aligned_verdict.v2"
    assert out["gate_pass"] is True and out["migrated_pass"] is True
    assert out["cov_family"] == "momentum"
    assert rl.validate_verdict(out) == []  # zero v2 validation errors

    # straight into tmp registry + pass_variants can read it
    reg = str(tmp_path / "verdicts.jsonl")
    rl.append_verdict(reg, out)
    passing = rl.pass_variants(rl.load_snapshot(reg))
    assert [v["variant_id"] for v in passing] == ["m_rsi_state"]
    assert passing[0]["migrated_pass"] is True
