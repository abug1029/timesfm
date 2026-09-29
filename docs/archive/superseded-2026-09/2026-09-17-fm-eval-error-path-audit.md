# fm_eval/evaluator.py 错误路径审计 — 生产代码疑似 bug 清单（2026-09-17）

> **修复状态（2026-09-17）**: bug #1-#7 已修复，PIN 测试已同步（原 [PIN] 断言改为验证修复后行为）。
> 三级测试：新文件 86 passed / 相邻 38 passed / 全量套件见文末记录。#8 暂缓待产品决策。

来源：AQE 覆盖分析 → qe-test-architect 生成 86 个错误路径/边界测试（tests/test_fm_evaluator_error_paths.py）时的代码审读发现。**只报告未修改**；code-reviewer 复核确认成立。

## 待修复（按严重度）

| # | 严重度 | 位置 | 问题 | 建议 | 状态 |
|---|--------|------|------|------|------|
| 1 | 中 | gate() | n=NaN fail-open：`nan < 350` 为 False 不触发样本拒绝，NaN 样本量可绕过硬门 | 加 math.isnan 防护，统一 fail-closed | ✅已修复（2026-09-17） |
| 2 | 低 | gate() | dir_acc=inf 通过硬门（inf >= 0.52） | 拒绝非有限值 | ✅已修复（2026-09-17） |
| 3 | 低 | load_baseline_points() | 中途坏 JSON 行静默部分加载，DM 配对样本可能无声缩水 | fail-fast 或返回值标记截断 | ✅已修复（2026-09-17） |
| 4 | 低 | build_summary() | point_dir_ok_list 键存在但值为 None 时 len(None) 抛 TypeError（.get 默认值只防键缺失） | 改 `(s.get(...) or [])` | ✅已修复（2026-09-17） |
| 5 | 低 | map_summary() | n="abc" 直接 int() 抛 ValueError，浮点字段有 _f 防护但整数字段没有——防护不一致 | 补 int 防护 | ✅已修复（2026-09-17） |
| 6 | info | validate_candidate() | bool 型 max_points 被当 int 接受（bool 是 int 子类） | isinstance(x, bool) 排除 | ✅已修复（2026-09-17） |
| 7 | info | effective_sample_size() | step=0 抛 ZeroDivisionError，非法参数未防护 | 抛 ValueError 或文档化 | ✅已修复（2026-09-17） |
| 8 | info | effective_sample_size() | 负 rho 时 n_eff 无上限帽，可远超名义 n（统计上合法） | 视调用方语义决定是否加帽 | 暂缓（产品决策） |

## 附带疑点（reviewer 提出，不阻塞）

- statistical_tests.py np.clip(p, 0, 1) 疑似死代码（student_t.sf 值域本身 [0,1]）
- gate() 对 NaN 策略不一致：n=NaN fail-open vs dir_acc=NaN fail-closed——已随 #1/#2 修复统一 fail-closed（math.isfinite 防护 n/n_eff/dir_acc 三字段）

## PIN 测试闭环约定

tests/test_fm_evaluator_error_paths.py 原有 9 处 [PIN] 测试固化了上述部分 bug 的**当前行为**。2026-09-17 修复 bug #1-#7 时已同步更新对应 7 处 PIN 断言（改为验证修复后行为，[PIN] 标记移除改为普通回归测试）；剩余 3 处 [PIN]（负 rho 无上限帽、nominal_n=0 floor 到 1、零方差回退 1.0）保持原状。文件头约定声明已同步更新。

## 流程记录

- 基线：853 passed / 3 既有失败（ss 烟测 + 2 eval-grid），零回归
- 新测试：86 个全绿（首版 86 中 1 空转 + 2 名实不符，经 code-reviewer 审查后已修复，终版 86 全绿）
- 审查结论：83/86 首轮质量合格，数学锚点（ESS=66、DM 边界、阈值闭区间）人工复算无误

## 修复记录（2026-09-17）

- 生产修复：`task_FM/evaluations/fm_eval/evaluator.py`（#1/#2 gate 非有限值 fail-closed、
  #3 load_baseline_points fail-fast 带行号、#4 point_dir_ok_list None 回退、
  #5 map_summary 整数字段 _i 防护、#6 max_points bool 排除、#7 step<=0 抛 ValueError）
- 调用方分析（#3 选 fail-fast 依据）：`run.py:105` 是唯一生产调用点，主循环无 per-candidate
  try/except，也无截断处理能力——按任务约定选 fail-fast（脏基线文件整批失败，响亮而非无声）。
  其余调用点为测试（`tests/test_prediction_quality_e2e.py`、`tests/test_praxist_fm_evaluator.py`），
  均写合法文件，不受影响。
- 测试同步：`tests/test_fm_evaluator_error_paths.py` 7 处原 [PIN] 断言改为验证修复后行为
- 三级测试证据：新文件 86 passed；相邻 38 passed
  （test_praxist_fm_evaluator + test_evaluation_metrics + test_evaluation_metrics_contract）；
  全量套件：937 passed / 5 failed / 4 skipped / 2 xfailed（6分36秒）。
  5 个失败 = 3 个任务基线（ss 烟测 + 2 eval-grid）+ 2 个经 git stash 对照验证的既有失败
  （test_paper_loop::test_core_and_watch_are_two_star、test_prediction_scheme_phase9::test_stars[ss]，
  两测试文件零引用 evaluator 代码，stash 后原样复现，与本次修改无关——疑似 ss 降级 2★→1★
  后数据层断言滞后，commit 9c7fc2a）


## 下轮跟进（2026-09-17 code-reviewer 审查后登记，不阻塞本次放行）

1. gate() 类型兜底：isfinite/比较块包 try/except (TypeError, OverflowError) 统一 fail-closed——当前 build_summary L174 有把原始 s（未消毒）传 gate 的既有路径，非数字 n 会 TypeError 整批崩溃。**勿改成 gate(m)**：map_summary 缺省 dir_acc=0.5 会恰好压线过自适应门，制造 fail-open。
2. gate() baseline_dir_acc 加 isfinite：当前靠 min/max 求值顺序对 NaN 侥幸安全，脆弱。
3. load_baseline_points：UnicodeDecodeError 在迭代处抛出，绕过行号化包装（错误信息退化，仍 fail-fast）。
4. load_baseline_points：合法 JSON 但非 dict 的行不防结构损坏，下游 run.py pt.get 会 AttributeError——加载时加 isinstance(obj, dict) 校验。
5. _i() 加 bool 排除与 validate_candidate 口径对齐（良性，可选）。

## 终验记录（2026-09-17 修复批次）

- 修复：bug #1-#7 全部完成（executor，+31/-11），#8 跳过（产品决策）
- PIN 同步：7 处 [PIN] 改为回归测试，零删除，注释可溯源审计编号
- 独立终验：新测试 86 passed + 相邻 100 passed + 全量 937 passed / 5 failed（全部既有：3 基线 + 2 个 ss 降级 9c7fc2a 漂移，stash 对照归因），零新增失败
- 审查：code-reviewer APPROVE（7/7 忠实、无 PIN 丢失、surgical）
