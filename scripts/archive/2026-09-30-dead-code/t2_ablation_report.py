#!/usr/bin/env python3
"""T2: 三路消融对照表（spec §8.2 出口核验）

判定目标：full / content / structural / baseline 四口径是否可区分
          —— 即「协变量输入确实改变模型」。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

FM_ROOT = Path("/home/abug/timesfm")
REGISTRY = FM_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"
OUT = FM_ROOT / "docs" / "superpowers" / "reports" / "2026-09-28-t2-ablation-table.md"

MODES = ["full", "content", "structural", "baseline"]


def load_ablation_verdicts():
    """加载带 ablation_mode 的裁决（排除墓碑）"""
    out = []
    with open(REGISTRY, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
            except json.JSONDecodeError:
                continue
            if v.get("ablation_mode") and v.get("status") == "ok":
                out.append(v)
    return out


def fmt(x, nd=4):
    if x is None:
        return "None"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def main():
    verdicts = load_ablation_verdicts()
    if not verdicts:
        print("❌ 无消融裁决")
        return 1

    # 按 (symbol, cov) -> mode -> verdict 索引
    table = defaultdict(dict)
    for v in verdicts:
        key = (v["symbol"], v["cov_override"])
        table[key][v["ablation_mode"]] = v

    lines = []
    lines.append("# T2 三路消融对照表（2026-09-28）\n")
    lines.append("> spec §8.2 出口核验：确认协变量输入确实改变模型。\n")
    lines.append(f"消融裁决数：**{len(verdicts)}**（status=ok，已排除 no_data 墓碑）\n")

    # ---- 逐组明细 ----
    lines.append("## 逐组明细\n")
    lines.append("| 品种 | 协变量 | 模式 | n | dir_acc | dir_acc_full | endpoint_mape | gate_pass |")
    lines.append("|------|--------|------|---|---------|-------------|--------------|-----------|")

    for (sym, cov) in sorted(table.keys()):
        for mode in MODES:
            v = table[(sym, cov)].get(mode)
            if v is None:
                lines.append(f"| {sym} | {cov} | {mode} | — | — | — | — | 缺失 |")
                continue
            lines.append(
                f"| {sym} | {cov} | {mode} | {v.get('n')} | "
                f"{fmt(v.get('dir_acc'))} | {fmt(v.get('dir_acc_full'))} | "
                f"{fmt(v.get('endpoint_mape'), 3)} | {v.get('gate_pass')} |"
            )
    lines.append("")

    # ---- 三组对照 ----
    lines.append("## 三路对照\n")
    lines.append("| 品种 | 协变量 | 内容效应 full-content | 通道效应 full-structural | 路径差 structural-baseline | 输入是否改变模型 |")
    lines.append("|------|--------|------------------------|--------------------------|------------------------------|------------------|")

    changed_groups, unchanged_groups = [], []
    for (sym, cov) in sorted(table.keys()):
        modes = table[(sym, cov)]
        f, c, s, b = (modes.get(m) for m in MODES)

        def da(v):
            return v.get("dir_acc") if v else None

        def diff(x, y):
            if x is None or y is None:
                return None
            return x - y

        d_content = diff(da(f), da(c))
        d_struct = diff(da(f), da(s))
        d_path = diff(da(s), da(b))

        # 「输入改变模型」判定 —— 必须用连续指标交叉验证。
        # 只看 dir_acc 会漏判：n 小时 dir_acc 是二值命中计数（k/n 粒度），
        # 不同连续输出可能落在同一命中数上。实测证据：
        #   jd_calendar_cyclical  baseline pred_end=3052.2571
        #                           structural pred_end=3049.5288
        # 两者 pred_end 不同但 dir_acc 均为 0.8330。
        # 故判据 = dir_acc 有差异 **或** endpoint_mape 有差异（相对容差 1e-6）。
        def mape(v):
            return v.get("endpoint_mape") if v else None

        vals = [da(x) for x in (f, c, s, b)]
        present = [v for v in vals if v is not None]
        changed_diracc = len(set(round(v, 9) for v in present)) > 1 if present else False

        mvals = [mape(x) for x in (f, c, s, b)]
        mpresent = [v for v in mvals if v is not None]
        changed_mape = len(set(round(v, 6) for v in mpresent)) > 1 if mpresent else False

        changed = changed_diracc or changed_mape

        fmtc = fmt(d_content) if d_content is not None else "—"
        fmts = fmt(d_struct) if d_struct is not None else "—"
        fmtp = fmt(d_path) if d_path is not None else "—"

        if changed_diracc and changed_mape:
            verdict = "✅ 是（dir_acc + mape 双证）"
        elif changed_mape:
            verdict = "✅ 是（仅 mape；dir_acc 二值粒度未分辨）"
        elif changed_diracc:
            verdict = "✅ 是（仅 dir_acc）"
        else:
            verdict = "❌ 四口径同一"
        (changed_groups if changed else unchanged_groups).append((sym, cov))

        lines.append(
            f"| {sym} | {cov} | {fmtc} | {fmts} | {fmtp} | {verdict} |"
        )
    lines.append("")

    # ---- 结论 ----
    lines.append("## 结论\n")
    if changed_groups:
        lines.append(f"**输入确实改变模型**：{len(changed_groups)}/{len(table)} 组四口径可区分。\n")
        for sym, cov in changed_groups:
            lines.append(f"- `{sym}_{cov}`")
        lines.append("")
    if unchanged_groups:
        lines.append(f"**输入未改变模型**：{len(unchanged_groups)} 组四口径同一 —— "
                     f"该协变量在此品种上对预测无任何影响（含通道与内容）。\n")
        for sym, cov in unchanged_groups:
            lines.append(f"- `{sym}_{cov}`")
        lines.append("")

    if changed_groups:
        lines.append("### 对 Stage 2 降级声明的影响\n")
        lines.append("Stage 1/2 的核心降级声明是「协变量未被利用」。本次消融显示"
                     "**部分协变量确实进入模型并改变输出**，故该声明需按品种/协变量"
                     "逐项收窄，而非全盘接受或全盘否定。\n")
    else:
        lines.append("### 对 Stage 2 降级声明的影响\n")
        lines.append("四口径全同 —— 协变量通道虽被调用，但在本样本上未观察到"
                     "对输出方向的影响。**注意：n=6 时 dir_acc 是二值命中计数，"
                     "分辨率不足以区分「路径相同」与「路径不同但方向一致」**，"
                     "故此结果不足以支撑「降级声明成立」的定论。\n")

    lines.append("## ⚠️ 脚本行为说明\n")
    lines.append("本脚本是**破坏性写入** —— 重跑会覆盖本文件中人工补充的"
                 "「方法论限制」小节。若需保留人工分析，请先备份，"
                 "或将人工段落改为由脚本读取的独立片段。\n")

    text = "\n".join(lines)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")

    print(text)
    print(f"\n已写入: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
