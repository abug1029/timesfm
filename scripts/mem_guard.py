#!/usr/bin/env python3
"""Minimal local memory guards for TimesFM / aligned evals.

Policy (2026-09-04 总管): do NOT use tight RLIMIT_AS as the primary hard cap —
TimesFM safetensors mmap needs VAS ≫ RSS. Prefer:

1) Global flock concurrency semaphore ≤1 + refuse start if MemAvailable < 2.5GiB
2) RSS monitor shed: TERM if single matching process RSS > ~3.5GiB
   OR MemAvailable < 2.5GiB (log → data/cache/capacity_actions.log)
3) If cgroup used: prefer memory.max / memory.high (physical), not RLIMIT_AS alone

RLIMIT_AS remains available but is **optional / OFF by default**.

API summary
-----------
- mem_available_bytes() -> int
- apply_rlimit_as(limit_bytes)  # optional; not primary
- rlimit_preexec_fn(limit_bytes)  # for subprocess preexec_fn when explicitly wanted
- EvalSlot(...): flock slot + MemAvailable gate; apply_limit=False by default
- acquire_slot(...) / apply_mem_guard(...): acquire 1 slot (no RLIMIT unless asked)
- process_rss_bytes(pid) -> int | None
- matching_eval_pids(extra_pids=None) -> list[(pid, rss, cmdline)]
- rss_shed_once(...): one-shot scan + TERM offenders; returns list of actions
- check_and_shed(...): alias of rss_shed_once
- rss_shed_watch(interval_s=15, ...): daemon thread periodically calling rss_shed_once
- log_capacity_action(msg): append to capacity_actions.log
"""
from __future__ import annotations

import fcntl
import os
import re
import resource
import signal
import sys
import threading
import time
from typing import Iterable, Optional

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOCK = os.path.join(FM_ROOT, "data", "cache", "eval_slots.lock")
DEFAULT_ACTION_LOG = os.path.join(FM_ROOT, "data", "cache", "capacity_actions.log")
DEFAULT_MAX_SLOTS = 1
MIN_AVAIL_BYTES = int(2.5 * 1024 * 1024 * 1024)  # 2.5 GiB (control-plane refuse)
CGROUP_REFUSE_RATIO = 0.90  # control-plane: stop new eval at/above this

def cgroup_memory_ratio(
    current_path: str = "/sys/fs/cgroup/memory.current",
    max_path: str = "/sys/fs/cgroup/memory.max",
) -> float | None:
    """Return memory.current/memory.max, or None if unreadable/unlimited."""
    try:
        cur = int(open(current_path, encoding="utf-8").read().strip())
        mx_raw = open(max_path, encoding="utf-8").read().strip()
        if mx_raw in ("", "max"):
            return None
        mx = int(mx_raw)
        if mx <= 0:
            return None
        return cur / mx
    except (OSError, ValueError):
        return None

RSS_LIMIT_BYTES = int(3.5 * 1024 * 1024 * 1024)  # ~3.5 GiB
# Kept for callers that explicitly opt in; NOT applied by default.
RLIMIT_AS_BYTES = 3500 * 1024 * 1024  # ~3.5 GiB (optional only)

# Cmdline fragments that identify TimesFM / eval workers eligible for shed.
DEFAULT_CMD_PATTERNS = (
    "fm_eval",
    "batch_runner",
    "aligned_slow_loop",
    "eval_wrapper",
    "HourlyModel",
    "DailyModel",
    "do_evaluate",
    "cascade_predict",
    "monthly_backtest",
    "run_symbol_backtest",
    # inline python -c bypass of protected_pids (peer Bash)
    "from evaluations",
    "import timesfm",
    # peer-written /tmp loaders (bypass flock)
    "standalone_eval",
    "run_eval_v",
    "run_eval_direct",
    "run_eval_wrapper",
    "/tmp/run_eval",
    "/tmp/standalone_eval",
    "/tmp/eval_",
)
_CMD_RE = re.compile("|".join(re.escape(p) for p in DEFAULT_CMD_PATTERNS))

_HELD_SLOT = None
_WATCH_THREAD = None
_WATCH_STOP = threading.Event()


