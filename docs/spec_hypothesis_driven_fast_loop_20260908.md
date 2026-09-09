# 设计规格：快环 Peer 转型为机制化假设作者（Hypothesis-Driven Fast Loop）

> 日期: 2026-09-08
> 状态: **已实施（2026-09-08 上线，当日首个过门策略 ss_vor 即出自本方案）**
> 关联文档: praxist_peer_evaluation_fix.md, audit_system_efficiency_20260908.md, runbook_praxist_three_loop.md

> **实施后增补（2026-09-09）**：
> - §4.3 选座在 QD 两遍填充之前增加 **tier 分层**（goal `cadence.priority_symbols`）：目标 1 星品种且当前 n≥350 → 目标品种欠样本（cj/lh）→ 其余品种；修复"扩目标后慢环座位全给 2 星"问题。
> - 新增 **n-不足近失误自动复测**：`plan_sample_retests` / `_maybe_enqueue_retests` 每 tick 扫描 gate 仅差 n 的裁决（n<350, ic≥0.05, ev>0, pf/incumbent>1.05），本地库有效点长到 ≥350 时旁路 dead 去重补队，checkpoint resume 只算新点；goal key `retest_min_new_points`。
> - 菜单新增 **symbol sample ceiling** 段（每品种当前可对齐有效点 + BELOW GATE/gate-reachable）。
> - 与设计的偏差：§4.3"合格未入队提案结转 pending-proposals 索引"未实现（下一 cycle 直接重扫 proposals/，dead/in-flight 去重已防重复入队）。
> - 事件可靠性修复：signal/atexit handler 改为 `main()` 启动时才武装（import 本模块当库用不再误发 unexpected_exit）；测试经 `_patch_paths` 隔离 EVENTS_PATH。
> - 当前运行口径（host 迁移）：WSL2 Ubuntu-22.04 `/home/abug/timesfm`，`.praxist-venv` CPython 3.11，7.7 GiB RAM。

---

## 1. 背景与动机

### 1.1 问题
快环 peer 当前用 n=3~6 的诊断评估（diagnostic）筛选候选，但小样本统计不可信。
n=3 时方向准确率标准误 ≈ sqrt(0.25/3) ≈ 0.29，PF/EV 噪声极大。实测诊断结论与慢环真相严重脱节：

| 诊断结论 (n=3) | 慢环真相 (n=396) | 偏差 |
|---|---|---|
| ss+ccl PF=10.1 | PF=1.02, gate=False | 高估 ~10x |
| eg+rsi_state PF=99.99 | PF=0.97, gate=False | 虚高 ~100x |
| jd+oi PF=1.37 | PF=0.97, gate=False | 假阳性 |
| m+oi PF=0.0 | 未测（可能被错误淘汰） | 假阴性 |

诊断档既不能可靠排除差组合，也不能可靠保留好组合，每次却耗费 60-150s 的 TimesFM 模型加载。

### 1.2 真正的验证引擎是慢环
慢环 walk-forward（n=350-600）硬门：n≥350 且 ic≥0.05（ic=2×|dir_acc−0.5|）。
当前 11 个 aligned 裁决全部 gate=False，搜索面仅打开 2%（30 协变量 × 21 品种 = 630 组合，仅测 11 个）。

### 1.3 目标
1. Peer **不再跑评估**，转为产出机制优先的结构化假设；慢环成为唯一验证器。
2. 策略池可维护：支持**新增协变量**（peer 提议 → 宿主实现入池）与**归档无效协变量**（全局退役）。
3. 假设非随机组合：强制机制论证 + 正交多样性（QD）+ 裁决历史反馈。

### 1.4 非目标
- 不改动冻结框架 `.praxist-venv/.../praxist/**`。
- 不改动慢环 `aligned_slow_loop.py` 与队列库 `registry_lib.py`。
- 不改动慢环硬门逻辑。
- 不让 peer 修改 features.py / evaluator.py（安全约束）。

---

## 2. 架构

```
快环（peers, LLM, 0 次模型加载）
  peer 读 known_verdicts + covariate_menu（含机制说明）
    │ 写结构化假设文件 + share_finding(hypothesis)
    ▼
  results/gen_N/<peer>/proposals/<sym>_<cov>.json     ← 新契约
    │
监督环（praxist_supervisor.py：新增 harvest_proposals）
  glob proposals → 校验(symbol合法 / cov在池active / 机制非空)
    → 去重(dead / passing / in-flight / 已提议)
    → 排序(正交族多样性 > 协变量履历 > 机制完备度 > 新颖性)
    → rl.queue_enqueue（复用现有 dead/existing 去重）
    │  新协变量想法(new_cov_*) → config/covariate_backlog.jsonl（不入队）
    ▼
慢环（aligned_slow_loop.py，0 token，唯一验证器）— 不改
  消费队列 → n=350-600 walk-forward → checkpoint 续跑 → aligned_verdicts.jsonl
    ▼
监督环 materialize → known_verdicts.inc.md + covariate_menu.inc.md → 下一代 peer 反馈
```

