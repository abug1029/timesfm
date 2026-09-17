<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-17 -->

# docs

## Purpose

人类可读运维与研究文档；回测实验注册表与固化判据的**文档真相源**。

## Key Files

| File | Description |
|------|-------------|
| `README.md` | 文档索引 |
| `praxist.md` | Praxist 架构概览（本体 vs 三环；现行合同） |
| `runbook_praxist_three_loop.md` | Praxist 三环运维 |
| `spec_hypothesis_driven_fast_loop_20260908.md` | 方案 A：peer 只写假设 |
| `runbook.md` | 日常运维 |
| `copilot.md` | Copilot 用法 |
| [已归档] `./archive/history/vol-risk.md` | Vol 风控状态（生产默认 OFF） |
| [已归档] `./archive/history/backtest_registry.md` | 历史实验目录（Phase 扫描） |
| `product_positioning.md` | 可交易方向 / 产品红线 |
| `module_freeze.md` | Vol/A2/Regime 冻结 |
| `param_hygiene.md` | 参数卫生裁决 |
| [已归档] `./archive/history/validation_criteria.md` | 固化判据 v2 |
| `long-task-sop.md` | 长任务 SOP |
| `superpowers/plans/` | 已清空（历史施工单见 `archive/superpowers-plans/`） |
| `superpowers/specs/` | 设计规格 |

**新口径经济真相**: g005e 结果文件已不在仓内（原 `../reports/research/20260808_g005e_results.md`；Phase 11/12 后协变量已刷新）

## For AI Agents

### Working In This Directory

- 重跑 heavy WF 前先读 `./archive/history/backtest_registry.md`（已归档） 与 `STATE.md`。
- 固化门槛判据 v2 已归档（`./archive/history/validation_criteria.md`）；当前 Praxist 裁决以 v23 spec（`./superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`）为准；实现参考 `scripts/phase4d_parse_results.verdict`。
- 更新文档时区分：**磁盘事实**（STATE/reports）vs 规划（plans）。
- Praxist：新人读 `praxist.md`；运维读 `runbook_praxist_three_loop.md`。`./archive/history/praxist_integration_plan.md` / `./archive/history/praxist_directive_design.md` 是历史方案（已归档），顶部有取代说明。
- Praxist 机器状态不在 STATE.md 独占：`data/cache/supervisor_state.json` + `task_FM/config/aligned_verdicts.jsonl`。

### Praxist 裁决口径 v23（Validation Criteria v2 已退役）

> 固化判据 v2 的 Rule1–Rule5（MaxDD 一票否决 / EV 翻正绿通等）已随 v23 退役出裁决链；旧文见 `./archive/history/validation_criteria.md`（已归档）。现行裁决口径唯一权威 = v23 spec `./superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`：

- 硬门：n≥350、n_eff≥50（Bartlett）、dir_acc≥0.52（品种自适应 effective_min = max(0.50, min(0.52, baseline_dir_acc))）
- 统计裁决：DM 检验（Newey-West HAC + HLN）+ BH-FDR（per-symbol 多重校正；K<4 时降级固定 Bonferroni α=0.025）
- 裁决三态：`v2_pass` / `hard-gate-but-losing` / `DEAD`（`scripts/praxist_supervisor.py::materialize_known_verdicts`）
- PF/EV/MaxDD/IC：仅经济报表字段，不参与裁决

### Note on EV unit

monthly stdout 打印 **`EV_ratio=`**（无量纲）。文档中的 EV 案例多为该尺度，勿与 `evaluation_metrics["EV"]` 价格点混淆。历史日志可能仍出现 `EV=` 别名（`phase4d_parse_results` 二者同语义）。**EV 为经济报表字段，不参与 Praxist 裁决（v23）。**

## Dependencies

### Internal

- 产物目录：`reports/monthly_backtest/`、`reports/research/`、`reports/phase1/`

<!-- MANUAL: -->
