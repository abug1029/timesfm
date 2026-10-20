# Gate Pass Feature Analysis Report

> Generated: 2026-10-20
> Data source: `task_FM/config/aligned_verdicts.jsonl`
> Deduplication: first occurrence per variant_id

## Overview

| Metric | Value |
|--------|-------|
| Total verdicts (deduped) | 593 |
| Gate Pass | 196 (33.1%) |
| Gate Fail | 397 (66.9%) |
| Pass avg dir_acc | 0.531 |
| Fail avg dir_acc | 0.457 |
| dir_acc gap | +0.074 |

## Symbol Gate Pass Rate (Top 15)

| Symbol | Pass Rate | Pass/Total |
|--------|-----------|------------|
| ta | 100.0% | 6/6 |
| ur | 100.0% | 1/1 |
| ao | 60.0% | 3/5 |
| sh | 54.5% | 6/11 |
| cf | 50.0% | 8/16 |
| ss | 49.2% | 31/63 |
| i | 47.4% | 9/19 |
| lh | 45.5% | 25/55 |
| cj | 43.2% | 19/44 |
| sr | 37.5% | 21/56 |
| p | 34.8% | 8/23 |
| bu | 33.3% | 1/3 |
| m | 28.0% | 21/75 |
| rb | 25.3% | 20/79 |
| jd | 22.5% | 16/71 |

## Family Gate Pass Rate (Top 10)

| Family | Pass Rate | Pass/Total |
|--------|-----------|------------|
| calendar | 40.4% | 21/52 |
| term_structure | 37.9% | 39/103 |
| momentum | 35.9% | 92/256 |
| inventory | 26.3% | 25/95 |
| volatility | 24.4% | 19/78 |
| unknown | 0.0% | 0/9 |

## Efficient Symbol-Family Combinations (Top 15)

| Combo | Pass Rate | Pass/Total |
|-------|-----------|------------|
| ta_term_structure | 100.0% | 4/4 |
| cf_calendar | 100.0% | 3/3 |
| ta_calendar | 100.0% | 2/2 |
| p_calendar | 75.0% | 3/4 |
| p_inventory | 75.0% | 3/4 |
| lh_calendar | 75.0% | 3/4 |
| ss_calendar | 75.0% | 3/4 |
| sr_term_structure | 66.7% | 6/9 |
| i_term_structure | 66.7% | 2/3 |
| ao_momentum | 60.0% | 3/5 |
| ss_term_structure | 57.1% | 8/14 |
| lh_volatility | 57.1% | 4/7 |
| ss_momentum | 56.0% | 14/25 |
| sh_momentum | 54.5% | 6/11 |
| cj_momentum | 50.0% | 11/22 |

## High Win-Rate Combos (rate >= 40%, samples >= 3)

| Combo | Pass Rate | Pass/Total |
|-------|-----------|------------|
| ta_term_structure | 100.0% | 4/4 |
| cf_calendar | 100.0% | 3/3 |
| p_calendar | 75.0% | 3/4 |
| p_inventory | 75.0% | 3/4 |
| lh_calendar | 75.0% | 3/4 |
| ss_calendar | 75.0% | 3/4 |
| sr_term_structure | 66.7% | 6/9 |
| i_term_structure | 66.7% | 2/3 |
| ao_momentum | 60.0% | 3/5 |
| ss_term_structure | 57.1% | 8/14 |
| lh_volatility | 57.1% | 4/7 |
| ss_momentum | 56.0% | 14/25 |
| sh_momentum | 54.5% | 6/11 |
| cj_momentum | 50.0% | 11/22 |
| cj_term_structure | 50.0% | 4/8 |
| i_inventory | 50.0% | 3/6 |
| sr_volatility | 50.0% | 3/6 |
| cj_volatility | 50.0% | 2/4 |
| lh_momentum | 46.2% | 12/26 |
| cf_momentum | 44.4% | 4/9 |
| m_calendar | 40.0% | 2/5 |

## Mechanism Keyword Frequency (Top 20)

| Keyword | Count |
|---------|-------|
| slope | 79 |
| crack | 72 |
| spread | 72 |
| gated | 57 |
| calendar | 53 |
| cyclical | 52 |
| oi | 50 |
| momentum | 50 |
| ccl | 33 |
| vor | 32 |
| basis | 31 |
| bb | 31 |
| squeeze | 31 |
| vwap | 30 |
| deviation | 30 |
| reversal | 29 |
| shadow | 29 |
| nvi | 29 |
| rsi6 | 26 |
| hurst | 25 |

## Tier Distribution

| Tier | Count | Share |
|------|-------|-------|
| S | 70 | 11.8% |
| A | 105 | 17.7% |
| B | 239 | 40.3% |
| C | 171 | 28.8% |
| D | 8 | 1.3% |

## Key Findings

1. **High pass rate symbols**: `ta` (100%, 6/6), `ao` (60%, 3/5), `sh` (54.5%, 6/11), `cf` (50%, 8/16)
2. **High pass rate families**: `calendar` (40.4%), `term_structure` (37.9%), `momentum` (35.9%)
3. **Best combos**: `ta_term_structure` (100%), `cf_calendar` (100%), `ta_calendar` (100%)
4. **dir_acc discrimination**: pass proposals avg dir_acc ~0.07 higher than fail, positive correlation
5. **Top mechanism keywords**: `slope`, `crack`, `spread`, `gated`, `calendar`, `cyclical`, `oi`, `momentum`

## Strategy Recommendations

- Increase sampling quotas for `ta`, `ao`, `sh`, `cf` (high pass rate symbols)
- Increase sampling for `calendar`, `term_structure` families (high pass rate)
- Reserve 20% exploration budget for low pass rate combos, avoid local optimum
- Build mechanism mutation templates from `slope`, `crack`, `spread` high-frequency keywords
