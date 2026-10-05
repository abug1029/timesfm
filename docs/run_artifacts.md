# 运行产物生命周期（run_artifacts）

> **范围**：仅管辖 `task_FM/experiments/run_*/` 下的 Praxist 运行产物。
> **不管辖**：`task_FM/config/` 与 `data/cache/` 下的真相源文件（见 §2），也不管辖 `docs/`（归档判据见 [archive/README.md](./archive/README.md)）。
>
> 最后核实：2026-10-05。所有数字为实测，非估计。

---

## 1. 为什么需要这份文档

`task_FM/experiments/` 是 supervisor 每次循环写出的 run 目录。2026-10-05 采样：

| 指标 | 实测值（**活系统，会增长**） |
|------|-------|
| run 目录数 | **213**（采样时；每轮循环 +1） |
| `.md` 文件数 | **9,708** |
| 目录总体积 | **1.6 GB** |
| 仓库总体积 | 5.1 GB（run 产物占 **~31%**） |
| 单 run 文件数 | 约 200–500 |

> ⚠️ **本文档不钉快照数字**——监督环每轮循环新增一个 run，任何写死的计数都会腐烂。
> 实时数量：`ls -d task_FM/experiments/run_* | wc -l`；体积：`du -sh task_FM/experiments/`。

**在此之前没有任何文档说明这些文件的分类、保留策略与清理流程**。唯一的线索是 `scripts/cleanup_experiments.sh` 里的代码常量——分类逻辑藏在代码里而不是文档里。本文档把那份隐含契约显式化。

---

## 2. 真相源不在本策略管辖范围内

三个机器真相源位于 `experiments/` **之外**，清理脚本不会碰它们：

| 文件 | git | 内容 | 被代码引用 |
|------|:---:|------|-----------|
| `task_FM/config/aligned_verdicts.jsonl` | ❌ 未追踪 | 唯一裁决注册表，**仅慢环可写** | 27 处 |
| `task_FM/config/symbol_status.json` | ✅ 已追踪（2 提交） | 品种级探索状态（`SYMBOL_DEAD` / `HOLD`） | 12 处 |
| `data/cache/supervisor_state.json` | ❌ 未追踪 | supervisor 机器状态、活计数 | 14 处 |

同目录另有三个**已追踪**的手写/半手写配置，改动会进 git 历史：
`covariate_pool.json`（9 提交）· `family_registry.jsonl`（1 提交）· `preregistry.jsonl`（1 提交）。

### 2.1 ⚠️ 裁决资产的备份编年史

`aligned_verdicts.jsonl` **不在 git 里**（`.gitignore:76`，规则由 commit `d236671` 加入，
该提交主目的是清理 `task.yaml` 泄露的 API key——忽略裁决是副作用，注释只写「runtime /
slow-loop writable」，从未说明理由）。但它**有三代备份，全部在同一块磁盘上**：

| 代 | 位置 | 行数 | 时间 | git |
|----|------|-----:|------|:---:|
| v1 原始 | `task_FM/config/aligned_verdicts.jsonl.bak_v1` | 9 | 2026-09-16 | ❌ |
| v2 封存 | `data/archive/fm_a_sealed_2026-09-24T1422/registry/` | 143 | 2026-09-24 | ❌ |
| v2 逐 cycle | `data/assets/verdicts/cycle_*_aligned_verdicts.jsonl` | 90 → 330 | 09-19 → 至今 | ❌ |

**覆盖是连续的**——v1 的 9 个 `variant_id` 全部包含在当前 registry 中，无丢失。

**但这是三重同盘单点**：`git clean -xdf` 会同时删除原件 + 174 个快照 + 封存包 + `.bak_v1`。
GitHub remote（6 个分支）与 `~/timesfm_backup_2026-09-28.bundle`（13 ref）**不含裁决历史**
——`git log --all -- task_FM/config/aligned_verdicts.jsonl` 返回空。

> **结论**：代码与文档备份健康（remote + bundle + 2 个 worktree），**唯独资产落在备份的洞里**。

### 2.2 快照编号不可跨运行段比较 ⚠️

`cycle_NNN` 编号在 supervisor 重启后**归 1**（`cycle_001` 在 09-19、09-27、09-28 各出现多次）。
所以**不能用编号判断快照缺口**——会误判成「缺 30 个 cycle」。实际覆盖无缺口，
判断连续性要看 `ls -t` 的时间顺序或 manifest.jsonl 的 `ts` 字段。

运行时隔离目录同样不入库、不备份：
- `task_FM/.runtime_guards/`（`.gitignore` 全忽略）
- `task_FM/.praxist/`（插件目录，可重建）
- `task_FM/peer_workspaces/`（在 `experiments/` 下，随之忽略）

---

## 3. 单个 run 的结构

以 `run_2026-10-05_11-10-44_primary_task_FM` 为例：

```
run_<YYYY-MM-DD>_<HH-MM-SS>_<tag>_task_FM/
├── results/          ← 核心产物：gen_*/gen*_peer*/proposals/*.json（策略提案）
├── gen_0/ gen_1/ gen_2/   ← 每代的 generation_results.json + peers/*/memory/
├── agendas/          ← pi_prompt_for_gen*.md + research_agenda_gen*.yaml
├── artifacts/        ← by_id/ 下提案产物快照
├── shared_store.db   ← sqlite（+wal/shm），跨 run 共享状态
├── graph/            ← graph_health.json / graph.html
├── .runtime_guards/  ← 每 peer 一个 python_site + guard_warnings.jsonl
├── peer_workspaces/  ← 每 peer 的临时工作区
├── task_project_manifest.json / run_summary.json / run_stop_report.json
└── frontier/ · variants/ · indexes/ · findings/ · shared_findings/ · logs/ · memory/
```

