# FM_a PRAXIST 三环自治架构设计 (Spec)

日期: 2026-09-02
状态: 待审阅
前序文档: docs/praxist_integration_plan.md, docs/praxist_directive_design.md

## 1. 背景与问题

PRAXIST 在 task_FM 任务包上的首次真实运行验证了 run 内自主迭代
(PI 议程 4 角色成功提交, 4 份 peer 提示词各异, 11 findings/代),
但暴露了三个不可回避的计算事实:

- F1: 每 walk-forward 评估点约 60s (daily 18-25s + hourly 33s, 2 核 CPU)
- F2: 预注册硬门要求 n>=350, 即 aligned 单次评估 6-8h, 无法塞进任何代窗
- F3: LLM 网关配额为 5 小时滚动窗, 曾中断 run (429)

在 run 内做 aligned 评估的架构不可行。同时用户的核心诉求是:
指定目标后系统自主编排、自主执行、直到目标达成或预算耗尽。

## 2. 设计决策总览

| 决策 | 选择 | 放弃的备选 |
|---|---|---|
| aligned 执行位置 | 代窗外慢环 (离线) | 超长代窗 (token 效率极差) |
| 硬门口径 | 维持 n>=350 (与 G005-E 可比) | 放宽到 n>=120 (破坏预注册) |
| daily 推理 | 按 (symbol, cutoff) 缓存复用 | 无缓存 (每候选 6-8h) |
| 跨 run 编排 | 监督环 (纯 Python, 0 token) | 人工 cron / LLM 驱动 |
| 目标指定 | goal.yaml 预注册可测量条件 | 自然语言目标 (不可判定) |

## 3. 架构

三环职责边界 (每环一个失败域, 互不传染):

    [监督环 supervisor]  纯 Python, 0 token, 常驻可选
      v 读 goal.yaml, 判定 success/budget, 调度快慢环, 写决策日志
      |
      +--> [快环 praxist run]  烧 token, ~2h, 有界
      |      PI 面板 + 4 角色 peers + diagnostic 筛选
      |      产出: 诊断幸存者 -> pending 队列
      |
      +--> [慢环 aligned_slow_loop]  纯 CPU, 0 token
             daily 缓存 + checkpoint 续跑 + verdict 裁决
             产出: verdict -> 注册表 (append-only)

数据流 (每周期 cycle = 快环一次 + 慢环清队列):

    goal.yaml ──> supervisor 判定
        | 未达成且预算未耗尽
        v
    praxist run (贴配额窗口启动)
        | run_summary + frontier 幸存者
        v
    supervisor 收割 -> aligned_pending.jsonl (去重: 已死者不入队)
        | harvest 非空则立即慢环 (phase=slow, 禁止下一轮快环)
        | harvest 空则本 cycle 完成, 尝试下一轮快环
        v
    aligned_slow_loop (checkpoint 续跑) 直到 pending+inprogress 空且 flock 释放
        | 每候选一个 verdict
        v
    aligned_verdicts.jsonl ──> 下一次 run 的提示词引用 (已过门/已死)
        |
        └──> supervisor 回到判定 (goal 条件更新; 配额不够则 wait_quota)

## 4. 组件设计

### 4.1 daily 预测缓存 (scripts/monthly_backtest.py 内)

- 动机: daily_model.predict() 不接收协变量参数 (已核实源码),
  daily 预测是 (symbol, cutoff) 的确定函数, 与候选协变量无关。
- 接口: run_symbol_backtest(...) 增加 daily_cache_dir 参数 (默认 None=关),
  命中则跳过 daily 推理; 未命中则计算后落盘 pickle。
- 键: f"{symbol}|{cutoff}|{CONTEXT_DAYS}x{HORIZON_DAYS}|{model_fp[:12]}"
  model_fp = TimesFM 权重文件 sha256 前 12 位 (一次性计算, 结果存 data/cache/daily_pred/.model_fp 复用; 模型升级自动失效)。
- 失效: 键含模型指纹与窗口参数, 升级即整体 miss, 旧文件可脚本清理。
- 验证 (实施时 TDD): 同 symbol 取 3 个 cutoff, A/B 对比缓存命中 vs
  强制重算, daily_result.point_forecast 必须逐位一致 (np.array_equal)。
- 落盘位置: data/cache/daily_pred/ (gitignored, 只增不删可脚本清理)。

