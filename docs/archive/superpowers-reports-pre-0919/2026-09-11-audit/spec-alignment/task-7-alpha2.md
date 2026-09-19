# Task 7：Alpha2 与已关轨 spec

- **任务**: spec–代码对齐计划 Task 7（只读；写本报告）
- **计划**: `docs/superpowers/plans/2026-09-11-spec-code-alignment.md` L151–160
- **仓**: WSL `/home/abug/timesfm`（HEAD `9653264`）
- **审核日**: 2026-09-11
- **对照 spec**: `2026-08-04-alpha2-phase1-baseline-gate-design.md`、`2026-08-05-a2-p1-dense-cache-resume-design.md`、`2026-08-05-a2-p1-market-vectorize-design.md`、`2026-08-05-a2-p1-runtime-redesign.md`
- **杀手来源**: `STATE.md` A2-P1/P2；`docs/module_freeze.md` CF-13 A
- **生产入口**: `scripts/copilot.py`、`scripts/cascade_predict.py`、`scripts/monthly_backtest.py`、`scripts/praxist_supervisor.py`
- **不改**: 生产代码、SCHEMES、`.env*`；不启动 Praxist
- **本子代理无 LSP 诊断通道**。替代证据：四入口 AST import + 全文检索 `a2_p1`/`lgbm_features`；`python3 -m py_compile` 四入口 + 残留 A2 模块 → **COMPILE_OK**

**判定口径（计划 L21–24）:** 设计失效的合法杀手是更高权威关轨（STATE 0/N GO、CF-13 永久关闭），不是「状态栏待审核」。失效条款不评代码对错。评价秤若仍被 monthly / 慢环使用，改走 hardening/eval，不在本任务报 Alpha2 缺口。

---

## 结论先行

**四份 Alpha2 spec 作为生产模型合同全部失效。** 残留脚本仍在，且大体还按当年探针架构实现对齐，但没有任何生产入口 import 它们。

| 文件 | 判定 | 杀手 | 残留代码 vs 自身 spec |
|------|------|------|------------------------|
| `docs/superpowers/specs/2026-08-04-alpha2-phase1-baseline-gate-design.md` | **失效** | STATE A2-P1 **0/5 GO**（L73–76）→ 用户特批后的 A2-P2 仍 **0/5 GO**；`module_freeze.md:9` CF-13 **A 永久关闭 Track B** | 探针脚本残留；**不对齐生产** |
| `docs/superpowers/specs/2026-08-05-a2-p1-dense-cache-resume-design.md` | **失效** | 只服务 A2-P1 探针；Track B 关轨后无独立生产合同 | **残留且对齐**（三级缓存接口仍在 `lgbm_features.py`） |
| `docs/superpowers/specs/2026-08-05-a2-p1-market-vectorize-design.md` | **失效** | 同上 | **残留且对齐**（`precomputed` + hurst 预计算，PCA 仍切片） |
| `docs/superpowers/specs/2026-08-05-a2-p1-runtime-redesign.md` | **失效** | 同上 | **残留且对齐**（Orchestrator / Worker / 排他锁仍在）；网格数字已跟 `backtest_config.STEP`，不再是 spec 里的 step=24 / ~396 |

**计划 Task 1 预置嫌疑「A2-P1 评价秤/JSONL 若仍被工具使用 = 部分有效」在 monthly / 慢环上证伪。** monthly 只用 `metrics_from_backtest_points`（PF/EV/MaxDD/DirAcc），这是 Alpha2 明确「不动」的旧秤，不是 A2-P1 新合同。`calc_vol_scaled_mae` 与 A2 JSONL 形态没有进生产入口。那些公式的对错归 Task 2 / 上一轮 Task 7 eval，本报告不报缺口。

仓外三份 Praxist 文档快判见 §6：`praxist_peer_evaluation_fix.md` **失效**；另外两份 **残留**（方案稿 / 部分条款已被方案 A 横幅降级）。

---

## 1. 生产入口是否还 import `a2_p1_*`

AST 解析四入口 + `aligned_slow_loop.py`（慢环，对照用）。命中规则：`import` / `from` 模块名或名字里出现 `a2_p1`、`a2_p2`、`lgbm_features`、`alpha2`。

