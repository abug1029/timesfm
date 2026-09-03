# 1 星 + PTA 品种协变量优化设计

**Status**: Approved (Phase 1 in progress)
**Date**: 2026-07-28
**Author**: Claude + chong pu
**Skill**: superpowers:brainstorming

---

## 1. 背景与目标

### 1.1 现状

FM_a 系统在 `config/prediction_scheme.py` 中固化了 20 个品种的预测方案。其中 6 个 1 星品种 + PTA 的协变量配置存在明确优化空间：

| 品种 | 当前协变量 | DirAcc | MAPE | 核心瓶颈 |
|:----|:----|:----:|:----:|:----|
| MA 甲醇 | hourly_slope+oi | 50% | 2.0% | 主协变量噪声过大 |
| CJ 红枣 | pca_momentum+bb_squeeze | 50% | 2.0% | combo 过拟、低流动性 |
| JD 鸡蛋 | gated_slope | 50% | 2.0% | Hurst 窗口与季节性失配 |
| EG 乙二醇 | bb_squeeze | 71% | 4.33% | 方向已优，MAPE/coverage 差 |
| LH 生猪 | ha_body | 67% | 7.62% | 结构性：基本面驱动，gap 多 |
| TA PTA | ha_body | 43% | 6.0% | 油/PX 驱动，技术无效（已归档） |

### 1.2 归因分类

将问题精准拆分为三类：

1. **技术特征过拟合/噪音**（MA、CJ）— 高频噪音协变量或复杂 combo 淹没主信号
2. **统计置信区间失配**（EG、LH）— 预测中枢对但方差预估不足
3. **缺乏基本面结构驱动**（TA、LH）— 价格由外部因子驱动，纯技术无解

### 1.3 目标

- 在双段验证（scan 快筛 + monthly_backtest walk-forward）下，对 6 个品种找到更优协变量配置
- 达到固化解锁阈值即可逐品种固化到 `prediction_scheme.py`
- TA 解冻参与本轮扫描，确认其技术上限；JD 日历特征列为下 Phase 独立立项

---

## 2. 工程前置（Phase 0）

### 2.1 问题

`scripts/covariate_scan.py` 的 `COVARIATE_TYPES` 列表过时——只含 11 种老协变量，缺 quant-trading 的 5 种（ha_body / reversal_shadow / bb_squeeze / ao_accel / sar_dist）。这导致扫描脚本根本测不到推荐的核心候选协变量。

### 2.2 修改

仅改 `scripts/covariate_scan.py`（允许区），不动保护文件：

- `COVARIATE_TYPES` 追加 5 种 quant-trading 协变量，共 16 种
- `COMBO_MODES` 追加 3 种新组合（含 P1 候选 `ha_body+oi` + 复刻 I/FU 现有固化 combo），共 7 种
- 不改扫描逻辑、评估口径、评估点数

### 2.3 验证

- `--help` 可加载
- 对 MA 跑 1 评估点，确认 quant-trading 协变量进入扫描循环（ha_body/sar_dist 出现在 TOP 5）
- 1 评估点 DirAcc=100% 不可信，仅为工程可用性验证

---

## 3. 实施路线（方案 C）

**结构**：工具 → 两批品种 → 双段验证闸门 → 逐品种固化

```
Phase 0: 补 scan 工具 ── 一次性
   │
   ├─ Phase 1: P1 批 (MA/CJ/JD) ── 易优化品种
   │     │
   │     ├─ scan 7点扫描 (独立子进程并行)
   │     ├─ monthly_backtest walk-forward 验证
   │     └─ 逐品种固化 (达阈即固化)
   │
   ├─ Phase 2: P2 批 (EG/LH/TA) ── 难优化品种
   │     │
   │     ├─ scan 7点扫描
   │     ├─ monthly_backtest 验证 (LH 加 clipping EV/PF)
   │     └─ 逐品种固化
   │
   └─ Phase 3: 跨品种一致性 + 文档收口
```

### 3.1 品种分批依据

| 批次 | 品种 | 可优化性 | 理由 |
|:----:|:----|:----:|:----|
| P1 | MA / CJ / JD | 🟢 重选 | 协变量明显不当，预期 +3~8% DirAcc |
| P2 | EG / LH / TA | 🟡 难 | 结构性或已接近上限 |

### 3.2 各品种候选

#### MA 甲醇（P1）

**诊断**：`hourly_slope` 是 1H 滚动斜率，对夜盘跳空 + 煤炭联动品种过于抖动。

候选：
1. `ha_body`（首选）— Heikin-Ashi 低通滤波平跳空，8 个品种通用最优
2. `ha_body + oi` 组合 — 复刻 I/RB 资金流补充，应对煤炭政策驱动的爆发

**注意**（用户补充）：测试 `ha_body + oi` 时需确保 OI 归一化不因合约换月产生断层跳跃——`calc_oi_pct_change` 用 `diff(OI)/OI.shift(1)`，换月时 OI 序列本身可能断层。扫描结果需对此做核验。

