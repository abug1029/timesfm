import sqlite3, os

os.chdir(os.path.expanduser("~/timesfm"))

header = f"{'symbol':>4} | {'daily_max':12} | {'d_rows':>6} | {'1h_max':18} | {'h_rows':>6}"
print(header)
print("-" * len(header))

for fn in sorted(os.listdir("db")):
    if fn.startswith("futures_") and fn.endswith(".db"):
        sym = fn.replace("futures_", "").replace(".db", "")
        try:
            conn = sqlite3.connect(f"db/{fn}")
            r = conn.execute("SELECT MAX(dt) FROM kline_1d").fetchone()
            r1h = conn.execute("SELECT MAX(dt) FROM kline_1h").fetchone()
            cnt1d = conn.execute("SELECT COUNT(*) FROM kline_1d").fetchone()[0]
            cnt1h = conn.execute("SELECT COUNT(*) FROM kline_1h").fetchone()[0]
            # Check for NULL indicators in recent 30 days
            null_cnt = conn.execute(
                "SELECT COUNT(*) FROM kline_1d WHERE ma20 IS NULL"
            ).fetchone()[0]
            print(
                f"{sym:>4} | {r[0] or 'NULL':12} | {cnt1d:>6} | "
                f"{r1h[0] or 'NULL':18} | {cnt1h:>6} | null_ma20={null_cnt}"
            )
            conn.close()
        except Exception as e:
            print(f"{sym:>4} | ERROR: {e}")