| 入口 | 行数 | `a2_p1` / `a2_p2` / `lgbm_features` / `Alpha2` 命中 | 实际从 cascade/scripts 拉了什么 |
|------|------|------------------------------------------------------|----------------------------------|
| `scripts/copilot.py` | 835 | **0** | `DailyModel`、`_compute_direction_v2`、`HourlyModel`、`VolRiskFilter`、`cascade_predict.TICK_SIZE` |
| `scripts/cascade_predict.py` | 957 | **0** | `DailyModel`、`HourlyModel`、`position_from_forecast`、`VolRiskFilter`、`_calc_atr` |
| `scripts/monthly_backtest.py` | 1015 | **0** | `DailyModel`、`HourlyModel`、`metrics_from_backtest_points`（L49）、`position_from_forecast`（L50） |
| `scripts/praxist_supervisor.py` | 1577 | **0** | 无 cascade / a2 import |
| `scripts/aligned_slow_loop.py`（对照） | — | **0** | `DailyModel`、`HourlyModel`、`calc_margin_maxdd_robust` |

反向调用（全仓 `.py`，排除 venv）：

| 符号 | 调用方（全部） |
|------|----------------|
| `a2_p1_*` 模块 | 仅 `scripts/a2_p1_*.py`、`scripts/a2_p2_*.py`、`tests/test_a2_*.py`、`cascade/lgbm_features.py:289`（`from scripts.a2_p1_runtime import generate_eval_grid`） |
| `cascade.lgbm_features` | 仅 `scripts/a2_p1_worker.py`、`a2_p1_lgbm_baseline.py`、`a2_p2_worker.py`、`a2_p1_runtime.py`、`tests/test_a2_p1_runtime.py`、`tests/test_lgbm_features.py` |
| `calc_vol_scaled_mae` | 定义在 `cascade/evaluation_metrics.py:285`；调用只在 `scripts/a2_p1_lgbm_baseline.py` 与 `tests/test_vol_scaled_mae.py` |
| `train_lgbm_walkforward` | 仅 A2 worker / baseline / 对应测试 |

`cascade/` 包内除 `lgbm_features.py` 自身外，没有任何兄弟模块 import 它。四入口不会因为 `import cascade` 间接拉进 A2。

**因此：LGBM 当生产模型、残差叠加、A2 运行时，整条 Track B 设计对生产路径失效。** 代码还在磁盘上，只是归档探针。

---

## 2. 关轨证据（杀手，不是状态栏）

### 2.1 STATE.md（权威层 1）

A2-P1（L44–76）：

- 原始运行 16 品种可复核，全部 NO-GO
- A2-P1.1 定向修复 FG/TA/BU/AO/UR，去重后 **0/5 GO**
- 不满足启动 A2-P2 的预设门槛（≥2 GO）
- 用户批准后仍启动了 A2-P2（2026-08-07）

A2-P2（L80–112）：

- 目标：`Y_residual = Y - timesfm_pure_pred`，`stacked = timesfm_pure + lgbm_residual`
- 5/5 NO-GO；Stacked PF 全部 &lt; 1.0，且低于 scheme PF
- **关闭 Track B（残差叠加方向），不启动 A2-P3**
- **当前生产姿态不变**：Copilot 仍是盘中入口；预测与 Vol Overlay 红线不因 A2 结果改变（L110–112）

### 2.2 冻结表

`docs/module_freeze.md:9`：

> A2 LGBM / 残差 Track B | CF-13 **A** | **永久关闭**（0/5 GO）；代码保留作归档

`scripts/AGENTS.md:20-21` 入口矩阵已写明：A2 LGBM 基线是实验编排；A2 残差叠加「Track B 已 NO-GO 关闭」。

### 2.3 spec 自己也不是生产合同

`2026-08-04-alpha2-phase1-baseline-gate-design.md` L5–7、L33–38：

- Track B 模型线；范围仅 A2-P1；A2-P2/P3 spec 待门禁后再做
- 非目标：**不修改** `forecast_with_covariates` 或任何生产预测路径；不改 `prediction_scheme.py` / `features.py`；Copilot 改造是 A2-P3

P1 本意是探针。探针失败 + P2 失败 + CF-13 关轨之后，这四份文件不再约束 `copilot` / `cascade_predict` / `monthly_backtest` / `praxist_supervisor`。

状态栏仍写「Draft / 待审核」——按计划 L21，**不够当杀手**，只说明文档没补关轨横幅。真正杀手是 STATE + CF-13。

