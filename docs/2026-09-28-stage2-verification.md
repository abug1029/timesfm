# 阶段 2 出口核验报告 (2026-09-28)

**Commit 范围:** `51088bd` (Stage 1 基线) .. `9d121be` (HEAD)
**测试:** 247 PASS, 1 xfailed（回归）+ 65 PASS（PR-B6 套件）
**评审:** 每个 PR 均经 `oh-my-claudecode:code-reviewer` (opus) 独立评审并修复全部 CRITICAL/HIGH

## 0. Stage 2 意图（摘自计划）

Stage 1 闭合三项硬门（因果对齐、比较对象、可追溯性）。Stage 2 是 L2 诊断层，目标是把"协变量未利用"从推断变成可验证事实，并为后续确认层 (L3) 和预注册层 (L4) 奠基。

**交付清单（5 个 PR）:**
- PR-B1: 指纹系统（实验身份 + 去重）
- PR-B2: 协变量诊断字段（有效性 + 零填充 fail-loud）
- PR-B3: `xreg_fallback` 贯通评估路径
- PR-B5: 三路消融（区分内容效应与通道效应）
- PR-B6: 提案质量门（板块/协变量/历史表现过滤）

**未实施:** PR-B4（dir_acc 口径变更影响面过大，留待阶段 3）

## 1. 实施清单与提交

| PR | Commits | 新增文件 | 修改文件 | 测试数 |
|----|---------|---------|---------|-------|
| B1 | `20245da` | `cascade/fingerprint_lib.py`, 2 测试文件 | `scripts/registry_lib.py`, `task_FM/evaluations/fm_eval/evaluator.py` | 43 |
| B2 | `4e0b598` | `cascade/covariate_diagnostics.py`, 1 测试文件 | `cascade/hourly_model.py` | 12 |
| B3 | `53ae61d` | — | `scripts/monthly_backtest.py`, `scripts/registry_lib.py`, `task_FM/evaluations/fm_eval/evaluator.py` | (含在 B2/B5 回归) |
| B5 | `2852623`, `170947c`, `e171e45` | `cascade/ablation.py`, `config/ablation_audit_config.json`, 2 测试文件 | `cascade/hourly_model.py`, `scripts/monthly_backtest.py` | 46 |
| B6 | `2fed5b9`, `9d121be` | 3 测试文件 | `scripts/praxist_supervisor.py` | 65 |

**测试总计:** 247 passed (回归) + 65 passed (PR-B6 套件) = 312 passed，1 xfailed (既有预期失败)

## 2. 专家评审对照

### PR-B5 评审 (commit `e171e45` 修复)

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| C1 | CRITICAL | resume 自我中毒：错误行不带 `ablation_mode`，读取侧归一为 full，非 full 运行出过一个点级错误就永远无法 resume | (1) 错误行写入补 `ablation_mode` (2) 读取侧仅对非错误行计数模式 |
| H1 | HIGH | baseline 模式 `covariates_used=True`，registry 元数据撒谎 | 提取 `_covariates_used()` 显式排除 baseline |
| H2 | HIGH | 审计集零覆盖 energy_chem 板块 | 加入 `fu`，新增板块覆盖断言 |
| M1 | MEDIUM | `rng.permutation` 多维语义含糊 | 显式 axis 0 写法 + docstring 注明差异 |
| L1 | LOW | arg 错误 exit 0，自动化调度误判成功 | 改 `sys.exit(2)` |
| L2 | LOW | `--ablation-mode` 无值静默忽略 | 报错退出 |
| L4 | LOW | baseline 仍 fetch feedstock (白付 I/O) | 提前返回块上移到 feedstock 抓取前 |
| N1 | NIT | `last_covariate_input` 未初始化 (PR-B2 遗留) | 在 `__init__` 初始化 |
| N2 | NIT | daily_slope 被 content 模式同样打乱未说明 | 加注释说明是有意为之 |

**未修复:** L3 (resume 检查在模型加载之后)、N3 (seed 硬编码 42)

### PR-B6 评审 (commit `9d121be` 修复)

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| C1 | CRITICAL | **板块过滤器导致 100% 饿死** — 生产快照 434/434 被拦，与 2026-09-24 饿死同构 | circuit-breaker：仅当板块**全集**（sector_map 定义）失败才拦 |
| H1 | HIGH | `_verdict_sort_key` ties 时取最旧裁决 | `>` 改 `>=`，ties 时取 jsonl 顺序最后的（最新） |
| H2 | HIGH | `cov_recent_fail` -20 项近死代码 | 已文档化，窗口语义测试锁定（`test_stale_pass_does_not_exempt_covariate_filter`） |
| M1 | MEDIUM | 双重计数键名漂移 | `quality_rejected` 对齐为 `quality_below_threshold` |
| L1 | LOW | 缺板块空裁决/单品种裁决测试 | 新增 `test_sector_with_no_verdicts_never_blocked` 和 `test_only_one_symbol_in_sector_with_verdict` |

**PR-B6 复评 (commit `9d121be` 后):** APPROVE。生产数据实测 sector 拦截从 100% → 0%，协变量/质量门拦截 36.9%，通过率 63.1%。

## 3. 关键设计决策

### 3.1 v2 schema 限制下的 PR-B6 评分口径

计划中 `_proposal_quality_gate` 的 PF/IC 项与 sector_filter 的 `ev` 项无法实现：
生产 registry 143 条裁决全为 `fm.aligned_verdict.v2`，不含 `pf`/`ev`/`ic`
(该三字段仅存在于已退役的 v1 schema)。

