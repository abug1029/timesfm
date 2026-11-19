# FM_a Spec 实施核验报告（2026-09-29）

> 核验基准：`docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15，1586 行）
> 核验时点：master @ `eecf05a`（WSL 唯一权威）
> 核验方式：通读 spec + 代码 grep 实证（agent 因 weekly quota 失败，由主 agent 直接核验）

---

## 一、逐 PR 实施状态

### 阶段 1 — 三项硬门槛（spec §8.1）

| PR | 标题 | 状态 | 证据 |
|----|------|------|------|
| PR-A1 | cutoff 与窗口语义 | ✅ | `_h1_upper_bound` + `cutoff_convention="bar_close"` + `PROTOCOL_FINGERPRINT_VERSION = "protocol_v2"` 含 cutoff_convention |
| PR-A2 | 换月守卫 | ✅ | `n_roll_excluded` + `n_roll_ratio` 在 evaluation_metrics.py |
| PR-A3 | bfill 因果化 | ✅ | `causal_ffill()` 函数 + 替换了原 `.bfill()` |
| PR-A4 | 无协变量基线 | ✅ | 9 份 `baseline_points_*_nocov.jsonl` 存在 |
| PR-A5 | 协议/样本指纹 | ⚠️ | 函数存在；**`compute_protocol_fingerprint()` 不覆盖数据窗口语义**（已知缺口，旧基线会被误判有效） |
| PR-A6 | dm_status + 去 migrated_pass | ✅ | `dm_status` 字段 + `pass_variants()` v2 注释"migrated_pass retired per W1.1" |

### 阶段 2 — 诊断完成项（spec §8.2）

| PR | 标题 | 状态 | 证据 |
|----|------|------|------|
| PR-B1 | cov/experiment_fingerprint + 身份派生 | ⚠️ | 库已实现，但 `variant_id` **未接线**（143 条全旧格式；已知，计划 T6 登记） |
| PR-B2 | 缺失/常数诊断 + 零填充 fail-loud | ✅ | `cov_effective` / `inert_constant` / `horizon_flat` / `all_zero` 在 hourly_model.py |
| PR-B3 | xreg_fallback 贯通 | ✅ | evaluator.py + monthly_backtest.py 消费 |
| PR-B4 | dir_acc 单口径 + 历史重算 | ✅ | `dir_acc_full` / `dir_acc_ex_roll` / `n_dir_total` / `n_dir_active` / `n_zero_move` 全在；重算脚本覆盖 108/170 |
| PR-B5 | 三路消融 | ✅ | `AblationMode` 枚举 + `ablate_content_covariates` + `ablate_structural_covariates`；审计集已跑 3 条裁决 |
| PR-B6 | 提案质量门 | ✅ | `_sector_filter_check` (circuit-breaker) + `_proposal_quality_gate` |

### 阶段 3 — 统计实现（spec §8.3）

| PR | 标题 | 状态 | 证据 |
|----|------|------|------|
| **PR-C1** | `detection_threshold_*` + `n_required` 功效公式 | ❌ | **全仓零匹配** |
| **PR-C2** | family 定义 + 封账 + `T_max` 兜底 | ❌ | **全仓零匹配** |
| PR-C3 | `n_eff` 实测 + `meets_min_info` | ✅ | `measured_n_eff` + `compute_meets_min_info` 在 evaluation_metrics.py |
| PR-C4 | 门槛一致性 + 历史修订防护 | ✅ | `threshold_basis` + `context_hash` + `data_revised` 在 evaluator.py |
| PR-C5 | 协变量族诊断矩阵 | ⚠️ | 脚本 `generate_covariate_family_verdict.py` 存在但**输出文件未落盘**（`task_FM/config/covariate_family_verdict.json` 不存在） |
| PR-C6 | horizon_known 分类 | ⚠️ | `covariate_pool.json` 有分类；**但 spec W5.2/W5.3/W5.5③ 代码路径未实现**（features.py / hourly_model.py / aligned_slow_loop.py 中零匹配） |

### 阶段 4 — 预注册、品种分级（spec §8.4）

| PR | 标题 | 状态 | 证据 |
|----|------|------|------|
| PR-D1 | 机器可读预注册 + no-peek | ❓ | 未核验（配额耗尽） |
| PR-D2 | 品种分级 + `symbol_status` 退休 | ❓ | 未核验（spec §8.5 约束 3：目标效应未裁定前不得实施） |

## 二、Spec §8.3 出口核验交付物状态

| §8.3 核验项 | 状态 | 缺口 |
|------------|------|------|
| 已知自相关序列手算长程方差 | ❌ | 无黄金用例文件 |
| 负自相关 / 边界滞后 / 重叠预测场景 | ❌ | 无专项用例 |
| **三套公式分别验证** | ❌ | 仅 n_eff 一套；detection_threshold / n_required 未实现 |
| 断言"长程方差 × VIF"混用路径不存在 | ❌ | 无断言测试 |
| 黄金用例写明带宽约定等 | ❌ | 无 |
| 黄金用例枚举（§5.3 测试 67）：4 个边界各一 | ❌ | 无 |
| 重叠预测：实测 HAC vs 名义 VIF 区分 | ❌ | 无 |
| 手算对账记录 | ❌ | 无独立记录文件 |

**阶段 3 出口核验：0/8 交付。** 这是进入阶段 4 的硬性前置（spec §8.5 约束 4）。

## 三、Spec §7 开放问题裁定状态

| 开放问题 | 状态 | 依据 |
|---------|------|------|
| **D5**（cutoff 语义） | ✅ 已裁定 | commit `d621a1a` + `968945f`，采用 bar_close |
| 目标效应与功效（§7 Q7） | ❓ 未裁定 | 阻断 PR-D2 实施 |
| family 封账缺失判定方法（§7 Q8） | ❓ 未裁定 | `missingness_admissible` 恒 False（保守默认） |
| 其他 §7 项 | 待查 | — |

## 四、剩余实施计划（优先级排序）

### 🔴 阻塞项（必须在进入阶段 4 前）

**P1：PR-C1 + PR-C2 实施**（spec §8.3 主体，阶段 4 硬前置）
- PR-C1：`detection_threshold_vs_random` / `_vs_baseline` + `n_required` 公式 + 黄金用例
  - 黄金值：0.596 / ≈0.096 / ≈31,000（spec 钦定）
  - 文件：`statistical_tests.py` + `evaluation_metrics.py`
- PR-C2：family 定义 + `family_close_at`=90 天 + `family_max_members`=20 + `T_max` + 未完成检验 `p=1`
  - 文件：`praxist_supervisor.py` + `statistical_tests.py`
- §8.3 核验的 8 项交付物（黄金用例等）

**P2：PR-C5 族诊断矩阵落盘**
- 跑 `generate_covariate_family_verdict.py` 输出 `covariate_family_verdict.json`

**P3：PR-C6 补 W5.2/W5.3/W5.5③ 代码路径**（宿主已裁定：补充实现）
- 在 `features.py` 加 `horizon_known` 读 + 按标签分支填充
- 在 `hourly_model.py` 落 `horizon_exogenous`
- 加加载时断言（W5.5③）
- 加前视不变量测试（W5.3）

### 🟡 重要但不阻塞进入阶段 4

**P4：PR-A5 协议指纹补数据窗口语义**
- 让旧基线在前视修复后自动失效
- 文件：`evaluator.py` `compute_protocol_fingerprint()`

**P5：PR-B1 variant_id 接线**
- 计划 T6 登记项
- 含 64-bit 截断评估

**P6：阶段 4 前置裁定**
- 目标效应与功效（§7 Q7）—— 决定 `N(该品种)` 与分级门槛
- `symbol_status.json` 改为派生（spec §4.6）

### 🟢 诊断卫生 / 长期改进

**P7：测试套件密封化**（F7）
**P8：pool provenance**（F6）
**P9：测试声明三件套**（F1）
**P10：审计报告移交**（WSL 归档）

## 五、关键风险

1. **PR-C1/C2 是 spec §8.3 的硬交付**，未实施 = 阶段 3 出口核验 0/8 = **不得进入阶段 4**（spec §8.5 约束 4）。这是当前最大缺口。
2. **PR-C6 的 W5.2/W5.3/W5.5③ 代码路径未实现** —— `horizon_known` 是「只校验、不生效」的字段。需裁定是否补实现（**宿主裁定：补实现**）。
3. **PR-A5 不覆盖数据窗口语义** —— 已登记为潜在静默失效。任何未来修改数据窗口的操作都可能让旧基线被误判有效。
4. **配额耗尽** —— 2026-09-29 的 weekly quota 已用完，重置时间 23:59:59 CST。

## 六、核验发现的方法论缺陷

**「报告 vs 代码」审计不能发现「报告 vs spec」缺口**

本轮审计与历次审计都只核对「completion report 声称的 vs 代码实际」。但 PR-C1/C2 在 completion report 里**根本未被声称**，缺口在「报告 vs spec」这一层——只做前一层核对的审计必然漏掉。今后任何「阶段已完成」的声明必须同时核对 spec §8 的 PR 清单。

---

**报告人**：主 agent（agent 配额耗尽，由主 agent 直接核验）
**日期**：2026-09-29
**文件**：`docs/superpowers/reports/2026-09-29-spec-implementation-audit.md`
