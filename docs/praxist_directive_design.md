# PRAXIST 探索指令发布机制设计 (2026-09-02)

## 1. 问题定义

协变量搜索的质量不取决于尝试数量, 而取决于每代指令的信息增量。
首次真实 run (run_2026-09-01_23-18-14) 暴露的断链:

- 提示词模板纯静态, praxist 计算的议程/前沿/变体提示全部被丢弃;
  四份 peer 提示逐字节相同, 每代没有累积任何方向修正。
- cohort=2 无法满足 PI 议程 4 角色校验, 议程从未生效。
- peer 评估输出写进 peer workspace, orchestrator 看不见, 证据链断裂。
- 诊断档 (max_points<=6) 结构性无法通过 n>=350 硬门, 证据永远无法成熟。

结论: 指令 = 议程 x 角色契约 x 评估阶梯 x 证据路径, 四者缺一不可。

## 2. 指令闭环

每代指令的生命周期 (闭环, 缺环即退化为随机搜索):

    PI 面板 (读 frontier + falsifications + findings)
      -> research_agenda_genN.yaml (cross_peer_hypotheses + peer_contracts)
      -> prompt_generation.jinja2 渲染 (每 peer 只看到自己的 contract)
      -> peers 执行 (diagnostic 筛 -> aligned 确认)
      -> 评估摘要落 canonical results 树 (自动物化为 result finding)
      -> 假设/洞见经 share_finding 挂 metric_refs (provenance=agent)
      -> frontier 更新 -> 下一轮 PI 以证据修订议程

## 3. 五个设计原则

### P1 结构化假设卡 (mechanism-first)
每个候选必须先回答"为什么这个协变量对这个品种应该有效", 未通过则不许跑:
- CCL / ccl_value: 主力资金净持仓力量, 适合持仓驱动品种
- basis_momentum: 期现结构收敛/发散, 适合基差活跃品种
- rsi_state / rsi_slope: 超买超卖状态与斜率, 适合震荡回复品种
- ha_body: K 线实体动能, 适合趋势延续品种
- calendar_cyclical: 季节性/交割月效应
- reversal_shadow / hourly_slope / oi*: 反转影子 / 小时斜率 / 持仓量异动
假设卡字段: claim, mechanism, minimal_test, kill_condition, promote_condition.

### P2 证据阶梯 + 多重比较预算
- diagnostic (p3/p6): 快筛, 每代可大量跑, 结构性不过硬门 (n<=6 << 350)
- aligned (350..500): 近全量 WF, 可过硬门 (n>=350 AND IC>=0.05 AND ev>0),
  但每 peer 每代限额 2 次 —— aligned 预算是假发现率的直接控制手段
- complete: replication (换 seed/窗口) 才允许 close
- 死亡规则: aligned 一次失败的候选即死, 除非 PI 以机制修正为由复活

### P3 角色分工映射到证伪结构 (cohort=4)
- exploit: 把诊断幸存者推过 aligned 门 (排行榜推进)
- falsifier: 构造消融对照 (同窗口去掉协变量), 机制主张若与对照无差异即证伪;
  产 finding_type=challenge
- bridge: 两个非冗余族融合 (如 CCL x rsi_state), 必须双消融
- anti_mainline: 强制覆盖被忽视族 (oi, ccl, basis_momentum, calendar),
  防 frontier 单一化 (HHI 多样性)

### P4 证据纪律 (让 orchestrator 看见一切)
- 评估摘要唯一合法路径: results/gen_<N>/<peer_id>/<variant_id>/<stage>/
- 假设/洞见/挑战走 share_finding MCP (带 peer_id/metrics/links),
  文件系统笔记 provenance 降级 legacy_weak
- result finding 由评估摘要自动物化, 指标挂靠在 metrics 字典

### P5 每代指令的信息增量
PI 议程必须引用上一代证据: mainline_observation (当前主线是什么),
被证伪的机制 (falsification 记录), frontier 空缺的族。
禁止原样重发上代议程 —— 议程无增量等价于浪费一代预算。

## 4. 落地映射 (本次实现)

| 设计项 | 实现位置 |
|---|---|
| cohort=4 满足 4 角色 | task.yaml generation_policy |
| aligned 档 (mature/parent allowed) | task.yaml evaluation.staged_protocols + maturity_policy.complete_stage_labels |
| 阶梯感知评估器 | evaluations/fm_eval/evaluator.py (STAGE_POINTS, build_summary) |
| 证据完整摘要 (variant_name/metrics/stage) | run.py -> build_summary |
| 议程/前沿/提示渲染进提示词 | prompt_base.jinja2 + prompt_generation.jinja2 |
| canonical results 路径契约 | prompt_base.jinja2 Output discipline 节 |
| share_finding 纪律 | prompt_base.jinja2 Findings discipline 节 |
| Gems 固化通道开启 | task.yaml gems.enabled=true (aligned=1 成熟单元即可入 Gems) |
| 每代窗口 1.0h, 显式合成触发器 | task.yaml synthesis_trigger (min_findings=8, peers=2, max_interval=30) |

## 5. 预期信号 (下一次 run 的验收标准)

| 信号 | 上次 run | 目标 |
|---|---|---|
| PI 议程状态 | failed_non_strict | committed (4 角色齐) |
| findings provenance | 全部 legacy_weak | result finding 出现 agent 级, metric_refs 非空 |
| frontier_records | 0 | >=1 (aligned 幸存者进入 incubator/frontier) |
| 每代提示词差异 | 4 份逐字节相同 | 每代含该代角色契约 + 上一代证据引用 |
| Gems | 0 (通道关闭) | >=0 (通道开启, 有 aligned 过门者即固化) |

## 6. 已知残余风险
- 4 peers x 1.0h x 3 gens 最坏 ~12 peer-hours token 消耗 (上次 ~5M tokens/18min,
  按比例估算最坏 30M+); 建议 max_generations 保持 3 观察 2 代即评
- aligned 350..500 点全量 WF 单次约 5-15 分钟, cohort=4 下调度器串行执行
  可能挤压 peer 时间预算 (compute_budget.max_parallel_runs_per_peer=1)
- falsifier 的消融对照若与 treatment 同路径, 会引入共享随机性;
  kill 判定应要求对照与 treatment 的 PF 差异方向性一致