def mem_available_bytes(path: str = "/proc/meminfo") -> int:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable not found in /proc/meminfo")


def apply_rlimit_as(limit_bytes: int = RLIMIT_AS_BYTES) -> None:
    """Optional: cap address-space (virtual) size for this process.

    Not the primary hard cap — tight RLIMIT_AS conflicts with TimesFM
    safetensors mmap (VAS ≫ RSS). Prefer flock + MemAvailable + RSS shed,
    or cgroup memory.max / memory.high for physical limits.
    """
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard == resource.RLIM_INFINITY:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    else:
        lim = min(limit_bytes, hard)
        resource.setrlimit(resource.RLIMIT_AS, (lim, hard))


def rlimit_preexec_fn(limit_bytes: int = RLIMIT_AS_BYTES):
    """Return a callable suitable for subprocess.Popen(preexec_fn=...)."""

    def _fn():
        apply_rlimit_as(limit_bytes)

    return _fn


def log_capacity_action(msg: str, log_path: str = DEFAULT_ACTION_LOG) -> None:
    """Append one line to capacity_actions.log (best-effort)."""
    try:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except OSError:
        pass


class EvalSlot:
    """Hold one of max_slots exclusive byte-range locks for the process lifetime.

    Primary gate: MemAvailable >= min_avail_bytes and a free flock slot.
    RLIMIT_AS is applied only when apply_limit=True (default False).
    """

    def __init__(
        self,
        lock_path: str = DEFAULT_LOCK,
        max_slots: int = DEFAULT_MAX_SLOTS,
        min_avail_bytes: int = MIN_AVAIL_BYTES,
        rlimit_as: int = RLIMIT_AS_BYTES,
        apply_limit: bool = False,
    ):
        self.lock_path = lock_path
        self.max_slots = int(max_slots)
        self.min_avail_bytes = int(min_avail_bytes)
        self.rlimit_as = int(rlimit_as)
        self.apply_limit = bool(apply_limit)
        self._fp = None
        self.slot = None

    def acquire(self, block: bool = False) -> "EvalSlot":
        ratio = cgroup_memory_ratio()
        if ratio is not None and ratio >= CGROUP_REFUSE_RATIO:
            msg = (
                f"mem_guard: cgroup_ratio={ratio:.3f} >= {CGROUP_REFUSE_RATIO} "
                f"(refuse new eval)"
            )
            log_capacity_action(msg)
            raise SystemExit(msg)
        avail = mem_available_bytes()
        if avail < self.min_avail_bytes:
            msg = (
                f"mem_guard: MemAvailable={avail} < {self.min_avail_bytes} "
                f"(refuse acquire; need >=2.5GiB)"
            )
            log_capacity_action(msg)
            raise SystemExit(msg)
        os.makedirs(os.path.dirname(self.lock_path) or ".", exist_ok=True)
        self._fp = open(self.lock_path, "a+b")
        self._fp.seek(0, os.SEEK_END)
        size = self._fp.tell()
        if size < self.max_slots:
            self._fp.write(b"\0" * (self.max_slots - size))
            self._fp.flush()
        flags = fcntl.LOCK_EX | (0 if block else fcntl.LOCK_NB)
        for i in range(self.max_slots):
            try:
                fcntl.lockf(self._fp.fileno(), flags, 1, i, os.SEEK_SET)
                self.slot = i
                break
            except BlockingIOError:
                continue
        if self.slot is None:
            self._fp.close()
            self._fp = None
            msg = (
                f"mem_guard: all {self.max_slots} eval slots busy "
                f"({self.lock_path}); refuse"
            )
            log_capacity_action(msg)
            raise SystemExit(msg)
        if self.apply_limit:
            apply_rlimit_as(self.rlimit_as)
        return self

    def release(self) -> None:
        if self._fp is not None and self.slot is not None:
            try:
                fcntl.lockf(
                    self._fp.fileno(), fcntl.LOCK_UN, 1, self.slot, os.SEEK_SET
                )
            except OSError:
                pass
        if self._fp is not None:
            try:
                self._fp.close()
            except OSError:
                pass
        self._fp = None
        self.slot = None

    def __enter__(self) -> "EvalSlot":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


