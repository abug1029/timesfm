# Audit: Backfill 审核修复计划

| 项 | 内容 |
|---|---|
| 对象 | `plans/2026-10-19-backfill-audit-fix-plan.md` |
| 对照 | `cascade/typesafe_prescreen.py`、`scripts/backfill_prescreen.py`、`tests/test_typesafe_prescreen.py`、changelog/503 报告、prior `reviews/2026-10-19-laya-backfill-execution-503-audit.md` |
| 审核时间 | 2026-10-19 15:40 CST（Asia/Shanghai） |
| 方法 | 全文读计划 → MRO 实证 ReadTimeout↛TimeoutError → 逐 Task 对行号/返回值/import 作用域 → 对照 prior P1/P2 覆盖 |
| **结论** | **有条件通过** |

---

## §1 一句话

方向对、覆盖 prior 全部 P1/P2；但 **Phase 1.1 粘贴「修复后」片段有两处 P0**（缺模块级 `requests` import + 错误返回形状），按原文开写会让熔断仍不触发或破坏 `_fallback_result` 契约——改片段后再进 Phase 1。

---

## §2 范围与完成度（对照 prior P1/P2）

| Prior 项 | 本计划 | 判定 |
|----------|--------|------|
| P1 代码：`ReadTimeout` 未进 `_record_timeout`/熔断 | Phase 1.1 加 `requests.exceptions.Timeout` | **意图正确**；片段有 P0（见 §4） |
| P1 文档：changelog「JSON=54」「374×503」 | Phase 1.2 删 374、换 §2.3 拆解表、改待办 | **覆盖**；changelog 实存对应段落 |
| P2 完成行缺 `skipped=` | Phase 2.1 | **覆盖**（实为 L607，非 ~580；已有 `degraded=`） |
| P2 `_strip_chinese` 入口防御 | Phase 2.2 | **覆盖**（双保险；HEAD 调用侧已 `str(... or "")`） |
| P2 缺 symbol/空文件独立计数 | Phase 2.3 | **半覆盖**：目标对，行号错、未改 `Stats`/`snapshot`/state 初值 |
| P2 HTTP 5xx/429 退避 | Phase 2.4 | **意图对，片段死代码**（`raise_for_status` 在前） |
| P2 TypeError 日志带 path | Phase 2.5 | **半覆盖**：文件/函数名写错；`process_proposal` 已有 path，真缺口在 `typesafe_prescreen.prescreen_proposal` |
| P2 503 报告 JSON 44→43 + 同名 run 注 | Phase 2.6 | **覆盖** |
| 单测 ReadTimeout→熔断 | Phase 3.1 | **覆盖**；现有测只用 builtin `TimeoutError` |
| 重跑失败子集 | Phase 3.2 | **弱**：`--force` 清空全部 processed，非「仅 failed/degraded」；「107」沿用错误汇总 |

与 leak-fix SPEC：不扩 `PrescreenStatus`；超时仍走 `degraded` + `_fallback_result`——**无冲突**（前提是不把返回值改成 plan 里的裸 dict）。

---

## §3 与代码 / API 可行性（证据）

### 3.1 MRO（本机 Python / requests 2.25.1）

- `issubclass(requests.exceptions.ReadTimeout, TimeoutError)` → **False**
- `issubclass(ReadTimeout, requests.exceptions.Timeout)` → **True**
- 因此 except 元组加 `requests.exceptions.Timeout` **正确**；只靠 builtin `TimeoutError` **不够**。

### 3.2 现码锚点

| Plan 声称 | 实际 | 备注 |
|-----------|------|------|
| `_prescreen_impl` ~417–426 | L417–424：`except (TimeoutError, TypeSafeTimeoutError)` → `_record_timeout` + `_fallback_result(..., note="Laya API 超时")`；泛 Exception → error | 「现有/修复后」返回 `{"status","error"}` **与现网不符** |
| `_call_laya` + `raise_for_status` | L329–380；`import requests` **仅函数内局部** | `_prescreen_impl` 作用域内 **无** 模块级 `requests` |
| `_strip_chinese` ~50 | **L41** | 行号偏差 |
| 完成行 ~580 | **L607–609**；已有 degraded，缺 skipped | |
| 缺 symbol ~300 / 空文件 ~280 | 均在 `extract_proposal_fields` **L180–187** → `None`；`process_proposal` **L323–325** `stats.inc("failed")` | 无独立「空文件」分支 |
| `prescreen_proposal` in backfill | backfill 只有 **`process_proposal`**（L405 已 `logging.error(... proposal_path ...)`） | TypeError 多在 `typesafe_prescreen.prescreen_proposal` L461–465 被吞成 fallback |
| `tests/test_backfill_prescreen.py` | **不存在** | 可新建；`test_typesafe_prescreen.py` 已有 circuit 测但只抛 `TimeoutError` |
| HEAD `raw_pd = str(... or "")` | L300 已在 | Phase 2.2 为纵深防御，合理 |

