# 长时 CPU 任务标准作业流程 (SOP)

> 适用于 FM_a (Windows + Git Bash + Python + TimesFM) 跑超过 10 分钟的 CPU 回测任务。
> 当前环境为 CPU-only；以下流程的目标是清理残留回测进程和保护 JSONL 断点，不涉及 GPU 资源释放。
> 2026-07-29 固化。背景: 多实例长任务混乱复盘（5 个 backtest 实例并发抢资源、同写一个 log）。

## 核心原则

**彻底抛弃"让 Agent 托管长周期任务"**，转向"完全脱机执行 + 状态机增量断点 + 周期性快照巡检"。

`run_in_background` + `TaskStop` 在 Windows 不可靠:
- `timeout` 10 分钟硬杀 background 任务
- `TaskStop`/超时只断工具跟踪，bash 脚本本体存活继续跑，叠加多实例
- 单杀 python 不停脚本（bash `run()` 跳下一 batch）

---

## 工具链 3 个不变量（开跑前确保）

### 1. 解析器免疫乱码 (`scripts/phase4d_parse_results.py`)
```python
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
# 判定符用 ASCII，禁 ✓/✗（GBK 崩溃）
PASS_MARK = "PASS"
FAIL_MARK = "FAIL"
```
解析器读 JSONL（每行 `{"symbol","mode","metric"}`），不读 log——避免 log 格式耦合，续跑不丢结果。

### 2. 杀手脚本精准树杀 (`scripts/_kill_phase4d.ps1`)
```powershell
# 仅匹配真实工作进程，避开 tail (.log)
$processes = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match "monthly_backtest\.py" -and $_.Name -match "python") -or
    ($_.CommandLine -match "phase4d_calendar_matrix\.sh" -and $_.Name -match "bash")
}
foreach ($p in $processes) {
    taskkill /F /T /PID $p.ProcessId | Out-Null   # /T 树杀子进程
}
```

### 3. 编排脚本增量断点 (`scripts/phase4d_calendar_matrix.sh`)
per-symbol-per-mode 循环 + JSONL checkpoint + OOM 缓冲:
```bash
JSONL="reports/monthly_backtest/phase4d_incremental_results.jsonl"
for sym in jd sr cf ur sp m; do
  for mode in baseline replace additive; do
    # JD 无 additive (gated_slope 不在 combo 路径)
    [ "$sym" = "jd" ] && [ "$mode" = "additive" ] && continue
    # 断点续跑: 已完成则跳过
    grep -q "\"symbol\": \"$sym\".*\"mode\": \"$mode\"" "$JSONL" 2>/dev/null && continue
    # 运行 + 捕获指标 + 记 JSONL (成功才记)
    metric=$(python scripts/monthly_backtest.py $ARGS 2>&1 | tee -a "$LOG" | grep -oE "[0-9]+pts DirAcc=.*WR=[0-9]+%")
    [ -n "$metric" ] && echo "{\"symbol\":\"$sym\",\"mode\":\"$mode\",\"metric\":\"$metric\"}" >> "$JSONL"
    sleep 8   # OOM/显存碎片缓冲
  done
done
```
- 全新启动截断 LOG；续跑追加 LOG（保旧结果）。
- 总 symbol-mode 数 = 17（JD 2 + UR/SR/CF/SP/M 各 3）。

---

### 3. 结果文件单写入者约束

同一 JSONL 结果或日志文件只能由一个 Worker/编排器实例写入。断点流程是“启动时读取已完成 bar，再追加 pending bar”，`flush()` 只保证当前进程尽快落盘，不提供并发幂等性。重启前必须确认旧实例已退出；完成判断要核对唯一 `bar_idx`、预期 eval grid、退出码和日志，不能只看行数。

---

## Agent 4 步法则

### Step 1: 环境净空断言 (Pre-flight)
**绝不盲目启动。** 先清理残留回测进程：
```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_phase4d.ps1
```

### Step 2: 火后即焚启动 (Fire and Forget)
**不用 `run_in_background` 工具**，直接 nohup detach:
```bash
cd D:/FlyBuddy/fm_a
nohup bash scripts/phase4d_calendar_matrix.sh > /tmp/phase4d_nohup.out 2>&1 & disown
```
立即结束 tool call，不等。

### Step 3: 并发唯一性断言 (Highlander Check)
启动 ~8s 后，**只数 python 进程**（不数 bash，bash 含工具包装层会误判）:
```bash
sleep 8 && powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object CommandLine -match 'monthly_backtest').Count"
```
期望 **2**（1 venv launcher + 1 SDK python）。若 4/6/更多 → 并发叠加，立即 `_kill_phase4d.ps1` 终止。

