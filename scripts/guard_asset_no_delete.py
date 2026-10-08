#!/usr/bin/env python3
"""git 提交守卫：资产路径只许累加，不许删除。

用法：
    python scripts/guard_asset_no_delete.py              # 检查 git status
    git commit ... && python scripts/guard_asset_no_delete.py --after-commit

背景（2026-10-08）：
    本仓在「纯代码修改环境」使用（不产生资产）。那里执行 `git add -A` 会把
    「磁盘上不存在资产」误判成删除 —— 一次就产生 35 条 `D`，其中包含刚入库的
    433 条 aligned 裁决、34 个 nocov 基线、1642 行决策日志。若被提交，远端
    的备份资产即消失。

    主环境（跑三环那台）确实需要这些路径入库，故不能靠 .gitignore 规避
    （那会让主环境的资产不再入库）。守卫放在提交前，与环境无关。

口径与 BACKUP_SYNC_GUIDE.md / .gitignore 一致：这些路径入库、只增不删。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

# 资产路径规则（与 .gitignore 的入库口径同步）
ASSET_RULES = (
    r"^\.omc/supervisor_decisions\.jsonl$",
    r"^task_FM/config/aligned_verdicts\.jsonl$",
    r"^task_FM/config/baseline_metrics\.json$",
    r"^task_FM/config/baseline_points_.*\.jsonl$",
    r"^task_FM/config/archive/.*baseline_points_.*\.jsonl$",
)

# 已裁定为「过时基线、允许移除」的例外（2026-10-08 起暂空；
# 若将来确需删除过时资产，在此显式登记，不靠通配符放行）
DELETE_EXCEPTIONS: tuple[str, ...] = ()

# porcelain 两字符状态里，凡含 'D' 者即为删除/删除相关
# 只拦【已暂存】的删除 —— 那才是 git commit 会真正提交出去的东西。
# porcelain 两字符为 "XY"：X=索引状态，Y=工作区状态。
#   "D "（X 含 D）→ 已暂存删除，危险，必须拦
#   " D"（仅 Y 含 D）→ 仅本机磁盘上不存在，纯代码环境的常态，不拦
# 因此只读 X（line[:2] 的首字符）。
_INDEX_DELETED = "D"


def staged_changes() -> list[tuple[str, str]]:
    """返回 [(index_status, worktree_status, path)]，保留 XY 两字符原样。"""
    out = subprocess.run(["git", "status", "--porcelain"],
                         capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        xy, path = line[:2], line[3:]
        rows.append((xy[0], xy[1], path))
    return rows


def asset_deletions(rows: list[tuple[str, str, str]]) -> list[str]:
    """挑出【已暂存】的资产删除（索引列 X 含 D）。"""
    hits = []
    for x, y, path in rows:
        norm = path.replace("\\", "/")
        if not any(re.match(r, norm) for r in ASSET_RULES):
            continue
        if norm in DELETE_EXCEPTIONS:
            continue
        if _INDEX_DELETED in x:
            hits.append("%s%s  %s" % (x, y, path))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="资产路径删除守卫")
    ap.add_argument("--after-commit", action="store_true",
                    help="提交后模式：提示新提交里是否含资产删除")
    args = ap.parse_args()

    if args.after_commit:
        head = subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        parent = subprocess.run(["git", "rev-parse", "HEAD~1"],
                                capture_output=True, text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "diff", "--name-status", parent, head],
                              capture_output=True, text=True).stdout
        rows = []
        for line in diff.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            st, path = parts[0], parts[-1]
            # diff 的状态列首字符即删除标记（D/RD/UD...）
            rows.append((st[0] if st else "", st[1:] or "", path))
        hits = asset_deletions(rows)
        if hits:
            print("[GUARD] 新提交 %s 含资产删除：" % head[:8], file=sys.stderr)
            for h in hits:
                print("    " + h, file=sys.stderr)
            return 1
        print("[GUARD] 新提交 %s 无资产删除 ✓" % head[:8])
        return 0

    rows = staged_changes()
    hits = asset_deletions(rows)
    print("资产路径规则 %d 条；删除例外 %d 条"
          % (len(ASSET_RULES), len(DELETE_EXCEPTIONS)))
    if hits:
        print("\n[GUARD] 检测到资产删除（禁止提交）：", file=sys.stderr)
        for h in hits:
            print("    " + h, file=sys.stderr)
        print("\n纯代码环境执行 `git add -A` 会把「资产不在磁盘」误判为删除。\n"
              "处置：git restore --staged -- <路径>  （不动磁盘、不动远端）",
              file=sys.stderr)
        return 1
    print("无资产删除 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
