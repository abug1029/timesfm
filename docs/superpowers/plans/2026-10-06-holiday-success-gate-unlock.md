# 国庆 success_gate 死锁解锁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 数据末端相对上海日历超过 3 天时，同窗已成功组合的复跑不再因缺少 `success_delta` 被拒；市场恢复出新 bar 后该旁路自动关闭。同时把仍会被这道门拒收的 `(symbol, cov)` 写进 peer 已读的 `known_verdicts`。

**Architecture:** 只改监督环的成功门和它喂给 peer 的证据文件。旁路插在 `_success_delta_gate` 里、`window_moved` 之后：同窗且 kline 日历年龄 `> 3` 时返回新状态 `data_stale`（放行，`reject_reason is None`）。`materialize_known_verdicts` 用同一次门调用生成 `## Locked this window`，数据冻结时名单为空，避免提示词和门各说各话。不改评估窗锚，不改 checkpoint。

**Tech Stack:** Python 3.12、现有 `praxist_supervisor.py` 收获路径、`pytest`、只读 sqlite `kline_1h`、`zoneinfo.ZoneInfo("Asia/Shanghai")`。

**Spec:** `docs/superpowers/reports/2026-10-06-holiday-success-gate-deadlock-diagnosis.md`（§2 机制、§5 P0-1/P0-3、§6 选项 A）。本计划采纳 A，并记下两处相对报告原文的改法，见文末「和诊断报告的差异」。

**代码树:** WSL `/root/timesfm`，当前 `HEAD` `52132c3`。本机没有 supervisor 进程，也没有 `data/cache/supervisor_state.json`。诊断里的活进程在 `/home/abug/timesfm`，那份树不在这台 WSL 上。实现只改 `/root/timesfm`。重启活进程不在本计划的编码任务里。

## Global Constraints

- `SUCCESS_DELTA_MIN_CHARS` 保持 `20`（`scripts/praxist_supervisor.py:2000`）。
- 新常量 `STALE_DATA_DAYS = 3`。陈旧 ⟺ `(上海今日 − kline 日期).days > 3`。`== 3` 不放行。
- 日期用 `Asia/Shanghai` 的日历日，不用 `datetime.now()` 的裸本地时，也不用 `(now - bar).days` 的小时截断。
- 读不到库、空表、SQL 错误、日期解析失败：不放行，继续走原来的 `no_success_delta`。
- 旁路只跳过 `success_delta` 这一道。`mechanism` 长度、dedup、family dead、PR-B6 质量门一律不动。
- 新状态名是 `data_stale`，计入已有的 `stats["success_gate_states"]`。不要并进 `window_moved`。
- 每个 symbol、每次 harvest 的 cache 里，`data_stale` 的 WARNING 只打一条。
- 不调用 `cascade/data_validator.py` 的 `is_stale`。那个标志会减法定假日，国庆当天有效滞后可以是负数，正好打不开这道门。
- 不修改 `scripts/monthly_backtest.py` 的锚，不修改 `scripts/aligned_slow_loop.py` 的 checkpoint 读取，不删除、不重写任何 checkpoint 的 `eval_end_ts`。
- 不 push。不在这台 WSL 上启动或重启 supervisor。`git commit` 只在宿主明确要求后执行。
- 现有测试不得依赖本机 `futures_*.db` 的真实新旧。会走到同窗分支的测试必须把 kline 日期钉成「今天」。

## 决策

采纳诊断 §6 的 A：现在做 P0-1 和 P0-3。

P0-2（数据变长后清除 checkpoint 旧锚）不实施。`scripts/monthly_backtest.py:340-343` 写明评估窗口是锚的纯函数，数据增长后重跑不平移，用来堵住「发现 B」（同一 checkpoint 混进多段窗口）。resume 日志 `monthly_backtest.py:1188` 同样是「窗口钉住, 数据增长不平移」。清锚会把这个不变量拆掉。

10/8 之后旁路会自己结束，不靠清锚：

