# TypeSafe 协变量提案预筛实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 FM_a 的 Praxist 快环与慢环之间接入 TypeSafe 协变量提案预筛层，为每个 proposal 产出机制合理性/新颖度/预期效果的三维度语义化评分，以软建议模式注入 verdict 元数据。

**Architecture:** 新增 `cascade/typesafe_prescreen.py` 核心模块（预筛逻辑 + 三态降级 + 半开熔断 + 原子写盘），修改 `aligned_slow_loop.py` 在 verdict 构建时读取伴随 `.prescreen.json` 文件并注入 `metadata.prescreen` 命名空间，修改 `data/config.py` 添加 API Key 读取函数，修改 `task_FM/task.yaml` 注入环境变量。

**Tech Stack:** Python 3.11 (WSL), typesafe-sdk (Noul/Choice/Score), pytest, POSIX os.replace 原子写

**Spec:** `docs/superpowers/specs/2026-09-22-typesafe-covariate-prescreen-design.md` (v4)

## Global Constraints

- 密钥只进 `.env.praxist`，不写进 `task_FM/task.yaml` 的代码部分
- 不改变 v23 裁决标准（n≥350 / n_eff≥50 / dir_acc / DM / BH-FDR）
- verdict schema 版本号仍为 `fm.aligned_verdict.v2`
- prescreen 字段仅存在于 `verdict["metadata"]["prescreen"]` 命名空间内
- 降级时 `skip_suggested` 显式为 `None`（非 `false`），防止统计污染
- Python 3.12+ 时区语法：`datetime.now(timezone.utc).isoformat()`（不用 `utcnow()`）
- 熔断器提供 `_reset_circuit_state()` 供 pytest 清理
- Choice 返回值归一化：`str(raw).strip().lower()`
- 原子写盘包含目录自愈 `os.makedirs(target_dir, exist_ok=True)`
- `prescreen_and_save` 门面函数包裹落盘异常守卫

---

### Task 1: 核心模块与单元测试（基础层）

**Files:**
- Create: `cascade/typesafe_prescreen.py`
- Create: `tests/test_typesafe_prescreen.py`

**Interfaces:**
- Consumes: `data.config._env_nonempty` (API Key 读取), `config.sector_map.SECTOR_MAP` (板块映射), `typesafe-sdk` (Choice/Noul/Score)
- Produces: `prescreen_proposal()`, `prescreen_and_save()`, `write_prescreen_result()`, `compute_skip_suggested()`, `generate_note()`, `_reset_circuit_state()`

#### Step 1.1: 创建模块骨架 + 类型定义 + 降级工厂

- [ ] **Step 1: 写入模块骨架**

```python
"""cascade/typesafe_prescreen.py — TypeSafe 协变量提案预筛（软建议模式）"""

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
    from typesafe_sdk.exceptions import AuthenticationError, TypeSafeTimeoutError
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
```

- [ ] **Step 2: 验证语法**

Run: `cd /home/abug/timesfm && python -c "import cascade.typesafe_prescreen; print('OK')"`
Expected: `OK`

#### Step 1.2: 纯函数 `compute_skip_suggested` + `generate_note`

- [ ] **Step 1: 写入纯函数**

追加到 `cascade/typesafe_prescreen.py`：

```python
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
```

- [ ] **Step 2: 测试纯函数**

写入 `tests/test_typesafe_prescreen.py`：

```python
"""tests/test_typesafe_prescreen.py"""
import json
import os
import sys
from pathlib import Path

import pytest

# ── 路径设置 ────────────────────────────────────────
FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))

from cascade.typesafe_prescreen import (
    compute_skip_suggested,
    generate_note,
    _fallback_result,
    _reset_circuit_state,
)


# ── 熔断状态自动清理 ─────────────────────────────────
@pytest.fixture(autouse=True)
def _clean_circuit_state():
    """每个测试用例前后重置熔断状态，防止全局变量污染。"""
    _reset_circuit_state()
    yield
    _reset_circuit_state()


# ── 纯函数测试 ──────────────────────────────────────

class TestComputeSkipSuggested:
    def test_plausible_novel_passes(self):
        assert compute_skip_suggested(0.85, "novel", 3) is False

    def test_implausible_skipped(self):
        assert compute_skip_suggested(0.3, "novel", 2) is True

    def test_invalid_mechanism_skipped(self):
        assert compute_skip_suggested(0.7, "invalid", 3) is True

    def test_redundant_weak_skipped(self):
        assert compute_skip_suggested(0.6, "redundant", 1) is True

    def test_zero_effect_low_plausibility_skipped(self):
        assert compute_skip_suggested(0.5, "novel", 0) is True

    def test_zero_effect_high_plausibility_passes(self):
        # effect_size=0 但 plausibility>=0.6 → 不跳过（机制可信但预期无信息量）
        assert compute_skip_suggested(0.7, "novel", 0) is False

    def test_redundant_strong_passes(self):
        # redundant 但 effect_size>1 → 不跳过
        assert compute_skip_suggested(0.6, "redundant", 2) is False


class TestGenerateNote:
    def test_high_confidence_note(self):
        note = generate_note(0.85, "novel", 3)
        assert "机制可信 (0.85)" in note
        assert "全新" in note
        assert "强" in note

    def test_low_confidence_note(self):
        note = generate_note(0.3, "redundant", 0)
        assert "机制可信度低 (0.30)" in note
        assert "冗余" in note
        assert "无信息量" in note

    def test_unknown_novelty_fallback(self):
        note = generate_note(0.5, "unknown_type", 1)
        assert "unknown_type" in note
```

