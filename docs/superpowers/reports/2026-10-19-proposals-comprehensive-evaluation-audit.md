# Audit: 7000+ 提案整体评估报告

| 项 | 内容 |
|---|---|
| 对象 | `reports/2026-10-19-proposals-comprehensive-evaluation.md` |
| 对照 | `task_FM/experiments/**/proposals/*.json`（7389）、`task_FM/config/aligned_verdicts.jsonl`（532）、`*.prescreen.json`（1611）、`data/cache/aligned_pending*.jsonl`、`scripts/sup_harvest.py`、`scripts/registry_lib.py`、先验 `prescreen-slowloop-effectiveness-evaluation-audit.md` |
| 用户硬约束 | **Laya 只是判断模型，无法学习**（不可训练/微调/权重自进化） |
| 审核时间 | 2026-10-19 20:45 CST（Asia/Shanghai） |
| 方法 | 全文读报告 → 复算提案/冗余/日产/verdict → 扇出「已验证」→ 对照 harvest/队列去重 → 扫描 Laya 学习表述 |
| **结论** | **有条件通过** |

---

## §1 一句话

报告作为**提案语料盘点**（规模、冗余、symbol/family 偏斜）大体可复现，且**未**把「训练/进化 Laya」写成主路线；但混用两套「已验证」口径、把 gate_pass≈34% 误贴到 prescreen、并夸大「队列被重复占据」（harvest/队列已按 variant_id 去重）——须修订后再当路线图执行。

---

## §2 主张 vs 证据

| 主张 | 证据核对 | 判定 |
|------|----------|------|
| 7389 提案 / 206 run / gen_0–2≈2489/2430/2466 | 现网精确吻合 | **成立** |
| 冗余 89.2%；唯一 variant≈796；Top 重复 cj/sr calendar 等 | 现网唯一≈791–796；Top10 次数与报告一致；冗余率≈89.3% | **成立** |
| 日产 10-05…10-18 表 | 日计数与报告逐行一致 | **成立** |
| peer 六分桶占比 | 与路径解析一致 | **成立** |
| 验证覆盖 6.5%=480/7389 | 现网 verdicts **532**（ok **490**）；unique key≈481。480 口径略旧/略滤，方向近 | **大致成立**；见下「口径」 |
| 通过率 34.0% | ok 上 gate_pass **163/490=33.3%**；163/480=34.0%（恰用 480 分母） | **成立（分母需写清）** |
| 高质量率 31.9%（S/A） | ok 上 S+A=**159/490=32.4%**；153/480≈31.9% | **近**；且 **26** 条 S/A 且 gate_pass=False → 与「通过」正交 |
| 内容质量 99.8% mechanism / 均长 157 | 顶层 `mechanism` 覆盖极高；抽样均长≈143；**绝大多数为中文** | **覆盖成立**；「质量高」未谈中文 PD 与 Laya 门禁摩擦 |
| Symbol 表 sr 1147/eg 903 等总数 | 与 stem 统计一致 | **成立** |
| Symbol/Family「已验证」数百～八百 + 通过率 | 用 **variant 命中后扇出到提案文件** 可复现量级（如 sr≈820/66.6%，calendar≈894/38.5%）；**不是** 480 条慢环记录 | **数字方向近；口径未声明 → P0/P1** |
| gen「已验证」1654/1657/1605、通过率≈23% | 同上扇出；与摘要 34% **不是同一总体** | **表内自洽、与摘要冲突未解释** |
| Family 总数 62；calendar 1050 等 | stem 族名约 **280+**；calendar≈973（非 1050） | **族名抽取规则不明 / 计数偏差 P1** |
| 队列 404 待处理、被重复占据 | 现网 pending **397** unique、**0** 重复 variant；inprogress 1。`registry_lib.queue_enqueue` + harvest `_reject("dedup")` 已去重 | **待处理量级近；「重复占据」不成立** |
| 浪费 89.2% prescreen | 磁盘重复文件会重复扫；但入队侧已去重；归因需拆「文件冗余」vs「队列/慢环」 | **半成立** |
| L1 预筛「已实现，34% 通过率」=prescreen | 34% 是 **gate_pass**，不是 Laya/prescreen。prescreen 文件 success/error/degraded=1147/408/56（71.2%/25.3%/3.5%） | **P0 概念串台** |

