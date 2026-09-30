#!/usr/bin/env python3
"""落盘 horizon_known 重标 —— **只改两种方法独立一致、且有 spec 依据的项**。

判定链（三者必须同时成立才改）：
  1. 静态表达式分析（`reclassify_horizon_known.py`）给出结论
  2. 实证探针（`probe_horizon_known.py`）给出**相同**结论
  3. 与 spec §4.5 W5.1 的定义不冲突（不推翻 spec 点名的示例）

只满足其一或二者冲突的，一律**不改**并留证待人工裁定。

用法:
    .venv/bin/python scripts/apply_horizon_known_relabel.py            # 只报告
    .venv/bin/python scripts/apply_horizon_known_relabel.py --write
"""
import argparse
import json
import sys
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "task_FM" / "config" / "covariate_pool.json"

# ── 静态分析 + 实证探针**独立得出同一结论**的项 ────────────────────────
# 两者一致意味着：表达式形态（_decay_fill / np.full）与运行时行为
# （horizon 不随 predicted_* 变化、非全零）互证。
CONFIRMED_PERSISTENCE = {
    # 静态: np.concatenate([ctx, _decay_fill(last_val, horizon)])
    # 探针: horizon 不随 predicted_* 变化且非全零
    "ao_accel", "bb_squeeze", "qstick", "reversal_shadow",
    "reversal_shadow_gated_02", "reversal_shadow_gated_03",
    "reversal_shadow_gated_05", "sar_dist", "stddev",
    # 静态: np.full(horizon, last_val) —— 末值常数
    "ha_body", "hurst", "hourly_slope",
}

# ── 用户裁定「按代码修正为 persistence」的 RSI 族 ──────────────────────
# spec W5.5① 原裁 self_referential，理由「horizon 尾值取自 TimesFM 自身
# 日线输出」被可执行探针证伪（扰动 predicted_daily_closes ×1.5+30，
# horizon 逐值不变）。构造是 _generate_rsi_state_horizon(last_ctx_state)
# —— context 末态向均值衰减，按 W5.1 定义属 persistence。
# 探针曾判 unknowable，但那是「末态恰为 0 时衰减也全零」的数据依赖假象
# （末态非零时实测为 [2,2,1,1,0,0,...]）。
RULED_PERSISTENCE = {"rsi_state", "rsi6", "rsi12", "rsi24"}

TO_CHANGE = CONFIRMED_PERSISTENCE | RULED_PERSISTENCE

# ── 明确**不改**的项（留证）────────────────────────────────────────────
# spec W5.1 点名「库存、持仓、基差、基本面」为 unknowable，理由是
# 「既不可知**也无法近似**」。代码对它们填了末值/衰减，探针遂判
# persistence —— 但 spec 的标签编码的是**判断**，探针无权推翻。
KEEP_SPEC_UNKNOWABLE = {"ccl", "oi", "nvi", "basis_momentum",
                        "crack_spread_level", "crack_spread_slope",
                        "crack_spread_zscore"}

# 两法冲突或无法判定，留待人工裁定。
NEEDS_RULING = {
    "pca_momentum": "静态判 unknowable（np.zeros），探针判 persistence",
    "regime_gated": "复合量：静态无法解析，探针判 persistence，审核判 unknowable（2/3 腿零填充）",
    "oi_gated_momentum": "探针品种间不一致（RB=unknowable, JD/I=persistence）",
    "vor": "静态无法解析（中间变量 horizon_vor），探针判 persistence",
    "vwap_deviation": "静态无法解析（中间变量 decay），探针判 persistence",
    "calendar_cyclical": "spec W5.5① vs W5.1/W5.5② 自相矛盾，宿主已定暂挂",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    pool = json.loads(POOL.read_text(encoding="utf-8"))
    covs = pool["covariates"]

    changes, missing = [], []
    for name in sorted(TO_CHANGE):
        if name not in covs:
            missing.append(name)
            continue
        cur = covs[name].get("horizon_known")
        if cur != "persistence":
            changes.append((name, cur))

    print("=== 将改判为 persistence (%d) ===" % len(changes))
    for name, cur in changes:
        src = "两法一致" if name in CONFIRMED_PERSISTENCE else "宿主裁定"
        print("  %-28s %-16s -> persistence   [%s]" % (name, cur, src))

    print("\n=== 明确不改：spec 点名 unknowable (%d) ===" % len(KEEP_SPEC_UNKNOWABLE))
    for name in sorted(KEEP_SPEC_UNKNOWABLE):
        print("  %-28s %s" % (name, covs.get(name, {}).get("horizon_known")))

    print("\n=== 留待人工裁定 (%d) ===" % len(NEEDS_RULING))
    for name, why in sorted(NEEDS_RULING.items()):
        print("  %-28s %s" % (name, why))

    if missing:
        print("\n[WARN] 池中不存在: %s" % missing, file=sys.stderr)

    if args.write:
        for name, _ in changes:
            covs[name]["horizon_known"] = "persistence"
        POOL.write_text(json.dumps(pool, indent=1, ensure_ascii=False),
                        encoding="utf-8")
        print("\n已写入 %s（%d 项）" % (POOL, len(changes)))
    else:
        print("\n（未落盘；加 --write 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
