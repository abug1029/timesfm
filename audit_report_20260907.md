# TimesFM Futures Database Audit Report

**Date:** 2026-09-07 21:53 UTC
**Auditor:** Automated audit script (`audit_futures_v2.py`)
**Scope:** 28 symbol databases in `~/timesfm/db/`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Databases found | 28 |
| Total daily rows | ~55,000+ across all symbols |
| Total 1H rows | ~270,000+ across all symbols |
| Data freshness | All symbols current to expected latest date |
| OHLC integrity | PASS (no inconsistencies found) |
| Price integrity | PASS (no zero/negative prices) |
| Volume/OI integrity | PASS (no negative values) |
| Indicator warmup | 25/28 symbols OK, 3 have recent NULL gaps |
| CCL labels | ALL 28 symbols have empty-string bug |
| Contract continuity | 27/28 clean, TA has stale legacy contracts |
| **Data Health Score** | **72/100** |

---

## Finding 1: Empty-String CCL Labels -- MEDIUM (systemic)

**Severity:** MEDIUM
**Affected:** ALL 28 symbols, both daily and 1H tables
**Impact:** 1 row per table per symbol has `ccl_value=NULL` and `ccl_label=''`

**Root cause:** The CCL indicator computation writes an empty string instead of NULL for rows where ccl_value cannot be computed.

**Fix:**
```sql
UPDATE kline_1d SET ccl_label = NULL WHERE ccl_label = '';
UPDATE kline_1h SET ccl_label = NULL WHERE ccl_label = '';
```

---

## Finding 2: Recent Indicator NULL Gaps -- HIGH

**Severity:** HIGH
**Affected:** 3 symbols (cf, jm, sr) in daily table; 1 symbol (ta) in 1H table

### cf (daily): 2 extra NULL rows
- Dates: 2026-09-07, 2026-09-04
- All 15 indicator columns NULL despite valid OHLCV prices
- Root cause: TqSdk data updated but indicator pipeline did not recompute these 2 rows

### jm (daily): 4 extra NULL rows
- Dates: 2026-09-07, 2026-09-04, 2026-09-03, 2026-09-02
- All 15 indicator columns NULL despite valid prices
- Root cause: Same as cf -- 4 recent rows missed indicator calculation

### sr (daily): 2 extra NULL rows
- Dates: 2026-09-07, 2026-09-04
- Same pattern as cf

### ta (1H): 38 extra NULL rows beyond warmup (57 total vs expected 19)
- Root cause: Historical non-MAIN contract rows (TA2609, TA2611) with missing indicators
- These 3,855 rows from legacy contracts have NULL indicators
- The recent NULL rows are a subset of the larger legacy data problem

**Fix:** Re-run indicator calculation pipeline for the affected symbols:
```bash
# For cf, jm, sr daily: recalculate indicators for recent rows
# For ta 1H: filter out non-MAIN contract rows, then recalculate
```

---

## Finding 3: TA Stale Legacy Contracts in 1H Table -- MEDIUM

**Severity:** MEDIUM
**Affected:** TA symbol only

The 1H table contains 3,855 rows from legacy contracts:
- TA2609: 2,802 rows (2016-01-04 to 2026-07-29)
- TA2611: 1,053 rows (2016-02-19 to 2026-07-29)

These are historical specific contracts that have expired. Only TA_MAIN (9,998 rows, current to 2026-09-07 21:00) should remain.

**Fix:**
```sql
DELETE FROM kline_1h WHERE contract_code IN ('TA2609', 'TA2611');
```

---

## Finding 4: Extreme Daily Moves -- INFO

**Severity:** INFO (review for data errors)
**Affected:** 18 symbols

| Symbol | Count | Notes |
|--------|-------|-------|
| fu | 17 | Historical volatility, verify early rows |
| jm | 16 | Coking coal, known for limit moves |
| jd | 14 | Eggs futures, seasonal spikes |
| sc | 13 | Crude oil, 2020 negative price era |
| i | 8 | Iron ore, policy-driven moves |
| lh | 7 | Live hogs, African swine fever period |
| cj | 6 | Jujube, new listing volatility |
| fg | 4 | Glass, construction cycle |
| sh | 3 | Industrial silicon |
| bu | 3 | Asphalt |
| m | 3 | Soybean meal |
| ao | 3 | Aluminum oxide (new listing) |
| bz | 1 | Benzene (new listing) |
| eg | 1 | Ethylene glycol |
| ma | 1 | Methanol |
| pp | 1 | Polypropylene |
| ur | 1 | Urea |
| p | 2 | Palm oil |

