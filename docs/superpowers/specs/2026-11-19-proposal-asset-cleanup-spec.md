# 提案资产清洗规范 v4（执行基线）

> **状态**：v4 — 执行基线（代码修正 + 硬门禁 + 增量 manifest + NUL 安全路径）  
> **创建日期**：2026-11-19  
> **v4 修订**：2026-11-19（P2/P3 代码修复、P1 NUL 安全 + pending 保护、P0 完整判据、动态 SESSION_ID、增量 manifest、单份原始备份、核实硬门禁、进程分类检查、TIMEOUT_NO_EVAL 统计隔离、测试扩展至 25 项）  
> **审计基线**：commit `7a5877d`  
> **配套报告**：`docs/superpowers/reports/2026-11-19-proposal-asset-management-audit.md`  
> **实施计划**：`docs/superpowers/plans/2026-11-19-proposal-asset-cleanup-plan.md`

---

## 一、问题陈述

`task_FM/experiments/` 累积 683 run / 11,952 提案 / 4.9 GB，无清理机制。裁决注册表 22 条 MISSING fingerprint + 75 条无 prescreen metadata。

**目标**：experiments 降至 ≤250 MB（软目标，受保护豁免 run 可突破），注册表卫生归零。

---

## 二、核心设计原则（v4 新增）

1. **单一脚本**：所有 Phase 逻辑统一在 `scripts/cleanup_proposal_assets.py`，禁止手工 Shell 执行核心逻辑
2. **硬门禁**：5 项前置核实必须在脚本内通过 assert，未通过则拒绝执行
3. **增量 manifest**：会话开始时创建，每处理一个对象立即追加，支持部分失败后回滚
4. **单份原始备份**：会话开始时一次性备份 `aligned_verdicts.jsonl` → `before-cleanup.jsonl`，P2/P3 均基于此恢复
5. **NUL 安全路径**：所有文件列表使用 `\0` 分隔，禁止换行分隔
6. **动态 SESSION_ID**：所有阶段通过 `--session` 参数传入，禁止硬编码目录
7. **TIMEOUT_NO_EVAL 隔离**：占位指纹不得参与任何统计/去重/比较逻辑

---

## 三、前置核实（硬门禁）

**脚本启动时自动执行，任何一项未通过则 exit(1) 并输出原因。**

| # | 核实项 | 通过条件 | 失败处理 |
|---|--------|---------|---------|
| 1 | `harvest_proposals` 去重边界 | 确认去重依赖 `aligned_verdicts.jsonl` 还是 `experiments/` 目录扫描 | 若依赖目录扫描：导出已拒 variant_id 到持久化清单后再归档 |
| 2 | 慢环 pending 队列存储方式 | 确认队列是否持有 run 目录路径引用 | 若持有路径引用：提取引用集合，加入 P0/P1 保护列表 |
| 3 | `supervisor_state` 字段 | `last_harvested_run_id` 和 `last_run_id` 存在且格式可比较 | 打印字段结构，要求人工确认 |
| 4 | 注册表时间字段 | 确认时间字段名 + 格式 + 时区 | 若 naive：需人工确认源时区（UTC vs UTC+8），确认后写入配置 |
| 5 | `protocol_fingerprint` 下游消费方 | 列出所有消费文件 + 是否需排除 TIMEOUT_NO_EVAL | 若有消费方未排除：脚本自动在消费方添加 `!= "TIMEOUT_NO_EVAL"` 守卫 |

**脚本内置核实结果存储**：

```python
class VerificationResults:
    dedup_boundary: str  # "registry" or "directory_scan"
    pending_queue_refs: set[str]  # 被 pending 队列引用的 run_id 集合
    state_schema_ok: bool
    time_field: str  # 实际时间字段名
    time_zone: str  # "UTC" or "UTC+8" or "naive_assumed_utc8"
    fingerprint_consumers: list[str]  # 消费 protocol_fingerprint 的文件列表
    fingerprint_exclusions_added: list[str]  # 已添加排除守卫的文件
```

核实结果写入 `manifest.json` 的 `verification` 字段，作为审计线索。

---

## 四、会话目录与 manifest

### 4.1 会话 ID 生成

```bash
SESSION_ID=$(date +%Y-%m-%dT%H-%M-%S)
```

所有阶段通过 `--session "$SESSION_ID"` 传入，脚本内部不再硬编码任何日期。

