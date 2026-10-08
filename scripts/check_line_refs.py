#!/usr/bin/env python3
"""行号引用闸门（技术债 D1 防回归，2026-10-08）。

背景：`docs/superpowers/reports/2026-10-07-tech-debt-inventory.md` D1 条目；
专项审计 `docs/superpowers/reports/2026-10-08-d1-line-reference-audit.md` 实测
现行契约文档 30 处行号引用 25 处已错（正确率 13%），且同一事实跨文档行号互相
矛盾。行号引用与文档同步靠人记，必然腐烂，故改为机器闸门。

两项检查：

1. **living（硬失败）**：现行契约/agent 文档禁止代码行号引用
   （`xxx.py:NN` / 裸 `` `:NN` `` / 跨文档 `xxx.md:NN`）。
   改法：只写符号（`_dead_families()`）或文件（`scripts/praxist_supervisor.py`）；
   文档内部互引用章节锚点。行号是冗余信息，删掉即零维护。

2. **dated（硬失败）**：日期型报告/计划/spec/changelog 若含行号引用，
   必须带 `代码基线` 头（短 commit），使历史行号永远可复核：
   `git show <sha>:<path> | sed -n 'NNp'`。
   历史证据不改行号（改=篡改证据），改用 commit 钉住。

用法：
    python3 scripts/check_line_refs.py            # 两项检查，违规退出码 1
    python3 scripts/check_line_refs.py --scope    # 打印检查范围与计数
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# ---- 三类行号引用（含裸行号承接上文文件的形态） ----
PATTERNS: dict[str, re.Pattern[str]] = {
    "code-line": re.compile(r"(?<![\w./])[A-Za-z0-9_][\w/-]*\.py:\d+(?:-\d+)?"),
    "bare-line": re.compile(r"`:\d+(?:-\d+)?`"),
    "doc-line": re.compile(r"(?<![\w./])[A-Za-z0-9_][\w/-]*\.md:\d+(?:-\d+)?"),
}

DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")
BASELINE_MARKER = "代码基线"

# 日期型根目录（行号按 commit 钉住，不改行号）
DATED_DIRS = (
    "docs/superpowers/reports",
    "docs/superpowers/plans",
    "docs/superpowers/specs",
    "docs/superpowers/changelogs",
    "docs/superpowers/reviews",
    "docs/research",
)


def _living_files() -> list[Path]:
    """现行契约/agent 文档：禁止一切行号引用。"""
    out: list[Path] = []
    out += sorted(REPO.glob("*.md"))                                   # 根目录契约
    out += sorted(REPO.glob("docs/*.md"))                              # docs 顶层
    out += sorted(REPO.glob("task_FM/*.md"))
    out += sorted(REPO.glob("task_FM/*.jinja2"))                       # peer 提示词
    out += sorted((REPO / "task_FM" / "roles").rglob("*.md"))
    for d in ("cascade", "scripts", "tests", "config", "data", "docs"):
        p = REPO / d / "AGENTS.md"
        if p.is_file():
            out.append(p)
    # 日期型 spec 是历史证据，属 dated 处置（钉 commit），不在本类
    return [p for p in out if not DATE_PREFIX.match(p.name)]


def _dated_files() -> list[Path]:
    """日期型文档：含行号引用则必须声明代码基线。"""
    out: list[Path] = []
    for d in DATED_DIRS:
        base = REPO / d
        if base.is_dir():
            out += sorted(base.rglob("*.md"))
    out += [p for p in sorted(REPO.glob("docs/*.md")) if DATE_PREFIX.match(p.name)]
    # docs/archive/ 是冻结区，不在任何检查范围
    return [p for p in out if "archive" not in p.parts]


def _violations(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(REPO)
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, pat in PATTERNS.items():
                for m in pat.finditer(line):
                    hits.append(f"{rel}:{lineno} [{kind}] {m.group(0)}")
    return hits


def _missing_baseline(paths: list[Path]) -> list[str]:
    out: list[str] = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(pat.search(text) for pat in PATTERNS.values()):
            continue  # 无行号引用的日期型文档无需基线
        if BASELINE_MARKER in text:
            continue
        out.append(str(p.relative_to(REPO)))
    return out


def main(argv: list[str]) -> int:
    living = _living_files()
    dated = _dated_files()

    if "--scope" in argv:
        print(f"living: {len(living)} files")
        for p in living:
            print("  ", p.relative_to(REPO))
        print(f"dated: {len(dated)} files")
        for p in dated:
            print("  ", p.relative_to(REPO))
        return 0

    rc = 0
    v1 = _violations(living)
    if v1:
        rc = 1
        print(f"[FAIL] living 文档含行号引用（{len(v1)} 处）——删行号改符号/章节锚点：")
        for h in v1:
            print("   ", h)
    else:
        print(f"[OK] living 文档行号引用清零（{len(living)} 文件）")

    v2 = _missing_baseline(dated)
    if v2:
        rc = 1
        print(f"[FAIL] 日期型文档含行号引用但缺 `代码基线` 头（{len(v2)} 份）：")
        for h in v2:
            print("   ", h)
        print("   修法：标题下加一行 > **代码基线**: `<git log -1 --format=%h -- 该文件>`")
    else:
        n = sum(1 for p in dated if BASELINE_MARKER in p.read_text(encoding="utf-8", errors="replace"))
        print(f"[OK] dated 文档基线齐备（{len(dated)} 文件，其中 {n} 份声明基线）")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