### 3.3 Phase 1.1 按原文粘贴的失败模式

1. **`requests` 未导入**：`except (..., requests.exceptions.Timeout)` 匹配时 `NameError` → 原 ReadTimeout 处理失败 → 外层仍走 error，**`_record_timeout` 仍不调用**。
2. **返回裸 dict**：下游期望 `_fallback_result` 字段（`skip_suggested`/`note`/`ts` 等），裸 `{"status","error"}` 破坏契约。

### 3.4 Phase 2.4 片段

```text
response.raise_for_status()   # 4xx/5xx 已抛
if response.status_code in (429, 500, ...):  # 不可达
```

且把耗尽重试改抛 `TypeSafeTimeoutError` 会 **误计入超时熔断**（HTTP 与超时混桶）——设计需拆开。

### 3.5 Phase 3.2

`--force` 清空 `processed_set` 后按扫描序重跑至 `--max 200`，**不能保证**打到 failed/degraded 子集；「107」= 错误 changelog 汇总（应 ~54 failed ± 45 degraded，或明确路径列表）。

---

## §4 P0 / P1 / P2 清单

### P0（开写 Phase 1 前必须改计划）

1. **Phase 1.1 片段**：明确模块级（或函数级事前）`from requests.exceptions import Timeout as RequestsTimeout`（或等价），**禁止**依赖 `_call_laya` 局部 `import requests`。
2. **Phase 1.1 返回值**：超时分支必须保持现有 `_fallback_result(proposal, symbol, status="degraded", note="Laya API 超时")` + `logger.warning`，**禁止**换成裸 `{"status":"degraded","error":...}`。

### P1（强烈建议改计划后再做）

1. **Phase 2.4**：退避必须在 `raise_for_status` **之前**循环；5xx/429 耗尽应走 HTTPError/专用错误，**不要**默认 `TypeSafeTimeoutError` 以免污染 `_consecutive_timeouts`。
2. **Phase 2.3**：补 `Stats.invalid_input`、`snapshot`、state 初值/`完成`/`进度` 行；行号改为 `extract_proposal_fields` / `process_proposal` L323。
3. **Phase 2.5**：目标改为 `cascade/typesafe_prescreen.py::prescreen_proposal`（日志含 `proposal.get("proposal_id")`），或在 `process_proposal` 对 `status!="success"` 打 `result["note"]` + path；删错误函数名。
4. **Phase 3.2**：用失败路径列表 / 过滤 processed，勿把「107」当选集；勿假设 `--force --max 200` = 失败子集。

### P2

1. Phase 1.2：同步改掉章节标题「107 个真正失败」（表换了标题还在会误导）。
2. Phase 2.1：行号改为 ~607；注明 degraded 已存在只补 skipped。
3. Phase 2.2：行号 ~41；可注明与 L300 `str()` 的职责分层。
4. 现有 `test_api_timeout_returns_degraded` 应增补 **ReadTimeout** 用例（plan 已写，落实时勿只 mock builtin）。
5. Changelog「12 个未修 JSON」vs 503 报告「7」仍不一致——1.2/2.6 对齐时一并选一数字并注明来源。

---

## §5 结论与放行条件

**有条件通过** — 计划正确承接 prior 审核的 P1（熔断 + 文档）与 P2 清单，异常类型选择（`requests.exceptions.Timeout`）经 MRO 验证成立，且不与 leak-fix SPEC 的 status 冻结冲突。

**放行条件（全部满足后再开 Phase 1 编码）**：

1. 修订 Phase 1.1：模块级 Timeout import + 保留 `_fallback_result` 返回；
2. 修订 Phase 2.4 伪代码（或降级为「另开任务，禁止按现片段合并」）；
3. 修正 Phase 2.3/2.5 锚点与 Stats 字段说明；
4. Phase 1 合并并通过 **ReadTimeout→`_consecutive_timeouts`→3 次短路** 单测后，才允许大规模重试/全量（与 prior 审核条件一致）。

非阻塞：Phase 3.3 生产侧门禁、行号注释精度、changelog「12 vs 7」数字对齐。
