# 国庆假期 success_gate 死锁诊断报告

> **日期**: 2026-10-06
> **窗口**: 2026-10-05 ~17:50 → 2026-10-06 ~08:53（15h，过夜）
> **触发**: supervisor.out 反复出现 `success_gate: {symbol}_{cov} 复跑缺 success_delta (len=0 < 20) → 拒收 (no_success_delta)`，24 个 (symbol, cov) 组合被反复拒收
> **诊断团队**: P0 根因分析 + P1 部署核查 + P2 数据运维（三路并行，sonnet 子 agent）
> **结论**: **v4 2.1 绝对锚 × T2 success_delta 门 × 国庆休市 = 死锁**（非 bug，是设计缺陷在假期边界条件下的复现）

---

## 1. 过夜运行概况（15h 窗口）

| 项 | 起（10-05 ~17:50） | 止（10-06 ~08:53） | Δ |
|---|---|---|---|
| Supervisor PID | 107041（活）| 同 | 凌晨 01:23 由子 supervisor 重启过（见 §3.2）|
| `cycles_done` | 225 | **236** | +11 |
| `phase` | fast | fast | 同 |
| v4 协议指纹 | `f02b2a433fd572ea…` | 同 | 未变（无重生波）|
| `active` 物化证据 | 133 / 312 | 142 / 321 | **+9 条** |
| 旧协议残留 | 91ab:18 / bd85:16 / none:145 | 同 | 0 |
| `aligned_verdicts.jsonl` | 200 行 | **357 行** | **+157 行** |
| `gate_pass=true`（最近 140 行）| — | **56 / 140 = 40.0%** | — |
| 拒收原因 | — | `ok:114 / no_data:26` | 无硬门失败 |
| 启动 run 数 | — | 9 | ~0.6 run/h |

**表面数据 vs 真实解读**:

| 表面指标 | 真实解读 |
|---|---|
| cycles 225 → 236 (+11) | ✅ 系统在跑 |
| active 证据 133 → 142 (+9) | ✅ 有新组合在探索 |
| verdicts 200 → 357 (+157) | ⚠️ 全是**无 prior 的新组合**，锁死组合的复跑全废 |
| gate_pass 40% | ⚠️ 分母里混了锁死组合的重复拒收，实际有效率更低 |
| phase=fast 未切 slow | 🔴 **慢环饿死**（peer 学习回传无 payload）|

---

## 2. 根因：v4 2.1 绝对锚 × T2 增量门死锁

### 2.1 死锁机制

| 组件 | 行为 | 单独看 | 叠加后 |
|---|---|---|---|
| v4 2.1 绝对锚 | `eval_end_ts` 钉死在 `2026-09-30 15:00:00`，数据不动锚不动 | ✅ 设计合理（防 1-bar 前视）| 锚永远不动 |
| T2 success_delta 门 | `prior_ts == anchor` → 强制要求 `success_delta ≥ 20 字` | ✅ 防重复提案 | `window_moved` 逃逸阀永远不触发 |
| 国庆休市（10/1-10/7）| 数据 6 天无新 bar | ✅ 预期行为 | 锚钉死 + 门强制 + 逃逸失效 = **死锁** |

### 2.2 代码证据（P0 定位）

**`praxist_supervisor.py:2300-2340 _success_delta_gate()`**（行号基于 dfd1f43 之前的版本；dfd1f43 在函数内插入 `_symbol_data_stale` 检查后，相关行下移至 ~2400-2440）:

```python
prior_ts = _row_eval_end_ts(prior, cache, root)   # -> "2026-09-30 15:00:00"
anchor = _current_window_anchor(snapshot, ...)     # -> "2026-09-30 15:00:00"
if prior_ts != anchor:
    return None, "window_moved"                    # <- 逃逸阀，但永不触发
delta = str((prop or {}).get("success_delta") or "").strip()
if len(delta) >= 20:
    return None, "success_delta_ok"
return "no_success_delta", "no_success_delta"      # <- 100% 命中
```