### 4.2 慢环驱动器 (scripts/aligned_slow_loop.py, 新文件)

- 输入: data/cache/aligned_pending.jsonl (队列, supervisor 写, 瞬态)
- 每行: {"variant_id", "symbol", "cov_override", "max_points",
          "stage": "aligned", "checkpoint_path", "enqueued_at", "src_run"}
- 流程: 取队首 -> run_symbol_backtest(--resume checkpoint) ->
  build_summary -> verdict 写注册表 -> 队列文件原子重写 (剩余行, done 行移入 data/cache/aligned_pending.done.jsonl)
- checkpoint: data/cache/aligned_checkpoints/<variant_id>.jsonl
  (monthly_backtest 原生 --resume 机制, 按 (symbol, idx) 合并)
- 单实例锁: flock data/cache/aligned_slow_loop.lock, 防双跑。
- 停止: 任意时刻可 SIGTERM; 重启后 checkpoint 续跑, 无损失。

### 4.3 verdict 注册表 (task_FM/config/aligned_verdicts.jsonl)

- append-only jsonl, 每行一个裁决:
  {"variant_id", "symbol", "cov_override", "max_points", "n", "pf", "ev",
   "maxdd", "dir_acc", "gate_pass", "ic", "decided_at", "checkpoint_path",
   "slow_loop_pid", "git_rev", "schema": "fm.aligned_verdict.v1"}
- 写权限: 仅慢环进程 (flock 持有者)。快环/peers/人工只读。
  红线将写入 loop-constraints.md: 伪造 verdict = 破坏预注册纪律。
- 语义: 同 variant_id 重复裁决 = 新行追加 (audit trail), 取最新行为准。
- 快环引用: prompt_base.jinja2 增 "Known verdicts" 节, 指示 peers 开工前
  读注册表; gate_pass=true 不再重试, false 即死亡 (P2 死亡规则)。

### 4.4 监督环 (scripts/praxist_supervisor.py, 新文件)

- 单进程, 纯文件与子进程操作, 不调用任何 LLM。
- 主循环 (每周期):
  1. 评估 goal.yaml success_condition -> 达成则出终报退出
  2. 评估 budgets -> 耗尽则出中途报告退出
  3. 快环调度: 解析最近 run 日志的 429 reset 时间戳;
     窗口剩余 >= run 预算时长 + 30min 余量 (按 goal.yaml 推算) 才 start; 否则 sleep 到重置点
  4. run 结束且非 429 pause -> 收割幸存者入队 (去重)。有行则 phase=slow 立刻启动慢环; 无行则 cycle+1
  5. phase=slow 时禁止 start 下一轮快环。队列空且慢环 flock 释放 -> cycle+1, phase=fast 或 wait_quota
  6. 配额不足只挡快环; 慢环 0 token, 抽干前继续跑
- 决策日志: .omc/supervisor_decisions.jsonl (append-only), 每动作一行
  {ts, action, reason, refs}, 事后可回放。
- 启动方式: nohup 常驻; goal 达成/budget 耗尽后自动退出。
- 明确非职责: 不修改 run 工件, 不重试 peer 失败 (那是 praxist 的事)。

### 4.5 goal.yaml (scripts/praxist_goal.yaml)

见 §2 目标指定原则, schema:
  goal.success_condition: 表达式列表 (DSL 见 §6)
  goal.budgets: {max_cycles, cpu_hours, token_budget_m, deadline}
  goal.cadence: {run_after_quota_reset, slow_loop_window}

## 5. success_condition DSL

目的: 让目标可判定, 监督环不调 LLM, 表达式必须可纯 Python 求值。
约束在 verdict 注册表快照上求值 (每个 cycle 重建快照 dict)。

可用变量: variants (全部裁决, 按 variant_id 最新行),
symbols_hit (gate_pass 且经济优越的品种集), families_hit (协变量族集),
cycles_done, cpu_hours_used, tokens_used_m。

表达式 = 白名单安全求值 (ast 模块, 仅比较/布尔/算术/下标/len/min/max/all/any,
禁止任意调用与属性访问)。所有聚合由监督环预算派生变量:
  - "len(symbols_hit) >= 3"
  - "min(pass_variant_pf_ratios) > 1.05"
  - "len(families_hit) >= 2"
