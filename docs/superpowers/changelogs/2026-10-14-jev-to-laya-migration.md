# Changelog: Jev → Laya 迁移（TypeSafe SDK → HTTP API）

**日期**：2026-10-14  
**commit**：待提交  
**关联审核**：专家审核通过

## 问题摘要

**背景**：原实现使用 TypeSafe SDK 调用 Jev 模型进行协变量预筛。由于 TypeSafe 服务区域限制（HTTP 451），需要迁移到自托管的 Laya 服务。

**目标**：将 `cascade/typesafe_prescreen.py` 从 TypeSafe SDK 迁移到 Laya HTTP API，保持功能不变。

## 修复内容

### 核心改动

**文件**：`cascade/typesafe_prescreen.py`

| 函数 | 修改 | 作用 |
|------|------|------|
| `_get_laya_base_url()` | **新增** | 获取 Laya 服务 URL（环境变量 `LAYA_BASE_URL` 或默认 `http://100.96.19.116:8000`） |
| `_call_typesafe()` | **重写** | 从 TypeSafe SDK 改为 HTTP API 调用 |

### 详细改动

#### 1. 新增 `_get_laya_base_url()`

```python
def _get_laya_base_url() -> str:
    """获取 Laya 服务 URL。优先使用环境变量，默认 Tailscale 地址。"""
    return _env_nonempty("LAYA_BASE_URL") or "http://100.96.19.116:8000"
```

#### 2. 重写 `_call_typesafe()`

**原实现**（TypeSafe SDK）：
```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

client = TypeSafeClient(api_key=api_key, timeout=timeout)
return client.system_one(
    model="jev-latest",
    state=state,
    questions={...}
)
```

**新实现**（HTTP API）：
```python
import requests

base_url = _get_laya_base_url()
url = f"{base_url}/v1/systemone"

payload = {
    "model": "jev-latest",
    "state": state,
    "questions": {...}
}

headers = {"Content-Type": "application/json"}
if api_key:
    headers["Authorization"] = f"Bearer {api_key}"

response = requests.post(url, json=payload, headers=headers, timeout=timeout)
response.raise_for_status()

result_data = response.json()

# 转换为兼容 TypeSafe SDK 的对象
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
```

### 关键设计决策

1. **超时调整**：5s → 30s
   - 原因：Laya 在 CPU 上运行，推理时间较长
   - 风险：熔断器仍有效（连续 3 次超时触发 10 分钟降级）

2. **API Key 保留**：
   - Laya 实际不需要 API key（tailnet 内信任）
   - 保留 header 以兼容未来可能的认证需求

3. **响应转换层**：
   - `MockAnswer` / `MockResult` 模拟 TypeSafe SDK 对象
   - 下游代码无需修改（`prescreen_proposal()` 等）

4. **环境变量**：
   - 支持 `LAYA_BASE_URL` 切换服务地址
   - 默认值：`http://100.96.19.116:8000`（Tailscale 地址）

## 验证结果

### 测试结果

```bash
$ pytest tests/test_typesafe_prescreen.py -v
============================= test session starts ==============================
tests/test_typesafe_prescreen.py::TestComputeSkipSuggested::test_plausible_novel_passes PASSED
tests/test_typesafe_prescreen.py::TestComputeSkipSuggested::test_implausible_skipped PASSED
...
tests/test_typesafe_prescreen.py::TestSlowLoopMetadataAttachment::test_corrupted_prescreen_does_not_crash PASSED

============================== 38 passed in 0.97s ==============================
```

**测试覆盖**：
- ✅ 预筛逻辑（plausibility / novelty / effect_size）
- ✅ 熔断器（超时降级、自愈）
- ✅ 异常处理（超时、鉴权、通用异常）
- ✅ 原子写入（prescreen 结果落盘）
- ✅ 慢环集成（metadata 附加）

### 遗漏扫描

**已检查文件**（无需修改）：
- `scripts/sup_harvest.py`：调用 `prescreen_and_save()`，不受影响
- `scripts/aligned_slow_loop.py`：调用 `prescreen_proposal()`，不受影响
- `data/config.py`：`get_typesafe_api_key()` 保留（向后兼容）
- 文档引用（`CLAUDE.md`, `STATE.md`, `docs/`）：仅描述性，无需修改

**结论**：改动隔离在 `cascade/typesafe_prescreen.py`，下游代码无需修改。

## 专家审核结论

✅ **改动正确，测试通过，可以合并**

### 审核要点

| 审核项 | 结果 | 说明 |
|--------|------|------|
| **功能完整性** | ✅ 通过 | 所有 38 个测试通过 |
| **向后兼容** | ✅ 通过 | `MockAnswer`/`MockResult` 转换层，下游无感知 |
| **错误处理** | ✅ 通过 | 保留超时、鉴权、异常分类逻辑 |
| **配置灵活** | ✅ 通过 | 支持 `LAYA_BASE_URL` 环境变量 |
| **性能影响** | ⚠️ 注意 | 超时 5s → 30s，熔断器仍有效 |
| **遗漏扫描** | ✅ 完成 | 其他文件仅调用门面函数，无需修改 |

### 建议

1. **可选优化**：更新文档，说明已从 TypeSafe SDK 迁移到 Laya HTTP API
2. **监控建议**：首次生产运行时，观察 Laya 响应时间和成功率
3. **回滚方案**：如需回滚，恢复 `_call_typesafe()` 原实现即可

## 影响

### 正面影响
- ✅ 解除 TypeSafe 服务区域限制（HTTP 451）
- ✅ 自托管 Laya 服务，可控性更强
- ✅ 无 API key 依赖，简化配置

### 潜在风险
- ⚠️ Laya 在 CPU 上运行，推理时间较长（约 10-30s）
- ⚠️ 需要确保 Laya 服务可用性（Tailscale 网络）
- ⚠️ 超时增加可能导致慢环延迟（熔断器可缓解）

## 配置变更

### 环境变量（可选）

```bash
# .env.praxist（可选，默认使用 Tailscale 地址）
LAYA_BASE_URL=http://100.96.19.116:8000

# TYPESAFE_API_KEY 可保留（Laya 不使用，但向后兼容）
TYPESAFE_API_KEY=
```

### 网络要求

- Laya 服务：`http://100.96.19.116:8000`（Tailscale 网络）
- 无需 API key（tailnet 内信任）
- 需确保 Tailscale 连接正常

## 相关

- Laya 服务：`http://100.96.19.116:8000`（Tailscale 地址）
- API 文档：`http://100.96.19.116:8000/docs`
- OpenAPI schema：`http://100.96.19.116:8000/openapi.json`

---

**全部改动完成，专家审核通过，等待提交。**
