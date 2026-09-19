# Task 4：research 文档 vs 磁盘/代码

> 审核日期：2026-09-11  
> 活仓：WSL `/home/abug/timesfm`  
> 范围：`docs/research/slow_loop_evaluation_points_research.md` 全文；`docs/audit_system_efficiency_20260908.md` 只核对「已落地/未动」清单  
> 只读。不改生产代码，不 push，不启动 Praxist。

## 结论先行

研究文档仍以 2026-09-09 的「待执行修复」口吻号召：STEP=24 → 396 点、日内前视必须立即修。这已经不是活代码事实。

- `config/backtest_config.py` 现为 `STEP=2`、`EVAL_WINDOW_BARS=1200`（`ee1f176`）。
- `monthly_backtest` 的「无条件 `end_date=cutoff_day` 含当日日线」已在 `ee1f176` 改为 `cutoff_hour>=15` 才含当日；10:00 cutoff 的单测失败方向正好证明代码已回退到前一日。
- `get_safe_daily` 存在（`ba361df`），生产预测路径并未接到 `daily_model.predict`。`2fcb3ee` 提交说明写「接入 cascade_predict 生产路径」，实际只换了报告用的 `daily_df`。
- **不要把研究文档的过期号召写成代码仍穿越。** `monthly_backtest` 原始前视不标 Critical。夜盘 `hour>=15` 含当日、以及 copilot/cascade_predict 日线预测仍走裸 `get_main_continuous`，交给 Task 5 重追。

**前视现状一句话：** `monthly_backtest` 已不再无条件吞当日日线；`get_safe_daily` 在，但日线模型预测仍可能读到未收盘日线。

---

## 权威对照（git）

| commit | 日期 | 说明 |
|--------|------|------|
| `43144ee729f853f100bb9de7689fbde0cc87c001` | 2026-09-09 10:40:57 +0000 | 研究文档唯一提交；此后未改 |
| `feedf44006297f954655bea200946a90020bd357` | 2026-09-09 09:19:31 +0000 | evaluator aligned 上限 500→600 |
| `ee1f1762ba2b7ff8f961fa9e36eadc8c935f9743` | 2026-09-10 06:23:10 +0800 | STEP 24→2、EVAL_WINDOW_BARS=1200、日线 `hour>=15` 前视防护、评估窗口截断 |
| `ba361dfd300f742d0220c0b059a3f81611d3c722` | 2026-09-10 13:49:32 +0800 | 新增 `get_safe_daily` + `tests/test_daily_freshness.py` |
| `2fcb3ee8d518157fac9ea4697016d994b8d20826` | 2026-09-10 13:56:38 +0800 | 声称接入 cascade_predict 生产路径；diff 只有报告用 `daily_df` |
| `cd29bb67ef48193e704f1c3561c9424bf4350cab` | 2026-09-10 15:07:03 +0800 | Merge `feat/critical-fixes-v1.4`（含 SPEC-003） |
| `2206d4e528f4a54d6aaea0f0a7e893fbf00f2198` | 2026-09-08 09:18:23 +0800 | 效率审计文档；此后未改 |

研究文档头部仍写「状态：调研完成，待执行修复」「最后更新：2026-09-09」。磁盘上该文件 mtime 也停在 Sep 9 19:08。

---

## 主张清单与判定

判定口径：

- **仍成立**：现在仍为真（含「当时修过、现在仍保持」的历史事实）。
- **已修复但文档未改**：研究当时为真，代码/配置已变，文档仍用「当前/必须立即」。
- **从未成立 / 从未精确成立**：公式、提交说明或修复方案与磁盘不一致。
- **未复验 / 交给 Task 5**：本任务没有重查库内日线，或路径分叉超出研究原文。

### 主表（研究文档）

