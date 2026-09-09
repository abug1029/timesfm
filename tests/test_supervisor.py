import json, os, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import praxist_supervisor as sup

def _patch_paths(monkeypatch, tmp_path):
    """Keep supervisor IO inside tmp_path; do not touch production data/cache."""
    monkeypatch.setattr(sup, "FM_ROOT", str(tmp_path))
    monkeypatch.setattr(sup, "QUEUE", str(tmp_path / "pending.jsonl"))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sup, "REGISTRY", str(tmp_path / "verdicts.jsonl"))
    monkeypatch.setattr(sup, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(sup, "LOCK_PATH", str(tmp_path / "sup.lock"))
    monkeypatch.setattr(sup, "VERDICTS_INC", str(tmp_path / "known_verdicts.inc.md"))
    monkeypatch.setattr(sup, "REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(sup, "STATE_MD", str(tmp_path / "STATE.md"))


def _clear_failover_env(monkeypatch):
    """Existing 429 tests assume no DashScope failover."""
    for k in (
        "FAILOVER_ANTHROPIC_BASE_URL", "FAILOVER_ANTHROPIC_API_KEY",
        "FAILOVER_ANTHROPIC_AUTH_TOKEN", "FAILOVER_MODEL",
        "ANTHROPIC_FAILOVER_BASE_URL", "ANTHROPIC_FAILOVER_API_KEY",
        "ANTHROPIC_FAILOVER_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)


def _set_failover_env(monkeypatch):
    """Dummy failover config for unit tests (fake values, never real secrets)."""
    monkeypatch.setenv("FAILOVER_ANTHROPIC_BASE_URL", "https://example.test/failover")
    monkeypatch.setenv("FAILOVER_ANTHROPIC_API_KEY", "test-failover-key")
    monkeypatch.setenv("FAILOVER_MODEL", "qwen3.7-plus")
    monkeypatch.setenv("PRIMARY_MODEL", "claude-opus-4-7")
    monkeypatch.setenv("PRIMARY_ANTHROPIC_BASE_URL", "https://example.test/primary")
    monkeypatch.setenv("PRIMARY_ANTHROPIC_API_KEY", "test-primary-key")

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
    # 窗在 reset+N*win_h 重开, remaining 在当前窗内计量
    now4 = reset + timedelta(hours=5)
    ok4, sl4 = sup.quota_gate(goal, now=now4)
    assert ok4 is True and sl4 == 0
    now5 = reset + timedelta(hours=5, seconds=1)
    ok5, sl5 = sup.quota_gate(goal, now=now5)
    assert ok5 is True and sl5 == 0

def _eval_summary(symbol, cov, ev, n=6, pf=1.3, max_points=None):
    """Canonical build_summary shape: top-level ev + metrics.ev_after_slippage."""
    mp = n if max_points is None else max_points
    return {
        "status": "ok", "usage_unknown": False, "stage": "diagnostic",
        "variant_name": f"{symbol}_{cov}_diagnostic_p{mp}",
        "symbol": symbol, "cov_override": cov,
        "n": n, "pf": pf, "ev": ev, "maxdd": -0.1, "dir_acc": 0.55,
        "gate_pass": False,
        "metrics": {
            "ev_after_slippage": ev, "pf": pf, "maxdd": -0.1,
            "n": n, "dir_acc": 0.55, "gate_pass": False,
        },
    }

def test_harvest_survivors(tmp_path):
    run = tmp_path / "task_FM" / "experiments" / "run_2026-09-02_10-00-00_x"
    # 保留的 harvest_survivors (回滚用) 读旧诊断产物 evaluation_summary.json;
    # 新提案产物 proposals/*.json 由 harvest_proposals 收割, 见 test_harvest_proposals.py。
    d1 = run / "results" / "gen_0" / "p0" / "m_rsi_state_diagnostic_p6" / "diagnostic"
    d1.mkdir(parents=True)
    (d1 / "evaluation_summary.json").write_text(json.dumps(
        _eval_summary("m", "rsi_state", ev=0.05, n=6, pf=1.3)))
    d2 = run / "results" / "gen_0" / "p1" / "m_ccl_diagnostic_p6" / "diagnostic"
    d2.mkdir(parents=True)
    (d2 / "evaluation_summary.json").write_text(json.dumps(
        _eval_summary("m", "ccl", ev=0.10, n=6, pf=1.5)))
    # 负 EV 不是幸存者
    d3 = run / "results" / "gen_0" / "p2" / "m_oi_diagnostic_p6" / "diagnostic"
    d3.mkdir(parents=True)
    (d3 / "evaluation_summary.json").write_text(json.dumps(
        _eval_summary("m", "oi", ev=-0.02, n=6, pf=0.8)))
    # ev==0 同样丢弃
    d0 = run / "results" / "gen_0" / "p3" / "m_ha_body_diagnostic_p6" / "diagnostic"
    d0.mkdir(parents=True)
    (d0 / "evaluation_summary.json").write_text(json.dumps(
        _eval_summary("m", "ha_body", ev=0.0, n=6, pf=1.0)))
    rows = sup.harvest_survivors(str(tmp_path), snapshot={}, dead=set(),
                                 existing=set(), top_k=5, aligned_max_points=400)
    vids = [r["variant_id"] for r in rows]
    assert vids == ["m_ccl", "m_rsi_state"]  # ev 降序; oi/ha_body 被过滤
    assert all(r["max_points"] == 400 for r in rows)
    # 同 cov 的 p3 不得再占 top_k
    run2 = tmp_path / "task_FM" / "experiments" / "run_2026-09-02_12-00-00_y"
    d4 = run2 / "results" / "gen_0" / "p0" / "m_rsi_state_diagnostic_p3" / "diagnostic"
    d4.mkdir(parents=True)
    (d4 / "evaluation_summary.json").write_text(json.dumps(
        _eval_summary("m", "rsi_state", ev=0.99, n=3, pf=2.0)))
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
    _patch_paths(monkeypatch, tmp_path)
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
    assert not (tmp_path / "known_verdicts.inc.md").exists()
    assert not (tmp_path / "pending.jsonl").exists()
    assert not (tmp_path / "STATE.md").exists()

def test_goal_reached_marks_stop_emitted(tmp_path, monkeypatch):
    """goal_reached 干净退出必须先 _mark_stop_emitted, 否则 atexit 兜底误报 unexpected_exit。"""
    monkeypatch.setattr(sup, "_STOP_EMITTED", False)
    monkeypatch.setattr(sup, "build_snapshot", lambda *a, **k: {
        "symbols_hit": {"ss"}, "families_hit": {"volatility"},
        "pass_variant_pf_ratios": [1.123], "variants": {}})
    # 隔离生产 IO (MENU_INC/VERDICTS/报告/事件未被 _patch_paths 重定向)
    monkeypatch.setattr(sup, "materialize_known_verdicts", lambda *a, **k: None)
    monkeypatch.setattr(sup, "materialize_covariate_menu", lambda *a, **k: None)
    monkeypatch.setattr(sup, "write_stop_report", lambda *a, **k: None)
    monkeypatch.setattr(sup, "_emit_event", lambda *a, **k: None)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 5, "last_run_id": None, "paused_429": False}), encoding="utf-8")
    goal = tmp_path / "goal.yaml"
    goal.write_text(
        "goal:\n"
        "  success_condition: ['len(symbols_hit) >= 1',\n"
        "                      'min(pass_variant_pf_ratios) > 1.05',\n"
        "                      'len(families_hit) >= 1']\n"
        "  budgets: {max_cycles: 10, cpu_hours: 60, token_budget_m: 80}\n"
        "  cadence: {survivors_per_cycle: 2, aligned_max_points: 400,\n"
        "            run_budget_hours: 2.0, quota_window_hours: 5.0, quota_margin_min: 30}\n",
        encoding="utf-8")
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    assert sup._STOP_EMITTED is True  # atexit 不会再发 supervisor_stopped/unexpected_exit

