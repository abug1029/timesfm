"""
提案状态管理（Phase 1 Task 3）

事件日志模型（Model A）：proposal_status.jsonl 作为状态事实源，
append-only 记录一切状态转换。
使用侧车锁 path + ".lock"（对齐 registry_lib._queue_lock）。
SPEC §4.5 去重：proposal_id+version+reject_reason+run_id 只记一次。
"""
import contextlib
import fcntl
import json
import os
from datetime import datetime, timezone
from typing import Optional


@contextlib.contextmanager
def _status_lock(path):
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


def _read_existing(status_file):
    """读取已有记录用于去重。"""
    if not os.path.exists(status_file):
        return []
    records = []
    for line in open(status_file, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _dedup_key(record):
    """SPEC §4.5 去重键。"""
    return (
        record.get("proposal_id"),
        record.get("version"),
        record.get("reject_reason"),
        record.get("run_id"),
    )


def write_proposal_status(
    status_file: str,
    proposal_id: str,
    version: int,
    status: str,
    run_id: str,
    variant_id: Optional[str] = None,
    reject_reason: Optional[str] = None,
    quality_score: Optional[float] = None,
    reason: Optional[str] = None,
) -> None:
    """
    写入提案状态事件到 status 日志（append-only）。

    Args:
        status_file: 状态文件路径（通常为 PROPOSAL_STATUS_PATH）
        proposal_id: 提案 ID（来自 proposal JSON 的 proposal_id 字段）
        version: 提案版本（v1 默认为 1）
        status: 状态枚举（draft/prescreened/queued/evaluating/verdicted/rejected/withdrawn/degraded）
        run_id: 当前 run ID（通常 os.path.basename(run_dir) 即 src_run）
        variant_id: 入队后填充的实验身份
        reject_reason: rejected 时填充拒绝原因
        quality_score: 质量分数（rejected 时由质量门写入；其余状态可为 None）
        reason: withdrawn/degraded 时填充原因

    注意：parent_proposal_id / relation 为 Phase 3 预留，Phase 1 不写入。
    """
    record = {
        "proposal_id": proposal_id,
        "version": version,
        "status": status,
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    if variant_id is not None:
        record["variant_id"] = variant_id
    if reject_reason is not None:
        record["reject_reason"] = reject_reason
    if quality_score is not None:
        record["quality_score"] = quality_score
    if reason is not None:
        record["reason"] = reason

    # SPEC §4.5 去重：仅当 reject_reason 非空时检查
    dk = _dedup_key(record)
    with _status_lock(status_file):
        existing = _read_existing(status_file)
        existing_keys = {_dedup_key(r) for r in existing}
        if dk in existing_keys and reject_reason is not None:
            return  # 去重：相同的 proposal_id+version+reject_reason+run_id
        parent = os.path.dirname(status_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(status_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
