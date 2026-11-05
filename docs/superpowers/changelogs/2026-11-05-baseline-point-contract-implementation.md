# Changelog: Baseline Point Contract 实施 + Laya 事故全修复

> 时间跨度：2026-11-02 08:00 ~ 2026-11-05
> 涉及 agent：opus analyst, sonnet code-reviewer/scientist/tracer/analyst/adversarial-reviewer × 12 executor, 主 session 协调
> Plan 文件：`docs/superpowers/plans/2026-11-03-baseline-point-contract-plan.md`
> Spec 文件：`docs/superpowers/specs/2026-11-03-baseline-point-contract-spec.md`
> 调查报告：`docs/superpowers/reports/2026-11-03-baseline-audit-dir-ok-jd-report.md`（§1-§11, 794 行）
> 运维说明：`docs/superpowers/reports/2026-11-03-jd-baseline-operator-note.md`（5 步 Rollout）

## TL;DR

从一次日常三环工作检查出发，发现 Laya 预筛 503 刷屏（4870 条错误）。取证发现是备份机 cleanup commit (`dbb68b5`) 误删 P1-P3 改进 + 本机 merge (`6aadfe9`) 误接受代码回退。修复过程中发现：
1. 基线重生是全量（慢）→ 集成 `incremental_baseline.py` 到 `ensure_baselines` 路径 ③
2. 增量脚本有 bug（588 点丢失）→ 修合并逻辑
3. Scientist 审核发现 dir_ok 不一致 6.25%（883 行）+ jd 死循环（永远 3 行）
4. Tracer 追溯根因：`monthly_backtest.py:566` 写入加权 `delta_pred`，但 `dir_ok` 用 endpoint
5. 我们最初的修复（改 `delta_pred` 为端点）与已有 plan `2026-11-03-baseline-point-contract-plan.md` 的 Global Constraints #1 **直接冲突**
6. 回滚 + 严格按 plan 执行 11 个 task，3 天完成 PR1+PR2+PR3，plan 全部闭环

**最终成果**：7 个关键函数按 plan 实现，124+ 测试通过，旧守卫彻底清除，jd 死循环用网格后条件根治。

## 关键设计决策（plan 约束）

1. **保留 `delta_pred` 加权语义**：不采用方案 A（覆盖成端点）。`delta_pred` 继续是加权可交易增量，覆盖成端点会改 PF/EV/MaxDD。
2. **新增 `endpoint_delta` + `position_sign` 两字段**：新行追加，旧行不回填。
3. **`tradable_sign` 下游兼容**：优先读 `position_sign`，缺键退回 `sign(delta_pred)`，向后兼容旧行。
4. **`baseline_jsonl_record` 单一投影**：两个 writer（全量/增量）都调它，杜绝实现漂移。
5. **`accept_baseline_file` 单一后条件**：严格匹配网格 + 指纹，不允许超集/子集/疤痕。
6. **`finalize_baseline_write` 两次收口**：增量 → 全量 → 失败记停滞。
7. **旧守卫 `_guard_confirm_from_ts_after_regen` 彻底删除**：jd 死循环根因。
8. **协议指纹不升级**：保持 v4 `f02b2a43`。

## 完整 commit 链

### Phase 0：Laya 事故修复（2026-11-02）

| Commit | 描述 | 测试 |
|---|---|---|
| `54b06c5` | revert: restore P0-B fail-fast + slow-loop warmup/docs (NOT typesafe_prescreen) | - |
| `cf2a149` | harden: Laya prescreen SKIP_AUTH + time-driven warmup + health check (re-impl) | 43/43 |
| `b2c780c` | chore: add .gitattributes protected-ours driver + backup merge protocol | - |
| `bf3addc` | follow-up: extend protected-ours to data/config.py + update runbook | - |

### Phase 1：基线重生优化 + bug 修复（2026-11-02 ~ 2026-11-03）

