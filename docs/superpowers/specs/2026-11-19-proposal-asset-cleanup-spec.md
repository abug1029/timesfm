# 提案资产清洗规范（Proposal Asset Cleanup Spec）

> **状态**：v3（定稿执行版）  
> **创建日期**：2026-11-19  
> **v2 修订**：2026-11-19（空间测算、三环耦合、P2/P3 矛盾、工程脚本）  
> **v3 修订**：2026-11-19（代码可执行性、P0/P1 验收修正、前置核实补全、运维语义对齐）  
> **审计基线**：commit `7a5877d`  
> **配套报告**：`docs/superpowers/reports/2026-11-19-proposal-asset-management-audit.md`

---

## 一、问题陈述

`task_FM/experiments/` 目录累积 **683 个 run、11,952 个提案文件、4.9 GB 磁盘**，无自动清理机制。同时裁决注册表存在 22 条 `MISSING protocol_fingerprint` 和 75 条无 prescreen metadata 的卫生问题。

**目标**：在不影响收割/慢环/监督环功能的前提下，将 experiments 磁盘占用从 4.9 GB 降至 **250 MB 以内**，并修复注册表卫生问题。

---

## 二、清洗范围与优先级

| Phase | 目标 | 预估释放 | 风险 |
|-------|------|---------|------|
| **P0** | 归档已收割的旧 run（保留最近 10 个 + 受保护豁免 run） | ~4.7 GB（experiments 目录） | LOW→MEDIUM |
| **P1** | 清理剩余活跃 run 中 error/degraded 状态的 `.prescreen.json` | < 1 MB（P0 后仅剩数十个） | LOW |
| **P2** | 修复 22 条 MISSING fingerprint 裁决 | 0（卫生） | MEDIUM |
| **P3** | 补充 75 条无 prescreen metadata 裁决的标记 | 0（卫生） | LOW |
| **P4** | 建立长期清理策略（独立幂等脚本） | 持续 | LOW |

> **v3 说明**：P0 归档后 98.5% 的 prescreen 文件已随旧 run 移除，P1 仅处理剩余活跃 run 中的无效缓存，空间释放可忽略。P1 本质是卫生清理。

### 关于 WSL 虚拟磁盘膨胀

归档到 `task_FM/archive/` 仅改变目录分布，不释放 WSL2 `ext4.vhdx` 宿主空间。若需缓解虚拟磁盘膨胀，见 §八外部归档方案。

---

## 三、前置核实（§3.0，v3 扩展）

**在执行任何 Phase 之前，必须先完成以下全部核实并记录结果。任何一项未通过则暂停执行。**

### 核实 1：`harvest_proposals` 的去重状态持久化边界

```bash
grep -n 'dedup\|existing\|aligned_verdicts' scripts/sup_harvest.py
```

- 若去重依赖 `aligned_verdicts.jsonl`（持久化注册表）：归档旧 run 不影响去重
- 若去重依赖 `experiments/` 目录扫描：归档会导致历史被拒提案的去重记忆丢失，必须修正验收条件并导出已拒 variant_id 到持久化清单

### 核实 2：慢环 pending 队列的存储位置与路径引用

```bash
grep -n 'proposal_path\|run_dir\|experiment' scripts/aligned_slow_loop.py
```

- 若队列存储 proposal 文件的绝对路径：归档引用路径的 run 会导致 `FileNotFoundError`
- 若队列存储 proposal 内容（已序列化）：归档不影响

### 核实 3：`supervisor_state` 字段结构（v3 新增）

```bash
python3 -c "
import json
d = json.load(open('data/cache/supervisor_state.json'))
# 确认 last_harvested_run_id 存在且格式可比较
print('last_harvested_run_id:', d.get('last_harvested_run_id', 'MISSING'))
print('last_run_id:', d.get('last_run_id', 'MISSING'))
"
```

- 确认 `last_harvested_run_id` 字段存在
- 确认 run_id 格式支持时序比较（当前格式 `run_YYYY-MM-DD_HH-MM-SS_...` 可用 ISO 排序）

### 核实 4：注册表时间字段名与格式（v3 新增）

```bash
python3 -c "
import json
with open('task_FM/config/aligned_verdicts.jsonl') as f:
    d = json.loads(f.readline())
    # 检查时间戳字段名和格式
    for key in ['timestamp', 'evaluated_at', 'created_at', 'dt']:
        if key in d:
            print(f'{key}: {d[key]}')
"
```

- 确认时间字段名（`timestamp`? `evaluated_at`? 其他？）
- 确认格式是否带时区后缀（`Z`/`+08:00`/naive）
- 此结果直接影响 P3 的归因逻辑

