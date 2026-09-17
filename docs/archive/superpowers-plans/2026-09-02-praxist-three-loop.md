# FM_a PRAXIST 三环自治架构 实施计划

> **2026-09-11：历史施工单，已落地，勿再执行。** 空框不表示未实现。活合同见 `docs/praxist.md`、runbook、方案 A spec。绑定解释第 4 条（diagnostic survivors / `evaluation_summary.json`）**作废**，现行 harvest 是 `harvest_proposals` / `proposals/*.json`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 落地三环自治系统: 监督环按 goal.yaml 自主编排 praxist 快环与 aligned 慢环, 无人值守直到目标达成或预算耗尽。

**Architecture:** 快环 (praxist run, LLM 探索+诊断筛选) 产幸存者; 慢环 (纯 CPU) 用 daily 预测缓存 + checkpoint 断点跑 aligned 全量评估并写 verdict 注册表; 监督环 (0 token) 读 goal.yaml 判定 success/budget、调度两环、收割入队。三环以 append-only 文件为唯一总线。

**Tech Stack:** Python 3.12 (/root/timesFM_fu/.venv), pytest, praxist 0.5.0 (/root/.praxist-venv), monthly_backtest.py 现有管线, flock 文件锁。

**Spec:** docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md

## Global Constraints

- 禁改: cascade/, data/config.py, config/prediction_scheme.py, task_FM/evaluations/fm_eval/evaluator.py 的既有契约 (只可加不改), praxist 核心 (site-packages)
- venv: 所有测试/实现用 /root/timesFM_fu/.praxist-venv/bin/python; praxist 命令用 /root/.praxist-venv/bin/praxist
- 测试: pytest tests/ 全绿是每个任务的完成条件 (当前基线 531 passed)
- 本仓库无 git: 每个 Task 以追加 ultragoal 台账 checkpoint 替代 commit:
  cat >> /root/timesFM_fu/.omc/ultragoal/20260901-praxist/ledger.jsonl
- 缓存与队列落 data/cache/ (只增不删)
- aligned 队列行 schema: {"variant_id","symbol","cov_override","max_points","stage":"aligned","checkpoint_path","enqueued_at","src_run"}
  variant_id = "{symbol}_{cov_override}" (与诊断档 pN 无关, p3/p6 同一候选)
- 队列 claim 协议 (0 损失): pending.jsonl 只在 queue_claim 时把队首移入 aligned_pending.inprogress.jsonl; 评估完成 queue_ack 才进 done。慢环启动先 queue_recover 把 inprogress 前置回 pending。禁止 take-then-delete-before-eval。
- verdict 行 schema: {"variant_id","symbol","cov_override","max_points","n","pf","ev","maxdd","dir_acc","gate_pass","ic","decided_at","checkpoint_path","slow_loop_pid","git_rev","schema":"fm.aligned_verdict.v1","status"}
  status=ok 才是终裁; status=no_data 可重试, 不得进入 dead_variants
- cycle = 一次已结束的 praxist run (含随后一次 harvest), 不是 300s poll。cycles_done 持久化在 data/cache/supervisor_state.json
- 监督环单实例锁: flock data/cache/supervisor.lock (与慢环锁分开)
- DailyResult 字段名是 forecast, 不是 spec 误写的 point_forecast (cascade/daily_model.py:23)

## Spec 绑定解释 (与 spec 原文冲突时以本箱为准)

Spec 意图保留; 下列机械描述已被本计划纠正, 执行者不要按 spec 过时句子实现:

1. cycle 计数: spec「快环一次 + 慢环清队列」= 一次已完成 praxist run。禁止 `sleep(300); cycles += 1`。
2. 429: spec §6「stop → 重置后 resume 同一 run_dir」。禁止 429 后 `praxist start` 新 run。窗口: 封禁期 (now < reset) 不可 start; 解封后剩余配额窗 (quota_window_hours 默认 5h, 从 reset 起算) >= run_budget_hours+quota_margin_min 才 start/resume; 否则 sleep 到下一重置点。
3. 慢环队列: spec「取队首并重写剩余」改为 claim/inprogress, 以满足同一节「SIGTERM 0 损失」。
4. harvest: **本条旧句作废**（diagnostic survivors / `evaluation_summary.json` 不是现行源）。现行：`harvest_proposals` 收割 `task_FM/experiments/run_*/results/**/proposals/*.json`（每 cycle 重扫全部 run，dead/passing/in-flight 去重）；身份 (symbol, cov_override)；`max_points` 来自 `goal.cadence.aligned_max_points`；0 份合格提案必须 log `harvest_empty`。旧 `harvest_survivors` 仅回滚。
5. 指纹: 权重 shard 的 (path, size, mtime) 变化即重算, 不是「.model_fp 存在就永不重算」。
6. incumbent PF: 从 config/knowledge_base.json historical_pf 读 (SCHEMES 无 PF 字段)。
7. --dry-run: 一轮打印 {action,reason,refs}, 不 sleep、不加 cycle、不写队列/不启进程, 然后退出。
8. 停机: goal_reached / budget_exhausted 必须写 docs/superpowers/reports/ 并追加 STATE.md。
9. DSL snapshot 必须含 variants (按 variant_id 最新行)。min/max 空序列 = unmet, 不是 eval error。
10. Known verdicts: 每次 start/resume 前写 task_FM/known_verdicts.inc.md; prompt_base.jinja2 `{% include %}` (praxist FileSystemLoader 根为 task_FM/, include 同胞文件可用)。验收断言渲染结果含真实 variant_id 与 gate_pass=。

---

### Task 1: daily 预测缓存 (monthly_backtest.py)

**Files:**
- Modify: scripts/monthly_backtest.py (run_symbol_backtest 及其模块级 helper 区)
- Create: tests/conftest.py (注册 slow 标记; 已有 tests/test_a2_p1_baseline.py 使用 @pytest.mark.slow 但仓库无 marker 定义)
- Test: tests/test_daily_pred_cache.py

tests/conftest.py:
```python
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: 真模型/真数据集成测试 (分钟级), 常规回归用 -m 'not slow' 排除")
```

**Interfaces:**
- Consumes: cascade/daily_model.py DailyModel.predict() -> DailyResult (字段: symbol, forecast, horizon_slope, historical_closes, historical_dates)
- Produces: run_symbol_backtest(..., daily_cache_dir: str | None = None);
  _model_fingerprint(cache_dir, weights_dir=None) -> str;
  _daily_predict_cached(...) -> DailyResult。
  缓存 payload 不得直接 pickle DailyResult (DatetimeIndex tz 会漂, 小时级协变量映射会静默错)。存 dict: forecast/closes 为 ndarray, historical_dates 为 tz-naive YYYY-MM-DD 字符串列表。

- [ ] Step 1: 写失败测试 tests/test_daily_pred_cache.py

```python
import os, pickle, sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from monthly_backtest import (
    _daily_cache_path, _model_fingerprint, _daily_predict_cached,
    _load_daily_cache, _save_daily_cache,
)

def _fake_weights(tmp_path, name="model.safetensors", blob=b"W" * 64):
    p = tmp_path / name
    p.write_bytes(blob)
    return str(tmp_path)

def test_cache_key_contains_symbol_cutoff_window(tmp_path):
    fp = _model_fingerprint(str(tmp_path / "c"), weights_dir=_fake_weights(tmp_path / "w"))
    p1 = _daily_cache_path(str(tmp_path / "c"), "m", "2021-01-05 14:00:00", "250x22", fp)
    p2 = _daily_cache_path(str(tmp_path / "c"), "m", "2021-01-06 09:00:00", "250x22", fp)
    assert p1 != p2 and "m" in os.path.basename(p1)

def test_fingerprint_stable_then_invalidates_on_mtime(tmp_path, monkeypatch):
    wdir = tmp_path / "w"
    cache = str(tmp_path / "c")
    monkeypatch.setenv("TIMESFM_WEIGHTS_DIR", _fake_weights(wdir))
    fp1 = _model_fingerprint(cache)
    fp2 = _model_fingerprint(cache)
    assert fp1 == fp2 and len(fp1) == 12
    # 改 shard 内容+mtime → 必须换 fp (禁止 .model_fp 永缓存)
    shard = wdir / "model.safetensors"
    shard.write_bytes(b"V" * 64)
    os.utime(shard, (os.path.getmtime(shard) + 10, os.path.getmtime(shard) + 10))
    fp3 = _model_fingerprint(cache)
    assert fp3 != fp1

def test_roundtrip_dates_tz_naive(tmp_path):
    from cascade.daily_model import DailyResult
    r = DailyResult(
        symbol="m", forecast=np.arange(22.0),
        horizon_slope=-0.01, historical_closes=np.arange(250.0),
        historical_dates=pd.DatetimeIndex(["2020-12-01", "2020-12-02"]),
    )
    _save_daily_cache(str(tmp_path), "m", "2021-01-05 14:00:00", "250x22", "abc123", r)
    got = _load_daily_cache(str(tmp_path), "m", "2021-01-05 14:00:00", "250x22", "abc123")
    assert np.array_equal(got.forecast, r.forecast)
    assert np.array_equal(got.historical_closes, r.historical_closes)
    assert list(pd.DatetimeIndex(got.historical_dates).strftime("%Y-%m-%d")) == ["2020-12-01", "2020-12-02"]
    assert getattr(got.historical_dates, "tz", None) is None
```

- [ ] Step 2: 运行确认失败
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_daily_pred_cache.py -v -m "not slow"
Expected: FAIL with ImportError (_daily_cache_path not defined)

- [ ] Step 3: 实现 (monthly_backtest.py 模块级, run_symbol_backtest 之前)

