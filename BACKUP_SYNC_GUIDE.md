# 备份

2026-10-07 晚裁定：备份与活仓同一个仓库。推 `origin`（GitHub）即可。

不再使用独立 backup remote，不再使用 `scripts/backup_data_assets.sh`，不再向 `/root/timesfm-data` 做日快照。

入库路径：`task_FM/config/aligned_verdicts.jsonl`、`baseline_points_*.jsonl`、`baseline_metrics.json`、`.omc/supervisor_decisions.jsonl`。

不入库：`.env`、`.env.*`、`data/cache/`、`logs/`。
