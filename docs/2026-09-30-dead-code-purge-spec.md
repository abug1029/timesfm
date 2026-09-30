# 死代码清理 Spec（v2 修订稿）

> 日期: 2026-09-30。v1 → v2：吸收专家审核报告（`reports/2026-09-30-dead-code-spec-review.md`，P0×6 / P1×6）+ 宿主裁定 (d)(e) + 审核方自勘误（oi_gated_momentum 实为活代码）。
> 上游审计: `D:\FlyBuddy\fma-audit\2026-09-30-fma-overengineering-audit.md`（仅按 §1.2 勘误后引用）。
> 状态: **已批准执行**（裁定记录见 §0）。
> 不改三环行为、不改评估口径、不改 `.venv`；协议 v4 升级不在本 spec（属 v4 收口实施计划阶段 2）。

## 0. 裁定与勘误记录（v2 新增）

| # | 性质 | 内容 |
|---|---|---|
| (d) | 宿主裁定 2026-09-30 | **协议 v4 现在捆绑**：fu 随 v4 重生波直接补 v4 → v1 §4.3「先重生再归档」约束撤销，regen 三件套顺延至 2.9 |
| (e) | 宿主裁定 2026-09-30 | **A2 整簇退役**：10 脚本 + `cascade/lgbm_features.py` + 全部配套测试 `git mv` 归档；`module_freeze.md` CF-13 行加一行注记；dead 结论入记忆文档；不做重量级归档 README |
| (b) | **撤销**（审核方自勘误） | v1 采推荐「oi_gated_momentum 连测试归档」的前提**错误**：模块是活代码（`cascade/features.py:1118` 相对导入 + `:1518` dispatch + `scripts/extract_xreg.py:85-89` 生产注册 + `task_FM/config/covariate_pool.json:212` 在池）→ 模块、3 个测试（含审核漏计的 `test_oi_gated_momentum.py`）、spec 文档**全部保留**。审核报告 P1-3 作废（其 §八勘误） |
| (c) | 默认推荐执行 | `install_praxist_llm_env_hook.py` 保留 ACTIVE_CLI（`praxist_llm_env.md:69/:82` 文档化人工命令）→ 移出 v1 的 37 名单 |

## 1. 目的与范围

上游审计结论「82% 是死代码，可删 29,024 行」经 v1 勘误为 8,048 行（16.5%）；v2 复核后精确账：

**立即归档 50 文件 / 12,374 行 + 顺延（2.9）3 文件 / 153 行 = 12,527 行**（A2 整簇退役使总量较 v1 上修）。

完成标准（全部满足才算落地）：

1. 仓库内不存在「代码零引用 + 文档未记载为可运行命令 + 测试零引用」的 Python 文件（口径见 §2.0）。
2. `cascade/` 保留 **29** 个模块（v1 拟删 5 个中 4 个实为活码；仅 lgbm_features 经裁定 (e) 随 A2 簇退役）。
3. 全部既有测试通过（基线 **0 失败** —— 119e28c 已修复 v1 时点的 2 failed；v1 的「当前基线 0 失败」表述当时不实，见审核报告 P0-6）。
4. 三环存活验证顺延至实施计划 2.9（本 spec 各归档批次不动三环行为）。

### 1.1 复核方法（v2：四道筛 → 五道筛）

每条「死」断言必须全部通过且**无截断**复查：

1. 函数级 import —— **含 `from .X import` 相对导入形态**（oi_gated_momentum 教训：audit119 与 v1 spec 均漏检 `features.py:1118` 的相对导入）
2. importlib 字符串引用（`importlib.import_module` / `spec_from_file_location`）
3. subprocess / `.sh` 调用边（`set -euo pipefail` 语义下断边即断链）
4. tests 导入（测试文件枚举不得依赖命名模式——`test_lgbm_features.py` 不匹配 `test_a2*` 曾被漏计）
5. 泛用名撞车检查：`FEATURE_COLUMNS` 级别的常见名需精确到 import 语句级验证（regime 系 `EXPECTED_FEATURE_COLUMNS` 与 lgbm_features 同名不同源）

### 1.2 P0 勘误（v1 原表，审核已逐项核实为真）

| 编号 | 审计报告 | 复核后 | 差 |
|---|---|---|---|
| E-1 | 87 个孤儿脚本 / 22,592 行 | 36 个 / 7,229 行（v1 的 37 减 install hook） | 51 个文件被误判 |
| E-2 | 18 个孤儿 cascade 模块 / 6,588 行 | 1 个 / 371 行（仅 lgbm_features，经裁定 e） | 17 个模块被误判 |
| E-3 | 「可安全归档 103 文件 / 29,024 行」 | 53 文件 / 12,527 行（含顺延） | 净减 57% |
| E-4 | `cascade/features.py` 建议删 2,000 行 | **不删**，是活跃依赖 | 撤回该建议 |
| E-5 | 建议删 `praxist_supervisor.py` 的 TODO 占位符 | 那是**已知未完成目标**（Phase 3 数学上不可达的根因），删掉会让缺口变静默错值 | 不在本次范围 |

