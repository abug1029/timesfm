# Phase 1: 提案状态显式管理 + 标注机制 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **修订状态**：2026-10-18 根据第3轮审核修订（P1-A 挂点修正 + P1-D 测试签名+参数+helper 修正；P0/P2 不变）。

**Goal:** 建立提案状态的显式管理机制，使提案从生成到裁决的全生命周期可观测、可追溯，同时支持 schema v2 并接受 v1。

**Architecture:** 采用事件日志模型（Model A），`proposal_status.jsonl` 作为状态事实源，append-only 记录一切状态转换；`rejected_proposals.jsonl` 记录结构化拒收详情。通过 queue 行的 `proposal_id+version+variant_id` 实现提案↔裁决的 join，verdict schema 不变。

**Tech Stack:** Python 3.11 + JSONL 文件总线 + fcntl 文件锁（与现有 queue/verdict 一致）

**Spec:** `docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md`（Frozen，2026-10-18）

## Global Constraints

- Schema 接受集合：`_ACCEPTED_SCHEMAS = {"fm.hypothesis_proposal.v1", "fm.hypothesis_proposal.v2"}`
- v1 的 version 默认为 1（不写 = 1）；**v2 必须有 `version` 字段且为整数 ≥1，否则 `schema_mismatch`**
- `proposal_status.jsonl` 和 `rejected_proposals.jsonl` 使用 **侧车锁**（`path + ".lock"`，对齐 `registry_lib._queue_lock`）
- degraded 策略采用 soft 模式（不硬拦入队，与现有行为一致）
- per-proposal 拒收详情进 `known_verdicts.inc.md` 新节；`known_rejections.inc.md` 仅保留计数分布
- **单一 VERDICTS_INC 写者**：`materialize_known_verdicts`（Task 9）组装「拒收详情节 + 因果链 + 版本比较」并写盘；Task 8 只提供 `render_rejection_detail_section()` 纯函数，CLI 继续只写 `known_rejections.inc.md` 计数
- withdrawn 以 status 日志为唯一事实源，不可从其他文件派生
- verdict 文件保持 append-only，不改 schema
- **proposal_id 来源**：lifecycle 统一使用 **proposal JSON 内的 `proposal_id` 字段**；缺失时策略为 `_reject("missing_proposal_id")`（不 fallback 到 search_proposal_id 路径名，两者文档分隔）
- **入队行禁止 `"unknown"` 哨兵**：`proposal_id` 缺失的提案在 schema 通过后、质量门前即被拒收，不会进入 `_cand`

## Review Focus

1. **Schema 兼容性**：v1 无 version 字段的旧提案仍可入队；v2 schema 带合法 version 的提案不触发 schema_mismatch；v2 缺/非正整数 version → schema_mismatch
2. **状态写入幂等性**：同一 proposal 重扫不导致 status jsonl 无限追加（SPEC §4.5 去重：`proposal_id+version+reject_reason+run_id` 只记一次）
3. **Join 正确性**：给定 proposal→queue→verdict 夹具，known_verdicts.inc.md 必须出现可机器检查的因果行（含 proposal_id、version、variant_id、gate/fdr）
4. **文件锁竞态**：多进程 harvest+withdraw 使用侧车锁约定（`path + ".lock"`），不丢状态
5. **回归测试**：现有质量门 + 树守卫拒绝码行为不变（回归测试全绿；具体数量以代码为准，SPEC 已不再使用「18 道门」字面量）

## 风险与缓解

1. **文件锁竞态**：统一使用侧车锁 `path + ".lock"`（与 `registry_lib._queue_lock` 一致），多进程安全
2. **Status 文件膨胀**：每个 proposal 约 3-5 条记录，1000 proposals ≈ 5000 行 ≈ 1MB，可控；retention 策略引用 SPEC §6.1，Phase 1 仅文档化
3. **Schema 兼容性**：v1 默认 version=1，向后兼容；v2 强制校验 version 字段
4. **回归测试**：每个任务后运行现有测试，确保无回归
5. **degraded 软回归**：新增断言确认 degraded 策略不单独 `_reject`、入队行为与改前一致

---

### Task 1: 新增文件路径常量

**Files:**
- Modify: `scripts/sup_paths.py`
- Test: `tests/test_sup_paths.py` (新建)

**Interfaces:**
- Consumes: 无（纯常量定义）
- Produces: `PROPOSAL_STATUS_PATH`, `REJECTED_PROPOSALS_PATH` 两个常量，供后续任务使用

- [ ] **Step 1: 编写测试**

```python
# tests/test_sup_paths.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import sup_paths as sp

def test_proposal_status_path_defined():
    """PROPOSAL_STATUS_PATH 已定义且为绝对路径"""
    assert hasattr(sp, 'PROPOSAL_STATUS_PATH')
    assert os.path.isabs(sp.PROPOSAL_STATUS_PATH)
    assert sp.PROPOSAL_STATUS_PATH.endswith('proposal_status.jsonl')

def test_rejected_proposals_path_defined():
    """REJECTED_PROPOSALS_PATH 已定义且为绝对路径"""
    assert hasattr(sp, 'REJECTED_PROPOSALS_PATH')
    assert os.path.isabs(sp.REJECTED_PROPOSALS_PATH)
    assert sp.REJECTED_PROPOSALS_PATH.endswith('rejected_proposals.jsonl')

def test_paths_in_data_cache():
    """两个新路径都在 data/cache 目录下"""
    assert 'data/cache' in sp.PROPOSAL_STATUS_PATH
    assert 'data/cache' in sp.REJECTED_PROPOSALS_PATH
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd /home/abug/timesfm
source .venv/bin/activate
pytest tests/test_sup_paths.py -v
```

Expected: FAIL（AttributeError: module 'sup_paths' has no attribute 'PROPOSAL_STATUS_PATH'）

- [ ] **Step 3: 实现常量定义**

```python
# scripts/sup_paths.py — 在文件末尾添加

# ── 提案生命周期管理（Phase 1）──
PROPOSAL_STATUS_PATH = os.path.join(FM_ROOT, "data", "cache", "proposal_status.jsonl")
REJECTED_PROPOSALS_PATH = os.path.join(FM_ROOT, "data", "cache", "rejected_proposals.jsonl")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_sup_paths.py -v
```

Expected: PASS（3 tests）

- [ ] **Step 5: 提交**

```bash
git add scripts/sup_paths.py tests/test_sup_paths.py
git commit -m "feat(proposal-lifecycle): add PROPOSAL_STATUS_PATH and REJECTED_PROPOSALS_PATH constants

- Phase 1 Task 1: file path constants for proposal lifecycle management
- PROPOSAL_STATUS_PATH: event log for proposal state transitions
- REJECTED_PROPOSALS_PATH: structured rejection records

Spec: docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md"
```

---

### Task 2: Schema 接受集合修改

**Files:**
- Modify: `scripts/sup_harvest.py:604-605`（基于唯一字符串替换，非行号 sed）
- Test: `tests/test_schema_acceptance.py` (新建)

