# Three-loop Open Closure Implementation Plan
> **代码基线**: `c814f11`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 2026-10-03 运行报告里已经能落地、且不需要宿主重新裁定的开口收口：运行手册与现行目标一致，两处红测转绿，探索裁决不再落下可确认的 `fdr_pass`，描述性失败不再杀死协变量族，慢环座位只给已有当前协议无协变量基线的品种，确认分派接到现成函数上，第一次停机信号不再接着开新的收割或新的快环。对照 `docs/superpowers/reports/2026-10-03-fm-a-open-issues.md` 之后，可执行任务仍是下面九项。

**Architecture:** 每项都改现有函数的门，不新造调度器，不改自适应门槛，不改协议指纹，不重写 `aligned_verdicts.jsonl`。`bh_fdr_promote` 继续只做 BH / Bonferroni 算术；能否落成 `fdr_pass=True` 由监督环侧的新过滤器决定。`_dead_families` 仍用 `min_ok=4`，pass 计数继续读 `gate_pass`，不改成 `registry_lib.pass_variants()`；计入的行必须是可确认的 DM 状态。座位过滤放在 `harvest_proposals` 里。基线补齐只扩展 `ensure_baselines` 的品种参数，生成仍走现成的 `generate_baseline_points.generate`，本计划的测试用假模块挡住真实导入。确认入队调用已经存在的 `dispatch_confirmation` / `finalize_confirmation`。停机仍由 `_signal_handler` 只置标志，主循环在开新工作前和睡眠切片里读这个标志。不加 90 秒看门狗。

**Tech Stack:** Python 3.11（`/home/abug/timesfm/.venv`），pytest，现有 `scripts/praxist_supervisor.py`、`cascade/statistical_tests.py`、`scripts/preregistry.py`、`cascade/baseline_paths.py`。不加载 TimesFM 权重。

