# 提案质量后续五步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用现有拒绝码只读回放审计窗口里的提案，只有结论是 `reserve_last_seat` 时才改最后一席；同一品种同一协变量的可确认失败必须在 `failure_delta` 里点名 `variant_id`；提示词改成与收割相同的配对条件，并加一个只读计数脚本。

**Architecture:** 先把 `harvest_proposals` 里从已读入的提案字典到成功增量门的判断收成 `classify_loaded_proposal`，收割和回放都调用它。回放不调用 `harvest_proposals`。选座函数只在回放 JSON 的 `decision` 为 `reserve_last_seat` 时加入，函数里不写 `inventory` 或 `calendar`。点名规则在回放落盘之后才进分类函数。提示词只改 `prompt_base.jinja2`。计数函数 `census` 只返回字典，期望数字只放在它的 `main`。

**Tech Stack:** 活仓 `/home/abug/timesfm`，解释器 `/home/abug/timesfm/.venv/bin/python`（Python 3.11），pytest 9。不引入新依赖。

**Spec:** `/home/abug/timesfm/docs/superpowers/specs/2026-11-18-proposal-followup-design.md`

**2026-11-19 审阅：** `docs/superpowers/reports/优化建议.txt` 批准按本计划执行，不改任务划分。三处编码注意已经写进对应步骤：Task 1 第 6 点要求族计数从提案字典查活跃池，不用提前返回时还没有的 `extra["family"]`；Task 2 的禁词检查连文档字符串和注释一起看；Task 5 的 `runs` 按 `RUN_IDS` 原顺序，并且 `def main` 之前不出现账本数字。

## Global Constraints

规格已经锁定。每个任务都带上下面这些限制。

- 代码基线是活仓 `master` 的 `50c848b09545230b4f0cc2d87556ca294829841f`。上一份提示词改动还没提交，必须留在工作区里。本计划在那些改动之上追加。
- 实施前先跑 `pgrep -af '[p]raxist_supervisor.py'`。有进程就停，不改活树上的 Python，也不从 `master` 开工作树。从 `master` 开工作树会丢掉尚未提交的三份提示词。没有进程才改 `/home/abug/timesfm`。
- 不重启监督环，不杀进程，不跑 `scripts/restart_three_loop_clean.sh`。提示词在下一次由宿主明确要求启动的快环里生效。
- 不执行 `git add`，不执行 `git commit`，不推送。这覆盖本技能模板里的提交步骤。活仓里已有的裁决、完成队列、实验目录和其它运行数据保持未暂存，不清理，不改写。
- 不改 `scripts/praxist_goal.yaml`、`task_FM/config/covariate_pool.json`、`task_FM/task.yaml`、评估门禁公式、协议指纹。`search_policy` 保持带引号的 `"shadow"`。裸 `off` 在 YAML 1.1 里是布尔假。不往 cadence 里加 `priority_symbols`。`survivors_per_cycle` 保持 3。`cohort_size | default(4)` 保持。
- 不按 `proposal_id` 硬去重，不把 `cj` 或 `bu` 移出 `target_symbols`，不把 `eg`、`rb`、`jd` 写成死亡或停牌，不另建协变量注册表，不加配额、多臂老虎机、熔断、本地预筛、JSON Schema、分年切片、跨品种迁移、留出集或模拟盘。
- 不把 24 个品种名写进提示词。品种权威仍是绝对路径 `/home/abug/timesfm/scripts/praxist_goal.yaml`。
- 本计划新加的英文句子只写在规格给出的那一段。`prompt_base.jinja2` 第 34 行已有的中文放弃示例留着。不把 `status=ok` 写进失败增量的条件。`_is_confirmable_failure` 不读 `status`。
- `failure_delta` 的长度是 `delta = str(p.get("failure_delta") or "").strip()` 之后的 `len(delta) < 20`。`strip` 只去首尾。禁止改成删掉全部空白。
- `variant_id` 用裁决行里存的字符串做区分大小写的子串。先 `str(vid or "").strip()`，空串不算。禁止改成 `{symbol}_{family}_{fingerprint}` 再去对。
- 回放结论文件一旦在第 1 步落盘，从第 3 步改分类函数起直到验收结束，不删除它，也不再运行 `scripts/proposal_reject_replay.py`。
- 两个新脚本互不导入。`scripts/sup_*.py` 和 `scripts/praxist_supervisor.py` 不出现 `proposal_reject_replay` 或 `proposal_quality_census`。
- 不跑完整 pytest。每条命令用绝对路径的解释器。不打印 `.env.praxist`。
- 命令在 Ubuntu-22.04 里执行。不要把含 `&&` 的脚本塞进 PowerShell 的 `wsl bash -lc`。
- 规格「明确不做」没有对应任务。

## 范围

这是一个子系统：审计窗口提案的只读回放、有条件的最后一席、失败增量点名、一条提示词、一个只读计数脚本。不拆成多份计划。任务按 1 到 5 的顺序做。计数脚本虽然不依赖选座，也不许先做，免得跳过回放。

五个实现边界的归属：15 个目录共用一套 `seen_vids` 在 Task 1；回放落盘后不再重跑在 Task 1 的冻结文件和 Task 3 的禁令；48 小时闭区间和补满空席在 Task 2；`census` 与 `main` 分开在 Task 5；首尾去空白在 Task 1 和 Task 3，`skill.md` 不改在 Task 4。

## 文件职责

| 文件 | 职责 |
|---|---|
| `scripts/sup_harvest.py` | 新增 `classify_loaded_proposal`。`harvest_proposals` 调用它。预筛、backlog 写入、放弃日志、搜索守卫仍留在 `harvest_proposals`。Task 2 分支 A 才新增 `fill_seats`、`_two_pass_select`、`_recent_done_family_counts`。 |
| `scripts/proposal_reject_replay.py` | 只读回放。人手动运行。写结论 JSON。 |
| `tests/test_proposal_reject_replay_20261118.py` | 分类函数和回放的临时目录测试。 |
| `scripts/sup_evidence.py` | Task 3 在 `_has_prior_failure` 后面新增 `failure_delta_rejects`。 |
| `tests/test_harvest_proposals.py` | Task 3 只追加测试。不改 `DELTA`。 |
| `tests/test_fill_seats_20261118.py` | 只有 Task 2 分支 A 创建。 |
| `task_FM/prompt_base.jinja2` | Task 4 改示例行、第 8 条，并在 Diversity 段后另起一段。 |
| `tests/test_prompt_symbol_authority_20261118.py` | Task 4 扩展。仍只读三个文本。 |
| `scripts/proposal_quality_census.py` | `census(root)` 返回字典。`main` 才对照期望数字。 |
| `tests/test_proposal_quality_census_20261118.py` | 临时目录测试。 |
| `docs/superpowers/reports/2026-11-18-proposal-reject-replay.json` | Task 1 的实盘回放写出。禁止手写这份 JSON。 |

不改 `task_FM/roles/peer_generalist/skill.md`、`task_FM/prompt_generation.jinja2`。测试只断言这两份文件里没有本计划新加的句子。

规格对照：第 1 步是 Task 1，第 2 步是 Task 2，第 3 步是 Task 3，第 4 步是 Task 4，第 5 步是 Task 5。验收 1 和 2 在 Task 1、Task 2。验收 3 在 Task 3。验收 4 在 Task 4。验收 5 和 6 在 Task 5。

---

### Task 1: 抽出分类函数并只读回放

**Files:**
- Create: `scripts/proposal_reject_replay.py`
- Create: `tests/test_proposal_reject_replay_20261118.py`
- Modify: `scripts/sup_harvest.py`（在 `harvest_proposals` 之前新增函数，并让循环调用它）
- Test: `tests/test_harvest_proposals.py`（本任务不改这个文件，只重跑）

**Interfaces:**
- Consumes: `harvest_proposals` 现有的门顺序、`sup_evidence._active_protocol_snapshot`、`rl.dead_variants`、`rl.in_flight_ids`、`rl.pass_variants`、`rl.canonical_mode`、`sup_evidence.load_covariate_pool`、`sup_state._norm_search_policy`、`sup_state._cad_int`。
- Produces: `classify_loaded_proposal(p, *, proposal_path, root, pool, snapshot, dead, existing, passing_ids, seen_vids, evaluated, status_map, archived, valid_covs, allowed_syms, sg_cache, search_check) -> tuple`。第一项是 `"reject"`、`"backlog"` 或 `"ok"`。第二项是拒绝码或 `None`。第三项是字典，必有 `bumps`（列表）和 `success_state`（字符串或 `None`）。`"ok"` 时还有 `symbol`、`cov`、`vid`、`family`、`quality_score`、`sector`。`search_check(p, symbol, cov, proposal_path)` 返回 `(reason_or_None, search_info_or_None)`。函数会在通过 variant 检查后执行 `seen_vids.add`。它不修改 `evaluated`。`replay(root, output_path, goal_path) -> int`。

