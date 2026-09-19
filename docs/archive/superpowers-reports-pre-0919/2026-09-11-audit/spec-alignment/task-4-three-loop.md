# Task 4：方案 A + 三环骨架 条款对齐

> **仓**: WSL `/home/abug/timesfm`（HEAD `9653264`）  
> **绑定合同**: `docs/spec_hypothesis_driven_fast_loop_20260908.md`（方案 A，已实施）  
> **骨架 spec**: `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md`（按条款拆：骨架仍有效，诊断收割失效）  
> **杀手**: `loop-constraints.md:47-49`、方案 A 全文、`docs/superpowers/specs/praxist_control_plane.md:191`  
> **方法**: 只读对照活代码 + 测试。不把已作废的 diagnostic 收割当代码缺口。不改生产代码。  
> **日期**: 2026-09-11

## 计数

| 判定 | 方案 A | 09-02 仍有效骨架 | 09-02 已失效 | 合计 |
|------|--------|------------------|--------------|------|
| 对齐 | 25 | 21 | — | **46** |
| 部分对齐 | 8 | 6 | — | **14** |
| 缺口 | 2 | 0 | — | **2** |
| 失效 | 1 | — | 10 | **11** |

计数 = 下文各判定表的数据行（不含表头）。点名 8 项是子集，不另加。

**三路汇总（本任务要求回报）：**

- **valid-aligned（对齐）: 46**
- **valid-gap（缺口）: 2**
- **invalidated（失效）: 11**

另有 **14** 条部分对齐，计入有效合同，不计入缺口、也不计入失效。

有效性预置已在本文件自证：方案 A 整份仍有效（仅「glob 仅本 run」被同文件 2026-09-09 增补废止）；09-02 的三环骨架 / 慢环唯一写 / daily 缓存 / 429 resume / phase 互斥仍有效；09-02 的 diagnostic 筛选与诊断幸存者收割失效。

---

## 计划点名（8 项必须先看）

