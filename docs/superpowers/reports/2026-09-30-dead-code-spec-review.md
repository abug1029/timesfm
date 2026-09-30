# 死代码清理 spec 专家审核报告

- 日期：2026-09-30
- 审核对象：`docs/2026-09-30-dead-code-purge-spec.md`（未跟踪稿）；上游依据 `D:\FlyBuddy\fma-audit\2026-09-30-fma-overengineering-audit.md`（勿动区，只读）
- 方法：定罪式复核（audit119/120）——每条「死」断言按四道筛验证：函数级 import / importlib 字符串 / subprocess-.sh 调用边 / tests 导入
- 总裁定：**打回修订**（P0×6、P1×6；修订后可执行）
- 后续：修订要求由 0.3 吸收进 spec 修订稿；宿主裁定 (d)(e) 已于 2026-09-30 落定，见实施计划「裁定记录」；**本报告自身的勘误见 §八**

## 一、核实为真的部分

spec 对上游审计的 E-1～E-5 勘误逐项属实：

1. `cascade/features.py` 三处 `_calc_atr` 函数级 import 确实存在——上游「82% 死」不成立；spec 下修为 ~8,048 行/16.5%，本审核再下修至 **~7.2–7.4K 行（~15%）**（裁定 (e) A2 整簇退役后总量上修至 ~10.7–11K，见第五节）。
2. `docs/module_freeze.md:14` 生产入口表确认相关模块的生产地位。
3. 37 脚本名单行数全部准确。
4. 名单之外零引用脚本 = 0（37 名单按代码引用口径完备）。
5. **fu 基线仍 v2** `bd851c9ca0730dc5`（588 行）——此项纠正了 Stage 3 评估报告 W1.4 的 9/9 记录。

## 二、P0（照原稿执行必出事故）

### P0-1 baseline_paths.py 判死错误
活引用：`task_FM/evaluations/fm_eval/evaluator.py:258`（函数级 import，每次基线加载必经）、`scripts/generate_baseline_points.py:29`、`tests/test_nocov_baseline.py:8/15/20`。

### P0-2 covariate_diagnostics.py 判死错误
活引用：`cascade/hourly_model.py:315`（主预测路径，`# PR-B2` 标注，每次 predict 执行）、`tests/test_covariate_diagnostics.py:5`。

### P0-3 experiment_fingerprint.py 判死错误且与 Stage 3 冲突
活引用：`scripts/restart_readiness_check.py:39`（importlib 字符串）+ `:96`（check_phase7 调 `compute_experiment_fingerprint`/`build_variant_id` 并断言 `ss_momentum_`+12hex 格式）、`tests/test_experiment_fingerprint.py:12`。
该模块同时是 W6.4 变体身份的唯一家、阶段 2 接线目标——归档它与 Stage 3 spec 直接冲突。

### P0-4 clear_supervisor_pause.py 归档会断重启链
`scripts/restart_three_loop_clean.sh:57`（第 [4/6] 步）在 `set -euo pipefail` 下调用它；归档 = 重启中止于第 4 步、supervisor 留停止态。
`user_paused` 标志实测无读者（仅 clearer 写）——标志该死，但调用边不能断：须连 `.sh` 第 4 步一起摘除。

### P0-5 lgbm_features.py 判死与 spec 自身矛盾
4 个保留脚本 import 它：`a2_p1_runtime.py:246`（顶层）、`a2_p2_worker.py:138/211`、`a2_p1_worker.py:135/216`、`a2_p1_lgbm_baseline.py:234`（函数级），另有 `tests/test_a2_p1_runtime.py` 6 处。
spec 用 a2 workers 作 features.py 的活证人，却判 workers 的另一依赖死——同一批证人救一个杀另一个。（裁定 (e) 整簇退役后矛盾自然消解。）

### P0-6 测试基线断言为假
「全量 pytest = 2 failed」被 spec 当作既有可接受基线；实际 2 failed 是待修 bug（同日 0.1 修复，119e28c）。检测测试的基线必须以 **0 failed** 为准。

## 三、P1（口径与设计缺陷）

