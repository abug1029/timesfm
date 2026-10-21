# Backfill 审核修复计划 v2（2026-10-19）

> **来源**: `docs/superpowers/reports/2026-10-19-laya-backfill-execution-503-audit.md`
> **修订**: 根据 `plans/2026-10-19-backfill-audit-fix-plan-audit.md` 修正 P0/P1
> **目标**: 修 ReadTimeout 熔断路径 + 文档纠错 + P2 改进
> **预估工作量**: P1 ~2h, P2 ~3h

---

## Phase 1: P1 代码修复（阻塞下一轮全量）

### 1.1 ReadTimeout 熔断路径修复

**文件**: `cascade/typesafe_prescreen.py`

**问题**: `_prescreen_impl` (L417-424) 只 `except (TimeoutError, TypeSafeTimeoutError)`，但 `requests.exceptions.ReadTimeout` 不继承 builtin `TimeoutError`，落入泛 `Exception` → 不调用 `_record_timeout()` → 熔断器永不触发。

**P0 修正**:
1. 模块级 import: `from requests.exceptions import Timeout as RequestsTimeout`（L10 附近，与现有 `import requests` 并列）
2. 返回值保持 `_fallback_result()` 契约，不用裸 dict

**修复**:
```python
# 模块级（L10 附近）
from requests.exceptions import Timeout as RequestsTimeout

# _prescreen_impl（L417-424）
# 现有代码
except (TimeoutError, TypeSafeTimeoutError) as e:
    _record_timeout()
    return _fallback_result(proposal, symbol, status="degraded", note="Laya API 超时")
except Exception as e:
    return _fallback_result(proposal, symbol, status="error", note=str(e))

# 修复后
except (TimeoutError, TypeSafeTimeoutError, RequestsTimeout) as e:
    _record_timeout()
    logger.warning(f"Laya API 超时: {e}")
    return _fallback_result(proposal, symbol, status="degraded", note="Laya API 超时")
except Exception as e:
    return _fallback_result(proposal, symbol, status="error", note=str(e))
```

**验证**: 
- 单测: mock `requests.post` 抛 `ReadTimeout`，断言 `_consecutive_timeouts` 递增且 3 次后 `_circuit_until` 置位
- 集成: 跑 100 个提案，人工注入超时，检查日志有「Laya API 超时」/「短路降级」

### 1.2 Changelog 纠错

**文件**: `docs/superpowers/changelogs/2026-10-19-laya-backfill-prescreen-execution.md`

**修改**:
1. **删除**「不做的事」第 1 条「374 个 Laya 503 错误」
2. **替换**章节标题「107 个真正失败」→「54 failed + 45 degraded 拆解」
3. **替换**表格为审核报告 §2.3 拆解表:

| 类型 | 数量 | 说明 |
|------|------|------|
| JSON 解析失败 | 43 | `[ERROR] 无法解析提案` |
| TypeError（PD 为 int） | 8 | `_strip_chinese` 期望 str |
| ReadTimeout | 1 | Laya API 超时 |
| 缺 symbol | 2 | `[WARNING] 缺少 symbol 字段` |
| W6.4 vid 不可得 | 45 | degraded（非 failed） |
| REGISTRY 跳过 | 6147 | 已处理过 |

4. **「待办」** 改为「监控超时/客户端断开/检查点切换」，非 503
5. **对齐** 「12 个未修 JSON」→ 「7 个」（与 503 报告一致，来源：fix_corrupted_proposals.py 输出）

---

## Phase 2: P2 改进

### 2.1 完成行补 skipped

**文件**: `scripts/backfill_prescreen.py`

**行号**: L607-609（非 ~580）

**现状**: 已有 `degraded=`，缺 `skipped=`