- 新 bar 的日期进入 3 天内 → `data_stale` 为假，同窗复跑恢复要求 `success_delta`。
- 没有旧 checkpoint 的新 variant，在 `eval_end_ts is None` 时把锚打成当前数据末端（`monthly_backtest.py:356-358`）。
- 这条新裁决进入 snapshot 后，`_current_window_anchor`（`praxist_supervisor.py:2284-2297`）取到更大的 `eval_end_ts`，旧成功的 `prior_ts != anchor`，原有 `window_moved` 放行。

所以假期锁死靠 P0-1 解开；开市后的窗口平移仍靠现有逃逸阀。两者交接的空档（已有新 bar、snapshot 里还没有更新的锚）恢复强制 `success_delta`。这是要保留的行为，用测试钉住。

## Review Focus

这五条是报告没写成测试、但实现时最容易错的输入。每条都挂在下面任务的测试上。

1. 周五收盘到下周一，日历差正好 3 天，门仍然拒收。任务 1：`test_age_three_days_still_rejects`。
2. 国庆这种日历差 6 天的冻结，空 `success_delta` 放行，且状态是 `data_stale`。任务 1：`test_national_day_gap_fail_open`。
3. kline 读失败时门保持拒收。任务 1：`test_unreadable_kline_stays_closed`。
4. 一个品种冻结、另一个品种仍新鲜时，只放行冻结的那个。任务 1：`test_stale_is_per_symbol`。
5. 门已经因 `data_stale` 放行时，`Locked this window` 必须是空名单。提示词若继续把组合写成「必须带 success_delta」，peer 会去补一门并不检查的字段。任务 2：`test_locked_section_empty_when_data_stale`。

## 文件

- 修改 `scripts/praxist_supervisor.py`：常量、三个助手、成功门、锁定名单、两处 `materialize_known_verdicts` 调用。
- 修改 `task_FM/prompt_base.jinja2:65`：规则 9 加一句，指向锁定名单。
- 修改 `tests/test_success_delta_gate_20261005.py` 的 `tmproot`：把 kline 钉成新鲜，避免假日机器上旧断言翻转。
- 新建 `tests/test_success_gate_stale_20261006.py`。
- 修改 `tests/test_known_verdicts_injection_20261005.py`：追加锁定名单测试。
- 不改 `scripts/monthly_backtest.py`、`scripts/aligned_slow_loop.py`。

---

### Task 1: 数据冻结旁路

**Files:**

- Modify: `scripts/praxist_supervisor.py:1999-2000`（常量旁）
- Modify: `scripts/praxist_supervisor.py:2300-2340`（`_success_delta_gate`）
- Modify: `tests/test_success_delta_gate_20261005.py` 的 `tmproot`
- Create: `tests/test_success_gate_stale_20261006.py`

**Interfaces:**

- Consumes: `_prior_success_row`、`_row_eval_end_ts`、`_current_window_anchor`、`SUCCESS_DELTA_MIN_CHARS`。
- Produces:
  - `STALE_DATA_DAYS: int = 3`
  - `_today_shanghai() -> datetime.date`
  - `_kline_1h_max_dt(symbol: str) -> str | None`
  - `_symbol_data_stale(symbol: str, cache: dict) -> bool`
  - `_prior_success_class(prior: dict) -> str`，取值只可能是 `v2-pass` 或 `hard-gate-but-losing`，条件与今天 WARNING 里的三元表达式相同（`fdr_pass` 且 `p_value is not None` 且 `run_mode == "confirmation"` → `v2-pass`）。
  - `_success_delta_gate` 增加状态 `data_stale`：返回 `(None, "data_stale")`。
  - cache 键：`_kline_max` 为 `{symbol: str | None}`，`_stale_logged` 为 `set[str]`。不得占用已有的 `anchor` 和 `_row_ts`。

- [ ] **Step 1: 写会失败的测试**

新建 `tests/test_success_gate_stale_20261006.py`。复用 `test_success_delta_gate_20261005.py` 里的 `_prop`、`_sv`、`_make_run`、`_harvest`、`tmproot` 会连带把 kline 钉死，所以这个新文件自己建一个不钉 kline 的 fixture，只复制指纹、baseline、symbol status 这三处 monkeypatch（照旧文件 `tmproot`）。测试里再钉 `_kline_1h_max_dt` 和 `_today_shanghai`。

