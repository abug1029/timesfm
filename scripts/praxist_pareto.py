#!/usr/bin/env python3
"""Pareto 前沿展示工具 (P0c, 2026-09-01)

输入 JSONL (每行 {candidate, pf, ev, maxdd, n}), 按契约门槛过滤后输出 Pareto 前沿。
目标方向: PF/EV 最大化, MaxDD 最大化 (越接近 0 越好), n 为硬门非目标。
"""
import json
import os
import sys

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_N_DEFAULT = 350


def _min_n():
    try:
        import yaml
        with open(os.path.join(FM_ROOT, "config", "praxist_task.yaml")) as f:
            c = (yaml.safe_load(f) or {}).get("constraints") or {}
        v = c.get("min_samples")
        if isinstance(v, int) and v >= 350:
            return v
    except Exception:
        pass
    return MIN_N_DEFAULT


def _dominates(a, b):
    """a 支配 b: 所有目标不差且至少一个严格更好"""
    keys = (("pf", max), ("ev", max), ("maxdd", max))
    not_worse = all(a[k] >= b[k] for k, _ in keys)
    better = any(a[k] > b[k] for k, _ in keys)
    return not_worse and better


def pareto_front(rows):
    gate = _min_n()
    ok = [r for r in rows if r.get("n", 0) >= gate]
    front = []
    for r in ok:
        if not any(_dominates(o, r) for o in ok if o is not r):
            front.append(r)
    return front


def main():
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print("usage: praxist_pareto.py <results.jsonl>", file=sys.stderr)
        sys.exit(2)
    rows = []
    with open(sys.argv[1], encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    front = pareto_front(rows)
    print(f"PARETO FRONT (n>={_min_n()}):")
    for r in front:
        print(f"  {r['candidate']:24s} PF={r.get('pf', 0):.3f} "
              f"EV={r.get('ev', 0):+.4f} MaxDD={r.get('maxdd', 0):.2%} n={r.get('n', 0)}")
    if not front:
        print("  (空 — 无候选过门槛)")
    dom = [r["candidate"] for r in rows if r not in front]
    print(f"被支配/被门过滤: {len(dom)}/{len(rows)}")


if __name__ == "__main__":
    main()
