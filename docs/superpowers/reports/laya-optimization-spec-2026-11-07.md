# Laya 服务优化规格说明书 (Specification)

**文档编号：** LAYA-OPT-2026-001  
**版本：** 1.1（根据工程审查最终修订）  
**日期：** 2026-11-07  
**状态：** 待审批

---

## 1. 概述

### 1.1 背景

Laya 是一个基于 FastAPI/uvicorn 的机器学习推理服务，部署在 4 核 CPU / 6GB RAM 的 Windows 服务器上。当前存在严重的性能问题：
- 客户端超时阈值 ~240s，但请求排队等待时间中位数 86s，尾部 288s
- 服务端成功率仅 17.1%，且包含大量"假成功"（服务端返回 200 但客户端已超时）
- 大量 CPU 算力浪费在为已断开连接的"僵尸请求"执行推理

### 1.2 目标

| 优先级 | 目标 | 量化指标 |
|--------|------|---------|
| P0 | 消除僵尸推理 | 僵尸请求比例 < 1% |
| P0 | 确保队列内请求 100% 在超时前完成 | 客户端超时断开率 < 5% |
| P1 | 提升有效吞吐量 | 真实成功率从 17% 提升至 40%+ |
| P2 | 压缩单次推理耗时 | 从 17s 降至 8-10s |

### 1.3 硬件约束

| 资源 | 规格 | 影响 |
|------|------|------|
| CPU | 4 核心 | 单次推理已满载，无法通过增加线程数提升吞吐 |
| RAM | 6 GB | 单 checkpoint ~1.15GB，最多缓存 3-4 个 |
| GPU | 无 | 纯 CPU 推理，单次耗时难以大幅压缩 |

---

## 2. 功能规格

### 2.1 F1: 僵尸请求检测与丢弃 [P0]

**描述：** 在执行推理之前，检测客户端是否已断开或请求是否已过期，若是则立即跳过推理。

**触发条件：**
- 协程已获取 `asyncio.Lock()`（serve.py:1306）
- 准备调用 `loop.run_in_executor(pool, _run_inference, run)` 之前

**检查项：**

| 检查 | 方法 | 触发条件 | 响应 |
|------|------|---------|------|
| 客户端断开 | `await request.is_disconnected()` | 返回 True | 跳过推理，返回 499 Client Closed Request |
| 排队超时 | `time.monotonic() - enqueue_time > 205` | 已等待超过 205s | 跳过推理，返回 503 + Retry-After |

**TTL 阈值推导：**
```
客户端超时: 240s
预留网络余量: 15s
单次推理耗时: 17s (P95)
执行死线: 240 - 17 - 15 = 208s ≈ 205s (取整)
```

**注意：** TTL 设为 205s 而非 180s，避免在终点线前误杀排在第 9-10 位的正常请求。

**实现位置：**
```
文件: laya/serve.py
函数: predict_handler() 或等效的推理入口
位置: async with gate: 块内，run_in_executor() 之前
```

**日志要求：**
```python
logger.info(
    "Skipping zombie request: disconnected=%s, waited=%.1fs",
    is_disconnected,
    wait_time
)
```

**指标（区分拦截与漏网）：**
- `laya_zombie_skipped_total{reason="disconnected|expired"}` - F1 成功拦截跳过的死请求
- `laya_zombie_executed_total` - 跑完推理后才发现客户端已断开的漏网之鱼
- `laya_zombie_wasted_inference_ratio` = executed / total_completed (目标 < 1%)

---

### 2.2 F2: 准入队列容量调整 [P0]

**描述：** 将 `LAYA_MAX_CONCURRENT` 从 16 下调至 10，确保所有进入队列的请求能在客户端超时前完成。

**算术推导：**
```
客户端超时阈值: 240s
安全边际: 60s (网络延迟、波动)
可用于排队时间: 180s
单次推理耗时: 17s (P95)
最大队列深度: floor(180 / 17) = 10
```

