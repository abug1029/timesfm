# 裁决诊断标签 Implementation Plan

> **代码基线**: `5b02284`
> **状态**：2026-11-07 已实施并快进合入 `master`。监督环未重启。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **修订（2026-11-07，执行前）**
>
> 1. 过硬门且 DM 不可确认时，先于 `p_value` 判断。描述性 p 值即使 ≤ 0.05，也不贴「本行 DM p ≤ 0.05」。
> 2. 选样本时，`dir_acc`、`baseline_dir_acc`、`effective_min` 三个字段都必须是有限数。缺一个就不能入选，避免渲染成「不足以归因」。
> 3. 没有正面样本时，本品种只有一个协变量才允许跨品种；有两个就不跨。跨品种同分时按品种名（casefold，忽略大小写）、再按 `variant_id` 取稳定的一条。

**Goal:** 在 `known_verdicts.inc.md` 里为每个目标品种加一对诊断样本，标签只由已落盘字段按互斥顺序生成。

**Architecture:** 两个纯函数放在 `scripts/sup_evidence.py`：`format_verdict_diag_label` 生成一句标签，`select_symbol_diag_pair` 在当前协议的行里挑正面和反面。`materialize_known_verdicts` 在 Effective clues 之后插入 `## 诊断样本`。不写回裁决文件，不改硬门和收割。

**Tech Stack:** Python 3.11，仓库内 pytest，活仓 `/home/abug/timesfm` 的 `.venv`。

**Spec:** `docs/superpowers/specs/2026-11-07-verdict-diag-label-spec.md`

## Global Constraints

- 对照代码为活仓 `master`。测试用 `/home/abug/timesfm/.venv/bin/python -m pytest`。不要用 Windows 上的 `D:\FlyBuddy\shared\timesfm`。
- 标签不写进 `aligned_verdicts.jsonl`，不改协议指纹，不重生基线。
- 不改 `gate()`、`scripts/sup_harvest.py`、`search_policy`、`prompt_base.jinja2`。
- 不实现前缀截断测试。未来段禁止用缺失值做扰动，那一项不在本计划里。
- 不重启监督环。
- 代码只写在工作树分支 `feat/verdict-diag-label`，不改活仓 master 的检出。各任务在该分支提交。不 push，不重启监督环。
- `status` 缺省按 `ok`。`p_value` 只有有限且 ≤ 0.05 才算显著。NaN 不算。
- 跨品种条件是去掉正面样本之后本品种可确认失败为空，不是去掉之前的条数为 0。

---

## 文件

- 修改：`scripts/sup_evidence.py`。新增两个纯函数和一节渲染，插在 `lines.extend(clue_lines)` 之后。
- 新建：`tests/test_verdict_diag_label.py`。只测这两个函数和生成的 markdown，不读活裁决文件。
- 不改：`scripts/sup_harvest.py`、`task_FM/evaluations/fm_eval/evaluator.py`。

## Task 1: 诊断标签

**Files:**

- Create: `tests/test_verdict_diag_label.py`
- Modify: `scripts/sup_evidence.py`
- Test: `tests/test_verdict_diag_label.py`

**Interfaces:**

- Consumes: 无。
- Produces: `format_verdict_diag_label(row: dict) -> str`。

- [ ] **Step 1: Write the failing test**

新建 `tests/test_verdict_diag_label.py`：

