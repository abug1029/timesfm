"""
Audit 1H vs Daily data alignment for all 20 core futures symbols.
Checks: contract overlap, price alignment, date coverage, volume/OI sanity.
"""
import sqlite3
import os
from collections import defaultdict

# 锚定项目根 db/ 目录 (2026-09-01: 迁移 Linux 后修复 D:/ 残留路径)
_DB_DIR_ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
DB_DIR = os.environ.get("FM_DB_DIR", _DB_DIR_ENV)
SYMBOLS = [
    "AO", "BU", "CF", "CJ", "EG", "FG", "FU", "I", "JD", "JM",
    "LH", "M", "MA", "P", "RB", "SP", "SR", "SS", "TA", "UR",
]

PRICE_MISMATCH_THRESHOLD = 2.0    # %
VOL_UNDER_THRESHOLD = -20.0       # % (1h vol significantly less than daily)


def get_db_path(sym):
    return os.path.join(DB_DIR, f"futures_{sym.lower()}.db")


def audit_symbol(sym):
    """Returns dict with all audit results for one symbol."""
    db_path = get_db_path(sym)
    if not os.path.exists(db_path):
        return {"symbol": sym, "error": f"DB not found: {db_path}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    result = {
        "symbol": sym,
        "error": None,
        "contracts_1d": {},
        "contracts_1h": {},
        "only_in_1d": [],
        "only_in_1h": [],
        "overlap_contracts": [],
        "price_mismatches": [],
        "missing_1h_dates": [],
        "extra_1h_dates": [],
        "vol_mismatches": [],
    }

    # 1. Get contracts and counts
    cur.execute(
        "SELECT contract_code, COUNT(*) as cnt FROM kline_1d GROUP BY contract_code"
    )
    for row in cur.fetchall():
        result["contracts_1d"][row["contract_code"]] = row["cnt"]

    cur.execute(
        "SELECT contract_code, COUNT(*) as cnt FROM kline_1h GROUP BY contract_code"
    )
    for row in cur.fetchall():
        result["contracts_1h"][row["contract_code"]] = row["cnt"]

    set_1d = set(result["contracts_1d"].keys())
    set_1h = set(result["contracts_1h"].keys())
    result["only_in_1d"] = sorted(set_1d - set_1h)
    result["only_in_1h"] = sorted(set_1h - set_1d)
    result["overlap_contracts"] = sorted(set_1d & set_1h)

    # 2. Price alignment + 3. Date coverage + 4. Volume sanity
    for contract in result["overlap_contracts"]:
        # Daily close prices by date
        cur.execute(
            "SELECT dt, close_price FROM kline_1d WHERE contract_code=? ORDER BY dt",
            (contract,),
        )
        daily_by_date = {}
        for r in cur.fetchall():
            daily_by_date[r["dt"]] = r["close_price"]

        # Daily volume by date
        cur.execute(
            "SELECT dt, SUM(volume) as vol FROM kline_1d WHERE contract_code=? GROUP BY dt ORDER BY dt",
            (contract,),
        )
        daily_vol_by_date = {}
        for r in cur.fetchall():
            daily_vol_by_date[r["dt"]] = r["vol"]

        # 1H: last close per date + total volume per date
        cur.execute(
            "SELECT SUBSTR(dt, 1, 10) as date_part, close_price, volume "
            "FROM kline_1h WHERE contract_code=? ORDER BY dt",
            (contract,),
        )
        hourly_rows = cur.fetchall()
        h_dates_seen = set()
        last_close_by_date = {}
        vol_1h_by_date = defaultdict(float)
        for r in hourly_rows:
            d = r["date_part"]
            h_dates_seen.add(d)
            last_close_by_date[d] = r["close_price"]  # ordered, so last wins
            vol_1h_by_date[d] += r["volume"]

        # Price alignment check
        for date_str, d_close in daily_by_date.items():
            if d_close is None or d_close == 0:
                continue
            if date_str in last_close_by_date:
                h_close = last_close_by_date[date_str]
                if h_close is None or h_close == 0:
                    continue
                diff_pct = abs(h_close - d_close) / d_close * 100
                if diff_pct > PRICE_MISMATCH_THRESHOLD:
                    result["price_mismatches"].append(
                        (contract, date_str, d_close, h_close, round(diff_pct, 4))
                    )

        # Date coverage: 1d dates missing from 1h
        for date_str in daily_by_date:
            if date_str not in h_dates_seen:
                result["missing_1h_dates"].append((contract, date_str))

        # Date coverage: 1h dates not in 1d
        for date_str in h_dates_seen:
            if date_str not in daily_by_date:
                result["extra_1h_dates"].append((contract, date_str))

        # Volume sanity: compare 1h total vs daily
        for date_str in daily_by_date:
            dv = daily_vol_by_date.get(date_str, 0)
            hv = vol_1h_by_date.get(date_str, 0)
            if dv and dv > 0:
                diff_pct = (hv - dv) / dv * 100
                if diff_pct < VOL_UNDER_THRESHOLD:
                    result["vol_mismatches"].append(
                        (contract, date_str, int(dv), int(hv), round(diff_pct, 2))
                    )

    conn.close()
    return result


