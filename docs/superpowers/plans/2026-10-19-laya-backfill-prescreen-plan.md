# Laya 积压预处理 + 慢环接手 — 实施计划

> **日期**: 2026-10-19
> **审核**: Critic (Opus) REJECT → 优化后通过
> **状态**: pending approval

---

## 0. 现状

| 项 | 值 |
|----|---|
| Laya 端点 | `http://100.96.19.116:8000`（Tailscale 备用 IP） |
| 延迟 | Connect 1.88s / TTFB 2.26s |
| 脚本 | `scripts/backfill_prescreen.py` v2.1.0 |
| 扫描范围 | `task_FM/experiments/run_*/results/**/proposals/*.json`（排除 `.prescreen.json`） |
| 提案总数 | 7389 |
| 已 prescreen | 1314 |
| **待处理** | **6075** |
| 实测单提案耗时 | ~11s（Oct 18 数据：50 个/551s） |
| Workers=2 预估 | **~9.3 小时** |

### 数据流

```
backfill_prescreen.py
  → Laya prescreen (HTTP POST /v1/systemone)
  → 写 .prescreen.json
  → queue_enqueue() → aligned_pending.jsonl（成功入队）

aligned_slow_loop.py
  → queue_claim() 从 aligned_pending.jsonl 取行
  → 回测评估
  → append_verdict() → aligned_verdicts.jsonl
  → write_proposal_status(verdicted)
```

---

## 1. Phase 0：预检（5 分钟）

```bash
cd /home/abug/timesfm

# 1.1 Laya 健康 + 模型确认
curl -sf --connect-timeout 5 --max-time 10 http://100.96.19.116:8000/health | python3 -m json.tool
# PASS: status=ok, loaded 含 english

# 1.2 延迟基线
curl -s -o /dev/null -w 'HTTP %{http_code} | Connect: %{time_connect}s | TTFB: %{time_starttransfer}s' \
  http://100.96.19.116:8000/health
# 记录基线值

# 1.3 磁盘空间
df -h /home/abug/timesfm | awk 'NR==2{print "Free: "$4}'
# PASS: > 1GB

# 1.4 积压确认
LAYA_BASE_URL=http://100.96.19.116:8000 python3 -c "
import glob
from pathlib import Path
FM = Path('/home/abug/timesfm')
all_p = [p for p in glob.glob(str(FM/'task_FM/experiments/run_*/results/**/proposals/*.json'), recursive=True) if not p.endswith('.prescreen.json')]
ps = [p for p in all_p if Path(p).with_suffix('.prescreen.json').exists()]
print(f'Total: {len(all_p)}, Prescreened: {len(ps)}, Pending: {len(all_p)-len(ps)}')
"
# PASS: Pending ≈ 6075 (±5%)
```

---

## 2. Phase 1：干跑（1 分钟）

```bash
LAYA_BASE_URL=http://100.96.19.116:8000 python3 scripts/backfill_prescreen.py \
  --dry-run --skip-laya-check
# PASS: 输出 "待处理: ~6075"
# FAIL: 偏差 >10% → 检查 glob 匹配
```

---

## 3. Phase 2：试点批 100 个 — 校准 + 质量门禁（20 分钟）

```bash
# 3.1 跑 100 个（校准计时）
LAYA_BASE_URL=http://100.96.19.116:8000 python3 scripts/backfill_prescreen.py \
  --max 100 --workers 2 --timeout-min 60 --skip-laya-check \
  >> logs/backfill_pilot_$(date +%Y%m%d_%H%M%S).log 2>&1
# 等待完成

# 3.2 计时校准
grep "elapsed=" logs/backfill_pilot_*.log | tail -1
# per_proposal_s = elapsed / total_processed
# full_estimate_h = (6075 * per_proposal_s / 2) / 3600
```

### Phase 2.5：Laya 工作质量评估

