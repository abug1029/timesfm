import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s1_symbol_home import ASSIGNS, FUNCS, HOME, NESTED, OVERRIDES

RAW = {
    "sup_paths": (0, 23),
    "sup_env": (5, 1),
    "sup_state": (15, 5),
    "sup_lifecycle": (11, 6),
    "sup_provider": (15, 0),
    "sup_harvest": (14, 6),
    "sup_evidence": (43, 7),
    "sup_family": (21, 9),
    "sup_loops": (26, 0),
}
EFFECTIVE = {
    "sup_paths": (0, 23),
    "sup_env": (5, 1),
    "sup_state": (15, 6),
    "sup_lifecycle": (11, 6),
    "sup_provider": (15, 0),
    "sup_harvest": (14, 4),
    "sup_evidence": (43, 11),
    "sup_family": (21, 6),
    "sup_loops": (26, 0),
}

def test_raw_appendix_and_effective_home():
    assert len(FUNCS) == 150
    assert len(ASSIGNS) == 57
    assert len(NESTED) == 10
    assert set(HOME) == set(FUNCS) | set(ASSIGNS)
    assert NESTED["family_for"] == "_maybe_enqueue_confirmations"
    assert NESTED["is_valid_tier"] == "build_snapshot"
    assert "is_valid_tier" not in FUNCS
    assert OVERRIDES == {
        "CROSS_MATRIX_MAX_ROWS": "sup_evidence",
        "OLD_PRIORS_MAX_ROWS": "sup_evidence",
        "_CONFIRMATORY_DM": "sup_evidence",
        "_CONFIRM_DATA_CACHE": "sup_state",
        "_CONFIRM_DATA_TTL_S": "sup_state",
        "_ev_mod_for_goal": "sup_evidence",
    }
    for name, mod in OVERRIDES.items():
        assert ASSIGNS[name] != mod
        assert HOME[name] == mod
    for mod, (nf, na) in RAW.items():
        assert sum(1 for m in FUNCS.values() if m == mod) == nf
        assert sum(1 for m in ASSIGNS.values() if m == mod) == na
    for mod, (nf, na) in EFFECTIVE.items():
        assert sum(1 for m in FUNCS.values() if m == mod) == nf
        assert sum(1 for name, m in HOME.items() if name in ASSIGNS and m == mod) == na