---

## §3 Laya 不可学习对照

用户约束：**Laya = 判断/打分，不能从反馈训练/微调/进化。**

### 3.1 本报告有无「训练 Laya」违规？

| 位置 | 原文要点 | 判定 |
|------|----------|------|
| 全文 | **几乎不出现「Laya」字样**；无「fine-tune Laya / 让 Laya 学习慢环」 | **未直接违规**（优于上一份 effectiveness 报告） |
| §6.2「缺乏学习机制」 | 语境是 **generation 无演进** | 可保留，但须写明「指生成/harvest 策略，**不是** Laya 权重」 |
| 建议3 质量反馈循环 | 调生成探索、mutation、精英保留 | **允许**（上游提案质量），禁止写成改 Laya |
| 建议5「修改 family-specific **评估标准**」 | 易被读成改 Laya 评分标准 | **须改措辞** → 本地 skip/入队规则或生成先验，非 Laya |
| 建议6 强化学习 / 建议7 质量预测+retrain | 外环 MDP / 独立分类器 | **允许**，须显式「独立于 Laya，不更新 Laya」 |
| 建议2/4 把 **34% gate** 当作 prescreen/L1 已实现 | 把慢环验收误贴到判断模型阶段 | **P0 串台**（效果叙事错误，虽非「学习」一词） |

### 3.2 与先验 effectiveness audit 的边界

- 上一份因「引入 Laya 学习机制」+ Tier 循环论证 → **不通过**。
- 本报告焦点是**提案库存与生成**，宜保留；但不得把「generation 反馈」偷换成 Laya 进化，也不得用 gate_pass 率证明 Laya/prescreen「已有效」。

---

## §4 方法 / 代码问题

### 4.1 两套「已验证」未声明（方法学主伤）

1. **摘要覆盖率**：≈ unique 慢环结果 / 提案文件数（480÷7389）。
2. **gen/symbol/family 表**：提案文件中 variant 能 join 到任一条 verdict 的**扇出计数**（总量可达数千），通过率被高重复 variant 加权。

后果：读者会以为「gen_0 已验证 1654 次慢环」，实际是「1654 个提案文件挂到已有 verdict」。gen≈23% vs 总 34% 的差异主要来自扇出权重，不是三代能力突变。

### 4.2 覆盖率叙事偏置

- 文件覆盖 6.5% 在 **89% 冗余** 下严重低估「想法」覆盖。
- 更相关：ok unique variant ≈474 / 唯一 variant≈796 → **约 60%** 唯一想法已有 ok 结论。
- 报告用文件分母强调「严重不足」时，应并列 unique-variant 覆盖，否则会过度驱动「盲目加速验一切重复文件」。

### 4.3 去重根因过度归咎

- **事实**：`sup_harvest` 已对 dead/existing/passing/seen_vids 与 proposal_id+version 做 `_reject("dedup")`；队列 pending **无重复 variant**。
- **仍真**：跨 run 仍写出大量同名提案 JSON → 磁盘冗余与 backfill/prescreen 扫描成本。
- 正确 P0：生成写盘前的**全局 variant 登记 / 禁止落盘重复**；或分析与 backfill 默认按 unique variant——而非「从零实施队列去重」。

### 4.4 Prescreen / Laya / 慢环未拆层

| 层 | 现网含义 |
|----|----------|
| 提案生成 | 7389 文件，中文 mechanism 为主 |
| Laya 判断 | HTTP 打分 + 本地 `compute_skip_suggested`；**不学习** |
| Prescreen 文件 | 1611；success 71.2%（非 34%） |
| 慢环 | gate_pass / tier；≈33% ok 过门 |

报告建议2「仅对 prescreen 通过做深度验证」方向可与 skip/enqueue 策略兼容，但**不能**用 34% 证明 L1 已校准。

