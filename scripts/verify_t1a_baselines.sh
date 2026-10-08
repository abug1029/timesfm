#!/bin/bash
# T1a 基线验收
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

echo "=== 1. 基线文件计数 ==="
COUNT=$(ls -1 task_FM/config/baseline_points_*_nocov.jsonl 2>/dev/null | wc -l)
echo "nocov 基线数: $COUNT (期望 8)"

echo
echo "=== 2. 逐份验收（行数 + protocol_fingerprint 存在性）==="
printf "%-14s %8s %10s %s\n" "文件" "行数" "指纹" "首行 cutoff 样例"
for f in task_FM/config/baseline_points_*_nocov.jsonl; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    lines=$(wc -l < "$f")
    fp=$(head -1 "$f" | grep -c 'protocol_fingerprint' || true)
    cutoff=$(head -1 "$f" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('cutoff','?'))" 2>/dev/null || echo "?")
    printf "%-14s %8s %10s %s\n" "$name" "$lines" "$fp" "$cutoff"
done

echo
echo "=== 3. 指纹一致性（同协议指纹才算可比）==="
python3 - <<'PY'
import json, glob, collections
fps = collections.Counter()
for p in sorted(glob.glob("task_FM/config/baseline_points_*_nocov.jsonl")):
    with open(p) as f:
        first = f.readline()
    if not first.strip():
        continue
    d = json.loads(first)
    fps[d.get("protocol_fingerprint")] += 1
for fp, n in fps.items():
    label = fp[:16] + "..." if fp else "None"
    print(f"  {label}: {n} 份")
if len(fps) == 1 and None not in fps:
    print("  ✅ 全部同协议指纹（可比）")
elif None in fps:
    print(f"  ❌ {fps[None]} 份缺指纹（不可比）")
else:
    print(f"  ⚠️ 存在 {len(fps)} 种不同指纹（跨协议不可比）")
PY

echo
echo "=== 4. T1a 判据 A/B' 验证 ==="
.venv/bin/python scripts/verify_t1a_criteria_a.py
echo "退出码: $?"
