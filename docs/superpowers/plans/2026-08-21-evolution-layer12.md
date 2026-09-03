# FM_a 第一层+第二层演进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复风控基础 bug → 弱信号品种组合协变量测试 → SH 纳入 → dir_acc 刷新 → KB 重建，将 FM_a 从"12 品种优化完成"推进到"全品种覆盖+知识体系闭环"。

**Architecture:** Task 1 修复 monthly_backtest.py 的 MaxDD 计算逻辑，确保所有评估数据可信。Task 2 对 7 个弱信号品种进行多协变量组合回测（基于 Phase 11 单协结果选择 top-2/3 组合）。Task 3 在 SCHEMES 中添加 SH 方案。Task 4 刷新全品种 dir_acc。Task 5 从最新 SCHEMES 重建 knowledge_base.json。每个 Task 完成后有专家审核门禁。

**Tech Stack:** Python + TimesFM 2.5 (CPU-only) + monthly_backtest.py + _batch_lib.sh + prediction_scheme.py

**Spec:** 用户 2026-08-21 对话中确定的演进方向，第一层 (高 ROI) + 第二层 (中期架构)。

## Global Constraints

- `config/prediction_scheme.py` 是高风险路径, 修改后必须验证 import + 运行 `test_prediction_scheme_phase9.py`
- 所有回测使用 `monthly_backtest.py` 完整 walk-forward (396pt), 禁止 3pt/7pt scan
- 回测前必须获得用户批准
- 使用 nohup 启动长时回测, 不用 run_in_background
- `PYTHONIOENCODING=utf-8` 必须设置 (Windows GBK 崩溃防护)
- 含 `\Pu Chong\` 的路径用 `\PUCHON~1\` 替代
- 每个 Task 完成后必须专家审核, 审核通过后才进入下一个 Task

---

### Task 1: MaxDD>100% Bug 修复

**Files:**
- Modify: `scripts/monthly_backtest.py` (MaxDD 计算逻辑)
- Create: `tests/test_maxdd_calculation.py`
- Modify: `docs/backtest_registry.md` (标注受影响的品种)

**背景:**
JM -265% / FG -134% 的 MaxDD 值在数学上不合理（最大亏损不应超过初始资金）。bug 可能在 monthly_backtest.py 的累计收益计算中——可能是简单累加而非复合计算，或者止损逻辑缺失。

**Interfaces:**
- Consumes: monthly_backtest.py 的回测输出 (PF/EV/MaxDD)
- Produces: 修复后的 MaxDD 计算函数, 值域限制在 [-100%, 0%]

- [ ] **Step 1: 定位 bug 根因**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
# 复现 JM 的 -265% MaxDD
PYTHONIOENCODING=utf-8 python scripts/monthly_backtest.py jm 2>&1 | grep -i "maxdd\|max_dd\|drawdown"
```

阅读 `scripts/monthly_backtest.py` 中 MaxDD 的计算逻辑，确认是累加收益 vs 复合收益的问题，还是止损逻辑缺失。

- [ ] **Step 2: 编写测试用例**

创建 `tests/test_maxdd_calculation.py`:
```python
"""验证 MaxDD 计算不超过 -100%"""
import unittest

class TestMaxDDCalculation(unittest.TestCase):
    def test_maxdd_bounded(self):
        """MaxDD 必须在 [-100%, 0%] 范围内"""
        # 使用已知的 JM/FG 回测数据验证
        # 具体实现依赖 Step 1 的根因分析
        pass

    def test_maxdd_compound(self):
        """复合收益计算: 连续亏损 50% 两次 = -75%, 非 -100%"""
        # 验证公式: 1 - product(1 + r_i) 而非 sum(r_i)
        pass
```

- [ ] **Step 3: 修复 MaxDD 计算**

