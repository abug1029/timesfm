"""死代码回归检测（dead-code purge 2026-09-30 后的防再堆积闸门）。

背景：2026-09-30 死代码清理（49 文件 / 12,228 行 git mv 至 archive/，见
docs/2026-09-30-dead-code-purge-spec.md）。本测试是 spec §5.1 的 P1-5 重设计版：
用 AST 导入图替代名字 grep。

历史教训（六次同型错误，名字 grep 各漏检一种形态）：
- 相对导入（oi_gated_momentum 险被误判死）
- importlib 字符串
- 裸文件名子进程边（pull_history_1h：data_management run_script("pull_history_1h.py")）
故边提取覆盖：AST import/from-import（含相对导入）、字符串字面量中的
``<stem>.py`` 形态（subprocess / importlib / 文档化提示）、tests 导入、
scripts/*.sh 调用边。

断言（spec §5.1）：引用集 ∪ LIVE_ENTRIES ∪ TEMPORARY_ALLOWLIST ∪
REVIEW_CANDIDATES = scope 全集。scope = scripts/ 与 cascade/ 顶层 .py
（archive/ 排除；与 pytest.ini norecursedirs 双重排除一致）。

名单语义：
- LIVE_ENTRIES：文档化人工命令 / 生产入口（保留依据逐条注明）。
- TEMPORARY_ALLOWLIST：regen 三件套顺延 2.9（v4 重生波完成后归档并释放本名单）。
- REVIEW_CANDIDATES：**检测测试首跑发现（2026-09-30）**——零引用、零文档、
  零配置调用，但不在已批准的归档清单内，未经宿主裁定不归档；2.9 后复核。
任何名单条目对应的文件被归档后，test_stale_list_entries 会强制移除该条目。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPE_DIRS = (REPO / "scripts", REPO / "cascade")
EXCLUDED_PARTS = frozenset({"archive", ".venv", "third_party", ".git", ".omc"})

# ---- 名单（逐条注明保留依据；新增条目必须写明证据） ----

# 生产入口与文档化人工命令（ACTIVE_CLI / REF）
LIVE_ENTRIES: dict[str, str] = {
    "copilot": "生产入口（runbook / module_freeze 生产入口行）",
    "cascade_predict": "生产入口（runbook / module_freeze 生产入口行）",
    "monthly_backtest": "固化权威 WF（module_freeze CF-20 注记行）",
    "data_management": "调度采集入口（AGENTS.md:248-250 / docs/runbook.md:23-25）",
    "pull_history_1h": "采集命令（docs/runbook.md:33；data_management run_script 子进程边）",
    "praxist_supervisor": "supervisor 守护（runbook；start_supervisor.sh 调用边）",
    "aligned_slow_loop": "慢环（runbook_praxist_three_loop.md；.sh 调用边）",
    "backtest_1h": "CF-20 遗留入口，DEPRECATED 但文档化（AGENTS.md:390 / scripts/AGENTS.md:35）",
    "install_praxist_llm_env_hook": "ACTIVE_CLI 保留（裁定 c；praxist_llm_env.md:69/:82）",
    "ledger_backfill": "人工命令（docs/runbook.md:78/:86 / docs/paper_trading.md:78）",
    "live_cov_health": "人工命令（docs/runbook.md:79/:89）",
    "organize_reports": "人工命令（AGENTS.md:406/:426）",
    "restart_readiness_check": "重启就绪验证（changelog 2026-09-29-stage3:167；spec v2 :97）",
}

# 顺延 2.9：v4 重生波完成后 git mv 归档并释放本名单（monitor_rb_regen.sh 为 .sh 非节点）
TEMPORARY_ALLOWLIST: dict[str, str] = {
    "regenerate_all_baselines": "regen 三件套，顺延 2.9（spec §0）",
    "regen_rb": "regen 三件套，顺延 2.9（spec §0；monitor_rb_regen.sh 调用边）",
}

# 检测测试首跑发现（2026-09-30）：零引用 / 零文档 / 零配置调用；
# 不在已批准归档清单内 → 先显式挂账，2.9 后宿主复核处置
REVIEW_CANDIDATES: dict[str, str] = {
    "ablation_context": "零引用零文档（仅 2026-09-11 sdd 审核提及）；初始提交 vintage",
    "add_horizon_known": "一次性补填工具（2026-09-28 已执行；STATE.md W5.5 未决牵连，不宜归档）",
    "resmoke_vol_thr_offline": "零引用零文档零配置调用；初始提交 vintage",
    "scan_vol_thr_smoke": "零引用零文档零配置调用；初始提交 vintage",
    "validate_context_length": "D5 修复脚本之一（2026-09-28 changelog）但零活引用",
    "verify_baseline_consistency": "零引用零文档零配置调用；初始提交 vintage",
}


def _excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def _scope_nodes() -> dict[tuple[str, str], Path]:
    """(目录名, stem) -> 路径；scripts/ 与 cascade/ 顶层 .py，排除 archive。"""
    nodes: dict[tuple[str, str], Path] = {}
    for d in SCOPE_DIRS:
        for p in sorted(d.glob("*.py")):
            if p.name == "__init__.py" or _excluded(p):
                continue
            nodes[(d.name, p.stem)] = p
    return nodes


def _py_refs(path: Path) -> set[str]:
    """AST 提取一个 .py 的全部引用名：import / from-import（含相对导入解析）
    + 全部字符串字面量（覆盖 subprocess / importlib / 文档提示中的 <stem>.py）。"""
    refs: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                refs.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level >= 1:  # 相对导入：按所在包目录解析（cascade / scripts）
                base = path.parent.name
                if node.module:
                    refs.add(f"{base}.{node.module}")
                    for a in node.names:
                        refs.add(f"{base}.{node.module}.{a.name}")
                else:
                    for a in node.names:
                        refs.add(f"{base}.{a.name}")
            else:
                if node.module:
                    refs.add(node.module)
                    for a in node.names:
                        refs.add(f"{node.module}.{a.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            refs.add(node.value)
    return refs


def _edge_sources(nodes: dict[tuple[str, str], Path]) -> list[tuple[str, set[str]]]:
    """边来源：scope 内 .py + tests/**（排除 archive）+ scripts/*.sh。"""
    sources: list[tuple[str, set[str]]] = []
    for (dname, stem), p in nodes.items():
        sources.append((f"{dname}/{stem}.py", _py_refs(p)))
    for p in sorted((REPO / "tests").rglob("*.py")):
        if _excluded(p):
            continue
        sources.append((str(p.relative_to(REPO)), _py_refs(p)))
    for p in sorted((REPO / "scripts").glob("*.sh")):
        txt = p.read_text(encoding="utf-8", errors="replace")
        sources.append((f"scripts/{p.name}", set(re.findall(r"\b[a-z_0-9]+\.py\b", txt))))
    return sources


def _referenced(nodes: dict[tuple[str, str], Path]) -> dict[tuple[str, str], str]:
    """返回每个被引用节点的首个证据（来源标签）。"""
    sources = _edge_sources(nodes)
    ref: dict[tuple[str, str], str] = {}
    for (dname, stem) in nodes:
        exact = {stem, f"{dname}.{stem}"}
        rx = re.compile(rf"(?:^|[^A-Za-z0-9_.]){re.escape(stem)}\.py\b")
        for label, refs in sources:
            if any(r in exact or rx.search(r) for r in refs):
                ref[(dname, stem)] = label
                break
    return ref


def test_no_unaccounted_modules() -> None:
    """每个 scope 模块必须：被引用，或在三个名单之一（含证据注记）。"""
    nodes = _scope_nodes()
    assert nodes, "scope 为空——目录结构变更？"
    ref = _referenced(nodes)
    enlisted = set(LIVE_ENTRIES) | set(TEMPORARY_ALLOWLIST) | set(REVIEW_CANDIDATES)
    unaccounted = sorted(
        f"{d}/{s}.py" for (d, s) in nodes if (d, s) not in ref and s not in enlisted
    )
    if unaccounted:
        pytest_fail_unaccounted(unaccounted)


def test_stale_list_entries() -> None:
    """名单条目必须仍存在于 scope——文件归档后强制同步移除名单项
    （如 2.9 regen 三件套归档后释放 TEMPORARY_ALLOWLIST）。"""
    stems = {s for (_d, s) in _scope_nodes()}
    stale = sorted(
        name
        for name in set(LIVE_ENTRIES) | set(TEMPORARY_ALLOWLIST) | set(REVIEW_CANDIDATES)
        if name not in stems
    )
    assert not stale, f"名单中存在已不在 scope 的条目（已归档？请移除）: {stale}"


def test_scope_excludes_archive_and_collisions() -> None:
    """scope 完整性：archive 排除生效 + scripts/cascade 顶层 stem 无碰撞。"""
    nodes = _scope_nodes()
    assert all("archive" not in p.parts for p in nodes.values()), "archive 泄漏进 scope"
    stems = [s for (_d, s) in nodes]
    assert len(stems) == len(set(stems)), "scripts/cascade 顶层 stem 碰撞——匹配逻辑需升级为 (dir, stem) 精确匹配"


def pytest_fail_unaccounted(unaccounted: list[str]) -> None:
    import pytest

    pytest.fail(
        "发现零引用且未挂账的模块（新增文件必须三选一：被引用 / 归档 / 进名单并注明依据）:\n"
        + "\n".join(f"  - {m}" for m in unaccounted)
        + "\n处理路径：git mv 至 scripts|cascade/archive/<date>-<tag>/；"
        "或补 LIVE_ENTRIES / TEMPORARY_ALLOWLIST / REVIEW_CANDIDATES 条目（附证据）。"
    )
