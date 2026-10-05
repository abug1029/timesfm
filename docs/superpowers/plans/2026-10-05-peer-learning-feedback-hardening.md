# Peer 学习反馈硬化实施计划（T0-T5）

> **日期**: 2026-10-05
> **来源**: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis-review.md`（评审裁定的真实缺口 G1-G6）
> **原报告**: `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis.md`（其 §7 方案经评审否决，理由见评审 §四）
>
> **设计原则**:
> 1. registry 保持唯一事实源——新增产物一律为可再生视图（digest），不建第二事实源
> 2. 一切注入/引用统计必须带协议指纹 + 样本量 + as-of 戳
> 3. 提示词纪律扩展优先于新机制（failure_delta 先例）
> 4. 任何拒收门必须带逃逸阀（09-24 no_failure_delta 饿死教训，supervisor:1920 注释）
> 5. 不触碰 gate 评估语义——协议指纹不变，零基线重生

## 0. 目标

把「peer 主动才有」的跨 run 定量反馈（评审 §2.1：今日 peer 自算 22/3/6 属例外而非常态）升级为「系统保证送达」；补上成功侧执法；根治统计僵尸化与样本量滥用；将协议轮换遗忘显式化。

## 1. 任务分解

### T0（P0 · docs）原报告勘误

- [ ] 文件：`docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis.md`
- 内容：
  1. 顶部加勘误块：结论改写为「学习回路存在且运行中（PI agenda 回路 + no_failure_delta 拒收门 + peer 自主 registry 读取），但反馈无系统保证、成功侧无执法、统计引用无溯源纪律」，指向评审报告
  2. §1 通道表补三行：registry 通道（peer 可读且实测在读）/ PI agenda 回路（运行中）/ no_failure_delta 拒收门（执法中，supervisor:2150）
  3. §2/§4 撤销「来源不明/可能幻觉/矛盾」表述，改记「22/3/6 为当前协议过滤精确统计；原复核 41/96 混用协议版本」
  4. §5 归因重写：加入 10-04 16:55 数据恢复断点（37.0%→58.3% 同日）；删除「v4 修复改善评估逻辑」（机制不成立，E1-E6 未触碰 gate 评估）；所有表格补数据来源与查询
- 依赖：无
- 验收：报告不含未修订的「盲猜/幻觉/矛盾」断言；所有数字标注协议口径与查询

### T1（P1 · 新脚本）Registry Digest 生成器

- [ ] 新文件：`scripts/build_registry_digest.py`（CLI：读 registry → 产出 digest；幂等；原子写 tmp+rename）
- 输出：`task_FM/config/registry_digest.md`（与 registry 同目录，peer 沙箱已证可读）+ `.gitignore` 追加该路径
- 过滤规则（与收割纪律一致，`045c7e2`）：
  - 仅 `status == "ok"`
  - 仅当前协议：`protocol_fingerprint ==` `task_FM/evaluations/fm_eval/evaluator.py::compute_protocol_fingerprint` 现算值
- 内容规格：
  1. 头部戳：`generated_at`（ISO）+ `protocol_fp8` + ok 行数 + 源文件 mtime
  2. symbol×family 矩阵：`(pass, n)` 格式；`n < 10` 追加 `low-n` 标记；**不出现裸比率**（S4）
  3. 成功清单：gate_pass=True 行（variant_id / symbol / family / fdr_pass / dir_acc / decided_at）
  4. 近失清单：gate_pass=False 且 `dir_acc >= effective_min - 0.02`（或 dm_status 未决）
  5. DEAD 清单：gate_pass=False 非近失（与 prompt_base「变体级 DEAD」纪律对应）
  6. 历史协议注记（S5 并入）：每个 (symbol, cov) 如存在 v2/v3 先验裁决，一行摘要 + 明示「仅上下文，不构成当前证据」
- 新测试：`tests/test_registry_digest_20261005.py`（fixture 构造混合协议 registry：矩阵 / low-n / 近失边界 / 历史注记 / 头部戳）
- 依赖：无
- 验收：CLI 幂等重跑输出稳定（除时间戳）；测试过；手动核对 v4 统计与评审 §2.1 一致（momentum (22,50)、inventory (3,13)、calendar (6,10)）；`git status` 确认 digest 不入版本库

### T2（P1 · supervisor）Digest 挂钩

- [ ] 文件：`scripts/praxist_supervisor.py`
- 触点：① supervisor 启动时；② 慢环批次回收完成后（verdicts 落账之后，避免竞态）
- 工程：digest 生成失败不得影响主管循环（try/except + warning 日志，参照既有 `_log_decision` 模式）
- 依赖：T1
- 验收：批次回收后 digest mtime 更新；人为制造 digest 异常时 supervisor 正常推进

### T3（P1 · prompt）prompt_base 注入指引

- [ ] 文件：`task_FM/prompt_base.jinja2`
- 内容（提案 schema 与记忆纪律两处）：
  1. 「提案前必读 `task_FM/config/registry_digest.md`」
  2. 引用纪律（S3/S4 prompt 侧）：任何引用统计必须写 `(pass, n)` + `as-of 日期` + `fp8`；`n < 10` 不得表述为百分比结论
  3. anti-anchoring checklist 追加：「你引用的数字今天还成立吗（对照 digest 头部戳）」
- 依赖：T1（digest 存在才有得读）
- 验收：新 run 渲染出的 generation prompt 含该块（取实际 run 的 prompt 文件实证）

### T4（P2 · supervisor）success_delta 拒收门

- [ ] 文件：`scripts/praxist_supervisor.py`（`no_failure_delta` 同域，:2150 附近）+ `task_FM/prompt_base.jinja2`（proposal schema 增加可选字段说明）
- 规则：
  - 命中条件：提案 (symbol, cov_override) 在当前协议 registry 中存在 `gate_pass=True 且 fdr_pass=True` 的 ok 裁决
  - 要求：`success_delta` ≥20 字，点名 settled variant_id + 本次增量
  - 拒收码：`no_success_delta`（计数日志与 no_failure_delta 同模式）
  - **逃逸阀**：settled 裁决 `decided_at` 距今 >14 天 → 放行并记 notice（评估窗口已移动，重测合法；防 09-24 型饿死）
- 新测试：`tests/test_success_delta_gate_20261005.py`（命中拒收 / 未命中放行 / 逃逸阀 / 长度校验四路径）
- 依赖：T1（复用成功清单判定逻辑）
- 验收：测试过；拒收计数入日志

### T5（P2 · 部署与观察）重启部署 + 两周观察

- [ ] 部署：按 runbook TERM 重启程序（注意：停止标记在 `data/cache/stop_report.json` / `supervisor_events.jsonl`，即时退出——见 `docs/supervisor_restart_backlog.md` 2026-10-04 勘误）；重启前协议指纹校验（本计划不触碰评估语义 → fp 应不变、零基线重生，仍须实测确认）
- 观察指标（两周）：
  1. PI agenda 的 main_risk「over-proposing without validation gates」是否消退（PI 自诊即现成验收锚点）
  2. peer handoff / proposal 引用是否带 `(pass, n)` + as-of + fp8
  3. `no_success_delta` 拒收量与慢环队列深度（无饿死）
  4. 下次窗口移动事件（10-08 国庆后开闸）时 peer 引用 digest 而非僵尸数字
- 依赖：T2 / T3 / T4 全部合入
- 验收：观察项 1-3 达成；观察项 4 首次实测留档

## 2. 明确不做

- 不新建 `data/assets/cross_run_learning.jsonl` 第二事实源（评审 §四）
- 不改框架（site-packages 的 memory_prompt 渲染、PI panel 机制）
- 不改 gate 评估语义（协议指纹不变）
- 不动 `research_memory.jsonl`（框架脚手架占位，非 repo 职责）

## 3. 顺序与依赖

```
T0（独立，先行）
  └─ T1 → T2 → T3   （P1 串行：digest 生成 → 挂钩 → prompt 注入）
        └─ T4       （复用 T1 成功清单逻辑）
             └─ T5  （全部合入后部署观察）
```

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| prompt 变更改变 peer 行为分布，gate_pass 率波动 | 归因时先查数据/窗口断点（评审 §2.4 教训），再查 prompt 变更 |
| success_delta 过严饿死慢环（09-24 同构） | 14 天逃逸阀 + 慢环队列深度监控 |
| digest 与 registry 短暂不一致（落账与生成竞态） | digest 头部带源 mtime；T2 触点放在批次回收完成后 |
| digest 误入版本库 | T1 内含 `.gitignore` 追加；验收含 `git status` 检查 |
| 10-08 开闸后确认流量叠加观察期 | T5 观察项 4 与确认通道观察（E1/E2）合并跟踪，避免双重归因混淆 |

---

*本计划为 `reports/2026-10-05-peer-learning-gap-analysis-review.md` 的落地件；执行遵循 09-28 纪律：实现前隔离 worktree 回归（失败集与 HEAD 恒等）、提交后先验指纹再重启。*
