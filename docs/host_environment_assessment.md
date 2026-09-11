# 宿主环境评估报告（Grok Bot 盒）

> **⚠️ 2026-09-09 起宿主再次迁移：以下 Grok Box（Debian/`/workspace`/15GiB/CPython 3.13）结论为历史记录，当前事实以下表为准。**
>
> | 项 | 当前值（2026-09-11 核对，WSL） |
> |----|-----|
> | 主机 | **WSL2**（Windows 10，发行版 Ubuntu-22.04.5，kernel 6.18 microsoft-standard） |
> | 项目根 | **`/home/abug/timesfm`**（GitHub `abug1029/timesfm`，分支 **`master`** HEAD `9653264`） |
> | Python | 本仓 **`.praxist-venv`（CPython 3.11.15）**，FM_a 与 PRAXIST 共用 |
> | CPU / 内存 | 8 vCPU / **7.7 GiB total**；Swap 以现场 `free -h` 为准（2026-09-11 测得 2.0Gi，**不要写死 0**） |
> | GPU | 无 |
> | 磁盘 | `/` 约 1TB，用量 2% |
> | 行情库 | **本仓 `db/` 为真实目录**（29 个 `futures_<sym>.db`），不再是 `/workspace` symlink；`.env` 为真实文件 |
> | 权重 | 本仓 `models/timesfm-2.5-200m-pytorch/` |
> | Praxist CLI | 本仓 `.praxist-venv/bin/praxist` |
>
> 旧盒的 N=4≈8.53GiB 结论在 7.7GiB WSL 上更不可持续；flock≤2 / `MemAvailable<2GiB` 拒启的硬顶继续有效。旧 `/workspace` 硬编码残留会报 `assets_archive_error: Permission denied: '/workspace'`（已 catch，非阻塞，待清理）。

> **as_of**: 2026-09-04 09:31 CST（**已被上方 2026-09-09 WSL 事实取代，保留作历史**）
> **取代**: 文档中基于 Windows/`D:/FlyBuddy`、旧 Linux `/root/timesFM_fu`（约 1.9GB RAM / 2 核）的环境结论。那些评估**不适用于**当前宿主。  
> **实测命令**: `lscpu` / `free -h` / `df -h` / `nvidia-smi`（无设备）

## 1. 实测配置

| 项 | 值 |
|----|-----|
| 主机角色 | Grok Bot 共享 Linux 盒（多岗共用同一文件系统） |
| OS | Debian GNU/Linux 13 (trixie), kernel 6.12.x |
| CPU | 8 × Intel Xeon（x86_64，1 socket，无超线程） |
| 内存 | 15 GiB total；评估当日 available ≈ 11 GiB；**无 Swap** |
| GPU | **无**（无 nvidia 设备 / 无 `nvidia-smi`） |
| 磁盘 | overlay ≈ 126G，评估当日 Used ≈ 17G / Avail ≈ 104G |
| 项目根 | `/workspace/repos/timesfm-abug1029`（GitHub `abug1029/timesfm`） |
| Python（FM_a） | `/home/abug/timesfm/.praxist-venv`（CPython 3.13） |
| 行情 SSOT | `db` → symlink → `/workspace/repos/timesFM_fu/db`（由「行情」岗维护） |
| TQSDK / `.env` | `.env` → symlink → `timesFM_fu/.env`（gitignore，不复制密钥） |
| Praxist CLI | 独立 venv（目标 `/home/box/.praxist-venv` 或本仓 `.praxist-venv`），与 FM_a `.venv` 隔离 |
| Praxist LLM | 火山方舟 Anthropic 兼容：`ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`（gitignore `.env.praxist`） |
| TimesFM（Praxist） | **独立权重目录**（本仓 `models/`）；磁盘可有副本；**容量试跑阶段允许并行加载**（旧「加载互斥」已解除，见 §3） |

## 2. 相对旧文档的变化

| 旧结论（过时） | 当前结论 |
|----------------|----------|
| Windows / `D:/FlyBuddy/...` | Linux 盒路径见上表 |
| `/root/timesFM_fu`，约 1.9GB RAM | 15 GiB RAM，根在 `timesfm-abug1029` |
| 「2 核硬约束」 | **8 核**；瓶颈仍是 **CPU TimesFM 推理 + 内存**，不是核数 |
| 评估期 RSS <1.7GB 才安全 | 单次 TimesFM CPU 峰值仍约 1.5–4GB 量级（视是否常驻）；15GB 余量充足；**串行-only 旧红线已解除**（容量试跑可并行，见 §3） |
| 可与采集窗口撞内存 | 采集由「行情」岗在 `timesFM_fu` 执行；容量试跑阶段 **允许** 并行 peer eval / 多份 TimesFM 共载（测 RSS/OOM） |

