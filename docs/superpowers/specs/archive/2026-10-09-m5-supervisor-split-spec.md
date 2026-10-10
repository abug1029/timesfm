> **Superseded by S1 v3.0, do not implement**

# M5: praxist_supervisor.py 模块拆分 SPEC

| 字段 | 值 |
|------|-----|
| **ID** | M5 |
| **日期** | 2026-10-09 |
| **作者** | Architect Agent |
| **状态** | Draft -> 待实施 |
| **前置依赖** | D4/D5（已完成） |
| **目标文件** | scripts/praxist_supervisor.py（4574 行） |
| **风险等级** | 高（核心运行时，141 个测试文件引用） |

---

## 1. 现状分析

### 1.1 文件概况

| 指标 | 值 |
|------|-----|
| 总行数 | 4574 |
| 函数总数 | 160（124 private + 36 public） |
| 类数 | 0 |
| 测试引用 | 141 个测试文件（test_supervisor.py 独占 1873 行 / 155 次 sup. 调用） |
| 外部导入 | registry_lib, goal_dsl, cascade.cov_family, cascade.experiment_fingerprint, search_trees, search_promote, cascade.statistical_tests |

### 1.2 功能分区扫描

通过对 160 个函数的行号分布、调用关系和职责分析，识别出以下 10 个逻辑域：

| 域 | 行号范围 | 函数数 | 职责 |
|----|----------|--------|------|
| A. FDR 与持久化 | 28-59 | 2 | fdr_pass_persistable, promote_batch_for_persistence |
| B. Praxist 二进制解析 | 60-82 | 2 | _resolve_praxist_bin, _praxist_bin, _praxist |
| C. 环境与配置 | 95-191 | 2 | _load_dotenv, _check_required_env |
| D. 研究家族管理 | 192-428 | 10 | family_key_for, register_family_member, dispatch_confirmation, finalize_confirmation 等 |
| E. 预注册与确认队列 | 332-620 | 8 | due_confirmations, confirmation_queue_row, _maybe_enqueue_confirmations 等 |
| F. 事件/信号/生命周期 | 621-758 | 9 | _emit_event, _write_heartbeat, _signal_handler, _shutdown_exit 等 |
| G. 状态/目标/符号 | 764-897 | 9 | load_state, save_state, load_goal, _goal_target_symbols 等 |
| H. LLM Provider 与 Failover | 897-1060 | 12 | _failover_configured, _llm_provider, _praxist_env, _model_argv 等 |
| I. 配额/预算/Token | 1061-1120, 3088-3180 | 11 | quota_gate, _read_cpu_hours, _token_budget_hit 等 |
| J. 快照/证据物化 | 1121-1743 | 20 | build_snapshot, materialize_known_verdicts, load_covariate_pool 等 |
| K. 提案收割与评分 | 1812-2150, 2631-2914 | 25 | harvest_proposals, _proposal_priority_score, _proposal_quality_gate 等 |
| L. 成功门/数据就绪 | 2375-2630 | 12 | _row_eval_end_ts, _current_window_anchor, _symbol_data_stale 等 |
| M. N/Step/Retest | 2915-3087 | 8 | _valid_n_for_symbol, plan_sample_retests, _log_decision |
| N. 快环决策 | 3224-3523 | 3 | decide_fast_loop, write_stop_report |
| O. 主循环/入口 | 3524-4574 | 15+ | main, _main_locked, _maybe_harvest, ensure_baselines 等 |

### 1.3 模块间依赖关系

main() 调用 _main_locked()，后者协调以下功能域：
- 状态加载（load_state, load_goal）-> 域 G
- 预算计量（_read_cpu_hours, _token_budget_hit）-> 域 I
- 快照构建（build_snapshot）-> 域 J
- 收割调度（_maybe_harvest, _harvest_rows）-> 域 O
- 提案入队（_maybe_enqueue_confirmations）-> 域 E
- 快环决策（decide_fast_loop）-> 域 N+H+I
- 慢环管理（_maybe_start_slow_loop, _maybe_finish_slow）-> 域 O
- 事件/信号（_emit_event, _sleep_interruptible）-> 域 F

