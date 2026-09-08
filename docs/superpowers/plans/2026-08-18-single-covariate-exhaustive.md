# 单协变量穷举回测 实施计划 (v3 — 冒烟实测版)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 7 个协变量 × 20 品种进行单独测试 (131 次), 确定每个协变量的独立预测价值与替代价值.

**Architecture:** 每个协变量在所有品种上单独运行完整 walk-forward 回测 (`monthly_backtest.py --combo "<单协变量>"`), 结果同时与**固化方案 baseline** 和 **STANDALONE 绝对门槛**双维裁决. 分 4 批次串行执行, 每批次启动前通知用户. 遵循 long-task-sop: nohup + JSONL 进度 + lock file Highlander.

**Tech Stack:** Python + TimesFM 2.5 (CPU), Git Bash, monthly_backtest.py

**Spec:** 2026-08-18 单协变量覆盖分析

## Global Constraints

- **完整回测**: 必须 396pt walk-forward, 禁止 3pt/7pt scan (2026-08-03 用户指令)
- **编码**: 所有脚本 `export PYTHONIOENCODING=utf-8`
- **Shell**: Git Bash only (终止进程用 `kill`, 不用 PowerShell)
- **SOP**: 长时任务遵循 `docs/long-task-sop.md` (nohup + JSONL + Highlander)
- **审批**: 启动每批次前须通知用户并获批准 (2026-08-05 用户指令)
- **路径**: FM_ROOT = `D:/FlyBuddy/FM_a`

## 权威品种清单 (20)

从 `config/prediction_scheme.py` SCHEMES 重建:

```
ALL20="ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p"
```

共 20 个. 每批循环必须精确匹配此清单 (排除已测品种后).

## 当前单协变量覆盖矩阵 (修正)

| 协变量 | 已单独测试品种 | 未测试品种 | 空白数 | 被固化方案使用次数 |
|:-------|:-------------|:----------|:-----:|:----------------:|
| ha_body | CJ FG FU LH SP | ss sr ma rb eg bu cf i jm jd ao ta ur sh p | **15** | 10 |
| calendar_cyclical | AO SR | ss cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p | **18** | 5 |
| rsi_state | — | 全部 20 品种 | **20** | 3 |
| oi | — | 全部 20 品种 | **20** | 3 |
| reversal_shadow | SS | sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p | **19** | 2 |
| hourly_slope | AO | ss sr cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p | **19** | 2 |
| ao_accel | — | 全部 20 品种 | **20** | 1 |
| bb_squeeze | — | 全部 20 品种 | 20 | 0 |
| vor | — | 全部 20 品种 | 20 | 0 |
| sar_dist | SR | — | **已判死刑** | 0 |

**总计: 131 次新测试** (7 协变量 × 20 品种 - 已测 = 15+18+20+20+19+19+20)

## 裁决标准 (双维 v2)

### 维度 A: 替代价值 (vs 固化方案 baseline)

| 判定 | 条件 |
|:----:|:-----|
| GREEN-EV | PF 相对 baseline ≥+10% AND 绝对 PF≥1.0 AND EV>0 |
| GREEN-MAXDD | MaxDD 绝对改善 ≥15% AND PF 不退化 >5% AND EV≥baseline×0.98 |
| FAIL | 不满足上述任一条件 |

回答: "这个单协变量能否替代当前多协变量组合?" (极简方案可能性)

### 维度 B: 独立价值 (STANDALONE, 绝对门槛)

| 判定 | 条件 |
|:----:|:-----|
| STANDALONE-GREEN | PF≥1.0 AND EV>0 AND MaxDD<80% |
| STANDALONE-BOUNDARY | PF∈[0.95,1.0) AND EV>-0.02 |
| STANDALONE-FAIL | PF<0.95 OR EV<-0.02 |

回答: "这个协变量单独使用是否盈利?" (独立预测能力)

### 为什么需要双维

- 维度 A 的 baseline 是多协变量组合 (如 SR: rsi_state+oi+calendar), 单协变量很难 +10%
- 维度 B 不要求对比 baseline, 直接回答 "能否独立使用"
- 两个维度互补: STANDALONE-GREEN 的品种如果 scheme FAIL, 意味着可以用单协变量简化方案

## 批次分配与精确计数

