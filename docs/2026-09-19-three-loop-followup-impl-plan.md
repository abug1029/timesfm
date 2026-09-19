# 三环 Verdict 跟进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让三环在 `cohort_size=2` 下能产出有效 PI 议程，并停止把慢环座位浪费在已证伪品种和重复提案上；同时把自适应硬门的实际门槛写进 verdict。

**Architecture:** 不改 Praxist 发行包。门槛公式抽成 `compute_effective_min` 并落库；任务侧 topology 插件把必填角色收成 `{exploit, falsifier}`；supervisor 用一份 `symbol_status.json` 同时喂 prompt、harvest 和评分。

**Tech Stack:** Python 3.11（`/home/abug/timesfm/.venv`）、pytest、PyYAML、Praxist 0.5 任务侧 plugin（`task_FM/.praxist/plugins/`）。

**Spec:** `docs/2026-09-19-three-loop-followup-spec.md`

## Global Constraints

- 禁止修改 `/home/abug/timesfm/.venv` 内 Praxist 源码。
- 禁止修改 `gate()` 自适应公式：`effective_min = max(0.50, min(0.52, baseline_dir_acc))`，baseline 缺失时为 0.52。
- 禁止把协变量族整族 `archived`。
- 禁止修 launcher `Event loop is closed`。
- 测试命令一律：`/home/abug/timesfm/.venv/bin/python -m pytest <path> -v`。
- Windows 宿主必须经 `wsl -d Ubuntu-22.04 -- bash -lc '...'` 读/改本仓。

---

## File map

| 文件 | 职责 |
|---|---|
| `task_FM/evaluations/fm_eval/evaluator.py` | `compute_effective_min`；`gate`/`build_summary` 写出 `baseline_dir_acc`、`effective_min` |
| `scripts/registry_lib.py` | v2 schema 与墓碑带上这两个可空字段 |
| `task_FM/.praxist/plugins/panel_topologies/fm_two_peer/plugin.yaml` | 任务侧 topology，`peer_role_rotation: [exploit, falsifier]` |
| `task_FM/task.yaml` | `panel.topology` 改指向 `panel_topology:fm_two_peer` |
| `task_FM/config/symbol_status.json` | 品种 DEAD/HOLD 唯一家 |
| `scripts/praxist_supervisor.py` | 读状态表；prompt 注入已提案 vid + 品种摘要；评分惩罚；harvest 拒绝 |
| `tests/test_praxist_fm_evaluator.py` | 门槛可观测 |
| `tests/test_verdict_registry.py` | 墓碑字段 |
| `tests/test_fm_two_peer_topology.py` | rotation 与 cohort_size 对账 |
| `tests/test_supervisor.py` | known_verdicts / 评分 |
| `tests/test_harvest_proposals.py` | DEAD/HOLD 拒绝 |

---

### Task 1: 门槛公式单点化并写入 verdict

**Files:**
- Modify: `task_FM/evaluations/fm_eval/evaluator.py`（`gate` 约 L392、`build_summary` 约 L255）
- Modify: `scripts/registry_lib.py`（`VERDICT_FIELDS_V2`、`make_error_tombstone`、`make_timeout_tombstone`）
- Test: `tests/test_praxist_fm_evaluator.py`
- Test: `tests/test_verdict_registry.py`

**Interfaces:**
- Consumes: 现行 `gate(s, min_n=350, min_n_eff=50, min_dir_acc=0.52, baseline_dir_acc=None)`
- Produces:

```python
def compute_effective_min(min_dir_acc=0.52, baseline_dir_acc=None) -> float:
    ...
```

`build_summary(...)` 的返回 dict 增加 `baseline_dir_acc: float | None`、`effective_min: float | None`（`metrics` 子 dict 同样有这两键）。

- [ ] **Step 1: 写失败测试（自适应门槛 + 落库字段）**

在 `tests/test_praxist_fm_evaluator.py` 追加：