### 1.4 痛点

1. 4574 行单文件，定位功能需扫描全文件
2. 测试 monkeypatch 负担重：1873 行 test_supervisor.py 中 155 次 sup.X 调用
3. 全局路径变量集中定义（QUEUE, INPROGRESS, REGISTRY, STATE_PATH 等）
4. 交叉引用密集：decide_fast_loop 调用 provider 和 quota 域；_main_locked 调用几乎所有域

---

## 2. 目标架构

### 2.1 设计原则

1. 向后兼容第一：import praxist_supervisor as sup 后所有 36 个 public 函数可用
2. 零运行时依赖变更：不引入新包，不改变启动顺序
3. 可回滚：每次迁移一个域，单 commit 可 git revert
4. 内聚 > 行数均衡：按职责边界拆，不追求文件大小均匀
5. 常量集中：所有路径常量收拢到单一 sup_paths.py

### 2.2 目标模块图

```
scripts/
  praxist_supervisor.py        # 入口 + re-export shim (<200 行)
  sup_paths.py                 # 路径常量 + FM_ROOT (~40 行)
  sup_env.py                   # 环境加载 + Praxist 二进制 (~100 行)
  sup_state.py                 # 状态/目标/符号 (~150 行)
  sup_lifecycle.py             # 事件/信号/心跳/停机 (~150 行)
  sup_provider.py              # LLM provider + failover (~180 行)
  sup_harvest.py               # 提案收割 + 评分 + 质量门 (~500 行)
  sup_evidence.py              # 快照构建 + 证据物化 + baseline (~600 行)
  sup_family.py                # 研究家族 + 确认队列 + FDR (~300 行)
  sup_loops.py                 # 快环决策 + 慢环 + 主循环 (~700 行)
```

### 2.3 模块职责

#### sup_paths.py (~40 行)
所有路径常量：FM_ROOT, HERE, QUEUE, INPROGRESS, REGISTRY, STATE_PATH, LOCK_PATH, VERDICTS_INC, POOL_PATH, BACKLOG_PATH, SYMBOL_STATUS_PATH, MENU_INC, REPORT_DIR, SEARCH_COMMITMENTS_PATH
依赖：os（stdlib）| 被依赖：所有其他模块

#### sup_env.py (~100 行)
_load_dotenv(), _check_required_env(), _resolve_praxist_bin(), _praxist_bin(), _praxist()
依赖：sup_paths | 被依赖：sup_loops, sup_provider

#### sup_state.py (~150 行)
load_state(), save_state(), load_goal(), _goal_target_symbols(), _assert_goal_symbols_contract(), _merge_save(), _cad_int(), _norm_search_policy()
依赖：sup_paths, yaml, json | 被依赖：几乎所有模块

#### sup_lifecycle.py (~150 行)
_emit_event(), _write_heartbeat(), _signal_handler(), _arm_handlers(), _shutdown_exit(), _sleep_interruptible(), _atexit_handler(), _mark_stop_emitted(), parse_429_reset(), _SHUTDOWN_REQUESTED, _START_TIME
依赖：sup_paths | 被依赖：sup_loops, sup_harvest

#### sup_provider.py (~180 行)
_failover_configured(), _llm_provider(), _llm_route(), _praxist_env(), _failover_model_name(), _failover_can_resume_same_run(), _model_argv(), _provider_state(), _run_active(), _active_run_meta(), _latest_429_reset()
依赖：sup_paths, sup_state, sup_env | 被依赖：sup_loops

#### sup_harvest.py (~500 行)
harvest_proposals(), harvest_survivors(), _proposal_priority_score(), _proposal_quality_gate(), _sector_filter_check(), _covariate_filter_check(), _success_delta_gate(), _prescreen_async(), _cross_run_repeat_counts(), _append_backlog(), collect_proposed_variant_ids(), materialize_covariate_menu()
依赖：sup_paths, sup_state, sup_evidence, search_trees, search_promote, registry_lib | 被依赖：sup_loops

