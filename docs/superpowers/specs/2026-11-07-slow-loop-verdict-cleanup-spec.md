# Slow Loop Verdict Registry Cleanup & Dedup Spec

> **Spec date**: 2026-11-07
> **Revision**: v5 (2026-11-07, final — syntax fix, off-by-one, atomic retry, flock)
> **Author**: Claude Code (opus) + user review
> **Status**: DRAFT — pending approval
> **Audit report**: `docs/superpowers/reports/2026-11-07-slow-loop-verdict-quality-audit.md` (v2)
> **Baseline**: master @ 5b02284, working tree 640 lines

### v3 → v4 Key Fixes

| # | v3 Issue | v4 Fix |
|---|----------|--------|
| 1 | **BLOCKER**: §4.1 cleanup archives terminal states → "death resurrection" loop | §4.1: KEEP condition includes `status in TERMINAL_STATUSES` |
| 2 | **HIGH**: §4.4 in-memory retry counter resets on process restart | §4.4: File-based retry state `.slow_loop_retry_state.json` |
| 3 | **HIGH**: §4.1 doesn't clean pending queue | §4.1: Added pending queue dedup + already-done removal |
| 4 | §7 test contradicts §4.3 (no write-layer dedup) | §7: Renamed to `test_registry_allows_multiple_appends` |
| 5 | Phase 3 says "NO CHANGES" but dedup exists | Phase 3: Renamed "Remove Existing Dedup Logic" |
| 6 | §4.6 _dead_families counts UNKNOWN as factor | §4.6: Filter out empty/UNKNOWN covariates |
| 7 | psutil race condition on process iteration | §4.1: Added `NoSuchProcess`/`AccessDenied` exception handling |
| 8 | `is_valid_pass` naming misleading | §4.2: Renamed to `is_complete_eval` |

---

## 1. Problem Statement

The slow loop verdict registry (`task_FM/config/aligned_verdicts.jsonl`) has accumulated severe data quality issues:

| Issue | Severity | Count |
|-------|----------|-------|
| **4 protocol fingerprint generations coexist** | High | 4 gens mixed |
| **Redundant verdicts (same symbol+cov repeated)** | High | 364/640 (56.9%) |
| **Current protocol redundancy** | High | 171/375 (45.6%) |
| **n=0 empty verdicts** | High | 77 (all old protocol) |
| **No-fingerprint verdicts with gate_pass=True** | High | 42 (legacy semantics) |
| **_dead_families false-kill from duplicate failure rows** | **Critical** | e.g. jd+stddev 18× all fail |
| **Same variant_id written multiple times** | Med | 108 duplicate writes |

### Critical Business Impact

`sup_evidence.py` `_dead_families` judges family death by **verdict row count** (not unique covariates):
- Family with ≥4 confirmatory DM failure verdicts + 0 gate_pass → declared dead
- Duplicate verdicts flood families with failure rows → false family death
- Once a family is declared dead, ALL future covariates in that family are unconditionally rejected
- Example: jd+stddev judged 18 times (0/18 gate_pass) → volatility family false-killed

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | Clean the registry to current-protocol-only, deduplicated state |
| G2 | Prevent recurrence via enqueue-layer dedup + n=0 write guard |
| G3 | Fix tier_classifier to prevent gate_pass=False from reaching S/A tier |
| G4 | Archive old protocol data losslessly (never delete, only move) |
| G5 | Fix _dead_families to count unique covariates, not verdict rows |

### Non-Goals

| # | Non-Goal | Rationale |
|---|----------|-----------|
| NG1 | Backfill old records with current fingerprint | Would pollute valid pool with legacy semantics |
| NG2 | Dedup by keeping gate_pass=True | Survivorship bias: erases falsification records |
| NG3 | Change n_eff scoring to relative ranking | Architecture incompatible; amplifies float noise |
| NG4 | Schema simplification (94 fields → fewer) | Out of scope; separate effort |

---

## 3. Current State

### 3.1 Protocol Fingerprint Distribution (640 verdicts)

| Fingerprint | Count | Pct | Notes |
|-------------|-------|-----|-------|
| `f02b2a43` (current) | 375 | 58.6% | 2026-10-01 to present |
| MISSING (field absent) | 220 | 34.4% | old protocol, no fingerprint |
| `bd851c9c` (old) | 27 | 4.2% | historical |
| `91ab913e` (old) | 18 | 2.8% | historical |

### 3.2 Current Protocol Tier Distribution (375 verdicts)

