# Laya 服务优化实施计划 - 完整三阶段版

**日期：** 2026-11-07
**版本：** v1.1（根据工程审查修订）
**基于：** 调研报告 v2.1 + 优化规格说明书 v1.1
**状态：** 待审批

---

## 总体架构概览

```
Client
  |
  |  POST /v1/systemone 或 /v1/systemone/batch
  |
  v
[DecisionLogMiddleware]  <-- ASGI 中间件，记录决策日志
  |
  v
[_admit()]               <-- 准入层：Semaphore(max_concurrent=10)
  |                          满员立即 503 + 动态 Retry-After
  |
  v
[_systemone_inner]       <-- 推理入口：解析请求、参数验证
  |                          或
  | [_systemone_batch_inner]
  |
  v
[asyncio.Lock gate]      <-- 推理门：排他锁，单线程执行
  |                          F1: 僵尸检测 (is_disconnected + TTL 205s)
  |
  v
[run_in_executor]        <-- ThreadPoolExecutor(max_workers=1)
  |                          在独立线程中执行 router.predict
  |
  v
[JSONResponse]           <-- 返回结果 + X-Inference-Time-Ms
```

---

## 阶段间依赖关系

```
阶段一（止血）          阶段二（优化）           阶段三（演进）
├── F1 僵尸检测 ──────→ F5 LRU 缓存 ──────→ 异步任务队列
├── F2 准入调整 ──────→ F6 推理加速 ──────→ 硬件升级评估
└── F3 动态 Retry-After ─→ F4 排队响应头 ──→ 水平扩展方案

前置条件：
  阶段二 → 阶段一全部完成且验证通过（僵尸请求漏网率 < 1%）
  阶段三 → 阶段二全部完成且推理加速方案已选定
```

---

## 阶段一：立即止血（本周，1-2 天）

**目标：** 消除僵尸推理浪费，确保入队请求 100% 在客户端超时前完成。

**预计总工时：** ~1.5 小时（不含测试验证）
**风险等级：** 低（仅插入检查，不删除原有代码）

---

### 1. 变更清单

#### 1.1 修改文件清单

| 文件 | 变更类型 | 行号范围 | 变更摘要 |
|------|---------|---------|---------|
| `laya/serve.py` (包内) | 修改 | ~137 | `DEFAULT_MAX_CONCURRENT` 从 16 下调至 10 |
| `laya/serve.py` (包内) | 新增 | ~137 之后 | 辅助函数：`_compute_retry_after`、`_record_inference_time`、`_avg_inference_time_ms` |
| `laya/serve.py` (包内) | 新增 | 顶部 import | `import random`（如未存在）|
| `laya/serve.py` (包内) | 修改 | ~1230-1246 | `_admit()` 上下文管理器：动态 Retry-After + 排队信息响应头 |
| `laya/serve.py` (包内) | 修改 | ~1248-1252 | `_systemone` 端点：记录 `enqueue_time` 并传递 |
| `laya/serve.py` (包内) | 修改 | ~1254 | `_systemone_inner` 签名：新增 `enqueue_time` 参数 |
| `laya/serve.py` (包内) | 修改 | ~1306-1327 | `_systemone_inner` 推理门：僵尸检测 + TTL 检查 + 推理时间记录 |
| `laya/serve.py` (包内) | 修改 | ~1345-1349 | `_systemone_batch` 端点：记录 `enqueue_time` 并传递 |
| `laya/serve.py` (包内) | 修改 | ~1351 | `_systemone_batch_inner` 签名：新增 `enqueue_time` 参数 |
| `laya/serve.py` (包内) | 修改 | ~1436-1470 | `_systemone_batch_inner` 推理门：同样的僵尸检测 + TTL |
| `start-laya-serve.ps1` (如有) | 修改 | 环境变量 | `LAYA_MAX_CONCURRENT=10` |

#### 1.2 无需修改的文件

- `serve_with_log.py` -- 仅调用 `laya.serve.main()`，不涉及推理逻辑
- `.venv` 虚拟环境 -- 直接修改 `site-packages/laya/serve.py`，无需重建

#### 1.3 新增代码

##### A. 全局辅助函数和计数器

在 `DEFAULT_MAX_CONCURRENT` 定义之后（约第 138 行）添加：

```python
import random
import threading

# === 推理时间追踪（滑动窗口，最近 100 个请求） ===
_inference_times: list[float] = []
_inference_times_lock = threading.Lock()


def _record_inference_time(ms: float) -> None:
    """记录一次推理耗时，保留最近 100 个样本。"""
    with _inference_times_lock:
        _inference_times.append(ms)
        if len(_inference_times) > 100:
            _inference_times[:] = _inference_times[-100:]


def _avg_inference_time_ms() -> float | None:
    """返回滑动窗口平均推理时间（毫秒），无样本时返回 None。"""
    with _inference_times_lock:
        if not _inference_times:
            return None
        return sum(_inference_times) / len(_inference_times)


def _compute_retry_after(avg_infer_ms: float | None = None) -> int:
    """计算重试间隔：下一个槽位释放时间（~10-20s），非全队列排空时间。"""
    base = (avg_infer_ms / 1000.0) if avg_infer_ms is not None else 17.0
    jitter = base * random.uniform(0.6, 1.2)
    return max(1, int(jitter))


# === 僵尸请求计数器 ===
zombie_skipped_disconnected = 0  # 推理前因断连跳过的请求数
zombie_skipped_expired = 0       # 推理前因 TTL 超期跳过的请求数
zombie_executed_counter = 0      # 推理完成后才发现断连的漏网之鱼
```

##### B. `_admit()` 修改（替换原 1230-1246 行）

```python
    @asynccontextmanager
    async def _admit():
        nonlocal admission
        if admission is None:
            admission = asyncio.Semaphore(max_concurrent)
        if admission.locked():
            # 动态 Retry-After：下一个槽位释放时间，非全队列排空时间
            avg_ms = _avg_inference_time_ms()
            retry_after = _compute_retry_after(avg_ms)
            # 动态预估等待时间：使用滑动窗口平均值
            avg_sec = (avg_ms / 1000.0) if avg_ms else 17.0
            est_wait = int(max_concurrent * avg_sec)
            # 立即 503，消耗 0 算力（准入层在推理之前，耗时 < 1ms）
            raise HTTPException(
                status_code=503,
                detail="server busy, try again later",
                headers={
                    "Retry-After": str(retry_after),
                    "X-Queue-Depth": str(max_concurrent),
                    "X-Estimated-Wait-Time": str(est_wait),
                    "X-Queue-Slots-Available": "0",
                }
            )
        await admission.acquire()
        try:
            yield
        finally:
            admission.release()
```

##### C. `_systemone` 端点修改（约 1248-1252 行）

```python
    @app.post("/v1/systemone")
    async def systemone(request: Request, authorization: Optional[str] = Header(default=None)):
        _check_auth(authorization)
        enqueue_time = time.monotonic()
        async with _admit():
            return await _systemone_inner(request, enqueue_time)
```

##### D. `_systemone_inner` 签名修改（约 1254 行）

```python
    async def _systemone_inner(request: Request, enqueue_time: float):
```

##### E. `_systemone_inner` 推理门内新增检查（在 `async with gate:` 块内，`run_in_executor` 之前）

在 `serve.py:1306` 处 `async with gate:` 之后、`loop = asyncio.get_running_loop()` 之前插入：

```python
            async with gate:
                # === 新增：僵尸请求检测 ===
                # 检查 1：客户端是否已断开
                if await request.is_disconnected():
                    global zombie_skipped_disconnected
                    zombie_skipped_disconnected += 1
                    _log.info("Skipping zombie request: client disconnected before inference")
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=499,
                        content={"detail": "client closed request"},
                        headers={"X-Zombie-Skipped": "disconnected"}
                    )

                # 检查 2：排队寿命是否超限（TTL = 205s）
                wait_time = time.monotonic() - enqueue_time
                if wait_time > 205.0:
                    global zombie_skipped_expired
                    zombie_skipped_expired += 1
                    _log.warning(
                        "Skipping zombie request: waited %.1fs (limit 205s)",
                        wait_time
                    )
                    from fastapi.responses import JSONResponse
                    avg_ms = _avg_inference_time_ms()
                    retry_after = _compute_retry_after(avg_ms)
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "request ttl exceeded, try again later"},
                        headers={
                            "Retry-After": str(retry_after),
                            "X-Zombie-Skipped": "expired",
                        }
                    )
                # === 僵尸检测结束 ===

                loop = asyncio.get_running_loop()
                t0 = time.perf_counter()
                # ... 原有推理代码 ...
                result = await loop.run_in_executor(pool, _run_inference, run)
                infer_ms = (time.perf_counter() - t0) * 1000.0

                # 记录推理时间用于滑动窗口
                _record_inference_time(infer_ms)

                # 后置检查：推理完成后再次检查客户端是否已断开
                if await request.is_disconnected():
                    global zombie_executed_counter
                    zombie_executed_counter += 1
                    _log.warning(
                        "Client disconnected during inference (wasted %.1fs, zombie executed)",
                        infer_ms / 1000.0
                    )
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=499,
                        content={"detail": "client disconnected during inference"},
                        headers={"X-Zombie-Executed": "true"}
                    )
                # 推理已完成，返回结果（不阻塞锁释放）
```

