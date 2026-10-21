# Phase 2-3 执行 Changelog 审计报告

**日期**: 2026-10-21（Asia/Shanghai）  
**对象**: `docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog.md`（commit `0f24c2b`）  
**仓库**: `/home/abug/timesfm` @ `0f24c2b`（HEAD）  
**对照**: SPEC `docs/superpowers/specs/2026-10-19-proposals-evaluation-optimization-spec.md`；计划 `.omc/ultragoal/plans/phase2-3-execution-plan.md`  
**审核状态**: **有条件通过**  
**完成度**: **~56%**（相对计划验收 / SPEC Phase2-3 里程碑，非「文件是否提交」）

### Commits 列表

| Hash | 声称 |
|------|------|
| `10f414b` | Task 1 生成策略外环 |
| `9af7bf7` | Task 2 短窗回测预筛 |
| `a0f9155` | Task 3 提案卫生门禁 |
| `9e87180` | Task 4 质量预测器 |
| `7e41813` | Task 4 CRITICAL pickle→JSON |
| `4e0a700` | Task 5 多样性指标 |
| `720d93c` | Task 6 持续监控 |
| `0f24c2b` | 主 changelog 文档 |

---

## §1 一句话

六 Task 的脚本与单测均已入库且 **110/110 通过**，Laya 硬约束未被违反；但 **Task1/5 未接入 peer 主路径**、**Task4 生产无 `quality_model.json`（预测恒 0.5）**、**Task6 未挂自动化**，计划验收目标（gate_pass≥40%、覆盖率等）未达——changelog 标「✅ 完成」属夸大，**不得宣称 Phase 2-3 验收完成**。

---

## §2 主 changelog 声称 vs 实证

| Task | Changelog 声称 | 实证 | 判定 |
|------|----------------|------|------|
| **T1 外环** | GenerationStrategy / UCB+Thompson / ElitePreservation；预期 gate_pass 38–42%；24/24 | 三文件在 HEAD；类与 CLI 可用；**`cascade/` / peer 零引用**；门控率仍 ~32.3%；未影响真实生成 | ⚠️ 库完成 / **主路径未接** |
| **T2 短窗** | 100–200 点、dir_acc>0.50；harvest `_short_window_check`；减 50%+ 无效验证；7/7 | 默认 150、阈值 >0.50；harvest 入队前硬拒 `short_window_fail`；fail-open；缓存仅 11 条（3 pass/8 fail）；**「减 50%+」无测量**；顺序实为 quality 门后、**异步 Laya 前**（非「prescreen 后」） | ⚠️ 已接入 / **效果未证** |
| **T3 卫生门** | validator + 批脚本；peer 集成缺失；26/26 | 脚本在；**harvest 已 `validate_proposal_dict` 并拒稿**（changelog 低估）；peer 写盘前仍无；非「写盘前」而是「收割入队前」 | ⚠️ 半集成（优于文档） |
| **T4 预测器** | FrequencyModel + harvest `+5*ml_prob`；跨进程；24/24 | 代码 JSON 序列化正确；harvest 有钩；**`models/quality_model.json` 不存在**；磁盘仅残留 **pickle** `quality_model.pkl`；现场 `score_proposal_for_harvest` → **恒 (0.5, {})** | ❌ 修复代码在 / **生产失效** |
| **T4 CRITICAL** | pickle→JSON；rsi6=0.93 vs oi=0.07 | 源码头注释/默认路径已 JSON；单测覆盖跨进程；**未留下可加载 JSON 产物**；`KNOWN_MODEL_FILES` 仍认 `.pkl` 不认 `.json` | ⚠️ 代码通过 / **部署缺口** |
| **T5 多样性** | 熵/覆盖率/新颖度；19.8% 组合覆盖；12/12 | CLI+文档在；**无 peer/外环反馈**；`test_diversity_bonus_integration` 自承「conceptual…not actual generation_strategy」 | ⚠️ 指标工具 / **未闭环** |
| **T6 监控** | 每日/周报+红线；WARNING 4/6；17/17 | 脚本在；`metrics_history` 有 18–20 三日文件但**数值完全相同**；crontab **无** monitor/weekly；红线为 models 未知文件启发式 | ⚠️ 可手工跑 / **非持续** |
| **禁止事项** | 未训 Laya 等 | 新脚本无 Laya 权重更新/微调；外环仅采样配额——**符合硬约束** | ✅ |
| **「✅ 完成」** | Phase 2-3 全部完成 | SPEC/计划勾选仍为 `[ ]`；里程碑 gate_pass 40%+、覆盖率 80% 等未达；changelog 自身「下一步」仍写 peer 集成 | ❌ **假完成表述** |

