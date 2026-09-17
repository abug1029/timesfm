# 回测资产目录 (Backtest Registry)

**生成日期**: 2026-08-29
**品种数**: 21
**实验总数**: 228 (含 Phase 12/13/15/15b/Q1 累计)

> 本目录记录所有品种+协变量配置的回测实验, 避免重复回测浪费算力。
> 每条记录包含: 协变量配置、日期、阶段、样本量(n)、DirAcc、结论。
>
> **口径备注 (2026-08-30)**: 2026-08-18~20 批次日志 (F1-F4) 中的 MaxDD 值为**修复前口径**
> (旧 cumsum 公式可 <-100%, 如 JM -265.86%/FG -134.98%)。MaxDD 已于 2026-08-21 修复
> (`cascade/evaluation_metrics.py` cumprod+clamp, 8 测试覆盖)。Phase 11 固化裁决以 PF 为准,
> 不受 MaxDD 口径影响。2026-08-21 之后的记录均为修复后口径。

## AO 氧化铝 (hourly_slope+calendar_cyclical, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 193 | 56.0% | baseline 参照 |
| ha_body | 2026-08-03 | Phase 9 (2星->3星) | 193 | 52.8% | FAIL |
| ha_body+oi | 2026-08-03 | Phase 9 (2星->3星) | 193 | 52.3% | FAIL |
| ha_body+hourly_slope | 2026-08-03 | Phase 9 (2星->3星) | 193 | 55.4% | FAIL |
| vor | 2026-08-04 | Phase 9 (有毒品种) | 193 | 44.0% | FAIL |
| hourly_slope+oi | 2026-08-04 | Phase 9 (有毒品种) | 193 | 56.0% | FAIL |
| hourly_slope+reversal_shadow | 2026-08-04 | Phase 9 (有毒品种) | 193 | 53.9% | FAIL |
| ao_accel | 2026-08-04 | Phase 9 (有毒品种) | 193 | 50.8% | FAIL |
| baseline | 2026-08-04 | Phase 9 (有毒品种) | 193 | 56.0% | baseline 参照 |
| bb_squeeze | 2026-08-04 | Phase 9 (有毒品种) | 193 | 48.7% | FAIL |
| calendar_cyclical | 2026-08-04 | Phase 9 (有毒品种) | 193 | 49.7% | PASS -> 已固化 |
| ha_body | 2026-08-04 | Phase 9 (有毒品种) | 193 | 52.8% | FAIL |
| reversal_shadow | 2026-08-04 | Phase 9 (有毒品种) | 193 | 50.3% | FAIL |
| hourly_slope+calendar_cyclical | 2026-08-04 | Phase 9 (有毒品种) | 193 | 52.3% | PASS -> 已固化 |
| full-signal (use_full_signal=True) | 2026-08-17 | AO 信号模式裁决 | 193 | 49.7% | v2 GREEN-MAXDD (PF 0.86→0.978 +13.7%, MaxDD -56%→-41.7% 改善25.5%), 不固化 (PF<1, n<350) |
| Phase 11 单协变量穷举 (5 cov) | 2026-08-20 | Phase 11 | 199 | 47% | 0 GREEN (best PF=0.73), 当前方案保持 |
| Phase 12 组合协变量 (2 cov × 2) | 2026-08-21 | Phase 12 | 199 | 49% | 0 GREEN (best rev+ha PF=0.76), 组合未突破 |
| Phase 13 组合探索 (18 tests) | 2026-08-22 | Phase 13 | 199 | 49% | 0 GREEN (最佳 ha+cal PF=0.95), 天花板确认 |
| Phase 15 新协变量 (4 tests) | 2026-08-23 | Phase 15 | 396 | 49% | 0 GREEN (最佳 vwap PF=0.86), 全面弱于 baseline 0.90 |
| stddev [returns std] | 2026-08-29 | Phase 15b | 199 | 49% | PF=0.90 (+0.14 vs price-std), MaxDD -35% 改善36%; n<350 underpowered, 待复评 |
| vwap_deviation [decay fill] | 2026-08-29 | Phase 15b | 199 | 49% | FAIL (PF=0.74 ≈ 常数 0.73), 衰减填充已回滚 |

