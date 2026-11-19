# Slow Loop Verdict Registry Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean 56.9% redundant verdicts from the slow loop registry, fix the `_dead_families` false-kill bug, add enqueue-layer dedup to prevent recurrence, and harden the tier classifier against gate_pass=False reaching S/A tier.

**Architecture:** Eight-phase approach: (0) shared constants + canonical helpers in registry_lib.py; (1) cleanup script dev + tests; (2) enqueue-layer dedup + pending fingerprint filtering; (3) remove write-layer dedup; (4) terminal state machine with persistent retry; (5) tier classifier hard gates; (6) _dead_families unified effective-row filter; (7) full regression + live data cleanup + restart + health check.

**Tech Stack:** Python 3.11, pytest, fcntl, psutil, JSONL

**Spec:** `docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md` (v5)

## Global Constraints

- All code in WSL `/home/abug/timesfm`
- Python 3.11, no new dependencies beyond `psutil` (already installed)
- Tests use pytest, run with `cd /home/abug/timesfm && pytest tests/<file> -v` (no `--timeout` flag; use shell `timeout 120s` if needed)
- Each Phase is a separate commit; code-review after each Phase
- **SSOT for constants and helpers**: defined in `scripts/registry_lib.py`, imported by all modules and tests:
  - `TERMINAL_STATUSES = frozenset({"insufficient_data", "error", "fatal_error"})`
  - `CURRENT_PROTOCOL_FINGERPRINT = "f02b2a43"` (CLI-overridable via `--current-fingerprint`)
  - `canonical_cov(record) -> str`: `record.get("cov_override") or record.get("covariate") or "UNKNOWN"`
  - `canonical_mode(record) -> str`: `record.get("run_mode") or record.get("mode") or "confirmatory"`
  - `effective_n(record) -> int`: safe int conversion of `n_eff` or `n`, returns 0 on failure
- Protocol fingerprint: current = `"f02b2a43"`
- Never use `min(tier, "C")` for tier capping — always use ordinal mapping
- Non-terminal states (n<350, retry_count<2) NOT written to registry
- Retry counter persisted to `task_FM/config/.slow_loop_retry_state.json` (atomic write, key includes protocol_fingerprint)
- **Live data cleanup happens LAST** (after all code fixes pass), never between code phases
- **Runtime data (verdicts, pending, retry state, archive) stays out of Git** — `.gitignore` covers all; verification report records stats only

## Review Focus

1. **Data loss during cleanup**: flock + atomic replace must prevent concurrent writes
2. **Death resurrection**: cleanup must KEEP current-protocol terminal states in main file
3. **Infinite retry loop**: enqueue-layer checks verdicts + pending + terminal states, all filtered by current fingerprint
4. **Survivorship bias in dedup**: keep latest by time, NOT by gate_pass=True
5. **Off-by-one in retry logic**: increment-then-check, 2nd failure = terminal
6. **UNKNOWN filter correctness**: `if cov and cov != "UNKNOWN"` — string "UNKNOWN" is truthy
7. **Terminal status records excluded from _dead_families**: error/insufficient_data must not vote
8. **n=0 canonicalization only for completed records**: half-finished records go to quarantine, not forced to error
9. **Pending queue lifecycle**: slow loop removes consumed items; fingerprint-aware cleanup

## Deferred Items (out of scope for this plan)

| Item | Rationale |
|------|-----------|
| Full pending state machine (pending→claimed→running→retryable/terminal/success) | Major refactor beyond cleanup scope; current append-only + remove-on-consume is sufficient |
| CURRENT_PROTOCOL_FINGERPRINT as external config file | CLI `--current-fingerprint` arg is sufficient for now; config file adds deployment complexity |
| Fault injection tests for cleanup crash recovery | Valuable but not blocking; cleanup has flock + atomic write + pre-cleanup backup |
| Lock contention / process guard unit tests | Hard to test reliably; covered by integration test in Phase 7 |

---

### Task 1: Phase 0 — Shared Constants + Canonical Helpers

**Files:**
- Modify: `scripts/registry_lib.py`
- Create: `tests/test_registry_lib_constants.py`

**Interfaces:**
- Produces: `TERMINAL_STATUSES`, `CURRENT_PROTOCOL_FINGERPRINT`, `canonical_cov()`, `canonical_mode()`, `effective_n()` — all exported from registry_lib.py

- [ ] **Step 1: Write tests for constants and helpers**

