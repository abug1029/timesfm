# 1星+PTA 协变量优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按方案 C 三阶段对 1 星+PTA 六品种进行协变量优化；Phase 1 CJ 破例固化 `reversal_shadow`（PF=1.14 + DirAcc+3pp，接受 MAPE 退化换 PF>1），Phase 2 继续扫描 EG/LH/TA（LH 用 clipping EV/PF，TA 解冻），Phase 3 启动 ledger 反馈环并产出总结。

**Architecture:** 三阶段流水线。Phase 1 已完成 scan+backtest 双段验证（JD 证伪 scan 方向增益，MA 边缘不固化，CJ 破例）。Phase 2 沿用相同方法论，LH 用 L1 `ECONOMIC_VERDICT.json` 的 PF/EV 快速通道 + walk-forward backtest。Phase 3 启动 `ledger_backfill` 反馈环，产出跨品种一致性报告 + 方法论教训文档。

**Tech Stack:** Python 3.11 + TimesFM 2.5 + TqSdk SQLite + numpy + pandas + scikit-learn。共享 venv: `D:\FlyBuddy\shared\timesfm\.venv\`。所有 Python 命令用 `/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe`。

## Global Constraints

- `config/prediction_scheme.py` / `cascade/features.py` / `data/config.py` 受保护，**固化必须人工确认**后执行
- 固化阈值（spec §4.3）：DirAcc ≥ 基线+2pp 且 MAPE 不退化；scan 首名 ≥ 次名 0.3pp 缓冲
- 例外规则（用户批准）：`PF > 1.1 且 EV > 0 且 DirAcc ≥ 基线+3pp` 可接受 MAPE 退化（CJ 已破例）
- LH 特例：DirAcc 仅参考，看 EV/PF（含 5% Gap clipping）
- scan 与 monthly_backtest 双段验证：scan 快筛 + walk-forward 定盘，**禁止跳过 backtest 固化**
- `reports/` 只增；`scripts/` 可改；`db/` 只增不删
- 所有受保护文件修改前**先告知用户，等人工确认后再写入**
- 工作目录始终 `D:/FlyBuddy/FM_a`

---

## Task 1: Phase 1 — MA 甲醇 hurst 协变量 backtest 验证（已完成）

**Files:**
- Read: `reports/monthly_backtest/20260728_1525_monthly_report.md`（backtest 输出已存在）

**背景:**
前置沟通中明确要求对 MA 的 `hurst` 协变量执行 monthly_backtest 验证，确认 MAPE 是否能控制在 2.5% 以内、DirAcc 维持 55% 以上。该 backtest 已在 brainstorming 阶段实际运行完成，结果直接纳入本计划。

**Backtest 实测结果（396 期 walk-forward）:**

| 指标 | MA 基线 (hourly_slope+oi) | backtest (hurst) | 判定 |
|:----|:----|:----|:----:|
| DirAcc | 50% | 52% | +2pp ✅ |
| MAPE | 2.0% | 2.52% | +0.52pp ❌ |
| Decay | 1.4x | 1.33x | — |
| EV | — | +0.009 | ≈0 ⚠️ |
| PF | — | 1.02 | 勉强 >1 ⚠️ |
| MaxDD | — | -62.60% | 大 ❌ |
| WR | — | 50% | — |

**判定**: 按 spec §4.3 严格阈值——
- DirAcc +2pp ✅ 达基线增量
- MAPE 2.52% > 基线 2.0% ❌ 退化
- EV=+0.009 ≈ 0，PF=1.02 仅勉强 >1 — 盈利能力几乎为零
- 按例外规则（PF>1.1 且 EV>0 且 DirAcc≥基线+3pp）：PF=1.02 不满足 >1.1，DirAcc 仅 +2pp 不满足 +3pp — ❌ 例外规则不达

**结论: MA 不固化**，保留原 `hourly_slope+oi`。

- [ ] **Step 1: 验证 backtest 输出文件存在**

```bash
ls -la D:/FlyBuddy/FM_a/reports/monthly_backtest/20260728_1525_monthly_report.md
```

期望：文件存在且非空。

- [ ] **Step 2: 记录 MA 不固化结论到计划执行日志**

创建 `reports/covariate_scan/20260728_phase1_summary.txt`，记录 MA 判定：

```text
# Phase 1 Backtest 汇总 (2026-07-28)