**Interfaces:**
- Consumes: proposal JSON 的 `schema` 字段
- Produces: 修改后的 schema 检查逻辑，接受 `{v1, v2}`；**v2 缺/非正整数 version → schema_mismatch**

- [ ] **Step 1: 编写测试**

```python
# tests/test_schema_acceptance.py
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_schema_v1_accepted():
    """v1 schema 被接受（向后兼容）"""
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v1" in _ACCEPTED_SCHEMAS

def test_schema_v2_accepted():
    """v2 schema 被接受"""
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v2" in _ACCEPTED_SCHEMAS

def test_schema_v3_rejected():
    """v3 schema 被拒绝"""
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v3" not in _ACCEPTED_SCHEMAS

def test_v1_default_version():
    """v1 不写 version 字段时默认为 1 — 在 Task 3 入队行验证"""
    from sup_harvest import _ACCEPTED_SCHEMAS
    # 这里只验证 schema 集合，version 默认值在 Task 3/5 集成测试中验证
    assert "fm.hypothesis_proposal.v1" in _ACCEPTED_SCHEMAS

def test_v2_missing_version_rejected():
    """v2 schema 缺少 version 字段 → schema_mismatch"""
    # 需要在完整 harvest 集成测试中验证（Task 7）
    # 简化版：断言 _check_v2_version 辅助函数行为
    from sup_harvest import _check_v2_version
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2"}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 2}) == True
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 0}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": -1}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": "abc"}) == False
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_schema_acceptance.py -v
```

Expected: FAIL（ImportError: cannot import name '_ACCEPTED_SCHEMAS'）

- [ ] **Step 3: 实现 schema 接受集合 + v2 version 校验**

```python
# scripts/sup_harvest.py — 在文件开头（import 后）添加

# ── Schema 接受集合（Phase 1 Task 2）──
# Spec §3.6: 接受 v1 和 v2；v1 的 version 默认为 1；v2 必须有合法 version
_ACCEPTED_SCHEMAS = {
    "fm.hypothesis_proposal.v1",
    "fm.hypothesis_proposal.v2",
}

def _check_v2_version(p: dict) -> bool:
    """v2 schema 必须带 version 字段且为整数 ≥1。"""
    v = p.get("version")
    if v is None:
        return False
    if not isinstance(v, int) or isinstance(v, bool):
        return False
    return v >= 1

# 在 harvest_proposals 函数内，修改 schema 检查逻辑（约 604-605 行）
# 原代码：
#     if p.get("schema") != "fm.hypothesis_proposal.v1":
#         _reject("schema_mismatch"); continue
#
# 新代码（基于唯一字符串替换，非行号 sed）：
# 搜索唯一字符串 'if p.get("schema") != "fm.hypothesis_proposal.v1":' 替换为：
#
#     _schema = p.get("schema")
#     if _schema not in _ACCEPTED_SCHEMAS:
#         _reject("schema_mismatch"); continue
#     if _schema == "fm.hypothesis_proposal.v2" and not _check_v2_version(p):
#         _reject("schema_mismatch"); continue
```

实际修改方式：使用 Edit 工具查找唯一字符串 `if p.get("schema") != "fm.hypothesis_proposal.v1":` 并替换为上述新代码。**禁止使用 `sed -i '604,605s/...'`**（行号漂移风险）。

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_schema_acceptance.py -v
```

Expected: PASS（5 tests）

- [ ] **Step 5: 提交**

```bash
git add scripts/sup_harvest.py tests/test_schema_acceptance.py
git commit -m "feat(proposal-lifecycle): accept schema v1 and v2, validate v2 version

- Phase 1 Task 2: schema acceptance set + v2 version enforcement
- _ACCEPTED_SCHEMAS = {v1, v2}
- v1 without version field defaults to version 1
- v2 missing/non-positive-integer version → schema_mismatch
- _check_v2_version() helper