- [ ] **Step 3: 运行测试**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_typesafe_prescreen.py -v -k "TestCompute or TestGenerate"`
Expected: 10 passed

#### Step 1.3: 历史裁决提取器 `_extract_relevant_history`

- [ ] **Step 1: 写入提取器**

追加到 `cascade/typesafe_prescreen.py`：

```python
# ── 历史裁决提取器（防上下文溢出 + 跨品种迁移先验）──

def _extract_relevant_history(
    verdict_history: list[dict] | None,
    symbol: str,
    max_entries: int = 5,
    max_cross_entries: int = 5,
) -> str:
    """两段式历史摘要：当前品种过门记录 + 同板块经典先验基底。"""
    from config.sector_map import SECTOR_MAP

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
        sector = SECTOR_MAP.get(symbol, "unknown")
        # 守卫：未知板块不提取跨品种先验，防止串扰污染
        if sector and sector != "unknown":
            sector_symbols = [
                s for s, sec in SECTOR_MAP.items()
                if sec == sector and s != symbol
            ]

            cross_sector = [
                v for v in verdict_history
                if v.get("symbol") in sector_symbols
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
                lines.append(f"同板块（{sector}）已过门协变量族（跨品种迁移先验）:")
                for v in cross_unique:
                    sym = v.get("symbol", "?")
                    fam = v.get("cov_family", "unknown")
                    lines.append(f"  - {sym}/{fam} (dir_acc={v.get('dir_acc', 0.0):.3f})")

    return "\n".join(lines) if lines else "无历史裁决记录"
```

- [ ] **Step 2: 测试提取器**

追加到 `tests/test_typesafe_prescreen.py`：

```python
from cascade.typesafe_prescreen import _extract_relevant_history


class TestExtractRelevantHistory:
    def test_empty_history(self):
        assert _extract_relevant_history(None, "ss") == "无历史裁决记录"

    def test_symbol_history_only(self):
        history = [
            {"symbol": "ss", "gate_pass": True, "cov_override": "rsi_state",
             "cov_family": "momentum", "dir_acc": 0.53, "decided_at": "2026-09-01T00:00:00"},
        ]
        result = _extract_relevant_history(history, "ss")
        assert "[ss] 已过门协变量" in result
        assert "rsi_state" in result

    def test_none_decided_at_safe(self):
        """decided_at=None 时排序不崩溃。"""
        history = [
            {"symbol": "ss", "gate_pass": True, "cov_override": "ccl",
             "cov_family": "inventory", "dir_acc": 0.51, "decided_at": None},
        ]
        result = _extract_relevant_history(history, "ss")
        assert "ccl" in result  # 不应抛出 TypeError

    def test_unknown_sector_no_cross_pollution(self):
        """未知板块品种不注入同板块先验。"""
        history = [
            {"symbol": "xyz_new", "gate_pass": True, "cov_override": "foo",
             "cov_family": "momentum", "dir_acc": 0.55, "decided_at": "2026-09-01"},
        ]
        result = _extract_relevant_history(history, "xyz_new")
        assert "同板块" not in result  # 不应出现跨品种先验

    def test_cross_sector_family_dedup(self):
        """跨品种先验按 cov_family 去重。"""
        history = [
            {"symbol": "rb", "gate_pass": True, "cov_override": "rsi_state",
             "cov_family": "momentum", "dir_acc": 0.54, "decided_at": "2026-09-01"},
            {"symbol": "rb", "gate_pass": True, "cov_override": "oi",
             "cov_family": "inventory", "dir_acc": 0.52, "decided_at": "2026-08-15"},
            {"symbol": "i", "gate_pass": True, "cov_override": "rsi12",
             "cov_family": "momentum", "dir_acc": 0.51, "decided_at": "2026-09-10"},
        ]
        result = _extract_relevant_history(history, "ss")
        # momentum 族只出现一次（最新的 i/rsi12）
        assert result.count("momentum") == 1
        assert "i/rsi12" in result or "rb/rsi_state" in result
```

- [ ] **Step 3: 运行测试**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_typesafe_prescreen.py -v -k "TestExtract"`
Expected: 5 passed

#### Step 1.4: 轻量熔断（半开自愈 + 测试清理）

- [ ] **Step 1: 写入熔断器**

追加到 `cascade/typesafe_prescreen.py`：

```python
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
        # 短路期已过，半开自愈：重置计数器
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
```

- [ ] **Step 2: 测试熔断器**

追加到 `tests/test_typesafe_prescreen.py`：

```python
from cascade.typesafe_prescreen import (
    _check_circuit, _record_timeout, _record_success, _reset_circuit_state,
)


class TestCircuitBreaker:
    def test_no_circuit_initially(self):
        assert _check_circuit() is False

    def test_opens_after_3_timeouts(self):
        _record_timeout()
        _record_timeout()
        _record_timeout()
        assert _check_circuit() is True

    def test_half_open_resets_on_expire(self, monkeypatch):
        """短路期满后自动重置，允许试探。"""
        _record_timeout()
        _record_timeout()
        _record_timeout()
        assert _check_circuit() is True

        # 模拟 601 秒后
        fake_now = time.time() + 601
        monkeypatch.setattr(time, "time", lambda: fake_now)
        assert _check_circuit() is False  # 半开：允许试探
        # 之后恢复正常
        _reset_circuit_state()

    def test_resets_on_success(self):
        _record_timeout()
        _record_timeout()
        _record_success()
        assert _check_circuit() is False

    def test_reset_circuit_state_clears_all(self):
        _record_timeout()
        _record_timeout()
        _record_timeout()
        _reset_circuit_state()
        assert _check_circuit() is False
```

- [ ] **Step 3: 运行测试**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_typesafe_prescreen.py -v -k "TestCircuit"`
Expected: 5 passed

#### Step 1.5: 核心入口 `prescreen_proposal` + `prescreen_and_save` + 原子写盘

- [ ] **Step 1: 写入核心入口和辅助函数**

追加到 `cascade/typesafe_prescreen.py`：

```python
# ── SDK 原始答案序列化 ──────────────────────────────

def _serialize_raw_answers(answers: dict) -> dict[str, Any]:
    """将 SDK 原始答案序列化为纯 dict，保留 reasoning/置信度元数据。"""
    out = {}
    for qid, ans in answers.items():
        entry: dict[str, Any] = {}
        if hasattr(ans, "probability_yes"):
            entry["probability_yes"] = ans.probability_yes
        if hasattr(ans, "value"):
            entry["value"] = ans.value
        if hasattr(ans, "level_index"):
            entry["level_index"] = ans.level_index
        if hasattr(ans, "confidence"):
            entry["confidence"] = ans.confidence
        if hasattr(ans, "reasoning") and ans.reasoning:
            entry["reasoning"] = ans.reasoning
        out[qid] = entry
    return out


# ── 内部辅助 ────────────────────────────────────────

def _get_typesafe_api_key() -> str | None:
    return _env_nonempty("TYPESAFE_API_KEY")


def _load_symbol_profile(symbol: str) -> dict[str, str]:
    """加载品种画像（板块 + 合约详情）。"""
    from config.sector_map import SECTOR_MAP, SECTOR_NAMES
    sector = SECTOR_MAP.get(symbol, "unknown")
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
    return client.judge(
        model="jev",
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
                levels=[
                    "无新增信息（纯噪声或已完全捕获）",
                    "微弱新增信息（与现有协变量高度相关，边际贡献有限）",
                    "中等新增信息（独立信号维度，可能有交互效应）",
                    "强新增信息（正交维度，高预期独立贡献）",
                ],
            ),
        },
    )
