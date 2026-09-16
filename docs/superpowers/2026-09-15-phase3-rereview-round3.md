# Phase 3 第三轮复审（对照 `1f864fb`）

- **日期**: 2026-09-15
- **对象**: WSL `/home/abug/timesfm` `feat/prediction-quality-redesign-v23`
- **HEAD**: `1f864fb`（相对上次复审 `6507cee`）
- **对照**: `2026-09-15-phase3-rereview.md` + `CHANGELOG-Phase3.md`「复审修复」
- **测试**: registry + quality + resume + aligned_slow_loop `-m not slow` → **34 passed, 1 deselected**
- **结论**: **错误点 `cutoff` 这次是真修了。** changelog 里「dir_ok 公式测试直接打到逐点公式」不成立——新测试把公式抄进了测试文件，改生产 345 行测不红。生产口径仍可开 Task 9。不要把文末 APPROVE 当独立盖章。

---

## 1. 上次意见处置

| 上次（`6507cee` 复审） | 本轮 `1f864fb` | 复算 |
|------------------------|----------------|------|
| **Important：错误点 `cutoff` 仍是日期** | **已修** | `cutoff` 在 `:271`、`try` 在 `:285`、`except` 在 `:418`。`:419` / `:423` 都写变量 `cutoff`（`%Y-%m-%d %H:%M:%S`）。没有 NameError。仓库里 `"cutoff": dt` 已无匹配 |
| **Important：质量测试打不到 `run_symbol_backtest`** | **声称已修，实际未修** | 新 `test_dir_ok_formula_endpoint_not_weighted` 只 `import numpy`，把 `:346-352` 抄进测试。`test_monthly_backtest_quality.py` 里 `run_symbol_backtest` 出现次数 = **0** |
| **Minor：`n_eff` 只断言 `1 <= n_eff <= n`** | **部分收紧** | 现断言 `n_eff <= n // 2`。n=10 时 STEP=2→1（过）、STEP=4→2（仍过）、STEP=12→6（不过）。能拦住 STEP=HORIZON，锁不住 STEP=2 |
| 墓碑 `metrics` 对不齐 §8.4；`endpoint_mape=0.0` / `weighted_dir_acc=0.5` | **未动** | 见 §3 |
| `update_batch_verdicts` 第一次 FDR 回写抹掉坏行 | **未动** | 独立复现：坏行在 `update_batch_verdicts` 后消失 |
| 慢环句柄追加 | **留给 Task 10** | `aligned_slow_loop.py:129-130` 仍是 `open(..., "a"); append_verdict(f, v)` |
| changelog 自报 APPROVE | **仍在，且把空转测试写成已完成** | 文首「代码审核通过」、文末「独立代码审核 + 复审均通过」 |

`6507cee` 生产路径仍在：终点 `dir_ok`、MAPE `max(base,1.0)`、路径真 append、墓碑能过 `validate_verdict_v2`。

---

## 2. 复算摘录

```
HEAD 1f864fb on feat/prediction-quality-redesign-v23
error cutoff in except: "cutoff": cutoff   (assigned at :271 before try :285)
remaining "cutoff": dt in monthly_backtest.py: none
run_symbol_backtest mentions in test_monthly_backtest_quality.py: 0
n_eff(n=10, H=24): STEP2=1  STEP4=2  STEP8=4  STEP12=6  STEP24=10
bad JSON survived second path-append: True
update_batch_verdicts drops bad JSON: True
validate error tombstone: []
error metrics.endpoint_mape=0.0  weighted_dir_acc=0.5
timeout tombstone has error_message: False
34 passed, 1 deselected
```

新测试核心（`tests/test_monthly_backtest_quality.py:205-234`）是这段复印件，不是生产调用：

```python
_delta_pred_endpoint = float(pred_end - base)
_delta_real_endpoint = float(real_end - base)
# ... np.sign 比较 ...
assert dir_ok is True
```

把 `monthly_backtest.py:346-352` 改回加权 `delta_pred`，这组测试仍绿。旧的 `test_dir_ok_uses_endpoint_not_weighted` 则在 fixture 里写死 `"dir_ok": True`，只测 `summarize`。

---

## 3. 问题

### Critical

无。Gate 的 `dir_acc` 和逐点 `dir_ok` 在生产路径上仍是终点价差；错误 `cutoff` 已是完整时间戳。

