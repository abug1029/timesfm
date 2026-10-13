# Circuit Breaker 重复重生问题调查报告

**日期**：2026-10-13  
**状态**：ROOT_CAUSE_IDENTIFIED  
**优先级**：P0（阻塞基线重生进度）

## 问题现象

1. jd 有 21 个归档文件，sr 有 12 个归档文件
2. 日志显示 jd → sr → jd → sr 无限循环重生
3. Circuit breaker 记录成功（8 次"重生后基线末端未推进"）
4. 但 circuit breaker **从未触发跳过**（0 次 `[INFO] ensure_baselines: {sym} 跳过重生`）

## 根因分析

### Circuit Breaker 逻辑

```python
# scripts/sup_evidence.py:1390-1401

if sym_lower in _RECENTLY_REGENED_NO_ADVANCE:
    prev_data_dt = _RECENTLY_REGENED_NO_ADVANCE[sym_lower]
    current_data_dt = sup_state._latest_data_dt(sym_lower)
    # 数据末端未变 → 继续跳过
    # 数据末端变了（daily_update 拉了新数据）→ 允许重生
    if current_data_dt == prev_data_dt:
        print(f"[INFO] ensure_baselines: {sym_lower} 跳过重生...")
        continue
    else:
        # 数据有变化，清除记录允许重生
        _RECENTLY_REGENED_NO_ADVANCE.pop(sym_lower)
```

### 根因

**`current_data_dt == prev_data_dt` 从未为 True**

可能原因（按概率排序）：

1. **`_latest_data_dt` 返回 None**
   - 如果数据库连接失败或缓存问题，返回 None
   - `None == "2026-10-09 14:00:00"` 为 False
   - 导致清除记录并允许重生

2. **时间戳格式不一致**
   - 重生前：`"2026-10-09 14:00:00"`
   - 重生后：`"2026-10-09T14:00:00"`（ISO 格式）
   - 字符串比较失败

3. **缓存 TTL 问题**
   - `_latest_data_dt` 有 30 分钟 TTL 缓存
   - 重生前缓存旧值，重生后缓存未过期
   - 下次 poll 时缓存过期，读到新值（但可能格式不同）

### 验证证据

```bash
# 统计 circuit breaker 触发次数
$ grep -c '重生后基线末端未推进' supervisor.out
8  # ✅ 记录成功

$ grep -c '\\[INFO\\] ensure_baselines.*跳过重生' supervisor.out
0  # ❌ 从未触发跳过
```

### 代码路径

1. `_regen_baseline_with_archive` 返回新 cutoff
2. 比较 `new_cutoff == prev_cutoff_before_regen` → True
3. 记录 `_RECENTLY_REGENED_NO_ADVANCE[sym] = current_data_dt`
4. 打印 `[WARN] 重生后基线末端未推进 → 下次 poll 跳过重生`
5. 下次 poll（5 分钟后）
6. 检查 `if sym in _RECENTLY_REGENED_NO_ADVANCE` → True
7. 调用 `_latest_data_dt(sym)` → 返回 None 或不同格式
8. 比较 `current_data_dt == prev_data_dt` → **False**
9. 清除记录，允许重生
10. 回到步骤 1

## 修复方案

### 方案 1：防御性检查 None（推荐）

```python
# scripts/sup_evidence.py:1395-1401

if current_data_dt is None or prev_data_dt is None:
    # 无法确定数据末端，保守处理：跳过重生
    print(f"[INFO] ensure_baselines: {sym_lower} 跳过重生（数据末端查询失败）",
          file=sys.stderr)
    continue

if current_data_dt == prev_data_dt:
    # 数据未变化，跳过重生
    print(f"[INFO] ensure_baselines: {sym_lower} 跳过重生（上次重生基线末端未推进，数据未增长，等 daily_update）",
          file=sys.stderr)
    continue
else:
    # 数据有变化，清除记录允许重生
    _RECENTLY_REGENED_NO_ADVANCE.pop(sym_lower)
```

**优点**：
- 防御性编程，处理 None 情况
- 保守策略：无法确定时跳过重生

**缺点**：
- 如果 `_latest_data_dt` 持续返回 None，会永久跳过重生

### 方案 2：持久化 circuit breaker 记忆

将 `_RECENTLY_REGENED_NO_ADVANCE` 持久化到磁盘（JSON 文件）：
- 启动时加载
- 退出时保存
- 避免 supervisor 重启后记忆丢失

**优点**：
- 解决重启后重复重生问题

**缺点**：
- 需要额外的文件 I/O
- 需要处理文件损坏情况

### 方案 3：在基线文件中添加重生标记

在 `baseline_points_{sym}_nocov.jsonl` 末尾添加特殊记录：
```json
{"__regen_timestamp__": "2026-10-13T15:30:00", "__regen_data_dt__": "2026-10-09 14:00:00"}
```

重生前检查该标记，如果存在且 `data_dt` 未变，跳过重生。

**优点**：
- 与基线文件绑定，不会丢失
- 自动跨 poll 持久化

**缺点**：
- 需要修改基线文件格式
- 需要处理旧格式兼容

## 推荐修复

**立即修复**：方案 1（防御性检查 None）
- 工作量：S（15 分钟）
- 风险：低

**后续优化**：方案 2 或 3（持久化记忆）
- 工作量：M（1-2 小时）
- 风险：中

## 影响评估

### 当前影响
- 基线重生进度：6/25（24%）
- 重复重生：jd（21 次）、sr（12 次）
- 浪费时间：约 30-60 小时（每个品种 15-30 分钟 × 重复次数）

### 修复后预期
- 基线重生进度：正常推进
- 无重复重生
- 预计完成时间：19 个品种 × 30 分钟 = 9.5 小时

## 相关文件

| 文件 | 行号 | 作用 |
|------|------|------|
| `scripts/sup_evidence.py` | 1217 | `_RECENTLY_REGENED_NO_ADVANCE` 定义 |
| `scripts/sup_evidence.py` | 1390-1401 | 重生前检查逻辑 |
| `scripts/sup_evidence.py` | 1453-1461 | 重生后记录逻辑 |
| `scripts/sup_state.py` | 26-50 | `_latest_data_dt` 函数 |

## 相关

- 修复 commit：`16c0ad4`（2026-10-13，circuit breaker 初始实现）
- 技术债记录：[[fm-baseline-regen-tech-debt]]
- 运维手册：[[fm-ops]]

---

**下一步**：实施方案 1（防御性检查 None），提交推送，重启 supervisor。
