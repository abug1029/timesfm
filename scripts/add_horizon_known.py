"""PR-C6: 为 covariate_pool.json 添加 horizon_known 分类"""

import json
from datetime import datetime
from pathlib import Path

# 宿主裁定 + 合理推断 + 实证探针确认的 horizon_known 分类
#
# 宿主裁定（2026-09-28）：
#   calendar_cyclical = known_ahead（暂挂）
#   ccl / oi          = unknowable
#   rsi_state / hourly_slope = self_referential → persistence（改判）
#
# 改判依据：实证探针证伪「horizon 取自 TimesFM 自身输出」——
#   rsi_state 扰动 predicted_daily_closes ×1.5+30，horizon 逐值不变
#   （末态非零时产出 [2,2,1,1,0,0,...]，context 末态衰减）；
#   hourly_slope 是 np.full(horizon, last_valid)，末值常数。
#   按 W5.1 定义（persistence = context 末值的确定性函数），归 persistence。
#
# 两法一致（静态表达式分析 + 实证探针）确认 persistence：
#   ao_accel / bb_squeeze / ha_body / hurst / qstick /
#   reversal_shadow[_gated_*] / sar_dist / stddev
HORIZON_KNOWN_MAP = {
    # 宿主裁定（2026-09-28）
    "calendar_cyclical": "known_ahead",
    "ccl": "unknowable",
    "oi": "unknowable",

    # 宿主改判：self_referential → persistence
    "rsi_state": "persistence",
    "rsi6": "persistence",
    "rsi12": "persistence",
    "rsi24": "persistence",
    "hourly_slope": "persistence",

    # momentum 族：两法一致确认 persistence
    "qstick": "persistence",
    "ha_body": "persistence",
    "reversal_shadow": "persistence",
    "reversal_shadow_gated_02": "persistence",
    "reversal_shadow_gated_03": "persistence",
    "reversal_shadow_gated_05": "persistence",
    "hurst": "persistence",
    "gated_slope": "persistence",
    "sar_dist": "persistence",
    "ao_accel": "persistence",

    # self_referential: 静态/探针冲突或品种间不一致，待人工裁定
    "rsi_slope": "self_referential",
    "pca_momentum": "self_referential",
    "regime_gated": "self_referential",
    "vwap_deviation": "self_referential",
    "oi_gated_momentum": "self_referential",
    "vor": "self_referential",

    # volatility 族：两法一致确认 persistence
    "stddev": "persistence",
    "bb_squeeze": "persistence",

    # inventory / term_structure 族：未来不可知
    "nvi": "unknowable",
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

            # known_ahead 必须有 known_ahead_evidence；
            # 非 known_ahead 必须清理残留证据，否则陈旧证据零告警存活
            # （与 cascade/cov_family.apply_horizon_known_downgrade 对齐）
            if horizon_known == "known_ahead":
                cov_config["known_ahead_evidence"] = CALENDAR_EVIDENCE
            else:
                cov_config.pop("known_ahead_evidence", None)

    # 更新 schema 版本和日期
    pool["schema"] = "fm.covariate_pool.v2"  # bump version
    pool["updated"] = datetime.now().strftime("%Y-%m-%d")

    # 添加 horizon_known 说明
    pool["horizon_known_note"] = (
        "PR-C6 新增（spec §4.5 W5）：协变量按未来可知性分为四类。"
        "known_ahead: cutoff 时点确实已知未来值（须附 known_ahead_evidence）；"
        "persistence: 未来不可知但可用末值延续近似（末值常数或确定性衰减）；"
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