```python
import pickle
import json as _json

_DAILY_CACHE_VER = "v2"  # v2 = dates 为 tz-naive ISO 列表, 不再 pickle DailyResult

def _weight_shards(weights_dir):
    import glob as _glob
    base = weights_dir or os.environ.get("TIMESFM_WEIGHTS_DIR") or os.path.expanduser(
        "~/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots")
    snaps = sorted(_glob.glob(os.path.join(base, "*", "*.safetensors")))
    if not snaps:
        snaps = sorted(_glob.glob(os.path.join(base, "*.safetensors")))
    if not snaps:
        raise RuntimeError("daily cache: model weights not found for fingerprint (set TIMESFM_WEIGHTS_DIR)")
    return snaps

def _model_fingerprint(cache_dir, weights_dir=None):
    import hashlib
    os.makedirs(cache_dir, exist_ok=True)
    shards = _weight_shards(weights_dir)
    sig = [[os.path.abspath(p), os.path.getsize(p), int(os.path.getmtime(p))] for p in shards]
    meta = os.path.join(cache_dir, ".model_fp.json")
    if os.path.exists(meta):
        try:
            old = _json.load(open(meta, encoding="utf-8"))
            if old.get("sig") == sig and old.get("fp"):
                return old["fp"]
        except Exception:
            pass
    h = hashlib.sha256()
    for sp in shards:
        with open(sp, "rb") as f:
            h.update(f.read(1 << 24))
    fp = h.hexdigest()[:12]
    with open(meta, "w", encoding="utf-8") as f:
        _json.dump({"fp": fp, "sig": sig}, f)
    return fp

def _daily_cache_path(cache_dir, symbol, cutoff, win, fp):
    import hashlib as _hl
    key = _hl.sha256("|".join([_DAILY_CACHE_VER, symbol, cutoff, win, fp]).encode()).hexdigest()
    return os.path.join(cache_dir, f"daily_{symbol}_{key[:16]}.pkl")

def _result_to_payload(result):
    dates = getattr(result, "historical_dates", None)
    iso = None if dates is None else [str(pd.Timestamp(d))[:10] for d in dates]
    return {
        "symbol": result.symbol,
        "forecast": np.asarray(result.forecast),
        "horizon_slope": float(result.horizon_slope),
        "historical_closes": np.asarray(result.historical_closes),
        "historical_dates": iso,
    }

def _payload_to_result(payload):
    from cascade.daily_model import DailyResult
    dates = payload.get("historical_dates")
    idx = pd.DatetimeIndex(dates) if dates is not None else None
    if idx is not None and idx.tz is not None:
        idx = idx.tz_localize(None)
    return DailyResult(
        symbol=payload["symbol"], forecast=payload["forecast"],
        horizon_slope=payload["horizon_slope"],
        historical_closes=payload["historical_closes"],
        historical_dates=idx,
    )

def _load_daily_cache(cache_dir, symbol, cutoff, win, fp):
    p = _daily_cache_path(cache_dir, symbol, cutoff, win, fp)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "rb") as f:
            obj = pickle.load(f)
        if isinstance(obj, dict) and "forecast" in obj:
            return _payload_to_result(obj)
        os.remove(p)  # 旧 v1 DailyResult pickle, 丢弃重算
        return None
    except Exception:
        try:
            os.remove(p)
        except OSError:
            pass
        return None

def _save_daily_cache(cache_dir, symbol, cutoff, win, fp, result):
    p = _daily_cache_path(cache_dir, symbol, cutoff, win, fp)
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(_result_to_payload(result), f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, p)

def _daily_predict_cached(daily_model, symbol, cutoff, context_days, horizon_days, cache_dir, store):
    if not cache_dir:
        return daily_model.predict(symbol, store, context_days=context_days, horizon_days=horizon_days)
    win = f"{context_days}x{horizon_days}"
    fp = _model_fingerprint(cache_dir)
    hit = _load_daily_cache(cache_dir, symbol, cutoff, win, fp)
    if hit is not None:
        return hit
    result = daily_model.predict(symbol, store, context_days=context_days, horizon_days=horizon_days)
    _save_daily_cache(cache_dir, symbol, cutoff, win, fp, result)
    return result
```

- [ ] Step 4: run_symbol_backtest 接入缓存

签名加 `daily_cache_dir=None`。点循环内两处
`daily_result = daily_model.predict(symbol, bt_store, context_days=CONTEXT_DAYS, horizon_days=HORIZON_DAYS)`
改为:
`daily_result = _daily_predict_cached(daily_model, symbol, cutoff, CONTEXT_DAYS, HORIZON_DAYS, daily_cache_dir, bt_store)`
(cutoff 在循环内已定义为 bar_ts.strftime("%Y-%m-%d %H:%M:%S"); 每个点已 `bt_store = BacktestDataStore(symbol, cutoff)`)

- [ ] Step 5: 跑测试确认通过 (排除 slow)
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_daily_pred_cache.py -v -m "not slow"
Expected: 3 PASS

- [ ] Step 6: A/B 逐位验证 (slow, 真模型; 每 cutoff 独立 store; 测 miss + HIT + live)

```python
@pytest.mark.slow
def test_ab_bitexact(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cascade.daily_model import DailyModel
    from data.data_store import BacktestDataStore
    from monthly_backtest import _daily_predict_cached
    d = DailyModel()
    calls = {"n": 0}
    real_predict = d.predict
    def wrapped(*a, **k):
        calls["n"] += 1
        return real_predict(*a, **k)
    monkeypatch.setattr(d, "predict", wrapped)
    cache = str(tmp_path)
    cutoffs = ["2021-01-05 14:00:00", "2021-01-11 09:00:00", "2021-01-14 13:00:00"]
    for c in cutoffs:
        store = BacktestDataStore("m", c)
        try:
            r_live = real_predict("m", store, context_days=250, horizon_days=22)
            n_before = calls["n"]
            r_miss = _daily_predict_cached(d, "m", c, 250, 22, cache, store)
            r_hit = _daily_predict_cached(d, "m", c, 250, 22, cache, store)
            assert calls["n"] == n_before + 1  # HIT 不得再 predict
            for r in (r_miss, r_hit):
                assert np.array_equal(r.forecast, r_live.forecast), f"forecast mismatch {c}"
                assert np.array_equal(r.historical_closes, r_live.historical_closes)
                assert abs(r.horizon_slope - r_live.horizon_slope) < 1e-12
                live_d = pd.DatetimeIndex(r_live.historical_dates).strftime("%Y-%m-%d")
                hit_d = pd.DatetimeIndex(r.historical_dates).strftime("%Y-%m-%d")
                assert list(hit_d) == list(live_d)
        finally:
            if hasattr(store, "close"):
                store.close()
```

Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_daily_pred_cache.py::test_ab_bitexact -v
Expected: PASS

- [ ] Step 7: 全量回归 + 台账 checkpoint
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/ -q -m "not slow"
Expected: 全绿 (531 + 新增)
台账:
```
cat >> .omc/ultragoal/20260901-praxist/ledger.jsonl <<'LEDGER'
{"ts":"<now>+08:00","event":"checkpoint","story":"P1","status":"complete","evidence":"daily cache v2 payload; fingerprint invalidates on shard mtime; A/B miss+HIT+live per-cutoff store"}
LEDGER
```

---

### Task 2: verdict 注册表与队列库 (scripts/registry_lib.py)

**Files:**
- Create: scripts/registry_lib.py
- Test: tests/test_verdict_registry.py

**Interfaces:**
- Produces:
  append_verdict(registry_fp, verdict) -> None
  load_snapshot(path) -> dict[variant_id -> 最新 verdict]
  pass_variants(snapshot) -> list[dict]  # status==ok (或缺省) 且 gate_pass 且 ev>0
  dead_variants(snapshot) -> set[str]    # 仅 status==ok 且 gate_pass is False; no_data 不是死
  queue_load(path) -> list[dict]
  queue_enqueue(path, rows, dead, existing) -> int
  queue_claim(pending_path, inprogress_path) -> dict | None
    锁内: 若 inprogress 已有行, 返回其队首 (崩溃恢复由 queue_recover 先做);
    否则把 pending 队首移入 inprogress, pending 写剩余。
  queue_ack(pending_path, inprogress_path, row, done_path) -> None  # 从 inprogress 去掉该 variant_id, 追加 done
  queue_recover(pending_path, inprogress_path) -> int  # 把 inprogress 整列前置回 pending 并清空 inprogress, 返回移回行数
  in_flight_ids(pending_path, inprogress_path) -> set[str]
  validate_verdict(v) -> list[str]

- [ ] Step 1: 写失败测试

