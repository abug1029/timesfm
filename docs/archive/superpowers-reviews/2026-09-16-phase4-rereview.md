# Phase 4 复审（changelog 追加段，`70568f1` + `0550560`）

- **日期**: 2026-09-16
- **对象**: WSL `/home/abug/timesfm` `feat/prediction-quality-redesign-v23`
- **HEAD**: `0550560`（相对上次独立审核 `5c4d080`）
- **触发**: `CHANGELOG-Phase4.md` 7463 → 9015 字节追加，不是新文件
- **对照**: `2026-09-16-phase4-code-review.md`；changelog「独立代码审核修复」
- **测试**: evaluator + slow loop + baseline + supervisor + goal_dsl + evidence_ladder → **`-m not slow`：76 passed, 1 deselected, 2 xfailed**；整文件含 slow：**77 passed, 2 xfailed**。changelog 写 65，对不上。
- **结论**: **`v["pf"]` 崩溃和 `path_corr=None` 这两条是真修了。** changelog 写「wait_for_batch 使用 `make_timeout_tombstone`」不成立——函数已接到 `_maybe_finish_slow`，但超时仍是 `open("a")` 瘦 dict。文末 APPROVE 仍不是独立盖章。

---

## 1. 上次意见处置

| 上次（`5c4d080`） | 本轮声称 | 复算 |
|-------------------|----------|------|
| **Critical：`build_snapshot` `v["pf"]` KeyError** | 删除 `pass_variant_pf_ratios` | **已修。** 独立复现 v2 `gate_pass+fdr_pass` 不再炸；snapshot 无该键 |
| **Critical：缺 `baseline_metrics.json` 直接 return** | 视为 `{}` 继续生成 | **部分。** 缺文件变成 `{}`；若 `pytest` 在 `sys.modules` 仍 return。生产会走进 `generate`，但 `generate(..., "default")` 且 `daily_model=None`，异常被吃掉，基线还是没有 |
| **Important：`wait_for_batch` 未接线** | 接到 `_maybe_finish_slow`，用 `make_timeout_tombstone` | **接线是真的，墓碑写法是假的。** 见 §2 |
| **Important：evidence ladder 红** | 改 `dir_acc` / Known verdicts | **已修。** 本轮套件含该文件，全绿 |
| **Important：`families_hit` 回退 `cov_override`** | 只看 `cov_family` | **已修。** `cov_family=None` 的过门记录不进 `families_hit` |
| **Important：`map_summary` `float(None)`** | `_f` 辅助函数 | **已修 TypeError。** `path_corr=None` 保持 None；`mae/mape` 缺省仍是 `0.0` |
| `GOAL_SYMBOLS_SET` 21 vs 计划 8 | 未声称 | **未动。** 且 `goal.yaml` 改成 `n_one_star_symbols_hit >= 4` 后，2 星品种也会算进去 |
| 慢环不传 `baseline_dir_acc` | 未声称 | **未动** |
| `_no_data` metrics 不齐 | 未声称 | **未动** |
| changelog 自报 APPROVE | 再次 APPROVE | **仍无效**；文首旧段还写着「wait_for_batch 已集成 / 69 tests」 |

`0550560` 把 `praxist_goal.yaml` 的 `min(pass_variant_pf_ratios) > 1.05` 换成数量条件，避免目标永远不可达。这属于计划 Task 13 的范围，改得必要，但注释仍写 `ev>0`。

---

## 2. 复算摘录

```
HEAD 0550560
snapshot v2 gate_pass+fdr_pass: OK, no pass_variant_pf_ratios
map_summary path_corr=None: None (no TypeError)
wait_for_batch called from _maybe_finish_slow:1539-1543  YES
wait_for_batch body still open("a") stub dict: YES
timeout rec keys: batch_id, decided_at, schema, status, symbol, variant_id
  endpoint_mape/gate_pass/metrics: missing
generate still daily_model=None, ensure_baselines cov="default"
GOAL_SYMBOLS_SET size=21
pytest: 76 passed, 1 deselected, 2 xfailed
changelog claimed: 65 passed, 2 xfailed
```

