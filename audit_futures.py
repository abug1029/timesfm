#!/usr/bin/env python3
"""TimesFM Futures Database Comprehensive Audit"""
import sqlite3
import os
from collections import defaultdict
from datetime import datetime
import json

DB_DIR = os.path.expanduser("~/timesfm/db")
SYMBOLS = ["ao", "cf", "cj", "hc", "i", "j", "jd", "jm", "l", "lh", "m", "ni", "ni", "p", "pp", "rb", "ru", "sn", "sr", "ta", "v", "wr", "y", "fg", "eg", "sa", "sp", "ur", "bu"]
# Deduplicate and sort
SYMBOLS = sorted(set(SYMBOLS))

def get_db_path(symbol):
    return os.path.join(DB_DIR, f"futures_{symbol}.db")

def connect(symbol):
    path = get_db_path(symbol)
    if not os.path.exists(path):
        return None, f"DB file missing: {path}"
    return sqlite3.connect(path), None

def audit_all():
    results = {}

    # First, discover all actual DB files
    db_files = sorted([f.replace("futures_", "").replace(".db", "") for f in os.listdir(DB_DIR) if f.startswith("futures_") and f.endswith(".db")])
    symbols = db_files
    print(f"Found {len(symbols)} symbol databases: {symbols}")

    for sym in symbols:
        results[sym] = audit_symbol(sym)

    return results, symbols