### 4.2 会话目录结构

```
task_FM/archive/
├── .gitignore                          # 忽略全部内容
└── <session_id>/
    ├── manifest.json                   # 增量更新
    ├── before-cleanup.jsonl            # 注册表原始备份（唯一一份）
    ├── runs/
    │   ├── run_2026-09-15_*.tar.gz
    │   └── ...
    ├── prescreen/
    │   └── prescreen_error_degraded.tar.gz
    └── cleanup.log                     # 操作日志
```

### 4.3 manifest.json（增量更新）

```json
{
  "session_id": "2026-11-19T17-00-00",
  "status": "in_progress",
  "created_at": "2026-11-19T17:00:00+08:00",
  "verification": { ... },
  "pre_cleanup": {
    "experiments_size": "4.9G",
    "run_count": 683,
    "verdict_count": 251,
    "prescreen_count": 2979
  },
  "phases": {
    "P0": {
      "status": "completed",
      "archived_runs": ["run_2026-09-15_...", "..."],
      "protected_runs": ["run_2026-11-18_..."],
      "errors": []
    },
    "P1": {
      "status": "completed",
      "deleted_count": 42,
      "preserved_count": 3,
      "errors": []
    },
    "P2": {
      "status": "completed",
      "patched_count": 22,
      "errors": []
    },
    "P3": {
      "status": "completed",
      "a_count": 30,
      "b_count": 45,
      "unknown_count": 0,
      "errors": []
    }
  }
}
```

**增量更新逻辑**：每归档一个 run / 每删除一个 prescreen / 每修复一条裁决后立即 `json.dump` 到 manifest。部分失败时回滚脚本可读 manifest 恢复。

---

## 五、各 Phase 规范

### P0：旧 Run 归档

**完整判据**（所有条件均由 Python 脚本计算，禁止 Shell 简化）：

```python
def compute_archive_set(experiments_dir, state, pending_refs, keep_n=10):
    """返回 (archive_set, protected_set)"""
    all_runs = sorted(Path(experiments_dir).glob("run_*"), key=lambda p: p.stat().st_mtime)
    
    # 最近 N 个（按 mtime）
    recent = set(all_runs[-keep_n:])
    
    # 按 run_id 解析时间排序的最近 N 个（与 mtime 取并集）
    by_id = sorted(all_runs, key=lambda p: parse_run_id_ts(p.name))
    recent_by_id = set(by_id[-keep_n:])
    recent = recent | recent_by_id  # v4：取并集
    
    protected = set()
    archive_candidates = set(all_runs) - recent
    
    for run in archive_candidates:
        run_id = run.name
        
        # 条件 2：当前活跃 run
        if run_id == state.get("last_run_id"):
            protected.add(run); continue
        
        # 条件 3：inprogress checkpoint
        if has_inprogress_checkpoint(run):
            protected.add(run); continue
        
        # 条件 4：pending 队列引用
        if run_id in pending_refs:
            protected.add(run); continue
        
        # 条件 5：收割未完成
        if not is_harvested(run_id, state.get("last_harvested_run_id")):
            protected.add(run); continue
    
    return archive_candidates - protected, protected
```

**排序统一规则（v4）**：保留集合 = mtime 最近 N 个 **∪** run_id 时间最近 N 个。两者不一致时取并集，不静默选择。

**出口条件（v4 修正）**：
- experiments 体积 ≤ 250 MB（**软目标**）
- 若受保护豁免 run 导致超 250 MB：记录豁免列表 + 总大小 + 原因到 manifest，标记 `size_target_overflow: true`
- 归档后体积较基线下降 ≥ 90%（**硬目标**）
- 所有满足判据的 run 均已归档

### P1：Prescreen 文件清理

**删除条件（v4 四个必须同时满足）**：

1. 文件状态为 `error` 或 `degraded`
2. 不属于当前活跃 run
3. 不被慢环 pending 队列引用
4. 文件不在最近保护时间窗口内（默认 24h，可配置）

**NUL 安全实现（v4 修正）**：

```bash
# 由 Python 脚本生成 NUL 分隔的待删文件列表
python3 scripts/cleanup_proposal_assets.py --session "$SID" --p1-list-only > /tmp/p1_delete_list.0

# 打包备份
if [ -s /tmp/p1_delete_list.0 ]; then
    tar --null -czf "$ARCHIVE_DIR/prescreen/prescreen_error_degraded.tar.gz" \
        --null -T /tmp/p1_delete_list.0
    # NUL 安全删除
    xargs -0 -r rm -f < /tmp/p1_delete_list.0
else
    echo "No error/degraded prescreen files to clean (idempotent)"
fi
rm -f /tmp/p1_delete_list.0
```