---

## 3. 四份 spec 条款级判定

失效条款不评「代码缺口」。残留实现对齐只说明归档脚本还认得当年设计，不恢复合同效力。

### 3.1 `2026-08-04-alpha2-phase1-baseline-gate-design.md` — 失效

| 条款 | spec | 活事实 | 判定 |
|------|------|--------|------|
| LGBM-B 打败 TimesFM-scheme 则启动 A2-P2 | L52–60 | 0/5 GO；Track B 关闭 | **失效**（已裁决） |
| 12 维宽特征池当树模型天花板探针 | L73+ | 只在 `cascade/lgbm_features.py`；生产入口 0 import | **失效**（生产模型）；残留库仍实现 |
| 三曲线 PF/EV/MaxDD + 配对 bootstrap | L44–60 | 只在 `a2_p1_lgbm_baseline.evaluate_gate` / A2 report | **失效** |
| 追加 `calc_vol_scaled_mae`，DirAcc 仅 logging | L28–29、L64–69 | 函数在 `evaluation_metrics.py:285`；monthly **不调用** | 残留函数；**不是** monthly 合同 |
| 不动 `calc_net_metrics` / 生产预测路径 | L33–38、L122 | 四入口仍 TimesFM XReg + `position_from_forecast` | 这条 Non-Goal **被生产遵守**，但那是「没把探针接进生产」，不是「spec 仍有效」 |

同名 `.txt` / 截断 `...-desig.txt` 按 Task 3 忽略，不当合同。

### 3.2 `2026-08-05-a2-p1-dense-cache-resume-design.md` — 失效；残留对齐

| 条款 | spec | 残留代码 | 对齐？ |
|------|------|----------|--------|
| 三级缓存 `market.parquet` / `tsfm.jsonl` / `dense_matrix.parquet` | L35–46 | `lgbm_features.build_dense_feature_matrix` L259–275、L270–275 | **残留且对齐** |
| `compute_timesfm_features_batch(..., resume_path=)` | L76–86 | 同文件；A2 worker 传入 `tsfm_resume_path` | **残留且对齐** |
| 不改 12 维 / step=24 / Gate | L163 | 残留默认 `dense_step=24`（L255）；eval 网格已改读 `STEP` | 网格数字跟了 hardening，见 §4 |

无生产调用 → **整份失效**。

### 3.3 `2026-08-05-a2-p1-market-vectorize-design.md` — 失效；残留对齐

| 条款 | spec | 残留代码 | 对齐？ |
|------|------|----------|--------|
| `extract_market_features_at_bar(..., precomputed=)` | L55–76 | `lgbm_features.py:40-47` | **残留且对齐** |
| hurst 等安全特征预计算；`pca_momentum` / `vol_prob` 仍切片 | L38–50 | `build_dense_feature_matrix` 传 `precomputed`（约 L332）；测试 `test_a2_p1_runtime.py` 锁 PCA 切片 | **残留且对齐** |
| 向后兼容 `precomputed=None` | L76 | 默认 None | **残留且对齐** |

无生产调用 → **整份失效**。spec L76 写「Copilot 等其他调用方不受影响」——今天 Copilot 根本不调这个函数，这句话已无对象。

### 3.4 `2026-08-05-a2-p1-runtime-redesign.md` — 失效；残留对齐（网格除外）

| 条款 | spec | 残留代码 | 对齐？ |
|------|------|----------|--------|
| Orchestrator / Worker 进程隔离 | L35–56 | `scripts/a2_p1_orchestrator.py`、`a2_p1_worker.py` | **残留且对齐** |
| JSONL 逐点 flush + 排他锁 | L70–111；完整性硬化后的 `a2_p1_runtime` | `exclusive_result_lock`、`append_unique_record` | **残留且对齐** |
| `stable_symbol_seed`（SHA256，非 `hash(symbol)`） | 完整性硬化；runtime spec L118 原写 `hash(symbol)` | `a2_p1_runtime.py:22-29` | 残留对齐的是后续硬化，不是 runtime spec 原文 |
| 监控 `a2_p1_status.py` | L176–189 | 文件仍在 | **残留且对齐** |
| walk-forward step=24、~396 pending | L232–238、L247 | `generate_eval_grid` 现读 `CONTEXT_BARS/EVAL_WINDOW_BARS/STEP`（`a2_p1_runtime.py:19,147-156`），与 monthly L220–222 **同构** | 数字已不是 396；跟的是现行 `backtest_config`，**不是**本 spec 的 396 合同 |