#### sup_evidence.py (~600 行)
build_snapshot(), materialize_known_verdicts(), load_covariate_pool(), load_symbol_status(), ensure_baselines(), _baseline_protocol_fingerprint(), _current_protocol_fingerprint(), _archive_baseline_before_regen(), _valid_n_for_symbol(), _experiment_fp_for(), symbol_goal_tier(), _row_eval_end_ts(), _current_window_anchor(), _today_shanghai(), _kline_1h_max_dt(), _symbol_data_stale()
依赖：sup_paths, sup_state, registry_lib, goal_dsl, cascade.* | 被依赖：sup_harvest, sup_loops

#### sup_family.py (~300 行)
family_key_for(), family_for(), register_family_member(), seal_research_family(), dispatch_confirmation(), finalize_confirmation(), load_family_members(), save_family_members(), due_confirmations(), confirmation_queue_row(), load_preregistry(), fdr_pass_persistable(), promote_batch_for_persistence(), _maybe_enqueue_confirmations(), _finalize_confirmation_verdict()
依赖：sup_paths, sup_state, registry_lib, cascade.cov_family, cascade.experiment_fingerprint | 被依赖：sup_loops

#### sup_loops.py (~700 行)
main(), _main_locked(), decide_fast_loop(), write_stop_report(), _maybe_harvest(), _harvest_rows(), _maybe_start_slow_loop(), _maybe_finish_slow(), wait_for_batch(), cleanup_batch_workers(), ensure_phase(), plan_sample_retests(), _maybe_enqueue_retests(), quota_gate(), _commit_search_accepts(), _sweep_search_stops(), _sweep_search_promotions(), _log_decision(), _read_cpu_hours(), _read_token_m(), _token_spend_m(), _token_budget_hit(), _in_slow_window(), _deadline_passed(), _slow_loop_alive(), _queue_busy(), _slow_drain_complete()
依赖：所有其他 sup_* 模块 + search_promote, registry_lib, goal_dsl | 被依赖：无（顶层入口）

### 2.4 向后兼容层

praxist_supervisor.py 缩减为 re-export shim（约 120-180 行）：

