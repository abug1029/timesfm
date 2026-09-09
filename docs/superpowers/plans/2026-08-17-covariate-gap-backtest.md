# 协变量空白补测 Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 20 品种中测试不足/从未测试的协变量×品种组合进行系统性补测，填补 141 次回测中的空白区域，寻找可改善 PF/DirAcc 的新组合。

**Architecture:** 基于 `scripts/monthly_backtest.py` 的 `--combo` / `--cov-override` CLI 接口，按优先级分批执行完整 396pt walk-forward 回测。每批次用链式 bash 脚本顺序执行，nohup 脱机运行。结果写 `reports/monthly_backtest/` 并更新 `docs/backtest_registry.md`。

**Tech Stack:** Python + TimesFM 2.5 (CPU-only) + SQLite + Git Bash + JSONL

**Spec:** 协变量穷举历史总梳理（2026-08-17 对话产出）

## Global Constraints

- **一次批准覆盖全部 5 批**（本计划启动前统一批准；若中途出现异常模式需加测，另行请示）
- **口径一致性**：所有基线数字均来自 `config/prediction_scheme.py` 中 G005 rebaseline（2026-08-08）后的值。`monthly_backtest.py` 代码未变，跑出的结果与基线直接可比。
- **`--combo` 语义确认**：`--combo "a,b"` **完全覆盖**品种默认协变量集（不叠加）。命令中列出的组合就是要测试的组合。
- CPU-only 环境，单品种 396pt ≈ 30-60 分钟
- 长时任务 SOP：`docs/long-task-sop.md`（nohup + 链式脚本 + 并发唯一性断言）
- Shell 统一为 **Git Bash**（`.venv/Scripts/activate` 兼容）
- `export PYTHONIOENCODING=utf-8` 防 GBK 崩溃（每个脚本顶部显式设置）
- 禁止用 3pt/7pt scan 代替完整 WF 回测（2026-08-03 用户指令）
- 每次运行独立报告文件（`monthly_backtest.py` 自动按时间戳命名），不需要手动指定 checkpoint

### v2 判定标准（统一口径，消除矛盾）

所有判定均为**相对当前固化基线**，同时满足绝对地板：

| 判定 | 条件（相对基线） | 绝对地板 |
|------|-----------------|----------|
| **GREEN-EV** | PF 相对提升 ≥ 10% **且** EV 相对提升 ≥ 10% | PF ≥ 1.0 **且** EV > 0 |
| **GREEN-MAXDD** | MaxDD 绝对值缩小 ≥ 15% **且** PF 不退化 > 5% | EV ≥ baseline_EV × 0.98（容差 2%） |
| **FAIL** | 不满足以上任一 | — |

裁决报告中**必须列出基线数值列**（baseline PF / EV / MaxDD / DirAcc），与测试结果并列。

### 品种覆盖说明

本计划覆盖 10 个品种（SS/UR/SR/JD/RB/FU/FG/SP/MA/TA），其余 10 个品种（CJ/LH/EG/M/CF/BU/AO/I/P/JM）不补测的原因：
- CJ/LH/EG/M/CF：Phase 9 已充分测试（各 5-18 条记录）
- BU/AO/I/JM：1★ 且 Phase 9/10 已测试充分，DirAcc 离 2★ 差距过大，优化空间有限
- P：G004 刚固化（2026-08-17），暂不动

---

## 批次总览 (16 次回测)