```python
def test_compute_effective_min_matches_v23():
    assert fm.compute_effective_min(0.52, 0.486) == 0.50
    assert fm.compute_effective_min(0.52, 0.502) == 0.502
    assert fm.compute_effective_min(0.52, 0.55) == 0.52
    assert fm.compute_effective_min(0.52, None) == 0.52


def test_gate_m_pca_momentum_repro():
    s = {"n": 588, "n_eff": 73, "dir_acc": 0.502}
    assert fm.gate(s, baseline_dir_acc=0.486) is True
    assert fm.gate(s) is False


def test_gate_sr_crack_spread_repro():
    s = {"n": 588, "n_eff": 73, "dir_acc": 0.510}
    assert fm.gate(s, baseline_dir_acc=0.502) is True
    assert fm.gate(s, baseline_dir_acc=0.55) is False


def test_build_summary_persists_effective_min(tmp_path):
    s = _summarize_v23(n=400, n_eff=400, dir_acc=0.502)
    cand = {"symbol": "m", "cov_override": "pca_momentum", "max_points": 6, "stage": "aligned"}
    out = fm.build_summary(s, cand, baseline_dir_acc=0.486, batch_id="b1")
    assert out["gate_pass"] is True
    assert out["baseline_dir_acc"] == 0.486
    assert out["effective_min"] == 0.50
    assert out["metrics"]["effective_min"] == 0.50
    assert out["metrics"]["baseline_dir_acc"] == 0.486
```

在 `tests/test_verdict_registry.py` 给墓碑断言追加：

```python
assert t.get("baseline_dir_acc") is None
assert t.get("effective_min") is None
```

（改 `make_error_tombstone` 的现有测试，不要另起不跑的测试。）

- [ ] **Step 2: 跑测试，确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_praxist_fm_evaluator.py::test_compute_effective_min_matches_v23 /home/abug/timesfm/tests/test_praxist_fm_evaluator.py::test_gate_m_pca_momentum_repro -v'
```

Expected: FAIL，`compute_effective_min` 未定义。

- [ ] **Step 3: 最小实现**

在 `evaluator.py` 的 `gate()` 上方新增并改 `gate`：

```python
def compute_effective_min(min_dir_acc=0.52, baseline_dir_acc=None):
    if baseline_dir_acc is not None:
        return max(0.50, min(float(min_dir_acc), float(baseline_dir_acc)))
    return float(min_dir_acc)


def gate(s, min_n=350, min_n_eff=50, min_dir_acc=0.52, baseline_dir_acc=None):
    ...
    effective_min = compute_effective_min(min_dir_acc, baseline_dir_acc)
    return dir_acc >= effective_min
```

`build_summary` 在算出 `gate_pass` 之后：

```python
effective_min = compute_effective_min(0.52, baseline_dir_acc)
...
"baseline_dir_acc": baseline_dir_acc,
"effective_min": effective_min,
```

`metrics` 同样写入。gated 协变量分支仍只换 `gate()` 的输入 dict，不改公式。

`registry_lib.py`：

```python
VERDICT_FIELDS_V2 = {..., "baseline_dir_acc", "effective_min"}
VERDICT_FIELDS_V2_NULLABLE = {..., "baseline_dir_acc", "effective_min"}
```

`make_error_tombstone` 与 `make_timeout_tombstone` 顶层加 `"baseline_dir_acc": None, "effective_min": None`。

- [ ] **Step 4: 跑测试，确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_praxist_fm_evaluator.py /home/abug/timesfm/tests/test_verdict_registry.py /home/abug/timesfm/tests/test_fm_evaluator_gated.py -v'
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add task_FM/evaluations/fm_eval/evaluator.py scripts/registry_lib.py tests/test_praxist_fm_evaluator.py tests/test_verdict_registry.py
git commit -m "feat: persist adaptive gate effective_min on aligned verdicts"
```

---

### Task 2: 两 peer 的 topology 插件

**Files:**
- Create: `task_FM/.praxist/plugins/panel_topologies/fm_two_peer/plugin.yaml`
- Modify: `task_FM/task.yaml`（`praxist_plugins.panel.topology`）
- Test: `tests/test_fm_two_peer_topology.py`
- Modify: `tests/test_praxist_evidence_ladder.py`（去掉 `test_task_cohort_covers_four_pi_roles` 的 xfail，改成 rotation 对账）

**Interfaces:**
- Consumes: bundled `legacy_multi_pi_two_round` 的 topology 主体（modes/roles/rounds 原样复制）
- Produces: `topology_ref: panel_topology:fm_two_peer`；`peer_role_rotation == ("exploit", "falsifier")`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_fm_two_peer_topology.py`：

```python
import os
import yaml

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK = os.path.join(FM_ROOT, "task_FM", "task.yaml")
PLUGIN = os.path.join(
    FM_ROOT, "task_FM", ".praxist", "plugins",
    "panel_topologies", "fm_two_peer", "plugin.yaml",
)