```python
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from registry_lib import (
    append_verdict, load_snapshot, pass_variants, dead_variants,
    queue_enqueue, queue_claim, queue_ack, queue_recover, queue_load,
    in_flight_ids, validate_verdict,
)

def _v(vid, **kw):
    base = {"variant_id": vid, "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "n": 380, "pf": 1.2, "ev": 0.02, "maxdd": -0.1,
            "dir_acc": 0.55, "gate_pass": True, "ic": 0.1, "decided_at": "t",
            "checkpoint_path": "cp", "slow_loop_pid": 1, "git_rev": "-",
            "schema": "fm.aligned_verdict.v1", "status": "ok"}
    base.update(kw); return base

def _row(vid="v1"):
    return {"variant_id": vid, "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "stage": "aligned", "checkpoint_path": "cp/v1.jsonl",
            "enqueued_at": "t1", "src_run": "r1"}

def test_validate_and_append(tmp_path):
    reg = tmp_path / "verdicts.jsonl"
    assert validate_verdict(_v("x")) == []
    errs = validate_verdict({"variant_id": "x"})
    assert any("missing" in e for e in errs)
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("x"))
    snap = load_snapshot(str(reg))
    assert snap["x"]["pf"] == 1.2

def test_snapshot_latest_wins(tmp_path):
    reg = tmp_path / "v.jsonl"
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("x", pf=1.0))
        append_verdict(f, _v("x", pf=1.5))
    assert load_snapshot(str(reg))["x"]["pf"] == 1.5

def test_pass_dead_split_no_data_not_dead(tmp_path):
    reg = tmp_path / "v.jsonl"
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("a", gate_pass=True, ev=0.02))
        append_verdict(f, _v("b", gate_pass=False, ev=-0.01))
        append_verdict(f, _v("c", gate_pass=False, n=0, status="no_data"))
    snap = load_snapshot(str(reg))
    assert [v["variant_id"] for v in pass_variants(snap)] == ["a"]
    assert dead_variants(snap) == {"b"}
    assert "c" not in dead_variants(snap)

def test_queue_claim_ack_recover(tmp_path):
    pending = str(tmp_path / "pending.jsonl")
    inflight = str(tmp_path / "inprogress.jsonl")
    done = str(tmp_path / "done.jsonl")
    assert queue_enqueue(pending, [_row("v1"), _row("v2")], dead=set(), existing=set()) == 2
    row = queue_claim(pending, inflight)
    assert row["variant_id"] == "v1"
    assert [r["variant_id"] for r in queue_load(pending)] == ["v2"]
    assert [r["variant_id"] for r in queue_load(inflight)] == ["v1"]
    assert in_flight_ids(pending, inflight) == {"v1", "v2"}
    # 崩溃: recover 把 v1 前置回 pending
    n = queue_recover(pending, inflight)
    assert n == 1
    assert [r["variant_id"] for r in queue_load(pending)] == ["v1", "v2"]
    assert queue_load(inflight) == []
    row = queue_claim(pending, inflight)
    queue_ack(pending, inflight, row, done)
    assert queue_load(inflight) == []
    assert "v1" in open(done, encoding="utf-8").read()
    assert [r["variant_id"] for r in queue_load(pending)] == ["v2"]
    # 去重
    assert queue_enqueue(pending, [_row("v2")], dead=set(), existing=set()) == 0

def test_tolerates_partial_line(tmp_path):
    reg = tmp_path / "v.jsonl"
    with open(reg, "a", encoding="utf-8") as f:
        append_verdict(f, _v("a"))
        f.write('{"variant_id": "partial')
    assert set(load_snapshot(str(reg))) == {"a"}
    q = str(tmp_path / "pending.jsonl")
    with open(q, "a", encoding="utf-8") as f:
        f.write(json.dumps(_row()) + "\n")
        f.write('{"variant_id": "hal')
    assert [r["variant_id"] for r in queue_load(q)] == ["v1"]
    assert queue_enqueue(q, [_row()], dead=set(), existing=set()) == 0
```

- [ ] Step 2: 运行确认失败
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_verdict_registry.py -v
Expected: FAIL ImportError

- [ ] Step 3: 实现 scripts/registry_lib.py

```python
"""verdict 注册表与 aligned 队列的共享库 (三环文件总线)"""
import json, os, contextlib

VERDICT_FIELDS = {"variant_id", "symbol", "cov_override", "max_points", "n",
                  "pf", "ev", "maxdd", "dir_acc", "gate_pass", "ic",
                  "decided_at", "checkpoint_path", "slow_loop_pid", "git_rev",
                  "schema"}
QUEUE_FIELDS = {"variant_id", "symbol", "cov_override", "max_points",
                "stage", "checkpoint_path", "enqueued_at", "src_run"}

def append_verdict(registry_fp, verdict):
    errs = validate_verdict(verdict)
    if errs:
        raise ValueError(f"invalid verdict: {errs}")
    registry_fp.write(json.dumps(verdict, ensure_ascii=False) + "\n")
    registry_fp.flush()

def _iter_jsonl(path):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

def load_snapshot(path):
    snap = {}
    for v in _iter_jsonl(path) or []:
        try:
            snap[v["variant_id"]] = v
        except (KeyError, TypeError):
            continue
    return snap

def pass_variants(snapshot):
    out = []
    for v in snapshot.values():
        if v.get("status", "ok") != "ok":
            continue
        if v.get("gate_pass") and v.get("ev", 0) > 0:
            out.append(v)
    return out

def dead_variants(snapshot):
    return {vid for vid, v in snapshot.items()
            if v.get("status", "ok") == "ok" and v.get("gate_pass") is False}

def validate_verdict(v):
    errs = []
    missing = VERDICT_FIELDS - set(v)
    if missing:
        errs.append(f"missing fields: {sorted(missing)}")
    for k in ("n", "pf", "ev", "maxdd", "dir_acc", "ic"):
        if k in v and not isinstance(v[k], (int, float)):
            errs.append(f"{k} must be numeric")
    return errs

@contextlib.contextmanager
def _queue_lock(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock = open(path + ".lock", "a")
    import fcntl
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

def _write_rows(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)

def queue_load(path):
    return [r for r in (_iter_jsonl(path) or []) if isinstance(r, dict) and "variant_id" in r]

def queue_enqueue(path, rows, dead, existing):
    if not rows:
        return 0
    with _queue_lock(path):
        inq = {r["variant_id"] for r in queue_load(path)}
        added = 0
        with open(path, "a", encoding="utf-8") as f:
            for r in rows:
                vid = r["variant_id"]
                if vid in dead or vid in existing or vid in inq:
                    continue
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                inq.add(vid)
                added += 1
    return added

def queue_claim(pending_path, inprogress_path):
    """把 pending 队首移入 inprogress; 两边同锁 (锁文件挂在 pending 上)。"""
    with _queue_lock(pending_path):
        inflight = queue_load(inprogress_path)
        if inflight:
            return inflight[0]
        rows = queue_load(pending_path)
        if not rows:
            return None
        row, rest = rows[0], rows[1:]
        _write_rows(pending_path, rest)
        _write_rows(inprogress_path, [row])
        return row

def queue_ack(pending_path, inprogress_path, row, done_path):
    with _queue_lock(pending_path):
        left = [r for r in queue_load(inprogress_path)
                if r.get("variant_id") != row.get("variant_id")]
        _write_rows(inprogress_path, left)
        parent = os.path.dirname(done_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(done_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def queue_recover(pending_path, inprogress_path):
    with _queue_lock(pending_path):
        inflight = queue_load(inprogress_path)
        if not inflight:
            return 0
        pending = queue_load(pending_path)
        seen = {r["variant_id"] for r in inflight}
        merged = inflight + [r for r in pending if r["variant_id"] not in seen]
        _write_rows(pending_path, merged)
        _write_rows(inprogress_path, [])
        return len(inflight)

def in_flight_ids(pending_path, inprogress_path):
    return {r["variant_id"] for r in queue_load(pending_path) + queue_load(inprogress_path)}
```

- [ ] Step 4: 跑测试确认通过
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_verdict_registry.py -v
Expected: 5 PASS

- [ ] Step 5: 全量回归 + 台账 checkpoint (story: P2)
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/ -q -m "not slow"
Expected: 全绿

---

### Task 3: 慢环驱动器 (scripts/aligned_slow_loop.py)

**Files:**
- Create: scripts/aligned_slow_loop.py
- Test: tests/test_aligned_slow_loop.py

**Interfaces:**
- Consumes: registry_lib (Task 2); monthly_backtest.run_symbol_backtest + _daily_predict_cached (Task 1); evaluator.build_summary (task_FM/evaluations/fm_eval/evaluator.py)
- Produces: main(--once/--queue/--inprogress/--registry/--checkpoint-dir/--daily-cache-dir);
  run_aligned_candidate(...) -> verdict dict;
  `_get_models()` 懒加载单例。启动时 `queue_recover`。claim 后再评估。失败 (异常) 不写 gate_pass=False, recover 后可重试。no_data 写 status=no_data。

- [ ] Step 1: 写失败测试

```python
import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import aligned_slow_loop as asl
import registry_lib as rl

def _row():
    return {"variant_id": "m_rsi_state", "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "stage": "aligned",
            "checkpoint_path": "", "enqueued_at": "t1", "src_run": "r1"}

class _FakeResult:
    pass

def _fake_data():
    return {"contract": "M", "points": [{"n": 400, "PF": 1.2, "EV": 0.02,
                                         "MaxDD": -0.1, "DirAcc": 0.55,
                                         "delta_pred": 1, "delta_real": 1}]}

def test_run_aligned_candidate(tmp_path, monkeypatch):
    import monthly_backtest as mb
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: _fake_data())
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 400, "PF": 1.2, "EV": 0.02,
                                                       "MaxDD": -0.1, "DirAcc": 0.55})
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    monkeypatch.setattr(asl, "build_summary",
                        lambda s, c: {"status": "ok", "gate_pass": True, "ev": 0.02,
                                      "pf": 1.2, "n": 400, "maxdd": -0.1, "dir_acc": 0.55})
    reg = tmp_path / "verdicts.jsonl"
    verdict = asl.run_aligned_candidate(
        _row(), daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(reg))
    assert verdict["gate_pass"] is True
    assert verdict["variant_id"] == "m_rsi_state"
    snap = rl.load_snapshot(str(reg))
    assert snap["m_rsi_state"]["gate_pass"] is True

def test_once_mode_claim_ack(tmp_path, monkeypatch):
    reg = tmp_path / "verdicts.jsonl"
    pending = tmp_path / "pending.jsonl"
    inflight = tmp_path / "inprogress.jsonl"
    with open(pending, "a", encoding="utf-8") as f:
        f.write(json.dumps(_row()) + "\n")
    import monthly_backtest as mb
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: _fake_data())
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 400, "PF": 1.2, "EV": 0.02,
                                                       "MaxDD": -0.1, "DirAcc": 0.55})
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    rc = asl.main(["--once", "--queue", str(pending), "--inprogress", str(inflight),
                   "--registry", str(reg),
                   "--checkpoint-dir", str(tmp_path / "cp"),
                   "--daily-cache-dir", str(tmp_path / "dc")])
    assert rc == 0
    assert os.path.getsize(str(pending)) == 0
    assert (not os.path.exists(str(inflight))) or os.path.getsize(str(inflight)) == 0

def test_recover_then_claim_after_crash(tmp_path, monkeypatch):
    """inprogress 残留 + checkpoint 存在时, 启动 recover 再跑, 不得丢候选。"""
    pending = tmp_path / "pending.jsonl"
    inflight = tmp_path / "inprogress.jsonl"
    inflight.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    import monthly_backtest as mb
    monkeypatch.setattr(mb, "run_symbol_backtest", lambda *a, **k: _fake_data())
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 400, "PF": 1.2, "EV": 0.02,
                                                       "MaxDD": -0.1, "DirAcc": 0.55})
    monkeypatch.setattr(asl, "_MODELS", (object(), object()))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    rc = asl.main(["--once", "--queue", str(pending), "--inprogress", str(inflight),
                   "--registry", str(tmp_path / "verdicts.jsonl"),
                   "--checkpoint-dir", str(tmp_path / "cp"),
                   "--daily-cache-dir", str(tmp_path / "dc")])
    assert rc == 0
    snap = rl.load_snapshot(str(tmp_path / "verdicts.jsonl"))
    assert "m_rsi_state" in snap

@pytest.mark.slow
def test_run_aligned_candidate_real_data(tmp_path, monkeypatch):
    row = {"variant_id": "it_m_rsi", "symbol": "m", "cov_override": "rsi_state",
           "max_points": 2, "stage": "aligned",
           "checkpoint_path": "", "enqueued_at": "t", "src_run": "integration"}
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    kw = dict(daily_cache_dir=str(tmp_path / "dc"),
              checkpoint_dir=str(tmp_path / "cp"),
              registry_path=str(tmp_path / "verdicts.jsonl"))
    v1 = asl.run_aligned_candidate(row, **kw)
    assert v1["status"] == "ok"
    assert rl.validate_verdict(v1) == []
    assert v1["variant_id"] == "it_m_rsi"
    assert isinstance(v1["gate_pass"], bool)
    cp = tmp_path / "cp" / "it_m_rsi.jsonl"
    assert cp.exists() and cp.stat().st_size > 0
    v2 = asl.run_aligned_candidate(row, **kw)
    assert v2["status"] == "ok" and rl.validate_verdict(v2) == []
```

