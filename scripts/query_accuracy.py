"""查询各固化品种最新预测 + 回测准确率"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from config.prediction_scheme import SCHEMES

rows = []
for sym, sc in sorted(SCHEMES.items()):
    pred_file = Path("reports/history") / sym.lower() / "predictions.json"
    latest_t1 = latest_t24 = change = direction = "-"
    pred_count = 0
    pred_time = ""
    if pred_file.exists():
        with open(pred_file, encoding="utf-8") as f:
            preds = json.load(f)
        pred_count = len(preds)
        if preds:
            la = preds[-1]
            latest_t1 = str(round(la.get("pred_t1", 0), 1)) if la.get("pred_t1") else "-"
            latest_t24 = str(round(la.get("pred_t24", 0), 1)) if la.get("pred_t24") else "-"
            ch = la.get("expected_change_pct", None)
            if ch is None:
                cp = la.get("current_price", 0)
                if cp and cp > 0:
                    ch = (la.get("pred_t24", 0) - cp) / cp * 100
            change = "{:+.2f}%".format(ch) if ch is not None else "-"
            direction = la.get("direction", "-")
            pred_time = la.get("timestamp", "")[:16]

    strategy = "全段" if sc.use_full_signal else "短段"
    star_str = "{}star".format(sc.stars)

    rows.append({
        "symbol": sym.upper(),
        "name": sc.name,
        "stars": star_str,
        "type": sc.scheme_type,
        "dir_acc": sc.dir_acc,
        "mape": sc.mape,
        "decay": sc.decay,
        "strategy": strategy,
        "pred_count": pred_count,
        "time": pred_time,
        "direction": direction,
        "t1": latest_t1,
        "t24": latest_t24,
        "change": change,
    })

# 按 DirAcc 降序排列
rows.sort(key=lambda r: r["dir_acc"], reverse=True)

# 输出表格
header = "{:<8} {:<6} {:>4} {:<10} {:>6} {:>6} {:>5} {:<4} {:>4} {:<16} {:<6} {:>8} {:>8} {:>8}"
print(header.format(
    "品种", "名称", "星级", "类型", "DirAcc", "MAPE", "衰减", "策略", "次数",
    "最新时间", "方向", "T+1", "T+24", "预期变动"
))
print("=" * 130)
for r in rows:
    print(header.format(
        r["symbol"], r["name"], r["stars"], r["type"],
        "{}%".format(r["dir_acc"]),
        "{:.2f}%".format(r["mape"]),
        "{:.2f}x".format(r["decay"]),
        r["strategy"],
        r["pred_count"],
        r["time"],
        r["direction"],
        r["t1"],
        r["t24"],
        r["change"],
    ))
