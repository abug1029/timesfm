# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

# FM — 期货数据管理与 TimesFM 预测系统

## 核心架构

**两阶段级联预测系统：**
1. **Stage 1 (日线模型)**: `cascade/daily_model.py` — TimesFM 2.5 预测 22 日走势，提取 horizon_slope
2. **Stage 2 (1H 级联)**: `cascade/hourly_model.py` — 以日线斜率 + 协变量(CCL/OI/RSI 等)进行 1H 预测

**数据流：** TqSdk → SQLite(每品种独立) → 技术指标计算 → TimesFM 预测 → 报告生成

**数据管理策略：**
- `LOOP.md` — 预测驱动采集策略 + 协变量变更日志
- `STATE.md` — 当前系统状态（回测/门禁/待办）**以磁盘事实为准**
- `loop-constraints.md` — 高风险路径保护规则
- `docs/` — 人类可读运维/接入文档（runbook、Copilot、Vol 风控状态）

**生产红线（2026-07-27）：**
- Absolute Risk Overlay / Neutral 压平：**默认 OFF**（L1 ops `ECONOMIC_PASS=False`）
- 盘中主观入口：`scripts/copilot.py`（预测永不压平；Vol 仅预警）
- 模型路径锚定 `data.config.FM_ROOT`，不依赖进程 cwd
- 幽灵 K 线：`data.future_bar_guard.run_guard` 为唯一批量入口（`daily_update` 末尾调用）


## TimesFM 权重隔离（预测岗 vs PRAXIST）

| 用途 | 仓库 / 进程 | 权重路径 |
|------|-------------|----------|
| 预测岗 | `timesFM_fu` | 其自身路径或该进程的 HF cache；**勿与 PRAXIST 共用 runtime 加载路径** |
| PRAXIST / FM_a cascade 慢路径 | `timesfm`（本仓，WSL `/home/abug/timesfm`） | **本地目录** `/home/abug/timesfm/models/timesfm-2.5-200m-pytorch` |

- 环境变量（优先）：`FM_TIMESFM_MODEL_PATH`（兼容 `TIMESFM_MODEL_PATH` / `TIMESFM_WEIGHTS_DIR`）
- 解析入口：`data.config.get_timesfm_model_path()`；cascade `DailyModel`/`HourlyModel` 经此加载
- HF hub id `google/timesfm-2.5-200m-pytorch` 仅作缺本地权重时的最后回退；PRAXIST 正式跑应保证本地目录已填充
- 权重目录 gitignore：`models/timesfm-*/`；填充方式：从 HF cache snapshot **复制**（非 runtime 直连共享 cache）或 `huggingface-cli download --local-dir`

## PRAXIST 运行环境（WSL2）

- 宿主：WSL2 Ubuntu-22.04，项目根 `/home/abug/timesfm`，8 vCPU / 7.7 GiB / 无 GPU（旧 Grok 盒 `/workspace` 路径已废弃）
- praxist venv：本仓 `.praxist-venv`（CPython 3.11，FM_a 与 PRAXIST 共用）；监督环自动解析本仓 `bin/praxist`，可用 `PRAXIST_BIN` 覆盖
- 规范启动：`set -a; source .env.praxist; set +a` 后 setsid 拉起 supervisor（见 `docs/runbook_praxist_three_loop.md`）。`task_FM/task.yaml` 内 **不要** 放明文 API key
- 所需环境变量见 `docs/praxist_llm_env.md`

## PRAXIST 三环（现行合同，2026-09-09）

Praxist 0.5.0 是与领域无关的研究控制平面；本仓任务包 `task_FM/` 提供科学合同；外层监督环零 token 调度。架构见 `docs/praxist.md`，运维见 `docs/runbook_praxist_three_loop.md`。**不要改** `.praxist-venv` 里的 Praxist 源码。

