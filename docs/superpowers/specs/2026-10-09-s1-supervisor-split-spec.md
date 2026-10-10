# S1: praxist_supervisor.py 模块拆分 SPEC

| 字段 | 值 |
|------|-----|
| **ID** | S1（新 S 系列：结构性重构；与已关闭的 **M5「n_eff 常数函数」** 完全不同——M5 已于 2026-10-07 溯源结案，见 `docs/superpowers/reports/2026-10-07-tech-debt-inventory.md:47`） |
| **日期** | 2026-10-09 |
| **版本** | v3.1（经三次 AST 全量复审；N1-N7 + F1-F8 全部修正） |
| **作者** | Architect Agent |
| **状态** | Draft → 待实施 |
| **前置依赖** | D4/D5（已完成） |
| **目标文件** | scripts/praxist_supervisor.py（4574 行，150 顶层函数 + 10 嵌套函数 + 57 模块级符号 + 9 导入别名） |
| **风险等级** | 高（核心运行时，32 个测试文件引用） |

---

## 1. 现状分析

### 1.1 文件概况

| 指标 | 值 |
|------|-----|
| 总行数 | 4574 |
| 顶层函数数 | 150（118 private + 32 public） |
| 嵌套函数数 | 10（随宿主函数迁移） |
| 模块级赋值 | 57（常量/缓存/路径） |
| 导入别名 | 9（`rl`, `ef`, `st`, 5 个 `_fam_*`） |
| 测试引用 | **32 个测试文件**引用 `praxist_supervisor`（其中 test_supervisor.py 独占 1873 行 / 155 次 sup. 调用） |
| 外部导入 | registry_lib, goal_dsl, cascade.cov_family, cascade.experiment_fingerprint, search_trees, search_promote, cascade.statistical_tests |

### 1.2 功能分区扫描

通过对 150 个顶层函数的行号分布、调用关系和职责分析（详见附录 A），识别出以下 10 个逻辑域：

| 域 | 行号范围 | 顶层函数数 | 职责 |
|----|----------|--------|------|
| A. FDR 与持久化 | 28-54 | 2 | fdr_pass_persistable, promote_batch_for_persistence |
| B. Praxist 二进制解析 | 60-79 | 2 | _resolve_praxist_bin, _praxist_bin, _praxist |
| C. 环境与配置 | 95-144 | 2 | _load_dotenv, _check_required_env |
| D. 研究家族管理 | 192-426 | 10 | family_key_for, register_family_member, dispatch_confirmation, finalize_confirmation 等 |
| E. 预注册与确认队列 | 332-618 | 8 | due_confirmations, confirmation_queue_row, _maybe_enqueue_confirmations 等 |
| F. 事件/信号/生命周期 | 621-762 | 10 | _emit_event, _write_heartbeat, _signal_handler, _shutdown_exit, parse_429_reset 等 |
| G. 状态/目标/符号 | 764-894 | 9 | load_state, save_state, load_goal, _goal_target_symbols 等 |
| H. LLM Provider 与 Failover | 897-1059 | 13 | _failover_configured, _llm_provider, _praxist_env, _model_argv 等 |
| I. 配额/预算/Token | 1061-1119, 3088-3203 | 14 | quota_gate, _read_cpu_hours, _token_budget_hit, _ensure_tokens_baseline 等 |
| J. 快照/证据物化 | 1121-1741, 2375-2628 | 24 | build_snapshot, materialize_known_verdicts, load_covariate_pool 等 |
| K. 提案收割与评分 | 1812-2150, 2631-2913 | 21 | harvest_proposals, _proposal_priority_score, _proposal_quality_gate 等 |
| L. 成功门/数据就绪 | 2375-2570 | 12 | _row_eval_end_ts, _current_window_anchor, _symbol_data_stale 等 |
| M. N/Step/Retest | 2915-3087 | 8 | _valid_n_for_symbol, plan_sample_retests, _log_decision 等 |
| N. 快环决策 | 3224-3521 | 3 | decide_fast_loop, write_stop_report |
| O. 主循环/入口 | 3524-4571 | 15+ | main, _main_locked, _maybe_harvest, ensure_baselines 等 |

> 注：域 D（192-426）与域 E（332-618）行号有重叠——两域在确认队列函数上交叉，拆分时以职责边界为准，不以行号硬切割。
> 附录 A 提供每个符号到目标模块的完整映射，消除未覆盖区间（原 v2.0 未覆盖 1744-1811、2151-2374、3181-3223）。

### 1.3 模块间依赖关系

main() 调用 _main_locked()，后者协调以下功能域：
- 状态加载（load_state, load_goal）→ 域 G
- 预算计量（_read_cpu_hours, _token_budget_hit, _token_spend_m, _read_token_m）→ 域 I
- 快照构建（build_snapshot）→ 域 J
- 收割调度（_maybe_harvest, _harvest_rows）→ 域 O
- 提案入队（_maybe_enqueue_confirmations）→ 域 E
- 快环决策（decide_fast_loop）→ 域 N+H+I
- 慢环管理（_maybe_start_slow_loop, _maybe_finish_slow）→ 域 O
- 事件/信号（_emit_event, _sleep_interruptible）→ 域 F

### 1.4 痛点

1. 4574 行单文件，定位功能需扫描全文件
2. 测试 monkeypatch 负担重：1873 行 test_supervisor.py 中 155 次 sup.X 调用
3. 全局路径变量集中定义（QUEUE, INPROGRESS, REGISTRY, STATE_PATH 等）
4. 交叉引用密集：decide_fast_loop 调用 provider 和 quota 域；_main_locked 调用几乎所有域

---

## 2. 目标架构

### 2.1 设计原则

1. 向后兼容第一：import praxist_supervisor as sup 后所有 32 个 public 函数可用
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
  sup_state.py                 # 状态/目标/符号 + token 预算基线 (~200 行)
  sup_lifecycle.py             # 事件/信号/心跳/停机 + _log_decision + _now_iso (~200 行)
  sup_provider.py              # LLM provider + failover + parse_429_reset (~200 行)
  sup_harvest.py               # 提案收割 + 评分 + 质量门 + harvest_survivors (~500 行)
  sup_evidence.py              # 快照构建 + 证据物化 + baseline 重生簇 + 死亡族簇 + _valid_n_for_symbol (~700 行)
  sup_family.py                # 研究家族 + 确认队列 + FDR（无 family_for 嵌套闭包）(~300 行)
  sup_loops.py                 # 快环决策 + 慢环 + 主循环 (~680 行)
