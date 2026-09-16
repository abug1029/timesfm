# Phase 3 复审（对照 `2026-09-15-phase3-code-review.md`）

- **日期**: 2026-09-15
- **对象**: WSL `/home/abug/timesfm` `feat/prediction-quality-redesign-v23`
- **修丁**: `6507cee`（`f54145a..HEAD`）
- **对照**: 上次审核 + `CHANGELOG-Phase3.md` 附录「独立代码审核修复」
- **测试**: registry + quality + resume + aligned_slow_loop `-m not slow` → **33 passed, 1 deselected**
- **结论**: **上次挡 Task 9 的口径分裂已在生产路径上修好。** 路径追加改回真正 append，墓碑能过 `validate_verdict_v2`。还开着的是测试打不到 `run_symbol_backtest`、错误点 `cutoff` 仍是日期、changelog 又自报 APPROVE。Task 9 可以开；Task 10 必须用路径版 `append_verdict`，不要和句柄混写。

---

## 1. 上次意见处置

| 上次 | 本次 | 复算 |
|------|------|------|
| **Critical：加权 `dir_ok` vs 终点 `dir_acc`** | **生产路径已修** | `run_symbol_backtest` 用 `pred[-1]-base` / `real[-1]-base`，零变动 False。加权 `delta_pred` 仍只给 `pnl`。`summarize` 的 `dir_acc` 仍走 `calc_prediction_quality` |
| **墓碑缺 `cov_family` / `weighted_dir_acc` / `error_message`** | **已修** | 复算：`cov_family=unknown`，`weighted_dir_acc=0.5`，`error_message` 在、`error` 不在；`validate_verdict(tombstone)==[]`；`VERDICT_FIELDS_V2 - set(tombstone)` 为空 |
| **`VERDICT_FIELDS_V2` 漏字段** | **已修（仍标可空）** | 已加入 `cov_family`、`weighted_dir_acc`，但两者在 `NULLABLE` 里，缺了也能过校验 |
| **逐点 MAPE 无 `max(base,1.0)`** | **已修** | 源码 `_ep_mape` / `_ep_bias` 都用 `max(base, 1.0)` |
| **路径追加整文件重写、不校验** | **已修** | 真正 `open(..., "a")+fsync`；坏行第二次追加后仍在（`not json` 还在文件里）；残缺 v2 抛 `ValueError` |
| **错误点 `cutoff` 仍是日期** | **未修** | `except` 仍 `"cutoff": dt` |
| **质量测试不进 `run_symbol_backtest`** | **基本未修** | 新测试仍喂现成 `points`。`test_dir_ok_uses_endpoint_not_weighted` 只证明 `summarize` 用终点算 `dir_acc`，**打不到** 345 行的逐点公式 |
| **`n_eff` 测试锁不住 STEP=2** | **未修** | 仍是 `1 <= n_eff <= n` |
| **句柄与路径混锁** | **留给 Task 10** | 慢环仍是句柄追加 |
| **changelog +221 / 自报 APPROVE** | **过程问题仍在** | 附录再次写「独立审核通过」 |

---

## 2. 复算摘录

```
validate error tombstone []
bad JSON line survived second append: True
incomplete v2 rejected: True
error cutoff still `"cutoff": dt`: True
endpoint dir_ok / mape floor present in source: True
33 passed, 1 deselected
```

墓碑 `metrics` 现有：`batch_id, dir_acc, endpoint_*, n, n_eff, path_corr, status, symbol, weighted_dir_acc`。规格 §8.4 里 `metrics` 还带 `mae/mape/decay/p_value/gate_pass/fdr_pass/migrated_pass`，这次从 metrics 里拿掉了（根节点仍有）。`endpoint_mape=0.0`、`weighted_dir_acc=0.5` 和规格墓碑（`None` / `0.0`）也不一致；若只看 `metrics.endpoint_mape` 且不看 `status`，崩溃变体会像 MAPE=0 的赢家。Task 12 应读根字段，或把 `metrics` 按 §8.4 抄齐。

`append` 已保留坏行；`update_batch_verdicts` 仍走 `_iter_jsonl` + tmp 重写，**第一次 FDR 回写会把坏行从磁盘抹掉**。规格允许跳过坏行，但要知道 Supervisor 结算等于一次净化。

---

## 3. 还开着的（不挡 Task 9，挡测试可靠性和 Task 10 混写）

**Important（测试）**  
`test_dir_ok_uses_endpoint_not_weighted` 不调用 `run_symbol_backtest`。把 345 行改回加权 `delta_pred`，这组测试仍绿。建议抽纯函数测 `dir_ok` 公式，或对 `run_symbol_backtest` 里那几行做最小单测。

**Important（错误路径）**  
异常点仍写日期 `cutoff`。`summarize` 会跳过 error 行，resume / 对账同日多根 1H 仍会撞。改成变量 `cutoff` 即可。

**Minor**  
- `cov_family` / `weighted_dir_acc` 标成可空，漏写不会被 `validate_verdict_v2` 拦住。  
- 先写赢仍静默 `return`，没有 warning。  
- `dir12_ok` 零变动仍 True。  
- changelog 文首 APPROVE、测试数 25（本轮指定套件是 33）。

---

## 4. 结论

**Ready to merge Phase 3 into the redesign branch:** 主体可以留下。错误路径 cutoff 和建议的 `dir_ok` 单测最好在 Task 9 前补上，但不构成公式层否决。  
**Task 9 evaluator:** **可以开。** 成功路径上 Gate 的 `dir_acc` 和存盘 `dir_ok` 已都用终点价差。不要用 changelog 当验收。  
**Task 10 慢环:** **可以开，但必须改成路径版 `append_verdict`**，不要继续 `open(..., "a"); append_verdict(f, v)`，否则和 Supervisor 的锁各写各的。墓碑工厂现在能过 v2 校验，可以直接用。

不要把 changelog 里「独立代码审核通过」当成已经盖章。本文件才是复审结论：Critical 口径已修，测试覆盖和错误 cutoff 还欠一刀。
