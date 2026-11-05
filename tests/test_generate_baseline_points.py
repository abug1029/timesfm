"""测试 generate_baseline_points.py"""

import json
import pytest
from pathlib import Path


def test_generate_writes_jsonl_and_metrics(tmp_path, monkeypatch):
    """测试生成 JSONL 和 metrics 文件"""
    import scripts.generate_baseline_points as gbp

    # 构造 120 个模拟点
    points = [
        {
            "cutoff": "2024-06-15 09:00:00",
            "dir_ok": True,
            "delta_pred": 1.0,
            "delta_real": 1.0,
            "pred_end": 101,
            "real_end": 101,
            "base": 100,
            "dir12_ok": True,
            "mae": 1,
            "mape": 1,
            "mae_h1": 1,
            "mae_h2": 1,
            "coverage": 20,
            "real_range": 1,
        }
    ] * 120

    # mock run_symbol_backtest
    monkeypatch.setattr(
        gbp.mb,
        "run_symbol_backtest",
        lambda *a, **k: {
            "symbol": "SS",
            "name": "不锈钢",
            "contract": "x",
            "total_bars": 1,
            "points": points,
        },
    )

    monkeypatch.setattr("scripts.sup_evidence.finalize_baseline_write", _accept_rename)

    # 运行生成
    gbp.generate("ss", cov="ccl", root=str(tmp_path))

    # 验证 JSONL 文件
    p = tmp_path / "task_FM" / "config" / "baseline_points_ss.jsonl"
    assert p.exists(), "JSONL 文件应该存在"
    lines = [line for line in p.open(encoding="utf-8") if line.strip()]
    assert len(lines) == 120, f"应该有 120 行，实际 {len(lines)}"

    # 验证每行包含必写键，可选键按需出现
    for line in lines:
        rec = json.loads(line)
        required = {"cutoff", "dir_ok", "delta_pred", "delta_real",
                    "protocol_fingerprint"}
        assert required <= set(rec.keys())
        assert set(rec.keys()) <= required | {"endpoint_delta", "position_sign"}
        assert "endpoint_delta" not in rec
        assert "position_sign" not in rec
        assert isinstance(rec["cutoff"], str)
        assert isinstance(rec["dir_ok"], bool)
        assert isinstance(rec["delta_pred"], float)
        assert isinstance(rec["delta_real"], float)

    # 验证 metrics 文件
    metrics_file = tmp_path / "task_FM" / "config" / "baseline_metrics.json"
    assert metrics_file.exists(), "metrics 文件应该存在"
    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
    assert "ss" in metrics, "metrics 应该包含 ss"
    assert metrics["ss"]["n"] == 120, f"n 应该是 120，实际 {metrics['ss']['n']}"
    assert "dir_acc" in metrics["ss"]
    assert "endpoint_mape" in metrics["ss"]
    assert "n_eff" in metrics["ss"]


def test_generate_handles_empty_result(tmp_path, monkeypatch):
    """测试处理空结果"""
    import scripts.generate_baseline_points as gbp

    # mock run_symbol_backtest 返回 None
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: None)

    # 应该不抛异常
    gbp.generate("ss", cov="ccl", root=str(tmp_path))

    # JSONL 文件不应该存在
    p = tmp_path / "task_FM" / "config" / "baseline_points_ss.jsonl"
    assert not p.exists(), "数据不足时不应生成 JSONL 文件"


def test_generate_lock_exclusive(tmp_path, monkeypatch):
    """测试锁排他性"""
    import scripts.generate_baseline_points as gbp
    import fcntl

    config_dir = tmp_path / "task_FM" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # 预先创建锁文件并持有
    lock_file = config_dir / ".ss.lock"
    lock_fp = open(lock_file, "w")
    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)

    # mock run_symbol_backtest（不应该被调用）
    called = []
    monkeypatch.setattr(
        gbp.mb,
        "run_symbol_backtest",
        lambda *a, **k: called.append(True),
    )

    # 应该抛出锁冲突异常
    with pytest.raises(RuntimeError, match="锁冲突"):
        gbp.generate("ss", cov="ccl", root=str(tmp_path))

    # run_symbol_backtest 不应该被调用
    assert len(called) == 0, "锁冲突时不应调用 run_symbol_backtest"

    # 清理
    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
    lock_fp.close()


