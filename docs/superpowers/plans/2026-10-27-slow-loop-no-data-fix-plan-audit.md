# 慢环 no_data 修复实施计划审计

| 项 | 内容 |
|----|------|
| **审计日期** | 2026-10-27（Asia/Shanghai） |
| **对象** | `docs/superpowers/plans/2026-10-27-slow-loop-no-data-fix-plan.md` |
| **对照** | 调查报告修订稿 + 重审 audit（MD5 `70cedaeb…`，~86%）+ 现码/队列 |
| **审核性质** | Implementation Plan 审计（只审 plan，不实施、不改 plan） |
| **状态** | **有条件通过** |
| **就绪度** | **~80%** |
| **是否可授权实施** | **否（先改 plan 的 P0）**；方向可采纳，Task 2 伪代码与测试缺口须修订后再开工 |

---

## §0 路径 / MD5

| 路径 | MD5 | 说明 |
|------|-----|------|
| `/home/abug/timesfm/docs/superpowers/plans/2026-10-27-slow-loop-no-data-fix-plan.md` | `52ef56644f23f1bf729ece63616a78cc` | 本轮审计对象 |
| `/home/abug/timesfm/docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation.md` | `24eb2f70afa6a4d2ba26c28f59d48b46` | 较重审时 `e77a039e…` 又有修订；已吸收 schema/~11 |
| `/home/abug/timesfm/docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation-audit.md` | `70cedaebac42d07e9cbb6606c82ab4e2` | 重审 audit（与 box mirror 一致） |
| `D:\FlyBuddy\docs\superpowers\plans\` 同名 plan | — | **不存在**（目录在，无 slow-loop plan）；本 audit 仍同步写入 D: plans |
| 本 audit（WSL） | （与下同） | `/home/abug/timesfm/docs/superpowers/plans/2026-10-27-slow-loop-no-data-fix-plan-audit.md` |
| 本 audit（box） | 落档后三路径同 MD5 | `/workspace/shared/reviews/2026-10-27-slow-loop-no-data-fix-plan-audit.md` |

---

## §1 一句话

Plan 正确吸收了重审遗留的 **pool schema** 与 **pending ~11（非 81）**，主根因/非 Laya/入队+fail-fast+清队方向成立；但 **Task 2 fail-fast 伪代码不可照抄**（错误函数签名、虚构 `_REGISTERED_COVARIATES`），且 **Task 1 未点名更新现有 `test_enqueue_reprocess`（fixture 用族名 `momentum` / 未注册 `basis`）**——**就绪度 ~80%，修完 P0 后再授权实施**。

---

## §2 Plan vs 调查报告 / 重审遗留 / 现码

### 2.1 重审 audit 遗留闭合

| # | 重审要求 | Plan 吸收情况 | 现码/队列实证 |
|---|----------|---------------|---------------|
| 1 | `load_supported_covariates`：`families`=list；合法名在顶层 `covariates` 的 `status:"active"` | Task 1/引用报告 P3 **已按正确 schema 写** | pool：`families` list[6]；`covariates` dict[31] 全 `active` |
| 2 | 清队勿写死 ~81；pending doomed≈十余 | 背景/Task 3 写 **~11**；未把 81 当清队数 | 现 pending **207**；unsupported cov **10**；+`symbol=="c"` 且 cov 合法 **1** → **11** |
| 3 | §7「333」残留 | Plan 未引用 333 | 报告路径表已改 ~210；结论段仍有一处「约 81」叙事残留（不影响 plan 清队数） |
| 4 | 主根因：族名/幻觉名作 `cov_override` → ValueError → no_data；非 Laya | 背景 § 正确；P1 指向 Praxist peer | `build_covariate_matrix` else 抛 `不支持 covariate_type`；`monthly_backtest` **逐点** `except Exception` 吞掉后继续满点 → `summarize` 全 error → `None` → ASL `_no_data_verdict` |
| 5 | 入队白名单 + 评估 fail-fast + registry 重估后再清队 | Task 1 / 2 / 3 结构对齐 | 入队脚本现无白名单；fail-fast 未落地；清队脚本未建 |

### 2.2 关键现码事实

1. **`scripts/enqueue_reprocess.py`**：scan → dedup → `filter_existing_verdicts` → 盲写队列；无 cov 校验。`ProposalInfo.cov_override` 字段存在，plan 挂钩点正确。
2. **`cascade/features.py`**：`build_covariate_matrix(symbol, store, historical_daily_closes, predicted_daily_closes, ..., covariate_type=...)`；未知类型 `raise ValueError("…不支持 covariate_type=…")`。别名分支含 `slope_only/none/baseline`。**31 个 active 均已分派**（与 pool 对齐）。
3. **不存在** plan Task 2 所写的 `_REGISTERED_COVARIATES` 常量。
4. **`monthly_backtest.run_symbol_backtest`**：协变量错误在 eval 循环内被泛化 `except Exception` 捕获并 `points.append({..., "error": ...})`，**不中断**，导致满点空转。
5. **`aligned_slow_loop`**：`data is None` / `summarize is None` → `_no_data_verdict`；外层未捕获异常 → error tombstone（与 no_data 不同）。
6. **测试债**：`tests/test_enqueue_reprocess.py` 用 `cov_override="momentum"`（族名）与 `"basis"`（非 active）——按 Task 1 落地后 **现有断言会红**。

### 2.3 报告「~11」口径 vs Task 边界

| 子集 | 现 pending 计数 | Task 1 会拦？ | Task 3（报告 P3）会清？ |
|------|-----------------|---------------|-------------------------|
| 族名 cov | 2（`term_structure`,`volatility`） | ✅ | ✅ |
| 未注册幻觉名 | 8 | ✅ | ✅ |
| `symbol=="c"` 且 cov 合法 | 1 | ❌（未写） | ✅ |
| **合计与「~11」** | **10+1=11** | 仅 **10** | **11** |

Plan 应用「约 11」作清队预期时须写明含品种 `c`；入队验收不应声称单独由 Task 1 消除全部 11。

---

## §3 任务拆分 / 验收 / 风险

| Task | 评价 | 主要问题 |
|------|------|----------|
| **1 P0-A 入队校验** | 方向正确；loader 片段可作实施底稿 | 未要求更新/扩展 `test_enqueue_reprocess`；未过滤 `symbol=="c"`（与 ~11 口径不一致，可接受若明文归 P3/P2） |
| **2 P0-B fail-fast** | 必要性高（现码逐点吞异常） | **伪代码不可照抄**：签名错误；虚构 registry 常量；「先调 `build_covariate_matrix`」缺 store/序列。应改为：在 eval 循环前用与 Task 1 相同的 supported 集校验 `effective_single`，失败则 **立即 `return None`（或抛一次专用异常并由 ASL 写成明确 status）** |
| **3 P3 清队** | 安全措施（停消费/锁/备份/原子替换）合理；委托报告 §P3 且报告 loader 已改对 | 「约 11」须按实施当日 pending 重扫，勿写死；与慢环锁文件名（ASL 用 `aligned_slow_loop.lock`）不同，计划已要求先 `pkill`——保留 |
| **4 集成测试** | 覆盖面够 | 应显式包含：旧 enqueue 单测变绿；fail-fast 耗时/点数远小于满窗；清理前后行数与备份 |

**依赖**：写「Task 1∥2 可并行」合理；「Task 3 依赖 Task 1 共用 loader」名不副实——Task 3 新建脚本内自带拷贝。建议 P1 抽共享 helper，避免三处漂移。

**风险表**：schema 变更/误杀/并发 — 基本到位。缺：**测试回归**与 **fail-fast 误用 error tombstone vs no_data** 的状态语义风险。

**验收清单**「代码提交并推送」超出本 standing 审计授权；实施阶段需用户另授 commit/push，审计本身禁止。

---

## §4 Laya 硬约束

| 检查 | 结果 |
|------|------|
| 是否主张训练/学习/改权重/进化 Laya？ | **否** |
| 根因归属 | Praxist peer 生成错误名；Laya 仅预筛软建议 — 与报告一致 |
| P1 后续 | peer prompt 白名单 /（报告侧）typesafe 硬门 — **非** Laya 训练 |

**Laya 硬约束：通过。**

---

## §5 P0 / P1 / P2（开工前须改 plan 的项）

### P0（必须改 plan 后再授权实施）

1. **重写 Task 2 实施步骤**：禁止照抄当前 `build_covariate_matrix(cov_override, …)` / `_REGISTERED_COVARIATES`。改为：
   - 复用 Task 1 的 `load_supported_covariates()`（或共享模块）；
   - 在 `run_symbol_backtest` 解析出 `effective_single` 后、**进入 eval 循环前**校验；不在 supported（且非 combo 路径）则立即 `return None`（或抛一次 `UnsupportedCovariateError`，由 ASL 映射为可区分 status）；
   - 明确：仅靠「第一点 try/except」不够——现码已在逐点 except 里吞掉并继续，必须 **中断整次 backtest**。
2. **Task 1 补测试债**：修订 `tests/test_enqueue_reprocess.py` fixture 为真实 active 名（如 `vor`/`rsi_slope`）；新增族名与未注册名被 skip、`invalid_covariate` 计数断言。
3. **统一「~11」口径**：正文写明 = unsupported cov（现 ~10）+ 可选 `symbol=="c"`（现 1）；Task 1 验收不包含 c，除非显式加过滤。

### P1（应改，不挡方向）

1. 抽取共享 `load_supported_covariates`（enqueue / cleanup / backtest 共用），避免拷贝漂移。
2. P1 后续文案「30 个」改为 **31**（与 pool active 一致）。
3. fail-fast 建议区分 `unsupported_covariate` vs 真 `no_data`（plan 已标可选——升为推荐）。
4. `covariate_pool.json` 路径改为相对仓库根的稳定定位（与其它脚本一致），避免纯 CWD。
5. 验收清单的 commit/push 标为「另授权限」，勿与功能验收混绑。

### P2（可选）

1. 报告结论段残留「约 81」与 plan/清队口径并存时，实施 changelog 以 pending 实扫为准。
2. D: 无同名 plan；仅 audit 同步。实施后若需 FlyBuddy 镜像再拷 plan。

---

## §6 结论

| 问题 | 答案 |
|------|------|
| Plan 是否吸收重审 schema / ~11 / 非 Laya / 三件套方向？ | **是** |
| 可否整份照抄伪代码实施？ | **否**（Task 2 伪代码坏；enqueue 单测未纳入） |
| 可否有条件授权实施？ | **修完 §5 P0 后可以** |
| 就绪度 | **~80%** |
| Laya 硬约束 | **通过** |
| 本轮是否改实现/改 plan/commit/push？ | **否**（只读 + 写本 `*-audit.md`） |

**总评**：有条件通过 ~80%。主路径正确；开工前必须改 Task 2 设计与 Task 1 测试计划，并写清 ~11 含品种 c 的口径。