## BU 沥青 (calendar_cyclical+hourly_slope, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| crack_spread (SC-BU) [baseline] | 2026-08-01 | Phase 8b | 396 | N/A | FAIL (UNDERPOWERED) |
| crack_spread (SC-BU) [additive] | 2026-08-01 | Phase 8b | 396 | N/A | FAIL (UNDERPOWERED) |
| crack_spread (SC-BU) [replace] | 2026-08-01 | Phase 8b | 396 | N/A | FAIL (UNDERPOWERED) |
| ha_body+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.3% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.0% | baseline 参照 |
| bb_squeeze+ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 55.0% | FAIL |
| ha_body+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.5% | FAIL |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 50% | 0 GREEN (best PF=0.99), 当前方案保持 |
| Phase 12 组合协变量 (2 cov × 2) | 2026-08-21 | Phase 12 | 396 | 51% | 1 GREEN (cal+hs PF=1.01), baseline(ha_body) PF=0.79 FAIL → 固化替换 calendar_cyclical+hourly_slope |

## CF 棉花 (ha_body+calendar_cyclical, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| calendar_cyclical [baseline] | 2026-07-30 | Phase 4d | 396 | 51% | 见STATE.md |
| calendar_cyclical [additive] | 2026-07-30 | Phase 4d | 396 | 56% | 见STATE.md |
| calendar_cyclical [replace] | 2026-07-30 | Phase 4d | 396 | 52% | 见STATE.md |
| rsi_state+oi+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.8% | FAIL |
| ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 51.3% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 56.1% | baseline 参照 |
| ha_body+reversal_shadow+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 55.3% | FAIL |
| ha_body+oi+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.8% | FAIL |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 50% | 0 GREEN (best PF=0.90), 当前方案保持 |
| Phase 12 组合协变量 (2 cov × 2) | 2026-08-21 | Phase 12 | 396 | 51% | 0 GREEN (best rev+ha PF=0.94), 组合未突破 |
| Phase 13 组合探索 (18 tests) | 2026-08-22 | Phase 13 | 396 | 49% | 0 GREEN (最佳 rev+ha PF=0.94), 天花板确认 |
| Phase 15 新协变量 (4 tests) | 2026-08-23 | Phase 15 | 396 | 49% | 0 GREEN (最佳 qstick PF=0.79), 全面弱于 baseline 0.95 |
| stddev [returns std] | 2026-08-29 | Phase 15b | 396 | 48% | FAIL (PF=0.76 vs price-std 0.73, +0.03 仍<1) |
| vwap_deviation [decay fill] | 2026-08-29 | Phase 15b | 396 | 48% | FAIL (PF=0.76 ≈), 衰减填充已回滚 |
| qstick_w28 [norm_window=28] | 2026-08-29 | Phase Q1 D2 (部分) | 396 | 47% | FAIL (PF=0.64 vs baseline 0.95, -0.31 大幅退化), 批次停止后 CANCEL |

## CJ 红枣 (hourly_slope, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| ha_body | 2026-08-03 | Phase 9 (2星->3星) | 317 | 55.2% | PASS -> 已固化 |
| ha_body+oi+reversal_shadow_gated_05 | 2026-08-03 | Phase 9 (2星->3星) | 317 | 52.4% | FAIL |
| ha_body+reversal_shadow_gated_05 | 2026-08-03 | Phase 9 (2星->3星) | 317 | 51.7% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 317 | 53.6% | baseline 参照 |
| reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 317 | 53.0% | FAIL |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 320 | 53% | 5 GREEN (hs=1.29🔥/ao=1.28/oi=1.14/rev=1.14/rsi=1.03), 固化 → hourly_slope |

## EG 乙二醇 (calendar_cyclical, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.8% | baseline 参照 |
| ha_body+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.3% | FAIL |
| ha_body+oi+reversal_shadow+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.8% | FAIL |
| ha_body+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.5% | FAIL |
| rsi_state+oi+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 53.0% | FAIL |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 51% | 1 GREEN (cal=1.04), 待基线对比决策 |

