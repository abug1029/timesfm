# v4 收口阶段 2 完成 + 阶段 3 启动 Changelog

**Date:** 2026-10-01
**Plan:** `docs/superpowers/plans/2026-09-30-v4-convergence-implementation-plan.md`
**Commits:** `e37e5c6` → `0015b00` → `bc6a9fb` → `c0e3aa4` → `7977d78` → `c3ae196`
**Spec:** §4.3 W3（预注册与前向确认）· §4.6（品种分级）· §1.4（双运行模式）
**裁定:** Q7 (a′) —— Δ\*=0.08、功效 80%、单侧 α=0.05、N(品种)=途径 B 实测 986–1,199 点

---

## 一、阶段 2 代码批次（2.4 / 2.7 生产接线）

`c0e3aa4` —— supervisor 侧两处接线，测试 +4，全量基准 **1557/0/6/1**。

| 项 | 内容 |
|---|---|
| P2 `_experiment_fp_for(symbol, cov)` | 实验指纹唯一家接线：weights=get_timesfm_model_path（与 evaluator 同源）、target=DataStore 1H `close_price` 逐品种缓存、`CONTEXT_BARS/HORIZON/STEP`+`[cov]` → `compute_experiment_fingerprint`；任一环不可解析 → `None` fail-visible |
| P4 harvest_proposals :1519 | family 前移到实际推导（pool 优先 → 提案 `covariate_family` 兜底 → 空则 `family_unresolved` 拒收计数）；vid = `build_variant_id` |
| P3 harvest_survivors :663 | 同一接线（`resolve_cov_family({"cov_override": cov})` 实池口径）；fp 不可得静默跳过（诊断路，不阻断） |
| P5 :1219 | **repeat penalty join 键保持旧式 `symbol_cov`** —— 与快环 `shared_findings.variant_name` 的 join 键，改实验身份会静默杀死惩罚 |
| 2.7 注释 | :536 pass_variants 注释 + :728 报告头去 migrated_pass；:836 报表 display-only 保持 |

**过渡语义裁定**：协议过滤（方案 A）已决定重生波语义 —— 过渡期 dead/passing/existing 集均空，dedup 波后自愈，无需双键死集合；旧 vid checkpoint 成孤儿（磁盘垃圾非正确性）。

**生产首验**（重启后首 tick 实测）：入队 vid = `sh_momentum_f8bc3e69c749` / `sr_volatility_3ede6200c5bd`，格式 `{symbol}_{family}_{fp12}` —— family 实池解析（rsi6→momentum、vor→volatility）、fp 真实计算、请求名退居 `cov_override` 可读字段。

---

## 二、2.9 一次重启（three_loop_restart_protocol）

**readiness 6/6 通过** → supervisor **PID 418**（11:09 启动，13:17 起心跳）→ v4 协议指纹 `f02b2a433fd572ea…` 上线。

### 2.1 ensure_baselines 重生波 9/9 全带 v4 落章

| 品种 | dir_acc | endpoint_mape | 备注 |
|---|---|---|---|
| cj | — | — | 首个完成（PID 393 时期落章，PID 418 恢复时**跳过**，可恢复设计实证） |
| eg | 0.446 | 10.44 | |
| **fu** | **0.448** | **27.60** | **入集后首个有效基线**；mape 偏高列为观察项 |
| jd | 0.457 | 13.78 | |
| lh | 0.462 | 8.97 | |
| m | 0.444 | 5.94 | |
| rb | 0.471 | 3.18 | |
| sr | 0.544 | 3.42 | |
| ss | 0.513 | 5.11 | |

**fu 的历史包袱被正确识别**：9/30 宿主 PID 40186 的 fu 重生中断于 351/589，留下 v2 指纹基线 → 本波判 `(bd851c9c != f02b2a43)` 跨协议不可比 → 完整重生（不是"只有 cj 需重生"的 P1 误判重演）。

### 2.2 WSL VM 回收事件（PID 393 被杀 → 幂等续跑）

PID 393 于 ~10:30 在 eg 重生 201/589 处被 WSL VM 回收击杀：无 traceback、无 Windows 睡眠事件、VM 10:32:46 重启。诊断：无 `.wslconfig`（默认 60s vmIdleTimeout）、会话间隙 `/tmp` 清空是 VM 回收实证、后台进程通常维持 VM（PID 670 曾存活过夜）。

**处置**：重跑 `scripts/start_supervisor.sh` → PID 418 从 eg 续跑（cj 持久化跳过）→ **波可恢复设计得到生产实证**（重生波幂等性此前只有代码层论证）。