def test_cycles_increment_only_after_harvest(tmp_path, monkeypatch):
    monkeypatch.setattr(sup.time, "sleep", lambda s: None)
    monkeypatch.setattr(sup, "_run_active", lambda: True)  # run 仍在
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True})
    _patch_paths(monkeypatch, tmp_path)
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
    _clear_failover_env(monkeypatch)
    calls = []
    def fake_praxist(args, **k):
        calls.append(list(args))
        return {"ok": True, "stdout": ""}
    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
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

def _goal_yaml(tmp_path, max_cycles=10):
    goal = tmp_path / "goal.yaml"
    goal.write_text(
        "goal:\n  success_condition: ['len(symbols_hit) >= 99']\n"
        "  budgets: {max_cycles: %s, cpu_hours: 60, token_budget_m: 80}\n"
        "  cadence: {survivors_per_cycle: 2, aligned_max_points: 400,\n"
        "            run_budget_hours: 2.0, quota_window_hours: 5.0, quota_margin_min: 30}\n"
        % max_cycles,
        encoding="utf-8")
    return goal

def test_429_stop_via_main_once_then_resume(tmp_path, monkeypatch):
    _clear_failover_env(monkeypatch)
    calls = []
    def fake_praxist(args, **k):
        calls.append(list(args))
        return {"ok": True, "stdout": json.dumps({"run_id": "runX", "run_dir": "/tmp/runX"})}
    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (False, 90))
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
        # Already harvested so pause→resume path is not mixed with harvest_empty cycle++
        "last_harvested_run_id": "runX", "paused_429": False,
    }), encoding="utf-8")
    goal = _goal_yaml(tmp_path)
    (tmp_path / "task_FM").mkdir()
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["paused_429"] is True
    assert st.get("cycles_done", 0) == 0
    assert ["stop", "runX"] in calls
    calls.clear()
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    rc2 = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc2 == 0
    st2 = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st2["paused_429"] is False
    assert st2.get("cycles_done", 0) == 0
    assert any(c[:1] == ["resume"] for c in calls)
    assert not any(c[:1] == ["start"] for c in calls)