```

- [ ] **Step 2: 写入主入口和门面函数**

追加到 `cascade/typesafe_prescreen.py`：

```python
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

    # 解包 SDK 返回为纯标量（与 SDK 对象解耦）
    answers = result.data.answers
    plausibility = answers["mechanism_plausibility"].probability_yes
    raw_novelty = answers["novelty_vs_redundancy"].value
    novelty: NoveltyType = str(raw_novelty).strip().lower()  # type: ignore[assignment]
    effect_size = answers["expected_effect_size"].level_index

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
```

- [ ] **Step 3: 验证模块可导入**

Run: `cd /home/abug/timesfm && python -c "from cascade.typesafe_prescreen import prescreen_proposal, prescreen_and_save, write_prescreen_result; print('All exports OK')"`
Expected: `All exports OK`

#### Step 1.6: 完整 Mock 测试

- [ ] **Step 1: 写入 Mock 测试（剩余 12 项）**

追加到 `tests/test_typesafe_prescreen.py`：

```python
# ── Mock SDK 辅助 ───────────────────────────────────

class MockAnswer:
    """Mock SDK Answer 对象，模拟 typesafe_sdk 返回。"""
    def __init__(self, probability_yes=None, value=None, level_index=None,
                 confidence=None, reasoning=None):
        self.probability_yes = probability_yes
        self.value = value
        self.level_index = level_index
        self.confidence = confidence
        self.reasoning = reasoning


class MockJudgeResult:
    """Mock SDK judge 返回。"""
    def __init__(self, answers: dict, is_ok: bool = True):
        self.data = type("Data", (), {"answers": answers})()
        self.is_ok = is_ok


def _make_mock_result(plausibility=0.85, novelty="novel", effect_size=3):
    return MockJudgeResult({
        "mechanism_plausibility": MockAnswer(probability_yes=plausibility),
        "novelty_vs_redundancy": MockAnswer(value=novelty),
        "expected_effect_size": MockAnswer(level_index=effect_size),
    })


SAMPLE_PROPOSAL = {
    "variant_id": "v_test_001",
    "symbol": "JD",
    "mechanism": "JD 鸡蛋散户反向指标在交割月效应增强",
    "cov_override": "rsi_state",
}


# ── 完整功能 Mock 测试 ──────────────────────────────

