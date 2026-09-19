# Tasks 5–9 Review — 代码审核报告（只读）

- **被审**: `task-5-data-lookahead.md` / `task-6-cascade.md` / `task-7-eval-gates.md` / `task-8-three-loop.md` / `task-9-copilot-vol.md`
- **计划**: `docs/superpowers/plans/2026-09-11-full-system-audit.md` Tasks 5–9
- **简报**: `.superpowers/sdd/2026-09-11-full-system-audit/task-{5,6,7,8,9}-brief.md`
- **审核日**: 2026-09-11
- **范围**: 只审五份报告是否按规格取证、严重度是否按全局口径；不改生产代码

## Verdicts

| Task | Spec | Quality | Must-fix |
|------|------|---------|----------|
| 5 data-lookahead | ✅ | Approved | 无 |
| 6 cascade | ✅ | Approved | 无 |
| 7 eval-gates | ✅ | Approved | 无 |
| 8 three-loop | ✅ | Approved | 无 |
| 9 copilot-vol | ✅ | Approved | 无 |

严重度口径（计划 Global Constraints）：Critical = 活路径错信号、仍影响 PF 或实盘建议的穿越、硬门被绕过、非慢环写 verdict。文档过期默认最高 Important。Copilot 违反 CF-01 A 但预测未被 overlay 拍平 → 允许记 Important，不因此拒审。

---

## Task 5 — 数据管线与前视

**被审**: `docs/superpowers/reports/2026-09-11-audit/task-5-data-lookahead.md`

### Spec 核对（计划 Step 1–4 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| 三条生产路径：cutoff、是否含当日日线、1H 是否截到 cutoff | 文首表 + §三条路径 | copilot / cascade_predict 无 cutoff、模型裸 `get_main_continuous`；cascade 报告层 `get_safe_daily`；monthly 走 `BacktestDataStore` bar 时刻 + `hour>=15` |
| 继承 Task 4，不再争论 STEP=2 / `get_safe_daily` 名实 | 文首继承段 | 与 `task-4-review.md` 同向：`2fcb3ee` 只换报告 `daily_df`；`DailyModel.predict` 仍裸读 |
| `run_guard` 是否唯一批量入口；`ensure_fresh_data` 失败是否静默脏数据 | §幽灵 K | 实现唯一（`daily_update` + `data_management --validate`）；cascade 全失败则停；copilot `valid or symbols` 回退（I2） |
| SPEC-011 落在哪条路径 | §换月/复权 | 挂在日线 `get_main_continuous`，被 `raw_close` 列名短路；1H 无复权；实现是价差比不是截面比 |
| Critical = 仍影响 PF 或实盘建议的穿越 | C1 + 不升 Critical 清单 | **未**把 `monthly_backtest` 的 `hour>=15` 标成 PF 穿越。C1 留给实盘裸读未完成下一交易日日线 |
| 每条 finding 有路径+行号、合同、代码/磁盘、只建议 | C1 / I1–I6 / M1–M2 | 独立复验见下 |
| 只写报告，不改生产 | git status | 本任务产出仅报告。仓内 `cascade/features.py` 有未提交改动，mtime 11:10，**不是**本报告写入 |

### Quality 核对

| 检查 | 结果 |
|------|------|
| 是否把已修的回测前视写成 live Critical | **否。** 夜盘含当日 ≠ 含夜盘价，用 ss 14:00 对齐证伪 |
| C1 是否过抬 | **否。** 活路径日线进 TimesFM → `daily_slope` / `horizon_slope` → 1H 与领航员/级联建议。计划口径就是实盘建议穿越 = Critical |
| 磁盘证据是否可复现 | **是。** 只读打开 `db/futures_ss.db`：日线尾 `2026-09-08` close=13860 `updated_at=2026-09-07 13:30:59`；1H 尾 `2026-09-07 21:00` close=13860；`2026-09-08` 的 1H 计数 0；`2026-09-07` 日线 13885 = 当日 14:00 |
| 未跑 TimesFM 是否毁掉 C1 | **否。** 报告自己写了 Critical Unknown / Discriminating Probe。因果链在代码里连着，缺的是斜率数值差，不是路径是否存在 |
| 越权改生产 | 否 |

### 独立复验

