# 技术债清单

本文件登记已识别但暂未修复的技术债务。每条记录包含优先级、修复方案和前置条件，供后续重启时按序处理。

> **2026-11-19 全面复审重写**：吸收同日四路审计（代码静态审计 / docs 时效审计 / 研究路径审计 / 资产审计）
> 的全部结论。旧版单条目 E1-EXT-MISMATCH 经核实已消解（见 §RES-1）。执行载体：
> `docs/superpowers/plans/2026-11-19-tech-debt-closure-plan.md`（配套 spec 同日）。
> **口径**：P0=阻塞项 / P1=结构性 / P2=卫生与一致性 / P3=流程与裁定请求。
> 归档与遗留物的处置登记见 `docs/archive/README.md`（2026-11-19 批次，51 件）。

---

## A. 阻塞项（P0）

### TD-01 requirements.txt 缺失运行必需依赖，新环境按清单安装后核心模块 ImportError

**优先级**: P0（一切测试/执行的前置）
**发现日期**: 2026-11-19
**发现来源**: 代码静态审计（依赖契约维度）
**状态**: 待修复

### 问题描述

- `requirements.txt` 仅 6 项（timesfm/torch/pandas/pyarrow/numpy/PyYAML）
- 活代码实际需要而未声明：**scipy**（`cascade/statistical_tests.py:155`、`cascade/regime_features.py:15`、`cascade/covariate_analysis.py:14-15`、`cascade/vol_risk_filter.py:156`）、**scikit-learn**（`cascade/features.py:17-18`、`cascade/vol_risk_filter.py:34-35`、`cascade/covariate_analysis.py:242`）、**tqsdk**（`data/tqsdk_fetcher.py:117`）
- 测试侧另需 **pytest**、**jinja2**（`tests/test_praxist_evidence_ladder.py:11`）
- 后果：本机（WSL）`.venv` 缺失且无法按清单重建——这正是三环未能在本机拉起（2026-10-08/10-13 两次 pid 14 秒退，`data/cache/stop_report.json`）的直接原因之一

### 修复方案

1. requirements.txt 补 `scipy`、`scikit-learn`、`tqsdk`（带版本下界）；测试依赖以注释分节列出 pytest/jinja2
2. 修正头部注释：`pandas 'H' 频率别名` 说法已过时（代码已小写化 `freq='h'`/`'1h'`，见 `cascade/features.py:2371`、`cascade/data_validator.py:601`）；若防 pandas 3.x 行为漂移则补 `pandas<3` 上界，与注释一致
3. 核实 `pyarrow` 是否仍有活引用（审计未发现 import；LGBM parquet 缓存注释所述用途现存无引用）

### 影响范围 / 前置条件

- `requirements.txt`；WSL 环境重建（需 `apt install python3.12-venv`）
- 无前置（纯声明层），但 TD-02 重建 venv 依赖它

---

## B. 结构性（P1）

### TD-02 WSL 侧运行环境缺失（.venv / praxist / LLM env）

**优先级**: P1
**发现日期**: 2026-11-19
**发现来源**: 本机环境实查（无 .venv、无 praxist 二进制、stop_report 两次 unexpected_exit）
**状态**: 待修复（依赖 TD-01）

### 问题描述

- 文档约定 `source .venv/bin/activate`（docs/README.md「30 秒上手」），本机不存在
- 三环监督环在宿主机运行，本机仅作 git 枢纽 + 备份落盘点；一旦宿主机不可用，无热备运行点

### 修复方案

按 TD-01 修复后的 requirements 重建 `.venv`（torch 用 CPU index），跑全量测试确认可用；praxist 本体与 `.env.praxist` 的恢复属宿主裁定项（见 TD-16），不在本仓自动执行。

### 前置条件

- TD-01 完成；`python3.12-venv` 系统包安装

### TD-03 死代码闸门自引用漏洞：任何自带 usage 示例的脚本可自证被引用