| 批次 | 协变量 | 循环品种 (精确) | 测试数 |
|:----:|:-------|:---------------|:-----:|
| F1 | calendar_cyclical | ss cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p (18, 排除 AO/SR) | 18 |
| F1 | rsi_state | ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p (20, 全量) | 20 |
| **F1 合计** | | | **38** |
| F2 | oi | ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p (20, 全量) | 20 |
| F2 | reversal_shadow | sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p (19, 排除 SS) | 19 |
| **F2 合计** | | | **39** |
| F3 | hourly_slope | ss sr cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p (19, 排除 AO) | 19 |
| F3 | ha_body | ss sr ma rb eg bu cf i jm jd ao ta ur sh p (15, 排除 CJ/FG/FU/LH/SP) | 15 |
| **F3 合计** | | | **34** |
| F4 | ao_accel | ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p (20, 全量) | 20 |
| **F4 合计** | | | **20** |
| **总计** | | | **131** |

### 巡检预期行数校验

每批次: `JSONL 行数 + log 中 [FAIL] 次数 = 批次测试数`
- F1: jsonl + fail_count = 38
- F2: jsonl + fail_count = 39
- F3: jsonl + fail_count = 34
- F4: jsonl + fail_count = 20

---

### Task 1: CLI 冒烟测试 — 获取实测耗时 + 验证 --combo 单值

**Files:**
- 无新建文件
- 验证: `scripts/monthly_backtest.py --combo` 对单协变量的支持
- 输出: 实测单测耗时 (用于重排时间线)

**Interfaces:**
- 输入: `--combo "calendar_cyclical"` (单协变量, 无逗号)
- 预期输出: 回测正常运行, 日志显示 `[cov=calendar_cyclical]`, 输出含 PF/EV/MaxDD

- [ ] **Step 1: 运行冒烟测试并计时**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
export PYTHONIOENCODING=utf-8

START=$(date +%s)
python scripts/monthly_backtest.py ss --combo "calendar_cyclical" 2>&1 | tee /tmp/smoke_test.log
END=$(date +%s)
ELAPSED=$((END - START))
echo "Smoke test elapsed: ${ELAPSED}s ($(( ELAPSED / 60 ))min)"
```

记录:
- 实测耗时 (秒): **1389s (23m9s)**
- PF: **1.05**
- EV: **+0.025**
- MaxDD: **-37.30%**
- n (pts): **396**
- DirAcc: **51%**

- [ ] **Step 2: 确认 log 格式含 PF/EV/MaxDD**

```bash
grep -E 'PF=|EV=|MaxDD|pts DirAcc' /tmp/smoke_test.log | tail -10
```

确认这些字段可被 grep 提取. 如格式不同, 调整后续 run_one 的 grep 模式.

- [ ] **Step 3: 预写 JSONL 条目避免 F1 重复测试**

冒烟测试已完成 SS calendar_cyclical, 写入 F1 进度文件让 F1 跳过:

```bash
mkdir -p reports/data_ops
SMOKE_METRIC=$(grep -oE '[0-9]+pts DirAcc=.*WR=[0-9]+' /tmp/smoke_test.log | tail -1)
echo "{\"label\": \"F1-cal-ss\", \"symbol\": \"ss\", \"combo\": \"calendar_cyclical\", \"metric\": \"$SMOKE_METRIC\", \"source\": \"smoke_test\"}" > reports/data_ops/batch_f1_progress.jsonl
```

- [ ] **Step 4: 根据实测耗时重排时间线**

```
per_test_min = ELAPSED / 60
total_hours = per_test_min * 131 / 60
per_batch_hours = {
  F1: per_test_min * 38 / 60,
  F2: per_test_min * 39 / 60,
  F3: per_test_min * 34 / 60,
  F4: per_test_min * 20 / 60,
}
```

将结果填入下方 "执行时间线" 表格的空格. 如 per_test > 30min, 需要与用户讨论批次切分策略.

---

### Task 2: 创建批次 F1 脚本 — calendar_cyclical × 18 + rsi_state × 20 = 38 tests

**Files:**
- Create: `scripts/batch_f1_single_cov.sh`
- Create: `reports/data_ops/batch_f1_progress.jsonl` (运行时生成, Task 1 已预写 1 条)
- Create: `reports/data_ops/batch_f1.log` (运行时生成)

**Interfaces:**
- 输入: 品种列表 + 协变量 (硬编码)
- 输出: 增强 JSONL (含 PF/EV/MaxDD) + full log

- [ ] **Step 1: 编写 batch_f1_single_cov.sh**

```bash
#!/bin/bash
# 批次 F1 — 单协变量穷举: calendar_cyclical × 18 + rsi_state × 20 = 38 tests
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate

