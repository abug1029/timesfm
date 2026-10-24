# Laya 预筛调用优化规范（修订版 v2）

**日期**: 2026-10-23  
**作者**: FM研  
**状态**: 修订版（已根据审计反馈修订，待二审）  
**依据**: Laya 服务端日志调研结论 + 审计反馈（2026-10-23 22:10）

---

## 0. 执行摘要

Laya 预筛服务存在性能瓶颈：**单推理 worker + 16 名额队列 + checkpoint 切换开销**。当前调用逻辑在高负载时频繁超时，导致预筛失效。本规范提出客户端韧性优化措施，预期将无效等待时间降至最低，并在拥堵时智能降级。

**当前状态**: 软建议模式（不阻断慢环），但高负载时 503 主导失败（85/94）  
**目标**: 智能降级（空闲时预筛，拥堵时跳过），统一 failure 分类并驱动熔断  
**预计工期**: 1-2 天（P0 项 0.5-1 天）

### 关键修订（相对 v1）

1. **失败模式修正**：现网主导是 **503（85/94）**，不是 timeout（5/94）
2. **实施顺序调整**：先修异常分类 + 熔断覆盖（含 503）→ 再评估 timeout 上调
3. **基线修正**：去掉虚假「30s→0s」；有效路径已是 5s
4. **English-only 缺口承认**：state 仍含中文板块名与历史，需真正英文化
5. **DoD 统一**：去掉「跳过 2 分钟」矛盾表述

---

## 1. 问题陈述

### 1.1 服务端架构约束（外部调研，待管理员复核）

根据 Laya 服务端日志调研（`serve.py` 源码分析，**本仓无读权**）：

| 组件 | 配置 | 含义 |
|------|------|------|
| `ThreadPoolExecutor(max_workers=1)` | 单推理 worker | 同时只有 1 个请求在计算 |
| `LAYA_MAX_CONCURRENT=16` | 全局 asyncio.Lock 名额 | 1 个计算 + 15 个排队，第 17 个返回 503 |
| `LAYA_MAX_LOADED=1` | 单 checkpoint 驻留 | 混合语言触发 checkpoint 切换（+11.6s） |

**注意**：以上数字来自外部调研，未在本仓独立核实。若作为容量规划依据，需管理员复核 `serve.py`。

### 1.2 现网失败结构（2026-10-23 22:08 CST）

客户端侧今日 experiments 下 `*.prescreen.json` **94 条全部 error**：

| note 前缀 | 条数 | 含义 |
|-----------|------|------|
| `All Laya endpoints unreachable: 503 Server Error` | **85** | 队列满/拒收 → **现码记 error，不进熔断** |
| `HTTPConnectionPool ... Read timed out` | **5** | 真超时；经 `_call_laya` 内吞掉后常升为 `ConnectionError` |
| 其他连接/旧 TypeSafe 文案 | 4 | 连通性 |

**结论**：现网主导失败是 **503**，不是 timeout。

### 1.3 客户端超时行为

- **客户端超时放弃不会省算力**：`serve.py:1105` 注释明确："a cancelled HTTP request whose forward pass continues after the event loop releases the gate"
- **当前代码**：`_prescreen_impl` 调 `_call_laya(..., timeout=5.0)`；`_call_laya` 签名默认 30.0 **未被 prescreen 使用**
- **问题**：
  - 5s < 6.4s（正常推理），导致空闲时也超时
  - 但 **503 是秒级拒绝**，不是 30s 空等
  - 异常分类未统一：503 / `ConnectionError` / timeout 不全触发熔断

### 1.4 English-only 缺口

**现状**：
- payload 已有 `language: "en"` ✅
- **但** `_build_state` / `_extract_relevant_history` 仍注入 **中文** `SECTOR_NAMES`（如「黑色系」「能化」）与中文历史摘要 ❌

**结论**：「state 全英文」未成立，可能触发 checkpoint 切换惩罚。

---

## 2. 目标状态

### 2.1 成功标准（Definition of Done）

1. **统一 failure 分类**：503 / `ConnectionError` / timeout 全部记为 failure 并驱动熔断
2. **熔断覆盖 503**：连续 3 次 503 后进入 OPEN 状态，后续请求直接跳过
3. **空闲场景**：timeout 覆盖 6.4s 推理 + 3s 网络缓冲 = **10s**（在熔断覆盖 503 后评估）
4. **拥堵场景**：熔断 OPEN 时客户端等待 **p50=0**（直接跳过）
5. **English-only 真正生效**：state 所有字段纯英文（含板块名、历史摘要），避免 checkpoint 切换

### 2.2 不做的事

