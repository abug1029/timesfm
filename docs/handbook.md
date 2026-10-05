# FM_a 技术手册（handbook）

> **入口文档。** 面向新人与新 agent 的阅读路径。
> 读这一页之后，你应该知道去哪找答案——不需要读完所有文档。

最后核实：2026-10-05，commit `ee01b56`。

---

## 1. 这是什么

FM（`timesfm`）是一个**中国商品期货的量化研究系统**，做两件事：

1. **级联预测** —— 用 TimesFM 时序模型预测品种价格方向，输出可交易建议
2. **Praxist 三环研究** —— 让 LLM agent 自动提出「换哪个协变量」的假设，并用统计门禁裁决

两者共享数据层与评估口径。**生产上真正在跑的是三环**。

> 产品定位：辅助判断，**非自动交易**。可交易方向 = 加权 1H 级联结果，日线斜率仅作 regime 副标签。

---

## 2. 5 分钟上手

```bash
cd /home/abug/timesfm
source .venv/bin/activate

# 盘中主观（推荐入口）
python scripts/copilot.py ss fu

# 生产级联预测
python scripts/cascade_predict.py ss

# 数据采集
python scripts/data_management.py --1h --daily

# 三环（生产监督环）
scripts/start_supervisor.sh
```

⚠️ **必须在 WSL**。Windows 侧的副本已不存在（2026-09-29 核实）。

---

## 3. 按需查什么

### 我想理解系统怎么работать

| 问题 | 读 |
|------|-----|
| 预测管线怎么设计（数据流 / 级联 / 协变量 / 信号） | [system_design.md](./system_design.md) |
| 三环的架构与两层关系（Praxist 本体 vs 本仓三环） | [praxist.md](./praxist.md) |
| 三环的**运行合同**（门判据 / 指纹 / family / 预注册） | [runtime_contract.md](./runtime_contract.md) |
| 资源治理（内存红线 / 429 failover / Session 解卡） | [superpowers/specs/praxist_control_plane.md](./superpowers/specs/praxist_control_plane.md) |

> ⚠️ 后两份**同名不同物**：`runtime_contract.md` 是运行合同，
> `superpowers/specs/praxist_control_plane.md` 是资源控制 spec。

### 我想知道"多少/是什么"

| 问题 | 读 |
|------|-----|
| **阈值是多少**（n / n_eff / effective_min / FDR α） | [evaluation.md](./evaluation.md) ← **唯一权威** |
| 品种 / 协变量族 / 数据表 / 字段 | [data_dictionary.md](./data_dictionary.md) |
| 这个词什么意思（DEAD / vid / horizon_known…） | [glossary.md](./glossary.md) |
| 依赖 / 环境 / 目录职责 | [tech_stack.md](./tech_stack.md) |

### 我要动手

| 任务 | 读 |
|------|-----|
| 启停 / 故障排查 | [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md) · [runbook.md](./runbook.md) |
| 长任务操作规范 | [long-task-sop.md](./long-task-sop.md) |
| 改运行产物 / 清理 | [run_artifacts.md](./run_artifacts.md) |
| 改 task_FM 下的东西 | [../task_FM/AGENTS.md](../task_FM/AGENTS.md) |

### 我要了解历史与决策

`docs/superpowers/` —— **spec**（设计论证）· **reports**（核验）· **changelogs**（实施证据链）· **plans**（施工单）。
历史文档 `docs/archive/`（已归档，勿作当前口径）。

---

## 4. 文档分层

```
L0 手册层   handbook.md（本文）· glossary · tech_stack · data_dictionary
L1 规范层   system_design · runtime_contract · evaluation ← 单一权威
            runbook* · run_artifacts · task_FM/AGENTS.md
L2 证据层   superpowers/{specs,reports,changelogs,plans} · archive/
```

**L1 是规范**——改代码前先查 L1，改完同步 L1。
**L2 是证据**——不合并、不重写，只链接。

---

## 5. 给新 agent 的硬约束

| 约束 | 说明 |
|------|------|
| **不在文档里钉活快照** | PID / cycles_done / 裁决条数 / run 计数都会腐烂，一律指向代码或查询命令 |
| **不硬编码品种清单** | 以 `list_by_stars(2)` 等代码为唯一事实源 |
| **阈值只认 `evaluation.md`** | 其他地方只能链接，不能复述数字 |
| **peer 不加载 TimesFM、不跑评估** | 方案 A 的核心约束 |
| **慢环是裁决唯一写入者** | 不要手改 `aligned_verdicts.jsonl` |
| **不手改运行产物** | `known_verdicts.inc.md` / `covariate_menu.inc.md` 每轮重新物化 |
| **不跑 `git clean -xdf`** | ⚠️ 会同时删除裁决原件 + 全部归档备份 |
| **不误判为过时** | 三类文档刻意留在原位：peer 提示词内嵌的 spec · 三环跟进合同 · changelog 证据链 |

---

## 6. 当前状态怎么查（别问人，查文件）

| 想问 | 查 |
|------|-----|
| 三环在跑吗？跑哪个阶段？ | `pgrep -f praxist_supervisor` · `data/cache/supervisor_state.json` |
| 当前有哪些裁决？ | `wc -l task_FM/config/aligned_verdicts.jsonl` |
| 哪些品种信用≥2★？ | `python -c "from config.prediction_scheme import list_by_stars; print(list_by_stars(2))"` |
| 当前卡在什么门？ | `STATE.md` |
| 协议指纹是多少？ | `evaluator.py:284` 定义 + 基线行内字段 |

> **状态类文档（`STATE.md`）与代码冲突时，以代码为准**——
> `STATE.md` 自称「唯一事实所有者」，但它也会腐烂（历史上钉过假 PID 与假裁决数）。

---

## 7. 相关文档

- 人类文档索引：[README.md](./README.md)
- Agent 会话约定：根 [../AGENTS.md](../AGENTS.md) · [../CLAUDE.md](../CLAUDE.md)
- 产品红线：[product_positioning.md](./product_positioning.md) · [module_freeze.md](./module_freeze.md)