| 批次 | 品种 | `--combo` 参数 | 对照基线 | 目标 | 预估耗时 |
|:----:|------|----------------|----------|------|----------|
| A1 | SS | `reversal_shadow` | SS 当前 baseline | 固化方案 v2 验证 | ~40min |
| A2 | SR | `sar_dist` | SR baseline (rsi_state+oi+calendar) | **sar_dist 孤立对照首测** | ~50min |
| A3 | UR | `ao_accel,oi` | UR baseline (ao_accel) | 组合增强 | ~50min |
| A4 | UR | `ao_accel,reversal_shadow` | UR baseline (ao_accel) | 组合增强 | ~50min |
| B1 | SS | `rsi_state,sar_dist` | SS baseline (reversal_shadow) | sar_dist 组合 rsi_state | ~40min |
| B2 | SR | `rsi_state,sar_dist` | SR baseline (rsi_state+oi+calendar) | sar_dist 加入已固化体系 | ~50min |
| B3 | JD | `rsi_state,sar_dist` | JD baseline (rsi_state+oi) | sar_dist 加入 rsi_state 体系 | ~50min |
| C1 | RB | `ha_body,sar_dist` | RB baseline (ha_body) | ha_body 正交增强 | ~50min |
| C2 | FU | `ha_body,sar_dist` | FU baseline (ha_body) | ha_body 正交增强 | ~50min |
| C3 | FG | `ha_body,sar_dist` | FG baseline (ha_body) | ha_body 正交增强 | ~50min |
| D1 | SP | `ha_body` | SP baseline (ha_body+calendar) | 消融：calendar 是否有贡献 | ~40min |
| D2 | SP | `rsi_state,oi` | SP baseline (ha_body+calendar) | 正交方案替代 | ~40min |
| D3 | MA | `sar_dist,hourly_slope` | MA baseline (hourly_slope+oi) | 新组合 | ~50min |
| E1 | SS | `reversal_shadow,calendar_cyclical` | SS baseline (reversal_shadow) | 影线+季节性 | ~40min |
| E2 | UR | `hourly_slope,reversal_shadow` | UR baseline (ao_accel) | 跨品种迁移验证 | ~50min |
| E3 | TA | `ha_body,ao_accel` | TA baseline (ha_body) | TA PF=0.99 边界改善 | ~50min |

**总计: 16 次回测（新增 A2=sar_dist 孤立对照），预估 13-15 小时**

> **sar_dist 归因说明**：
> - **A2 (SR `sar_dist` 单独)**: 孤立对照，与 SR baseline (rsi_state+oi+calendar) 的差纯粹是 sar_dist 替换整个组合的效应。这是 sar_dist 有无价值的直接证据。
> - **B1-B3**: 组合测试，与 baseline 差多个变量。PASS/FAIL 不能归因于 sar_dist 单独。
> - **C1-C3**: 干净归因——baseline 就是 ha_body 单独，combo 只加了 sar_dist 一个变量。差就是 sar_dist 的边际贡献。
> - **D3/MA**: 混杂了"移除 oi"效应，不能干净归因。
> - **sar_dist 全 FAIL 时的结论降级**（修正原风险预案过强推断）：若 A2 + C1-C3 全部 FAIL → "sar_dist 作为独立或 ha_body 辅助协变量无价值"；若 A2 FAIL 但 C1-C3 有 PASS → "sar_dist 不能替代 rsi_state 体系，但与 ha_body 搭配有边际价值"；若仅 A2 FAIL 但其他 PASS → 结论需分体系讨论，不能一刀切。

---

## 链式脚本设计

每个批次一个 bash 脚本，顺序执行该批次所有回测，一次 nohup 启动跑完整个批次。

**脚本模板** (`scripts/batch_X_cov_gap.sh`)：

```bash
#!/bin/bash
# 批次 X — 协变量空白补测
# 一次启动，顺序跑完所有组合，每完成一条记 JSONL
set -euo pipefail
export PYTHONIOENCODING=utf-8

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate

JSONL="reports/data_ops/batch_X_progress.jsonl"
LOG="reports/data_ops/batch_X.log"

# 全新启动截断 LOG；续跑追加
[ ! -f "$JSONL" ] || true  # JSONL 保留（断点续跑用）
: > "$LOG"  # 截断 LOG

run_one() {
  local sym="$1" combo="$2" label="$3"
  # 断点续跑：检查 JSONL 是否已有此 label 的成功记录
  if grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
    echo "[SKIP] $label 已完成" >> "$LOG"
    return
  fi
  echo "[START] $label ($sym --combo '$combo')" >> "$LOG"
  # 运行
  if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$LOG" 2>&1; then
    # 从 LOG 尾部提取结果行
    metric=$(tail -5 "$LOG" | grep -oE '[0-9]+pts DirAcc=.*WR=[0-9]+%' | tail -1)
    echo "{\"label\":\"$label\",\"symbol\":\"$sym\",\"combo\":\"$combo\",\"metric\":\"$metric\"}" >> "$JSONL"
    echo "[DONE] $label: $metric" >> "$LOG"
  else
    echo "[FAIL] $label 回测异常退出 (exit $?)" >> "$LOG"
  fi
  sleep 8  # OOM 缓冲
}

# ── 批次内容 ──
run_one ss  "reversal_shadow"              "A1-SS-revshadow"
run_one sr  "sar_dist"                      "A2-SR-sardist-alone"
# ... 其余 run_one 调用
```