```python
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import sup_evidence


def _row(**kw):
    base = {
        "status": "ok",
        "dm_status": "ok",
        "gate_pass": False,
        "dir_acc": 0.45,
        "baseline_dir_acc": 0.40,
        "effective_min": 0.52,
        "p_value": None,
    }
    base.update(kw)
    return base


def test_non_ok_without_dir_acc_is_not_insufficient():
    text = sup_evidence.format_verdict_diag_label(
        _row(status="error", dir_acc=None, gate_pass=False))
    assert text == "本行不是有效裁决，不写成机制失败"


def test_unconfirmable_dm_without_dir_acc_is_not_insufficient():
    text = sup_evidence.format_verdict_diag_label(
        _row(dm_status="no_baseline", dir_acc=None, gate_pass=False))
    assert text == "DM 不可确认。不计作机制失败。这种 DM 状态不计入家族死亡"
    assert "方向低于" not in text


def test_missing_dir_acc_on_ok_confirmable_row():
    assert sup_evidence.format_verdict_diag_label(
        _row(dir_acc=None)) == "不足以归因"


def test_nan_dir_acc_is_insufficient():
    assert sup_evidence.format_verdict_diag_label(
        _row(dir_acc=float("nan"))) == "不足以归因"


def test_unconfirmable_dm_does_not_add_mechanism_label():
    text = sup_evidence.format_verdict_diag_label(
        _row(dm_status="no_baseline", dir_acc=0.30, baseline_dir_acc=0.40))
    assert text.startswith("DM 不可确认")
    assert "方向低于" not in text


def test_gate_pass_with_significant_p_is_not_confirmation():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dir_acc=0.55, p_value=0.04))
    assert "p ≤ 0.05" in text
    assert "不是确认成功" in text
    assert "已经解决" not in text


def test_gate_pass_with_large_p():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dir_acc=0.55, p_value=0.20))
    assert text == "过硬门。本行 DM 未显示 p ≤ 0.05。硬门本身不读 DM，这也不是确认成功"


def test_gate_pass_with_unconfirmable_dm_stays_a_pass():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dm_status="no_baseline", dir_acc=0.55))
    assert text.startswith("过硬门")
    assert "DM 不可确认" in text
    assert "机制失败" in text


def test_gate_pass_unconfirmable_dm_ignores_descriptive_p_value():
    text = sup_evidence.format_verdict_diag_label(
        _row(gate_pass=True, dm_status="set_mismatch_descriptive",
             dir_acc=0.55, p_value=0.01))
    assert text.startswith("过硬门。DM 不可确认")
    assert "p ≤ 0.05" not in text


def test_nan_p_value_falls_through_to_unstable_label():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.45, baseline_dir_acc=0.40, effective_min=0.52,
             p_value=float("nan")))
    assert text == "方向不低于基线，未过自适应门槛，DM 未显示稳定优势"


def test_significant_p_below_near_miss_band():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.40, baseline_dir_acc=0.30, effective_min=0.52,
             p_value=0.01))
    assert text == "DM 显著改善，但方向准确率未达自适应门槛"
    assert "近失" not in text


def test_significant_p_inside_near_miss_band():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.50, baseline_dir_acc=0.40, effective_min=0.52,
             p_value=0.01))
    assert text == "DM 显著改善，但方向准确率未达自适应门槛。近失，距该品种门槛只差一截"


def test_below_baseline_inside_near_miss_band():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.50, baseline_dir_acc=0.55, effective_min=0.52,
             p_value=0.20))
    assert text == "方向低于无协变量基线。近失，距该品种门槛只差一截"


def test_dir_acc_at_threshold_but_gate_failed_is_not_blamed_on_dm():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.55, baseline_dir_acc=0.40, effective_min=0.52,
             gate_pass=False, p_value=0.20))
    assert text.startswith("方向达到自适应门槛，但硬门未过")
    assert "败于" not in text
    assert "本行 DM 亦未显示 p ≤ 0.05" in text


def test_nan_p_value_on_gate_sized_failure_adds_no_p_clause():
    text = sup_evidence.format_verdict_diag_label(
        _row(dir_acc=0.55, baseline_dir_acc=0.40, effective_min=0.52,
             gate_pass=False, p_value=float("nan")))
    assert text == "方向达到自适应门槛，但硬门未过。硬门还检查样本量与有效样本，不读 DM"
    assert math.isnan(float("nan"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && .venv/bin/python -m pytest tests/test_verdict_diag_label.py -q`

Expected: FAIL，`format_verdict_diag_label` 不存在。

- [ ] **Step 3: Write minimal implementation**

