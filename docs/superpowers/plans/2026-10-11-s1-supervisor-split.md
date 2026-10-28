# S1 Supervisor Split Implementation Plan

> **代码基线**: `3e8756e`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `scripts/praxist_supervisor.py`（HEAD `9850af2`，4574 行）按 S1 SPEC v3.2 拆成 9 个 `scripts/sup_*.py` 加一个 ≤200 行的兼容入口，外部 `import praxist_supervisor as sup` 的调用保持可用。

**Architecture:** 符号归属以 SPEC 附录 A 为唯一表。每个符号只在它的 home 模块里用裸名定义；其他模块在调用时写 `home.name`，禁止 `from home import name`（那是值拷贝，monkeypatch 和 `_SHUTDOWN_REQUESTED = True` 都会静默失效）。入口模块用 PEP 562 `__getattr__` 把 `sup.name` 的读转到 home，这样测试里 `sup._foo()` 不用改。`setattr` 和属性赋值改到 home，因为模块赋值不经过 `__getattr__`。依赖顺序就是 SPEC §3.2 的 DAG。

**Tech Stack:** Python 3 标准库 `ast`、现有 pytest。不新增依赖。本机没有 `.venv`，用 `python3 -m pytest`。不要用 `.venv/bin/python`（SPEC §7 的那条命令在这台 WSL 上不存在）。

**Spec:** `docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md`（commit `9850af29a72b03bcfe921ec54a739e93a6f6636f`，版本 v3.2）

## Global Constraints

- 基线是 `9850af2` 的 `scripts/praxist_supervisor.py`，4574 行。当前 `/root/timesfm` 索引里有一份已暂存的 4516 行删改（删掉 `VALID_TIER_VALUES`、`is_valid_tier`、abandon 分支、`active_runs.json` 两段式写入）。那不是本计划的输入。在新 worktree 里从 `9850af2` 开工，不要在脏索引上改。
- 向后兼容第一：`import praxist_supervisor as sup` 之后，附录 A.1 里 34 个公开函数，以及提升后的 `is_valid_tier`，都能通过属性访问拿到。
- 零运行时依赖变更。不新增第三方包，不改 `main()` 的参数和启动顺序。
- 所有新模块都放在 `scripts/`，和现在的入口同级。不要建子包。`_prescreen_async` 用 `dirname(dirname(__file__))` 找仓库根，换目录会算错。
- 不改任何 gate / verdict 阈值，不改 `_current_protocol_fingerprint` 和 `_baseline_protocol_fingerprint` 的函数体，不 bump protocol fingerprint。
- `family_for` 保持为 `_maybe_enqueue_confirmations` 内部的嵌套函数，不提升。
- 死导入 `_fam_report_scope` 不复制到新模块，也不从 shim 导出。
- 任何 `sup_*` 模块禁止 `import praxist_supervisor`。否则和 shim 成环。
- 函数体内的惰性 `import` 随宿主函数原样搬家，不为它们新建模块。
- 拆分过程不重启 `/home/abug/timesfm` 上的 supervisor。那台机器不在本环境。Task 12 只留给宿主人工执行。
- 开工的第一条命令是 `git -C /root/timesfm worktree add -b feat/s1-supervisor-split /root/timesfm-s1 9850af2`。分支或目录已存在就停下来问，不要重置。之后所有读写和 git 都在 `/root/timesfm-s1`，每条 git 命令都带 `git -C /root/timesfm-s1`。不要在 `/root/timesfm` 里 add 或 commit。那里的索引已经暂存了 SPEC 和一批测试的删除。
- 每个任务一个 commit。作者用 `git -C /root/timesfm-s1 -c user.name=FlyBuddy -c user.email=abug@flybuddy.local`。新文件先 `chmod 644`。只 add 本任务列出的路径。禁止 `git add -u`、`git add -A`、`git add tests`。本机 pytest 7.4.4 遇到收集错误会中断整个会话，junit 里就只剩那几十个收集错误。每次 `python3 -m pytest` 都带 `--continue-on-collection-errors`。缺 torch 和 sklearn 是既有环境，不要安装。提交前 `git -C /root/timesfm-s1 diff --cached --name-only` 必须逐行等于该任务的路径清单，否则中止，不要 commit。
- 测试命令都在 worktree 根目录用 bash 跑。`python3 -m pytest`。torch 缺失导致的收集失败若在基线就存在，记入基线，不要顺手修。Windows 上的 PowerShell 没有 heredoc，commit message 写进 `/tmp/s1-msg.txt`，用 `git commit -F`。

## 锁定的实现决定

这些决定 SPEC 正文彼此冲突，实施时按这里，不按另一处。

1. **附录 A 压过 §2.3 的散文清单。** `PHASES` 和 `POLL_S` 在 A.3，归 `sup_paths`。§2.3 的路径散文漏了它们。§2.4 的 import 块已经包含它们。决定 8 的六处归属改写压过附录 A。
2. **内部引用用 `home.name`，shim 用 `__getattr__`。** §2.4 的 `from sup_X import name` 是值拷贝，和 §4.1 描述的失效方式相同。shim 保留 §2.4 的 `__all__` 名单，但名字不在 import 时绑定进模块字典，而是：

```python
_HOMES: dict[str, object] = {}  # 每搬完一个模块就填 name -> module

def __getattr__(name):
    mod = _HOMES.get(name)
    if mod is None:
        raise AttributeError(name)
    return getattr(mod, name)
```

   shim 的 path bootstrap 用一个不在 `_HOMES` 里的名字，然后再 `import sup_paths`：

```python
_BOOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BOOT_DIR)
sys.path.insert(0, os.path.dirname(_BOOT_DIR))
import sup_paths
```

   不要写 `HERE = ...` 或 `FM_ROOT = ...`，也不要 `from sup_paths import HERE`。这两个名字都在 `_HOMES` 里。模块字典里一旦有同名绑定，PEP 562 的 `__getattr__` 就不会再被调用，`sup.HERE` 会停在 bootstrap 那份字符串上，之后补丁 `sup_paths.HERE` 看不见。HEAD 只有 4178 和 4191 两处读 `HERE`，都是 `os.path.join(HERE, "aligned_slow_loop.py")`，Task 3 改成 `sup_paths.HERE`。现有测试不补丁 `HERE`。`FM_ROOT` 有 4 处 setattr：`tests/test_supervisor.py:8`、`tests/test_search_promote_20261007.py:164`、同文件 `:190`、`tests/test_success_delta_gate_20261005.py:243`。Task 3 的 retarget 把它们打到 `sup_paths`。`tests/test_timesfm_model_path.py:21` 打的是 `data.config.FM_ROOT`，不要改。测试会 `import scripts.praxist_supervisor`，那时 `scripts/` 还不在 `sys.path` 上，所以这两次 insert 必须发生在 `import sup_paths` 之前。
