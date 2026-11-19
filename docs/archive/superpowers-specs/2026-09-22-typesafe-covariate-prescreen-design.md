# TypeSafe 协变量提案预筛设计

> **日期**: 2026-09-22
> **状态**: 设计草稿，待审核（审查后修订版 v4 — 第三轮确认全部修复已落地）
> **作者**: Claude (architectural brainstorming)
> **来源**: TypeSafe × FM_a 集成探索 — P0 层位

---

## 1. 动机

Praxist 三环运行至今，105 个 verdict 仅 22 个 gate_pass（21%）。每个未过门的提案都消耗了 30+ 分钟的 walk-forward 回测时间（加载 TimesFM、跑 350-600 点数据、统计检验）。大量提案在慢环启动前就明显不可信——机制不合理、与已有协变量冗余、或对该品种不适用——但 peer 无法预知，必须等回测跑完才能看到 numeric verdict。

TypeSafe System One（Jev 模型）可以在 peer 写完 proposal 后、慢环启动前，用结构化判断评估提案的**机制合理性**和**新颖度**，为后续迭代提供语义化反馈。

### 核心设计约束：软建议模式（Approach A）

- **不阻断任何回测**：TypeSafe 只输出建议标签 + 理由，记录到 verdict 元数据中
- **不改变 v23 裁决标准**：n≥350 / n_eff≥50 / dir_acc / DM / BH-FDR 保持不变
- **先积累准确率数据**：等 TypeSafe 判断与真实 verdict 的对应关系有足够样本后，再考虑硬门控

---

## 2. 设计目标

- **语义化反馈**：每个 proposal 得到 mechanism_plausibility / novelty / effect_size 三维度评分
- **零侵入裁决链**：不修改 evaluator / aligned_slow_loop 的核心逻辑，只追加元数据字段
- **可追溯**：prescreen 结果与 proposal 一一对应，写入同目录
- **可验证**：prescreen 的 skip_suggested=true 的提案中，有多少实际 gate_pass / gate_fail，积累误杀率数据
- **低成本**：每次 prescreen 1 次 TypeSafe API 调用（3 问并行），预计 <2 秒
- **统计纯净**：降级样本与成功样本严格区分，不污染监控指标

---

## 3. 架构

### 3.1 数据流

> **路径基准**：所有 proposal 和 prescreen 文件均以项目根下的 `results/` 为前缀。
> Peer 写 proposal 到 `results/gen_N/<peer>/<variant_id>/proposals/<id>.json`；
> 慢环从同一 `results/` 前缀读取。

```
Peer 写 proposal (results/gen_N/<peer>/<variant_id>/proposals/<id>.json)
    │
    ▼
cascade/typesafe_prescreen.py (新增)
    │ 读取: proposal + symbol 历史 verdict + covariate_menu
    │ 调用: TypeSafe judge (3 问并行)
    │ 输出: results/gen_N/<peer>/<variant_id>/proposals/<id>.prescreen.json
    │       (与 proposal 同目录同名，仅扩展名不同)
    │
    ▼ (不改变 proposal 状态)
慢环正常启动 (aligned_slow_loop.py)
    │ 读取: <proposal_path>.prescreen.json (若存在)
    │ verdict["metadata"]["prescreen"] 追加预筛字段
    ▼
v23 verdict 写入 aligned_verdicts.jsonl
    │ verdict["metadata"]["prescreen"] 包含:
    │   status, skip_suggested, plausibility,
    │   novelty, effect_size, note
    ▼
监督环汇总 (supervisor_state.json)
    │ 新增统计: prescreen_total, prescreen_success_count,
    │           prescreen_skip_suggested_count,
    │           prescreen_fnr (仅统计 status=="success" 样本)
```

### 3.2 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `cascade/typesafe_prescreen.py` | **新增** | 预筛核心逻辑 + 轻量熔断 |
| `tests/test_typesafe_prescreen.py` | **新增** | Mock 测试 |
| `scripts/aligned_slow_loop.py` | 修改 | 读取 prescreen 结果，追加 verdict metadata |
| `task_FM/task.yaml` | 修改 | env 添加 TYPESAFE_API_KEY |
| `data/config.py` | 修改 | 新增 get_typesafe_api_key() |
| `docs/superpowers/specs/` | 本文件 | 设计文档 |

---

## 4. 预筛核心逻辑

### 4.1 入口函数与返回契约