def test_harvest_survivors_enter_slow_no_start_no_cycle(tmp_path, monkeypatch):
    """有幸存者: harvest 入队, phase=slow, 本 tick 不开下一轮快环, cycles 不加。"""
    calls = []
    pops = []
    def fake_praxist(args, **k):
        calls.append(list(args))
        return {"ok": True, "stdout": json.dumps({"run_id": "runY", "run_dir": "/tmp/runY"})}
    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    monkeypatch.setattr(sup.subprocess, "Popen",
                        lambda *a, **k: pops.append(a) or type("P", (), {"pid": 1})())
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
        "last_harvested_run_id": None, "paused_429": False,
    }), encoding="utf-8")
    run = tmp_path / "task_FM" / "experiments" / "run_2026-09-02_10-00-00_x"
    # peer 已转型为假设作者: 主循环 _harvest_rows 走 harvest_proposals, 读 proposals/*.json
    # (不再产 evaluation_summary.json)。造一份合格机制化提案触发入队 + 进 slow 相。
    pdir = run / "results" / "gen_0" / "p0" / "proposals"
    pdir.mkdir(parents=True)
    (pdir / "m_rsi_state.json").write_text(json.dumps({
        "schema": "fm.hypothesis_proposal.v1",
        "proposal_id": "m_rsi_state",
        "symbol": "m", "cov_override": "rsi_state",
        "covariate_family": "oscillator",
        "mechanism": "RSI(14) 超买超卖体制在豆粕主力合约上有明确的均值回归机制，极端读数后价格倾向回到波动中枢，持仓资金活跃放大反转有效性。",
        "symbol_fit": "豆粕主力持仓资金活跃，RSI 反转信号在主力合约上有效性高。",
        "predicted_direction": "oversold -> long revert",
        "kill_condition": "aligned ev<0 或 ic<0.02",
        "promote_condition": "gate_pass 且 PF>1.05 且 ev>0",
    }), encoding="utf-8")
    goal = _goal_yaml(tmp_path)
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st.get("cycles_done") == 0
    assert st.get("phase") == "slow"
    assert st.get("last_harvested_run_id") == "runX"
    assert st.get("last_run_id") == "runX"
    assert not any(c[:1] == ["start"] for c in calls)
    assert pops, "slow loop Popen should fire same tick"
    vids = [json.loads(line)["variant_id"]
            for line in (tmp_path / "pending.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert "m_rsi_state" in vids


def test_harvest_empty_counts_cycle_and_allows_start(tmp_path, monkeypatch):
    calls = []
    def fake_praxist(args, **k):
        calls.append(list(args))
        return {"ok": True, "stdout": json.dumps({"run_id": "runY", "run_dir": "/tmp/runY"})}
    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
        "last_harvested_run_id": None, "paused_429": False,
    }), encoding="utf-8")
    (tmp_path / "task_FM" / "experiments").mkdir(parents=True)
    goal = _goal_yaml(tmp_path)
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st.get("cycles_done") == 1
    assert st.get("phase") == "fast"
    assert any(c[:1] == ["start"] for c in calls)


def test_slow_drain_counts_cycle_then_start(tmp_path, monkeypatch):
    calls = []
    def fake_praxist(args, **k):
        calls.append(list(args))
        return {"ok": True, "stdout": json.dumps({"run_id": "runY", "run_dir": "/tmp/runY"})}
    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "pending.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "inprogress.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
        "last_harvested_run_id": "runX", "paused_429": False, "phase": "slow",
    }), encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    goal = _goal_yaml(tmp_path)
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st.get("cycles_done") == 1
    assert st.get("phase") == "fast"
    assert any(c[:1] == ["start"] for c in calls)


def test_phase_slow_blocks_start_even_in_window(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sup, "_praxist",
                        lambda args, **k: calls.append(list(args)) or {"ok": True, "stdout": "{}"})
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: True)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "pending.jsonl").write_text(
        json.dumps({"variant_id": "m_ccl", "symbol": "m", "cov_override": "ccl",
                    "max_points": 400, "stage": "aligned", "checkpoint_path": "",
                    "enqueued_at": "t", "src_run": "r"}) + "\n", encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_harvested_run_id": "runX",
        "paused_429": False, "phase": "slow",
    }), encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    goal = _goal_yaml(tmp_path)
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st.get("phase") == "slow"
    assert st.get("cycles_done") == 0
    assert not any(c[:1] == ["start"] for c in calls)


def test_slow_starts_outside_clock_window(tmp_path, monkeypatch):
    pops = []
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True, "stdout": "{}"})
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    monkeypatch.setattr(sup, "_in_slow_window", lambda goal, now=None: False)
    monkeypatch.setattr(sup.subprocess, "Popen",
                        lambda *a, **k: pops.append(a) or type("P", (), {"pid": 1})())
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "pending.jsonl").write_text(
        json.dumps({"variant_id": "m_ccl", "symbol": "m", "cov_override": "ccl",
                    "max_points": 400, "stage": "aligned", "checkpoint_path": "",
                    "enqueued_at": "t", "src_run": "r"}) + "\n", encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_harvested_run_id": "runX",
        "paused_429": False, "phase": "slow",
    }), encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    goal = _goal_yaml(tmp_path)
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    assert pops


