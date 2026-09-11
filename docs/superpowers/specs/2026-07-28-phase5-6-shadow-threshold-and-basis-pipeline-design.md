# Phase 5+6 协变量优化设计（影线门控 + TA 基差管道）

> **文档状态（2026-09-11）**：**历史战役**。正文当考古。活 SCHEMES 以 `config/prediction_scheme.py` 为准。不要按本文改生产方案表。

**Status**: 历史战役（2026-09-11 标注；原 Draft）
**Date**: 2026-07-28
**Author**: Claude + chong pu
**Skill**: superpowers:brainstorming

---

## 1. 背景与目标

承接 `2026-07-28-covariate-optimization-design.md` §9 后续路线图。本轮聚焦两个独立但互补的方向，分独立 spec 处理：

| Phase | 品种 | 方向 | 性质 |
|:----|:----|:----|:----|
| 5 | CJ 红枣 | 影线阈值门控 | 现协变量调优（features.py 算法优化） |
| 6 | TA PTA | 近远月基差采集 + basis_momentum 实证 | 数据管道基建（采集层） |

**轮外**：Phase 4（JD 日历特征）、Phase 7（LH 基本面）各自独立立项，本轮不做。

### 1.1 Phase 5 动机

CJ 已固化 `reversal_shadow`（1星→2星，DirAcc 50%→53%，PF=1.14）。原 spec §3.2 指出 CJ 低流动性品种的影线含大量无意义日常小波动，建议设最小影线阈值过滤。本轮解决此遗留项。

### 1.2 Phase 6 动机

TA 在上一轮靠 `bb_squeeze` 从归档复活（stars 0→2，DirAcc 43%→56%，MAPE -62%）。但 spec §3.2 原话："真正优化要引入原油/PX 价差作为 basis_momentum 协变量……这是项目级工程"。

本轮认知修正：**近远月价差（期限结构 / 库存松紧）与原油/PX 跨品种价差（炼化利润）是正交的两个基本面维度**。先打通单一品种的近远月基差管道，是建立基差类协变量技术阶梯的最合理一步，跨品种时间轴对齐问题留给未来 Phase。

---

## 2. 现状核实

### 2.1 全品种 kline_1h 合约构成（致命发现）

实测全部 27 个品种库：

```
所有品种 kline_1h 仅有 1 个合约：{SYM}_MAIN（主力连续）
无任何品种有具体月度合约（如 ta2609）数据
```

根因：`data/cli.py:90` 与 `scripts/collect_1h.py:29-31` 仅调 `fetcher.get_main_continuous_kline`，从不采集具体月度合约。

影响：
- `data_store.py:399 get_basis_1h` 的 JOIN 逻辑（line 462-477）需要近月/远月**两个具体合约**在 `kline_1h` 中并存 → **对所有品种返回空**
- `cascade/features.py:974-1004` `basis_momentum` 协变量代码完整，但均匀零填充回退 → **全系统 basis 协变量是从未真正喂过数据的死代码**
- 只有 TA 因被诊断为"基差驱动"才撞上此缺口，其他品种没列 basis 候选故未暴露

### 2.2 数据层能力链核实（已就绪）

- `data/tqsdk_fetcher.py:119` `get_kline_1h(contract_code)` — **已支持具体合约代码**（如 `ta2609`），fetcher 层能力齐
- `data/contract_manager.py:61-74` `generate_contract_codes()` — **已能按当前日期生成未来 18 个月候选合约码**
- `cascade/features.py:974-1004` `basis_momentum` — 算法完整（含 `_decay_fill` horizon 填充）
- `data/data_store.py:399-487` `get_basis_1h` — 自动选 OI 最高的近月/远月并 JOIN 算 basis，**原样可用**（注入月度数据后无需改）

结论：本轮 Phase 6 只需补"采集 + 注入"，不涉及 features/store 的算法改动。

### 2.3 影线协变量跨品种影响（Phase 5）

`calc_reversal_shadow_ratio`（features.py:1465）当前被 4 个品种使用：**CJ、SS、FG、LH**（均为近两轮固化）。改此函数影响这 4 个品种已固化配置 → 必须零回归保证。

---

## 3. Phase 5 设计 — CJ 影线阈值门控（A+B 方案）

### 3.1 方案

**A（参数化复用）** + **B（独立命名注册）** 结合：

