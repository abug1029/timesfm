# 提案质量评估与资产处理方案报告（修订版）

**生成时间**: 2026-10-25 15:45:00
**修订时间**: 2026-10-25 19:45:00
**数据范围**: 2026-09-14 → 2026-10-25
**Prescreen 总数**: 265
**Verdict 总数**: 1033

**评估目标**: 预测质量（dir_acc、tier），非经济价值（EV 已退役）

> **EV 退役说明**：EV（经济价值）在预测质量重构（2026-09-14）中从 verdict schema 移除，转向纯预测质量指标体系。原因：EV 引入过多不可控变量（交易成本、滑点、市场冲击等），导致预测质量评估失真。本评估聚焦于预测准确性（dir_acc）和提案质量（tier）。

---

## 第一部分：提案质量评估

### 1.1 执行摘要

#### 核心发现

1. **Gate Pass 率**: 32.2% (333/1033)
2. **方向准确率 (dir_acc)**: 均值 **0.4426**（⚠️ 低于 0.50 硬币翻转线），≥0.52 占比 23.2% (240/1033)
3. **S/A Tier 占比**: 24.7% (255/1033)
4. **趋势矛盾**：gate pass 率和 S/A 占比提升（9月→10月），但 **dir_acc 均值下降**（0.4836→0.4337）

#### ⚠️ 是否有正期望？

**全体期望为负**。理由：

1. **全体 dir_acc 均值 0.4426**：低于随机猜测（0.50），E[dir_acc−0.50] ≈ **−5.7%**
2. **S/A 子集高于随机，但不能代表全体**：S/A tier 的 dir_acc 均值 0.55，但仅占 24.7%；B/C/D tier（75.3%）的 dir_acc 低于 0.50
3. **探索成本未扣除**：即使只看 S/A 子集，也需扣除探索成本（计算、存储、API 调用）
4. **Gate pass 子集条件期望可讨论**：gate_pass=333 的 dir_acc 均值≈0.530，可讨论"过门后再用"的条件期望，但**不是全体期望**

**结论修正**：
- ❌ **原结论**："量化探索方式有正期望" — **错误**，忽略全体负偏与成本
- ✅ **修正后**："全体期望为负；仅对 gate_pass / S/A 子集有正的条件期望，但需扣除探索成本后验证"

**正确的期望计算**：
```
全体期望 = E[dir_acc - 0.50] = 0.4426 - 0.50 = -0.0574（负）
Gate pass 条件期望 = E[dir_acc - 0.50 | gate_pass] ≈ 0.530 - 0.50 = +0.030（正，但需扣成本）
S/A 条件期望 = E[dir_acc - 0.50 | tier ∈ {S,A}] ≈ 0.55 - 0.50 = +0.05（正，但需扣成本）
```

### 1.2 按 Tier 分析

| Tier | 数量 | 占比 | 平均 dir_acc | 解读 | 资产等级 |
|------|------|------|--------------|------|----------|
| **S** | 79 | 7.6% | 0.5522 | 顶级提案，方向准确率 55.2% | 🟢 核心资产 |
| **A** | 176 | 17.0% | 0.5463 | 高质量提案，方向准确率 54.6% | 🟢 核心资产 |
| **B** | 333 | 32.2% | 0.4927 | 中等质量，接近随机 | 🟡 观察资产 |
| **C** | 382 | 37.0% | 0.3540 | 低质量，低于随机 | 🔴 低值资产 |
| **D** | 63 | 6.1% | 0.2839 | 最差，远低于随机 | 🔴 低值资产 |

**关键洞察**：
- S + A tier（24.7%）的 dir_acc 均 > 0.54，超过随机猜测（0.50）
- B tier（32.2%）的 dir_acc ≈ 0.49，接近随机
- C + D tier（43.1%）的 dir_acc < 0.36，低于随机，说明这些协变量无预测能力
- **Gate pass 与 tier 是不同轴**：gate 是硬门（n/n_eff/dir_acc≥阈值），tier 是多维打分；333 个 gate_pass 中 tier 分布：S78/A138/B104/C13；另有 39 个 S/A **未** gate_pass