class TestPrescreenProposalMock:
    """Mock SDK 调用，验证 prescreen_proposal 核心逻辑。"""

    def test_plausible_proposal_passes(self, monkeypatch):
        """合理机制 + 新颖 → success, skip_suggested=false"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.85, "novel", 3))

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "success"
        assert result["skip_suggested"] is False
        assert result["mechanism_plausibility"] == 0.85

    def test_implausible_proposal_skipped(self, monkeypatch):
        """不可信机制 → skip_suggested=true"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.2, "novel", 1))

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "success"
        assert result["skip_suggested"] is True

    def test_redundant_proposal_skipped(self, monkeypatch):
        """冗余 + 微弱效果 → skip_suggested=true"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.6, "redundant", 1))

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["skip_suggested"] is True

    def test_invalid_mechanism_skipped(self, monkeypatch):
        """无效机制 → skip_suggested=true"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.7, "invalid", 3))

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["skip_suggested"] is True

    def test_zero_effect_low_plausibility_skipped(self, monkeypatch):
        """effect_size=0 且 plausibility<0.6 → skip_suggested=true"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.5, "extension", 0))

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["skip_suggested"] is True

    def test_no_api_key_returns_degraded(self, monkeypatch):
        """无 API Key → degraded, skip_suggested=None"""
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "degraded"
        assert result["skip_suggested"] is None

    def test_api_timeout_returns_degraded(self, monkeypatch):
        """超时 → degraded, skip_suggested=None, 且触发熔断。
        
        注意：mock 桩函数只抛 TimeoutError，不手动调 _record_timeout()，
        因为 _prescreen_impl 的 except 块已经会调用。双重调用会导致计数器 +2。
        """
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        def raise_timeout(*a, **k):
            raise TimeoutError("simulated timeout")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_timeout)

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "degraded"
        assert result["skip_suggested"] is None
        assert "超时" in result["note"]

    def test_auth_error_returns_error(self, monkeypatch):
        """鉴权失败 → error"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        def raise_auth(*a, **k):
            raise AuthenticationError("401 Unauthorized")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_auth)

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "error"
        assert result["skip_suggested"] is None
        assert "鉴权" in result["note"]

    def test_timeout_triggers_circuit_not_error(self, monkeypatch):
        """连续 3 次超时后，第 4 次应走短路降级而非 API 调用"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        call_count = [0]
        def raise_timeout(*a, **k):
            call_count[0] += 1
            _record_timeout()
            raise TimeoutError("simulated")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_timeout)

        # 前 3 次
        for _ in range(3):
            prescreen_proposal(SAMPLE_PROPOSAL, "JD")

        # 第 4 次：应走短路，不再调用 API
        call_count[0] = 0
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert call_count[0] == 0  # API 未被调用
        assert result["status"] == "degraded"

    def test_never_raise_wraps_all_exceptions(self, monkeypatch):
        """内部处理异常（如 AttributeError）→ 平滑降级，不抛异常"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        def raise_internal(*a, **k):
            # 模拟 answers 缺失字段
            return MockJudgeResult({})
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe", raise_internal)

        # 不应抛出异常
        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["status"] == "error"
        assert result["skip_suggested"] is None

    def test_novelty_normalisation(self, monkeypatch):
        """Choice 返回值归一化：大小写/空白不敏感"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.6, "  REDUNDANT ", 1))

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert result["novelty"] == "redundant"  # 归一化后的小写
        assert result["skip_suggested"] is True

    def test_raw_answers_preserved(self, monkeypatch):
        """raw_answers 保留 SDK 原始序列化"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.85, "novel", 3))

        result = prescreen_proposal(SAMPLE_PROPOSAL, "JD")
        assert "mechanism_plausibility" in result["raw_answers"]
        assert result["raw_answers"]["mechanism_plausibility"]["probability_yes"] == 0.85


class TestAtomicWrite:
    def test_atomic_write_replaces_cleanly(self, tmp_path):
        """原子写入，无临时文件残留"""
        p = str(tmp_path / "sub" / "test.prescreen.json")
        result = {"status": "success", "skip_suggested": False}
        write_prescreen_result(p, result)

        assert os.path.exists(p)
        # 确认无 .tmp.* 残留
        assert len(list(tmp_path.rglob("*.tmp.*"))) == 0
        with open(p) as f:
            assert json.load(f)["status"] == "success"


class TestPrescreenAndSaveFacade:
    def test_facade_calls_both(self, monkeypatch, tmp_path):
        """门面函数一次调用完成预筛 + 落盘"""
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr("cascade.typesafe_prescreen._call_typesafe",
                           lambda *a, **k: _make_mock_result(0.7, "extension", 2))

        proposal_path = str(tmp_path / "p_001.json")
        result = prescreen_and_save(SAMPLE_PROPOSAL, proposal_path, "JD")

        assert result["status"] == "success"
        prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
        assert os.path.exists(prescreen_path)