### 核实 5：`TIMEOUT_NO_EVAL` 指纹下游兼容性（v3 新增）

```bash
# 静态排查所有消费 protocol_fingerprint 的代码
grep -rn 'protocol_fingerprint' scripts/ cascade/ --include='*.py' | grep -v '.pyc'
```

- 逐一检查消费方是否仅做 `if d.get("protocol_fingerprint"):` 非空判断
- 若是：`TIMEOUT_NO_EVAL` 会被当作有效指纹混入统计，必须在消费方增加显式排除
- 若消费方做精确匹配/哈希比较：`TIMEOUT_NO_EVAL` 不影响

> **核实 1 结果**：（待填写）  
> **核实 2 结果**：（待填写）  
> **核实 3 结果**：（待填写）  
> **核实 4 结果**：（待填写）  
> **核实 5 结果**：（待填写）

---

## 四、各 Phase 详细规范

### P0：旧 Run 归档

**判据**：满足以下**全部**条件的 run 目录可归档：

1. `run_id` 不在最近 10 个 run 之列（按 mtime 排序）
2. run 不是当前活跃 run（`supervisor_state.last_run_id`）
3. run 目录中无 `inprogress` 慢环 checkpoint
4. 慢环 pending 队列不引用该 run 下的任何提案路径
5. run 已完成收割（`last_harvested_run_id` 时序在该 run 之后）

> **v3 说明**：条件 3-5 可能保护超过 10 个 run（如第 12 近的 run 仍有 pending 提案）。此时保留目录数 = 10 + K（K = 受保护豁免 run 数量），出口条件相应放宽。

**归档目录结构（v3 统一会话 ID）**：

```
task_FM/archive/
├── .gitignore               # 忽略所有内容（防止 Git 污染）
└── 2026-11-19T17-00-00/     # 会话 ID 目录
    ├── manifest.json         # 原始路径映射
    ├── run_2026-09-15_*.tar.gz
    ├── run_2026-09-16_*.tar.gz
    ├── ...
    ├── aligned_verdicts.bak  # P2/P3 注册表备份
    └── prescreen_files.tar.gz # P1 prescreen 备份
```

**`manifest.json` 格式**：

```json
{
  "session_id": "2026-11-19T17-00-00",
  "created_at": "2026-11-19T17:00:00+08:00",
  "phases_executed": ["P0", "P1", "P2", "P3"],
  "files_archived": [
    {"original": "task_FM/experiments/run_2026-09-15_08-00-00_...", "archive": "run_2026-09-15_*.tar.gz"},
    ...
  ],
  "registry_backup": "aligned_verdicts.bak",
  "pre_cleanup_experiments_size": "4.9G",
  "pre_cleanup_run_count": 683
}
```

**原子打包（v3 修正 Shell 语法 + 空值保护）**：

```bash
#!/bin/bash
set -euo pipefail

SESSION_ID="2026-11-19T17-00-00"
ARCHIVE_DIR="task_FM/archive/$SESSION_ID"
mkdir -p "$ARCHIVE_DIR"

# 用数组避免引号陷阱（v3 修正）
mapfile -t RUN_LIST < <(find task_FM/experiments/ -maxdepth 1 -type d -name 'run_*' | sort | head -n -10)
# 或按判据过滤：此处简化为排除最近 10 个

for run_dir in "${RUN_LIST[@]}"; do
    run_id=$(basename "$run_dir")
    archive_path="$ARCHIVE_DIR/${run_id}.tar.gz"
    
    tar czf "$archive_path" -C "task_FM/experiments" "$run_id"
    
    # 校验打包成功且非空
    if [ ! -s "$archive_path" ]; then
        echo "FATAL: archive failed for $run_id" >&2
        exit 1
    fi
    
    rm -rf "$run_dir"
    echo "Archived: $run_id"
done
```

> **v3 修正**：用 `mapfile` + 数组 `"${RUN_LIST[@]}"` 替代 `"$RUN_LIST"` 双引号变量（后者会将全部路径合并为单个字符串）。

**`.gitignore` 核查**：

```bash
grep -q 'task_FM/archive' .gitignore || echo 'task_FM/archive/' >> .gitignore
```

### P1：Prescreen 文件清理（v3 修正策略）

**策略变更**：P0 已归档 98.5% 的 prescreen 文件。P1 仅处理剩余活跃 run 中的 **error/degraded 状态** prescreen 文件（v3 修正：不再全删，保护有效缓存）。