```
DailyModel.predict              cascade/daily_model.py:104  store.get_main_continuous
copilot run_one                 scripts/copilot.py:396-400
cascade_predict 模型            scripts/cascade_predict.py:101-102
cascade_predict 报告            scripts/cascade_predict.py:106-107 get_safe_daily
get_safe_daily                  data/data_store.py:158-198（date>today 由 closed_mask 剔除）
BacktestDataStore 日线          data/data_store.py:789-803 hour>=15 → cutoff_day
BacktestDataStore 1H            data/data_store.py:805-826 dt <= cutoff_ts
copilot 全失败回退              scripts/copilot.py:769  symbols = valid or symbols
cascade 全失败退出              scripts/cascade_predict.py:840-844 只用 valid_symbols
SPEC-011 短路                   data/data_store.py:418  if "raw_close" not in df.columns
ALIGN 旁路                      cascade/hourly_model.py:132-136 get_klines_1h 无 end_date
ss 库尾                         09-08 日线 13860 = 09-07 21:00 1H；无 09-08 1H
```

`get_safe_daily` 生产调用点仍只有 `cascade_predict.py:107` 与 `tests/test_daily_freshness.py`。

### 非阻塞偏差（不必返工）

- 计划 Read 列表里的 `data/indicator_calculator.py`、`data/config.py`、`tests/test_ensure_data_result.py`、`tests/test_holidays.py` 未点名。`indicator_calculator` 只在 copilot `refresh_intraday_1h` 写 1H 指标，不是日线穿越向量。三条路径合同已画全，不构成 spec 缺口。
- `get_safe_daily` 规则行号写成 `:166-188`（文档字符串 + 掩码）；实现掩码在 `:187`。语义对。
- 只深探 ss。I4 是否会在无 `_MAIN` 品种上动 PF，报告标 Important 并交给运行日志，符合「测试未覆盖的路径分叉 = Important」。

**状态**: Spec ✅ / Approved / 无 must-fix。

---

## Task 6 — 级联预测核心

**被审**: `docs/superpowers/reports/2026-09-11-audit/task-6-cascade.md`

### Spec 核对（计划 Step 1–4 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| 谁在生产路径上：`position_from_forecast` / `_compute_direction` / `_compute_direction_v2` / `signal_weight` / cosine | §2 符号表 | `_compute_direction` 不存在。cascade_predict / monthly 走 `position_from_forecast`。copilot 走 `_compute_direction_v2`（点名给 Task 9）。cosine 实现了、`SCHEMES` 全关 |
| 不得推翻 Task 2 裁定 | 文首四条 | 与 Task 2 同向：CF-01 A 是加权 1H；`horizon_slope` 分数/天 |
| 协变量 context vs horizon：日历合法 / OI·CCL 是否填 cutoff 后真值 | §3 点名表 | OI/CCL 单路径与 combo 均为 `np.zeros(horizon)`（`features.py:1055,1392,1481`）。日历 `calc_calendar_cyclical` 外推交易时段 |
| TimesFM 是否走 `data.config.get_timesfm_model_path()`；compile-skip 声称路径 | §4 | 函数不存在（`data/config.py` 无此名）。Daily/Hourly 硬编码 hub id。`ensure_compiled` 在 init+predict |
| 产出日线→1H→方向真实合同（函数名+单位） | §1 表 | 可交易方向 = `sign(weighted_1H − T0)` |
| pytest 声称子集 | §8 | 报告：18 passed, 1 deselected。本审核未重跑慢测 |

### Quality 核对

| 检查 | 结果 |
|------|------|
| 是否按 `system_design.md` §5.1 把级联方向判错 | **否。** 明确 cascade/monthly 已对齐 CF-01 A，不要改 `position_from_forecast` |
| 是否把加载隔离合同写成错信号 | **否。** I1 Important：hub id + HF cache symlink，不证明预测算错 |
| copilot 分叉是否越权改结论 | **否。** I3 点名，细节归 Task 9 |
| OI/CCL 穿越是否误报 | **否。** 活代码仍是 horizon 置零。combo 的 `ccl` 在报告落盘时（11:07）supported 列表无 `ccl`（M6） |
| 越权改生产 | 否 |

### 独立复验

```
position_from_forecast          cascade/signal_contract.py:32
  cascade_predict               scripts/cascade_predict.py:209-220,535-536
  monthly_backtest              scripts/monthly_backtest.py:50,329
  copilot                       全文件无 import
_compute_direction_v2           cascade/daily_model.py:189
  copilot 主方向                scripts/copilot.py:384,433-434
from_pretrained hub id          daily_model.py:80-81；hourly_model.py:84-85
get_timesfm_model_path          data/config.py 无此符号
OI zeros                        features.py:1055,1481
CCL zeros                       features.py:1392
rsi_state 单路径=日线           features.py:1076-1119
rsi_state combo=1H              features.py:1483-1487
ALIGN get_klines_1h             hourly_model.py:132-136（报告写 :137-147，偏了 5 行；路径存在）
```

