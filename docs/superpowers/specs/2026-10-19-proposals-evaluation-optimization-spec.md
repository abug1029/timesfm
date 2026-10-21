# 7000+ 提案整体评估规范（Spec v3.1）

**文档类型**: 技术规范（Specification）  
**版本**: 3.1  
**日期**: 2026-10-19  
**基于**: `reports/2026-10-19-proposals-comprehensive-evaluation.md` + audit `2026-10-19-proposals-comprehensive-evaluation-audit.md` + spec audit `2026-10-19-proposals-evaluation-optimization-spec-audit.md`  
**状态**: v3.1 修订完成（P1 全部关闭，可执行 Phase 1）

---

## 0. 文档目的

本规范定义 **7000+ 协变量提案库存** 的评估方法、指标口径、问题诊断与优化路线，确保：
1. 指标定义清晰、可复现
2. 三层架构（生成 → Laya 判断 → 慢环验证）严格分离
3. 所有优化建议**不违反"Laya 不可学习"硬约束**
4. 去重/加速/反馈策略与现有 harvest/队列逻辑兼容

---

## 1. 系统架构与职责边界

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: 提案生成（sup_harvest + 多 peer）              │
│ - 输入: symbol/family 配置、历史 verdicts（只读）       │
│ - 输出: 提案 JSON 文件（mechanism/symbol_fit/...）      │
│ - 职责: 探索新协变量想法                                │
│ - 约束: 可调整生成策略（采样/变异/精英保留）            │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Laya 判断（typesafe_prescreen）                │
│ - 输入: 提案 JSON + symbol context                      │
│ - 输出: prescreen.json（mechanism_plausibility/novelty）│
│ - 职责: 快速过滤明显不合理提案                          │
│ - 约束: **不可学习/微调/权重更新**（用户硬约束）        │
│ - 现状: success 71.2%, error 25.3%, degraded 3.5%       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 3: 慢环验证（aligned_slow_loop）                  │
│ - 输入: prescreen success 提案                          │
│ - 输出: verdict（gate_pass/tier/dir_acc/...）           │
│ - 职责: 深度回测验证提案实际预测能力                    │
│ - 约束: 可调整验证优先级/并行度，但不反馈到 Laya        │
│ - 现状: 532 verdicts, gate_pass 33.3%, S/A 32.4%        │
└─────────────────────────────────────────────────────────┘
```

### 1.2 关键约束

| 约束 | 说明 | 违反示例 |
|------|------|----------|
| **Laya 不可学习** | Laya 是判断模型，不可训练/微调/权重自进化 | ❌ "让 Laya 学习慢环反馈" |
| **队列已去重** | `registry_lib.queue_enqueue` + harvest `_reject("dedup")` 已保证 unique variant | ❌ "实施队列去重" |
| **扇出计数需声明** | 用提案文件 join verdict 会放大高重复 variant，需明确标注 | ❌ 混用 unique 与扇出口径 |

---

## 2. 指标定义与口径

### 2.0 Variant ID 定义与 Join 规则（v3 新增）

**三种 variant_id 键**：
1. **stem**：提案文件名（不含扩展名），如 `p_calendar_cyclical`
   - 唯一 stems: 796
   - 用于：文件级统计、去重检查
   
2. **proposal_id**：提案 JSON 中的 `proposal_id` 字段
   - 唯一 proposal_ids: 805
   - 用于：提案身份标识、版本追踪
   
3. **(symbol, cov_override)**：提案 JSON 中的组合键
   - 唯一组合: ~480
   - 用于：业务逻辑、family 分组

**verdict variant_id 格式**：
- 格式：`{symbol}_{cov_override}`，如 `p_calendar_cyclical`
- 与 stem **基本一致**，但可能含 fingerprint（如 `_aligned_p6`）
- Join 规则：verdict.variant_id == proposal.stem（忽略 fingerprint 后缀）

**推荐主键**：
- **统计报表**：使用 stem（796 unique）
- **业务逻辑**：使用 (symbol, cov_override)（480 unique）
- **版本追踪**：使用 proposal_id（805 unique）

**严禁混用**：
- ❌ 用 stem 统计 symbol/family 分组（会混入 fingerprint）
- ❌ 用 proposal_id 做去重（与 stem 不完全一致）
- ✅ 明确声明使用的键，并在表头标注

### 2.1 提案库存指标

| 指标 | 定义 | 计算公式 | 现网值 | 口径说明 |
|------|------|----------|--------|----------|
| **总提案数** | 磁盘上所有提案 JSON 文件数 | `count(proposals/*.json)` | 7389 | 含重复 variant |
| **唯一 variant 数** | 不同 variant_id 的数量 | `count(unique variant_id)` | ~796 | 去重后 |
| **冗余率** | 重复提案占比 | `(总提案 - 唯一 variant) / 总提案` | 89.2% | 磁盘级冗余 |
| **平均重复次数** | 每个 variant 的平均文件数 | `总提案 / 唯一 variant` | 9.3 | - |

### 2.2 验证覆盖指标

| 指标 | 定义 | 计算公式 | 现网值 | 口径说明 |
|------|------|----------|--------|----------|
| **文件覆盖率** | 已验证提案文件占比 | `已验证文件数 / 总提案数` | 6.5% | 分母含重复 |
| **唯一 variant 覆盖率** | 已有 ok verdict 的唯一 variant 占比 | `unique verdict variant / 唯一 variant` | ~60% | **推荐主指标** |
| **verdict 总数** | 慢环输出的裁决记录数 | `count(aligned_verdicts.jsonl)` | 532 | 含重复 variant 多次验证 |
| **ok verdict 数** | status=ok 的裁决数 | `count(status=ok)` | 490 | 有效验证 |

**关键区分**：
- **文件覆盖率 6.5%** 强调"大量提案文件未验证"（在 89% 冗余下严重低估想法覆盖）
- **唯一 variant 覆盖率 ~60%** 强调"大部分独特想法已有结论"（更反映实际进度）
- **报告时必须并列两者**，避免误导

### 2.3 质量指标

| 指标 | 定义 | 计算公式 | 现网值 | 所属层 |
|------|------|----------|--------|--------|
| **Prescreen 成功率** | Laya 判断 success 占比 | `success / 总 prescreen` | 71.2% | Layer 2 |
| **Prescreen proceed 率** | 未被 skip_suggested 的占比 | `proceed / success` = 88.7%；`proceed / total` = 63.1% | 88.7% (success 口径) | Layer 2 |
| **Gate pass 率** | 慢环 gate_pass=True 占比 | `gate_pass / ok verdicts` | 32.3% (156/483) | **Layer 3** |
| **高质量率（S/A）** | tier=S 或 A 的占比 | `(S+A) / ok verdicts` | 32.4% | **Layer 3** |
| **平均 dir_acc** | 方向准确率均值 | `mean(dir_acc)` | 0.453 | Layer 3 |

**严禁混淆**：
- ❌ "L1 预筛 34% 通过率" → 34% 是 **慢环 gate_pass**，不是 prescreen
- ✅ "慢环 gate_pass 率 32.3%"
- ✅ "Prescreen success 率 71.2%"

**gate_pass 真实条件**（基于代码复算，非简单阈值）：
- 现网 156 个 gate_pass 中：
  - 63.5% 的 dir_acc >= 0.52
  - 71.8% 的 p_value is not None
  - 仅 2.6% 的 fdr_pass=True
- **结论**：gate_pass 不是简单的 "dir_acc > 0.52 且统计显著"，而是多层条件组合。禁止在文档中写死单一阈值。

### 2.4 分组统计口径

对 symbol/family/generation 分组时，必须声明使用哪种口径：

| 口径 | 定义 | 适用场景 | 注意事项 |
|------|------|----------|----------|
| **提案文件口径** | 按提案文件 join verdict，高重复 variant 被多次计数 | 评估"文件处理效率" | 通过率被重复 variant 加权 |
| **唯一 variant 口径** | 按 unique variant_id 聚合，每个 variant 只计一次 | 评估"想法质量" | **推荐主口径** |
| **verdict 口径** | 按 verdict 记录统计，同一 variant 多次验证分别计数 | 评估"验证一致性" | 需检查多次验证结果是否一致 |

**规范要求**：
- 摘要/结论使用 **唯一 variant 口径**
- 详细分析表可并列多种口径，但必须标注
- 禁止混用口径导致自相矛盾（如 gen 表 23% vs 摘要 34%）

---

## 3. 现状盘点（修正后）

### 3.1 提案库存

| 指标 | 值 | 评估 |
|------|---|------|
| 总提案数 | 7389 | ✅ 充足 |
| 唯一 variant | ~796 | - |
| 冗余率 | 89.2% | ❌ **最严重问题** |
| 平均重复次数 | 9.3 | - |

**冗余根因**：
- ✅ **事实**：跨 run 写出大量同名提案 JSON → 磁盘冗余 + backfill/prescreen 重复扫描成本
- ❌ **误区**：队列 pending 无重复 variant（harvest 已去重）
- ✅ **正确 P0**：生成写盘前的全局 variant 登记 / 禁止落盘重复

### 3.2 验证覆盖

| 指标 | 值 | 评估 |
|------|---|------|
| 文件覆盖率 | 6.5% | ⚠️ 在 89% 冗余下严重低估 |
| **唯一 variant 覆盖率** | **~60%** | ✅ **实际进度良好** |
| verdict 总数 | 532 | - |
| ok verdict | 490 | - |

**关键洞察**：
- 60% 的独特想法已有慢环结论 → 无需"盲目加速验一切重复文件"
- 优先级：**唯一、未判定、高不确定** variant

### 3.3 质量分布（唯一 variant 口径）

| 层 | 指标 | 值 | 评估 |
|----|------|---|------|
| Layer 2 | Prescreen success 率 | 71.2% | ✅ 良好 |
| Layer 2 | Prescreen proceed 率 | 88.7% | ✅ 良好 |
| Layer 3 | Gate pass 率 | 33.3% | ⚠️ 需提升 |
| Layer 3 | 高质量率（S/A） | 32.4% | ⚠️ 需提升 |
| Layer 3 | 平均 dir_acc | 0.453 | ⚠️ 低于 0.52 门槛 |

### 3.4 Symbol 表现（唯一 variant 口径，复算于 2026-10-19）

| Symbol | 唯一 OK variant | Gate pass 数 | Gate pass 率 | 评估 |
|--------|----------------|-------------|-------------|------|
| rb | 66 | 19 | 28.8% | ⚠️ 中等 |
| jd | 63 | 14 | 22.2% | ⚠️ 需提升 |
| m | 60 | 20 | 33.3% | ⚠️ 中等 |
| lh | 46 | 22 | **47.8%** | ✅ 良好 |
| ss | 42 | 14 | 33.3% | ⚠️ 中等 |
| sr | 38 | 17 | **44.7%** | ✅ 良好 |
| eg | 37 | 0 | 0% | ❌ 需诊断 |
| cj | 31 | 8 | 25.8% | ⚠️ 需提升 |
| p | 21 | 8 | 38.1% | ⚠️ 中等 |
| i | 19 | 9 | **47.4%** | ✅ 良好 |
| cf | 15 | 8 | 53.3% | ✅ 优秀 |
| sh | 11 | 6 | 54.5% | ✅ 优秀 |
| ta | 6 | 6 | 100% | ✅ 优秀（样本小） |
| ao | 5 | 3 | 60.0% | ✅ 优秀（样本小） |
| ma | 6 | 0 | 0% | ❌ 需诊断（样本小） |
| fu | 5 | 0 | 0% | ❌ 需诊断（样本小） |
| px | 4 | 0 | 0% | ❌ 需诊断（样本小） |
| jm | 2 | 0 | 0% | ❌ 需诊断（样本极小） |

**关键修正**（v2 → v3）：
- **lh**: 47.8%（非 0%）→ **不应暂停探索**
- **i**: 47.4%（非 0%）→ **不应暂停探索**
- **sr**: 44.7%（非 68%）→ 良好但非"优秀"
- **eg**: 0% 方向正确，需诊断
- **cf/sh/ta**: 表现优异，可增加采样

**注意**：eg/ma/fu/px/jm 0% 通过率需先诊断根因（数据问题？门控问题？协变量族无效？样本量过小？），避免过早砍探索。样本量 <10 的 symbol 不作为"低效"结论依据。

### 3.5 Family 表现（唯一 variant 口径，复算于 2026-10-19）

| Family | 唯一 OK variant | Gate pass 数 | Gate pass 率 | 评估 |
|--------|----------------|-------------|-------------|------|
| rsi6 | 20 | 13 | **65.0%** | ✅ 优秀 |
| crack_spread_slope | 28 | 13 | **46.4%** | ✅ 优秀 |
| calendar_cyclical | 47 | 20 | **42.6%** | ✅ 良好 |
| reversal_shadow | 10 | 4 | 40.0% | ✅ 良好（样本小） |
| rsi_slope | 10 | 4 | 40.0% | ✅ 良好（样本小） |
| basis_momentum | 27 | 10 | **37.0%** | ✅ 良好 |
| oi | 31 | 11 | 35.5% | ⚠️ 中等 |
| crack_spread_zscore | 18 | 6 | 33.3% | ⚠️ 中等 |
| ccl | 27 | 3 | **11.1%** | ⚠️ 需提升 |
| bb_squeeze | 28 | 7 | 25.0% | ⚠️ 中等 |
| vor | 25 | 6 | 24.0% | ⚠️ 中等 |
| nvi | 24 | 7 | 29.2% | ⚠️ 中等 |
| hurst | 20 | 6 | 30.0% | ⚠️ 中等 |
| vwap_deviation | 20 | 5 | 25.0% | ⚠️ 中等 |
| gated_slope | 18 | 5 | 27.8% | ⚠️ 中等 |
| stddev | 15 | 1 | 6.7% | ❌ 需诊断 |

**关键修正**（v2 → v3）：
- **basis_momentum**: 37.0%（非 0%）→ **不应暂停探索**
- **ccl**: 11.1%（非 1%）→ 需提升但非"极差"
- **rsi6**: 65.0% → 表现优异，可增加采样
- **stddev**: 6.7% → 需诊断

**注意**：Family 抽取规则基于 `cov_override` 字段（非 stem 解析）。现网 unique (symbol, cov_override) 组合 ~480 个，与 stem 796 不同。分组表必须声明使用 `cov_override` 作为 family 键。

### 3.6 Generation 演进（唯一 variant 口径）

| Generation | 唯一 variant | 已验证 | Gate pass 率 | 评估 |
|------------|-------------|--------|-------------|------|
| gen_0 | ~260 | ~250 | ~23% | - |
| gen_1 | ~255 | ~245 | ~24% | - |
| gen_2 | ~260 | ~250 | ~23% | - |
| gen_3 | ~5 | ~5 | ~50% | 样本不足 |

**关键结论**：在**可比口径**（唯一 variant）下，gen_0/1/2 难言演进。需去掉扇出混杂后再下结论。

---

## 4. 问题诊断（修正后）

### 4.1 P0：磁盘级 variant 冗余（89.2%）

**现象**：
- 7389 个提案文件，仅 ~796 个唯一 variant
- 跨 run 写出大量同名提案 JSON

**根因**：
- 生成过程未检查已存在的 variant_id
- 不同 run/generation 之间缺乏协调
- harvest 已在入队前去重，但**写盘前未拦截**

**影响**：
- 浪费 89.2% 的 prescreen 扫描成本
- 磁盘占用膨胀
- 不影响队列/慢环（已去重）

**正确解法**：
1. **写盘前全局 variant 登记**：生成前查询全局 registry，禁止落盘重复
2. **分析与 backfill 默认 unique**：扫描时自动去重
3. ❌ **不重做队列去重**（harvest 已实现）

### 4.2 P0：部分 Symbol/Family 表现极差

**现象**（修正后，基于复算数据）：
- **eg**: 0% gate pass 率（37 unique variant）→ 需诊断
- **ma/fu/px/jm**: 0% gate pass 率，但样本量极小（<10）→ 需诊断，但不作为"低效"结论依据
- **stddev**: 6.7% gate pass 率（15 unique variant）→ 需诊断
- **ccl**: 11.1% gate pass 率（27 unique variant）→ 需提升

**重要修正**（v2 → v3）：
- ❌ **删除**：lh/i 不是 0%（实际 47.8%/47.4%）
- ❌ **删除**：basis_momentum 不是 0%（实际 37.0%）
- ✅ **保留**：eg 确实 0%，需诊断

**诊断要求**（暂停前先确认）：
1. **数据质量**：这些 symbol/family 的基础数据是否完整/正确？
2. **门控问题**：是否因 gate_pass 条件过严导致全挂？
3. **协变量族无效**：这些 family 的协变量本身预测能力弱？
4. **样本期问题**：是否因验证样本期特殊（如极端行情）？
5. **样本量问题**：小样本（<10）的 0% 是否统计显著？

**禁止**：未诊断前直接暂停生成。特别是 lh/i/basis_momentum 等实际表现良好的类别，**严禁**基于错误数据暂停探索。

### 4.3 P1：Generation 无演进

**现象**：gen_0/1/2 在唯一 variant 口径下 gate pass 率一致（~23%）

**可能根因**：
1. 选择压力不足：未基于历史 gate_pass 调整 symbol/family 采样
2. 变异策略未针对成功特征优化
3. 缺乏精英保留机制
4. 评估标准未反馈到**生成策略**（非 Laya）

**正确解法**：
- ✅ 按历史 gate_pass 调整 symbol/family 采样配额（规则/多臂老虎机）
- ✅ 精英保留：保留高质量提案作为种子
- ❌ **禁止**：更新 Laya 权重/让 Laya 学习

### 4.4 P1：中文 mechanism 与 Laya 门禁摩擦

**现象**：
- 99.8% 提案有 mechanism 描述
- **绝大多数为中文**
- Laya 要求英文 state（先验 backfill 中文门议题）

**影响**：
- 中文 mechanism 可能导致 Laya 判断质量下降
- prescreen error/degraded 桶可能含中文相关错误

**解法**：
- 上游提案卫生：JSON/类型/中英门禁
- 降低 prescreen error 桶
- ❌ **禁止**：训练 Laya 理解中文

---

## 5. 优化路线（修正后）

### 5.1 P0：写盘前全局 variant 登记（1-2 周）

**目标**：将磁盘冗余率从 89.2% 降至 <10%

**方案**：
1. **全局 variant registry**：
   - 维护 `data/cache/variant_registry.jsonl`
   - 记录所有已生成的 variant_id (stem) + 首次生成时间 + run_id
   
2. **生成写盘前检查**（**关键修正**：钩子在生成写盘，非 harvest）：
   - peer 生成提案后、写盘前查询 registry
   - 若 variant_id (stem) 已存在，跳过写盘或生成新 variant_id
   - **注意**：`sup_harvest` 是收割/入队逻辑，写盘在 peer 生成侧
   
3. **harvest 作为第二道防线**：
   - 沿用 harvest 的 `_reject("dedup")` 队列去重
   - 写盘前拦截是**额外防线**，不替代 harvest 去重
   
4. **兼容现有逻辑**：
   - 不修改 harvest 核心逻辑
   - 不修改队列去重（已实现）

**预期效果**：
- 减少 80%+ 磁盘冗余
- 降低 prescreen 扫描成本
- 不影响队列/慢环（已去重）

**实施难度**：中  
**风险**：低

### 5.2 P0：诊断低效 Symbol/Family（2-4 周）

**目标**：识别 eg（0%，n=37）/ stddev（6.7%）/ ccl（11.1%）等低通过率 symbol/family 的根因；小样本 0%（ma/fu/px/jm）仅作观察，不作为"低效"结论依据

**方案**：
1. **数据质量检查**：
   - 检查这些 symbol 的基础数据完整性
   - 验证数据对齐/时间戳正确性
   
2. **门控分析**：
   - 分析 dir_acc 分布，是否因门槛过严
   - 检查 gate_pass 判定逻辑
   
3. **协变量族有效性**：
   - 分析这些 family 的协变量是否本身预测能力弱
   - 对比其他 symbol 上同 family 的表现
   
4. **样本期问题**：
   - 检查验证样本期是否有极端行情
   - 分析不同时间窗口的稳定性

**预期效果**：
- 识别系统性问题并修复
- 避免过早砍探索
- 优化 symbol/family 配额

**实施难度**：中  
**风险**：中

### 5.3 P1：生成策略外环（规则/多臂，不更新 Laya）（2-4 周）

**目标**：实现 generation 间质量提升（每代 +5%）

**方案**：
1. **历史反馈分析**：
   - 提取 gate_pass 提案的共同特征（symbol/family/mechanism 关键词）
   - 识别高效/低效组合
   
2. **采样配额调整**（规则）：
   - 高通过率 symbol/family 增加采样比例
   - 低通过率 symbol/family 减少采样比例
   - 保留 10-20% 探索预算
   
3. **多臂老虎机**（可选）：
   - 每个 symbol/family 作为一个臂
   - UCB 或 Thompson Sampling 动态分配
   - **明确不更新 Laya**
   
4. **精英保留**：
   - 保留 top-K 高质量提案作为种子
   - 基于精英提案生成变异体

**预期效果**：
- gate pass 率从 33% 提升至 40%+
- 高质量率从 32% 提升至 40%+
- 实现持续质量改进

**实施难度**：高  
**风险**：中  
**约束**：**不更新 Laya 权重**

### 5.4 P1：独立质量预测器（可选，1-3 月）

**目标**：预测未验证提案质量，优先验证高潜力 variant

**方案**：
1. **特征工程**：
   - 提取提案特征（symbol/family/mechanism 关键词/长度等）
   - 利用已验证的 ~480 unique variant 作为训练数据
   
2. **模型选择**：
   - 二分类：预测是否 gate_pass
   - 模型：XGBoost/LightGBM/随机森林
   - **明确独立于 Laya，不更新 Laya**
   
3. **应用**：
   - 对未验证 variant 进行预测
   - 优先验证高预测质量的 variant
   - 主动学习：定期 retrain 模型

**预期效果**：
- 提升验证效率 2-3 倍
- 更快发现高质量提案

**实施难度**：高  
**风险**：中  
**约束**：**独立于 Laya，不更新 Laya**

### 5.5 P1：廉价实证预筛（短窗回测）（1-2 月）

**目标**：在入队前进行快速实证验证，减少无效深度验证

**方案**：
1. **短窗回测**：
   - 对 prescreen success 提案进行 100-200 时间点快速回测
   - 仅 dir_acc > 0.50 的提案进入完整慢环（588 时间点）
   
2. **队列策略**：
   - 短窗回测结果写入 prescreen.json 或独立文件
   - 慢环优先验证短窗通过的提案
   
3. **不反馈 Laya**：
   - 短窗回测结果**不反传 Laya 权重**
   - 仅用于队列优先级排序

**预期效果**：
- 减少 50%+ 无效深度验证
- 提升验证吞吐量

**实施难度**：高  
**风险**：中  
**约束**：**不反馈 Laya**

### 5.6 P2：上游提案输入卫生（持续）

**目标**：降低 prescreen error/degraded 桶，提升 Laya **输入**质量

**方案**：
1. **JSON 门禁**：
   - 写盘前验证 JSON 格式正确性
   - 捕获序列化错误
   
2. **类型门禁**：
   - 验证 predicted_direction 等字段类型
   - 强制 string/number 类型
   
3. **中英门禁**：
   - mechanism/symbol_fit 字段强制英文
   - 或提供中文→英文翻译层
   
4. **重复门禁**：
   - 写盘前检查 variant_id 是否已存在
   - 禁止落盘重复

**预期效果**：
- 降低 prescreen error 率（当前 25.3%）
- 提升 Laya **输入**质量（非判断模型本身）

**实施难度**：中  
**风险**：低

---

## 6. 禁止事项（红线）

以下行为**严格禁止**，违反视为不合格：

| 禁止行为 | 说明 | 违反示例 |
|----------|------|----------|
| ❌ **训练/微调 Laya** | Laya 是判断模型，不可学习 | "让 Laya 学习慢环反馈" |
| ❌ **更新 Laya 权重** | 任何反传/自进化 | "用 gate_pass 更新 Laya" |
| ❌ **重做队列去重** | harvest 已实现 | "实施队列去重" |
| ❌ **混淆口径** | 扇出 vs unique 需声明 | 混用导致自相矛盾 |
| ❌ **混淆层级** | prescreen vs 慢环需分离 | "L1 34% 通过率" |
| ❌ **过早砍探索** | 未诊断前暂停 symbol/family | "暂停 eg/lh" |

---

## 7. 可复现性要求

### 7.1 分析脚本

所有指标计算必须提供可复现脚本：

```python
# 示例：计算唯一 variant 覆盖率（v3 修正：使用正确的 join 键）
import json
from pathlib import Path

# 1. 统计唯一 variant (stem)
variant_ids = set()
for pf in Path('task_FM/experiments').glob('run_*/results/**/proposals/*.json'):
    if not pf.name.endswith('.prescreen.json'):
        vid = pf.stem  # stem 作为 variant_id
        variant_ids.add(vid)
unique_variants = len(variant_ids)

# 2. 统计已验证 unique variant (ok verdict)
verdict_variants = set()
with open('task_FM/config/aligned_verdicts.jsonl') as f:
    for line in f:
        if line.strip():
            v = json.loads(line)
            if v.get('status') == 'ok':
                # verdict variant_id 格式：{symbol}_{cov_override}
                # 与 stem 基本一致，可能含 fingerprint 后缀
                vid = v['variant_id']
                # 去除可能的 fingerprint 后缀（如 _aligned_p6）
                base_vid = vid.split('_aligned_')[0] if '_aligned_' in vid else vid
                verdict_variants.add(base_vid)
verified_unique = len(verdict_variants)

# 3. 计算覆盖率
coverage = verified_unique / unique_variants
print(f"唯一 variant 覆盖率: {coverage:.1%}")
print(f"唯一 variant 数: {unique_variants}")
print(f"已验证 unique variant: {verified_unique}")
```

**关键修正**（v2 → v3）：
- ✅ 明确使用 stem 作为 variant_id（796 unique）
- ✅ verdict variant_id 可能含 fingerprint，需预处理
- ✅ 明确 join 规则：verdict.variant_id == proposal.stem

### 7.2 指标定义文档

所有指标必须在文档中明确定义：
- 计算公式
- 数据来源
- 口径说明（unique vs 扇出）
- 现网值

### 7.3 数据快照

分析时应记录数据快照时间戳，便于复现：
```
数据快照时间: 2026-10-19 20:45 CST
提案文件数: 7389
唯一 variant: 796
verdict 总数: 532
ok verdict: 490
```

---

## 8. 补充说明（v3 新增）

### 8.1 skip_suggested 与 backfill 入队

**现网行为**：
- `skip_suggested=True` **不阻断** backfill 入队
- backfill 仅检查 `status=success`，不看 `skip_suggested`
- 因此 proceed 率（88.7%）≠ 实际入队率

**如需使用 proceed 作门禁**：
- 需修改 backfill 逻辑，增加 `skip_suggested` 检查
- 属于独立变更，不在本 SPEC 范围

### 8.2 done.jsonl 重复 variant

**现网现象**：
- `aligned_pending.done.jsonl` 存在重复 variant（重跑导致）
- 与 `aligned_pending.jsonl`（unique）不同

**统计时注意**：
- pending/inprogress: unique（无重复）
- done: 可能含重复（需去重统计）
- verdicts: 按 variant_id 去重后使用

### 8.3 参考文档审核状态

引用先验文档时，需标注其审核状态：

| 文档 | 审核状态 | 说明 |
|------|---------|------|
| `proposals-comprehensive-evaluation.md` | 有条件通过 | 可作为盘点底稿，但需修订事实表 |
| `prescreen-slowloop-effectiveness-evaluation.md` | **不通过** | 含"Laya 学习"违规建议，**禁止引用其优化建议** |
| `laya-503-error-analysis.md` | 通过 | 可用于错误分析参考 |

**禁止**：引用 effectiveness 报告中的"Laya 学习机制"等违规建议。

### 8.4 磁盘归档安全细则

清理磁盘冗余（归档重复文件）属不可逆运维，实施 plan 须补：

1. **备份**：归档前完整备份原文件
2. **干跑**：先模拟归档，检查影响范围
3. **回滚**：准备回滚脚本，可快速恢复
4. **分阶段**：先归档旧 run，验证无问题后再归档新 run

**本 SPEC 仅定义方向**，具体实施细节在 phase plan 中补充。

---

## 9. 与现有系统兼容性

### 8.1 与 harvest 兼容

- ✅ 沿用 harvest 的 `_reject("dedup")` 队列去重
- ✅ 写盘前 variant 登记是**额外防线**
- ✅ 不修改 harvest 核心逻辑

### 8.2 与队列兼容

- ✅ 队列 pending 已 unique（397 个）
- ✅ 优先级策略可调整（唯一/未判定/高不确定）
- ✅ 不重做队列去重

### 8.3 与慢环兼容

- ✅ 慢环单进程运行中（PID 548）
- ✅ 可调整验证优先级
- ⚠️ 并行慢环需评估 GPU 争用（P2）

### 8.4 与 prescreen 兼容

- ✅ prescreen 已实现（success 71.2%）
- ✅ 可添加短窗回测作为额外过滤
- ✅ 不修改 Laya 判断逻辑

---

## 10. 实施路线图

### Phase 1（第 1-2 周）：P0 基础优化

- [ ] 实施写盘前全局 variant 登记
- [ ] 清理现有磁盘冗余（归档重复文件）
- [ ] 诊断 eg（0%，n=37）/ stddev（6.7%）/ ccl（11.1%）根因；小样本 0%（ma/fu/px/jm）仅作观察

**里程碑**：
- 冗余率降至 <50%
- 低效 symbol/family 根因报告

### Phase 2（第 3-4 周）：P1 质量提升

- [ ] 实施生成策略外环（规则/多臂）
- [ ] 部署廉价实证预筛（短窗回测）
- [ ] 上游提案卫生（JSON/类型/中英门禁）

**里程碑**：
- gate pass 率提升至 40%+
- 高质量率提升至 35%+

### Phase 3（第 2-3 月）：P2 智能化

- [ ] 建立独立质量预测器（非 Laya）
- [ ] 引入多样性指标
- [ ] 持续监控与优化

**里程碑**：
- 实现 generation 间质量提升（每代 +5%）
- 唯一 variant 覆盖率 >80%

---

## 11. 监控指标

### 10.1 核心指标（每日跟踪）

| 指标 | 目标 | 当前值 | 趋势 |
|------|------|--------|------|
| 冗余率 | <10% | 89.2% | ↓ |
| 唯一 variant 覆盖率 | >80% | ~60% | ↑ |
| Gate pass 率 | >50% | 33.3% | ↑ |
| 高质量率（S/A） | >40% | 32.4% | ↑ |
| Prescreen success 率 | >80% | 71.2% | ↑ |

### 10.2 过程指标（每周跟踪）

| 指标 | 目标 | 当前值 | 趋势 |
|------|------|--------|------|
| 日均唯一 variant 产出 | >50 | ~30 | ↑ |
| Generation 质量提升 | +5%/代 | 0% | ↑ |
| 验证吞吐量 | >100/日 | ~50/日 | ↑ |

### 10.3 红线指标（实时监控）

| 指标 | 红线 | 动作 |
|------|------|------|
| Laya 权重更新 | 任何更新 | **立即停止** |
| 队列重复 variant | >0 | 检查 harvest 逻辑 |
| 扇出口径混用 | 发现即修正 | 重新计算指标 |

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 写盘前登记增加延迟 | 生成速度下降 | 异步登记 / 批量检查 |
| 多臂老虎机过拟合 | 探索不足 | 保留 10-20% 探索预算 |
| 短窗回测与长窗不一致 | 误筛优质提案 | 定期校准短窗阈值 |
| 并行慢环 GPU 争用 | 性能下降 | 评估硬件资源 / 分时调度 |
| 质量预测器过拟合 | 优先级偏差 | 定期 retrain / 主动学习 |

---

## 13. 附录

### 12.1 术语表

| 术语 | 定义 |
|------|------|
| **variant_id** | 提案唯一标识（symbol + cov_override） |
| **unique variant** | 不同 variant_id 的数量 |
| **扇出计数** | 提案文件 join verdict，高重复 variant 被多次计数 |
| **gate_pass** | 慢环验证通过（dir_acc > 0.52 且统计显著） |
| **tier S/A** | 高质量裁决（综合评分 top 30%） |
| **prescreen success** | Laya 判断成功（非 error/degraded） |
| **Laya** | System-1 判断模型（**不可学习**） |

### 12.2 参考文档

- 提案评估报告：`reports/2026-10-19-proposals-comprehensive-evaluation.md`
- 审核报告：`reports/2026-10-19-proposals-comprehensive-evaluation-audit.md`
- Prescreen 有效性评估：`reports/2026-10-19-prescreen-slowloop-effectiveness-evaluation.md`
- 503 错误分析：`reports/2026-10-19-laya-503-error-analysis.md`

### 12.3 数据源

- 提案文件：`task_FM/experiments/run_*/results/**/proposals/*.json`
- Prescreen 结果：`task_FM/experiments/run_*/results/**/proposals/*.prescreen.json`
- 慢环裁决：`task_FM/config/aligned_verdicts.jsonl`
- 队列状态：`data/cache/aligned_pending*.jsonl`

---

**文档版本**: 2.0  
**最后更新**: 2026-10-19 21:00 CST  
**作者**: AI Assistant  
**审核状态**: 待审核  
**下一步**: 根据审核反馈修订 → 实施 Phase 1
