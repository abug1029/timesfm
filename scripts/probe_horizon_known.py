#!/usr/bin/env python3
"""**实证**判定每个协变量的 horizon_known（不采信静态解析或外部清单）。

判定逻辑（对应 spec §4.5 W5.1 的定义）：

    构造同一协变量两次，只改 `predicted_daily_closes`（模型自身输出）：
      horizon 段**变化**        → self_referential（来自模型输出）
      horizon 段全零            → unknowable（无任何近似）
      horizon 段不变且非全零    → persistence（context 末值的确定性函数）

这比读 `covariate_full = ...` 的表达式可靠：走 helper 的分支、用中间变量的
分支都能被覆盖（正则解析会漏掉它们）。

⚠️ **三个已知失效模式 —— 本探针不是权威，不得单独据此落盘**

  1. **无法判定 `known_ahead`**。探针只测「horizon 是否随 `predicted_*` 变化」，
     而 `known_ahead` 与 `persistence` 在该测下表现**完全相同**（都不变）。
     实测它把 `calendar_cyclical` 误判为 persistence。
     要判 `known_ahead` 需**另一个**探针：扰动 **cutoff 之后**的数据，
     看 horizon 是否不变。

  2. **与 spec 的判断层冲突**。W5.1 点名「库存、持仓、基差、基本面」为
     `unknowable`，理由是「既不可知**也无法近似**」。而代码对它们仍填了
     末值/衰减，探针遂判为 persistence。差别在于：**spec 的标签编码的是
     「末值延续对该量是否算合法近似」这一判断**，不只是代码路径。
     实测它把 `ccl`/`oi`/`nvi` 误判为 persistence。

  3. **「全零」是数据依赖的**。`unknowable` 的判据是「horizon 全零」，
     但衰减型构造在 **context 末值恰为 0** 时也产出全零。
     实测 `rsi_state`/`rsi12`/`rsi24` 被判 `unknowable`，而它们的构造
     （`_generate_rsi_state_horizon`）在末态非零时产出 `[2,2,1,1,0,0,…]`
     —— 是衰减，不是全零。换一个 cutoff 结论就会翻转。

  `--write` 在存在「无法判定」或「探针无权改判」项时**拒绝落盘**。
  但即使全部可判定，上述 3 个失效模式仍意味着**需要人工逐项对照 spec 与
  代码**才能定标签。本探针是证据来源之一，不是判决。

用法:
    .venv/bin/python scripts/probe_horizon_known.py            # 只报告
    .venv/bin/python scripts/probe_horizon_known.py --write    # 落盘
"""
import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))

from cascade.features import build_covariate_matrix  # noqa: E402
from config.backtest_config import CONTEXT_BARS, HORIZON  # noqa: E402
from data.data_store import DataStore  # noqa: E402

POOL = FM_ROOT / "task_FM" / "config" / "covariate_pool.json"
PROBE_SYMBOLS = ("RB", "JD", "I")


def _horizon_of(res: dict, limit: int) -> dict:
    """取出返回里各通道的 horizon 段。"""
    out = {}
    for k, v in res.items():
        if k == "daily_slope":
            continue
        arr = np.asarray(v, dtype=float).ravel()
        if len(arr) > limit:
            out[k] = arr[limit:]
    return out