### 非阻塞偏差

- I4 行号写成 `hourly_model.py:137-147`。ALIGN 调用在 `:136`，`:137-141` 是 `_MAIN` 分支。事实仍成立。
- M6「combo 不支持 ccl」对 **报告落盘时刻的 HEAD** 成立。随后未提交的 `cascade/features.py`（mtime 11:10，+84 行）把 combo 补上了 `ccl` / `basis_momentum` / `gated_slope` / `regime_gated`。这是并行改动，不是报告写错。Task 11 不要把 M6 当现行代码事实。
- 本审核未复跑 `test_signal_contract` / `test_calendar_cyclical` / `test_compile_skip`。行号抽查与声称合同一致。

**状态**: Spec ✅ / Approved / 无 must-fix。

---

## Task 7 — 评估指标、硬门、回测入口

**被审**: `docs/superpowers/reports/2026-09-11-audit/task-7-eval-gates.md`

### Spec 核对（计划 Step 1–4 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| PF / EV / EV_ratio / IC / DirAcc / MaxDD（名义 vs 保证金）唯一实现 | §1 | 秤在 `evaluation_metrics.py`。IC 不在秤里，在 `evaluator.gate` 与慢环 `setdefault` |
| 核对 `system_design` §7 示例是否错 | §1.3 / I-02 | §7.1 Pearson 是错合同；PF / 名义 MaxDD 伪代码同构 |
| `gate_pass` 实际条件；`ss_vor` / `i_oi` 磁盘验证 | §2.3 | 布尔 = `n>=350 and ic>=0.05`，不含 EV。亏钱过门仍在，并多 `m_ccl` |
| STEP / EVAL_WINDOW / CONTEXT / HORIZON；理论 n；磁盘 n | §3 | STEP=2，窗口 1200，理论 589，磁盘最高 588，常见 396 |
| 主回测入口是否仍是 monthly_backtest | §4 | 慢环唯一调 `run_symbol_backtest`；唯一写 jsonl 的是 `aligned_slow_loop.py` |
| Task 1 矛盾 2/3/5 回写 | §6 | 三对全部证实 |
| 不要按 yaml/`system_design` 去给 `gate()` 加 EV | 结论先行 + 建议 5 | 与 Task 1 两扇门裁决一致 |

### Quality 核对

| 检查 | 结果 |
|------|------|
| 是否把「亏钱仍 gate_pass」写成硬门被绕过（Critical） | **否。** I-01 Important。`pass_variants()` 仍要 `ev>0`。这是命名两扇门，不是 evaluator 被跳过 |
| 磁盘数字是否可复算 | **是。** 26 行、unique 26；`gate_pass=true` 仅 ss_vor / i_oi / m_ccl；经济过门仅 ss_vor；26/26 `ic == 2*|dir_acc-0.5|` |
| 396 vs 588 vs 589 vs 600 是否搅成门限冲突 | **否。** 硬门阈值仍是 350。396 = 旧网格或 `max_points` 截断 |
| 保证金 MaxDD 吃毛 PnL | I-03 正确：`aligned_slow_loop.py:109-114` 传入 `p["pnl"]`；`monthly_backtest.py:353` 是 `position_sign * delta_real` |
| 越权改生产 | 否 |

### 独立复验（磁盘）

```
aligned_verdicts.jsonl          26 行 / 26 unique
gate_pass=true                  ss_vor ev=+11.06；i_oi ev=−2.46；m_ccl ev=−3.64
pass_variants 经济过门          仅 ss_vor
n 分布                          396×21 / 588×3 / 324×1 / 142×1
ic 公式                         26/26 匹配 2*|dir_acc-0.5|
evaluator.gate                  task_FM/evaluations/fm_eval/evaluator.py:199-203
慢环补 ic                       scripts/aligned_slow_loop.py:101
STEP / 窗口                     config/backtest_config.py:55-56 = 2 / 1200
理论 n                          len(range(0, 1200-24+1, 2)) = 589
append_verdict 生产点           仅 aligned_slow_loop.py:122（测试夹具除外）
```

`m_ccl`：n=396, dir_acc=0.544, ic=0.088, ev=−3.64, pf=0.839, maxdd=−0.8288, gate_pass=true, margin_maxdd=−0.3067, max_points=396, decided_at=2026-09-11T10:27。与报告表一致。

### 非阻塞偏差

