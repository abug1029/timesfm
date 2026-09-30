"""A2-P1 历史结果文件调和工具：扫描、恢复、去重、写 manifest。

严禁 import 任何模型/数据库依赖。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

# ─────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────

EXPECTED_BARS_COUNT = len(list(range(480, 10000 - 24 + 1, 24)))  # 396

IMMUTABLE_SYMBOLS = [
    "ss", "rb", "fu", "bu", "ao", "sp",
    "i", "jm", "m", "p", "eg", "jd", "lh",
    "cf", "sr", "ta", "ma", "fg", "ur", "cj",
]


# ─────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    """计算文件 SHA256 (hex)。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_jsonl_rows(path: Path) -> List[dict]:
    """读取 JSONL 文件，跳过空行；损坏 JSON 行抛 ValueError 带行号。"""
    rows: List[dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped:
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL {path}:{line_no}") from exc
    return rows


def _bar_idx_values(rows: List[dict]) -> List[int]:
    """从记录列表中提取 bar_idx 值（按原始顺序）。"""
    return [r["bar_idx"] for r in rows if "bar_idx" in r]


def _unique_bars(rows: List[dict]) -> Set[int]:
    return set(_bar_idx_values(rows))


def _duplicate_count(rows: List[dict]) -> int:
    bars = _bar_idx_values(rows)
    return len(bars) - len(set(bars))


def _versions(rows: List[dict]) -> Set[str]:
    return {r.get("version", "unknown") for r in rows}


# ─────────────────────────────────────────────────────────────
# scan_historical_results
# ─────────────────────────────────────────────────────────────

@dataclass
class SymbolScanResult:
    source: str = "missing"  # "main" / "backup" / "missing"
    main_path: Optional[str] = None
    backup_path: Optional[str] = None
    main_rows: int = 0
    backup_rows: int = 0
    main_unique_bars: int = 0
    backup_unique_bars: int = 0
    main_duplicate_rows: int = 0
    backup_duplicate_rows: int = 0
    first_bar: Optional[int] = None
    last_bar: Optional[int] = None
    versions: Set[str] = field(default_factory=set)
    sha256: Optional[str] = None
    expected_bars_count: int = EXPECTED_BARS_COUNT
    unexpected_bars_count: int = 0  # unique_bars 超出 expected 的数量
    status: str = "missing"  # "complete" / "partial" / "duplicated" / "missing"


def scan_historical_results(
    main_dir: Path,
    backup_dir: Path,
    expected_symbols: List[str],
) -> Dict[str, SymbolScanResult]:
    """扫描主目录和备份目录，返回每个 symbol 的扫描结果。"""
    results: Dict[str, SymbolScanResult] = {}

    for sym in expected_symbols:
        sym_lower = sym.lower()
        main_path = main_dir / f"{sym_lower}.jsonl"
        backup_path = backup_dir / f"{sym_lower}.jsonl"

        main_exists = main_path.exists()
        backup_exists = backup_path.exists()

        sr = SymbolScanResult()

        if main_exists:
            sr.source = "main"
            sr.main_path = str(main_path)
            sr.sha256 = _sha256(main_path)
            main_rows = _read_jsonl_rows(main_path)
            sr.main_rows = len(main_rows)
            sr.main_unique_bars = len(_unique_bars(main_rows))
            sr.main_duplicate_rows = _duplicate_count(main_rows)
            sr.versions = _versions(main_rows)
            bars = _bar_idx_values(main_rows)
            if bars:
                sr.first_bar = min(bars)
                sr.last_bar = max(bars)
        elif backup_exists:
            sr.source = "backup"
            sr.backup_path = str(backup_path)
            sr.sha256 = _sha256(backup_path)
            backup_rows = _read_jsonl_rows(backup_path)
            sr.backup_rows = len(backup_rows)
            sr.backup_unique_bars = len(_unique_bars(backup_rows))
            sr.backup_duplicate_rows = _duplicate_count(backup_rows)
            sr.versions = _versions(backup_rows)
            bars = _bar_idx_values(backup_rows)
            if bars:
                sr.first_bar = min(bars)
                sr.last_bar = max(bars)
        else:
            sr.source = "missing"

        # 确定状态
        if sr.source == "missing":
            sr.status = "missing"
        else:
            unique = sr.main_unique_bars if main_exists else sr.backup_unique_bars
            dups = sr.main_duplicate_rows if main_exists else sr.backup_duplicate_rows
            sr.unexpected_bars_count = max(0, unique - EXPECTED_BARS_COUNT)
            if dups > 0:
                sr.status = "duplicated"
            elif unique == EXPECTED_BARS_COUNT:
                sr.status = "complete"
            elif unique > 0:
                sr.status = "partial"
            else:
                sr.status = "missing"

        results[sym_lower] = sr

    return results


# ─────────────────────────────────────────────────────────────
# restore_missing_results
# ─────────────────────────────────────────────────────────────

def restore_missing_results(
    main_dir: Path,
    backup_dir: Path,
    expected_symbols: List[str],
    apply: bool = False,
) -> dict:
    """
    将备份目录中存在的 JSONL 恢复到主目录（仅当主目录不存在时）。

    Returns:
        {copied: [...], conflicts: [...], skipped: [...]}
    """
    result = {"copied": [], "conflicts": [], "skipped": []}

    for sym in expected_symbols:
        sym_lower = sym.lower()
        main_path = main_dir / f"{sym_lower}.jsonl"
        backup_path = backup_dir / f"{sym_lower}.jsonl"

        if main_path.exists():
            # 主目录已有文件 → conflict，绝不覆盖
            result["conflicts"].append({
                "symbol": sym_lower,
                "reason": "main directory already has file",
                "main_path": str(main_path),
            })
            continue

        if backup_path.exists():
            if apply:
                main_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(backup_path), str(main_path))
                result["copied"].append({
                    "symbol": sym_lower,
                    "from": str(backup_path),
                    "to": str(main_path),
                    "sha256": _sha256(main_path),
                })
            else:
                result["skipped"].append({
                    "symbol": sym_lower,
                    "reason": "dry-run, would restore",
                    "backup_path": str(backup_path),
                })
        else:
            result["skipped"].append({
                "symbol": sym_lower,
                "reason": "not found in backup either",
            })

    return result