1. `calc_reversal_shadow_ratio` 增参 `min_shadow_atr: float = 0.0`，默认 0 → 现有 4 品种字节级不变
2. 注册新协变量名 `reversal_shadow_gated`（及 `_02/_03/_05` 三档用于 scan 裁决）
3. CJ scheme 的 `covariate_type` 从 `reversal_shadow` 改为胜出的 `reversal_shadow_gated_XX`

### 3.2 底层过滤逻辑（独立静默）

在 `calc_reversal_shadow_ratio` 内，`directional_shadow = lower_shadow - upper_shadow` 之前插入**双向独立滤除**（避免单向 Pin Bar 的有效影线被反向噪音稀释）：

```python
if min_shadow_atr > 0:
    threshold = min_shadow_atr * atr_val
    upper_shadow = np.where(upper_shadow < threshold, 0.0, upper_shadow)
    lower_shadow = np.where(lower_shadow < threshold, 0.0, lower_shadow)
directional_shadow = lower_shadow - upper_shadow
```

原理：影线需 ≥ 1/3 ATR 才视为有效试盘/反转（量化形态学标准）。0.3 是经验起点，scan 校准。

### 3.3 分发注册（两处 elif 链）

`features.py` 有两个独立分发串（无集中字典），均需加分支：
- `build_covariate_matrix`（单协变量，line 808+）`elif covariate_type == "reversal_shadow_gated":` → `calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.3)`，horizon 用 `_decay_fill`（与原 `reversal_shadow` 分支一致）
- `build_combo_covariate_matrix`（组合，line 1142+）`elif cov_type == "reversal_shadow_gated":` 同理

scan 阶段临时注册：`reversal_shadow_gated_02` / `_03` / `_05` 分别传 `min_shadow_atr=0.2/0.3/0.5`，scan 结束后保留胜者正式注册为 `reversal_shadow_gated`。

### 3.4 验证闸门

**零回归（强制前置）**：`min_shadow_atr=0.0` 时对 SS/FG/LH 三品种跑 `np.array_equal(改动前输出, 改动后输出)` 必须为 True — 证明字节级不变。

**双段（CJ）**：
- scan：`python scripts/covariate_scan.py cj --points 7`，三档 `reversal_shadow_gated_02/_03/_05` 进入评估，与原 `reversal_shadow` 横向比较，选 scan 最优档
- backtest：`python scripts/monthly_backtest.py cj`（用 scan 胜者），基线是刚固化的 `reversal_shadow`（DirAcc=53%, MAPE=2.64%, EV=+0.065, PF=1.14）
- 固化阈值（沿用上轮 spec §4.3）：DirAcc ≥ 基线+2pp 且 MAPE 不退化；或例外规则 PF>1.1 且 EV>0 且 DirAcc≥基线+3pp
- 达阈 → CJ scheme 改 `covariate_type` 为胜出的 gated 版；未达阈 → 保 CJ 现状 `reversal_shadow`，Phase 5 产出为"阈值过滤已实现 + 实证无明显增益"

---

## 4. Phase 6 设计 — TA 基差采集管道 + basis_momentum 实证

### 4.1 核心约束（关键风险预警）

**历史回测数据断层**：今天 OI 最高的近月/远月合约（如 TA2609/TA2701）在 2024-2025 远端要么不存在、要么 OI≈0。monthly_backtest 396 期 walk-forward 历史区间 JOIN 出全 NaN，basis_momentum 协变量崩溃。

**结果**：Phase 6 不以"固化"为唯一成功标准，而以"L1 管道打通 + 历史回测边界明确"为成功标准，保 bb_squeeze 为固化退路。

### 4.2 改动

**4.2.1 `scripts/collect_1h.py`（允许区）**：新增 `--with-basis <symbols>` 选项。命中时，在所有 `_MAIN` 采集 + `commit()` **之后**，对指定品种执行月度合约采集，套严格 `try/except`，单合约异常不阻塞主力合约：

```
1. contract_manager.generate_contract_codes() 拿未来 18 个月候选
2. 对每个候选调 fetcher.get_kline_1h(code)，记录 OI
3. 取 OI 最高的两个未过期合约（近月+次近月），calculator.calculate_all()，写入 kline_1h（contract_code=具体月度代码）
4. 失败/无 OI 的候选静默跳过（不污染库）
```

**4.2.2 `data_store.py` get_basis_1h（受保护，仅验证不改）**：原样可用。plan 验证步骤：采集后跑 `get_basis_1h(limit=480)` 断言非空 + basis 非全零 + 行数 ≥ 480。

