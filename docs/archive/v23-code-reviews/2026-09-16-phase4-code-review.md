# Phase 4 代码审核（Task 9–12）

- **日期**: 2026-09-16
- **对象**: WSL `/home/abug/timesfm` `feat/prediction-quality-redesign-v23`
- **HEAD**: `5c4d080`
- **范围**: `14000cb..5c4d080`（并回看 `b07865d` 的墓碑/`endpoint_dir_ok`，changelog 没写）
- **对照**: `CHANGELOG-Phase4.md`；计划 Task 9–12；规格 §4 / §8.3–§8.6 / §8.10
- **测试**: changelog 点名的 5 个文件 → **70 passed**；计划还要求的 `test_praxist_evidence_ladder.py` → **2 failed**（`ev_after_slippage`、prompt 仍提 `aligned_verdicts.jsonl`）
- **结论**: **changelog 里的 APPROVE 不算数。** 硬门和 DM 在 evaluator 里是真的，慢环也改成了路径版 `append_verdict`。但有两条已经复现的 Critical：冷启动没有 `baseline_metrics.json` 时预检直接跳过；第一个 v2 过门变体会让 `build_snapshot` 因 `v["pf"]` 把 Supervisor 打崩。`wait_for_batch` 没接到主循环。计划要求改的 evidence ladder 测试还是红的。

---

## 0. 日志对不上的地方

| 日志说法 | 实际 |
|----------|------|
| 状态「完成，代码审核通过」 | 执行者自报。独立审核见本文件 |
| `evaluator.py` +183/-51 | `14000cb` 该文件 **+112/-68** |
| `run.py` +52/-14 | **+28/-8** |
| 慢环 +117/-55 | 那是 **整 commit（含测试）**；`aligned_slow_loop.py` 本身 +72/-36 |
| Supervisor +179/-21 | 三文件合计；`praxist_supervisor.py` 在 `182d1c0` 是 +142/-9 |
| 慢环测试 8/8 | **9 collected / 9 passed**（含 `@pytest.mark.slow`） |
| Phase 4 总计 69 | 点名套件 **70**；再加上计划要求的 evidence ladder 则有 2 红 |
| `wait_for_batch` 集成到 `_maybe_finish_slow` | **未调用**。该文件里只有定义和一条单测 |
| 审核人「独立代码审核」 | 没有独立报告；本轮才是 |

`b07865d`（抽 `endpoint_dir_ok`、墓碑 `metrics` 按规格、FDR 回写保留坏行）在 Phase 4 之前，changelog 没提。墓碑根字段现在是 `endpoint_mape=None`、`weighted_dir_acc=0.0`，能过 `validate_verdict_v2`。

---

## 1. 做得对的地方

**Task 9**

- `gate`：`n` / `n_eff` / `dir_acc` 任一为 None 则 False；有 baseline 时 `effective_min = max(0.50, min(min_dir_acc, baseline_dir_acc))`，无 baseline 用 0.52。函数内无文件 IO。
- `map_summary` 只出质量秤 10 键，不再要 PF/EV/MaxDD。
- `build_summary`：`schema=fm.aligned_verdict.v2`；`pair_dir_ok_series` + `diebold_mariano_p`（horizon/step 从 config 读，生产 **HORIZON=24 STEP=2**）；两端或配对后 `<100` → `p_value=None`；`s.pop("point_dir_ok_list")`；`fdr_pass=None`、`migrated_pass=None`；`stage=="diagnostic"` 强制 `gate_pass=False`。
- `load_baseline_points` 只读 `task_FM/config/baseline_points_{symbol}.jsonl`。
- `test_praxist_fm_evaluator.py` 13 条与计划示例对齐，均绿。

**Task 10**

