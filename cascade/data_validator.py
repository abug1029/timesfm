"""
数据校验层 — 预测前数据质量保障

在级联预测执行前，检查数据时效性、合约一致性、连续性、交易时段。
Fail-fast: 校验失败则跳过该品种 (断路器模式)。
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
from collections import Counter


@dataclass
class ValidationResult:
    """数据校验结果"""
    ok: bool = True
    errors: List[str] = field(default_factory=list)      # 必须修复才能预测
    warnings: List[str] = field(default_factory=list)     # 可继续但有风险
    contract_1h: str = ""                                  # 1H 使用的合约
    contract_daily: str = ""                               # 日线使用的合约
    latest_1h_dt: str = ""                                 # 1H 最新时间
    latest_daily_dt: str = ""                              # 日线最新日期
    gaps_found: int = 0                                    # 发现的 gap 数
    valid_trading_hours: List = field(default_factory=list)  # 该品种实际交易时点
    is_stale: bool = False                                 # 结构化标志: 数据是否过期 (替代字符串匹配)


def validate_prediction_data(symbol: str, store, max_stale_days: int = 1) -> ValidationResult:
    """
    预测前数据校验

    检查项:
    1. 时效性: 1H 数据 MAX(dt) 距今 ≤ max_stale_days 交易日
    2. 合约一致性: 1H 合约 vs main_continuous_1d 最新合约
    3. 连续性: 1H context 无 >3h 的 gap
    4. 日期覆盖: 日线最后日期 ≥ 1H 最后日期 - 1天
    5. 数据量: 1H ≥ 48 bars, 日线 ≥ 60 days
    6. 交易时段探测: 从历史 1H 提取合法交易时点

    Args:
        symbol: 品种代码
        store: DataStore 实例
        max_stale_days: 允许的最大滞后天数 (默认 1 交易日)

    Returns:
        ValidationResult
    """
    vr = ValidationResult()

    # ── 1. 日线数据检查 ──
    daily_df = store.get_main_continuous(limit=5)
    if daily_df.empty:
        vr.ok = False
        vr.errors.append("无日线主链数据")
        return vr

    vr.latest_daily_dt = str(daily_df["dt"].iloc[-1])[:10]
    # 日线合约: 从 main_continuous_1d 最新记录提取
    daily_contract = str(daily_df["contract_code"].iloc[-1]) if "contract_code" in daily_df.columns else ""
    # 支持连续合约格式: XX_CONT, XX0, 或具体合约 XX2609
    if daily_contract and (daily_contract.endswith('_CONT') or daily_contract.endswith('0')):
        # 连续合约: 直接使用, 不做合约级对齐
        vr.contract_daily = daily_contract
    elif daily_contract:
        vr.contract_daily = daily_contract

    # 日线数据量
    daily_count = store.conn.execute("SELECT COUNT(*) FROM main_continuous_1d").fetchone()[0]
    if daily_count < 60:
        vr.ok = False
        vr.errors.append(f"日线数据不足: {daily_count} < 60")

    # ── 2. 1H 数据检查 ──
    h1_df = store.get_main_contract_1h(limit=480)
    if h1_df.empty:
        vr.ok = False
        vr.errors.append("无 1H 数据")
        return vr

    vr.latest_1h_dt = str(h1_df["dt"].iloc[-1])
    vr.contract_1h = str(h1_df["contract_code"].iloc[0]) if "contract_code" in h1_df.columns else ""

    # 数据量
    if len(h1_df) < 48:
        vr.ok = False
        vr.errors.append(f"1H 数据不足: {len(h1_df)} < 48")

    # ── 6. 交易时段探测 (提前, 供 bar 级别时效性检查) ──
    vr.valid_trading_hours = detect_trading_hours(h1_df)

    # ── 7. bar 级别时效性检查 (回测模式跳过) ──
    is_backtest = hasattr(store, 'cutoff_date')
    if not is_backtest:
        try:
            latest_1h = pd.to_datetime(vr.latest_1h_dt)
            now = datetime.now()
            days_stale = (now - latest_1h).days
            # 周末/假日市场休市，按星期放宽阈值
            dow = now.weekday()  # 0=Mon ... 6=Sun
            effective_max = max_stale_days
            if dow == 0:    # Monday: Fri data = 3 calendar days
                effective_max = max(effective_max, 3)
            elif dow == 1:  # Tuesday: Fri data = 4 calendar days
                effective_max = max(effective_max, 4)
            elif dow == 2:  # Wednesday: allow 3 (covers long weekend)
                effective_max = max(effective_max, 3)
            elif dow == 5:  # Saturday
                effective_max = max(effective_max, 2)
            elif dow == 6:  # Sunday
                effective_max = max(effective_max, 3)
            # 节假日放宽 (2026-08-30): 扣除 (最后bar日, 今日] 区间内法定休市日，
            # 时效性转为交易日口径。未知年份 (2027+) count 返回 0 = 回退现状。
            # 错误方向安全: 表多标 → 更宽容; 漏标 → 现状行为, 均不拒绝新鲜数据。
            from data.holidays import count_holidays_between
            _hol = count_holidays_between(latest_1h.date(), now.date())
            _effective_stale = days_stale - _hol
            if _effective_stale > effective_max:
                vr.ok = False
                vr.is_stale = True
                vr.errors.append(
                    f"1H 数据滞后 {days_stale} 天 (扣除法定节假日 {_hol} 天后 "
                    f"{_effective_stale} 天 > {effective_max})，"
                    f"可能是长假未收录 (2027+ 请更新 data/holidays.py) 或未采集，"
                    f"请先采集数据"
                )
            # ── 同日内 bar 级别检查 (时段感知) ──
            # 将交易时点按时段分组 (间隔 >2h 视为不同时段)
            # 例: [09:00,10:00,11:00] [13:00,14:00] [21:00,22:00]
            # 只在当前所属时段内检查 bar 完整性，跨时段 gap 不计为缺失
            elif days_stale == 0 and vr.valid_trading_hours:
                current_h, current_m = now.hour, now.minute
                current_time = now.time()

                # 按交易时段分组 (间隔 >2h 切分)
                sessions = _group_into_sessions(vr.valid_trading_hours)

                # 找到当前时刻所在的时段 (或最近的已过去时段)
                # 逻辑: 当前时间属于哪个时段的范围内 (时段首 - 1h ~ 时段末)
                actual_hour = latest_1h.time()

                # 找到最新 bar 所属的时段
                actual_session = None
                for sess in sessions:
                    if sess[0] <= actual_hour <= sess[-1]:
                        actual_session = sess
                        break

                # 找到当前时刻应完成到的时段
                # "应完成" = 该时段最后一个 bar 的收盘时间已过 (末位时点 + 1h)
                expected_session = None
                for sess in sessions:
                    last_bar_time = sess[-1]
                    # 该 bar 收盘时间 = last_bar_time + 1h (用总分钟数避免跨午夜问题)
                    close_total_min = (last_bar_time.hour + 1) * 60 + last_bar_time.minute
                    current_total_min = current_h * 60 + current_m
                    # 处理跨午夜: close >= 24h 说明收盘在次日 00:00 或之后
                    # 此时用 last_bar_time 作为边界: 只要 current >= last_bar_time 即视为已过
                    if close_total_min >= 24 * 60:
                        # 收盘跨入次日 (e.g. 23:00 bar closes at 24:00+)
                        # 只要当前时间 >= last_bar_time 即认为该时段已过
                        if current_time >= last_bar_time:
                            expected_session = sess
                    else:
                        close_time = last_bar_time.replace(
                            hour=close_total_min // 60,
                            minute=close_total_min % 60)
                        if current_time >= close_time:
                            expected_session = sess

                if actual_session and expected_session:
                    # 只比较同属一个连续交易块内的 bar
                    # 如果 actual_session 和 expected_session 是同一个时段，正常比较
                    # 如果 actual 在更早的时段，检查实际 bar 是否完整
                    if actual_session == expected_session:
                        # 同一时段: 直接比较索引差
                        if actual_hour not in actual_session:
                            # 最新 bar 不在已知交易时点中 (异常 bar)，跳过 bar 级检查
                            pass
                        else:
                            actual_idx = actual_session.index(actual_hour)
                            expected_latest = expected_session[-1]
                            expected_idx = expected_session.index(expected_latest)
                            missing_bars = expected_idx - actual_idx
                            if missing_bars > 2:
                                vr.ok = False
                                vr.is_stale = True
                                vr.errors.append(
                                    f"1H 数据滞后: 最新 bar {actual_hour.strftime('%H:%M')}, "
                                    f"预期至 {expected_latest.strftime('%H:%M')}, "
                                    f"缺失 {missing_bars} 根 bar，请先采集数据"
                                )
                    else:
                        # 不同时段: 检查实际 bar 时段是否已过 (数据属于已结束的旧时段)
                        # 如果 actual 在比 expected 更早的时段，且 expected 时段的 bar 一根都没有
                        # 说明数据确实过期
                        actual_sess_idx = sessions.index(actual_session)
                        expected_sess_idx = sessions.index(expected_session)
                        if expected_sess_idx > actual_sess_idx:
                            # 数据停留在更早的时段，中间所有时段的 bar 都缺失
                            # 但跨时段不算 "bar 缺失"，只判断是否过期
                            # 如果只差一个时段 (如上午→下午, 午间休市), 允许
                            if expected_sess_idx - actual_sess_idx > 1:
                                vr.ok = False
                                vr.is_stale = True
                                vr.errors.append(
                                    f"1H 数据滞后: 最新 bar {actual_hour.strftime('%H:%M')} "
                                    f"({actual_session[0].strftime('%H:%M')}-"
                                    f"{actual_session[-1].strftime('%H:%M')} 时段), "
                                    f"当前已过 {expected_session[-1].strftime('%H:%M')} "
                                    f"时段，请先采集数据"
                                )
        except (ValueError, TypeError) as e:
            vr.warnings.append(f"时效性检查异常: {e}")

    # ── 4. 合约一致性 ──
    # 连续合约标记 (_MAIN / _CONT / XX0) 之间不视为不一致
    if vr.contract_1h and vr.contract_daily:
        is_1h_continuous = (vr.contract_1h.endswith('_MAIN')
                            or vr.contract_1h.endswith('_CONT')
                            or vr.contract_1h.endswith('0'))
        is_daily_continuous = (vr.contract_daily.endswith('_CONT')
                               or vr.contract_daily.endswith('0'))
        both_continuous = is_1h_continuous and is_daily_continuous
        if vr.contract_1h != vr.contract_daily and not both_continuous:
            vr.warnings.append(
                f"合约不一致: 1H={vr.contract_1h}, 日线={vr.contract_daily} "
                f"(将强制对齐到日线合约)"
            )

    # ── 5. 日期覆盖对齐 ──
    try:
        latest_daily = pd.to_datetime(vr.latest_daily_dt)
        latest_1h_date = pd.to_datetime(vr.latest_1h_dt).normalize()
        if latest_daily < latest_1h_date - timedelta(days=1):
            vr.warnings.append(
                f"日线({vr.latest_daily_dt})落后于1H({vr.latest_1h_dt})"
            )
    except Exception:
        pass

    # ── 6. Gap 检测 ──
    vr.gaps_found = _detect_gaps(h1_df)
    if vr.gaps_found > 0:
        vr.warnings.append(f"1H 数据存在 {vr.gaps_found} 处 gap (>3h)")

    # ── 7. xreg_factors 新鲜度检查 (warning 级别, 回测模式跳过) ──
    if not is_backtest:
        try:
            xreg_df = store.conn.execute(
                "SELECT MAX(dt) FROM xreg_factors"
            ).fetchone()
            if xreg_df and xreg_df[0]:
                xreg_latest = pd.to_datetime(xreg_df[0])
                xreg_stale = (datetime.now() - xreg_latest).days
                if xreg_stale >= 5:
                    vr.warnings.append(
                        f"xreg_factors 滞后 {xreg_stale} 天 (最新: {xreg_df[0][:10]})"
                    )
        except Exception:
            pass  # xreg_factors 表可能不存在

    return vr



@dataclass
class FreshnessResult:
    """ensure_fresh_data() 返回结果"""
    symbol: str
    was_fresh: bool = False          # True = 数据已新鲜 (无需采集或采集后验证通过)
    collected: bool = False           # True = 执行了采集
    collect_type: str = ""            # "daily+1H" | "1H_only" | ""
    bars_added: int = 0              # 采集的 bar 数
    revalidated: bool = False        # 采集后重新验证是否通过
    errors: List[str] = field(default_factory=list)


def _ensure_fresh_single(
    symbol: str,
    auto_collect: bool = True,
    max_stale_days: int = 1,
    verbose: bool = True,
) -> FreshnessResult:
    """单品种数据新鲜度检查 + 自动采集 (内部实现)

    流程:
    1. validate_prediction_data() 检查时效性
    2. 如果数据新鲜 -> 直接返回 (was_fresh=True)
    3. 如果数据过期 + auto_collect=True:
       a. 判断过期类型 (bar级别 vs day级别)
       b. bar级别 -> 仅采集 1H (collect_1h_for_symbol)
       c. day级别 -> 全量采集 (ensure_data: daily+1H+main chain+xreg)
       d. 重新验证
    4. 如果 auto_collect=False 或采集后仍失败 -> 返回错误
    """
    from data.data_store import DataStore

    result = FreshnessResult(symbol=symbol)

    # Step 1: 初始验证
    try:
        with DataStore(symbol) as store:
            vr = validate_prediction_data(symbol, store, max_stale_days=max_stale_days)
    except Exception as e:
        result.errors.append(f"验证异常: {e}")
        return result

    if vr.ok:
        result.was_fresh = True
        if verbose:
            for w in vr.warnings:
                print(f"  [WARN] {symbol.upper()}: {w}")
        return result

    # Step 2: 校验失败 — 判断是否需要自动采集
    # 任何校验失败 (数据过期 OR 数据不足) 都触发采集, 而非仅 is_stale
    if not auto_collect:
        result.errors.extend(vr.errors)
        return result

    # Step 3: 判断过期类型 - bar级别 vs day级别
    is_bar_stale = False
    try:
        from datetime import datetime as _dt
        latest_1h = pd.to_datetime(vr.latest_1h_dt)
        now = _dt.now()
        # bar级别: 最新 1H 数据在最近 24 小时内 (覆盖夜盘跨午夜场景)
        # 例如周一 01:00, 周日 23:00 夜盘数据仅滞后 2h, 应走轻量 1H 采集而非全量
        hours_stale = (now - latest_1h.replace(tzinfo=None)).total_seconds() / 3600
        is_bar_stale = hours_stale < 24
    except Exception:
        pass

    # Step 4: 执行采集
    if verbose:
        label = "bar过期" if is_bar_stale else "数据过期"
        kind = "1H" if is_bar_stale else "日线+1H"
        print(f"  [AUTO-COLLECT] {symbol.upper()}: {label}，自动采集 {kind} 数据...")

    try:
        if is_bar_stale:
            # bar级别过期 -> 仅采集 1H
            from data.tqsdk_fetcher import UnifiedFetcher
            from data.indicator_calculator import IndicatorCalculator
            from data.data_store import DataStore as DS2
            from scripts.collect_1h import collect_1h_for_symbol

            fetcher = UnifiedFetcher()
            calc = IndicatorCalculator()
            with DS2(symbol) as store2:
                n = collect_1h_for_symbol(symbol, fetcher, calc, store2)
                result.bars_added = n
                result.collect_type = "1H_only"
                if verbose:
                    print(f"  [AUTO-COLLECT] 1H +{n} bars")
        else:
            # day级别过期 -> 全量采集 (deferred import 避免循环依赖)
            from scripts.three_star_predict import ensure_data as _ensure
            _r = _ensure(symbol)
            if not _r["ok"]:
                result.errors.append(f"全量采集失败: {_r['error']}")
            result.collect_type = "daily+1H"

        result.collected = True
    except Exception as e:
        result.errors.append(f"采集失败: {e}")
        if verbose:
            print(f"  [SKIP] {symbol.upper()}: 自动采集失败: {e}")
        return result

    # Step 5: 重新验证 (在新的 DataStore 上下文中)
    try:
        with DataStore(symbol) as store2:
            vr2 = validate_prediction_data(symbol, store2, max_stale_days=max_stale_days)
        if vr2.ok:
            result.revalidated = True
            result.was_fresh = True  # 采集后变新鲜了
            if verbose:
                for w in vr2.warnings:
                    print(f"  [WARN] {symbol.upper()}: {w}")
        else:
            result.errors.extend(vr2.errors)
            if verbose:
                errs = "; ".join(vr2.errors)
                print(f"  [SKIP] {symbol.upper()}: 自动采集后仍校验失败: {errs}")
    except Exception as e:
        result.errors.append(f"重验证异常: {e}")

    return result


def ensure_fresh_data(
    symbols,
    auto_collect: bool = True,
    max_stale_days: int = 1,
    verbose: bool = True,
):
    """预测前数据新鲜度检查 + 自动采集 (多态入口)

    支持两种调用方式:

    1. 单品种模式:
       result = ensure_fresh_data("cf")
       -> 返回 FreshnessResult

    2. 批量模式:
       valid, skipped = ensure_fresh_data(["cf", "rb", "i"])
       -> 返回 (valid_symbols: list[str], skipped_symbols: list[dict])
       -> skipped_symbols 每项: {"symbol": str, "name": str, "error": str}

    Args:
        symbols: 品种代码 (str) 或品种代码列表 (list[str])
        auto_collect: 是否自动采集过期数据 (默认 True)
        max_stale_days: 允许的最大滞后天数 (默认 1)
        verbose: 是否打印状态信息 (默认 True)

    Returns:
        单品种: FreshnessResult
        批量: (valid_symbols, skipped_symbols)
    """
    # ── 单品种模式 ──
    if isinstance(symbols, str):
        return _ensure_fresh_single(
            symbols, auto_collect=auto_collect,
            max_stale_days=max_stale_days, verbose=verbose,
        )

    # ── 批量模式 ──
    from data.data_store import DataStore
    from data.config import get_name

    valid_symbols = []
    skipped_symbols = []

    for s in symbols:
        try:
            # 先做数据量快速检查 (与原有逻辑兼容)
            with DataStore(s) as store:
                df = store.get_main_contract_1h(limit=48)
                if len(df) < 48:
                    if verbose:
                        print(f"  [SKIP] {s.upper()}: 1H 数据不足 ({len(df)} bars)")
                    skipped_symbols.append({"symbol": s, "name": get_name(s),
                                            "error": f"1H 数据不足 ({len(df)} bars)"})
                    continue

            # 调用单品种新鲜度检查
            fr = _ensure_fresh_single(
                s, auto_collect=auto_collect,
                max_stale_days=max_stale_days, verbose=verbose,
            )
            if fr.was_fresh:
                valid_symbols.append(s)
            else:
                errors = "; ".join(fr.errors) if fr.errors else "数据校验失败"
                if verbose:
                    print(f"  [SKIP] {s.upper()}: {errors}")
                skipped_symbols.append({"symbol": s, "name": get_name(s),
                                        "error": errors})
        except Exception as e:
            if verbose:
                print(f"  [SKIP] {s.upper()}: {e}")
            skipped_symbols.append({"symbol": s, "name": get_name(s),
                                    "error": str(e)})

    return valid_symbols, skipped_symbols



def _group_into_sessions(valid_hours: list) -> list:
    """将扁平的交易时点列表按交易时段分组

    原理: 相邻时点间隔 >=2h 视为不同时段 (午休 11:00→13:00 = 2h 恰好分开,
    收盘→夜盘 14:00→21:00 = 7h, 夜盘→次日 22:00→09:00 = 11h)。
    跨午夜的时点 (23:00→00:00) 始终分属不同交易日, 强制拆分。

    Args:
        valid_hours: detect_trading_hours() 返回的排序 time 列表

    Returns:
        list of list, 每个子列表是一个交易时段的 time 对象
        e.g. [[09:00, 10:00, 11:00], [13:00, 14:00], [21:00, 22:00]]
    """
    if not valid_hours:
        return []

    # 兼容整数小时输入: 转换为 time 对象
    from datetime import time as _dt_time
    if isinstance(valid_hours[0], int):
        valid_hours = [_dt_time(h) for h in valid_hours]

    sessions = [[valid_hours[0]]]
    for t in valid_hours[1:]:
        prev = sessions[-1][-1]
        # 计算时点间隔 (处理跨午夜的情况)
        gap_minutes = (t.hour * 60 + t.minute) - (prev.hour * 60 + prev.minute)
        if gap_minutes < 0:
            gap_minutes += 24 * 60  # 跨午夜
        if gap_minutes >= 120:  # >=2h = 不同时段 (午休 11:00→13:00 恰好 120min)
            sessions.append([t])
        else:
            sessions[-1].append(t)

    # 后处理: 拆分跨午夜的时段 (同时包含 >=21:00 和 <06:00 的时点)
    # 例: [21:00, 22:00, 23:00, 00:00, 01:00] → [21:00, 22:00, 23:00] + [00:00, 01:00]
    final_sessions = []
    for sess in sessions:
        late_hours = [t for t in sess if t.hour >= 21]
        early_hours = [t for t in sess if t.hour < 6]
        if late_hours and early_hours:
            # 跨午夜: 拆分为夜盘 (>=21) + 凌晨盘 (<6)
            final_sessions.append(late_hours)
            final_sessions.append(early_hours)
        else:
            final_sessions.append(sess)

    return final_sessions


def _detect_gaps(df_1h: pd.DataFrame, max_gap_hours: int = 3) -> int:
    """检测 1H 数据中的异常 gap (排除正常交易间隔)

    方法: 检测每个交易日内的 bar 时点是否完整。
    如果一个交易日缺失了某些本应存在的时点 (如只有日盘没有夜盘), 记为 gap。
    隔夜 gap (15:00→22:00, 23:00→10:00) 是正常交易间隔, 不计入。
    """
    if len(df_1h) < 10:
        return 0

    dates = pd.to_datetime(df_1h["dt"])
    df_check = df_1h.copy()
    df_check["_dt"] = dates
    df_check["_date"] = dates.dt.date
    df_check["_time"] = dates.dt.time

    # 探测该品种的合法交易时点
    valid_hours = detect_trading_hours(df_1h)
    if not valid_hours:
        return 0

    # 转换为 time 对象用于与 bar time 比较
    from datetime import time as _dt_time
    valid_set = set(_dt_time(h) for h in valid_hours)

    # 按日分组, 检查每天的 bar 完整性
    gaps = 0
    for date, group in df_check.groupby("_date"):
        actual_times = set(group["_time"])
        # 只检查 80% 以上交易日都出现的时点 (核心交易时段)
        # 如果某天缺失了核心时点, 记为 gap
        missing = valid_set - actual_times
        # 只有缺失 >2 个核心时点才算 gap (允许个别时点缺失)
        if len(missing) > len(valid_set) * 0.3:
            gaps += 1

    return gaps


def detect_trading_hours(df_1h: pd.DataFrame, min_frequency_pct: float = 0.05) -> list:
    """从历史 1H 数据提取合法交易时段 (数据驱动, 零维护成本)

    原理: 统计每个小时在数据中出现的频率,
    过滤掉低于阈值的噪声时点。

    Args:
        df_1h: 1H K线 DataFrame, 需有 'dt' 列
        min_frequency_pct: 最低频率阈值 (0-1), 默认 0.05 (5%)

    Returns:
        排序后的小时列表, e.g. [9, 10, 11, 13, 14, 15, 21, 22, 23]
    """
    if df_1h.empty:
        return []

    dt_col = 'dt' if 'dt' in df_1h.columns else 'date'
    hours = pd.DatetimeIndex(df_1h[dt_col]).hour
    counts = hours.value_counts(normalize=True)
    return sorted(counts[counts >= min_frequency_pct].index.tolist())


def generate_trading_dates(last_dt, horizon: int, valid_hours: list) -> pd.DatetimeIndex:
    """生成 horizon 个交易 bar 的未来日期

    基于 detect_trading_hours 的结果，跳过非交易时段和周末。

    Args:
        last_dt: 最后一个已知 bar 的时间
        horizon: 需要生成的 bar 数
        valid_hours: detect_trading_hours() 返回的合法时点列表

    Returns:
        DatetimeIndex, 长度 = horizon
    """
    if not valid_hours:
        # 回退: 简单 1h 间隔 (无交易时段信息)
        last = pd.to_datetime(last_dt)
        return pd.date_range(start=last + pd.Timedelta(hours=1),
                             periods=horizon, freq='1h')

    valid_set = set(valid_hours)
    future = []
    current = pd.to_datetime(last_dt)
    max_iter = horizon * 24  # 安全上限

    while len(future) < horizon and max_iter > 0:
        max_iter -= 1
        current += pd.Timedelta(hours=1)

        # 跳过周末
        if current.weekday() >= 5:
            # 跳到下周一 00:00
            days_to_monday = 7 - current.weekday()
            current = current.normalize() + pd.Timedelta(days=days_to_monday)
            continue

        # 检查是否属于合法交易时点
        # 兼容整数小时和 time 对象
        _sample = next(iter(valid_set))
        check_val = current.hour if isinstance(_sample, int) else current.time()
        if check_val in valid_set:
            future.append(current)

    return pd.DatetimeIndex(future)