- [ ] **Step 1: 确认监督环没在跑，并且结论文件还不存在**

在 Ubuntu-22.04 里运行：

```bash
pgrep -af '[p]raxist_supervisor.py'; echo EXIT:$?
test ! -e /home/abug/timesfm/docs/superpowers/reports/2026-11-18-proposal-reject-replay.json; echo ABSENT:$?
```

有进程（`pgrep` 退出码 0）就停，本计划全部不做。结论文件已经存在也停。不要删掉一份不是本任务刚刚写出来的文件。

- [ ] **Step 2: 记下抽出前的收割测试结果**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_harvest_proposals.py -q --tb=line
```

预期：全部通过。把通过条数记下来。有失败就停，不要顺手改那些失败。

- [ ] **Step 3: 写一条还不能导入分类函数的失败测试**

创建 `tests/test_proposal_reject_replay_20261118.py`：

```python
"""只读回放与分类函数。规格 2026-11-18-proposal-followup-design.md 第 1 步。"""
import ast
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import sup_evidence
import sup_harvest

LONGM = (
    "波动率范围压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
    "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。"
)


def _kwargs(seen=None, evaluated=None):
    return dict(
        proposal_path="x.json",
        root="/tmp/replay-unit",
        pool={"vor": {"family": "volatility"}},
        snapshot={},
        dead=set(),
        existing=set(),
        passing_ids=set(),
        seen_vids=set() if seen is None else seen,
        evaluated=set() if evaluated is None else evaluated,
        status_map={},
        archived={},
        valid_covs={"vor"},
        allowed_syms={"m"},
        sg_cache={},
        search_check=lambda *args: (None, None),
    )


def test_classify_rejects_short_mechanism(monkeypatch):
    monkeypatch.setattr(
        sup_evidence, "_symbol_has_current_nocov_baseline", lambda symbol, root: True)
    proposal = {
        "schema": "fm.hypothesis_proposal.v1",
        "symbol": "m",
        "cov_override": "vor",
        "mechanism": "too short",
        "covariate_family": "volatility",
    }
    kind, reason, extra = sup_harvest.classify_loaded_proposal(proposal, **_kwargs())
    assert kind == "reject"
    assert reason == "mechanism_too_short"
    assert extra["bumps"] == []
    assert extra["success_state"] is None
```

- [ ] **Step 4: 跑这条测试，确认它失败**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_proposal_reject_replay_20261118.py::test_classify_rejects_short_mechanism -q --tb=line
```

预期：失败，原因是 `classify_loaded_proposal` 还不存在。

- [ ] **Step 5: 在 `scripts/sup_harvest.py` 实现分类函数并接到收割**

把下面的函数放在 `harvest_proposals` 定义之前。门的判断式与现在循环里的相同，不要改阈值，不要在这里点名 `variant_id`。

```python
def classify_loaded_proposal(
    p, *, proposal_path, root, pool, snapshot, dead, existing, passing_ids,
    seen_vids, evaluated, status_map, archived, valid_covs, allowed_syms,
    sg_cache, search_check,
):
    """已读入的提案字典走到成功增量门。

    返回 (kind, reason, extra)。kind 为 reject、backlog、ok。
    通过 variant 检查后把 vid 放进 seen_vids，即使后面的质量门再拒绝。
    不修改 evaluated，不写 backlog，不调用预筛，不构造 SearchGuard。
    """
    extra = {"bumps": [], "success_state": None, "search_info": None}
    if not isinstance(p, dict):
        return "reject", "schema_mismatch", extra
    if p.get("decision") == "abandon":
        return "reject", "decision_abandon", extra
    if p.get("new_covariate") or p.get("new_cov"):
        return "backlog", None, extra
    if p.get("schema") != "fm.hypothesis_proposal.v1":
        return "reject", "schema_mismatch", extra
    symbol = str(p.get("symbol") or "").lower().strip()
    cov = str(p.get("cov_override") or "").strip()
    mechanism = str(p.get("mechanism") or "").strip()
    extra["symbol"] = symbol
    extra["cov"] = cov
    if not symbol or not cov:
        return "reject", "missing_symbol_or_cov", extra
    search_reason, search_info = search_check(p, symbol, cov, proposal_path)
    extra["search_info"] = search_info
    if search_reason:
        return "reject", search_reason, extra
    if allowed_syms is not None and symbol not in allowed_syms:
        return "reject", "symbol_not_allowed", extra
    if cov in archived:
        return "reject", "cov_archived", extra
    if valid_covs is not None and cov not in valid_covs:
        return "reject", "cov_not_in_active_pool", extra
    if not sup_evidence._symbol_has_current_nocov_baseline(symbol, root):
        return "reject", "no_current_baseline", extra
    if len(mechanism) < 40:
        return "reject", "mechanism_too_short", extra
    sym_st = str((status_map.get(symbol) or {}).get("status") or "ACTIVE").upper()
    if sym_st == "DEAD":
        return "reject", "symbol_dead", extra
    if sym_st == "HOLD":
        return "reject", "symbol_hold", extra
    dead_fams = sup_evidence._dead_families(snapshot or {})
    fam = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or ""
    extra["family"] = fam
    if not fam:
        return "reject", "family_unresolved", extra
    if fam in dead_fams:
        return "reject", "family_dead", extra
    fp = sup_evidence._experiment_fp_for(symbol, cov)
    if fp is None:
        return "reject", "experiment_fp_unavailable", extra
    vid = ef.build_variant_id(symbol, fam, fp)
    extra["vid"] = vid
    if sup_evidence._has_prior_failure(snapshot or {}, symbol, cov):
        delta = str(p.get("failure_delta") or "").strip()
        if len(delta) < 20:
            return "reject", "no_failure_delta", extra
    if vid in dead or vid in existing or vid in passing_ids or vid in seen_vids:
        return "reject", "dedup", extra
    seen_vids.add(vid)
    if (symbol, cov, rl.canonical_mode(p)) in evaluated:
        return "reject", "dedup_evaluated", extra
    sec_blocked, sector, _sec_failed = _sector_filter_check(symbol, snapshot or {})
    extra["sector"] = sector
    if sec_blocked:
        extra["bumps"].append("sector_blocked")
        return "reject", "sector_blocked", extra
    cov_blocked, _fail_n, _pass_n = _covariate_filter_check(cov, symbol, snapshot or {})
    if cov_blocked:
        extra["bumps"].append("cov_cross_fail")
        return "reject", "cov_cross_fail", extra
    quality_score, _quality_bd = _proposal_quality_gate(
        p, snapshot or {}, proposal_path=proposal_path)
    extra["quality_score"] = quality_score
    if quality_score < MIN_QUALITY_SCORE:
        extra["bumps"].append("quality_below_threshold")
        return "reject", "quality_below_threshold", extra
    sg_reason, sg_state = sup_evidence._success_delta_gate(
        p, symbol, cov, snapshot or {}, root, cache=sg_cache)
    extra["success_state"] = sg_state
    if sg_reason is not None:
        return "reject", sg_reason, extra
    return "ok", None, extra
```

在 `harvest_proposals` 里，评估器、`status_map`、`archived`、`valid_covs`、`allowed_syms`、`passing_ids`、`_sg_cache`、`seen_vids`、`_evaluated` 仍在目录循环之前各创建一次。把现在循环里从 `decision == "abandon"` 到成功增量门的整段换成对这个函数的一次调用。JSON 读入、读失败时的 `_reject("unparseable_json")`、`stats["seen"] += 1`、停机检查、`glob` 都留在循环里。不要改 `glob`，预筛文件仍会被收割读到。

搜索守卫原样搬进循环内的闭包，签名返回一对：