**优先级**: P1（闸门失效 → 孤儿永不暴露）
**发现日期**: 2026-11-19
**发现来源**: 代码静态审计（实测 `pytest tests/test_no_dead_code.py` 3 passed，但 `scripts/calibrate_crack_ratio.py` 等跨文件引用=0，仅自身 docstring 含 usage）
**状态**: 待修复

### 问题描述

`tests/test_no_dead_code.py` 的 `_edge_sources`/`_referenced`（约 96-130 行）未排除「source 文件自身」——文件 docstring 里的用法示例（`python scripts/xxx.py`）被当作引用边，孤儿脚本全部靠自引用过闸。

### 修复方案

`_referenced` 排除 `(dname, stem)` 与 source 相同的边；新增测试 `test_gate_catches_self_reference`（构造自带 usage 的假孤儿，断言闸门能抓到）；重跑后把新暴露的孤儿补进 REVIEW_CANDIDATES（见 TD-04），不动文件本体。

### TD-04 孤儿脚本群：14 个 .py（3064 行）+ 11 个 .sh/.ps1（532 行）全仓零引用

**优先级**: P1
**发现日期**: 2026-11-19
**发现来源**: 代码静态审计（文件名+stem 双通道 grep）
**状态**: 待裁定（闸门修复后挂账）

### 问题描述

孤儿明细（审计报告 §维度2）：`calibrate_crack_ratio.py`、`check_baseline_progress.py`、`diracc_candidate_generator.py`、`diracc_optimizer.py`、`prediction_accuracy.py`（700 行，最大）、`p15_corr_precheck.py`、`review_underpowered_varieties.py`、`scan_vol_thr_smoke.py`、`toxic_variety_verdict.py`（与 `run_toxic_variety.ps1`→`toxic_variety_runner.py` 断链）、`resmoke_vol_thr_offline.py`、`verify_baseline_consistency.py`、`migrate_verdicts_tier.py`（仅测试 import）、`scripts/verify/check_slope_only.py`（仅 archive 引用）、`timesfm_hardcap_daemon.py`（**注意**：`scripts/mem_guard.py:359,421` 按进程名守护，疑由 cron/外部拉起，勿轻删）；.sh/.ps1：`archive_supervisor_logs.sh`、`cleanup_baseline_locks.sh`、`idle_hold_guard.sh`、`monitor_t1a.sh`、`patch_praxist_anthropic_env.sh`、`patch_praxist_env_propagation.sh`、`phase10_backtest_jd_i_p_remaining.sh`、`phase10_backtest_ss_ur.sh`、`run_baseline_remaining.sh`、`verify_t1a_baselines.sh`、`run_toxic_variety.ps1`。另 `tests/test_no_dead_code.py:73-80` 既有 REVIEW_CANDIDATES 6 项同样零引用。

### 修复方案

闸门修复（TD-03）后，将孤儿全量列入 REVIEW_CANDIDATES 并逐项附证据与建议（archive / keep / 待宿主确认外部调用）；**本仓不直接删除**——.sh/.ps1 可能被宿主 cron 引用，`timesfm_hardcap_daemon.py` 被 mem_guard 守护。归档动作待宿主逐项裁定。

### 前置条件

- TD-03；宿主确认 cron/外部调用面（TD-16 裁定请求）

### TD-05 `data/main_chain.py` 标注 DEPRECATED (2026-07-02) 但仍被生产日更链路调用

**优先级**: P1
**发现日期**: 2026-11-19
**发现来源**: 代码静态审计（DEPRECATED 声明现状）
**状态**: 待修复（需宿主确认方向）

### 问题描述

文件头+类+方法三层 DEPRECATED，文档五处同步；但 `build()` 仍被 `scripts/daily_update.py:29,137,319`、`data/cli.py:35,84`、`scripts/three_star_predict.py:60,104` 实例化调用，`daily_update.py:141` 对异常仅 WARN。「弃用」停留在文档层，调用图未拆。

### 修复方案（二选一，宿主裁定）