| Tier | Count | Unique combos | gate_pass |
|------|-------|---------------|-----------|
| S | 53 | 44 | 52/53 (98.1%) |
| A | 98 | 64 | 59/98 (60.2%) |
| B | 135 | 101 | 30/135 (22.2%) |
| C | 65 | 50 | 7/65 (10.8%) |
| D | 24 | 8 | 0/24 (0.0%) |

### 3.3 Root Causes

1. **registry_lib.py:310** dedup key `(batch_id, variant_id)` includes batch_id; variant_id contains experiment_fingerprint which varies with data window → same (symbol, cov) produces different variant_ids across batches → bypasses dedup
2. **Same variant_id also duplicated**: 108 times — caused by stash merge (commit 38ae77d: 469→935 lines) + sup_harvest.py existing set invalidated by fingerprint changes
3. **sup_harvest.py** does not check if (symbol, cov) already has a valid verdict under current protocol before enqueuing
4. **sup_harvest.py** does not check `aligned_pending.jsonl` — same combo can be enqueued multiple times while slow
5. **aligned_slow_loop.py** writes n=0 verdicts with status=ok instead of status=error
6. **tier_classifier.py** allows gate_pass=False verdicts to reach S/A tier
7. **sup_evidence.py:_dead_families** counts verdict rows, not unique covariates

---

## 4. Design

### 4.1 Data Cleanup (One-Time Script)

**File**: `scripts/cleanup_verdict_registry.py`

**Pre-flight checks**:
1. **Process guard**: Use `psutil` with exception handling for race conditions. If running, abort with error message.
   ```python
   import psutil
   for proc in psutil.process_iter(['cmdline']):
       try:
           cmdline = ' '.join(proc.info['cmdline'] or [])
           if any(t in cmdline for t in ['aligned_slow_loop', 'praxist_supervisor']):
               raise RuntimeError(f"Process still running: PID {proc.pid} ({cmdline[:50]}...). Stop all三环 processes first.")
       except (psutil.NoSuchProcess, psutil.AccessDenied):
           continue  # process exited during iteration
   ```
2. **File lock**: Acquire exclusive lock via `fcntl.flock()` on `aligned_verdicts.jsonl` before any writes.
3. **Atomic write**: Write to `aligned_verdicts.jsonl.tmp`, then `os.replace()` to target path.

**Algorithm**:
```python
import json, os, fcntl
from collections import defaultdict
from datetime import datetime

VERDICT_PATH = "task_FM/config/aligned_verdicts.jsonl"
PENDING_PATH = "task_FM/config/aligned_pending.jsonl"
ARCHIVE_PATH = f"task_FM/config/aligned_verdicts.archive.{datetime.now():%Y%m%d_%H%M%S}.jsonl"
CURRENT_FP = "f02b2a43"
TERMINAL_STATUSES = {"insufficient_data", "error", "fatal_error"}

# 1. Read verdicts WITH line index; KEEP terminal states too (prevent "death resurrection")
#    Acquire exclusive lock to prevent concurrent writes during cleanup
verdicts = []
archive = []
with open(VERDICT_PATH, "r", encoding="utf-8") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # exclusive lock
    for idx, line in enumerate(f):
        if not line.strip():
            continue
        v = json.loads(line)
        fp = v.get("protocol_fingerprint")
        n = v.get("n") or 0
        n_eff = v.get("n_eff") or 0
        status = v.get("status")
        
        # KEEP if: valid run (current fp, n>0, n_eff>0)
        #       OR: terminal state under current fp (prevents death resurrection)
        is_valid_run = (fp == CURRENT_FP and n > 0 and n_eff > 0)
        is_terminal = (fp == CURRENT_FP and status in TERMINAL_STATUSES)
        
        if is_valid_run or is_terminal:
            verdicts.append((idx, v))
        else:
            archive.append(v)

# 2. Group by (symbol, cov, run_mode) with field canonicalization
groups = defaultdict(list)
for idx, v in verdicts:
    sym = v.get("symbol")
    cov = v.get("cov_override") or v.get("covariate") or "UNKNOWN"
    mode = v.get("run_mode") or "exploration"
    key = (sym, cov, mode)
    groups[key].append((idx, v))

# 3. Dedup: keep latest by (decided_at, line_idx) — both descending
deduped = []
for key, group in groups.items():
    group.sort(key=lambda x: (x[1].get("decided_at") or "", x[0]), reverse=True)
    best_idx, best_v = group[0]
    best_v["cov_override"] = key[1]
    best_v["run_mode"] = key[2]
    deduped.append(best_v)

# 4. Write verdicts (atomic)
tmp_path = VERDICT_PATH + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    for v in deduped:
        f.write(json.dumps(v, ensure_ascii=False) + "\n")
os.replace(tmp_path, VERDICT_PATH)

# 5. Clean pending queue: dedup + remove items already in cleaned verdicts
cleaned_keys = set()
for v in deduped:
    sym = v.get("symbol")
    cov = v.get("cov_override") or v.get("covariate") or "UNKNOWN"
    mode = v.get("run_mode") or "exploration"
    cleaned_keys.add((sym, cov, mode))

if os.path.exists(PENDING_PATH):
    pending = []
    seen_pending = set()
    with open(PENDING_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            p = json.loads(line)
            sym = p.get("symbol")
            cov = p.get("cov_override") or p.get("covariate") or "UNKNOWN"
            mode = p.get("run_mode") or "exploration"
            key = (sym, cov, mode)
            # Skip if already in cleaned verdicts (terminal/valid) or duplicate in pending
            if key in cleaned_keys or key in seen_pending:
                continue
            seen_pending.add(key)
            pending.append(p)
    
    tmp_pending = PENDING_PATH + ".tmp"
    with open(tmp_pending, "w", encoding="utf-8") as f:
        for p in pending:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    os.replace(tmp_pending, PENDING_PATH)
    print(f"Pending queue: cleaned to {len(pending)} items")

# 6. Archive (timestamped, idempotent)
with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
    for v in archive:
        f.write(json.dumps(v, ensure_ascii=False) + "\n")

# 7. Summary
print(f"Verdicts: {len(verdicts) + len(archive)} → {len(deduped)} (deduped), {len(archive)} archived")
print(f"Archive: {ARCHIVE_PATH}")
```

