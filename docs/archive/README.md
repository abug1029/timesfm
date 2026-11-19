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

### 2026-11-19 追加（全仓时效复审批次）

复审判定标准同上（一次性调查 / 已结案核验 / 已执行完施工单且不再被在用文档引用）。引用完整性已逐件 grep 预检；`2026-09-30-dead-code-purge-spec.md` 内 3 处指针已同步回填新路径。

自 `superpowers/reports/` 移入（6 件）：

| 原名 | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-09-28-t1b-hand-calc-report.md | Stage 3 一次性手算核对（T1b，通过 10/10） | STATE.md 交付表 T1b 行；purge spec 指针已回填 |
| 2026-09-28-t2-ablation-table.md | Stage 3 三路消融对照表（T2，16 裁决） | STATE.md「本轮自查修正」节；purge spec 指针已回填 |
| 2026-09-29-spec-implementation-audit.md | 一次性 spec 实施核验（基线 eecf05a） | STATE.md 交付表 |
| 2026-09-30-dead-code-spec-review.md | 死代码 spec v1→v2 的审核意见，已吸收完毕 | purge spec v2 头部勘误记录 |
| 2026-09-30-q7-target-effect-power-memo.md | Q7 决策备忘录，宿主裁定 (a′) 当日已写入 STATE/spec | STATE.md:78（Δ*=0.08/功效 80%） |
| 2026-09-30-stage3-compliance-evaluation.md | 一次性第三方合规评估 | v4 收口计划处置 |

自 `superpowers/changelogs/` 移入（4 件；changelog 默认留原位，仅归档自带取代声明或纯一次性无追溯价值的）：

| 原名 | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-09-28-stage3-final-report.md | 顶部自带 SUPERSEDED banner（2026-09-28） | 本目录 superseded-2026-09/2026-09-28-stage3-completion-report.md |
| 2026-09-28-stage3-final-report-updated.md | 同上 banner，一字不差 | 同上 |
| 2026-09-28-stage3-status-report.md | 当日状态快照（钉「审核中」等活状态） | review-rounds changelog + completion-report |
| 2026-09-28-t1a-execution-guide.md | T1a 执行型指南（PR-A1 已完成，`6c94275`） | changelog 2026-09-27-task 系列 |

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
| 2026-09-22-typesafe-covariate-prescreen-design.md | 初版 TypeSafe 预筛设计稿，已实施；「设计权威」地位被 jev-prescreen-peer-influence（CLAUDE.md 认定）取代；TypeSafe/Jev 细节被 Laya 迁移过时化，全仓零引用 | `docs/superpowers/changelogs/2026-10-14-jev-to-laya-migration.md` + 在用 spec 2026-09-22 |
| 2026-10-08-d4-d5-n10-e1-research-spec.md | 自带「调研阶段」声明的一次性调研稿；Q1-Q10 已全部裁定并实施闭环 | `docs/archive/superseded-2026-10/2026-10-08-d4-d5-n10-e1-q-rulings.md` |

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
| 2026-10-05-peer-learning-feedback-hardening.md | 已执行完（T0-T3 全 ✅，观察期 10-05→10-19 已过，头部自带收口声明；tests/test_known_verdicts_injection_20261005.py docstring 指针已回填） | `docs/superpowers/changelogs/2026-10-05-peer-learning-feedback-hardening-t0-t3.md` |
| 2026-10-06-holiday-success-gate-unlock.md | 已执行完；自带失效设计（data_stale 旁路 10/8 后自结束） | `docs/superpowers/changelogs/2026-10-06-holiday-success-gate-data-stale.md` |
| 2026-10-08-open-issues-closure-implementation.md | 已执行完（12 条未结问题 + N10 全处置，完成基准 `3287dcb`） | `docs/superpowers/changelogs/2026-10-08-open-issues-closure-implementation.md` |
| 2026-10-09-d4-d5-n10-e1-rulings-fix-plan.md | 已执行完，全仓零引用 | `docs/superpowers/changelogs/2026-10-09-d4-d5-n10-e1-rulings-fix-completion.md` |
| 2026-10-09-d4-watchdog-cron-setup.md | 已执行完（自愈上线并实弹演练）；运维细节已内化进 runbook | `docs/runbook_praxist_three_loop.md`（maintenance.flag / diagnose 章节） |
| 2026-10-11-data-update-incremental-fix-plan.md | v1 待审稿，被同日 v2 审计版取代 | `2026-10-11-data-update-incremental-fix-plan-audit.md`（在用） |
| 2026-10-11-s1-supervisor-split.md | 已执行完（`3e8756e`）；模块归属现以 docs/praxist.md 为唯一表 | `docs/praxist.md` + `docs/superpowers/changelogs/2026-10-12-s1-supervisor-split.md` |
| 2026-10-11-supervisor-death-loop-fix-plan.md | v1 待审稿，被同日 v2 审计版取代 | `2026-10-11-supervisor-death-loop-fix-plan-audit.md` |
| 2026-10-11-supervisor-death-loop-fix-plan-audit.md | v2 = 实际执行版，修复已上线且 runbook 内化 | `docs/superpowers/changelogs/2026-10-11-supervisor-watchdog-death-loop-fix.md` |
| 2026-10-12-baseline-regen-loop-fix-plan.md | 已执行完（头部 APPROVED 记录） | `docs/superpowers/changelogs/2026-10-13-baseline-regen-loop-fix.md` |
| 2026-10-13-timesfm-25-to-30-migration-plan.md | 状态 PROPOSED 但迁移实质完成（验证方式：全仓 grep `timesfm-2.5/2.5-200m` 活路径残留为零；无对应 changelog） | 模型层现状（models/timesfm-3.0-pytorch + import timesfm3） |
| 2026-10-27-slow-loop-no-data-fix-plan.md | 已执行完（changelog + changelog-audit 双重核验） | `docs/superpowers/changelogs/2026-10-27-slow-loop-no-data-fix-changelog.md` |
| 2026-11-03-baseline-point-contract-plan.md | 已执行完；现行读法合同由在用 spec 承载 | `docs/superpowers/changelogs/2026-11-05-baseline-point-contract-implementation.md` + 在用 spec |
| 2026-11-07-slow-loop-verdict-cleanup-plan.md | 八阶段全部执行完（Phase 0-5 + 6-7 两会话收口）；卫生合同由在用 spec 承载 | spec 2026-11-07-slow-loop-verdict-cleanup-spec（在用）+ `docs/superpowers/changelogs/2026-11-12-phase6-7-completion-session.md` |

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

