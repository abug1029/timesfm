#!/usr/bin/env python3
"""清除重复提案文件，保留每个 variant_id 的最新版本"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def scan_proposals(experiments_dir: Path) -> list[dict]:
    """扫描所有提案文件"""
    proposals = []

    # 扫描活跃和归档的实验目录
    for pattern in ["run_*/results/gen_*/gen*_peer*/proposals/*.json",
                    "archive/run_*/results/gen_*/gen*_peer*/proposals/*.json"]:
        for path in experiments_dir.glob(pattern):
            # 跳过 prescreen 文件
            if path.name.endswith(".prescreen.json"):
                continue

            try:
                data = json.loads(path.read_text())
                symbol = data.get("symbol")
                cov_override = data.get("cov_override")

                if not symbol or not cov_override:
                    continue

                variant_id = f"{symbol}_{cov_override}"

                proposals.append({
                    "variant_id": variant_id,
                    "symbol": symbol,
                    "cov_override": cov_override,
                    "file_path": str(path),
                    "mtime": path.stat().st_mtime,
                    "size": path.stat().st_size
                })
            except (json.JSONDecodeError, KeyError, OSError) as e:
                print(f"Warning: skipping {path}: {e}", file=sys.stderr)
                continue

    return proposals

def deduplicate_proposals(proposals: list[dict]) -> tuple[list[dict], list[dict]]:
    """去重，返回 (保留的, 待删除的)"""
    grouped = defaultdict(list)

    for prop in proposals:
        grouped[prop["variant_id"]].append(prop)

    keep = []
    delete = []

    for variant_id, props in grouped.items():
        # 按 mtime 排序，保留最新的
        props.sort(key=lambda p: p["mtime"], reverse=True)
        keep.append(props[0])
        delete.extend(props[1:])

    return keep, delete

def main():
    experiments_dir = Path("task_FM/experiments")

    if not experiments_dir.exists():
        print(f"Error: {experiments_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    print("Scanning proposals...")
    proposals = scan_proposals(experiments_dir)
    print(f"Found {len(proposals)} proposal files")

    print("\nDeduplicating...")
    keep, delete = deduplicate_proposals(proposals)

    print(f"\nStatistics:")
    print(f"  Unique proposals (keep): {len(keep)}")
    print(f"  Duplicates (delete): {len(delete)}")
    print(f"  Space to free: {sum(p['size'] for p in delete) / 1024 / 1024:.2f} MB")

    if not delete:
        print("\nNo duplicates found.")
        return

    # 确认删除
    print(f"\nAbout to delete {len(delete)} duplicate files.")
    response = input("Continue? (yes/no): ")

    if response.lower() != "yes":
        print("Aborted.")
        return

    # 执行删除
    deleted = 0
    failed = 0

    for prop in delete:
        try:
            Path(prop["file_path"]).unlink()
            deleted += 1
        except OSError as e:
            print(f"Error deleting {prop['file_path']}: {e}", file=sys.stderr)
            failed += 1

    print(f"\nDeleted {deleted} files, failed {failed} files.")
    print(f"Freed {sum(p['size'] for p in delete[:deleted]) / 1024 / 1024:.2f} MB")

    # 生成报告
    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_files": len(proposals),
        "unique_proposals": len(keep),
        "duplicates_deleted": deleted,
        "duplicates_failed": failed,
        "space_freed_mb": sum(p["size"] for p in delete[:deleted]) / 1024 / 1024
    }

    report_path = Path("docs/proposal_dedup_report.json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved to {report_path}")

if __name__ == "__main__":
    main()
