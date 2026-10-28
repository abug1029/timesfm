# 提案质量与资产处理报告 — 合理性评估 Audit

| 项 | 内容 |
|----|------|
| **日期** | 2026-10-25（Asia/Shanghai） |
| **对象** | `/home/abug/timesfm/docs/proposal_quality_and_asset_treatment_report.md` |
| **仓库 / commit** | `/home/abug/timesfm` @ `62dc675`（2026-10-25，`refactor: rename laya_prescreen to typesafe_prescreen…`） |
| **审核性质** | 报告合理性评估（事实 / 推理 / 可落地性）；**只读**报告 + 最小相关代码与数据 |
| **数据对照快照** | `task_FM/config/aligned_verdicts.jsonl` 现 **1033** 行（mtime 约 19:39）；报告生成时刻约 15:45 写 **1021** — 多数百分比接近，绝对计数有漂移 |
| **状态** | 有条件不按原文执行核心结论 |
| **合理性** | **~58%** |
| **是否建议采纳** | **有条件采纳描述性统计与分级备份思路；不建议按原文采纳「有正期望」结论与「暂停 ma/eg/fu/fg 探索」** |

授权：用户 t149u + widget t150s684；锁由总管授予 New Bot；本 audit **不** commit/push/删改实现/改报告正文。

---

## §1 一句话

报告的 **tier / 品种 / 族分布数字大体可复核**，但把「S/A 子集高于 0.50」偷换成「探索整体有正期望」、用选择性趋势指标宣称「质量在改善」，并建议暂停仍在 `praxist_goal.yaml` 目标集内的品种 — **核心结论与 P0 行动不可按原文执行**。

---

## §2 报告主张 vs 实证表

对照源：`aligned_verdicts.jsonl`（现 1033）、`task_FM/experiments/**/*.prescreen.json`（现 265）、`scripts/praxist_goal.yaml`、`task_FM/evaluations/fm_eval/evaluator.py`、`cascade/tier_classifier.py`、`cascade/typesafe_prescreen.py`、`docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`。

