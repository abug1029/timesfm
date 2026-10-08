# D1 行号腐烂专项审阅：全仓行号引用审计

> **日期**: 2026-10-08
> **触发**: 技术债清单 D1（`2026-10-07-tech-debt-inventory.md`）
> **代码基线**: `c814f11`
> **方法**: 全量正则扫描 4 种引用形态 → 逐条解析目标文件 → 打印被指行实际内容 → 人工判定语义是否相符
> **结论一句话**: 现行契约文档 30 处行号引用中 **25 处错误、1 处部分正确、仅 4 处正确（正确率 13%）**；D1 原述的"peer 提示词内嵌行号"**已不存在**（prompt 模板 0 处行号）；真正需要修的是 9 份常读契约文档，日期型报告与归档合计 1605 处属历史快照、不应修。

---

## 1. 审计覆盖范围（防漏查）

扫描模式共 4 类，避免只查 `xxx.py:NNN` 一种形态：

| 形态 | 示例 | 扫描位置 |
|---|---|---|
| ① 带文件名行号 | `evaluator.py:284`、`praxist_supervisor.py:1455-1471` | 全仓 `*.md` + `*.jinja2` |
| ② 裸行号（承接上文文件） | `` `:697` ``、`` `:293-332` `` | 全仓 `*.md` |
| ③ 报告/spec 行号 | `L30`、`L190–199` | 全仓 `*.md` |
| ④ 跨文档行号 | `three_loop_workflow.md:290` | 现行 `*.md` |

**扫描结果分布**：

| 区域 | 引用数 | 性质 | 处置 |
|---|---:|---|---|
| 现行契约文档（9 份，§2） | 30 | 常读、被引用当合同 | **逐条核验并修正** |
| `docs/superpowers/` 日期型（reports/plans/specs/changelogs/reviews） | 235 | 写作当日的证据快照 | 不改行号，改为绑定 commit（§5） |
| `docs/archive/` | 1370 | 归档冻结 | 不动 |
| peer prompt 模板（`prompt_base.jinja2` / `prompt_generation.jinja2` / `roles/peer_generalist/skill.md`） | **0** | — | D1 原述载体已消失 |

---

## 2. 现行契约文档逐条核验（30 条全量）

图例：✅ 正确 ｜ ⚠️ 部分正确 ｜ ❌ 错误

### 2.1 `docs/runtime_contract.md`

| 行 | 引用声称 | 被指行实际内容 | 判定 | 正确位置 |
|---:|---|---|:--:|---|
| 31 | `praxist_supervisor.py:144` 定义 `POLL_S = 300` | `EVENTS_PATH = os.path.join(...)` | ❌ | **:152** |
| 96 | `evaluator.py:697` `compute_effective_min()` | `_active_fields = {` | ❌ | **:761** |
| 125 | `evaluator.py:284` 指纹版本定义 | （空行） | ❌ | **:315** |
| 126 | `restart_readiness_check.py:70` 有 assert | `assert PROTOCOL_FINGERPRINT_VERSION == "protocol_v4"` | ✅ | :70 |
| 155 | `praxist_supervisor.py:1752` `_dead_families(...)` | （空行） | ❌ | **:1875** |
| 202 | `praxist_supervisor.py:1912` `_sector_filter_check()` | （空行） | ❌ | **:2190** |

### 2.2 `docs/evaluation.md`

| 行 | 引用声称 | 被指行实际内容 | 判定 | 正确位置 |
|---:|---|---|:--:|---|
| 36 | `evaluator.py:697` `compute_effective_min()` | `_active_fields = {` | ❌ | **:761** |
| 144 | `praxist_supervisor.py:1604` `_dead_families(snapshot, min_ok=4)` | `weak.sort()` | ❌ | **:1875** |
| 167 | `evaluator.py:284` 版本定义 | （空行） | ❌ | **:315** |
| 167 | `restart_readiness_check.py:70` assert | 同上 | ✅ | :70 |

### 2.3 `task_FM/AGENTS.md`（错误最密集，5 处裸行号**全错**）

| 行 | 引用声称 | 被指行实际内容 | 判定 | 正确位置 |
|---:|---|---|:--:|---|
| 99 | ``compute_effective_min（`:697`）`` | `_active_fields = {` | ❌ | **:761** |
| 110 | `evaluator.py:284` 指纹版本定义 | （空行） | ❌ | **:315** |
| 134 | `compute_protocol_fingerprint`（`:293`） | `return []` | ❌ | **:324** |
| 135 | `build_summary`（`:447`） | `if _WEIGHT_FINGERPRINT_CACHE[...]` | ❌ | **:478** |
| 136 | `compute_effective_min`（`:697`） | `_active_fields = {` | ❌ | **:761** |
| 137 | `gate`（`:703`） | `"n_nan": gm.get("n_nan", 0),` | ❌ | **:767** |
| 138 | `effective_sample_size`（`:720`） | `try:` | ❌ | **:784** |

> 注：该表已带函数名，行号纯属冗余——删掉行号即可自愈（§5 方案 A）。

### 2.4 其余现行文档

