"""
期货数据完整性审计脚本

用法:
  python scripts/data_audit.py              # 审计 20 核心品种
  python scripts/data_audit.py cf rb ss     # 审计指定品种
  python scripts/data_audit.py --all        # 审计所有数据库

输出:
  reports/data_audit_YYYYMMDD_HHMM.md
"""

import sys
import os
import re
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.config import DEFAULT_SYMBOLS, get_name, SYMBOL_EXCHANGE_MAP, get_db_path
# list_all_dbs 已移除, 使用 DEFAULT_SYMBOLS
from data.data_store import DataStore


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class Finding:
    level: str        # CRITICAL, HIGH, MEDIUM, LOW, INFO
    dimension: str    # 触发维度
    symbol: str       # 品种代码
    message: str      # 错误描述
    action: str = ""  # 修复建议 (含 SQL)


# ── 审计器 ────────────────────────────────────────────────

class DataAuditor:
    """期货数据完整性审计器"""

    def __init__(self, symbols: list = None):
        self.symbols = symbols or DEFAULT_SYMBOLS

    def run(self) -> str:
        """运行审计，返回 Markdown 报告"""
        all_findings: List[Finding] = []
        symbol_stats = {}

        # 逐品种审计 (并发)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._audit_single, sym): sym
                for sym in self.symbols
            }
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    findings, stats = future.result()
                    all_findings.extend(findings)
                    symbol_stats[sym] = stats
                except Exception as e:
                    all_findings.append(Finding(
                        level="CRITICAL", dimension="系统",
                        symbol=sym, message=f"审计异常: {e}",
                        action="检查数据库文件是否损坏"
                    ))

        # 跨品种检查
        all_findings.extend(self.check_cross_symbol())

        return self._generate_report(all_findings, symbol_stats)

    def _audit_single(self, symbol: str) -> tuple:
        """审计单个品种，返回 (findings, stats)"""
        findings = []
        db_path = get_db_path(symbol)

        if not db_path.exists():
            findings.append(Finding(
                level="CRITICAL", dimension="系统",
                symbol=symbol, message=f"数据库文件不存在: {db_path}",
                action=f"python -m data.cli collect {symbol}"
            ))
            return findings, {"exists": False}

        with DataStore(symbol) as store:
            stats = self._get_stats(store)

            findings.extend(self.check_data_source_consistency(store, symbol))
            findings.extend(self.check_contract_alignment(store, symbol))
            findings.extend(self.check_price_continuity(store, symbol))
            findings.extend(self.check_time_continuity(store, symbol))
            findings.extend(self.check_indicator_correctness(store, symbol))
            findings.extend(self.check_adjustment_factor(store, symbol))
            findings.extend(self.check_field_completeness(store, symbol))
            findings.extend(self.check_oi_data(store, symbol))

        stats["exists"] = True
        return findings, stats

    def _get_stats(self, store: DataStore) -> dict:
        """获取品种数据概况"""
        conn = store.conn
        return {
            "kline_1d_count": conn.execute("SELECT COUNT(*) FROM kline_1d").fetchone()[0],
            "kline_1h_count": conn.execute("SELECT COUNT(*) FROM kline_1h").fetchone()[0],
            "main_count": conn.execute("SELECT COUNT(*) FROM main_continuous_1d").fetchone()[0],
            "latest_daily": conn.execute("SELECT MAX(dt) FROM main_continuous_1d").fetchone()[0],
            "latest_1h": conn.execute("SELECT MAX(dt) FROM kline_1h").fetchone()[0],
            # 新架构: kline_1d 统一为 {SYM}_CONT, 合约数恒为 1
            "contract_codes": conn.execute(
                "SELECT GROUP_CONCAT(DISTINCT contract_code) FROM kline_1d"
            ).fetchone()[0],
        }

    # ── 维度 1: 数据源一致性 ──

    def check_data_source_consistency(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 1a) kline_1d 合法格式为 {SYM}_CONT; 检查旧格式残留 (CF0/RB0) 或 _MAIN 混入
        rows = conn.execute("""
            SELECT contract_code, COUNT(*) as cnt, MIN(dt), MAX(dt)
            FROM kline_1d
            WHERE contract_code LIKE '%_MAIN'
               OR (contract_code LIKE '%0'
                   AND contract_code NOT GLOB '*[0-9][0-9][0-9][0-9]')
               OR (contract_code NOT LIKE '%_CONT'
                   AND contract_code NOT GLOB '[A-Za-z]*[0-9][0-9][0-9]'
                   AND contract_code NOT GLOB '[A-Za-z]*[0-9][0-9][0-9][0-9]')
            GROUP BY contract_code
        """).fetchall()
        for r in rows:
            findings.append(Finding(
                level="CRITICAL", dimension="数据源一致性",
                symbol=symbol,
                message=f"kline_1d 存在非 _CONT 合约 {r[0]} ({r[1]} 条, {r[2]}~{r[3]})",
                action=f"DELETE FROM kline_1d WHERE contract_code = '{r[0]}';"
            ))

        # 1a2) kline_1h 中的连续合约残留 (仅检查 CF0/RB0 格式，{SYMBOL}_MAIN 为合法历史数据)
        rows = conn.execute("""
            SELECT contract_code, COUNT(*) as cnt, MIN(dt), MAX(dt)
            FROM kline_1h
            WHERE contract_code LIKE '%0'
              AND contract_code NOT GLOB '*[0-9][0-9][0-9][0-9]'
              AND contract_code NOT LIKE '%_MAIN'
            GROUP BY contract_code
        """).fetchall()
        for r in rows:
            findings.append(Finding(
                level="CRITICAL", dimension="数据源一致性",
                symbol=symbol,
                message=f"kline_1h 存在连续合约 {r[0]} ({r[1]} 条, {r[2]}~{r[3]})",
                action=f"DELETE FROM kline_1h WHERE contract_code = '{r[0]}';"
            ))

        # 1b) main_continuous_1d 合约代码格式 (新架构: {SYM}_CONT)
        # 合法格式: CF_CONT, RB_CONT, SS_CONT 等; 旧格式 (CF2609) 标记为异常
        sym_upper = symbol.upper()
        expected_cont = f"{sym_upper}_CONT"
        rows = conn.execute("""
            SELECT contract_code, COUNT(*) as cnt
            FROM main_continuous_1d
            WHERE contract_code != ?
            GROUP BY contract_code
        """, (expected_cont,)).fetchall()
        for r in rows:
            findings.append(Finding(
                level="HIGH", dimension="数据源一致性",
                symbol=symbol,
                message=f"main_continuous_1d 异常合约代码: {r[0]} (期望 {expected_cont}, {r[1]} 条)",
                action="重新运行 MainChainBuilder.build()"
            ))

        # 1c) 交叉验证: 同合约同日 kline_1d 与 kline_1h 日盘末 bar close 一致
        # 日线 close = 结算价, 1H 14:00 bar ≈ 最后成交价, 允许 2% 差异
        rows = conn.execute("""
            SELECT d.dt, d.contract_code, d.close_price as d_close,
                   h.last_close as h_close,
                   ABS(d.close_price - h.last_close) as diff
            FROM kline_1d d
            JOIN (
                SELECT DATE(dt) as dt, contract_code,
                       close_price as last_close,
                       ROW_NUMBER() OVER (
                           PARTITION BY DATE(dt), contract_code
                           ORDER BY dt DESC
                       ) as rn
                FROM kline_1h
                WHERE strftime('%H', dt) IN ('14', '15')
            ) h ON d.dt = h.dt AND d.contract_code = h.contract_code AND h.rn = 1
            WHERE d.dt >= DATE('now', '-60 days')
              AND d.close_price > 0 AND h.last_close > 0
              AND ABS(d.close_price - h.last_close) / d.close_price > 0.02
            LIMIT 10
        """).fetchall()
        if rows:
            findings.append(Finding(
                level="HIGH", dimension="数据源一致性",
                symbol=symbol,
                message=f"近 60 天日盘收盘价差异 >2% ({len(rows)} 条)",
                action="可能来自不同数据源，以 TqSdk 为准重新采集",
            ))

        return findings

    # ── 维度 2: 合约对齐 ──

    def check_contract_alignment(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 2a) 主链合约在 kline_1d 中是否有对应数据 (近 60 天)
        rows = conn.execute("""
            SELECT m.dt, m.contract_code
            FROM main_continuous_1d m
            LEFT JOIN kline_1d k ON m.dt = k.dt AND m.contract_code = k.contract_code
            WHERE k.dt IS NULL
              AND m.dt >= DATE('now', '-60 days')
            LIMIT 10
        """).fetchall()
        if rows:
            findings.append(Finding(
                level="HIGH", dimension="合约对齐",
                symbol=symbol,
                message=f"近 60 天有 {len(rows)} 天主链合约在 kline_1d 中无数据",
                action=f"python -m data.cli collect {symbol}"
            ))

        # 2b) 已移除: "日线主力 vs 1H 主力" 检查有已知误报
        #     远月合约可能因历史数据量多而成为 1H 中出现最多的合约
        #     主力覆盖验证由 2c/2d 完成

        # 2c) 主力合约 1H 数据覆盖 (级联预测必需)
        # 新架构: main_continuous_1d 统一为 {SYM}_CONT, kline_1h 统一为 {SYM}_MAIN
        sym_upper = symbol.upper()
        main_contract = f"{sym_upper}_MAIN"
        # 检查 kline_1h 中 {SYM}_MAIN 数据是否存在
        h1_stats = conn.execute("""
            SELECT COUNT(*), MIN(DATE(dt)), MAX(DATE(dt))
            FROM kline_1h
            WHERE UPPER(contract_code) = UPPER(?)
        """, (main_contract,)).fetchone()
        h1_count, h1_min_date, h1_max_date = h1_stats
        if h1_count == 0:
            findings.append(Finding(
                level="HIGH", dimension="主力1H覆盖",
                symbol=symbol,
                message=f"主力合约 {main_contract} 无任何 1H 数据 (级联预测无法运行)",
                action=f"python scripts/collect_1h.py {symbol}"
            ))
        else:
            # 检查近期数据新鲜度 (最新 1H bar 距今)
            days_since = conn.execute("""
                SELECT CAST(JULIANDAY('now') - JULIANDAY(MAX(DATE(dt))) AS INTEGER)
                FROM kline_1h
                WHERE UPPER(contract_code) = UPPER(?)
            """, (main_contract,)).fetchone()[0]
            if days_since > 3:
                findings.append(Finding(
                    level="HIGH", dimension="主力1H覆盖",
                    symbol=symbol,
                    message=f"主力 {main_contract} 1H 数据滞后 {days_since} 天 (最新: {h1_max_date})",
                    action=f"python scripts/collect_1h.py {symbol}"
                ))

            # 检查近 20 交易日每日 bar 数 (仅检查过少，不检查过多)
            # 夜盘归属下一日历日期会导致某些日仅有日盘 bar (3-7根)
            # 周五夜盘归属周六，所以周五可能只有 3-7 根日盘 bar
            no_night = symbol.lower() in ('cj', 'jd', 'lh', 'ur')
            min_bars = 2 if no_night else 3
            sparse_days = conn.execute("""
                WITH daily_bars AS (
                    SELECT DATE(dt) as d, COUNT(*) as bars
                    FROM kline_1h
                    WHERE UPPER(contract_code) = UPPER(?)
                      AND DATE(dt) >= DATE('now', '-30 days')
                      AND CAST(strftime('%w', dt) AS INTEGER) BETWEEN 1 AND 5
                    GROUP BY DATE(dt)
                )
                SELECT d, bars FROM daily_bars
                WHERE bars < ?
                ORDER BY d
                LIMIT 10
            """, (main_contract, min_bars)).fetchall()
            if sparse_days:
                findings.append(Finding(
                    level="MEDIUM", dimension="主力1H覆盖",
                    symbol=symbol,
                    message=f"主力 {main_contract} 近 30 天有 {len(sparse_days)} 日 bar 数过少"
                            f" (<{min_bars} 根): "
                            + ", ".join(f"{r[0]}:{r[1]}" for r in sparse_days[:5]),
                    action="检查 TqSdk 采集是否遗漏部分交易时段"
                ))

        # 2d) 次主力合约 1H 覆盖 (换月连续性)
        # 新架构: main_continuous_1d 只有 {SYM}_CONT 一个合约, 无次主力概念
        # 换月连续性由 _CONT 复权自动处理, 此检查已不适用

        return findings

    # ── 维度 3: 价格连续性 ──

    def check_price_continuity(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 3a) OHLC 逻辑关系
        rows = conn.execute("""
            SELECT dt, contract_code FROM main_continuous_1d
            WHERE high < low
               OR open_price > high + 0.01
               OR open_price < low - 0.01
               OR close_price > high + 0.01
               OR close_price < low - 0.01
               OR open_price IS NULL OR high IS NULL OR low IS NULL OR close_price IS NULL
               OR open_price <= 0 OR high <= 0 OR low <= 0 OR close_price <= 0
            LIMIT 20
        """).fetchall()
        for r in rows:
            findings.append(Finding(
                level="CRITICAL", dimension="价格连续性",
                symbol=symbol,
                message=f"OHLC 异常: {r[0]} {r[1]}",
                action="数据源错误，需重新采集"
            ))

        # 3b) 非换月跳变 >15% (同合约)
        rows = conn.execute("""
            WITH returns AS (
                SELECT dt, contract_code, close_price,
                       LAG(close_price) OVER (ORDER BY dt) as prev_close,
                       LAG(contract_code) OVER (ORDER BY dt) as prev_contract
                FROM main_continuous_1d
                WHERE close_price IS NOT NULL AND close_price > 0
            )
            SELECT dt, contract_code, close_price, prev_close,
                   ROUND((close_price - prev_close) * 100.0 / prev_close, 2) as pct
            FROM returns
            WHERE contract_code = prev_contract
              AND prev_close > 0
              AND ABS((close_price - prev_close) * 100.0 / prev_close) > 15
            ORDER BY dt DESC
            LIMIT 10
        """).fetchall()
        for r in rows:
            findings.append(Finding(
                level="HIGH", dimension="价格连续性",
                symbol=symbol,
                message=f"非换月跳变 {r[4]:+.1f}%: {r[0]} {r[1]} ({r[2]} vs {r[3]})",
                action="检查原始数据是否准确"
            ))

        return findings

    # ── 维度 4: 时间连续性 ──

    def check_time_continuity(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 4a) 日线缺口 (>12 天 = 排除所有中国长假含春节，仅捕捉真正的数据丢失)
        # 春节最多 7天法定 + 前后周末 = 最大 ~11 天缺口
        # TqSdk/AkShare 数据源边界 (3000+ 天) 在 check_data_source_consistency 处理
        rows = conn.execute("""
            WITH gaps AS (
                SELECT dt,
                       CAST(JULIANDAY(dt) - JULIANDAY(LAG(dt) OVER (ORDER BY dt)) AS INT) as gap
                FROM main_continuous_1d
            )
            SELECT dt, gap FROM gaps
            WHERE gap > 12 AND gap < 100
            ORDER BY dt DESC
            LIMIT 10
        """).fetchall()
        for r in rows:
            findings.append(Finding(
                level="MEDIUM", dimension="时间连续性",
                symbol=symbol,
                message=f"日线缺口 {r[1]} 天 (至 {r[0]})",
                action="确认是否为长假期，否则重新采集"
            ))

        # 4b) 1H 每日 bar 数异常 (仅检查过少，多合约混合属正常)
        # 只标记 <3 根/天 的情况 (真正的数据缺失), 排除当日 (交易日尚未结束)
        rows = conn.execute("""
            SELECT DATE(dt) as dt, COUNT(*) as bars
            FROM kline_1h
            WHERE dt >= DATE('now', '-60 days')
              AND DATE(dt) < DATE('now')
            GROUP BY DATE(dt)
            HAVING bars < 3
            ORDER BY dt
            LIMIT 10
        """).fetchall()
        for r in rows:
            findings.append(Finding(
                level="MEDIUM", dimension="时间连续性",
                symbol=symbol,
                message=f"1H bar 数异常: {r[0]} 仅 {r[1]} 根",
                action="检查是否为半日市或数据缺失"
            ))

        # 4c) 主链数据时效
        row = conn.execute("SELECT MAX(dt) FROM main_continuous_1d").fetchone()
        if row and row[0]:
            try:
                latest = datetime.strptime(row[0][:10], "%Y-%m-%d")
                days_ago = (datetime.now() - latest).days
                if days_ago > 3:
                    findings.append(Finding(
                        level="HIGH", dimension="时间连续性",
                        symbol=symbol,
                        message=f"主链数据滞后 {days_ago} 天 (最新: {row[0]})",
                        action=f"python -m data.cli collect {symbol}"
                    ))
            except ValueError:
                pass

        # 4d) 1H 数据时效
        row = conn.execute("SELECT MAX(dt) FROM kline_1h").fetchone()
        if row and row[0]:
            try:
                latest = datetime.strptime(row[0][:16], "%Y-%m-%d %H:%M")
                hours_ago = (datetime.now() - latest).total_seconds() / 3600
                if hours_ago > 48:
                    findings.append(Finding(
                        level="HIGH", dimension="时间连续性",
                        symbol=symbol,
                        message=f"1H 数据滞后 {int(hours_ago)}h (最新: {row[0]})",
                        action=f"python -m data.cli collect {symbol}"
                    ))
            except ValueError:
                pass

        return findings

    # ── 维度 5: 技术指标正确性 ──

    def check_indicator_correctness(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 5a) RSI 范围 0-100
        for col in ['rsi6', 'rsi12', 'rsi24']:
            rows = conn.execute(f"""
                SELECT COUNT(*) FROM main_continuous_1d
                WHERE {col} IS NOT NULL AND ({col} < -0.01 OR {col} > 100.01)
                  AND dt >= DATE('now', '-60 days')
            """).fetchone()
            if rows and rows[0] > 0:
                findings.append(Finding(
                    level="CRITICAL", dimension="技术指标",
                    symbol=symbol,
                    message=f"{col} 超出 0-100 范围 ({rows[0]} 条)",
                    action="RSI 计算逻辑错误"
                ))

        # 5b) MACD: DIF ≈ EMA12 - EMA26 (相对容差: close * 0.001)
        rows = conn.execute("""
            SELECT COUNT(*) FROM main_continuous_1d
            WHERE macd_dif IS NOT NULL AND ema12 IS NOT NULL AND ema26 IS NOT NULL
              AND close_price > 0
              AND ABS(macd_dif - (ema12 - ema26)) > close_price * 0.001
              AND dt >= DATE('now', '-60 days')
        """).fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="HIGH", dimension="技术指标",
                symbol=symbol,
                message=f"MACD DIF != EMA12-EMA26 ({rows[0]} 条, 容差 close*0.1%)",
                action="检查 EMA/MACD 计算逻辑"
            ))

        # 5c) BOLL: upper > mid > lower
        rows = conn.execute("""
            SELECT COUNT(*) FROM main_continuous_1d
            WHERE boll_upper IS NOT NULL AND boll_mid IS NOT NULL AND boll_lower IS NOT NULL
              AND (boll_upper < boll_mid - 0.01 OR boll_lower > boll_mid + 0.01)
              AND dt >= DATE('now', '-60 days')
        """).fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="HIGH", dimension="技术指标",
                symbol=symbol,
                message=f"布林带关系错误 ({rows[0]} 条)",
                action="BOLL 计算错误"
            ))

        # 5d) KDJ: J = 3K - 2D
        rows = conn.execute("""
            SELECT COUNT(*) FROM main_continuous_1d
            WHERE kdj_k IS NOT NULL AND kdj_d IS NOT NULL AND kdj_j IS NOT NULL
              AND ABS(kdj_j - (3 * kdj_k - 2 * kdj_d)) > 0.5
              AND dt >= DATE('now', '-60 days')
        """).fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="HIGH", dimension="技术指标",
                symbol=symbol,
                message=f"KDJ J != 3K-2D ({rows[0]} 条)",
                action="KDJ 计算逻辑错误"
            ))

        # 5e) ATR >= 0
        rows = conn.execute("""
            SELECT COUNT(*) FROM main_continuous_1d
            WHERE atr14 IS NOT NULL AND atr14 < 0
              AND dt >= DATE('now', '-60 days')
        """).fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="HIGH", dimension="技术指标",
                symbol=symbol,
                message=f"ATR14 为负值 ({rows[0]} 条)",
                action="ATR 计算错误"
            ))

        return findings

    # ── 维度 7: 复权因子 ──

    def check_adjustment_factor(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 7a) adjustment_factor 为 NULL
        rows = conn.execute("""
            SELECT COUNT(*) FROM main_continuous_1d
            WHERE adjustment_factor IS NULL
        """).fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="HIGH", dimension="复权因子",
                symbol=symbol,
                message=f"adjustment_factor 为 NULL ({rows[0]} 条)",
                action="重新运行 MainChainBuilder.build()"
            ))

        # 7b) 非换月日 adjustment_factor 不应变化
        # 新架构: _CONT 无合约切换, 此检查仍有效 (catches 复权因子异常波动)
        rows = conn.execute("""
            WITH changes AS (
                SELECT dt, contract_code, adjustment_factor,
                       LAG(contract_code) OVER (ORDER BY dt) as prev_c,
                       LAG(adjustment_factor) OVER (ORDER BY dt) as prev_adj
                FROM main_continuous_1d
                WHERE adjustment_factor IS NOT NULL
            )
            SELECT COUNT(*) FROM changes
            WHERE contract_code = prev_c
              AND ABS(adjustment_factor - prev_adj) > 0.01
        """).fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="HIGH", dimension="复权因子",
                symbol=symbol,
                message=f"非换月日 adjustment_factor 变化 ({rows[0]} 次)",
                action="_calc_adjustment 逻辑错误"
            ))

        # 7c) 关键: close_price 应等于 raw_close (价格未被修改)
        rows = conn.execute("""
            SELECT COUNT(*) FROM main_continuous_1d
            WHERE raw_close IS NOT NULL AND close_price IS NOT NULL
              AND ABS(close_price - raw_close) > 0.01
        """).fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="CRITICAL", dimension="复权因子",
                symbol=symbol,
                message=f"close_price != raw_close ({rows[0]} 条) — 价格被修改!",
                action="MainChainBuilder 不应修改价格，重新 build()"
            ))

        return findings

    # ── 维度 8: 字段完整性 ──

    def check_field_completeness(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 关键字段 NULL/0 检查
        for table in ['kline_1d', 'main_continuous_1d']:
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if total == 0:
                continue
            for col in ['open_price', 'high', 'low', 'close_price', 'volume']:
                cnt = conn.execute(f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE {col} IS NULL OR {col} <= 0
                """).fetchone()[0]
                pct = cnt * 100 // total
                if pct > 1:
                    findings.append(Finding(
                        level="HIGH" if pct > 10 else "MEDIUM",
                        dimension="字段完整性",
                        symbol=symbol,
                        message=f"{table}.{col} 有 {cnt}/{total} 条 NULL/0 ({pct}%)",
                        action="检查数据源和写入逻辑"
                    ))

        return findings

    # ── 维度 9: OI 数据 ──

    def check_oi_data(self, store: DataStore, symbol: str) -> List[Finding]:
        findings = []
        conn = store.conn

        # 9a) OI 为负
        rows = conn.execute("SELECT COUNT(*) FROM kline_1d WHERE open_interest < 0").fetchone()
        if rows and rows[0] > 0:
            findings.append(Finding(
                level="CRITICAL", dimension="OI 数据",
                symbol=symbol,
                message=f"kline_1d OI 为负值 ({rows[0]} 条)",
                action="数据源错误"
            ))

        # 9b) 主链 OI 是否为当日最大 (近 60 天)
        # 新架构: kline_1d 只有 {SYM}_CONT, 直接比较 main_continuous_1d 与 kline_1d 同合约
        rows = conn.execute("""
            SELECT m.dt, m.contract_code, m.open_interest as main_oi
            FROM main_continuous_1d m
            WHERE m.dt >= DATE('now', '-60 days')
              AND m.open_interest IS NOT NULL
              AND m.open_interest < (
                  SELECT k.open_interest * 0.99 FROM kline_1d k
                  WHERE k.dt = m.dt
                    AND k.contract_code = m.contract_code
              )
            LIMIT 10
        """).fetchall()
        if rows:
            findings.append(Finding(
                level="HIGH", dimension="OI 数据",
                symbol=symbol,
                message=f"近 60 天有 {len(rows)} 天主链 OI 不是当日最大",
                action="检查 _select_main() 逻辑"
            ))

        # 9c) OI 缺失率
        total = conn.execute("SELECT COUNT(*) FROM kline_1d WHERE dt >= DATE('now', '-60 days')").fetchone()[0]
        if total > 0:
            null_oi = conn.execute("""
                SELECT COUNT(*) FROM kline_1d
                WHERE dt >= DATE('now', '-60 days')
                  AND (open_interest IS NULL OR open_interest = 0)
            """).fetchone()[0]
            pct = null_oi * 100 // total
            if pct > 5:
                findings.append(Finding(
                    level="HIGH", dimension="OI 数据",
                    symbol=symbol,
                    message=f"近 60 天 OI 缺失 {null_oi}/{total} ({pct}%)",
                    action="TqSdk 应提供 OI，检查数据源"
                ))

        return findings

    # ── 维度 6+10: 跨品种一致性 ──

    def check_cross_symbol(self) -> List[Finding]:
        findings = []

        # 按交易所分组
        by_exchange = {}
        for sym in self.symbols:
            ex = SYMBOL_EXCHANGE_MAP.get(sym.upper(), SYMBOL_EXCHANGE_MAP.get(sym, ""))
            by_exchange.setdefault(ex, {})[sym] = {}

        for sym in self.symbols:
            db_path = get_db_path(sym)
            if not db_path.exists():
                continue
            conn = sqlite3.connect(str(db_path))
            ex = SYMBOL_EXCHANGE_MAP.get(sym.upper(), SYMBOL_EXCHANGE_MAP.get(sym, ""))

            latest_main = conn.execute("SELECT MAX(dt) FROM main_continuous_1d").fetchone()[0]
            latest_1h = conn.execute("SELECT MAX(dt) FROM kline_1h").fetchone()[0]
            main_count = conn.execute("SELECT COUNT(DISTINCT dt) FROM main_continuous_1d").fetchone()[0]
            conn.close()

            if ex in by_exchange:
                by_exchange[ex][sym] = {
                    'latest_main': latest_main,
                    'latest_1h': latest_1h,
                    'main_days': main_count,
                }

        # 同交易所数据日期一致性 (容忍 1 天差异，夜盘归属可能导致)
        for ex, data in by_exchange.items():
            if not ex:
                continue
            dates = set(d['latest_main'] for d in data.values() if d.get('latest_main'))
            if len(dates) > 1:
                max_date = max(dates)
                stale = {s: d['latest_main'] for s, d in data.items()
                         if d.get('latest_main') and
                         abs((datetime.strptime(max_date, '%Y-%m-%d') -
                              datetime.strptime(d['latest_main'], '%Y-%m-%d')).days) > 1}
                if stale:
                    stale_str = ", ".join(f"{s}={d}" for s, d in sorted(stale.items()))
                    findings.append(Finding(
                        level="MEDIUM", dimension="跨品种一致性",
                        symbol=ex,
                        message=f"{ex} 交易所品种数据滞后 >1天: {stale_str}",
                        action="统一运行 python -m data.cli collect --all"
                    ))

            # 同交易所数据量差异
            day_counts = {s: d['main_days'] for s, d in data.items() if d.get('main_days', 0) > 0}
            if day_counts:
                max_cnt = max(day_counts.values())
                min_sym = min(day_counts, key=day_counts.get)
                min_cnt = day_counts[min_sym]
                if max_cnt > 0 and min_cnt < max_cnt * 0.5:
                    findings.append(Finding(
                        level="MEDIUM", dimension="跨品种一致性",
                        symbol=ex,
                        message=f"{ex} 数据量差异: {min_sym} 仅 {min_cnt} 天 (最多 {max_cnt} 天)",
                        action="部分品种缺少历史数据"
                    ))

        return findings

    # ── 报告生成 ──

    def _generate_report(self, findings: List[Finding], stats: dict) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ts = datetime.now().strftime("%Y%m%d_%H%M")

        # 统计
        levels = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in findings:
            levels[f.level] = levels.get(f.level, 0) + 1

        lines = [
            f"# 期货数据完整性审计报告",
            f"",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| 审计时间 | {now} |",
            f"| 审计品种 | {len(self.symbols)} 个 |",
            f"| 发现问题 | {len(findings)} 个 |",
            f"",
            f"## 汇总",
            f"",
            f"| 严重度 | 数量 |",
            f"|:------:|:----:|",
        ]
        for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            icon = {"CRITICAL": "🔴", "HIGH": "🟡", "MEDIUM": "🟠", "LOW": "🟢", "INFO": "ℹ️"}
            lines.append(f"| {icon.get(level, '')} {level} | {levels[level]} |")

        lines.append("")

        # 数据概况
        lines.extend(["## 数据概况", "",
                      "| 品种 | 日线 bars | 1H bars | 主链 bars | 合约代码 | 最新日线 | 最新 1H |",
                      "|:----:|:---------:|:-------:|:---------:|:--------:|:--------:|:-------:|"])
        for sym in self.symbols:
            s = stats.get(sym, {})
            if not s.get("exists"):
                lines.append(f"| {sym.upper()} | 无数据库 | — | — | — | — | — |")
            else:
                cc = s.get('contract_codes', '—') or '—'
                lines.append(
                    f"| {sym.upper()} | {s.get('kline_1d_count', 0):,} "
                    f"| {s.get('kline_1h_count', 0):,} "
                    f"| {s.get('main_count', 0):,} "
                    f"| {cc} "
                    f"| {s.get('latest_daily', '—')} "
                    f"| {s.get('latest_1h', '—')} |"
                )
        lines.append("")

        # 按严重度列出发现
        for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            level_findings = [f for f in findings if f.level == level]
            if not level_findings:
                continue

            icon = {"CRITICAL": "🔴", "HIGH": "🟡", "MEDIUM": "🟠", "LOW": "🟢"}
            lines.extend([f"## {icon.get(level, '')} {level} ({len(level_findings)})", ""])

            # 按品种分组
            by_sym = {}
            for f in level_findings:
                by_sym.setdefault(f.symbol, []).append(f)

            for sym, sym_findings in sorted(by_sym.items()):
                name = get_name(sym) if sym in DEFAULT_SYMBOLS or sym.lower() in DEFAULT_SYMBOLS else sym
                lines.append(f"### {sym.upper()} {name}")
                lines.append("")
                for f in sym_findings:
                    lines.append(f"- **[{f.dimension}]** {f.message}")
                    if f.action:
                        lines.append(f"  - 修复: `{f.action}`")
                lines.append("")

        lines.extend([
            "---",
            "",
            "> 审计工具: `scripts/data_audit.py`",
            "",
        ])

        return "\n".join(lines)


# ── 入口 ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="期货数据完整性审计")
    parser.add_argument("symbols", nargs="*", help="品种代码")
    parser.add_argument("--all", action="store_true", help="所有数据库")
    parser.add_argument("-o", "--output", help="报告输出路径")
    args = parser.parse_args()

    if args.all:
        symbols = list(DEFAULT_SYMBOLS)
    elif args.symbols:
        symbols = [s.lower() for s in args.symbols]
    else:
        symbols = DEFAULT_SYMBOLS

    print(f"审计 {len(symbols)} 个品种...")
    auditor = DataAuditor(symbols)
    report = auditor.run()

    # 输出
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"报告已保存: {args.output}")
    else:
        reports_dir = Path(__file__).resolve().parent.parent / "reports"
        reports_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = reports_dir / f"data_audit_{ts}.md"
        output_path.write_text(report, encoding="utf-8")
        print(f"报告已保存: {output_path}")

    # 控制台摘要 (避免 emoji 编码问题)
    print(f"\n审计完成，报告已保存")
    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        cnt = report.count(f"| {level} |")
        if cnt > 0:
            print(f"  {level}: {cnt}")


if __name__ == "__main__":
    main()
