"""步② C：拉取日重锚 + 唯一收口后条件测试（事项一五步之 2/5）。

确认窗 cutoff 从网格消失是缺失报告；回滚目标必须通过当前网格后条件。
`finalize_baseline_write` 是唯一换名或回滚的函数。
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import sup_state
import sup_evidence
import praxist_supervisor as sup


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


# ── _baseline_reanchor_reason ──────────────────────────────────────

def test_reanchor_reason_none_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-01 10:00:00")
    # 无预注册；基线末端落后 2h << 168h
    assert sup._baseline_reanchor_reason("jd", "2026-10-01 08:00:00", str(tmp_path)) is None


def test_reanchor_reason_confirmation_window_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-04 08:00:00")
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    reason = sup._baseline_reanchor_reason("jd", "2026-09-30 14:00:00", str(tmp_path))
    assert reason is not None
    assert "确认窗" in reason


def test_reanchor_reason_none_when_data_not_caught_up(tmp_path, monkeypatch):
    """国庆缺口：数据末端 09-30 未越过 confirm_from_ts 10-03 → 不重生。"""
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-09-30 14:00:00")
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    # (b) 也满足：lag = 0h
    assert sup._baseline_reanchor_reason("jd", "2026-09-30 14:00:00", str(tmp_path)) is None


def test_reanchor_reason_staleness_cap(tmp_path, monkeypatch):
    """漂移上界：无预注册但基线落后 14 天 > 7 天 → 重锚。"""
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-09-30 14:00:00")
    reason = sup._baseline_reanchor_reason("jd", "2026-09-16 15:00:00", str(tmp_path))
    assert reason is not None
    assert "落后" in reason


def test_reanchor_reason_fail_open_on_missing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: None)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    assert sup._baseline_reanchor_reason("jd", "2026-09-30 14:00:00", str(tmp_path)) is None


def test_reanchor_reason_prereg_of_other_symbol_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-04 08:00:00")
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "sr",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    assert sup._baseline_reanchor_reason("jd", "2026-10-04 06:00:00", str(tmp_path)) is None


# ── finalize_baseline_write（唯一收口）──────────────────────────────

def _patch_grid(monkeypatch, cutoffs, fp="fp_test"):
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(cutoffs))
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: fp)


def _rising_grid(n=588):
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    return [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def test_guard_noop_without_prereg(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    before = pts.read_bytes()
    scar = tmp_path / "baseline_points_jd_nocov.archive_20261021T1500.jsonl"
    _write_points(scar, ["2026-10-21 10:00:00"])
    # 没有预注册。1 行归档不是恢复目标。活文件已经等于网格时收口为真，字节不变。
    tmp = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    tmp.write_bytes(before)
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(scar)) is True
    assert pts.read_bytes() == before
    assert scar.read_bytes() != pts.read_bytes()


def test_guard_passes_when_new_file_keeps_confirm_window(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    before = pts.read_bytes()
    archive = tmp_path / "baseline_points_jd_nocov.archive_20261021T1500.jsonl"
    _write_points(archive, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                            "2026-10-21 15:00:00"])
    tmp = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    tmp.write_bytes(before)
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(archive)) is True
    assert pts.read_bytes() == before
    assert not tmp.exists()


def test_guard_restores_archive_when_cutoffs_deleted(tmp_path, monkeypatch):
    """网格外的 3 行归档不得盖回一份网格有效的文件。"""
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    before = pts.read_bytes()
    archive = tmp_path / "baseline_points_jd_nocov.archive_20261021T1500.jsonl"
    _write_points(archive, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                            "2026-10-21 15:00:00"])
    rejected = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    _write_points(rejected, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                             "2026-10-21 15:00:00"])
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(archive)) is False
    assert pts.read_bytes() == before
    assert not rejected.exists()


def test_guard_noop_when_archive_has_no_confirm_points(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    archive = tmp_path / "baseline_points_jd_nocov.archive_20260930T1400.jsonl"
    _write_points(archive, ["2026-09-30 14:00:00"])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-10-01 00:00:00"])
    before = pts.read_bytes()
    rejected = tmp_path / ".baseline_points_jd_nocov.jsonl.tmp"
    _write_points(rejected, ["2026-10-01 00:00:00"])
    assert sup_evidence.finalize_baseline_write("jd", str(pts), str(tmp_path), str(archive)) is False
    assert pts.read_bytes() == before
    assert not rejected.exists()


def test_prereg_and_no_prereg_keep_the_same_grid_file(tmp_path, monkeypatch):
    grid = _rising_grid()
    _patch_grid(monkeypatch, grid)
    for symbol in ("sr", "bu"):
        root = tmp_path / symbol
        root.mkdir()
        if symbol == "sr":
            _write_prereg(str(root), [{"prereg_id": "p-sr", "symbol": "sr",
                                       "confirm_from_ts": "2026-10-03 00:00:00",
                                       "n_confirm_required": 986}])
        pts = root / f"baseline_points_{symbol}_nocov.jsonl"
        _write_points(pts, grid)
        before = pts.read_bytes()
        archive = root / f"baseline_points_{symbol}_nocov.archive_scar.jsonl"
        _write_points(archive, ["2026-10-21 10:00:00", "2026-10-21 12:00:00",
                                "2026-10-21 15:00:00"])
        tmp = root / f".baseline_points_{symbol}_nocov.jsonl.tmp"
        tmp.write_bytes(before)
        assert sup_evidence.finalize_baseline_write(symbol, str(pts), str(root), str(archive)) is True
        assert pts.read_bytes() == before

    text = Path("scripts/sup_evidence.py").read_text(encoding="utf-8")
    # Check that finalize_baseline_write doesn't have special-case logic for jd
    func_start = text.find("def finalize_baseline_write")
    func_end = text.find("\ndef ", func_start + 1)
    if func_end == -1:
        func_end = len(text)
    func_body = text[func_start:func_end]
    assert 'symbol == "jd"' not in func_body
    assert "symbol == 'jd'" not in func_body


# ── ensure_baselines 集成 ──────────────────────────────────────────

class _FakeGbp:
    def __init__(self):
        self.calls = []

    def baseline_filename(self, sym, cov):
        return f"baseline_points_{sym}_nocov.jsonl"

    def generate(self, sym, cov, root, finalize=False):
        self.calls.append((sym, cov, finalize))


def _rising_grid(n=4):
    from datetime import datetime, timedelta
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    return [(t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as f:
        for c in cutoffs:
            f.write(json.dumps({"cutoff": c, "dir_ok": True, "delta_pred": 1.0,
                                "delta_real": 1.0, "protocol_fingerprint": fp}) + "\n")


def test_ensure_baselines_no_regen_when_fresh(tmp_path, monkeypatch):
    grid = _rising_grid(4)
    config = tmp_path / "task_FM" / "config"
    config.mkdir(parents=True)
    (config / "baseline_metrics.json").write_text(json.dumps({"jd": {"n": 4}}), encoding="utf-8")
    pts = config / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, grid)
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-10-01 10:00:00")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: list(grid))
    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)
    fake = _FakeGbp()

    def _generate(sym, cov, root, finalize=False):
        fake.calls.append((sym, cov, root))

    fake.generate = _generate
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    sup.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == []
    assert list(config.glob("baseline_points_jd_nocov.archive_*.jsonl")) == []


def test_ensure_baselines_reanchors_on_stale_baseline(tmp_path, monkeypatch):
    config = tmp_path / "task_FM" / "config"
    config.mkdir(parents=True)
    (config / "baseline_metrics.json").write_text(json.dumps({"jd": {"n": 4}}), encoding="utf-8")
    pts = config / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-09-16 15:00:00"])
    order = []
    monkeypatch.setattr(sup_state, "_latest_data_dt", lambda s: "2026-09-30 14:00:00")
    monkeypatch.setattr(sup_evidence, "_current_protocol_fingerprint", lambda: "fp_test")
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: _rising_grid(4))

    def _incremental(*a, **k):
        order.append("incremental")
        return None

    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", _incremental)
    fake = _FakeGbp()

    def _generate(sym, cov, root, finalize=False):
        order.append("generate")
        fake.calls.append((sym, cov, root))

    fake.generate = _generate
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    sup.ensure_baselines(["JD"], str(tmp_path))
    assert fake.calls == [("jd", None, str(tmp_path))]
    archives = list(config.glob("baseline_points_jd_nocov.archive_*.jsonl"))
    assert len(archives) == 1
    assert order == ["incremental", "generate"]
