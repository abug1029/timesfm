# 确认派发活性调研报告（事项三）

> **日期**: 2026-10-07（立项与交付同日）
> **性质**: 只读调研（零代码改动）
> **背景**: dm-status 报告 §7 #2 通电前置检查——2026-10-03 两条预注册（34fedcb：jd daily_slope+vor n_req=1199、sr daily_slope+vwap_deviation n_req=986）落地后，registry 仅 4 行 no_data 存根、`__prereg_` 检查点 0 字节，确认派发链是否仍在运转需独立查证。B+C（事项一）让 dm_status 可确认，但不保证预注册确认能被派发与评估。
> **代码基线**: live /home/abug/timesfm master@ca4a3b9（pevs 合入后；本文行号均为该版本读数）
> **结论一句话**: 派发机制健康、全程在线——主循环每拍都在尝试派发，全部被数据就绪闸门依设计拦截并留痕（国庆缺口）；存根与 0 字节检查点是 10-03 闸门上线前的最后墓碑，不是失联。**但结构上 B+C 是确认轨道的前置**：数据恢复后若无 C，两预注册将陷入 no_common_cutoff 6h 一座 ×2 的无限循环；若无 B，评估即便配对成功也被 descriptive 拦截。

## 0. 结论速览

| 层 | 结论 |
|---|---|
| 机制层 | 主循环每拍走完整派发链：筛选五条件 → 数据闸门（fail-closed）→ 6h 节流 → 入队；未入队者 6h 一条决策留痕。无死代码、无断链 |
| 实证层 | 50 条 `confirmation_not_enqueued` 留痕（~6h 精确节奏，持续到今晨 09:56）；拒因全部 = 数据未就绪（1H 末端 2026-09-30 14:00 ≤ confirm_from_ts 2026-10-03）——**拦截是正确行为** |
| 结构层 | **B+C 是确认轨道的结构性前置**：`ensure_baselines` 无数据新鲜度检查 → 冻结基线对确认窗零覆盖 → 无 C = 派发能入队但评估恒 no_common_cutoff；无 B = 评估能跑但确认恒被 descriptive 拦截 |
| 通电判定 | 三正例（入队留痕 / status=ok∧dm_status 可确认的 peek / n_confirm_actual 收敛）+ 四反例诊断，服务事项一第 5 步 #2 |

## 1. 机制层：派发链全图

### 1.1 主链（每拍执行）

```
主循环 (:4210) 每拍
  └─ _maybe_enqueue_confirmations (:490)
      └─ due_confirmations (:354)      # 筛选五条件（见 1.2）
      ├─ 数据闸门 (:444)               # 1H 最新 bar 必须 > confirm_from_ts；fail-closed
      │                                # 按 symbol 30 分钟缓存；2026-10-03 深夜上线
      ├─ E2 节流 (:517-529)            # _CONFIRM_REDISPATCH_TTL_S = 6h (:1752)
      │                                # peek/墓碑不永久占坑（6h 后可重派）
      └─ 入队 / E1 满样终态 (:477)     # status=ok 且 n_actual ≥ n_req 才算已跑
```

未入队者每 ~6h 产生一条 `confirmation_not_enqueued` 决策留痕（`_CONFIRMATION_NOTICE_TTL_S = 6h`，:1748），经 `_log_decision` 写入 `.omc/supervisor_decisions.jsonl`——**不经 supervisor stdout**（supervisor.out 无 confirmation 行不是缺失，是设计）。

另有提案驱动支线 `dispatch_confirmation`（:222）：peer 提案确认时直接派发，与主链互补，同受闸门与节流约束。

> 命名说明：本文「数据闸门」（:444）= 确认派发的数据就绪检查，**非**技术债计划批次 4 的 D1（行号→章节锚点）条目。

### 1.2 筛选五条件（due_confirmations :354）

一条预注册要成为派发候选，须全部满足：

1. 非 terminal 状态（underpowered 封账等终态跳过）
2. 到期（confirm_from_ts 已过）
3. 未满样（E1：status=ok ∧ n_actual ≥ n_req 才算满）
4. 附加协变量恰 1 个、指纹与 family 可解析
5. 未被 blocked

