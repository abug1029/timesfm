# Laya 预筛调用优化 SPEC 审计报告（修订重审）

**日期**: 2026-10-23 22:25（Asia/Shanghai）  
**性质**: **修订重审**（相对 t141u ~70%；非实施 changelog 审计）  
**对象**: `docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md`（修订版 v2，状态：待二审）  
**证据主路径**: WSL `/home/abug/timesfm/docs/superpowers/specs/...` 与 `D:\\FlyBuddy\\docs\\superpowers\\specs\\...` **MD5 一致** `696f46a329d92da7fd97eea09c534051`（相对 v1 `fd02da20…` 已变），mtime **2026-10-23 22:18 CST**，14858 B；无分叉。源码对照仓：`/home/abug/timesfm`（`cascade/laya_prescreen.py`、`config/sector_map.py`）。  
**前次审计**: `/workspace/shared/reviews/2026-10-23-laya-prescreen-optimization-spec-audit.md`（有条件 ~70%）  
**用户硬约束**: **Laya 只是判断模型，无法学习 / 训练 / 进化；不可改权重**  
**审核状态**: **有条件通过**  
**就绪度**: **~88%**（相对「可授权 Day1 P0 开工」；前次 ~70% → **+约 18 点**）  
**是否可授权 Day1 P0**: **可以（有条件）** — 须在开工说明/实现中显式对齐 `_call_laya` 异常包装；不必再大改叙事。

---

## §0 相对 t141u 一句话

v2 已吸收前次全部叙事级 P0（503 主导、先熔断后 timeout、去掉虚假 30s→0s、去掉「跳过 2 分钟」、承认 English 缺口并列入 P1）。Laya 硬约束仍通过。剩余主要是 **§3.1 草图与现码异常路径不对齐**（`_call_laya` 把 503 吞成 `ConnectionError`，`_prescreen_impl` 捕不到 `HTTPError`）以及 §3.4 `SECTOR_NAMES` 键值方向写反——属可实施前的定点澄清，不挡「按修订意图」授权 Day1 P0。

---

## §1 前次 P0 闭合核对

| # | 前次 P0 | v2 是否改对 | 是否自洽可实施 | 状态 |
|---|---------|-------------|----------------|------|
| 1 | 现网主导 **503（85/94）**；熔断须覆盖 503/`ConnectionError` | ✅ §0 关键修订 + §1.2 失败表 + §2.1/§3.1/§5.1 | ⚠️ 意图正确；§3.1 草图捕 `HTTPError` **与现码不符**（见 §3） | **叙事已闭；实施草图仍须定点改** |
| 2 | 勿先单独 timeout 5→10；先失败分类+熔断 | ✅ §4 顺序：P0-1→P0-2→P0-3；§3.3 写明前置条件 | ✅ | **已闭** |
| 3 | 「30s→0s」基线假；DoD「跳过 2 分钟」矛盾 | ✅ §2.2 明确不做虚假宣称；拥堵目标改为 OPEN 时 p50=0；全文无「2 分钟」 | ✅ | **已闭** |
| 4 | English-only 未成立（state 含中文） | ✅ §1.4 承认缺口；§3.4 列为 **P1-1 Day2**；§2.1 仍含英文化成功标准（跨日） | ⚠️ §3.4 示例把 `SECTOR_NAMES` **键值写反**（见 §3） | **承认已闭；补丁草图须改键方向** |

---

## §2 Laya 硬约束

| 检查 | 结果 |
|------|------|
| 「学习 / 训练 / 微调 / 进化 / 更新权重」 | **无** |
| 优化落点 | 客户端 failure 分类、三态熔断、timeout 分档、（P1）state 英文化 / 队列感知 |
| 与 10-19 effectiveness「引入 Laya 学习」 | **不复发** |

**硬约束：通过。** 无概念违规。

---

## §3 现码只读对齐（SPEC 草图 vs 工作树）

### 3.1 异常路径（挡「按 §3.1 原文照抄」）

现码事实（2026-10-23 只读）：

- `_call_laya`：对每个端点 `raise_for_status()`，**所有**异常（含 HTTP 503）落入 `except Exception`，最终 **`raise ConnectionError(f"All Laya endpoints unreachable: {last_error}")`**。
- `_prescreen_impl`：仅 `(TimeoutError, LayaTimeoutError)` → `_record_timeout()`；**`ConnectionError` / 含 503 的包装错误走 `Exception`，不进熔断**。
- 故今日 85/94 的 503 **永不打开**熔断——与 v2 问题陈述一致。

**v2 §3.1 草图问题**：在 `_prescreen_impl` 捕 `requests.HTTPError` —— **按现架构永远打不到**（503 已被 `_call_laya` 吞掉）。

**可实施的正确落点（须写入实现说明，建议补一句进 SPEC）**：