```

### 2.3 模块职责

#### sup_paths.py (~40 行)
所有路径常量：FM_ROOT, HERE, QUEUE, INPROGRESS, REGISTRY, STATE_PATH, LOCK_PATH, VERDICTS_INC, POOL_PATH, BACKLOG_PATH, SYMBOL_STATUS_PATH, MENU_INC, REPORT_DIR, SEARCH_COMMITMENTS_PATH, STATE_MD, EVENTS_PATH, HEARTBEAT_PATH, STOP_REPORT_JSON, RETEST_GATE_N, FAMILY_REGISTRY, PREREGISTRY_PATH
依赖：os, pathlib（stdlib）| 被依赖：所有其他模块

#### sup_env.py (~100 行)
_load_dotenv(), _check_required_env(), _resolve_praxist_bin(), _praxist_bin(), _praxist()
依赖：sup_paths | 被依赖：sup_loops, sup_provider

#### sup_state.py (~200 行)
load_state(), save_state(), load_goal(), _goal_target_symbols(), _assert_goal_symbols_contract(), _cad_int(), _norm_search_policy(), **_ensure_tokens_baseline()**, **_read_token_m()**, **_token_spend_m()**, _load_goal_symbols(), _reset_goal_symbols_cache(), **load_preregistry()**, **_latest_data_dt()**
依赖：sup_paths, yaml, json | 被依赖：几乎所有模块

> **N1 环 B 修正**：`_ensure_tokens_baseline` + `_read_token_m` + `_token_spend_m` 从 sup_loops 移至 sup_state（load_state:774 直接调用 _ensure_tokens_baseline，属于状态初始化语义，与 state 域内聚）。

#### sup_lifecycle.py (~200 行)
_emit_event(), _write_heartbeat(), _signal_handler(), _shutdown_exit(), _sleep_interruptible(), _atexit_handler(), _arm_handlers(), _mark_stop_emitted(), _write_stop_json(), **_log_decision()**, **_now_iso()**, _SHUTDOWN_REQUESTED, _START_TIME, _STOP_EMITTED, _RUN_ID, _EVENT_LOCK, _HANDLERS_ARMED
依赖：sup_paths, json | 被依赖：sup_loops, sup_harvest, sup_family, sup_evidence（通过 _log_decision 横切调用）

> **N1 环 C 修正**：`_now_iso`（:325）移至 sup_lifecycle（被 _emit_event:628 / _write_stop_json:659 / _write_heartbeat:681 / _log_decision:3081 调用，属底层横切工具函数）。

#### sup_provider.py (~200 行)
_failover_configured(), _llm_provider(), _llm_route(), _praxist_env(), _failover_model_name(), _failover_can_resume_same_run(), _model_argv(), _provider_state(), _run_active(), _active_run_meta(), _latest_429_reset(), _recorded_run_model(), _status_rows(), _env_first(), **parse_429_reset()**
依赖：sup_paths, sup_state, sup_env | 被依赖：sup_loops

> **N1 边 H 修正**：`parse_429_reset` 移至 sup_provider（_latest_429_reset:1049 是其唯一调用方，provider 自洽）。

#### sup_harvest.py (~500 行)
harvest_proposals(), **harvest_survivors()**, _proposal_priority_score(), _proposal_quality_gate(), **_sector_filter_check()**, _covariate_filter_check(), _prescreen_async(), _cross_run_repeat_counts(), _append_backlog(), materialize_covariate_menu(), _apply_prescreen_score(), _prescreen_plausibility(), _latest_verdict_per_symbol(), _recent_ok_verdicts()
依赖：sup_paths, sup_state, sup_evidence, sup_lifecycle, search_trees, search_promote, registry_lib | 被依赖：sup_loops

> **N7 修正**：`harvest_survivors`(:1254) 与 `_sector_filter_check`(:2208) 等 gap 段函数归入 sup_harvest（收割职责内聚）。

#### sup_evidence.py (~700 行)
build_snapshot(), materialize_known_verdicts(), load_covariate_pool(), load_symbol_status(), ensure_baselines(), **_verdict_sort_key()**, **collect_proposed_variant_ids()**, **_success_delta_gate()**（跨域移动：原域 O → 此处）, _baseline_protocol_fingerprint(), _current_protocol_fingerprint(), _archive_baseline_before_regen(), _valid_n_for_symbol()（跨域移动：原域 M → 此处）, _experiment_fp_for(), symbol_goal_tier(), _row_eval_end_ts(), _current_window_anchor(), _today_shanghai(), _kline_1h_max_dt(), _symbol_data_stale(), _prior_success_class(), _prior_success_row(), _success_delta_gate(), _locked_success_rows(), _locked_window_lines(), _symbol_n_table(), _load_evaluator(), _symbol_has_current_nocov_baseline(), _protocol_section_line(), _verdict_family(), _finite_dir_acc(), _has_prior_failure(), _effective_clue_lines(), _cross_matrix_lines(), _prior_class(), _old_protocol_prior_lines(), **_is_confirmable_failure()**, **_dead_families()**, **_dead_family_lines()**, **_family_confirmatory_counts()**, **_active_protocol_snapshot()**, **_regen_baseline_with_archive()**, **_baseline_reanchor_reason()**, **_guard_confirm_from_ts_after_regen()**, **_prereg_confirm_from_ts()**, **_cutoffs_at_or_after()**（嵌套，随宿主迁移）, **_da_key()**（嵌套，随宿主迁移）,
**VALID_TIER_VALUES**（从域 A 移入此处，见 C3 修正）,
**is_valid_tier()**（从 build_snapshot 嵌套函数提升为模块级，见 C4 + N5 修正）
依赖：sup_paths, sup_state, sup_lifecycle, registry_lib, goal_dsl, cascade.* | 被依赖：sup_harvest, sup_loops, sup_family

> **N1 修正汇总**：
> - 环 A：`_active_protocol_snapshot`(:3029) → sup_evidence（内部仅调 _current_protocol_fingerprint，evidence 自洽）
> - 环 D：基线重生簇（`_regen_baseline_with_archive`, `_baseline_reanchor_reason`, `_guard_confirm_from_ts_after_regen`, `_prereg_confirm_from_ts`, `_cutoffs_at_or_after`）整体 → sup_evidence
> - 边 E：`_is_confirmable_failure`(:1859) → sup_evidence（唯一调用方 `_has_prior_failure` 在 evidence 内）
> - 边 F：死亡族簇（`_dead_families`/`_dead_family_lines`/`_family_confirmatory_counts`）→ sup_evidence（harvest→evidence 已声明，无需 harvest→family 边）
> - 边 I：`_load_evaluator`(:1790) → sup_evidence（被 harvest_proposals:2631 与 _symbol_n_table:2987 双向调用，不可落 sup_harvest）

#### sup_family.py (~300 行)
family_key_for(), register_family_member(), seal_research_family(), dispatch_confirmation(), finalize_confirmation(), load_family_members(), save_family_members(), due_confirmations(), confirmation_queue_row(), fdr_pass_persistable(), promote_batch_for_persistence(), _maybe_enqueue_confirmations(), _finalize_confirmation_verdict(), _requested_covariate(), _confirmation_is_final(), _confirm_data_ready(), _merge_family_members(), _stamp_member(), _seal_if_all_terminal(), _PERSISTABLE_DM, _BASE_COVARIATE, _CONFIRM_DATA_TTL_S, _CONFIRM_DATA_CACHE, _CONFIRMATION_NOTICE, _CONFIRMATION_NOTICE_TTL_S, _CONFIRM_REDISPATCH, _CONFIRM_REDISPATCH_TTL_S, _CONFIRMATORY_DM, _prereg_field(), _find_prereg()
依赖：sup_paths, sup_state, sup_lifecycle, **sup_evidence**（N1 边 G：_maybe_enqueue_confirmations:521 → load_covariate_pool）, registry_lib, cascade.cov_family, cascade.experiment_fingerprint | 被依赖：sup_loops

> **WARNING: 删除 `family_for`**（N2 修正）：:522 实测为 `_maybe_enqueue_confirmations` 内的**嵌套闭包**（4 空格缩进，捕获 `pool`），与 is_valid_tier 同类问题但步骤 0 未覆盖。闭包随宿主函数整体迁移，不在模块级 import 列表中。

#### sup_loops.py (~680 行)
main(), _main_locked(), decide_fast_loop(), write_stop_report(), _maybe_harvest(), _harvest_rows(), _maybe_start_slow_loop(), _maybe_finish_slow(), wait_for_batch(), cleanup_batch_workers(), ensure_phase(), plan_sample_retests(), _maybe_enqueue_retests(), quota_gate(), _token_budget_hit(), _commit_search_accepts(), _sweep_search_stops(), _sweep_search_promotions(), _read_cpu_hours(), _in_slow_window(), _deadline_passed(), _slow_loop_alive(), _queue_busy(), _slow_drain_complete(), _append_jsonl(), _retest_candidates()
依赖：所有其他 sup_* 模块 + search_promote, registry_lib, goal_dsl | 被依赖：无（顶层入口）

### 2.4 向后兼容层

praxist_supervisor.py 缩减为 re-export shim（约 120-180 行）。**§4.2 patch 映射源以附录 A 为准**。

```python
#!/usr/bin/env python3
from sup_paths import FM_ROOT, HERE, QUEUE, INPROGRESS, REGISTRY, STATE_PATH, LOCK_PATH, VERDICTS_INC, POOL_PATH, BACKLOG_PATH, SYMBOL_STATUS_PATH, MENU_INC, REPORT_DIR, SEARCH_COMMITMENTS_PATH, STATE_MD, EVENTS_PATH, HEARTBEAT_PATH, STOP_REPORT_JSON, RETEST_GATE_N, FAMILY_REGISTRY, PREREGISTRY_PATH, PHASES, POLL_S
from sup_env import _load_dotenv, _check_required_env, _praxist, _PRAXIST
from sup_state import load_state, save_state, load_goal, _merge_save, _goal_target_symbols, _assert_goal_symbols_contract, _cad_int, _norm_search_policy, _load_goal_symbols, _reset_goal_symbols_cache, _ensure_tokens_baseline, _read_token_m, _token_spend_m, load_preregistry, _latest_data_dt, _CADENCE_DEFAULTS, _GOAL_YAML_DEFAULT, _GOAL_SYMBOLS_CACHE, _ev_mod_for_goal, GOAL_SYMBOLS_SET
from sup_lifecycle import _emit_event, _write_heartbeat, _signal_handler, _shutdown_exit, _sleep_interruptible, _atexit_handler, _arm_handlers, _mark_stop_emitted, _write_stop_json, _log_decision, _now_iso, _SHUTDOWN_REQUESTED, _START_TIME, _STOP_EMITTED, _RUN_ID, _EVENT_LOCK, _HANDLERS_ARMED
from sup_provider import _failover_configured, _llm_provider, _llm_route, _praxist_env, _failover_model_name, _failover_can_resume_same_run, _model_argv, _provider_state, _run_active, _active_run_meta, _latest_429_reset, _recorded_run_model, _status_rows, _env_first, parse_429_reset
from sup_harvest import harvest_proposals, harvest_survivors, _proposal_priority_score, _proposal_quality_gate, _sector_filter_check, _covariate_filter_check, _prescreen_async, _cross_run_repeat_counts, _append_backlog, materialize_covariate_menu, _apply_prescreen_score, _prescreen_plausibility, _latest_verdict_per_symbol, _recent_ok_verdicts, CROSS_MATRIX_MAX_ROWS, OLD_PRIORS_MAX_ROWS, MIN_QUALITY_SCORE, COV_CROSS_FAIL_MIN, COV_FAIL_WINDOW, SYMBOL_FAIL_WINDOW
from sup_evidence import build_snapshot, materialize_known_verdicts, load_covariate_pool, load_symbol_status, ensure_baselines, symbol_goal_tier, _valid_n_for_symbol, _experiment_fp_for, _symbol_n_table, _baseline_protocol_fingerprint, _current_protocol_fingerprint, _archive_baseline_before_regen, _row_eval_end_ts, _current_window_anchor, _today_shanghai, _kline_1h_max_dt, _symbol_data_stale, _prior_success_class, _prior_success_row, _success_delta_gate, _locked_success_rows, _locked_window_lines, VALID_TIER_VALUES, is_valid_tier, _protocol_section_line, _verdict_family, _finite_dir_acc, _has_prior_failure, _effective_clue_lines, _cross_matrix_lines, _prior_class, _old_protocol_prior_lines, _symbol_has_current_nocov_baseline, _load_evaluator, _is_confirmable_failure, _dead_families, _dead_family_lines, _family_confirmatory_counts, _active_protocol_snapshot, _regen_baseline_with_archive, _baseline_reanchor_reason, _guard_confirm_from_ts_after_regen, _prereg_confirm_from_ts, _verdict_sort_key, collect_proposed_variant_ids, LOCKED_WINDOW_MAX_ROWS, STALE_DATA_DAYS, SUCCESS_DELTA_MIN_CHARS, _BASELINE_STALENESS_MAX_H, _FP_TARGET_CACHE, _FP_WEIGHTS_CACHE
from sup_family import family_key_for, register_family_member, seal_research_family, dispatch_confirmation, finalize_confirmation, load_family_members, save_family_members, due_confirmations, confirmation_queue_row, fdr_pass_persistable, promote_batch_for_persistence, _maybe_enqueue_confirmations, _finalize_confirmation_verdict, _requested_covariate, _confirmation_is_final, _confirm_data_ready, _merge_family_members, _stamp_member, _seal_if_all_terminal, _PERSISTABLE_DM, _BASE_COVARIATE, _CONFIRM_DATA_TTL_S, _CONFIRM_DATA_CACHE, _CONFIRMATION_NOTICE, _CONFIRMATION_NOTICE_TTL_S, _CONFIRM_REDISPATCH, _CONFIRM_REDISPATCH_TTL_S, _CONFIRMATORY_DM, _prereg_field, _find_prereg
from sup_loops import main, decide_fast_loop, write_stop_report, ensure_phase, quota_gate, _main_locked, _maybe_harvest, _harvest_rows, _maybe_start_slow_loop, _maybe_finish_slow, wait_for_batch, cleanup_batch_workers, plan_sample_retests, _maybe_enqueue_retests, _append_jsonl, _read_cpu_hours, _in_slow_window, _deadline_passed, _slow_loop_alive, _queue_busy, _slow_drain_complete, _retest_candidates, _token_budget_hit, _commit_search_accepts, _sweep_search_stops, _sweep_search_promotions

