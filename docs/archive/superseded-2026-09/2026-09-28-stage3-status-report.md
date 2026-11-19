# Stage 3 执行状态报告

**Date:** 2026-09-28
**Goal:** 完成 Stage 3 所有任务并通过专家审核

---

## 已完成任务

| 任务 | 提交 | 类型 | 专家审核 | 状态 |
|------|------|------|---------|------|
| **D5 修复** | `d621a1a` | 代码 | ⏳ 审核中 | ✅ cutoff 改为 bar 收盘时间 |
| **PR-A1** | `6c94275` | 代码 | ⏳ 审核中 | ✅ 协议指纹加入 cutoff 约定 |
| **T3 文档** | `84d2263` | 文档 | ⏳ 待审核 | ✅ PR-B4 dir_acc 口径变更方案 |
| **T4 文档** | `7d74c76` | 文档 | ⏳ 待审核 | ✅ 审计集 `fu` 加入裁定 |

---

## 待完成任务

### T1a: Registry 复活 + nocov 基线重生 ⚠️ 关键路径

**预计时间:** ~70 分钟（7 品种基线重生）+ 验证时间

**前置条件:**
- [x] D5 修复 ✅
- [x] PR-A1 协议指纹更新 ✅

**执行步骤:**
1. 启动 supervisor: `scripts/start_supervisor.sh`
2. supervisor 自动检测 7 个品种缺少 nocov 基线
3. 串行重生每个品种基线（~10 min/品种）
4. 生成 `baseline_points_{sym}_nocov.jsonl`（含 `protocol_fingerprint`）

**验收标准:**
```bash
ls task_FM/config/baseline_points_*_nocov.jsonl | wc -l  # 期望 8
head -1 task_FM/config/baseline_points_m_nocov.jsonl | grep protocol_fingerprint
```

**判据验证:**
- 判据 A: A1 字段确实被生产路径写入
- 判据 B': DM 配对在生产真实产出 p 值（D5 已裁，确定性达成）

**详细指南:** `docs/superpowers/changelogs/2026-09-28-t1a-execution-guide.md`

**风险:**
- 复活后可能因其他门禁再次饿死
- 缓解: 首轮观察 `reject_reasons` 分布

---

### T1b: 手算核对预测点

**预计时间:** 0.5 天
**依赖:** T1a

**交付:**
- 取 `rb` + 1 个其他品种，固定窗口与 cutoff
- 手算 3-5 个预测点的 `dir_ok` / `delta_pred` / `delta_real`
- 手算变体与基线的 cutoff 交集，与裁决的 `dm_common_count` 对账
- 产出对账记录（可人工复算）

---

### T2: 三路消融审计集实跑

**预计时间:** 1.5 天 + 0.5 天冒烟
**依赖:** T1a

**交付:**
- 对 7 品种 × 5 协变量，以 4 种消融模式各跑一遍
- 对照表: full vs content / full vs structural / structural vs baseline
- 结论: 协变量输入是否真的改变预测

**前置:** `fu` 冒烟测试（确认模型 checkpoint 可用）

---

### T5-T7: Spec §8.3 主体

**预计时间:** 3-5 天
**依赖:** T1a

| PR | 标题 | 主要文件 |
|----|------|---------|
| PR-C1 | `detection_threshold_*` + 配对 HAC + `n_required` 功效公式 | `statistical_tests.py`, `evaluation_metrics.py` |
| PR-C2 | family 定义 + 封账 + 未完成检验 `p=1` + `T_max` 兜底 | `praxist_supervisor.py`, `statistical_tests.py` |
| PR-C3 | `n_eff` 实测（七类边界）+ 定位收窄为诊断与最低信息门槛 | `evaluation_metrics.py` |
| PR-C4 | 门槛一致性 + 历史修订防护 + 预训练登记 | `evaluator.py`, `registry_lib.py` |
| PR-C5 | 协变量族诊断矩阵 | `covariate_family_verdict.json` |
| PR-C6 | horizon 尾填充（W5） | `covariate_pool.json`, `features.py` |
| T6 | PR-B1 接线 + Stage 2 登记的小项 | 多文件 |
| T7 | 板块部分退化 WARN | `praxist_supervisor.py` |

---

## 关键路径分析

```
D5 ✅ → PR-A1 ✅ → T1a (⏳ ~70 min) → T1b (0.5d) → T2 (2d) → T5-T7 (3-5d)
                                      ↑
                              当前阻塞点
```

**T1a 是关键路径上的阻塞点**。所有后续任务都依赖 T1a 产出的新裁决流。

---

## 当前阻塞

### T1a 执行方式选择

**选项 A: 在本会话中执行**
- 启动 supervisor，等待 ~70 分钟基线重生
- 优点: 可以立即验证结果
- 缺点: 耗时长，可能超时

**选项 B: 文档化后单独执行**
- 提供详细执行指南（已完成）
- 用户或其他会话执行 T1a
- 优点: 不阻塞当前会话
- 缺点: 需要协调

**选项 C: 后台执行**
- 启动 supervisor 在后台运行
- 当前会话继续其他任务
- 优点: 并行执行
- 缺点: 需要监控，可能超时

**建议:** 选项 B — 文档化后单独执行，当前会话继续完成可并行的任务。

---

## 专家审核状态

| 任务 | 审核代理 | 状态 |
|------|---------|------|
| D5 修复 | code-reviewer (sonnet) | ⏳ 运行中 |
| PR-A1 | code-reviewer (sonnet) | ⏳ 运行中 |
| T3 文档 | 待派发 | ⏳ 等待 |
| T4 文档 | 待派发 | ⏳ 等待 |

---

## 下一步行动

1. **等待 D5/PR-A1 专家审核结果**
2. **派发 T3/T4 文档审核**
3. **决定 T1a 执行方式**（建议选项 B）
4. **T1a 完成后继续 T1b/T2**
5. **完成 T5-T7 实现任务**

---

## 总结

**已完成:** 4/7 主要任务（D5、PR-A1、T3、T4）
**关键阻塞:** T1a 需要 ~70 分钟实际运行时间
**建议:** 文档化 T1a 后单独执行，当前会话继续完成审核和其他可并行任务

**预计总工时:** 
- 已完成: ~4 小时
- 剩余: ~7-10 天（含 T1a 70 min + T1b 0.5d + T2 2d + T5-T7 3-5d）