| # | 主张（压缩） | 出处 | 判定 | 证据强度 |
|---|----------------|------|------|----------|
| R1 | 状态「待执行修复」 | 文首、§7.3、§8、§10 | 已修复但文档未改 | Strong（git + 配置） |
| R2 | evaluator 硬顶 500，`feedf44` 改为 `(350, 600)` | §2.1、§7.1 | 仍成立 | Strong |
| R3 | supervisor 默认 400→600 | §7.1 | 仍成立（有一处死默认 400） | Strong |
| R4 | **当前** STEP=24 | §3.1 表、§8 | 已修复但文档未改 | Strong |
| R5 | STEP=24 + total≈10000 → **当前** 396 点 | 摘要、§1.3、§3.1 | 已修复但文档未改（当时算术成立） | Strong |
| R6 | 硬顶改 600 后实际仍 396 | §2.2 | 已修复但文档未改（当时成立） | Moderate（未重跑慢环） |
| R7 | `eval_indices = range(CONTEXT, total-H+1, STEP)` 无窗口截断 | §3.1 标 `monthly_backtest.py:215` | 已修复但文档未改 | Strong |
| R8 | 建议 STEP=2、EVAL_WINDOW_BARS=1200 尚未落地 | §5.2、§8 | 已修复但文档未改 | Strong |
| R9 | STEP=2 + 1200 bars = **600** 点 | §3.3、§6 | 从未精确成立 | Strong（公式） |
| R10 | 国内期货日均 5–6 根 1H（jd 约 4） | §3.3 | 仍成立（市场事实，本任务未重采） | Weak |
| R11 | TimesFM 主输入只有价格，不接收 datetime | §4.1 | 仍成立 | Strong |
| R12 | 交易日历断点 vs 预训练周期先验：未验证 | §4.1、§5.3 | 仍成立 | Moderate（负证据：仓内无该项实验） |
| R13 | RevIN 均值回归偏置：未验证 | §4.3 | 仍成立 | Moderate |
| R14 | `BacktestDataStore.get_main_continuous` **无条件** `end_date=cutoff_day` 含当日 | §4.2 代码块 | 已修复但文档未改 | Strong |
| R15 | 所有日内评估点都有前视，必须立即修 | 摘要、§4.2、§10 | 已修复但文档未改（回测无条件含当日已修） | Strong |
| R16 | 修复应改为**无条件前一日历日** | §5.1 | 从未按原文落地（落地的是 hour≥15） | Strong |
| R17 | 夜盘 21:00 / 上午 10:30 / 下午 14:00 均前瞻 | §4.2 表 | 10:30/14:00 回测已挡；21:00 仍含当日 → Task 5 | Moderate |
| R18 | 2026-09-08 日线盘中 `updated_at=10:39` close=5925 铁证 | §4.2 | 未复验库；机制对实盘路径仍相关 | Weak（当时快照，本次未查库） |
| R19 | 架构「日线定方向 + 小时定时机」 | §1.2 | 与现行 CF-01 A 冲突，研究当合同会误导 | Moderate（文档对文档；方向公式归 Task 6） |
| R20 | `goal.yaml` `aligned_max_points: 600` | §1.3 | 仍成立 | Strong |
| R21 | `get_safe_daily` 已接到 cascade_predict **预测**路径 | 非研究原文；`2fcb3ee` 说明 | 从未成立（只接到报告 `daily_df`） | Strong |

**计数：** 仍成立 7（R2, R3, R10, R11, R12, R13, R20）· 已修复但文档未改 8（R1, R4, R5, R6, R7, R8, R14, R15）· 从未成立/从未精确 3（R9, R16, R21）· 未复验/分叉 3（R17, R18, R19）。合计 21 条。

---

## Evidence For

### 研究当时的采样瓶颈（R4–R7，当时为真）

`ee1f176` 之前 `config/backtest_config.py` 是 `STEP = 24`，且 `monthly_backtest.py` 为：

```python
eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))
```

`range(480, 9977, 24)` 确实是 396 个点。研究把「evaluator 硬顶」和「STEP 采样」分层，这一层当时成立。

### 配置层 500→600（R2, R3, R20）仍在磁盘上