| 文档:行 | 引用声称 | 被指行实际内容 | 判定 | 正确位置 |
|---|---|---|:--:|---|
| `CLAUDE.md:68` | `evaluator.py:284` 指纹版本定义 | （空行） | ❌ | **:315** |
| `CLAUDE.md:68` | `restart_readiness_check.py:70` assert | assert 语句 | ✅ | :70 |
| `docs/handbook.md:125` | `evaluator.py:284` 协议指纹定义 | （空行） | ❌ | **:315** |
| `docs/glossary.md:68` | `horizon_fill.py:94` 缺 pool/词表外抛 `HorizonContractError` | `:94` 是词表外检查（raise 在 `:95`）；"缺 pool 条目"实际在 `:81` | ⚠️ | 拆为 **:81** 与 **:94-97** |
| `docs/run_artifacts.md:166` | `praxist_supervisor.py:2977` 归档调用在**裸 except** | `:2977` 在文档字符串内；真实归档调用在 **:3724-3729**，且现为 `except Exception as e:`（**非裸 except**） | ❌ | **:3724-3729**，并修正"裸 except"表述 |
| `docs/supervisor_restart_backlog.md:7` | `praxist_supervisor.py:745` `materialize_covariate_menu` | `def _arm_handlers():` | ❌ | **:2841** |
| `docs/supervisor_restart_backlog.md:88` | `praxist_supervisor.py:361` `_signal_handler` | （空行） | ❌ | **:689** |
| `docs/supervisor_restart_backlog.md:90` | 主循环顶读标志（`:2858`） | `lines.append("- %s: %s%s" ...)`（菜单渲染，无关） | ❌ | **:2665 / :2671** |
| `docs/supervisor_restart_backlog.md:92` | `POLL_S = 300`（`:117`） | （无关） | ❌ | **:152** |
| `docs/supervisor_restart_backlog.md:114` | `praxist_supervisor.py:749` track 行加前缀 | `signal.signal(signal.SIGTERM, ...)` | ❌ | 描述需重写（track 行在 `materialize_covariate_menu` `:2841` 内） |
| `STATE.md:228` | `features.py:1047-1048` `_generate_rsi_state_horizon` | `for i in range(context_len):` | ❌ | 调用点 **:1052**（定义 `:389`） |
| `STATE.md:229` | `features.py:1227` `np.full(horizon, last_valid)` | `hourly_closes = df_1h["close_price"]...` | ❌ | **:1231** |
| `STATE.md:255` | `data_validator.py:562-581` `detect_trading_hours` | `def detect_trading_hours(...)` 起始行 | ✅ | :562-581 |

**统计：30 条 = ✅4 + ⚠️1 + ❌25。**

---

## 3. 同一事实的跨文档自相矛盾（D1 最危险的形态）

同一处代码，两份现行契约各写各的行号，**且都错**：

| 事实 | `docs/evaluation.md` | `docs/runtime_contract.md` | `docs/supervisor_restart_backlog.md` | 实际 |
|---|:--:|:--:|:--:|:--:|
| `_dead_families` 定义 | :1604 | :1752 | — | **:1875** |
| `POLL_S = 300` | — | :144 | :117 | **:152** |
| `PROTOCOL_FINGERPRINT_VERSION` 定义 | :284 | :284 | — | **:315** |

三处漂移量不一（+64 / +113~143 / +31），说明它们是在不同时期、按当时代码各自抄录后再各自漂移——**没有任何单一真相源**。读者对照两份文档会得到两个"权威"数字。

---

## 4. 其他发现

### 4.1 D1 原述载体已不存在
`task_FM/prompt_base.jinja2`、`task_FM/prompt_generation.jinja2`、`roles/peer_generalist/skill.md` 扫描结果 **0 处行号引用**。清单原话"peer 提示词内嵌规格行号"在当前模板不成立（D1 的主诉已消失，残留问题集中在人类读的契约文档）。

### 4.2 技术债清单自身即案例
`2026-10-07-tech-debt-inventory.md:29` 引 `test_supervisor.py:1663/1678`；10-08 的 `38df4ac`（P1 收口）插入测试后，真实位置变为 `test_dead_families_identified` **:1668** / 断言 **:1687**（另有 :1432 / :1467）。**清单写完 24 小时内行号即腐烂**，实证 D1 的日腐烂速度。

### 4.3 执行中的收口计划已被自身修复内容推翻
`plans/2026-10-07-tech-debt-closure-plan.md` 仍在执行，但：
- `:17` 引 `_family_confirmatory_counts`（`praxist_supervisor.py:1736-1751`）→ 现为 **:1852**（`:1736` 现在是 covariate pool 加载）
- `:30` 引 `aligned_max_points` 默认（`:3399`）→ `38df4ac` 已把默认值收口到 `_CADENCE_DEFAULTS` **:790**，`:3399` 现为无关 JSON 输出