### 2.3 活跃视图 v4 干净（只读检查）

```
当前协议指纹: f02b2a433fd572ea…
registry 总行数: 188 = 143 legacy(无指纹) + 27 v2(bd851c9c) + 18 v3(91ab913e)
活跃视图 (only_protocol=v4): passing=0, dead=0
```

v4 裁决从零累积；首条 v4 行 `p_inventory_bf6661363084`（pf=f02b2a43）已落，**2.4 生产链路（vid 诞生→入队→裁决行）端到端走通**。

---

## 三、2.9 收尾（`7977d78` + `c3ae196`）

| 项 | 内容 |
|---|---|
| regen 三件套归档 | `regenerate_all_baselines.py` / `regen_rb.py` / `monitor_rb_regen.sh`（3 文件 153 行）git mv → `scripts/archive/2026-09-30-dead-code/`；ensure_baselines 内建重生为唯一路径，三件套互引边整体消亡 |
| TEMPORARY_ALLOWLIST 释放 | 释放为空（`test_stale_list_entries` 时效性语义行使）；REVIEW_CANDIDATES 6 件复核条件达成，待宿主裁定 |
| 计划文档 | 2.9 执行日志 + 补账 2.8/2.10（`e37e5c6` / 0015b00 内含）+ P1-4 映射行收口 |
| STATE.md | 头行 10-01；三环状态块换 v4 证据块；Stage 3「未做」注记；PR-B1 行 ⚠️→✅ |
| 工作区 AGENTS.md | FM_a 行追加 v4 收口（阶段 2 完成并重启）段 |
| agent 记忆 | MEMORY.md 加 10-01 行（60 行纪律内以最旧行置换）+ fm-ops.md 状态块重写至 PID 418 / v4 / 188 行 |

---

## 四、阶段 3 启动（PR-D1 / PR-D2）：设计定型

### 4.1 现有基础设施盘点（决定 PR-D1 工作量远小于预期）

| 已有 | 位置 | 状态 |
|---|---|---|
| family 全套记账 | `cascade/research_family.py`（PR-C2） | `FAMILY_CLOSE_AFTER=90d` / `FAMILY_MAX_MEMBERS=20` / `T_MAX=180d` / `research_target_hash` / `family_bh_fdr` / `seal_family` 全部在位 |
| supervisor family 包装 | `praxist_supervisor.py:142-172` | **已 import + 已包装，但无调用点** —— 正是 PR-D1 的接线对象 |
| verdict run_mode | `evaluator.build_summary(run_mode="exploration")` + registry_lib `RUN_MODES` | 逐行落盘已通；当前全部探索行（`run_label=exploratory_unconfirmed`） |
| 保守默认 | `pairing_valid=False` / `missingness_admissible=False`（§7.8 裁定前恒 False）/ `fdr_pass=None` | spec v12 降级约束在位 |
| symbol_status.json | `task_FM/config/symbol_status.json` | **已清空**（`{"symbols": {}}`），无存活读者（仅 archive 内 A2 遗留引用） |
| n_required | `cascade/statistical_tests.py:568` | `(var_d, vif, z_alpha, z_beta, delta)`；途径 B 传 `vif=1.0` 防重复调整 |

### 4.2 关键设计决策（本轮勘查得出，均已核对代码）

1. **eval_start_ts 参数缺失**：`run_symbol_backtest` 只有 `eval_end_ts`（尾部窗口 `max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)`），确认集需要新增 `eval_start_ts`。切片方向 `eval_indices[:max_points]` = **取前 n** —— 与 test 68「确认集 = 预定序列中 >= confirm_from_ts 的点」天然一致，无需改语义。
2. **确认行必须隔离 checkpoint**：checkpoint 按 `variant_id` 分文件，慢环 resume 会把探索点混进确认集（污染 DM）。确认行用 `{vid}__prereg_{prereg_id[:8]}.jsonl` 命名空间（与消融批次"必须用不同 variant_id"同型先例）。
3. **n_confirm_required 逐品种**：用生产 `n_required(var_d=Var_LR, vif=1.0, delta=0.08)` 复算 Q7 表全部吻合（jd 1,199 / m 1,021 / rb 1,182 / sr 986 / ss 1,115；无实测品种取保守默认 1.240 → 1,199）。
4. **run_label 写时口径**：确认 verdict 写时落个体结论 ∈ {confirmed, refuted, underpowered}；**成功判定仍走 `pass_variants` 严格链**（含 `fdr_pass`，只由 family 封账盖章）—— 个体"confirmed"≠ 计入目标。
5. **goal 阈值硬编码在 build_snapshot**，yaml 的 `phase_definitions` 只是文档摆设（真判据 = snapshot 布尔名）。PR-D2 的重写对象是 `build_snapshot` 的 per-symbol 判定 + `all_symbols_pass_phase*` 布尔族。
6. **预算是真强制**（`max_cycles` / `cpu_hours` / `token_budget_m` / `_deadline_passed`），999999 无界与预注册纪律直接冲突（spec W3.6④）；goal 每轮热重载，改预算不需重启。

