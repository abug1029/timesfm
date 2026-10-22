# B1 Feedback -> Agenda Schema 定义

> **日期**: 2026-10-21
> **状态**: 输入侧（feedback）已冻结；输出侧（agenda）草案由 C0 冒烟验证 2 PASS 确认

**上游**: Spec §3.3 P1-B / Plan Task 1-2
**消费者**: `scripts/synthesize_agenda_from_feedback.py`（B2 离线合成器，待实现）

---

## 1. 输入侧 — bandit_feedback.jsonl Schema（已冻结）

**写盘方**: `scripts/sup_harvest.py::_write_bandit_feedback()`
**路径**: `data/cache/bandit_feedback.jsonl`
**写入时机**: 提案成功入队（通过质量门 + 注册 stem）后立即追加一行

### JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "BanditFeedbackRecord",
  "type": "object",
  "required": ["symbol", "family", "reward", "enqueued_at"],
  "additionalProperties": false,
  "properties": {
    "symbol": {
      "type": "string",
      "description": "期货品种代码（小写），如 jm/lh/cj",
      "pattern": "^[a-z]{1,4}$"
    },
    "family": {
      "type": "string",
      "description": "协变量家族名称（来自 cascade.cov_family.resolve_cov_family）",
      "examples": ["momentum", "oi", "volatility", "regime", "microstructure"]
    },
    "reward": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Bandit 奖励。1.0 = 该协变量历史有 gate_pass；0.0 = 无"
    },
    "enqueued_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO-8601 UTC 时间戳，提案入队时刻"
    }
  }
}
```

### 示例记录

```jsonl
{"symbol": "jm", "family": "momentum", "reward": 1.0, "enqueued_at": "2026-10-21T02:15:30Z"}
{"symbol": "lh", "family": "oi", "reward": 0.0, "enqueued_at": "2026-10-21T02:16:01Z"}
```

### 消费约定（B2 合成器）

- 按 `family` 分桶聚合：
  - `pulls`: 总入队次数
  - `successes`: reward=1.0 的次数
  - `success_rate`: successes / pulls
- **Batch Bandit** 模式（按代批式更新，非在线逐次）
- 最小样本量门槛：**N >= 30** 才参与 KL/JS 散度告警

---

## 2. 输出侧 — research_agenda_gen{N}.yaml Schema（草案）

**写盘方**: `scripts/synthesize_agenda_from_feedback.py`（B2 离线合成器，待实现）
**路径**: `task_FM/experiments/run_*/agendas/research_agenda_gen{N}.yaml`
**消费者**: Praxist peer（只读渲染 prompt 上下文）

### 结构来源

基于 C0 实测文件 `task_FM/experiments/run_2026-10-13_19-04-43_primary_task_FM/agendas/research_agenda_gen2.yaml` 提取。C0 冒烟验证 2 已确认 Schema 完整性 PASS。

### YAML Schema（草案）

```yaml
# 顶层元信息（必填）
generation: integer           # 当前代序号，与文件名 gen{N} 对齐
synthesized_from_gen: integer # 合成所基于的上一代
synthesized_at: string        # ISO-8601 UTC 时间戳

# 主线观察（必填）
mainline_observation:
  current_dominant_mechanisms: list[string]   # 当前主导机制清单
  main_risk: string                           # 主要风险描述
  key_tradeoff: string                        # 关键权衡

# 跨 peer 假设列表（必填，至少 1 条）
cross_peer_hypotheses:
  - id: string                # 假设 ID，如 H_g2_01
    claim: string             # 假设陈述（自然语言）
    source_findings:          # 来源 findings
      - finding_id: string    # UUID
        peer: string          # 来源 peer（如 gen0_peer0）
        role: string          # 来源角色（如 performance_anchor）
    minimal_test: string      # 最小验证测试
    kill_condition: string    # 终止条件
    promote_condition: string # 晋升条件
    bottleneck_target: string # 瓶颈目标类型
    evidence_stage: string    # scout | validating | confirmed
    tradeoff_class: string    # 权衡类别
    primary_tradeoff: string  # 主要权衡
    next_step_intent: string  # 下一步意图
    parent_candidate: string  # 父候选（可为空字符串）
    parent_usage: string      # none | partial | full
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| generation | int | yes | 当前代序号，与文件名 gen{N} 对齐 |
| synthesized_from_gen | int | yes | 合成所基于的上一代 |
| synthesized_at | str | yes | ISO-8601 UTC |
| mainline_observation | obj | yes | 主线观察，供 peer 了解全局态势 |
| cross_peer_hypotheses | list | yes | 跨 peer 假设列表，每个 peer 从中选取执行 |

### 示例片段

```yaml
generation: 2
synthesized_from_gen: 1
synthesized_at: "2026-10-21T03:00:00Z"
mainline_observation:
  current_dominant_mechanisms:
    - oi_gated_momentum
    - regime_gated
  main_risk: Surface entropy critically low
  key_tradeoff: Balance refining momentum vs mandatory exploration
cross_peer_hypotheses:
  - id: H_g2_01
    claim: OI-gated momentum has boundary conditions...
    source_findings:
      - finding_id: 03317c78-7e4d-431a-88c5-d2f22d578c96
        peer: gen0_peer0
        role: performance_anchor
    minimal_test: Extend to lh and test on cj...
    kill_condition: If fails on both high-concentration symbols...
    promote_condition: If lh achieves gate_pass with fdr_pass...
    bottleneck_target: process_or_evidence_gap
    evidence_stage: scout
    tradeoff_class: incomplete_evidence
    primary_tradeoff: custom
    next_step_intent: preserve_and_validate
    parent_candidate: ""
    parent_usage: none
```

---

## 3. Schema 演进规则

1. **输入侧（feedback）**：已冻结。新增字段须向后兼容（`additionalProperties: false`，新增须显式声明）。
2. **输出侧（agenda）**：草案阶段。C0 验证 PASS 后定稿；后续新增字段须保持 peer 向下兼容（peer 应忽略未知字段）。
3. **版本标记**：当前 Schema 未带版本号。若后续出现 breaking change，在顶层加 `schema_version: 2` 字段。

---

## 4. 验证清单

- [x] feedback Schema 与 `sup_harvest.py::_write_bandit_feedback()` 实际写盘字段一致（4 字段：symbol/family/reward/enqueued_at）
- [x] agenda Schema 与 C0 实测文件 `research_agenda_gen2.yaml` 结构一致（C0 验证 PASS）
- [x] C0 冒烟验证 2（Agenda Schema 验证）PASS — 包含全部必要字段
- [ ] B2 合成器实现后，补充端到端集成测试（feedback 文件 -> agenda 文件）

---

**下一步**: Task 1-3 A2 plugin 骨架 -> Task 1-4 B2 离线合成器