```python
"""Tests for registry_lib shared constants and helpers — SSOT."""
import pytest
from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, canonical_mode, effective_n,
)


def test_terminal_statuses_contents():
    assert TERMINAL_STATUSES == frozenset({"insufficient_data", "error", "fatal_error"})


def test_current_fingerprint():
    assert CURRENT_PROTOCOL_FINGERPRINT == "f02b2a43"


def test_canonical_cov_override_priority():
    assert canonical_cov({"cov_override": "rsi", "covariate": "macd"}) == "rsi"


def test_canonical_cov_fallback_to_covariate():
    assert canonical_cov({"covariate": "macd"}) == "macd"


def test_canonical_cov_default_unknown():
    assert canonical_cov({}) == "UNKNOWN"


def test_canonical_mode_run_mode_priority():
    assert canonical_mode({"run_mode": "exploration", "mode": "confirmatory"}) == "exploration"


def test_canonical_mode_fallback_to_mode():
    assert canonical_mode({"mode": "confirmatory"}) == "confirmatory"


def test_canonical_mode_default_confirmatory():
    assert canonical_mode({}) == "confirmatory"


def test_effective_n_normal():
    assert effective_n({"n_eff": 73}) == 73


def test_effective_n_fallback_to_n():
    assert effective_n({"n": 588}) == 588


def test_effective_n_string_conversion():
    assert effective_n({"n_eff": "350"}) == 350


def test_effective_n_none_returns_zero():
    assert effective_n({"n_eff": None}) == 0


def test_effective_n_missing_returns_zero():
    assert effective_n({}) == 0


def test_effective_n_invalid_string_returns_zero():
    assert effective_n({"n_eff": "abc"}) == 0
```

- [ ] **Step 2: Run tests to verify they FAIL**

Run: `cd /home/abug/timesfm && pytest tests/test_registry_lib_constants.py -v`
Expected: FAIL (functions don't exist yet)

- [ ] **Step 3: Implement constants and helpers in registry_lib.py**

At top of `scripts/registry_lib.py`:

```python
# Shared constants and helpers (SSOT — imported by all modules and tests)
TERMINAL_STATUSES = frozenset({"insufficient_data", "error", "fatal_error"})
CURRENT_PROTOCOL_FINGERPRINT = "f02b2a43"


def canonical_cov(record: dict) -> str:
    """Canonical covariate identifier. cov_override > covariate > UNKNOWN."""
    return record.get("cov_override") or record.get("covariate") or "UNKNOWN"


def canonical_mode(record: dict) -> str:
    """Canonical run mode. run_mode > mode > confirmatory."""
    return record.get("run_mode") or record.get("mode") or "confirmatory"


def effective_n(record: dict) -> int:
    """Safe integer extraction of effective sample count. n_eff > n > 0."""
    raw = record.get("n_eff", record.get("n", 0))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0
```

- [ ] **Step 4: Run tests to verify they PASS**

Run: `cd /home/abug/timesfm && pytest tests/test_registry_lib_constants.py -v`
Expected: 14 PASS

- [ ] **Step 5: Verify pytest-timeout availability**

Run: `cd /home/abug/timesfm && pytest --help 2>&1 | grep timeout || echo "pytest-timeout not installed; use shell timeout instead"`

- [ ] **Step 6: Commit**

```bash
cd /home/abug/timesfm
git add scripts/registry_lib.py tests/test_registry_lib_constants.py
git commit -m "feat: SSOT constants + canonical helpers in registry_lib (Phase 0)

- TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT
- canonical_cov(), canonical_mode(), effective_n()
- 14 tests pass
- All modules must import from here, not redefine locally

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md"
```

---

### Task 2: Phase 1 — Cleanup Script + Tests (dev only, no live data)

**Files:**
- Create: `scripts/cleanup_verdict_registry.py`
- Create: `tests/test_cleanup_verdict_registry.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: spec §4.1, all SSOT helpers from registry_lib
- Produces: working cleanup script + 12 passing tests

- [ ] **Step 1: Write all tests (complete assertions, no `pass` stubs)**

Tests must exercise real failure when implementation is missing. Key tests:

```python
"""Tests for scripts/cleanup_verdict_registry.py — spec §4.1"""
import json, os, subprocess, tempfile
import pytest
from pathlib import Path

from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, canonical_mode, effective_n,
)


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# --- Archive / KEEP rules ---

def test_old_protocol_archived():
    """Old protocol records → archive, regardless of n or status."""

def test_current_protocol_valid_kept():
    """Current fp, n>0, n_eff>0, status=ok → kept in main file."""

def test_current_protocol_terminal_kept():
    """Current fp + status in TERMINAL_STATUSES → kept (not archived)."""

def test_old_protocol_terminal_archived():
    """Old protocol + status=error → archived (NOT kept, only current fp terminals kept)."""

def test_current_protocol_n0_completed_canonicalized():
    """Current fp + n=0 + has decided_at/completed_at → canonicalized to status=error, kept."""

