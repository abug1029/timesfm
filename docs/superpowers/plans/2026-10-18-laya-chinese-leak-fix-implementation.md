# Laya 预筛中文泄漏修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Laya 预筛 predicted_direction 字段中文泄漏问题，确保发送到 Laya 的 state 100% 无东亚宽字符

**Architecture:** 两条腿走路：(1) 下游过滤——在 `_build_state()` 中剥除 predicted_direction 的中文字符和全角标点，含空壳检测回退；(2) 源头约束——在 peer prompt 中强制 predicted_direction English only。附加去重优化避免重复调用 Laya。

**Tech Stack:** Python 3.11, pytest, regex, WSL Ubuntu 22.04

**Spec:** `/home/abug/timesfm/docs/superpowers/specs/2026-10-18-laya-chinese-leak-fix-spec.md`

## Global Constraints

- **PrescreenStatus 枚举不扩**：保持 `Literal["success", "degraded", "error"]` 三值，与 Frozen lifecycle spec §71/§422 一致
- **验收字符类**：禁止 CJK 统一表意文字（U+4E00–U+9FFF）、CJK 标点（U+3000–U+303F）、全角标点（U+FF00–U+FFEF 标点区）；允许 ASCII、拉丁扩展、半角符号、全角数字/字母
- **空壳阈值**：`_PD_MIN_LEN = 12`，对齐实测 ~496 空壳（27.6%，双道 strip 后）
- **language 字段**：best-effort，不与成功率验收强绑
- **回滚**：Phase 1 为单 logical unit，可 `git revert` 整体回滚
- **Commit 策略**：Phase 1（Task 1–5）每 Task 独立 commit，方便逐 task review；Phase 2（Task 6）、Phase 3（Task 7）各自独立 commit

## Review Focus

1. **空壳误判**：典型空壳 `"-> long, -> short"` 的 core="longshort" 长 **9**（`-`/`>`/`,`/空格被 `re.sub` 剥，方向词 `long`/`short` 保留，下划线 `_` 不在剥除字符类中），阈值 12 判为 True → Task 2 单测覆盖
2. **全角标点残留**：`"价差（利润） -> long"` → `"-> long"`（全角括号 `（）` 被 `_FULLWIDTH_PUNCT` 剥，前导空格被 `.strip()` 剥）→ Task 1 单测覆盖
3. **全量扫描**：动态计数所有 proposals（不硬编码 7194），0 条 state 含东亚宽字符 → Task 5 门禁脚本验收（验收禁止类：Han + CJK 标点 + 全角标点）
4. **去重不丢新提案**：仅跳过 REGISTRY/QUEUE 已有 variant → Task 6 集成测试（按真实 `process_proposal` 签名）
5. **短公式空壳**：`"RSI(6)>80 超买 -> short"` → strip 后 `"RSI(6)>80 -> short"` → core=`"RSI680short"` len=11 < 12 → 判为空壳 → Task 3 集成测试覆盖

---

### Task 1: _strip_chinese() 函数 + 单元测试

**Files:**
- Modify: `cascade/typesafe_prescreen.py:1-50` (添加函数 + 正则常量)
- Create: `tests/test_strip_chinese.py`

**Interfaces:**
- Consumes: 无
- Produces: `_strip_chinese(s: str) -> str`，双道剥离：(1) CJK 汉字+CJK 标点 → 空格，(2) 全角标点 → 空格，然后合并空白 + `.strip(" (;,)")`

> **算法行为精确记录**（TDD 断言依据）：
> - `_ZH.sub(' ', s)` 把每个 CJK 字符替换为空格
> - `_FULLWIDTH_PUNCT.sub(' ', result)` 把全角标点替换为空格
> - `re.sub(r'\s+', ' ', result)` 合并连续空白
> - `.strip(' (;,)')` 剥首尾的空格、括号、分号、逗号
> - **注意**：括号内部空格不会被剥（如 `(7-9 )` 中的空格保留）；下划线 `_` 不在任何正则中

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strip_chinese.py
import pytest
from cascade.typesafe_prescreen import _strip_chinese

def test_strip_chinese_basic():
    """纯中文前缀 → 前导空格被 strip 掉"""
    # "价差加速度转正" 7 字 → 7 空格 → collapse → " " → strip → 无
    assert _strip_chinese("价差加速度转正 -> long") == "-> long"