## 2. 核实结论

### 2.0 判死口径（v2 改写，吸收 P1-2）

v1 口径「脚本名在 scripts/cascade/tests/docs 中均不出现」被自家名单 4 个文件违反。v2 口径：

1. **五道筛零命中**（§1.1）；
2. **未被在用文档记载为可运行命令**（命令示例 = 保留；历史性提及/行数表 = 归档 + 文档同步标注）。

### 2.1 scripts/ 归档批次（36 文件 / 7,229 行，分级全名单落纸）

#### D1 证据保留（8 文件 / 802 行；其中 regen 双件顺延 2.9，立即 6 文件 / 690 行）

| 文件 | 行数 | 保留证据的理由 |
|---|---|---|
| enqueue_fast_loop_proposals.py | 103 | n=6 事件唯一证据（09-28 一次性运行产物） |
| audit_1h_daily_alignment.py | 324 | 1H/日线对齐审计证据 |
| regime_routing_poc.py | 136 | PoC 不留生产目录，但决策过程留档 |
| probe_timesfm3.py | 99 | TimesFM 3.0 升级探针 |
| regenerate_all_baselines.py | 86 | 基线重生（fu 随 v4 波后归档 → **顺延 2.9**） |
| regen_rb.py | 26 | rb 重生记录（**顺延 2.9**） |
| download_timesfm3_weights.py | 14 | 升级期脚手架 |
| clear_supervisor_pause.py | 14 | 死标志 clearer（`user_paused` 无读者；**归档必须连带 `restart_three_loop_clean.sh` 摘除第 [4/6] 步**，P0-4） |

#### D2 一次性调查（22 文件 / 5,691 行；结论均已写入报告/changelog）

diagnose_regime_supervised 667、train_regime_supervised 612、validate_vol_gating_hypothesis 585、validate_regime_clusters 376、fm_collect_analyze 352、si_quality_benchmark 316、strategy_changelog 260、analyze_backtest_performance 250、phase10_jd_i_p_verdict 243、backtest_tracker 237、validate_regime_classifier 226、verify_all_baselines 221、three_star_verify_runner 210、test_tqsdk_1h_depth 186、t2_ablation_report 181（结论在 `reports/2026-09-28-t2-ablation-table.md`）、a3_lasso_diagnostic 174、regime_detector 170、three_star_verify_critic 120、t1b_hand_calc_verification 99（结论在 `reports/2026-09-28-t1b-hand-calc-report.md`）、rebuild_universe_neutral_report 97、shadow_replay_30 88、audit_indicator_alignment 21。

#### D3 纯残留（6 文件 / 736 行）

scheme_migrator 187（迁移已完成）、prediction_calendar 165（一次性生成）、pull_history_1h 146（被生产数据路径取代；`runbook.md:33` 行数表同步删除）、apply_horizon_known_relabel 110（PR-C6 重标已完成）、query_accuracy 75（临时查询）、install_praxist_qwen_model_patterns 53（安装已完成）。

#### 名单外特记

- `install_praxist_llm_env_hook.py`（119 行）→ **ACTIVE_CLI 保留**（裁定 c）。
- `enqueue_fast_loop_proposals` 的 `three_loop_workflow.md:290` 提及 → 1.7 标注归档路径。
- `monitor_rb_regen.sh`（41 行，.sh 不在上述计数）→ **顺延 2.9**（引用 regen_rb，三件套同进退）。

### 2.2 cascade/ —— 归档 1 模块 / 371 行（v1: 5/700，v2 修正）

| 模块 | 行数 | v2 判定 | 证据 |
|---|---|---|---|
| baseline_paths.py | 13 | **保留（活）** | `evaluator.py:258` 函数级 import（每次基线加载必经）+ `generate_baseline_points.py:29` + `tests/test_nocov_baseline.py:8/15/20`（P0-1） |
| covariate_diagnostics.py | 81 | **保留（活）** | `hourly_model.py:315` 主预测路径调用（`# PR-B2`）—— v1「未实际调用」被证伪（P0-2） |
| experiment_fingerprint.py | 147 | **保留（活）** | `restart_readiness_check.py:39` importlib + `:96` check_phase7 调用并断言格式；W6.4 身份唯一家、阶段 2 接线目标（P0-3） |
| lgbm_features.py | 371 | **归档（裁定 e，非零引用）** | 导入者全部在 A2 簇内（4 a2 脚本 + 3 测试文件）；簇亡则引亡，簇外零依赖（regime 系 `EXPECTED_FEATURE_COLUMNS` 同名不同源，五道筛第 5 筛） |
| oi_gated_momentum.py | 88 | **保留（活）** | `features.py:1118` **相对导入** + `:1518` dispatch + `extract_xreg.py:85-89` 生产注册 + `covariate_pool.json:212` 在池 —— v1「零引用」与审核报告 P1-3 均错（自勘误，见 §0(b)） |