def test_plugin_exists_and_rotation_matches_cohort():
    assert os.path.exists(PLUGIN)
    plugin = yaml.safe_load(open(PLUGIN, encoding="utf-8"))
    task = yaml.safe_load(open(TASK, encoding="utf-8"))
    rotation = plugin["topology"]["peer_role_rotation"]
    cohort = task["generation_policy"]["cohort_size"]
    assert cohort == 2
    assert rotation == ["exploit", "falsifier"]
    assert len(rotation) == cohort
    assert task["praxist_plugins"]["panel"]["topology"] == "panel_topology:fm_two_peer"
    assert plugin["topology"]["topology_ref"] == "panel_topology:fm_two_peer"
```

同时改 `tests/test_praxist_evidence_ladder.py`：删除 `test_task_cohort_covers_four_pi_roles`（含 xfail）。用新名 `test_task_cohort_matches_peer_role_rotation` 做正向断言：`cohort_size==2` 且 plugin rotation 恰好为 `["exploit","falsifier"]`。禁止再要求 `cohort_size >= 4`，禁止继续 xfail。

- [ ] **Step 2: 跑测试，确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_fm_two_peer_topology.py -v'
```

Expected: FAIL，插件文件不存在。

- [ ] **Step 3: 最小实现**

1. 把 `/home/abug/timesfm/.venv/lib/python3.11/site-packages/praxist/plugins/panel_topologies/legacy_multi_pi_two_round/plugin.yaml` 复制为 `task_FM/.praxist/plugins/panel_topologies/fm_two_peer/plugin.yaml`。
2. 只改这些字段（其余 rounds/roles 保持）：

```yaml
name: fm_two_peer
stability: experimental
description: "FM_a two-peer Chair rotation: exploit + falsifier (cohort_size=2)."
capabilities:
  - panel.multi_pi
  - panel.round1_independent_memos
  - panel.round2_cross_review
  - panel.chair_agenda
  - panel.executable_legacy_executor
  - panel.peer_role_rotation
topology:
  topology_ref: panel_topology:fm_two_peer
  peer_role_rotation:
    - exploit
    - falsifier
  peer_role_descriptions:
    exploit: "Refine near-miss symbol x cov with a sharper mechanism and kill/promote."
    falsifier: "Do not chase the leaderboard; author a proposal that would disprove the mainline mechanism."
```

`stability: experimental` 对 task-local 插件是允许的（Praxist 对 `source=task_project` 跳过 bundled 的 v1_stable 检查）。

3. `task_FM/task.yaml`：

```yaml
praxist_plugins:
  panel:
    topology: panel_topology:fm_two_peer
```

其它键不动。

- [ ] **Step 4: 跑测试，确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_fm_two_peer_topology.py /home/abug/timesfm/tests/test_praxist_evidence_ladder.py::test_task_cohort_matches_peer_role_rotation /home/abug/timesfm/tests/test_praxist_task_contract.py -v'
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add task_FM/.praxist/plugins/panel_topologies/fm_two_peer/plugin.yaml task_FM/task.yaml tests/test_fm_two_peer_topology.py tests/test_praxist_evidence_ladder.py
git commit -m "feat: two-peer PI rotation exploit+falsifier for cohort_size=2"
```

---

### Task 3: 品种状态表 + harvest 拒绝

**Files:**
- Create: `task_FM/config/symbol_status.json`
- Modify: `scripts/praxist_supervisor.py`（新 `load_symbol_status`、改 `harvest_proposals`）
- Test: `tests/test_harvest_proposals.py`

**Interfaces:**
- Consumes: `task_FM/config/symbol_status.json`
- Produces:

```python
def load_symbol_status(path=None) -> dict:
    """Return {symbol: {"status": "DEAD"|"HOLD"|"ACTIVE", ...}}. Missing file -> {}."""