JSONL="reports/data_ops/batch_f1_progress.jsonl"
LOG="reports/data_ops/batch_f1.log"
LOCK="/tmp/fm_batch_f1.lock"
: > "$LOG"

# Highlander: lock file (Git Bash ps 跨会话不可靠)
if [ -f "$LOCK" ]; then
  old_pid=$(cat "$LOCK")
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "ERROR: another F1 running (pid=$old_pid). abort." | tee -a "$LOG"
    exit 1
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# 增强版 run_one: 提取 PF/EV/MaxDD + unknown 标记
run_one() {
  local sym="$1" combo="$2" label="$3"
  if [ -f "$JSONL" ] && grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
    echo "[SKIP] $label already done" | tee -a "$LOG"
    return 0
  fi
  echo "[START] $label: $sym --combo '$combo'" | tee -a "$LOG"
  if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$LOG" 2>&1; then
    local pf ev maxdd diracc
    pf=$(grep -oE 'PF=[0-9.]+' "$LOG" | tail -1 || echo "PF=unknown")
    ev=$(grep -oE 'EV=[+-]?[0-9.]+' "$LOG" | tail -1 || echo "EV=unknown")
    maxdd=$(grep -oE 'MaxDD=[+-]?[0-9.]+%' "$LOG" | tail -1 || echo "MaxDD=unknown")
    diracc=$(grep -oE '[0-9]+pts DirAcc=[0-9.]+%' "$LOG" | tail -1 || echo "unknown")
    local metric="${diracc} ${pf} ${ev} ${maxdd}"
    # unknown 标记: 允许 DONE 但附加需检查标记
    if echo "$metric" | grep -q "unknown"; then
      echo "[DONE?] $label: $metric (NEEDS_REVIEW)" | tee -a "$LOG"
    else
      echo "[DONE] $label: $metric" | tee -a "$LOG"
    fi
    echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"$combo\", \"pf\": \"$pf\", \"ev\": \"$ev\", \"maxdd\": \"$maxdd\", \"diracc\": \"$diracc\", \"ts\": \"$(date -Iseconds)\"}" >> "$JSONL"
  else
    local rc=$?
    echo "[FAIL] $label exit=$rc" | tee -a "$LOG"
  fi
  sleep 8
}

echo "=== batch_f1 START $(date -Iseconds) ===" >> "$LOG"

# calendar_cyclical × 18 品种 (AO/SR 已有单独测试)
for sym in ss cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p; do
  run_one "$sym" "calendar_cyclical" "F1-cal-$sym"
done

# rsi_state × 20 品种 (全量, 从未单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  run_one "$sym" "rsi_state" "F1-rsi-$sym"
done

echo "=== batch_f1 DONE $(date -Iseconds) ===" | tee -a "$LOG"
```

- [ ] **Step 2: 验证脚本语法 + 计数**

```bash
cd D:/FlyBuddy/FM_a
bash -n scripts/batch_f1_single_cov.sh && echo "syntax OK"

# 计数校验
cal_count=$(grep -c 'run_one.*calendar_cyclical' scripts/batch_f1_single_cov.sh || echo "from_loop")
# 实际: for 循环 18 个品种 × 1 个 covariate = 18 次调用
rsi_count=$(grep -c 'run_one.*rsi_state' scripts/batch_f1_single_cov.sh || echo "from_loop")
# 实际: for 循环 20 个品种 × 1 个 covariate = 20 次调用
echo "F1 expected: cal=18 + rsi=20 = 38"
```

- [ ] **Step 3: 提交脚本**

```bash
git add scripts/batch_f1_single_cov.sh
git commit -m "feat: batch_f1 single cov exhaustive (calendar×18 + rsi_state×20 = 38)"
```

---

### Task 3: 创建批次 F2 脚本 — oi × 20 + reversal_shadow × 19 = 39 tests

**Files:**
- Create: `scripts/batch_f2_single_cov.sh`

- [ ] **Step 1: 编写 batch_f2_single_cov.sh**

```bash
#!/bin/bash
# 批次 F2 — 单协变量穷举: oi × 20 + reversal_shadow × 19 = 39 tests
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate

JSONL="reports/data_ops/batch_f2_progress.jsonl"
LOG="reports/data_ops/batch_f2.log"
LOCK="/tmp/fm_batch_f2.lock"
: > "$LOG"

if [ -f "$LOCK" ]; then
  old_pid=$(cat "$LOCK")
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "ERROR: another F2 running (pid=$old_pid). abort." | tee -a "$LOG"
    exit 1
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