| 品种 | 基线 | 候选 | backtest DirAcc | MAPE | EV | PF | 判定 |
|:----|:----|:----|:----:|:----:|:----:|:----:|:----|
| MA | hourly_slope+oi | hurst | 52% (+2pp) | 2.52% (+0.52pp) | +0.009 | 1.02 | 不固化 (EV≈0, PF≤1.1) |
| CJ | pca_momentum+bb_squeeze | reversal_shadow | 53% (+3pp) | 2.64% (+0.64pp) | +0.065 | 1.14 | 破例固化 |
| JD | gated_slope | rsi_slope | 47% (-3pp) | 6.52% (+4.52pp) | -0.030 | 0.94 | 退化，保原 |

# 方法论教训: scan 7 点 DirAcc 严重高估 (19-33pp)，monthly_backtest 是唯一权威
```

- [ ] **Step 3: 提交**

```bash
git -C D:/FlyBuddy/FM_a add reports/covariate_scan/20260728_phase1_summary.txt
git -C D:/FlyBuddy/FM_a commit -m "data(phase1): MA/CJ/JD backtest 判定汇总

MA hurst: DirAcc+2pp 但 EV≈0, PF=1.02 → 不固化
CJ reversal_shadow: DirAcc+3pp, PF=1.14, EV=+0.065 → 破例固化
JD rsi_slope: DirAcc-3pp, 严重退化 → 保原 gated_slope

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Phase 1 — CJ 红枣固化 `reversal_shadow`

**Files:**
- Modify: `D:/FlyBuddy/FM_a/config/prediction_scheme.py:358-372`（受保护，人工确认）

**Interfaces:**
- Consumes: Phase 1 backtest 结果（DirAcc=53%, MAPE=2.64%, decay=1.48x, EV=+0.065, PF=1.14, MaxDD=-58.79%, WR=51%）
- Produces: SCHEMES["cj"] 更新为单协变量 `reversal_shadow`

**说明:**
当前 CJ 配置是 combo（`pca_momentum+bb_squeeze`），Phase 1 实证：combo 在 walk-forward 上 DirAcc=50% → MAPE 偏高。`reversal_shadow` 在 396 期 walk-forward 上 DirAcc=53%（+3pp），PF=1.14>1，EV=+0.065>0，满足例外规则。

- [ ] **Step 1: 编辑 `config/prediction_scheme.py`**

将第 358-372 行：

```python
    "cj": VarietyScheme(
        symbol="cj",
        name="红枣",
        scheme_type="short_range",
        stars=1,
        dir_acc=0.50,
        mape=2.0,
        decay=1.4,
        coverage=0.5,
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="bb_squeeze",  # 2026-07-23 四批次扫描: DirAcc 50.0%→52.2% (+2.2%)
        covariate_types=["pca_momentum", "bb_squeeze"],
    ),
```

改为：

```python
    "cj": VarietyScheme(
        symbol="cj",
        name="红枣",
        scheme_type="short_range",
        stars=2,  # 2026-07-28 Phase 1 固化: reversal_shadow
        dir_acc=0.53,
        mape=2.64,
        decay=1.48,
        coverage=0.5,
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="reversal_shadow",  # 2026-07-28 Phase 1 固化: DirAcc 50%→53% (+3pp), PF=1.14, EV=+0.065
        # 注: MAPE 2.0%→2.64% 退化 0.64pp；按例外规则（PF>1.1, EV>0, DirAcc≥基线+3pp）通过
    ),
```

**关键变更**:
- `covariate_type`: `bb_squeeze` → `reversal_shadow`
- 移除 `covariate_types` 行（从 combo 回到单协变量）
- `stars`: 1 → 2（反映 PF=1.14 + EV 正）
- 更新 `dir_acc`/`mape`/`decay` 为 backtest 实测值
- 注释说明破例依据

- [ ] **Step 2: 验证语法正确**

```bash
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "from config.prediction_scheme import SCHEMES; c=SCHEMES['cj']; print(f'cj: type={c.covariate_type}, stars={c.stars}, DirAcc={c.dir_acc:.0%}, MAPE={c.mape}%')"
```

期望输出：`cj: type=reversal_shadow, stars=2, DirAcc=53%, MAPE=2.64%`