##### F. `_systemone_batch` 端点修改（约 1345-1349 行）

```python
    @app.post("/v1/systemone/batch")
    async def systemone_batch(request: Request, authorization: Optional[str] = Header(default=None)):
        _check_auth(authorization)
        enqueue_time = time.monotonic()
        async with _admit():
            return await _systemone_batch_inner(request, enqueue_time)
```

##### G. `_systemone_batch_inner` 签名修改（约 1351 行）

```python
    async def _systemone_batch_inner(request: Request, enqueue_time: float):
```

##### H. `_systemone_batch_inner` 推理门内新增检查（约 1436 行）

在 `async with gate:` 块内、`loop = asyncio.get_running_loop()` 之前插入与单请求版本相同的僵尸检测逻辑，但日志使用 "batch request" 关键词，计数器使用同一组全局变量。

##### I. `DEFAULT_MAX_CONCURRENT` 修改

```python
# 原代码 (serve.py:137):
DEFAULT_MAX_CONCURRENT = 16

# 新代码:
DEFAULT_MAX_CONCURRENT = 10
```

#### 1.4 需要修改的现有代码（汇总）

| 位置 | 原代码 | 新代码 |
|------|--------|--------|
| `serve.py:137` | `DEFAULT_MAX_CONCURRENT = 16` | `DEFAULT_MAX_CONCURRENT = 10` |
| `serve.py:1240-1241` | `headers={"Retry-After": "1"}` | 动态计算 + 排队信息响应头（见 1.3 B） |
| `serve.py:1251-1252` | `return await _systemone_inner(request)` | `enqueue_time` + 传参（见 1.3 C） |
| `serve.py:1254` | `async def _systemone_inner(request: Request):` | 新增 `enqueue_time: float` 参数 |
| `serve.py:1306-1314` | `async with gate:` 后直接 `run_in_executor` | 新增僵尸检测 + TTL 检查 + 时间记录（见 1.3 E） |
| `serve.py:1348-1349` | `return await _systemone_batch_inner(request)` | `enqueue_time` + 传参（见 1.3 F） |
| `serve.py:1351` | `async def _systemone_batch_inner(request: Request):` | 新增 `enqueue_time: float` 参数 |
| `serve.py:1436-1457` | batch 推理门后直接 `run_in_executor` | 新增僵尸检测 + TTL 检查（见 1.3 H） |

#### 1.5 不需要删除的旧代码

阶段一**不删除**任何现有代码，仅在现有代码中插入检查。这是为了最小化回滚风险。

---

### 2. 实施步骤（严格按顺序）

#### 步骤 1：备份（5 分钟）

```powershell
# 备份当前 serve.py
Copy-Item "D:\laya\.venv\Lib\site-packages\laya\serve.py" `
          "D:\laya\.venv\Lib\site-packages\laya\serve.py.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
```

**验证：** `Test-Path` 确认备份文件存在且大小与原文件一致（约 80 KB）。

#### 步骤 2：修改 `DEFAULT_MAX_CONCURRENT`（2 分钟）

- 文件：`serve.py`，第 137 行
- `DEFAULT_MAX_CONCURRENT = 16` -> `DEFAULT_MAX_CONCURRENT = 10`

**验证：** `python -c "from laya.serve import DEFAULT_MAX_CONCURRENT; assert DEFAULT_MAX_CONCURRENT == 10"`

#### 步骤 3：新增辅助函数和计数器（10 分钟）

在文件顶部 `DEFAULT_MAX_CONCURRENT` 之后添加：
1. `import random`（如 `import threading` 已存在则跳过）
2. `_inference_times` 列表 + `_inference_times_lock`
3. `_record_inference_time(ms)` 函数
4. `_avg_inference_time_ms()` 函数
5. `_compute_retry_after(avg_infer_ms)` 函数
6. 僵尸请求计数器变量

**验证：** 启动服务后发送几个请求，确认计数器无语法错误。

#### 步骤 4：修改 `_admit()` 上下文管理器（10 分钟）

- 替换原有的 `Retry-After: "1"` 为动态计算
- 添加 503 响应时携带的排队信息响应头

**验证：** `curl -I` 连续发 11 个请求，第 11 个应返回 503 且包含动态 `Retry-After`。

#### 步骤 5：为 `_systemone` 和 `_systemone_batch` 添加 `enqueue_time`（5 分钟）

- 在 `@app.post` 装饰器后的函数体内，`async with _admit():` 之前记录 `enqueue_time`
- 将 `enqueue_time` 传递给 `_systemone_inner` 和 `_systemone_batch_inner`
- 修改这两个函数的签名

**验证：** 在推理门前 `print(f"wait={time.monotonic() - enqueue_time:.1f}s")` 确认。

#### 步骤 6：修改 `_systemone_inner` 推理门（15 分钟）

- 在 `async with gate:` 块内，`run_in_executor` 之前插入：
  - 客户端断开检查（返回 499）
  - TTL 超期检查（> 205s，返回 503 + Retry-After）
- 在 `run_in_executor` 之后插入：
  - `_record_inference_time(infer_ms)` 调用
  - 推理后断开检查（记录 `zombie_executed_counter`）

**注意：** 计数器变量定义在模块顶层（第 138 行之后），因此在 `async` 函数中必须使用 `global` 声明（而非 `nonlocal`），否则会产生 `SyntaxError`。

#### 步骤 7：修改 `_systemone_batch_inner` 推理门（15 分钟）

- 同步骤 6 的修改，应用于 batch 端点
- 日志关键词改为 "batch request"

#### 步骤 8：启动服务并运行冒烟测试（10 分钟）

```powershell
# 启动服务（Windows PowerShell 语法）
cd D:\laya
Start-Process python -ArgumentList "serve_with_log.py" -NoNewWindow

# 等待服务启动
Start-Sleep -Seconds 5

# 冒烟测试 - 正常推理请求
$response = Invoke-WebRequest -Uri "http://localhost:8000/v1/systemone" `
    -Method POST `
    -ContentType "application/json" `
    -Body '{"questions": {"q1": {"type": "choice", "instructions": "test", "criteria": ["a","b"]}}, "state": "test state"}' `
    -UseBasicParsing
Write-Host "Status: $($response.StatusCode)"

