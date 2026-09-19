# Task 6：级联预测核心

- **任务**: 全系统审核计划 Task 6（只读生产代码，写报告）
- **简报**: `.superpowers/sdd/2026-09-11-full-system-audit/task-6-brief.md`
- **仓**: WSL `/home/abug/timesfm`
- **审核日**: 2026-09-11
- **范围**: `cascade/daily_model.py`、`hourly_model.py`、`features.py`、`signal_contract.py`、`walk_forward.py`、`config/prediction_scheme.py`（只读）、`tests/test_signal_contract.py`、`tests/test_compile_skip.py`、`tests/test_calendar_cyclical.py`；对照入口 `scripts/cascade_predict.py`、`scripts/monthly_backtest.py`、`scripts/copilot.py`
- **不改**: 生产代码、`SCHEMES`、模型、`.env*`；不启动 Praxist
- **Task 2 裁定（本任务不得推翻，已在代码复核）**:
  - 可交易方向合同是 CF-01 A：`cascade/signal_contract.position_from_forecast`（加权 1H）
  - `_compute_direction` 是幽灵函数；活函数 `_compute_direction_v2` 是日线副标签（R² 门）
  - `cascade_predict.py` / `monthly_backtest.py` 走 `position_from_forecast`
  - `copilot.py` 把 `_compute_direction_v2` 当卡面主方向——点名，细节归 Task 9
  - `horizon_slope` 存储单位是**分数/天**

**结论先说：** 日线 → 1H → 可交易方向这条生产链，在 `cascade_predict` / `monthly_backtest` 上守 CF-01 A。OI/CCL 的 horizon 段是零填充，日历是外推交易时段，**没有**把 cutoff 之后的真实仓单/持仓填进预测段。TimesFM **没有**走文档里的 `data.config.get_timesfm_model_path()`——这个函数不存在，加载硬编码 HuggingFace hub id；本仓 `models/timesfm-2.5-200m-pytorch` 是指向 HF cache 的符号链接，不是隔离副本。cosine rolloff 已实现但生产 `SCHEMES` 全关。compile-skip 在声称的 Daily/Hourly `predict` 路径上生效。

---

## 1. 真实合同（日线 → 1H → 方向）

| 环节 | 函数 | 单位 / 语义 |
|------|------|-------------|
| Stage 1 日线预测 | `DailyModel.predict`（`cascade/daily_model.py:86`） | 输入 250 日收盘；输出 `forecast` shape (22,) 价格 |
| 日线斜率存储 | `DailyResult.horizon_slope`（`:24, :151`） | `reg_slope / forecast.mean()`，**分数/天**（展示才 `×100` 成 %/天） |
| 日线副标签 | `_compute_direction_v2`（`:189`） | R²&lt;0.35 →「中性 → (形态分歧)」；否则 `horizon_slope` 比 `trend_threshold_pct/100` |
| Stage 2 1H | `HourlyModel.predict`（`hourly_model.py:89`） | context 480 根 1H + XReg 协变量；输出 `point_forecast` shape (24,) 价格 |
| 可交易方向 | `position_from_forecast`（`signal_contract.py:32`） | `sign(weighted_1H − T0 收盘)`；权重来自 `signal_weight` |
| 权重 | `signal_weight`（`prediction_scheme.py:524`） | 全段：`decay ** (-t/H)`；短段默认硬切前 `min(H//2,12)` 根 |
| 日线状态（副） | `trend_direction(daily_slope * 100, scheme)`（`signal_contract.py:89-91`） | 入参已经是 %/天；**从不改** `position_sign` |

**一句话合同：** 可交易方向 = `sign(signal_weight 加权的 1H 点预测 − T0 收盘)`，实现是 `cascade.signal_contract.position_from_forecast`；`horizon_slope` 存分数/天，只进 `regime_direction`；`_compute_direction` 不存在，`_compute_direction_v2` 只给日线副标签（含 R² 门）。

单测锁：`tests/test_signal_contract.py:66-75` — 日线 `0.0005` 分数/天 → regime 中性，仓位仍是 1H 看多。本次跑测：`pytest tests/test_signal_contract.py tests/test_calendar_cyclical.py tests/test_compile_skip.py -m 'not slow'` → **18 passed, 1 deselected**（慢测 `test_skip_vs_force_compile_bitexact_real_model` 未跑）。

