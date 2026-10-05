# 术语表（glossary）

> 每个术语给出**代码锚点**——定义以代码为准，本文只做索引与一句话解释。
> 阈值类术语见 [evaluation.md](./evaluation.md)；运行合同见 [runtime_contract.md](./runtime_contract.md)；
> 数据类见 [data_dictionary.md](./data_dictionary.md)。
>
> 最后核实：2026-10-05，commit `ee01b56`。

---

## 三环结构

| 术语 | 含义 | 载体 |
|------|------|------|
| **监督环** | 外层调度器，**零 token**，每 300s 一个 tick 决定「起快环 / 收割 / 跑慢环」 | `scripts/praxist_supervisor.py` |
| **快环** | peer 生成**机制化假设提案**，**不加载 TimesFM** | `.venv` 内 Praxist 核心 |
| **慢环** | **唯一验证器**，唯一可写裁决注册表 | `scripts/aligned_slow_loop.py` |
| **cycle** | 监督环的一次完整循环 = 结束 run + harvest + 慢环抽干 | `supervisor_state.json:cycles_done` |
| **harvest** | 快环跑完后，监督环扫 `results/**/proposals/*.json` 入队 | `harvest_proposals()` |
| **Praxist** | 领域无关的**研究控制平面**（0.5.0）；本仓 `task_FM/` 提供科学合同 | `.venv`（**不可改**，升级会丢） |

---

## 提案与 peer

| 术语 | 含义 | 载体 |
|------|------|------|
| **peer** | 快环里的假设作者 agent，**只写假设不验证** | `task_FM/roles/peer_generalist/` |
| **exploit / falsifier** | 两种 peer 角色（挖掘有效方向 / 试图证伪）；`panel_topology: fm_two_peer` | `role.yaml: peer_role_rotation` |
| **mechanism** | 机制说明，**必须 ≥ 40 字** | 提案字段 |
| **failure_delta** | 与前次相比**改变了什么**，**必须 ≥ 20 字** | 提案字段 |
| **family** | 同一协变量族的研究单元，按 `(品种, horizon, …)` 分组 | `cascade/research_family.py` |
| **panel_topology** | peer 编队方式；本仓用 `fm_two_peer`（2 peer） | `.praxist/plugins/panel_topologies/` |

---

## 评估与裁决

> 阈值全部见 [evaluation.md](./evaluation.md)，此处只给概念。

| 术语 | 含义 |
|------|------|
| **DirAcc / dir_acc** | 方向准确率，主指标 |
| **n_eff** | Bartlett 有效样本量（重叠窗口去相关后） |
| **effective_min** | 自适应门槛——基线差时门槛自动降 |
| **DM 检验** | Diebold-Mariano，Newey-West HAC + HLN 校正 |
| **BH-FDR** | Benjamini-Hochberg 多重比较校正（per-symbol） |
| **gate_pass** | 硬门是否通过（**纯统计**，不含经济） |
| **fdr_pass** | 多重比较校正后是否通过 |
| **hard-gate-but-losing** | 过统计门但经济为负 |
| **run_mode** | `exploration` / `confirmation` |
| **confirmation** | 确认级通道，参数须**事先预注册** |
| **prereg_id** | 预注册唯一标识，32 位 hex |

---

## 协变量与 horizon

| 术语 | 含义 | 载体 |
|------|------|------|
| **协变量（covariate）** | 预测时附加的输入特征 | `cascade/features.py` |
| **6 族词表** | `momentum` · `calendar` · `inventory` · `macro_sentiment` · `term_structure` · `volatility` | `cascade/cov_family.py:ALLOWED_FAMILIES` |
| **horizon_known** | 该协变量**是否预先可知未来 horizon 段**，4 值受控词表 | `cascade/horizon_fill.py` |
| **`known_ahead`** | 真实可知（日历等）→ 直接用真值，**须有 `known_ahead_evidence`** | 同上 |
| **`persistence`** | 按 spec 填 **context 末值**（**替代历史 zeros / decay**） | 同上 |
| **`self_referential`** | 需自引用处理 | 同上 |
| **`unknowable`** | 不可知 | 同上 |
| **vocab 校验** | 缺 pool 条目或词表外 → **抛 `HorizonContractError`**，不静默兜底 | `horizon_fill.py:94` |
| **cov_fill** | 协变量缺失填充策略 | `COV_FILL_VERSION` |
| **roll_guard** | 换月守卫，防跨合约拼接 | `ROLL_GUARD_VERSION` |