# stdlib re-exports for test monkeypatch (sup.time, sup.subprocess)
import time
import subprocess
# goal_dsl re-export for test_supervisor.py direct calls (sup.evaluate_goal)
from goal_dsl import evaluate_goal

__all__ = [
    "main", "decide_fast_loop", "write_stop_report", "ensure_phase",
    "quota_gate", "build_snapshot", "harvest_proposals", "harvest_survivors",
    "materialize_known_verdicts", "materialize_covariate_menu",
    "collect_proposed_variant_ids", "load_covariate_pool", "load_symbol_status",
    "load_state", "save_state", "load_goal", "load_preregistry",
    "load_family_members", "save_family_members",
    "family_key_for", "register_family_member",
    "seal_research_family", "dispatch_confirmation", "finalize_confirmation",
    "due_confirmations", "confirmation_queue_row",
    "fdr_pass_persistable", "promote_batch_for_persistence",
    "parse_429_reset", "ensure_baselines", "symbol_goal_tier",
    "plan_sample_retests", "wait_for_batch", "cleanup_batch_workers",
    "is_valid_tier", "VALID_TIER_VALUES",
    "FM_ROOT", "HERE", "QUEUE", "INPROGRESS", "REGISTRY", "STATE_PATH",
    "LOCK_PATH", "VERDICTS_INC", "POOL_PATH", "BACKLOG_PATH",
    "SYMBOL_STATUS_PATH", "MENU_INC", "REPORT_DIR", "SEARCH_COMMITMENTS_PATH",
    "STATE_MD", "EVENTS_PATH", "HEARTBEAT_PATH", "STOP_REPORT_JSON",
    "RETEST_GATE_N", "FAMILY_REGISTRY", "PREREGISTRY_PATH",
    "_SHUTDOWN_REQUESTED", "_START_TIME", "_PRAXIST", "_PERSISTABLE_DM",
    "_STOP_EMITTED", "_RUN_ID", "_EVENT_LOCK", "_HANDLERS_ARMED",
    "_CADENCE_DEFAULTS", "_GOAL_YAML_DEFAULT", "_GOAL_SYMBOLS_CACHE",
    "_ev_mod_for_goal", "GOAL_SYMBOLS_SET",
    "_CONFIRM_DATA_TTL_S", "_CONFIRM_DATA_CACHE",
    "_CONFIRMATION_NOTICE", "_CONFIRMATION_NOTICE_TTL_S",
    "_CONFIRM_REDISPATCH", "_CONFIRM_REDISPATCH_TTL_S",
    "_CONFIRMATORY_DM", "_BASE_COVARIATE",
    "_FP_WEIGHTS_CACHE", "_FP_TARGET_CACHE",
    "MIN_QUALITY_SCORE", "CROSS_MATRIX_MAX_ROWS", "OLD_PRIORS_MAX_ROWS",
    "LOCKED_WINDOW_MAX_ROWS", "SUCCESS_DELTA_MIN_CHARS", "STALE_DATA_DAYS",
    "COV_CROSS_FAIL_MIN", "SYMBOL_FAIL_WINDOW", "COV_FAIL_WINDOW",
    "_BASELINE_STALENESS_MAX_H",
    "PHASES", "POLL_S",
]

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

---

## 3. 拆分方案

### 3.0 迁移步骤 0（C4 前置 + N5 修正：提升 is_valid_tier 为模块级函数）

在正式拆分前，先将 `is_valid_tier` 从 `build_snapshot` 内部（行 1150）提升为模块级函数。

**实际函数体**（:1150-1162，实测）：
```python
def is_valid_tier(v):
    """校验 tier 值域，防止非法值（第二套中文语义、None、数字等）混入。

    注意：第三套语义（"A"/"B"/"C" 字面值）与第一套值域重叠，值域守卫无法区分；
    第三套语义的实际防线是写入方唯一性 + two_star_critic 已退役（N10）。
    """
    tier = v.get("tier")
    if tier is None:
        return False
    if tier not in VALID_TIER_VALUES:
        _log_decision(log, "tier_domain_violation", f"variant={v.get('variant_id', 'unknown')} tier={tier}")
        return False
    return True
```

