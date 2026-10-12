"""AST 闸门：禁止裸 DELETE FROM kline（无 dt/date 限定条件）。

背景：2026-07-15 Lesson #11 记录 "DELETE 全表 + INSERT 模式在数据采集场景都是定时炸弹"。
collect_1h.py 已修复为 INSERT OR REPLACE + MIN_1H_ROWS 保护（增量安全）。
但 daily_update.py 的 collect_1h_main_only() 和 pull_history_1h.py 仍保留全量 DELETE。

本测试检测所有 scripts/*.py 中的 DELETE FROM kline 语句：
- 必须带 dt > 或 date > 限定条件（防御性清理未来 bar）
- 或带 # ALLOWED: <原因> 注释豁免（如 pull_history_1h.py 显式标注为初始化专用）

参考：tests/test_no_dead_code.py 的 AST 闸门设计。

历史教训：
- 2026-07-15 Lesson #11: DELETE-then-INSERT 是定时炸弹
- 2026-09-30 死代码审核第 6 次同型错误（漏检裸文件名子进程调用）
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO / "scripts"

# 允许豁免的文件（必须显式标注 # ALLOWED: <原因>）
ALLOWED_FILES = {
    # pull_history_1h.py 设计为初始化/灾难恢复专用，全量 DELETE 是其职责
    # 但必须带 # ALLOWED 注释 + MIN_ROWS 保护
    "pull_history_1h.py",
    # data_audit.py 是只读审计脚本，DELETE 语句在 f-string 中仅用于日志/报告，不实际执行
    "data_audit.py",
}


def _extract_delete_statements(source: str, filename: str) -> list[dict]:
    """Extract DELETE FROM kline statements from Python source.

    Returns list of dicts with keys:
    - line: line number
    - col: column offset
    - sql: SQL string (if literal)
    - has_dt_filter: whether DELETE has dt > or date > filter
    - has_allowed_comment: whether line has # ALLOWED: comment
    """
    deletes = []
    lines = source.split('\n')

    for i, line in enumerate(lines, 1):
        # 检测 DELETE FROM kline 模式（字符串字面量）
        if re.search(r'DELETE\s+FROM\s+kline', line, re.IGNORECASE):
            # 检查是否有 dt > 或 date > 限定
            has_dt_filter = bool(re.search(r'(dt|date)\s*>', line, re.IGNORECASE))
            # 检查是否有 # ALLOWED: 注释
            # 检查当前行或上 1-2 行是否有 # ALLOWED: 注释
            has_allowed_comment = bool(re.search(r'#\s*ALLOWED:', line))
            if not has_allowed_comment and i > 1:
                # 检查上 1 行
                prev_line = lines[i - 2]  # 0-indexed
                has_allowed_comment = bool(re.search(r'#\s*ALLOWED:', prev_line))
            if not has_allowed_comment and i > 2:
                # 检查上 2 行（允许 DELETE 语句跨多行的情况）
                prev2_line = lines[i - 3]
                has_allowed_comment = bool(re.search(r'#\s*ALLOWED:', prev2_line))

            deletes.append({
                'line': i,
                'col': 0,
                'sql': line.strip(),
                'has_dt_filter': has_dt_filter,
                'has_allowed_comment': has_allowed_comment,
                'filename': filename,
            })

    return deletes


def test_no_bare_delete_from_kline():
    """所有 scripts/*.py 中的 DELETE FROM kline 必须带 dt/date 限定或 # ALLOWED 注释。

    违反此测试的代码会在 TqSdk 网络异常时摧毁全部历史数据（Lesson #11 定时炸弹）。
    """
    violations = []

    for py_file in SCRIPTS_DIR.glob("*.py"):
        if py_file.name in ALLOWED_FILES:
            # 豁免文件仍需检查是否有 # ALLOWED 注释
            source = py_file.read_text(encoding='utf-8')
            deletes = _extract_delete_statements(source, py_file.name)
            for d in deletes:
                if not d['has_allowed_comment']:
                    violations.append(
                        f"{py_file.name}:{d['line']}: DELETE FROM kline without # ALLOWED comment\n"
                        f"  {d['sql']}\n"
                        f"  豁免文件必须显式标注 # ALLOWED: <原因>"
                    )
            continue

        source = py_file.read_text(encoding='utf-8')
        deletes = _extract_delete_statements(source, py_file.name)

        for d in deletes:
            # 必须有 dt/date 限定 或 # ALLOWED 注释
            if not (d['has_dt_filter'] or d['has_allowed_comment']):
                violations.append(
                    f"{py_file.name}:{d['line']}: bare DELETE FROM kline (no dt/date filter, no # ALLOWED)\n"
                    f"  {d['sql']}\n"
                    f"  这会摧毁全部历史数据（Lesson #11 定时炸弹）。\n"
                    f"  修复：加 AND dt > ? 限定（防御性清理未来 bar）\n"
                    f"  或加 # ALLOWED: <原因> 注释（如 pull_history_1h.py 初始化专用）"
                )

    if violations:
        msg = "发现裸 DELETE FROM kline 语句（无 dt/date 限定，无 # ALLOWED 注释）：\n\n"
        msg += "\n\n".join(violations)
        msg += "\n\n参考：2026-07-15 Lesson #11 'DELETE 全表 + INSERT 是定时炸弹'"
        raise AssertionError(msg)


def test_collect_1h_main_only_is_incremental():
    """daily_update.py 的 collect_1h_main_only() 必须用增量模式（INSERT OR REPLACE + MIN_ROWS）。

    断言：不包含裸 DELETE FROM kline_1h WHERE contract_code = ?（无 dt 限定）。
    """
    daily_update = SCRIPTS_DIR / "daily_update.py"
    source = daily_update.read_text(encoding='utf-8')

    # 查找 collect_1h_main_only 函数
    match = re.search(
        r'def collect_1h_main_only\([^)]+\):.*?(?=\ndef |\Z)',
        source,
        re.DOTALL
    )
    assert match, "collect_1h_main_only 函数未找到"

    func_body = match.group(0)

    # 检查是否有裸 DELETE（无 dt 限定）
    # Fix: check for (dt|date) with >=? operators
    bare_delete = re.search(
        r"DELETE\s+FROM\s+kline_1h\s+WHERE\s+contract_code\s*=\s*\?"
        r"(?!\s+AND\s+(dt|date)\s*>=?)",
        func_body,
        re.IGNORECASE
    )

    if bare_delete is not None:
        msg = (
            f"collect_1h_main_only() 包含裸 DELETE: {bare_delete.group(0)}\n"
            f"  位置: daily_update.py (函数体内)\n"
            f"  问题: 这会摧毁全部历史数据（Lesson #11 定时炸弹）\n"
            f"  修复: 对齐 collect_1h.py 的增量模式\n"
            f"    1. 用 INSERT OR REPLACE（store_klines_1h 内部已支持）\n"
            f"    2. 加 MIN_1H_ROWS 保护（防 TqSdk 网络异常返回部分数据）\n"
            f"    3. DELETE 仅用于防御性清理未来 bar（AND dt > new_max）"
        )
        raise AssertionError(msg)


def test_data_management_no_pull_history():
    """data_management.py 的 collect_1h() 不应调用 pull_history_1h.py。

    pull_history_1h.py 是全量 DELETE+INSERT，会覆盖 collect_1h.py 的增量修复。
    仅用于初始化/灾难恢复，不应被日常流程调度。
    """
    data_mgmt = SCRIPTS_DIR / "data_management.py"
    source = data_mgmt.read_text(encoding='utf-8')

    # 查找 collect_1h 函数
    # Fix: allow return type annotation `) -> list[dict]:`
    match = re.search(
        r'def collect_1h\(.*?\n(?:.*?\n)*?(?=\ndef |\Z)',
        source,
    )
    assert match, "collect_1h 函数未找到"

    func_body = match.group(0)

    # 检查是否调用 pull_history_1h.py
    calls_pull_history = 'run_script("pull_history_1h.py"' in func_body or "run_script('pull_history_1h.py'" in func_body

    assert not calls_pull_history, (
        "collect_1h() 调用了 pull_history_1h.py（全量 DELETE+INSERT）\n"
        "这会覆盖 collect_1h.py 的增量修复，使增量模式完全无效。\n"
        "修复：移除 pull_history_1h.py 调用，仅保留 collect_1h.py（增量安全）\n"
        "如需全量重建，手动运行：python scripts/pull_history_1h.py"
    )


if __name__ == "__main__":
    # 手动运行测试
    print("Running test_no_bare_delete_from_kline...")
    try:
        test_no_bare_delete_from_kline()
        print("✅ PASS")
    except AssertionError as e:
        print(f"❌ FAIL:\n{e}")

    print("\nRunning test_collect_1h_main_only_is_incremental...")
    try:
        test_collect_1h_main_only_is_incremental()
        print("✅ PASS")
    except AssertionError as e:
        print(f"❌ FAIL:\n{e}")

    print("\nRunning test_data_management_no_pull_history...")
    try:
        test_data_management_no_pull_history()
        print("✅ PASS")
    except AssertionError as e:
        print(f"❌ FAIL:\n{e}")
