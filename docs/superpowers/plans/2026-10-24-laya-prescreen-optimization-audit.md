# Laya 预筛优化 — Implementation Plan 审计报告

**日期**: 2026-10-24 10:20（Asia/Shanghai）  
**性质**: **计划审计**（只审 plan，**不实施**；用户已表态「先不动 Laya Day1」）  
**对象**: `docs/superpowers/plans/2026-10-24-laya-prescreen-optimization.md`  
**证据主路径**:  
- `D:\FlyBuddy\docs\superpowers\plans\2026-10-24-laya-prescreen-optimization.md`  
- WSL `/home/abug/timesfm/docs/superpowers/plans/2026-10-24-laya-prescreen-optimization.md`  
- **MD5 一致** `4c1e865b8962b3c0d9953bbd37140a51`（45662 B）；mtime D 09:54 / WSL 09:55 CST；**无分叉**  
**对照**:  
- SPEC v2：`…/specs/2026-10-23-laya-prescreen-optimization-spec.md`（D/WSL MD5 一致 `4c4f78ca…`）  
- SPEC 修订重审：`/workspace/shared/reviews/2026-10-23-laya-prescreen-optimization-spec-audit.md`（有条件 ~88%；可有条件授权 Day1 P0）  
- 现码：`/home/abug/timesfm/cascade/laya_prescreen.py`（476 行）+ `config/sector_map.py` + `tests/test_laya_prescreen.py`  
**用户硬约束**: **Laya 只是判断模型，无法学习 / 训练 / 进化；不可改权重**  
**审核状态**: **有条件通过**  
**就绪度**: **~82%**（相对「plan 可授权实施」；相对 SPEC 审计遗留项吸收度高）  
**是否可授权实施**: **有条件可授权 Day1（须先补 plan P0 补丁）**；**本轮勿开工**（用户：先不动 Laya Day1）

---

## §1 一句话

Plan 正确吸收了 SPEC 审计的核心遗留（改 `_call_laya` 抛 `LayaUnavailableError`、先 failure/熔断后 timeout、`SECTOR_NAMES_EN` 不改共享中文表、顺序 Task1→2→3），钩点与现码行号大体对齐；但 **Task1 异常元组丢掉裸 `TimeoutError` + 改 note 文案会打爆现有回归测**，Task3 测试伪代码引用不存在的 `lp.requests`/`lp.MagicMock`，且 DoD「state 全英」相对 `contract_details`/`covariate_menu` 仍夸大——**修这几处前不宜派 executor 照抄开工**。

---

## §2 Plan vs SPEC / 现码

### 2.1 路径与元数据

| 项 | 结论 |
|----|------|
| D vs WSL plan | MD5 一致，无分叉 |
| Plan 自称 Spec「v3 ~88%」 | SPEC 文首仍写 **修订版 v2**；就绪度 88% 来自 **SPEC audit**，非 SPEC 自称 v3 → **元数据笔误（P2）** |
| 范围声明 | 「只动 `laya_prescreen.py` + `sector_map.py`」与 Task1–5 一致；测试/changelog 另增文件合理 |

### 2.2 对 SPEC P0-1/2/3 与审计遗留的覆盖

| SPEC / 审计遗留 | Plan 是否覆盖 | 评价 |
|-----------------|---------------|------|
| Day1 须改 `_call_laya`：503 现被吞成 ConnectionError | ✅ Task1 Step 1d：`HTTPError`+503 → `LayaUnavailableError`，不试第二端点 | **已吸收（关键）** |
| 顺序：先失败分类+熔断，再 timeout | ✅ Task1→2→3；文首 Global + 执行顺序图 | **已吸收** |
| 主导失败是 503 非 timeout | ✅ Goal/Architecture/Review Focus #1/#4 | **已吸收** |
| §3.4 SECTOR_NAMES 键值方向（English=P1） | ✅ Task4 新增 `SECTOR_NAMES_EN`，**不改** `SECTOR_NAMES`；默认 `unknown` | **已吸收** |
| P0-2 三态 + HALF_OPEN 探针锁 | ✅ Task2 + 并发测 | **对齐 SPEC §3.2，且补了审计建议的锁** |
| P0-3 10s/5s + 503 不重试 | ✅ Task3（依赖 1+2） | **顺序正确** |
| P1-1 / P1-2 | ✅ Task4 / Task5 | **有，但见 §4 缺口** |
| Laya 不可学习 | ✅ Global Constraints 显式禁止训练叙事 | **通过** |