def test_strip_chinese_mixed():
    """中英文混合：括号内中文被剥，括号内空格保留"""
    # "(7-9月出栏高峰)" → "(7-9     )" → collapse → "(7-9 )" → strip 不影响内部
    assert _strip_chinese("seasonal_supply_peak(7-9月出栏高峰) -> short") == "seasonal_supply_peak(7-9 ) -> short"

def test_strip_chinese_fullwidth_punct():
    """全角标点剥离（v3 二次清洗）"""
    # "价差（利润）" → "  （   ） " → fullwidth pass → "      " → collapse → " " → strip → 无
    assert _strip_chinese("价差（利润） -> long") == "-> long"
    # "超买" 被剥，其余保留
    assert _strip_chinese("RSI(6)>80 超买 -> short") == "RSI(6)>80 -> short"

def test_strip_chinese_preserve_ascii():
    """保留 ASCII、下划线、数字、半角括号"""
    assert _strip_chinese("oi_up_with_price -> long") == "oi_up_with_price -> long"
    assert _strip_chinese("RSI(6)>80 -> short") == "RSI(6)>80 -> short"

def test_strip_chinese_empty():
    """空串"""
    assert _strip_chinese("") == ""

def test_strip_chinese_pure_chinese():
    """纯中文 → 全空 → strip → 空串"""
    assert _strip_chinese("价差加速度转正利润加速扩张") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_strip_chinese.py -v`
Expected: FAIL with "module 'cascade.typesafe_prescreen' has no attribute '_strip_chinese'"

- [ ] **Step 3: Write minimal implementation**

```python
# cascade/typesafe_prescreen.py 顶部（import 区之后）添加
import re

# v3: 主正则剥 CJK 汉字 + CJK 标点；二次清洗剥全角标点（保留全角数字/字母）
_ZH = re.compile(r'[一-鿿　-〿]+')
_FULLWIDTH_PUNCT = re.compile(r'[！-／：-＠［-＿｛-･]+')

def _strip_chinese(s: str) -> str:
    """剥中文字符 + 全角标点，保留英文/数字/半角符号/空格/下划线。

    双道剥离：
      1. CJK 汉字 (U+4E00–U+9FFF) + CJK 标点 (U+3000–U+303F) → 空格
      2. 全角标点 (U+FF01–U+FF65 中的标点区) → 空格
      3. 合并连续空白
      4. 剥首尾空格/括号/分号/逗号

    注意：下划线 _ 不在任何正则中，会保留。括号内空格会保留。
    """
    result = _ZH.sub(' ', s)
    result = _FULLWIDTH_PUNCT.sub(' ', result)
    return re.sub(r'\s+', ' ', result).strip(' (;,)')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_strip_chinese.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/abug/timesfm
git add cascade/typesafe_prescreen.py tests/test_strip_chinese.py
git commit -m "feat(cascade): add _strip_chinese() dual-pass CJK + fullwidth punct removal

- Pass 1: strip CJK ideographs (U+4E00-U+9FFF) + CJK punctuation (U+3000-U+303F)
- Pass 2: strip fullwidth punctuation (U+FF01-U+FF65 punct range), preserves fullwidth digits/letters
- Trailing whitespace collapse + strip(' (;,)')
- Unit tests: basic/mixed/fullwidth/ASCII/empty/pure-Chinese