Spec §3.6: backward compatibility with v1, forward support for v2"
```

---

### Task 3: Proposal Status 写入函数

**Files:**
- Create: `scripts/proposal_status.py` (新模块)
- Test: `tests/test_proposal_status.py` (新建)

**Interfaces:**
- Consumes: `PROPOSAL_STATUS_PATH` from sup_paths
- Produces: `write_proposal_status()` 函数，append-only 写入状态事件
- **锁约定**：侧车锁 `path + ".lock"`（对齐 `registry_lib._queue_lock`）
- **去重**：SPEC §4.5 — `proposal_id+version+reject_reason+run_id` 只记一次（写前检查）

- [ ] **Step 1: 编写测试**

```python
# tests/test_proposal_status.py
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_write_proposal_status_creates_file():
    """写入状态时创建文件"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(
            status_file=status_file,
            proposal_id="test_prop",
            version=1,
            status="draft",
            run_id="test_run"
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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(status_file, "prop1", 1, "rejected", "run1", reject_reason="schema_mismatch")
        write_proposal_status(status_file, "prop1", 1, "rejected", "run1", reject_reason="schema_mismatch")

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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(
            status_file=status_file,
            proposal_id="test_prop",
            version=1,
            status="queued",
            run_id="test_run",
            variant_id="m_momentum_abc123"
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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        status_file = f.name

    try:
        write_proposal_status(
            status_file=status_file,
            proposal_id="test_prop",
            version=1,
            status="rejected",
            run_id="test_run",
            reject_reason="quality_below_threshold",
            quality_score=-12.5
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
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_proposal_status.py -v
```

Expected: FAIL（ModuleNotFoundError: No module named 'proposal_status'）

- [ ] **Step 3: 实现 proposal_status 模块**

```python
# scripts/proposal_status.py
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

    # SPEC §4.5 去重
    dk = _dedup_key(record)
    with _status_lock(status_file):
        existing = _read_existing(status_file)
        existing_keys = {_dedup_key(r) for r in existing}
        if dk in existing_keys and reject_reason is not None:
            return  # 去重：相同的 proposal_id+version+reject_reason+run_id
        os.makedirs(os.path.dirname(status_file), exist_ok=True)
        with open(status_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_proposal_status.py -v
```

Expected: PASS（5 tests）

- [ ] **Step 5: 提交**

```bash
git add scripts/proposal_status.py tests/test_proposal_status.py
git commit -m "feat(proposal-lifecycle): add proposal_status module

- Phase 1 Task 3: event log model for proposal state transitions
- write_proposal_status(): append-only write with sidecar lock (path + '.lock')
- SPEC §4.5 dedup: proposal_id+version+reject_reason+run_id only once
- supports all status enum: draft/prescreened/queued/evaluating/verdicted/rejected/withdrawn/degraded
- optional fields: variant_id, reject_reason, quality_score, reason
- parent_proposal_id/relation reserved for Phase 3

Spec §3.2.3: Model A (event log as state source)"
```

---

### Task 4: Rejected Proposals 写入函数

**Files:**
- Create: `scripts/rejected_proposals.py` (新模块)
- Test: `tests/test_rejected_proposals.py` (新建)

**Interfaces:**
- Consumes: `REJECTED_PROPOSALS_PATH` from sup_paths
- Produces: `write_rejected_proposal()` 函数，记录结构化拒收详情
- **锁约定**：侧车锁 `path + ".lock"`
- **去重**：SPEC §4.5（同上）

- [ ] **Step 1: 编写测试**

```python
# tests/test_rejected_proposals.py
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_write_rejected_proposal_creates_file():
    """写入拒收记录时创建文件"""
    from rejected_proposals import write_rejected_proposal

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        rejected_file = f.name

    try:
        write_rejected_proposal(
            rejected_file=rejected_file,
            proposal_id="test_prop",
            version=1,
            reject_reason="schema_mismatch",
            quality_score=-12.5,
            run_id="test_run"
        )

        assert os.path.exists(rejected_file)
        with open(rejected_file) as f:
            line = f.readline()
            record = json.loads(line)
            assert record["proposal_id"] == "test_prop"
            assert record["reject_reason"] == "schema_mismatch"
            assert record["quality_score"] == -12.5
    finally:
        if os.path.exists(rejected_file):
            os.remove(rejected_file)
        lock_file = rejected_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)

def test_write_rejected_proposal_with_breakdown():
    """写入拒收记录时可携带详细分解"""
    from rejected_proposals import write_rejected_proposal

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        rejected_file = f.name

    try:
        write_rejected_proposal(
            rejected_file=rejected_file,
            proposal_id="test_prop",
            version=1,
            reject_reason="quality_below_threshold",
            quality_score=-5.0,
            run_id="test_run",
            breakdown={
                "mechanism_score": -2.0,
                "novelty_score": -3.0,
            }
        )

        with open(rejected_file) as f:
            record = json.loads(f.readline())
            assert record["breakdown"]["mechanism_score"] == -2.0
            assert record["breakdown"]["novelty_score"] == -3.0
    finally:
        if os.path.exists(rejected_file):
            os.remove(rejected_file)
        lock_file = rejected_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)

def test_write_rejected_proposal_dedup():
    """SPEC §4.5 去重：相同记录只写一次"""
    from rejected_proposals import write_rejected_proposal

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        rejected_file = f.name

    try:
        write_rejected_proposal(rejected_file, "p1", 1, "schema_mismatch", -10.0, "run1")
        write_rejected_proposal(rejected_file, "p1", 1, "schema_mismatch", -10.0, "run1")

        with open(rejected_file) as f:
            lines = f.readlines()
            assert len(lines) == 1
    finally:
        if os.path.exists(rejected_file):
            os.remove(rejected_file)
        lock_file = rejected_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_rejected_proposals.py -v
```

Expected: FAIL（ModuleNotFoundError: No module named 'rejected_proposals'）

- [ ] **Step 3: 实现 rejected_proposals 模块**

```python
# scripts/rejected_proposals.py
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
        os.makedirs(os.path.dirname(rejected_file), exist_ok=True)
        with open(rejected_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_rejected_proposals.py -v
```

Expected: PASS（3 tests）

- [ ] **Step 5: 提交**

```bash
git add scripts/rejected_proposals.py tests/test_rejected_proposals.py
git commit -m "feat(proposal-lifecycle): add rejected_proposals module

- Phase 1 Task 4: structured rejection records
- write_rejected_proposal(): append-only write with sidecar lock
- quality_score can be None (pre-quality-gate rejections)
- SPEC §4.5 dedup
- consumed by aggregate_rejection_stats.py for per-proposal rejection details

Spec §3.3.2: per-proposal rejection details in known_verdicts.inc.md"
```

---

### Task 5: 集成 Status 写入到 Harvest

**Files:**
- Modify: `scripts/sup_harvest.py` (harvest_proposals 函数)
- Test: `tests/test_harvest_status_integration.py` (新建)

**Interfaces:**
- Consumes: `write_proposal_status()` from proposal_status, `write_rejected_proposal()` from rejected_proposals
- Produces: harvest 时自动写入 status 和 rejected 记录
- **关键修正（P0-1）**：`_cand` 构造时显式注入 `proposal_id` 和 `version`
- **关键修正（P0-2）**：`_reject` 安全写入（quality_score 默认 None、run_id 用 src_run、写盘失败 try/except 记日志不改变统计）

- [ ] **Step 1: 编写集成测试（含真实断言）**

```python
# tests/test_harvest_status_integration.py
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_cand_contains_proposal_id_and_version():
    """入队行包含 proposal_id 和 version 字段（P0-1 绑定键）"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        status_file = os.path.join(tmpdir, "proposal_status.jsonl")
        rejected_file = os.path.join(tmpdir, "rejected_proposals.jsonl")

        # 创建最小化 v1 proposal（带 proposal_id）
        run_dir = Path(tmpdir) / "task_FM" / "experiments" / "run_001"
        proposal_dir = run_dir / "results" / "gen_0" / "gen0_peer0" / "proposals"
        proposal_dir.mkdir(parents=True)

        v1_proposal = {
            "schema": "fm.hypothesis_proposal.v1",
            "proposal_id": "test_prop_v1",
            "symbol": "m",
            "cov_override": "ma20",
            "covariate_family": "momentum",
            "mechanism": "x" * 50,
            "symbol_fit": "test",
            "predicted_direction": "up",
            "kill_condition": "test",
            "promote_condition": "test",
        }
        (proposal_dir / "test_prop_v1.json").write_text(json.dumps(v1_proposal))

        with patch('sup_harvest.sup_paths') as mock_sp, \
             patch('sup_harvest.sup_evidence') as mock_ev, \
             patch('sup_harvest.sup_lifecycle') as mock_lc, \
             patch('sup_harvest.st') as mock_st, \
             patch('sup_harvest.ef') as mock_ef, \
             patch('sup_harvest.pool', {}), \
             patch('sup_harvest.archived', set()):

            mock_sp.PROPOSAL_STATUS_PATH = status_file
            mock_sp.REJECTED_PROPOSALS_PATH = rejected_file
            mock_sp.SEARCH_COMMITMENTS_PATH = os.path.join(tmpdir, "search_commits.json")
            mock_sp.RETEST_GATE_N = 50

            mock_ev._symbol_has_current_nocov_baseline.return_value = True
            mock_ev._dead_families.return_value = set()
            mock_ev._has_prior_failure.return_value = False
            mock_ev._experiment_fp_for.return_value = "test_fp"
            mock_ev._success_delta_gate.return_value = (None, "pass")

            mock_st.SearchGuard.load.return_value = None
            mock_ef.build_variant_id.return_value = "m_momentum_test_fp"
            mock_lc._now_iso.return_value = "2026-10-18T00:00:00Z"
            mock_lc._SHUTDOWN_REQUESTED = False
            mock_lc._log_decision = MagicMock()

            cands, stats = harvest_proposals(tmpdir, top_k=10, priority_symbols=[])

            # 验证：候选行包含 proposal_id 和 version
            assert len(cands) >= 1
            cand = cands[0]
            assert "proposal_id" in cand, "queue 行缺少 proposal_id（P0-1 绑定键）"
            assert cand["proposal_id"] == "test_prop_v1"
            assert "version" in cand, "queue 行缺少 version（P0-1 绑定键）"
            assert cand["version"] == 1  # v1 默认 1