## 2. 实证层：活性证据

### 2.1 决策留痕（.omc/supervisor_decisions.jsonl，读数 2026-10-07 ~15:00）

- **50 条 `confirmation_not_enqueued`**；jd 与 sr 两条预注册均在持续产生留痕
- 尾部样本：2026-10-06 21:47 / 10-07 03:51 / 10-07 09:56——**派发尝试持续到今晨**
- 节奏 ~6h 精确对齐 E2/NOTICE TTL；拒因 state 全部 `not_ready` = 数据闸门（1H 最新 bar 2026-09-30 14:00 ≤ confirm_from_ts 2026-10-03 00:00:00）

### 2.2 存根与检查点时间线

| 证据 | 时间 | 解读 |
|---|---|---|
| 4 行 no_data 存根（registry，run_mode=confirmation） | 10-03 22:31 / 22:37 | **数据闸门上线前的最后墓碑**（git_rev e155474 / b8a2118）。存根 = 「派发成功但评估窗无数据」——恰好证明派发链当时活着 |
| `__prereg_` 检查点 ×2 均 0 字节（aligned_checkpoints/） | 10-03 21:36 | 同上：确认评估被派发过、评估窗无数据、写空检查点防探索混样 |
| `confirmation_not_enqueued` 留痕 | 10-03 深夜起持续至今晨 | 闸门上线后从「派发-空转存根」改为「闸门拦截-留痕」——机制按设计演进，不再产生新存根 |
| 队列现状（data/cache/） | 10-07 15 时段 | pending 空；in-progress 1 条（探索行，jd_stddev peer 提案 14:47，非确认任务）——无确认任务排队 = 闸门全拦，符合预期 |

### 2.3 数据末端

- 1H 数据末端 **2026-09-30 14:00**（国庆假期缺口 ~7 天）；success_gate 每拍告警 7 天 stale 但 fail-open 放行（探索轨道不受影响）
- 数据闸门 fail-closed：末端 ≤ confirm_from_ts → 拒绝派发——**拦截是正确行为**（无数据时派发只会再产生 no_data 存根）
- 数据恢复预计 ~10-09（假期后首个交易日拉取）；恢复后闸门自动放行，无需人工干预

## 3. 结构层：B+C 是确认轨道的结构性前置

### 3.1 评估侧对基线的要求

确认行评估（scripts/aligned_slow_loop.py）：

- `eval_start_ts = confirm_from_ts`（:427-429）——**确认窗从注册日起算，不滑动**（v9 修订②）
- 基线 = `load_baseline_points(symbol, cov=None)`（:443，E7）——nocov 基线
- 独立检查点（:393-395）防探索混样；窗口无数据 → `_no_data_verdict` 墓碑（:93）

### 3.2 基线侧的缺口

`ensure_baselines`（scripts/praxist_supervisor.py:3697-3779）的再生条件只有三个：

1. metrics 无效
2. 行数 < 100
3. 指纹不符

**没有数据新鲜度检查**。现役基线锚定 ~09-17 前后（dm-status 报告 §4.3 案例：共同窗右端停 2026-09-17）——对确认窗（≥10-03）**零覆盖**。由此：

- **无 C（拉取日重锚）**：确认窗内变体 cutoff 与冻结基线 cutoff 交集为空 → `no_common_cutoff` → 6h 一座墓碑 × 2 预注册无限循环——**派发能入队、评估恒失败**
- **无 B（admissibility 豁免）**：即便 C 落地、配对成功，窗内缺失按现行规则 missingness_admissible=False → descriptive → `_passes_confirmation`（scripts/preregistry.py:463-476）拦截——**评估能跑、确认恒不通过**

→ **B+C 同时是第 5 步通电检查 #2 通过的必要条件**，与 dm-status 报告 §6 裁定的落地顺序一致（C 的基线版本化 = 第 1 步，C 重锚 = 第 2 步，B = 第 3 步）。

### 3.3 时间线推演

