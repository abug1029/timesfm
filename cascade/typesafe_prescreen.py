"""cascade/typesafe_prescreen.py — Laya 协变量提案预筛（软建议模式）"""

import json
import re
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from data.config import _env_nonempty

logger = logging.getLogger(__name__)

# ── 异常类（本地兜底）──────────────────────────────────

class AuthenticationError(Exception):
    """Laya 鉴权失败异常（本地兜底）"""
    pass

class TypeSafeTimeoutError(TimeoutError):
    """Laya 超时异常（本地兜底，保留类名兼容调用方）"""
    pass


# ── 项目根路径 ──────────────────────────────────────
FM_ROOT = Path(__file__).resolve().parent.parent


# ── 类型别名 ────────────────────────────────────────
PrescreenStatus = Literal["success", "degraded", "error"]
NoveltyType = Literal["novel", "extension", "redundant", "invalid"]

# ── 中文字符剥离（v3: 双道剥离 CJK + 全角标点）──────────
_ZH = re.compile(r'[\u4e00-\u9fff\u3000-\u303f]+')
_FULLWIDTH_PUNCT = re.compile(r'[\uff01-\uff0f\uff1a-\uff20\uff3b-\uff3f\uff5b-\uff65]+')
_PD_MIN_LEN = 12  # v3: 对齐实测 ~496 空壳（27.6%，双道 strip 后）


def _strip_chinese(s: str) -> str:
    """剥中文字符 + 全角标点，保留英文/数字/半角符号/空格/下划线。

    双道剥离：
      1. CJK 汉字 (U+4E00-U+9FFF) + CJK 标点 (U+3000-U+303F) -> 空格
      2. 全角标点 (U+FF01-U+FF65 中的标点区) -> 空格
      3. 合并连续空白
      4. 剥首尾空格/括号/分号/逗号

    注意：下划线 _ 不在任何正则中，会保留。括号内空格会保留。
    """
    result = _ZH.sub(' ', s)
    result = _FULLWIDTH_PUNCT.sub(' ', result)
    return re.sub(r'\s+', ' ', result).strip(' (;,)')


def _is_shell_pd(stripped: str) -> bool:
    """判定 strip 后是否为近空壳。

    算法：剥除 -> , ; | ( ) + 空白 后，剩余核心长度 < _PD_MIN_LEN 视为空壳。
    注意：下划线 _ 不在剥除字符类中，会保留并计入长度。

    v3: 阈值 12。典型空壳 '-> long, -> short' -> core='longshort' len=9 < 12 -> True。
    """
    core = re.sub(r'[->,;|()+\s]', '', stripped)
    return len(core) < _PD_MIN_LEN