```
监督环  scripts/praxist_supervisor.py     0 token
   ├─ 快环  praxist start --task-path task_FM   peer = 假设作者，不加载 TimesFM
   └─ 慢环  scripts/aligned_slow_loop.py        唯一验证器；唯一可写 aligned_verdicts.jsonl
```

- 快环产物：`results/gen_<N>/<peer>/proposals/<symbol>_<cov>.json`（`fm.hypothesis_proposal.v1`，mechanism ≥40 字）
- 硬门：n≥350 且 IC≥0.05 且扣滑点 EV>0（`config/praxist_task.yaml`）
- 目标：`scripts/praxist_goal.yaml`（1 星集合过门 ≥4 + PF 比>1.05 + ≥1 族）
- 机器状态：`data/cache/supervisor_state.json`；裁决：`task_FM/config/aligned_verdicts.jsonl`
- `task_FM/task.yaml` 禁止明文 API key；密钥只进 `.env.praxist`
- Windows 挂载/副本可能过期；读本仓用 `wsl -d Ubuntu-22.04 -- bash -c "..."`

## 分层文档 (deepinit 2026-08-08)

| 目录 | 文档 |
|------|------|
| `cascade/` | `cascade/AGENTS.md` — 指标秤 / Neutral / 模型核心 |
| `config/` | `config/AGENTS.md` — SCHEMES / 回测超参 |
| `data/` | `data/AGENTS.md` — 采集 / BacktestDataStore 截断契约 |
| `scripts/` | `scripts/AGENTS.md` — 入口矩阵 / 回测陷阱 |
| `docs/` | `docs/AGENTS.md` — registry / validation v2 / Praxist 文档路由 |
| `tests/` | `tests/AGENTS.md` — 合约测试清单 |
| `task_FM/` | Praxist 任务包（prompts / 评估器 / 协变量池）；合同见 `docs/praxist.md` |

## 回测真相源 (Sources of Truth)

| 关切 | 唯一来源 |
|------|----------|
| 经济指标 PF/EV/MaxDD | `cascade/evaluation_metrics.py` |
| Neutral A/B 门禁 | `cascade/neutral_ab_report.py` |
| WF 超参 480/24/24 | `config/backtest_config.py` |
| 品种协变量/星级 | `config/prediction_scheme.py`（改前人工确认） |
| 固化判据 v2 | `docs/validation_criteria.md` + `scripts/phase4d_parse_results.verdict` |
| 固化 WF 权威入口 | `scripts/monthly_backtest.py`（禁止 3/7 点 scan 顶替） |
| 实验防重复 | `docs/backtest_registry.md` |
| 幽灵 K 线 | `data.future_bar_guard.run_guard` only |
| Praxist 机器状态 | `data/cache/supervisor_state.json` |
| Praxist aligned 裁决 | `task_FM/config/aligned_verdicts.jsonl`（仅慢环可写） |
| Praxist 预注册口径 | `config/praxist_task.yaml` |
| Praxist 架构/运维 | `docs/praxist.md` + `docs/runbook_praxist_three_loop.md` |

**2026-08-21 状态锚点（Phase 11/12 结案）**
- Phase 11 单协变量穷举结案：12 品种协变量替换固化，34 GREEN（详见 `docs/backtest_registry.md`）
- Phase 12 BU 组合协变量：`calendar_cyclical+hourly_slope` 固化（PF=1.01 边际 GREEN）
- M/P/SR 基线验证保持（当前方案优于 Phase 11 单协变量候选）
- 信用档不变：≥2★ = CJ/SS/SR/M/JD/LH/EG/RB（8 品种）；1★ = 12 品种
- 冲突债：`20260808_conflict_debt_register.md`（DONE）

**2026-08-08 状态锚点**  
- 回测 P0 工程已修：`20260808_tech_strategy_debt_post_fix.md`  
- 冲突债：`20260808_conflict_debt_register.md`（绝大多数 DONE）  
- 新口径 **20/20** monthly：`20260808_g005e_results.md`  
- 产品定位：`docs/product_positioning.md`（可交易方向=加权1H）  
- 可交易 alpha 健康度 **6.7/10**：`20260808_tradable_alpha_final_score.md`  