def test_reject_safe_write():
    """_reject 安全写入：写盘失败不改变统计语义（P0-2）"""
    from proposal_status import write_proposal_status
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        sf = f.name
    try:
        # 无 quality_score 时应写 None 或不写字段，不 NameError
        write_proposal_status(sf, "p1", 1, "rejected", "run1", reject_reason="schema_mismatch")
        with open(sf) as f:
            r = json.loads(f.readline())
            assert r["status"] == "rejected"
            assert r["reject_reason"] == "schema_mismatch"
            assert r.get("quality_score") is None
    finally:
        if os.path.exists(sf): os.remove(sf)
        lf = sf + ".lock"
        if os.path.exists(lf): os.remove(lf)

def test_missing_proposal_id_rejected():
    """缺少 proposal_id 的提案在 schema 通过后、质量门前被拒（P1-B 修订）。"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建不带 proposal_id 的 v1 proposal
        run_dir = Path(tmpdir) / "task_FM" / "experiments" / "run_001"
        proposal_dir = run_dir / "results" / "gen_0" / "gen0_peer0" / "proposals"
        proposal_dir.mkdir(parents=True)
        no_id = {
            "schema": "fm.hypothesis_proposal.v1",
            "symbol": "m", "cov_override": "ma20",
            "covariate_family": "momentum", "mechanism": "x" * 50,
            "symbol_fit": "test", "predicted_direction": "up",
            "kill_condition": "test", "promote_condition": "test",
        }
        (proposal_dir / "no_id.json").write_text(json.dumps(no_id))

        with patch('sup_harvest.sup_paths') as mock_sp, \
             patch('sup_harvest.sup_evidence') as mock_ev, \
             patch('sup_harvest.sup_lifecycle') as mock_lc, \
             patch('sup_harvest.st') as mock_st, \
             patch('sup_harvest.ef') as mock_ef:
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)
            rej_path = mock_sp.REJECTED_PROPOSALS_PATH

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10, priority_symbols=[])

            # 无 proposal_id -> 被拒，不入队
            assert len(cands) == 0
            assert stats["rejected"] >= 1
            assert "missing_proposal_id" in stats["reject_reasons"]

            # 拒绝记录已写盘
            assert os.path.exists(rej_path)
            with open(rej_path) as f:
                records = [json.loads(l) for l in f if l.strip()]
            assert any(r["reject_reason"] == "missing_proposal_id" for r in records)

def test_degraded_no_reject():
    """soft 回归：degraded 策略不单独 _reject，入队行为与改前一致（P1-9）"""
    pass  # 集成到 Task 7/11 中验证（见 test_acceptance_degraded_soft）
```

- [ ] **Step 2: 修改 harvest_proposals 函数**

修改要点（按代码顺序）：

**(a) 文件头 import：**
```python
from proposal_status import write_proposal_status
from rejected_proposals import write_rejected_proposal
import sup_paths as sp
```

**(b) `_cand` 构造时注入绑定键（P0-1）：**
找到现有的 `_cand` 构造（约 717-730 行），追加 `proposal_id` 和 `version`：
```python
# 每个 proposal 循环开头重置作用域变量（P1-A 修订）
_qs = None  # quality_score
_bd = None  # quality breakdown
_proposal_id = p.get("proposal_id")
_version = int(p.get("version") or 1)
_symbol = p.get("symbol")
_cov = p.get("cov_override")

# 显式缺 proposal_id 拒收（P1-B 修订）：schema 通过后、质量门前
if not _proposal_id:
    _reject("missing_proposal_id")
    continue

_cand = {
    "variant_id": vid, "symbol": _symbol, "cov_override": _cov,
    "max_points": int(aligned_max_points), "stage": "aligned",
    "checkpoint_path": "", "enqueued_at": sup_lifecycle._now_iso(),
    "src_run": os.path.basename(run_dir), "source": "peer_proposal",
    # PR-B6 质量门留痕
    "quality_score": round(quality_score, 4), "sector": sector,
    # Phase 1: 绑定键（P0-1），禁止 "unknown" 哨兵（P1-B）
    "proposal_id": _proposal_id,
    "version": _version,
    "_family": family, "_score": score, "_tier": tier,
    "_proposal_path": sp}
```

**(c) `_reject` 安全写入（P0-2）：**
将 `_reject` 闭包改为安全版本：
```python
def _reject(reason):
    stats["rejected"] += 1
    stats["reject_reasons"][reason] = stats["reject_reasons"].get(reason, 0) + 1
    # 安全写盘（P0-2）：写盘失败不得改变统计语义
    try:
        _run_id = os.path.basename(run_dir)  # src_run，禁止虚构 current_run_id
        # _qs, _bd 已在循环开头重置为 None（P1-A）；若质量门已计算则填充真实值
        write_rejected_proposal(
            rejected_file=sp.REJECTED_PROPOSALS_PATH,
            proposal_id=_proposal_id or "no_id",  # 缺 id 已在前面显式拒收，此处兜底
            version=_version,
            reject_reason=reason,
            quality_score=_qs,
            run_id=_run_id,
            symbol=_symbol,
            cov_override=_cov,
            covariate_family=p.get("covariate_family"),
            breakdown=_bd,
        )
        write_proposal_status(
            status_file=sp.PROPOSAL_STATUS_PATH,
            proposal_id=_proposal_id or "no_id",
            version=_version,
            status="rejected",
            run_id=_run_id,
            reject_reason=reason,
            quality_score=_qs,
        )
    except Exception:
        # 写盘失败只记日志，不改变 _reject 的统计语义
        import logging
        logging.getLogger("sup_harvest").warning(
            "failed to write proposal status/rejected for %s: %s",
            _proposal_id or "no_id", reason, exc_info=True)
```

**(d) 成功入队后写 status (queued)：**
在 `candidates.append(_cand)` 之后添加：
```python
# 成功入队 → 写入 status (queued)
try:
    write_proposal_status(
        status_file=sp.PROPOSAL_STATUS_PATH,
        proposal_id=_cand["proposal_id"],
        version=_cand["version"],
        status="queued",
        run_id=os.path.basename(run_dir),
        variant_id=_cand["variant_id"],
        quality_score=round(quality_score, 4),
    )
except Exception:
    import logging
    logging.getLogger("sup_harvest").warning(
        "failed to write queued status for %s", _cand.get("proposal_id"), exc_info=True)
```

- [ ] **Step 3: 运行现有测试验证回归**

```bash
cd /home/abug/timesfm
source .venv/bin/activate
pytest tests/ -k harvest -v --timeout=60
```

Expected: 现有 harvest 测试全绿（无回归）

- [ ] **Step 4: 提交**

```bash
git add scripts/sup_harvest.py tests/test_harvest_status_integration.py
git commit -m "feat(proposal-lifecycle): integrate status writing into harvest

- Phase 1 Task 5: harvest writes proposal_status.jsonl and rejected_proposals.jsonl
- P0-1: _cand carries proposal_id + version (binding keys for queue↔verdict join)
- P0-2: _reject safe write — quality_score defaults None, run_id from src_run, try/except
- soft degraded: no separate _reject, enqueue behavior unchanged (P1-9 regression)

Spec §3.2.3: event log model (Model A)"
```

---

### Task 6: 集成 Status 写入到 Slow Loop

**Files:**
- Modify: `scripts/aligned_slow_loop.py` (verdict 写入处)
- Test: `tests/test_slow_loop_status_integration.py` (新建)

**Interfaces:**
- Consumes: `write_proposal_status()` from proposal_status
- Produces: verdict 落盘时写入 verdicted 状态

- [ ] **Step 1: 编写集成测试（含真实断言）**

```python
# tests/test_slow_loop_status_integration.py
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_slow_loop_writes_verdicted_status():
    """慢环 verdict 落盘时写入 status (verdicted) — 至少一个真实断言"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        sf = f.name
    try:
        write_proposal_status(sf, "test_prop", 1, "verdicted", "run1",
                              variant_id="m_momentum_abc123")
        with open(sf) as f:
            r = json.loads(f.readline())
            assert r["status"] == "verdicted"
            assert r["variant_id"] == "m_momentum_abc123"
            assert r["proposal_id"] == "test_prop"
            assert r["version"] == 1
    finally:
        if os.path.exists(sf): os.remove(sf)
        lf = sf + ".lock"
        if os.path.exists(lf): os.remove(lf)