### P2：修复 MISSING fingerprint

**方案（v4 统一）**：写入占位指纹 `TIMEOUT_NO_EVAL` + 归档标记。

```python
import json, os, tempfile, shutil

def execute_p2(registry_path, session_dir):
    # 单份原始备份在会话开始时已完成，此处不重复备份
    
    rows = []
    patched = 0
    with open(registry_path) as f:
        for line in f:
            d = json.loads(line)
            if not d.get("protocol_fingerprint"):
                d["protocol_fingerprint"] = "TIMEOUT_NO_EVAL"
                d["archived_reason"] = "timeout_no_fingerprint"
                d["archived_at"] = SESSION_ID
                patched += 1
            rows.append(d)
    
    atomic_write_jsonl(registry_path, rows)
    return patched
```

**TIMEOUT_NO_EVAL 统计隔离（v4 强制）**：

脚本在核实 5 阶段自动扫描所有消费 `protocol_fingerprint` 的代码，并在以下文件中添加排除守卫：

```python
# 自动添加的守卫模式：
if d.get("protocol_fingerprint") and d["protocol_fingerprint"] != "TIMEOUT_NO_EVAL":
    # 纳入统计
```

**验收**：
- MISSING fingerprint = 0
- TIMEOUT_NO_EVAL = 22
- 含 TIMEOUT_NO_EVAL 的统计测试确认 v4 指纹数量仍为 229
- 所有消费方已添加排除守卫

### P3：补充 prescreen metadata

```python
from datetime import datetime, timezone, timedelta

def execute_p3(registry_path, time_field, assumed_tz_offset_hours=8):
    """
    time_field: 从核实 4 获取的实际时间字段名
    assumed_tz_offset_hours: naive 时间戳假设的时区偏移（默认 +8）
    """
    MIGRATION_CUTOFF = datetime(2026, 10, 17, tzinfo=timezone.utc)
    assumed_tz = timezone(timedelta(hours=assumed_tz_offset_hours))
    
    rows = []
    a_count = b_count = unknown_count = 0
    
    with open(registry_path) as f:
        for line in f:
            d = json.loads(line)
            meta = d.setdefault("metadata", {})
            if "prescreen" not in meta:
                ts_raw = d.get(time_field, "")
                eval_dt = parse_ts_safe(ts_raw, assumed_tz)
                
                if eval_dt is None:
                    unknown_count += 1
                    meta["prescreen"] = {
                        "status": "unavailable",
                        "note": "timestamp_unparseable"
                    }
                elif eval_dt < MIGRATION_CUTOFF:
                    a_count += 1
                    meta["prescreen"] = {
                        "status": "unavailable",
                        "note": "pre_laya_migration_no_prescreen"
                    }
                else:
                    b_count += 1
                    meta["prescreen"] = {
                        "status": "unavailable",
                        "note": "prescreen_service_down_at_evaluation_time"
                    }
            rows.append(d)
    
    # 硬门禁：unknown 必须为 0，否则中止
    assert unknown_count == 0, (
        f"P3 found {unknown_count} records with unparseable timestamps. "
        f"Check time_field='{time_field}' and timezone assumption. "
        f"Fix data or adjust config before retrying."
    )
    assert a_count + b_count == 75, f"Expected 75, got {a_count + b_count}"
    
    atomic_write_jsonl(registry_path, rows)
    return a_count, b_count

def parse_ts_safe(ts_str, assumed_tz):
    """安全解析，返回 aware datetime 或 None"""
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=assumed_tz)
        return dt
    except (ValueError, TypeError):
        return None
```

---

## 六、执行顺序