## 目录结构

```
/home/abug/timesfm/
├── data/             # 期货数据管理系统
│   ├── config.py               # 品种/交易所 + FM_ROOT/resolve_under_root
│   ├── trading_calendar.py     # 会话感知交易日标签（夜盘/周末）
│   ├── future_bar_guard.py     # 幽灵 K 线防护（run_guard）
│   ├── db.py                   # SQLite 建表
│   ├── tqsdk_fetcher.py        # TqSdk 数据获取
│   ├── indicator_calculator.py # 技术指标
│   ├── data_store.py           # SQLite 读写
│   ├── contract_manager.py     # 合约发现/主力识别
│   ├── main_chain.py           # DEPRECATED
│   └── cli.py                  # CLI 入口
├── config/           # 配置
│   ├── prediction_scheme.py    # 品种固化方案 SCHEMES
│   ├── sector_map.py           # 板块表（唯一）
│   ├── knowledge_base.json     # Copilot 信用背书（L1+SCHEMES）
│   └── backtest_config.py
├── models/           # 风控/Regime 模型 pkl + operational_thr.json
├── cascade/          # 跨周期级联预测 + VolRisk + Neutral A/B 评分
│   ├── daily_model.py / hourly_model.py
│   ├── data_validator.py       # ensure_fresh_data()
│   ├── vol_risk_filter.py      # 波动熔断 + ThrPolicy + R1 路径
│   ├── neutral_ab_report.py    # Neutral A/B 唯一评分源
│   ├── features.py / ccl_monitor.py / prediction_tracker.py
│   └── regime_*.py / walk_forward.py / ...
├── db/               # SQLite 每品种 futures_<sym>.db
├── docs/             # 运维与接入文档（人类）
├── scripts/          # 脚本
│   ├── copilot.py              # 主观领航员（推荐盘中）
│   ├── build_knowledge_base.py
│   ├── cascade_predict.py      # 级联预测（vol 压平默认 OFF）
│   ├── daily_update.py / data_management.py / collect_1h.py
│   ├── train_vol_risk_sector.py
│   ├── backtest_vol_gating_fullchain.py
│   ├── variety_analysis.py     # 技术面+CCL+Copilot 融合分析
│   └── ...
├── reports/          # 预测报告 (按品种分类)
│   ├── TEMPLATE.md             # 级联预测报告模版 (ASCII 表格样式)
│   ├── TEMPLATE_analysis.md    # 指标分析预警报告模版
│   ├── <symbol>/               # 每个品种一个目录: ss, rb, i, jm, cf...
│   │   ├── cascade_YYYYMMDD_HHmm.md  # 级联预测报告
│   │   └── analysis_YYYYMMDD_HHmm.md # 指标分析预警报告
│   ├── summaries/            # 汇总报告
│   │   ├── YYYYMMDD_HHmm_summary.md
│   │   └── YYYYMMDD_HHmm_three_star.md
│   ├── history/                # 历史预测存档 (按品种分类)
│   │   ├── <symbol>/           # 各品种历史报告
│   │   └── <symbol>/predictions.json  # 预测追踪数据
│   ├── monthly_backtest/       # 月度回测报告 + history.json
│   ├── regime_analysis/        # Regime-Covariate 分析结果
│   │   ├── run_001/            # 首次分析运行结果
│   │   ├── run_002/            # 修复后分析结果
│   │   └── ralph_execution_report_20260723.md
│   ├── research/               # 调研报告
│   ├── archive/                # 历史归档
│   │   ├── predictions/        # 旧预测报告 (2026-06)
│   │   ├── backtest/           # 旧回测报告
│   │   ├── audit/              # 数据审计报告
│   │   ├── covariate_scan/     # 协变量扫描结果
│   │   └── logs/               # 日志文件
│   ├── daily/                  # Copilot 研报
│   ├── phase1/                 # Neutral/R1 全链路回测产物
│   ├── data_ops/               # 采集/审计运维日志
│   └── ...
├── STATE.md / LOOP.md / AGENTS.md / CLAUDE.md
└── tests/            # test_future_bar_guard / test_vol_threshold_contract 等
```

