"""
Live prediction ledger (Phase L) — project-level SQLite.

Separates model decision events from per-symbol market DBs (futures_*.db).
Used by Copilot / cascade for insert; Phase S queries by vol_prob, hour, cov.

MAE formula (locked):
  sign = sign(pred_t24 - base_price); neutral (|ret| < 1e-12) → MAE/MFE NULL
  long:  MAE = max(0, (base - min_low) / base)
         MFE = max(0, (max_high - base) / base)
  short: MAE = max(0, (max_high - base) / base)
         MFE = max(0, (base - min_low) / base)
  over the next `horizon` 1H bars after asof_ts (exclusive of asof bar).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from data.config import FM_ROOT, resolve_under_root

DEFAULT_LEDGER_PATH = "db/live_ledger.db"


def default_ledger_path() -> Path:
    return resolve_under_root(DEFAULT_LEDGER_PATH)


@dataclass
class PredictionRun:
    """One prediction event to insert."""

    symbol: str
    asof_ts: str
    base_price: float
    cov_used: str
    pred_trajectory: Sequence[float]
    source: str = "copilot"
    scheme_type: Optional[str] = None
    daily_slope: Optional[float] = None
    vol_prob: Optional[float] = None
    vol_thr: Optional[float] = None
    vol_high: Optional[bool] = None
    vol_model_source: Optional[str] = None
    p10_trajectory: Optional[Sequence[float]] = None
    p90_trajectory: Optional[Sequence[float]] = None
    xreg_fallback: bool = False
    horizon: Optional[int] = None
    direction: Optional[str] = None
    uuid: Optional[str] = None
    created_at: Optional[str] = None
    extra: dict = field(default_factory=dict)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS prediction_runs (
    uuid                TEXT PRIMARY KEY,
    created_at          TEXT NOT NULL,
    asof_ts             TEXT NOT NULL,
    asof_hour           INTEGER,
    symbol              TEXT NOT NULL,
    source              TEXT NOT NULL,
    cov_used            TEXT,
    scheme_type         TEXT,
    daily_slope         REAL,
    base_price          REAL NOT NULL,
    vol_prob            REAL,
    vol_thr             REAL,
    vol_high            INTEGER,
    vol_model_source    TEXT,
    pred_t1             REAL,
    pred_t4             REAL,
    pred_t12            REAL,
    pred_t24            REAL,
    pred_trajectory     TEXT,
    p10_trajectory      TEXT,
    p90_trajectory      TEXT,
    xreg_fallback       INTEGER DEFAULT 0,
    horizon             INTEGER,
    direction           TEXT,
    actual_t1           REAL,
    actual_t24          REAL,
    dir_correct_t1      INTEGER,
    dir_correct_t24     INTEGER,
    err_t1_pct          REAL,
    err_t24_pct         REAL,
    max_adverse_excursion   REAL,
    max_favorable_excursion REAL,
    backfilled_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_sym_asof ON prediction_runs(symbol, asof_ts);
CREATE INDEX IF NOT EXISTS idx_runs_vol ON prediction_runs(vol_prob);
CREATE INDEX IF NOT EXISTS idx_runs_cov ON prediction_runs(cov_used);
CREATE INDEX IF NOT EXISTS idx_runs_source ON prediction_runs(source);
CREATE INDEX IF NOT EXISTS idx_runs_hour ON prediction_runs(symbol, asof_hour);
"""


def _json_list(xs: Optional[Sequence[float]]) -> Optional[str]:
    if xs is None:
        return None
    out = []
    for x in xs:
        try:
            v = float(x)
            if v != v:  # NaN
                out.append(None)
            else:
                out.append(v)
        except (TypeError, ValueError):
            out.append(None)
    return json.dumps(out, ensure_ascii=False)


def _parse_hour(asof_ts: str) -> Optional[int]:
    s = (asof_ts or "").strip()
    if len(s) >= 13 and s[10] in (" ", "T"):
        try:
            return int(s[11:13])
        except ValueError:
            return None
    return None


def _at(traj: Sequence[float], i: int) -> Optional[float]:
    if not traj:
        return None
    if i < 0 or i >= len(traj):
        return float(traj[-1]) if traj else None
    try:
        v = float(traj[i])
        return None if v != v else v
    except (TypeError, ValueError):
        return None