无生产调用 → **整份失效**。不要把「A2 runtime 现在跟 monthly 用同一套 STEP」读成「Alpha2 网格仍有效」——那是 eval 网格重构（`ee1f176`）扫进了归档脚本。

---

## 4. 残留脚本清单（归档，不是生产）

`scripts/AGENTS.md:20-21` 已把它们标成实验入口；CF-13 说代码保留作归档。

**A2-P1**

| 文件 | 角色 |
|------|------|
| `scripts/a2_p1_orchestrator.py` | 品种级调度 |
| `scripts/a2_p1_worker.py` | 单品种 JSONL 探针 |
| `scripts/a2_p1_runtime.py` | run_id / 锁 / eval grid / 幂等 JSONL |
| `scripts/a2_p1_lgbm_baseline.py` | 旧单进程入口 + `train_lgbm_walkforward` / `evaluate_gate` |
| `scripts/a2_p1_generate_report.py` | 裁决报告 |
| `scripts/a2_p1_status.py` | 进度表 |
| `scripts/a2_p1_restore_manifest.py` | 历史 JSONL 清单 / 安全恢复 |

**A2-P2（关轨后的残留，无独立有效 spec）**

| 文件 | 角色 |
|------|------|
| `scripts/a2_p2_orchestrator.py` | 残差叠加调度 |
| `scripts/a2_p2_worker.py` | `Y_residual` / stack |
| `scripts/a2_p2_generate_report.py` | P2 报告 |

**共享库（放在 `cascade/` 但不被生产入口 import）**

| 文件 | 角色 |
|------|------|
| `cascade/lgbm_features.py` | 12 维 dense 矩阵；反向依赖 `scripts.a2_p1_runtime.generate_eval_grid`（L289） |
| `cascade/evaluation_metrics.py:285` `calc_vol_scaled_mae` | A2 诊断字段；monthly 不用 |

**测试（只锁归档行为）**

`tests/test_a2_p1_baseline.py`、`test_a2_p1_runtime.py`、`test_a2_p1_integrity.py`、`test_a2_p2_integrity.py`、`test_lgbm_features.py`、`test_vol_scaled_mae.py`

**文档残留（不是 spec 合同）**

- 计划：`docs/superpowers/plans/2026-08-04-alpha2-phase1-baseline-gate.md`、`2026-08-05-a2-p1-*.md`、`2026-08-05-alpha2-next-steps.md`（仍写「全量运行未完成」，已被 STATE 结案 supersede）、`2026-08-07-a2-p1-integrity-hardening.md`、`2026-08-07-a2-p2-residual-stacking.md`
- `cascade/AGENTS.md:23` 仍把 `lgbm_features.py` 列在 cascade 地图里，未标明「归档 / 生产不 import」

本次 `rglob` 未找到 `reports/a2_p1_results*`、`reports/a2_p1_features/`、`reports/research/20260807_a2_p2_verdict.md` 等磁盘产物。STATE 仍引用它们。缺产物不改变关轨结论，只说明归档结果可能已不在工作树。

---

## 5. 评价秤：明确不报 Alpha2 缺口

Alpha2 spec L122：「改（追加）`calc_vol_scaled_mae`；**不动** `calc_net_metrics` / `compare_strategies` 决策逻辑。」

monthly 实际秤：

```
scripts/monthly_backtest.py:49  from cascade.evaluation_metrics import metrics_from_backtest_points
scripts/monthly_backtest.py:450 net = metrics_from_backtest_points(...)
```

`evaluation_metrics.py` 文首 L1–19 仍是 PF / EV / EV_ratio / MaxDD / DirAcc。这是全项目唯一秤，hardening / 上一轮 Task 7 eval 的合同，**不是** A2-P1 留下的有效条款。