---

## §3 各 commit 文件落地核对

| Hash | 提交文件 | HEAD 仍在？ | 备注 |
|------|----------|-------------|------|
| `10f414b` | `scripts/generation_strategy.py`, `tests/test_generation_strategy.py`, `docs/superpowers/reports/2026-10-20-gate-pass-feature-analysis.md` | ✅ | 分析报告在 `reports/` |
| `9af7bf7` | `scripts/short_window_backtest.py`, `scripts/sup_harvest.py`(+), `tests/test_short_window_backtest.py` | ✅ | harvest 钩仍在 |
| `a0f9155` | `proposal_validator.py`, `validate_all_proposals.py`, `tests/test_proposal_validator.py` | ✅ | 另：后续 harvest 增加了调用 |
| `9e87180` | `quality_predictor.py`, harvest(+), `docs/quality_predictor.md`, tests | ✅ | 后被 `7e41813` 改序列化 |
| `7e41813` | predictor/docs/tests | ✅ | 默认 `models/quality_model.json`；**仓内无该文件** |
| `4e0a700` | `diversity_metrics.py`, guide, tests | ✅ | 孤岛 CLI |
| `720d93c` | `monitor_metrics.py`, `generate_weekly_report.py`, example report, tests | ✅ | 未进 cron |
| `0f24c2b` | 本 changelog | ✅ | |

行数抽查：generation_strategy 609、short_window 483、proposal_validator 114、diversity 308、monitor 364——与 commit 叙述基本一致。quality_predictor 现 536（CRITICAL 后略增）。

---

## §4 vs SPEC / 计划对齐；Laya 硬约束

### SPEC v3.1（§5.3–5.6 / Phase 2–3 清单）

| 要求 | 对齐 |
|------|------|
| 生成策略外环、**明确不更新 Laya** | 外环实现方向正确；**未接到生成**；无 Laya 训练 ✅约束 / ❌落地 |
| 独立质量预测器、非 Laya | FrequencyModel（非计划中的 XGB/LGBM）可接受简化；**无部署模型** |
| 短窗预筛、不反馈 Laya | 已拒稿路径；无反传 Laya ✅ |
| 上游卫生 JSON/类型/中英 | 逻辑有；peer 写盘前缺失 |
| 多样性进适应度 | **未做**（仅度量） |
| 监控+红线（含 Laya 权重更新） | 脚本有启发式；非实时调度 |
| Phase 里程碑 gate_pass≥40%、覆盖率>80% 等 | **未达成**（changelog §七自承） |

### 计划 `.omc/ultragoal/plans/phase2-3-execution-plan.md`

明确要求改 `cascade/peer/*.py`（T1/T3/T5）——**实证 peer 无相关引用（grep 空）**。验收勾选在计划中仍为未勾。

### Laya 硬约束（审计硬规则）

- 未发现「让 Laya 学习 / 更新 Laya 权重 / 微调」实现或 changelog 违规表述。
- Task1 外环改采样配额 / MAB / 精英变异 —— 允许。
- Task4 独立频率模型 —— 允许。
- **本项：通过。**

---

## §5 P0 / P1 / P2 清单

### P0

