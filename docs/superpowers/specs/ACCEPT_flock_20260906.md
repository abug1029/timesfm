# mem_guard flock A+C acceptance (2026-09-06)

## Scope
- `MIN_AVAIL_BYTES=2.5GiB`, `DEFAULT_MAX_SLOTS=1`
- Hook wraps `python -m …protected_pids` via runpy `_cli` entry trace
- Slot held until original `launch_command` returns

## ACCEPT4_20260906T084514Z
1. First launch: `hook: launch_command wrapped (runpy:_cli_entry)` + `hook: launch slot=0`
2. Parallel second launch: `all 1 eval slots busy … refuse` (exit 1); `hook: refuse launch_command` in `data/cache/capacity_actions.log`

## Files
- `scripts/mem_guard.py`
- `scripts/praxist_mem_guard_hook.py`
- `scripts/timesfm_hardcap_daemon.py` (3s demote fallback)
