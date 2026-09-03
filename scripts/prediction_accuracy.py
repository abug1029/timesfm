#!/usr/bin/env python3
"""
prediction_accuracy.py — FM_a 期货版 1H 预测精度追踪

对比历史级联预测的逐小时价格与实际 1H 收盘价，输出精度评估报告。

核心逻辑:
1. 找到距今 ≥2 天的报告目录
2. 从 summary.md 提取品种方向，从 cascade_*.md 提取逐小时预测
3. 从 kline_1h 查询对应小时的实际收盘价
4. 计算逐小时 MAPE、方向准确率

用法:
    python scripts/prediction_accuracy.py
"""

import os
import re
import sys
import sqlite3
import glob

# Windows UTF-8 输出修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径 ─────────────────────────────────────────────
FM_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = FM_ROOT / "reports"
DB_DIR = FM_ROOT / "db"


# ── 品种 → DB 映射 ──────────────────────────────────

def get_db_path(symbol_code: str) -> Path:
    """品种缩写 → 数据库文件路径。BU → db/futures_bu.db"""
    code = symbol_code.strip().lower()
    return DB_DIR / f"futures_{code}.db"


# ── 报告目录解析 ──────────────────────────────────────

def parse_report_dirs():
    """扫描 reports/ 下所有时间戳目录，返回 (datetime, path) 列表（升序）。"""
    results = []
    if not REPORTS_DIR.exists():
        return results
    for d in REPORTS_DIR.iterdir():
        if not d.is_dir():
            continue
        m = re.match(r"^(\d{8})_(\d{4})$", d.name)
        if not m:
            continue
        try:
            dt = datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M")
            results.append((dt, d))
        except ValueError:
            continue
    results.sort(key=lambda x: x[0])
    return results


# ── summary.md 解析 ──────────────────────────────────

def parse_summary_directions(summary_path: Path) -> list[dict]:
    """从 summary.md 的"方向总览"表格提取品种方向。

    返回 list of dict: {symbol, full_name, direction, t1_value, t24_value}
    """
    rows = []
    if not summary_path.exists():
        return rows

    text = summary_path.read_text(encoding="utf-8")
    dir_map = {"↑": "bull", "↓": "bear", "→": "neutral"}

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if len(cells) < 4:
            continue
        # 跳过分隔行和表头
        if re.match(r"^[-:]+$", cells[0]):
            continue
        if cells[0] in ("品种", "字段"):
            continue

        name_part = cells[0]
        dir_part = cells[1]

        # 品种缩写
        sym_match = re.match(r"([A-Za-z0-9]+)", name_part)
        if not sym_match:
            continue
        symbol = sym_match.group(1)

        # 方向
        direction = "neutral"
        for arrow, d in dir_map.items():
            if arrow in dir_part:
                direction = d
                break

        # T+1 和 T+24 值
        try:
            t1_value = float(cells[2].replace(",", ""))
        except (ValueError, TypeError):
            t1_value = None
        try:
            t24_value = float(cells[3].replace(",", ""))
        except (ValueError, TypeError):
            t24_value = None

        rows.append({
            "symbol": symbol,
            "full_name": name_part,
            "direction": direction,
            "t1_value": t1_value,
            "t24_value": t24_value,
        })

    return rows


# ── cascade_*.md 解析 ───────────────────────────────

def parse_last_kline_dt(cascade_path: Path) -> datetime | None:
    """从 cascade_*.md 的"数据范围"行提取最后一根 K 线的时间。

    报告格式: **数据范围**: 2026-04-08 13:00 ~ 2026-06-29 14:00 (480 根 K 线)
    返回: datetime(2026, 6, 29, 14, 0) 或 None
    """
    if not cascade_path.exists():
        return None
    text = cascade_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "数据范围" in line and "~" in line:
            # 提取 ~ 后面的日期时间
            m = re.search(r"~\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", line)
            if m:
                try:
                    return datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M")
                except ValueError:
                    pass
    return None


