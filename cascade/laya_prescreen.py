"""cascade/laya_prescreen.py — Laya 协变量提案预筛（软建议模式）"""

import json
import logging
import os
import time
import threading

import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from data.config import _env_nonempty

logger = logging.getLogger(__name__)

# ── 异常类兼容导入 ──────────────────────────────────
try:
    from typesafe_sdk import (
        TypeSafeAuthenticationError as AuthenticationError,
        TypeSafeAPITimeoutError as LayaTimeoutError,
    )
except ImportError:
    class AuthenticationError(Exception):
        """Laya SDK 鉴权失败异常（本地兜底）"""
        pass

    class LayaTimeoutError(TimeoutError):
        """Laya SDK 超时异常（本地兜底）"""
        pass


class LayaUnavailableError(Exception):
    """Laya 服务不可用（503 / 队列满）。触发熔断，不试第二端点。"""
    pass


# ── Timeout 分档（P0-3）──────────────────────────────
_TIMEOUT_PRIMARY = 10.0  # 覆盖 6.4s 推理 + 3s 网络缓冲
_TIMEOUT_FALLBACK = 5.0  # 副端点快速探测
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
    """Two-section history summary: symbol gate-pass records + sector peer priors. (English only)"""
    from config.sector_map import sector_of, SECTORS, SECTOR_NAMES_EN

    lines = []

    # Section 1: current symbol gate-pass records
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
            lines.append(f"[{symbol}] gate-passed covariates ({len(relevant)} total, showing {len(recent)} most recent):")
            for v in recent:
                cov = v.get("cov_override", "default")
                family = v.get("cov_family", "unknown")
                da = v.get("dir_acc", 0.0)
                lines.append(f"  - {cov} (family: {family}, dir_acc={da:.3f})")
        else:
            lines.append(f"[{symbol}] no gate-pass records yet")

    # Section 2: cross-symbol sector peer priors
    if verdict_history:
        sector = sector_of(symbol)
        # Guard: skip cross-symbol priors for unknown sector to prevent contamination
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
                sector_en = SECTOR_NAMES_EN.get(sector, sector)
                lines.append(f"Sector peers ({sector_en}) gate-passed covariate families (cross-symbol priors):")
                for v in cross_unique:
                    sym = v.get("symbol", "?")
                    fam = v.get("cov_family", "unknown")
                    da = v.get("dir_acc", 0.0)
                    lines.append(f"  - {sym}/{fam} (dir_acc={da:.3f})")

    return "\n".join(lines) if lines else "No verdict history available"

class CircuitBreaker:
    """三态熔断器：CLOSED → OPEN → HALF_OPEN。HALF_OPEN 仅允许 1 个探针。"""
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(self, threshold: int = 3, duration: float = 300.0):
        self.state = self.CLOSED
        self.failure_count = 0
        self.threshold = threshold
        self.duration = duration
        self.last_failure_time: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = threading.Lock()
    
    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.state = self.CLOSED
            self._half_open_probe_in_flight = False
    
    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.threshold:
                self.state = self.OPEN
            self._half_open_probe_in_flight = False
    
    def should_skip(self) -> bool:
        """返回 True 表示应跳过。HALF_OPEN 仅允许 1 个探针。"""
        with self._lock:
            if self.state == self.CLOSED:
                return False
            if self.state == self.OPEN:
                if self.last_failure_time and (time.time() - self.last_failure_time) > self.duration:
                    if not self._half_open_probe_in_flight:
                        self.state = self.HALF_OPEN
                        self._half_open_probe_in_flight = True
                        return False  # 放行 1 个探针
                    return True  # 探针进行中，其他跳过
                return True  # OPEN 中，跳过
            if self.state == self.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    return True  # 探针进行中
                return False  # 防御性
            return False


# 从环境变量读取配置（显式解析 bool，非恒真）
def _parse_bool_env(name: str, default: bool) -> bool:
    """显式解析环境变量：0/false/off/no → False；1/true/on/yes → True；其他 → default。"""
    val = os.environ.get(name, "").strip().lower()
    if val in ("0", "false", "off", "no"):
        return False
    if val in ("1", "true", "on", "yes"):
        return True
    return default


_cb_enabled = _parse_bool_env("LAYA_CIRCUIT_BREAKER_ENABLED", default=True)
_cb_threshold = int(os.environ.get("LAYA_CIRCUIT_BREAKER_THRESHOLD", "3"))
_cb_duration = float(os.environ.get("LAYA_CIRCUIT_BREAKER_DURATION", "300"))

_circuit_breaker = CircuitBreaker(threshold=_cb_threshold, duration=_cb_duration)
_laya_rr_idx: int = 0  # round-robin 索引