| 时点 | 无 B+C | 只有 C | B+C 齐 |
|---|---|---|---|
| 数据恢复（~10-09） | 闸门放行 → 入队 → 评估 no_common_cutoff 墓碑 6h ×2 循环 | 入队 → 配对成功 → descriptive → 确认不通过 | 入队 → 配对成功 → admissibility 判定 → 确认开始累计 |
| 预注册终局 | 墓碑循环至预算耗尽（2028-10-02） | 确认恒不通过，同上 | 按 n_req=986/1199 收敛（注释估算填充期 ~50 天） |

## 4. 通电判定标准（第 5 步 #2 用）

**前置**：B+C 上线（事项一第 3 步后）+ 数据恢复（1H 末端 > confirm_from_ts）。

| # | 检查 | 通过标准 | 观察点 |
|---|---|---|---|
| ① | 派发入队 | `not_ready` 留痕消失，出现 `confirmation_enqueued` | .omc/supervisor_decisions.jsonl |
| ② | 评估产出 | registry 出现 status=ok ∧ dm_status∈{ok, set_mismatch_ok} 的确认 peek（n>0） | task_FM/config/aligned_verdicts.jsonl |
| ③ | 样本收敛 | n_confirm_actual 向 986 / 1199 单调递增（填充期 ~50 天，允许慢） | registry 确认行 |

**反例诊断**（任一出现 = 对应环节未生效，定位后回改再验）：

- 仍 `no_common_cutoff` → **C 未生效**（基线未重锚到确认窗）
- 仍 `no_data` → 数据未恢复，或闸门误拦（查 30 分钟缓存是否脏）
- `confirmation_enqueue_error` → 派发异常（队列/指纹解析），回查 due_confirmations 五条件
- 配对成功但持续 descriptive → **B 未生效**或豁免双条件不满足（查 admissibility_rule 是否落行）

## 5. 与开放问题 #3 的边界

- **#2（本调研）**：确认轨道派发活性——**已查清：健康**，剩余风险全部在结构层（B+C 前置，§3）
- **#3**：十月探索行 `no_common_cutoff`×9——探索轨道的同类症状，B 的边缘豁免明确**不覆盖**（dm-status 报告 §7 #3），待第 5 步通电核查单独验
- 两者正交：#3 即便全部不解，也不影响本报告对确认派发链的运转判定

## 6. 证据与复现

- **派发链**（scripts/praxist_supervisor.py，master@ca4a3b9 行号）：:222（dispatch_confirmation 支线）/ :354（due_confirmations 五条件）/ :444（数据闸门 + 30min 缓存）/ :477（E1 满样）/ :490（_maybe_enqueue_confirmations）/ :517-529（E2 节流）/ :1748（NOTICE_TTL）/ :1752（REDISPATCH_TTL）/ :3697-3779（ensure_baselines 三条件，无新鲜度）/ :4210（主循环调用点）
- **确认评估**（scripts/aligned_slow_loop.py）：:93（no_data 墓碑）/ :393-395（独立检查点）/ :427-429（eval_start=confirm_from_ts）/ :443（E7 nocov 基线）
- **确认判据**（scripts/preregistry.py）：:463-476（_passes_confirmation）
- **留痕**：`grep confirmation_not_enqueued /home/abug/timesfm/.omc/supervisor_decisions.jsonl`（读数时点 50 条；state=not_ready；jd/sr 两预注册）
- **存根**：aligned_verdicts.jsonl `run_mode=confirmation` 4 行（decided_at 2026-10-03T22:31/22:37；git_rev e155474/b8a2118）
- **检查点**：`ls -la` aligned_checkpoints/`__prereg_*` 2 个 0 字节（10-03 21:36）
- **队列**：data/cache/aligned_pending*.jsonl（pending 空 / in-progress 1 探索行）
- **数据末端**：1H 数据文件末端 2026-09-30 14:00 + 闸门拒因 state=not_ready 互证
- **stdout 无行 ≠ 缺失**：决策走 `_log_decision` → decisions 日志，不经 supervisor stdout（data/cache/supervisor.out）

---

**交付边界**: 调研结论服务事项一 §6.4 第 5 步通电核查（#2 判定标准即本报告 §4）；#3（探索行 no_common_cutoff×9）不在本调研范围。2026-10-07 同日交付；行号为 pevs 合入后（master@ca4a3b9）读数。
