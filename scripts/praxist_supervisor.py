#!/usr/bin/env python3
"""三环监督环: goal 判定 + 两环调度, 纯 Python 0 token"""
import os
import sys

_BOOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BOOT_DIR)
sys.path.insert(0, os.path.dirname(_BOOT_DIR))
import sup_paths
import time
import subprocess
import logging
import registry_lib as rl
import sup_env
import sup_state
import sup_lifecycle
import sup_provider
import sup_evidence
import sup_harvest
import sup_family
import sup_loops

_HOMES: dict[str, object] = {  # name -> defining module
    "HERE": sup_paths, "FM_ROOT": sup_paths, "QUEUE": sup_paths,
    "INPROGRESS": sup_paths, "REGISTRY": sup_paths,
    "SEARCH_COMMITMENTS_PATH": sup_paths, "STATE_PATH": sup_paths,
    "LOCK_PATH": sup_paths, "VERDICTS_INC": sup_paths, "POOL_PATH": sup_paths,
    "BACKLOG_PATH": sup_paths, "SYMBOL_STATUS_PATH": sup_paths, "MENU_INC": sup_paths,
    "REPORT_DIR": sup_paths, "STATE_MD": sup_paths, "EVENTS_PATH": sup_paths,
    "HEARTBEAT_PATH": sup_paths, "STOP_REPORT_JSON": sup_paths, "POLL_S": sup_paths,
    "PHASES": sup_paths, "RETEST_GATE_N": sup_paths, "FAMILY_REGISTRY": sup_paths,
    "PREREGISTRY_PATH": sup_paths,
    "_resolve_praxist_bin": sup_env, "_praxist_bin": sup_env, "_load_dotenv": sup_env,
    "_check_required_env": sup_env, "_praxist": sup_env, "_PRAXIST": sup_env,
    "load_preregistry": sup_state, "_CONFIRM_DATA_TTL_S": sup_state,
    "_CONFIRM_DATA_CACHE": sup_state, "_latest_data_dt": sup_state,
    "load_state": sup_state, "save_state": sup_state, "load_goal": sup_state,
    "_CADENCE_DEFAULTS": sup_state, "_cad_int": sup_state,
    "_norm_search_policy": sup_state, "_goal_target_symbols": sup_state,
    "_GOAL_YAML_DEFAULT": sup_state, "_GOAL_SYMBOLS_CACHE": sup_state,
    "_assert_goal_symbols_contract": sup_state, "_load_goal_symbols": sup_state,
    "_reset_goal_symbols_cache": sup_state, "GOAL_SYMBOLS_SET": sup_state,
    "_ensure_tokens_baseline": sup_state, "_token_spend_m": sup_state,
    "_read_token_m": sup_state, "_merge_save": sup_state,
    "_EVENT_LOCK": sup_lifecycle, "_SHUTDOWN_REQUESTED": sup_lifecycle,
    "_RUN_ID": sup_lifecycle, "_START_TIME": sup_lifecycle,
    "_STOP_EMITTED": sup_lifecycle, "_now_iso": sup_lifecycle,
    "_mark_stop_emitted": sup_lifecycle, "_emit_event": sup_lifecycle,
    "_write_stop_json": sup_lifecycle, "_write_heartbeat": sup_lifecycle,
    "_signal_handler": sup_lifecycle, "_shutdown_exit": sup_lifecycle,
    "_sleep_interruptible": sup_lifecycle, "_atexit_handler": sup_lifecycle,
    "_HANDLERS_ARMED": sup_lifecycle, "_arm_handlers": sup_lifecycle,
    "_log_decision": sup_lifecycle,
    "parse_429_reset": sup_provider, "_env_first": sup_provider,
    "_failover_configured": sup_provider, "_llm_provider": sup_provider,
    "_llm_route": sup_provider, "_praxist_env": sup_provider,
    "_failover_model_name": sup_provider, "_recorded_run_model": sup_provider,
    "_failover_can_resume_same_run": sup_provider, "_model_argv": sup_provider,
    "_provider_state": sup_provider, "_status_rows": sup_provider,
    "_run_active": sup_provider, "_active_run_meta": sup_provider,
    "_latest_429_reset": sup_provider,
    "VALID_TIER_VALUES": sup_evidence, "is_valid_tier": sup_evidence,
    "symbol_goal_tier": sup_evidence, "build_snapshot": sup_evidence,
    "collect_proposed_variant_ids": sup_evidence,
    "_protocol_section_line": sup_evidence, "materialize_known_verdicts": sup_evidence,
    "_verdict_family": sup_evidence, "_finite_dir_acc": sup_evidence,
    "_has_prior_failure": sup_evidence, "_effective_clue_lines": sup_evidence,
    "_cross_matrix_lines": sup_evidence, "_prior_class": sup_evidence,
    "_old_protocol_prior_lines": sup_evidence, "load_covariate_pool": sup_evidence,
    "load_symbol_status": sup_evidence, "_load_evaluator": sup_evidence,
    "_ev_mod_for_goal": sup_evidence, "_CONFIRMATORY_DM": sup_evidence,
    "_is_confirmable_failure": sup_evidence,
    "_family_confirmatory_counts": sup_evidence, "_dead_families": sup_evidence,
    "_dead_family_lines": sup_evidence, "CROSS_MATRIX_MAX_ROWS": sup_evidence,
    "OLD_PRIORS_MAX_ROWS": sup_evidence, "LOCKED_WINDOW_MAX_ROWS": sup_evidence,
    "SUCCESS_DELTA_MIN_CHARS": sup_evidence, "STALE_DATA_DAYS": sup_evidence,
    "_verdict_sort_key": sup_evidence,
    "_symbol_has_current_nocov_baseline": sup_evidence,
    "_prior_success_row": sup_evidence, "_row_eval_end_ts": sup_evidence,
    "_current_window_anchor": sup_evidence, "_today_shanghai": sup_evidence,
    "_kline_1h_max_dt": sup_evidence, "_symbol_data_stale": sup_evidence,
    "_prior_success_class": sup_evidence, "_success_delta_gate": sup_evidence,
    "_locked_success_rows": sup_evidence, "_locked_window_lines": sup_evidence,
    "_valid_n_for_symbol": sup_evidence, "_FP_WEIGHTS_CACHE": sup_evidence,
    "_FP_TARGET_CACHE": sup_evidence, "_experiment_fp_for": sup_evidence,
    "_symbol_n_table": sup_evidence, "_active_protocol_snapshot": sup_evidence,
    "_baseline_protocol_fingerprint": sup_evidence,
    "_current_protocol_fingerprint": sup_evidence,
    "_archive_baseline_before_regen": sup_evidence,
    "_BASELINE_STALENESS_MAX_H": sup_evidence, "_prereg_confirm_from_ts": sup_evidence,
    "_baseline_reanchor_reason": sup_evidence,
    "_guard_confirm_from_ts_after_regen": sup_evidence,
    "_regen_baseline_with_archive": sup_evidence, "ensure_baselines": sup_evidence,
    "harvest_survivors": sup_harvest, "_cross_run_repeat_counts": sup_harvest,
    "_apply_prescreen_score": sup_harvest, "_prescreen_async": sup_harvest,
    "_proposal_priority_score": sup_harvest, "_append_backlog": sup_harvest,
    "MIN_QUALITY_SCORE": sup_harvest, "COV_CROSS_FAIL_MIN": sup_harvest,
    "SYMBOL_FAIL_WINDOW": sup_harvest, "COV_FAIL_WINDOW": sup_harvest,
    "_latest_verdict_per_symbol": sup_harvest, "_recent_ok_verdicts": sup_harvest,
    "_prescreen_plausibility": sup_harvest, "_sector_filter_check": sup_harvest,
    "_covariate_filter_check": sup_harvest, "_proposal_quality_gate": sup_harvest,
    "harvest_proposals": sup_harvest, "materialize_covariate_menu": sup_harvest,
    "_PERSISTABLE_DM": sup_family, "fdr_pass_persistable": sup_family,
    "promote_batch_for_persistence": sup_family, "family_key_for": sup_family,
    "register_family_member": sup_family, "seal_research_family": sup_family,
    "_prereg_field": sup_family, "_find_prereg": sup_family,
    "dispatch_confirmation": sup_family, "_stamp_member": sup_family,
    "_seal_if_all_terminal": sup_family, "finalize_confirmation": sup_family,
    "_BASE_COVARIATE": sup_family, "_requested_covariate": sup_family,
    "confirmation_queue_row": sup_family, "due_confirmations": sup_family,
    "load_family_members": sup_family, "save_family_members": sup_family,
    "_merge_family_members": sup_family, "_confirm_data_ready": sup_family,
    "_confirmation_is_final": sup_family, "_maybe_enqueue_confirmations": sup_family,
    "_finalize_confirmation_verdict": sup_family, "_CONFIRMATION_NOTICE": sup_family,
    "_CONFIRMATION_NOTICE_TTL_S": sup_family, "_CONFIRM_REDISPATCH": sup_family,
    "_CONFIRM_REDISPATCH_TTL_S": sup_family,
    "quota_gate": sup_loops, "_retest_candidates": sup_loops,
    "plan_sample_retests": sup_loops, "_maybe_enqueue_retests": sup_loops,
    "_read_cpu_hours": sup_loops, "_token_budget_hit": sup_loops,
    "_in_slow_window": sup_loops, "_deadline_passed": sup_loops,
    "_slow_loop_alive": sup_loops, "_queue_busy": sup_loops,
    "_slow_drain_complete": sup_loops, "ensure_phase": sup_loops,
    "write_stop_report": sup_loops, "decide_fast_loop": sup_loops, "main": sup_loops,
    "_harvest_rows": sup_loops, "_commit_search_accepts": sup_loops,
    "_sweep_search_stops": sup_loops, "_append_jsonl": sup_loops,
    "_sweep_search_promotions": sup_loops, "_maybe_harvest": sup_loops,
    "wait_for_batch": sup_loops, "cleanup_batch_workers": sup_loops,
    "_maybe_start_slow_loop": sup_loops, "_maybe_finish_slow": sup_loops,
    "_main_locked": sup_loops, "evaluate_goal": sup_loops,
}