- `import os` 之后立刻 `OMP_NUM_THREADS` / `MKL_NUM_THREADS` setdefault，早于 `monthly_backtest` / numpy / torch。
- `torch.set_num_threads(4)` 包在 `ImportError` 里。
- 外层 `try/except`：`make_error_tombstone` + `append_verdict(registry_path, tombstone)`（路径 API），返回墓碑，`main` 仍 ack。
- 成功路径：`build_summary(..., batch_id=bid, baseline_points=load_baseline_points(symbol))`，不再 `setdefault pf/ev/ic`。
- `_no_data_verdict`：`status=no_data`，`n=0`，`gate_pass=False`，`p_value=1.0`，根字段 `endpoint_mape=None` / `weighted_dir_acc=0.0`，带 `metrics`。
- `--batch-id` CLI 存在。

**Task 11**

- 脚本存在；JSONL 只写 `cutoff/dir_ok/delta_pred/delta_real`；cutoff 用 `%Y-%m-%d %H:%M:%S` 校验；同品种 `.lock`；metrics 文件锁 + 空文件兜底；tmp rename；summary 缺键抛错。
- evaluator / 慢环 **没有** import 这个脚本。生产调用只在 `ensure_baselines`。

**Task 12（接到主循环的部分）**

- `GOAL_SYMBOLS_SET` 来自 `evaluator.ALLOWED_SYMBOLS`，空集打 WARN。
- `ensure_baselines` 接到 `_main_locked` 启动前。
- `_maybe_finish_slow` 在 drain 完成后对 `current_batch_id` 调 `bh_fdr_promote` + `update_batch_verdicts`，然后 `cleanup_batch_workers`（`pkill -f --batch-id.*{batch_id}`），再清 state。
- `harvest_survivors` 过滤 `dir_acc >= 0.50`，排序 `-dir_acc`（docstring 还在写 EV，行为已改）。
- `build_snapshot` 有 `n_one_star_symbols_hit` / `n_unique_pass_variants` / `n_families_hit`。

---

## 2. 问题

### Critical

Gate 和 DM 在 evaluator 成功路径上仍是同一套终点 `dir_ok`，公式层没有否决。下面两条会在生产主循环炸掉或让统计检验整段空转。

**1. 第一个 v2 过门变体会把 Supervisor 打崩**

- 文件：`scripts/praxist_supervisor.py:428-429`
- `build_snapshot` 对 `rl.pass_variants` 的结果做 `v["pf"] / INCUMBENT_PF[...]`。v2 成功 verdict 没有 `pf`。
- 独立复现：`schema=v2, gate_pass=True, fdr_pass=True` 的一条记录 → `KeyError: 'pf'`。
- `test_build_snapshot_scalars_v2` 的 fixture 塞了 `pf/ev`，测不到。FDR 一旦真晋级，`evaluate_goal` 读 snapshot 会炸。
- 修法：v2 不要读 `pf`；`.get("pf")` 或删掉 `pass_variant_pf_ratios`。YAML 改数量条件可以留到 Task 13，但 snapshot 现在就必须能吃 v2。

**2. 基线预检在生产冷启动会直接跳过**

- 文件：`scripts/praxist_supervisor.py:1395-1399`
- 打不开 `task_FM/config/baseline_metrics.json` 就 `return`。仓库里这个文件 **不存在**，目录只有 `.gitkeep` 和旧 jsonl。
- 预检虽挂在 `_main_locked:1579`，冷启动等于没跑。没有逐点 baseline → `p_value=None` → FDR 把 None 当 1.0，显著性通道关掉。
- 修法：文件缺失当成 `{}` 再按品种生成；不要把「测试目录没有 metrics」和「生产冷启动」混成一次跳过。

### Important

**3. `wait_for_batch` 没有接到主循环**