**关键差异（与 v2.0 sketch 对比）**：
1. **无** `isinstance(v, dict)` 检查——直接 `v.get("tier")`。照抄 v2.0 sketch 反而引入语义变更。
2. 命中非法值时调用 `_log_decision(log, "tier_domain_violation", ...)`——**`log` 是 build_snapshot 作用域的闭包变量**。

**提升到模块级的方案**：
```python
def is_valid_tier(v, log=None):
    """校验 tier 值域，防止非法值混入。

    Args:
        v: variant dict（调用方保证非 None）。
        log: 可选日志函数。模块级调用时提供（如 _log_decision），
             build_snapshot 内调用时传入其闭包 log。
    """
    tier = v.get("tier")
    if tier is None:
        return False
    if tier not in VALID_TIER_VALUES:
        if log is not None:
            log("tier_domain_violation", f"variant={v.get('variant_id', 'unknown')} tier={tier}")
        return False
    return True
```

build_snapshot 内调用点更新为 `is_valid_tier(v, log)`。

**验证项**：
- `tier_domain_violation` 日志路径仍有测试覆盖（grep tests/ -l "tier_domain_violation"）
- 模块级默认调用 `is_valid_tier(v)`（无 log）不抛异常

| 操作 | 验证 | 回滚 |
|------|------|------|
| 单 commit：提升 is_valid_tier 到模块级 + 参数化 log + 全量测试 | pytest tests/ -x -q | git revert |

> **惰性导入说明**：函数级惰性导入（如 `from data.data_store import DataStore` 在 :463/:2925/:2969 内 `import`）随宿主函数自动迁移，不占附录 A 条目——实施者无需为惰性导入单独创建模块。

### 3.1 迁移步骤（10 步 + 步骤 0）

| 步骤 | 操作 | 验证 | 回滚 |
|------|------|------|------|
| **0** | 提升 is_valid_tier 为模块级函数（C4 + N5） | pytest tests/ -x -q | git revert |
| 1 | 创建 sup_paths.py | pytest tests/ -x -q | git revert |
| 2 | praxist_supervisor.py 中 from sup_paths import 替换路径 | 同上 | 同上 |
| 3 | 创建 sup_env.py | 同上 | 同上 |
| 4 | 创建 sup_state.py | 同上 | 同上 |
| 5 | 创建 sup_lifecycle.py | 同上 | 同上 |
| 6 | 创建 sup_provider.py | 同上 | 同上 |
| 7 | 创建 sup_evidence.py | 同上 | 同上 |
| 8 | 创建 sup_harvest.py | 同上 | 同上 |
| 9 | 创建 sup_family.py | 同上 | 同上 |
| 10 | 创建 sup_loops.py + shim 化 | 全量 32 个测试文件 | 同上 |

### 3.2 跨模块依赖 DAG（基于附录 A 重画，v3.0 确认无环）

```
                          sup_paths
                         /    |    \
                    sup_env  sup_state  sup_lifecycle
                      |     /    |   \      |
                      |    /     |    \     |
                  sup_provider   |   sup_evidence
                      |          |     /   |   \
                      |          |    /    |    \
                      |          |   /     |     \
                   sup_loops <- sup_family   sup_harvest
                                  \___________/
```

**依赖方向**（全部向下，无循环）：
- sup_paths → 所有模块（基础路径常量）
- sup_env → sup_loops, sup_provider（环境/二进制）
- sup_state → sup_provider, sup_evidence, sup_family, sup_harvest, sup_loops（状态/目标/token基线）
- sup_lifecycle → sup_provider（parse_429_reset 已入 provider），sup_evidence（_log_decision 横切），sup_family，sup_harvest，sup_loops
- sup_provider → sup_loops（provider 被 loops 依赖）
- sup_evidence → sup_harvest（证据被收割依赖），sup_family（N1 边 G：load_covariate_pool），sup_loops
- sup_family → sup_loops（家族被 loops 依赖）
- sup_harvest → sup_loops（收割被 loops 依赖）

**N1 修正后的环消解确认**：
| 原环 | 修正 | 结果 |
|------|------|------|
| 环 A (loops <-> family) | `_active_protocol_snapshot` → sup_evidence | loops → family → evidence，无回边 |
| 环 B (loops <-> state) | `_ensure_tokens_baseline` + `_read_token_m` → sup_state | state → evidence/loops 单向 |
| 环 C (lifecycle <-> family) | `_now_iso` → sup_lifecycle | lifecycle → family 单向 |
| 环 D (loops <-> evidence) | 基线重生簇 → sup_evidence | evidence → loops 单向 |
| 边 E | `_is_confirmable_failure` → sup_evidence | evidence 内聚 |
| 边 F | 死亡族簇 → sup_evidence | harvest → evidence 单向 |
| 边 G | family deps 补 evidence | family → evidence 单向 |
| 边 H | `parse_429_reset` → sup_provider | provider 内聚 |
| 边 I | `_load_evaluator` → sup_evidence | evidence 内聚 |
| **环 E** (evidence <-> harvest) | `_verdict_sort_key` + `collect_proposed_variant_ids` -> sup_evidence | harvest -> evidence 单向（v3.1 修正） |
| **环 F** (evidence <-> family) | `load_preregistry` + `_latest_data_dt` -> sup_state | family -> state 单向，evidence -> state 单向（v3.1 修正） |

**§3.2 声明：基于附录 A 的完整调用图，此 DAG 无循环依赖（v3.1 修正后：环 E/F 消解）。**

### 3.3 全局变量归属（v3.0 修正版）

| 变量 | 目标模块 | 说明 |
|------|----------|------|
| _PRAXIST | sup_env | Praxist 二进制路径缓存 |
| _SHUTDOWN_REQUESTED | sup_lifecycle | 关机信号标志 |
| _START_TIME | sup_lifecycle | 启动时间戳 |
| _STOP_EMITTED | sup_lifecycle | stop 事件已发射标志 |
| _RUN_ID | sup_lifecycle | 运行 ID |
| _EVENT_LOCK | sup_lifecycle | 事件写锁 |
| _HANDLERS_ARMED | sup_lifecycle | 信号处理已注册标志 |
| _PERSISTABLE_DM | sup_family | 持久化决策矩阵 |
| VALID_TIER_VALUES | sup_evidence（C3 修正） | 有效 tier 值集合 |
| _BASE_COVARIATE | sup_family | 基础协变量 |
| _CONFIRM_DATA_TTL_S / _CONFIRM_DATA_CACHE | sup_family | 确认数据缓存 |
| _CONFIRMATION_NOTICE / _CONFIRMATION_NOTICE_TTL_S | sup_family | 确认通知 |
| _CONFIRM_REDISPATCH / _CONFIRM_REDISPATCH_TTL_S | sup_family | 确认重发 |
| _CONFIRMATORY_DM | sup_family | 确认决策矩阵 |
| _CADENCE_DEFAULTS | sup_state | 默认节奏配置 |
| _GOAL_YAML_DEFAULT / _GOAL_SYMBOLS_CACHE | sup_state | 目标 YAML 默认/缓存 |
| _ev_mod_for_goal | sup_state | 评估模块映射 |
| GOAL_SYMBOLS_SET | sup_state | 目标符号集合 |
| _FP_WEIGHTS_CACHE / _FP_TARGET_CACHE | sup_evidence | 指纹缓存 |
| _BASELINE_STALENESS_MAX_H | sup_evidence | 基线陈旧阈值 |

> shim 必须 re-export 以上全部全局符号，见 §2.4。

---

## 4. 测试策略（v3.0 修正版）

### 4.1 新原则：Patch 目标机械迁移，测试语义零改动

v1.0 的「零测试修改」原则已被评审证实不可行：
- 7 个测试文件共 **238 处** `monkeypatch.setattr(sup, ...)` + **7 处** `sup._SHUTDOWN_REQUESTED = True/False`
- Shim `from sup_X import Y` 是值拷贝，`setattr(sup, "Y", mock)` 只改 shim 命名空间，拆分后真实调用方在 sup_X 命名空间解析 → **patch 静默失效**
- 模块属性赋值无 `__setattr__` 钩子（PEP 562），shim 设计无法拦截 `_SHUTDOWN_REQUESTED` 直接赋值