- [ ] Step 2: 运行确认失败 (ImportError)
- [ ] Step 3: 实现 scripts/aligned_slow_loop.py

```python
#!/usr/bin/env python3
"""aligned slow loop: claim-driven, checkpoint resume, verdicts (0 token)"""
import argparse, fcntl, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)
sys.path.insert(0, os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval"))
import monthly_backtest as mb
import registry_lib as rl
from evaluator import build_summary
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel

_MODELS = None
_METRICS_PATH = os.path.join(FM_ROOT, "data", "cache", "slow_loop_metrics.jsonl")

def _get_models():
    global _MODELS
    if _MODELS is None:
        daily = DailyModel()
        _MODELS = (daily, HourlyModel(shared_model=daily.model))
    return _MODELS

def _now():
    import datetime
    return datetime.datetime.now().isoformat()

def _git_rev():
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True, cwd=HERE).stdout.strip() or "-"
    except Exception:
        return "-"

def _record_elapsed(variant_id, elapsed_s):
    os.makedirs(os.path.dirname(_METRICS_PATH), exist_ok=True)
    with open(_METRICS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"variant_id": variant_id, "elapsed_s": elapsed_s,
                            "ts": _now()}, ensure_ascii=False) + "\n")

def _no_data_verdict(row):
    return {"variant_id": row["variant_id"], "symbol": row["symbol"],
            "cov_override": row["cov_override"], "max_points": row["max_points"],
            "n": 0, "pf": 0.0, "ev": 0.0, "maxdd": 0.0, "dir_acc": 0.5,
            "gate_pass": False, "ic": 0.0, "decided_at": _now(),
            "checkpoint_path": "", "slow_loop_pid": os.getpid(),
            "git_rev": _git_rev(), "schema": "fm.aligned_verdict.v1",
            "status": "no_data"}  # dead_variants 忽略 no_data

def run_aligned_candidate(row, daily_cache_dir, checkpoint_dir, registry_path):
    vid = row["variant_id"]
    os.makedirs(checkpoint_dir, exist_ok=True)
    cp = os.path.join(checkpoint_dir, vid + ".jsonl")
    completed, resumed = set(), {}
    if os.path.exists(cp):
        for line in open(cp, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (str(rec.get("symbol", "")).lower(), int(rec["idx"]))
            completed.add(key)
            if "delta_pred" in rec and "delta_real" in rec and "error" not in rec:
                resumed[key] = rec
    daily_model, hourly_model = _get_models()
    t0 = time.time()
    with open(cp, "a", encoding="utf-8") as checkpoint_fp:
        data = mb.run_symbol_backtest(
            row["symbol"].upper(), daily_model, hourly_model,
            cov_override=row["cov_override"], max_points=row["max_points"],
            daily_cache_dir=daily_cache_dir,
            completed=completed, checkpoint_fp=checkpoint_fp,
            resumed_points=resumed)
    elapsed_s = round(time.time() - t0, 3)
    if data is None:
        v = _no_data_verdict(row)
    else:
        s = mb.summarize(data)
        if s is None:
            v = _no_data_verdict(row)
        else:
            v = build_summary(s, {"symbol": row["symbol"], "cov_override": row["cov_override"],
                                  "max_points": row["max_points"], "stage": "aligned"})
            v.setdefault("status", "ok")
            v["variant_id"] = row["variant_id"]
            v.setdefault("symbol", row["symbol"])
            v.setdefault("cov_override", row["cov_override"])
            v.setdefault("max_points", row["max_points"])
            v.setdefault("ic", 2 * abs(float(v.get("dir_acc", 0.5)) - 0.5))
            v.setdefault("decided_at", _now())
            v.setdefault("schema", "fm.aligned_verdict.v1")
    v["checkpoint_path"] = cp
    v["slow_loop_pid"] = os.getpid()
    v["git_rev"] = _git_rev()
    with open(registry_path, "a", encoding="utf-8") as f:
        rl.append_verdict(f, v)
    _record_elapsed(row["variant_id"], elapsed_s)
    return v

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--queue", default=os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl"))
    ap.add_argument("--inprogress", default=os.path.join(FM_ROOT, "data", "cache", "aligned_pending.inprogress.jsonl"))
    ap.add_argument("--registry", default=os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl"))
    ap.add_argument("--checkpoint-dir", default=os.path.join(FM_ROOT, "data", "cache", "aligned_checkpoints"))
    ap.add_argument("--daily-cache-dir", default=os.path.join(FM_ROOT, "data", "cache", "daily_pred"))
    args = ap.parse_args(argv)
    os.makedirs(args.checkpoint_dir, exist_ok=True)
    lock_file = os.path.join(os.path.dirname(args.checkpoint_dir), "aligned_slow_loop.lock")
    lock = open(lock_file, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another slow loop instance holds the lock; exit")
        return 0
    try:
        rl.queue_recover(args.queue, args.inprogress)
        while True:
            row = rl.queue_claim(args.queue, args.inprogress)
            if row is None:
                print("queue empty; done")
                return 0
            try:
                verdict = run_aligned_candidate(row, args.daily_cache_dir,
                                                args.checkpoint_dir, args.registry)
            except Exception as e:
                print(json.dumps({"variant_id": row["variant_id"], "error": str(e)}))
                # 不 ack: inprogress 残留, 下次启动 recover 重试。不写死亡 verdict。
                return 1
            rl.queue_ack(args.queue, args.inprogress, row,
                         os.path.join(os.path.dirname(args.checkpoint_dir), "aligned_pending.done.jsonl"))
            print(json.dumps({"variant_id": verdict["variant_id"],
                              "gate_pass": verdict.get("gate_pass"),
                              "status": verdict.get("status")}))
            if args.once:
                return 0
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

if __name__ == "__main__":
    sys.exit(main() or 0)
```

- [ ] Step 4: 单元测试 (排除 slow)
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_aligned_slow_loop.py -v -m "not slow"
Expected: 3 PASS

- [ ] Step 5: 真实数据集成
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_aligned_slow_loop.py -m slow -v
Expected: 1 PASS

- [ ] Step 6: 全量回归 + 台账 checkpoint (story: P3)
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/ -q -m "not slow"

---

### Task 4: goal DSL 安全求值器 (scripts/goal_dsl.py)

**Files:**
- Create: scripts/goal_dsl.py
- Test: tests/test_goal_dsl.py

**Interfaces:**
- Produces: evaluate_goal(conditions, snapshot) -> (bool, list[str])
  snapshot 必含: variants (dict), pass_variant_pf_ratios (list), symbols_hit/families_hit (set),
  cycles_done/cpu_hours_used/tokens_used_m。
  min/max 对空序列返回 unmet, 不把 ValueError 当注入失败。

- [ ] Step 1: 写失败测试

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from goal_dsl import evaluate_goal

SNAP = {"symbols_hit": {"m", "rb"}, "families_hit": {"rsi_state", "ccl"},
        "pass_variant_pf_ratios": [1.2, 1.08],
        "variants": {"a": {"pf": 1.2}},
        "cycles_done": 1, "cpu_hours_used": 4.0, "tokens_used_m": 12.0}

def test_all_conditions_met():
    ok, _ = evaluate_goal(["len(symbols_hit) >= 2",
                           "min(pass_variant_pf_ratios) > 1.05"], SNAP)
    assert ok is True

def test_condition_unmet():
    ok, why = evaluate_goal(["len(symbols_hit) >= 3"], SNAP)
    assert ok is False and "len(symbols_hit) >= 3" in why[0]

def test_empty_min_is_unmet_not_error():
    snap = dict(SNAP)
    snap["pass_variant_pf_ratios"] = []
    ok, why = evaluate_goal(["min(pass_variant_pf_ratios) > 1.05"], snap)
    assert ok is False
    assert any("unmet" in w and "forbidden" not in w and "eval error" not in w for w in why)

def test_variants_name_allowed():
    ok, _ = evaluate_goal(["len(variants) >= 1"], SNAP)
    assert ok is True

def test_injection_rejected():
    for expr in ["__import__('os').system('x')", "(lambda: 1)()",
                 "open('/etc/passwd')", "symbols_hit.__class__"]:
        ok, why = evaluate_goal([expr], SNAP)
        assert ok is False and any("forbidden" in w for w in why)
