"""A2-P1 共享运行配置: run_id、路径、eval grid、JSONL 读取/校验、排他锁、幂等写入。

Worker、Orchestrator、Report Generator 共同使用此模块，消除重复表达式。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional
from datetime import datetime, timezone

from config.backtest_config import CONTEXT_BARS, HORIZON, STEP, EVAL_WINDOW_BARS, SLIPPAGE_TICKS, SYMBOLS


def stable_symbol_seed(symbol: str) -> int:
    """基于 SHA256 的稳定种子函数。

    同 symbol 返回相同 seed，跨 Python 进程可复现（不依赖 PYTHONHASHSEED）。
    取 SHA256 前 4 字节，转为 uint32 (0..4294967295)。
    """
    digest = hashlib.sha256(symbol.upper().encode("utf-8")).digest()
    return int.from_bytes(digest[:4], byteorder="big", signed=False)


# ═══════════════════════════════════════════════════════════
# Exclusive File Lock
# ═══════════════════════════════════════════════════════════

@contextmanager
def exclusive_result_lock(lock_path: Path, *, run_id: str = "unknown") -> Generator[None, None, None]:
    """跨进程排他锁: 使用 os.O_CREAT|os.O_EXCL 保证单写入者。

    正常退出时关闭文件描述符并删除锁文件。
    如果锁已存在，读取元数据并抛 RuntimeError 告知持有者信息。
    不自动清理 stale lock——由用户显式决定。
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "pid": os.getpid(),
        "run_id": run_id,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }

    fd = None  # type: int | None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            holder = json.loads(Path(lock_path).read_text(encoding="utf-8"))
            holder_info = (
                f"pid={holder.get('pid', '?')}, "
                f"run_id={holder.get('run_id', '?')}, "
                f"acquired_at={holder.get('acquired_at', '?')}"
            )
        except Exception:
            holder_info = f"lock_path={lock_path} (无法读取元数据)"
        raise RuntimeError(f"lock held by {holder_info}") from None

    try:
        os.write(fd, json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if lock_path.exists():
            os.unlink(str(lock_path))


# ═══════════════════════════════════════════════════════════
# Idempotent JSONL Append
# ═══════════════════════════════════════════════════════════

_IMMUTABLE_FIELDS = (
    "run_id", "symbol", "version",
    "pure_pred_move", "scheme_pred_move",
    "lgbm_pred_move",              # A2-P1 / A2-P1.1
    "stacked_pred_move",           # A2-P2
    "lgbm_residual_pred_move",     # A2-P2
    "actual_move", "base_price", "atr",
)


def append_unique_record(path: Path, record: dict, key: str = "bar_idx") -> None:
    """幂等追加 JSONL 记录。

    - 如果 key 已存在且不可变字段完全相同: 静默跳过 (幂等)
    - 如果 key 已存在但字段有冲突: 抛 ValueError
    - 如果 key 不存在: 追加并 flush
    """
    path = Path(path)
    key_value = record[key]

    # 读取已有记录构建 key -> record 映射
    existing: dict = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rk = rec.get(key)
                if rk is not None:
                    existing[rk] = rec

    if key_value in existing:
        prev = existing[key_value]
        # 比较不可变字段
        conflicts = []
        for field in _IMMUTABLE_FIELDS:
            old = prev.get(field)
            new = record.get(field)
            if old != new:
                conflicts.append(f"{field}: {old!r} vs {new!r}")
        if conflicts:
            raise ValueError(
                f"conflicting record at {path} for {key}={key_value}: "
                f"{', '.join(conflicts)}"
            )
        # 完全相同 → 幂等跳过
        return

    # 不存在 → 追加
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()


# ═══════════════════════════════════════════════════════════
# Eval Grid
# ═══════════════════════════════════════════════════════════

def generate_eval_grid(total_bars: int) -> list[int]:
    """生成 eval bars 网格。

    起点: CONTEXT_BARS (需要足够 context 窗口)
    终点: total_bars - HORIZON (需要足够空间计算未来移动)
    步长: STEP (非重叠窗口)
    """
    # 评估窗口截断: 聚焦最近 EVAL_WINDOW_BARS 根 bar (~200 交易日)
    eval_start = max(CONTEXT_BARS, total_bars - EVAL_WINDOW_BARS)
    return list(range(eval_start, total_bars - HORIZON + 1, STEP))


def expected_eval_grid(symbol: str) -> list[int]:
    """从当前数据库计算某品种的精确 eval grid。

    通过 DataStore 读取主合约 1H 数据，获取真实 bar 数量后
    调用 generate_eval_grid 生成精确网格。

    如果 DataStore 打开失败或没有数据，抛出 RuntimeError。
    """
    from data.data_store import DataStore

    with DataStore(symbol) as store:
        df_1h = store.get_main_contract_1h(limit=100000)
    if df_1h.empty:
        raise RuntimeError(
            f"expected_eval_grid({symbol}): DataStore 返回空数据，"
            f"请先采集 {symbol} 的 1H 数据"
        )
    return generate_eval_grid(len(df_1h))


# ═══════════════════════════════════════════════════════════
# RunConfig
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RunConfig:
    """单次运行的共享配置。"""
    run_id: str
    results_dir: Path
    logs_dir: Path
    report_path: Path
    features_dir: Path
    symbols: list[str]

    @classmethod
    def for_run(cls, run_id: str, symbols: list[str], root: Path) -> "RunConfig":
        """根据 run_id 创建对应实验的完整路径配置。

        A2-P1 与 A2-P1.1 使用完全隔离的结果目录、日志目录和报告路径。
        """
        if run_id == "a2-p1":
            suffix = "a2_p1"
            report = root / "reports/research/2026-08-05_a2_p1_baseline_result.md"
        elif run_id == "a2-p1.1":
            suffix = "a2_p1.1"
            report = root / "reports/research/20260806_a2_p1.1_verdict.md"
        elif run_id == "a2-p2":
            suffix = "a2_p2"
            report = root / "reports/research/20260807_a2_p2_verdict.md"
        else:
            raise ValueError(f"unsupported run_id: {run_id}")
        return cls(
            run_id=run_id,
            results_dir=root / f"reports/{suffix}_results",
            logs_dir=root / f"reports/{suffix}_logs",
            report_path=report,
            features_dir=root / "reports/a2_p1_features",
            symbols=[s.lower() for s in symbols],
        )


# ═══════════════════════════════════════════════════════════
# JSONL 读取
# ═══════════════════════════════════════════════════════════

def load_jsonl_records(path: Path) -> list[dict]:
    """读取 JSONL 文件，返回记录列表。

    - 空行自动跳过
    - 解析失败抛 ValueError 并带上行号
    """
    records: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL {path}:{line_no}") from exc
    return records



import subprocess as _subprocess

from config.backtest_config import TICK_SIZES
from cascade.lgbm_features import FEATURE_COLUMNS


def _get_git_sha(root: Path) -> str:
    """返回当前 git HEAD commit hash（全写）。"""
    try:
        r = _subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=root,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _is_git_dirty(root: Path) -> bool:
    """工作区是否有未提交变更。"""
    try:
        r = _subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=root,
        )
        return r.returncode == 0 and len(r.stdout.strip()) > 0
    except Exception:
        return False


