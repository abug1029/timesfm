# 基线重生循环修复计划

> **代码基线**: `37c1ee8`

**日期**：2026-10-12  
**状态**：APPROVED（2026-10-12 审核通过）  
**优先级**：P0（阻塞快环启动）  
**预计工作量**：M（1-2 小时）

## 审核记录

**2026-10-12 专家审核**（code-reviewer Opus）：
- **结论**：APPROVE（修正 MAJOR 后）
- **Findings**：1 MAJOR + 2 MINOR + 2 NIT
- **修正**：
  - ✅ [MAJOR] 添加 `_legacy_indices` 辅助函数同步更新（修改 5）
  - ✅ [MINOR] 添加 `generate()` 失败路径注释（修改 2）
  - ✅ [NIT] 添加 docstring 更新（修改 6）
  - ⏸ [MINOR] per-symbol 连续重生计数器（留作后续优化）
  - ⏸ [NIT] 空壳 def 清理（留作后续优化）

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

**修改 2：`ensure_baselines` 加重生循环检测（跨 poll 记忆）**

文件：`/home/abug/timesfm/scripts/sup_evidence.py:1389-1404`

**关键洞察**：`continue` 只能跳过当前循环迭代，挡不住下一次 poll。必须在调用 `generate` **之前**检查并跳过，且需要跨 poll 记忆。

```python
# 模块级变量（在文件顶部或函数外）
_RECENTLY_REGENED_NO_ADVANCE = set()  # 记录"重生后 cutoff 未推进"的品种

def ensure_baselines(symbols, root):
    # ... 现有代码 ...
    for sym in symbols:
        sym_lower = sym.lower()
        points_path = ...
        
        # === Phase 1 止血：在重生之前检查 ===
        # 如果这个品种上次重生后 cutoff 未推进，跳过重生
        if sym_lower in _RECENTLY_REGENED_NO_ADVANCE:
            # 检查数据末端是否真的变了
            current_data_dt = _get_data_dt(sym_lower)  # 读 DB 最新 dt
            if current_data_dt == _RECENTLY_REGENED_NO_ADVANCE[sym_lower]:
                # 数据没变，跳过重生
                print(f"[INFO] ensure_baselines: {sym_lower} 跳过重生（数据未增长，等 daily_update）",
                      file=sys.stderr)
                continue
            else:
                # 数据变了，允许重生
                _RECENTLY_REGENED_NO_ADVANCE.pop(sym_lower)
        
        # ... 现有的重生条件检查 ...
        
        # 重生前记录当前 cutoff
        prev_cutoff = last_cutoff
        
        # 重生（三个调用点之一：1404 行的 reanchor 分支）
        _regen_baseline_with_archive(sym_lower, points_path, root)
        
        # 重生后读取新 cutoff（在 _guard_confirm_from_ts_after_regen 之后）
        new_cutoff = _read_last_cutoff(points_path)
        
        # 比较并记录
        if new_cutoff is not None and new_cutoff == prev_cutoff:
            # 重生后 cutoff 未推进，记录到跨 poll 记忆
            _RECENTLY_REGENED_NO_ADVANCE[sym_lower] = prev_cutoff
            print(f"[WARN] ensure_baselines: {sym_lower} 重生后基线末端未推进 "
                  f"(停在 {new_cutoff}) -- 下次 poll 将跳过重生",
                  file=sys.stderr)
        # ... 其余逻辑 ...
```

**辅助函数**：

```python
def _read_last_cutoff(points_path):
    """读取基线文件的最后一个 cutoff"""
    last_cutoff = None
    try:
        with open(points_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        last_cutoff = rec.get("cutoff") or last_cutoff
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return last_cutoff

def _get_data_dt(sym_lower):
    """读取品种数据的最新 dt（从 DB）"""
    from data.data_store import DataStore
    store = DataStore(sym_lower)
    try:
        result = store.conn.execute("SELECT MAX(dt) FROM kline_1h").fetchone()
        return result[0] if result else None
    finally:
        store.close()
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

文件：`/home/abug/timesfm/tests/test_confirmation_wiring.py:113`

```python
# 修改前：
assert max(got) <= total - HORIZON

# 修改后：
assert max(got) <= total - HORIZON - 1
```

**修改 5（MAJOR）：更新 `_legacy_indices` 辅助函数**

文件：`/home/abug/timesfm/tests/test_confirmation_wiring.py`（文件开头 `_legacy_indices` 函数）

```python
# 修改前：
def _legacy_indices(total):
    # ... 
    right = total - HORIZON + 1
    # ...

# 修改后：
def _legacy_indices(total):
    # ...
    right = total - HORIZON  # 与修复后的 select_eval_indices 一致
    # ...
```

**理由**：`_legacy_indices` 用于向后兼容测试，必须与修复后的主函数公式一致，否则测试 FAIL。

**修改 6（NIT）：更新 `select_eval_indices` docstring**

文件：`/home/abug/timesfm/scripts/monthly_backtest.py:268-273`

```python
# 修改 docstring 中右边界描述：
# 从 "右边界仍是 total - HORIZON" 
# 改为 "右边界是 total - HORIZON - 1"
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
import tempfile


def test_read_last_cutoff():
    """_read_last_cutoff 应正确读取基线文件的最后一个 cutoff"""
    from scripts.sup_evidence import _read_last_cutoff
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"cutoff": "2026-09-23 15:00:00"}) + "\n")
        f.write(json.dumps({"cutoff": "2026-09-24 15:00:00"}) + "\n")
        f.flush()
        path = f.name
    
    try:
        result = _read_last_cutoff(path)
        assert result == "2026-09-24 15:00:00"
    finally:
        Path(path).unlink()


def test_circuit_breaker_memory_across_polls():
    """circuit breaker 应跨 poll 记忆，第二次重生应跳过"""
    from scripts.sup_evidence import (
        _RECENTLY_REGENED_NO_ADVANCE,
        ensure_baselines,
    )
    
    # 清空记忆
    _RECENTLY_REGENED_NO_ADVANCE.clear()
    
    # Mock: 第一次调用，重生后 cutoff 未推进
    # 断言: _RECENTLY_REGENED_NO_ADVANCE 记录了该品种
    
    # Mock: 第二次调用（模拟下一次 poll），数据未变
    # 断言: 跳过重生，打印 INFO
    
    # Mock: 数据变了（模拟 daily_update 后）
    # 断言: 允许重生


def test_regen_proceeds_when_data_advances():
    """数据末端推进后应允许重生"""
    from scripts.sup_evidence import (
        _RECENTLY_REGENED_NO_ADVANCE,
        _get_data_dt,
    )
    
    # Mock: _RECENTLY_REGENED_NO_ADVANCE["jd"] = "2026-09-24 15:00:00"
    # Mock: _get_data_dt("jd") = "2026-09-27 15:00:00" (推进)
    # 断言: 从记忆中移除，允许重生


def test_eval_indices_last_point_has_full_horizon():
    """最后一个 eval 点应有完整的 HORIZON 根 target bars"""
    from scripts.monthly_backtest import select_eval_indices
    from config.backtest_config import HORIZON
    
    # 真实签名: select_eval_indices(dts, *, eval_start_ts=None, max_points=None)
    # 需要构造 dts 列表
    total = 10000
    dts = list(range(total))  # 模拟 10000 个时间点
    
    indices = select_eval_indices(dts)
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
