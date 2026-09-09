# Praxist Run Report: run_2026-09-08_04-25-44_primary_task_FM

- Generated at: `2026-09-08T05:36:01Z`
- Trigger: `final_run_completion`
- Generation context: `1`
- Report kind: `frontier_lineage_health`
- Run directory: `/home/abug/timesfm/task_FM/experiments/run_2026-09-08_04-25-44_primary_task_FM`

## A. Strongest Variants And Pareto Front

No clean frontier or Pareto-front entries were found yet. The report is separating mature measurements from broader validation, shared-finding, Gems, and result-summary signals.

### Strong Signals Requiring Validation

These measurements remain visible but are not presented as mature evidence.

| Metric | Direction | Best Signal | Gen | Value | Evidence | Blocker / Status | Source |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| `ev_after_slippage` | maximize | `gen_1/gen1_peer1/rb_oi/diagnostic` | 1 | 0.33 | validation candidate / unknown | excluded_from_durable_frontier | results/gen_1/gen1_peer1/rb_oi/diagnostic/evaluation_summary.json |

Comparative claims and charts were omitted for metrics with unknown or conflicting direction: `n_hard_constraint_violations`, `best_ic`, `best_ic_positive_ev`, `dir_acc`, `ev`, `evidence_maturity_rank`, `maxdd`, `metric_value`, `min_coverage_ratio`, `min_effort_ratio`, `n`, `pf`, `variant_name`.

## B. Strong-Variant Evolution And Lineage

No lineage can be inferred from the available result signals yet.

## Visual Companion

- PDF report with charts: `/home/abug/timesfm/task_FM/docs/praxist_reports/20260908_053601_run_2026-09-08_04-25-44_primary_task_FM_final_run_completion_gen1.pdf`
- Chart: Signal-only ev_after_slippage observations by generation
- Chart: Signal-only metric leaders by task dimension

## C. Run Health And Evidence State

- Status: `failed`, exit condition: `signal_sigterm`.
- Generation progress: `2` / `3`.
- Structured findings visible: `0`.
- No explicit run-summary warnings were found.
- Validation candidates retained for follow-up: `12` (partial/scout/repair/late signals are preserved separately from clean frontier truth).
- Latest generation boundary: `gen_1` status `committed`.

## Report Semantics

This Markdown report is a derived human-readable view. Canonical facts remain in frontier, findings, result summaries, Gems state, and generation boundary artifacts. Do not hand-edit this report to change run truth.
A companion PDF is written next to this Markdown file at `/home/abug/timesfm/task_FM/docs/praxist_reports/20260908_053601_run_2026-09-08_04-25-44_primary_task_FM_final_run_completion_gen1.pdf`.