### 4.3 首批确认假设（Q7 §3.4 观察带）

| 品种 | 协变量 | 探索 d_mean | z | n_confirm_required | 预计日历 |
|---|---|---|---|---|---|
| jd | vor | **+0.078** | +1.63 | 1,199 | ~2.0y |
| sr | vwap_deviation | +0.063 | +1.51 | 986 | ~1.2y |

两者跨品种 = 跨 family（spec：默认一个品种 = 一个研究问题 = 一个 family）。确认集 = 注册后新到 cutoff（探索的 588 点全部已观察，不得入确认集）。

---

## 五、状态快照（收尾时点）

| 项 | 值 |
|---|---|
| supervisor | PID 418，运行中，phase=slow，慢环消费 sh/sr 变体 |
| 协议指纹 | v4 `f02b2a43…`（v3 `91ab913e`、v2 `bd851c9c`） |
| registry | 189 行 = 188 跨协议旧行（活跃视图空）+ 1 条 v4 行 |
| 基线 | 9/9 v4（含 fu 首个） |
| git HEAD | `c3ae196`（工作树仅 `m third_party`） |
| 测试基准 | 1557/0/6/1 |
| 待宿主 | REVIEW_CANDIDATES 6 件裁定；fu mape 观察项 |

### 23:00 校准快照（supervisor 续跑 11h50m 后）

写入时快照（§五）为 15:00 时点；23:00 复核时 v4 裁决已实质累积，一并固定：

| 项 | 值 |
|---|---|
| supervisor | PID 418 存活 11h50m，心跳 `2026-10-01T23:00:56`（run_id 7d5d85f0c5dd） |
| registry | **203 行 = 188 跨协议旧行 + 15 条 v4 行**（`active=15/192`，排除 v3 91ab913e） |
| v4 行分布 | 品种 sr 6 / jd 3 / m 3 / sh 2 / p 1；family momentum 5 / inventory 4 / term_structure 3 / volatility 3 |
| gate_pass | 3/15 True；top：`sh_momentum_3bd3de5a6fd8` dir_acc=0.564、`sh_momentum_f8bc3e69c749` 0.55、`p_inventory_bf6661363084` 0.531 |
| run_mode | 15/15 = `exploration`（确认机制尚未实施，符合预期） |
| 活跃视图 passing | 0（无 fdr_pass → 严格链不认，符合 W3.4） |
| 队列 | `aligned_pending.jsonl` 0 行（首波两行已消费完） |

**观察项（非 blocker）**：
1. **star 字段全为 None**（15/15 v4 行）——v3 行的 2★ 评级来源与 v4 行的差异待查（疑与 `meets_min_info`/多字段门槛相关）；不影响 gate_pass 判定。
2. **agri 板块降级告警**：`Sector partial degradation: agri has 5/10 symbols failed (50%). Approaching circuit-breaker` ——circuit-breaker 仅在板块全集失败时拦（提案饿死红线防护），5/10 未触发拦截，提案流未断；列入下轮巡检。
3. 对方 agent commit `f0f33d4`（v3→v4 文档同步，仅动 dead-code-spec-review + three_loop_workflow）与我方 `b2cf4dd` 无重叠。

## 六、下一步（阶段 3 实施，尚未落码）

- **A** `scripts/preregistry.py` 纯逻辑 + `tests/test_preregistry.py`（tests 37/38/40/44/68 + (a′) golden）
- **B** `eval_start_ts` + 慢环透传（run_mode/prereg_id/命名空间）+ supervisor 确认分派 + 终结解析 + family 接线 + 测试
- **C** PR-D2：`build_snapshot` 分级重写（n_confirmed_variants / 三档派生 / 0.51 退役）+ goal yaml 有界预算 + symbol_status 退休 + 测试
- **D** 首批预注册落 `preregistry.jsonl` + Phase 3 TODO spec + 计划日志
- **E** 三环一次重启加载新代码（确认集需 ~1.2–2.0y 累积，重启安全）