根据 Step 1 的根因，修改 `monthly_backtest.py` 中的 MaxDD 计算：
- 如果是累加问题：改为复合收益计算 `cumulative = product(1 + daily_return)`
- 如果是止损缺失：添加 -100% 硬止损（爆仓即停止）
- 如果是累积收益允许低于 -100%：添加 `max(returns, -1.0)` 截断

- [ ] **Step 4: 运行测试验证**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
PYTHONIOENCODING=utf-8 python -m pytest tests/test_maxdd_calculation.py -v
```

- [ ] **Step 5: 重新跑 JM/FG 验证修复效果**

```bash
PYTHONIOENCODING=utf-8 python scripts/monthly_backtest.py jm
PYTHONIOENCODING=utf-8 python scripts/monthly_backtest.py fg
```

确认 MaxDD 值在合理范围内（-100% ~ 0%）。

- [ ] **Step 6: 提交**

```bash
git add scripts/monthly_backtest.py tests/test_maxdd_calculation.py
git commit -m "fix: MaxDD>100% bug 修复 (JM -265%/FG -134% → 合理范围)"
```

- [ ] **🔒 审核门禁: 专家审核 MaxDD 修复**

审核要点:
1. 修复是否改变了 PF/EV 的计算（不应改变，只修 MaxDD）
2. 对已有 GREEN 品种的 MaxDD 值是否有影响
3. 测试用例覆盖是否充分
4. 是否需要重跑所有已固化品种的 baseline

审核通过 → 进入 Task 2
审核不通过 → 修复后重新审核

---

### Task 2: 弱信号品种组合协变量测试

**Files:**
- Create: `scripts/batch_weak_combo.sh` (组合回测批次脚本)
- Create: `reports/data_ops/batch_weak_combo_progress.jsonl` (运行时生成)
- Modify: `docs/backtest_registry.md` (追加组合测试结果)
- Modify: `config/prediction_scheme.py` (如有 GREEN 组合则固化)

**背景:**
7 个弱信号品种 (AO/BU/CF/FG/JM/MA/UR) 在 Phase 11 单协变量测试中全部 0 GREEN。但 M/P/SR 的基线对比已证明多协变量组合可以优于单 GREEN。需要对弱信号品种测试 top-2/3 协变量组合。

**组合选择策略 (基于 Phase 11 PF 排名):**

| 品种 | Top-1 | Top-2 | Top-3 | 测试组合 |
|:-----|:------|:------|:------|:---------|
| BU | cal(0.99) | hs(0.91) | rev(0.87) | cal+hs, cal+rev, hs+rev |
| JM | hs(0.90) | ha(0.87) | rsi(0.85) | hs+ha, hs+rsi, ha+rsi |
| MA | rsi(1.00) | oi(0.86) | cal(0.84) | rsi+oi, rsi+cal, oi+cal |
| UR | rsi(0.96) | hs(0.90) | cal(0.88) | rsi+hs, rsi+cal, hs+cal |
| FG | oi(0.93) | rev(0.91) | hs(0.90) | oi+rev, oi+hs, rev+hs |
| CF | rev(0.90) | rsi(0.89) | hs(0.88) | rev+rsi, rev+hs, rsi+hs |
| AO | rev(0.73) | hs(?) | rsi(?) | top-2 组合 (需确认数据) |

总计: ~21 个组合测试 (7 品种 × 3 组合), 预计 ~14h。

- [ ] **Step 1: 确认 Phase 11 各品种 top-3 协变量 PF 值**

从 JSONL 数据提取每个弱信号品种的 top-3 协变量：
```bash
cd D:/FlyBuddy/FM_a
PYTHONIOENCODING=utf-8 python -c "
import json, re
from collections import defaultdict
data = defaultdict(list)
for f in ['batch_f1_progress','batch_f2a_progress','batch_f2b_progress','batch_f2c_progress','batch_f3a_progress','batch_f3b_progress','batch_f3c_progress','batch_f4_progress']:
    with open(f'reports/data_ops/{f}.jsonl') as fh:
        for line in fh:
            d = json.loads(line.strip())
            pf = float(re.search(r'[0-9.]+', d['pf']).group())
            data[d['symbol']].append((d['combo'], pf))