**Key decisions**:
- **KEEP terminal states**: `status in TERMINAL_STATUSES` records are kept to prevent "death resurrection" — if cleaned, §4.2 would re-enqueue them
- **Pending queue cleanup**: Dedup pending + remove items already in cleaned verdicts
- **Timsort fix**: `(decided_at, line_idx)` dual-key descending sort
- **psutil safety**: `NoSuchProcess`/`AccessDenied` exceptions caught
- Field canonicalization + timestamped archive

### 4.2 Enqueue-Layer Dedup (Prevention)

**File**: `scripts/sup_harvest.py`

**Change**: Before enqueuing a proposal, check if the current protocol fingerprint already has a valid verdict OR if it's already in the pending queue OR if it has reached a terminal state.

**Terminal States Definition**:
```python
# All statuses that mean "do not re-evaluate"
TERMINAL_STATUSES = {"insufficient_data", "error", "fatal_error"}
```

**Performance**: Load evaluated set into memory once at harvest start (O(1) lookup), not per-proposal disk scan.

```python
import os, json

TERMINAL_STATUSES = {"insufficient_data", "error", "fatal_error"}

def _load_evaluated_or_queued(verdict_path: str, pending_path: str, fingerprint: str) -> set:
    """Load set of (symbol, cov, run_mode) that are evaluated or queued.
    
    A combo is considered "done" if:
    1. It has status=ok AND n>=350 in verdicts (valid pass), OR
    2. It has status in TERMINAL_STATUSES (error/insufficient_data/fatal_error)
    3. It's already in the pending queue (waiting to be evaluated)
    """
    evaluated = set()
    
    # 1. Scan verdicts
    if os.path.exists(verdict_path):
        with open(verdict_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    v = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                if v.get("protocol_fingerprint") != fingerprint:
                    continue
                
                status = v.get("status")
                n = v.get("n") or 0
                
                # Complete evaluation: status=ok AND n>=350
                is_complete_eval = (status == "ok" and n >= 350)
                # Terminal state: error/insufficient_data/fatal_error
                is_terminal = (status in TERMINAL_STATUSES)
                
                if is_complete_eval or is_terminal:
                    sym = v.get("symbol")
                    cov = v.get("cov_override") or v.get("covariate") or "UNKNOWN"
                    mode = v.get("run_mode") or "exploration"
                    evaluated.add((sym, cov, mode))
    
    # 2. Scan pending queue
    if os.path.exists(pending_path):
        with open(pending_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    p = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sym = p.get("symbol")
                cov = p.get("cov_override") or p.get("covariate") or "UNKNOWN"
                mode = p.get("run_mode") or "exploration"
                evaluated.add((sym, cov, mode))
    
    return evaluated

# In harvest main loop:
evaluated_set = _load_evaluated_or_queued(VERDICT_PATH, PENDING_PATH, current_fingerprint)

for proposal in candidates:
    sym = proposal["symbol"]
    cov = proposal.get("cov_override") or proposal.get("covariate") or "UNKNOWN"
    mode = proposal.get("run_mode") or "exploration"
    key = (sym, cov, mode)
    
    if key in evaluated_set:
        continue  # already evaluated, terminal, or queued
    
    enqueue(proposal)
    evaluated_set.add(key)  # CRITICAL: prevent same-batch duplicate enqueue
```

