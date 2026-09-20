# 三环运行 Verdict 分析与 Peer 提案质量报告

> 日期: 2026-09-19。数据截止: 2026-09-19 10:20 UTC+8。
> Supervisor PID 1612（09-18 20:46 启动），当前 run: `run_2026-09-19_08-35-03_primary_task_FM`。
> 状态: **分析完成，待宿主裁定**。

---

## 1. 总体产出快照

| 指标 | 值 |
|---|---|
| 累计 verdicts（aligned_verdicts.jsonl） | **81** |
| 过门（gate_pass=True） | **16（19.8%）** |
| PID 1612 重启后新增 verdicts | **22** |
| PID 1612 后过门 | **2**（m_pca_momentum, sr_crack_spread_level） |
| 当前 run 代数 | gen_0 / gen_1 / gen_2（3 代） |
| Peer 提案总数 | **39**（跨 3 代 x 2 peer） |
| 唯一 symbol*covariate 组合 | 33 |
| 跨代重复提案 | 6 |
| 提案已出 verdict | 11/33（33%） |
| 提案已过门 | **0/11** |
| 提案待跑 verdict | 22 |
| 慢环当前队列 | 1（m_ccl） |
| 慢环单 verdict 耗时 | ~420s（7 min） |

---

## 2. 过门 Verdicts 全表

### 2.1 历史过门（PID 1612 前，14 个）

| # | variant_id | dir_acc | n_eff | fdr_pass | endpoint_mape |
|---|---|---|---|---|---|
| 1 | p_calendar_cyclical | 0.563 | 71 | True | 2.29 |
| 2 | cf_rsi6 | 0.531 | 71 | True | 2.07 |
| 3 | p_oi | 0.568 | 71 | True | 2.06 |
| 4 | cj_oi | 0.500 | 73 | False | 2.63 |
| 5 | cj_reversal_shadow | 0.503 | 73 | False | 3.23 |
| 6 | m_calendar_cyclical | 0.502 | 73 | False | 1.47 |
| 7 | cj_reversal_shadow_gated_02 | 0.500 | 73 | False | 3.34 |
| 8 | cj_reversal_shadow_gated_03 | 0.510 | 73 | False | 3.11 |
| 9 | sr_calendar_cyclical | **0.617** | 73 | False | 1.13 |
| 10 | cj_rsi24 | 0.520 | 73 | False | 2.66 |
| 11 | ss_calendar_cyclical | 0.568 | 73 | False | 1.86 |
| 12 | m_oi | 0.502 | 73 | False | 1.47 |
| 13 | sr_oi | 0.522 | 73 | False | 0.91 |
| 14 | cj_bb_squeeze | 0.524 | 73 | False | 2.55 |

### 2.2 PID 1612 后新过门（2 个）

| # | variant_id | dir_acc | n_eff | fdr_pass | endpoint_mape |
|---|---|---|---|---|---|
| 15 | m_pca_momentum | **0.502** | 73 | False | 1.47 |
| 16 | sr_crack_spread_level | **0.510** | 73 | False | 1.03 |

> **P0 异常**：#15 和 #16 的 dir_acc 均 < 0.52（spec 5 硬门阈值），但 gate_pass=True。
> 可能原因：gate() 函数内部有 n_eff/Bartlett 置信区间动态调整机制，使有效阈值低于 0.52。
> **需核查评估器 gate() 逻辑**确认是否符合 v23 spec 设计意图。

### 2.3 特别关注：sr_calendar_cyclical（dir_acc=0.617）

全库最高 dir_acc，但 fdr_pass=False（BH-FDR 未过）。作为亮点候选已登记。

---

## 3. 品种维度分析