- `task_FM/evaluations/fm_eval/evaluator.py:126`：`"aligned": (350, 600)`（研究写的 `:124` 已漂移；`STAGE_POINTS` 在 124 行）。
- `scripts/praxist_goal.yaml:22`：`aligned_max_points: 600`。
- `scripts/praxist_supervisor.py:419,566`：`aligned_max_points=600`。
- `feedf44` 提交说明与现码一致。

### STEP / 窗口已按建议落地（R8）

`config/backtest_config.py:57-58`：

```python
STEP = 2                  # walk-forward 步长 (bars): 每天评估 3 次 ...
EVAL_WINDOW_BARS = 1200   # 评估窗口 (bars): 600 点 × STEP=2 ≈ 200 交易日
```

`scripts/monthly_backtest.py:220-222`：

```python
eval_start = max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)
eval_indices = list(range(eval_start, total - HORIZON + 1, STEP))
```

来源 commit：`ee1f176`。

### 回测日线无条件含当日已修（R14, R15）

`data/data_store.py:789-804`（`BacktestDataStore.get_main_continuous`）：

```python
cutoff_hour = pd.Timestamp(self.cutoff_ts).hour
if cutoff_hour >= 15:
    target_day = self.cutoff_day
else:
    target_day = (pd.Timestamp(self.cutoff_day) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
return super().get_main_continuous(end_date=target_day, limit=limit, **kwargs)
```

`scripts/monthly_backtest.py:283`：每个评估点 `bt_store = BacktestDataStore(symbol, cutoff)`，日线/1H 预测都走这个 store（`:290-312`）。

单测反证（Controlled reproduction）：

```
FAILED tests/test_backtest_cutoff.py::TestBarExactCutoff::test_daily_includes_cutoff_calendar_day
AssertionError: '2026-03-10' not found in {'2026-03-09'}
```

cutoff=`2026-03-10 10:00:00` 时日线只剩前一日。该测试写于 `10dbeb3`（2026-09-03），锁的是旧合同「含当日」；`ee1f176` 改代码后测试未改。`tests/test_daily_freshness.py` 6 条全过。

### TimesFM 主输入仍是价格数组（R11）

`cascade/daily_model.py:108,138`：`closes = df["close_price"]...` → `self.model.forecast(horizon=..., inputs=[closes])`。  
`cascade/hourly_model.py:145,237`：`hourly_closes` → `forecast_with_covariates(inputs=[hourly_closes], ...)`。datetime 只用于时效检查和协变量，不进主序列。

### `get_safe_daily` 存在、有测试、有调用者（控制器假设需确认的部分）

定义：`data/data_store.py:158-198`，规则与回测一致：`date < today` 或 `(date == today and hour >= 15)`。

调用者（全仓 `*.py`，排除 venv）：

| 文件 | 用途 |
|------|------|
| `data/data_store.py:158` | 定义 |
| `scripts/cascade_predict.py:106-107` | **报告** `daily_df`，在 `daily_model.predict` **之后** |
| `tests/test_daily_freshness.py` | 单测 |

`daily_model.predict` 自身：`cascade/daily_model.py:104` `df = store.get_main_continuous(limit=context_days)`，**不**调用 `get_safe_daily`。

---

## Evidence Against / Gaps

### 研究把「当前系统」冻在 09-09（R1, R4, R8, R15）

文档 §8 仍标 `data/data_store.py` / `backtest_config.py` / `monthly_backtest.py` 为「⏳ 待执行」。这三处都在次日 `ee1f176` 落地。继续按该文档「立即修前视 / 改 STEP=2」会改已经改过的生产路径。

### 「600 点」从未被公式给出（R9）

`n = floor((EVAL_WINDOW_BARS - HORIZON) / STEP) + 1 = floor(1176/2)+1 = 589`（在 `total >= CONTEXT+EVAL_WINDOW` 时）。再被 `max_points=600` 截也到不了 600。研究 §6 表写 600，是目标不是网格基数。

### 落地修复 ≠ 研究 §5.1 的无条件前一日（R16, R17）

