"""cascade/typesafe_prescreen.py — TypeSafe 协变量提案预筛（软建议模式）"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from data.config import _env_nonempty

logger = logging.getLogger(__name__)

# ── 异常类兼容导入 ──────────────────────────────────
try:
    from typesafe_sdk import (
        TypeSafeAuthenticationError as AuthenticationError,
        TypeSafeAPITimeoutError as TypeSafeTimeoutError,
    )
except ImportError:
    class AuthenticationError(Exception):
        """TypeSafe SDK 鉴权失败异常（本地兜底）"""
        pass

    class TypeSafeTimeoutError(TimeoutError):
        """TypeSafe SDK 超时异常（本地兜底）"""
        pass


# ── 项目根路径 ──────────────────────────────────────
FM_ROOT = Path(__file__).resolve().parent.parent


# ── 类型别名 ────────────────────────────────────────
PrescreenStatus = Literal["success", "degraded", "error"]
NoveltyType = Literal["novel", "extension", "redundant", "invalid"]


# ── 标准降级工厂 ────────────────────────────────────
def _fallback_result(
    proposal: dict[str, Any],
    symbol: str,
    status: PrescreenStatus = "degraded",
    note: str = "TypeSafe 未启用或降级",
) -> dict[str, Any]:
    """标准降级对象。skip_suggested 永远为 None，防止统计污染。"""
    return {
        "status": status,
        "variant_id": proposal.get("variant_id", ""),
        "symbol": symbol,
        "mechanism_plausibility": None,
        "novelty": None,
        "effect_size": None,
        "skip_suggested": None,
        "note": note,
        "raw_answers": {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ── 纯函数：判定 + 摘要（与 SDK 对象解耦）───────────

def compute_skip_suggested(
    plausibility: float,
    novelty: str,
    effect_size: int,
) -> bool:
    """决定是否建议跳过。纯函数，参数为基础标量。"""
    if plausibility < 0.4:
        return True
    if novelty == "invalid":
        return True
    if novelty == "redundant" and effect_size <= 1:
        return True
    if effect_size == 0 and plausibility < 0.6:
        return True
    return False


def generate_note(
    plausibility: float,
    novelty: str,
    effect_size: int,
) -> str:
    """生成人类可读的预筛摘要。纯函数。"""
    parts = []

    if plausibility < 0.4:
        parts.append(f"机制可信度低 ({plausibility:.2f})")
    elif plausibility < 0.6:
        parts.append(f"机制可信度中等 ({plausibility:.2f})")
    else:
        parts.append(f"机制可信 ({plausibility:.2f})")

    novelty_labels = {
        "novel": "全新", "extension": "扩展",
        "redundant": "冗余", "invalid": "无效"
    }
    parts.append(f"新颖度: {novelty_labels.get(novelty, novelty)}")

    effect_labels = ["无信息量", "微弱", "中等", "强"]
    parts.append(f"预期效果: {effect_labels[effect_size]}")

    return " | ".join(parts)


# ── 历史裁决提取器（防上下文溢出 + 跨品种迁移先验）──

def _extract_relevant_history(
    verdict_history: list[dict] | None,
    symbol: str,
    max_entries: int = 5,
    max_cross_entries: int = 5,
) -> str:
    """两段式历史摘要：当前品种过门记录 + 同板块经典先验基底。"""
    from config.sector_map import sector_of, SECTORS, SECTOR_NAMES

    lines = []

    # 第一段：当前品种历史过门记录
    if verdict_history:
        relevant = [
            v for v in verdict_history
            if v.get("symbol") == symbol and v.get("gate_pass")
        ]
        if relevant:
            recent = sorted(
                relevant,
                key=lambda v: v.get("decided_at") or "",
                reverse=True,
            )[:max_entries]
            lines.append(f"[{symbol}] 已过门协变量 ({len(relevant)} 条，显示最近 {len(recent)} 条):")
            for v in recent:
                cov = v.get("cov_override", "默认协变量")
                family = v.get("cov_family", "unknown")
                da = v.get("dir_acc", 0.0)
                lines.append(f"  - {cov} (族: {family}, dir_acc={da:.3f})")
        else:
            lines.append(f"[{symbol}] 暂无过门裁决记录")

    # 第二段：同板块已过门协变量族（跨品种迁移先验）
    if verdict_history:
        sector = sector_of(symbol)
        # 守卫：未知板块不提取跨品种先验，防止串扰污染
        if sector and sector != "other":
            sector_symbols = SECTORS.get(sector, [])
            peer_symbols = [s for s in sector_symbols if s != symbol]

            cross_sector = [
                v for v in verdict_history
                if v.get("symbol") in peer_symbols
                and v.get("gate_pass")
                and v.get("cov_family") is not None
            ]
            family_seen: set[str] = set()
            cross_unique = []
            for v in sorted(cross_sector, key=lambda v: v.get("decided_at") or "", reverse=True):
                fam = v.get("cov_family", "")
                if fam not in family_seen:
                    family_seen.add(fam)
                    cross_unique.append(v)
                    if len(cross_unique) >= max_cross_entries:
                        break

            if cross_unique:
                sector_name = SECTOR_NAMES.get(sector, sector)
                lines.append(f"同板块（{sector_name}）已过门协变量族（跨品种迁移先验）:")
                for v in cross_unique:
                    sym = v.get("symbol", "?")
                    fam = v.get("cov_family", "unknown")
                    da = v.get("dir_acc", 0.0)
                    lines.append(f"  - {sym}/{fam} (dir_acc={da:.3f})")

    return "\n".join(lines) if lines else "无历史裁决记录"


# ── 轻量熔断（连续超时退避 + 半开自愈）─────────────
_consecutive_timeouts = 0
_circuit_until: float | None = None


def _check_circuit() -> bool:
    """检查是否处于短路降级状态。返回 True 表示应跳过 API 调用。"""
    global _circuit_until, _consecutive_timeouts
    now = time.time()
    if _circuit_until:
        if now < _circuit_until:
            return True
        _circuit_until = None
        _consecutive_timeouts = 0
    return False


def _record_timeout():
    """记录一次超时。连续 3 次超时后开启 10 分钟短路。"""
    global _consecutive_timeouts, _circuit_until
    _consecutive_timeouts += 1
    if _consecutive_timeouts >= 3:
        _circuit_until = time.time() + 600
        logger.warning("TypeSafe prescreen: 连续 3 次超时，开启 10 分钟短路降级")


def _record_success():
    """成功调用重置计数器并解除短路。"""
    global _consecutive_timeouts, _circuit_until
    _consecutive_timeouts = 0
    _circuit_until = None


def _reset_circuit_state() -> None:
    """仅供单元测试重置模块级熔断状态。"""
    global _consecutive_timeouts, _circuit_until
    _consecutive_timeouts = 0
    _circuit_until = None


# ── SDK 原始答案序列化 ──────────────────────────────

def _serialize_raw_answers(answers: dict) -> dict[str, Any]:
    """将 SDK 原始答案序列化为纯 dict，保留 reasoning/置信度元数据。"""
    out = {}
    for qid, ans in answers.items():
        entry: dict[str, Any] = {}
        if hasattr(ans, "noul"):
            entry["noul"] = ans.noul
        if hasattr(ans, "choice"):
            entry["choice"] = ans.choice
        if hasattr(ans, "score"):
            entry["score"] = ans.score
        if hasattr(ans, "confidence"):
            entry["confidence"] = ans.confidence
        # SDK v0.7.1 的 Noul/Choice/Score answer 均无 reasoning 字段, 故不序列化
        out[qid] = entry
    return out


# ── 内部辅助 ────────────────────────────────────────

def _get_typesafe_api_key() -> str | None:
    return _env_nonempty("TYPESAFE_API_KEY")


def _load_symbol_profile(symbol: str) -> dict[str, str]:
    """加载品种画像（板块 + 合约详情）。"""
    from config.sector_map import sector_of, SECTOR_NAMES
    sector = sector_of(symbol)
    sector_name = SECTOR_NAMES.get(sector, sector)
    return {"sector": sector_name, "contract_details": f"{symbol} ({sector_name})"}


def _load_covariate_menu() -> dict[str, Any]:
    """加载协变量菜单。"""
    menu_path = FM_ROOT / "task_FM" / "covariate_menu.inc.md"
    if menu_path.exists():
        return {"text": menu_path.read_text(encoding="utf-8")}
    return {}


def _build_state(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None,
    covariate_menu: dict[str, Any] | None,
) -> dict[str, Any]:
    """构建 TypeSafe judge 的 State。"""
    symbol_profile = _load_symbol_profile(symbol)
    return {
        "symbol": symbol,
        "proposal": proposal,
        "sector": symbol_profile.get("sector", "未知"),
        "contract_details": symbol_profile.get("contract_details", ""),
        "covariate_menu": covariate_menu or _load_covariate_menu(),
        "recent_verdicts_summary": _extract_relevant_history(verdict_history, symbol),
    }


def _call_typesafe(state: dict[str, Any], api_key: str, timeout: float = 5.0) -> Any:
    """调用 TypeSafe SDK judge（3 问并行）。"""
    from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

    client = TypeSafeClient(api_key=api_key, timeout=timeout)
    return client.system_one(
        model="jev-latest",
        state=state,
        questions={
            "mechanism_plausibility": Noul(
                instructions=(
                    f"基于 {state['symbol']} 的品种特征（{state['sector']}板块，"
                    f"{state['contract_details']}），该协变量提案的机制解释是否合理"
                    f"且有经济逻辑支撑？"
                ),
            ),
            "novelty_vs_redundancy": Choice(
                instructions=(
                    f"该提案与 {state['symbol']} 已有协变量的关系"
                    f"（见 covariate_menu 和 recent_verdicts_summary）"
                ),
                criteria={
                    "novel": "全新机制，与现有协变量正交",
                    "extension": "已知机制的新参数或新品种适配",
                    "redundant": "与现有协变量高度重叠（机制或数值相关性>0.8）",
                    "invalid": "机制不存在或逻辑错误",
                },
            ),
            "expected_effect_size": Score(
                instructions=f"预期该协变量对 {state['symbol']} 预测质量的信息量贡献",
                criteria=[
                    "无新增信息（纯噪声或已完全捕获）",
                    "微弱新增信息（与现有协变量高度相关，边际贡献有限）",
                    "中等新增信息（独立信号维度，可能有交互效应）",
                    "强新增信息（正交维度，高预期独立贡献）",
                ],
            ),
        },
    )


# ── 主入口 ──────────────────────────────────────────

def _prescreen_impl(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None,
    covariate_menu: dict[str, Any] | None,
) -> dict[str, Any]:
    """预筛核心实现。异常分类：超时→degraded，鉴权→error，其他→error。"""
    api_key = _get_typesafe_api_key()
    if not api_key:
        return _fallback_result(proposal, symbol, note="TypeSafe 未启用")

    if _check_circuit():
        return _fallback_result(proposal, symbol, note="TypeSafe 短路降级中")

    state = _build_state(proposal, symbol, verdict_history, covariate_menu)

    try:
        result = _call_typesafe(state, api_key, timeout=5.0)
    except (TimeoutError, TypeSafeTimeoutError) as e:
        _record_timeout()
        logger.warning("TypeSafe API 超时: %s", e)
        return _fallback_result(proposal, symbol, status="degraded", note="TypeSafe API 超时")
    except AuthenticationError as e:
        logger.error("TypeSafe API 鉴权失败: %s", e)
        return _fallback_result(proposal, symbol, status="error", note="TypeSafe API 鉴权失败")
    except Exception as e:
        logger.exception("TypeSafe API 调用失败: %s", e)
        return _fallback_result(proposal, symbol, status="error", note=f"TypeSafe API 返回异常: {e}")

    answers = result.answers
    plausibility = answers["mechanism_plausibility"].noul
    raw_novelty = answers["novelty_vs_redundancy"].choice
    novelty: NoveltyType = str(raw_novelty).strip().lower()  # type: ignore[assignment]
    effect_size = int(answers["expected_effect_size"].score)

    _record_success()

    skip = compute_skip_suggested(plausibility, novelty, effect_size)
    note = generate_note(plausibility, novelty, effect_size)

    return {
        "status": "success",
        "variant_id": proposal.get("variant_id", ""),
        "symbol": symbol,
        "mechanism_plausibility": plausibility,
        "novelty": novelty,
        "effect_size": effect_size,
        "skip_suggested": skip,
        "note": note,
        "raw_answers": _serialize_raw_answers(answers),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def prescreen_proposal(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None = None,
    covariate_menu: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """TypeSafe 预筛一个协变量提案。全量异常保护。"""
    try:
        return _prescreen_impl(proposal, symbol, verdict_history, covariate_menu)
    except Exception as e:
        logger.exception("TypeSafe 预筛未预期异常，防御性降级")
        return _fallback_result(
            proposal, symbol,
            status="error",
            note=f"预筛异常降级: {type(e).__name__}",
        )


# ── 原子写盘助手 ────────────────────────────────────

def write_prescreen_result(prescreen_path: str, result: dict[str, Any]) -> None:
    """原子写入 prescreen JSON，防止慢环读取半写文件。"""
    target_dir = os.path.dirname(prescreen_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    temp_path = f"{prescreen_path}.tmp.{os.getpid()}"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, prescreen_path)


# ── 门面函数 ────────────────────────────────────────

def prescreen_and_save(
    proposal: dict[str, Any],
    proposal_path: str,
    symbol: str,
    verdict_history: list[dict[str, Any]] | None = None,
    covariate_menu: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """端到端门面：预筛 + 原子落盘至 <proposal_path>.prescreen.json。"""
    result = prescreen_proposal(proposal, symbol, verdict_history, covariate_menu)
    try:
        prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
        write_prescreen_result(prescreen_path, result)
    except Exception as e:
        logger.error("prescreen 结果原子落盘失败 (%s): %s", proposal_path, e)
    return result