for sym in ['bu','jm','ma','ur','fg','cf','ao']:
    top3 = sorted(data.get(sym, []), key=lambda x:-x[1])[:3]
    print(f'{sym}: {[(c, round(p,2)) for c,p in top3]}')
"
```

- [ ] **Step 2: 创建组合回测脚本**

创建 `scripts/batch_weak_combo.sh`，使用 `monthly_backtest.py --combo "cov1+cov2"` 测试每个组合：
```bash
#!/bin/bash
set -euo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONWARNINGS=ignore

cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate

JSONL="reports/data_ops/batch_weak_combo_progress.jsonl"
LOG="reports/data_ops/batch_weak_combo.log"

source scripts/_batch_lib.sh
: > "$LOG"
batch_init "batch_weak_combo"

echo "=== batch_weak_combo START $(date -Iseconds) ===" >> "$LOG"

# BU 组合
batch_run_one "bu" "calendar_cyclical+hourly_slope" "BU-cal+hs" "$JSONL" "$LOG"
batch_run_one "bu" "calendar_cyclical+reversal_shadow" "BU-cal+rev" "$JSONL" "$LOG"
batch_run_one "bu" "hourly_slope+reversal_shadow" "BU-hs+rev" "$JSONL" "$LOG"

# ... 其余品种类似 (Step 1 确认后填入)

echo "=== batch_weak_combo DONE $(date -Iseconds) ===" | tee -a "$LOG"
```

- [ ] **Step 3: 验证脚本语法**

```bash
bash -n scripts/batch_weak_combo.sh && echo "syntax OK"
```

- [ ] **Step 4: 启动回测 (需用户批准)**

```bash
nohup bash scripts/batch_weak_combo.sh > reports/data_ops/batch_weak_combo_nohup.log 2>&1 &
```

预计耗时: ~14h (21 tests × 40min)

- [ ] **Step 5: 监控完成并分析结果**

等待回测完成，从 JSONL 提取结果：
- GREEN 数量 / 品种
- 最佳组合 per 品种
- 与单协变量 best PF 的对比

- [ ] **Step 6: 更新 Registry**

为每个测试品种追加组合测试行到 `docs/backtest_registry.md`。

- [ ] **Step 7: 提交**

```bash
git add docs/backtest_registry.md reports/data_ops/batch_weak_combo_progress.jsonl scripts/batch_weak_combo.sh
git commit -m "feat: 弱信号品种组合协变量测试 (7 品种 × 3 组合)"
```

- [ ] **🔒 审核门禁: 专家审核组合测试结果**

审核要点:
1. 组合 GREEN 是否真实 (PF≥1.0 AND EV>0 AND MaxDD<80%)
2. 组合是否优于当前 baseline (如 JM 当前 ha_body PF=0.87)
3. 如果有 GREEN 组合, 是否需要基线对比确认
4. 固化决策是否正确

审核通过 → 如有固化则修改 prediction_scheme.py → 进入 Task 3
审核不通过 → 分析失败原因, 可能需要调整组合策略

---

### Task 3: SH 纳入 SCHEMES

**Files:**
- Modify: `config/prediction_scheme.py` (添加 SH 方案)
- Modify: `data/config.py` (确认 SH 已在 SYMBOL 列表中)
- Modify: `docs/backtest_registry.md` (更新 SH 状态)

**背景:**
SH (烧碱) 于 2026-07-27 加入品种池, Phase 11 测试 0 GREEN (best PF=0.90)。需要跑完整 baseline 回测确定 scheme 参数 (DirAcc/MAPE/decay/scheme_type), 然后加入 SCHEMES。

- [ ] **Step 1: 跑 SH 完整 baseline 回测**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
PYTHONIOENCODING=utf-8 python scripts/monthly_backtest.py sh
```

