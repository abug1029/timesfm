#!/usr/bin/env python3
"""Second-level TimesFM eval hard-cap demoter (control-plane ops).

Hard cap=1. Prefer TERM newest inline/python -c / non-canonical; else newest run.py.
Also soft-demote when MemAvailable < 2.5GiB if >1 load; force ≤1 if <2.2GiB.
cgroup ratio ≥0.90 → TERM all matching evals (stop new via flock refuse).
Does not clear SHUTDOWN. Logs to reports + capacity_actions.
"""
from __future__ import annotations
import os, signal, time, sys
from pathlib import Path

REPO = Path('/workspace/repos/timesfm-abug1029')
sys.path.insert(0, str(REPO / 'scripts'))
import mem_guard as mg  # noqa: E402

LOG = REPO / 'docs/superpowers/reports/praxist_20260906_ctrl/mem_guard_watch.log'
INTERVAL = float(os.environ.get('FM_HARDCAP_INTERVAL', '3'))
HARD_CAP = 1
SOFT_MEM = 2.5 * 1024**3
HARD_MEM = 2.2 * 1024**3
CGROUP_STOP = 0.90

def classify(cmd: str) -> str:
    if 'evaluations/fm_eval/run.py' in cmd or 'evaluations/fm_eval/run_eval.py' in cmd:
        return 'run.py'
    low = cmd.lower()
    if (
        ' -c ' in cmd or ' -c"' in cmd or " -c'" in cmd
        or 'do_evaluate' in low
        or 'hourlymodel' in low
        or 'dailymodel' in low
        or 'monthly_backtest' in low
        or 'run_symbol_backtest' in low
        or 'standalone_eval' in low
        or 'run_eval_v' in low
        or 'run_eval_direct' in low
        or '/tmp/run_eval' in low
        or '/tmp/standalone_eval' in low
        or '/tmp/eval_' in low
    ):
        return 'inline'
    return 'other'

def start_time(pid: int) -> int:
    try:
        return int(open(f'/proc/{pid}/stat').read().split()[21])
    except Exception:
        return 0

def list_loads():
    out = []
    for pid, rss, cmd in mg.matching_eval_pids():
        out.append({'pid': pid, 'rss': rss, 'cmd': cmd, 'kind': classify(cmd), 'start': start_time(pid)})
    out.sort(key=lambda x: x['start'])
    return out

def log(msg: str) -> None:
    ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    line = f'{ts} hardcap_daemon: {msg}\n'
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.open('a').write(line)
    except OSError:
        pass
    mg.log_capacity_action(f'hardcap_daemon: {msg}')

def demote(loads, reason: str, target_cap: int = HARD_CAP):
    # prefer kill inline/other newest, then newest run.py
    non = sorted([x for x in loads if x['kind'] != 'run.py'], key=lambda x: -x['start'])
    run = sorted([x for x in loads if x['kind'] == 'run.py'], key=lambda x: -x['start'])
    order = non + run
    killed = []
    while len(loads) > target_cap and order:
        v = order.pop(0)
        try:
            os.kill(v['pid'], signal.SIGTERM)
            killed.append(v)
            log(f'TERM pid={v["pid"]} kind={v["kind"]} reason={reason} cmd={v["cmd"][:120]!r}')
        except ProcessLookupError:
            pass
        time.sleep(0.4)
        loads = list_loads()
        non = sorted([x for x in loads if x['kind'] != 'run.py'], key=lambda x: -x['start'])
        run = sorted([x for x in loads if x['kind'] == 'run.py'], key=lambda x: -x['start'])
        order = non + run
    return killed, loads

def main():
    log(f'start interval={INTERVAL}s hard_cap={HARD_CAP}')
    while True:
        try:
            loads = list_loads()
            avail = mg.mem_available_bytes()
            ratio = mg.cgroup_memory_ratio()
            if ratio is not None and ratio >= CGROUP_STOP and loads:
                demote(loads, f'cgroup>={CGROUP_STOP} ratio={ratio:.3f} n={len(loads)}', target_cap=0)
            elif len(loads) > HARD_CAP:
                demote(loads, f'cap>{HARD_CAP} n={len(loads)} avail={avail}')
            elif avail < HARD_MEM and len(loads) > 1:
                demote(loads, f'mem<{HARD_MEM} n={len(loads)}')
            elif avail < SOFT_MEM and len(loads) > HARD_CAP:
                demote(loads, f'mem<{SOFT_MEM} n={len(loads)}')
        except Exception as e:
            log(f'error {e!r}')
        time.sleep(INTERVAL)

if __name__ == '__main__':
    main()
