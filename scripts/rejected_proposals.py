"""
拒收提案记录（Phase 1 Task 4）

结构化记录被质量门拒绝的提案详情，供 aggregate_rejection_stats.py 消费。
使用侧车锁 path + ".lock"（对齐 registry_lib._queue_lock）。
SPEC §4.5 去重：proposal_id+version+reject_reason+run_id 只记一次。
"""
import contextlib
import fcntl
import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict


@contextlib.contextmanager
def _rejected_lock(path):
    """侧车锁，对齐 registry_lib._queue_lock。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock = open(path + ".lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _read_existing(rejected_file):
    if not os.path.exists(rejected_file):
        return []
    records = []
    for line in open(rejected_file, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _dedup_key(record):
    return (
        record.get("proposal_id"),
        record.get("version"),
        record.get("reject_reason"),
        record.get("run_id"),
    )


def write_rejected_proposal(
    rejected_file: str,
    proposal_id: str,
    version: int,
    reject_reason: str,
    quality_score: Optional[float],
    run_id: str,
    symbol: Optional[str] = None,
    cov_override: Optional[str] = None,
    covariate_family: Optional[str] = None,
    breakdown: Optional[Dict] = None,
) -> None:
    """
    写入拒收提案记录到 rejected 日志（append-only）。

    quality_score 可为 None（在质量门之前被拒的提案）。
    """
    record = {
        "proposal_id": proposal_id,
        "version": version,
        "reject_reason": reject_reason,
        "quality_score": quality_score,  # None 允许（质量门前被拒）
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    if symbol is not None:
        record["symbol"] = symbol
    if cov_override is not None:
        record["cov_override"] = cov_override
    if covariate_family is not None:
        record["covariate_family"] = covariate_family
    if breakdown is not None:
        record["breakdown"] = breakdown

    dk = _dedup_key(record)
    with _rejected_lock(rejected_file):
        existing = _read_existing(rejected_file)
        existing_keys = {_dedup_key(r) for r in existing}
        if dk in existing_keys:
            return  # 去重
        parent = os.path.dirname(rejected_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(rejected_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