## FG 玻璃 (ha_body, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| baseline | 2026-08-02 | Phase 9 (2星->3星) | 396 | 51.3% | baseline 参照 |
| ha_body+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.0% | FAIL |
| ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 55.3% | PASS -> 已固化 |
| reversal_shadow+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.5% | FAIL |
| ha_body+oi+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 54.8% | FAIL |
| ha_body+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 53.5% | FAIL |
| ha_body+sar_dist | 2026-08-18 | 协变量空白补测 批次C (干净归因) | 396 | 47% | FAIL (PF=0.89 vs baseline 0.91, 退化) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 48% | 0 GREEN (best oi=0.93), 当前方案保持 |
| Phase 12 组合协变量 (2 cov × 2) | 2026-08-21 | Phase 12 | 396 | 48% | 0 GREEN (best oi+hs PF=0.93), 组合未突破 |
| Phase 13 组合探索 (18 tests) | 2026-08-22 | Phase 13 | 396 | 48% | 0 GREEN (最佳 oi+cal PF=0.88), 天花板确认 |
| Phase 15 新协变量 (4 tests) | 2026-08-23 | Phase 15 | 396 | 46% | 0 GREEN (最佳 vwap PF=0.86), 全面弱于 baseline 0.93 |
| stddev [returns std] | 2026-08-29 | Phase 15b | 396 | 46% | FAIL (PF=0.81 vs price-std 0.80, ≈) |
| vwap_deviation [decay fill] | 2026-08-29 | Phase 15b | 396 | 46% | FAIL (PF=0.81 vs 常数 0.86, -0.05), 衰减填充已回滚 |

## FU 燃料油 (calendar_cyclical, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| crack_spread (SC-FU) [baseline] | 2026-08-01 | Phase 8b | 396 | N/A | FAIL (UNDERPOWERED) |
| crack_spread (SC-FU) [additive] | 2026-08-01 | Phase 8b | 396 | N/A | FAIL (UNDERPOWERED) |
| crack_spread (SC-FU) [replace] | 2026-08-01 | Phase 8b | 396 | N/A | FAIL (UNDERPOWERED) |
| ha_body+reversal_shadow | 2026-08-02 | Phase 9 (2星->3星) | 396 | 54.0% | FAIL |
| ha_body | 2026-08-02 | Phase 9 (2星->3星) | 396 | 55.0% | PASS -> 已固化 |
| ha_body+oi+reversal_shadow | 2026-08-02 | Phase 9 (2星->3星) | 396 | 52.8% | FAIL |
| ha_body+oi | 2026-08-02 | Phase 9 (2星->3星) | 396 | 55.0% | FAIL |
| baseline | 2026-08-02 | Phase 9 (2星->3星) | 396 | 53.5% | baseline 参照 |
| ha_body+calendar_cyclical | 2026-08-02 | Phase 9 (2星->3星) | 396 | 54.5% | FAIL |
| ha_body+sar_dist | 2026-08-18 | 协变量空白补测 批次C (干净归因) | 396 | 51% | FAIL (PF=1.02 vs baseline 0.95, +7.4% 未达10%) |
| baseline (ha_body) | 2026-08-20 | Phase 11 基线对比 | 396 | 50% | PF=0.93 EV=-0.037 (FAIL) |
| calendar_cyclical | 2026-08-20 | Phase 11 单协变量 | 396 | 53% | PF=1.23 EV=+0.101 GREEN → 固化替换 ha_body |

## I 铁矿石 (reversal_shadow, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| ha_body+oi+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 53.0% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 51.8% | baseline 参照 |
| ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.3% | PASS -> 已固化 |
| ha_body+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 50.2% | FAIL |
| candidate IB | 2026-08-04 | Phase 10 | 1583 | N/A | 待查文档 |
| candidate IC | 2026-08-04 | Phase 10 | 1577 | N/A | 待查文档 |
| candidate IA | 2026-08-04 | Phase 10 | 1580 | N/A | 待查文档 |
| candidate baseline | 2026-08-04 | Phase 10 | 1584 | N/A | 待查文档 |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 51% | 1 GREEN (rev=1.06), baseline ha_body PF=0.98 → 固化替换 reversal_shadow |