**锚计算逻辑**（`monthly_backtest.py:356-358`，dfd1f43 未改此文件，行号仍准确）:

```python
_anchor = (str(eval_end_ts) if eval_end_ts is not None
           else (pd.Timestamp(all_1h["dt"].iloc[-1])
                 + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"))
# -> 最后一根 bar dt=14:00 + 1h = 15:00:00
```

### 2.3 数据证据（P2 定位）

| Symbol | kline_1h 最新 dt | kline_1d 最新 dt | 数据行数 | 来源 |
|---|---|---|---|---|
| rb / jd / m / lh / ss / fu / sp / cj | `2026-09-30 14:00` | `2026-09-30` | 6945-10000 | `futures_*.db` |

- **`pull_cron.log`**: 10-05 17:45 最后一次采集 ✅（无新 bar 可写）
- 数据文件 mtime = 2026-10-05 18:xx（pull 跑了，但市场没数据）
- `eval_end_ts=2026-09-30 15:00:00` 与 kline 收盘时间完全吻合，**无 bug**

### 2.4 拒收样本

`supervisor.out` 中 24 个不同 (symbol, cov) 被反复拒收（每 cycle ~18 条，15h 累计 24+ 条 WARNING）:

```
success_gate: rb_basis_momentum 复跑缺 success_delta (len=0 < 20) -> 拒收
  prior=rb_term_structure_750fe8f84747 class=hard-gate-but-losing
  run_mode=exploration eval_end_ts=2026-09-30 15:00:00
```

对应提案 `success_delta` 字段全部为空字符串（19/19 提案 `len=0`）。

---

## 3. 三路专家独立核查

### 3.1 P0 根因分析（108k tokens / 66 tool-uses）

- 抽样 `trajectory.jsonl` 拒收上下文 + `orchestrator_status.json`
- 定位 `_success_delta_gate` 完整计算链（`praxist_supervisor.py:2300-2340`）
- 发现 `window_moved` 逃逸阀在数据冻结期永不触发 -> 死锁
- 9119 条 pre-T2 gate_pass 裁决 `eval_end_ts=None`（行内），但 `_row_eval_end_ts` 从 checkpoint 回读到 `2026-09-30 15:00:00`
- 17 条 post-T2 gate_pass 裁决行内直接携带 `eval_end_ts=2026-09-30 15:00:00`

### 3.2 P1 部署核查（94k tokens / 47 tool-uses）

- supervisor PID 107041 启动时间：**2026-10-06 01:23:41**（elapsed 07:56:24）
- e007a6c commit 时间：2026-10-06 00:29:16
- **T2d 已部署生效**（启动晚于 commit 54 分钟）
- T2d 改动范围：`scripts/aligned_slow_loop.py:154-183` 新增 `_checkpoint_last_anchor()` + :346-350 回填逻辑
- T2d 触发条件 `eval_end_ts is None AND anchor is None` 不满足（anchor 非 None）-> 当前场景无需兜底
- WARNING 中 `eval_end_ts=2026-09-30 15:00:00` 是 **`prior` 行的 eval_end_ts**（`praxist_supervisor.py:2331-2338` 的 `prior_ts`），不是当前运行窗口的锚

### 3.3 P2 数据运维（86k tokens / 37 tool-uses）

- 全仓 28 个 `futures_*.db` 的 `kline_1h` `max(dt)` = `2026-09-30 14:00`
- `pull_cron.log` 10-05 18:33 最后一次采集 ✅（无 error / exception / fail / timeout）
- 数据停在 Sep 30 是**国庆休市的预期行为**，不是 `pull_cron` 故障
- `scripts/aligned_slow_loop.py:142-157` 的 `eval_end_ts` 计算逻辑与 kline 收盘时间吻合
- 10/8 周三开市后 pull_cron 会自动拉到新数据，`eval_end_ts` 自然平移

**三路诊断完全收敛**，无矛盾。

---

## 4. 与 10-03 / 10-05 报告的关联

