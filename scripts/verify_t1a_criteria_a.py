#!/usr/bin/env python3
"""T1a 判据验证脚本 — 判据 A（接线层）+ 判据 B'（统计层）。

背景（Stage 3 计划 T1a）:
  registry 冻结于 2026-09-24 06:25，Stage 1 A1 接线落于 2026-09-27（封存后 3 天）
  → 接线从未在生产运行过。143/143 旧裁决缺全部 18 个 A1 字段。

  本脚本验证 T1a 产出的**新裁决**是否确实携带 A1 字段。

判据 A（接线层，本阶段可达成）:
  限定为「经评估产出的、非 no-data 墓碑的」exploration 裁决:
  1. protocol_fingerprint / dir_acc_full / dir_acc_ex_roll / n_roll_excluded /
     n_roll_ratio / run_mode / covariates_used 均非空
  2. a1_missing_fields() 返回空列表
  3. run_mode == "exploration"（当前设计预期值，非 None）
  4. dm_status / pair_set_hash 有值（可为 no_common_cutoff，但不得为缺键）
  5. cov_fingerprint 可为 null（在 A1_NULLABLE 内，设计豁免）

判据 B'（统计层，依赖 PR-A1）:
  6. 至少 1 条裁决 pairing_valid=True 且 p_value 非 None
  7. dm_status 落入可配对状态（非 no_baseline / no_common_cutoff）

用法:
  .venv/bin/python scripts/verify_t1a_criteria_a.py
  .venv/bin/python scripts/verify_t1a_criteria_a.py --since 2026-09-28T11:49:00
  .venv/bin/python scripts/verify_t1a_criteria_a.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.registry_lib import (  # noqa: E402
    A1_NULLABLE,
    A1_REQUIRED_FIELDS,
    RUN_MODES,
    a1_missing_fields,
)

DEFAULT_REGISTRY = REPO_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"

# 判据 A 第 1 项：必须非空的字段子集
A1_MUST_BE_NON_NULL = (
    "protocol_fingerprint",
    "dir_acc_full",
    "dir_acc_ex_roll",
    "n_roll_excluded",
    "n_roll_ratio",
    "run_mode",
    "covariates_used",
)

# 判据 A 第 4 项：必须有值（不得缺键）
A1_MUST_BE_PRESENT = ("dm_status", "pair_set_hash")

# 判据 B' 第 7 项：可配对状态（排除不可配对者）
DM_NOT_PAIRABLE = frozenset({"no_baseline", "no_common_cutoff", "protocol_mismatch"})

# no-data 墓碑判定：这些是 _no_data_verdict 的合法 null，不算「经评估产出」
NO_DATA_MARKERS = frozenset({"no_data", "error"})


def load_verdicts(path: Path) -> list[dict]:
    """读取 registry（JSONL）。坏行 fail-loud。"""
    if not path.exists():
        raise FileNotFoundError(f"registry 不存在: {path}")
    out = []
    with path.open(encoding="utf-8") as fp:
        for lineno, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno} 非法 JSON: {e}") from e
    return out


def is_new_a1_verdict(v: dict, since: str | None) -> bool:
    """新裁决判定：A1 字段已接线（protocol_fingerprint 非空）。

    旧 registry（143 条）protocol_fingerprint 全为 None → 天然排除。
    since 提供时额外要求 decided_at >= since。
    """
    if v.get("protocol_fingerprint") is None:
        return False
    if since:
        decided = v.get("decided_at")
        if not isinstance(decided, str) or decided < since:
            return False
    return True


def is_no_data_tombstone(v: dict) -> bool:
    """no-data 墓碑（合法 null，不计入判据 A 分母）。"""
    status = str(v.get("status") or "").lower().strip()
    if status in NO_DATA_MARKERS:
        return True
    # 无 dir_acc 且无 n → 未产出评估
    if v.get("dir_acc") is None and v.get("n") in (None, 0):
        return True
    return False


def check_criteria_a(verdicts: list[dict]) -> dict:
    """判据 A：A1 字段确实被生产路径写入。"""
    failures: list[dict] = []
    for v in verdicts:
        vid = v.get("variant_id") or v.get("symbol") or "<unknown>"
        issues: list[str] = []

        # 1. 关键字段非空
        for k in A1_MUST_BE_NON_NULL:
            if v.get(k) is None:
                issues.append(f"{k} is None")

        # 2. a1_missing_fields 为空
        missing = a1_missing_fields(v)
        if missing:
            issues.append(f"a1_missing_fields={missing}")

        # 3. run_mode 为 exploration
        rm = v.get("run_mode")
        if rm not in RUN_MODES:
            issues.append(f"run_mode={rm!r} not in {sorted(RUN_MODES)}")
        elif rm != "exploration":
            issues.append(f"run_mode={rm!r} (expected 'exploration')")

        # 4. dm_status / pair_set_hash 有值
        for k in A1_MUST_BE_PRESENT:
            if k not in v:
                issues.append(f"{k} missing key")
            elif v.get(k) is None:
                issues.append(f"{k} is None")

        if issues:
            failures.append({"variant_id": vid, "issues": issues})

    passed = len(failures) == 0 and len(verdicts) > 0
    return {
        "criterion": "A",
        "name": "接线层 — A1 字段确被生产路径写入",
        "n_evaluated": len(verdicts),
        "n_failed": len(failures),
        "passed": passed,
        "failures": failures[:20],  # 截断展示
    }


def check_criteria_b_prime(verdicts: list[dict]) -> dict:
    """判据 B'：DM 配对在生产真实产出 p 值。"""
    pairable = [
        v for v in verdicts
        if v.get("dm_status") not in DM_NOT_PAIRABLE
    ]
    with_p = [
        v for v in pairable
        if v.get("pairing_valid") is True and v.get("p_value") is not None
    ]
    passed = len(with_p) >= 1
    return {
        "criterion": "B'",
        "name": "统计层 — DM 配对产出 p 值",
        "n_evaluated": len(verdicts),
        "n_pairable": len(pairable),
        "n_with_valid_p": len(with_p),
        "passed": passed,
        "examples": [
            {
                "variant_id": v.get("variant_id"),
                "dm_status": v.get("dm_status"),
                "p_value": v.get("p_value"),
                "dm_common_count": v.get("dm_common_count"),
            }
            for v in with_p[:5]
        ],
    }


