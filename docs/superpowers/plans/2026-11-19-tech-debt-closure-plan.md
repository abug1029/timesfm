# 技术债收口实施计划（2026-11-19 批次）

> **状态**：待宿主审批（批准后进入无人值守执行）  
> **spec**：`docs/superpowers/specs/2026-11-19-tech-debt-closure-spec.md`  
> **登记册**：`docs/superpowers/plans/tech-debt-register.md`（TD-01…TD-20）  
> **执行环境**：WSL Ubuntu-24.04 `/root/timesfm`（root，Python 3.12.3，磁盘余 940G）  
> **执行模式**：无人值守；单任务重试 ≤3 次，超限停并上报；每 Task 一个 commit  
> **冻结路径**：`config/prediction_scheme.py`、`cascade/features.py`、`cascade/daily_model.py`、`cascade/hourly_model.py`、`data/config.py`、`aligned_verdicts.jsonl`、`.env*` —— 全部不触

---

## Goal（成功条件）

```yaml
goal: tech_debt_closure_20261119
success_condition: all_tasks_pass_phase1   # T1-T9 验收全绿
budget: { task_retries: 3, push: after_report }
```

---

## 执行日志

（执行时逐 Task 回填：时间 / commit / 验收输出摘要 / 偏差）

| Task | 状态 | commit | 验收摘要 |
|---|---|---|---|
| T1 | 待执行 | — | — |
| T2 | 待执行 | — | — |
| T3 | 待执行 | — | — |
| T4 | 待执行 | — | — |
| T5 | 待执行 | — | — |
| T6 | 待执行 | — | — |
| T7 | 待执行 | — | — |
| T8 | 待执行 | — | — |
| T9 | 待执行 | — | — |

---

## T1 依赖契约修复（TD-01，P0）

**动作**：
1. 重写 `requirements.txt`：
   ```
   # timesFM_fu 关键依赖锁版（2026-11-19 复审修正）
   # - pandas 建议 <3：防 3.x 行为漂移（代码已用小写 freq，不再依赖 'H' 别名）
   # - torch：WSL 本机无 GPU，装 CPU 版（pip install torch --index-url https://download.pytorch.org/whl/cpu）
   timesfm>=3.0.0
   torch>=2.0
   pandas>=2.0,<3
   numpy<3
   scipy>=1.11
   scikit-learn>=1.3
   pyarrow>=14        # 2026-11-19 复审：活代码未见 import；如 T3 证实零依赖可移除（登记后处置）
   PyYAML>=6.0.3
   tqsdk>=3.5
   # --- 测试依赖（dev）---
   pytest>=7
   jinja2>=3.1
   ```
   （最终以实测可用版本集为准；tqsdk 如与 py3.12 有兼容问题按实测下界登记，安装失败重试 ≤3 后转 P2 降级：requirements 记录 + venv 无 tqsdk，数据采集功能标记宿主侧）
2. `pyarrow` 依赖核实：`grep -r "import pyarrow\|from pyarrow" --include="*.py"` 活代码命中数 → 结果写执行日志

**验收**：文件写就 + pyarrow 核实结论入日志。  
**commit**: `deps: fix requirements contract (scipy/sklearn/tqsdk/pytest/jinja2), correct stale header`

## T2 venv 重建（TD-02，P1）

**动作**：
1. `apt-get install -y python3.12-venv`（幂等；失败重试 ≤3）
2. `python3 -m venv .venv && .venv/bin/pip install -U pip`
3. `.venv/bin/pip install -r requirements.txt`；torch 单独走 CPU index（`--index-url https://download.pytorch.org/whl/cpu`）
4. 烟测：`.venv/bin/python -c "import numpy, pandas, scipy, sklearn, yaml, pyarrow"`；torch/timesfm/tqsdk 单独 try-import 并记录结果（timesfm 的模块名口径见 TD-06，只记录不修改代码）
5. praxist 本体安装**不做**（属宿主裁定 TD-16）

**验收**：烟测输出入日志；失败项如实记录（timesfm/tqsdk 允许失败并转登记）。  
**commit**: 环境产物不入库（.venv 已在 .gitignore）——本 Task 无 commit，仅日志

## T3 全量测试基线（TD-02 验收）

**动作**：`.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`（norecursedirs 已排除 archive），超时 30 分钟；记录 pass/fail/skip/error。若因 tqsdk/timesfm 缺失出现 ImportError 类失败，与 TD-01/TD-06 关联记录，不视为回归。

**验收**：基线表入执行日志，与 2026-10-03 基准（1557 passed / 0 failed / 6 skipped / 1 xfailed）对照差异清单。  
**commit**: 无（日志）；若基线异常 → 停，上报

## T4 死代码闸门修复（TD-03，P1）

**动作**：
1. `tests/test_no_dead_code.py`：`_referenced` 排除与 source 相同的 `(dname, stem)` 自引用边
2. 新增 `test_gate_catches_self_reference`：tmp 下构造自带 usage docstring 的假孤儿 + 引用文件，断言修复后能判孤儿
3. 重跑闸门测试；将新暴露的孤儿并入 T5 名单

**验收**：新测试绿 + 原闸门测试绿（名单更新后）。  
**commit**: `fix: dead-code gate excludes self-reference edges + regression test`

## T5 孤儿挂账（TD-04，P1）

**动作**：REVIEW_CANDIDATES 由 6 项扩至全量孤儿（T4 重跑后名单为准，预期 ~25 项）；每项行内注释：行数 / 唯一引用情况 / 建议动作（archive / keep / 待宿主 R-6）。**不移动、不删除任何文件**。`timesfm_hardcap_daemon.py`、`migrate_verdicts_tier.py`（测试专用 import）、mem_guard 守护对象按证据标注特殊处置。

