# Phase 9 有毒品种专攻设计 — AO 氧化铝 + JD 鸡蛋

> **文档状态（2026-09-11）**：**历史战役**。正文当考古。活 SCHEMES 以 `config/prediction_scheme.py` 为准。不要按本文改生产方案表。

**日期**: 2026-08-04
**前置**: Phase 9 全量实证 (73 作业, 15 品种)
**类型**: 协变量层优化

---

## 一、问题陈述

ha_body 是全系统最强 DirAcc 推升器（13 品种使用），但对部分品种有毒：

| 品种 | ha_body 表现 | 当前配置 | 当前 DirAcc |
|:--:|:--|:--|:--:|
| **AO 氧化铝** | EV 转负 (-0.054), MaxDD 翻倍 (-57.92%) | hourly_slope (单协变量) | 56.0% |
| **JD 鸡蛋** | ha_body 有害 (-3pp DirAcc, EV 转负) | rsi_state+oi (组合) | 52.0% |
| CF 棉花 | ha_body 单用有害 (-5pp) | ha_body+calendar (组合有效) | 56.0% |

CF 已在 Phase 9 中 4 候选全 FAIL，确认 ha_body+calendar 组合为最优，本次不纳入。

---

## 二、方法

**纯完整 walk-forward 回测**，逐个候选验证。不用 7pt scan 快筛（历史证明 scan DirAcc 高估 19-33pp，无参考价值）。

---

## 三、候选列表

### AO 氧化铝（9 个候选 + 基线对照）

| # | 候选 | 类型 | 依据 |
|:--:|:--|:--:|:--|
| 0 | **hourly_slope** (基线) | 单 | 当前配置, DirAcc 56.0% |
| 1 | ha_body | 单 | Phase 9 已测: EV 转负, MaxDD 翻倍 |
| 2 | ao_accel | 单 | 对 UR 有效 (70% DirAcc), 验证对 AO 是否同样有效 |
| 3 | vor | 单 | 波动率比率, 捕捉 AO 高波动特性 |
| 4 | bb_squeeze | 单 | 布林带突破, 适合 AO 波动率爆发 |
| 5 | reversal_shadow | 单 | 影线反转, 应对 AO 长影线扫损 |
| 6 | calendar_cyclical | 单 | 日历周期, 捕捉 AO 季节性 |
| 7 | hourly_slope+oi | 组合 | 当前基线 + 持仓量 |
| 8 | hourly_slope+calendar | 组合 | 趋势 + 季节性 |
| 9 | hourly_slope+reversal_shadow | 组合 | 趋势 + 反转信号 |

### JD 鸡蛋（8 个候选 + 基线对照）

| # | 候选 | 类型 | 依据 |
|:--:|:--|:--:|:--|
| 0 | **rsi_state+oi** (基线) | 组合 | 当前配置, DirAcc 52.0%, Phase 9 v2 PASS (PF+20.2%) |
| 1 | calendar_cyclical | 单 | 鸡蛋强季节性 |
| 2 | gated_slope | 单 | JD 的 Phase 4d-2 旧配置 |
| 3 | calendar_cyclical+gated_slope | 组合 | 季节性 + 趋势过滤 |
| 4 | ao_accel | 单 | 动量加速度 |
| 5 | bb_squeeze | 单 | 波动率突破 |
| 6 | reversal_shadow | 单 | 影线反转 |
| 7 | hourly_slope+oi | 组合 | 1H 斜率 + 持仓量 |
| 8 | rsi_state+oi+calendar | 组合 | 当前基线 + 日历周期 |

---

## 四、判定标准 (v2 裁决)

| 规则 | 条件 | 结果 |
|:---|:---|:---|
| R1 | MaxDD 相对恶化 >20% | 一票否决 |
| R2 | 仅 MAPE 达标时 PF 退化 >2% | 否决 |
| R3 | EV 从负翻正 | GREEN-EV PASS |
| R4 | MaxDD 绝对改善 ≥10pp 或相对 ≥30% + EV 未退化 | GREEN-MAXDD PASS |
| 常规 | MAPE 降 ≥3% OR DirAcc +3pp OR PF 升 ≥10% | PASS |

---

## 五、执行流程

1. 对 AO 的 9 个候选 + JD 的 8 个候选，分别跑 `monthly_backtest.py` walk-forward 回测
2. 汇总全部指标（DirAcc / MAPE / EV / PF / MaxDD / WinRate / Decay）
3. 应用 v2 裁决，标记 PASS / FAIL / GREEN-EV / GREEN-MAXDD
4. 若有 PASS 候选：
   - 比较多个 PASS 候选，选最优者
   - 更新 `config/prediction_scheme.py`
   - 运行 `build_knowledge_base.py` 刷新 KB
   - 运行回归测试确认无破坏
5. 保存实证报告

---

## 六、产出

- 实证报告: `reports/research/20260804_phase9_toxic_variety_study.md`
- 若 PASS: `config/prediction_scheme.py` 更新
- 若 PASS: `config/knowledge_base.json` 重建
- `LOOP.md` / `STATE.md` 同步更新

---

## 七、风险

- AO/JD 可能所有候选均 FAIL（如同 MA），结论为"当前已最优"
- 回测耗时较长，每个候选 ~15-20 分钟
- 总工作量: 17 候选 × 15-20min ≈ 4-6 小时
