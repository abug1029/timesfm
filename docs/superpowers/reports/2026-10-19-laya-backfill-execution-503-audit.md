# Audit: Backfill 执行 Changelog + 503 错误分析

| 项 | 内容 |
|---|---|
| 对象 | `changelogs/2026-10-19-laya-backfill-prescreen-execution.md` + `reports/2026-10-19-laya-503-error-analysis.md` |
| 对照 | `scripts/backfill_prescreen.py`、`cascade/typesafe_prescreen.py`、`scripts/aligned_slow_loop.py`、`logs/backfill_prescreen_20261019_032210.log`、`logs/backfill_retry_.log`、`D:\FlyBuddy\laya-decision-report-2026-10-19.md`、commits `770552e`/`7cf8517`/`fd41c60` |
| 审核时间 | 2026-10-19 15:28 CST（Asia/Shanghai） |
| 方法 | 全文读两文档 → 主/重试日志计数 → HEAD 代码路径核对 → 异常 MRO/熔断路径实证 → 提案字段抽样 |
| **结论** | **有条件通过** |

---

## §1 一句话

主数字（6645 / success=399 / failed=54 / enqueued=384 / degraded=45）与「无 HTTP 503」结论成立；changelog 仍残留「374×503 / failed=54 全是 JSON」误述；代码侧下一轮前应修 **ReadTimeout 未进熔断**（P1）。

---

## §2 Changelog 对照代码 / 日志

### 2.1 成立的部分

| 主张 | 实证 |
|------|------|
| Phase 3 完成 `total=6645 success=399 failed=54 enqueued=384 degraded=45 elapsed=4591s` | 主日志末行一致；4591s ≈ 76.5 min |
| skipped≈6147「消失」实为 REGISTRY 去重 | `6645−399−54−45=6147`；`process_proposal` 在 `existing` 命中时 `inc("skipped")` |
| 3 commits 修复点存在 | `770552e` 删循环内 `import registry_lib`；`7cf8517` `str(...)` + 进度 `skipped=`；`fd41c60` cov 多 schema + `pmi` |
| 慢环 UnboundLocalError 根因 | 局部 import shadow 顶层 `rl`，`queue_recover()` 在 import 前调用 — 与 diff 一致 |
| 错误率 0.81% | `54/6645≈0.813%` |

### 2.2 偏差 / 过时

| 问题 | 说明 | 严重度 |
|------|------|--------|
| **「JSON 解析错误 = 54」** | 主日志 `无法解析提案` **43**；failed=54 = **43 JSON + 8 TypeError + 1 ReadTimeout + 2 缺 symbol**。把整桶 failed 标成 JSON 是错误归因 | **P1（文档）** |
| **仍写「374 个 Laya 503」**（不做的事 / 待办） | 与同日 503 报告及 Laya 决策日志矛盾；主日志「503」命中实为 `elapsed=1503s` 伪阳性 + HTTPConnectionPool 超时栈，**非 HTTP 503** | **P1（文档）** |
| 剩余坏 JSON「12」vs 503 报告「7」 | 两文档不一致；主跑仅见 43 条解析 ERROR，未在本审核中复验 fix 工具产出 | P2 |
| 主跑进度行无 `skipped=` | 符合时间线：主跑 11:22–12:38，`7cf8517` 13:55 才合入；P0 修复有效但**未覆盖当次主跑日志** | 信息 |
| `完成:` 行仍无 `skipped` | HEAD `backfill_prescreen.py` 进度行有 skipped，收尾行仍省略 — 半吊子透明度 | P2 |
| success−enqueued=15 | `399−384=15`：`queue_enqueue` 返回空（已在 QUEUE/INPROGRESS/DEAD）未计 enqueued；changelog 未解释，非 bug | 信息 |

### 2.3 failed=54 正确拆解（应用此表替换 changelog「107 真正失败」表）

| 类型 | 数量 | 日志特征 | stats |
|------|------|----------|-------|
| JSON 解析失败 | 43 | `[ERROR] 无法解析提案` | failed |
| TypeError（PD 为 int） | 8 | `Laya 预筛未预期异常` → `_strip_chinese` | failed |
| ReadTimeout | 1 | `Laya API 调用失败: ... Read timed out` | failed |
| 缺 `symbol` | 2 | `[WARNING] 缺少 symbol 字段` | failed |
| W6.4 vid 不可得 | 45 | WARNING + 改写 prescreen 为 error | **degraded**（非 failed） |
| REGISTRY 跳过 | 6147 | （主跑进度行未打印 skipped） | skipped |

「107 真正失败」若含 degraded 则约 `54+45=99`，再加空文件叙事易胀到 ~108；建议废弃该汇总标签，改用上表。

---

## §3 503 报告对照代码 / 日志

### 3.1 根因结论：**成立**

- 主日志 / 重试日志：**HTTP 503 = 0**（无 `Service Unavailable` / `raise_for_status` 503）。
- Laya 决策报告：542 请求，200×539 + 客户端断开 2 + 400×1，**503×0**。
- P2 agent「374×503 / 29×连接错误」：**幻觉**，本审核同意。

### 3.2 分类核对