**Spec:** `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15）W3.3、W3.4、W3.6、§7.8；Q7 备忘录 (a′) Δ\*=0.08 / 功效 80% / 单侧 α=0.05；`docs/superpowers/plans/2026-09-30-v4-convergence-implementation-plan.md` 阶段 3.3。46 小时事实来源是 `docs/superpowers/reports/2026-10-03-three-loop-v4-operations-report.md`，其中与本计划冲突的两句（`cf_calendar` 可做下一条预注册、`star` 字段为空等于评级链没产出）不采用。开口对照是 `docs/superpowers/reports/2026-10-03-fm-a-open-issues.md`。该报告 §1.1 说 `_dead_families` 的 pass 来自 `registry_lib.pass_variants()`，与 `scripts/praxist_supervisor.py` 第 1194–1212 行不符：死亡计数读的是 `gate_pass`。`pass_variants` 在 `scripts/registry_lib.py` 第 516 行，要求确认运行且 `gate_pass`、`fdr_pass`、`p_value` 同时成立，它是成功计数，不是死亡计数。报告 §1.4 的三条补救不进入实现。

## Global Constraints

- 活仓只认 WSL `/home/abug/timesfm`。执行前用 `ps -eo pid,cmd` 看监督环是否还在。监督环在跑时，代码改动放进 `superpowers:using-git-worktrees` 建的工作树，不直接改活检出。本计划文件本身可以留在 master 的 `docs/superpowers/plans/`。
- 不要启动、停止或重启监督环。不要调用 `scripts/restart_three_loop_clean.sh`，不要调用 `start_supervisor.sh`。
- 不要在测试或执行过程中调用真实的 `generate_baseline_points.generate`，不要导入会加载 TimesFM 权重的路径来“试一下基线”。假模块必须先放进 `sys.modules["generate_baseline_points"]`。
- 不要把 `missingness_admissible` 改成 True。§7.8 的缺失检验方法仍由宿主定。生产裁决上这个字段保持 False。
- 不要改自适应门 `effective_min = max(0.50, min(0.52, baseline_dir_acc))`。
- 不要重写、截断或回填 `aligned_verdicts.jsonl`。已有的那条探索行 `fdr_pass=True` 留在文件里。目标计数仍然要 `run_label==confirmed` 且 `fdr_pass is True`，所以那条探索行不会变成成功。
- 不要把 `token_budget_m` 改回 200，也不要写成 999999。缺失该键时默认上限仍是 80。null 表示不参与停机。`max_cycles` 2000、`cpu_hours` 2000、`deadline` `2028-10-02` 不动。
- 不要勾选 v4 计划里的任务 E。那一项含验收和记忆同步，本计划不代勾。
- 不要处置 `tests/test_no_dead_code.py` 里已有的 6 条 `REVIEW_CANDIDATES`（`ablation_context`、`add_horizon_known`、`resmoke_vol_thr_offline`、`scan_vol_thr_smoke`、`validate_context_length`、`verify_baseline_consistency`）。不要归档这 6 个文件。
- 不要预注册 `cf_calendar_5bd18d23ae63`。它的 `baseline_dir_acc` 是 null，`p_value` 是 null，`dm_status` 是 `no_common_cutoff`。同一协变量在已有基线的 fu、cj 上没有过门。
- 不要提高 `cadence.survivors_per_cycle`（现在是 3）。不要把池外的 11 个未用动量名放进活跃池。`known_ahead` 仍只有 `calendar_cyclical`，且 `verified_by` 不能由执行者自己填。
- 不要给 `multi_seed` / `decay` 发明数值通过线。`docs/superpowers/specs/2026-10-02-phase3-multiseed-decay-todo.md` 写明它们不是通过规则。
- 不要改 `GOAL_SYMBOLS_SET`。它仍是 `m, ss, sr, cj, jd, lh, eg, rb, fu` 这 9 个，继续只服务原有的命中计数。预检品种表另走 goal 的 `target_symbols`。
- `_dead_families` 的 `min_ok` 保持 4。不要改成约 30，也不要改成别的数。不要改成「必须已有 `run_mode=confirmation` 的记录才允许死亡」，也不要在确认产出为 0 时豁免全部家族死亡。
- 不要把 `_has_prior_failure` 从「同 symbol 或同 cov」改成必须同一配对。不要把农产品断路器从「失败数达到板块人数」改成半数。不要扩大 `config/sector_map.py`。不要加 90 秒停机看门狗。不要自动改写已锁定的 `n_confirm_required`，不要改 Δ\*=0.08。细则在「报告处置」。
- 可确认的 `dm_status` 只有 `ok` 和 `set_mismatch_ok`（spec W3.4）。`self_referential` 不是确认门槛。v4 裁决没有 `star` 字段；`tier` 已经在写。不要补 `star`。
- 确认样本未满且 `request_early_seal is not True` 时，`finalize_confirmation` 只返回 peek。不要为了“看到确认结果”去提前封账。今天入队也填不满 jd 的 1199 和 sr 的 986。
- 第一次 SIGTERM/SIGINT 只停止新的收割、新的复测入队、新的确认入队、新的快环启动。已经在跑的子进程不要加新的杀死逻辑。`_signal_handler` 继续只置 `_SHUTDOWN_REQUESTED`，里面不要做 I/O。
- 提交信息用英文，风格对齐 `fix(v4):` / `docs(v4):` / `test(v4):` / `feat(v4):`。不要 push，不要 force-push。`third_party/timesfm-3.0-official` 的示例图片保持不提交。
- 测试只用下面这种聚焦命令。不要跑全量 pytest。工作目录是仓库根。从 PowerShell 包一层 `wsl` 时，命令字符串里不要放 `$` 和反引号。
- 任务 3、7、8 必须在任务 9 之前。其余任务各自能测，仍按编号顺序提交，避免两个人同时改 `_main_locked`。

## 文件地图

- 修改 `docs/runbook_praxist_three_loop.md`：现行成功条件和预算；写明已锁定的预注册样本量不由监督环改写；座位拒绝原因补 `no_current_baseline`。
- 修改 `tests/test_goal_tiers.py`：锁住运行手册不再写退役公式。
- 修改 `tests/test_supervisor.py`：复测夹具补协议指纹；停机信号测试。
- 修改 `tests/test_no_dead_code.py`：只给 `TEMPORARY_ALLOWLIST` 加 `write_first_preregistry`。
- 修改 `tests/test_harvest_proposals.py`：夹具种下当前协议无协变量基线；描述性失败不杀族；无基线不占座。
- 修改 `scripts/praxist_supervisor.py`：FDR 落盘过滤、`_dead_families`、座位过滤、预检品种、停机守卫、确认入队与终结。
- 修改 `tests/test_confirmation_wiring.py`：确认队列行和到期过滤。不新增第二套调度器文件。
- 不修改 `cascade/statistical_tests.py` 的 `bh_fdr_promote`。
- 不修改 `scripts/praxist_goal.yaml`。
- 不修改 `task_FM/config/preregistry.jsonl`。
- 不修改 `task_FM/evaluations/fm_eval/aligned_verdicts.jsonl` 或任何裁决 jsonl。

## 明确不做

- §7.8 缺失方法，以及把 `missingness_admissible` 翻成 True。
- 6 条 `REVIEW_CANDIDATES` 的归档或删除。
- 为 Phase 3 发明通过门槛。
- 恢复 token 上限，或写成无界大数。
- 预注册 `cf_calendar_5bd18d23ae63`，以及下面两条自指命中：`m_momentum_b06ddbcd88e3`（vwap_deviation，dir_acc 0.515，p=0.0236，`gate_pass` True，`horizon_known=self_referential`，`dm_status=set_mismatch_descriptive`，`missingness_admissible` False）、`lh_momentum_8c75bd7b917f`（oi_gated_momentum，dir_acc 0.531，p=0.0374，`gate_pass` False，同样是 self_referential 且描述性 DM）。报告表格漏写了 lh 这条没有过门。`self_referential` 不是确认门槛，本计划不加 `horizon_known` 门。
- `cf_calendar_5bd18d23ae63` 的 dir_acc 是 0.576、`gate_pass` True，但 `p_value` 是 null、`baseline_dir_acc` 是 null、`dm_status` 是 `no_common_cutoff`、`pairing_valid` False、`missingness_admissible` False。cf 没有当前协议无协变量基线，这不是一条 DM 结果。同一协变量在已有基线的品种上：`fu_calendar_89c2b2e2f8be` dir_acc 0.433、p=1.0、`gate_pass` False、`dm_status=set_mismatch_descriptive`、baseline 0.447；`cj_calendar_08b83d656d35` dir_acc 0.494、p=0.131、`gate_pass` False、同样是描述性 DM、baseline 0.442。三条的 `horizon_known` 都是 `known_ahead`。
- 提高 `top_k` / `survivors_per_cycle`。
- 把未入池的动量名或 `oi_gated_ha_body` 放进活跃池。
- 删除 `_dead_families`，或把 `min_ok` 改成约 30，或改成「等确认记录出现才允许死亡」，或在确认产出为 0 时豁免死亡。当前协议快照（指纹前缀 `f02b2a43`，last-wins 44 行，全部 `run_mode=exploration`）里，死亡集合只有 `term_structure`。各家 ok 行数 / `gate_pass` 行数：momentum 15/7，inventory 13/3，volatility 8/2，calendar 3/1，term_structure 5/0。term_structure 这 5 行全是 `dm_status=set_mismatch_descriptive`（cj crack_spread_slope、jd crack_spread_level、m crack_spread_zscore、sr crack_spread_slope、sr crack_spread_zscore）。「每族 pass 都是 0」与这张表不符。`family_dead` 从 602 到 642 是累计重扫拒绝次数，20:28 时已经是 602，不是新死掉的一族。
- 把 `_has_prior_failure` 改成必须同一品种且同一协变量。运行手册约第 131 行写的是同 symbol 或同 cov。`045c7e2` 只按当前协议过滤，没有放宽这条。开口报告窗口里 `no_failure_delta` 从 1226 到 1922（+696）、可用候选从 123 到 67，比 `family_dead` +40 大得多。这 696 次是既有规则在每轮重扫里累计拒绝，不是与 `family_dead` 并列的第二个收割缺陷，所以本计划不改这条或规则。宿主保留的次生风险：覆盖面很宽。当前协议快照里某品种只要有一条 `status` 为 ok（缺省也算 ok）且 `gate_pass` 不为真的裁决，该品种之后每条提案都要有不少于 20 字的 `failure_delta`；某协变量只要有这样一条裁决，所有品种上的该协变量同样要写。当前协议失败 31 行、10 个品种（cj、eg、fu、jd、lh、m、ma、p、rb、sr）、17 个协变量、31 个配对；活跃池 31 个协变量里 17 个已被碰到。`family_dead` 的 642 是累计重扫次数，不是 642 个新座位。任务 4 只是让描述性失败不再杀死一族；收割顺序里 `family_dead` 在 `no_failure_delta` 之前，这些提案放过去之后仍可能被或规则拦住。任务 4 被监督环实际收割过至少一轮之后再看 `family_dead`、`no_failure_delta` 和可用候选数。曲线仍下滑就再议，不在本计划里把或改成与。
- 下调农产品断路器，或把未观察品种算成失败。`config/sector_map.py` 的 agri 就是 `m, p, cf, sr, jd, lh, cj, ur, fg, ao` 这 10 个。`_sector_filter_check`（约 1486 行）只在失败数达到板块人数时切断；达到一半只打 WARN。未观察的品种不计入失败，所以 ur、fg、ao 没有裁决时失败数到不了 10。当前协议各品种最近一条：失败的是 m（oi，dir_acc 0.466，unknowable，描述性 DM）、p（bb_squeeze，dir_acc 0.483，`no_common_cutoff`，p 没有无协变量基线，已由任务 5 和任务 6 覆盖）、sr（crack_spread_zscore，dir_acc 0.501，描述性，p=1.0）、lh（oi，dir_acc 0.37，描述性，p=1.0）、cj（calendar，dir_acc 0.494，known_ahead，p=0.131）；过门的是 cf（bb_squeeze，同样没有基线）和 jd（ha_body）；ur、fg、ao 没有裁决。这 5 条失败的状态都是 ok、n=588，协变量并不相同，不是同一条评估异常。spec W6.1b 仍想给 agri 加 y、oi，给 energy_chem 加 l、pp、px、sc；这张表还被 Regime、VolRisk、Neutral A/B 共用，本计划不扩大它。y、px、oi、sc 在 goal 里但不都在 `ALLOWED_SYMBOLS`，现有的 `symbol_not_allowed` 保持原样。
- 新造季度 cron，或改写 `task_FM/config/preregistry.jsonl` 里已锁定的 1199 / 986。确认要 1.2–2.0 年是 Q7 (a′) 的样本量，任务 1 只把「监督环不改写、季度复核是宿主动作」写进运行手册。
- 补一个 `star` 字段。运行报告里已经没有「star 字段」那句。历史 changelog `docs/superpowers/changelogs/2026-10-01-v4-stage2-done-stage3-start.md` 第 140 行的旧句不改写；2026-10-03 的勘误以本计划为准。`tier` 已经在写。
- 勾选 v4 计划任务 E，改 `STATE.md`，改 Windows 侧 `D:\FlyBuddy\fma-audit\`。
- 在本计划执行中真正生成 cf/i/p/sh/ma 的基线。那是下一次监督环已停止之后的维护窗口操作，由预检代码在那时调用现成 `generate`。本计划只把调用名单和测试夹具写对。

## 报告处置

核对日是 2026-10-03。当前协议快照用 `<FM_ROOT>/.venv/bin/python` 重读。系统 `python3` 没有 numpy，协议指纹会失败打开，快照会把历史行全部算进来，那次数不能用来下结论。监督环在这次只读核对里没有被启动或停止。

| 报告位置 | 处置 |
|---|---|
| §5.1 两则红测 | 任务 2。两则兄弟测试一起钉住当前协议指纹，避免假绿。 |
| §5.2 第一次 SIGTERM 约 180 秒后才停 | 任务 7。睡眠改成 1 秒切片。不加 90 秒看门狗。「约 90 秒干净退出」写在两份 2026-10-03 报告里，`docs/three_loop_restart_protocol.md` 和运行手册里没有这句。 |
| §4 star 勘误 | 明确不做。不改代码，不改历史 changelog。 |
| §1 `family_dead` | 任务 4 只改计入口径：描述性 DM 不计数，`min_ok` 仍是 4，pass 仍是 `gate_pass`。§1.1 的 `pass_variants` 诊断和 §1.4 的三条补救不采用。 |
| §1 表里的 `no_failure_delta` 与候选下降 | 本计划不改或规则。它是候选 123→67 的主因，也是任务 4 之后的次生风险。监督环实际收割过至少一轮后再测；曲线仍下滑再议。 |
| §2 确认要 1.2–2.0 年 | 任务 1 的运行手册句子。不新造调度器，不改锁定样本量，不改 Δ\*=0.08。 |
| §3 自指命中，以及把 `cf_calendar` 预注册 | 明确不做。上面三条日历行和两条自指行都不进预注册。 |
| §5.3 农产品 5/10 超过 46 小时 | 明确不做。断路器保持全板块才切断。p 的缺基线由任务 5 和任务 6 处理。 |

---

### Task 1: 运行手册与现行目标对齐

**Files:**
- Modify: `docs/runbook_praxist_three_loop.md:149`
- Test: `tests/test_goal_tiers.py`

**Interfaces:**
- Consumes: `scripts/praxist_goal.yaml` 已有字段 `success_condition: ["all_symbols_pass_phase1"]`，`budgets.max_cycles: 2000`，`budgets.cpu_hours: 2000`，`budgets.token_budget_m: null`，`budgets.deadline: "2028-10-02"`，`cadence.target_symbols` 24 个品种。
- Produces: 运行手册「当前 goal」段不再含退役公式，并写明已锁定的预注册样本量不在监督环里改写。后续任务不读这一段做门控。

开口报告 §2 把 1.2–2.0 年的确认等待写成待修问题。这是 Q7 (a′) 锁定样本量之后的日历长度。本任务不新造调度器，不改 `task_FM/config/preregistry.jsonl`，不改 Δ\*=0.08。新段落不得重新写入 `999999`、`2099-12-31`、`n_gate_pass_variants`、`0.51`、`n_tier_a_or_b`；这五个字符串目前只出现在运行手册第 149 行。

- [ ] **Step 1: Write the failing test**

在 `tests/test_goal_tiers.py` 末尾添加：

```python
def test_runbook_states_live_success_and_bounded_budget():
    text = (project_root / "docs" / "runbook_praxist_three_loop.md").read_text(encoding="utf-8")
    assert "all_symbols_pass_phase1" in text
    assert "`max_cycles`=2000" in text
    assert "`cpu_hours`=2000" in text
    assert "`token_budget_m`=null" in text
    assert "`deadline`=2028-10-02" in text
    assert "999999" not in text
    assert "2099-12-31" not in text
    assert "n_gate_pass_variants" not in text
    assert "0.51" not in text
    assert "n_tier_a_or_b" not in text
    assert "已锁定的预注册样本量不在监督环里改写" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_goal_tiers.py::test_runbook_states_live_success_and_bounded_budget -q --tb=line`

Expected: FAIL，因为第 149 行仍有 `n_gate_pass_variants`、`0.51`、`999999`、`2099-12-31`，且全文还没有「已锁定的预注册样本量不在监督环里改写」。

- [ ] **Step 3: Write the replacement paragraph**

把 `docs/runbook_praxist_three_loop.md` 第 149 行整段换成下面这一段，不要在文件其他地方再写那些退役数字：

```markdown
成功条件（以 `scripts/praxist_goal.yaml` 为准）：只有 `all_symbols_pass_phase1`。一个品种达到「可预测」当且仅当至少有一条 family 封账的确认：`run_label` 为 confirmed 且 `fdr_pass` 为 True。原三阶段门槛和无界预算已经退役，本文件不再记录那些公式。目标品种 24 个：m/ss/sr/cj/jd/lh/eg/rb/i/p/y/cf/bu/fu/ta/ma/fg/ur/px/oi/sh/sp/ao/sc。预算：`max_cycles`=2000，`cpu_hours`=2000，`token_budget_m`=null（不参与停机），`deadline`=2028-10-02。cadence：survivors=3、aligned_max_points=600、quota 窗 5h、run 预算 1.5h。`dir_acc` 主口径为剔零变动（spec W6.5①，PR-B4）；经济数值仅作报表参考，不参与裁决。已锁定的预注册样本量不在监督环里改写。jd 的确认样本仍是 1199，sr 的确认样本仍是 986，都写在 `task_FM/config/preregistry.jsonl`。Q7 备忘录要求重启后按 live 密度修订日历，并且每季按实测 Var_LR 复核 Δ_min；那是宿主动作，监督环不为此改预注册文件，也不改 Δ\*=0.08。
```

不要编辑 `docs/superpowers/plans/2026-09-30-v4-convergence-implementation-plan.md` 的任务 E 勾选框。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_goal_tiers.py::test_runbook_states_live_success_and_bounded_budget tests/test_goal_tiers.py::test_goal_yaml_drops_old_bar_and_unbounded_budget -q --tb=short`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add docs/runbook_praxist_three_loop.md tests/test_goal_tiers.py
git commit -m "docs(v4): record the live three-loop success condition in the runbook"
```

---

### Task 2: 两处红测改在测试侧

**Files:**
- Modify: `tests/test_supervisor.py:988-1058`
- Modify: `tests/test_no_dead_code.py:56-58`
- Test: 上述两个现成测试

**Interfaces:**
- Consumes: `plan_sample_retests` 已经通过 `_active_protocol_snapshot` 丢掉无指纹行。`test_no_unaccounted_modules` 要求 stem 属于引用集、`LIVE_ENTRIES`、`TEMPORARY_ALLOWLIST` 或 `REVIEW_CANDIDATES`。
- Produces: 无新生产函数。`REVIEW_CANDIDATES` 的 6 个键保持原样。

- [ ] **Step 1: Run the two red tests and read the failure**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_maybe_enqueue_retests_gating_and_dedup tests/test_no_dead_code.py::test_no_unaccounted_modules -q --tb=line`

