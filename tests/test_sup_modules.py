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