```python
def _search_check(p, symbol, cov, proposal_path):
    search_info = None
    if search_guard is not None:
        _fam = (pool.get(cov, {}) or {}).get("family") or p.get("covariate_family") or ""
        if _fam:
            _pid = os.path.relpath(proposal_path, root)
            _sr, search_info = search_guard.check(p, symbol, _fam, cov, _pid)
            if _sr is not None:
                return _sr, None
            search_info["search_family"] = _fam
            search_info["search_proposal_id"] = _pid
    if shadow_guard is not None:
        _fam_s = ((pool.get(cov, {}) or {}).get("family")
                  or p.get("covariate_family") or "")
        if _fam_s:
            _sr_s, _shadow_info = shadow_guard.check(
                p, symbol, _fam_s, cov, os.path.relpath(proposal_path, root))
            if _sr_s is not None:
                bucket = stats["search_would_reject"]
                bucket[_sr_s] = bucket.get(_sr_s, 0) + 1
                stats["search_shadow_log"].append(
                    "%s %s" % (_sr_s, os.path.relpath(proposal_path, root)))
    return None, search_info
```

调用后的分支保持现在的副作用位置：

```python
kind, reason, extra = classify_loaded_proposal(
    p, proposal_path=sp, root=root, pool=pool, snapshot=snapshot,
    dead=dead, existing=existing, passing_ids=passing_ids,
    seen_vids=seen_vids, evaluated=_evaluated, status_map=status_map,
    archived=archived, valid_covs=valid_covs, allowed_syms=allowed_syms,
    sg_cache=_sg_cache, search_check=_search_check)
for name in extra["bumps"]:
    stats[name] += 1
if extra["success_state"] is not None:
    bucket = stats["success_gate_states"]
    state = extra["success_state"]
    bucket[state] = bucket.get(state, 0) + 1
if kind == "backlog":
    if _append_backlog(p, sp):
        stats["backlog"] += 1
    else:
        _reject("backlog_dup")
    continue
if kind == "reject":
    if reason == "decision_abandon":
        sup_lifecycle._log_decision(
            log, "proposal_abandoned",
            "peer=%s reason=%s" % (
                p.get("peer_id", "unknown"), p.get("abandon_reason", "N/A")))
    _reject(reason)
    continue
symbol = extra["symbol"]
cov = extra["cov"]
vid = extra["vid"]
family = extra["family"]
```

`"ok"` 之后的打分、档位、候选字典、`_evaluated.add`、`_prescreen_async` 保持现在的代码。`search_info` 仍只在候选上 `update`。排序和两轮选座本任务保持现在的循环，不要调用还不存在的 `fill_seats`。

- [ ] **Step 6: 分类测试通过，并且原收割测试条数不变**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_proposal_reject_replay_20261118.py::test_classify_rejects_short_mechanism /home/abug/timesfm/tests/test_harvest_proposals.py -q --tb=line
```

预期：新增那条通过，`test_harvest_proposals.py` 的通过条数与 Step 2 相同，失败数仍是 0。条数或失败变了，就收回这次抽出，本计划停在这里，Task 2 到 Task 5 都不做。

- [ ] **Step 7: 补回放的失败测试**

把下面的测试追加到同一个测试文件。临时目录自己带一份 `search_policy: "shadow"` 的目标文件。不要读 `task_FM/experiments`。

```python
import sup_paths
import registry_lib as rl

GOAL_TEXT = (
    "goal:\n"
    "  search_policy: \"shadow\"\n"
    "  cadence:\n"
    "    survivors_per_cycle: 3\n"
    "    aligned_max_points: 600\n"
)