# 兼容旧调用：_check_circuit / _record_timeout / _record_success 委托给 _circuit_breaker
def _check_circuit() -> bool:
    """检查是否处于短路降级状态。返回 True 表示应跳过 API 调用。"""
    if not _cb_enabled:
        return False
    return _circuit_breaker.should_skip()


def _record_timeout() -> None:
    """兼容旧名；新代码统一走 _record_failure。"""
    _circuit_breaker.record_failure()


def _record_success() -> None:
    """成功调用重置计数器并解除短路。"""
    _circuit_breaker.record_success()


def _record_failure(reason: str) -> None:
    """统一 failure 入口。503 / timeout / ConnectionError 都走这里。"""
    _circuit_breaker.record_failure()
    logger.warning("Laya prescreen failure: %s", reason)


def _reset_circuit_state() -> None:
    """仅供单元测试重置模块级熔断状态。"""
    with _circuit_breaker._lock:
        _circuit_breaker.failure_count = 0
        _circuit_breaker.state = CircuitBreaker.CLOSED
        _circuit_breaker._half_open_probe_in_flight = False
        _circuit_breaker.last_failure_time = None


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

def _get_laya_api_key() -> str | None:
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
    """Build Laya judge State (English-only for sector + history to avoid checkpoint switch)."""
    from config.sector_map import sector_of, SECTOR_NAMES_EN

    symbol_profile = _load_symbol_profile(symbol)
    sector_key = sector_of(symbol)  # English key e.g. "black_metals"
    sector_en = SECTOR_NAMES_EN.get(sector_key, "unknown")

    return {
        "symbol": symbol,
        "proposal": proposal,
        "sector": sector_en,  # English only
        "contract_details": symbol_profile.get("contract_details", ""),
        "covariate_menu": covariate_menu or _load_covariate_menu(),
        "recent_verdicts_summary": _extract_relevant_history(verdict_history, symbol),
    }


def _get_laya_endpoints() -> list[str]:
    """获取 Laya 服务地址列表。环境变量 LAYA_BASE_URL 优先，否则使用两个已知地址做 failover。"""
    env_url = _env_nonempty("LAYA_BASE_URL")
    if env_url:
        return [env_url, "http://100.96.19.116:8000"]
    return ["http://10.1.1.67:8000", "http://100.96.19.116:8000"]