```python
"""cascade/typesafe_prescreen.py"""

from pathlib import Path
from typing import Any, Literal

PrescreenStatus = Literal["success", "degraded", "error"]
NoveltyType = Literal["novel", "extension", "redundant", "invalid"]


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
        "ts": datetime.utcnow().isoformat(),
    }


def prescreen_proposal(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None = None,
    covariate_menu: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """TypeSafe 预筛一个协变量提案。
    
    全量异常保护：任何内部处理错误都会平滑降级为标准 fallback 对象，
    绝不向调用方（Peer 流程）抛出异常。
    """
    try:
        return _prescreen_impl(proposal, symbol, verdict_history, covariate_menu)
    except Exception as e:
        logger.exception("TypeSafe 预筛未预期异常，防御性降级")
        return _fallback_result(
            proposal, symbol,
            status="error",
            note=f"预筛异常降级: {type(e).__name__}",
        )


def prescreen_and_save(
    proposal: dict[str, Any],
    proposal_path: str,
    symbol: str,
    verdict_history: list[dict[str, Any]] | None = None,
    covariate_menu: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """端到端门面：预筛 + 原子落盘至 <proposal_path>.prescreen.json。
    
    Peer 端只需调用此单一函数，无需手动协调 prescreen_proposal +
    write_prescreen_result + Path.with_suffix。
    """
    result = prescreen_proposal(proposal, symbol, verdict_history, covariate_menu)
    prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
    write_prescreen_result(prescreen_path, result)
    return result


def _prescreen_impl(
    proposal: dict[str, Any],
    symbol: str,
    verdict_history: list[dict[str, Any]] | None,
    covariate_menu: dict[str, Any] | None,
) -> dict[str, Any]:
    """预筛核心实现。异常分类：超时→degraded，鉴权→error，其他→error。"""
    
    # 1. API Key 检查
    api_key = _get_typesafe_api_key()
    if not api_key:
        return _fallback_result(proposal, symbol, note="TypeSafe 未启用")
    
    # 2. 熔断检查
    if _check_circuit():
        return _fallback_result(proposal, symbol, note="TypeSafe 短路降级中")
    
    # 3. 构建 State
    state = _build_state(proposal, symbol, verdict_history, covariate_menu)
    
    # 4. 调用 TypeSafe API（3 问并行，显式 5s 超时）
    try:
        result = _call_typesafe(state, api_key, timeout=5.0)
    except TimeoutError as e:
        _record_timeout()  # 触发熔断计数
        logger.warning("TypeSafe API 超时: %s", e)
        return _fallback_result(proposal, symbol, status="degraded", note="TypeSafe API 超时")
    except AuthenticationError as e:
        logger.error("TypeSafe API 鉴权失败: %s", e)
        return _fallback_result(proposal, symbol, status="error", note="TypeSafe API 鉴权失败")
    except Exception as e:
        logger.exception("TypeSafe API 调用失败: %s", e)
        return _fallback_result(proposal, symbol, status="error", note=f"TypeSafe API 返回异常: {e}")
    
    # 5. 解包 SDK 返回为纯标量（与 SDK 对象解耦）
    answers = result.data.answers
    plausibility = answers["mechanism_plausibility"].probability_yes
    novelty = answers["novelty_vs_redundancy"].value
    effect_size = answers["expected_effect_size"].level_index
    
    _record_success()
    
    # 6. 纯函数判定 + note 生成
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
        "raw_answers": _serialize_raw_answers(answers),  # 保留 SDK 原始序列化，用于审计
        "ts": datetime.utcnow().isoformat(),
    }


def _serialize_raw_answers(answers: dict) -> dict[str, Any]:
    """将 SDK 原始答案序列化为纯 dict，保留 probability_yes/reasoning/置信度元数据。"""
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
```

**降级契约**：当无 API Key、超时或 API 错误时，返回 `status="degraded"` 且 `skip_suggested=None`（绝不返回布尔值），防止后续统计污染。

### 4.2 TypeSafe 三问

**State 构建**（变量展平，避免 KeyError）：
```python
symbol_profile = _load_symbol_profile(symbol)

state = {
    "symbol": symbol,
    "proposal": proposal,  # 完整的 fm.hypothesis_proposal.v1
    "sector": symbol_profile.get("sector", "未知"),
    "contract_details": symbol_profile.get("contract_details", ""),
    "covariate_menu": covariate_menu or _load_covariate_menu(),
    "recent_verdicts_summary": _extract_relevant_history(verdict_history, symbol),
}
```

**Question 1: mechanism_plausibility (Noul)**

