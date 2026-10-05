# 数据字典（data_dictionary）

> 品种、协变量、数据表、关键字段的**集中定义**。
> 阈值类见 [evaluation.md](./evaluation.md)；术语速查见 [glossary.md](./glossary.md)。
>
> 最后核实：2026-10-05，commit `ee01b56`。**本文不钉活快照**——品种数以代码为准。

---

## 1. 品种集合（三层，不等长）

⚠️ **三个集合大小不同**，这是最容易踩的坑：

| 层 | 数量 | 权威 | 用途 |
|----|-----:|------|------|
| `DEFAULT_SYMBOLS` | **28** | `data/config.py` | 数据采集的全集 |
| `SCHEMES` | **21** | `config/prediction_scheme.py` | 有生产预测方案的品种 |
| `target_symbols` | **24** | `scripts/praxist_goal.yaml` | 三环要攻坚的目标 |

**差集（2026-10-05 实测）**：

- `SCHEMES` 有但 goal 无：**`jm`（焦煤）** —— 有生产方案但不在三环目标内，**不是三环失败**
- goal 有但 `SCHEMES` 无：`oi` · `px` · `sc` · `y` —— 攻坚目标但还没有生产方案
- `DEFAULT_SYMBOLS` 有但 goal 无：`bz` · `eb` · `jm` · `pp` —— 只采数据，不参与预测/攻坚

> 「三环有 target 但没 SCHEMES」不代表失败——那是**尚未固化方案**的攻坚对象。

### 品种代码

`ao` 氧化铝 · `bu` 沥青 · `bz` · `cf` 棉花 · `cj` 红枣 · `eb` · `eg` 乙二醇
`fg` 玻璃 · `fu` 燃料油 · `i` 铁矿石 · `jd` 鸡蛋 · `jm` 焦煤 · `lh` 生猪
`m` 豆粕 · `ma` 甲醇 · `oi` · `p` 棕榈油 · `pp` · `px` · `rb` 螺纹钢 · `sc` ·
`sh` 烧碱 · `sp` 纸浆 · `sr` 白糖 · `ss` 不锈钢 · `ta` PTA · `ur` 尿素 · `y`

中文名以 `config/backtest_config.py::SYMBOL_NAMES` 为准（部分品种无映射）。

### 信用档

**无真实 3 星**。清单以代码为唯一事实源：

```python
from config.prediction_scheme import list_by_stars
list_by_stars(2)   # 可辩护档；CLI --three-star 映射到此
```

⚠️ **不要在任何文档里硬编码品种清单**——SS 已于 2026-09-17 降级（commit `9c7fc2a`），
写死的清单随降级动作腐烂。

---

## 2. 协变量 6 族受控词表

`cascade/cov_family.py::ALLOWED_FAMILIES` —— 提案的协变量族必须在此表内，否则 `invalid_covariate_family` 拒收。

| 族 | 含义 |
|----|------|
| `momentum` | 动量 / 趋势 |
| `calendar` | 日历效应 |
| `inventory` | 库存 |
| `macro_sentiment` | 宏观情绪 |
| `term_structure` | 期限结构（近远月价差） |
| `volatility` | 波动率 |

权威池：[../task_FM/config/covariate_pool.json](../task_FM/config/covariate_pool.json)（含 `active` / `archived` 状态）。

### horizon_known 四值词表

`cascade/horizon_fill.py::HORIZON_KNOWN_VOCAB` —— 声明该协变量**是否预先可知未来 horizon 段**：

| 值 | 含义 | 处理 |
|----|------|------|
| `known_ahead` | 真实可知（日历等） | 直接用真值，**须有 `known_ahead_evidence`** |
| `persistence` | 按 spec 填 **context 末值** | 替代历史 zeros / decay |
| `self_referential` | 自引用 | 专门处理 |
| `unknowable` | 不可知 | — |

**违反契约即抛** `HorizonContractError`（缺 pool 条目 / 词表外），**不静默兜底**。
分类唯一家在 `cascade/horizon_fill.py`（读 `covariate_pool.json`），
**禁止按协变量名硬编码分类**。

---