def test_ensure_phase_migrates_legacy_state(tmp_path, monkeypatch):
    _clear_failover_env(monkeypatch)
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    (tmp_path / "pending.jsonl").write_text(
        json.dumps({"variant_id": "m_ccl", "symbol": "m", "cov_override": "ccl",
                    "max_points": 400, "stage": "aligned", "checkpoint_path": "",
                    "enqueued_at": "t", "src_run": "r"}) + "\n", encoding="utf-8")
    st = {"cycles_done": 1, "last_run_id": "r", "paused_429": False}
    out = sup.ensure_phase(st)
    assert out["phase"] == "slow"
    (tmp_path / "pending.jsonl").write_text("", encoding="utf-8")
    out2 = sup.ensure_phase({"cycles_done": 0, "paused_429": True})
    assert out2["phase"] == "wait_quota"

def test_tokens_baseline_delta_budget(tmp_path, monkeypatch):
    """Historical disk tokens are a baseline; only the delta counts toward token_budget_m."""
    monkeypatch.setattr(sup.time, "sleep", lambda s: None)
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True})
    # 无慢环在排空: budget_hit 当 tick 必须写 stop 报告。
    # alive=True 会让 _slow_drain_complete() 为 False → 走 drain-defer 分支不退出。
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(sup, "_read_token_m", lambda: (21.0, False))
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
        "last_harvested_run_id": None, "paused_429": False,
    }), encoding="utf-8")
    goal = tmp_path / "goal.yaml"
    goal.write_text(
        "goal:\n  success_condition: ['len(symbols_hit) >= 99']\n"
        "  budgets: {max_cycles: 10, cpu_hours: 60, token_budget_m: 10}\n"
        "  cadence: {survivors_per_cycle: 2, aligned_max_points: 400,\n"
        "            run_budget_hours: 2.0, quota_window_hours: 5.0, quota_margin_min: 30}\n",
        encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0  # absolute 21M would exhaust 10M; delta 0 must not
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["tokens_baseline_m"] == 21.0
    assert not list((tmp_path / "reports").glob("supervisor_budget_exhausted_*.md"))
    monkeypatch.setattr(sup, "_read_token_m", lambda: (31.0, False))
    monkeypatch.setattr(sup, "_STOP_EMITTED", False)
    rc2 = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc2 == 0
    assert list((tmp_path / "reports").glob("supervisor_budget_exhausted_*.md"))
    assert sup._STOP_EMITTED is True  # budget 干净退出同样不得触发 atexit unexpected_exit
    st2 = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st2["tokens_baseline_m"] == 21.0


def test_tok_unknown_skips_token_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(sup.time, "sleep", lambda s: None)
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: True)
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(sup, "_read_token_m", lambda: (0.0, True))
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
        "last_harvested_run_id": None, "paused_429": False,
    }), encoding="utf-8")
    goal = tmp_path / "goal.yaml"
    goal.write_text(
        "goal:\n  success_condition: ['len(symbols_hit) >= 99']\n"
        "  budgets: {max_cycles: 10, cpu_hours: 60, token_budget_m: 0}\n"
        "  cadence: {survivors_per_cycle: 2, aligned_max_points: 400,\n"
        "            run_budget_hours: 2.0, quota_window_hours: 5.0, quota_margin_min: 30}\n",
        encoding="utf-8")
    (tmp_path / "task_FM").mkdir()
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    assert not list((tmp_path / "reports").glob("supervisor_budget_exhausted_*.md"))
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "tokens_baseline_m" not in st


def test_materialize_known_verdicts(tmp_path):
    dest = tmp_path / "known_verdicts.inc.md"
    snap = {"a": _v("m_ccl", gate_pass=True, ev=0.02),
            "b": _v("m_oi", gate_pass=False, ev=-0.01)}
    sup.materialize_known_verdicts(snap, str(dest))
    text = dest.read_text(encoding="utf-8")
    assert "m_ccl" in text and "gate_pass=True" in text
    assert "m_oi" in text and "gate_pass=False" in text


def test_429_failover_resume_not_wait_quota(tmp_path, monkeypatch):
    """paused_429 + Ark banned + failover configured → failover resume, not wait_quota."""
    _set_failover_env(monkeypatch)
    calls = []
    envs = []

    def fake_praxist(args, **k):
        calls.append(list(args))
        envs.append(k.get("env"))
        return {"ok": True, "stdout": ""}

    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(
        __import__("json").dumps({
            "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
            "paused_429": True, "phase": "wait_quota", "llm_provider": "primary",
        }),
        encoding="utf-8",
    )
    tz = __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))
    reset = __import__("datetime").datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz)
    monkeypatch.setattr(sup, "_latest_429_reset", lambda: reset)
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0,
                        "quota_margin_min": 30}}
    now = __import__("datetime").datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)  # before reset
    actions = sup.decide_fast_loop(goal, dry_run=True, now=now)
    names = [a["action"] for a in actions]
    assert "wait_quota" not in names, names
    # Primary run model was claude; Praxist forbids model change on resume → fresh start
    assert "run_started" in names, names
    started = next(a for a in actions if a["action"] == "run_started")
    assert started.get("llm_provider") == "failover"
    assert "--model" in started["argv"]
    assert "qwen3.7-plus" in started["argv"]


