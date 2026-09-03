"""Markdown rendering for Neutral A/B universe reports.

Pure presentation — no scoring / gate decisions.
Constants for domain-shift labels imported from neutral_ab_report.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from config.sector_map import agri_symbols, chem_symbols


def render_markdown(score: Any, *, constants: dict | None = None) -> str:
    """
    Render UniverseScore → markdown string.

    `constants` optional override for unit tests; default pulls from
    cascade.neutral_ab_report module attributes.
    """
    if constants is None:
        from cascade import neutral_ab_report as nab
        constants = {
            "TRAIN_POOL": nab.TRAIN_POOL,
            "VETO_NEAR_ZERO": nab.VETO_NEAR_ZERO,
            "VETO_NEAR_ALL": nab.VETO_NEAR_ALL,
            "VETO_SOFT_HIGH": nab.VETO_SOFT_HIGH,
            "R1_EXTREME_THRESHOLD": nab.R1_EXTREME_THRESHOLD,
        }

    train_pool = constants["TRAIN_POOL"]
    veto_zero = constants["VETO_NEAR_ZERO"]
    veto_all = constants["VETO_NEAR_ALL"]
    veto_soft = constants["VETO_SOFT_HIGH"]
    r1_thr = constants["R1_EXTREME_THRESHOLD"]

    c = score.counts
    po, pn = score.pool_off, score.pool_on
    d = score.domain
    smoke = score.smoke
    meta = score.meta or {}
    thr = meta.get("thr", 0.55)
    oos = f"{meta.get('oos_start', '?')} ~ {meta.get('oos_end', '?')}"
    step = meta.get("step", 24)
    train = ",".join(sorted(train_pool))

    extreme_txt = ", ".join(
        f"{x['sym'].upper()}({x['veto']:.0%})"
        for x in d["extreme_strict_non_black"]
    ) or "(none)"
    soft_txt = ", ".join(
        f"{x['sym'].upper()}({x['veto']:.0%})"
        for x in d["extreme_soft_non_black"]
    ) or "(none)"

    r1_label = "触发 → 建议分板块重训" if d["r1_trigger"] else "未触发"
    chem_cands = sorted(
        (set(d["chem_extremes"]) | chem_symbols()) & set(score.symbols)
    )
    agri_cands = sorted(
        (set(d["agri_extremes"]) | agri_symbols()) & set(score.symbols)
    )

    lines = [
        "# TimesFM 全链路 Vol Gating OOS — **NEUTRAL OVERLAY**",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**品种**: {', '.join(s.upper() for s in score.symbols)} "
        f"(n={len(score.symbols)})",
        f"**OOS**: {oos}",
        f"**step**: {step}  **thr**: {thr}  **action**: `neutral`  "
        f"**mode**: shared-forecast",
        f"**工程裁决**: `{score.engineering_verdict}`",
        f"**生产门禁**: `{score.production_gate}`",
        f"**生产默认**: 仍为 OFF",
        f"**vol_model**: `models/vol_risk_filter_v2.pkl` (train pool: {train})",
        "",
        "## 裁决说明",
        "",
        "- 配对控制：Base(Cov) vs Base(Cov)+Flatten；共享 raw forecast",
        f"- 分品种：HELPS={c['HELPS']}  MIXED={c['MIXED']}  "
        f"HURTS={c['HURTS']}  NEUTRAL={c['NEUTRAL']}",
        f"- EV↑={c['ev_up']}/{len(score.rows)}  MaxDD↑={c['dd_up']}/{len(score.rows)}  "
        f"risk_cut={c['risk_cut']}",
        f"- 宇宙 ΔmeanEV={c['delta_EV']:+.3f}  ΔmeanMaxDD={c['delta_MaxDD']:+.4f}  "
        f"ΔΣNetPnL={c['delta_sum_NetPnL']:+.1f}",
        f"- Domain Shift 非黑色系极端 veto(0%|100%): "
        f"**{len(d['extreme_strict_non_black'])}** ({extreme_txt})",
        f"- R1 阈值(>{r1_thr} 非黑色 0%/100%): **{r1_label}**",
    ]
    for p in score.verdict_parts:
        lines.append(f"- {p}")
    for g in score.gate_reasons:
        lines.append(f"- {g}")
    for n in smoke.notes:
        lines.append(f"- Smoke: {n}")

    lines.extend([
        "",
        "## 汇总（品种等权 · 主指标 EV / MaxDD / NetPnL）",
        "",
        "| 模式 | mean EV | mean MaxDD | ΣNetPnL | mean PF† |",
        "|------|--------:|-----------:|--------:|---------:|",
        f"| 熔断 OFF | {po['mean_EV']:.4f} | {po['mean_MaxDD']:.4f} | "
        f"{po['sum_NetPnL']:.1f} | {po['mean_PF']:.3f} |",
        f"| **NEUTRAL** | {pn['mean_EV']:.4f} | {pn['mean_MaxDD']:.4f} | "
        f"{pn['sum_NetPnL']:.1f} | {pn['mean_PF']:.3f} |",
        f"| **Δ** | **{c['delta_EV']:+.4f}** | **{c['delta_MaxDD']:+.4f}** | "
        f"**{c['delta_sum_NetPnL']:+.1f}** | **{c['delta_mean_PF']:+.3f}** |",
        "",
        "> † mean PF 在大量全空仓时会被 0 / 99.99 扭曲，**不作主裁决**。",
        "",
        "## 分品种 A/B",
        "",
        "| 品种 | sector | cov | n | veto% | EV_off | EV_on | ΔEV | "
        "MaxDD_off | MaxDD_on | NetPnL_off | NetPnL_on | 判定 | warn |",
        "|------|--------|-----|--:|------:|-------:|------:|----:|"
        "----------:|---------:|-----------:|----------:|------|------|",
    ])
    for r in score.rows:
        lines.append(
            f"| {r['sym'].upper()} | {r['sector']} | {r['cov']} | {r['n']} | "
            f"{r['veto']:.0%} | {r['ev_off']:.3f} | {r['ev_on']:.3f} | "
            f"{r['ev_on']-r['ev_off']:+.3f} | "
            f"{r['dd_off']:.4f} | {r['dd_on']:.4f} | "
            f"{r['pnl_off']:.1f} | {r['pnl_on']:.1f} | "
            f"**{r['tag']}** | {(r['warn'] or '')[:36]} |"
        )

    off_all = meta.get("_off_blocks") or {}
    neu_all = meta.get("_neu_blocks") or {}
    if off_all and neu_all:
        lines.append("")
        lines.append("## 预测平滑 / 尖刺")
        lines.append("")
        lines.append(
            "| 品种 | OFF mean|Δ| | ON mean|Δ| | ON spikes≥2% | "
            "spikes@veto切换 | ON max|Δ| |"
        )
        lines.append(
            "|------|------------:|-----------:|---------------:"
            "|-----------------:|------------:|"
        )
        for sym in score.symbols:
            s_off = (off_all.get(sym) or {}).get("spike_stats") or {}
            s_on = (neu_all.get(sym) or {}).get("spike_stats") or {}
            if not s_off and not s_on:
                continue
            lines.append(
                f"| {sym.upper()} | "
                f"{s_off.get('mean_abs_d_end_pct', float('nan')):.4f} | "
                f"{s_on.get('mean_abs_d_end_pct', float('nan')):.4f} | "
                f"{s_on.get('n_spikes_ge_2pct', 0)} | "
                f"{s_on.get('n_spikes_on_veto_switch', 0)} | "
                f"{s_on.get('max_abs_d_end_pct', float('nan')):.4f} |"
            )

    lines.extend([
        "",
        "## Domain Shift / R1 审计",
        "",
        f"- **严格极端 (≤{veto_zero:.0%} 或 ≥{veto_all:.0%}) 非黑色**: "
        f"{len(d['extreme_strict_non_black'])} / 阈值>{r1_thr} → "
        f"{'**R1 TRIGGER**' if d['r1_trigger'] else 'OK'}",
        f"- 明细: {extreme_txt}",
        f"- 软极端 (0% 或 ≥{veto_soft:.0%}) 非黑色: "
        f"{len(d['extreme_soft_non_black'])} — {soft_txt}",
        f"- 能化极端: {d['chem_extremes']}",
        f"- 农产品极端: {d['agri_extremes']}",
        f"- 训练池内极端: {d['train_pool_extremes']}",
        "",
        "### R1 建议",
        "",
    ])
    if d["r1_trigger"]:
        lines.extend([
            "1. **暂停 L2**；生产保持 OFF。",
            f"2. 重训 `vol_risk_filter_chem.pkl` (候选: {chem_cands})。",
            f"3. 重训 `vol_risk_filter_agri.pkl` (候选: {agri_cands})。",
            "4. 黑色系可暂留 R0；注意板块内 veto 不一致时可单列 black 过滤器。",
            "5. R1 完成后再跑 L1 对照，再议 L2。",
            "",
        ])
    else:
        lines.extend([
            "- 未触发 R1；可在 REMAIN_OFF 前提下评估 L2（可选）。",
            "",
        ])

    lines.extend([
        "## 生产门禁结论",
        "",
        f"**`{score.production_gate}`**",
        "",
        "| 选项 | 含义 | 本轮 |",
        "|------|------|------|",
        f"| REMAIN_OFF | 生产默认继续关 | "
        f"{'← 当前' if score.production_gate == 'REMAIN_OFF' else ''} |",
        f"| WHITELIST_ONLY | 仅白名单品种实验开关 | "
        f"{'← 当前' if score.production_gate == 'WHITELIST_ONLY' else ''} |",
        f"| ALLOW_DEFAULT_ON_L1 | L1 默认可开 | "
        f"{'← 当前' if score.production_gate == 'ALLOW_DEFAULT_ON_L1' else ''} |",
        "",
        "白名单候选 (HELPS 且 ΔEV>1): "
        + (", ".join(s.upper() for s in score.whitelist) or "(无)"),
        "",
        "## Phase 1 终局说明",
        "",
        "- Neutral Override = Absolute Risk Overlay：切断高波失效期左侧尾部。",
        "- 不改 XReg 维数 → 无 Ridge 跳变；delta_pred=0 → PnL=0 + 摩擦豁免。",
        "- 生产默认仍 OFF，直至 R1 或人工确认白名单。",
        "- 评分源: `cascade/neutral_ab_report.py`；渲染: `cascade/neutral_ab_render.py`。",
        "",
    ])
    if meta.get("progress_path"):
        lines.append(f"进度日志: `{meta['progress_path']}`")
    if meta.get("report_json"):
        lines.append(f"JSON: `{meta['report_json']}`")
    if meta.get("by_symbol_dir"):
        lines.append(f"by_symbol: `{meta['by_symbol_dir']}`")
    lines.append("")
    return "\n".join(lines)
