# supervisor 重启待办

> 登记日期: 2026-09-17。**不重启运行中的 supervisor**；以下两项在下次 supervisor 自然停止或显式重启时一并实施。

## 1. 菜单 track 行固定前缀「【旧口径线索·非证据】」

- 位置: `scripts/praxist_supervisor.py:745` 附近，`materialize_covariate_menu` 渲染 track 行处：
  `tr = " [track: %s]" % v["track_record"] ...`
- 做法: 给菜单 track 行加固定前缀「【旧口径线索·非证据】」（防御性，防止 pool 未来再写入裸数字时被当作证据）。
- 背景: pool 源头已在 2026-09-17 去数字（covariate_pool 内 10 条 v22 旧口径 track_record 标注，见 git log）。

## 2. IDLE_HOLD 守卫等价物

- 背景: 原 `scripts/start_praxist.sh`（已归档至 `docs/archive/batch/`）启动前检查 `docs/superpowers/reports/praxist_20260907_ctrl/IDLE_HOLD` 文件，存在即拒绝启动（exit 78），作为启动守卫。
- 现状: 脚本归档后该守卫失去入口，当前无引用。
- 做法: 如需该功能，应在 supervisor 侧补等价实现（启动周期检查 IDLE_HOLD 标记文件，存在则拒绝启快环）。当前仅为登记，无实施计划。