```bash
# 仅删除 error/degraded 状态的 prescreen 文件
# 先统计
find task_FM/experiments/ -name '*.prescreen.json' -exec \
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('status') in ('error','degraded') else 1)" {} \; -print | wc -l

# 打包备份（v3 空值保护：先检查是否有匹配文件）
PRESCREEN_LIST=$(mktemp)
find task_FM/experiments/ -name '*.prescreen.json' -exec \
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('status') in ('error','degraded') else 1)" {} \; -print > "$PRESCREEN_LIST"

if [ -s "$PRESCREEN_LIST" ]; then
    tar --null -czf "$ARCHIVE_DIR/prescreen_files.tar.gz" --files-from "$PRESCREEN_LIST"
    cat "$PRESCREEN_LIST" | xargs rm -f
    echo "Cleaned $(wc -l < "$PRESCREEN_LIST") prescreen files"
else
    echo "No error/degraded prescreen files found (idempotent)"
fi
rm -f "$PRESCREEN_LIST"
```

> **v3 修正**：① 仅删除 error/degraded 状态文件，保留有效 prescreen 缓存；② 打包前检查文件列表非空（避免 GNU tar 空包报错）；③ 与 P4 活跃保护规则一致。

**验收（v3 修正空间预期）**：
- 剩余有效 prescreen 文件数量 ≥ 0（不再要求 0 残留）
- error/degraded 状态文件 = 0
- `du -sh task_FM/experiments/` 不再做差值验收（P0 后 P1 空间变化 < 1 MB）

### P2：修复 MISSING fingerprint 裁决（v3 原子写入）

```python
#!/usr/bin/env python3
"""P2: 修复 22 条 MISSING protocol_fingerprint 裁决"""
import json
import shutil
import os
import tempfile

ARCHIVED_FP = "TIMEOUT_NO_EVAL"
ARCHIVED_AT = "2026-11-19"
REGISTRY = "task_FM/config/aligned_verdicts.jsonl"
SESSION_DIR = "task_FM/archive/2026-11-19T17-00-00"

# 1. 备份到会话目录（v3：不在 config/ 下生成备份文件）
backup_path = os.path.join(SESSION_DIR, "aligned_verdicts.bak_p2")
shutil.copy2(REGISTRY, backup_path)

# 2. 读取并修改
rows = []
fp_added = 0
with open(REGISTRY) as f:
    for line in f:
        d = json.loads(line)
        if not d.get("protocol_fingerprint"):
            d["protocol_fingerprint"] = ARCHIVED_FP
            d["archived_reason"] = "timeout_no_fingerprint"
            d["archived_at"] = ARCHIVED_AT
            fp_added += 1
        rows.append(d)

# 3. 原子写入（v3：临时文件 + fsync + rename）
fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(REGISTRY), suffix=".tmp")
try:
    with os.fdopen(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, REGISTRY)
except:
    os.unlink(tmp_path)
    raise

print(f"P2 complete: {fp_added} fingerprints patched")
```

> **v3 修正**：① `import shutil` 已补齐；② 备份写入 `SESSION_DIR` 而非 `config/`；③ 原子写入（tempfile + fsync + os.replace），中途异常不损坏注册表。

**验收**：
- `protocol_fingerprint` 缺失条目 = 0
- `TIMEOUT_NO_EVAL` 条目 = 22
- 核实 5 确认的下游消费方已兼容（或已修正排除 `TIMEOUT_NO_EVAL`）

### P3：补充 prescreen metadata 标记（v3 时区安全）