def acquire_slot(
    lock_path: str = DEFAULT_LOCK,
    max_slots: int = DEFAULT_MAX_SLOTS,
    min_avail_bytes: int = MIN_AVAIL_BYTES,
    rlimit_as: Optional[int] = None,
    apply_limit: bool = False,
    block: bool = False,
) -> EvalSlot:
    """Acquire 1 eval slot (+ optional RLIMIT_AS). Keep ref until done."""
    if rlimit_as is None:
        rlimit_as = RLIMIT_AS_BYTES
    slot = EvalSlot(
        lock_path=lock_path,
        max_slots=max_slots,
        min_avail_bytes=min_avail_bytes,
        rlimit_as=rlimit_as,
        apply_limit=apply_limit,
    )
    slot.acquire(block=block)
    lim_note = f"RLIMIT_AS={rlimit_as}" if apply_limit else "RLIMIT_AS=off"
    print(
        f"mem_guard: acquired slot={slot.slot}/{max_slots} {lim_note} "
        f"MemAvailable={mem_available_bytes()}",
        flush=True,
    )
    return slot


# Back-compat alias (old name implied RLIMIT; now OFF by default).
def acquire_slot_and_limit(
    lock_path: str = DEFAULT_LOCK,
    max_slots: int = DEFAULT_MAX_SLOTS,
    min_avail_bytes: int = MIN_AVAIL_BYTES,
    rlimit_as: int = RLIMIT_AS_BYTES,
    block: bool = False,
    apply_limit: bool = False,
) -> EvalSlot:
    return acquire_slot(
        lock_path=lock_path,
        max_slots=max_slots,
        min_avail_bytes=min_avail_bytes,
        rlimit_as=rlimit_as,
        apply_limit=apply_limit,
        block=block,
    )


def apply_mem_guard(
    lock_path: str = DEFAULT_LOCK,
    max_slots: int = DEFAULT_MAX_SLOTS,
    min_avail_bytes: int = MIN_AVAIL_BYTES,
    rlimit_as: Optional[int] = None,
    apply_limit: bool = False,
    block: bool = False,
) -> "EvalSlot":
    """Acquire 1 slot (+ optional RLIMIT_AS). Used by aligned_slow_loop at entry.

    Default: flock + MemAvailable only (apply_limit=False). Raises SystemExit
    if MemAvailable < 2.5GiB or all slots busy.
    """
    global _HELD_SLOT
    if rlimit_as is None:
        rlimit_as = RLIMIT_AS_BYTES
    if _HELD_SLOT is not None and _HELD_SLOT.slot is not None:
        if apply_limit:
            apply_rlimit_as(rlimit_as)
        return _HELD_SLOT
    _HELD_SLOT = acquire_slot(
        lock_path=lock_path,
        max_slots=max_slots,
        min_avail_bytes=min_avail_bytes,
        rlimit_as=rlimit_as,
        apply_limit=apply_limit,
        block=block,
    )
    return _HELD_SLOT