## 3. 能力评估（给 Praxist / TimesFM）

> **2026-09-04 用户授权（约 09:23 CST）：** 盒配置远高于旧宿主约束；为测最大可持续容量，**解除**「评估必须串行 / 禁止与预测岗同时常驻第二份 TimesFM」红线。容量试跑阶段：**并行 peer eval / 多份 TimesFM 共载 OK**，同时计量 RSS/OOM。e2e 可并行跑 `fm_eval`。恢复生产长跑策略前须据实测再定。

**适合**
- 一份或多份独立 TimesFM 加载（Praxist 慢环 / 容量试跑）+ Praxist 监督环
- LLM peers 在云端并行探索；本机评估 **容量试跑阶段可并行**（旧「串行-only」已解除）
- 短试跑 / 单品种 toy task / doctor 验收 / **最大可持续容量试跑**（并行 fm_eval、多份权重共载）

**不适合 / 红线**
- ~~与「预测」岗同时常驻两份 TimesFM~~ → **旧约束已解除（容量试跑阶段）**；仍须监控 RSS/OOM，多副本可能顶满 15 GiB / 无 Swap
- GPU 批推（本宿主无 GPU）；`monthly_backtest --parallel` 可按容量试跑需要抬高，但以实测 OOM 边界为准
- 把旧路径 `/root/...` 或 Windows venv 写进新脚本

**容量试跑建议（就绪后执行，非正式长跑）**
1. `praxist doctor` 全绿  
2. 单品种（如 `fu` 或 `m`）加载独立模型，记录 RSS 峰值与单次评估墙钟时间  
3. 在串行基线之上逐步加压：并行 peer eval / 多份 TimesFM 共载，记录可持续上限与 OOM 边界  
4. 将实测峰值写回本文件 §4  

## 4. 试跑实测（容量试跑，非正式长跑）

| 指标 | 结果 |
|------|------|
| doctor | **ok**（无 fail）；warn：`praxist_console` 不在 PATH、`PRAXIST_MODEL` provider default、`config_dir`/`registry_dir` 默认路径、`codex_skills` 0/10 |
| 独立模型路径 | `/workspace/repos/timesfm-abug1029/models/timesfm-2.5-200m-pytorch`（`TIMESFM_MODEL_PATH` from `.env.praxist`） |
| 单次评估 RSS 峰值 | **≈ 2.11 GiB**（max ≈ 2161 MiB；`resource.getrusage(RUSAGE_CHILDREN).ru_maxrss`） |
| 单次评估耗时 | **≈ 6.6–6.7 s** wall（单品种 `fu`，`--no-auto-collect`，串行冷/热加载各次独立进程） |
| 连续 N 次是否稳定 | **是**（N=3，exit 0，无 OOM；与「预测」岗无共驻冲突） |

**三次串行明细**（`.praxist-venv/bin/python /tmp/timed_run.py .praxist-venv/bin/python scripts/cascade_predict.py fu --no-auto-collect`；`RUSAGE_CHILDREN`；GNU `/usr/bin/time` 未安装）：

| Run | Wall | Peak RSS | OOM? | log |
|-----|------|----------|------|-----|
| 1 | 6.610 s | 2160.5 MiB (2.110 GiB) | 否 | `/tmp/cascade_fu_run1.log` |
| 2 | 6.602 s | 2161.1 MiB (2.110 GiB) | 否 | `/tmp/cascade_fu_run2.log` |
| 3 | 6.697 s | 2161.1 MiB (2.110 GiB) | 否 | `/tmp/cascade_fu_run3.log` |

试跑前 `free -h` available ≈ 11 GiB；试跑后 available ≈ 10 GiB。未执行 `praxist start`。试跑期间确认无「预测」岗 TimesFM / 第二份 cascade 共驻。

### 结论

**能承载「常驻一份 TimesFM + 串行评估」**（§4 基线实测）。单份峰值约 2.11 GiB，相对 15 GiB / 0 Swap 有充足余量。**2026-09-04 起串行-only 红线已解除（容量试跑）**：允许并行 peer eval / 多份共载以测最大可持续容量；仍须盯 RSS/OOM。上表 N=3 串行数字保持为基线事实，不改为并行结果。

## 4b. 并行承载压测（用户批准后）

> 政策变更 as_of 2026-09-04 09:24 CST：允许并行 fm_eval。  
> **实测 as_of 2026-09-04 09:31 CST**（e2e `run_084806` 自然 peer 并发 + 安全 shed；未另起 supervisor）。