3. **`import registry_lib as rl` 留在 shim 和每个用到 `rl` 的 home 里。** 九处 `sup.rl.方法` 打在模块对象上，各文件 `import registry_lib as rl` 拿到的是同一个模块，这类补丁不要改。另外两处是整对象替换，必须在 Task 8 改掉，不能留到 Task 11：`tests/test_confirm_bugs_20261003.py:95` 和 `tests/test_fixes_20261003.py:149`。它们把 `sup.rl` 换成带 `in_flight_ids` / `queue_enqueue` / `load_snapshot` 的假对象，再调 `_maybe_enqueue_confirmations`。HEAD 507 行立刻调用 `_active_protocol_snapshot`，3031 行用 `rl.load_snapshot`。这个函数在 Task 8 进 `sup_evidence` 之后走 `sup_evidence.rl`，假对象还挂在 shim 上就看不见。Task 8 起两处都改成 `install_fake_rl(monkeypatch, fake)`：扫描已加载的 `praxist_supervisor` 和每个 `sup_*`，谁的 `__dict__` 里有 `rl` 就 setattr。后面新建的模块只要在 import 监督环时执行了 `import registry_lib as rl`，同一次扫描就盖住，不用再改测试。
4. **`is_valid_tier` 的调用点保持 `is_valid_tier(v)`。** SPEC §3.0 写「改成 `is_valid_tier(v, log)`」，但 `build_snapshot`（HEAD 1121 行）没有 `log` 这个局部变量。嵌套函数里的 `log` 只在非法 tier 分支被用到，今天会 `NameError`。按 SPEC 的签名把 `log` 默认成 `None`：不传就不记日志、不抛。不要在成功路径上引用不存在的 `log`。这是 SPEC 明确要的唯一行为差，单独放在 Task 2 的 commit message 里。不 bump fingerprint。
5. **patch 脚本用 AST，别名来自 `praxist_supervisor` 和 `scripts.praxist_supervisor`。** 实测别名：`as sup` 14 条 import、13 个文件（`test_admissibility_rule.py` 导入两次）；`as S` 13 个文件；`as sv` 1 个文件（`test_confirmation_wiring.py`）；`import scripts.praxist_supervisor as s` 1 个文件（`test_prescreen_score.py`）。`test_supervisor.py:203` 的 `"import praxist_supervisor as s; "` 是字符串，不许改。
6. **死代码闸门不用改名单。** `tests/test_no_dead_code.py` 要求 `scripts/` 顶层模块被 import 到。shim 的 `import sup_*` 就是那条边。不要把 `sup_*` 写进 `LIVE_ENTRIES`。
7. **§2.4 的 import 名单已经覆盖测试里的属性读取**（那些名字多数不在 `__all__` 里，但在 import 块里）。`rl` 是例外，见决定 3。最终测试用 AST 再对一遍，缺一个就补进 `_HOMES`。
8. **六处归属改写，不放开反向 import。** 解析器先按附录 A 原样出表。实施用的 `HOME` 再盖上下表。evidence 仍然禁止 `import sup_harvest` 和 `import sup_family`。state 禁止 `import sup_evidence` 和 `import sup_family`。不要把常量复制成两份。

| 符号 | 附录 A | 实施 home | 依据 |
|---|---|---|---|
| `CROSS_MATRIX_MAX_ROWS` | sup_harvest | sup_evidence | 唯一读者 `_cross_matrix_lines`（HEAD 1634，evidence；读点 1657） |
| `OLD_PRIORS_MAX_ROWS` | sup_harvest | sup_evidence | 唯一读者 `_old_protocol_prior_lines`（1689，evidence；读点 1696） |
| `_CONFIRMATORY_DM` | sup_family | sup_evidence | 读者是 `_is_confirmable_failure`（1859）和 `_family_confirmatory_counts`（1870）。`_cross_run_repeat_counts` 不读它 |
| `_CONFIRM_DATA_CACHE` | sup_family | sup_state | 唯一读写者 `_latest_data_dt`（450，458，473）。family 只调 `sup_state._latest_data_dt` |
| `_CONFIRM_DATA_TTL_S` | sup_family | sup_state | 读点在 `_latest_data_dt`（459） |
| `_ev_mod_for_goal` | sup_state | sup_evidence | HEAD 1803 的赋值和 1808 的 `del` 跟着 `_load_evaluator`。`GOAL_SYMBOLS_SET = _load_goal_symbols()`（1807）留在 state。`_load_goal_symbols` 不读这个名字 |

有效赋值数：`sup_state` 6，`sup_harvest` 4，`sup_evidence` 11，`sup_family` 6。函数数仍是附录 A 的数字。

`tests/test_known_verdicts_injection_20261005.py:118` 的 `setattr(sup, "CROSS_MATRIX_MAX_ROWS", 1)` 在 Task 8 改到 `sup_evidence`。同文件 185 行对 `sup.OLD_PRIORS_MAX_ROWS` 的读走 `__getattr__`，不改。`tests/test_confirm_bugs_20261003.py` 里三处 `sup._CONFIRM_DATA_CACHE.clear()` 不改：`clear` 改的是 `__getattr__` 返回的同一个 dict。2137 行写明这两个行数常量就是给测试 monkeypatch 的，retarget 跟新 home 走。

## Review Focus

这五条是拆完之后最容易静默坏掉、而现有测试语义本身不会点名的情况。每条的测试写在对应任务里。

1. 非法 tier（`"1"`、`"可预测"`、`None`）进 `build_snapshot` 时，函数必须返回、不抛 `NameError`，并且该变体不计进 tier A/B。今天的嵌套函数在记日志时会炸。
2. 测试把 `QUEUE` 指到临时文件之后，`_queue_busy` 必须读到那个临时路径。`from sup_paths import QUEUE` 会让 patch 看起来成功、实际仍读生产队列。
3. `_SHUTDOWN_REQUESTED = True` 写在 `sup_lifecycle` 上时，`_sleep_interruptible` 必须立刻返回，不能再 `time.sleep`。布尔值被 import 拷走就会睡满。
4. `family_for` 如果被提成模块函数，就抓不到 `_maybe_enqueue_confirmations` 的 `pool`，确认派发会把家族算成 `None`。
5. `test_prescreen_score.py` 把 `logging` 换成假的 logger。假 logger 若留在 shim 上，`_prescreen_async` 的 warning 会进真日志，测试还可能照样绿。

---

### Task 1: 干净 worktree 和符号表

**Files:**
- Create: `/root/timesfm-s1`（git worktree，分支 `feat/s1-supervisor-split`，起点 `9850af2`）
- Create: `tests/s1_symbol_home.py`
- Test: `tests/test_s1_symbol_home.py`

**Interfaces:**
- Consumes: SPEC 附录 A.1、A.2、A.3 的表格。
- Produces: `HOME: dict[str, str]`，键是符号名，值是 `sup_paths` … `sup_loops`。`NESTED: dict[str, str]`，键是 A.2 的函数名，值是宿主函数名。后续每个任务只搬 `HOME` 里属于自己的键。

- [ ] **Step 1: 先建 worktree，再写失败测试**

```bash
git -C /root/timesfm worktree add -b feat/s1-supervisor-split /root/timesfm-s1 9850af2
```

cwd 改到 `/root/timesfm-s1`。把本计划复制到该 worktree 的 `docs/superpowers/plans/2026-10-11-s1-supervisor-split.md`。Task 1 不提交计划正文。分支或目录已存在就停下来问，不要重置。

然后在 worktree 里写 `tests/test_s1_symbol_home.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s1_symbol_home import ASSIGNS, FUNCS, HOME, NESTED, OVERRIDES

RAW = {
    "sup_paths": (0, 23),
    "sup_env": (5, 1),
    "sup_state": (15, 5),
    "sup_lifecycle": (11, 6),
    "sup_provider": (15, 0),
    "sup_harvest": (14, 6),
    "sup_evidence": (43, 7),
    "sup_family": (21, 9),
    "sup_loops": (26, 0),
}
EFFECTIVE = {
    "sup_paths": (0, 23),
    "sup_env": (5, 1),
    "sup_state": (15, 6),
    "sup_lifecycle": (11, 6),
    "sup_provider": (15, 0),
    "sup_harvest": (14, 4),
    "sup_evidence": (43, 11),
    "sup_family": (21, 6),
    "sup_loops": (26, 0),
}

def test_raw_appendix_and_effective_home():
    assert len(FUNCS) == 150
    assert len(ASSIGNS) == 57
    assert len(NESTED) == 10
    assert set(HOME) == set(FUNCS) | set(ASSIGNS)
    assert NESTED["family_for"] == "_maybe_enqueue_confirmations"
    assert NESTED["is_valid_tier"] == "build_snapshot"
    assert "is_valid_tier" not in FUNCS
    assert OVERRIDES == {
        "CROSS_MATRIX_MAX_ROWS": "sup_evidence",
        "OLD_PRIORS_MAX_ROWS": "sup_evidence",
        "_CONFIRMATORY_DM": "sup_evidence",
        "_CONFIRM_DATA_CACHE": "sup_state",
        "_CONFIRM_DATA_TTL_S": "sup_state",
        "_ev_mod_for_goal": "sup_evidence",
    }
    for name, mod in OVERRIDES.items():
        assert ASSIGNS[name] != mod
        assert HOME[name] == mod
    for mod, (nf, na) in RAW.items():
        assert sum(1 for m in FUNCS.values() if m == mod) == nf
        assert sum(1 for m in ASSIGNS.values() if m == mod) == na
    for mod, (nf, na) in EFFECTIVE.items():
        assert sum(1 for m in FUNCS.values() if m == mod) == nf
        assert sum(1 for name, m in HOME.items() if name in ASSIGNS and m == mod) == na
```

