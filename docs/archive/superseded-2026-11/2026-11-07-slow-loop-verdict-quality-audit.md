# Slow Loop Verdict Quality Audit (Revised v2)

> Audit date: 2026-11-07
> Revision date: 2026-11-07 (v2, rewritten per user correction)
> Baseline: master @ d3e2679 + working tree 640 lines
> v1->v2 key corrections: all stats re-filtered by current protocol fingerprint f02b2a43;
>   redundancy 78.4% -> 56.9% (all) / 45.6% (current);
>   added dead-family false-kill risk; corrected jd+vor S-tier attribution (belongs to old protocol bd851c9c, not current)

## Summary

| Metric | All (640) | Current f02b2a43 (375) |
|--------|---------------|--------------------------|
| Unique (symbol, cov_override) combos | 276 | 204 |
| Redundant verdicts | 364 (56.9%) | 171 (45.6%) |
| gate_pass total | - | 148/375 (39.5%) |
| S-tier | 53 | 53 |

The v1 report computed stats on all data mixed across 4 protocol fingerprint generations,
causing S-tier count, redundancy rate, and TOP combo ranking to all be distorted.
This version re-runs all stats after filtering to current protocol f02b2a43.

---

## 1. Tier Distribution (current protocol f02b2a43, 375 verdicts)

| Tier | Count | Pct | Unique combos | gate_pass |
|------|-------|-----|---------------|-----------|
| S | 53 | 14.1% | 44 | 52/53 (98.1%) |
| A | 98 | 26.1% | 64 | 59/98 (60.2%) |
| B | 135 | 36.0% | 101 | 30/135 (22.2%) |
| C | 65 | 17.3% | 50 | 7/65 (10.8%) |
| D | 24 | 6.4% | 8 | 0/24 (0.0%) |

The v1 S-tier=65 was inflated by mixing in old protocol data (v1 had 631 lines).
After filtering: 53 S-tier verdicts cover 44 unique combos,
of which 8 combos were repeatedly judged (cf+calendar_cyclical 3次, sh+rsi6 2次, cf+gated_slope 2次, ta+calendar_cyclical 2次, lh+calendar_cyclical 2次, etc).

---

## 2. S-tier Analysis

- Current protocol S-tier: 53, gate_pass: 52 (98.1%), gate_pass=False: 1
- dir_acc range: 0.513 - 0.611
- All 53 S-tier run_mode: exploration=53, confirmation=0
- 18 S-tier combos also appear in old protocol data (overlap), indicating cross-protocol stability

### S-tier Systematic Bias (same as v1)
- S-tier lowest dir_acc=0.513, below S-tier 40-point threshold (dir_acc>=0.56)
- These S-tiers did not get 40 points from dir_acc; other dimensions compensated
- n_eff scoring ceiling=73 exactly equals max effective sample size, removing discrimination power

---

## 3. Sample Size Compliance

### Gate Hard Threshold (evaluator.py)

Gate requires: n >= 350 AND n_eff >= 50 AND dir_acc >= effective_min

| Metric | Current protocol value |
|--------|----------------------|
| n range | 1-588, avg=531 |
| n_eff range | 1-73, avg=65.9 |
| n>0 and n<350 | 39 (current protocol) |

### Key Clarifications
- **min_samples=350 refers to nominal sample count n, NOT n_eff**
- n_eff is Bartlett effective sample size; with 1h horizon overlapping window autocorrelation=0.9, 588 nominal samples compress to ~73 effective samples
- This is statistically correct behavior, not a bug
- Current protocol has 0 n=0 records; all 77 n=0 records belong to old/missing protocol, current f02b2a43 has zero n=0

---

## 4. Duplicate Verdict Analysis

### 4.1 Statistics

**All data (4 protocol generations mixed, 640 verdicts)**:

| Metric | Value |
|--------|-------|
| Total verdicts | 640 |
| Unique (symbol, cov_override) combos | 276 |
| Redundant verdicts | 364 (56.9%) |

> v1 report: 631 - 274 = 495 (78.4%). **Arithmetic error**: 631 - 274 = 357, not 495.
> Since each of the 274 combos has 1 legitimate first verdict, redundancy = total - unique.
> Data grew to 640 lines (background slow loop kept appending), corrected all-data redundancy: 364 (56.9%).

**Current protocol (f02b2a43, 375 verdicts)**:

| Metric | Value |
|--------|-------|
| Verdicts | 375 |
| Unique combos | 204 |
| Redundant verdicts | 171 (45.6%) |
| Repeated combos | 98 |