run_one() {
  local sym="$1" combo="$2" label="$3"
  if [ -f "$JSONL" ] && grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
    echo "[SKIP] $label already done" | tee -a "$LOG"
    return 0
  fi
  echo "[START] $label: $sym --combo '$combo'" | tee -a "$LOG"
  if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$LOG" 2>&1; then
    local pf ev maxdd diracc
    pf=$(grep -oE 'PF=[0-9.]+' "$LOG" | tail -1 || echo "PF=unknown")
    ev=$(grep -oE 'EV=[+-]?[0-9.]+' "$LOG" | tail -1 || echo "EV=unknown")
    maxdd=$(grep -oE 'MaxDD=[+-]?[0-9.]+%' "$LOG" | tail -1 || echo "MaxDD=unknown")
    diracc=$(grep -oE '[0-9]+pts DirAcc=[0-9.]+%' "$LOG" | tail -1 || echo "unknown")
    local metric="${diracc} ${pf} ${ev} ${maxdd}"
    if echo "$metric" | grep -q "unknown"; then
      echo "[DONE?] $label: $metric (NEEDS_REVIEW)" | tee -a "$LOG"
    else
      echo "[DONE] $label: $metric" | tee -a "$LOG"
    fi
    echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"$combo\", \"pf\": \"$pf\", \"ev\": \"$ev\", \"maxdd\": \"$maxdd\", \"diracc\": \"$diracc\", \"ts\": \"$(date -Iseconds)\"}" >> "$JSONL"
  else
    local rc=$?
    echo "[FAIL] $label exit=$rc" | tee -a "$LOG"
  fi
  sleep 8
}

echo "=== batch_f2 START $(date -Iseconds) ===" >> "$LOG"

# oi × 20 品种 (全量, 从未单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  run_one "$sym" "oi" "F2-oi-$sym"
done

# reversal_shadow × 19 品种 (SS 已有单独测试)
for sym in sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  run_one "$sym" "reversal_shadow" "F2-rev-$sym"
done

echo "=== batch_f2 DONE $(date -Iseconds) ===" | tee -a "$LOG"
```

- [ ] **Step 2: 验证并提交**

```bash
bash -n scripts/batch_f2_single_cov.sh && echo "syntax OK"
echo "F2 expected: oi=20 + rev=19 = 39"
git add scripts/batch_f2_single_cov.sh
git commit -m "feat: batch_f2 single cov exhaustive (oi×20 + reversal_shadow×19 = 39)"
```

---

### Task 4: 创建批次 F3 脚本 — hourly_slope × 19 + ha_body × 15 = 34 tests

**Files:**
- Create: `scripts/batch_f3_single_cov.sh`

- [ ] **Step 1: 编写 batch_f3_single_cov.sh**

```bash
#!/bin/bash
# 批次 F3 — 单协变量穷举: hourly_slope × 19 + ha_body × 15 = 34 tests
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate

JSONL="reports/data_ops/batch_f3_progress.jsonl"
LOG="reports/data_ops/batch_f3.log"
LOCK="/tmp/fm_batch_f3.lock"
: > "$LOG"

if [ -f "$LOCK" ]; then
  old_pid=$(cat "$LOCK")
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "ERROR: another F3 running (pid=$old_pid). abort." | tee -a "$LOG"
    exit 1
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

run_one() {
  local sym="$1" combo="$2" label="$3"
  if [ -f "$JSONL" ] && grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
    echo "[SKIP] $label already done" | tee -a "$LOG"
    return 0
  fi
  echo "[START] $label: $sym --combo '$combo'" | tee -a "$LOG"
  if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$LOG" 2>&1; then
    local pf ev maxdd diracc
    pf=$(grep -oE 'PF=[0-9.]+' "$LOG" | tail -1 || echo "PF=unknown")
    ev=$(grep -oE 'EV=[+-]?[0-9.]+' "$LOG" | tail -1 || echo "EV=unknown")
    maxdd=$(grep -oE 'MaxDD=[+-]?[0-9.]+%' "$LOG" | tail -1 || echo "MaxDD=unknown")
    diracc=$(grep -oE '[0-9]+pts DirAcc=[0-9.]+%' "$LOG" | tail -1 || echo "unknown")
    local metric="${diracc} ${pf} ${ev} ${maxdd}"
    if echo "$metric" | grep -q "unknown"; then
      echo "[DONE?] $label: $metric (NEEDS_REVIEW)" | tee -a "$LOG"
    else
      echo "[DONE] $label: $metric" | tee -a "$LOG"
    fi
    echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"$combo\", \"pf\": \"$pf\", \"ev\": \"$ev\", \"maxdd\": \"$maxdd\", \"diracc\": \"$diracc\", \"ts\": \"$(date -Iseconds)\"}" >> "$JSONL"
  else
    local rc=$?
    echo "[FAIL] $label exit=$rc" | tee -a "$LOG"
  fi
  sleep 8
}