断言：

```python
def test_national_day_gap_fail_open(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-09-30 14:00:00")
    prior = _sv("rb_volatility_prior", "rb", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    _make_run(tmproot, _prop(symbol="rb", cov="vor"))
    rows, stats = _harvest(tmproot, snap={"rb_volatility_prior": prior})
    assert stats["success_gate_states"]["data_stale"] == 1
    assert "no_success_delta" not in stats["success_gate_states"]
    assert "no_success_delta" not in stats["reject_reasons"]
    assert len(rows) == 1


def test_age_three_days_still_rejects(tmproot, monkeypatch):
    # 2026-10-10 是周五，2026-10-13 是周一，日历差 3。
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 13))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-10-10 14:00:00")
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-10-10 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert reason == "no_success_delta"
    assert state == "no_success_delta"


def test_age_four_days_opens(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 14))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-10-10 14:00:00")
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-10-10 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert reason is None
    assert state == "data_stale"


def test_fresh_bar_same_anchor_still_rejects(tmproot, monkeypatch):
    # 已有新 bar，snapshot 锚仍是旧值：旁路结束，window_moved 还没发生。
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert (reason, state) == ("no_success_delta", "no_success_delta")


def test_window_moved_does_not_read_kline(tmproot, monkeypatch):
    def _boom(symbol):
        raise AssertionError("window_moved 不应读 kline")
    monkeypatch.setattr(S, "_kline_1h_max_dt", _boom)
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-23 15:00:00")
    other = _sv("jd_volatility_other", "jd", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor",
        {"m_volatility_prior": prior, "jd_volatility_other": other},
        tmproot, cache={})
    assert (reason, state) == (None, "window_moved")


def test_unreadable_kline_stays_closed(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: None)
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert (reason, state) == ("no_success_delta", "no_success_delta")


def test_stale_is_per_symbol(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))
    def _max(symbol):
        return "2026-09-30 14:00:00" if symbol == "rb" else "2026-10-06 14:00:00"
    monkeypatch.setattr(S, "_kline_1h_max_dt", _max)
    rb = _sv("rb_volatility_prior", "rb", "vor", gate_pass=True,
             eval_end_ts="2026-09-30 15:00:00")
    # m 的锚也停在同一天，但 m 的 kline 是今天，不放行。
    m = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
            eval_end_ts="2026-09-30 15:00:00")
    snap = {"rb_volatility_prior": rb, "m_volatility_prior": m}
    cache = {}
    assert S._success_delta_gate(_prop(symbol="rb"), "rb", "vor", snap, tmproot, cache)[1] == "data_stale"
    assert S._success_delta_gate(_prop(), "m", "vor", snap, tmproot, cache)[1] == "no_success_delta"


def test_stale_warning_once_per_symbol(tmproot, monkeypatch, caplog):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-09-30 14:00:00")
    prior = _sv("rb_volatility_prior", "rb", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    snap = {"rb_volatility_prior": prior}
    cache = {}
    with caplog.at_level(logging.WARNING):
        S._success_delta_gate(_prop(symbol="rb"), "rb", "vor", snap, tmproot, cache)
        S._success_delta_gate(_prop(symbol="rb", cov="oi"), "rb", "oi", snap, tmproot, cache)
    warns = [r for r in caplog.records if "data_stale" in r.getMessage()]
    assert len(warns) == 1
    assert "rb" in warns[0].getMessage()
    assert "2026-09-30" in warns[0].getMessage()
    assert "6" in warns[0].getMessage()
```

`_prop(symbol="rb")` 要能覆盖 symbol。旧 `_prop` 已支持 `**over`，直接传 `symbol="rb"`。`oi` 若被 active pool 拒绝，`test_stale_warning_once_per_symbol` 走的是门函数而不是 harvest，不经过 pool。`test_national_day_gap_fail_open` 走 harvest，`cov` 必须用池内已有的 `vor`（旧测试已用它）。