def print_report(all_results):
    """Print structured summary."""
    print("=" * 100)
    print("  1H vs DAILY DATA ALIGNMENT AUDIT REPORT")
    print(f"  Date: 2026-06-27 | Symbols: {len(SYMBOLS)} | DB dir: {DB_DIR}")
    print("=" * 100)

    total_price_mismatches = 0
    total_vol_mismatches = 0
    total_missing_dates = 0
    total_extra_dates = 0
    symbols_with_issues = []

    # --- Section 1: Overview table ---
    print("\n" + "=" * 100)
    print("  SECTION 1: PER-SYMBOL OVERVIEW")
    print("=" * 100)
    header = (
        f"{'Symbol':<8} {'1D Ctrcts':<11} {'1H Ctrcts':<11} "
        f"{'Overlap':<9} {'Only1D':<8} {'Only1H':<8} "
        f"{'PriceMM':<9} {'VolMM':<8} {'MissDt':<8} {'ExtraDt':<8}"
    )
    print(header)
    print("-" * 100)

    for r in all_results:
        sym = r["symbol"]
        if r["error"]:
            print(f"{sym:<8} ERROR: {r['error']}")
            continue
        n1d = len(r["contracts_1d"])
        n1h = len(r["contracts_1h"])
        nov = len(r["overlap_contracts"])
        no1d = len(r["only_in_1d"])
        no1h = len(r["only_in_1h"])
        npm = len(r["price_mismatches"])
        nvm = len(r["vol_mismatches"])
        nmd = len(r["missing_1h_dates"])
        ned = len(r["extra_1h_dates"])
        total_price_mismatches += npm
        total_vol_mismatches += nvm
        total_missing_dates += nmd
        total_extra_dates += ned
        has_issue = npm > 0 or nvm > 0 or nmd > 0 or ned > 0 or no1d > 0 or no1h > 0
        if has_issue:
            symbols_with_issues.append(sym)
        marker = " !" if has_issue else " OK"
        print(
            f"{sym:<8} {n1d:<11} {n1h:<11} {nov:<9} {no1d:<8} {no1h:<8} "
            f"{npm:<9} {nvm:<8} {nmd:<8} {ned:<8}{marker}"
        )

    # --- Section 2: Contract overlap details ---
    print("\n" + "=" * 100)
    print("  SECTION 2: CONTRACT OVERLAY DETAILS")
    print("=" * 100)
    any_overlap_issue = False
    for r in all_results:
        if r["error"]:
            continue
        if r["only_in_1d"] or r["only_in_1h"]:
            any_overlap_issue = True
            sym = r["symbol"]
            if r["only_in_1d"]:
                for c in r["only_in_1d"]:
                    cnt = r["contracts_1d"][c]
                    print(f"  {sym}  {c}  ONLY IN 1D  ({cnt} records)")
            if r["only_in_1h"]:
                for c in r["only_in_1h"]:
                    cnt = r["contracts_1h"][c]
                    print(f"  {sym}  {c}  ONLY IN 1H  ({cnt} records)")
    if not any_overlap_issue:
        print("  All contracts match between 1D and 1H tables.")

    # --- Section 3: Price mismatches ---
    print("\n" + "=" * 100)
    print(f"  SECTION 3: PRICE ALIGNMENT MISMATCHES (>2% threshold)")
    print("=" * 100)
    if total_price_mismatches == 0:
        print("  No price mismatches found.")
    else:
        print(f"  Found {total_price_mismatches} mismatches:\n")
        print(
            f"  {'Symbol':<8} {'Contract':<12} {'Date':<14} "
            f"{'Daily Close':>12} {'1H Last Close':>14} {'Diff %':>10}"
        )
        print("  " + "-" * 75)
        for r in all_results:
            if r["error"]:
                continue
            for contract, date_str, d_close, h_close, diff_pct in r["price_mismatches"]:
                print(
                    f"  {r['symbol']:<8} {contract:<12} {date_str:<14} "
                    f"{d_close:>12.2f} {h_close:>14.2f} {diff_pct:>9.4f}%"
                )

    # --- Section 4: Date coverage ---
    print("\n" + "=" * 100)
    print(f"  SECTION 4: DATE COVERAGE")
    print("=" * 100)
    if total_missing_dates == 0 and total_extra_dates == 0:
        print("  Date coverage is consistent.")
    else:
        if total_missing_dates > 0:
            print(f"\n  1D dates MISSING from 1H ({total_missing_dates} total):")
            shown = 0
            for r in all_results:
                if r["error"]:
                    continue
                for contract, date_str in r["missing_1h_dates"]:
                    if shown < 80:
                        print(f"    {r['symbol']}  {contract}  {date_str}")
                        shown += 1
            if total_missing_dates > 80:
                print(f"    ... and {total_missing_dates - 80} more")
        if total_extra_dates > 0:
            print(f"\n  1H dates NOT in 1D ({total_extra_dates} total):")
            shown = 0
            for r in all_results:
                if r["error"]:
                    continue
                for contract, date_str in r["extra_1h_dates"]:
                    if shown < 80:
                        print(f"    {r['symbol']}  {contract}  {date_str}")
                        shown += 1
            if total_extra_dates > 80:
                print(f"    ... and {total_extra_dates - 80} more")

    # --- Section 5: Volume/OI sanity ---
    print("\n" + "=" * 100)
    print(f"  SECTION 5: VOLUME SANITY (1H total < daily by >20%)")
    print("=" * 100)
    if total_vol_mismatches == 0:
        print("  Volume sanity check passed.")
    else:
        print(f"  Found {total_vol_mismatches} volume mismatches:\n")
        print(
            f"  {'Symbol':<8} {'Contract':<12} {'Date':<14} "
            f"{'Daily Vol':>12} {'1H Total Vol':>14} {'Diff %':>10}"
        )
        print("  " + "-" * 75)
        for r in all_results:
            if r["error"]:
                continue
            for contract, date_str, dv, hv, diff_pct in r["vol_mismatches"]:
                print(
                    f"  {r['symbol']:<8} {contract:<12} {date_str:<14} "
                    f"{dv:>12} {hv:>14} {diff_pct:>9.2f}%"
                )

    # --- Final verdict ---
    print("\n" + "=" * 100)
    print("  FINAL VERDICT")
    print("=" * 100)
    overlap_issues = sum(
        1 for r in all_results
        if not r["error"] and (r["only_in_1d"] or r["only_in_1h"])
    )
    issues = total_price_mismatches + total_vol_mismatches + total_missing_dates + total_extra_dates
    if issues == 0 and overlap_issues == 0:
        print("  PASS - All 20 symbols have clean 1H/daily alignment.")
    else:
        print(f"  ISSUES FOUND:")
        print(f"      Symbols with overlap issues : {overlap_issues}/20")
        print(f"      Symbols with any issue      : {len(symbols_with_issues)}/20  {symbols_with_issues}")
        print(f"      Price mismatches (>2%)      : {total_price_mismatches}")
        print(f"      Volume mismatches (>20% low): {total_vol_mismatches}")
        print(f"      Missing 1H dates            : {total_missing_dates}")
        print(f"      Extra 1H dates (not in 1D)  : {total_extra_dates}")
    print("=" * 100)


if __name__ == "__main__":
    all_results = []
    for sym in SYMBOLS:
        try:
            r = audit_symbol(sym)
        except sqlite3.DatabaseError as e:
            # 损坏库 (AO/UR) 不阻断整体审计
            r = {"symbol": sym, "error": f"DB corrupted: {type(e).__name__}: {e}"}
        all_results.append(r)
    print_report(all_results)