echo "=== batch_f3 START $(date -Iseconds) ===" >> "$LOG"

# hourly_slope × 19 品种 (AO 已有单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd sp ta ur sh p; do
  run_one "$sym" "hourly_slope" "F3-hs-$sym"
done

# ha_body × 15 品种 (CJ/FG/FU/LH/SP 已有单独测试)
for sym in ss sr ma rb eg bu cf i jm jd ao ta ur sh p; do
  run_one "$sym" "ha_body" "F3-hb-$sym"
done

echo "=== batch_f3 DONE $(date -Iseconds) ===" | tee -a "$LOG"
```

- [ ] **Step 2: 验证并提交**

```bash
bash -n scripts/batch_f3_single_cov.sh && echo "syntax OK"
echo "F3 expected: hs=19 + hb=15 = 34"
git add scripts/batch_f3_single_cov.sh
git commit -m "feat: batch_f3 single cov exhaustive (hourly_slope×19 + ha_body×15 = 34)"
```

---

### Task 5: 创建批次 F4 脚本 — ao_accel × 20 = 20 tests

**Files:**
- Create: `scripts/batch_f4_single_cov.sh`

- [ ] **Step 1: 编写 batch_f4_single_cov.sh**

```bash
#!/bin/bash
# 批次 F4 — 单协变量穷举: ao_accel × 20 = 20 tests
# ao_accel 是 UR 的固化协变量, 从未在其余 19 品种单独测试
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate

JSONL="reports/data_ops/batch_f4_progress.jsonl"
LOG="reports/data_ops/batch_f4.log"
LOCK="/tmp/fm_batch_f4.lock"
: > "$LOG"

if [ -f "$LOCK" ]; then
  old_pid=$(cat "$LOCK")
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "ERROR: another F4 running (pid=$old_pid). abort." | tee -a "$LOG"
    exit 1
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

run_one() {
  local sym="$1" combo="$2" label="$3"
  if [ -f "$JSONL" ] && grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
    echo "[SKIP] $label already done" | tee -a "$LOG"
    return 0
  fi
  echo "[START] $label: $sym --combo '$combo'" | tee -a "$LOG"
  if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$LOG" 2>&1; then
    local pf ev maxdd diracc
    pf=$(grep -oE 'PF=[0-9.]+' "$LOG" | tail -1 || echo "PF=unknown")
    ev=$(grep -oE 'EV=[+-]?[0-9.]+' "$LOG" | tail -1 || echo "EV=unknown")
    maxdd=$(grep -oE 'MaxDD=[+-]?[0-9.]+%' "$LOG" | tail -1 || echo "MaxDD=unknown")
    diracc=$(grep -oE '[0-9]+pts DirAcc=[0-9.]+%' "$LOG" | tail -1 || echo "unknown")
    local metric="${diracc} ${pf} ${ev} ${maxdd}"
    if echo "$metric" | grep -q "unknown"; then
      echo "[DONE?] $label: $metric (NEEDS_REVIEW)" | tee -a "$LOG"
    else
      echo "[DONE] $label: $metric" | tee -a "$LOG"
    fi
    echo "{\"label\": \"$label\", \"symbol\": \"$sym\", \"combo\": \"$combo\", \"pf\": \"$pf\", \"ev\": \"$ev\", \"maxdd\": \"$maxdd\", \"diracc\": \"$diracc\", \"ts\": \"$(date -Iseconds)\"}" >> "$JSONL"
  else
    local rc=$?
    echo "[FAIL] $label exit=$rc" | tee -a "$LOG"
  fi
  sleep 8
}

echo "=== batch_f4 START $(date -Iseconds) ===" >> "$LOG"

# ao_accel × 20 品种 (全量, 从未单独测试)
for sym in ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p; do
  run_one "$sym" "ao_accel" "F4-ao-$sym"
done