旧文件 `tmproot` 末尾追加：

```python
monkeypatch.setattr(S, "_today_shanghai", lambda: date(2099, 1, 1))
monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2099-01-01 14:00:00")
```

这样 `test_gate_rejects_rerun_without_success_delta` 在活数据库停在 09-30 的机器上仍然拒收。

- [ ] **Step 2: 跑新测试，确认失败**

```bash
cd /root/timesfm && .venv/bin/python -m pytest tests/test_success_gate_stale_20261006.py -q
```

若没有 `.venv`，用 `python3 -m pytest`。预期：`_today_shanghai` / `_symbol_data_stale` 不存在，或同窗用例仍返回 `no_success_delta`。`test_window_moved_does_not_read_kline` 在实现前就会读 kline 或直接走 `window_moved`；实现前允许它失败，实现后必须过。

- [ ] **Step 3: 实现助手和门**

在 `SUCCESS_DELTA_MIN_CHARS = 20` 下一行加 `STALE_DATA_DAYS = 3`。

`_kline_1h_max_dt(symbol)`：`data.config.get_db_path(symbol)`，`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`，`SELECT MAX(dt) FROM kline_1h`。文件不存在、`sqlite3.Error`、`MAX` 为 `NULL` → `None`。不要用 `DataStore`，不要建库。

`_symbol_data_stale(symbol, cache)`：按 symbol 缓存原始 `MAX(dt)`。取前 10 字符 `%Y-%m-%d`。`age > STALE_DATA_DAYS` 才为真。为真时 WARNING 一次，句子固定为：

```text
success_gate: {symbol} 数据末端 {max_dt} 距上海日历 {today} 已 {age} 天 > {STALE_DATA_DAYS} → data_stale 放行
```

`_success_delta_gate` 在 `if prior_ts != anchor: return None, "window_moved"` 之后、读取 `success_delta` 之前：

```python
if _symbol_data_stale(symbol, cache):
    return None, "data_stale"
```

把 WARNING 里的分类三元表达式换成 `_prior_success_class(prior)`。日志其余字段不变。

函数 docstring 的状态列表加上 `data_stale`。删掉「不用墙钟」这句对这条新路径的覆盖；保留 `window_moved` / `anchor_unavailable` 仍然不看时钟。

- [ ] **Step 4: 新测试和旧成功门测试一起过**

```bash
cd /root/timesfm && python3 -m pytest tests/test_success_gate_stale_20261006.py tests/test_success_delta_gate_20261005.py -q
```

预期：全部 PASS。

- [ ] **Step 5: 提交**

只在宿主要求提交时执行。消息：`fix(v4): 数据冻结超过 3 天时 success_delta 门 fail-open`。不要把 checkpoint 或数据库文件加进去。

---

### Task 2: 锁定名单与提示词一致

**Files:**

- Modify: `scripts/praxist_supervisor.py` 的 `materialize_known_verdicts`，以及约 `3634`、`3724` 两处调用
- Modify: `task_FM/prompt_base.jinja2:65`
- Modify: `tests/test_known_verdicts_injection_20261005.py`

**Interfaces:**

- Consumes: Task 1 的 `_success_delta_gate`、`_prior_success_class`、`data_stale`。
- Produces:
  - `LOCKED_WINDOW_MAX_ROWS: int = 40`，放在 `CROSS_MATRIX_MAX_ROWS` 旁边。
  - `_locked_success_rows(snapshot, root, cache=None) -> list[dict]`。元素是「空 `success_delta` 的复跑会被拒」的那条 prior 裁决，每个 `(symbol, cov_override)` 一条，即 `_success_delta_gate` 返回 `("no_success_delta", "no_success_delta")` 的 prior。`data_stale`、`window_moved`、`anchor_unavailable`、`no_prior_success` 都不进名单。
  - `materialize_known_verdicts` 在 `## Do not re-propose` 之前写入锁定段。

- [ ] **Step 1: 写会失败的测试**