def audit_symbol(sym):
    findings = []
    conn, err = connect(sym)
    if err:
        return {"severity": "CRITICAL", "findings": [f"CRITICAL: {err}"], "row_counts": {}}

    cur = conn.cursor()

    # Check tables exist
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]

    row_counts = {}

    # --- DAILY TABLE ---
    if "kline_1d" in tables:
        cur.execute("SELECT COUNT(*) FROM kline_1d")
        cnt = cur.fetchone()[0]
        row_counts["kline_1d"] = cnt

        # Get date range
        cur.execute("SELECT MIN(dt), MAX(dt) FROM kline_1d")
        min_dt, max_dt = cur.fetchone()
        row_counts["d_range"] = f"{min_dt} ~ {max_dt}"

        # Findings
        findings.append(f"INFO: Daily rows={cnt}, range={min_dt} ~ {max_dt}")

        # Check latest date
        if max_dt:
            if sym in ["cj", "jd", "lh", "ur"]:
                expected_latest = "2026-09-07"
            else:
                expected_latest = "2026-09-08"
            if max_dt != expected_latest:
                sev = "HIGH" if max_dt < expected_latest else "INFO"
                findings.append(f"{sev}: Latest daily date={max_dt}, expected={expected_latest}")

        # OHLC consistency
        cur.execute("""
            SELECT COUNT(*) FROM kline_1d
            WHERE high < MAX(open_price, close_price)
               OR low > MIN(open_price, close_price)
               OR open_price <= 0 OR close_price <= 0
               OR high <= 0 OR low <= 0
        """)
        bad_ohlc = cur.fetchone()[0]
        if bad_ohlc > 0:
            findings.append(f"CRITICAL: {bad_ohlc} rows with OHLC inconsistency or non-positive prices")

        # Volume/OI negative
        cur.execute("SELECT COUNT(*) FROM kline_1d WHERE volume < 0 OR open_interest < 0")
        bad_vol = cur.fetchone()[0]
        if bad_vol > 0:
            findings.append(f"CRITICAL: {bad_vol} rows with negative volume or open_interest")

        # Check for large daily moves
        cur.execute("SELECT COUNT(*) FROM kline_1d WHERE change_pct IS NOT NULL AND ABS(change_pct) > 10")
        big_moves = cur.fetchone()[0]
        if big_moves > 0:
            findings.append(f"MEDIUM: {big_moves} days with |change_pct| > 10%")

        # NULL indicator analysis for ma20
        cur.execute("SELECT COUNT(*) FROM kline_1d WHERE ma20 IS NULL")
        null_ma20 = cur.fetchone()[0]
        findings.append(f"INFO: ma20 NULL count={null_ma20} (expected ~19 for warmup)")
        if null_ma20 > 19:
            findings.append(f"HIGH: ma20 has {null_ma20} NULLs, expected ~19 (extra={null_ma20-19})")

        # Check all indicator columns for unexpected NULLs
        indicator_cols = ["ma5","ma10","ma20","ma60","ema12","ema26","macd_dif","macd_dea","macd_bar",
                         "rsi6","rsi12","rsi24","kdj_k","kdj_d","kdj_j","boll_upper","boll_mid","boll_lower",
                         "atr14","cci14"]
        for col in indicator_cols:
            cur.execute(f"SELECT COUNT(*) FROM kline_1d WHERE {col} IS NULL")
            null_cnt = cur.fetchone()[0]
            if null_cnt > 0 and col not in ["ma5"]:  # ma5 can have 4 NULLs
                expected = {"ma5":4,"ma10":9,"ma20":19,"ma60":59,"ema12":11,"ema26":25}.get(col, 0)
                if null_cnt > expected + 2:
                    findings.append(f"HIGH: {col} has {null_cnt} NULLs (expected ~{expected})")

        # Check for NaN/infinite (stored as weird strings or special values)
        cur.execute("""
            SELECT COUNT(*) FROM kline_1d
            WHERE typeof(macd_dif)='text' OR typeof(rsi6)='text' OR typeof(close_price)='text'
        """)
        text_vals = cur.fetchone()[0]
        if text_vals > 0:
            findings.append(f"CRITICAL: {text_vals} rows with text-typed numeric columns")

        # CCL check
        cur.execute("SELECT COUNT(*) FROM kline_1d WHERE ccl_value IS NULL")
        null_ccl = cur.fetchone()[0]
        cur.execute("SELECT DISTINCT ccl_label FROM kline_1d WHERE ccl_label IS NOT NULL")
        ccl_labels = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT MIN(ccl_value), MAX(ccl_value), AVG(ccl_value) FROM kline_1d WHERE ccl_value IS NOT NULL")
        ccl_stats = cur.fetchone()
        findings.append(f"INFO: CCL: NULLs={null_ccl}, labels={ccl_labels}, range=[{ccl_stats[0]}, {ccl_stats[1]}], avg={ccl_stats[2]:.2f}" if ccl_stats[0] else "INFO: CCL: all NULL")

        # updated_at check
        cur.execute("SELECT MAX(updated_at) FROM kline_1d")
        max_upd = cur.fetchone()[0]
        findings.append(f"INFO: Daily updated_at latest={max_upd}")

        # Contract code check
        cur.execute("SELECT DISTINCT contract_code FROM kline_1d ORDER BY contract_code")
        codes = [r[0] for r in cur.fetchall()]
        findings.append(f"INFO: Daily contract codes: {codes[:5]}{'...' if len(codes)>5 else ''}")

        # Gap analysis - check for missing trading days
        cur.execute("SELECT dt FROM kline_1d ORDER BY dt")
        dates = [r[0] for r in cur.fetchall()]
        if len(dates) > 1:
            import datetime as dt_mod
            gaps = []
            for i in range(1, len(dates)):
                d1 = dt_mod.datetime.strptime(dates[i-1], "%Y-%m-%d")
                d2 = dt_mod.datetime.strptime(dates[i], "%Y-%m-%d")
                diff = (d2 - d1).days
                # Allow up to 3 days for weekends, longer for holidays
                if diff > 7:  # Flag gaps > 1 week
                    gaps.append(f"{dates[i-1]} -> {dates[i]} ({diff}d)")
            if gaps:
                findings.append(f"MEDIUM: Daily gaps > 7d: {gaps[:5]}{'...' if len(gaps)>5 else ''}")

        # Check oi_signal values
        cur.execute("SELECT DISTINCT oi_signal FROM kline_1d WHERE oi_signal IS NOT NULL")
        oi_signals = [r[0] for r in cur.fetchall()]

        # ccl_label valid values check
        valid_ccl_labels = {"strong_long", "long", "weak_long", "neutral", "weak_short", "short", "strong_short", None}
        invalid_ccl = [l for l in ccl_labels if l not in valid_ccl_labels]
        if invalid_ccl:
            findings.append(f"HIGH: Invalid ccl_label values: {invalid_ccl}")

    # --- 1H TABLE ---
    if "kline_1h" in tables:
        cur.execute("SELECT COUNT(*) FROM kline_1h")
        cnt = cur.fetchone()[0]
        row_counts["kline_1h"] = cnt

        cur.execute("SELECT MIN(dt), MAX(dt) FROM kline_1h")
        min_dt, max_dt = cur.fetchone()
        row_counts["h_range"] = f"{min_dt} ~ {max_dt}"

        findings.append(f"INFO: 1H rows={cnt}, range={min_dt} ~ {max_dt}")

        # Expected latest
        if sym in ["cj", "jd", "lh", "ur"]:
            expected_latest = "2026-09-07 14:00:00"
        else:
            expected_latest = "2026-09-07 21:00:00"
        if max_dt and max_dt != expected_latest:
            findings.append(f"HIGH: Latest 1H bar={max_dt}, expected={expected_latest}")

        # OHLC consistency
        cur.execute("""
            SELECT COUNT(*) FROM kline_1h
            WHERE high < MAX(open_price, close_price)
               OR low > MIN(open_price, close_price)
               OR open_price <= 0 OR close_price <= 0
        """)
        bad = cur.fetchone()[0]
        if bad > 0:
            findings.append(f"CRITICAL: {bad} 1H rows with OHLC inconsistency")

        # NULL ma20 in 1H
        cur.execute("SELECT COUNT(*) FROM kline_1h WHERE ma20 IS NULL")
        null_ma20 = cur.fetchone()[0]
        findings.append(f"INFO: 1H ma20 NULL count={null_ma20}")

        # CCL
        cur.execute("SELECT DISTINCT ccl_label FROM kline_1h WHERE ccl_label IS NOT NULL")
        ccl_labels = [r[0] for r in cur.fetchall()]
        invalid_ccl = [l for l in ccl_labels if l not in valid_ccl_labels]
        if invalid_ccl:
            findings.append(f"HIGH: Invalid 1H ccl_label values: {invalid_ccl}")

        # updated_at
        cur.execute("SELECT MAX(updated_at) FROM kline_1h")
        max_upd = cur.fetchone()[0]
        findings.append(f"INFO: 1H updated_at latest={max_upd}")

        # Contract code
        cur.execute("SELECT DISTINCT contract_code FROM kline_1h ORDER BY contract_code")
        codes = [r[0] for r in cur.fetchall()]
        findings.append(f"INFO: 1H contract codes: {codes[:5]}{'...' if len(codes)>5 else ''}")

        # Check _MAIN in 1H, _CONT in daily
        has_main = any("_MAIN" in c for c in codes) if codes else False
        has_cont = any("_CONT" in c for c in codes) if codes else False
        if not has_main:
            findings.append(f"MEDIUM: 1H contract codes missing _MAIN suffix")

    # Daily vs 1H alignment
    if "kline_1d" in tables and "kline_1h" in tables:
        cur.execute("SELECT MIN(dt), MAX(dt) FROM kline_1d")
        d_min, d_max = cur.fetchone()
        cur.execute("SELECT MIN(dt), MAX(dt) FROM kline_1h")
        h_min, h_max = cur.fetchone()

        # Check date coverage alignment
        cur.execute("SELECT COUNT(DISTINCT dt) FROM kline_1d")
        num_trading_days = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT SUBSTR(dt,1,10)) FROM kline_1h")
        num_h_days = cur.fetchone()[0]

        findings.append(f"INFO: Alignment: daily has {num_trading_days} distinct dates, 1H covers {num_h_days} distinct dates")

    conn.close()

    # Determine overall severity
    severity = "INFO"
    for f in findings:
        if f.startswith("CRITICAL"):
            severity = "CRITICAL"
            break
        elif f.startswith("HIGH") and severity not in ["CRITICAL"]:
            severity = "HIGH"
        elif f.startswith("MEDIUM") and severity not in ["CRITICAL", "HIGH"]:
            severity = "MEDIUM"

    return {"severity": severity, "findings": findings, "row_counts": row_counts}

