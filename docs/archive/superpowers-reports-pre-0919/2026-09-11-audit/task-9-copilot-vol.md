# Task 9：Copilot、纸面、Vol

- **任务**: 全系统审核计划 Task 9（只审盘中路径是否守红线，不改生产代码）
- **仓**: WSL `/home/abug/timesfm`
- **审核日**: 2026-09-11
- **对照**: `docs/product_positioning.md` CF-01 A / 生产红线、`docs/module_freeze.md` CF-12 A、`cascade/signal_contract.py`、`scripts/copilot.py`、`scripts/cascade_predict.py`、`cascade/vol_risk_filter.py`、`cascade/live_ledger.py`、`scripts/paper_loop.py`
- **单测（只读）**: 相关 7 个文件 → **53 passed, 3 skipped, 2 deselected**（12.26s）

**结论先说：**

1. **Vol / Neutral 压平默认 OFF，Copilot 不会被 overlay 静默拍平。** Copilot 没有 `--vol-filter-neutral`，也不读 `FM_VOL_FILTER`，不调用 `apply_neutral_override*`。雷达只打标签。
2. **Copilot 违反 CF-01 A。** 卡面主方向、领航建议、研报「方向」列、止损映射、ledger.direction 全部走日线 `_compute_direction_v2`；**UI/研报都不打印加权 1H**。`cascade_predict` / 月报回测已经走 `position_from_forecast`。
3. **无真实 3 星；Copilot `--three-star` = `list_by_stars(2)`。** 这条红线 Copilot 守住。纸面主盘不要用这条 CLI（会带 EG/RB），文档和 `paper_loop` 已写明。

---

## 红线记分卡

| 红线 | 盘中路径结论 | 证据 |
|------|----------------|------|
| Vol / Neutral 压平默认 **OFF** | **守住** | `cascade_predict.py:56-63,67,140-141,763-780`；`vol_risk_filter.py:354` `FM_VOL_FILTER` 默认 `"0"` |
| Copilot 预测 **永不因 Overlay 静默压平** | **守住** | `copilot.py:139-177,413-424`；无 `apply_neutral*` import；CLI 只有 `--no-vol-radar` |
| 可交易方向 = **加权 1H**（CF-01 A） | **Copilot 违反**；cascade_predict / 月报 **守住** | 见 I1 |
| 无真实 3 星；`--three-star` = `stars≥2` | **Copilot 守住**；cascade_predict 映射对、help 文案过期 | `copilot.py:14,728-729,743-745`；`SCHEMES` 最大 stars=2；KB credit_stars ∈ {1,2} |

---

## Step 1：压平互斥

### 1.1 Copilot 打不开 Neutral override

| 检查 | 事实 |
|------|------|
| argparse | `scripts/copilot.py:722-737`：`--three-star` / `--no-vol-radar` / `--no-refresh` 等。**没有** `--vol-filter` / `--vol-filter-neutral` / `--vol-filter-slope` / `--vol-thr` |
| env | 全文件 **零次** `FM_VOL_FILTER`、`is_vol_filter_enabled`、`VolRiskFilter.is_enabled` |
| 压平函数 | 全文件 **零次** `apply_neutral_override` / `apply_neutral_override_v2` / `force_neutral` |
| 预测 | `copilot.py:413-424` 注释「永不压平：始终用静态 scheme 出完整预测」；`HourlyModel.predict` 之后 **不** 改写 `point_forecast` |
| 雷达 | `evaluate_vol_radar`（`copilot.py:139-177`）调用 `filt.evaluate`，只把 `decision.veto` 写成 `high_vol`，并 **覆写文案为预警**。`decision.action`（源码里高波时是 `"neutral_override"`，`vol_risk_filter.py:387-399`）**没有**写进返回 dict，更不会拿去压平 |
| 下游 | `insert_from_copilot_card`（`live_ledger.py:453-487`）写入原始 `point_forecast`；`vol_high` 只是布尔标签 |
| 共享 import | `from scripts.cascade_predict import TICK_SIZE`（`copilot.py:29`）会加载 `cascade_predict` 模块，但压平只在 `run_cascade(..., use_vol_filter=True)` 里发生。Copilot **不** 调 `run_cascade` |