1. 改 `_call_laya`：对 503 **立即 re-raise**（或抛专用 `LayaUnavailableError`），且按 §3.3「不试第二端点」；和/或  
2. 在 endpoint 循环内/包装后按 `status_code` 或 `ConnectionError` 文案分类后调用 `_record_failure`；  
3. `_prescreen_impl` 对 `ConnectionError`（及超时）统一 `_record_failure`，不能只加一个永远不触发的 `HTTPError` 分支。

→ **不挡授权意图**，但 **挡「零修改照抄 §3.1 代码块」**。

### 3.2 熔断现状

仍为模块级 `_consecutive_timeouts` + `_circuit_until`（连续 **超时** → **600s**）；无三态、无探针锁。§3.2 草图方向正确；HALF_OPEN 建议补 **threading 锁**（多 worker/线程下 `_half_open_probe_in_flight` 仍可能惊群）——P1 级。

### 3.3 timeout / failover

有效路径仍 `timeout=5.0`；双端点已存在。§3.3 分档 10s+5s 与「503 不试第二端点」合理。草图笔误：`except requests.Timeout: last_error = e` 中 **`e` 未绑定**（应为 `as e`）——实施时修正即可。

### 3.4 English / SECTOR

- `payload.language = "en"` 已有。  
- `_extract_relevant_history` 大量中文模板（「已过门协变量」「同板块」「族:」等）。  
- `_build_state`：`sector` 来自 profile，默认 **「未知」**。  
- 真实 `config/sector_map.py`：

```text
SECTOR_NAMES = {
  "black_metals": "黑色系",
  "energy_chem": "能化",
  "agri": "农产品",
}
```

§3.4 写成 `"黑色系": "ferrous"` **键值方向错误**，且会误导改错共享表。正确方向：展示/注入 state 时用 **英文 key 或英文 display**，避免把中文 value 写入 `state["sector"]` / history；**不宜**把全项目 `SECTOR_NAMES` 改成中文 key。

### 3.5 服务端表

已标「外部调研，待管理员复核 / 本仓无读权」——前次 P1 已吸收。

---

## §4 仍开 / 新发现（相对「可授权」）

### 仍开（实施前定点，建议补 2–3 句进 SPEC 或开工注释）

1. **P0-草图对齐（强烈建议补丁，否则 Day1 易做错）**：写明必须改 `_call_laya` 的包装语义，不能只在 `_prescreen_impl` 加 `HTTPError`。  
2. **P1-草图**：`SECTOR_NAMES` 示例改键方向；英文化优先改 history 模板与 `state["sector"]` 注入，慎动共享中文 display 表的语义。

### 非挡（可 Day1 并行记下）

- HALF_OPEN 缺显式锁。  
- §2.1 成功标准含 Day2 English（跨日 DoD 可接受；Day1 验收以 §5.1 中 failure/熔断项为准）。  
- OPEN 时长 300s vs 现码 600s：有意缩短，验收用配置项即可（§5.3 已列 env）。

### 已闭（相对 t141u）

- 503 主导叙事、实施顺序、虚假 30s 基线、「2 分钟」矛盾、English 缺口承认、服务端未复核脚注、回滚配置键名、success 定义（`status=success` 且非熔断跳过）。

---

## §5 结论

**有条件通过（就绪度 ~88%，前次 ~70%）。**

| 问题 | 答案 |
|------|------|
| 相对 t141u | **抬升**；叙事级 P0 已闭 |
| 可授权 Day1 P0？ | **可以（有条件）**：按 §4 顺序做 P0-1/P0-2，再 P0-3；**实现必须对齐 `_call_laya` 异常包装** |
| 是否还需大改 SPEC 正文？ | **不必**；建议补一小段「`_call_laya` 现状与改法」+ 修正 §3.4 键方向后即可视为可施工 |
| Blocker（硬） | **无**（硬约束通过；叙事 P0 已闭） |
| Blocker（软 / 开工注释） | §3.1 与现码异常路径不对齐；照抄草图会漏掉 503 |

**推荐 Day1 范围**：§3.1（含改 `_call_laya`）+ §3.2；§3.3 仅在前两项合并进主路径后再做。English / 滑动窗口留 Day2。

---

## §6 审核签字

- 审核方：New Bot 执行子代理（**本任务不释放** `/workspace/shared/local-pc.lock`；不联系总管；不向用户发消息）  
- machineId: `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`  
- 授权依据：用户 standing + 父任务 pt143u  
- 落档（本文件覆盖）：  
  - `/home/abug/timesfm/docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec-audit.md`  
  - `D:\\FlyBuddy\\docs\\superpowers\\specs\\2026-10-23-laya-prescreen-optimization-spec-audit.md`  
  - `/workspace/shared/reviews/2026-10-23-laya-prescreen-optimization-spec-audit.md`