def probe_one(symbol: str, cov: str) -> tuple:
    """返回 (label, 说明)。"""
    store = DataStore(symbol)
    df_1h = store.get_main_contract_1h(limit=CONTEXT_BARS + HORIZON + 50)
    if df_1h is None or df_1h.empty:
        return None, "无 1H 数据"

    daily = store.get_main_continuous(limit=200)
    if daily is None or daily.empty:
        return None, "无日线数据"
    hist = daily["close_price"].values.astype(float)
    dates = daily["dt"]

    rng = np.random.default_rng(20260928)
    pred_a = hist[-1] * np.cumprod(1 + 0.002 * np.ones(30))
    pred_b = hist[-1] * np.cumprod(1 - 0.02 * np.ones(30))  # 剧烈反向

    kw = dict(historical_daily_closes=hist, daily_dates=dates,
              horizon=HORIZON, limit=CONTEXT_BARS, df_1h=df_1h)
    try:
        ra = build_covariate_matrix(symbol, store, predicted_daily_closes=pred_a,
                                    covariate_type=cov, **kw)
        rb = build_covariate_matrix(symbol, store, predicted_daily_closes=pred_b,
                                    covariate_type=cov, **kw)
    except Exception as e:
        return None, "构造失败: %s" % str(e)[:60]

    ha, hb = _horizon_of(ra, CONTEXT_BARS), _horizon_of(rb, CONTEXT_BARS)
    if not ha:
        return None, "无 horizon 段"

    if set(ha) != set(hb):
        return None, "两次返回通道不一致"
    for k in ha:
        if not np.array_equal(ha[k], hb[k]):
            return "self_referential", "horizon 随 predicted_* 变化 (%s)" % k

    if all(np.allclose(ha[k], 0.0) for k in ha):
        return "unknowable", "horizon 全零"

    return "persistence", "horizon 不随 predicted_* 变化且非全零"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    pool = json.loads(POOL.read_text(encoding="utf-8"))
    covs = pool["covariates"]

    results, undecided = {}, []
    for cov in sorted(covs):
        votes = {}
        for sym in PROBE_SYMBOLS:
            try:
                label, why = probe_one(sym, cov)
            except Exception as e:
                label, why = None, str(e)[:50]
            if label:
                votes.setdefault(label, []).append(sym)
            else:
                votes.setdefault("_why", []).append("%s:%s" % (sym, why))
        decided = {k: v for k, v in votes.items() if k != "_why"}
        if len(decided) == 1:
            results[cov] = (list(decided)[0], ",".join(list(decided.values())[0]))
        elif len(decided) > 1:
            undecided.append((cov, "品种间不一致: %s" % decided))
        else:
            undecided.append((cov, "; ".join(votes.get("_why", []))[:80]))

    # ── 本探针**不能**判定的两类，必须排除，不得据此改判 ──────────────
    #
    # 1) known_ahead：探针只测「horizon 是否随 predicted_* 变化」。
    #    known_ahead 与 persistence 在这一测下表现**完全相同**（都不变），
    #    故探针会把日历类误判为 persistence。要判 known_ahead 需另一个
    #    探针：扰动 **cutoff 之后**的数据，看 horizon 是否不变。
    #
    # 2) spec 点名的 unknowable 示例：W5.1 明确列「库存、持仓、基差、基本面」
    #    为 unknowable，理由是「既不可知**也无法近似**」。而代码对它们仍
    #    填了末值/衰减，于是探针会判成 persistence。
    #    差别在于：spec 的标签编码的是**「末值延续对该量是否算合法近似」
    #    这一判断**，不只是代码路径。探针只测代码行为，无权推翻该判断。
    SPEC_UNKNOWABLE = {"ccl", "oi", "nvi", "basis_momentum", "crack_spread_level"}

    def _probe_authoritative(cov: str) -> str:
        cur = covs[cov].get("horizon_known")
        if cur == "known_ahead":
            return "探针无法判定 known_ahead（与 persistence 同表现）"
        if cov in SPEC_UNKNOWABLE:
            return "spec W5.1 点名该类为 unknowable（判断层，探针无权改）"
        return ""

    changes, guarded = [], []
    for c, (lbl, why) in sorted(results.items()):
        if covs[c].get("horizon_known") == lbl:
            continue
        g = _probe_authoritative(c)
        (guarded if g else changes).append((c, covs[c].get("horizon_known"), lbl, g or why))

    if guarded:
        print("=== 探针无权改判，已挡下 (%d) ===" % len(guarded))
        for c, cur, new, why in guarded:
            print("  %-28s %-16s (探针判 %s)  %s" % (c, cur, new, why))
        print()


    print("=== 需改判 (%d) ===" % len(changes))
    for c, cur, new, why in changes:
        print("  %-28s %-16s -> %-16s   %s" % (c, cur, new, why))

    print("\n=== 已一致 (%d) ===" % (len(results) - len(changes)))
    for c, (lbl, _) in sorted(results.items()):
        if covs[c].get("horizon_known") == lbl:
            print("  %-28s %s" % (c, lbl))

    print("\n=== 无法判定 (%d) ===" % len(undecided))
    for c, why in undecided:
        print("  %-28s %s" % (c, why))

    if args.write:
        if undecided:
            print("\n[REFUSE] 有 %d 项无法判定，拒绝落盘" % len(undecided),
                  file=sys.stderr)
            return 2
        if guarded:
            print("\n[REFUSE] 有 %d 项探针无权改判，拒绝落盘"
                  "（探针只测代码行为，无法替代 spec 的判断层）" % len(guarded),
                  file=sys.stderr)
            return 2
        for c, _, new, _ in changes:
            covs[c]["horizon_known"] = new
        POOL.write_text(json.dumps(pool, indent=1, ensure_ascii=False),
                        encoding="utf-8")
        print("\n已写入 %s（%d 项改判）" % (POOL, len(changes)))
    else:
        print("\n（未落盘；加 --write 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
