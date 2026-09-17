# MA 品种专项验证方案

**日期**: 2026-08-23  
**优先级**: 下一步行动计划 (Baseline PF 全品种核实完成后执行)

## 背景

Phase 15 专家审核发现：
1. Baseline PF 严重不一致 (MA: G005=0.71 vs STATE.md=1.00, delta +0.29)
2. StdDev 数学错误 (用 price std 而非 returns std, 已修复)
3. VWAP 填充策略无实证 (已添加 decay fill 选项)

用 G005 真实 baseline 重新评估 Phase 15 结果：
- MA: 0.71 → 0.89 (delta +0.18, 显著改善但未达 GREEN)
- 修复后可能进一步提升

## 目标

验证修复后的新协变量能否让 MA 突破 PF=1.0 (GREEN 门槛)

## 为什么选 MA

1. ✅ 改善最大 (+0.18, 从 0.71 → 0.89)
2. ✅ 样本量充足 (n=396)
3. ✅ 最接近 GREEN 门槛 (PF=1.0)
4. ✅ StdDef/VWAP 修复后仍有提升空间

## 实验设计

### 任务 1: Baseline 核实 (已在全品种核实中完成)
```bash
python scripts/monthly_backtest.py ma --with-baseline --max-points 396
```

### 任务 2: 修复后重跑 Phase 15 最佳协变量 (nvi)
```bash
python scripts/monthly_backtest.py ma --cov nvi --with-baseline --max-points 396
```

### 任务 3: StdDev 修复后重测 (原 math 错误)
```bash
python scripts/monthly_backtest.py ma --cov stddev --with-baseline --max-points 396
```

### 任务 4: VWAP decay fill 对照实验
```bash
# decay fill (12-bar half-life)
python scripts/monthly_backtest.py ma --cov vwap_deviation --fill-strategy decay --with-baseline --max-points 396

# constant fill (原始)
python scripts/monthly_backtest.py ma --cov vwap_deviation --fill-strategy default --with-baseline --max-points 396
```

### 任务 5: 组合最优 (如果 stddev/vwap 有改善)
```bash
python scripts/monthly_backtest.py ma --cov stddev vwap_deviation --fill-strategy decay --with-baseline --max-points 396
```

## 成功标准

- **GREEN**: PF >= 1.0 AND EV_ratio > 0 AND abs(MaxDD) < 80% AND n_eval >= 350
- 如果 MA 达到 GREEN → 固化到 prediction_scheme.py
- 如果 MA 未达 GREEN 但 PF > 0.95 → 考虑信号工程 (非线性变换)
- 如果 MA 仍 < 0.95 → 接受天花板,转向其他品种

## 预计耗时

5 次回测 × ~2-3 分钟/次 = 10-15 分钟 (CPU-only)

## 风险

- MA 可能仍无法突破 PF=1.0 (弱信号品种天花板)
- StdDef/VWAP 修复后改善有限

## 依赖

- Baseline PF 全品种核实完成 (确认真实 baseline)
- StdDev 数学修复已部署 (commit 338f144)
- VWAP fill_strategy 参数已添加 (commit 83341ea)

## 下一步

Baseline PF 全品种核实完成后，按任务 1-5 顺序执行。
