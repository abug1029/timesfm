# 基线重生循环修复计划

**日期**：2026-10-12  
**状态**：PROPOSED  
**优先级**：P0（阻塞快环启动）  
**预计工作量**：M（1-2 小时）

## 问题摘要

**现象**：supervisor 启动后基线无限重生（116 次），cycles_done 卡在 29，快环无法启动。

**根因**：
1. **主因**：`_baseline_reanchor_reason` 无 circuit breaker，重生后 cutoff 未推进仍重复触发
2. **次因**：`monthly_backtest.py:276` 的 `right = total - HORIZON` 公式差 1（边界越界）
3. **环境**：TqSdk 10000 bars 硬限，DB 数据停在 2026-10-09，基线末端停在 2026-09-24

**数据流**：
```
ensure_baselines() 
  → _baseline_reanchor_reason() 检查 confirm_from_ts (10-03) > last_cutoff (9-24)
  → 返回 "基线末端未覆盖确认窗起点"
  → _regen_baseline_with_archive() 重生
  → generate_baseline_points.generate() 生成 588 个点（仍到 9-24）
  → 下次 poll：相同 last_cutoff → 相同重锚 → 死循环
```

## 修复方案

### Phase 1：止血（选项 A，15 分钟）

**目标**：停止重生循环，让快环启动。

**修改 1：`_regen_baseline_with_archive` 返回新 cutoff**

文件：`/home/abug/timesfm/scripts/sup_evidence.py:1305-1323`

```python
def _regen_baseline_with_archive(sym_lower, points_path, root):
    # ... 现有 archive + generate + guard 代码 ...
    
    # 重生后读取新的 last_cutoff
    new_last_cutoff = None
    try:
        with open(points_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        new_last_cutoff = rec.get("cutoff") or new_last_cutoff
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return new_last_cutoff
```

**修改 2：`ensure_baselines` 加重生循环检测**

文件：`/home/abug/timesfm/scripts/sup_evidence.py:1389-1404`

```python
# 在 reanchor 分支前记录 prev_cutoff
prev_cutoff = last_cutoff

# ... reanchor 检测逻辑 ...

# 重生后比较
new_cutoff = _regen_baseline_with_archive(sym_lower, points_path, root)
if new_cutoff is not None and new_cutoff == prev_cutoff:
    print(f"[WARN] ensure_baselines: {sym_lower} 重生后基线末端未推进 "
          f"(停在 {new_cutoff}) -- 跳过重锚（数据未增长，等 daily_update 拉新数据）",
          file=sys.stderr)
    # 跳过后续重锚逻辑
    continue
```

**效果**：
- 第一次重生：执行，但 cutoff 未推进 → 打印 WARN
- 第二次重生：检测到 prev_cutoff == new_cutoff → 跳过
- 后续：每次 poll 都跳过，不再死循环
- 自愈：当 daily_update 拉新数据后，基线末端推进，重锚恢复正常

### Phase 2：修边界（选项 B，30 分钟）

**目标**：修复最后一个 eval 点的 horizon 不足问题。

**修改 3：修复 `select_eval_indices` 边界公式**

文件：`/home/abug/timesfm/scripts/monthly_backtest.py:276`

```python
# 修改前：
right = total - HORIZON

# 修改后：
right = total - HORIZON - 1
```

**理由**：
- `idx = right` 时，target slice 是 `iloc[idx+1 : idx+1+HORIZON]`
- 当前公式：`idx = total - HORIZON` → slice `[total-HORIZON+1 : total+1]` → 越界（实际只有 HORIZON-1 根）
- 修正后：`idx = total - HORIZON - 1` → slice `[total-HORIZON : total]` → 正好 HORIZON 根

**修改 4：更新测试断言**

文件：`/home/abug/timesfm/tests/test_confirmation_wiring.py:108`

```python
# 修改前：
assert max(got) <= total - HORIZON

# 修改后：
assert max(got) <= total - HORIZON - 1
```

### Phase 3：测试（TDD，30 分钟）

**新建测试文件**：`/home/abug/timesfm/tests/test_baseline_regen_loop.py`