| # | 点 | spec | 代码 | 测试 | 判定 | 严重度 |
|---|----|------|------|------|------|--------|
| 1 | `_harvest_rows` 走 `harvest_proposals`，不读诊断 | 方案 A `:142-149`、`:57` | `praxist_supervisor.py:1283-1294` 只调 `harvest_proposals`；glob `results/**/proposals/*.json`（`:596`）。`harvest_survivors`（`:419`）读 `evaluation_summary.json`，**无生产调用**（仅测试/回滚） | `tests/test_harvest_proposals.py`；`test_supervisor.py:322-368` 主循环造提案入队 | **对齐** | — |
| 2 | `mechanism >= 40` 字拒绝并计数 | 方案 A `:103`、`:144`、`:227` | `:613-623` `len(mechanism) < 40` → `_reject("mechanism_too_short")` | `test_short_mechanism_rejected` | **对齐** | — |
| 3 | schema `fm.hypothesis_proposal.v1` 不符即拒绝 | 方案 A `:97-98`、`:144`；`loop-constraints.md:49` | `harvest_proposals` **从不读** `p["schema"]`。缺字段或写错 schema，只要有 symbol+cov+满 40 字 mechanism 就会入队 | 夹具都带合法 schema；**无** `schema_mismatch` 用例 | **缺口** | HIGH |
| 4 | 慢环唯一写 `aligned_verdicts.jsonl` | 09-02 `:96-97`；`loop-constraints.md:18`；方案 A `:65` | 生产 `append_verdict` 仅 `aligned_slow_loop.py:119-122`。监督环 `REGISTRY` 只 `load_snapshot`。`praxist_assets_archive.py:292` `restore-verdicts` 是人工 CLI，不在 300s tick | 慢环写入有测；无「supervisor 不得 open(REGISTRY,"a")」锁 | **对齐**（活路径）；CLI 例外见部分对齐表 | — |
| 5 | phase 互斥：慢环未抽干禁止下一轮快环 | 09-02 `:54`、`:112` | `ensure_phase:929-936` 队列忙或慢环活 → `phase=slow`。`decide_fast_loop:1151-1152` slow 直接 return。`main:1537-1541` slow 优先于 start | `test_harvest_survivors_enter_slow_no_start_no_cycle`；`test_phase_slow_blocks_start_even_in_window` | **对齐** | — |
| 6 | 429 后 resume 同一 run | 09-02 `:148`；`docs/praxist.md:80` | 同提供商：`decide_fast_loop:1174-1178` `_plan_resume(rd, "primary", ...)`。**例外**：`_failover_can_resume_same_run:320-329` 模型 id 不同（claude→qwen）则 FRESH `start` | `test_429_stop_then_resume`、`test_429_stop_via_main_once_then_resume` 锁 resume；`test_paused_429_fresh_start_on_identity_wall` 把开新 run 锁成预期 | **部分对齐** | MEDIUM |
| 7 | 日线预测缓存键 | 09-02 `:72-73` `f"{symbol}\|cutoff\|{CONTEXT_DAYS}x{HORIZON_DAYS}\|fp[:12]"` | 逻辑元组含 symbol / cutoff / `{context}x{horizon}` / 12 位指纹；实现是 `_DAILY_CACHE_VER` + 上列再 sha256，文件名 `daily_{symbol}_{key[:16]}.pkl`（`monthly_backtest.py:66,104-107,163-173`）。指纹是各 shard **前 16MiB** 的 sha256，不是整文件 | `tests/test_daily_pred_cache.py` 锁 cutoff 分键、指纹 12 位、mtime 失效、slow A/B | **部分对齐** | LOW |
| 8 | peers 禁止评估 / 禁止加载 TimesFM | 方案 A `:37`、`:1.4`；`loop-constraints.md:49`；`praxist.md:67` | **软闸**：`prompt_base.jinja2:5-9`、`skill.md:3-6`、`task.yaml:9-11,24`。**能力面仍开**：`task.yaml:54-55` `diagnostic.launch_allowed: true`；`:83-85` 评估入口 `evaluations/fm_eval/run.py`；`:136-137` `praxist_plugins.evaluations`；`roles/peer_generalist/role.yaml:18` `evaluation_tools.peer`。活 harvest **不读** `evaluation_summary.json`，所以违禁评估不会写进 verdict | 无「do NOT run TimesFM」断言；`test_praxist_task_contract.py` 仍锁旧 diagnostic 契约 | **部分对齐** | HIGH |

**点名缺口只有一条真正的合同未执行：schema 校验。** family 缺失拒绝见下表，不在这 8 项里。peer 不评估没有能力面闸门，但是活收割路径已经不吃诊断产物，所以判部分对齐而不是「收割写反」。

---

## 1. 有效 / 失效判定（本任务自写，不等 Task 1）

| 文件 | 判定 | 理由 |
|------|------|------|
| `docs/spec_hypothesis_driven_fast_loop_20260908.md` | **仍有效**（绑定快环合同） | 状态「已实施」；`loop-constraints.md:47-49` 把方案 A 写进预注册契约。2026-09-09 增补（tier 选座、近失误复测、atexit 仅 main 武装）是同一合同的补丁，不是取代 |
| `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` | **部分有效** | 三环职责、慢环唯一写、daily 缓存、429 resume、phase 互斥、goal DSL **仍约束代码**。peer「diagnostic 筛选 / 诊断幸存者入队」被方案 A 废止 |

失效的唯一合法理由是后续更高权威明确废止。状态栏「待审阅」和日期早，不够。

---

## 2. 方案 A 条款表

### 2.1 对齐

