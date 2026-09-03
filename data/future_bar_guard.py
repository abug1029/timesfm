"""
幽灵 K 线防护 — 数据层唯一入口。

职责:
  删除 date(dt) > max_allowed_daily_label(now) 的日线/主链/xreg/1H 行。

语义由 data.trading_calendar 提供（会话感知），避免:
  - 周五夜误删「下周一」标签
  - 周六仍保留未完成周一 partial bar

耦合约定:
  - 日线采集成功后的 purge **只**由 scripts/daily_update.py 调用一次
  - data_management --validate 可单独调用本模块做卫生检查
  - 禁止在父进程对 daily_update 再套一层 purge
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from data.config import DB_DIR, FM_ROOT
from data.trading_calendar import max_allowed_daily_label

# 日线相关
_DAILY_TABLES = (
    ("kline_1d", "dt"),
    ("main_continuous_1d", "dt"),
    ("xreg_factors", "dt"),
)
# 1H：同一交易日上界
_H1_TABLES = (("kline_1h", "dt"),)


def _symbol_db_path(symbol: str, db_dir: Optional[Path] = None) -> Path:
    return (db_dir or DB_DIR) / f"futures_{symbol.lower()}.db"


def purge_future_bars(
    symbol: str,
    *,
    db_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    dry_run: bool = False,
    include_1h: bool = True,
) -> dict:
    """
    单品种 purge。

    Returns dict with counts, max_legal, ok, error.
    """
    sym = symbol.lower().strip()
    path = Path(db_path) if db_path else _symbol_db_path(sym)
    legal = max_allowed_daily_label(now)
    legal_s = legal.isoformat()

    out = {
        "symbol": sym,
        "max_legal": legal_s,
        "dry_run": dry_run,
        "kline_1d": 0,
        "main_continuous_1d": 0,
        "xreg_factors": 0,
        "kline_1h": 0,
        "daily_max": None,
        "h1_max": None,
        "ok": True,
        "error": None,
    }
    if not path.exists():
        out["ok"] = True  # 无库不算失败
        out["error"] = "missing_db"
        return out

    tables = list(_DAILY_TABLES) + (list(_H1_TABLES) if include_1h else [])
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        for table, col in tables:
            try:
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE substr({col}, 1, 10) > ?",
                    (legal_s,),
                )
                n = int(cur.fetchone()[0])
            except sqlite3.Error:
                continue
            out[table] = n
            if n and not dry_run:
                cur.execute(
                    f"DELETE FROM {table} WHERE substr({col}, 1, 10) > ?",
                    (legal_s,),
                )
        if not dry_run:
            conn.commit()
        try:
            cur.execute("SELECT max(substr(dt, 1, 10)) FROM kline_1d")
            out["daily_max"] = cur.fetchone()[0]
        except sqlite3.Error:
            pass
        if include_1h:
            try:
                cur.execute("SELECT max(dt) FROM kline_1h")
                out["h1_max"] = cur.fetchone()[0]
            except sqlite3.Error:
                pass
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return out


# 兼容旧名
purge_future_daily_bars = purge_future_bars


def run_guard(
    symbols: Optional[Iterable[str]] = None,
    *,
    db_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
    dry_run: bool = False,
    include_1h: bool = True,
    quiet: bool = False,
) -> dict:
    """
    数据层唯一批量入口。

    Returns:
      {
        ok: bool,  # 全部品种无硬错误
        max_legal: str,
        total_removed: int,
        errors: [{symbol, error}, ...],
        results: [per-symbol dict],
      }
    """
    root = db_dir or DB_DIR
    if symbols is None:
        paths = sorted(root.glob("futures_*.db"))
        syms = [p.stem.replace("futures_", "") for p in paths]
    else:
        syms = [s.lower().strip() for s in symbols if s]

    legal = max_allowed_daily_label(now)
    if not quiet:
        print(
            f"[future_bar_guard] max_allowed_daily_label={legal.isoformat()} "
            f"dry_run={dry_run} include_1h={include_1h} n={len(syms)} "
            f"root={root}"
        )

    results = []
    errors = []
    total = 0
    for sym in syms:
        r = purge_future_bars(
            sym,
            db_path=_symbol_db_path(sym, root),
            now=now,
            dry_run=dry_run,
            include_1h=include_1h,
        )
        results.append(r)
        removed = (
            int(r.get("kline_1d") or 0)
            + int(r.get("main_continuous_1d") or 0)
            + int(r.get("xreg_factors") or 0)
            + int(r.get("kline_1h") or 0)
        )
        total += removed
        if not r.get("ok", True):
            errors.append({"symbol": sym, "error": r.get("error")})
        if removed and not quiet:
            print(
                f"  {sym:4} -k1d={r.get('kline_1d', 0)} "
                f"-main={r.get('main_continuous_1d', 0)} "
                f"-xreg={r.get('xreg_factors', 0)} "
                f"-1h={r.get('kline_1h', 0)} "
                f"→ daily_max={r.get('daily_max')}"
            )

    ok = len(errors) == 0
    if not quiet:
        tag = "would_remove" if dry_run else "removed"
        status = "OK" if ok else f"FAIL errors={len(errors)}"
        print(f"[future_bar_guard] done {tag}={total} {status}")
        for e in errors:
            print(f"  [ERROR] {e['symbol']}: {e['error']}")

    return {
        "ok": ok,
        "max_legal": legal.isoformat(),
        "total_removed": total,
        "errors": errors,
        "results": results,
        "dry_run": dry_run,
        "fm_root": str(FM_ROOT),
    }


# 兼容旧 API
def purge_all_symbols(
    symbols: Optional[Iterable[str]] = None,
    *,
    db_dir: Optional[Path] = None,
    today: Optional[date] = None,
    ahead_days: int = 3,  # deprecated, ignored
    dry_run: bool = False,
    quiet: bool = False,
) -> list[dict]:
    """Deprecated wrapper → run_guard. `today`/`ahead_days` 忽略，改用会话语义。"""
    now = None
    if today is not None:
        now = datetime.combine(today, datetime.min.time().replace(hour=12))
    summary = run_guard(
        symbols, db_dir=db_dir, now=now, dry_run=dry_run, quiet=quiet
    )
    return summary["results"]


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Purge impossible future bars (session-aware)")
    p.add_argument("symbols", nargs="*", help="品种；默认全库")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-1h", action="store_true", help="不清理 kline_1h")
    p.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="覆盖当前时刻 YYYY-MM-DD[THH:MM]（测试用）",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="有错误时 exit 1",
    )
    args = p.parse_args(argv)

    now = None
    if args.as_of:
        s = args.as_of.replace(" ", "T")
        if "T" in s:
            now = datetime.fromisoformat(s)
        else:
            now = datetime.combine(date.fromisoformat(s), datetime.min.time().replace(hour=12))

    summary = run_guard(
        args.symbols or None,
        now=now,
        dry_run=args.dry_run,
        include_1h=not args.no_1h,
        quiet=False,
    )
    if args.strict and not summary["ok"]:
        return 1
    return 0 if summary["ok"] else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