# 并发压力测试：11 个请求同时到达
$jobs = @()
for ($i = 0; $i -lt 11; $i++) {
    $jobs += Start-Job -ScriptBlock {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:8000/v1/systemone" `
                -Method POST `
                -ContentType "application/json" `
                -Body '{"questions": {"q1": {"type": "choice", "instructions": "test", "criteria": ["a","b"]}}, "state": "test"}' `
                -UseBasicParsing
            return $resp.StatusCode
        } catch {
            return $_.Exception.Response.StatusCode.value__
        }
    }
}

# 收集结果
$jobs | Wait-Job | Receive-Job
# 预期：10 个 200，1 个 503
```

#### 步骤 9：验证日志和指标（5 分钟）

- 检查 `decision-log.jsonl` 中是否有新的 `error_class` 记录
- 检查 `laya-serve.log` 中是否有 "Skipping zombie request" 日志
- 确认 503 响应包含 `Retry-After`、`X-Queue-Depth` 等响应头

---

### 3. 测试计划

#### 3.1 单元测试用例

```python
"""阶段一优化：僵尸检测 + 准入调整的单元测试"""

import time
import random
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# === 测试动态 Retry-After ===

class TestComputeRetryAfter:
    def test_default_no_data(self):
        """无历史数据时使用 17s 基线"""
        result = _compute_retry_after(None)
        assert 10 <= result <= 21  # 17 * 0.6 ~ 17 * 1.2

    def test_with_avg_17s(self):
        """平均 17s 时重试间隔 ~10-20s"""
        result = _compute_retry_after(17000.0)
        assert 10 <= result <= 21

    def test_with_avg_10s(self):
        """平均 10s 时重试间隔 ~6-12s"""
        result = _compute_retry_after(10000.0)
        assert 6 <= result <= 13

    def test_with_avg_25s(self):
        """平均 25s 时重试间隔 ~15-30s"""
        result = _compute_retry_after(25000.0)
        assert 15 <= result <= 31

    def test_jitter_prevents_thundering_herd(self):
        """随机抖动确保重试时间不集中"""
        times = [_compute_retry_after(17000.0) for _ in range(100)]
        unique = len(set(times))
        assert unique > 3  # 至少应有 4 种不同的重试时间

# === 测试滑动窗口推理时间追踪 ===

class TestInferenceTimeTracking:
    def setup_method(self):
        _inference_times.clear()

    def test_record_single(self):
        _record_inference_time(15000.0)
        assert _avg_inference_time_ms() == 15000.0

    def test_record_multiple(self):
        _record_inference_time(10000.0)
        _record_inference_time(20000.0)
        assert _avg_inference_time_ms() == 15000.0

    def test_window_limit_100(self):
        for i in range(150):
            _record_inference_time(float(i))
        assert len(_inference_times) == 100
        # 应保留最后 100 个（50-149）
        assert _inference_times[0] == 50.0

    def test_empty_returns_none(self):
        assert _avg_inference_time_ms() is None

# === 测试准入队列容量 ===

class TestAdmissionQueue:
    @pytest.mark.asyncio
    async def test_max_concurrent_is_10(self):
        assert DEFAULT_MAX_CONCURRENT == 10

    @pytest.mark.asyncio
    async def test_11th_request_rejected(self):
        """第 11 个请求应被立即拒绝（503）"""
        # 使用 mock 模拟 10 个请求正在推理
        # 第 11 个应获得 503 + Retry-After + 排队信息响应头
        pass

    @pytest.mark.asyncio
    async def test_503_has_correct_headers(self):
        """503 响应包含正确的响应头"""
        # 验证 Retry-After 在 10-21s 范围内
        # 验证 X-Queue-Depth = 10
        # 验证 X-Estimated-Wait-Time = 170
        # 验证 X-Queue-Slots-Available = 0
        pass

# === 测试僵尸请求检测 ===

class TestZombieDetection:
    @pytest.mark.asyncio
    async def test_disconnected_before_inference(self):
        """推理前检测到客户端断开应跳过推理"""
        mock_request = AsyncMock()
        mock_request.is_disconnected.return_value = True

        # 应返回 499 且不执行 run_in_executor
        pass

    @pytest.mark.asyncio
    async def test_expired_ttl_before_inference(self):
        """排队超过 205s 应跳过推理"""
        enqueue_time = time.monotonic() - 210  # 210s 前入队

        # 应返回 503 + Retry-After
        pass

    @pytest.mark.asyncio
    async def test_disconnected_during_inference(self):
        """推理完成后检测到客户端断开应记录但不阻塞"""
        # 推理已完成，但客户端已断开
        # 应记录 zombie_executed_counter + warning 日志
        # 但仍返回结果（避免锁竞争）
        pass

    @pytest.mark.asyncio
    async def test_ttl_boundary_205s(self):
        """205s 边界：204s 不应被杀，206s 应被杀"""
        # 204s -> 正常处理
        # 205.1s -> 跳过
        pass

# === 集成测试 ===

class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_request_lifecycle(self):
        """完整请求生命周期：入队 -> 等待 -> 推理 -> 响应"""
        pass

    @pytest.mark.asyncio
    async def test_concurrent_10_succeeds(self):
        """10 个并发请求应全部成功（200）"""
        pass

    @pytest.mark.asyncio
    async def test_concurrent_15_rejects_5(self):
        """15 个并发请求应拒绝 5 个（503）"""
        pass
```

#### 3.2 集成测试场景

| 场景 | 操作 | 预期结果 |
|------|------|---------|
| A. 正常单请求 | 发送 1 个推理请求 | 200，推理时间 ~17s |
| B. 满载 | 同时发送 10 个请求 | 10 个 200 |
| C. 超载 | 同时发送 15 个请求 | 10 个 200，5 个 503（含 Retry-After） |
| D. 客户端断开 | 发送请求后 2s 断开连接 | 服务端检测到 499，不执行推理 |
| E. TTL 超期 | 模拟请求在队列中等待 210s | 服务端返回 503，跳过推理 |
| F. 推理中断开 | 发送请求，推理完成后客户端断开 | 记录 zombie_executed，返回结果 |
| G. 滚动升级 | 服务重启后连续发请求 | 首个请求可能较慢（checkpoint 加载），后续正常 |
| H. 混合单/batch | 同时发送单请求和 batch 请求 | 两者都被正确准入/拒绝 |

#### 3.3 压力测试方法

```powershell
# 使用 PowerShell 并发压力测试
$port = 8000  # 替换为实际端口
$endpoint = "http://localhost:$port/v1/systemone"
$body = '{"questions": {"q1": {"type": "choice"}}, "state": "test"}'

# 发送 30 个请求，期望 10 成功 + 20 被拒
$jobs = 1..30 | ForEach-Object {
    Start-Job -ScriptBlock {
        param($url, $body, $i)
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            $resp = Invoke-WebRequest -Uri $url -Method POST `
                -ContentType "application/json" -Body $body `
                -TimeoutSec 240
            $sw.Stop()
            [PSCustomObject]@{
                Index = $i
                Status = $resp.StatusCode
                TimeMs = $sw.ElapsedMilliseconds
                RetryAfter = $resp.Headers["Retry-After"]
                QueueDepth = $resp.Headers["X-Queue-Depth"]
            }
        } catch {
            $sw.Stop()
            [PSCustomObject]@{
                Index = $i
                Status = $_.Exception.Response.StatusCode.value__
                TimeMs = $sw.ElapsedMilliseconds
                RetryAfter = $_.Exception.Response.Headers["Retry-After"]
            }
        }
    } -ArgumentList $endpoint, $body, $_
}

# 等待全部完成
$jobs | Wait-Job | Receive-Job | Format-Table -AutoSize
```

**预期结果：**
- 成功请求（200）：~10 个，推理时间 ~17s
- 被拒请求（503）：~20 个，耗时 < 50ms
- Retry-After 值：10-21s 范围内

---

### 4. 回滚方案

#### 4.1 快速恢复步骤

```powershell
# 1. 停止服务
Get-Process python | Where-Object { $_.Path -like "*laya*" } | Stop-Process -Force

# 2. 恢复备份
$backup = Get-ChildItem "D:\laya\.venv\Lib\site-packages\laya\serve.py.bak.*" |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item $backup.FullName "D:\laya\.venv\Lib\site-packages\laya\serve.py" -Force

# 3. 重启服务
cd D:\laya
python serve_with_log.py
```

#### 4.2 需要备份的文件

| 文件 | 备份路径 | 大小预估 |
|------|---------|---------|
| `laya/serve.py` | `serve.py.bak.YYYYMMDD-HHMMSS` | ~80 KB |

#### 4.3 环境变量回滚

如果修改了 `start-laya-serve.ps1` 中的 `LAYA_MAX_CONCURRENT`：

```powershell
# 恢复为原值
$env:LAYA_MAX_CONCURRENT = '16'
```

#### 4.4 回滚验证

```powershell
# 确认已回滚
python -c "from laya.serve import DEFAULT_MAX_CONCURRENT; print(DEFAULT_MAX_CONCURRENT)"
# 应输出 16（回滚后）
```

---

### 5. 阶段一验收标准

- [ ] `DEFAULT_MAX_CONCURRENT == 10`
- [ ] 11 个并发请求中第 11 个返回 503 且 `Retry-After` 在 10-21s 范围内
- [ ] 503 响应包含 `X-Queue-Depth`、`X-Estimated-Wait-Time`、`X-Queue-Slots-Available`
- [ ] 模拟客户端断开后，服务端跳过推理（日志含 "Skipping zombie request"）
- [ ] 模拟排队 210s 的请求，服务端跳过推理并返回 503
- [ ] 推理完成后客户端断开，日志含 "zombie executed" warning
- [ ] 正常请求的 `X-Inference-Time-Ms` 响应头正常返回
- [ ] `zombie_executed_counter` 在 100 个请求中 < 1
- [ ] 回滚测试：恢复备份后服务正常启动

---

### 6. 阶段一风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `request.is_disconnected()` 在某些 HTTP 版本下行为不一致 | 低 | 中 | 保留后置检查作为兜底 |
| TTL 205s 在极端负载下仍可能超时 | 中 | 低 | 可下调至 180s |
| 滑动窗口占用少量内存 | 极低 | 极低 | 100 个 float ~ 800 bytes |
| 计数器变量在重启后归零 | 确定 | 低 | 仅用于运行时监控，持久化通过 decision-log |
| batch 请求的 TTL 检查与单请求不一致 | 低 | 中 | 使用相同的 205s 阈值和逻辑 |
| `global` 声明遗漏导致计数器不更新 | 低 | 中 | 实施后运行 `python -m py_compile` 语法检查 |

---

### 7. 阶段一实施时间线

| 步骤 | 预估时间 | 累计 |
|------|---------|------|
| 1. 备份 | 5 分钟 | 5 分钟 |
| 2. 修改 DEFAULT_MAX_CONCURRENT | 2 分钟 | 7 分钟 |
| 3. 新增辅助函数 | 10 分钟 | 17 分钟 |
| 4. 修改 _admit() | 10 分钟 | 27 分钟 |
| 5. 添加 enqueue_time | 5 分钟 | 32 分钟 |
| 6. 修改 _systemone_inner | 15 分钟 | 47 分钟 |
| 7. 修改 _systemone_batch_inner | 15 分钟 | 62 分钟 |
| 8. 冒烟测试 | 10 分钟 | 72 分钟 |
| 9. 验证日志/指标 | 5 分钟 | 77 分钟 |
| **总计** | | **~1 小时 20 分钟** |

建议预留 2 小时窗口（含意外排查时间）。

---

## 阶段二：性能优化（本月，1-2 周）

**目标：** 在 4 核 CPU / 6GB RAM 约束下，压缩单次推理耗时，提升模型缓存命中率。

**预计总工时：** ~26 小时（3.25 个工作日）
**风险等级：** 中（涉及模型加载路径变更）
**前置条件：** 阶段一全部完成且验证通过

---

### 8. 变更清单

#### 8.1 修改文件清单

| 文件 | 变更类型 | 行号范围 | 变更摘要 |
|------|---------|---------|---------|
| `laya/serve.py` (包内) | 新增 | 顶部 | `CheckpointCache` 类 + 全局缓存实例 |
| `laya/serve.py` (包内) | 修改 | Router 加载/卸载逻辑 | 集成 CheckpointCache.get() 替代直接 torch.load |
| `laya/serve.py` (包内) | 修改 | 推理入口 | 包裹 `torch.inference_mode()` |
| `laya/serve.py` (包内) | 新增 | 顶部 import | `import gc`（如未存在）|
| `D:\laya\benchmarks\inference_benchmark.py` | 新增 | 新文件 | 推理加速 A/B 测试脚本 |
| `D:\laya\tests\test_checkpoint_cache.py` | 新增 | 新文件 | LRU 缓存单元测试 |

#### 8.2 新增代码

##### F4: 排队信息响应头中间件

在 `create_app()` 函数中、`DecisionLogMiddleware` 之后添加：

```python
@app.middleware("http")
async def add_queue_info_middleware(request, call_next):
    start_time = time.monotonic()
    response = await call_next(request)

    # 正常完成的请求：添加实际耗时
    if response.status_code == 200:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        response.headers["X-Total-Time-Ms"] = str(elapsed_ms)

    return response
```

##### F5: 自定义 LRU 模型缓存

```python
from collections import OrderedDict
import gc
import torch
import os


class CheckpointCache:
    """先删后载的 LRU 模型缓存，maxsize=2 确保不超出 6GB 内存。"""

    def __init__(self, maxsize: int = 2, checkpoint_dir: str = "checkpoints"):
        self.maxsize = maxsize
        self.checkpoint_dir = os.path.abspath(checkpoint_dir)
        self.cache: OrderedDict[str, object] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self._lock = threading.Lock()

    def _normalize_name(self, model_name: str) -> str:
        """归一化模型名称，防止路径遍历 (CWE-22)。"""
        # 构建绝对路径并校验
        root = self.checkpoint_dir
        full = os.path.abspath(os.path.join(root, f"{model_name.strip()}.pt"))
        # 使用 commonpath 校验，防止 startswith 绕过
        if os.path.commonpath([root, full]) != root:
            raise ValueError(f"Model name escapes checkpoint dir: {model_name}")
        # 返回不带扩展名的相对路径
        return os.path.splitext(os.path.relpath(full, root))[0]

    def get(self, model_name: str) -> object:
        model_name = self._normalize_name(model_name)

        # 整个方法体在锁内执行，防止并发穿透
        with self._lock:
            if model_name in self.cache:
                self.cache.move_to_end(model_name)
                self.hits += 1
                return self.cache[model_name]

            # Cache miss: 先删除旧模型，再加载新模型
            if len(self.cache) >= self.maxsize:
                evicted_name, evicted_model = self.cache.popitem(last=False)
                del evicted_model
                gc.collect()
                _log.info("Evicted checkpoint: %s", evicted_name)

            self.misses += 1
            start = time.perf_counter()
            checkpoint_path = os.path.join(self.checkpoint_dir, f"{model_name}.pt")
            checkpoint = torch.load(checkpoint_path, map_location="cpu")

            # 防御性检查：只有 nn.Module 实例才有 eval() 方法
            if hasattr(checkpoint, "eval"):
                checkpoint.eval()

            load_time = time.perf_counter() - start
            _log.info("Loaded checkpoint %s in %.2fs", model_name, load_time)

            self.cache[model_name] = checkpoint
            return checkpoint

    def stats(self) -> dict:
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "cached_models": list(self.cache.keys()),
                "hit_rate": self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0.0,
            }


# 全局缓存实例
checkpoint_cache = CheckpointCache(maxsize=2)
```

##### F6: 推理加速评估

**A. `torch.inference_mode()` 集成**

在 `_run_inference` 包装函数或 Router 的 `predict` / `predict_batch` 调用处包裹：

```python
# 原代码（Router.predict 或 serve.py 的推理入口）:
result = router.predict(state, questions, model=model)

# 新代码:
with torch.inference_mode():
    result = router.predict(state, questions, model=model)
```

**B. INT8 量化评估脚本**（`D:\laya\benchmarks\inference_benchmark.py`）

```python
"""推理加速 A/B 测试：baseline vs inference_mode vs INT8 vs ONNX"""

import time
import torch
import torch.nn as nn
from torch.quantization import quantize_dynamic
from pathlib import Path


def benchmark(fn, iterations=10, warmup=3):
    """基准测试函数，返回平均耗时（秒）和标准差。"""
    # Warmup
    for _ in range(warmup):
        fn()

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)

    return sum(times) / len(times), (max(times) - min(times)) / 2


def run_benchmarks(model, sample_input, checkpoint_path=None):
    """运行完整的 A/B/C/D 测试矩阵。"""
    results = {}

    # A: Baseline (no_grad)
    def baseline():
        with torch.no_grad():
            return model(sample_input)
    results["baseline_no_grad"] = benchmark(baseline)

    # B: inference_mode
    def inference_mode_fn():
        with torch.inference_mode():
            return model(sample_input)
    results["inference_mode"] = benchmark(inference_mode_fn)

    # C: INT8 dynamic quantization
    model_quant = quantize_dynamic(model, {nn.Linear}, dtype=torch.qint8)
    def quantized_fn():
        with torch.inference_mode():
            return model_quant(sample_input)
    results["int8_quantized"] = benchmark(quantized_fn)

    # D: 输出对比报告
    print("=" * 60)
    print("推理加速基准测试报告")
    print("=" * 60)
    baseline_mean = results["baseline_no_grad"][0]
    for name, (mean, std) in results.items():
        speedup = baseline_mean / mean
        print(f"{name:25s}: {mean:.3f}s (+/- {std:.3f}s) [{speedup:.2f}x]")
    print("=" * 60)

    return results


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"D:\laya\.venv\Lib\site-packages")

    # 加载模型（需根据实际模型结构调整）
    checkpoint = torch.load(r"D:\laya\checkpoints\model.pt", map_location="cpu")
    model = checkpoint
    model.eval()

    # 创建样本输入（需根据实际输入形状调整）
    sample_input = torch.randint(0, 1000, (1, 128))  # 示例: batch=1, seq_len=128

    run_benchmarks(model, sample_input)
```

**C. ONNX Runtime 评估**（同上脚本中的可选部分）

```python
def evaluate_onnx(model, sample_input, onnx_path="model.onnx"):
    """导出 ONNX 并测试 ONNX Runtime CPU 性能。"""
    import onnxruntime as ort

    # 导出 ONNX
    torch.onnx.export(
        model, sample_input, onnx_path,
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "batch", 1: "seq_len"},
                      "output": {0: "batch"}},
        opset_version=14,
    )

    # 创建 ONNX Runtime session
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    def onnx_fn():
        return session.run(None, {input_name: sample_input.numpy()})

    mean, std = benchmark(onnx_fn)
    print(f"ONNX Runtime CPU: {mean:.3f}s (+/- {std:.3f}s)")
    return mean, std
```

#### 8.3 需要修改的现有代码（汇总）

| 位置 | 原代码 | 新代码 |
|------|--------|--------|
| `serve.py:137 之后` | 无 | 新增 `CheckpointCache` 类 + `checkpoint_cache` 实例 |
| `serve.py:137 之后` | 无 | 新增 F4 排队信息中间件 |
| Router.predict 调用处 | `result = router.predict(...)` | `with torch.inference_mode(): result = ...` |
| Router.checkpoint 加载处 | `torch.load(...)` | `checkpoint_cache.get(model_name)` |

---

### 9. 实施步骤（严格按顺序）

#### 步骤 0：备份阶段一已验证版本（5 分钟）

```powershell
# 备份阶段一已验证的 serve.py（不要只依赖阶段一的备份，否则回滚会回到未修复版本）
$phase1_verified = "D:\laya\.venv\Lib\site-packages\laya\serve.py.bak.phase1_verified"
Copy-Item "D:\laya\.venv\Lib\site-packages\laya\serve.py" $phase1_verified -Force

# 同时备份到 .venv 之外的安全位置（防止 pip install 覆盖 site-packages）
New-Item -ItemType Directory -Force -Path "D:\laya\backups" | Out-Null
Copy-Item "D:\laya\.venv\Lib\site-packages\laya\serve.py" "D:\laya\backups\serve.py.phase1_verified.$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Force
```

**验证：** `Test-Path $phase1_verified` 返回 `True`。

#### 步骤 1：F4 排队信息响应头（2 小时）

1. 在 `create_app()` 中添加 `add_queue_info_middleware`
2. 确保 200 响应携带 `X-Total-Time-Ms`
3. 确保 503 响应携带 `X-Queue-Depth`、`X-Estimated-Wait-Time`、`X-Queue-Slots-Available`

**验证：** 发送请求后检查响应头是否齐全。

#### 步骤 2：F5 LRU 模型缓存 -- 核心实现（4 小时）

1. 在 `serve.py` 中新增 `CheckpointCache` 类
2. 确保 `maxsize=2`，先删后载
3. 确保 `gc.collect()` 在删除后调用
4. 确保路径遍历防护

**验证：**
- 加载 3 个不同模型，确认内存中始终只有 2 个
- 检查 `checkpoint_cache.stats()` 的命中率
- 监控 RSS 内存不超过 5.2GB

#### 步骤 3：F5 集成到 Router 加载路径（4 小时）

1. 修改 Router 的 `_load_model` 或等效函数，使用 `checkpoint_cache.get()` 替代 `torch.load()`
2. **重要：`router.unload()` 不得清理 `checkpoint_cache`** -- 模型生命周期由 LRU 缓存托管，仅在进程退出或显式管理指令时才清空缓存
3. 添加缓存命中/未命中日志

**验证：** 正常推理请求返回结果，且命中时跳过磁盘 I/O。连续 3 次请求相同模型，后 2 次应命中缓存。

#### 步骤 4：F6 `torch.inference_mode()` 集成（2 小时）

1. 在 Router 的 `predict` 和 `predict_batch` 调用处包裹 `torch.inference_mode()`
2. 确认 `torch.no_grad()` 被替换或合并

**验证：** 推理时间较 baseline 下降 5-10%。

#### 步骤 5：F6 INT8 量化评估（6 小时）

1. 编写 `inference_benchmark.py` 脚本
2. 在开发环境中运行 baseline vs INT8 对比
3. 验证量化后模型输出精度损失 < 1%
4. 评估是否启用

**验证：**
- 精度对比测试（100 个样本，正确率差异 < 1%）
- 推理时间对比（预期 30-50% 提升）
- 内存占用对比

#### 步骤 6：F6 ONNX Runtime 评估（4 小时）

1. 导出模型为 ONNX 格式
2. 使用 ONNX Runtime CPU provider 推理
3. 与 PyTorch baseline 对比

**验证：**
- 输出精度对比
- 推理时间对比（预期 40-60% 提升）
- 导出兼容性（算子支持）

#### 步骤 7：F6 最终方案选定和集成（2 小时）

根据步骤 5-6 的评估结果，选择最优方案集成到生产代码。

**验证：** 生产环境端到端测试通过。

#### 步骤 8：完整测试和验收（2 小时）

运行阶段二全部测试用例。

---

### 10. 阶段二测试计划

#### 10.1 单元测试

##### F5: CheckpointCache 测试

```python
"""测试 LRU 模型缓存"""

import gc
import pytest
import torch
from unittest.mock import patch, MagicMock
from laya.serve import CheckpointCache


class TestCheckpointCache:
    def setup_method(self):
        self.cache = CheckpointCache(maxsize=2, checkpoint_dir="/tmp/test_checkpoints")

    def test_cache_miss_loads_model(self):
        """未命中时应加载模型"""
        mock_model = MagicMock()
        with patch("torch.load", return_value=mock_model):
            result = self.cache.get("model_a")
            assert result is mock_model
            assert self.cache.misses == 1

    def test_cache_hit_returns_same_object(self):
        """命中时应返回同一对象"""
        mock_model = MagicMock()
        with patch("torch.load", return_value=mock_model):
            self.cache.get("model_a")
            result = self.cache.get("model_a")
            assert result is mock_model
            assert self.cache.hits == 1

    def test_eviction_when_full(self):
        """缓存满时应先删后载"""
        with patch("torch.load") as mock_load:
            mock_load.side_effect = [MagicMock(name="a"), MagicMock(name="b"), MagicMock(name="c")]
            self.cache.get("model_a")
            self.cache.get("model_b")
            # 加载第 3 个模型时，应驱逐 model_a
            self.cache.get("model_c")
            assert "model_a" not in self.cache.cache
            assert "model_b" in self.cache.cache
            assert "model_c" in self.cache.cache
            assert len(self.cache.cache) == 2

    def test_lru_order_on_access(self):
        """访问应将模型移到最近使用位置"""
        with patch("torch.load") as mock_load:
            mock_load.side_effect = [MagicMock(name="a"), MagicMock(name="b")]
            self.cache.get("model_a")
            self.cache.get("model_b")
            # 再次访问 model_a，使其成为最近使用
            self.cache.get("model_a")
            # 加载第 3 个模型，应驱逐 model_b（LRU）
            mock_load.return_value = MagicMock(name="c")
            self.cache.get("model_c")
            assert "model_b" not in self.cache.cache

    def test_maxsize_2_memory_safety(self):
        """maxsize=2 确保不加载超过 2 个模型"""
        with patch("torch.load") as mock_load:
            models = [MagicMock(name=f"m{i}") for i in range(5)]
            mock_load.side_effect = models
            for i in range(5):
                self.cache.get(f"model_{i}")
            assert len(self.cache.cache) <= 2

    def test_path_traversal_protection(self):
        """路径遍历攻击应被拒绝"""
        with pytest.raises(ValueError):
            self.cache.get("../../etc/passwd")

    def test_eval_called_on_load(self):
        """加载模型后应调用 eval()"""
        mock_model = MagicMock()
        with patch("torch.load", return_value=mock_model):
            self.cache.get("model_a")
            mock_model.eval.assert_called_once()

    def test_stats_returns_correct_counts(self):
        """stats() 应返回正确的命中/未命中统计"""
        mock_model = MagicMock()
        with patch("torch.load", return_value=mock_model):
            self.cache.get("model_a")  # miss
            self.cache.get("model_a")  # hit
            self.cache.get("model_b")  # miss (evicts model_a)
            stats = self.cache.stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 2
            assert stats["hit_rate"] == 1.0 / 3.0
```

##### F6: 推理加速测试

```python
"""测试推理加速效果"""

import torch
import time
import pytest


class TestInferenceMode:
    def test_inference_mode_faster_than_no_grad(self):
        """inference_mode() 应比 no_grad() 更快"""
        model = torch.nn.Linear(128, 64)
        x = torch.randn(32, 128)

        # no_grad
        start = time.perf_counter()
        for _ in range(10):
            with torch.no_grad():
                model(x)
        no_grad_time = time.perf_counter() - start

        # inference_mode
        start = time.perf_counter()
        for _ in range(10):
            with torch.inference_mode():
                model(x)
        inf_mode_time = time.perf_counter() - start

        # inference_mode 应至少一样快，通常更快
        assert inf_mode_time <= no_grad_time * 1.1  # 允许 10% 噪声
```

#### 10.2 集成测试场景

| 场景 | 操作 | 预期结果 |
|------|------|---------|
| A. 缓存命中 | 连续请求同一模型的 2 个 checkpoint | 第 2 次跳过磁盘 I/O，耗时显著降低 |
| B. 缓存驱逐 | 请求第 3 个不同 checkpoint | 驱逐最旧的，内存中保持 2 个 |
| C. INT8 量化 | 运行量化模型 100 次 | 输出精度损失 < 1% |
| D. ONNX Runtime | 导出 ONNX 并推理 | 结果与 PyTorch 一致 |
| E. 内存安全 | 加载 10 个不同模型 | RSS 内存始终 < 5.2GB |
| F. 推理加速 | 运行 benchmark 脚本 | inference_mode 较 baseline 快 5%+ |

#### 10.3 压力测试

```powershell
# 阶段二压力测试：缓存命中率 + 内存监控
$port = 8000
$endpoint = "http://localhost:$port/v1/systemone"
$models = @("model_a", "model_b", "model_c")

# 循环请求不同模型，触发缓存驱逐
for ($i = 0; $i -lt 30; $i++) {
    $model = $models[$i % 3]
    $body = "{`"questions`": {`"q1`": {`"type`": `"choice`"}}, `"state`": `"test`", `"model`": `"$model`"}"
    Invoke-WebRequest -Uri $endpoint -Method POST -ContentType "application/json" -Body $body
}

