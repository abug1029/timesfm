# 国庆 success_gate data_stale 旁路 — 代码审核报告

**Date:** 2026-10-06
**Reviewer:** oh-my-claudecode:code-reviewer (Opus)
**Scope:** 5 文件（2 code, 1 template, 2 test）+ changelog + plan
**Verdict:** ✅ APPROVE（无阻塞问题）

---

## 统计

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 2 |
| LOW      | 2 |

---

## MEDIUM 发现

### M1: STALE_DATA_DAYS 边界语义需 domain expert 确认

**File:** `scripts/praxist_supervisor.py:2004`
**Confidence:** HIGH

代码使用 `age > STALE_DATA_DAYS`（严格大于）：
- age=3（周五→周一）：**不放行**，门保持关闭
- age=4（周五→周二）：**放行**，旁路打开

Changelog §7 显式提出了这个不确定性：「周一休市、周二早盘尚无新 bar 时，周五到周二日历差为 4，旁路会开一个上午」。

**影响:** 若周一是假日且周二早盘尚无新 bar，旁路会开约半个上午。可能是预期行为（假日 fail-open），也可能需要调整（`>= 3` 代替 `> 3`）。

**建议:** 与 domain expert 确认后在 changelog 记录最终决定。

### M2: ~~测试覆盖完整性不可验证~~ → **已验证完整**

**File:** `tests/test_success_gate_stale_20261006.py`

审核员初判称 diff 中不可验证，经主审核会话补充读取完整测试文件后确认：**8 个用例全部实现**。

覆盖矩阵：

| # | 场景 | 用例 | 状态 |
|---|------|------|------|
| 1 | 边界 age=3 拒收 | `test_age_three_days_still_rejects` | ✅ |
| 2 | 边界 age=4 放行 | `test_age_four_days_opens` | ✅ |
| 3 | 国庆假期间放行 | `test_national_day_gap_fail_open` | ✅ |
| 4 | 按 symbol 独立判定 | `test_stale_is_per_symbol` | ✅ |
| 5 | 不可读 kline 保持拒收 | `test_unreadable_kline_stays_closed` | ✅ |
| 6 | window_moved 不读 kline | `test_window_moved_does_not_read_kline` | ✅ |
| 7 | 新 bar 同锚仍拒收 | `test_fresh_bar_same_anchor_still_rejects` | ✅ |
| 8 | WARNING 每 symbol 一次 | `test_stale_warning_once_per_symbol` | ✅ |

**此条降级为 INFO，非阻塞。**

---

## LOW 发现

### L1: `_today_shanghai()` 缺防御包装

**File:** `scripts/praxist_supervisor.py:2305-2307`

`datetime.now(ZoneInfo("Asia/Shanghai"))` 无异常处理。风险极低——zoneinfo 和 datetime 是核心库，但与其他函数（如 `_kline_1h_max_dt` 全 catch）的防御模式不一致。

**建议:** 可选加 try-except 返回 UTC fallback。文档化这是防御性的，非预期失败。

### L2: cache 原地修改可能让维护者意外

**File:** `scripts/praxist_supervisor.py:2331-2345`

`_symbol_data_stale` 原地修改 cache dict（`setdefault` + 赋值）。docstring 已记录用于 memoization。单线程 supervisor、cache 生命周期短，风险低。

**建议:** docstring 已记录，可在调用点（如 `_locked_success_rows`）加一行注释标明 cache 会被原地修改。

---

## 亮点

**防御性编程出色：**
- `_kline_1h_max_dt` 以 `?mode=ro` 只读打开 DB，所有异常路径返回 None（fail-safe，不是 fail-open）
- 空/缺数据处理一致正确

**关注点分离清晰：**
- 助手函数聚焦、可测试
- `_prior_success_class` 从内联逻辑提取为单一事实来源
- 门控（`_success_delta_gate`）与物化（`_locked_window_lines`）职责分明

**门检查顺序正确：**
```
no_prior_success → anchor_unavailable → window_moved → data_stale → success_delta
```
锚不可得时不读 kline，窗口已平移时不读 kline。每条逃逸阀只在必要时才评估。

**测试更新扎实：**
- 旧测试 tmproot 把 kline 钉到 2099-01-01，防止活库旧数据翻转断言
- 8 个新用例专门针对冻结旁路
- 测试命名描述性，遵循项目规范

**文档一致：**
- docstring 已更新反映新旁路逻辑
- 提示词规则 9 指向锁定名单
- Changelog 含详细理由和开放问题

**提示词工程到位：**
- 规则 9 明确警告：「该名单为空时不要为了过门去补 success_delta」
- 防止模型编造假 delta 过门

**无安全/注入风险：**
- SQL 查询硬编码，无用户输入
- DB 只读打开
- 无外部输入未经校验即信任

---

## 开放问题（需宿主确认）

| # | 问题 | 当前实现 | 来源 |
|---|------|----------|------|
| 1 | `== 3` 不放行、`> 3` 放行是否接受？ | `age > STALE_DATA_DAYS` | Changelog §7.1 |
| 2 | 新 bar 入库、snapshot 锚未更新的空档恢复强制 success_delta 是否接受？ | 是预期行为 | Changelog §7.2 |
| 3 | 物化探门的 `_probe` 不打日志是否正确？ | 静默探门 | Changelog §7.3 |
| 4 | 锁定名单是提示而非硬门的设计是否合理？ | 硬拒收只在 `_success_delta_gate` | Changelog §7.4 |

---

## 结论

**无阻塞问题，可以合并。** 4 个设计决策需 domain expert 确认（尤其 #1 边界条件），建议在 changelog 中记录最终决定。

代码结构良好、防御性强、边界处理完整。实现与 plan 一致，文档与代码一致。

---

**审核工具:** oh-my-claudecode:code-reviewer (Opus)
**审核日期:** 2026-10-06
**审核范围:** WSL `/root/timesfm`，基线 `52132c3`
