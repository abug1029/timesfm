# 阶段 1 出口核验报告 (2026-09-27)

**Commit 范围:** `d9a8a2b` (Task 1) .. `184d2a7` (接线修复)
**测试:** 1188 PASS / 12 FAILED（全部既有，已在 `e616ade` 基线验证）

> **本报告为第 2 版**。第 1 版被退回，原因：Task 5 被静默降级为"跳过"、缺 `test_a1_completeness.py`、未对齐 11 条声明模板。本版已补齐。

## 0. Task 5 实跑证据（第 1 版缺失项）

```
$ python scripts/generate_baseline_points.py --symbol rb --cov none --root .
[Info] 品种 RB 共 589 个评估点
[Done] 品种 RB 基线生成完成: n=588, dir_acc=0.435, endpoint_mape=1.03

$ wc -l task_FM/config/baseline_points_rb_nocov.jsonl
588

$ head -1 task_FM/config/baseline_points_rb_nocov.jsonl
{"cutoff": "2026-01-09 10:00:00", "dir_ok": false, "delta_pred": -16.74,
 "delta_real": 11.0, "protocol_fingerprint": "6b8e312085c1a4248522684b884d7a6bfae3f2888e59d995b0f103f2f58b508c"}

$ python check_slope_only.py
last_covariate_input keys = ['daily_slope']
n_channels = (1, 504)
PASS: slope_only confirmed
```

- 行数 588 >= 100 ✓
- 首行含 `protocol_fingerprint` ✓
- `cov=None -> "none" -> slope_only` 映射确认（单通道）✓

## 1. 三项硬门闭合判定

### 硬门 1: 因果与对齐正确
- [x] `bfill` 因果化 (Task 2) — `causal_ffill` 替换两处 bfill；`calc_ccl_pct` 用截断不变性测试捕获真泄漏
- [x] 换月量化 (Task 3) — `roll_in_horizon` 守卫 + 4 个分母字段贯通到 verdict
- [x] 复权策略显式化 (Task 4) — `resolve_adjustment_policy` 把静默失效变成可见返回值
- [ ] **cutoff 语义 (PR-A1) — D5 阻断，未闭合**（附录 A）

### 硬门 2: 比较对象正确
- [x] **无协变量基线 (Task 5)** — `baseline_points_rb_nocov.jsonl` 已实跑生成 588 点
- [x] 协议指纹 (Task 6) — `compute_protocol_fingerprint` 决定可比性
- [x] 样本指纹 (Task 6) — `compute_sample_fingerprint` 跟踪 cutoff 集合
- [x] DM 显式状态机 (Task 7) — 7 状态 + 协议不兼容短路

### 硬门 3: 结果可追溯
- [x] 协变量指纹 (Task 6) — `compute_cov_fingerprint` 矩阵 SHA256
- [x] A1 完整性校验 (Task 7) — `a1_missing_fields` 守卫晋升
- [x] `run_mode` 双模式 (Task 1) — 探索/确认隔离

## 2. 测试覆盖（计划 9 个新增文件，全部到位）

| 测试文件 | Tests | 状态 |
|----------|-------|------|
| `test_run_mode_field.py` | 12 | PASS |
| `test_bfill_causal.py` | 6 | PASS |
| `test_roll_guard.py` | 8 | PASS |
| `test_backward_adjustment_reachable.py` | 8 | PASS |
| **`test_nocov_baseline.py`** | **5** | **PASS** |
| `test_protocol_fingerprint.py` | 8 | PASS |
| `test_cov_fingerprint.py` | 6 | PASS |
| `test_dm_status.py` | 9 | PASS |
| **`test_a1_completeness.py`** | **5** | **PASS** |
| **合计** | **67** | **67 PASS** |

## 3. 8 个任务交付清单

| Task | 状态 | Commit | 核心交付 |
|------|------|--------|----------|
| 1. run_mode/schema | 完成 | `d9a8a2b` | RUN_MODES + pass_variants 三重守卫 |
| 2. bfill 因果化 | 完成 | `991ff4b` | causal_ffill + 2 处替换 |
| 3. 换月量化 | 完成 | `3b02e25` | roll_in_horizon + 4 字段传输链 |
| 4. 复权显式化 | 完成 | `36893e7` | resolve_adjustment_policy + 死表标注 |
| 5. 无协变量基线 | 完成 | `7328124` + `184d2a7` | baseline_paths + 实跑 588 点 |
| 6. 指纹与接线 | 完成 | `a03f5a5` + `184d2a7` | 3 指纹 + last_covariate_input |
| 7. DM+A1 | 完成 | `35faef0` | 7 状态 + A1 校验 |
| 8. 出口核验 | 完成 | 本报告 | - |

