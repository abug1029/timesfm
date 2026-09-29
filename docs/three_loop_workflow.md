# FM_a 三环工作流 -- 按代码实写（2026-09-29）

> 本文档是**代码的转述**，不是规范也不是计划。每个断言都锚定到 `文件:行号`。
> 方案 A 合同：peer 只写提案 JSON，**不加载 TimesFM、不跑任何评估**（已落实）。

## 0. 关键文件一览

| 文件 | 角色 |
|------|------|
| `scripts/praxist_supervisor.py` | 监督环主循环（~2800 行）|
| `scripts/aligned_slow_loop.py` | 慢环 / 对齐回测（~290 行） |
| `scripts/registry_lib.py` | 裁决注册表读写 / 队列 / 快照 |
| `cascade/typesafe_prescreen.py` | TypeSafe Jev 预筛 |
| `task_FM/config/aligned_verdicts.jsonl` | **canonical 证据源**（gitignored，仅慢环追加） |
| `scripts/praxist_goal.yaml` | 目标定义 + cadence 参数 |

---

## 1. 监督环主循环（`praxist_supervisor.py:2193 main`）

每个周期（cycle）按顺序执行：

```
while True:
    1a. _maybe_harvest          <- 收割已完成的 praxist run
    1b. _maybe_enqueue_retests  <- n-不足型近失误自动复测排队
    1c. _maybe_start_slow_loop  <- 启动/续跑慢环（phase=slow 或队列忙）
    1d. _maybe_finish_slow      <- 完成慢环批次（写 timeout 墓碑）
    1e. decide_fast_loop         <- 决定快环动作（启动新 run / 续跑 / skip）
    1f. materialize_known_verdicts  <- 重写 known_verdicts.inc.md（peer 证据）
    1g. materialize_covariate_menu  <- 重写 covariate_menu.inc.md
    1h. quota_gate               <- 429 限额门控
    1i. save_state               <- 持久化 cycles_done / phase / last_run_id
```

**周期结束标志**：`cycles_done += 1`（`praxist_supervisor.py:2592`）

---

## 2. 快环（praxist run / peer agents）

### 启动（`decide_fast_loop`, `praxist_supervisor.py:1922`）

```python
subprocess.Popen([
    "praxist", "run", "--prompt", prompt_path,
    "--topology", "fm_two_peer", "--model", model, ...
], start_new_session=True)   # <- 孤儿化，PPID = /init
```

**快环 NOT 做什么**（方案 A，已验证）：
- 不加载 TimesFM 模型
- 不跑任何回测或评估
- 不写 `aligned_verdicts.jsonl`

**快环 DO 做什么**：
- peer agents 读取 `known_verdicts.inc.md`（已知证据）+ `covariate_menu.inc.md`（协变量菜单）
- 写入提案 JSON 到 `task_FM/experiments/<run>/results/gen_N/peers/genN_peerM/proposals/*.json`
- 提案 schema = `fm.hypothesis_proposal.v1`，含 mechanism（>=40 字）

---

## 3. 收割（harvest，`harvest_proposals`, `praxist_supervisor.py:1452`）

周期末尾扫描所有 run 目录：

```python
# 1. 读提案 JSON
proposal = json.load(open(proposal_path))

# 2. 转队列行
rows.append({
    "variant_id": f"{symbol}_{cov_override}_aligned_p{n}",
    "symbol": symbol, "cov_override": cov_override,
    "max_points": int(aligned_max_points),   # <- 600（来自 goal.yaml）
    "stage": "aligned",
    "source": "peer_proposal",
    "quality_score": ..., "sector": ..., "_family": ..., "_tier": ...,
})

# 3. TypeSafe Jev 预筛（fire-and-forget，不阻塞收割）
_prescreen_async(proposal, proposal_path, symbol)
```

**`max_points = aligned_max_points`** -- 从 `goal.yaml` 的 `cadence.aligned_max_points` 读取，当前值 **600**。

### 预筛触发（`_prescreen_async`, `praxist_supervisor.py:1092`）

- `cascade.typesafe_prescreen.prescreen_and_save` -- 调用 TypeSafe Jev API
- 幂等守卫：已有 `.prescreen.json` 且 `status == "success"` 则跳过
- 结果写为 `proposal.prescreen.json`（plausibility / skip_suggested / novelty / note）
- 熔断：连续失败 -> 停止调用（`_check_circuit`）
- 对快环提案的影响：**只影响调度打分**（`_proposal_priority_score`），不阻断

**已落盘的预筛结果**：registry 中 22 条 verdict 带 `metadata.prescreen`，最近一条 2026-09-29。

