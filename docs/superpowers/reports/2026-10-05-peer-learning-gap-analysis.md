# Peer 学习机制断裂分析报告

> 日期：2026-10-05
> 触发：用户提问「peer们是否可以从历史成果中学习到更有效果的方向、方法？」
> 方法：检查 peer memory 文件、shared findings、cycle 结果、cross-run 持久化存储

## 结论

**Peer 几乎没有从历史成果中学到东西。** 225 个 cycle 的评估结果从未被结构化地回传给 peer，peer 每次提案本质上是在没有历史数据的情况下做决策。

## 1. Peer 当前学习通道盘点

| 通道 | 状态 | 说明 |
|------|------|------|
| Run 内 session 记忆 | ✅ 有 | peer_state.yaml + experiment_ledger.jsonl + session_handoff.md |
| Peer 间共享发现 | ✅ 有 | shared_findings 里可看到其他 peer 的假设 |
| Cross-run 持久记忆 | ❌ 空 | research_memory.jsonl = 0 行，shared_store.db = 0 bytes |
| Cycle 结果回传 | ❌ 无 | gate pass/fail 结果不回写给 peer |
| Cross-run 历史统计 | ❌ 无 | 新 run 启动时 peer 从零开始 |

## 2. Peer 的「学习」实质

Peer 在做一种**伪学习** —— 引用「Passing family migration」策略：

- `"Passing family (inventory: 3 gate_pass) to ss"`
- `"Passing family (calendar: 6 gate_pass) to sr"`
- `"momentum (dominant family with 22 gate_pass)"`

但这些数字**来源不明** —— peer 看不到 cycle 结果数据，可能来自：
- 其他 peer 的 notes（二手信息传递）
- 共享 findings 里的定性描述推断
- LLM 编造（幻觉）

## 3. 关键断裂点

```
225 个 cycle 执行 → gate pass/fail 写入 cycle summary
                                                ↓
                                        ❌ 没有人把结果告诉 peer
                                                ↓
                                        peer 下一轮提案 = 盲猜
```

Peer 的 experiment_ledger.jsonl 只记录自己**提了什么**，不记录**评估结果如何**。

## 4. 证据 vs Peer 认知矛盾

Peer 声称 momentum 有 22 个 gate_pass，实际数据：

| 日期 | momentum 实际通过率 | 样本量 |
|------|-------------------|--------|
| Oct 4 | 31%（17/55） | 55 |
| Oct 5 | 59%（24/41） | 41 |
| 累计 | ~41%（41/96） | 96 |

Peer 说的「22 gate_pass」可能是跨所有 run 的累计，但这个数字从未被系统注入给 peer。

## 5. 两天 Gate Pass 对比

### 整体

| 日期 | 通过率 | Variants |
|------|--------|----------|
| Oct 4 | 39.2% | 130 |
| Oct 5 | 62.0% | 50 |
| 变化 | +22.8pp | - |

### 品种维度

| 品种 | Oct 4 | Oct 5 | 变化 |
|------|-------|-------|------|
| m (豆粕) | 27% (3/11) | 100% (6/6) | +73pp |
| jd (鸡蛋) | 45% (5/11) | 80% (12/15) | +35pp |
| rb (螺纹) | 42% (8/19) | 64% (9/14) | +22pp |
| lh (生猪) | 56% (14/25) | 0% (0/4) | -56pp |
| ss (不锈钢) | 44% (8/18) | 29% (2/7) | -15pp |

### 协变量族维度

| 族 | Oct 4 | Oct 5 | 变化 |
|----|-------|-------|------|
| term_structure | 51% (20/39) | 78% (7/9) | +27pp |
| momentum | 31% (17/55) | 59% (24/41) | +28pp |
| calendar | 56% (10/18) | - | - |
| volatility | 22% (4/18) | - | - |

Gate pass 率的提升（39% -> 62%）**不太可能是 peer 学习的结果**，更可能是：
1. 10/04 的 v4 确认通道修复（e155474, f4e8e90）改善了评估逻辑
2. 新协变量入队（pmi / crack_spread_acceleration）
3. 随机波动 + 品种轮转

## 6. 与 10-03 范式审计的关系

10-03 审计已识别「记忆回路断裂」—— 拒收理由不回写 peer。当时修了：
- D2: 死亡族名单（death registry）
- D3: 协议指纹回流给 peer

但**最核心的 gate pass 结果回传仍未实现**。本次分析确认了这个缺口依然存在。

## 7. 建议：Cross-Run Feedback Channel

要让 peer 真正学习，需要：

```
每个 cycle 结束 →
  提取 gate pass 结果（variant_id, symbol, family, passed）→
  聚合成 family x symbol 统计矩阵 →
  持久化到 data/assets/cross_run_learning.jsonl →
  注入下一个 run 的 peer memory_prompt →
  peer 据此决定探索方向
```

### 具体实现路径

1. **Cycle 结果聚合器**：在 supervisor 层，每个 cycle 完成后提取 gates_tail，按 (symbol, family) 聚合 pass/fail 统计
2. **持久化存储**：写入 `data/assets/cross_run_learning.jsonl`，格式：

```json
{"ts": "...", "symbol": "m", "family": "momentum", "pass": 6, "fail": 4, "rate": 0.6}
```

3. **Peer 注入**：新 run 启动时，读取最新统计，写入 memory_prompt 的 `Historical Gate Pass Statistics` 段
4. **Peer 提示词纪律**：要求 peer 在提案时引用历史统计，而非凭直觉

### 预期效果

- Peer 能避开低通过率组合（如 volatility on p: 0%）
- Peer 能集中探索高通过率方向（如 momentum on m: 100%）
- 减少无效提案，提升 gate pass 率

## 8. 状态

| 项目 | 状态 |
|------|------|
| 问题识别 | ✅ 已完成（10-03 审计 + 本报告） |
| 设计 spec | ❌ 未写 |
| 实现 | ❌ 未实现 |
| 验证 | ❌ 未验证 |

---

*本报告是 10-03 三环范式审计的后续发现，聚焦 peer 学习机制的定量分析。*