pass_variant_pf_ratios = [v.pf / incumbent_pf(v.symbol), ...] 由监督环
从 verdict 快照与 SCHEMES (只读 import) 预计算, 表达式本身无调用。

## 6. 错误处理与恢复矩阵

| 故障 | 影响环 | 机制 | 数据损失 |
|---|---|---|---|
| peer 429 | 快环 | praxist 原生 billing-error 暂停 20min 重试, session 接续 | 0 (会话内) |
| 配额窗耗尽 | 快环 | supervisor 检测 -> stop -> 重置后 resume; 边界工件保留 | 0 (边界级) |
| 代内残局 | 快环 | praxist resume 识别 pending boundary 内部恢复 | 0 |
| 慢环被杀 | 慢环 | checkpoint (symbol,idx) 续跑 | 0 (点级) |
| 双跑冲突 | 慢环 | flock 单实例锁 | 0 |
| 机器重启 | 慢环+监督环 | 两进程均以文件状态为准, 重启即续 | 0 |
| 缓存投毒/损坏 | 慢环 | 缓存键含模型指纹; 损坏文件加载失败即重算 | 该点重算 |
| verdict 伪造 | 全局 | 写权限仅慢环 (flock), 红线入 loop-constraints | n/a |
| 目标写错 | 全局 | budgets 硬顶兜底; goal 变更走 loop-constraints 纪律 | n/a |

## 7. 测试策略

- 单测 (tests/): 缓存键构造/命中/模型指纹失效; DSL 安全求值 (注入拒绝);
  verdict 行 schema; 队列去重; 429 reset 时间戳解析。
- A/B 逐位验证 (实施时一次): 3 cutoff x 缓存命中 vs 强制重算,
  np.array_equal 逐位一致才算缓存正确; 差异即缓存 bug, 禁止上线。
- 驱动器集成: 用 p3 诊断候选伪造 aligned pending 队列, 驱动器跑通
  取队首->resume->verdict 全流程 (慢环单测用 max_points=350 上限内小样本
  mock run_symbol_backtest, 不做真 6h 评估)。
- 监督环: dry-run 模式 (--dry-run 只打印动作不执行); goal 评估器对
  构造的注册表快照求值; 429 解析对真实日志样本。
- 伪 run 集成: 造一个 fake praxist run_dir 工件 (run_summary/frontier),
  验证收割去重逻辑。

## 8. 预算与停止条件

| 预算 | 默认 | 耗尽行为 |
|---|---|---|
| max_cycles | 10 | 出中途报告退出 |
| cpu_hours (慢环) | 60 | 同上 |
| token_budget_m | 80 | 同上 |
| deadline | 2026-09-30 | 同上 |

任一触发即停, 监督环写中途报告 (goal 进度 + 各预算消耗 + 下轮建议)。
中途报告落 docs/superpowers/reports/ 目录, 并更新 STATE.md。

## 9. 非目标 (YAGNI)

- 不做 GPU/多机并行 (2 核是当前硬约束)
- 不修改 cascade/ (禁改红线)
- 不改 praxist 核心源码 (venv 内, 升级会丢)
- 不做 Web UI / 通知推送 (决策日志+报告文件足够)
- 不做每小时对齐 (慢环窗口错峰即可)
- 不自动改 goal.yaml (目标变更必须人工走纪律)

## 10. 实施顺序 (供 writing-plans 展开)

1. daily 缓存 + A/B 逐位验证 (TDD)
2. 慢环驱动器 + verdict 注册表 (TDD, mock 集成)
3. 监督环 + goal.yaml + DSL 求值器 (TDD, dry-run)
4. 快环模板接入 Known verdicts + task.yaml/loop-constraints 增补
5. runbook: 429 恢复 + supervisor 操作手册 (docs/)
6. 端到端演练: goal.yaml 用小目标 (1 个过门 variant) 演练 1 个完整 cycle

## 11. 验收标准 (整体系统)

- 无人值守 1 个完整 cycle: supervisor 起 run -> 收割入队 -> 慢环裁决 ->
  verdict 落表 -> 下次 run 提示词引用注册表 (peers 提示含 verdict 引用)
- 缓存 A/B 逐位一致
- kill 慢环/快环/监督环任意时刻, 重启后无数据损失续跑
- 429 注入演练: 模拟配额耗尽, supervisor 正确等待重置并 resume
- goal DSL 注入攻击被拒绝 (安全求值)