```python
#!/usr/bin/env python3
from sup_paths import FM_ROOT, HERE, QUEUE, INPROGRESS, REGISTRY, STATE_PATH, LOCK_PATH, VERDICTS_INC, POOL_PATH, BACKLOG_PATH, SYMBOL_STATUS_PATH, MENU_INC, REPORT_DIR, SEARCH_COMMITMENTS_PATH
from sup_env import _load_dotenv, _check_required_env, _praxist
from sup_state import load_state, save_state, load_goal, _merge_save, _goal_target_symbols, _assert_goal_symbols_contract, _cad_int, _norm_search_policy
from sup_lifecycle import _emit_event, _write_heartbeat, _signal_handler, _shutdown_exit, _sleep_interruptible, _atexit_handler, _arm_handlers, _mark_stop_emitted, parse_429_reset, _write_stop_json
from sup_provider import _failover_configured, _llm_provider, _llm_route, _praxist_env, _failover_model_name, _failover_can_resume_same_run, _model_argv, _provider_state, _run_active, _active_run_meta, _latest_429_reset
from sup_harvest import harvest_proposals, harvest_survivors, _proposal_priority_score, _proposal_quality_gate, _sector_filter_check, _covariate_filter_check, _success_delta_gate, _prescreen_async, _cross_run_repeat_counts, _append_backlog, collect_proposed_variant_ids, materialize_covariate_menu
from sup_evidence import build_snapshot, materialize_known_verdicts, load_covariate_pool, load_symbol_status, ensure_baselines, symbol_goal_tier, _valid_n_for_symbol, _experiment_fp_for, _symbol_n_table, _baseline_protocol_fingerprint, _current_protocol_fingerprint, _row_eval_end_ts, _current_window_anchor, _today_shanghai, _kline_1h_max_dt, _symbol_data_stale, _prior_success_class, _prior_success_row, _locked_success_rows, _locked_window_lines
from sup_family import family_key_for, family_for, register_family_member, seal_research_family, dispatch_confirmation, finalize_confirmation, load_family_members, save_family_members, due_confirmations, confirmation_queue_row, load_preregistry, fdr_pass_persistable, promote_batch_for_persistence, _maybe_enqueue_confirmations, _finalize_confirmation_verdict, _requested_covariate, _confirmation_is_final, _confirm_data_ready, _merge_family_members, _stamp_member, _seal_if_all_terminal, _dead_families, _is_confirmable_failure
from sup_loops import main, decide_fast_loop, write_stop_report, ensure_phase, quota_gate, _main_locked, _maybe_harvest, _harvest_rows, _maybe_start_slow_loop, _maybe_finish_slow, wait_for_batch, cleanup_batch_workers, plan_sample_retests, _maybe_enqueue_retests, _log_decision, _commit_search_accepts, _sweep_search_stops, _sweep_search_promotions, _append_jsonl, _read_cpu_hours, _read_token_m, _token_spend_m, _token_budget_hit, _ensure_tokens_baseline, _in_slow_window, _deadline_passed, _slow_loop_alive, _queue_busy, _slow_drain_complete, _retest_candidates, _active_protocol_snapshot

__all__ = [
    "main", "decide_fast_loop", "write_stop_report", "ensure_phase",
    "quota_gate", "build_snapshot", "harvest_proposals", "harvest_survivors",
    "materialize_known_verdicts", "materialize_covariate_menu",
    "collect_proposed_variant_ids", "load_covariate_pool", "load_symbol_status",
    "load_state", "save_state", "load_goal", "load_preregistry",
    "load_family_members", "save_family_members",
    "family_key_for", "family_for", "register_family_member",
    "seal_research_family", "dispatch_confirmation", "finalize_confirmation",
    "due_confirmations", "confirmation_queue_row",
    "fdr_pass_persistable", "promote_batch_for_persistence",
    "parse_429_reset", "ensure_baselines", "symbol_goal_tier",
    "plan_sample_retests", "wait_for_batch", "cleanup_batch_workers",
    "is_valid_tier",
    "FM_ROOT", "HERE", "QUEUE", "INPROGRESS", "REGISTRY", "STATE_PATH",
    "LOCK_PATH", "VERDICTS_INC", "POOL_PATH", "BACKLOG_PATH",
    "SYMBOL_STATUS_PATH", "MENU_INC", "REPORT_DIR", "SEARCH_COMMITMENTS_PATH",
]

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

---

## 3. 拆分方案

### 3.1 迁移步骤（10 步）

| 步骤 | 操作 | 验证 | 回滚 |
|------|------|------|------|
| 1 | 创建 sup_paths.py | pytest test_supervisor.py | git revert |
| 2 | praxist_supervisor.py 中 from sup_paths import 替换路径 | 同上 | 同上 |
| 3 | 创建 sup_env.py | 同上 | 同上 |
| 4 | 创建 sup_state.py | 同上 | 同上 |
| 5 | 创建 sup_lifecycle.py | 同上 | 同上 |
| 6 | 创建 sup_provider.py | 同上 | 同上 |
| 7 | 创建 sup_evidence.py | 同上 | 同上 |
| 8 | 创建 sup_harvest.py | 同上 | 同上 |
| 9 | 创建 sup_family.py | 同上 | 同上 |
| 10 | 创建 sup_loops.py + shim 化 | 全量 141 测试 | 同上 |

### 3.2 跨模块依赖 DAG

```
sup_paths <- sup_env, sup_state, sup_lifecycle
                |              |           |
         sup_provider <- sup_evidence <- sup_harvest
                |              |           |
              sup_family <- sup_loops