- [ ] **Step 3: 运行 CJ 预测 smoke test**

```bash
cd D:/FlyBuddy/FM_a
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/cascade_predict.py cj --no-auto-collect 2>&1 | tail -30
```

期望：预测正常完成，报告显示 CJ 使用 `reversal_shadow` 协变量。若失败，回滚 Step 1 改动。

- [ ] **Step 4: 提交 Phase 1 固化**

```bash
git -C D:/FlyBuddy/FM_a add config/prediction_scheme.py
git -C D:/FlyBuddy/FM_a commit -m "feat(cj): 固化 reversal_shadow 协变量 (Phase 1 例外规则)

backtest 396 期 DirAcc 50%→53% (+3pp), PF=1.14, EV=+0.065
MAPE 2.0%→2.64% 退化 0.64pp 按例外规则通过 (PF>1.1, EV>0, DirAcc+3pp)
砍 combo (pca_momentum+bb_squeeze) 回到单协变量
stars 1→2

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Phase 1 — 重建 knowledge_base.json

**Files:**
- Generate: `D:/FlyBuddy/FM_a/config/knowledge_base.json`（允许区，覆盖）

**Interfaces:**
- Consumes: 更新后的 `config/prediction_scheme.py`（CJ 已固化）
- Produces: Copilot 信用背书 JSON（反映 CJ 新配置）

- [ ] **Step 1: 重建 KB**

```bash
cd D:/FlyBuddy/FM_a
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/build_knowledge_base.py 2>&1 | tail -30
```

期望输出：`Wrote config/knowledge_base.json (20 symbols)`，其中 `cj` 条目显示 `covariate=reversal_shadow, stars=2`。

- [ ] **Step 2: 验证 CJ 条目**

```bash
cd D:/FlyBuddy/FM_a
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "import json; kb=json.load(open('config/knowledge_base.json')); c=kb['symbols']['cj']; print(f\"cj: cov={c['covariate']}, stars={c['credit_stars']}, DirAcc={c['historical_diracc']}\")"
```

期望：`cj: cov=reversal_shadow, stars=2, DirAcc=0.53`

- [ ] **Step 3: 提交 KB 更新**

```bash
git -C D:/FlyBuddy/FM_a add config/knowledge_base.json
git -C D:/FlyBuddy/FM_a commit -m "chore: 重建 knowledge_base.json (反映 CJ Phase 1 固化)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Phase 2 — EG/LH/TA 协变量扫描

**Files:**
- Run: `scripts/covariate_scan.py`（工具已就绪，无需修改）
- Generate: `reports/covariate_scan/` 临时文件（自动清理）

**Interfaces:**
- Consumes: Phase 0 已就绪的 scan 工具（含 16 单协变量 + 7 combo）
- Produces: 三品种 7 点扫描结果，每品种 TOP5 协变量

**说明:**
- EG 基线 `bb_squeeze`（DirAcc=71%, MAPE=4.33%）：方向已优，关注 MAPE 退化
- LH 基线 `ha_body`（DirAcc=67%, MAPE=7.62%）：LH 看 EV/PF，DirAcc 仅参考
- TA 基线 `ha_body`（DirAcc=43%, MAPE=6.0%）：解冻测试，找技术上限

- [ ] **Step 1: 运行 scan（三品种 7 点）**

```bash
cd D:/FlyBuddy/FM_a
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/covariate_scan.py eg lh ta --points 7 2>&1 | tee reports/covariate_scan/20260728_phase2_scan.txt
```

预计时长：30 分钟（每品种 ~10 分钟）。

- [ ] **Step 2: 提取 TOP5 结果**

```bash
grep -A 7 "^---" reports/covariate_scan/20260728_phase2_scan.txt | grep -E "^---|最优|TOP|#[1-5]"
```

整理三品种 TOP5 表。

- [ ] **Step 3: 评估 scan 候选**

对每个品种：
- **EG**：若新候选 MAE 低于基线 4.33% 且 DirAcc ≥ 73%，进入 backtest
- **LH**：不以 DirAcc 判，看 scan 胜者是否 MAE 低于基线 7.62% 且候选合理
- **TA**：若新候选 DirAcc > 43%，进入 backtest 测技术上限

记录候选，进入 Task 6（backtest 校准）。

