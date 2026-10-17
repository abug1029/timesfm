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
    assert "Laya" in seen[0][0]


def test_family_for_stays_nested_over_pool():
    import inspect
    import sup_family
    assert not hasattr(sup_family, "family_for")
    src = inspect.getsource(sup_family._maybe_enqueue_confirmations)
    assert "def family_for(cov):" in src
    assert "pool.get(cov)" in src


PUBLIC = [
    "fdr_pass_persistable", "promote_batch_for_persistence", "family_key_for",
    "register_family_member", "seal_research_family", "dispatch_confirmation",
    "finalize_confirmation", "confirmation_queue_row", "due_confirmations",
    "load_preregistry", "load_family_members", "save_family_members",
    "parse_429_reset", "load_state", "save_state", "load_goal", "quota_gate",
    "symbol_goal_tier", "build_snapshot", "harvest_survivors",
    "collect_proposed_variant_ids", "materialize_known_verdicts",
    "load_covariate_pool", "load_symbol_status", "harvest_proposals",
    "materialize_covariate_menu", "plan_sample_retests", "ensure_phase",
    "write_stop_report", "decide_fast_loop", "main", "ensure_baselines",
    "wait_for_batch", "cleanup_batch_workers", "is_valid_tier",
]

def test_shim_public_and_all_and_size():
    import ast
    import praxist_supervisor as sup
    for name in PUBLIC:
        assert hasattr(sup, name), name
    text = open(
        "docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md",
        encoding="utf-8",
    ).read()
    start = text.index("__all__ = [")
    end = text.index("]", start)
    expected = ast.literal_eval(text[start:end + 1].split("=", 1)[1])
    assert list(sup.__all__) == expected
    assert len(sup.__all__) >= 80
    assert len(open(sup.__file__, encoding="utf-8").read().splitlines()) <= 200

def test_no_import_cycle_and_no_back_edges():
    import ast
    from pathlib import Path
    forbidden = {
        "sup_paths": {"sup_env", "sup_state", "sup_lifecycle", "sup_provider",
                      "sup_evidence", "sup_harvest", "sup_family", "sup_loops",
                      "praxist_supervisor"},
        "sup_env": {"sup_provider", "sup_evidence", "sup_harvest", "sup_family",
                    "sup_loops", "praxist_supervisor"},
        "sup_state": {"sup_provider", "sup_evidence", "sup_harvest", "sup_family",
                      "sup_loops", "praxist_supervisor"},
        "sup_lifecycle": {"sup_provider", "sup_evidence", "sup_harvest",
                          "sup_family", "sup_loops", "praxist_supervisor"},
        "sup_provider": {"sup_evidence", "sup_harvest", "sup_family", "sup_loops",
                         "praxist_supervisor"},
        "sup_evidence": {"sup_harvest", "sup_family", "sup_loops", "praxist_supervisor"},
        "sup_harvest": {"sup_family", "sup_loops", "praxist_supervisor"},
        "sup_family": {"sup_loops", "praxist_supervisor"},
        "sup_loops": {"praxist_supervisor"},
    }
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name, bad in forbidden.items():
        tree = ast.parse((scripts / f"{name}.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(bad), (name, imported & bad)

def test_no_patch_left_on_shim_for_home_symbols():
    import ast
    import sys
    from pathlib import Path
    # tests/ is a package, so pytest does not put it on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from s1_symbol_home import HOME
    root = Path(__file__).resolve().parents[1] / "tests"
    for path in root.rglob("*.py"):
        if "archive" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in {"praxist_supervisor", "scripts.praxist_supervisor"}:
                        aliases.add(a.asname or "praxist_supervisor")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "setattr":
                continue
            if len(node.args) < 2:
                continue
            target, attr = node.args[0], node.args[1]
            if isinstance(target, ast.Name) and target.id in aliases:
                if isinstance(attr, ast.Constant) and attr.value in HOME:
                    raise AssertionError(f"{path}:{node.lineno} still patches shim {attr.value}")
