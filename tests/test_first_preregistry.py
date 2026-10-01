"""首批两条预注册落盘。不加载模型。"""
from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

import preregistry as pr  # noqa: E402


_PATH = project_root / "task_FM" / "config" / "preregistry.jsonl"

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

_ROWS = (
    {
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
    },
    {
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
    },
)


def test_first_preregistry_two_rows():
    text = _PATH.read_text(encoding="utf-8")
    assert "family_key" not in text
    assert "0.51" not in text
    assert "0.52" not in text
    assert "999999" not in text
    lines = text.splitlines()
    assert len(lines) == 2
    stored = [json.loads(line) for line in lines]
    assert [row["symbol"] for row in stored] == ["jd", "sr"]
    assert stored[0]["symbol"] != stored[1]["symbol"]
    hashes = [row["cov_fingerprint"]["matrix_sha256"] for row in stored]
    assert hashes[0] != hashes[1]
    assert hashes == [
        "b5a9a95caee5240c723f2d9dcb6ad4d7fbc690b14a82c3a723b2f4b6ad5c3008",
        "2d82b5637bd737e1205403c1a9d06c079de805de90c836aaafeb8bcdc0d678a2",
    ]
    ids = []
    existing = []
    for fields, row in zip(_ROWS, stored, strict=True):
        rec = pr.register(fields, existing)
        existing.append(rec)
        fresh = dataclasses.asdict(rec)
        assert re.fullmatch(r"[0-9a-f]{32}", row["prereg_id"])
        ids.append(row["prereg_id"])
        disk = dict(row)
        disk.pop("prereg_id")
        fresh.pop("prereg_id")
        assert disk == fresh
        assert row["n_confirm_required"] == pr.n_confirm_required_for_symbol(row["symbol"])
        assert row["terminal_state"] is None
        assert row["confirm_from_ts"] == "2026-10-03 00:00:00"
        assert row["registered_at"] == "2026-10-02T00:00:00+00:00"
        assert row["metric_version"] == "v1"
        assert row["horizon"] == 24
        assert isinstance(row["horizon"], int)
    assert ids[0] != ids[1]
    assert stored[0]["n_confirm_required"] == 1199
    assert stored[1]["n_confirm_required"] == 986
