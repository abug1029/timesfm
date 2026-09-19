# Task 5：数据管线与前视 / 幽灵 K 线

> 审核日期：2026-09-11  
> 活仓：WSL `/home/abug/timesfm`  
> 范围：三条生产路径（`scripts/copilot.py` / `scripts/cascade_predict.py` / `scripts/monthly_backtest.py`）的日线与 1H 截断契约；`run_guard` 入口；`ensure_fresh_data` 失败行为；SPEC-011 复权落点。  
> 只读。不改生产代码，不写库，不 push，不启动 Praxist。  
> 继承 Task 4 已确认、本任务不再争论：`STEP=2`、`EVAL_WINDOW_BARS=1200`；`BacktestDataStore` 用 `hour>=15` 才含当日日线；`get_safe_daily` 存在但 `DailyModel.predict` 仍裸读；`2fcb3ee` 只换了报告用 `daily_df`。

## 结论先行

**回测 PF 路径没有「夜盘日线含夜盘价」这种穿越。** ss 库内已收盘日线的 `close` 与当日 14:00 的 1H 收盘一致，不等于 21:00/23:00。`monthly_backtest` 在 21:00 评估点纳入当日日线，用的是 15:00 已定型的日盘收盘，不是后半夜价格。

**实盘建议路径仍有穿越。** `copilot` 和 `cascade_predict` 的日线模型都走裸 `DataStore.get_main_continuous`。夜盘采集会留下「下一交易日」的未完成日线；`future_bar_guard` 在夜盘故意允许这根标签；`get_safe_daily` 会丢掉它，但模型没用这个函数。ss 库在 2026-09-11 仍挂着 `2026-09-08` 日线，收盘 13860，与 `2026-09-07 21:00` 的 1H 收盘相同，且没有 09-08 的 1H——这就是未完成的下一交易日日线。

| 路径 | cutoff | 日线含当日？ | 1H 是否截到 cutoff | 一句话 |
|------|--------|--------------|---------------------|--------|
| copilot | 墙上时钟「现在」，无 `BacktestDataStore` | 含库内最新日线（无 15:00 掩码） | 否，取最新 `limit` 根 | 实盘建议：日线模型会吃未收盘 / 下一交易日盘中 bar |
| cascade_predict | 同上 | 模型裸读；**报告**走 `get_safe_daily` | 否，取最新 `limit` 根 | 模型与报告日线可以不是同一根 |
| monthly_backtest | 评估 1H bar 的完整时间戳 | `hour>=15` 含当日，否则前一日历日 | 是，`dt <= cutoff_ts`（含该 bar） | PF：夜盘含当日 ≠ 含夜盘价 |

**不要把 `monthly_backtest` 的 `hour>=15` 设计选择标成 PF 穿越。** Critical 只留给仍会影响实盘建议的裸读。

---

## 三条路径的日线 / 1H 契约

### copilot（实盘领航员）

调用链：

1. `main`：`ensure_fresh_data`（可 `--no-collect` 跳过）→ `refresh_intraday_1h`（只刷 1H）→ `run_one`
2. `run_one`：`with DataStore(symbol)` → `daily_model.predict(symbol, store, ...)` → `store.get_main_contract_1h(limit=ctx_bars)`（波动率雷达 / 最新价）→ `hourly_model.predict(symbol, store, daily_result, ...)`

证据：

```396:400:scripts/copilot.py
    with DataStore(symbol) as store:
        daily_model = DailyModel(shared_model=shared_model)
        daily_result = daily_model.predict(
            symbol, store, context_days=ctx_days, horizon_days=h_days
        )
```

```103:104:cascade/daily_model.py
        # 读取主链日线数据
        df = store.get_main_continuous(limit=context_days)
```

```87:90:scripts/copilot.py
    拉取 TqSdk 主力连续 1H，增量写入 SQLite。
    日线不重算（盘中用昨日收盘特征即可）。
```