| 品种 | verdicts | 过门 | 过门率 | 平均 dir_acc | 最佳 dir_acc | 诊断 |
|---|---|---|---|---|---|---|
| **sr** | 3 | 3 | 100% | 0.550 | 0.617 | 最强品种，全过门 |
| **p** | 2 | 2 | 100% | 0.565 | 0.568 | 高水平（样本少） |
| **cf** | 1 | 1 | 100% | 0.531 | 0.531 | 样本不足，待观察 |
| **cj** | 19 | 6 | 32% | 0.485 | 0.524 | 量大，过门集中于 reversal_shadow 族 |
| **ss** | 3 | 1 | 33% | 0.505 | 0.568 | calendar_cyclical 表现突出 |
| **m** | 8 | 3 | 38% | 0.488 | 0.502 | 过门均踩线（0.502） |
| **sh** | 2 | 0 | 0% | 0.489 | 0.510 | rsi6 接近但未过 |
| **i** | 2 | 0 | 0% | 0.494 | 0.497 | 接近门但未突破 |
| **lh** | 7 | 0 | 0% | 0.461 | 0.488 | 死区特征 |
| **jd** | 7 | 0 | 0% | 0.451 | 0.468 | 死区特征 |
| **eg** | **22** | **0** | **0%** | **0.453** | **0.490** | **重度死区** |
| **rb** | 3 | 0 | 0% | 0.413 | 0.437 | 死区 |
| **ma** | 1 | 0 | 0% | 0.451 | 0.451 | 数据不足 |
| **jm** | 1 | 0 | 0% | 0.461 | 0.461 | 数据不足 |

### 3.1 品种分档

| 档位 | 品种 | 特征 |
|---|---|---|
| **富矿区**（过门 + avg_da>0.52） | sr, p | 协变量有效率高 |
| **有矿区**（有 over 门但均值<0.52） | cj, ss, m, cf | 需要挑选特定协变量 |
| **贫矿区**（0 过门 + avg_da 0.48~0.50） | sh, i | 接近但未突破 |
| **死区**（0 过门 + avg_da<0.47） | eg, jd, lh, rb | 22+7+7+3=39 verdicts 全败 |

---

## 4. 协变量族分析

| 协变量族 | 总数 | 过门 | 过门率 | 平均 dir_acc | 评价 |
|---|---|---|---|---|---|
| **oi** | 11 | 4 | 36% | 0.520 | 最高效 |
| **calendar_cyclical** | 9 | 4 | 44% | 0.509 | 高产 |
| **bb_squeeze** | 5 | 1 | 20% | 0.470 | 不稳定 |
| **rsi6** | 4 | 1 | 25% | 0.488 | 一般 |
| reversal_shadow_gated_03 | 3 | 1 | 33% | 0.490 | cj 专属 |
| crack_spread_level | 3 | 1 | 33% | 0.480 | sr 专属 |
| ccl | 4 | 0 | 0% | 0.476 | 无贡献 |
| nvi | 4 | 0 | 0% | 0.480 | 无贡献 |
| vor | 3 | 0 | 0% | 0.457 | 无贡献 |
| basis_momentum | 3 | 0 | 0% | 0.460 | 无贡献 |
| crack_spread_slope | 3 | 0 | 0% | 0.463 | 无贡献 |
| crack_spread_zscore | 3 | 0 | 0% | 0.446 | 无贡献 |
| stddev | 3 | 0 | 0% | 0.469 | 无贡献 |
| ao_accel | 2 | 0 | 0% | 0.463 | 无贡献 |
| hurst | 2 | 0 | 0% | 0.438 | 无贡献 |

### 4.1 协变量族分档

| 档位 | 族 | 策略建议 |
|---|---|---|
| **有效族**（过门） | oi, calendar_cyclical, bb_squeeze, rsi6, reversal_shadow_gated, crack_spread_level | 继续探索 |
| **无效族**（4+ verdicts, 0 过门） | ccl, nvi, vor, basis_momentum, crack_spread_slope/zscore, stddev | 建议标记 DEAD |
| **数据不足族**（<=2 verdicts） | ao_accel, hurst, pca_momentum, rsi24, rsi_slope, ... | 保留观察 |

---

## 5. Peer 提案质量评估

### 5.1 提案统计

| 维度 | 值 |
|---|---|
| 总提案 | 39 |
| 唯一组合 | 33 |
| 跨代重复 | 6（15%） |
| 已出 verdict | 11/33（33%） |
| 已过门 | 0/11（0%） |
| 待出 verdict | 22/33（67%） |

### 5.2 跨代重复提案（去重失效）

| 提案 | 出现代数 | 重复次数 |
|---|---|---|
| jd_ccl | gen_0, gen_1, gen_2 | 3 |
| sr_qstick | gen_0, gen_1, gen_2 | 3 |
| m_vor | gen_1, gen_2 | 2 |
| rb_vor | gen_0, gen_2 | 2 |