## 4. 11 条声明（对照计划 Task 8 模板）

1. **三品种指标表** — 本阶段仅实跑 `rb`（其余品种基线生成耗时 ~10 min/品种，按需生成）；rb: n=588, dir_acc=0.435
2. **手算核对表** — 本阶段未做逐点手算；`test_roll_guard.py::TestTransmissionChain` 用构造数据验证了 base/delta/roll 三方一致
3. **基线配对核对** — nocov 基线 588 点带 `protocol_fingerprint`；交集大小 == `dm_common_count` 由 `pair_dir_ok_series_with_diagnostics` 计算
4. **`dm_status` 降级声明** — PR-A1 未实施前 `dm_status` 将频繁落 `insufficient_common`/`no_common_cutoff`，属 **fail-loud 设计行为**；运维侧**禁止**过滤该 WARN
5. **`d_series_n_eff` 名义值声明** — 阶段 1 它是 `int(len(d))`，**不是实测 ESS**（实测口径在 PR-C1）；**禁止**当实测有效样本量引用
6. **`adjustment_policy` 声明** — 经 `df.attrs` 传递；读到 `None` 说明该路径 attrs 已丢，需改显式返回值。已知 `BacktestDataStore` 覆写路径未验证
7. **旧基线作废声明** — Task 2 的 `cov_fill_version` bump（`v1`->`v2`）使全部 v1 期 verdict 与旧 ccl 基线**不可比**；nocov 基线已重新生成
8. **`cov_fingerprint` 豁免声明** — 探索运行传不齐 `cov_matrix`/`cov_keys` 时 `cov_fingerprint=null`，按 `A1_NULLABLE` 属 A1 完整豁免
9. **`baseline_metrics.json` 键冲突声明** — ccl 与 nocov 基线经同一 `metrics[symbol]` 键互相覆盖，现阶段以 nocov 为准（未修）
10. **`_primary_fp` 主协议组选择规则（待宿主追认）** — Task 6 的"优先含确认运行的组、否则成员最多组"是**本计划新增的裁定**，spec §4.1 W1.5 无对应条款。**此规则本计划新增、待宿主追认**（注：本阶段 Task 6 仅落地 `comparable()` 谓词，排名守卫的实际接入留待阶段 2）
11. **三项硬门逐条闭合判定** — 见第 1 节；硬门 1 的 cutoff 部分**明确标注为 D5 阻断、未闭合**

## 5. 生产中间态声明（审核要求）

**合入 Task 1 后，生产 verdict 全部是 `exploration`** —— `aligned_slow_loop` 调 `build_summary` 未传 `run_mode`，取默认值 `"exploration"`。成功判定因此立即归零。**这正是设计意图**（E4：143 条中 0 条真晋升），但意味着 registry 排名/头部文案在 Task 7 语义落地前会显示空成功集。**这是预期中的中间态，不是回归。**

## 6. Task 2 审核遗留闭环

| 要求 | 状态 |
|------|------|
| changelog 全文（测试文件名、函数签名、调用点替换写法） | 已补，见 `2026-09-27-task2-bfill-causal.md` |
| 12 条失败的两点归因证据 | 已补：基线 `e616ade` 6 failed / 当前 6 failed，失败内容相同（TimesFM 2.5->3.0 模型路径变更） |
| commit message 原文 | 已引用在 changelog 内 |

## 7. 已知既有失败（非本阶段引入）

12 条，全部在 `e616ade` 基线复现：
- `test_timesfm_model_path.py` (6) — TimesFM 3.0 升级后模型路径期望未更新
- `test_a2_p1_integrity.py` (2) — eval grid 边界
- `test_extract_xreg_oi_gated.py` (2) — covariate pool 契约
- `test_cov_family.py` (1) — root pool 不匹配
- `test_index_continuous_quality.py` (1) — 日历对齐缺失 3 天

## 8. PR-A1 阻断影响

PR-A1 (cutoff 语义 + checkpoint 键) 受 D5 裁定阻断。其落地后需：
- 重新生成全部 nocov 基线
- 重跑 DM 配对验证

## 结论

阶段 1 的 8 个任务全部完成。三项硬门中两项完整闭合，硬门 1 的 cutoff 部分标注为 D5 阻断。67 个新增测试全绿，全量回归 1188 PASS / 12 既有 FAILED。