| 并行度 N | 峰值 RSS 合计 | 单进程峰值 RSS | 最低 available | OOM? | 备注 |
|----------|---------------|----------------|----------------|------|------|
| 2 | ≈ 4741 MiB (4.63 GiB) | ≈ 2372 MiB | ≈ 3.77 GiB | 否 | 舒适区；可持续 |
| 3 | ≈ 6893 MiB (6.73 GiB) | ≈ 2370 MiB | ≈ 1.67 GiB | 否 | 临界：常压到 available<2GiB；短时可，须带 shed |
| 4 | ≈ 8739 MiB (8.53 GiB) | ≈ 2345 MiB | ≈ 1.67 GiB | 否 | **不可持续**：触发安全策略 TERM 最新一份 fm_eval |

**安全动作（已执行）**
- 规则：`available` 持续 <2 GiB 或 OOM → 杀掉**最新**多余 `fm_eval`，不硬顶。
- 2026-09-04T01:29:05Z：N=4 / avail≈1.68 GiB → `TERM` pid 498299（gen0_peer1）；shed 后 N=3 / avail≈3.75 GiB。
- dmesg：**无 OOM**（本窗口）。

**推荐最大并发 TimesFM / fm_eval 负载**
- **生产 / 长跑：N=2**（available 余量充足）。
- **容量试跑短时：N=3** 可接受，但必须保留 auto-shed（available<2GiB 时降级）。
- **N=4：不推荐**（实测立即触碰 <2GiB 红线）。


### Hard caps (2026-09-04；总管 retune — 勿用紧 RLIMIT_AS)

生产/长跑硬顶（落码；**不以紧 RLIMIT_AS 为主** — TimesFM safetensors mmap 需要 VAS≫RSS）：
1. **全局并发**：`scripts/mem_guard.py` flock 最多 **2** 槽（`data/cache/eval_slots.lock`）；`MemAvailable < 2 GiB` **拒绝启动**。
2. **RSS shed**：`rss_shed_once` / `check_and_shed` / `rss_shed_watch` — 单进程 RSS > ~**3.5 GiB** 或 `MemAvailable < 2 GiB` 时对匹配进程（`fm_eval|batch_runner|eval_wrapper|aligned_slow_loop|HourlyModel`）发 **TERM**；日志 → `data/cache/capacity_actions.log`（及 e2e 目录副本）。
3. **cgroup（若启用）**：优先 `memory.max` / `memory.high`（物理），不要单独靠 `RLIMIT_AS`。
4. **RLIMIT_AS**：可选，**默认 OFF**（`apply_limit=False`）。旧「默认 3.5GiB AS / slow_loop 强制 10GiB AS」路径已撤回。
5. **praxist 挂钩（强制，不靠 prompt）**：`scripts/praxist_mem_guard_hook.py` monkeypatch `protected_pids.launch_command`（subprocess.run / Popen 两路径）；经 `scripts/install_praxist_mem_guard_hook.py` 写入 `.praxist-venv` / `~/.praxist-venv` 的 `zz_fm_mem_guard.pth` + loader，使 peer Bash/batch_runner/fm_eval 启动前必走 flock+MemAvailable+RSS shed。`PRAXIST_MAX_PARALLEL_RUNS_PER_PEER` 仅为 per-peer；**GLOBAL≤2 由 flock 保证**。
6. `aligned_slow_loop.py`：仅 `apply_mem_guard(apply_limit=False)`（slot+MemAvailable）；候选之间轻量 `check_and_shed` + `self_rss_ok`。
7. `task_FM/task.yaml` → `compute_budget.max_concurrent_evals: 2`。
8. 依据 §4b：N=4 合计峰值 ≈ **8.53 GiB**（batch_runner / fm_eval 并行压测）不可持续；N=2 为舒适区。**e2e round complete**（fast + harvest + slow）。

**日志**
- 样本 TSV：`docs/superpowers/reports/e2e_20260904/run_084806/capacity_samples.tsv`
- 动作日志：`data/cache/capacity_actions.log`；e2e：`.../capacity_actions.log`
- 峰值 JSON：`.../capacity_peaks.json`
- 并行采样原文：`.../capacity_parallel_timesfm.txt`


## 5. 文档维护


更新本报告时同步修订：
- `docs/praxist_integration_plan.md` §资源适配
- `docs/runbook_praxist_three_loop.md` 项目根/路径表
- `docs/runbook.md` 环境表
- [x] `AGENTS.md` / `CLAUDE.md` / peer prompts 环境配置（已改为 box 路径；旧 `D:/FlyBuddy` 示例已清除）
