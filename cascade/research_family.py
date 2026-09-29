"""研究 family：多重比较纪律（spec §4.3 W3.6，v4/v7/v8/v10）。

一个 family = **同一研究问题 + 同一预注册系列**内全部**确认检验**。
默认一个品种 = 一个研究问题 = 一个 family（同一 protocol_fingerprint 下）；
批次、运行、代际都不重置校正。

命名注意：本模块的 "family" 是**研究 family**（同一研究问题的确认检验集合），
与 `cascade/cov_family.py` 的**协变量 family**（momentum/volatility 类型分组）
是两个不同概念，不可互换。
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

# ── 常量（spec 787-835）────────────────────────────────────────

FAMILY_CLOSE_AFTER = timedelta(days=90)   # family_close_at：首成员注册 + 90 天
FAMILY_MAX_MEMBERS = 20                   # family_max_members
T_MAX = timedelta(days=180)               # 单成员 registered_at 起算 180 天
SEAL_DEADLINE_GRACE = T_MAX               # 封账上界 = close_at + T_max

TERMINAL_STATES = frozenset({"confirmed", "refuted", "abandoned", "timeout"})

# 计入 K 的终态：abandoned / timeout 也计入，否则「结果不好就丢掉」= 缩小 K = p-hacking
COUNTED_TERMINAL = frozenset({"confirmed", "refuted", "abandoned", "timeout"})

SCHEMA_PREFIX = "research_target_v1"
SEPARATOR = "|"


class FieldFormatError(ValueError):
    """字段违反 v10 序列化规范（fail-loud，不做静默替换）。"""


# ── v10 序列化规范 ────────────────────────────────────────────


def _normalize_field(value: str, field: str) -> str:
    """规范化单个字段：NFC -> 小写 -> 去两端空白；含分隔符则 fail-loud。"""
    if not isinstance(value, str):
        raise FieldFormatError(f"{field} 必须是字符串，got {type(value).__name__}")
    s = unicodedata.normalize("NFC", value).strip().lower()
    if SEPARATOR in s:
        raise FieldFormatError(
            f"{field}={value!r} 含分隔符 {SEPARATOR!r}，会造成碰撞（spec v10 要求 fail-loud）"
        )
    if not s:
        raise FieldFormatError(f"{field} 规范化后为空")
    return s


def research_target_hash(
    symbol: str,
    target_var: str,
    price_series_def: str,
    adjust_roll_rule_version: str,
) -> str:
    """研究对象的稳定标识（spec §4.3 W3.6 family 键第三要素，v8/v10）。

    只哈希"研究目标本身"：品种、目标变量、价格序列**定义**、复权/换月**规则版本**。
    **不含**观测数据内容与截止时间 —— 否则新增一根 bar 就会拆出新 family，
    恰恰削弱"换批次/协议版本不能重置校正"的防规避意图。

    v10 序列化规范（锁死跨实现字节级确定性）：
        输入顺序  symbol | target_var | price_series_def | adjust_roll_rule_version
        前缀参与  schema 前缀 research_target_v1| 参与最终 SHA-256 输入
        分隔符    |  (U+007C)，字段值禁止含 |，出现即 fail-loud
        规范化    全小写、去两端空白、Unicode NFC

    与 `target_snapshot_hash`（experiment_fingerprint 用）的区分：
        research_target_hash = 研究问题**身份**，稳定
        target_snapshot_hash = 本次实验**数据快照**内容哈希，随运行变化
    二者不得混用。
    """
    import hashlib

    parts = [
        _normalize_field(symbol, "symbol"),
        _normalize_field(target_var, "target_var"),
        _normalize_field(price_series_def, "price_series_def"),
        _normalize_field(adjust_roll_rule_version, "adjust_roll_rule_version"),
    ]
    payload = SEPARATOR.join([SCHEMA_PREFIX, *parts])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_research_question(
    predict_target: str,
    predict_horizon: int | str,
    rth: str,
) -> str:
    """research_question = (预测目标, 预测任务/期限, research_target_hash)。"""
    return SEPARATOR.join(
        [
            _normalize_field(predict_target, "predict_target"),
            _normalize_field(str(predict_horizon), "predict_horizon"),
            _normalize_field(rth, "research_target_hash"),
        ]
    )


def make_family_key(symbol: str, research_question: str) -> str:
    """family_key = (symbol, research_question)。

    research_question 是 make_research_question 拼好的复合串，其内部分隔符是
    合法结构而非碰撞，故这里只校验非空；叶子字段的 '|' 禁令已在各自构造时执行。
    """
    if not isinstance(research_question, str) or not research_question.strip():
        raise FieldFormatError("research_question 必须是非空字符串")
    if research_question != research_question.strip():
        raise FieldFormatError("research_question 首尾不得有空白")
    return SEPARATOR.join(
        [
            _normalize_field(symbol, "family_key.symbol"),
            research_question.strip(),
        ]
    )


def default_family_key(
    symbol: str,
    *,
    target_var: str = "dir",
    price_series_def: str = "main_continuous",
    adjust_roll_rule_version: str = "v1",
    predict_target: str = "dir",
    predict_horizon: int | str = 24,
) -> str:
    """默认口径：一个品种 = 一个研究问题 = 一个 family。"""
    rth = research_target_hash(
        symbol, target_var, price_series_def, adjust_roll_rule_version
    )
    return make_family_key(
        symbol, make_research_question(predict_target, predict_horizon, rth)
    )


# ── 成员登记 ──────────────────────────────────────────────────


def _as_utc(ts) -> datetime:
    """接受 datetime 或 ISO 字符串（成员落盘 JSON 后往返即为字符串）。"""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if not isinstance(ts, datetime):
        raise TypeError(f"expected datetime or ISO string, got {type(ts).__name__}")
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def family_close_at(members: Sequence[dict]) -> datetime | None:
    """family_close_at = 首个成员 registered_at + 90 天。"""
    regs = [_as_utc(m["registered_at"]) for m in members if m.get("registered_at")]
    return min(regs) + FAMILY_CLOSE_AFTER if regs else None


def registration_open(members: Sequence[dict], now: datetime) -> tuple[bool, str]:
    """注册截止判定：时间截止与成员上限并用，先到者为准（spec W3.6②）。"""
    if not members:
        return True, "open:first_member"

    if len(members) >= FAMILY_MAX_MEMBERS:
        return False, f"closed:max_members({len(members)}/{FAMILY_MAX_MEMBERS})"

    close_at = family_close_at(members)
    if close_at is not None and _as_utc(now) >= close_at:
        return False, f"closed:close_at({close_at.isoformat()})"

    return True, "open"


def make_member(
    family_key: str,
    symbol: str,
    variant_id: str,
    registered_at: datetime,
    *,
    run_mode: str = "confirmation",
) -> dict:
    """构造一个 family 成员记录。

    只有确认检验进 family；探索期结果不是检验，不进 family（spec W3.6①）。
    """
    if run_mode != "confirmation":
        raise ValueError(
            f"探索期结果不进 family（run_mode={run_mode!r}）——"
            "探索自由、确认严格是本设计的分界线"
        )
    return {
        "family_key": family_key,
        "symbol": symbol,
        "variant_id": variant_id,
        "registered_at": _as_utc(registered_at).isoformat(),
        "status": "registered",
        "p_value": None,
        "p_value_family_adjusted": None,
    }


def register_member(
    members: list[dict], member: dict, now: datetime
) -> tuple[list[dict], str]:
    """登记一个确认成员。返回 (新成员列表, 登记结果标签)。

    截止后不再接纳新确认假设 —— 这是封账可达的必要条件（spec W3.6②）。
    """
    if member["family_key"] != (members[0]["family_key"] if members else member["family_key"]):
        raise ValueError("不能把不同 family 的成员登记到同一 family")

    ok, reason = registration_open(members, now)
    if not ok:
        return members, f"rejected:{reason}"

    return members + [member], "registered"


# ── 终态判定与封账 ────────────────────────────────────────────


def resolve_terminal_states(members: Sequence[dict], now: datetime) -> list[dict]:
    """把超过各自 T_max 仍未终态的成员落 timeout + p=1（spec W3.6②）。"""
    now = _as_utc(now)
    out: list[dict] = []
    for m in members:
        m = dict(m)
        if m.get("status") not in TERMINAL_STATES:
            deadline = _as_utc(m["registered_at"]) + T_MAX
            if now >= deadline:
                m["status"] = "timeout"
                # p=1 仅适用于已进入确认 family 且截止前未完成的假设
                m["p_value"] = 1.0
        out.append(m)
    return out


def all_terminal(members: Sequence[dict]) -> bool:
    return bool(members) and all(m.get("status") in TERMINAL_STATES for m in members)


def seal_deadline(members: Sequence[dict]) -> datetime | None:
    """封账上界 = family_close_at + T_max。"""
    close_at = family_close_at(members)
    return close_at + SEAL_DEADLINE_GRACE if close_at else None


def family_bh_fdr(members: Sequence[dict], fdr_q: float = 0.10) -> dict[str, float]:
    """family 级 BH-FDR，一次性在封账时运行（spec W3.6②）。

    K 计入全部终态成员，含 abandoned / timeout（否则「结果不好就悄悄丢掉」
    等于缩小 K，等于 p-hacking）。未在 K 内取得 p 值的成员按 p=1 参与排序。

    Returns:
        {variant_id: 校正后 p 值}
    """
    counted = [m for m in members if m.get("status") in COUNTED_TERMINAL]
    k = len(counted)
    out: dict[str, float] = {}
    if k == 0:
        return out

    def p_of(m: dict) -> float:
        p = m.get("p_value")
        return 1.0 if p is None else float(p)

    ordered = sorted(counted, key=lambda m: (p_of(m), m.get("variant_id", "")))
    # BH 校正：p_adj(i) = min over j>=i of (K/j * p(j))，上截断到 1
    running_min = 1.0
    adj = [0.0] * k
    for idx in range(k - 1, -1, -1):
        candidate = min(1.0, p_of(ordered[idx]) * k / (idx + 1))
        running_min = min(running_min, candidate)
        adj[idx] = running_min

    for m, p_adj in zip(ordered, adj):
        out[m["variant_id"]] = float(p_adj)
    return out


def seal_family(
    members: Sequence[dict], now: datetime
) -> tuple[list[dict], dict[str, float]]:
    """封账：全部成员终态后一次性跑 BH-FDR（spec W3.6②）。

    Returns:
        (封账后的成员列表, {variant_id: 校正后 p 值})
    """
    resolved = resolve_terminal_states(members, now)
    if not all_terminal(resolved):
        raise ValueError(
            f"family 尚未全部终态（{sum(1 for m in resolved if m.get('status') not in TERMINAL_STATES)}"
            f"/{len(resolved)} 未完成），不得封账"
        )

    adjusted = family_bh_fdr(resolved)
    sealed = []
    for m in resolved:
        m = dict(m)
        m["p_value_family_adjusted"] = adjusted.get(m["variant_id"])
        m["family_sealed_at"] = _as_utc(now).isoformat()
        sealed.append(m)
    return sealed, adjusted


def family_report_scope() -> str:
    """跨品种错误率范围声明（spec W3.6①，报告模板须同时呈现）。"""
    return (
        "本 spec 默认不跨品种合并校正：每个品种是独立研究问题，各自控制 FDR。"
        "因此结论范围仅限品种内，报告不得产出跨品种聚合声称。"
    )