**新原则**：238+7 处 patch 点脚本化改写为 `setattr(<Y 实际所属模块>, "Y", mock)`，测试逻辑本身零改动。

### 4.2 Patch 迁移脚本规范（N2/N3/N4 修正）

**别名扫描（N4 修正）**：脚本必须识别全部 4 种 import 别名形态：
| 别名 | 文件数 | 示例 |
|------|--------|------|
| `as sup` | 14 | `import praxist_supervisor as sup` |
| `as S` | 13 | `import praxist_supervisor as S` |
| `as sv` | 1 | `import praxist_supervisor as sv` |
| `as s` | 1 | 内联 `import praxist_supervisor as s` |

脚本正则/AST 匹配模式：`(?:sup|S|sv|s)\.(\w+)`，提取属性名后查附录 A 映射表获取目标模块。

**映射源（N2 修正）**：§4.2 脚本使用附录 A 的完整符号→模块映射表（而非 §2.4 的 import 清单），覆盖所有 ~245 个可测试引用符号（150 顶层函数 + 57 赋值 + 9 别名 + ~29 模块级常量/缓存）。

**附录 A 之外的特判符号**（10 个无法经附录 A 映射，须在迁移脚本中特殊处理）：
| 符号 | 来源 | 处置 |
|------|------|------|
| `time` | stdlib 模块属性（`sup.time.sleep`） | shim 已 `import time`，测试直接 `setattr(sup.time, ...)` 全局生效 |
| `subprocess` | stdlib 模块属性（`sup.subprocess.Popen`） | shim 已 `import subprocess`，同上 |
| `logging` | stdlib 模块属性（`s.logging = ...`） | 测试中通过 `as s` 别名替换，不属附录 A 符号 |
| `evaluate_goal` | `goal_dsl.evaluate_goal` 直接调用 | shim 已 `from goal_dsl import evaluate_goal` 重新导出 |
| `__file__` | 源码自省（`open(S.__file__)`） | 迁移后 S.__file__ 指向 shim（<200 行），不含原调用文本——改指 `sup_loops.__file__`（见 F7） |

**迁移脚本强制要求**：必须使用 AST import 追踪（识别每个文件中 `import praxist_supervisor as <alias>` 的别名绑定），禁止裸正则 `(?:sup|S|sv|s)\.(\w+)` 匹配——后者会将局部变量 `s.update(over)`、`s.short_horizon_only` 及字符串字面量 `"%s_%s.json"`/`"sup.lock"` 误判为 supervisor 引用并改坏测试。

**别名 patch 策略（N3 修正）**：对导入别名（`rl`, `subprocess`, `time`, `logging` 等），单点 `monkeypatch.setattr(sup, "rl", ...)` 只影响 shim 命名空间，拆分后 `rl.` 绑定存在于多个 sup_* 模块。修正策略二选一：

1. **patch 源模块**（推荐）：`monkeypatch.setattr(rl, "read_rows", mock_read_rows)` 直接 patch 源模块 `registry_lib` 的属性。这样所有 import `rl` 的 sup_* 模块共享同一 mock。
2. **循环 patch 全部 sup_* 模块**：在测试夹具中遍历 `[sup_paths, sup_env, sup_state, sup_lifecycle, sup_provider, sup_harvest, sup_evidence, sup_family, sup_loops]`，对每个模块 `monkeypatch.setattr(mod, "rl", mock_rl)`。

对 `subprocess`/`time`/`logging` 等 stdlib 别名同理处理。

**源码自省测试处置（F7）**：部分测试通过 `open(S.__file__)` 读取源码文本并断言特定调用存在（如 `test_search_tree_stop_rules_20261006.py:479` 断言 `'_sweep_search_stops(goal, log, snap["variants"])' in src`）。拆分后 `S.__file__` 指向 shim（不含该调用原文），此类测试须迁移为指向实际模块的 `__file__`（如 `sup_loops.__file__`）。迁移脚本须识别 `open(.*\_\_file\_\_).*read()` 模式并替换目标模块。

### 4.3 死代码闸门适配（m4 补充）

`tests/test_no_dead_code.py` 使用 AST 扫描检测死代码。拆分后源文件从 1 个变为 10 个（praxist_supervisor.py + 9 sup_*.py）。若该测试含文件白名单，须同步更新以包含所有新模块。

### 4.4 每步验证

1. pytest tests/test_supervisor.py -x -q
2. pytest tests/ -x -q --tb=short（全部 32 个引用文件 + 其他测试）
3. 验证 32 个 public 函数可通过 hasattr(sup, name) 访问
4. 验证路径常量可被 monkeypatch
5. 验证 patch 迁移后 238+7 处全部指向实际模块
6. **N5 新增**：验证 `tier_domain_violation` 日志路径仍有测试覆盖

### 4.5 新增测试

tests/test_sup_modules.py：
- 验证所有新模块可独立导入
- 验证 shim 导出完整性（len(sup.__all__) >= 80，v3.0 扩容后）
- 验证无循环导入
- 验证全局符号 re-export（`_SHUTDOWN_REQUESTED`, `_START_TIME`, `_PRAXIST`, `_PERSISTABLE_DM`, `VALID_TIER_VALUES` 均可通过 `from praxist_supervisor import X` 获取）
- **N5 新增**：验证 `is_valid_tier({"tier": "invalid"}, log=mock_log)` 正确调用 log 并返回 False

---

## 5. 风险评估

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | 循环导入 | 低（附录 A 确认 DAG 无环） | 高 | 严格按 §3.2 DAG 顺序创建 |
| R2 | monkeypatch 路径失效 | 低（附录 A 映射 + N3 别名策略） | 高 | §4.2 脚本迁移 + assert 验证 |
| R3 | sup_loops.py 仍过大 | 高 | 低 | 可接受（<=700 行） |
| R4 | 短暂不可用 | 低 | 高 | 每步单 commit 可 revert |
| R5 | 生产启动失败 | 低 | 极高 | 迁移窗口协议（§5.1） |
| R6 | __all__ 遗漏 | 低 | 中 | 自动校验脚本 |
| R7 | 全局状态跨模块 | 低 | 中 | 统一定义在 sup_lifecycle，shim re-export |
| R8 | 测试非标准 import | 低 | 中 | 拆分前 AST 扫描所有 32 个测试文件 |
| R9 | 迁移窗口 watchdog 触发重启 | 中 | 高 | §5.1 协议：flag 续期 + supervisor 停机 |

### 5.1 迁移窗口协议（M3 新增）

拆分过程须遵守以下协议，防止 cron 看门狗（diagnose_three_loop.sh, 每 15 分钟）在代码半拆分状态下触发 supervisor 重启：

1. **拆分前**：
   - 若 supervisor 在运行：`kill -TERM <pid>` 优雅停止 → `sleep 5` 等待退出 → `pgrep -f praxist_supervisor` 确认 0 进程
   - 暂停 cron 自动重启：`crontab -e` 注释 diagnose_three_loop.sh 行（或创建 maintenance.flag）——迁移窗口内禁止看门狗触发重启
   - 若使用 flag：每 3 小时 `touch /home/abug/timesfm/maintenance.flag` 续期（flag 过期 = 4 小时，P1 修正产物）

2. **拆分中**：
   - 每步单 commit，任一 commit 状态不可用于生产
   - 全量测试通过后方可进入下一步

3. **拆分后**：
   - 全量 pytest 通过 + `--dry-run --once` 输出与拆分前一致
   - 拉起 supervisor：`.venv/bin/python scripts/praxist_supervisor.py --once` 冒烟
   - 确认 ≥1 个心跳周期正常运行（_write_heartbeat 文件写入成功）
   - 撤销维护模式（恢复 crontab 或移除 maintenance.flag）
   - 正常启动 supervisor 并验证 PID 存活

---

## 6. 成功标准