Expected: 第一则失败是入队数为 0 而不是 1。第二则失败点名 `scripts/write_first_preregistry.py`。若第一则已经通过，停下来核对 `_current_protocol_fingerprint` 是不是在该环境下返回了 None；返回 None 时无指纹行不会被过滤，这个夹具修复仍然要做，避免环境一变就再红。

- [ ] **Step 2: Pin the fingerprint on the three retest fixtures**

`test_maybe_enqueue_retests_respects_margin` 和 `test_maybe_enqueue_retests_fail_open_on_db_error` 用同一条无指纹裁决。前者期望 0，协议过滤也会得到 0，所以它现在是假绿。三处都要钉住指纹。

把 `_aligned_verdict` 改成接受可选指纹：

```python
def _aligned_verdict(vid, symbol, cov, n, pf, ev, ic, gate, status="ok",
                     max_points=600, protocol_fingerprint=None):
    row = {"variant_id": vid, "symbol": symbol, "cov_override": cov,
           "max_points": max_points, "n": n, "pf": pf, "ev": ev, "maxdd": -0.2,
           "dir_acc": 0.5 + ic / 2.0, "gate_pass": gate, "ic": ic,
           "decided_at": "2026-09-08T00:00:00", "checkpoint_path": "",
           "slow_loop_pid": 1, "git_rev": "x", "schema": "fm.aligned_verdict.v1",
           "status": status}
    if protocol_fingerprint is not None:
        row["protocol_fingerprint"] = protocol_fingerprint
    return row
```

在下面三个测试的写注册表之前各加一行：

```python
monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "current")
```

并把这三处 `_aligned_verdict(...)` 都加上 `protocol_fingerprint="current"`：

- `test_maybe_enqueue_retests_gating_and_dedup`
- `test_maybe_enqueue_retests_respects_margin`
- `test_maybe_enqueue_retests_fail_open_on_db_error`

`test_retest_candidates_only_n_near_miss` 直接把字典交给 `_retest_candidates`，不走快照过滤，不要改它的断言。

- [ ] **Step 3: Account for the one-shot script**

只改 `TEMPORARY_ALLOWLIST`，不要动 `REVIEW_CANDIDATES` 和 `LIVE_ENTRIES`：

```python
TEMPORARY_ALLOWLIST: dict[str, str] = {
    "write_first_preregistry": (
        "一次性人工命令（scripts/write_first_preregistry.py）："
        "2026-10-02 已执行，task_FM/config/preregistry.jsonl 已有两条；"
        "文件存在时拒绝重写；零运行时引用。不归档，不并入 REVIEW_CANDIDATES。"
    ),
}
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_maybe_enqueue_retests_gating_and_dedup tests/test_supervisor.py::test_maybe_enqueue_retests_respects_margin tests/test_supervisor.py::test_maybe_enqueue_retests_fail_open_on_db_error tests/test_supervisor.py::test_retest_candidates_only_n_near_miss tests/test_no_dead_code.py -q --tb=short`

Expected: PASS。`test_stale_list_entries` 也要过，因为 `scripts/write_first_preregistry.py` 还在。

- [ ] **Step 5: Commit**

```bash
git add tests/test_supervisor.py tests/test_no_dead_code.py
git commit -m "test(v4): pin retest fixtures to the current protocol and account for the preregistry one-shot"
```

---

### Task 3: 探索行和描述性 DM 不能落下 fdr_pass=True

**Files:**
- Modify: `scripts/praxist_supervisor.py:2792-2804`
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `cascade.statistical_tests.bh_fdr_promote(verdicts) -> dict[str, dict]`，值的形状是 `{"fdr_pass": bool}`。本任务不改这个函数，也不改它的现有单测。
- Produces:
  - `fdr_pass_persistable(verdict: dict) -> bool`
  - `promote_batch_for_persistence(verdicts: list[dict]) -> dict[str, dict]`
  - 监督环批次收尾改调用 `promote_batch_for_persistence`。

W3.4 要 `run_mode==confirmation`、`missingness_admissible is True`、`dm_status` 属于 `ok` 或 `set_mismatch_ok`，才可能成功。生产代码在 `missingness_admissible` 为 False 时只会给出 `set_mismatch_descriptive`，不会给出 `ok`。过滤器仍两边都查，避免只改状态字符串就落成 True。

- [ ] **Step 1: Write the failing test**

在 `tests/test_supervisor.py` 末尾添加：