**修改**: 
```python
# L607-609 现有
logging.info(
    "完成: total=%d success=%d failed=%d enqueued=%d degraded=%d elapsed=%.0fs",
    stats["total"], stats["success"], stats["failed"], stats["enqueued"],
    stats.get("degraded", 0), elapsed
)

# 修改后
logging.info(
    "完成: total=%d success=%d failed=%d enqueued=%d skipped=%d degraded=%d elapsed=%.0fs",
    stats["total"], stats["success"], stats["failed"], stats["enqueued"],
    stats.get("skipped", 0), stats.get("degraded", 0), elapsed
)
```

### 2.2 _strip_chinese 防御性类型检查

**文件**: `cascade/typesafe_prescreen.py`

**行号**: L41（非 ~50）

**现状**: L300 调用侧已 `str(proposal.get("predicted_direction") or "")`，本修改为纵深防御

**修改**: 
```python
# L41 _strip_chinese 入口
def _strip_chinese(s):
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    # ... 原有逻辑
```

### 2.3 缺 symbol / 空文件独立计数

**文件**: `scripts/backfill_prescreen.py`

**行号修正**:
- 缺 symbol: `extract_proposal_fields` L180-187 → `None`；`process_proposal` L323-325 `stats.inc("failed")`
- 空文件: 无独立分支，JSON 解析失败时检查

**修改**:
1. `Stats` 类加 `invalid_input` 字段（L50 附近）
2. `process_proposal` L323-325:
```python
# 现有
if not symbol:
    logging.warning(f"缺少 symbol 字段，跳过")
    stats.inc("failed")
    return {"status": "error", "error": "missing symbol"}

# 修改后
if not symbol:
    logging.warning(f"缺少 symbol 字段，跳过")
    stats.inc("invalid_input")
    return {"status": "error", "error": "missing symbol"}
```
3. `snapshot()` 加 `invalid_input`（L70 附近）
4. state 初值加 `invalid_input: 0`（L150 附近）
5. 进度行/完成行加 `invalid=%d`（L576, L607）

### 2.4 HTTP 5xx/429 指数退避

**文件**: `cascade/typesafe_prescreen.py` `_call_laya`

**行号**: L329-380

**P1 修正**: 退避必须在 `raise_for_status()` **之前**；耗尽重试抛 `HTTPError`（非 `TypeSafeTimeoutError`，避免污染超时熔断）

**修改**:
```python
# L360 附近，response = requests.post(...) 后
# 现有
response.raise_for_status()
return response.json()

# 修改后
if response.status_code in (429, 500, 502, 503, 504):
    for attempt in range(3):
        wait = min(2 ** attempt, 10)
        time.sleep(wait)
        response = requests.post(url, json=payload, timeout=timeout)
        if response.status_code == 200:
            break
    else:
        response.raise_for_status()  # 抛 HTTPError，不进超时熔断
return response.json()
```

### 2.5 TypeError 日志带 proposal_id

**文件**: `cascade/typesafe_prescreen.py`

**行号修正**: `prescreen_proposal` L461-465（非 backfill 的 `process_proposal`）

**现状**: L461-465 外层 except 被吞成 fallback，无 proposal_id

**修改**:
```python
# L461-465 现有
except Exception as e:
    logger.error(f"prescreen 异常: {e}")
    return _fallback_result(proposal, symbol, status="error", note=str(e))

# 修改后
except Exception as e:
    proposal_id = proposal.get("proposal_id", "?")
    logger.error(f"prescreen 异常 {proposal_id}: {e}")
    return _fallback_result(proposal, symbol, status="error", note=str(e))
```

### 2.6 503 报告数字修正

**文件**: `docs/superpowers/reports/2026-10-19-laya-503-error-analysis.md`

**修改**:
1. JSON 44 → 43
2. 加注: 「同名提案多 run，int PD 仅 `run_2026-10-18_23-28-46` 下 8 份」
3. 对齐「未修 JSON」: 12 → 7（与 changelog 一致）

---

## Phase 3: 验证与重跑

### 3.1 单元测试

**文件**: `tests/test_typesafe_prescreen.py`