研究要 `end_date=prev_day` 永远。代码在 `hour>=15`（含夜盘）仍 `end_date=cutoff_day`。`tests/test_daily_freshness.py:25-30` `test_night_session_daily_kept` 明确要求 21:30 **保留**当日日线。这是另一套合同：假定日线 15:00 收盘定型。若库内日线 close 含夜盘 21:00–23:00，则夜盘评估点仍可能前瞻。本任务**不**把它标成 live Critical；Task 5 必须查 `main_continuous_1d` 的日线收盘定义。

### `2fcb3ee` 说明过声称（R21）

```
feat(SPEC-003): integrate get_safe_daily into cascade_predict production path
- Replace raw get_main_continuous with get_safe_daily for daily data
```

实际 diff 只有：

```python
# scripts/cascade_predict.py 报告段
- daily_df = store.get_main_continuous(limit=500)
+ daily_df = get_safe_daily(symbol, store=store)
```

此前 `daily_model.predict(symbol, store, ...)` 已经用裸 `DataStore.get_main_continuous` 跑完日线预测（`cascade_predict.py:97-101` + `daily_model.py:104`）。

`scripts/copilot.py:396-400` 同样：`with DataStore` → `daily_model.predict(symbol, store, ...)`，全程无 `get_safe_daily`。

### supervisor 仍有一处 400 死默认（R3 的缺口）

`scripts/praxist_supervisor.py:1292`：

```python
aligned_max_points=cad.get("aligned_max_points", 400),
```

`goal.yaml` 有 600 时走不到这个默认。与 `feedf44`「3 处默认 400→600」不完全一致。Minor。

### 行号已漂移

| 研究引用 | 现在 |
|----------|------|
| `evaluator.py:124` aligned 元组 | `:126`；`:124` 是 `STAGE_POINTS = {` |
| `monthly_backtest.py:215` eval_indices | `:222` |

### R18 日线盘中更新：本次未查库

研究给出的 `updated_at=2026-09-08 10:39:07` 是当时库快照。本任务禁止当生产写入、也未 SELECT 日线表。不能把 09-08 快照当成 09-11 仍成立的库事实。代码路径上，实盘日线预测仍能吃到「若存在」的未收盘日线。

---

## Findings（按严重度）

### Important — 研究文档过期号召（文档债，不是活代码 Critical）

- **合同原文：** 「当前回测系统存在严重的前视偏差……必须立即修复的致命缺陷。」（研究摘要）；§8 三文件「待执行」。
- **磁盘事实：** `ee1f176` + 现码 `STEP=2` / `EVAL_WINDOW_BARS=1200` / `hour>=15` 截断；10:00 单测失败方向证明不含当日。
- **建议：** 给研究文档加「历史 / 已被 `ee1f176`+SPEC-003 取代」横幅；删掉「立即修复」祈使句。不要按该文档再改 `BacktestDataStore`。

### Important — `get_safe_daily` 未接到日线预测；`2fcb3ee` 名实不符

- **合同原文：** `2fcb3ee`「integrate get_safe_daily into cascade_predict production path」。
- **磁盘事实：** `cascade/daily_model.py:104` 仍 `store.get_main_continuous`；`cascade_predict.py:101` 先预测、`:107` 才 `get_safe_daily`；`copilot.py:396-400` 完全不走。
- **建议：** Task 5 沿 `copilot` / `cascade_predict` / `monthly_backtest` 三条日线读取画 cutoff。若盘中库仍有当日未收盘日线，实盘日线预测仍可穿越。本任务不升 Critical，因为未复验库、且回测路径已有独立截断。

### Important — `test_backtest_cutoff.py` 仍锁旧合同

- **事实：** `tests/test_backtest_cutoff.py:110-120` `test_daily_includes_cutoff_calendar_day` 在 cutoff 10:00 断言含 `2026-03-10`；现码返回 `{2026-03-09}`，测试失败。
- **建议：** Task 10 把该测试改成「10:00 必须不含当日」。失败测试不是「代码没修」的证据，而是「测试没跟着修」。

