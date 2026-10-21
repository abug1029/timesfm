# Phase 3 实施计划：提案版本控制 + 关系追踪

> **上位 Spec**: `/home/abug/timesfm/docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md` (§5 Phase 3)
> **前置**: Phase 1（schema v2 接受、status 写入、rejected_proposals）和 Phase 2（跨 Run 反馈）已完成
> **分支**: `feat/proposal-version-tracking`
> **文件变更**: ~5 个文件 + 1 个新测试

---

## 全局约束

- 侧车锁模式：所有 jsonl 写操作用 `fcntl.flock`（对齐 `proposal_status.py`）
- Append-only JSONL：禁止覆盖/截断
- 最小改动：不触碰已有稳定的 dedup/质量门/树守卫逻辑
- 测试先行：每个 Task 先写红灯测试，再实现

---

## Task P3.2 + P3.3：sup_harvest.py dedup 增加 proposal_id+version 维度 + version_dup 拒绝码

**Spec**: §3.5.3「收割侧 dedup 检查顺序：先 variant_id，再 proposal_id+version」

**文件**:
- `scripts/sup_harvest.py`（约 line 730-740，vid dedup 之后）

**接口变更**:
- `_reject("version_dup")`：新增拒绝码，语义 = 同一 proposal_id + version 已处理过
- `_has_proposal_version_status(status_path, proposal_id, version) -> bool`：新 helper

**实现方案**:

```python
# sup_harvest.py 新增 helper（放在 _cross_run_repeat_counts 之后）

def _has_proposal_version_status(status_path, proposal_id, version, statuses=None):
    """检查 proposal_id+version 是否已在 proposal_status.jsonl 中有记录。

    statuses 可选过滤（如 {"rejected", "queued", "verdicted"}）；
    None = 任意状态都算重复。
    """
    if not os.path.exists(status_path):
        return False
    target = (proposal_id, version)
    for raw in open(status_path, encoding="utf-8"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if (r.get("proposal_id"), r.get("version")) == target:
            if statuses is None or r.get("status") in statuses:
                return True
    return False
```

**插入位置**: 在现有 `vid` dedup 之后（line ~736），PR-B6 质量门之前：

```python
# 现有代码（不动）:
if vid in dead or vid in existing or vid in passing_ids or vid in seen_vids:
    _reject("dedup"); continue
seen_vids.add(vid)

# ── P3.2: proposal_id+version 去重（spec §3.5.3）──
# 同一 proposal_id+version 已处理过 → version_dup 拒绝；
# 更高 version 允许（视为新提案）。
if _has_proposal_version_status(
        sup_paths.PROPOSAL_STATUS_PATH, _proposal_id, _version):
    _reject("version_dup"); continue
```

**为什么在 vid dedup 之后**: spec §3.5.3 明确顺序——先实验身份（variant_id）去重，再提案版本去重。同一提案不同 version 会产生相同 variant_id（数据不变时），vid dedup 先拦；同一 version 重提走 version_dup。

**统计注册**: `_reject` 自动计入 `stats["reject_reasons"]["version_dup"]`（无需额外改动）。

---

## Task P3.1：prompt_base.jinja2 引入 version 和 version_note 字段说明

**Spec**: §4.1 Proposal Schema v2 + §3.5.3 peer 指引

**文件**:
- `task_FM/prompt_base.jinja2`（约 line 80-100，搜索树字段节之后）

**变更**: 在搜索树字段说明节之后，新增 version 指引块：