```python
def _promotable(run_mode, dm_status, missingness, p_value=0.01, gate_pass=True):
    return {
        "variant_id": "jd_momentum_abc123abc123",
        "symbol": "jd",
        "gate_pass": gate_pass,
        "p_value": p_value,
        "run_mode": run_mode,
        "dm_status": dm_status,
        "missingness_admissible": missingness,
    }


def test_exploration_or_descriptive_dm_cannot_persist_fdr_pass():
    exploration = _promotable("exploration", "set_mismatch_descriptive", False)
    no_cutoff = _promotable("confirmation", "no_common_cutoff", False)
    status_only = _promotable("confirmation", "ok", False)
    ready = _promotable("confirmation", "ok", True)
    mismatch_ok = _promotable("confirmation", "set_mismatch_ok", True)
    mismatch_ok["variant_id"] = "sr_momentum_def456def456"
    updates = sup.promote_batch_for_persistence(
        [exploration, no_cutoff, status_only, ready, mismatch_ok])
    assert updates["jd_momentum_abc123abc123"]["fdr_pass"] is True
    assert updates["sr_momentum_def456def456"]["fdr_pass"] is True
    # 同 variant_id 后写覆盖前写。不可确认的三条都用了同一个 vid，最后一条 ready 才为 True。
    # 下面把不可确认行单独送入，确认它们自己不会被写成 True。
    assert sup.promote_batch_for_persistence([exploration])["jd_momentum_abc123abc123"]["fdr_pass"] is False
    assert sup.promote_batch_for_persistence([no_cutoff])["jd_momentum_abc123abc123"]["fdr_pass"] is False
    assert sup.promote_batch_for_persistence([status_only])["jd_momentum_abc123abc123"]["fdr_pass"] is False
    assert sup.fdr_pass_persistable(exploration) is False
    assert sup.fdr_pass_persistable(ready) is True
```

`bh_fdr_promote` 在 K<4 时用 Bonferroni α=0.025。`p_value=0.01` 且 `gate_pass=True` 时算术结果是 True，过滤器再把它打回 False。这正是要锁住的泄漏。

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_exploration_or_descriptive_dm_cannot_persist_fdr_pass -q --tb=line`

Expected: FAIL，`AttributeError: promote_batch_for_persistence`。

- [ ] **Step 3: Implement the filter and switch the one call site**

在 `scripts/praxist_supervisor.py` 里、`bh_fdr_promote` 的导入已经可见的位置附近添加。若该名字是函数内导入，就在模块级从 `cascade.statistical_tests` 导入同名函数，不要复制 BH 算术。

```python
_PERSISTABLE_DM = frozenset({"ok", "set_mismatch_ok"})


def fdr_pass_persistable(verdict):
    """W3.4：只有确认运行、缺失可接受、且 DM 状态可确认时，fdr_pass=True 才能落盘。"""
    if not isinstance(verdict, dict):
        return False
    return (
        verdict.get("run_mode") == "confirmation"
        and verdict.get("missingness_admissible") is True
        and verdict.get("dm_status") in _PERSISTABLE_DM
    )


def promote_batch_for_persistence(verdicts):
    """先做原 BH/Bonferroni，再拒绝不可确认行的 True。不写文件。"""
    updates = bh_fdr_promote(verdicts)
    by_vid = {}
    for verdict in verdicts or []:
        vid = verdict.get("variant_id")
        if vid is not None:
            by_vid[vid] = verdict
    for vid, update in updates.items():
        if update.get("fdr_pass") is True and not fdr_pass_persistable(by_vid.get(vid)):
            update["fdr_pass"] = False
    return updates
```

把 `_main_locked` 慢环收尾里的：

```python
updates = bh_fdr_promote(batch_verdicts)
```

换成：

```python
updates = promote_batch_for_persistence(batch_verdicts)
```

不要改 `cascade/statistical_tests.py`。不要回写已有 jsonl。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_exploration_or_descriptive_dm_cannot_persist_fdr_pass tests/test_statistical_tests.py tests/test_confirmation_wiring.py -q --tb=short`

Expected: PASS。`bh_fdr_promote` 的旧断言仍是算术本身为 True。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_supervisor.py
git commit -m "fix(v4): persist fdr_pass only on confirmable rows"
```

---

### Task 4: 只有可确认的 DM 失败才让一族死亡

**Files:**
- Modify: `scripts/praxist_supervisor.py:1194-1212`
- Modify: `tests/test_supervisor.py:1513-1529`
- Modify: `tests/test_harvest_proposals.py:311-333`
- Test: 上述两处，加新测试

**Interfaces:**
- Consumes: 无前序任务的新函数。裁决字段 `status`、`cov_family`、`gate_pass`、`dm_status`。`run_mode` 不参与死亡判断。
- Produces: `_dead_families(snapshot, min_ok=4) -> set[str]`。签名不变。`min_ok` 默认值仍是 4。计入的行必须 `status==ok`（缺省仍视为 ok，与现在一致）且 `dm_status` 属于 `{"ok", "set_mismatch_ok"}`。pass 计数继续是 `v.get("gate_pass")`，函数体内不调用 `registry_lib.pass_variants`。

开口报告 §1.4 的三条补救不实现：不把 `min_ok` 提到约 30，不等待 `run_mode=confirmation` 的记录，也不在确认产出为 0 时豁免死亡。下面的杀死族断言故意只放 `run_mode="exploration"` 的行。若实现改成那三条里的任意一条，这则测试必须失败。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_supervisor.py` 的 `test_dead_families_identified` 之后添加：

```python
def test_descriptive_failures_do_not_kill_a_family():
    rows = {}
    for i, status in enumerate(
        ["set_mismatch_descriptive", "set_mismatch_descriptive",
         "no_common_cutoff", "no_common_cutoff", "insufficient_common"]
    ):
        rows["r%s" % i] = {
            "variant_id": "r%s" % i, "symbol": "m", "cov_family": "term_structure",
            "status": "ok", "gate_pass": False, "dm_status": status,
            "run_mode": "exploration",
        }
    assert "term_structure" not in sup._dead_families(rows)
    confirmatory = {
        "r%s" % i: {
            "variant_id": "r%s" % i, "symbol": "m", "cov_family": "term_structure",
            "status": "ok", "gate_pass": False, "dm_status": "ok",
            "run_mode": "exploration",
        }
        for i in range(3)
    }
    assert "term_structure" not in sup._dead_families(confirmatory)
    confirmatory["r3"] = {
        "variant_id": "r3", "symbol": "ss", "cov_family": "term_structure",
        "status": "ok", "gate_pass": False, "dm_status": "set_mismatch_ok",
        "run_mode": "exploration",
    }
    assert "term_structure" in sup._dead_families(confirmatory)
```

把现有 `test_dead_families_identified` 里 4 条 `ccl` 失败行都加上 `"dm_status": "ok"` 和 `"run_mode": "exploration"`。`m_oi` 那条过门行也加上 `"dm_status": "ok"`。不改断言。

把 `tests/test_harvest_proposals.py` 的 `test_dead_family_harvest_rejected` 里 4 条 inventory 失败行都加上 `"dm_status": "ok"` 和 `"run_mode": "exploration"`。

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_descriptive_failures_do_not_kill_a_family tests/test_supervisor.py::test_dead_families_identified -q --tb=line`

Expected: 新测试 FAIL，因为 5 条描述性失败在旧规则下 `term_structure` 已死；3 条可确认失败不该死，这条会先过。旧测试在补上 `dm_status` 之后、实现改完之前会 FAIL（4 条 `ok` 不再被计入）。

- [ ] **Step 3: Count only confirmatory DM rows**

把 `_dead_families` 换成：

```python
_CONFIRMATORY_DM = frozenset({"ok", "set_mismatch_ok"})


def _dead_families(snapshot, min_ok=4):
    """一族至少 min_ok 条可确认 DM 的 ok 裁决且 0 条过门，才算死亡。

    dm_status 缺省、set_mismatch_descriptive、no_common_cutoff、
    insufficient_common 都不计数。min_ok 仍是 4。
    run_mode 不读：探索行上的可确认失败同样计数。
    pass 计数是 gate_pass，不调用 pass_variants。
    """
    fam_ok = {}
    fam_pass = {}
    for v in (snapshot or {}).values():
        if not isinstance(v, dict) or v.get("status", "ok") != "ok":
            continue
        if v.get("dm_status") not in _CONFIRMATORY_DM:
            continue
        fam = str(v.get("cov_family") or "").strip()
        if not fam:
            continue
        fam_ok[fam] = fam_ok.get(fam, 0) + 1
        if v.get("gate_pass"):
            fam_pass[fam] = fam_pass.get(fam, 0) + 1
    return {fam for fam, n in fam_ok.items()
            if n >= min_ok and fam_pass.get(fam, 0) == 0}