### 4.2 Current Protocol TOP 10 Repeated Combos

| symbol + cov_override | Count | gate_pass | Tier distribution |
|----------------------|-------|-----------|-------------------|
| sr + vwap_deviation | 22 | 0/22 | A(22) |
| jd + vor | 18 | 0/18 | C(1), D(17) |
| rb + bb_squeeze | 6 | 0/6 | B(6) |
| jd + stddev | 5 | 0/5 | B(2), C(3) |
| sh + rsi6 | 4 | 4/4 | A(2), S(2) |
| cf + gated_slope | 4 | 4/4 | B(2), S(2) |
| cf + rsi_state | 4 | 1/4 | A(1), B(1), C(1), S(1) |
| ta + crack_spread_slope | 4 | 4/4 | A(4) |
| i + reversal_shadow | 4 | 2/4 | A(2), B(2) |
| bu + nvi | 4 | 1/4 | A(1), C(3) |

### 4.3 All-data TOP Repeated Combos (including old protocols)

| symbol + cov_override | Count | gate_pass | Protocol split |
|----------------------|-------|-----------|----------------|
| sr + vwap_deviation | 43 | 1/43 | f02b2a43:22, MISSING:19, bd851c9c:1, 91ab913e:1 |
| jd + vor | 42 | 1/42 | MISSING:22, f02b2a43:18, bd851c9c:1, 91ab913e:1 |
| jd + stddev | 18 | 0/18 | MISSING:13, f02b2a43:5 |

> v1 reported jd+vor 41 times with 1 S-tier; that S-tier came from old protocol 91ab913e (not current).
> Under current protocol, jd+vor has 18 verdicts, 0 S-tier, tiers: {'C': 1, 'D': 17}.

### 4.4 Root Causes

**Direct root cause**: registry_lib.py:310 dedup key is `(batch_id, variant_id)` which includes batch_id,
and `variant_id` contains `experiment_fingerprint` (varies with data window), so the same (symbol, cov_override)
produces different variant_ids across batches, bypassing dedup.

**Same variant_id also duplicated**: 640 verdicts -> 532 unique variant_ids, 108 same-ID duplicates.
Cause: stash merge conflict (commit 38ae77d ballooned from 469 to 935 lines) + sup_harvest.py
existing set only valid for current snapshot; fingerprint change -> new vid -> bypasses dedup.

**MOST CRITICAL IMPACT: False triggering of _dead_families**

sup_evidence.py:736 _dead_families judges by verdict row count: a family with >=4 confirmatory
DM ok verdicts and 0 gate_pass is declared dead. Duplicate verdicts flood families with failure rows:

- jd+stddev judged 18 times (all data), 0/18 gate_pass, cov_family: {'volatility': 6, 'unknown': 12}
- volatility family accumulates many failure verdicts on jd (jd+stddev + jd+vor etc), easily hitting min_ok=4 threshold
- Once volatility is falsely declared dead, ALL future covariates in that family (including potentially valid ones) are unconditionally rejected
- **This is the #1 reason immediate cleanup is required**

---

## 5. Protocol Fingerprint Mixing

| Fingerprint | Count | Pct | Notes |
|-------------|-------|-----|-------|
| f02b2a43 (current) | 375 | 58.6% | 2026-10-01 to present |
| MISSING (field absent) | 220 | 34.4% | old protocol, no fingerprint field |
| bd851c9c (old) | 27 | 4.2% | historical version |
| 91ab913e (old) | 18 | 2.8% | historical version |

220 no-fingerprint verdicts contain 42 gate_pass=True, potentially carrying stale window semantics that would pollute the valid pool if mixed.

---

## 6. Data Integrity

| Check | Result |
|-------|--------|
| wc -l | 640 (background slow loop kept appending during audit) |
| JSON parse failures | 0 |
| Total fields | 94 (extremely bloated schema) |
| protocol_fingerprint field missing | 220 (34.4%) |
| n=0 or n_eff=0 | 77 (all belong to old/missing protocol) |
| mape type | float + NoneType inconsistent |
| tier missing | 1 (all data), 0 in current protocol |
| decided_at range (current) | 2026-10-01 to 2026-11-07 |

---