即使进程环境里 `FM_VOL_FILTER=1`，Copilot 也不会压平：它从不问 `is_enabled()`。雷达默认仍开（可用 `--no-vol-radar` 关），只打标签。

### 1.2 `cascade_predict` 默认 OFF；开关只影响声明过的入口

| 入口 | 默认 | 如何打开压平 |
|------|------|----------------|
| `scripts/cascade_predict.py` | OFF（`use_vol_filter: bool = False`，`:67`） | CLI `--vol-filter` / `--vol-filter-neutral` / `--vol-filter-slope` **或** `FM_VOL_FILTER=1`（`:56-63,753-766`） |
| `scripts/copilot.py` | 雷达 ON、压平不存在 | **无法打开** |
| `scripts/paper_loop.py` | 不跑 TimesFM | 无 Vol 开关 |
| `scripts/monthly_backtest.py` | 走 `position_from_forecast`；文档把 Vol 对比指到 `backtest_vol_gating.py` / `cascade_predict --vol-filter`（`:17-20`） | 月报本身不默认压平 |
| `scripts/backtest_vol_gating_fullchain.py` | 研究入口，显式调用 `apply_neutral_override` | 研究，非 Copilot |
| `cascade/hourly_model.py` | 无 `apply_neutral` / `FM_VOL_FILTER` | 模型层不压平 |

打开之后 `cascade_predict.py:174-195` 会调 `apply_neutral_override_v2`，并把原始路径留在 `HourlyResult.baseline_forecast`。这是 **显式实验开关**，不是静默 overlay。打开时会打印 `[WARN] Vol Gating ON`（`:768-770`）。

`VolRiskFilter.is_enabled`（`vol_risk_filter.py:351-354`）：

```
if cli_flag: return True
return os.getenv("FM_VOL_FILTER", "0") == "1"
```

默认字符串 `"0"`，只有精确等于 `"1"` 才开。

### 1.3 简报里的 `test_signal_mode_mutex.py` 不是 Vol 互斥锁

`tests/test_signal_mode_mutex.py:15-21` 锁的是 `SCHEMES` 里 `short_horizon_only=True ⇒ use_full_signal=False`（CF-06）。**不是** `--vol-filter-neutral` / `FM_VOL_FILTER` / Copilot 压平互斥。仓内 **没有**「Copilot 不得调用 `apply_neutral_override`」的测试。

---

## Step 2：建议文案 vs 信号（CF-01 A）

### 合同原文

- `docs/product_positioning.md:15-22`：可交易方向 = `sign(weighted_1H − base)` via `signal_weight` / short_horizon；**报告主方向、回测仓位、汇总排序** 用它。日线状态仅副标签。实现：`cascade/signal_contract.position_from_forecast`。
- `cascade/signal_contract.py:5-13`：**唯一可交易方向** = 加权 1H；「Production (cascade_predict / **copilot**) … MUST call `position_from_forecast`。Endpoint-only sign(pred[T+24]-base) is legacy。」
- `docs/product_positioning.md:24-28`：Vol 默认 OFF；Copilot 预测永不因 Overlay 静默压平；无真实 3 星。

### 2.1 Copilot 主方向 = 日线 `_compute_direction_v2`（违反 CF-01 A）

`scripts/copilot.py:384,433-446`：

- import `_compute_direction_v2`，**不** import `position_from_forecast`
- `direction = _compute_direction_v2(daily_result, scheme)`
- `delta_pct = (t24 / last_close - 1) * 100`（**T+24 终点**，不是加权 1H）
- 注释 `:435`：「终点涨跌：用 T+h 点 vs 当前（更直观）；**加权作补充**」—— **补充从未实现**