Ref: spec 2026-10-18-laya-chinese-leak-fix-spec.md §3.1"
```

---

### Task 2: _is_shell_pd() 函数 + 单元测试

**Files:**
- Modify: `cascade/typesafe_prescreen.py:51-70` (添加函数 + 阈值常量)
- Modify: `tests/test_strip_chinese.py` (追加测试)

**Interfaces:**
- Consumes: `_strip_chinese()` 的输出（已剥 CJK + 全角标点的字符串）
- Produces: `_is_shell_pd(stripped: str) -> bool`，判定 strip 后是否为近空壳

> **算法行为精确记录**（TDD 断言依据）：
> - `re.sub(r'[->,;|()+\s]', '', stripped)` 剥除以下字符：`-`, `>`, `,`, `;`, `|`, `(`, `)`, `+`, 空白
> - **不去除**：下划线 `_`、字母、数字、冒号 `:`、点 `.` 等
> - 典型空壳 `"-> long, -> short"` → 剥后 `"longshort"` len=**9**（不是 8）
> - 有效 PD `"oi_up_with_price -> long"` → 剥后 `"oi_up_with_pricelong"` len=**20**（下划线保留）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strip_chinese.py 追加
from cascade.typesafe_prescreen import _is_shell_pd

def test_is_shell_pd_typical_shell():
    """典型空壳：仅剩方向词 long/short"""
    # "-> long, -> short" → 剥 - > , 空格 → "longshort" len=9 < 12 → True
    assert _is_shell_pd("-> long, -> short") == True

def test_is_shell_pd_short_formula():
    """短公式空壳（Review Focus §5）：RSI(6)>80 超买 -> short → strip 后 core len=11"""
    # "RSI(6)>80 -> short" → 剥 ( ) > 空格 → "RSI680short" len=11 < 12 → True
    assert _is_shell_pd("RSI(6)>80 -> short") == True

def test_is_shell_pd_valid_pd():
    """有效 PD：含条件描述，下划线保留"""
    # "oi_up_with_price -> long" → 剥 -> 空格 → "oi_up_with_pricelong" len=20 >= 12 → False
    assert _is_shell_pd("oi_up_with_price -> long") == False
    # "seasonal_supply_peak(7-9 ) -> short" → 剥 ( ) - > 空格 → "seasonal_supply_peak79short" len=29 → False
    assert _is_shell_pd("seasonal_supply_peak(7-9 ) -> short") == False

def test_is_shell_pd_threshold_boundary():
    """阈值边界：用无方向词的纯 core 串，避免方向词干扰长度计算"""
    # 无方向词：剥后 = 原串（无 ->,;|()+\s 可剥）
    assert _is_shell_pd("abcdefghijk") == True       # len=11 < 12 → True
    assert _is_shell_pd("abcdefghijkl") == False      # len=12 >= 12 → False
    assert _is_shell_pd("abcdefghijklm") == False     # len=13 >= 12 → False

def test_is_shell_pd_empty():
    """空串"""
    assert _is_shell_pd("") == True  # len=0 < 12 → True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_strip_chinese.py::test_is_shell_pd_typical_shell -v`
Expected: FAIL with "module 'cascade.typesafe_prescreen' has no attribute '_is_shell_pd'"

- [ ] **Step 3: Write minimal implementation**

```python
# cascade/typesafe_prescreen.py 追加
_PD_MIN_LEN = 12  # v3: 对齐实测 ~496 空壳（27.6%，双道 strip 后）

def _is_shell_pd(stripped: str) -> bool:
    """判定 strip 后是否为近空壳。

    算法：剥除 -> , ; | ( ) + 空白 后，剩余核心长度 < _PD_MIN_LEN 视为空壳。
    注意：下划线 _ 不在剥除字符类中，会保留并计入长度。

    v3: 阈值 12。典型空壳 '-> long, -> short' → core='longshort' len=9 < 12 → True。
    """
    core = re.sub(r'[->,;|()+\s]', '', stripped)
    return len(core) < _PD_MIN_LEN
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_strip_chinese.py -v`
Expected: PASS (12 tests = 6 from Task 1 + 6 new)

- [ ] **Step 5: Commit**

```bash
cd /home/abug/timesfm
git add cascade/typesafe_prescreen.py tests/test_strip_chinese.py
git commit -m "feat(cascade): add _is_shell_pd() empty-shell detection, threshold=12

- _PD_MIN_LEN=12 aligns with measured ~496 shells (27.6%, dual-pass strip)
- re.sub strips ->,;|()+ and whitespace; underscores preserved
- Typical shell '-> long, -> short' → core='longshort' len=9 < 12 → True
- Short-formula shell 'RSI(6)>80 -> short' → core='RSI680short' len=11 < 12 → True
- Valid PD 'oi_up_with_price -> long' → core='oi_up_with_pricelong' len=20 → False
- Boundary tests use pure core strings (no direction words) for exact length control

Ref: spec 2026-10-18-laya-chinese-leak-fix-spec.md §3.1"
```

---

### Task 3: _build_state() 修改 + 集成测试

**Files:**
- Modify: `cascade/typesafe_prescreen.py:255-282` (`_build_state` 函数)
- Create: `tests/test_build_state_no_cjk.py`

**Interfaces:**
- Consumes: `_strip_chinese()`, `_is_shell_pd()`, proposal dict, symbol str
- Produces: state dict with `predicted_direction` stripped + shell fallback + `language: "en"`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_state_no_cjk.py
import re
from cascade.typesafe_prescreen import _build_state

