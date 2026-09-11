<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-11 -->

# cascade

## Purpose

跨周期级联预测核心库：日线 TimesFM → 日线斜率 → 1H XReg 预测；另含统一经济指标秤、Vol/Neutral 评分、Regime/LGBM 特征与 walk-forward 辅助框架。

## Key Files

| File | Description |
|------|-------------|
| `daily_model.py` | Stage-1 日线预测，产出 `horizon_slope`（高风险，改前需人工确认） |
| `hourly_model.py` | Stage-2 1H 级联 + 协变量 XReg（高风险） |
| `features.py` | 协变量构建：`ha_body` / `calendar_cyclical` / `reversal_shadow` 等（高风险） |
| `evaluation_metrics.py` | **全项目唯一经济指标秤**：PF / EV / MaxDD / DirAcc / net PnL |
| `data_validator.py` | `ensure_fresh_data()` 预测前数据门禁 |
| `vol_risk_filter.py` | 波动熔断 + ThrPolicy + Neutral override |
| `vol_gating_replay.py` | 离线 thr 重算（不重跑 TimesFM） |
| `neutral_ab_report.py` | **Neutral A/B 唯一评分源** |
| `neutral_ab_render.py` | Neutral 报告 Markdown 渲染 |
| `lgbm_features.py` | **归档**（A2 Track B 已关）。生产入口 `cascade_predict` / `monthly_backtest` / `copilot` 不 import；仅 A2 脚本与测试仍引用 |
| `walk_forward.py` | Regime 协变量 IS/OOS 优化器（IR 体系，非 PF/EV） |
| `regime_features.py` / `regime_classifier.py` | Regime 特征与 KMeans |
| `prediction_tracker.py` | 历史预测 JSON 追踪 |
| `ccl_monitor.py` | CCL 持仓力量监控 |
| `live_ledger.py` | 实盘 ledger 辅助 |

## Subdirectories

无子包；测试见 `../tests/`。

## For AI Agents

### Working In This Directory

- **禁止自动改**（见 `loop-constraints.md`）：`daily_model.py`、`hourly_model.py`、`features.py`。
- 经济指标只从 `evaluation_metrics.calc_net_metrics` 出；禁止在 scripts 内复制 PF/EV 公式。
- Neutral/R1 裁决只从 `neutral_ab_report` 出；禁止旁路算分。
- 改指标语义必须同步：`tests/test_vol_scaled_mae.py`、`test_neutral_ab_report.py`、stdout 打印口径。

### Known Design Gaps (2026-08-08 audit)

1. **MaxDD** 用 `(cum-peak)/(|peak|+1.0)`，非标准净值回撤；v2 门禁阈值继承此畸变。
2. **DirAcc** 文档称“仅报告不决策”，但月度分类/星级/KB 仍重度依赖。
3. `walk_forward.py` 以 **IS IR** 选最优组合 → 与 monthly PF/EV 体系分叉，勿用于固化 SCHEMES。

### Testing Requirements

```bash
python -m unittest tests.test_vol_scaled_mae tests.test_neutral_ab_report tests.test_vol_threshold_contract -v
```

### Common Patterns

- 滑点：`tick_size * SLIPPAGE_TICKS`；`dirs==0` 不计费。
- 中性 override 时 NetPnL 必须严格为 0。

## Dependencies

### Internal

- `config/backtest_config.py` — TICK_SIZES / SLIPPAGE_TICKS
- `config/prediction_scheme.py` — 协变量方案（运行时读，不写）
- `data/data_store.py` — 含 `BacktestDataStore`

### External

- TimesFM 2.5、PyTorch、pandas/numpy；LightGBM 仅 A2 归档路径，生产入口不依赖

<!-- MANUAL: -->
