#!/usr/bin/env python3
"""
regime_detector.py — FM_a 跨品种联动监控

读取 drift_tracking.json，检测多品种同步退化（宏观 regime 切换信号）。

用法:
    python scripts/regime_detector.py
"""

import json
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = FM_ROOT / "reports"
DRIFT_FILE = REPORTS_DIR / "drift_tracking.json"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_EXCHANGE_MAP

# 告警阈值
WARNING_THRESHOLD = 5    # ≥5 品种同时 Warning
ALERT_THRESHOLD = 5      # ≥5 品种同时 Alert
SYSTEMIC_THRESHOLD = 10  # ≥10 品种同时 Warning → 系统性风险

# 交易所分组
EXCHANGE_GROUPS = {}
for sym, exchange in SYMBOL_EXCHANGE_MAP.items():
    EXCHANGE_GROUPS.setdefault(exchange, []).append(sym.lower())


def load_drift() -> dict:
    """读取 drift_detector 的输出。"""
    if not DRIFT_FILE.exists():
        return {}
    try:
        return json.loads(DRIFT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def detect_regime(drift_data: dict) -> dict:
    """检测跨品种联动信号。"""
    symbols = drift_data.get("symbols", {})
    if not symbols:
        return {"regime": "unknown", "message": "无漂移数据"}

    warning_syms = [s for s, d in symbols.items() if d.get("status") == "warning"]
    alert_syms = [s for s, d in symbols.items() if d.get("status") == "alert"]
    ok_syms = [s for s, d in symbols.items() if d.get("status") == "ok"]

    # 按交易所分组统计
    exchange_status = {}
    for exchange, syms in EXCHANGE_GROUPS.items():
        ex_alerts = [s for s in syms if s in alert_syms]
        ex_warnings = [s for s in syms if s in warning_syms]
        exchange_status[exchange] = {
            "total": len(syms),
            "alerts": ex_alerts,
            "warnings": ex_warnings,
        }

    # 判定 regime
    regime = "normal"
    message = "市场正常"

    if len(alert_syms) >= ALERT_THRESHOLD:
        regime = "regime_shift"
        message = f"宏观 regime 切换（{len(alert_syms)} 品种告警），建议暂停自动修改"
    elif len(warning_syms) >= SYSTEMIC_THRESHOLD:
        regime = "systemic_risk"
        message = f"系统性风险信号（{len(warning_syms)} 品种预警）"
    elif len(warning_syms) >= WARNING_THRESHOLD:
        regime = "volatile"
        message = f"市场波动加大（{len(warning_syms)} 品种预警）"

    # 检测产业链联动（同交易所品种同步退化）
    correlated_exchanges = []
    for exchange, status in exchange_status.items():
        if len(status["alerts"]) + len(status["warnings"]) >= 3:
            correlated_exchanges.append({
                "exchange": exchange,
                "alert_count": len(status["alerts"]),
                "warning_count": len(status["warnings"]),
                "symbols": status["alerts"] + status["warnings"],
            })

    return {
        "regime": regime,
        "message": message,
        "total_symbols": len(symbols),
        "alert_count": len(alert_syms),
        "warning_count": len(warning_syms),
        "ok_count": len(ok_syms),
        "alert_symbols": alert_syms,
        "warning_symbols": warning_syms,
        "exchange_status": exchange_status,
        "correlated_exchanges": correlated_exchanges,
    }


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 🌐 跨品种联动报告\n")
    print(f"**时间**: {now_str}\n")

    drift_data = load_drift()
    if not drift_data:
        print("> drift_tracking.json 不存在，请先运行 drift_detector.py\n")
        json.dump({"status": "no_data"}, sys.stderr, ensure_ascii=False)
        return

    result = detect_regime(drift_data)

    # regime 状态
    regime_icons = {
        "normal": "✅",
        "volatile": "🟡",
        "systemic_risk": "🟠",
        "regime_shift": "🔴",
        "unknown": "⚪",
    }
    icon = regime_icons.get(result["regime"], "⚪")
    print(f"## {icon} {result['message']}\n")

    # 汇总
    print(f"| 指标 | 值 |")
    print(f"|------|------|")
    print(f"| 总品种 | {result['total_symbols']} |")
    print(f"| 🔴 告警 | {result['alert_count']} |")
    print(f"| 🟡 预警 | {result['warning_count']} |")
    print(f"| ✅ 正常 | {result['ok_count']} |")

    # 交易所联动
    if result.get("correlated_exchanges"):
        print(f"\n## 交易所联动\n")
        for ce in result["correlated_exchanges"]:
            syms = ", ".join(f"`{s}`" for s in ce["symbols"])
            print(f"- **{ce['exchange']}**: {ce['alert_count']} 告警 + {ce['warning_count']} 预警 → {syms}")

    # 告警品种明细
    if result["alert_symbols"]:
        print(f"\n## 🔴 告警品种\n")
        for s in result["alert_symbols"]:
            print(f"- `{s}`")

    if result["warning_symbols"]:
        print(f"\n## 🟡 预警品种\n")
        for s in result["warning_symbols"]:
            print(f"- `{s}`")

    # JSON to stderr
    json.dump({
        "regime": result["regime"],
        "message": result["message"],
        "alert_count": result["alert_count"],
        "warning_count": result["warning_count"],
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