预期：DirAcc 50% → 55~58%。

#### CJ 红枣（P1）

**诊断**：低流动性、易操控、波动不规则。`pca_momentum + bb_squeeze` 双协变量在 50% 难品种上过拟。

候选：
1. `reversal_shadow`（首选）— 操盘常用长影线试盘，契合低流动性品种
2. `vor` — 量仓比 Z-score 捕捉控盘换手异常（参照 M 豆粕）

**注意**（用户补充）：CJ 用 `reversal_shadow` 时建议对影线长度设最低阈值，滤除无意义的日常小波动——这需在 `features.py` 改 `calc_reversal_shadow_ratio`（受保护，本轮不动）；当前 `lookback=20` 滚动平均已部分降噪，作为本轮 fallback。

**建议**：砍掉 combo 回到单协变量，short_range 模式下 horizon 段影响小，combo 复杂度收益不抵过拟风险。

预期：DirAcc 50% → 53~55%。

#### JD 鸡蛋（P1）

**诊断**：`gated_slope` 用 120bar Hurst 门控日线斜率，鸡蛋季节性切换更快（供给/节日需求），Hurst 慢窗口→门控滞后。CCL 异动极强但 CCL 仅以默认 `ccl_pct` 存在，未作强化协变量。

候选：
1. `ha_body + oi` — 用通用动量 + 显式持仓变化，复刻 I 铁矿石组合（同为周期波动品种）
2. `reversal_shadow` — 鸡蛋急涨急跌反转（季节切换点），影线信号契合

**日历特征**（用户补充，本轮不做）：鸡蛋季节性极强（端午/中秋前备货），引入 DayOfYear/Month 比换动量指标更降维打击。但日历特征是新协变量类型，需改 `features.py`（受保护），涉及 horizon 填充（未来日期已知，可精确填），列为下 Phase 独立立项。

预期：DirAcc 50% → 54~56%；EV 当前 +0.166 已正，目标别破坏它。

#### EG 乙二醇（P2）

**诊断**：DirAcc 71% 已是 1 星最高，bb_squeeze 抓住了 EG "低波动→突破"的油链节奏。真正问题是 MAPE 4.33% + coverage 0.600：方向对的价格错。这不是协变量能解的。

方向：
1. **不动 covariate**，调 `confidence_multiplier` 1.0 → 1.15~1.2（参照 FU/SH 的 1.1/1.2），展宽 P10-P90 提 coverage
2. 若仍想动协变量：试 `bb_squeeze + hourly_slope` combo，用 1H 动量补日内爆发

预期：covariate 不变；coverage 0.60 → 0.70，MAPE 不变（已是结构）。

#### LH 生猪（P2）

**诊断**：MAPE 7.62%（全场最高）、coverage 0.320（全场最低）、decay 1.06（信号不衰减）。生猪是猪周期/疫病/节日驱动的基本面市场，价格 gap 多、技术面抓不到 ASF 与母猪存栏信息。

候选（坦率：上限有限）：
1. `reversal_shadow` — 生猪 gap 后常现影线反转
2. `regime_gated` — 按 Hurst 切换协变量，应对周期切换
3. `confidence_multiplier` 1.2 → 1.4 — coverage 0.32 太低，必须大幅展宽

**EV/PF 评估**（用户补充）：LH 基本面 Gap 频发，计算 EV/PF 时需检查是否被极少数极端 Gap 扭曲回测，必要时对收益做截断（clipping）评估。本设计采用：5% 极端 Gap 截断后看稳定性，DirAcc 仅作参考。

诚实结论：DirAcc 可能从 67% 降到 60% 但 coverage 大幅上升、PF 改善。单看 DirAcc 不是 LH 的合理指标，应看 EV / PF（含 clipping）。

#### TA PTA（P2，解冻）

**诊断**：DirAcc 43% < 随机，模型在油/PX 驱动市场上系统性反向。归档决定原本是对的，但本轮解冻一起测，用最小成本确认其技术上限。

候选：
1. `regime_gated` — 震荡区切换协变量，oscillation 类型理论匹配
2. `short_horizon_only=True + 仅用 T+1~T+6` — 远端预测在震荡市必错，砍掉

诚实结论：TA 无纯技术解；真正优化要引入原油/PX 价差作为 `basis_momentum` 协变量（features.py 已支持，但需 store 层补基差数据）。这是项目级工程，建议单独立项。

---

## 4. 双段验证闸门

### 4.1 第一段：scan 快筛

`scripts/covariate_scan.py <symbols> --points 7`

- 7 评估点，间距 24 bars，horizon 24h
- 输出：每品种 24h MAE + DirAcc TOP 5
- 独立子进程，天然可并行

### 4.2 第二段：monthly_backtest walk-forward

`scripts/monthly_backtest.py <symbols>`