def test_active_429_plans_failover_llm(tmp_path, monkeypatch):
    """Active + quota banned + failover → run_failover_llm + planned resume argv."""
    _set_failover_env(monkeypatch)
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True, "stdout": ""})
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(
        __import__("json").dumps({
            "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
            "paused_429": False, "phase": "fast", "llm_provider": "primary",
        }),
        encoding="utf-8",
    )
    tz = __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))
    reset = __import__("datetime").datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz)
    monkeypatch.setattr(sup, "_latest_429_reset", lambda: reset)
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0,
                        "quota_margin_min": 30}}
    now = __import__("datetime").datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)
    actions = sup.decide_fast_loop(goal, dry_run=True, now=now)
    names = [a["action"] for a in actions]
    assert names[0] == "run_failover_llm"
    assert "run_started" in names  # model differs from primary run → fresh start
    assert "wait_quota" not in names
    fo = actions[0]
    assert fo.get("start_argv") and "qwen3.7-plus" in fo["start_argv"]
    assert fo.get("resume_argv") is None
    assert fo.get("llm_provider") == "failover"


def test_praxist_env_selects_failover(monkeypatch):
    _set_failover_env(monkeypatch)
    env = sup._praxist_env("failover")
    assert env["ANTHROPIC_BASE_URL"] == "https://example.test/failover"
    assert env["ANTHROPIC_API_KEY"] == "test-failover-key"
    env_p = sup._praxist_env("primary")
    assert env_p["ANTHROPIC_BASE_URL"] == "https://example.test/primary"


def test_new_run_started_reverts_to_primary(tmp_path, monkeypatch):
    """When Ark ok, NEW run_started leaves failover → primary (no mid-run thrash)."""
    _set_failover_env(monkeypatch)
    calls = []

    def fake_praxist(args, **k):
        calls.append(list(args))
        return {"ok": True, "stdout": __import__("json").dumps(
            {"run_id": "runY", "run_dir": "/tmp/runY"})}

    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "quota_gate", lambda goal, now=None: (True, 0))
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(
        __import__("json").dumps({
            "cycles_done": 1, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
            "last_harvested_run_id": "runX", "paused_429": False, "phase": "fast",
            "llm_provider": "failover", "llm_route": "failover",
        }),
        encoding="utf-8",
    )
    (tmp_path / "task_FM").mkdir()
    goal = _goal_yaml(tmp_path)
    rc = sup.main(["--once", "--goal", str(goal), "--root", str(tmp_path)])
    assert rc == 0
    st = __import__("json").loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st.get("llm_provider") == "primary"
    start = next(c for c in calls if c and c[0] == "start")
    assert "claude-opus-4-7" in start



def test_failover_env_switch_and_model_argv(monkeypatch):
    monkeypatch.setenv("PRIMARY_ANTHROPIC_BASE_URL", "https://ark.example/api/coding")
    monkeypatch.setenv("PRIMARY_ANTHROPIC_API_KEY", "ark-key-xxx")
    monkeypatch.setenv("PRIMARY_MODEL", "claude-opus-4-7")
    monkeypatch.setenv("FAILOVER_ANTHROPIC_BASE_URL", "https://coding.dashscope.aliyuncs.com/apps/anthropic")
    monkeypatch.setenv("FAILOVER_ANTHROPIC_API_KEY", "ds-key-xxx")
    monkeypatch.setenv("FAILOVER_MODEL", "qwen3.7-plus")
    # also accept ANTHROPIC_FAILOVER_* alone
    assert sup._failover_configured() is True
    env_f = sup._praxist_env("failover")
    assert env_f["ANTHROPIC_BASE_URL"].endswith("/apps/anthropic")
    assert env_f["ANTHROPIC_API_KEY"] == "ds-key-xxx"
    assert env_f["PRAXIST_MODEL"] == "qwen3.7-plus"
    assert "ds-key-xxx" not in str(sup._model_argv("failover"))  # argv has model only
    assert sup._model_argv("failover") == ["--model", "qwen3.7-plus"]
    env_p = sup._praxist_env("primary")
    assert env_p["ANTHROPIC_BASE_URL"].startswith("https://ark.example")
    assert env_p["PRAXIST_MODEL"] == "claude-opus-4-7"
    assert sup._model_argv("primary") == ["--model", "claude-opus-4-7"]


def test_anthropic_failover_alias_names(monkeypatch):
    import os as _os
    for k in list(_os.environ.keys()):
        if "FAILOVER" in k or k.startswith("PRIMARY_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_FAILOVER_BASE_URL", "https://coding.dashscope.aliyuncs.com/apps/anthropic")
    monkeypatch.setenv("ANTHROPIC_FAILOVER_API_KEY", "alias-key")
    monkeypatch.setenv("ANTHROPIC_FAILOVER_MODEL", "qwen3.7-plus")
    assert sup._failover_configured() is True
    env = sup._praxist_env("failover")
    assert env["ANTHROPIC_API_KEY"] == "alias-key"
    assert env["PRAXIST_MODEL"] == "qwen3.7-plus"


