# Laya Prescreen Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Laya 预筛客户端在高负载（503 主导 / 队列拥堵）下智能降级，把无效等待降到 0，并在空闲时保持 >90% 成功率。

**Architecture:** 在 `cascade/laya_prescreen.py` 内做四层改造：① 新增 `LayaUnavailableError` 让 503 绕过 `_call_laya` 的 `ConnectionError` 包装直达调用方；② 用模块级 `CircuitBreaker` 类替换现有的 `_consecutive_timeouts + _circuit_until` 二元组，三态（CLOSED→OPEN→HALF_OPEN）加探针锁；③ timeout 分档 10s/5s；④ P1 阶段追加 state 英文化与队列感知退避。所有变更只动 `cascade/laya_prescreen.py` 与 `config/sector_map.py` 两个文件，不引入新依赖，不改服务端。

**Tech Stack:** Python 3.11 + stdlib `requests`（已装）+ `pytest`。无新依赖。

**Spec:** `docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md`（v2 + audit ~88%，2026-10-23 修订重审）

## Global Constraints

- **不修改服务端**：不碰 Laya 的 `serve.py`、不增加 worker、不改队列深度。
- **不硬阻断慢环**：预筛仍是软建议模式（`status="degraded"`），失败时静默跳过。
- **不引入新依赖**：只用现有 `requests`，不引 `aiohttp` / `httpx`。
- **Laya 不可学习**：优化仅作用于客户端 failure 分类 / 熔断 / timeout / state 构建；任何"训练 / 微调 / 进化"叙事不得出现。
- **保留 `SECTOR_NAMES`（中文 value）共享 display 表**：新增 `SECTOR_NAMES_EN` 仅用于 Laya state，不动其他模块依赖的中文映射。
- **线程安全**：`CircuitBreaker` 与退避窗口须能扛多线程（`threading.Lock` 保护）。
- **可回滚**：`LAYA_CIRCUIT_BREAKER_ENABLED` / `LAYA_CIRCUIT_BREAKER_THRESHOLD` / `LAYA_CIRCUIT_BREAKER_DURATION` 三个环境变量控制，默认开启。
- **测试基线**：当前 `tests/test_laya_prescreen.py` 全绿；新代码 TDD，老测试不得回归。

## Review Focus

以下 5 类失效模式 spec 暗示但单测未必覆盖，须显式钉在对应 task 的 step 里：

1. **503 经 `_call_laya` 被吞成 `ConnectionError` 后漏掉熔断** → Task 1 Step 1c 测试 `_call_laya` 抛 `LayaUnavailableError`，Step 3b 测试 `_prescreen_impl` 捕到后调 `_record_failure`。
2. **HALF_OPEN 探针期间并发请求惊群** → Task 2 Step 2d 多线程场景测试 `_half_open_probe_in_flight` 锁。
3. **`_extract_relevant_history` 含中文模板（「已过门协变量」「同板块」「族:」）触发 checkpoint 切换** → Task 4 Step 2 用正则 `[一-鿿]` 扫所有输出。
4. **503 误试第二端点（两 endpoint 共享同一队列，重试只会拖长失败路径）** → Task 3 Step 2b 断言 503 时只有一次 HTTP 调用。
5. **`state["sector"]` 默认值 `"未知"` 是中文** → Task 4 Step 1b 断言默认 sector 为 `"unknown"`。

---

## Task 1: P0-1 — 统一 failure 分类 + 503 进熔断

**Files:**
- Modify: `cascade/laya_prescreen.py:179-216`（熔断模块区，新增 `LayaUnavailableError`）
- Modify: `cascade/laya_prescreen.py:287-372`（`_call_laya` — 503 re-raise）
- Modify: `cascade/laya_prescreen.py:374-426`（`_prescreen_impl` — 统一捕异常）
- Create: `tests/test_laya_failure_classification.py`

**Interfaces:**
- Consumes: `_call_laya(state, api_key, timeout)`（现有签名不变）；`_prescreen_impl(proposal, symbol, verdict_history, covariate_menu)`（签名不变）
- Produces: 
  - `class LayaUnavailableError(Exception)` — 503 / 队列满专用
  - `class LayaTimeoutError(TimeoutError)` — 已存在，保留
  - `_record_failure(reason: str)` — 新函数，统一 failure 入口，调 `_circuit_breaker.record_failure()`
  - `_record_success()` — 已存在，保留（调 `_circuit_breaker.record_success()`）

- [ ] **Step 1a: 写失败测试 — `LayaUnavailableError` 异常类**

文件：`tests/test_laya_failure_classification.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from cascade.laya_prescreen import (
    LayaUnavailableError,
    _call_laya,
    _prescreen_impl,
    _fallback_result,
)

class TestLayaUnavailableError:
    def test_503_raises_laya_unavailable(self):
        """503 响应必须被 re-raise 为 LayaUnavailableError，不能被 ConnectionError 吞掉。"""
        import requests
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        
        with patch("cascade.laya_prescreen.requests.post") as mock_post:
            mock_post.side_effect = requests.HTTPError(response=mock_resp)
            with pytest.raises(LayaUnavailableError):
                _call_laya({"symbol": "rb"}, api_key="x", timeout=5.0)
```

- [ ] **Step 1b: 运行测试确认失败**

```bash
cd /home/abug/timesfm
pytest tests/test_laya_failure_classification.py::TestLayaUnavailableError::test_503_raises_laya_unavailable -v
```

预期：FAIL — `ImportError: cannot import name 'LayaUnavailableError'`

- [ ] **Step 1c: 在 `cascade/laya_prescreen.py` 顶部（line ~27，紧跟 `LayaTimeoutError`）定义 `LayaUnavailableError`**

```python
class LayaUnavailableError(Exception):
    """Laya 服务不可用（503 / 队列满）。与 LayaTimeoutError 区分：前者触发熔断，后者仅记录。"""
    pass
```