| 报告 | 识别 | 本报告新发现 |
|---|---|---|
| 10-03 （46h 战果）| peer 学习机制断裂（225 cycle 结果未回传）| 断裂在假期数据冻结条件下**升级为死锁** |

> **[2026-10-06 注]**：10-05 报告的「断裂」原始结论已被其自身 **T0 勘误**推翻——结果回传实际已由 `known_verdicts.inc.md` 注入每一代提示词（见 `2026-10-05-peer-learning-gap-analysis.md` 顶部 T0 块）。当前真实问题是**数据冻结期 payload 为零**，而非注入通路失效。
| 10-05 Peer 学习反馈硬化 T0-T3 | T0-T3 已部署（8 commits）| 结构就位但 payload 为零（无成功提案可回传）|
| 10-05 T2 success_delta 增量门 | commit `318daca` / `2089f1c` / `e007a6c` | 门本身正确，但与 v4 2.1 绝对锚叠加形成死锁 |

**关键判断**: 10-05 代码侧修复的 T0-T3 + T2 门都**工作正确**，但设计者未考虑「数据末端长期冻结」这一边界条件。T2 门的 `window_moved` 逃逸阀假设「数据会持续增长」，该假设在假期失效。

---

## 5. 处置建议

> **[2026-10-06 实施状态更新]**：下方 P0-1 与 P0-3 建议已由 commit `dfd1f43`（2026-10-06 14:18）实施。P0-1 实现为 `_symbol_data_stale()` 函数（上海日历年龄 >3 天放行）；P0-3 实现为 `_locked_success_rows()` 生成的 `## Locked this window` 段注入 prompt_base.jinja2 规则 9。详见 `docs/superpowers/changelogs/2026-10-06-holiday-success-gate-data-stale.md`。

### P0-1（立即）：`_anchor_is_stale()` 临时旁路

在 `_success_delta_gate` 中增加一个条件：如果**数据末端超过 N 天未更新**（如 3 天），自动降级为 `window_moved` 放行（fail-open）。

**检测方式**: 对比 `kline_1h` 的 `max(dt)` 与当前日期，> 3 天即视为 stale。

**位置**: `praxist_supervisor.py:2300-2340` `_success_delta_gate` 函数内，在 `prior_ts != anchor` 判断之前插入。

**风险**: 可能放行一些本应被拒的重复提案，但假期期间 peer 无法提供有意义的 success_delta，fail-open 优于死锁。

### P0-2（10/8 开市后自动解除）：checkpoint 锚解锁

新 1h bar 入库后，新创建的 variant 锚 = 新数据末端。但旧 checkpoint 仍钉在旧锚 -> 需要在 `_load_checkpoint_state` 或 `_eval_end_ts_for_run` 中检测「数据末端已超过 checkpoint 锚」-> 清除旧锚、允许窗口跟随数据前进。

**当前 v4 2.1 设计**: 「钉住不平移」，但钉住的前提是数据末端 = 锚；数据增长后应自动解锁。

### P0-3（与 10-05 peer 学习回传合并）：已知成功组合注入 peer prompt

将 gate_pass=True 的 (symbol, cov) 列表注入 peer prompt 的 `known_verdicts` 通道，让 peer 不再提案已锁死的组合，避免浪费 cycle 预算。

**现状**: `CROSS_MATRIX_MAX_ROWS = 40` 的 known_verdicts 注入已存在（`prompt_base.jinja2:37,65`），但需要确认是否包含了 gate_pass 状态的成功组合。

**效果**: 减少无效 LLM 调用（当前 ~24 个无效拒收/cycle × ~10 cycle/天 ≈ 240 次无效 LLM 调用 / 天）。

---

## 6. 决策建议

| 选项 | 代价 | 收益 |
|---|---|---|
| **A. 立即修 P0-1 + P0-3** | 今天实施 + 测试，supervisor 今晚重启生效 | 假期不再浪费 cycle；慢环恢复工作 |
| **B. 等 10/8 开市自动解除** | 2 天 ~480 次无效 LLM 调用 | 不动代码，无回归风险 |
| **C. 只修 P0-3** | peer 绕开锁死组合，但 T2 门设计缺陷留着下次复现 | 治标，治不了本 |