**Key points**:
- `TERMINAL_STATUSES` includes "error" — prevents n=0 infinite retry loop
- `evaluated_set.add(key)` after enqueue — prevents same-batch duplicate
- Checks both verdicts AND pending queue — prevents double-queueing

### 4.3 Write-Layer: NO DEDUP (Removed to Prevent Deadlock)

**File**: `scripts/registry_lib.py`

**DECISION**: **Remove write-layer dedup entirely.**

**Rationale (v2 → v3)**: v2 specified dedup key `(protocol_fingerprint, symbol, cov_override, run_mode)` at write layer. This creates an **irreconcilable deadlock** with the retry state machine (§4.4):

**Deadlock scenario**:
1. Combo A first run: n=200 < 350, slow loop writes status="ok", n=200
2. Write-layer now has key (f02b2a43, A, cov, mode) → blocks future writes
3. Next harvest: sees n < 350 → re-enqueues combo A
4. Slow loop second run: n=200 again, fail_count >= 2, tries to write status="insufficient_data"
5. **Write-layer blocks** the terminal state write because key already exists!
6. Disk forever has only n=200, harvest forever re-enqueues → **infinite retry deadlock**

**Solution**: Primary dedup happens at **enqueue layer** (§4.2). Write layer is append-only, no dedup check. This allows terminal states to be written.

**Note**: If duplicate writes occur (e.g., from merge conflicts), the cleanup script (§4.1) handles them post-hoc.

### 4.4 n=0 / n<350 Write Guard + Terminal State

**File**: `scripts/aligned_slow_loop.py`

**Change**: Do NOT write non-terminal states to registry. Only write when reaching terminal state.

**Retry counter persistence**: Use a local state file (NOT in-memory counter) to survive process restarts. Atomic write + corruption recovery.

```python
# Retry state file: task_FM/config/.slow_loop_retry_state.json
# Format: {"symbol::cov_override::run_mode": {"count": N, "last_attempt": "ISO timestamp"}}

import json, os
from pathlib import Path

RETRY_STATE_PATH = "task_FM/config/.slow_loop_retry_state.json"

def _load_retry_state() -> dict:
    if os.path.exists(RETRY_STATE_PATH):
        try:
            return json.loads(Path(RETRY_STATE_PATH).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}  # corrupted file — start fresh
    return {}

def _save_retry_state(state: dict):
    """Atomic write: write to .tmp then os.replace."""
    tmp_path = RETRY_STATE_PATH + ".tmp"
    Path(tmp_path).write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp_path, RETRY_STATE_PATH)

def _get_retry_count(symbol: str, cov: str, mode: str) -> int:
    key = f"{symbol}::{cov}::{mode}"
    state = _load_retry_state()
    return state.get(key, {}).get("count", 0)

def _increment_retry(symbol: str, cov: str, mode: str) -> int:
    """Increment retry counter and return the NEW count."""
    key = f"{symbol}::{cov}::{mode}"
    state = _load_retry_state()
    entry = state.get(key, {"count": 0})
    entry["count"] += 1
    from datetime import datetime
    entry["last_attempt"] = datetime.now().isoformat()
    state[key] = entry
    _save_retry_state(state)
    return entry["count"]  # return new count for immediate check
```

**State machine**:
```
                    ┌─────────────────┐
                    │  Proposal Ready │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Slow Loop Run  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌────▼────┐   ┌─────▼──────┐
        │ n >= 350  │  │ n > 0   │   │ n == 0     │
        │ + gate ok │  │ < 350   │   │ (crash)    │
        └─────┬─────┘  └────┬────┘   └─────┬──────┘
              │              │              │
              │              │              │
        ┌─────▼─────┐  ┌────▼────────┐  ┌──▼──────────┐
        │ WRITE     │  │ INCREMENT   │  │ WRITE       │
        │ status=ok │  │ retry file  │  │ status=     │
        │           │  │ THEN check  │  │ "error"     │
        └───────────┘  └────┬────────┘  └─────────────┘
                            │
                   new_count >= 2?
                   ┌────yes──┴──no────┐
                   │                  │
             ┌─────▼──────┐    (new_count == 1)
             │ WRITE      │    NO WRITE, wait
             │ status=    │    for next harvest
             │"insuffi-   │
             │ cient_data"│
             └────────────┘
```