1. **Changelog「Phase 2-3 ✅ 完成」夸大**：计划/SPEC 验收与里程碑未满足；自身仍列「应用到 peer」为下一步。不得对外宣称验收完成。
2. **Task4 生产模型缺失**：代码默认 `quality_model.json`，文件不存在；现场分数恒 0.5；harvest `+5*ml_prob` 无区分度。CRITICAL「区分度已验证」未转化为可加载产物。磁盘残留 `quality_model.pkl`（真 pickle）易误导。

### P1

1. **Task1 未接入 peer/慢环反馈**：`get_sampling_quota` / `bandit.update` / `add_elite` 无调用方。
2. **Task5 多样性未进生成/外环**：`test_diversity_bonus_integration` 为概念假集成。
3. **Task6 无 cron/loops 挂载**：非「持续」监控；三日 metrics 数值克隆，趋势不可信。
4. **短窗顺序/效果**：非 changelog 所写「prescreen 后」；「减 50%+」无证据。
5. **红线白名单滞后**：`KNOWN_MODEL_FILES` 含 `quality_model.pkl`、不含 `.json`——训练 JSON 后反会 CRITICAL 误报。
6. **Task3 peer 写盘前卫生仍缺**（harvest 侧已补，优于 changelog）。

### P2

1. 「组合覆盖率」T5≈19.8%（提案宇宙）vs T6≈66.2%（verdict 已见表内 gate_pass 占比）**同名异义**，changelog 并列表易误读。
2. Task4 计划写 XGB/LGBM，实为频率模型——应在 changelog 标明简化。
3. 短窗同步阻塞 harvest（代码自承）——规模上升后的性能债。

---

## §6 测试实证

```text
.venv/bin/python -m pytest \
  tests/test_generation_strategy.py \
  tests/test_short_window_backtest.py \
  tests/test_proposal_validator.py \
  tests/test_quality_predictor.py \
  tests/test_diversity_metrics.py \
  tests/test_monitor_metrics.py -q
→ 110 passed in ~3.9s
```

| 套件 | 收集数 | Changelog |
|------|--------|-----------|
| generation_strategy | 24 | 24 ✅ |
| short_window | 7 | 7 ✅ |
| proposal_validator | 26 | 26 ✅ |
| quality_predictor | 24 | 24 ✅ |
| diversity | 12 | 12 ✅ |
| monitor | 17 | 17 ✅ |
| **合计** | **110** | **110 ✅** |

说明：单测通过 ≠ 主路径/生产产物就绪（尤其 T4 模型、T1/T5 集成测试为 mock/概念）。

现场抽查：

```text
score_proposal_for_harvest({rsi6}) → (0.5, {})
score_proposal_for_harvest({oi})   → (0.5, {})
quality_model.json: missing
quality_model.pkl: exists, pickle protocol (非 JSON)
crontab: 无 monitor_metrics / generate_weekly_report
cascade peer 引用 generation_strategy/diversity: 0
```

---

## §7 结论与放行建议

| 问题 | 答案 |
|------|------|
| 能否宣称「Phase 2-3 执行完成」？ | **否**（验收意义）。可写：「6 Task 代码+110 单测已提交；T2/T3/T4 钩入 harvest（T4 缺模型）；T1/T5/T6 未形成闭环。」 |
| 审核状态 | **有条件通过 ~56%** |
| Laya 硬约束 | **通过** |
| 放行条件（建议） | ① 训练并落盘 `models/quality_model.json`，更新红线白名单，复测 rsi6≠oi；② peer（或明确外环入口）调用 GenerationStrategy/Elite；③ 多样性奖励真接入外环或删假测试；④ cron/supervisor 挂每日 collect + 周报；⑤ changelog 改「部分完成 / CONDITIONAL」，去掉总完成印章；⑥ 补短窗减量实证或降级措辞。 |

**签字建议**: CONDITIONAL_APPROVE — 允许合入已提交代码作为能力库；**阻塞「Phase 2-3 完成」叙事与下游 Ultragoal 勾选**，直至 P0 关闭。

---

*审计执行: New Bot 执行子代理；只读源码 + 写本 audit；未 commit/push/删除。*