def _install_fakes(monkeypatch):
    monkeypatch.setattr(
        sup_evidence, "_symbol_has_current_nocov_baseline", lambda symbol, root: True)
    monkeypatch.setattr(sup_evidence, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup_evidence, "_dead_families", lambda snapshot, min_ok=4: set())
    monkeypatch.setattr(sup_evidence, "_has_prior_failure", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        sup_evidence, "_success_delta_gate",
        lambda *args, **kwargs: (None, "no_prior_success"))
    monkeypatch.setattr(sup_evidence, "_active_protocol_snapshot", lambda path: {})
    monkeypatch.setattr(rl, "dead_variants", lambda snap: set())
    monkeypatch.setattr(rl, "in_flight_ids", lambda queue, inprogress: set())
    monkeypatch.setattr(rl, "pass_variants", lambda snap: [])
    monkeypatch.setattr(
        sup_harvest, "_load_evaluated_or_queued", lambda *args, **kwargs: set())
    monkeypatch.setattr(sup_evidence, "load_covariate_pool", lambda: {"vor": {"family": "volatility"}})
    monkeypatch.setattr(sup_evidence, "load_symbol_status", lambda: {})
    monkeypatch.setattr(sup_evidence, "_load_evaluator", lambda: None)
    monkeypatch.setattr(sup_harvest, "_proposal_priority_score", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(sup_harvest, "_cross_run_repeat_counts", lambda *args, **kwargs: {})


def _write_goal(root):
    path = root / "goal.yaml"
    path.write_text(GOAL_TEXT, encoding="utf-8")
    return str(path)


def _write_proposal(root, run_id, name, mechanism, mtime_ns):
    dest = root / "task_FM" / "experiments" / run_id / "results" / "gen_0" / "peer0" / "proposals"
    dest.mkdir(parents=True)
    payload = {
        "schema": "fm.hypothesis_proposal.v1",
        "symbol": "m",
        "cov_override": "vor",
        "covariate_family": "positioning",
        "mechanism": mechanism,
    }
    file_path = dest / name
    file_path.write_text(json.dumps(payload), encoding="utf-8")
    # dest 是 proposals 目录，parents[3] 是 run 目录。
    os.utime(dest.parents[3], ns=(mtime_ns, mtime_ns))
    return file_path


def test_replay_short_mechanism_and_skips_prescreen(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    _write_proposal(tmp_path, RUN_IDS[0], "m_vor.json", "too short", 2_000_000_000_000_000_000)
    prescreen = (
        tmp_path / "task_FM" / "experiments" / RUN_IDS[0]
        / "results" / "gen_0" / "peer0" / "proposals" / "m_vor.prescreen.json")
    prescreen.write_text('{"status":"degraded"}', encoding="utf-8")
    out = tmp_path / "out.json"
    code = replay(str(tmp_path), str(out), goal)
    assert code == 0
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["failure_delta_rule"] == "length_only"
    reasons = [row["reason"] for row in body["files"]]
    assert reasons == ["mechanism_too_short"]
    assert body["proposal_json_excluding_prescreen"] == 1
    assert body["dominant_reject_inventory_calendar"] is None


def test_newer_directory_occupies_variant_id(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    # 目录新旧只看 mtime，不看目录名里的日期。
    _write_proposal(tmp_path, RUN_IDS[0], "new.json", LONGM, 2_000_000_000_000_000_000)
    _write_proposal(tmp_path, RUN_IDS[1], "old.json", LONGM, 1_000_000_000_000_000_000)
    out = tmp_path / "out.json"
    assert replay(str(tmp_path), str(out), goal) == 0
    rows = json.loads(out.read_text(encoding="utf-8"))["files"]
    by_name = {Path(row["path"]).name: row for row in rows}
    assert by_name["new.json"]["kind"] == "ok"
    assert by_name["old.json"]["reason"] == "dedup"


def test_same_proposal_id_with_different_variant_is_not_dedup(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    newer = _write_proposal(tmp_path, RUN_IDS[0], "m.json", LONGM, 2_000_000_000_000_000_000)
    older = _write_proposal(tmp_path, RUN_IDS[1], "rb.json", LONGM, 1_000_000_000_000_000_000)
    for path, symbol in ((newer, "m"), (older, "rb")):
        body = json.loads(path.read_text(encoding="utf-8"))
        body["symbol"] = symbol
        body["proposal_id"] = "same-proposal-id"
        path.write_text(json.dumps(body), encoding="utf-8")
    # 改文件会带动目录 mtime。文件再往上 4 层才是 run 目录，写完再钉一次。
    os.utime(newer.parents[4], ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    os.utime(older.parents[4], ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    out = tmp_path / "out.json"
    assert replay(str(tmp_path), str(out), goal) == 0
    rows = json.loads(out.read_text(encoding="utf-8"))["files"]
    assert sorted(row["kind"] for row in rows) == ["ok", "ok"]
    assert all(row["reason"] is None for row in rows)


def test_later_reject_still_occupies_variant_id(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(
        sup_harvest, "_sector_filter_check", lambda symbol, snapshot: (True, "x", []))
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    _write_proposal(tmp_path, RUN_IDS[0], "new.json", LONGM, 2_000_000_000_000_000_000)
    _write_proposal(tmp_path, RUN_IDS[1], "old.json", LONGM, 1_000_000_000_000_000_000)
    out = tmp_path / "out.json"
    assert replay(str(tmp_path), str(out), goal) == 0
    rows = json.loads(out.read_text(encoding="utf-8"))["files"]
    by_name = {Path(row["path"]).name: row for row in rows}
    assert by_name["new.json"]["reason"] == "sector_blocked"
    assert by_name["old.json"]["reason"] == "dedup"


def test_existing_output_is_left_byte_identical(tmp_path):
    goal = _write_goal(tmp_path)
    out = tmp_path / "out.json"
    out.write_bytes(b'{"keep":true}\n')
    before = out.read_bytes()
    marker = tmp_path / "not-a-directory"
    marker.write_text("x", encoding="utf-8")
    from proposal_reject_replay import replay
    assert replay(str(marker), str(out), goal) == 0
    assert out.read_bytes() == before


def test_replay_script_does_not_call_harvest_side_effects():
    path = Path(ROOT) / "scripts" / "proposal_reject_replay.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    banned = {"harvest_proposals", "_prescreen_async", "_append_backlog", "_harvest_rows"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert name not in banned
    supervised = list(Path(ROOT, "scripts").glob("sup_*.py"))
    supervised.append(Path(ROOT, "scripts", "praxist_supervisor.py"))
    for script in supervised:
        text = script.read_text(encoding="utf-8")
        assert "proposal_reject_replay" not in text
        assert "proposal_quality_census" not in text
```

这里的 `replay` 在脚本还不存在时会导入失败。`covariate_family` 故意写成 `positioning`，回放仍应按池里的 `volatility` 算族，这样能看住「不读提案自己的族」。

- [ ] **Step 8: 跑新测试，确认除了已经通过的短机制分类测试之外都失败**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_proposal_reject_replay_20261118.py -q --tb=line
```

预期：`test_classify_rejects_short_mechanism` 通过。其余失败在导入 `proposal_reject_replay`。

- [ ] **Step 9: 实现 `scripts/proposal_reject_replay.py`**

脚本开头把仓库根和 `scripts/` 放进 `sys.path`。提供 `replay(root, output_path, goal_path) -> int`。

行为按这个顺序：

1. `output_path` 已存在：返回 0。不要读 `root`，不要读目标文件，不要替换。
2. `goal = sup_state.load_goal(goal_path)`。这个函数返回的已经是文件里 `goal:` 节点，`search_policy` 和 `cadence` 都在这一层，不要再取一次 `["goal"]`。`sup_state._norm_search_policy(goal)` 不是字符串 `shadow`，返回 2，不写文件。`cadence = goal.get("cadence") or {}`。`sup_state._cad_int(cadence, "survivors_per_cycle")` 不是 3，返回 2，不写文件。`priority_symbols` 只用 `cadence.get("priority_symbols")`，现在是 `None`。测试里的目标文件必须把 `cadence` 写在 `goal:` 下面。
3. 快照和队列来源与 `scripts/sup_loops.py` 的 `_harvest_rows` 相同，但不要调用 `_harvest_rows`：

```python
snap = sup_evidence._active_protocol_snapshot(sup_paths.REGISTRY)
dead = rl.dead_variants(snap)
existing = rl.in_flight_ids(sup_paths.QUEUE, sup_paths.INPROGRESS) | set(snap.keys())
pool = sup_evidence.load_covariate_pool()
passing_ids = {row["variant_id"] for row in rl.pass_variants(snap or {})}
evaluated = sup_harvest._load_evaluated_or_queued(
    sup_paths.REGISTRY, sup_paths.QUEUE, rl.CURRENT_PROTOCOL_FINGERPRINT)
seen_vids = set()
```

评估器、状态表、归档协变量、合法协变量、合法品种、`sg_cache` 各取一次，与 `harvest_proposals` 相同。`search_check` 固定返回 `(None, None)`。不要构造 `SearchGuard`。

4. 只走这 15 个目录名。缺目录就当 0 个文件，不抛 `FileNotFoundError`。按目录 `mtime` 从新到旧。目录内用与收割相同的 `glob`，不要再排序。文件名以 `.prescreen.json` 结尾的跳过。

```python
RUN_IDS = (
    "run_2026-11-17_01-55-15_primary_task_FM",
    "run_2026-11-17_03-55-34_primary_task_FM",
    "run_2026-11-17_05-56-23_primary_task_FM",
    "run_2026-11-17_07-56-25_primary_task_FM",
    "run_2026-11-17_10-57-34_primary_task_FM",
    "run_2026-11-17_13-50-15_primary_task_FM",
    "run_2026-11-17_16-05-58_primary_task_FM",
    "run_2026-11-17_18-07-01_primary_task_FM",
    "run_2026-11-18_00-28-23_primary_task_FM",
    "run_2026-11-18_02-25-52_primary_task_FM",
    "run_2026-11-18_04-23-37_primary_task_FM",
    "run_2026-11-18_06-22-12_primary_task_FM",
    "run_2026-11-18_08-38-47_primary_task_FM",
    "run_2026-11-18_10-41-10_primary_task_FM",
    "run_2026-11-18_12-41-11_primary_task_FM",
)
```

5. 能读的 JSON 交给 `classify_loaded_proposal`。读失败记 `unparseable_json`，不调用分类函数。`kind == "backlog"` 时只把原因记成 `backlog`，不调用 `_append_backlog`。`kind == "ok"` 时才 `evaluated.add((symbol, cov, rl.canonical_mode(p)))`，并用现在的打分和档位做候选。`priority_symbols` 为空时档位是 0，这段与 `harvest_proposals` 里 760 到 772 行相同。然后按 `(tier, -score, family, variant_id)` 排序，用现在的两轮选座模拟，`top_k` 为 3。这段模拟写在回放脚本里，不要调用 `fill_seats`。

6. 族只认活跃池里 `cov_override` 那一行的 `family`。提案 JSON 的 `covariate_family` 不参加 269 和 150 的计数。`hypothesis_v1`、各族计数和 `dominant_reject_inventory_calendar` 都从读出的提案字典计算：仅当 `p.get("schema") == "fm.hypothesis_proposal.v1"` 时，用 `str(p.get("cov_override") or "").strip()` 去查活跃池，得到 `pool_family`。不要用 `extra.get("family")`。分类函数在 `decision_abandon`、backlog、`symbol_not_allowed`、`mechanism_too_short` 等提前返回时，`extra` 里还没有 `family`，用它计数会让实盘账本对不上并退出码 2。拒绝码 `family_dead` 的 `extra["family"]` 必须属于同一次 `sup_evidence._dead_families(snap)`。有一个不属于就返回 2，不写结论文件。这个归属检查可以用 `extra["family"]`，因为它只在已经解析出族之后才会返回 `family_dead`。

7. 候选里至少有一个池族是 `inventory` 或 `calendar`，并且模拟选中的族里这两个都不在，`decision` 才是 `reserve_last_seat`。否则是 `no_selection_change`。这两个字符串只出现在回放脚本的结论里，不出现在 `fill_seats` 里，因为那个函数本任务还不存在。

8. `dominant_reject_inventory_calendar` 只统计被拒绝、且池族是这两类的文件。次数并列时取下面元组里更靠前的拒绝码。一个都没有则是 JSON `null`。

```python
REJECT_SOURCE_ORDER = (
    "unparseable_json", "decision_abandon", "backlog_dup", "schema_mismatch",
    "missing_symbol_or_cov", "symbol_not_allowed", "cov_archived",
    "cov_not_in_active_pool", "no_current_baseline", "mechanism_too_short",
    "symbol_dead", "symbol_hold", "family_unresolved", "family_dead",
    "experiment_fp_unavailable", "no_failure_delta", "dedup", "dedup_evaluated",
    "sector_blocked", "cov_cross_fail", "quality_below_threshold",
    "no_success_delta",
)
```

9. 先写到结论文件同目录的临时文件。检查通过后 `os.replace`。检查失败就删掉临时文件并返回 2，调用方路径上不留下 JSON。`failure_delta_rule` 固定写 `length_only`。`run_scope` 固定写 `appendix_a_only`。`replay` 增加参数 `expect_ledger`，默认 `False`。只有 `main` 传 `True`。`expect_ledger` 为真时才核对提案文件 894、假设 879、`inventory` 269、`calendar` 150、`term_structure` 102、`momentum` 225、`volatility` 132、不在池里 1；有一项对不上就返回 2，不留 JSON。默认 `False` 时不套这组数字，临时目录里的 1 个文件也能写成结论。两种模式都做第 6 点的 `family_dead` 归属检查。

结论 JSON 至少含这些键：`run_scope`、`failure_delta_rule`、`decision`、`dominant_reject_inventory_calendar`、`proposal_json_excluding_prescreen`、`hypothesis_v1`、`family_counts`、`selected_families`、`files`。`files` 的每一项含 `path`、`kind`、`reason`、`pool_family`。

`main` 使用参数 `--root`、`--output`、`--goal`。默认分别是 `/home/abug/timesfm`、该仓库下的 `docs/superpowers/reports/2026-11-18-proposal-reject-replay.json`、该仓库下的 `scripts/praxist_goal.yaml`。`main` 调用 `replay(..., expect_ledger=True)`。

- [ ] **Step 10: 回放单元测试通过**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_proposal_reject_replay_20261118.py -q --tb=line
```

预期：全部通过。再跑一次 `tests/test_harvest_proposals.py`，通过条数仍与 Step 2 相同。

- [ ] **Step 11: 对活仓跑一次实盘回放**

```bash
/home/abug/timesfm/.venv/bin/python /home/abug/timesfm/scripts/proposal_reject_replay.py --root /home/abug/timesfm --output /home/abug/timesfm/docs/superpowers/reports/2026-11-18-proposal-reject-replay.json --goal /home/abug/timesfm/scripts/praxist_goal.yaml
```

预期只有两种：退出码 0，并且 JSON 里 `decision` 是 `reserve_last_seat` 或 `no_selection_change`，`failure_delta_rule` 是 `length_only`；或者退出码 2，并且该路径上没有 JSON。其它退出码、第三种 `decision`、或退出码 2 却留下了文件，都先修脚本。修完后只有在分类函数仍是上面的长度检查、并且这份文件是本任务刚刚写出的错误文件时，才可以删掉它再跑一次。

把两个 sha256 写到 `/tmp/proposal-followup-task1-freeze.txt`。JSON 没生成时第二行写 `ABSENT`。

```bash
/home/abug/timesfm/.venv/bin/python -c "import hashlib, pathlib; r=pathlib.Path('/home/abug/timesfm/scripts/proposal_reject_replay.py'); j=pathlib.Path('/home/abug/timesfm/docs/superpowers/reports/2026-11-18-proposal-reject-replay.json'); lines=[hashlib.sha256(r.read_bytes()).hexdigest()]; lines.append(hashlib.sha256(j.read_bytes()).hexdigest() if j.exists() else 'ABSENT'); pathlib.Path('/tmp/proposal-followup-task1-freeze.txt').write_text('\n'.join(lines)+'\n')"
```

- [ ] **Step 12: 不提交**

不执行 `git add`，不执行 `git commit`。`test_harvest_proposals.py` 在本任务结束时与 Step 2 相比没有 diff。

---

### Task 2: 仅在结论授权时改最后一席

**Files:**
- Modify: `scripts/sup_harvest.py`（只在分支 A）
- Create: `tests/test_fill_seats_20261118.py`（只在分支 A）
- Test: `tests/test_harvest_proposals.py::test_production_goal_survivors_per_cycle_is_3`

**Interfaces:**
- Consumes: Task 1 的结论文件和 `/tmp/proposal-followup-task1-freeze.txt`。不调用 `replay`。
- Produces: 分支 A 产生 `fill_seats(candidates, top_k, dead_families, family_counts) -> list`、`_two_pass_select(candidates, top_k) -> list`、`_recent_done_family_counts(done_path, pool, now)`。`now.tzinfo` 不是 `None` 时计数函数返回 `None`。分支 B 不产生这些名字。

- [ ] **Step 1: 读冻结结果，只进一个分支**

读 `/tmp/proposal-followup-task1-freeze.txt` 和结论文件。回放脚本的 sha256 必须与冻结文件第一行一致。结论文件存在时，它的 sha256 必须与第二行一致，并且 `failure_delta_rule` 仍是 `length_only`。对不上就停。不要为了对齐而重跑回放。

然后只做下面一个分支。

分支 A 的条件：JSON 存在，且 `decision` 是 `reserve_last_seat`。

分支 B 的条件：JSON 不存在，或 `decision` 是 `no_selection_change`。

其它 `decision`：停，不要改选座。

- [ ] **Step 2A: 先写选座测试**

仅分支 A。创建 `tests/test_fill_seats_20261118.py`。候选按分数从高到低已经排好，测试直接调用函数，不读活的完成队列。每个候选带 `"_pool_family": True`，除非某条测试在查「不在池里」。

```python
"""最后一席。只在回放 decision 为 reserve_last_seat 时加入。"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import sup_harvest


def _row(family, score, vid, in_pool=True):
    return {
        "variant_id": vid,
        "_family": family,
        "_score": score,
        "_tier": 0,
        "_pool_family": in_pool,
    }


def test_low_count_family_takes_last_seat():
    rows = [
        _row("alpha", 40, "a"),
        _row("beta", 30, "b"),
        _row("gamma", 20, "c"),
        _row("delta", 10, "d"),
    ]
    picked = sup_harvest.fill_seats(rows, 3, set(), {"alpha": 5, "beta": 5, "gamma": 5, "delta": 0})
    assert [row["variant_id"] for row in picked] == ["a", "b", "d"]


def test_dead_family_does_not_take_reserved_seat():
    rows = [
        _row("alpha", 40, "a"),
        _row("beta", 30, "b"),
        _row("gamma", 20, "c"),
        _row("delta", 10, "d"),
    ]
    picked = sup_harvest.fill_seats(
        rows, 3, {"delta"}, {"alpha": 5, "beta": 5, "gamma": 5, "delta": 0})
    assert [row["variant_id"] for row in picked] == ["a", "b", "c"]


def test_top_k_one_uses_current_two_pass():
    rows = [_row("alpha", 40, "a"), _row("beta", 30, "b")]
    picked = sup_harvest.fill_seats(rows, 1, set(), {"alpha": 0, "beta": 0})
    assert [row["variant_id"] for row in picked] == ["a"]


def test_all_zero_counts_match_current_pass_one():
    rows = [
        _row("alpha", 40, "a"),
        _row("beta", 30, "b"),
        _row("gamma", 20, "c"),
        _row("delta", 10, "d"),
    ]
    picked = sup_harvest.fill_seats(rows, 3, set(), {})
    assert [row["variant_id"] for row in picked] == ["a", "b", "c"]


def test_one_family_still_fills_three_seats():
    rows = [_row("alpha", 40, "a"), _row("alpha", 30, "b"), _row("alpha", 20, "c")]
    picked = sup_harvest.fill_seats(rows, 3, set(), {"alpha": 0})
    assert [row["variant_id"] for row in picked] == ["a", "b", "c"]


def test_exact_48h_counts_and_aware_rows_do_not():
    now = datetime(2026, 11, 18, 12, 0, 0)
    exact = (now - timedelta(hours=48)).isoformat()
    early = (now - timedelta(hours=48) - timedelta(microseconds=1)).isoformat()
    late = (now + timedelta(microseconds=1)).isoformat()
    aware = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    text = "".join(
        json.dumps(row) + "\n"
        for row in (
            {"cov_override": "oi", "enqueued_at": exact},
            {"cov_override": "ccl", "enqueued_at": early},
            {"cov_override": "nvi", "enqueued_at": late},
            {"cov_override": "calendar_cyclical", "enqueued_at": aware},
            {"cov_override": "missing", "enqueued_at": exact},
        )
    )
    path = "/tmp/proposal-followup-done.jsonl"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    pool = {
        "oi": {"family": "alpha"},
        "ccl": {"family": "beta"},
        "nvi": {"family": "gamma"},
        "calendar_cyclical": {"family": "delta"},
    }
    counts = sup_harvest._recent_done_family_counts(path, pool, now)
    assert counts == {"alpha": 1}
    aware_now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    assert sup_harvest._recent_done_family_counts(path, pool, aware_now) is None


def test_seat_functions_do_not_name_inventory_or_calendar():
    import inspect
    for fn in (
        sup_harvest.fill_seats,
        sup_harvest._two_pass_select,
        sup_harvest._recent_done_family_counts,
    ):
        src = inspect.getsource(fn)
        assert "inventory" not in src
        assert "calendar" not in src
```

时钟夹具里的协变量名可以出现在测试里。函数源码里不能出现 `inventory` 和 `calendar`。池的族在这条测试里用 `alpha` 这些占位名，避免函数为了通过测试去写死族名。

- [ ] **Step 3A: 确认选座测试失败**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_fill_seats_20261118.py -q --tb=line
```

预期：失败，因为 `fill_seats` 还不存在。

- [ ] **Step 4A: 实现选座并接到收割**

在 `scripts/sup_harvest.py` 增加 `from datetime import datetime, timedelta`。

`_two_pass_select` 是把现在 792 到 808 行的两轮循环原样搬成函数，返回选中列表，不弹出私有键。

`fill_seats`：

```python
def fill_seats(candidates, top_k, dead_families, family_counts):
    limit = int(top_k)
    if limit < 2:
        return _two_pass_select(candidates, limit)
    selected = []
    used = set()
    for row in candidates:
        if len(selected) >= limit - 1:
            break
        if row["_family"] in used:
            continue
        selected.append(row)
        used.add(row["_family"])
    chosen = None
    chosen_key = None
    selected_ids = {row["variant_id"] for row in selected}
    for row in candidates:
        if row["variant_id"] in selected_ids:
            continue
        family = row["_family"]
        if family in used or family in dead_families or not row.get("_pool_family"):
            continue
        key = (int(family_counts.get(family, 0)), -row["_score"], row["variant_id"])
        if chosen_key is None or key < chosen_key:
            chosen_key = key
            chosen = row
    if chosen is not None:
        selected.append(chosen)
    if len(selected) < limit:
        selected_ids = {row["variant_id"] for row in selected}
        for row in candidates:
            if len(selected) >= limit:
                break
            if row["variant_id"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["variant_id"])
    return selected
```

`_recent_done_family_counts`：`now.tzinfo is not None` 时返回 `None`。否则 `cutoff = now - timedelta(hours=48)`，保留 `cutoff <= enqueued_dt <= now`。用 `datetime.fromisoformat`。带 `tzinfo` 的行、解析失败的行、协变量不在池里的行都不计数。族用该行 `cov_override` 在池里的 `family`。文件不存在时返回空字典，不返回 `None`。

候选字典增加 `"_pool_family": bool(pool_family) and pool_family == family`，其中 `pool_family` 是池里的族。返回选中行之前，和 `_family`、`_score`、`_tier` 一起弹出 `_pool_family`。

替换 `harvest_proposals` 末尾的两轮循环：

```python
seat_now = datetime.fromisoformat(sup_lifecycle._now_iso())
family_counts = _recent_done_family_counts(
    os.path.join(root, "data", "cache", "aligned_pending.done.jsonl"),
    pool, seat_now)
dead_fams = sup_evidence._dead_families(snapshot or {})
if family_counts is None:
    selected = _two_pass_select(candidates, top_k)
else:
    selected = fill_seats(candidates, top_k, dead_fams, family_counts)
```

不要改 `survivors_per_cycle`。不要在这几个函数里写 `inventory` 或 `calendar`。`inspect.getsource` 会连函数自己的文档字符串和注释一起看。文档字符串、行内注释里也不要出现这两个词，包括「不要针对 inventory」这种否定句。不要让收割去读回放 JSON。

- [ ] **Step 5A: 选座测试和席位数测试通过**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_fill_seats_20261118.py /home/abug/timesfm/tests/test_harvest_proposals.py::test_production_goal_survivors_per_cycle_is_3 /home/abug/timesfm/tests/test_harvest_proposals.py::test_family_diversity_pass_one -q --tb=line
```

预期：全部通过。回放脚本和结论文件的 sha256 仍与冻结文件一致。

- [ ] **Step 2B: 不改选座**

仅分支 B。确认 `scripts/sup_harvest.py` 里没有 `def fill_seats`，也没有 `def _recent_done_family_counts`。不要创建 `tests/test_fill_seats_20261118.py`。

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_harvest_proposals.py::test_production_goal_survivors_per_cycle_is_3 /home/abug/timesfm/tests/test_harvest_proposals.py::test_family_diversity_pass_one -q --tb=line
```

预期：两条都通过。回放脚本和结论文件的 sha256 仍与冻结文件一致。JSON 本来就不存在时，路径继续不存在。

- [ ] **Step 6: 不提交**

两个分支都不执行 `git add` 或 `git commit`。

---

### Task 3: 失败增量必须点名 variant_id

**Files:**
- Modify: `scripts/sup_evidence.py`（`_has_prior_failure` 后面）
- Modify: `scripts/sup_harvest.py`（只改 `classify_loaded_proposal` 里那四行长度检查）
- Modify: `tests/test_harvest_proposals.py`（只追加测试，不改 `DELTA`）
- Test: `tests/test_harvest_proposals.py::test_production_goal_survivors_per_cycle_is_3`

**Interfaces:**
- Consumes: `classify_loaded_proposal` 的返回形状。`_is_confirmable_failure` 和 `_has_prior_failure` 的配对语义。
- Produces: `failure_delta_rejects(snapshot, symbol, cov, proposal) -> str | None`。拒绝时返回 `"no_failure_delta"`，否则返回 `None`。分类函数里只有这一处调用。`harvest_proposals` 不再自己写一套长度检查。

- [ ] **Step 1: 确认冻结文件没被重跑**

读 `/tmp/proposal-followup-task1-freeze.txt`。回放脚本 sha256 必须仍一致。结论文件存在时 sha256 必须仍一致，且 `failure_delta_rule` 是 `length_only`。文件本来就是 `ABSENT` 时，路径必须仍然不存在。不要运行 `scripts/proposal_reject_replay.py`，不要删除 JSON。对不上就停。

- [ ] **Step 2: 写会失败的点名测试**

追加到 `tests/test_harvest_proposals.py`。沿用该文件已有的 `tmproot`、`_prop`、`_harvest`、`DELTA`。不要改 296 行的 `DELTA`。

```python
def test_failure_delta_long_without_variant_id_rejected(tmproot):
    snap = {"m_vor": {"variant_id": "m_vor_aaa111", "symbol": "m", "cov_override": "vor",
                      "status": "ok", "gate_pass": False, "dir_acc": 0.45,
                      "dm_status": "set_mismatch_ok",
                      "admissibility_rule": "edge_continuous_block_30d"}}
    text = "这次机制改了二十个字以上但是没有点名失败裁决"
    assert "m_vor_aaa111" not in text
    assert len(text.strip()) >= 20
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=text))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "no_failure_delta" in stats["reject_reasons"]


def test_failure_delta_names_second_variant_id(tmproot):
    snap = {
        "one": {"variant_id": "aaa_fail_1111", "symbol": "m", "cov_override": "vor",
                "gate_pass": False, "dm_status": "ok",
                "admissibility_rule": "edge_continuous_block_30d"},
        "two": {"variant_id": "bbb_fail_2222", "symbol": "m", "cov_override": "vor",
                "gate_pass": False, "dm_status": "set_mismatch_ok",
                "admissibility_rule": "edge_continuous_block_30d"},
    }
    text = "相对失败裁决 bbb_fail_2222，本次把触发从压缩改成持仓变化，机制不同。"
    assert "aaa_fail_1111" not in text
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta=text))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 1


def test_failure_delta_rejected_when_matching_variant_id_blank(tmproot):
    snap = {"m_vor": {"variant_id": "  ", "symbol": "m", "cov_override": "vor",
                      "gate_pass": False, "dm_status": "ok",
                      "admissibility_rule": "edge_continuous_block_30d"}}
    _make_run(tmproot, _prop(symbol="m", cov="vor", failure_delta="已经写满二十个字的机制差异说明。"))
    rows, stats = _harvest(tmproot, snap=snap)
    assert stats["selected"] == 0
    assert "no_failure_delta" in stats["reject_reasons"]


def test_failure_delta_internal_spaces_count_and_case_differs():
    base = {"symbol": "m", "cov_override": "vor", "gate_pass": False,
            "dm_status": "ok", "admissibility_rule": "edge_continuous_block_30d"}
    spaced = "m_vor" + (" " * 14) + "y"
    assert len(spaced.strip()) == 20
    snap = {"row": dict(base, variant_id="m_vor")}
    assert sup_evidence.failure_delta_rejects(
        snap, "m", "vor", {"failure_delta": spaced}) is None
    snap_case = {"row": dict(base, variant_id="m_vor_Case")}
    wrong_case = "m_vor_case" + "本次机制差异已经超过二十个字"
    assert sup_evidence.failure_delta_rejects(
        snap_case, "m", "vor", {"failure_delta": wrong_case}) == "no_failure_delta"
```

- [ ] **Step 3: 跑新测试，确认失败**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_harvest_proposals.py::test_failure_delta_long_without_variant_id_rejected /home/abug/timesfm/tests/test_harvest_proposals.py::test_failure_delta_names_second_variant_id /home/abug/timesfm/tests/test_harvest_proposals.py::test_failure_delta_rejected_when_matching_variant_id_blank /home/abug/timesfm/tests/test_harvest_proposals.py::test_failure_delta_internal_spaces_count_and_case_differs -q --tb=line
```

预期：失败，因为 `failure_delta_rejects` 还不存在，而且长文本没有 id 时现在的长度检查会放行。

- [ ] **Step 4: 实现配对点名**

在 `scripts/sup_evidence.py` 的 `_has_prior_failure` 后面增加：

```python
def failure_delta_rejects(snapshot, symbol, cov, proposal):
    """同一对已有可确认失败时，增量太短或没点名就返回 no_failure_delta。"""
    sym_key = str(symbol or "").lower()
    matched = []
    for row in (snapshot or {}).values():
        if not isinstance(row, dict) or not _is_confirmable_failure(row):
            continue
        if str(row.get("symbol") or "").lower() != sym_key:
            continue
        if str(row.get("cov_override") or "") != cov:
            continue
        matched.append(row)
    if not matched:
        return None
    delta = str((proposal or {}).get("failure_delta") or "").strip()
    if len(delta) < 20:
        return "no_failure_delta"
    ids = [str(row.get("variant_id") or "").strip() for row in matched]
    ids = [vid for vid in ids if vid]
    if not ids:
        return "no_failure_delta"
    if any(vid in delta for vid in ids):
        return None
    return "no_failure_delta"
```

把 `classify_loaded_proposal` 里这四行：

```python
if sup_evidence._has_prior_failure(snapshot or {}, symbol, cov):
    delta = str(p.get("failure_delta") or "").strip()
    if len(delta) < 20:
        return "reject", "no_failure_delta", extra
```

换成：

```python
fd_reason = sup_evidence.failure_delta_rejects(snapshot or {}, symbol, cov, p)
if fd_reason:
    return "reject", fd_reason, extra
```

不要用 `re.sub`，不要删掉中间空白。没有配对失败时函数返回 `None`，分类函数继续往下走。不要再在 `harvest_proposals` 里留第二套检查。

- [ ] **Step 5: 收割测试通过**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_harvest_proposals.py -q --tb=line
```

预期：原有测试加上本任务四条都通过。`test_failure_delta_enqueued_when_present`、`test_failure_delta_not_required_for_same_symbol_other_cov`、`test_production_goal_survivors_per_cycle_is_3` 都在其中。`survivors_per_cycle` 仍是 3。

再核对冻结文件。回放脚本和结论 JSON 的 sha256 必须没变。不要运行回放脚本。

- [ ] **Step 6: 不提交**

不执行 `git add`，不执行 `git commit`。

---

### Task 4: 提示词改成配对条件并要求至少两个品种

**Files:**
- Modify: `task_FM/prompt_base.jinja2`
- Modify: `tests/test_prompt_symbol_authority_20261118.py`
- Test: 规格验收第 4 条列出的五个节点

**Interfaces:**
- Consumes: 已经写在 `prompt_base.jinja2` 里的绝对路径品种规则、`p_oi` 的 inventory、Diversity 段、aligned 门。本任务不改这几句。
- Produces: 示例行、第 8 条、以及 Diversity 段落后的独立英文段，原文见下面 Step 3。没有新的 Python 接口。

- [ ] **Step 1: 扩展静态测试，先让它失败**

把 `tests/test_prompt_symbol_authority_20261118.py` 的模块说明改成同时覆盖配对条件和两个品种这句。保留原有禁止串和必须串。在 `test_prompt_base_symbol_family_and_gate` 里增加：

```python
RULE8 = (
    "8. **failure_delta**：若该 symbol 与该 cov 的组合已有可确认失败"
    "（`gate_pass` 为假，且 `dm_status` 为 `ok` 或 `set_mismatch_ok`），"
    "必须填写 ≥20 字，并且原文包含该组合至少一条失败裁决的 `variant_id`。"
    "只提到品种或只提到协变量不算。没有点名会被拒收 (`no_failure_delta`)。"
)
EXAMPLE = (
    '  "failure_delta": "仅当本 symbol 与本 cov 的组合已有可确认失败时必填：'
    '原文包含该失败裁决的 variant_id，并写清这次机制差在哪（≥20字）",'
)
DIVERSITY = (
    "When you write two or more proposals in this generation, at least one must "
    "use an ACTIVE covariate family from the menu below that differs from the "
    "family of your other proposal. A single proposal is valid when its covariate "
    "is an ACTIVE row in that menu. Do not invent a family the menu does not list."
)
TWO_SYMBOLS = (
    "When you write two or more proposals in this generation, use at least two symbols. "
    "For a symbol and covariate that already has a confirmable failure, write at most "
    "one more proposal in this generation, and only with a failure_delta that contains "
    "that failure's variant_id."
)
assert RULE8 in text
assert EXAMPLE in text
assert DIVERSITY in text
assert TWO_SYMBOLS in text
assert "本 symbol 或本 cov" not in text
between = text[text.index(DIVERSITY) + len(DIVERSITY):text.index(TWO_SYMBOLS)]
assert between.strip() == ""
```

在 `test_skill_scope_uses_goal_file_and_english_kill` 的禁止元组里加上 `failure_delta`、`symbol or cov`、`本 symbol 或`、`use at least two symbols`。

在 `test_generation_anti_mainline_does_not_name_macro_sentiment` 里加 `assert "use at least two symbols" not in text`。

- [ ] **Step 2: 跑测试，确认失败在 prompt_base**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_prompt_symbol_authority_20261118.py -q --tb=line
```

预期：失败，因为第 8 条和新英文段还不在 `prompt_base.jinja2`。若失败位置在 `skill.md` 或 `prompt_generation.jinja2`，停下来。本任务不许改那两个文件。写计划时两份文件都不含这些禁止串。

- [ ] **Step 3: 只改 prompt_base 的三处**

把示例里的 `failure_delta` 整行换成 `EXAMPLE` 那一行，行末逗号保留。

把第 8 条整句换成 `RULE8`。第 9 条不动，其中这句必须原样留下：

```text
缺 `success_delta` 的复跑会被拒收 (`no_success_delta`)。
```

Diversity 段现有的 `DIVERSITY` 保持为一个独立段落。紧接其后另起一段，整段就是 `TWO_SYMBOLS`。不要并进 Diversity 段，也不要写进收割。

第 34 行中文放弃示例、绝对路径品种规则、`p_oi` 的 `"covariate_family": "inventory"`、`cohort_size | default(4)`、`n=350-600`、两处 include、`p_oi.json`、`ACTIVE 品种优先`、`positioning/calendar/structure` 都不改。

- [ ] **Step 4: 跑规格列出的五个测试节点**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_prompt_symbol_authority_20261118.py /home/abug/timesfm/tests/test_praxist_evidence_ladder.py::test_prompt_base_selection_discipline /home/abug/timesfm/tests/test_praxist_evidence_ladder.py::test_templates_render_directive_context /home/abug/timesfm/tests/test_praxist_evidence_ladder.py::test_templates_render_without_agenda /home/abug/timesfm/tests/test_search_peer_surface_20261007.py::test_prompt_teaches_search_fields_and_keeps_success_delta -q --tb=line
```

预期：全部通过。不要跑完整 pytest。

- [ ] **Step 5: 不提交**

不执行 `git add`，不执行 `git commit`。不改 `skill.md` 和 `prompt_generation.jinja2`。

---

### Task 5: 只读计数脚本

**Files:**
- Create: `scripts/proposal_quality_census.py`
- Create: `tests/test_proposal_quality_census_20261118.py`

**Interfaces:**
- Consumes: Task 1 的 15 个目录名和「跳过 `*.prescreen.json`」规则。不导入回放脚本。
- Produces: `census(root) -> dict`。键只有 `direction_field`、`dir_acc_zero_rows_current_ok`、`hypothesis_v1`、`unparseable_proposal_json`、`proposal_json_excluding_prescreen`、`prescreen_files`、`prescreen_all_degraded_timeout`、`done_enqueued_at_on_2026_11_17_or_18`、`done_src_run_in_window`、`runs`。`direction_field` 的值是 `dir_acc`。`runs` 的每一项只有 `id` 和 `proposal_json_excluding_prescreen`。`main` 才对照账本并在不一致时退出码 1。

- [ ] **Step 1: 写临时目录测试**

创建 `tests/test_proposal_quality_census_20261118.py`：

```python
"""只读计数。census 不读期望数字，也不决定退出码。"""
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from proposal_quality_census import RUN_IDS, census

FP = "f02b2a433fd572eab341c7e4ad2f394168f5a02ddb6d5739dcebbdce49db4ae5"


def _layout(root, with_prescreen):
    run_id = RUN_IDS[0]
    dest = root / "task_FM" / "experiments" / run_id / "results" / "gen_0" / "peer0" / "proposals"
    dest.mkdir(parents=True)
    (dest / "m_vor.json").write_text(
        json.dumps({"schema": "fm.hypothesis_proposal.v1", "symbol": "m"}),
        encoding="utf-8")
    (dest / "bad.json").write_text("{", encoding="utf-8")
    if with_prescreen:
        (dest / "m_vor.prescreen.json").write_text(
            json.dumps({"status": "degraded", "note": "TypeSafe API 超时"}),
            encoding="utf-8")
    verdicts = root / "task_FM" / "config" / "aligned_verdicts.jsonl"
    verdicts.parent.mkdir(parents=True)
    rows = [
        {"status": "ok", "protocol_fingerprint": FP, "dir_acc": 0},
        {"status": "ok", "protocol_fingerprint": FP, "dir_acc": False},
        {"status": "ok", "protocol_fingerprint": FP},
    ]
    verdicts.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    done = root / "data" / "cache" / "aligned_pending.done.jsonl"
    done.parent.mkdir(parents=True)
    done.write_text(
        json.dumps({"enqueued_at": "2026-11-17T01:00:00", "src_run": run_id}) + "\n"
        + json.dumps({"enqueued_at": "2026-11-18T01:00:00", "src_run": "other"}) + "\n",
        encoding="utf-8")


def test_census_fixture_counts_and_missing_runs_are_zero(tmp_path):
    _layout(tmp_path, True)
    body = census(str(tmp_path))
    assert body["proposal_json_excluding_prescreen"] == 2
    assert body["hypothesis_v1"] == 1
    assert body["unparseable_proposal_json"] == 1
    assert body["prescreen_files"] == 1
    assert body["prescreen_all_degraded_timeout"] is True
    assert body["dir_acc_zero_rows_current_ok"] == 1
    assert body["direction_field"] == "dir_acc"
    assert body["done_enqueued_at_on_2026_11_17_or_18"] == 2
    assert body["done_src_run_in_window"] == 1
    assert len(body["runs"]) == 15
    assert body["runs"][0]["proposal_json_excluding_prescreen"] == 2
    assert all(row["proposal_json_excluding_prescreen"] == 0 for row in body["runs"][1:])
    assert "dir_ok" not in json.dumps(body)


def test_prescreen_flag_false_when_no_prescreen_files(tmp_path):
    _layout(tmp_path, False)
    assert census(str(tmp_path))["prescreen_all_degraded_timeout"] is False


def test_script_source_has_no_dir_ok_and_ledger_lives_in_main():
    text = Path(ROOT, "scripts", "proposal_quality_census.py").read_text(encoding="utf-8")
    assert "dir_ok" not in text
    before_main = text.split("def main")[0]
    for number in ("894", "879", "196"):
        assert number not in before_main
    supervised = list(Path(ROOT, "scripts").glob("sup_*.py"))
    supervised.append(Path(ROOT, "scripts", "praxist_supervisor.py"))
    for script in supervised:
        assert "proposal_quality_census" not in script.read_text(encoding="utf-8")
```

零行的判断必须写成 `not isinstance(value, bool) and isinstance(value, (int, float)) and value == 0`。布尔 `False` 不算 0。缺字段不算 0。

- [ ] **Step 2: 跑测试，确认失败**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_proposal_quality_census_20261118.py -q --tb=line
```

预期：导入失败，因为脚本还不存在。

- [ ] **Step 3: 实现计数脚本**

`census(root)` 只返回字典。15 个目录名与 Task 1 的 `RUN_IDS` 相同，复制一份，不要导入回放脚本。`runs` 按这份元组的定义顺序输出。夹具只创建了 `RUN_IDS[0]`，测试断言 `runs[0]` 的提案数是 2。不要按目录 mtime 倒序，那是回放的顺序，不是计数的顺序。缺目录时该项为 0，不抛 `FileNotFoundError`。提案计数跳过 `*.prescreen.json`。无法解析是 JSON 解码失败。`hypothesis_v1` 是能解析且 `schema` 为 `fm.hypothesis_proposal.v1` 的文件数。

完成队列路径是 `root/data/cache/aligned_pending.done.jsonl`。63 那个键用 `enqueued_at` 字符串包含 `2026-11-17` 或 `2026-11-18`。另一个键只数 `src_run` 精确等于这 15 个目录名的行。不要用 48 小时窗口。

裁决路径是 `root/task_FM/config/aligned_verdicts.jsonl`。只看 `status` 为 `ok`、且 `protocol_fingerprint` 以 `f02b2a43` 开头的行。

`prescreen_all_degraded_timeout` 仅当预筛文件数大于 0，且每一份都能解析、`status` 是 `degraded`、`note` 是 `TypeSafe API 超时`。文件数是 0，或任何一份失败，都为假。

源文件的正文、注释、文档字符串、名字和报错里都不出现 `dir_ok`。`def main` 之前的正文，包括模块文档字符串和注释，也不出现 `894`、`879`、`196`。测试会把源码从 `def main` 处切开，检查前半段。不打印比率。

`main` 调用 `census`，打印 JSON，再与账本比较。有一项不同就向 stderr 写 `ledger mismatch` 和不同的键名，退出码 1。不要在报错里写 `dir_ok`。期望是：提案文件 894，假设 879，无法解析 15，预筛 196 且标志为真，完成队列 63 和 13，零行数 0，逐 run 为 48、65、67、103、56、78、40、18、51、79、56、54、58、78、43。这些数字只出现在 `main`。不要改裁决、价格、合约映射或这组期望数字。

- [ ] **Step 4: 夹具测试通过后跑活仓**

```bash
/home/abug/timesfm/.venv/bin/python -m pytest /home/abug/timesfm/tests/test_proposal_quality_census_20261118.py -q --tb=line
```

预期：通过。然后：

```bash
/home/abug/timesfm/.venv/bin/python /home/abug/timesfm/scripts/proposal_quality_census.py --root /home/abug/timesfm
```

预期：退出码 0，打印的 JSON 与账本一致，正文里没有 `dir_ok`。退出码 1 就停。不要把期望数字改成新数，也不要改数据。同一天完成队列若已经不再是 63 或 13，这就是停，不是调账。

- [ ] **Step 5: 验收收口**

在 Ubuntu-22.04 里确认：

```bash
pgrep -af '[p]raxist_supervisor.py'; echo EXIT:$?
/home/abug/timesfm/.venv/bin/python -c "from pathlib import Path; text=Path('/home/abug/timesfm/scripts/praxist_goal.yaml').read_text(encoding='utf-8'); assert 'search_policy: \"shadow\"' in text; print('shadow-ok')"
```

`pgrep` 退出码为 1。`search_policy` 仍是带引号的 `shadow`。

再读 `/tmp/proposal-followup-task1-freeze.txt`。回放脚本 sha256 没变。结论文件要么仍然不存在，要么 sha256 没变且 `failure_delta_rule` 仍是 `length_only`。不要为了收口重跑回放。

不执行 `git add`，不执行 `git commit`，不推送，不重启监督环。工作区里原有的运行数据保持原样。