- 「600 点 × STEP=2」注释在 `backtest_config.py:56`，报告写成 `:57`（`:57` 是 `MIN_EVAL_POINTS`）。数值对。
- 本审核未重跑声称的 65 passed。磁盘与源码抽查足够锁住公式。

**状态**: Spec ✅ / Approved / 无 must-fix。

---

## Task 8 — Praxist 三环代码

**被审**: `docs/superpowers/reports/2026-09-11-audit/task-8-three-loop.md`

### Spec 核对（计划 Step 1–3 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| praxist.md 硬规则逐条到代码/测试；缺测试 = Important | §1 R1–R10 + §6 表 | peer 禁评估只在提示词；schema 不校验；mechanism≥40 有测；survivors=3 无测锁；phase 互斥有测；慢环唯一写活路径过；429 同提供商 resume 有测；harvest=proposals 有测 |
| `i_oi` gate_pass vs EV；materializer 是否仍误导 | §2 | 未修。磁盘又多 `m_ccl`。`known_verdicts.inc.md` 仍写 already solved，且没有 `m_ccl` |
| 不要诊断监督环是否在跑 | §0 快照 | 只读 `supervisor_state.json`，不推断进程 |
| 产出：peer 不评估 / 慢环唯一写 / 429 resume 同一 run | 结论先行 | peer：**软对齐、能力面仍在**。写者：生产 tick 只有慢环。429：同提供商 resume 同一 `run_dir` |
| Task 3 I4：paused_429 期间是否 harvest | §3 / R10 | **坐实代码会 harvest。** runbook L82/L123 落后。未改文档 |

### Quality 核对

| 检查 | 结果 |
|------|------|
| 是否把提示词缺口写成「正在伪造 aligned verdict」（Critical） | **否。** Critical=0。活 harvest 不读 `evaluation_summary.json`。I1 保留开放问题：Praxist 是否自动调度 fm_eval（计划禁止读 `.praxist-venv`） |
| 非慢环写 verdict | 生产 `append_verdict` 仅 `aligned_slow_loop.py:122`。`restore-verdicts` 是人工 CLI（M6），不在 300s tick |
| `harvest_survivors` 是否还在活路径 | **否。** 定义在 `praxist_supervisor.py:419`，调用只在 `tests/test_supervisor.py`。`_harvest_rows:1289` 调 `harvest_proposals` |
| schema 不校验 | `harvest_proposals:611-623` 无 `p["schema"]` 分支 |
| 越权改生产 / 启动 Praxist | 否 |

### 独立复验

```
harvest_proposals               scripts/praxist_supervisor.py:565；校验段 :611-623 无 schema
_harvest_rows                   :1289 harvest_proposals；缺省 survivors_per_cycle=2（:1291）
goal 生产值                     scripts/praxist_goal.yaml:21 = 3
_maybe_harvest 文档字符串       :1299-1300 paused_429 不挡 harvest
main tick                       :1527-1529 明确 even during paused_429
materialize 文案                :483-486 already solved / DEAD（报告写 :473-477，偏了约 10 行）
task.yaml 评估入口              task_FM/task.yaml:83-85,136-137
peer role evaluation_tools      task_FM/roles/peer_generalist/role.yaml:18
known_verdicts.inc.md           头两句 already solved；有 i_oi ev=−2.46；无 m_ccl
test_praxist_task_contract      write_paths 锁 scripts/praxist_ws（:48-51）；diagnostic 档（:57）
```

快照：`supervisor_state.json` 本审核未重读 mtime；报告给出的 phase=fast / cycles_done=1 / paused_429=false 与 Task 1 复验同向，不作为「正在跑」的结论。

### 非阻塞偏差

- I7 行号写反：`write_paths` 在 `test_praxist_task_contract.py:48-51`，不是 `:37-41`（那是 `min_samples`/`min_ic`）；`diagnostic` 档在 `:57`，不是 `:47-50`。**断言内容对。**
- materializer 行号 `:473-477` 实际是 harvest 选座尾巴；函数从 `:483` 起。文案原文正确。
- I1 升 Critical 的条件（插件自动调度评估）未在 venv 外证实。按计划保持开放问题，不阻塞。

**状态**: Spec ✅ / Approved / 无 must-fix。

---

## Task 9 — Copilot、纸面、Vol

**被审**: `docs/superpowers/reports/2026-09-11-audit/task-9-copilot-vol.md`