---

## 2. Step 1：方向与权重，谁在生产路径上

对照 `docs/product_positioning.md:15-22` CF-01 A 与 `docs/system_design.md:313-332`（日线 `_compute_direction`，Task 2 C1 已定性为文档债）。

| 符号 | 仓内 | 生产路径？ |
|------|------|-----------|
| `position_from_forecast` | `cascade/signal_contract.py:32` | **是**：`cascade_predict.py:209-220,535-536`；`monthly_backtest.py:50,329`；A2 worker 同样 import |
| `signal_weight` | `prediction_scheme.py:524` | **是**（被 `position_from_forecast:80` 调用；报告表 `cascade_predict.py:480` 再算一遍只为展示） |
| cosine rolloff / `smooth_cutoff` | `prediction_scheme.py:99,543-553` | **否**。默认 `False`；`SCHEMES` 无一项设 `True`。只在 `tests/test_system_hardening.py:124-164` 用 `__new__` 打开 |
| 全段指数衰减 | `signal_weight` 第一分支 `:535-541` | **是**（`use_full_signal and not short_horizon_only`，SS/RB/M 等多数品种） |
| 短段硬切 12 根 | `:555-559` | **是**（`short_horizon_only=True`：`bu/p/cf/ao/cj`，`:290,:323,:338,:355,:418`） |
| `_compute_direction` | **不存在** | 幽灵。全仓无此 def |
| `_compute_direction_v2` | `daily_model.py:189` | **不是**可交易仓位。用途：① `DailyModel.summary:180` 日线摘要；② `cascade_predict.py:296` 报告「日线状态」；③ **`copilot.py:433-434` 卡面主方向**（Task 9） |
| 终点 `sign(pred[T+24]-base)` | `position_from_forecast` 在 `scheme is None` 时的回退（`:59-63`） | 无 scheme 才走；生产 `get_scheme` 有固化项时不走 |

`cascade_predict.py:208` 注释写明「可交易方向=加权1H」。`monthly_backtest.py:324-334` 注释写明「Live-aligned signal: signal_weight / short_horizon (not endpoint-only)」，`position_sign` 进 PnL（`:352`）。

`cascade/walk_forward.py` **不是**生产 walk-forward：它是协变量 IS/OOS 的 IR 选择器（文件头 `:3-5` 写明勿用于固化 SCHEMES）。生产 WF 入口是 `scripts/monthly_backtest.py`。

`signal_contract.py:12-13` 文档字符串写「Production (cascade_predict / **copilot**) … MUST call `position_from_forecast`」。**代码事实**：`copilot.py` 不 import 该函数，`direction = _compute_direction_v2(...)`（`:384,433-434`），`delta_pct` 用终点 T+h（`:435-437`）。这是合同文件自己的谎言，细节归 Task 9，本任务只点名。

`config/AGENTS.md:43-44` 仍写「实盘 `cascade_predict` 用 daily_slope 定方向，回测用终点符号」——**已过期**，与现行代码相反。不要按这份 Known Issues 去改回测。

---

## 3. Step 2：协变量 context vs horizon（防穿越）

XReg 输入由 `build_covariate_matrix` / `build_combo_covariate_matrix`（`features.py:992,1410`）拼 `context + horizon`。`HourlyModel.predict` 把整段交给 `forecast_with_covariates`（`hourly_model.py:239-244`）。

原则：日历在 horizon 段用**未来可知**的日历；OI/CCL 若把 cutoff 之后的真实值填进去才是偷未来。

### 3.1 点名：horizon 怎么填

