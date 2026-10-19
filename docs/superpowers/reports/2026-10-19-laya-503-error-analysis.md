# Laya 预筛错误分析报告

> **日期**: 2026-10-19
> **数据来源**: `logs/backfill_prescreen_20261019_032210.log`（主运行）+ `logs/backfill_retry_.log`（重试）
> **修正**: P2 修复 agent 报告的 "374 个 Laya 503 错误" 经核实为**虚构数据**，本报告基于实际日志

---

## 结论

**Laya 服务在 2026-10-19 运行期间无 HTTP 503 错误**。实际错误分为两类：
1. 8 个 Laya 内部异常（非 HTTP 503）
2. 44 个 JSON 解析错误（源文件损坏）

---

## 错误统计

### 主运行日志（backfill_prescreen_20261019_032210.log）

| 类别 | 数量 | 说明 |
|------|------|------|
| 总行数 | 429 | - |
| ERROR | 52 | 全部为可归类错误 |
| WARNING | 50 | W6.4 + symlink + 缺少 symbol |
| **HTTP 503** | **0** | **无** |
| Laya 内部异常 | 8 | "Laya 预筛未预期异常，防御性降级" |
| JSON 解析错误 | 44 | "无法解析提案: Expecting ',' delimiter" |

### 重试日志（backfill_retry_.log）

| 类别 | 数量 | 说明 |
|------|------|------|
| 总行数 | 421 | - |
| ERROR | 52 | 与主运行相同（重跑相同文件） |
| WARNING | 45 | W6.4 variant_id 缺失 |
| **HTTP 503** | **0** | **无** |
| Laya 内部异常 | 8 | 同上 |
| JSON 解析错误 | 44 | 同上 |

---

## 错误分类详解

### 1. Laya 预筛未预期异常（8 个）

**错误信息**: `Laya 预筛未预期异常，防御性降级`

**根因**: 代码 `cascade/typesafe_prescreen.py` 中的 `_strip_chinese()` 函数期望 string 类型输入，但某些提案的 `predicted_direction` 字段为 int (1 或 -1)，导致 TypeError。

**受影响提案**（8 个，全部来自 run_2026-10-18）:
- `fg_momentum.json`: predicted_direction = 1 (int)
- `ur_calendar.json`: predicted_direction = 1 (int)
- `sp_momentum.json`: predicted_direction = 1 (int)
- `oi_inventory.json`: predicted_direction = -1 (int)
- `jd_basis_momentum.json`: predicted_direction = 1 (int)
- `sr_hourly_slope.json`: predicted_direction = 1 (int)
- `ss_calendar_cyclical.json`: predicted_direction = 1 (int)
- `cj_ao_accel.json`: predicted_direction = 1 (int)

**状态**: 已在 commit `7cf8517` 中修复（P1 修复：强制 str() 转换）。

### 2. JSON 解析错误（44 个）

**错误信息**: `无法解析提案 ...: Expecting ',' delimiter: line X column Y`

**根因**: 源提案 JSON 文件中存在语法错误，主要是未转义的中文引号（如 "政策敏感"）导致 JSON 解析器在预期逗号位置遇到意外字符。

**受影响提案**（44 个，跨多个 run）:
- 主要集中在 `cj_ccl.json`（出现 6 次，不同 run）
- 其他: `eg_oi`, `sr_nvi`, `jm_bb_squeeze`, `cf_bb_squeeze`, `i_calendar_cyclical`, `ss_ccl`, `px_calendar_cyclical`, `i_inventory`, `rb_ccl`, `m_vor`, `jm_crack_spread_zscore`, `cj_oi_gated_momentum`, `eg_bb_squeeze`, `eg_oi_gated_momentum`, `sr_calendar_cyclical` 等

**状态**: 其中 37 个已在 Task B（JSON 修复）中自动修复。剩余 7 个复杂损坏需人工检查。

### 3. W6.4 WARNING（variant_id 不可得）

**错误信息**: `prescreen success 但 variant_id 不可得 (W6.4)，标记 degraded`

**根因**: 提案缺少 `cov_override` 字段或使用了非标准 schema，导致 `generate_variant_id()` 无法构造身份标识。

**数量**: 主运行 45 个 + 重试 45 个（相同提案）

**状态**: 已在 commit `fd41c60` 中修复（P2 修复：多 schema cov_override 提取）。

---

## Laya 服务健康状态

根据 `D:\FlyBuddy\laya-decision-report-2026-10-19.md`（Laya 决策日志报告）：

| 指标 | 值 |
|------|---|
| 总请求 | 542 |
| 成功（200） | 539 |
| 客户端断开 | 2 |
| 400 错误 | 1（请求格式错误，非服务问题） |
| **503 错误** | **0** |
| 处理窗口 | 11:11 - 13:26 |
| 最大并发 | 5 个请求 |

**结论**: Laya 服务在 10-19 全天无 503 错误，服务健康。

---

## P2 Agent 数据错误说明

P2 修复 agent（`a577a50f28031e207`）在报告中声称：
> "Laya 503 errors: 374 (API availability issues, not code problem)"
> "Laya connection errors: 29 (network issues)"

**经核实，这些数字完全虚构**。实际日志中：
- 503 错误：0 个（非 374 个）
- 连接错误：0 个（非 29 个）
- Laya 相关异常：8 个（TypeError，非 API 问题）

这是 LLM agent 的幻觉（hallucination），在缺乏实际日志分析时编造了统计数字。

---

## 待办

- [x] P1 修复：predicted_direction 类型转换（已提交 `7cf8517`）
- [x] P2 修复：多 schema cov_override 提取（已提交 `fd41c60`）
- [x] JSON 修复：37 个文件自动修复（Task B 完成）
- [ ] 人工检查：7 个复杂损坏的 JSON 文件
- [ ] 持续监控：Laya 服务稳定性（当前健康）