| 标准 | 目标 |
|------|------|
| 测试通过率 | 100%（32 个引用文件，patch 目标已迁移） |
| praxist_supervisor.py 行数 | ≤ 200 行 |
| 最大子模块行数 | ≤ 700 行 |
| --dry-run --once 输出 | 与拆分前一致 |
| 无循环导入 | 验证通过 |
| 32 个 public 函数 | hasattr 全 True |
| 全局符号 re-export | `_SHUTDOWN_REQUESTED`, `_START_TIME`, `_PRAXIST`, `_PERSISTABLE_DM`, `VALID_TIER_VALUES` 均可 import |
| **附录 A 覆盖** | 150 顶层函数 + 57 赋值 + 9 别名 + 10 嵌套，全部有目标模块 |
| **§4.2 别名扫描** | 4 种别名形态（sup/S/sv/s）全部覆盖 |

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
| scripts/sup_state.py | ~200 |
| scripts/sup_lifecycle.py | ~200 |
| scripts/sup_provider.py | ~200 |
| scripts/sup_harvest.py | ~500 |
| scripts/sup_evidence.py | ~700 |
| scripts/sup_family.py | ~300 |
| scripts/sup_loops.py | ~680 |
| tests/test_sup_modules.py | ~60 |

### 修改
| 文件 | 说明 |
|------|------|
| scripts/praxist_supervisor.py | 4574 → ≤200 行（re-export shim） |
| **32 个测试文件**（引用 praxist_supervisor） | Patch 目标机械迁移（~245 处 `sup.X` → `actual_module.X`），测试逻辑零改动 |
| tests/test_no_dead_code.py | 文件白名单更新（如有） |

---

## 9. 时间估算（v3.0 修正版，N2 工作量并入）

| 步骤 | 时间 |
|------|------|
| **步骤 0：is_valid_tier 提升**（C4 + N5，含 log 参数化） | 30 min |
| sup_paths | 15 min |
| sup_env | 15 min |
| sup_state（含 _ensure_tokens_baseline 等） | 25 min |
| sup_lifecycle（含 _log_decision + _now_iso） | 30 min |
| sup_provider（含 parse_429_reset） | 25 min |
| sup_evidence（含 VALID_TIER_VALUES + is_valid_tier + 基线重生簇 + 死亡族簇） | 60 min |
| sup_harvest（含 harvest_survivors + _sector_filter_check） | 45 min |
| sup_family | 30 min |
| sup_loops + shim | 60 min |
| **238+7 处 patch 脚本化迁移**（含附录 A 映射 + 4 别名扫描 + N3 别名策略） | 120 min |
| 全量测试 + 修补 | 60 min |
| 迁移窗口协议执行 + 冒烟 | 30 min |
| **总计** | **~11 小时 / 2 个工作日** |

---

## 10. 指纹纪律声明（m5 新增）

本次拆分 **不修改任何 gate/verdict 语义**，所有函数行为、阈值、裁决逻辑保持与拆分前完全一致。因此：

- `protocol_fingerprint` / `_current_protocol_fingerprint` / `_baseline_protocol_fingerprint` **不会 bump**
- 拆分是纯结构性重构（reorganize），不是语义变更（change）
- 若实施过程中意外触碰 verdict 路径或门限计算，须独立 commit + 显式说明 + 触发重生

---

## 11. 参考资料

- scripts/praxist_supervisor.py - 当前 4574 行单文件
- tests/test_supervisor.py - 1873 行主测试
- docs/superpowers/specs/2026-10-08-d4-d5-n10-e1-research-spec.md - D4/D5 前置依赖
- docs/superpowers/reports/2026-10-07-tech-debt-inventory.md - 技术债清单（含已关闭 M5 n_eff）
- docs/superpowers/reports/2026-10-09-m5-supervisor-split-spec-review.md - v1.0 expert review（Reject as-is，13 项修正要求）
- docs/superpowers/reports/2026-10-10-s1-supervisor-split-spec-review.md - v2.0 二次复审（N1-N7，符号清单完备性）
- docs/superpowers/plans/2026-10-07-tech-debt-closure-plan.md - 技术债关闭计划

---

## 附录 A：完整符号→模块映射表（AST 扫描生成）

> 生成方式：Python `ast` 模块扫描 `scripts/praxist_supervisor.py`（4574 行），提取 150 个顶层函数定义、10 个嵌套函数、57 个模块级赋值、9 个导入别名，结合 N1 的 9 项归属修正，得到以下映射表。
> 此表为 §2.4 shim import 清单与 §4.2 patch 映射的**唯一权威源**。

### A.1 顶层函数（150 个）

按行号升序排列，`→` 后为目标模块。

