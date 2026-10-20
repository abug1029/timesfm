#!/usr/bin/env python3
"""批量提案验证 CLI。

Usage:
    python scripts/validate_all_proposals.py --all
    python scripts/validate_all_proposals.py --run run_2026-10-20_12-00-00
    python scripts/validate_all_proposals.py --report output.md
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from proposal_validator import validate_proposal


def scan_proposals(root, run_filter=None):
    """扫描提案文件，返回路径列表。"""
    pattern = os.path.join(root, "task_FM", "experiments", "run_*",
                           "results", "**", "proposals", "*.json")
    all_files = glob.glob(pattern, recursive=True)
    if run_filter:
        all_files = [f for f in all_files if run_filter in f]
    return sorted(all_files)


def validate_all(files):
    """批量验证，返回结果列表。"""
    results = []
    for fp in files:
        r = validate_proposal(fp)
        r["path"] = fp
        results.append(r)
    return results


def generate_report(results, output_path):
    """生成 Markdown 报告。"""
    total = len(results)
    valid = sum(1 for r in results if r["valid"])
    invalid = total - valid

    error_counter = Counter()
    chinese_fields = Counter()
    for r in results:
        if not r["valid"]:
            for e in r["errors"]:
                kind = e.split(":")[0]
                error_counter[kind] += 1
                if kind == "chinese_field":
                    field = e.split(":")[1]
                    chinese_fields[field] += 1

    lines = [
        "# 提案验证报告",
        "",
        "- **总计**: %d" % total,
        "- **有效**: %d" % valid,
        "- **无效**: %d" % invalid,
    ]
    if total:
        lines.append("- **有效率**: %.1f%%" % (valid / total * 100))
    else:
        lines.append("- **有效率**: N/A")

    lines.extend([
        "",
        "## 错误类型分布",
        "",
    ])
    for kind, count in error_counter.most_common():
        lines.append("- `%s`: %d" % (kind, count))

    if chinese_fields:
        lines.extend([
            "",
            "## 中文字段统计",
            "",
        ])
        for field, count in chinese_fields.most_common():
            lines.append("- `%s`: %d 条" % (field, count))

    lines.extend([
        "",
        "## 无效提案列表",
        "",
    ])
    for r in results:
        if not r["valid"]:
            rel = os.path.relpath(r["path"])
            lines.append("- `%s`: %s" % (rel, r["errors"]))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Report written to: " + output_path)


def main():
    parser = argparse.ArgumentParser(description="Batch proposal validation")
    parser.add_argument("--all", action="store_true", help="Validate all proposals")
    parser.add_argument("--run", type=str, help="Validate specific run (substring match)")
    parser.add_argument("--report", type=str, help="Output report path")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if not args.all and not args.run and not args.report:
        parser.print_help()
        sys.exit(1)

    root = _repo_root
    files = scan_proposals(root, run_filter=args.run)
    if not files:
        print("No proposal files found")
        sys.exit(0)

    print("Found %d proposal files" % len(files))
    results = validate_all(files)

    valid = sum(1 for r in results if r["valid"])
    invalid = len(results) - valid

    if args.json:
        print(json.dumps({
            "total": len(results),
            "valid": valid,
            "invalid": invalid,
            "details": results,
        }, ensure_ascii=False, indent=2))
    else:
        print("Valid: %d, Invalid: %d" % (valid, invalid))
        if invalid:
            print("\nInvalid proposals:")
            for r in results:
                if not r["valid"]:
                    print("  %s: %s" % (os.path.relpath(r["path"]), r["errors"]))

    if args.report:
        generate_report(results, args.report)

    sys.exit(0 if invalid == 0 else 1)


if __name__ == "__main__":
    main()