- [ ] **Step 1d: 改 `_call_laya`（line 287）— 503 re-raise，不试第二端点；真实 timeout 升为 `LayaTimeoutError`**

把现有的 `except Exception as e:` 单 catch 块拆成三分支：

```python
for attempt, endpoint in enumerate(endpoints):
    url = f"{endpoint}/v1/systemone"
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        # ... 原有 MockResult 构造
        return MockResult(result_data)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 503:
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

# 双端点皆超时 → 升为 LayaTimeoutError（不是 ConnectionError）
if isinstance(last_error, requests.Timeout):
    raise LayaTimeoutError(f"All Laya endpoints timed out: {last_error}") from last_error
# 其他混合失败 → ConnectionError
raise ConnectionError(f"All Laya endpoints unreachable: {last_error}")
```

注：
- **真实 timeout 升为 `LayaTimeoutError`**：避免 `_prescreen_impl` 把线上 timeout 误记为 `connection_error`。
- **503 立即 re-raise**：不试第二端点（共享队列）。

- [ ] **Step 1e: 写失败测试 — `_prescreen_impl` 对 503 调 `_record_failure`**

追加到 `tests/test_laya_failure_classification.py`：

```python
class TestPrescreenFailureClassification:
    def test_503_triggers_record_failure(self):
        """503 必须走 _record_failure，不能漏进泛 Exception 分支。"""
        from cascade import laya_prescreen as lp
        
        recorded = []
        orig_record_failure = getattr(lp, "_record_failure", None)
        lp._record_failure = lambda reason: recorded.append(reason)
        
        try:
            with patch.object(lp, "_call_laya", side_effect=lp.LayaUnavailableError("503 from x")):
                with patch.object(lp, "_get_laya_api_key", return_value="x"):
                    with patch.object(lp, "_check_circuit", return_value=False):
                        with patch.object(lp, "_build_state", return_value={"symbol": "rb"}):
                            result = lp._prescreen_impl({"variant_id": "v1"}, "rb", None, None)
            assert result["status"] in ("degraded", "error")
            assert "503_unavailable" in recorded
        finally:
            if orig_record_failure is not None:
                lp._record_failure = orig_record_failure
            else:
                delattr(lp, "_record_failure")

    def test_timeout_triggers_record_failure(self):
        """超时也必须走 _record_failure（统一分类）。"""
        from cascade import laya_prescreen as lp
        
        recorded = []
        lp._record_failure = lambda reason: recorded.append(reason)
        
        try:
            with patch.object(lp, "_call_laya", side_effect=lp.LayaTimeoutError("t")):
                with patch.object(lp, "_get_laya_api_key", return_value="x"):
                    with patch.object(lp, "_check_circuit", return_value=False):
                        with patch.object(lp, "_build_state", return_value={"symbol": "rb"}):
                            lp._prescreen_impl({"variant_id": "v1"}, "rb", None, None)
            assert any("timeout" in r for r in recorded)
        finally:
            delattr(lp, "_record_failure")
```

- [ ] **Step 1f: 运行测试确认失败**

```bash
pytest tests/test_laya_failure_classification.py -v
```

预期：FAIL — `_record_failure` 不存在 / `_prescreen_impl` 503 分支不调用

- [ ] **Step 1g: 在 `cascade/laya_prescreen.py` 加 `_record_failure` 函数（line ~205，紧跟 `_record_success`）**

```python
def _record_failure(reason: str) -> None:
    """统一 failure 入口。所有 503 / timeout / ConnectionError 必须走这里。"""
    global _consecutive_timeouts, _circuit_until
    # Task 2 会把这里换成 _circuit_breaker.record_failure()
    _consecutive_timeouts += 1
    if _consecutive_timeouts >= 3:
        _circuit_until = time.time() + 600
    logger.warning("Laya prescreen failure: %s", reason)
```

- [ ] **Step 1h: 改 `_prescreen_impl`（line 374）— 四分支统一捕获（保留裸 `TimeoutError` 防回归）**

把现有的 `except (TimeoutError, LayaTimeoutError)` / `except AuthenticationError` / `except Exception` 替换为：

```python
try:
    result = _call_laya(state, api_key, timeout=_TIMEOUT_PRIMARY)
except LayaUnavailableError as e:
    _record_failure("503_unavailable")
    logger.warning("Laya 503: %s", e)
    return _fallback_result(proposal, symbol, status="degraded", note=f"Laya 503 不可用: {e}")
except (TimeoutError, LayaTimeoutError, requests.Timeout) as e:
    # 保留裸 TimeoutError 防回归（现有测试 mock 抛 TimeoutError）
    _record_failure("timeout")
    logger.warning("Laya timeout: %s", e)
    return _fallback_result(proposal, symbol, status="degraded", note=f"Laya API 超时: {e}")
except ConnectionError as e:
    _record_failure("connection_error")
    logger.warning("Laya connection error: %s", e)
    return _fallback_result(proposal, symbol, status="degraded", note=f"Laya 连接失败: {e}")
except AuthenticationError as e:
    logger.error("Laya auth error: %s", e)
    return _fallback_result(proposal, symbol, status="error", note=f"Laya API 鉴权失败: {e}")
except Exception as e:
    _record_failure("unknown")
    logger.exception("Laya unknown failure: %s", e)
    return _fallback_result(proposal, symbol, status="error", note=f"Laya API 返回异常: {e}")
```

注：
- **保留裸 `TimeoutError`**：现有测试 `test_api_timeout_returns_degraded` / `test_timeout_triggers_circuit_not_error` mock 抛裸 `TimeoutError`，丢掉会回归炸。
- **`note=` 保留中文前缀**：现有测试断言 `"超时" in note`、`"鉴权" in note`。用 `f"Laya API 超时: {e}"` 保留稳定前缀，附 `str(e)` 供日志追溯。

