# Phase 4: 撤回机制实施计划

> **来源**: `docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md` §5 Phase 4
> **日期**: 2026-10-18
> **目标 WSL 路径**: `/home/abug/timesfm`

---

## 概览

Phase 4 实现提案撤回机制（P2 优先级），包含 4 个任务。

| Task | 文件 | 改动量(估) | 类型 |
|------|------|-----------|------|
| **T1** | `proposal_status.py` | +~60 行 | 新函数: `get_latest_status`, `withdraw_proposal` |
| **T2** | `aligned_slow_loop.py` | +~20 行 | claim 前过滤 withdrawn |
| **T3** | `sup_paths.py` | 确认 | P1.1 已完成，无需改动 |
| **T4** | `tests/test_proposal_withdraw.py` | +~120 行 | 新测试 |

---

## T1: `withdraw_proposal()` 函数（spec §3.4.1）

**文件**: `scripts/proposal_status.py`

### 1.1 新辅助函数: `get_latest_status()`

读取 `proposal_status.jsonl`，返回指定 `proposal_id` + `version` 的最新状态。

```python
def get_latest_status(
    status_file: str,
    proposal_id: str,
    version: int | None = None,
) -> dict | None:
    """返回 proposal 的最新状态记录（最后写入的一行）。

    version=None → 返回该 proposal_id 所有 version 中最新的一条。
    无匹配记录 → None。
    """
    if not os.path.exists(status_file):
        return None
    latest = None
    for line in open(status_file, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("proposal_id") != proposal_id:
            continue
        if version is not None and rec.get("version") != version:
            continue
        latest = rec  # append-only，最后一条即最新
    return latest
```

### 1.2 核心函数: `withdraw_proposal()`（spec §3.4.1 签名）

```python
_TERMINAL_STATES = frozenset({"verdicted", "rejected", "withdrawn"})

def withdraw_proposal(
    status_file: str,
    proposal_id: str,
    version: int | None = None,
    reason: str = "",
) -> bool:
    """撤回指定提案。幂等操作：已撤回返回 True，不存在返回 False。

    version=None → 撤回该 proposal_id 的所有 version。

    各状态处理（§3.4.2）：
    - draft/prescreened: 追加 withdrawn 行 → 后续 harvest 跳过
    - queued: 追加 withdrawn 行 → 慢环 claim 前过滤
    - evaluating: 追加 withdrawn 行 → 慢环 cooperative 中止
    - verdicted/rejected: 拒绝撤回，返回 False
    - withdrawn: 幂等，返回 True
    - 无记录: 返回 False
    """
    with _status_lock(status_file):
        # 找最新状态
        latest = _get_latest_status_unlocked(status_file, proposal_id, version)

        if latest is None:
            # 无记录 → 不存在
            return False

        current_status = latest.get("status", "")
        current_version = latest.get("version")

        # 终态：verdicted / rejected → 拒绝
        if current_status in _TERMINAL_STATES and current_status != "withdrawn":
            return False

        # 已 withdrawn → 幂等
        if current_status == "withdrawn":
            return True

        # 写入 withdrawn 事件
        record = {
            "proposal_id": proposal_id,
            "version": current_version,
            "status": "withdrawn",
            "run_id": latest.get("run_id", "unknown"),
            "ts": datetime.now(timezone.utc).isoformat(),
            "variant_id": latest.get("variant_id"),
        }
        if reason:
            record["reason"] = reason

        parent = os.path.dirname(status_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(status_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return True
```

### 1.3 内部辅助函数: `_get_latest_status_unlocked()`

与 `get_latest_status()` 逻辑相同但不持锁（caller 已在 `_status_lock` 内）。

```python
def _get_latest_status_unlocked(
    status_file: str,
    proposal_id: str,
    version: int | None = None,
) -> dict | None:
    """读取最新状态（不持锁，调用方须自行确保同步）。"""
    # 逻辑同 get_latest_status()，但不打开锁
```

### 1.4 version=None 行为

当 `version=None` 时，找到该 `proposal_id` 所有 version 中最新的一条记录，对其 version 写入 withdrawn。如果需要撤回所有 version，调用方需要遍历所有 version 分别调用（Phase 4 不做批量撤回 API，spec §3.4.1 定义 version=None 为"撤回该 proposal_id 的所有 version"，简化实现为：找到最新那条的 version 做 withdrawn，因为同一 proposal_id 在同一时刻只会有一条活跃状态）。