def test_current_protocol_n0_incomplete_quarantined():
    """Current fp + n=0 + no completion markers → quarantined (not kept, not archived as valid)."""


# --- Dedup ---

def test_cleanup_dedup_by_latest():
    """Multiple records same key → keep latest (decided_at, line_idx) descending."""

def test_cleanup_no_gate_pass_bias():
    """42 runs 1 pass → keeps latest (likely fail), not the 1 pass."""


# --- Field canonicalization ---

def test_cleanup_cov_field_fallback():
    """Uses canonical_cov(): cov_override > covariate > UNKNOWN."""

def test_cleanup_mode_field_fallback():
    """Uses canonical_mode(): run_mode > mode > confirmatory."""


# --- Pending queue ---

def test_cleanup_dedups_pending_queue():
    """Pending deduped + items already in cleaned verdicts removed."""

def test_cleanup_pending_fingerprint_filtered():
    """Pending items with old fingerprint are archived, not treated as current-protocol queued."""


# --- Safety ---

def test_cleanup_atomic_write():
    """Uses .tmp + os.replace; original file never half-written."""

def test_cleanup_idempotent():
    """Running cleanup twice produces same result (second run is no-op)."""
```

- [ ] **Step 2: Run tests to verify they FAIL**

Run: `cd /home/abug/timesfm && pytest tests/test_cleanup_verdict_registry.py -v`
Expected: FAIL (script doesn't exist yet)

- [ ] **Step 3: Implement cleanup script per spec §4.1**

Key elements:
1. Process guard via psutil (with NoSuchProcess/AccessDenied handling)
2. fcntl.flock exclusive lock on verdict file
3. KEEP rules (using SSOT helpers):
   - `is_valid = (fp == CURRENT_FP and effective_n(v) > 0 and status == "ok")`
   - `is_terminal = (fp == CURRENT_FP and status in TERMINAL_STATUSES)`
   - `is_n0_completed = (fp == CURRENT_FP and effective_n(v) == 0 and (v.get("decided_at") or v.get("completed_at") or v.get("error")))`
   - KEEP = is_valid OR is_terminal OR is_n0_completed
   - n=0 completed → canonicalize to `status="error"` before keeping
   - n=0 incomplete → quarantine file
4. Dedup by (symbol, cov, mode) using `canonical_cov()` and `canonical_mode()`
5. Sort by (decided_at, line_idx) descending
6. Atomic write: .tmp + os.replace
7. Pending queue cleanup: fingerprint-filtered, deduped, already-done removed, atomic write
8. Timestamped archive + quarantine files

- [ ] **Step 4: Fill in test bodies and run**

Run: `cd /home/abug/timesfm && pytest tests/test_cleanup_verdict_registry.py -v`
Expected: 12 PASS (adjust count if any tests merge)

- [ ] **Step 5: Update .gitignore**

```
# Slow loop runtime data (not versioned)
task_FM/config/aligned_verdicts.jsonl
task_FM/config/aligned_pending.jsonl
task_FM/config/aligned_verdicts.archive.*.jsonl
task_FM/config/aligned_verdicts.pre-cleanup-*.jsonl
task_FM/config/aligned_verdicts.quarantine.*.jsonl
task_FM/config/.slow_loop_retry_state.json
```

- [ ] **Step 6: Commit**

```bash
cd /home/abug/timesfm
git add scripts/cleanup_verdict_registry.py tests/test_cleanup_verdict_registry.py .gitignore
git commit -m "feat: cleanup verdict registry script + 12 tests (Phase 1)

- Process guard (psutil) + flock + atomic write
- KEEP rules: valid run / terminal state / n=0 completed (canonicalized)
- n=0 incomplete → quarantine
- Uses canonical_cov(), canonical_mode(), effective_n() from SSOT
- Pending queue: fingerprint-filtered + deduped + atomic write
- Idempotent on re-run
- .gitignore covers all runtime data
- 12 tests pass

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md §4.1"
```

- [ ] **Step 7: Code review**

---

### Task 3: Phase 2 — Enqueue-Layer Dedup + Tests

**Files:**
- Modify: `scripts/sup_harvest.py`
- Create: `tests/test_sup_harvest_dedup.py`

- [ ] **Step 1: Write all tests**

```python
"""Tests for sup_harvest.py enqueue-layer dedup — spec §4.2"""
import json, os
import pytest
from pathlib import Path

from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, canonical_mode,
)


def test_harvest_rejects_current_fp_evaluated():
    """Current fp + status=ok + n>=350 → not re-enqueued."""