class LiveLedger:
    """WAL SQLite ledger for prediction runs."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_ledger_path()
        if not self.path.is_absolute():
            self.path = resolve_under_root(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def insert_run(self, run: PredictionRun) -> str:
        """Insert one run; returns uuid."""
        uid = run.uuid or str(uuid.uuid4())
        created = run.created_at or datetime.now().isoformat(timespec="seconds")
        traj = list(run.pred_trajectory or [])
        h = int(run.horizon if run.horizon is not None else (len(traj) or 24))
        asof_hour = _parse_hour(run.asof_ts)
        row = {
            "uuid": uid,
            "created_at": created,
            "asof_ts": str(run.asof_ts),
            "asof_hour": asof_hour,
            "symbol": run.symbol.lower().strip(),
            "source": run.source or "copilot",
            "cov_used": run.cov_used,
            "scheme_type": run.scheme_type,
            "daily_slope": run.daily_slope,
            "base_price": float(run.base_price),
            "vol_prob": run.vol_prob,
            "vol_thr": run.vol_thr,
            "vol_high": (
                None if run.vol_high is None else (1 if run.vol_high else 0)
            ),
            "vol_model_source": run.vol_model_source,
            "pred_t1": _at(traj, 0),
            "pred_t4": _at(traj, 3),
            "pred_t12": _at(traj, 11),
            "pred_t24": _at(traj, h - 1) if h else _at(traj, -1),
            "pred_trajectory": _json_list(traj),
            "p10_trajectory": _json_list(run.p10_trajectory),
            "p90_trajectory": _json_list(run.p90_trajectory),
            "xreg_fallback": 1 if run.xreg_fallback else 0,
            "horizon": h,
            "direction": run.direction,
        }
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO prediction_runs ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )
        return uid

    def get_run(self, uid: str) -> Optional[dict]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM prediction_runs WHERE uuid = ?", (uid,)
            )
            r = cur.fetchone()
            return dict(r) if r else None

    def query(
        self,
        *,
        symbol: Optional[str] = None,
        source: Optional[str] = None,
        cov_used: Optional[str] = None,
        min_vol_prob: Optional[float] = None,
        max_vol_prob: Optional[float] = None,
        hour_min: Optional[int] = None,
        hour_max: Optional[int] = None,
        backfilled_only: bool = False,
        unfilled_only: bool = False,
        limit: int = 500,
    ) -> list[dict]:
        """Phase S-style filters without loading JSON files."""
        clauses: list[str] = []
        params: list[Any] = []
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol.lower().strip())
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if cov_used is not None:
            clauses.append("cov_used = ?")
            params.append(cov_used)
        if min_vol_prob is not None:
            clauses.append("vol_prob >= ?")
            params.append(float(min_vol_prob))
        if max_vol_prob is not None:
            clauses.append("vol_prob <= ?")
            params.append(float(max_vol_prob))
        if hour_min is not None:
            clauses.append("asof_hour >= ?")
            params.append(int(hour_min))
        if hour_max is not None:
            clauses.append("asof_hour <= ?")
            params.append(int(hour_max))
        if backfilled_only:
            clauses.append("actual_t24 IS NOT NULL")
        if unfilled_only:
            clauses.append("actual_t24 IS NULL")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT * FROM prediction_runs{where} "
            f"ORDER BY asof_ts DESC LIMIT ?"
        )
        params.append(int(limit))
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def update_backfill(
        self,
        uid: str,
        *,
        actual_t1: Optional[float] = None,
        actual_t24: Optional[float] = None,
        max_adverse_excursion: Optional[float] = None,
        max_favorable_excursion: Optional[float] = None,
    ) -> bool:
        """Update actuals / errors / direction / MAE for a run. Returns False if missing."""
        run = self.get_run(uid)
        if not run:
            return False
        base = float(run["base_price"])
        pred_t1 = run.get("pred_t1")
        pred_t24 = run.get("pred_t24")

        fields: dict[str, Any] = {
            "backfilled_at": datetime.now().isoformat(timespec="seconds"),
        }
        if actual_t1 is not None and pred_t1 is not None and base:
            fields["actual_t1"] = float(actual_t1)
            fields["err_t1_pct"] = (float(actual_t1) - float(pred_t1)) / base * 100.0
            fields["dir_correct_t1"] = int(
                _dir_correct(base, float(pred_t1), float(actual_t1))
            )
        if actual_t24 is not None and pred_t24 is not None and base:
            fields["actual_t24"] = float(actual_t24)
            fields["err_t24_pct"] = (float(actual_t24) - float(pred_t24)) / base * 100.0
            fields["dir_correct_t24"] = int(
                _dir_correct(base, float(pred_t24), float(actual_t24))
            )
        if max_adverse_excursion is not None:
            fields["max_adverse_excursion"] = float(max_adverse_excursion)
        if max_favorable_excursion is not None:
            fields["max_favorable_excursion"] = float(max_favorable_excursion)

        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE prediction_runs SET {sets} WHERE uuid = ?",
                (*fields.values(), uid),
            )
        return True


def _dir_correct(base: float, pred: float, actual: float) -> bool:
    pred_dir = 1 if pred > base else (-1 if pred < base else 0)
    act_dir = 1 if actual > base else (-1 if actual < base else 0)
    if pred_dir == 0:
        return act_dir == 0
    return pred_dir == act_dir


def compute_excursions(
    base: float,
    pred_t24: float,
    highs: Sequence[float],
    lows: Sequence[float],
) -> tuple[Optional[float], Optional[float]]:
    """MAE / MFE over path highs/lows. See module docstring."""
    if not highs or not lows or base == 0:
        return None, None
    edge = pred_t24 - base
    if abs(edge) < 1e-12:
        return None, None
    min_low = float(min(lows))
    max_high = float(max(highs))
    if edge > 0:  # long
        mae = max(0.0, (base - min_low) / base)
        mfe = max(0.0, (max_high - base) / base)
    else:
        mae = max(0.0, (max_high - base) / base)
        mfe = max(0.0, (base - min_low) / base)
    return mae, mfe


def backfill_run_from_1h(
    ledger: LiveLedger,
    uid: str,
    *,
    bars: Optional[list[dict]] = None,
    symbol: Optional[str] = None,
) -> dict:
    """
    Backfill actuals from 1H bars after asof_ts.

    bars: optional list of {dt, high, low, close_price} sorted ascending.
    If bars is None, loads from DataStore for the run's symbol.
    Does not invent prices: if insufficient bars, leaves NULLs (except partial t1 if available).
    """
    run = ledger.get_run(uid)
    if not run:
        return {"ok": False, "error": "missing_uuid", "uuid": uid}

    asof = str(run["asof_ts"])
    h = int(run.get("horizon") or 24)
    base = float(run["base_price"])
    pred_t24 = run.get("pred_t24")
    if pred_t24 is None:
        return {"ok": False, "error": "missing_pred_t24", "uuid": uid}

    if bars is None:
        bars = _load_1h_bars_after(run["symbol"], asof, h)
    else:
        # filter to after asof
        bars = [b for b in bars if str(b.get("dt", "")) > asof][:h]

    if not bars:
        return {
            "ok": True,
            "uuid": uid,
            "filled": False,
            "reason": "no_bars_after_asof",
        }

    actual_t1 = float(bars[0]["close_price"]) if bars else None
    actual_t24 = float(bars[h - 1]["close_price"]) if len(bars) >= h else None
    highs = [float(b["high"]) for b in bars if b.get("high") is not None]
    lows = [float(b["low"]) for b in bars if b.get("low") is not None]
    # if only close available in fixture
    if not highs:
        highs = [float(b["close_price"]) for b in bars]
    if not lows:
        lows = [float(b["close_price"]) for b in bars]

    mae, mfe = (None, None)
    if actual_t24 is not None:
        mae, mfe = compute_excursions(base, float(pred_t24), highs, lows)

    ledger.update_backfill(
        uid,
        actual_t1=actual_t1,
        actual_t24=actual_t24,
        max_adverse_excursion=mae if actual_t24 is not None else None,
        max_favorable_excursion=mfe if actual_t24 is not None else None,
    )
    return {
        "ok": True,
        "uuid": uid,
        "filled": actual_t24 is not None,
        "n_bars": len(bars),
        "actual_t1": actual_t1,
        "actual_t24": actual_t24,
        "mae": mae,
        "mfe": mfe,
    }


def _load_1h_bars_after(symbol: str, asof: str, horizon: int) -> list[dict]:
    """Read kline_1h from per-symbol market DB (read-only path)."""
    import sqlite3
    from data.config import get_db_path

    db_path = get_db_path(symbol)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # prefer MAIN continuous
        cur = conn.execute(
            """
            SELECT dt, high, low, close_price FROM kline_1h
            WHERE contract_code LIKE '%_MAIN' AND dt > ?
            ORDER BY dt ASC LIMIT ?
            """,
            (asof, horizon),
        )
        rows = cur.fetchall()
        if not rows:
            cur = conn.execute(
                """
                SELECT dt, high, low, close_price FROM kline_1h
                WHERE dt > ? ORDER BY dt ASC LIMIT ?
                """,
                (asof, horizon),
            )
            rows = cur.fetchall()
        return [
            {"dt": r[0], "high": r[1], "low": r[2], "close_price": r[3]}
            for r in rows
        ]
    finally:
        conn.close()


def insert_from_copilot_card(card: Any, *, ledger: Optional[LiveLedger] = None) -> str:
    """
    Shared write path for Copilot (and tests).

    card: CopilotCard-like with attributes used below.
    """
    led = ledger or LiveLedger()
    vol = getattr(card, "vol", None) or {}
    traj = list(getattr(card, "point_forecast", None) or [])
    p10 = list(getattr(card, "p10", None) or [])
    p90 = list(getattr(card, "p90", None) or [])
    # CopilotCard.daily_slope is %/bar (horizon_slope * 100); ledger stores fraction
    slope = getattr(card, "daily_slope", None)
    slope_f = (float(slope) / 100.0) if slope is not None else None

    run = PredictionRun(
        symbol=getattr(card, "symbol"),
        asof_ts=str(getattr(card, "last_1h_dt") or datetime.now().strftime("%Y-%m-%d %H:%M")),
        base_price=float(getattr(card, "current_price") or 0.0),
        cov_used=str(getattr(card, "cov_label") or ""),
        pred_trajectory=traj,
        source="copilot",
        scheme_type=getattr(card, "scheme_type", None),
        daily_slope=slope_f,
        vol_prob=vol.get("vol_prob"),
        vol_thr=vol.get("threshold"),
        vol_high=bool(vol.get("high_vol")) if vol.get("vol_prob") is not None else None,
        vol_model_source=vol.get("model_source") or vol.get("threshold_source"),
        p10_trajectory=p10 if p10 else None,
        p90_trajectory=p90 if p90 else None,
        xreg_fallback=bool(getattr(card, "xreg_fallback", False)),
        horizon=len(traj) or 24,
        direction=getattr(card, "direction", None),
    )
    return led.insert_run(run)


def health_stats(
    ledger: Optional[LiveLedger] = None,
    *,
    min_vol_prob: Optional[float] = None,
    source: Optional[str] = "copilot",
) -> list[dict]:
    """
    Minimal Phase S helper: per-symbol stats for candidates-ready summary.
    """
    led = ledger or LiveLedger()
    clauses = ["actual_t24 IS NOT NULL"]
    params: list[Any] = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if min_vol_prob is not None:
        clauses.append("vol_prob >= ?")
        params.append(float(min_vol_prob))
    where = " AND ".join(clauses)
    sql = f"""
        SELECT
            symbol,
            cov_used,
            COUNT(*) AS n,
            AVG(dir_correct_t24) AS diracc_t24,
            AVG(ABS(err_t24_pct)) AS mae_t24_pct,
            AVG(max_adverse_excursion) AS mean_mae,
            AVG(vol_prob) AS mean_vol_prob
        FROM prediction_runs
        WHERE {where}
        GROUP BY symbol, cov_used
        ORDER BY n DESC
    """
    with led._connect() as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def export_candidates(
    ledger: Optional[LiveLedger] = None,
    *,
    max_diracc: float = 0.50,
    min_n: int = 3,
) -> list[dict]:
    """Symbols/cov with weak live diracc → scan queue candidates."""
    rows = health_stats(ledger, min_vol_prob=None, source=None)
    out = []
    for r in rows:
        n = int(r.get("n") or 0)
        da = r.get("diracc_t24")
        if n < min_n or da is None:
            continue
        if float(da) <= max_diracc:
            out.append(
                {
                    "symbol": r["symbol"],
                    "cov_used": r["cov_used"],
                    "n": n,
                    "diracc_t24": float(da),
                    "mae_t24_pct": r.get("mae_t24_pct"),
                    "reason": "live_diracc_weak",
                }
            )
    return out
