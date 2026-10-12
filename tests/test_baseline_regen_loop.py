"""基线重生循环防护测试（Phase 1 止血）。

防止 ensure_baselines 在 TqSdk 10000 bar 硬限下无限重生。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import sup_state
import sup_evidence
import sup_lifecycle


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as f:
        for c in cutoffs:
            f.write(json.dumps({"cutoff": c, "dir_ok": True, "delta_pred": 1.0,
                                "delta_real": 1.0, "protocol_fingerprint": fp}) + "\n")


def _write_prereg(root, rows):
    config_dir = os.path.join(root, "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "preregistry.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _setup_healthy_baseline(root, n=150, fp="fp_test", last_cutoff="2026-09-16 15:00:00"):
    config_dir = os.path.join(root, "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    metrics = {"jd": {"n": 588, "dir_acc": 0.5, "endpoint_mape": 1.0, "n_eff": 73}}
    with open(os.path.join(config_dir, "baseline_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f)
    _write_points(os.path.join(config_dir, "baseline_points_jd_nocov.jsonl"),
                  [last_cutoff] * n, fp=fp)


# ── _read_last_cutoff ─────────────────────────────────────────────────

def test_read_last_cutoff_returns_last():
    """_read_last_cutoff 应返回基线文件中最后一个 cutoff。"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding="utf-8") as f:
        f.write(json.dumps({"cutoff": "2026-09-23 15:00:00"}) + "\n")
        f.write(json.dumps({"cutoff": "2026-09-24 15:00:00"}) + "\n")
        f.flush()
        path = f.name
    try:
        result = sup_evidence._read_last_cutoff(path)
        assert result == "2026-09-24 15:00:00"
    finally:
        os.unlink(path)