1. **可达性四盲区**：函数级 import / importlib 字符串 / subprocess-.sh 调用边 / tests 导入——「名字不在别处出现」≠「不可达」。
2. **判死口径被自家名单违反**（4/37）：enqueue_fast_loop_proposals（three_loop_workflow.md:290）、pull_history_1h（runbook.md:33 行数表）、install_praxist_llm_env_hook（praxist_llm_env.md:69/82，文档化人工命令）、clear_supervisor_pause（three_loop_restart_protocol.md）。口径应改为「**未被在用文档记载为可运行命令**」。
3. **oi_gated_momentum.py** 被 2 个测试 import（test_features_oi_gated_dispatch.py:21/26、test_extract_xreg_oi_gated.py:85/105）——须连测试一起归档才自洽（裁定 (b) 采推荐：归档）。
4. **monitor_rb_regen.sh:29-32** 引用 regen_rb.py——regen_rb 归档会让监控脚本永久 exit 1；三件套（regenerate_all_baselines / regen_rb / monitor_rb_regen.sh）顺延至重生波后（2.9）归档。
5. **检测测试需重设计**：AST 导入分析 + allowlist + archive 目录排除 + pytest.ini。实证：2026-09-30 0.1 验收时裸 `pytest` 递归收集 `third_party/timesfm-3.0-official` 7 个测试文件、收集阶段 7 errors 中断（72.77s 白跑）。
6. **D1/D2/D3 名单缺陷**：D1 名单 8 文件实为 **802 行** ≠ spec ~2,600；D2/D3 成员全文未落纸，无法执行。

## 四、结构计数（实测）

- `scripts/*.py` = **123**（spec 的 40+22+37=99 对不上账，缺约 24 个测试支撑脚本）
- `cascade/*.py` = 30，合计 **12,302 行**（保留 25 = 11,602 行 + 拟删 5 = 700 行）
- **无 pytest.ini / pyproject.toml / setup.cfg / tox.ini 任何一件**
- 裸 pytest 收集范围 = tests/ + third_party/（+ 未来 archive/）——1.6 必须一并解决

## 五、真实总量

- 按原稿范围（37 脚本 + 5 cascade 模块）实际可归档 **≈7.2–7.4K 行（~15%）**。
- 裁定 (e)（A2 整簇退役）后上修：+10 个 a2 脚本（~3,032 行）+ `cascade/lgbm_features.py`（371 行）+ 配套测试 → **≈10.7–11K 行**。精确数以 0.3 修订稿全名单落纸为准。

## 六、错误模式记录（第四次同型）

K2 → N1 → P1 → 本例：spec §1.1 批评上游审计「没有程序调用者 = 没人用」，自己犯同型错「import 闭包不可达 = 死」。
规则沉淀：每条「死」断言必须过四道筛（函数级 import / importlib 字符串 / subprocess-.sh 边 / tests 导入）并留证据；关键判死结论必须**无截断**复查（audit119 的 `head -6` 差点漏掉 lgbm_features 的 4 个活 import）。

## 七、审核自勘误

初稿把变体身份函数记作 `derive_variant_id`——实际导出名 `build_variant_id`；「生产接线 0」结论不变。

## 八、勘误（2026-09-30，执行前边界终验）

本报告发出后、spec v2 修订落地前，执行方对归档边界做执行前终验，发现本报告自身犯下与第六节同型的错误。以下以本节为准：

1. **P1-3 撤回——oi_gated_momentum.py 是活代码。** 第三节第 3 条以「仅被 2 个测试 import」为由建议连测试归档，与 v1 spec 同漏检生产引用：`cascade/features.py:1118` 函数级**相对导入**（`from .oi_gated_momentum import compute_oi_gated_momentum`，位于 `_build_oi_gated_momentum_from_daily` 内）、`features.py:1518` dispatch 分支、`scripts/extract_xreg.py:85-89` 生产注册（自称 spec §4 调用方）、`task_FM/config/covariate_pool.json:212` 在池。模块（88 行）、3 个测试（`test_oi_gated_momentum.py` 349 行——本报告亦漏计、`test_features_oi_gated_dispatch.py`、`test_extract_xreg_oi_gated.py`）、`docs/2026-09-18-oi-gated-momentum-spec.md` 全部保留；裁定 (b) 撤销（spec v2 §0）。
2. **总量修正（第五节估算作废）。** cascade 死码候选 5 → 1（仅 lgbm_features，经裁定 e）；以 spec v2 全名单落纸为准：**立即归档 50 文件 / 12,374 行 + 顺延 2.9 三件套 3 文件 / 153 行 = 12,527 行**；cascade 保留 29 模块（第四节「保留 25」随之作废）。
3. **test_lgbm_features.py 补录。** `tests/test_lgbm_features.py`（144 行）不匹配 `test_a2*` 命名模式，被本报告与 v1 spec 双双漏计 → A2 批测试 4 → 5 件（1,854 行），A2 批总量 **16 文件 / 5,257 行**。教训沉淀进 spec v2 §1.1 第 4 筛：测试枚举不得依赖命名模式。
4. **第五次同型错误（K2 → N1 → P1 → spec §1.1 → 本例）。** 本报告以四道筛自居，却在 oi_gated_momentum 上漏检相对导入形态——首次轮到审核方自身，幸为执行前捕获，未造成损害。四道筛升级为**五道筛**（+相对导入形态 `from .X import`；+泛用名撞车 import 语句级验证，源自 `EXPECTED_FEATURE_COLUMNS` 同名不同源的边界确认）。spec v2 §1.1 已固化。