```bash
# 3.3 中文泄漏检查
python3 -c "
import json, re
from pathlib import Path

_EAST_ASIAN = re.compile(r'[一-鿿　-〿！-／：-＠［-＿｛-･]')
FM = Path('/home/abug/timesfm')
files = sorted(FM.glob('task_FM/experiments/run_*/results/**/proposals/*.prescreen.json'))
recent = files[-100:]  # 最近 100 个

violations = 0
for pf in recent:
    data = json.loads(pf.read_text(encoding='utf-8'))
    pd = data.get('proposal_summary', {}).get('predicted_direction', '')
    if _EAST_ASIAN.search(pd):
        violations += 1
        print(f'VIOLATION: {pf.name} -> {pd!r}')

print(f'Checked {len(recent)}, violations: {violations}')
assert violations == 0, f'Chinese leakage detected: {violations} violations'
"
# PASS: violations == 0
# FAIL: violations > 0 → STOP，检查 Laya 模型版本

# 3.4 status 字段合法性
python3 -c "
import json
from pathlib import Path
from collections import Counter

FM = Path('/home/abug/timesfm')
files = sorted(FM.glob('task_FM/experiments/run_*/results/**/proposals/*.prescreen.json'))[-100:]
statuses = Counter()
for pf in files:
    data = json.loads(pf.read_text())
    statuses[data.get('status')] += 1

print(f'Status distribution: {dict(statuses)}')
invalid = {k: v for k, v in statuses.items() if k not in ('success', 'error', 'degraded', None)}
assert not invalid, f'Invalid statuses: {invalid}'
"
# PASS: all in {success, error, degraded, None}

# 3.5 variant_id 格式
python3 -c "
import json, re
from pathlib import Path

FM = Path('/home/abug/timesfm')
files = sorted(FM.glob('task_FM/experiments/run_*/results/**/proposals/*.prescreen.json'))[-100:]
valid_re = re.compile(r'^[a-z0-9_]+$')
invalid = []
for pf in files:
    data = json.loads(pf.read_text())
    vid = data.get('variant_id', '')
    if vid and not valid_re.match(vid):
        invalid.append((pf.name, vid))

print(f'Checked {len(files)}, invalid variant_ids: {len(invalid)}')
if invalid:
    for name, vid in invalid[:5]:
        print(f'  {name}: {vid}')
assert len(invalid) == 0, f'Invalid variant_ids found'
"
# PASS: all variant_ids match [a-z0-9_]+
```

**质量门禁总结**：
| 检查项 | PASS 条件 | FAIL 处理 |
|--------|----------|----------|
| 中文泄漏 | 0 violations | STOP，调查 Laya 模型 |
| status 合法 | 全部 ∈ {success, error, degraded} | >5% 非法 → STOP |
| variant_id 格式 | 全部 ∈ [a-z0-9_]+ | >5% 非法 → STOP |

---

## 4. Phase 3：全量执行（~9.3 小时）

```bash
cd /home/abug/timesfm

# 关键参数：--timeout-min 720（12h，含 20% 余量）
LAYA_BASE_URL=http://100.96.19.116:8000 setsid nohup \
  python3 scripts/backfill_prescreen.py \
  --workers 2 \
  --timeout-min 720 \
  --skip-laya-check \
  >> logs/backfill_$(date +%Y%m%d_%H%M%S).log 2>&1 &

echo "PID: $!"
```

### Phase 3.5：运行监控

```bash
# 看门狗：每 5 分钟检查 state 文件更新
LOG_FILE=$(ls -t /home/abug/timesfm/logs/backfill_2*.log | head -1)
STATE_FILE="/home/abug/timesfm/data/cache/backfill_prescreen_state.json"

while kill -0 $BACKFILL_PID 2>/dev/null; do
  sleep 300
  STATE_AGE=$(( $(date +%s) - $(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0) ))
  PROGRESS=$(grep -oP '进度: \K\d+/\d+' "$LOG_FILE" 2>/dev/null | tail -1)
  echo "$(date +%H:%M) Progress: $PROGRESS | State age: ${STATE_AGE}s"

  if (( STATE_AGE > 900 )); then
    echo "⚠️ WARNING: state file stale > 15 min — possible hang"
  fi

  RECENT_ERR=$(tail -50 "$LOG_FILE" | grep -c '\[ERROR\]' || true)
  if (( RECENT_ERR > 15 )); then
    echo "🚨 ALERT: $RECENT_ERR errors in last 50 lines"
  fi
done
echo "Backfill process exited"
```

---

## 5. Phase 4：后验证 + 质量评估（15 分钟）