- [ ] **Step 1i: 运行测试确认通过**

```bash
pytest tests/test_laya_failure_classification.py -v
```

预期：PASS（至少 2 个新测试通过）

- [ ] **Step 1j: 运行回归测试确认无破坏**

```bash
pytest tests/test_laya_prescreen.py tests/test_prescreen_score.py tests/test_slow_loop_prescreen.py -v
```

预期：所有现有测试仍通过

- [ ] **Step 1k: 提交**

```bash
cd /home/abug/timesfm
git add cascade/laya_prescreen.py tests/test_laya_failure_classification.py
git commit -m "feat(laya): unified failure classification + 503 triggers circuit breaker

- Add LayaUnavailableError (distinct from LayaTimeoutError)
- _call_laya re-raises 503 immediately, does not retry second endpoint
- _prescreen_impl catches 503/timeout/ConnectionError/auth/unknown separately
- All failure paths route through _record_failure(reason)
- 503 no longer swallowed by generic ConnectionError wrapping

Spec: docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md §3.1"
```

---

## Task 2: P0-2 — 三态熔断器（CLOSED→OPEN→HALF_OPEN + 探针锁）

**Files:**
- Modify: `cascade/laya_prescreen.py:179-216`（替换 `_consecutive_timeouts`/`_circuit_until`/`_check_circuit`/`_record_timeout`/`_record_success`/`_reset_circuit_state` 为 `CircuitBreaker` 类实例）
- Modify: `cascade/laya_prescreen.py:205`（`_record_failure` 内部从计数器调用改为 `_circuit_breaker.record_failure()`）
- Create: `tests/test_circuit_breaker.py`

**Interfaces:**
- Consumes: `_record_failure(reason)`（Task 1 已加）
- Produces:
  - `class CircuitBreaker` — 三态状态机，线程安全
  - `CircuitBreaker.should_skip() -> bool` — 调用前判断
  - `CircuitBreaker.record_failure()` / `record_success()` — 状态迁移
  - 模块实例：`_circuit_breaker = CircuitBreaker(threshold, duration)`

- [ ] **Step 2a: 写失败测试 — 基础状态迁移**

文件：`tests/test_circuit_breaker.py`

```python
import time
import threading
from cascade.laya_prescreen import CircuitBreaker

class TestCircuitBreakerBasic:
    def test_initial_state_closed(self):
        cb = CircuitBreaker(threshold=3, duration=300)
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.should_skip() is False

    def test_three_failures_open(self):
        cb = CircuitBreaker(threshold=3, duration=300)
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.should_skip() is True

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker(threshold=3, duration=300)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0

    def test_open_after_duration_transitions_to_half_open(self):
        cb = CircuitBreaker(threshold=3, duration=0.1)  # 100ms 用于测试
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.15)
        # 第一次 should_skip 触发 → HALF_OPEN，且允许 1 个探针
        assert cb.should_skip() is False
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_probe_success_closes(self):
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.should_skip()  # transition to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_probe_failure_reopens(self):
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.should_skip()  # transition to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
```

- [ ] **Step 2b: 运行测试确认失败**

```bash
pytest tests/test_circuit_breaker.py -v
```

预期：FAIL — `ImportError: cannot import name 'CircuitBreaker'`

- [ ] **Step 2c: 写失败测试 — HALF_OPEN 探针锁（防惊群）**

追加到 `tests/test_circuit_breaker.py`：

```python
class TestCircuitBreakerConcurrency:
    def test_half_open_only_one_probe_allowed(self):
        """HALF_OPEN 期间，第一次 should_skip 返回 False（放行探针），后续都返回 True。"""
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        
        # 第一个调用者拿到探针权
        assert cb.should_skip() is False
        # 后续调用者全部跳过
        assert cb.should_skip() is True
        assert cb.should_skip() is True
        assert cb.should_skip() is True

    def test_thread_safety(self):
        """多线程下不崩溃，且探针锁仍然有效。"""
        cb = CircuitBreaker(threshold=3, duration=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        
        results = []
        def probe():
            results.append(cb.should_skip())
        
        threads = [threading.Thread(target=probe) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 必须恰好有 1 个 False（探针），其余 True
        assert results.count(False) == 1
        assert results.count(True) == 9
```

- [ ] **Step 2d: 运行测试确认失败**

```bash
pytest tests/test_circuit_breaker.py::TestCircuitBreakerConcurrency -v
```

预期：FAIL — `CircuitBreaker` 不存在

- [ ] **Step 2e: 在 `cascade/laya_prescreen.py` line ~179 实现 `CircuitBreaker` 类并替换模块级变量**

```python
import threading

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

# 兼容旧调用：_check_circuit / _record_timeout / _record_success 委托给 _circuit_breaker
def _check_circuit() -> bool:
    if not _cb_enabled:
        return False
    return _circuit_breaker.should_skip()

def _record_timeout() -> None:
    """兼容旧名；新代码统一走 _record_failure。"""
    _circuit_breaker.record_failure()

def _record_success() -> None:
    _circuit_breaker.record_success()

def _reset_circuit_state() -> None:
    """仅供单元测试重置。"""
    with _circuit_breaker._lock:
        _circuit_breaker.failure_count = 0
        _circuit_breaker.state = CircuitBreaker.CLOSED
        _circuit_breaker._half_open_probe_in_flight = False
        _circuit_breaker.last_failure_time = None
```

同时删掉旧的 `_consecutive_timeouts` / `_circuit_until` / `_laya_rr_idx` 模块级变量（`_laya_rr_idx` 保留，跟熔断无关）。

- [ ] **Step 2f: 把 Task 1 的 `_record_failure` 改为委托给 `_circuit_breaker`**

```python
def _record_failure(reason: str) -> None:
    """统一 failure 入口。"""
    _circuit_breaker.record_failure()
    logger.warning("Laya prescreen failure: %s", reason)
```