## 环境配置

> 宿主评估见 `docs/host_environment_assessment.md` 顶部 2026-09-09 WSL 迁移表（8 vCPU / 7.7GiB / 无 GPU）。旧 Grok 盒 `/workspace/...` 与 Windows `D:/FlyBuddy/...` 路径均已废弃。

**必需：**
```bash
cd /home/abug/timesfm
source .praxist-venv/bin/activate
# TqSdk 凭证在 .env（真实文件，勿把密钥写入可提交文件）
```

**数据库位置：** 本仓 `db/futures_<symbol>.db`（真实目录，29 个品种 SQLite；不再是 /workspace symlink）

## 快速使用

```bash
# 激活环境
cd /home/abug/timesfm && source .praxist-venv/bin/activate

# 采集数据
python -m data.cli collect cf          # 棉花
python -m data.cli collect cf fu p     # 多品种
python -m data.cli collect --all       # 全品种

# 查看状态
python -m data.cli status              # 全部概览
python -m data.cli status cf           # 品种详情

# 查询数据
python -m data.cli query cf --days 30  # 含技术指标
python -m data.cli timesfm cf          # TimesFM 输入

# 一键预测 + 报告
python scripts/predict.py cf           # 单品种
python scripts/predict.py cf fu p ss ao  # 多品种
python scripts/predict.py --all --collect  # 先采集再预测

# 级联预测 (自动应用固化方案, 预检查数据后才加载模型)
python scripts/cascade_predict.py ss              # 单品种
python scripts/cascade_predict.py --all            # 全品种
python scripts/cascade_predict.py --three-star     # 信用≥2星（历史CLI名；现无真实3星）
python scripts/cascade_predict.py ss --collect     # 先采集数据再预测
python scripts/cascade_predict.py --all --collect-if-stale 2  # 滞后>2天自动采集

# 主观交易领航员 Copilot (预测永不压平；Vol 仅预警；Rich CLI + MD 研报)
python scripts/build_knowledge_base.py            # 从 L1 回测固化 knowledge_base.json
python scripts/copilot.py ss fu                   # 盘中入口：刷 1H → 推理 → 终端仪表盘
python scripts/copilot.py --three-star            # 信用≥2星
python scripts/copilot.py ss --no-refresh         # 跳过盘中 1H 刷新（用库内截面）
# 研报: reports/daily/YYYYMMDD_HHMM_<symbols>.md

# 月度回测
python scripts/monthly_backtest.py                # 全品种 walk-forward
python scripts/monthly_backtest.py ss rb sr       # 指定品种
python scripts/monthly_backtest.py --summary      # 仅打印历史对比

# 数据采集（动态 timeout；日线结束自动 run_guard）
python scripts/collect_1h.py ss
python scripts/collect_1h.py ta --with-basis   # 同时采集近/远月合约 (basis_momentum 协变量所需)
python scripts/data_management.py --1h
python scripts/data_management.py --daily --1h
python scripts/data_management.py --validate      # 卫生 purge + 校验；guard 失败 exit 2
python -m data.future_bar_guard --dry-run         # 幽灵 K 线预览
python -m data.future_bar_guard --strict          # 清理；有错 exit 1

# 系统诊断 / 单测
python scripts/data_health_check.py
python -m data.cli status
python -m unittest tests.test_future_bar_guard tests.test_vol_threshold_contract -v
```

**人类文档：** 见 `docs/README.md`（runbook / Copilot / Vol 风控状态）。