def test_429_triggers_failover_not_wait_quota(tmp_path, monkeypatch):
    calls = []
    def fake_praxist(args, env=None, **k):
        calls.append({"args": list(args), "base": (env or {}).get("ANTHROPIC_BASE_URL"),
                      "model": (env or {}).get("PRAXIST_MODEL")})
        return {"ok": True, "stdout": "{}", "stderr": ""}
    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(sup, "_active_run_meta",
                        lambda: {"run_id": "runX", "run_dir": "/tmp/runX", "state": "running"})
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    monkeypatch.setenv("FAILOVER_ANTHROPIC_BASE_URL", "https://coding.dashscope.aliyuncs.com/apps/anthropic")
    monkeypatch.setenv("FAILOVER_ANTHROPIC_API_KEY", "ds-key")
    monkeypatch.setenv("FAILOVER_MODEL", "qwen3.7-plus")
    monkeypatch.setenv("PRIMARY_ANTHROPIC_BASE_URL", "https://ark.example/api/coding")
    monkeypatch.setenv("PRIMARY_ANTHROPIC_API_KEY", "ark-key")
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runX", "last_run_dir": "/tmp/runX",
        "paused_429": False, "phase": "fast", "llm_provider": "primary", "llm_route": "primary",
    }), encoding="utf-8")
    tz = timezone(timedelta(hours=8))
    reset = datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz)
    monkeypatch.setattr(sup, "_latest_429_reset", lambda: reset)
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0, "quota_margin_min": 30}}
    now = datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)
    actions = sup.decide_fast_loop(goal, dry_run=True, now=now)
    names = [a["action"] for a in actions]
    assert "run_failover_llm" in names
    assert "wait_quota" not in names
    # live path
    actions2 = sup.decide_fast_loop(goal, dry_run=False, now=now)
    assert any(c["args"][:1] == ["stop"] for c in calls)
    # Primary run has no matching failover model → FRESH start (not resume+qwen)
    assert any(c["args"][:1] == ["start"] and "qwen3.7-plus" in c["args"] for c in calls)
    assert not any(c["args"][:1] == ["resume"] for c in calls)
    start = next(c for c in calls if c["args"][:1] == ["start"])
    assert start["base"].endswith("/apps/anthropic")
    assert start["model"] == "qwen3.7-plus"
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["llm_provider"] == "failover"
    assert st["llm_route"] == "failover"
    assert st.get("paused_429") is False


def test_failover_can_resume_same_run_identity(tmp_path):
    """Resume only when recorded startup model already equals failover model."""
    run = tmp_path / "run_claude"
    run.mkdir()
    (run / "startup_config.json").write_text(json.dumps({
        "canonical_args": {"model": "claude-opus-4-7"},
    }), encoding="utf-8")
    assert sup._failover_can_resume_same_run(str(run)) is False
    assert sup._failover_can_resume_same_run(str(tmp_path / "missing")) is False

    run_q = tmp_path / "run_qwen"
    run_q.mkdir()
    (run_q / "startup_config.json").write_text(json.dumps({
        "canonical_args": {"model": "qwen3.7-plus"},
    }), encoding="utf-8")
    assert sup._failover_can_resume_same_run(str(run_q)) is True


def test_active_429_resumes_when_run_already_failover_model(tmp_path, monkeypatch):
    """If the live run already used qwen, failover may resume same run_dir."""
    _set_failover_env(monkeypatch)
    run = tmp_path / "runQ"
    run.mkdir()
    (run / "startup_config.json").write_text(json.dumps({
        "canonical_args": {"model": "qwen3.7-plus"},
    }), encoding="utf-8")
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True, "stdout": ""})
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(
        sup, "_active_run_meta",
        lambda: {"run_id": "runQ", "run_dir": str(run), "state": "running"},
    )
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runQ", "last_run_dir": str(run),
        "paused_429": False, "phase": "fast", "llm_provider": "primary",
    }), encoding="utf-8")
    tz = timezone(timedelta(hours=8))
    monkeypatch.setattr(
        sup, "_latest_429_reset",
        lambda: datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz),
    )
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0,
                        "quota_margin_min": 30}}
    now = datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)
    actions = sup.decide_fast_loop(goal, dry_run=True, now=now)
    fo = next(a for a in actions if a["action"] == "run_failover_llm")
    assert fo.get("resume_argv") and "qwen3.7-plus" in fo["resume_argv"]
    assert fo.get("start_argv") is None
    assert "run_resumed" in [a["action"] for a in actions]