echo "=== batch_f4 DONE $(date -Iseconds) ===" | tee -a "$LOG"
```

- [ ] **Step 2: 验证并提交**

```bash
bash -n scripts/batch_f4_single_cov.sh && echo "syntax OK"
echo "F4 expected: ao_accel=20"
git add scripts/batch_f4_single_cov.sh
git commit -m "feat: batch_f4 single cov exhaustive (ao_accel×20 = 20)"
```

---

### Task 6: 执行 F1 批次 — 38 tests

**Files:**
- 使用: `scripts/batch_f1_single_cov.sh` (Task 2)
- 前置: `reports/data_ops/batch_f1_progress.jsonl` (Task 1 已预写 F1-cal-ss)

- [ ] **Step 1: 数据新鲜度预检 (data.cli status)**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
python -m data.cli status 2>&1 | grep -E 'STALE|ERROR|过期' || echo "ALL FRESH"
```

如有 STALE, 先采集数据. 不通过则停止.

- [ ] **Step 2: 通知用户并获批准**

报告: 实测单测耗时 (Task 1 结果) × 38 = F1 预计总时长.

- [ ] **Step 3: Highlander + 启动**

```bash
cd D:/FlyBuddy/FM_a
# 确认无其他回测运行
tasklist | grep -i python | grep monthly_backtest || echo "no existing backtest"

# 启动
export PYTHONIOENCODING=utf-8
nohup bash scripts/batch_f1_single_cov.sh > reports/data_ops/batch_f1_nohup.out 2>&1 &
echo $! > reports/data_ops/batch_f1.pid
```

- [ ] **Step 4: 巡检**

```bash
# 进度: JSONL 行数 + FAIL 数 = 38?
jsonl_count=$(wc -l < reports/data_ops/batch_f1_progress.jsonl 2>/dev/null || echo 0)
fail_count=$(grep -c '\[FAIL\]' reports/data_ops/batch_f1.log 2>/dev/null || echo 0)
echo "F1 progress: $jsonl_count done + $fail_count failed / 38 total"
tail -3 reports/data_ops/batch_f1.log
```

- [ ] **Step 5: 确认完成**

```bash
jsonl_count=$(wc -l < reports/data_ops/batch_f1_progress.jsonl)
fail_count=$(grep -c '\[FAIL\]' reports/data_ops/batch_f1.log || echo 0)
echo "F1 final: $jsonl_count + $fail_count = $(( jsonl_count + fail_count )) (expect 38)"
grep 'batch_f1 DONE' reports/data_ops/batch_f1.log
```

- [ ] **Step 6: 终止方式 (如需)**

```bash
kill $(cat reports/data_ops/batch_f1.pid) 2>/dev/null
```

---

### Task 7: 执行 F2 批次 — 39 tests

**Files:**
- 使用: `scripts/batch_f2_single_cov.sh` (Task 3)
- 额外预检: oi 字段覆盖率 (F2 含 oi 回测)

- [ ] **Step 1: 数据预检 + oi 覆盖率检查**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
python -m data.cli status 2>&1 | grep -E 'STALE|ERROR|过期' || echo "ALL FRESH"

# oi 覆盖率检查 (F2 特有)
python -c "
import sqlite3
syms = 'ss sr cj fg fu lh ma rb eg bu cf i jm jd ao sp ta ur sh p'.split()
for s in syms:
    con = sqlite3.connect(f'db/futures_{s}.db')
    try:
        total = con.execute('SELECT COUNT(*) FROM kline_1d WHERE oi IS NOT NULL AND oi > 0').fetchone()[0]
        all_rows = con.execute('SELECT COUNT(*) FROM kline_1d').fetchone()[0]
        pct = total / all_rows * 100 if all_rows > 0 else 0
        if pct < 80:
            print(f'WARNING: {s} oi coverage {pct:.0f}% ({total}/{all_rows})')
    except Exception as e:
        print(f'ERROR: {s} — {e}')
    con.close()