# ─────────────────────────────────────────────────────────────
# canonicalize_duplicates
# ─────────────────────────────────────────────────────────────

def canonicalize_duplicates(
    main_dir: Path,
    expected_symbols: List[str],
    apply: bool = False,
) -> dict:
    """
    对主目录中重复写入的 JSONL 文件去重：
    - 按 bar_idx 保留首次出现的记录
    - 写到 <symbol>.jsonl.canonical（不覆盖原文件）

    Returns:
        {canonicalized: [...], already_clean: [...]}
    """
    result = {"canonicalized": [], "already_clean": []}

    for sym in expected_symbols:
        sym_lower = sym.lower()
        src_path = main_dir / f"{sym_lower}.jsonl"

        if not src_path.exists():
            continue

        rows = _read_jsonl_rows(src_path)
        total = len(rows)
        if total == 0:
            continue

        # 按 bar_idx 保留首次出现
        seen: Set[int] = set()
        deduped: List[dict] = []
        for r in rows:
            bi = r.get("bar_idx")
            if bi is not None and bi not in seen:
                seen.add(bi)
                deduped.append(r)

        dup_count = total - len(deduped)

        canonical_path = src_path.with_name(f"{sym_lower}.jsonl.canonical")

        if dup_count == 0:
            if apply:
                lines = [json.dumps(r, ensure_ascii=False) for r in deduped]
                canonical_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                old_sha = _sha256(src_path)
                new_sha = _sha256(canonical_path)
                result["already_clean"].append({
                    "symbol": sym_lower,
                    "rows": total,
                    "canonical_path": str(canonical_path),
                    "original_sha256": old_sha,
                    "canonical_sha256": new_sha,
                })
            else:
                result["already_clean"].append({
                    "symbol": sym_lower,
                    "rows": total,
                })
            continue

        if apply:
            canonical_path = src_path.with_name(f"{sym_lower}.jsonl.canonical")
            lines = [json.dumps(r, ensure_ascii=False) for r in deduped]
            canonical_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            old_sha = _sha256(src_path)
            new_sha = _sha256(canonical_path)

            result["canonicalized"].append({
                "symbol": sym_lower,
                "original_rows": total,
                "canonical_rows": len(deduped),
                "removed_duplicates": dup_count,
                "original_sha256": old_sha,
                "canonical_sha256": new_sha,
                "original_path": str(src_path),
                "canonical_path": str(canonical_path),
            })
        else:
            result["canonicalized"].append({
                "symbol": sym_lower,
                "original_rows": total,
                "canonical_rows": len(deduped),
                "removed_duplicates": dup_count,
                "dry_run": True,
            })

    return result


