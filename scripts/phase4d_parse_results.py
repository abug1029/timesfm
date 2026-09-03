"""Phase 4d calendar_cyclical 回测结果解析器 (读 JSONL)

每行 JSONL: {"symbol":"<sym>","mode":"<mode>","metric":"<指标行>"}
按品种计算 Replace/Additive vs Baseline 的固化判定。

用法: python scripts/phase4d_parse_results.py [jsonl_path]
"""
import sys
import json
import re
from pathlib import Path

# 防御 Windows GBK 控制台: 强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_JSONL = Path(__file__).resolve().parents[1] / "reports" / "monthly_backtest" / "phase4d_incremental_results.jsonl"

# 指标行: EV_ratio= 无量纲 (历史日志可能仍为 EV= 别名，二者同语义)
# 396pts DirAcc=50%(ref) MAPE=2.50% decay=1.42x EV_ratio=+0.042 PF=1.09 MaxDD=-49.04% WR=48%
METRIC_RE = re.compile(
    r"(\d+)pts\s+DirAcc=(\d+)%\(ref\)\s+MAPE=([\d.]+)%\s+decay=([\d.]+)x\s+"
    r"(?:EV_ratio|EV)=([+-]?[\d.]+)\s+PF=([\d.]+)\s+MaxDD=(-?[\d.]+)%\s+WR=(\d+)%"
)

MAPE_REL_DROP = 0.03   # MAPE 相对下降 >=3% (MAE 代理, stdout 无 MAE)
DIRACC_DELTA = 3       # DirAcc 绝对提升 >=3pp
PF_REL_GAIN = 0.10     # PF 相对提升 >=10%

# v2 新判据阈值 (2026-07-30 Phase 4d 升级, 见 docs/validation_criteria.md)
MAXDD_WORSEN_VETO = 0.20      # Rule 1: MaxDD 相对恶化 >20% 一票否决
PF_DEGRADE_GUARD = 0.02       # Rule 2: 仅 MAPE 达标时 PF 退化 <=2%
EV_DELTA_MIN = 0.01           # Rule 4: EV 不显著退化阈值 (cand >= base - 0.01)
MAXDD_ABS_IMPROVE = 10.0      # Rule 4: MaxDD 绝对改善 >=10pp (|DD_base|-|DD_new|)
MAXDD_REL_IMPROVE = 0.30      # Rule 4: MaxDD 相对改善 >=30%
N_MIN = 350                   # Rule 5: n>=350 为有效门槛


def parse_metric(line):
    m = METRIC_RE.search(line or "")
    if not m:
        return None
    n, da, mape, dec, ev, pf, dd, wr = m.groups()
    return {
        "n": int(n), "diracc": int(da), "mape": float(mape),
        "decay": float(dec), "ev": float(ev), "pf": float(pf),
        "maxdd": float(dd), "wr": int(wr),
    }


def load(jsonl_path):
    rows = {}  # sym -> {mode: metrics}
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = parse_metric(rec.get("metric", ""))
            if not m:
                continue
            rows.setdefault(rec["symbol"], {})[rec["mode"]] = m
    return rows