### 4.5 「高质量」与 gate_pass 正交

存在 S/A 且未过门（现网 26）。Family 表出现「通过率 0% + 高质量数>0」（如 oi_gated_momentum）在扇出+该定义下可出现，须在指标定义中写明。

### 4.6 分析脚本不可追溯

附录称 pandas 一次性分析，未附脚本/过滤条件/variant 键定义 → family=62、已验证=480 无法一键复现。

---

## §5 P0 / P1 / P2

### P0（修订后再当路线图）

1. **声明并统一「已验证」口径** — 摘要用 unique verdict；分表若用扇出须标注「提案文件扇出」，并避免与 34% 混读。
2. **删除/改正「prescreen/L1 = 34% 通过率」** — 34% 仅可标为慢环 gate_pass；Laya/prescreen 另报 success/proceed/skip。
3. **纠正「队列被重复提案占据」** — 改为：队列已 unique；冗余危害在写盘与重复 prescreen 扫描；去重工单对齐 harvest 已有逻辑，做缺口而非重做。

### P1（强修）

1. **覆盖率并列 unique-variant**（约 60%）与文件覆盖（6.5%）。
2. **Family 抽取规则 + 复现脚本**（现网 stem 族远多于 62；Top 计数与报告有偏差）。
3. **建议3/5/6/7 加「非 Laya」脚注**；「评估标准」改为生成先验或本地规则阈值。
4. **中文 mechanism**：与「内容完整」分开评估对 Laya/中文门/strip 的影响（先验 backfill 中文门议题）。
5. **暂停 eg/lh 等**前先确认：0% 是数据/门控/样本期问题还是协变量族无效，避免过早砍探索。

### P2（改进）

1. 指标定义区分 gate_pass vs tier S/A。
2. 日趋势表加「当日唯一 variant / 当日新 variant」避免产出虚高。
3. 建议并行慢环前评估共享 checkpoint/GPU 争用（运维风险）。
4. 与 execution/503 audit 对齐：加速验证 ≠ 忽略熔断/超时。

---

## §6 结论与可用建议（兼容「Laya 不学习」）

**有条件通过** — 可作提案语料与冗余问题的**盘点底稿**；不可不经修订就执行「重做去重 / 用 34% 证明 L1 / 把反馈写成评估模型进化」。

**可保留的结论**

- 磁盘级 variant 冗余≈89% 为真实、最严重的库存问题；
- symbol/family 表现极化（sr 高、eg/部分 family 近 0）值得**生成侧**配额，而非训练 Laya；
- gen_0/1/2 在**可比口径**下难言演进（需先去掉扇出混杂再下结论）；
- 内容字段完整 ≠ 对下游判断友好（中文 PD）。

**可用后续（允许）**

1. **写盘前全局 variant 登记** / 分析与 backfill 默认 unique（补齐 harvest 未覆盖的落盘重复）。
2. **入队与验证优先级**：唯一、未判定、高不确定；沿用现有队列去重。
3. **生成策略外环**：按历史 gate_pass 调整 symbol/family 采样（规则/多臂），**不**更新 Laya。
4. **独立质量预测器**（可选）：用已验证样本训 XGB 等做排序——明确非 Laya。
5. **廉价实证预筛**（短窗回测）作队列策略，结果不反传 Laya 权重。
6. **上游提案卫生**：JSON/类型/中英门禁，降低 prescreen error 桶。

**禁止后续（不允许）**

- fine-tune / 反传 / 「让 Laya 学习慢环」/ 可学习 Laya；
- 用 Tier 或 gate_pass 事后分数冒充 Laya 阶段已校准的通过率。

---

## §7 审核签字

- 审核方：New Bot（本机锁 standing；**本任务不释放** `/workspace/shared/local-pc.lock`，由父代理释放）
- 机器：`5e6e79c9-6445-4d39-92dc-e2a6b67c5763`
- 落档：本文件；盒副本 `/workspace/shared/reviews/2026-10-19-proposals-comprehensive-evaluation-audit.md`