def test_generate_writes_new_keys_when_present(tmp_path, monkeypatch):
    """假点带 endpoint_delta 和 position_sign 时，JSONL 里也以 float 出现"""
    import scripts.generate_baseline_points as gbp

    points = [
        {
            "cutoff": "2024-06-15 09:00:00",
            "dir_ok": True,
            "delta_pred": 1.0,
            "delta_real": 1.0,
            "endpoint_delta": 0.5,
            "position_sign": 1.0,
            "pred_end": 101.0,
            "real_end": 101.0,
            "base": 100.0,
            "dir12_ok": True,
            "mae": 1.0,
            "mape": 1.0,
            "mae_h1": 1.0,
            "mae_h2": 1.0,
            "coverage": 20,
            "real_range": 1.0,
        }
    ] * 10

    monkeypatch.setattr(
        gbp.mb,
        "run_symbol_backtest",
        lambda *a, **k: {
            "symbol": "SS",
            "name": "不锈钢",
            "contract": "x",
            "total_bars": 1,
            "points": points,
        },
    )

    # 10 个相同 cutoff 过不了 accept。这里只检查投影，收口换成换名。
    monkeypatch.setattr("scripts.sup_evidence.finalize_baseline_write", _accept_rename)
    gbp.generate("ss", cov="ccl", root=str(tmp_path))

    p = tmp_path / "task_FM" / "config" / "baseline_points_ss.jsonl"
    lines = [line for line in p.open(encoding="utf-8") if line.strip()]
    assert len(lines) == 10
    for line in lines:
        rec = json.loads(line)
        assert "endpoint_delta" in rec
        assert "position_sign" in rec
        assert isinstance(rec["endpoint_delta"], float)
        assert isinstance(rec["position_sign"], float)
        assert rec["endpoint_delta"] == 0.5
        assert rec["position_sign"] == 1.0

def _accept_rename(symbol, points_path, root, archive_path):
    live = Path(points_path)
    tmp = live.with_name("." + live.name + ".tmp")
    tmp.replace(live)
    return True


def test_finalize_false_leaves_temp_and_skips_accept(tmp_path, monkeypatch):
    import scripts.generate_baseline_points as gbp
    points = [{
        "cutoff": "2026-02-01 10:00:00", "dir_ok": True,
        "delta_pred": 1.0, "delta_real": 1.0,
        "pred_end": 101.0, "real_end": 101.0, "base": 100.0,
        "dir12_ok": True, "mae": 1.0, "mape": 1.0, "mae_h1": 1.0, "mae_h2": 1.0,
        "coverage": 20, "real_range": 1.0,
    }]
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: {
        "points": points, "symbol": "SS", "name": "不锈钢", "contract": "x", "total_bars": 1,
    })
    called = {"n": 0}

    def _no(symbol, points_path, root, archive_path):
        called["n"] += 1
        return True

    monkeypatch.setattr("scripts.sup_evidence.finalize_baseline_write", _no)
    got = gbp.generate("ss", cov="ccl", root=str(tmp_path), finalize=False)
    live = tmp_path / "task_FM" / "config" / "baseline_points_ss.jsonl"
    tmp = tmp_path / "task_FM" / "config" / ".baseline_points_ss.jsonl.tmp"
    assert got == "2026-02-01 10:00:00"
    assert tmp.exists()
    assert not live.exists()
    assert called["n"] == 0


def test_error_point_is_not_a_publishable_file(tmp_path, monkeypatch):
    import scripts.generate_baseline_points as gbp
    points = [
        {
            "cutoff": "2026-02-01 10:00:00", "dir_ok": True,
            "delta_pred": 1.0, "delta_real": 1.0,
            "pred_end": 101.0, "real_end": 101.0, "base": 100.0,
            "dir12_ok": True, "mae": 1.0, "mape": 1.0, "mae_h1": 1.0, "mae_h2": 1.0,
            "coverage": 20, "real_range": 1.0,
        },
        {"cutoff": "2026-02-01 12:00:00", "error": "model failed"},
    ]
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: {"points": points})
    got = gbp.generate("ss", cov="ccl", root=str(tmp_path), finalize=False)
    cfg = tmp_path / "task_FM" / "config"
    assert got is None
    assert not (cfg / ".baseline_points_ss.jsonl.tmp").exists()
    assert not (cfg / "baseline_points_ss.jsonl").exists()


def test_error_point_deletes_preexisting_temp_and_keeps_live(tmp_path, monkeypatch):
    import scripts.generate_baseline_points as gbp

    class _Model:
        def __init__(self, *a, **k):
            self.model = None

    monkeypatch.setattr("cascade.daily_model.DailyModel", _Model)
    monkeypatch.setattr("cascade.hourly_model.HourlyModel", _Model)
    monkeypatch.setattr(gbp.mb, "run_symbol_backtest", lambda *a, **k: {
        "points": [{"cutoff": "2026-02-01 12:00:00", "error": "fresh point failed"}],
    })
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True)
    live = cfg / "baseline_points_ss.jsonl"
    tmp = cfg / ".baseline_points_ss.jsonl.tmp"
    live_body = '{"cutoff": "2026-01-01 10:00:00", "dir_ok": true}' + chr(10)
    live.write_text(live_body, encoding="utf-8")
    tmp.write_text('{"cutoff": "2026-01-02 10:00:00", "dir_ok": true}' + chr(10), encoding="utf-8")
    got = gbp.generate("ss", cov="ccl", root=str(tmp_path), finalize=False)
    assert got is None
    assert not tmp.exists()
    assert live.read_text(encoding="utf-8") == live_body
