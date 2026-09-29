import pytest
import numpy as np
import pandas as pd
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
lgb = pytest.importorskip("lightgbm")
from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward

def _synth_matrix(n=400):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "bar_idx": np.arange(n),
        "hourly_slope": rng.normal(0, 0.001, n),
        "rsi_state": rng.integers(-2, 3, n).astype(float),
        "timesfm_pure_pred": rng.normal(0, 0.01, n),
        "hurst": rng.normal(0, 0.5, n),
        "Y": rng.normal(0, 0.02, n),
        "weight": rng.uniform(1, 200, n),
    })
    return df

def test_walkforward_output_schema():
    mat = _synth_matrix(400)
    eval_bars = list(range(50, 400, 10))  # 35 eval points
    out = train_lgbm_walkforward(mat, eval_bars, refit_every=5)
    assert set(["bar_idx","pred_return","pred_move","actual_move"]).issubset(out.columns)
    assert len(out) == len(eval_bars)
    # 合成测试无 close, 检查 pred_return 范围合理
    assert out["pred_return"].abs().max() < 1.0

def test_walkforward_no_train_test_overlap():
    """eval bar t 的预测只用 t 之前训练数据"""
    mat = _synth_matrix(400)
    eval_bars = [200]
    out = train_lgbm_walkforward(mat, eval_bars, refit_every=1)
    # 篡改 t=200 处的 Y (标签), 预测应不变 (训练不含 t)
    mat_b = mat.copy()
    mat_b.loc[mat_b["bar_idx"] == 200, "Y"] = 999.0
    out_b = train_lgbm_walkforward(mat_b, eval_bars, refit_every=1)
    assert abs(out["pred_return"].iloc[0] - out_b["pred_return"].iloc[0]) < 1e-6

from scripts.a2_p1_lgbm_baseline import evaluate_gate, paired_bootstrap_ev_ci

def test_paired_bootstrap_ci_basic():
    """LGBM 明显优于 scheme 时, EV 差 CI 下界 > 0"""
    rng = np.random.default_rng(1)
    n = 200
    actual = rng.normal(0, 10, n)
    # LGBM: 方向对, 赚; scheme: 随机, 不赚
    lgbm_pnl = np.abs(actual) - 2  # 方向对: |actual| - 滑点 = 净盈利
    scheme_pnl = rng.normal(0, 5, n)
    lo, hi = paired_bootstrap_ev_ci(lgbm_pnl - scheme_pnl, n_boot=500)
    assert lo > 0  # LGBM 显著优

def test_evaluate_gate_go():
    rng = np.random.default_rng(2)
    n = 200
    actual = rng.normal(0, 10, n)
    base = np.full(n, 3000.0)
    atr = np.full(n, 10.0)
    lgbm_pred = np.sign(actual) * 5  # 方向对
    scheme_pred = rng.normal(0, 1, n)  # 弱
    pure_pred = rng.normal(0, 1, n)
    verdict = evaluate_gate(lgbm_pred, pure_pred, scheme_pred, actual, base, atr, tick_size=1.0)
    assert verdict["gate"] == "GO"
    assert verdict["lgbm_metrics"]["EV"] > 0
    assert verdict["lgbm_metrics"]["PF"] > verdict["scheme_metrics"]["PF"]

def test_evaluate_gate_no_go():
    rng = np.random.default_rng(3)
    n = 200
    actual = rng.normal(0, 10, n)
    base = np.full(n, 3000.0); atr = np.full(n, 10.0)
    # LGBM 不优于 scheme
    lgbm_pred = rng.normal(0, 1, n)
    scheme_pred = np.sign(actual) * 5  # scheme 强
    pure_pred = rng.normal(0, 1, n)
    verdict = evaluate_gate(lgbm_pred, pure_pred, scheme_pred, actual, base, atr, tick_size=1.0)
    assert verdict["gate"] == "NO-GO"

def _clear_stale_locks(root):
    """删除持有者进程已死的 a2_p1 锁。

    崩溃残留的锁会永久卡住 test_smoke_ss_end_to_end (锁按 O_EXCL 建, 不自动释放)。
    与 exclusive_result_lock 的"不自动清理"契约一致: 这里只清**进程已死**的,
    活着的锁 (含别人的进程) 一律保留。
    """
    import json
    import os
    for lock in pathlib.Path(root, "reports").rglob("*.lock"):
        try:
            pid = int(json.loads(lock.read_text(encoding="utf-8"))["pid"])
        except Exception:
            continue  # 不是锁元数据, 不动
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            lock.unlink()
        except PermissionError:
            pass  # 进程存在但不属于当前用户 -> 视为活着


@pytest.mark.slow
def test_smoke_ss_end_to_end():
    """端到端: ss 品种, --max-points 100, 验证落盘 + 报告生成 + LGBM 训练数据充足"""
    import subprocess, sys
    from data.config import FM_ROOT
    # build_dense_feature_matrix 用 pandas.to_parquet 做中间落盘 (归档的 A2 Track B),
    # 需 pyarrow/fastparquet 之一。venv 未装 -> 显式 skip, 与本文件 lightgbm 的处理一致。
    pytest.importorskip("pyarrow", reason="smoke 路径需 parquet 引擎 (未安装 pyarrow)")
    _clear_stale_locks(FM_ROOT)
    r = subprocess.run(
        [sys.executable,
         "scripts/a2_p1_lgbm_baseline.py", "ss", "--max-points", "100",
         "--dense-step", "24", "--refit-every", "5"],
        capture_output=True, text=True, cwd=str(FM_ROOT), timeout=1800,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    # 验证 JSONL 落盘
    import pathlib, json
    out_jsonl = pathlib.Path("reports/a2_p1_baseline_results.jsonl")
    assert out_jsonl.exists()
    lines = out_jsonl.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert "gate" in rec and "lgbm_metrics" in rec