- **cutoff 定义：** 没有。活 `DataStore`，SQL 无 `end_date`。
- **是否含当日日线：** 库里有就用。没有 `hour>=15` 掩码，也没有 `get_safe_daily`。
- **1H：** `HourlyModel.predict` 自己再读 `store.get_main_contract_1h(limit=480)`（`hourly_model.py:138`），同样无时刻截断；对实盘「现在」这是对的，前提是没有未来日期的幽灵 bar。
- **注释与代码冲突：** 注释写盘中用昨日收盘，代码仍把库内最新日线送进 TimesFM。夜盘 `daily_update` 之后，这根「最新」经常是下一交易日的未完成 bar。

### cascade_predict（实盘级联预测）

```97:108:scripts/cascade_predict.py
    with DataStore(symbol) as store:
        ...
        daily_result = daily_model.predict(symbol, store,
                                           context_days=ctx_days, horizon_days=h_days)
        ...
        from data.data_store import get_safe_daily
        daily_df = get_safe_daily(symbol, store=store)
        hourly_df = store.get_main_contract_1h(limit=ctx_bars)
```

- **cutoff：** 同 copilot，墙上时钟。
- **模型日线：** 裸 `get_main_continuous`（经 `DailyModel.predict`）。
- **报告日线：** `get_safe_daily`，只用于最后价、月表、报告日期（`:352-376`）。不回写 `DailyResult`。
- **1H：** 无 cutoff；`HourlyModel` 再读一遍最新 480 根。
- **预检查：** `ensure_fresh_data` 后 `symbols = valid_symbols`（`:840-841`）。全部失败则直接退出，不会硬跑。这一点比 copilot 干净。

`get_safe_daily` 规则（`data/data_store.py:166-188`）：

- `date < today` 保留
- `date == today` 且 `hour >= 15` 保留
- `date == today` 且 `hour < 15` 剔除
- `date > today` 无条件剔除（夜盘跨日标签）

生产里调用它的只有 `cascade_predict.py:107` 和 `tests/test_daily_freshness.py`。

### monthly_backtest（慢环 / PF）

```209:211:scripts/monthly_backtest.py
    with DataStore(symbol) as store:
        all_1h = store.get_main_contract_1h(limit=99999)
        daily_df = store.get_main_continuous(limit=99999)
```

开头这次裸读只用来切 `eval_indices` 和取 `real` 收益（未来 1H 作为标签，这是评估该有的，不是模型输入）。

每个评估点：

```267:283:scripts/monthly_backtest.py
        bar_ts = pd.Timestamp(all_1h["dt"].iloc[idx])
        ...
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        ...
        bt_store = BacktestDataStore(symbol, cutoff)
        ...
                daily_result = _daily_predict_cached(
                    daily_model, symbol, cutoff, CONTEXT_DAYS, HORIZON_DAYS,
                    daily_cache_dir, bt_store)
```

```789:826:data/data_store.py
    def get_main_continuous(self, limit=None, **kwargs):
        cutoff_hour = pd.Timestamp(self.cutoff_ts).hour
        if cutoff_hour >= 15:
            target_day = self.cutoff_day
        else:
            target_day = (pd.Timestamp(self.cutoff_day) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        return super().get_main_continuous(
            end_date=target_day, limit=limit, **kwargs
        )

    def get_main_contract_1h(self, limit=480):
        ...
                return self.get_klines_1h(
                    contract_code=code,
                    end_date=self.cutoff_ts,
                    limit=limit,
                )
```

- **cutoff：** 该评估 1H bar 的完整时间戳（禁止只截日期）。
- **日线：** `hour>=15` → `end_date=cutoff` 日历日；否则前一日历日（不是「前一交易日」，周末会落到周日，通常无 bar）。
- **1H：** `dt <= cutoff_ts`，含该评估 bar，不含其后同日 bar。
- **日线模型：** 同样 `DailyModel.predict` → `store.get_main_continuous`，但这里的 `store` 是已截断的 `BacktestDataStore`，所以回测日线有截止，实盘没有。

`tests/test_backtest_cutoff.py:110-120` 的 `test_daily_includes_cutoff_calendar_day` 仍断言 10:00 cutoff **含**当日。Task 4 已复现失败方向 `'2026-03-10' not found in {'2026-03-09'}`。测试锁的是旧合同，不能用来证明代码没修。

---

