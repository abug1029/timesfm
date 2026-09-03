# Loop Constraints

> 约束规则在每个循环运行开始时自动加载。
> `loop-constraints` 技能读取此文件，所有约束 **强制执行**。

## Push & Merge
- 不要未经告知就 push
- 永远不要自动合并到 main 分支
- 创建变更时先报告，等人工确认

## Paths — 禁止自动编辑（高风险）
- `.env`, `.env.*` — 密钥文件（TqSdk 凭证）
- `config/prediction_scheme.py` — 20 品种固化方案，需人工确认
- `cascade/daily_model.py` / `cascade/hourly_model.py` — 模型核心逻辑，需人工确认
- `cascade/features.py` — 协变量构建逻辑，需人工确认
- `data/config.py` — 品种配置，需人工确认
- `.omc/` — OMC 内部状态
- aligned_verdicts.jsonl 唯一写入方: aligned_slow_loop.py (慢环 flock 持有者)。
  peers/supervisor/人工写 verdict = 破坏预注册纪律, 视同数据造假。
  status=no_data 不是死亡; 只有 status=ok 且 gate_pass=false 为 DEAD。
  verdict 注册表为 canonical 证据源, reports/ 均为衍生视图。

## Paths — 允许操作
- `scripts/` — 运行脚本（在 worktree 中测试）
- `reports/` — 生成报告
- `db/` — 数据采集（只增不删）
- `data/tqsdk_fetcher.py` — 数据采集逻辑（谨慎修改）
- `data/data_store.py` — 数据读写层（谨慎修改）
- `data/main_chain.py` — DEPRECATED (2026-07-02)，仅作兼容保留
- `data/contract_manager.py` — 合约管理（已适配 _CONT 格式）

## Code
- 修改前先说明要做什么
- 不要修改无关代码 — 一次运行只做一件事
- 单个问题最多尝试 3 次，之后上报人工
- 修改后运行相关脚本验证

## Communication
- 做之前先告诉我要做什么
- 不要自行关闭 issue 或 PR

## Budget
- **Token 预算已禁用**（Unlimited Coding Plan）
- 如果 loop-pause-all 激活，立即退出
- 如果 STATE.md 无待处理事项，快速退出（不要空跑）

## 预注册评估契约 (2026-09-01, P0a)
- **任何诊断性回测启动前**，先在任务文件中写死最终裁决口径：全量 walk-forward、扣滑点 EV>0、IC≥0.05、多重比较校正（bonferroni/holm）
- 评估代码与口径同 commit 落盘；诊断 PF 好看不作数（B1 教训：诊断 PF 好看但全量 0/11 GREEN）
- 契约权威文件：`config/praxist_task.yaml`（校验器 `scripts/praxist_validate_task.py`，违规 exit 2）
- PRAXIST peers 唯一可写区：`scripts/praxist_ws/` 与 `reports/praxist/`；SCHEMES/cascade/data.config 固化仍须人工执行

---
<!-- 在下方添加自定义规则。Loop 会原样读取。 -->