# ── 标准降级工厂 ────────────────────────────────────
def _fallback_result(
    proposal: dict[str, Any],
    symbol: str,
    status: PrescreenStatus = "degraded",
    note: str = "Laya 未启用或降级",
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
        logger.warning("Laya prescreen: 连续 3 次超时，开启 10 分钟短路降级")


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


# ── Laya 原始答案序列化 ──────────────────────────────

def _serialize_raw_answers(answers: dict) -> dict[str, Any]:
    """将 Laya 原始答案序列化为纯 dict，保留 reasoning/置信度元数据。"""
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
        out[qid] = entry
    return out


# ── 内部辅助 ────────────────────────────────────────

def _load_symbol_profile(symbol: str) -> dict[str, str]:
    """加载品种画像（板块 + 合约详情，英文）。"""
    from config.sector_map import sector_of
    sector = sector_of(symbol)
    # 英文板块名（避免中文导致 Laya 超时）
    sector_en = {
        "black": "black", "nonferrous": "nonferrous", "precious": "precious",
        "energy": "energy", "chemical": "chemical", "agricultural": "agricultural",
        "soft": "soft", "forestry": "forestry", "livestock": "livestock",
    }.get(sector, sector)
    return {"sector": sector_en, "contract_details": f"{symbol} futures ({sector_en} sector)"}


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
    """构建 Laya System-1 的 State（英文，避免中文导致超时）。"""
    symbol_profile = _load_symbol_profile(symbol)

    # v3: 过滤 predicted_direction 中文 + 空壳回退
    raw_pd = str(proposal.get("predicted_direction") or "")  # Handle explicit null, force string
    stripped_pd = _strip_chinese(raw_pd)
    final_pd = "" if _is_shell_pd(stripped_pd) else stripped_pd

    # 提取关键字段，构建英文描述（不包含中文 mechanism/symbol_fit）
    proposal_summary = {
        "proposal_id": proposal.get("proposal_id", ""),
        "symbol": proposal.get("symbol", symbol),
        "cov_override": proposal.get("cov_override", ""),
        "covariate_family": proposal.get("covariate_family", ""),
        "predicted_direction": final_pd,
    }

    return {
        "language": "en",    # best-effort: 未证实 Laya 服务端识别此字段
        "symbol": symbol,
        "proposal_summary": proposal_summary,
        "sector": symbol_profile.get("sector", "commodity"),
        "contract_details": symbol_profile.get("contract_details", "futures contract"),
        # 跳过中文 covariate_menu 和 recent_verdicts_summary（避免 Laya 超时）
        # "covariate_menu": covariate_menu or _load_covariate_menu(),
        # "recent_verdicts_summary": _extract_relevant_history(verdict_history, symbol),
    }

def _get_laya_base_url() -> str:
    """获取 Laya 服务 URL。优先使用环境变量，默认局域网地址。"""
    return _env_nonempty("LAYA_BASE_URL") or "http://10.1.1.67:8000"


def _call_laya(state: dict[str, Any], timeout: float = 60.0) -> Any:
    """调用 Laya System-1 服务（HTTP POST /v1/systemone）。"""
    import requests

    base_url = _get_laya_base_url()
    url = f"{base_url}/v1/systemone"

    payload = {
        "model": "laya-rl-agent",
        "language": "en",    # best-effort: 未证实服务端识别，不阻塞成功率验收
        "state": state,
        "questions": {
            "mechanism_plausibility": {
                "type": "noul",
                "instructions": (
                    f"Based on the characteristics of {state.get('symbol', 'this')} futures "
                    f"({state.get('sector', 'commodity')} sector, {state.get('contract_details', 'contract')}), "
                    f"is the mechanism explanation of this covariate proposal plausible and supported by economic logic?"
                ),
            },
            "novelty_vs_redundancy": {
                "type": "choice",
                "instructions": (
                    f"How does this proposal relate to existing covariates for {state.get('symbol', 'this')}? "
                    f"(see covariate_menu and recent_verdicts_summary)"
                ),
                "criteria": {
                    "novel": "Entirely new mechanism, orthogonal to existing covariates",
                    "extension": "Known mechanism with new parameters or new product adaptation",
                    "redundant": "Highly overlapping with existing covariates (mechanism or correlation >0.8)",
                    "invalid": "Mechanism does not exist or logic is flawed",
                },
            },
            "expected_effect_size": {
                "type": "score",
                "instructions": (
                    f"Expected information contribution of this covariate to {state.get('symbol', 'this')} prediction quality"
                ),
                "criteria": [
                    "No new information (pure noise or fully captured)",
                    "Weak new information (highly correlated with existing covariates, limited marginal contribution)",
                    "Moderate new information (independent signal dimension, possible interaction effects)",
                    "Strong new information (orthogonal dimension, high expected independent contribution)",
                ],
            },
        },
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()

    result_data = response.json()

    class MockAnswer:
        def __init__(self, data):
            self.noul = data.get("noul")
            self.choice = data.get("choice")
            self.score = data.get("score")
            self.confidence = data.get("confidence")

    class MockResult:
        def __init__(self, data):
            self.answers = {
                qid: MockAnswer(ans_data)
                for qid, ans_data in data.get("answers", {}).items()
            }

    return MockResult(result_data)


# ── 主入口 ──────────────────────────────────────────

def _prescreen_impl(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None,
    covariate_menu: dict[str, Any] | None,
) -> dict[str, Any]:
    """预筛核心实现。异常分类：超时→degraded，鉴权→error，其他→error。"""
    if _check_circuit():
        return _fallback_result(proposal, symbol, note="Laya 短路降级中")

    state = _build_state(proposal, symbol, verdict_history, covariate_menu)

    try:
        result = _call_laya(state, timeout=60.0)
    except (TimeoutError, TypeSafeTimeoutError) as e:
        _record_timeout()
        logger.warning("Laya API 超时: %s", e)
        return _fallback_result(proposal, symbol, status="degraded", note="Laya API 超时")
    except AuthenticationError as e:
        logger.error("Laya API 鉴权失败: %s", e)
        return _fallback_result(proposal, symbol, status="error", note="Laya API 鉴权失败")
    except Exception as e:
        logger.exception("Laya API 调用失败: %s", e)
        return _fallback_result(proposal, symbol, status="error", note=f"Laya API 返回异常: {e}")

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
    """Laya 预筛一个协变量提案。全量异常保护。"""
    try:
        return _prescreen_impl(proposal, symbol, verdict_history, covariate_menu)
    except Exception as e:
        logger.exception("Laya 预筛未预期异常，防御性降级")
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