```
instructions: "基于 {symbol} 的品种特征（{sector}板块，{contract_details}），该协变量提案的机制解释是否合理且有经济逻辑支撑？"
```

输出：`probability_yes` (0.0-1.0)

**Question 2: novelty_vs_redundancy (Choice)**

```
instructions: "该提案与 {symbol} 已有协变量的关系（见 covariate_menu 和 recent_verdicts_summary）"
criteria: {
    "novel": "全新机制，与现有协变量正交",
    "extension": "已知机制的新参数或新品种适配",
    "redundant": "与现有协变量高度重叠（机制或数值相关性>0.8）",
    "invalid": "机制不存在或逻辑错误",
}
```

**Question 3: expected_effect_size (Score)**

```
instructions: "预期该协变量对 {symbol} 预测质量的信息量贡献"
levels: [
    "无新增信息（纯噪声或已完全捕获）",
    "微弱新增信息（与现有协变量高度相关，边际贡献有限）",
    "中等新增信息（独立信号维度，可能有交互效应）",
    "强新增信息（正交维度，高预期独立贡献）",
]
```

### 4.3 历史裁决提取器（防上下文溢出 + 跨品种迁移先验 + None 安全）

```python
def _extract_relevant_history(
    verdict_history: list[dict] | None,
    symbol: str,
    max_entries: int = 5,
    max_cross_entries: int = 5,
) -> str:
    """两段式历史摘要：当前品种过门记录 + 同板块经典先验基底。
    
    新品种冷启动时，通过同板块已过门协变量提供迁移参照，
    避免模型因缺乏上下文将 extension 误判为 novel。
    """
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
            # 按 cov_family 去重，每族只取最新一条
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

> **设计说明**：第二段仅取 cov_family 级别（不取具体 cov_override），为模型提供"这个族在其他品种上有效"的先验信号，帮助区分 novel 与 extension。

### 4.4 skip_suggested 判定规则（纯函数，与 SDK 对象解耦）

```python
def compute_skip_suggested(
    plausibility: float,
    novelty: str,
    effect_size: int,
) -> bool:
    """决定是否建议跳过。纯函数，参数为基础标量，便于单元测试。
    
    覆盖边界盲区：effect_size==0 且机制可信度不高时建议跳过。
    """
    if plausibility < 0.4:
        return True  # 机制不可信
    if novelty == "invalid":
        return True  # 机制错误
    if novelty == "redundant" and effect_size <= 1:
        return True  # 冗余且效果微弱
    if effect_size == 0 and plausibility < 0.6:
        return True  # 预期无信息量且机制缺乏高确定性
    
    return False
```

### 4.5 note 生成（纯函数，与 SDK 对象解耦）

```python
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

### 4.6 轻量熔断（连续超时退避 + 半开自愈）

```python
# 模块级状态，进程内有效
_consecutive_timeouts = 0
_circuit_until: float | None = None  # 短路截止时间戳


def _check_circuit() -> bool:
    """检查是否处于短路降级状态。返回 True 表示应跳过 API 调用。
    
    半开自愈：短路期满后自动重置计数器，允许一次试探请求。
    若试探成功则恢复正常；若试探再次超时则重新进入短路。
    """
    global _circuit_until, _consecutive_timeouts
    now = time.time()
    if _circuit_until:
        if now < _circuit_until:
            return True  # 仍处于短路期
        # 短路期已过，进入半开自愈：重置计数器，给予试探机会
        _circuit_until = None
        _consecutive_timeouts = 0
    return False


def _record_timeout():
    """记录一次超时。连续 3 次超时后开启 10 分钟短路。"""
    global _consecutive_timeouts, _circuit_until
    _consecutive_timeouts += 1
    if _consecutive_timeouts >= 3:
        _circuit_until = time.time() + 600  # 10 分钟短路
        logger.warning("TypeSafe prescreen: 连续 3 次超时，开启 10 分钟短路降级")


def _record_success():
    """成功调用重置计数器并解除短路。"""
    global _consecutive_timeouts, _circuit_until
    _consecutive_timeouts = 0
    _circuit_until = None
```

### 4.7 原子写盘助手（防并发 JSONDecodeError）

```python
def write_prescreen_result(prescreen_path: str, result: dict[str, Any]) -> None:
    """原子写入 prescreen JSON，防止慢环读取半写文件。
    
    先写临时文件（含 PID 防冲突），再 os.replace 原子替换。
    POSIX 保证 os.replace 的原子性：读者要么看到旧文件，要么看到完整新文件。
    """
    import os
    temp_path = f"{prescreen_path}.tmp.{os.getpid()}"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, prescreen_path)
```