```python
#!/usr/bin/env python3
"""P3: 补充 75 条无 prescreen metadata 裁决的标记"""
import json
import os
import tempfile
from datetime import datetime, timezone

# 核实 4 结果：假设时间字段名为 timestamp（执行前必须确认）
TIME_FIELD = "timestamp"  # ← 核实 4 确认后填入实际字段名
MIGRATION_CUTOFF = datetime(2026, 10, 17, tzinfo=timezone.utc)

REGISTRY = "task_FM/config/aligned_verdicts.jsonl"
SESSION_DIR = "task_FM/archive/2026-11-19T17-00-00"

# 备份
import shutil
shutil.copy2(REGISTRY, os.path.join(SESSION_DIR, "aligned_verdicts.bak_p3"))

def parse_ts(ts_str):
    """安全解析时间戳，处理 naive/aware/各种格式（v3 修正）"""
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        # 尝试直接解析
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        # 若 naive，按系统时区（UTC+8）补齐
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt
    except (ValueError, TypeError):
        return None

rows = []
a_count = 0  # pre_laya_migration
b_count = 0  # service_down
with open(REGISTRY) as f:
    for line in f:
        d = json.loads(line)
        meta = d.setdefault("metadata", {})
        if "prescreen" not in meta:
            ts_raw = d.get(TIME_FIELD, "")
            eval_dt = parse_ts(ts_raw)
            
            if eval_dt is not None and eval_dt < MIGRATION_CUTOFF:
                meta["prescreen"] = {
                    "status": "unavailable",
                    "note": "pre_laya_migration_no_prescreen"
                }
                a_count += 1
            else:
                meta["prescreen"] = {
                    "status": "unavailable",
                    "note": "prescreen_service_down_at_evaluation_time"
                }
                b_count += 1
        rows.append(d)

# 原子写入
fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(REGISTRY), suffix=".tmp")
try:
    with os.fdopen(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, REGISTRY)
except:
    os.unlink(tmp_path)
    raise

print(f"P3 complete: A(pre-migration)={a_count}, B(service-down)={b_count}, total={a_count+b_count}")
assert a_count + b_count == 75, f"Expected 75, got {a_count + b_count}"
```

> **v3 修正**：① `parse_ts()` 独立处理 naive datetime（按 UTC+8 补齐），不再被 `except TypeError` 静默吞没；② 时间字段名从核实 4 获取（执行前填入）；③ 备份写入 `SESSION_DIR`；④ 原子写入；⑤ `assert` 校验总数 = 75。

### P4：长期清理策略（v3 独立脚本）

创建 `scripts/cleanup_proposal_assets.py`，统一 P0-P3 逻辑：

```
用法：
    python scripts/cleanup_proposal_assets.py --dry-run
    python scripts/cleanup_proposal_assets.py --session 2026-11-19T17-00-00 --archive-runs --keep 10
    python scripts/cleanup_proposal_assets.py --session 2026-11-19T17-00-00 --clean-prescreen
    python scripts/cleanup_proposal_assets.py --session 2026-11-19T17-00-00 --fix-registry
    python scripts/cleanup_proposal_assets.py --rollback 2026-11-19T17-00-00
```

**不修改 `praxist_supervisor.py`**。长期清理由宿主定期手动执行。

**安全约束**：
- 不清理仍在活跃 run 中的 prescreen 文件
- 不清理 error/degraded 以外的 prescreen 文件
- 每次执行前确认三环全进程已停止
- 所有操作记录到 `task_FM/archive/<session_id>/cleanup.log`

---

## 五、执行顺序（v3 修正）

```
1. 停止三环全部进程
   a. kill -TERM <supervisor_pid>
   b. 轮询等待进程消失：
      while kill -0 <supervisor_pid> 2>/dev/null; do sleep 2; done
      # v3 修正：不依赖 exit code，用 kill -0 轮询
   c. 检查监督环日志末尾确认正常退出：
      tail -5 data/cache/supervisor.out | grep -i 'exit\|shutdown\|signal'
   d. 确认无残留进程：
      pgrep -af 'praxist_supervisor|praxist|aligned_slow_loop' || echo "all clear"
      # 若有残留：逐个 kill -TERM，等待；仍残留则 kill -KILL
   e. 确认慢环 flock 释放：
      flock -n data/cache/aligned_slow_loop.lock echo "lock free"

2. 完成 §3.0 全部 5 项前置核实

3. 创建会话目录
   SESSION_ID=$(date +%Y-%m-%dT%H-%M-%S)
   mkdir -p task_FM/archive/$SESSION_ID

4. P0：归档旧 run

5. P1：清理 error/degraded prescreen 文件

6. P2：修复 MISSING fingerprint

7. P3：补充 prescreen metadata

8. 静态资产验收（重启前）
   - experiments 体积 ≤ 250 MB
   - run 目录数 ≤ 10 + K（K = 受保护豁免 run 数）
   - error/degraded prescreen = 0
   - MISSING fingerprint = 0
   - 缺失 prescreen metadata = 0

9. 重启三环
   a. bash scripts/start_supervisor.sh
   b. 等待 30 秒
   c. 运行态验收：
      pgrep -af praxist_supervisor  # 确认 supervisor 存活
      tail -20 data/cache/supervisor.out  # 检查首 cycle 日志

10. 写入 manifest.json
```

> **v3 修正**：① Step 1b 用 `kill -0` 轮询替代 `wait`（后台进程不可 wait）；② Step 8 仅含静态验收，运行态验收拆到 Step 9c；③ 出口条件中 run 目录数 = 10 + K。

---