`wait_for_batch` 接在 `_slow_drain_complete()` **之后**，超时默认 `get_batch_timeout`（7200 秒）。队列已空、进程已死时：人到齐则立刻返回；有人缺墓碑就会再空等最多 2 小时。挂死的 Worker 本来就不会让 drain 完成，超时熔断仍然帮不上忙。`batch_records` 里 `symbol=""`。只把 `ok/error/timeout` 当完成；已有 `no_data` 行仍会再追加 timeout，`load_snapshot` 按 `variant_id` 后写覆盖。

commit `70568f1` 说明写了 `make_timeout_tombstone + append_verdict_path`，diff 只加了调用，**没改函数体**。

---

## 3. 问题

### Critical

无新的公式层否决。上次两条会打崩 Supervisor 的 Critical，`pf` 那条已关掉。

冷启动生成仍会失败（见 Important），但异常被吃掉，不会把 Supervisor 进程打崩。

### Important

**1. changelog / commit 说明：超时墓碑走 `make_timeout_tombstone`——源码不是**

- 文件：`scripts/praxist_supervisor.py:1434-1478`（写入）、`:1535-1543`（调用）
- 独立跑 timeout：只有 6 个键，没有 `gate_pass` / `p_value` / `endpoint_mape=None` / `weighted_dir_acc=0.0` / `metrics`。`open(..., "a")`，不走路径锁和先写赢。
- 修法：`rl.append_verdict(path, rl.make_timeout_tombstone(symbol, vid, batch_id))`。drain 完成后再等 7200 秒没有意义，缺人应立刻写墓碑（timeout=0 或只扫一轮）。

**2. 生产冷启动仍生成不出基线**

- 文件：`ensure_baselines:1418+` 调 `gbp.generate(sym, "default", root)`；`generate_baseline_points.py:60-64` `daily_model=None`
- 缺 metrics 文件不再整段 return（pytest 下仍跳过，合理）。真跑会在 `hourly_model.predict` 上炸，打日志后继续 → `p_value` 仍是 None。
- 修法：generate 内加载模型；cov 用 `ccl`（或配置）；失败要让预检可见。

**3. `n_one_star_symbols_hit` 按 21 个品种算**

- 文件：`evaluator.py:115`；`GOAL_SYMBOLS_SET`；`praxist_goal.yaml` 新条件 `n_one_star_symbols_hit >= 4`
- 旧 YAML 显式交集 `{m,ss,sr,cj,jd,lh,eg,rb}`。现在 ao/bu 等 2 星也会把「1 星命中数」加进去。独立复现：ao/bu/cf/fg 四条 v2 过门 → `evaluate_goal` 为 True。`test_production_goal_yaml_tier1_expansion` 直接喂标量，测不到「2 星不凑数」。注释还写 1 星八品种和 `ev>0`。
- 修法：snapshot 标量与 task.yaml 的 8 个对齐，或 YAML 写回显式交集；加一条用真实 snapshot、4 个 2 星不得过门的测试。

**4. 文首旧段和文末 APPROVE 继续自相矛盾**

- 文首仍「完成，代码审核通过」、Task 12「wait_for_batch 已集成」、总计 69 tests。追加段写 65 tests。本机 76。
- 修法：文首改成「待独立复审」；不要再写独立审核通过。

### Minor

- `mae/mape` 在 `_f(..., 0.0)` 下，None 变成 0.0，像零误差。
- 慢环仍不传 `baseline_dir_acc`。
- `_no_data` 的 `metrics` 仍不齐。
- `gate` 仍不认只有 `DirAcc` 的旧 summarize。
- `materialize_known_verdicts` / goal.yaml 注释仍写 `ev>0`。
- `wait_for_batch` 单测仍只断言 `status=="timeout"`。

---

## 4. 结论

**Ready to merge Phase 4 into the redesign branch:** No（独立审核员同此；功能上原先两条会打崩的 Critical 已关掉，但超时墓碑声明为假，且 4 个 2 星即可达成生产目标）。`pf` KeyError 和 `path_corr=None` 已关掉，evidence ladder 已绿，goal.yaml 不再死引用已删字段。超时墓碑、基线冷启动、1 星集合口径还没按规格落地。

**不要把追加段「审核结论：APPROVE（独立代码审核通过）」当盖章。** 本文件才是复审结论。

建议下一刀只做三件事：超时走 `make_timeout_tombstone` 且 drain 后不要再睡 7200 秒；generate 带真实模型和 `ccl`；`n_one_star_symbols_hit` 锁回 8 个 1 星品种。