## 夜盘 `hour>=15` 含当日：是不是夜盘价？

这是 Task 4 留给本任务的判别题。只读打开 `db/futures_ss.db`（`file:...?mode=ro`），不经 `DataStore.init_db`。

### 已收盘日线 ≈ 日盘 14:00，不含同日历日夜盘

ss 近 12 个交易日（1H 合约 `SS_MAIN`）：

| 日线 dt | 日线 close | 同日 14:00 1H | 同日夜盘最后 1H | 匹配 14:00？ | 匹配夜盘？ |
|---------|------------|---------------|-----------------|--------------|------------|
| 2026-09-07 | 13885 | 13885 | 21:00=13860 | 是 | 否 |
| 2026-09-04 | 13845 | 13845 | 23:00=13925 | 是 | 否 |
| 2026-09-03 | 13825 | 13825 | 23:00=13830 | 是 | 否 |
| 2026-09-02 | 13765 | 13765 | 23:00=13815 | 是 | 否 |
| 2026-09-01 | 13805 | 13825 | 23:00=13760 | **否**（等于 00:00=13805） | 否 |
| 2026-08-31 | 13890 | 13890 | 23:00=13800 | 是 | 否 |
| 2026-08-28 … 08-24 | … | 均等于 14:00 | 不等于 23:00 | 是 | 否 |

TqSdk 日线 `dt` 是 `%Y-%m-%d`（`tqsdk_fetcher.py:175-176`）。1H 直方图只有 00/09/10/11/13/14/21/22/23，没有 15:00 标签；日盘最后一根是 14:00（14:00–15:00）。

**12 天里 11 天日线收盘 = 14:00 1H。** 夜盘 21:00 之后的价格在**下一交易日**的日线里，不在当日日线里。09-01 是数据质量异常（对齐 00:00 而不是 14:00），仍不是「含当晚 21:00+」。

### 完整交易日上 10:30 vs 21:00（2026-09-04）

| as-of | BacktestDataStore 日线上界 | 日线 last close | 1H last | 同日 cutoff 之后的 1H（若未截会漏） |
|-------|----------------------------|-----------------|---------|--------------------------------------|
| 09-04 10:00 / 10:30 | 09-03 | 13825 | 09-04 10:00 = 13850 | 11:00, 13:00, 14:00, 21–23:00 |
| 09-04 14:00 | 09-03 | 13825 | 09-04 14:00 = 13845 | 21–23:00 |
| 09-04 15:00 / 21:00 | 09-04 | **13845（=14:00）** | 21:00=13810 | 22:00, 23:00 |
| 09-04 23:00 | 09-04 | 13845 | 23:00=13925 | （无） |

21:00 评估点纳入的当日日线是 13845，不是 21:00 的 13810，更不是 23:00 的 13925。  
`get_safe_daily(now=09-04 10:30)` 与 10:30 的 `BacktestDataStore` 一样停在 09-03；`now=09-04 21:00` 停在 09-04。

**因此：回测夜盘含当日日线 ≠ 把未发生的夜盘涨跌喂给日线模型。** 不升 Critical。

### 库尾的未完成下一交易日日线（实盘才吃得到）

裸 `main_continuous_1d` 最后一行：

| 字段 | 值 |
|------|----|
| dt | 2026-09-08 |
| close | 13860 |
| volume | 33445 |
| updated_at | 2026-09-07 13:30:59 |
| 09-08 的 1H | **没有** |
| 最近 1H | 2026-09-07 21:00 close=**13860** |
| metadata `main_continuous_updated` | 2026-09-07 21:30 |
| metadata `1h_latest_SS_MAIN` | 2026-09-07 21:41 |

09-08 日线收盘正好等于周一夜盘第一根 1H，且没有周二日盘 1H。这是周一夜盘写下的「周二交易日尚未走完」的日线。

模拟（逻辑与代码同构，只读 SQL）：

| as-of | 裸 DataStore last | BacktestDataStore last | get_safe_daily last |
|-------|-------------------|------------------------|---------------------|
| 2026-09-08 10:30 | **09-08 / 13860** | 09-07 / 13885 | 09-07 / 13885 |
| 2026-09-08 21:00 | **09-08 / 13860** | **09-08 / 13860** | **09-08 / 13860** |

