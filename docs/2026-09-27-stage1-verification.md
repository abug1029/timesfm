# 阶段 1 出口核验报告 (2026-09-27)

**Commit 范围:** `d9a8a2b` (Task 1) .. `35faef0` (Task 7)
**测试:** 74/74 PASS (8 个新测试文件)

## 1. 三项硬门闭合判定

### 硬门 1: 因果与对齐正确
- [x] `bfill` 因果化 (Task 2) — `causal_ffill` 替换两处 bfill
- [x] 换月量化 (Task 3) — `roll_in_horizon` 守卫 + 4 个分母字段贯通
- [x] 复权策略显式化 (Task 4) — `resolve_adjustment_policy` 可见
- [ ] **cutoff 语义 (PR-A1) — D5 阻断，未闭合** (spec 已知)

### 硬门 2: 比较对象正确
- [x] 协议指纹 (Task 6) — `compute_protocol_fingerprint` 决定可比性
- [x] 样本指纹 (Task 6) — `compute_sample_fingerprint` 跟踪 cutoff 集合
- [x] DM 显式状态机 (Task 7) — 7 状态 + 协议不兼容短路

### 硬门 3: 结果可追溯
- [x] 协变量指纹 (Task 6) — `compute_cov_fingerprint` 矩阵 SHA256
- [x] A1 完整性校验 (Task 7) — `a1_missing_fields` 守卫晋升
- [x] `run_mode` 双模式 (Task 1) — 探索/确认隔离

## 2. 测试覆盖

| 测试文件 | 行数 | 状态 |
|----------|------|------|
| `test_run_mode_field.py` | 12 tests | PASS |
| `test_bfill_causal.py` | 6 tests | PASS |
| `test_roll_guard.py` | 8 tests | PASS |
| `test_backward_adjustment_reachable.py` | 8 tests | PASS |
| `test_protocol_fingerprint.py` | 8 tests | PASS |
| `test_cov_fingerprint.py` | 6 tests | PASS |
| `test_dm_status.py` | 9 tests | PASS |
| `test_verdict_registry.py` | 12 tests | PASS |
| `test_prediction_quality_e2e.py` | 5 tests | PASS |
| **总计** | **74 tests** | **74 PASS** |

## 3. 8 个任务交付清单

| Task | 状态 | 核心交付 |
|------|------|----------|
| 1. run_mode/schema | 完成 | RUN_MODES 常量 + pass_variants 三重守卫 |
| 2. bfill 因果化 | 完成 | causal_ffill + 2 处替换 |
| 3. 换月量化 | 完成 | roll_in_horizon + 4 字段传输链 |
| 4. 复权显式化 | 完成 | resolve_adjustment_policy + 死表标注 |
| 5. 无协变量基线 | 跳过 (依赖 Task 6, 需实跑) |
| 6. 指纹与接线 | 完成 | 3 指纹 + comparable() |
| 7. DM+A1 | 完成 | 7 状态 + A1 校验 |
| 8. 出口核验 | 完成 | 本报告 |

## 4. 已知降级声明

- **dm_status 降级**: PR-A1 未实施前 `dm_status` 将频繁落 `insufficient_common`/`no_common_cutoff` — fail-loud 设计行为
- **d_series_n_eff 名义值**: 阶段 1 是 `int(len(d))`，非实测 ESS
- **cov_fingerprint null 豁免**: 探索运行传不齐 cov_matrix/cov_keys 时 `cov_fingerprint=null` — 属 A1 豁免

## 5. PR-A1 阻断影响

PR-A1 (cutoff 语义 + checkpoint 键) 受 D5 裁定阻断。其落地后需：
- 重生成 nocov 基线 (Task 5)
- 重跑 DM 配对验证

## 结论

阶段 1 的 7 个代码任务全部完成，74/74 测试通过。三项硬门中两项闭合，硬门 1 的 cutoff 部分标注为 D5 阻断。建议进入阶段 2 (诊断)。
