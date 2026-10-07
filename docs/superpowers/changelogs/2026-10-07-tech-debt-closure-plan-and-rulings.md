# 技术债收口：盘点核实 + 收口计划 + 宿主六项裁定

> **日期**: 2026-10-07
> **分支**: feat/tech-debt-closure-2026-10-07（worktree /home/abug/timesfm-wt-techdebt）
> **输入**: reports/2026-10-07-tech-debt-inventory.md（23 条，另一会话 07:30 生成）

## 做了什么

1. **23 条全量核实**（代码对照 master@5e7237a + live registry 393 行实跑验证）：
   - **6 条勘误**（清单说法已过时）：L1 `_dead_families` 已修复（live 实跑返回空集）、L5 已有 9 用例测试、M2 Locked window 已接线（:1350）、D3/D8 已归档、D9 已挂账
   - **4 项新发现**：N1 dead families 生产空转（`fam_ok={}`，与 pevs P2.6 生产活性风险同根因）、N2 aligned_max_points 默认值漂移、N3 数据资产清单扩大（decisions/基线/cache 均 gitignored 无保护）、N4 git 层备份不覆盖数据资产
2. **收口计划** `plans/2026-10-07-tech-debt-closure-plan.md`：批次 0-4 + Q1-Q6 裁定点 + 验收总表
3. **宿主六项裁定**（同日全落定，回写计划 §8）

## 裁定记录

| Q | 裁定 | 计划影响 |
|---|---|---|
| Q1 n_eff | 两步走：先溯源（默认假设非 bug）；确证 bug 才修且走 v4 指纹流程；移除作废（tier 依赖） | §4 M5 拆为溯源+处置两步，溯源即日启动 |
| Q2 第二异地 | **要，且为默认层（宿主设计）**：每次同步默认含 rclone | §2.2 第三层从可选转默认；daily 保留 180 天；待端点+密钥 |
| Q3 品种集 | **研究 24 个品种而非 9 个** | §3 L3 单源化 goal.yaml、删硬编码、缺键 fail loud |
| Q4 M1 通道 | **方案 A**：读时聚合既有 jsonl | §4 M1 定案，零新状态存储；spec D1 补注记 |
| Q5 串行 | **确认串行，pevs 先行** | 批次 2/3/D5 排 pevs 合入后；批次 0/1 并行不受限 |
| Q6 dm_status 口径 | **独立子项目**：先彻底根因调研（分布/机制/根因/影响四层），再讨论修复 | 新增计划 §6 子项目章程；N1 并入；调研结论反哺 pevs P2.7 |

## 解锁与启动

- **批次 0/1（P0 资产保护）**：设计全部落定；批次 0 执行时点待宿主确认；对象存储待 S3 端点+密钥
- **Q6 调研子项目**：即日启动（只读零冲突）——交付 `reports/2026-10-07-dm-status-liveness-root-cause.md`（证据+机制+根因占比+修复选项清单，只列不决策）
- **Q1 溯源**：即日启动（只读）——追 n_eff 计算路径，三假设择一落定
- **批次 2/3**：待 pevs P2.7-P3 合入部署后基于新 master 开工

## 提交

- `767ad43` docs: 技术债收口方案与实施计划——23 条全核实（6 条勘误）+ 批次 0-4 + 裁定点 Q1-Q6
- 本次提交：裁定回写（§8 裁定表 + §6 Q6 子项目章程 + Q2/Q3/Q4/Q5 相关章节同步）+ 本 changelog


## 后续：Q6 调研 + Q1 溯源完成（2026-10-07 晚）

- 交付 `reports/2026-10-07-dm-status-liveness-root-cause.md`：根因 = spec §7.8 开放问题 #8 未裁定（missingness_admissible 恒 False，可确认分支结构不可达，396 行历史零可确认）；生产"mismatch"实证为基线快照 vs 滚动窗的良性边缘漂移（47.6% 行零不匹配，jd_ccl 案例首尾落点实证）；修复选项 A-E 只列不决策，待宿主裁定
- Q1 溯源结案：n_eff = fallback_n_eff 解析式 Bartlett 修正（n=588 → 恒 73，monthly_backtest.py:660 唯一生产路径），设计使然非 bug，**M5 关闭零改动**；measured_n_eff / effective_sample_size 为死代码（登记 D 类清理候选）
- 计划文档同步：§4 M5 溯源完成标记 / §6 交付物已交付标记 / §8 Q1 行补结论
