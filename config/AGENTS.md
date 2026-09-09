<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-09 -->

# config

## Purpose

品种固化方案、回测超参、板块映射与 Copilot 信用知识库。固化决策的**配置真相源**。

## Key Files

| File | Description |
|------|-------------|
| `prediction_scheme.py` | 20 品种 `SCHEMES`：协变量、stars、dir_acc、short_horizon、signal_weight（**高风险，禁止自动改**） |
| `backtest_config.py` | 回测池、`CONTEXT_BARS=480` / `HORIZON=24` / `STEP=24`、TICK_SIZES、`SLIPPAGE_TICKS=2` |
| `sector_map.py` | agri / chem / black 板块唯一表 |
| `crack_spread_pairs.py` | 裂解价差配对与 ratio |
| `knowledge_base.json` | Copilot L1+SCHEMES 信用背书（由 `build_knowledge_base.py` 生成） |
| `praxist_task.yaml` | Praxist 预注册评估口径（n/IC/EV）；校验器 `scripts/praxist_validate_task.py` |

## For AI Agents

### Working In This Directory

- **`prediction_scheme.py` 禁止自动编辑**；任何 SCHEMES 变更需人工确认 + 完整 walk-forward 证据。
- 固化门禁真相：`docs/validation_criteria.md` v2 + `scripts/phase4d_parse_results.verdict`。
- 禁止用 3/7 点 scan 结果改 SCHEMES；只用 `monthly_backtest` 完整 WF。
- 改 scheme 后跑：`tests/test_prediction_scheme_phase9.py` + `tests/test_kb_schemes_consistency.py`。

### Parameter Contract (backtest_config)

| Param | Value | Meaning |
|-------|-------|---------|
| CONTEXT_BARS | 480 | 1H context |
| HORIZON | 24 | 预测时域 bars |
| STEP | 24 | 非重叠 walk-forward 步长 |
| CONTEXT_DAYS / HORIZON_DAYS | 250 / 22 | 日线 stage |
| SLIPPAGE_TICKS | 2 | 双边合计 2 tick |
| commission | 0 | 默认不计手续费 |

### Known Issues (2026-08-08 audit)

1. **实盘信号 ≠ 回测信号**：实盘 `cascade_predict` 用 `daily_slope + trend_threshold` 定方向，并用 `signal_weight` 做加权价；回测用 `sign(pred[T+24]-base)`。
2. **short_horizon_only** 品种实盘 T+13..T+24 权重为 0，回测仍评 T+24 终点。
3. **2026-08-08：系统内无 3 星**；信用≥2 见 `list_by_stars(2)`；全表 `20260808_g005e_results.md`。
4. `credit_stars` = `scheme.stars`（KB 镜像）；`scheme.context_bars` 与 monthly 默认 480 对齐。

### Testing Requirements

```bash
python -m unittest tests.test_prediction_scheme_phase9 tests.test_kb_schemes_consistency tests.test_ha_body_toxic_blacklist -v
```

## Dependencies

### Internal

- 被 `scripts/monthly_backtest.py`、`cascade_predict.py`、`copilot.py`、A2 workers 读取

### External

- 无

<!-- MANUAL: -->