```bash
LOG_FILE=$(ls -t /home/abug/timesfm/logs/backfill_2*.log | head -1)

# 5.1 日志最终统计
grep "完成:" "$LOG_FILE" | tail -1
# 期望: total=6075 success=N failed=M enqueued=K degraded=D

# 5.2 错误率
python3 -c "
import re, sys
line = open('$LOG_FILE').read()
m = re.search(r'success=(\d+).*?failed=(\d+)', line.split(chr(10))[-10:])
if m:
    s, f = int(m.group(1)), int(m.group(2))
    rate = f/(s+f)*100 if (s+f) else 0
    print(f'Error rate: {rate:.1f}% ({f}/{s+f})')
    assert rate < 5, f'Error rate {rate:.1f}% exceeds 5% threshold'
"

# 5.3 磁盘交叉验证
python3 -c "
import glob
from pathlib import Path
FM = Path('/home/abug/timesfm')
on_disk = len(glob.glob(str(FM/'task_FM/experiments/run_*/results/**/proposals/*.prescreen.json'), recursive=True))
print(f'Prescreen files on disk: {on_disk}')
# 应等于: 1314(前) + success(本次)
"

# 5.4 队列深度评估
python3 -c "
from pathlib import Path
q = Path('/home/abug/timesfm/data/cache/aligned_pending.jsonl')
if q.exists():
    lines = [l for l in q.read_text().strip().split(chr(10)) if l.strip()]
    print(f'Queue depth: {len(lines)}')
    if len(lines) > 5000:
        print('⚠️ WARNING: large queue — verify slow ring is running')
"

# 5.5 全量中文泄漏检查
python3 /home/abug/timesfm/scripts/check_pd_chinese.py
# EXIT 0: PASS

# 5.6 抽样 10 个手审
python3 -c "
import json, random
from pathlib import Path
from datetime import datetime

FM = Path('/home/abug/timesfm')
all_ps = list(FM.glob('task_FM/experiments/run_*/results/**/proposals/*.prescreen.json'))
now = datetime.now().timestamp()
recent = [p for p in all_ps if (now - p.stat().st_mtime) < 43200]
sample = random.sample(recent, min(10, len(recent)))
print(f'Sample {len(sample)} from this run:')
for p in sample:
    d = json.loads(p.read_text())
    print(f'  {p.stem}: status={d.get(\"status\")}, vid={d.get(\"variant_id\",\"?\")[:20]}')
"
```

---

## 6. 慢环接手

backfill 内置 `queue_enqueue()` → 成功 prescreen 的提案自动入队 `aligned_pending.jsonl`。

慢环消费链路：
```
aligned_pending.jsonl  →  aligned_slow_loop.py queue_claim()
  → 回测评估  →  append_verdict()  →  aligned_verdicts.jsonl
  →  write_proposal_status(verdicted)
```

**确保慢环运行**：
```bash
# 检查慢环是否在跑
pgrep -fa aligned_slow_loop || echo "NOT RUNNING"

# 如果未运行，通过 supervisor 启动
bash scripts/start_supervisor.sh
# 或单独启动慢环
python3 scripts/aligned_slow_loop.py
```

---

## 7. Pass/Fail 总门

| Phase | Gate | PASS | FAIL |
|-------|------|------|------|
| 0.1 | Laya 健康 | status=ok | 中止，排查 Laya |
| 0.4 | 积压数 | 6000-6150 | 偏差 >10% → 检查 |
| 1 | 干跑 | ≈ 6075 | 偏差 → 重扫 |
| 2 | 试点 | success>0, error<10% | 调查 |
| 2.5 | 质量门禁 | 0 中文泄漏, status 合法, vid 格式 | STOP |
| 3 | 全量 | 日志 "完成:" | 从 state 续跑 |
| 3.5 | 监控 | state 15min 内更新 | 查 hang |
| 4.2 | 错误率 | < 5% | >10% → 拒绝 |
| 4.5 | 中文检查 | EXIT 0 | 标记受影响提案 |

---

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Laya 服务中断 | state 文件断点续跑，重启自动恢复 |
| 超时（默认 30min） | `--timeout-min 720` |
| 静默 hang | 看门狗监控 state 文件 mtime |
| 中文泄漏回归 | Phase 2.5 + 4.5 双重检查 |
| 磁盘满 | Phase 0 预检（需 ~15MB） |
| 队列积压过深 | Phase 4 检查 queue depth，确认慢环在跑 |

---

## 9. 关键参数

| 参数 | 值 | 理由 |
|------|---|------|
| `--workers` | 2 | CPU-bound Laya，多 worker 无加速 |
| `--timeout-min` | 720 | 9.3h × 1.2 余量 |
| 试点批量 | 100 | 10 太少，冷启动主导计时 |
| LAYA_BASE_URL | http://100.96.19.116:8000 | 10.1.1.67 不可达 |