**可行性依据**：队列消费者只需 `variant_id/symbol/cov_override/max_points`，不校验诊断评估存在；
`aligned_pending.done.jsonl` 已有 5 个 `src_run=manual_inject` 直注成功裁决先例。

---

## 3. 数据契约

### 3.1 协变量池注册表（新）`task_FM/config/covariate_pool.json`
```json
{
  "schema": "fm.covariate_pool.v1",
  "covariates": {
    "vor":            {"family": "volatility", "status": "active",
                        "mechanism": "波动率范围压缩→扩张预判", "track_record": "m_vor PF1.30/MaxDD最低"},
    "basis_momentum": {"family": "structure", "status": "archived",
                        "archived_reason": "Phase6 退化弱信号", "archived_at": "2026-09-08"}
  }
}
```
- status: active（可提议）| experimental（宿主测试中）| archived（全局退役）
- family: volatility/trend/structure/oscillator/positioning/calendar/volume/statistical（供 QD）
- mechanism: 协变量为何有效，直接喂 peer 做机制化推理
- 种子：现有 30 协变量按 features.py 分派归类；证据不足者一律 active，数据驱动未来归档

### 3.2 假设提案 `results/gen_N/<peer>/proposals/<symbol>_<cov>.json`
```json
{
  "schema": "fm.hypothesis_proposal.v1",
  "proposal_id": "m_vor",
  "symbol": "m",
  "cov_override": "vor",
  "covariate_family": "volatility",
  "mechanism": "必填：该协变量在该品种的经济/微观结构机制（≥40字，禁模板）",
  "symbol_fit": "必填：为何是这个品种（如 crack_spread 仅对裂解链品种有意义）",
  "predicted_direction": "low_vol_compression→long_breakout",
  "kill_condition": "预注册：aligned ev<0 或 ic<0.02 → 放弃",
  "promote_condition": "预注册：gate_pass 且 PF>1.05 且 ev>0",
  "peer_id": "gen2_peer0", "gen_id": 2, "proposed_at": "..."
}
```

### 3.3 新协变量想法 `results/gen_N/<peer>/proposals/new_cov_<name>.json`
`cov_override: null` + `new_covariate:{name, formula, mechanism, family}`；监督环转入 backlog，不入队。

### 3.4 入队行（沿用 QUEUE_FIELDS）
`{variant_id, symbol, cov_override, max_points:cadence, stage:"aligned", checkpoint_path:"",
   enqueued_at, src_run, source:"peer_proposal"}`

---

## 4. 变更清单

### 4.1 新增文件
| 文件 | 职责 |
|---|---|
| `task_FM/config/covariate_pool.json` | 协变量池单一事实源（active/archived/experimental + family + mechanism） |
| `task_FM/config/covariate_backlog.jsonl` | peer 提议的新协变量想法（宿主评审用） |
| `task_FM/covariate_menu.inc.md` | 监督环生成的菜单（active 机制目录 + archived 禁用块） |
| `tests/test_covariate_pool.py` | 池 schema、归档拒绝、active 均有 features 分派 |
| `tests/test_harvest_proposals.py` | 空机制拒绝、去重、family 多样性、new_cov 转 backlog |
| `tests/test_combo_parity.py` | rsi6/12/24 + gated/regime/basis combo 路径可跑 |

### 4.2 编辑 `task_FM/evaluations/fm_eval/evaluator.py`
- 新增 `_load_pool()`：读 covariate_pool.json → ACTIVE / ARCHIVED 集合
- AST 并集（L67）之后做**差集**（关键：现 `|= discovered` 只会加）：
  `VALID_COVARIATES -= ARCHIVED_COVARIATES`
- validate_candidate 对归档协变量返回 `covariate 已归档: <reason>`
- 池文件缺失/解析失败 fail-open（不归档）+ stderr 告警（仿 _DYNAMIC_DISCOVERY_ERROR）

### 4.3 编辑 `scripts/praxist_supervisor.py`
- `load_covariate_pool()`：读池供排序/校验
- `harvest_proposals(root, snapshot, dead, existing, pool, top_k, aligned_max_points)`（镜像 harvest_survivors L398-459）：
  - glob `run_*/results/**/proposals/*.json`（仅本 run）
  - 拒绝：schema 不符 / symbol∉ALLOWED / cov∉active / mechanism 空或<40字 / family 缺 → reject 计数 + log（fail visibly）
  - 去重：dead / pass_variants / in_flight / seen
  - 排序：① 正交族多样性（沿用 two-pass seat-fill）② 协变量履历（近门优先）③ 机制完备度 ④ 新颖性（未测组合优先）
  - 合格未入队提案结转（pending-proposals 索引，下 cycle 再排）
  - new_cov_* → 追加 covariate_backlog.jsonl
- `_harvest_rows()`（L927）改调 harvest_proposals（保留 harvest_survivors 函数体，仅断调用）
- 新增 `materialize_covariate_menu()`：从池生成 covariate_menu.inc.md（在 L995/L1054 附近调用）