| Commit | 描述 | 测试 |
|---|---|---|
| `faa9dba` | perf: ensure_baselines 路径 ③ (reanchor) 改增量重生 | - |
| `4c4d704` | fix: incremental_baseline 合并 resumed_points 到写入文件 | - |

### Phase 2：Scientist 审核 + 根因追溯 + 报告（2026-11-03）

| Commit | 描述 |
|---|---|
| `5528143` | docs: 基线数据完整性审核报告（初版） |
| `d51a3bb` | fix: monthly_backtest.py:566 delta_pred 改用 endpoint 与 dir_ok 对齐 ← **被 plan 拒绝，已回滚** |

### Phase 3：回滚 + 严格按 plan 执行（2026-11-04 ~ 2026-11-05）

| Commit | 描述 | 测试 | Plan Task |
|---|---|---|---|
| `cbd4187` | revert: monthly_backtest.py:566 + restore 21 weighted baselines | - | - |
| `7a12008` | move endpoint_dir_ok into signal_contract and re-export it | 7/7 | Task 1 |
| `04d7d7e` | assemble endpoint dir_ok separately from the weighted position | 9/9 | Task 2 |
| `9b101bc` | score economic direction from position_sign when the point has it | 2/2 | Task 3 |
| `3c7bb28` | project baseline rows once and merge resume payloads on their own | 11/11 | Task 4 |
| `339bd20` | give every dir_ok field the endpoint owner | 3/3 | Task 5 |
| `2c2c778` | move the eval grid next to the backtest and keep its right bound | 10/10 | Task 6 |
| `c21bff0` | accept a baseline only when its cutoffs equal the injected grid | 13/13 | Task 7 |
| `6e866b2` | keep a failed baseline publish off the live filename | 5/5 | Task 8 |
| `beba66a` | reuse only current-grid baseline rows when extending a file | 4/4 | Task 9 |
| `04a9cb6` | accept or keep the live baseline with one post-condition | 49/49 | Task 10 |
| `da4abb7` | lock jd and sr to one baseline post-condition and record the operator steps | 11/11 | Task 11 |

### Phase 4：最终报告 + F1 修复 + 数据更新（2026-11-05）

| Commit | 描述 |
|---|---|
| `bdefc7d` | chore: F1 修复（dynamic import → top-level）+ plan/spec 权威源 + 基线数据更新 |
| (本 changelog) | 完整会话记录 |

## 关键函数清单

| 函数 | 文件 | 行号 | 描述 |
|---|---|---|---|
| `endpoint_dir_ok` | `cascade/signal_contract.py` | 37 | 端点方向判定（零变动判假）|
| `assemble_direction` | `cascade/signal_contract.py` | 123 | 返回 4 键 dict（分离加权/端点/方向）|
| `tradable_sign` | `cascade/evaluation_metrics.py` | 178 | 经济指标方向（优先 position_sign）|
| `baseline_jsonl_record` | `cascade/baseline_paths.py` | 19 | 唯一基线行投影（可选键不写 null/0）|
| `baseline_eval_cutoffs` | `cascade/eval_grid.py` | 74 | 当前网格 cutoff 序列（空抛 RuntimeError）|
| `accept_baseline_file` | `cascade/eval_grid.py` | 99 | 后条件：严格匹配网格 + 指纹 |
| `finalize_baseline_write` | `scripts/sup_evidence.py` | 1405 | 唯一收口（两次收口逻辑）|
| `_incremental_or_regen` | `scripts/sup_evidence.py` | 1518 | 增量 → 全量 → 失败记停滞 |
| `ensure_baselines` | `scripts/sup_evidence.py` | 1620 | 重写：单后条件 + 网格失败 continue |

## 删除项

- `_guard_confirm_from_ts_after_regen`（旧守卫，jd 死循环根因）
- `scripts/praxist_supervisor.py` `_HOMES` 中的 `_guard_confirm_from_ts_after_regen` 引用
- `_baseline_reanchor_reason` 调用（`ensure_baselines` 不再用）
- 「推进不足 7 天就 `_remember_stall`」逻辑

## 数据状态