**新增**:
```python
def test_read_timeout_returns_degraded():
    """ReadTimeout 应触发熔断（与 builtin TimeoutError 同路径）"""
    from requests.exceptions import ReadTimeout
    with mock.patch("cascade.typesafe_prescreen.requests.post") as mock_post:
        mock_post.side_effect = ReadTimeout("read timeout")
        result = prescreen_proposal(test_proposal)
        assert result["status"] == "degraded"
        assert _consecutive_timeouts > 0
```

**现有**: `test_api_timeout_returns_degraded` 只 mock builtin `TimeoutError`，需增补 `ReadTimeout` 用例

### 3.2 集成重跑失败子集

**P1 修正**: 不用 `--force --max 200`（不保证打到失败子集）

**方法**:
1. 提取失败路径列表:
```bash
grep '\[ERROR\]' logs/backfill_prescreen_20261019_032210.log | \
  grep -oP 'task_FM/experiments/[^ ]+\.json' | sort -u > /tmp/failed_proposals.txt
wc -l /tmp/failed_proposals.txt  # 应 ~54
```
2. 清空 processed 中失败项:
```python
python3 -c "
import json
from pathlib import Path
state_file = Path('data/cache/backfill_prescreen_state.json')
state = json.loads(state_file.read_text())
failed = set(Path(l.strip()).stem for l in open('/tmp/failed_proposals.txt'))
state['processed'] = [p for p in state['processed'] if p not in failed]
state_file.write_text(json.dumps(state))
print(f'Removed {len(failed)} failed from processed')
"
```
3. 重跑（无 `--force`，只跑失败子集）:
```bash
LAYA_BASE_URL=http://100.96.19.116:8000 python3 scripts/backfill_prescreen.py \
  --max 100 --workers 2 --timeout-min 30 --skip-laya-check
```

**验证**:
- TypeError → 0（P1 修复生效）
- W6.4 degraded 下降（多 schema 提取生效）
- ReadTimeout 触发熔断（若 Laya 变慢）

### 3.3 提案生产侧（长期）

- 禁止 `predicted_direction` 非字符串（提案生成脚本加类型校验）
- 写盘前 `json.dumps` round-trip（捕获序列化错误）
- 中文引号 escape 门禁（从源头砍 JSON 43）

---

## 交付物

1. **代码修复**: 2 commits
   - `fix(prescreen): ReadTimeout 熔断路径 + _strip_chinese 防御`
   - `feat(backfill): invalid_input 计数 + HTTP 退避 + 完成行透明度`
2. **文档修正**: 1 commit
   - `docs(changelog): 纠错 failed 归因 + 删 374 叙事 + 对齐数字`
3. **测试**: 1 个新增单测（ReadTimeout）+ 集成重跑报告
4. **重跑结果**: ~54 个失败提案的处理统计

---

## 时间线

| 阶段 | 耗时 | 依赖 |
|------|------|------|
| Phase 1 P1 修复 | 2h | 无 |
| Phase 2 P2 改进 | 3h | Phase 1 |
| Phase 3 验证 | 1h | Phase 1+2 |
| **总计** | **6h** | - |

**阻塞条件**: Phase 1 未完成前不开大规模重试/全量。

---

## 修订记录

**v2**（2026-10-19 15:45）: 根据 plan audit 修正
- P0: Phase 1.1 加模块级 `RequestsTimeout` import + 保持 `_fallback_result` 返回
- P1: Phase 2.4 退避移到 `raise_for_status` 前 + 抛 `HTTPError` 非 `TypeSafeTimeoutError`
- P1: Phase 2.3 修正行号（L180/L323）+ 补 `Stats.invalid_input`/`snapshot`/state 初值
- P1: Phase 2.5 修正目标函数（`typesafe_prescreen.prescreen_proposal` L461）
- P1: Phase 3.2 改用失败路径列表 + 清空 processed 中失败项（非 `--force`）
- P2: 修正行号（L607/L41）+ 对齐数字（12→7）+ 章节标题改