```

调用处 `dead_fams = _dead_families(snapshot or {})` 不要改参数。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_descriptive_failures_do_not_kill_a_family tests/test_supervisor.py::test_dead_families_identified tests/test_harvest_proposals.py::test_dead_family_harvest_rejected tests/test_harvest_proposals.py::test_live_family_still_enqueued -q --tb=short`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_supervisor.py tests/test_harvest_proposals.py
git commit -m "fix(v4): retire a family only after confirmatory DM failures"
```

落地后观察，不阻塞任务 5，本计划执行时也不启动监督环。宿主下次让监督环跑过至少一轮收割后，对照开口窗口的 `no_failure_delta` 1226→1922 和候选 123→67，读当时的 `family_dead`、`no_failure_delta` 和可用候选数。642 是累计重扫次数。描述性失败不再杀死一族之后，原先记在 `family_dead` 上的提案会继续走到或规则；品种或协变量上已有一条 ok 且未过门的裁决时，它们要有不少于 20 字的 `failure_delta`，不会自动变成座位。曲线仍下滑就停下来交给宿主，不要把 `_has_prior_failure` 改成同一配对。

---

### Task 5: 慢环座位只给有当前协议无协变量基线的品种

**Files:**
- Modify: `scripts/praxist_supervisor.py` 的 `harvest_proposals`（约 1664 行之后，协变量已确认在池中的位置）
- Modify: `tests/test_harvest_proposals.py` 的 `_make_run` 与 `tmproot`
- Modify: `docs/runbook_praxist_three_loop.md` 拒绝原因那一条（约第 131 行）
- Test: `tests/test_harvest_proposals.py`

**Interfaces:**
- Consumes: `cascade.baseline_paths.baseline_filename(symbol, None) -> "baseline_points_{symbol}_nocov.jsonl"`。`_baseline_protocol_fingerprint(path) -> (status, fp)`，`status=="ok"` 表示首行有指纹。`_current_protocol_fingerprint() -> str | None`。
- Produces: `_symbol_has_current_nocov_baseline(symbol: str, root: str) -> bool`。指纹暂时算不出来时返回 True，与 `ensure_baselines` 在指纹不可得时跳过重生一致。拒绝原因字符串是 `no_current_baseline`。`survivors_per_cycle` 仍由调用方传入，本任务不改 yaml。

- [ ] **Step 1: Write the failing test**

在 `tests/test_harvest_proposals.py` 的 `test_good_proposal_enqueued` 之后添加：

```python
def test_symbol_without_current_nocov_baseline_gets_no_seat(tmproot):
    _make_run(tmproot, _prop(symbol="m", cov="vor"), filename="m_vor.json")
    _make_run(tmproot, _prop(symbol="cf", cov="vor"), filename="cf_vor.json")
    missing = os.path.join(
        tmproot, "task_FM", "config", "baseline_points_cf_nocov.jsonl")
    os.remove(missing)
    rows, stats = _harvest(tmproot, top_k=3)
    assert [r["symbol"] for r in rows] == ["m"]
    assert stats["reject_reasons"].get("no_current_baseline") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_harvest_proposals.py::test_symbol_without_current_nocov_baseline_gets_no_seat -q --tb=line`

Expected: FAIL。当前收割会把 m 和 cf 都留下（`top_k` 是 3），并且没有 `no_current_baseline`。

- [ ] **Step 3: Plant a current baseline in the existing fixture, then filter**

`tmproot` 里、现有 `_experiment_fp_for` 补丁之后加：

```python
monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current-protocol")
```

`_make_run` 末尾加：

```python
config = os.path.join(root, "task_FM", "config")
os.makedirs(config, exist_ok=True)
base = os.path.join(config, "baseline_points_%s_nocov.jsonl" % symbol)
if not os.path.exists(base):
    with open(base, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "protocol_fingerprint": "current-protocol",
            "cutoff": "2026-01-01 00:00:00",
            "dir_ok": True,
        }) + "\n")
```

在 `praxist_supervisor.py` 添加：

```python
def _symbol_has_current_nocov_baseline(symbol, root):
    """当前协议的无协变量基线在，才占慢环座位。指纹算不出来时放行。不生成基线。"""
    fp = _current_protocol_fingerprint()
    if fp is None:
        return True
    from cascade.baseline_paths import baseline_filename
    path = os.path.join(root, "task_FM", "config", baseline_filename(symbol, None))
    status, got = _baseline_protocol_fingerprint(path)
    return status == "ok" and got == fp
```

`_baseline_protocol_fingerprint` 定义在文件后部，运行时解析即可，不要搬动它。

在 `harvest_proposals` 里，`cov_not_in_active_pool` 那次 `continue` 之后、`mechanism` 长度检查之前插入：

```python
if not _symbol_has_current_nocov_baseline(symbol, root):
    _reject("no_current_baseline"); continue
```

在运行手册拒绝原因列举里加上 `` `no_current_baseline` ``（该品种没有当前协议的 `baseline_points_{symbol}_nocov.jsonl`）。不要改 `survivors_per_cycle` 那一句的数字 3。

- [ ] **Step 4: Run the harvest tests**

Run: `.venv/bin/python -m pytest tests/test_harvest_proposals.py -q --tb=short`

Expected: PASS。`test_harvest_snapshot_ignores_other_protocols` 替换了 `harvest_proposals`，不受座位过滤影响。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_harvest_proposals.py docs/runbook_praxist_three_loop.md
git commit -m "fix(v4): give slow-loop seats only to symbols with a current nocov baseline"
```

---

### Task 6: 预检名单改为 goal 的目标品种

**Files:**
- Modify: `scripts/praxist_supervisor.py` 的 `_main_locked` 预检（约 2851 行）和 `ensure_baselines`（约 2578 行，函数体不改生成逻辑）
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `load_goal(path) -> dict`，`goal["cadence"]["target_symbols"]`。`ensure_baselines(symbols, root)` 已有实现：缺文件、行数小于 100、或首行指纹不等于当前指纹时调用 `generate_baseline_points.generate`。
- Produces: `_goal_target_symbols(goal) -> list[str]`，小写、保持 yaml 顺序、去重。`_main_locked` 先 `load_goal`，再 `ensure_baselines(_goal_target_symbols(goal), args.root)`。`GOAL_SYMBOLS_SET` 的 9 个成员一个都不加。

本任务的测试不准导入真实 `generate_baseline_points`。那个模块会带上 `monthly_backtest`。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_supervisor.py` 末尾添加：

```python
def test_goal_target_symbols_follow_yaml_order():
    goal = {"cadence": {"target_symbols": ["SS", "m", "cf", "m"]}}
    assert sup._goal_target_symbols(goal) == ["ss", "m", "cf"]
    assert sup._goal_target_symbols({}) == []
    live = sup.load_goal(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "praxist_goal.yaml"))
    got = sup._goal_target_symbols(live)
    assert got[:4] == ["m", "ss", "sr", "cj"]
    assert {"cf", "i", "p", "sh", "ma"} <= set(got)
    assert len(got) == 24


