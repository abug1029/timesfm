#!/usr/bin/env python3
"""Cross-Run Feedback Bridge — 把 supervisor registry 的 per-symbol 过门统计
写成 gate_pass_stats.yaml，供下次运行时 fast-loop 参考历史通过率。

不影响 Praxist 官方 ledger（aligned_verdicts.jsonl 只读不改）。
"""
import sys
from pathlib import Path
from datetime import datetime

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import registry_lib as rl          # noqa: E402
import sup_evidence                # noqa: E402
import sup_paths                   # noqa: E402

# ponytail: output dir comes from caller (sup_loops passes last_run_dir); no hardcoded cache path


def _aggregate():
    """读 registry → 按当前协议过滤 → 按 (symbol, family) 聚合 pass/fail。

    SPEC FR-2 / §4.2.2：聚合维度为 (symbol, cov_family)，每个组合独立统计。
    """
    fp = sup_evidence._current_protocol_fingerprint()
    snap = rl.load_snapshot(sup_paths.REGISTRY, only_protocol=fp)
    stats = {}
    for v in snap.values():
        if not isinstance(v, dict):
            continue
        sym = v.get("symbol")
        if not sym:
            continue
        family = v.get("cov_family") or "unknown"
        # 键为 (symbol, family) 组合
        key = f"{sym}_{family}"
        entry = stats.setdefault(key, {
            "symbol": sym,
            "family": family,
            "pass_count": 0,
            "fail_count": 0,
            "total": 0,
        })
        entry["total"] += 1
        if v.get("gate_pass"):
            entry["pass_count"] += 1
        else:
            entry["fail_count"] += 1
    for entry in stats.values():
        total = entry["total"]
        entry["pass_rate"] = round(entry["pass_count"] / total, 4) if total else 0.0
    return stats


def _write_yaml(stats, path):
    """手写 YAML；字段顺序固定，便于 diff。

    SPEC FR-2：原子写（tmp + os.replace）。
    SPEC §4.2.2：ledger_name / entries 包装。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fp = sup_evidence._current_protocol_fingerprint() or "none"
    now = datetime.now().isoformat(timespec='seconds')
    lines = [
        "ledger_name: gate_pass_stats",
        "description: 自定义旁路统计，非 Praxist 官方 coverage_matrix",
        "version: 1",
        f"# protocol_fingerprint: {fp}",
        "entries:",
    ]
    for key in sorted(stats):
        e = stats[key]
        lines.append(f"  - id: stats_{e['symbol']}_{e['family']}")
        lines.append(f"    symbol: {e['symbol']}")
        lines.append(f"    family: {e['family']}")
        lines.append(f"    pass_count: {e['pass_count']}")
        lines.append(f"    fail_count: {e['fail_count']}")
        lines.append(f"    total: {e['total']}")
        lines.append(f"    pass_rate: {e['pass_rate']}")
        lines.append(f"    updated_at: '{now}'")

    yaml_str = "\n".join(lines) + "\n"

    # 原子写：先写 tmp，再 os.replace
    tmp_path = path.with_suffix('.tmp')
    tmp_path.write_text(yaml_str, encoding="utf-8")
    tmp_path.replace(path)


def run(aligned_verdicts_path=None, run_dir=None):
    """Write gate_pass_stats.yaml into <run_dir>/research_memory/ledgers/.

    If *run_dir* is None, falls back to data/cache/ for backward compat
    (e.g. manual CLI invocation with no supervisor state yet).

    aligned_verdicts_path 参数保留以符合 NFR-4 接口约定（当前未使用，仅验证）。
    """
    stats = _aggregate()
    if run_dir is not None:
        out = Path(run_dir) / "research_memory" / "ledgers" / "gate_pass_stats.yaml"
    else:
        out = Path(sup_paths.FM_ROOT) / "data" / "cache" / "gate_pass_stats.yaml"
    _write_yaml(stats, out)
    print(f"[bridge] wrote {len(stats)} entries -> {out}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python sup_memory_bridge.py <aligned_verdicts.jsonl> <run_dir>")
        print("  aligned_verdicts.jsonl: 对齐判定文件路径（只读）")
        print("  run_dir: 输出目录（gate_pass_stats.yaml 写入 run_dir/research_memory/ledgers/）")
        sys.exit(1)

    aligned_path = Path(sys.argv[1])
    run_dir = Path(sys.argv[2])

    if not aligned_path.exists():
        print(f"错误: aligned_verdicts 文件不存在: {aligned_path}", file=sys.stderr)
        sys.exit(1)

    run(aligned_verdicts_path=aligned_path, run_dir=run_dir)