## JD 鸡蛋 (rsi_state, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| calendar_cyclical [baseline] | 2026-07-30 | Phase 4d | 396 | 50% | 见STATE.md |
| calendar_cyclical [replace] | 2026-07-30 | Phase 4d | 396 | 50% | 见STATE.md |
| rsi_state+oi+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 50.2% | FAIL |
| ha_body+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 49.5% | FAIL |
| rsi_state+oi+ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 53.0% | FAIL |
| rsi_state+oi+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 50.0% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.5% | baseline 参照 |
| ao_accel | 2026-08-04 | Phase 9 (有毒品种) | 396 | 50.2% | FAIL |
| candidate baseline | 2026-08-04 | Phase 10 | 778 | N/A | 待查文档 |
| candidate JDC | 2026-08-04 | Phase 10 | 1582 | N/A | 待查文档 |
| gated_slope | 2026-08-04 | Phase 9 (有毒品种) | 396 | 50.0% | FAIL |
| reversal_shadow | 2026-08-04 | Phase 9 (有毒品种) | 396 | 48.7% | FAIL |
| hourly_slope+oi | 2026-08-04 | Phase 9 (有毒品种) | 396 | 51.5% | FAIL |
| candidate JDA | 2026-08-04 | Phase 10 | 639 | N/A | 待查文档 |
| calendar_cyclical | 2026-08-04 | Phase 9 (有毒品种) | 396 | 49.5% | FAIL |
| baseline | 2026-08-04 | Phase 9 (有毒品种) | 396 | 52.5% | baseline 参照 |
| rsi_state+sar_dist | 2026-08-18 | 协变量空白补测 批次B | 396 | 48% | FAIL (PF=0.94, sar_dist替换oi退化) |
| rsi_state+oi+calendar_cyclical | 2026-08-04 | Phase 9 (有毒品种) | 396 | 50.2% | FAIL |
| calendar_cyclical+gated_slope | 2026-08-04 | Phase 9 (有毒品种) | 0 | N/A | FAIL (计算异常) |
| bb_squeeze | 2026-08-04 | Phase 9 (有毒品种) | 396 | 46.7% | FAIL |
| candidate JDB | 2026-08-04 | Phase 10 | 1590 | N/A | 待查文档 |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 48% | 3 GREEN (rsi=1.09/hs=1.06/hb=1.03), baseline(rsi_state+oi) PF=0.96 → 固化替换 rsi_state (审核修正: hs→rsi) |
| rsi_state_adaptive | 2026-08-29 | Phase Q1 D1 | 396 | 48% | REJECT (PF=1.07 vs rsi_state 1.09, -0.02; 信息量 6.4x↑ 但预测力↓) |

## JM 焦煤 (ha_body, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 53.3% | baseline 参照 |
| ha_body+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.0% | FAIL |
| rsi_state+oi+ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.0% | FAIL |
| ha_body+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 51.8% | FAIL |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 47% | 0 GREEN (best hs=0.90), 弱信号品种, 当前方案保持 |
| Phase 12 组合协变量 (2 cov × 2) | 2026-08-21 | Phase 12 | 396 | 52% | 0 GREEN (best hs+ha PF=0.98), 组合未突破 |
| Phase 13 组合探索 (18 tests) | 2026-08-22 | Phase 13 | 396 | 49% | 0 GREEN (最佳 hs+cal PF=0.87), 天花板确认 |
| Phase 15 新协变量 (4 tests) | 2026-08-23 | Phase 15 | 396 | 49% | 0 GREEN (最佳 vwap PF=0.86), 全面弱于 baseline 0.90 |
| stddev [returns std] | 2026-08-29 | Phase 15b | 396 | 52% | FAIL (PF=0.82 vs price-std 0.77, +0.05 仍<1) |
| vwap_deviation [decay fill] | 2026-08-29 | Phase 15b | 396 | 49% | FAIL (PF=0.83 vs 常数 0.86, -0.03), 衰减填充已回滚 |
| qstick_w28 [norm_window=28] | 2026-08-29 | Phase Q1 D2 (部分) | 396 | 49% | FAIL (PF=0.80 vs baseline 0.90, -0.10), 批次停止后 CANCEL |
| qstick_w42 [norm_window=42] | 2026-08-29 | Phase Q1 D2 (部分) | 396 | 50% | FAIL (PF=0.81 vs baseline 0.90, -0.09), 批次停止后 CANCEL |