样例：
```json
{"status": "success", "skip_suggested": false, "plausibility": 0.77,
 "novelty": "extension", "effect_size": 1,
 "note": "机制可信 (0.77) | 新颖度: 扩展 | 预期效果: 微弱"}
```

---

## 4. 慢环（aligned_slow_loop.py，~290 行）

**这是全系统唯一执行回测的地方。**

### 入队 -> 执行 -> 出队

```
aligned_pending.jsonl  <- harvest_proposals 写入
       |
queue_claim()          <- 慢环从 pending 移到 inprogress
       |
run_aligned_candidate()  <- 对每条记录执行
       |
  _run_inner():
    mb.run_symbol_backtest(...)     <- THE backtest（唯一调用点，aligned_slow_loop.py:137）
    -> 数据充足 -> build_summary(...) -> verdict 追加到 aligned_verdicts.jsonl
    -> 数据不足 -> _no_data_verdict(...) -> status="no_data"
       |
queue_ack()            <- 移到 aligned_pending.done.jsonl
```

### 回测入口（`aligned_slow_loop.py:137`）

```python
data = mb.run_symbol_backtest(
    row["symbol"].upper(), daily_model, hourly_model,
    cov_override=row["cov_override"], max_points=row["max_points"],
    daily_cache_dir=daily_cache_dir,
    completed=completed, checkpoint_fp=checkpoint_fp,
    resumed_points=resumed,
    ablation_mode=row.get("ablation_mode") or "full")
```

### 无数据处理（`_no_data_verdict`, `aligned_slow_loop.py:55`）

当 `run_symbol_backtest` 返回 None 或 summarize 返回 None：
- `status = "no_data"`
- `run_mode = None`
- 不进入 pass_variants（status != "ok"）

**实测：registry 172 条裁决中 0 条 status=no_data。** 慢环在正常产出。

### Checkpoint 机制

- 每个 variant_id 一个文件：`data/cache/aligned_checkpoints/{variant_id}.jsonl`
- 逐点追加（`checkpoint_fp.write(json.dumps(point) + "\n")`）
- 中断后可 resume（读 checkpoint 重建 completed set）

---

## 5. 样本复测（sample_retest，`plan_sample_retests`, `praxist_supervisor.py:1723`）

**不是第二个回测**--是对同一慢环回测的重复触发。

### 触发条件

`_maybe_enqueue_retests(goal, log)` 扫描 registry：
- variant 的 `n < 350`（样本不足）但其它条件接近过门
- 本地数据已增长 >= `retest_min_new_points`（默认 1）
- 不在 dead 集合中

### 排队参数

```python
{
    "variant_id": row["variant_id"],   # 保持不变
    "max_points": int(aligned_max_points),  # 600（与 harvest 相同）
    "source": "sample_retest",
}
```

### 与 harvest 的区别

| | harvest_proposals | sample_retest |
|---|---|---|
| 来源 | peer 提案 JSON | registry 中已有裁决 |
| variant_id | 新建 `{sym}_{cov}_aligned_p{n}` | **复用已有 variant_id** |
| max_points | 600 | 600 |
| 目的 | 新假设首次验证 | 补足已有假设的样本量 |

---

## 6. 裁决注册表（`aligned_verdicts.jsonl`）

**canonical 证据源**（`loop-constraints.md` 明令：仅此文件可写，禁止 peers/人工手写）。

### 写入者

| 写入者 | 条件 |
|--------|------|
| `aligned_slow_loop.py`（正常路径） | 回测数据充足 -> `build_summary()` |
| `aligned_slow_loop.py`（无数据） | 回测返回 None -> `_no_data_verdict()` |
| `wait_for_batch`（timeout=0） | 批次完成时写 timeout 墓碑 |

### 2026-09-29 现状（方案 A 过滤后）

| 协议指纹 | 条数 | 状态 |
|---------|:----:|------|
| `91ab913e...`（v3） | **2** | **当前有效** |
| `bd851c9c...`（v2） | 27 | 排除（10 条一次性脚本 + 16 条消融实验，均 2026-09-28） |
| 无指纹 | 143 | 排除（pre-v2 遗留） |

### pass_variants 过滤链

```python
def pass_variants(snapshot):
    for v in snapshot.values():
        if v.get("status") != "ok": continue       # 排除 no_data/timeout
        if schema == "v2":
            if run_mode not in RUN_MODES: continue  # A1 守卫
            if run_mode == "exploration": continue  # 探索期不晋升
            if gate_pass and fdr_pass and p_value is not None:
                if a1_missing_fields(v): continue   # 缺 A1 字段 -> 不完整
                out.append(v)
        else:  # v1 legacy
            if gate_pass and ev > 0: out.append(v)
```