```
1. 停止三环全进程（分类检查）
   a. kill -TERM <supervisor_pid>
   b. 轮询：while kill -0 <pid> 2>/dev/null; do sleep 2; done
   c. 分类检查残留（v4 修正）：
      check_stopped() {
          if pgrep -f -- "$1" | grep -v "grep\|check_stopped" > /dev/null; then
              echo "FATAL: residual process: $1" >&2
              return 1
          fi
      }
      check_stopped 'python.*praxist_supervisor\.py'
      check_stopped 'praxist( |$)'
      check_stopped 'python.*aligned_slow_loop\.py'
   d. 确认 flock 释放

2. 启动清洗脚本
   SESSION_ID=$(date +%Y-%m-%dT%H-%M-%S)
   python3 scripts/cleanup_proposal_assets.py \
       --session "$SESSION_ID" \
       --phases P0 P1 P2 P3 \
       --dry-run     # 先 dry-run

3. 确认 dry-run 输出无误后，去掉 --dry-run 执行

4. 静态资产验收（重启前）

5. 重启三环
   bash scripts/start_supervisor.sh

6. 运行态验收
```

---

## 七、出口条件

| 条件 | 类型 | 验收方式 |
|------|------|---------|
| 归档后体积下降 ≥ 90% | **硬** | `du -sh task_FM/experiments/` |
| experiments ≤ 250 MB | 软 | 受保护 run 可突破，记录到 manifest |
| error/degraded prescreen = 0 | **硬** | `find ... -name '*.prescreen.json'` + status 过滤 |
| MISSING fingerprint = 0 | **硬** | Python 脚本检查 |
| 缺失 prescreen metadata = 0 | **硬** | Python 脚本检查 |
| TIMEOUT_NO_EVAL 不参与统计 | **硬** | 测试 `test_timeout_placeholder_excluded_from_statistics` |
| 无残留目标进程 | **硬** | `check_stopped` 分类检查 |
| supervisor 正常重启 | **硬** | `pgrep -af praxist_supervisor` |
| manifest status = "completed" | **硬** | `python3 -c 'import json; ...'` |

---

## 八、回滚

```bash
python3 scripts/cleanup_proposal_assets.py --rollback <session_id>
```

**回滚逻辑**：
1. 读 manifest，检查 `status`
2. 若 `completed`：完整回滚（解压所有 tar + 恢复 `before-cleanup.jsonl`）
3. 若 `in_progress`：部分回滚（只恢复已记录的 archived_runs + 恢复注册表）
4. 回滚后标记 manifest `status: "rolled_back"`

---

## 九、测试（25 项）

```text
# 保护条件
test_dry_run_no_changes
test_preserves_active_run
test_preserves_recent_runs
test_preserves_inprogress
test_preserves_pending_queue_refs           # P0 + P1 共用
test_protected_runs_may_exceed_ten           # v4 新增
test_size_target_reports_protected_run_overflow  # v4 新增

# P0
test_harvest_unchanged
test_p0_uses_run_id_and_mtime_union
test_rollback_after_partial_p0              # v4 新增

# P1
test_p1_preserves_valid_prescreen
test_p1_uses_null_delimited_paths           # v4 新增
test_p1_preserves_pending_queue_refs        # v4 新增

# P2
test_p2_fingerprint_placeholder
test_timeout_placeholder_excluded_from_statistics  # v4 新增

# P3
test_p3_attribution_split
test_p3_rejects_unknown_timestamp           # v4 新增
test_p3_handles_naive_timestamp_with_declared_timezone  # v4 新增
test_p3_fails_when_time_field_config_is_invalid  # v4 新增

# 会话管理
test_session_id_is_used_by_all_phases       # v4 新增
test_manifest_is_written_incrementally      # v4 新增
test_rollback_restores_original_registry    # v4 新增

# 原子性
test_atomic_write_no_corruption

# 进程
test_no_residual_target_processes           # v4 新增

# Git
test_gitignore_archive
```

---

## 十、安全约束

1. **单一脚本入口**：所有操作通过 `cleanup_proposal_assets.py`，禁止手工 Shell
2. **硬门禁**：5 项核实 + P3 unknown_count=0 + TIMEOUT_NO_EVAL 排除测试
3. **原子写入**：tempfile + fsync + os.replace
4. **NUL 安全路径**：所有文件列表用 `\0` 分隔
5. **增量 manifest**：每操作一个对象立即持久化
6. **单份原始备份**：`before-cleanup.jsonl`，P2/P3 共享
7. **`.gitignore` 保护**：`task_FM/archive/` 不入 Git
8. **不修改核心调度代码**：`praxist_supervisor.py` 不动（TIMEOUT_NO_EVAL 排除守卫仅加在统计/比较入口）
9. **停机后执行**：分类检查全进程组停止
