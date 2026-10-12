import sys
from pathlib import Path

# tests/ is a package, so pytest does not put it on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

SAMPLE = '''
s = {}
s.update(over)
s.short_horizon_only = True
name = "%s_%s.json" % ("a", "b")
open("sup.lock")
text = "import praxist_supervisor as s; "
import praxist_supervisor as sup
monkeypatch.setattr(sup, "QUEUE", "x")
monkeypatch.setattr(sup, "load_state", fake)
'''


def test_retarget_only_selected_names_and_ignores_local_s():
    from s1_retarget_patches import retarget_source
    out = retarget_source(SAMPLE, {"QUEUE"})
    assert 'setattr(sup_paths, "QUEUE", "x")' in out
    assert 'setattr(sup, "load_state", fake)' in out
    assert "s.update(over)" in out
    assert "s.short_horizon_only = True" in out
    assert '"%s_%s.json"' in out
    assert "sup.lock" in out
    assert "import praxist_supervisor as s;" in out