```python
"""
基线重生循环防护测试。

防止 ensure_baselines 在 TqSdk 10000 bar 硬限下无限重生。
"""
import pytest
from pathlib import Path
import json


def test_regen_returns_new_cutoff():
    """_regen_baseline_with_archive 应返回新生成的 last_cutoff"""
    # Mock: 创建临时基线文件
    # 调用: _regen_baseline_with_archive
    # 断言: 返回值是基线文件的最后一个 cutoff


def test_circuit_breaker_skips_same_cutoff():
    """重生后 cutoff 未推进时应跳过重锚"""
    # Mock: prev_cutoff = "2026-09-24 15:00:00"
    # Mock: new_cutoff = "2026-09-24 15:00:00" (相同)
    # 断言: 打印 WARN 并跳过


def test_regen_proceeds_when_cutoff_advances():
    """重生后 cutoff 推进时应正常继续"""
    # Mock: prev_cutoff = "2026-09-24 15:00:00"
    # Mock: new_cutoff = "2026-09-27 15:00:00" (推进)
    # 断言: 不跳过，继续后续逻辑


def test_eval_indices_last_point_has_full_horizon():
    """最后一个 eval 点应有完整的 HORIZON 根 target bars"""
    from scripts.monthly_backtest import select_eval_indices
    from config.backtest_config import HORIZON
    
    total = 10000
    indices = select_eval_indices(total, HORIZON)
    max_idx = max(indices)
    
    # 断言: max_idx + 1 + HORIZON <= total
    assert max_idx + 1 + HORIZON <= total
```

**更新现有测试**：`/home/abug/timesfm/tests/test_baseline_reanchor.py`

添加 circuit breaker 测试用例。

### Phase 4：验证（30 分钟）

**步骤 1**：运行测试

```bash
cd /home/abug/timesfm
pytest tests/test_baseline_regen_loop.py -v
pytest tests/test_baseline_reanchor.py -v
pytest tests/test_confirmation_wiring.py -v
```

**步骤 2**：重启 supervisor

```bash
bash scripts/start_supervisor.sh
```

**步骤 3**：观察日志

```bash
tail -f data/cache/supervisor.out
```

预期：
- 第一次重生：执行
- 第二次重生：打印 `[WARN] ensure_baselines: jd 重生后基线末端未推进`
- 后续：跳过重生，快环启动
- cycles_done 开始增长

**步骤 4**：拉取最新数据（可选）

```bash
python scripts/daily_update.py --symbols jd sr
```

预期：
- DB 数据从 10-09 推进到 10-12
- 下次基线重生时末端推进到 9-27/9-28
- 重锚恢复正常（不再跳过）

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Circuit breaker 误判（数据已增长但跳过） | 低 | 中 | 比较 cutoff 字符串精确匹配；打印 WARN 便于排查 |
| 边界公式修复影响现有基线 | 低 | 低 | 只影响最后一个 eval 点（589 → 588 个）；重生后会修正 |
| TqSdk 10000 bar 硬限无法突破 | 高 | 中 | 接受限制；基线末端会随时间自然推进（每日 ~10 根 1H bar） |

## 时间线

| 阶段 | 任务 | 预计时间 |
|------|------|---------|
| Phase 1 | 止血（circuit breaker） | 15 分钟 |
| Phase 2 | 修边界（公式 + 测试） | 30 分钟 |
| Phase 3 | 测试（TDD） | 30 分钟 |
| Phase 4 | 验证 | 30 分钟 |
| **总计** | | **1 小时 45 分钟** |

## 关键文件路径

| 文件 | 作用 |
|------|------|
| `/home/abug/timesfm/scripts/sup_evidence.py` | 重生逻辑 + circuit breaker |
| `/home/abug/timesfm/scripts/monthly_backtest.py` | eval 边界公式 |
| `/home/abug/timesfm/tests/test_baseline_regen_loop.py` | 新建：circuit breaker 测试 |
| `/home/abug/timesfm/tests/test_baseline_reanchor.py` | 更新：加 circuit breaker 测试 |
| `/home/abug/timesfm/tests/test_confirmation_wiring.py` | 更新：边界断言 |
| `/home/abug/timesfm/config/backtest_config.py` | HORIZON 常量定义 |

## 成功标准

- ✅ 测试全部通过（test_baseline_regen_loop + test_baseline_reanchor + test_confirmation_wiring）
- ✅ Supervisor 启动后无无限重生（日志只打印 1 次 WARN）
- ✅ cycles_done 开始增长（快环启动）
- ✅ 基线末端随 daily_update 推进后恢复正常重锚

## 后续优化（可选）

- **选项 C**：突破 TqSdk 10000 bar 上限（分页拉取）
- **选项 D**：多数据源融合（TqSdk + 其他）
- **选项 E**：动态调整确认窗起点（根据数据末端自动调整）

---

**下一步**：按 Phase 1 → 2 → 3 → 4 顺序实施。