cascade 保留 **29** 个模块（含 v1 被误判「最大嫌疑」的 `features.py` 2,393、`evaluation_metrics.py` 632、`vol_risk_filter.py` 760、`neutral_ab_report.py` 959、`live_ledger.py` 553）。

### 2.3 A2 整簇退役（v2 新增，裁定 e）

| 组成 | 文件数 | 行数 |
|---|---|---|
| `scripts/a2_*.py`（p1: generate_report 160 / lgbm_baseline 404 / orchestrator 264 / restore_manifest 503 / runtime 559 / status 84 / worker 283；p2: generate_report 193 / orchestrator 266 / worker 316） | 10 | 3,032 |
| `cascade/lgbm_features.py` | 1 | 371 |
| tests: `test_a2_p1_baseline` 88 / `test_a2_p1_integrity` 1,186 / `test_a2_p1_runtime` 177 / `test_a2_p2_integrity` 259 / `test_lgbm_features` 144 | 5 | 1,854 |
| **合计** | **16** | **5,257** |

依据：CF-13（2026-08-08，ultragoal G003）0/5 GO **永久关闭**，`module_freeze.md` 载「代码保留作归档」—— `git mv` 即该决议的归档形式（裁定 e）。
簇外引用终验为零：regime 系为同名常量不同源；`test_d5_cutoff_fix.py:89/:100` 仅注释提及（自实现逻辑，不导入）→ 该测试保留，1.7 时 docstring 补归档路径注。

## 3. 非目标

- 40+1 个 ACTIVE_CLI 与 REF 文件全部保留（v2: + `install_praxist_llm_env_hook.py`）。
- 不精简 `praxist_supervisor.py`（2,825+ 行，在跑的三环主循环）。
- 不动 Phase 3 TODO 占位符（§1.2 E-5）。
- 不改 `aligned_verdicts.jsonl` / 协议指纹 / `pass_variants` 过滤链（v4 属实施计划阶段 2）。
- 不删 `.venv` / Praxist 发行源码。
- `module_freeze.md` CF-13 决议语义不改，仅加「已归档至 `<路径>`，决议不变」注记。

## 4. 设计

### 4.1 删除方式：`git mv` 归档，不 `rm`（v1 保留）

```
scripts/archive/2026-09-30-dead-code/     <- 36 个 D 批脚本（2.9 时 +regen 双件）
scripts/archive/2026-09-30-a2-retired/    <- 10 个 a2 脚本
cascade/archive/2026-09-30-a2-retired/    <- lgbm_features.py
tests/archive/2026-09-30-a2-retired/      <- 5 个测试文件
scripts/monitor_rb_regen.sh               -> 2.9 随三件套归档
docs/archive/dead-code-2026-09-30/README.md  <- 轻量归档说明
```

`git mv` 保留历史（`git log --follow` 可追溯）；归档目录被 pytest.ini `norecursedirs` 与检测测试双重排除。

### 4.2 分级归档汇总（v2 全名单见 §2.1/§2.3）

| 档 | 文件 | 行数 | README 处置 |
|---|---|---|---|
| D1 证据保留 | 8（立即 6） | 802（立即 690） | 每文件一行「为何保留」 |
| D2 一次性调查 | 22 | 5,691 | 每文件一行「结论落在哪」 |
| D3 纯残留 | 6 | 736 | 只列名 |
| D-A2 整簇退役 | 16 | 5,257 | 一段 CF-13 + 裁定 (e) 注记（不做重量级 README） |
| **合计** | **52（立即 50）** | **12,486（立即 12,374）** | |

### 4.3 fu 基线（v2：被裁定 (d) 取代）

v1 要求「先重生 fu (v3) 再归档 regen 脚本」。裁定 (d) 后 fu 随 **v4 重生波**直接补 v4 —— v1 的唯一执行顺序约束撤销，三件套（regenerate_all_baselines / regen_rb / monitor_rb_regen.sh）顺延 2.9。

### 4.4 归档 README（`docs/archive/dead-code-2026-09-30/README.md`）

保留 v1 表结构（文件/行数/档位/归档理由/判定证据/关联审计）；顶部写明上游审计 5 处勘误（§1.2）防复读；A2 段一段话（CF-13 + 裁定 e）。

