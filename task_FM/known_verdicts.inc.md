## Known aligned verdicts (supervisor snapshot)
econ pass (gate_pass=True AND ev>0): already solved, do NOT re-propose.
hard-gate-but-losing (gate_pass=True AND ev<=0): 过硬门但亏钱; not a success; do not re-propose as solved.
DEAD (gate_pass=False, status=ok): never revive without a mechanism correction.

- ss_vor: econ_pass, gate_pass=True, ev=11.06, n=396, status=ok
- i_oi: hard-gate-but-losing, gate_pass=True, ev=-2.46, n=396, status=ok
- m_ccl: hard-gate-but-losing, gate_pass=True, ev=-3.64, n=396, status=ok
- cj_oi: DEAD, gate_pass=False, ev=19.46, n=324, status=ok
- m_vor: DEAD, gate_pass=False, ev=8.71, n=396, status=ok
- ss_nvi: DEAD, gate_pass=False, ev=6.34, n=396, status=ok
- ss_rsi_state: DEAD, gate_pass=False, ev=4.22, n=396, status=ok
- fu_nvi: DEAD, gate_pass=False, ev=3.82, n=396, status=ok
- rb_ha_body: DEAD, gate_pass=False, ev=3.0, n=396, status=ok
- ss_ha_body: DEAD, gate_pass=False, ev=2.1, n=396, status=ok
- p_vor: DEAD, gate_pass=False, ev=1.73, n=396, status=ok
- ss_ccl: DEAD, gate_pass=False, ev=1.49, n=396, status=ok
- ta_bb_squeeze: DEAD, gate_pass=False, ev=0.32, n=396, status=ok
- sr_calendar_cyclical: DEAD, gate_pass=False, ev=-0.85, n=396, status=ok
- rb_oi: DEAD, gate_pass=False, ev=-1.2, n=396, status=ok
- eg_rsi_state: DEAD, gate_pass=False, ev=-1.69, n=396, status=ok
- jd_oi: DEAD, gate_pass=False, ev=-1.8, n=396, status=ok
- m_oi: DEAD, gate_pass=False, ev=-4.18, n=588, status=ok
- rb_vor: DEAD, gate_pass=False, ev=-5.08, n=396, status=ok
- eg_nvi: DEAD, gate_pass=False, ev=-6.59, n=588, status=ok