> 分类唯一家在 `horizon_fill.py`（读 `covariate_pool.json`），
> **禁止按协变量名硬编码分类**。

---

## 协议与身份

| 术语 | 含义 |
|------|------|
| **protocol_fingerprint** | 七组件指纹，标识评估协议版本；**bump ⇒ 基线不可比** |
| **variant_id (vid)** | 变体唯一标识，**两种历史格式并存**（见下） |
| **checkpoint 命名空间** | `{vid}__prereg_{id[:8]}.jsonl`，防 resume 混入探索点 |
| **batch_id** | 一批裁决的标识 |
| **migrate v1→v2** | 历史裁决 schema 迁移，`batch_id=migrated_v1` |

### ⚠️ vid 有两种格式（历史断层）

| 格式 | 样例 | 来源 |
|------|------|------|
| 旧 `{symbol}_{cov}` | `cf_rsi6` | Stage 3 之前 |
| 新 `{symbol}_{family}_{fp12}` | `lh_momentum_e5272a12ce30` | `ef.build_variant_id()` |

**读历史行不要假设格式统一。** 生成方：`praxist_supervisor.py` 3 个调用点（373 / 1167 / 2146）。

---

## 品种状态

| 术语 | 含义 | 载体 |
|------|------|------|
| **信用档 / star** | 0–3 星；**当前无真实 3 星** | `config/prediction_scheme.py::list_by_stars` |
| **`SYMBOL_DEAD`** | **品种级**停止探索（人手改 JSON） | `config/symbol_status.json` |
| **`HOLD`** | 品种级暂停 | 同上 |
| **DEAD 家族** | **变体级**：同族 ≥4 条可确认 DM 裁决且 0 条过门 | `_dead_families(min_ok=4)` |

> ⚠️ **品种级 DEAD/HOLD 与变体级 DEAD 是两套状态机，别混名。**
> ⚠️ **不要硬编码品种清单**——以 `list_by_stars(2)` 为唯一事实源。

---

## 运行时状态

| 术语 | 含义 |
|------|------|
| **gems / frontier / findings** | Praxist 内部的 session / 探索前沿状态 |
| **shared_store.db** | Praxist 运行时 sqlite（**不是**面向 peer 的反馈通道） |
| **`research_memory.jsonl`** | 设计为跨 run 反馈——**当前全部 0 字节，未实现** |
| **`materialize_known_verdicts`** | 每轮把已知裁决物化成 `known_verdicts.inc.md` 供 peer 读 |
| **proposal 质量门** | 18 道，任一不满足即拒收 |

---

## 快速索引

| 我想知道… | 看 |
|-----------|------|
| 项目是什么、怎么跑起来 | [handbook.md](./handbook.md) |
| 依赖、环境、目录职责 | [tech_stack.md](./tech_stack.md) |
| 预测管线怎么设计 | [system_design.md](./system_design.md) |
| 三环怎么运行 | [runtime_contract.md](./runtime_contract.md) |
| 阈值与统计口径 | [evaluation.md](./evaluation.md) |
| 品种 / 协变量 / 数据表 | [data_dictionary.md](./data_dictionary.md) |
| 怎么启停、故障怎么查 | [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md) |
| 产物怎么分级、怎么清理 | [run_artifacts.md](./run_artifacts.md) |
| 任务包内部 | [../task_FM/AGENTS.md](../task_FM/AGENTS.md) |