- **不修改服务端**：不碰 Laya 的 `serve.py`、不增加 worker、不改队列深度
- **不硬阻断慢环**：预筛仍是软建议模式，失败时静默跳过
- **不引入新依赖**：用现有 `requests` 库，不引 `aiohttp` / `httpx`
- **不虚假宣称「30s→0s」**：基线已是 5s，优化目标是「熔断 OPEN 时 0 等待」

---

## 3. 优化方案

### 3.1 P0-1：统一 failure 分类 + 熔断覆盖 503

**现状**（只读对齐）：
```python
# cascade/laya_prescreen.py
def _call_laya(state, api_key, timeout=5.0):
    endpoints = _get_laya_endpoints()
    last_error = None
    for endpoint in endpoints:
        try:
            resp = requests.post(f"{endpoint}/v1/systemone", json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            continue
    raise ConnectionError(f"All Laya endpoints unreachable: {last_error}")

def _prescreen_impl(...):
    try:
        result = _call_laya(state, api_key, timeout=5.0)
        # ...
    except (TimeoutError, LayaTimeoutError) as e:
        _record_timeout()  # 仅 timeout 进熔断
        return _fallback_result(note=str(e))
    except Exception as e:
        return _fallback_result(note=str(e))  # 503 / ConnectionError 走这里，不进熔断！
```

**问题**：
- `_call_laya` 把所有异常（含 503）吞掉后统一抛 `ConnectionError`
- `_prescreen_impl` 仅对 `TimeoutError` / `LayaTimeoutError` 调 `_record_timeout()`
- `ConnectionError`（含 503）走 `Exception` 分支，**永不触发熔断**
- 今日 85/94 的 503 全部不进熔断 → 熔断永远不打开

**修复（双层）**：

**层 1：改 `_call_laya` — 503 立即 re-raise 专用异常**
```python
class LayaUnavailableError(Exception):
    """Laya 服务不可用（503 / 队列满）。"""
    pass

def _call_laya(state, api_key, timeout=5.0):
    endpoints = _get_laya_endpoints()
    last_error = None
    for endpoint in endpoints:
        try:
            resp = requests.post(f"{endpoint}/v1/systemone", json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 503:
                raise LayaUnavailableError(f"503 from {endpoint}") from e
            last_error = e
            continue
        except requests.Timeout as e:
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue
    raise ConnectionError(f"All Laya endpoints unreachable: {last_error}")
```

**层 2：改 `_prescreen_impl` — 统一 failure 分类**
```python
def _prescreen_impl(...):
    try:
        result = _call_laya(state, api_key, timeout=5.0)
        # ...
    except LayaUnavailableError as e:
        _record_failure("503_unavailable")  # 503 进熔断
        return _fallback_result(note=str(e))
    except (LayaTimeoutError, requests.Timeout, ConnectionError) as e:
        _record_failure("timeout_or_connection")  # 统一记 failure
        return _fallback_result(note=str(e))
    except Exception as e:
        _record_failure("unknown")
        return _fallback_result(note=str(e))

def _record_failure(reason: str):
    """统一 failure 记录，驱动熔断。"""
    _circuit_breaker.record_failure()
    logger.warning(f"Laya prescreen failure: {reason}")
```

**验收**：
- [ ] 503 触发熔断（连续 3 次后 OPEN）
- [ ] timeout / ConnectionError 触发熔断
- [ ] 日志记录 failure 原因（`503_unavailable` / `timeout_or_connection` / `unknown`）

### 3.2 P0-2：熔断器增强（三态，修复惊群）

**现状**：简单计数（连续 3 次超时 → 10 分钟后全量重置）。

**修复**：三态熔断器，HALF_OPEN 仅允许 1 个探针：

```python
class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, threshold=3, duration=300):
        self.state = self.CLOSED
        self.failure_count = 0
        self.threshold = threshold
        self.duration = duration
        self.last_failure_time = None
        self._half_open_probe_in_flight = False

    def record_success(self):
        self.failure_count = 0
        self.state = self.CLOSED
        self._half_open_probe_in_flight = False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.state = self.OPEN
        self._half_open_probe_in_flight = False

    def should_skip(self) -> bool:
        """返回 True 表示应跳过预筛。HALF_OPEN 时仅允许 1 个探针。"""
        if self.state == self.CLOSED:
            return False
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time > self.duration:
                if not self._half_open_probe_in_flight:
                    self.state = self.HALF_OPEN
                    self._half_open_probe_in_flight = True
                    return False  # 允许 1 个探针
                return True  # 探针进行中，其他跳过
            return True  # OPEN 中，跳过
        if self.state == self.HALF_OPEN:
            if self._half_open_probe_in_flight:
                return True  # 探针进行中，其他跳过
            return False  # 不应到达，但防御性返回 False
        return False
```