```

- [ ] Step 2: 运行确认失败 (ImportError)
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_goal_dsl.py -v
Expected: FAIL ImportError

- [ ] Step 3: 实现 scripts/goal_dsl.py

```python
"""goal success_condition 安全求值: ast 白名单, 无调用无属性访问"""
import ast

def _safe_min(*args):
    if len(args) == 1 and hasattr(args[0], "__iter__") and not isinstance(args[0], (str, bytes)):
        seq = list(args[0])
        if not seq:
            raise _Unmet("min of empty sequence")
        return min(seq)
    return min(args)

def _safe_max(*args):
    if len(args) == 1 and hasattr(args[0], "__iter__") and not isinstance(args[0], (str, bytes)):
        seq = list(args[0])
        if not seq:
            raise _Unmet("max of empty sequence")
        return max(seq)
    return max(args)

class _Unmet(Exception):
    pass

_ALLOWED_FUNCS = {"len": len, "min": _safe_min, "max": _safe_max, "all": all, "any": any,
                  "abs": abs, "round": round}

def _forbidden_nodes(tree, allowed_names):
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            bad.append("attribute access at line %s" % getattr(node, "lineno", "?"))
        elif isinstance(node, (ast.Lambda, ast.Await, ast.NamedExpr)):
            bad.append("lambda/await/walrus forbidden")
        elif isinstance(node, ast.Call):
            f = node.func
            if not (isinstance(f, ast.Name) and f.id in _ALLOWED_FUNCS):
                bad.append("call to non-whitelisted func at line %s" % getattr(node, "lineno", "?"))
        elif isinstance(node, ast.Name) and node.id not in allowed_names:
            bad.append("name %s not in snapshot or allowed funcs" % node.id)
    return bad

def evaluate_goal(conditions, snapshot):
    allowed_names = set(snapshot) | set(_ALLOWED_FUNCS)
    ok_flags, reasons = [], []
    for expr in conditions:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            ok_flags.append(False)
            reasons.append("%s -> parse error: %s" % (expr, e))
            continue
        bad = _forbidden_nodes(tree, allowed_names)
        if bad:
            ok_flags.append(False)
            reasons.append("%s -> forbidden: %s" % (expr, bad))
            continue
        try:
            val = eval(compile(tree, "<goal>", "eval"),
                       {"__builtins__": {}},
                       dict(snapshot) | {k: _ALLOWED_FUNCS[k] for k in _ALLOWED_FUNCS})
        except _Unmet as u:
            ok_flags.append(False)
            reasons.append("%s -> unmet (%s)" % (expr, u))
            continue
        except Exception as any_err:
            ok_flags.append(False)
            reasons.append("%s -> eval error: %s" % (expr, any_err))
            continue
        ok_flags.append(val is True)
        if val is not True:
            reasons.append("%s -> unmet (val=%r)" % (expr, val))
    return all(ok_flags), reasons
```

- [ ] Step 4: 跑测试确认通过
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_goal_dsl.py -v
Expected: 5 PASS

- [ ] Step 5: 全量回归 + 台账 checkpoint (story: P4)

---

### Task 5: 监督环 (scripts/praxist_supervisor.py)

**Files:**
- Create: scripts/praxist_supervisor.py
- Test: tests/test_supervisor.py

**Interfaces:**
- Consumes: goal_dsl.evaluate_goal; registry_lib
- Produces:
  main(--dry-run/--once/--goal/--root/--max-cycles);
  load_goal; parse_429_reset; quota_gate; harvest_survivors;
  build_snapshot (含 variants); materialize_known_verdicts;
  write_stop_report; load/save supervisor_state.json
- cycle 只在「一个 praxist run 结束且已 harvest」后 +1, 写入 data/cache/supervisor_state.json
- 429: 活 run + 仍在封禁 → `praxist stop <run_id>`; 解封后 `praxist resume <run_dir_or_run_id> --daemonize --json`
- harvest 身份 `{symbol}_{cov_override}`; max_points=cadence.aligned_max_points 默认 400; 幸存者 ev>0; existing 含 pending+inprogress
- 单实例 flock data/cache/supervisor.lock
- --dry-run / --once: 一轮决策打印后退出, 不 sleep

- [ ] Step 1: 写失败测试

```python
import json, os, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import praxist_supervisor as sup

def test_parse_429_reset():
    log = "... 429 ... It will reset at 2026-09-02 11:26:27 +0800 CST ..."
    dt = sup.parse_429_reset(log)
    assert dt is not None and dt.strftime("%F %H:%M") == "2026-09-02 11:26"
    assert sup.parse_429_reset("no error here") is None

def test_quota_gate_banned_and_remaining(monkeypatch):
    tz = timezone(timedelta(hours=8))
    reset = datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz)
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0,
                        "quota_margin_min": 30}}
    monkeypatch.setattr(sup, "_latest_429_reset", lambda: reset)
    # 封禁中
    now = datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)
    ok, sleep_s = sup.quota_gate(goal, now=now)
    assert ok is False and sleep_s > 0
    # 刚解封, 5h 窗剩余 5h >= 2.5h
    now2 = datetime(2026, 9, 2, 11, 30, 0, tzinfo=tz)
    ok2, sl2 = sup.quota_gate(goal, now=now2)
    assert ok2 is True and sl2 == 0
    # 解封后已过 3h, 剩余 2h < 2.5h → 等下一窗
    now3 = datetime(2026, 9, 2, 14, 30, 0, tzinfo=tz)
    ok3, sl3 = sup.quota_gate(goal, now=now3)
    assert ok3 is False and sl3 > 0

def test_harvest_survivors(tmp_path):
    run = tmp_path / "task_FM" / "experiments" / "run_2026-09-02_10-00-00_x"
    d1 = run / "results" / "gen_0" / "p0" / "m_rsi_state_diagnostic_p6" / "diagnostic"
    d1.mkdir(parents=True)
    (d1 / "evaluation_summary.json").write_text(json.dumps(
        {"status": "ok", "stage": "diagnostic", "variant_name": "m_rsi_state_diagnostic_p6",
         "symbol": "m", "cov_override": "rsi_state",
         "metrics": {"ev": 0.05, "pf": 1.3, "n": 6}, "gate_pass": False}))
    d2 = run / "results" / "gen_0" / "p1" / "m_ccl_diagnostic_p6" / "diagnostic"
    d2.mkdir(parents=True)
    (d2 / "evaluation_summary.json").write_text(json.dumps(
        {"status": "ok", "stage": "diagnostic", "variant_name": "m_ccl_diagnostic_p6",
         "symbol": "m", "cov_override": "ccl",
         "metrics": {"ev": 0.10, "pf": 1.5, "n": 6}, "gate_pass": False}))
    # 负 EV 不是幸存者
    d3 = run / "results" / "gen_0" / "p2" / "m_oi_diagnostic_p6" / "diagnostic"
    d3.mkdir(parents=True)
    (d3 / "evaluation_summary.json").write_text(json.dumps(
        {"status": "ok", "stage": "diagnostic", "variant_name": "m_oi_diagnostic_p6",
         "symbol": "m", "cov_override": "oi",
         "metrics": {"ev": -0.02, "pf": 0.8, "n": 6}, "gate_pass": False}))
    rows = sup.harvest_survivors(str(tmp_path), snapshot={}, dead=set(),
                                 existing=set(), top_k=5, aligned_max_points=400)
    vids = [r["variant_id"] for r in rows]
    assert vids == ["m_ccl", "m_rsi_state"]  # ev 降序; oi 被过滤
    assert all(r["max_points"] == 400 for r in rows)
    # 同 cov 的 p3 不得再占 top_k
    run2 = tmp_path / "task_FM" / "experiments" / "run_2026-09-02_12-00-00_y"
    d4 = run2 / "results" / "gen_0" / "p0" / "m_rsi_state_diagnostic_p3" / "diagnostic"
    d4.mkdir(parents=True)
    (d4 / "evaluation_summary.json").write_text(json.dumps(
        {"status": "ok", "stage": "diagnostic", "variant_name": "m_rsi_state_diagnostic_p3",
         "symbol": "m", "cov_override": "rsi_state",
         "metrics": {"ev": 0.99, "pf": 2.0, "n": 3}, "gate_pass": False}))
    os.utime(run2, (2e9, 2e9))
    rows2 = sup.harvest_survivors(str(tmp_path), snapshot={}, dead=set(),
                                  existing=set(), top_k=5, aligned_max_points=400)
    vids2 = [r["variant_id"] for r in rows2]
    assert vids2.count("m_rsi_state") == 1
    assert vids2[0] == "m_rsi_state"  # 更新 run 的更高 ev 优先, 身份仍合并

def _v(vid, **kw):
    base = {"variant_id": vid, "symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "n": 380, "pf": 1.2, "ev": 0.02, "maxdd": -0.1,
            "dir_acc": 0.55, "gate_pass": True, "ic": 0.1, "decided_at": "t",
            "checkpoint_path": "cp", "slow_loop_pid": 1, "git_rev": "-",
            "schema": "fm.aligned_verdict.v1", "status": "ok"}
    base.update(kw); return base

def test_build_snapshot_metrics(tmp_path):
    reg = tmp_path / "v.jsonl"
    with open(reg, "w", encoding="utf-8") as f:
        f.write(json.dumps(_v("a", gate_pass=True, pf=1.2, ev=0.02, symbol="m")) + "\n")
        f.write(json.dumps(_v("b", gate_pass=False)) + "\n")
    snap = sup.build_snapshot(str(reg), cycles_done=2, cpu_hours_used=6.0,
                              tokens_used_m=10.0)
    assert snap["symbols_hit"] == {"m"}
    assert "a" in snap["variants"]
    assert abs(snap["pass_variant_pf_ratios"][0] - 1.2 / sup.INCUMBENT_PF["m"]) < 1e-9
    assert snap["cycles_done"] == 2