## 数据库设计

- SQLite，每品种一个文件：`db/futures_cf.db`
- 5 张表：`kline_1d`（含 30+ 技术指标列）、`main_continuous_1d`、`contracts`、`xreg_factors`、`metadata`
- 数据源：TqSdk（天勤量化，实时行情 + 历史数据）
- 与 ProjectOne 完全独立，不共享数据库
- **数据格式 (2026-07-02 迁移)：** kline_1d 和 main_continuous_1d 均存储 TqSdk 主力连续合约数据 (`KQ.m@`)，contract_code 统一为 `{SYM}_CONT`
- **1H 数据：** kline_1h 表存储主力连续 1H 数据，contract_code 为 `{SYM}_MAIN`；`--with-basis` 采集时也会存储具体月度合约（如 `TA2609`），供 `get_basis_1h` 计算近远月基差
- **基差流动性过滤 (2026-07-29):** `get_basis_1h` 自动对历史低 OI bar 置 NaN (合约自身 P95×5% 门槛),防止过期合约挂单价污染 basis 协变量;下游 `features.basis_momentum` NaN→0 回退
- **主链构建：** `data/main_chain.py` — 已标记 DEPRECATED，build() 简化为 kline_1d → main_continuous_1d 直接同步
- **协变量存储：** `xreg_factors` 表保存 CCL/OI/RSI 等协变量时间序列

## 报告规则

- 命名：`reports/YYYYMMDD_HHmm_<品种>.md`（单品种）或 `YYYYMMDD_HHmm_daily.md`（多品种）
- 模版：`reports/TEMPLATE.md`
- 内容：历史概况 → 周度汇总 → 逐日预测 → 核心结论 → 趋势判断 → 风险提示

## 数据验证管线 (2026-07-14 统一为 ensure_fresh_data)

所有预测/分析脚本在预测前统一调用 `cascade.data_validator.ensure_fresh_data()`，自动检查数据新鲜度并补采过期数据：

**共享函数 `ensure_fresh_data(symbols, auto_collect=True)`：**
1. 对每个品种调用 `validate_prediction_data()` 校验 (数据量+时效性+合约+gap)
2. 校验失败且 `auto_collect=True` 时自动采集：
   - bar 级别过期（同日内缺 bar）→ 仅补采 1H
   - 日级别过期 → 全量采集（日线+1H+主链+协变量）
3. 采集后重新校验，通过则放行，否则 SKIP

**使用此函数的脚本 (默认 auto_collect=True)：**
- `cascade_predict.py` / `predict.py` / `three_star_predict.py` / `variety_analysis.py`
- 均可通过 `--no-auto-collect` 或 `--no-collect` 禁用

**模型内校验** (`daily_model.py` / `hourly_model.py`)：
- 日线：`days_stale > max_allowed` 时抛出 ValueError（周末/假日放宽）
- 1H：`validate_prediction_data()` 始终运行，错误始终阻断

**时效性阈值矩阵**：

| 星期 | 1H max_stale | Daily max_stale | 说明 |
|:----:|:------------:|:---------------:|------|
| 周一 | 3 | 5 | 周五数据 3 天 |
| 周二 | 4 | 6 | 周五数据 4 天 |
| 周三 | 3 | 5 | 覆盖长周末 |
| 周四~五 | 1 | 3 | 正常交易日 |
| 周六 | 2 | 4 | — |
| 周日 | 3 | 4 | — |

> 注：不含中国法定节假日日历。长假后错误信息提示"可能是节假日导致，请先采集数据"。

## 信用档与新口径经济表 (2026-08-08)

> **无真实 3 星。** 2026-08-03 前 SP/SR 曾保留旧 3 星标签。2026-08-08 G005-E 全量 rebaseline 后，最高星级降为 2 星。  
> **可交易方向** = 加权 1H（`cascade/signal_contract`），日线斜率仅为 regime 副标签。详见 `docs/product_positioning.md`。  
> **全表**: `reports/research/20260808_g005e_results.md`（Phase 11/12 后协变量已刷新，星级不变）。