## LH 生猪 (rsi_state, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| reversal_shadow+oi | 2026-08-03 | Phase 9 (2星->3星) | 231 | 55.4% | FAIL |
| ha_body+oi+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 231 | 58.0% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 231 | 56.7% | baseline 参照 |
| ha_body+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 231 | 57.6% | FAIL |
| ha_body | 2026-08-03 | Phase 9 (2星->3星) | 231 | 58.4% | PASS -> 已固化 |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 234 | 51% | 4 GREEN (rsi=1.24/rev=1.17/oi=1.14/ao=1.06), 固化 → rsi_state |

## M 豆粕 (ha_body+calendar_cyclical, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| calendar_cyclical [baseline] | 2026-07-30 | Phase 4d | 396 | 52% | 见STATE.md |
| calendar_cyclical [replace] | 2026-07-30 | Phase 4d | 396 | 56% | 见STATE.md |
| calendar_cyclical [additive] | 2026-07-30 | Phase 4d | 396 | 55% | 见STATE.md |
| ha_body+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 396 | 58.1% | PASS -> 已固化 |
| ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.8% | FAIL |
| vor | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.3% | FAIL |
| ha_body+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.0% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 56.3% | baseline 参照 |
| rsi_state+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 51.0% | FAIL |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-21 | Phase 11 (补跑) | 396 | 50% | 1 GREEN (cal=1.06), baseline(ha_body+calendar) PF=1.13 PASS → 保持当前方案 |

## MA 甲醇 (hourly_slope+oi, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| ha_body+hourly_slope | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 55.3% | 验证/MA优化 |
| bb_squeeze | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 53.5% | 验证/MA优化 |
| ao_accel | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 54.3% | 验证/MA优化 |
| vor | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 54.8% | 验证/MA优化 |
| baseline | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 53.8% | 验证/MA优化 |
| bb_squeeze+ha_body | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 54.5% | 验证/MA优化 |
| ha_body | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 55.0% | 验证/MA优化 |
| sar_dist+hourly_slope | 2026-08-18 | 协变量空白补测 批次D | 396 | 49% | FAIL (PF=0.80 vs baseline 0.71, 相对+12.7% 但绝对<1.0) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 50% | 0 GREEN (best PF=1.00, EV≤0), 当前方案保持 |
| Phase 12 组合协变量 (2 cov × 2) | 2026-08-21 | Phase 12 | 396 | 50% | 0 GREEN (best rsi+oi PF=0.84), 组合未突破 |
| Phase 13 组合探索 (18 tests) | 2026-08-22 | Phase 13 | 396 | 49% | 0 GREEN (最佳 rsi+cal PF=0.85), 天花板确认 |
| Phase 15 新协变量 (4 tests) | 2026-08-23 | Phase 15 | 396 | 48% | 0 GREEN (最佳 nvi PF=0.89), 全面弱于 baseline 1.00 |
| stddev [returns std] | 2026-08-29 | Phase 15b | 396 | 49% | FAIL (PF=0.79 vs price-std 0.77, +0.02) |
| vwap_deviation [decay fill] | 2026-08-29 | Phase 15b | 396 | 49% | FAIL (PF=0.78 ≈), 衰减填充已回滚 |

## P 棕榈油 (rsi_state+reversal_shadow, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.0% | baseline 参照 |
| rsi_state+oi+ha_body | 2026-08-03 | Phase 9 (2星->3星) | 396 | 51.3% | FAIL |
| ha_body+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 396 | 53.5% | PASS -> 已固化（G005 后经济失效，G004 替换） |
| rsi_state+reversal_shadow | 2026-08-17 | G003/G004 | 396 | 49.1% | PASS GREEN-EV → 已固化 (PF 1.014, EV 翻正) |
| ha_body+oi | 2026-08-03 | Phase 9 (2星->3星) | 396 | 52.5% | FAIL |
| candidate PB | 2026-08-04 | Phase 10 | 1584 | N/A | 待查文档 |
| candidate PC | 2026-08-04 | Phase 10 | 1583 | N/A | 待查文档 |
| candidate baseline | 2026-08-04 | Phase 10 | 1580 | N/A | 待查文档 |
| candidate PA | 2026-08-04 | Phase 10 | 1582 | N/A | 待查文档 |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 234 | 49% | 2 GREEN (cal=1.02/hb=1.02), baseline(rsi_state+rev_shadow) PF=1.10 PASS → 保持当前方案 |
| rsi_state_adaptive (单) | 2026-08-29 | Phase Q1 D1 | 396 | 49% | FAIL (PF=0.91; 非公平对比参考) |
| rsi_state_adaptive+reversal_shadow | 2026-08-29 | Phase Q1 D1 | 396 | 49% | REJECT (PF=1.00 vs rsi_state+rev 1.10, -0.10), 当前方案保持 |