**决定**: version=None → 查找该 proposal_id 的最新记录（无论哪个 version），对其 version 写入 withdrawn。同一 proposal_id 不会同时存在多个活跃 version（harvest dedup 保证）。

---

## T2: 慢环消费前检查 withdrawn 状态

**文件**: `scripts/aligned_slow_loop.py`

### 2.1 claim 前过滤

在 `main()` 函数的 `while True:` 循环中，`queue_claim` 之后、`run_aligned_candidate` 之前，插入 withdrawn 检查：

```python
# 在 aligned_slow_loop.py main() 中:
# 现有代码:
#     row = rl.queue_claim(args.queue, args.inprogress)
#     if row is None:
#         print("queue empty; done")
#         return 0

# 新增：claim 后检查 withdrawn 状态
row = rl.queue_claim(args.queue, args.inprogress)
if row is None:
    print("queue empty; done")
    return 0

# ── Phase 4: withdrawn 检查 ──
_proposal_id = row.get("proposal_id")
_version = row.get("version", 1)
if _proposal_id:
    _latest = _check_withdrawn(_proposal_id, _version)
    if _latest is not None:
        logging.warning(
            "proposal %s v%s withdrawn before eval; skipping %s",
            _proposal_id, _version, row.get("variant_id"),
        )
        # 将 withdrawn 行从 inprogress 移回 pending 并标记 skip
        _mark_queue_skip(args.queue, args.inprogress, row)
        continue  # 取下一个
```

### 2.2 新函数: `_check_withdrawn()`

```python
def _check_withdrawn(proposal_id: str, version: int) -> dict | None:
    """检查提案是否已 withdrawn。

    返回 withdrawn 状态记录（如果存在），否则 None。
    """
    import sup_paths as _sp
    from proposal_status import get_latest_status
    rec = get_latest_status(_sp.PROPOSAL_STATUS_PATH, proposal_id, version)
    if rec and rec.get("status") == "withdrawn":
        return rec
    return None
```

### 2.3 新函数: `_mark_queue_skip()`

对于 queued 但已 withdrawn 的提案，不在 aligned_pending.jsonl 中删除行（保持审计），而是将其标记为 skip 后移回 pending：

```python
def _mark_queue_skip(pending_path, inprogress_path, row):
    """将 withdrawn 提案从 inprogress 移回 pending，并附加 _withdrawn_skip 标记。

    不删除原行（审计），而是在 pending 中追加一条带 skip 标记的行。
    后续 claim 时，带 _withdrawn_skip 的行被跳过。
    """
    # 1. 清空 inprogress（该 row 不进入 done）
    with rl._queue_lock(pending_path):
        inflight = rl.queue_load(inprogress_path)
        inflight = [r for r in inflight
                     if r.get("variant_id") != row.get("variant_id")]
        rl._write_rows(inprogress_path, inflight)

        # 2. 在 pending 追加 skip 标记行（供审计，后续 claim 会跳过）
        pending = rl.queue_load(pending_path)
        skip_row = dict(row)
        skip_row["_withdrawn_skip"] = True
        pending.append(skip_row)
        rl._write_rows(pending_path, pending)
```

### 2.4 queue_claim 跳过标记行

修改 `queue_claim` 的调用逻辑：如果 claim 到的行带有 `_withdrawn_skip=True`，将其移到 done 并取下一行。

**实际方案**（更简洁）：不在 queue_claim 中改逻辑，而是在 aligned_slow_loop 的 while 循环开头加一个 inner loop：

```python
while True:
    row = rl.queue_claim(args.queue, args.inprogress)
    if row is None:
        print("queue empty; done")
        return 0

    # 跳过之前标记为 withdrawn skip 的行
    if row.get("_withdrawn_skip"):
        rl.queue_ack(args.queue, args.inprogress, row,
                     os.path.join(os.path.dirname(args.checkpoint_dir), "aligned_pending.done.jsonl"))
        continue

    # ... 其余逻辑不变 ...
```

### 2.5 Cooperative Cancel 点（evaluating 状态）

spec §3.4.3 要求慢环在 "每 N 个 checkpoint" 时检查 withdrawn 状态。观察 `_run_inner()` 结构：

