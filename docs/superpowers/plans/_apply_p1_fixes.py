#!/usr/bin/env python3
"""Apply P1-A/B/C/D fixes to the Phase 1 plan document."""
import sys

PLAN_PATH = "/home/abug/timesfm/docs/superpowers/plans/2026-10-18-proposal-lifecycle-phase1.md"

with open(PLAN_PATH, "r") as f:
    content = f.read()

# Fix 1: Header update
content = content.replace(
    "> **修订状态**：2026-10-18 根据审核  修订（P0-1..4 已修复 + P1-5..12 已修复 + P2-13..16 已标注）。",
    "> **修订状态**：2026-10-18 根据二审修订，已通过（P0-1..4 已修复 + P1-5..12 已修复 + P2-13..16 已标注；P1-A/B/C/D 残留已收进 Task 5/7/8 正文）。"
)

# Fix 2: Add "unknown sentinel" constraint
old_line = """- **proposal_id 来源**：lifecycle 统一使用 **proposal JSON 内的  字段**；缺失时策略为 （不 fallback 到 search_proposal_id 路径名，两者文档分隔）"""
new_line = old_line + """
- **入队行禁止  哨兵**： 缺失的提案在 schema 通过后、质量门前即被拒收，不会进入 """
content = content.replace(old_line, new_line)

with open(PLAN_PATH, "w") as f:
    f.write(content)

print(f"Fixes 1-2 applied. File size: {len(content)} chars")
