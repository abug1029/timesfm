#!/usr/bin/env python3
"""Monkeypatch praxist protected_pids.launch_command to enforce mem_guard.

Durable install via scripts/install_praxist_mem_guard_hook.py (.pth loader).
Does NOT permanently edit protected_pids.py in site-packages.

On every launch_command:
  1) rss_shed_once() (pressure relief)
  2) acquire global EvalSlot (flock ≤2 + MemAvailable ≥2GiB); refuse if busy/low
  3) call original launch_command (subprocess.run ~L523 or Popen ~L592 paths)
  4) release slot when launch returns

Also starts rss_shed_watch daemon (light periodic shed) once per interpreter.

Env:
  FM_MEM_GUARD_DISABLE=1  — skip patch (escape hatch)
  FM_MEM_GUARD_BLOCK=1    — block waiting for a free slot (default: refuse)
  PRAXIST_MAX_PARALLEL_RUNS_PER_PEER — per-peer only; GLOBAL≤2 is the flock
"""
from __future__ import annotations

import os
import sys
import threading

_PATCHED = False
_LOCK = threading.Lock()


def _repo_scripts_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_mem_guard_importable() -> None:
    scripts = _repo_scripts_dir()
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


# Heavy TimesFM / eval cmdline fragments (aligned with mem_guard.DEFAULT_CMD_PATTERNS).
# Intentionally NO bare "sh" substring — that matched almost every argv.
_GATE_PATTERNS = (
    "fm_eval",
    "batch_runner",
    "eval_wrapper",
    "aligned_slow_loop",
    "HourlyModel",
    "cascade_predict",
    "monthly_backtest",
    "timesfm",
)


def _should_gate_command(command) -> bool:
    """Decide whether launch_command must take an EvalSlot (GLOBAL≤2).

    True for known heavy TimesFM/eval cmds (see _GATE_PATTERNS). Empty or
    unparseable argv also gates (cautious): protected_pids is for peer long
    jobs and failing open would bypass flock. Recognized non-matching argv
    returns False so light helper launches are not serialized.
    """
    if command is None:
        return True
    try:
        parts = list(command) if not isinstance(command, (str, bytes)) else [command]
    except TypeError:
        return True  # unparseable → cautious gate
    if not parts:
        return True  # empty → cautious gate
    joined = " ".join(str(c) for c in parts)
    lower = joined.lower()
    for pat in _GATE_PATTERNS:
        if pat.lower() in lower:
            return True
    return False


def install(force: bool = False) -> bool:
    """Patch protected_pids.launch_command. Idempotent. Returns True if patched."""
    global _PATCHED
    if os.environ.get("FM_MEM_GUARD_DISABLE", "").strip() in ("1", "true", "yes"):
        return False
    with _LOCK:
        if _PATCHED and not force:
            return True
        _ensure_mem_guard_importable()
        try:
            from praxist.plugins.workflow_stages.research_loop.backend import (  # noqa: WPS433
                protected_pids as pp,
            )
        except Exception as e:  # noqa: BLE001
            # Not in a praxist env — silent no-op
            sys.stderr.write(f"praxist_mem_guard_hook: import protected_pids failed: {e}\n")
            return False

        if getattr(pp, "_fm_mem_guard_patched", False) and not force:
            _PATCHED = True
            return True

        import mem_guard as mg  # noqa: WPS433

        # Start background RSS shed once
        try:
            mg.rss_shed_watch(interval_s=15.0)
        except Exception as e:  # noqa: BLE001
            mg.log_capacity_action(f"hook: rss_shed_watch failed: {e}")

        _orig = pp.launch_command

        def launch_command(command, *args, **kwargs):  # type: ignore[no-untyped-def]
            if not _should_gate_command(command):
                return _orig(command, *args, **kwargs)

            # Pre-launch shed + global slot
            try:
                mg.rss_shed_once()
            except Exception:  # noqa: BLE001
                pass

            block = os.environ.get("FM_MEM_GUARD_BLOCK", "").strip() in (
                "1",
                "true",
                "yes",
            )
            slot = None
            try:
                slot = mg.acquire_slot(apply_limit=False, block=block)
            except SystemExit as e:
                mg.log_capacity_action(
                    f"hook: refuse launch_command: {e}; cmd={command!r}"
                )
                raise
            try:
                mg.log_capacity_action(
                    f"hook: launch slot={slot.slot} cmd={list(command)[:8]!r}"
                )
                return _orig(command, *args, **kwargs)
            finally:
                if slot is not None:
                    slot.release()

        pp.launch_command = launch_command  # type: ignore[assignment]
        pp._fm_mem_guard_patched = True
        _PATCHED = True
        mg.log_capacity_action("hook: protected_pids.launch_command patched")
        return True


# Auto-install when imported (via .pth loader).
try:
    install()
except Exception as _e:  # noqa: BLE001
    sys.stderr.write(f"praxist_mem_guard_hook: install error: {_e}\n")
