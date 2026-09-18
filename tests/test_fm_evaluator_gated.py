"""评估器 gated 协变量通用支持测试 (TDD 2026-09-18, spec §5 Active DirAcc)

覆盖: active_mask_metrics 分类与 fail-closed、build_summary active 口径落库与硬门挂
n_active、run.py 接线、_point_signal cutoff 信号捕获、pool "gated" 挂点读取、零漂移。
零漂移约束: 本文件不修改任何既有测试文件。
"""
import importlib.util
import json
import math
import os
import sys

import pytest

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "fm_evaluator",
    os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval", "evaluator.py"))
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)

sys.path.insert(0, os.path.join(FM_ROOT, "scripts"))


def _s_v23(n=600, n_eff=400, dir_acc=0.56):
    return {
        "n": n, "n_eff": n_eff, "dir_acc": dir_acc,
        "endpoint_mape": 0.4, "endpoint_bias_pct": 0.1,
        "path_corr": 0.7, "weighted_dir_acc": 0.57,
        "mae": 1.0, "mape": 0.4, "decay": 1.1,
    }


def _cand(cov="rsi_state", stage="aligned", mp=400):
    return {"symbol": "m", "cov_override": cov, "max_points": mp, "stage": stage}


# ======================================================
# active_mask_metrics
# ======================================================

class TestActiveMaskMetrics:

    def test_mixed_classification(self):
        pts = [
            {"signal": 1.5, "dir_ok": True},    # active ok
            {"signal": 1.5, "dir_ok": False},   # active wrong
            {"signal": -2.0, "dir_ok": True},   # 负信号也是激活 (只按 != 0)
            {"signal": 0.0, "dir_ok": True},    # zero
            {"signal": -0.0, "dir_ok": True},   # -0.0 == 0.0 → zero
            {"signal": float("nan"), "dir_ok": True},  # nan
            {"signal": None, "dir_ok": True},   # None → nan
            {"signal": "abc", "dir_ok": True},  # 非数值 → nan
            {"signal": 2.0},                    # dir_ok 缺失 → 目标不可评 → nan
            {"signal": 3.0, "dir_ok": True},
        ]
        gm = fm.active_mask_metrics(pts)
        assert gm["n_total"] == 10
        assert gm["n_active"] == 4
        # active 样本 dir_ok: T, F, T, T → 3/4
        assert gm["active_dir_acc"] == 0.75
        assert gm["n_zero"] == 2
        assert gm["n_nan"] == 4
        # 分区不变量: n_active + n_zero + n_nan == n_total
        assert gm["n_active"] + gm["n_zero"] + gm["n_nan"] == gm["n_total"]

    def test_n_active_zero_returns_nan_no_exception(self):
        pts = [{"signal": 0.0, "dir_ok": True},
               {"signal": 0.0, "dir_ok": False}]
        gm = fm.active_mask_metrics(pts)
        assert gm["n_active"] == 0
        assert gm["n_zero"] == 2
        assert math.isnan(gm["active_dir_acc"])  # fail-closed, 绝不 ZeroDivisionError

    def test_empty_points_all_zero(self):
        gm = fm.active_mask_metrics([])
        assert gm["n_total"] == 0
        assert gm["n_active"] == 0
        assert gm["n_zero"] == 0
        assert gm["n_nan"] == 0
        assert math.isnan(gm["active_dir_acc"])

    def test_error_points_excluded(self):
        pts = [
            {"signal": 1.0, "dir_ok": True},
            {"cutoff": "2024-01-01 09:00:00", "error": "boom"},
            {"signal": 0.0, "dir_ok": True},
        ]
        gm = fm.active_mask_metrics(pts)
        assert gm["n_total"] == 2
        assert gm["n_active"] == 1
        assert gm["n_zero"] == 1

    def test_no_signal_key_all_nan_bucket(self):
        """改造前 resume checkpoint 点无 signal 键 → 全部按标尺失效计数, 不崩."""
        pts = [{"dir_ok": True}, {"dir_ok": False}]
        gm = fm.active_mask_metrics(pts)
        assert gm["n_total"] == 2
        assert gm["n_nan"] == 2
        assert gm["n_active"] == 0

    def test_counts_partition_invariant_property(self):
        pts = []
        for i in range(30):
            r = i % 5
            sig = {0: 1.0, 1: 0.0, 2: float("nan"), 3: -1.0, 4: None}[r]
            pt = {"signal": sig, "dir_ok": (i % 2 == 0)}
            pts.append(pt)
        gm = fm.active_mask_metrics(pts)
        assert gm["n_active"] + gm["n_zero"] + gm["n_nan"] == gm["n_total"] == 30
        assert gm["n_active"] == 12  # r=0 和 r=3 → 6+6
        assert gm["n_zero"] == 6
        assert gm["n_nan"] == 12     # nan 6 + None 6