def build_manifest(
    run_id: str,
    symbols: list[str],
    results_dir: Path,
    logs_dir: Path,
    report_path: Path,
    per_symbol: dict[str, dict] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    root: Path | None = None,
) -> dict:
    """构建运行清单 (manifest)，包含身份、配置、git、逐品种状态。

    输出 JSON 到 ``<report_path 所在目录>/<run_id>.manifest.json``。

    返回 manifest dict（供调用方写入 finished_at 后回填）。
    """
    root = root or Path(__file__).resolve().parent.parent

    manifest: dict = {
        "run_id": run_id,
        "symbols": symbols,
        "results_dir": str(results_dir),
        "logs_dir": str(logs_dir),
        "report_path": str(report_path),
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "finished_at": finished_at,
        "python_executable": sys.executable,
        "git_sha": _get_git_sha(root),
        "git_dirty": _is_git_dirty(root),
        "feature_columns": list(FEATURE_COLUMNS),
        "config_snapshot": {
            "CONTEXT_BARS": CONTEXT_BARS,
            "HORIZON": HORIZON,
            "STEP": STEP,
            "SLIPPAGE_TICKS": SLIPPAGE_TICKS,
        },
        "tick_sizes": dict(TICK_SIZES),
        "per_symbol": per_symbol or {},
    }

    out_path = report_path.parent / f"{run_id}.manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return manifest


