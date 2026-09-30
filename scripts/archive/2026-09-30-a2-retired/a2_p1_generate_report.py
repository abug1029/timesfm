"""A2-P1 Report Generator: fail-closed 校验 + 原子写入 + 正确 tick size。

Usage:
    python scripts/a2_p1_generate_report.py --run-id a2-p1
    python scripts/a2_p1_generate_report.py --run-id a2-p1.1

不带 --run-id 参数时报错。

产出:
    reports/research/2026-08-05_a2_p1_baseline_result.md   (a2-p1)
    reports/research/20260806_a2_p1.1_verdict.md            (a2-p1.1)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pandas as pd

from config.backtest_config import SYMBOLS, TICK_SIZES
from scripts.a2_p1_lgbm_baseline import evaluate_gate
from scripts.a2_p1_runtime import (
    RunConfig,
    validate_run_results,
)


def load_symbol_results(jsonl_path: pathlib.Path) -> pd.DataFrame:
    """读取单品种 JSONL 为 DataFrame"""
    if not jsonl_path.exists():
        return pd.DataFrame()
    records = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return pd.DataFrame(records) if records else pd.DataFrame()


def generate_report(config: RunConfig) -> None:
    """遍历所有 JSONL, 做 fail-closed 校验, 计算 gate 裁决, 生成 Markdown 报告。

    - 任何一个 symbol 校验失败: 打印 per-symbol 错误, 抛 RuntimeError, 不写报告
    - 所有 symbol 校验通过后: 先写到 .tmp, 再 os.replace 原子替换
    - tick size 来自 TICK_SIZES; 缺失时抛 RuntimeError
    """
    # ═══ Step 1: fail-closed 前置校验 ═══
    report = validate_run_results(config)
    if not report.ok:
        print("[Report] FAIL — 校验不通过:")
        for err in report.errors:
            print(f"  {err}")
        raise RuntimeError(
            f"generate_report: {len(report.errors)} validation error(s) "
            f"across {sum(1 for v in report.per_symbol.values() if not v.ok)} symbol(s)"
        )

    # ═══ Step 2: 计算每个品种的 gate 裁决 ═══
    results_dir = config.results_dir
    verdicts = []

    for sym in config.symbols:
        sym_lower = sym.lower()
        jsonl_path = results_dir / f"{sym_lower}.jsonl"
        df = load_symbol_results(jsonl_path)

        if df.empty or len(df) < 10:
            print(f"[Report] SKIP {sym.upper()}: insufficient data ({len(df)} points)")
            continue

        # 提取 arrays
        lgbm_moves = df["lgbm_pred_move"].values.astype(float)
        pure_moves = df["pure_pred_move"].values.astype(float)
        scheme_moves = df["scheme_pred_move"].values.astype(float)
        actual_moves = df["actual_move"].values.astype(float)
        base_prices = df["base_price"].values.astype(float)
        atrs = df["atr"].values.astype(float)

        # tick_size — 唯一权威来源: TICK_SIZES
        try:
            tick = float(TICK_SIZES[sym_lower])
        except KeyError:
            raise RuntimeError(
                f"missing tick size for {sym_lower}; "
                f"please add it to config.backtest_config.TICK_SIZES"
            )

        # 调用 evaluate_gate
        verdict = evaluate_gate(
            lgbm_moves, pure_moves, scheme_moves,
            actual_moves, base_prices, atrs, tick_size=tick,
        )
        verdict["symbol"] = sym.upper()
        verdict["n_eval"] = len(df)
        verdict["tick_size"] = tick
        verdicts.append(verdict)
        lgbm_pf = verdict.get("lgbm_metrics", {}).get("PF", "N/A")
        print(f"[Report] {sym.upper()}: {verdict.get('gate')} (LGBM PF={lgbm_pf})")

    # ═══ Step 3: 写 Markdown 报告 (原子替换) ═══
    report_path = config.report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# A2-P1 LGBM 基线门禁裁决报告", "", f"**品种数**: {len(verdicts)}", ""]
    go_count = sum(1 for v in verdicts if v.get("gate") == "GO")
    lines.append(f"**聚合裁决**: {'GO' if go_count > len(verdicts) / 2 else 'NO-GO'} "
                 f"({go_count}/{len(verdicts)} 品种 GO)")
    lines.append("")
    lines.append("| 品种 | gate | LGBM PF | scheme PF | LGBM EV | EV差CI下界 | n | tick_size |")
    lines.append("|------|------|---------|-----------|---------|-----------|---|-----------|")
    for v in verdicts:
        lpf = v.get("lgbm_metrics", {}).get("PF", "N/A")
        spf = v.get("scheme_metrics", {}).get("PF", "N/A")
        lev = v.get("lgbm_metrics", {}).get("EV", "N/A")
        ci = v.get("ev_diff_ci", {}).get("lower", "N/A")
        ts = v.get("tick_size", "?")
        lines.append(f"| {v.get('symbol', '?')} | {v.get('gate', '?')} | {lpf} | "
                     f"{spf} | {lev} | {ci} | {v.get('n_eval', 0)} | {ts} |")

    lines.append("")
    lines.append("## 声明")
    lines.append("- vol_prob 在 2026-03 前评估点有轻微 Lookahead（模型训练截止 2026-03-31）")
    lines.append("- 本报告会随 JSONL 数据增加自动更新")

    content = "\n".join(lines)

    # 原子写入: 先写 .tmp, 再 os.replace
    tmp_path = report_path.with_suffix('.tmp')
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(str(tmp_path), str(report_path))
    print(f"\n报告已生成: {report_path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A2-P1 门禁裁决报告生成器 (fail-closed)"
    )
    parser.add_argument(
        "--run-id",
        required=True,
        choices=["a2-p1", "a2-p1.1"],
        help="实验 run_id (a2-p1 或 a2-p1.1)",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    from data.config import FM_ROOT
    config = RunConfig.for_run(args.run_id, SYMBOLS, FM_ROOT)
    generate_report(config)
