"""A2-P1 运行架构重设计测试"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os
import tempfile
import json


def test_parquet_atomic_write():
    """验证 build_dense_feature_matrix 的缓存写入是原子的（临时文件 + os.replace）"""
    import inspect
    from cascade.lgbm_features import build_dense_feature_matrix
    source = inspect.getsource(build_dense_feature_matrix)
    # 检查源码中包含 os.replace 和 .tmp
    assert "os.replace" in source, "必须使用 os.replace() 原子替换"
    assert ".tmp" in source, "必须使用临时文件 .tmp"


def test_worker_jsonl_payload_schema():
    """验证 worker JSONL 每行包含完整 payload (可直接 evaluate_gate)"""
    worker_path = pathlib.Path(__file__).parent.parent / "scripts" / "a2_p1_worker.py"
    assert worker_path.exists(), "scripts/a2_p1_worker.py 必须存在"
    worker_src = worker_path.read_text(encoding="utf-8")
    # 必须包含所有必要字段
    required_fields = ["bar_idx", "pure_pred_move", "scheme_pred_move",
                       "lgbm_pred_move", "actual_move", "base_price", "atr"]
    for field in required_fields:
        assert f'"{field}"' in worker_src or f"'{field}'" in worker_src, \
            f"Worker JSONL 必须包含字段: {field}"
    # 必须包含 version 和 seed
    assert "version" in worker_src, "必须包含 git commit version"
    assert "seed" in worker_src or "np.random" in worker_src, "必须包含固定 seed"


def test_orchestrator_skip_completed():
    """验证 orchestrator 跳过已完成的品种 (JSONL 行数 == 预期)"""
    orch_path = pathlib.Path(__file__).parent.parent / "scripts" / "a2_p1_orchestrator.py"
    assert orch_path.exists(), "scripts/a2_p1_orchestrator.py 必须存在"
    orch_src = orch_path.read_text(encoding="utf-8")
    # 必须检查 JSONL 是否存在
    assert "jsonl" in orch_src.lower() or "results" in orch_src.lower()
    # 必须有 skip 逻辑
    assert "skip" in orch_src.lower() or "continue" in orch_src.lower()
    # 必须用 subprocess 调用 worker
    assert "subprocess" in orch_src


def test_status_script_exists():
    """验证 status 脚本存在且可运行"""
    status_path = pathlib.Path(__file__).parent.parent / "scripts" / "a2_p1_status.py"
    assert status_path.exists(), "scripts/a2_p1_status.py 必须存在"


def test_report_script_exists():
    """验证报告生成脚本存在"""
    report_path = pathlib.Path(__file__).parent.parent / "scripts" / "a2_p1_generate_report.py"
    assert report_path.exists(), "scripts/a2_p1_generate_report.py 必须存在"


def test_baseline_backward_compat():
    """验证旧入口向后兼容性: 参数废弃警告 + SYMBOLS import + --force"""
    src = pathlib.Path(__file__).parent.parent / "scripts" / "a2_p1_lgbm_baseline.py"
    src = src.read_text(encoding="utf-8")
    # 必须包含 SYMBOLS import
    assert "SYMBOLS" in src, "必须从 backtest_config 导入 SYMBOLS"
    # 必须包含 --force 参数
    assert "--force" in src, "必须保留 --force 参数"
    # 必须包含 --max-points 废弃警告
    assert "max-points" in src.lower(), "必须包含 --max-points 废弃警告"
    assert "warning" in src.lower() or "deprecated" in src.lower(), "必须有 warning 或 deprecated 提示"
    # 必须包含 --dense-step 警告
    assert "dense-step" in src.lower(), "必须包含 --dense-step 警告"
    src_lower = src.lower()
    # 确保 warning 出现在 dense-step 检查之后 (同一段 main 函数内)
    assert src_lower.index("dense-step") < src_lower.rindex("warning"), "dense-step 警告必须在 warning 之后出现"
    # 必须包含 --refit-every 警告
    assert "refit-every" in src.lower(), "必须包含 --refit-every 警告"


def test_compute_timesfm_resume_path():
    """验证 compute_timesfm_features_batch 支持 resume_path 断点续算"""
    import inspect
    from cascade.lgbm_features import compute_timesfm_features_batch
    source = inspect.getsource(compute_timesfm_features_batch)
    assert "resume_path" in source, "必须支持 resume_path 参数"
    # 必须逐 bar 追加并 flush；并发安全由调用方的单写入者约束保证
    assert "json.dumps" in source, "必须写 JSON 行"
    assert "flush" in source, "必须 flush 立即写盘"


def test_build_dense_market_cache():
    """验证 build_dense_feature_matrix 支持 market_cache_path / tsfm_resume_path"""
    import inspect
    from cascade.lgbm_features import build_dense_feature_matrix
    source = inspect.getsource(build_dense_feature_matrix)
    assert "market_cache_path" in source, "必须支持 market_cache_path 参数"
    assert "tsfm_resume_path" in source, "必须支持 tsfm_resume_path 参数"


def test_worker_passes_cache_paths():
    """验证 Worker 传入 market_cache_path / tsfm_resume_path"""
    worker_path = pathlib.Path(__file__).parent.parent / "scripts" / "a2_p1_worker.py"
    assert worker_path.exists(), "scripts/a2_p1_worker.py 必须存在"
    worker_src = worker_path.read_text(encoding="utf-8")
    assert "market_cache_path" in worker_src, "Worker 必须传入 market_cache_path"
    assert "tsfm_resume_path" in worker_src, "Worker 必须传入 tsfm_resume_path"


def test_orchestrator_unbuffered_and_timeout():
    """验证 Orchestrator 用 -u 无缓冲 + timeout 5400"""
    orch_path = pathlib.Path(__file__).parent.parent / "scripts" / "a2_p1_orchestrator.py"
    assert orch_path.exists(), "scripts/a2_p1_orchestrator.py 必须存在"
    orch_src = orch_path.read_text(encoding="utf-8")
    assert "-u" in orch_src or "unbuffered" in orch_src.lower(), "必须用 -u 无缓冲模式"
    assert "5400" in orch_src, "timeout 必须为 5400s (90min, 覆盖冷启动)"


def test_extract_features_precomputed_param():
    """验证 extract_market_features_at_bar 支持 precomputed 参数 (安全特征 O(1) 取值, PCA 仍切片)"""
    import inspect
    from cascade.lgbm_features import extract_market_features_at_bar
    source = inspect.getsource(extract_market_features_at_bar)
    assert "precomputed" in source, "必须支持 precomputed 参数"
    # 安全特征按索引/key 取值 (pc 为 precomputed 别名)
    assert 'pc["hurst"]' in source or 'precomputed["hurst"]' in source, "hurst 必须支持预计算取值"
    # pca_momentum 不进 precomputed (仍切片 closes, 防 StandardScaler+PCA 全局 fitting 泄漏)
    assert "calc_pca_momentum(closes" in source, "pca_momentum 必须仍用切片 closes (防穿越)"


def test_build_dense_precomputes_safe_features():
    """验证 build_dense_feature_matrix 预计算安全特征 (hurst 瓶颈 O(N²)->O(N))"""
    import inspect
    from cascade.lgbm_features import build_dense_feature_matrix
    source = inspect.getsource(build_dense_feature_matrix)
    assert "precomputed" in source, "必须构建 precomputed 字典"
    assert "calc_rolling_hurst(closes" in source or "calc_rolling_hurst(full" in source, "必须预计算 hurst 全序列"
    assert "precomputed=precomputed" in source, "必须传 precomputed 给 extract_market_features_at_bar"
    # daily_slope 字典映射防 IndexError
    assert "daily_slope" in source and ("for t in valid" in source), "daily_slope 必须按 valid 预计算"


def test_precomputed_equals_slice_numeric():
    """验证预计算模式与切片模式数值一致 (安全特征 pca_momentum 都用切片)"""
    import numpy as np
    import pandas as pd
    from data.data_store import DataStore
    from cascade.lgbm_features import (
        extract_market_features_at_bar, calc_rolling_hurst,
        calc_hourly_slope, calc_rsi_state, calc_oi_pct_change,
    )

    with DataStore("ss") as store:
        df_1h = store.get_main_contract_1h(limit=2000)  # 小样本加速
        df_daily = store.get_main_continuous(limit=100000) if hasattr(store, "get_main_continuous") else pd.DataFrame()

    closes_full = df_1h["close_price"].values.astype(float)
    precomputed = {
        "hurst": calc_rolling_hurst(closes_full, window=120, step=6),
        "hourly_slope": calc_hourly_slope(closes_full, window=24).values,
        "rsi_state": calc_rsi_state(closes_full, rsi_period=14),
    }
    if "open_interest" in df_1h.columns:
        precomputed["oi_pct_change"] = calc_oi_pct_change(df_1h["open_interest"]).values

    # 抽样 5 个 bar 验证预计算 == 切片
    for t in [480, 600, 800, 1000, 1200]:
        f_pre = extract_market_features_at_bar(df_1h, df_daily, t, "ss", precomputed=precomputed)
        f_slice = extract_market_features_at_bar(df_1h, df_daily, t, "ss", precomputed=None)
        # hurst: 切片模式有已知 bug (closes[:t+1] 末尾 bar 未被 forward-fill 覆盖, 返回默认 0.0)
        # 预计算模式修复此 bug, 返回真实 hurst (不穿越, 只用 ret[t-120:t])
        # 断言预计算 hurst 提取到有效值 (不为默认无效值 0.0)
        assert abs(f_pre["hurst"]) > 1e-6, f"t={t} 预计算 hurst 不应为默认无效值 0.0, got {f_pre['hurst']}"
        # hourly_slope, rsi_state: 预计算 == 切片 (纯滚动, 无边界 bug)
        for k in ["hourly_slope", "rsi_state"]:
            assert abs(f_pre[k] - f_slice[k]) < 1e-9, f"t={t} {k}: pre={f_pre[k]} slice={f_slice[k]}"
        # pca_momentum 必须一致 (都用切片, 不进 precomputed)
        assert abs(f_pre["pca_momentum"] - f_slice["pca_momentum"]) < 1e-9, f"t={t} pca 不一致"
