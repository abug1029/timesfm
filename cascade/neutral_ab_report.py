"""
Neutral Overlay A/B — 唯一评分 / 门禁 / 报告写出层。

fullchain 跑完后、rebuild 从 by_symbol 恢复时，都必须走本模块。
禁止在脚本内复制第二套 HELPS/R1/production_gate 逻辑。

主裁决指标: EV / MaxDD / NetPnL（非 mean PF）。
生产默认: OFF。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from config.sector_map import (
    agri_symbols,
    black_symbols,
    chem_symbols,
    sector_of,
)
from cascade.neutral_ab_render import render_markdown

# VolRisk R0 训练池（与 models/vol_risk_filter_v2.pkl 对齐）
TRAIN_POOL: frozenset[str] = frozenset({"rb", "i", "jm", "ss", "sr", "fu", "m"})

# Domain-shift: 严格极端 = 几乎从不熔断 或 几乎全熔断
VETO_NEAR_ZERO = 0.01
VETO_NEAR_ALL = 0.99
VETO_SOFT_HIGH = 0.80
# 非黑色系严格极端超过此数 → 触发 R1
R1_EXTREME_THRESHOLD = 4

# 行级判定数值容差
_EPS = 1e-9


@dataclass(frozen=True)
class VerdictPolicy:
    """工程裁决门槛（可配置，默认偏严）。"""
    min_helps: int = 1
    min_risk_cut: int = 1
    # 宇宙内若包含 FU/SR，对应 smoke 必须通过才能 PASS_NEUTRAL_OVERLAY
    require_present_smoke: bool = True
    # PASS_NEUTRAL_OVERLAY 还要求 MaxDD 改善或至少有 HELPS
    require_dd_or_helps: bool = True


DEFAULT_VERDICT_POLICY = VerdictPolicy()


# ---------------------------------------------------------------------------
# Atomic IO
# ---------------------------------------------------------------------------

def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def atomic_write_json(path: Path | str, payload: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
    )


# ---------------------------------------------------------------------------
# Row-level scoring (single taxonomy)
# ---------------------------------------------------------------------------

def _metrics(block: dict) -> dict:
    return block.get("metrics") or {}


def n_active_from_points(points: Sequence[dict] | None) -> int:
    if not points:
        return 0
    return sum(
        1 for p in points
        if "error" not in p and abs(float(p.get("delta_pred", 0.0) or 0.0)) > _EPS
    )


def classify_row(ev_off: float, ev_on: float, dd_off: float, dd_on: float) -> str:
    """
    唯一行级标签（主看 EV + MaxDD）:
      HELPS   — EV↑ 且 MaxDD 不恶化
      MIXED   — EV↓ 但 MaxDD 改善（常见：误杀盈利但降风险）
      HURTS   — EV↓ 且 MaxDD 未改善
      NEUTRAL — EV/MaxDD 实质不变
    """
    d_ev = float(ev_on) - float(ev_off)
    dd_off_f, dd_on_f = float(dd_off), float(dd_on)
    if abs(d_ev) <= _EPS and abs(dd_on_f - dd_off_f) <= _EPS:
        return "NEUTRAL"
    if d_ev > _EPS and dd_on_f >= dd_off_f - _EPS:
        return "HELPS"
    if d_ev < -_EPS and dd_on_f > dd_off_f + _EPS:
        return "MIXED"
    if d_ev < -_EPS:
        return "HURTS"
    if d_ev > _EPS:
        return "HELPS"  # EV↑ 但 DD 略差 — 仍标 HELPS，用 dd_up=False 区分
    return "NEUTRAL"


def compare_modes(off: dict, on: dict) -> dict:
    """
    OFF vs Neutral 的 deltas + 布尔旗标。
    与 classify_row 对齐：不单独搞第二套 HELPS 语义。
    """
    m0, m1 = _metrics(off), _metrics(on)
    points_on = on.get("points") or []
    n_active = n_active_from_points(points_on)

    ev0 = float(m0.get("EV", 0.0))
    ev1 = float(m1.get("EV", 0.0))
    dd0 = float(m0.get("MaxDD", 0.0))
    dd1 = float(m1.get("MaxDD", 0.0))
    pnl0 = float(m0.get("NetPnL", 0.0))
    pnl1 = float(m1.get("NetPnL", 0.0))
    tag = classify_row(ev0, ev1, dd0, dd1)

    # 全空仓切断亏损 = risk_cut
    risk_cut = (n_active == 0 and ev0 < -_EPS) or (
        ev1 >= ev0 - _EPS
        and abs(dd1) <= abs(dd0) + _EPS
        and pnl1 >= pnl0 - 1e-6
    )

    return {
        "tag": tag,
        "delta_PF": float(m1.get("PF", 0.0)) - float(m0.get("PF", 0.0)),
        "delta_EV": ev1 - ev0,
        "delta_MaxDD": dd1 - dd0,
        "delta_NetPnL": pnl1 - pnl0,
        "ev_improved": ev1 > ev0 + _EPS,
        "maxdd_improved": abs(dd1) < abs(dd0) - _EPS or (
            n_active == 0 and dd0 < -_EPS
        ),
        "risk_cut": risk_cut,
        "n_active_on": n_active,
    }


# ---------------------------------------------------------------------------
# Universe scoring
# ---------------------------------------------------------------------------

@dataclass
class SmokeCheck:
    fu_ok: bool = False
    sr_identical: bool = False
    fu: dict = field(default_factory=dict)
    sr: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class UniverseScore:
    symbols: list[str]
    rows: list[dict]
    pool_off: dict
    pool_on: dict
    counts: dict
    domain: dict
    smoke: SmokeCheck
    engineering_verdict: str
    production_gate: str
    gate_reasons: list[str]
    whitelist: list[str]
    verdict_parts: list[str]
    compare: dict
    domain_warns: dict
    meta: dict = field(default_factory=dict)


def pool_metrics(results_mode: dict[str, dict], symbols: Sequence[str]) -> dict:
    pfs, evs, dds, pnls = [], [], [], []
    for s in symbols:
        if s not in results_mode:
            continue
        m = _metrics(results_mode[s])
        pfs.append(float(m.get("PF", 0.0)))
        evs.append(float(m.get("EV", 0.0)))
        dds.append(float(m.get("MaxDD", 0.0)))
        pnls.append(float(m.get("NetPnL", 0.0)))
    n = len(evs) or 1
    return {
        "mean_PF": sum(pfs) / n if pfs else 0.0,
        "mean_EV": sum(evs) / n if evs else 0.0,
        "mean_MaxDD": sum(dds) / n if dds else 0.0,
        "sum_NetPnL": sum(pnls),
        "n_symbols": len(evs),
    }


def _smoke_checks(rows: list[dict]) -> SmokeCheck:
    by = {r["sym"]: r for r in rows}
    sc = SmokeCheck()
    if "fu" in by:
        fu = by["fu"]
        sc.fu = {
            "ev_off": fu["ev_off"], "ev_on": fu["ev_on"],
            "dd_off": fu["dd_off"], "dd_on": fu["dd_on"],
            "pnl_off": fu["pnl_off"], "pnl_on": fu["pnl_on"],
            "veto": fu["veto"],
        }
        sc.fu_ok = (
            abs(fu["pnl_on"]) < 1e-9
            and fu["veto"] >= VETO_NEAR_ALL
            and fu["dd_on"] >= fu["dd_off"] - 1e-12
        )
        sc.notes.append(
            f"FU NetPnL_on={fu['pnl_on']} veto={fu['veto']:.0%} "
            f"MaxDD {fu['dd_off']:.4f}→{fu['dd_on']:.4f} → "
            f"{'PASS' if sc.fu_ok else 'FAIL'}"
        )
    else:
        sc.notes.append("FU not in universe — smoke skipped")

    if "sr" in by:
        sr = by["sr"]
        sc.sr = {
            "ev_off": sr["ev_off"], "ev_on": sr["ev_on"],
            "dd_off": sr["dd_off"], "dd_on": sr["dd_on"],
            "pnl_off": sr["pnl_off"], "pnl_on": sr["pnl_on"],
            "veto": sr["veto"],
        }
        sc.sr_identical = (
            abs(sr["ev_off"] - sr["ev_on"]) < 1e-9
            and abs(sr["dd_off"] - sr["dd_on"]) < 1e-9
            and abs(sr["pnl_off"] - sr["pnl_on"]) < 1e-9
            and sr["veto"] < VETO_NEAR_ZERO + 1e-12
        )
        sc.notes.append(
            f"SR OFF≡ON veto={sr['veto']:.0%} → "
            f"{'PASS' if sc.sr_identical else 'FAIL'}"
        )
    else:
        sc.notes.append("SR not in universe — smoke skipped")
    return sc


def decide_production_gate(
    *,
    r1_trigger: bool,
    n_helps: int,
    n_hurts: int,
    n_ev_up: int,
    n_dd_up: int,
    n_rows: int,
    delta_ev: float,
    whitelist: list[str],
    chem_ext: list[str],
    agri_ext: list[str],
) -> tuple[str, list[str]]:
    """
    单一出口优先级（硬序）:
      1. R1 domain-shift 触发 → REMAIN_OFF
      2. 多数 EV↑ 且 多数 MaxDD↑ 且 ΔEV>0 → ALLOW_DEFAULT_ON_L1
      3. 有实质 HELPS 白名单 → WHITELIST_ONLY
      4. 否则 → REMAIN_OFF
    """
    reasons: list[str] = []
    half = (n_rows + 1) // 2

    if r1_trigger:
        reasons.append(
            f"R1 触发：非黑色系极端 veto(0%|{VETO_NEAR_ALL:.0%}) "
            f"> {R1_EXTREME_THRESHOLD}"
        )
        if chem_ext or agri_ext:
            reasons.append(
                f"建议先 R1：chem 极端={chem_ext} agri 极端={agri_ext}"
            )
        return "REMAIN_OFF", reasons

    if n_ev_up >= half and n_dd_up >= half and delta_ev > 0:
        reasons.append("多数品种 EV↑ 且 MaxDD↑，宇宙 ΔEV>0")
        return "ALLOW_DEFAULT_ON_L1", reasons

    if whitelist and n_helps >= 1:
        reasons.append(
            "可白名单 HELPS: " + ",".join(s.upper() for s in whitelist)
        )
        if n_hurts > n_helps:
            reasons.append(f"HURTS({n_hurts}) > HELPS({n_helps}) — 仅白名单")
        return "WHITELIST_ONLY", reasons

    if delta_ev < 0:
        reasons.append(f"宇宙 ΔEV={delta_ev:+.3f} 未改善")
    if n_hurts > n_helps:
        reasons.append(f"HURTS({n_hurts}) > HELPS({n_helps})")
    reasons.append("默认保持生产 OFF")
    return "REMAIN_OFF", reasons


def decide_engineering_verdict(
    *,
    n_helps: int,
    n_mixed: int,
    n_hurts: int,
    n_ev_up: int,
    n_dd_up: int,
    n_rows: int,
    delta_ev: float,
    delta_dd: float,
    risk_cut_count: int,
    smoke: SmokeCheck,
    policy: VerdictPolicy = DEFAULT_VERDICT_POLICY,
) -> tuple[str, list[str]]:
    """
    工程裁决（机制是否工作），与 production_gate 分离。

    PASS_NEUTRAL_OVERLAY 门槛（默认）:
      - risk_cut >= min_risk_cut 或 HELPS >= min_helps
      - 且 (ΔMaxDD>0 或 HELPS>=1) 当 require_dd_or_helps
      - 且 宇宙内若测了 FU/SR，对应 smoke 必须 PASS（require_present_smoke）
    不再允许「仅 fu_ok」单独抬升为 PASS。
    """
    parts: list[str] = []
    half = (n_rows + 1) // 2 if n_rows else 0

    if n_rows == 0:
        return "FAIL_OR_NO_GAIN", ["无有效品种结果"]

    smoke_blockers: list[str] = []
    if policy.require_present_smoke:
        if smoke.fu and not smoke.fu_ok:
            smoke_blockers.append("S2 FU smoke FAIL")
        if smoke.sr and not smoke.sr_identical:
            smoke_blockers.append("S2 SR smoke FAIL")

    if n_ev_up >= half and n_dd_up >= half and delta_ev > 0:
        if smoke_blockers:
            parts.extend(smoke_blockers)
            parts.append("宇宙 EV/DD 多数改善，但 smoke 失败 → 降级 MIXED")
            return "MIXED", parts
        parts.append("多数品种 EV↑ 且 MaxDD↑")
        return "PASS_FULLCHAIN", parts

    mechanism_ok = (
        risk_cut_count >= policy.min_risk_cut
        or n_helps >= policy.min_helps
    )
    dd_or_helps_ok = (
        (not policy.require_dd_or_helps)
        or delta_dd > 0
        or n_helps >= policy.min_helps
    )

    if mechanism_ok and dd_or_helps_ok and not smoke_blockers:
        parts.append(
            f"Neutral 机制有效（risk_cut≥{policy.min_risk_cut} 或 "
            f"HELPS≥{policy.min_helps}）"
        )
        if delta_ev <= 0:
            parts.append(f"宇宙 ΔEV={delta_ev:+.3f} 未全面增利（风控优先）")
        if smoke.fu_ok:
            parts.append("S2: FU 全熔断减亏 PASS")
        if smoke.sr_identical:
            parts.append("S2: SR OFF≡ON PASS")
        return "PASS_NEUTRAL_OVERLAY", parts

    if smoke_blockers:
        parts.extend(smoke_blockers)

    if n_helps >= 1 or n_mixed >= 1:
        parts.append("部分品种改善，未形成宇宙级优势")
        return "MIXED", parts

    parts.append("全链路未观察到可复用改善")
    return "FAIL_OR_NO_GAIN", parts


def score_universe(
    symbols: Sequence[str],
    results: dict,
    meta: dict | None = None,
) -> UniverseScore:
    """
    results 结构:
      {
        "off": {sym: {metrics, cov_label, veto_rate, points?, spike_stats?, ...}},
        "neutral": {...},
        "domain_warns": {sym: str},  # optional
      }
    """
    meta = dict(meta or {})
    off_all = results.get("off") or {}
    neu_all = results.get("neutral") or {}
    domain_warns = dict(results.get("domain_warns") or {})

    symbols = [s.lower() for s in symbols if s.lower() in off_all and s.lower() in neu_all]
    compare: dict[str, dict] = {}
    rows: list[dict] = []

    for sym in symbols:
        off, neu = off_all[sym], neu_all[sym]
        c = compare_modes(off, neu)
        compare[sym] = c
        mo, mn = _metrics(off), _metrics(neu)
        veto = float(neu.get("veto_rate") if neu.get("veto_rate") is not None else 0.0)
        warn = domain_warns.get(sym) or ""
        if not warn:
            if veto <= VETO_NEAR_ZERO:
                warn = "VETO_NEAR_ZERO — 可能分布漂移（阈值难触发）"
            elif veto >= VETO_NEAR_ALL:
                warn = "VETO_NEAR_ALL — 可能分布漂移（过度熔断）"
            if warn:
                domain_warns[sym] = warn

        rows.append({
            "sym": sym,
            "sector": sector_of(sym),
            "cov": off.get("cov_label"),
            "n": off.get("n_eval") or mo.get("n"),
            "veto": veto,
            "ev_off": float(mo.get("EV", 0.0)),
            "ev_on": float(mn.get("EV", 0.0)),
            "dd_off": float(mo.get("MaxDD", 0.0)),
            "dd_on": float(mn.get("MaxDD", 0.0)),
            "pnl_off": float(mo.get("NetPnL", 0.0)),
            "pnl_on": float(mn.get("NetPnL", 0.0)),
            "pf_off": float(mo.get("PF", 0.0)),
            "pf_on": float(mn.get("PF", 0.0)),
            "tag": c["tag"],
            "warn": warn,
            "ev_up": c["ev_improved"],
            "dd_up": c["maxdd_improved"],
            "risk_cut": c["risk_cut"],
        })

    pool_off = pool_metrics(off_all, symbols)
    pool_on = pool_metrics(neu_all, symbols)
    delta_ev = pool_on["mean_EV"] - pool_off["mean_EV"]
    delta_dd = pool_on["mean_MaxDD"] - pool_off["mean_MaxDD"]
    delta_pnl = pool_on["sum_NetPnL"] - pool_off["sum_NetPnL"]

    n_helps = sum(1 for r in rows if r["tag"] == "HELPS")
    n_hurts = sum(1 for r in rows if r["tag"] == "HURTS")
    n_mixed = sum(1 for r in rows if r["tag"] == "MIXED")
    n_neutral = sum(1 for r in rows if r["tag"] == "NEUTRAL")
    n_ev_up = sum(1 for r in rows if r["ev_up"])
    n_dd_up = sum(1 for r in rows if r["dd_up"])
    n_risk = sum(1 for r in rows if r["risk_cut"])

    black = black_symbols()
    chem = chem_symbols()
    agri = agri_symbols()

    extreme_strict = [
        r for r in rows
        if r["sym"] not in black
        and (r["veto"] <= VETO_NEAR_ZERO or r["veto"] >= VETO_NEAR_ALL)
    ]
    extreme_soft = [
        r for r in rows
        if r["sym"] not in black
        and (r["veto"] <= VETO_NEAR_ZERO or r["veto"] >= VETO_SOFT_HIGH)
    ]
    r1_trigger = len(extreme_strict) > R1_EXTREME_THRESHOLD
    chem_ext = [r["sym"] for r in extreme_strict if r["sym"] in chem]
    agri_ext = [r["sym"] for r in extreme_strict if r["sym"] in agri]

    whitelist = [
        r["sym"] for r in rows
        if r["tag"] == "HELPS" and (r["ev_on"] - r["ev_off"]) > 1.0
    ]

    smoke = _smoke_checks(rows)

    gate, gate_reasons = decide_production_gate(
        r1_trigger=r1_trigger,
        n_helps=n_helps,
        n_hurts=n_hurts,
        n_ev_up=n_ev_up,
        n_dd_up=n_dd_up,
        n_rows=len(rows),
        delta_ev=delta_ev,
        whitelist=whitelist,
        chem_ext=chem_ext,
        agri_ext=agri_ext,
    )

    eng, eng_parts = decide_engineering_verdict(
        n_helps=n_helps,
        n_mixed=n_mixed,
        n_hurts=n_hurts,
        n_ev_up=n_ev_up,
        n_dd_up=n_dd_up,
        n_rows=len(rows),
        delta_ev=delta_ev,
        delta_dd=delta_dd,
        risk_cut_count=n_risk,
        smoke=smoke,
    )

    domain = {
        "extreme_strict_non_black": [
            {"sym": r["sym"], "veto": r["veto"], "sector": r["sector"]}
            for r in extreme_strict
        ],
        "extreme_soft_non_black": [
            {"sym": r["sym"], "veto": r["veto"], "sector": r["sector"]}
            for r in extreme_soft
        ],
        "r1_trigger": r1_trigger,
        "r1_threshold": R1_EXTREME_THRESHOLD,
        "chem_extremes": chem_ext,
        "agri_extremes": agri_ext,
        "train_pool_extremes": [
            r["sym"] for r in extreme_strict if r["sym"] in TRAIN_POOL
        ],
    }

    return UniverseScore(
        symbols=list(symbols),
        rows=rows,
        pool_off=pool_off,
        pool_on=pool_on,
        counts={
            "HELPS": n_helps,
            "MIXED": n_mixed,
            "HURTS": n_hurts,
            "NEUTRAL": n_neutral,
            "ev_up": n_ev_up,
            "dd_up": n_dd_up,
            "risk_cut": n_risk,
            "delta_EV": delta_ev,
            "delta_MaxDD": delta_dd,
            "delta_sum_NetPnL": delta_pnl,
            "delta_mean_PF": pool_on["mean_PF"] - pool_off["mean_PF"],
        },
        domain=domain,
        smoke=smoke,
        engineering_verdict=eng,
        production_gate=gate,
        gate_reasons=gate_reasons,
        whitelist=whitelist,
        verdict_parts=eng_parts,
        compare=compare,
        domain_warns=domain_warns,
        meta=meta,
    )


# ---------------------------------------------------------------------------
# Load from by_symbol artifacts
# ---------------------------------------------------------------------------

def load_results_from_by_symbol(
    by_dir: Path | str,
    symbols: Sequence[str] | None = None,
) -> tuple[list[str], dict]:
    by_dir = Path(by_dir)
    if symbols is None:
        symbols = sorted(p.stem.lower() for p in by_dir.glob("*.json"))
    else:
        symbols = [s.lower() for s in symbols]

    results: dict = {"off": {}, "neutral": {}, "domain_warns": {}}
    missing = []
    for sym in symbols:
        path = by_dir / f"{sym}.json"
        if not path.exists():
            missing.append(sym)
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        off = dict(d["off"])
        neu = dict(d["neutral"])
        off["points"] = d.get("points_off") or []
        neu["points"] = d.get("points_on") or []
        results["off"][sym] = off
        results["neutral"][sym] = neu
        if d.get("domain_warn"):
            results["domain_warns"][sym] = d["domain_warn"]

    if missing:
        raise FileNotFoundError(
            f"by_symbol 缺少: {missing} (dir={by_dir})"
        )
    return list(symbols), results


# ---------------------------------------------------------------------------
# Per-symbol checkpoint IO
# ---------------------------------------------------------------------------

def load_checkpoint_dir(
    ckpt_dir: Path | str,
    legacy_file: Path | str | None = None,
) -> dict:
    """
    加载分品种 checkpoint 目录 → {sym: payload}。
    若目录空且存在 legacy 单文件 ckpt.json，则迁移拆分写入目录。
    """
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    for p in sorted(ckpt_dir.glob("*.json")):
        try:
            out[p.stem.lower()] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

    if out:
        return out

    if legacy_file is not None:
        legacy = Path(legacy_file)
        if legacy.exists():
            try:
                blob = json.loads(legacy.read_text(encoding="utf-8"))
            except Exception:
                blob = {}
            if isinstance(blob, dict):
                for sym, payload in blob.items():
                    if isinstance(payload, dict):
                        out[sym.lower()] = payload
                        save_symbol_checkpoint(ckpt_dir, sym, payload)
    return out


def save_symbol_checkpoint(
    ckpt_dir: Path | str,
    symbol: str,
    payload: dict,
) -> None:
    """原子写入单品种 checkpoint。"""
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(ckpt_dir / f"{symbol.lower()}.json", payload)


# ---------------------------------------------------------------------------
# Report write
# ---------------------------------------------------------------------------

def score_to_payload(score: UniverseScore) -> dict:
    return {
        "verdict": score.engineering_verdict,
        "engineering_verdict": score.engineering_verdict,
        "production_gate": score.production_gate,
        "gate_reasons": score.gate_reasons,
        "verdict_parts": score.verdict_parts,
        "action_mode": "neutral",
        "production_default": "OFF",
        "symbols": score.symbols,
        "n_symbols": len(score.symbols),
        "pool_off": score.pool_off,
        "pool_on": score.pool_on,
        "counts": score.counts,
        "domain_shift": score.domain,
        "smoke": asdict(score.smoke),
        "whitelist": score.whitelist,
        "rows": score.rows,
        "compare": score.compare,
        "domain_warns": score.domain_warns,
        "meta": {
            k: v for k, v in score.meta.items()
            if not k.startswith("_")
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scorer": "cascade.neutral_ab_report",
        "renderer": "cascade.neutral_ab_render",
        "verdict_policy": asdict(DEFAULT_VERDICT_POLICY),
    }


def update_task_state(score: UniverseScore, report_path: Path | str) -> None:
    project_root = Path(__file__).resolve().parent.parent
    ts_path = project_root / "task_state.json"
    state: dict = {}
    if ts_path.exists():
        try:
            state = json.loads(ts_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state["phase"] = "Path2_L1_neutral_fullchain"
    state["status"] = f"{score.engineering_verdict}|{score.production_gate}"
    state["path2_l1_neutral"] = {
        "verdict": score.engineering_verdict,
        "production_gate": score.production_gate,
        "r1_trigger": score.domain["r1_trigger"],
        "counts": score.counts,
        "report": str(report_path).replace("\\", "/"),
        "production_default": "OFF",
    }
    state["production"] = {
        "vol_filter_default": False,
        "vol_action_recommended": "neutral",
        "reason": (
            f"gate={score.production_gate}; "
            f"R1={score.domain['r1_trigger']}; default OFF"
        ),
    }
    atomic_write_json(ts_path, state)


def write_report(
    score: UniverseScore,
    report_path: Path | str,
    *,
    update_state: bool = True,
) -> UniverseScore:
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = report_path.with_suffix(".json")

    score.meta = dict(score.meta)
    score.meta.setdefault("report_json", str(json_path).replace("\\", "/"))

    md = render_markdown(score)
    atomic_write_text(report_path, md)
    atomic_write_json(json_path, score_to_payload(score))
    if update_state:
        update_task_state(score, report_path)
    return score


def score_and_write(
    symbols: Sequence[str],
    results: dict,
    report_path: Path | str,
    meta: dict | None = None,
    *,
    update_state: bool = True,
) -> UniverseScore:
    """唯一入口：评分 + 写 markdown/json/task_state。"""
    meta = dict(meta or {})
    # 供 spike 表使用
    meta["_off_blocks"] = results.get("off") or {}
    meta["_neu_blocks"] = results.get("neutral") or {}
    score = score_universe(symbols, results, meta=meta)
    return write_report(score, report_path, update_state=update_state)
