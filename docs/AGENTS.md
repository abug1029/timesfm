<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-09 -->

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
| `vol-risk.md` | Vol 风控状态（生产默认 OFF） |
| `backtest_registry.md` | 历史实验目录（Phase 扫描） |
| `product_positioning.md` | 可交易方向 / 产品红线 |
| `module_freeze.md` | Vol/A2/Regime 冻结 |
| `param_hygiene.md` | 参数卫生裁决 |
| `validation_criteria.md` | 固化判据 v2 |
| `long-task-sop.md` | 长任务 SOP |
| `superpowers/plans/` | 阶段实现计划 |
| `superpowers/specs/` | 设计规格 |

**新口径经济真相**: `../reports/research/20260808_g005e_results.md`（20/20）

## For AI Agents

### Working In This Directory

- 重跑 heavy WF 前先读 `backtest_registry.md` 与 `STATE.md`。
- 固化门槛以 `validation_criteria.md` v2 为准；实现参考 `scripts/phase4d_parse_results.verdict`。
- 更新文档时区分：**磁盘事实**（STATE/reports）vs 规划（plans）。
- Praxist：新人读 `praxist.md`；运维读 `runbook_praxist_three_loop.md`。`praxist_integration_plan.md` / `praxist_directive_design.md` 是历史方案，顶部有取代说明。
- Praxist 机器状态不在 STATE.md 独占：`data/cache/supervisor_state.json` + `task_FM/config/aligned_verdicts.jsonl`。

### Validation Criteria v2 (summary)

1. Rule1 MaxDD 相对恶化 >20% → 否决  
2. Rule2 仅 MAPE 达标且 PF 退化 >2% → 否决  
3. Rule3 EV 负→正绿通（仍受 R1）  
4. Rule4 MaxDD 大幅改善 + EV 不显著退化 → 绿通  
5. Rule5 n<350 负面 → UNDERPOWERED  

常规：MAPE 相对降≥3% **或** DirAcc +≥3pp **或** PF 相对 +≥10%。

### Note on EV unit

monthly stdout 打印的 `EV=` 实际是 **EV_ratio**（无量纲）。文档中的 EV 案例多为该尺度，勿与 `evaluation_metrics["EV"]` 价格点混淆。

## Dependencies

### Internal

- 产物目录：`reports/monthly_backtest/`、`reports/research/`、`reports/phase1/`

<!-- MANUAL: -->