追加到 `tests/test_known_verdicts_injection_20261005.py`，用已有 `_v` 和 `_write`。行上要有 `eval_end_ts`。测试自己 monkeypatch `_today_shanghai` 和 `_kline_1h_max_dt`。

```python
def test_locked_section_lists_same_window_combo(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    row = _v("rb_basis_1", "rb", "basis_momentum", "basis", gate_pass=True)
    row["eval_end_ts"] = "2026-09-30 15:00:00"
    text = _write(tmp_path, {"rb_basis_1": row})
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert "rb cov=basis_momentum prior=rb_basis_1 class=hard-gate-but-losing eval_end_ts=2026-09-30 15:00:00" in sec
    assert sec.index("## Locked this window") if False else True
    assert text.index("## Locked this window") < text.index("## Do not re-propose")


def test_locked_section_empty_when_data_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-09-30 14:00:00")
    row = _v("rb_basis_1", "rb", "basis_momentum", "basis", gate_pass=True)
    row["eval_end_ts"] = "2026-09-30 15:00:00"
    text = _write(tmp_path, {"rb_basis_1": row})
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert "- (none)" in sec
    assert "basis_momentum" not in sec


def test_locked_section_uses_checkpoint_when_row_has_no_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    row = _v("rb_basis_1", "rb", "basis_momentum", "basis", gate_pass=True,
             run_mode="confirmation")
    row["fdr_pass"] = True
    row["p_value"] = 0.01
    cp = tmp_path / "data" / "cache" / "aligned_checkpoints"
    cp.mkdir(parents=True)
    (cp / "rb_basis_1.jsonl").write_text(
        json.dumps({"eval_end_ts": "2026-09-30 15:00:00"}) + "\n",
        encoding="utf-8")
    text = _write(tmp_path, {"rb_basis_1": row}, root=str(tmp_path))
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert "class=v2-pass" in sec
    assert "eval_end_ts=2026-09-30 15:00:00" in sec


def test_locked_section_truncates_at_40(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(sup, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    snap = {}
    for i in range(41):
        vid = "s%02d_basis" % i
        row = _v(vid, "s%02d" % i, "basis_momentum", "basis", gate_pass=True)
        row["eval_end_ts"] = "2026-10-08 15:00:00"
        snap[vid] = row
    text = _write(tmp_path, snap)
    sec = text.split("## Locked this window", 1)[1].split("\n## ", 1)[0]
    assert sum(1 for ln in sec.splitlines() if ln.startswith("- ")) == 40
    assert "locked_window_truncated=1" in sec
```

`test_locked_section_lists_same_window_combo` 里那行 `assert sec.index(...) if False` 不要写进文件。位置断言只保留 `text.index("## Locked this window") < text.index("## Do not re-propose")`。

- [ ] **Step 2: 跑这四个测试，确认失败**

```bash
cd /root/timesfm && python3 -m pytest tests/test_known_verdicts_injection_20261005.py -q -k locked
```

预期：FAIL，输出里还没有 `## Locked this window`。

- [ ] **Step 3: 实现名单和提示词**

`_locked_success_rows(snapshot, root, cache=None)`：扫 snapshot 里 `status=="ok"` 且 `gate_pass` 的行，按 `(symbol.lower(), cov_override)` 去重后对每个组合调用 `_success_delta_gate({"success_delta": ""}, symbol, cov, snapshot, root, cache)`。只收集状态为 `no_success_delta` 的 prior。排序键：`symbol`，再 `cov_override`。

`materialize_known_verdicts` 在写出 `## Do not re-propose` 之前插入：

```text
## Locked this window
同评估窗已有 gate_pass=True 的 (symbol, cov)。复跑必须写 success_delta（≥20 字）并点名 prior。空 success_delta 会被拒 (no_success_delta)。数据末端距上海日历超过 3 天时此名单为空。
- {symbol} cov={cov} prior={variant_id} class={class} eval_end_ts={prior_ts}
```

没有命中时唯一的列表行是 `- (none)`。超过 `LOCKED_WINDOW_MAX_ROWS` 时只写前 40 行，并加 `locked_window_truncated={剩余条数}`。这段不要写 `datetime.now()`，否则会破坏 `test_idempotent_rewrite_except_generated_at`。