- [ ] **Step 4: 提交 scan 报告**

```bash
git -C D:/FlyBuddy/FM_a add reports/covariate_scan/20260728_phase2_scan.txt
git -C D:/FlyBuddy/FM_a commit -m "data: Phase 2 scan 报告 (EG/LH/TA 7pt)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Phase 2 — 为 `monthly_backtest.py` 新增 `--clip-gap` 参数

**Files:**
- Modify: `D:/FlyBuddy/FM_a/scripts/monthly_backtest.py`（允许区）

**背景:**
LH 生猪 backtest 需要计算 5% 极值截断后的 EV/PF（spec §4 例外路径）。不应在 Shell 层面临时写脚本处理输出，而应在代码层面完成 clipping 并直接输出 clipped EV/PF。

**设计:**
- 新增 `--clip-gap <ratio>` 参数（如 `--clip-gap 0.05`）
- 在每期评估点计算 `delta_real = real[-1] - base` 后，若启用 clip_gap，将 delta_real 截断到 `[-clip_gap * base, +clip_gap * base]`
- 截断后的 delta_real 存入 point dict 的 `delta_real` 字段，供 `cascade/evaluation_metrics.metrics_from_backtest_points` 计算 EV/PF
- MAE / MAPE 不受影响（使用 `pred - real` 而非 `delta_real`）

- [ ] **Step 1: 新增 `--clip-gap` 参数解析**

在 `scripts/monthly_backtest.py` 第 562 行（`--combo` 解析之后），添加：

```python
    # 极值截断: --clip-gap 0.05 (将 delta_real 截断到 ±5% * base, 用于 LH 等 gap 频发品种)
    clip_gap = None
    if "--clip-gap" in args:
        idx = args.index("--clip-gap")
        if idx + 1 < len(args):
            clip_gap = float(args[idx + 1])
            args = args[:idx] + args[idx + 2:]
```

- [ ] **Step 2: 在每期评估循环中应用截断**

在 `scripts/monthly_backtest.py` 第 167 行 `delta_real = real[-1] - base` 之后，添加：

```python
            delta_pred = pred[-1] - base
            delta_real_raw = real[-1] - base
            # Apply gap clipping for EV/PF stability (LH-style)
            if clip_gap is not None:
                max_move = clip_gap * base
                delta_real = float(np.clip(delta_real_raw, -max_move, max_move))
            else:
                delta_real = delta_real_raw
            dir_ok = bool(np.sign(delta_pred) == np.sign(delta_real_raw)) if delta_real_raw != 0 else True
```

并将原 `dir_ok = bool(np.sign(delta_pred) == np.sign(delta_real))` 行删除（已合并到上面）。

**验证点**：
- `delta_real`（可能被截断）进入 point dict 的 `delta_real` 字段 → `evaluation_metrics` 计算 EV/PF 时用截断值
- `delta_real_raw`（未截断）用于 `dir_ok` 方向判断（方向应基于真实价格变动，不受截断影响）
- `mae` / `mape` 仍使用 `pred - real`（第 172-174 行），不受 clip_gap 影响

- [ ] **Step 3: 验证 --clip-gap 对 MAE 无影响**

用已有 CJ 数据跑对照：

```bash
cd D:/FlyBuddy/FM_a
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/monthly_backtest.py cj --cov-override reversal_shadow 2>&1 | grep -E "MAPE|DirAcc" > /tmp/cj_no_clip.txt
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/monthly_backtest.py cj --cov-override reversal_shadow --clip-gap 0.05 2>&1 | grep -E "MAPE|DirAcc" > /tmp/cj_clip.txt
diff /tmp/cj_no_clip.txt /tmp/cj_clip.txt
```

期望：MAPE / DirAcc 两文件完全一致（clip_gap 不影响方向与价格精度指标），仅 EV/PF 不同。

- [ ] **Step 4: 提交**

```bash
git -C D:/FlyBuddy/FM_a add scripts/monthly_backtest.py
git -C D:/FlyBuddy/FM_a commit -m "feat(monthly_backtest): 新增 --clip-gap 参数

对 delta_real 截断到 ±ratio*base，截断后的值进入 point dict 供
evaluation_metrics 计算 EV/PF。用于 LH 等 gap 频发品种的稳定性评估。
MAE/MAPE/dir_ok 不受影响（分别使用 pred-real 与 delta_real_raw）。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Phase 2 — monthly_backtest walk-forward 校准