### 信用≥2 星（可辩护 / 边界）

| 档 | 品种 | 新口径 PF（约） | 备注 |
|----|------|-----------------|------|
| 弱正 | **SS, SR, M, JD** | 1.06–1.15 | n≈396 较足 |
| 弱正·小样本 | **CJ, LH** | 1.05–1.26 | n&lt;350 underpowered |
| 边界 | **EG, RB** | ≈1.00 | EV≈0 |

### 1 星（新口径经济弱/失效，12 品种）

SP TA FU BU P CF FG JM I AO UR MA — short_horizon **CF 仍失效**（Phase 11 best PF=0.90）；**BU 经 Phase 12 边际 GREEN**（PF=1.01, cal+hs）；**P 经 G004 翻正仍 1★**（PF=1.01）；多数 ha_body 单因子仍弱。

### 使用

```bash
# 信用≥2星一键预测（CLI 历史名 --three-star / three_star_predict）
python scripts/three_star_predict.py
python scripts/cascade_predict.py --three-star
python scripts/copilot.py --three-star

# 单品种
python scripts/cascade_predict.py ss
```

### 方案架构

- `config/prediction_scheme.py` — `SCHEMES` + `list_by_stars(min_stars=2)`
- `credit_stars` = `scheme.stars`（KB 唯一源）
- 固化/复评权威：`scripts/monthly_backtest.py` 完整 WF + v2 判据；禁止 3/7 点 scan
- 回测 P0 工程（bar-exact cutoff、resume 全点、标准 MaxDD）见 `20260808_tech_strategy_debt_post_fix.md`

### 方案类型说明

| 类型 | 特征 | 操作建议 |
|------|------|----------|
| trend / stable / short_range | **历史标签**，可能与当前 PF 不一致 | 以 stars + PF 为准 |
| short_range | 信号仅 T+1~12 权重 | BU 经 Phase 12 边际 GREEN (PF=1.01, cal+hs)；CF 仍失效 (Phase 11 best PF=0.90)；P 经 G004 换 rsi_state+reversal 后 PF=1.01（1★） |

### 协变量（配置层，Phase 11/12 刷新 2026-08-21；经济表现以 g005e + Phase 11 为准）

> 真源：`config/prediction_scheme.py` SCHEMES。下表仅做速查，变更以代码为准。

| 协变量 | 配置品种 |
|--------|----------|
| `calendar_cyclical` | SS / SP / FU / TA / EG（单协变量）；M / CF（组合底层）；BU（+hourly_slope, Phase 12） |
| `rsi_state` | RB / JD / LH（单协变量）；SR（+oi+calendar 组合）；P（+reversal_shadow, G004） |
| `hourly_slope` | CJ（单协变量）；AO（+calendar）；MA（+oi）；BU（+calendar, Phase 12） |
| `ha_body` | JM / FG / I→`reversal_shadow`(Phase 11)；M（+calendar 组合） |
| `reversal_shadow` | I（Phase 11 替换 ha_body）；P（+rsi_state, G004） |
| `ao_accel` | UR |

> `calendar_cyclical` 用户面单入口 → 4×1D 正余弦；成对使用。
> Phase 11 关键变更（2026-08-20/21）：SS reversal_shadow→calendar_cyclical; SP ha_body+calendar→calendar_cyclical; FU ha_body→calendar_cyclical; I ha_body→reversal_shadow; RB ha_body→rsi_state; JD hourly_slope→rsi_state; CJ ha_body→hourly_slope; LH ha_body→rsi_state; EG ha_body+oi+reversal_shadow→calendar_cyclical; TA ha_body→calendar_cyclical; BU ha_body→calendar_cyclical+hourly_slope (Phase 12)。M/P/SR 基线验证保持。

### 协变量优化