def test_harvest_rejects_terminal_status():
    """status in TERMINAL_STATUSES (any of 3) → not re-enqueued."""

def test_harvest_ignores_old_fp_records():
    """Old protocol fp records do NOT count as evaluated (new fp can re-evaluate)."""

def test_harvest_checks_pending_current_fp():
    """Pending items with current fp count as queued → not re-enqueued."""

def test_harvest_ignores_pending_old_fp():
    """Pending items with old fp are NOT treated as queued (can be re-enqueued under new fp)."""

def test_harvest_in_flight_batch_dedup():
    """Same (symbol, cov, mode) twice in one batch → only enqueued once."""

def test_harvest_uses_canonical_helpers():
    """cov_override/covariate fallback and run_mode/mode fallback work correctly."""
```

- [ ] **Step 2: Run tests to verify they FAIL**

- [ ] **Step 3: Implement `_load_evaluated_or_queued()` in sup_harvest.py**

```python
from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, canonical_mode, effective_n,
)

def _load_evaluated_or_queued(verdict_path, pending_path, fingerprint):
    """Load set of (symbol, cov, mode) that are evaluated or queued under current fingerprint."""
    evaluated = set()

    # 1. Verdicts: only current fingerprint
    if os.path.exists(verdict_path):
        for line in open(verdict_path, encoding="utf-8"):
            if not line.strip(): continue
            v = json.loads(line)
            if v.get("protocol_fingerprint") != fingerprint: continue
            status = v.get("status")
            is_complete = (status == "ok" and effective_n(v) >= 350)
            is_terminal = (status in TERMINAL_STATUSES)
            if is_complete or is_terminal:
                key = (v.get("symbol"), canonical_cov(v), canonical_mode(v))
                evaluated.add(key)

    # 2. Pending: only current fingerprint
    if os.path.exists(pending_path):
        for line in open(pending_path, encoding="utf-8"):
            if not line.strip(): continue
            p = json.loads(line)
            if p.get("protocol_fingerprint") != fingerprint: continue
            key = (p.get("symbol"), canonical_cov(p), canonical_mode(p))
            evaluated.add(key)

    return evaluated
```

- [ ] **Step 4: Integrate into harvest loop with in-batch dedup**

```python
evaluated_set = _load_evaluated_or_queued(VERDICT_PATH, PENDING_PATH, CURRENT_PROTOCOL_FINGERPRINT)
for proposal in candidates:
    key = (proposal["symbol"], canonical_cov(proposal), canonical_mode(proposal))
    if key in evaluated_set: continue
    enqueue(proposal)
    evaluated_set.add(key)  # in-batch dedup
```

- [ ] **Step 5: Run tests**

Run: `cd /home/abug/timesfm && pytest tests/test_sup_harvest_dedup.py -v`
Expected: 7 PASS

Run full regression: `cd /home/abug/timesfm && timeout 120 pytest tests/ -x -q`

- [ ] **Step 6: Commit**

```bash
git add scripts/sup_harvest.py tests/test_sup_harvest_dedup.py
git commit -m "feat: enqueue-layer dedup with fingerprint filtering (Phase 2)

- _load_evaluated_or_queued() checks verdicts + pending, filtered by current fp
- TERMINAL_STATUSES treated as evaluated
- Old fp records do NOT block new fp evaluation
- In-batch dedup via evaluated_set.add()
- Uses canonical_cov(), canonical_mode() from SSOT
- 7 tests pass

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md §4.2"
```

- [ ] **Step 7: Code review**

---

### Task 4: Phase 3 — Remove Write-Layer Dedup + Test

**Files:**
- Modify: `scripts/registry_lib.py` (~line 310)
- Create: `tests/test_registry_lib_no_write_dedup.py`

- [ ] **Step 1: Write test**

```python
def test_append_verdict_allows_duplicates(tmp_path):
    """Two verdicts with same (symbol, cov, mode) but different batch_id → both written."""
    # Create two records with same semantic key, different batch_id/timestamp
    # Call append_verdict twice → both should appear in file
```

- [ ] **Step 2: Run test to verify it FAILS** (current code deduplicates)

- [ ] **Step 3: Remove `_is_duplicate_unlocked` call from `append_verdict`**

Keep function for potential future use, but remove the call in append path.

- [ ] **Step 4: Run tests**

Expected: PASS. Run full regression.

- [ ] **Step 5: Commit**

```bash
git add scripts/registry_lib.py tests/test_registry_lib_no_write_dedup.py
git commit -m "fix: remove write-layer dedup to prevent deadlock (Phase 3)