- [ ] **Step 2g: 运行测试确认通过**

```bash
pytest tests/test_circuit_breaker.py tests/test_laya_failure_classification.py -v
```

预期：全部 PASS

- [ ] **Step 2h: 运行全量 prescreen 测试确认无回归**

```bash
pytest tests/test_laya_prescreen.py tests/test_prescreen_score.py tests/test_slow_loop_prescreen.py tests/test_track_prescreen_quality.py -v
```

预期：全绿

- [ ] **Step 2j: 改写旧测 `test_half_open_resets_on_expire`（语义变化）**

旧测：到期后计数清零、全程放行。新语义：HALF_OPEN + 单探针。需改写断言：

```python
# 旧（test_laya_prescreen.py）：
# def test_half_open_resets_on_expire():
#     _record_timeout(); _record_timeout(); _record_timeout()
#     time.sleep(0.1)
#     assert _check_circuit() is False  # 到期后放行
#     assert _consecutive_timeouts == 0  # 计数清零

# 新（语义变化）：
def test_half_open_resets_on_expire():
    """到期后进入 HALF_OPEN，允许 1 个探针；后续仍跳过直到探针成功。"""
    _circuit_breaker.record_failure()
    _circuit_breaker.record_failure()
    _circuit_breaker.record_failure()
    time.sleep(0.1)  # duration=0.1 for test
    assert _circuit_breaker.should_skip() is False  # 第一个放行（探针）
    assert _circuit_breaker.should_skip() is True  # 后续跳过
    _circuit_breaker.record_success()  # 探针成功 → CLOSED
    assert _circuit_breaker.state == CircuitBreaker.CLOSED
    assert _circuit_breaker.should_skip() is False  # 全放行
```

注：旧测在 `tests/test_laya_prescreen.py` 中；实施时需改写以匹配新三态语义（P1-9 补丁）。

- [ ] **Step 2k: 提交**

```bash
git add cascade/laya_prescreen.py tests/test_circuit_breaker.py tests/test_laya_prescreen.py
git commit -m "feat(laya): three-state circuit breaker with probe lock

- CircuitBreaker class: CLOSED → OPEN → HALF_OPEN
- HALF_OPEN allows exactly 1 probe; concurrent requests skip (no thundering herd)
- Thread-safe via threading.Lock
- Configurable via env: LAYA_CIRCUIT_BREAKER_ENABLED/THRESHOLD/DURATION (bool parsed explicitly)
- _record_failure unified entry; _check_circuit/_record_timeout delegate
- Default: threshold=3, duration=300s
- Rewrite old test_half_open_resets_on_expire to match new three-state semantics

Spec: docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md §3.2"
```

---

## Task 3: P0-3 — timeout 上调（10s + 5s fallback）+ 503 不重试

**Files:**
- Modify: `cascade/laya_prescreen.py:287-372`（`_call_laya` — 分档 timeout）
- Modify: `cascade/laya_prescreen.py:374-426`（`_prescreen_impl` — timeout 5.0 → 10.0）
- Create: `tests/test_laya_timeout_tiers.py`

**Interfaces:**
- Consumes: `LayaUnavailableError`（Task 1）；`_circuit_breaker`（Task 2）
- Produces: `_call_laya` 内部 timeout 分档逻辑（对外签名不变）

- [ ] **Step 3a: 写失败测试 — 主端点 10s，副端点 5s**

文件：`tests/test_laya_timeout_tiers.py`

```python
import requests
from unittest.mock import patch, MagicMock
from cascade import laya_prescreen as lp

class TestTimeoutTiers:
    def test_primary_endpoint_uses_10s_timeout(self):
        """主端点 timeout 10s（覆盖 6.4s 推理 + 3s 网络缓冲）。"""
        captured_timeouts = []
        
        def fake_post(url, json, headers, timeout):
            captured_timeouts.append(timeout)
            raise requests.Timeout("simulated")
        
        with patch("cascade.laya_prescreen.requests.post", side_effect=fake_post):
            try:
                lp._call_laya({"symbol": "rb"}, "x")
            except (ConnectionError, lp.LayaTimeoutError):
                pass
        
        assert captured_timeouts[0] == 10.0, f"primary should be 10s, got {captured_timeouts[0]}"

    def test_fallback_endpoint_uses_5s_timeout(self):
        """副端点 timeout 5s（快速探测，不拖长失败路径）。"""
        captured_timeouts = []
        
        def fake_post(url, json, headers, timeout):
            captured_timeouts.append(timeout)
            raise requests.Timeout("simulated")
        
        with patch("cascade.laya_prescreen.requests.post", side_effect=fake_post):
            try:
                lp._call_laya({"symbol": "rb"}, "x")
            except (ConnectionError, lp.LayaTimeoutError):
                pass
        
        assert captured_timeouts[1] == 5.0, f"fallback should be 5s, got {captured_timeouts[1]}"

    def test_503_does_not_retry_second_endpoint(self):
        """503 = 队列满，两个 endpoint 共享同一 worker，重试只会拖长。"""
        call_count = 0
        
        def fake_post(url, json, headers, timeout):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 503
            raise requests.HTTPError(response=resp)
        
        with patch("cascade.laya_prescreen.requests.post", side_effect=fake_post):
            try:
                lp._call_laya({"symbol": "rb"}, "x")
            except lp.LayaUnavailableError:
                pass
        
        assert call_count == 1, f"503 should not retry, but got {call_count} calls"
```

注：
- `import requests` 在测试文件顶部（不在 `lp.requests`，因 `_call_laya` 内部 import）
- `from unittest.mock import MagicMock` 显式导入
- patch 目标 `cascade.laya_prescreen.requests.post`：需保证 `_call_laya` 内 `import requests` 是模块级或可 patch