# ─────────────────────────────────────────────────────────────
# write_manifest
# ─────────────────────────────────────────────────────────────

def write_manifest(
    main_dir: Path,
    backup_dir: Path,
    expected_symbols: List[str],
    output_path: Path,
) -> dict:
    """生成并写入 manifest JSON 文件。"""
    scan = scan_historical_results(main_dir, backup_dir, expected_symbols)

    manifest = {
        "generated_at": _now_iso(),
        "main_dir": str(main_dir),
        "backup_dir": str(backup_dir),
        "expected_symbols": expected_symbols,
        "per_symbol": {},
    }

    for sym, sr in scan.items():
        entry: dict = {
            "source": sr.source,
            "status": sr.status,
        }

        if sr.source == "main":
            entry["rows"] = sr.main_rows
            entry["unique_bars"] = sr.main_unique_bars
            entry["duplicate_rows"] = sr.main_duplicate_rows
            entry["first_bar"] = sr.first_bar
            entry["last_bar"] = sr.last_bar
            entry["versions"] = sorted(sr.versions)
            entry["sha256"] = sr.sha256
            entry["expected_bars_count"] = sr.expected_bars_count
            entry["unexpected_bars_count"] = sr.unexpected_bars_count
        elif sr.source == "backup":
            entry["rows"] = sr.backup_rows
            entry["unique_bars"] = sr.backup_unique_bars
            entry["duplicate_rows"] = sr.backup_duplicate_rows
            entry["first_bar"] = sr.first_bar
            entry["last_bar"] = sr.last_bar
            entry["versions"] = sorted(sr.versions)
            entry["sha256"] = sr.sha256
            entry["expected_bars_count"] = sr.expected_bars_count
            entry["unexpected_bars_count"] = sr.unexpected_bars_count
        else:
            entry["rows"] = 0
            entry["unique_bars"] = 0
            entry["duplicate_rows"] = 0
            entry["first_bar"] = None
            entry["last_bar"] = None
            entry["versions"] = []
            entry["sha256"] = None
            entry["expected_bars_count"] = sr.expected_bars_count
            entry["unexpected_bars_count"] = 0

        manifest["per_symbol"][sym] = entry

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def _print_scan(scan: Dict[str, SymbolScanResult]) -> None:
    """打印扫描结果摘要。"""
    print(f"{'Symbol':<8} {'Source':<8} {'Status':<12} {'Rows':>6} {'Unique':>6} {'Dups':>6} {'SHA256[:12]}':>14}")
    print("-" * 72)
    for sym in sorted(scan):
        sr = scan[sym]
        rows = sr.main_rows if sr.source == "main" else sr.backup_rows
        unique = sr.main_unique_bars if sr.source == "main" else sr.backup_unique_bars
        dups = sr.main_duplicate_rows if sr.source == "main" else sr.backup_duplicate_rows
        sha = sr.sha256[:12] if sr.sha256 else "N/A"
        print(f"{sym:<8} {sr.source:<8} {sr.status:<12} {rows:>6} {unique:>6} {dups:>6} {sha:>14}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="A2-P1 历史结果文件调和工具")
    parser.add_argument("--dry-run", action="store_true", help="只扫描并打印，不写任何文件")
    parser.add_argument("--canonicalize", action="store_true", help="执行 canonicalize_duplicates（去重写 .canonical 文件）")
    parser.add_argument("--restore", action="store_true", help="执行 restore_missing_results（从备份恢复到主目录）")
    parser.add_argument("--write-manifest", action="store_true", help="生成 reports/a2_p1_manifest.json")
    parser.add_argument("--symbols", nargs="*", default=None, help="指定品种列表（默认使用 backtest_config.SYMBOLS）")

    args = parser.parse_args()

    root = Path(__file__).parent.parent
    main_dir = root / "reports" / "a2_p1_results"
    backup_dir = root / "reports" / "a2_p1_results_backup"
    manifest_path = root / "reports" / "a2_p1_manifest.json"

    if args.symbols:
        expected_symbols = [s.lower() for s in args.symbols]
    else:
        try:
            from config.backtest_config import SYMBOLS
            expected_symbols = [s.lower() for s in SYMBOLS]
        except ImportError:
            expected_symbols = IMMUTABLE_SYMBOLS

    if args.dry_run:
        print("=== A2-P1 历史结果文件扫描 (DRY RUN) ===\n")
        scan = scan_historical_results(main_dir, backup_dir, expected_symbols)
        _print_scan(scan)

        print("=== 恢复预检 ===")
        restore = restore_missing_results(main_dir, backup_dir, expected_symbols, apply=False)
        print(f"  可恢复 (skipped): {len(restore['skipped'])}")
        for item in restore["skipped"]:
            print(f"    {item['symbol']}: {item['reason']}")
        print(f"  冲突 (conflicts): {len(restore['conflicts'])}")
        for item in restore["conflicts"]:
            print(f"    {item['symbol']}: {item['reason']}")
        print()

        print("=== 去重预检 ===")
        canon = canonicalize_duplicates(main_dir, expected_symbols, apply=False)
        print(f"  需去重: {len(canon['canonicalized'])}")
        for item in canon["canonicalized"]:
            print(f"    {item['symbol']}: {item['original_rows']} -> {item['canonical_rows']} (移除 {item['removed_duplicates']} 重复)")
        print(f"  已干净: {len(canon['already_clean'])}")
        for item in canon["already_clean"]:
            print(f"    {item['symbol']}: {item['rows']} rows")
        print()
        return

    if args.canonicalize:
        print("=== 执行去重 (canonicalize) ===")
        canon = canonicalize_duplicates(main_dir, expected_symbols, apply=True)
        for item in canon["canonicalized"]:
            print(f"  {item['symbol']}: {item['original_rows']} -> {item['canonical_rows']} rows, "
                  f"移除 {item['removed_duplicates']} 重复")
            print(f"    原文件 SHA256:   {item['original_sha256']}")
            print(f"    去重后 SHA256:   {item['canonical_sha256']}")
            print(f"    去重文件:        {item['canonical_path']}")
        for item in canon["already_clean"]:
            print(f"  {item['symbol']}: 已干净 ({item['rows']} rows)")
        print()
        # 更新 manifest
        write_manifest(main_dir, backup_dir, expected_symbols, manifest_path)
        print(f"Manifest 已更新: {manifest_path}")
        return

    if args.restore:
        print("=== 执行恢复 (restore) ===")
        restore = restore_missing_results(main_dir, backup_dir, expected_symbols, apply=True)
        for item in restore["copied"]:
            print(f"  已恢复 {item['symbol']}: {item['from']} -> {item['to']}")
        for item in restore["conflicts"]:
            print(f"  冲突   {item['symbol']}: {item['reason']}")
        for item in restore["skipped"]:
            print(f"  跳过   {item['symbol']}: {item['reason']}")
        print()
        write_manifest(main_dir, backup_dir, expected_symbols, manifest_path)
        print(f"Manifest 已更新: {manifest_path}")
        return

    if args.write_manifest:
        print("=== 生成 Manifest ===")
        manifest = write_manifest(main_dir, backup_dir, expected_symbols, manifest_path)
        print(f"Manifest 已写入: {manifest_path}")
        print(f"  品种数: {len(manifest['per_symbol'])}")
        for sym, entry in sorted(manifest["per_symbol"].items()):
            print(f"  {sym}: source={entry['source']}, status={entry['status']}, rows={entry['rows']}")
        print()
        return

    # 默认行为：dry-run
    parser.print_help()


if __name__ == "__main__":
    main()