**验收**：
- [ ] 连续 3 次 failure → OPEN
- [ ] OPEN 5 分钟后 → HALF_OPEN（仅 1 个探针）
- [ ] HALF_OPEN 探针成功 → CLOSED
- [ ] HALF_OPEN 探针失败 → OPEN（再等 5 分钟）
- [ ] HALF_OPEN 期间其他请求跳过（不惊群）

### 3.3 P0-3：timeout 上调（在 P0-1/P0-2 之后）

**现状**：`timeout=5.0` < 6.4s（正常推理）。

**前置条件**：P0-1（failure 分类）+ P0-2（熔断覆盖 503）完成后，再评估 timeout。

**修复**：
```python
_TIMEOUT_PRIMARY = 10.0  # 覆盖 6.4s 推理 + 3s 网络缓冲
_TIMEOUT_FALLBACK = 5.0  # 第二个端点快速探测

def _call_laya(state, api_key, timeout=_TIMEOUT_PRIMARY):
    endpoints = _get_laya_endpoints()
    last_error = None
    for i, endpoint in enumerate(endpoints):
        t = _TIMEOUT_PRIMARY if i == 0 else _TIMEOUT_FALLBACK
        try:
            resp = requests.post(f"{endpoint}/v1/systemone", json=payload, timeout=t)
            resp.raise_for_status()
            return resp.json()
        except LayaUnavailableError:
            raise  # 503 快速失败，不试第二个端点
        except requests.Timeout as e:
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue
    raise ConnectionError(f"All Laya endpoints unreachable: {last_error}")
```

**注意**：503（`LayaUnavailableError`）不试第二个端点（队列满 = 两个端点都满）。

**验收**：
- [ ] 空闲场景成功率 > 90%（定义：`status=success` 且非熔断跳过）
- [ ] 503 快速失败（< 1s）
- [ ] timeout 后 5s 内完成第二个端点探测

### 3.4 P1-1：state 真正英文化

**现状**：
```python
# config/sector_map.py
SECTOR_NAMES = {
    "black_metals": "黑色系",  # 英文 key → 中文 value（用于 display）
    "energy_chem": "能化",
    "agri": "农产品",
}

# cascade/laya_prescreen.py
def _build_state(proposal):
    sector = profile.get("sector", "未知")  # 中文！
    return {
        "sector": sector,  # 写入 state 的是中文
        "history": _extract_relevant_history(proposal),  # 含中文模板
    }
```

**问题**：
- `SECTOR_NAMES` 是 **英文 key → 中文 value**（用于 display）
- 但 `_build_state` 把中文 value 写入 `state["sector"]` → 触发 checkpoint 切换
- `_extract_relevant_history` 大量中文模板（「已过门协变量」「同板块」「族:」等）

**修复（不改共享 display 表）**：
```python
# 新增：英文 sector 映射（仅用于 Laya state）
SECTOR_NAMES_EN = {
    "black_metals": "ferrous",
    "energy_chem": "energy_chemical",
    "agri": "agricultural",
    "non_ferrous": "non_ferrous",
}

def _build_state(proposal):
    sector_key = proposal.get("sector_key", "")  # 英文 key
    sector_en = SECTOR_NAMES_EN.get(sector_key, "unknown")
    
    history = _extract_relevant_history(proposal)
    history = _strip_chinese_from_history(history)  # 过滤中文模板
    
    return {
        "sector": sector_en,  # 纯英文
        "history": history,
        # ... 其他字段确保英文
    }

def _strip_chinese_from_history(history: str) -> str:
    """移除中文模板，保留英文内容。"""
    # 简单实现：过滤含中文的行
    lines = history.split("\n")
    english_lines = [l for l in lines if not re.search(r"[一-鿿]", l)]
    return "\n".join(english_lines)
```

**注意**：
- **不改** `config/sector_map.py` 的 `SECTOR_NAMES`（共享 display 表，其他模块依赖中文 value）
- **新增** `SECTOR_NAMES_EN` 仅用于 Laya state 注入
- 英文化优先改 history 模板与 `state["sector"]` 注入

**验收**：
- [ ] state 所有字段无中文字符（正则检查 `[一-鿿]`）
- [ ] 预筛请求日志记录 `checkpoint` 字段，无 `multilingual`

### 3.5 P1-2：队列感知退避（滑动窗口）

**方案**：滑动窗口监控延迟，p80 > 20s 时主动跳过。

