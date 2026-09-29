# 文档归档（docs/archive）

本目录存放 v23 重构（2026-09-16 合入 master，spec: `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`）后已过时或纯历史的文档。文件保留原名，历史路径引用需改用 `docs/archive/...` 新路径。归档文档内部的相对链接按归档前目录层级书写，随移动失效，属历史记录不修复。

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

## docs/archive/superseded-2026-09/

2026-09-29 归档。**判定标准**：一次性调查 / 已结案的阶段核验 / 已执行完的施工单，
其结论已被后续文档取代，且**不再被任何在用文档或生产提示词引用**。

**刻意留在原位的**（易被误判，实为在用）：

| 文档 | 为何不归档 |
|------|-----------|
| `docs/2026-09-18-oi-gated-momentum-spec.md` | 被 peer 提示词直接内嵌（`task_FM/covariate_menu.inc.md` + 各 run 的 `gen*_peer*_prompt.md`），改动影响生产提案面 |
| `docs/2026-09-19-three-loop-followup-spec.md` | 三环跟进**合同**，`runbook_praxist_three_loop.md` / `CLAUDE.md` / `AGENTS.md` 均引用 |
| `docs/superpowers/changelogs/*` | 审计证据链。第六~八轮审计逐条核对这些 changelog 的数字与命令，归档会切断可追溯性 |
| `docs/superpowers/specs/*` | 上游 spec v15 / v23 是现行裁决口径的源头 |
| `docs/superpowers/reports/2026-09-29-stage3-verification-record.md` | §8.3 出口条件核验记录，Stage 3 的放行依据 |

| 原路径 | 归档原因 | 被何取代 |
|--------|----------|----------|
| `audit_report_20260907.md`（仓根） | 一次性 DB 审计（2026-09-07），28 品种 P0–P5 建议早已实施完毕；其审计脚本 `audit_futures_v2.py` 已于 `a068d92` 删除，无法复跑 | STATE.md |
| `loop-run-log.md`（仓根） | 2026-07-02 停用的 triage 循环日志，全部 `outcome: no-op` | `data/cache/supervisor_state.json` |
| `loop-budget.md`（仓根） | 同上循环的预算表（无限量 Coding Plan） | `loop-constraints.md`（仍在用） |
| `2026-09-20-qwen3-max-model-switch-eval.md` | 一次性模型切换评估（111 条 verdict 口径，已过时） | v23 spec + `aligned_verdicts.jsonl` |
| `2026-09-17-fm-eval-error-path-audit.md` | 8 个 bug 清单已全部修复 | v23 spec |
| `2026-09-18-oi-gated-momentum-impl-plan.md` | 五步实施计划已执行完 | 同目录 spec（仍在用） |
| `2026-09-18-oi-gated-momentum-data-quality-report.md` | 一次性数据质量报告 | 同上 |
| `2026-09-18-oi-gated-momentum-blocking-decision.md` | 首跑 dir_acc=0.453 的当场决策 | 同上 |
| `2026-09-19-three-loop-followup-impl-plan.md` | 642 行施工单已执行完 | `2026-09-19-three-loop-followup-spec.md`（仍在用） |
| `2026-09-19-verdict-analysis-report.md` | 81 verdict 时点快照（现 171），提案过门 0/11 的结论已被后续轮次覆盖 | v23 spec |
| `2026-09-19-peer-proposal-quality-verification.md` | 单测已过；「快环过门率待下一轮」的待办从未闭合，现由 09-29 审计闭环 | — |
| `2026-09-19-cleanup-and-fix-log.md` | 一次性清理日志 | — |
| `2026-09-27-stage1-verification.md` | Stage 1 出口核验，已被 Stage 3 结案取代 | `superpowers/reports/2026-09-29-stage3-verification-record.md` |
| `2026-09-28-stage2-verification.md` | 同上 | 同上 |
| `audit_system_efficiency_20260908.md` | 2026-09-08 效率审计，行数与组件表全部过时 | — |
| `spec_optimization_roadmap.md` | 基于 system_design **v2.4**（2026-09-10）的优化任务表 | 现行 `docs/system_design.md` |
| `PER_SYMBOL_GOAL_UPDATE_2026-09-23.md` | 目标变更记录 | `scripts/praxist_goal.yaml`（唯一真相） |
| `SUCCESS_CONDITION_UPDATE_2026-09-23.md` | 同上 | 同上 |
| `results_summary.md` | 143 行时点快照（现 171），**全仓无生成脚本**，无法再生 | `task_FM/config/aligned_verdicts.jsonl` |
| `RESULTS_FORMAT_TEMPLATE.md` | 上述快照的展示格式规范，随之失效 | — |
| `v22_findings_audit.md`（`task_FM/`） | v22 存量污染登记，处置策略为「随新 run 自然稀释」 | — |
| `superpowers/reports/2026-09-28-stage3-completion-report.md` | 早于 09-29 核验记录的完成报告 | `2026-09-29-stage3-verification-record.md` |
| `superpowers/reports/2026-09-28-stage3-final-status.md` | 同上 | 同上 |

## docs/archive/superpowers-plans/（2026-09-29 追加）

以下 4 份已执行完的施工单于 2026-09-29 移入本目录：

| 原名 | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-09-22-typesafe-covariate-prescreen-implementation.md | 已执行完 | `docs/superpowers/changelogs/2026-09-22-typesafe-prescreen-implementation.md` |
| 2026-09-27-covariate-credibility-stage1.md | 已执行完 | `docs/superpowers/changelogs/2026-09-27-task*.md` |
| 2026-09-28-covariate-credibility-stage3.md | 已执行完 | `docs/superpowers/changelogs/2026-09-28-*.md` |
| 2026-09-29-spec-alignment-impl-plan.md | 已执行完（Phase 1-10 全部交付，`381f31e`） | `docs/superpowers/changelogs/2026-09-29-stage3-impl-and-prep.md` |

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

## docs/archive/peer-proposals-pre-0918/

2026-09-19 归档。146 个 2026-09-07 至 2026-09-17 的 peer run 目录（），含 peer_workspaces/findings/gems/trajectory 等快环提案产物。128M。

归档原因：v23 评估系统重构后，9-18 前的 peer 提案已无活跃引用（harvest 仅扫当前 experiments/ 下 run），保留原位增加目录噪音。9-18 起的 run 留在  供 harvest 正常扫描。
