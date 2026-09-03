"""
Volatility Gating / Vol Circuit Breaker（波动率熔断器）

战略定位（Path 2）:
  - 不是趋势动态路由
  - 预测「未来 24H 高波动」时 veto=True → Neutral Override（压平预测/空仓）
  - 默认 OFF

阈值契约（单一真相）:
  - evaluate() **只读** self.threshold
  - calibrated_thr / operational_thr 是元数据，**从不**在 __init__ 里覆盖 threshold
  - 运行 thr 由 ThrPolicy.resolve() 一次决议后 with_threshold() 写入

用法:
  filt = VolRiskFilter.bind_for_symbol("fu", mode="r1", policy=ThrPolicy(...))
  decision = filt.evaluate(hourly_df)
  if decision.veto:
      pred, quant = apply_neutral_override(pred, base, quant)
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from cascade.regime_features import (
    extract_1h_regime_features,
    EXPECTED_FEATURE_COLUMNS_V2,
    FEATURE_VERSION_V2,
)
from data.config import FM_ROOT, MODELS_DIR, resolve_under_root

DEFAULT_PROB_THRESHOLD = 0.55
ABS_Q = 0.70
HORIZON = 24

# 逻辑名（相对 models/）；运行时一律 resolve_under_root → 绝对路径
DEFAULT_MODEL_PATH = "models/vol_risk_filter_v2.pkl"  # R0
SECTOR_MODEL_PATHS = {
    "energy_chem": "models/vol_risk_filter_chem.pkl",
    "agri": "models/vol_risk_filter_agri.pkl",
    "black_metals": "models/vol_risk_filter_black.pkl",
}
R0_FALLBACK_PATH = DEFAULT_MODEL_PATH
MIN_MODEL_BYTES = 1024  # 拒绝空/半写 pkl

DEFAULT_MAX_BARS_PER_SYMBOL = 2000
DEFAULT_CALIB_QUANTILE = 0.80
DEFAULT_OPERATIONAL_THR_PATH = "models/operational_thr.json"


def model_path_usable(path: str | Path) -> bool:
    """文件存在且非空壳，才视为可用模型。"""
    p = resolve_under_root(path)
    try:
        return p.is_file() and p.stat().st_size >= MIN_MODEL_BYTES
    except OSError:
        return False


@dataclass(frozen=True)
class ResolvedModelPath:
    """模型路径决议结果（路径 + 来源，供审计/绑定）。"""
    path: str
    source: str  # r0 | sector_r1 | r0_fallback_black
    sector: Optional[str] = None


@dataclass
class VolGateDecision:
    enabled: bool
    veto: bool
    vol_prob: float
    threshold: float
    action: str
    message: str
    feature_version: str = FEATURE_VERSION_V2

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def apply_neutral_override(
    point_forecast: np.ndarray,
    base_price: float,
    quantile_forecast: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray | None]:
    """压平预测路径 → delta_pred=0 → 空仓。"""
    horizon = len(point_forecast)
    flat = np.full(horizon, float(base_price), dtype=float)
    q_flat = None
    if quantile_forecast is not None:
        q = np.asarray(quantile_forecast, dtype=float)
        if q.ndim == 2:
            q_flat = np.full_like(q, float(base_price))
        else:
            q_flat = np.full(q.shape, float(base_price))
    return flat, q_flat


def load_operational_thr_map(
    path: str | Path = DEFAULT_OPERATIONAL_THR_PATH,
) -> dict[str, float]:
    """读取 models/operational_thr.json → {sector_key: thr}。文件不存在返回 {}。"""
    import json
    p = resolve_under_root(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    # 允许 short 名
    aliases = {
        "chem": "energy_chem",
        "energy_chem": "energy_chem",
        "agri": "agri",
        "black": "black_metals",
        "black_metals": "black_metals",
    }
    for k, v in (raw or {}).items():
        if k.startswith("_") or k in ("comment", "notes", "source"):
            continue
        key = aliases.get(str(k).lower().strip(), str(k).lower().strip())
        out[key] = float(v)
    return out


@dataclass(frozen=True)
class ThrPolicy:
    """
    运行时阈值决议（单一出口）。

    优先级（硬序）:
      1. global_cli              — --thr
      2. sector_cli[sector]      — --thr-chem / --thr-agri
      3. operational_map[sector] — models/operational_thr.json（业务操作 thr）
      4. operational_thr (pkl)   — pkl 内写入的操作 thr
      5. calibrated_thr          — IS predict_proba 分位（元数据，可能对 OOS 失效）
      6. default                 — DEFAULT_PROB_THRESHOLD
    """
    global_cli: float | None = None
    sector_cli: Mapping[str, float] = field(default_factory=dict)
    operational_map: Mapping[str, float] = field(default_factory=dict)
    default: float = DEFAULT_PROB_THRESHOLD
    allow_calibrated: bool = True
    allow_operational: bool = True

    def resolve(
        self,
        symbol: str,
        *,
        calibrated_thr: float | None,
        operational_thr: float | None,
    ) -> tuple[float, str]:
        from config.sector_map import sector_of

        if self.global_cli is not None:
            return float(self.global_cli), "cli_global"

        sec = sector_of(symbol)
        if sec in self.sector_cli and self.sector_cli[sec] is not None:
            return float(self.sector_cli[sec]), f"cli_sector:{sec}"

        if self.allow_operational and sec in self.operational_map:
            return float(self.operational_map[sec]), f"operational_file:{sec}"

        if self.allow_operational and operational_thr is not None:
            return float(operational_thr), "operational_pkl"

        if self.allow_calibrated and calibrated_thr is not None:
            return float(calibrated_thr), "calibrated_is"

        return float(self.default), "default"

    @staticmethod
    def from_cli(
        thr: float | None = None,
        thr_chem: float | None = None,
        thr_agri: float | None = None,
        *,
        allow_calibrated: bool = True,
        operational_path: str | Path | None = DEFAULT_OPERATIONAL_THR_PATH,
        load_operational_file: bool = True,
    ) -> "ThrPolicy":
        sector_cli: dict[str, float] = {}
        if thr_chem is not None:
            sector_cli["energy_chem"] = float(thr_chem)
        if thr_agri is not None:
            sector_cli["agri"] = float(thr_agri)
        op_map: dict[str, float] = {}
        if load_operational_file and operational_path is not None:
            op_map = load_operational_thr_map(operational_path)
        return ThrPolicy(
            global_cli=float(thr) if thr is not None else None,
            sector_cli=sector_cli,
            operational_map=op_map,
            allow_calibrated=allow_calibrated,
        )


class VolRiskFilter:
    """
    波动率熔断器。

    推理阈值 = self.threshold（唯一）。
    calibrated_thr / operational_thr 仅元数据。
    """

    def __init__(
        self,
        model=None,
        scaler: Optional[StandardScaler] = None,
        feature_columns: Optional[list] = None,
        q_abs: float = 0.0,
        threshold: float = DEFAULT_PROB_THRESHOLD,
        model_path: str = DEFAULT_MODEL_PATH,
        sector: Optional[str] = None,
        train_symbols: Optional[list] = None,
        train_end: Optional[str] = None,
        max_bars_per_symbol: Optional[int] = None,
        n_samples: int = 0,
        n_by_symbol: Optional[dict] = None,
        pos_rate: float = 0.0,
        calibrated_thr: Optional[float] = None,
        operational_thr: Optional[float] = None,
        calib_quantile: float = DEFAULT_CALIB_QUANTILE,
        threshold_source: str = "default",
        model_source: str = "unknown",
        # 兼容旧调用：prob_threshold 仅作 threshold 别名入参
        prob_threshold: Optional[float] = None,
    ):
        self.model = model
        self.scaler = scaler
        self.feature_columns = feature_columns or list(EXPECTED_FEATURE_COLUMNS_V2)
        self.q_abs = float(q_abs)
        # 元数据（不参与 evaluate 决议）
        self.calibrated_thr = (
            float(calibrated_thr) if calibrated_thr is not None else None
        )
        self.operational_thr = (
            float(operational_thr) if operational_thr is not None else None
        )
        self.calib_quantile = float(calib_quantile)
        # 唯一运行时阈值
        if prob_threshold is not None and threshold == DEFAULT_PROB_THRESHOLD:
            threshold = float(prob_threshold)
        self.threshold = float(threshold)
        self.threshold_source = threshold_source
        self.model_path = str(resolve_under_root(model_path))
        self.model_source = model_source  # r0 | sector_r1 | r0_fallback_black | ...
        self.sector = sector
        self.train_symbols = list(train_symbols or [])
        self.train_end = train_end
        self.max_bars_per_symbol = max_bars_per_symbol
        self.n_samples = int(n_samples)
        self.n_by_symbol = dict(n_by_symbol or {})
        self.pos_rate = float(pos_rate)

    # ---- 兼容别名：旧代码读/写 prob_threshold ----
    @property
    def prob_threshold(self) -> float:
        return self.threshold

    @prob_threshold.setter
    def prob_threshold(self, value: float) -> None:
        self.threshold = float(value)
        self.threshold_source = "mutated"

    def with_threshold(self, thr: float, source: str = "cli") -> "VolRiskFilter":
        """设置运行时 threshold，不改动 calibrated/operational 元数据。"""
        self.threshold = float(thr)
        self.threshold_source = source
        return self

    @staticmethod
    def is_enabled(cli_flag: bool = False) -> bool:
        if cli_flag:
            return True
        return os.getenv("FM_VOL_FILTER", "0") == "1"

    def evaluate(self, hourly_df: pd.DataFrame) -> VolGateDecision:
        thr = self.threshold
        if self.model is None or self.scaler is None:
            return VolGateDecision(
                enabled=True,
                veto=False,
                vol_prob=float("nan"),
                threshold=thr,
                action="none",
                message="[Vol Gating] 模型未加载，跳过熔断",
            )

        feats = extract_1h_regime_features(hourly_df, version=FEATURE_VERSION_V2)
        row = feats.iloc[-1]
        if row[self.feature_columns].isna().any():
            return VolGateDecision(
                enabled=True,
                veto=False,
                vol_prob=float("nan"),
                threshold=thr,
                action="none",
                message="[Vol Gating] 特征不足，跳过熔断",
            )

        x = row[self.feature_columns].values.astype(float).reshape(1, -1)
        xs = self.scaler.transform(x)
        proba = float(self.model.predict_proba(xs)[0, 1])
        veto = proba >= thr
        if veto:
            return VolGateDecision(
                enabled=True,
                veto=True,
                vol_prob=proba,
                threshold=thr,
                action="neutral_override",
                message=(
                    f"[RISK] High Volatility Predicted "
                    f"(vol_prob={proba:.2%} >= {thr:.0%} src={self.threshold_source}); "
                    f"Neutral Override → flat forecast / no position"
                ),
            )
        return VolGateDecision(
            enabled=True,
            veto=False,
            vol_prob=proba,
            threshold=thr,
            action="none",
            message=(
                f"[Vol Gating] vol_prob={proba:.2%} < {thr:.0%} "
                f"(src={self.threshold_source}) → keep static scheme"
            ),
        )

    def save(self, path: Optional[str] = None) -> None:
        abs_path = resolve_under_root(path or self.model_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "scaler": self.scaler,
            "feature_columns": self.feature_columns,
            "q_abs": self.q_abs,
            # 持久化：默认运行 thr 快照 + 元数据分列
            "prob_threshold": self.threshold,
            "threshold": self.threshold,
            "feature_version": FEATURE_VERSION_V2,
            "task": "Path2_vol_circuit_breaker",
            "sector": self.sector,
            "train_symbols": self.train_symbols,
            "train_end": self.train_end,
            "max_bars_per_symbol": self.max_bars_per_symbol,
            "n_samples": self.n_samples,
            "n_by_symbol": self.n_by_symbol,
            "pos_rate": self.pos_rate,
            "calibrated_thr": self.calibrated_thr,
            "operational_thr": self.operational_thr,
            "calib_quantile": self.calib_quantile,
            "threshold_source": self.threshold_source,
        }
        with open(abs_path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        self.model_path = str(abs_path)

    @classmethod
    def load(cls, path: str = DEFAULT_MODEL_PATH) -> "VolRiskFilter":
        """
        从 pkl 加载模型与元数据。
        初始 threshold = operational > calibrated > saved threshold > default
        （不含 CLI；CLI 由 ThrPolicy + with_threshold / bind_for_symbol 应用）
        """
        abs_path = resolve_under_root(path)
        if not model_path_usable(abs_path):
            raise FileNotFoundError(
                f"VolRiskFilter model not found or unusable: {abs_path} "
                f"(no silent fallback; train sector model first)"
            )
        with open(abs_path, "rb") as f:
            payload = pickle.load(f)

        cal = payload.get("calibrated_thr")
        op = payload.get("operational_thr")
        saved = payload.get("threshold", payload.get("prob_threshold"))
        if op is not None:
            thr, src = float(op), "operational"
        elif cal is not None:
            thr, src = float(cal), "calibrated_is"
        elif saved is not None:
            thr, src = float(saved), "pkl_saved"
        else:
            thr, src = DEFAULT_PROB_THRESHOLD, "default"

        return cls(
            model=payload["model"],
            scaler=payload["scaler"],
            feature_columns=payload.get("feature_columns"),
            q_abs=payload.get("q_abs", 0.0),
            threshold=thr,
            model_path=str(abs_path),
            sector=payload.get("sector"),
            train_symbols=payload.get("train_symbols"),
            train_end=payload.get("train_end"),
            max_bars_per_symbol=payload.get("max_bars_per_symbol"),
            n_samples=int(payload.get("n_samples") or 0),
            n_by_symbol=payload.get("n_by_symbol"),
            pos_rate=float(payload.get("pos_rate") or 0.0),
            calibrated_thr=float(cal) if cal is not None else None,
            operational_thr=float(op) if op is not None else None,
            calib_quantile=float(
                payload.get("calib_quantile", DEFAULT_CALIB_QUANTILE)
            ),
            threshold_source=src,
            model_source="loaded",
        )

    @staticmethod
    def resolve_model_ref(
        symbol: str,
        mode: str = "r0",
        r0_path: str = DEFAULT_MODEL_PATH,
    ) -> ResolvedModelPath:
        """决议绝对路径 + 来源（单一真相）。"""
        from config.sector_map import sector_of

        mode = (mode or "r0").lower().strip()
        r0_abs = str(resolve_under_root(r0_path or R0_FALLBACK_PATH))

        if mode in ("r0", "global"):
            if not model_path_usable(r0_abs):
                raise FileNotFoundError(f"R0 model unusable: {r0_abs}")
            return ResolvedModelPath(path=r0_abs, source="r0", sector=None)

        if mode not in ("r1", "sector"):
            raise ValueError(f"unknown vol model mode: {mode!r}")

        sec = sector_of(symbol)
        if sec == "other":
            raise KeyError(
                f"symbol {symbol!r} has no sector mapping; "
                f"cannot resolve R1 vol filter"
            )
        rel = SECTOR_MODEL_PATHS.get(sec)
        if not rel:
            raise KeyError(f"no sector model path for sector={sec!r}")
        path_abs = str(resolve_under_root(rel))
        if model_path_usable(path_abs):
            return ResolvedModelPath(path=path_abs, source="sector_r1", sector=sec)

        # black：无独立 R1 pkl 时回落 R0（显式 source，不静默）
        if sec == "black_metals":
            if model_path_usable(r0_abs):
                return ResolvedModelPath(
                    path=r0_abs, source="r0_fallback_black", sector=sec
                )
            raise FileNotFoundError(
                f"R1 black model missing and R0 fallback missing: "
                f"tried {path_abs} and {r0_abs}"
            )
        raise FileNotFoundError(
            f"R1 sector model missing for {symbol} (sector={sec}): {path_abs} "
            f"— run scripts/train_vol_risk_sector.py --sector {sec}"
        )

    @staticmethod
    def resolve_model_path_for_symbol(
        symbol: str,
        mode: str = "r0",
        r0_path: str = DEFAULT_MODEL_PATH,
    ) -> str:
        """兼容旧 API：只返回绝对路径字符串。"""
        return VolRiskFilter.resolve_model_ref(symbol, mode=mode, r0_path=r0_path).path

    @classmethod
    def bind_for_symbol(
        cls,
        symbol: str,
        *,
        mode: str = "r0",
        r0_path: str = DEFAULT_MODEL_PATH,
        policy: ThrPolicy | None = None,
        cache: dict | None = None,
    ) -> "VolRiskFilter":
        """
        解析路径 → load 元数据 → ThrPolicy 一次写入 threshold。
        fullchain / 预测侧应只走此入口。
        """
        policy = policy or ThrPolicy()
        ref = cls.resolve_model_ref(symbol, mode=mode, r0_path=r0_path)
        path = ref.path
        # cache by absolute path
        if cache is not None and path in cache:
            base = cache[path]
        else:
            base = cls.load(path)
            if cache is not None:
                cache[path] = base

        thr, src = policy.resolve(
            symbol,
            calibrated_thr=base.calibrated_thr,
            operational_thr=base.operational_thr,
        )
        bound = cls(
            model=base.model,
            scaler=base.scaler,
            feature_columns=base.feature_columns,
            q_abs=base.q_abs,
            threshold=thr,
            model_path=path,
            sector=base.sector or ref.sector,
            train_symbols=base.train_symbols,
            train_end=base.train_end,
            max_bars_per_symbol=base.max_bars_per_symbol,
            n_samples=base.n_samples,
            n_by_symbol=base.n_by_symbol,
            pos_rate=base.pos_rate,
            calibrated_thr=base.calibrated_thr,
            operational_thr=base.operational_thr,
            calib_quantile=base.calib_quantile,
            threshold_source=src,
            model_source=ref.source,
        )
        return bound

    @classmethod
    def load_or_train(
        cls,
        path: str = DEFAULT_MODEL_PATH,
        symbols: Optional[list] = None,
        train_end: str = "2026-03-31",
        prob_threshold: float = DEFAULT_PROB_THRESHOLD,
        force_retrain: bool = False,
    ) -> "VolRiskFilter":
        """R0 兼容入口。缺文件时训练（非 R1 纪律路径）。"""
        abs_path = str(resolve_under_root(path))
        if not force_retrain and model_path_usable(abs_path):
            filt = cls.load(abs_path)
            if prob_threshold is not None:
                filt.with_threshold(prob_threshold, "cli_load_or_train")
            return filt
        filt = cls.train(
            symbols=symbols,
            train_end=train_end,
            prob_threshold=prob_threshold,
        )
        filt.save(abs_path)
        return filt

    @classmethod
    def train(
        cls,
        symbols: Optional[list] = None,
        train_end: str = "2026-03-31",
        prob_threshold: float = DEFAULT_PROB_THRESHOLD,
        step: int = 6,
        max_bars_per_symbol: Optional[int] = None,
        sector: Optional[str] = None,
        min_samples: int = 200,
        calib_quantile: float = DEFAULT_CALIB_QUANTILE,
        operational_thr: Optional[float] = None,
    ) -> "VolRiskFilter":
        """
        IS 训练 Target-A 波动分类器。

        calibrated_thr = IS predict_proba 的 calib_quantile 分位（元数据）。
        默认运行 threshold：
          operational_thr if set, else calibrated_thr.
        """
        from data.data_store import DataStore

        if symbols is None:
            symbols = ["rb", "i", "jm", "ss", "sr", "fu", "m"]

        train_end_ts = pd.Timestamp(train_end) + pd.Timedelta(hours=23, minutes=59)
        cols = list(EXPECTED_FEATURE_COLUMNS_V2)
        rows = []
        n_by_symbol: dict[str, int] = {}
        bars_used: dict[str, int] = {}

        for sym in symbols:
            sym = sym.lower()
            try:
                with DataStore(sym) as store:
                    df = store.get_main_contract_1h(limit=10**9)
            except Exception as e:
                print(f"[Vol Gating] skip {sym}: load fail {e}")
                continue
            if df is None or df.empty:
                print(f"[Vol Gating] skip {sym}: empty 1H")
                continue
            df = df.copy()
            df["dt"] = pd.to_datetime(df["dt"])
            df = df.sort_values("dt").reset_index(drop=True)
            df = df[df["dt"] <= train_end_ts].reset_index(drop=True)
            if df.empty:
                print(f"[Vol Gating] skip {sym}: no IS bars")
                continue
            if max_bars_per_symbol is not None and len(df) > max_bars_per_symbol:
                df = df.iloc[-int(max_bars_per_symbol):].reset_index(drop=True)
            bars_used[sym] = len(df)

            close = (
                df["close_price"].values.astype(float)
                if "close_price" in df.columns
                else df["close"].values.astype(float)
            )
            feats = extract_1h_regime_features(df, version=FEATURE_VERSION_V2)
            n_sym = 0
            for i in range(0, len(df) - HORIZON, step):
                fr = feats.iloc[i]
                if fr[cols].isna().any():
                    continue
                c0 = close[i]
                if c0 == 0:
                    continue
                abs_move = abs((close[i + HORIZON] - c0) / c0)
                rows.append({
                    **{c: float(fr[c]) for c in cols},
                    "abs_move": abs_move,
                    "symbol": sym,
                })
                n_sym += 1
            n_by_symbol[sym] = n_sym
            print(f"[Vol Gating] {sym}: bars={bars_used[sym]} samples={n_sym}")

        data = pd.DataFrame(rows)
        if len(data) < min_samples:
            raise ValueError(
                f"VolRiskFilter train samples too few: {len(data)} "
                f"(sector={sector}, symbols={symbols}, by_sym={n_by_symbol})"
            )

        q_abs = float(data["abs_move"].quantile(ABS_Q))
        y = (data["abs_move"] >= q_abs).astype(int).values
        X = data[cols].values
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)
        model = RandomForestClassifier(
            n_estimators=300,
            max_depth=6,
            min_samples_leaf=40,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(Xs, y)
        pos_rate = float(y.mean())

        train_proba = model.predict_proba(Xs)[:, 1]
        calibrated_thr = float(np.quantile(train_proba, calib_quantile))
        op = float(operational_thr) if operational_thr is not None else None
        if op is not None:
            run_thr, src = op, "operational"
        else:
            run_thr, src = calibrated_thr, "calibrated_is"

        print(
            f"[Vol Gating] trained sector={sector} n={len(data)} "
            f"q_abs={q_abs:.5f} pos_rate={pos_rate:.1%} "
            f"calibrated_thr(p{int(calib_quantile*100)})={calibrated_thr:.4f} "
            f"runtime_thr={run_thr:.4f}({src}) "
            f"max_bars={max_bars_per_symbol} by_sym={n_by_symbol}"
        )
        print(
            f"[Vol Gating] train_proba: "
            f"min={train_proba.min():.3f} p50={np.median(train_proba):.3f} "
            f"p80={np.quantile(train_proba, 0.8):.3f} "
            f"p90={np.quantile(train_proba, 0.9):.3f} max={train_proba.max():.3f}"
        )
        return cls(
            model=model,
            scaler=scaler,
            feature_columns=cols,
            q_abs=q_abs,
            threshold=run_thr,
            sector=sector,
            train_symbols=[s.lower() for s in symbols],
            train_end=train_end,
            max_bars_per_symbol=max_bars_per_symbol,
            n_samples=len(data),
            n_by_symbol=n_by_symbol,
            pos_rate=pos_rate,
            calibrated_thr=calibrated_thr,
            operational_thr=op,
            calib_quantile=calib_quantile,
            threshold_source=src,
        )