| 报告主张 | 日志/代码 | 判定 |
|----------|-----------|------|
| Laya 内部异常 8 = TypeError on int PD | 8× traceback：`_build_state` → `_strip_chinese` → `expected string or bytes-like`；磁盘上恰有 8 个非 str PD（均在 `run_2026-10-18_23-28-46`） | **成立**（basename 列表对；注意同名提案另有 str 副本） |
| JSON 44 | 主日志 **43** unique paths | **差 1**（P2） |
| W6.4 ×45 | 主/重试均 45 | **成立**；`fd41c60` 多 schema 提取在 HEAD |
| 已修 str() / 多 schema | HEAD 含 `str(proposal.get("predicted_direction") or "")` 与 priority 3/4 cov 提取 | **成立** |

### 3.3 报告未写但代码暴露的问题

1. **`requests.exceptions.ReadTimeout` 不继承 `TimeoutError`**  
   `_prescreen_impl` 只 `except (TimeoutError, TypeSafeTimeoutError)`，实际 ReadTimeout 落入泛 `Exception`：  
   - 记 `status=error`（非 degraded）  
   - **不调用 `_record_timeout()` → 连续超时熔断永不触发**  
   主跑实证：1 次 ReadTimeout 走「API 调用失败」栈，无「Laya API 超时」/「短路降级」日志。

2. **无 HTTP 状态分级重试**  
   `_call_laya`：`raise_for_status()` 后无 429/5xx backoff；503 若出现会与其它 HTTPError 一样变 `error`，无退避。

3. **语言/检查点质量（旁证，非 503）**  
   Laya 报告：多语言检查点 90 条中 80×`invalid`；客户端 60s 超时 vs 服务端排队+推理可逼近上限。与「无 503」并行的真实风险是 **超时 + 路由抖动**，不是服务不可用。

---

## §4 代码问题清单

### P0（挡下一轮全量）

*无。* str()/多 schema/慢环 import 已在 HEAD；主数字闭环。

### P1（强烈建议下一轮前修）

1. **`cascade/typesafe_prescreen.py` `_prescreen_impl`（~417–426）** — 捕获 `requests.exceptions.Timeout`（含 `ConnectTimeout`/`ReadTimeout`），走现有 `_record_timeout()` + `status=degraded` 路径；勿依赖 builtin `TimeoutError`。  
2. **Changelog 纠错** — 删除/改正「374×503」与「JSON=54」；采用 §2.3 拆解表；与 503 报告对齐剩余坏文件数量。

### P2（改进）

1. **`backfill_prescreen.py` 收尾行** — `完成:` 补 `skipped=` / `degraded=` 与进度行一致。  
2. **`_strip_chinese` 入口** — 防御：`if not isinstance(s, str): s = "" if s is None else str(s)`（双保险；`str(0 or "")` 会吞 `0`，方向字段虽罕见但建议 `None` 显式判断）。  
3. **缺 symbol / 空文件** — 单独计数器或 `stats.inc("invalid_input")`，避免与 Laya/API failed 混桶。  
4. **HTTP 5xx/429** — 有限次指数退避后再 error；熔断与超时共用。  
5. **TypeError 日志** — `prescreen_proposal` 外层 except 应带上 `proposal_id`/`path`，避免再靠猜 basename。  
6. **503 报告** — JSON 44→43；注明「同名提案多 run，int PD 仅 `run_2026-10-18_23-28-46` 下 8 份」。

---

## §5 后续优化建议（可执行）

1. **修 ReadTimeout→熔断路径（P1）**，单测：mock `requests.post` 抛 `ReadTimeout`，断言 `_consecutive_timeouts` 递增且 3 次后 `_circuit_until` 置位。  
2. **重跑失败子集**：`--force` 仅对 failed/degraded（或清空 processed 中失败项）；验证 TypeError→0、W6.4 degraded 下降。  
3. **Changelog 修订 PR**：去掉 374 叙事；failed 拆表；待办改为「监控超时/客户端断开/检查点切换」，非 503。  
4. **提案生产侧**：禁止 `predicted_direction` 非字符串；写盘前 `json.dumps` round-trip；中文引号 escape 门禁（从源头砍 JSON 43）。  
5. **Laya 侧/客户端**：固定英文检查点（或证实 `language` 字段生效）；客户端 timeout 与服务端 p99(queue+infer) 对齐（报告示排队中位 6.6s、换检查点可至 ~48s）。  
6. **观测**：进度/完成日志统一字段；可选把 `skipped/degraded/invalid_input/timeout` 写入 `backfill_prescreen_state.json` 便于看板。

---

## §6 结论

**有条件通过** — 执行 Changelog 的**主结果数字**与 503 报告的**「无 HTTP 503 / 374 为幻觉」**经日志与 Laya 决策报告交叉验证成立；三笔修复 commit 与 HEAD 一致。  
条件：

1. 修订 Changelog（去 374、改正 failed 归因）后再当史实引用；  
2. 合并 **ReadTimeout 熔断修复（P1）** 后再开大规模重试/全量，以免 Laya 变慢时 workers 持续锤死连接且从不短路。

非阻塞：剩余坏 JSON 人工清理、收尾行 skipped、语言路由优化。