- [ ] **Step 3b: 运行测试确认失败**

```bash
pytest tests/test_laya_timeout_tiers.py -v
```

预期：FAIL — `captured_timeouts[0]` 是 5.0 不是 10.0；503 重试了 2 次

- [ ] **Step 3c: 在 `cascade/laya_prescreen.py` 顶部加 timeout 常量**

```python
_TIMEOUT_PRIMARY = 10.0  # 覆盖 6.4s 推理 + 3s 网络缓冲
_TIMEOUT_FALLBACK = 5.0  # 副端点快速探测
```

- [ ] **Step 3d: 改 `_call_laya`（line ~287）— 分档 timeout + 503 不重试**

```python
def _call_laya(state: dict[str, Any], api_key: str, timeout: float = _TIMEOUT_PRIMARY) -> Any:
    """调用 Laya 服务。双地址 failover；503 不重试第二端点。"""
    import requests
    
    endpoints = _get_laya_endpoints()
    last_error: Exception | None = None
    
    # ... (payload 构造不变)
    
    for attempt, endpoint in enumerate(endpoints):
        url = f"{endpoint}/v1/systemone"
        t = _TIMEOUT_PRIMARY if attempt == 0 else _TIMEOUT_FALLBACK
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=t)
            response.raise_for_status()
            # ... (原有 MockResult 构造)
            return MockResult(result_data)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 503:
                raise LayaUnavailableError(f"503 from {endpoint}") from e
            last_error = e
            logger.warning("Laya endpoint %s HTTP error: %s", endpoint, e)
            continue
        except requests.Timeout as e:
            last_error = e
            logger.warning("Laya endpoint %s timeout: %s", endpoint, e)
            continue
        except Exception as e:
            last_error = e
            logger.warning("Laya endpoint %s failed: %s", endpoint, e)
            continue
    
    raise ConnectionError(f"All Laya endpoints unreachable: {last_error}")
```

- [ ] **Step 3e: 改 `_prescreen_impl`（line ~374）— 把 `timeout=5.0` 改为 `timeout=_TIMEOUT_PRIMARY`**

```python
try:
    result = _call_laya(state, api_key, timeout=_TIMEOUT_PRIMARY)
```

- [ ] **Step 3f: 运行测试确认通过**

```bash
pytest tests/test_laya_timeout_tiers.py tests/test_laya_failure_classification.py tests/test_circuit_breaker.py -v
```

预期：全部 PASS

- [ ] **Step 3g: 运行全量 prescreen 测试确认无回归**

```bash
pytest tests/test_laya_prescreen.py tests/test_prescreen_score.py tests/test_slow_loop_prescreen.py tests/test_track_prescreen_quality.py tests/test_laya_failure_classification.py tests/test_circuit_breaker.py tests/test_laya_timeout_tiers.py -v
```

预期：全绿

- [ ] **Step 3h: 提交**

```bash
git add cascade/laya_prescreen.py tests/test_laya_timeout_tiers.py
git commit -m "feat(laya): tiered timeout 10s primary + 5s fallback; 503 fast-fail

- _TIMEOUT_PRIMARY = 10.0 (covers 6.4s inference + 3s network buffer)
- _TIMEOUT_FALLBACK = 5.0 (second endpoint fast probe)
- 503 (LayaUnavailableError) does NOT retry second endpoint (shared queue)
- _prescreen_impl uses _TIMEOUT_PRIMARY instead of hardcoded 5.0

Spec: docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md §3.3"
```

---

## Task 4: P1-1 — state 关键路径英文化（sector + history）

**Files:**
- Modify: `config/sector_map.py`（末尾新增 `SECTOR_NAMES_EN`）
- Modify: `cascade/laya_prescreen.py:261-277`（`_build_state` — 用英文 sector key）
- Modify: `cascade/laya_prescreen.py:110-177`（`_extract_relevant_history` — 英文化模板）
- Create: `tests/test_laya_state_english_only.py`

**Interfaces:**
- Consumes: `SECTOR_NAMES_EN`（新增）；`sector_of(symbol)`（已存在）
- Produces: `_build_state` 返回 `sector` + `recent_verdicts_summary` 纯英文；`_extract_relevant_history` 返回纯英文字符串

**Scope 收窄（P1-5 补丁）**：
- **仅英文化 `sector` + `recent_verdicts_summary`（history）**
- **不动** `contract_details`（来自 `_load_symbol_profile`，可能含中文板块名；改需扩 scope 到 profile 构建）
- **不动** `covariate_menu`（可能整份中文 `covariate_menu.inc.md`；改需截断/英文摘要策略，超出本 plan 范围）
- **DoD 收窄为**：「`sector` + `history` 无中文字符」，不称「state 所有字段」

- [ ] **Step 4a: 写失败测试 — state 无中文**

文件：`tests/test_laya_state_english_only.py`

```python
import re
from cascade.laya_prescreen import _build_state, _extract_relevant_history

CJK_RE = re.compile(r"[一-鿿]")

class TestStateEnglishOnly:
    def test_build_state_sector_is_english(self):
        """state['sector'] 必须是英文，不能是 '黑色系' 等中文。"""
        state = _build_state(
            proposal={"variant_id": "v1"},
            symbol="rb",  # 黑色系
            verdict_history=None,
            covariate_menu=None,
        )
        assert state["sector"] in ("ferrous", "black_metals"), f"got {state['sector']!r}"
        assert not CJK_RE.search(state["sector"]), f"sector contains Chinese: {state['sector']!r}"

    def test_build_state_default_sector_unknown(self):
        """未知品种的 sector 默认 'unknown'，不是 '未知'。"""
        state = _build_state(
            proposal={"variant_id": "v1"},
            symbol="unknown_symbol_xyz",
            verdict_history=None,
            covariate_menu=None,
        )
        assert state["sector"] == "unknown", f"got {state['sector']!r}"

    def test_extract_relevant_history_no_chinese(self):
        """历史摘要不能含中文模板（「已过门协变量」「同板块」「族:」）。"""
        history = [
            {"symbol": "rb", "gate_pass": True, "cov_override": "x", "cov_family": "f1", "dir_acc": 0.5, "decided_at": "2026-01-01"},
            {"symbol": "i", "gate_pass": True, "cov_override": "y", "cov_family": "f2", "dir_acc": 0.3, "decided_at": "2026-01-02"},
        ]
        result = _extract_relevant_history(history, "rb")
        assert not CJK_RE.search(result), f"history contains Chinese:\n{result}"

    def test_extract_relevant_history_empty(self):
        """空历史返回英文默认文案。"""
        result = _extract_relevant_history(None, "rb")
        assert not CJK_RE.search(result), f"empty history has Chinese: {result!r}"
```