契约：`FUNCS` 是 A.1 的 150 个顶层函数，`ASSIGNS` 是 A.3 的 57 个赋值，`NESTED` 是 A.2 的 10 个嵌套函数。`OVERRIDES` 是决定 8 那六项，写死，不从 SPEC 解析。`HOME = {**FUNCS, **ASSIGNS, **OVERRIDES}`。后续任务只按 `HOME` 搬。`is_valid_tier` 只出现在 `NESTED`。Task 2 不改这张表。

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_s1_symbol_home.py -q --tb=line`

Expected: FAIL，`ModuleNotFoundError: s1_symbol_home`。路径插入已经写在测试里。

- [ ] **Step 3: 写解析器**

`tests/s1_symbol_home.py` 读 SPEC 路径 `docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md`。只解析三个表：

- `### A.1` 到 `### A.2`：函数名、目标模块。目标模块单元格里用正则取出第一个 `sup_[a-z]+`。
- `### A.2` 到 `### A.3`：函数名、宿主函数名。
- `### A.3` 到 `### A.4`：符号名、目标模块。

导出 `FUNCS`、`ASSIGNS`、`NESTED`、`OVERRIDES`、`HOME`。前三张表从 SPEC 解析，不要手抄 217 行。`OVERRIDES` 用决定 8 的六项字面量。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_s1_symbol_home.py -q --tb=line`

Expected: PASS。同时 `wc -l scripts/praxist_supervisor.py` 必须是 4574。

- [ ] **Step 5: 记录全量基线，然后提交**

Run: `python3 -m pytest --continue-on-collection-errors tests/ -q --tb=no -p no:cacheprovider --junitxml=/tmp/s1-baseline.xml`

把 junit 留在 `/tmp/s1-baseline.xml`。不要提交。基线里已有的失败，后面的任务不得增加新的失败节点。同一时刻再跑：

```bash
python3 scripts/praxist_supervisor.py --dry-run --once > /tmp/s1-dry-before.txt 2>&1 || true
```

缺 key 或数据库时允许非 0。这个文件是 Task 11 的对照，不要提交。

```bash
chmod 644 tests/s1_symbol_home.py tests/test_s1_symbol_home.py
git -C /root/timesfm-s1 add tests/s1_symbol_home.py tests/test_s1_symbol_home.py
git -C /root/timesfm-s1 diff --cached --name-only
git -C /root/timesfm-s1 -c user.name=FlyBuddy -c user.email=abug@flybuddy.local commit -m "test(s1): 从 SPEC 附录 A 解析符号归属表"
```

`diff --cached --name-only` 只能是上面那两个路径。多一行就中止。计划正文留到 Task 11 再提交。

---

### Task 2: 把 is_valid_tier 提为模块级函数

**Files:**
- Modify: `scripts/praxist_supervisor.py`（HEAD 1150–1162 的嵌套函数，以及 1166、1185 两处调用）
- Test: `tests/test_tier_domain_guard.py`

**Interfaces:**
- Consumes: 现有 `VALID_TIER_VALUES = frozenset({"S", "A", "B", "C", "D"})`（HEAD 25 行）。`_log_decision(log_path, action, reason, refs=None)` 不变。
- Produces: `is_valid_tier(v, log=None) -> bool`，定义在 `praxist_supervisor` 模块顶层。Task 8 再把它搬进 `sup_evidence`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_tier_domain_guard.py` 末尾追加，不要改已有四个测试：

```python
def test_is_valid_tier_invalid_calls_log_and_returns_false():
    import praxist_supervisor as sup
    seen = []
    ok = sup.is_valid_tier(
        {"variant_id": "v1", "tier": "可预测"},
        log=lambda event, msg: seen.append((event, msg)),
    )
    assert ok is False
    assert seen == [("tier_domain_violation", "variant=v1 tier=可预测")]


def test_is_valid_tier_without_log_does_not_raise():
    import praxist_supervisor as sup
    assert sup.is_valid_tier({"tier": "1"}) is False
    assert sup.is_valid_tier({"variant_id": "v2"}) is False
    assert sup.is_valid_tier({"tier": "A"}) is True


def test_build_snapshot_invalid_tier_does_not_raise(monkeypatch):
    import praxist_supervisor as sup
    row = {"variant_id": "v", "tier": "1", "symbol": "rb",
           "gate_pass": False, "dir_acc": 0.5}
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp")
    monkeypatch.setattr(sup, "symbol_goal_tier", lambda variants, symbol: {
        "tier": "不可预测", "n_confirmed_variants": 0})
    monkeypatch.setattr(sup, "GOAL_SYMBOLS_SET", frozenset({"rb"}))
    # registry_lib.load_snapshot 返回 {variant_id: row}，没有 "variants" 键。
    # 1165 行的 snap.get("variants") 在真实快照上是空的，而且 n_tier_a_or_b 不在返回值里。
    # 按品种计数走 1181 行的 snap.values()，写入 1208 行的 n_tier_a_b。
    monkeypatch.setattr(sup.rl, "load_snapshot", lambda *a, **k: {"v": row})
    monkeypatch.setattr(sup.rl, "pass_variants", lambda snap: [])
    out = sup.build_snapshot("unused", 0, 0, 0)
    assert out["symbol_stats"]["rb"]["n_tier_a_b"] == 0
```

不要把 1181 行改成 `snap.get("variants")`。那会把真实裁决全部挤出 `symbol_stats`。Task 5 的 retarget 会把 `GOAL_SYMBOLS_SET` 这处 setattr 改到 `sup_state`，那是对的。`_current_protocol_fingerprint` 和 `symbol_goal_tier` 留到 Task 8 再改到 `sup_evidence`。

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_tier_domain_guard.py -q --tb=line`

Expected: FAIL，`module 'praxist_supervisor' has no attribute 'is_valid_tier'`。

- [ ] **Step 3: 提升函数**

用 SPEC §3.0 的函数体，原样放在 `VALID_TIER_VALUES` 之后：

```python
def is_valid_tier(v, log=None):
    """校验 tier 值域，防止非法值混入。

    Args:
        v: variant dict（调用方保证非 None）。
        log: 可选日志函数。模块级调用时提供，
             build_snapshot 内不传（该作用域没有 log 路径）。
    """
    tier = v.get("tier")
    if tier is None:
        return False
    if tier not in VALID_TIER_VALUES:
        if log is not None:
            log("tier_domain_violation", f"variant={v.get('variant_id', 'unknown')} tier={tier}")
        return False
    return True
```

删掉 `build_snapshot` 内部 1150–1162 的嵌套定义。1166 和 1185 的调用保持 `is_valid_tier(v)`。不要加 `isinstance(v, dict)`。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_tier_domain_guard.py tests/test_supervisor.py -q --tb=line`

Expected: PASS。`grep -l tier_domain_violation tests/test_tier_domain_guard.py` 有输出。

- [ ] **Step 5: Commit**

在 `/root/timesfm-s1` 里 `chmod 644`。git 必须带 `-C`，不要在 `/root/timesfm` 的 shell 里裸跑 `git add`。message 写到 `/tmp/s1-msg.txt`，三行正文是：

```text
refactor(s1): 提升 is_valid_tier 为模块级函数

非法 tier 分支不再因为未定义的 log 抛 NameError。
不传 log 时只返回 False，不写决策日志。不 bump protocol fingerprint。
```

```bash
chmod 644 tests/test_tier_domain_guard.py scripts/praxist_supervisor.py
git -C /root/timesfm-s1 add tests/test_tier_domain_guard.py scripts/praxist_supervisor.py
git -C /root/timesfm-s1 diff --cached --name-only
git -C /root/timesfm-s1 -c user.name=FlyBuddy -c user.email=abug@flybuddy.local commit -F /tmp/s1-msg.txt
```

`diff --cached --name-only` 只能是上面那两个路径。后面的任务同样：message 用 `-F`，禁止 heredoc，禁止裸 `git add`。

---

### Task 3: sup_paths，并让队列路径在调用时读取

