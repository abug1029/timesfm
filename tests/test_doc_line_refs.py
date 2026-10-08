"""行号引用闸门（技术债 D1 防回归，2026-10-08）。

见 `scripts/check_line_refs.py` 模块文档与
`docs/superpowers/reports/2026-10-08-d1-line-reference-audit.md`。

两项断言：
- living 契约文档零行号引用（改符号/章节锚点）；
- dated 报告/计划/spec 含行号引用时必须声明 `代码基线`（commit 钉住历史证据）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_line_refs.py"


def test_script_exists() -> None:
    assert SCRIPT.is_file(), f"missing gate script: {SCRIPT}"


def test_no_line_number_refs_and_baselines_present() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, (
        "行号引用闸门失败（D1 回归）。修法见脚本输出：\n"
        + proc.stdout
        + proc.stderr
    )
