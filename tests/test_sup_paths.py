"""Tests for proposal lifecycle path constants."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from sup_paths import PROPOSAL_STATUS_PATH, REJECTED_PROPOSALS_PATH


def test_proposal_status_path_defined():
    """PROPOSAL_STATUS_PATH is defined and absolute."""
    assert PROPOSAL_STATUS_PATH is not None
    assert os.path.isabs(PROPOSAL_STATUS_PATH)


def test_rejected_proposals_path_defined():
    """REJECTED_PROPOSALS_PATH is defined and absolute."""
    assert REJECTED_PROPOSALS_PATH is not None
    assert os.path.isabs(REJECTED_PROPOSALS_PATH)


def test_paths_in_data_cache():
    """Both paths are under data/cache directory."""
    assert 'data/cache' in PROPOSAL_STATUS_PATH or 'data\cache' in PROPOSAL_STATUS_PATH
    assert 'data/cache' in REJECTED_PROPOSALS_PATH or 'data\cache' in REJECTED_PROPOSALS_PATH