`DailyModel.predict` 走左列。盘中上午的实盘预测会把未完成的 09-08 当作已经收盘的一天送进 TimesFM，再变成 1H 的 `daily_slope` / `horizon_slope`（`cascade/features.py:87-135`，`cascade/daily_model.py:108-167`）。这会影响领航员卡片和级联报告里的可交易方向。

`validate_prediction_data` 第 4 项是「日线最后日期 ≥ 1H 最后日期 − 1 天」（`data_validator.py:39`）。日线**超前** 1H 时这项会通过，挡不住形成中的下一交易日日线。

---

## 幽灵 K 与补采

### `run_guard` 仍是唯一批量实现

`purge_future_bars` / `run_guard` 按 `date(dt) > max_allowed_daily_label(now)` 删除日线、主链、xreg、1H（`future_bar_guard.py:40-95, 124-206`）。仓内没有第二套 purge SQL。

生产调用点：

| 位置 | 角色 |
|------|------|
| `scripts/daily_update.py:292-300` | 日更末尾；失败 `SystemExit(2)` |
| `scripts/data_management.py:419-423` | `--validate` 无采集时仍跑一遍卫生 |
| `python -m data.future_bar_guard` | CLI |
| `tests/test_future_bar_guard.py` | 单测 |

`data_management.collect_daily`（`:166`）明确不再二次 purge，只委托 `daily_update`。实现入口仍唯一；「只有 `daily_update` 会调用」这句文档过严，`--validate` 也走同一函数。不构成散落删除。

夜盘语义（`trading_calendar.py:69-90, 118-135`）：会话进行中 `max_allowed` = 正在交易的交易日标签；周五夜允许下周一。**Guard 不会在夜盘删掉下一交易日的盘中日线。** 这是采集卫生，不是读侧截断。读侧本该由 `get_safe_daily` 负责，但预测没接上。

### `ensure_fresh_data` 在预测前会调用；失败不静默吞进 cascade，copilot 有一个回退坑

`cascade_predict.py:840` 与 `copilot.py:766` 都会在加载模型前调用。`monthly_backtest` 不调用（正确：用历史库）。

`_ensure_fresh_single`（`data_validator.py:318-322, 384-388`）：校验失败且 `auto_collect=False`，或采集后仍失败 → `was_fresh=False`，错误进 `FreshnessResult.errors`。批量模式只把 `was_fresh` 的品种放进 `valid_symbols`，其余进 `skipped_symbols`（`:455-462`）。**cascade_predict 只用 valid，全部失败则 return。**

copilot：

```764:769:scripts/copilot.py
    if not args.no_collect:
        ...
        valid, skipped = ensure_fresh_data(symbols, auto_collect=True)
        if skipped:
            print(f"  [SKIP] {skipped}")
        symbols = valid or symbols
```

部分失败时 `valid` 非空，脏品种会被丢掉。**全部失败时 `valid=[]` 为假，`valid or symbols` 回到原始列表，继续预测。** 会打印 SKIP，但不会停。这是失败路径上的脏数据，不是日常前视的主因；标 Important。

`ensure_fresh_data` 在 1H 滞后 <24h 时只补 1H（`:324-357`），不重写日线。与 copilot「盘中只刷 1H」叠加后，夜盘留下的下一交易日日线会一直留到下一次全日采集。

---

## SPEC-011 换月 / 复权落在哪条路径

合同（hardening spec §SPEC-011）：同时间戳截面比 `P_new(t)/P_old(t)`，向量化后复权，最新合约 factor=1.0，预测值即名义价。

代码事实：

