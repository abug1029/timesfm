# Phase 4 第三轮复审（changelog 第二轮追加，`84205f2`）

- **日期**: 2026-09-16
- **对象**: WSL `/home/abug/timesfm` `feat/prediction-quality-redesign-v23`
- **HEAD**: `84205f2`（相对上一轮 `0550560`）
- **触发**: `CHANGELOG-Phase4.md` 9015 → 9976 字节追加
- **对照**: `2026-09-16-phase4-rereview.md`；changelog「复审修复 (2026-09-16 第二轮)」
- **测试**: 指定套件 `-m not slow` → **76 passed, 1 deselected, 2 xfailed**（changelog 写 45 passed，那是 supervisor+goal_dsl 子集；文末又写 76）
- **结论**: **三件声称的修复，墓碑 API 和 8 个 1 星品种是真的。** 「drain 后不再等 7200 秒」不成立：调用仍是 `timeout=get_batch_timeout(goal)`。文末「独立审核 + 复审均通过」仍不是独立盖章。

---

## 1. 上次意见处置

| 上一轮 | 声称 | 复算 |
|--------|------|------|
| **wait_for_batch 瘦 dict / 不用 `make_timeout_tombstone`** | 改用 `make_timeout_tombstone` + 路径 `append_verdict` | **已修。** 独立写入一条 timeout：`endpoint_mape=None`，`weighted_dir_acc=0.0`，`gate_pass=False`，有 `metrics`，schema v2 |
| **drain 后空等 7200 秒** | 完成后不再等 | **未修。** `_maybe_finish_slow:1537-1538` 仍 `timeout = get_batch_timeout(goal)` 再传入 |
| **`no_data` 被 timeout 覆盖** | 未单列 | **覆盖被先写赢挡住**（仍 1 行 `no_data`）。但 `status in (ok, error, timeout)` 仍不认 `no_data`，有 `no_data` 时仍会把等待循环跑满超时 |
| **`generate(..., "default")` + `daily_model=None`** | cov=`ccl`；加载 DailyModel/HourlyModel | **主体已修。** `ensure_baselines` 两处都是 `"ccl"`。generate 会 `DailyModel()`；加载失败仍 fallback `None` 并继续 |
| **`GOAL_SYMBOLS_SET` 21 个，4 个 2 星即可过门** | 硬编码 8 个 | **已修。** 集合 `{'m','ss','sr','cj','jd','lh','eg','rb'}`。ao/bu/cf/fg 四条 v2 过门 → `evaluate_goal False`；m/ss/sr/cj 四条 → `True` |
| 慢环不传 `baseline_dir_acc` | 未声称 | **未动** |
| `_no_data` metrics 不齐 | 未声称 | **未动** |
| `mae/mape` None→0.0 | 未声称 | **未动** |
| changelog APPROVE | 再次「审核+复审均通过」 | **仍无效** |

---

## 2. 复算摘录

```
HEAD 84205f2
GOAL_SYMBOLS_SET = {cj, eg, jd, lh, m, rb, sr, ss}  # n=8
timeout tombstone keys include endpoint_mape=None weighted_dir_acc=0.0 gate_pass=False metrics
no_data then wait_for_batch: still 1 line status=no_data (first-write-wins)
2-star ao/bu/cf/fg evaluate_goal: False (n_one_star_symbols_hit=0)
1-star m/ss/sr/cj evaluate_goal: True
ensure_baselines cov: "ccl" x2, "default" x0
_maybe_finish_slow still: timeout = get_batch_timeout(goal); wait_for_batch(..., timeout=timeout)
wait_for_batch completion statuses: ok, error, timeout  # not no_data
pytest -m "not slow": 76 passed, 1 deselected, 2 xfailed
```

---

## 3. 问题

### Critical

无。上一轮挡住合并的两条（瘦 timeout 墓碑、21 品种当 1 星）已复现为修好。

### Important

**1. drain 完成后仍按 `batch_timeout_s`（默认 7200）去等**

- 文件：`scripts/praxist_supervisor.py:1537-1538`，`wait_for_batch:1433` 默认 7200
- changelog / commit 都写「不再等待 7200 秒 / 立刻写墓碑」。源码只改了**写什么**，没改**等多久**。人到齐会马上返回；缺人或只有 `no_data` 仍会 5 秒一轮直到超时。
- 挂死 Worker 仍然到不了这里（drain 要求进程已死）。
- 修法：drain 之后 `timeout=0`（或只扫一轮再写墓碑）；把 `no_data` 算进完成态。

**2. generate 加载失败仍 fallback `None`**

- 文件：`scripts/generate_baseline_points.py:61-68`
- 生产冷启动会真去构模型，这是对的。失败后仍把 `None` 交给 `run_symbol_backtest`，异常继续被 `ensure_baselines` 吃掉。pytest 缺文件分支仍 `return`，这条路径没有单测。
- 修法：模型加载失败直接失败，不要静默 None。

### Minor

- 生产调用 `wait_for_batch` 时 `symbol=""`（`batch_records` 只带 variant_id），timeout 墓碑的 symbol 可能是空串。
- 慢环仍不传 `baseline_dir_acc`；`gate` 仍不认只有 `DirAcc`。
- `_no_data` 的 metrics 仍比错误墓碑少字段。
- `map_summary` 对 `mae/mape` 的 None 仍填 0.0。
- `wait_for_batch` 测试仍只断言 `status=="timeout"`，锁不住完整 v2 字段。
- changelog 文首旧段、65/45/76 三种测试数并存。
- goal.yaml 注释仍写 `ev>0`。

---

## 4. 结论

**Ready to merge Phase 4 into the redesign branch:** With remaining notes。墓碑 API 和 8 个 1 星口径已经对上规格；不要按 changelog 把「7200 秒」和「复审均通过」写进完成态。

建议下一刀只改：drain 后 `timeout=0` + 承认 `no_data`；generate 失败不要 fallback None。其余可进 Task 13。

不要把「独立代码审核 + 复审均通过」当盖章。本文件才是第三轮复审结论。