### Spec 核对（计划 Step 1–3 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| copilot 打不开 Neutral override；cascade_predict 默认 OFF；开关只影响声明入口 | §1.1–1.2 | copilot argparse 无 `--vol-filter*`，全文件无 `apply_neutral_override` / `FM_VOL_FILTER`。cascade `use_vol_filter: bool = False`（`:67`）；CLI `:753-765` 或 env `"1"` |
| `craft_advisory` 是否用日线当主句，和加权 1H 对不上 | §2 | `direction = _compute_direction_v2`（`:433-434`）；`delta_pct` 用 T+24 终点。UI/研报/止损/ledger 全跟日线 |
| 盘中路径是否仍守红线 | 红线记分卡 | Vol 默认 OFF **守住**；永不静默压平 **守住**；可交易方向 **Copilot 违反**；无真实 3 星 **守住** |
| 必答：Copilot 是否违反 CF-01 A | 文末裁决 | **是。** 预测未被 overlay 改写 |
| 必读测试/文档 | 文首对照 + pytest 声称 | 点名了 copilot.md / paper_trading.md / vol-risk.md / module_freeze.md；`test_signal_mode_mutex` 与 Vol 无关写清楚了 |

### Quality 核对

| 检查 | 结果 |
|------|------|
| CF-01 A 记 Important 而非 Critical 是否拒审 | **否。** 预测点位未被拍平、不是自动下单、文档已披露。符合本审核校准句 |
| 是否把 Vol 雷达文案「空仓观望」写成静默压平 | **否。** 明确是明牌建议，不改 `point_forecast` |
| `--three-star` = stars≥2 | copilot `:728-729,743-745` help 与实现一致。cascade help 仍写「三星固化 (SS/UR/SR)」（`:743-744`），实现 `:782-785` 已映射 `list_by_stars(2)`（M4） |
| 纸面 T+24 对账 | I2 与 `docs/paper_trading.md` 已知债对齐，未写成「文档撒谎」 |
| 越权改生产 | 否 |

### 独立复验

```
copilot 无 apply_neutral        scripts/copilot.py 全文件 0 命中
copilot CLI                     :722-737 无 vol-filter；有 --no-vol-radar
copilot 主方向                  :433-434 _compute_direction_v2；:435-437 T+24 delta_pct
copilot 不调 position_from_forecast  全文件 0 命中（cascade/monthly 有）
Vol 默认                        cascade_predict.py:67 False；vol_risk_filter.py:354 FM_VOL_FILTER 默认 "0"
打开时压平                      cascade_predict.py:174-195 apply_neutral_override_v2 + baseline_forecast
三星映射                        copilot :745 list_by_stars(2)；cascade :785 同
CF-01 A 原文                    docs/product_positioning.md:15-22
signal_contract 模块头          cascade/signal_contract.py:12-13 仍写 copilot MUST 调用（合同文件自己的谎）
```

### 非阻塞偏差

- 「相关 7 个文件 → 53 passed」：简报测试清单是 6 个文件。未列出第 7 个名字。不改变红线结论。本审核未重跑该子集。
- argparse 行号写成 `:722-737`；`--three-star` 从 `:727` 起，`:737` 是 `--out-dir`。旗标集合正确。

**状态**: Spec ✅ / Approved / 无 must-fix。

---

## 交叉（给 Task 10 / 11，不发明新结论）

| 主题 | Task 5 | Task 6 | Task 7 | Task 8 | Task 9 |
|------|--------|--------|--------|--------|--------|
| 实盘日线裸读 | **C1 Critical** | 指针给 Task 5 | — | — | 下游吃这根 bar 的日线方向 |
| copilot 主方向=日线 | 点名 | I3 点名给 Task 9 | — | — | **I1 Important**（预测未拍平） |
| ALIGN `get_klines_1h` 无 cutoff | I4 Important | I4 Important | — | — | — |
| `gate_pass` 不含 EV；i_oi / m_ccl | — | — | I-01 | I3 materializer 误导 | — |
| 慢环唯一写 jsonl | — | — | §4 | R7 活路径过 | — |
| Vol 默认 OFF / copilot 不压平 | — | — | — | — | 守住 |
| 加载隔离 `get_timesfm_model_path` | — | I1 Important | — | — | — |

冲突：无。五份对同一事实同向。唯一时间线提醒：Task 6 M6（combo 无 ccl）已被事后未提交的 `features.py` 补上，SUMMARY 以 git HEAD 为准。

---

## 总评

五份都覆盖了计划 Step，finding 带行号/磁盘，严重度没有把文档债抬成活 Critical，也没有把 Copilot 方向分叉因为「没拍平」就放走（Task 9 记了 Important 并写了必答裁决）。Task 5 C1 是这五份里唯一的 Critical，且磁盘可复现。全部 Approved，无 must-fix。
