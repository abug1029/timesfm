# Laya 积压预处理 + 慢环接手 — 实施计划（v2）

> **日期**: 2026-10-19
> **审核**: Critic (Opus) + plan audit → 修订后通过
> **状态**: pending approval
> **修订记录**: v2 消化 plan audit 全部 P0 + P1（`--max` 显式传参、中文门禁改用 `check_pd_chinese.py`、PID 赋值、错误率脚本修复、pending 口径统一、variant_id 查 queue 行、坏批次回滚）

---

## 0. 现状与口径

| 项 | 值 |
|----|---|
| Laya 端点 | `http://100.96.19.116:8000`（Tailscale 备用 IP） |
| 延迟 | Connect 1.88s / TTFB 2.26s |
| 脚本 | `scripts/backfill_prescreen.py` v2.1.0（**`--max` 默认 500**） |
| 扫描范围 | `task_FM/experiments/run_*/results/**/proposals/*.json`（排除 `.prescreen.json`） |
| 提案总数 | 7389 |
| 已有 `.prescreen.json` | 1314 |
| 无 prescreen 文件 | 6075 |
| `should_skip` 口径 | 仅 `status=="success"` 跳过（694 个）；degraded(71) + error(549) 会**重试** |
| **真实待处理** | **无文件(6075) + 重试(620) − state processed(51) ≈ 6644** |
| 实测单提案耗时 | ~11s（Oct 18 数据：50 个/551s） |
| Workers=2 预估 | **~10 小时**（6644 × 11s ÷ 2 = ~10.2h） |

**Pending 口径统一**：脚本 `should_skip` 仅跳过 `status=="success"`，degraded/error 会重试。实际处理量 > 无文件数。本计划以「处理全部无文件 + 重试非 success」为目标，`--max 20000` 确保不截断。

### 数据流

```
backfill_prescreen.py
  → Laya prescreen (HTTP POST /v1/systemone)
  → 写 .prescreen.json（字段：status, variant_id, symbol, mechanism_plausibility, ...）
  → queue_enqueue() → aligned_pending.jsonl（成功入队）

aligned_slow_loop.py
  → queue_claim() 从 aligned_pending.jsonl 取行
  → 回测评估 → append_verdict() → aligned_verdicts.jsonl
  → write_proposal_status(verdicted)
```

### 已知缺口（residual）

| 项 | 说明 | 影响 |
|----|------|------|
| backfill queue 行缺 `proposal_id`/`version` | `queue_row` 无 lifecycle 字段 | 慢环 withdrawn 检查对该行跳过（不崩溃），但撤回链失效 |
| workers=2 理由 | 限流保护 Laya（HTTP I/O bound，非 CPU bound） | 保守选择，脚本默认 5 |

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

# 1.3 磁盘空间
df -h /home/abug/timesfm | awk 'NR==2{print "Free: "$4}'
# PASS: > 1GB

# 1.4 积压确认（统一口径）
LAYA_BASE_URL=http://100.96.19.116:8000 python3 -c "
import glob, json
from pathlib import Path
FM = Path('/home/abug/timesfm')
all_p = [p for p in glob.glob(str(FM/'task_FM/experiments/run_*/results/**/proposals/*.json'), recursive=True) if not p.endswith('.prescreen.json')]
no_file = [p for p in all_p if not Path(p).with_suffix('.prescreen.json').exists()]
retry = 0
for p in all_p:
    pf = Path(p).with_suffix('.prescreen.json')
    if pf.exists():
        try:
            d = json.loads(pf.read_text())
            if d.get('status') in ('error', 'degraded'):
                retry += 1
        except: pass
state_processed = 0
sf = FM / 'data/cache/backfill_prescreen_state.json'
if sf.exists():
    state = json.loads(sf.read_text())
    state_processed = len(state.get('processed', []))
effective = len(no_file) + retry - state_processed
print(f'No-file: {len(no_file)}, Retry: {retry}, State-processed: {state_processed}')
print(f'Effective pending: {effective}')
"
# PASS: effective > 6000
```

---

## 2. Phase 1：干跑（1 分钟）

```bash
LAYA_BASE_URL=http://100.96.19.116:8000 python3 scripts/backfill_prescreen.py \
  --dry-run --skip-laya-check --max 20000