def __getattr__(name):
    mod = _HOMES.get(name)
    if mod is None:
        raise AttributeError(name)
    return getattr(mod, name)


__all__ = [
    "main", "decide_fast_loop", "write_stop_report", "ensure_phase", "quota_gate",
    "build_snapshot", "harvest_proposals", "harvest_survivors",
    "materialize_known_verdicts", "materialize_covariate_menu",
    "collect_proposed_variant_ids", "load_covariate_pool", "load_symbol_status",
    "load_state", "save_state", "load_goal", "load_preregistry", "load_family_members",
    "save_family_members", "family_key_for", "register_family_member",
    "seal_research_family", "dispatch_confirmation", "finalize_confirmation",
    "due_confirmations", "confirmation_queue_row", "fdr_pass_persistable",
    "promote_batch_for_persistence", "parse_429_reset", "ensure_baselines",
    "symbol_goal_tier", "plan_sample_retests", "wait_for_batch",
    "cleanup_batch_workers", "is_valid_tier", "VALID_TIER_VALUES", "FM_ROOT", "HERE",
    "QUEUE", "INPROGRESS", "REGISTRY", "STATE_PATH", "LOCK_PATH", "VERDICTS_INC",
    "POOL_PATH", "BACKLOG_PATH", "SYMBOL_STATUS_PATH", "MENU_INC", "REPORT_DIR",
    "SEARCH_COMMITMENTS_PATH", "STATE_MD", "EVENTS_PATH", "HEARTBEAT_PATH",
    "STOP_REPORT_JSON", "RETEST_GATE_N", "FAMILY_REGISTRY", "PREREGISTRY_PATH",
    "_SHUTDOWN_REQUESTED", "_START_TIME", "_PRAXIST", "_PERSISTABLE_DM",
    "_STOP_EMITTED", "_RUN_ID", "_EVENT_LOCK", "_HANDLERS_ARMED", "_CADENCE_DEFAULTS",
    "_GOAL_YAML_DEFAULT", "_GOAL_SYMBOLS_CACHE", "_ev_mod_for_goal", "GOAL_SYMBOLS_SET",
    "_CONFIRM_DATA_TTL_S", "_CONFIRM_DATA_CACHE", "_CONFIRMATION_NOTICE",
    "_CONFIRMATION_NOTICE_TTL_S", "_CONFIRM_REDISPATCH", "_CONFIRM_REDISPATCH_TTL_S",
    "_CONFIRMATORY_DM", "_BASE_COVARIATE", "_FP_WEIGHTS_CACHE", "_FP_TARGET_CACHE",
    "MIN_QUALITY_SCORE", "CROSS_MATRIX_MAX_ROWS", "OLD_PRIORS_MAX_ROWS",
    "LOCKED_WINDOW_MAX_ROWS", "SUCCESS_DELTA_MIN_CHARS", "STALE_DATA_DAYS",
    "COV_CROSS_FAIL_MIN", "SYMBOL_FAIL_WINDOW", "COV_FAIL_WINDOW",
    "_BASELINE_STALENESS_MAX_H", "PHASES", "POLL_S",
]


if __name__ == "__main__":
    raise SystemExit(sup_loops.main())