**Implementation**:
```python
# In aligned_slow_loop.py, after backtest:
result = run_backtest(proposal)
n = result.get("n") or 0
symbol = result["symbol"]
cov = result.get("cov_override") or result.get("covariate")
mode = result.get("run_mode") or "exploration"

if n == 0:
    # Terminal error: write to registry so enqueue-layer knows not to retry
    result["status"] = "error"
    registry.append_verdict(result)
    
elif n < 350:
    # Not enough data — increment persistent retry counter, then check
    new_count = _increment_retry(symbol, cov, mode)
    
    if new_count >= 2:
        # Terminal: insufficient data after 2 attempts
        result["status"] = "insufficient_data"
        registry.append_verdict(result)
    # new_count == 1: non-terminal, do NOT write to registry
    # Harvest will re-enqueue next cycle
        
else:
    # n >= 350: normal case
    result["status"] = "ok"
    registry.append_verdict(result)
```

**Key**: Non-terminal states (n < 350, retry count < 2) are **NOT written to registry**. Retry counter is **persisted to file** to survive process restarts. Only terminal states (error, insufficient_data, ok with n>=350) are written.

### 4.5 Tier Classifier Hard Gates (with ordinal mapping)

**File**: `cascade/tier_classifier.py`

**Critical fix**: Python string comparison `min(tier, "C")` does NOT work because 'A' < 'B' < 'C' in ASCII. Must use ordinal mapping.

```python
# Define ordinal mapping (lower rank = better tier)
TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
RANK_TO_TIER = {v: k for k, v in TIER_RANK.items()}

def cap_tier(tier: str, max_tier: str) -> str:
    """Cap tier at max_tier (e.g., cap_tier("A", "C") -> "C")."""
    tier_rank = TIER_RANK.get(tier, 4)
    max_rank = TIER_RANK.get(max_tier, 4)
    return RANK_TO_TIER[max(tier_rank, max_rank)]

# In tier_classifier.py, after computing tier:
# 1. gate_pass=False → max tier C
if not row.get("gate_pass", False):
    tier = cap_tier(tier, "C")

# 2. S-tier requires dir_acc >= effective_min + 0.02
# Use (row.get("dir_acc") or 0.0) to handle None values
effective_min = 0.52  # or fetch from evaluator config
dir_acc = row.get("dir_acc") or 0.0
if tier == "S" and dir_acc < effective_min + 0.02:
    tier = "A"  # demote to A
```

### 4.6 Fix _dead_families (Defensive Fix)

**File**: `scripts/sup_evidence.py:736`

**Change**: Count unique covariates, not verdict rows. **Filter out UNKNOWN/empty covariates** — malformed data should not have "voting power".

```python
# In sup_evidence.py, _dead_families function:
# OLD (buggy):
# if len(failure_rows) >= 4 and total_gate_pass == 0:
#     declare_dead(family)

# NEW (fixed):
unique_failed_covs = set()
for r in confirmatory_failures:
    cov = r.get("cov_override") or r.get("covariate")
    if cov:  # Only named, valid covariates count — UNKNOWN/empty excluded
        unique_failed_covs.add(cov)

if len(unique_failed_covs) >= 4 and total_gate_pass == 0:
    declare_dead(family)
```

**Rationale**: Even if duplicate verdicts slip through, _dead_families will not false-trigger because it counts unique named covariates, not rows. Malformed records (no covariate field) are excluded to prevent them from contributing to the death threshold.

---

## 5. Implementation Plan

### Phase 1: Data Cleanup (one-time script)

| Task | File | Description |
|------|------|-------------|
| T1.1 | `scripts/cleanup_verdict_registry.py` | Write cleanup script with process guard + file lock + atomic write |
| T1.2 | `tests/test_cleanup_verdict_registry.py` | Tests: archive count, dedup count, no gate_pass bias, cov field fallback |
| T1.3 | Run script | Stop slow loop → backup → cleanup → verify |
| T1.4 | `docs/superpowers/reports/2026-11-07-cleanup-verification.md` | Post-cleanup audit |

### Phase 2: Enqueue-Layer Dedup

| Task | File | Description |
|------|------|-------------|
| T2.1 | `scripts/sup_harvest.py` | Add `_load_evaluated_or_queued()` (checks verdicts + pending queue) |
| T2.2 | `scripts/sup_harvest.py` | Add `insufficient_data` terminal state handling |
| T2.3 | `tests/test_sup_harvest_dedup.py` | Tests: already-evaluated rejected, pending queue checked, insufficient_data terminal |
| T2.4 | Run slow loop | Verify no new duplicates after 1 cycle |

