# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## 目录结构

```
D:\FlyBuddy\FM_a\
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

**必需：**
```bash
# TqSdk 凭证 (已配置在 .env)
TQSDK_ACCOUNT=your_account
TQSDK_PASSWORD=your_password

# 激活环境 (共享底座)
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a
```

**数据库位置：** `db/futures_<symbol>.db` (SQLite，每品种独立)

## 快速使用

```bash
# 激活环境 (共享底座)
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a

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
**回测资产目录：** 见 `docs/backtest_registry.md`（141 实验, 20 品种, 避免重复回测）。

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
- **derived_view 规则 (2026-09-01, P0b)**：`reports/` 全部为衍生视图（可从 predictions.json / 回测 JSONL 重建），
  冲突时以 STATE.md + 磁盘回测产物为准；权威状态仅 STATE.md（canonical_state 声明见 STATE.md 头部）

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

> **无真实 3 星。** 详见 `AGENTS.md` 同节与 `reports/research/20260808_g005e_results.md`。  
> 可交易方向=加权1H（`docs/product_positioning.md`）。

**≥2★**: CJ SS SR M JD LH（弱正 PF 1.06–1.29）+ EG RB（弱边界 PF 1.04–1.09）  
**1★**: SP TA FU BU P CF FG JM I AO UR MA  
（P 已 G004 换 `rsi_state+reversal_shadow`，PF=1.01 刚过线，仍 1★；BU 经 Phase 12 换 `calendar_cyclical+hourly_slope` PF=1.01 边际 GREEN，仍 1★）  
**待固化**: SH 烧碱（data/config.py 已加入品种池，Phase 11 best PF=0.90 无 GREEN，待后续数据积累后复评，不纳入 SCHEMES）

```bash
python scripts/three_star_predict.py          # stars≥2
python scripts/cascade_predict.py --three-star
python scripts/copilot.py --three-star
```

固化权威：`monthly_backtest.py`；`list_by_stars(2)` 在 `prediction_scheme.py`。

## 关键脚本分类

**预测类：**
- `scripts/copilot.py` — **主观交易领航员**（推荐盘中入口）：Rich 仪表盘 + `reports/daily/` 研报；Vol 只打风险标签不压平预测；读 `config/knowledge_base.json` 信用背书
- `scripts/build_knowledge_base.py` — 从 L1 ECONOMIC_VERDICT + SCHEMES 生成 knowledge_base.json
- `scripts/predict.py` — 基础预测 (无级联，仅 TimesFM 直接预测，含 ensure_fresh_data 新鲜度检查)
- `scripts/cascade_predict.py` — 级联预测主入口 (自动识别固化方案，ensure_fresh_data 预检查，支持 `--collect` / `--collect-if-stale` / `--no-auto-collect`；实验性 Absolute Risk Overlay: `--vol-filter-neutral --vol-thr 0.55`，**默认 OFF**)
- `scripts/backtest_vol_gating_fullchain.py` / `rebuild_universe_neutral_report.py` — Path2 Neutral A/B 全链路；评分唯一源 `cascade/neutral_ab_report.py`（见 `STATE.md`）
- `scripts/three_star_predict.py` — 信用≥2星一键预测（历史名 three_star）
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

## MindMemOS 记忆配置

本项目使用 MindMemOS 进行跨会话记忆管理。

| 参数 | 值 |
|------|-----|
| app_id | `flybuddy-fm-a` |
| user_id | `abug1029` |

**写入记忆时**必须带 `--app-id flybuddy-fm-a`：
```bash
mindmemos memory add --content "..." --app-id flybuddy-fm-a
```

**搜索记忆时**必须用 filter 隔离：
```bash
mindmemos memory search "..." --filter '{"app_id": "flybuddy-fm-a"}'
```

Python SDK:
```python
from mindmemos_sdk import MindMemOSClient
with MindMemOSClient(app_id="flybuddy-fm-a") as client:
    client.memory.add(messages=[...])
    client.memory.search("...", filters={"app_id": "flybuddy-fm-a"})
```
