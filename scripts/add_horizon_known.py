"""PR-C6: 为 covariate_pool.json 添加 horizon_known 分类"""

import json
from pathlib import Path

# 宿主裁定 + 合理推断的 horizon_known 分类
HORIZON_KNOWN_MAP = {
    # 宿主裁定（2026-09-28）
    "calendar_cyclical": "known_ahead",
    "rsi_state": "self_referential",
    "hourly_slope": "self_referential",
    "ccl": "unknowable",
    "oi": "unknowable",

    # 合理推断（基于协变量性质）
    # momentum 族：大多基于价格，horizon 尾取自 TimesFM 自身输出
    "rsi6": "self_referential",
    "rsi12": "self_referential",
    "rsi24": "self_referential",
    "rsi_slope": "self_referential",
    "qstick": "self_referential",
    "ha_body": "self_referential",
    "reversal_shadow": "self_referential",
    "reversal_shadow_gated_02": "self_referential",
    "reversal_shadow_gated_03": "self_referential",
    "reversal_shadow_gated_05": "self_referential",
    "pca_momentum": "self_referential",
    "hurst": "self_referential",
    "regime_gated": "self_referential",
    "gated_slope": "self_referential",
    "sar_dist": "self_referential",
    "ao_accel": "self_referential",
    "oi_gated_momentum": "self_referential",
    "vwap_deviation": "self_referential",

    # volatility 族：基于价格波动，horizon 尾取自 TimesFM 自身输出
    "stddev": "self_referential",
    "vor": "self_referential",
    "bb_squeeze": "self_referential",

    # inventory 族：未来持仓/库存不可知
    "nvi": "unknowable",

    # term_structure 族：未来基差/价差不可知
    "basis_momentum": "unknowable",
    "crack_spread_level": "unknowable",
    "crack_spread_slope": "unknowable",
    "crack_spread_zscore": "unknowable",
}

# calendar_cyclical 的 known_ahead 证据（宿主裁定）
CALENDAR_EVIDENCE = {
    "source": "交易所交易日历",
    "publication_rule": "每年12月公布次年日历",
    "publication_lag": "0",
    "reconstructable": "可用 cutoff 时点当时的日历信息复原",
    "verified_by": "host",
    "verified_at": "2026-09-28"
}


def add_horizon_known_to_pool(pool_path: str) -> dict:
    """为 covariate_pool.json 添加 horizon_known 字段"""
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)

    covariates = pool.get("covariates", {})

    for cov_name, cov_config in covariates.items():
        if cov_name in HORIZON_KNOWN_MAP:
            horizon_known = HORIZON_KNOWN_MAP[cov_name]
            cov_config["horizon_known"] = horizon_known

            # known_ahead 必须有 known_ahead_evidence
            if horizon_known == "known_ahead":
                cov_config["known_ahead_evidence"] = CALENDAR_EVIDENCE

    # 更新 schema 版本和日期
    pool["schema"] = "fm.covariate_pool.v2"  # bump version
    pool["updated"] = "2026-09-28"

    # 添加 horizon_known 说明
    pool["horizon_known_note"] = (
        "PR-C6 新增（spec §4.5 W5）：协变量按未来可知性分类。"
        "known_ahead: cutoff 时点确实已知未来值；"
        "persistence: 未来不可知但可用末值延续近似；"
        "self_referential: 未来值来自模型自身输出；"
        "unknowable: 既不可知也无法近似。"
        "仅 known_ahead 算外生信息，其余三类 horizon 尾填末值。"
    )

    return pool


if __name__ == "__main__":
    pool_path = "task_FM/config/covariate_pool.json"
    pool = add_horizon_known_to_pool(pool_path)

    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=1, ensure_ascii=False)

    print(f"Updated {pool_path}")
    print(f"  schema: {pool['schema']}")
    print(f"  covariates: {len(pool['covariates'])}")

    # 统计各分类数量
    counts = {}
    for cov_config in pool["covariates"].values():
        hk = cov_config.get("horizon_known", "unknown")
        counts[hk] = counts.get(hk, 0) + 1

    print(f"  horizon_known distribution: {counts}")
