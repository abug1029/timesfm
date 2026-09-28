#!/usr/bin/env python3
"""scripts/recompute_dir_acc.py -- 历史 verdict 的 dir_acc 主口径重算

T3 验收 #4/#5：把历史 verdict 的 `dir_acc` 从旧口径（全点，零变动算错）
重算为 PR-B4 主口径（**剔零变动**，spec W6.5①），结果写入 `dir_acc_v2`。

## 三条硬约束

1. **不覆盖原 `dir_acc`**。旧值原样保留 —— 它是历史证据，改了就无法追溯
   口径变更的影响面（T3 风险表明确要求「先 dry-run 对照，量化影响面」）。
2. **幂等**。重复运行产生逐字节相同的输出。已重算且结论未变的记录跳过写入。
3. **Fail-visible**。拿不到证据就**不写值**，写状态。见下。

## 为什么「拿不到证据」是常态（本轮实测）

复审假定 checkpoint 能唯一标识它那次 run。**实测不成立**，三类断裂：

- **`checkpoint_drift`**：checkpoint 是 `mode="a"` **追加**的
  （`monthly_backtest.py` L1116），而 `eval_indices` 是
  `range(total - EVAL_WINDOW_BARS, total - HORIZON + 1, STEP)` 的**后缀窗口**
  （L293-295）。数据增长后重跑 → 新窗口接在旧窗口之后 → 文件里出现
  **多段 run**。实测 `i_oi.jsonl`：行 0-394 步长 24（idx 480→9960），
  行 395 **倒退**到 idx 8798，行 396-934 步长 2/4。文件序**非 idx 单调**。
  故「取最后 n 行」是错的。
- **`checkpoint_mismatch`**：数量对上了，但按任何一种口径算出的 dir_acc
  都对不上 verdict 里记的值。实测 10 条如此。
- **文件互相覆盖**：实测 7 组 checkpoint **逐字节相同**（md5 一致）却属于
  不同协变量，例如 `m_oi` / `m_calendar_cyclical` / `m_pca_momentum` /
  `m_nvi` 四者 md5 全为 `e6e0be1f…`（228742 字节）。即 checkpoint 已
  **不再能标识它的 run**。

对这三类，脚本**拒绝写 `dir_acc_v2`** —— 编一个数出来比不写更糟：
它会长得像权威结论，而下游（DM 检验、门限判定）会拿它当真。

## 判据

对每条 verdict 取 checkpoint 的非错误点，算两种口径：

    m_all  = mean(dir_ok)                    # 旧口径：全点
    m_act  = mean(dir_ok[~zero_move])        # 新口径：剔零变动
    zero_move = |real_end - base| < 1e-8     # 与 evaluation_metrics.py L419 同

- `round(m_act,3) == dir_acc` → 该 verdict 已是新口径 → `ok_confirmed`
- `round(m_all,3) == dir_acc` → 旧口径，本次才转新 → `ok_recomputed`
- 两者都不是 → `checkpoint_mismatch`（不写值）

## 用法

    .venv/bin/python scripts/recompute_dir_acc.py                 # dry-run，只报告
    .venv/bin/python scripts/recompute_dir_acc.py --apply         # 原子写入 + 备份
    .venv/bin/python scripts/recompute_dir_acc.py --apply --json report.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, FM_ROOT)

DEFAULT_REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")

# 与 cascade/evaluation_metrics.py:419 的 eps 一致。改这里必须同步改那边，
# 否则重算值与生产值会在边界点上分叉。
ZERO_MOVE_EPS = 1e-8

# 重算写入的字段。dir_acc_v2 是主产出；分母四项是 W6.5① 要求的「分母全套」，
# 历史 verdict 缺它们（审计 N1），重算时一并补齐。
RECOMPUTE_FIELDS = (
    "dir_acc_v2",
    "recompute_status",
    "recompute_n_points",
    "n_dir_total",
    "n_dir_active",
    "n_zero_move",
    "n_zero_ratio",
)

STATUS_DOC = {
    "ok_recomputed": "旧口径 → 新口径，dir_acc_v2 != dir_acc",
    "ok_confirmed": "已是新口径，dir_acc_v2 == dir_acc（口径已对，仅补分母）",
    "ok_noop_no_zero_move": "无零变动点，两口径等价",
    "checkpoint_missing": "checkpoint 文件不存在，无证据",
    "checkpoint_drift": "checkpoint 点数 != verdict.n，文件含多段 run 或已被覆盖",
    "checkpoint_mismatch": "点数对但 dir_acc 对不上任何一种口径，文件与 verdict 不同源",
    "checkpoint_unreadable": "checkpoint 存在但无可用点（全 error 行或解析失败）",
}
UNRESOLVED = {
    "checkpoint_missing", "checkpoint_drift",
    "checkpoint_mismatch", "checkpoint_unreadable",
}


def load_ok_points(path: str):
    """读 checkpoint，返回非 error 点。与 summarize() 的 ok 过滤同构。"""
    pts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in rec:
                continue
            # 旧格式残缺行无法重建 delta_real，剔除（与 resume 的合并条件一致）
            if "delta_real" not in rec or "base" not in rec or "dir_ok" not in rec:
                continue
            pts.append(rec)
    return pts


def compute_calibers(pts):
    """返回 (m_all, m_act, n_total, n_active, n_zero, zero_ratio)。"""
    n_total = len(pts)
    n_zero = 0
    hit_all = 0
    hit_act = 0
    for p in pts:
        d_real = float(p["real_end"]) - float(p["base"])
        ok = bool(p["dir_ok"])
        hit_all += int(ok)
        if abs(d_real) < ZERO_MOVE_EPS:
            n_zero += 1
        else:
            hit_act += int(ok)
    n_active = n_total - n_zero
    m_all = (hit_all / n_total) if n_total else 0.0
    m_act = (hit_act / n_active) if n_active else 0.0
    zero_ratio = (n_zero / n_total) if n_total else 0.0
    return m_all, m_act, n_total, n_active, n_zero, zero_ratio


def classify(v, registry_dir=None):
    """判定单条 verdict 的重算结论。

    返回 (status, payload)。payload 为 None 表示**不写值**。
    """
    cp = v.get("checkpoint_path")
    if not cp:
        return "checkpoint_missing", None
    if not os.path.isabs(cp):
        cp = os.path.join(FM_ROOT, cp)
    if not os.path.exists(cp):
        return "checkpoint_missing", None

    try:
        pts = load_ok_points(cp)
    except OSError:
        return "checkpoint_unreadable", None
    if not pts:
        return "checkpoint_unreadable", None

    m_all, m_act, n_total, n_active, n_zero, zero_ratio = compute_calibers(pts)

    # 证据闸门 1：点数必须与 verdict 一致。
    # 不一致说明 checkpoint 含多段 run 或已被别的 run 覆盖 —— 无从知道
    # verdict 当时用的是哪个子集，故不猜。
    if n_total != v.get("n"):
        return "checkpoint_drift", None

    recorded = v.get("dir_acc")
    if recorded is None:
        return "checkpoint_mismatch", None

    payload = {
        "recompute_n_points": n_total,
        "n_dir_total": n_total,
        "n_dir_active": n_active,
        "n_zero_move": n_zero,
        "n_zero_ratio": round(zero_ratio, 4),
    }

    # 证据闸门 2：算出的值必须能复现 verdict 里记的 dir_acc。
    # 复现不了 → 这份 checkpoint 不是那条 verdict 的来源，不写值。
    r_all = round(m_all, 3)
    r_act = round(m_act, 3)
    if r_act == recorded:
        if r_all == recorded:
            payload["dir_acc_v2"] = r_act
            payload["recompute_status"] = "ok_noop_no_zero_move"
            return "ok_noop_no_zero_move", payload
        payload["dir_acc_v2"] = r_act
        payload["recompute_status"] = "ok_confirmed"
        return "ok_confirmed", payload
    if r_all == recorded:
        payload["dir_acc_v2"] = r_act
        payload["recompute_status"] = "ok_recomputed"
        return "ok_recomputed", payload
    return "checkpoint_mismatch", None


def needs_write(v, payload):
    """幂等判据：payload 里每个字段都已存在且相等 → 无需写。"""
    if payload is None:
        # 未解决的记录也要落状态，否则「未重算」是静默的
        return v.get("recompute_status") is None
    for k, want in payload.items():
        if v.get(k) != want:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    ap.add_argument("--apply", action="store_true",
                    help="原子写入（默认 dry-run，只报告）")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="把逐条结论写到 JSON")
    args = ap.parse_args()

    if not os.path.exists(args.registry):
        print("registry 不存在: %s" % args.registry, file=sys.stderr)
        return 1

    records = []
    with open(args.registry, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    stats = Counter()
    rows = []
    changed = 0

    for v in records:
        status, payload = classify(v)
        stats[status] += 1
        row = {
            "variant_id": v.get("variant_id"),
            "symbol": v.get("symbol"),
            "cov_override": v.get("cov_override"),
            "ablation_mode": v.get("ablation_mode"),
            "dir_acc": v.get("dir_acc"),
            "dir_acc_v2": (payload or {}).get("dir_acc_v2"),
            "status": status,
            "checkpoint_path": v.get("checkpoint_path"),
        }
        if payload is not None:
            row["n_zero_move"] = payload.get("n_zero_move")
            row["n_dir_active"] = payload.get("n_dir_active")
        rows.append(row)

        if not args.apply:
            continue
        if needs_write(v, payload):
            changed += 1
        if payload is not None:
            v.update(payload)
        # 未解决的记录写状态（不写值），让「没重算」可见
        if status in UNRESOLVED:
            v["recompute_status"] = status
        elif payload is not None:
            v["recompute_status"] = payload["recompute_status"]

    # ── 报告 ──
    print("=" * 72)
    print("dir_acc 主口径重算（剔零变动，spec W6.5①）")
    print("registry: %s" % args.registry)
    print("模式: %s" % ("APPLY" if args.apply else "DRY-RUN（未写入）"))
    print("=" * 72)
    print("总记录: %d" % len(records))
    print()
    for st in sorted(stats, key=lambda s: (-stats[s], s)):
        print("  %-24s %4d   %s" % (st, stats[st], STATUS_DOC.get(st, "")))
    print()

    resolved = sum(stats[s] for s in stats if s not in UNRESOLVED)
    unresolved = len(records) - resolved
    print("可重算: %d   不可重算(无证据，未写值): %d" % (resolved, unresolved))
    print()

    # 口径变更影响面（T3 风险表要求先量化再决定门限）
    deltas = [(r["dir_acc"], r["dir_acc_v2"]) for r in rows
              if r["status"] == "ok_recomputed" and r["dir_acc_v2"] is not None]
    if deltas:
        ds = [b - a for a, b in deltas]
        print("口径变更影响面（%d 条由旧口径转新口径）:" % len(deltas))
        print("  Δdir_acc  均值 %+.4f  中位 %+.4f  最小 %+.4f  最大 %+.4f"
              % (sum(ds) / len(ds), sorted(ds)[len(ds) // 2], min(ds), max(ds)))
        up = sum(1 for d in ds if d > 0)
        print("  上升 %d 条 / 下降 %d 条 / 不变 %d 条"
              % (up, sum(1 for d in ds if d < 0), sum(1 for d in ds if d == 0)))
        print()

    if unresolved:
        print("不可重算明细（按 variant_id）:")
        for r in rows:
            if r["status"] in UNRESOLVED:
                print("  %-34s %-22s dir_acc=%s"
                      % (str(r["variant_id"])[:34], r["status"], r["dir_acc"]))
        print()

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"stats": dict(stats), "rows": rows,
                       "generated_at": datetime.now().isoformat()},
                      f, ensure_ascii=False, indent=2)
        print("逐条结论: %s" % args.json_out)

    if not args.apply:
        print("\n（dry-run；加 --apply 写入）")
        return 0

    if changed == 0:
        print("\n无变化 —— 已是最新（幂等）")
        return 0

    # ── 原子写入 + 备份 ──
    bak = args.registry + ".bak_dir_acc_v2_" + datetime.now().strftime("%Y%m%d%H%M%S")
    shutil.copy2(args.registry, bak)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(args.registry), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for v in records:
                f.write(json.dumps(v, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, args.registry)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print("\n已写入 %d 条变更；备份 %s" % (changed, bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