### Phase 3: Write-Layer — Remove Existing Dedup Logic

| Task | File | Description |
|------|------|-------------|
| T3.1 | `scripts/registry_lib.py` | **Remove existing dedup logic at :310** (currently uses `(batch_id, variant_id)` key). Write layer becomes append-only, no dedup check. |
| T3.2 | `tests/test_registry_lib.py` | Test: append_verdict allows same (symbol, cov) written multiple times (no write-layer dedup) |

### Phase 4: n<350 Write Guard + Terminal State

| Task | File | Description |
|------|------|-------------|
| T4.1 | `scripts/aligned_slow_loop.py` | n=0 → status=error + write; n<350 first retry → no write; n<350 fail_count>=2 → status=insufficient_data + write |
| T4.2 | `tests/test_aligned_slow_loop.py` | Tests: n=0 → error written; n<350 first (new_count=1) → not written; n<350 second (new_count=2) → insufficient_data written |

### Phase 5: Tier Classifier Hard Gates

| Task | File | Description |
|------|------|-------------|
| T5.1 | `cascade/tier_classifier.py` | Add `cap_tier()` with ordinal mapping; gate_pass=False → max C |
| T5.2 | `cascade/tier_classifier.py` | S-tier requires dir_acc ≥ 0.54 (with None handling) |
| T5.3 | `tests/test_tier_classifier.py` | Tests: gate_pass=False caps at C; S-tier dir_acc minimum; None values handled |

### Phase 6: Fix _dead_families

| Task | File | Description |
|------|------|-------------|
| T6.1 | `scripts/sup_evidence.py:736` | Count unique covariates, not verdict rows |
| T6.2 | `tests/test_sup_evidence.py` | Test: duplicate failure rows do not trigger family death |

---

## 6. Rollback Plan

- **Data cleanup**: Original file backed up to `aligned_verdicts.backup.<timestamp>.jsonl`; restore with `cp`
- **Code changes**: All changes in separate commits; revert with `git revert`
- **Enqueue dedup**: If it blocks valid proposals, disable by commenting out `_load_evaluated_or_queued()` check

---

## 7. Testing Strategy

### Unit Tests

| Test | File | Verifies |
|------|------|----------|
| `test_cleanup_preserves_archive` | `tests/test_cleanup_verdict_registry.py` | Archive contains all old protocol + n=0 records |
| `test_cleanup_dedup_by_latest` | `tests/test_cleanup_verdict_registry.py` | Dedup keeps latest decided_at, not gate_pass |
| `test_cleanup_no_gate_pass_bias` | `tests/test_cleanup_verdict_registry.py` | sr+vwap_deviation: 42 runs 1 pass → keeps latest |
| `test_cleanup_cov_field_fallback` | `tests/test_cleanup_verdict_registry.py` | cov_override takes precedence, fallback to covariate |
| `test_harvest_rejects_evaluated` | `tests/test_sup_harvest_dedup.py` | Combo with valid verdict not re-enqueued |
| `test_harvest_checks_pending` | `tests/test_sup_harvest_dedup.py` | Combo in pending queue not re-enqueued |
| `test_harvest_insufficient_data_terminal` | `tests/test_sup_harvest_dedup.py` | insufficient_data status treated as evaluated |
| `test_registry_allows_multiple_appends` | `tests/test_registry_lib.py` | append_verdict allows same (symbol, cov) written multiple times (no write-layer dedup) |
| `test_slow_loop_n0_status_error` | `tests/test_aligned_slow_loop.py` | n=0 → status=error |
| `test_slow_loop_insufficient_data` | `tests/test_aligned_slow_loop.py` | n<350 after 2 tries → insufficient_data |
| `test_tier_gate_pass_false_caps_c` | `tests/test_tier_classifier.py` | gate_pass=False → tier ≤ C (ordinal mapping) |
| `test_tier_s_dir_acc_minimum` | `tests/test_tier_classifier.py` | S-tier requires dir_acc ≥ 0.54 |
| `test_tier_none_handling` | `tests/test_tier_classifier.py` | None dir_acc does not crash (uses `or 0.0`) |
| `test_dead_families_unique_covs` | `tests/test_sup_evidence.py` | Duplicate rows do not trigger family death |
| `test_dead_families_excludes_unknown` | `tests/test_sup_evidence.py` | UNKNOWN/empty covariates not counted toward death threshold |
| `test_cleanup_keeps_terminal_states` | `tests/test_cleanup_verdict_registry.py` | status=error records kept in cleaned file (not archived) |
| `test_cleanup_dedups_pending_queue` | `tests/test_cleanup_verdict_registry.py` | Pending queue deduped + already-done items removed |
| `test_retry_counter_persists` | `tests/test_aligned_slow_loop.py` | Retry counter survives process restart (file-based) |