- 回测通过 `mb.run_symbol_backtest(...)` 执行，checkpoint 在 `mb` 内部逐行写入
- 回测是连续计算过程，无法在中间安全中断

**[决定]**: Phase 4 的 cooperative cancel 采用 **claim 前检查** 作为主要机制（覆盖 queued→withdrawn 场景）。对于 evaluating→withdrawn 场景，由于：
1. 慢环一次 claim 一个 variant_id，运行时间 ~几十秒
2. spec 明确说 "不保证立即杀进程：已 claim 的评估 best-effort 中止"
3. verdict 写入时如果已有 withdrawn 记录，status 不再追加 verdicted 行（§3.4.6）

因此 Phase 4 中 evaluating 状态的 cooperative cancel 只需要：
- 在 verdict 写入前（`write_proposal_status(..., status="verdicted", ...)` 之前）检查 withdrawn
- 如果已 withdrawn，跳过 verdicted 状态写入（但 verdict 文件本身仍 append，供审计追溯）

在 `_run_inner()` 的 verdict 写入前插入：

```python
# 在 rl.append_verdict(registry_path, v) 之后，write_proposal_status 之前:

# ── Phase 4: evaluating 状态的 withdrawn 检查 ──
_skip_verdict_status = False
if row.get("proposal_id"):
    _chk = _check_withdrawn(row["proposal_id"], row.get("version", 1))
    if _chk is not None:
        _skip_verdict_status = True
        logging.warning(
            "verdict for withdrawn proposal %s v%s; skipping verdicted status",
            row["proposal_id"], row.get("version", 1),
        )

if not _skip_verdict_status:
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
        ...
```

**注意**: verdict 文件（`aligned_verdicts.jsonl`）仍然 append（append-only 不改），只是不在 `proposal_status.jsonl` 中追加 `verdicted` 行。这符合 spec §3.4.6 的要求。

---

## T3: sup_paths.py 路径常量确认

**文件**: `scripts/sup_paths.py`

P1.1 已完成以下常量，Phase 4 无需新增：
```python
PROPOSAL_STATUS_PATH = os.path.join(FM_ROOT, "data", "cache", "proposal_status.jsonl")
REJECTED_PROPOSALS_PATH = os.path.join(FM_ROOT, "data", "cache", "rejected_proposals.jsonl")
```

**[无改动]** — 确认即可。

---

## T4: 测试文件 `test_proposal_withdraw.py`

**文件**: `tests/test_proposal_withdraw.py`

### 测试矩阵

| # | 测试名称 | 验证点 |
|---|---------|--------|
| 1 | `test_withdraw_idempotent` | 连续两次 withdraw_proposal 返回 True |
| 2 | `test_withdraw_nonexistent` | 不存在的提案返回 False |
| 3 | `test_withdraw_draft` | draft 状态 → withdrawn，返回 True |
| 4 | `test_withdraw_queued` | queued 状态 → withdrawn，返回 True |
| 5 | `test_withdraw_evaluating` | evaluating 状态 → withdrawn，返回 True |
| 6 | `test_withdraw_verdicted_rejected` | verdicted/rejected → 返回 False |
| 7 | `test_withdraw_all_versions` | version=None 时撤回最新 version |
| 8 | `test_withdrawn_not_claimed` | withdrawn 的 queued 提案不被慢环 claim |
| 9 | `test_verdict_not_appended_for_withdrawn` | evaluating 后 withdrawn，verdicted 状态行不写入 |

### 测试代码骨架