def test_dry_run_one_shot_no_sleep(tmp_path, monkeypatch):
    slept = {"n": 0}
    monkeypatch.setattr(sup.time, "sleep", lambda s: slept.__setitem__("n", slept["n"] + 1))
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(sup, "FM_ROOT", str(tmp_path))
    monkeypatch.setattr(sup, "QUEUE", str(tmp_path / "pending.jsonl"))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sup, "REGISTRY", str(tmp_path / "verdicts.jsonl"))
    monkeypatch.setattr(sup, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(sup, "LOCK_PATH", str(tmp_path / "sup.lock"))
    goal = tmp_path / "goal.yaml"
    goal.write_text(
        "goal:\n  success_condition: ['len(symbols_hit) >= 99']\n"
        "  budgets: {max_cycles: 10, cpu_hours: 60, token_budget_m: 80}\n"
        "  cadence: {survivors_per_cycle: 2, aligned_max_points: 400,\n"
        "            run_budget_hours: 2.0, quota_window_hours: 5.0, quota_margin_min: 30,\n"
        "            slow_loop_window: '00:00-23:59'}\n",
        encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    rc = sup.main(["--dry-run", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    assert slept["n"] == 0

def test_cycles_increment_only_after_harvest(tmp_path, monkeypatch):
    monkeypatch.setattr(sup.time, "sleep", lambda s: None)
    monkeypatch.setattr(sup, "_run_active", lambda: True)  # run 仍在
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "FM_ROOT", str(tmp_path))
    monkeypatch.setattr(sup, "QUEUE", str(tmp_path / "pending.jsonl"))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sup, "REGISTRY", str(tmp_path / "verdicts.jsonl"))
    monkeypatch.setattr(sup, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(sup, "LOCK_PATH", str(tmp_path / "sup.lock"))
    (tmp_path / "state.json").write_text('{"cycles_done": 0}', encoding="utf-8")
    goal = tmp_path / "goal.yaml"
    goal.write_text(
        "goal:\n  success_condition: ['len(symbols_hit) >= 99']\n"
        "  budgets: {max_cycles: 1, cpu_hours: 60, token_budget_m: 80}\n"
        "  cadence: {survivors_per_cycle: 2, aligned_max_points: 400,\n"
        "            run_budget_hours: 2.0, quota_window_hours: 5.0, quota_margin_min: 30}\n",
        encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st.get("cycles_done", 0) == 0  # 活 run 不加 cycle

def test_429_stop_then_resume(tmp_path, monkeypatch):
    calls = []
    def fake_praxist(args, **k):
        calls.append(list(args))
        return {"ok": True, "stdout": ""}
    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    tz = timezone(timedelta(hours=8))
    reset = datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz)
    monkeypatch.setattr(sup, "_latest_429_reset", lambda: reset)
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0,
                        "quota_margin_min": 30}}
    now = datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)
    actions = sup.decide_fast_loop(goal, dry_run=True, now=now)
    assert [a["action"] for a in actions] == ["run_paused_429"]
    assert calls == []  # dry_run 不调 praxist
    now2 = datetime(2026, 9, 2, 11, 30, 0, tzinfo=tz)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "load_state", lambda: {"last_run_dir": "/tmp/runX", "paused_429": True,
                                                    "cycles_done": 0})
    actions2 = sup.decide_fast_loop(goal, dry_run=True, now=now2)
    assert [a["action"] for a in actions2] == ["run_resumed"]

def test_materialize_known_verdicts(tmp_path):
    dest = tmp_path / "known_verdicts.inc.md"
    snap = {"a": _v("m_ccl", gate_pass=True, ev=0.02),
            "b": _v("m_oi", gate_pass=False, ev=-0.01)}
    sup.materialize_known_verdicts(snap, str(dest))
    text = dest.read_text(encoding="utf-8")
    assert "m_ccl" in text and "gate_pass=True" in text
    assert "m_oi" in text and "gate_pass=False" in text
```

- [ ] Step 2: 运行确认失败 (ImportError)
- [ ] Step 3: 实现 scripts/praxist_supervisor.py

```python
#!/usr/bin/env python3
"""三环监督环: goal 判定 + 两环调度, 纯 Python 0 token"""
import argparse, fcntl, glob, json, os, re, subprocess, sys, time
from datetime import datetime, timedelta
import yaml
HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)
import registry_lib as rl
from goal_dsl import evaluate_goal

PRAXIST = "/root/.praxist-venv/bin/praxist"
QUEUE = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl")
INPROGRESS = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.inprogress.jsonl")
REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")
STATE_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_state.json")
LOCK_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor.lock")
VERDICTS_INC = os.path.join(FM_ROOT, "task_FM", "known_verdicts.inc.md")
REPORT_DIR = os.path.join(FM_ROOT, "docs", "superpowers", "reports")
STATE_MD = os.path.join(FM_ROOT, "STATE.md")
POLL_S = 300

with open(os.path.join(FM_ROOT, "config", "knowledge_base.json"), encoding="utf-8") as _f:
    _kb = json.load(_f)
INCUMBENT_PF = {sym: float(rec["historical_pf"])
                for sym, rec in _kb["symbols"].items()
                if rec.get("historical_pf") is not None}

def _now_iso():
    return datetime.now().isoformat()

def parse_429_reset(log_text):
    m = re.search(r"reset at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})", log_text)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")

def load_state():
    if not os.path.exists(STATE_PATH):
        return {"cycles_done": 0, "last_run_dir": None, "last_run_id": None,
                "last_harvested_run_id": None, "paused_429": False}
    try:
        return json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception:
        return {"cycles_done": 0}

def save_state(st):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)

