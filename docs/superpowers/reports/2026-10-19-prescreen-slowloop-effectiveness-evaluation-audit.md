# Audit: Prescreen + 慢环有效性评估报告

| 项 | 内容 |
|---|---|
| 对象 | `reports/2026-10-19-prescreen-slowloop-effectiveness-evaluation.md` |
| 对照 | `cascade/typesafe_prescreen.py`、`cascade/tier_classifier.py`、`scripts/aligned_slow_loop.py`、`scripts/backfill_prescreen.py`、`task_FM/config/aligned_verdicts.jsonl`、磁盘 `*.prescreen.json`、先验 `/workspace/shared/reviews/2026-10-19-laya-backfill-execution-503-audit.md` |
| 用户硬约束 | **Laya 只是判断模型，无法学习**（不可训练/微调/权重自进化） |
| 审核时间 | 2026-10-19 20:18 CST（Asia/Shanghai） |
| 方法 | 全文读报告 → 标「可学习」表述 → 复算 proceed/skip/gate_pass/pearson/tier → 对照 skip 规则与 tier 评分权重 |
| **结论** | **不通过** |

---

## §1 一句话

描述性方向（proceed≈30% 过门、mp↔dir_acc 近零相关）大致可复现，但报告把 **Laya 当成可学习组件**（§4.2 建议4、§5 P1、§6.2/6.3）构成 **P0 概念错误**；另把 **慢环产出的 Tier** 当作可在 prescreen 阶段使用的「更好预测器」存在循环论证。不可作路线图原文执行。

---

## §2 报告主张 vs 证据

| 主张 | 证据核对 | 判定 |
|------|----------|------|
| 样本量 147 = 507 prescreen ∩ 479 verdicts | 现网：success prescreen **1147**；verdicts **531**（ok 489）；宽松 (symbol,cov/vid) 匹配 **816**。报告数字不可复现、无分析脚本/过滤口径 | **P1 可追溯性** |
| Proceed 通过率 29.9% (40/134) | 宽松匹配：proceed 748，gate_pass 233 → **31.1%**；全量 ok verdicts 基线 gate_pass=**33.3%** | **方向成立**；未报基线 →「极差/接近随机」夸大（实为几乎不优于基线） |
| Skip 准确率 69.2% (9/13) | 匹配 skip 68，其中未过门 47 → **69.1%**；n 与报告不同但比例近 | **方向成立**；**选择偏差**：多数 skip 从未进慢环，n 小且有偏 |
| mp 失败/通过均值 0.711 vs 0.705；pearson −0.072 | 现网 proceed：fail_mp≈0.724 / pass_mp≈0.722；pearson≈**−0.012** | **无相关成立** |
| Tier S/A 通过率 95%+，优于 prescreen | Tier 由 dir_acc(0–40)+decay+mape+n_eff+prescreen(0–5)/105 构成（`tier_classifier.py`）；与 gate_pass 同属慢环事后指标。现网 proceed 中 A 过门仅 **72.5%**（非报告 95%） | **循环论证 / 样本敏感**（P0 方法） |
| Prescreen 成功率 71.2% / error 25.3% / degraded 3.5% | 现网 1147/408/56 → success **71.2%**、error **25.3%**、degraded **3.5%**（相对 1611） | **成立**（分母是全量文件，非报告「507」） |
| 7389→507→147→采用 | 7389 与 backfill 扫描一致；507 口径不清；中间省略 REGISTRY skip≈6147、enqueued 等运维事实 | **流程叙事不完整**（P1） |
| jd 22.2% / lh 48.8% | 现网 ok：jd≈29.0%、lh≈47.7% | **lh 近；jd 偏差**（子集或过时） |

---

## §3 Laya「判断不可学习」对照纠偏

用户约束：**Laya = 判断/打分模型，不能从慢环反馈中学习、训练、微调或自我进化。**

### 3.1 报告违规表述（须删改）

| 位置 | 原文要点 | 问题 |
|------|----------|------|
| §2.2 / §6.2 | 「缺乏实证反馈」「无法学习什么特征真正有效」——作为**待修复缺陷** | 把「不学习」写成系统 bug；正确表述：Laya **设计上**不做权重学习，反馈应落在**流水线规则/提示词/阈值** |
| §4.2 **建议4「引入 Laya 学习机制」** | 「将慢环结果反馈给 Laya」「让 Laya 学习哪些特征真正有效」「定期更新 Laya 的评估标准」 | **P0 概念错误**（模型学习叙事） |
| §5 表 | P1「Laya 学习机制」收益高 | 同上，优先级表传播错误目标 |
| §6.3 | 「启动 Laya 学习机制研发」 | 同上 |
| §6.3 长期 | 「自适应、**可学习**的协变量筛选系统」 | 若指 Laya 权重 → 违规；若仅指规则/阈值外环 → 须改措辞并去掉「Laya 学习」 |

### 3.2 可保留但须改类的表述

| 原文 | 正确归类（兼容不可学习） |
|------|--------------------------|
| 提高 mechanism_plausibility / effect_size 阈值 | **本地规则** `compute_skip_suggested`（当前 mp <0.4 才 skip），非训练 Laya |
| few-shot / 成功特征库 | **提示词侧**注入（代码里 `_extract_relevant_history` 已存在但被注释以避免超时）——仍是判断输入，不是权重更新 |
| 快速回测「校准 Laya 评估」 | 若=调阈值/是否 enqueue → OK；若=反传训练 Laya → **禁止** |
| 多模型集成 | 外部第二判断器，非 Laya 学习 |
| 强化学习调阈值 | 外环优化**规则阈值**可讨论；不可写成训练 Laya |

### 3.3 代码事实（支撑纠偏）