# 检查内存使用
$process = Get-Process python | Where-Object { $_.Path -like "*laya*" }
Write-Host "RSS Memory: $($process.WorkingSet64 / 1MB) MB"
```

---

### 11. 阶段二验收标准

- [ ] P50 推理耗时 < 10s（较 baseline 17s 提升 40%+）
- [ ] P95 推理耗时 < 15s
- [ ] Checkpoint 缓存命中率 > 50%（在常见双模型轮询场景下）
- [ ] RSS 内存峰值 < 5.2GB（安全，< 6GB）
- [ ] INT8 量化精度损失 < 1%（如启用）
- [ ] ONNX Runtime 输出与 PyTorch 一致（如启用）
- [ ] `torch.inference_mode()` 已在推理入口启用
- [ ] F4 排队信息响应头在所有响应中正确返回

---

### 12. 阶段二风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `torch.inference_mode()` 不兼容某些算子 | 低 | 中 | 回退到 `torch.no_grad()` |
| INT8 量化精度损失 > 1% | 中 | 高 | 离线验证后决定是否启用 |
| ONNX 导出算子不支持 | 中 | 高 | 仅作为备选方案 |
| LRU 缓存驱逐时 GC 不足 | 低 | 高 | `gc.collect()` 后验证内存释放 |
| 缓存加载路径与现有 Router 不兼容 | 中 | 高 | 充分集成测试 |
| F4 中间件增加响应延迟 | 极低 | 低 | 中间件仅添加 header，开销 < 1ms |

---

### 13. 阶段二实施时间线

| 步骤 | 预估时间 | 累计 |
|------|---------|------|
| 1. F4 排队信息响应头 | 2h | 2h |
| 2. F5 LRU 缓存核心实现 | 4h | 6h |
| 3. F5 集成到 Router 加载路径 | 4h | 10h |
| 4. F6 inference_mode 集成 | 2h | 12h |
| 5. F6 INT8 量化评估 | 6h | 18h |
| 6. F6 ONNX Runtime 评估 | 4h | 22h |
| 7. F6 最终方案选定和集成 | 2h | 24h |
| 8. 完整测试和验收 | 2h | 26h |
| **总计** | | **~26 小时（3.25 个工作日）** |

建议预留 1.5 周窗口（含意外排查时间）。

---

### 14. 阶段二回滚方案

#### 14.1 回滚步骤

```powershell
# 1. 停止服务
Get-Process python | Where-Object { $_.Path -like "*laya*" } | Stop-Process -Force