| 条款 | spec | 代码 / 测试 | 判定 |
|------|------|-------------|------|
| 慢环是唯一验证器；诊断 PF 不作数 | `:37`、`:65` | `_harvest_rows` 不读 EV/诊断；慢环 `aligned_slow_loop.py` 跑 n=350–600 | 对齐 |
| 不改 `.praxist-venv` 冻结框架 | `:41` | 本方案改动在 `scripts/` / `task_FM/` / `cascade/features.py` | 对齐 |
| 不改硬门逻辑 | `:44` | `evaluator.gate()` 仍 n≥350 且 `ic=2×\|dir_acc−0.5\|≥0.05` | 对齐 |
| peer 不改 `features.py` / `evaluator.py` | `:45`、`:180` | `task.yaml:104` `writable_roots: [results]`；新 cov 进 backlog | 对齐 |
| `covariate_pool.json` schema v1 + status/family/mechanism | `:78-93` | `task_FM/config/covariate_pool.json:1-5`；`test_pool_schema` | 对齐 |
| AST 并集后对 archived 做差集；缺池 fail-open | `:135-138` | `evaluator.py:69-70,103-108,109-113` | 对齐 |
| `validate_candidate` 拒绝归档并给 reason | `:137` | `evaluator.py:138-139`；`test_archived_candidate_rejected` | 对齐 |
| `load_covariate_pool` / `harvest_proposals` | `:141-142` | `praxist_supervisor.py:499-506,565` | 对齐 |
| glob `proposals/*.json` | `:143` | `:596` | 对齐 |
| 拒绝非法 symbol / 非 active cov / mechanism 空或 <40 | `:144` | `:616-623`；`test_illegal_symbol_rejected` / `test_unknown_cov_rejected` / `test_short_mechanism_rejected` | 对齐 |
| 去重 dead / passing / in-flight / seen | `:145` | `:625-626`；`test_dead_dedup`。`passing_ids` 走 `pass_variants`（还要 `ev>0`） | 对齐 |
| 排序：族多样性 → 履历 → 完备度 → 新颖性；后增 1 星 tier | `:146`、增补 `:8` | `_proposal_priority_score:520-536`；两遍 family QD `:650-667`；tier `:630-642`；`test_family_diversity_pass_one` / `test_priority_symbols_tiered_seat_fill` | 对齐 |
| new_cov → `covariate_backlog.jsonl`，不入队 | `:113`、`:148` | `:605-610`、`_append_backlog:538`；`test_new_covariate_goes_to_backlog` / `test_new_covariate_dedup_across_harvests` | 对齐 |
| `_harvest_rows` 改调 `harvest_proposals`；`harvest_survivors` 留体 | `:149`、`:221` | `:1289` vs `:419`。生产调用点零 | 对齐 |
| `materialize_covariate_menu` | `:150` | `:673`；主循环 `:1432` 与慢环抽干 `:1362` | 对齐 |
| 入队行 `source:peer_proposal` + cadence `max_points` | `:116-117` | `:647`；`queue_enqueue` 原样落盘；`test_good_proposal_enqueued` | 对齐 |
| 提示词：首动作写 ≥2 假设；include 菜单；禁跑 fm_eval | `:153-163` | `prompt_base.jinja2:5-57`；`skill.md`；`prompt_generation.jinja2:12-25` | 对齐 |
| `synthesis_trigger.min_findings=4` | `:168` | `task.yaml:113` | 对齐 |
| combo 补 rsi6/12/24、gated_slope、regime_gated、basis_momentum | `:171-173` | `features.py:1489,1638,1669,1688,1720-1727`；HEAD `9653264` | 对齐 |
| 单路径未知 cov `raise ValueError`（不再静默 CCL） | `:174` | `features.py:1395-1400`；`tests/test_combo_parity.py` | 对齐 |
| 测试三文件 | `:129-131` | `test_covariate_pool.py` / `test_harvest_proposals.py` / `test_combo_parity.py` 均在 | 对齐 |
| 活 cadence `survivors_per_cycle=3`、`aligned_max_points=600` | 增补 / goal | `scripts/praxist_goal.yaml:21-22`；`_harvest_rows` 读 cadence | 对齐（活路径） |
| n-不足近失误复测 | 增补 `:9` | `plan_sample_retests` / `_maybe_enqueue_retests`；条件含 `ev>0`（`:847` 一带，亏钱的 `i_oi` 不会当欠样本复测） | 对齐 |
| signal/atexit 仅 `main()` 武装 | 增补 `:12` | `_arm_handlers:167-174`；模块顶注释 `:162-164` | 对齐 |
| 菜单含 symbol sample ceiling | 增补 `:10` | `materialize_covariate_menu:711-716` | 对齐 |