**当前 pass_variants 返回 0 条**：
- v3 的 2 条中，1 条 `fdr_pass=False`，1 条 `run_mode="exploration"`
- 0 条 `run_mode="confirmation"`（PR-D1 未实施，pre-registration 不存在）

---

## 7. 物化输出（peer 看到的证据）

### known_verdicts.inc.md（`materialize_known_verdicts`, `praxist_supervisor.py:713`）

周期末尾重写，peer 用它避免重复提案。2026-09-29 新增：

```
[INFO] 物化证据按 protocol 过滤: active=2/172 fp=91ab913e448aead6...
       排除=91ab913e448aead6:2 bd851c9ca0730dc5:26 none:143
```

**不静默**--被排除的行数和按指纹分组的直方图每周期打印。

### covariate_menu.inc.md（`materialize_covariate_menu`, `praxist_supervisor.py:1604`）

渲染协变量池中的候选，带 track record 前缀「【旧口径线索·非证据】」。

---

## 8. 队列与状态文件

| 文件 | 用途 |
|------|------|
| `data/cache/aligned_pending.jsonl` | 待回测队列 |
| `data/cache/aligned_pending.inprogress.jsonl` | 当前在跑的记录 |
| `data/cache/aligned_pending.done.jsonl` | 已完成的记录 |
| `data/cache/aligned_checkpoints/*.jsonl` | 逐点 checkpoint |
| `data/cache/supervisor_state.json` | cycles_done / phase / last_run_id |
| `data/cache/supervisor.out` | 监督环日志（`setsid nohup >> ...`） |
| `data/cache/eval_slots.lock` | 1 字节空文件（历史残留，无害） |

---

## 9. 停止监督环

**`scripts/stop_supervisor.sh` 不存在。`logs/supervisor.log` 不存在。**

正确做法：
```bash
kill -TERM <supervisor_pid>           # 只置标志，主循环下个 tick 退出
# 等 data/cache/supervisor.out 出现:
#   supervisor_stopped{reason: signal_received, exit_code: 0}
setsid nohup python scripts/praxist_supervisor.py --goal scripts/praxist_goal.yaml \
  >> data/cache/supervisor.out 2>&1 < /dev/null &
```

---

## 10. 已知的结构性问题

1. **Phase 3 占位符**（`praxist_supervisor.py:551`）:
   ```python
   n_validated_multi_seed = 0  # TODO: implement
   decay_below_threshold = 0   # TODO: implement
   ```
   -> `all_symbols_pass_phase3` 恒 False。**goal 在数学上不可达。**

2. **`preregistry.jsonl` 不存在**（PR-D1 未实施）:
   -> 无 `prereg_id` -> 无 `run_mode="confirmation"` -> 无裁决可经统计晋升

3. **`enqueue_fast_loop_proposals.py` 无调用点**:
   -> 硬编码 `max_points: 6` 的孤儿脚本，未接入生产路径
   -> 26 条 n=6 裁决是该脚本（09-28 一次性运行）+ T2 消融实验的产物

4. **`_p6` 命名歧义**:
   -> 快环提案和消融实验共享 `_aligned_p6` 后缀，但 max_points 不同（600 vs 6）

5. **172 行 registry 中 170 行被方案 A 过滤排除**:
   -> 仅 2 条 v3 裁决可参与统计，且都不满足 pass 条件
   -> registry 需要**真正的新裁决流**（v3 基线 + confirmation run_mode）才能产出有效证据

---

## 附录：关键函数调用链

```
main() [2193]
  +-- _maybe_harvest()
  |     +-- harvest_proposals() [1452]
  |           +-- proposal_to_queue_row() -> max_points=600
  |           +-- _prescreen_async() [1092] -> TypeSafe Jev
  |
  +-- _maybe_enqueue_retests() [2767]
  |     +-- plan_sample_retests() [1723] -> max_points=600
  |
  +-- _maybe_start_slow_loop()
  |     +-- subprocess.Popen(aligned_slow_loop.py --batch-id ...)
  |
  +-- decide_fast_loop() [1922]
  |     +-- subprocess.Popen(praxist run ...) [start_new_session=True]
  |
  +-- materialize_known_verdicts() [2581]
  |     +-- load_snapshot(REGISTRY, only_protocol=v3_fp) -> 过滤后 2 条
  |
  +-- materialize_covariate_menu() [2585]

aligned_slow_loop.py:main() [231]
  +-- run_aligned_candidate() [100]
        +-- _run_inner() [116]
              +-- mb.run_symbol_backtest() [137]  <- 唯一回测
              +-- build_summary()                <- 数据充足
              +-- _no_data_verdict() [55]        <- 数据不足
```