(a) 把 kline_1d→main_continuous_1d 同步逻辑收编进 `data/data_store.py` 正式化后摘除调用；(b) 撤销 DEPRECATED 标注、在 data/AGENTS.md 承认其为现役组件。禁止无裁定直接删调用。

### 前置条件

- 宿主裁定；`data/data_store.py` 属谨慎区（loop-constraints）

### TD-06 模型包模块名口径不一致（timesfm vs timesfm3）+ 空的 third_party 占位

**优先级**: P1
**发现日期**: 2026-11-19
**发现来源**: 代码静态审计（依赖契约维度；PyPI 实测 timesfm 3.0.2 存在、timesfm3 包不存在）
**状态**: 待修复（venv 重建后按实测统一）

### 问题描述

- 活代码 `import timesfm3`（`cascade/daily_model.py:15`、`cascade/hourly_model.py:15`、`scripts/predict.py:253`、`scripts/ablation_context.py:16`）
- DEPRECATED 脚本 `import timesfm`（`scripts/backtest_1h.py:31`、`scripts/batch_backtest.py:24`）
- requirements 只声明 `timesfm>=3.0.0`；`third_party/timesfm-3.0-official/` 为**空目录**，全仓无路径引用

### 修复方案

venv 重建（TD-02）时实测：若 `pip install timesfm` 提供 `timesfm3` 模块则统一为 timesfm3 并修两个 DEPRECATED 脚本的旧名导入；若不提供，则恢复旧 venv 的安装来源（疑为源码安装，third_party 空目录需填充或删除）。`cascade/daily_model.py`/`hourly_model.py` 属 loop-constraints 禁改路径，其 import 行如需变更须人工确认。

---

## C. 卫生与一致性（P2）

### TD-07 技术债登记册滞后：E1-EXT-MISMATCH 条目所假设的错配实际不存在

**优先级**: P2
**发现日期**: 2026-11-19
**状态**: **已消解（本重写处理）**——见 §RES-1；`l1_economic_verdict.py:121` 自初始提交即原子双写 `.json` sidecar，`build_knowledge_base.py:23` 读的正是 sidecar。

### TD-08 scripts/AGENTS.md 引用不存在的 `_kill_cov_gap.ps1`

**优先级**: P2
**发现来源**: 代码静态审计
**状态**: 待修复（删除该行或补回脚本，倾向删行——脚本无历史可考）

### TD-09 sup_evidence.py 稳定性指标为占位硬编码 0

**优先级**: P2
**位置**: `scripts/sup_evidence.py:144-145`（`n_validated_multi_seed = 0  # TODO` / `decay_below_threshold = 0  # TODO`）
**状态**: 待修复——实现多 seed/decay 追踪，或把这两个指标从证据阶梯输出显式移除。与 `docs/superpowers/specs/2026-10-02-phase3-multiseed-decay-todo.md`（现行约束：不发明通过线）对齐后择一。

### TD-10 指标计算三处重复实现（RSI×3 / ATR×2 / VWAP×2）

**优先级**: P2
**位置**: RSI：`data/indicator_calculator.py:84` vs `cascade/features.py:182,362` vs `scripts/backtest_vol_gating.py:43`(DEPRECATED)；ATR：`data/indicator_calculator.py:119` vs `cascade/features.py:54`；VWAP 偏离：`cascade/features.py:901` vs `scripts/p15_corr_precheck.py:66`
**状态**: 待修复——声明 `cascade/features.py` 为唯一指标权威（注意其属禁改路径，声明性文档可写，代码改动需人工确认）；`data/` 与一次性诊断脚本改为导入复用

### TD-11 `sys.path.insert` 手工路径 hack 共 222 处（scripts 81 / tests 141）

**优先级**: P2
**状态**: 待修复——长期方案 pyproject + `pip install -e .` 或 conftest.py 单点注入；涉及面大，单列一批处理，不阻塞其他项