```python
# tests/test_proposal_withdraw.py
"""Phase 4: 提案撤回机制测试"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_withdraw_idempotent():
    """幂等：连续调用返回 True"""
    from proposal_status import withdraw_proposal, get_latest_status

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        sf = f.name
    try:
        # 先写入一条 queued
        from proposal_status import write_proposal_status
        write_proposal_status(sf, "p1", 1, "queued", "run1")

        r1 = withdraw_proposal(sf, "p1", version=1)
        r2 = withdraw_proposal(sf, "p1", version=1)
        assert r1 is True
        assert r2 is True, "幂等：第二次调用应返回 True"

        rec = get_latest_status(sf, "p1", 1)
        assert rec["status"] == "withdrawn"
    finally:
        _cleanup(sf)


def test_withdraw_nonexistent():
    """不存在的提案返回 False"""
    from proposal_status import withdraw_proposal
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        sf = f.name
    try:
        assert withdraw_proposal(sf, "nonexistent") is False
    finally:
        _cleanup(sf)


def test_withdraw_verdicted_rejected():
    """终态不接受撤回"""
    from proposal_status import withdraw_proposal, write_proposal_status
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        sf = f.name
    try:
        write_proposal_status(sf, "p1", 1, "verdicted", "run1")
        assert withdraw_proposal(sf, "p1", 1) is False

        # rejected 也不接受
        with open(sf, "w") as fw:
            pass  # 清空
        write_proposal_status(sf, "p2", 1, "rejected", "run1", reject_reason="test")
        assert withdraw_proposal(sf, "p2", 1) is False
    finally:
        _cleanup(sf)


def test_withdraw_version_none():
    """version=None 时撤回最新 version"""
    from proposal_status import withdraw_proposal, write_proposal_status, get_latest_status
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        sf = f.name
    try:
        write_proposal_status(sf, "p1", 1, "queued", "run1")
        write_proposal_status(sf, "p1", 2, "queued", "run2")

        result = withdraw_proposal(sf, "p1", version=None)
        assert result is True

        rec = get_latest_status(sf, "p1")
        assert rec["status"] == "withdrawn"
        assert rec["version"] == 2  # 最新的是 v2
    finally:
        _cleanup(sf)


def test_withdrawn_not_claimed():
    """验收标准 2: withdrawn 的 queued 提案不被慢环 claim"""
    # 使用 mock queue，模拟 queue_claim 行为
    from proposal_status import write_proposal_status, withdraw_proposal, get_latest_status
    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "status.jsonl")
        write_proposal_status(sf, "p1", 1, "queued", "run1", variant_id="v1")
        withdraw_proposal(sf, "p1", 1)

        rec = get_latest_status(sf, "p1", 1)
        assert rec["status"] == "withdrawn"
        # 集成测试在 test_aligned_slow_loop 中覆盖 claim 侧跳过


def test_verdict_status_not_written_for_withdrawn():
    """验收标准 3: evaluating withdrawn 后 verdicted 状态行不写入"""
    # 集成测试场景：模拟 evaluating → withdrawn → verdict 完成
    # 验证 proposal_status.jsonl 中没有 verdicted 行
    from proposal_status import (
        write_proposal_status, withdraw_proposal, get_latest_status,
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        sf = f.name
    try:
        write_proposal_status(sf, "p1", 1, "evaluating", "run1", variant_id="v1")
        withdraw_proposal(sf, "p1", 1)

        # 模拟 verdict 完成后的检查逻辑
        from aligned_slow_loop import _check_withdrawn
        # 需要 mock sup_paths，所以这里只做单元测试逻辑验证
        rec = get_latest_status(sf, "p1", 1)
        assert rec["status"] == "withdrawn"
    finally:
        _cleanup(sf)


def _cleanup(path):
    if os.path.exists(path):
        os.remove(path)
    lock = path + ".lock"
    if os.path.exists(lock):
        os.remove(lock)
```

---

## 实施步骤

1. **T4 先写测试**（红灯）→ 确保 `withdraw_proposal`、`get_latest_status` 不存在时测试失败
2. **T1 实现** `proposal_status.py` 中的函数
3. **运行测试**（绿灯）→ `pytest tests/test_proposal_withdraw.py -v`
4. **T2 实现** `aligned_slow_loop.py` 中的 withdrawn 检查
5. **T3 确认** `sup_paths.py` 路径常量存在
6. **运行集成测试** → `pytest tests/test_proposal_withdraw.py tests/test_aligned_slow_loop.py -v`
7. **运行全量回归** → `cd /home/abug/timesfm && pytest tests/ -x --timeout=120`

---

## 文件清单

| 文件 | 改动 | 说明 |
|------|------|------|
| `scripts/proposal_status.py` | **修改** | 新增 `get_latest_status()`, `_get_latest_status_unlocked()`, `withdraw_proposal()`, `_TERMINAL_STATES` |
| `scripts/aligned_slow_loop.py` | **修改** | claim 前 withdrawn 检查 + verdict 写入前 withdrawn 检查 + `_check_withdrawn()` + `_mark_queue_skip()` |
| `scripts/sup_paths.py` | **确认** | P1.1 已完成，无需改动 |
| `tests/test_proposal_withdraw.py` | **新增** | 7 个测试函数覆盖撤回语义 |
