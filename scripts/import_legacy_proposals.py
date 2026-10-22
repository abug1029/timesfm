#!/usr/bin/env python3
"""Import legacy proposal files into slow loop queue with idempotency and concurrency control.

Ponytail: Minimal implementation - reads proposals, validates, deduplicates by variant_id,
acquires .local-pc.lock, writes to queue. No fancy abstractions.
"""
import fcntl
import json
import logging
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)

from proposal_validator import validate_proposal_dict
from cascade.experiment_fingerprint import build_variant_id
from cascade.cov_family import resolve_cov_family

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

LOCK_PATH = Path(FM_ROOT) / '.local-pc.lock'
QUEUE_PATH = Path(FM_ROOT) / 'task_FM' / 'config' / 'aligned_verdicts.jsonl'

def acquire_lock():
    """Acquire .local-pc.lock file lock (ponytail: stdlib fcntl, no fancy lock lib)."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(LOCK_PATH, 'a+')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        log.info(f'Acquired lock: {LOCK_PATH}')
        return lock_fd
    except BlockingIOError:
        lock_fd.close()
        raise RuntimeError(f'Cannot acquire lock {LOCK_PATH} - another process running')

def release_lock(lock_fd):
    """Release file lock."""
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
        log.info(f'Released lock: {LOCK_PATH}')
    except Exception as e:
        log.warning(f'Failed to release lock: {e}')

def load_existing_variant_ids():
    """Load existing variant_ids from queue (ponytail: read whole file, OK for <10MB)."""
    if not QUEUE_PATH.exists():
        return set()
    ids = set()
    with open(QUEUE_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                vid = rec.get('variant_id')
                if vid:
                    ids.add(vid)
            except json.JSONDecodeError:
                continue
    return ids

def normalize_proposal(p):
    """Normalize proposal to standard format."""
    symbol = p.get('symbol', '').lower()
    cov = p.get('cov_override', '')
    # resolve_cov_family expects a verdict dict
    verdict = {'symbol': symbol, 'cov_override': cov}
    fam = resolve_cov_family(verdict)
    fp = p.get('fingerprint', 'legacy')
    variant_id = build_variant_id(symbol, fam, fp)
    return {
        'variant_id': variant_id,
        'symbol': symbol,
        'cov_override': cov,
        'cov_family': fam,
        'proposal': p,
    }

def import_proposal_file(prop_path, existing_ids):
    """Import single proposal file. Returns (imported, skipped, failed) counts."""
    imported, skipped, failed = 0, 0, 0
    try:
        with open(prop_path, 'r', encoding='utf-8') as f:
            proposal = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error(f'Failed to read {prop_path}: {e}')
        return 0, 0, 1

    # Normalize
    try:
        normalized = normalize_proposal(proposal)
    except Exception as e:
        log.error(f'Failed to normalize {prop_path}: {e}')
        return 0, 0, 1

    variant_id = normalized['variant_id']

    # Idempotency check
    if variant_id in existing_ids:
        log.debug(f'Skipping duplicate: {variant_id}')
        return 0, 1, 0

    # Validate
    validation = validate_proposal_dict(proposal)
    if not validation.get('valid'):
        log.warning(f'Validation failed for {prop_path}: {validation.get("validation_signal")}')
        return 0, 0, 1

    # Write to queue (ponytail: append mode, one line per proposal)
    try:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(QUEUE_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                'schema': 'fm.aligned_verdict.v2',
                'variant_id': variant_id,
                'symbol': normalized['symbol'],
                'cov_override': normalized['cov_override'],
                'cov_family': normalized['cov_family'],
                'status': 'queued',
                'stage': 'imported_legacy',
                'proposal': proposal,
            }, ensure_ascii=False) + '\n')
        existing_ids.add(variant_id)  # Prevent duplicate in same run
        imported += 1
        log.info(f'Imported: {variant_id}')
    except Exception as e:
        log.error(f'Failed to write {variant_id}: {e}')
        failed += 1

    return imported, skipped, failed

def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Import legacy proposals')
    parser.add_argument('--proposals-dir', type=str, default=str(Path(FM_ROOT) / 'task_FM' / 'proposals'),
                        help='Directory containing proposal JSON files')
    parser.add_argument('--dry-run', action='store_true', help='Validate without writing')
    args = parser.parse_args()

    proposals_dir = Path(args.proposals_dir)
    if not proposals_dir.exists():
        log.error(f'Proposals directory not found: {proposals_dir}')
        sys.exit(1)

    prop_files = list(proposals_dir.glob('*.json'))
    log.info(f'Found {len(prop_files)} proposal files in {proposals_dir}')

    if args.dry_run:
        log.info('DRY RUN - no writes')
        existing_ids = set()
    else:
        lock_fd = acquire_lock()
        try:
            existing_ids = load_existing_variant_ids()
            log.info(f'Loaded {len(existing_ids)} existing variant_ids from queue')

            total_imported, total_skipped, total_failed = 0, 0, 0
            for prop_file in prop_files:
                imp, skp, fail = import_proposal_file(prop_file, existing_ids)
                total_imported += imp
                total_skipped += skp
                total_failed += fail

            log.info(f'Import complete: {total_imported} imported, {total_skipped} skipped (duplicate), {total_failed} failed')
        finally:
            release_lock(lock_fd)

if __name__ == '__main__':
    main()