```

`harvest_proposals(...)` 在组成 `vid` 之后、`dedup` 之前：若 `status==DEAD` 则 `_reject("symbol_dead")`；`HOLD` 则 `_reject("symbol_hold")`。

- [ ] **Step 1: 写失败测试**

`tests/test_harvest_proposals.py` 追加：

```python
def test_dead_symbol_rejected(tmproot, monkeypatch):
    status_path = os.path.join(tmproot, "symbol_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"schema": "fm.symbol_status.v1", "symbols": {
            "eg": {"status": "DEAD", "reason": "x"},
            "jd": {"status": "HOLD", "hold_generations": 5, "reason": "y"},
        }}, f)
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", status_path)
    _make_run(tmproot, _prop(symbol="eg", cov="oi"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert "symbol_dead" in stats["reject_reasons"]


def test_hold_symbol_rejected(tmproot, monkeypatch):
    status_path = os.path.join(tmproot, "symbol_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"schema": "fm.symbol_status.v1", "symbols": {
            "jd": {"status": "HOLD", "hold_generations": 5, "reason": "y"},
        }}, f)
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", status_path)
    _make_run(tmproot, _prop(symbol="jd", cov="ccl"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 0
    assert "symbol_hold" in stats["reject_reasons"]


def test_active_symbol_still_enqueued(tmproot, monkeypatch):
    status_path = os.path.join(tmproot, "symbol_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"schema": "fm.symbol_status.v1", "symbols": {
            "eg": {"status": "DEAD", "reason": "x"},
        }}, f)
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", status_path)
    _make_run(tmproot, _prop(symbol="m", cov="vor"))
    rows, stats = _harvest(tmproot)
    assert stats["selected"] == 1
    assert rows[0]["variant_id"] == "m_vor"
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_harvest_proposals.py::test_dead_symbol_rejected -v'
```

Expected: FAIL，`SYMBOL_STATUS_PATH` 不存在或拒绝原因未出现。

- [ ] **Step 3: 最小实现**

`task_FM/config/symbol_status.json`：

```json
{
  "schema": "fm.symbol_status.v1",
  "updated": "2026-09-19",
  "symbols": {
    "eg": {"status": "DEAD", "reason": "22 ok verdicts, 0 pass, best dir_acc=0.490"},
    "jd": {"status": "HOLD", "hold_generations": 5, "reason": "7 ok verdicts, 0 pass, best=0.468"},
    "lh": {"status": "HOLD", "hold_generations": 5, "reason": "7 ok verdicts, 0 pass, best=0.488"}
  }
}
```

`praxist_supervisor.py` 在其它 PATH 常量旁：

```python
SYMBOL_STATUS_PATH = os.path.join(FM_ROOT, "task_FM", "config", "symbol_status.json")


def load_symbol_status(path=None):
    p = path or SYMBOL_STATUS_PATH
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f) or {}
        out = {}
        for sym, rec in (raw.get("symbols") or {}).items():
            if not isinstance(rec, dict):
                continue
            st = str(rec.get("status") or "ACTIVE").upper()
            if st in ("DEAD", "HOLD", "ACTIVE"):
                out[str(sym).lower()] = rec
        return out
    except Exception as e:
        print("[WARN] symbol_status load failed (fail-open): %s" % e, file=sys.stderr)
        return {}
```

`harvest_proposals` 开头 `status_map = load_symbol_status()`。在 `vid = "%s_%s" % (symbol, cov)` 之后：

```python
sym_st = str((status_map.get(symbol) or {}).get("status") or "ACTIVE").upper()
if sym_st == "DEAD":
    _reject("symbol_dead"); continue
if sym_st == "HOLD":
    _reject("symbol_hold"); continue
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_harvest_proposals.py -v'
```

Expected: PASS（含原有入队/去重用例）。

- [ ] **Step 5: Commit**

```bash
git add task_FM/config/symbol_status.json scripts/praxist_supervisor.py tests/test_harvest_proposals.py
git commit -m "feat: reject DEAD/HOLD symbols at proposal harvest"
```

---

### Task 4: known_verdicts 注入品种表与已提案 vid

**Files:**
- Modify: `scripts/praxist_supervisor.py`（`materialize_known_verdicts` 约 L513）
- Test: `tests/test_supervisor.py`（现有 `test_materialize_known_verdicts` 必须继续绿）

**Interfaces:**
- Consumes: snapshot dict；可选 `proposed_ids: set[str]`、`status_map: dict`、`queue_ids: set[str]`
- Produces: markdown 含 `## Symbol status`、`## Do not re-propose`、原有 verdict 列表

签名保持可调用 `materialize_known_verdicts(snapshot, dest_path)`。新增可选参数，缺省时扫描 `QUEUE`/`INPROGRESS` 与最新 `run_*` 的 proposals。

```python
def collect_proposed_variant_ids(root) -> set:
    """Parse results/**/proposals/*.json into {symbol_cov}."""

def materialize_known_verdicts(snapshot, dest_path, *, proposed_ids=None,
                               status_map=None, queue_ids=None, root=None):
    ...
```