`_compute_direction_v2`（`cascade/daily_model.py:189-207`）：R²<0.35 强制「中性 → (形态分歧)」；否则 `horizon_slope` 与 `trend_threshold_pct/100` 比。这是 **日线副标签**，带阈值，会把小斜率拍成中性。

对照：`cascade_predict.py:208-230` 在有 1H 收盘时走 `position_from_forecast`，把 `direction` 写成可交易方向，`regime_direction` 才是日线。报告模板 `:530-548` 明确打印「**可交易方向**」和「日线状态(副)」以及「加权预测价」。

锁合同的测试：`tests/test_signal_contract.py:67-77` —— 日线 0.0005 分数/天 → regime 中性，仓位仍是 1H 看多。**Copilot 没有对等测试**；它会把这种截面的主方向打成中性。

### 2.2 UI / 研报 **不** 打印加权 1H

`CopilotCard`（`copilot.py:348-370`）字段：`direction, t4, t12, t24, delta_pct, daily_slope, ...`。**没有** `weighted_pred` / `position_sign` / `regime_direction`。

| 表面 | 印什么 | 加权 1H？ |
|------|--------|-----------|
| Rich CLI（`:513-560`） | 现价→T+24 终点%、核心轨迹 T+4/12/24、**日线斜率**、风险雷达、`advisory` | **无**。连 `c.direction` 都没有单独一行，只通过建议文案带出日线偏向 |
| 纯文本 CLI（`:576-598`） | 同样是 T+24 终点；**不印** 日线斜率行，也不印加权价 | **无** |
| Markdown 结论面板（`:617-630`） | 列名「方向」= `c.direction`（日线 v2）；涨跌 = T+24 `delta_pct` | **无** |
| Markdown 2.1（`:642-649`） | 日线斜率、1H 截面时间、Vol 敏感度 | **无** 可交易方向 / 加权价 |
| 止损（`:684`） | `generate_risk_bounds(c.direction, P10, P90)` | 按 **日线方向** 选多头/空头防线 |
| `variety_analysis.py:231-252,361` | 复用 `run_one`，报告写「**方向**: {cp['direction']}（T+24 预期 …）」 | **无** |

`craft_advisory`（`:247-318`）主句：

> 时效策略: … 当前方向偏向【{bias}】（T+24 预期 {dlt}）。

`bias` 来自日线 `direction`（`:238-244,285`）；`dlt` 来自 T+24 终点 `delta_pct`。同一句话里 **日线方向 + 终点涨跌**，两头都不是加权 1H。高波 HELPS 文案会劝「空仓观望」（`:293-297`）——这是 **明牌建议**，不是 overlay 改预测，不构成「静默压平」。

`craft_advisory_v2`（`:322-342`）处理 degraded/revoked，**单测有**（`tests/test_system_hardening.py:277-291`），**`run_one` 不调用**。活路径仍是 v1。当前 KB 全部 `slow_loop_status=ok`，暂未爆。

### 2.3 纸面账本评的是 T+24 终点，不是加权 1H

| 件 | 事实 |
|----|------|
| schema（`live_ledger.py:60-95`） | 有 `pred_t24` / `direction` / `daily_slope`；**无** `weighted_pred` |
| 写入（`:453-487`） | `direction=card.direction`（日线）；轨迹是未压平的 1H 点预测 |
| 回填对错（`:313-318,293-298`） | `dir_correct_t24 = sign(pred_t24-base) == sign(actual_t24-base)` |
| MAE/MFE（`:7-13,321-341`） | 仓位符号 = `sign(pred_t24-base)`，中性阈值 `1e-12` |
| health（`paper_loop.py:114`） | 自己打印：「dir_correct = sign(pred_t24-base)，**非加权1H**」 |

文档已承认缺口：`docs/paper_trading.md:6-7,111-122`、`docs/copilot.md:64`。这是 **已知债**，不是「文档说对了、代码偷偷改对了」。

---

## Step 3：其它红线

### 3.1 `--three-star` = stars≥2（无真实 3 星）