# ======================================================
# build_summary gated 消费
# ======================================================

class TestGatedBuildSummary:

    def test_gated_fields_landed(self):
        s = _s_v23(n=600)
        s["gated_metrics"] = {"active_dir_acc": 0.60, "n_active": 380,
                              "n_total": 600, "n_zero": 200, "n_nan": 20}
        out = fm.build_summary(s, _cand())
        assert out["active_dir_acc"] == 0.60
        assert out["n_active"] == 380
        assert out["n_total"] == 600
        assert out["n_zero"] == 200
        assert out["n_nan"] == 20
        assert out["gate_basis"] == "active"
        for k in ("active_dir_acc", "n_active", "n_total", "n_zero", "n_nan"):
            assert k in out["metrics"]
        assert "gated_metrics" not in out
        # n_active=380>=350, n_eff_active=min(400,380)=380>=50, 0.60>=0.52 → 过门
        assert out["gate_pass"] is True

    def test_gate_uses_n_active_not_n_total(self):
        # 全量口径会过门 (n=600, dir_acc=0.56), 但 n_active=300<350 → 拒
        s = _s_v23(n=600)
        s["gated_metrics"] = {"active_dir_acc": 0.60, "n_active": 300,
                              "n_total": 600, "n_zero": 280, "n_nan": 20}
        out = fm.build_summary(s, _cand())
        assert out["gate_pass"] is False

    def test_gate_active_can_pass_when_full_fails(self):
        # 全量 dir_acc=0.40 会拒, 但 active 口径 0.53 + n_active=380 → 过
        s = _s_v23(n=600, dir_acc=0.40)
        s["gated_metrics"] = {"active_dir_acc": 0.53, "n_active": 380,
                              "n_total": 600, "n_zero": 200, "n_nan": 20}
        out = fm.build_summary(s, _cand())
        assert out["gate_pass"] is True

    def test_nan_active_dir_acc_fail_closed(self):
        s = _s_v23(n=600)
        s["gated_metrics"] = {"active_dir_acc": float("nan"), "n_active": 0,
                              "n_total": 600, "n_zero": 600, "n_nan": 0}
        out = fm.build_summary(s, _cand())
        assert math.isnan(out["active_dir_acc"])
        assert out["gate_pass"] is False  # NaN → gate fail-closed, 无异常

    def test_missing_active_dir_acc_fail_closed(self):
        s = _s_v23(n=600)
        s["gated_metrics"] = {"n_active": 380, "n_total": 600,
                              "n_zero": 200, "n_nan": 20}
        out = fm.build_summary(s, _cand())
        assert out["active_dir_acc"] is None
        assert out["gate_pass"] is False  # dir_acc=None → gate False

    def test_gated_diagnostic_stage_gate_false(self):
        s = _s_v23(n=6, n_eff=6, dir_acc=0.9)
        s["gated_metrics"] = {"active_dir_acc": 0.9, "n_active": 6,
                              "n_total": 6, "n_zero": 0, "n_nan": 0}
        out = fm.build_summary(s, _cand(stage="diagnostic", mp=6))
        assert out["gate_pass"] is False
        assert out["active_dir_acc"] == 0.9
        assert out["n_active"] == 6

    def test_gated_adaptive_baseline_floor(self):
        gm = {"active_dir_acc": 0.505, "n_active": 380,
              "n_total": 600, "n_zero": 200, "n_nan": 20}
        # baseline 0.50 → 自适应地板 max(0.50, min(0.52, 0.50)) = 0.50 → 0.505 过
        s1 = _s_v23(n=600)
        s1["gated_metrics"] = dict(gm)
        out1 = fm.build_summary(s1, _cand(), baseline_dir_acc=0.50)
        assert out1["gate_pass"] is True
        # baseline 0.55 → 自适应地板 0.52 → 0.505 拒 (fresh dict: gated_metrics 被 pop)
        s2 = _s_v23(n=600)
        s2["gated_metrics"] = dict(gm)
        out2 = fm.build_summary(s2, _cand(), baseline_dir_acc=0.55)
        assert out2["gate_pass"] is False

    def test_non_gated_output_has_no_active_keys(self):
        """零漂移: 非 gated 输出不含 active_* / gate_basis 键."""
        out = fm.build_summary(_s_v23(n=400), _cand())
        for k in ("active_dir_acc", "n_active", "n_total", "n_zero",
                  "n_nan", "gate_basis"):
            assert k not in out
            assert k not in out["metrics"]

    def test_gated_metrics_key_popped(self):
        s = _s_v23(n=600)
        s["gated_metrics"] = {"active_dir_acc": 0.60, "n_active": 380,
                              "n_total": 600, "n_zero": 200, "n_nan": 20}
        fm.build_summary(s, _cand())
        assert "gated_metrics" not in s


