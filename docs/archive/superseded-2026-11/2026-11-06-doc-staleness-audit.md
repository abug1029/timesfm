# FM_a 文档陈旧度审计报告
> 审计日期：2026-11-06
> 对照基准：master @ 1f90081
> 对照区间：257fcf3..1f90081（含 Baseline Point Contract + Laya 事故修复 + 慢环 no_data 修复 + 增量数据模式等）
> 审计范围：14 个活跃文档（不含 archive/、changelogs/、2026-09-*.md 旧 spec）

## 概要
- 审计 **14** 个文档
- **High**: 5 / **Med**: 8 / **Low**: 3
- 最落后的 3 个文档：
  1. **handbook.md**（最后核实 2026-10-05，落后 1 个月，缺失 Baseline Point Contract 全部变更）
  2. **system_design.md**（版本 1.6，2026-09-29，落后超 1 个月，仍有 TypeSafe Jev 预筛描述）
  3. **praxist.md**（仍写 TypeSafe Jev 预筛，未反映 Laya P1-P3 改进）

---

## 详细发现

### handbook.md（最后核实 2026-10-05，commit ee01b56）

- [**High**] L24 产品定位：「可交易方向 = 加权 1H 级联结果，日线斜率仅作 regime 副标签」
  - 应更新为：可交易方向 = `tradable_sign()`（`cascade/evaluation_metrics.py`），优先读 `position_sign`（新行，基于端点 `endpoint_delta`），旧行回退 `sign(delta_pred)`（加权 1H）。
  - 依据：commit c727308 已将 `tradable_sign()` 立为可交易方向唯一真源；Baseline Point Contract spec 定义了 `position_sign` / `endpoint_delta` / `endpoint_dir_ok`。
  - 链接 `docs/product_positioning.md`（已更新）。

- [**Med**] L63-L78 硬约束表：缺失 tradable_sign 为唯一可交易方向来源的约束。
  - 应补充：「可交易方向唯一真源 = `tradable_sign()`，不得用 `sign(delta_pred)` 或其他口径替代。」

- [**Med**] 品种口径：SC 已从 target_symbols 和 SCHEMES 中移除（2026-10-08 裁定），但本文品种数以 list_by_stars(2) 为指针，未显式提及 24 品种更新。
  - 建议：在 L85 附近补充链接到 `data_dictionary.md` 的当前品种表。
### system_design.md（版本 1.6，2026-09-29）

- [**High**] L890：「TypeSafe Jev 预筛」描述未更新为 Laya System-1 预筛。
  - 原文：「harvest 时 fire-and-forget 调 TypeSafe 三问……」
  - 应更新为：**Laya 预筛**（`cascade/typesafe_prescreen.py`），HTTP POST 到 Laya 服务（`LAYA_BASE_URL`），模型名仍为 `jev-latest`（Laya 兼容格式），支持多地址故障转移、指数退避重试（P1）、超时常量化（P2，`LAYA_COLD_START_TIMEOUT=180s` / `LAYA_WARM_TIMEOUT=15s`）、完整类型提示（P3）、预热检测（`_is_warmed_up` 标志）。详见 `cascade/typesafe_prescreen.py`。
  - 依据：commits 512a13b ~ cf2a149 系列。

- [**Med**] L77-L85 当前接线表：「可交易方向 = `position_from_forecast`（加权 1H）」——未反映 Baseline Point Contract 变更。
  - 应补充：`tradable_sign()` 为可交易方向唯一真源；`position_from_forecast` 产出 `position_sign` 和 `endpoint_delta`；`endpoint_dir_ok` 已移入 `signal_contract.py`。
  - 依据：commits 7a12008、04d7d7e、9b101bc、c727308。

- [**Med**] L371：`dir_ok` 由 `endpoint_dir_ok()`（`cascade/signal_contract.py:37`）在 endpoint 处计算，但文档未提及 `endpoint_dir_ok` 已作为独立函数移入 `signal_contract.py`（commit 7a12008）。
  - 应补充：dir_ok 不再依赖 weighted 方向，而是 endpoint 方向判定。

- [**Med**] L255-L260（评估指标节）：未提及 eval grid 已独立于 backtest（commit 2c2c778 `cascade/eval_grid.py`）。
  - 应补充：`cascade/eval_grid.py` 独立管理评估网格，`monthly_backtest.py` 不再内嵌 grid 逻辑。

- [**Low**] L12 版本声明仍为「1.6 (2026-09-29)」——应升级到 1.7 或更新版本号。

### docs/AGENTS.md

- [**High**] L35 Key Files 表：「系统设计全景：架构/数据流/协变量/评估/Praxist 三环 + TypeSafe 预筛」
  - 应改为：「……Praxist 三环 + Laya 预筛」。

- [**High**] L52 设计规格行：「设计规格（v23 / spec v15 / praxist_control_plane / TypeSafe 预筛）」
  - 应改为：「……Laya 预筛」。

- [**Med**] Key Files 表：`system_design.md` 描述中未反映 Baseline Point Contract 变更。
  - 建议补充链接到 `product_positioning.md`（tradable_sign 唯一真源）。

### praxist.md

- [**High**] L110 监督环步骤 4：「TypeSafe Jev 预筛（可选，软建议）：连 peer 提案同时 _prescreen_async……调 TypeSafe System One 三问……无 TYPESAFE_API_KEY 或降级时静默跳过」
  - 应更新为：**Laya 预筛**（替代 TypeSafe Jev）。HTTP POST 到 `LAYA_BASE_URL`（支持多地址故障转移），模型名 `jev-latest`（Laya 兼容），不需要 API key（`LAYA_SKIP_AUTH` 默认 True），支持指数退避重试（P1）、超时常量化（P2）、完整类型提示（P3）、预热检测（`warmup_laya()`）。详见 `cascade/typesafe_prescreen.py`。
  - 依据：commits 512a13b ~ cf2a149 系列。

