#!/usr/bin/env python3
"""
R1 分板块 VolRiskFilter 训练。

核准约束:
  - 默认 all = chem + agri（black 不自动训；缺 pkl 时推理回落 R0）
  - --sector black_metals 或 --include-black 可训独立 black pkl（本轮不强制执行）
  - 分板块自算 q70 标签阈值
  - 每品种 IS 末端等长截断（默认 2000 bars）防大品种霸权
  - thr 主路径 0.55（写入 pkl，推理可覆盖）
  - 缺模型调用方必须 FileNotFoundError，本脚本不提供 silent fallback

用法:
  python scripts/train_vol_risk_sector.py --sector all
  python scripts/train_vol_risk_sector.py --sector energy_chem --force
  python scripts/train_vol_risk_sector.py --sector black_metals --force  # 可选，不默认
  python scripts/train_vol_risk_sector.py --sector all --include-black --force
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.sector_map import get_sector_symbols, list_sectors  # noqa: E402
from cascade.vol_risk_filter import (  # noqa: E402
    DEFAULT_MAX_BARS_PER_SYMBOL,
    DEFAULT_PROB_THRESHOLD,
    SECTOR_MODEL_PATHS,
    VolRiskFilter,
)
from cascade.neutral_ab_report import atomic_write_json  # noqa: E402
from data.config import resolve_under_root  # noqa: E402

# 默认 all 只训核心两块；black 可显式指定（不默认 GPU 训练）
R1_CORE_SECTORS = ("energy_chem", "agri")
R1_ALLOWED_SECTORS = ("energy_chem", "agri", "black_metals")

_SECTOR_SHORT = {
    "energy_chem": "chem",
    "agri": "agri",
    "black_metals": "black",
}


def train_one(
    sector: str,
    train_end: str,
    thr: float,
    max_bars: int,
    out_path: Path,
    force: bool,
    meta_dir: Path,
) -> dict:
    if out_path.exists() and not force:
        print(f"[skip] {out_path} exists (use --force to retrain)")
        # 不传 thr 覆盖：保留 pkl 元数据与默认 threshold 决议
        filt = VolRiskFilter.load(str(out_path))
        return {
            "sector": sector,
            "path": str(out_path).replace("\\", "/"),
            "skipped": True,
            "q_abs": filt.q_abs,
            "n_samples": filt.n_samples,
            "n_by_symbol": filt.n_by_symbol,
            "pos_rate": filt.pos_rate,
            "calibrated_thr": filt.calibrated_thr,
            "threshold": filt.threshold,
            "threshold_source": filt.threshold_source,
        }

    symbols = get_sector_symbols(sector)
    print(f"\n=== train sector={sector} symbols={symbols} ===")
    filt = VolRiskFilter.train(
        symbols=symbols,
        train_end=train_end,
        prob_threshold=thr,
        step=6,
        max_bars_per_symbol=max_bars,
        sector=sector,
        min_samples=200,
    )
    filt.model_path = str(out_path)
    filt.save(str(out_path))

    meta = {
        "sector": sector,
        "path": str(out_path).replace("\\", "/"),
        "skipped": False,
        "train_end": train_end,
        "legacy_thr_arg": thr,
        "calibrated_thr": filt.calibrated_thr,
        "calib_quantile": filt.calib_quantile,
        "prob_threshold_default": filt.prob_threshold,
        "max_bars_per_symbol": max_bars,
        "train_symbols": symbols,
        "q_abs": filt.q_abs,
        "n_samples": filt.n_samples,
        "n_by_symbol": filt.n_by_symbol,
        "pos_rate": filt.pos_rate,
        "equal_weight": "truncate_last_N_bars_per_symbol",
        "label": f"abs_move_24h >= sector_q{int(0.70*100)}",
        "thresholding": "IS_predict_proba_quantile",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    meta_dir.mkdir(parents=True, exist_ok=True)
    short = _SECTOR_SHORT.get(sector, sector)
    atomic_write_json(meta_dir / f"{short}_train_meta.json", meta)
    print(f"[saved] {out_path}")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="R1 sector VolRiskFilter train")
    parser.add_argument(
        "--sector",
        default="all",
        help="energy_chem | agri | black_metals | all (default all=chem+agri only)",
    )
    parser.add_argument(
        "--include-black",
        action="store_true",
        help="with --sector all, also train black_metals (default off)",
    )
    parser.add_argument("--train-end", default="2026-03-31")
    parser.add_argument("--thr", type=float, default=DEFAULT_PROB_THRESHOLD)
    parser.add_argument(
        "--max-bars-per-symbol",
        type=int,
        default=DEFAULT_MAX_BARS_PER_SYMBOL,
        help="等权：每品种 IS 末端 bar 数",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--meta-dir",
        default="reports/phase1/r1",
    )
    args = parser.parse_args()

    if args.sector == "all":
        sectors = list(R1_CORE_SECTORS)
        if args.include_black:
            sectors = list(sectors) + ["black_metals"]
    else:
        if args.sector not in R1_ALLOWED_SECTORS:
            raise SystemExit(
                f"R1 allows {R1_ALLOWED_SECTORS}, got {args.sector!r}. "
                f"Known sectors: {list_sectors()}"
            )
        sectors = [args.sector]

    meta_dir = Path(args.meta_dir)
    if not meta_dir.is_absolute():
        meta_dir = resolve_under_root(meta_dir)
    results = []
    for sec in sectors:
        out = resolve_under_root(SECTOR_MODEL_PATHS[sec])
        print(f"[plan] sector={sec} → {out}")
        results.append(
            train_one(
                sector=sec,
                train_end=args.train_end,
                thr=args.thr,
                max_bars=args.max_bars_per_symbol,
                out_path=out,
                force=args.force,
                meta_dir=meta_dir,
            )
        )

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sectors": results,
        "policy": {
            "equal_weight": "max_bars_per_symbol",
            "max_bars_per_symbol": args.max_bars_per_symbol,
            "q_abs": "per_sector_pool_quantile_0.70",
            "thr": args.thr,
            "train_end": args.train_end,
            "no_silent_fallback": True,
        },
    }
    atomic_write_json(meta_dir / "train_summary.json", summary)
    print("\n=== R1.1 train summary ===")
    for r in results:
        print(
            f"  {r['sector']}: n={r.get('n_samples')} "
            f"q_abs={r.get('q_abs')} pos={r.get('pos_rate')} "
            f"path={r.get('path')} skip={r.get('skipped')}"
        )


if __name__ == "__main__":
    main()