### Minor — 「600 点」网格算术

理论 n=589，不是 600。硬门 n≥350 仍可满足。不要把 396 vs 600 再当现行瓶颈。

### Minor — supervisor `cad.get(..., 400)`

`praxist_supervisor.py:1292`。goal.yaml 在则无害。

### 不升 Critical 的前视残留（交给 Task 5）

1. 夜盘 `hour>=15` 含当日日线——合同如此，是否等于夜盘价格泄漏取决于日线 bar 的收盘定义。
2. 实盘 `DailyModel.predict` 裸读 `get_main_continuous`。
3. `monthly_backtest.py:209-210` 开头用裸 `DataStore` 拉全量日线，只用于 `eval_indices` 日线充足性过滤，不进模型。不是预测穿越。

---

## `get_safe_daily` / BacktestDataStore 对照

| 路径 | 日线怎么读 | 含当日？ |
|------|------------|----------|
| `monthly_backtest` 预测点 | `BacktestDataStore.get_main_continuous` | cutoff hour≥15 含；&lt;15 前一日历日 |
| `monthly_backtest` 开头过滤 | 裸 `DataStore.get_main_continuous(limit=99999)` | 含库内全部日期（不进模型） |
| `cascade_predict` 日线模型 | `DailyModel` → 裸 `store.get_main_continuous` | 含库内最新日线（无 15:00 掩码） |
| `cascade_predict` 报告图/表 | `get_safe_daily` | 有 15:00 掩码 |
| `copilot.run_one` | 同日线模型：裸 `get_main_continuous` | 无掩码 |

**BacktestDataStore 是否仍 `end_date=cutoff_day` 含当日：** 不再无条件。`hour>=15` 时 `end_date=self.cutoff_day`（含当日）；否则 `end_date=前一日历日`。注意是日历日减一天，不是「前一交易日」（周末 cutoff 会跳到周日，通常无 bar，效果接近周五，但与研究写的「前一交易日」不完全相同）。

---

## 效率审计 `docs/audit_system_efficiency_20260908.md` 落地核对

文档日期 2026-09-08，git `2206d4e`，此后未更新。组件行数已过期（supervisor ~1100→1576，features ~2000→2163，data_validator ~250→627，vol_risk_filter ~400→760）。下面只核「修复计划」是否还对。