记录: DirAcc, MAPE, decay, coverage, PF, EV, MaxDD。

- [ ] **Step 2: 确定 SH scheme 参数**

根据 Step 1 结果:
- `scheme_type`: 根据走势判断 (trend/stable/oscillating)
- `stars`: 根据 PF/EV/MaxDD 判定 (GREEN→2星, BOUNDARY→1星, FAIL→1星)
- `dir_acc`: 从回测结果提取
- `mape`: 从回测结果提取
- `decay`: 从回测结果提取
- `covariate_type`: Phase 11 best (虽然 0 GREEN, 选 best PF 的协变量)

- [ ] **Step 3: 添加到 prediction_scheme.py**

```python
"sh": VarietyScheme(
    symbol="sh",
    name="烧碱",
    scheme_type="<Step 2 确定>",
    stars=<Step 2 确定>,
    dir_acc=<Step 1>,
    mape=<Step 1>,
    decay=<Step 1>,
    coverage=<Step 1>,
    use_full_signal=True,
    short_horizon_only=False,
    confidence_multiplier=1.0,
    covariate_type="<Phase 11 best>",
    covariate_types=["<Phase 11 best>"],
),
```

- [ ] **Step 4: 验证 import + 运行测试**

```bash
PYTHONIOENCODING=utf-8 python -c "from config.prediction_scheme import SCHEMES; print(SCHEMES['sh'])"
PYTHONIOENCODING=utf-8 python -m pytest tests/test_prediction_scheme_phase9.py -v
```

- [ ] **Step 5: 更新 Registry SH 段**

更新 SH 段标题为实际方案, 添加 baseline 行。

- [ ] **Step 6: 提交**

```bash
git add config/prediction_scheme.py docs/backtest_registry.md
git commit -m "feat: SH 烧碱纳入 SCHEMES (Phase 11 0 GREEN, baseline 确定 scheme)"
```

- [ ] **🔒 审核门禁: 专家审核 SH 方案**

审核要点:
1. scheme_type 是否合理 (对比走势特征)
2. stars 判定是否符合标准
3. covariate_type 是否为 Phase 11 best
4. test_prediction_scheme_phase9.py 是否通过

审核通过 → 进入 Task 4

---

### Task 4: dir_acc 全量刷新

**Files:**
- Modify: `config/prediction_scheme.py` (更新所有品种 dir_acc)
- Modify: `docs/backtest_registry.md` (标注刷新日期)

**背景:**
`dir_acc` 随 walk-forward 窗口漂移而 stale (见 memory/scheme-diracc-stale.md)。上次全量刷新是 2026-08-03, 之后 Phase 11 和基线对比又产生了更新鲜的数据。需要从 JSONL 和回测结果中提取最新 dir_acc 并写入 SCHEMES。

- [ ] **Step 1: 收集所有品种最新 dir_acc**

从以下数据源提取每个品种的最新 dir_acc:
- Phase 11 JSONL (batch_f[1-4]_progress.jsonl, batch_m_progress.jsonl)
- 基线对比 JSONL (batch_baseline*.jsonl)
- 此前已跑的回测结果

```bash
cd D:/FlyBuddy/FM_a
PYTHONIOENCODING=utf-8 python -c "
# 提取每个品种最新回测的 dir_acc
# 优先使用 baseline 对比数据, 其次 Phase 11 数据
import json, re
# ... (具体实现)
"
```

- [ ] **Step 2: 对比当前 scheme dir_acc vs 新鲜值**

```bash
PYTHONIOENCODING=utf-8 python -c "
from config.prediction_scheme import SCHEMES
for sym in sorted(SCHEMES.keys()):
    s = SCHEMES[sym]
    # 对比新鲜值 vs scheme.dir_acc
    # 标记偏差 > 3pp 的品种
"
```

- [ ] **Step 3: 更新 prediction_scheme.py**

对所有品种更新 `dir_acc` 为最新 walk-forward 值。