- [ ] **Step 1: 写失败测试**

`tests/test_supervisor.py` 追加（保留原 `test_materialize_known_verdicts`）：

```python
def test_materialize_known_verdicts_symbol_table_and_proposed(tmp_path):
    dest = tmp_path / "known_verdicts.inc.md"
    snap = {
        "eg_oi": _v("eg_oi", gate_pass=False, dir_acc=0.45, symbol="eg"),
        "eg_ccl": _v("eg_ccl", gate_pass=False, dir_acc=0.44, symbol="eg"),
        "m_oi": _v("m_oi", gate_pass=True, dir_acc=0.55, symbol="m"),
    }
    for rec in snap.values():
        rec["symbol"] = rec.get("symbol") or rec["variant_id"].split("_")[0]
    sup.materialize_known_verdicts(
        snap, str(dest),
        proposed_ids={"jd_ccl", "sr_qstick"},
        status_map={"eg": {"status": "DEAD", "reason": "22 fail"}},
        queue_ids={"m_vor"},
    )
    text = dest.read_text(encoding="utf-8")
    assert "SYMBOL_DEAD" in text
    assert "eg:" in text
    assert "jd_ccl" in text
    assert "sr_qstick" in text
    assert "m_vor" in text
    assert "Do not re-propose" in text
```

若现有 `_v()` 不写 `symbol`，测试里显式补。

- [ ] **Step 2: 跑测试，确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_supervisor.py::test_materialize_known_verdicts_symbol_table_and_proposed -v'
```

Expected: FAIL，文案不含 `SYMBOL_DEAD` / `Do not re-propose`。

- [ ] **Step 3: 最小实现**

`materialize_known_verdicts` 在现有 20 条列表之前插入两段：

```
## Symbol status
- eg: SYMBOL_DEAD, n_ok=2, n_pass=0, best=0.450 — 22 fail
- m: ACTIVE, n_ok=1, n_pass=1, best=0.550