# PASS: 输出 "待处理: ~6600"（与 Phase 0 effective 一致 ±10%）
# FAIL: 偏差 >10% → 检查 glob 匹配或 state 文件
```

---

## 3. Phase 2：试点批 100 个 — 校准（20 分钟）

```bash
# 3.1 跑 100 个（校准计时）
LOG_SUFFIX=$(date +%Y%m%d_%H%M%S)
LAYA_BASE_URL=http://100.96.19.116:8000 python3 scripts/backfill_prescreen.py \
  --max 100 --workers 2 --timeout-min 60 --skip-laya-check \
  2>&1 | tee logs/backfill_pilot_${LOG_SUFFIX}.log

# 3.2 计时校准
grep "elapsed=" logs/backfill_pilot_${LOG_SUFFIX}.log | tail -1
# per_proposal_s = elapsed / total_processed
# full_estimate_h = (effective_pending * per_proposal_s / 2) / 3600
```

### Phase 2.5：Laya 工作质量门禁

```bash
# 3.3 中文泄漏检查（对源 proposal 跑 check_pd_chinese.py）
# .prescreen.json 不含 predicted_direction，必须对源 JSON 跑 _build_state
python3 scripts/check_pd_chinese.py
# EXIT 0: PASS（0 violations）
# EXIT 1: FAIL → STOP，检查 Laya 模型版本

# 3.4 status 字段合法性（对试点新生成的文件）
python3 -c "
import json, os
from pathlib import Path
from collections import Counter

FM = Path('/home/abug/timesfm')
# 按 mtime 取最近 30 分钟生成的 prescreen 文件
now = os.path.getmtime('.')  # reference
files = []
for pf in FM.glob('task_FM/experiments/run_*/results/**/proposals/*.prescreen.json'):
    if now - pf.stat().st_mtime < 1800:  # 最近 30 min
        files.append(pf)

statuses = Counter()
for pf in files:
    data = json.loads(pf.read_text())
    statuses[data.get('status')] += 1

print(f'Recent prescreens: {len(files)}')
print(f'Status distribution: {dict(statuses)}')
invalid = {k: v for k, v in statuses.items() if k not in ('success', 'error', 'degraded')}
if invalid:
    print(f'INVALID statuses: {invalid}')
assert not invalid, f'Invalid statuses found: {invalid}'
"
# PASS: all in {success, error, degraded}

# 3.5 variant_id 格式（查 queue 新行，非 .prescreen.json 空字段）
python3 -c "
import json, re
from pathlib import Path

FM = Path('/home/abug/timesfm')
queue_path = FM / 'data/cache/aligned_pending.jsonl'
if not queue_path.exists():
    print('Queue empty — skip variant_id check')
    exit(0)

lines = queue_path.read_text().strip().split(chr(10))
# 取最近 100 行（本轮入队）
recent = lines[-100:] if len(lines) > 100 else lines
valid_re = re.compile(r'^[a-z0-9_]+$')
invalid = []
for l in recent:
    entry = json.loads(l)
    vid = entry.get('variant_id', '')
    if vid and not valid_re.match(vid):
        invalid.append(vid)

print(f'Checked {len(recent)} queue entries, invalid variant_ids: {len(invalid)}')
if invalid:
    print(f'Invalid: {invalid[:5]}')
assert len(invalid) == 0, f'Invalid variant_ids in queue'
"
# PASS: all variant_ids in queue match [a-z0-9_]+
```

**质量门禁总结**：

| 检查项 | PASS 条件 | FAIL 处理 |
|--------|----------|----------|
| 中文泄漏 | `check_pd_chinese.py` EXIT 0 | STOP，调查 Laya 模型 |
| status 合法 | 全部 ∈ {success, error, degraded} | >5% 非法 → STOP |
| variant_id 格式 | queue 行全部 ∈ [a-z0-9_]+ | >5% 非法 → STOP |

---

## 4. Phase 3：全量执行（~10 小时）

```bash
cd /home/abug/timesfm
LOG_SUFFIX=$(date +%Y%m%d_%H%M%S)

