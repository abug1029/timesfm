"""步② C：拉取日重锚 + confirm_from_ts 守卫断言测试（事项一五步之 2/5）。

裁定 C（2026-10-07，dm-status 报告附录 A.2）：
- 基线快照版本化为前置（步① 已落地）；
- 守卫断言 = 重锚不得删除 >= confirm_from_ts 的基线 cutoff（保 v9 修订②）；
- unmatched 预期 ≈ 拉取滞后 1-3 点（非零），B 不因 C 省略。

重锚条件（per symbol，任一触发重生）：
(a) 确认窗覆盖缺口：存在预注册 confirm_from_ts ∈ (基线末端, 数据末端]；
(b) 漂移上界：数据末端 - 基线末端 > _BASELINE_STALENESS_MAX_H（168h=7 天）。
数据末端读不到 → None（fail-open，防误重生）。
"""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
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
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: "2026-10-01 10:00:00")
    # 无预注册；基线末端落后 2h << 168h
    assert sup._baseline_reanchor_reason("jd", "2026-10-01 08:00:00", str(tmp_path)) is None


def test_reanchor_reason_confirmation_window_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: "2026-10-04 08:00:00")
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    reason = sup._baseline_reanchor_reason("jd", "2026-09-30 14:00:00", str(tmp_path))
    assert reason is not None
    assert "确认窗" in reason


def test_reanchor_reason_none_when_data_not_caught_up(tmp_path, monkeypatch):
    """国庆缺口：数据末端 09-30 未越过 confirm_from_ts 10-03 → 不重生。"""
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: "2026-09-30 14:00:00")
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    # (b) 也满足：lag = 0h
    assert sup._baseline_reanchor_reason("jd", "2026-09-30 14:00:00", str(tmp_path)) is None


def test_reanchor_reason_staleness_cap(tmp_path, monkeypatch):
    """漂移上界：无预注册但基线落后 14 天 > 7 天 → 重锚。"""
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: "2026-09-30 14:00:00")
    reason = sup._baseline_reanchor_reason("jd", "2026-09-16 15:00:00", str(tmp_path))
    assert reason is not None
    assert "落后" in reason


def test_reanchor_reason_fail_open_on_missing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: None)
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    assert sup._baseline_reanchor_reason("jd", "2026-09-30 14:00:00", str(tmp_path)) is None


def test_reanchor_reason_prereg_of_other_symbol_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: "2026-10-04 08:00:00")
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "sr",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    assert sup._baseline_reanchor_reason("jd", "2026-10-04 06:00:00", str(tmp_path)) is None


# ── _guard_confirm_from_ts_after_regen ─────────────────────────────

def test_guard_noop_without_prereg(tmp_path):
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-10-03 00:00:00"])
    assert sup._guard_confirm_from_ts_after_regen("jd", str(pts), None, str(tmp_path)) is True


def test_guard_passes_when_new_file_keeps_confirm_window(tmp_path):
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    archive = tmp_path / "baseline_points_jd_nocov.archive_20260930T1400.jsonl"
    _write_points(archive, ["2026-10-02 00:00:00", "2026-10-03 00:00:00",
                            "2026-10-05 00:00:00"])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-10-01 00:00:00", "2026-10-03 00:00:00",
                        "2026-10-05 00:00:00", "2026-10-06 00:00:00"])
    before = pts.read_bytes()
    assert sup._guard_confirm_from_ts_after_regen("jd", str(pts), str(archive), str(tmp_path)) is True
    assert pts.read_bytes() == before   # 通过时不恢复


def test_guard_restores_archive_when_cutoffs_deleted(tmp_path):
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    archive = tmp_path / "baseline_points_jd_nocov.archive_20260930T1400.jsonl"
    _write_points(archive, ["2026-10-03 00:00:00", "2026-10-05 00:00:00"])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-10-01 00:00:00"])   # 重生丢掉了确认窗点
    result = sup._guard_confirm_from_ts_after_regen("jd", str(pts), str(archive), str(tmp_path))
    assert result is False
    assert pts.read_bytes() == archive.read_bytes()   # 旧档已恢复


def test_guard_noop_when_archive_has_no_confirm_points(tmp_path):
    """旧档本身不含 >= confirm_from_ts 的点（现状）→ 断言平凡通过。"""
    _write_prereg(str(tmp_path), [{"prereg_id": "p1", "symbol": "jd",
                                   "confirm_from_ts": "2026-10-03 00:00:00"}])
    archive = tmp_path / "baseline_points_jd_nocov.archive_20260930T1400.jsonl"
    _write_points(archive, ["2026-09-30 14:00:00"])
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2026-10-01 00:00:00"])
    before = pts.read_bytes()
    assert sup._guard_confirm_from_ts_after_regen("jd", str(pts), str(archive), str(tmp_path)) is True
    assert pts.read_bytes() == before


# ── ensure_baselines 集成 ──────────────────────────────────────────

class _FakeGbp:
    def __init__(self):
        self.calls = []

    def baseline_filename(self, sym, cov):
        return f"baseline_points_{sym}_nocov.jsonl"

    def generate(self, sym, cov, root):
        self.calls.append((sym, cov, root))


def _setup_healthy_baseline(root, n=150, fp="fp_test", last_cutoff="2026-09-16 15:00:00"):
    config_dir = os.path.join(root, "task_FM", "config")
    os.makedirs(config_dir, exist_ok=True)
    metrics = {"jd": {"n": 588, "dir_acc": 0.5, "endpoint_mape": 1.0, "n_eff": 73}}
    with open(os.path.join(config_dir, "baseline_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f)
    _write_points(os.path.join(config_dir, "baseline_points_jd_nocov.jsonl"),
                  [last_cutoff] * n, fp=fp)


def test_ensure_baselines_reanchors_on_stale_baseline(tmp_path, monkeypatch):
    """指纹合格但基线落后数据 14 天 → 重锚重生（先归档）。"""
    _setup_healthy_baseline(str(tmp_path))   # 末端 2026-09-16 15:00
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: "2026-09-30 14:00:00")
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp_test")
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)

    sup.ensure_baselines(["JD"], str(tmp_path))

    assert len(fake.calls) == 1
    archives = list((tmp_path / "task_FM" / "config").glob("baseline_points_jd_nocov.archive_*.jsonl"))
    assert len(archives) == 1


def test_ensure_baselines_no_regen_when_fresh(tmp_path, monkeypatch):
    """指纹合格且新鲜（落后 2h）→ 不重生。"""
    _setup_healthy_baseline(str(tmp_path), last_cutoff="2026-10-01 08:00:00")
    monkeypatch.setattr(sup, "_latest_data_dt", lambda s: "2026-10-01 10:00:00")
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp_test")
    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)

    sup.ensure_baselines(["JD"], str(tmp_path))

    assert fake.calls == []