### 2.3 现码钩点真实性（只读）

| 钩点 | 现码事实 | Plan 是否对得上 |
|------|----------|-----------------|
| `_call_laya` L287：单 `except Exception` → 最终 `ConnectionError` | ✅ | Task1/3 改点正确 |
| `_prescreen_impl` L391：`timeout=5.0`；仅 `(TimeoutError, LayaTimeoutError)` → `_record_timeout` | ✅ | Task1 统一 `_record_failure` 方向正确 |
| 熔断 L179–216：`_consecutive_timeouts` + 600s | ✅ | Task2 替换为 `CircuitBreaker`（默认 300s）与 SPEC 一致 |
| `_build_state` sector 默认「未知」；history 中文模板 | ✅ | Task4 对准 |
| `_load_symbol_profile` 用 `SECTOR_NAMES` 中文写入 sector **与** `contract_details` | ✅ | Plan 只改 `_build_state.sector`，**未改 contract_details 中文**（见 P1） |
| `_load_covariate_menu` 读中文 md | ✅ | Plan **未处理**（见 P1） |

### 2.4 任务拆分 / 验收 / 风险（结构）

- **6 Task + Day1/Day2 + DoD 表**：结构完整，TDD 步骤清晰。  
- **风险**：文中 Review Focus 5 条钉到 step，优于空泛「注意线程安全」。  
- **夸大**：Task6 commit message「Day1+Day2 complete」、DoD#5「state 所有字段无中文」在 Task4 范围内 **做不到全字段**；Plan 本身 checkbox 未勾，**未伪称已完成实现**（好）。

---

## §3 Laya 硬约束

| 检查 | 结果 |
|------|------|
| 学习 / 训练 / 微调 / 进化 / 改权重 | **无** |
| 优化落点 | 客户端 failure 分类、熔断、timeout、state 构建、队列退避 |
| 服务端 | 明确不碰 `serve.py` / worker / 队列 |

**硬约束：通过。**

---

## §4 发现（P0 / P1 / P2）

### P0（开工前必须改 plan 或实现说明）

1. **裸 `TimeoutError` 从 `_prescreen_impl` 捕获元组中消失**  
   - 现码 / 现测：`except (TimeoutError, LayaTimeoutError)`；`test_api_timeout_returns_degraded` / `test_timeout_triggers_circuit_not_error` mock 抛的是 **`TimeoutError`**。  
   - Plan Step 1h 改为 `(LayaTimeoutError, requests.Timeout)` —— **不含 `TimeoutError`** → 落入 `Exception` → `status="error"` + reason `unknown`，熔断语义与回归 **双炸**。  
   - **补丁**：捕获元组保留 `TimeoutError`（或在 `_call_laya` 将 `requests.Timeout` 升为 `LayaTimeoutError` 并同步改测）。

2. **`note=` 从固定中文改为 `str(e)` 破坏现有断言**  
   - 现测断言 `"超时" in note`、`"鉴权" in note`。  
   - Plan 用 `note=str(e)` → 英文异常串，回归失败。  
   - **补丁**：保留稳定 note 前缀（可附 `str(e)`），或同步改测；plan 须写明。

3. **Task3 测试伪代码不可运行**  
   - `lp.requests.Timeout` / `lp.requests.HTTPError` / `lp.MagicMock`：`requests` 仅在 `_call_laya` 内 import，**不是**模块属性；`MagicMock` 亦不在 `lp` 上。  
   - **补丁**：测试内 `import requests` + `from unittest.mock import MagicMock`；patch 目标仍为 `cascade.laya_prescreen.requests.post`（实现里需保证模块级可 patch，或 `patch("requests.post")` 与实现 import 风格一致）。

### P1（不挡有条件授权，挡「照抄即绿 / DoD 字面」）

4. **真实 timeout 经 `_call_laya` 仍升为 `ConnectionError`**  
   - Task1 `_call_laya` 对 `requests.Timeout` 是 `continue` 后最终 `ConnectionError`，不会以 `LayaTimeoutError` 冒泡。  
   - `_prescreen_impl` 的 timeout 分支主要靠 **mock**；线上 timeout 记为 `connection_error`。与「统一分类」叙事不完全一致。建议 `_call_laya` 在双端点皆超时后 `raise LayaTimeoutError(...) from last_error`。