**4.2.3 `cascade_predict.py` / `data_validator.py`（允许区，仅核实）**：确认 `ensure_fresh_data` 的 1H 时效性检查用 `_MAIN`，月度合约不参与。**不改逻辑**，仅补注释。

**4.2.4 `scripts/monthly_backtest.py`（允许区）**：跑 TA basis_momentum 时，回测区间每个评估点取该点时刻的近月/远月合约数据，若该点 NaN 占比 > 30%，**显式 SKIP 该点并记录原因**（zero-fill 不进入聚合指标）。判定逻辑：先实测 `get_basis_1h` 在 backtest 起止 dt 区间的返回，若整段为空/NaN>30% 全占 → 整品种 SKIP（不需改 backtest）；若仅远端区间 NaN → 改 backtest 加逐点 skip 逻辑。具体落点由实施时实测决定，本 spec 锁原则（fail-visibly，不 zero-fill 蒙混指标），不预判代码形态。

**4.2.5 TA scheme（prediction_scheme.py，受保护）**：仅当 L4 闸门通过才改 `covariate_type="basis_momentum"`；否则保持 `bb_squeeze`。

### 4.3 验证闸门（分层降级）

| 层级 | 成功标准 | 失败处理 |
|:----|:----|:----|
| L1 数据管道 | 采集后 `get_basis_1h(limit=480)` 非空、basis 非全零、≥480 行 | L1 失败 = Phase 6 工程失败，修复采集逻辑 |
| L2 scan 7pt | basis_momentum 进入 TOP5（方向有信号） | L2 因历史 NaN 退化 → 降级为"L1 就绪"产出 |
| L3 backtest 396pt | 预期大概率失败（历史区间无月度合约数据→NaN） | NaN>30% 显式 SKIP；失败不强行修复历史拼接 |
| L4 固化决策 | basis_momentum 达双段阈值（基线 bb_squeeze DirAcc=56%, MAPE=2.26%, EV=+0.120, PF=1.27） | 未达阈 → 保 bb_squeeze；产出="管道打通 + 历史边界明确" |

### 4.4 诚实预期

- 本轮 `basis_momentum` 是 TA 近远月价差（期限结构/库存松紧），**非跨品种原油/PX**。两者正交，跨品种因交易时段不对齐、NaN 处理复杂，列未来独立 Phase
- Phase 6 真正沉淀：**实时基差采集管道**（为实盘积攒数据）+ **历史 Rollover 缺口的位置探明**（为未来"历史移仓换月动态映射算法"指明确切起点）

---

## 5. 保护规则遵守

- `cascade/features.py` — 受保护，Phase 5 改 `calc_reversal_shadow_ratio`（加默认参数零回归）+ 两处 elif 链加分支，**Phase 6 不改**
- `config/prediction_scheme.py` — 受保护，固化时人工确认
- `data/data_store.py` — 受保护，Phase 6 仅验证 `get_basis_1h`，不改
- `scripts/collect_1h.py` / `monthly_backtest.py` / `cascade_predict.py` — 允许区
- `reports/` — 允许区，只增

---

## 6. 成功标准

- Phase 5：SS/FG/LH `np.array_equal` 零回归通过 + CJ 双段闸门运行完毕（达阈固化或产出"实证无明显增益"）
- Phase 6：L1 管道非空 + 至少跑通 L2 scan，明确 L3 backtest 历史 NaN 边界，固化或保 bb_squeeze
- 两个 Phase 各自独立验证，互不阻塞

---

## 7. 不做（YAGNI）

- 不实现 JD 日历特征（Phase 4）
- 不引入原油/PX 跨品种基差（未来独立 Phase）
- 不实现历史移仓换月（Rollover）动态映射（项目级工程）
- 不实现 LH 基本面数据（Phase 7）
- 不自动改 `prediction_scheme.py`（人工确认）
- 不跑全品种 basis 采集（仅 TA）

---

## 8. 后续路线（不在本轮范围）

- Phase 4：JD 日历特征（DayOfYear/Month 正余弦编码，改 features.py + horizon 填充）
- Phase 7：LH 基本面（母猪存栏/猪粮比，外部数据源）
- Phase 8（新增）：TA 跨品种原油/PX 基差（Crack Spread，交易时段对齐工程）
- Phase 9（新增）：历史移仓换月 Rollover 动态映射，让 historical basis_momentum 真正可用于长程回测