| 函数名 | 行号 | 目标模块 | 备注 |
|--------|------|----------|------|
| fdr_pass_persistable | 28 | sup_family | |
| promote_batch_for_persistence | 43 | sup_family | → fdr_pass_persistable |
| _resolve_praxist_bin | 60 | sup_env | |
| _praxist_bin | 75 | sup_env | → _resolve_praxist_bin |
| _load_dotenv | 95 | sup_env | |
| _check_required_env | 135 | sup_env | |
| family_key_for | 192 | sup_family | |
| register_family_member | 197 | sup_family | |
| seal_research_family | 209 | sup_family | |
| _prereg_field | 214 | sup_family | |
| _find_prereg | 221 | sup_family | → _prereg_field |
| dispatch_confirmation | 228 | sup_family | → _find_prereg, _prereg_field, family_key_for, register_family_member |
| _stamp_member | 266 | sup_family | |
| _seal_if_all_terminal | 279 | sup_family | → seal_research_family |
| finalize_confirmation | 298 | sup_family | → _seal_if_all_terminal, _stamp_member |
| _now_iso | 325 | **sup_lifecycle**（N1 环 C） | 被 _emit_event/_write_stop_json/_write_heartbeat/_log_decision 调用 |
| _requested_covariate | 332 | sup_family | |
| confirmation_queue_row | 340 | sup_family | → _now_iso, _requested_covariate |
| due_confirmations | 360 | sup_family | → _requested_covariate, confirmation_queue_row |
| load_preregistry | 390 | **sup_state**（v3.1 环 F） | 调用方 _maybe_enqueue_confirmations/_sweep_search_promotions/_prereg_confirm_from_ts 均 -> state |
| load_family_members | 401 | sup_family | |
| save_family_members | 418 | sup_family | |
| _merge_family_members | 429 | sup_family | |
| _latest_data_dt | 450 | **sup_state**（v3.1 环 F） | 调用方 _confirm_data_ready/_baseline_reanchor_reason 均 -> state |
| _confirm_data_ready | 477 | sup_family | → _latest_data_dt |
| _confirmation_is_final | 491 | sup_family | |
| _maybe_enqueue_confirmations | 504 | sup_family | → load_covariate_pool（N1 边 G） |
| _finalize_confirmation_verdict | 608 | sup_family | → finalize_confirmation |
| _mark_stop_emitted | 621 | sup_lifecycle | |
| _emit_event | 628 | sup_lifecycle | → _mark_stop_emitted, _now_iso, _write_stop_json |
| _write_stop_json | 659 | sup_lifecycle | → _now_iso |
| _write_heartbeat | 681 | sup_lifecycle | → _now_iso |
| _signal_handler | 692 | sup_lifecycle | |
| _shutdown_exit | 698 | sup_lifecycle | → _emit_event |
| _sleep_interruptible | 710 | sup_lifecycle | |
| _atexit_handler | 720 | sup_lifecycle | → _emit_event |
| _arm_handlers | 748 | sup_lifecycle | |
| parse_429_reset | 758 | **sup_provider**（N1 边 H） | _latest_429_reset 唯一调用方 |
| load_state | 764 | sup_state | → _ensure_tokens_baseline（N1 环 B） |
| save_state | 776 | sup_state | |
| load_goal | 783 | sup_state | |
| _cad_int | 799 | sup_state | |
| _norm_search_policy | 809 | sup_state | |
| _goal_target_symbols | 831 | sup_state | |
| _assert_goal_symbols_contract | 856 | sup_state | → _goal_target_symbols |
| _load_goal_symbols | 871 | sup_state | → _assert_goal_symbols_contract, load_goal |
| _reset_goal_symbols_cache | 883 | sup_state | |
| _env_first | 888 | sup_provider | |
| _failover_configured | 897 | sup_provider | → _env_first |
| _llm_provider | 911 | sup_provider | → load_state |
| _llm_route | 920 | sup_provider | → _llm_provider |
| _praxist_env | 924 | sup_provider | → _env_first, _failover_configured, _llm_provider |
| _failover_model_name | 982 | sup_provider | → _env_first |
| _recorded_run_model | 986 | sup_provider | |
| _failover_can_resume_same_run | 1002 | sup_provider | → _failover_model_name, _recorded_run_model |
| _model_argv | 1014 | sup_provider | → _env_first, _failover_model_name, _llm_provider |
| _provider_state | 1023 | sup_provider | |
| _praxist | 1028 | sup_env | → _praxist_bin |
| _status_rows | 1032 | sup_provider | → _praxist |
| _run_active | 1040 | sup_provider | → _status_rows |
| _active_run_meta | 1043 | sup_provider | → _status_rows |
| _latest_429_reset | 1049 | sup_provider | → parse_429_reset |
| quota_gate | 1061 | sup_loops | → _latest_429_reset |
| symbol_goal_tier | 1087 | sup_evidence | |
| build_snapshot | 1121 | sup_evidence | → _current_protocol_fingerprint, _log_decision, symbol_goal_tier |
| harvest_survivors | 1254 | **sup_harvest**（N7） | → _experiment_fp_for, _now_iso |
| collect_proposed_variant_ids | 1320 | **sup_evidence**（v3.1 环 E） | 调用方 materialize_known_verdicts/_maybe_finish_slow/_main_locked 均 -> evidence |
| _protocol_section_line | 1341 | sup_evidence | |
| materialize_known_verdicts | 1348 | sup_evidence | → _dead_family_lines 等 |
| _verdict_family | 1536 | sup_evidence | |
| _finite_dir_acc | 1541 | sup_evidence | |
| _has_prior_failure | 1550 | sup_evidence | → _is_confirmable_failure（N1 边 E） |
| _effective_clue_lines | 1576 | sup_evidence | → _finite_dir_acc, _verdict_family |
| _cross_matrix_lines | 1634 | sup_evidence | → _protocol_section_line, _verdict_family |
| _prior_class | 1680 | sup_evidence | |
| _old_protocol_prior_lines | 1689 | sup_evidence | → _finite_dir_acc, _prior_class |
| load_covariate_pool | 1744 | sup_evidence | |
| load_symbol_status | 1772 | sup_evidence | |
| _load_evaluator | 1790 | **sup_evidence**（N1 边 I） | 被 harvest_proposals 与 _symbol_n_table 调用 |
| _cross_run_repeat_counts | 1812 | sup_harvest | |
| _is_confirmable_failure | 1859 | **sup_evidence**（N1 边 E） | 被 _has_prior_failure / _sector_filter_check / _covariate_filter_check 调用 |
| _family_confirmatory_counts | 1870 | **sup_evidence**（N1 边 F） | |
| _dead_families | 1893 | **sup_evidence**（N1 边 F） | → _family_confirmatory_counts |
| _dead_family_lines | 1907 | **sup_evidence**（N1 边 F） | → _family_confirmatory_counts, _protocol_section_line |
| _apply_prescreen_score | 1931 | sup_harvest | |
| _prescreen_async | 1967 | sup_harvest | |
| _proposal_priority_score | 2021 | sup_harvest | → _apply_prescreen_score, load_symbol_status |
| _append_backlog | 2102 | sup_harvest | → _now_iso |
| _verdict_sort_key | 2151 | **sup_evidence**（v3.1 环 E） | 调用方 _latest_verdict_per_symbol/_prior_success_row 均在 evidence 域内 |
| _latest_verdict_per_symbol | 2157 | sup_harvest | → _verdict_sort_key |
| _recent_ok_verdicts | 2177 | sup_harvest | |
| _prescreen_plausibility | 2185 | sup_harvest | |
| _sector_filter_check | 2208 | **sup_harvest**（N7） | → _is_confirmable_failure, _latest_verdict_per_symbol |
| _covariate_filter_check | 2247 | sup_harvest | → _is_confirmable_failure |
| _proposal_quality_gate | 2274 | sup_harvest | → _prescreen_plausibility, _recent_ok_verdicts |
| _symbol_has_current_nocov_baseline | 2341 | sup_evidence | → _baseline_protocol_fingerprint, _current_protocol_fingerprint |
| _prior_success_row | 2352 | sup_evidence | → _verdict_sort_key |
| _row_eval_end_ts | 2375 | sup_evidence | |
| _current_window_anchor | 2427 | sup_evidence | → _row_eval_end_ts |
| _today_shanghai | 2444 | sup_evidence | |
| _kline_1h_max_dt | 2457 | sup_evidence | |
| _symbol_data_stale | 2482 | sup_evidence | → _kline_1h_max_dt, _today_shanghai |
| _prior_success_class | 2516 | sup_evidence | |
| _success_delta_gate | 2526 | sup_evidence | |
| _locked_success_rows | 2573 | sup_evidence | → _prior_success_row, _success_delta_gate |
| _locked_window_lines | 2602 | sup_evidence | → _locked_success_rows, _prior_success_class, _row_eval_end_ts |
| harvest_proposals | 2631 | sup_harvest | → _load_evaluator（N1 边 I） |
| materialize_covariate_menu | 2866 | sup_harvest | → _symbol_n_table |
| _valid_n_for_symbol | 2915 | sup_evidence | |
| _experiment_fp_for | 2949 | sup_evidence | |
| _symbol_n_table | 2987 | sup_evidence | → _load_evaluator（N1 边 I）, _valid_n_for_symbol |
| _retest_candidates | 2993 | sup_loops | |
| _active_protocol_snapshot | 3029 | **sup_evidence**（N1 环 A） | → _current_protocol_fingerprint |
| plan_sample_retests | 3034 | sup_loops | → _active_protocol_snapshot |
| _maybe_enqueue_retests | 3060 | sup_loops | → _emit_event, _log_decision, _merge_save, plan_sample_retests |
| _log_decision | 3081 | sup_lifecycle | → _now_iso |
| _read_cpu_hours | 3088 | sup_loops | |
| _ensure_tokens_baseline | 3104 | **sup_state**（N1 环 B） | → _read_token_m, save_state |
| _token_spend_m | 3116 | **sup_state**（N1 环 B） | |
| _token_budget_hit | 3123 | sup_loops | |
| _read_token_m | 3143 | **sup_state**（N1 环 B） | |
| _in_slow_window | 3163 | sup_loops | |
| _deadline_passed | 3173 | sup_loops | |
| _slow_loop_alive | 3182 | sup_loops | |
| _queue_busy | 3199 | sup_loops | |
| _slow_drain_complete | 3202 | sup_loops | → _queue_busy, _slow_loop_alive |
| ensure_phase | 3205 | sup_loops | → _failover_configured, _llm_provider, _queue_busy, _run_active, _slow_loop_alive |
| write_stop_report | 3224 | sup_loops | → _now_iso |
| _merge_save | 3247 | **sup_state**（v3.1 语义内聚） | 调 load_state + save_state，13 个调用点均在 loops 域但语义属 state |
| decide_fast_loop | 3253 | sup_loops | → 17 个函数调用 |
| main | 3524 | sup_loops | → _arm_handlers, _main_locked 等 |
| _harvest_rows | 3579 | sup_loops | → harvest_proposals, load_covariate_pool |
| _commit_search_accepts | 3596 | sup_loops | |
| _sweep_search_stops | 3632 | sup_loops | → _dead_families, _log_decision, _norm_search_policy |
| _append_jsonl | 3660 | sup_loops | |
| _sweep_search_promotions | 3668 | sup_loops | → _append_jsonl, _log_decision, _norm_search_policy, _now_iso, load_preregistry |
| _maybe_harvest | 3719 | sup_loops | → _commit_search_accepts, _harvest_rows, _log_decision, _merge_save, _run_active, load_state, quota_gate, save_state |
| _baseline_protocol_fingerprint | 3769 | sup_evidence | |
| _current_protocol_fingerprint | 3799 | sup_evidence | |
| _archive_baseline_before_regen | 3812 | sup_evidence | |
| _prereg_confirm_from_ts | 3876 | **sup_evidence**（N1 环 D） | → load_preregistry |
| _baseline_reanchor_reason | 3888 | **sup_evidence**（N1 环 D） | → _latest_data_dt, _prereg_confirm_from_ts |
| _guard_confirm_from_ts_after_regen | 3920 | **sup_evidence**（N1 环 D） | → _prereg_confirm_from_ts |
| _regen_baseline_with_archive | 3968 | **sup_evidence**（N1 环 D） | → _archive_baseline_before_regen, _guard_confirm_from_ts_after_regen |
| ensure_baselines | 3988 | sup_evidence | → _baseline_protocol_fingerprint, _baseline_reanchor_reason, _current_protocol_fingerprint, _regen_baseline_with_archive |
| wait_for_batch | 4070 | sup_loops | |
| cleanup_batch_workers | 4127 | sup_loops | |
| _maybe_start_slow_loop | 4142 | sup_loops | → _log_decision, _queue_busy, _slow_loop_alive, load_state, save_state |
| _maybe_finish_slow | 4209 | sup_loops | → 17 个函数调用 |
| _main_locked | 4338 | sup_loops | → 34 个函数调用 |