These are likely real market events (limit moves, COVID crash, new contract listing volatility) rather than data errors, but should be reviewed individually.

---

## Finding 5: Missing vs Extra DB Files -- INFO

The current 28 DB files differ from the original task specification:

| Missing (9) | Extra (9) |
|-------------|-----------|
| hc, j, l, ni, ru, sa, sn, v, wr | bz, eb, fu, ma, oi, px, sc, sh, ss |

This appears to be an intentional symbol list refresh -- the 9 "extra" symbols are actively traded futures that replaced the 9 "missing" ones. No data integrity issue.

---

## Finding 6: Daily Gaps >7 Days -- INFO

**Severity:** INFO (expected)
**Affected:** All symbols

All gaps >7 days correspond to Chinese market holidays:
- Spring Festival (Jan/Feb, typically 7-10 trading days)
- National Day (Oct 1-7, typically 8-11 trading days)
- Qingming/May Day/Dragon Boat/Mid-Autumn (shorter gaps)

The FU symbol shows a 49-day and 91-day gap in early 2016, likely reflecting a contract rollover or listing transition.

---

## Data Freshness Verification

| Check | Result |
|-------|--------|
| Daily latest date (night session symbols) | 2026-09-08 -- PASS |
| Daily latest date (no-night: cj,jd,lh,ur) | 2026-09-07 -- PASS |
| 1H latest bar (night session) | 2026-09-07 21:00 -- PASS |
| 1H latest bar (no-night) | 2026-09-07 14:00 -- PASS |
| Updated_at timestamps | All updated 2026-09-07 13:25-13:45 UTC -- PASS |
| Contract codes (daily) | All use _CONT suffix -- PASS |
| Contract codes (1H) | 27/28 use _MAIN only, TA has extras -- SEE Finding 3 |

---

## Per-Symbol Health Summary

| Sym | Status | Issue |
|-----|--------|-------|
| ao | OK | Only empty-string CCL label |
| bu | OK | Only empty-string CCL label |
| bz | OK | Only empty-string CCL label |
| **cf** | **HIGH** | 2 recent rows with NULL indicators + CCL |
| cj | OK | Only empty-string CCL label |
| eb | OK | Only empty-string CCL label |
| eg | OK | Only empty-string CCL label |
| fg | OK | Only empty-string CCL label |
| fu | OK | Only empty-string CCL label |
| i | OK | Only empty-string CCL label |
| jd | OK | Only empty-string CCL label |
| **jm** | **HIGH** | 4 recent rows with NULL indicators + CCL |
| lh | OK | Only empty-string CCL label |
| m | OK | Only empty-string CCL label |
| ma | OK | Only empty-string CCL label |
| oi | OK | Only empty-string CCL label |
| p | OK | Only empty-string CCL label |
| pp | OK | Only empty-string CCL label |
| px | OK | Only empty-string CCL label |
| rb | OK | Only empty-string CCL label |
| sc | OK | Only empty-string CCL label |
| sh | OK | Only empty-string CCL label |
| sp | OK | Only empty-string CCL label |
| **sr** | **HIGH** | 2 recent rows with NULL indicators + CCL |
| ss | OK | Only empty-string CCL label |
| **ta** | **HIGH** | 1H: 3,855 legacy contract rows + CCL |
| ur | OK | Only empty-string CCL label |
| y | OK | Only empty-string CCL label |

---

## Actionable Recommendations (Priority Order)

### P1 -- Re-run indicator pipeline for cf, jm, sr
```bash
# Re-calculate indicators for recent rows that have prices but NULL indicators
# cf: 2026-09-04, 2026-09-07
# jm: 2026-09-02, 2026-09-03, 2026-09-04, 2026-09-07
# sr: 2026-09-04, 2026-09-07
```

### P2 -- Fix empty-string CCL labels (all 28 symbols)
```sql
UPDATE kline_1d SET ccl_label = NULL WHERE ccl_label = '';
UPDATE kline_1h SET ccl_label = NULL WHERE ccl_label = '';
```

### P3 -- Clean TA legacy contracts from 1H table
```sql
DELETE FROM kline_1h WHERE contract_code IN ('TA2609', 'TA2611');
```

### P4 -- Add guard to indicator pipeline
Ensure the indicator computation script runs AFTER all price data is updated, and verify no rows are left with valid prices but NULL indicators. Add a post-update validation step.

### P5 -- Prevent legacy contract accumulation
The 1H data fetch should only pull _MAIN contract data. Add a filter to prevent specific contract codes (e.g., TA2609) from being written to the 1H table.