### 2.2 部分对齐

| 条款 | spec | 事实 | 判定 | 严重度 |
|------|------|------|------|--------|
| peers 禁止评估 / 禁止加载 TimesFM | `:37`、`:155` | 提示词对齐；`task.yaml` / `role.yaml` 仍挂评估入口。活 harvest 不消费诊断，所以不会把小样本 PF 写进 registry | 部分对齐 | HIGH |
| mechanism「禁模板」 | `:103`、`:227` | 只做长度；菜单复读满 40 字能过 | 部分对齐 | LOW |
| `symbol_fit` / kill / promote 必填 | `:104-107` | 提示词必填；harvest **不拒绝**缺失，只在 `_proposal_priority_score` 各 +1 | 部分对齐 | MEDIUM |
| 合格未入队结转 pending-proposals 索引 | `:147` | **同文件增补 `:11` 自认未做**；每 cycle 重扫全部 `run_*`，dead/in-flight 去重防重复入队。未入选提案下 cycle 仍可占座 | 部分对齐 | LOW |
| diagnostic 降级为仅宿主冒烟 | `:167` | `diagnostic.launch_allowed: true` 仍在；peer `evaluation_tools` 仍在。宿主冒烟入口本身合理，缺的是 peer 侧关掉 | 部分对齐 | HIGH（与「禁止评估」同一洞） |
| `_harvest_rows` 缺 cadence 时默认 | 活合同 3 / 600 | `praxist_supervisor.py:1291-1292` `survivors_per_cycle` 默认 **2**、`aligned_max_points` 默认 **400**。活 `praxist_goal.yaml` 有 3/600，测试夹具常用 2/400 | 部分对齐 | LOW |
| 429 期间是否 harvest | 方案 A 未禁止 | 代码有意 harvest（`:1299-1300`、`:1527-1529`）。控制面 `:191` 后合同允许。runbook L82/L123 仍写「paused_429 不 harvest」——那是文档债，交 Task 5，不记本任务缺口 | 部分对齐（代码与后合同；runbook 落后） | — |
| 过硬门但亏钱仍可再提议 | 去重用 `pass_variants` | `i_oi` / `m_ccl`：`gate_pass=True` 且 `ev<0`，既非 passing 也非 dead，harvest 可再入队；materializer 却写 already solved。硬门不含 EV 是权威链事实（Task 1/2），不是方案 A 写反 | 部分对齐 | MEDIUM（误导 peer，不改信号） |

### 2.3 缺口（有效设计，代码没有或写反）

| ID | 条款 | spec | 代码 | 严重度 | 修复建议（不落地） |
|----|------|------|------|--------|-------------------|
| G1 | schema 不符即拒绝 | 方案 A `:144`「拒绝：schema 不符」；`:97` `fm.hypothesis_proposal.v1` | `harvest_proposals:603-623` 无 `p.get("schema")` 分支。仓内无此符号 | **HIGH** | `_reject("schema_mismatch")` 除非 `== "fm.hypothesis_proposal.v1"`；补测试。Critical 门槛未到：收割源仍是 proposals，不是诊断 PF |
| G2 | family 缺 → reject | 方案 A `:144`「family 缺」 | `:628` `(pool.family) or p.covariate_family or "other"`，缺则归 `other` 继续入队 | **MEDIUM** | 池与提案都无 family 时 `_reject("family_missing")`。池里 active 项目前都有 family，活风险低 |

Critical：0。没有「活路径按诊断幸存者收割」或「监督环写 verdict」。

### 2.4 方案 A 自己废掉的句子（失效，不当缺口）

| 条款 | spec | 杀手 | 判定 |
|------|------|------|------|
| glob「仅本 run」 | 方案 A `:143` | **同文件增补 `:11`**：pending-proposals 未做，下一 cycle **重扫** `proposals/`；实现 `:593-594` 扫全部 `run_*` | **失效** |

---

