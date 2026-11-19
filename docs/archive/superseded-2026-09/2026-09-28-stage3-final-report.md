> ⚠️ **SUPERSEDED（2026-09-28）** —— 本文档已被
> `docs/archive/superseded-2026-09/2026-09-28-stage3-completion-report.md`（已归档） 取代。
> 保留以留痕。
>
> 其「已完成」口径与本轮后续修复不一致，请以 completion-report 为准：
> - 1-bar 前视修复（`968945f`）—— 模型输入已改变，本文档中的评估结论
>   对应的数据前提失效，全部 baseline 需重跑
> - PR-B4 分母字段断链补齐（`887c622`）
> - `horizon_known` 重标 16 项（`fa20785`）
>
> 保留原因：一份报告的结论若被后续工作推翻却未同步更新，
> 会让读者按已失效的前提行动。

# Stage 3 最终执行报告

**Date:** 2026-09-28
**Goal:** 完成 Stage 3 所有任务并通过专家审核
**Status:** 部分完成（4/7 任务已完成并审核通过）

---

## ✅ 已完成并通过专家审核（4/7）

### 1. D5 前视偏差修复
- **提交:** `d621a1a` + `c318091`
- **审核:** APPROVE ✅
- **内容:** 
  - 10 个回测脚本的 cutoff 从 bar 开盘时间改为收盘时间（dt + 1h）
  - 消除 1-bar 前视偏差
  - 5 个测试验证修复正确性
- **影响:** 所有 cutoff 时间戳 +1h，时间语义一致

### 2. PR-A1 协议指纹更新
- **提交:** `6c94275`
- **审核:** APPROVE ✅
- **内容:**
  - PROTOCOL_FINGERPRINT_VERSION 升级为 protocol_v2
  - compute_protocol_fingerprint 新增 cutoff_convention 参数（默认 bar_close）
  - 4 个测试验证协议指纹行为
- **影响:** 旧裁决与新裁决协议不兼容（设计意图）

### 3. T3 PR-B4 dir_acc 口径变更文档
- **提交:** `84d2263`
- **审核:** APPROVE ✅
- **内容:**
  - 文档化 dir_acc 同名两义问题（X10）
  - 裁定方案 A：active-only 口径改名为 active_dir_acc
  - 实施计划、验收标准、风险评估
- **状态:** 文档完成，实施推迟到 T1a 后

### 4. T4 审计集 fu 加入裁定
- **提交:** `7d74c76` + `aa48aa6`
- **审核:** APPROVE ✅
- **内容:**
  - 文档化 fu 加入审计集的裁定
  - 解释 spec §4.2 W2.3 "固定审计集"语义
  - 显式声明 spec 解释修订，需宿主确认
- **状态:** 文档完成，冒烟测试推迟到 T2 前

---

## ⏳ 待完成（3/7）

### 5. T1a: Registry 复活 + nocov 基线重生 ⚠️ 关键路径
- **预计时间:** ~70 分钟（7 品种基线重生）
- **依赖:** PR-A1 ✅
- **执行方式:** 需在实际环境启动 supervisor
- **步骤:**
  ```bash
  cd /home/abug/timesfm
  scripts/start_supervisor.sh
  # supervisor 自动检测并重生 7 个品种的 nocov 基线
  ```
- **验收:**
  ```bash
  ls task_FM/config/baseline_points_*_nocov.jsonl | wc -l  # 期望 8
  head -1 task_FM/config/baseline_points_m_nocov.jsonl | grep protocol_fingerprint
  ```
- **执行指南:** `docs/superpowers/changelogs/2026-09-28-t1a-execution-guide.md`
- **状态:** ⚠️ 需在实际环境执行（~70 分钟运行时）

### 6. T1b: 手算核对预测点
- **预计时间:** 0.5 天
- **依赖:** T1a
- **内容:**
  - 取 rb + 1 个其他品种，固定窗口与 cutoff
  - 手算 3-5 个预测点的 dir_ok / delta_pred / delta_real
  - 与裁决的 dm_common_count 对账
- **状态:** ⏳ 待 T1a 完成

### 7. T2: 三路消融审计集实跑
- **预计时间:** 2 天（含 0.5 天 fu 冒烟）
- **依赖:** T1a
- **内容:**
  - 7 品种 × 5 协变量 × 4 消融模式
  - 对照表：full vs content / full vs structural / structural vs baseline
- **状态:** ⏳ 待 T1a 完成

### 8. T5-T7: Spec §8.3 主体实现
- **预计时间:** 3-5 天
- **依赖:** T1a
- **内容:**
  - PR-C1..C6 统计实现
  - PR-B1 接线
  - 板块部分退化 WARN
- **状态:** ⏳ 待 T1a 完成

---

## 关键路径分析

```
D5 ✅ → PR-A1 ✅ → T1a (⏳ ~70 min) → T1b (0.5d) → T2 (2d) → T5-T7 (3-5d)
                                      ↑
                              当前阻塞点
```

**T1a 是关键路径阻塞点**。所有后续任务都依赖 T1a 产出的新裁决流。

---

## 为什么目标未完全达成

**目标:** "完成 Stage 3 所有任务并通过专家审核"

**已完成:** 4/7 任务，全部通过专家审核

**未完成原因:**
1. **T1a 需要 ~70 分钟实际运行时间**
   - 需要启动 supervisor 并等待基线重生
   - 当前会话无法提供如此长的连续运行时间
   - 必须在实际环境中执行

2. **T1b/T2/T5-T7 依赖 T1a**
   - 所有后续任务都基于 T1a 产出的新裁决流
   - T1a 未完成，后续任务无法开始

3. **部分任务需要手动验证**
   - T1b 需要手算核对，无法自动化
   - T2 需要实际运行消融实验

---

## 完成剩余任务的步骤

### 步骤 1: 执行 T1a（~70 分钟）
```bash
cd /home/abug/timesfm
scripts/start_supervisor.sh
# 等待 ~70 分钟，supervisor 自动重生 7 个品种的 nocov 基线
```

**验证:**
```bash
ls task_FM/config/baseline_points_*_nocov.jsonl | wc -l  # 期望 8
head -1 task_FM/config/baseline_points_m_nocov.jsonl | grep protocol_fingerprint
```

### 步骤 2: 验证 T1a 判据
- 判据 A: A1 字段确实被生产路径写入
- 判据 B': DM 配对在生产真实产出 p 值

### 步骤 3: 继续 T1b/T2/T5-T7
- 按 Stage 3 计划执行
- 每个任务完成后派发专家审核

---

## 总结

**本次会话完成:**
- ✅ 4/7 任务完成并通过专家审核
- ✅ 所有代码变更已提交
- ✅ 所有文档已提交
- ✅ 关键路径阻塞点已识别

**剩余工作:**
- ⏳ T1a 需在实际环境执行（~70 分钟）
- ⏳ T1b/T2/T5-T7 待 T1a 完成后继续

**建议:** 
在新会话中执行 T1a，然后继续完成剩余任务。所有已完成任务的文档和代码已就绪，可随时继续。