---

## 5. 慢环集成（非阻塞）

### 5.1 aligned_slow_loop.py 修改

在 verdict 构建阶段，基于 proposal 路径推导 prescreen 文件并注入 `metadata` 命名空间：

```python
from pathlib import Path

# 基于 proposal_path 推导 prescreen 文件路径
# proposal_path 例如: results/gen_3/peer_001/v_xyz/proposals/p_001.json
# prescreen_path 则为: results/gen_3/peer_001/v_xyz/proposals/p_001.prescreen.json
# 使用 Path.with_suffix() 避免 .replace() 贪婪替换路径中间段的风险
prescreen_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
if os.path.exists(prescreen_path):
    try:
        with open(prescreen_path, encoding="utf-8") as f:
            ps = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # 半写文件或损坏 JSON：记录 warn 但不阻断回测
        logger.warning("prescreen 文件解析失败 (%s): %s", prescreen_path, e)
        ps = None
    
    if ps:
        # 注入 verdict["metadata"]["prescreen"] 命名空间，不污染根节点
        if "metadata" not in verdict:
            verdict["metadata"] = {}
        verdict["metadata"]["prescreen"] = {
            "status": ps.get("status"),
            "skip_suggested": ps.get("skip_suggested"),
            "plausibility": ps.get("mechanism_plausibility"),
            "novelty": ps.get("novelty"),
            "effect_size": ps.get("effect_size"),
            "note": ps.get("note"),
        }
```

**不改变**：
- verdict schema 版本号（仍为 `fm.aligned_verdict.v2`）
- gate_pass / fdr_pass / status 等核心裁决字段（prescreen 字段仅存在于 `metadata` 命名空间内）
- 回测执行逻辑

### 5.2 触发方式

**方式 A（推荐，首版实现）**：在 peer 的 `share_finding(finding_type=hypothesis)` 后，调用 `prescreen_and_save` 门面函数。Peer 端无需手动协调路径或写盘：

```python
from cascade.typesafe_prescreen import prescreen_and_save

result = prescreen_and_save(
    proposal=proposal_dict,
    proposal_path=proposal_file_path,  # 例如: results/gen_3/peer_001/v_xyz/proposals/p_001.json
    symbol=symbol,
    verdict_history=verdict_history,
    covariate_menu=covariate_menu,
)
```

**方式 B**（未来优化）：在 supervisor 的 harvest 循环中，对新发现的 proposal 批量跑 prescreen。

---

## 6. 环境变量与配置

### 6.1 TYPESAFE_API_KEY

密钥只进 `.env.praxist`，不写进 `task_FM/task.yaml` 的代码部分：

```yaml
# task_FM/task.yaml — runtime_environment 节追加
runtime_environment:
  env:
    CUDA_VISIBLE_DEVICES: ''
    PRAXIST_TRUSTED_PROJECT_EXTRA_ROOTS: /home/abug/timesfm
    TYPESAFE_API_KEY: '${TYPESAFE_API_KEY}'  # 从 .env.praxist 加载
```

### 6.2 降级行为（三态）

| 场景 | status | skip_suggested | note |
|------|--------|----------------|------|
| 无 TYPESAFE_API_KEY | `"degraded"` | `None` | "TypeSafe 未启用" |
| API 超时（>5s） | `"degraded"` | `None` | "TypeSafe API 超时" |
| API 鉴权失败（401） | `"error"` | `None` | "TypeSafe API 鉴权失败" |
| 正常调用但 API 异常 | `"error"` | `None` | "TypeSafe API 返回异常: {msg}" |
| 成功但低置信 | `"success"` | `false` | 正常 note |
| 成功且建议跳过 | `"success"` | `true` | 正常 note |

降级时 `skip_suggested` 显式为 `None`（非 `false`），防止监控指标污染。

---

## 7. 测试

### 7.1 Mock 测试（`tests/test_typesafe_prescreen.py`）