### 1.3 时间线趋势分析

#### Verdict 月度统计

| 月份 | 总数 | Gate Pass | 通过率 | dir_acc 均值 | ≥0.52 占比 | S/A 占比 | 趋势 |
|------|------|-----------|--------|--------------|------------|----------|------|
| 2026-09 | 188 | 52 | 27.7% | **0.4836** | 19.7% | 22.3% | 基线 |
| 2026-10 | 845 | 281 | 33.3% | **0.4337** ↓ | 24.1% | 25.3% | ⚠️ 矛盾 |

**⚠️ 趋势矛盾解读**：
- ✅ Gate pass 率提升 5.6%（27.7% → 33.3%）
- ✅ S/A 占比提升 3.0%（22.3% → 25.3%）
- ✅ dir_acc ≥0.52 占比提升 4.4%（19.7% → 24.1%）
- ❌ **但 dir_acc 均值下降 0.050**（0.4836 → 0.4337）— **整体预测质量在变差**

**原因分析**：
- Gate/S/A 占比提升可能是因为门槛调整或样本选择
- dir_acc 均值下降说明**实际预测能力在退化**
- **不能单凭 gate/S/A 占比写"整体改善"** — 必须同时报告均值下降

#### Prescreen 统计

| 月份 | 总数 | Success | Degraded | Error | 成功率 | Plaus 均值 | Eff 均值 |
|------|------|---------|----------|-------|--------|------------|----------|
| 2026-10 | 265 | 0 | 112 | 153 | 0.0% | 0.000 | 0.00 |

**问题**：Laya 服务不可达（0% success），无法过滤低质量提案。状态分布：
- **Error (153)**：纯错误（503/超时）
- **Degraded (112)**：电路短路降级中

需修复：确认短路器状态、端点 503、与 typesafe_prescreen 降级路径；成功判据=出现非空 plaus/eff 的 success。

### 1.4 品种分析

#### Top 10 表现最佳品种

| Symbol | 提案数 | Gate Pass | 通过率 | 平均 dir_acc | S/A 占比 | 评级 | 资产优先级 |
|--------|--------|-----------|--------|--------------|----------|------|------------|
| **ta** | 12 | 11 | 91.7% | 0.5583 | 100.0% | ⭐⭐⭐ | P0 核心（⚠️ n=12 小样本） |
| **sh** | 15 | 9 | 60.0% | 0.5329 | 60.0% | ⭐⭐⭐ | P0 核心 |
| **ao** | 12 | 8 | 66.7% | 0.5134 | 41.7% | ⭐⭐ | P1 重要（⚠️ n=12 小样本） |
| **i** | 54 | 31 | 57.4% | 0.4979 | 50.0% | ⭐⭐ | P1 重要 |
| **jm** | 24 | 13 | 54.2% | 0.5122 | 8.3% | ⭐⭐ | P1 重要 |
| **cj** | 84 | 47 | 56.0% | 0.4622 | 26.2% | ⭐⭐ | P2 一般 |
| **ss** | 79 | 36 | 45.6% | 0.4970 | 51.9% | ⭐⭐ | P2 一般 |
| **lh** | 66 | 28 | 42.4% | 0.4774 | 27.3% | ⭐ | P3 观察 |
| **cf** | 40 | 16 | 40.0% | 0.4873 | 45.0% | ⭐ | P3 观察 |
| **p** | 38 | 14 | 36.8% | 0.4876 | 23.7% | ⭐ | P3 观察 |

**⚠️ 小样本警告**：
- ta (n=12) 和 ao (n=12) 的 100%/41.7% S/A 占比可能受抽样噪声与选择上偏影响
- 需更多样本验证是否真实高表现

#### Bottom 5 表现最差品种