append_verdict is now append-only. Primary dedup at enqueue layer (Phase 2).

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md §4.3"
```

- [ ] **Step 6: Code review**

---

### Task 5: Phase 4 — Terminal State Machine + Tests

**Files:**
- Modify: `scripts/aligned_slow_loop.py`
- Create: `tests/test_slow_loop_terminal_state.py`

- [ ] **Step 1: Write all tests**

```python
"""Tests for aligned_slow_loop.py terminal state machine — spec §4.4"""
import json, os
import pytest
from pathlib import Path

from scripts.registry_lib import TERMINAL_STATUSES


def test_n0_writes_error():
    """n=0 → status=error written to registry."""

def test_n_lt_350_first_no_write():
    """n<350 first attempt (new_count=1) → NOT written to registry."""

def test_n_lt_350_second_writes_insufficient_data():
    """n<350 second attempt (new_count=2) → status=insufficient_data written."""

def test_retry_counter_persists_across_calls():
    """Retry counter survives function call (file-based persistence)."""

def test_retry_state_corruption_recovery():
    """Corrupted retry state file → graceful fallback to empty dict."""

def test_retry_key_includes_fingerprint():
    """Different fingerprints have independent retry counts (no cross-protocol pollution)."""

def test_success_clears_retry_entry():
    """n>=350 success removes retry entry for that combo."""

def test_exception_writes_fatal_error():
    """Unhandled exception in backtest → status=fatal_error written."""

def test_pending_item_removed_after_consumption():
    """After slow loop processes a pending item, it's removed from pending queue."""
```

- [ ] **Step 2: Run tests to verify they FAIL**

- [ ] **Step 3: Implement retry state functions**

```python
RETRY_STATE_PATH = "task_FM/config/.slow_loop_retry_state.json"

def _load_retry_state() -> dict:
    if os.path.exists(RETRY_STATE_PATH):
        try:
            return json.loads(Path(RETRY_STATE_PATH).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def _save_retry_state(state: dict):
    tmp = RETRY_STATE_PATH + ".tmp"
    Path(tmp).write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, RETRY_STATE_PATH)

def _retry_key(symbol, cov, mode, fingerprint):
    return f"{fingerprint}::{symbol}::{cov}::{mode}"

def _increment_retry(symbol, cov, mode, fingerprint) -> int:
    key = _retry_key(symbol, cov, mode, fingerprint)
    state = _load_retry_state()
    entry = state.get(key, {"count": 0})
    entry["count"] += 1
    from datetime import datetime
    entry["last_attempt"] = datetime.now().isoformat()
    state[key] = entry
    _save_retry_state(state)
    return entry["count"]

def _clear_retry(symbol, cov, mode, fingerprint):
    key = _retry_key(symbol, cov, mode, fingerprint)
    state = _load_retry_state()
    state.pop(key, None)
    _save_retry_state(state)
```

- [ ] **Step 4: Implement state machine + pending removal**

```python
try:
    result = run_backtest(proposal)