| ID | 审计当时主张 | 现在 | 判定 |
|----|----------------|------|------|
| F-001 | monthly_backtest DataStore 泄漏 | `monthly_backtest.py:209` `with DataStore`；`721ee47` | **已落地** |
| F-002 | XReg `except Exception` 吞掉且无 `failure_reason` | `hourly_model.py:247-253` 仍宽泛 except；无 `failure_reason` | **未动** |
| F-003 | checkpoint JSONL 无文件锁 | `:864-900` 改为「单写入者约定」+ 仍 `open(cp,"a")`，无 flock | **未按原方案落地**（用约定替代） |
| F-004 | 每次 predict 重编译 | `ensure_compiled` + `a8b0b6b`/`b32ec93` | **已落地** |
| F-005 | 测试硬编码 `D:/FlyBuddy/fm_a` | `tests/test_a2_p1_integrity.py` 改 `Path(__file__)`，`:1183` 断言不再含该路径 | **已落地** |
| F-006 | cascade_predict 无 `empty_cache` | 全文件无 `empty_cache`；monthly 仍有 `:278` | **未动** |
| F-007 | `pickle.load` vol 模型 | `vol_risk_filter.py:452` 仍 `pickle.load` | **未动** |
| F-008 | 主力合约检测忽略周末 | `_get_main_contract_at_cutoff` 仍 `dt <= cutoff_ts` 最大 OI，无交易日历 | **未动** |
| F-009 | 全库 print、无结构化日志 | monthly 60 处 print；data_store 有 logger 但未铺开 | **未动**（局部 logger 不算完成） |
| F-010 | sklearn 函数内 import | `features.py:15-16` 模块级 | **已落地** |
| F-011 | progress.log `write_text` 覆盖 | `_append_progress` + `08ac006` | **已落地** |
| F-012 | `days_stale==0` 才做 session 检查 | `data_validator.py:133` 仍 `elif days_stale == 0 and vr.valid_trading_hours` | **未动** |
| F-013 | `sys.path.insert` 不一致 | `monthly_backtest.py:31` 仍 insert | **未动**（低优先级） |
| F-014 | features 协变量长度无测试 | 现有 `test_calendar_cyclical.py` / `test_new_covariates.py` 等 shape 断言，不是审计要的全量 invariant | **部分落地** |
| F-015 | rolling Hurst Python for 循环 | `features.py:346` 仍 `for` 调 `calc_hurst_exponent` | **未动** |
| F-016 | cascade_predict 模型失败仍开 DataStore | 未在本任务逐行重追主循环 | **未复验** |
| F-017 | ThrPolicy 无全面测试 | `tests/test_vol_threshold_contract.py` 多条 | **已落地** |
| F-018 | calendar_cyclical horizon 忽略交易时间 | `features.py:2125-2151` 已用 `valid_hours` / `detect_trading_hours` | **已落地** |
| F-019 | `store_klines` `iterrows` | `data/data_store.py:245,279,315,357` 仍 iterrows + executemany | **未动** |
| F-020 | 30+ 协变量函数无单测 | 有 `test_new_covariates.py` 等，远非 30+ 全覆盖 | **部分落地** |
| F-022 | ATR 重复计算 | `features.py:1835,1864` 支持 `atr_arr` 注入，未确认所有调用点 | **部分落地** |
| F-021 | 回测函数无类型提示 | 未作为本任务重点 | **未复验** |

**效率审计计数：** 已落地 7（F-001,004,005,010,011,017,018）· 未动 9（F-002,003,006,007,008,009,012,013,015,019 中 F-003 算未按原方案）→ 未动记 10 若含 F-003 · 部分 3（F-014,020,022）· 未复验 2（F-016,021）。表内 F-003 单列「未按原方案」。合计对照 22 项中核对了 20 项。

Phase 1 原计划 5 项：落地 3（F-001,010,011），未按原方案 1（F-003），未动 1（F-006）。

---

## Rebuttal Round

**对当前领先解释的最强反驳：**  
「`test_daily_includes_cutoff_calendar_day` 失败，说明前视修复没生效 / 回测仍含当日。」

**为何领先解释仍成立：**  
失败方向是 `'2026-03-10' not found in {'2026-03-09'}`。这是 **10:00 已不含当日** 的直接实验证据，与 `data_store.py:796-799` 一致。测试锁的是 09-03 旧合同，不能用来证明代码没修。

**第二条反驳：**  
「`2fcb3ee` + `cd29bb6` 写了 SPEC-003，所以实盘也修了。」

**否：** `daily_model.py:104` 与 `cascade_predict` 调用顺序是源码事实。`get_safe_daily` 只过滤报告用的 `daily_df`（`:352-376` 价格/月表），不改变 `DailyResult`。

**第三条反驳：**  
「hour≥15 含当日，等于研究说的夜盘 2 小时前瞻仍在，应标 Critical。」

**否（本任务）：** 那是「日线 bar 是否含夜盘价格」的数据契约问题，研究当时用的修复是无条件前一日，代码有意没采用。没有 09-11 的日线 close 构成证据前，标 Critical 会把设计选择写成已证实穿越。Task 5 应用库内日线 `dt/close/updated_at` 与 21:00 cutoff 做判别。

---

## Convergence / Separation

