# Task 10 Review — 测试是否锁住合同

- **被审**: `docs/superpowers/reports/2026-09-11-audit/task-10-tests.md`
- **计划**: `docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 10
- **简报**: `.superpowers/sdd/2026-09-11-full-system-audit/task-10-brief.md`
- **审核日**: 2026-09-11
- **范围**: 只审 Task 10 报告是否按规格取证、失败用例分类是否正确；不改生产代码、不改测试

## Verdicts

| 项 | 结论 |
|----|------|
| **Spec** | ✅ |
| **Task quality** | **Approved** |

## Must-fix gaps

无。

---

## Spec 核对（计划 Step 1–3 + 简报）

| 要求 | 报告是否做到 | 复核 |
|------|----------------|------|
| 合同-测试矩阵：行=硬合同，列=测试文件，空=缺口 | §1 七行表 | 计划点名方向 / IC 公式 / gate / 前视 / peer 不评估 / Vol OFF。报告把 IC 与 gate 合成第 2 行，把前视拆成实盘裸读 + 回测 `hour>=15`，并补上 Tasks 5–9 已裁定的「慢环唯一写 verdict」。六条点名合同都在，没有空行被写成「已锁」 |
| 跑简报指定子集，记 pass/fail；失败不修，不扩 monthly | §0 | 简报六文件在命令里。本审核独立跑这六文件：`83 passed in 11.43s`（0 failed）。报告实际命令多了 cutoff / freshness / copilot / vol / mutex 五份，收集 127 = 123 passed + 1 failed + 3 skipped，与独立 `--collect-only` 一致。不是全量 monthly |
| 三态判定：有锁 / 缺口 / 锁的是过期合同 | 文首 + §1 判定列 + §3 | 唯一红测判过期合同；现行七条里只有加权 1H **函数**有锁；其余缺口。绿着锁旧 `write_paths` 单独点名 |
| 读 `tests/AGENTS.md`（若有）+ 文件名 vs 合同 | §4 末 + §5 | `tests/AGENTS.md` 存在；优先跑清单确实没列 `test_signal_contract` / `test_backtest_cutoff` / `test_daily_freshness` / `test_copilot_advisory`。未倾销全部 `tests/*.py`，相关合同文件已覆盖 |
| 只写报告，不改生产 / 测试 / SCHEMES | git status | 工作树干净。`task-10-tests.md` 是本任务产出 |

失败用例分类是本任务的硬检查点，见下节独立复验：过期合同，不是代码 bug。

## Quality 核对

| 检查 | 结果 |
|------|------|
| 是否把红测写成活代码回归 / H1 前视没修 | **否。** 明确写「不要按这只红测去把 10:00 改回含当日」。与 Task 5 的 `hour>=15` 同向 |
| 是否把 123 passed 读成七条合同已锁 | **否。** 文首与 §7 / §8 写明缺口不是红测，是绿测给不了的信心 |
| 七条硬合同是否与 Tasks 5–9 同向 | **是。** 方向=加权 1H 且 Copilot 分叉；IC=`2*|dir_acc-0.5|` 且 `gate_pass` 不含 EV；实盘 `DailyModel.predict` 裸读；回测 10:00 不含当日日线；peer 禁评估只在提示词；Vol 默认 OFF；慢环唯一写 jsonl |
| 严重度是否把测试债抬成生产 Critical | **否。** 本任务产出是锁/缺口/过期三态，不另发明代码 bug |
| 越权改生产或扩跑 monthly | 否 |

## 独立复验（活仓 `/home/abug/timesfm`）

```
指定子集（简报六文件, --tb=no）
  83 passed in 11.43s

报告扩跑命令收集
  127 tests collected
  与「123 passed + 1 failed + 3 skipped」加法一致

红测
  tests/test_backtest_cutoff.py::TestBarExactCutoff::test_daily_includes_cutoff_calendar_day
  AssertionError: '2026-03-10' not found in {'2026-03-09'}
  夹具 cutoff = 2026-03-10 10:00:00，断言日线含 2026-03-10
  活代码 data/data_store.py:795-802
    cutoff_hour >= 15 → end_date=cutoff_day
    否则前一日历日 → 10:00 得到 {2026-03-09}
  判定：测试锁的是过期合同；代码是现行前视防护。不是 bug。

1H 同文件绿锁
  test_midday_excludes_later_same_day_bars 仍要求 10:00 含自身、不含 11:00/14:00（现行）

跳过
  test_vol_threshold_contract.py
    test_paths_are_absolute_under_fm_root
    test_resolve_independent_of_cwd
    test_black_missing_pkl_falls_back_to_r0_with_source
  条件：缺 trained vol pkl。与报告一致。

合同 1 方向
  tests/test_signal_contract.py:66-75 绿：daily_slope=0.0005 → regime 中性、position_sign=1
  cascade_predict.py:209-220,535-536 调 position_from_forecast（测试没锁调用点）
  monthly_backtest.py:50,329 同上
  copilot.py 全文件 0 次 position_from_forecast；:434 走 _compute_direction_v2
  test_copilot_advisory.py:18-20 只喂「中性」给 generate_risk_bounds
  test_system_hardening.py:170-192 锁的是 v2 副标签

合同 2 IC / gate
  evaluator.gate  task_FM/evaluations/fm_eval/evaluator.py:199-203 只判 n+ic
  test_evaluation_metrics_contract.py 八用例无 IC、不调 gate()
  子集外 test_praxist_fm_evaluator.py:23-28 默认 diracc=0.54 ev=0.9，只拦 n<350
  子集外 test_aligned_slow_loop.py:94-95 dir_acc=0.55 → ic==0.1（隐式公式）
  无 gate(n=400, ic=0.06, ev=-2) is True

合同 3 实盘裸读
  daily_model.py:104 store.get_main_continuous
  copilot.py:396-400 / cascade_predict.py:101-102 传入活 DataStore
  get_safe_daily 生产调用仅 cascade_predict.py:107（报告层）
  test_daily_freshness.py 全部 MagicMock 后再喂 helper

合同 4 回测 cutoff
  见红测。无「15:00 含当日 / 10:00 不含当日」正向锁

合同 5 peer 禁评估
  prompt_base.jinja2:5 / peer skill.md:4 有 do NOT run TimesFM
  指定子集不断言提示词、不断言 role 无 evaluation_tools
  role.yaml:18 仍含 evaluation_tools.peer
  test_praxist_task_contract.py:48-51 write_paths ⊆ {scripts/praxist_ws, reports/praxist}
  config/praxist_task.yaml:24-26 仍是这两条 → 今天绿
  :60 只断言 full_walkforward.gate 真值（yaml 含 ev>0）

合同 6 Vol OFF
  cascade_predict.py:67 use_vol_filter: bool = False
  vol_risk_filter.py:354 FM_VOL_FILTER 默认 "0"
  copilot.py apply_neutral* 0 命中
  指定子集无默认开关 / 无源码扫描

合同 7 慢环唯一写
  生产 append_verdict 仅 aligned_slow_loop.py:122（定义在 registry_lib.py:11）
  指定子集无 test_aligned_slow_loop.py
```

## 非阻塞偏差（不必返工）

- 简报命令是六文件 `-q --tb=no`。报告用了十一文件 `-q --tb=line`，并写「用户补的 cutoff/freshness/copilot/vol/mutex」。指定六文件独立复跑全绿，红测只存在于补进的 `test_backtest_cutoff.py`。SUMMARY 若引用 pass/fail，应写清「简报六文件 83 passed；扩跑后多 1 只过期合同红测」。
- 计划 Step 1 括号里是六条名字。报告七行是把前视拆开、IC 与 gate 合并、并加上慢环唯一写者。覆盖完整，不是漏合同。
- `data/data_store.py` 写成 `:790-802`。`get_main_continuous` 在 **L789**，`hour>=15` 在 **L796**。语义对。
- `test_praxist_task_contract.py`「gate 列表非空」写成 `:54-59`。函数从 L54 起，断言在 **L60**。
- `scripts/copilot.py:433-434`：L433 是 `d_slope`，调用在 **L434**。
- `tests/` 未给完整文件名清单。相关合同文件与子集外补洞表（§5）足够支撑三态判定。

以上不改变：红测是过期合同、七条现行合同只有函数层方向被锁、指定子集本身全绿。

**状态**: Spec ✅ / Approved / 无 must-fix。
