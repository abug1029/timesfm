"""ensure_baselines 协议指纹校验测试（2026-09-28 T1a 实测发现的缺口）。

背景: 原实现只按 n_lines<100 判断，导致 PR-A1 升级指纹后，
已有足够行数的旧基线（rb, 588 行 / protocol_v1）被静默保留，
与新生基线跨协议不可比。
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.praxist_supervisor import (  # noqa: E402
    _baseline_protocol_fingerprint,
    ensure_baselines,
)

CUR_FP = "bd851c9ca0730dc5" + "0" * 48
OLD_FP = "6b8e312085c1a424" + "0" * 48


def _write_baseline(path: Path, n_lines: int, fp):
    with path.open("w", encoding="utf-8") as f:
        for i in range(n_lines):
            rec = {"cutoff": f"2026-01-01 {i:02d}:00:00", "dir_ok": True}
            if fp is not None:
                rec["protocol_fingerprint"] = fp
            f.write(json.dumps(rec) + "\n")


def _write_strict(path: Path, n_lines: int, fp: str):
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    cutoffs = []
    with path.open("w", encoding="utf-8") as handle:
        for i in range(n_lines):
            cutoff = (t0 + timedelta(hours=2 * i)).strftime("%Y-%m-%d %H:%M:%S")
            cutoffs.append(cutoff)
            handle.write(json.dumps({
                "cutoff": cutoff, "dir_ok": True, "delta_pred": 1.0,
                "delta_real": 1.0, "protocol_fingerprint": fp,
            }) + "\n")
    return cutoffs


# ── _baseline_protocol_fingerprint ──────────────────────────────────────

def test_fingerprint_ok(tmp_path):
    p = tmp_path / "b.jsonl"
    _write_baseline(p, 3, CUR_FP)
    assert _baseline_protocol_fingerprint(str(p)) == ("ok", CUR_FP)


def test_fingerprint_missing_key(tmp_path):
    p = tmp_path / "b.jsonl"
    _write_baseline(p, 3, None)
    assert _baseline_protocol_fingerprint(str(p)) == ("missing", None)


def test_fingerprint_empty_file(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text("", encoding="utf-8")
    assert _baseline_protocol_fingerprint(str(p)) == ("missing", None)


def test_fingerprint_unreadable_json(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text("not-json\n", encoding="utf-8")
    assert _baseline_protocol_fingerprint(str(p)) == ("unreadable", None)


def test_fingerprint_missing_file(tmp_path):
    assert _baseline_protocol_fingerprint(str(tmp_path / "nope.jsonl")) == ("unreadable", None)


def test_fingerprint_skips_blank_lines(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text("\n\n" + json.dumps({"protocol_fingerprint": CUR_FP}) + "\n", encoding="utf-8")
    assert _baseline_protocol_fingerprint(str(p)) == ("ok", CUR_FP)


# ── ensure_baselines 指纹分支 ────────────────────────────────────────────

class _FakeGBP(types.ModuleType):
    """伪造 generate_baseline_points，记录 generate 调用。"""
    def __init__(self):
        super().__init__("generate_baseline_points")
        self.calls = []

    def baseline_filename(self, symbol, cov=None):
        return f"baseline_points_{symbol.lower()}_nocov.jsonl"

    def generate(self, symbol, cov, root, finalize=False):
        self.calls.append((symbol, cov))


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """搭一个最小 root：task_FM/config + metrics。"""
    root = tmp_path
    cfg = root / "task_FM" / "config"
    cfg.mkdir(parents=True)

    fake = _FakeGBP()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    monkeypatch.setattr(
        "sup_evidence._current_protocol_fingerprint",
        lambda: CUR_FP,
    )
    monkeypatch.setattr("scripts.incremental_baseline.incremental_generate", lambda *a, **k: None)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: ["2099-01-01 10:00:00"])
    return root, cfg, fake


def _write_metrics(cfg: Path, symbol: str, n: int = 588):
    (cfg / "baseline_metrics.json").write_text(
        json.dumps({symbol: {"n": n}}), encoding="utf-8"
    )


def test_regenerates_on_fingerprint_mismatch(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "rb")
    cutoffs = _write_strict(cfg / "baseline_points_rb_nocov.jsonl", 4, OLD_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["rb"], str(root))
    assert fake.calls == [("rb", None)]


def test_skips_when_fingerprint_matches(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "ss")
    cutoffs = _write_strict(cfg / "baseline_points_ss_nocov.jsonl", 4, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["ss"], str(root))
    assert fake.calls == []


def test_regenerates_when_fingerprint_missing(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "m")
    cutoffs = _write_strict(cfg / "baseline_points_m_nocov.jsonl", 4, CUR_FP)
    text = (cfg / "baseline_points_m_nocov.jsonl").read_text(encoding="utf-8")
    (cfg / "baseline_points_m_nocov.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in json.loads(line).items() if k != "protocol_fingerprint"})
                  for line in text.splitlines() if line.strip()) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["m"], str(root))
    assert fake.calls == [("m", None)]


def test_regenerates_when_too_few_lines(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "cj")
    live = _write_strict(cfg / "baseline_points_cj_nocov.jsonl", 50, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: live[:4])
    ensure_baselines(["cj"], str(root))
    assert fake.calls == [("cj", None)]


def test_metrics_gap_does_not_regen_a_file_that_matches_the_grid(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text("{}", encoding="utf-8")
    cutoffs = _write_strict(cfg / "baseline_points_fu_nocov.jsonl", 4, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["fu"], str(root))
    assert fake.calls == []


def test_short_file_equal_to_grid_is_not_rewritten(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "cj")
    cutoffs = _write_strict(cfg / "baseline_points_cj_nocov.jsonl", 4, CUR_FP)
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: cutoffs)
    ensure_baselines(["cj"], str(root))
    assert fake.calls == []


def test_fingerprint_check_skipped_when_current_unavailable(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    monkeypatch.setattr("sup_evidence._current_protocol_fingerprint", lambda: None)
    _write_metrics(cfg, "sr")
    before = _write_strict(cfg / "baseline_points_sr_nocov.jsonl", 4, OLD_FP)
    path = cfg / "baseline_points_sr_nocov.jsonl"
    raw = path.read_bytes()
    ensure_baselines(["sr"], str(root))
    assert fake.calls == []
    assert path.read_bytes() == raw
    assert before


def test_no_metrics_entry_regenerates(fake_env):
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text("{}", encoding="utf-8")
    ensure_baselines(["fu"], str(root))
    assert fake.calls == [("fu", None)]


def test_multiple_symbols_mixed(fake_env, monkeypatch):
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text(
        json.dumps({"ss": {"n": 4}, "rb": {"n": 4}}), encoding="utf-8")
    ss = _write_strict(cfg / "baseline_points_ss_nocov.jsonl", 4, CUR_FP)
    rb = _write_strict(cfg / "baseline_points_rb_nocov.jsonl", 4, OLD_FP)
    grids = {"ss": ss, "rb": rb}
    monkeypatch.setattr("cascade.eval_grid.baseline_eval_cutoffs", lambda symbol: grids[symbol])
    ensure_baselines(["ss", "rb"], str(root))
    assert fake.calls == [("rb", None)]