```python
_latency_window = []  # 最近 10 次调用延迟

def _record_latency(latency: float):
    _latency_window.append(latency)
    if len(_latency_window) > 10:
        _latency_window.pop(0)

def _should_skip_prescreen() -> bool:
    """队列感知：p80 > 20s 时跳过。"""
    if len(_latency_window) < 5:
        return False
    sorted_latencies = sorted(_latency_window)
    p80 = sorted_latencies[-3]  # n=10 时第 3 高 ≈ p80
    return p80 > 20.0

def _prescreen_impl(...):
    if _should_skip_prescreen():
        return _fallback_result(note="queue_congestion_skip")
    # ... 正常调用
```

**验收**：
- [ ] p80 > 20s 时后续请求直接跳过
- [ ] p80 恢复到 < 15s 后恢复正常调用

### 3.6 P2（暂缓）

**批量预筛**：Session 串行对单 worker 服务端几乎无吞吐收益，**不实施**。

**强制 English checkpoint**：需服务端配合，**暂缓**。

---

## 4. 实施顺序

```text
Day 1（立即）
  ├─ P0-1: 统一 failure 分类 + 熔断覆盖 503
  ├─ P0-2: 熔断器增强（三态，修复惊群）
  └─ P0-3: timeout 上调（10s + 5s fallback）← 依赖 P0-1/P0-2

Day 2
  ├─ P1-1: state 真正英文化
  ├─ P1-2: 队列感知退避（滑动窗口）
  └─ 测试验证（单元测试 + 集成测试）
```

**关键约束**：P0-3（timeout 上调）必须在 P0-1/P0-2（熔断覆盖 503）完成后实施。

---

## 5. 验收清单

### 5.1 功能验收

- [ ] 503 / timeout / ConnectionError 全部触发熔断
- [ ] 连续 3 次 failure → OPEN 状态
- [ ] OPEN 5 分钟后 → HALF_OPEN（仅 1 个探针）
- [ ] HALF_OPEN 探针成功 → CLOSED
- [ ] state 所有字段无中文字符
- [ ] 空闲场景：预筛成功率 > 90%（定义：`status=success` 且非熔断跳过）
- [ ] 拥堵场景：熔断 OPEN 时客户端等待 p50=0（直接跳过）

### 5.2 性能验收

- [ ] 无效等待时间减少：熔断 OPEN 时 0 等待
- [ ] 503 快速失败 < 1s
- [ ] 预筛失败不影响慢环回测（软降级）
- [ ] 日志可追溯：每次预筛记录延迟、状态、熔断器状态、failure 原因

### 5.3 回滚方案

- [ ] 配置项：`LAYA_CIRCUIT_BREAKER_ENABLED`（默认 true）
- [ ] 配置项：`LAYA_CIRCUIT_BREAKER_THRESHOLD`（默认 3）
- [ ] 配置项：`LAYA_CIRCUIT_BREAKER_DURATION`（默认 300s）
- [ ] 若优化后预筛成功率下降，可关闭熔断器

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 熔断器误判（正常请求被跳过） | 阈值可调，日志记录每次跳过原因 |
| 503 风暴时熔断不开 | P0-1 统一 failure 分类，503 显式触发熔断 |
| state 英文化遗漏 | 正则检查 + 单元测试覆盖所有 sector |
| HALF_OPEN 惊群 | 探针锁（`_half_open_probe_in_flight`） |
| 服务端数字不可复验 | 标「外部调研，待管理员复核」 |

---

## 7. 参考链接

- Laya 服务端源码：`serve.py`（`/home/laya/serve/serve.py`，需管理员权限，**本仓无读权**）
- 客户端代码：`cascade/laya_prescreen.py`
- 调研结论：用户提供的服务端日志分析（2026-10-23）
- 审计反馈：`docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec-audit.md`

---

## 8. 与既有 SPEC / 审计对齐

| 既有结论 | 本 SPEC | 对齐 |
|----------|---------|------|
| Laya 不可学习 | 无学习叙事；只改客户端调用策略 | ✅ |
| proposals-evaluation-optimization 通过 | 不重叠主目标 | ✅ 互补 |
| Phase2–3 praxist 集成 ~78% | 本 SPEC 不声称修 B3/旁路 | ✅ 范围更窄 |
| 现网 503 主导失败 | P0-1 统一 failure 分类覆盖 503 | ✅ 修订 |

---

## 9. 下一步（需用户拍板）

### 9.1 授权实施 P0（立即）

批准执行 §3.1 + §3.2 + §3.3：
- 统一 failure 分类 + 熔断覆盖 503
- 熔断器增强（三态）
- timeout 上调（10s + 5s fallback）

**要求**：今日内闭环，明天验证效果。

### 9.2 授权实施 P1（Day 2）

批准执行 §3.4 + §3.5：
- state 真正英文化
- 队列感知退避

### 9.3 暂缓 P2

维持默认建议：不实施批量预筛 / 强制 English checkpoint。

---

**文档结束**