# 东亚宽字符正则（与门禁脚本一致）
_EAST_ASIAN_WIDE = re.compile(r'[一-鿿　-〿！-／：-＠［-＿｛-･]')

def test_build_state_strips_chinese_pd():
    """predicted_direction 含中文 → strip 后无东亚宽字符"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "oi",
        "covariate_family": "positioning",
        "predicted_direction": "seasonal_supply_peak(7-9月出栏高峰) -> short",
    }
    state = _build_state(proposal, "p", None, None)
    pd = state["proposal_summary"]["predicted_direction"]
    assert not _EAST_ASIAN_WIDE.search(pd), f"PD still has East Asian wide chars: {pd!r}"

def test_build_state_shell_pd_fallback():
    """空壳 PD → 置为空串"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "oi",
        "covariate_family": "positioning",
        "predicted_direction": "价差加速度转正 -> long, 加速度转负 -> short",
    }
    state = _build_state(proposal, "p", None, None)
    pd = state["proposal_summary"]["predicted_direction"]
    # strip 后 "-> long, -> short" → core="longshort" len=9 < 12 → 空壳 → ""
    assert pd == ""

def test_build_state_short_formula_shell():
    """短公式空壳（Review Focus §5）：RSI(6)>80 超买 -> short → 空壳"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "rsi",
        "covariate_family": "momentum",
        "predicted_direction": "RSI(6)>80 超买 -> short",
    }
    state = _build_state(proposal, "p", None, None)
    pd = state["proposal_summary"]["predicted_direction"]
    # strip 后 "RSI(6)>80 -> short" → core="RSI680short" len=11 < 12 → 空壳 → ""
    assert pd == ""

def test_build_state_language_field():
    """state 包含 language: en（best-effort）"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "p",
        "cov_override": "oi",
        "covariate_family": "positioning",
        "predicted_direction": "oi_up_with_price -> long",
    }
    state = _build_state(proposal, "p", None, None)
    assert state.get("language") == "en"

def test_build_state_preserves_other_fields():
    """其他字段不受影响"""
    proposal = {
        "proposal_id": "p_test",
        "symbol": "JD",
        "cov_override": "rsi",
        "covariate_family": "momentum",
        "predicted_direction": "RSI(6)>80 超买 -> short",
    }
    state = _build_state(proposal, "JD", None, None)
    assert state["proposal_summary"]["proposal_id"] == "p_test"
    assert state["proposal_summary"]["symbol"] == "JD"
    assert state["proposal_summary"]["cov_override"] == "rsi"
    assert state["proposal_summary"]["covariate_family"] == "momentum"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_build_state_no_cjk.py -v`
Expected: FAIL (predicted_direction 含中文 / 无 language 字段 / 无空壳回退)

- [ ] **Step 3: Write minimal implementation**

```python
# cascade/typesafe_prescreen.py _build_state() 函数修改（~L255-282）
def _build_state(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None,
    covariate_menu: dict[str, Any] | None,
) -> dict[str, Any]:
    """构建 Laya System-1 的 State（英文，避免中文导致超时）。"""
    symbol_profile = _load_symbol_profile(symbol)

    # v3: 过滤 predicted_direction 中文 + 空壳回退
    raw_pd = proposal.get("predicted_direction", "")
    stripped_pd = _strip_chinese(raw_pd)
    if _is_shell_pd(stripped_pd):
        # 空壳回退：置为空串，Laya 收到空 predicted_direction
        final_pd = ""
    else:
        final_pd = stripped_pd

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
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_build_state_no_cjk.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/abug/timesfm
git add cascade/typesafe_prescreen.py tests/test_build_state_no_cjk.py
git commit -m "feat(cascade): _build_state() strips Chinese PD + adds language field

- predicted_direction filtered through _strip_chinese()
- Empty-shell PD (core len < 12) falls back to empty string
- Short-formula shell (e.g. 'RSI(6)>80 超买 -> short') detected via core='RSI680short' len=11
- state includes language='en' (best-effort, not validated against Laya)
- Integration tests verify no East Asian wide chars in state output