### Integration Tests

- Run slow loop for 1 cycle after all fixes
- Verify: no new duplicates in aligned_verdicts.jsonl
- Verify: no n=0 verdicts written with status=ok
- Verify: S-tier list matches expected (no low dir_acc S-tiers, no gate_pass=False S-tiers)
- Verify: _dead_families does not false-trigger on duplicate failure rows

---

## 8. What NOT To Do (6 Traps)

| Trap | Why It's Wrong |
|------|----------------|
| **Dedup at write layer (v2 §4.3)** | **DEADLOCK**: write-layer blocks terminal state write → infinite retry loop. v3 removes write-layer dedup entirely. |
| **Keep gate_pass=True when deduping** | Survivorship bias: sr+vwap_deviation 42 times only 1 pass → keeping pass erases 41 falsifications |
| **Backfill old records with current fingerprint** | 42 old gate_pass=True would mix into valid pool, polluting signals |
| **Change n_eff to relative ranking** | tier_classifier is streaming single-item; all n=588 → n_eff always=73 → ranking amplifies float noise |
| **Use Python string min() for tier capping** | 'A' < 'C' in ASCII → min("A", "C") returns "A" (not capped!); must use ordinal mapping |
| **Write non-terminal states to registry** | n<350 first retry should NOT be written — only terminal states (error/insufficient_data/ok with n>=350) |

---

## 9. Success Criteria

| Criterion | Target |
|-----------|--------|
| Registry contains only current protocol f02b2a43 | ✅ |
| No duplicate (symbol, cov_override, run_mode) in registry | ✅ |
| No n=0 verdicts with status=ok in registry | ✅ |
| Enqueue-layer dedup prevents new duplicates (checks verdicts + pending) | ✅ |
| Insufficient data combos reach terminal state (no infinite retry) | ✅ |
| gate_pass=False verdicts never reach S/A tier | ✅ |
| _dead_families counts unique covariates, not rows | ✅ |
| All tests pass | ✅ |

---

## 10. Resolved Questions

| Question | Resolution |
|----------|------------|
| **run_mode missing in old data** | Default to "exploration": `v.get("run_mode") or "exploration"` |
| **cov_override vs covariate** | Use fallback chain: `v.get("cov_override") or v.get("covariate") or "UNKNOWN"` |
| **effective_min accessibility** | Hardcode 0.52 for now; can fetch from evaluator config later |
| **None value handling** | Use `(row.get("dir_acc") or 0.0)` to convert None to 0.0 before comparison |
| **Write-layer dedup causing deadlock** | v3: Remove write-layer dedup entirely; primary dedup at enqueue layer only |
| **status="error" infinite loop** | v3: Add to TERMINAL_STATUSES set; enqueue-layer treats as evaluated |
| **Timsort keeps earliest not latest** | v3: Use `(decided_at, line_idx)` dual-key descending sort |
| **Archive append non-idempotent** | v3: Use timestamped archive filename |

---

## Appendix A: Key File Locations

| File | Purpose |
|------|---------|
| `task_FM/config/aligned_verdicts.jsonl` | Verdict registry (target of cleanup) |
| `task_FM/config/aligned_pending.jsonl` | Pending queue (checked by enqueue dedup) |
| `scripts/registry_lib.py` | Verdict write layer (dedup key at :310) |
| `scripts/sup_harvest.py` | Harvest enqueue layer (add dedup here) |
| `scripts/aligned_slow_loop.py` | Slow loop evaluator (add n=0 guard + terminal state) |
| `cascade/tier_classifier.py` | Tier scoring (add ordinal cap + dir_acc gate) |
| `scripts/sup_evidence.py:736` | _dead_families logic (fix to count unique covs) |
| `task_FM/evaluations/fm_eval/evaluator.py` | Gate logic (min_samples=350, min_n_eff=50) |

## Appendix B: Historical Context

| Commit | Lines | Notes |
|--------|-------|-------|
| 38ae77d | 935 | Backup sync merge (stash conflict) |
| 510db60 | 1557 | Historical peak |
| d3e2679 (HEAD) | 590 | After manual cleanups |
| working tree | 640 | Background slow loop kept appending |

## Appendix C: v1 → v2 Revision Summary