**Files:**
- Create: `scripts/sup_paths.py`
- Create: `tests/s1_retarget_patches.py`
- Modify: `scripts/praxist_supervisor.py`
- Test: `tests/test_sup_modules.py`
- Test: `tests/test_s1_retarget_patches.py`

**Interfaces:**
- Consumes: `ASSIGNS` 里值为 `sup_paths` 的 23 个名字。HEAD 7–8 行和 80–92、146–149、155–156、171、188–189 行的右侧表达式。
- Produces: `import sup_paths` 之后，这 23 个名字是 `sup_paths` 的属性。`QUEUE` 的值仍是 `os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl")`，其余路径保持 HEAD 的拼接方式。这两行只出现在 `sup_paths.py`：`HERE = os.path.dirname(os.path.abspath(__file__))`，`FM_ROOT = os.path.dirname(HERE)`。shim 不复制它们。

- [ ] **Step 1: 写失败测试**

`tests/test_sup_modules.py`：

```python
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

def test_queue_busy_reads_sup_paths_at_call_time(monkeypatch):
    import registry_lib
    import sup_paths
    import praxist_supervisor as sup
    seen = []
    monkeypatch.setattr(sup_paths, "QUEUE", "SENTINEL_Q")
    monkeypatch.setattr(sup_paths, "INPROGRESS", "SENTINEL_I")

    def fake_load(path):
        seen.append(path)
        return []

    monkeypatch.setattr(registry_lib, "queue_load", fake_load)
    assert sup._queue_busy() is False
    assert seen == ["SENTINEL_Q", "SENTINEL_I"]

def test_shim_here_follows_sup_paths(monkeypatch):
    import sup_paths
    import praxist_supervisor as sup
    monkeypatch.setattr(sup_paths, "HERE", "/tmp/s1-here")
    monkeypatch.setattr(sup_paths, "FM_ROOT", "/tmp/s1-root")
    assert sup.HERE == "/tmp/s1-here"
    assert sup.FM_ROOT == "/tmp/s1-root"
    assert "HERE" not in vars(sup)
    assert "FM_ROOT" not in vars(sup)
```

`tests/test_s1_retarget_patches.py` 用一段临时源码喂给脚本的纯函数 `retarget_source(src: str, names: set[str]) -> str`：

```python
SAMPLE = '''
s = {}
s.update(over)
s.short_horizon_only = True
name = "%s_%s.json" % ("a", "b")
open("sup.lock")
text = "import praxist_supervisor as s; "
import praxist_supervisor as sup
monkeypatch.setattr(sup, "QUEUE", "x")
monkeypatch.setattr(sup, "load_state", fake)
'''

def test_retarget_only_selected_names_and_ignores_local_s():
    from s1_retarget_patches import retarget_source
    out = retarget_source(SAMPLE, {"QUEUE"})
    assert 'setattr(sup_paths, "QUEUE", "x")' in out
    assert 'setattr(sup, "load_state", fake)' in out
    assert "s.update(over)" in out
    assert "s.short_horizon_only = True" in out
    assert '"%s_%s.json"' in out
    assert "sup.lock" in out
    assert "import praxist_supervisor as s;" in out
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_queue_busy_reads_sup_paths_at_call_time tests/test_sup_modules.py::test_shim_here_follows_sup_paths tests/test_s1_retarget_patches.py -q --tb=line`

Expected: FAIL，`sup_paths` 或 `s1_retarget_patches` 不存在。

- [ ] **Step 3: 建模块、改读路径、写 retarget**

`scripts/sup_paths.py` 只放那 23 个赋值和它们需要的 `import os`。表达式从 HEAD 原样搬，不要改字符串。

`praxist_supervisor.py`：删掉这 23 个赋值，包括 HEAD 7–8 行的 `HERE` 和 `FM_ROOT`。文件开头换成决定 2 的 `_BOOT_DIR` bootstrap，然后 `import sup_paths`。不要留下 `HERE =` 或 `FM_ROOT =`。把仍留在本文件里的、对这 23 个名字的自由变量读写改成 `sup_paths.NAME`。HEAD 4178 和 4191 改成 `sup_paths.HERE`。嵌套函数同样改。不要 `from sup_paths import QUEUE`，也不要 `from sup_paths import HERE`。

在 monolith 加上决定 2 的 `_HOMES` 和 `__getattr__`。还定义在 monolith 里的名字不要放进 `_HOMES`。这 23 个路径名放进 `_HOMES`，值是 `sup_paths`。以后每搬一个模块，就在同一个 commit 里把搬走的名字从 monolith 删掉并登记进 `_HOMES`。

`tests/s1_retarget_patches.py`：

- `retarget_source` 用 `ast` 解析。找到 `import praxist_supervisor as <alias>` 和 `import scripts.praxist_supervisor as <alias>`。
- 只改两类节点：`monkeypatch.setattr(<alias>, "<name>", ...)` 或 `setattr(<alias>, "<name>", ...)`，以及 `<alias>.<name> = ...`（Assign / AnnAssign / AugAssign）。`<name>` 必须在本次 `names` 里。
- 把被改节点的对象换成 home 模块名。home 从 `s1_symbol_home.HOME` 查。测试文件若还没 import 该模块，在文件第一个 import 区加上 `import <home>`。
- 不改字符串、不改局部变量 `s`、不改 `setattr(<alias>.time, ...)` 这种已经是属性对象的调用。
- CLI：`python3 tests/s1_retarget_patches.py --names QUEUE,INPROGRESS,...` 就地改 `tests/**/*.py`，跳过 `tests/archive/`。

然后对这 23 个路径名跑一遍 CLI。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_queue_busy_reads_sup_paths_at_call_time tests/test_sup_modules.py::test_shim_here_follows_sup_paths tests/test_s1_retarget_patches.py tests/test_supervisor.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
chmod 644 scripts/sup_paths.py scripts/praxist_supervisor.py tests/s1_retarget_patches.py tests/test_s1_retarget_patches.py tests/test_sup_modules.py
git -C /root/timesfm-s1 status --short
git -C /root/timesfm-s1 add scripts/sup_paths.py scripts/praxist_supervisor.py tests/s1_retarget_patches.py tests/test_s1_retarget_patches.py tests/test_sup_modules.py
```

Message: `refactor(s1): 抽出 sup_paths，队列路径在调用时读取`

retarget 改过的测试逐个 `git -C /root/timesfm-s1 add <path>`。禁止 `git add -u`。`git -C /root/timesfm-s1 diff --cached --name-only` 对完再 commit。出现本任务之外的删除或修改就停下来。

---

### Task 4: sup_env

**Files:**
- Create: `scripts/sup_env.py`
- Modify: `scripts/praxist_supervisor.py` 和 retarget 点到的测试

**Interfaces:**
- Consumes: `sup_paths.FM_ROOT`、`sup_paths.HERE`。`FUNCS` 里 `sup_env` 的 5 个函数：`_resolve_praxist_bin`、`_praxist_bin`、`_load_dotenv`、`_check_required_env`、`_praxist`。赋值 `_PRAXIST`。
- Produces: 这 6 个名字在 `sup_env` 上。`_praxist` 的签名和 HEAD 1028 行一致。其他模块调用写成 `sup_env._praxist`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_sup_modules.py` 增加：

```python
def test_praxist_bin_cache_lives_on_sup_env():
    import sup_env
    saved = sup_env._PRAXIST
    try:
        sup_env._PRAXIST = "/tmp/fake-praxist"
        assert sup_env._praxist_bin() == "/tmp/fake-praxist"
    finally:
        sup_env._PRAXIST = saved
```