# 关键参数：--max 20000（确保不截断）+ --timeout-min 720（12h）
BACKFILL_PID=$!
LAYA_BASE_URL=http://100.96.19.116:8000 setsid nohup \
  python3 scripts/backfill_prescreen.py \
  --max 20000 \
  --workers 2 \
  --timeout-min 720 \
  --skip-laya-check \
  >> logs/backfill_${LOG_SUFFIX}.log 2>&1 &
BACKFILL_PID=$!
echo "PID: $BACKFILL_PID"
```

### Phase 3.5：运行监控

```bash
# 看门狗：每 5 分钟检查
LOG_FILE="logs/backfill_${LOG_SUFFIX}.log"
STATE_FILE="/home/abug/timesfm/data/cache/backfill_prescreen_state.json"

while kill -0 $BACKFILL_PID 2>/dev/null; do
  sleep 300
  STATE_AGE=$(( $(date +%s) - $(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0) ))
  PROGRESS=$(grep -oP '进度: \K\d+/\d+' "$LOG_FILE" 2>/dev/null | tail -1)
  echo "$(date +%H:%M) Progress: $PROGRESS | State age: ${STATE_AGE}s"

  if (( STATE_AGE > 900 )); then
    echo "WARNING: state file stale > 15 min — possible hang"
  fi

  RECENT_ERR=$(tail -50 "$LOG_FILE" | grep -c '\[ERROR\]' || true)
  if (( RECENT_ERR > 15 )); then
    echo "ALERT: $RECENT_ERR errors in last 50 lines"
  fi
done
echo "Backfill process exited"
```

---

## 5. Phase 4：后验证 + 质量评估（15 分钟）

```bash
LOG_FILE="logs/backfill_${LOG_SUFFIX}.log"

# 5.1 日志最终统计
grep "完成:" "$LOG_FILE" | tail -1
# 期望: total=N success=M failed=K enqueued=J degraded=D elapsed=Xs

# 5.2 错误率（修复 re.search TypeError）
grep "完成:" "$LOG_FILE" | tail -1 | python3 -c "
import sys, re
line = sys.stdin.read().strip()
m = re.search(r'success=(\d+).*?failed=(\d+)', line)
if m:
    s, f = int(m.group(1)), int(m.group(2))
    total = s + f
    rate = f/total*100 if total else 0
    print(f'Error rate: {rate:.1f}% ({f}/{total})')
    assert rate < 5, f'Error rate {rate:.1f}% exceeds 5%'
    print('PASS')
else:
    print('WARN: could not parse completion line')
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

# 5.4 队列深度
python3 -c "
from pathlib import Path
q = Path('/home/abug/timesfm/data/cache/aligned_pending.jsonl')
if q.exists():
    lines = [l for l in q.read_text().strip().split(chr(10)) if l.strip()]
    print(f'Queue depth: {len(lines)}')
    if len(lines) > 5000:
        print('WARNING: large queue — verify slow ring is running')
"

# 5.5 全量中文泄漏检查
python3 scripts/check_pd_chinese.py
# EXIT 0: PASS

# 5.6 抽样 10 个（按 mtime 取本次生成的）
python3 -c "
import json, random, os
from pathlib import Path

FM = Path('/home/abug/timesfm')
all_ps = list(FM.glob('task_FM/experiments/run_*/results/**/proposals/*.prescreen.json'))
now = os.path.getmtime('$LOG_FILE')
recent = [p for p in all_ps if abs(p.stat().st_mtime - now) < 43200]
sample = random.sample(recent, min(10, len(recent)))
print(f'Sample {len(sample)} from this run:')
for p in sample:
    d = json.loads(p.read_text())
    print(f'  {p.stem}: status={d.get(\"status\")}, vid={d.get(\"variant_id\",\"?\")[:20]}')
