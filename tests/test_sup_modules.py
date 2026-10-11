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