def parse_hourly_predictions(cascade_path: Path) -> list[dict]:
    """从 cascade_*.md 的"逐小时预测"表格提取 T+1~T+24 预测值。

    返回 list of dict: {hour: int, pred: float}
    """
    rows = []
    if not cascade_path.exists():
        return rows

    text = cascade_path.read_text(encoding="utf-8")
    in_hourly_table = False

    for line in text.splitlines():
        line = line.strip()
        # 检测逐小时预测表
        if "逐小时预测" in line:
            in_hourly_table = True
            continue
        if not in_hourly_table:
            continue
        if not line.startswith("|"):
            if in_hourly_table and line and not line.startswith("|"):
                # 表格结束
                if not any(c == "|" for c in line):
                    break
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if len(cells) < 2:
            continue
        # 跳过分隔行
        if re.match(r"^[-:]+$", cells[0]):
            continue
        # 跳过表头 (兼容新旧格式: "Hour" 在 cells[0] 或 cells[1])
        if cells[0] in ("Hour", "小时") or (len(cells) > 1 and cells[1] in ("Hour", "小时")):
            continue

        # 解析 T+N — 动态查找 (兼容有时间列的新格式)
        hour_idx = None
        for ci, cell in enumerate(cells):
            hour_match = re.match(r"T\+(\d+)", cell)
            if hour_match:
                hour_idx = ci
                break
        if hour_idx is None:
            continue
        hour = int(re.match(r"T\+(\d+)", cells[hour_idx]).group(1))

        try:
            pred = float(cells[hour_idx + 1].replace(",", ""))
        except (ValueError, TypeError):
            continue

        rows.append({"hour": hour, "pred": pred})

    return rows


# ── 交易时段小时映射 ─────────────────────────────────

def get_trading_hours(base_dt: datetime) -> list[datetime]:
    """从基准时间开始，生成 T+1 ~ T+24 对应的实际交易小时时间戳。

    期货交易时段:
    - 日盘: 09:00-10:15, 10:30-11:30, 13:30-15:00
    - 夜盘: 21:00-23:00 (部分品种到凌晨)

    为简化，假设每小时一根 K 线，跳过非交易时段。
    """
    # 简化版: 每根 1H K 线的 dt 格式为 "YYYY-MM-DD HH:MM:SS"
    # 实际交易小时: 10:00, 11:00, 13:30(视为14:00), 14:00, 15:00, 21:00, 22:00, 23:00...
    # 这里用固定偏移: 从基准时间起每 1 小时，跳过 12:00-13:00 午休

    trading_hours = []
    current = base_dt.replace(minute=0, second=0)

    # 交易时段定义 (开始小时, 结束小时)
    day_sessions = [
        (9, 10.25),    # 09:00-10:15
        (10.5, 11.5),  # 10:30-11:30
        (13.5, 15),    # 13:30-15:00
    ]
    night_sessions = [
        (21, 23.99),   # 21:00-23:59 (简化)
    ]

    # 简化: 找到基准时间后的下一个交易小时
    hours_added = 0
    max_iterations = 100  # 安全上限

    while hours_added < 24 and max_iterations > 0:
        max_iterations -= 1
        current = current + timedelta(hours=1)
        hour = current.hour + current.minute / 60.0

        is_trading = False
        # 日盘
        if current.weekday() < 5:  # 工作日
            for start, end in day_sessions:
                if start <= hour <= end:
                    is_trading = True
                    break
            for start, end in night_sessions:
                if start <= hour <= end:
                    is_trading = True
                    break
        else:
            # 周末只有夜盘（周五夜盘到周六凌晨）
            if current.weekday() == 5 and hour < 1:
                is_trading = True

        if is_trading:
            hours_added += 1
            trading_hours.append(current)

    return trading_hours


# ── 数据库查询 ────────────────────────────────────────

def _connect(db_path: Path):
    """安全连接 SQLite，失败返回 None。"""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        return conn
    except Exception:
        return None


