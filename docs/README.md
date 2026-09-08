# FM_a 文档索引

面向人类操作者与下游接手者。AI 会话约定见根目录 `AGENTS.md` / `CLAUDE.md`；**当前门禁与待办以 `STATE.md` 为准**。

| 文档 | 内容 |
|------|------|
| [runbook.md](./runbook.md) | 环境、采集、幽灵 K 线、单测、故障排查 |
| [copilot.md](./copilot.md) | 主观领航员用法与报告说明 |
| [paper_trading.md](./paper_trading.md) | **纸面闭环**：Copilot → ledger → 回填 → 健康表 |
| [product_positioning.md](./product_positioning.md) | **产品定位**：可交易方向=加权1H；辅助非自动 |
| [module_freeze.md](./module_freeze.md) | 子策略冻结（Vol OFF / A2 关 / Regime 研究-only） |
| [param_hygiene.md](./param_hygiene.md) | 参数卫生裁决记录 |
| [vol-risk.md](./vol-risk.md) | Vol 风控 / R1 / L1 经济结论与红线 |
| [validation_criteria.md](./validation_criteria.md) | 固化判据 v2 |
| [backtest_registry.md](./backtest_registry.md) | 历史协变量实验目录（Phase 扫描；**新口径以 g005e 为准**） |

### 2026-08-08 新口径 rebaseline（必读）

| 文档 | 内容 |
|------|------|
| [`../reports/research/20260808_g005e_results.md`](../reports/research/20260808_g005e_results.md) | **20 品种全表** PF/星级（bar-exact + signal_weight） |
| [`../reports/research/20260808_tradable_alpha_final_score.md`](../reports/research/20260808_tradable_alpha_final_score.md) | 可交易 alpha 健康度 6.7/10 |
| [`../reports/research/20260808_conflict_debt_register.md`](../reports/research/20260808_conflict_debt_register.md) | 冲突债 CF-01…25 裁决 |

## 30 秒上手

```bash
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a

# 盘中主观（推荐）
python scripts/copilot.py ss fu

# 生产级联预测（默认无 vol 压平）
python scripts/cascade_predict.py ss

# 数据卫生
python scripts/data_management.py --daily --1h
python -m data.future_bar_guard --dry-run
```

## 研究门禁状态（2026-08-07 A2-P1 完整性硬化 + A2-P2 完成）

**磁盘事实来源**：
- A2-P1：`reports/a2_p1_manifest.json`（由 `a2_p1_restore_manifest.py --write-manifest` 生成）
- A2-P2：`reports/research/20260807_a2_p2_verdict.md`

### A2-P1 20 品种可复核状态

| 状态 | 数量 | 品种 |
|:----:|:----:|:-----|
| **complete** | 13 | ss, rb, sp, i, jm, m, p, eg, jd, cf, sr, ma, fg |
| **partial** | 5 | ao(258/396), lh(259/396), ta(397/396, 1 unexpected), ur(331/396), cj(345/396) |
| **duplicated** | 1 | fu(792 行, 396 唯一 bar, 已生成 .canonical) |
| **missing** | 0 | — |

### A2-P1.1 定向修复裁决

- FG/TA/BU/AO/UR 去重后 **0/5 GO**，未满足启动 A2-P2 的 ≥2 GO 门槛。
- 用户批准后启动 A2-P2。

### A2-P2 残差叠加裁决（2026-08-07 完成）

**目标**：测试 LGBM 残差叠加架构能否改善预测质量（`stacked = timesfm_pure + lgbm_residual`）

**执行**：5 品种（FG/TA/BU/AO/UR），总耗时 ~90 分钟

**裁决结果**：**0/5 GO**
- Stacked PF 全部 < 1.0（0.838-0.937），且低于 scheme PF
- 残差叠加架构未改善预测质量，**关闭 Track B**

详细报告：`reports/research/20260807_a2_p2_verdict.md`

### 历史结果对账工具

- `python scripts/a2_p1_restore_manifest.py --dry-run` — 扫描主/备份目录，打印 20 品种状态
- `python scripts/a2_p1_restore_manifest.py --canonicalize` — 对重复写入的 JSONL 去重
- `python scripts/a2_p1_restore_manifest.py --restore` — 从备份恢复缺失文件
- 详见 [runbook.md](./runbook.md) "A2-P1 完整性工具" 章节

## 当前生产姿态（2026-08-21）

- **Neutral / Absolute Risk Overlay：默认 OFF**（全宇宙经济门禁未过）
- **Copilot：预警-only**，不改变预测数值；**可交易方向 = 加权 1H**（非日线标签）
- **无真实 3 星**；`--three-star` = 信用≥2 星列表
- **Phase 11（2026-08-21 结案）**：12 品种协变量替换固化（SS/SP/FU/I/RB/TA/EG/CJ/LH/JD + 3 基线保持 M/P/SR），34 GREEN
- **Phase 12（2026-08-21）**：BU 组合协变量 `calendar_cyclical+hourly_slope` 固化（PF=1.01 边际 GREEN）
- 新口径经济表与信用档：见上表 g005e（Phase 11/12 后协变量已刷新）；运维细节见 [vol-risk.md](./vol-risk.md) 与 `STATE.md`