## 3. 09-02 仍有效骨架

骨架没被方案 A 废掉。方案 A 明确「不改动慢环 / 不改硬门 / 监督环加 harvest_proposals」。下列仍要对齐。

| 条款 | spec | 代码 / 测试 | 判定 |
|------|------|-------------|------|
| aligned 放代窗外慢环 | `:24`、`:41-43` | `aligned_slow_loop.py` 独立进程，0 token | 对齐 |
| 硬门维持 n≥350（相对放宽到 120） | `:25` | `evaluator.gate(..., min_n=350)`；`STAGE_POINTS["aligned"]=(350,600)` | 对齐 |
| daily 推理按 (symbol, cutoff) 缓存，与 cov 无关 | `:26`、`:68-69` | `_daily_predict_cached`；`DailyModel.predict` 无 cov 参数 | 对齐 |
| 监督环纯 Python、0 token | `:27`、`:105` | `praxist_supervisor.py` 不调 LLM，只起 praxist / 慢环子进程 | 对齐 |
| goal.yaml 可测量条件 | `:28`、`:119-124` | `scripts/praxist_goal.yaml` | 对齐 |
| 三环失败域互不传染 | `:32-43` | 快环 token / 慢环 CPU / 监督文件总线 | 对齐 |
| harvest 非空 → `phase=slow`，禁止下一轮快环 | `:54`、`:112` | `_maybe_harvest:1315`；`decide_fast_loop:1151` | 对齐 |
| harvest 空 → cycle+1，可再开快环 | `:55` | `_maybe_harvest:1321-1331`；`test_harvest_empty_counts_cycle_and_allows_start` | 对齐 |
| 缓存目录 `data/cache/daily_pred/` | `:77` | `aligned_slow_loop.py:144` 默认该路径 | 对齐 |
| A/B 逐位一致才算缓存正确 | `:75-76`、`:161-162` | `test_daily_pred_cache.py::test_ab_bitexact`（`@pytest.mark.slow`） | 对齐 |
| 慢环：取队 / checkpoint / flock / SIGTERM 续跑 | `:81-90` | claim/inprogress/ack + `queue_recover`（绑定解释改写「重写剩余行」，仍有效）；`fcntl.flock` `:147-153`；异常不 ack、不写死亡行 `:172-175` | 对齐 |
| checkpoint 键 (symbol, idx) | `:86-87` | `aligned_slow_loop.py:66` | 对齐 |
| verdict schema `fm.aligned_verdict.v1`，append-only，最新行准 | `:93-99` | `_no_data_verdict` / `run_aligned_candidate` 写 schema；`load_snapshot` 按 vid 覆盖 | 对齐 |
| 写权限仅慢环 flock 持有者；红线进 loop-constraints | `:96-98` | `loop-constraints.md:18-20`；生产 `append_verdict` 仅慢环 | 对齐 |
| Known verdicts 进提示词 | `:100-101` | `prompt_base.jinja2:65-72` include `known_verdicts.inc.md` | 对齐 |
| 配额不足只挡快环；慢环继续抽干 | `:113` | `ensure_phase` 文档：wait_quota/paused_429 **不**挡已入队慢环；`main:1536-1541` | 对齐 |
| 决策日志 append-only | `:114-115` | `.omc/supervisor_decisions.jsonl`；`_log_decision` | 对齐 |
| DSL 白名单 ast，禁任意调用 | `:135-136` | `evaluate_goal` 安全求值；`tests/test_goal_dsl.py` | 对齐 |
| 不改 praxist 核心 / 不自动改 goal.yaml | `:187`、`:190` | 仍成立 | 对齐 |
| `--dry-run` 只打印不执行 | 绑定解释 #7 | `decide_fast_loop(..., dry_run=True)`；`main --dry-run` | 对齐 |
| 同提供商 429：stop → 解封 resume 同一 `run_dir` | `:148`、绑定解释 #2 | `test_429_stop_then_resume` 等 | 对齐（主路径） |

### 3.1 骨架部分对齐（仍有效，实现有偏差）