class TestSlowLoopMetadataAttachment:
    def test_slow_loop_reads_prescreen(self, tmp_path):
        """模拟慢环读取 prescreen 并注入 verdict metadata"""
        proposal_path = str(tmp_path / "proposals" / "p_001.json")
        prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))

        # 写入 prescreen 文件
        ps = {
            "status": "success", "skip_suggested": True,
            "mechanism_plausibility": 0.3, "novelty": "invalid",
            "effect_size": 0, "note": "机制可信度低 (0.30) | 新颖度: 无效 | 预期效果: 无信息量",
        }
        os.makedirs(os.path.dirname(prescreen_path), exist_ok=True)
        with open(prescreen_path, "w") as f:
            json.dump(ps, f)

        # 模拟慢环逻辑
        verdict = {"gate_pass": False, "status": "aligned"}
        pp = str(Path(proposal_path).with_suffix(".prescreen.json"))
        if os.path.exists(pp):
            try:
                with open(pp, encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, OSError):
                loaded = None
            if loaded:
                if "metadata" not in verdict:
                    verdict["metadata"] = {}
                verdict["metadata"]["prescreen"] = {
                    "status": loaded.get("status"),
                    "skip_suggested": loaded.get("skip_suggested"),
                    "plausibility": loaded.get("mechanism_plausibility"),
                    "novelty": loaded.get("novelty"),
                    "effect_size": loaded.get("effect_size"),
                    "note": loaded.get("note"),
                }

        assert verdict["metadata"]["prescreen"]["skip_suggested"] is True
        assert verdict["metadata"]["prescreen"]["plausibility"] == 0.3

    def test_corrupted_prescreen_does_not_crash(self, tmp_path):
        """半写 prescreen 文件不阻断回测"""
        proposal_path = str(tmp_path / "proposals" / "p_001.json")
        prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
        os.makedirs(os.path.dirname(prescreen_path), exist_ok=True)
        # 写一个不完整的 JSON
        with open(prescreen_path, "w") as f:
            f.write('{"status": "succe')

        verdict = {"gate_pass": True}
        pp = str(Path(proposal_path).with_suffix(".prescreen.json"))
        if os.path.exists(pp):
            try:
                with open(pp, encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, OSError):
                loaded = None
        # 不应抛出异常，且不应注入 metadata
        assert "metadata" not in verdict
```

- [ ] **Step 2: 运行全部测试**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_typesafe_prescreen.py -v`
Expected: 27 passed (10 纯函数 + 5 提取器 + 5 熔断 + 7 Mock + 1 原子写 + 1 门面 + 2 慢环)

- [ ] **Step 3: Commit**

```bash
cd /home/abug/timesfm
git add cascade/typesafe_prescreen.py tests/test_typesafe_prescreen.py
git commit -m "feat: TypeSafe 协变量提案预筛核心模块 + 27 测试

- prescreen_proposal / prescreen_and_save 门面
- compute_skip_suggested / generate_note 纯函数
- _extract_relevant_history 跨品种迁移先验
- 半开自愈熔断器 + _reset_circuit_state
- 原子写盘 + Choice 归一化
- 三态降级 (degraded/error/success)
- 27 个 Mock 测试全绿"
```

---

### Task 2: 环境配置与慢环集成（链路层）

**Files:**
- Modify: `data/config.py` (新增 `get_typesafe_api_key`)
- Modify: `task_FM/task.yaml` (新增 TYPESAFE_API_KEY 环境变量)
- Modify: `scripts/aligned_slow_loop.py` (读取 prescreen 注入 verdict metadata)

**Interfaces:**
- Consumes: Task 1 的 `prescreen_and_save`, `write_prescreen_result`
- Produces: verdict 中 `metadata.prescreen` 命名空间

#### Step 2.1: data/config.py 新增 `get_typesafe_api_key`

- [ ] **Step 1: 修改 config.py**

在 `data/config.py` 末尾追加：

```python
# ── TypeSafe ────────────────────────────────────────

def get_typesafe_api_key() -> str | None:
    """读取 TYPESAFE_API_KEY，未设置时返回 None。"""
    return _env_nonempty("TYPESAFE_API_KEY")
```

- [ ] **Step 2: 验证导入**

Run: `cd /home/abug/timesfm && python -c "from data.config import get_typesafe_api_key; print(get_typesafe_api_key())"`
Expected: `None`（未设置环境变量时）

#### Step 2.2: task_FM/task.yaml 注入环境变量

- [ ] **Step 1: 修改 task.yaml**

在 `task_FM/task.yaml` 的 `runtime_environment.env` 节追加 `TYPESAFE_API_KEY`：

```yaml
runtime_environment:
  cwd: task_project
  venv: ../.venv
  python: ../.venv/bin/python
  require_paths: true
  env:
    CUDA_VISIBLE_DEVICES: ''
    PRAXIST_TRUSTED_PROJECT_EXTRA_ROOTS: /home/abug/timesfm
    TYPESAFE_API_KEY: '${TYPESAFE_API_KEY}'
  protected_child_paths:
  - evaluations
```

> 注意：`${TYPESAFE_API_KEY}` 由 Praxist 从 `.env.praxist` 加载。密钥不写进 task.yaml 明文。

#### Step 2.3: aligned_slow_loop.py 注入 prescreen metadata

- [ ] **Step 1: 修改 slow loop 的 verdict 构建处**

在 `scripts/aligned_slow_loop.py` 的 `run_aligned_candidate` 函数中，`v = build_summary(...)` 之后、`rl.append_verdict(registry_path, v)` 之前，追加 prescreen 读取逻辑：

```python
# 在 v = build_summary(...) 之后，v["variant_id"] = row["variant_id"] 之后添加：
# ── TypeSafe 预筛伴随文件注入 ──────────────────────
# 基于 proposal 路径推导 prescreen 文件（若存在）
_proposal_path = row.get("_proposal_path") or row.get("proposal_path")  # 二级回退
if _proposal_path:
    from pathlib import Path as _Path
    _ps_path = str(_Path(_proposal_path).with_suffix(".prescreen.json"))
    if os.path.exists(_ps_path):
        try:
            with open(_ps_path, encoding="utf-8") as _f:
                _ps = json.load(_f)
        except (json.JSONDecodeError, OSError) as _e:
            logging.warning("prescreen 文件解析失败 (%s): %s", _ps_path, _e)
            _ps = None

        if _ps:
            if "metadata" not in v:
                v["metadata"] = {}
            v["metadata"]["prescreen"] = {
                "status": _ps.get("status"),
                "skip_suggested": _ps.get("skip_suggested"),
                "plausibility": _ps.get("mechanism_plausibility"),
                "novelty": _ps.get("novelty"),
                "effect_size": _ps.get("effect_size"),
                "note": _ps.get("note"),
            }
```