"
```

---

## 6. 慢环接手

backfill 内置 `queue_enqueue()` → 成功 prescreen 的提案自动入队 `aligned_pending.jsonl` → 慢环 `queue_claim()` 消费。

```bash
# 检查慢环是否在跑
pgrep -fa aligned_slow_loop || echo "NOT RUNNING — start with:"
# bash scripts/start_supervisor.sh
# 或: python3 scripts/aligned_slow_loop.py
```

### 慢环资产生命周期

```
aligned_pending.jsonl  →  queue_claim()  →  aligned_pending.inprogress.jsonl
  → 回测评估
  → append_verdict()  →  aligned_verdicts.jsonl（append-only）
  → queue_ack()  →  aligned_pending.done.jsonl（审计保留）
  → write_proposal_status(verdicted)  →  proposal_status.jsonl
  → materialize_known_verdicts()  →  known_verdicts.inc.md（peer prompt 用）
```

---

## 7. 坏批次回滚

如果全量跑发现质量问题（中文泄漏、大量错误等），需要从队列中剔除本次入队的行：

```bash
# 7.1 记录本次运行的时间窗
START_TS=$(date -d "2026-10-19 $(grep '开始:' logs/backfill_${LOG_SUFFIX}.log | head -1 | grep -oP '\d{2}:\d{2}:\d{2}')" +%s 2>/dev/null || echo 0)

# 7.2 从 aligned_pending.jsonl 中剔除本次入队行（按 _proposal_path 或时间戳）
python3 -c "
import json
from pathlib import Path

q = Path('/home/abug/timesfm/data/cache/aligned_pending.jsonl')
lines = q.read_text().strip().split(chr(10))
keep = []
removed = 0
for l in lines:
    entry = json.loads(l)
    # 按入队时间戳过滤（本次运行的 enqueued_at）
    ts = entry.get('enqueued_at', '')
    if ts >= '2026-10-19TXX':  # 替换为实际开始时间
        removed += 1
        continue
    keep.append(l)

print(f'Removed {removed} entries, keeping {len(keep)}')
q.write_text(chr(10).join(keep) + chr(10) if keep else '')
"

# 7.3 清除对应的 .prescreen.json（可选，仅当需要重跑时）
# find task_FM/experiments -name '*.prescreen.json' -newer logs/backfill_${LOG_SUFFIX}.log -delete
```

---

## 8. Pass/Fail 总门

| Phase | Gate | PASS | FAIL |
|-------|------|------|------|
| 0.1 | Laya 健康 | status=ok | 中止 |
| 0.4 | 积压数 | effective > 6000 | 检查口径 |
| 1 | 干跑 | ≈ effective（±10%） | 偏差 → 检查 |
| 2 | 试点 | success>0, error<10% | 调查 |
| 2.5 | 质量门禁 | 0 中文泄漏, status 合法, vid 格式 | STOP |
| 3 | 全量 | 日志 "完成:" | 从 state 续跑 |
| 3.5 | 监控 | state 15min 内更新 | 查 hang |
| 4.2 | 错误率 | < 5% | >10% → 拒绝 |
| 4.5 | 中文检查 | EXIT 0 | 标记受影响提案 |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Laya 服务中断 | state 断点续跑 |
| 超时 | `--timeout-min 720` |
| 静默 hang | 看门狗 state mtime |
| 中文泄漏 | Phase 2.5 + 4.5 双重 `check_pd_chinese.py` |
| 磁盘满 | Phase 0 预检（需 ~15MB） |
| 队列积压 | Phase 4 检查 depth，确认慢环运行 |
| `--max` 默认 500 截断 | **所有命令显式传 `--max 20000`** |
| 坏批次入队 | §7 回滚步骤 |
| queue 行缺 `proposal_id`/`version` | 已知缺口，慢环 withdrawn 检查跳过（不崩溃） |

---

## 10. 关键参数

| 参数 | 值 | 理由 |
|------|---|------|
| `--max` | **20000** | 默认 500 会截断；需 > pending(6644) |
| `--workers` | 2 | 限流保护 Laya（HTTP I/O，脚本默认 5） |
| `--timeout-min` | 720 | ~10h × 1.2 余量 |
| 试点批量 | 100 | 足够校准计时 |
| LAYA_BASE_URL | http://100.96.19.116:8000 | 10.1.1.67 不可达 |