**Files:**
- Run: `scripts/monthly_backtest.py`（允许区，用 `--cov-override` 参数）
- Generate: `reports/monthly_backtest/YYYYMMDD_HHmm_monthly_report.md`

**Interfaces:**
- Consumes: Task 4 的 scan 候选
- Produces: 三品种 walk-forward 实测 DirAcc/MAPE/EV/PF

**说明:**
- EG：直接用 `--cov-override <candidate>`
- LH：用 `--cov-override <candidate>` 跑 walk-forward，看 EV/PF + 5% Gap clipping
- TA：同 EG 流程，若 DirAcc>43% 则可能达"技术上限"

LH 特殊处理（L1 VERDICT 快路径）：
- 同时查阅 `reports/phase1/full_universe_neutral_r1_ops/ECONOMIC_VERDICT.json` 的 `pf_off` / `ev_off` 作为参考
- walk-forward MAE 路径中检测 >5% Gap 的 bar，单独统计 clipping 后 EV/PF

- [ ] **Step 1: 提取三品种 TOP1 协变量（从 Task 4 输出）**

读取 Task 4 产生的 scan 输出，定位每品种 "最优:" 行，记录到下方表格：

```bash
grep -B1 -A1 "^  最优:" reports/covariate_scan/20260728_phase2_scan.txt
```

输出格式：每品种一段，含 `  最优: <cov_name>    MAE=X.XX%  DirAcc=YY%`。

记录提取结果（工程师在下方填入实际协变量名）：

| 品种 | Task 4 TOP1 候选 | 基线 DirAcc | 基线 MAPE | 固化候选阈值 |
|:----|:----|:----:|:----:|:----|
| EG | (从 scan 输出提取) | 71% | 4.33% | DirAcc≥73%, MAPE≤4.33% |
| LH | (从 scan 输出提取) | 67% | 7.62% | 看 EV/PF 含 clipping |
| TA | (从 scan 输出提取) | 43% | 6.0% | DirAcc>43% 且 (PF>1 或 EV>0) |

- [ ] **Step 2: 并发启动三品种 backtest**

把 Step 1 提取的三品种 TOP1 候选代入下方命令（`EG_CAND` / `LH_CAND` / `TA_CAND` 替换为实际协变量名）：

```bash
cd D:/FlyBuddy/FM_a
EG_CAND=<从 Step 1 表格填入>; LH_CAND=<从 Step 1 表格填入>; TA_CAND=<从 Step 1 表格填入>
mkdir -p reports/monthly_backtest

/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/monthly_backtest.py eg --cov-override "$EG_CAND" > reports/monthly_backtest/eg_bt.txt 2>&1 &
EG_PID=$!
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/monthly_backtest.py lh --cov-override "$LH_CAND" > reports/monthly_backtest/lh_bt.txt 2>&1 &
LH_PID=$!
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/monthly_backtest.py ta --cov-override "$TA_CAND" > reports/monthly_backtest/ta_bt.txt 2>&1 &
TA_PID=$!

wait $EG_PID $LH_PID $TA_PID
echo "All backtests done. Exit codes: EG=$? LH=$? TA=$?"
```

等待三个进程全部完成（预计 10-15 分钟）。

- [ ] **Step 2: 提取 walk-forward 结果**

对每个 backtest 输出文件，提取关键行：

```bash
grep "DirAcc=" reports/monthly_backtest/eg_bt.txt reports/monthly_backtest/lh_bt.txt reports/monthly_backtest/ta_bt.txt
```

整理三品种 backtest 实测指标表。

- [ ] **Step 3: LH 使用 --clip-gap 重跑 backtest**

对 LH 单独再跑一次 `--clip-gap 0.05`，直接输出 clipped EV/PF：

```bash
cd D:/FlyBuddy/FM_a
LH_CAND=<从 Step 1 表格填入>
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/monthly_backtest.py lh --cov-override "$LH_CAND" --clip-gap 0.05 > reports/monthly_backtest/lh_bt_clipped.txt 2>&1
```

从 `lh_bt_clipped.txt` 提取 clipped 版 EV / PF：