def main():
    print("=" * 80)
    print("TIMESFM FUTURES DATABASE AUDIT")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    results, symbols = audit_all()

    print("\n" + "=" * 80)
    print("ROW COUNT SUMMARY")
    print("=" * 80)
    print(f"{'Symbol':<8} {'Daily':>8} {'1H':>8} {'Daily Range':<30} {'1H Range':<30}")
    print("-" * 80)
    for sym in symbols:
        rc = results[sym].get("row_counts", {})
        dr = rc.get("d_range", "N/A")
        hr = rc.get("h_range", "N/A")
        print(f"{sym:<8} {rc.get('kline_1d','N/A'):>8} {rc.get('kline_1h','N/A'):>8} {dr:<30} {hr:<30}")

    print("\n" + "=" * 80)
    print("PER-SYMBOL FINDINGS")
    print("=" * 80)

    all_findings = []
    for sym in symbols:
        r = results[sym]
        sev = r["severity"]
        print(f"\n--- {sym.upper()} [{sev}] ---")
        for f in r["findings"]:
            print(f"  {f}")
            all_findings.append((sym, sev, f))

    # Overall summary
    print("\n" + "=" * 80)
    print("OVERALL AUDIT SUMMARY")
    print("=" * 80)

    crit = sum(1 for _,s,f in all_findings if s == "CRITICAL")
    high = sum(1 for _,s,f in all_findings if s == "HIGH")
    med = sum(1 for _,s,f in all_findings if s == "MEDIUM")
    low = sum(1 for _,s,f in all_findings if s == "LOW")
    info = sum(1 for _,s,f in all_findings if s == "INFO")

    total = len(all_findings)
    health = max(0, 100 - crit*20 - high*10 - med*3 - low*1)

    print(f"Total findings: {total}")
    print(f"  CRITICAL: {crit}")
    print(f"  HIGH:     {high}")
    print(f"  MEDIUM:   {med}")
    print(f"  LOW:      {low}")
    print(f"  INFO:     {info}")
    print(f"\nData Health Score: {health}/100")

    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    rec_num = 1
    # Check for ma20 NULL issues
    ma20_issues = [(s, f) for s, sev, f in all_findings if "ma20" in f.lower() and "NULL" in f]
    if ma20_issues:
        print(f"  {rec_num}. [HIGH] Investigate extra ma20 NULLs on: {', '.join(s for s,_ in ma20_issues)}")
        print(f"     Expected ~19 warmup NULLs; extras suggest NULL propagation from source data.")
        rec_num += 1

    # Check for freshness issues
    freshness_issues = [(s, f) for s, sev, f in all_findings if "Latest" in f and ("expected" in f.lower() or "HIGH" in f)]
    if freshness_issues:
        print(f"  {rec_num}. [HIGH] Re-fetch data for stale symbols: {', '.join(s for s,_ in freshness_issues)}")
        rec_num += 1

    # Check for OHLC issues
    ohlc_issues = [(s, f) for s, sev, f in all_findings if "OHLC" in f or "non-positive" in f.lower()]
    if ohlc_issues:
        print(f"  {rec_num}. [CRITICAL] Fix price data errors in: {', '.join(s for s,_ in ohlc_issues)}")
        rec_num += 1

    # Check for missing DB files
    expected = ["ao","cf","cj","hc","i","j","jd","jm","l","lh","m","ni","p","pp","rb","ru","sn","sr","ta","v","wr","y","fg","eg","sa","sp","ur","bu"]
    actual = symbols
    missing = [s for s in expected if s not in actual]
    extra = [s for s in actual if s not in expected]
    if missing:
        print(f"  {rec_num}. [CRITICAL] Missing DB files for: {missing}")
        rec_num += 1
    if extra:
        print(f"  {rec_num}. [INFO] Extra DB files found: {extra}")
        rec_num += 1

    # CCL issues
    ccl_issues = [(s, f) for s, sev, f in all_findings if "ccl_label" in f.lower() and "Invalid" in f]
    if ccl_issues:
        print(f"  {rec_num}. [HIGH] Fix invalid CCL labels on: {', '.join(s for s,_ in ccl_issues)}")
        rec_num += 1

    print(f"  {rec_num}. [INFO] Overall data quality is {'GOOD' if health >= 80 else 'NEEDS ATTENTION' if health >= 50 else 'POOR'}")

if __name__ == "__main__":
    main()
