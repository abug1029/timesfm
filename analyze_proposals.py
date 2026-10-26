import json, os, glob, re
from collections import defaultdict, Counter
from datetime import datetime, timedelta

EXPERIMENTS = "/home/abug/timesfm/task_FM/experiments"
VERDICTS_PATH = "/home/abug/timesfm/task_FM/config/aligned_verdicts.jsonl"

prescreen_stats = []
for ps_path in glob.glob(EXPERIMENTS + "/**/proposals/*.prescreen.json", recursive=True):
    try:
        m = re.search(r"run_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", ps_path)
        if not m:
            continue
        run_dt = datetime.strptime(m.group(1), "%Y-%m-%d_%H-%M-%S")
        with open(ps_path) as f:
            ps = json.load(f)
        prescreen_stats.append({
            "dt": run_dt,
            "status": ps.get("status", "unknown"),
            "plausibility": ps.get("mechanism_plausibility") or ps.get("plausibility"),
            "novelty": (ps.get("novelty") or "").lower(),
            "effect_size": ps.get("effect_size"),
            "skip": ps.get("skip_suggested"),
        })
    except Exception:
        continue

print("总 prescreen 文件数:", len(prescreen_stats))
if not prescreen_stats:
    print("无 prescreen 数据")
    exit()
min_dt = min(p["dt"] for p in prescreen_stats)
max_dt = max(p["dt"] for p in prescreen_stats)
print("时间范围:", min_dt.strftime("%Y-%m-%d %H:%M"), "->", max_dt.strftime("%Y-%m-%d %H:%M"))

# 按月聚合
monthly = defaultdict(lambda: {"total": 0, "success": 0, "degraded": 0, "error": 0,
                                "plausibility": [], "effect_size": [], "novelty": Counter()})
for p in prescreen_stats:
    mk = p["dt"].strftime("%Y-%m")
    monthly[mk]["total"] += 1
    monthly[mk][p["status"]] = monthly[mk].get(p["status"], 0) + 1
    if p["plausibility"] is not None:
        monthly[mk]["plausibility"].append(p["plausibility"])
    if p["effect_size"] is not None:
        monthly[mk]["effect_size"].append(p["effect_size"])
    if p["novelty"]:
        monthly[mk]["novelty"][p["novelty"]] += 1

print("\n=== Prescreen 月度统计 ===")
print(f"{'月份':<10} {'总数':>5} {'success':>8} {'degraded':>9} {'error':>6} {'成功率':>7} {'plaus均':>8} {'eff均':>6}")
for month in sorted(monthly.keys()):
    m = monthly[month]
    sr = m["success"] / m["total"] * 100 if m["total"] > 0 else 0
    pa = sum(m["plausibility"]) / len(m["plausibility"]) if m["plausibility"] else 0
    ea = sum(m["effect_size"]) / len(m["effect_size"]) if m["effect_size"] else 0
    print(f"{month:<10} {m['total']:>5} {m['success']:>8} {m.get('degraded',0):>9} {m.get('error',0):>6} {sr:>6.1f}% {pa:>8.3f} {ea:>6.2f}")

# 最近 24h vs 历史
cutoff_24h = max_dt - timedelta(hours=24)
recent = [p for p in prescreen_stats if p["dt"] >= cutoff_24h]
historical = [p for p in prescreen_stats if p["dt"] < cutoff_24h]

print("\n=== Prescreen 最近 24h vs 历史 ===")
for label, subset in [("最近 24h", recent), ("历史", historical)]:
    if not subset:
        print(f"{label}: 无数据")
        continue
    total = len(subset)
    success = sum(1 for p in subset if p["status"] == "success")
    plaus_vals = [p["plausibility"] for p in subset if p["plausibility"] is not None]
    eff_vals = [p["effect_size"] for p in subset if p["effect_size"] is not None]
    novelty_c = Counter(p["novelty"] for p in subset if p["novelty"])
    print(f"\n{label} ({total} 个):")
    print(f"  success 率: {success}/{total} = {success/total*100:.1f}%")
    if plaus_vals:
        print(f"  plausibility: mean={sum(plaus_vals)/len(plaus_vals):.3f}, min={min(plaus_vals):.3f}, max={max(plaus_vals):.3f}")
    if eff_vals:
        print(f"  effect_size: mean={sum(eff_vals)/len(eff_vals):.2f}")
    if novelty_c:
        print(f"  novelty 分布: {dict(novelty_c)}")