| 条款 | spec | 事实 | 判定 | 严重度 |
|------|------|------|------|--------|
| 缓存键明文 `symbol\|cutoff\|WIN\|fp[:12]` | `:72-73` | 逻辑字段齐；外加 `v2` 前缀后 sha256 当文件名。绑定解释 #5 要求 (path,size,mtime) 变化即重算——`.model_fp.json` 的 `sig` 做到了 | 部分对齐 | LOW |
| 指纹 = 权重文件 sha256 前 12 位 | `:73` | 各 shard `read(1<<24)` 再哈希（`monthly_backtest.py:94-98`），不是整文件 | 部分对齐 | LOW |
| 429 禁止开新 run | `:148`；`praxist.md:80` | 主路径 resume；failover 身份墙 FRESH start（Praxist 不允许 claude→qwen）。测试把开新 run 锁成合法 | 部分对齐 | MEDIUM |
| `families_hit` = 协变量族集 | `:132` | `build_snapshot:411` 用 `cov_override` 当族名，与 QD family 不是同一概念 | 部分对齐 | LOW |
| `gate_pass=true` 不再重试 / false 即死亡 | `:101` | 未区分「过 n+ic 但 ev<0」。materializer `:484-485` 把 `i_oi`/`m_ccl` 写成 already solved | 部分对齐 | MEDIUM |
| 唯一写者测试锁 | `:159` | 慢环写入有测；「别人不写」无测。`restore-verdicts` 默认 dest 是生产 jsonl | 部分对齐 | LOW |

09-02 仍有效骨架 **没有缺口**（没有「代码缺了骨架要求的机制」）。偏差都落在部分对齐。

---

## 4. 09-02 失效条款（列杀手，判定=失效，不评代码对错）

这些句子曾经是 09-02 的收割合同。方案 A / loop-constraints / 控制面已经废止。`harvest_survivors` 函数体按方案 A `:221` 是回滚面，**残留 ≠ 缺口**。

| # | 失效条款 | 位置 | 杀手（文件:行） | 判定 |
|---|---------|------|-----------------|------|
| X1 | 快环 =「PI + 4 角色 peers + **diagnostic 筛选**」 | 09-02 `:38` | `loop-constraints.md:49`「peers 不再跑任何评估/加载 TimesFM」；方案 A `:37` | **失效** |
| X2 | 快环产出 =「**诊断幸存者** → pending 队列」 | 09-02 `:39` | 方案 A `:57-62` 新契约是 `proposals/*.json` → `harvest_proposals` | **失效** |
| X3 | 数据流：`run_summary + frontier 幸存者` | 09-02 `:51` | 方案 A `:58` glob proposals；活路径 `_harvest_rows:1289` | **失效** |
| X4 | 「run 结束且非 429 pause → **收割幸存者**入队」里的幸存者身份 | 09-02 `:110-111`、`:125` | 方案 A `:142-149`；`praxist.md:81` `harvest_proposals` | **失效** |
| X5 | 「非 429 pause 才收割」这条门闩 | 09-02 `:110`、`:125` | **`praxist_control_plane.md:191`**「harvest 不再因 paused_429 跳过」；监督环 docstring `:1299-1300`、`:1527-1529`。方案 A 收割的是本地 JSON，不烧 LLM | **失效** |
| X6 | 验收：造 fake run 的 `run_summary/frontier` 验证收割 | 09-02 `:168-169` | 方案 A `:210-218` 验收改为造 `proposals/*.json`；现行测试是 `test_harvest_proposals.py` | **失效** |
| X7 | 实施计划绑定解释 #4：幸存者 = diagnostic + status=ok + ev>0；源 = `evaluation_summary.json` | `docs/superpowers/plans/2026-09-02-praxist-three-loop.md:37` | `loop-constraints.md:49`；方案 A `:142-149`。runbook L192 仍指向这份绑定解释——那是**文档指针有毒**（上一轮 Task 3 C1），不是代码缺口 | **失效** |
| X8 | 计划架构句「快环 = LLM 探索+诊断筛选，产幸存者」 | 同计划 `:7` | 方案 A `:37`；`praxist.md:65-67` | **失效** |
| X9 | Non-Goal「不修改 cascade/」作为永久红线 | 09-02 `:186` | 后合同豁免：compile-skip（`a8b0b6b` 等）与 hardening SPEC-004…013（`243693d`）已批改 `cascade/` | **失效** |
| X10 | 前序 `praxist_directive_design` 的「peers 执行 diagnostic 筛 → aligned 确认」 | 09-02 `:4` 引用；directive `:25` | **directive 自己的横幅 `:1-3`**（2026-09-09）：§3 证据阶梯与 peer 跑评估已被方案 A 取代 | **失效** |

