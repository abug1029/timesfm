import atexit
import json
import os
import signal
import sys
import threading
import time
import uuid
from datetime import datetime

import sup_paths

_EVENT_LOCK = threading.Lock()
_SHUTDOWN_REQUESTED = False
_RUN_ID = uuid.uuid4().hex[:12]
_START_TIME = time.time()
_STOP_EMITTED = False


def _now_iso():
    return datetime.now().isoformat()


def _mark_stop_emitted():
    global _STOP_EMITTED
    _STOP_EMITTED = True


# ── Event monitoring system ──────────────────────────────────

def _emit_event(level, event, data=None, **extra):
    """Append a structured event to the events JSONL.

    Thread-safe via _EVENT_LOCK. On write failure, falls back to stderr.
    Never raises — monitoring must not crash the supervisor.
    """
    rec = {
        "ts": _now_iso(),
        "schema_version": 1,
        "run_id": _RUN_ID,
        "pid": os.getpid(),
        "level": level,
        "event": event,
        "data": data or {},
    }
    rec.update(extra)
    line = json.dumps(rec, ensure_ascii=False, default=str)
    try:
        os.makedirs(os.path.dirname(sup_paths.EVENTS_PATH), exist_ok=True)
        with _EVENT_LOCK:
            with open(sup_paths.EVENTS_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
    except OSError as e:
        print(f"[EVENT_FALLBACK] {line}", file=sys.stderr)
    if event == "supervisor_stopped":
        _mark_stop_emitted()
        _write_stop_json(rec)


def _write_stop_json(event_rec):
    """Write a timestamped stop report JSON (keeps history)."""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.dirname(sup_paths.STOP_REPORT_JSON),
                            f"stop_report_{ts}.json")
        report = {
            "ts": _now_iso(),
            "run_id": _RUN_ID,
            "pid": os.getpid(),
            "uptime_s": round(time.time() - _START_TIME, 1),
            "event": event_rec.get("event"),
            "data": event_rec.get("data", {}),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        with open(sup_paths.STOP_REPORT_JSON, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[STOP_REPORT_ERROR] {e}", file=sys.stderr)


_LAST_HB_WRITE = 0.0

def _write_heartbeat():
    """Write heartbeat timestamp. Called each main loop iteration.

    Throttled to at most once per second so a tight caller, including
    ensure_baselines, does not rewrite the heartbeat file on every symbol.
    A failed write still advances the stamp, so a persistent OSError does
    not print a warning on every call.
    """
    global _LAST_HB_WRITE
    now = time.monotonic()
    if now - _LAST_HB_WRITE < 1.0:
        return
    try:
        os.makedirs(os.path.dirname(sup_paths.HEARTBEAT_PATH), exist_ok=True)
        with open(sup_paths.HEARTBEAT_PATH, "w") as f:
            f.write(json.dumps({"ts": _now_iso(), "run_id": _RUN_ID,
                                "pid": os.getpid()}))
    except OSError as e:
        print(f"[WARN] Failed to write heartbeat: {e}", file=sys.stderr)
    finally:
        _LAST_HB_WRITE = now


def _signal_handler(signum, frame):
    """Signal handler: set flag only, no I/O. Main loop detects and emits event."""
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True


def _shutdown_exit():
    """标志为真时走与循环顶相同的干净退出。不收割，不启动新 run，不杀已经在跑的子进程。"""
    if not _SHUTDOWN_REQUESTED:
        return None
    _emit_event("critical", "supervisor_stopped", {
        "reason": "signal_received",
        "exit_code": 0,
        "uptime_s": round(time.time() - _START_TIME, 1),
    })
    return 0


def _sleep_interruptible(seconds):
    """最多睡 seconds 秒。每 1 秒看一次标志。处理函数本身仍然只置标志。"""
    remaining = max(1, int(seconds))
    while remaining > 0:
        if _SHUTDOWN_REQUESTED:
            return
        time.sleep(1)
        remaining -= 1


def _atexit_handler():
    """Emit stop event on any exit path not already handled."""
    global _STOP_EMITTED
    if _STOP_EMITTED:
        return
    if os.path.exists(sup_paths.STOP_REPORT_JSON):
        try:
            existing = json.load(open(sup_paths.STOP_REPORT_JSON, encoding="utf-8"))
            if existing.get("run_id") == _RUN_ID:
                return
        except (OSError, json.JSONDecodeError):
            pass
    # atexit 兜底只在未覆盖的退出(未捕获异常等; CPython 此类退出码=1)触发。
    # 干净退出(goal_reached/budget_exhausted/dry-run/one-shot/signal)已先 _mark_stop_emitted()。
    # 历史 bug: getattr(sys,"exitcode",1) 中 sys.exitcode 并非标准属性, hasattr 恒 False,
    # 导致任何干净退出在漏标时都被记 exit_code=1。
    _emit_event("critical", "supervisor_stopped", {
        "reason": "unexpected_exit",
        "exit_code": 1,
        "uptime_s": round(time.time() - _START_TIME, 1),
    })


# Signal/atexit handlers are armed only when main() actually runs the supervisor.
# 历史 bug: 这些在 import 时注册, 导致仅把本模块当库 import 的只读脚本/测试
# (调 harvest_proposals/build_snapshot 等) 退出时被 atexit 误报 unexpected_exit。
_HANDLERS_ARMED = False

def _arm_handlers():
    global _HANDLERS_ARMED
    if _HANDLERS_ARMED:
        return
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_atexit_handler)
    _HANDLERS_ARMED = True


def _log_decision(log_path, action, reason, refs=None):
    rec = {"ts": _now_iso(), "action": action, "reason": reason, "refs": refs or []}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