- [ ] **Step 4b: 运行测试确认失败**

```bash
pytest tests/test_laya_state_english_only.py -v
```

预期：FAIL — `state["sector"]` 是 "黑色系"；`_extract_relevant_history` 含中文

- [ ] **Step 4c: 在 `config/sector_map.py` 末尾新增 `SECTOR_NAMES_EN`**

```python
# English display names — Laya state injection only.
# DO NOT touch SECTOR_NAMES above (Chinese values used by display/other modules).
SECTOR_NAMES_EN = {
    "black_metals": "ferrous",
    "energy_chem": "energy_chemical",
    "agri": "agricultural",
    "non_ferrous": "non_ferrous",
    "other": "other",
}
```

- [ ] **Step 4d: 改 `_build_state`（line 261）— 用英文 sector**

```python
def _build_state(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None,
    covariate_menu: dict[str, Any] | None,
) -> dict[str, Any]:
    """构建 Laya judge 的 State（纯英文，避免触发 checkpoint 切换）。"""
    from config.sector_map import sector_of, SECTOR_NAMES_EN
    
    symbol_profile = _load_symbol_profile(symbol)
    sector_key = sector_of(symbol)  # 英文 key，如 "black_metals"
    sector_en = SECTOR_NAMES_EN.get(sector_key, "unknown")
    
    return {
        "symbol": symbol,
        "proposal": proposal,
        "sector": sector_en,  # 纯英文
        "contract_details": symbol_profile.get("contract_details", ""),
        "covariate_menu": covariate_menu or _load_covariate_menu(),
        "recent_verdicts_summary": _extract_relevant_history(verdict_history, symbol),
    }
```

- [ ] **Step 4e: 改 `_extract_relevant_history`（line 110）— 英文化模板**

把中文模板替换为英文：

```python
def _extract_relevant_history(
    verdict_history: list[dict] | None,
    symbol: str,
    max_entries: int = 5,
    max_cross_entries: int = 5,
) -> str:
    """Two-section history summary: symbol's gate-pass records + sector peer priors. (English only)"""
    from config.sector_map import sector_of, SECTORS, SECTOR_NAMES_EN
    
    lines = []
    
    # Section 1: current symbol's gate-pass records
    if verdict_history:
        relevant = [v for v in verdict_history if v.get("symbol") == symbol and v.get("gate_pass")]
        if relevant:
            recent = sorted(relevant, key=lambda v: v.get("decided_at") or "", reverse=True)[:max_entries]
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
```

- [ ] **Step 4f: 运行测试确认通过**

```bash
pytest tests/test_laya_state_english_only.py -v
```

预期：全部 PASS

- [ ] **Step 4g: 运行全量 prescreen 测试确认无回归**

```bash
pytest tests/test_laya_prescreen.py tests/test_prescreen_score.py tests/test_slow_loop_prescreen.py tests/test_track_prescreen_quality.py tests/test_laya_failure_classification.py tests/test_circuit_breaker.py tests/test_laya_timeout_tiers.py tests/test_laya_state_english_only.py -v
```

预期：全绿

- [ ] **Step 4h: 提交**

```bash
git add cascade/laya_prescreen.py config/sector_map.py tests/test_laya_state_english_only.py
git commit -m "feat(laya): state truly English-only (sector + history)

- Add SECTOR_NAMES_EN in config/sector_map.py (English display for Laya state only)
- DO NOT touch SECTOR_NAMES (Chinese values still used by other modules)
- _build_state uses sector_of() + SECTOR_NAMES_EN for pure-English sector
- Default sector for unknown symbols: 'unknown' (not '未知')
- _extract_relevant_history templates fully English ('gate-passed covariates', 'family:', 'Sector peers')
- Empty history: 'No verdict history available' (not '无历史裁决记录')

Spec: docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md §3.4"
```

---

## Task 5: P1-2 — 队列感知退避（滑动窗口 p80 > 20s 跳过）

**Files:**
- Modify: `cascade/laya_prescreen.py`（末尾新增 `_latency_window` + `_record_latency` + `_should_skip_prescreen`）
- Modify: `cascade/laya_prescreen.py:374-426`（`_prescreen_impl` — 入口加退避检查）
- Create: `tests/test_laya_queue_backoff.py`

**Interfaces:**
- Consumes: `_prescreen_impl`（已存在）
- Produces:
  - `_record_latency(latency: float)` — 记录单次调用延迟
  - `_should_skip_prescreen() -> bool` — p80 > 20s 返回 True
  - `_latency_window: list[float]` — 模块级滑动窗口（最近 10 次）

- [ ] **Step 5a: 写失败测试 — p80 阈值**

文件：`tests/test_laya_queue_backoff.py`

