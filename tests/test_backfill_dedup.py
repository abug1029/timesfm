# tests/test_backfill_dedup.py
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# 确保项目根在 sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def test_backfill_skips_existing_variant():
    """existing 中已有 variant -> 跳过 prescreen_and_save 调用"""
    stats = MagicMock()
    stats.skipped = 0

    mock_fields = {
        "symbol": "p",
        "cov_override": "oi",
        "proposal_data": {"proposal_id": "p_test", "symbol": "p", "cov_override": "oi"},
    }
    mock_vid = "v_p_oi_abc123def456"
    existing = {mock_vid}

    with patch('scripts.backfill_prescreen.extract_proposal_fields', return_value=mock_fields),          patch('scripts.backfill_prescreen.generate_variant_id', return_value=mock_vid),          patch('cascade.typesafe_prescreen.prescreen_and_save') as mock_prescreen:

        from scripts.backfill_prescreen import process_proposal
        result = process_proposal(
            "task_FM/experiments/run_1/results/p/proposals/p_test.json",
            stats=stats,
            verdict_history=None,
            covariate_menu=None,
            queue_path="/dev/null",
            dead=set(),
            existing=existing,
        )

        assert result == "skipped"
        stats.inc.assert_called_with("skipped")
        mock_prescreen.assert_not_called()


def test_backfill_does_not_skip_new_variant():
    """existing 中无该 variant -> 正常调 prescreen_and_save"""
    stats = MagicMock()
    stats.success = 0
    stats.skipped = 0

    mock_fields = {
        "symbol": "p",
        "cov_override": "oi",
        "proposal_data": {"proposal_id": "p_new", "symbol": "p", "cov_override": "oi"},
    }
    mock_vid = "v_p_oi_newvariant"
    existing = set()

    with patch('scripts.backfill_prescreen.extract_proposal_fields', return_value=mock_fields),          patch('scripts.backfill_prescreen.generate_variant_id', return_value=mock_vid),          patch('cascade.typesafe_prescreen.prescreen_and_save', return_value={"status": "degraded"}) as mock_prescreen:

        from scripts.backfill_prescreen import process_proposal
        result = process_proposal(
            "task_FM/experiments/run_1/results/p/proposals/p_new.json",
            stats=stats,
            verdict_history=None,
            covariate_menu=None,
            queue_path="/dev/null",
            dead=set(),
            existing=existing,
        )

        mock_prescreen.assert_called_once()