### Important

**1. 新测试是公式抄写，打不到生产代码**

- 文件：`tests/test_monthly_backtest_quality.py:205-234`
- changelog 写「直接验证逐点 dir_ok 用终点价差」。AST：该函数不 import `monthly_backtest` 的判定函数，也不调用 `run_symbol_backtest`。
- 为什么要紧：Task 9 会把存盘 `dir_ok` 拿去配 DM。有人把 `:345` 改回加权，现有测试拦不住。
- 修法：抽纯函数（例如 `endpoint_dir_ok(pred_end, real_end, base)`），`run_symbol_backtest` 调用它，测试 import 这个函数。不要在测试里再抄一遍公式。

**2. 墓碑 `metrics` 仍对不齐规格；哨兵值会像赢家**

- 文件：`scripts/registry_lib.py` `make_error_tombstone` / `make_timeout_tombstone`
- 本轮未改。根字段能过 v2 校验。
- 现在 vs 规格墓碑：`endpoint_mape` 是 `0.0` 不是 `None`；`weighted_dir_acc` 是 `0.5` 不是 `0.0`。`metrics` 缺 `gate_pass / p_value / fdr_pass / mae / mape / decay / migrated_pass`。超时墓碑没有 `error_message`（该字段也不在 `VERDICT_FIELDS_V2` 里，所以校验仍绿）。
- 修法：按规格抄齐 `metrics`；`endpoint_mape=None`，`weighted_dir_acc=0.0`。Task 12 读根字段，并显式过滤 `status != "ok"`。

**3. `update_batch_verdicts` 第一次 FDR 回写会抹掉坏行**

- 文件：`scripts/registry_lib.py` `update_batch_verdicts`
- 读取走 `_iter_jsonl`（跳过坏行），写出 tmp 整文件替换。路径 append 会保留坏行；Supervisor 结算等于一次净化。
- 修法：重写时保留无法解析的原始行，或至少在 Task 12 落地前写进测试。

**4. changelog 把未完成的测试修复写成已完成，并再次自报 APPROVE**

- 文件：`D:\FlyBuddy\docs\superpowers\CHANGELOG-Phase3.md`（WSL 仓库里没有这份 changelog）
- 文首状态「完成，代码审核通过」；第二轮把公式抄写当成「直接验证」；文末「独立代码审核 + 复审均通过」。测试数在 23 / 25 / 34 之间跳。
- 修法：改成「错误 cutoff 已修；dir_ok 生产路径仍靠读源码，测试未锁住」。不要再写独立审核通过。

### Minor

- `n_eff <= n // 2` 锁不住 STEP=2（STEP=4 仍绿）。可断言 `n_eff == fallback_n_eff(n, HORIZON, STEP)`。
- 错误 `cutoff` 没有回归测试：改回 `dt`，34 个测试仍绿。
- `dir12_ok` 零变动仍记 True（`:376`）。不进 Gate。
- `cov_family` / `weighted_dir_acc` 仍在 `VERDICT_FIELDS_V2_NULLABLE`，漏写也能过校验。
- 先写赢静默 `return`，没有 warning。
- 慢环仍是句柄追加（Task 10 必须改）。
- 错误日志 `:430` 仍打印日历日 `dt`，只影响控制台。

---

## 4. 结论

**Ready to merge Phase 3 into the redesign branch:** 主体可以留下（With remaining notes）。错误 cutoff 已修；生产终点 `dir_ok`、真 append、MAPE 地板仍在。未完成的是测试空转、墓碑 `metrics` 合同、FDR 净化坏行。

**Task 9 evaluator:** **可以开。** 成功路径上 Gate 的 `dir_acc` 和存盘 `dir_ok` 都用终点价差；错误点时间戳已是 `%Y-%m-%d %H:%M:%S`。不要假设质量测试能拦住有人把 `:345` 改回加权。

**Task 10 慢环:** **可以开，但必须改成路径版 `append_verdict(path, v)`**，不要继续 `open(..., "a"); append_verdict(f, v)`。墓碑工厂能过 v2 校验，可先用；写入前把 `metrics` 按规格补齐，`endpoint_mape=None`，`weighted_dir_acc=0.0`。

不要把 changelog 里「独立代码审核 + 复审均通过」当成已经盖章。本文件才是第三轮复审结论。