## 3. 数据库（每品种一个 SQLite）

`db/futures_<symbol>.db` —— **30 个文件**，每个含 7 张表。

### 3.1 核心表

| 表 | 内容 | 主键 |
|----|------|------|
| **`kline_1d`** | 日线 K 线 + 派生指标 | — |
| **`kline_1h`** | 1 小时 K 线 + 派生指标 | — |
| **`main_continuous_1d`** | 主力连续（**后复权**） | `dt` |
| `index_continuous_1d` | 指数连续 | `dt` |
| `contracts` | 合约元数据（`is_main` / `main_since` / `delivery_year`） | `contract_code` |
| `xreg_factors` | XReg 因子 | — |
| `metadata` | 键值元数据 | `meta_key` |

### 3.2 `kline_1d` 字段

**OHLCV**：`dt`（**开盘时间**，见 §4 防穿越）· `contract_code` · `open_price` · `high` · `low` · `close_price` · `volume`

**持仓**：`open_interest` · `oi_change` · `oi_trend_5d` · `oi_price_corr` · `volume_oi_ratio` · `oi_signal`

**均线**：`ma5` `ma10` `ma20` `ma60` · `ema12` `ema26`

**振荡**：`macd_dif` `macd_dea` `macd_bar` · `rsi6` `rsi12` `rsi24` · `kdj_k` `kdj_d` `kdj_j` · `boll_upper` `boll_mid` `boll_lower`

**其他**：`atr14` · `cci14`（仅日线）· `settle` · `change_pct` · `ccl_value` `ccl_label` · `updated_at`

### 3.3 `main_continuous_1d` 的复权字段

除 OHLCV 外还有：`raw_open` `raw_high` `raw_low` `raw_close`（**未复权原价**）
+ `adjustment_factor`（复权因子）→ 复权价 = raw × factor

> 预测输出为**后复权价**，等于**名义价格**——这是 System Hardening 的不变量之一。

---

## 4. ⚠️ 防穿越：两个不同的语义

| 场景 | 规则 |
|------|------|
| **回测** | 日线 `hour >= 15`（收盘后） |
| **实盘 predict** | 走 `get_safe_daily` |

### `kline_1h.dt` 是**开盘时间**（2026-09-28 修复）

`dt <= cutoff` 会把**目标首根**放进训练集 —— 1-bar 前视。
修法：`_h1_upper_bound = cutoff_ts − 1h`。

⚠️ **协议指纹测不出这类问题**（协议没变，数据语义变了）。
→ 修数据窗口类 bug 必须**强制重生基线**。

---

## 5. 机器真相源（jsonl / json）

| 文件 | 内容 | git |
|------|------|:---:|
| `task_FM/config/aligned_verdicts.jsonl` | **裁决注册表**，仅慢环可写 | ❌ |
| `task_FM/config/symbol_status.json` | 品种状态（`ACTIVE`/`DEAD`/`HOLD`） | ✅ |
| `task_FM/config/covariate_pool.json` | 协变量池权威源 | ✅ |
| `task_FM/config/family_registry.jsonl` | family 成员登记 | ✅ |
| `task_FM/config/preregistry.jsonl` | 预注册（append-only） | ✅ |
| `data/cache/supervisor_state.json` | 监督环活状态 | ❌ |

裁决的字段与判读 → [evaluation.md](./evaluation.md)
备份编年史与风险 → [run_artifacts.md §2](./run_artifacts.md)

---

## 6. checkpoint 命名规则

| 用途 | 格式 |
|------|------|
| 常规变体 | `data/cache/aligned_checkpoints/<vid>.jsonl` |
| 确认通道（命名空间隔离） | `{vid}__prereg_{prereg_id[:8]}.jsonl` |

隔离的目的是**防 resume 把探索点混进确认 DM**。

---

## 7. 运行产物

`task_FM/experiments/run_<YYYY-MM-DD>_<HH-MM-SS>_<tag>_task_FM/` —— 结构与分级见
[run_artifacts.md](./run_artifacts.md)。

⚠️ `cycle_NNN` 编号**跨运行段归 1**，不能用它判断快照缺口。