def load_goal(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["goal"]

def _praxist(args, env=None):
    r = subprocess.run([PRAXIST, *args], capture_output=True, text=True, env=env)
    return {"ok": r.returncode == 0, "stdout": r.stdout or "", "stderr": r.stderr or "", "rc": r.returncode}

def _status_rows():
    r = _praxist(["status", "--json"])
    try:
        data = json.loads(r["stdout"] or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []

def _run_active():
    return any((row or {}).get("state") in {"running", "starting"} for row in _status_rows())

def _active_run_meta():
    for row in _status_rows():
        if (row or {}).get("state") in {"running", "starting"}:
            return row
    return None

def _latest_429_reset():
    logs = sorted(glob.glob(os.path.join(FM_ROOT, "task_FM", "experiments", "run_*", "logs", "*.log")),
                  key=os.path.getmtime, reverse=True)
    for lp in logs[:5]:
        try:
            reset = parse_429_reset(open(lp, encoding="utf-8", errors="ignore").read())
        except OSError:
            continue
        if reset:
            return reset
    return None

def quota_gate(goal, now=None):
    """return (window_ok, sleep_seconds_if_blocked)."""
    cad = goal.get("cadence") or {}
    run_h = float(cad.get("run_budget_hours", 2.0))
    win_h = float(cad.get("quota_window_hours", 5.0))
    margin_h = float(cad.get("quota_margin_min", 30)) / 60.0
    need = run_h + margin_h
    reset = _latest_429_reset()
    if reset is None:
        return True, 0
    now = now or datetime.now(reset.tzinfo)
    if now.tzinfo is None and reset.tzinfo is not None:
        now = now.replace(tzinfo=reset.tzinfo)
    if now < reset:
        return False, max(1, int((reset - now).total_seconds()))
    elapsed_h = (now - reset).total_seconds() / 3600.0
    remaining = win_h - elapsed_h
    if remaining >= need:
        return True, 0
    next_reset = reset + timedelta(hours=win_h)
    return False, max(1, int((next_reset - now).total_seconds()))

def build_snapshot(registry_path, cycles_done, cpu_hours_used, tokens_used_m):
    snap = rl.load_snapshot(registry_path)
    passing = rl.pass_variants(snap)
    return {
        "variants": snap,
        "symbols_hit": {v["symbol"] for v in passing},
        "families_hit": {v["cov_override"] for v in passing},
        "pass_variant_pf_ratios": [v["pf"] / INCUMBENT_PF.get(v["symbol"], 1.0)
                                   for v in passing],
        "cycles_done": cycles_done,
        "cpu_hours_used": cpu_hours_used,
        "tokens_used_m": tokens_used_m,
    }

def harvest_survivors(root, snapshot, dead, existing, top_k, aligned_max_points=400):
    out = []
    seen = set()
    run_dirs = sorted(glob.glob(os.path.join(root, "task_FM", "experiments", "run_*")),
                      key=os.path.getmtime, reverse=True)
    for run_dir in run_dirs:
        for sp in glob.glob(os.path.join(run_dir, "results", "**", "evaluation_summary.json"),
                            recursive=True):
            try:
                d = json.load(open(sp, encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") != "ok" or d.get("stage") != "diagnostic":
                continue
            ev = float((d.get("metrics") or {}).get("ev") or 0.0)
            if ev <= 0:
                continue
            try:
                symbol = d["symbol"].lower()
                cov = d["cov_override"]
            except KeyError:
                continue
            vid = f"{symbol}_{cov}"
            if vid in dead or vid in existing or vid in snapshot or vid in seen:
                continue
            seen.add(vid)
            out.append({"variant_id": vid, "symbol": symbol, "cov_override": cov,
                        "max_points": int(aligned_max_points),
                        "stage": "aligned", "checkpoint_path": "",
                        "enqueued_at": _now_iso(), "src_run": os.path.basename(run_dir),
                        "_ev": ev})
    out.sort(key=lambda r: -r["_ev"])
    for r in out:
        r.pop("_ev", None)
    return out[:top_k]

def materialize_known_verdicts(snapshot, dest_path):
    lines = ["## Known aligned verdicts (supervisor snapshot)",
             "gate_pass=True: already solved, do NOT re-propose.",
             "gate_pass=False: DEAD, revive only with PI mechanism correction.",
             ""]
    items = list(snapshot.values()) if isinstance(snapshot, dict) else []
    items.sort(key=lambda v: (not v.get("gate_pass", False), -float(v.get("ev") or 0)))
    if not items:
        lines.append("(no aligned verdicts yet)")
    for v in items[:20]:
        lines.append("- {0}: gate_pass={1}, ev={2}, n={3}, status={4}".format(
            v.get("variant_id"), v.get("gate_pass"), v.get("ev"),
            v.get("n"), v.get("status", "ok")))
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def _log_decision(log_path, action, reason, refs=None):
    rec = {"ts": _now_iso(), "action": action, "reason": reason, "refs": refs or []}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def _read_cpu_hours():
    p = os.path.join(FM_ROOT, "data", "cache", "slow_loop_metrics.jsonl")
    total = 0.0
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                try:
                    total += float(json.loads(line).get("elapsed_s", 0)) / 3600.0
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
    return round(total, 3)

def _read_token_m():
    """Best-effort. 若所有 generation_results 都缺 runtime_usage, 返回 (0.0, True)=unknown, 跳过 token 预算。"""
    total = 0.0
    saw = False
    for gr in glob.glob(os.path.join(FM_ROOT, "task_FM", "experiments", "run_*", "gen_*", "generation_results.json")):
        try:
            d = json.load(open(gr, encoding="utf-8"))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else [d]):
            u = (it or {}).get("runtime_usage") or {}
            tok = u.get("total_tokens")
            if tok is None:
                tok = (it or {}).get("total_tokens")
            if tok is None:
                continue
            saw = True
            total += float(tok)
    return round(total / 1e6, 3), (not saw)

def _in_slow_window(goal, now=None):
    win = (goal.get("cadence") or {}).get("slow_loop_window") or ""
    if "-" not in win:
        return True
    a, b = [x.strip() for x in win.split("-", 1)]
    now_s = (now or datetime.now()).strftime("%H:%M")
    if a <= b:
        return a <= now_s <= b
    return now_s >= a or now_s <= b

def _deadline_passed(b):
    d = b.get("deadline")
    if not d:
        return False
    try:
        return datetime.now() > datetime.fromisoformat(str(d))
    except ValueError:
        return False

def _slow_loop_alive():
    lock_path = os.path.join(FM_ROOT, "data", "cache", "aligned_slow_loop.lock")
    if not os.path.exists(lock_path):
        return False
    f = open(lock_path, "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    finally:
        f.close()

def write_stop_report(kind, snap, why, budgets_line):
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(REPORT_DIR, f"supervisor_{kind}_{ts}.md")
    body = ["# Supervisor {0}".format(kind), "",
            "- ts: {0}".format(_now_iso()),
            "- cycles_done: {0}".format(snap.get("cycles_done")),
            "- cpu_hours_used: {0}".format(snap.get("cpu_hours_used")),
            "- tokens_used_m: {0}".format(snap.get("tokens_used_m")),
            "- symbols_hit: {0}".format(sorted(snap.get("symbols_hit") or [])),
            "- families_hit: {0}".format(sorted(snap.get("families_hit") or [])),
            "- budgets: {0}".format(budgets_line),
            "- why: {0}".format("; ".join(why) if why else "(all conditions met)"),
            ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    try:
        with open(STATE_MD, "a", encoding="utf-8") as f:
            f.write("\n## Supervisor {0} ({1})\n\nSee {2}\n".format(kind, ts, path))
    except OSError:
        pass
    return path

def decide_fast_loop(goal, dry_run=False, now=None):
    """纯决策: 返回 actions 列表 [{action, reason, refs, argv?}]. dry_run 不调用 praxist。"""
    actions = []
    ok, sleep_s = quota_gate(goal, now=now)
    active = _run_active()
    meta = _active_run_meta() if active else None
    st = load_state()
    if active and not ok:
        run_id = (meta or {}).get("run_id") or st.get("last_run_id")
        run_dir = (meta or {}).get("run_dir") or st.get("last_run_dir")
        actions.append({"action": "run_paused_429", "reason": "quota banned; stop then wait reset",
                        "refs": [run_id, run_dir], "argv": ["stop", str(run_id)] if run_id else None,
                        "sleep_s": sleep_s})
        if not dry_run and run_id:
            _praxist(["stop", str(run_id)])
            st["paused_429"] = True
            st["last_run_dir"] = run_dir
            st["last_run_id"] = run_id
            save_state(st)
        return actions
    if (not active) and ok and st.get("paused_429") and st.get("last_run_dir"):
        rd = st["last_run_dir"]
        actions.append({"action": "run_resumed", "reason": "quota window ok; resume same run_dir",
                        "refs": [rd],
                        "argv": ["resume", rd, "--daemonize", "--json"]})
        if not dry_run:
            env = {**os.environ, "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_AUTH_TOKEN", "")}
            _praxist(["resume", rd, "--daemonize", "--json"], env=env)
            st["paused_429"] = False
            save_state(st)
        return actions
    if (not active) and ok:
        actions.append({"action": "run_started", "reason": "window ok, no active run",
                        "refs": [],
                        "argv": ["start", "--task-path", os.path.join(FM_ROOT, "task_FM"),
                                 "--daemonize", "--json"]})
        if not dry_run:
            env = {**os.environ, "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_AUTH_TOKEN", "")}
            r = _praxist(["start", "--task-path", os.path.join(FM_ROOT, "task_FM"),
                          "--daemonize", "--json"], env=env)
            st["paused_429"] = False
            # 尽力从 json stdout 收 run_dir
            try:
                js = json.loads(r["stdout"] or "{}")
                st["last_run_dir"] = js.get("run_dir") or st.get("last_run_dir")
                st["last_run_id"] = js.get("run_id") or st.get("last_run_id")
            except json.JSONDecodeError:
                pass
            save_state(st)
        return actions
    if not ok:
        actions.append({"action": "wait_quota", "reason": "quota window insufficient",
                        "refs": [], "sleep_s": sleep_s})
    return actions

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--goal", default=os.path.join(FM_ROOT, "scripts", "praxist_goal.yaml"))
    ap.add_argument("--root", default=FM_ROOT)
    ap.add_argument("--max-cycles", type=int, default=None)
    args = ap.parse_args(argv)
    if args.root != FM_ROOT:
        # 测试可把模块级路径 monkeypatch; --root 仅给 harvest 用
        pass
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    lock = open(LOCK_PATH, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another supervisor holds the lock; exit")
        return 0
    try:
        return _main_locked(args)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

def _main_locked(args):
    goal = load_goal(args.goal)
    log = os.path.join(FM_ROOT, ".omc", "supervisor_decisions.jsonl")
    max_cycles = args.max_cycles or goal["budgets"]["max_cycles"]
    one_shot = args.dry_run or args.once
    while True:
        st = load_state()
        cycles = int(st.get("cycles_done") or 0)
        cpu_h = _read_cpu_hours()
        tok_m, tok_unknown = _read_token_m()
        snap = build_snapshot(REGISTRY, cycles, cpu_h, tok_m)
        materialize_known_verdicts(snap["variants"], VERDICTS_INC)
        ok, why = evaluate_goal(goal["success_condition"], snap)
        if ok:
            rec = _log_decision(log, "goal_reached", "; ".join(why) or "all conditions met")
            write_stop_report("goal_reached", snap, why, rec["reason"])
            print(json.dumps(rec, ensure_ascii=False))
            return 0
        b = goal["budgets"]
        tok_hit = (not tok_unknown) and tok_m >= b.get("token_budget_m", 80)
        if (cycles >= max_cycles or cpu_h >= b.get("cpu_hours", 60)
                or tok_hit or _deadline_passed(b)):
            rec = _log_decision(log, "budget_exhausted",
                                f"cycles={cycles} cpu_h={cpu_h} tok_m={tok_m} tok_unknown={tok_unknown}")
            write_stop_report("budget_exhausted", snap, [rec["reason"]], rec["reason"])
            print(json.dumps(rec, ensure_ascii=False))
            return 0
        planned = decide_fast_loop(goal, dry_run=args.dry_run)
        for a in planned:
            print(json.dumps(a, ensure_ascii=False, default=str))
            _log_decision(log, a["action"], a.get("reason", ""), a.get("refs") or [])

        cad = goal.get("cadence") or {}
        snap_now = rl.load_snapshot(REGISTRY)
        dead = rl.dead_variants(snap_now)
        existing = rl.in_flight_ids(QUEUE, INPROGRESS)
        rows = harvest_survivors(
            FM_ROOT, snap_now, dead, existing,
            top_k=cad.get("survivors_per_cycle", 2),
            aligned_max_points=cad.get("aligned_max_points", 400))
        last = st.get("last_run_id")
        harvested_already = bool(last) and st.get("last_harvested_run_id") == last
        if args.dry_run:
            print(json.dumps({"action": "harvest_plan", "n": len(rows),
                              "vids": [r["variant_id"] for r in rows]}, ensure_ascii=False))
        elif (not _run_active()) and last and not harvested_already:
            if rows:
                n = rl.queue_enqueue(QUEUE, rows, dead, existing)
                _log_decision(log, "harvested", f"enqueued {n}",
                              [r["variant_id"] for r in rows])
            else:
                _log_decision(log, "harvest_empty",
                              "finished run produced 0 diagnostic survivors "
                              "(need results/**/evaluation_summary.json)")
            st["cycles_done"] = cycles + 1
            st["last_harvested_run_id"] = last
            save_state(st)

        pending_rows = rl.queue_load(QUEUE) + rl.queue_load(INPROGRESS)
        if (not args.dry_run) and _in_slow_window(goal) and pending_rows:
            if not _slow_loop_alive():
                out_path = os.path.join(FM_ROOT, "data", "cache", "slow_loop.out")
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                out_fp = open(out_path, "ab")
                try:
                    subprocess.Popen(
                        [sys.executable, os.path.join(HERE, "aligned_slow_loop.py")],
                        stdout=out_fp, stderr=subprocess.STDOUT, start_new_session=True)
                finally:
                    out_fp.close()
                _log_decision(log, "slow_loop_started", "queue non-empty, in window")

        if one_shot:
            return 0
        sleep_s = POLL_S
        for a in planned:
            if a.get("sleep_s"):
                sleep_s = min(sleep_s, int(a["sleep_s"]))
        time.sleep(max(1, sleep_s))

if __name__ == "__main__":
    sys.exit(main() or 0)
```

cycle 计数 (与上面 `_main_locked` 一致, 不要改成 sleep tick):

- `last_run_id` / `last_run_dir` 在 start 的 JSON stdout 或 resume 的 target 里更新。
- 仅当 `_run_active() is False` 且 `last_run_id` 非空且 `last_harvested_run_id != last_run_id` 时: harvest 一次, 然后 `cycles_done += 1`, `last_harvested_run_id = last_run_id`。
- dry-run / 活 run: cycles 不变。
- `praxist resume` 真实 CLI (已核): `praxist resume <run_id_or_run_dir> --daemonize --json` (位置参数 `target`, 不是 `--run-dir`)。`praxist stop <run_id>`。

- [ ] Step 4: 跑测试确认通过
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_supervisor.py -v
Expected: 8 PASS (parse_429, quota_gate, harvest, snapshot, dry_run, cycles, 429 resume, materialize)

- [ ] Step 5: 全量回归 + 台账 checkpoint (story: P5)

---

### Task 6: goal.yaml + Known verdicts include + 红线

**Files:**
- Create: scripts/praxist_goal.yaml
- Create: task_FM/known_verdicts.inc.md (初始占位, supervisor 每次覆盖)
- Modify: task_FM/prompt_base.jinja2 (末尾 include)
- Modify: loop-constraints.md (verdict 写权限红线)
- Test: tests/test_praxist_evidence_ladder.py 追加 1 个渲染测试

- [ ] Step 1: 扩展渲染测试

```python
def test_templates_render_known_verdicts(tmp_path):
    inc = os.path.join(os.path.dirname(BASE_TPL), "known_verdicts.inc.md")
    os.makedirs(os.path.dirname(inc), exist_ok=True)
    with open(inc, "w", encoding="utf-8") as f:
        f.write("- m_ccl: gate_pass=True, ev=0.02, n=400, status=ok\n")
    ctx = _fake_ctx()
    # FileSystemLoader 同胞 include: 测试侧用与 praxist 相同的 loader
    import jinja2
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(BASE_TPL)),
        undefined=jinja2.ChainableUndefined)
    base = env.get_template(os.path.basename(BASE_TPL)).render(**ctx)
    assert "aligned_verdicts.jsonl" in base or "known_verdicts.inc.md" in base
    assert "m_ccl" in base and "gate_pass=True" in base
```

- [ ] Step 2: 跑测试确认失败
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/test_praxist_evidence_ladder.py::test_templates_render_known_verdicts -v
Expected: FAIL

- [ ] Step 3: prompt_base.jinja2 文件末尾追加

```
## Known verdicts (aligned registry)
Before proposing ANY candidate, Read task_FM/config/aligned_verdicts.jsonl
and the snapshot below. gate_pass=True means already solved: do NOT re-propose.
gate_pass=False (status=ok) means DEAD: never revive without a PI mechanism
correction. status=no_data is retryable, not dead.
{% include 'known_verdicts.inc.md' ignore missing %}
```

- [ ] Step 4: 写 scripts/praxist_goal.yaml

```yaml
goal:
  success_condition:
    - "len(symbols_hit) >= 1"
    - "min(pass_variant_pf_ratios) > 1.05"
    - "len(families_hit) >= 1"
  budgets:
    max_cycles: 3
    cpu_hours: 12
    token_budget_m: 40
    deadline: "2026-09-30"
  cadence:
    slow_loop_window: "22:00-08:00"
    survivors_per_cycle: 2
    aligned_max_points: 400
    run_budget_hours: 2.0
    quota_window_hours: 5.0
    quota_margin_min: 30
```

max_cycles: 3 现在表示 3 次已完成 praxist run, 不是 15 分钟。e2e 可接受。

- [ ] Step 5: 写 task_FM/known_verdicts.inc.md 占位

```
(no aligned verdicts yet)
```

- [ ] Step 6: loop-constraints.md 高风险路径保护节追加

```
  - aligned_verdicts.jsonl 唯一写入方: aligned_slow_loop.py (慢环 flock 持有者)。
    peers/supervisor/人工写 verdict = 破坏预注册纪律, 视同数据造假。
    status=no_data 不是死亡; 只有 status=ok 且 gate_pass=false 为 DEAD。
    verdict 注册表为 canonical 证据源, reports/ 均为衍生视图。
```

- [ ] Step 7: 跑测试 + 全量回归 + 台账 checkpoint (story: P6)
Run: cd /root/timesFM_fu && .praxist-venv/bin/python -m pytest tests/ -q -m "not slow"
Expected: 全绿

---

### Task 7: runbook + 端到端演练

**Files:**
- Create: docs/runbook_praxist_three_loop.md

- [ ] Step 1: 写 runbook

```
## 启动/停止
- 启动监督环: nohup .praxist-venv/bin/python scripts/praxist_supervisor.py > data/cache/supervisor.out 2>&1 &
- 干跑: .praxist-venv/bin/python scripts/praxist_supervisor.py --dry-run
  (一轮打印 action JSON, 不 sleep, 不起 run/慢环, 不加 cycle)
- 单步: --once (允许真启进程, 仍不 sleep)
- 停止: kill <pid>; flock 在进程死后释放; 队列 inprogress 由慢环下次 queue_recover 回收

## 快环
- 手动: ANTHROPIC_API_KEY=$ANTHROPIC_AUTH_TOKEN praxist start --task-path task_FM --daemonize --json
- 429: 监督环在封禁期对活 run 执行 praxist stop <run_id>, 解封且窗口足够后
  praxist resume <run_dir_or_run_id> --daemonize --json
- 禁止 429 后 start 新 run

## 慢环
- 手动单候选: .praxist-venv/bin/python scripts/aligned_slow_loop.py --once
- 监控: tail -f data/cache/slow_loop.out
- 队列: data/cache/aligned_pending.jsonl
- 进行中: data/cache/aligned_pending.inprogress.jsonl
- checkpoint: data/cache/aligned_checkpoints/<variant_id>.jsonl
- kill 慢环后重启: recover inprogress → claim → checkpoint 续跑

## 验收演练
1. --dry-run: 看到 goal 评估 / harvest_plan / wait_quota 或 run_started 的 JSON, 立即退出
2. 注入假 429 日志 → quota_gate 返回 False; decide_fast_loop 在活 run 时给出 run_paused_429
3. 把一行写入 inprogress, kill 想象中的慢环, 再跑 --once → recover 后产出 verdict
4. 真实 cycle: 小 goal; run 结束后 harvest 入队 → 慢环 verdict → 下次 start 前 known_verdicts.inc.md
   被 include 进 peer 提示 (渲染含 variant_id 与 gate_pass=)
5. max_cycles 在 --once 循环下不会因为 300s tick 耗尽 (cycles 只在 harvest 已完成 run 后 +1)
```

- [ ] Step 2: 台账 checkpoint (story: P7)
- [ ] Step 3: 执行期验收 (对照 spec §11, 以本计划「Spec 绑定解释」为准)

---

## 自审记录 (writing-plans Self-Review)

1. Spec 覆盖: §4.1→Task1 (v2 payload + 指纹失效测试 + 真 HIT A/B); §4.2→Task3 claim/recover; §4.3→Task2+Task6; §4.4→Task5 (cycle 持久化, 429 stop/resume, 报告); §4.5/§5→Task4 variants + 空 min; §6 恢复矩阵→Task2 recover + Task5 429; §7 测试→各 Task Step1 含控制环; §8 预算/报告→write_stop_report; §11→Task7。
2. 占位符: 无 TBD/TODO。`praxist resume <target> --daemonize --json` 已按 site-packages 核过。
3. 类型一致性: queue_claim/ack/recover/in_flight_ids 在 Task2/3/5 一致; harvest variant_id=`{symbol}_{cov}`; aligned_max_points=400; DailyResult.forecast; dead_variants 忽略 no_data。

## 评审修订记录

2026-09-03 外部评审 18 项已在前一版消化。2026-09-03 第二轮审核 (critic REJECT) 后本版重写控制环与队列协议:

| # | 缺陷 | 本版处置 |
|---|------|----------|
| C1 | cycles += 1 每 300s, max_cycles=3 约 15min 退出 | cycle = 已完成 praxist run + harvest; 持久化 supervisor_state.json; 活 run 不加; 单测 |
| C2 | queue_take 后 6h 评估, kill 丢候选 / harvest 重复入队 | claim/inprogress/ack/recover; harvest existing 含 in_flight_ids |
| C3 | 429 后 start 新 run, 无剩余窗口 | quota_gate; 封禁 stop; 解封 resume 同一 run_dir; 窗剩余 < run+30min 则等下一窗 |
| M4 | --dry-run 仍 sleep 并写假 run_started | --dry-run/--once 一轮打印退出, 不 sleep |
| M5 | 无终报/中途报告 | write_stop_report + STATE.md |
| M6 | .model_fp 永不重算 | .model_fp.json 存 sig(path,size,mtime); 单测改 shard 即换 fp |
| M7 | A/B 不测 HIT、三 cutoff 共用 store、不比 dates | 每 cutoff 独立 BacktestDataStore; miss+HIT+live; dates ISO |
| M8 | harvest max_points=诊断 n → 永远 350 | cadence.aligned_max_points=400 |
| M9 | slow 测试缺 monkeypatch 参数 | 签名加 monkeypatch |
| M10 | Known verdicts 不进提示词 | task_FM/known_verdicts.inc.md + jinja include; 断言含 variant_id |
| M11 | 真实 results 常无 evaluation_summary | harvest_empty 决策日志; 身份 (symbol,cov); 负 EV 过滤 |
| M12 | DSL 无 variants; min([]) eval error | snapshot.variants; _safe_min 空序列 unmet |
| M13 | 监督环无 flock; status 子串; token 常为 0 | supervisor.lock; JSON state in {running,starting}; token unknown 跳过预算 |
| M14 | Task5 无控制环测试 | quota_gate / dry_run / cycles / 429 resume / materialize |
| M15 | no_data 永久死亡 | status=no_data 不进 dead_variants |

升级后再实施。不要按 2026-09-02 旧内联 Task 5 开工。