## docs/archive/superseded-2026-10/

2026-11-19 全仓时效复审归档（判定标准同 superseded-2026-09：一次性调查 / 已结案核验，且不再被在用文档或生产提示词引用；引用完整性逐件 grep 预检通过）。

| 原名（自 `superpowers/reports/` 移入） | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-10-03-supervisor-stop-event-report.md | PID 416 停机事件一次性报告 | `docs/supervisor_restart_backlog.md` |
| 2026-10-05-peer-learning-gap-analysis-review.md | 一审报告，顶部自带勘误并入声明 | `2026-10-05-peer-learning-gap-analysis.md`（在用） |
| 2026-10-05-peer-learning-review-and-plan-audit.md | 一次性复审，结论已由 T0-T3 changelog 落地 | `docs/superpowers/changelogs/2026-10-05-peer-learning-feedback-hardening-t0-t3.md` |
| 2026-10-06-holiday-success-gate-deadlock-diagnosis.md | 一次性死锁诊断，§6 选项 A 已实施 | `docs/superpowers/changelogs/2026-10-06-holiday-success-gate-data-stale.md` |
| 2026-10-07-confirmation-dispatch-liveness.md | 自述「只读调研、立项与交付同日」 | — |
| 2026-10-07-dm-status-liveness-root-cause.md | 一次性根因调研，裁定记录于收口计划 §8 | `docs/superpowers/plans/2026-10-07-tech-debt-closure-plan.md`（在用） |
| 2026-10-07-three-loop-midnight-status.md | 午夜状态快照（钉 PID 等活数字） | `data/cache/supervisor_state.json`（活状态唯一源） |
| 2026-10-08-c1-diagnostic-report.md | C1 判停一次性诊断（对齐点 c200210） | STATE.md |
| 2026-10-08-c1-diagnostic-report-review.md | 对上报告的审阅意见（一次性） | — |
| 2026-10-08-d4-d5-n10-e1-q-rulings.md | Q1-Q10 裁定记录，处置已闭环 | `docs/superpowers/changelogs/2026-10-09-d4-d5-n10-e1-rulings-fix-completion.md` |
| 2026-10-08-m2-documentation-alignment.md | M2 验收记录（一次性，对齐点 a2cb889） | STATE.md |
| 2026-10-08-m3-pyyaml-verification.md | PyYAML 修复验收记录（一次性） | STATE.md |
| 2026-10-09-m5-supervisor-split-spec-review.md | M5 spec v1 审核（Reject as-is），任务改名 S1 | `2026-10-10-s1-supervisor-split-spec-review.md`（本目录） |
| 2026-10-10-s1-supervisor-split-spec-review.md | S1 v2 复审（第二次 Reject） | `2026-10-10-s1-supervisor-split-spec-v3-review.md`（本目录） |
| 2026-10-10-s1-supervisor-split-spec-v3-review.md | S1 v3 三审（第三次 Reject，机械级修订）；拆分已实施 | `docs/superpowers/changelogs/2026-10-12-s1-supervisor-split.md` + 在用 spec v3.2 |
| 2026-10-11-supervisor-watchdog-death-loop-audit.md | 一次性审计，修复 changelog 存在 | `docs/superpowers/changelogs/2026-10-11-supervisor-watchdog-death-loop-fix.md` |
| 2026-10-13-circuit-breaker-regen-loop-investigation.md | 一次性调查（自标 FIXED_IN_WORKTREE） | `docs/superpowers/changelogs/2026-10-13-baseline-regen-loop-fix.md` |
| 2026-10-20-low-efficiency-diagnosis.md | 数据快照诊断（452 verdicts 时点），属 derived_view | `task_FM/config/aligned_verdicts.jsonl`（canonical） |
| 2026-10-27-slow-loop-no-data-investigation.md | 一次性调查，修复 changelog 存在（可信度 ~86% 自评） | `docs/superpowers/changelogs/2026-10-27-slow-loop-no-data-fix-changelog.md` |