### 4.4 编辑 Peer 提示词（3 文件，框架不动）
- `prompt_base.jinja2`：
  - 删 L5-17 FIRST ACTION 跑评估、L19-28 评估输入 spec、L30-38 证据阶梯、L40-71 评估协议、
    L73-79 结果树、L95-110 内存卫生/评估启动（peer 不再加载 TimesFM，N=1 并发约束消失）
  - 改为：首动作 = 写 ≥2 机制化假设到 proposals/ + share_finding(hypothesis, extra={...})
  - `{% include 'covariate_menu.inc.md' %}` 提供机制目录；机制优先禁随机组合
  - symbol-fit 推理、预注册 kill/promote、QD 正交、保留 known_verdicts 段
  - 修 L22-24 陈旧 12 协变量裸列表 → include 菜单
  - 每 peer 每代 ≥2-3 条 hypothesis finding（保 synthesis_trigger.min_findings=4）
- `roles/peer_generalist/skill.md`：L5-38 评估协议 → 假设作者协议；删 L40-45 内存卫生
- `prompt_generation.jinja2`：L39-52 角色（exploit/falsifier/bridge）改为提出/精炼/否决假设；
  L54-62 清单改为假设公开项

### 4.5 编辑 `task_FM/task.yaml`
- 修 L13 research_direction 陈旧 1 星品种（ao,bu,cf...）→ 当前品种集；删 praxist_ws 写入指引
- staged_protocols：diagnostic 降级为仅宿主冒烟；aligned 可 mature/promote
- synthesis_trigger.min_findings=4 保持（hypothesis findings 满足）

### 4.6 编辑 `cascade/features.py`（审查发现的真 bug）
- build_combo_covariate_matrix（L1384+）补 rsi6/rsi12/rsi24 分支 + supported 列表
  （单路径 L1051 已修，combo 路径缺失 → combo 含 rsi6 会 raise ValueError）
- 同补 gated_slope / regime_gated / basis_momentum（单路径有、combo 无）
- 单路径 L1362 未知协变量**静默降级 CCL → 改为 raise ValueError**（归档/拼写错误显式暴露；combo 已是 raise）

---

## 5. 运维工作流

### 5.1 新增协变量（peer 不能改 features.py）
1. peer 写 new_cov_*.json → 监督环汇入 covariate_backlog.jsonl
2. 宿主评审 backlog → features.py 加 calc_* + 单路径分支 + combo 分支 + supported 列表 + 单元测试
3. 宿主用 run.py diagnostic 档冒烟（验证数据可用、无 NaN）
4. 池注册 active → 菜单自动出现 → 下一代 peer 可提议 symbol×new_cov

### 5.2 归档协变量
1. 足够跨品种证据失败 → 池置 archived + reason
2. evaluator 拒绝新提议；菜单移除
3. 检查 config/prediction_scheme.py SCHEMES 是否仍引用（否则单路径静默降级 CCL）→ 迁移
4. features.py 分支保留（历史数据可读）；per-symbol 死亡仍由 dead_variants 自动拦截

---

## 6. 实施前置：停止当前 praxist

```bash
kill -TERM 486     # supervisor 优雅停（handler 置位 + atexit 写 stop_report）
kill -TERM 7230    # praxist run（终止 peer）
# eval 子进程随父终止，必要时 kill -9
ps aux | grep -E 'praxist|fm_eval'   # 确认无残留（grep 自身除外）
free -h            # 确认 TimesFM 内存释放
```
慢环已退出（队列空），无需处理；11 裁决 + checkpoint 持久化；在途 n=3 诊断为废弃工作，零损失。
改造完成后重启 supervisor，新 run 自动用新模板 + 新 harvest。

---

## 7. 验证

```bash
cd /home/abug/timesfm && source .praxist-venv/bin/activate
python -m pytest tests/test_covariate_pool.py tests/test_harvest_proposals.py tests/test_combo_parity.py -v
python -m py_compile scripts/praxist_supervisor.py cascade/features.py task_FM/evaluations/fm_eval/evaluator.py
# 干跑：造 2 提案（1 好 1 空机制），harvest_proposals dry-run
#   断言：好提案入队、空机制拒绝计数、new_cov 进 backlog
```
端到端（下一 praxist 周期）：peer 产 proposals/*.json（无 evaluation_summary.json）；
监督环 log 出现 `harvested proposals: enqueued N`；aligned_pending 新增 `source:peer_proposal` 行；
慢环产出 verdict；covariate_menu.inc.md 生成；归档协变量提议被拒并明示 reason。

## 8. 回滚
所有改动在 git。harvest_survivors 函数体保留，回退时把 _harvest_rows 调用改回即可。

## 9. 风险与缓解
| 风险 | 缓解 |
|---|---|
| 取消诊断后慢环队列洪泛 | survivors_per_cycle=3 限流 + 机制/多样性排序 + 合格提案结转不丢失 |
| peer 机制论证流于模板 | 监督环强制 mechanism≥40字 + 非空校验，reject 计数反馈 |
| 新协变量未实现却入队 | new_cov 强制走 backlog，不入队；active 校验要求 features 有分派（测试守护） |
| features.py 改动影响在途 | 实施前先停 praxist（第 6 节） |
