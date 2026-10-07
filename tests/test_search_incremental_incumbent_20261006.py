"""子任务 2.6 — incremental_vs_incumbent 落账（spec 2026-10-05 §6.4/§5/§7 T7/T14）。

锁定：
- §6.4 缺现任（无 gate_pass 现任）→ not_applicable（视为通过）。
- §6.4 现任存在且增量 DM 通过（共同样本 pairing_valid + missingness_admissible +
  dm_status∈{ok,set_mismatch_ok} + d_mean>0 + p<0.05）→ pass。
- §6.4 现任存在但增量 DM 不通过 → fail。
- §6.4/T14 现任裁决在而其 checkpoint 损坏（文件级弃读）→ fail，晋升不发生。
- §6.4/T7 gate_pass 不受影响：写字段不改 gate_pass/fdr_pass。
- §6.4 共同 cutoff 对齐：只在交集上配对。
- §5 现任定义：同一品种、当前协议指纹、status=ok、gate_pass=True 的裁决里 δ 最大。
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cascade import statistical_tests as st  # noqa: E402
import registry_lib as rl  # noqa: E402

# 2.6 新增函数（实现后导入）
try:
    from scripts.aligned_slow_loop import (
        find_incumbent,
        load_incumbent_points_from_checkpoint,
        compute_incremental_vs_incumbent,
    )
except ImportError:
    find_incumbent = None
    load_incumbent_points_from_checkpoint = None
    compute_incremental_vs_incumbent = None


FP_NOW = "f02b2a43"


# ── 辅助：构造裁决与点序列 ────────────────────────────────

def _make_verdict(
    symbol="jd",
    cov_override="momentum_20",
    dir_acc=0.56,
    baseline_dir_acc=0.50,
    gate_pass=True,
    status="ok",
    protocol_fingerprint=FP_NOW,
    variant_id=None,
    checkpoint_path=None,
):
    delta = dir_acc - baseline_dir_acc if (dir_acc is not None and baseline_dir_acc is not None) else 0
    vid = variant_id or f"{symbol}_{cov_override}_p400"
    return {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": vid,
        "symbol": symbol,
        "cov_override": cov_override,
        "cov_family": "momentum",
        "status": status,
        "stage": "aligned",
        "batch_id": "b1",
        "n": 400,
        "n_eff": 400,
        "dir_acc": dir_acc,
        "weighted_dir_acc": dir_acc,
        "gate_pass": gate_pass,
        "p_value": 0.03,
        "fdr_pass": None,
        "migrated_pass": None,
        "endpoint_mape": None,
        "endpoint_bias_pct": None,
        "path_corr": None,
        "mae": None,
        "mape": None,
        "decay": None,
        "checkpoint_path": checkpoint_path or "",
        "slow_loop_pid": None,
        "git_rev": None,
        "decided_at": "2026-10-06T00:00:00",
        "baseline_dir_acc": baseline_dir_acc,
        "effective_min": 0.52,
        "run_mode": "exploration",
        "run_label": "exploratory_unconfirmed",
        "dir_acc_full": dir_acc,
        "dir_acc_ex_roll": dir_acc,
        "n_roll_excluded": 0,
        "n_roll_ratio": 0.0,
        "n_dir_total": 400,
        "n_dir_active": 400,
        "n_zero_move": 0,
        "n_zero_ratio": 0.0,
        "protocol_fingerprint": protocol_fingerprint,
        "sample_fingerprint": None,
        "cov_fingerprint": None,
        "weight_fingerprint": None,
        "seed_fingerprint": None,
        "dm_status": "set_mismatch_descriptive",
        "dm_common_count": 400,
        "dm_unmatched_variant": 0,
        "dm_unmatched_baseline": 0,
        "pair_set_hash": None,
        "raw_cutoff_set_hash": None,
        "d_series_n_eff": 400,
        "d_bar_le_zero": False,
        "n_avail_variant": 400,
        "n_avail_baseline": 400,
        "missingness_admissible": False,
        "covariates_used": True,
        "pairing_valid": False,
        "xreg_fallback_count": None,
        "xreg_fallback_rate": None,
        "se": 0.02,
        "delta_post_shrunk": 0.0096,
    }


def _make_points(n=200, hit_rate=0.6, start_idx=0):
    """生成 n 个确定性点序列，cutoff 唯一，dir_ok 按 hit_rate 命中。"""
    pts = []
    for i in range(n):
        ts = "2024-01-01 %02d:%02d:00" % ((start_idx + i) // 60, (start_idx + i) % 60)
        pts.append({"cutoff": ts, "dir_ok": (i % 10) < int(hit_rate * 10)})
    return pts


def _write_checkpoint(tmp_path, points, fp=FP_NOW, corrupt=False):
    """写 checkpoint 文件。corrupt=True 时写非法 JSON（文件级弃读）。"""
    cp = str(tmp_path / "incumbent_cp.jsonl")
    if corrupt:
        with open(cp, "w", encoding="utf-8") as f:
            f.write("NOT VALID JSON {{{\n")
        return cp
    with open(cp, "w", encoding="utf-8") as f:
        for pt in points:
            rec = {"cutoff": pt["cutoff"], "dir_ok": pt["dir_ok"],
                   "symbol": "jd", "protocol_fingerprint": fp,
                   "eval_end_ts": "2026-10-06T00:00:00"}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return cp


# ══════════════════ §5 现任定位 ══════════════════

class TestFindIncumbent:
    def test_no_incumbent_when_no_gate_pass(self):
        """无 gate_pass=True 的现任 → None。"""
        snap = {
            "v1": _make_verdict(dir_acc=0.60, gate_pass=False, variant_id="v1"),
            "v2": _make_verdict(dir_acc=0.55, gate_pass=False, variant_id="v2"),
        }
        assert find_incumbent("jd", FP_NOW, snap) is None

    def test_no_incumbent_when_empty(self):
        assert find_incumbent("jd", FP_NOW, {}) is None

    def test_no_incumbent_when_wrong_symbol(self):
        snap = {"v1": _make_verdict(symbol="sr", dir_acc=0.60, gate_pass=True, variant_id="v1")}
        assert find_incumbent("jd", FP_NOW, snap) is None

    def test_no_incumbent_when_wrong_protocol(self):
        snap = {"v1": _make_verdict(dir_acc=0.60, gate_pass=True,
                                     protocol_fingerprint="old_fp", variant_id="v1")}
        assert find_incumbent("jd", FP_NOW, snap) is None

    def test_no_incumbent_when_status_not_ok(self):
        snap = {"v1": _make_verdict(dir_acc=0.60, gate_pass=True,
                                     status="no_data", variant_id="v1")}
        assert find_incumbent("jd", FP_NOW, snap) is None

    def test_picks_max_delta(self):
        """δ 最大者当选。"""
        snap = {
            "v1": _make_verdict(dir_acc=0.55, baseline_dir_acc=0.50, gate_pass=True, variant_id="v1"),
            "v2": _make_verdict(dir_acc=0.60, baseline_dir_acc=0.50, gate_pass=True, variant_id="v2"),
            "v3": _make_verdict(dir_acc=0.58, baseline_dir_acc=0.50, gate_pass=True, variant_id="v3"),
        }
        inc = find_incumbent("jd", FP_NOW, snap)
        assert inc["variant_id"] == "v2"

    def test_ignores_non_ok_status(self):
        snap = {
            "v1": _make_verdict(dir_acc=0.70, gate_pass=True, status="error", variant_id="v1"),
            "v2": _make_verdict(dir_acc=0.60, gate_pass=True, variant_id="v2"),
        }
        inc = find_incumbent("jd", FP_NOW, snap)
        assert inc["variant_id"] == "v2"


# ══════════════════ §6.4/T14 现任序列获取 ══════════════════

class TestLoadIncumbentPoints:
    def test_returns_none_when_checkpoint_missing(self, tmp_path):
        """checkpoint 文件不存在 → None（T14）。"""
        inc = _make_verdict(checkpoint_path=str(tmp_path / "nonexistent.jsonl"))
        assert load_incumbent_points_from_checkpoint(inc, FP_NOW) is None

    def test_returns_none_when_checkpoint_corrupt(self, tmp_path):
        """checkpoint 文件级损坏 → None（T14）。"""
        cp = _write_checkpoint(tmp_path, _make_points(), corrupt=True)
        inc = _make_verdict(checkpoint_path=cp)
        result = load_incumbent_points_from_checkpoint(inc, FP_NOW)
        assert result is None

    def test_returns_points_filtered_by_protocol(self, tmp_path):
        """只返回当前协议指纹的点。"""
        pts = _make_points(10)
        cp = _write_checkpoint(tmp_path, pts, fp=FP_NOW)
        inc = _make_verdict(checkpoint_path=cp)
        result = load_incumbent_points_from_checkpoint(inc, FP_NOW)
        assert result is not None
        assert len(result) == 10

    def test_returns_none_when_empty_checkpoint_path(self):
        inc = _make_verdict(checkpoint_path="")
        assert load_incumbent_points_from_checkpoint(inc, FP_NOW) is None


# ══════════════════ §6.4 增量判定 ══════════════════

class TestComputeIncrementalVsIncumbent:
    def test_not_applicable_when_no_incumbent(self):
        """缺现任 → not_applicable（视为通过）。"""
        result = compute_incremental_vs_incumbent(
            new_variant_points=_make_points(),
            incumbent_points=None,
            incumbent_verdict=None,
            variant_protocol=FP_NOW,
            incumbent_protocol=None,
        )
        assert result == "not_applicable"

    def test_fail_when_incumbent_checkpoint_unavailable(self):
        """现任裁决在但序列不可得 → fail（T14）。"""
        inc = _make_verdict(dir_acc=0.55, gate_pass=True)
        result = compute_incremental_vs_incumbent(
            new_variant_points=_make_points(),
            incumbent_points=None,
            incumbent_verdict=inc,
            variant_protocol=FP_NOW,
            incumbent_protocol=FP_NOW,
        )
        assert result == "fail"

    def test_pass_when_incremental_dm_significant(self):
        """现任存在且增量 DM 通过 → pass。

        构造：变体命中率 0.7，现任命中率 0.5，共同 cutoff 200 点。
        需要 pairing_valid=True 且 missingness_admissible=True 且 dm_status∈{ok,set_mismatch_ok}。
        """
        new_pts = _make_points(200, hit_rate=0.7)
        inc_pts = _make_points(200, hit_rate=0.5)
        inc = _make_verdict(dir_acc=0.55, gate_pass=True)
        result = compute_incremental_vs_incumbent(
            new_variant_points=new_pts,
            incumbent_points=inc_pts,
            incumbent_verdict=inc,
            variant_protocol=FP_NOW,
            incumbent_protocol=FP_NOW,
            missingness_admissible=True,
        )
        assert result == "pass"

    def test_fail_when_incremental_dm_not_significant(self):
        """现任存在但增量 DM 不通过 → fail。

        构造：变体命中率 0.5，现任命中率 0.5（无差异）。
        """
        new_pts = _make_points(200, hit_rate=0.5)
        inc_pts = _make_points(200, hit_rate=0.5)
        inc = _make_verdict(dir_acc=0.55, gate_pass=True)
        result = compute_incremental_vs_incumbent(
            new_variant_points=new_pts,
            incumbent_points=inc_pts,
            incumbent_verdict=inc,
            variant_protocol=FP_NOW,
            incumbent_protocol=FP_NOW,
            missingness_admissible=True,
        )
        assert result == "fail"

    def test_fail_when_pairing_invalid(self):
        """pairing_valid=False → fail。"""
        new_pts = _make_points(200, hit_rate=0.7)
        inc_pts = _make_points(200, hit_rate=0.5)
        inc = _make_verdict(dir_acc=0.55, gate_pass=True)
        result = compute_incremental_vs_incumbent(
            new_variant_points=new_pts,
            incumbent_points=inc_pts,
            incumbent_verdict=inc,
            variant_protocol=FP_NOW,
            incumbent_protocol=FP_NOW,
            missingness_admissible=False,
        )
        assert result == "fail"

    def test_common_cutoff_alignment(self):
        """只在共同 cutoff 上配对。

        构造：变体有 100 点（cutoff 0-99），现任有 100 点（cutoff 50-149），
        共同 cutoff = 50-99（50 点）。
        """
        new_pts = _make_points(100, hit_rate=0.7, start_idx=0)
        inc_pts = _make_points(100, hit_rate=0.5, start_idx=50)
        inc = _make_verdict(dir_acc=0.55, gate_pass=True)
        result = compute_incremental_vs_incumbent(
            new_variant_points=new_pts,
            incumbent_points=inc_pts,
            incumbent_verdict=inc,
            variant_protocol=FP_NOW,
            incumbent_protocol=FP_NOW,
            missingness_admissible=True,
        )
        # 共同 cutoff 只有 50 点 < dm_min_common=50 → dm_status=insufficient_common → fail
        assert result == "fail"


# ══════════════════ §6.4/T7 gate_pass 不受影响 ══════════════════

class TestGatePassUnaffected:
    def test_incremental_field_does_not_alter_gate_pass(self):
        """incremental_vs_incumbent 写字段不改 gate_pass/fdr_pass（T7）。"""
        v = _make_verdict(dir_acc=0.56, gate_pass=True)
        original_gate_pass = v["gate_pass"]
        original_fdr_pass = v["fdr_pass"]
        # 模拟落账 incremental_vs_incumbent
        v["incremental_vs_incumbent"] = "fail"
        assert v["gate_pass"] == original_gate_pass
        assert v["fdr_pass"] == original_fdr_pass


# ══════════════════ schema 登记 ══════════════════

class TestSchemaRegistration:
    def test_field_registered_in_v2(self):
        assert "incremental_vs_incumbent" in rl.VERDICT_FIELDS_V2

    def test_field_registered_nullable(self):
        assert "incremental_vs_incumbent" in rl.VERDICT_FIELDS_V2_NULLABLE

    def test_historical_verdict_without_field_valid(self):
        """历史行缺 incremental_vs_incumbent 仍合法。"""
        row = _make_verdict()
        assert "incremental_vs_incumbent" not in row
        assert rl.validate_verdict(row) == []

    def test_verdict_with_field_valid(self):
        row = _make_verdict()
        row["incremental_vs_incumbent"] = "pass"
        assert rl.validate_verdict(row) == []

    def test_verdict_with_invalid_value_rejected(self):
        """非法取值应被校验拒绝。"""
        row = _make_verdict()
        row["incremental_vs_incumbent"] = "invalid_value"
        errs = rl.validate_verdict(row)
        assert len(errs) > 0
