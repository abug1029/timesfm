"""搜索树（spec 2026-10-05 §6.2）——enforce 档的提案树资格门。

数据来源：
- task_FM/config/search_commitments.jsonl（append-only，schema
  fm.search_commitments.v1）：树的存在性（event=accept）、成员（accept 行的
  variant_id）、终态（event=stop/promote）。写入器 append_commitment 在本
  模块（P2.3）：收割侧 _commit_search_accepts 落 accept；stop/promote 的
  触发语义在 2.4/2.7 接线，此处只锁写入器合同。
- 收割传入的裁决快照（当前协议视图，{variant_id: 裁决行}）：父节点 ok 判定、
  近失判据、预算计数。快照在调用侧已按当前协议过滤，本模块不二次过滤。

解读裁决（spec 未逐字规定处；实施解读，专家复核点）：
1. search_role_missing 兼收字段-值合同违反：root 带非空 search_parent_id；
    exploit/falsifier 缺 search_parent_id 或 tree_id（空值视同缺）。
    role 值与 id 值均不做空白归一（与 _norm_search_policy 对 " enforce" 的
    处置一致：宁拒勿静默改写）。
2. root 自带的 tree_id 字段值被收割忽略重写（spec：根提案的 tree_id 由收割
    写成）。
3. 子提案 (symbol, family) 与目标树身份不匹配 → search_tree_busy
    （该 tree_id 对这份提案而言不可用，与「tree_id 不属于任何已知树」同族）。
4. 近失判据 fail-closed：dir_acc 或 effective_min 缺失/非有限 →
    not_near_miss。不采用 known_verdicts 渲染侧的 0.52 回退——放行侧不可
    缺值放行（当前协议 v2 行实际总带 effective_min，该分支只是防御）。
5. 预算 = 树成员（accept 行 variant_id，distinct）∩ 快照 status=ok 行数；
    复测不重复计数（同一节点的再裁决不占新预算）；no_data 不占（spec §5）。
6. 守卫活态在 guard-pass 时建树/占座（spec「先处理的 root 先建树」「后到的
    同角色提案按收割处理顺序拒绝」）：guard-pass 后被下游（池/质量门/去重等）
    拒绝的提案会留下同轮幻影占位——后到同 (symbol,family) root 记 busy、
    后到同角色合法提案记 conflict。占座只认「通过树检查」的提案
    （T18：首份 parent_missing 不占座）。spec 的检查顺序（管道最前、
    first-hit）要求活态检查必须在守卫内完成，无法推迟到 selection 后。
7. promote 与 stop 同为终态（spec §6.5 停止四规则含 promoted）；
    已停止的 (symbol,family) 允许开新树（新 proposal_id → 新 tree_id）。
8. 防御：根提案计算出的 tree_id 与已停止树同名（同文件重提）→
    search_tree_closed，不得重开已探索的树。
9. commitments 坏行/撕裂行跳过并告警（append-only jsonl 容错）；文件缺失
    = 无树（首开 enforce 的状态）。行内 B/τ 与常量不符则 ValueError
    fail-loud（M3，spec §8 冻结的读侧闸）；字段缺席放行（兼容手写行）。
10. 族未解析（pool 与提案均无 family）时收割跳过守卫，交由既有
    family_unresolved 拒收——树拒绝码不覆盖非树归因。
11. 停止巡检（2.4，§6.5）：evaluate_tree_stops 只判定不落账（落账在
    supervisor _sweep_search_stops）；条件序 budget → dominated →
    family_dead first-hit（promoted 是 2.7 事件驱动落 promote 行，同为
    终态，不由巡检判定）。dominated fail-closed（停止不可逆）：se 不可算
    的节点不参与；现任 se 不可算则条件禁用；无现任时现任下界 0；严格
    小于才停；δ 平手取 se 较大者（上界更高更难停——保守方向）。今日
    裁决行尚无 se 字段 → 条件休眠，2.5 落字段后自然激活。
12. M1 重放通道（P2.3 审核）：崩溃窗口 A（accept 已落账、入队未发生）
    的 root 重放——同 proposal_id 已是未停止树成员且该成员尚无当前协议
    裁决 → 幂等放行原指派（守卫拒绝=整行丢弃：否则成员永不评估，
    幻影树作为唯一扩展树冻结整个搜索）。已裁决成员的陈旧重扫仍撞
    search_tree_busy（防每轮重扫都重新放行）；树已停止的重放撞
    search_tree_closed（不得重开已探索的树）。
"""
import hashlib
import json
import logging
import math
import os
from datetime import datetime