Ref: spec 2026-10-18-laya-chinese-leak-fix-spec.md §3.1"
```

---

### Task 4: _call_laya() language 字段 + 超时统一

**Files:**
- Modify: `cascade/typesafe_prescreen.py:289-350` (`_call_laya` 函数签名 + payload)
- Modify: `cascade/typesafe_prescreen.py:375` (`_prescreen_impl` 调用点)
- Modify: `tests/test_build_state_no_cjk.py` (追加测试)

**Interfaces:**
- Consumes: state dict (含 language 字段)
- Produces: HTTP POST payload with `language: "en"` at top level; timeout signature 30→60

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_state_no_cjk.py 追加
from unittest.mock import patch, MagicMock
import inspect

def test_call_laya_payload_includes_language():
    """_call_laya payload 顶层包含 language: en"""
    from cascade.typesafe_prescreen import _call_laya
    state = {
        "language": "en",
        "symbol": "p",
        "proposal_summary": {"predicted_direction": "oi_up -> long"},
    }
    with patch('cascade.typesafe_prescreen.requests.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"answers": {}})
        _call_laya(state)
        # 提取 payload（可能在 json= kwarg 或 positional arg）
        call_kwargs = mock_post.call_args.kwargs if mock_post.call_args.kwargs else {}
        call_args = mock_post.call_args.args if mock_post.call_args.args else ()
        payload = call_kwargs.get('json') or (call_args[1] if len(call_args) > 1 else None)
        assert payload is not None, "Could not find payload in mock call"
        assert payload.get("language") == "en"

def test_call_laya_timeout_signature():
    """_call_laya 签名默认超时 60s（从 30s 统一）"""
    from cascade.typesafe_prescreen import _call_laya
    sig = inspect.signature(_call_laya)
    timeout_param = sig.parameters.get('timeout')
    assert timeout_param is not None
    assert timeout_param.default == 60.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_build_state_no_cjk.py::test_call_laya_payload_includes_language tests/test_build_state_no_cjk.py::test_call_laya_timeout_signature -v`
Expected: FAIL (payload 无 language 字段 / timeout 默认 30)

- [ ] **Step 3: Write minimal implementation**

```python
# cascade/typesafe_prescreen.py _call_laya() 修改
# ⚠️ 实施前 Read 现函数全文（~L289-350），保留现有 questions 结构，仅改：
#   1. 签名默认值 30→60
#   2. payload 顶层添加 language 字段

# 1. 签名默认值 30→60
def _call_laya(state: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    """调用 Laya System-1 HTTP API。"""

    # 2. payload 顶层添加 language（保留现有 questions 结构不变）
    payload = {
        "model": "laya-rl-agent",
        "language": "en",    # best-effort: 未证实服务端识别，不阻塞成功率验收
        "state": state,
        "questions": {
            # ... 保持原有 questions 结构不变
        },
    }
    # ... 其余 HTTP POST 逻辑不变
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_build_state_no_cjk.py -v`
Expected: PASS (7 tests = 5 from Task 3 + 2 new)

- [ ] **Step 5: Commit**

```bash
cd /home/abug/timesfm
git add cascade/typesafe_prescreen.py tests/test_build_state_no_cjk.py
git commit -m "feat(cascade): _call_laya() adds language field + unifies timeout to 60s

- Payload top-level includes language='en' (best-effort)
- Signature timeout default 30s → 60s, aligns with _prescreen_impl call site
- Unit tests verify payload structure and timeout signature

Ref: spec 2026-10-18-laya-chinese-leak-fix-spec.md §3.1"
```

---

### Task 5: check_pd_chinese.py 门禁脚本

**Files:**
- Create: `scripts/check_pd_chinese.py`

**Interfaces:**
- Consumes: `task_FM/experiments/run_*/results/**/proposals/*.json`（动态计数，不硬编码 7194）
- Produces: stdout 输出扫描总数 + 违规数；exit 0 = pass, exit 1 = fail

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""一次性门禁脚本：扫描所有 proposal，验证 _build_state() 输出无东亚宽字符。

Usage:
    cd /home/abug/timesfm && python scripts/check_pd_chinese.py

Exit codes:
    0: 所有 state 无东亚宽字符
    1: 存在含东亚宽字符的 state