```

无循环依赖。

### 3.3 全局变量归属

| 变量 | 目标模块 |
|------|----------|
| _PRAXIST | sup_env |
| _SHUTDOWN_REQUESTED | sup_lifecycle |
| _START_TIME | sup_lifecycle |
| _PERSISTABLE_DM | sup_family |
| VALID_TIER_VALUES | sup_harvest |

---

## 4. 测试策略

### 4.1 零测试修改原则
所有 141 个测试文件在拆分过程中不得修改。

### 4.2 每步验证
1. pytest tests/test_supervisor.py -x -q
2. pytest tests/ -x -q --tb=short
3. 验证 36 个 public 符号可通过 hasattr(sup, name) 访问
4. 验证路径常量可被 monkeypatch

### 4.3 新增测试
tests/test_sup_modules.py：
- 验证所有新模块可独立导入
- 验证 shim 导出完整性（len(sup.__all__) >= 50）
- 验证无循环导入

---

## 5. 风险评估

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | 循环导入 | 中 | 高 | 严格按 DAG 顺序创建 |
| R2 | monkeypatch 路径失效 | 中 | 高 | 路径常量从 sup_paths re-export |
| R3 | sup_loops.py 仍过大 | 高 | 低 | 可接受 |
| R4 | 短暂不可用 | 低 | 高 | 每步单 commit |
| R5 | 生产启动失败 | 低 | 极高 | 迁移期间不部署 |
| R6 | __all__ 遗漏 | 低 | 中 | 自动校验脚本 |
| R7 | 全局状态跨模块 | 中 | 中 | 统一定义在 sup_lifecycle |
| R8 | 测试非标准 import | 低 | 中 | 拆分前扫描所有 import |

---

## 6. 成功标准

| 标准 | 目标 |
|------|------|
| 测试通过率 | 100%（141 文件，0 修改） |
| praxist_supervisor.py 行数 | <= 200 行 |
| 最大子模块行数 | <= 700 行 |
| --dry-run --once 输出 | 与拆分前一致 |
| 无循环导入 | 验证通过 |
| 36 个 public 符号 | hasattr 全 True |

---

## 7. 回滚方案

```bash
# 全量回滚
git revert <拆分开始>..<拆分结束> --no-edit
# 单步回滚
git revert <具体步骤commit> --no-edit
# 验证
.venv/bin/python -m pytest tests/test_supervisor.py -x -q
```

---

## 8. 文件清单

### 新增
| 文件 | 行数 |
|------|------|
| scripts/sup_paths.py | ~40 |
| scripts/sup_env.py | ~100 |
| scripts/sup_state.py | ~150 |
| scripts/sup_lifecycle.py | ~150 |
| scripts/sup_provider.py | ~180 |
| scripts/sup_harvest.py | ~500 |
| scripts/sup_evidence.py | ~600 |
| scripts/sup_family.py | ~300 |
| scripts/sup_loops.py | ~700 |
| tests/test_sup_modules.py | ~40 |

### 修改
| 文件 | 说明 |
|------|------|
| scripts/praxist_supervisor.py | 4574 -> <=200 行 |
| 141 个测试文件 | 不修改 |

---

## 9. 时间估算

| 步骤 | 时间 |
|------|------|
| sup_paths | 15 min |
| sup_env | 15 min |
| sup_state | 20 min |
| sup_lifecycle | 20 min |
| sup_provider | 25 min |
| sup_evidence | 40 min |
| sup_harvest | 45 min |
| sup_family | 30 min |
| sup_loops + shim | 60 min |
| 全量测试 + 修补 | 30 min |
| **总计** | **~5 小时** |

---

## 10. 参考资料

- scripts/praxist_supervisor.py - 当前 4574 行单文件
- tests/test_supervisor.py - 1873 行主测试
- docs/superpowers/specs/2026-10-08-d4-d5-n10-e1-research-spec.md - D4/D5 前置依赖
- docs/superpowers/reports/2026-10-07-tech-debt-inventory.md - 技术债清单
- docs/superpowers/plans/2026-10-07-tech-debt-closure-plan.md - 技术债关闭计划

---

*SPEC v1.0, 2026-10-09, M5 Supervisor Split*
