"""把首批两条确认假设写入 task_FM/config/preregistry.jsonl。

文件已存在时拒绝重写。不读时钟，不读数据库，不接监督环。
样本量只由 register 计算。
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from preregistry import register  # noqa: E402

OUT = ROOT / "task_FM" / "config" / "preregistry.jsonl"

_COMMON = {
    "registered_at": "2026-10-02T00:00:00+00:00",
    "confirm_from_ts": "2026-10-03 00:00:00",
    "delta_star": 0.08,
    "power": 0.80,
    "alpha": 0.05,
    "horizon": 24,
    "metric_version": "v1",
    "model_fingerprint": {
        "weights_sha256": "778773a8e8bcbb23",
        "n_files": 1,
        "hash_version": "v1",
    },
    "predict_params": {
        "context_bars": 480,
        "context_days": 250,
        "horizon_days": 22,
        "fill_strategy": "default",
        "ablation_mode": "full",
        "visualize": False,
    },
    "promote_condition": {"field": "d_mean", "threshold": 0.08},
    "kill_condition": {"field": "d_mean", "threshold": 0.0},
}

_JD = {
    **_COMMON,
    "symbol": "jd",
    "var_lr": 1.240,
    "n_planned": 1199,
    "cov_fingerprint": {
        "keys": ["daily_slope", "vor"],
        "matrix_sha256": "b5a9a95caee5240c723f2d9dcb6ad4d7fbc690b14a82c3a723b2f4b6ad5c3008",
        "n_channels": 2,
        "hash_version": "cov_matrix_hash_v1",
    },
    "mechanism": (
        "鸡蛋价格受季节性供需和节假日效应驱动,中秋/春节前需求激增导致价格突破。"
        "在低波动率压缩期(VOR<历史中位数),市场积蓄动能,一旦节日需求启动或供给冲击(疫病/饲料成本),"
        "价格沿突破方向运行。VOR捕捉波动率从压缩到扩张的转折点,提前信号节日行情启动。"
    ),
    "predicted_direction": "low_vol_compression -> holiday_demand_breakout",
}

_SR = {
    **_COMMON,
    "symbol": "sr",
    "var_lr": 1.020,
    "n_planned": 986,
    "cov_fingerprint": {
        "keys": ["daily_slope", "vwap_deviation"],
        "matrix_sha256": "2d82b5637bd737e1205403c1a9d06c079de805de90c836aaafeb8bcdc0d678a2",
        "n_channels": 2,
        "hash_version": "cov_matrix_hash_v1",
    },
    "mechanism": (
        "白糖是投机性极强的农产品期货,价格易受全球供需预期(巴西/印度产季、泰国出口政策)"
        "和资金情绪驱动而过度延伸。VWAP偏离度量化价格相对成交量加权均衡价格的短期过度延伸:"
        "正偏离过大说明价格上涨超出成交量支撑的合理区间,回调压力大;"
        "负偏离过大说明下跌超出合理区间,反弹概率高。"
        "白糖的sharp rallies/crashes常由投机资金推动至VWAP极端偏离后快速均值回归。"
    ),
    "predicted_direction": (
        "vwap_deviation_extreme_positive -> short (过度上涨回归); "
        "vwap_deviation_extreme_negative -> long (过度下跌回归)"
    ),
}


def main() -> int:
    if OUT.exists():
        print("refuse rewrite: %s" % OUT, file=sys.stderr)
        return 1
    existing = []
    lines = []
    for fields in (_JD, _SR):
        rec = register(fields, existing)
        existing.append(rec)
        lines.append(json.dumps(dataclasses.asdict(rec), ensure_ascii=False))
    got = [rec.n_confirm_required for rec in existing]
    if got != [1199, 986]:
        print(
            "n_confirm_required is %s, expected [1199, 986]; not writing" % (got,),
            file=sys.stderr,
        )
        return 2
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