def test_read_last_cutoff_empty_file():
    """空文件应返回 None。"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding="utf-8") as f:
        f.flush()
        path = f.name
    try:
        result = sup_evidence._read_last_cutoff(path)
        assert result is None
    finally:
        os.unlink(path)


def test_read_last_cutoff_missing_file():
    """不存在的文件应返回 None（不抛异常）。"""
    result = sup_evidence._read_last_cutoff("/tmp/nonexistent_baseline.jsonl")
    assert result is None


# ── Circuit breaker memory ────────────────────────────────────────────


class _FakeGbp:
    def __init__(self):
        self.calls = []

    def baseline_filename(self, sym, cov):
        return f"baseline_points_{sym}_nocov.jsonl"

    def generate(self, sym, cov, root):
        self.calls.append((sym, cov, root))


def test_circuit_breaker_skips_regen_on_second_poll(tmp_path, monkeypatch):
    """第二次 poll 时，如果重生后 cutoff 未推进且数据未变，应跳过重生。"""
    sup_evidence._RECENTLY_REGENED_NO_ADVANCE.clear()
    _setup_healthy_baseline(str(tmp_path), last_cutoff="2026-09-24 15:00:00")
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-09 14:00:00")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    # 模拟重生后 cutoff 仍然停在 2026-09-24（TqSdk 10000 bar 限制）
    monkeypatch.setattr(sup_evidence, "_read_last_cutoff", lambda p: "2026-09-24 15:00:00")
    monkeypatch.setattr(sup_lifecycle, "_write_heartbeat", lambda: None)
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)

    # 第一次调用：触发重生（cutoff 未推进）
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1
    # 记录的是数据末端
    assert sup_evidence._RECENTLY_REGENED_NO_ADVANCE.get("jd") == "2026-10-09 14:00:00"

    # 第二次调用（模拟下一次 poll）：应跳过重生
    fake.calls.clear()
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == [], "第二次 poll 应跳过重生"


def test_circuit_breaker_allows_regen_after_data_advance(tmp_path, monkeypatch):
    """数据末端推进后（daily_update），应允许重生。

    注意：重生后 cutoff 可能仍然不推进（TqSdk 10000 bar 限制），
    此时 circuit breaker 会再次记录新的数据末端。
    """
    sup_evidence._RECENTLY_REGENED_NO_ADVANCE.clear()
    _setup_healthy_baseline(str(tmp_path), last_cutoff="2026-09-24 15:00:00")
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-09 14:00:00")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr(sup_evidence, "_read_last_cutoff", lambda p: "2026-09-24 15:00:00")
    monkeypatch.setattr(sup_lifecycle, "_write_heartbeat", lambda: None)
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)

    # 第一次：触发重生并记录到 circuit breaker（存的是 data_dt）
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1
    assert sup_evidence._RECENTLY_REGENED_NO_ADVANCE.get("jd") == "2026-10-09 14:00:00"

    # 模拟 daily_update 后数据末端推进到 10-12
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-12 14:00:00")

    # 第二次：数据变了，允许重生
    fake.calls.clear()
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1, "数据推进后应允许重生"
    # 重生后 cutoff 仍然不推进 → 再次记录（新 data_dt）
    assert sup_evidence._RECENTLY_REGENED_NO_ADVANCE.get("jd") == "2026-10-12 14:00:00"

    # 第三次：数据没再变 → 跳过
    fake.calls.clear()
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == [], "数据未变应跳过重生"


def test_circuit_breaker_records_data_dt(tmp_path, monkeypatch):
    """circuit breaker 应记录数据末端（不是 cutoff）。"""
    sup_evidence._RECENTLY_REGENED_NO_ADVANCE.clear()
    _setup_healthy_baseline(str(tmp_path), last_cutoff="2026-09-24 15:00:00")
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-09 14:00:00")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr(sup_evidence, "_read_last_cutoff", lambda p: "2026-09-24 15:00:00")
    monkeypatch.setattr(sup_lifecycle, "_write_heartbeat", lambda: None)
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)

    sup_evidence.ensure_baselines(["JD"], str(tmp_path))

    # 存储的是 data_dt，不是 cutoff
    assert sup_evidence._RECENTLY_REGENED_NO_ADVANCE.get("jd") == "2026-10-09 14:00:00"


# ── Eval indices: last point has full horizon ─────────────────────────

def test_eval_indices_last_point_has_full_horizon():
    """最后一个 eval 点应有完整的 HORIZON 根 target bars。"""
    import pandas as pd
    from config.backtest_config import HORIZON
    import monthly_backtest as mb

    total = 10000
    dts = (
        pd.date_range("2024-01-01", periods=total, freq="h")
        .strftime("%Y-%m-%d %H:%M:%S")
        .tolist()
    )

    indices = mb.select_eval_indices(dts)
    max_idx = max(indices)

    # 最后一个 eval 点的 target slice: dts[max_idx+1 : max_idx+1+HORIZON]
    # 必须保证 max_idx + 1 + HORIZON <= total
    assert max_idx + 1 + HORIZON <= total, (
        f"最后一个 eval 点 {max_idx} 的 target slice 越界: "
        f"max_idx+1+HORIZON={max_idx+1+HORIZON} > total={total}"
    )


def test_regen_returns_cutoff(tmp_path, monkeypatch):
    """_regen_baseline_with_archive 应返回重生后的 cutoff。"""
    sup_evidence._RECENTLY_REGENED_NO_ADVANCE.clear()
    config_dir = os.path.join(str(tmp_path), "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)

    # 写一个基线文件
    points_path = os.path.join(config_dir, "baseline_points_jd_nocov.jsonl")
    _write_points(points_path, ["2026-09-24 15:00:00"], fp="fp_test")
    _write_prereg(str(tmp_path), [])

    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-09 14:00:00")
    monkeypatch.setattr(sup_lifecycle, "_write_heartbeat", lambda: None)

    class FakeGbp2:
        def baseline_filename(self, sym, cov):
            return f"baseline_points_{sym}_nocov.jsonl"

        def generate(self, sym, cov, root):
            # 模拟 generate 写了新文件，cutoff 推进到 09-25
            _write_points(points_path, ["2026-09-25 15:00:00"], fp="fp_test")

    monkeypatch.setitem(sys.modules, "generate_baseline_points", FakeGbp2())

    result = sup_evidence._regen_baseline_with_archive("jd", points_path, str(tmp_path))
    assert result == "2026-09-25 15:00:00"
