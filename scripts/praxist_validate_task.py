#!/usr/bin/env python3
"""PRAXIST 任务包契约校验器 (P0a, 2026-09-01)

用法: python scripts/praxist_validate_task.py [contract.yaml]
默认校验 config/praxist_task.yaml。exit 0=通过, 2=违规。
红线: peers 可写区仅限 scripts/praxist_ws 与 reports/praxist。
"""
import os
import sys

import yaml

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_WRITE_PATHS = {"scripts/praxist_ws", "reports/praxist"}
ALLOWED_MC = {"bonferroni", "holm", "benjamini-hochberg"}


def validate(path):
    errors = []
    with open(path, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f)
    if not isinstance(d, dict) or not d:
        return ["contract: 必须是非空映射"]

    obj = d.get("objective") or {}
    if obj.get("primary") != "ev_after_slippage":
        errors.append("objective.primary 必须是 ev_after_slippage (预注册经济口径)")
    if obj.get("secondary") != "profit_factor":
        errors.append("objective.secondary 必须是 profit_factor")
    if obj.get("green_requires_full_walkforward") is not True:
        errors.append("green_requires_full_walkforward 必须为 true (B1 教训)")

    c = d.get("constraints") or {}
    if not (isinstance(c.get("min_samples"), int) and c["min_samples"] >= 350):
        errors.append("constraints.min_samples 必须 >= 350")
    if not (isinstance(c.get("min_ic"), (int, float)) and c["min_ic"] >= 0.05):
        errors.append("constraints.min_ic 必须 >= 0.05")
    if c.get("multiple_comparison") not in ALLOWED_MC:
        errors.append(f"constraints.multiple_comparison 必须是 {sorted(ALLOWED_MC)} 之一")
    if c.get("maxdd_caliber") != "cumprod_clamp":
        errors.append("constraints.maxdd_caliber 必须是 cumprod_clamp")

    wp = d.get("write_paths") or []
    if not set(wp) <= ALLOWED_WRITE_PATHS:
        errors.append(f"write_paths 越红线: {set(wp) - ALLOWED_WRITE_PATHS}")

    stages = {s.get("stage"): s for s in (d.get("evidence_maturity") or [])}
    if "diagnostic" not in stages or "full_walkforward" not in stages:
        errors.append("evidence_maturity 必须含 diagnostic 与 full_walkforward 两级")
    elif not stages["full_walkforward"].get("gate"):
        errors.append("full_walkforward 阶段必须有硬门 (gate 非空)")

    if d.get("generation_close_policy") != "sealed":
        errors.append("generation_close_policy 必须是 sealed")

    return errors


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(FM_ROOT, "config", "praxist_task.yaml")
    errors = validate(path)
    if errors:
        print("CONTRACT VIOLATIONS:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(2)
    print(f"OK: {path} 契约合规 (预注册口径 + 红线可写区 + 证据成熟度门)")


if __name__ == "__main__":
    main()