def verdict(base, cand):
    """cand 相对 base 的 v2 固化判定。返回 (status, tag, reasons)。

    status:  'PASS' | 'GREEN-EV' | 'GREEN-MAXDD' | 'FAIL' | 'UNDERPOWERED'
    tag:     命中规则的简短标注 (如 'Rule3' / 'Rule4' / 'R1-VETO' / 'R2-GUARD' / 'ordinary' / '')
    reasons: 文本原因列表
    """
    if not base or not cand:
        return "FAIL", "", ["缺数据"]

    # Phase 8: crack_spread 行带 effective_n (feedstock 覆盖内评估点数);
    # 非跨品种行无此字段, fallback 到 cand["n"]
    n = cand.get("effective_n", cand["n"])
    b_ev, c_ev = base["ev"], cand["ev"]
    b_pf, c_pf = base["pf"], cand["pf"]
    b_dd, c_dd = base["maxdd"], cand["maxdd"]  # 负值
    b_mape, c_mape = base["mape"], cand["mape"]
    b_da, c_da = base["diracc"], cand["diracc"]

    # 预计算各项 delta
    mape_drop = (b_mape - c_mape) / b_mape if b_mape > 0 else 0
    da_delta = c_da - b_da
    pf_gain = (c_pf - b_pf) / b_pf if b_pf > 0 else 0
    pf_degrade = (b_pf - c_pf) / b_pf if b_pf > 0 else 0   # >0 表示退化
    # MaxDD 相对恶化 (>0 表示更糟: 回撤幅度 |DD| 变大)
    # 例: b=-35, c=-50 -> |c|-|b|=15 -> 15/35 = +43% 恶化
    # 例: b=-20, c=-10 -> |c|-|b|=-10 -> -50% (改善, 非恶化)
    maxdd_worsen = (abs(c_dd) - abs(b_dd)) / abs(b_dd) if b_dd != 0 else 0
    # MaxDD 相对改善 (>0 表示更好)
    maxdd_rel_improve = (abs(b_dd) - abs(c_dd)) / abs(b_dd) if b_dd != 0 else 0
    maxdd_abs_improve = abs(b_dd) - abs(c_dd)  # 百分点

    mape_ok = mape_drop >= MAPE_REL_DROP
    da_ok = da_delta >= DIRACC_DELTA
    pf_ok = pf_gain >= PF_REL_GAIN
    ordinary_pass = mape_ok or da_ok or pf_ok

    reasons = []
    if mape_ok:
        reasons.append(f"MAPE -{mape_drop*100:.1f}%")
    if da_ok:
        reasons.append(f"DirAcc +{da_delta}pp")
    if pf_ok:
        reasons.append(f"PF +{pf_gain*100:.1f}%")

    # Rule 1: MaxDD 一票否决 (无论绿色通道还是常规, 只要触发即否决)
    r1_veto = maxdd_worsen > MAXDD_WORSEN_VETO

    # ---- Step 1: 绿色通道 ----
    # Rule 3: EV 翻正 (base<0 且 cand>0)
    if b_ev < 0 < c_ev:
        reasons.insert(0, f"EV {b_ev:+.3f}->{c_ev:+.3f} 翻正")
        if r1_veto:
            reasons.append(f"R1-VETO: MaxDD 恶化 {maxdd_worsen*100:.1f}%>20%")
            return ("UNDERPOWERED" if n < N_MIN else "FAIL"), "R1-VETO", reasons
        return "GREEN-EV", "Rule3", reasons

    # Rule 4: MaxDD 大幅改善 + EV 未显著退化
    ev_not_degraded = (c_ev >= b_ev - EV_DELTA_MIN)
    maxdd_green = (maxdd_abs_improve >= MAXDD_ABS_IMPROVE) or (maxdd_rel_improve >= MAXDD_REL_IMPROVE)
    if ev_not_degraded and maxdd_green:
        reasons.insert(0, f"MaxDD {b_dd:.2f}%->{c_dd:.2f}% (改善 {maxdd_rel_improve*100:.1f}%)")
        reasons.append(f"EV {b_ev:+.3f}->{c_ev:+.3f} 未退化")
        if r1_veto:
            # 改善和恶化同时出现一般不可能, 但防御一下
            reasons.append(f"R1-VETO: MaxDD 恶化 {maxdd_worsen*100:.1f}%>20%")
            return ("UNDERPOWERED" if n < N_MIN else "FAIL"), "R1-VETO", reasons
        return "GREEN-MAXDD", "Rule4", reasons

    # ---- Step 2: 常规达标 ----
    if not ordinary_pass:
        reasons.append("常规维度未达阈值")
        if n < N_MIN:
            reasons.append(f"n={n}<{N_MIN} underpowered")
            return "UNDERPOWERED", "Rule5", reasons
        return "FAIL", "", reasons

    # ---- Step 3: 否决检查 ----
    if r1_veto:
        reasons.append(f"R1-VETO: MaxDD 恶化 {maxdd_worsen*100:.1f}%>20%")
        if n < N_MIN:
            reasons.append(f"n={n}<{N_MIN} underpowered")
            return "UNDERPOWERED", "R1-VETO", reasons
        return "FAIL", "R1-VETO", reasons

    # Rule 2: 仅 MAPE 达标时, PF 退化 <=2%
    only_mape = mape_ok and not da_ok and not pf_ok
    if only_mape and pf_degrade > PF_DEGRADE_GUARD:
        reasons.append(f"R2-GUARD: 仅 MAPE 达标且 PF 退化 {pf_degrade*100:.1f}%>2%")
        if n < N_MIN:
            reasons.append(f"n={n}<{N_MIN} underpowered")
            return "UNDERPOWERED", "R2-GUARD", reasons
        return "FAIL", "R2-GUARD", reasons
    if only_mape:
        reasons.append(f"R2 险过: PF 退化 {pf_degrade*100:.1f}%<=2%")

    # 常规 PASS
    if n < N_MIN:
        reasons.append(f"n={n}<{N_MIN} 小样本警示")
    return "PASS", "ordinary", reasons


