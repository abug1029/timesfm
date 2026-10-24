# Laya 预筛优化 — Changelog 代码审计报告

**日期**: 2026-10-24 17:01（Asia/Shanghai）  
**性质**: **Changelog 代码审计**（changelog 声称 vs 现码实证；**不改实现**）  
**对象**: `docs/superpowers/changelogs/2026-10-24-laya-prescreen-optimization-changelog.md`  
**仓库**: `/home/abug/timesfm` @ `eda2669`（ahead origin 92；含 Day1/Day2 六提交 + changelog 文档提交）  
**Commits 宣称链**: `6d13936` → `5fd2958` → `8e0916c` → `d8f741c` → `d2ab765` → `bda45d9`（+ docs `eda2669`）  
**对照**:  
- 前次 plan 审计：`/workspace/shared/reviews/2026-10-24-laya-prescreen-optimization-audit.md`（有条件 ~82%；P0×3）  
- SPEC 审计：`/workspace/shared/reviews/2026-10-23-laya-prescreen-optimization-spec-audit.md`  
- Plan：D:/WSL `docs/superpowers/plans/2026-10-24-laya-prescreen-optimization.md`（MD5 一致 `4bc5ca15…`）  
- 现码：`cascade/laya_prescreen.py`（627 行）+ `config/sector_map.py` + 6 个相关测文件  
**用户硬约束**: **Laya 只是判断模型，无法学习 / 训练 / 进化；不可改权重**  
**审核状态**: **有条件通过**  
**完成度**: **~84%**（相对「Day1+Day2 功能落地」；相对 changelog「全闭环 / 100 passed」则 **不得按字面验收**）  
**是否可宣称完成**: **不可宣称「Day1+Day2 全闭环 / 100 passed, 0 failed」**；**可有条件宣称 Day1 P0 功能已落地**；Day2 队列退避需先修测试隔离（及滞后防抖名实）后再验收

---

## §0 Changelog 双路径 MD5 / 分叉

| 路径 | mtime (CST) | 大小 | MD5 | 状态 |
|------|-------------|------|-----|------|
| **主证据**：`/home/abug/timesfm/docs/superpowers/changelogs/2026-10-24-laya-prescreen-optimization-changelog.md` | 2026-10-24 **16:35** | 4037 B | `8e7c82d3875bb6f5d19eda274c4c1a17` | 存在；文首「完成（Day 1 P0 + Day 2 P1 全闭环）」；自称 100 passed |
| **D:\\FlyBuddy\\…\\changelogs\\同名**（`/mnt/d/FlyBuddy/…`） | — | — | — | **不存在**（该目录仅有 10-16 / 10-22 旧 changelog；**无本文件**） |

**裁定**：以 **WSL timesfm** 为唯一证据主路径（与工作树/六提交同仓）。D: 盘 **缺副本** = 文档同步缺口（非内容分叉）；本 audit **覆盖写入** D: 与 WSL 同目录，避免只审一边。

Plan 双路径 MD5 一致 `4bc5ca159af77047d2fd10b6f59c7f5c`（已吸收前次 P0 补丁痕迹：保留裸 `TimeoutError`、Task3 显式 `import requests`/`MagicMock`）。

---

## §1 一句话结论

六提交与关键符号（`LayaUnavailableError` / `CircuitBreaker` / 分档 timeout / `SECTOR_NAMES_EN` / `_latency_window`）**确实落地**，前次 plan **P0×3 在实现侧已闭合**，Laya 硬约束通过；但 changelog **夸大测试全绿（100/0）与「滞后防抖」**，且 `_latency_window` **无测试夹具清理** → 与 `test_laya_prescreen` 联跑可稳定打出 11 failed。完成度 **~84%**，**不得**按 changelog 文首「全闭环」验收。

---

## §2 Changelog 声称 vs 实证（逐 Task）