- 文件：`scripts/praxist_supervisor.py:1433` 定义；`_maybe_finish_slow:1526+` 未调用
- changelog / 计划：超时写墓碑、批次人数守恒。
- 现状：`_slow_drain_complete()` = 队列空 **且** 慢环进程已死。挂死的 Worker 会让 Supervisor 一直停在 slow；被 `pkill` 掉、没写出墓碑的候选，FDR 只看已经落盘的行，缺的人不会补 timeout 墓碑。
- 即便调用，当前实现也是 `open(..., "a")` 手写瘦 dict（只有 `status/schema/variant_id/symbol/batch_id/decided_at`），不用 `make_timeout_tombstone`，也不走路径锁 / `validate_verdict`。
- 修法：在 drain 或慢环启动后调用 `wait_for_batch`；超时用 `make_timeout_tombstone` + `append_verdict(path, ...)`。

**4. 计划 Task 9 要求改的 evidence ladder 仍红**

- 文件：`tests/test_praxist_evidence_ladder.py:116, 190`
- 计划 Step 4：`test_praxist_evidence_ladder.py` 若仍断言 `ev_after_slippage`，本任务内改成 `dir_acc`。
- 实测：`KeyError: 'ev_after_slippage'`；另一条还在 prompt 里找 `aligned_verdicts.jsonl`。changelog 套件故意没带这个文件。
- 修法：断言改到 `dir_acc` / `endpoint_mape`；prompt 文案放到 Task 13 也可以，但不要把这条测试继续留红。

**5. `ensure_baselines` 真要生成时，模型和协变量都不对**

- 文件：`scripts/praxist_supervisor.py:1378-1424`；`scripts/generate_baseline_points.py:60-64`
- 缺条目时 `gbp.generate(sym, "default", root)`，协变量是 `"default"` 不是规格/CLI 约定的 `ccl`。`"default"` 在回测里是填充策略名。
- `generate` 调用 `run_symbol_backtest(..., daily_model=None, hourly_model=None)`。测试 mock 了它；真跑会在 `hourly_model.predict` 上炸，异常被吃掉打日志。
- `_main_locked` 里 pre-flight 失败只 print，Supervisor 照样启动 → 慢环 `load_baseline_points` 得到 `[]` → `p_value` 一直 None，硬门仍可能过。
- 修法：缺文件也生成；传入真实模型或在 generate 内 `_get_models()`；cov 用基线约定（如 `ccl`）；失败要能让预检可见，不要静默降级成「无 DM」。

**6. `GOAL_SYMBOLS_SET` 是 21 个品种，不是计划写的 8 个信用品种**

- 文件：`evaluator.py:115` `ALLOWED_SYMBOLS`；`praxist_supervisor.py:552`
- 计划：`{m,ss,sr,cj,jd,lh,eg,rb}`，「不要另造 1-star 集合」。
- 现状：另加了 ao/bu/cf/fg/fu/i/jm/ma/p/sh/sp/ta/ur。`n_one_star_symbols_hit` 会按 21 个算，成功条件比计划松。
- 修法：GOAL 集合与 task.yaml 的 8 个对齐，或改计划并改 YAML，不要两套。

**7. `families_hit` 在 `cov_family` 缺失时回退到 `cov_override`**

- 文件：`scripts/praxist_supervisor.py:415-420`
- 计划只计受控词表里的 `cov_family`，且排除 `unknown`。回退会把 `rsi_state` 这类原始协变量名算进 `n_families_hit`。
- 修法：只看 `cov_family`，不要 `or cov_override`。

**8. `map_summary` 不能吃可空的 `path_corr`**

- 文件：`task_FM/evaluations/fm_eval/evaluator.py:241`
- `summarize()` 在没有有效路径相关时返回 `path_corr=None`。`float(None)` → `TypeError`。独立复现。成功回测会被外层 catch 写成 error 墓碑。
- 修法：`None` 原样保留；`mae/mape/decay` 同样可空，一起处理。

**9. 慢环没传 `baseline_dir_acc`，`gate` 也不读 `DirAcc` 别名**

