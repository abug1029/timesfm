# spec 七组件 → 承载方映射表（H3 交付物）

> spec §4.5 协议指纹由 7 个组件构成，任一变化都意味着"评估口径不同"。
> 本表给出每个组件的承载位置，作为跨实现校验的唯一索引。

| # | spec 组件 | 承载方 | 来源常量 | 当前值 |
|---|----------|--------|----------|--------|
| 1 | CONTEXT_BARS / CONTEXT_DAYS | `protocol_fingerprint` | `backtest_config.CONTEXT_BARS` / `CONTEXT_DAYS` | 480 / 25 |
| 2 | EVAL_WINDOW_BARS | `protocol_fingerprint` | `backtest_config.EVAL_WINDOW_BARS` | — |
| 3 | STEP | `protocol_fingerprint` | `backtest_config.STEP` | — |
| 4 | HORIZON | `protocol_fingerprint` | `backtest_config.HORIZON` | — |
| 5 | cutoff 约定 | `protocol_fingerprint` | `compute_protocol_fingerprint(cutoff_convention=...)` | `bar_close` |
| 6 | cov_fill 版本 | `protocol_fingerprint` | `evaluator.COV_FILL_VERSION` | `v2` |
| 7 | 复权规则版本 + 换月守卫版本 | `protocol_fingerprint` | `evaluator.ADJUSTMENT_RULE_VERSION` / `ROLL_GUARD_VERSION` | `v1` / `v1` |

## 不在 `protocol_fingerprint` 的组件（另有承载方）

| spec 组件 | 承载方 | 说明 |
|----------|--------|------|
| 模型指纹（权重哈希）+ 预测参数 | `experiment_fingerprint`（**Phase 7 从零建**，H4 标注） | 当前全仓无 `compute_experiment_fingerprint` |
| 特征代码 git_rev | `registry.verdict["git_rev"]` | 每个裁决自带 |
| covariate_pool_rev | 由 pool 文件路径 + 内容 hash 派生 | 当前无显式字段，`covariate_pool.json` 变更即视为 pool rev 变化 |
| 指标定义版本（dir_acc 口径 + 零变动策略） | 隐式（代码版本） | 尚无显式 `metric_version`，仅 `protocol_v3` 字符串标识 |

## 命名注意

| 名称 | 含义 | 承载 |
|------|------|------|
| `protocol_fingerprint` | 评估口径身份（决定可比性） | evaluator.py |
| `experiment_fingerprint` | 单次实验身份（模型+数据快照） | Phase 7 建 |
| `research_target_hash` | 研究问题身份（稳定，决定 family 边界） | cascade/research_family.py |
| `target_snapshot_hash` | 本次实验所用数据快照内容哈希（随运行变化） | Phase 7（`experiment_fingerprint` 内部） |

**`research_target_hash` vs `target_snapshot_hash` 不得混用**（spec v8）：
- 前者 = 研究问题**身份**（稳定，决定"是不是同一 family"）
- 后者 = 数据快照**内容**（变化，决定"实验记录可否合并"）