def test_ensure_baselines_asks_generate_only_for_a_missing_file(monkeypatch, tmp_path):
    import sys
    import types
    calls = []
    fake = types.ModuleType("generate_baseline_points")

    def baseline_filename(sym, cov):
        assert cov is None
        return "baseline_points_%s_nocov.jsonl" % sym

    def generate(sym, cov, root):
        calls.append((sym, cov))

    fake.baseline_filename = baseline_filename
    fake.generate = generate
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp-current")
    config = tmp_path / "task_FM" / "config"
    config.mkdir(parents=True)
    (config / "baseline_metrics.json").write_text(
        json.dumps({"m": {"n": 588}, "cf": {"n": 588}}), encoding="utf-8")
    ready = config / "baseline_points_m_nocov.jsonl"
    line = json.dumps({"protocol_fingerprint": "fp-current", "dir_ok": True}) + "\n"
    ready.write_text(line * 100, encoding="utf-8")
    sup.ensure_baselines(["m", "cf"], str(tmp_path))
    assert calls == [("cf", None)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_goal_target_symbols_follow_yaml_order tests/test_supervisor.py::test_ensure_baselines_asks_generate_only_for_a_missing_file -q --tb=line`

Expected: 第一则 `AttributeError: _goal_target_symbols`。不要为了让第二则先跑而去掉第一则。

- [ ] **Step 3: Load the goal, then pass its symbols**

```python
def _goal_target_symbols(goal):
    cad = (goal or {}).get("cadence") or {}
    raw = cad.get("target_symbols") or []
    out = []
    seen = set()
    for item in raw:
        sym = str(item).lower().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out
```

`_main_locked` 开头现在是先 `ensure_baselines(GOAL_SYMBOLS_SET, args.root)`，那时 goal 还没读。改成：

```python
try:
    goal_for_baselines = load_goal(args.goal)
    ensure_baselines(_goal_target_symbols(goal_for_baselines), args.root)
except Exception as e:
    print(f"[ERROR] ensure_baselines pre-flight failed: {e}", file=sys.stderr)
```

循环里原有的 `goal = load_goal(args.goal)` 留着，热加载行为不变。不要改 `ensure_baselines` 里面的 `gbp.generate(...)` 调用，也不要在 pytest 分支里把“指标文件可读”的路径提前 return。第二则测试要证明缺文件时确实会调用一次 `generate(sym, None, root)`。

不要在这个任务里执行真实生成，也不要启动监督环。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_goal_target_symbols_follow_yaml_order tests/test_supervisor.py::test_ensure_baselines_asks_generate_only_for_a_missing_file tests/test_goal_tiers.py::test_goal_yaml_drops_old_bar_and_unbounded_budget -q --tb=short`

Expected: PASS。确认测试输出里没有 TimesFM 权重加载日志。若有，说明假模块没挡住真实导入，停下来修测试，不要继续跑生成。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_supervisor.py
git commit -m "fix(v4): preflight nocov baselines for every goal target symbol"
```

---

### Task 7: 第一次停机信号不再开新工作

**Files:**
- Modify: `scripts/praxist_supervisor.py` 的 `_signal_handler`（361 行，保持只置标志）、`_main_locked` 循环（2856 行起）、睡眠（3050 行）
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Consumes: 模块全局 `_SHUTDOWN_REQUESTED`。`_signal_handler(signum, frame)` 已有实现，不要往里面加日志或文件写。
- Produces:
  - `_shutdown_exit() -> int | None`：标志为真时发出与现在循环顶相同的 `supervisor_stopped` / `reason=signal_received` / `exit_code=0` 事件并返回 0；否则返回 None。
  - `_sleep_interruptible(seconds: int) -> None`：最多睡 `seconds` 秒，标志一旦为真就在下一次 1 秒切片前返回。
  - 任务 9 会调用 `_shutdown_exit`。

`POLL_S` 仍是 300。现在 `time.sleep` 一次睡完，处理函数又不打断睡眠，所以标志要等到下一轮循环顶才被看见。循环顶的检查在收割和 `decide_fast_loop` 之前；信号若落在这一轮已经通过检查之后，本轮仍会收割并启动快环。2026-10-02 第一次 SIGTERM 落在这一窗口里，大约 180 秒后才退出，和最多等一轮轮询相符。

开口报告 §5.2 沿用了「约 90 秒干净退出」这句期望。这句在两份 2026-10-03 报告里，不在 `docs/three_loop_restart_protocol.md`，也不在运行手册。不要加 90 秒看门狗，不要在 `_signal_handler` 里起计时器。睡眠改成 1 秒切片之后，睡眠中的信号在下一次切片返回；已经开始的收割和已经启动的子进程仍要跑完。处理函数继续只置标志。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_supervisor.py` 末尾添加：

```python
def test_sleep_returns_on_the_slice_that_sees_the_flag(monkeypatch):
    calls = []

    def _sleep(seconds):
        calls.append(seconds)
        sup._SHUTDOWN_REQUESTED = True

    monkeypatch.setattr(sup.time, "sleep", _sleep)
    sup._SHUTDOWN_REQUESTED = False
    try:
        sup._sleep_interruptible(180)
    finally:
        sup._SHUTDOWN_REQUESTED = False
    assert calls == [1]


def test_once_does_not_harvest_or_start_when_flag_is_set_after_the_top_check(
        tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    harvested = []
    started = []
    monkeypatch.setattr(sup, "_SHUTDOWN_REQUESTED", False)
    monkeypatch.setattr(sup, "ensure_baselines", lambda *a, **k: None)
    monkeypatch.setattr(sup, "build_snapshot", lambda *a, **k: {
        "variants": {}, "symbols_hit": set(), "families_hit": set(),
    })
    monkeypatch.setattr(sup, "evaluate_goal", lambda *a, **k: (False, ["not yet"]))
    monkeypatch.setattr(sup, "_read_cpu_hours", lambda: 0.0)
    monkeypatch.setattr(sup, "_read_token_m", lambda: (0.0, False))
    monkeypatch.setattr(sup, "materialize_known_verdicts", lambda *a, **k: None)
    monkeypatch.setattr(sup, "materialize_covariate_menu", lambda *a, **k: None)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "_queue_busy", lambda: False)
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)

    def _ensure_phase(st):
        sup._SHUTDOWN_REQUESTED = True
        return st

    monkeypatch.setattr(sup, "ensure_phase", _ensure_phase)
    monkeypatch.setattr(sup, "_maybe_harvest", lambda *a, **k: harvested.append("harvest") or False)
    monkeypatch.setattr(sup, "_maybe_enqueue_retests", lambda *a, **k: harvested.append("retest"))
    monkeypatch.setattr(
        sup, "decide_fast_loop",
        lambda *a, **k: started.append("start") or [{"action": "run_started"}])
    monkeypatch.setattr(sup.time, "sleep", lambda *_a, **_k: None)
    goal = tmp_path / "goal.yaml"
    goal.write_text(
        "goal:\n  success_condition: ['all_symbols_pass_phase1']\n"
        "  budgets: {max_cycles: 2000, cpu_hours: 2000, token_budget_m: 80, deadline: '2028-10-02'}\n"
        "  cadence: {survivors_per_cycle: 3, aligned_max_points: 600,\n"
        "            run_budget_hours: 1.5, quota_window_hours: 5.0, quota_margin_min: 30}\n",
        encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    try:
        rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    finally:
        sup._SHUTDOWN_REQUESTED = False
    assert rc == 0
    assert harvested == []
    assert started == []
```

`ensure_phase` 位于循环顶的标志检查之后、`_maybe_harvest` 之前。这就是 2026-10-02 第一次 SIGTERM 仍能收割并启动运行的窗口。

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_sleep_returns_on_the_slice_that_sees_the_flag tests/test_supervisor.py::test_once_does_not_harvest_or_start_when_flag_is_set_after_the_top_check -q --tb=line`

Expected: 第一则 `AttributeError: _sleep_interruptible`。第二则在函数补上之前也会因同样原因，或在只补了睡眠时 FAIL（`harvested` 非空）。

- [ ] **Step 3: Check the flag before new work, and slice the sleep**

```python
def _shutdown_exit():
    """标志为真时走与循环顶相同的干净退出。不收割，不启动新 run，不杀已经在跑的子进程。"""
    if not _SHUTDOWN_REQUESTED:
        return None
    _emit_event("critical", "supervisor_stopped", {
        "reason": "signal_received",
        "exit_code": 0,
        "uptime_s": round(time.time() - _START_TIME, 1),
    })
    return 0
```

`_shutdown_exit` 不要在 `_emit_event` 之后再调用 `_mark_stop_emitted()`，也不要再发第二条 `supervisor_stopped`。事件名是 `supervisor_stopped` 时，`_emit_event` 写完事件就调用 `_mark_stop_emitted()`（`scripts/praxist_supervisor.py` 约 323–324 行）。现循环顶 2858–2864 行就是这一形：只发 `reason=signal_received`、`exit_code=0`，然后 `return 0`，标记由 `_emit_event` 内部置上，`_atexit_handler` 看到 `_STOP_EMITTED` 后直接返回。Task 7 把这段收成函数，标记仍走同一条内部路径。

显式 `_mark_stop_emitted()` 只用于事件名不是 `supervisor_stopped` 的干净退出：`goal_reached`（2922、2977）、`budget_exhausted`（3002）、dry-run（2903）、one-shot（3048）、锁冲突（2465）。这些路径的 `_emit_event` 不会走到 324 行。测试若把 `_emit_event` 换成空函数，就不能再靠内部标记，必须像 `test_goal_reached_marks_stop_emitted` 那样自己调用 `_mark_stop_emitted()` 并断言 `_STOP_EMITTED`。Task 7 的两个新测试不替换 `_emit_event`。

```python
def _sleep_interruptible(seconds):
    """最多睡 seconds 秒。每 1 秒看一次标志。处理函数本身仍然只置标志。"""
    remaining = max(1, int(seconds))
    while remaining > 0:
        if _SHUTDOWN_REQUESTED:
            return
        time.sleep(1)
        remaining -= 1
```

循环顶现有的 `if _SHUTDOWN_REQUESTED:` 整段换成：

```python
code = _shutdown_exit()
if code is not None:
    return code
```

在预算耗尽分支调用 `_maybe_harvest` 之前加同一段 `code = _shutdown_exit(); if code is not None: return code`。

在正常路径 `if not _run_active(): _maybe_harvest(...)` 之前加同一段。这一段必须包住后面的 `_maybe_enqueue_retests`、慢环启动和 `decide_fast_loop(goal, dry_run=False)`。标志为真时直接 `return code`，不要再调用这四个里面的任何一个。`decide_fast_loop(goal, dry_run=True)` 在 `--dry-run` 分支里，那个分支本来就马上退出，不用改。

把循环末尾的 `time.sleep(max(1, sleep_s))` 换成 `_sleep_interruptible(max(1, sleep_s))`。

不要修改 `_signal_handler` 的函数体。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py::test_sleep_returns_on_the_slice_that_sees_the_flag tests/test_supervisor.py::test_once_does_not_harvest_or_start_when_flag_is_set_after_the_top_check tests/test_supervisor.py::test_dry_run_one_shot_no_sleep -q --tb=short`

Expected: PASS。dry-run 测试仍然是 0 次睡眠。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_supervisor.py
git commit -m "fix(v4): stop new harvest and new runs on the first shutdown signal"
```

---

### Task 8: 从已锁定的预注册造确认队列行

**Files:**
- Modify: `scripts/praxist_supervisor.py`（纯函数，本任务不改主循环）
- Test: `tests/test_confirmation_wiring.py`

**Interfaces:**
- Consumes: `family_key_for(symbol) -> str`。`cascade.experiment_fingerprint.build_variant_id(symbol, cov_family, experiment_fingerprint) -> str`。`dispatch_confirmation(proposal, registry, members) -> dict`，键为 `accepted`、`reason`、`run_label`、`prereg_id`、`members`、`registration`。`_experiment_fp_for(symbol, cov) -> str | None`。协变量池 `load_covariate_pool()[cov]["family"]`。XReg 自动注入的基通道名是 `daily_slope`（`cascade/realtime_regime_classifier.py` 写明第二协变量才是请求协变量）。
- Produces:
  - `_requested_covariate(prereg_row: dict) -> str | None`
  - `confirmation_queue_row(prereg_row: dict, variant_id: str) -> dict`
  - `due_confirmations(registry: list[dict], now_ts: str, blocked_ids: set[str], already_ran_ids: set[str], fingerprint_for, family_for) -> list[dict]`

`now_ts` 与 `confirm_from_ts` 都是 `YYYY-MM-DD HH:MM:SS`，按字符串比较。不要解析时区。`blocked_ids` 是已经在 pending 或 inprogress 里的 `variant_id`。`already_ran_ids` 是当前协议快照里已经出现过的 `prereg_id`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_confirmation_wiring.py` 末尾添加。测试文件若尚未导入监督环，沿用该文件已有的 `sv` 别名；若别名不同，用该文件已经在用的那个模块名，不要另引一份。

```python
def test_due_confirmation_row_uses_the_locked_preregistration():
    jd = {
        "prereg_id": "6f944c74e2c94ca5a5b70e64676e518b",
        "symbol": "jd",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 1199,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }
    sr = {
        "prereg_id": "ef908a2214e141abaa2d480ca82b53bb",
        "symbol": "sr",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 986,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vwap_deviation"]},
    }
    early = dict(jd)
    early["prereg_id"] = "too-early"
    early["confirm_from_ts"] = "2026-10-04 00:00:00"
    assert sv._requested_covariate(jd) == "vor"
    assert sv._requested_covariate({"cov_fingerprint": {"keys": ["daily_slope"]}}) is None
    due = sv.due_confirmations(
        [jd, sr, early],
        "2026-10-03 12:00:00",
        blocked_ids=set(),
        already_ran_ids=set(),
        fingerprint_for=lambda symbol, cov: "ab" * 32,
        family_for=lambda cov: "momentum",
    )
    assert [row["symbol"] for row in due] == ["jd", "sr"]
    assert due[0]["run_mode"] == "confirmation"
    assert due[0]["variant_id"] == "jd_momentum_" + ("ab" * 32)[:12]
    assert due[0]["cov_override"] == "vor"
    assert due[0]["prereg_id"] == jd["prereg_id"]
    assert due[0]["confirm_from_ts"] == "2026-10-03 00:00:00"
    assert due[0]["n_confirm_required"] == 1199
    assert due[0]["max_points"] == 1199
    assert due[0]["source"] == "confirmation"
    assert "request_early_seal" not in due[0]
    blocked = sv.due_confirmations(
        [jd], "2026-10-03 12:00:00",
        blocked_ids={due[0]["variant_id"]},
        already_ran_ids=set(),
        fingerprint_for=lambda symbol, cov: "ab" * 32,
        family_for=lambda cov: "momentum",
    )
    assert blocked == []
    ran = sv.due_confirmations(
        [jd], "2026-10-03 12:00:00",
        blocked_ids=set(),
        already_ran_ids={jd["prereg_id"]},
        fingerprint_for=lambda symbol, cov: "ab" * 32,
        family_for=lambda cov: "momentum",
    )
    assert ran == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_confirmation_wiring.py::test_due_confirmation_row_uses_the_locked_preregistration -q --tb=line`

Expected: FAIL，`AttributeError: _requested_covariate`。

- [ ] **Step 3: Implement the pure functions**

```python
_BASE_COVARIATE = "daily_slope"


def _requested_covariate(prereg_row):
    keys = ((prereg_row or {}).get("cov_fingerprint") or {}).get("keys") or []
    extra = [key for key in keys if key != _BASE_COVARIATE]
    if len(extra) != 1:
        return None
    return extra[0]


def confirmation_queue_row(prereg_row, variant_id):
    cov = _requested_covariate(prereg_row)
    n_req = int(prereg_row["n_confirm_required"])
    return {
        "variant_id": variant_id,
        "symbol": str(prereg_row["symbol"]).lower(),
        "cov_override": cov,
        "max_points": n_req,
        "stage": "aligned",
        "checkpoint_path": "",
        "enqueued_at": _now_iso(),
        "src_run": "confirmation_dispatch",
        "source": "confirmation",
        "run_mode": "confirmation",
        "prereg_id": prereg_row["prereg_id"],
        "confirm_from_ts": prereg_row["confirm_from_ts"],
        "n_confirm_required": n_req,
    }


def due_confirmations(registry, now_ts, blocked_ids, already_ran_ids,
                      fingerprint_for, family_for):
    """到期且未占用、未跑过的预注册。不入队，不读时钟，不读权重。"""
    import cascade.experiment_fingerprint as ef

    out = []
    for row in registry or []:
        if not isinstance(row, dict):
            continue
        if row.get("terminal_state") not in (None, ""):
            continue
        confirm_from = row.get("confirm_from_ts")
        if not isinstance(confirm_from, str) or confirm_from > now_ts:
            continue
        if row.get("prereg_id") in already_ran_ids:
            continue
        cov = _requested_covariate(row)
        if cov is None:
            continue
        fp = fingerprint_for(str(row.get("symbol") or "").lower(), cov)
        fam = family_for(cov)
        if not fp or not fam:
            continue
        vid = ef.build_variant_id(str(row["symbol"]).lower(), fam, fp)
        if vid in blocked_ids:
            continue
        out.append(confirmation_queue_row(row, vid))
    return out
```

不要在本任务里读生产 `preregistry.jsonl`，也不要把它写进测试期望以外的新假设。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_confirmation_wiring.py::test_due_confirmation_row_uses_the_locked_preregistration tests/test_confirmation_wiring.py::test_dispatch_accepts_locked_id_and_registers_family tests/test_confirmation_wiring.py::test_finalize_short_sample_returns_peek_audit_and_not_confirmed -q --tb=short`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_confirmation_wiring.py
git commit -m "feat(v4): build confirmation queue rows from locked preregistrations"
```

---

### Task 9: 把确认入队和终结接到主循环

**Files:**
- Modify: `scripts/praxist_supervisor.py` 的 `_main_locked` 正常路径（`_maybe_enqueue_retests` 旁边）以及慢环批次收尾
- Test: `tests/test_confirmation_wiring.py`

**Interfaces:**
- Consumes: 任务 3 的 `promote_batch_for_persistence(verdicts) -> dict[str, dict]`。任务 7 的 `_shutdown_exit() -> int | None`。任务 8 的 `due_confirmations(...) -> list[dict]`。`dispatch_confirmation(proposal, registry, members)`。`finalize_confirmation(row, members, now)`。`rl.queue_enqueue(path, rows, dead, existing) -> int`。`rl.in_flight_ids(pending, inprogress) -> set[str]`。`family_key_for(symbol)`。
- Produces:
  - `load_preregistry(path) -> list[dict]`
  - `load_family_members(path) -> list[dict]`，同一 `variant_id` 后写覆盖前写
  - `save_family_members(path, members) -> None`
  - `_maybe_enqueue_confirmations(log, now_ts) -> int`
  - `_finalize_confirmation_verdict(verdict, members, now) -> dict | None`

主循环在任务 7 的停机守卫之内、`_maybe_enqueue_retests` 之后调用 `_maybe_enqueue_confirmations`。不要另写 cron、线程或新的选假设规则。

- [ ] **Step 1: Write the failing test**

在 `tests/test_confirmation_wiring.py` 末尾添加：

```python
def test_enqueue_due_confirmation_then_peek_does_not_seal(tmp_path, monkeypatch):
    prereg_path = tmp_path / "preregistry.jsonl"
    family_path = tmp_path / "family_registry.jsonl"
    queue_path = tmp_path / "pending.jsonl"
    jd = {
        "prereg_id": "6f944c74e2c94ca5a5b70e64676e518b",
        "symbol": "jd",
        "registered_at": "2026-10-02T00:00:00+00:00",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 1199,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }
    prereg_path.write_text(json.dumps(jd) + "\n", encoding="utf-8")
    monkeypatch.setattr(sv, "PREREGISTRY_PATH", str(prereg_path))
    monkeypatch.setattr(sv, "FAMILY_REGISTRY", str(family_path))
    monkeypatch.setattr(sv, "QUEUE", str(queue_path))
    monkeypatch.setattr(sv, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sv, "_experiment_fp_for", lambda symbol, cov: "ab" * 32)
    monkeypatch.setattr(sv, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sv, "_active_protocol_snapshot", lambda path: {})
    n = sv._maybe_enqueue_confirmations(str(tmp_path / "decisions.jsonl"), "2026-10-03 12:00:00")
    assert n == 1
    queued = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert queued[0]["run_mode"] == "confirmation"
    assert queued[0]["max_points"] == 1199
    members = sv.load_family_members(str(family_path))
    assert len(members) == 1
    assert members[0]["status"] == "registered"
    # 同一 vid 已在队里，第二轮不再入队，也不抢占。
    assert sv._maybe_enqueue_confirmations(str(tmp_path / "decisions.jsonl"), "2026-10-03 12:00:00") == 0
    verdict = {
        "variant_id": queued[0]["variant_id"],
        "run_mode": "confirmation",
        "prereg_id": jd["prereg_id"],
        "n": 10,
        "n_confirm_required": 1199,
        "p_value": 0.01,
        "gate_pass": True,
        "dm_status": "set_mismatch_descriptive",
        "missingness_admissible": False,
    }
    out = sv._finalize_confirmation_verdict(verdict, members, datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert out["audit"]["event"] == "no_peek_rejected"
    assert out["sealed"] is False
    assert out.get("fdr_pass") is not True
    assert out["run_label"] != "confirmed"
```

该测试文件需要 `json`、`datetime`、`timezone`。若文件顶部还没有，只补缺的导入。

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_confirmation_wiring.py::test_enqueue_due_confirmation_then_peek_does_not_seal -q --tb=line`

Expected: FAIL，`AttributeError: _maybe_enqueue_confirmations` 或 `PREREGISTRY_PATH`。

- [ ] **Step 3: Persist family members, enqueue, and peek**

```python
PREREGISTRY_PATH = os.path.join(FM_ROOT, "task_FM", "config", "preregistry.jsonl")


def load_preregistry(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_family_members(path):
    by_vid = {}
    order = []
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            member = json.loads(line)
            vid = member.get("variant_id")
            if vid not in by_vid:
                order.append(vid)
            by_vid[vid] = member
    return [by_vid[vid] for vid in order]


def save_family_members(path, members):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for member in members:
            fh.write(json.dumps(member, ensure_ascii=False) + "\n")


def _maybe_enqueue_confirmations(log, now_ts):
    registry = load_preregistry(PREREGISTRY_PATH)
    blocked = rl.in_flight_ids(QUEUE, INPROGRESS)
    snap = _active_protocol_snapshot(REGISTRY)
    already = {
        v.get("prereg_id") for v in (snap or {}).values()
        if isinstance(v, dict) and v.get("prereg_id")
    }
    pool = load_covariate_pool()

    def family_for(cov):
        return (pool.get(cov) or {}).get("family")

    rows = due_confirmations(
        registry, now_ts, blocked, already, _experiment_fp_for, family_for)
    produced = {row["prereg_id"] for row in rows}
    for src in registry:
        if not isinstance(src, dict) or src.get("terminal_state") not in (None, ""):
            continue
        confirm_from = src.get("confirm_from_ts")
        if not isinstance(confirm_from, str) or confirm_from > now_ts:
            continue
        if src.get("prereg_id") in already or src.get("prereg_id") in produced:
            continue
        _log_decision(log, "confirmation_not_enqueued",
                      src.get("prereg_id") or "",
                      [str(src.get("symbol") or "")])
    if not rows:
        return 0
    added = 0
    members = load_family_members(FAMILY_REGISTRY)
    for row in rows:
        proposal = {
            "prereg_id": row["prereg_id"],
            "symbol": row["symbol"],
            "variant_id": row["variant_id"],
            "family_key": family_key_for(row["symbol"]),
        }
        decision = dispatch_confirmation(proposal, registry, members)
        if not decision["accepted"] or str(decision.get("registration") or "").startswith("rejected"):
            _log_decision(log, "confirmation_rejected",
                          decision.get("reason") or decision.get("registration") or "",
                          [row["variant_id"]])
            continue
        members = decision["members"]
        n = rl.queue_enqueue(QUEUE, [row], dead=set(), existing=set())
        added += n
        if n:
            _log_decision(log, "confirmation_enqueued", row["prereg_id"], [row["variant_id"]])
    save_family_members(FAMILY_REGISTRY, members)
    return added


def _finalize_confirmation_verdict(verdict, members, now):
    """样本未满只 peek。不把 fdr_pass 写成 True，不设 request_early_seal。"""
    if not isinstance(verdict, dict) or verdict.get("run_mode") != "confirmation":
        return None
    row = dict(verdict)
    if row.get("n_confirm_actual") is None:
        row["n_confirm_actual"] = row.get("n") if row.get("n") is not None else 0
    if row.get("n_confirm_required") is None:
        return None
    row["request_early_seal"] = False
    return finalize_confirmation(row, members, now)
```

`queue_enqueue` 自己还会对 pending 文件去重。`blocked_ids` 已经含 inprogress，所以第二轮 `due_confirmations` 返回空。`existing=set()` 是故意的：探索裁决的 `variant_id` 相同，不能把它放进 `existing`，否则确认行永远进不了队。pending/inprogress 的占用由 `blocked_ids` 负责，并打日志，不要改写已有的探索队列行。

在 `_main_locked` 里，`_maybe_enqueue_retests` 的 try 块之后、停机守卫尚未返回的位置加：

```python
try:
    _maybe_enqueue_confirmations(log, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
except Exception as e:
    _log_decision(log, "confirmation_enqueue_error", str(e))
```

若任务 7 的守卫是整段 `return`，这段必须写在守卫后面、且和复测同一层：标志已为真时函数已经返回，不会执行到这里。

在慢环批次 `promote_batch_for_persistence` 之后、清理 worker 之前，对 `batch_verdicts` 里 `run_mode==confirmation` 的行调用 `_finalize_confirmation_verdict`。成员表用 `load_family_members(FAMILY_REGISTRY)`，把返回的 `members` 再 `save_family_members`。不要根据返回值写 `fdr_pass`。`n_confirm_actual < n_confirm_required` 时结果是 peek，`sealed` 为 False。

不要把 `missingness_admissible` 设为 True。不要调用慢环，不要加载模型。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_confirmation_wiring.py::test_enqueue_due_confirmation_then_peek_does_not_seal tests/test_confirmation_wiring.py::test_due_confirmation_row_uses_the_locked_preregistration tests/test_confirmation_wiring.py::test_finalize_short_sample_returns_peek_audit_and_not_confirmed tests/test_supervisor.py::test_once_does_not_harvest_or_start_when_flag_is_set_after_the_top_check -q --tb=short`

Expected: PASS。停机测试仍然不入队。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_confirmation_wiring.py
git commit -m "feat(v4): enqueue due confirmations and peek until the sample is full"
```

不要 push。不要启动监督环。

---

## 覆盖核对

| 开口 | 落在 |
|---|---|
| 运行手册仍写 0.51、三阶段、999999、2099-12-31 | 任务 1 |
| 复测夹具缺 `protocol_fingerprint`，含两则假绿 | 任务 2 |
| `write_first_preregistry.py` 未挂账 | 任务 2，只进 `TEMPORARY_ALLOWLIST` |
| 探索行或描述性 DM 落下 `fdr_pass=True` | 任务 3 |
| `term_structure` 被描述性失败杀死；`min_ok` 仍是 4 | 任务 4 |
| cf/i/p/sh/ma 没有当前协议无协变量基线却能占座 | 任务 5 |
| 预检只覆盖 `GOAL_SYMBOLS_SET` 的 9 个品种 | 任务 6，真实生成留到维护窗口 |
| 第一次 SIGTERM 后仍收割并启动快环 | 任务 7。不加 90 秒看门狗 |
| `dispatch_confirmation` / `finalize_confirmation` 没有主循环调用者 | 任务 8 和任务 9 |
| 开口报告 §2：确认要 1.2–2.0 年 | 任务 1 的运行手册句子。不新造季度调度，不改 1199 / 986，不改 Δ\*=0.08 |
| 开口报告 §1.1 把死亡计数说成 `pass_variants()` | 不改调用。任务 4 的 pass 计数仍是 `gate_pass`。杀死族的测试行全部是 `run_mode=exploration` |
| 开口报告 §1.4：`min_ok` 提到约 30、等确认记录、确认产出为 0 时豁免死亡 | 明确不做 |
| 开口报告 §1 表：`no_failure_delta` 与候选 123→67 | 本计划不改或规则。任务 4 被实际收割过至少一轮后复测；曲线仍下滑再议 |
| 开口报告 §3：预注册 `cf_calendar` 和两条自指命中 | 明确不做 |
| 开口报告 §5.3：农产品 5/10 | 明确不做。断路器保持全板块才切断。p 的缺基线在任务 5 和任务 6 |
| 开口报告 §4：star 勘误 | 明确不做。不改历史 changelog |
| §7.8、6 条 REVIEW_CANDIDATES、Phase 3 数值门槛、token 上限、提高 top_k、扩大 `sector_map`、勾选任务 E | 明确不做 |