- 文件：`aligned_slow_loop.py:149-152`；`evaluator.py:170, 249-262`
- `run.py` 会从基线点算 `baseline_dir_acc`；慢环只传 `baseline_points`，自适应地板在 aligned 上不会下调。
- `gate(s)` 读 `s["dir_acc"]`。只有 `DirAcc` 的旧 summarize 会被当成 null → False。独立复现：`gate({"n":400,"n_eff":400,"DirAcc":0.56}) is False`。
- 修法：慢环按 `run.py` 同样算 `baseline_dir_acc`；`gate` 走 `map_summary` 之后的键。

**10. `_no_data` 墓碑的 metrics 仍对不齐规格 §8.4**

- 文件：`scripts/aligned_slow_loop.py:64-103`
- 根字段 `endpoint_mape=None`、`weighted_dir_acc=0.0` 是对的。`metrics` 缺 `endpoint_mape/weighted_dir_acc/mae/mape/decay/fdr_pass/migrated_pass`。
- 修法：与 `make_error_tombstone` 的 metrics 对齐。

**11. changelog 再次自报 APPROVE，行数和测试数写错**

- 与 Phase 1–3 同一模式。不要当验收。

### Minor

- `harvest_survivors` / `materialize_known_verdicts` 文案仍写 `ev>0`。Peer 会读到过时指令（正式文案在 Task 13）。
- `load_baseline_points` 不把 symbol 转小写，和 generate 的 `baseline_points_{sym_lower}.jsonl` 可能对不上。
- `map_summary` 缺键时 `endpoint_mape` 默认 `0.0`，像完美预测。
- 基线 JSONL 的 tmp 名没有 pid/`time_ns()`，metrics 是 `write_text` 不是 `.tmp → fsync → replace`。
- `ensure_baselines` / FDR / `current_batch_id` 没有接到主循环的测试（timeout 单测打的是未接线函数）。
- `build_snapshot` 仍带 `pass_variant_pf_ratios`（经济秤残留）。
- `append_verdict` 仍保留句柄 dispatch；慢环已走路径。Task 10 约束已满足。

---

## 3. 测试复算

```
# changelog 点名套件（未含 evidence ladder）
.venv/bin/python -m pytest tests/test_praxist_fm_evaluator.py \
  tests/test_aligned_slow_loop.py tests/test_generate_baseline_points.py \
  tests/test_supervisor.py tests/test_goal_dsl.py -q
→ 70 passed

# 计划 Task 9 Step 4 还要求
tests/test_praxist_evidence_ladder.py
→ 2 failed (ev_after_slippage, aligned_verdicts.jsonl in prompt),
   74 passed / 1 deselected / 2 xfailed when included in the larger run
```

`wait_for_batch` 单测只证明「调用该函数会写 `status=timeout`」，不证明 Supervisor 会调用它。

---

## 4. 结论

**Ready to merge Phase 4 into the redesign branch:** No。硬门/DM/路径 append 可以留下，但 Supervisor 在第一份 v2 过门记录上会 `KeyError: 'pf'`，冷启动基线预检是空转。这两条要先修。

**Task 9:** 主体可用。`map_summary` 的 `None` 和 evidence ladder 红测试要补。

**Task 10:** 路径版 append 已落地，可以留下。`no_data` 的 metrics 抄错误墓碑。

**Task 11:** 测试绿。生产必须能在缺 metrics 文件时真正生成，cov 用 `ccl`，不要 `daily_model=None`。

**Task 12:** FDR 和 `batch_id` 已接到 drain 完成；**先修 `pf` KeyError，再把 `wait_for_batch` 接到主循环，超时走 `make_timeout_tombstone`。**

**Task 13 (YAML/Prompt):** 等上述 Critical 修完再开。`materialize_known_verdicts` 还在教 Peer 看 `ev>0`，应和 YAML 一起改。

不要把 changelog 里「独立代码审核通过」当成已经盖章。本文件才是审核结论。