| 协变量 | 函数 | context | horizon | 判定 |
|--------|------|---------|---------|------|
| `daily_slope` | `build_daily_slope_covariate`（`features.py:87`） | 真实日线滚动斜率，按 `daily_dates` 阶梯映射（`:124-137`） | Stage-1 **预测**价格的回归斜率常数（`:140-157`） | 合法：用的是日线预测，不是未来真收盘 |
| `calendar_cyclical` | `calc_calendar_cyclical`（`:2097`） | 历史 `dt` 的 DOY/Month sin/cos | `generate` 交易时段未来时间戳再编码（`:2124-2163`） | **合法**：日历可知。不读 OI/CCL |
| `oi` / `oi_pct_change` | `calc_oi_pct_change`（`:594`）+ 拼接 | `df_1h["open_interest"]` 的差分比 | **`np.zeros(horizon)`**（`:1055,1481`） | **未**填 cutoff 后真实 OI |
| `ccl` / `ccl_pct` | `calc_ccl_pct`（`:610`）+ 拼接 | context 仓单/OI | **`np.zeros(horizon)`**（`:1392`） | **未**填 cutoff 后真实 CCL |
| `vor` | `calc_vor` + `_decay_fill`（`:1247-1261`） | context 的 vol/OI | 末端值指数衰减，不是未来 OI | 合法（末端已知） |
| `rsi_state`（单路径） | `build_covariate_matrix:1076-1119` | 日线 RSI 状态 ffill 到 1H | `_generate_rsi_state_horizon` 从 context 末端衰减（`:1117-1118`） | 合法；**不用** `pred_states` 作 horizon |
| `rsi_state`（combo） | `build_combo:1483-1487` | **1H 收盘** RSI | 同样末端衰减 | 合法填充；但与单路径**不是同一个量**（见 I2） |
| 动量类 `ao_accel`/`nvi`/… | 各 `calc_*` + `_decay_fill`（`:983`） | 仅 `df_1h` context | 末端衰减或常数 | 合法 |
| `crack_spread_*` | `calc_crack_spread`（`:749`） | `_align_feedstock` 只 join `df_main` 时间轴（`:715-746`）；原料经 `_fetch_feedstock_1h`（`hourly_model.py:43-59`）按 cutoff 开 `BacktestDataStore` | level=常数 / slope&zscore=衰减 | 原料读取有 cutoff 感知；horizon 不读未来腿 |

`fill_strategy`（`"default"` / `"decay"`）**管不到** OI/CCL：这两类永远零填充。`cascade_predict` 不传该参数，默认 `"default"`。`monthly_backtest` 可传，但只影响 `vwap_deviation` 等少数分支（`features.py:1366-1373,1622-1629`）。

### 3.2 日历 OK

`calc_calendar_cyclical` 的 horizon 时间戳是合成的（weekday&lt;5 且小时在 `valid_hours`），测试 `tests/test_calendar_cyclical.py:51-70` 锁「horizon 编码等于未来每小时的真实 dayofyear/month」，用的是外推日期，不是库里 cutoff 后的 K 线。

`build_covariate_matrix:1029-1034` 给 `daily_slope` 用的未来轴是 `data_validator.generate_trading_dates`（`:584`）。日历函数**自己又写了一套**未来轴（`:2131-2150`），并且 `replace(minute=0)`。两套都是日历外推，不是偷未来行情；但对不齐会让「第 k 根 horizon」的日历编码和斜率映射对的不是同一个时钟（见 M2）。

### 3.3 OI/CCL 没有 fill cutoff 之后的真值

单路径 / combo 对 OI 都是 `np.concatenate([oi_pct.values, np.zeros(horizon)])`。CCL 同构。features **假定** `store.get_main_contract_1h` 已经截在 cutoff（回测是 `BacktestDataStore`）。若 store 把 cutoff 后的 bar 当作 context 吐出来，那是数据层穿越，归 Task 5，本任务不宣称「代码仍穿越」。

`calc_ccl_pct:639-640` 对 OI 基数 `rolling(5).mean()` 再 **`bfill()`**：只在 context 内部把早段 NaN 用更晚的 context OI 填上。对 T0 一次预测，整段 context 在 T0 都已知，不是 horizon 偷未来。不要把它写成「fill 了 cutoff 之后」。

---

## 4. Step 3：模型加载与 compile-skip

### 4.1 TimesFM 路径 **没有** 走 `get_timesfm_model_path`

文档合同（`AGENTS.md:28-38`，git `d236671` 2026-09-06 写入）：