在 `scripts/sup_evidence.py` 里 `_CONFIRMATORY_DM` 之后加入：

```python
def _diag_finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def format_verdict_diag_label(row):
    """给线索文件用的互斥标签。不读盘，不改 row。"""
    if not isinstance(row, dict):
        return "不足以归因"
    gate = bool(row.get("gate_pass", False))
    status = row.get("status", "ok")
    confirmable = row.get("dm_status") in _CONFIRMATORY_DM
    if not gate and status != "ok":
        return "本行不是有效裁决，不写成机制失败"
    if not gate and not confirmable:
        return "DM 不可确认。不计作机制失败。这种 DM 状态不计入家族死亡"
    dir_acc = row.get("dir_acc")
    base = row.get("baseline_dir_acc")
    emin = row.get("effective_min")
    if not (_diag_finite(dir_acc) and _diag_finite(base) and _diag_finite(emin)):
        return "不足以归因"
    p_val = row.get("p_value")
    p_sig = confirmable and _diag_finite(p_val) and p_val <= 0.05
    if gate and not confirmable:
        return "过硬门。DM 不可确认，不能写成统计成功，也不能写成机制失败"
    if gate and p_sig:
        return "过硬门。本行 DM p ≤ 0.05。硬门本身不读 DM，这也不是确认成功"
    if gate:
        return "过硬门。本行 DM 未显示 p ≤ 0.05。硬门本身不读 DM，这也不是确认成功"
    if dir_acc < base:
        text = "方向低于无协变量基线"
    elif dir_acc < emin:
        if p_sig:
            text = "DM 显著改善，但方向准确率未达自适应门槛"
        else:
            text = "方向不低于基线，未过自适应门槛，DM 未显示稳定优势"
    else:
        text = "方向达到自适应门槛，但硬门未过。硬门还检查样本量与有效样本，不读 DM"
        if p_sig:
            text += "。本行 DM p ≤ 0.05，硬门仍未过"
        elif _diag_finite(p_val):
            text += "。本行 DM 亦未显示 p ≤ 0.05"
        return text
    if 0.49 <= dir_acc < emin:
        text += "。近失，距该品种门槛只差一截"
    return text
```

文件顶部若还没有 `import math`，补上。不要改 `_CONFIRMATORY_DM` 的成员。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && .venv/bin/python -m pytest tests/test_verdict_diag_label.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

在工作树分支上执行，不要在活仓 master 上提交：

```bash
git add tests/test_verdict_diag_label.py scripts/sup_evidence.py
git commit -m "feat: label aligned verdicts with mutually exclusive diagnostics"
```

## Task 2: 正反样本

**Files:**

- Modify: `tests/test_verdict_diag_label.py`
- Modify: `scripts/sup_evidence.py`
- Test: `tests/test_verdict_diag_label.py`

**Interfaces:**

- Consumes: `format_verdict_diag_label` 不在本任务的选择函数里调用。选择函数只挑行。
- Produces: `select_symbol_diag_pair(symbol_rows: list, other_rows: list) -> dict`。键为 `positive`、`negative`、`positive_empty`、`negative_empty`、`cross_symbol`、`repeat_n`。

- [ ] **Step 1: Write the failing test**

把下面的测试追加到 `tests/test_verdict_diag_label.py`：