def _call_laya(state: dict[str, Any], api_key: str, timeout: float = _TIMEOUT_PRIMARY) -> Any:
    """调用 Laya 服务。双地址 failover，两个都不可达才报错。"""

    endpoints = _get_laya_endpoints()
    last_error: Exception | None = None

    # 构建请求 payload
    payload = {
        "model": "laya-rl-agent",
        "state": state,
        "language": "en",
        "questions": {
            "mechanism_plausibility": {
                "type": "noul",
                "instructions": (
                    f"Based on {state['symbol']} sector characteristics ({state['sector']} sector, "
                    f"{state['contract_details']}), is this covariate proposal's mechanism explanation "
                    f"plausible and supported by economic logic?"
                ),
            },
            "novelty_vs_redundancy": {
                "type": "choice",
                "instructions": (
                    f"Relationship between this proposal and existing covariates for {state['symbol']} "
                    f"(see covariate_menu and recent_verdicts_summary)"
                ),
                "criteria": {
                    "novel": "Brand new mechanism, orthogonal to existing covariates",
                    "extension": "New parameters for known mechanism or new variety adaptation",
                    "redundant": "Highly overlaps with existing covariates (mechanism or numerical correlation > 0.8)",
                    "invalid": "Mechanism does not exist or logically incorrect",
                },
            },
            "expected_effect_size": {
                "type": "score",
                "instructions": f"Expected information contribution of this covariate to {state['symbol']} prediction quality",
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
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for attempt, endpoint in enumerate(endpoints):
        url = f"{endpoint}/v1/systemone"
        t = _TIMEOUT_PRIMARY if attempt == 0 else _TIMEOUT_FALLBACK
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=t)
            response.raise_for_status()
            result_data = response.json()

            # 成功：更新 round-robin 索引
            global _laya_rr_idx
            _laya_rr_idx = (_laya_rr_idx + attempt + 1) % len(endpoints)

            # 将 Laya 响应转换为标准 answer 对象
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
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 503:
                # 503 = 共享队列满，不试第二端点
                raise LayaUnavailableError(f"503 from {endpoint}") from e
            last_error = e
            logger.warning("Laya endpoint %s HTTP error (non-503): %s", endpoint, e)
            continue
        except requests.Timeout as e:
            last_error = e
            logger.warning("Laya endpoint %s timeout: %s", endpoint, e)
            continue
        except Exception as e:
            last_error = e
            logger.warning("Laya endpoint %s failed: %s", endpoint, e)
            continue

    # 双端点皆失败：timeout 升为 LayaTimeoutError，否则 ConnectionError
    if isinstance(last_error, requests.Timeout):
        raise LayaTimeoutError(f"All Laya endpoints timed out: {last_error}") from last_error
    raise ConnectionError(f"All Laya endpoints unreachable: {last_error}")



def _prescreen_impl(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None,
    covariate_menu: dict[str, Any] | None,
) -> dict[str, Any]:
    """预筛核心实现。异常分类：超时→degraded，鉴权→error，其他→error。"""
    api_key = _get_laya_api_key()
    if not api_key:
        return _fallback_result(proposal, symbol, note="Laya 未启用")

    if _check_circuit():
        return _fallback_result(proposal, symbol, note="Laya 短路降级中")

    if _should_skip_prescreen():
        return _fallback_result(proposal, symbol, status="degraded", note="queue_congestion_skip (p80 > 20s)")

    state = _build_state(proposal, symbol, verdict_history, covariate_menu)

    try:
        start_t = time.time()
        result = _call_laya(state, api_key, timeout=_TIMEOUT_PRIMARY)
    except LayaUnavailableError as e:
        _record_failure("503_unavailable")
        logger.warning("Laya 503: %s", e)
        _record_latency(time.time() - start_t)
        return _fallback_result(proposal, symbol, status="degraded", note=f"Laya 503 不可用: {e}")
    except (TimeoutError, LayaTimeoutError, requests.Timeout) as e:
        # 保留裸 TimeoutError 防回归（现有测试 mock 抛裸 TimeoutError）
        _record_failure("timeout")
        logger.warning("Laya timeout: %s", e)
        _record_latency(time.time() - start_t)
        return _fallback_result(proposal, symbol, status="degraded", note=f"Laya API 超时: {e}")
    except ConnectionError as e:
        _record_failure("connection_error")
        logger.warning("Laya connection error: %s", e)
        _record_latency(time.time() - start_t)
        return _fallback_result(proposal, symbol, status="degraded", note=f"Laya 连接失败: {e}")
    except AuthenticationError as e:
        logger.error("Laya auth error: %s", e)
        _record_latency(time.time() - start_t)
        return _fallback_result(proposal, symbol, status="error", note=f"Laya API 鉴权失败: {e}")
    except Exception as e:
        _record_failure("unknown")
        logger.exception("Laya unknown failure: %s", e)
        _record_latency(time.time() - start_t)
        return _fallback_result(proposal, symbol, status="error", note=f"Laya API 返回异常: {e}")

    answers = result.answers
    plausibility = answers["mechanism_plausibility"].noul
    raw_novelty = answers["novelty_vs_redundancy"].choice
    novelty: NoveltyType = str(raw_novelty).strip().lower()  # type: ignore[assignment]
    effect_size = int(answers["expected_effect_size"].score)

    _record_latency(time.time() - start_t)
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


# ── 队列感知退避（滑动窗口 p80）────────────────────
_latency_window: list[float] = []  # 最近 10 次调用延迟
_LATENCY_WINDOW_SIZE = 10
_P80_THRESHOLD_SKIP = 20.0  # p80 > 20s 时跳过
_P80_THRESHOLD_RECOVER = 15.0  # p80 < 15s 时恢复（滞后防抖）
_MIN_SAMPLES = 5
_latency_lock = threading.Lock()  # 线程安全


def _record_latency(latency: float) -> None:
    """记录单次调用延迟（秒）。窗口满时弹出最旧的。线程安全。"""
    with _latency_lock:
        _latency_window.append(latency)
        if len(_latency_window) > _LATENCY_WINDOW_SIZE:
            _latency_window.pop(0)


def _should_skip_prescreen() -> bool:
    """队列感知：p80 > 20s 时跳过；p80 < 15s 时恢复。样本 < 5 时不启用。"""
    with _latency_lock:
        if len(_latency_window) < _MIN_SAMPLES:
            return False
        sorted_latencies = sorted(_latency_window)
        # n=10 时 p80 ≈ sorted[-3] (第 3 高)；n=5 时 p80 ≈ sorted[-2]
        idx = max(0, len(sorted_latencies) - 3)
        p80 = sorted_latencies[idx]
        # 滞后逻辑：> 20s 跳过，< 15s 恢复；中间地带保持当前状态
        if p80 > _P80_THRESHOLD_SKIP:
            return True
        if p80 < _P80_THRESHOLD_RECOVER:
            return False
        # 中间地带（15s <= p80 <= 20s）：保持当前状态（不切换）
        # 简化实现：默认不跳过（保守）
        return False
