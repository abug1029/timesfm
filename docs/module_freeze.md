# 子策略冻结表（CF-11…14 / 19 / 20）

**裁决日期**: 2026-08-08（ultragoal G003）

| 模块 | 裁决 | 生产姿态 |
|------|------|----------|
| 静态 SCHEMES | CF-11 **A** | **唯一生产协变量表**；Regime 动态路由仅研究 |
| Vol / Neutral 压平 | CF-12 **A** | **永不默认 ON**；Copilot 仅预警 |
| A2 LGBM / 残差 Track B | CF-13 **A** | **永久关闭**（0/5 GO）；代码保留作归档 |
| Crack spread | CF-14 **A** | 2027 Q4 复评前不固化 |
| `cascade/walk_forward.py` IS-IR | CF-19 **A** | **禁止用于 SCHEMES 固化** |
| `batch_backtest` / `backtest_1h` | CF-20 **A** | 遗留入口；启动时 deprecation 警告 |

生产入口：`scripts/copilot.py`、`scripts/cascade_predict.py`。  
固化权威 WF：`scripts/monthly_backtest.py` only。
