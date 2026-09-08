#!/usr/bin/env python3
"""Monkeypatch praxist protected_pids.launch_command to enforce mem_guard.

Durable install via scripts/install_praxist_mem_guard_hook.py (.pth loader).

On every gated launch_command:
  1) rss_shed_once()
  2) acquire EvalSlot (flock <=1 + MemAvailable >=2.5GiB); refuse if busy/low
  3) call original (waits for child / process group)
  4) release slot only after original returns

python -m ...protected_pids re-executes as __main__ and calls _cli() *inside*
runpy._run_code, so post-exec wrap is too late. We set a trace during that
exec and wrap launch_command on _cli entry. Also patches the package module.
"""
from __future__ import annotations

import os
import sys
import threading

_PATCHED = False
_RUNPY_PATCHED = False
_LOCK = threading.Lock()


def _repo_scripts_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_mem_guard_importable() -> None:
    scripts = _repo_scripts_dir()
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


_GATE_PATTERNS = (
    "fm_eval",
    "batch_runner",
    "eval_wrapper",
    "aligned_slow_loop",
    "HourlyModel",
    "DailyModel",
    "do_evaluate",
    "cascade_predict",
    "monthly_backtest",
    "timesfm",
    "from evaluations",
    "standalone_eval",
    "run_eval_v",
    "run_eval_direct",
    "/tmp/run_eval",
    "/tmp/standalone_eval",
    "/tmp/eval_",
)


def _should_gate_command(command) -> bool:
    if command is None:
        return True
    try:
        parts = list(command) if not isinstance(command, (str, bytes)) else [command]
    except TypeError:
        return True
    if not parts:
        return True
    joined = " ".join(str(c) for c in parts)
    lower = joined.lower()
    for pat in _GATE_PATTERNS:
        if pat.lower() in lower:
            return True
    return False


def _make_wrapper(orig_fn, mg):
    def launch_command(command, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not _should_gate_command(command):
            return orig_fn(command, *args, **kwargs)
        try:
            mg.rss_shed_once()
        except Exception:
            pass
        block = os.environ.get("FM_MEM_GUARD_BLOCK", "").strip() in (
            "1", "true", "yes",
        )
        slot = None
        try:
            slot = mg.acquire_slot(apply_limit=False, block=block)
        except SystemExit as e:
            mg.log_capacity_action(
                f"hook: refuse launch_command: {e}; cmd={command!r}"
            )
            raise
        prev_held = os.environ.get("FM_EVAL_SLOT_HELD")
        try:
            os.environ["FM_EVAL_SLOT_HELD"] = "1"
            mg.log_capacity_action(
                f"hook: launch slot={slot.slot} cmd={list(command)[:8]!r}"
            )
            return orig_fn(command, *args, **kwargs)
        finally:
            if prev_held is None:
                os.environ.pop("FM_EVAL_SLOT_HELD", None)
            else:
                os.environ["FM_EVAL_SLOT_HELD"] = prev_held
            if slot is not None:
                sid = slot.slot
                slot.release()
                mg.log_capacity_action(
                    f"hook: release slot={sid} after launch returned"
                )

    launch_command._fm_mem_guard_wrapped = True  # type: ignore[attr-defined]
    launch_command._fm_mem_guard_orig = orig_fn  # type: ignore[attr-defined]
    return launch_command


def _wrap_globals_launch(g, mg, reason: str) -> bool:
    if isinstance(g, dict):
        fn = g.get("launch_command")
    else:
        fn = getattr(g, "launch_command", None)
    if not callable(fn):
        return False
    if getattr(fn, "_fm_mem_guard_wrapped", False):
        return True
    wrapped = _make_wrapper(fn, mg)
    if isinstance(g, dict):
        g["launch_command"] = wrapped
    else:
        g.launch_command = wrapped  # type: ignore[attr-defined]
    mg.log_capacity_action(f"hook: launch_command wrapped ({reason})")
    return True


def _ensure_runpy_patch(mg) -> None:
    """Wrap __main__.launch_command on _cli entry (before body runs)."""
    global _RUNPY_PATCHED
    if _RUNPY_PATCHED:
        return
    try:
        import runpy
    except Exception as e:
        mg.log_capacity_action(f"hook: runpy import failed: {e}")
        return

    _orig_run_code = runpy._run_code

    def _run_code(code, run_globals, *args, **kwargs):  # type: ignore[no-untyped-def]
        fname = str(getattr(code, "co_filename", "") or "")
        need = "protected_pids" in fname

        def _trace(frame, event, arg):  # noqa: ANN001
            if event == "call" and frame.f_code.co_name == "_cli":
                try:
                    _wrap_globals_launch(frame.f_globals, mg, "runpy:_cli_entry")
                except Exception as e:
                    mg.log_capacity_action(f"hook: _cli_entry wrap failed: {e}")
            return _trace

        old_trace = sys.gettrace()
        if need:
            sys.settrace(_trace)
        try:
            return _orig_run_code(code, run_globals, *args, **kwargs)
        finally:
            if need:
                sys.settrace(old_trace)
            try:
                if need or (
                    callable(run_globals.get("launch_command"))
                    and callable(run_globals.get("_cli"))
                ):
                    _wrap_globals_launch(run_globals, mg, "runpy:post_exec")
            except Exception:
                pass

    runpy._run_code = _run_code  # type: ignore[assignment]
    _RUNPY_PATCHED = True
    mg.log_capacity_action("hook: runpy._run_code patched (_cli_trace)")


def _patch_main_if_needed(mg) -> bool:
    main = sys.modules.get("__main__")
    if main is None:
        return False
    if not callable(getattr(main, "launch_command", None)):
        return False
    main_file = str(getattr(main, "__file__", "") or "")
    spec = getattr(main, "__spec__", None)
    spec_name = str(getattr(spec, "name", "") or "") if spec is not None else ""
    if not (
        "protected_pids" in main_file
        or "protected_pids" in spec_name
        or hasattr(main, "_cli")
    ):
        return False
    return _wrap_globals_launch(main, mg, "__main__")


def install(force: bool = False) -> bool:
    global _PATCHED
    if os.environ.get("FM_MEM_GUARD_DISABLE", "").strip() in ("1", "true", "yes"):
        return False
    with _LOCK:
        _ensure_mem_guard_importable()
        try:
            from praxist.plugins.workflow_stages.research_loop.backend import (
                protected_pids as pp,
            )
        except Exception as e:
            sys.stderr.write(
                f"praxist_mem_guard_hook: import protected_pids failed: {e}\n"
            )
            return False

        import mem_guard as mg

        _ensure_runpy_patch(mg)
        _patch_main_if_needed(mg)

        if getattr(pp, "_fm_mem_guard_patched", False) and not force:
            _PATCHED = True
            return True

        try:
            mg.rss_shed_watch(interval_s=15.0)
        except Exception as e:
            mg.log_capacity_action(f"hook: rss_shed_watch failed: {e}")

        _orig = pp.launch_command
        if getattr(_orig, "_fm_mem_guard_wrapped", False) and not force:
            pp._fm_mem_guard_patched = True
            _PATCHED = True
            return True

        pp.launch_command = _make_wrapper(_orig, mg)
        pp._fm_mem_guard_patched = True
        _PATCHED = True
        _patch_main_if_needed(mg)
        mg.log_capacity_action(
            "hook: protected_pids.launch_command patched (pkg+_cli_trace)"
        )
        return True


try:
    install()
except Exception as _e:
    sys.stderr.write(f"praxist_mem_guard_hook: install error: {_e}\n")