**决策:** 评分与过滤一律基于 v2 可观测字段 (`gate_pass` / `decided_at` / `cov_override` / `symbol`)。评分项：
- `+5` 该品种有过成功协变量
- `+3` 组合未测过 (新颖性)
- `+3` 机制论证完整
- `+10 * prescreen plausibility`
- `-20` 该协变量在其他品种最近 3 次全失败
- `-15` 该品种最近 5 次全失败

### 3.2 PR-B5 与 PR-B6 交互: resume 模式隔离

PR-B5 的 `ablation_mode` 与 PR-B3 的 `--resume` 机制交互：
- 不同消融模式不得共享同一 checkpoint（否则点级去重会跨模式复用）
- `_resume_mode_conflict()` 守卫检测模式不一致，`sys.exit(2)`
- 错误行写入也带 `ablation_mode`，避免读取侧归一化误判

### 3.3 PR-B6 板块过滤器 circuit-breaker

**问题:** 原计划 `SECTOR_BLOCK_MIN_FAILED = 3` 在生产快照上触发三板块全拦 → 100% 饿死。

**修复:** 改为 `n_failed >= sector_size` (sector_map 定义的全集)。语义：
- 部分失败不拦 (agri 9/10 失败 → 放行)
- 完全死亡的板块才拦 (black_metals 4/4 失败 → 拦截)
- 冷启动不拦 (无裁决时 `n_failed=0`)
- 未观察到的品种不参与失败计数

**风险:** 该语义无法预警"板块部分退化" (如 agri 4/4 已观察全死但 6/10 未观察)。
未来增强：当 `n_failed >= sector_size * 0.5` 时打 WARN 日志。当前不实现，因为 filter 是二元 (block/pass)，不是信号。

## 4. 测试覆盖矩阵

| 模块 | 测试文件 | 测试数 | 覆盖要点 |
|------|---------|-------|---------|
| 指纹系统 | `test_fingerprint_lib.py`, `test_fingerprint_dedup.py` | 43 | 4 类指纹 + NaN/Inf 处理 + 去重 |
| 协变量诊断 | `test_covariate_diagnostics.py` | 12 | all_zero/inert_constant/horizon_flat/effective |
| 三路消融 | `test_ablation.py`, `test_ablation_integration.py` | 46 | 4 模式接线 + 审计集有效性 + resume 守卫 + covariates_used |
| 提案质量门 | `test_proposal_quality_gate.py`, `test_sector_filter.py`, `test_covariate_filter.py`, `test_harvest_proposals.py` | 65 | 评分项逐项 + 板块/协变量过滤 + E2E 接线 + 冷启动回归 |

**回归套件:** `test_supervisor.py`, `test_praxist_fm_evaluator.py`, `test_verdict_registry.py`, `test_praxist_evidence_ladder.py`, `test_praxist_task_contract.py`, `test_combo_parity.py`, `test_hourly_align_frame.py`, `test_migrate_verdicts_v1_to_v2.py`, `test_evaluation_metrics_contract.py` 等 — 全部通过。

**关键回归保护:**
- `test_cold_start_not_blocked_by_quality_gates`: 空 snapshot 不得被新门挡住（防 2026-09-24 饿死重演）
- `test_predict_default_mode_is_full`: 默认 ablation_mode=full 行为不变
- `test_predict_baseline_mode_skips_covariates`: baseline 主动选择，xreg_fallback=False

## 5. 生产数据实测

评审期间对生产 registry (`task_FM/config/aligned_verdicts.jsonl`, 143 条裁决, 14 品种) 运行完整门逻辑：

| 指标 | PR-B6 修复前 | PR-B6 修复后 |
|------|------------|------------|
| sector 拦截率 | 434/434 (100%) | 0/434 (0%) |
| covariate 拦截率 | (未达) | 78/434 (18.0%) |
| quality 拦截率 | (未达) | 82/434 (18.9%) |
| 通过率 | 0% | 274/434 (63.1%) |

**结论:** PR-B6 修复后，提案通过率合理，不会饿死慢环。

## 6. 已知后续 (非 Stage 2 范围)

| 项 | 来源 | 说明 |
|---|------|------|
| PR-B4 dir_acc 口径变更 | 计划 | 影响面过大，留待 Stage 3 |
| L3 resume 检查位置 | PR-B5 评审 | resume 冲突检查在模型加载 (~800MB) 后执行，性能/UX 问题 |
| N3 predict() seed 参数 | PR-B5 评审 | seed 硬编码 42，无法多 seed 敏感性分析 |
| symbol_has_pass 与 pass_variants 定义差异 | PR-B6 评审 | quality gate 用 `gate_pass` 真值 vs pass_variants 更严的 v2 定义。是设计取舍，不改 |
| 板块部分退化预警 | PR-B6 评审 | `n_failed >= sector_size * 0.5` 时 WARN 日志 |

## 7. 结论

**Stage 2 全部 5 个 PR 已完成并经专家评审 + 修复。**

- PR-B1/B2/B3 评审通过 (无 CRITICAL)
- PR-B5 评审返回 REQUEST CHANGES，1 CRITICAL + 2 HIGH 修复后通过
- PR-B6 评审返回 REQUEST CHANGES，1 CRITICAL (100% 饿死) 修复后 APPROVE，复评通过

测试 312 passed，生产数据实测通过率 63.1%，无饿死风险。

**Stage 2 出口关闭。** 可进入 Stage 3 (PR-B4 dir_acc 口径 + 其他待办)。