**配置变更：**
```powershell
# start-laya-serve.ps1
$env:LAYA_MAX_CONCURRENT = '10'  # 原值: 16
```

**行为规格：**

| 队列深度 | 第 N+1 个请求行为 | 响应 |
|---------|------------------|------|
| < 10 | 进入队列等待 | 正常处理 |
| = 10 | 立即拒绝 | 503 + Retry-After: ~17s |

**注意：** `Retry-After` 表示"等待下一个槽位释放"（~17s），而非"全队列排空时间"（~170s）。

**指标：**
- `layadmission_rejected_total`
- `laya_queue_depth` (gauge)
- `laya_queue_wait_time_seconds` (histogram)

---

### 2.3 F3: 动态 Retry-After 响应头 [P1]

**描述：** 当请求被拒绝时，返回动态计算的退避时间，让上游调用方按节奏重试。

**计算公式（修正版）：**
```
Retry-After = avg_inference_time * random(0.6, 1.2)  # ~10-20s，等待下一个槽位释放
```

**注意：** 这不是"全队列排空时间"，而是"下一个槽位何时可用"。避免客户端在 170s 后同时重试造成洪峰。

**实现：**
```python
import random

if admission.locked():
    avg_inference_time = get_recent_avg_inference_time()  # 滑动窗口平均
    # 单个推理周期 + 随机抖动，避免重试洪峰
    retry_after = int(avg_inference_time * random.uniform(0.6, 1.2))
    
    raise HTTPException(
        status_code=503,
        detail="Server busy",
        headers={
            "Retry-After": str(retry_after),
            "X-Queue-Depth": str(get_current_queue_depth()),
        }
    )
```

**指标：**
- `laya_avg_inference_time_seconds` (滑动窗口，最近 100 个请求)

---

### 2.4 F4: 排队信息响应头 [P2]

**描述：** 为所有响应添加排队信息，让客户端感知服务状态。

**响应头（503 拒绝时）：**

| Header | 说明 | 示例值 |
|--------|------|--------|
| `X-Queue-Depth` | 当前队列深度 | `10` |
| `X-Estimated-Wait-Time` | 预估等待时间（秒）= queue_depth * 17 | `170` |
| `X-Queue-Slots-Available` | 准入队列剩余槽位 | `0` |

**注意：** 推理槽位永远只有 1 个（排他锁），这里 `X-Queue-Slots-Available` 表示准入队列剩余槽位（10 - queue_depth）。

**响应头（正常完成时）：**

| Header | 说明 | 示例值 |
|--------|------|--------|
| `X-Queue-Wait-Time-Ms` | 实际排队等待时间（毫秒） | `85000` |
| `X-Inference-Time-Ms` | 实际推理时间（毫秒） | `17000` |

**实现位置：** FastAPI middleware

---

### 2.5 F5: LRU 模型缓存 [P2]

**描述：** 在内存中缓存 2 个常用的 checkpoint，避免每次推理都从磁盘加载。

**规格（修正版）：**
- 缓存容量：**2 个 checkpoint**（占用 ~2.3GB，安全上限）
- 淘汰策略：LRU (Least Recently Used)，**先删后载**
- 命中时：直接从内存返回，跳过磁盘 I/O
- 未命中时：**先删除旧模型并 gc.collect()，再加载新模型**

**内存预算：**
```
2 个 checkpoint: ~2.3GB
Windows 系统: ~1.5-2.0GB
Python + PyTorch 运行时: ~0.6GB
推理激活张量: ~0.3GB
总峰值: ~4.7-5.2GB (安全，< 6GB)
```

**为什么不能用 @lru_cache：**
- `lru_cache` 是"先执行后淘汰"：加载第 4 个模型时，内存中会同时存在 4 个 checkpoint (~4.6GB)
- 加上系统开销 ~2.4GB = 7.0GB，超出 6GB 物理内存，触发 OOM