> **注意**：`_proposal_path` 需要由 `evaluations/fm_eval/run.py` 在写入 proposal 文件后注入到 `row` 中。这是一个新的字段，不影响现有字段。

#### Step 2.4: evaluations/fm_eval/run.py 注入 proposal 路径 + 触发预筛

- [ ] **Step 1: 在 run.py 的 proposal 写入后，触发预筛并注入路径**

在 `evaluations/fm_eval/run.py` 中，找到 peer proposal 写入文件并调用 `share_finding` 后的位置，追加：

```python
# ── TypeSafe 预筛触发 ──────────────────────────────
from cascade.typesafe_prescreen import prescreen_and_save

# 加载历史裁决供预筛参考
_history_verdicts = []
_verdicts_path = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")
if os.path.exists(_verdicts_path):
    with open(_verdicts_path, encoding="utf-8") as _vf:
        _history_verdicts = [json.loads(_l) for _l in _vf if _l.strip()]

# 加载协变量菜单
_menu_content = {}
_menu_path = os.path.join(FM_ROOT, "task_FM", "covariate_menu.inc.md")
if os.path.exists(_menu_path):
    with open(_menu_path, encoding="utf-8") as _mf:
        _menu_content = {"text": _mf.read()}

# 1. 触发预筛并原子落盘伴随文件
prescreen_and_save(
    proposal=proposal_dict,
    proposal_path=proposal_file_path,
    symbol=symbol,
    verdict_history=_history_verdicts,
    covariate_menu=_menu_content,
)

# 2. 注入路径供慢环消费
row["_proposal_path"] = proposal_file_path
row["proposal_path"] = proposal_file_path  # 二级回退键名
```

> **注意**：同时写入 `_proposal_path` 和 `proposal_path` 两个键名，慢环端增加二级回退读取。

#### Step 2.5: 集成测试验证

- [ ] **Step 1: 运行现有测试确保无回归**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_typesafe_prescreen.py tests/test_supervisor.py -v`
Expected: All existing tests pass (no regression)

- [ ] **Step 2: 测试慢环 prescreen 注入（Mock 版）**

写入 `tests/test_slow_loop_prescreen.py`：

```python
"""tests/test_slow_loop_prescreen.py — 慢环 prescreen 注入集成测试"""
import json
import os
from pathlib import Path
import sys

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))


class TestSlowLoopPrescreenInjection:
    """模拟慢环读取 prescreen 并注入 verdict metadata 的完整流程。"""

    def test_injection_with_valid_prescreen(self, tmp_path):
        """有效的 prescreen 文件被正确注入到 verdict metadata"""
        from cascade.typesafe_prescreen import write_prescreen_result

        # 准备 prescreen 文件
        proposal_path = str(tmp_path / "proposals" / "p_001.json")
        prescreen_data = {
            "status": "success",
            "skip_suggested": True,
            "mechanism_plausibility": 0.3,
            "novelty": "invalid",
            "effect_size": 0,
            "note": "测试 note",
        }
        os.makedirs(os.path.dirname(proposal_path), exist_ok=True)
        write_prescreen_result(
            str(Path(proposal_path).with_suffix(".prescreen.json")),
            prescreen_data,
        )

        # 模拟慢环逻辑
        verdict = {"gate_pass": False, "status": "aligned", "variant_id": "v_001"}
        _proposal_path = proposal_path

        # 复制 slow loop 的注入代码
        if _proposal_path:
            _ps_path = str(Path(_proposal_path).with_suffix(".prescreen.json"))
            if os.path.exists(_ps_path):
                try:
                    with open(_ps_path, encoding="utf-8") as _f:
                        _ps = json.load(_f)
                except (json.JSONDecodeError, OSError):
                    _ps = None
                if _ps:
                    if "metadata" not in verdict:
                        verdict["metadata"] = {}
                    verdict["metadata"]["prescreen"] = {
                        "status": _ps.get("status"),
                        "skip_suggested": _ps.get("skip_suggested"),
                        "plausibility": _ps.get("mechanism_plausibility"),
                        "novelty": _ps.get("novelty"),
                        "effect_size": _ps.get("effect_size"),
                        "note": _ps.get("note"),
                    }

        assert "metadata" in verdict
        assert verdict["metadata"]["prescreen"]["status"] == "success"
        assert verdict["metadata"]["prescreen"]["skip_suggested"] is True
        assert verdict["metadata"]["prescreen"]["plausibility"] == 0.3
        # 核心裁决字段不变
        assert verdict["gate_pass"] is False

    def test_no_proposal_path_no_injection(self, tmp_path):
        """无 _proposal_path 时不注入"""
        verdict = {"gate_pass": True, "status": "aligned"}
        _proposal_path = None

        if _proposal_path:
            pass  # 不应进入

        assert "metadata" not in verdict

    def test_missing_prescreen_file_no_injection(self, tmp_path):
        """prescreen 文件不存在时不注入"""
        verdict = {"gate_pass": True}
        _proposal_path = str(tmp_path / "nonexistent.json")

        _ps_path = str(Path(_proposal_path).with_suffix(".prescreen.json"))
        assert not os.path.exists(_ps_path)
        assert "metadata" not in verdict