## docs/archive/superseded-2026-11/

2026-11-19 全仓时效复审归档（判定标准同上）。

| 原名（自 `superpowers/reports/` 移入） | 归档原因 | 被何取代 |
|------|----------|----------|
| 2026-11-03-baseline-audit-dir-ok-jd-report.md | 一次性基线审计（2026-11-02~03），changelog 引用为调查报告 | `docs/superpowers/changelogs/2026-11-05-baseline-point-contract-implementation.md` |
| 2026-11-06-doc-staleness-audit.md | 上一轮文档陈旧度审计（对照 1f90081，一次性）；本次复审即其接替者 | 本 README 本批次登记 |
| 2026-11-07-cleanup-verification.md | Phase 6-7 清理验收记录（配套 changelog 已在） | `docs/superpowers/changelogs/2026-11-12-phase6-7-completion-session.md` |
| 2026-11-07-slow-loop-verdict-quality-audit.md | 一次性质量审计（v2 修订版），结论已进入在用 spec | `docs/superpowers/specs/2026-11-07-slow-loop-verdict-cleanup-spec.md` |
| 2026-11-18-proposal-quality-2day-audit.md | 一次性审计，followup 五步已实施（changelog + 测试随 `ff721f4` 提交） | `docs/superpowers/changelogs/2026-11-19-proposal-followup-changelog.md` |
| laya-optimization-research-2026-11-07.md | v1 调研，被同目录 .v2.md（v2.1 最终修订）取代，全仓零引用 | `superpowers/reports/laya-optimization-research-2026-11-07.v2.md`（留原位待宿主审批） |

> **同批复审后刻意留在原位的存疑件**（见技术债登记表）：`laya-optimization-research-2026-11-07.v2.md` / `laya-optimization-spec-2026-11-07.md` / `laya-implementation-plan-full.md`（待宿主审批）、`2026-11-03-jd-baseline-operator-note.md`（待并入 runbook 后处置）、`docs/BACKUP-MERGE-PROTOCOL.md`（文件损坏待重写）。