HEAD 75–79 行：`_PRAXIST` 不是 `None` 时直接返回，不检查文件是否存在。模块初值是 `None`。

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_praxist_bin_cache_lives_on_sup_env -q --tb=line`

Expected: FAIL，`No module named 'sup_env'`。

- [ ] **Step 3: 搬函数**

把 5 个函数和 `_PRAXIST` 原样搬进 `sup_env.py`。函数里对路径名的引用保持 Task 3 已经改成的 `sup_paths.NAME`。登记 `_HOMES`。从 monolith 删除定义。对这 6 个名字跑 retarget CLI。`_check_required_env` 仍返回 `(missing_required, missing_recommended)`，必填键仍是 `ANTHROPIC_API_KEY`。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py tests/test_supervisor.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。

- [ ] **Step 5: Commit**

Message: `refactor(s1): 抽出 sup_env`

只 add `scripts/sup_env.py`、`scripts/praxist_supervisor.py` 和 retarget 改到的测试。

---

### Task 5: sup_state

**Files:**
- Create: `scripts/sup_state.py`
- Modify: `scripts/praxist_supervisor.py` 和 retarget 点到的测试

**Interfaces:**
- Consumes: `sup_paths`。`FUNCS` 里 15 个 `sup_state` 函数，包含 `_ensure_tokens_baseline`、`_read_token_m`、`_token_spend_m`、`load_preregistry`、`_latest_data_dt`、`_merge_save`。赋值 6 个：`_CADENCE_DEFAULTS`、`_GOAL_YAML_DEFAULT`、`_GOAL_SYMBOLS_CACHE`、`GOAL_SYMBOLS_SET`、`_CONFIRM_DATA_CACHE`、`_CONFIRM_DATA_TTL_S`。`_ev_mod_for_goal` 不在这里，见决定 8。
- Produces: `load_state()`，没有 `path` 参数（HEAD 764 行）。`load_state` 在本模块内调用裸名 `_ensure_tokens_baseline`。`_latest_data_dt` 用裸名读写 `_CONFIRM_DATA_CACHE`。其他模块写 `sup_state.load_state` 和 `sup_state._latest_data_dt`。family 不自己持有这份缓存。

- [ ] **Step 1: 写失败测试**

```python
def test_goal_symbols_cache_resets_on_sup_state():
    import sup_state
    saved = sup_state._GOAL_SYMBOLS_CACHE
    try:
        sup_state._GOAL_SYMBOLS_CACHE = frozenset({"rb"})
        sup_state._reset_goal_symbols_cache()
        assert sup_state._GOAL_SYMBOLS_CACHE is None
    finally:
        sup_state._GOAL_SYMBOLS_CACHE = saved
```

HEAD 883–886 行把 `_GOAL_SYMBOLS_CACHE` 设成 `None`。

- [ ] **Step 2: 跑测试，确认失败**

Expected: FAIL，`No module named 'sup_state'`。

- [ ] **Step 3: 搬函数**

原样搬家。跨模块名字（路径、`_log_decision` 若已被 state 函数调用）写成 `home.name`。`load_state` 对 `_ensure_tokens_baseline` 保持裸名。登记 `_HOMES`。跑 retarget。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py tests/test_supervisor.py tests/test_tech_debt_20261008.py tests/test_symbol_universe_20261008.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。

- [ ] **Step 5: Commit**

Message: `refactor(s1): 抽出 sup_state，token 基线与预注册随状态走`

---

### Task 6: sup_lifecycle

**Files:**
- Create: `scripts/sup_lifecycle.py`
- Modify: `scripts/praxist_supervisor.py` 和 retarget 点到的测试

**Interfaces:**
- Consumes: `sup_paths`。11 个函数：`_now_iso`、`_mark_stop_emitted`、`_emit_event`、`_write_stop_json`、`_write_heartbeat`、`_signal_handler`、`_shutdown_exit`、`_sleep_interruptible`、`_atexit_handler`、`_arm_handlers`、`_log_decision`。6 个赋值：`_EVENT_LOCK`、`_SHUTDOWN_REQUESTED`、`_RUN_ID`、`_START_TIME`、`_STOP_EMITTED`、`_HANDLERS_ARMED`。
- Produces: `_sleep_interruptible(seconds)` 读本模块的 `_SHUTDOWN_REQUESTED`。`_log_decision(log_path, action, reason, refs=None)` 签名不变。`_arm_handlers` 仍不在 import 时注册信号。

- [ ] **Step 1: 写失败测试**

```python
def test_sleep_interruptible_sees_lifecycle_flag(monkeypatch):
    import sup_lifecycle
    calls = []
    monkeypatch.setattr(sup_lifecycle.time, "sleep", lambda n: calls.append(n))
    monkeypatch.setattr(sup_lifecycle, "_SHUTDOWN_REQUESTED", True)
    sup_lifecycle._sleep_interruptible(5)
    assert calls == []
```

- [ ] **Step 2: 跑测试，确认失败**

Expected: FAIL，`No module named 'sup_lifecycle'`。

- [ ] **Step 3: 搬函数**

`_sleep_interruptible`、`_signal_handler`、`_shutdown_exit` 用裸名读写 `_SHUTDOWN_REQUESTED`。其他模块若也读写这个标志，改成 `sup_lifecycle._SHUTDOWN_REQUESTED`。`_now_iso` 留在本模块，调用方写 `sup_lifecycle._now_iso()`。登记 `_HOMES`。

retarget 的名字包括上述 17 个。赋值 `sup._SHUTDOWN_REQUESTED = ...` 必须变成 `sup_lifecycle._SHUTDOWN_REQUESTED = ...`。HEAD 测试里这种赋值有 7 处，setattr 有 4 处。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_sleep_interruptible_sees_lifecycle_flag tests/test_supervisor.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。`test_sleep_interruptible_sees_lifecycle_flag` 若 sleep 被调用，说明标志被拷贝了，回到 Step 3。

- [ ] **Step 5: Commit**

Message: `refactor(s1): 抽出 sup_lifecycle，停机标志不被拷贝`

---

### Task 7: sup_provider

**Files:**
- Create: `scripts/sup_provider.py`
- Modify: `scripts/praxist_supervisor.py` 和 retarget 点到的测试

**Interfaces:**
- Consumes: `sup_paths`、`sup_state.load_state`、`sup_env._praxist`。15 个函数，含 `parse_429_reset`、`_latest_429_reset`、`_env_first`。没有模块级赋值。
- Produces: `parse_429_reset(log_text)` 仍用 HEAD 758 行的正则。`_latest_429_reset` 在本模块内调用裸名 `parse_429_reset`。

- [ ] **Step 1: 写失败测试**

```python
def test_parse_429_reset_stays_on_provider():
    import sup_provider
    text = "reset at 2026-10-11 01:02:03 +0800"
    assert sup_provider.parse_429_reset(text) is not None
```

返回值以 HEAD 函数为准。测试只断言「能从这串文本里抽出重置时间」，不断言新的格式。

- [ ] **Step 2: 跑测试，确认失败**

Expected: FAIL，`No module named 'sup_provider'`。

- [ ] **Step 3: 搬函数**

`_status_rows` 调用 `sup_env._praxist`，不要在 provider 里再定义 `_praxist`。`_llm_provider` 调用 `sup_state.load_state`。登记 `_HOMES`。跑 retarget。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py tests/test_supervisor.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。

- [ ] **Step 5: Commit**

Message: `refactor(s1): 抽出 sup_provider，parse_429_reset 留在 provider`

---

### Task 8: sup_evidence

**Files:**
- Create: `scripts/sup_evidence.py`
- Create: `tests/s1_fake_rl.py`
- Modify: `scripts/praxist_supervisor.py`、`tests/test_confirm_bugs_20261003.py`、`tests/test_fixes_20261003.py`、`tests/test_known_verdicts_injection_20261005.py`，以及 retarget 点到的其他测试

**Interfaces:**
- Consumes: `sup_paths`、`sup_state`、`sup_lifecycle._log_decision`、`sup_lifecycle._now_iso`。`FUNCS` 里 43 个 `sup_evidence` 函数，加上 Task 2 的 `is_valid_tier`。赋值 11 个：原来的 `VALID_TIER_VALUES`、`LOCKED_WINDOW_MAX_ROWS`、`SUCCESS_DELTA_MIN_CHARS`、`STALE_DATA_DAYS`、`_FP_WEIGHTS_CACHE`、`_FP_TARGET_CACHE`、`_BASELINE_STALENESS_MAX_H`，加上决定 8 的 `CROSS_MATRIX_MAX_ROWS`、`OLD_PRIORS_MAX_ROWS`、`_CONFIRMATORY_DM`、`_ev_mod_for_goal`。嵌套函数 `_da_key`（宿主 `materialize_known_verdicts`）和 `_cutoffs_at_or_after`（宿主 `_guard_confirm_from_ts_after_regen`）随宿主走。`is_valid_tier` 不再嵌套。
- Produces: `build_snapshot(registry_path, cycles_done, cpu_hours_used, tokens_used_m)`。`is_valid_tier(v, log=None)`。`_current_protocol_fingerprint` 与 `_baseline_protocol_fingerprint` 的函数体与 `9850af2` 逐字节相同（Task 2 没有改过它们）。

- [ ] **Step 1: 写失败测试**

```python
def test_is_valid_tier_is_module_level_on_evidence():
    import inspect
    import sup_evidence
    assert inspect.isfunction(sup_evidence.is_valid_tier)
    src = inspect.getsource(sup_evidence.build_snapshot)
    assert "def is_valid_tier" not in src