### 4.4 新 spec 的 40+ 处裸行号是下一个腐烂源
`specs/2026-10-08-open-issues-closure-spec.md` 抽查 3 处（`:4139` `start_new_session=True`、`:1148`/`:1167` tier 读取点、`:696` 退出标志）**全部正确**——因其按 `c814f11` 现写。但该 spec 自身在 `:32-34` 已声明"与 D1 表面矛盾"并选择继续用行号；批次执行中每合入一笔即腐烂一次（同 §4.2）。

### 4.5 跨文档引用指向已移动/不存在的文件
- `docs/2026-09-30-dead-code-purge-spec.md:162` → `docs/three_loop_workflow.md:290`：文件已移至 `docs/archive/`，路径失效（内容仍可按归档路径找到）。
- 日期型 spec 中引用已按设计删除的死代码行（如 `features.py:1118`）属预期，不计为错误。

---

## 5. 处置建议

### A. 现行契约文档（9 份 / 30 处）：删除行号，改符号引用 —— 立即
行号是**冗余信息**：§2.3 的接口表已带函数名，删掉 `:NN` 即完全自愈。规则：
- 行内**只写符号**：`compute_effective_min()`（不写行号）
- 必须定位时写 `file.py:symbol_name`，由脚本解析行号
- 涉及常量/配置段落时改**章节锚点**（`runtime_contract.md` 内部互引一律用 `#标题锚点`）
- §2 表中 25 处 ❌ 有两条路：① 直接删行号（推荐，零维护）；② 按"正确位置"列更新（3 天内会再次腐烂，不推荐）

### B. 加防回归检查 —— 与 A 同批
新增 `scripts/check_line_refs.py`（可挂 `tests/test_no_dead_code.py` 同级常备套件）：
1. 扫描白名单文档（§2 的 9 份 + prompt 模板）中所有 `file.py:NN` 与 `` `:NN` ``；
2. 解析目标行 ±2 行，断言包含引用上下文声称的符号名（如 `_dead_families`、`POLL_S`）；
3. 不匹配即报错，错误信息给出当前真实行号。
这样"腐烂"从**静默**变为**测试红**，是唯一能阻止复发的机制。

### C. 日期型报告/changelog/plans（235 处）：不改行号，绑定 commit
这些是"写作当日的证据"，改行号等于篡改历史证据。约定：
- 报告头部已有"代码基线"字段的（如 `master@5e7237a`）保留并强制化；
- 无基线的报告补 `git rev-parse --short HEAD`；
- 引用格式 `file.py:NN @ <commit>`，读者自行 `git show <commit>:file | sed -n 'NNp'`。
- **归档（1370 处）完全不动。**

### D. 进行中的 spec/plans（§4.3/§4.4）：执行完即转状态
- `2026-10-07-tech-debt-closure-plan.md` 的勘误表引用在批次 2 完成后应随"勘误回写"一并更新为符号引用；
- `2026-10-08-open-issues-closure-spec.md` 结案时，把其中 `:NNNN` 全部替换为符号或直接随 spec 归档，避免长期挂在 living 目录里继续被引用。

---

## 6. 边界与说明

- 本审计为**只读**，未修改任何文件；§2 的"正确位置"以 `c814f11` 为准，下次合入后需重新解析（这正是建议 A/B 的理由）。
- 工作区当时有 35 个 `D` 状态的 gitignored 数据资产（WSL 副本无磁盘文件）与 1 个未跟踪新 spec；与本审计无关，仅作留痕。
- 235 处日期型引用**未逐条核验**（按 §5-C 改为绑定 commit 后无需核验）；如需对其也做逐条核验，可复用本次扫描模式扩展。

---

**审计者**: Claude Code（D1 专项）
**方法留痕**: 4 类正则全量扫描 → 30 条现行引用逐条打印被指行内容人工判定 → 反向定位真实符号行号
**关联**: `docs/superpowers/reports/2026-10-07-tech-debt-inventory.md`（D1 条目）、`docs/superpowers/plans/2026-10-07-tech-debt-closure-plan.md`（批次 3 D1 章节锚点方案）

---

## 执行记录（2026-10-08，建议 A-C 已落地）

| 建议 | 执行内容 | 结果 |
|---|---|---|
| **A** 现行契约文档去行号 | 9 份文档 29 处改为符号/文件引用（含 `run_artifacts.md` "裸 except" 失真表述一并修正） | 复扫三类模式（`xxx.py:NN` / 裸 `` `:NN` `` / `xxx.md:NN`）**清零** |
| **B** 防回归闸门 | `scripts/check_line_refs.py`（living 禁行号 + dated 必须有基线，双硬失败）+ 常备测试 `tests/test_doc_line_refs.py` | 44 份 living 全过；违规时退出码 1 |
| **C** 历史证据钉 commit | 32 份含行号的日期型文档注入 `> **代码基线**: <sha>` 头（`git log -1` 取 sha；未入库文件用 HEAD 并标注） | 79 份 dated 中 35 份声明基线，其余无行号引用无需声明 |
| 纪律固化 | `docs/AGENTS.md` 新增「行号引用纪律」章节 | 与闸门互为表里 |

**范围边界**：归档区 `docs/archive/`（1370 处）未动；日期型文档行号一律未改（只加基线头）。