**实现（自定义 OrderedDict）：**
```python
from collections import OrderedDict
import gc
import torch

class CheckpointCache:
    def __init__(self, maxsize=2):
        self.maxsize = maxsize
        self.cache = OrderedDict()
    
    def get(self, model_name):
        if model_name in self.cache:
            self.cache.move_to_end(model_name)
            return self.cache[model_name]
        
        # Cache miss: 先删除旧模型，再加载新模型（避免峰值 4 个）
        if len(self.cache) >= self.maxsize:
            evicted_name, evicted_model = self.cache.popitem(last=False)
            del evicted_model
            gc.collect()  # 显式释放物理内存
            logger.info(f"Evicted checkpoint: {evicted_name}")
        
        # 加载新模型
        start = time.perf_counter()
        checkpoint = torch.load(f"checkpoints/{model_name}.pt", map_location="cpu")
        checkpoint.eval()  # 设置为推理模式
        load_time = time.perf_counter() - start
        logger.info(f"Loaded checkpoint {model_name} in {load_time:.2f}s")
        
        self.cache[model_name] = checkpoint
        return checkpoint

# 全局缓存实例
checkpoint_cache = CheckpointCache(maxsize=2)
```

**指标：**
- `laya_checkpoint_cache_hits_total`
- `laya_checkpoint_cache_misses_total`
- `laya_checkpoint_load_time_seconds` (histogram)

---

### 2.6 F6: 推理加速 [P2]

**描述：** 评估并启用 CPU 推理加速技术。

**检查清单：**

| 技术 | 预期收益 | 实施难度 | 优先级 |
|------|---------|---------|--------|
| `torch.inference_mode()` | 5-10% | 低 | P2 |
| INT8 动态量化 | 30-50% | 中 | P2 |
| ONNX Runtime CPU | 40-60% | 中 | P2 |

**验证方法：**
```python
# A/B 测试
import torch
import time

# Baseline
start = time.perf_counter()
result = model(input)
baseline_time = time.perf_counter() - start

# With inference_mode
with torch.inference_mode():
    start = time.perf_counter()
    result = model(input)
    optimized_time = time.perf_counter() - start

print(f"Speedup: {baseline_time / optimized_time:.2f}x")
```

**指标：**
- `laya_inference_time_seconds` (histogram，按 checkpoint 分组)

---

## 3. 非功能规格

### 3.1 性能

| 指标 | 目标值 | 测量方法 |
|------|--------|---------|
| 僵尸请求漏网率 | < 1% | `laya_zombie_executed_total` / 完成请求总数 |
| 僵尸请求拦截数 | 监控即可 | `laya_zombie_skipped_total`（反映节省的算力） |
| 客户端超时断开率 | < 5% | 超时断开数 / 总请求数 |
| 准入拒绝率 | 30-50% | 拒绝数 / 总请求数（预期值，表示过载保护生效） |
| 入队请求有效完成率 | > 95% | 成功完成且客户端收到响应的入队请求 / 入队总数 |
| P50 推理耗时 | < 10s | 滑动窗口中位数 |
| P95 推理耗时 | < 15s | 滑动窗口 95 分位 |

**阶段一 vs 阶段二目标说明：**
- **阶段一**（僵尸检测 + 准入调整）：核心指标是"入队请求有效完成率 > 95%"，即进入队列的请求几乎都能成功完成
- **阶段二**（推理加速）：目标是将单次推理从 17s 压缩至 8-10s，此时"总请求成功率 > 40%"才可实现

### 3.2 可靠性

| 场景 | 预期行为 |
|------|---------|
| 客户端在推理前断开 | 跳过推理，释放锁，不记录为错误 |
| 客户端在推理中断开 | 完成推理但丢弃结果，记录为 client_disconnect |
| 队列满 | 立即返回 503，耗时 < 10ms |
| Checkpoint 加载失败 | 返回 500，记录错误日志，不加入缓存 |

### 3.3 可观测性