---

### Task 1: 准备工作 — 脚本 + 环境 + 数据

**Files:**
- Create: `scripts/batch_a_cov_gap.sh`
- Create: `scripts/batch_b_cov_gap.sh`
- Create: `scripts/batch_c_cov_gap.sh`
- Create: `scripts/batch_d_cov_gap.sh`
- Create: `scripts/batch_e_cov_gap.sh`
- Create: `scripts/_kill_cov_gap.ps1`

**前置条件:**
- 用户批准全部 5 批（一次批准）

- [ ] **Step 1: 编写 5 个批次链式脚本**

每个脚本按上述模板，填入该批次的 `run_one` 调用。完整内容：

**`scripts/batch_a_cov_gap.sh`**:
```bash
#!/bin/bash
set -euo pipefail
export PYTHONIOENCODING=utf-8
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate

JSONL="reports/data_ops/batch_a_progress.jsonl"
LOG="reports/data_ops/batch_a.log"
: > "$LOG"

run_one() {
  local sym="$1" combo="$2" label="$3"
  if grep -q "\"label\": \"$label\"" "$JSONL" 2>/dev/null; then
    echo "[SKIP] $label 已完成" >> "$LOG"; return
  fi
  echo "[START] $label" >> "$LOG"
  if python scripts/monthly_backtest.py "$sym" --combo "$combo" >> "$LOG" 2>&1; then
    metric=$(tail -10 "$LOG" | grep -oE '[0-9]+pts DirAcc=.*WR=[0-9]+%' | tail -1)
    echo "{\"label\":\"$label\",\"symbol\":\"$sym\",\"combo\":\"$combo\",\"metric\":\"$metric\"}" >> "$JSONL"
    echo "[DONE] $label: $metric" >> "$LOG"
  else
    echo "[FAIL] $label" >> "$LOG"
  fi
  sleep 8
}

run_one ss "reversal_shadow"               "A1"
run_one sr "sar_dist"                       "A2"
run_one ur "ao_accel,oi"                    "A3"
run_one ur "ao_accel,reversal_shadow"       "A4"
```

**`scripts/batch_b_cov_gap.sh`**:
```bash
run_one ss "rsi_state,sar_dist"             "B1"
run_one sr "rsi_state,sar_dist"             "B2"
run_one jd "rsi_state,sar_dist"             "B3"
```

**`scripts/batch_c_cov_gap.sh`**:
```bash
run_one rb "ha_body,sar_dist"               "C1"
run_one fu "ha_body,sar_dist"               "C2"
run_one fg "ha_body,sar_dist"               "C3"
```

**`scripts/batch_d_cov_gap.sh`**:
```bash
run_one sp "ha_body"                        "D1"
run_one sp "rsi_state,oi"                   "D2"
run_one ma "sar_dist,hourly_slope"          "D3"
```

**`scripts/batch_e_cov_gap.sh`**:
```bash
run_one ss "reversal_shadow,calendar_cyclical"  "E1"
run_one ur "hourly_slope,reversal_shadow"       "E2"
run_one ta "ha_body,ao_accel"                   "E3"
```

> 注：上面只列出 `run_one` 调用部分，完整的 `run_one` 函数定义与 batch_a 相同。每个脚本头部均需要 `set -euo pipefail / export PYTHONIOENCODING=utf-8 / cd / source venv / JSONL/LOG 定义 / run_one 函数定义`。

- [ ] **Step 2: 编写杀手脚本 `scripts/_kill_cov_gap.ps1`**

```powershell
$processes = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match "monthly_backtest\.py" -and $_.Name -match "python") -or
    ($_.CommandLine -match "batch_[a-e]_cov_gap\.sh" -and $_.Name -match "bash")
}
foreach ($p in $processes) {
    taskkill /F /T /PID $p.ProcessId | Out-Null
}
```

