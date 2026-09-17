# batch 实验脚本归档说明

- **归档日期**: 2026-09-17
- **原因**: 这批脚本服务 v22 时代的批量回测实验流程（batch_f*/batch_baseline_*/batch_p1x*/batch_*_cov_gap 等），v23 口径切换后无复用计划。
- **内容**: 26 个 batch_*.sh + `_batch_lib.sh` + `start_praxist.sh` + 2 个配套杀手脚本（`_kill_batch.ps1`、`_kill_cov_gap.ps1`），共 30 个文件。

## 事实记录

1. **死路径**: 22 个 batch 脚本硬编码 `FM_ROOT="D:/FlyBuddy/FM_a"`（Windows 路径，WSL 内不存在，死路径）；`_batch_lib.sh` 仅在头注释中要求调用方设置该值。这正是「不修复而归档」的原因——它们只能在旧的 Windows/MSYS 环境下运行，在当前 WSL 权威源里已无法工作。
2. **start_praxist.sh 漂移**: 此处归档的是 `scripts/start_praxist.sh`（漂移版），事实如下：
   - `--supervisor` / `--once` 分支启动 `praxist_supervisor.py` 时缺 `--goal scripts/praxist_goal.yaml`；
   - 硬编码模型名 qwen3.7-plus 已过时（当前走 `.env.praxist` + primary provider）；
   - 默认分支走 fast-loop，而现行规范走监督环统一调度。
3. **现行规范启动方式**: 见 `docs/runbook_praxist_three_loop.md:31-38`（`setsid nohup` + `praxist_supervisor.py --goal scripts/praxist_goal.yaml`）。根目录的 mini 版 `/home/abug/timesfm/start_praxist.sh` 仍在原位，未动。

## 关联文档

- `docs/supervisor_restart_backlog.md` — IDLE_HOLD 启动守卫等价物等 supervisor 侧重启待办。