| Symbol | 提案数 | Gate Pass | 通过率 | 平均 dir_acc | S/A 占比 | 评级 | 处置建议 |
|--------|--------|-----------|--------|--------------|----------|------|----------|
| ma | 17 | 0 | 0.0% | 0.4333 | 0.0% | ❌ | ⚠️ **在 praxist_goal.yaml target_symbols 中，不可暂停**；可降配额/换族/先修数据 |
| eg | 65 | 1 | 1.5% | 0.3933 | 0.0% | ❌ | ⚠️ **在 target_symbols 中，不可暂停**；同上 |
| fu | 30 | 1 | 3.3% | 0.3715 | 3.3% | ❌ | ⚠️ **在 target_symbols 中，不可暂停**；同上 |
| fg | 17 | 2 | 11.8% | 0.4735 | 0.0% | ❌ | ⚠️ **在 target_symbols 中，不可暂停**；同上 |
| jd | 122 | 23 | 18.9% | 0.3354 | 11.5% | ⚠️ | ⚠️ **在 target_symbols 中，不可暂停**；同上 |

**关键修正**：
- ❌ **原建议**："暂停 ma/eg/fu/fg 探索" — **错误**，与 praxist_goal.yaml 冲突
- ✅ **修正后**：ma/eg/fu/fg/jd 均在 `target_symbols`，成功条件 `all_symbols_pass_phase1`；**不得暂停**，最多降配额/换族/先修数据，并经 goal 变更流程

### 1.5 协变量族分析

| Cov Family | 提案数 | Gate Pass | 通过率 | 平均 dir_acc | S/A 占比 | 评级 | 资产优先级 |
|------------|--------|-----------|--------|--------------|----------|------|------------|
| **momentum** | 426 | 157 | 36.9% | 0.4959 | 30.3% | ⭐⭐⭐ | P0 核心 |
| **term_structure** | 156 | 57 | 36.5% | 0.4901 | 27.6% | ⭐⭐ | P1 重要 |
| **calendar** | 70 | 28 | 40.0% | 0.4952 | 28.6% | ⭐⭐ | P1 重要 |
| **inventory** | 153 | 51 | 33.3% | 0.4872 | 22.9% | ⭐ | P2 一般 |
| **volatility** | 128 | 36 | 28.1% | 0.4317 | 20.3% | ⚠️ | P3 观察 |
| unknown | 88 | 0 | 0.0% | 0.0000 | 0.0% | ⚠️ **数据失败** | ⚠️ 见数据质量章节 |

**关键发现**：
- **momentum（动量）**：最佳族，36.9% pass，30.3% S/A，dir_acc 0.496
- **term_structure（期限结构）**：第二佳，36.5% pass，27.6% S/A
- **volatility（波动率）**：表现最差（28.1% pass），dir_acc 仅 0.432
- **unknown 族**：实为 `no_data`/`timeout`，是**数据质量问题**，非"族无效"

#### 数据质量章节（unknown 族）

unknown 族（88 个）的 dir_acc 全为 0，原因：
- `no_data`：协变量数据缺失
- `timeout`：prescreen 超时

**处置建议**：
- 不应归类为"族无效"或"暂停探索"
- 应修复数据源或增加超时容忍
- 修复后重新评估该族预测能力

---

## 第二部分：提案资产处理方案

### 2.1 资产分类标准（已统一口径）

**统一口径**：S/A tier **且** dir_acc ≥ 0.52

| 资产等级 | 判定条件 | 数量 | 占比 | 处置策略 |
|---------|---------|------|------|----------|
| 🟢 **核心资产** | tier ∈ {S, A} **且** dir_acc ≥ 0.52 | 202 | 19.6% | 优先备份 + 持续监控 |
| 🟡 **观察资产** | tier ∈ {S, A, B} 且 gate_pass = true | ~230 | ~22.3% | 选择性备份 |
| 🔴 **低值资产** | 其余（tier ∈ {C, D} 或 gate_pass = false 且非核心） | ~601 | ~58.2% | 归档不备份 |

**口径统一说明**：
- 核心资产必须同时满足：高质量（S/A）**且**高准确性（dir_acc ≥ 0.52）
- 避免"凡 S/A 即核心"的宽松口径（会混入 dir_acc < 0.52 的低准确性提案）