| # | 主张（报告） | 实证 | 判定 |
|---|--------------|------|------|
| 1 | Verdict 总数 1021；Gate Pass 32.2% (329/1021) | 现 1033；gate_pass True **333 (32.2%)**。9 月块与报告一致（188/52/27.7%）。10 月由 833→844。属生成后增量漂移 | ⚠️ 比例准，绝对数过时 |
| 2 | dir_acc 均值 0.4429，≥0.52 占 23.3%；S/A 24.8% (253) | 现均值 **0.4426**，≥0.52 **23.2% (240)**；S/A **255 (24.7%)**。Tier 均值与报告几乎一致（S 0.5522 等） | ✅ 基本站得住 |
| 3 | EV 在「v23 重构 (2026-09-14)」从 verdict schema 移除 | 现 schema=`fm.aligned_verdict.v2`，**无任何 ev/EV 键**；evaluator 头注释写明 PF/EV/MaxDD 已退役；设计文 `2026-09-14-prediction-quality-redesign-design.md` 确删 EV。但「v23」在该文中多指局部补丁，整包更宜称 **预测质量重构**，不宜绑死「v23=退役 EV」 | ⚠️ 事实对，命名偏松 |
| 4 | Prescreen 251：Success 0 / Degraded 98 / Error 153；Laya 不可达 | 现 **265** 文件：success **0**，error **153**，degraded **112**；note 多为「Laya 短路降级中」/503/超时；plaus/eff **全 null**。模块已更名为 `typesafe_prescreen`（仍调 Laya 端点） | ✅ 现象成立（计数略增） |
| 5 | Gate pass ≈ S/A，故 gate「有效筛选高质量」 | gate_pass=333 中 tier：**A138 / B104 / S78 / C13**；另有 **39** 个 S/A **未** gate_pass。gate 硬门是 n/n_eff/dir_acc≥~0.52（evaluator），tier 是多维打分（`tier_classifier`）— **两轴不同**。32.2% vs 24.8% 并不「接近到可互相替代」 | ❌ 概念偷换 |
| 6 | 「有正期望」：P(S/A)×(0.55−0.50)=1.24% | **全体** E[dir_acc−0.50]≈ **−5.7%**（z≈−11 vs 0.5）。公式只计 S/A 上行、忽略 B/C/D 下行与探索成本。若只看 gate_pass 子集均值≈0.530，可讨论「过门后再用」的条件期望，但报告算式不是这个 | ❌ 推理不成立 |
| 7 | 9→10 月「整体预测质量在改善」 | gate/S/A/≥0.52 占比升；但 **dir_acc 均值 0.4836→0.434** 明显变差。报告表格写出均值下降却结论写「改善」— 选择性叙事 | ❌ / ⚠️ 证据矛盾 |
| 8 | Top/Bottom 品种与 cov family 表 | ta/sh/ao/i 等排序与现码一致；ma/eg/fu/fg/jd 确为最差档。族：momentum/term_structure/calendar 相对较好，volatility 较差，unknown≈全 `no_data`/`timeout`（dir_acc=0） | ✅ 描述准（未知族是数据失败非「族无效」） |
| 9 | 核心资产≈253；观察≈B∧gate≈100；低值≈668 | B∧gate_pass 现 **104**；S/A∧dir_acc≥0.52 现 **202**（与 §2.3 P0「约 200」一致）。但 §2.1 用「凡 S/A」与 §2.3「S/A 且 ≥0.52」**两套口径未统一** | ⚠️ 数量近，定义打架 |
| 10 | 备份路径 `task_FM/assets/{core,important,observe}/`；全量约 2–3GB | `assets/` **尚不存在**（属提案）；`task_FM/experiments`≈**3.0G**，checkpoints≈407M — 量级说法合理。脚本用 `cov_name`，verdict **无此字段**（有 `variant_id`/`cov_family`）；复制 proposal/checkpoint 仍为 TODO | ⚠️ 方向可做，脚本不可直接跑 |
| 11 | P0：暂停 ma/eg/fu/fg 探索；修复 Laya | `praxist_goal.yaml` `target_symbols` **含 ma,eg,fu,fg,jd**；成功条件 `all_symbols_pass_phase1`。暂停四品种与「全品种达标」**直接冲突**。修复 Laya/短路属运维合理，且未主张训练 Laya | ❌ 暂停探索；✅ 修 Laya（表述需标明短路/降级） |
| 12 | 调整 peer prompt 提升 dir_acc | 无实证链路（未展示 prompt→dir_acc 因果）；与正期望搜索 spec（`search_policy: shadow`）的「树/父节点/缩水增量」框架未对齐 | ⚠️ 空泛，缺证据 |

**Laya 硬约束**：报告仅提「修复服务 / 备用」，**未**主张学习/训练/进化/改权重。`typesafe_prescreen` 设计为 judgment 注入式预筛。本项 **通过**（无违规），但「修复」应写清是恢复端点可用性或短路策略，而非改模型。

---

## §3 推理 / 建议合理性

### 3.1 自洽性

- **循环/偷换**：「S/A 高于随机」→「探索有正期望」忽略失败质量与成本；「gate≈S/A」混淆硬门与评级。
- **正期望口径冲突**：仓库另有 `2026-10-05-positive-ev-factor-search-spec.md`，正期望定义为扣尝试成本、重复与选择上偏后的增量；报告的 1.24% 算式与该 spec **不是同一概念**，却共用「正期望」词。
- **趋势**：同一节承认均值下降又写「改善」— 内部不一致。

### 3.2 可落地性（相对现架构）

