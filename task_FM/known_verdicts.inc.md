## Known aligned verdicts (supervisor snapshot)
v2 pass (gate_pass=True AND (fdr_pass OR migrated_pass)): already solved, do NOT re-propose.
v1 legacy: pass by ev>0 (legacy econ caliber, schema=v1 entries only).
hard-gate-but-losing (gate_pass=True but not (fdr_pass or migrated_pass)): 过硬门但未过 v23 统计检验; not a success; do not re-propose as solved.
DEAD (gate_pass=False, status=ok): never revive without a mechanism correction.

- sr_calendar_cyclical: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- p_oi: v2_pass, gate_pass=True, ev=None, n=588, status=ok
- ss_calendar_cyclical: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- p_calendar_cyclical: v2_pass, gate_pass=True, ev=None, n=588, status=ok
- cf_rsi6: v2_pass, gate_pass=True, ev=None, n=588, status=ok
- cj_bb_squeeze: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- sr_oi: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- cj_rsi24: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- cj_reversal_shadow_gated_03: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- cj_reversal_shadow: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- m_calendar_cyclical: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- m_oi: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- cj_oi: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- cj_reversal_shadow_gated_02: hard-gate-but-losing, gate_pass=True, ev=None, n=588, status=ok
- sh_rsi6: DEAD, gate_pass=False, ev=None, n=588, status=ok
- ss_vor: DEAD, gate_pass=False, ev=None, n=588, status=ok
- cj_calendar_cyclical: DEAD, gate_pass=False, ev=None, n=588, status=ok
- cj_basis_momentum: DEAD, gate_pass=False, ev=None, n=588, status=ok
- cj_stddev: DEAD, gate_pass=False, ev=None, n=588, status=ok
- i_oi: DEAD, gate_pass=False, ev=None, n=588, status=ok