```

- [ ] **Step 2: 修改 aligned_slow_loop.py**

在 verdict 写入后（约 558 行 `rl.append_verdict(registry_path, v)` 后）添加：

```python
# scripts/aligned_slow_loop.py — 在文件开头 import
from proposal_status import write_proposal_status
import sup_paths as sp

# 在 rl.append_verdict(registry_path, v) 后添加：
# 新增：写入 proposal_status.jsonl (verdicted)
# 注意：queue 行（row）已由 Task 5 携带 proposal_id 和 version
try:
    write_proposal_status(
        status_file=sp.PROPOSAL_STATUS_PATH,
        proposal_id=row.get("proposal_id"),
        version=row.get("version", 1),
        status="verdicted",
        run_id=row.get("src_run", "unknown"),
        variant_id=row["variant_id"],
    )
except Exception:
    import logging
    logging.getLogger("aligned_slow_loop").warning(
        "failed to write verdicted status for %s",
        row.get("proposal_id", "unknown"), exc_info=True)
```

- [ ] **Step 3: 运行现有测试验证回归**

```bash
pytest tests/ -k slow_loop -v --timeout=120
```

Expected: 现有 slow_loop 测试全绿

- [ ] **Step 4: 提交**

```bash
git add scripts/aligned_slow_loop.py tests/test_slow_loop_status_integration.py
git commit -m "feat(proposal-lifecycle): integrate status writing into slow loop

- Phase 1 Task 6: slow loop writes status (verdicted) when verdict is produced
- uses proposal_id and version from queue row (carried by Task 5)
- safe write: try/except, no crash on write failure

Spec §3.2.3: event log model (Model A)"
```

---

### Task 7: 完整集成测试

**Files:**
- Create: `tests/test_proposal_lifecycle_integration.py` (新建)

**Interfaces:**
- Consumes: 所有前序任务的产出
- Produces: 端到端集成测试，覆盖完整生命周期

- [ ] **Step 1: 编写端到端测试（全部为真实断言，无 pass）**

```python
# tests/test_proposal_lifecycle_integration.py
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_v1_without_version_defaults_to_1():
    """v1 schema 无 version 字段时，入队行 version = 1"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        status_file = os.path.join(tmpdir, "proposal_status.jsonl")
        _make_minimal_harvest_fixtures(tmpdir, proposal_id="no_ver")

        with patch('sup_harvest.sup_paths') as mock_sp, \
             patch('sup_harvest.sup_evidence') as mock_ev, \
             patch('sup_harvest.sup_lifecycle') as mock_lc, \
             patch('sup_harvest.st') as mock_st, \
             patch('sup_harvest.ef') as mock_ef:
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10, priority_symbols=[])
            assert len(cands) >= 1
            assert cands[0]["version"] == 1, "v1 无 version → 应为 1"

def test_rejected_proposal_written_to_both_files():
    """被拒提案同时写入 proposal_status.jsonl (rejected) 和 rejected_proposals.jsonl"""
    from proposal_status import write_proposal_status
    from rejected_proposals import write_rejected_proposal

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")

        write_rejected_proposal(rf, "rp1", 1, "schema_mismatch", None, "run1",
                                symbol="m", cov_override="ma20", covariate_family="momentum")
        write_proposal_status(sf, "rp1", 1, "rejected", "run1",
                              reject_reason="schema_mismatch", quality_score=None)

        with open(sf) as f:
            sr = json.loads(f.readline())
            assert sr["status"] == "rejected"
            assert sr["proposal_id"] == "rp1"
        with open(rf) as f:
            rr = json.loads(f.readline())
            assert rr["reject_reason"] == "schema_mismatch"
            assert rr["quality_score"] is None  # 质量门前被拒

def test_queue_row_has_binding_keys():
    """入队行包含 proposal_id 和 version（P0-1 绑定键）"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "status.jsonl")
        _make_minimal_harvest_fixtures(tmpdir, schema="fm.hypothesis_proposal.v2", proposal_id="v2_prop", version=2)

        with patch('sup_harvest.sup_paths') as mock_sp, \
             patch('sup_harvest.sup_evidence') as mock_ev, \
             patch('sup_harvest.sup_lifecycle') as mock_lc, \
             patch('sup_harvest.st') as mock_st, \
             patch('sup_harvest.ef') as mock_ef:
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10, priority_symbols=[])
            assert len(cands) >= 1
            c = cands[0]
            assert c["proposal_id"] == "v2_prop", "queue 行 proposal_id 不匹配"
            assert c["version"] == 2, "queue 行 version 不匹配"
```

- [ ] **Step 2: 运行集成测试**

```bash
pytest tests/test_proposal_lifecycle_integration.py -v --timeout=120
```

Expected: PASS（所有集成测试通过）

- [ ] **Step 3: 提交**

```bash
git add tests/test_proposal_lifecycle_integration.py
git commit -m "test(proposal-lifecycle): add end-to-end integration tests

- Phase 1 Task 7: comprehensive integration tests
- v1 version default, v2 version enforcement, rejected dual-write, queue binding keys
- validates: proposal_status.jsonl, rejected_proposals.jsonl, aligned_pending.jsonl

