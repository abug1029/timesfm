<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-09-09 -->

# tests

## Purpose

合约级与回归测试：数据防护、方案快照、Vol/Neutral 门禁、A2 完整性、特征防回归。

## Key Files

| File | Description |
|------|-------------|
| `test_future_bar_guard.py` | 幽灵 K 线防护 |
| `test_vol_threshold_contract.py` | ThrPolicy 合约 |
| `test_neutral_ab_report.py` | Neutral 评分唯一源 |
| `test_validation_criteria.py` | v2 判据 |
| `test_prediction_scheme_phase9.py` | 20 品种 scheme 快照 |
| `test_kb_schemes_consistency.py` | KB ↔ SCHEMES 一致性 |
| `test_ha_body_toxic_blacklist.py` | AO/JD 禁 ha_body |
| `test_a2_p1_*.py` / `test_a2_p2_integrity.py` | A2 管道 |
| `test_calendar_cyclical.py` | 日历协变量 |
| `test_basis_oi_filter.py` | 基差 OI 过滤 |
| `test_lgbm_features.py` | LGBM 特征防穿越 |
| `test_vol_scaled_mae.py` | 波动缩放 MAE |
| `test_scan_significance.py` | scan 显著性门槛 |
| `test_covariate_audit.py` | 协变量质量审计 (19 tests, 5 维度: 平稳性/范围/NaN/前视偏差/信息量, Phase Q1 D6) |
| `test_supervisor.py` | 三环监督环（harvest / 429 / cycle / atexit 隔离） |
| `test_harvest_proposals.py` | 方案 A 提案收割（机制校验 / 去重 / 选座） |
| `test_covariate_pool.py` | 协变量池 schema 与归档拒绝 |
| `test_aligned_slow_loop.py` | 慢环 claim/recover |
| `test_goal_dsl.py` | goal.yaml DSL 白名单求值 |
| `test_praxist_task_contract.py` | `config/praxist_task.yaml` 预注册契约 |

## For AI Agents

### Working In This Directory

- 改 `evaluation_metrics` / scheme / Vol thr 后优先跑对应合约测试。
- 快照测试故意检测篡改：改 SCHEMES 必须同步更新期望值（经人工批准）。
- 不新增“为通过而 mock 掉门禁”的测试。

### Suggested smoke after backtest-related changes

```bash
python -m unittest \
  tests.test_validation_criteria \
  tests.test_vol_scaled_mae \
  tests.test_neutral_ab_report \
  tests.test_a2_p1_runtime \
  tests.test_future_bar_guard -v

# Praxist 三环（改 supervisor / harvest / 任务契约后）
python -m pytest tests/test_supervisor.py tests/test_harvest_proposals.py \
  tests/test_covariate_pool.py tests/test_praxist_task_contract.py tests/test_goal_dsl.py -v
```

## Dependencies

### Internal

- `cascade/`, `config/`, `data/`, `scripts/`

<!-- MANUAL: -->