不要对 X1–X10 报「代码没按诊断幸存者收割」。活代码不按它们做，是合同要求。

**残留能力面（不是缺口）：**

- `harvest_survivors` 仍在 `praxist_supervisor.py:419`，测试 `test_harvest_survivors` 仍绿。方案 A `:221` 要求留体以便回滚。注释和测试标明不走活路径。
- `evaluator.STAGE_POINTS["diagnostic"]` 仍在——方案 A 允许宿主冒烟。
- peer `evaluation_tools` / `diagnostic.launch_allowed` 是方案 A「禁止评估」的**部分对齐**，已在 G 区之外的 2.2 表；不要再当成 09-02 诊断收割缺口报一次。

---

## 5. 硬规则 × 测试（给 Task 8 / Task 10）

| 硬规则 | 活路径 | 锁现行合同的测试 |
|--------|--------|------------------|
| harvest = `harvest_proposals` | 是 | 有 |
| mechanism ≥40 | 是 | 有 `test_short_mechanism_rejected` |
| schema `fm.hypothesis_proposal.v1` | **否** | **无** |
| family 缺拒绝 | **否**（fallback `other`） | **无** |
| 禁模板 | 否 | 无 |
| peer 不跑 fm_eval | 提示词是；能力面否 | **无** |
| `survivors_per_cycle=3` | 活 goal 是 | 测试夹具多用 2；分层测的 `top_k=3` 是参数 |
| phase 互斥 | 是 | 有 |
| 慢环唯一写 aligned_verdicts | 是 | 部分（写入有；「别人不写」无） |
| 429 resume 同一 run | 同提供商是 | 有；failover 开新 run 也被测成合法 |
| 日线缓存键含 symbol/cutoff/窗口/指纹 | 逻辑是 | 有 `test_daily_pred_cache.py` |
| 429 期间仍 harvest | 是（后合同） | **无** |

`tests/test_praxist_task_contract.py` 锁的是方案 A 之前的可写区 / 必须有 diagnostic 档，**不**锁方案 A。执行者若按那份测试「修契约」会把可写区改回去。

---

## 6. Findings（有效合同范围内）

### Critical

无。活 harvest 不是诊断幸存者；监督环不写 registry；同提供商 429 会 resume 同一 run。

### HIGH

**H1. `harvest_proposals` 不校验 `schema=fm.hypothesis_proposal.v1`。**  
文件: `scripts/praxist_supervisor.py:603-623`  
Confidence: HIGH  
Issue: 方案 A `:144` 把 schema 不符列进拒绝清单；实现只看 symbol/cov/mechanism 长度。  
Fix: 拒绝非 `fm.hypothesis_proposal.v1`，计入 `reject_reasons`；`tests/test_harvest_proposals.py` 加 `schema_mismatch`。

**H2. peer「禁止评估」只写在提示词里，任务包仍暴露评估能力。**  
文件: `task_FM/task.yaml:54-55,83-85,136-137`；`task_FM/roles/peer_generalist/role.yaml:18`  
Confidence: HIGH（能力面存在）；Praxist 是否**自动**调度评估 = LOW（见开放问题）  
Issue: 7.7GiB 宿主上 peer 一旦走入口加载 TimesFM，会和慢环抢内存。方案 A「0 次模型加载」没有能力面闸门。活 harvest 不吃诊断，所以不会伪造 aligned verdict。  
Fix: `diagnostic.launch_allowed: false`；拿掉 peer 的 `evaluation_tools`；审计规则改为提案文件。不要为了满足这份缺口去改硬门或 SCHEMES。

