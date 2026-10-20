# Phase 1 执行计划：写盘前 variant 登记 + 低效诊断

**基于**: SPEC v3.1 (`specs/2026-10-19-proposals-evaluation-optimization-spec.md`)
**审核状态**: 三审通过（2026-10-19 22:40 CST）
**创建时间**: 2026-10-20
**状态**: 待执行

---

## Phase 1 目标（第 1-2 周）

1. **写盘前全局 variant 登记**：将磁盘冗余率从 89.2% 降至 <10%
2. **清理磁盘冗余**：归档重复提案文件
3. **诊断低效 symbol/family**：识别 eg/stddev/ccl 等低通过率根因

---

## Task 1：写盘前全局 variant 登记

**目标**：在 peer 生成提案后、写盘前检查 variant_id 是否已存在，禁止落盘重复

**涉及文件**：
- `cascade/peer/*.py`（peer 生成逻辑）
- `cascade/sup_harvest.py`（harvest 逻辑，作为第二道防线）
- `data/cache/variant_registry.jsonl`（新增，全局 registry）

**实现要点**：
1. 创建 `data/cache/variant_registry.jsonl` 维护所有已生成 variant_id (stem)
2. peer 生成提案后、写盘前查询 registry
3. 若 stem 已存在，跳过写盘或生成新 variant_id
4. harvest 保留 `_reject("dedup")` 队列去重作为第二道防线
5. 不修改 harvest 核心逻辑

**预期效果**：
- 减少 80%+ 磁盘冗余
- 降低 prescreen 扫描成本
- 不影响队列/慢环（已去重）

**验收标准**：
- [ ] variant_registry.jsonl 正确记录所有已生成 stem
- [ ] peer 写盘前检查逻辑生效（重复 stem 不落盘）
- [ ] 新增测试覆盖检查逻辑
- [ ] 现有 harvest 去重逻辑不受影响

---

## Task 2：清理磁盘冗余（归档重复文件）

**目标**：归档重复提案文件，保留每个 variant 的最新版本

**涉及文件**：
- `task_FM/experiments/run_*/results/**/proposals/*.json`
- `task_FM/experiments/archive/`（新增归档目录）

**实现要点**：
1. 扫描所有提案文件，按 stem 分组
2. 对每个 stem，保留最新版本（按 mtime），归档其余
3. 归档前备份原文件
4. 干跑模拟，检查影响范围
5. 准备回滚脚本

**预期效果**：
- 磁盘冗余率从 89.2% 降至 <10%
- 释放磁盘空间
- 保留完整历史（可回滚）

**验收标准**：
- [ ] 归档脚本正确识别重复文件
- [ ] 保留每个 variant 的最新版本
- [ ] 归档目录结构清晰（按 run_id 组织）
- [ ] 回滚脚本可快速恢复
- [ ] 干跑报告影响范围

---

## Task 3：诊断低效 symbol/family 根因

**目标**：识别 eg（0%）/ stddev（6.7%）/ ccl（11.1%）等低通过率 symbol/family 的根因

**诊断维度**：
1. **数据质量**：基础数据完整性、对齐、时间戳
2. **门控分析**：dir_acc 分布、gate_pass 判定逻辑
3. **协变量族有效性**：family 协变量预测能力
4. **样本期问题**：验证样本期是否有极端行情
5. **样本量问题**：小样本（<10）的 0% 是否统计显著

**涉及 symbol/family**：
- **eg**：0% gate pass 率（n=37）→ 需诊断
- **stddev**：6.7% gate pass 率（n=15）→ 需诊断
- **ccl**：11.1% gate pass 率（n=27）→ 需提升
- **小样本观察**：ma/fu/px/jm（n<10）仅作观察

**预期交付**：
- 诊断报告（含数据快照时间戳）
- 根因分析（数据/门控/协变量/样本期/样本量）
- 优化建议（不违反 Laya 不可学习约束）

**验收标准**：
- [ ] 诊断报告包含数据快照时间戳
- [ ] 每个低效 symbol/family 有明确根因
- [ ] 优化建议不违反 Laya 不可学习约束
- [ ] 小样本（n<10）不作为"低效"结论依据

---

## 实施顺序

1. **Task 1**（1-2 天）：写盘前 variant 登记
   - 创建 variant_registry.jsonl
   - 实现 peer 写盘前检查
   - 新增测试
   - Code review

2. **Task 2**（1-2 天）：磁盘冗余归档
   - 编写归档脚本
   - 干跑模拟
   - 执行归档（分阶段）
   - 验证回滚脚本
   - Code review

3. **Task 3**（2-3 天）：低效诊断
   - 数据质量检查
   - 门控分析
   - 协变量族有效性
   - 样本期/样本量分析
   - 撰写诊断报告
   - Code review

---

## 禁止事项（红线）

- ❌ 训练/微调 Laya
- ❌ 更新 Laya 权重
- ❌ 重做队列去重（harvest 已实现）
- ❌ 混淆口径（扇出 vs unique）
- ❌ 混淆层级（prescreen vs 慢环）
- ❌ 过早砍探索（未诊断前暂停 symbol/family）

---

## 里程碑

- [ ] Task 1 完成：variant 登记生效，重复 stem 不落盘
- [ ] Task 2 完成：磁盘冗余率 <50%（第一阶段）
- [ ] Task 3 完成：低效 symbol/family 诊断报告
- [ ] 所有 Task code review PASS
- [ ] Changelog 记录

---

**下一步**：开始 Task 1 实施