def test_fingerprint_bodies_match_baseline():
    import ast
    import inspect
    import subprocess
    import sup_evidence
    old = subprocess.check_output(
        ["git", "show", "9850af2:scripts/praxist_supervisor.py"], text=True)
    old_tree = ast.parse(old)
    wanted = {"_current_protocol_fingerprint", "_baseline_protocol_fingerprint"}
    old_src = {}
    for node in old_tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            old_src[node.name] = ast.dump(node, include_attributes=False)
    for name in wanted:
        got = ast.parse(inspect.getsource(getattr(sup_evidence, name)))
        assert ast.dump(got.body[0], include_attributes=False) == old_src[name]
```

- [ ] **Step 2: 跑测试，确认失败**

Expected: FAIL，`No module named 'sup_evidence'`。

- [ ] **Step 3: 搬函数**

只搬 `HOME` 值是 `sup_evidence` 的名字。决定 8 的四项以 `HOME` 为准，不要按附录 A 把它们留在 harvest 或 family。`harvest_*` 名字不许进这个文件。本模块禁止 `import sup_harvest`、`import sup_family`、`import sup_loops`。

`CROSS_MATRIX_MAX_ROWS`、`OLD_PRIORS_MAX_ROWS`、`_CONFIRMATORY_DM` 定义在本模块，读者用裸名。`_ev_mod_for_goal = _load_evaluator()` 和后面的 `del _ev_mod_for_goal` 放在 `_load_evaluator` 定义之后。`GOAL_SYMBOLS_SET = _load_goal_symbols()` 留在 `sup_state`，不要搬过来。

`build_snapshot` 里对 `is_valid_tier` 保持裸名。对 `_log_decision` 写 `sup_lifecycle._log_decision`。登记 `_HOMES`，包括 `is_valid_tier`、`VALID_TIER_VALUES` 和决定 8 改到 evidence 的四个名字。跑 retarget。`tests/test_known_verdicts_injection_20261005.py:118` 的 `CROSS_MATRIX_MAX_ROWS` 必须落到 `sup_evidence`。

同一 commit 新增 `tests/s1_fake_rl.py`：

```python
def install_fake_rl(monkeypatch, fake):
    import sys
    for mod in list(sys.modules.values()):
        name = getattr(mod, "__name__", "")
        if name == "praxist_supervisor" or name.startswith("sup_"):
            if "rl" in vars(mod):
                monkeypatch.setattr(mod, "rl", fake)
```

两个测试文件若还不能 `import s1_fake_rl`，在文件里已有的 path 插入旁边加一次 `sys.path.insert(0, str(Path(__file__).resolve().parent))`，然后 `from s1_fake_rl import install_fake_rl`。`test_confirm_bugs_20261003.py:95` 和 `test_fixes_20261003.py:149` 的 `monkeypatch.setattr(sup, "rl", fake)` 改成 `install_fake_rl(monkeypatch, fake)`。假对象的三个方法原样保留。`sup.rl.方法` 那种补丁不动。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py tests/test_tier_domain_guard.py tests/test_supervisor.py tests/test_baseline_archival.py tests/test_baseline_reanchor.py tests/test_ensure_baselines_fingerprint.py tests/test_success_delta_gate_20261005.py tests/test_success_gate_stale_20261006.py tests/test_confirm_bugs_20261003.py tests/test_fixes_20261003.py tests/test_known_verdicts_injection_20261005.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。指纹测试失败就说明搬家时改过函数体，把那两个函数恢复成 `9850af2` 的原文。

- [ ] **Step 5: Commit**

Message: `refactor(s1): 抽出 sup_evidence，指纹函数体保持不变`

---

### Task 9: sup_harvest

**Files:**
- Create: `scripts/sup_harvest.py`
- Modify: `scripts/praxist_supervisor.py`、`tests/test_prescreen_score.py` 和 retarget 点到的测试

**Interfaces:**
- Consumes: `sup_paths`、`sup_state`、`sup_evidence`（`_verdict_sort_key`、`_is_confirmable_failure`、`_load_evaluator`、`load_symbol_status`、`_symbol_n_table`）、`sup_lifecycle._now_iso`。14 个函数，含 `harvest_survivors`、`harvest_proposals`、`_sector_filter_check`。嵌套 `_run`（宿主 `_prescreen_async`）和 `_reject`（宿主 `harvest_proposals`）。赋值 4 个：`MIN_QUALITY_SCORE`、`COV_CROSS_FAIL_MIN`、`SYMBOL_FAIL_WINDOW`、`COV_FAIL_WINDOW`。`CROSS_MATRIX_MAX_ROWS`、`OLD_PRIORS_MAX_ROWS`、`_CONFIRMATORY_DM` 不在本模块出现。它们的读者在 evidence，本模块只调用那些函数。
- Produces: `harvest_proposals(...)` 签名与 HEAD 2631 行相同。`_prescreen_async` 里的 `logging.warning` 读本模块全局 `logging`。

- [ ] **Step 1: 写失败测试**

```python
def test_prescreen_import_failure_logs_on_harvest_module(monkeypatch):
    import sys
    import sup_harvest
    seen = []

    class FakeLog:
        def warning(self, *args, **kwargs):
            seen.append(args)

    monkeypatch.setattr(sup_harvest, "logging", FakeLog())
    monkeypatch.setitem(sys.modules, "cascade.typesafe_prescreen", None)
    sup_harvest._prescreen_async({}, "/tmp/no-such.json", "rb")
    assert seen
    assert "TypeSafe" in seen[0][0]
```

HEAD 1982 行的格式串以 `TypeSafe` 开头。假 logger 必须装在 `sup_harvest.logging` 上，装在 shim 上这条测试失败。

同时把 `tests/test_prescreen_score.py` 里对 `s.logging` 的读和写改成 `sup_harvest.logging`。该文件的 `import scripts.praxist_supervisor as s` 若只为了换 logger，改完后如果还有别的 `s.` 用法就保留 import。测试逻辑的断言一句不改。

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_prescreen_import_failure_logs_on_harvest_module -q --tb=line`

Expected: FAIL，`No module named 'sup_harvest'`。

- [ ] **Step 3: 搬函数**

禁止 `import sup_loops`。对 evidence 符号写 `sup_evidence.name`。`_prescreen_async` 顶部 `import logging` 必须留在本模块。`__file__` 不要改写法。登记 `_HOMES`。跑 retarget。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_prescreen_import_failure_logs_on_harvest_module tests/test_prescreen_score.py tests/test_harvest_proposals.py tests/test_proposal_quality_gate.py tests/test_sector_filter.py tests/test_covariate_filter.py tests/test_supervisor.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。

- [ ] **Step 5: Commit**

Message: `refactor(s1): 抽出 sup_harvest，预筛日志打在 harvest 模块上`

---

### Task 10: sup_family

**Files:**
- Create: `scripts/sup_family.py`
- Modify: `scripts/praxist_supervisor.py` 和 retarget 点到的测试