| 项 | 值 |
|---|---|
| 品种数 | 24 |
| 总行数 | ~14,000 |
| 协议指纹 | v4 `f02b2a433fd572ea...`（不变）|
| 旧行 `endpoint_delta` | 无（零回填）|
| 旧行 `position_sign` | 无（零回填）|
| 下游 `tradable_sign` 行为 | 旧行 → `sign(delta_pred)`（加权，向后兼容）|

## 测试结果

| 测试集 | 通过 |
|---|---|
| Plan Task 1-11 各自测试 | 124+ |
| Scientist 审核（24 品种终验）| 加权状态，符合 plan 预期 |
| Code-reviewer 审核（7 关键函数）| 7/7 OK |
| F1 修复（`short_variety_diagnostic.py` 动态导入）| import OK |

## 运维下一步（按 `2026-11-03-jd-baseline-operator-note.md`）

1. **重启 supervisor**：plan 约束是执行过程中不重启，现已允许
2. **观察 ensure_baselines**：
   - 23 个品种当前基线符合新后条件 → 验收通过，不写
   - jd 当前 3 行不通过 → 触发 `_incremental_or_regen`
     - 第一次收口（增量）：网格失败（jd 活文件只有 3 行，网格要求 ~588 行）
     - 第二次收口（全量 `generate(finalize=False)`）：加载 TimesFM 权重计算 jd 网格
3. **成功判据**：`baseline_points_jd_nocov.jsonl` cutoff 序列等于 `baseline_eval_cutoffs("jd")`，指纹仍 v4
4. **不要做的事**：
   - 不要手删 `baseline_points_jd_nocov.jsonl`（旧守卫会拷回疤痕）
   - 不要把 `archive_20260929T1500.jsonl` 拷到活文件
   - 不要运行 `scripts/restart_three_loop_clean.sh`

## 遗留项

- ⏸ Laya 后端间歇 503（自动恢复，根因未查）
- ⏸ 备份机 merge driver（需用户 SSH 到 `chong@100.96.19.116` 手动注册 `merge.protected-ours` driver）
- ⏸ `aligned_verdicts.jsonl` 历史 verdicts PF/EV 偏移（预期行为，详见报告 §9.7）

## 不做的事

- ❌ 不重跑 21 品种（plan Global Constraint #2：不为 dir_ok 重生品种）
- ❌ 不升级协议指纹到 v5（plan Global Constraint：不引入第五版）
- ❌ 不回填旧行 `endpoint_delta`/`position_sign`（plan Global Constraint #3：旧行不必回填）
- ❌ 不修改 `calc_prediction_quality` / `neutral_ab_report` / `vol_gating_replay`（plan Global Constraint #10）
- ❌ 不为 jd 写特例代码（plan Global Constraint #6：jd 与 sr 不是两套代码）

## 文档索引

| 文档 | 路径 |
|---|---|
| Plan | `docs/superpowers/plans/2026-11-03-baseline-point-contract-plan.md` |
| Spec | `docs/superpowers/specs/2026-11-03-baseline-point-contract-spec.md` |
| 调查报告 | `docs/superpowers/reports/2026-11-03-baseline-audit-dir-ok-jd-report.md` |
| 运维说明 | `docs/superpowers/reports/2026-11-03-jd-baseline-operator-note.md` |
| Backup merge 协议 | `docs/BACKUP-MERGE-PROTOCOL.md` |
| .gitattributes | `.gitattributes`（protected-ours driver 保护 4 路径）|

## 致谢（参与 agent）

- Opus analyst：dbd68b5 误删取证
- Sonnet code-reviewer：4 commit 修复审核 + Plan 执行后全面审核
- Sonnet scientist：24 品种基线完整性审核
- Sonnet tracer：dir_ok 不一致根因追溯
- Sonnet analyst：下游影响评估
- Opus adversarial-reviewer：Plan + §9 审核（发现"实际只需改 1 行"）
- Sonnet executor × 12：Plan Task 1-11 执行（多次 429 resume）
- 主 session：协调 + 报告撰写
