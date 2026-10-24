#!/usr/bin/env python3
"""验证 TypeSafe 预筛与历史 proposal 的一致性。

用法:
  source .venv/bin/activate
  python scripts/validate_typesafe_prescreen.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cascade.typesafe_prescreen import prescreen_and_save

# ── 加载生产环境历史裁决 ────────────────────────────
FM_ROOT = Path(__file__).resolve().parent.parent
VERDICTS_PATH = FM_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"
verdict_history = []
if VERDICTS_PATH.exists():
    with open(VERDICTS_PATH, encoding="utf-8") as _vf:
        verdict_history = [json.loads(_l) for _l in _vf if _l.strip()]
    print(f"已加载 {len(verdict_history)} 条历史裁决")
else:
    print(f"⚠️ 未找到历史裁决文件: {VERDICTS_PATH}")

# ── 5 个典型历史 proposal（硬编码，消除占位符）─────
HISTORY_PROPOSALS = [
    {
        "symbol": "JD",
        "proposal_path": "results/gen_2/peer_001/v_jd_rsi/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_jd_rsi",
            "mechanism": "JD 鸡蛋 RSI 超卖反转在交割月效应增强",
            "cov_override": "rsi_state",
        },
        "expected_plausibility_range": (0.6, 0.9),
        "expected_novelty": "extension",
        "expected_skip": False,
    },
    {
        "symbol": "SS",
        "proposal_path": "results/gen_2/peer_002/v_ss_ccl/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_ss_ccl",
            "mechanism": "不锈钢仓单量价背离预示短期回调",
            "cov_override": "ccl",
        },
        "expected_plausibility_range": (0.5, 0.85),
        "expected_novelty": "extension",
        "expected_skip": False,
    },
    {
        "symbol": "RB",
        "proposal_path": "results/gen_2/peer_003/v_rb_oi/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_rb_oi",
            "mechanism": "螺纹钢持仓量增仓方向与价格趋势共振",
            "cov_override": "oi",
        },
        "expected_plausibility_range": (0.6, 0.9),
        "expected_novelty": "extension",
        "expected_skip": False,
    },
    {
        "symbol": "CF",
        "proposal_path": "results/gen_2/peer_004/v_cf_seasonal/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_cf_seasonal",
            "mechanism": "棉花季节性备货周期驱动价格波动",
            "cov_override": "calendar_cyclical",
        },
        "expected_plausibility_range": (0.4, 0.75),
        "expected_novelty": "novel",
        "expected_skip": False,
    },
    {
        "symbol": "M",
        "proposal_path": "results/gen_2/peer_005/v_m_rsi_oi/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_m_rsi_oi",
            "mechanism": "豆粕 RSI+OI 组合协变量在低波动体制下的增强效果",
            "cov_override": "rsi_state",
        },
        "expected_plausibility_range": (0.3, 0.65),
        "expected_novelty": "redundant",
        "expected_skip": True,
    },
]


def main():
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"TypeSafe 预筛人工验证 — {len(HISTORY_PROPOSALS)} 个历史 proposal")
    print(f"历史裁决: {len(verdict_history)} 条")
    print(sep)

    pass_count = 0
    for item in HISTORY_PROPOSALS:
        sym = item["symbol"]
        vid = item["proposal"]["variant_id"]
        print(f"\n--- {sym} / {vid} ---")

        result = prescreen_and_save(
            proposal=item["proposal"],
            proposal_path=item["proposal_path"],
            symbol=item["symbol"],
            verdict_history=verdict_history,
        )

        print(f"  status: {result['status']}")
        if result["status"] != "success":
            print(f"  note: {result['note']}")
            continue

        pl = result["mechanism_plausibility"]
        lo, hi = item["expected_plausibility_range"]
        nov = result["novelty"]
        es = result["effect_size"]
        skip = result["skip_suggested"]
        note = result["note"]
        exp_nov = item["expected_novelty"]
        exp_skip = item["expected_skip"]

        print(f"  plausibility: {pl:.2f} (预期 [{lo}, {hi}])")
        print(f"  novelty: {nov} (预期 {exp_nov})")
        print(f"  effect_size: {es}")
        print(f"  skip_suggested: {skip} (预期 {exp_skip})")
        print(f"  note: {note}")

        pl_ok = lo <= pl <= hi
        skip_ok = skip == exp_skip

        if pl_ok:
            print("  ✅ plausibility 一致")
        else:
            print(f"  ⚠️ plausibility 偏离预期 ({pl:.2f} not in [{lo}, {hi}])")

        if skip_ok:
            print("  ✅ skip 判断一致")
        else:
            print(f"  ⚠️ skip 判断偏离预期 (got {skip}, expected {exp_skip})")

        if pl_ok and skip_ok:
            pass_count += 1

    print(f"\n{sep}")
    print(f"验证完成: {pass_count}/{len(HISTORY_PROPOSALS)} 一致")
    print(sep)


if __name__ == "__main__":
    main()
