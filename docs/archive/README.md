# 文档归档（docs/archive）

本目录存放 v23 重构（2026-09-16 合入 master，spec: `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`）后已过时或纯历史的文档。文件保留原名，历史路径引用需改用 `docs/archive/...` 新路径。

## docs/archive/history/

| 原名 | 归档原因 | 被何取代 |
|------|----------|----------|
| LOOP.md | 历史运营文档：预测驱动采集的数据管理策略 | runbook.md、docs/README.md |
| backtest_registry.md | 自带过时声明：2026-08-29 实验快照，新口径以 g005e 为准（g005e 结果文件已不在仓内，历史指针悬空） | v23 spec（裁决口径） |
| praxist_directive_design.md | 自带失效声明：证据阶梯与 peer 跑评估已被方案 A（2026-09-08）取代 | docs/spec_hypothesis_driven_fast_loop_20260908.md |
| praxist_integration_plan.md | 自带过时声明：2026-09-01 方案稿，路径/venv/peer 假设已过时 | docs/praxist.md、docs/runbook_praxist_three_loop.md |
| praxist_peer_evaluation_fix.md | 自带失效声明（方案 A）：禁止按本文给 peer 加评估 | docs/spec_hypothesis_driven_fast_loop_20260908.md |
| validation_criteria.md | v2 固化判据与 v23 判据冲突（DirAcc/MAPE/DM/BH-FDR 硬门）。注意：phase4d SCHEMES 固化线（scripts/phase4d_parse_results.py、tests/test_validation_criteria.py）仍引用 v2 判据，其 v23 对齐登记为遗留项，不在本次范围 | v23 spec（裁决口径） |
| vol-risk.md | 历史快照（2026-09-10，v2 布朗运动 CI 时代风控红线） | STATE.md、v23 spec |

## docs/archive/superpowers-specs/

| 原名 | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-07-28-covariate-optimization-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-07-28-covariate-optimization-design.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-07-29-followup-4-directions-optimization-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-07-29-followup-4-directions-optimization-design.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-07-29-phase4-calendar-cyclical-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-07-29-phase4-calendar-cyclical-design.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-07-31-phase8-crack-spread-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-08-04-alpha2-phase1-baseline-gate-desig.txt | 历史 spec（同名 .md 的文本副本）。文件名截断（缺 n），历史产物保留原名 | v23 spec（裁决口径） |
| 2026-08-04-alpha2-phase1-baseline-gate-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-08-04-alpha2-phase1-baseline-gate-design.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-08-04-phase9-toxic-variety-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-08-04-phase9-toxic-variety-design.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-08-05-a2-p1-dense-cache-resume-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-08-05-a2-p1-market-vectorize-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-08-05-a2-p1-market-vectorize-design.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-08-05-a2-p1-runtime-redesign.md | 历史 spec | v23 spec（裁决口径） |
| 2026-08-05-a2-p1-runtime-redesign.txt | 历史 spec | v23 spec（裁决口径） |
| 2026-08-22-phase15-new-covariates-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-09-02-praxist-three-loop-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-09-09-compile-skip-phase1-design.md | 历史 spec | v23 spec（裁决口径） |
| 2026-09-10-system-hardening-design.md | 历史 spec | v23 spec（裁决口径） |
| ACCEPT_flock_20260906.md | 历史 spec | v23 spec（裁决口径） |

## docs/archive/superpowers-plans/

| 原名 | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-07-28-covariate-optimization-phase1.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-07-28-covariate-optimization-phase1.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-07-29-followup-4-directions-optimization.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-07-29-phase4-calendar-cyclical.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-07-29-phase4-calendar-cyclical.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-07-29-phase5-6-shadow-threshold-and-basis-pipeline.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-07-29-phase5-6-shadow-threshold-and-basis-pipeline.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-07-31-phase8-crack-spread.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-04-alpha2-phase1-baseline-gate.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-04-alpha2-phase1-baseline-gate.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-04-toxic-variety-plan.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-04-toxic-variety-plan.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-a2-p1-dense-cache-resume.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-a2-p1-dense-cache-resume.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-a2-p1-market-vectorize.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-a2-p1-market-vectorize.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-a2-p1-runtime-redesign.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-a2-p1-runtime-redesign.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-alpha2-next-steps.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-05-alpha2-next-steps.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-07-a2-p1-integrity-hardening.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-07-a2-p2-residual-stacking.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-17-covariate-gap-backtest.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-17-covariate-gap-backtest.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-18-single-covariate-exhaustive.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-18-single-covariate-exhaustive.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-20-phase11-mop-up.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-21-evolution-layer12.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-22-copilot-kb-regime-maxdd.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-22-evolution-roadmap.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-22-phase15-new-covariates.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-23-ma-variety-validation.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-08-23-phase15-audit-fixes.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-02-praxist-three-loop.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-03-fast-slow-handshake.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-09-compile-skip-phase1.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-10-system-hardening.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-11-audit-c9-c12.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-11-audit-code-fixes.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-11-covariate-combo-completion.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-11-doc-sync.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-11-full-system-audit.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| 2026-09-11-spec-code-alignment.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-1-report.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-1-review.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-2-report.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-2-rereview.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-2-review.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-3-report.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-3-review.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-4-report.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| task-4-review.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| whole-branch-review.md | 历史施工单 | 现行文档（v23 spec / docs/README.md） |
| whole-branch-review.txt | 历史施工单 | 现行文档（v23 spec / docs/README.md） |

## docs/archive/superpowers-reviews/

| 原名 | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-09-15-phase1-2-code-review.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-15-phase1-2-rereview.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-15-phase1-2-rereview-round3.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-15-phase3-code-review.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-15-phase3-rereview.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-15-phase3-rereview-round3.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-16-phase4-code-review.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-16-phase4-rereview.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
| 2026-09-16-uncommitted-changes-review.md | 历史审查记录 | v23 spec（裁决口径）、docs/README.md |
