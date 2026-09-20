# SPEC: KB PF all null (schemes_snapshot_no_L1) 修复方案

**日期**: 2026-09-20
**状态**: PROPOSED
**优先级**: P2 — 功能降级但不阻塞核心探索
**影响范围**: `scripts/praxist_supervisor.py`, `scripts/build_knowledge_base.py`, `scripts/copilot.py`

---

## 1. 问题描述

Supervisor 每次启动/重载打印：
```
[degraded] KB PF all null (schemes_snapshot_no_L1): retest PF ratio gate denominator falls back to 1.0
```

`config/knowledge_base.json` 自 2026-09-17T17:45:35 起处于 `schemes_snapshot_no_L1` 降级模式，21 个品种 `historical_pf` / `historical_ev` / `historical_maxdd` 全为 `null`。

---

## 2. 根因分析

### 2.1 完整因果链

```
[根本] L1 全量回测产物（2026-07-25 生成，ECONOMIC_PASS=False, ΔEV≈-10.8）
       从未被 git 提交，后被清理
  ↓
[直接] reports/phase1/full_universe_neutral_r1_ops/ 目录不存在
       → ECONOMIC_VERDICT.json 缺失
  ↓
[构建] build_knowledge_base.py 走 else 分支（line 107-113）
       → mode = "schemes_snapshot_no_L1"
       → 所有品种 historical_pf/ev/maxdd = null
  ↓
[运行] praxist_supervisor.py 启动（line 117-122）
       → INCUMBENT_PF = {}（空字典）
       → 打印 degraded 警告
  ↓
[决策] _retest_candidates()（line 1221）
       → ratio = variant_pf / 1.0（代替 variant_pf / incumbent_pf）
       → 复测筛选语义失真
```

### 2.2 历史时间线

| 日期 | 事件 | 影响 |
|------|------|------|
| 2026-07-25 | L1 全量回测执行，ECONOMIC_PASS=False | vol-filter 在 ops 全量上伤害 EV，产物在 `reports/phase1/` |
| 2026-09-03 | 初始提交 `10dbeb3`，KB/脚本入仓 | `reports/` 已在 `.gitignore`，phase1 产物未版本化 |
| 2026-09-10 | SPEC-006 字段扩展 | KB 仍引用已消失的 L1 文件，开始用 `dir_acc * 2.0` **伪造 PF** |
| 2026-09-11 | KB 已有 `"warning": "missing ECONOMIC_VERDICT.json"` | 伪造链路维持表面运转 |
| **2026-09-17** | **commit `5951611`** | **显式拆除伪造链路，PF 改为 null，引入 degraded 模式** |
| 2026-09-20 | 本报告 | 调研根因、评估影响、提出方案 |

### 2.3 降级是有意设计，非 bug

commit `5951611` message:
> fix(kb): L1 缺失显式降级重建 KB + ss_vor 漏网之鱼处置
> 根除 dir_acc×2 伪造 PF 链路

代码注释和 KB `_meta` 均明确标注 `schemes_snapshot_no_L1` 为预期降级。无 TODO/FIXME 标记待修复。

---

## 3. 影响评估

### 3.1 功能影响矩阵

| 功能 | 代码位置 | 影响 | 严重度 |
|------|----------|------|--------|
| **近失误复测筛选** | `supervisor.py:1221` | PF ratio 分母=1.0，语义从「相对 incumbent 提升 5%」变为「绝对 PF > 1.05」 | 🟡 中 |
| **copilot 领航展示** | `copilot.py:259,336,548,628,663` | PF 显示为 N/A；DirAcc/stars/hold_period 正常 | 🟢 低 |
| **variety_analysis** | `variety_analysis.py:346-352` | 跳过历史信用行 | 🟢 低 |
| **核心慢环评估** | `aligned_slow_loop` | 不受影响 | ⚪ 无 |
| **快环预测** | Praxist task_FM | 不受影响 | ⚪ 无 |
| **目标达成判定** | `goal.yaml` success_condition | 不受影响（基于 DirAcc，非 PF） | ⚪ 无 |

### 3.2 复测筛选量化影响 — 双重阻塞，事实休眠

当前实际影响 **为零**，原因双重阻塞：

1. **INCUMBENT_PF 为空** → 分母 fallback 1.0
2. **v23 裁决无 PF 字段** → `aligned_verdicts.jsonl` 105 条记录 pf=null → `_retest_candidates()` 中 `float(v.get("pf") or 0.0)` 恒为 0.0 → `ratio = 0.0` → 不可能 > 1.05

即：即使修复 INCUMBENT_PF，复测筛选仍然不会产出候选（v23 评估器不计算 PF）。

**结论：PF ratio gate 当前事实休眠，无需紧急修复。**

### 3.3 KB 降级模式保留功能

| 保留 ✅ | 缺失 ❌ |
|---------|---------|
| credit_stars（来自 scheme.stars） | historical_pf / historical_ev / historical_maxdd |
| historical_diracc / mape / decay / coverage | vol_sensitivity（全 UNKNOWN） |
| best_hold_period / short_horizon_only | vol_l1_veto_rate / vol_l1_delta_ev |
| sector / covariate / scheme_type | — |
| slow_loop_* 字段（从 aligned_verdicts 同步） | — |

---

## 4. 解决方案

### 方案 A：重建 L1 数据管线（完整修复）

**触发条件**：当 PF ratio gate 被重新激活（如 v23 评估器开始输出 PF）时执行。