def test_paused_429_fresh_start_on_identity_wall(tmp_path, monkeypatch):
    """paused_429 + claude run_dir → fresh start, not resume with qwen."""
    _set_failover_env(monkeypatch)
    run = tmp_path / "runC"
    run.mkdir()
    (run / "startup_config.json").write_text(json.dumps({
        "canonical_args": {"model": "claude-opus-4-7"},
    }), encoding="utf-8")
    monkeypatch.setattr(sup, "_praxist", lambda *a, **k: {"ok": True, "stdout": ""})
    monkeypatch.setattr(sup, "_run_active", lambda: False)
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runC", "last_run_dir": str(run),
        "paused_429": True, "phase": "fast", "llm_provider": "failover",
    }), encoding="utf-8")
    tz = timezone(timedelta(hours=8))
    monkeypatch.setattr(
        sup, "_latest_429_reset",
        lambda: datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz),
    )
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0,
                        "quota_margin_min": 30}}
    now = datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)
    actions = sup.decide_fast_loop(goal, dry_run=True, now=now)
    names = [a["action"] for a in actions]
    assert "run_started" in names
    assert "run_resumed" not in names
    assert "wait_quota" not in names


def test_active_failover_run_not_stopped_by_ark_quota(tmp_path, monkeypatch):
    """Live DashScope run must survive Ark quota_gate=False."""
    _set_failover_env(monkeypatch)
    stops = []

    def fake_praxist(args, **k):
        if args and args[0] == "stop":
            stops.append(list(args))
        return {"ok": True, "stdout": ""}

    monkeypatch.setattr(sup, "_praxist", fake_praxist)
    monkeypatch.setattr(sup, "_run_active", lambda: True)
    monkeypatch.setattr(
        sup, "_active_run_meta",
        lambda: {"run_id": "runF", "run_dir": "/tmp/runF", "state": "running"},
    )
    monkeypatch.setattr(sup, "_slow_loop_alive", lambda: False)
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({
        "cycles_done": 0, "last_run_id": "runF", "last_run_dir": "/tmp/runF",
        "paused_429": False, "phase": "fast",
        "llm_provider": "failover", "llm_route": "failover",
    }), encoding="utf-8")
    tz = timezone(timedelta(hours=8))
    monkeypatch.setattr(
        sup, "_latest_429_reset",
        lambda: datetime(2026, 9, 2, 11, 26, 27, tzinfo=tz),
    )
    goal = {"cadence": {"run_budget_hours": 2.0, "quota_window_hours": 5.0,
                        "quota_margin_min": 30}}
    now = datetime(2026, 9, 2, 10, 0, 0, tzinfo=tz)
    actions = sup.decide_fast_loop(goal, dry_run=False, now=now)
    assert stops == []
    assert "run_paused_429" not in [a["action"] for a in actions]
    assert any(a["action"] == "noop" for a in actions)
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st.get("paused_429") is False


def test_failover_env_auth_token_matches_api_key(monkeypatch):
    """Stale primary AUTH_TOKEN must not survive failover overlay."""
    monkeypatch.setenv("PRIMARY_ANTHROPIC_BASE_URL", "https://ark.example/api/coding")
    monkeypatch.setenv("PRIMARY_ANTHROPIC_API_KEY", "ark-primary-key")
    monkeypatch.setenv("PRIMARY_MODEL", "claude-opus-4-7")
    monkeypatch.setenv("FAILOVER_ANTHROPIC_BASE_URL", "https://coding.dashscope.aliyuncs.com/apps/anthropic")
    monkeypatch.setenv("FAILOVER_ANTHROPIC_API_KEY", "sk-failover-key")
    monkeypatch.setenv("FAILOVER_MODEL", "qwen3.7-plus")
    # Poison process env the way a sourced .env.praxist leaves it
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ark-primary-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ark-primary-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://ark.example/api/coding")
    env = sup._praxist_env("failover")
    assert env["ANTHROPIC_API_KEY"] == "sk-failover-key"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-failover-key"
    assert env["ANTHROPIC_AUTH_TOKEN"] != "ark-primary-key"
    assert "dashscope" in env["ANTHROPIC_BASE_URL"]


# ── n-不足型近失误自动复测 (cj_oi: PF1.133/ev19.46/ic0.08 全过, 仅 n=324<350) ──

def _aligned_verdict(vid, symbol, cov, n, pf, ev, ic, gate, status="ok",
                     max_points=600):
    return {"variant_id": vid, "symbol": symbol, "cov_override": cov,
            "max_points": max_points, "n": n, "pf": pf, "ev": ev, "maxdd": -0.2,
            "dir_acc": 0.5 + ic / 2.0, "gate_pass": gate, "ic": ic,
            "decided_at": "2026-09-08T00:00:00", "checkpoint_path": "",
            "slow_loop_pid": 1, "git_rev": "x", "schema": "fm.aligned_verdict.v1",
            "status": status}

def test_retest_candidates_only_n_near_miss():
    snap = {
        # 近失误: n<350, ic/ev/pf-ratio 全过 → 入选
        "cj_oi": _aligned_verdict("cj_oi", "cj", "oi", 324, 1.133, 19.46, 0.08, False),
        # n 已达标但 gate False (ic 不足) → 不入选
        "ss_nvi": _aligned_verdict("ss_nvi", "ss", "nvi", 396, 1.068, 6.34, 0.036, False),
        # 已过门 → 不入选
        "ss_vor": _aligned_verdict("ss_vor", "ss", "vor", 396, 1.123, 11.06, 0.06, True),
        # no_data 不进 dead → 不入选
        "lh_x": _aligned_verdict("lh_x", "lh", "oi", 0, 0.0, 0.0, 0.0, False,
                                 status="no_data"),
        # n<350 但 pf/ev 不过 → 不入选 (加样本也无意义)
        "m_bad": _aligned_verdict("m_bad", "m", "oi", 300, 0.9, -1.0, 0.08, False),
    }
    assert [v["variant_id"] for v in sup._retest_candidates(snap)] == ["cj_oi"]

