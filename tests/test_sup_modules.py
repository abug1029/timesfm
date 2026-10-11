import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))


def test_queue_busy_reads_sup_paths_at_call_time(monkeypatch):
    import registry_lib
    import sup_paths
    import praxist_supervisor as sup
    seen = []
    monkeypatch.setattr(sup_paths, "QUEUE", "SENTINEL_Q")
    monkeypatch.setattr(sup_paths, "INPROGRESS", "SENTINEL_I")

    def fake_load(path):
        seen.append(path)
        return []

    monkeypatch.setattr(registry_lib, "queue_load", fake_load)
    assert sup._queue_busy() is False
    assert seen == ["SENTINEL_Q", "SENTINEL_I"]


def test_shim_here_follows_sup_paths(monkeypatch):
    import sup_paths
    import praxist_supervisor as sup
    monkeypatch.setattr(sup_paths, "HERE", "/tmp/s1-here")
    monkeypatch.setattr(sup_paths, "FM_ROOT", "/tmp/s1-root")
    assert sup.HERE == "/tmp/s1-here"
    assert sup.FM_ROOT == "/tmp/s1-root"
    assert "HERE" not in vars(sup)
    assert "FM_ROOT" not in vars(sup)


def test_praxist_bin_cache_lives_on_sup_env():
    import sup_env
    saved = sup_env._PRAXIST
    try:
        sup_env._PRAXIST = "/tmp/fake-praxist"
        assert sup_env._praxist_bin() == "/tmp/fake-praxist"
    finally:
        sup_env._PRAXIST = saved

def test_goal_symbols_cache_resets_on_sup_state():
    import sup_state
    saved = sup_state._GOAL_SYMBOLS_CACHE
    try:
        sup_state._GOAL_SYMBOLS_CACHE = frozenset({"rb"})
        sup_state._reset_goal_symbols_cache()
        assert sup_state._GOAL_SYMBOLS_CACHE is None
    finally:
        sup_state._GOAL_SYMBOLS_CACHE = saved


def test_sleep_interruptible_sees_lifecycle_flag(monkeypatch):
    import sup_lifecycle
    calls = []
    monkeypatch.setattr(sup_lifecycle.time, "sleep", lambda n: calls.append(n))
    monkeypatch.setattr(sup_lifecycle, "_SHUTDOWN_REQUESTED", True)
    sup_lifecycle._sleep_interruptible(5)
    assert calls == []


def test_parse_429_reset_stays_on_provider():
    import sup_provider
    text = "reset at 2026-10-11 01:02:03 +0800"
    assert sup_provider.parse_429_reset(text) is not None


def test_is_valid_tier_is_module_level_on_evidence():
    import inspect
    import sup_evidence
    assert inspect.isfunction(sup_evidence.is_valid_tier)
    src = inspect.getsource(sup_evidence.build_snapshot)
    assert "def is_valid_tier" not in src


def test_fingerprint_bodies_match_baseline():
    import ast
    import inspect
    import subprocess
    import sup_evidence
    old = subprocess.check_output(
        ["git", "show", "9850af2:scripts/praxist_supervisor.py"], text=True)
    old_tree = ast.parse(old)
    wanted = {"_current_protocol_fingerprint", "_baseline_protocol_fingerprint"}
    old_src = {}
    for node in old_tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            old_src[node.name] = ast.dump(node, include_attributes=False)
    for name in wanted:
        got = ast.parse(inspect.getsource(getattr(sup_evidence, name)))
        assert ast.dump(got.body[0], include_attributes=False) == old_src[name]


def test_prescreen_import_failure_logs_on_harvest_module(monkeypatch):
    import sys
    import sup_harvest
    seen = []

    class FakeLog:
        def warning(self, *args, **kwargs):
            seen.append(args)

    monkeypatch.setattr(sup_harvest, "logging", FakeLog())
    monkeypatch.setitem(sys.modules, "cascade.typesafe_prescreen", None)
    sup_harvest._prescreen_async({}, "/tmp/no-such.json", "rb")
    assert seen
    assert "TypeSafe" in seen[0][0]
