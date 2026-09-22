"""tests/test_track_prescreen_quality.py — Test Jev quality tracking (Phase 3)."""
import json
import sys
from pathlib import Path

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))

from scripts.track_prescreen_quality import _analyze, _verdicts, MIN_SAMPLES


def _mk(prescreen: dict, gate_pass=False, dir_acc=None, migrated=False):
    v = {
        "symbol": "rb", "cov_override": "xe", "cov_family": "mom",
        "gate_pass": gate_pass, "migrated_pass": migrated,
        "dir_acc": dir_acc, "metadata": {"prescreen": prescreen},
    }
    return v


class TestAnalyze:
    def test_empty_returns_zeros(self):
        m = _analyze([])
        assert m["high_conf_gate_rate"] == 0.0
        assert m["high_conf_n"] == 0

    def test_high_conf_gate_rate(self):
        vs = [
            _mk({"plausibility": 0.8, "skip_suggested": False}, gate_pass=True),
            _mk({"plausibility": 0.9, "skip_suggested": False}, gate_pass=False),
        ]
        m = _analyze(vs)
        assert m["high_conf_n"] == 2
        assert m["high_conf_gate_rate"] == 0.5

    def test_skip_true_rate_strict(self):
        # NIT-2: 严格口径只计 gate_pass, 不算 migrated_pass
        vs = [
            _mk({"plausibility": 0.3, "skip_suggested": True}, gate_pass=False),
            _mk({"plausibility": 0.2, "skip_suggested": True}, gate_pass=False, migrated=True),
        ]
        m = _analyze(vs)
        assert m["skip_true_n"] == 2
        assert m["skip_true_gate_rate"] == 0.0  # 严格: 无 gate_pass

    def test_high_conf_loose_includes_migrated(self):
        # NIT-2: 宽松口径计入 migrated_pass, 严格口径不计
        vs = [
            _mk({"plausibility": 0.8, "skip_suggested": False}, gate_pass=False, migrated=True),
        ]
        m = _analyze(vs)
        assert m["high_conf_n"] == 1
        assert m["high_conf_gate_rate"] == 0.0           # 严格
        assert m["high_conf_gate_rate_loose"] == 1.0     # 宽松

    def test_novelty_dir_acc(self):
        vs = [
            _mk({"novelty": "novel"}, dir_acc=0.60),
            _mk({"novelty": "redundant"}, dir_acc=0.50),
        ]
        m = _analyze(vs)
        assert m["novel_mean_dir_acc"] == pytest.approx(0.60)
        assert m["redundant_mean_dir_acc"] == pytest.approx(0.50)

    def test_effect_buckets(self):
        vs = [
            _mk({"effect_size": 0}, gate_pass=False),
            _mk({"effect_size": 3}, gate_pass=True),
        ]
        m = _analyze(vs)
        assert m["effect_bucket_rates"] == {0: 0.0, 3: 1.0}


class TestVerdicts:
    def test_insufficient_samples_gives_no_recommendation(self):
        verdicts = [_mk({"plausibility": 0.8}) for _ in range(10)]
        findings = _verdicts(_analyze(verdicts), verdicts)
        assert any("样本不足" in f for f in findings)

    def test_sufficient_high_conf_signal(self):
        # 30 high-conf verdicts, 60%+ gate rate → 有效信号
        verdicts = [_mk({"plausibility": 0.8, "skip_suggested": False},
                        gate_pass=True, dir_acc=0.55)
                    for _ in range(MIN_SAMPLES)]
        # 保证高可信 n 足够: 全高可信
        m = _analyze(verdicts)
        findings = _verdicts(m, verdicts)
        assert any("[有效]" in f for f in findings)

    def test_sufficient_low_confidence_keeps_conservative(self):
        # 高可信但过门率低 → 保守结论
        verdicts = [_mk({"plausibility": 0.8, "skip_suggested": False})
                    for _ in range(MIN_SAMPLES)]
        m = _analyze(verdicts)
        findings = _verdicts(m, verdicts)
        assert any("[待校准]" in f for f in findings)