**步骤**：
```bash
cd /home/abug/timesfm

# S0: 准入扫描（~5 min）
python scripts/universe_eligibility.py
# 产出: reports/phase1/universe_eligibility.json

# S1: 全量 walk-forward 回测（3-6 小时）
python scripts/backtest_vol_gating_fullchain.py --universe l1
# 产出: reports/phase1/full_universe_neutral_r1_ops/by_symbol/{sym}.json

# L1: 经济判决（~1 min）
python scripts/l1_economic_verdict.py
# 产出: reports/phase1/.../ECONOMIC_VERDICT.json + .md

# KB: 重建知识库（~5 sec）
python scripts/build_knowledge_base.py
# 产出: config/knowledge_base.json (mode=l1_plus_schemes)
```

**注意事项**：
- 上次运行（2026-07-25）结果 ECONOMIC_PASS=False（ΔEV≈-10.8），vol-filter 在 ops 全量上伤害 EV
- 重跑可能仍然 FAIL → KB 会再次 degraded
- 需要 28 个 SQLite DB（`db/futures_*.db`），当前全部存在
- 需要 TimesFM 模型权重 + 充足 CPU/GPU 时间

**预期产物**：
- 若 PASS：KB 恢复完整 PF/EV/MaxDD，supervisor degraded 警告消失
- 若 FAIL：KB 仍 degraded，但 L1 文件存在（含 HURTS 标记），KB 可读取 L1 行数据

### 方案 B：创建管线自动化脚本（预防性）

**目标**：消除手动串联 S0→S1→L1→KB 的脆弱性。

```bash
#!/usr/bin/env bash
# scripts/rebuild_kb_pipeline.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/4] S0: universe eligibility scan..."
python scripts/universe_eligibility.py

echo "[2/4] S1: fullchain vol-gating backtest..."
python scripts/backtest_vol_gating_fullchain.py --universe l1

echo "[3/4] L1: economic verdict..."
python scripts/l1_economic_verdict.py

echo "[4/4] KB: rebuild knowledge base..."
python scripts/build_knowledge_base.py

echo "Done. Check config/knowledge_base.json _meta.mode"
```

### 方案 C：延迟执行 — 标记已知退化（推荐）

**理由**：
1. PF ratio gate 当前双重阻塞，事实休眠 → 无功能性损失
2. L1 上次结果为 FAIL → 重跑可能仍 FAIL，投入 3-6h 算力可能无收益
3. 核心目标（4+ 1 星品种过门）基于 DirAcc，不依赖 PF
4. Supervisor 探索/评估/快环/慢环全部正常运行

**行动**：
- 在 supervisor degraded 警告后追加「不影响核心功能」说明
- 在 FM_a 探索日志记录此调研结论
- 待以下条件满足时再执行方案 A：
  - v23 评估器开始输出 PF 指标
  - 或复测队列机制被重新启用
  - 或 vol-filter 方案有实质性更新（需要重跑 L1）

---

## 5. 推荐方案

**短期（立即）**：方案 C — 标记已知退化，不执行代码变更。

**中期（条件触发）**：当 v23 评估器产出 PF 时，执行方案 A + B。

**不需要**：
- 修改 supervisor 代码（degraded 行为正确）
- 修改 KB 构建代码（降级逻辑正确）
- 修改 goal.yaml（成功条件不依赖 PF）

---

## 6. 关键文件清单

| 文件 | 路径（WSL） | 说明 |
|------|------------|------|
| Supervisor | `scripts/praxist_supervisor.py` | INCUMBENT_PF 初始化 L117-122，retest gate L1200-1226 |
| KB 构建 | `scripts/build_knowledge_base.py` | 降级逻辑 L107-113，SCHEMES 合并 L130-180 |
| L1 判决 | `scripts/l1_economic_verdict.py` | 门禁标准 L30-31, L58-68 |
| Fullchain 回测 | `scripts/backtest_vol_gating_fullchain.py` | 重型 walk-forward |
| 准入扫描 | `scripts/universe_eligibility.py` | S0 前置 |
| 当前 KB | `config/knowledge_base.json` | degraded 态 |
| 缺失 L1 输出 | `reports/phase1/.../ECONOMIC_VERDICT.json` | 不存在 |
| 历史记录 | `docs/archive/history/LOOP.md:232-235` | 记载 2026-07-25 L1 运行 |
| 拆除伪造 commit | `5951611` | 根除 dir_acc*2 伪造 PF |

---

## 7. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 重跑 L1 仍 FAIL | 高 | KB 仍 degraded | 方案 C：接受降级 |
| fullchain 运行中 OOM | 中 | 中断管线 | 使用 `--resume` 断点续跑 |
| 未来误读 degraded 为新 bug | 低 | 重复调研 | 本 spec 入仓作为参考 |
| PF ratio gate 被意外激活 | 极低 | 无候选可筛 | v23 评估器不产出 PF，天然阻塞 |

---

## 附录 A: INCUMBENT_PF 完整使用链

```
supervisor 主循环 (~L2193)
  └→ _maybe_enqueue_retests(goal, log)
       └→ plan_sample_retests(goal)     # L1226
            └→ _retest_candidates(snap)  # L1233
                 └→ INCUMBENT_PF.get(symbol, 1.0)  # L1221 — 唯一消费点
```

常量：
- `RETEST_PF_RATIO = 1.05` — 候选 PF 须超过 incumbent 5%
- `RETEST_GATE_N = 350` — 最小样本点
- `RETEST_GATE_IC = 0.05` — 最小信息系数

## 附录 B: KB 消费者清单

| 消费者 | 读取字段 | null PF 影响 |
|--------|----------|-------------|
| supervisor `INCUMBENT_PF` | `historical_pf` | ratio fallback 1.0 |
| copilot.py 卡片展示 | `historical_pf`, `vol_sensitivity` | 显示 N/A / UNKNOWN |
| variety_analysis.py | `historical_pf`, `historical_ev` | 跳过历史信用行 |
| two_star_critic.py | 不直接读 KB PF | 无影响 |
| task_FM verdicts | 不读 KB | 无影响 |