**验收**：闸门测试绿；名单与审计证据一致。  
**commit**: `chore: register full orphan script inventory in dead-code gate (no deletions)`

## T6 卫生批（TD-08 / TD-13，P2）

**动作**：
1. `scripts/AGENTS.md`：删除 `_kill_cov_gap.ps1` 悬空引用行（或改为「已移除」注记）
2. `git mv scripts/covariate_scan.py.deprecated_20260804 scripts/archive/`；`git mv data/akshare_fetcher.py.deprecated data/archive/`（目录不存在则 mkdir；git mv 后 grep 确认无引用破坏）
3. TD-12 的 4 个硬编码路径文件已入 T5 名单，本 Task 不动

**验收**：`grep -r "_kill_cov_gap" scripts/` 为零（或仅历史注记）；`find . -name "*.deprecated*"` 为零。  
**commit**: `chore: hygiene - drop dangling ref, archive .deprecated files`

## T7 文档债批（TD-18 / TD-19，P3）

**动作**：
1. **BACKUP-MERGE-PROTOCOL.md 恢复**：`git log --follow -p docs/BACKUP-MERGE-PROTOCOL.md` 找最近完好版本作底稿；对照 `.gitattributes`（protected-ours driver）校对受保护路径表；剔除 2026-11-02 诊断报告拼接段；重写后在 `docs/README.md` 索引收录
2. **jd 运维注记并入 runbook**：`docs/runbook_praxist_three_loop.md` 增「基线收口路径」小节（内容取自 `2026-11-03-jd-baseline-operator-note.md`：baseline_eval_cutoffs / accept_baseline_file / finalize_baseline_write），注记原件 `git mv` 入 `docs/archive/superseded-2026-11/`，README 归档登记 + 原 changelog 引用回填检查
3. **docs/README.md 索引修正**：`2026-09-30-dead-code-purge-spec.md` 状态行更新为「已执行完（2026-10 实施）」

**验收**：恢复后的协议文件与 .gitattributes 一致；runbook 新节存在；引用 grep 无断链。  
**commit**: `docs: restore BACKUP-MERGE-PROTOCOL, merge jd operator note into runbook, index fixes`

## T8 cleanup_proposal_assets.py 实现（TD-17.1 实现半，P1）

**动作**（合同=`2026-11-19-proposal-asset-cleanup-spec.md` v4，逐节实现）：
1. 脚本骨架：`--session` / `--phases P0 P1 P2 P3` / `--dry-run` / `--rollback <session_id>` / `--p1-list-only`
2. 硬门禁 5 项核实（`VerificationResults`，写 manifest.verification）
3. P0 `compute_archive_set`（mtime ∪ run_id 并集、5 保护条件、软目标溢出记录）
4. P1 四条件删除 + NUL 安全（`--null` tar + `xargs -0`）
5. P2 TIMEOUT_NO_EVAL 占位 + 统计隔离守卫
6. P3 prescreen metadata 回填（时区假设显式化、unknown=0 硬断言）
7. 增量 manifest + 单份 before-cleanup.jsonl + 原子写（tempfile+fsync+os.replace）+ 回滚（completed/in_progress 两档）
8. `task_FM/archive/.gitignore`（忽略全部内容）
9. 测试 `tests/test_cleanup_proposal_assets.py`：spec v4 §九 25 项全量，**全部基于 tmp fixture**（不读真实 experiments/；本机无该目录，脚本对缺失路径安全退出）
10. 烟测：`--dry-run` 于空 fixture 目录

**验收**：25 测试全绿 + dry-run 烟测绿。  
**commit**: `feat: implement cleanup_proposal_assets.py per asset-cleanup spec v4 (25 tests, execution stays host-side)`

## T9 宿主执行包 + 裁定请求（TD-16 / TD-17）

**动作**：
1. 新建 `docs/superpowers/plans/2026-11-19-host-side-execution-pack.md`：
   - 资产清洗执行步骤（停三环分类检查 → dry-run → 实跑 → 静态验收 → 重启 → 运行态验收；命令引自 spec v4 §六）
   - 监督环重启 + followup 验收闭合步骤（three_loop_restart_protocol 链接）
   - 长期机制两条（每 100 cycle 盘点 / Laya 健康告警）
2. 新建 `docs/superpowers/plans/2026-11-19-host-rulings-request.md`：R-1…R-6 裁定请求（laya 线 / v23-retest 台账 / positive-ev P5 / peer-memory D1+D4 / jd-sr max_points / cron 清单）+ TD-05 main_chain 方向 + TD-06 import 统一确认，每项带证据链接与建议
3. `docs/README.md` 索引补两条目；`tech-debt-register.md` 状态列更新（已执行项 → 完成）

**验收**：两文档存在、被索引、无断链。  
**commit**: `docs: host-side execution pack + rulings request (R-1..R-6)`

---

## 收尾

1. 引用完整性复审（全仓在用文档 grep 断链扫描）
2. `git log --oneline` 本批次审阅；**push origin master**（本计划被批准即视为已告知）
3. 向宿主/用户交付：执行日志汇总 + host-side execution pack + rulings request

## 已知风险与降级

| 风险 | 降级 |
|---|---|
| tqsdk 在 py3.12 装不上 | requirements 记录 + venv 缺装，数据采集侧标记宿主；不阻塞其他 Task |
| timesfm 包不提供 timesfm3 模块 | 如实登记 TD-06，不改冻结路径代码；测试基线按 ImportError 分类记录 |
| 全量测试出现与依赖无关的新失败 | 停止后续 Task，保留现场上报（不热修） |
| pytest 全量超 30 分钟 | 分片跑（tests/ 按目录），记录分片基线 |