def _replace_dominates(repl, add):
    """replace 是否全维不劣于 additive (MAPE<=, EV>=, PF>=, |MaxDD|<=)。用于建议逻辑二选一。"""
    if not repl or not add:
        return False
    return (repl["mape"] <= add["mape"] + 1e-9 and
            repl["ev"] >= add["ev"] - 1e-9 and
            repl["pf"] >= add["pf"] - 1e-9 and
            abs(repl["maxdd"]) <= abs(add["maxdd"]) + 1e-9)


def main():
    jsonl_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_JSONL
    if not jsonl_path.exists():
        print(f"JSONL not found: {jsonl_path}")
        return
    rows = load(jsonl_path)
    if not rows:
        print("no results parsed")
        return

    syms = sorted(rows)
    print("=" * 92)
    print("Phase 4d calendar_cyclical 回测对比表 (from JSONL)")
    print("=" * 92)
    print(f"{'sym':<4} {'mode':<10} {'n':>4} {'DirAcc':>7} {'MAPE%':>7} {'EV':>8} {'PF':>6} {'MaxDD%':>8} {'WR':>4}")
    print("-" * 92)
    for sym in syms:
        for mode in ("baseline", "replace", "additive"):
            r = rows[sym].get(mode)
            if r:
                print(f"{sym:<4} {mode:<10} {r['n']:>4} {str(r['diracc'])+'%':>7} "
                      f"{r['mape']:>7} {r['ev']:>+8} {r['pf']:>6} {r['maxdd']:>8} {r['wr']:>4}")
        print()

    print("=" * 110)
    print("固化判定 v2 (vs Baseline) - 规则详见 docs/validation_criteria.md")
    print("=" * 110)
    print(f"{'sym':<4} {'Replace':<30} {'Additive':<40} {'建议'}")
    print("-" * 110)
    for sym in syms:
        base = rows[sym].get("baseline")
        repl = rows[sym].get("replace")
        add = rows[sym].get("additive")
        r_status, r_tag, rrs = verdict(base, repl) if (base and repl) else ("N/A", "", [])
        a_status, a_tag, ars = verdict(base, add) if (base and add) else ("N/A", "", [])

        def fmt(status, tag, reasons):
            if status == "N/A":
                return "N/A"
            label = f"{status}"
            if tag:
                label += f"[{tag}]"
            detail = "; ".join(reasons) if reasons else ""
            return f"{label} {detail}"

        rtxt = fmt(r_status, r_tag, rrs)
        atxt = fmt(a_status, a_tag, ars)

        # 建议逻辑: 两者达标时对比 replace vs additive; replace 全维不劣于则选 replace (降噪)
        a_pass = a_status in ("PASS", "GREEN-EV", "GREEN-MAXDD")
        r_pass = r_status in ("PASS", "GREEN-EV", "GREEN-MAXDD")
        if a_pass and r_pass:
            if _replace_dominates(repl, add):
                sug = "固化 replace (剥离原协变量, 降噪)"
            else:
                sug = "固化 additive (+calendar_cyclical)"
        elif a_pass:
            sug = "固化 additive (+calendar_cyclical)"
        elif r_pass:
            sug = "固化 replace (仅 Replace 可用/达标)"
        elif a_status == "UNDERPOWERED" or r_status == "UNDERPOWERED":
            sug = "待复测 (n<350 负结果)"
        else:
            sug = "不固化 (负结果)"

        print(f"{sym:<4} {rtxt:<30} {atxt:<40} {sug}")
    print("=" * 110)
    print()
    print("状态标记: PASS=常规达标 | GREEN-EV=Rule3 EV翻正 | GREEN-MAXDD=Rule4 回撤大改善")
    print("          FAIL=未达标/否决 | UNDERPOWERED=n<350负结果 | R1-VETO=MaxDD否决 | R2-GUARD=PF保护否决")


if __name__ == "__main__":
    main()