### TD-12 过期 Windows 路径硬编码（`D:\FlyBuddy\...` / `D:/FlyBuddy/fm_a`）

**优先级**: P2
**位置**: `scripts/run_toxic_variety.ps1:3-5`、`scripts/phase10_backtest_jd_i_p.sh:7`、`scripts/phase10_backtest_ss_ur.sh:7`、`scripts/phase4d_calendar_matrix.sh:8`
**状态**: 待裁定——与 TD-04 孤儿裁定合并处理（phase10 系列本身在孤儿名单内）

### TD-13 `.deprecated` 后缀文件滞留工作区

**优先级**: P2
**位置**: `scripts/covariate_scan.py.deprecated_20260804`、`data/akshare_fetcher.py.deprecated`（akshare 全仓零活引用）
**状态**: 待修复——git mv 至 `scripts/archive/`、`data/archive/`（文件级移动，无 import 依赖）

### TD-14 cascade 性能债 TODO 悬置（numba JIT）

**优先级**: P2
**位置**: `cascade/features.py:2090,2222`（W3 TODO：limit 增至 1000+ 或批量全品种时加 @numba.jit）
**状态**: 挂账（批量全品种上线前处理；`features.py` 属禁改路径）

### TD-15 根目录 `pp` SQLite 与 `xreg_factors` 历史遗留表

**优先级**: P2
**位置**: `pp`（80KB，六表）、`scripts/three_star_predict.py:141`（"xreg_factors 表为历史遗留"）
**状态**: 待裁定——明确 pp 定位（种子库/样本库）并挂账 data/AGENTS.md；xreg_factors 停写后删表

### TD-16 悬置裁定请求（宿主窗口）

**优先级**: P2（对宿主为裁定请求清单）
**状态**: 待裁定，逐项：

| # | 事项 | 现状证据 | 建议 |
|---|------|----------|------|
| R-1 | **laya 优化线**（`reports/laya-optimization-spec-2026-11-07.md` v1.1 + `laya-implementation-plan-full.md` v1.1，均「待审批」；`.v2.md` 为其输入） | 全仓引用零命中、无 changelog、无执行痕迹；与已完成的 Jev→Laya 迁移（2026-10-14）是两回事 | 宿主审批或明确放弃；放弃则三件一并归档 |
| R-2 | **v23-retest-pending-ledger**（`plans/2026-10-08-v23-retest-pending-ledger.md`，10 条待复测组合） | 结案依赖的慢环确认裁决在 v4 预注册制下可能永不产出 | 宿主裁定：转入 v4 确认队列或关闭台账 |
| R-3 | **positive-ev 搜索 P5 enforce**（spec 在用，plan 头部 P3/P4 已发生、P5 未启动） | `scripts/praxist_goal.yaml:12` 现值 `search_policy: "shadow"` | 宿主决定是否从 shadow 升 enforce（关联 TD-09/TD-17 的三环重启） |
| R-4 | **peer-memory 回路 D1/D4**（spec 2026-10-03，README 标实施中） | D2/D3 已实施；D1 依赖 M3 窗口（已实施）、D4 依赖 M4（abandon 提案） | 纳入下轮实施批次（可与 TD-17 重启同批） |
| R-5 | **jd/sr max_points gap**（预注册 1199/986 vs aligned_max_points 600） | `2026-11-19-proposal-asset-management-audit.md` R4 | 宿主裁定提升上限至 800-1000 或设品种独立上限 |
| R-6 | **外部调用面确认**（TD-04 孤儿的 cron/cron-like 调用清单） | 本机无 crontab 可查（宿主侧） | 宿主提供 cron -l 清单后执行孤儿归档 |

### TD-17 宿主侧执行项（需停机窗口，本仓不可达）

**优先级**: P1（对宿主）
**状态**: 已有完整 spec/plan，待宿主执行：

