#!/usr/bin/env python3
"""Install durable praxist mem_guard hook via site-packages .pth + loader.

Writes into each known praxist venv site-packages:
  - zz_fm_mem_guard.pth          (import zz_fm_mem_guard_loader)
  - zz_fm_mem_guard_loader.py    (imports repo scripts/praxist_mem_guard_hook.py)

Does NOT permanently edit protected_pids.py. Re-run after praxist reinstall.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = FM_ROOT / "scripts" / "praxist_mem_guard_hook.py"

CANDIDATE_SITE = [
    Path("/home/box/.praxist-venv/lib/python3.13/site-packages"),
    FM_ROOT / ".praxist-venv" / "lib" / "python3.13" / "site-packages",
]

LOADER_SRC = '''\
"""Auto-loaded via zz_fm_mem_guard.pth — installs FM mem_guard on praxist start."""
from __future__ import annotations

def _install():
    import importlib.util
    import os
    import sys
    hook = os.environ.get("FM_MEM_GUARD_HOOK") or {hook_path!r}
    if not os.path.isfile(hook):
        # Fallback: relative to this file via FM_ROOT env or common path
        alt = "/workspace/repos/timesfm-abug1029/scripts/praxist_mem_guard_hook.py"
        hook = alt if os.path.isfile(alt) else hook
    if not os.path.isfile(hook):
        return
    scripts = os.path.dirname(hook)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("praxist_mem_guard_hook", hook)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules["praxist_mem_guard_hook"] = mod
    spec.loader.exec_module(mod)

try:
    _install()
except Exception as e:  # noqa: BLE001
    import sys as _sys
    _sys.stderr.write(f"zz_fm_mem_guard_loader: {{e}}\\n")
'''


def install_into(site: Path) -> bool:
    if not site.is_dir():
        print(f"skip (missing): {site}")
        return False
    loader = site / "zz_fm_mem_guard_loader.py"
    pth = site / "zz_fm_mem_guard.pth"
    loader.write_text(LOADER_SRC.format(hook_path=str(HOOK_PATH)), encoding="utf-8")
    pth.write_text("import zz_fm_mem_guard_loader\n", encoding="utf-8")
    print(f"installed: {pth}")
    print(f"installed: {loader}")
    return True


def main() -> int:
    if not HOOK_PATH.is_file():
        print(f"missing hook: {HOOK_PATH}", file=sys.stderr)
        return 2
    n = 0
    for site in CANDIDATE_SITE:
        if install_into(site):
            n += 1
    # Also try the interpreter that is running us, if it is a praxist venv
    try:
        import site as site_mod

        for sp in site_mod.getsitepackages():
            p = Path(sp)
            if "praxist" in str(p) and p not in CANDIDATE_SITE:
                if install_into(p):
                    n += 1
    except Exception:
        pass
    print(f"done: {n} site-packages updated")
    print("note: GLOBAL≤2 enforced by mem_guard flock; "
          "PRAXIST_MAX_PARALLEL_RUNS_PER_PEER is per-peer only")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