- `list_by_stars`（`prediction_scheme.py:513-521`）：默认 `min_stars=2`；注释写明 CLI 历史名映射到此表。活列表：`cj, eg, jd, lh, m, rb, sr, ss`（8 个）。`SCHEMES` **最大 stars=2**。
- Copilot：`:14,728-729,743-745` help 与实现一致：`list_by_stars(2)`。
- dataclass 默认 `stars: int = 3`（`prediction_scheme.py:82`）被每条 SCHEMES 覆盖；**不是** 活 3 星。
- KB `config/knowledge_base.json`：21 品种，`credit_stars` 只有 1 或 2。
- `craft_advisory` 仍有 `stars >= 3` 分支（`:267,311`）——死代码。`stars_label` 仍允许显示到 3 星（`:76-79`）。
- `cascade_predict.py:743-744` help 仍写「仅运行三星固化品种 (SS/UR/SR)」；实现 `:782-785` 已映射 `list_by_stars(2)`。**映射对，文案错。**
- 纸面：`paper_loop.py:26-28,38` 明确「不要用 `--three-star`」（会带边界 EG/RB）。主盘 CORE=`ss,sr,m,jd`。

### 3.2 文档合同（本任务范围内）与代码同向的部分

- `docs/copilot.md:8,11,64`：永不压平、Vol 仅预警、面板方向仍是日线 —— **与代码一致**。
- `docs/vol-risk.md:8-9,43-47,61-63`：压平默认 OFF；Copilot 复用模型做雷达 —— **与代码一致**。
- `docs/module_freeze.md:8`：CF-12 A 永不默认 ON；Copilot 仅预警 —— **与代码一致**。
- `docs/paper_trading.md` 把 Copilot 方向缺口和 T+24 对账缺口写清楚了。不要把这些再写成「文档撒谎」。

---

## Findings

### I1 — Important — Copilot 把日线斜率当主方向，违反 CF-01 A；UI/研报都不印加权 1H

- **合同**: `docs/product_positioning.md:15-22`；`cascade/signal_contract.py:5-13`（点名 copilot MUST 调用 `position_from_forecast`）。
- **代码**: `scripts/copilot.py:384,433-446,247-287,617-630,684`；`cascade/daily_model.py:189-207`；下游 `scripts/variety_analysis.py:231-252,361`。
- **对照正确路径**: `scripts/cascade_predict.py:208-230,530-548`；`scripts/monthly_backtest.py:50,329`；`tests/test_signal_contract.py:67-77`。
- **为何不是 Critical**: 预测点位本身没被改、不是自动下单、`docs/copilot.md:64` / `paper_trading.md:111-122` 已披露；cascade_predict / 回测仓位仍是加权 1H。危险在于 **人读 Copilot「方向」和止损防线时会跟日线走**，而日线带 0.1%/天阈值 + R² 门，会和加权 1H 反号或被拍中性。
- **建议（不落地）**: `run_one` 调 `position_from_forecast`：卡面 `direction` = `_sig["direction"]`（加权 1H）；另存 `regime_direction`。`delta_pct` 用 `weighted_pred`。CLI/研报同时印「可交易方向 / 加权价 / 日线状态」。`generate_risk_bounds` 跟可交易方向。`CopilotCard` 补 `weighted_pred`。加测试：日线中性 + 1H 看多时，Copilot 主方向仍看多。不要为了「和 Copilot 对齐」去改 `position_from_forecast`。

### I2 — Important — 纸面 health / MAE 用 T+24 终点符号，账本没有加权价，无法按产品契约复盘仓位

- **合同**: 同上，可交易方向 = 加权 1H。
- **代码**: `live_ledger.py:7-13,60-95,293-318,321-341,485`；`paper_loop.py:114`。
- **文档**: `docs/paper_trading.md:111-116` 已列缺口。
- **建议（不落地）**: schema 加 `weighted_pred` / `position_sign`（需迁移）；health 增加加权 1H DirAcc，T+24 终点保留为辅指标。在 I1 修好之前不要把 health 当「可交易方向对错表」。

