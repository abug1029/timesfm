# Copilot 纸面使用流程

**定位**：把弱正品种的盘中预测记下来，满 24 根 1H 后对账。  
**不是**：自动下单、Vol 压平、用账本改 `prediction_scheme`。

权威口径：可交易方向 = 加权 1H（`docs/product_positioning.md`）。  
本流程当前**能记预测路径并对 T+24 终点对账**；Copilot 面板上的「方向」仍是日线斜率，见下方缺口。

---

## 品种

| 盘 | 品种 | 说明 |
|----|------|------|
| **主盘** | SS SR M JD | G005-E 弱正且 n≈396 |
| **观察** | CJ LH | 经济尚可，n<350，不升仓 |
| **不要当主盘** | `--three-star` 整表 | 会带上边界 EG/RB |

不要用 `python scripts/copilot.py --three-star` 当纸面入口。

---

## 周节奏

```
盘中/每个交易日
  copilot（主盘） → 自动写入 live_ledger
        ↓
满 24 根 1H 之后（通常次日或隔夜后）
  paper_loop backfill → 填 actual / 对错 / MAE
        ↓
每周一次
  paper_loop health → 只看退化报警，不改方案
```

成功标准：能回答「这四个品种这周盘中 T+24 方向对了几次、错的时候逆行多深」。

---

## 命令

环境：

```bash
# 激活共享底座
# source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a
```

### 1. 看账本

```bash
python scripts/paper_loop.py status
python scripts/paper_loop.py next
```

### 2. 盘中记一笔（写 ledger + 研报）

```bash
python scripts/copilot.py ss sr m jd
# 观察仓
python scripts/copilot.py cj lh --no-refresh
```

- 成功推理后自动 `insert_from_copilot_card`（`source=copilot`，`asof_ts`=最后一根 1H）
- 研报：`reports/daily/YYYYMMDD_HHMM_<symbols>.md`
- 不要用 `cascade_predict` 当纸面入口：它写 ledger 的 `asof_ts` 是墙钟，不是 K 线时间

盘后补记（不刷 TqSdk）：

```bash
python scripts/copilot.py ss sr m jd --no-refresh --no-collect
```

### 3. 回填真值（满 24 根 1H 才填得上）

```bash
python scripts/paper_loop.py backfill
# 等价: python scripts/ledger_backfill.py --all-unfilled --limit 200
```

未满 24 根会打印 `filled=False`，属正常，下个交易日再跑。

### 4. 健康表

```bash
python scripts/paper_loop.py health
python scripts/paper_loop.py health --json-out reports/live_cov_health/latest.json
# 若要看 cascade 历史行（asof 是墙钟，仅排障）:
python scripts/paper_loop.py health --source all
```

`candidates` = live DirAcc ≤50% 且 n≥3。只报警。改协变量必须走 `monthly_backtest.py` + 人工确认。

---

## 基础设施审核（2026-08-17）

| 件 | 状态 | 证据 |
|----|:----:|------|
| `db/live_ledger.db` + schema | **有** | `cascade/live_ledger.py` WAL |
| Copilot 写入 | **有** | `insert_from_copilot_card`；失败只打日志不中断 |
| asof = 最后 1H | **Copilot 有** | `last_1h_dt` |
| 从 `kline_1h` `_MAIN` 回填 | **有** | `backfill_run_from_1h`；单测通过 |
| 健康 / 弱候选 | **有** | `health_stats` / `export_candidates` |
| 主盘 1H MAIN | **有** | SS/SR/M/JD 均有数据，截面到 2026-08-17 |
| KB 20 品种 | **有** | `config/knowledge_base.json` |
| 单测 | **有** | `tests/test_live_ledger.py` 8/8 |

### 未完备（用的时候必须知道）

| 缺口 | 影响 |
|------|------|
| Copilot `direction` 仍用日线斜率（`_compute_direction`），未走 `position_from_forecast` | 面板「方向」≠ 回测可交易方向 |
| 回填 `dir_correct_t24` = `sign(pred_t24 − base)` | 健康表评的是 **T+24 终点**，不是加权 1H |
| ledger 无 `weighted_pred` 列 | 无法按产品契约复盘纸面仓位 |
| `cascade_predict` → `track_prediction` 的 asof 是 `now()` | 不要把 cascade 行当纸面样本 |
| KB `historical_pf` 来自 L1 Neutral-OFF，不是 G005-E | Copilot「历史 PF」会虚高或对不上月报 |
| 账本几乎是空的 | 2026-08-17 探查：个位数行；健康表没有统计功效 |
| 无法记「我主观跟没跟」 | 账本只有模型事件，没有你的动作 |

当前诚实用法：**把 Copilot 当日记（记路径），把 health 当 T+24 终点对错表。不要把面板方向当成纸面开仓方向。**

---

## 不要做

- 不要因一周 live DirAcc 就改 `prediction_scheme.py`
- 不要打开 Vol / Neutral 压平
- 不要用 3/7 点 scan 消化 `export_candidates`
- 不要把 L1 / KB 的 PF 和 G005-E 月报混成一张表