```
11. **版本字段**（v2 schema）：提案 JSON 可携带 `version`（整数，默认 1）和 `version_note`（字符串，可选）。
    - 首次提案：version=1（可不写 version 字段）。
    - 同一 proposal_id 被拒后重提且改了内容：version 递增，version_note 描述改了什么。
    - 原样重提（无变化）：version 不变。
    - version_note 为空的重提会记录警告日志；建议始终填写。
    - 高 version 的提案视为新提案，允许入队。

```json
{
  "schema": "fm.hypothesis_proposal.v2",
  "proposal_id": "m_crack_spread_slope",
  "version": 2,
  "version_note": "修正了 kill_condition 阈值，增加压榨利润相关性论证"
}
```

**行预算**: 约 10 行，不挤占已有内容。

---

## Task P3.4：sup_evidence.py 版本链构建逻辑

**Spec**: §3.3.2 节 3「版本比较（单个提案）」+ §3.3.3 行预算 ≤ 10 行

**文件**:
- `scripts/sup_evidence.py`（约 line 298-320，`_version_comparison_lines` 函数增强）

**当前状态**: `_version_comparison_lines(status_path, max_lines=10)` 已存在，但只列出 proposal_id 和 version 集合，不含裁决信息。

**变更**: 增强 `_version_comparison_lines`，使其从 proposal_status.jsonl + aligned_verdicts.jsonl 做 join，输出带裁决状态的版本比较行：

```python
def _version_comparison_lines(status_path, max_lines=10):
    """Build version comparison view for multi-version proposals (P3.4 enhanced).

    从 proposal_status.jsonl 聚合同一 proposal_id 的多个 version，
    join verdict 的 gate_pass/fdr_pass，输出格式：
      m_crack_spread_slope: v1 rejected(quality_below_threshold) → v2 queued → v3 verdicted(gate=True,fdr=True)
    """
    if not os.path.exists(status_path):
        return []
    by_prop = {}  # proposal_id -> [(version, status, reject_reason, variant_id), ...]
    for raw in open(status_path, encoding="utf-8"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            continue
        pid = r.get("proposal_id")
        if not pid:
            continue
        ver = r.get("version", "?")
        status = r.get("status", "?")
        rr = r.get("reject_reason")
        vid = r.get("variant_id")
        by_prop.setdefault(pid, []).append((ver, status, rr, vid))

    # 获取 verdict 信息（variant_id → gate_pass/fdr_pass）
    verdict_path = sup_paths.REGISTRY  # aligned_verdicts.jsonl
    verdict_map = {}
    if os.path.exists(verdict_path):
        for raw in open(verdict_path, encoding="utf-8"):
            raw = raw.strip()
            if not raw:
                continue
            try:
                v = json.loads(raw)
                vid = v.get("variant_id")
                if vid:
                    verdict_map[vid] = v
            except json.JSONDecodeError:
                continue

    out = []
    for pid, entries in sorted(by_prop.items()):
        # 去重：同一 version+status 只保留第一条
        seen = set()
        unique = []
        for ver, status, rr, vid in entries:
            key = (ver, status)
            if key not in seen:
                seen.add(key)
                unique.append((ver, status, rr, vid))
        if len(unique) < 2:
            continue  # 单 version 不显示比较
        # 构建版本链字符串
        parts = []
        for ver, status, rr, vid in unique[:5]:  # 最多 5 个 version
            tag = status
            if status == "rejected" and rr:
                tag = "rejected(%s)" % rr
            elif status == "verdicted" and vid:
                v = verdict_map.get(vid, {})
                gp = v.get("gate_pass")
                fp = v.get("fdr_pass")
                tag = "verdicted(gate=%s,fdr=%s)" % (gp, fp)
            parts.append("v%s %s" % (ver, tag))
        out.append("%s: %s" % (pid, " → ".join(parts)))
        if len(out) >= max_lines:
            break
    return out
```

**物化集成**: `materialize_known_verdicts` 已调用 `_version_comparison_lines`（line ~518），无需改动调用点。

---

## Task P3.5：search_trees.py 增强 _Tree 类，支持 version 感知的 tree_id 派生

**Spec**: §3.5.1 search_policy 分支 + §3.5.2 提案演化关系 + §7.6 tree_id_for 实现说明

**文件**:
- `scripts/search_trees.py`（约 line 95-120 `_Tree` 类 + `tree_id_for` 函数）

**变更**:

### 1. `_Tree` 类增加 version 追踪字段

```python
class _Tree:
    __slots__ = ("tree_id", "symbol", "family", "member_vids",
                 "member_pid_vid", "member_pid_ver",  # 新增 version 映射
                 "accept_ts", "stop_reason")

    def __init__(self, tree_id, symbol, family, accept_ts):
        self.tree_id = tree_id
        self.symbol = symbol
        self.family = family
        self.member_vids = set()
        self.member_pid_vid = {}     # proposal_id -> vid
        self.member_pid_ver = {}     # proposal_id -> version（P3.5 新增）
        self.accept_ts = accept_ts
        self.stop_reason = ""
```

### 2. `_apply_record` 同步读取 version

```python
def _apply_record(index, rec):
    # ... 现有 accept 逻辑不变 ...
    if event == "accept":
        # ... 现有代码 ...
        pid = str(rec.get("proposal_id") or "")
        if pid:
            tree.member_pid_vid[pid] = vid
            ver = rec.get("version")
            if ver is not None:
                tree.member_pid_ver[pid] = int(ver)
    # ... 其余不变 ...
```

### 3. `append_commitment` 增加 version 参数

```python
def append_commitment(path, event, tree_id, symbol="", family="",
                      proposal_id="", variant_id="", search_role="",
                      search_parent_id="", stop_reason=None,
                      delta_post=None, n_required=None,
                      version=None):  # P3.5 新增
    # ... 现有校验不变 ...
    rec = {"schema": COMMITMENTS_SCHEMA,
           "ts": datetime.now().isoformat(),
           "event": event,
           "tree_id": str(tree_id),
           "symbol": str(symbol or ""),
           "family": str(family or ""),
           "proposal_id": str(proposal_id or ""),
           "variant_id": str(variant_id or ""),
           "search_role": str(search_role or ""),
           "search_parent_id": str(search_parent_id or ""),
           "B": BUDGET_B, "tau": TAU_SD}
    if version is not None:
        rec["version"] = int(version)  # P3.5：version 有值才写入
    # ... 其余写入逻辑不变 ...
```

### 4. `tree_id_for` 不变（已经是 proposal_id 输入）

`tree_id_for(symbol, family, proposal_id)` 的签名和实现不变——它已经以 proposal_id 为输入。off/shadow/enforce 分支在调用侧（sup_harvest.py）处理。

### 5. `render_open_trees` 增加 version 标注

```python
def render_open_trees(index, snapshot):
    # ... 现有逻辑不变，直到 member_vids 遍历 ...
    for vid in sorted(tree.member_vids):
        row = snap.get(vid)
        # 查找该 vid 对应的 version（通过 member_pid_vid 反查）
        ver = "?"
        for pid, mvid in tree.member_pid_vid.items():
            if mvid == vid:
                ver = tree.member_pid_ver.get(pid, "?")
                break
        near = "no"
        # ... 现有 near_miss 逻辑不变 ...
        lines.append("  - parent %s ver=%s near_miss=%s" % (vid, ver, near))
```

---

## Task P3.6：新测试 test_proposal_versioning.py

**文件**: `tests/test_proposal_versioning.py`（新建）

**测试用例**:

| # | 测试名 | 验证内容 |
|---|--------|---------|
| 1 | `test_version_dup_rejected` | 同一 proposal_id+version 重提被 version_dup 拒绝 |
| 2 | `test_higher_version_allowed` | 同一 proposal_id 的更高 version 可入队 |
| 3 | `test_version_dup_after_variant_id_dedup` | dedup 顺序：vid 先拦，version_dup 后拦 |
| 4 | `test_v2_with_version_note` | v2 schema + version_note 正常入队 |
| 5 | `test_has_proposal_version_status` | `_has_proposal_version_status` 正确读取 status 文件 |
| 6 | `test_tree_member_has_version` | `_Tree.member_pid_ver` 正确存储 version |
| 7 | `test_append_commitment_carries_version` | `append_commitment` 写入 version 字段 |
| 8 | `test_version_comparison_lines` | `_version_comparison_lines` 输出多 version 链 |

**测试骨架**:

```python
# tests/test_proposal_versioning.py
"""Phase 3: 提案版本控制 + 关系追踪测试。"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from test_harvest_status_integration import (
    _make_minimal_harvest_fixtures,
    _patch_harvest_deps,
)


def test_version_dup_rejected():
    """同一 proposal_id+version 重提被 version_dup 拒绝（P3.2/P3.3）。"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        rf = os.path.join(tmpdir, "rejected_proposals.jsonl")
        _make_minimal_harvest_fixtures(tmpdir, proposal_id="dup_test", version=1)

        # 预写一条 status 记录，模拟该 proposal_id+version 已处理过
        with open(sf, "a") as f:
            f.write(json.dumps({
                "proposal_id": "dup_test", "version": 1,
                "status": "rejected", "reject_reason": "quality_below_threshold",
                "ts": "2026-10-18T00:00:00", "run_id": "prev_run"
            }) + "\n")

        with patch("sup_harvest.sup_paths") as mock_sp, \
             patch("sup_harvest.sup_evidence") as mock_ev, \
             patch("sup_harvest.sup_lifecycle") as mock_lc, \
             patch("sup_harvest.st") as mock_st, \
             patch("sup_harvest.ef") as mock_ef:
            mock_sp.PROPOSAL_STATUS_PATH = sf
            mock_sp.REJECTED_PROPOSALS_PATH = rf
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10
            )

            assert len(cands) == 0, "version_dup 提案不应入队"
            assert "version_dup" in stats["reject_reasons"], \
                "应有 version_dup 拒绝记录"