> **问题**：peer 在代际间不读取前人提案，导致相同 symbol*covariate 被反复提案。
> 快环去重（harvest 的 vid 去重）在入口层挡住了部分重复，但 prompt 注入的 known_verdicts
> 未包含「已被同代 peer 提案但尚未出 verdict」的组合。

### 5.3 Peer 对死区品种的执念

| 品种 | 历史 verdicts | 历史过门 | 本轮提案数 | 评价 |
|---|---|---|---|---|
| **eg** | 22 | 0 | 5 | 22 败仍提案，peer 不吸取 |
| **jd** | 7 | 0 | 3 | 7 败仍提案 |
| **lh** | 7 | 0 | 2 | 7 败仍提案 |
| **rb** | 3 | 0 | 4 | 3 败仍提案 |

> **根因**：peer prompt 注入的 known_verdicts 以「过门/未过门」二元标记呈现，
> 但 peer 对「连续 N 次失败=该品种可能不可为」缺乏统计感知。
> 评分函数的品种历史惩罚项权重不足。

### 5.4 提案机制描述质量

Peer 提案的 mechanism 字段质量整体较高：
- 包含品种特异性分析（如鸡蛋鲜活属性无法囤积、化工装置检修窗口）
- 信号传导链逻辑完整（如 CCL 转多 -> 产业端预判供给偏紧 -> 跟随做多）
- kill_condition 和 promote_condition 结构完整
- 部分跨代重复提案的 mechanism 文本几乎相同（peer 复制自己的历史提案）
- 部分机制假设缺少对历史失败的解释（如 eg 为何再试一次会不同）

### 5.5 提案的 Verdict 转化率

| 提案 | 已出 verdict | dir_acc | gate_pass |
|---|---|---|---|
| eg_ao_accel | Yes | 0.440 | No |
| eg_basis_momentum | Yes | 0.446 | No |
| eg_gated_slope | Yes | 0.432 | No |
| eg_qstick | Yes | 0.463 | No |
| eg_stddev | Yes | 0.457 | No |
| jd_calendar_cyclical | Yes | 0.468 | No |
| jd_ccl | Yes | 0.468 | No |
| lh_calendar_cyclical | Yes | 0.437 | No |
| m_bb_squeeze | Yes | 0.483 | No |
| rb_calendar_cyclical | Yes | 0.437 | No |
| rb_oi | Yes | 0.393 | No |

> **本 run 提案的 verdict 转化率**：11/33 = 33%（慢环仍在消化中）
> **本 run 提案的过门率**：0/11 = 0%
> **最接近过门**：m_bb_squeeze (0.483)，仍差 0.037

---

## 6. 发现的问题

### P0-1: gate_pass 与 dir_acc 阈值矛盾

**现象**：m_pca_momentum (dir_acc=0.502) 和 sr_crack_spread_level (dir_acc=0.510) 的
dir_acc 均低于 spec 5 的 0.52 硬门阈值，但 gate_pass=True。

**可能原因**：
1. gate() 函数内部有 n_eff/Bartlett 置信区间的动态调整（下界放宽）
2. v23 重构时 gate 逻辑与 spec 文本出现偏差
3. 某些字段含义与表面不同（如 gate_pass 可能综合了多个条件）

**影响**：如果 gate 阈值实际低于 0.52，则 spec 5 的 kill 条件定义不被代码忠实执行。

**建议**：核查 evaluator.py 的 gate() 函数，确认阈值逻辑与 spec 一致。

### P0-2: PI Synthesis 失败导致 gen_2 无议程

**现象**：
```
PIAgent: agenda validation failed: peer_contracts missing required roles:
[exploit, falsifier]
```
gen_1->gen_2 的 PI synthesis 失败，gen_2 退回无议程（fallback to baseline behavior）。

**影响**：gen_2 peer 缺乏引导，提案方向不受控——实际表现为 gen_2 重复了 gen_0/1 的
提案（m_vor, jd_ccl, sr_qstick, rb_vor 均重复）。