### Step 4: 异步快照巡检 (Asynchronous Patrol)
**不用 Monitor**（`tail` 会被 .ps1 连带杀）。需要进度时按需巡检:
```bash
tail -n 15 reports/monthly_backtest/phase4d_calendar_matrix.log   # 看日志尾部
wc -l reports/monthly_backtest/phase4d_incremental_results.jsonl  # 数完成进度
```
进度从 1 增到 17 = 完成，跑 `python scripts/phase4d_parse_results.py` 出最终报告。

---

## 模式 -> monthly_backtest 参数映射

| 模式 | 命令 | 品种 |
|------|------|------|
| baseline | `python scripts/monthly_backtest.py <sym>` | 全部 |
| replace | `python scripts/monthly_backtest.py --cov-override calendar_cyclical <sym>` | 全部 |
| additive | `python scripts/monthly_backtest.py --combo "<orig>,calendar_cyclical" <sym>` | UR/SR/CF/SP/M（JD 无）|

additive 原协变量: UR=ao_accel, SR=rsi_state,oi, CF=ha_body, SP=ha_body, M=vor

## 固化判定（解析器自动）
- MAPE 相对下降 ≥3% / DirAcc 绝对 +3pp / PF 相对 +10%（任一即 PASS）
- Additive PASS → 固化（`covariate_types` 追加 `calendar_cyclical`）
- 仅 Replace PASS → 待裁定
- 都不 PASS → 不固化

---

## 进程管理库 (_batch_lib.sh) — 2026-08-18 加固

> 背景: 单协变量穷举回测暴露 3 个 bash 实例并发跑同一 batch, 孤儿 python worker 继续写 JSONL, 导致结果丢失。
> 根因: `kill -0` Highlander 无法检测孤儿进程 (reparent 到 PID 1), `flock` 在 Git Bash 不可用。

### 核心机制

| 机制 | 实现 | 解决什么 |
|:-----|:-----|:---------|
| 原子抢锁 | `set -C` (noclobber) + 文件 create-or-fail | 防止 TOCTOU 竞态 |
| 心跳过期 | 后台 while 每 60s 更新锁时间戳, 5min 无更新视为过期 | 检测孤儿锁 |
| 双模式清场 | PowerShell 匹配 `batch_f*.sh` + `monthly_backtest.py` | 不漏孤儿 python |
| winpid 贯穿 | 锁文件存 Windows PID (非 MSYS $$) | 跨进程准确识别 |
| heartbeat 自校验 | Get-Process 检查父进程存活, 父死则自退 | 防止孤儿 heartbeat 永锁 |
| EXIT trap 安全删锁 | 校验锁属己 (winpid 匹配) 才删 | 防止删新实例的锁 |

### 使用方法

**batch 脚本 (source _batch_lib.sh):**
```bash
FM_ROOT="D:/FlyBuddy/FM_a"
source scripts/_batch_lib.sh
: > "$LOG"
batch_init "batch_f1"   # 原子锁 + 清场 + heartbeat

for sym in ss sr cj ...; do
  batch_run_one "$sym" "calendar_cyclical" "F1-cal-$sym" "$JSONL" "$LOG"
done
# EXIT trap 自动清理
```

**手动杀进程:**
```bash
# 预览 (不实际杀)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_batch.ps1 -DryRun

# 执行清场
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_batch.ps1

# 排除自身 PID
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_batch.ps1 -ExcludePid 12345
```

### 锁文件

```
路径: reports/data_ops/.batch_runner.lock (全局单实例, 非 per-batch)
内容: winpid|batch_name|unix_timestamp
```

### Agent 启动流程 (修订版)

```
Step 1: 环境净空 (手动, 在 nohup 之前)
  powershell -NoProfile -File scripts/_kill_batch.ps1

Step 2: 启动 (fire and forget)
  nohup bash scripts/batch_f1_single_cov.sh > reports/data_ops/batch_f1_nohup.out 2>&1 &
  立即结束 tool call, 不等。

Step 3: 唯一性断言 (启动 ~30s 后)
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object CommandLine -match 'monthly_backtest' | Select-Object ProcessId, WorkingSetSize"
  期望 2 个 python (1 venv launcher ~3MB + 1 worker ~250MB)。
  若 >2 → 并发叠加, 立即 _kill_batch.ps1。
  若 0 → 可能 cleanup 自杀, 检查 nohup.out。

Step 4: 按需巡检
  wc -l reports/data_ops/batch_f1_progress.jsonl   # 完成数
  tail -5 reports/data_ops/batch_f1.log             # 最新状态
  cat reports/data_ops/.batch_runner.lock            # 锁状态
```

> **重要**: `batch_init` 不再自动清场 (2026-08-18 修复)。
> MSYS `/proc/self/winpid` 与 Win32_Process 进程树不兼容, 自动清场会杀掉自身。
> 孤儿清理必须在 nohup 启动**前**手动执行 `_kill_batch.ps1`。