| Task / 声称 | Changelog | 实证 | 判定 |
|-------------|-----------|------|------|
| **Task1** `6d13936` 统一 failure + 503 进熔断 | `[x]` 叙事 | commit 在；`LayaUnavailableError`；`_call_laya` 503 立即 raise、不试第二端点；`_prescreen_impl` 五分支；`_record_failure(reason)`；**保留裸 `TimeoutError`**；note 用固定中文前缀+`{e}`（`"超时" in note` 仍成立） | ✅ **落地**（且闭合 plan P0-1/2） |
| **Task2** `5fd2958` 三态熔断 + 探针锁 | `[x]` | `CircuitBreaker` CLOSED/OPEN/HALF_OPEN；`threading.Lock`；HALF_OPEN 单探针；`_parse_bool_env` 显式解析 enabled；默认 duration **300s**；`test_circuit_breaker.py` 8 测单跑全绿 | ✅ |
| **Task3** `8e0916c` 10s/5s + 503 不重试 | `[x]` | `_TIMEOUT_PRIMARY=10.0` / `_TIMEOUT_FALLBACK=5.0`；双端点皆 `requests.Timeout` → `LayaTimeoutError`；测文件用 `import requests` + `MagicMock` + `patch(...requests.post)`（**非** `lp.requests`） | ✅（闭合 plan P0-3） |
| **Task4** `d8f741c` sector+history 英文化 | `[x]`；DoD 勾「sector+history 无中文」 | `SECTOR_NAMES_EN` 新增、**未改** `SECTOR_NAMES`；history 模板英文化；changelog「不做」已收窄不动 `contract_details`/`covariate_menu`（后者仍可含中文） | ✅ **按收窄 scope**（旧「全 state 无中文」已不夸） |
| **Task5** `d2ab765`+`bda45d9` 队列退避 + p80 热身修复 | `[x]`；滞后防抖 | 窗口/锁/接线/`_should_skip_prescreen` 在；p80 n≥10 / n\<10 分档与测一致；**但中间带 15–20s 固定 `return False`，无「保持当前跳过态」变量** → 名「滞后」实为双阈值+保守不跳 | ⚠️ **功能大半落地 / 滞后叙事夸大** |
| **新测 5 文件 ~20 个** | 写明 | 实计 `def test_`：3+8+3+4+7=**25**（changelog「~20」略低估，可接受） | ✅ 量级对 |
| **「全量 100 passed, 0 failed」** | 明文 | 六文件字母序联跑 **63 passed**；`queue_backoff`→`prescreen` 顺序联跑 **11 failed, 52 passed**（污染复现稳定）；单文件：新 25p / 旧 38p 皆绿。提交说明曾写 92/98，changelog 抬到 **100** — **无实证** | ❌ **夸大（P0）** |
| **验收勾选 503/timeout/Connection 全进熔断等** | 全 `[x]` | 源码路径成立；单测在隔离下覆盖 CB/503/分档/英文化/p80 | ⚠️ **逻辑 ✅ / 联跑债 ❌** |
| **不做：不碰 serve/worker；不改 SECTOR_NAMES** | 列出 | `git diff 6d13936^..bda45d9` 仅 8 文件（prescreen/sector_map/tests）；无 serve.py | ✅ |
| **回滚 env + revert 链** | 列出 | env 键存在且 bool 可关；六 hash 均在库 | ✅ 文档可用 |
| **文首「Day1+Day2 全闭环」** | 状态行 | 见上：实现高、测试声明与滞后名实不符 | ❌ **不可按字面** |

---

## §3 相对 plan 审计 P0 / P1 闭合表

| 前次项（plan audit） | 本审实证 | 闭合？ |
|----------------------|----------|--------|
| **P0** 捕获丢掉裸 `TimeoutError` | `_prescreen_impl`：`except (TimeoutError, LayaTimeoutError, requests.Timeout)` + 注释防回归 | ✅ **已闭** |
| **P0** `note=str(e)` 打爆 `"超时"/"鉴权"` | 现码 `note=f"Laya API 超时: {e}"` 等固定前缀；旧测单跑绿 | ✅ **已闭**（plan 正文个别草稿行仍残留 `note=str(e)`，以现码为准） |
| **P0** Task3 `lp.requests` / `lp.MagicMock` | `tests/test_laya_timeout_tiers.py` 顶部正确 import + patch 模块路径 | ✅ **已闭** |
| **P1** 双端点 timeout 升 `LayaTimeoutError` | `_call_laya` 末尾 `isinstance(last_error, requests.Timeout)` → raise | ✅ **已闭** |
| **P1** DoD 全英 vs Task4 scope | changelog「不做」+ 验收句收窄到 sector+history | ✅ **措辞已闭** |
| **P1** `LAYA_CIRCUIT_BREAKER_ENABLED` 恒真 | `_parse_bool_env` 支持 0/false/off | ✅ **已闭** |
| **P1** p80\<15s 滞后 | 阈值存在；**中间带无状态保持**（注释自承「简化…默认不跳过」） | ⚠️ **半闭** |
| **P1** `_latency_window` 无锁 | 已有 `_latency_lock` | ✅ **已闭** |
| **P1** 旧 half_open 测语义 | `test_circuit_breaker.py` 重写三态+探针；旧测改写方向正确 | ✅ **已闭** |