# 2. 恢复备份
$backup = Get-ChildItem "D:\laya\.venv\Lib\site-packages\laya\serve.py.bak.*" |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item $backup.FullName "D:\laya\.venv\Lib\site-packages\laya\serve.py" -Force

# 3. 重启服务
cd D:\laya
python serve_with_log.py
```

#### 14.2 回滚验证

```powershell
# 确认缓存已移除
python -c "from laya.serve import checkpoint_cache; print('cache still present')" 2>$null
# 如果 import 失败，说明代码已回滚

# 确认推理功能正常
curl http://localhost:<port>/health
```

---

## 阶段三：长期演进（下季度，1-2 月）

**目标：** 解耦 HTTP 连接与推理执行，支持水平扩展和 GPU 加速。

**预计总工时：** ~80-120 小时（2-3 周）
**风险等级：** 高（架构级变更）
**前置条件：** 阶段二全部完成且推理加速方案已选定

---

### 15. 架构设计

#### 15.1 异步任务队列架构

```
                    ┌─────────────────────────────────────┐
                    │         Client (HTTP)               │
                    └──────────────┬──────────────────────┘
                                   │ POST /v1/systemone
                                   ▼
                    ┌─────────────────────────────────────┐
                    │      API Gateway (FastAPI)           │
                    │  - 认证 + 准入控制                   │
                    │  - 创建任务 -> 返回 task_id          │
                    │  - GET /tasks/{id} -> 轮询结果       │
                    └──────────────┬──────────────────────┘
                                   │ 任务入队
                                   ▼
                    ┌─────────────────────────────────────┐
                    │       Task Queue (Redis)             │
                    │  - 持久化任务                        │
                    │  - 优先级队列                        │
                    │  - 死信队列 (DLQ)                    │
                    └──────────────┬──────────────────────┘
                                   │ 任务出队
                                   ▼
                    ┌─────────────────────────────────────┐
                    │      Worker Pool (独立进程)           │
                    │  - 多 worker 并行推理                │
                    │  - 支持 GPU (CUDA)                   │
                    │  - 自动扩缩容                        │
                    │  - 健康检查 + 故障恢复               │
                    └──────────────┬──────────────────────┘
                                   │ 结果存储
                                   ▼
                    ┌─────────────────────────────────────┐
                    │      Result Store (Redis)            │
                    │  - 任务状态 (pending/running/done)   │
                    │  - 结果缓存 (TTL 1h)                 │
                    └─────────────────────────────────────┘
