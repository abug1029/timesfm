<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-11 -->

# data

## Purpose

期货数据管线：TqSdk 采集 → SQLite 每品种独立库 → 指标计算 → 预测/回测用的 `DataStore` / `BacktestDataStore`。

## Key Files

| File | Description |
|------|-------------|
| `config.py` | 品种/交易所 + `FM_ROOT` / `resolve_under_root`（**高风险**） |
| `data_store.py` | SQLite 读写；含 **`BacktestDataStore`**（walk-forward 截断） |
| `db.py` | 建表 schema |
| `tqsdk_fetcher.py` | TqSdk 拉取 |
| `indicator_calculator.py` | 技术指标列 |
| `trading_calendar.py` | 会话感知交易日（夜盘/周末） |
| `future_bar_guard.py` | 幽灵 K 线；**唯一批量入口 `run_guard`**（由 `daily_update` 调用） |
| `contract_manager.py` | 合约发现 / 主力 |
| `main_chain.py` | **DEPRECATED**（kline_1d → main_continuous 直同步） |
| `cli.py` | `python -m data.cli` collect/status/query |

## For AI Agents

### Working In This Directory

- 禁止自动改 `config.py`。
- 幽灵 K 线清理只走 `future_bar_guard.run_guard`，勿散落 purge。
- `db/` 只增不删；不手改生产 `.db` 结构。
- 回测截断契约：`BacktestDataStore(symbol, cutoff)` 的 **cutoff 是 bar 完整 datetime**。

### Critical: BacktestDataStore Cutoff Semantics

**现行（`ee1f176` 已修）**：cutoff 是评估 bar 的完整时刻，不是仅日期。

- 1H / 主力合约 OI：截到 `cutoff_ts`（含该时刻 bar）
- 日线：`hour >= 15`（含夜盘）则包含当日日线；15:00 前退到前一日历日
- 仅日期字符串按 **当日 00:00:00** 处理并打警告，不再扩成 23:59

```text
monthly:
  cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")   # 完整时刻
  BacktestDataStore(symbol, cutoff)
  get_main_contract_1h → end_date = cutoff_ts
```

~~旧行为（date-only + 23:59 → 同日 1H lookahead）~~ 已在 `ee1f176` 移除。

### Contract Series Mismatch

| 用途 | 序列 |
|------|------|
| 标签 / base（monthly） | `{SYM}_MAIN` 主力连续 |
| 预测上下文（BacktestDataStore） | cutoff 日 OI 最大具体月度合约 |

连续价与具体合约价可能不一致 → `delta_pred` 与 `delta_real` 尺度扭曲。

### Roll Adjustment (SPEC-011 / C10)

日线 `get_main_continuous` 只要帧里有 `raw_close` 列就**不**做换月后复权。`main_continuous_1d` 建表恒有该列（生产值常全 NULL），`SELECT *` 必带列，活路径等于永不调用 `apply_backward_adjustment_robust`。1H `get_klines_1h` 从未复权。活读到的是未后复权名义价。禁止未确认列语义就删 `raw_close`；截面比后复权未实现（现有检测是相邻价差比）。

### Testing Requirements

```bash
python -m unittest tests.test_future_bar_guard tests.test_basis_oi_filter -v
```

### 采集策略（2026-10-11 确立）

**核心原则**：1H 数据必须增量更新，禁止裸 DELETE（详见 `../CLAUDE.md` 数据采集设计原则章节）。

**权威实现**：
- `collect_1h.py` → `collect_1h_for_symbol()`：增量模式（INSERT OR REPLACE + MIN_1H_ROWS = 500 + 防御性 DELETE dt > new_max）
- `daily_update.py` → `collect_1h_main_only()`：已对齐 `collect_1h.py` 增量模式（2026-10-11 修复）
- `data_management.py` → `collect_1h()`：仅调用 `collect_1h.py`（2026-10-11 移除 `pull_history_1h.py` 调用）

**特殊路径**：
- `pull_history_1h.py`：**仅初始化/灾难恢复**用，全量 DELETE + INSERT。设计如此，必须有 `# ALLOWED: 初始化专用` 注释 + MIN_ROWS 保护。
- `backfill_gaps()`：数据不足时（`< MIN_1H_ROWS`）调用 `pull_history_1h.py` 是合法例外，已显式标注 `# ALLOWED`。

**数据源**：TqSdk（天勤量化），单一数据源。`data/akshare_fetcher.py.deprecated` 已废弃。

**保护机制**：
- `MIN_1H_ROWS = 500`：TqSdk 网络异常返回部分数据时，跳过写入防覆盖历史
- `tests/test_no_full_wipe.py`：AST 闸门检测裸 DELETE 模式，CI 必须通过

**历史教训**：
- 2026-07-15 Lesson #11："DELETE 全表 + INSERT 模式在数据采集场景都是定时炸弹"
- 2026-10-11 修复：`daily_update.py` 和 `data_management.py` 同步对齐增量模式

## Dependencies

## Dependencies

### Internal

- `db/futures_<sym>.db`
- 被 `cascade/*` 与 `scripts/*` 调用

### External

- TqSdk、pandas、SQLite

<!-- MANUAL: -->