```python
def _picked(**kw):
    row = {
        "symbol": "jd",
        "cov_override": "rsi_state",
        "status": "ok",
        "dm_status": "ok",
        "gate_pass": False,
        "dir_acc": 0.50,
        "baseline_dir_acc": 0.40,
        "effective_min": 0.52,
        "variant_id": "jd_rsi",
    }
    row.update(kw)
    return row


def test_negative_prefers_same_symbol_ordinary_failure_over_cross():
    near = _picked(variant_id="near", dir_acc=0.50)
    low = _picked(variant_id="low", dir_acc=0.40)
    other = _picked(symbol="rb", variant_id="rb_low", dir_acc=0.48)
    got = sup_evidence.select_symbol_diag_pair([near, low], [other])
    assert got["positive"] is near or got["positive"]["variant_id"] == "near"
    assert got["negative"]["variant_id"] == "low"
    assert got["cross_symbol"] is False
    assert got["repeat_n"] == 0


def test_only_near_miss_used_as_positive_still_crosses():
    only = _picked(variant_id="only", dir_acc=0.51)
    other = _picked(symbol="rb", variant_id="rb_hit", dir_acc=0.42)
    got = sup_evidence.select_symbol_diag_pair([only], [other])
    assert got["positive"] is only
    assert got["negative"] is other
    assert got["cross_symbol"] is True
    assert got["repeat_n"] == 1
    assert got["negative_empty"] is None


def test_cross_symbol_picks_highest_and_counts_repeats():
    pos = _picked(gate_pass=True, dir_acc=0.56, variant_id="pass")
    low = _picked(symbol="rb", variant_id="rb_low", dir_acc=0.41)
    high = _picked(symbol="m", variant_id="m_high", dir_acc=0.47)
    got = sup_evidence.select_symbol_diag_pair([pos], [low, high])
    assert got["negative"]["variant_id"] == "m_high"
    assert got["repeat_n"] == 2
    assert got["cross_symbol"] is True


def test_blank_symbol_uses_fixed_empty_reasons():
    got = sup_evidence.select_symbol_diag_pair([], [])
    assert got["positive"] is None
    assert got["negative"] is None
    assert got["positive_empty"] == "本品种无通过、无近失"
    assert got["negative_empty"] == "本品种尚无有效失败记录"


def test_selector_does_not_mutate_rows():
    only = _picked()
    snapshot = dict(only)
    sup_evidence.select_symbol_diag_pair([only], [])
    assert only == snapshot


def test_incomplete_higher_dir_acc_loses_to_complete_row():
    broken = _picked(variant_id="broken", dir_acc=0.60, baseline_dir_acc=None,
                     gate_pass=True)
    whole = _picked(variant_id="whole", dir_acc=0.55, gate_pass=True)
    got = sup_evidence.select_symbol_diag_pair([broken, whole], [])
    assert got["positive"]["variant_id"] == "whole"


def test_no_positive_single_cov_crosses_two_covs_do_not():
    local = _picked(dm_status="no_baseline", dir_acc=0.40, variant_id="local",
                    cov_override="rsi_state")
    other = _picked(symbol="rb", variant_id="rb", dir_acc=0.43,
                    cov_override="rsi_state")
    got = sup_evidence.select_symbol_diag_pair([local], [other])
    assert got["positive"] is None
    assert got["negative"]["variant_id"] == "rb"
    assert got["cross_symbol"] is True
    second = _picked(dm_status="no_baseline", dir_acc=0.41, variant_id="local2",
                     cov_override="vwap_deviation")
    got2 = sup_evidence.select_symbol_diag_pair([local, second], [other])
    assert got2["positive"] is None
    assert got2["negative"] is None
    assert got2["cross_symbol"] is False


def test_equal_dir_acc_prefers_smaller_symbol_name():
    pos = _picked(gate_pass=True, dir_acc=0.56, variant_id="pass")
    rb = _picked(symbol="rb", variant_id="rb", dir_acc=0.44)
    em = _picked(symbol="m", variant_id="m", dir_acc=0.44)
    got = sup_evidence.select_symbol_diag_pair([pos], [rb, em])
    assert got["negative"]["variant_id"] == "m"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && .venv/bin/python -m pytest tests/test_verdict_diag_label.py -q`

Expected: 新测试 FAIL，`select_symbol_diag_pair` 不存在。Task 1 的测试仍 PASS。

- [ ] **Step 3: Write minimal implementation**

在 `format_verdict_diag_label` 之后加入：