**建议**：修复 PI synthesis 的 agenda validation 逻辑，确保 exploit/falsifier 角色
在 peer_contracts 中被正确生成。

### P1-1: Peer 不吸取历史失败

**现象**：eg 累计 22 verdicts 全败（best=0.490），peer 仍在 gen_0/1/2 中提案 5 次。
jd（7 败）、lh（7 败）、rb（3 败）同理。

**根因**：评分函数对品种历史失败率的惩罚权重不足；peer prompt 未传递品种级统计摘要。

**影响**：浪费 token（每个慢环 verdict ~7 min CPU + LLM cost），降低有效探索效率。

**建议**：
1. 对 N 次（如 N>=5）连续失败的 symbol*covariate 组合，在评分函数中施加递增惩罚
2. 在 peer prompt 中注入品种级统计："eg: 22 verdicts, 0 passed, best=0.490 -> 建议回避"

### P1-2: 跨代去重失效

**现象**：jd_ccl 和 sr_qstick 各被提案 3 次（gen_0/1/2 各一次）。

**根因**：快环 harvest 的去重基于 variant_id = symbol_covariate，但仅对比已有 verdicts
和 pending 队列。如果前代提案尚未出 verdict（不在 aligned_verdicts.jsonl 中也不在
aligned_pending.jsonl 中），后代 peer 会重复提案。

**建议**：在 known_verdicts 注入时，包含所有已提案的 variant_id（不仅是已有 verdict 的）。

### P2: Launcher 退出时 asyncio 清理异常

**现象**：launcher.nohup.log 尾部出现 RuntimeError: Event loop is closed。

**评价**：已知 Python asyncio 在进程退出时的常见清理问题，不影响 verdict 正确性。
标记为低优先级噪音。

---

## 7. 死区品种处置建议

以下品种累计 verdicts >= 5 且 0 过门，建议标记为 **DEAD** 或 **HOLD**：

| 品种 | verdicts | best dir_acc | avg dir_acc | 建议 |
|---|---|---|---|---|
| **eg** | 22 | 0.490 | 0.453 | **DEAD**（22 次充分证伪） |
| **jd** | 7 | 0.468 | 0.451 | **HOLD**（样本适中，暂停 5 代） |
| **lh** | 7 | 0.488 | 0.461 | **HOLD**（lh_nvi=0.488 接近） |
| **rb** | 3 | 0.437 | 0.413 | 数据不足，暂不标记 |
| **sh** | 2 | 0.510 | 0.489 | 数据不足，继续观察 |
| **i** | 2 | 0.497 | 0.494 | 数据不足，i_oi=0.497 接近 |

---

## 8. 亮点候选

| variant_id | dir_acc | 亮点 |
|---|---|---|
| **sr_calendar_cyclical** | 0.617 | 全库最高 dir_acc，但 fdr_pass=False |
| **ss_calendar_cyclical** | 0.568 | dir_acc 高，fdr_pass=False |
| **p_calendar_cyclical** | 0.563 | fdr_pass=True（仅 2 个 fdr 过门之一） |
| **p_oi** | 0.568 | fdr_pass=True |
| **cf_rsi6** | 0.531 | fdr_pass=True |

> calendar_cyclical 族在 sr/ss/p/cj/m 5 个品种过门——值得深入分析该族为何在
> 季节性强品种上表现突出。

---

## 9. 待办清单

| 优先级 | 项 | 状态 |
|---|---|---|
| P0 | 核查 gate() 逻辑：dir_acc<0.52 为何 gate_pass=True | 待办 |
| P0 | 修复 PI synthesis agenda validation（exploit/falsifier 缺失） | 待办 |
| P1 | 品种级失败惩罚：eg 22 败后标记 DEAD | 待宿主裁定 |
| P1 | 跨代去重：peer prompt 注入全量已提案 variant_id | 待办 |
| P1 | 死区品种 HOLD/DEAD 标记 | 待宿主裁定 |
| P2 | launcher asyncio 清理异常 | 低优先级 |
| - | 22 个待跑 verdict 完成 | 慢环自动处理 |

---

*报告生成: 2026-09-19 10:20 UTC+8*
*数据源: aligned_verdicts.jsonl (81 entries), supervisor_events.jsonl, run_2026-09-19_08-35-03*