def get_1h_actuals(conn, target_hours: list[datetime]) -> dict[str, float]:
    """查询指定小时时间戳的实际收盘价。

    返回 {dt_str: close_price}
    """
    if not conn:
        return {}

    results = {}
    cur = conn.cursor()

    for hour_dt in target_hours:
        # kline_1h 的 dt 格式可能是 "YYYY-MM-DD HH:MM:SS" 或 "YYYY-MM-DD"
        date_str = hour_dt.strftime("%Y-%m-%d")
        hour_str = hour_dt.strftime("%H:%M")

        try:
            # 精确匹配小时
            cur.execute(
                """
                SELECT dt, close_price FROM kline_1h
                WHERE dt LIKE ?
                ORDER BY COALESCE(open_interest, 0) DESC
                LIMIT 1
                """,
                (f"{date_str} {hour_str}%",),
            )
            row = cur.fetchone()
            if row and row[1] is not None:
                results[hour_dt.strftime("%Y-%m-%d %H:00")] = float(row[1])
                continue

            # 宽松匹配: 该小时到下一整点的范围
            next_hour = (hour_dt.replace(minute=0, second=0) + timedelta(hours=1))
            cur.execute(
                """
                SELECT dt, close_price FROM kline_1h
                WHERE dt >= ? AND dt < ?
                ORDER BY COALESCE(open_interest, 0) DESC
                LIMIT 1
                """,
                (
                    hour_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    next_hour.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            row = cur.fetchone()
            if row and row[1] is not None:
                results[hour_dt.strftime("%Y-%m-%d %H:00")] = float(row[1])
        except Exception:
            continue

    return results


def get_daily_actual(db_path: Path, prediction_date_str: str):
    """获取预测日之后第一个交易日的主力连续收盘价 (回退方案)。"""
    conn = _connect(db_path)
    if not conn:
        return None, None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT dt, close_price FROM main_continuous_1d
            WHERE dt > ?
            ORDER BY dt ASC
            LIMIT 1
            """,
            (prediction_date_str,),
        )
        row = cur.fetchone()
        if row and row[1] is not None:
            return row[0], float(row[1])
        return None, None
    except Exception:
        return None, None
    finally:
        conn.close()


# ── 报告生成 ──────────────────────────────────────────

DIR_LABEL = {"bull": "看多 ↑", "bear": "看空 ↓", "neutral": "中性 →"}


def generate_report(results, report_dir_name, prediction_date_str, mode="1h"):
    """生成 Markdown 格式的精度评估报告。"""
    lines = [
        "# 预测精度评估报告 (FM_a 期货版)",
        "",
        f"- **报告目录**: `{report_dir_name}`",
        f"- **预测日期**: {prediction_date_str}",
        f"- **对比模式**: {'1H 逐小时' if mode == '1h' else 'T+1 日线'}",
        "",
    ]

    valid = [r for r in results if r.get("actual") is not None or r.get("hourly_matches")]
    skipped = [r for r in results if r.get("actual") is None and not r.get("hourly_matches")]

    if not valid:
        lines.append("> 所有品种均无实际数据可供对比（数据库可能尚未更新）。")
        return "\n".join(lines)

    # ── 明细表 ──
    lines += [
        "## 逐品种对比",
        "",
    ]

    if mode == "1h":
        lines += [
            "| 品种 | 方向 | 匹配小时数 | 1H MAPE | 1H 方向准确率 | 平均偏差 |",
            "|------|:----:|:---------:|--------:|:-----------:|--------:|",
        ]
    else:
        lines += [
            "| 品种 | 方向 | T+1 预测 | 实际收盘 | 误差% | 方向匹配 |",
            "|------|:----:|--------:|--------:|------:|:-------:|",
        ]

    all_hourly_errors = []
    all_hourly_dir_hits = 0
    all_hourly_dir_total = 0

    for r in valid:
        if mode == "1h" and r.get("hourly_matches"):
            matches = r["hourly_matches"]
            total_hours = len(matches)
            matched_hours = sum(1 for m in matches if m.get("actual") is not None)

            if matched_hours > 0:
                errors = [
                    abs(m["pred"] - m["actual"]) / m["actual"] * 100
                    for m in matches
                    if m.get("actual") is not None
                ]
                mape = sum(errors) / len(errors) if errors else 0
                avg_dev = sum(m["pred"] - m["actual"] for m in matches if m.get("actual")) / matched_hours
                dir_hits = sum(
                    1 for m in matches
                    if m.get("actual") is not None and (
                        (m["pred"] > m["actual"] and r["direction"] == "bull") or
                        (m["pred"] < m["actual"] and r["direction"] == "bear") or
                        (abs(m["pred"] - m["actual"]) / m["actual"] < 0.001 and r["direction"] == "neutral")
                    )
                )
                dir_acc = dir_hits / matched_hours * 100

                all_hourly_errors.extend(errors)
                all_hourly_dir_hits += dir_hits
                all_hourly_dir_total += matched_hours

                err_flag = " ⚠" if mape > 2 else ""
                lines.append(
                    f"| {r['full_name']} "
                    f"| {DIR_LABEL.get(r['direction'], r['direction'])} "
                    f"| {matched_hours}/{total_hours} "
                    f"| {mape:.2f}%{err_flag} "
                    f"| {dir_acc:.0f}% ({dir_hits}/{matched_hours}) "
                    f"| {avg_dev:+.1f} |"
                )
            else:
                lines.append(
                    f"| {r['full_name']} "
                    f"| {DIR_LABEL.get(r['direction'], r['direction'])} "
                    f"| 0/{total_hours} "
                    f"| — | — | — |"
                )
        elif r.get("actual") is not None:
            err = abs(r["predicted"] - r["actual"]) / r["actual"] * 100
            dmark = "✓" if r.get("dir_match") else "✗"
            err_flag = " ⚠" if err > 3 else ""
            lines.append(
                f"| {r['full_name']} "
                f"| {DIR_LABEL.get(r['direction'], r['direction'])} "
                f"| {r['predicted']:,.0f} "
                f"| {r['actual']:,.0f} "
                f"| {err:.2f}%{err_flag} "
                f"| {dmark} |"
            )

    # ── 汇总 ──
    lines += ["", "## 汇总统计", ""]

    if mode == "1h" and all_hourly_errors:
        avg_mape = sum(all_hourly_errors) / len(all_hourly_errors)
        dir_acc = all_hourly_dir_hits / all_hourly_dir_total * 100 if all_hourly_dir_total else 0
        lines += [
            "| 指标 | 值 |",
            "|------|------|",
            f"| 可对比品种数 | {len(valid)} |",
            f"| 总对比小时数 | {len(all_hourly_errors)} |",
            f"| 平均 1H MAPE | {avg_mape:.2f}% |",
            f"| 1H 方向准确率 | {dir_acc:.1f}% ({all_hourly_dir_hits}/{all_hourly_dir_total}) |",
        ]
    else:
        errors = [
            abs(r["predicted"] - r["actual"]) / r["actual"] * 100
            for r in valid if r.get("actual") is not None
        ]
        dir_hits = sum(1 for r in valid if r.get("dir_match"))
        avg_mape = sum(errors) / len(errors) if errors else 0
        dir_acc = dir_hits / len(valid) * 100 if valid else 0
        lines += [
            "| 指标 | 值 |",
            "|------|------|",
            f"| 可对比品种数 | {len(valid)} |",
            f"| 平均 MAPE | {avg_mape:.2f}% |",
            f"| 方向准确率 | {dir_acc:.1f}% ({dir_hits}/{len(valid)}) |",
        ]

    # ── 高误差警报 ──
    if mode != "1h":
        alerts = [r for r in valid
                  if r.get("actual") and abs(r["predicted"] - r["actual"]) / r["actual"] * 100 > 3]
        if alerts:
            lines += ["", "## ⚠ 高误差警报 (误差 > 3%)", ""]
            for r in alerts:
                err = abs(r["predicted"] - r["actual"]) / r["actual"] * 100
                lines.append(
                    f"- **{r['full_name']}**: 预测 {r['predicted']:,.0f}，"
                    f"实际 {r['actual']:,.0f}，误差 {err:.2f}%"
                )

    # ── 缺失数据说明 ──
    if skipped:
        lines += ["", "## 数据缺失", ""]
        for r in skipped:
            lines.append(f"- {r['full_name']}: 无实际数据")

    return "\n".join(lines)


# ── 主入口 ────────────────────────────────────────────

def find_eligible_report_dir():
    """找到最早的、距今至少 2 个自然日、且 summary.md 存在的报告目录。"""
    all_dirs = parse_report_dirs()
    today = datetime.now().date()

    for dt, path in all_dirs:
        if (today - dt.date()).days >= 2:
            if (path / "summary.md").exists():
                return dt, path

    return None, None


def main():
    report_dt, report_dir = find_eligible_report_dir()

    if not report_dir:
        print("无历史预测可供对比 (需要 ≥2 天前的报告)")
        return

    report_dir_name = report_dir.name
    prediction_date_str = report_dt.strftime("%Y-%m-%d")

    # 从 summary.md 获取品种方向和 T+1 值
    summary_rows = parse_summary_directions(report_dir / "summary.md")
    if not summary_rows:
        print("无有效预测数据可解析")
        return

    results = []
    mode = "1h"  # 默认尝试 1H 对比

    for row in summary_rows:
        symbol = row["symbol"]
        db_path = get_db_path(symbol)

        # 尝试从 cascade_*.md 读取逐小时预测
        cascade_path = report_dir / f"cascade_{symbol.lower()}.md"
        hourly_preds = parse_hourly_predictions(cascade_path)

        result = {
            "symbol": symbol,
            "full_name": row["full_name"],
            "direction": row["direction"],
            "predicted": row["t1_value"],
            "actual": None,
            "actual_date": None,
            "dir_match": False,
            "hourly_matches": [],
        }

        if hourly_preds:
            # 1H 对比模式
            # C1 fix: 从报告解析最后一根 K 线时间作为基准（非报告运行时间）
            last_kline_dt = parse_last_kline_dt(cascade_path)
            base_dt = last_kline_dt if last_kline_dt else report_dt
            trading_hours = get_trading_hours(base_dt)
            conn = _connect(db_path)

            if conn:
                # M1 fix: 优先使用 {SYMBOL}_MAIN（主力连续合约），它覆盖所有交易时段
                cur = conn.cursor()
                main_contract = f"{symbol.upper()}_MAIN"
                # 验证 _MAIN 合约是否有数据
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM kline_1h WHERE contract_code = ?",
                        (main_contract,),
                    )
                    if cur.fetchone()[0] == 0:
                        # _MAIN 无数据，回退到 main_continuous_1d 查合约
                        cur.execute(
                            """
                            SELECT contract_code FROM main_continuous_1d
                            WHERE dt <= ?
                            ORDER BY dt DESC LIMIT 1
                            """,
                            (prediction_date_str,),
                        )
                        mc_row = cur.fetchone()
                        main_contract = mc_row[0] if mc_row else None
                except Exception:
                    main_contract = None

                for i, pred_info in enumerate(hourly_preds):
                    hour = pred_info["hour"]
                    pred = pred_info["pred"]

                    # 找到对应的交易时间
                    if hour - 1 < len(trading_hours):
                        target_dt = trading_hours[hour - 1]
                        date_str = target_dt.strftime("%Y-%m-%d")
                        hour_str = target_dt.strftime("%H")

                        try:
                            if main_contract:
                                cur.execute(
                                    """
                                    SELECT close_price FROM kline_1h
                                    WHERE dt LIKE ? AND contract_code = ?
                                    LIMIT 1
                                    """,
                                    (f"{date_str} {hour_str}:%", main_contract),
                                )
                            else:
                                cur.execute(
                                    """
                                    SELECT close_price FROM kline_1h
                                    WHERE dt LIKE ?
                                    ORDER BY COALESCE(open_interest, 0) DESC
                                    LIMIT 1
                                    """,
                                    (f"{date_str} {hour_str}%",),
                                )
                            actual_row = cur.fetchone()
                            actual = float(actual_row[0]) if actual_row and actual_row[0] else None
                        except Exception:
                            actual = None

                        result["hourly_matches"].append({
                            "hour": hour,
                            "pred": pred,
                            "actual": actual,
                            "target_dt": target_dt.strftime("%Y-%m-%d %H:00"),
                        })
                    else:
                        result["hourly_matches"].append({
                            "hour": hour,
                            "pred": pred,
                            "actual": None,
                        })

                conn.close()

            # 如果 1H 数据太少，回退到日线对比
            matched = sum(1 for m in result["hourly_matches"] if m["actual"] is not None)
            if matched < 3:
                # 回退到 T+1 日线
                actual_dt, actual_close = get_daily_actual(db_path, prediction_date_str)
                result["actual"] = actual_close
                result["actual_date"] = actual_dt
                if actual_close and row["t1_value"]:
                    actual_pct = (actual_close - row["t1_value"]) / row["t1_value"] * 100
                    if actual_pct > 0.1:
                        actual_dir = "bull"
                    elif actual_pct < -0.1:
                        actual_dir = "bear"
                    else:
                        actual_dir = "neutral"
                    result["dir_match"] = actual_dir == row["direction"]
                result["hourly_matches"] = []
        else:
            # 无逐小时数据，回退到 T+1 日线
            actual_dt, actual_close = get_daily_actual(db_path, prediction_date_str)
            result["actual"] = actual_close
            result["actual_date"] = actual_dt
            if actual_close and row["t1_value"]:
                actual_pct = (actual_close - row["t1_value"]) / row["t1_value"] * 100
                if actual_pct > 0.1:
                    actual_dir = "bull"
                elif actual_pct < -0.1:
                    actual_dir = "bear"
                else:
                    actual_dir = "neutral"
                result["dir_match"] = actual_dir == row["direction"]
            mode = "daily"

        results.append(result)

    # 判断最终模式
    has_hourly = any(r["hourly_matches"] for r in results)
    report = generate_report(results, report_dir_name, prediction_date_str,
                             mode="1h" if has_hourly else "daily")
    print(report)


if __name__ == "__main__":
    main()