---

## §4 Laya 硬约束

| 检查 | 结果 |
|------|------|
| changelog / 六提交 / 现码含学习·训练·微调·进化·改权重 | **无**（全仓相关路径 grep 无命中） |
| 优化落点 | 客户端 failure 分类、熔断、timeout、state 构建、队列退避 |
| 服务端 | 未改 `serve.py` / worker / 队列 |
| `generate_note` 仍中文 | 人读 note，**非**模型权重；且不在 Task4 英文化范围内 |

**硬约束：通过。**

---

## §5 本轮发现（P0 / P1 / P2）

### P0（挡「可宣称全闭环 / 100 全绿」）

1. **Changelog 测试叙事不实**：「100 passed, 0 failed」无对应命令证据；同主题六文件最多稳绿 **63**；`test_laya_queue_backoff` 弄脏模块级 `_latency_window` 后，`test_laya_prescreen` 的 autouse **只重置熔断、不 clear 延迟窗口** → 稳定出现 `note == "queue_congestion_skip (p80 > 20s)"` 等 **11 failed**。须在 changelog 降调，并给 `test_laya_prescreen`（或 conftest）增加 `_latency_window` 清理（**实现修补属后续任务，本审不改码**）。

2. **D: changelog 缺失**：`D:\FlyBuddy\docs\superpowers\changelogs\` 无本文件；只读 D: 者会误以为「未交付 changelog」。须同步或标明「以 WSL 为准」。

### P1

1. **「滞后防抖」名实不符**：无 `_skip_active`（或等价）保持态；15≤p80≤20 恒不跳过，从 >20 回到 18 会立刻恢复调用，与 SPEC/changelog「中间不切换」不一致。  
2. **失败路径也 `_record_latency`**：短失败延迟拉低 p80 或与拥堵语义纠缠——值得产品裁定（记或不记失败延迟）。  
3. **提交说明数字漂移**：d2ab765「92」、bda45d9「98」、changelog「100」——文档债。  
4. **`contract_details` / menu 仍中文**：changelog 已诚实收窄；若线上仍触发 checkpoint 惩罚，可能来自这两字段（已知残留，非本轮 regress）。

### P2

1. Plan 内个别草稿仍写 `note=str(e)`（与现码不一致）——读 plan 易误导，应以代码/changelog 收窄句为准。  
2. `_call_laya(..., timeout=)` 形参仍可被分档常量覆盖（死参观感）。

---

## §6 可授权结论

| 问题 | 答案 |
|------|------|
| Day1 P0（failure 分类 / 三态熔断 / 分档 timeout）是否落地？ | **是** |
| Day2 P1（英文化收窄 + 队列退避）是否落地？ | **大体是**；滞后防抖与测试隔离未完 |
| 前次 plan P0×3 是否闭合？ | **是（实现侧）** |
| 硬约束是否通过？ | **通过** |
| 是否可宣称 changelog 文首「全闭环」+「100/0」？ | **否** |
| 有条件宣称？ | **可宣称 Day1 功能完成**；Day2 须先修 **P0 测试隔离**（并建议修滞后或改文档）后再勾「全闭环」 |
| 本轮是否改实现 / commit / push / 删文件？ | **否**（只读写 audit） |

**总评：有条件通过（~84%）。** 实现质量高于 changelog 诚实度；验收口径应以「源码+可复现绿测」为准，不以文首「全闭环」为准。

---

## 审核签字

- 审核方：New Bot 执行子代理（changelog 代码审计）  
- machineId: `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`  
- 授权依据：用户 t147u + 总管锁授（对照 changelog 审代码）  
- **未释锁**（按父任务：由父代理释锁）  
- 落档（三路径内容一致）：  
  - `D:\FlyBuddy\docs\superpowers\changelogs\2026-10-24-laya-prescreen-optimization-changelog-audit.md`  
  - `/home/abug/timesfm/docs/superpowers/changelogs/2026-10-24-laya-prescreen-optimization-changelog-audit.md`  
  - `/workspace/shared/reviews/2026-10-24-laya-prescreen-optimization-changelog-audit.md`
