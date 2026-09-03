"""Pareto 前沿工具测试 (P0c, TDD 2026-09-01)"""
import json, os, subprocess, sys
FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(FM_ROOT, "scripts"))
import praxist_pareto as pp
TOOL = os.path.join(FM_ROOT, "scripts", "praxist_pareto.py")


def _row(**kw):
    r = {"candidate": "X", "pf": 1.0, "ev": 0.0, "maxdd": -0.2, "n": 400}
    r.update(kw)
    return r


def test_empty_input():
    assert pp.pareto_front([]) == []


def test_single_on_front():
    assert [r["candidate"] for r in pp.pareto_front([_row(candidate="A")])] == ["A"]


def test_dominated_excluded():
    rows = [
        _row(candidate="good", pf=1.2, ev=0.1, maxdd=-0.1),
        _row(candidate="bad", pf=1.1, ev=0.05, maxdd=-0.3),
    ]
    got = [r["candidate"] for r in pp.pareto_front(rows)]
    assert got == ["good"]


def test_tradeoff_both_on_front():
    rows = [
        _row(candidate="hiPF", pf=1.3, ev=0.02),
        _row(candidate="hiEV", pf=1.1, ev=0.08),
    ]
    got = [r["candidate"] for r in pp.pareto_front(rows)]
    assert got == ["hiPF", "hiEV"]


def test_maxdd_less_negative_wins():
    rows = [
        _row(candidate="a", pf=1.2, ev=0.1, maxdd=-0.1),
        _row(candidate="b", pf=1.2, ev=0.1, maxdd=-0.4),
    ]
    got = [r["candidate"] for r in pp.pareto_front(rows)]
    assert got == ["a"]


def test_gate_filters_low_n():
    rows = [
        _row(candidate="ok", n=400),
        _row(candidate="low", n=200),
    ]
    got = [r["candidate"] for r in pp.pareto_front(rows)]
    assert got == ["ok"]


def test_missing_file_exits_nonzero():
    r = subprocess.run([sys.executable, TOOL, "/nonexistent.jsonl"],
                       capture_output=True, text=True)
    assert r.returncode != 0


def test_cli_end_to_end(tmp_path):
    p = tmp_path / "r.jsonl"
    rows = [_row(candidate="A", pf=1.2, ev=0.1),
            _row(candidate="B", pf=1.1, ev=0.05)]
    p.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
    r = subprocess.run([sys.executable, TOOL, str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "A" in r.stdout and "B" not in r.stdout.split("PARETO FRONT")[-1]