仅 `monthly_backtest.py` 完整 walk-forward；scan 不得指导固化。

## 关键脚本分类

**预测类：**
- `scripts/copilot.py` — **主观交易领航员**（推荐盘中入口）：Rich 仪表盘 + `reports/daily/` 研报；Vol 只打风险标签不压平预测；读 `config/knowledge_base.json` 信用背书
- `scripts/build_knowledge_base.py` — 从 L1 ECONOMIC_VERDICT + SCHEMES 生成 knowledge_base.json
- `scripts/predict.py` — 基础预测 (无级联，仅 TimesFM 直接预测，含 ensure_fresh_data 新鲜度检查)
- `scripts/cascade_predict.py` — 级联预测主入口 (自动识别固化方案，ensure_fresh_data 预检查，支持 `--collect` / `--collect-if-stale` / `--no-auto-collect`；实验性 Absolute Risk Overlay: `--vol-filter-neutral --vol-thr 0.55`，**默认 OFF**)
- `scripts/backtest_vol_gating_fullchain.py` / `rebuild_universe_neutral_report.py` — Path2 Neutral A/B 全链路；评分唯一源 `cascade/neutral_ab_report.py`（见 `STATE.md`）
- `scripts/three_star_predict.py` — 信用≥2星一键预测（历史名；`list_by_stars(2)`）
- 协变量优化：使用 `scripts/monthly_backtest.py` 完整 walk-forward（禁止用 3/7 点 scan 指导固化）

**回测类：**
- `scripts/monthly_backtest.py` — 月度 walk-forward 回测 (`--cache-interval` / `--max-points` / `--resume <checkpoint.jsonl>` 支持减量+断点续跑；JSONL 断点追加要求单写入者)
- `scripts/batch_backtest.py` — **DEPRECATED**，勿固化
- `scripts/backtest_1h.py` — **DEPRECATED**，勿固化

**数据运维类：**
- `scripts/data_management.py` — 调度入口（动态 timeout；cwd=`FM_ROOT`；**不**二次 purge）
- `scripts/daily_update.py` — 日线增量 + **唯一** `run_guard` 调用点（失败 exit 2）
- `data/trading_calendar.py` / `data/future_bar_guard.py` — 会话语义交易日 + 幽灵 K 线
- `scripts/data_self_heal.py` — 数据自愈
- `scripts/data_health_check.py` / `scripts/data_audit.py` — 健康/审计

**监控优化类：**
- `scripts/drift_detector.py` — 退化检测 (滑动窗口 DirAcc)
- `scripts/confidence_tracker.py` — 置信度追踪
- `scripts/residual_analyzer.py` — 残差分析
- `scripts/covariate_advisor.py` — 协变量建议

**报告管理类：**
- `scripts/organize_reports.py` — 整理历史报告，按品种分类保存到 reports/history/
- `scripts/variety_analysis.py` — 指标分析预警 (技术面+持仓+CCL+Copilot融合, 支持 `--all` / `--no-collect` / `--no-predict`, 报告保存至 `reports/<symbol>/`)
- `cascade/prediction_tracker.py` — 历史预测追踪模块 (记录/查询/准确率统计)

### 历史预测追踪 (2026-07-08 新增)

每次预测自动记录到 `reports/history/{symbol}/predictions.json`，支持：

```bash
# 查看某品种的预测准确率报告
python -c "from cascade.prediction_tracker import generate_accuracy_report; print(generate_accuracy_report('ur'))"

# 获取最近N次预测记录
python -c "from cascade.prediction_tracker import get_recent_predictions; print(get_recent_predictions('ss', 5))"
```

**报告新增内容**：信号解读后显示"历史预测对比 (最近5次)"表格

**整理历史报告**：
```bash
python scripts/organize_reports.py  # 将现有报告按品种分类到 reports/history/
```

# 指标分析预警 (2026-07-09 新增)

