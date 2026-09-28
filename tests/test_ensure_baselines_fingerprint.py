"""ensure_baselines 协议指纹校验测试（2026-09-28 T1a 实测发现的缺口）。

背景: 原实现只按 n_lines<100 判断，导致 PR-A1 升级指纹后，
已有足够行数的旧基线（rb, 588 行 / protocol_v1）被静默保留，
与新生基线跨协议不可比。
"""
from __future__ import annotations

import json
import sys
import types
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

    def generate(self, symbol, cov, root):
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
        "scripts.praxist_supervisor._current_protocol_fingerprint",
        lambda: CUR_FP,
    )
    return root, cfg, fake


def _write_metrics(cfg: Path, symbol: str, n: int = 588):
    (cfg / "baseline_metrics.json").write_text(
        json.dumps({symbol: {"n": n}}), encoding="utf-8"
    )


def test_regenerates_on_fingerprint_mismatch(fake_env):
    """核心回归: 行数够但指纹不符 -> 必须重生。"""
    root, cfg, fake = fake_env
    _write_metrics(cfg, "rb")
    _write_baseline(cfg / "baseline_points_rb_nocov.jsonl", 588, OLD_FP)

    ensure_baselines(["rb"], str(root))

    assert fake.calls == [("rb", None)], "指纹不符时必须触发重生"


def test_skips_when_fingerprint_matches(fake_env):
    root, cfg, fake = fake_env
    _write_metrics(cfg, "ss")
    _write_baseline(cfg / "baseline_points_ss_nocov.jsonl", 588, CUR_FP)

    ensure_baselines(["ss"], str(root))

    assert fake.calls == [], "指纹相符时不得重生"


def test_regenerates_when_fingerprint_missing(fake_env):
    """pre-A1 遗留基线（首行无指纹）也必须重生。"""
    root, cfg, fake = fake_env
    _write_metrics(cfg, "m")
    _write_baseline(cfg / "baseline_points_m_nocov.jsonl", 588, None)

    ensure_baselines(["m"], str(root))

    assert fake.calls == [("m", None)]


def test_regenerates_when_too_few_lines(fake_env):
    """原有行为不得回归: 行数不足仍重生。"""
    root, cfg, fake = fake_env
    _write_metrics(cfg, "cj")
    _write_baseline(cfg / "baseline_points_cj_nocov.jsonl", 50, CUR_FP)

    ensure_baselines(["cj"], str(root))

    assert fake.calls == [("cj", None)]


def test_fingerprint_check_skipped_when_current_unavailable(fake_env, monkeypatch):
    """当前指纹不可得时跳过校验（并告警），不得误删可用基线。"""
    root, cfg, fake = fake_env
    monkeypatch.setattr(
        "scripts.praxist_supervisor._current_protocol_fingerprint",
        lambda: None,
    )
    _write_metrics(cfg, "sr")
    _write_baseline(cfg / "baseline_points_sr_nocov.jsonl", 588, OLD_FP)

    ensure_baselines(["sr"], str(root))

    assert fake.calls == [], "指纹不可得时不得触发重生"


def test_no_metrics_entry_regenerates(fake_env):
    """原有冷启动行为不得回归。"""
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text("{}", encoding="utf-8")

    ensure_baselines(["fu"], str(root))

    assert fake.calls == [("fu", None)]


def test_multiple_symbols_mixed(fake_env):
    """混合场景: 只有指纹不符的那个重生。"""
    root, cfg, fake = fake_env
    (cfg / "baseline_metrics.json").write_text(
        json.dumps({"ss": {"n": 588}, "rb": {"n": 588}}), encoding="utf-8"
    )
    _write_baseline(cfg / "baseline_points_ss_nocov.jsonl", 588, CUR_FP)
    _write_baseline(cfg / "baseline_points_rb_nocov.jsonl", 588, OLD_FP)

    ensure_baselines(["ss", "rb"], str(root))

    assert fake.calls == [("rb", None)]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