- [ ] **Step 4: 验证 + 运行测试**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_prediction_scheme_phase9.py -v
```

注意: 测试可能因 dir_acc 变化而 FAIL (快照不匹配), 需要更新测试快照。

- [ ] **Step 5: 提交**

```bash
git add config/prediction_scheme.py tests/
git commit -m "chore: dir_acc 全量刷新 (2026-08-21 窗口)"
```

- [ ] **🔒 审核门禁: 专家审核 dir_acc 刷新**

审核要点:
1. 每个品种的 dir_acc 变化幅度是否合理 (< 5pp)
2. 是否有品种 dir_acc 大幅变化需要关注
3. test_prediction_scheme_phase9.py 快照更新是否正确

审核通过 → 进入 Task 5

---

### Task 5: knowledge_base.json 重建

**Files:**
- Run: `scripts/build_knowledge_base.py` (自动重建)
- Modify: `knowledge_base.json` (自动生成)
- Modify: `docs/backtest_registry.md` (标注 KB 重建日期)

**背景:**
12 品种在 Phase 11 中固化了新协变量, SH 新纳入 SCHEMES, dir_acc 全量刷新 — 这些都影响 knowledge_base.json 的内容。KB 是 Copilot 信用背书的数据源, 必须与最新 SCHEMES 同步。

- [ ] **Step 1: 重建 KB**

```bash
cd D:/FlyBuddy/FM_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
PYTHONIOENCODING=utf-8 python scripts/build_knowledge_base.py
```

- [ ] **Step 2: 验证 KB 内容**

```bash
PYTHONIOENCODING=utf-8 python -c "
import json
with open('config/knowledge_base.json') as f:
    kb = json.load(f)
# 检查:
# 1. 所有 21 品种都在 KB 中
# 2. stars 与 SCHEMES 一致
# 3. covariate_type 与 SCHEMES 一致
# 4. L1_verdict 正确
"
```

- [ ] **Step 3: 验证 Copilot 可正常读取**

```bash
PYTHONIOENCODING=utf-8 python -c "
# 模拟 Copilot 读取 KB
import json
with open('config/knowledge_base.json') as f:
    kb = json.load(f)
print(f'品种数: {len(kb.get(\"schemes\", {}))}')
print(f'L1 entries: {len(kb.get(\"l1_verdicts\", {}))}')
"
```

- [ ] **Step 4: 提交**

```bash
git add config/knowledge_base.json
git commit -m "chore: knowledge_base.json 重建 (反映 Phase 11 + SH + dir_acc 刷新)"
```

- [ ] **🔒 审核门禁: 最终验收**

审核要点:
1. KB 品种数 = SCHEMES 品种数 (21)
2. 每品种 stars/covariate_type 与 SCHEMES 一致
3. Copilot 可正常启动并读取 KB
4. 所有文件变更已提交, 无遗漏

---

## 依赖关系图

```
Task 1 (MaxDD 修复)
  │
  ├──→ Task 2 (弱信号组合测试, ~14h)
  │      │
  │      └──→ [如有 GREEN] → 基线对比 → 固化
  │
  ├──→ Task 3 (SH 纳入, ~2h) ← 可与 Task 2 并行
  │
  └──→ Task 4 (dir_acc 刷新, ~1h) ← 需等 Task 2/3 固化完成
         │
         └──→ Task 5 (KB 重建, ~30min) ← 最后执行
```

## 总时间估算

| Task | 回测时间 | 人工时间 | 合计 |
|:-----|:--------:|:--------:|:----:|
| 1 MaxDD 修复 | - | 2h | 2h |
| 2 弱信号组合 | ~14h | 3h | 17h |
| 3 SH 纳入 | ~1h | 1h | 2h |
| 4 dir_acc 刷新 | - | 1h | 1h |
| 5 KB 重建 | - | 0.5h | 0.5h |
| 审核 (5 次) | - | 2.5h | 2.5h |
| **总计** | ~15h | ~10h | **~25h** |