| Issue | v1 | v2 Fix |
|-------|----|---------
| Tier capping logic | `min(tier, "C")` (broken) | Ordinal mapping `cap_tier()` |
| Enqueue dedup scope | Only verdicts | Verdicts + pending queue |
| n=0 retry loop | status=error → re-enqueue | Terminal state `insufficient_data` |
| File write safety | Direct overwrite | Process guard + flock + atomic replace |
| _dead_families fix | Not included | Phase 6: count unique covs |
| Dedup "keep latest" bias | Not addressed | Documented: latest may be the 1 pass |
| Write-layer dedup key | (fingerprint, variant_id, mode) | (fingerprint, symbol, cov, mode) |
| Performance | O(M×N) disk scan | O(1) in-memory set |
| Open questions | 4 unresolved | All resolved in §10 |

## Appendix D: v2 → v3 Revision Summary (State Machine Deadlock Fix)

| # | v2 Issue | Severity | v3 Fix |
|---|----------|----------|--------|
| 1 | **BLOCKER**: Write-layer dedup blocks terminal state write → infinite retry deadlock | Critical | **Remove write-layer dedup entirely** (§4.3); primary dedup at enqueue layer only |
| 2 | **CRITICAL**: status="error" not in terminal states → infinite loop | Critical | Add `TERMINAL_STATUSES = {"insufficient_data", "error", "fatal_error"}` (§4.2) |
| 3 | **HIGH**: Harvest batch not self-deduping | High | Add `evaluated_set.add(key)` after enqueue (§4.2) |
| 4 | **HIGH**: Timsort stability keeps earliest not latest when no decided_at | High | Use `(decided_at, line_idx)` dual-key sort (§4.1) |
| 5 | **MED**: Process guard shell syntax `cmd1 || cmd2` wrong | Med | Use `psutil` for process checking (§4.1) |
| 6 | **MED**: Dangling code block in §4.2 | Med | Integrate terminal state logic into `_load_evaluated_or_queued()` body |
| 7 | **MED**: Field canonicalization missing | Med | Normalize `cov_override` + `run_mode` before write (§4.1) |
| 8 | **MED**: Archive append non-idempotent | Med | Use timestamped archive filename (§4.1) |
| 9 | **NEW**: Non-terminal states written to registry | High | Only write terminal states (error/insufficient_data/ok with n>=350) (§4.4) |

### State Machine Diagram (v3)

```
Proposal → Slow Loop Run
    │
    ├─ n == 0        → WRITE status="error" (terminal)
    │
    ├─ n < 350       → fail_count < 2? → NO WRITE (retry in memory)
    │                  fail_count >= 2? → WRITE status="insufficient_data" (terminal)
    │
    └─ n >= 350      → WRITE status="ok" (terminal)
```

**Key insight**: Only terminal states are written to registry. Non-terminal retries (n<350, first attempt) are tracked in persistent file, preventing write-layer conflicts.

## Appendix E: v3 → v4 Revision Summary (Death Resurrection + Persistent Retry)

| # | v3 Issue | Severity | v4 Fix |
|---|----------|----------|--------|
| 1 | **BLOCKER**: §4.1 cleanup archives n=0 terminal states → "death resurrection" loop | Critical | §4.1: KEEP condition includes `status in TERMINAL_STATUSES` |
| 2 | **HIGH**: §4.4 in-memory retry counter resets on process restart | High | §4.4: File-based retry state `.slow_loop_retry_state.json` |
| 3 | **HIGH**: §4.1 doesn't clean pending queue | High | §4.1: Added pending queue dedup + already-done removal |
| 4 | **DOC**: §7 test contradicts §4.3 (no write-layer dedup) | Med | §7: Renamed to `test_registry_allows_multiple_appends` |
| 5 | **DOC**: Phase 3 says "NO CHANGES" but dedup exists | Med | Phase 3: Renamed "Remove Existing Dedup Logic" |
| 6 | **MED**: §4.6 _dead_families counts UNKNOWN as factor | Med | §4.6: Filter out empty/UNKNOWN covariates |
| 7 | **MED**: psutil race condition on process iteration | Med | §4.1: Added `NoSuchProcess`/`AccessDenied` exception handling |
| 8 | **MED**: `is_valid_pass` naming misleading | Med | §4.2: Renamed to `is_complete_eval` |

### New Tests Added (v4)

| Test | Verifies |
|------|----------|
| `test_cleanup_keeps_terminal_states` | status=error records kept in cleaned file (not archived) |
| `test_cleanup_dedups_pending_queue` | Pending queue deduped + already-done items removed |
| `test_retry_counter_persists` | Retry counter survives process restart (file-based) |
| `test_dead_families_excludes_unknown` | UNKNOWN/empty covariates not counted toward death |