```

#### 15.2 数据流

```
1. Client POST /v1/systemone -> API Gateway
2. API Gateway 创建任务记录 {task_id, status: "pending", created_at}
3. 返回 task_id 给 Client (HTTP 202 Accepted)
4. 任务入队到 Redis
5. Worker 从队列获取任务
6. Worker 执行推理，更新状态为 "running"
7. Worker 完成推理，更新状态为 "done"，存储结果
8. Client GET /tasks/{task_id} -> 返回结果
9. Client 可选 WebSocket / SSE 接收结果推送
```

#### 15.3 任务状态机

```
         ┌──────┐
         │ NEW  │
         └──┬───┘
            │ enqueue
            ▼
      ┌───────────┐
      │  PENDING  │◄── 重试
      └─────┬─────┘
            │ dequeue by worker
            ▼
      ┌───────────┐
      │  RUNNING  │
      └─────┬─────┘
            │
     ┌──────┼──────┐
     ▼      ▼      ▼
  ┌────┐ ┌────┐ ┌──────┐
  │DONE│ │FAIL│ │CANCEL│
  └────┘ └────┘ └──────┘
```

---

### 16. 技术选型

#### 16.1 消息队列选型

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **Redis (RQ / Celery)** | 轻量、易部署、Windows 友好 | 无原生持久化、单节点瓶颈 | 中小型部署（推荐） |
| RabbitMQ | 高可靠、消息持久化、集群 | 部署复杂、Windows 支持弱 | 高可用企业部署 |
| Apache Kafka | 高吞吐、分区扩展 | 运维复杂、资源需求高 | 大规模多租户 |
| PostgreSQL LISTEN/NOTIFY | 已有数据库、零额外依赖 | 性能瓶颈、非专业队列 | 最小化部署 |

**推荐：Redis + Celery**（部署简单、生态成熟）

> **⚠️ Windows 兼容性警告：** Celery 自 4.0 起已停止对原生 Windows 的官方支持。其默认的 `prefork` 进程池在 Windows 上启动 Worker 时会直接崩溃。**必须**在启动命令中指定 `--pool=solo`（单线程，最契合单 Worker 独占模型设计）或 `--pool=threads`。

#### 16.2 Worker 框架选型

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Celery** | 成熟稳定、监控工具丰富 | Python 重量级、启动慢 |
| **RQ (Redis Queue)** | 极简、轻量 | 功能较少 |
| **Ray** | 分布式、GPU 原生 | 学习曲线陡 |
| **自定义 multiprocessing** | 零依赖、可控 | 需自行实现容错 |

**推荐：Celery**（生产级、监控完善、与 Redis 无缝集成）

#### 16.3 硬件升级路径

| 升级选项 | 成本（预估） | 预期收益 | 优先级 |
|---------|------------|---------|--------|
| RAM 扩至 16GB | 低 (200-400 元) | 支持 2-3 个 worker 进程 | 立即可行 |
| GPU T4 (16GB) | 中 (3000-5000 元) | 推理时间 17s -> 1-2s，10x 吞吐 | 高 |
| GPU A10 (24GB) | 中高 (8000-12000 元) | 推理时间 17s -> <1s，支持 batch | 中 |
| 多机部署 (2-4 台) | 高 | 水平扩展、企业级可靠性 | 长期规划 |

---

### 17. 变更清单

#### 17.1 新增文件

| 文件 | 用途 |
|------|------|
| `D:\laya\api_gateway\app.py` | FastAPI API 网关（任务创建 + 结果查询） |
| `D:\laya\api_gateway\celery_app.py` | Celery 应用配置 |
| `D:\laya\api_gateway\tasks.py` | Celery 任务定义 |
| `D:\laya\worker\inference_worker.py` | 推理 Worker 进程 |
| `D:\laya\worker\celery_config.py` | Worker 配置 |
| `D:\laya\docker-compose.yml` | Docker Compose 编排 |
| `D:\laya\Dockerfile.api` | API 网关 Dockerfile |
| `D:\laya\Dockerfile.worker` | Worker Dockerfile |
| `D:\laya\redis.conf` | Redis 配置 |
| `D:\laya\benchmarks\scaling_benchmark.py` | 水平扩展压力测试 |
| `D:\laya\tests\test_task_queue.py` | 任务队列集成测试 |

#### 17.2 API 设计

##### POST /v1/systemone (同步，保留兼容)

保留现有同步接口，内部可选择走同步路径（阶段一/二代码）或异步路径。

##### POST /v1/tasks

创建异步推理任务。

**请求体：**
```json
{
  "questions": {"q1": {"type": "choice"}},
  "state": "user state string",
  "model": "model_name",
  "max_len": 4096
}
```

**响应 (HTTP 202 Accepted)：**
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "pending",
  "created_at": "2026-11-07T10:30:00.000Z",
  "estimated_wait_seconds": 17,
  "status_url": "/v1/tasks/a1b2c3d4-..."
}
```