# 提取 verdict
verdict_stats = []
if os.path.exists(VERDICTS_PATH):
    with open(VERDICTS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
                da = v.get("decided_at", "")
                if not da:
                    continue
                v_dt = datetime.fromisoformat(da.split("+")[0].split(".")[0])
                verdict_stats.append({
                    "dt": v_dt,
                    "gate_pass": v.get("gate_pass", False),
                    "dir_acc": v.get("dir_acc"),
                    "tier": v.get("tier", ""),
                    "p_value": v.get("p_value"),
                    "fdr_pass": v.get("fdr_pass", False),
                    "ev": v.get("ev"),
                    "symbol": v.get("symbol", ""),
                    "cov_family": v.get("cov_family", ""),
                })
            except Exception:
                continue

print(f"\n总 verdict 文件数: {len(verdict_stats)}")
if not verdict_stats:
    print("无 verdict 数据")
    exit()
min_v_dt = min(v["dt"] for v in verdict_stats)
max_v_dt = max(v["dt"] for v in verdict_stats)
print("时间范围:", min_v_dt.strftime("%Y-%m-%d %H:%M"), "->", max_v_dt.strftime("%Y-%m-%d %H:%M"))

# 按月聚合 verdict
v_monthly = defaultdict(lambda: {"total": 0, "gate_pass": 0, "dir_acc": [], "tier": Counter(), "ev": []})
for v in verdict_stats:
    mk = v["dt"].strftime("%Y-%m")
    v_monthly[mk]["total"] += 1
    if v["gate_pass"]:
        v_monthly[mk]["gate_pass"] += 1
    if v["dir_acc"] is not None:
        v_monthly[mk]["dir_acc"].append(v["dir_acc"])
    if v["tier"]:
        v_monthly[mk]["tier"][v["tier"]] += 1
    if v["ev"] is not None:
        v_monthly[mk]["ev"].append(v["ev"])

print("\n=== Verdict 月度统计 ===")
print(f"{'月份':<10} {'总数':>5} {'gate_pass':>10} {'通过率':>7} {'dir_acc均':>9} {'S/A占比':>8} {'ev>0占比':>9}")
for month in sorted(v_monthly.keys()):
    m = v_monthly[month]
    pr = m["gate_pass"] / m["total"] * 100 if m["total"] > 0 else 0
    da = sum(m["dir_acc"]) / len(m["dir_acc"]) if m["dir_acc"] else 0
    sa = m["tier"].get("S", 0) + m["tier"].get("A", 0)
    sar = sa / m["total"] * 100 if m["total"] > 0 else 0
    evp = sum(1 for e in m["ev"] if e > 0) / len(m["ev"]) * 100 if m["ev"] else 0
    print(f"{month:<10} {m['total']:>5} {m['gate_pass']:>10} {pr:>6.1f}% {da:>9.4f} {sar:>7.1f}% {evp:>8.1f}%")

# 最近 24h vs 历史（verdict）
cutoff_v_24h = max_v_dt - timedelta(hours=24)
recent_v = [v for v in verdict_stats if v["dt"] >= cutoff_v_24h]
historical_v = [v for v in verdict_stats if v["dt"] < cutoff_v_24h]

print("\n=== Verdict 最近 24h vs 历史 ===")
for label, subset in [("最近 24h", recent_v), ("历史", historical_v)]:
    if not subset:
        print(f"{label}: 无数据")
        continue
    total = len(subset)
    gp = sum(1 for v in subset if v["gate_pass"])
    dir_vals = [v["dir_acc"] for v in subset if v["dir_acc"] is not None]
    tier_c = Counter(v["tier"] for v in subset if v["tier"])
    ev_vals = [v["ev"] for v in subset if v["ev"] is not None]
    print(f"\n{label} ({total} 个):")
    print(f"  gate_pass 率: {gp}/{total} = {gp/total*100:.1f}%")
    if dir_vals:
        a52 = sum(1 for d in dir_vals if d >= 0.52)
        print(f"  dir_acc: mean={sum(dir_vals)/len(dir_vals):.4f}, >=0.52: {a52}/{len(dir_vals)} ({a52/len(dir_vals)*100:.1f}%)")
    if tier_c:
        sa = tier_c.get("S", 0) + tier_c.get("A", 0)
        print(f"  tier 分布: {dict(tier_c)}, S/A 占比: {sa/total*100:.1f}%")
    if ev_vals:
        pos = sum(1 for e in ev_vals if e > 0)
        print(f"  ev>0: {pos}/{len(ev_vals)} ({pos/len(ev_vals)*100:.1f}%)")