except Exception as e:
    result = {"symbol": symbol, "cov_override": cov, "status": "fatal_error",
              "n": 0, "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT, ...}
    registry.append_verdict(result)
    _remove_from_pending(proposal)  # atomic removal
    return

n = result.get("n") or 0

if n == 0:
    result["status"] = "error"
    registry.append_verdict(result)
elif n < 350:
    new_count = _increment_retry(symbol, cov, mode, CURRENT_PROTOCOL_FINGERPRINT)
    if new_count >= 2:
        result["status"] = "insufficient_data"
        registry.append_verdict(result)
    # new_count == 1: no verdict write, retry state tracked
else:
    result["status"] = "ok"
    registry.append_verdict(result)
    _clear_retry(symbol, cov, mode, CURRENT_PROTOCOL_FINGERPRINT)

_remove_from_pending(proposal)  # always remove consumed item from pending
```

- [ ] **Step 5: Run tests**

Expected: 9 PASS. Run full regression.

- [ ] **Step 6: Commit**

```bash
git add scripts/aligned_slow_loop.py tests/test_slow_loop_terminal_state.py
git commit -m "feat: terminal state machine + persistent retry + pending removal (Phase 4)

- n=0 → error; n<350 first → no write; n<350 second → insufficient_data
- Exception → fatal_error
- Retry key includes fingerprint (no cross-protocol pollution)
- Success clears retry entry
- Pending item removed after consumption
- Retry state: atomic write + corruption recovery
- 9 tests pass

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md §4.4"
```

- [ ] **Step 7: Code review**

---

### Task 6: Phase 5 — Tier Classifier Hard Gates + Tests

**Files:**
- Modify: `cascade/tier_classifier.py`
- Create: `tests/test_tier_classifier_hard_gates.py`

- [ ] **Step 1: Write all tests (including boundary + type edge cases)**

```python
"""Tests for tier_classifier.py hard gates — spec §4.5"""
import pytest


def test_gate_pass_false_caps_at_c():
    """gate_pass=False → tier ≤ C."""

def test_gate_pass_d_stays_d():
    """D-tier with gate_pass=False stays D."""

def test_gate_pass_missing_treated_as_false():
    """Missing gate_pass field → treated as False → capped at C."""

def test_gate_pass_string_false():
    """gate_pass='False' (string) → must be correctly interpreted as False."""

def test_s_tier_dir_acc_above_054():
    """S-tier with dir_acc=0.55 → stays S."""

def test_s_tier_dir_acc_at_boundary():
    """S-tier with dir_acc=0.54 → stays S (boundary is inclusive)."""

def test_s_tier_dir_acc_below_boundary():
    """S-tier with dir_acc=0.539 → demoted to A."""

def test_s_tier_dir_acc_0513_demotes():
    """S-tier with dir_acc=0.513 → demoted to A."""

def test_none_dir_acc_no_crash():
    """None dir_acc → treated as 0.0, no crash."""

def test_string_dir_acc_no_crash():
    """dir_acc='0.55' (string) → handled without TypeError."""

def test_cap_tier_normalizes_lowercase():
    """cap_tier('a', 'C') → 'C' (lowercase input handled)."""

def test_cap_tier_normalizes_whitespace():
    """cap_tier(' A ', 'C') → 'C' (whitespace stripped)."""

def test_cap_tier_unknown_input():
    """cap_tier('X', 'C') → 'C' (unknown tier defaults to worst)."""
```

- [ ] **Step 2: Run tests to verify they FAIL**

- [ ] **Step 3: Implement ordinal mapping + hard gates + input normalization**

```python
TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
RANK_TO_TIER = {v: k for k, v in TIER_RANK.items()}

def _as_bool(value) -> bool:
    if isinstance(value, bool): return value
    if isinstance(value, str): return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)

def _as_float(value, default=0.0) -> float:
    if value is None: return default
    try: return float(value)
    except (TypeError, ValueError): return default

def cap_tier(tier: str, max_tier: str) -> str:
    tier = tier.strip().upper() if tier else "D"
    tier_rank = TIER_RANK.get(tier, 4)
    max_rank = TIER_RANK.get(max_tier.strip().upper(), 4)
    return RANK_TO_TIER[max(tier_rank, max_rank)]

# After tier computation:
tier = tier.strip().upper() if tier else "D"
if not _as_bool(row.get("gate_pass")):
    tier = cap_tier(tier, "C")
dir_acc = _as_float(row.get("dir_acc"))
if tier == "S" and dir_acc < 0.54:
    tier = "A"
```

- [ ] **Step 4: Run tests**

Expected: 13 PASS. Run full regression.

- [ ] **Step 5: Commit**

```bash
git add cascade/tier_classifier.py tests/test_tier_classifier_hard_gates.py
git commit -m "feat: tier classifier hard gates + input normalization (Phase 5)

- cap_tier() with ordinal mapping + strip().upper() normalization
- _as_bool() handles bool/string/missing gate_pass
- _as_float() handles None/string/invalid dir_acc
- gate_pass=False → max C; S-tier requires dir_acc >= 0.54
- 13 tests pass (incl. boundary + type edge cases)

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md §4.5"
```

- [ ] **Step 6: Code review**

---

### Task 7: Phase 6 — Fix _dead_families + Tests

**Files:**
- Modify: `scripts/sup_evidence.py` (~line 736)
- Create: `tests/test_dead_families_fix.py`

- [ ] **Step 1: Read _dead_families real interface**

```bash
cd /home/abug/timesfm
grep -n '_dead_families\|def.*dead' scripts/sup_evidence.py
# Read function signature, input format, return value, side effects
```

Document in test file: function signature, input record structure, how to observe "family declared dead".

- [ ] **Step 2: Write all tests using REAL function interface**

```python
"""Tests for _dead_families fix — spec §4.6

Binds to real _dead_families() function in sup_evidence.py.
"""
import pytest
from scripts.registry_lib import TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT, canonical_cov


def test_dead_families_unique_covs():
    """4 duplicate rows for same cov → NOT dead (only 1 unique)."""

def test_dead_families_excludes_unknown():
    """3 real covs + 1 UNKNOWN → NOT dead (only 3 valid unique)."""

def test_dead_families_excludes_terminal_status():
    """4 error/insufficient_data verdicts → NOT dead (terminal excluded)."""

def test_dead_families_4_unique_triggers():
    """4 unique valid covs with status=ok + 0 gate_pass → dead."""

def test_dead_families_only_counts_current_fp():
    """Old fp failure rows not counted toward death threshold."""