# ═══════════════════════════════════════════════════════════
# ValidationResult
# ═══════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    """JSONL 记录校验结果。"""
    ok: bool
    errors: list[str]
    row_count: int = 0
    unique_count: int = 0
    missing_bars: list[int] | None = None
    unexpected_bars: list[int] | None = None
    versions: set[str] | None = None


@dataclass
class ValidationReport:
    """全量品种校验汇总报告。"""
    ok: bool
    per_symbol: dict[str, ValidationResult]
    errors: list[str]


_REQUIRED_NUMERIC_FIELDS = (
    "pure_pred_move", "scheme_pred_move",
    "actual_move", "base_price", "atr",
)

# run_id -> LGBM 特有必需字段 (不同 run_id 的 Worker 输出不同预测列)
_REQUIRED_LGBM_FIELDS_BY_RUN = {
    "a2-p1":   ("lgbm_pred_move",),
    "a2-p1.1": ("lgbm_pred_move",),
    "a2-p2":   ("stacked_pred_move", "lgbm_residual_pred_move"),
}

# 允许为 None 的字段 (scheme 失败时 scheme_pred_move 为 None)
_OPTIONAL_NULL_FIELDS = ("scheme_pred_move",)


def _is_finite(v) -> bool:
    """检查值是否为有限数。"""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def validate_jsonl_records(
    records: list[dict],
    expected_bars: list[int],
    run_id: str,
    symbol: str,
    version: Optional[str] = None,
) -> ValidationResult:
    """校验 JSONL 记录的完整性。

    校验项:
    1. 同一 symbol 存在重复 bar_idx
    2. 缺失期望 eval bar
    3. 存在意外 eval bar
    4. run_id 与 config.run_id 不一致
    5. symbol 字段不一致
    6. 存在多个不同非空 version
    7. 缺少必要数字字段
    8. scheme_ok == False 或 scheme_error 非空 (如果字段存在)
    9. 预测、actual、base_price 或 atr 为非有限数
    """
    errors: list[str] = []
    expected_set = set(expected_bars)

    # ── 提取 bar_idx 并检查重复 ──
    bar_indices: list[int] = []
    for rec in records:
        idx = rec.get("bar_idx")
        if idx is None:
            errors.append("missing bar_idx in record")
            continue
        bar_indices.append(int(idx))

    actual_set = set(bar_indices)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)

    if missing:
        errors.append(f"missing eval bars: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    if unexpected:
        errors.append(f"unexpected bars: {unexpected[:5]}{'...' if len(unexpected) > 5 else ''}")

    # 检查重复
    if len(bar_indices) != len(actual_set):
        from collections import Counter
        dupes = [k for k, v in Counter(bar_indices).items() if v > 1]
        errors.append(f"duplicate bar_idx: {dupes[:5]}")

    # ── run_id 一致性 ──
    seen_run_ids = set()
    for rec in records:
        rid = rec.get("run_id")
        if rid is not None:
            seen_run_ids.add(str(rid))
    if seen_run_ids and seen_run_ids != {run_id}:
        errors.append(
            f"run_id mismatch: expected {run_id!r}, got {sorted(seen_run_ids)}"
        )

    # ── symbol 一致性 ──
    seen_symbols = set()
    for rec in records:
        s = rec.get("symbol")
        if s is not None:
            seen_symbols.add(str(s))
    sym_upper = symbol.upper()
    if seen_symbols and seen_symbols != {sym_upper}:
        errors.append(
            f"symbol mismatch: expected {sym_upper!r}, got {sorted(seen_symbols)}"
        )

    # ── version 冲突 ──
    seen_versions: set[str] = set()
    for rec in records:
        v = rec.get("version")
        if v is not None and str(v).strip():
            seen_versions.add(str(v).strip())
    if len(seen_versions) > 1:
        errors.append(f"multiple versions: {sorted(seen_versions)}")

    # ── 必要数字字段 + 有限数检查 ──
    for rec in records:
        bi = rec.get("bar_idx")
        for field in _REQUIRED_NUMERIC_FIELDS:
            val = rec.get(field)
            if val is None:
                # scheme_pred_move 允许为 None (scheme 失败时)
                if field in _OPTIONAL_NULL_FIELDS:
                    continue
                errors.append(f"bar_idx={bi}: missing required field {field}")
            elif not _is_finite(val):
                errors.append(f"bar_idx={bi}: non-finite {field} = {val!r}")

    # ── run-specific LGBM 字段校验 ──
    if run_id not in _REQUIRED_LGBM_FIELDS_BY_RUN:
        errors.append(f"unknown run_id {run_id!r}: no LGBM field mapping configured")
    else:
        lgbm_required = _REQUIRED_LGBM_FIELDS_BY_RUN[run_id]
        for rec in records:
            bi = rec.get("bar_idx")
            for field in lgbm_required:
                val = rec.get(field)
                if val is None:
                    errors.append(f"bar_idx={bi}: missing required field {field}")
                elif not _is_finite(val):
                    errors.append(f"bar_idx={bi}: non-finite {field} = {val!r}")

    # ── scheme_ok / scheme_error (如果字段存在) ──
    # A2-P1/A2-P1.1: scheme_ok=False 且 scheme_error 非空 → 拒绝 (严格)
    # A2-P2: scheme 错误作为警告，不拒绝 (部分 bar 的 scheme 可能失败)
    scheme_errors = []
    for rec in records:
        bi = rec.get("bar_idx")
        ok = rec.get("scheme_ok")
        err = rec.get("scheme_error")
        if ok is False and err:
            scheme_errors.append(f"bar_idx={bi}: scheme_error = {err!r}")

    # A2-P1/A2-P1.1 严格拒绝 scheme 错误；A2-P2 允许
    if run_id in ("a2-p1", "a2-p1.1") and scheme_errors:
        errors.extend(scheme_errors)

    return ValidationResult(
        ok=len(errors) == 0,
        errors=errors,
        row_count=len(records),
        unique_count=len(actual_set),
        missing_bars=missing,
        unexpected_bars=unexpected,
        versions=seen_versions,
    )


def validate_run_results(config: "RunConfig") -> ValidationReport:
    """对 config.symbols 中的每个 symbol 校验其 JSONL 结果文件。

    返回汇总 ValidationReport。
    """
    per_symbol: dict[str, ValidationResult] = {}
    all_errors: list[str] = []

    for sym in config.symbols:
        sym_lower = sym.lower()
        jsonl_path = config.results_dir / f"{sym_lower}.jsonl"

        if not jsonl_path.exists():
            vr = ValidationResult(
                ok=False,
                errors=[f"result file not found: {jsonl_path}"],
            )
            per_symbol[sym_lower] = vr
            all_errors.append(f"[{sym_lower}] result file not found: {jsonl_path}")
            continue

        try:
            records = load_jsonl_records(jsonl_path)
        except ValueError as exc:
            vr = ValidationResult(
                ok=False,
                errors=[f"JSONL parse error: {exc}"],
            )
            per_symbol[sym_lower] = vr
            all_errors.append(f"[{sym_lower}] JSONL parse error: {exc}")
            continue

        try:
            expected_grid = expected_eval_grid(sym_lower)
        except RuntimeError as exc:
            vr = ValidationResult(
                ok=False,
                errors=[f"cannot compute expected grid: {exc}"],
            )
            per_symbol[sym_lower] = vr
            all_errors.append(f"[{sym_lower}] cannot compute expected grid: {exc}")
            continue

        vr = validate_jsonl_records(records, expected_grid, config.run_id, sym_lower)
        per_symbol[sym_lower] = vr
        if not vr.ok:
            for err in vr.errors:
                all_errors.append(f"[{sym_lower}] {err}")

    return ValidationReport(
        ok=all(vr.ok for vr in per_symbol.values()),
        per_symbol=per_symbol,
        errors=all_errors,
    )