> 解析入口：`data.config.get_timesfm_model_path()`；cascade `DailyModel`/`HourlyModel` 经此加载。环境变量优先 `FM_TIMESFM_MODEL_PATH`（兼容 `TIMESFM_MODEL_PATH` / `TIMESFM_WEIGHTS_DIR`）。HF hub id 仅作缺本地权重时的最后回退。填充方式：从 HF cache **复制**（非 runtime 直连共享 cache）。

代码事实：

- `data/config.py` **没有** `get_timesfm_model_path`（文件止于 `:118`，只有 `resolve_under_root` / `get_db_path` 等）。`git log -S get_timesfm_model_path -- '*.py'` 为空——函数从未进过 Python。
- `DailyModel.__init__`（`daily_model.py:80-81`）与 `HourlyModel.__init__`（`hourly_model.py:84-85`）无条件：
  `timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")`
- `cascade_predict` / `copilot`（`:776-781`）都是 `DailyModel()` 这条路径。
- 磁盘：`/home/abug/timesfm/models/timesfm-2.5-200m-pytorch/` **存在**，但三个文件全是指向
  `~/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots/1d952420…/`
  的符号链接，不是合同要求的副本。
- `monthly_backtest.py:69-77` 的 `TIMESFM_WEIGHTS_DIR` 只用于日线缓存**指纹**，不改变 `from_pretrained` 加载路径。

### 4.2 compile-skip 只在声称路径生效

规格：`docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md:50-64` 画的是 `_ensure_compiled`；实现名是 `ensure_compiled`（`daily_model.py:53-59`），指纹字段 `FP_FIELDS`（`:33-42`）与 spec §3.1 一致。

调用点（生产）：

- `DailyModel.__init__:84`、`DailyModel.predict:101`
- `HourlyModel.__init__:82,87`、`HourlyModel.predict:118`

行为：指纹相同则跳过 `model.compile`；配置从日线切到 XReg（或反过来）必编；`compile` 抛错不写指纹（`:74-87` 测试锁）。

`monthly_backtest` 日线缓存命中时不进 `DailyModel.predict`，与 spec §3「热缓存连续 1H 跳过 compile」同构。

**不走** `ensure_compiled` 的旁路（非本任务生产主链，记一笔）：`scripts/predict.py:252-253`、`scripts/ablation_context.py:25-28,184-185`、A2 worker 直接 `from_pretrained` + 自管 compile。

测试：`tests/test_compile_skip.py` 假模型次数、配置切换、失败不写指纹、`DailyModel.predict` 第二次 skip、共享模型日线→1H 必重编。慢测真模型逐位对比本次按 `-m 'not slow'` 跳过。

---

## 5. Findings

### I1 — Important — `get_timesfm_model_path` 未实现；级联加载硬编码 hub id

- **文档合同**: `AGENTS.md:35-38`：解析入口 `data.config.get_timesfm_model_path()`；本地目录 `/home/abug/timesfm/models/timesfm-2.5-200m-pytorch`；复制隔离，hub id 仅回退。
- **代码/磁盘**: 函数不存在。`daily_model.py:80-81`、`hourly_model.py:84-85` 固定 hub id。本地目录是 HF cache 的 symlink（`ls -la models/timesfm-2.5-200m-pytorch`）。
- **建议**: 在 `data/config.py` 实现解析（env → 本地目录 → hub 回退），Daily/Hourly 经此 `from_pretrained`。隔离要复制，不要 symlink。不要在未开 plan 时改加载逻辑以外的预测公式。
- **若维持现状**: 预测岗与 Praxist 慢环 runtime 可能打同一份 HF cache；快照升级时无本地钉扎。当前 symlink 指向同一 `1d952420` snapshot，**不证明信号已经算错**，这是加载合同未落地，不是方向公式 bug。

### I2 — Important — 同名 `rsi_state`：单路径=日线 RSI，combo=1H RSI

- **代码**:
  - 单路径 `features.py:1076-1119`：`calc_rsi_state(hist_daily + pred_daily)`，再按日映射到 1H。
  - combo `features.py:1483-1487`：`calc_rsi_state(hourly_closes)`。
  - 切换：`hourly_model.py:196-197`，`len(covariate_types) > 1` 才进 combo。