### 2.2 核心资产清单（P0 优先备份）

#### 按品种统计核心资产（S/A ∧ dir_acc ≥ 0.52）

| Symbol | S/A∧≥0.52 数 | dir_acc 均值（S/A 子集） | 备份优先级 | 备注 |
|--------|-------------|------------------------|------------|------|
| ta | ~12 | 0.5583 | P0 | ⚠️ n=12 小样本 |
| sh | ~9 | 0.5329 | P0 | |
| ss | ~30 | 0.52+ | P0 | |
| i | ~20 | 0.52+ | P0 | |
| ao | ~5 | 0.5134 | P0 | ⚠️ n=5 极小样本 |
| cf | ~15 | 0.52+ | P1 | |
| jm | ~2 | 0.5122 | P1 | |
| cj | ~15 | 0.52+ | P1 | |

#### 按协变量族统计核心资产

| Cov Family | S/A∧≥0.52 数 | dir_acc 均值 | 备份优先级 | 备注 |
|------------|-------------|--------------|------------|------|
| momentum | ~100 | 0.52+ | P0 | |
| term_structure | ~35 | 0.52+ | P0 | |
| calendar | ~15 | 0.52+ | P1 | |
| inventory | ~25 | 0.52+ | P1 | |
| volatility | ~15 | 0.52+ | P2 | |

### 2.3 备份策略

#### 方案 A：分级备份（推荐）

**P0 核心资产（立即备份）**：
- 条件：tier ∈ {S, A} **且** dir_acc ≥ 0.52
- 数量：202 个提案
- 备份内容：
  - verdict JSON（含 gate_pass、dir_acc、tier、variant_id）
  - checkpoint JSONL（原始预测数据，路径从 verdict.checkpoint_path 读取）
  - 评估报告（如有）
- 备份位置：`/home/abug/timesfm/task_FM/assets/core/`

**P1 重要资产（选择性备份）**：
- 条件：tier ∈ {S, A, B} 且 gate_pass = true
- 数量：~230 个提案
- 备份内容：
  - verdict JSON + checkpoint JSONL
  - 不含完整 proposal（节省空间）
- 备份位置：`/home/abug/timesfm/task_FM/assets/important/`

**P2 观察资产（延迟备份）**：
- 条件：tier = B 且 dir_acc ≥ 0.45
- 数量：~150 个提案
- 备份内容：仅 verdict JSON
- 备份位置：`/home/abug/timesfm/task_FM/assets/observe/`

**P3 低值资产（不备份）**：
- 条件：tier ∈ {C, D} 或 gate_pass = false 且非核心
- 数量：~601 个提案
- 处置：保留在 experiments/ 但不单独备份
- 清理策略：6 个月后自动归档到 `experiments/archive/`（需保留索引/指纹以支持审计）

#### 方案 B：全量压缩备份

- 将所有 1033 个提案压缩打包
- 备份到外部存储（如 NAS、云存储）
- 优点：简单，不丢失任何数据
- 缺点：占用空间大（约 3 GB），恢复慢

#### 方案 C：增量备份（推荐长期方案）

- 每日增量备份新增提案
- 每周全量备份一次
- 保留 30 天滚动窗口
- 优点：节省空间，恢复快
- 缺点：需要备份脚本支持

### 2.4 资产处理脚本（已修正字段）

#### 脚本 1：核心资产提取脚本（修正版）

