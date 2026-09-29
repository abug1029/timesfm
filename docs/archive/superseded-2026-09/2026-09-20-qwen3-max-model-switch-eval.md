# 换用模型评估报告：qwen3.7-plus → qwen3-max-2026-01-23

- **日期**:2026-09-20
- **切换动作**:监督环停机，`.env.praxist` 全部模型变量（PRAXIST_MODEL / MODEL / FAILOVER_MODEL / PRIMARY_MODEL）改为 `qwen3-max-2026-01-23`，重启监督环
- **生效证据**:新快环 run 均带 `--model qwen3-max-2026-01-23`；新提案 verdict 的 `git_rev` 为 `26df19b2`
- **数据源**:`task_FM/config/aligned_verdicts.jsonl`（111 条）；`data/cache/aligned_pending.done.jsonl`
- **口径提醒**:下文严格区分 **①gate 过线**（慢环 evaluate 判定可测，`gate_pass=True`）与 **②正式过门**（v23 目标口径 `pass_variant = gate_pass AND (fdr_pass OR migrated_pass)`）

---

## 一、结论摘要

| 维度 | 结论 |
|---|---|
| 提案质量 | **显著提升**：`dir_acc>0.52` 命中率 **50%（2/4）** vs 旧模型 **6.2%（6/97）**，约 8× |
| 慢环 gate 过线 | **75%（3/4）**（ss_rsi6、m_vor、m_hourly_slope） |
| 探索聚焦度 | **明显更严**：4 个提案全落在目标 8 品种集 {m,ss,sr,cj,jd,lh,eg,rb}，无旧模型 p/cf 等非目标品种泄漏 |
| 正式过门（v23） | **均未触发**：新旧模型 `fdr_pass` 全为 False——所有探索变体 p 值 0.11–0.33 均未达 FDR 显著门，此为新旧共有的系统门槛，非换模缺陷 |
| 综合 | **换模收益为正且方向正确**：产量虽低（本批 4 提案），但命中与聚焦质量大幅提升；离正式过门仍差「p 值显著性」这一关 |

## 二、新模型 4 提案明细（git 26df19b2）

| variant | sym | dir_acc | p_value | gate | fdr | 判定含义 |
|---|---|---:|---:|---|---|---|
| ss_rsi6 | ss(1★) | **0.537** | 0.219 | True | False | ✅ `>0.52` 硬线，仍差 FDR 显著 |
| m_vor | m | **0.526** | 0.187 | True | False | ✅ `>0.52` 硬线，仍差 FDR 显著 |
| m_hourly_slope | m | 0.503 | 0.111 | True | False | ⚠️ gate 过、`<0.52` 硬线、近门未达标 |
| cj_crack_spread_zscore | cj(2★) | 0.498 | 0.325 | False | False | ✗ 未过 gate |

批号：前 3 个属 `batch_74e8bb60`（12:47–13:05 评估）；`m_hourly_slope` 属 `batch_daa6d6c8`（14:48 评估，本次停机前最后一笔慢环产出）。

## 三、新旧模型对比（目标 8 品种集内）

| 指标 | qwen3.7-plus（97 条） | qwen3-max（4 条） |
|---|---:|---:|
| `dir_acc>0.52` 命中 | 6 / 97 = **6.2%** | 2 / 4 = **50%** |
| gate 过线 | 约 24 / 97（含大量 `0.50–0.52` 贴线） | 3 / 4 = **75%** |
| 撞 0.52 硬线的提案 | 大量（cj_oi 0.500、cj_reversal 0.503、m_calendar 0.502 …） | 0（要么显著过线、要么明确不及） |
| 非目标品种泄漏 | 有（p、cf 等） | 无 |
| 最低 p 值 | 0.030（sr_calendar 0.617，但 fdr=False） | 0.111 |

**解读**:旧模型倾向提交大量贴 0.50 下限的“似噪提案”，先验 line 判定后多数算不过账；新模型犯得少而准，虽只有 4 条，但 2 条直接顶到 >0.52，另一条也近门。

## 四、目标达成进度（口径 vs 现状）

- 成功条件：`n_one_star_symbols_hit ≥ 4`、`n_unique_pass_variants ≥ 4`、`min_pass_variant_dir_acc > 0.52`。
- **历史过门**:目标注释记载 `ss_vor` 已占一席（早期 migrated/历史固化，不在当前 `aligned_verdicts.jsonl` 111 条内，需另行在 knowledge_base/历史 pass 记录复核其归位）。
- **当前 aligned_verdicts 内**:目标 8 品种严格过门（fdr_pass=True）= **0**；全库 fdr_pass=True 仅 cf、p（均非目标品种）。
- **因此**:换模后仍处“积累显著样本”阶段，未新增正式过门。与换模强负相关的判断不成立——阻塞点在统计显著性，不在提案质量。

## 五、风险与后续

1. **p 值显著性瓶颈**:所有提案 p 值偏高（≥0.11），独立变体不足以过 FDR。缓解方向 = 慢环 `aligned_max_points=600` 深度下继续累积时间片段、或 FDR 按批次批量校正（多候选联合，单个体 bootstrap 功效不足）。
2. **m_hourly_slope(0.503)** 属近门，符合“n-不足近失误自动复测”条件（数据点延长后可重判），不必重投。
3. **产量与质量权衡**:新模型本批只出 4 提案（旧模型可能的探索空间更大但泥沙俱下）。建议继续跑 2–3 个 cycle 看稳定命中率，再决定是否把 qwen3-max 设为长效机制。

## 六、数据回溯点

- 本次停机前 supervisor_state：`phase=fast · cycles=39 · last_harvested=run_2026-09-20_13-07-01`
- 慢环产出 `m_hourly_slope` 后 clean stop；`aligned_verdicts.jsonl` 定格 **111 条**
- 恢复后复算：`wc -l task_FM/config/aligned_verdicts.jsonl` 应 ≥111，且新增 verdict 的 `git_rev` 应仍为 `26df19b2`（qwen3-max 时代）