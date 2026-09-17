# 审核代码债修复计划（C1–C8 先落地）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. After **each** task: commit, then dispatch a code reviewer. Fix Critical/Important before the next task.

**Goal:** 按 `docs/superpowers/reports/2026-09-11-audit/SUMMARY.md` 的代码列，先修会改错盘中建议或合同测试的项。不改 SCHEMES 协变量、不改 `evaluator.gate` 公式、不接回 diagnostic 收割。

**Architecture:** 活仓 WSL `/home/abug/timesfm`。C9–C12（ALIGN 合约、SPEC-011 复权、权重路径、rsi_state 分名）风险高且会改 PF/XReg，本计划**不含**，另开。

**Tech Stack:** Python 3.11 `.praxist-venv`，pytest，TimesFM 2.5。

**Spec:** 全系统审核 SUMMARY C1–C8；产品合同 CF-01 A；`get_safe_daily` 规则（`data/data_store.py`）。

## Global Constraints

- 路径：`wsl -d Ubuntu-22.04`，根 `/home/abug/timesfm`。禁止 `D:\FlyBuddy\timesfm`。
- TDD：先写失败测试，再改生产代码。
- 每个 Task 结束：相关 pytest 绿；`git commit`；**复审代码**（reviewer subagent）。Critical/Important 未关不得进下一 Task。
- 禁止：改 `config/prediction_scheme.py` 的 SCHEMES 值；给 `evaluator.gate` 加 EV；改 `STEP`；接回 `harvest_survivors` 主路径。
- `cascade/daily_model.py` 是高风险路径。本计划 Task 1 **只**把非 `BacktestDataStore` 的读日线换成 `get_safe_daily`。回测路径继续 `get_main_continuous`（已有 hour>=15）。
- 不要加载真 TimesFM 跑单测；mock 模型或抽纯函数测读框。
- 不 push，除非用户后来说提交推送。

C9–C12 明确不做（本计划）。

---

### Task 1: 实盘日线接线（C1 / CC-1）

**Files:**
- Modify: `cascade/daily_model.py`（`predict` 读框）
- Create: `tests/test_daily_model_live_frame.py`
- Test: `tests/test_daily_freshness.py` 仍绿；`tests/test_backtest_cutoff.py` 不得为了变绿去改回测实现

**Interfaces:**
- Consumes: `data.data_store.get_safe_daily(symbol, limit, now_dt, store)`
- Produces: 活 `DataStore` 上 `DailyModel.predict` 最后一根日线遵守 get_safe_daily 掩码；`BacktestDataStore` 行为不变

- [ ] **Step 1: 写失败测试**

`tests/test_daily_model_live_frame.py`：抽/测读框函数（不要实例化真 TimesFM）。

```python
def test_live_store_trims_unclosed_today_before_15():
    """活 DataStore、10:30、库尾含今日日线 → 读框不含今日。"""

def test_backtest_store_still_uses_get_main_continuous():
    """有 cutoff_date 的 store 不走 get_safe_daily。"""
```

失败原因：现在 `predict` 一律 `get_main_continuous`，10:30 仍含今日。

- [ ] **Step 2: 跑测试确认红**
- [ ] **Step 3: 最小实现**

`DailyModel.predict`：`hasattr(store, "cutoff_date")` → `get_main_continuous`；否则 `get_safe_daily(symbol, limit=context_days, store=store)`（可传 now 便于测）。

- [ ] **Step 4: 测试绿**（新测 + `test_daily_freshness.py` + 不得改坏 `test_backtest_cutoff` 的 hour>=15 行为）
- [ ] **Step 5: commit** `fix(cascade): live DailyModel.predict uses get_safe_daily`
- [ ] **Step 6: 代码复审**

---

### Task 2: 过期 cutoff 单测（C2）

**Files:**
- Modify: `tests/test_backtest_cutoff.py` 中 `test_daily_includes_cutoff_calendar_day`
- 不改 `BacktestDataStore`

- [ ] 10:00 cutoff **断言不含**当日日线；新增 15:00 **含**当日。
- [ ] `pytest tests/test_backtest_cutoff.py -q` 全绿
- [ ] commit `test: lock hour>=15 same-day daily cutoff`
- [ ] 代码复审

---

### Task 3: Copilot 可交易方向 = 加权 1H（C3）

**Files:**
- Modify: `scripts/copilot.py` `run_one` / 卡面 / CLI / 研报 / `generate_risk_bounds`
- Modify: `tests/test_copilot_advisory.py`（或新建）锁 CF-01 A
- 不改 `cascade/signal_contract.py` 的公式

- [ ] 失败测试：日线中性、1H 看多 → 卡面 direction 看多（对照 `test_signal_contract.py:67-77`）
- [ ] `run_one` 调 `position_from_forecast`；`direction` = 加权 1H；另存 `regime_direction`；`delta_pct` 用加权价；止损跟可交易方向
- [ ] 纸面 schema 若本任务动 ledger 会太大：加权价字段可标 TODO 留 Task 3b。**本 Task 至少改 Copilot 卡面/研报/止损。** 若不动 `live_ledger.py`，复审不得把「ledger 未迁」升为 Critical。
- [ ] commit + 复审

---

### Task 4: Copilot 全失败不再回退脏列表（C6）

**Files:** `scripts/copilot.py` 入口；对应测试

- [ ] `valid or symbols` 改为：无 valid 则停或只跑 valid（与 `cascade_predict` 同策略）
- [ ] commit + 复审

---

### Task 5: harvest schema 拒绝（C7）

**Files:** `scripts/praxist_supervisor.py` `harvest_proposals`；`tests/test_harvest_proposals.py`

- [ ] 非 `fm.hypothesis_proposal.v1` → reject `schema_mismatch`，入队失败
- [ ] 可顺手锁 `survivors_per_cycle` 读真实 goal=3（若测试易加）
- [ ] commit + 复审

---

### Task 6: materializer 三态（C4）

**Files:** `scripts/praxist_supervisor.py` known_verdicts 物化；`task_FM/prompt_base.jinja2`；测试夹具 `gate_pass=True, ev<0`

- [ ] 三态：经济过门 / 过硬门但亏钱 / DEAD。**不要**改 `evaluator.gate`
- [ ] commit + 复审

---

### Task 7: 关掉 peer 评估能力面（C5）

**Files:** `task_FM/task.yaml`；`task_FM/roles/peer_generalist/role.yaml`；提示词/审计规则；测试

- [ ] `diagnostic.launch_allowed: false`；去掉 peer `evaluation_tools`；锁测试
- [ ] 不改 Praxist 本体
- [ ] commit + 复审

---

### Task 8: 保证金 MaxDD 吃净 PnL（C8）

**Files:** `scripts/aligned_slow_loop.py` / `monthly_backtest.py` 传入保证金 MaxDD 的数组；测试

- [ ] 传入扣滑点后的净点值，不是 `position_sign * delta_real`
- [ ] 不进 `gate()`
- [ ] commit + 复审

---

## Execution notes

先提交已有文档对齐（单独 commit），再 Task 1。分支名 `feat/audit-code-fixes`。不在 master 上直接改代码。