def test_higher_version_allowed():
    """同一 proposal_id 的更高 version 可入队（§3.5.3）。"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        _make_minimal_harvest_fixtures(tmpdir,
            schema="fm.hypothesis_proposal.v2",
            proposal_id="ver_test", version=2)

        # 预写 v1 已被拒
        with open(sf, "a") as f:
            f.write(json.dumps({
                "proposal_id": "ver_test", "version": 1,
                "status": "rejected", "reject_reason": "quality_below_threshold",
                "ts": "2026-10-18T00:00:00", "run_id": "prev_run"
            }) + "\n")

        with patch("sup_harvest.sup_paths") as mock_sp, \
             patch("sup_harvest.sup_evidence") as mock_ev, \
             patch("sup_harvest.sup_lifecycle") as mock_lc, \
             patch("sup_harvest.st") as mock_st, \
             patch("sup_harvest.ef") as mock_ef:
            mock_sp.PROPOSAL_STATUS_PATH = sf
            mock_sp.REJECTED_PROPOSALS_PATH = os.path.join(tmpdir, "rejected.jsonl")
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10
            )

            assert len(cands) >= 1
            assert cands[0]["version"] == 2
            assert "version_dup" not in stats["reject_reasons"]


def test_version_comparison_lines():
    """_version_comparison_lines 输出多 version 链（P3.4）。"""
    from sup_evidence import _version_comparison_lines

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        # 写入 3 个 version
        records = [
            {"proposal_id": "test_prop", "version": 1, "status": "rejected",
             "reject_reason": "quality_below_threshold", "variant_id": "vid1"},
            {"proposal_id": "test_prop", "version": 2, "status": "queued",
             "variant_id": "vid2"},
            {"proposal_id": "test_prop", "version": 3, "status": "verdicted",
             "variant_id": "vid3"},
        ]
        with open(sf, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        lines = _version_comparison_lines(sf)
        assert len(lines) == 1
        assert "test_prop" in lines[0]
        assert "v1" in lines[0]
        assert "v2" in lines[0]
        assert "v3" in lines[0]


def test_tree_member_has_version():
    """_Tree.member_pid_ver 正确存储 version（P3.5）。"""
    from search_trees import _Tree

    t = _Tree("test::tree::abc123", "m", "momentum", "2026-10-18T00:00:00")
    t.member_pid_vid["run_001/.../p_test.json"] = "m_momentum_fp123"
    t.member_pid_ver["run_001/.../p_test.json"] = 2

    assert t.member_pid_ver["run_001/.../p_test.json"] == 2
```

---

## 实施顺序

1. **P3.6**（测试先行）：创建 `test_proposal_versioning.py`，跑红灯
2. **P3.2 + P3.3**：`sup_harvest.py` 增加 `_has_proposal_version_status` + version_dup 检查 → 绿灯
3. **P3.4**：增强 `sup_evidence.py` `_version_comparison_lines` → 绿灯
4. **P3.5**：`search_trees.py` 增强 `_Tree` + `append_commitment` + `render_open_trees` → 绿灯
5. **P3.1**：`prompt_base.jinja2` 增加 version 指引 → 无测试要求（文档变更）

---

## 验收标准（对齐 spec §5 Phase 3）

- [ ] 同一 proposal_id 的 v2 可以入队（test_higher_version_allowed）
- [ ] 同一 proposal_id + version 重提被 version_dup 拒绝（test_version_dup_rejected）
- [ ] dedup 顺序：variant_id 先于 proposal_id+version（test_version_dup_after_variant_id_dedup）
- [ ] 搜索树 `_Tree` 携带 version 信息（test_tree_member_has_version）
- [ ] `append_commitment` 写入 version 字段（test_append_commitment_carries_version）
- [ ] `_version_comparison_lines` 输出多 version 链（test_version_comparison_lines）
- [ ] `lsp_diagnostics` 零错误
- [ ] 现有测试全绿（回归）

---

## 不做的事（Spec §7.5 重申）

- 不修改质量门/树守卫阈值
- 不修改 variant_id 生成规则
- 不修改 aligned_verdicts.jsonl schema
- 不强制 peer 填 search_parent_id/tree_id（off/shadow 模式）
