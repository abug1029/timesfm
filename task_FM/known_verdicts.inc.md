## Known aligned verdicts (supervisor snapshot)
v2 pass (gate_pass=True AND (fdr_pass OR migrated_pass)): already solved, do NOT re-propose.
v1 legacy: pass by ev>0 (legacy econ caliber, schema=v1 entries only).
hard-gate-but-losing (gate_pass=True but not (fdr_pass or migrated_pass)): 过硬门但未过 v23 统计检验; not a success; do not re-propose as solved.
DEAD (gate_pass=False, status=ok): never revive without a mechanism correction.

- p_oi: v1_legacy_pass, gate_pass=True, ev=12.03, n=588, status=ok
- p_calendar_cyclical: v1_legacy_pass, gate_pass=True, ev=14.28, n=588, status=ok
- cf_rsi6: hard-gate-but-losing, gate_pass=True, ev=-23.95, n=588, status=ok
- sh_reversal_shadow_gated_03: hard-gate-but-losing, gate_pass=True, ev=-9.19, n=588, status=ok
- jm_oi: hard-gate-but-losing, gate_pass=True, ev=-4.51, n=588, status=ok
- ma_rsi6: hard-gate-but-losing, gate_pass=True, ev=-22.63, n=588, status=ok
- sh_rsi6: DEAD, gate_pass=False, ev=-1.17, n=588, status=ok
- i_oi: DEAD, gate_pass=False, ev=-1.58, n=588, status=ok
- i_reversal_shadow_gated_03: DEAD, gate_pass=False, ev=-2.87, n=588, status=ok