### M1 — Minor — 「加权作补充」是空注释

- `copilot.py:435-436` 声称加权作补充，全文件无 `weighted` / `signal_weight` / `position_from_forecast`。
- **建议**: 删掉这句，或真的计算并展示（随 I1）。

### M2 — Minor — `craft_advisory_v2` 未接到 `run_one`

- 定义 `copilot.py:322-342`；活路径 `:445` 仍 `craft_advisory`。
- 测试锁的是 v2（`test_system_hardening.py:277-291`），生产看不到 revoked 冻结句。
- 当前 KB 全是 `ok`，暂无现场伤害。
- **建议**: `run_one` 改调 v2，或删 v2 避免双文案。

### M3 — Minor — `stars>=3` 死分支；`stars_label` 仍可画 3 星

- `copilot.py:76-79,267-270,311`。磁盘无 3 星。
- **建议**: 文案按 2 星封顶；或保留分支但注释「历史/不会触发」。

### M4 — Minor — `cascade_predict --three-star` help 仍写「三星固化 (SS/UR/SR)」

- `cascade_predict.py:743-744` vs 实现 `:782-785`。
- **建议**: help 改成与 Copilot 相同的「信用≥2星（历史名）」。

### M5 — Minor — 没有测试锁「Copilot 永不压平 / 主方向=加权 1H」

- `tests/test_copilot_advisory.py` 只测 `generate_risk_bounds` / tick。
- `tests/test_signal_mode_mutex.py` 与 Vol 无关。
- **建议**: 静态断言 Copilot 源码不含 `apply_neutral_override`；`run_one` 方向合同进 `test_signal_contract` 同类用例。

---

## 正面观察

- Copilot 把 Vol 做成雷达：覆写 `evaluate()` 的「Neutral Override / flat forecast」文案为「极高波动预警」，预测点位保持模型原输出（`copilot.py:157-172,413-424`）。这是 CF-12 A 在盘中路径上的正确姿态。
- `cascade_predict` 默认 OFF，打开时有 `[WARN]`，压平后仍把原预测放进 `baseline_forecast`（`cascade_predict.py:183-191`），不是偷偷改。
- 纸面入口与 `--three-star` 宇宙拆开（`paper_loop.py:26-40`；`tests/test_paper_loop.py:16-23` 锁 CORE/WATCH 仍在 2 星且不含 EG/RB）。
- `signal_contract.position_from_forecast` 把可交易方向和日线副标签拆开，`cascade_predict` 报告已经按这个印。
- ledger 写入失败只打日志、不中断 Copilot（`copilot.py:797-804`）；asof 用最后一根 1H（`live_ledger.py:470`），比 cascade 墙钟适合纸面。

---

## 与 Task 2 的衔接

Task 2 C1 已记录：`system_design.md` 把日线当主方向；`copilot.py:433-446` 与文档一致、与 CF-01 A / cascade_predict 不一致，交给 Task 9。本任务证实该分叉 **仍在**，且 UI/研报/建议/止损/variety_analysis/ledger.direction 全部跟日线。**不要按 `system_design.md` §5.1 去「统一」级联入口。** 该改的是 Copilot 去调用 `position_from_forecast`。

---

## CF-01 A 裁决（本任务必答）

**Copilot 是否违反 CF-01 A？是。**

证据：`scripts/copilot.py:433-446` 用 `_compute_direction_v2(daily_result, scheme)` 作为 `CopilotCard.direction` 和 `craft_advisory` 入参；全文件不出现 `position_from_forecast`；Markdown「方向」列（`:629`）和 `variety_analysis.py:361` 打印的就是这个日线字符串。加权 1H 既不计算也不展示。

**Copilot 是否违反「永不静默压平」？否。** 预测不被 overlay 改写。`--vol-filter-neutral` / `FM_VOL_FILTER` 只作用于 `cascade_predict`（及研究回测），与 Copilot 互斥。
