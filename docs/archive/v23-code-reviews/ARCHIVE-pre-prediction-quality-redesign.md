# 归档：预测质量改造之前的未提交工作区

- **分支**: `archive/pre-prediction-quality-redesign`
- **标签**: `archive/pre-prediction-quality-redesign-20260915`
- **基线**: `master` (`e22db35`)，即 `feat/prediction-quality-redesign-v23` 分出之前
- **日期**: 2026-09-15
- **处理**: **不要合并**。改造目标已改为纯预测质量（DirAcc / endpoint_MAPE / DM / BH-FDR），本快照里的 PF/EV 成功条件、1★ 品种集切换、shell 路径与 Supervisor 小改动全部作废。

## 里面有什么

当时工作区里 48 个已跟踪文件的未提交修改，主要包括：

- `scripts/praxist_goal.yaml`：仍按 `ev>0` 和 PF ratio，并把 1★ 品种集换成 i/jm/fg/…
- `scripts/praxist_supervisor.py`、`task_FM/task.yaml`、`task_FM/known_verdicts.inc.md`
- 一批 `scripts/batch_*.sh` / `phase*.sh` 的路径或注释改动
- 若干 docs 与 `STATE.md`

## 不要做什么

- 不要向 `master` 或 `feat/prediction-quality-redesign-v23` 开 PR
- 不要 cherry-pick 进改造线（成功条件和品种宇宙已经过时）
- 需要对照旧目标时，检出本分支或看本标签即可

## 现行工作

继续走 `feat/prediction-quality-redesign-v23`。