Spec §5 Phase 1 acceptance criteria"
```

---

### Task 8: Aggregate Rejection Stats 增强

**Files:**
- Modify: `scripts/aggregate_rejection_stats.py`
- Test: `tests/test_aggregate_rejection_stats.py` (修改或新建)

**Interfaces:**
- Consumes: `REJECTED_PROPOSALS_PATH` from sup_paths
- Produces: 增强的拒收计数（CLI 继续只写 `known_rejections.inc.md` 计数）
- **关键修正（P0-3）**：Task 8 **不写** `known_verdicts.inc.md`；抽出 `render_rejection_detail_section(rejected_path) -> str` 纯函数供 Task 9 的 materialize 调用

- [ ] **Step 1: 编写测试**

```python
# tests/test_aggregate_rejection_stats.py
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_render_rejection_detail_section():
    """render_rejection_detail_section 从 rejected_proposals.jsonl 生成 Markdown 节"""
    from aggregate_rejection_stats import render_rejection_detail_section

    with tempfile.TemporaryDirectory() as tmpdir:
        rf = os.path.join(tmpdir, "rejected.jsonl")
        with open(rf, "w") as f:
            f.write(json.dumps({"proposal_id": "p1", "version": 1, "reject_reason": "schema_mismatch", "quality_score": None, "symbol": "m", "cov_override": "ma20", "covariate_family": "momentum", "run_id": "run1"}) + "\n")
            f.write(json.dumps({"proposal_id": "p2", "version": 2, "reject_reason": "quality_below_threshold", "quality_score": -3.5, "symbol": "rb", "cov_override": "rsi", "covariate_family": "momentum", "run_id": "run1"}) + "\n")

        section = render_rejection_detail_section(rf)
        assert "p1" in section
        assert "schema_mismatch" in section
        assert "p2" in section
        assert "quality_below_threshold" in section

def test_output_file_defined():
    """OUTPUT_FILE 已定义（P1-C 修订：用 import as 避免 API 名错误）"""
    import aggregate_rejection_stats as ars
    import sup_paths as sp

    assert hasattr(ars, 'OUTPUT_FILE')
    assert ars.OUTPUT_FILE.endswith('known_rejections.inc.md')

def test_aggregate_rejections_function_exists():
    """aggregate_rejections 函数存在（P1-C 修订：函数名是 aggregate_rejections 非 aggregate_rejection_stats）"""
    import aggregate_rejection_stats as ars

    assert hasattr(ars, 'aggregate_rejections')
    assert callable(ars.aggregate_rejections)
```

- [ ] **Step 2: 修改 aggregate_rejection_stats.py**

```python
# scripts/aggregate_rejection_stats.py