**Interfaces:**
- Consumes: `sup_paths`、`sup_state.load_preregistry`、`sup_state._latest_data_dt`、`sup_lifecycle._now_iso`、`sup_evidence.load_covariate_pool`。21 个函数。嵌套 `family_for` 只存在于 `_maybe_enqueue_confirmations` 的源码里。赋值 6 个：`_PERSISTABLE_DM`、`_BASE_COVARIATE`、`_CONFIRMATION_NOTICE`、`_CONFIRMATION_NOTICE_TTL_S`、`_CONFIRM_REDISPATCH`、`_CONFIRM_REDISPATCH_TTL_S`。本模块源码里不出现 `_CONFIRM_DATA_CACHE`、`_CONFIRM_DATA_TTL_S`、`_CONFIRMATORY_DM`。读最新数据时间只写 `sup_state._latest_data_dt(...)`。
- Produces: `family_key_for`、`register_family_member`、`seal_research_family`、`dispatch_confirmation`、`finalize_confirmation`、`due_confirmations`、`confirmation_queue_row`、`fdr_pass_persistable`、`promote_batch_for_persistence` 的签名与 HEAD 相同。没有模块级 `family_for`。

- [ ] **Step 1: 写失败测试**

```python
def test_family_for_stays_nested_over_pool():
    import inspect
    import sup_family
    assert not hasattr(sup_family, "family_for")
    src = inspect.getsource(sup_family._maybe_enqueue_confirmations)
    assert "def family_for(cov):" in src
    assert "pool.get(cov)" in src
```

- [ ] **Step 2: 跑测试，确认失败**

Expected: FAIL，`No module named 'sup_family'`。

- [ ] **Step 3: 搬函数**

`family_for` 整段留在 `_maybe_enqueue_confirmations` 里面，缩进不动。`load_covariate_pool` 写成 `sup_evidence.load_covariate_pool`。不要复制 `_fam_report_scope`。其余 `_fam_*` 别名只在本模块 import。禁止 `import sup_harvest` 和 `import sup_loops`。登记 `_HOMES`。跑 retarget。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_family_for_stays_nested_over_pool tests/test_confirmation_wiring.py tests/test_confirm_bugs_20261003.py tests/test_confirmation_finality_20261004.py tests/test_admissibility_rule.py tests/test_supervisor.py tests/test_no_dead_code.py -q --tb=line -p no:cacheprovider --junitxml=/tmp/s1-task10.xml`

Expected: 相对 `/tmp/s1-baseline.xml` 没有新的失败节点。`tests/test_confirmation_wiring.py:22` 会 import `monthly_backtest`，`scripts/monthly_backtest.py:36` 是模块级 `import torch`。本机没有 torch，收集阶段就会失败，这个节点 Task 1 已经写进基线 xml。不要另写 `/tmp/s1-baseline-fails.txt`。基线 xml 不存在就停，回到 Task 1。

用 Task 11 同一套节点算法比较。写到 `/tmp/s1_task10_junit_diff.py` 再跑：

```python
import xml.etree.ElementTree as ET

def names(path):
    root = ET.parse(path).getroot()
    return {
        f"{case.get('classname')}::{case.get('name')}"
        for case in root.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    }

extra = sorted(names("/tmp/s1-task10.xml") - names("/tmp/s1-baseline.xml"))
print("new failures", len(extra))
print("\n".join(extra))
raise SystemExit(1 if extra else 0)
```

`new failures 0` 才算通过。pytest 进程本身可以非 0，闸门是这个 diff，不是 pytest 的退出码。

- [ ] **Step 5: Commit**

Message: `refactor(s1): 抽出 sup_family，family_for 仍是闭包`

---

### Task 11: sup_loops、shim，以及 patch 审计

**Files:**
- Create: `scripts/sup_loops.py`
- Modify: `scripts/praxist_supervisor.py`（变成 shim，≤200 行）
- Modify: `tests/test_search_tree_stop_rules_20261006.py`（只改 `__file__` 那一处）
- Modify: `tests/test_supervisor.py`（只改 `evaluate_goal` 的那一处 setattr）
- Test: `tests/test_sup_modules.py`

**Interfaces:**
- Consumes: 全部其他 `sup_*`。`FUNCS` 里 26 个 `sup_loops` 函数：`quota_gate`、`_retest_candidates`、`plan_sample_retests`、`_maybe_enqueue_retests`、`_read_cpu_hours`、`_token_budget_hit`、`_in_slow_window`、`_deadline_passed`、`_slow_loop_alive`、`_queue_busy`、`_slow_drain_complete`、`ensure_phase`、`write_stop_report`、`decide_fast_loop`、`main`、`_harvest_rows`、`_commit_search_accepts`、`_sweep_search_stops`、`_append_jsonl`、`_sweep_search_promotions`、`_maybe_harvest`、`wait_for_batch`、`cleanup_batch_workers`、`_maybe_start_slow_loop`、`_maybe_finish_slow`、`_main_locked`。嵌套四个都在 `decide_fast_loop` 里：`_resume_argv`、`_start_argv`、`_plan_resume`、`_plan_start`。
- Produces: `main()` 仍是 `if __name__ == "__main__"` 的入口。`decide_fast_loop(goal, dry_run=False, now=None)`。shim 的 `__all__` 与 SPEC §2.4 代码块里的列表逐项相同、顺序相同。`sup.evaluate_goal` 经 `__getattr__` 读到 `sup_loops.evaluate_goal`，而 `sup_loops` 里是 `from goal_dsl import evaluate_goal`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_sup_modules.py`：

```python
PUBLIC = [
    "fdr_pass_persistable", "promote_batch_for_persistence", "family_key_for",
    "register_family_member", "seal_research_family", "dispatch_confirmation",
    "finalize_confirmation", "confirmation_queue_row", "due_confirmations",
    "load_preregistry", "load_family_members", "save_family_members",
    "parse_429_reset", "load_state", "save_state", "load_goal", "quota_gate",
    "symbol_goal_tier", "build_snapshot", "harvest_survivors",
    "collect_proposed_variant_ids", "materialize_known_verdicts",
    "load_covariate_pool", "load_symbol_status", "harvest_proposals",
    "materialize_covariate_menu", "plan_sample_retests", "ensure_phase",
    "write_stop_report", "decide_fast_loop", "main", "ensure_baselines",
    "wait_for_batch", "cleanup_batch_workers", "is_valid_tier",
]

def test_shim_public_and_all_and_size():
    import ast
    import praxist_supervisor as sup
    for name in PUBLIC:
        assert hasattr(sup, name), name
    text = open(
        "docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md",
        encoding="utf-8",
    ).read()
    start = text.index("__all__ = [")
    end = text.index("]", start)
    expected = ast.literal_eval(text[start:end + 1].split("=", 1)[1])
    assert list(sup.__all__) == expected
    assert len(sup.__all__) >= 80
    assert len(open(sup.__file__, encoding="utf-8").read().splitlines()) <= 200

def test_no_import_cycle_and_no_back_edges():
    import ast
    from pathlib import Path
    forbidden = {
        "sup_paths": {"sup_env", "sup_state", "sup_lifecycle", "sup_provider",
                      "sup_evidence", "sup_harvest", "sup_family", "sup_loops",
                      "praxist_supervisor"},
        "sup_env": {"sup_provider", "sup_evidence", "sup_harvest", "sup_family",
                    "sup_loops", "praxist_supervisor"},
        "sup_state": {"sup_provider", "sup_evidence", "sup_harvest", "sup_family",
                      "sup_loops", "praxist_supervisor"},
        "sup_lifecycle": {"sup_provider", "sup_evidence", "sup_harvest",
                          "sup_family", "sup_loops", "praxist_supervisor"},
        "sup_provider": {"sup_evidence", "sup_harvest", "sup_family", "sup_loops",
                         "praxist_supervisor"},
        "sup_evidence": {"sup_harvest", "sup_family", "sup_loops", "praxist_supervisor"},
        "sup_harvest": {"sup_family", "sup_loops", "praxist_supervisor"},
        "sup_family": {"sup_loops", "praxist_supervisor"},
        "sup_loops": {"praxist_supervisor"},
    }
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name, bad in forbidden.items():
        tree = ast.parse((scripts / f"{name}.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(bad), (name, imported & bad)

def test_no_patch_left_on_shim_for_home_symbols():
    import ast
    from pathlib import Path
    from s1_symbol_home import HOME
    root = Path(__file__).resolve().parents[1] / "tests"
    for path in root.rglob("*.py"):
        if "archive" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in {"praxist_supervisor", "scripts.praxist_supervisor"}:
                        aliases.add(a.asname or "praxist_supervisor")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "setattr":
                continue
            if len(node.args) < 2:
                continue
            target, attr = node.args[0], node.args[1]
            if isinstance(target, ast.Name) and target.id in aliases:
                if isinstance(attr, ast.Constant) and attr.value in HOME:
                    raise AssertionError(f"{path}:{node.lineno} still patches shim {attr.value}")
```