## RB 螺纹钢 (rsi_state, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| ha_body+oi+reversal_shadow | 2026-08-02 | Phase 9 (2星->3星) | 396 | 53.0% | FAIL |
| ha_body+reversal_shadow | 2026-08-02 | Phase 9 (2星->3星) | 396 | 52.3% | FAIL |
| baseline | 2026-08-02 | Phase 9 (2星->3星) | 396 | 55.0% | baseline 参照 |
| ha_body+oi | 2026-08-02 | Phase 9 (2星->3星) | 396 | 54.8% | FAIL |
| rsi_state+oi+ha_body | 2026-08-02 | Phase 9 (2星->3星) | 396 | 52.5% | FAIL |
| ha_body+calendar_cyclical | 2026-08-02 | Phase 9 (2星->3星) | 396 | 52.5% | FAIL |
| ha_body+sar_dist | 2026-08-18 | 协变量空白补测 批次C (干净归因) | 396 | 53% | FAIL (PF=1.01 vs baseline 1.00, +1% 可忽略) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 53% | 5 GREEN (rsi=1.09/oi=1.09/hs=1.05/ao=1.05/rev=1.00), 固化 → rsi_state (审核修正: hs→rsi PF更高) |

## SH 烧碱 (reversal_shadow, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| baseline (ha_body) | 2026-08-21 | Task 3 初始 | 138 | 43% | PF=0.74 EV=-0.149 MaxDD=-51.2% 震荡型, stars=1 |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 138 | 46% | 0 GREEN (best rev=0.73), 弱信号品种, reversal_shadow 为最佳 |

## SP 纸浆 (calendar_cyclical, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| calendar_cyclical [baseline] | 2026-07-30 | Phase 4d | 396 | 57% | 见STATE.md |
| calendar_cyclical [replace] | 2026-07-30 | Phase 4d | 396 | 55% | 见STATE.md |
| calendar_cyclical [additive] | 2026-07-30 | Phase 4d | 396 | 57% | 见STATE.md |
| baseline | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 57.1% | 验证/MA优化 |
| ha_body | 2026-08-18 | 协变量空白补测 批次D (消融) | 396 | 48% | FAIL (移除calendar后PF 0.95→0.84, calendar有显著贡献) |
| rsi_state+oi | 2026-08-18 | 协变量空白补测 批次D | 396 | 50% | FAIL (PF=0.93, MaxDD-80.85% 改善但未达15%门槛) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 50% | 1 GREEN (cal=1.07), 待基线对比决策 |

## SR 白糖 (rsi_state+oi+calendar_cyclical, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| calendar_cyclical [baseline] | 2026-07-30 | Phase 4d | 396 | 55% | 见STATE.md |
| calendar_cyclical [additive] | 2026-07-30 | Phase 4d | 396 | 57% | 见STATE.md |
| calendar_cyclical [replace] | 2026-07-30 | Phase 4d | 396 | 57% | 见STATE.md |
| baseline | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 57.3% | 验证/MA优化 |
| sar_dist | 2026-08-18 | 协变量空白补测 批次A | 396 | 50% | FAIL (PF=0.93, EV<0, sar_dist孤立无价值) |
| rsi_state+sar_dist | 2026-08-18 | 协变量空白补测 批次B | 396 | 49% | FAIL (PF=0.93, sar_dist替换整个体系退化) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 51% | 1 GREEN (rev=1.03 ⚠️ 边界), baseline(rsi_state+oi+calendar) PF=1.10 PASS → 保持当前方案 |