run 目录名自带时间戳，天然按时间可排序。

---

## 4. 产物分级

分类依据 `scripts/cleanup_experiments.sh` 的 `PURGEABLE_ITEMS`（脚本只删这一组，其余一律不碰）：

### 4.1 可清理（`PURGEABLE_ITEMS`，脚本唯一会动的集合）

| 项 | 性质 |
|----|------|
| `peer_workspaces/` | peer 临时工作区，可重建 |
| `trajectory.jsonl` | LLM 调用轨迹，体积大、可重建 |
| `graph/` | 知识图谱可视化产物 |
| `artifacts/` | 提案快照（内容在 `results/` 有正本） |
| `shared_store.db{,-shm,-wal}` | sqlite 状态库 |
| `gems/` | Praxist gems 状态 |

### 4.2 保护项（脚本绝不触碰）

`results/`（提案正本）· `gen_*/generation_results.json` · `logs/` · `shared_findings/` · `run_summary.json` · run 根下的 `*.json` 与 `task_spec.yaml`

### 4.3 未分级（脚本不删，但也没文档说明是否该留）

`agendas/` · `frontier/` · `variants/` · `indexes/` · `findings/` · `memory/` · `graph_health.json` · `tool_results/` · `baseline_cache/` · `credentials_redacted.json`

> 这组是 §7 的开放问题之一：分类只覆盖了「明确可删」和「明确保护」，中间地带靠脚本的保守默认（不删）兜底。

---

## 5. 保留与清理流程

### 5.1 现状参数

- `KEEP_LATEST=3`：最新 3 个 run **完整保留**，不动分毫
- 更早的 run 只删 §4.1 的可清理项
- 活跃 run 自动检测：脚本从 `/proc/*/cmdline` 里抓 `--run-dir` 参数，活跃 run 强制加入保留集

### 5.2 两段式执行

```bash
scripts/cleanup_experiments.sh            # dry-run（默认）：只打印计划，不动文件
scripts/cleanup_experiments.sh --apply    # 把可清理项移入 task_FM/experiments/_trash/
scripts/cleanup_experiments.sh --purge    # 真删 _trash/
```

`-h` 打印脚本头部注释作为帮助。

### 5.3 触发方式

**纯手动**。无 cron、无 CI、无磁盘阈值告警。这是刻意的（避免误删生产 run），但也意味着 1.6 GB 会持续增长直到有人想起来跑。

---

## 6. 与文档归档判据的关系

[archive/README.md](./archive/README.md) 的三条判据（一次性调查 / 已结案核验 / 已被取代且无引用）针对的是 **`.md` 文档**，不能直接套用到 run 产物——run 是机器生成的，不存在「被引用」语义。

run 的归档判据应当另立，本文档 §4 的分级 + §5.1 的保留窗口即当前事实上的判据。

---

## 7. 开放问题（尚无答案，需定规矩）

| # | 问题 | 状态 |
|---|------|------|
| 1 | §4.3 那组未分级产物是否需要显式归档？ | 待定 |
| 2 | 是否需要「金标 run」概念——哪些 run 因审计/复现需求必须永久保留并标记？ | 无机制 |
| 3 | `_trash/` 的 TTL 是多少？目前 `--purge` 完全手动 | 待定 |
| 4 | 磁盘配额上限与告警阈值？ | 无监控 |
| 5 | harvest 扫哪些 run 的历史范围？ | 已核实：supervisor 直接扫 `experiments/` 下的 run，无历史窗口限制 |
| 6 | **异地备份落在哪？**（§2.1 三重同盘单点） | **阻塞级，待决策** |
| 7 | 归档调用包在裸 `except` 里（`praxist_supervisor.py:2977`），supervisor 崩溃时该 cycle 静默失败 | 待修 |
| 8 | `git clean -xdf` 的危险是否需要在 `AGENTS.md` / `CLAUDE.md` 显著警告？ | 待定 |

### 已解决

- ~~归档是否覆盖 `family_registry` / `baseline_points`？~~
  → **2026-10-05 已补**：`scripts/praxist_assets_archive.py::archive_slow_cycle()` 现在每 cycle
  快照 `family_registry.jsonl` + 全部 `baseline_points_*.jsonl`（实测 32/32 字节一致），
  并写入 `manifest.jsonl` 与 timeline。
- ~~真相源三个文件是否都未追踪？~~
  → **勘误**：只有 `aligned_verdicts.jsonl` 和 `supervisor_state.json` 未追踪；
  `symbol_status.json` / `preregistry.jsonl` / `covariate_pool.json` / `family_registry.jsonl` **均已追踪**。

---

## 8. 变更记录

| 日期 | 内容 |
|------|------|
| 2026-10-05 | 初版。基线数据实测自 WSL `/home/abug/timesfm`，commit `ee01b56` |
| 2026-10-05 | 补 §2.1 裁决资产备份编年史（三代备份 + 同盘单点）、§2.2 快照编号跨运行段重置的坑；勘误真相源 git 状态；归档脚本补 `family_registry` + `baseline_points` |