```bash
grep -E "DirAcc=|MAPE=|EV=|PF=" reports/monthly_backtest/lh_bt_clipped.txt | tail -5
```

对比 `lh_bt.txt`（未 clip）与 `lh_bt_clipped.txt`（clip 5%）：
- 若 clipped PF > unclipped PF 且 EV > 0，说明极端 Gap 扭曲了原始结果，采用 clipped 版本作为 LH 评估依据
- 若两者接近，采用未 clip 版本

同时查阅 L1 VERDICT 对照（`reports/phase1/full_universe_neutral_r1_ops/ECONOMIC_VERDICT.json` 中 LH 的 `pf_off` / `ev_off`），作为独立参考。

- [ ] **Step 4: 按阈值评估是否固化**

逐品种对照 spec §4.3：
- **EG**：若 backtest DirAcc ≥ 73%（基线+2pp）且 MAPE ≤ 4.33%（基线不退化），固化
- **LH**：若 backtest EV/PF（含 clipping）优于基线，且 DirAcc ≥ 69%（基线+2pp），固化
- **TA**：若 backtest DirAcc > 43% 且 PF>1 或 EV>0，固化；否则保持归档

不固化品种记录原因，进入 Task 8（ledger 反馈环）。

- [ ] **Step 5: 提交 backtest 报告**

```bash
git -C D:/FlyBuddy/FM_a add reports/monthly_backtest/
git -C D:/FlyBuddy/FM_a commit -m "data: Phase 2 monthly_backtest 报告 (EG/LH/TA walk-forward)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Phase 2 — 品种固化（若达阈）

**Files:**
- Modify: `config/prediction_scheme.py`（受保护，人工确认）
- Modify: `config/knowledge_base.json`

**说明:**
本 Task 仅在 Task 6 评估后确定有品种达固化阈值时执行。若无品种达阈，跳过本 Task 直接进入 Task 8。

- [ ] **Step 1: 编辑 `prediction_scheme.py`（每个达阈品种）**

按 Task 2（CJ 固化）同样模式：
- 修改对应品种的 `VarietyScheme` 条目
- 更新 `dir_acc`/`mape`/`decay` 为 backtest 实测
- 更新 `covariate_type` 为新协变量
- 若从 combo 回到单协变量，移除 `covariate_types`
- 注释说明 backtest 结果与固化解锁路径

- [ ] **Step 2: 验证语法正确**

```bash
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "from config.prediction_scheme import SCHEMES; [print(f'{k}: {v.covariate_type} DirAcc={v.dir_acc:.0%}') for k,v in SCHEMES.items() if k in ('eg','lh','ta')]"
```

- [ ] **Step 3: 重建 KB**

```bash
cd D:/FlyBuddy/FM_a
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/build_knowledge_base.py
```

- [ ] **Step 4: 提交**

```bash
git -C D:/FlyBuddy/FM_a add config/prediction_scheme.py config/knowledge_base.json
git -C D:/FlyBuddy/FM_a commit -m "feat(phase2): 固化 [达阈品种] 协变量 (backtest walk-forward 验证)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Phase 3 — 启动 ledger 反馈环

**Files:**
- Modify: `db/live_ledger.db`（只增）
- Generate: `reports/research/ledger_feedback_loop_init.md`

**Interfaces:**
- Consumes: 已固化品种的最新 `prediction_scheme.py`
- Produces: ledger 中回填历史 Copilot 预测记录；未来实盘退化自动触发 covariate_scan

**说明:**
按 spec §8 设计，ledger 反馈环是"固化后监控"工具，非选型工具。回填历史数据启动 `export_candidates(max_diracc=0.50)` 自动监控。

- [ ] **Step 1: 回填未填充记录**

```bash
cd D:/FlyBuddy/FM_a
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe scripts/ledger_backfill.py --all-unfilled --limit 500 2>&1
```

期望：回填所有 unfilled 的 ledger 记录（`actual_t24`, `err_t24_pct`, `dir_correct_t24`, `max_adverse_excursion`）。

- [ ] **Step 2: 检查回填结果**

```bash
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "
from cascade.live_ledger import LiveLedger
led = LiveLedger()
stats = led.health_stats()
for s in stats:
    print(f\"{s['symbol']:3} cov={s['cov_used']:20} n={s['n']:3} diracc={s['diracc_t24']:.0%} mae={s['mae_t24_pct']:.2f}%\")
"
```