##### GET /v1/tasks/{task_id}

查询任务状态和结果。

**响应 (进行中，HTTP 200)：**
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "running",
  "created_at": "2026-11-07T10:30:00.000Z",
  "started_at": "2026-11-07T10:30:01.000Z",
  "estimated_remaining_seconds": 15
}
```

**响应 (完成，HTTP 200)：**
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "done",
  "created_at": "2026-11-07T10:30:00.000Z",
  "started_at": "2026-11-07T10:30:01.000Z",
  "completed_at": "2026-11-07T10:30:18.000Z",
  "result": {
    "model": "model_name",
    "answers": {"q1": {"answer": "A"}},
    "usage": {"input_tokens": 128, "output_tokens": 1}
  }
}
```

**响应 (失败，HTTP 200)：**
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "failed",
  "error": "inference_failed",
  "error_detail": "model not found: unknown_model",
  "retries": 0
}
```

##### DELETE /v1/tasks/{task_id}

取消任务（仅在 pending/running 状态下有效）。

---

### 18. 实施步骤

#### 子阶段 3.1：架构搭建（第 1-2 周）

1. **部署 Redis**（4h）
   - 安装 Redis for Windows 或使用 Docker
   - 配置持久化（AOF + RDB）
   - 设置内存限制

2. **Celery 基础配置**（6h）
   - 创建 `celery_app.py`
   - 配置 Redis broker + result backend
   - 定义推理任务 `run_inference_task(task_id, body)`
   - 设置并发 worker 数（初始 1，与现有行为一致）

3. **API 网关搭建**（8h）
   - 从 `serve.py` 中拆分出路由注册逻辑
   - 实现 `POST /v1/tasks`
   - 实现 `GET /v1/tasks/{task_id}`
   - 保留现有同步端点作为兼容层

#### 子阶段 3.2：Worker 实现（第 3-4 周）

4. **推理 Worker 实现**（12h）
   - Worker 进程加载模型到内存
   - 从 Celery 队列获取任务
   - 执行推理（使用阶段二的加速方案）
   - 将结果写回 Redis
   - 处理异常和超时

5. **容错和重试**（8h）
   - 任务超时自动重试（max_retries=1）
   - Worker 崩溃自动恢复
   - 死信队列处理

6. **监控和可观测性**（8h）
   - Celery Flower 监控面板
   - Prometheus metrics 暴露
   - 结构化日志

#### 子阶段 3.3：硬件扩展（第 5-6 周）

7. **GPU 支持评估**（16h）
   - 安装 CUDA + PyTorch GPU 版本
   - 基准测试 GPU 推理性能
   - 评估 GPU vs CPU 性价比

8. **多 Worker 进程**（8h）
   - 配置多个 Celery worker
   - 测试并发推理
   - 内存管理（每个 worker 的内存隔离）

9. **水平扩展验证**（8h）
   - 多机部署测试
   - 负载均衡配置
   - 端到端压力测试

#### 子阶段 3.4：迁移和上线（第 7-8 周）

10. **灰度发布**（8h）
    - 先让 10% 流量走异步路径
    - 监控错误率和延迟
    - 逐步提高比例

11. **文档和运维手册**（8h）
    - 部署文档
    - 运维手册
    - 故障排查指南

12. **最终验收**（4h）
    - 全链路压力测试
    - 故障注入测试
    - 回滚演练

---

### 19. Docker Compose 编排

```yaml
# docker-compose.yml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes --maxmemory 512mb
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - LAYA_API_KEY=${LAYA_API_KEY}
    depends_on:
      redis:
        condition: service_healthy

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - LAYA_THREADS=${LAYA_THREADS:-4}
    depends_on:
      redis:
        condition: service_healthy
    deploy:
      replicas: 1  # 初始 1 个 worker，按需扩展

  flower:
    image: mher/flower:2.0
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - worker

volumes:
  redis-data:
```

---

### 20. 迁移路径

#### 阶段 0：现有架构（当前）

```
Client -> FastAPI -> asyncio.Lock -> ThreadPoolExecutor(1) -> 推理
```

#### 阶段 1：同步 + 异步并存（第 1-2 月）

```
Client (短连接) -> FastAPI -> 同步路径（阶段一/二代码）
Client (异步)   -> FastAPI -> Celery -> Worker -> 推理 -> Redis -> Client 轮询
```

#### 阶段 2：完全异步（第 3 月+）

```
Client -> API Gateway -> Celery -> Worker Pool (GPU) -> Redis -> Client WebSocket/SSE
```

#### 迁移步骤

1. 部署 Redis + Celery Worker，同步端点继续运行
2. 新增 `/v1/tasks` 异步端点，测试通过
3. 客户端逐步切换至异步端点
4. 确认异步路径稳定后，同步端点标记为 deprecated
5. 最终移除同步路径，完成迁移

---

### 21. 阶段三测试计划

#### 21.1 集成测试

| 场景 | 操作 | 预期结果 |
|------|------|---------|
| A. 任务创建 | POST /v1/tasks | 202 + task_id |
| B. 任务轮询 | GET /v1/tasks/{id} | pending -> running -> done |
| C. 任务取消 | DELETE /v1/tasks/{id} | 状态变为 cancelled |
| D. 并发任务 | 同时创建 20 个任务 | 全部完成，无丢失 |
| E. Worker 重启 | 重启 Worker 进程 | 未完成任务自动恢复 |
| F. Redis 故障 | 停止 Redis 后重启 | 任务不丢失（持久化） |
| G. GPU 推理 | GPU worker 处理任务 | 推理时间 < 2s |

#### 21.2 压力测试

```python
"""阶段三压力测试：水平扩展验证"""

import aiohttp
import asyncio
import time


async def create_task(session, url, body):
    async with session.post(url, json=body) as resp:
        return await resp.json()