### 4.5 文档同步（v2 扩充）

- `scripts/restart_three_loop_clean.sh`：**摘除第 [4/6] 步**（clear_supervisor_pause 调用）并重编号（1.4，代码改动）
- `docs/three_loop_restart_protocol.md`：同步移除该步骤
- `docs/runbook.md:33`：pull_history_1h 行删除
- `docs/three_loop_workflow.md:290`：enqueue 提及标注归档路径
- `docs/module_freeze.md`：CF-13 行加归档注记
- `cascade/AGENTS.md`：A2 标注更新（`test_a2_p1_baseline.py:84` 所引）
- `docs/AGENTS.md`、WSL 根 `AGENTS.md`、`D:\FlyBuddy\AGENTS.md` FM_a 行（1.7）
- agent 记忆：A2 dead 结论 + 基准数字

## 5. 测试要求（v2 重设计，P1-5 + 实证）

1. **检测测试重设计**（`tests/test_no_dead_code.py`）：**AST 导入图分析**替代名字 grep —— `ast.parse` 提取 import / from-import（**含相对导入**）+ importlib 字符串 + subprocess/.sh 调用边 + tests 导入，构建可达集；断言可达集 ∪ ACTIVE_CLI ∪ REF = 全集。归档目录排除；顺延件入 `TEMPORARY_ALLOWLIST`（2.9 释放）。
2. **新建 `pytest.ini`**：`testpaths = tests`，`norecursedirs` 含 `archive` / `third_party`。实证：2026-09-30 裸 `pytest` 递归收集 third_party 7 errors 中断（72.77s 白跑）。
3. **import 完整性**：保留模块全部可导入（`cascade.horizon_fill / hourly_model / features / evaluation_metrics / oi_gated_momentum` 等）。
4. **基线**：`pytest tests/ -q` = **1646 passed / 0 failed / 7 skipped / 1 xfailed**（119e28c 后实测）；A2 测试归档后总数相应下降，以「归档前 scoped 跑 + 归档后全量对照」验收。
5. **生产入口可运行**：`copilot.py --help` 与 `cascade_predict.py --help` 退出码 0。
6. **三环存活**：顺延至 2.9 重启验证。

## 6. Key Decisions

1. **不删，只归档。** `git mv` 保留审计证据链（v1 保留）。
2. **CLI 入口不是死代码。** 判死口径必须含「是否被文档化为人工命令」（v1 保留）。
3. **`features.py` 不动。** E-4 撤回（v1 保留）。
4. **TODO 占位符不是过度设计。**（v1 保留）
5. **CF-13「保留作归档」由 `git mv` 满足**；A2 整簇退役的依据是**裁决而非零引用** —— lgbm_features 有簇内引用，簇亡则引亡（v2，裁定 e）。
6. **相对导入是盲区**（v2 新增）：oi_gated_momentum 险些被错误归档——第五次同型错误，首次轮到审核方自身，被 0.3 修订前的执行边界终验捕获。
7. **同名常量不同源**（v2 新增）：判依赖必须到 import 语句级（`EXPECTED_FEATURE_COLUMNS` 教训）。

## 7. 开放问题（v2：全部关闭）

| 问题 | v2 结论 |
|---|---|
| oi_gated_momentum | **保留**（活代码；v1「有 spec 无实现/零引用」前提错误——实现存在且在产） |
| covariate_diagnostics | **保留**（`hourly_model.py:315` 实调已验证） |
| experiment_fingerprint | **保留**（重启闸门依赖 + W6.4 接线目标） |
| D1 的 8 个脚本 | 全保留 D1 档（裁定 e 只涉及 A2 簇） |

## 8. PR 切分（对齐实施计划阶段 1）

| 顺序 | 内容 | 规模 | 依赖 |
|---|---|---|---|
| 1.1 | D3 归档 | 6 文件 / 736 行 | — |
| 1.2 | D2 归档 | 22 文件 / 5,691 行 | — |
| 1.3 | D1 归档 | 6 文件 / 690 行 | — |
| 1.4 | clear_supervisor_pause + `.sh` 删步 | 1 文件 + 1 处编辑 | — |
| 1.5 | A2 整簇退役 + CF-13 注记 | 16 文件 / 5,257 行 | — |
| 1.6 | 检测测试（AST 版）+ pytest.ini + allowlist | 2 新文件 | 1.1–1.5 |
| 1.7 | 文档同步 | 见 §4.5 | 1.1–1.6 |
| 2.9 | regen 三件套归档 + allowlist 释放 | 3 文件 / 153 行 | v4 重生波完成 |

每个 PR 独立可回滚；1.1–1.5 只做 `git mv`（唯 1.4 含 `.sh` 编辑与 1.5 含 module_freeze 注记）。