"""
import json
import re
import sys
from pathlib import Path

from cascade.typesafe_prescreen import _build_state

# 东亚宽字符正则（与 SPEC 验收字符类一致）：CJK 汉字 + CJK 标点 + 全角标点
_EAST_ASIAN_WIDE = re.compile(
    r'[一-鿿'        # CJK 统一表意文字
    r'　-〿'          # CJK 符号和标点
    r'！-／'          # 全角 ASCII 标点区 1
    r'：-＠'          # 全角 ASCII 标点区 2
    r'［-＿'          # 全角 ASCII 标点区 3
    r'｛-･'          # 全角 ASCII 标点区 4
    r']'
)

def check_proposals():
    proposals_dir = Path("task_FM/experiments")
    if not proposals_dir.exists():
        print(f"ERROR: {proposals_dir} does not exist", file=sys.stderr)
        return False

    proposal_files = list(proposals_dir.glob("run_*/results/**/proposals/*.json"))
    if not proposal_files:
        print("WARNING: no proposal files found", file=sys.stderr)
        return True

    total = 0
    violations = 0

    for pf in proposal_files:
        try:
            with open(pf) as f:
                proposal = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"SKIP (unreadable): {pf}: {e}")
            continue

        state = _build_state(proposal, proposal.get("symbol", ""), None, None)
        pd = state["proposal_summary"]["predicted_direction"]

        total += 1
        if _EAST_ASIAN_WIDE.search(pd):
            violations += 1
            print(f"VIOLATION: {pf} → predicted_direction={pd!r}")

    print(f"\nScanned {total} proposals, {violations} violations")
    return violations == 0

if __name__ == "__main__":
    sys.exit(0 if check_proposals() else 1)
```

- [ ] **Step 2: Run script to verify it works**

Run: `cd /home/abug/timesfm && python scripts/check_pd_chinese.py`
Expected: Scan all proposals (dynamic count, ~8503), 0 violations

- [ ] **Step 3: Commit**

```bash
cd /home/abug/timesfm
git add scripts/check_pd_chinese.py
git commit -m "feat(scripts): add one-time gate script for PD East Asian wide char validation

- Scans all proposals under task_FM/experiments/ (dynamic count, not hardcoded)
- Verifies 0 states contain East Asian wide chars (CJK + fullwidth punct)
- Handles unreadable files gracefully (skip + log)
- Exit 0 = pass, exit 1 = fail

Ref: spec 2026-10-18-laya-chinese-leak-fix-spec.md §4.1"
```

---

### Task 6: backfill 去重 pre-check（Phase 2）

**Files:**
- Modify: `scripts/backfill_prescreen.py` (`process_proposal` 函数，~L298-360)
- Create: `tests/test_backfill_dedup.py`

**Interfaces:**
- Consumes: 真实 `process_proposal(proposal_path, stats, verdict_history, covariate_menu, queue_path, dead, existing)` 签名；`generate_variant_id(symbol, cov_override)`；`extract_proposal_fields(proposal_path)`；`prescreen_and_save(...)`
- Produces: 在 `prescreen_and_save` 调用前检查 `existing`，命中则 `stats.inc("skipped")` 并 return `"skipped"`

> **现网代码关键点**（实施前必读）：
> - `process_proposal` 签名：`(proposal_path, stats, verdict_history, covariate_menu, queue_path, dead, existing)`（~L298）
> - 内部先调 `extract_proposal_fields(proposal_path)` 获取 `symbol`, `cov_override`, `proposal_data`
> - 然后调 `prescreen_and_save(proposal=..., proposal_path=..., symbol=..., verdict_history=..., covariate_menu=...)`
> - `generate_variant_id(symbol, cov_override)` 在 ~L202，依赖 `cascade.cov_family` + `cascade.experiment_fingerprint` + `sup_evidence`
> - `Stats` 类 (~L257) 有 `.skipped` 字段和 `.inc(field)` 方法
> - **去重点**：在 `extract_proposal_fields` 成功后、`prescreen_and_save` 调用前，用 `generate_variant_id(symbol, cov_override)` 查 `existing`
> - `existing` 是 `main()` 中构建的 REGISTRY∪INPROGRESS∪QUEUE 集合（~L497-510）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backfill_dedup.py
from unittest.mock import patch, MagicMock
import sys
import types

def test_backfill_skips_existing_variant():
    """existing 中已有 variant → 跳过 prescreen_and_save 调用"""
    # 构造真实签名所需的全部参数
    stats = MagicMock()
    stats.skipped = 0

    # mock extract_proposal_fields 返回有效字段
    mock_fields = {
        "symbol": "p",
        "cov_override": "oi",
        "proposal_data": {"proposal_id": "p_test", "symbol": "p", "cov_override": "oi"},
    }

    # mock generate_variant_id 返回已知 vid
    mock_vid = "v_p_oi_abc123def456"

    # existing 包含该 vid
    existing = {mock_vid}

    with patch('scripts.backfill_prescreen.extract_proposal_fields', return_value=mock_fields), \
         patch('scripts.backfill_prescreen.generate_variant_id', return_value=mock_vid), \
         patch('cascade.typesafe_prescreen.prescreen_and_save') as mock_prescreen:
        # 注意：prescreen_and_save 在 process_proposal 函数体内
        # `from cascade.typesafe_prescreen import prescreen_and_save`，
        # 所以 patch 源模块 cascade.typesafe_prescreen.prescreen_and_save

        from scripts.backfill_prescreen import process_proposal
        result = process_proposal(
            "task_FM/experiments/run_1/results/p/proposals/p_test.json",
            stats=stats,
            verdict_history=None,
            covariate_menu=None,
            queue_path="/dev/null",
            dead=set(),
            existing=existing,
        )

        assert result == "skipped"
        stats.inc.assert_called_with("skipped")
        mock_prescreen.assert_not_called()  # 未调用 Laya

def test_backfill_does_not_skip_new_variant():
    """existing 中无该 variant → 正常调 prescreen_and_save"""
    stats = MagicMock()
    stats.success = 0
    stats.skipped = 0

    mock_fields = {
        "symbol": "p",
        "cov_override": "oi",
        "proposal_data": {"proposal_id": "p_new", "symbol": "p", "cov_override": "oi"},
    }
    mock_vid = "v_p_oi_newvariant"
    existing = set()  # 空集 → 不跳过

    with patch('scripts.backfill_prescreen.extract_proposal_fields', return_value=mock_fields), \
         patch('scripts.backfill_prescreen.generate_variant_id', return_value=mock_vid), \
         patch('cascade.typesafe_prescreen.prescreen_and_save', return_value={"status": "degraded"}) as mock_prescreen:
        # 返回 "degraded" 而非 "success"，避免走入队分支（入队依赖 queue_path 写盘等副作用）

        from scripts.backfill_prescreen import process_proposal
        result = process_proposal(
            "task_FM/experiments/run_1/results/p/proposals/p_new.json",
            stats=stats,
            verdict_history=None,
            covariate_menu=None,
            queue_path="/dev/null",
            dead=set(),
            existing=existing,
        )

        # 核心断言：prescreen_and_save 被调用（去重未跳过）
        mock_prescreen.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_backfill_dedup.py -v`
Expected: FAIL (无去重逻辑，prescreen_and_save 被调用)

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/backfill_prescreen.py process_proposal() 中，在 extract_proposal_fields 成功后、prescreen_and_save 前添加

def process_proposal(proposal_path, stats, verdict_history, covariate_menu,
                     queue_path, dead, existing):
    """处理单个提案，返回 status_label。"""
    fields = extract_proposal_fields(proposal_path)
    if fields is None:
        stats.inc("failed")
        return "error"

    symbol = fields["symbol"]
    cov_override = fields["cov_override"]
    proposal_data = fields["proposal_data"]

    # ── Phase 2: 去重 pre-check ──────────────────────────
    variant_id = generate_variant_id(symbol, cov_override)
    if variant_id is not None and variant_id in existing:
        stats.inc("skipped")
        return "skipped"
    # ─────────────────────────────────────────────────────

    try:
        from cascade.typesafe_prescreen import prescreen_and_save

        result = prescreen_and_save(
            proposal=proposal_data,
            proposal_path=str(proposal_path),
            symbol=symbol,
            verdict_history=verdict_history,
            covariate_menu=covariate_menu,
        )
        # ... 其余逻辑不变
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && python -m pytest tests/test_backfill_dedup.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/abug/timesfm
git add scripts/backfill_prescreen.py tests/test_backfill_dedup.py
git commit -m "feat(backfill): pre-check skips existing variants in REGISTRY/QUEUE/INPROGRESS

- After extract_proposal_fields, before prescreen_and_save
- Uses generate_variant_id(symbol, cov_override) to check existing set
- On hit: stats.inc('skipped'), return 'skipped', no Laya call
- Does not expand PrescreenStatus enum (Frozen lifecycle spec §71/§422)
- Tests use real process_proposal signature with all 7 params

Ref: spec 2026-10-18-laya-chinese-leak-fix-spec.md §3.3"
```

---

### Task 7: prompt English only 约束（Phase 3）

**Files:**
- Modify: `task_FM/prompt_base.jinja2:65-66`

**Interfaces:**
- Consumes: peer LLM prompt template
- Produces: predicted_direction 字段约束 "English only. No Chinese annotations."

- [ ] **Step 1: Read current prompt**

Run: `cd /home/abug/timesfm && sed -n '60,70p' task_FM/prompt_base.jinja2`
Expected: 看到当前 L65-66 约束

- [ ] **Step 2: Modify the prompt**

```jinja2
{# task_FM/prompt_base.jinja2 L65-66 修改 #}
{# 原：- predicted_direction / kill_condition / promote_condition must be falsifiable before seeing results #}
- predicted_direction: English only. No Chinese annotations. Format: "condition -> action"
  Example: "oi_up_with_price -> long; oi_down_with_price_breakdown -> short"
- kill_condition / promote_condition must be falsifiable before seeing results
```

- [ ] **Step 3: 验证 prompt 语法**

Run: `cd /home/abug/timesfm && python -c "from jinja2 import Environment; Environment().get_template(open('task_FM/prompt_base.jinja2').read())"`
Expected: 无 Jinja2 语法错误

- [ ] **Step 4: Commit**

```bash
cd /home/abug/timesfm
git add task_FM/prompt_base.jinja2
git commit -m "feat(prompt): enforce English-only predicted_direction in peer prompt

- Adds constraint: 'English only. No Chinese annotations'
- Includes example format to guide peer LLM
- Long-term fix: prevents new Chinese PD from entering system
- Existing 1796 Chinese PD proposals still handled by downstream _strip_chinese()

Ref: spec 2026-10-18-laya-chinese-leak-fix-spec.md §3.2"
```

---

## Self-Review Checklist

✅ **Spec coverage:** 所有 §3（修复方案）和 §4（验证标准）均有对应 task
- §3.1 下游止血 → Task 1-5
- §3.2 源头约束 → Task 7
- §3.3 去重 → Task 6
- §3.4 超时统一 → Task 4
- §4.1 短期验证 → Task 1-5 测试 + Task 5 门禁
- §4.2 长期验证 → Task 7 (Jinja 语法验证；10 seed 验证为手动 follow-up)
- §4.3 去重验证 → Task 6 测试

✅ **Placeholder scan:** 无 TBD/TODO/"implement later"/"假设已有"
- Task 6 使用真实 `process_proposal` 签名、真实 `generate_variant_id`、真实 `prescreen_and_save`
- Task 7 删除不存在的 `run_peer_seeds.py` 引用，改为 Jinja 语法验证

✅ **Type consistency:**
- `_strip_chinese(s: str) -> str` — Task 1 定义，Task 2/3/5 一致引用
- `_is_shell_pd(stripped: str) -> bool` — Task 2 定义，Task 3 引用
- `_PD_MIN_LEN = 12` — Task 2 定义，Review Focus 一致
- `process_proposal(proposal_path, stats, verdict_history, covariate_menu, queue_path, dead, existing)` — Task 6 使用真实签名
- `generate_variant_id(symbol, cov_override)` — Task 6 使用真实函数

✅ **Review Focus 覆盖:**
1. 空壳误判（longshort len=9）→ Task 2 `test_is_shell_pd_typical_shell`
2. 全角标点残留 → Task 1 `test_strip_chinese_fullwidth_punct`
3. 全量扫描动态计数 → Task 5 `len(proposal_files)` + print
4. 去重不丢新提案 → Task 6 `test_backfill_does_not_skip_new_variant`
5. 短公式空壳 → Task 2 `test_is_shell_pd_short_formula` + Task 3 `test_build_state_short_formula_shell`

---

## Execution Handoff

Plan complete and saved to `/home/abug/timesfm/docs/superpowers/plans/2026-10-18-laya-chinese-leak-fix-implementation.md`.

Please review the plan. Does it capture what you want? If so, which execution approach should we use?

- **Subagent-driven** - A fresh subagent implements each task and a fresh reviewer checks it before the next one starts, then a whole-branch review at the end. Most thorough; costs a fresh context per task and per review.
- **Native** - I implement every task myself in this session, then one fresh reviewer on the most capable model checks the whole branch. Cheapest and fastest; no independent review until the end.

**For this plan I recommend Native**, because: (1) Task 1-5 紧耦合（每个依赖前一个的函数签名），(2) Task 6 需要精确匹配现网 7 参签名，需要 Read-then-Edit，(3) 代码变更精准（正则 + 2 函数 + 1 集成 + 1 dedup），(4) WSL 环境可直接跑测试。
