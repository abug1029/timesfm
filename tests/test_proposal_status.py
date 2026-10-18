import json
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_write_proposal_status_creates_file():
    """写入状态时创建文件"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(
            status_file=status_file,
            proposal_id="test_prop",
            version=1,
            status="draft",
            run_id="test_run",
        )

        assert os.path.exists(status_file)
        with open(status_file) as f:
            line = f.readline()
            record = json.loads(line)
            assert record["proposal_id"] == "test_prop"
            assert record["version"] == 1
            assert record["status"] == "draft"
            assert record["run_id"] == "test_run"
            assert "ts" in record
    finally:
        if os.path.exists(status_file):
            os.remove(status_file)
        lock_file = status_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)


def test_write_proposal_status_uses_sidecar_lock():
    """使用侧车锁 path + '.lock'（对齐 registry_lib._queue_lock）"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(status_file, "prop1", 1, "queued", "run1")
        write_proposal_status(status_file, "prop1", 1, "prescreened", "run1")
        with open(status_file) as f:
            lines = f.readlines()
            assert len(lines) == 2
    finally:
        if os.path.exists(status_file):
            os.remove(status_file)
        lock_file = status_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)


def test_write_proposal_status_dedup():
    """SPEC §4.5 去重：相同 proposal_id+version+reject_reason+run_id 只记一次"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(
            status_file, "prop1", 1, "rejected", "run1",
            reject_reason="schema_mismatch",
        )
        write_proposal_status(
            status_file, "prop1", 1, "rejected", "run1",
            reject_reason="schema_mismatch",
        )

        with open(status_file) as f:
            lines = f.readlines()
            # 去重后只有 1 条（相同的 proposal_id+version+reject_reason+run_id）
            assert len(lines) == 1
    finally:
        if os.path.exists(status_file):
            os.remove(status_file)
        lock_file = status_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)


def test_write_proposal_status_with_variant_id():
    """写入状态时可携带 variant_id"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(
            status_file=status_file,
            proposal_id="test_prop",
            version=1,
            status="queued",
            run_id="test_run",
            variant_id="m_momentum_abc123",
        )

        with open(status_file) as f:
            record = json.loads(f.readline())
            assert record["variant_id"] == "m_momentum_abc123"
    finally:
        if os.path.exists(status_file):
            os.remove(status_file)
        lock_file = status_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)


def test_write_proposal_status_with_quality_score():
    """写入 rejected 状态时可携带 quality_score"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(
            status_file=status_file,
            proposal_id="test_prop",
            version=1,
            status="rejected",
            run_id="test_run",
            reject_reason="quality_below_threshold",
            quality_score=-12.5,
        )

        with open(status_file) as f:
            record = json.loads(f.readline())
            assert record["status"] == "rejected"
            assert record["reject_reason"] == "quality_below_threshold"
            assert record["quality_score"] == -12.5
    finally:
        if os.path.exists(status_file):
            os.remove(status_file)
        lock_file = status_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