- **生产谁走哪条**:
  - 日线 RSI：`rb`/`lh`/`jd`（`covariate_types=["rsi_state"]`，长度 1）
  - 1H RSI：`sr`（`["rsi_state","oi","calendar_cyclical"]`）、`p`（`["rsi_state","reversal_shadow"]`）
- **建议**: 拆成两个名字，或 combo 复用单路径的日线构造。固化前应用该品种真实路径回测，不要假设「rsi_state 到处一样」。
- **不是穿越**: 两条的 horizon 都从 context 末端衰减，没有填未来 RSI。

### I3 — Important — `copilot` 主方向仍是日线 `_compute_direction_v2`（Task 9）

- **合同**: CF-01 A / `signal_contract.py:12-13` 声称 copilot MUST 调 `position_from_forecast`。
- **代码**: `scripts/copilot.py:384,433-446` — `direction = _compute_direction_v2`；`delta_pct` 用终点。不 import `position_from_forecast`。
- **建议**: 本任务不改 copilot。修文档字符串，避免执行者按 `signal_contract` 模块头去「统一」级联（级联已经对了）。卡面主句归 Task 9。

### I4 — Important — ALIGN 时价格序列与协变量可能不是同一合约

- **代码**: `hourly_model.py:137-147`：非 `_MAIN` 且 1H 合约 ≠ 日线合约时，价格用 `get_klines_1h(contract_code=vr.contract_daily)`；随后 `build_covariate_matrix:1022` **总是** `store.get_main_contract_1h`。
- **建议**: features 吃 HourlyModel 已经读好的 `df_1h`，或 ALIGN 时同样按合约取协变量。生产连续合约路径（`_MAIN`）不进该分支。
- **置信度**: 路径存在；活路径是否常触发取决于 `data_validator` 的合约字段，需 Task 5/运行日志确认。

---

### M1 — Minor — SPEC-007 cosine 在库里，不在生产 `SCHEMES`

- **文档**: `system_design.md:357-361` 只写硬切 12 根；hardening SPEC-007 要平滑滚降。
- **代码**: `prediction_scheme.py:543-553` 实现 plateau=8 / cutoff=16 cosine；`smooth_cutoff` 默认 False，`SCHEMES` 未打开。短段品种走硬切（`:555-559`）。
- **建议**: 文档写清「代码有 cosine，生产全关」。不要把测试里的 `smooth_cutoff=True` 当成活信号。

### M2 — Minor — 日历未来轴与 `generate_trading_dates` 不是同一函数

- **代码**: 斜率用 `generate_trading_dates`（`data_validator.py:584-626`，保留分钟，周末跳到周一 00:00）；日历用自写循环（`features.py:2131-2150`，分钟清零，`max_iter=horizon*48`）。
- **建议**: 日历直接调用 `generate_trading_dates`，避免第 k 根 horizon 对钟不一致。不是偷未来。

### M3 — Minor — compile-skip 规格名 `_ensure_compiled`，实现是 `ensure_compiled`

- **规格**: `2026-09-09-compile-skip-phase1-design.md:55`
- **代码**: `daily_model.py:53`。行为与指纹字段对齐。改文档即可。

### M4 — Minor — `config/AGENTS.md` 仍写实盘方向 ≠ 回测方向

- **文档**: `config/AGENTS.md:43-44`
- **代码**: 两边都是 `position_from_forecast`（见 §2）。过期 Known Issues，不要当活 bug 去改 `monthly_backtest`。

### M5 — Minor — stdout 日线摘要仍打印 `_compute_direction_v2`

- **代码**: `daily_model.py:180`；`cascade_predict.py:103` 会打印。结构化结果里的 `direction` 已是加权 1H（`:219`）。
- **建议**: 摘要改称「日线状态」，避免和可交易方向抢「方向」二字。

### M6 — Minor — combo 不支持 `ccl`

- **代码**: `features.py:1637-1648` 的 supported 列表无 `ccl`。当前 combo `SCHEMES` 不用 ccl，不会炸。以后若把 ccl 塞进 `covariate_types` 会显式报错（比静默降级好）。