print('oi coverage check done')
"
```

oi 覆盖率 <80% 的品种在裁决时需标注 "oi 数据不足, 结果仅供参考".

- [ ] **Step 2: 通知用户并获批准**
- [ ] **Step 3: Highlander + 启动 (同 Task 6 模式)**
- [ ] **Step 4: 巡检 (expect 39)**
- [ ] **Step 5: 确认完成**

---

### Task 8: 执行 F3 批次 — 34 tests

- [ ] **Step 1: 数据预检**
- [ ] **Step 2: 通知用户并获批准**
- [ ] **Step 3: Highlander + 启动**
- [ ] **Step 4: 巡检 (expect 34)**
- [ ] **Step 5: 确认完成**

---

### Task 9: 执行 F4 批次 — 20 tests

- [ ] **Step 1: 数据预检**
- [ ] **Step 2: 通知用户并获批准**
- [ ] **Step 3: Highlander + 启动**
- [ ] **Step 4: 巡检 (expect 20)**
- [ ] **Step 5: 确认完成**

---

### Task 10: 汇总结果 + 裁决报告 + Registry 更新

**Files:**
- 输入: 4 个 JSONL + 4 个 full log
- Create: `reports/research/20260818_single_cov_exhaustive_verdict.md`
- Create: `scripts/gen_single_cov_registry.py` (从 JSONL 生成 registry 条目)
- Modify: `docs/backtest_registry.md`

- [ ] **Step 1: 从 4 个 JSONL 提取全部 131 条指标**

JSONL 已含 pf/ev/maxdd/diracc 字段, 直接解析:

```python
import json
results = []
for batch in ['f1', 'f2', 'f3', 'f4']:
    jsonl = f'reports/data_ops/batch_{batch}_progress.jsonl'
    with open(jsonl) as f:
        for line in f:
            results.append(json.loads(line))
print(f"Total results: {len(results)}")
```

- [ ] **Step 2: 双维裁决**

对每条结果:
- 维度 A (替代价值): 从 backtest_registry 取该品种 baseline PF/EV/MaxDD, 计算相对变化
- 维度 B (独立价值): STANDALONE-GREEN if PF≥1.0 AND EV>0 AND MaxDD<80%

- [ ] **Step 3: 按协变量聚合**

对每个协变量统计:
- STANDALONE-GREEN 品种数 / 总测试数
- 平均 PF, 最高/最低 PF 品种
- vs baseline 退化/持平/改善分布

- [ ] **Step 4: 撰写裁决报告**

报告结构:
1. 冒烟测试耗时 + 实际执行时间线
2. 全量结果表 (131 行, 双维裁决)
3. 按协变量聚合统计
4. 与已固化方案对比 (维度 A)
5. 独立价值排名 (维度 B)
6. 关键发现 + 固化建议
7. bb_squeeze/vor 重启条件: 若本轮出现强独立信号 (STANDALONE-GREEN ≥5 品种), 建议回炉
8. 多重比较说明

- [ ] **Step 5: 编写 registry 生成脚本**

```python
#!/usr/bin/env python3
"""从 batch_fX JSONL + log 生成 backtest_registry.md 追加条目."""
import json, re, os

VARIETY_NAMES = {
    'ss': 'SS 不锈钢', 'sr': 'SR 白糖', 'cj': 'CJ 红枣', 'fg': 'FG 玻璃',
    'fu': 'FU 燃料油', 'lh': 'LH 生猪', 'ma': 'MA 甲醇', 'rb': 'RB 螺纹钢',
    'eg': 'EG 乙二醇', 'bu': 'BU 沥青', 'cf': 'CF 棉花', 'i': 'I 铁矿石',
    'jm': 'JM 焦煤', 'jd': 'JD 鸡蛋', 'ao': 'AO 氧化铝', 'sp': 'SP 纸浆',
    'ta': 'TA PTA', 'ur': 'UR 尿素', 'sh': 'SH 烧碱', 'p': 'P 棕榈油',
}

results = []
for batch in ['f1', 'f2', 'f3', 'f4']:
    jsonl = f'reports/data_ops/batch_{batch}_progress.jsonl'
    if not os.path.exists(jsonl):
        continue
    with open(jsonl) as f:
        for line in f:
            r = json.loads(line.strip())
            r['batch'] = batch
            results.append(r)

# 按品种分组输出
from collections import defaultdict
by_sym = defaultdict(list)
for r in results:
    by_sym[r['symbol']].append(r)

for sym in sorted(by_sym.keys()):
    name = VARIETY_NAMES.get(sym, sym.upper())
    print(f"\n## {name}")
    print("| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |")
    print("|:---|:---:|:---|---:|:---:|:---|")
    for r in by_sym[sym]:
        combo = r['combo']
        diracc = r.get('diracc', 'N/A')
        pf = r.get('pf', '')
        print(f"| {combo} | 2026-08-18 | Phase 11 (单协变量穷举) | {diracc} | {pf} | 待裁决 |")
