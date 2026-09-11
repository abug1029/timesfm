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

### Testing Requirements

```bash
python -m unittest tests.test_future_bar_guard tests.test_basis_oi_filter -v
```

## Dependencies

### Internal

- `db/futures_<sym>.db`
- 被 `cascade/*` 与 `scripts/*` 调用

### External

- TqSdk、pandas、SQLite

<!-- MANUAL: -->