- [ ] **Step 3: 环境净空断言**

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/_kill_cov_gap.ps1
# 确认无残留
sleep 8 && powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object CommandLine -match 'monthly_backtest').Count"
# 期望 0
```

- [ ] **Step 4: 数据新鲜度预检（全品种）**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
python -m data.cli status ss ur sr jd rb fu fg sp ma ta
```

预期: 所有品种无 stale 警告。若 stale，先补采：
```bash
python scripts/collect_1h.py ss ur sr jd rb fu fg sp ma ta
```

- [ ] **Step 5: 协变量完整性预检**

确认 sar_dist 在各品种数据上不会 NaN 断档：
```bash
python -c "
from data.data_store import DataStore
from cascade.features import calc_sar_distance, _calc_atr
for sym in ['ss','sr','jd','rb','fu','fg','sp','ma','ta']:
    df = DataStore(sym).get_main_contract_1h(limit=99999)
    atr = _calc_atr(df)
    sd = calc_sar_distance(df, atr)
    nan_pct = np.isnan(sd).mean()
    print(f'{sym}: len={len(df)}, sar_dist NaN%={nan_pct:.1%}')
"
```
预期: NaN% < 5%。若某品种 NaN% > 20%，说明 Parabolic SAR 在该品种数据上初始化失败，需在裁决时注明。

- [ ] **Step 6: 提交脚本**

```bash
git add scripts/batch_[a-e]_cov_gap.sh scripts/_kill_cov_gap.ps1
git commit -m "feat(batch): 协变量空白补测链式脚本 + 杀手脚本"
```

---

### Task 2: 批次 A — 固化验证 + sar_dist 孤立对照 + UR 增强

**Files:**
- 产出: `reports/data_ops/batch_a_progress.jsonl`
- 产出: `reports/data_ops/batch_a.log`
- 产出: `reports/monthly_backtest/20260818_*_monthly_report.md` (×4)

- [ ] **Step 1: 启动批次 A**

```bash
cd D:/FlyBuddy/FM_a
chmod +x scripts/batch_a_cov_gap.sh
nohup bash scripts/batch_a_cov_gap.sh > /dev/null 2>&1 & disown
```

- [ ] **Step 2: 并发唯一性断言（~8s 后）**

```bash
sleep 8 && powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object CommandLine -match 'monthly_backtest').Count"
```

期望: 2（1 venv launcher + 1 SDK python）。若更多 → `_kill_cov_gap.ps1` 终止后重启。

- [ ] **Step 3: 等待批次 A 完成**

巡检进度：
```bash
wc -l reports/data_ops/batch_a_progress.jsonl   # 期望 4 = 全部完成
tail -5 reports/data_ops/batch_a.log             # 看最新状态
```

预估耗时: ~3h (4 × 40-50min)

- [ ] **Step 4: 收集批次 A 结果 + 更新 backtest_registry**

从 `batch_a_progress.jsonl` 和各 `monthly_report.md` 提取结果，追加到 `docs/backtest_registry.md`。
按 v2 判定标准（相对基线）逐条判定。

关键对比:
- A1 (SS reversal_shadow): 与 SS 当前 baseline (PF=1.15, EV_r=+0.068) 对比 → 验证固化方案
- A2 (SR sar_dist 单独): 与 SR baseline (PF=1.10, DirAcc=55%) 对比 → sar_dist 孤立价值
- A3 (UR ao_accel+oi): 与 UR baseline (PF=0.84) 对比
- A4 (UR ao_accel+reversal_shadow): 与 UR baseline 对比

---

### Task 3: 批次 B — sar_dist 组合扫描

**前置条件:** 批次 A 完成（或至少 A2 结果已出，判断 sar_dist 是否有孤立价值）

- [ ] **Step 1: 启动批次 B**

```bash
chmod +x scripts/batch_b_cov_gap.sh
nohup bash scripts/batch_b_cov_gap.sh > /dev/null 2>&1 & disown
```

- [ ] **Step 2: 并发唯一性断言**

同 Task 2 Step 2。

- [ ] **Step 3: 等待完成 + 收集结果**