多品种技术面 + 持仓 + CCL 综合预警分析，支持横向对比：

```bash
python scripts/variety_analysis.py p m oi y         # 指定品种 (默认含 Copilot 预测)
python scripts/variety_analysis.py --all              # 全品种
python scripts/variety_analysis.py ss rb --no-collect # 跳过数据采集
python scripts/variety_analysis.py sh --no-predict    # 仅技术面+CCCL，跳过 TimesFM 预测
```

报告保存至 `reports/YYYYMMDD_analysis/analysis_<symbol>.md`，包含 6 个章节：
价格走势 → 技术指标 → 持仓分析 → CCL 持仓力量 → CCL 异动预警 → 综合判断

模版：`reports/TEMPLATE_analysis.md`

## Regime-Covariate 分析 (2026-07-23 新增)

基于市场状态（Regime）的协变量优化分析工具，识别不同市场环境下最优协变量组合。

**核心架构**：
- `cascade/regime_features.py` — 特征提取（vor_skew, rolling_hurst, rolling_adx, vol_cone_position）
- `cascade/regime_classifier.py` — K-Means Regime 分类器（4 Regime: high_vol_trend, low_vol_narrow, wide_oscillation, transition）
- `cascade/covariate_analysis.py` — 协变量相关性分析与聚类
- `cascade/walk_forward.py` — Walk-Forward Optimization（IS/OOS 分割, 交叉验证）
- `cascade/deployment_monitor.py` — 部署监控（性能追踪, 异常预警）

**6 步分析管线**：
1. 特征提取（10 个滚动特征, 40/60 窗口）
2. Regime 分类（K-Means, 4 个 Regime）
3. 协变量相关性分析
4. Walk-Forward Optimization（IS/OOS 验证）
5. SHAP 归因分析
6. Regime-Covariate 映射矩阵

**使用**：
```bash
# 完整分析管线（9 品种, 2018-2024）
python scripts/regime_covariate_analysis.py \
    --varieties rb jm i ss ur sp cf fg ma \
    --is-years 2018-2022 \
    --oos-years 2023-2024 \
    --n-regimes 4 \
    --output-dir reports/regime_analysis/run_001

# 单品种测试
python scripts/regime_covariate_analysis.py --varieties ss --n-regimes 4
```

**输出**：
- `reports/regime_analysis/run_XXX/regime_classification_*.json` — Regime 分类结果
- `reports/regime_analysis/run_XXX/correlation_analysis_*.json` — 协变量相关性
- `reports/regime_analysis/run_XXX/mapping_matrices_*.json` — Regime-Covariate 映射矩阵

**关键认知**：
- Regime 分析的价值在于**动态路由**（预测时实时识别当前 Regime，动态选择协变量）
- 避免静态绑定（不要把协变量永久写死在 prediction_scheme.py 中）
- 评估指标必须包含 PF（盈亏比）和 EV（期望值），DirAcc 提升不等于盈利能力提升

## 数据管理策略 (Predict-then-Collect)

不使用 cron 定时任务。每次预测请求时自动检查并补齐数据。

**预测前自动采集 (统一由 ensure_fresh_data 驱动)：**
- 所有预测/分析脚本默认开启 auto-collect，数据过期时自动补采
- bar 级别过期 → 仅补 1H；日级别过期 → 全量采集
- 可通过 `--no-auto-collect` / `--no-collect` 禁用

**手动采集：**
```bash
python scripts/collect_1h.py              # 全品种 1H
python scripts/collect_1h.py ss rb        # 指定品种
python scripts/collect_1h.py ta --with-basis  # 同时采集近/远月合约 (basis_momentum)
python -m data.cli collect --all          # 全品种日线
```

**高风险路径保护 (见 loop-constraints.md)：**
- 禁止自动修改：`config/prediction_scheme.py`, `cascade/*.py`, `data/config.py`
- 允许操作：`scripts/`, `reports/`, `db/` (只增不删)