1. **只挂在日线 `DataStore.get_main_continuous`**（`data_store.py:416-421`）。`get_klines_1h` / `get_main_contract_1h` **没有**复权。三条路径的日线读取（含 `BacktestDataStore` 的 `super()`、`get_safe_daily` 先调 `get_main_continuous`）理论上都会经过这里；1H 价格序列不经过。
2. **开关被 schema 短路。** 条件是 `"raw_close" not in df.columns`。`main_continuous_1d` 建表就有 `raw_close`（`data/db.py:119-122`）。ss 1686 行 `raw_close` 全是 NULL，但列存在，pandas 读出来就有这列 → **生产库上复权代码根本不跑。** `adjustment_factor` 全是 0.0，不是算出的累乘因子。
3. **即使跑，也不是合同里的截面比。** 真正被调用的是 `detect_rolls_from_price_gaps`（`data_store.py:84-110`），`roll_ratio = close[i]/close[i-1]`。这正是 spec v1.1 禁止的「混入当日涨跌」。`tqsdk_fetcher.detect_roll_events` 存在且有单测，但 `get_main_continuous` **没有调用它**；而且缺 `roll_ratio` 列时它会默认 1.0（空操作）。
4. 单测 `tests/test_system_hardening.py:TestSPEC011RollAdjustment` 只测 `apply_backward_adjustment_robust` 的向量化与 `detect_roll_events` 的合约切换，**不测读路径是否真的复权。**

结论：SPEC-011 不是「只在某一条生产路径上」——它在日线读函数里，但被列名短路，对 copilot / cascade_predict / monthly_backtest 都等于没开。1H 从未复权。这会造成日线与 1H 价位制度不一致的风险，但不是前视。标 Important，不标 Critical。

---

## Findings

### Critical

**C1 — 实盘日线预测裸读未收盘 / 下一交易日盘中日线，领航员与级联建议会吃到这根 bar**

- **合同：** 防穿越；`get_safe_daily` 的 15:00 掩码 + 剔除 `date>today`；copilot 注释「盘中用昨日收盘」。
- **代码 / 磁盘：** `DailyModel.predict` → `store.get_main_continuous`（`daily_model.py:104`）。copilot `run_one:398`、cascade_predict `:101` 都把活 `DataStore` 传进去。ss 库尾 `2026-09-08` close=13860 = `2026-09-07 21:00` 1H，无当日 1H。
- **为何影响实盘建议：** 最后一根日线进入 TimesFM context → `horizon_slope` 与历史 `daily_slope` 协变量 → 1H 点预测 → copilot 卡片 / cascade 报告。`validate_prediction_data` 只拦日线落后，不拦日线超前。
- **建议（不落地）：** `DailyModel.predict` 在非回测路径改走 `get_safe_daily`（或与 `BacktestDataStore` 同一套 15:00 / 跨日规则）。夜盘后、次日 15:00 前的实盘预测应以「最近已收盘交易日」为日线尾。

### Important

**I1 — `get_safe_daily` 只接到 cascade 报告；测试只覆盖 helper，不覆盖 `DailyModel.predict`**

- `get_safe_daily` 调用方：`cascade_predict.py:107`、`tests/test_daily_freshness.py`。
- `2fcb3ee` 名实不符（Task 4 已判，本任务用调用图确认）。
- 盘中 10:30：报告可能写昨日收盘，模型 context 仍含今日未收盘日线。执行者会对着两套数。

**I2 — copilot 在 `ensure_fresh_data` 全部失败时 `valid or symbols` 回退到原始列表**

- `copilot.py:769`。cascade_predict `:841` 没有这个回退。
- 失败会打印 SKIP，但仍可能对脏库做日线+1H 推理。

**I3 — SPEC-011 在生产日线读取上是死代码；1H 无复权；实现也不是截面比**

- 见上一节。三条路径一视同仁（都没真正复权），不是「只回测有 / 只实盘有」。

**I4 — `HourlyModel` 在非 `_MAIN` 对齐时调用未覆盖的 `get_klines_1h`，回测会丢掉时刻截断**

- `hourly_model.py:131-136`：`vr.contract_1h != vr.contract_daily` 且不是 `_MAIN` 时，`store.get_klines_1h(contract_code=..., limit=480)`。
- `BacktestDataStore` 只覆盖了 `get_main_contract_1h` / `get_main_continuous`，没有覆盖 `get_klines_1h`。
- ss 走 `SS_MAIN`，这条不触发。无 `_MAIN` 的品种在 `monthly_backtest` 里可能把 cutoff 之后的 1H 喂进模型，**那才会动 PF**。本任务未扫全品种是否都有 `_MAIN`。