```python
from cascade import laya_prescreen as lp

class TestQueueBackoff:
    def setup_method(self):
        lp._latency_window.clear()
    
    def test_under_5_samples_never_skips(self):
        """样本 < 5 时不启用退避（冷启动期）。"""
        for lat in [1.0, 2.0, 3.0, 4.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is False

    def test_p80_under_20s_does_not_skip(self):
        """p80 <= 20s 时正常调用。"""
        for lat in [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 15.0]:
            lp._record_latency(lat)
        # p80 = sorted[7] = 12.0
        assert lp._should_skip_prescreen() is False

    def test_p80_over_20s_skips(self):
        """p80 > 20s 时跳过后续请求。"""
        for lat in [5.0, 6.0, 7.0, 8.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0]:
            lp._record_latency(lat)
        # sorted = [5,6,7,8,21,22,23,24,25,26]; p80 = sorted[7] = 24.0 > 20
        assert lp._should_skip_prescreen() is True

    def test_window_is_bounded_at_10(self):
        """滑动窗口最多保留 10 条。"""
        for i in range(20):
            lp._record_latency(float(i))
        assert len(lp._latency_window) == 10

    def test_recovery_after_backoff(self):
        """p80 回落到 < 15s 后恢复正常调用。"""
        # 先拥堵
        for lat in [5.0, 6.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0, 31.0, 32.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is True
        
        # 恢复到正常
        lp._latency_window.clear()
        for lat in [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0]:
            lp._record_latency(lat)
        assert lp._should_skip_prescreen() is False
```

- [ ] **Step 5b: 运行测试确认失败**

```bash
pytest tests/test_laya_queue_backoff.py -v
```

预期：FAIL — `_record_latency` / `_should_skip_prescreen` / `_latency_window` 不存在

- [ ] **Step 5c: 在 `cascade/laya_prescreen.py` 末尾新增队列感知函数**

```python
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
```

注：
- **线程安全**：`_latency_lock` 保护 append/pop（P1-8 补丁）
- **滞后防抖**：`p80 > 20s` 跳过，`p80 < 15s` 恢复；中间地带不切换（P1-7 补丁）

- [ ] **Step 5d: 在 `_prescreen_impl` 入口（line ~374）加退避检查**

在 `if _check_circuit():` 之后、`state = _build_state(...)` 之前加：

```python
if _should_skip_prescreen():
    return _fallback_result(proposal, symbol, status="degraded", note="queue_congestion_skip (p80 > 20s)")
```

并在成功路径与失败路径都加 `_record_latency(elapsed)`：

```python
start_t = time.time()
try:
    result = _call_laya(state, api_key, timeout=_TIMEOUT_PRIMARY)
except LayaUnavailableError as e:
    _record_latency(time.time() - start_t)
    _record_failure("503_unavailable")
    logger.warning("Laya 503: %s", e)
    return _fallback_result(proposal, symbol, status="degraded", note=str(e))
except (LayaTimeoutError, requests.Timeout) as e:
    _record_latency(time.time() - start_t)
    _record_failure("timeout")
    logger.warning("Laya timeout: %s", e)
    return _fallback_result(proposal, symbol, status="degraded", note=str(e))
except ConnectionError as e:
    _record_latency(time.time() - start_t)
    _record_failure("connection_error")
    logger.warning("Laya connection error: %s", e)
    return _fallback_result(proposal, symbol, status="degraded", note=str(e))
except AuthenticationError as e:
    logger.error("Laya auth error: %s", e)
    return _fallback_result(proposal, symbol, status="error", note=str(e))
except Exception as e:
    _record_latency(time.time() - start_t)
    _record_failure("unknown")
    logger.exception("Laya unknown failure: %s", e)
    return _fallback_result(proposal, symbol, status="error", note=str(e))

_record_latency(time.time() - start_t)
_record_success()
```

注：每个 `except` 分支在 return 前调 `_record_latency`；成功路径在 `_record_success()` 之前调。确保每次调用（无论成败）都记录延迟，且只记录一次。

- [ ] **Step 5e: 运行测试确认通过**

```bash
pytest tests/test_laya_queue_backoff.py -v
```

预期：全部 PASS

- [ ] **Step 5f: 运行全量测试确认无回归**

```bash
pytest tests/ -k "laya or prescreen" -v
```

预期：全绿

- [ ] **Step 5g: 提交**

```bash
git add cascade/laya_prescreen.py tests/test_laya_queue_backoff.py
git commit -m "feat(laya): queue-aware backoff (sliding window p80 > 20s skip)

- _latency_window: bounded list of last 10 call latencies
- _should_skip_prescreen: returns True when p80 > 20s (min 5 samples)
- _prescreen_impl records latency on both success and failure paths
- Recovery automatic when p80 drops below threshold

Spec: docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md §3.5"
```

---

## Task 6: 验收 + 文档 + 推送备份

**Files:**
- Modify: `docs/superpowers/changelogs/2026-10-24-laya-prescreen-optimization-changelog.md`（新建）
- Modify: `docs/handbook.md`（如提及 Laya 调用策略，追加引用）

- [ ] **Step 6a: 运行全量测试确认基线**

```bash
cd /home/abug/timesfm
pytest tests/ -k "laya or prescreen or circuit" -v
```

预期：所有新测试 + 旧测试全绿，无回归

- [ ] **Step 6b: 跑一次真实预筛验证端到端**

```bash
cd /home/abug/timesfm
# 取一个真实提案 variant_id，调用 prescreen_proposal，观察日志
python3 -c "
from cascade.laya_prescreen import prescreen_proposal
import json

# 用一个真实提案（从 experiments/ 取）
# 若 Laya 服务不可达，预期日志显示 '503_unavailable' 或 'timeout' 或 'connection_error'
# 若可达，预期 'success' + 纯英文 state
result = prescreen_proposal('path/to/some/proposal.json')
print(json.dumps(result, indent=2))
"
```

预期：日志能看到 `Laya prescreen failure: <reason>` 或 `success`，且 state 无中文

- [ ] **Step 6c: 写 changelog**

