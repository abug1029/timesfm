#!/usr/bin/env python3
"""
批次 F (M3)：拒收统计聚合脚本

从 `.omc/supervisor_decisions.jsonl` 聚合「本轮」拒收分布，
物化为 prompt 段 `## Why proposals were rejected recently`。

窗口定义（Q10=a）：
- 主窗口：本次 supervisor 进程启动至今（满足幂等）
- 对照段：跨轮累计 since <first_decision_timestamp>（不受重启清零影响）

输出：
- 主窗口拒收分布（门 × 频次 top-N + 一句话原因）
- 对照段累计拒收分布（只读，不参与渲染决策）
- 本轮样本数（避免 peer 把薄样本当结论）

幂等约束：
- 除 `generated_at` 外物化字节一致
- 日志轮转/截断时降级为空段
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)

# Reuse canonical path from sup_paths (single source of truth)
sys.path.insert(0, HERE)
import sup_paths  # noqa: E402
DECISIONS_LOG = os.path.join(FM_ROOT, ".omc", "supervisor_decisions.jsonl")
SUPERVISOR_STATE = os.path.join(FM_ROOT, "data", "cache", "supervisor_state.json")
OUTPUT_FILE = sup_paths.REJECTIONS_INC  # canonical path from sup_paths


def parse_reject_reasons(reason_str):
    """解析 proposal_scan 的 reason 字段，提取 rejected 数和 reasons 字典"""
    # 格式：seen=N rejected=M backlog=K reasons={'key1': count1, 'key2': count2}
    match = re.search(r'rejected=(\d+)\s+backlog=\d+\s+reasons=(\{.*\})', reason_str)
    if not match:
        return 0, {}
    rejected = int(match.group(1))
    reasons_str = match.group(2)
    try:
        # 安全解析 dict 字符串（不用 eval）
        # 支持单引号和双引号
        reasons = {}
        for m in re.finditer(r"['\"](\w+)['\"]:\s*(\d+)", reasons_str):
            reasons[m.group(1)] = int(m.group(2))
        return rejected, reasons
    except Exception:
        return rejected, {}


def get_supervisor_start_ts():
    """获取 supervisor 启动时间戳（从 decisions log 推断）

    策略：找到最近一次 "run_started" action，这通常是 supervisor 启动后第一次调度。
    更准确的方式是在 supervisor 启动时写入 supervisor_state.json，但当前版本未实现。
    """
    if not os.path.exists(DECISIONS_LOG):
        return None

    # 从后往前找最近的 run_started
    with open(DECISIONS_LOG) as f:
        lines = f.readlines()

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if record.get("action") == "run_started":
            ts_str = record.get("ts")
            if ts_str:
                try:
                    return datetime.fromisoformat(ts_str).timestamp()
                except ValueError:
                    continue

    return None


def aggregate_rejections():
    """聚合拒收统计"""
    if not os.path.exists(DECISIONS_LOG):
        return {
            "main_window": {"total": 0, "reasons": {}},
            "cumulative": {"total": 0, "reasons": {}, "since": None},
            "sample_count": 0,
        }

    supervisor_start_ts = get_supervisor_start_ts()
    first_decision_ts = None
    main_window_reasons = Counter()
    cumulative_reasons = Counter()
    main_window_total = 0
    cumulative_total = 0
    sample_count = 0

    with open(DECISIONS_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("action") != "proposal_scan":
                continue

            # 解析时间戳
            ts_str = record.get("ts")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str).timestamp()
            except ValueError:
                continue

            # 记录第一条决策时间（对照段起点）
            if first_decision_ts is None:
                first_decision_ts = ts

            # 解析拒收原因
            reason_str = record.get("reason", "")
            rejected, reasons = parse_reject_reasons(reason_str)
            if rejected == 0:
                continue

            sample_count += 1
            cumulative_total += rejected
            for k, v in reasons.items():
                cumulative_reasons[k] += v

            # 主窗口：supervisor 启动至今
            if supervisor_start_ts and ts >= supervisor_start_ts:
                main_window_total += rejected
                for k, v in reasons.items():
                    main_window_reasons[k] += v

    return {
        "main_window": {
            "total": main_window_total,
            "reasons": dict(main_window_reasons.most_common()),
        },
        "cumulative": {
            "total": cumulative_total,
            "reasons": dict(cumulative_reasons.most_common()),
            "since": first_decision_ts,
        },
        "sample_count": sample_count,
    }


def render_markdown(stats):
    """渲染为 Markdown prompt 段"""
    lines = []
    lines.append("## Why proposals were rejected recently")
    lines.append("")
    lines.append(f"> 本轮样本数：{stats['sample_count']} 次扫描，{stats['main_window']['total']} 条拒收")
    lines.append("")

    if stats['main_window']['total'] == 0:
        lines.append("本轮无拒收记录。")
    else:
        lines.append("**主窗口（本轮）拒收分布**：")
        lines.append("")
        for reason, count in stats['main_window']['reasons'].items():
            pct = count / stats['main_window']['total'] * 100
            lines.append(f"- `{reason}`: {count} 次 ({pct:.1f}%)")
        lines.append("")

    # 对照段
    if stats['cumulative']['total'] > 0:
        since_str = "N/A"
        if stats['cumulative']['since']:
            since_str = datetime.fromtimestamp(stats['cumulative']['since']).strftime("%Y-%m-%d %H:%M")
        lines.append(f"<details><summary>跨轮累计（since {since_str}，只读参考）</summary>")
        lines.append("")
        lines.append(f"累计 {stats['cumulative']['total']} 条拒收：")
        lines.append("")
        for reason, count in stats['cumulative']['reasons'].items():
            pct = count / stats['cumulative']['total'] * 100
            lines.append(f"- `{reason}`: {count} 次 ({pct:.1f}%)")
        lines.append("")
        lines.append("</details>")

    lines.append("")
    lines.append(f"_Generated at: {datetime.now().isoformat()}_")
    return "\n".join(lines)


def main():
    stats = aggregate_rejections()
    md = render_markdown(stats)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        f.write(md)

    print(f"M3 拒收统计已物化到 {OUTPUT_FILE}")
    print(f"  主窗口：{stats['main_window']['total']} 条拒收")
    print(f"  对照段：{stats['cumulative']['total']} 条拒收")
    print(f"  样本数：{stats['sample_count']} 次扫描")


if __name__ == "__main__":
    main()


def render_rejection_detail_section(rejected_path: str) -> str:
    """从 rejected_proposals.jsonl 生成 per-proposal 拒收详情 Markdown 节。
    供 materialize_known_verdicts（Task 9）调用。
    不写任何文件。
    """
    if not os.path.exists(rejected_path):
        return '\n_no rejection records yet_\n'

    records = []
    for line in open(rejected_path, encoding='utf-8'):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    lines = []
    lines.append('\n### Rejection Details (per-proposal)\n')
    lines.append('| proposal_id | version | reason | quality_score | symbol | cov_override | family |')
    lines.append('|---|---|---|---|---|---|---|')
    for r in records:
        lines.append('| %s | v%s | %s | %s | %s | %s | %s |' % (
            r.get('proposal_id', '?'),
            r.get('version', '?'),
            r.get('reject_reason', '?'),
            r.get('quality_score', 'N/A'),
            r.get('symbol', '?'),
            r.get('cov_override', '?'),
            r.get('covariate_family', '?'),
        ))
    return '\n'.join(lines) + '\n'