**I5 — Guard 夜盘允许下一交易日标签，与读侧 `get_safe_daily` 的 `date>today` 不一致**

- 设计上 guard 保采集、读侧做截断。读侧没接到预测后，不一致就变成实盘污染（见 C1）。
- `run_guard` 另有 `data_management --validate` 调用点。实现仍唯一，文档「daily_update 唯一调用」过严。

**I6 — `data/AGENTS.md` 与 `test_backtest_cutoff` 仍锁旧 cutoff 合同**

- `data/AGENTS.md:32-44` 仍写「cutoff 为日期字符串」「`end_date = cutoff + 23:59`」。代码已是 bar 时刻 + `hour>=15`。
- `test_daily_includes_cutoff_calendar_day` 期望 10:00 含当日，与活代码相反。Agent 若按这份 AGENTS 或按这只「红」测试理解，会把已修的回测 1H 截断当成还没修。

### Minor

**M1 — ss 2026-09-01 日线收盘 13805 对齐 00:00 1H，不对齐 14:00=13825**

- 不改变「已收盘日线不含当晚夜盘」的主结论。像结算价或采集切片问题，留给数据质量，不是系统性地把 21:00 后价格写进当日日线。

**M2 — copilot 注释「盘中用昨日收盘」与裸读最新日线矛盾**

- 文档债，C1 的表象。

---

## 不升 Critical 的清单

| 嫌疑 | 为何不升 |
|------|----------|
| `monthly_backtest` 原始「无条件含当日」 | Task 4 已确认 `ee1f176` 修好；本任务用 ss 10:30 回退到前一日复验 |
| 夜盘 `hour>=15` 含当日日线 | ss 上该日线 = 14:00 收盘，不是 21:00/23:00；21:00 评估点用的是已于 15:00 可知的信息 |
| STEP=24 / 396 点 | 本任务禁止再争论；配置已是 STEP=2 |
| `monthly_backtest` 开头裸读全量日线 | 只做评估点过滤和标签 `real`，不进 `DailyModel` |
| 幽灵 K 散落 purge | 未发现第二套删除实现 |
| SPEC-011 未按截面比落地 | 价位制度问题，不是时间穿越 |
| `ensure_fresh_data` 失败 | cascade 跳过；copilot 回退是 I2，不是日常前视 |

---

## Evidence For

- **H1 实盘日线裸读（领先）：** `daily_model.py:104` + copilot `:398` + cascade_predict `:101` 源码；`get_safe_daily` 的 grep 只有报告和测试；ss 库尾 09-08 与 09-07 21:00 1H 同价、无 09-08 1H。
- **H2 回测夜盘含当日 = 含夜盘价：** 被 11/12 天 14:00 对齐证伪。09-04 21:00 的 BacktestDataStore 日线 13845 ≠ 1H 13810。
- **H3 Guard 非唯一调用但实现唯一：** `daily_update.py:297` 与 `data_management.py:422` 都 `from data.future_bar_guard import run_guard`；全仓 `purge_future` 无第三套 SQL。
- **H4 SPEC-011 死在列名上：** schema 有 `raw_close`；ss `raw_null=1686`；读函数 `if "raw_close" not in df.columns`。

## Evidence Against / Gaps

- **H1：** 若每次实盘前都先跑完整 `daily_update` 且 TqSdk 在 15:00 后把当日日线写成真正收盘，则盘后预测的「含当日」是合法的。C1 的危险窗口是**夜盘之后到次日 15:00 采集之前**，以及盘中误跑了日线采集。ss 在 09-11 仍留着 09-08 盘中 bar，说明这个窗口可以跨很多天，不只是几小时。
- **H1：** 本任务没有实际调用 `DailyModel.predict`（会加载 TimesFM）。用 SQL 复现了它会读到的最后一行，没有对 `horizon_slope` 做数值差分。因果链在代码里是连着的，缺的是一次「接上 get_safe_daily 前后斜率差多少」的对照。
- **H2：** 只探了 ss。其他夜盘更长的品种（到 01:00/02:30）日线是否仍等于 14:00，未扫。09-01 的错位说明个别日不是 14:00。
- **I4：** 未列出哪些生产品种没有 `{SYM}_MAIN`。