文件：`docs/superpowers/changelogs/2026-10-24-laya-prescreen-optimization-changelog.md`

内容按模板：
- 问题（503 主导失败、熔断不覆盖 503、state 含中文）
- 根因（`_call_laya` 吞 503 成 `ConnectionError`；`_prescreen_impl` 仅对 `TimeoutError` 调 `_record_timeout`）
- 修复方案（P0-1/P0-2/P0-3/P1-1/P1-2 5 个 task 的摘要）
- 关键设计决策（`LayaUnavailableError` 区分、三态熔断 + 探针锁、SECTOR_NAMES_EN 不替换 SECTOR_NAMES）
- 测试覆盖（5 个新测试文件）
- 验收结果（Step 6a/6b 输出）
- 不做的事（不改服务端、不引新依赖、不硬阻断慢环）

- [ ] **Step 6d: 提交 changelog**

```bash
git add docs/superpowers/changelogs/2026-10-24-laya-prescreen-optimization-changelog.md
git commit -m "docs: laya prescreen optimization changelog (Day1+Day2 complete)"
```

- [ ] **Step 6e: 推送备份（需用户授权）**

```bash
git push backup master
```

注：**本轮用户禁止开工**；实施阶段需用户明确授权 push。若用户未授权，跳过此步。

- [ ] **Step 6f: 通知用户验收完成**

汇报：
- 5 个 task 全部 PASS
- N 个新测试加入，0 个回归
- changelog 已推送
- 现网效果需 1-2 天观察（503 主导失败是否下降、熔断 OPEN 时是否 0 等待）

---

## 执行顺序与依赖

```text
Day 1 (P0，立即)
  Task 1: P0-1 统一 failure 分类 (无依赖)
    ↓
  Task 2: P0-2 三态熔断器 (依赖 Task 1 的 _record_failure)
    ↓
  Task 3: P0-3 timeout 分档 (依赖 Task 1 + Task 2)

Day 2 (P1，次日)
  Task 4: P1-1 state 英文化 (无依赖，可与 Day1 并行)
  Task 5: P1-2 队列感知退避 (无依赖，可与 Day1 并行)

收尾
  Task 6: 验收 + 文档 + 推送备份
```

**执行策略**：用户已明确「用专家执行计划」→ 走 `superpowers:subagent-driven-development`。每个 Task 派 `oh-my-claudecode:executor` subagent 实施，完成后派 `oh-my-claudecode:code-reviewer` 审核，BLOCK 则修复重审，PASS 则进入下一 Task。

---

## 验收总表（最终 DoD）

| # | 验收项 | Task |
|---|--------|------|
| 1 | 503 / timeout / ConnectionError 全部触发熔断 | Task 1 + 2 |
| 2 | 连续 3 次 failure → OPEN | Task 2 |
| 3 | OPEN 5 分钟后 → HALF_OPEN（仅 1 个探针） | Task 2 |
| 4 | HALF_OPEN 探针成功 → CLOSED；失败 → OPEN | Task 2 |
| 5 | **`sector` + `history` 无中文字符**（scope 收窄，不含 `contract_details` / `covariate_menu`） | Task 4 |
| 6 | 空闲场景：预筛成功率 > 90% | Task 3（端到端验证） |
| 7 | 拥堵场景：熔断 OPEN 时客户端等待 p50=0 | Task 2 + 6 |
| 8 | 503 快速失败 < 1s | Task 1 + 3 |
| 9 | 预筛失败不影响慢环回测（软降级） | Task 1-5（`status="degraded"`） |
| 10 | 日志可追溯（延迟、状态、熔断器状态、failure 原因） | Task 1-5 |
| 11 | 配置项可回滚（3 个 env，bool 显式解析） | Task 2 |
| 12 | 队列感知退避：p80 > 20s 跳过，p80 < 15s 恢复（滞后防抖） | Task 5 |

---

## 审计补丁追踪（2026-10-24 plan audit）

| 审计 # | 级别 | 问题 | 补丁位置 |
|--------|------|------|----------|
| P0-1 | P0 | 裸 `TimeoutError` 从捕获元组消失 | Task 1 Step 1h：保留 `TimeoutError` |
| P0-2 | P0 | `note=str(e)` 破坏现有断言 | Task 1 Step 1h：保留中文前缀 |
| P0-3 | P0 | Task3 测试伪代码不可运行 | Task 3 Step 3a：显式 `import requests` + `MagicMock` |
| P1-4 | P1 | 真实 timeout 经 `_call_laya` 仍升为 `ConnectionError` | Task 1 Step 1d：双端点皆超时后 `raise LayaTimeoutError` |
| P1-5 | P1 | DoD「state 所有字段无中文」超 Task4 范围 | Task 4 标题收窄：`sector` + `history`；DoD 表 #5 同步收窄 |
| P1-6 | P1 | `LAYA_CIRCUIT_BREAKER_ENABLED` 恒真 | Task 2 Step 2e：`_parse_bool_env` 显式解析 |
| P1-7 | P1 | 恢复条件「p80 < 15s」未实现 | Task 5 Step 5c：`_P80_THRESHOLD_RECOVER = 15.0` 滞后 |
| P1-8 | P1 | `_latency_window` 无锁 | Task 5 Step 5c：`_latency_lock = threading.Lock()` |
| P1-9 | P1 | 旧测 `test_half_open_resets_on_expire` 语义变化 | Task 2 Step 2j：改写断言匹配新三态 |
| P2-10 | P2 | Plan 写 Spec「v3」——应为 v2 | Plan 头部：改为「v2 + audit ~88%」 |
| P2-11 | P2 | Task6 `git push backup master` 本轮禁止 | Task 6 Step 6e：加注释「需用户授权」 |
| P2-12 | P2 | `_call_laya(..., timeout=)` 形参成死参 | Task 3 Step 3e：实施时可删除形参或注明 |