| 容易误报成「Alpha2 缺口」的东西 | 为什么本任务不报 |
|----------------------------------|------------------|
| PF / EV / MaxDD / DirAcc 公式 | Alpha2 声明不动；monthly 仍用；归 eval/hardening |
| IC = `2×\|dir_acc−0.5\|`、`gate()` 不含 EV | 方案 A / loop-constraints / 上一轮 Task 7；与 LGBM 探针无关 |
| STEP=2、EVAL_WINDOW_BARS=1200、理论 n=589 | `ee1f176` 网格重构；A2 runtime 只是跟读同一常量 |
| `calc_vol_scaled_mae` monthly 不用 | 残留诊断函数，不是生产缺口，也不是仍有效的 A2 合同 |
| A2 JSONL 形态 | 只有 A2 脚本读写；monthly 有自己的 checkpoint JSONL |

**不要**在失效 spec 下写「monthly 没接 LGBM 三曲线」当缺口——Non-Goal 就是不准接进生产，关轨后更不准。

---

## 6. 仓外三份 Praxist 文档（只判失效 / 残留）

计划清单 18–20。不在此做条款级对齐（那是 Task 4/5）。

| 文件 | 判定 | 理由 |
|------|------|------|
| `docs/praxist_directive_design.md` | **残留**（§3 失效，指令闭环降级为历史解释） | 文首 L3 已写：指令闭环「仍有效」；§3 diagnostic/aligned 阶梯与「peer 跑评估」被 2026-09-08 方案 A 取代。现行合同是 `spec_hypothesis_driven_fast_loop_20260908.md`。不要按 §3 去给 peer 开评估。 |
| `docs/praxist_integration_plan.md` | **残留**（已实施的 2026-09-01 方案稿） | 文首 L3–6：P0–P3 已落地；路径与架构以 `praxist.md` / runbook 为准。`/root/timesFM_fu`、独立 `/root/.praxist-venv`、peer 跑 diagnostic、磁盘 8.4GB 均为过时假设。不是现行合同，也不是「待执行」。 |
| `docs/praxist_peer_evaluation_fix.md` | **失效** | L4 状态仍是「待执行」。全文目标是让 peer 绕过 delete guard 去跑 `evaluations/fm_eval/run.py`。方案 A 之后 peer **禁止**评估、禁止加载 TimesFM。按这份文档施工会把死设计接回主路径。杀手：`loop-constraints.md` 方案 A；`docs/praxist.md` L65–67。上一轮 SUMMARY M-02 已点名状态栏「待执行」。 |

---

## 7. 建议（不落地）

文档横幅，不是改生产代码：

1. 四份 Alpha2 spec 文首加：Track B 已 CF-13 / STATE 0/5 GO **永久关闭**；生产入口不 import；代码是归档。
2. `2026-08-05-alpha2-next-steps.md` 头上写「已被 STATE 2026-08-07 结案 supersede」，避免执行者按「全量运行未完成」再开 20 品种探针。
3. `cascade/AGENTS.md` 给 `lgbm_features.py` 标「归档 / 生产入口不 import」。
4. `praxist_peer_evaluation_fix.md` 状态从「待执行」改成「失效（方案 A）」，或删。
5. **不要**为了对齐这四份 spec 去改 `copilot` / `cascade_predict` / `monthly_backtest` / `praxist_supervisor`。
6. **不要**删残留脚本当本审核的产出——CF-13 明确代码保留作归档；删除是另开的清理 plan。

---

## 8. 给 Task 8 的一行

| ID | spec | 有效/失效 | 对齐 | 缺口计数 | 备注 |
|----|------|-----------|------|----------|------|
| 11 | `2026-08-04-alpha2-phase1-baseline-gate-design.md` | **失效** | 不适用（生产）；残留探针仍实现 12 维 + gate | 0（不评失效条款） | 杀手 STATE L73–103 + CF-13 |
| 13 | `2026-08-05-a2-p1-dense-cache-resume-design.md` | **失效** | 残留且对齐 | 0 | 无生产 import |
| 14 | `2026-08-05-a2-p1-market-vectorize-design.md` | **失效** | 残留且对齐 | 0 | 无生产 import |
| 15 | `2026-08-05-a2-p1-runtime-redesign.md` | **失效** | 残留且对齐（网格数字已跟 STEP=2） | 0 | 无生产 import |
| 18 | `docs/praxist_directive_design.md` | **残留**（§3 失效） | — | — | 横幅已指向方案 A |
| 19 | `docs/praxist_integration_plan.md` | **残留** | — | — | 已实施的方案稿 |
| 20 | `docs/praxist_peer_evaluation_fix.md` | **失效** | — | — | 「待执行」与方案 A 相反 |