**建议**: **A**。P0-1 是 10 行内的 fail-open 旁路，回归风险低；P0-3 与 10-05 已识别的 peer 学习回传合并，一石二鸟。

---

## 7. 附录：原始诊断数据

### 7.1 supervisor 状态（`data/cache/supervisor_state.json`）

```json
{
  "cycles_done": 236,
  "phase": "fast",
  "tokens_baseline_m": 113.957,
  "paused_429": false,
  "llm_provider": "primary",
  "llm_route": "primary",
  "last_run_dir": "/home/abug/timesfm/task_FM/experiments/run_2026-10-06_08-37-58_primary_task_FM",
  "last_run_id": "run_2026-10-06_08-37-58_primary_task_FM",
  "last_harvested_run_id": "run_2026-10-06_06-37-07_primary_task_FM",
  "user_paused": false
}
```

### 7.2 过夜启动的 run（`task_FM/experiments/`）

| 时间 | Run ID | 状态 |
|---|---|---|
| 10-05 17:52 | run_2026-10-05_17-52-56 | 完成 |
| 10-05 19:13 | run_2026-10-05_19-13-xx | 完成 |
| 10-05 20:09 | run_2026-10-05_20-09-44 | 完成 |
| 10-05 21:30 | run_2026-10-05_21-30-xx | 完成 |
| 10-05 22:05 | run_2026-10-05_22-05-15 | 完成（含 early WARNING）|
| 10-06 00:20 | run_2026-10-06_00-20-57 | 完成 |
| 10-06 02:35 | run_2026-10-06_02-35-38 | 完成 |
| 10-06 04:36 | run_2026-10-06_04-36-34 | 完成 |
| 10-06 06:37 | run_2026-10-06_06-37-07 | 完成（last_harvested）|
| 10-06 08:37 | run_2026-10-06_08-37-58 | **当前运行中** |

### 7.3 git log（24h 内 19 commits）

```
e007a6c T2d: 裁决行 eval_end_ts checkpoint 兜底——首跑行自含评估窗锚
14fd980 docs: 正期望协变量搜索实施计划（P0-P5）
9ca48ac docs: spec 二次修订（宿主落地指示）
824b1fb docs: 正期望协变量搜索 spec 审核修订
9dccbbc fix(docs): 专家审核修订
f171874 docs: peer 学习反馈硬化 T0-T3 changelog
2089f1c T2c: 审计修复——success 门 checkpoint 解码异常面补全
4024506 fix(docs): 手册自审发现 3 处失效引用
42a919c docs: 技术规范手册 L0/L1 分层
7199738 docs: peer 学习反馈硬化计划 T0-T3 执行状态收口
739a583 T2b: 拒收信息带先验分类与 run_mode
318daca T2: 已成功组合的 success_delta 增量论证门
054de29 T1 注入通道硬化：known_verdicts 计数带分母
351efa6 fix: 恢复 praxist_assets_archive.py 可执行位
7f2f433 docs: 技术文档体系补全 + 7 处文档腐烂勘误
4165554 docs: T0 勘误三处 + 审核报告入库
0420513 docs: 按独立审核修订 peer 学习反馈硬化计划 v2
ee01b56 docs: peer 学习机制报告独立评审
a5c1412 docs: Peer 学习机制断裂分析
```

---

**报告生成**: 2026-10-06 ~10:00
**参与子 agent**: P0 根因分析（108k tokens / 66 tool-uses）、P1 部署核查（94k tokens / 47 tool-uses）、P2 数据运维（86k tokens / 37 tool-uses）
**总诊断成本**: 288k tokens / 150 tool-uses / ~30 分钟 wall-clock
**决策状态**: 待宿主裁定（§6 选项 A/B/C）