def test_dead_families_effective_rows_filter():
    """Only status=ok + n>=350 + current fp rows contribute to both
    unique_failed_covs AND total_gate_pass (unified filter)."""
```

- [ ] **Step 3: Run tests to verify they FAIL**

- [ ] **Step 4: Implement fix with unified effective_rows filter**

```python
from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, effective_n,
)

# Unified effective row filter
effective_rows = [
    r for r in all_rows
    if r.get("protocol_fingerprint") == CURRENT_PROTOCOL_FINGERPRINT
    and r.get("status") == "ok"
    and effective_n(r) >= 350
]

# Derive both metrics from same filtered set
unique_failed_covs = set()
total_gate_pass = 0
for r in effective_rows:
    cov = canonical_cov(r)
    if r.get("gate_pass", False):
        total_gate_pass += 1
    elif cov and cov != "UNKNOWN":
        unique_failed_covs.add(cov)

if len(unique_failed_covs) >= 4 and total_gate_pass == 0:
    declare_dead(family)
```

- [ ] **Step 5: Run tests**

Expected: 6 PASS. Run full regression.

- [ ] **Step 6: Commit**

```bash
git add scripts/sup_evidence.py tests/test_dead_families_fix.py
git commit -m "fix: _dead_families unified effective-row filter (Phase 6)

- Unified filter: current fp + status=ok + n>=350
- Both unique_failed_covs and total_gate_pass derived from same set
- Excludes UNKNOWN covariates from death threshold
- Excludes terminal status records
- Tests bind to real _dead_families() interface
- 6 tests pass

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md §4.6"
```

- [ ] **Step 7: Code review**

---

### Task 8: Phase 7 — Full Regression + Live Cleanup + Restart

**Files:**
- Create: `docs/superpowers/reports/2026-11-07-cleanup-verification.md`
- Create: `docs/superpowers/changelogs/2026-11-07-slow-loop-verdict-cleanup.md`

**Runtime data (verdicts, pending, archive, retry state) is NOT committed to Git.**

- [ ] **Step 1: Run full test suite**

```bash
cd /home/abug/timesfm
timeout 120 pytest tests/ -x -q
```

Expected: All pass (existing + 50 new tests from Phases 0-6)

- [ ] **Step 2: Stop three-loop processes (robust procedure)**

```bash
# 1. Record target PIDs
PIDS=$(pgrep -f 'praxist_supervisor|aligned_slow_loop' 2>/dev/null)
echo "Target PIDs: $PIDS"

# 2. Send SIGTERM to each
for pid in $PIDS; do kill -TERM "$pid" 2>/dev/null; done

# 3. Poll with timeout (30s)
for i in $(seq 1 30); do
    remaining=$(pgrep -f 'praxist_supervisor|aligned_slow_loop' 2>/dev/null)
    if [ -z "$remaining" ]; then echo "All stopped after ${i}s"; break; fi
    sleep 1
done

# 4. SIGKILL any remaining original PIDs
for pid in $PIDS; do
    if kill -0 "$pid" 2>/dev/null; then
        echo "Force killing $pid"
        kill -9 "$pid" 2>/dev/null
    fi
done

# 5. Final verification
sleep 2
pgrep -af 'praxist_supervisor|aligned_slow_loop' && echo "WARNING: still running" || echo "Confirmed stopped"

# 6. Disable auto-restart (if applicable)
# systemctl stop fm-supervisor 2>/dev/null || true
# crontab -l | grep -v supervisor | crontab - 2>/dev/null || true
```

- [ ] **Step 3: Backup BOTH verdict and pending files**

```bash
TS=$(date +%Y%m%d_%H%M%S)
cp task_FM/config/aligned_verdicts.jsonl task_FM/config/aligned_verdicts.pre-cleanup-${TS}.jsonl
cp task_FM/config/aligned_pending.jsonl task_FM/config/aligned_pending.pre-cleanup-${TS}.jsonl
echo "Backups created with timestamp ${TS}"
```

- [ ] **Step 4: Run cleanup script**

```bash
cd /home/abug/timesfm
python scripts/cleanup_verdict_registry.py --current-fingerprint f02b2a43
```

- [ ] **Step 5: Verify results (both files)**

```bash
echo "=== Verdicts ==="
wc -l task_FM/config/aligned_verdicts.jsonl
python3 -c "
import json
from collections import Counter
lines = [json.loads(l) for l in open('task_FM/config/aligned_verdicts.jsonl') if l.strip()]
print(f'Total: {len(lines)}')
print(f'Tier: {dict(Counter(v.get(\"tier\") for v in lines))}')
print(f'Status: {dict(Counter(v.get(\"status\") for v in lines))}')
keys = set((v.get('symbol'), v.get('cov_override') or v.get('covariate'), v.get('run_mode') or v.get('mode')) for v in lines)
print(f'Unique keys: {len(keys)}')
dups = len(lines) - len(keys)
print(f'Duplicates: {dups}')
"