def build_report(registry_path: Path, since: str | None) -> dict:
    all_verdicts = load_verdicts(registry_path)
    new_verdicts = [v for v in all_verdicts if is_new_a1_verdict(v, since)]
    evaluated = [v for v in new_verdicts if not is_no_data_tombstone(v)]
    tombstones = len(new_verdicts) - len(evaluated)

    report = {
        "registry": str(registry_path),
        "since": since,
        "n_total_in_registry": len(all_verdicts),
        "n_new_a1_verdicts": len(new_verdicts),
        "n_no_data_tombstones": tombstones,
        "n_evaluated": len(evaluated),
    }

    if not new_verdicts:
        report["status"] = "NO_NEW_VERDICTS"
        report["note"] = (
            "registry 中尚无 A1 完整的新裁决 —— T1a 的裁决流尚未产出。"
            "基线重生完成后需等待慢环产出首批裁决再复跑本脚本。"
        )
        return report

    report["criteria_a"] = check_criteria_a(evaluated)
    report["criteria_b_prime"] = check_criteria_b_prime(evaluated)
    report["status"] = (
        "PASS" if (report["criteria_a"]["passed"]
                   and report["criteria_b_prime"]["passed"])
        else "PARTIAL" if report["criteria_a"]["passed"]
        else "FAIL"
    )
    return report


def print_report(rep: dict) -> None:
    print("=" * 70)
    print("T1a 判据验证报告")
    print("=" * 70)
    print(f"registry            : {rep['registry']}")
    print(f"since               : {rep.get('since') or '(未限定)'}")
    print(f"registry 总条数      : {rep['n_total_in_registry']}")
    print(f"新 A1 裁决数         : {rep['n_new_a1_verdicts']}")
    print(f"其中 no-data 墓碑    : {rep['n_no_data_tombstones']}")
    print(f"进入判据的分母       : {rep['n_evaluated']}")
    print(f"总体状态             : {rep['status']}")
    print()

    if rep["status"] == "NO_NEW_VERDICTS":
        print(rep["note"])
        return

    for key in ("criteria_a", "criteria_b_prime"):
        c = rep[key]
        mark = "✅ PASS" if c["passed"] else "❌ FAIL"
        print(f"[判据 {c['criterion']}] {c['name']} — {mark}")
        for k, v in c.items():
            if k in ("criterion", "name", "passed", "failures", "examples"):
                continue
            print(f"    {k}: {v}")
        if c.get("failures"):
            print("    失败样例:")
            for f in c["failures"][:5]:
                print(f"      - {f['variant_id']}: {'; '.join(f['issues'])}")
        if c.get("examples"):
            print("    成功样例:")
            for e in c["examples"][:3]:
                print(f"      - {e}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description="T1a 判据 A / B' 验证")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--since", default=None,
                    help="仅统计 decided_at >= 该 ISO 时间戳的裁决（如 2026-09-28T11:49:00）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    rep = build_report(Path(args.registry), args.since)

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_report(rep)

    # 退出码：PASS=0 / PARTIAL=1 / FAIL=2 / NO_NEW_VERDICTS=3
    return {"PASS": 0, "PARTIAL": 1, "FAIL": 2, "NO_NEW_VERDICTS": 3}[rep["status"]]


if __name__ == "__main__":
    sys.exit(main())