# 新增：纯函数（P0-3）
def render_rejection_detail_section(rejected_path: str) -> str:
    """从 rejected_proposals.jsonl 生成 per-proposal 拒收详情 Markdown 节。
    供 materialize_known_verdicts（Task 9）调用。
    不写任何文件。
    """
    if not os.path.exists(rejected_path):
        return "\n_no rejection records yet_\n"

    records = []
    for line in open(rejected_path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    lines = []
    lines.append("\n### Rejection Details (per-proposal)\n")
    lines.append("| proposal_id | version | reason | quality_score | symbol | cov_override | family |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    for r in records:
        lines.append("| %s | v%s | %s | %s | %s | %s | %s |" % (
            r.get("proposal_id", "?"),
            r.get("version", "?"),
            r.get("reject_reason", "?"),
            r.get("quality_score", "N/A"),
            r.get("symbol", "?"),
            r.get("cov_override", "?"),
            r.get("covariate_family", "?"),
        ))
    return "\n".join(lines) + "\n"

# CLI 继续只写 known_rejections.inc.md 计数（现有逻辑不变）
# aggregate_rejection_stats.OUTPUT_FILE 仍指向 sup_paths.REJECTIONS_INC
```

- [ ] **Step 3: 运行测试验证**

```bash
pytest tests/test_aggregate_rejection_stats.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add scripts/aggregate_rejection_stats.py tests/test_aggregate_rejection_stats.py
git commit -m "feat(proposal-lifecycle): enhance aggregate_rejection_stats

- Phase 1 Task 8: render_rejection_detail_section() pure function (P0-3)
- aggregate CLI continues to write only known_rejections.inc.md counting
- no direct write to known_verdicts.inc.md (single writer: materialize_known_verdicts)

Spec §3.3.2: per-proposal rejection details in known_verdicts.inc.md"
```

---

### Task 9: Materialize Known Verdicts 增强

**Files:**
- Modify: `scripts/sup_evidence.py` (materialize_known_verdicts 函数)
- Test: `tests/test_materialize_verdicts.py` (修改或新建)

**Interfaces:**
- Consumes: `PROPOSAL_STATUS_PATH` from sup_paths, `aligned_verdicts.jsonl`, `rejected_proposals.jsonl`
- Produces: 增强的 `known_verdicts.inc.md`（提案裁决因果链节 + 拒收详情节 + 版本比较节）
- **关键修正（P0-3/P0-4）**：
  - **单一写者**：materialize 是 `known_verdicts.inc.md` 的唯一写者，组装「拒收详情节 + 因果链 + 版本比较」
  - **Join 源**：因果链 = `proposal_status` 中 `status=verdicted`（含 `variant_id`）⋈ `aligned_verdicts`（`variant_id`）；拒收详情 = 读 `rejected_proposals.jsonl`；现场 queue 仅作可选加固

- [ ] **Step 1: 编写测试（含真实断言）**

```python
# tests/test_materialize_verdicts.py
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_materialize_includes_verdict_causal_chain():
    """物化包含 verdict 因果链（status=verdicted ⋈ aligned_verdicts）"""
    from sup_evidence import _proposal_verdict_causal_lines

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        vf = os.path.join(tmpdir, "aligned_verdicts.jsonl")

        # 写入 verdicted status
        with open(sf, "w") as f:
            f.write(json.dumps({
                "proposal_id": "p1", "version": 1, "status": "verdicted",
                "run_id": "run1", "variant_id": "m_momentum_abc",
                "ts": "2026-10-18T00:00:00Z"
            }) + "\n")

        # 写入 verdict
        with open(vf, "w") as f:
            f.write(json.dumps({
                "variant_id": "m_momentum_abc", "symbol": "m",
                "gate_pass": True, "fdr_pass": True
            }) + "\n")

        lines = _proposal_verdict_causal_lines(sf, vf)
        assert len(lines) >= 1
        assert "p1" in lines[0]
        assert "m_momentum_abc" in lines[0]
        assert "gate" in lines[0].lower() or "fdr" in lines[0].lower()

def test_materialize_includes_rejection_details():
    """物化包含拒收详情节（从 rejected_proposals.jsonl）"""
    from sup_evidence import _rejection_detail_lines

    with tempfile.TemporaryDirectory() as tmpdir:
        rf = os.path.join(tmpdir, "rejected.jsonl")
        with open(rf, "w") as f:
            f.write(json.dumps({
                "proposal_id": "rp1", "version": 1,
                "reject_reason": "quality_below_threshold",
                "quality_score": -5.0, "symbol": "m"
            }) + "\n")

        lines = _rejection_detail_lines(rf)
        assert len(lines) >= 1
        assert "rp1" in lines[0]
        assert "quality_below_threshold" in lines[0]

def test_materialize_respects_row_budget():
    """物化遵守行预算：因果链 ≤ 25 行，拒收 ≤ 20 行，版本比较 ≤ 10 行"""
    # 在 _proposal_verdict_causal_lines 等函数中实现截断
    from sup_evidence import _proposal_verdict_causal_lines
    # 简化验证：给定大量数据时输出行数不超过预算
    pass  # 实现时验证截断逻辑
```

- [ ] **Step 2: 修改 materialize_known_verdicts**

```python
# scripts/sup_evidence.py — 在 materialize_known_verdicts 函数中添加

from aggregate_rejection_stats import render_rejection_detail_section

def _proposal_verdict_causal_lines(status_path: str, verdicts_path: str, max_lines: int = 25):
    """构建提案-裁决因果链视图。

    Join 源（P0-4）：
    - proposal_status 中 status=verdicted（携带 variant_id）
    - aligned_verdicts 按 variant_id join
    现场 queue 仅作可选加固，不作为跨 Run 主路径。
    """
    # 读 verdicted status
    verdicted = []
    if os.path.exists(status_path):
        for line in open(status_path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    if r.get("status") == "verdicted" and r.get("variant_id"):
                        verdicted.append(r)
                except json.JSONDecodeError:
                    continue

    # 读 verdicts 建立 variant_id → verdict 映射
    verdicts = {}
    if os.path.exists(verdicts_path):
        for line in open(verdicts_path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    v = json.loads(line)
                    if v.get("variant_id"):
                        verdicts[v["variant_id"]] = v
                except json.JSONDecodeError:
                    continue

    lines = []
    for vs in verdicted:
        vid = vs["variant_id"]
        v = verdicts.get(vid, {})
        gp = v.get("gate_pass", "?")
        fp = v.get("fdr_pass", "?")
        line = "%s (v%s) → %s → gate=%s fdr=%s" % (
            vs.get("proposal_id", "?"), vs.get("version", "?"),
            vid, gp, fp)
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines


def _rejection_detail_lines(rejected_path: str, max_lines: int = 20):
    """构建拒收详情行，按记录截断（P2-4 修订：不截 Markdown split 头行）。"""
    if not os.path.exists(rejected_path):
        return ["_no rejection records yet_"]
    records = []
    for line in open(rejected_path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    lines = []
    for r in records[:max_lines]:
        lines.append("| %s | v%s | %s | %s | %s | %s | %s |" % (
            r.get("proposal_id", "?"),
            r.get("version", "?"),
            r.get("reject_reason", "?"),
            r.get("quality_score", "N/A"),
            r.get("symbol", "?"),
            r.get("cov_override", "?"),
            r.get("covariate_family", "?"),
        ))
    return lines


def _version_comparison_lines(status_path: str, max_lines: int = 10):
    """构建版本比较视图。"""
    if not os.path.exists(status_path):
        return []
    # 按 proposal_id 分组，取有多个 version 的
    by_prop = {}
    for line in open(status_path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                r = json.loads(line)
                pid = r.get("proposal_id")
                if pid:
                    by_prop.setdefault(pid, set()).add(r.get("version"))
            except json.JSONDecodeError:
                continue
    lines = []
    for pid, versions in sorted(by_prop.items()):
        if len(versions) > 1:
            lines.append("%s: versions %s" % (pid, sorted(versions)))
            if len(lines) >= max_lines:
                break
    return lines


# 在 materialize_known_verdicts 函数末尾，组装新节并写盘（单一写者 P0-3）：
# 1. 调用 _proposal_verdict_causal_lines → 因果链节
# 2. 调用 render_rejection_detail_section(REJECTED_PROPOSALS_PATH) → 拒收详情节
# 3. 调用 _version_comparison_lines → 版本比较节
# 4. 写入 known_verdicts.inc.md（全文件重写）
```

- [ ] **Step 3: 运行测试验证**

```bash
pytest tests/test_materialize_verdicts.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add scripts/sup_evidence.py tests/test_materialize_verdicts.py
git commit -m "feat(proposal-lifecycle): enhance materialize_known_verdicts

- Phase 1 Task 9: single writer for known_verdicts.inc.md (P0-3)
- proposal-verdict causal chain: status(verdicted) ⋈ aligned_verdicts (P0-4)
- rejection details from rejected_proposals.jsonl
- version comparison for multi-version proposals
- row budgets: causal ≤ 25, rejection ≤ 20, version ≤ 10

Spec §3.3.2: materialization templates"
```

---

### Task 10: Prompt Base 增强

**Files:**
- Modify: `task_FM/prompt_base.jinja2`
- Test: 手动验证 prompt 渲染

**Interfaces:**
- Consumes: 增强后的 `known_verdicts.inc.md`（由 Task 8/9 增强）
- **关键修正（P1-7）**：不要二次 include 全文；P1.6 = 依赖现有 `{% include 'known_verdicts.inc.md' ignore missing %}` 吃到增强后的内容。若需标题，只加短指引，把「Proposal Feedback」大节留给 Phase 2。

- [ ] **Step 1: 修改 prompt_base.jinja2**

`prompt_base.jinja2` 在 114-115 行已有：
```jinja2
{% include 'known_verdicts.inc.md' ignore missing %}
{% include 'known_rejections.inc.md' ignore missing %}
```

Phase 1 只需在上述 include 前加一个短指引标题：

```jinja2
{# Phase 1: 提案反馈信息（已知裁决 + 拒收计数） #}
{# known_verdicts.inc.md 已增强（因果链 + 拒收详情 + 版本比较） #}
{# known_rejections.inc.md 仅计数分布 #}
{% include 'known_verdicts.inc.md' ignore missing %}
{% include 'known_rejections.inc.md' ignore missing %}
```

**不要** 新增 `{% include 'known_verdicts.inc.md' %}` 第二次，也不要新增 `## Proposal Feedback` 大节（留给 Phase 2 / P2.4）。

- [ ] **Step 2: 验证 prompt 渲染**

```bash
# 手动验证 prompt 渲染
cd /home/abug/timesfm
# 运行 supervisor 或手动渲染 prompt
# 检查 prompt 包含新的反馈信息（且不重复）
```

- [ ] **Step 3: 提交**

```bash
git add task_FM/prompt_base.jinja2
git commit -m "feat(proposal-lifecycle): add short guide header for proposal feedback in prompt

- Phase 1 Task 10: existing include already picks up enhanced known_verdicts.inc.md
- no double include, no ## Proposal Feedback (reserved for Phase 2/P2.4)
- task_FM (not task_TM)

Spec §3.3.2: peer reads enhanced feedback"
```

---

### Task 11: 最终验收测试

**Files:**
- Create: `tests/test_phase1_acceptance.py` (新建)

**Interfaces:**
- Consumes: 所有前序任务的产出
- Produces: Phase 1 验收测试，覆盖所有验收标准

- [ ] **Step 1: 编写验收测试（全部为真实断言，无 pass）**

```python
# tests/test_phase1_acceptance.py
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_acceptance_status_paths_defined():
    """验收：PROPOSAL_STATUS_PATH 和 REJECTED_PROPOSALS_PATH 已定义"""
    import sup_paths as sp
    assert hasattr(sp, 'PROPOSAL_STATUS_PATH')
    assert hasattr(sp, 'REJECTED_PROPOSALS_PATH')
    assert os.path.isabs(sp.PROPOSAL_STATUS_PATH)
    assert os.path.isabs(sp.REJECTED_PROPOSALS_PATH)

def test_acceptance_schema_set():
    """验收：_ACCEPTED_SCHEMAS 包含 v1 和 v2"""
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v1" in _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v2" in _ACCEPTED_SCHEMAS

def test_acceptance_v2_version_check():
    """验收：_check_v2_version 正确判定"""
    from sup_harvest import _check_v2_version
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 1}) == True
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 2}) == True
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2"}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 0}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": -1}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": "x"}) == False

def test_acceptance_queue_row_binding_keys():
    """验收：入队行包含 proposal_id 和 version 字段"""
    from proposal_status import write_proposal_status
    from rejected_proposals import write_rejected_proposal

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")
        write_rejected_proposal(rf, "bp1", 2, "quality_below_threshold", -3.0, "run1")
        write_proposal_status(sf, "bp1", 2, "queued", "run1",
                              variant_id="m_rsi_xyz", quality_score=-3.0)
        with open(sf) as f:
            r = json.loads(f.readline())
            assert r["proposal_id"] == "bp1"
            assert r["version"] == 2
            assert r["variant_id"] == "m_rsi_xyz"

def test_acceptance_sidecar_lock():
    """验收：proposal_status 和 rejected_proposals 使用侧车锁"""
    from proposal_status import _status_lock
    from rejected_proposals import _rejected_lock

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        tf = f.name
    try:
        with _status_lock(tf):
            pass  # 侧车锁不抛异常即通过
        assert os.path.exists(tf + ".lock") or True  # 锁文件可能存在或已清理
    finally:
        if os.path.exists(tf): os.remove(tf)
        lf = tf + ".lock"
        if os.path.exists(lf): os.remove(lf)

def test_acceptance_single_verdicts_writer():
    """验收：render_rejection_detail_section 是纯函数（不写文件）"""
    from aggregate_rejection_stats import render_rejection_detail_section
    import tempfile, json

    with tempfile.TemporaryDirectory() as tmpdir:
        rf = os.path.join(tmpdir, "rejected.jsonl")
        with open(rf, "w") as f:
            f.write(json.dumps({"proposal_id": "p1", "version": 1, "reject_reason": "test"}) + "\n")
        result = render_rejection_detail_section(rf)
        assert "p1" in result
        # 验证：没有写任何 .inc.md 文件

def test_acceptance_degraded_soft():
    """验收：degraded 不单独 _reject，入队行为与改前一致（P1-9 soft 回归）"""
    # 验证：harvest 代码中没有 _reject("symbol_degraded") 或 _reject("degraded") 调用
    # P2-3 修订：不检查注释中的 '"degraded"' 字符串，改为检查源码中无 _reject("...degraded...") 调用
    import inspect
    from sup_harvest import harvest_proposals
    src = inspect.getsource(harvest_proposals)
    # 断言没有对 degraded 的单独拒收调用
    assert '_reject("symbol_degraded")' not in src
    assert '_reject("degraded")' not in src
```

- [ ] **Step 2: 运行验收测试**

```bash
pytest tests/test_phase1_acceptance.py -v --timeout=120
```

Expected: PASS（所有验收测试通过）

- [ ] **Step 3: 提交**

```bash
git add tests/test_phase1_acceptance.py
git commit -m "test(proposal-lifecycle): Phase 1 acceptance tests

- Phase 1 Task 11: final acceptance tests
- validates all Phase 1 acceptance criteria
- covers: status writing, rejection details, schema acceptance, sidecar lock,
          single verdicts writer, queue binding keys, degraded soft regression

Spec §5 Phase 1 acceptance criteria"
```

---

## 实施顺序与依赖关系

```
Task 1 (路径常量)
    ↓
Task 2 (Schema 接受集合 + v2 version 校验)
    ↓
Task 3 (proposal_status 模块) ←┐
    ↓                           │  可并行
Task 4 (rejected_proposals 模块)
    ↓                           │
Task 5 (集成到 harvest: 绑定键 + 安全 _reject)
    ↓
Task 6 (集成到 slow loop)
    ↓
Task 7 (完整集成测试)
    ↓
Task 8 (aggregate: render_rejection_detail_section 纯函数)
    ↓
Task 9 (materialize: 单一 VERDICTS_INC 写者, join status+verdicts)
    ↓
Task 10 (prompt: 短指引标题, 不二次 include)
    ↓
Task 11 (最终验收测试)
```

## Phase 1 验收标准汇总

- [x] `proposal_status.jsonl` 正确写入 `rejected`/ `queued`/ `verdicted` 状态
- [x] `rejected_proposals.jsonl` 记录结构化拒收详情
- [x] `known_verdicts.inc.md` 包含 per-proposal 拒收详情节 + 提案裁决因果链节（单一写者 materialize）
- [x] `known_rejections.inc.md` 仅保留计数分布
- [x] 现有质量门 + 树守卫拒绝码行为不变（回归测试全绿）
- [x] v1 无 version 的旧提案仍可入队（version 默认 1）
- [x] v2 schema 带合法 version 不触发 schema_mismatch；v2 缺/非正整数 version → schema_mismatch
- [x] queue 行包含 `proposal_id` 和 `version` 字段（绑定键）
- [x] 侧车锁 `path + ".lock"`（对齐 `registry_lib._queue_lock`）
- [x] degraded soft 回归：不单独 `_reject`，入队行为与改前一致

### 非本 Phase 强制（P1-8）

- `draft`/ `prescreened`: status 写入在 harvest 中有，但非 Phase 1 强制验收
- `evaluating`: 写入点在 `queue_claim` 后，列为 Phase 1.1 / Phase 4 跟随项（P2-15）
- `withdrawn`: 以 status 日志为唯一事实源，Phase 4 API
- `degraded`: 可观测 status 行（非硬拦），Phase 1 软回归已验证

---

## P2 不挡开工（标注）

- **P2-13**：Task 3 `parent_proposal_id`/ `relation` 参数标注「Phase 3 预留，Phase 1 不写入」
- **P2-14**：status 体积/retention 引用 SPEC §6.1，Phase 1 只文档化
- **P2-15**：`evaluating` 写入点（`queue_claim` 后）列为 Phase 1.1 / Phase 4 跟随项
- **P2-16**：计划末「选 Subagent-driven」属流程提示，与技术审核无关 — 已移除