`test_search_tree_stop_rules_20261006.py` 的 `test_sweep_called_every_cycle_in_main_loop`：`open(S.__file__)` 改成 `open(sup_loops.__file__)`，并 import `sup_loops`。断言字符串 `'_sweep_search_stops(goal, log, snap["variants"])'` 一个字不改。

`tests/test_supervisor.py:1837` 的 `monkeypatch.setattr(sup, "evaluate_goal", ...)` 改成 `monkeypatch.setattr(sup_loops, "evaluate_goal", ...)`。同文件 1130 和 1136 的 `sup.evaluate_goal(...)` 直接调用不改。

两处整对象替换已在 Task 8 改成 `install_fake_rl`。本任务不要改回去。`sup_loops` 里的 `import registry_lib as rl` 会在 import 监督环之后被同一次扫描盖住。Step 4 的全量 pytest 必须包含 `test_confirm_bugs_20261003.py` 和 `test_fixes_20261003.py`。

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py::test_shim_public_and_all_and_size tests/test_sup_modules.py::test_no_patch_left_on_shim_for_home_symbols -q --tb=line`

Expected: FAIL。行数仍远大于 200，或还有 setattr 留在 shim 上。

- [ ] **Step 3: 搬主循环并收成 shim**

`sup_loops.py` 拿走剩下的 26 个函数。跨模块调用全部是 `home.name`。`evaluate_goal` 用本模块的 `from goal_dsl import evaluate_goal`，`_main_locked` 里两处调用保持裸名 `evaluate_goal`。

`praxist_supervisor.py` 只留下：

- shebang 和模块 docstring（原文第一行 docstring）
- path bootstrap，只用决定 2 的 `_BOOT_DIR`。`import sup_paths` 紧跟在两次 `sys.path.insert` 之后。源码里不得赋值 `HERE` 或 `FM_ROOT`
- `import time`、`import subprocess`、`import logging`
- `import registry_lib as rl`
- import 九个 `sup_*` 并填充 `_HOMES`（§2.4 import 块里的每一个名字，加上测试 AST 读到、但 §2.4 漏掉的名字）
- `__getattr__` 和 SPEC §2.4 的 `__all__`
- `if __name__ == "__main__": raise SystemExit(sup_loops.main())`

不要在 shim 里再定义业务函数。行数 ≤ 200。最大的 `sup_*.py` 若超过 700 行，停下来报告实际行数，不要再拆一刀。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m pytest --continue-on-collection-errors tests/test_sup_modules.py tests/test_supervisor.py tests/test_search_tree_stop_rules_20261006.py tests/test_tier_domain_guard.py tests/test_prescreen_score.py tests/test_no_dead_code.py -q --tb=line`

Expected: PASS。

然后：

把下面写到 `/tmp/s1_junit_diff.py`，然后跑后面的三条命令。

```python
import xml.etree.ElementTree as ET

def names(path):
    root = ET.parse(path).getroot()
    return {
        f"{case.get('classname')}::{case.get('name')}"
        for case in root.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    }

extra = sorted(names("/tmp/s1-after.xml") - names("/tmp/s1-baseline.xml"))
print("new failures", len(extra))
print("\n".join(extra))
raise SystemExit(1 if extra else 0)
```

```bash
python3 -m pytest --continue-on-collection-errors tests/ -q --tb=no -p no:cacheprovider --junitxml=/tmp/s1-after.xml
python3 /tmp/s1_junit_diff.py
python3 scripts/praxist_supervisor.py --dry-run --once > /tmp/s1-dry-after.txt 2>&1 || true
diff -u /tmp/s1-dry-before.txt /tmp/s1-dry-after.txt
```

Expected: `new failures 0`，并且 dry-run 的 diff 为空。diff 若只差时间戳或 `run_id`，把那几行记进 commit message，不要改业务代码去抹掉它们。缺 `ANTHROPIC_API_KEY` 时两次都应在同一处失败。不要和线上进程比输出。

- [ ] **Step 5: Commit**

把 `docs/superpowers/plans/2026-10-11-s1-supervisor-split.md` 一并加入。`chmod 644`。

Message: `refactor(s1): 抽出 sup_loops，入口改为 __getattr__ shim`

---

### Task 12: 宿主迁移窗口（不要在本机执行）

**Files:** 无代码改动。

**Interfaces:**
- Consumes: Task 11 的分支。生产目录 `/home/abug/timesfm`。看门狗 `diagnose_three_loop.sh`，每 15 分钟。`maintenance.flag` 的过期是 4 小时。
- Produces: 无。这一任务不是本 worktree 的 commit。

- [ ] **Step 1: 确认执行地点**

只在 `/home/abug/timesfm` 那台宿主上做。从 `/root/timesfm` 或 `/root/timesfm-s1` 执行 `kill`、改 crontab、碰 `maintenance.flag`，都算失败。

- [ ] **Step 2: 停监督环并挡住看门狗**

按 SPEC §5.1：若进程在跑，`kill -TERM <pid>`，`sleep 5`，`pgrep -f praxist_supervisor` 必须是 0。用 maintenance flag 或注释 crontab 里的 `diagnose_three_loop.sh`。窗口超过 3 小时就 `touch /home/abug/timesfm/maintenance.flag`。

- [ ] **Step 3: 部署 Task 11 的 commit，再冒烟**

宿主上的 pytest 用它自己的 `.venv`。`python scripts/praxist_supervisor.py --dry-run --once` 的输出与部署前一次相比，业务行一致。然后 `.venv/bin/python scripts/praxist_supervisor.py --once`。心跳文件由 `_write_heartbeat` 写出之后，再撤掉维护模式，按 `docs/three_loop_restart_protocol.md` 启动。

- [ ] **Step 4: 回滚命令预先写在操作记录里**

```bash
git revert <拆分开始>..<拆分结束> --no-edit
.venv/bin/python -m pytest tests/test_supervisor.py -x -q
```

单步回滚是 `git revert <该步 commit> --no-edit`。中间 commit 不可当作生产版本启动。

---

## 自检记录

- SPEC §3.0 到 §3.1 的步骤 0–10：Task 2 到 Task 11。步骤 1 和 2 并成 Task 3，因为只创建 `sup_paths.py` 而不 import 会让 `test_no_dead_code` 失败。
- §4.2 的 AST retarget、四种别名、`scripts.praxist_supervisor`、`__file__`、`evaluate_goal`、`logging`：Task 3 和 Task 11。
- §4.3 死代码闸门：决定 6，每个抽出任务都跑 `test_no_dead_code.py`。
- §4.5 新测试：`tests/test_sup_modules.py` 在 Task 3 起生长，Task 11 补齐 `__all__`、行数、环。
- §5.1：Task 12，且禁止在 WSL 执行。
- §6 的行数、34+1 个公开函数、全局符号：Task 11 的 `PUBLIC` 和 `__getattr__`。
- §10 指纹：Task 8 的 AST 对比。Task 2 的 NameError 变化写在 commit message，不 bump。
- 附录 A 的 150 / 57 / 10：Task 1 的 raw 计数。决定 8 的六处改写后，实施计数是 state 6、harvest 4、evidence 11、family 6。后续任务用 `HOME` 搬。
- 开工先建 `/root/timesfm-s1`。git 命令都带 `git -C /root/timesfm-s1`。没有 `git add -u`。
- `build_snapshot` 的非法 tier 测试用扁平 `{variant_id: row}`，断言 `symbol_stats["rb"]["n_tier_a_b"] == 0`。
- `rl` 整对象替换在 Task 8 改成 `install_fake_rl`，不拖到 Task 11。
- shim bootstrap 用 `_BOOT_DIR`。`HERE` 和 `FM_ROOT` 不进 shim 的模块字典。Task 3 的 `test_shim_here_follows_sup_paths` 锁住。
- Task 10 的失败对照是 `/tmp/s1-baseline.xml` 对 `/tmp/s1-task10.xml`。不写 `/tmp/s1-baseline-fails.txt`。
