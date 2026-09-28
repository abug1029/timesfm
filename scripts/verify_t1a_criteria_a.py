#!/usr/bin/env python3
"""T1a 判据验证脚本 — 判据 A（接线层）+ 判据 B'（统计层）。

背景（Stage 3 计划 T1a）:
  registry 冻结于 2026-09-24 06:25，Stage 1 A1 接线落于 2026-09-27（封存后 3 天）
  → 接线从未在生产运行过。143/143 旧裁决缺全部 18 个 A1 字段。

判据 A（接线层）:
  1. protocol_fingerprint / dir_acc_full / dir_acc_ex_roll / n_roll_excluded /
     n_roll_ratio / run_mode / covariates_used 均非空
  2. a1_missing_fields() 返回空列表
  3. run_mode == "exploration"（当前设计预期值，非 None）
  4. dm_status / pair_set_hash **有键**（值可为 None —— 见下方 nullable 说明）
  5. cov_fingerprint 可为 null（在 A1_NULLABLE 内，设计豁免）

判据 B'（统计层）:
  6. 至少 1 条裁决 pairing_valid is True 且 p_value 为有限值
  7. dm_status 落入可配对状态

用法:
  .venv/bin/python scripts/verify_t1a_criteria_a.py
  .venv/bin/python scripts/verify_t1a_criteria_a.py --since 2026-09-28T11:49:00
  .venv/bin/python scripts/verify_t1a_criteria_a.py --json

退出码:
  0 PASS / 1 PARTIAL / 2 FAIL / 3 NO_NEW_VERDICTS / 4 A1_NOT_WIRED / 5 用法或内部错误

审计/复核修正记录（2026-09-28）:
  - HIGH-1: pair_set_hash 改为「键存在」判定。原稿判 `is None` 会对
    plan-legal 的 `no_common_cutoff` / `no_baseline` 裁决假 FAIL
    （`statistical_tests.py:350` 在非 ok 分支一律留 None；
    且 `registry_lib.A1_NULLABLE` 明确含该字段）。
  - HIGH-2: 判别器不再自指。新增**时间基**判别 + `A1_NOT_WIRED` 状态：
    若有「时间上属于新裁决」但缺 `protocol_fingerprint` 的记录，
    报告接线可能失效，而非静默报「仍在等待」。
  - MEDIUM: tombstone 改为 `status == "ok"` 白名单（原 denylist 漏 "timeout"）。
  - MEDIUM: 退出码区分崩溃/用法错误（原与 PARTIAL/FAIL 撞码）。
  - MEDIUM: `--since` 做 ISO 解析校验（原为字典序比较，格式不符会静默漏判）。
  - MEDIUM: 非 dict 的合法 JSON 行 fail-loud（原抛 AttributeError）。
  - LOW: p_value 需为有限浮点（原 NaN / bool 可通过）。
  - LOW: 报告逐条列出被排除的 tombstone variant_id。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.registry_lib import (  # noqa: E402
    A1_NULLABLE,
    RUN_MODES,
    a1_missing_fields,
)

DEFAULT_REGISTRY = REPO_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"

# 判据 A 第 1 项：必须**非空**的字段子集
A1_MUST_BE_NON_NULL = (
    "protocol_fingerprint",
    "dir_acc_full",
    "dir_acc_ex_roll",
    "n_roll_excluded",
    "n_roll_ratio",
    "run_mode",
    "covariates_used",
)

# 判据 A 第 4 项：必须**有键**（值可为 None，plan 原文「不得为缺键」）
# 复核 HIGH-1: pair_set_hash 在 A1_NULLABLE 内，且统计层在非 ok 分支留 None
A1_MUST_HAVE_KEY = ("dm_status", "pair_set_hash")

# 判据 B' 第 7 项：不可配对状态
DM_NOT_PAIRABLE = frozenset({"no_baseline", "no_common_cutoff", "protocol_mismatch"})

# 经评估产出：仅 status == "ok" 计入（白名单，替代原 denylist）
EVALUATED_STATUS = "ok"


class UsageError(Exception):
    """用法/输入错误（退出码 5，区别于判据 FAIL）。"""


def _parse_ts(s: str, label: str) -> datetime:
    """严格 ISO 解析（复核 MEDIUM-5）。

    原实现用字典序字符串比较：`decided_at="2026-09-28 12:00:00"` 与
    `--since "2026-09-28T11:49:00"` 相比会因空格 < 'T' 而漏判，
    静默落入 NO_NEW_VERDICTS。改为解析后比较，格式不符即报错。
    """
    try:
        return datetime.fromisoformat(s)
    except ValueError as e:
        raise UsageError(f"{label} 不是合法 ISO 时间戳: {s!r} ({e})") from e


def load_verdicts(path: Path) -> list[dict]:
    """读取 registry（JSONL）。坏行 fail-loud。

    复核 MEDIUM-6: 合法 JSON 但非对象的行（`null` / `123`）也必须 fail-loud，
    否则会以 AttributeError 的形式在远处崩溃。
    """
    if not path.exists():
        raise UsageError(f"registry 不存在: {path}")
    out: list[dict] = []
    with path.open(encoding="utf-8") as fp:
        for lineno, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno} 非法 JSON: {e}") from e
            if not isinstance(obj, dict):
                raise ValueError(
                    f"{path}:{lineno} 非 JSON 对象（{type(obj).__name__}）"
                )
            out.append(obj)
    return out


def _decided_at(v: dict) -> datetime | None:
    raw = v.get("decided_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def is_new_by_time(v: dict, since: datetime | None) -> bool:
    """时间基判别（复核 HIGH-2 新增）。

    与 protocol_fingerprint 判别**相互独立**：若时间上属于新裁决却缺指纹，
    说明接线可能失效 —— 必须报错而非静默等待。
    """
    if since is None:
        return False
    ts = _decided_at(v)
    return ts is not None and ts >= since


def is_new_a1_verdict(v: dict) -> bool:
    """指纹基判别：A1 字段已接线。"""
    return v.get("protocol_fingerprint") is not None


def is_evaluated(v: dict) -> bool:
    """经评估产出（白名单，复核 MEDIUM-3）。

    原 denylist {no_data, error} 漏掉 registry_lib 的 `timeout` tombstone
    （make_timeout_tombstone, status="timeout"），且从不检查 status，
    导致 `status="skipped"` 之类记录可凭 A1 字段混入判据 A 分母。
    """
    return str(v.get("status") or "").lower().strip() == EVALUATED_STATUS


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

        # 4. 键存在（值可为 None —— 复核 HIGH-1）
        for k in A1_MUST_HAVE_KEY:
            if k not in v:
                issues.append(f"{k} missing key")

        if issues:
            failures.append({"variant_id": vid, "issues": issues})

    passed = len(failures) == 0 and len(verdicts) > 0
    return {
        "criterion": "A",
        "name": "接线层 — A1 字段确被生产路径写入",
        "n_evaluated": len(verdicts),
        "n_failed": len(failures),
        "passed": passed,
        "failures": failures,
    }


def _valid_p(p) -> bool:
    """p_value 必须是有限浮点且在 [0,1]（复核 LOW-3）。

    原实现只判 `is not None`，NaN / True 均通过 —— NaN 不是「产出了 p 值」的证据。
    """
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        return False
    return math.isfinite(float(p)) and 0.0 <= float(p) <= 1.0


def check_criteria_b_prime(verdicts: list[dict]) -> dict:
    """判据 B'：DM 配对在生产真实产出 p 值。"""
    pairable = [v for v in verdicts if v.get("dm_status") not in DM_NOT_PAIRABLE]
    with_p = [
        v for v in pairable
        if v.get("pairing_valid") is True and _valid_p(v.get("p_value"))
    ]
    return {
        "criterion": "B'",
        "name": "统计层 — DM 配对产出 p 值",
        "n_evaluated": len(verdicts),
        "n_pairable": len(pairable),
        "n_with_valid_p": len(with_p),
        "passed": len(with_p) >= 1,
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


def build_report(registry_path: Path, since_raw: str | None) -> dict:
    since = _parse_ts(since_raw, "--since") if since_raw else None

    all_verdicts = load_verdicts(registry_path)
    by_fp = [v for v in all_verdicts if is_new_a1_verdict(v)]
    by_time = [v for v in all_verdicts if is_new_by_time(v, since)]

    # 复核 HIGH-2: 时间基说「新」但指纹缺失 → 接线可能失效，必须显式报出
    time_new_without_fp = [
        v for v in by_time if not is_new_a1_verdict(v)
    ]

    new_verdicts = by_fp
    evaluated = [v for v in new_verdicts if is_evaluated(v)]
    excluded = [v for v in new_verdicts if not is_evaluated(v)]

    report = {
        "registry": str(registry_path),
        "since": since_raw,
        "n_total_in_registry": len(all_verdicts),
        "n_new_a1_verdicts": len(new_verdicts),
        "n_excluded_not_evaluated": len(excluded),
        "excluded_variants": [
            {"variant_id": v.get("variant_id"), "status": v.get("status")}
            for v in excluded[:50]
        ],
        "n_evaluated": len(evaluated),
        "time_based_new_count": len(by_time),
        "time_new_without_fingerprint": len(time_new_without_fp),
    }

    # 复核 HIGH-2: 接线失效优先于「仍在等待」
    if time_new_without_fp and not by_fp:
        report["status"] = "A1_NOT_WIRED"
        report["note"] = (
            f"检测到 {len(time_new_without_fp)} 条 decided_at >= since 的裁决，"
            "但**全部缺 protocol_fingerprint** —— 这不是「尚未产出」，"
            "而是**A1 接线可能失效**。请检查 build_summary 是否仍写入该字段。"
        )
        report["suspects"] = [
            {"variant_id": v.get("variant_id"), "decided_at": v.get("decided_at")}
            for v in time_new_without_fp[:20]
        ]
        return report

    if not new_verdicts:
        report["status"] = "NO_NEW_VERDICTS"
        report["note"] = (
            "registry 中尚无 A1 完整的新裁决 —— T1a 的裁决流尚未产出。"
            "基线重生完成后需等待慢环产出首批裁决再复跑本脚本。"
            + ("（时间基判别亦无命中，故非接线失效）" if since else
               "（未提供 --since，无法做时间基交叉校验）")
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
    print(f"时间基新裁决数       : {rep['time_based_new_count']}")
    print(f"  其中缺指纹         : {rep['time_new_without_fingerprint']}")
    print(f"非 ok 被排除         : {rep['n_excluded_not_evaluated']}")
    print(f"进入判据的分母       : {rep['n_evaluated']}")
    print(f"总体状态             : {rep['status']}")
    print()

    if rep["status"] in ("NO_NEW_VERDICTS", "A1_NOT_WIRED"):
        print(rep["note"])
        for s in rep.get("suspects", [])[:5]:
            print(f"  - {s}")
        return

    if rep.get("excluded_variants"):
        print("被排除的非 ok 记录:")
        for e in rep["excluded_variants"][:5]:
            print(f"  - {e['variant_id']} (status={e['status']})")
        print()

    for key in ("criteria_a", "criteria_b_prime"):
        c = rep[key]
        mark = "✅ PASS" if c["passed"] else "❌ FAIL"
        print(f"[判据 {c['criterion']}] {c['name']} — {mark}")
        for k, val in c.items():
            if k in ("criterion", "name", "passed", "failures", "examples"):
                continue
            print(f"    {k}: {val}")
        if c.get("failures"):
            print("    失败样例:")
            for f in c["failures"][:5]:
                print(f"      - {f['variant_id']}: {'; '.join(f['issues'])}")
        if c.get("examples"):
            print("    成功样例:")
            for e in c["examples"][:3]:
                print(f"      - {e}")
        print()


EXIT_CODES = {
    "PASS": 0,
    "PARTIAL": 1,
    "FAIL": 2,
    "NO_NEW_VERDICTS": 3,
    "A1_NOT_WIRED": 4,
    "USAGE_ERROR": 5,
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="T1a 判据 A / B' 验证",
        exit_on_error=False,
    )
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--since", default=None,
                    help="仅统计 decided_at >= 该 ISO 时间戳的裁决（如 2026-09-28T11:49:00）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    try:
        args = ap.parse_args()
    except SystemExit as e:                      # argparse 在部分版本仍会退出
        print(f"用法错误（退出码 {EXIT_CODES['USAGE_ERROR']}）", file=sys.stderr)
        return EXIT_CODES["USAGE_ERROR"]

    try:
        rep = build_report(Path(args.registry), args.since)
    except UsageError as e:
        print(f"用法/输入错误: {e}", file=sys.stderr)
        return EXIT_CODES["USAGE_ERROR"]
    except ValueError as e:
        print(f"数据错误: {e}", file=sys.stderr)
        return EXIT_CODES["USAGE_ERROR"]

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_report(rep)

    return EXIT_CODES[rep["status"]]


if __name__ == "__main__":
    sys.exit(main())