## Do not re-propose (variant_id)
- eg_ccl (verdict)
- eg_oi (verdict)
- jd_ccl (proposed)
- m_vor (queue)
- sr_qstick (proposed)
```

实现要点：

- 对 `GOAL_SYMBOLS_SET` 逐个汇总 snapshot（`status==ok` 计 n_ok；`gate_pass` 计 n_pass；`best` 取最大 dir_acc）。
- 状态优先 `status_map`，否则 ACTIVE。
- 禁止再提案集合 = snapshot keys ∪ queue_ids ∪ proposed_ids，每条标注来源；超过 80 条截断并写 `truncated=N`。
- 品种表**不截断**。
- 原 20 条亮点块保留，header 文案不要回退到「gate_pass=True: already solved」。

`collect_proposed_variant_ids`：只扫 `task_FM/experiments/run_*/results/**/proposals/*.json`，解析 `symbol`+`cov_override`，坏 JSON 跳过。

现有调用点 `materialize_known_verdicts(snap, VERDICTS_INC)` 改为传入 `status_map=load_symbol_status()`、`queue_ids=rl.in_flight_ids(QUEUE, INPROGRESS)`、`proposed_ids=collect_proposed_variant_ids(FM_ROOT)`。两处调用（约 L1622、L1697）都要传。

- [ ] **Step 4: 跑测试，确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_supervisor.py::test_materialize_known_verdicts /home/abug/timesfm/tests/test_supervisor.py::test_materialize_known_verdicts_symbol_table_and_proposed -v'
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_supervisor.py
git commit -m "feat: inject symbol stats and proposed ids into known_verdicts"
```

---

### Task 5: 评分函数的品种失败惩罚

**Files:**
- Modify: `scripts/praxist_supervisor.py`（`_proposal_priority_score` 约 L588）
- Test: `tests/test_supervisor.py`（现有 `test_proposal_score_exploration_bias` 与 `test_proposal_score_guards` 必须同步期望值——本任务的失败惩罚在那些夹具里 n_fail=0 或 1，期望分数应保持不变）

**Interfaces:**
- Consumes: 现行 score 组成；`load_symbol_status()`
- Produces: 返回值仍是 float；新项：

```
n_fail = count(symbol==S and status==ok and gate_pass==False)
penalty = 0                     if n_fail < 3
        = 4 * (n_fail - 2)      if 3 <= n_fail < 8
        = 24 + 8 * (n_fail - 7) if n_fail >= 8
score -= penalty
if status DEAD: score -= 50
if status HOLD: score -= 20
```

- [ ] **Step 1: 写失败测试**

```python
def test_proposal_score_symbol_fail_penalty():
    prop = {"symbol_fit": "f", "kill_condition": "k", "promote_condition": "p"}
    fail_snap = {
        "eg_c%d" % i: {
            "variant_id": "eg_c%d" % i, "symbol": "eg", "cov_override": "c%d" % i,
            "status": "ok", "gate_pass": False, "dir_acc": 0.45,
        }
        for i in range(8)
    }
    eg = sup._proposal_priority_score(prop, "oi", "eg", fail_snap)
    sr = sup._proposal_priority_score(prop, "oi", "sr", fail_snap)
    # sr: 机制3 + 新颖5 + 探索6 = 14；eg 同结构再减 24+8=32 → -18
    assert abs(sr - 14.0) < 1e-9, sr
    assert abs(eg - (14.0 - 32.0)) < 1e-9, eg


def test_proposal_score_symbol_status_penalty(monkeypatch):
    prop = {"symbol_fit": "f", "kill_condition": "k", "promote_condition": "p"}
    monkeypatch.setattr(sup, "load_symbol_status", lambda: {
        "eg": {"status": "DEAD"}, "jd": {"status": "HOLD"},
    })
    base = sup._proposal_priority_score(prop, "oi", "sr", {})
    dead = sup._proposal_priority_score(prop, "oi", "eg", {})
    hold = sup._proposal_priority_score(prop, "oi", "jd", {})
    assert abs(dead - (base - 50.0)) < 1e-9
    assert abs(hold - (base - 20.0)) < 1e-9
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_supervisor.py::test_proposal_score_symbol_fail_penalty -v'
```

Expected: FAIL，eg 与 sr 分数相同。

- [ ] **Step 3: 最小实现**

在 `_proposal_priority_score` 现行 `return score` 之前：

```python
n_fail = 0
for v in (snapshot or {}).values():
    if v.get("symbol") == symbol and v.get("status", "ok") == "ok" and not v.get("gate_pass"):
        n_fail += 1
if n_fail >= 8:
    score -= 24.0 + 8.0 * (n_fail - 7)
elif n_fail >= 3:
    score -= 4.0 * (n_fail - 2)
st = str((load_symbol_status().get(symbol) or {}).get("status") or "ACTIVE").upper()
if st == "DEAD":
    score -= 50.0
elif st == "HOLD":
    score -= 20.0
return score
```

不要改履历/探索项。`test_proposal_score_exploration_bias` 夹具里失败条数为 0，分数应仍是 15.6/14/18.6/13。

- [ ] **Step 4: 跑测试，确认通过**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_supervisor.py -k proposal_score -v'
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/praxist_supervisor.py tests/test_supervisor.py
git commit -m "feat: penalize high-failure symbols in proposal scoring"
```

---

### Task 6: 回归门

**Files:** 不新增生产文件。

**Interfaces:** 无。

- [ ] **Step 1: 跑本 spec 触及的测试集**

```bash
wsl -d Ubuntu-22.04 -- bash -lc '/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_praxist_fm_evaluator.py /home/abug/timesfm/tests/test_fm_evaluator_gated.py /home/abug/timesfm/tests/test_verdict_registry.py /home/abug/timesfm/tests/test_fm_two_peer_topology.py /home/abug/timesfm/tests/test_harvest_proposals.py /home/abug/timesfm/tests/test_supervisor.py /home/abug/timesfm/tests/test_praxist_task_contract.py /home/abug/timesfm/tests/test_praxist_evidence_ladder.py -v'
```

Expected: PASS。

- [ ] **Step 2: 扫 diff 里是否出现 test.skip / TODO / 未实现分支**

没有才算完。禁止把「等下次快环再看 agenda」当作本任务完成证据——完成证据是测试绿 + 文件落地。

- [ ] **Step 3: 若有提交未推送，保持本地，不推** 除非宿主明确要求。

---

## Self-review

1. **Spec coverage:** P0-1→Task 1；P0-2→Task 2；P1-1 DEAD/HOLD→Task 3+5；P1-2 去重→Task 4；P2 与族归档按 spec 非目标，无任务。
2. **Placeholder scan:** 无 TBD；测试代码与命令均为可执行原文。
3. **Type consistency:** `load_symbol_status` / `collect_proposed_variant_ids` / `compute_effective_min` 名称在后续任务中与定义一致。