### M7 — Minor — `walk_forward.py` 不是生产级联 WF

- **代码**: IR / IS-OOS，明确禁止固化 SCHEMES（`:3-5`）。方向合同不经过它。

---

## 6. 非本任务（指针，不升级成本任务 Critical）

| 项 | 去向 |
|----|------|
| Stage 1 读 `get_main_continuous` 而非 `get_safe_daily`（`daily_model.py:104` vs `cascade_predict.py:106-107` 仅报告） | Task 5 / Task 2 I7。本文不宣称仍穿越 |
| `BacktestDataStore` cutoff 是否 bar-exact | Task 5。`monthly_backtest.py:267-270` 已写 bar 时间戳；`data/AGENTS.md:34-44` 仍写日历日+23:59（文档过期嫌疑） |
| copilot 卡面文案、Vol 雷达永不压平 | Task 9 |
| IC / `gate_pass` / 硬门 | Task 7 |
| `system_design.md` 日线主方向伪代码 | Task 2 C1，改文档不改 `position_from_forecast` |

---

## 7. 符号核对（相对 Task 2 表，本任务代码复核）

| 符号 | 结论 |
|------|------|
| `_compute_direction` | 不存在 |
| `_compute_direction_v2` | `daily_model.py:189`，日线副标签 + copilot 主句 |
| `position_from_forecast` | `signal_contract.py:32`，cascade_predict / monthly 生产方向 |
| `signal_weight` | `prediction_scheme.py:524`，在生产路径上（经 position_from_forecast） |
| cosine / `smooth_cutoff` | 实现了，生产 SCHEMES 关闭 |
| `ensure_compiled` | 在 Daily/Hourly init+predict 上；规格名多一个下划线 |
| `get_timesfm_model_path` | **不存在** |
| `horizon_slope` | 分数/天（`daily_model.py:151`）；摘要 `×100`（`:179`） |
| `calc_calendar_cyclical` | 4 维，horizon 外推日历 |
| `walk_forward.py` | 非生产方向路径 |

---

## 8. 测试证据

```text
cd /home/abug/timesfm
.praxist-venv/bin/python -m pytest tests/test_signal_contract.py \
  tests/test_calendar_cyclical.py tests/test_compile_skip.py -q -m 'not slow'
# ..................  18 passed, 1 deselected in 21.51s
```

未跑：`test_skip_vs_force_compile_bitexact_real_model`（`@pytest.mark.slow`，真模型）。无 LSP 工具；以 pytest 代替类型诊断。

---

## 9. Root cause

方向合同在 8 月已经钉成 CF-01 A，`signal_contract.py` + 回测/级联入口已对齐。`system_design.md` 和 `config/AGENTS.md` 仍停在「日线定方向 / 实盘≠回测」。权重隔离写进 `AGENTS.md` 但从未写成 `data.config` 函数，Daily/Hourly 继续 hub id，本地「模型目录」只是 HF cache 的链接。协变量 horizon 填充整体是保守的（OI/CCL 置零、日历外推）；真正的同名异义在 `rsi_state` 单/combo 分叉，以及 copilot 仍用日线副标签当主句。

---

## 10. Recommendations（只建议，不落地）

1. **不要改** `position_from_forecast` / 不要按 `system_design.md` §5.1 去「统一」级联方向。
2. 实现或删掉 `get_timesfm_model_path` 合同：要么代码跟上 `AGENTS.md`，要么文档改成「现行=hub id + HF cache」。
3. 给 `rsi_state` 分名或统一构造，避免 SR 与 RB 其实不是同一个协变量。
4. copilot 方向分叉交给 Task 9；同时改 `signal_contract.py` 模块头，不要把 copilot 写成已合规。
5. cosine 保持默认关，文档写明。

---

## 11. 计数

| 严重度 | 条数 |
|--------|------|
| Critical | 0 |
| Important | 4（I1 加载路径、I2 rsi_state 分叉、I3 copilot 主方向、I4 ALIGN 合约） |
| Minor | 7 |

**状态**: `DONE_WITH_CONCERNS`（方向合同在级联/回测上成立；加载隔离合同未落地；copilot 分叉点名给 Task 9）