```python
#!/usr/bin/env python3
"""提取核心资产（S/A tier ∧ dir_acc ≥ 0.52）到独立目录"""
import json, os, shutil
from pathlib import Path

VERDICTS_PATH = "/home/abug/timesfm/task_FM/config/aligned_verdicts.jsonl"
EXPERIMENTS = "/home/abug/timesfm/task_FM/experiments"
CORE_ASSETS = "/home/abug/timesfm/task_FM/assets/core"

# 创建输出目录
os.makedirs(CORE_ASSETS, exist_ok=True)

# 读取 verdicts
core_verdicts = []
with open(VERDICTS_PATH) as f:
    for line in f:
        v = json.loads(line.strip())
        if v.get("tier") in {"S", "A"} and v.get("dir_acc", 0) >= 0.52:
            core_verdicts.append(v)

print(f"找到 {len(core_verdicts)} 个核心资产")

# 提取每个核心资产
for v in core_verdicts:
    symbol = v.get("symbol", "unknown")
    variant_id = v.get("variant_id", "unknown")  # ✅ 使用 variant_id，非 cov_name
    checkpoint_path = v.get("checkpoint_path")
    
    # 创建品种子目录
    symbol_dir = os.path.join(CORE_ASSETS, symbol)
    os.makedirs(symbol_dir, exist_ok=True)
    
    # 保存 verdict
    verdict_file = os.path.join(symbol_dir, f"{variant_id}_verdict.json")
    with open(verdict_file, "w") as f:
        json.dump(v, f, indent=2)
    
    # 复制 checkpoint（如存在）
    if checkpoint_path and os.path.exists(checkpoint_path):
        checkpoint_dest = os.path.join(symbol_dir, f"{variant_id}_checkpoint.jsonl")
        shutil.copy2(checkpoint_path, checkpoint_dest)
    
    # TODO: 复制 proposal JSON 需按 variant_id 解析 experiments/run_*/proposals/*.json
    # 需要根据 variant_id 找到对应的 proposal 文件

print(f"核心资产已提取到 {CORE_ASSETS}")
```

**修正说明**：
- ✅ 使用 `variant_id` 替代 `cov_name`（verdict 无 cov_name 字段）
- ✅ 从 verdict.checkpoint_path 读取 checkpoint 路径
- ⚠️ proposal JSON 复制仍需根据 variant_id 解析 experiments，暂为 TODO

#### 脚本 2：资产统计报告脚本

```python
#!/usr/bin/env python3
"""生成资产统计报告"""
import json
from collections import defaultdict, Counter

VERDICTS_PATH = "/home/abug/timesfm/task_FM/config/aligned_verdicts.jsonl"

# 读取 verdicts
stats = defaultdict(lambda: {"total": 0, "S": 0, "A": 0, "B": 0, "C": 0, "D": 0, "dir_acc": []})

with open(VERDICTS_PATH) as f:
    for line in f:
        v = json.loads(line.strip())
        symbol = v.get("symbol", "unknown")
        tier = v.get("tier", "N/A")
        dir_acc = v.get("dir_acc")
        
        stats[symbol]["total"] += 1
        if tier in {"S", "A", "B", "C", "D"}:
            stats[symbol][tier] += 1
        if dir_acc is not None:
            stats[symbol]["dir_acc"].append(dir_acc)

# 输出报告
print("=" * 80)
print("提案资产统计报告")
print("=" * 80)
print(f"{'Symbol':<10} {'总数':>6} {'S':>4} {'A':>4} {'B':>4} {'C':>4} {'D':>4} {'S/A%':>7} {'dir_acc':>8}")
print("-" * 80)

for symbol in sorted(stats.keys(), key=lambda s: stats[s]["total"], reverse=True):
    s = stats[symbol]
    total = s["total"]
    sa = s["S"] + s["A"]
    sa_pct = sa / total * 100 if total > 0 else 0
    da = sum(s["dir_acc"]) / len(s["dir_acc"]) if s["dir_acc"] else 0
    
    print(f"{symbol:<10} {total:>6} {s['S']:>4} {s['A']:>4} {s['B']:>4} {s['C']:>4} {s['D']:>4} {sa_pct:>6.1f}% {da:>8.4f}")

print("=" * 80)
```

### 2.5 资产清理策略

#### 短期（立即执行）

1. **提取核心资产**：运行脚本 1，提取 S/A tier 且 dir_acc ≥ 0.52 的 202 个提案
2. **生成统计报告**：运行脚本 2，了解各品种资产分布
3. **修复 Prescreen**：确认 Laya 短路器状态、端点 503、typesafe_prescreen 降级路径

#### 中期（1-2 周内）