1. **提案资产清洗 v4**（`docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md` + plan v4）：experiments 4.9GB / 683 run / 注册表 22 MISSING + 75 无 metadata。**清洗脚本 `scripts/cleanup_proposal_assets.py` 尚未实现**（25 项测试）——实现可在本仓无人值守完成，执行（停三环→清洗→重启）必须宿主停机窗口。
2. **监督环重启 + followup 验收链闭合**：`2026-11-19-proposal-followup-changelog.md` 自述改动已实施但「监督环没有重启」，验收未闭合；重启走 `docs/three_loop_restart_protocol.md`。
3. **长期清理策略**（asset audit 建议 3/4）：每 100 cycle 资产盘点自动化 + Laya prescreen 健康可观测（当前静默降级无告警）。

---

## D. 流程与文档债（P3）

### TD-18 `docs/BACKUP-MERGE-PROTOCOL.md` 文件损坏（合并事故）

**优先级**: P3
**发现来源**: 文档时效审计（字节级检查：第 7-9 行反引号内容缺失、受保护路径表路径列全空、第 20-296 行整份拼入 2026-11-02 低效诊断报告）
**状态**: 待修复——从 git 历史损坏前版本恢复正文（`.gitattributes` 的 protected-ours merge driver 是活机制，协议正文有存在价值），并收录进 docs/README.md 索引

### TD-19 `2026-11-03-jd-baseline-operator-note.md` 未并入 runbook

**优先级**: P3
**状态**: 待修复——其内容（baseline_eval_cutoffs / accept_baseline_file / finalize_baseline_write 收口路径）是现行运维语义，应并入 `docs/runbook_praxist_three_loop.md` 后将原件归档

### TD-20 changelog 自述与提交行为矛盾（流程债）

**优先级**: P3
**发现来源**: 2026-11-19 复审
**状态**: 挂账待宿主知悉——`2026-11-19-proposal-followup-changelog.md` 自述「本文件不提交、不推送」，但已被 `ff721f4`（chore: 提交监督环运行资产）连改动一并提交；且该批次注释提到 `50c848b` 曾被**仓库外历史重写**移出分支。风险：未验收改动以已提交形态存在、重写导致双谱系。建议：宿主补一条重写事件裁定记录；后续「不提交」类指令改用仓库内标记（如 STATE.md 挂账）而非仅文件自述。

---

## RES. 已消解登记（保留追溯）

### RES-1 E1-EXT-MISMATCH（旧登记册唯一条目，2026-10-09 登记为待修复）

**消解结论（2026-11-19 代码审计核实）**：任务假设的 `.md`/`.json` 错配**当前不成立**。`scripts/l1_economic_verdict.py:42-46` 默认 `--out ECONOMIC_VERDICT.md`，`:121` 同时原子写 `out.with_suffix(".json")` sidecar；`scripts/build_knowledge_base.py:23,249` 默认读 `ECONOMIC_VERDICT.json`——恰好消费 sidecar，契约自初始提交 `10dbeb3` 即一致。上游 `universe_eligibility.py:151` 默认输出与 `l1_economic_verdict.py:42` 的 `--eligibility` 默认一致。原条目的真实遗留是 E1 证据链问题本身（universe_eligibility.json 重建），已由 Q1 裁定 (c) 放弃（`docs/archive/superseded-2026-10/2026-10-08-d4-d5-n10-e1-q-rulings.md`）。

---

## 统计快照（2026-11-19）

| 类别 | 数量 |
|---|---|
| P0 阻塞 | 1（TD-01） |
| P1 结构 | 6（TD-02…TD-06 + TD-17 宿主执行） |
| P2 卫生/裁定 | 11（TD-07 已消解，TD-08…TD-16） |
| P3 流程/文档 | 3（TD-18…TD-20） |
| 归档批次 | 51 件（见 docs/archive/README.md 2026-11-19 节） |
| 代码侧锚点 | TODO 4 / DEPRECATED 活代码 6 文件 / 孤儿 25 项 / sys.path hack 222 处 / 重复实现 3 组 / 测试 176 文件 1927 函数 |