def process_rss_bytes(pid: int) -> Optional[int]:
    """Return RSS in bytes for pid, or None if unreadable."""
    try:
        with open(f"/proc/{pid}/statm", encoding="utf-8") as f:
            # statm: size resident ... (pages)
            parts = f.read().split()
            if len(parts) < 2:
                return None
            return int(parts[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError):
        return None


def _cmdline_of(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read().replace(b"\0", b" ")
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def is_timesfm_eval_cmdline(cmd: str) -> bool:
    """True for run.py / model loads / inline python -c TimesFM evals.

    Peers have bypassed protected_pids via `.praxist-venv/bin/python -c "...do_evaluate..."`.
    Those must count toward the global hard cap even when flock never saw them.
    """
    if not cmd:
        return False
    # Must be a python worker (not bash/node that merely mentions patterns in a script)
    head = cmd.lstrip()
    is_python = (
        "python" in head.split(" ", 1)[0]
        or "/python " in head[:80]
        or "/python3 " in head[:80]
        or head.startswith("python ")
        or head.startswith("python3 ")
    )
    if not is_python:
        return False
    # skip launch wrappers / orchestrator (count the child python instead)
    if "protected_pids" in cmd and "launch" in cmd:
        return False
    if "praxist_supervisor" in cmd or "praxist.run run" in cmd:
        return False
    if "praxist_mem_guard" in cmd or "install_praxist_mem_guard" in cmd:
        return False
    if "timesfm_hardcap_daemon" in cmd or "hardcap_daemon" in cmd:
        return False
    lower = cmd.lower()
    for pat in DEFAULT_CMD_PATTERNS:
        if pat.lower() in lower:
            return True
    # python -c with heavy markers (truncated cmdline still often keeps these)
    if " -c " in cmd or ' -c"' in cmd or " -c'" in cmd:
        if any(
            k in lower
            for k in (
                "do_evaluate",
                "hourlymodel",
                "dailymodel",
                "monthly_backtest",
                "run_symbol_backtest",
                "fm_eval",
                "from evaluations",
                "import timesfm",
                "timesfm.",
            )
        ):
            return True
    # peer-written /tmp TimesFM loaders (script path in argv)
    if "/tmp/" in lower and any(
        k in lower
        for k in (
            "run_eval",
            "standalone_eval",
            "eval_",
            "hourlymodel",
            "monthly_backtest",
            "do_evaluate",
            "timesfm",
        )
    ):
        return True
    return False


def matching_eval_pids(
    patterns: Iterable[str] = DEFAULT_CMD_PATTERNS,
    extra_pids: Optional[Iterable[int]] = None,
) -> list[tuple[int, int, str]]:
    """Return [(pid, rss_bytes, cmdline)] for matching eval-like processes."""
    pat = re.compile("|".join(re.escape(p) for p in patterns))
    found: list[tuple[int, int, str]] = []
    seen: set[int] = set()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return found
    for name in entries:
        if not name.isdigit():
            continue
        pid = int(name)
        cmd = _cmdline_of(pid)
        if not cmd:
            continue
        # Launch wrappers are never eval loads (count the child python instead).
        if "protected_pids" in cmd and "launch" in cmd:
            continue
        if "timesfm_hardcap_daemon" in cmd or "hardcap_daemon" in cmd:
            continue
        # Prefer is_timesfm_eval_cmdline (python-only). Fallback regex only for
        # python workers so bash/node shells that embed pattern text in scripts
        # are never counted as eval loads.
        if is_timesfm_eval_cmdline(cmd):
            pass
        elif ("python" in cmd.split(" ", 1)[0] or "/python" in cmd[:100]) and pat.search(cmd):
            pass
        else:
            continue
        rss = process_rss_bytes(pid)
        if rss is None:
            continue
        found.append((pid, rss, cmd.strip()[:200]))
        seen.add(pid)
    if extra_pids:
        for pid in extra_pids:
            if pid in seen:
                continue
            rss = process_rss_bytes(pid)
            if rss is None:
                continue
            found.append((pid, rss, _cmdline_of(pid).strip()[:200]))
    return found


def rss_shed_once(
    rss_limit_bytes: int = RSS_LIMIT_BYTES,
    min_avail_bytes: int = MIN_AVAIL_BYTES,
    patterns: Iterable[str] = DEFAULT_CMD_PATTERNS,
    pids: Optional[Iterable[int]] = None,
    log_path: str = DEFAULT_ACTION_LOG,
    signal_num: int = signal.SIGTERM,
) -> list[dict]:
    """One-shot RSS / MemAvailable shed.

    TERM matching processes when:
      - that process RSS > rss_limit_bytes (~3.5GiB), OR
      - MemAvailable < min_avail_bytes (2.5GiB) — shed highest-RSS offenders
        until available recovers or no candidates left (newest/highest first).

    Returns list of action dicts. Does not raise.
    """
    actions: list[dict] = []
    try:
        avail = mem_available_bytes()
    except RuntimeError as e:
        log_capacity_action(f"rss_shed_once: meminfo error: {e}", log_path)
        return actions

    procs = matching_eval_pids(patterns=patterns, extra_pids=pids)
    # Per-process RSS overshoot
    for pid, rss, cmd in procs:
        if rss > rss_limit_bytes:
            try:
                os.kill(pid, signal_num)
                act = {
                    "action": "TERM",
                    "reason": "rss_over_limit",
                    "pid": pid,
                    "rss": rss,
                    "limit": rss_limit_bytes,
                    "cmd": cmd,
                }
                actions.append(act)
                log_capacity_action(
                    f"TERM pid={pid} reason=rss_over_limit "
                    f"rss={rss} limit={rss_limit_bytes} cmd={cmd!r}",
                    log_path,
                )
            except OSError as e:
                log_capacity_action(f"TERM failed pid={pid}: {e}", log_path)

    # Host pressure: shed highest-RSS matching procs while avail < floor
    if avail < min_avail_bytes:
        # Refresh list (some may already be gone)
        procs = matching_eval_pids(patterns=patterns, extra_pids=pids)
        # Prefer shedding highest RSS first
        for pid, rss, cmd in sorted(procs, key=lambda t: t[1], reverse=True):
            try:
                avail = mem_available_bytes()
            except RuntimeError:
                break
            if avail >= min_avail_bytes:
                break
            # Skip already terminated in this pass
            if any(a.get("pid") == pid for a in actions):
                continue
            try:
                os.kill(pid, signal_num)
                act = {
                    "action": "TERM",
                    "reason": "mem_available_low",
                    "pid": pid,
                    "rss": rss,
                    "avail": avail,
                    "floor": min_avail_bytes,
                    "cmd": cmd,
                }
                actions.append(act)
                log_capacity_action(
                    f"TERM pid={pid} reason=mem_available_low "
                    f"avail={avail} floor={min_avail_bytes} rss={rss} cmd={cmd!r}",
                    log_path,
                )
            except OSError as e:
                log_capacity_action(f"TERM failed pid={pid}: {e}", log_path)
    return actions


def check_and_shed(**kwargs) -> list[dict]:
    """Alias for rss_shed_once (caller-friendly name)."""
    return rss_shed_once(**kwargs)


def rss_shed_watch(
    interval_s: float = 15.0,
    rss_limit_bytes: int = RSS_LIMIT_BYTES,
    min_avail_bytes: int = MIN_AVAIL_BYTES,
    patterns: Iterable[str] = DEFAULT_CMD_PATTERNS,
    log_path: str = DEFAULT_ACTION_LOG,
    daemon: bool = True,
) -> threading.Thread:
    """Start a daemon thread that periodically runs rss_shed_once.

    Idempotent: only one watcher per process. Returns the thread.
    """
    global _WATCH_THREAD
    if _WATCH_THREAD is not None and _WATCH_THREAD.is_alive():
        return _WATCH_THREAD

    _WATCH_STOP.clear()

    def _loop():
        while not _WATCH_STOP.wait(interval_s):
            try:
                rss_shed_once(
                    rss_limit_bytes=rss_limit_bytes,
                    min_avail_bytes=min_avail_bytes,
                    patterns=patterns,
                    log_path=log_path,
                )
            except Exception as e:  # noqa: BLE001 — never kill host on watch error
                log_capacity_action(f"rss_shed_watch error: {e}", log_path)

    t = threading.Thread(target=_loop, name="mem_guard_rss_shed", daemon=daemon)
    t.start()
    _WATCH_THREAD = t
    log_capacity_action(
        f"rss_shed_watch started interval_s={interval_s} "
        f"rss_limit={rss_limit_bytes} avail_floor={min_avail_bytes}",
        log_path,
    )
    return t


def stop_rss_shed_watch() -> None:
    _WATCH_STOP.set()


def self_rss_ok(rss_limit_bytes: int = RSS_LIMIT_BYTES) -> bool:
    """Cheap self-check: True if this process RSS is under limit (or unreadable)."""
    rss = process_rss_bytes(os.getpid())
    if rss is None:
        return True
    return rss <= rss_limit_bytes


if __name__ == "__main__":
    # smoke: acquire (no RLIMIT), print, release; one shed pass
    s = apply_mem_guard()
    print(f"ok slot={s.slot}")
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    print(f"RLIMIT_AS soft={soft} hard={hard} (expected unlimited / unchanged)")
    print(f"MemAvailable={mem_available_bytes()}")
    acts = rss_shed_once()
    print(f"shed_actions={acts}")
    s.release()
    sys.exit(0)
