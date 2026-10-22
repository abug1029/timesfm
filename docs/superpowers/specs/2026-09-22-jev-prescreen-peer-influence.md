# Jev 预筛输出影响 Peer 行为的设计

> **状态**: 设计草案（2026-09-22）
> **当前**: 预筛结果仅作为软建议写入 `.prescreen.json`，供慢环注入 verdict metadata，不改变 peer 或调度行为。

## 当前数据流（已实现）

```
Peer → 写 proposals/*.json
          ↓
Supervisor harvest_proposals → prescreen_and_save()
          ↓                     调用 Jev(system_one) 3 问并行
          ↓                     原子写入 .prescreen.json
          ↓
          按 _proposal_priority_score() 排序 → 选 top_k
          ↓
Slow Loop → 读 proposal + .prescreen.json → 注入 verdict["metadata"]["prescreen"]
          ↓
          运行回测 → 写 aligned_verdicts.jsonl
```

**当前 gap**: `skip_suggested` 只写入元数据，不参与 `_proposal_priority_score()` 排序，不改变 peer 的提案选择行为。

## Jev 三问输出与 Peer 行为的映射

| Jev 问题 | 返回 | 当前用途 | 应影响的 Peer 行为 |
|----------|------|----------|-------------------|
| `mechanism_plausibility` | `noul` (0-1) | 写入 metadata | **Peer 提案生成策略调整** |
| `novelty_vs_redundancy` | `choice` | 写入 metadata | **探索分计算** |
| `expected_effect_size` | `score` (0-3) | 写入 metadata | **优先级排序** |

### 设计原则

1. **Jev 不决定慢环是否回测** — 慢环永远运行，prescreen 是软建议
2. **Jev 影响 peer 提案的调度优先级** — `skip_suggested=True` 的提案应被降权
3. **Jev 影响 peer 的探索方向** — plausibility 低的机制应收到反馈信号

---

## Phase 1（当前已完成 — 不改变 peer 行为）

当前实现：prescreen 结果写入 `.prescreen.json`，慢环读取并注入 `verdict["metadata"]["prescreen"]`。

**不做任何 peer 行为改变**。理由：
- 先验证 Jev 的判断质量（5 个 proposal 验证，2/5 完全一致，3 个边界偏离需人工审核预期）
- 确认 Jev 的 plausibility/novelty/effect_size 与人类评估的统计一致性后，再接入 peer 调度

---

## Phase 2（建议 — prescreen 影响调度优先级）

### 2.1 跳过建议 → 调度降权

**位置**: `scripts/praxist_supervisor.py` → `_proposal_priority_score()`

当 `.prescreen.json` 存在且 `skip_suggested=True` 时：

```python
# _proposal_priority_score() 末尾追加
def _apply_prescreen_penalty(score, proposal_path):
    """根据 Jev 预筛结果调整提案优先级。"""
    ps_path = str(Path(proposal_path).with_suffix(".prescreen.json"))
    if os.path.exists(ps_path):
        try:
            with open(ps_path, encoding="utf-8") as f:
                ps = json.load(f)
        except (json.JSONDecodeError, OSError):
            return score
        
        if ps.get("skip_suggested") is True:
            novelty = ps.get("novelty", "")
            plausibility = ps.get("mechanism_plausibility")
            
            # 机制不可信 → 强降权
            if novelty == "invalid":
                return score - 100.0  # 实质上移出候选池
            # 冗余 + 微弱效果 → 中度降权
            if novelty == "redundant" and ps.get("effect_size", 0) <= 1:
                return score - 30.0
            # 纯低可信度 → 轻度降权
            if plausibility is not None and plausibility < 0.4:
                return score - 20.0
        
        # skip_suggested=False 且高效果 → 轻度奖励
        if ps.get("skip_suggested") is False and ps.get("effect_size", 0) >= 2:
            return score + 10.0
    
    return score
```

**为什么用 score 惩罚而非硬阻断**：
- `invalid` 机制 -100 分实质移出候选池（等效于阻断，但保留可审计性）
- `redundant` -30 分让同 family 的新变体有机会
- 低 plausibility -20 分让高探索分的机制仍有机会被验证
- 不改变慢环回测逻辑，只改变**谁先被验证**

### 2.2 跨品种迁移先验 → Jev 确认 → 加分

当前 `_proposal_priority_score()` 第 5 条已有"过门族迁移 +8 分"（基于历史 gate_pass）。

Jev 提供了**前瞻判断**（不依赖历史回测），可以新增：

```python
# Jev 跨品种确认：同 family 在其他品种被判为 novel/extension + 高 plausibility
if ps.get("novelty") in ("novel", "extension") and ps.get("mechanism_plausibility", 0) > 0.6:
    score += 5.0  # Jev 确认的新颖/扩展机制，+5 分
```

### 2.3 Peer 提案生成反馈（可选增强）

当前 peer 生成 proposal 时**不知道** Jev 的看法。可以在 proposal 目录写入一个 `prescreen_feedback.json`：

```json
{
  "prescreen_status": "success",
  "skip_suggested": true,
  "reason": "机制可信度低 (0.35) | 新颖度: 冗余 | 预期效果: 无信息量",
  "suggestion": "考虑修正机制描述或选择正交协变量"
}
```

Peer 在下一轮生成时读取这个反馈，调整 mechanism 描述或选择不同的 cov_override。

---

## Phase 3（远期 — Jev 反馈闭环）

### 3.1 Jev 判断质量追踪

在 `aligned_verdicts.jsonl` 的 metadata 中已有 prescreen 结果。可以追踪：

| 指标 | 计算方式 | 用途 |
|------|----------|------|
| Jev plausibility vs gate_pass | 高 plausibility 的提案是否更可能过门？ | 校准 plausibility 阈值 |
| Jev novelty vs dir_acc | novel 提案的 DirAcc 是否高于 redundant？ | 验证新颖度判断质量 |
| Jev effect_size vs EV | 高 effect_size 提案的 EV 是否更高？ | 校准 effect_size 阈值 |

### 3.2 自动阈值校准

当积累了 50+ 条带 prescreen metadata 的 verdict 后：

```python
# 如果 Jev plausibility >= 0.7 的提案 gate_pass 率 > 60%
# → plausibility 是有效信号，可以在排序中加权
# 如果 Jev skip_suggested=True 的提案 gate_pass 率 < 10%
# → skip 判断是有效信号，可以加大降权幅度
```

### 3.3 Peer 自适应机制

Peer 读取历史 Jev 反馈 + 回测结果，自我调整：
- 避免被 Jev 反复判定为 `invalid` 的机制模式
- 优先探索被 Jev 判定为 `novel` + `high effect_size` 的方向
- 当 Jev 和回测结果持续不一致时，标记"Jev 盲区"（如特定品种/体制下 Jev 判断不准）

---

## 实施优先级

| 阶段 | 内容 | 优先级 | 依赖 |
|------|------|--------|------|
| **Phase 1** | 写入 prescreen.json + 慢环注入 metadata | ✅ 已完成 | — |
| **Phase 2.1** | skip_suggested 影响调度优先级 | 高 | Jev 验证 ≥50 条 verdict |
| **Phase 2.2** | Jev 跨品种确认加分 | 中 | 同 2.1 |
| **Phase 2.3** | Peer 反馈文件写入 | 低 | 2.1 |
| **Phase 3** | Jev 质量追踪 + 自动校准 | 低 | ≥50 条带 metadata verdict |