- [**Med**] L109 PID 快照（PID 416）已过时。
  - 本文顶部已声明「过期时以磁盘为准」，可接受。
### data_dictionary.md（最后核实 2026-10-05）

- [**Med**] L25 品种集合：`SCHEMES` 数量 21 正确（实测确认），但「同期裁定：删 sc（原油）」的说明位置在 `target_symbols` 归一说明中，未单独作为 SCHEMES 的变更注记。
  - 代码证实：sc 不在 SCHEMES 中。建议明确「SCHEMES 21 个品种（2026-10-14 移除 SC）」。

- [**Low**] L118-L134 运行产物表：缺少 `task_FM/config/baseline_points_*.jsonl`（nocov 基线）和 `task_FM/config/baseline_metrics.json` 的条目。

### evaluation.md（最后核实 2026-10-05）

- [**Med**] 全文未提及 `tradable_sign()` 作为可交易方向唯一真源。
  - 应新增一节补充：`tradable_sign(point)`（`cascade/evaluation_metrics.py:178`）——优先读 `position_sign`，回退 `sign(delta_pred)`；`dir_acc` 的 `dir_ok` 判定现在由 `endpoint_dir_ok()` 在 endpoint 处计算。
  - 依据：commits 9b101bc、7a12008、c727308。

- [**Low**] L167 变更记录：应补充 2026-11-05 Baseline Point Contract 后的口径更新。

### runbook.md

- [**Med**] 缺失慢环 no_data 修复（commits 03e3171 ~ fb6a40a）相关内容：
  - P0-B fail-fast：组合协变量也抛 UnsupportedCovariateError
  - P3 队列清理：无效提案清理脚本
  - 建议新增一节「慢环队列管理」，链接到 `docs/runbook_praxist_three_loop.md`（已有队列清理节）。

- [**Med**] 缺失基线重生锁冲突修复（SQLite 超时 30s、进程互斥锁、增量重生）。
  - 建议新增「基线运维」节，说明 `incremental_baseline.py` 增量模式与 `generate_baseline_points.py` 的原子写入（.tmp 重命名）。

### README.md

- [**Low**] 「当前生产姿态」节仍写「无真实 3 星；--three-star = 信用>=2 星列表」。
  - 信用星级已退役（2026-10-08），应改为「--evidence 参数，档位为 solid/positive/negative/no_evidence」。
  - `data_dictionary.md` 已详细记录信用档退役，README 只需更新指针。

### runtime_contract.md

- [**Med**] L95-L105（v23 门判据节）：未反映 tradable_sign 作为可交易方向判定依据。
  - 建议新增一小节补充 tradable_sign 口径，或链接到 product_positioning.md。

### product_positioning.md / fingerprint_component_mapping.md / param_hygiene.md / module_freeze.md

- [**PASS**] product_positioning.md 已由 commit c727308 更新为 tradable_sign() 唯一真源。
- [**PASS**] fingerprint_component_mapping.md 无变更（协议指纹仍为 v4）。
- [**PASS**] param_hygiene.md / module_freeze.md 未涉及近期变更。

### paper_trading.md

- [**Low**] 回填对账口径：仍写 T+24 终点，但 tradable_sign 的引入意味着回填方向判定可优先用 position_sign。
  - 建议补充：「回填 `dir_correct_t24` 口径在 Baseline Point Contract 后应使用 `tradable_sign()` 判定。」
---

## 改写分组建议

按文件归属和修改范围分为 4 组，可并行执行：

### 组 A：可交易方向更新（Baseline Point Contract 核心变更）
**文件**：`handbook.md`、`system_design.md`、`evaluation.md`、`runtime_contract.md`
- 必改点：`tradable_sign()` 为唯一真源；`position_sign` / `endpoint_delta` / `endpoint_dir_ok`；eval grid 独立
- 涉及 High 项 3 个，Med 项 5 个

### 组 B：Laya 预筛统一命名
**文件**：`system_design.md`、`docs/AGENTS.md`、`praxist.md`
- 必改点：「TypeSafe Jev 预筛」改为「Laya 预筛」；补充 P1-P3 改进（重试/超时/类型提示）
- 涉及 High 项 3 个

### 组 C：运维补充（慢环 + 基线）
**文件**：`runbook.md`、`data_dictionary.md`
- 必改点：慢环 no_data 修复 / 队列清理 / 基线增量重生 / SC 移除注记
- 涉及 Med 项 4 个

### 组 D：轻量更新
**文件**：`README.md`、`paper_trading.md`
- 必改点：--three-star 改为 --evidence 指针更新；paper_trading 回填口径补充
- 涉及 Low 项 3 个

---
## 附录：代码事实验证命令

以下命令在 WSL 中运行以验证代码事实：

1. 验证 tradable_sign 存在：
   python3 -c "from cascade.evaluation_metrics import tradable_sign; print(callable(tradable_sign))"

2. 验证 SC 不在 SCHEMES：
   python3 -c "from config.prediction_scheme import SCHEMES; print(sc in SCHEMES)"

3. 验证 endpoint_dir_ok 在 signal_contract：
   grep -n "def endpoint_dir_ok" cascade/signal_contract.py

4. 验证 eval_grid 独立存在：
   ls cascade/eval_grid.py

5. 验证 Laya 预筛多地址 + jev-latest 模型名：
   grep -n "jev-latest" cascade/typesafe_prescreen.py