5. **DoD「state 所有字段无中文」相对 Task4 夸大**  
   - `contract_details` 仍来自 `_load_symbol_profile` → `f"{symbol} ({sector_name})"`（中文板块名）。  
   - `covariate_menu` 仍可能注入整份中文 `covariate_menu.inc.md`。  
   - Task4 测试只扫 `sector` + history，**扫不到**上述字段。  
   - **补丁**：收窄 DoD 为「sector + history 英文化」；或追加改 profile/`contract_details` + menu 策略（截断/不加中文 menu / 英文摘要）。

6. **`LAYA_CIRCUIT_BREAKER_ENABLED` 配置恒真**  
   - `_cb_enabled = _env_nonempty(...) or True` —— 任意假值仍被 `or True` 打开。应显式解析 `0/false/off`。

7. **SPEC §3.5 恢复条件「p80 < 15s」未实现**  
   - Plan 仅 `p80 > 20` 跳过；恢复测靠 `clear()`，无 15s 滞后。与 SPEC 验收句不完全一致。

8. **`_latency_window` 无锁**  
   - 与 CircuitBreaker 的线程安全承诺不一致；多线程 append/pop 有竞态（P1）。

9. **旧测 `test_half_open_resets_on_expire` 语义变化**  
   - 旧：到期后计数清零、全程放行。新：HALF_OPEN + 单探针。单次断言仍可能过，但「半开」语义已变，建议在 Task2 回归清单中显式改写该测，避免假绿。

### P2

10. Plan 写 Spec「v3」——应为 v2 + audit ~88%。  
11. Task6 `git push backup master` + 「通知用户验收完成」——实施阶段事项；**本轮用户禁止开工**，执行时另需用户授权 push。  
12. `_call_laya(..., timeout=)` 形参在 Task3 内被分档常量覆盖，形参成死参——可注明或删除以免误导。

---

## §5 是否可授权实施

| 问题 | 答案 |
|------|------|
| Plan 是否覆盖 Day1 P0 且顺序正确？ | **是**（含改 `_call_laya`） |
| 是否可「零修改照抄」派子代理？ | **否** — 须先合入 §4 P0 补丁 |
| 有条件授权 Day1？ | **可以**（修 P0 后：Task1→2→3） |
| **本轮是否开工？** | **否** — 用户明确「先不动 Laya Day1」；本任务只落 audit |
| Day2 Task4/5？ | 可并行规划；Task4 须先收窄 DoD 或扩 scope |
| 硬 Blocker？ | **无**（硬约束通过；无「不可修」架构冲突） |
| 软 Blocker（挡照抄） | §4 P0 ×3 |

---

## §6 结论

**有条件通过（就绪度 ~82%）。**

相对 SPEC 修订重审（~88% 可有条件授权 Day1），本 **plan** 已把「必须改 `_call_laya`」写成可执行 Task，顺序与 SECTOR 方向正确，Laya 硬约束通过。扣分主要来自：**回归破坏点（TimeoutError / note）未写入 plan、Task3 测试草稿不可运行、全英 DoD 超 Task4 实际范围**。

**建议**：用户恢复 Day1 授权前，用一小段 plan 补丁闭合 §4 P0（不必重写全文）；然后再按 Task1→2→3 实施。Task4 开工前先裁定 DoD 范围（sector+history vs 全 state）。

**本任务未改任何实现代码、未 commit/push/删除、未释放** `/workspace/shared/local-pc.lock`。

---

## 审核签字

- 审核方：New Bot 执行子代理（plan audit only）  
- machineId: `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`  
- 授权依据：父任务 pt145u + 总管锁授 + 用户「先不动 Laya Day1」  
- 落档：  
  - `D:\FlyBuddy\docs\superpowers\plans\2026-10-24-laya-prescreen-optimization-audit.md`  
  - `/home/abug/timesfm/docs/superpowers/plans/2026-10-24-laya-prescreen-optimization-audit.md`  
  - `/workspace/shared/reviews/2026-10-24-laya-prescreen-optimization-audit.md`