```

- [ ] **Step 6: 提交最终产物**

```bash
git add reports/research/20260818_single_cov_exhaustive_verdict.md
git add scripts/gen_single_cov_registry.py
git add docs/backtest_registry.md
git commit -m "feat: Phase 11 单协变量穷举裁决 (131 tests, 7 covariates, 20 varieties)"
```

---

## 执行时间线 (冒烟实测: 23min/test)

**冒烟实测**: SS calendar_cyclical, 396pts, **23m9s** (2026-08-18 09:38→10:02)
**冒烟结果**: DirAcc=51% PF=1.05 EV=+0.025 MaxDD=-37.30% → **STANDALONE-GREEN**

| 阶段 | 内容 | 测试数 | CPU 时间 | 状态 |
|:----:|:-----|:-----:|:-------:|:----:|
| Task 1 | CLI 冒烟 | 1 | 23min | ✅ 完成 |
| Task 2-5 | 脚本创建 | — | ~15min | 待执行 |
| Task 6 | F1: calendar×18+rsi_state×20 | 38 | ~14.5h | 待审批 |
| Task 7 | F2: oi×20+reversal_shadow×19 | 39 | ~15h | 待审批 |
| Task 8 | F3: hourly_slope×19+ha_body×15 | 34 | ~13h | 待审批 |
| Task 9 | F4: ao_accel×20 | 20 | ~7.5h | 待审批 |
| Task 10 | 裁决报告 | — | ~30min | 待执行 |
| **总计** | | **132** | **~50h** | |

> 实测口径 23min/test. 4 批次 ≈ 4 晚 (每晚 ~12-15h). 与 v1 的 15min 估算差 1.5×, 与 v1-review 引用的 30-60min 估算差 0.4×.

## 跳过的测试

| 协变量 | 跳过理由 | 重启条件 |
|:-------|:---------|:---------|
| sar_dist | 协变量空白补测 6 次 0 PASS, 已归档 | — |
| bb_squeeze | Phase 9 组合测试全 FAIL (AO/JD/MA) | 本轮若 ≥5 品种 STANDALONE-GREEN, 回炉测试 |
| vor | 同上 | 同上 |
| basis_momentum | 仅部分品种可用 (需 basis 数据) | 留待 basis 专项 |
| ccl / ccl_pct / pca_momentum | 已废弃 | — |

## 修正记录 (v1 → v2)

| 问题 | 来源 | 修正 |
|:-----|:----:|:-----|
| ao_accel 20 次缺失 | 阻断 #1 | 新增 F4 批次, 总计 111→131 |
| 品种 19≠20, P 缺失 | 阻断 #2 | 全部 6 个循环加入 p, 重算所有计数 |
| 耗时 15min 与 30-60min 矛盾 | 阻断 #3 | 改为冒烟实测驱动, 时间线留空待填 |
| 判定基线混淆独立/替代价值 | 重要 #4 | 增加双维裁决 (维度 A 替代 + 维度 B STANDALONE) |
| JSONL 缺 PF/EV/MaxDD | 重要 #5 | run_one 改为分别 grep pf/ev/maxdd, 存入 JSONL |
| 预检退化+缺 oi 覆盖 | 重要 #6 | 每批次用 data.cli status, F2 加 oi 覆盖率检查 |
| 冒烟测试重复 | 次要 | Task 1 Step 3 预写 JSONL 让 F1 跳过 |
| PowerShell kill 残留 | 次要 | 改为 `kill $(cat pid)`, 删除 _kill_cov_gap.ps1 引用 |
| Highlander 不可靠 | 次要 | 改为 lock file + kill -0 检测 |
| 巡检不含 FAIL 计数 | 次要 | 改为 "JSONL + FAIL = 预期" |
| Registry 手工追加易错 | 次要 | 新增 gen_single_cov_registry.py 自动生成 |
| bb_squeeze/vor 无重启条件 | 次要 | 跳过表增加 "重启条件" 列 |

### v2 → v3 (冒烟实测)

| 变更 | 数据 |
|:-----|:-----|
| 实测耗时 | 23m9s/test (SS calendar_cyclical, 396pts, CPU-only) |
| 总耗时 | ~50h (131 × 23min), 4 晚 |
| 冒烟结果 | SS calendar: PF=1.05, EV=+0.025, MaxDD=-37.30%, STANDALONE-GREEN |
| JSONL 预存 | F1-cal-ss 已写入 batch_f1_progress.jsonl, F1 执行时自动跳过 |
| 时间口径对比 | v1: 15min (偏低 1.5×), user-review: 30-60min (偏高 1.3-2.6×), 实测: 23min |