### MEDIUM

**M1. family 缺失不拒绝。** `praxist_supervisor.py:628`。池内 active 目前都有 family。  
Fix: 双源皆空则 reject。

**M2. failover 身份墙开新 run，与「禁止开新 run」字面冲突。** `praxist_supervisor.py:320-329,1167-1171`。  
Fix: 合同补一句「failover 且 model id 不同 → 允许新 run_dir，不得在原 run 上改模型」；或主备改成同一 model id。

**M3. `gate_pass=True` 且 `ev<0` 的三态缺失**（`i_oi`、`m_ccl`）。权威链：`gate()` 不含 EV 是对的；错的是 materializer / 提示词把亏钱组合标成 already solved。不要把 EV 塞进 `evaluator.gate`。

### LOW

**L1.** 缓存键哈希 + `v2` 前缀 + 指纹只读 shard 前 16MiB。逻辑身份仍是 (symbol, cutoff, 窗口, 模型指纹)。  
**L2.** `_harvest_rows` 缺省 2/400 vs 活 goal 3/600。  
**L3.** mechanism 禁模板无实现。  
**L4.** `families_hit` 用 cov 名。  
**L5.** `restore-verdicts` 可写生产 jsonl（人工 CLI）。

---

## 7. 开放问题（低置信，不挡结论）

1. Praxist 0.5.0 是否会仅因 `praxist_plugins.evaluations: [task_evaluation:fm_eval]` 和 `diagnostic.launch_allowed: true` **自动**调度 `fm_eval/run.py`，还是必须 peer 主动调 `evaluation_tools`？未读 `.praxist-venv` 源码（红线）。若会自动调度，H2 应升 Critical。
2. 日线指纹截断 16MiB 在 TimesFM 200m 上碰撞概率可忽略，但与 spec 原文「整文件 sha256」不等价；未做两份不同权重共享前 16MiB 的反例。

---

## 8. 做得对的地方

- `_harvest_rows` 只调 `harvest_proposals`；`harvest_survivors` 留作回滚，注释和测试都标明诊断路径已退役。这是方案 A 的核心，活路径成立。
- 短 mechanism fail visibly（`reject_reasons`），有测试。
- phase=slow 时窗口够也不 start，有端到端 `--once` 测试。
- 同提供商 429：stop → 解封 resume 同一 `run_dir`，有测试。
- 慢环异常不写死亡 verdict、不 ack，队列可 recover。
- `pass_variants` 已要求 `ev>0`，目标 DSL 不会把 `i_oi` / `m_ccl` 算成功。
- combo 四条分派已在 HEAD `9653264` 补齐；未知 cov 显式 raise。
- 近失误复测走 `ev>0`，不会把亏钱组合当欠样本。

---

## 9. 不要做的事

- 不要为了满足已失效的 09-02 诊断收割，把 `_harvest_rows` 改回 `harvest_survivors`。
- 不要因为 runbook L82 写「paused_429 不 harvest」去改代码跳过收割——后合同（控制面 `:191`）明确允许。该改的是 runbook（Task 5）。
- 不要把 `evaluator.gate` 塞进 EV 来「修」i_oi：硬门不含 EV 是权威链。
- 不要删 `harvest_survivors` 函数体（方案 A 回滚设计）。

---

## 10. 状态

**DONE_WITH_CONCERNS**

| 路 | 数 |
|----|----|
| valid-aligned（对齐） | 46 |
| 部分对齐（有效，有偏差） | 14 |
| valid-gap（缺口） | 2（schema 校验、family 缺拒绝） |
| invalidated（失效） | 11（方案 A「仅本 run」1 + 09-02 诊断收割等 10） |

点名 8 项：`harvest_proposals` / `mechanism>=40` / 慢环唯一写 / phase 互斥 = 对齐；schema = 缺口；429 resume / 日线缓存键 / peers 不评估 = 部分对齐。
