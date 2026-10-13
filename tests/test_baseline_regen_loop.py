"""基线重生循环防护。

ensure_baselines 每个进程只在 pre-flight 跑一次。断路器若只活在内存里，
下次 supervisor 启动时记忆是空的，停滞品种会再次重生。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import sup_evidence
import sup_lifecycle
import sup_state


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as f:
        for c in cutoffs:
            f.write(json.dumps({
                "cutoff": c,
                "dir_ok": True,
                "delta_pred": 1.0,
                "delta_real": 1.0,
                "protocol_fingerprint": fp,
            }) + "\n")


def _setup_healthy_baseline(root, n=150, fp="fp_test", last_cutoff="2026-09-16 15:00:00"):
    config_dir = os.path.join(root, "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    metrics = {"jd": {"n": 588, "dir_acc": 0.5, "endpoint_mape": 1.0, "n_eff": 73}}
    with open(os.path.join(config_dir, "baseline_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f)
    _write_points(
        os.path.join(config_dir, "baseline_points_jd_nocov.jsonl"),
        [last_cutoff] * n,
        fp=fp,
    )


class _FakeGbp:
    def __init__(self):
        self.calls = []

    def baseline_filename(self, sym, cov):
        return f"baseline_points_{sym}_nocov.jsonl"

    def generate(self, sym, cov, root):
        self.calls.append((sym, cov, root))



def _write_prereg(root, rows):
    config_dir = os.path.join(root, "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "preregistry.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _forget_process_memory():
    """模拟新进程：模块级字典为空，磁盘记录还在。"""
    mem = getattr(sup_evidence, "_RECENTLY_REGENED_NO_ADVANCE", None)
    if isinstance(mem, dict):
        mem.clear()


def _arm(monkeypatch, data_dt):
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: data_dt)
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr(sup_lifecycle, "_write_heartbeat", lambda: None)
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    return fake


def test_stalled_baseline_is_not_regenerated_after_process_restart(tmp_path, monkeypatch):
    """重启后数据末端未变时，不得再次重生。"""
    _setup_healthy_baseline(str(tmp_path))
    _forget_process_memory()
    fake = _arm(monkeypatch, "2026-10-09 14:00:00")

    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1

    _forget_process_memory()
    fake.calls.clear()
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == []


def test_unreadable_data_end_keeps_the_stall(tmp_path, monkeypatch):
    """数据末端暂时读不到时，不得拆掉断路器再重生。"""
    _setup_healthy_baseline(str(tmp_path))
    _forget_process_memory()
    fake = _arm(monkeypatch, "2026-10-09 14:00:00")

    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1

    _forget_process_memory()
    fake.calls.clear()
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: None)
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == []

    _forget_process_memory()
    fake.calls.clear()
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-09 14:00:00")
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == [], "读失败那一轮不得把停滞记录清掉"


def test_timestamp_spelling_difference_does_not_clear_stall(tmp_path, monkeypatch):
    """同一末端的空格写法与 ISO 写法不得被当成数据增长。"""
    _setup_healthy_baseline(str(tmp_path))
    _forget_process_memory()
    fake = _arm(monkeypatch, "2026-10-09 14:00:00")

    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1

    _forget_process_memory()
    fake.calls.clear()
    # 重锚条件仍成立。若断路器把 ISO 写法当成新数据，这里会再次 generate。
    monkeypatch.setattr(sup_evidence, "_baseline_reanchor_reason", lambda *a, **k: "仍需重锚")
    monkeypatch.setattr(
        sup_state, "_latest_data_dt", lambda s: "2026-10-09T14:00:00.000000000")
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == []


def test_newer_data_end_allows_regen_after_restart(tmp_path, monkeypatch):
    """数据末端真正变新后，允许再重生一次；同一新末端的再下一次启动不再重生。"""
    _setup_healthy_baseline(str(tmp_path))
    _forget_process_memory()
    fake = _arm(monkeypatch, "2026-10-09 14:00:00")

    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1

    _forget_process_memory()
    fake.calls.clear()
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-12 14:00:00")
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert len(fake.calls) == 1

    _forget_process_memory()
    fake.calls.clear()
    sup_evidence.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == []


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