```python
def _diag_failure(row):
    return (isinstance(row, dict)
            and row.get("status", "ok") == "ok"
            and _is_confirmable_failure(row))


def _diag_dir(row):
    """三个方向字段都是有限数才返回 dir_acc。缺一个就不当候选。"""
    if not isinstance(row, dict):
        return None
    da = row.get("dir_acc")
    base = row.get("baseline_dir_acc")
    emin = row.get("effective_min")
    if _diag_finite(da) and _diag_finite(base) and _diag_finite(emin):
        return float(da)
    return None


def _diag_near_miss(row):
    if not _diag_failure(row):
        return False
    da = _diag_dir(row)
    emin = row.get("effective_min")
    return da is not None and _diag_finite(emin) and 0.49 <= da < float(emin)


def _diag_best(rows):
    """dir_acc 高者优先。同分时品种名较小者优先，再比 variant_id。"""
    ranked = []
    for row in rows:
        da = _diag_dir(row)
        if da is None:
            continue
        ranked.append((
            -da,
            str(row.get("symbol") or "").casefold(),
            str(row.get("variant_id") or ""),
            row,
        ))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[:3])
    return ranked[0][3]


def select_symbol_diag_pair(symbol_rows, other_rows):
    """挑一个品种的正面和反面。不改输入行。"""
    symbol_rows = [r for r in (symbol_rows or []) if isinstance(r, dict)]
    other_rows = [r for r in (other_rows or []) if isinstance(r, dict)]
    passes = [r for r in symbol_rows if bool(r.get("gate_pass", False))]
    positive = _diag_best(passes)
    if positive is None:
        positive = _diag_best([r for r in symbol_rows if _diag_near_miss(r)])
    failures = [r for r in symbol_rows if _diag_failure(r) and r is not positive]
    negative = _diag_best([r for r in failures if _diag_near_miss(r)])
    if negative is None:
        negative = _diag_best(failures)
    cross = False
    repeat_n = 0
    if negative is None:
        cov = None
        if positive is not None:
            cov = positive.get("cov_override")
        else:
            covs = {r.get("cov_override") for r in symbol_rows
                    if r.get("cov_override")}
            if len(covs) == 1:
                cov = next(iter(covs))
        if cov:
            pool = [r for r in other_rows
                    if r.get("cov_override") == cov and _diag_failure(r)]
            repeat_n = len(pool)
            negative = _diag_best(pool)
            cross = negative is not None
        if negative is None:
            repeat_n = 0
    return {
        "positive": positive,
        "negative": negative,
        "positive_empty": None if positive is not None else "本品种无通过、无近失",
        "negative_empty": None if negative is not None else "本品种尚无有效失败记录",
        "cross_symbol": cross,
        "repeat_n": repeat_n if cross else 0,
    }
```

`r is not positive` 必须用对象身份。本品种只剩那一条近失时，`failures` 为空，才会走进跨品种。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && .venv/bin/python -m pytest tests/test_verdict_diag_label.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

在工作树分支上执行，不要在活仓 master 上提交：

```bash
git add tests/test_verdict_diag_label.py scripts/sup_evidence.py
git commit -m "feat: pick same-symbol diagnostic samples before crossing symbols"
```

## Task 3: 写进线索文件

**Files:**

- Modify: `scripts/sup_evidence.py`（`materialize_known_verdicts` 里 `lines.extend(clue_lines)` 的下一行）
- Modify: `tests/test_verdict_diag_label.py`
- Test: `tests/test_verdict_diag_label.py`

**Interfaces:**