# spec §5/§8：B 与 τ 是 spec 规定值，不是可调参数；
# 不得在第一行 search_commitments.jsonl 写入之后更改。
BUDGET_B = 4
TAU_SD = 0.04
NEAR_MISS_FLOOR = 0.49
ROLES = ("root", "exploit", "falsifier")
COMMITMENTS_SCHEMA = "fm.search_commitments.v1"
# spec §6.5：停止原因枚举（append_commitment event=stop 的写入闸 N2）
STOP_REASONS = ("budget", "promoted", "dominated", "family_dead")
# spec §6.5-3：dominated 上/下界的单侧 95% Z 值
DOMINATED_Z = 1.645


def tree_id_for(symbol, family, proposal_id):
    """根提案的 tree_id：symbol::family::sha256(proposal_id)[:12]。

    spec §6.2「symbol 加族加根提案 proposal_id」的紧凑实现：proposal_id
    （收割相对路径）完整哈希进 id，12 hex（48-bit）与 variant_id 的截断
    宽度一致；完整 proposal_id 随 accept 行落 commitments。
    """
    digest = hashlib.sha256(str(proposal_id).encode("utf-8")).hexdigest()[:12]
    return "%s::%s::%s" % (symbol, family, digest)


def _finite(value):
    """有限 float 或 None（bool 不算数——YAML 1.1 陷阱同源防御）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class _Tree:
    __slots__ = ("tree_id", "symbol", "family", "member_vids",
                 "member_pid_vid", "accept_ts", "stop_reason")

    def __init__(self, tree_id, symbol, family, accept_ts):
        self.tree_id = tree_id
        self.symbol = symbol
        self.family = family
        self.member_vids = set()
        self.member_pid_vid = {}    # proposal_id -> vid（M1 重放通道，2.4）
        self.accept_ts = accept_ts
        self.stop_reason = ""


class TreeIndex:
    """search_commitments.jsonl 的只读索引。"""

    def __init__(self):
        self.trees = {}        # tree_id -> _Tree
        self.stopped = set()   # tree_id（stop/promote 终态）

    def unstopped(self):
        return [t for t in self.trees.values() if t.tree_id not in self.stopped]

    def unstopped_for(self, symbol, family):
        for t in self.unstopped():
            if t.symbol == symbol and t.family == family:
                return t
        return None


def _apply_record(index, rec):
    tid = str(rec.get("tree_id") or "")
    event = str(rec.get("event") or "")
    if not tid or not event:
        return
    if event == "accept":
        tree = index.trees.get(tid)
        if tree is None:
            tree = _Tree(tid, str(rec.get("symbol") or ""),
                         str(rec.get("family") or ""), str(rec.get("ts") or ""))
            index.trees[tid] = tree
        vid = str(rec.get("variant_id") or "")
        if vid:
            tree.member_vids.add(vid)
        pid = str(rec.get("proposal_id") or "")
        if pid:
            tree.member_pid_vid[pid] = vid
    elif event in ("stop", "promote"):
        index.stopped.add(tid)
        tree = index.trees.get(tid)
        if tree is not None:
            tree.stop_reason = str(rec.get("stop_reason") or event)


def load_tree_index(path):
    """读 commitments → TreeIndex。文件缺失 = 无树；坏行跳过并告警。

    行内 B/τ 与常量不符 → ValueError fail-loud（M3：spec §8 B/τ 首行
    写入后不得更改，违例是合同破坏，必须人工介入而非静默继续）；字段
    缺席放行（兼容手写行/测试夹具）。
    """
    index = TreeIndex()
    if not path or not os.path.exists(path):
        return index
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    logging.warning("search_commitments 坏行跳过 %s:%d",
                                    path, lineno)
                    continue
                if not isinstance(rec, dict) or \
                        rec.get("schema") != COMMITMENTS_SCHEMA:
                    logging.warning("search_commitments 非 %s 行跳过 %s:%d",
                                    COMMITMENTS_SCHEMA, path, lineno)
                    continue
                # M3（spec §8 冻结读侧闸）：存在性校验，不符 fail-loud
                if "B" in rec and rec.get("B") != BUDGET_B:
                    raise ValueError(
                        "search_commitments B 与常量不符（spec §8 冻结）"
                        " %s:%d: %r" % (path, lineno, rec.get("B")))
                if "tau" in rec and _finite(rec.get("tau")) != TAU_SD:
                    raise ValueError(
                        "search_commitments tau 与常量不符（spec §8 冻结）"
                        " %s:%d: %r" % (path, lineno, rec.get("tau")))
                _apply_record(index, rec)
    except OSError as exc:
        logging.warning("search_commitments 读取失败（按无树处理）: %s", exc)
        return TreeIndex()
    return index


class SearchGuard:
    """enforce 档树资格守卫。

    load 时快照：扩展树（未停止树中 event=accept 最早，平手按 tree_id
    字典序）与根轮次（无未停止树）。check 按 spec §6.2 表序 first-hit；
    guard-pass 即活态建树/占座（见模块 docstring 第 6 条）。
    """

    def __init__(self, index, snapshot):
        self.index = index
        self.snapshot = snapshot if isinstance(snapshot, dict) else {}
        unstopped = self.index.unstopped()
        self.root_round = not unstopped
        if unstopped:
            self.expansion_tree = min(
                (t.tree_id for t in unstopped),
                key=lambda tid: (self.index.trees[tid].accept_ts or "", tid))
        else:
            self.expansion_tree = None
        self._budget = {t.tree_id: self._count_budget(t) for t in unstopped}
        self._round_trees = {}       # (symbol, family) -> tree_id（本轮 root 建树）
        self._claimed_roles = set()  # 本轮扩展树已占角色

    @classmethod
    def load(cls, commitments_path, snapshot):
        return cls(load_tree_index(commitments_path), snapshot)

    def _count_budget(self, tree):
        return count_ok_members(tree, self.snapshot)

    def _ok_row(self, vid):
        row = self.snapshot.get(vid)
        if isinstance(row, dict) and row.get("status", "ok") == "ok":
            return row
        return None

    def check(self, prop, symbol, family, cov, proposal_id):
        """树资格检查（spec §6.2 表序，first-hit）。

        Returns: (reason | None, info | None)
          reason 为 None = 放行；info 携带收割落账三字段
          （root 的 search_tree_id 为收割指派值）。
        """
        role = prop.get("search_role")
        parent_id = str(prop.get("search_parent_id") or "")
        tree_id_field = str(prop.get("tree_id") or "")
        # 1 search_role_missing（含字段-值合同违反）
        if role not in ROLES:
            return "search_role_missing", None
        if role == "root":
            if parent_id:
                return "search_role_missing", None
            assigned = tree_id_for(symbol, family, proposal_id)
            # 2 search_tree_closed（防御：同 proposal_id 不得重开已停止树）
            if assigned in self.index.stopped:
                return "search_tree_closed", None
            existing = self.index.unstopped_for(symbol, family)
            # M1 重放通道（2.4，P2.3 审核）：崩溃窗口 A（accept 已落账、
            # 入队未发生）的 root 重放——同 proposal_id 已是本树成员且该
            # 成员尚无当前协议裁决 → 幂等放行原指派（守卫拒绝=整行丢弃：
            # 否则成员永不评估，幻影树作为唯一扩展树冻结整个搜索）。
            # 已裁决成员的陈旧重扫仍撞 busy（防每轮重扫都重新放行）。
            # 不占本轮建树座。
            if existing is not None:
                pid = str(proposal_id)
                if pid in existing.member_pid_vid:
                    mvid = existing.member_pid_vid.get(pid) or ""
                    mrow = self.snapshot.get(mvid) if mvid else None
                    if not mvid or not isinstance(mrow, dict):
                        return None, {"search_role": "root",
                                      "search_tree_id": existing.tree_id,
                                      "search_parent_id": ""}
            # 4 search_tree_busy（同轮先处理的 root 已建树；
            #    或该 (symbol, family) 已有未停止树）
            if (symbol, family) in self._round_trees:
                return "search_tree_busy", None
            if existing is not None:
                return "search_tree_busy", None
            # 8 search_root_while_tree_active（收割开始时有未停止树）
            if not self.root_round:
                return "search_root_while_tree_active", None
            # 放行：本轮建树（内存态；accept 落账在 2.3 selection 时）
            self._round_trees[(symbol, family)] = assigned
            return None, {"search_role": "root", "search_tree_id": assigned,
                          "search_parent_id": ""}
        # ── 子角色（exploit / falsifier）──
        if not parent_id or not tree_id_field:
            return "search_role_missing", None
        # 2 search_tree_closed（含子提案指向已停止的树）
        if tree_id_field in self.index.stopped:
            return "search_tree_closed", None
        tree = self.index.trees.get(tree_id_field)
        # 3 search_budget_exhausted（树已知才有预算；未知树在 4 号原因记 busy）
        if tree is not None and \
                self._budget.get(tree_id_field, 0) >= BUDGET_B:
            return "search_budget_exhausted", None
        # 4 search_tree_busy
        if tree is None:
            return "search_tree_busy", None          # tree_id 不属于任何已知树
        if tree.symbol != symbol or tree.family != family:
            return "search_tree_busy", None          # 树身份与提案不匹配
        if self.expansion_tree is not None and tree_id_field != self.expansion_tree:
            return "search_tree_busy", None          # 另一棵未停止非扩展树
        # 5 search_parent_missing（父 = 本树成员 且 当前协议 status=ok 裁决）
        if parent_id not in tree.member_vids:
            return "search_parent_missing", None
        prow = self._ok_row(parent_id)
        if prow is None:
            return "search_parent_missing", None
        # 6 search_parent_not_near_miss（exploit 专用；fail-closed）
        if role == "exploit":
            da = _finite(prow.get("dir_acc"))
            emin = _finite(prow.get("effective_min"))
            if da is None or emin is None or \
                    not (NEAR_MISS_FLOOR <= da < emin):
                return "search_parent_not_near_miss", None
        # 7 search_falsifier_same_cov（falsifier 专用）
        if role == "falsifier":
            if str(prow.get("cov_override") or "") == cov:
                return "search_falsifier_same_cov", None
        # 9 search_role_conflict（扩展树同角色占座；只认通过树检查的提案）
        if role in self._claimed_roles:
            return "search_role_conflict", None
        self._claimed_roles.add(role)
        return None, {"search_role": role, "search_tree_id": tree_id_field,
                      "search_parent_id": parent_id}


def count_ok_members(tree, snapshot):
    """树成员中当前协议 status=ok 裁决数（§6.5-1 预算计数；status 缺省按 ok）。

    守卫 _count_budget 与停止巡检 evaluate_tree_stops 共用同一口径。
    """
    n = 0
    for vid in tree.member_vids:
        row = snapshot.get(vid) if isinstance(snapshot, dict) else None
        if isinstance(row, dict) and row.get("status", "ok") == "ok":
            n += 1
    return n


def _delta_se(row):
    """(δ, se)（§5 δ=dir_acc−baseline_dir_acc；§6.5-3 se）。

    status=ok 且 dir_acc/baseline_dir_acc 均有限才可算 δ；se 单独返回
    （可为 None=不可算）。任一前提不满足 δ 为 None（节点不参与比较）。
    """
    if not isinstance(row, dict) or row.get("status", "ok") != "ok":
        return (None, None)
    da = _finite(row.get("dir_acc"))
    base = _finite(row.get("baseline_dir_acc"))
    if da is None or base is None:
        return (None, None)
    return (da - base, _finite(row.get("se")))


def _incumbent_lower_bound(snapshot, symbol):
    """现任下界（§6.5-3；现任定义 §5：同品种当前协议 ok∧gate_pass δ 最大者）。

    无现任 → 0.0；现任 se 不可算 → None（条件禁用：停止不可逆，
    fail-closed 宁不停勿错停）。现任 δ 平手取先见者（快照序=jsonl 序，
    病态情形，不影响正确性——各候选同为最大 δ）。
    """
    best = None   # (δ, se)
    for row in (snapshot or {}).values():
        if not isinstance(row, dict) or row.get("symbol") != symbol:
            continue
        if row.get("status", "ok") != "ok" or not row.get("gate_pass"):
            continue
        d, se = _delta_se(row)
        if d is None:
            continue
        if best is None or d > best[0]:
            best = (d, se)
    if best is None:
        return 0.0
    if best[1] is None:
        return None
    return best[0] - DOMINATED_Z * best[1]


def evaluate_tree_stops(index, snapshot, dead_families):
    """对未停止树按 §6.5 列表序求 first-hit 停止原因（只判定不落账）。

    Returns: [(tree_id, stop_reason), ...]——调用侧（supervisor
    _sweep_search_stops）负责落 stop 行与决策日志。

    条件序（spec §6.5）：
      1. budget   成员 ok 裁决数 ≥ B（count_ok_members 同守卫口径）；
      2. promoted §6.6 晋升——2.7 事件驱动落 promote 行（同为终态，
         本函数不判定）；
      3. dominated se 可算节点中 δ 最大者的上界 δ+Z·se 严格小于
         现任下界（_incumbent_lower_bound；无现任 → 0；现任 se 不可算
         → 条件禁用）。δ 平手取 se 较大者——上界更高更难停，保守方向；
      4. family_dead 树族 ∈ dead_families（supervisor 传
         _dead_families(snapshot)，判据照旧 min_ok=4/gate_pass）。

    全部条件 fail-closed：数据不齐不停止（停止不可逆）。
    """
    dead = dead_families if isinstance(dead_families, (set, frozenset)) \
        else set()
    stops = []
    for tree in index.unstopped():
        reason = None
        if count_ok_members(tree, snapshot) >= BUDGET_B:
            reason = "budget"
        else:
            lb = _incumbent_lower_bound(snapshot, tree.symbol)
            if lb is not None:
                cands = []
                for vid in tree.member_vids:
                    d, se = _delta_se((snapshot or {}).get(vid))
                    if d is not None and se is not None:
                        cands.append((d, se, vid))
                if cands:
                    d, se, _vid = max(cands)
                    if d + DOMINATED_Z * se < lb:
                        reason = "dominated"
        if reason is None and tree.family in dead:
            reason = "family_dead"
        if reason is not None:
            stops.append((tree.tree_id, reason))
    return stops


def render_open_trees(index, snapshot):
    """known_verdicts「未停止的树」（spec §6.8）。没有未停止的树时写「无」。"""
    lines = ["## 未停止的树"]
    trees = index.unstopped()
    if not trees:
        lines.append("无")
        lines.append("")
        return lines
    extension = min(
        (tree.tree_id for tree in trees),
        key=lambda tid: (index.trees[tid].accept_ts or "", tid))
    snap = snapshot if isinstance(snapshot, dict) else {}
    for tree in sorted(trees, key=lambda item: item.tree_id):
        used = count_ok_members(tree, snap)
        lines.append(
            "- %s symbol=%s family=%s used=%d budget=%d extension=%s" % (
                tree.tree_id, tree.symbol, tree.family, used, BUDGET_B,
                "yes" if tree.tree_id == extension else "no"))
        if not tree.member_vids:
            lines.append("  - parent none")
            continue
        for vid in sorted(tree.member_vids):
            row = snap.get(vid)
            near = "no"
            if isinstance(row, dict) and row.get("status", "ok") == "ok":
                accuracy = _finite(row.get("dir_acc"))
                floor = _finite(row.get("effective_min"))
                if (accuracy is not None and floor is not None
                        and NEAR_MISS_FLOOR <= accuracy < floor):
                    near = "yes"
            lines.append("  - parent %s near_miss=%s" % (vid, near))
    lines.append("本轮两份提案应为本轮扩展树的 exploit 与 falsifier。")
    lines.append("")
    return lines


def append_commitment(path, event, tree_id, symbol="", family="",
                      proposal_id="", variant_id="", search_role="",
                      search_parent_id="", stop_reason=None,
                      delta_post=None, n_required=None):
    """向 search_commitments.jsonl 追加一条事件行（append-only，spec §6.7）。

    - event ∈ {accept, stop, promote} 且 tree_id 非空，否则 ValueError
      （fail-loud；校验先于建目录/开文件，不留半行）。
    - 每行携带 schema/ts/event/B/tau（§8：B/τ 在首行写入后不得更改）。
    - stop 行必须带合法 stop_reason ∈ {budget, promoted, dominated,
      family_dead}（§6.5 枚举，N2 写入闸；缺省/非法 → ValueError）；
      promote 行可带 delta_post/n_required（§6.3 数例；2.7 接线）。
      条件字段只在传值时写入——accept 行不携带停止/晋升字段。
    - 时间戳与收割 _now_iso 同源（datetime.now().isoformat()，本地时区）。
    - 读侧容错在 load_tree_index（坏行跳过）；本函数不做读回验。
    """
    if event not in ("accept", "stop", "promote"):
        raise ValueError("event 必须是 accept/stop/promote: %r" % (event,))
    if not tree_id:
        raise ValueError("tree_id 不能为空")
    # N2（§6.5 枚举写入闸）：stop 行必须携带合法停止原因
    if event == "stop" and stop_reason not in STOP_REASONS:
        raise ValueError("stop 行必须带合法 stop_reason（§6.5: %s）: %r"
                         % ("/".join(STOP_REASONS), stop_reason))
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
    if stop_reason is not None:
        rec["stop_reason"] = str(stop_reason)
    if delta_post is not None:
        rec["delta_post"] = delta_post
    if n_required is not None:
        rec["n_required"] = int(n_required)
    parent_dir = os.path.dirname(str(path or ""))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