echo "=== Pending ==="
wc -l task_FM/config/aligned_pending.jsonl

echo "=== Checksums ==="
md5sum task_FM/config/aligned_verdicts.jsonl task_FM/config/aligned_pending.jsonl
```

- [ ] **Step 6: Write verification report**

Create `docs/superpowers/reports/2026-11-07-cleanup-verification.md` with:
- Before/after line counts for BOTH verdicts and pending
- Tier distribution, unique keys, duplicates removed
- Checksums of cleaned files
- Backup file locations
- Any anomalies

- [ ] **Step 7: Restart with health check**

```bash
cd /home/abug/timesfm
bash scripts/start_supervisor.sh
NEW_PID=$(pgrep -f praxist_supervisor | head -1)
echo "New supervisor PID: $NEW_PID"

# Health check: wait 30s, verify process alive + no immediate crashes
sleep 30
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "Health check: supervisor alive after 30s"
else
    echo "HEALTH CHECK FAILED: supervisor died within 30s"
    echo "Rollback procedure:"
    echo "  1. kill any remaining processes"
    echo "  2. cp task_FM/config/aligned_verdicts.pre-cleanup-*.jsonl task_FM/config/aligned_verdicts.jsonl"
    echo "  3. cp task_FM/config/aligned_pending.pre-cleanup-*.jsonl task_FM/config/aligned_pending.jsonl"
    echo "  4. git revert HEAD"
    exit 1
fi
```

- [ ] **Step 8: Write changelog**

Create `docs/superpowers/changelogs/2026-11-07-slow-loop-verdict-cleanup.md`:
- Problem summary, root causes, solution (8 phases)
- Key decisions: SSOT helpers, no write-layer dedup, terminal state machine, unified effective-row filter
- Test coverage: 50 new tests
- Verification results
- Backup locations + checksums

- [ ] **Step 9: Commit (only docs, not runtime data)**

```bash
cd /home/abug/timesfm
git add docs/superpowers/reports/2026-11-07-cleanup-verification.md \
       docs/superpowers/changelogs/2026-11-07-slow-loop-verdict-cleanup.md
git commit -m "docs: cleanup verification report + changelog (Phase 7)

All 7 code phases committed and reviewed.
50 new tests, all pass.
Live cleanup executed: verdicts 640→~200 lines, pending cleaned.
Runtime data NOT versioned (in .gitignore).
Supervisor restarted, health check passed.
Backups preserved with checksums in verification report.

Spec: docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md"
```

- [ ] **Step 10: Push to backup (with pre-checks)**

```bash
# Pre-flight checks
git remote get-url backup || { echo "ERROR: backup remote not found"; exit 1; }
[ "$(git branch --show-current)" = "master" ] || { echo "ERROR: not on master"; exit 1; }
[ -z "$(git status --short)" ] || { echo "ERROR: working tree not clean"; exit 1; }
echo "Pushing: $(git log -1 --oneline)"
git push backup master
```

---

## Summary

| Phase | Task | Content | Tests | Commit | Review |
|-------|------|---------|-------|--------|--------|
| 0: SSOT | T1 | Constants + canonical helpers | 14 | 1 | — |
| 1: Cleanup dev | T2 | Script + .gitignore (no live data) | 12 | 1 | 1 review |
| 2: Enqueue dedup | T3 | Fingerprint-filtered dedup + pending | 7 | 1 | 1 review |
| 3: Remove write dedup | T4 | Append-only write layer | 1 | 1 | 1 review |
| 4: Terminal state | T5 | Persistent retry + pending removal | 9 | 1 | 1 review |
| 5: Tier gates | T6 | Ordinal cap + type normalization | 13 | 1 | 1 review |
| 6: _dead_families | T7 | Unified effective-row filter | 6 | 1 | 1 review |
| 7: Live ops | T8 | Regression + stop + cleanup + restart + health check | — | 1 | — |
| **Total** | **8 Tasks** | | **62 tests** | **8 commits** | **6 reviews** |

## Execution Order Rationale

Live data cleanup (Task 8) runs **LAST** to prevent "window period re-contamination":
- All code fixes committed and reviewed before touching live data
- Stop processes → backup → cleanup → restart → health check is atomic
- Runtime data NOT committed to Git (`.gitignore`); only verification report + changelog committed
- Rollback procedure documented in health check step