预估耗时: ~2.5h

关键对比:
- B1 (SS rsi_state+sar_dist): vs SS baseline (reversal_shadow)，差两个变量，不可归因
- B2 (SR rsi_state+sar_dist): vs SR baseline (rsi_state+oi+calendar)，差 sar_dist vs oi+calendar
- B3 (JD rsi_state+sar_dist): vs JD baseline (rsi_state+oi)，差 sar_dist 替换 oi → 部分可归因

**门控决策点**: 如果 A2 + B1-B3 全部 FAIL → sar_dist 在 rsi_state 体系下无价值，批次 C 仍继续（ha_body 体系是正交维度），但裁决报告中降低 sar_dist 整体权重。

---

### Task 4: 批次 C — ha_body + sar_dist 正交增强

**前置条件:** 批次 B 完成

- [ ] **Step 1: 启动批次 C**

```bash
chmod +x scripts/batch_c_cov_gap.sh
nohup bash scripts/batch_c_cov_gap.sh > /dev/null 2>&1 & disown
```

- [ ] **Step 2: 并发唯一性断言 + 等待完成 + 收集结果**

预估耗时: ~2.5h

关键对比（**干净归因** — baseline 都是 ha_body 单独，combo 只加 sar_dist）:
- C1 (RB): vs RB baseline (ha_body, PF=1.00)
- C2 (FU): vs FU baseline (ha_body, PF=0.95)
- C3 (FG): vs FG baseline (ha_body, PF=0.91)

---

### Task 5: 批次 D — 测试不足品种补测

- [ ] **Step 1: 数据预检**

```bash
python -m data.cli status sp ma
```

- [ ] **Step 2: 启动批次 D**

```bash
chmod +x scripts/batch_d_cov_gap.sh
nohup bash scripts/batch_d_cov_gap.sh > /dev/null 2>&1 & disown
```

- [ ] **Step 3: 并发唯一性断言 + 等待完成 + 收集结果**

预估耗时: ~2h

关键对比:
- D1 (SP ha_body): vs SP baseline (ha_body+calendar) → **消融**：calendar 贡献
- D2 (SP rsi_state+oi): vs SP baseline → 完全不同的协变量体系
- D3 (MA sar_dist+hourly_slope): vs MA baseline (hourly_slope+oi) → 混杂 "移除 oi" 效应

---

### Task 6: 批次 E — 补充探索

- [ ] **Step 1: 数据预检**

```bash
python -m data.cli status ss ur ta
```

- [ ] **Step 2: 启动批次 E**

```bash
chmod +x scripts/batch_e_cov_gap.sh
nohup bash scripts/batch_e_cov_gap.sh > /dev/null 2>&1 & disown
```

- [ ] **Step 3: 并发唯一性断言 + 等待完成 + 收集结果**

预估耗时: ~2.5h

关键对比:
- E1 (SS reversal_shadow+calendar): vs SS baseline (reversal_shadow) → calendar 边际贡献
- E2 (UR hourly_slope+reversal_shadow): vs UR baseline (ao_accel) → 跨体系迁移
- E3 (TA ha_body+ao_accel): vs TA baseline (ha_body, PF=0.99) → 边界品种改善

---

### Task 7: 综合裁决

**Files:**
- 产出: `reports/research/20260818_covariate_gap_verdict.md`
- 修改: `config/prediction_scheme.py`（仅当有 GREEN-EV PASS 时）
- 修改: `docs/backtest_registry.md`

- [ ] **Step 1: 汇总全部 16 次回测结果**

构建完整对比表，格式：

| 标签 | 品种 | 测试组合 | baseline PF | 测试 PF | PF Δ% | baseline EV | 测试 EV | EV Δ% | MaxDD Δ% | 判定 |
|------|------|----------|:-----------:|:-------:|:-----:|:-----------:|:-------:|:-----:|:--------:|:----:|
| A1 | SS | reversal_shadow | 1.15 | ? | ? | +0.068 | ? | ? | ? | GREEN/FAIL |
| ... | | | | | | | | | | |

- [ ] **Step 2: v2 verdict 判定（严格按统一口径）**

