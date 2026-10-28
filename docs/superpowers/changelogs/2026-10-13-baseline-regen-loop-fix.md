# Changelog: 基线重生循环修复

> **代码基线**: `16c0ad4`

**日期**：2026-10-13  
**commit**：待提交  
**关联计划**：`docs/superpowers/plans/2026-10-12-baseline-regen-loop-fix-plan.md`

## 问题摘要

**现象**：supervisor 启动后基线无限重生（116 次），cycles_done 卡在 29，快环无法启动。

**根因**：
1. **主因**：`_baseline_reanchor_reason` 无 circuit breaker，重生后 cutoff 未推进仍重复触发
2. **次因**：`monthly_backtest.py:276` 的 `right = total - HORIZON` 公式差 1（边界越界）
3. **环境**：TqSdk 10000 bars 硬限，DB 数据停在 2026-10-09，基线末端停在 2026-09-24

## 修复内容

### Phase 1：止血（circuit breaker）

**文件**：`scripts/sup_evidence.py`

| 行号 | 修改 | 作用 |
|------|------|------|
| 1217 | `_RECENTLY_REGENED_NO_ADVANCE: dict[str, str] = {}` | 模块级变量，记录"重生后 cutoff 未推进"的品种及其数据末端 |
| 1309-1328 | `_read_last_cutoff(points_path)` | 辅助函数：读取基线文件最后一个 cutoff |
| 1349-1350 | `_regen_baseline_with_archive` 返回 `_read_last_cutoff(points_path)` | 重生后返回新 cutoff |
| 1387-1401 | circuit breaker 检查（重生之前） | 如果品种在记忆中且数据末端未变，跳过重生 |
| 1453-1461 | 重生后比较 cutoff | cutoff 未推进则记录数据末端到记忆 |

**关键设计**：
- Circuit breaker 存储**数据末端**（data_dt），不是 cutoff
- 检查在 `generate()` **之前**，避免无谓计算
- 跨 poll 记忆：只有 daily_update 拉新数据后才允许重生

### Phase 2：修边界

**文件**：`scripts/monthly_backtest.py`

| 行号 | 修改 | 作用 |
|------|------|------|
| 271 | docstring 更新为 `右边界是 total - HORIZON - 1` | 文档同步 |
| 276 | `right = total - HORIZON - 1` | 修复边界公式，保证最后一个 eval 点有完整 HORIZON 根 target |

**文件**：`tests/test_confirmation_wiring.py`

| 行号 | 修改 | 作用 |
|------|------|------|
| 33 | `_legacy_indices` 公式 `total - HORIZON + 1` → `total - HORIZON` | 向后兼容测试与新公式一致 |
| 113 | 断言 `max(got) <= total - HORIZON` → `max(got) <= total - HORIZON - 1` | 边界断言更新 |

### Phase 3：测试

**新建文件**：`tests/test_baseline_regen_loop.py`（218 行，8 个测试）

| 测试 | 作用 |
|------|------|
| `test_read_last_cutoff_returns_last` | 正确读取最后一个 cutoff |
| `test_read_last_cutoff_empty_file` | 空文件返回 None |
| `test_read_last_cutoff_missing_file` | 不存在文件返回 None |
| `test_circuit_breaker_skips_regen_on_second_poll` | 第二次 poll 跳过重生 |
| `test_circuit_breaker_allows_regen_after_data_advance` | 数据推进后允许重生 |
| `test_circuit_breaker_records_data_dt` | 存储的是 data_dt 而非 cutoff |
| `test_eval_indices_last_point_has_full_horizon` | 最后一个 eval 点有完整 horizon |
| `test_regen_returns_cutoff` | _regen 返回新 cutoff |

## 验证结果

### 测试结果
```
✅ test_baseline_regen_loop.py: 8 passed
✅ test_baseline_reanchor.py: 12 passed
✅ test_confirmation_wiring.py: 20 passed
✅ 总计: 40 passed, 0 failed
```

### 生产环境验证
```
修复前：
- cycles_done = 29（卡死）
- phase = slow
- 重生循环 116 次

修复后：
- cycles_done = 30（增长）✅
- phase = fast（快环启动）✅
- 重生循环停止 ✅
- 快环 run_2026-10-13_01-06-27 启动 ✅
```

**Circuit breaker 生效证据**：
```
[WARN] ensure_baselines: jd 重生后基线末端未推进 (停在 2026-09-24 15:00:00) → 下次 poll 跳过重生
[WARN] ensure_baselines: sr 重生后基线末端未推进 (停在 2026-09-29 10:00:00) → 下次 poll 跳过重生
```

## 影响

### 正面影响
- ✅ 停止无限重生循环，让快环正常启动
- ✅ 修复最后一个 eval 点的 horizon 不足问题
- ✅ 自愈：daily_update 拉新数据后自动恢复重生

### 潜在风险
- ⚠️ 如果 TqSdk 10000 bar 硬限长期不突破，基线末端会持续落后于确认窗
- ⚠️ 需要定期运行 daily_update 保持数据新鲜度

## 后续优化（可选）

- **选项 C**：突破 TqSdk 10000 bar 上限（分页拉取）
- **选项 D**：多数据源融合（TqSdk + 其他）
- **选项 E**：动态调整确认窗起点（根据数据末端自动调整）

## 相关

- 计划文档：`docs/superpowers/plans/2026-10-12-baseline-regen-loop-fix-plan.md`
- 调查报告：`docs/superpowers/reports/2026-10-11-supervisor-watchdog-death-loop-audit.md`（前序）

---

**全部修复完成，等待专家审核后提交。**