**日志级别：**
- INFO: 正常请求处理、僵尸请求跳过、checkpoint 缓存命中/未命中
- WARNING: 队列深度超过阈值 (> 8)、推理耗时超过 P95
- ERROR: Checkpoint 加载失败、推理异常

**指标暴露：**
- 端点：`/metrics` (Prometheus 格式)
- 刷新间隔：10s

---

## 4. 实施计划

### 4.1 阶段一：立即止血（本周）

| 任务 | 优先级 | 预计工时 | 负责人 |
|------|--------|---------|--------|
| F1: 僵尸请求检测 | P0 | 4h | - |
| F2: 准入队列容量调整 | P0 | 1h | - |
| F3: 动态 Retry-After | P1 | 2h | - |

**验收标准：**
- [ ] 僵尸请求漏网率 < 1%（跑完推理后发现客户端已断开）
- [ ] 所有进入队列的请求在 205s 内拿到推理锁
- [ ] 入队请求有效完成率 > 95%
- [ ] 客户端超时断开率 < 10%

### 4.2 阶段二：性能优化（本月）

| 任务 | 优先级 | 预计工时 | 负责人 |
|------|--------|---------|--------|
| F4: 排队信息响应头 | P2 | 2h | - |
| F5: 自定义 LRU 模型缓存 | P2 | 8h | - |
| F6: 推理加速评估 | P2 | 16h | - |

**验收标准：**
- [ ] P50 推理耗时 < 10s
- [ ] Checkpoint 缓存命中率 > 50%
- [ ] 总请求成功率 > 40%（依赖单次推理压缩至 8s 以内）

### 4.3 阶段三：长期演进（下季度）

- [ ] 异步任务队列架构设计
- [ ] 硬件升级评估（GPU / 多机）
- [ ] 水平扩展方案验证

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 僵尸检查增加延迟 | 每次推理多 ~10ms | 可接受，相比 17s 推理可忽略 |
| MAX_CONCURRENT=10 过于保守 | 可能拒绝过多请求 | 根据实际负载调整至 8-12 |
| LRU 缓存占用过多内存 | 可能导致 OOM | **限制 maxsize=2**，先删后载，监控内存使用 |
| INT8 量化影响精度 | 推理结果偏差 | 离线验证精度损失 < 1% |

---

## 6. 附录

### 6.1 关键代码位置

| 文件 | 行号 | 功能 |
|------|------|------|
| `serve.py` | 1079 | `ThreadPoolExecutor(max_workers=1)` |
| `serve.py` | 1230-1246 | 准入层 `Semaphore(16)` |
| `serve.py` | 1306 | 推理门 `asyncio.Lock()` |
| `serve.py` | 1500-1506 | `uvicorn.run()` 单 worker |

### 6.2 术语表

| 术语 | 定义 |
|------|------|
| 僵尸请求 | 客户端已断开但服务端仍在处理的请求 |
| 准入层 | 控制同时进入系统的请求数量的信号量 |
| 推理门 | 确保同一时刻只有一个推理任务执行的排他锁 |
| Checkpoint | 模型权重文件，用于加载到内存进行推理 |
| TTL (Time To Live) | 请求在队列中的最大存活时间 |
| Retry-After | 告诉客户端何时重试的 HTTP 响应头 |

### 6.3 修订历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| 1.0 | 2026-11-07 | 初版 |
| 1.1 | 2026-11-07 | **根据工程审查修订：**<br>1. F1 TTL 从 180s 放宽至 205s，避免终点线误杀<br>2. F3 Retry-After 从 `queue_depth * 17` 改为 `~17s`（下个槽位释放时间）<br>3. F5 LRU 缓存从 `maxsize=3` 改为 `maxsize=2`，且改用自定义 OrderedDict（先删后载）<br>4. 指标拆分：`zombie_skipped` vs `zombie_executed`<br>5. F4 响应头命名：`X-Inference-Slots-Available` → `X-Queue-Slots-Available`<br>6. 客户端断连统一返回 499（非 503） |

---

**文档结束**