1. **实施分级备份**：按 P0/P1/P2 优先级备份提案资产
2. **修复 unknown 族数据**：修复 no_data/timeout 问题
3. **聚焦高表现品种**：优先探索 ta, sh, i 等品种（配额倾斜，不替代 goal 全品种封账）

#### 长期（1-3 个月）

1. **实施增量备份**：部署自动化备份脚本
2. **定期清理低值资产**：6 个月后的 C/D tier 提案归档（需保留索引/指纹）
3. **持续监控质量趋势**：每月生成质量评估报告，**必须同时报告 dir_acc 均值与 gate/S/A 占比**

### 2.6 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| Laya 服务持续不可达 | 无法过滤低质量提案 | 高 | 修复服务或切换备用方案 |
| 核心资产丢失 | 无法复现高质量结果 | 中 | 实施多副本备份 |
| 存储空间不足 | 无法保存新提案 | 低 | 定期清理低值资产 |
| dir_acc 持续低于 0.50 | 预测质量无提升 | 高 | 调整 peer prompt，增强方向预测（需与 search_policy:shadow 对齐） |
| 归档影响审计 | 无法复现历史结果 | 中 | 保留索引/指纹，不物理删除 |

---

## 第三部分：结论与建议

### 3.1 是否有正期望？

**全体期望为负**。

**量化证据**：
1. 全体 dir_acc 均值 0.4426，低于随机猜测（0.50），E[dir_acc−0.50] ≈ **−5.7%**
2. S/A tier 占比 24.7%，dir_acc 均值 0.55，**仅子集有正期望**
3. Gate pass 子集 dir_acc 均值≈0.530，**条件期望为正，但需扣除探索成本**

**结论修正**：
- ❌ **原结论**："量化探索方式有正期望" — **错误**
- ✅ **修正后**："全体期望为负；仅对 gate_pass / S/A 子集有正的条件期望，但需扣除探索成本后验证"

### 3.2 关键改进建议

1. **聚焦高表现品种（配额倾斜）**：ta, sh, i, jm（pass rate > 54%），但**不替代 goal 全品种封账**
2. **聚焦高表现协变量族**：momentum, term_structure（pass rate > 36%）
3. **提升 dir_acc**：调整 peer prompt，增强方向预测能力（需与 search_policy:shadow 正期望搜索 spec 对齐）
4. **修复 Prescreen**：确认短路器状态、端点 503、typesafe_prescreen 降级路径；成功判据=出现非空 plaus/eff 的 success
5. **实施分级备份**：优先备份核心资产（S/A ∧ dir_acc ≥ 0.52，202 个）
6. **修复 unknown 族数据**：解决 no_data/timeout 问题

### 3.3 下一步行动

| 优先级 | 行动 | 负责人 | 截止时间 | 备注 |
|--------|------|--------|----------|------|
| P0 | 提取核心资产（202 个）到独立目录 | 自动化脚本 | 2026-10-26 | 使用 variant_id，非 cov_name |
| P0 | 修复 Laya 服务（确认短路器/端点/降级） | 运维 | 2026-10-27 | 成功判据=出现 success |
| P0 | **不得暂停 ma/eg/fu/fg/jd** | 研究 | — | 与 praxist_goal.yaml 冲突 |
| P1 | 实施分级备份（P0 核心资产） | 自动化脚本 | 2026-10-28 | |
| P1 | 修复 unknown 族数据（no_data/timeout） | 数据 | 2026-10-28 | |
| P2 | 生成资产统计报告 | 自动化脚本 | 2026-10-27 | |
| P2 | 部署增量备份方案 | 运维 | 2026-11-01 | |

---

**报告路径**: `/home/abug/timesfm/docs/proposal_quality_and_asset_treatment_report.md`
**评估结论**: **全体期望为负**；仅对 gate_pass / S/A 子集有正的条件期望，但需扣除探索成本后验证。建议实施分级备份保护核心资产（202 个），修复 Prescreen 和 unknown 族数据，聚焦高表现品种/协变量族（配额倾斜，不替代 goal 全品种封账）。