## 7. Hidden Issues List

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | **_dead_families falsely triggered by duplicate failure rows** | Critical | Entire covariate family unconditionally rejected |
| 2 | **220 no-fingerprint verdicts mixed in** | High | 42 gate_pass=True polluting valid pool |
| 3 | **Current protocol 45.6% redundancy** | High | Noise + storage waste + dead-family false kills |
| 4 | **77 n=0 empty verdicts** (old protocol) | High | All n_eff=0, legacy leftovers |
| 5 | **n_eff scoring ceiling=73** | Med | n_eff dimension has no S/A discrimination power |
| 6 | **mape field type inconsistent** | Med | Downstream .get() does not crash but semantics fuzzy |
| 7 | **1 tier missing** (all data) | Low | Current protocol has zero such cases |
| 8 | **4 protocol fingerprint generations coexist** | Med | Same registry mixes multiple generations |

---

## 8. Revised Fix Recommendations

### 8.1 Four-Step Cleanup (replaces original P0~P2)

**Step 1: Losslessly isolate old protocol and empty records**
- Backup original file
- Extract records where protocol_fingerprint != f02b2a43 (220 MISSING + 27 bd851c9c + 18 91ab913e = 265)
  + n=0 or n_eff=0 records -> aligned_verdicts.archive.jsonl
- Keep only current protocol valid records in original file

**Step 2: Dedup within current protocol by latest time**
- In f02b2a43 valid records, group by (symbol, cov_override, run_mode)
- Keep only 1 record per group: n>0 and latest decided_at
- **Do NOT filter by gate_pass** (avoids survivorship bias: sr+vwap_deviation 42 times only 1 gate_pass,
  keeping gate_pass=True erases 41 falsifications)
- Immediately relieves _dead_families false-kill from duplicate failure rows

**Step 3: Re-run audit stats on clean dataset**
- Re-output Tier distribution and S-tier list on cleaned data
- Verify which of 53 S-tier (44 unique combos) survive dedup

**Step 4: Code-level recurrence prevention**
- sup_harvest.py enqueue: add interception for already-evaluated (symbol, cov_override) under current protocol
- aligned_slow_loop.py: block n=0 empty results from being written
- tier_classifier.py: gate_pass==False must not receive S/A tier

### 8.2 Original Suggestion Traps (5 cases with corrections)

| Original suggestion | Trap | Correct approach |
|---------------------|------|------------------|
| P0: Dedup before write in registry_lib.py by (symbol, cov_override, fingerprint) | 100% wasted compute (backtest already ran); write-layer discard -> variant_id not stored -> next harvest thinks unevaluated -> re-enqueue (death loop) | **Move dedup to sup_harvest.py enqueue layer**: check if current fingerprint already has status=ok and n>=350 valid verdict for that combo; write-layer dedup key changed to (fingerprint, variant_id, run_mode) |
| P2: Keep gate_pass=True with largest n | Survivorship bias: sr+vwap_deviation 42 times only 1 gate_pass, keeping gate_pass=True erases 41 falsifications | **Strict protocol isolation + latest time retention**: do not pick by gate_pass, keep the 1 record with latest decided_at and n meeting threshold |
| P1: Backfill 220 no-fingerprint records with current fingerprint | After backfill, 42 old gate_pass=True mix into valid pool, polluting signals | **Do NOT backfill current fingerprint**: mark uniformly as legacy_unfingerprinted or archive out |
| P1: Change n_eff to relative ranking | 1) tier_classifier is streaming single-item scoring, cannot get quantiles 2) all n=588 -> n_eff always=73, ranking amplifies float noise | **Keep n_eff>=73 scores 10 points**, fix two real gaps: gate_pass=False caps at B/C; S-tier requires dir_acc>=effective_min+0.02 |
| P2: Omit mape field when None | Omitted key -> KeyError; downstream .get() returns None anyway | **Keep schema keys complete**, fix aligned_slow_loop.py to set status=error when n=0 |

---

## Appendix

### Code Fact Verification Commands

```bash
# Total line count
wc -l task_FM/config/aligned_verdicts.jsonl

# Protocol fingerprint distribution
python3 -c "import json; from collections import Counter;
lines = [json.loads(l) for l in open('task_FM/config/aligned_verdicts.jsonl') if l.strip()];
print(Counter(str(v.get('protocol_fingerprint','MISSING'))[:12] for v in lines))"

# _dead_families logic location
grep -n '_dead_families' scripts/sup_evidence.py
```

### Historical Backtrack (key nodes)

| commit | lines | notes |
|--------|-------|-------|
| 38ae77d | 935 | Backup sync merge (stash conflict caused line count explosion) |
| 510db60 | 1557 | 28 new verdicts entered (historical peak) |
| working tree | 640 | current (after multiple cleanups) |

v1->v2 revision driven by user correction feedback; all statistics re-verified by current protocol fingerprint filtering.
