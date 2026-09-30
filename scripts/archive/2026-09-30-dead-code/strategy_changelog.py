#!/usr/bin/env python3
"""
策略变更日志 — FM_a 期货版

从 git 历史生成变更记录。完全市场无关，纯 git log 解析。

用法:
  python scripts/strategy_changelog.py              # 最近 7 天
  python scripts/strategy_changelog.py --days 30    # 最近 30 天
  python scripts/strategy_changelog.py --json       # JSON 输出

输出:
  Markdown 报告到 stdout 和 reports/strategy_changelog.md
  JSON 摘要到 stderr
"""

import sys
import json

# Windows UTF-8 输出修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import argparse

REPO_ROOT = Path(__file__).resolve().parent.parent

# 文件路径 → 分类映射
CATEGORY_MAP = [
    ("cascade/",  "模型变更"),
    ("config/",   "配置变更"),
    ("data/",     "数据管线"),
    ("scripts/",  "工具变更"),
]

# 不在以上目录中的根目录文件归为 "项目配置"
ROOT_CATEGORY = "项目配置"


def categorize_file(filepath: str) -> str:
    """根据文件路径判断所属分类."""
    for prefix, category in CATEGORY_MAP:
        if filepath.startswith(prefix):
            return category
    if "/" not in filepath:
        return ROOT_CATEGORY
    return ROOT_CATEGORY


def run_git(*args: str) -> str | None:
    """执行 git 命令，返回 stdout 或 None（失败时）."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode != 0:
            print(f"git 错误: {' '.join(args)}\n{result.stderr.strip()}", file=sys.stderr)
            return None
        return result.stdout
    except FileNotFoundError:
        print("错误: 未找到 git，请确认已安装 git 并在仓库目录下运行。", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"git 命令超时: {' '.join(args)}", file=sys.stderr)
        return None


def check_git_repo() -> bool:
    """检查当前目录是否为 git 仓库."""
    result = run_git("rev-parse", "--git-dir")
    return result is not None


def get_commits(days: int) -> list[dict]:
    """获取指定天数内的所有 commit."""
    # M5 fix: 空仓库直接返回，避免 git log 输出 stderr 噪音
    count_result = run_git("rev-list", "--count", "HEAD")
    if count_result is None or count_result.strip() == "0":
        return []

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    log_format = "%H%x00%h%x00%ai%x00%s%x00%b"
    raw = run_git(
        "log",
        f"--since={since}",
        f"--pretty=format:{log_format}",
        "--name-only",
        "--no-merges",
    )
    if raw is None:
        return []

    commits = []
    blocks = raw.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines or not lines[0].strip():
            continue

        meta_parts = lines[0].split("\x00")
        if len(meta_parts) < 4:
            continue

        commit_hash = meta_parts[0].strip()
        short_hash = meta_parts[1].strip()
        date_str = meta_parts[2].strip()[:10]
        subject = meta_parts[3].strip()

        files = [f.strip() for f in lines[1:] if f.strip()]

        commits.append({
            "hash": commit_hash,
            "short_hash": short_hash,
            "date": date_str,
            "subject": subject,
            "files": files,
        })

    return commits


def build_changelog(commits: list[dict]) -> dict[str, list[dict]]:
    """将 commits 按分类整理."""
    categorized = defaultdict(list)

    for commit in commits:
        commit_categories = set()
        for f in commit["files"]:
            commit_categories.add(categorize_file(f))

        for cat in commit_categories:
            cat_files = [
                f for f in commit["files"]
                if categorize_file(f) == cat
            ]
            categorized[cat].append({
                "date": commit["date"],
                "short_hash": commit["short_hash"],
                "subject": commit["subject"],
                "files": cat_files,
            })

    return dict(categorized)


def render_markdown(changelog: dict, since: str, until: str) -> str:
    """渲染 Markdown 报告."""
    lines = [
        f"# 策略变更日志 ({since} ~ {until})",
        "",
    ]

    category_order = ["模型变更", "配置变更", "数据管线", "工具变更", "项目配置"]

    has_any = False
    for cat in category_order:
        entries = changelog.get(cat)
        if not entries:
            continue
        has_any = True

        lines.append(f"## {cat}")
        for entry in entries:
            files_str = ", ".join(entry["files"][:3])
            if len(entry["files"]) > 3:
                files_str += f" 等 {len(entry['files'])} 个文件"
            lines.append(
                f"- [{entry['date']}] {entry['short_hash']}: "
                f"{entry['subject']} ({files_str})"
            )
        lines.append("")

    if not has_any:
        lines.append(f"_{since} ~ {until} 期间无相关变更。_")
        lines.append("")

    return "\n".join(lines)


def render_json(changelog: dict, since: str, until: str, days: int) -> str:
    """渲染 JSON 摘要."""
    summary = {
        "since": since,
        "until": until,
        "days": days,
        "categories": {},
    }
    for cat, entries in changelog.items():
        summary["categories"][cat] = {
            "count": len(entries),
            "entries": [
                {
                    "date": e["date"],
                    "hash": e["short_hash"],
                    "subject": e["subject"],
                    "files": e["files"],
                }
                for e in entries
            ],
        }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def write_report(content: str, output_path: Path):
    """写入报告文件，自动创建目录."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="从 git 历史生成策略变更日志")
    parser.add_argument("--days", type=int, default=7, help="回溯天数 (默认 7)")
    parser.add_argument(
        "--output",
        type=str,
        default="reports/strategy_changelog.md",
        help="输出文件路径 (默认 reports/strategy_changelog.md)",
    )
    parser.add_argument("--json", action="store_true", help="仅输出 JSON 到 stdout")
    args = parser.parse_args()

    if not check_git_repo():
        print("错误: 当前目录不是 git 仓库，或 git 不可用。", file=sys.stderr)
        sys.exit(1)

    since_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    until_date = datetime.now().strftime("%Y-%m-%d")

    commits = get_commits(args.days)
    changelog = build_changelog(commits)

    if args.json:
        json_output = render_json(changelog, since_date, until_date, args.days)
        print(json_output)
        return

    md_content = render_markdown(changelog, since_date, until_date)
    print(md_content)

    output_path = REPO_ROOT / args.output
    write_report(md_content, output_path)
    print(f"报告已写入: {output_path}", file=sys.stderr)

    json_summary = render_json(changelog, since_date, until_date, args.days)
    print(f"\nJSON 摘要:\n{json_summary}", file=sys.stderr)


if __name__ == "__main__":
    main()