- Consumes: `format_verdict_diag_label`、`select_symbol_diag_pair`、`_protocol_section_line`、`sup_state.GOAL_SYMBOLS_SET`。
- Produces: `materialize_known_verdicts` 的 markdown 在 Effective clues 之后、`render_open_trees` 之前多一节 `## 诊断样本`。

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_verdict_diag_label.py`：

```python
def test_materialize_inserts_diag_section_without_mutating_rows(tmp_path, monkeypatch):
    import sup_state
    monkeypatch.setattr(sup_state, "GOAL_SYMBOLS_SET", {"jd"})
    only = {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": "jd_only",
        "symbol": "jd",
        "cov_override": "rsi_state",
        "cov_family": "momentum",
        "status": "ok",
        "gate_pass": False,
        "dir_acc": 0.51,
        "baseline_dir_acc": 0.40,
        "effective_min": 0.52,
        "p_value": 0.20,
        "dm_status": "ok",
        "protocol_fingerprint": "f" * 64,
        "run_mode": "exploration",
        "decided_at": "2026-11-01T00:00:00",
        "fdr_pass": False,
        "n": 400,
        "ev": 0.0,
    }
    other = dict(only)
    other.update({"variant_id": "rb_only", "symbol": "rb", "dir_acc": 0.44})
    before = (dict(only), dict(other))
    dest = tmp_path / "known_verdicts.inc.md"
    sup_evidence.materialize_known_verdicts(
        {"jd_only": only, "rb_only": other}, str(dest),
        proposed_ids=set(), status_map={}, queue_ids=set())
    text = dest.read_text(encoding="utf-8")
    assert text.index("## Effective clues") < text.index("## 诊断样本")
    assert "jd 正面：" in text
    assert "jd 反面（跨品种 rb）：" in text
    assert "同协变量可确认失败 n=1" not in text
    assert "mechanism" not in text.split("## 诊断样本", 1)[1].split("\n## ", 1)[0]
    assert only == before[0]
    assert other == before[1]
```

`n=1` 不写「反复」。断言用「同协变量可确认失败 n=1」不出现；`n=2` 的渲染放到同文件的下一个测试，避免和这条混在一个断言里：

```python
def test_repeat_count_is_written_only_when_at_least_two():
    import sup_state
    # 不跑 materialize。渲染函数直接吃 select 的结果。
    pos = _picked(gate_pass=True, dir_acc=0.56, variant_id="pass",
                  decided_at="2026-11-01T00:00:00")
    a = _picked(symbol="rb", variant_id="a", dir_acc=0.42,
                decided_at="2026-11-02T00:00:00")
    b = _picked(symbol="m", variant_id="b", dir_acc=0.46,
                decided_at="2026-11-03T00:00:00")
    picked = sup_evidence.select_symbol_diag_pair([pos], [a, b])
    line = sup_evidence._format_diag_bullet("jd", "反面", picked)
    assert "反面（跨品种 m）" in line
    assert "同协变量可确认失败 n=2" in line
    assert "decided_at=2026-11-03T00:00:00" in line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/abug/timesfm && .venv/bin/python -m pytest tests/test_verdict_diag_label.py::test_materialize_inserts_diag_section_without_mutating_rows tests/test_verdict_diag_label.py::test_repeat_count_is_written_only_when_at_least_two -q`

Expected: FAIL。第一节找不到 `## 诊断样本`，第二节找不到 `_format_diag_bullet`。

- [ ] **Step 3: Write minimal implementation**

在 `select_symbol_diag_pair` 之后加入：