## Rebuttal Round

**对 C1 的最强反驳：**  
「09-08 日线其实是完整的周二，只是 1H 没采到；用它当最后一天不是穿越，只是数据陈旧。」

**为何 C1 仍成立：**  
行级 `updated_at=2026-09-07 13:30:59` 在周二日盘开始之前；close 与周一 21:00 1H **完全相等**；09-08 没有任何 1H。完整周二日线应等于周二 14:00，库里没有这根 1H，也没有别的价格来源能在周一下午写出「完整周二」。即便把 09-08 解释成 TqSdk 预分配的交易日 bar，它在周一夜盘也只含夜盘价，不能当已收盘日。

**对「夜盘 hour>=15 应升 Critical」的反驳（本任务允许升的那条）：**  
判别实验已经做了。已收盘日线不含同日 21:00+。回测 21:00 点纳入当日，用的是 15:00 可知的收盘。把这条升 Critical 会把设计选择写成已证实的 PF 穿越。

**对「get_safe_daily 已接入生产」：**  
cascade 报告段 `:352-376` 用它；`DailyResult.historical_closes` 不用它。模型与报告可以指向不同的最后一天。

## Convergence / Separation

- **收敛：** copilot 与 cascade_predict 的日线预测是**同一根因**（`DailyModel.predict` 裸读活 `DataStore`）。不要写成两个独立 bug。cascade 多出来的只是报告层掩码，会让问题更难从报告里看出来。
- **分开：** `monthly_backtest` 的 `hour>=15` 与实盘裸读**不是**同一机制。前者有 cutoff 且实证不含夜盘价；后者没有 cutoff 且实证会吃下一交易日盘中 bar。
- **分开：** SPEC-011 死代码 ≠ 时间穿越。
- **分开：** `run_guard` 夜盘放行下一交易日，本身正确；只有读侧不截断时才变成 C1 的上游。

## 当前最佳解释（仍可修正）

实盘两条预测入口把「库内最新日线」当成已收盘日。夜盘采集 + guard 放行会在库尾留下下一交易日的未完成日线。这根 bar 会进入日线模型，从而进入 1H 协变量和领航员建议。回测路径用 `BacktestDataStore` 的时刻截断，10:30 退回前一日历日，21:00 纳入当日已收盘日线（14:00），**不把未发生的夜盘涨跌算进 PF。** `get_safe_daily` 的规则对 10:30 / 跨日标签是对的，但没有接到 `DailyModel.predict`。

## Critical Unknown

生产上 copilot / cascade_predict 是否经常在「夜盘 `daily_update` 之后、次日 15:00 全日线重写之前」跑。ss 库在 09-11 仍留着 09-08 盘中日线，说明至少有一段时间没有后续全日采集来覆盖它；不知道这是运维空窗还是常态。

## Discriminating Probe

在一次真实夜盘 `daily_update` 之后、不写库、不加载 TimesFM：对同一 `DataStore` 比较 `store.get_main_continuous(limit=3)["dt"].iloc[-1]` 与 `get_safe_daily(symbol, store=store)["dt"].iloc[-1]`。若前者是下一交易日、后者是今日已收盘日，C1 在活数据上闭合。若要量化对建议的影响，再在隔离环境对这两份日线各跑一次 `DailyModel.predict`，比 `horizon_slope` 和 1H 方向。

## Uncertainty Notes

- 只深探了 ss。I4 的 `_MAIN` 覆盖率、其他品种日线是否一律等于 14:00，未扫。
- 未调用 TimesFM，没有斜率数值差。
- `get_safe_daily` 在「今天 21:00 但今日日线仍是昨夜未完成 bar、白天从未重写」时，`hour>=15` 会**保留**这根坏 bar（上表 09-08 21:00 行）。接上 helper 仍要处理「有今日标签但不等于 14:00」的陈旧盘中日线。
- 1H 实盘无 cutoff 是对的；未来日期幽灵 bar 依赖 `run_guard`。若只跑 copilot、很久不跑 `daily_update`，guard 也不会跑。