| 测试 | 验证 |
|------|------|
| `test_plausible_proposal_passes` | 合理机制 + 新颖 → status="success", skip_suggested=false |
| `test_implausible_proposal_skipped` | 不可信机制 → status="success", skip_suggested=true |
| `test_redundant_proposal_skipped` | 冗余 + 微弱效果 → skip_suggested=true |
| `test_invalid_mechanism_skipped` | 无效机制 → skip_suggested=true |
| `test_zero_effect_low_plausibility_skipped` | effect_size=0 且 plausibility<0.6 → skip_suggested=true |
| `test_no_api_key_returns_degraded` | 无 API Key → status="degraded", skip_suggested=None |
| `test_api_timeout_returns_degraded` | 超时 → status="degraded", skip_suggested=None |
| `test_auth_error_returns_error` | 401 → status="error", skip_suggested=None |
| `test_circuit_opens_after_3_timeouts` | 连续 3 次超时 → 短路激活，后续调用立即返回 degraded |
| `test_circuit_half_open_resets_on_expire` | 短路期满后自动重置计数器，允许试探请求 |
| `test_circuit_resets_on_success` | 短路后成功调用 → 计数器清零，短路解除 |
| `test_timeout_triggers_circuit_not_error` | TimeoutError → status="degraded"（非 error）且 _record_timeout 被调用 |
| `test_auth_error_returns_error_not_degraded` | AuthenticationError → status="error" |
| `test_slow_loop_attaches_prescreen_to_metadata` | 慢环读取 prescreen 并注入 verdict["metadata"]["prescreen"] |
| `test_prescreen_file_named_after_proposal` | prescreen 文件与 proposal 同名同目录 (.prescreen.json) |
| `test_atomic_write_replaces_cleanly` | write_prescreen_result 用 os.replace 原子写入，无临时文件残留 |
| `test_never_raise_wraps_all_exceptions` | 内部处理异常 → 平滑降级，不向调用方抛异常 |
| `test_cross_symbol_history_none_safe_sorting` | verdict 中 decided_at=None 时排序不崩溃 |
| `test_cross_symbol_history_unknown_sector_excluded` | 未知板块品种不注入同板块先验 |
| `test_compute_skip_suggested_pure_function` | 传入纯标量即可调用，无需 mock SDK 对象 |
| `test_prescreen_and_save_facade` | 门面函数一次调用完成预筛 + 原子落盘 |

### 7.2 集成验证（人工）

设置 TYPESAFE_API_KEY 后，对 5 个历史 proposal 跑 prescreen，手动验证：
- mechanism_plausibility 是否合理
- novelty 分类是否准确
- skip_suggested 的判定是否与直觉一致

---

## 8. 监控与后续

### 8.1 监控指标（精确定义）

prescreen 积累 50+ **status="success"** 样本后，计算以下指标。降级样本（status="degraded" 或 "error"）不参与计算：

| 指标 | 定义 | 关注阈值 |
|------|------|---------|
| **假阴性率 / 误杀率 (FNR)** | FNR = Σ(status="success" ∧ skip_suggested=True ∧ gate_pass=True) / Σ(status="success" ∧ gate_pass=True) | <5% |
| **推荐跳过有效率 (Precision_skip)** | Precision_skip = Σ(status="success" ∧ skip_suggested=True ∧ gate_pass=False) / Σ(status="success" ∧ skip_suggested=True) | 越高越好 |
| **一致率** | Σ(status="success" ∧ skip_suggested=False ∧ gate_pass=True) / Σ(status="success" ∧ skip_suggested=False) | 越高越好 |

### 8.2 未来升级路径

当 FNR <5% 且 status="success" 样本量 >200 后，可考虑：

- **Approach B（硬门控）**：skip_suggested=true 的提案不进慢环
- **Peer prompt 增强**：在 peer 的 prompt 中加入 prescreen 历史统计，指导其生成更高质量的提案
- **Supervisor 面板**：在 supervisor_state.json 中暴露 prescreen 统计，供 runbook 查询

### 8.3 不做的

- 不替代 v23 裁决标准
- 不改变 peer 的 proposal schema
- 不在 prescreen 中跑 TimesFM 回测（保持轻量）
- 不做 prescreen 结果的跨 symbol 迁移（每个 symbol 独立评估）

---

## 9. 与 trader 项目 TypeSafe 集成的关系

| 维度 | trader | FM_a P0 |
|------|--------|---------|
| SDK 复用 | `src/adapters/typesafe_adapter.py` | 可复用或直接用 typesafe-sdk |
| 判断类型 | Choice/Score/Noul（入场/漂移） | Noul/Choice/Score（协变量预筛） |
| 接线方式 | `judgment` 参数注入图节点 | 独立 prescreen 函数调用 |
| 熔断器 | 有（threading.Lock 四态） | 轻量级（进程内计数器，10 分钟短路） |
| 降级策略 | fallback 到 LLM structured | 三态降级（skip_suggested=None） |

两个项目共用同一 TYPESAFE_API_KEY 或各自独立，取决于你的 API 配额规划。