## 六、出口条件（v3 修正）

| 条件 | 验收命令 |
|------|---------|
| experiments ≤ 250 MB | `du -sh task_FM/experiments/` |
| run 目录 ≤ 10 + K | `ls -d task_FM/experiments/run_*/ \| wc -l`（K = 核实 2 中受保护 run 数） |
| error/degraded prescreen = 0 | `find task_FM/experiments/ -name '*.prescreen.json' -exec python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('status') in ('error','degraded') else 1)" {} \\; -print \| wc -l` |
| MISSING fingerprint = 0 | `python3 -c 'import json; n=sum(1 for l in open("task_FM/config/aligned_verdicts.jsonl") if not json.loads(l).get("protocol_fingerprint")); print(n)'` |
| 缺失 prescreen metadata = 0 | `python3 -c 'import json; n=sum(1 for l in open("task_FM/config/aligned_verdicts.jsonl") if "prescreen" not in json.loads(l).get("metadata",{})); print(n)'` |
| harvest 功能正常 | supervisor 首 cycle 日志无异常 |
| supervisor 正常重启 | `pgrep -af praxist_supervisor` |

---

## 七、安全约束（v3 修正）

1. **所有删除操作先 dry-run**：`scripts/cleanup_proposal_assets.py --dry-run`
2. **safe_clean.sh 白名单保护**：`.omc/`、`data/cache/`、`.env*` 不可触碰。**`task_FM/config/` 除 P2/P3 对 `aligned_verdicts.jsonl` 执行受控原子更新外，其余文件严禁修改**（v3 修正：消除原文矛盾）
3. **归档而非删除**：所有归档到 `task_FM/archive/<session_id>/`（已加入 `.gitignore`）
4. **原子操作**：tar 校验后 rm；注册表用 tempfile + fsync + os.replace
5. **停机后执行**：全进程组停止后操作
6. **回滚**：`scripts/cleanup_proposal_assets.py --rollback <session_id>`，从 `task_FM/archive/<session_id>/manifest.json` 恢复
7. **不将 `task_FM/archive/` 提交到 Git**（`.gitignore` 保护）
8. **备份文件统一写入会话目录**，不在 `config/` 下生成 `.bak` 文件

---

## 八、外部归档方案（可选）

若需真正释放 WSL 虚拟磁盘空间：

```bash
# 方案 A：归档到宿主机挂载盘
EXTERNAL="/mnt/d/FlyBuddy/shared/timesfm-archive"
mkdir -p "$EXTERNAL"
# P0 打包时直接写入外部路径
# 或打包后 mv 过去

# 方案 B：WSL 虚拟磁盘压缩（宿主 Windows PowerShell 管理员）
# Optimize-VHD -Path "C:\...\ext4.vhdx" -Mode Full
```

---

## 九、跟进项（清洗之外的技术债）

| # | 跟进项 | 关联 |
|---|--------|------|
| 1 | 慢环超时异常处理兜底写入 `protocol_fingerprint` | P2 根因修复 |
| 2 | jd/sr 的 `aligned_max_points` 提升（600 → 800-1000）或品种独立上限 | R4 根因修复 |
| 3 | Laya 服务不可达时的可观测性告警 | R5 |
| 4 | 核实 5 中发现的下游消费方修正（若需要排除 TIMEOUT_NO_EVAL） | P2 配套 |

---

## 十、测试

`scripts/cleanup_proposal_assets.py` 需包含：

1. `test_dry_run_no_changes`：dry-run 模式不修改任何文件
2. `test_preserves_active_run`：当前活跃 run 不被归档
3. `test_preserves_recent_runs`：最近 10 个 run 不被归档
4. `test_preserves_inprogress`：有 inprogress checkpoint 的 run 不被归档
5. `test_preserves_pending_queue_refs`：慢环 pending 队列引用的 run 不被归档
6. `test_harvest_unchanged`：清洗后 harvest 对未归档 run 的增量输出一致
7. `test_rollback`：从 manifest.json 恢复后状态与清洗前一致
8. `test_p2_fingerprint_placeholder`：P2 后 0 MISSING + 22 TIMEOUT_NO_EVAL
9. `test_p3_attribution_split`：P3 后 A 类 + B 类归因正确且总数 = 75
10. `test_gitignore_archive`：`task_FM/archive/` 在 `.gitignore` 中
11. `test_p1_preserves_valid_prescreen`：P1 仅删 error/degraded，保留有效缓存（v3 新增）
12. `test_atomic_write_no_corruption`：写入中断后注册表不损坏（v3 新增）