def test_maybe_enqueue_retests_gating_and_dedup(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    with open(sup.REGISTRY, "w", encoding="utf-8") as f:
        f.write(json.dumps(_aligned_verdict(
            "cj_oi", "cj", "oi", 324, 1.133, 19.46, 0.08, False)) + "\n")
    log = str(tmp_path / "decisions.jsonl")
    goal = {"cadence": {"aligned_max_points": 600, "retest_min_new_points": 1}}
    live_n = {"cj": 324}
    monkeypatch.setattr(sup, "_valid_n_for_symbol", lambda s: live_n.get(s))
    # 数据未增长到硬门样本量 → 不排队
    assert sup._maybe_enqueue_retests(goal, log) == 0
    assert not os.path.exists(sup.QUEUE)
    # 本地库 n>=350 → 旁路 dead 去重排队, phase=slow
    live_n["cj"] = 350
    assert sup._maybe_enqueue_retests(goal, log) == 1
    rows = sup.rl.queue_load(sup.QUEUE)
    assert [r["variant_id"] for r in rows] == ["cj_oi"]
    assert rows[0]["source"] == "sample_retest"
    assert json.load(open(sup.STATE_PATH, encoding="utf-8"))["phase"] == "slow"
    # 已在队列 → 不重复
    assert sup._maybe_enqueue_retests(goal, log) == 0
    assert len(sup.rl.queue_load(sup.QUEUE)) == 1

def test_maybe_enqueue_retests_respects_margin(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    with open(sup.REGISTRY, "w", encoding="utf-8") as f:
        f.write(json.dumps(_aligned_verdict(
            "cj_oi", "cj", "oi", 324, 1.133, 19.46, 0.08, False)) + "\n")
    goal = {"cadence": {"aligned_max_points": 600, "retest_min_new_points": 30}}
    monkeypatch.setattr(sup, "_valid_n_for_symbol", lambda s: 350)
    # 350-324=26 < margin 30 → 不排队
    assert sup._maybe_enqueue_retests(goal, str(tmp_path / "d.jsonl")) == 0
    assert not os.path.exists(sup.QUEUE)

def test_maybe_enqueue_retests_fail_open_on_db_error(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    with open(sup.REGISTRY, "w", encoding="utf-8") as f:
        f.write(json.dumps(_aligned_verdict(
            "cj_oi", "cj", "oi", 324, 1.133, 19.46, 0.08, False)) + "\n")
    goal = {"cadence": {"retest_min_new_points": 1}}
    monkeypatch.setattr(sup, "_valid_n_for_symbol", lambda s: None)
    # DB 查询失败 → 0 排队, 不抛
    assert sup._maybe_enqueue_retests(goal, str(tmp_path / "d.jsonl")) == 0

def test_menu_renders_symbol_sample_ceiling(monkeypatch, tmp_path):
    monkeypatch.setattr(sup, "_symbol_n_table",
                        lambda: [("cj", 324), ("m", 396), ("lh", None)])
    dest = str(tmp_path / "menu.md")
    sup.materialize_covariate_menu({}, dest)
    txt = open(dest, encoding="utf-8").read()
    assert "cj: n=324 BELOW GATE" in txt
    assert "m: n=396 gate-reachable" in txt
    assert "lh: n=? unknown" in txt

def test_production_goal_yaml_tier1_expansion():
    goal_fp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "scripts", "praxist_goal.yaml")
    goal = sup.load_goal(goal_fp)
    conds = goal["success_condition"]
    # 当前生产状态: 仅 ss_vor 过门 → 扩目标后未达成
    snap = {"symbols_hit": {"ss"}, "families_hit": {"vor"},
            "pass_variant_pf_ratios": [1.123]}
    ok, why = sup.evaluate_goal(conds, snap)
    assert ok is False and any("symbols_hit" in w for w in why)
    # 4 个 1 星品种过门 → 达成 (含 2 星品种不额外计数)
    snap2 = {"symbols_hit": {"ss", "m", "sr", "jd", "ao"},
             "families_hit": {"vor", "oi"}, "pass_variant_pf_ratios": [1.1, 1.08]}
    ok2, _ = sup.evaluate_goal(conds, snap2)
    assert ok2 is True
    # 只有 3 个 1 星 (即使加 2 星凑数) → 仍未达成
    snap3 = {"symbols_hit": {"ss", "m", "ao", "bu"},
             "families_hit": {"vor"}, "pass_variant_pf_ratios": [1.1]}
    ok3, _ = sup.evaluate_goal(conds, snap3)
    assert ok3 is False