### A.2 嵌套函数（10 个，随宿主迁移）

| 函数名 | 行号 | 宿主函数 | 目标模块（同宿主） |
|--------|------|----------|-------------------|
| family_for | 522 | _maybe_enqueue_confirmations | sup_family |
| is_valid_tier | 1150 | build_snapshot | sup_evidence（步骤 0 提升为模块级） |
| _da_key | 1496 | materialize_known_verdicts | sup_evidence |
| _run | 1998 | _prescreen_async | sup_harvest |
| _reject | 2674 | harvest_proposals | sup_harvest |
| _resume_argv | 3268 | decide_fast_loop | sup_loops |
| _start_argv | 3275 | decide_fast_loop | sup_loops |
| _plan_resume | 3289 | decide_fast_loop | sup_loops |
| _plan_start | 3306 | decide_fast_loop | sup_loops |
| _cutoffs_at_or_after | 3934 | _guard_confirm_from_ts_after_regen | sup_evidence |

### A.3 模块级赋值（57 个）

| 符号 | 行号 | 目标模块 |
|------|------|----------|
| HERE | 7 | sup_paths |
| FM_ROOT | 8 | sup_paths |
| _PERSISTABLE_DM | 22 | sup_family |
| VALID_TIER_VALUES | 25 | sup_evidence |
| _PRAXIST | 57 | sup_env |
| QUEUE | 80 | sup_paths |
| INPROGRESS | 81 | sup_paths |
| REGISTRY | 82 | sup_paths |
| SEARCH_COMMITMENTS_PATH | 84 | sup_paths |
| STATE_PATH | 85 | sup_paths |
| LOCK_PATH | 86 | sup_paths |
| VERDICTS_INC | 87 | sup_paths |
| POOL_PATH | 88 | sup_paths |
| BACKLOG_PATH | 89 | sup_paths |
| SYMBOL_STATUS_PATH | 90 | sup_paths |
| MENU_INC | 91 | sup_paths |
| REPORT_DIR | 92 | sup_paths |
| STATE_MD | 146 | sup_paths |
| EVENTS_PATH | 147 | sup_paths |
| HEARTBEAT_PATH | 148 | sup_paths |
| STOP_REPORT_JSON | 149 | sup_paths |
| _EVENT_LOCK | 150 | sup_lifecycle |
| _SHUTDOWN_REQUESTED | 151 | sup_lifecycle |
| _RUN_ID | 152 | sup_lifecycle |
| _START_TIME | 153 | sup_lifecycle |
| _STOP_EMITTED | 154 | sup_lifecycle |
| POLL_S | 155 | sup_paths |
| PHASES | 156 | sup_paths |
| RETEST_GATE_N | 171 | sup_paths |
| FAMILY_REGISTRY | 188 | sup_paths |
| PREREGISTRY_PATH | 189 | sup_paths |
| _BASE_COVARIATE | 329 | sup_family |
| _CONFIRM_DATA_TTL_S | 446 | sup_family |
| _CONFIRM_DATA_CACHE | 447 | sup_family |
| _HANDLERS_ARMED | 746 | sup_lifecycle |
| _CADENCE_DEFAULTS | 793 | sup_state |
| _GOAL_YAML_DEFAULT | 852 | sup_state |
| _GOAL_SYMBOLS_CACHE | 853 | sup_state |
| _ev_mod_for_goal | 1803 | sup_state |
| GOAL_SYMBOLS_SET | 1807 | sup_state |
| _CONFIRMATORY_DM | 1848 | sup_family |
| _CONFIRMATION_NOTICE | 1851 | sup_family |
| _CONFIRMATION_NOTICE_TTL_S | 1852 | sup_family |
| _CONFIRM_REDISPATCH | 1855 | sup_family |
| _CONFIRM_REDISPATCH_TTL_S | 1856 | sup_family |
| MIN_QUALITY_SCORE | 2136 | sup_harvest |
| CROSS_MATRIX_MAX_ROWS | 2138 | sup_harvest |
| OLD_PRIORS_MAX_ROWS | 2139 | sup_harvest |
| LOCKED_WINDOW_MAX_ROWS | 2140 | sup_evidence |
| SUCCESS_DELTA_MIN_CHARS | 2142 | sup_evidence |
| STALE_DATA_DAYS | 2143 | sup_evidence |
| COV_CROSS_FAIL_MIN | 2146 | sup_harvest |
| SYMBOL_FAIL_WINDOW | 2147 | sup_harvest |
| COV_FAIL_WINDOW | 2148 | sup_harvest |
| _FP_WEIGHTS_CACHE | 2945 | sup_evidence |
| _FP_TARGET_CACHE | 2946 | sup_evidence |
| _BASELINE_STALENESS_MAX_H | 3873 | sup_evidence |

### A.4 导入别名（9 个）

| 别名 | 原始模块 | 行号 | 被哪些 sup_* 模块引用 |
|------|----------|------|---------------------|
| rl | registry_lib | 11 | sup_family, sup_evidence, sup_harvest, sup_loops |
| ef | cascade.experiment_fingerprint | 14 | sup_evidence, sup_family, sup_harvest |
| st | search_trees | 15 | sup_evidence, sup_harvest, sup_loops, sup_provider, sup_state |
| _fam_all_terminal | cascade.research_family | 179 | sup_family |
| _fam_default_key | cascade.research_family | 179 | sup_family |
| _fam_report_scope | cascade.research_family | 179 | ~~sup_family~~（死导入，零函数引用，拆分可丢弃） |
| _fam_make_member | cascade.research_family | 179 | sup_family |
| _fam_register_member | cascade.research_family | 179 | sup_family |
| _fam_seal_family | cascade.research_family | 179 | sup_family |

> **v3.1 补充**：以下 4 个非 stdlib 模块级 `from X import Y` 导入（非别名形态）也随宿主函数迁移，无需单独 shim 行：`evaluate_goal`（goal_dsl）、`ALLOWED_FAMILIES`（cascade.cov_family）、`resolve_cov_family`（cascade.cov_family）、`search_promote`（search_promote）。

### A.5 映射统计（v3.1 重生成，基于 A.1/A.3 实际计数 + F1/F2 修正）

| 目标模块 | 顶层函数数 | 赋值数 | 嵌套函数 | 合计符号数 |
|----------|-----------|--------|----------|-----------|
| sup_paths | 0 | 23 | 0 | 23 |
| sup_env | 5 | 1 | 0 | 6 |
| sup_state | 15 | 5 | 0 | 20 |
| sup_lifecycle | 11 | 6 | 0 | 17 |
| sup_provider | 15 | 0 | 0 | 15 |
| sup_harvest | 14 | 6 | 2 | 22 |
| sup_evidence | 43 | 7 | 3 | 53 |
| sup_family | 21 | 9 | 1 | 31 |
| sup_loops | 26 | 0 | 4 | 30 |
| **顶层函数总计** | **150** | | | |
| **赋值总计** | | **57** | | |
| **嵌套函数总计** | | | **10** | |
| **全部符号** | **217**（150+57+10） | | | |

> sup_loops 的 26 个顶层函数包含：quota_gate, _read_cpu_hours, _token_budget_hit, _in_slow_window, _deadline_passed, _slow_loop_alive, _queue_busy, _slow_drain_complete, ensure_phase, write_stop_report, decide_fast_loop, main, _harvest_rows, _commit_search_accepts, _sweep_search_stops, _append_jsonl, _sweep_search_promotions, _maybe_harvest, wait_for_batch, cleanup_batch_workers, _maybe_start_slow_loop, _maybe_finish_slow, _main_locked, _retest_candidates 等（见 A.1 完整列表；_merge_save 已迁至 sup_state）。

---

*SPEC v3.1, 2026-10-10, S1 Supervisor Split（经三次 AST 全量复审，N1-N7 + F1-F8 全部修正；机械级修订，无架构变更）*