对每一行计算：
1. PF 相对变化 = (test_PF - baseline_PF) / baseline_PF
2. EV 相对变化 = (test_EV - baseline_EV) / abs(baseline_EV)（若 baseline_EV=0 则只看绝对值）
3. MaxDD 变化 = (|test_MaxDD| - |baseline_MaxDD|) / |baseline_MaxDD|
4. 应用判定规则：GREEN-EV / GREEN-MAXDD / FAIL

- [ ] **Step 3: sar_dist 专项结论**

按归因层级分别结论：
- A2 (孤立): sar_dist 单独 vs SR baseline
- C1-C3 (干净): sar_dist 作为 ha_body 辅助
- B1-B3 (混杂): 仅作参考
- 综合: sar_dist 在哪个体系下有/无价值

- [ ] **Step 4: 撰写裁决报告**

`reports/research/20260818_covariate_gap_verdict.md` 包含：
1. 完整结果表（带 baseline 列）
2. sar_dist 分层结论
3. 多重比较说明（16 次测试，α=0.05 预期 ~1 个假 PASS；PASS 品种需满足绝对地板才固化）
4. 每个 GREEN-EV/GREEN-MAXDD 品种的固化建议
5. 下一个优化方向建议
6. 其余 10 个品种不补测的原因

- [ ] **Step 5: 固化 PASS 品种（如有）**

仅固化 GREEN-EV（非 GREEN-MAXDD）的品种。
更新 `config/prediction_scheme.py` 中对应品种的 `covariate_type` / `covariate_types`。

- [ ] **Step 6: 提交**

```bash
git add docs/backtest_registry.md reports/research/20260818_covariate_gap_verdict.md
# 仅当有固化时:
git add config/prediction_scheme.py
git commit -m "feat(covariate-gap): 协变量空白补测 16 次回测 + v2 裁决"
```

---

## 执行节奏

| 天 | 时段 | 批次 | 预估耗时 | 备注 |
|:--:|:----:|:----:|:--------:|------|
| 1 | 上午 | Task 1 准备 | ~1h | 脚本+数据预检+提交 |
| 1 | 中午 | 批次 A 启动 | nohup 脱机 | 4 回测 ~3h |
| 1 | 下午 | 收 A 结果 | ~30min | 更新 registry |
| 1 | 下午 | 批次 B 启动 | nohup 脱机 | 3 回测 ~2.5h |
| 2 | 上午 | 收 B 结果 + 门控决策 | ~30min | sar_dist 方向判断 |
| 2 | 上午 | 批次 C 启动 | nohup 脱机 | 3 回测 ~2.5h |
| 2 | 下午 | 收 C 结果 | ~30min | |
| 2 | 下午 | 批次 D 启动 | nohup 脱机 | 3 回测 ~2h |
| 3 | 上午 | 收 D 结果 | ~30min | |
| 3 | 上午 | 批次 E 启动 | nohup 脱机 | 3 回测 ~2.5h |
| 3 | 下午 | 收 E 结果 + 裁决 | ~1h | 汇总+固化+提交 |

**总计: 16 次回测 ~13h + 准备/裁决 ~2.5h，3 天完成。**

## 风险预案

1. **sar_dist 全 FAIL (A2+C1-C3)**: "sar_dist 作为独立或 ha_body 辅助无价值"，从候选池移除。有价值的负结论。
2. **sar_dist A2 FAIL 但 C1-C3 部分 PASS**: "sar_dist 在 rsi_state 体系无用，但与 ha_body 搭配有边际价值"，仅固化 ha_body+sar_dist 的组合。
3. **SS reversal_shadow 验证 FAIL (A1)**: 当前固化方案在新口径下退化。需从 E1 (rev+calendar) 或 B1 (rsi_state+sar_dist) 中选择替代方案。暂不固化。
4. **数据 stale**: 每个批次启动前预检。stale 则先补采再启动。
5. **CPU 时间不足**: 至少完成 A+B+C（10 回测 ~8h）。D+E 为可选扩展。
6. **多重比较假 PASS**: 16 次测试按 α=0.05 预期 ~1 个假阳性。所有 PASS 必须同时满足绝对地板（PF≥1.0 且 EV>0）才固化，这是最强保护。裁决报告中注明此限制。