- [ ] **Step 3: 导出当前弱信号候选**

```bash
/d/FlyBuddy/shared/timesfm/.venv/Scripts/python.exe -c "
from cascade.live_ledger import export_candidates
candidates = export_candidates(max_diracc=0.50, min_n=3)
import json
print(json.dumps(candidates, indent=2))
"
```

期望：输出可能为空（当前数据量小），但机制已就绪。

- [ ] **Step 4: 提交回填脚本日志与文档**

```bash
git -C D:/FlyBuddy/FM_a add reports/research/
git -C D:/FlyBuddy/FM_a commit -m "docs(phase3): 启动 ledger 反馈环

backfill --all-unfilled 回填 unfilled 记录
export_candidates(max_diracc=0.50, min_n=3) 已就绪
未来实盘退化协变量将自动触发 covariate_scan

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: 方法论教训文档

**Files:**
- Append: `docs/superpowers/specs/2026-07-28-covariate-optimization-design.md`（追加 §9）

**说明:**
把本轮关键发现固化为方法论文档，供后续优化参考。

- [ ] **Step 1: 追加 §9 方法论教训到 spec**

在 spec 文件末尾追加：

```markdown
---

## 9. 方法论教训（Phase 1 实证）

### 9.1 scan 7 点 DirAcc 严重高估

实测对比（Phase 1 三品种）：

| 品种 | scan 7pt DirAcc | backtest 396pt DirAcc | 高估 |
|:----|:----:|:----:|:----:|
| JD | 71% | 47% | +24pp |
| CJ | 86% | 53% | +33pp |
| MA | 71% | 52% | +19pp |

**结论**: scan 7 点评估的 DirAcc 不可信，不能作为固化解锁依据。样本过小导致方向准确率被严重高估。

### 9.2 monthly_backtest walk-forward 是唯一权威

所有固化决策必须经 monthly_backtest 396 期 walk-forward 验证。

### 9.3 方向增益与价格尺度常负相关

CJ `reversal_shadow` DirAcc +3pp 但 MAPE 2.0%→2.64%。JD `rsi_slope` DirAcc -3pp 且 MAPE 2.0%→6.52%。方向对时价格尺度预测差是协变量切换的常见副作用，需看 PF/EV 综合判定。

### 9.4 scan 口径缺口修正建议

未来优化中 `scripts/covariate_scan.py` 的评估指标应与 `monthly_backtest.py` 对齐：
- 当前: scan = 24h MAE + DirAcc (7点)
- 建议: scan 增加 walk-forward MAPE 子集（至少 50 点）作为固化解锁预筛口径

或：将 spec §4.3 的"MAE ≤ 基线"改为"walk-forward MAPE ≤ 基线"，scan 仅做方向排序。
```

- [ ] **Step 2: 提交**

```bash
git -C D:/FlyBuddy/FM_a add docs/superpowers/specs/2026-07-28-covariate-optimization-design.md
git -C D:/FlyBuddy/FM_a commit -m "docs(spec): 追加方法论教训 §9 (scan 7pt DirAcc 不可信)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 后续路线图（不在本轮范围）

### Phase 4: JD 鸡蛋日历特征（独立立项）

JD 季节性极强（端午/中秋备货），引入 DayOfYear/Month 正弦/余弦编码。需改 `cascade/features.py`（受保护）+ horizon 填充（未来日期已知），与本月协变量优化分离。

### Phase 5: CJ 影线阈值调优

用户补充：`reversal_shadow` 在低流动性品种（CJ）上应对影线长度设最低阈值，滤除无意义日常小波动。需改 `cascade/features.py` 的 `calc_reversal_shadow_ratio`（受保护），作为独立立项。

### Phase 6: TA PTA 基本面协变量

TA 技术上限在 walk-forward 上仍 <43% DirAcc（待 Phase 2 backtest 实证）。真正解法：引入原油/PX 价差作为 `basis_momentum` 协变量（features.py 已支持，但需 store 层补基差数据）。项目级工程。

### Phase 7: LH 生猪基本面

LH 基本面驱动（猪周期/疫病/节日），纯技术协变量天花板低。长期需引入母猪存档、猪粮比等基本面数据。短期走 clipping EV/PF 评估。