- Laya 调用路径：`typesafe_prescreen._call_laya` → HTTP `requests.post`，产出 noul/choice/score；**无训练 API**。
- `skip_suggested` 由本地纯函数 `compute_skip_suggested(plausibility, novelty, effect_size)` 决定。
- `recent_verdicts_summary` 在 `_build_state` **被注释**（注释写明避免 Laya 超时）——历史反馈目前**未**进 prompt；恢复属提示词/延迟工程，不是「学习机制」。

---

## §4 代码/流水线层面的有效性评估是否成立

### 4.1 预测有效性（报告核心）

- **成立**：在已匹配样本上，Laya `mechanism_plausibility` **不能**预测 `dir_acc` / `gate_pass`；proceed 过门率≈基线。
- **弱化**：「Prescreen 阶段无效」忽略其运维价值（错误输入拦截、中文 strip、熔断、队列门控、成本过滤）。应拆成：**排序/预测力弱** vs **门禁/降本是否有用**（报告未测后者）。

### 4.2 Tier「更好」——不成立为独立发现

- Tier **主要是慢环指标的加权摘要**（dir_acc 最大 40 分；prescreen 最多 5 分）。
- 用 Tier 预测 gate_pass ≈ 用事后分数预测事后过门 → **方法学 P0**。
- 「prescreen 阶段增加快速 tier 预估」未给出**不跑回测**如何得到 dir_acc/decay/mape；与建议3「快速回测」重复时应改称**廉价实证预筛**，不要叫 tier。

### 4.3 选择偏差 / 混杂

1. **条件化于「已进慢环」**：skip_suggested=True 多数未验证 → Skip 准确率不可推广。
2. **REGISTRY 去重**：backfill 主跑 skipped≈6147 是登记簿命中，不是 Laya 过滤——报告流程图未体现，易把「筛选效率」算到 Laya 头上。
3. **匹配口径**：147/507 无法复现；现网更宽松匹配给出相近 proceed 率，但 Tier 细分表不稳定（A：95%→72.5%）。

### 4.4 与运维审计的边界

本报告评估的是**判断力/方法**，不是 backfill 执行健康度。执行侧问题（ReadTimeout 熔断、JSON/TypeError 拆解、无 HTTP 503）见既有 execution/503 audit；本报告未覆盖，也不应混写「Laya 变聪明」。

---

## §5 P0 / P1 / P2

### P0（挡采纳）

1. **概念：Laya 学习机制** — §4.2 建议4、§5、§6.2–6.3 将慢环反馈写成训练/进化 Laya。须整段删除或改写为「外环规则/提示词/阈值」，并显式声明 Laya 权重不可学。
2. **方法：Tier 作预处理预测器** — §1.3 / 建议1 在未剥离慢环特征前宣称 Tier 优于 prescreen；属循环论证。须改为「事后分层描述」或改为「廉价回测代理指标」。

### P1（强修）

1. **基线缺失** — 应并列：全量 ok `gate_pass`≈33%、proceed≈31%，再谈「准确率」。
2. **样本不可复现** — 写明过滤规则、join 键、时间切片；附脚本或一次性命令。
3. **选择偏差处理不足** — Skip 结论降级为「探索性」；讨论未入慢环的 skip 体积。
4. **建议2 阈值 0.8** — 现网 proceed 中 mp <0.8 约占 **82%**（833/1017），与「减少 30–50%」预期矛盾；须先画 mp 分布与 gate_pass 校准曲线再定阈值。
5. **流程数字** — 7389→507 叙事补 REGISTRY skip / enqueued / degraded，避免归因全到 Laya。

### P2（改进）

1. 区分「Laya 打分」与「本地 skip 规则」两层，报告图表分列。
2. 评估门禁价值：error/degraded 拦截、成本、重复 enqueue（对照 backfill changelog）。
3. 若使用历史摘要：测延迟/超时，再决定是否恢复 `recent_verdicts_summary`（prompt，非训练）。
4. 删「强化学习自动优化」或降级为可选外环实验，避免与「可学习 Laya」连读。

---

## §6 结论与可用建议（兼容「Laya 不学习」）

**不通过** — 不可作为「下一步去训练/进化 Laya」或「用 Tier 替换 prescreen」的决策依据。可抢救的结论仅限：

- mp / 当前 skip 规则对 gate_pass **几乎无排序力**（在已回测子集上）；
- 慢环 + gate_pass/tier **作为事后验收**仍然必要。

**可用后续（允许）**

1. **调本地阈值**：改 `compute_skip_suggested`（或外加基于校准曲线的门槛），A/B 测 enqueue 量与过门率——不碰 Laya 权重。
2. **廉价实证预筛**：短窗回测（报告建议3 的合理内核）→ 过门再进全量慢环；结果用于**队列策略**，不「训练 Laya」。
3. **提示词/状态工程**：谨慎恢复或压缩 `verdict_history` 摘要；固定英文检查点、超时与熔断（运维）。
4. **上游提案质量**：禁非 str PD、JSON round-trip、中文泄漏门禁（降低 error 桶）。
5. **REGISTRY/去重/熔断**：继续按 execution audit 修 ReadTimeout→熔断等，属流水线有效性，与模型学习无关。

**禁止后续（不允许）**

- 任何「fine-tune / 反传 / 让 Laya 学习慢环结果 / 权重更新 / 可学习 Laya」表述或工单。

---

## §7 审核签字

- 审核方：New Bot（本机锁 standing；本任务不释放锁）
- 机器：`5e6e79c9-6445-4d39-92dc-e2a6b67c5763`
- 落档：本文件；盒副本 `/workspace/shared/reviews/2026-10-19-prescreen-slowloop-effectiveness-evaluation-audit.md`
