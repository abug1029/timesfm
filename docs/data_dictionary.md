# 数据字典（data_dictionary）

> 品种、协变量、数据表、关键字段的**集中定义**。
> 阈值类见 [evaluation.md](./evaluation.md)；术语速查见 [glossary.md](./glossary.md)。
>
> 最后核实：2026-10-05，commit `ee01b56`。**本文不钉活快照**——品种数以代码为准。

---

## 1. 品种集合（四层，两组已对齐）

⚠️ **集合大小不同**，这是最容易踩的坑：

| 层 | 数量 | 权威 | 用途 |
|----|-----:|------|------|
| `DEFAULT_SYMBOLS` | **28** | `data/config.py` | 数据采集的全集 |
| `SCHEMES` | **21** | `config/prediction_scheme.py` | 有生产预测方案的品种 |
| `target_symbols` | **24** | `scripts/praxist_goal.yaml` | 三环要攻坚的目标 —— **单一来源** |
| `ALLOWED_SYMBOLS` | **24** | 从 `target_symbols` 派生 | 候选准入门（第一道硬检查） |

**2026-10-08 对齐裁定**：`target_symbols` 与 `ALLOWED_SYMBOLS` 曾是两份独立硬编码，
且准入门内容恰好等于 `SCHEMES`(21) 而非目标(24)，造成双向割裂 ——
`oi`/`px`/`y` 是攻坚目标却被准入门挡死（无法为它们产出任何候选），
`jm` 能过门但不被 goal 统计（孤儿）。现已归一：yaml 为唯一来源，evaluator 从它派生。
同期裁定：删 `sc`（原油，不再作为攻坚目标）、增 `jm`。

**当前差集（2026-10-08 实测）**：

- `target_symbols` == `ALLOWED_SYMBOLS`：**已恒等，均为同一 24 个品种**
- `SCHEMES` 有但 goal 无：**无**（原 `jm` 已补进目标）
- goal 有但 `SCHEMES` 无：`oi` · `px` · `y` —— 攻坚目标但还没有生产方案
- `DEFAULT_SYMBOLS` 有但 goal 无：`bz` · `eb` · `pp` —— 只采数据，不参与预测/攻坚
  （原清单里的 `jm` 已进入目标，故不再出现在此差集）
- `sc` 已退出攻坚目标，**但仍作为 `fu`/`bu` 裂解价差的原料输入保留**在
  `config/crack_spread_pairs.py` —— 那是数据依赖，不是研究目标，不要连带删除

> 「三环有 target 但没 SCHEMES」不代表失败——那是**尚未固化方案**的攻坚对象。

> 守卫：`tests/test_symbol_universe_20261008.py` 断言 `target_symbols` ==
> `ALLOWED_SYMBOLS`，并禁止 `ALLOWED_SYMBOLS` 退回内联字面量。漂移会直接测试失败。

### 品种代码

`ao` 氧化铝 · `bu` 沥青 · `bz` · `cf` 棉花 · `cj` 红枣 · `eb` · `eg` 乙二醇
`fg` 玻璃 · `fu` 燃料油 · `i` 铁矿石 · `jd` 鸡蛋 · `jm` 焦煤 · `lh` 生猪
`m` 豆粕 · `ma` 甲醇 · `oi` · `p` 棕榈油 · `pp` · `px` · `rb` 螺纹钢 ·
`sh` 烧碱 · `sp` 纸浆 · `sr` 白糖 · `ss` 不锈钢 · `ta` PTA · `ur` 尿素 · `y`

中文名以 `config/backtest_config.py::SYMBOL_NAMES` 为准（部分品种无映射）。

### 品种信心分级（信用档已退役）

**2026-10-08 信用档（`scheme.stars`）整体退役。** 原 1★/2★/3★ 体系不再存在。

**为什么退役**（四条证据，任一独立成立）：

1. **零决策参与** —— `praxist_supervisor.py` / `aligned_slow_loop.py` 从不读取它；
2. **自我声明脱钩** —— 模块 docstring 写明数值冻结在 2026-08 v2 月度回测口径，
   「不得作为 v23 证据引用」；
3. **服务目标不可达** —— 2026-08-03 结论「3 星不可达（DirAcc 天花板 ~58%）」；
4. **被"唯一事实源"固化成陈旧值** —— CF-10 A 把 `credit_stars` 唯一源钉成
   `scheme.stars`，于是 L1 证据 0/21 全缺失时仍输出 1~3 星，用冻结值冒充信心。

**取代方案（方案 A）**：信心分级改由 **L1 经济证据派生** ——
`build_knowledge_base.evidence_grade(historical_pf, historical_ev)`：

| 档位 | 判据 |
|------|------|
| `no_evidence` | L1 经济判决缺失或该品种无 PF（**证据缺失，显式暴露**） |
| `solid` | PF ≥ 1.20 且 EV > 0 |
| `positive` | PF ≥ 1.05 且 EV > 0（边际正） |
| `negative` | 有 PF 但不达门槛 |

**当前实测**：L1 `ECONOMIC_VERDICT.json` 不存在 → 21 个品种**全部** `no_evidence`。
这是事实陈述而非缺陷：产出 L1 经济判决后自动转为真实档位。

**保留部分**：`config/prediction_scheme.py` 的**固化预测参数全部保留**
（`covariate_type` / `dir_acc` / `mape` / `decay` / `scheme_type` /
`short_horizon_only` / `confidence_multiplier` / `signal_weight()` /
`confidence_band()` 等）—— 那是生产预测参数，不是评级。

**归档**：`two_star_critic.py` / `two_star_candidate_runner.py` → 
`scripts/archive/2026-10-08-credit-star-retired/`（服务 2★→3★ 晋级，
目标已判定不可达，自 2026-09-03 初始提交后从未更新）。

**CLI 变更**：`copilot.py --three-star` → `--evidence {solid|positive|negative|no_evidence}`；
`three_star_predict.run_all_three_star()` → `run_all_schemes()`（改跑全部固化品种，
文件名 `*_three_star.md` / `three_star_progress.log` 保持不变以兼容既有产物路径）。

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

`db/futures_<symbol>.db` —— 每品种一个文件，数量随采集范围变化（`ls db/futures_*.db | wc -l`），
每个含 7 张表。

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