```python
def _format_diag_bullet(symbol, side, picked):
    row = picked["positive"] if side == "正面" else picked["negative"]
    empty = picked["positive_empty"] if side == "正面" else picked["negative_empty"]
    if row is None:
        return "- %s %s：%s" % (symbol, side, empty)
    label = format_verdict_diag_label(row)
    da = row.get("dir_acc")
    da_s = ("%.3f" % da) if _diag_finite(da) else "n/a"
    head = "- %s %s" % (symbol, side)
    if side == "反面" and picked.get("cross_symbol"):
        head = "- %s 反面（跨品种 %s）" % (
            symbol, str(row.get("symbol") or "").lower())
    line = "%s：%s | variant_id=%s dir_acc=%s cov=%s" % (
        head, label, row.get("variant_id"), da_s, row.get("cov_override"))
    if row.get("decided_at"):
        line += " decided_at=%s" % row.get("decided_at")
    if side == "反面" and picked.get("cross_symbol") and picked.get("repeat_n", 0) >= 2:
        line += " 同协变量可确认失败 n=%d" % picked["repeat_n"]
    return line


def _diag_sample_lines(items, primary_fp):
    rows = []
    if isinstance(primary_fp, str) and primary_fp:
        rows = [v for v in (items or [])
                if isinstance(v, dict)
                and v.get("protocol_fingerprint") == primary_fp]
    by_sym = {}
    for row in rows:
        by_sym.setdefault(str(row.get("symbol") or "").lower(), []).append(row)
    lines = ["## 诊断样本", _protocol_section_line(primary_fp)]
    for sym in sorted(sup_state.GOAL_SYMBOLS_SET):
        mine = by_sym.get(sym, [])
        others = [row for name, group in sorted(by_sym.items()) if name != sym
                  for row in group]
        picked = select_symbol_diag_pair(mine, others)
        lines.append(_format_diag_bullet(sym, "正面", picked))
        lines.append(_format_diag_bullet(sym, "反面", picked))
    lines.append("")
    return lines
```

在 `materialize_known_verdicts` 里，紧接 `lines.extend(clue_lines)` 之后、`lines.extend(st.render_open_trees(...))` 之前插入：

```python
    lines.extend(_diag_sample_lines(items, _primary_fp))
```

不要改 `items.sort`，不要改 Do not re-propose 的 80 行上限，不要把 `mechanism` 写进新节。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/abug/timesfm && .venv/bin/python -m pytest tests/test_verdict_diag_label.py tests/test_known_verdicts_injection_20261005.py -q`

Expected: 两个文件都 PASS。旧注入测试仍通过，说明其他节没有被改坏。

- [ ] **Step 5: Commit**

在工作树分支上执行，不要在活仓 master 上提交：

```bash
git add tests/test_verdict_diag_label.py scripts/sup_evidence.py
git commit -m "feat: render diagnostic samples into known verdicts"
```

## Task 4: 确认范围没有扩大

**Files:**

- Test: `tests/test_verdict_diag_label.py`
- 只读核对：`scripts/sup_harvest.py`、`task_FM/evaluations/fm_eval/evaluator.py`

**Interfaces:**

- Consumes: Task 3 的工作区。
- Produces: 一份测试输出。没有新的产品代码。

- [ ] **Step 1: 再跑本计划的测试**

Run: `cd /home/abug/timesfm && .venv/bin/python -m pytest tests/test_verdict_diag_label.py tests/test_known_verdicts_injection_20261005.py -q`

Expected: PASS。

- [ ] **Step 2: 确认收割和硬门没有改动**

Run: `cd /home/abug/timesfm && git diff --name-only -- scripts/sup_harvest.py task_FM/evaluations/fm_eval/evaluator.py task_FM/prompt_base.jinja2 scripts/praxist_goal.yaml`

Expected: 无输出。

- [ ] **Step 3: 不重启**

不执行 `docs/three_loop_restart_protocol.md`。线索要等现有进程下一次调用 `materialize_known_verdicts` 才会出现在运行中的文件里。

## 不在本计划里

- 第 4.2 节的提示词轮换，以及 `macro_sentiment` 空家族屏蔽。
- 第 4.3 节的前缀截断测试。将来若写，未来段只能用有限数值冲击，例如价格乘 10。禁止把 `df.iloc[t:]` 改成缺失值。
- 用已失败 `variant_id` 的再次提案率做运行验收。那是线索上线之后的对比，不是这次的测试。

## Self-review

- 规格 S1 到 S5 分别落在 Task 1、Task 2、Task 3、Task 3 的不改行测试、Task 4。
- 去掉正面样本后再跨品种：Task 2 的 `test_only_near_miss_used_as_positive_still_crosses`。
- `status` 和不可确认 DM 先于有限数：Task 1 的前两个测试。
- NaN 的 `p_value`：Task 1 的 `test_nan_p_value_falls_through_to_unstable_label`。
- 第 4.3 节不在任务里。
