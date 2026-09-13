## Known aligned verdicts (supervisor snapshot)
econ pass (gate_pass=True AND ev>0): already solved, do NOT re-propose.
hard-gate-but-losing (gate_pass=True AND ev<=0): 过硬门但亏钱; not a success; do not re-propose as solved.
DEAD (gate_pass=False, status=ok): never revive without a mechanism correction.

- ss_vor: econ_pass, gate_pass=True, ev=11.06, n=396, status=ok
- i_oi: hard-gate-but-losing, gate_pass=True, ev=-2.46, n=396, status=ok
- m_ccl: hard-gate-but-losing, gate_pass=True, ev=-3.64, n=396, status=ok
- rb_ccl: hard-gate-but-losing, gate_pass=True, ev=-9.01, n=588, status=ok
- rb_calendar_cyclical: hard-gate-but-losing, gate_pass=True, ev=-9.01, n=588, status=ok
- ss_oi: hard-gate-but-losing, gate_pass=True, ev=-29.29, n=588, status=ok
- lh_oi: hard-gate-but-losing, gate_pass=True, ev=-58.69, n=588, status=ok
- lh_ha_body: hard-gate-but-losing, gate_pass=True, ev=-58.69, n=588, status=ok
- lh_vor: hard-gate-but-losing, gate_pass=True, ev=-58.69, n=588, status=ok
- lh_calendar_cyclical: hard-gate-but-losing, gate_pass=True, ev=-58.69, n=588, status=ok
- lh_ccl: hard-gate-but-losing, gate_pass=True, ev=-58.69, n=588, status=ok
- m_vor: DEAD, gate_pass=False, ev=8.71, n=396, status=ok
- ss_nvi: DEAD, gate_pass=False, ev=6.34, n=396, status=ok
- ss_rsi_state: DEAD, gate_pass=False, ev=4.22, n=396, status=ok
- fu_nvi: DEAD, gate_pass=False, ev=3.82, n=396, status=ok
- rb_ha_body: DEAD, gate_pass=False, ev=3.0, n=396, status=ok
- ss_ha_body: DEAD, gate_pass=False, ev=2.1, n=396, status=ok
- sr_oi: DEAD, gate_pass=False, ev=2.06, n=588, status=ok
- sr_vor: DEAD, gate_pass=False, ev=2.06, n=588, status=ok
- p_vor: DEAD, gate_pass=False, ev=1.73, n=396, status=ok