# ======================================================
# run.py do_evaluate 接线
# ======================================================

class TestRunWiring:

    def _load_run(self, name):
        fm_eval = os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval")
        sys.path.insert(0, os.path.join(FM_ROOT, "scripts"))
        sys.path.insert(0, fm_eval)
        run_path = os.path.join(fm_eval, "run.py")
        spec = importlib.util.spec_from_file_location(name, run_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_do_evaluate_gated_injects_metrics(self, monkeypatch):
        import monthly_backtest as mb
        monkeypatch.setattr(mb, "DailyModel", lambda: object())
        monkeypatch.setattr(mb, "HourlyModel", lambda: object())
        pts = [{"signal": 1.0, "dir_ok": True},
               {"signal": 0.0, "dir_ok": False},
               {"signal": None, "dir_ok": True}]
        monkeypatch.setattr(mb, "run_symbol_backtest",
                            lambda *a, **k: {"points": pts})
        monkeypatch.setattr(mb, "summarize", lambda data: {
            "n": 3, "dir_acc": 0.5, "n_eff": 3,
            "endpoint_mape": 0.3, "endpoint_bias_pct": 0.05,
            "path_corr": 0.6, "weighted_dir_acc": 0.56,
            "mae": 0.8, "mape": 0.3, "decay": 1.0})
        run_mod = self._load_run("fm_eval_run_gated_a")
        monkeypatch.setattr(run_mod, "is_gated_covariate", lambda name: True)
        out = run_mod.do_evaluate({
            "symbol": "m", "cov_override": "oi_gated_momentum",
            "max_points": 400, "stage": "aligned"})
        s = out["summary"]
        assert s["n_active"] == 1
        assert s["n_zero"] == 1
        assert s["n_nan"] == 1
        assert s["n_total"] == 3
        assert s["active_dir_acc"] == 1.0
        assert s["gate_pass"] is False  # n_active=1 < 350

    def test_do_evaluate_non_gated_no_metrics(self, monkeypatch):
        import monthly_backtest as mb
        monkeypatch.setattr(mb, "DailyModel", lambda: object())
        monkeypatch.setattr(mb, "HourlyModel", lambda: object())
        pts = [{"signal": 1.0, "dir_ok": True}]
        monkeypatch.setattr(mb, "run_symbol_backtest",
                            lambda *a, **k: {"points": pts})
        monkeypatch.setattr(mb, "summarize", lambda data: {
            "n": 1, "dir_acc": 0.5, "n_eff": 1,
            "endpoint_mape": 0.3, "endpoint_bias_pct": 0.05,
            "path_corr": 0.6, "weighted_dir_acc": 0.56,
            "mae": 0.8, "mape": 0.3, "decay": 1.0})
        run_mod = self._load_run("fm_eval_run_gated_b")
        monkeypatch.setattr(run_mod, "is_gated_covariate", lambda name: False)
        out = run_mod.do_evaluate({
            "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "stage": "aligned"})
        s = out["summary"]
        assert "active_dir_acc" not in s
        assert "n_active" not in s


# ======================================================
# monthly_backtest._point_signal
# ======================================================

class _FakeHourlyResult:
    def __init__(self, covariates, context_len):
        self.covariates = covariates
        self.context_len = context_len


class TestPointSignal:

    def test_signal_at_cutoff_bar(self):
        import monthly_backtest as mb
        ctx, h = 5, 3
        arr = [0.1] * (ctx - 1) + [2.5] + [9.9] * h
        res = _FakeHourlyResult({"oi_gated_momentum": arr}, ctx)
        assert mb._point_signal(res, "oi_gated_momentum") == 2.5

    def test_combo_mode_returns_none(self):
        import monthly_backtest as mb
        res = _FakeHourlyResult({"a": [1.0] * 8}, 5)
        assert mb._point_signal(res, None) is None

    def test_xreg_fallback_empty_covariates(self):
        import monthly_backtest as mb
        res = _FakeHourlyResult({}, 5)
        assert mb._point_signal(res, "oi_gated_momentum") is None

    def test_missing_cov_key_returns_none(self):
        import monthly_backtest as mb
        res = _FakeHourlyResult({"other": [1.0] * 8}, 5)
        assert mb._point_signal(res, "oi_gated_momentum") is None

    def test_short_array_returns_none(self):
        import monthly_backtest as mb
        res = _FakeHourlyResult({"oi_gated_momentum": [1.0] * 3}, 5)
        assert mb._point_signal(res, "oi_gated_momentum") is None

    def test_nan_signal_preserved(self):
        import monthly_backtest as mb
        arr = [0.1] * 4 + [float("nan")] + [9.9] * 3
        res = _FakeHourlyResult({"oi_gated_momentum": arr}, 5)
        assert math.isnan(mb._point_signal(res, "oi_gated_momentum"))

    def test_non_result_object_tolerated(self):
        import monthly_backtest as mb
        assert mb._point_signal(object(), "oi_gated_momentum") is None


# ======================================================
# pool "gated" 挂点读取
# ======================================================

class TestGatedPoolFlag:

    def test_flag_loaded_from_pool(self, tmp_path, monkeypatch):
        pool = {"covariates": {
            "oi_gated_momentum": {"status": "active", "gated": True},
            "rsi_state": {"status": "active"},
        }}
        p = tmp_path / "covariate_pool.json"
        p.write_text(json.dumps(pool), encoding="utf-8")
        monkeypatch.setattr(fm, "POOL_PATH", str(p))
        assert fm._load_gated_covariates() == {"oi_gated_momentum"}

    def test_gated_false_excluded(self, tmp_path, monkeypatch):
        pool = {"covariates": {
            "a": {"status": "active", "gated": False},
            "b": {"status": "active", "gated": "true"},  # 字符串不算
        }}
        p = tmp_path / "covariate_pool.json"
        p.write_text(json.dumps(pool), encoding="utf-8")
        monkeypatch.setattr(fm, "POOL_PATH", str(p))
        assert fm._load_gated_covariates() == set()

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fm, "POOL_PATH",
                            str(tmp_path / "nope.json"))
        assert fm._load_gated_covariates() == set()

    def test_corrupt_file_returns_empty(self, tmp_path, monkeypatch):
        p = tmp_path / "covariate_pool.json"
        p.write_text("{broken", encoding="utf-8")
        monkeypatch.setattr(fm, "POOL_PATH", str(p))
        assert fm._load_gated_covariates() == set()

    def test_is_gated_covariate(self, monkeypatch):
        monkeypatch.setattr(fm, "GATED_COVARIATES", {"oi_gated_momentum"})
        assert fm.is_gated_covariate("oi_gated_momentum") is True
        assert fm.is_gated_covariate("rsi_state") is False