两处调用补上 `root=FM_ROOT`：慢环物化（约 3634 行）和主循环物化（约 3724 行）。单元测试不传 `root` 时保持 `None`，不去读仓库里的真实 checkpoint。

`task_FM/prompt_base.jinja2` 规则 9 末尾加这一句：

```text
当前窗口被锁的组合见下文 Locked this window；该名单为空时不要为了过门去补 success_delta。
```

- [ ] **Step 4: 注入测试与成功门测试一起过**

```bash
cd /root/timesfm && python3 -m pytest tests/test_known_verdicts_injection_20261005.py tests/test_success_gate_stale_20261006.py tests/test_success_delta_gate_20261005.py tests/test_eval_end_ts_backfill_20261005.py -q
```

预期：全部 PASS。

再确认锚文件没有被改到：

```bash
cd /root/timesfm && git diff --stat -- scripts/monthly_backtest.py scripts/aligned_slow_loop.py
```

预期：无输出。

- [ ] **Step 5: 提交**

只在宿主要求提交时执行。消息：`fix(v4): known_verdicts 列出同窗锁定组合`。

---

## 编码完成后的检查

- `python3 -m pytest` 跑上面四份测试文件，退出码 0。
- `git diff -- scripts/monthly_backtest.py scripts/aligned_slow_loop.py` 为空。
- `git diff -G 'eval_end_ts' -- scripts/monthly_backtest.py scripts/aligned_slow_loop.py` 为空。
- 搜 `data_stale`，只出现在成功门、锁定名单和对应测试里。

## 活进程部署（编码任务之外，要宿主另一次确认）

这台 WSL 的 `/root/timesfm` 不是诊断里那个正在跑的进程。活路径是 `/home/abug/timesfm`（`supervisor_state.json` 的 `last_run_dir`）。代码合并过去之后，按 `docs/three_loop_restart_protocol.md` 的快速重启：

```bash
cd /home/abug/timesfm
bash scripts/restart_three_loop_clean.sh
```

重启后看下一轮 `data/cache/supervisor.out`：

- 假期数据仍停在 `2026-09-30` 时，同窗复跑记 `data_stale`，不再刷 `no_success_delta`。
- `task_FM/known_verdicts.inc.md` 出现 `## Locked this window`。冻结期末尾是 `- (none)`。
- 10/8 第一根新 1h bar 写入之后，`data_stale` 停止；同窗复跑恢复 `no_success_delta`，锁定名单重新列出这些组合。

本计划的执行不跑这台重启。

## 和诊断报告的差异

- 报告写「降级为 `window_moved`」。计划用独立状态 `data_stale`。放行行为一样，计数能把假日旁路和真实窗口平移分开。
- 报告写把陈旧判断插在 `prior_ts != anchor` 之前。计划放在该判断之后。窗口已经平移时不再读 sqlite，`window_moved` 的含义不变。
- 报告的 P0-2 不实施。理由见「决策」。
- 不复用 `data_validator` 的滞后天数。`count_holidays_between(2026-09-30, 2026-10-08) == 7`（`tests/test_holidays.py`），减完假日之后国庆当天不会被标成 stale。成功门要识别的是「末端冻结」，不是「采集故障」。

## 风险

- 周一休市、周二早盘还没有新 bar 时，周五到周二日历差为 4，旁路会开一个上午。只跳过 `success_delta`，其他拒收还在。阈值若改成 `> 4`，国庆前两天（10/4，差 4 天）又打不开，所以保持 `> 3`。
- kline 里若有未来日期，年龄为负，旁路关闭，门维持原样。
- 锁定名单是提示，不是第二道硬门。硬拒收仍只有 `_success_delta_gate`。名单的验收标准是段落内容，不是 LLM 调用次数下降。
- 旧协议行没有行内 `eval_end_ts` 时，名单靠 checkpoint 兜底，因此两处物化调用必须传入 `root=FM_ROOT`。测试不传 `root`，避免读到开发机上的真实 checkpoint。
