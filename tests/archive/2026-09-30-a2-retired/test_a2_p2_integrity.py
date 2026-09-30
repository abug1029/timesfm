"""A2-P2 残差叠加架构测试"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from pathlib import Path
from scripts.a2_p1_runtime import RunConfig
from scripts.a2_p2_worker import compute_residual_target, stack_predictions


def test_run_config_a2_p2_paths():
    root = Path("D:/FlyBuddy/fm_a")
    cfg = RunConfig.for_run("a2-p2", ["fg"], root)
    assert cfg.results_dir == root / "reports/a2_p2_results"
    assert cfg.logs_dir == root / "reports/a2_p2_logs"
    assert cfg.report_path == root / "reports/research/20260807_a2_p2_verdict.md"
    assert cfg.features_dir == root / "reports/a2_p1_features"
    assert cfg.results_dir != RunConfig.for_run("a2-p1", ["fg"], root).results_dir
    assert cfg.results_dir != RunConfig.for_run("a2-p1.1", ["fg"], root).results_dir


def test_run_config_a2_p2_features_dir_shared_with_a2_p1():
    root = Path("D:/FlyBuddy/fm_a")
    p2 = RunConfig.for_run("a2-p2", ["fg"], root)
    p1 = RunConfig.for_run("a2-p1", ["fg"], root)
    p11 = RunConfig.for_run("a2-p1.1", ["fg"], root)
    assert p2.features_dir == p1.features_dir  # 共享 TimesFM 缓存
    assert p2.features_dir == p11.features_dir


def test_residual_target_is_actual_minus_pure_pred():
    df = pd.DataFrame({
        "Y": [0.10, -0.05, 0.0],
        "timesfm_pure_pred": [0.04, -0.02, 0.01],
    })
    out = compute_residual_target(df)
    assert "Y_residual" in out.columns
    np.testing.assert_allclose(out["Y_residual"].values, [0.06, -0.03, -0.01])


def test_residual_target_handles_nan_pure_pred():
    df = pd.DataFrame({
        "Y": [0.10, 0.05],
        "timesfm_pure_pred": [np.nan, 0.02],
    })
    out = compute_residual_target(df)
    assert np.isnan(out["Y_residual"].iloc[0])
    np.testing.assert_allclose(out["Y_residual"].iloc[1], 0.03)


def test_stack_predictions_adds_residual_to_base():
    base = np.array([0.04, -0.02, 0.01])
    residual = np.array([0.01, 0.005, -0.002])
    stacked = stack_predictions(base, residual)
    np.testing.assert_allclose(stacked, [0.05, -0.015, 0.008])


def test_train_lgbm_walkforward_accepts_target_col():
    import inspect
    from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward
    sig = inspect.signature(train_lgbm_walkforward)
    assert "target_col" in sig.parameters
    assert sig.parameters["target_col"].default == "Y"


def test_a2_p2_worker_main_exists():
    from scripts.a2_p2_worker import run_worker
    assert callable(run_worker)


def test_a2_p2_worker_uses_residual_target_in_source():
    import pathlib
    src = pathlib.Path("scripts/a2_p2_worker.py").read_text(encoding="utf-8")
    assert "compute_residual_target" in src
    assert "stack_predictions" in src
    assert "target_col" in src
    assert "stacked_pred_move" in src


# ═══════════════════════════════════════════════════════════
# A2-P2 runtime 兼容性测试 (Task 3.5 HIGH fix)
# ═══════════════════════════════════════════════════════════

from scripts.a2_p1_runtime import (
    _IMMUTABLE_FIELDS,
    append_unique_record,
    validate_jsonl_records,
)


def test_immutable_fields_include_a2_p2_fields():
    """_IMMUTABLE_FIELDS 包含 A2-P2 特有的堆叠预测字段。"""
    assert "stacked_pred_move" in _IMMUTABLE_FIELDS
    assert "lgbm_residual_pred_move" in _IMMUTABLE_FIELDS
    # A2-P1 字段保留 (向后兼容)
    assert "lgbm_pred_move" in _IMMUTABLE_FIELDS


def test_append_unique_record_a2_p2_idempotent(tmp_path):
    """A2-P2 记录的幂等追加: 同 bar_idx 同字段应静默跳过。"""
    path = tmp_path / "a2p2.jsonl"
    rec = {
        "bar_idx": 480,
        "run_id": "a2-p2",
        "symbol": "FG",
        "version": "test",
        "pure_pred_move": 1.0,
        "scheme_pred_move": 2.0,
        "stacked_pred_move": 1.5,
        "lgbm_residual_pred_move": 0.5,
        "actual_move": 1.3,
        "base_price": 100.0,
        "atr": 2.0,
    }
    append_unique_record(path, rec)
    append_unique_record(path, rec)  # 幂等跳过
    lines = [l for l in path.read_text().strip().split("\n") if l.strip()]
    assert len(lines) == 1


def test_append_unique_record_a2_p2_detects_conflict(tmp_path):
    """A2-P2 记录的不可变字段冲突应报错。"""
    import pytest
    path = tmp_path / "a2p2.jsonl"
    rec1 = {
        "bar_idx": 480,
        "run_id": "a2-p2",
        "symbol": "FG",
        "version": "test",
        "pure_pred_move": 1.0,
        "scheme_pred_move": 2.0,
        "stacked_pred_move": 1.5,
        "lgbm_residual_pred_move": 0.5,
        "actual_move": 1.3,
        "base_price": 100.0,
        "atr": 2.0,
    }
    rec2 = dict(rec1, stacked_pred_move=9.9)  # 冲突
    append_unique_record(path, rec1)
    with pytest.raises(ValueError, match="conflicting"):
        append_unique_record(path, rec2)


def test_validate_a2_p2_records_pass():
    """A2-P2 记录 (有 stacked_pred_move + lgbm_residual_pred_move，无 lgbm_pred_move) 应通过校验。"""
    rows = [{
        "bar_idx": 480,
        "run_id": "a2-p2",
        "symbol": "FG",
        "version": "test",
        "pure_pred_move": 1.0,
        "scheme_pred_move": 2.0,
        "stacked_pred_move": 1.5,
        "lgbm_residual_pred_move": 0.5,
        "actual_move": 1.3,
        "base_price": 100.0,
        "atr": 2.0,
    }]
    result = validate_jsonl_records(rows, [480], "a2-p2", "fg")
    assert result.ok, f"A2-P2 validation failed: {result.errors}"


def test_validate_a2_p1_records_still_pass():
    """A2-P1 记录 (有 lgbm_pred_move) 仍应通过校验 (向后兼容)。"""
    rows = [{
        "bar_idx": 480,
        "run_id": "a2-p1",
        "symbol": "SS",
        "version": "test",
        "pure_pred_move": 1.0,
        "scheme_pred_move": 2.0,
        "lgbm_pred_move": 1.8,
        "actual_move": 1.3,
        "base_price": 100.0,
        "atr": 2.0,
    }]
    result = validate_jsonl_records(rows, [480], "a2-p1", "ss")
    assert result.ok, f"A2-P1 validation failed: {result.errors}"


def test_validate_a2_p2_records_reject_missing_stacked():
    """A2-P2 run_id 下缺少 stacked_pred_move 应报错。"""
    rows = [{
        "bar_idx": 480,
        "run_id": "a2-p2",
        "symbol": "FG",
        "version": "test",
        "pure_pred_move": 1.0,
        "scheme_pred_move": 2.0,
        # 缺少 stacked_pred_move 和 lgbm_residual_pred_move
        "actual_move": 1.3,
        "base_price": 100.0,
        "atr": 2.0,
    }]
    result = validate_jsonl_records(rows, [480], "a2-p2", "fg")
    assert not result.ok
    assert any("stacked_pred_move" in e for e in result.errors)


def test_validate_unknown_run_id_rejected():
    """未知 run_id 应报错 (fail-closed, 防止拼写错误绕过 LGBM 校验)。"""
    rows = [{
        "bar_idx": 480,
        "run_id": "a2-p11",  # 拼写错误
        "symbol": "FG",
        "version": "test",
        "pure_pred_move": 1.0,
        "scheme_pred_move": 2.0,
        "lgbm_pred_move": 1.5,
        "actual_move": 1.3,
        "base_price": 100.0,
        "atr": 2.0,
    }]
    result = validate_jsonl_records(rows, [480], "a2-p11", "fg")
    assert not result.ok
    assert any("unknown run_id" in e for e in result.errors)


def test_a2_p2_worker_no_redundant_train_import():
    """run_worker 不应冗余导入 train_lgbm_walkforward (仅 _run_worker_core 需要)。"""
    src = pathlib.Path("scripts/a2_p2_worker.py").read_text(encoding="utf-8")
    # 找到 run_worker 函数体 (从 def run_worker 到下一个 def 或文件末尾)
    import re
    match = re.search(r'def run_worker\(.*?\n(?=def )', src, re.DOTALL)
    assert match, "run_worker function not found"
    run_worker_body = match.group(0)
    # run_worker 不应导入 train_lgbm_walkforward
    assert "train_lgbm_walkforward" not in run_worker_body, \
        "run_worker should not import train_lgbm_walkforward (redundant with _run_worker_core)"


def test_a2_p2_orchestrator_uses_run_level_lock():
    import pathlib
    src = pathlib.Path("scripts/a2_p2_orchestrator.py").read_text(encoding="utf-8")
    assert "exclusive_result_lock" in src
    assert "a2-p2" in src
    assert "a2_p2_worker.py" in src


def test_a2_p2_report_gate_uses_stacked_vs_scheme():
    import pathlib
    src = pathlib.Path("scripts/a2_p2_generate_report.py").read_text(encoding="utf-8")
    assert "stacked_pred_move" in src
    assert "evaluate_gate" in src
    assert "--run-id" in src
    assert "a2-p2" in src


def test_a2_p2_report_fail_closed_on_missing_symbol(tmp_path):
    import pytest
    from scripts.a2_p1_runtime import RunConfig
    from scripts.a2_p2_generate_report import generate_report
    cfg = RunConfig.for_run("a2-p2", ["fg"], tmp_path)
    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    # 不写任何 JSONL → fail-closed
    with pytest.raises(RuntimeError):
        generate_report(cfg)