async def poll_task(session, url, task_id, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        async with session.get(f"{url}/{task_id}") as resp:
            data = await resp.json()
            if data["status"] in ("done", "failed"):
                return data
        await asyncio.sleep(1)
    return {"status": "timeout"}


async def load_test(n_tasks=100):
    async with aiohttp.ClientSession() as session:
        # 创建任务
        start = time.time()
        tasks = []
        for i in range(n_tasks):
            body = {
                "questions": {"q1": {"type": "choice"}},
                "state": f"test state {i}",
            }
            result = await create_task(session, "http://localhost:8000/v1/tasks", body)
            tasks.append(result["task_id"])
        create_time = time.time() - start

        # 轮询结果
        start = time.time()
        results = await asyncio.gather(*[
            poll_task(session, "http://localhost:8000/v1/tasks", tid)
            for tid in tasks
        ])
        process_time = time.time() - start

        # 统计
        done = sum(1 for r in results if r.get("status") == "done")
        failed = sum(1 for r in results if r.get("status") == "failed")
        print(f"Created {n_tasks} tasks in {create_time:.2f}s")
        print(f"Completed {done} tasks in {process_time:.2f}s")
        print(f"Failed {failed} tasks")
        print(f"Throughput: {done / process_time:.2f} tasks/s")


if __name__ == "__main__":
    asyncio.run(load_test(100))
```

---

### 22. 阶段三验收标准

- [ ] 异步任务 API 全部通过集成测试
- [ ] Worker 支持 GPU 推理（如已采购 GPU）
- [ ] 100 个并发任务全部完成，丢失率 < 0.1%
- [ ] 平均任务处理时间 < 20s（CPU）或 < 3s（GPU）
- [ ] Worker 重启后未完成任务自动恢复
- [ ] Redis 故障恢复后任务不丢失
- [ ] Celery Flower 监控面板正常运行
- [ ] 灰度发布验证通过（10% -> 50% -> 100% 流量）

---

### 23. 阶段三风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Redis 单点故障 | 中 | 高 | Sentinel 或 Cluster 模式 |
| Celery worker 内存泄漏 | 低 | 中 | Worker 定期重启（max-tasks-per-child） |
| GPU 驱动兼容性 | 中 | 高 | 充分测试 + 回退到 CPU |
| 水平扩展时负载均衡不均 | 中 | 中 | 一致性哈希或最小连接策略 |
| 迁移期间 API 不兼容 | 低 | 高 | 保留同步端点作为兼容层 |
| 数据持久化丢失 | 低 | 高 | AOF + RDB 双持久化 |
| 多机部署网络延迟 | 中 | 中 | 同可用区部署，网络延迟 < 1ms |

---

### 24. 阶段三实施时间线

| 子阶段 | 内容 | 预估时间 | 累计 |
|--------|------|---------|------|
| 3.1 | 架构搭建（Redis + Celery + API 网关） | 18h | 18h |
| 3.2 | Worker 实现 + 容错 + 监控 | 28h | 46h |
| 3.3 | 硬件扩展（GPU + 多 Worker + 水平扩展） | 32h | 78h |
| 3.4 | 迁移和上线（灰度 + 文档 + 验收） | 20h | 98h |
| **总计** | | **~98 小时（~2.5 周）** | |

建议预留 1.5-2 月窗口（含 GPU 采购、运维审批等外部依赖）。

---

### 25. 阶段三回滚方案

#### 25.1 回滚步骤

```powershell
# 1. 停止所有新组件
docker-compose down

# 2. 恢复原有 serve.py（阶段一/二的版本）
$backup = Get-ChildItem "D:\laya\.venv\Lib\site-packages\laya\serve.py.bak.*" |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item $backup.FullName "D:\laya\.venv\Lib\site-packages\laya\serve.py" -Force

# 3. 重启原有服务
cd D:\laya
python serve_with_log.py

# 4. 通知客户端切回同步端点
```

---

## 整体里程碑和时间线

```
2026-11-07 (Day 0)  ── 计划审批
       │
2026-11-08 (Day 1)  ── 阶段一开始实施
       │
2026-11-09 (Day 2)  ── 阶段一完成验证 ✅
       │
2026-11-10 (Day 3)  ── 阶段二开始：F4 排队响应头 + F5 LRU 缓存
       │
2026-11-14 (Day 7)  ── F5 集成完成
       │
2026-11-17 (Day 10) ── F6 推理加速评估完成
       │
2026-11-21 (Day 14) ── 阶段二完成验证 ✅
       │
2026-11-24 ── 阶段三开始：架构搭建
       │
2026-12-05 ── Worker 实现完成
       │
2026-12-19 ── GPU 支持验证完成（如需采购 GPU）
       │
2026-12-26 ── 灰度发布完成
       │
2027-01-02 ── 阶段三完成验证 ✅
       │
       ▼
    全部完成
```

### 关键里程碑

| 里程碑 | 日期 | 依赖 |
|--------|------|------|
| M1: 阶段一完成 | 2026-11-09 | 无 |
| M2: 阶段二完成 | 2026-11-21 | M1 |
| M3: 异步 API 可用 | 2026-11-28 | M2 |
| M4: Worker 稳定运行 | 2026-12-05 | M3 |
| M5: GPU 推理验证 | 2026-12-19 | M4 + GPU 到位 |
| M6: 全部完成 | 2027-01-02 | M5 |

---

## 附录

### A. 术语表

| 术语 | 定义 |
|------|------|
| 僵尸请求 | 客户端已断开但服务端仍在处理的请求 |
| 准入层 | 控制同时进入系统的请求数量的信号量 |
| 推理门 | 确保同一时刻只有一个推理任务执行的排他锁 |
| TTL (Time To Live) | 请求在队列中的最大存活时间 |
| Retry-After | 告诉客户端何时重试的 HTTP 响应头 |
| Checkpoint | 模型权重文件，用于加载到内存进行推理 |
| 死信队列 | 无法处理的任务最终存放的队列 |

### B. 关键代码位置索引

| 文件 | 行号 | 功能 | 阶段 |
|------|------|------|------|
| `laya/serve.py` | 137 | `DEFAULT_MAX_CONCURRENT` | 阶段一 |
| `laya/serve.py` | 1079 | `ThreadPoolExecutor(max_workers=1)` | 不变 |
| `laya/serve.py` | 1230-1246 | `_admit()` 准入上下文 | 阶段一 |
| `laya/serve.py` | 1248-1252 | `/v1/systemone` 端点 | 阶段一 |
| `laya/serve.py` | 1254-1343 | `_systemone_inner` 推理 | 阶段一/二 |
| `laya/serve.py` | 1345-1349 | `/v1/systemone/batch` 端点 | 阶段一 |
| `laya/serve.py` | 1351-1477 | `_systemone_batch_inner` 推理 | 阶段一 |
| `laya/serve.py` | 1500-1506 | `uvicorn.run()` | 不变 |

### C. 配置文件清单

| 文件 | 用途 | 阶段 |
|------|------|------|
| `.env` | 环境变量（LAYA_MAX_CONCURRENT, LAYA_THREADS 等） | 阶段一 |
| `start-laya-serve.ps1` | 启动脚本 | 阶段一 |
| `redis.conf` | Redis 配置 | 阶段三 |
| `celery_config.py` | Celery Worker 配置 | 阶段三 |
| `docker-compose.yml` | Docker 编排 | 阶段三 |

### D. 监控指标汇总

| 指标 | 阶段 | 来源 | 告警阈值 |
|------|------|------|---------|
| `zombie_skipped_disconnected` | 1 | 计数器 | > 20/小时 |
| `zombie_skipped_expired` | 1 | 计数器 | 连续 > 0 |
| `zombie_executed_counter` | 1 | 计数器 | > 1% 总请求 |
| 503 率 | 1 | access log | > 60% |
| P50 推理耗时 | 1/2 | X-Inference-Time-Ms | > 15s |
| 缓存命中率 | 2 | checkpoint_cache.stats() | < 50% |
| RSS 内存 | 2 | 进程监控 | > 5.2GB |
| 任务队列深度 | 3 | Celery/Radis | > 100 |
| Worker 健康 | 3 | Celery Flower | 0 active worker |
| GPU 利用率 | 3 | nvidia-smi | < 20%（已采购时） |

### E. 修订历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v1.0 | 2026-11-07 | 初版 |
| v1.1 | 2026-11-07 | **根据工程审查修订：**<br>1. [P0] `nonlocal` 改为 `global`（模块级变量）<br>2. [P0] 推理后断连检查增加 `return JSONResponse(status_code=499)`<br>3. [Major] `_admit()` 中 `X-Estimated-Wait-Time` 使用动态均值<br>4. [Major] PowerShell 命令改为 Windows 兼容语法<br>5. [P0] `router.unload()` 不得清理 `checkpoint_cache`<br>6. [P0] `CheckpointCache` 路径校验改用 `os.path.commonpath`<br>7. [P0] `CheckpointCache.get()` 整个方法体包裹在锁内<br>8. [Minor] Celery Windows 兼容性警告（`--pool=solo`）<br>9. 阶段二增加备份步骤（步骤 0） |

---

**文档结束**