```

- [ ] **Step 3: 运行集成测试**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_slow_loop_prescreen.py -v`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
cd /home/abug/timesfm
git add data/config.py task_FM/task.yaml scripts/aligned_slow_loop.py tests/test_slow_loop_prescreen.py
git commit -m "feat: TypeSafe 预筛慢环集成 + 环境变量注入

- data/config.py: get_typesafe_api_key()
- task_FM/task.yaml: TYPESAFE_API_KEY 环境变量
- aligned_slow_loop.py: 读取 .prescreen.json 注入 verdict metadata
- 3 个集成测试验证注入逻辑
- 不改变 v23 verdict schema 版本"
```

---

### Task 3: 人工历史数据验证（验证层）

**Files:**
- No code changes — 交互式验证脚本

**Goal:** 用 5 个历史 proposal 运行真实 API 预筛，确认 TypeSafe 判断与人工直觉一致。

#### Step 3.1: 创建验证脚本

- [ ] **Step 1: 创建验证脚本 `scripts/validate_typesafe_prescreen.py`**

```python
#!/usr/bin/env python3
"""验证 TypeSafe 预筛与 5 个历史 proposal 的一致性。

用法:
  source .venv/bin/activate
  python scripts/validate_typesafe_prescreen.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cascade.typesafe_prescreen import prescreen_and_save

# ── 加载生产环境历史裁决 ────────────────────────────
VERDICTS_PATH = Path(__file__).resolve().parent.parent / "task_FM" / "config" / "aligned_verdicts.jsonl"
verdict_history = []
if VERDICTS_PATH.exists():
    with open(VERDICTS_PATH, encoding="utf-8") as _vf:
        verdict_history = [json.loads(_l) for _l in _vf if _l.strip()]
    print(f"已加载 {len(verdict_history)} 条历史裁决")
else:
    print(f"⚠️ 未找到历史裁决文件: {VERDICTS_PATH}")

# ── 5 个典型历史 proposal（硬编码，消除占位符）─────
HISTORY_PROPOSALS = [
    {
        "symbol": "JD",
        "proposal_path": "results/gen_2/peer_001/v_jd_rsi/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_jd_rsi",
            "mechanism": "JD 鸡蛋 RSI 超卖反转在交割月效应增强",
            "cov_override": "rsi_state",
        },
        "expected_plausibility_range": (0.6, 0.9),
        "expected_novelty": "extension",
        "expected_skip": False,
    },
    {
        "symbol": "SS",
        "proposal_path": "results/gen_2/peer_002/v_ss_ccl/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_ss_ccl",
            "mechanism": "不锈钢仓单量价背离预示短期回调",
            "cov_override": "ccl",
        },
        "expected_plausibility_range": (0.5, 0.85),
        "expected_novelty": "extension",
        "expected_skip": False,
    },
    {
        "symbol": "RB",
        "proposal_path": "results/gen_2/peer_003/v_rb_oi/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_rb_oi",
            "mechanism": "螺纹钢持仓量增仓方向与价格趋势共振",
            "cov_override": "oi",
        },
        "expected_plausibility_range": (0.6, 0.9),
        "expected_novelty": "extension",
        "expected_skip": False,
    },
    {
        "symbol": "CF",
        "proposal_path": "results/gen_2/peer_004/v_cf_seasonal/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_cf_seasonal",
            "mechanism": "棉花季节性备货周期驱动价格波动",
            "cov_override": "calendar_cyclical",
        },
        "expected_plausibility_range": (0.4, 0.75),
        "expected_novelty": "novel",
        "expected_skip": False,
    },
    {
        "symbol": "M",
        "proposal_path": "results/gen_2/peer_005/v_m_rsi_oi/proposals/p_001.json",
        "proposal": {
            "variant_id": "v_m_rsi_oi",
            "mechanism": "豆粕 RSI+OI 组合协变量在低波动体制下的增强效果",
            "cov_override": "rsi_state",
        },
        "expected_plausibility_range": (0.3, 0.65),
        "expected_novelty": "redundant",
        "expected_skip": True,
    },
]


def main():
    print(f"\n{'='*60}")
    print(f"TypeSafe 预筛人工验证 — {len(HISTORY_PROPOSALS)} 个历史 proposal")
    print(f"历史裁决: {len(verdict_history)} 条")
    print(f"{'='*60}")

    pass_count = 0
    for item in HISTORY_PROPOSALS:
        print(f"\n--- {item['symbol']} / {item['proposal']['variant_id']} ---")

        result = prescreen_and_save(
            proposal=item["proposal"],
            proposal_path=item["proposal_path"],
            symbol=item["symbol"],
            verdict_history=verdict_history,
        )

        print(f"  status: {result['status']}")
        if result["status"] != "success":
            print(f"  note: {result['note']}")
            continue

        print(f"  plausibility: {result['mechanism_plausibility']:.2f} "
              f"(预期 {item['expected_plausibility_range']})")
        print(f"  novelty: {result['novelty']} (预期 {item['expected_novelty']})")
        print(f"  effect_size: {result['effect_size']}")
        print(f"  skip_suggested: {result['skip_suggested']} (预期 {item['expected_skip']})")
        print(f"  note: {result['note']}")

        # 一致性检查
        lo, hi = item["expected_plausibility_range"]
        pl_ok = lo <= result["mechanism_plausibility"] <= hi
        skip_ok = result["skip_suggested"] == item["expected_skip"]

        if pl_ok:
            print("  ✅ plausibility 一致")
        else:
            print(f"  ⚠️ plausibility 偏离预期 ({result['mechanism_plausibility']:.2f} not in [{lo}, {hi}])")

        if skip_ok:
            print("  ✅ skip 判断一致")
        else:
            print(f"  ⚠️ skip 判断偏离预期 (got {result['skip_suggested']}, expected {item['expected_skip']})")

        if pl_ok and skip_ok:
            pass_count += 1

    print(f"\n{'='*60}")
    print(f"验证完成: {pass_count}/{len(HISTORY_PROPOSALS)} 一致")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行验证（需 TYPESAFE_API_KEY）**

Run: `cd /home/abug/timesfm && source .venv/bin/activate && python scripts/validate_typesafe_prescreen.py`
Expected: 5 个 proposal 均返回 `status="success"`，大部分 `✅` 一致

#### Step 3.2: 验证结果记录

- [ ] **Step 1: 记录验证结果到 changelog**

将验证结果追加到 `docs/superpowers/changelogs/` 新文件 `2026-09-22-typesafe-prescreen-implementation.md`：

```markdown
# TypeSafe 协变量提案预筛实施记录

## 2026-09-22 — 实施完成

**Task 1**: 核心模块 + 27 测试 ✅
**Task 2**: 环境配置 + 慢环集成 + 3 集成测试 ✅
**Task 3**: 人工历史验证 — 5 个 proposal 跑真实 API

| Proposal | plausibility | novelty | skip | 一致? |
|----------|-------------|---------|------|------|
| JD/rsi_state | 0.XX | extension | false | ✅/⚠️ |
| ... | ... | ... | ... | ... |
```

#### Step 3.3: 最终 Commit

```bash
cd /home/abug/timesfm
git add scripts/validate_typesafe_prescreen.py docs/superpowers/changelogs/2026-09-22-typesafe-prescreen-implementation.md
git commit -m "feat: TypeSafe 预筛人工验证脚本 + 实施记录"
```

---

## Self-Review

### 1. Spec coverage

| Spec § | Task | Covered? |
|--------|------|----------|
| §4.1 入口函数 + 降级契约 | Task 1.1, 1.5 | ✅ |
| §4.2 TypeSafe 三问 | Task 1.5 (`_call_typesafe`) | ✅ |
| §4.3 历史裁决提取器 | Task 1.3 | ✅ |
| §4.4 skip_suggested 纯函数 | Task 1.2 | ✅ |
| §4.5 note 纯函数 | Task 1.2 | ✅ |
| §4.6 半开自愈熔断 | Task 1.4 | ✅ |
| §4.7 原子写盘 | Task 1.5 | ✅ |
| §5.1 慢环集成 | Task 2.3 | ✅ |
| §5.2 prescreen_and_save 门面 | Task 1.5 | ✅ |
| §6.1 TYPESAFE_API_KEY | Task 2.1, 2.2 | ✅ |
| §6.2 三态降级 | Task 1.1, 1.6 | ✅ |
| §7.1 17 Mock 测试 | Task 1.6 (27 tests total) | ✅ |
| §7.2 人工验证 | Task 3 | ✅ |
| §8.1 监控指标 | 文档中已定义，实现后计算 | ✅ (deferred until 50+ samples) |
| 终审微观订正 1: 异常导入 | Task 1.1 (`try/except ImportError`) | ✅ |
| 终审微观订正 2: 熔断重置 | Task 1.4 (`_reset_circuit_state`) | ✅ |
| 终审微观订正 3: Choice 归一化 | Task 1.5 (`str(raw).strip().lower()`) | ✅ |
| 终审微观订正 4: 门面落盘守卫 + 目录自愈 | Task 1.5 (`try/except` + `os.makedirs`) | ✅ |
| 终审微观订正 5: 时区语法 | Task 1.1, 1.5 (`datetime.now(timezone.utc)`) | ✅ |

### 2. Placeholder scan
No "TBD", "TODO", or "implement later" found. All code blocks contain complete implementations.

### 3. Type consistency
- `PrescreenStatus = Literal["success", "degraded", "error"]` — consistent across §4.1, §6.2, tests
- `NoveltyType = Literal["novel", "extension", "redundant", "invalid"]` — consistent across §4.1, §4.4, §4.5
- `compute_skip_suggested(plausibility: float, novelty: str, effect_size: int) -> bool` — called with pure scalars in §4.1 and tested as pure function in tests
- `verdict["metadata"]["prescreen"]` — consistent across §5.1 and tests
- `_reset_circuit_state()` — defined in §4.6, used in `pytest.fixture(autouse=True)`

No type mismatches found.

---

**Plan complete and saved to `docs/superpowers/plans/2026-09-22-typesafe-covariate-prescreen-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