| 建议 | 与 peer→proposals→prescreen→harvest→慢环 / Praxist 关系 | 结论 |
|------|----------------------------------------------------------|------|
| 分级备份 S/A（及 checkpoint） | 不改收割逻辑；checkpoint 对核心 202 条路径均存在 | 可做（先统一口径、修脚本字段） |
| 聚焦 ta/sh/momentum 等 | 可作为 **配额倾斜**，不能替代 goal 全品种封账 | 有条件 |
| 暂停 ma/eg/fu/fg | 与 `target_symbols` + `all_symbols_pass_phase1` 冲突 | **不可按原文** |
| 修复 Laya / 降级 | 与 typesafe prescreen 一致；当前全是 error/degraded | 可做 |
| 6 个月归档 C/D | 可能影响复现与审计轨迹；需保留索引/指纹 | 需另定策略 |
| 改 peer prompt | 未接 search_policy/shadow 与收获门 | 暂不作为 P0 |

---

## §4 遗漏与风险

1. **全体 dir_acc 显著低于 0.50**（最大的反证）未进入「是否有正期望」的主结论。
2. **小样本明星品种**：ta 仅 n=12 且 100% S/A，抽样噪声与选择上偏未讨论。
3. **unknown 族**：实为 `no_data`/`timeout`，写成「暂停该族探索」易误导为机制无效。
4. **核心资产表「dir_acc 均值」**：对 ss/i 等用的是 **该品种全体** 均值（可 <0.50），不是 S/A 子集均值 — 标签误导。
5. **Prescreen「无法过滤」**：准确；但未区分电路短路（degraded）与纯 error，运维动作不同。
6. **存储 / 清理**：未评估与 experiments 保留策略、指纹、preregistry 的交互。
7. **姊妹文档**：`docs/proposal_quality_assessment_report.md`（更早、同套数字）与本报告大量重复；资产方案是增量，质量结论同源，缺陷同源。

---

## §5 P0 / P1 / P2

### P0（若按报告行动会出事）

1. **不得**把「P(S/A)×5%」当作探索正期望证据；对外结论需改为：全体负偏，或明确「仅对 gate_pass / 已晋升子集」的条件口径，并扣成本。
2. **不得**暂停 `ma/eg/fu/fg`（均在 `target_symbols`）；最多改为降配额 / 换族 / 先修数据，并经 goal 变更流程。
3. **统一资产口径**：§2.1「凡 S/A」vs §2.3「S/A∧dir_acc≥0.52」二选一写死；脚本字段改为 `variant_id`（勿用 `cov_name`）。

### P1

4. 趋势节必须同时报告 dir_acc **均值下降**，禁止单凭 gate/S/A 占比写「整体改善」。
5. 「修复 Laya」改为：确认短路器状态、端点 503、与 `typesafe_prescreen` 降级路径；成功判据=出现非空 plaus/eff 的 `success`。
6. 备份方案先跑通「verdict + 已存在 checkpoint_path」；proposal JSON 复制需按 `variant_id` 解析 experiments，不可 TODO 上生产。

### P2

7. 澄清 EV 退役表述（预测质量重构 vs 「v23」）。
8. unknown/`no_data` 从「族评级」挪到「数据质量」章节。
9. 与 `search_policy: shadow` 正期望搜索 spec 对齐用词，避免两套「正期望」。

---

## §6 结论

| 项 | 判定 |
|----|------|
| **总体合理性** | **~58%** |
| **建议** | **有条件采纳**：描述性统计（tier/品种/族/prescreen 故障）可作参考；分级备份思路可改口径后实施。**不建议按原文执行**：「有正期望」结论、暂停目标品种探索、未修脚本的「立即提取核心资产」自动化。 |
| **一句话** | 数大体可核，**结论与目标体系打架** — 先改口径与建议，再谈执行。 |

---

## 附录 A：复核命令摘要（只读）

```text
wc -l task_FM/config/aligned_verdicts.jsonl   # 1033
# Python 聚合 tier / gate_pass / monthly / symbol / cov_family
# glob task_FM/experiments/**/*.prescreen.json → status Counter
# grep target_symbols scripts/praxist_goal.yaml
```

## 附录 B：落档

- WSL: `/home/abug/timesfm/docs/proposal_quality_and_asset_treatment_report-audit.md`
- Box mirror: `/workspace/shared/reviews/proposal_quality_and_asset_treatment_report-audit.md`（由执行端同步）