- **收敛：** 「STEP=24→396」与「建议 STEP=2」收敛为同一根因（采样网格），且已在 `ee1f176` 落地。文档过期是单一文档债。
- **分离：** 回测 `BacktestDataStore` 截断 ≠ 实盘 `get_safe_daily` ≠ `DailyModel` 裸读。不能说 SPEC-003 merge 了就三条路径都安全。
- **分离：** 研究要的「永远前一日」≠ 落地的「15:00 阈值」。后者把夜盘评估点留在「含当日」集合里。
- **不收敛：** evaluator 硬顶 500 与 STEP=24 是两层瓶颈；前者 09-09 已修，后者 09-10 才修。文档把后者仍写成当前，会让人以为硬门 n 仍是 396。

---

## Current Best Explanation

研究文档是 **09-09 的正确诊断 + 未回写的修复清单**。控制器嫌疑成立：文档仍写 STEP=24/396/必须立即修前视；git 已有 `cd29bb6` / `2fcb3ee` / `ee1f176`；配置已是 STEP=2、EVAL_WINDOW_BARS=1200。

`get_safe_daily` **存在**；调用者只有 `cascade_predict` 的报告段和单测。`BacktestDataStore` **不再**无条件 `end_date=cutoff_day` 含当日。`monthly_backtest` 预测走 `BacktestDataStore`，原始日内前视（盘中 cutoff 吃当日收盘）按代码+失败单测应视为已修。

效率审计是另一份 09-08 快照：Phase 1 并未全部落地（F-006 仍缺，F-003 改成约定）。

本解释在「实盘日线预测是否此刻正在吃未收盘 bar」上是 **暂定的**：路径未接防护是确认的，库里有没有当日脏 bar 未查。

---

## Critical Unknown

盘中 `main_continuous_1d` 的当日行，close 到底是「日盘 15:00 结算」还是「随 1H/夜盘一直更新」？  
它把两件未决事项一次切开：夜盘 `hour>=15` 含当日是否仍穿越，以及 copilot/cascade_predict 裸读是否构成 live lookahead。

## Discriminating Probe（Task 5）

对一个有夜盘的品种（如 `ss`/`rb`），只读查询：

1. 取一条盘中 10:30 的 1H 与同日日线 `close` / `updated_at`（若有）对比；
2. 取 21:00 后再比一次；
3. 同时对同一 cutoff 分别调用 `BacktestDataStore.get_main_continuous`、`get_safe_daily(now_dt=cutoff)`、`DataStore.get_main_continuous`，列出最后一行 `dt`。

若 10:30 日线 close 已等于下午/夜盘价，则实盘裸读为 live 问题（可升 Critical）；若 15:00 后日线不再变，则夜盘含当日是安全合同，研究 §5.1 的「永远前一日」是过保守方案。

不要用「再改一次 STEP」当探针——网格已经改过。

---

## Uncertainty Notes

- 未重跑慢环，不知磁盘 verdict 的实际 n 是否已从 396 变成 ~589。R6 的「仍 396」只作为历史事实。
- 未打开任何品种 SQLite 核验 R18。
- CF-01 A vs 「日线定方向」只做文档冲突标记，方向函数归 Task 6。
- F-016/F-021 未核。
- `aligned_slow_loop.py` 调 `monthly_backtest` 并传 `max_points`；网格仍受 `STEP`/`EVAL_WINDOW_BARS` 约束。本任务未读 verdict JSONL。

---

## 给 Task 5 的交接

- 回测无条件含当日：**已修**。不要把研究摘要复制成代码 Critical。
- 必须重追：`DailyModel.predict` 三条入口的 store 类型；日线 bar 收盘定义；夜盘 cutoff。
- 单测债：`test_daily_includes_cutoff_calendar_day` 与现码相反，Task 10 改测试。

## 建议（不落地）

1. 研究文档改为 Historical，顶部写被 `ee1f176` / SPEC-003 取代。
2. 纠正 `2fcb3ee` 所暗示的「生产预测已防护」。
3. 若产品要实盘与回测同构：让 `DailyModel.predict` 在非 `BacktestDataStore` 时走 `get_safe_daily`（需另开 plan，本审计不改码）。
4. 效率审计另开「落地对照」或标明 09-08 快照；不要按其 Phase 1 清单当尚未开工。
