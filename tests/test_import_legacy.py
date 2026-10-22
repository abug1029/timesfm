"""Tests for import_legacy_proposals.py - idempotency and concurrency."""
import json
import os
import tempfile
import pytest
from pathlib import Path

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
import import_legacy_proposals as imp

class TestIdempotencyKey:
    """Test variant_id as idempotency key."""

    def test_duplicate_variant_id_skipped(self):
        """Same variant_id should be skipped on second import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup temp queue
            queue_path = Path(tmpdir) / 'queue.jsonl'
            imp.QUEUE_PATH = queue_path

            # Create valid proposal with 64-char fingerprint
            prop = {
                'symbol': 'm',
                'cov_override': 'vol',
                'mechanism': 'volatility drives price through liquidity gaps',
                'symbol_fit': 'm is a liquid commodity future',
                'predicted_direction': 'up',
                'fingerprint': 'a' * 64,
            }
            prop_path = Path(tmpdir) / 'prop1.json'
            with open(prop_path, 'w') as f:
                json.dump(prop, f)

            existing_ids = set()
            imported, skipped, failed = imp.import_proposal_file(prop_path, existing_ids)
            assert imported == 1
            assert skipped == 0
            # variant_id format: symbol_cov_family_fingerprint
            expected_vid = 'm_volatility_' + 'a' * 12
            assert expected_vid in existing_ids
            assert queue_path.exists()
            assert len(queue_path.read_text().strip().split('\n')) == 1

            # Second import should skip
            imported2, skipped2, failed2 = imp.import_proposal_file(prop_path, existing_ids)
            assert imported2 == 0
            assert skipped2 == 1
            lines = queue_path.read_text().strip().split('\n')
            assert len(lines) == 1  # Still only one line

    def test_different_variant_ids_imported(self):
        """Different variant_ids should both be imported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / 'queue.jsonl'
            imp.QUEUE_PATH = queue_path

            prop1 = {
                'symbol': 'm',
                'cov_override': 'vol',
                'mechanism': 'volatility drives price',
                'symbol_fit': 'm is liquid',
                'predicted_direction': 'up',
                'fingerprint': 'b' * 64,
            }
            prop2 = {
                'symbol': 'm',
                'cov_override': 'momentum',
                'mechanism': 'momentum drives price',
                'symbol_fit': 'm is liquid',
                'predicted_direction': 'down',
                'fingerprint': 'c' * 64,
            }

            p1 = Path(tmpdir) / 'prop1.json'
            p2 = Path(tmpdir) / 'prop2.json'
            with open(p1, 'w') as f:
                json.dump(prop1, f)
            with open(p2, 'w') as f:
                json.dump(prop2, f)

            existing_ids = set()
            imp.import_proposal_file(p1, existing_ids)
            imp.import_proposal_file(p2, existing_ids)

            assert len(existing_ids) == 2
            lines = queue_path.read_text().strip().split('\n')
            assert len(lines) == 2

class TestConcurrencyLock:
    """Test .local-pc.lock file lock."""

    def test_lock_acquire_release(self):
        """Lock should be acquirable and releasable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / '.local-pc.lock'
            imp.LOCK_PATH = lock_path

            lock_fd = imp.acquire_lock()
            assert lock_path.exists()
            assert lock_fd is not None

            imp.release_lock(lock_fd)

    def test_concurrent_lock_blocked(self):
        """Second lock acquisition should fail while first holds lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / '.local-pc.lock'
            imp.LOCK_PATH = lock_path

            lock_fd1 = imp.acquire_lock()
            with pytest.raises(RuntimeError, match='Cannot acquire lock'):
                imp.acquire_lock()

            imp.release_lock(lock_fd1)

            # Now should succeed
            lock_fd2 = imp.acquire_lock()
            imp.release_lock(lock_fd2)