- walk-forward 正式回测
- 评审：DirAcc + MAPE 不退化（项目权威口径）

### 4.3 固化解锁阈值

scan 胜者达以下条件才固化：

- DirAcc ≥ 当前基线 + 2pp
- 24h MAE ≤ 当前基线
- scan 首名 ≥ 次名 0.3pp 缓冲（防次优 toggle）

且 monthly_backtest 验证：DirAcc + MAPE 不退化。

**LH 特例**：DirAcc 仅参考，看 EV/PF（含 5% Gap clipping）改善。

---

## 5. 保护规则遵守

- `config/prediction_scheme.py` — 受保护，固化时人工确认生效（本设计提供推荐，不自动写入）
- `cascade/features.py` — 受保护，本轮不改（JD 日历特征、CJ 影线阈值列为下 Phase）
- `scripts/covariate_scan.py` — 允许区，Phase 0 已改
- `scripts/monthly_backtest.py` — 允许区，仅运行不修改
- `reports/` — 允许区，只增

---

## 6. 成功标准

- Phase 0：scan 工具就绪，quant-trading 5 协变量可被测
- Phase 1：MA/CJ/JD 三个品种扫描 + backtest 完成；达阈者固化
- Phase 2：EG/LH/TA 三个品种扫描 + backtest 完成；达阈者固化（LH 看 EV/PF）
- Phase 3：跨品种一致性复扫；总结报告落盘
- Phase 3 工程债：启动 `ledger_backfill --all-unfilled` 回填 `db/live_ledger.db`，让 `health_stats` / `export_candidates(max_diracc=0.50)` 形成实盘退化自动监控，作为未来协变量重扫的触发器（固化后运行，非选型输入）

---

## 8. 领航员产出与 ledger 反馈环（探索结论 2026-07-28）

探索 `cascade/live_ledger.py` / `scripts/ledger_backfill.py` / `scripts/build_knowledge_base.py` / `docs/copilot.md` 后结论：

### 8.1 ledger 是"固化后监控"工具，非"选型"工具

ledger 设计上是协变量 A/B 实证金矿：
- `health_stats()` 按 `(symbol, cov_used)` 聚合 diracc_t24 / mae_t24_pct / mean_mae
- `export_candidates(max_diracc=0.50)` 直接导出"实盘 DirAcc 退化协变量 → 进扫描队列"

但当前实证状态（2026-07-28 探查）：
- 全 ledger 仅 7 条记录，均产生于今日 fm-collect-analyze 测试
- 6 个目标品种中仅 JD 有 5 条（全为 cov=gated_slope），EG/LH/MA/CJ/TA 零记录
- 0 条回填（`actual_t24 IS NULL` 全占）

"先填 ledger 再优化"无正收益——ledger 只能由未来 Copilot 预测实时写入，无法凭空创造历史；用历史数据模拟填 ledger 与 `covariate_scan.py` 重复（同模型、同评估点、同指标，循环引用）。

### 8.2 LH 验证快路径

LH 的 EV/PF 数据可走 L1 `reports/phase1/full_universe_neutral_r1_ops/ECONOMIC_VERDICT.json` 的 `pf_off` / `ev_off` / `dd_off`，不必等 monthly_backtest 全跑——LH 在 L1 中已是被记录的 over-veto 主导品种（ΔEV≈−10.80）。`max_adverse_excursion` 字段正是 clipping 评估所需。

### 8.3 角色定位

| 阶段 | ledger 角色 |
|:----|:----|
| 选型（Phase 1/2） | 不参与，主线走 scan + monthly_backtest |
| 固化后监控（Phase 3 之后） | 回填 + health_stats + export_candidates 形成反馈环 |

---

---

## 7. 不做（YAGNI）

- 不实现 JD 日历特征（下 Phase 独立立项）
- 不改 `features.py`（CJ 影线阈值等，下 Phase）
- 不补 store 层基差数据（TA basis_momentum，项目级立项）
- 不自动改 `prediction_scheme.py`（人工确认）
- 不跑全 20 品种扫描（只跑 6 个目标品种）

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

### 9.4 L1 VERDICT cov 字段优先级

`build_knowledge_base.py` 原优先读 L1 的 `cov` 字段（历史回测条件），导致固化后 KB 仍显示旧协变量。修复：优先 SCHEMES（当前生产配置），L1 仅作 fallback。KB 应反映生产状态而非历史快照。

### 9.5 scan 口径缺口修正建议（后续考虑）

未来优化中 `scripts/covariate_scan.py` 的评估指标应与 `monthly_backtest.py` 对齐：
- 当前: scan = 24h MAE + DirAcc (7点)
- 建议: scan 增加 walk-forward MAPE 子集（至少 50 点）作为固化解锁预筛口径

或：将 spec §4.3 的"MAE ≤ 基线"改为"walk-forward MAPE ≤ 基线"，scan 仅做方向排序。