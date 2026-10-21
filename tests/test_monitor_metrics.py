"""Tests for monitor_metrics.py and generate_weekly_report.py.

Run: pytest tests/test_monitor_metrics.py -v
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# We need to import from scripts/
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from monitor_metrics import (
    collect_daily_metrics,
    check_red_lines,
    generate_report,
    compute_trend,
    _read_jsonl,
    _compute_combination_coverage,
    TARGETS,
)
from generate_weekly_report import (
    generate_weekly_report,
    _generate_recommendations,
    _get_dates_for_week,
)


# ---------------------------------------------------------------------------
# Test data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_verdicts(tmp_path):
    """Create sample verdicts JSONL."""
    verdicts = [
        {"variant_id": "m_momentum", "symbol": "m", "cov_family": "momentum", "gate_pass": True, "tier": "S"},
        {"variant_id": "m_momentum", "symbol": "m", "cov_family": "momentum", "gate_pass": False, "tier": "C"},
        {"variant_id": "cf_calendar", "symbol": "cf", "cov_family": "calendar", "gate_pass": True, "tier": "A"},
        {"variant_id": "cf_calendar", "symbol": "cf", "cov_family": "calendar", "gate_pass": True, "tier": "B"},
        {"variant_id": "rb_vol", "symbol": "rb", "cov_family": "volatility", "gate_pass": False, "tier": "D"},
    ]
    path = tmp_path / "verdicts.jsonl"
    with open(path, "w") as f:
        for v in verdicts:
            f.write(json.dumps(v) + "\n")
    return path


@pytest.fixture
def sample_registry(tmp_path):
    """Create sample registry JSONL with proposal + prescreen stems."""
    entries = [
        {"stem": "20261018_m_momentum.fm.hypothesis_proposal.v1"},
        {"stem": "20261018_cf_calendar.fm.hypothesis_proposal.v1"},
        {"stem": "20261018_rb_vol.fm.hypothesis_proposal.v1"},
        {"stem": "20261018_m_momentum.fm.hypothesis_proposal.v1.prescreen"},
        {"stem": "20261018_cf_calendar.fm.hypothesis_proposal.v1.prescreen"},
    ]
    path = tmp_path / "registry.jsonl"
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


@pytest.fixture
def sample_pending(tmp_path):
    """Create sample pending JSONL (not used for prescreen metric directly)."""
    entries = [
        {"variant_id": "v1", "stage": "aligned"},
        {"variant_id": "v2", "stage": "aligned"},
    ]
    path = tmp_path / "pending.jsonl"
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


@pytest.fixture
def sample_short_win(tmp_path):
    """Create sample short window results."""
    entries = [
        {"variant_id": "v1", "pass": True},
        {"variant_id": "v2", "pass": False},
    ]
    path = tmp_path / "short_win.jsonl"
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCollectDailyMetrics:
    def test_collect_daily_metrics(self, sample_verdicts, sample_registry,
                                    sample_pending, sample_short_win):
        """Metric collection returns correct values."""
        with patch("monitor_metrics.VERDICTS_PATH", sample_verdicts), \
             patch("monitor_metrics.REGISTRY_PATH", sample_registry), \
             patch("monitor_metrics.PENDING_PATH", sample_pending), \
             patch("monitor_metrics.SHORT_WIN_PATH", sample_short_win):
            metrics = collect_daily_metrics(date_str="2026-10-20")

        assert metrics["date"] == "2026-10-20"
        assert metrics["raw_counts"]["total_verdicts"] == 5
        assert metrics["raw_counts"]["gate_pass"] == 3  # 3 out of 5
        assert metrics["gate_pass_rate"] == pytest.approx(0.6, abs=0.01)
        # S=1, A=1 -> 2/5 = 0.4
        assert metrics["high_quality_rate"] == pytest.approx(0.4, abs=0.01)
        # All 4 stems unique -> 0.0 redundancy
        assert metrics["redundancy_rate"] == pytest.approx(0.0, abs=0.01)
        # 3 proposal stems, all 3 have verdicts -> 1.0
        assert metrics["unique_variant_coverage"] == pytest.approx(1.0, abs=0.01)
        # 2 prescreen stems, both have verdicts -> 1.0
        assert metrics["prescreen_success_rate"] == pytest.approx(1.0, abs=0.01)
        # short_win: 2 entries
        assert metrics["raw_counts"]["short_window_results"] == 2
        # combination: (m,momentum)=pass, (cf,calendar)=pass, (rb,volatility)=no -> 2/3
        assert metrics["combination_coverage"] == pytest.approx(0.667, abs=0.01)

    def test_empty_data_handling(self, tmp_path):
        """Empty data files produce zero metrics without error."""
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        with patch("monitor_metrics.VERDICTS_PATH", empty), \
             patch("monitor_metrics.REGISTRY_PATH", empty), \
             patch("monitor_metrics.PENDING_PATH", empty), \
             patch("monitor_metrics.SHORT_WIN_PATH", empty):
            metrics = collect_daily_metrics()

        assert metrics["gate_pass_rate"] == 0.0
        assert metrics["high_quality_rate"] == 0.0
        assert metrics["redundancy_rate"] == 0.0
        assert metrics["status"] == "warning"  # all below targets


class TestCheckRedLines:
    def test_check_red_lines_laya_update(self, tmp_path):
        """Unknown model files trigger a CRITICAL alert."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "quality_model.json").touch()
        (models_dir / "suspicious_new_model.bin").touch()

        with patch("monitor_metrics._REPO_ROOT", tmp_path):
            alerts = check_red_lines()

        assert any("CRITICAL" in a for a in alerts)

    def test_check_red_lines_queue_duplicates(self, tmp_path):
        """Duplicate stems in registry trigger a WARNING."""
        registry = tmp_path / "registry.jsonl"
        registry.write_text(
            '{"stem": "20261018_a_momentum.fm.hypothesis_proposal.v1"}\n'
            '{"stem": "20261018_a_momentum.fm.hypothesis_proposal.v1"}\n'
        )
        with patch("monitor_metrics.REGISTRY_PATH", registry), \
             patch("monitor_metrics._REPO_ROOT", tmp_path):
            alerts = check_red_lines()

        assert any("duplicate stems" in a for a in alerts)

    def test_no_red_lines_clean(self, tmp_path):
        """Clean state produces no alerts."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "quality_model.json").touch()

        empty_registry = tmp_path / "registry.jsonl"
        empty_registry.write_text("")

        # No experiment dir -> no ledger entries -> no mixed covariates
        with patch("monitor_metrics._REPO_ROOT", tmp_path), \
             patch("monitor_metrics.REGISTRY_PATH", empty_registry):
            alerts = check_red_lines()

        assert len(alerts) == 0


class TestGenerateReport:
    def test_generate_report_markdown(self):
        """Markdown report contains expected sections."""
        metrics = collect_daily_metrics.__wrapped__() if hasattr(collect_daily_metrics, '__wrapped__') else {
            "date": "2026-10-20",
            "redundancy_rate": 0.05,
            "unique_variant_coverage": 0.85,
            "gate_pass_rate": 0.55,
            "high_quality_rate": 0.45,
            "prescreen_success_rate": 0.85,
            "combination_coverage": 0.35,
            "raw_counts": {"total_verdicts": 100, "gate_pass": 55, "high_quality_S_A": 45,
                          "registry_stems": 50, "dup_stems": 2, "pending_total": 20,
                          "pending_ok": 17, "short_window_results": 10},
            "status": "ok",
            "alerts": [],
        }
        report = generate_report(metrics, output_format="markdown")
        assert "# FM_a 监控报告" in report
        assert "核心指标" in report
        assert "✅" in report

    def test_generate_report_json(self):
        """JSON report is valid JSON with all required keys."""
        metrics = {
            "date": "2026-10-20",
            "redundancy_rate": 0.05,
            "unique_variant_coverage": 0.85,
            "gate_pass_rate": 0.55,
            "high_quality_rate": 0.45,
            "prescreen_success_rate": 0.85,
            "combination_coverage": 0.35,
            "raw_counts": {},
            "status": "ok",
            "alerts": [],
        }
        report = generate_report(metrics, output_format="json")
        parsed = json.loads(report)
        assert parsed["date"] == "2026-10-20"
        assert "gate_pass_rate" in parsed


class TestTrendCalculation:
    def test_trend_up(self):
        assert compute_trend([0.1, 0.2, 0.3, 0.4, 0.5]) == "up"

    def test_trend_down(self):
        assert compute_trend([0.5, 0.4, 0.3, 0.2, 0.1]) == "down"

    def test_trend_stable(self):
        assert compute_trend([0.5, 0.5, 0.5, 0.5]) == "stable"

    def test_trend_single_value(self):
        assert compute_trend([0.5]) == "stable"

    def test_trend_empty(self):
        assert compute_trend([]) == "stable"


class TestCombinationCoverage:
    def test_combination_coverage_full(self):
        verdicts = [
            {"symbol": "m", "cov_family": "momentum", "gate_pass": True},
            {"symbol": "m", "cov_family": "calendar", "gate_pass": False},
        ]
        # 2 combos, 1 has gate_pass -> 0.5
        assert _compute_combination_coverage(verdicts) == pytest.approx(0.5)

    def test_combination_coverage_empty(self):
        assert _compute_combination_coverage([]) == 0.0


class TestWeeklyReport:
    def test_weekly_report_generation(self, tmp_path):
        """Weekly report generates with correct structure."""
        # Create fake metrics history
        metrics_dir = tmp_path / "data" / "cache" / "metrics_history"
        metrics_dir.mkdir(parents=True)
        for i in range(3):
            date_str = f"2026-10-{18 + i}"
            data = {
                "date": date_str,
                "redundancy_rate": 0.05 + i * 0.01,
                "unique_variant_coverage": 0.80,
                "gate_pass_rate": 0.55,
                "high_quality_rate": 0.40,
                "prescreen_success_rate": 0.85,
                "combination_coverage": 0.35,
                "raw_counts": {},
                "status": "ok",
                "alerts": [],
            }
            (metrics_dir / f"metrics_{date_str}.json").write_text(
                json.dumps(data), encoding="utf-8"
            )

        with patch("generate_weekly_report._METRICS_DIR", metrics_dir):
            report = generate_weekly_report(
                ["2026-10-18", "2026-10-19", "2026-10-20"],
                week_label="测试周",
            )

        assert "周报" in report
        assert "测试周" in report
        assert "指标趋势" in report
        assert "每日摘要" in report

    def test_get_dates_for_week(self):
        """ISO week date calculation is correct."""
        dates = _get_dates_for_week(2026, 1)
        assert len(dates) == 7
        assert dates[0] == "2025-12-29"  # Monday of week 1
        assert dates[-1] == "2026-01-04"  # Sunday

    def test_recommendations(self):
        """Recommendations fire when metrics are below target."""
        averages = {
            "redundancy_rate": 0.05,
            "unique_variant_coverage": 0.50,  # below 0.80 target
            "gate_pass_rate": 0.30,  # below 0.50 target
            "high_quality_rate": 0.30,  # below 0.40 target
            "prescreen_success_rate": 0.60,  # below 0.80 target
            "combination_coverage": 0.20,  # below 0.30 target
        }
        trends = {k: "stable" for k in averages}
        recs = _generate_recommendations(averages, trends)
        assert len(recs) >= 3  # at least 3 metrics below target