## SS 不锈钢 (calendar_cyclical, 2星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| baseline | 2026-08-03 | Phase 9 (3星验证+MA) | 396 | 54.8% | 验证/MA优化 |
| reversal_shadow | 2026-08-18 | 协变量空白补测 批次A (固化验证) | 396 | 51% | GREEN (PF=1.08, EV=+0.040, 固化方案验证通过) |
| rsi_state+sar_dist | 2026-08-18 | 协变量空白补测 批次B | 396 | 52% | 近PASS (PF=1.13 vs rev_shadow +4.6%, 未达10%门槛) |
| reversal_shadow+calendar_cyclical | 2026-08-18 | 协变量空白补测 批次E | 396 | 51% | FAIL (PF=1.09 微升, MaxDD恶化-23%→-35%) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 53% | 4 GREEN (hs=1.05/rsi=1.09/oi=1.09/ao=1.05), 固化 → rsi_state (审核修正: hs→rsi PF更高) |

## TA PTA (calendar_cyclical, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| crack_spread (PX-TA) [replace] | 2026-08-01 | Phase 8a | 377 | N/A | FAIL (弱信号) |
| crack_spread (PX-TA) [additive] | 2026-08-01 | Phase 8a | 377 | N/A | FAIL (弱信号) |
| crack_spread (PX-TA) [baseline] | 2026-08-01 | Phase 8a | 377 | N/A | FAIL (弱信号) |
| ha_body+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 377 | 58.9% | FAIL |
| ha_body+calendar_cyclical | 2026-08-03 | Phase 9 (2星->3星) | 377 | 55.4% | FAIL |
| ha_body+oi+reversal_shadow | 2026-08-03 | Phase 9 (2星->3星) | 377 | 57.3% | FAIL |
| baseline | 2026-08-03 | Phase 9 (2星->3星) | 377 | 57.8% | baseline 参照 |
| ha_body+ao_accel | 2026-08-18 | 协变量空白补测 批次E | 396 | 52% | FAIL (PF=0.96 vs baseline 0.99, 退化) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 396 | 53% | 1 GREEN (cal=1.03 ⚠️ 边界), 固化 → calendar_cyclical |

## UR 尿素 (ao_accel, 1星)

| 协变量配置 | 日期 | 阶段 | n | DirAcc | 结论 |
|:---|:---:|:---|---:|:---:|:---|
| calendar_cyclical [baseline] | 2026-07-30 | Phase 4d | 396 | 54% | 见STATE.md |
| calendar_cyclical [replace] | 2026-07-30 | Phase 4d | 396 | 54% | 见STATE.md |
| calendar_cyclical [additive] | 2026-07-30 | Phase 4d | 396 | 53% | 见STATE.md |
| baseline | 2026-08-03 | Phase 9 (3星验证+MA) | 303 | 53.8% | 验证/MA优化 |
| ao_accel+oi | 2026-08-18 | 协变量空白补测 批次A | 306 | 48% | FAIL (PF=0.80, MaxDD=-120%) |
| ao_accel+reversal_shadow | 2026-08-18 | 协变量空白补测 批次A | 306 | 48% | FAIL (PF=0.80, MaxDD=-122%) |
| hourly_slope+reversal_shadow | 2026-08-18 | 协变量空白补测 批次E | 306 | 50% | FAIL (PF=0.85 vs baseline 0.84, 跨体系迁移无效) |
| Phase 11 单协变量穷举 (7 cov) | 2026-08-20 | Phase 11 | 306 | 49% | 0 GREEN (best PF=0.96), 当前方案保持 |
| Phase 12 组合协变量 (2 cov × 2) | 2026-08-21 | Phase 12 | 306 | 50% | 0 GREEN (best rsi+hs PF=0.99), 组合未突破 |
| Phase 13 组合探索 (18 tests) | 2026-08-22 | Phase 13 | 306 | 50% | 0 GREEN (最佳 rsi+cal PF=0.97), 天花板确认 |
| Phase 15 新协变量 (4 tests) | 2026-08-23 | Phase 15 | 306 | 50% | 0 GREEN (最佳 stddev PF=0.92), 全面弱于 baseline 0.97 |
| stddev [returns std] | 2026-08-29 | Phase 15b | 306 | 47% | FAIL (PF=0.81 vs price-std 0.92, -0.11 🔴 唯一退化), 例外待复评 |
| vwap_deviation [decay fill] | 2026-08-29 | Phase 15b | 306 | 48% | FAIL (PF=0.71 vs 常数 0.77, -0.06), 衰减填充已回滚 |

---
**总计: 21 品种, 228 次回测实验**