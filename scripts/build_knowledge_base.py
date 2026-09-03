#!/usr/bin/env python3
"""
从 L1 全链路经济判决 + 固化方案 SCHEMES 生成 config/knowledge_base.json。

用法:
  python scripts/build_knowledge_base.py
  python scripts/build_knowledge_base.py --l1 reports/phase1/full_universe_neutral_r1_ops/ECONOMIC_VERDICT.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.prediction_scheme import SCHEMES, get_scheme  # noqa: E402
from config.sector_map import sector_of  # noqa: E402

DEFAULT_L1 = ROOT / "reports/phase1/full_universe_neutral_r1_ops/ECONOMIC_VERDICT.json"
OUT_PATH = ROOT / "config/knowledge_base.json"

# 短线衰减品种：建议提前出场（与 scheme short_range / 高 decay 对齐）
SHORT_HOLD = {"p", "cf", "bu", "ao", "cj", "fu", "eg", "ma", "ta"}
LONG_HOLD = {"ss", "sr", "sp", "ur", "m"}


def _best_hold(sym: str, scheme) -> str:
    if scheme and scheme.short_horizon_only:
        return "T+1 ~ T+8"
    if sym in SHORT_HOLD:
        return "T+1 ~ T+8"
    if scheme and scheme.decay >= 1.5:
        return "T+1 ~ T+12（远端衰减快）"
    if sym in LONG_HOLD or (scheme and scheme.scheme_type == "trend"):
        return "T+12 ~ T+24"
    return "T+4 ~ T+16"


def _stars_from_metrics(dir_acc: float, pf: float, scheme_stars: int | None) -> int:
    """信用星级（CF-10 A）：唯一源 = scheme.stars。

    DirAcc/PF 公式仅作 ``formula_stars`` 诊断字段，不再覆盖 scheme。
    无 scheme 时才回退公式（兼容仅有 L1 行的符号）。
    """
    if scheme_stars is not None:
        return max(0, min(3, int(scheme_stars)))
    score = 0.0
    if dir_acc >= 0.65:
        score += 2
    elif dir_acc >= 0.55:
        score += 1
    if pf >= 1.4:
        score += 1
    elif pf >= 1.15:
        score += 0.5
    if pf > 0 and pf < 0.95:
        score = max(0.0, score - 1)
    return max(0, min(3, int(round(min(3, score)))))


def _rationale(sym: str, cov: str, scheme) -> str:
    st = scheme.scheme_type if scheme else "unknown"
    parts = [
        f"固化协变量={cov}",
        f"方案类型={st}",
    ]
    if scheme and scheme.short_horizon_only:
        parts.append("短线品种：远端衰减显著，优先前半段信号")
    if scheme and scheme.scheme_type == "trend":
        parts.append("趋势型：可适当持有至 T+24")
    return "；".join(parts) + "。"


def build(l1_path: Path) -> dict:
    l1_rows = {}
    meta = {}
    if l1_path.exists():
        raw = json.loads(l1_path.read_text(encoding="utf-8"))
        meta = {
            "l1_source": str(l1_path.as_posix()),
            "l1_generated_at": raw.get("generated_at"),
            "l1_economic_pass": raw.get("pass"),
        }
        for r in raw.get("rows") or []:
            l1_rows[str(r.get("sym", "")).lower()] = r
    else:
        meta = {"l1_source": None, "warning": f"missing {l1_path}"}

    symbols = sorted(set(list(SCHEMES.keys()) + list(l1_rows.keys())))
    kb: dict = {
        "_meta": {
            "version": 1,
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "note": (
                "信用星级 credit_stars = scheme.stars（唯一源 CF-10 A）。"
                "DirAcc/MAPE/decay 来自 SCHEMES；PF/EV 来自 L1 OFF 基线。"
                "Vol 仅预警不压平。产品=主观辅助非自动下单。"
                "展示优先 PF/EV/MaxDD，DirAcc 仅附录（CF-23 A）。"
            ),
            **meta,
        },
        "symbols": {},
    }

    for sym in symbols:
        scheme = get_scheme(sym)
        r = l1_rows.get(sym, {})
        pf = float(r["pf_off"]) if r.get("pf_off") is not None else (
            float("nan") if not scheme else max(0.5, scheme.dir_acc * 2.0)
        )
        # fallback PF estimate if no L1: rough from dir_acc only for display
        if pf != pf:  # nan
            pf = 1.0
        ev = float(r["ev_off"]) if r.get("ev_off") is not None else None
        dir_acc = float(scheme.dir_acc) if scheme else 0.5
        mape = float(scheme.mape) if scheme else None
        decay = float(scheme.decay) if scheme else None
        coverage = float(scheme.coverage) if scheme else None
        cov = (
            "+".join(scheme.covariate_types)
            if scheme and scheme.covariate_types
            else (scheme.covariate_type if scheme else None)
        ) or r.get("cov") or "unknown"
        vol_tag = r.get("tag") or "UNKNOWN"  # HELPS/HURTS/MIXED/NEUTRAL from vol overlay A/B
        # 注意：L1 tag 是「开 vol-filter 后相对 OFF 的经济标签」，不是品种本身波动属性。
        # 作为高波应对指南：HELPS=高波时过滤有利→观望；HURTS=过滤有害→高波可能是趋势机会
        stars = _stars_from_metrics(dir_acc, pf, scheme.stars if scheme else None)
        entry = {
            "name": scheme.name if scheme else sym.upper(),
            "sector": r.get("sector") or sector_of(sym),
            "covariate": cov,
            "scheme_type": scheme.scheme_type if scheme else None,
            "scheme_stars": scheme.stars if scheme else None,
            "credit_stars": stars,
            "historical_diracc": round(dir_acc, 4),
            "historical_mape": mape,
            "historical_decay": decay,
            "historical_coverage": coverage,
            "historical_pf": round(pf, 4) if pf == pf else None,
            "historical_ev": round(ev, 4) if ev is not None else None,
            "historical_maxdd": r.get("dd_off"),
            "vol_sensitivity": vol_tag,  # HELPS | HURTS | MIXED | NEUTRAL | UNKNOWN
            "vol_l1_veto_rate": r.get("veto"),
            "vol_l1_delta_ev": (
                round(float(r["ev_on"]) - float(r["ev_off"]), 4)
                if r.get("ev_on") is not None and r.get("ev_off") is not None
                else None
            ),
            "best_hold_period": _best_hold(sym, scheme),
            "short_horizon_only": bool(scheme.short_horizon_only) if scheme else False,
            "covariate_rationale": _rationale(sym, cov, scheme),
        }
        kb["symbols"][sym] = entry

    return kb


def main():
    ap = argparse.ArgumentParser(description="Build Copilot knowledge_base.json")
    ap.add_argument("--l1", type=Path, default=DEFAULT_L1)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    kb = build(args.l1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(kb["symbols"])
    print(f"Wrote {args.out} ({n} symbols)")
    for sym, e in sorted(kb["symbols"].items()):
        print(
            f"  {sym:3} ★{e['credit_stars']} PF={e['historical_pf']} "
            f"DirAcc={e['historical_diracc']} vol={e['vol_sensitivity']} "
            f"hold={e['best_hold_period']}"
        )


if __name__ == "__main__":
    main()
