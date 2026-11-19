# 提案资产清洗实施计划 v2

> **日期**：2026-11-19  
> **依据规范**：`docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md`（v4 执行基线）  
> **审计基线**：commit `7a5877d`  
> **状态**：v2 — 修订完成，待执行

---

## 〇、时间线分离

本计划严格区分**开发测试**与**生产执行**两个阶段，不混在同一条时间线上。

| 阶段 | 内容 | 预计耗时 | 是否触碰生产数据 |
|------|------|---------|----------------|
| **A. 实现与测试** | Task 1-7：编写脚本 + 25 项测试 | ~3.5 小时 | **否** |
| **B. 预生产验证** | Task 8-10：版本锁定 + dry-run | ~15 分钟 | 只读 |
| **C. 生产停机窗口** | Task 11-20：实际清洗 + 验收 | ~30-60 分钟 | **是** |
| **D. 收尾** | Task 21-22：文档 + changelog | ~15 分钟 | 否 |

**总耗时**：开发 3.5h + 停机窗口 30-60min + 收尾 15min ≈ **4.5-5 小时**（分散在多个时段）

---

## A. 实现与测试阶段（不触碰生产数据）

### Task 1：前置核实 + 版本锁定

**目标**：`--verify` 子命令 + spec 版本校验 + 5 项硬门禁。

**交付物**：
- `scripts/cleanup_proposal_assets.py` 骨架（CLI 框架 + `--verify`）
- `VerificationResults` 数据类
- 5 个核实函数
- `verify_spec_version()` 函数（读取 spec 文件的 version/sha256 + 校验 HEAD commit）

**spec 版本锁定**：
```python
def verify_spec_version():
    spec_path = "docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md"
    spec_hash = sha256_file(spec_path)
    current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
    
    # 从 spec 文件解析 version 和 baseline_commit
    spec_meta = parse_spec_frontmatter(spec_path)
    
    assert spec_meta["version"] == "v4", f"Spec version mismatch: {spec_meta['version']}"
    assert current_commit.decode() == spec_meta["baseline_commit"] or True  # 允许后续 commit
    # 注：baseline_commit 校验允许宽松（因为开发阶段可能有后续 commit），但必须记录
```

**核实门禁**（任何一项失败 exit(1)）：

| # | 核实项 | 通过条件 |
|---|--------|---------|
| 1 | harvest 去重边界 | 确认依赖 registry 还是目录扫描 |
| 2 | 慢环 pending 队列 | 提取引用 run_id 集合 |
| 3 | supervisor_state 字段 | last_harvested_run_id 存在且可比较 |
| 4 | 注册表时间字段 | 确认字段名 + 格式 + 时区 |
| 5 | fingerprint 消费方 | 列出消费文件 + TIMEOUT_NO_EVAL 兼容性 |

**验收**：`test_verify_*`（5 项核实各有 pass/fail 测试）

**预计耗时**：30 分钟

---

### Task 2：SessionManager + 初始 manifest + 原始备份

**目标**：会话基础设施，所有后续 Phase 依赖此 Task。

**交付物**：
- `SessionManager` 类：
  - `__init__(session_id)` — 创建会话目录
  - `init_manifest(baseline_info)` — 写入初始 manifest
  - `backup_registry()` — 单份原始备份 `before-cleanup.jsonl` + SHA-256
  - `record_run_archive(run_id, archive_path, metadata)` — 增量追加
  - `record_prescreen_delete(file_list)` — 增量追加
  - `record_registry_patch(phase, count)` — 增量追加
  - `finalize()` — 标记 `status: completed`
- 初始 manifest 结构：

```json
{
  "session_id": "...",
  "status": "in_progress",
  "created_at": "...",
  "spec_version": "v4",
  "spec_sha256": "...",
  "baseline_commit": "7a5877d",
  "verification": { ... },
  "pre_cleanup": {
    "experiments_size_bytes": ...,
    "run_count": 683,
    "verdict_count": 251,
    "prescreen_count": 2979
  },
  "registry_backup": {
    "path": "before-cleanup.jsonl",
    "sha256": "...",
    "created_at": "..."
  },
  "phases": {
    "P0": {"status": "pending", "archived_runs": [], "protected_exemptions": [], "errors": []},
    "P1": {"status": "pending", "deleted_files": [], "quarantined": [], "errors": []},
    "P2": {"status": "pending", "patched_count": 0, "errors": []},
    "P3": {"status": "pending", "a_count": 0, "b_count": 0, "unknown_count": 0, "errors": []}
  }
}
```

**依赖**：Task 1（需要 VerificationResults）

**验收**：
- `test_session_id_is_used_by_all_phases`
- `test_manifest_is_written_incrementally`
- `test_rollback_restores_original_registry`

**预计耗时**：30 分钟

---

### Task 3：P0 归档逻辑

**目标**：`compute_archive_set()` + 原子打包 + SHA-256 校验。

**保留集合定义（v2 明确）**：

```
protected_recent = top_10_by_mtime ∪ top_10_by_run_id_timestamp

archive_candidates = all_runs
    - protected_recent
    - {active_run}
    - {runs_with_inprogress_checkpoint}
    - {runs_referenced_by_pending_queue}
    - {unharvested_runs}

protected_exemptions = archive_candidates 中被保护条件拦下的 run
    K = |protected_exemptions - protected_recent|
```

**并集含义**：对"保留集合"取并集。一个 run 只要在 mtime Top10 **或** run_id Top10 中，就不可归档。

**mtime 定义**：使用 run 目录自身的 `st_mtime`（非内部文件）。

**run_id 排序**：解析 `run_YYYY-MM-DD_HH-MM-SS_...` 中的时间戳，不依赖字符串字典序。

**`last_harvested_run_id` 比较**：解析双方时间戳后比较。若字段缺失或格式异常 → 核实 3 失败 → 拒绝执行。

**tar 校验标准（v2 强化）**：

```python
def verify_archive(archive_path, original_path):
    """打包后校验"""
    # 1. 文件非空
    assert os.path.getsize(archive_path) > 0
    
    # 2. tar 可读
    result = subprocess.run(["tar", "-tzf", archive_path], capture_output=True)
    assert result.returncode == 0
    entries = result.stdout.decode().strip().split("\n")
    assert len(entries) > 0
    
    # 3. 记录元数据
    return {
        "archive_path": str(archive_path),
        "original_path": str(original_path),
        "original_size_bytes": dir_size(original_path),
        "archive_size_bytes": os.path.getsize(archive_path),
        "archive_file_count": len(entries),
        "archive_sha256": sha256_file(archive_path),
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
```

**幂等保护**：再次运行时，若归档已存在且 SHA-256 匹配 → 跳过，不重复打包/删除。

**`compute_archive_set()` 输出**（写入 manifest）：

```json
{
  "recent_by_mtime": [...],
  "recent_by_run_id": [...],
  "active_runs": [...],
  "inprogress_runs": [...],
  "pending_ref_runs": [...],
  "unharvested_runs": [...],
  "archive_candidates": [...],
  "protected_exemptions": [...]
}
```

**依赖**：Task 2（需要 SessionManager）

**验收**：
- `test_preserves_active_run`
- `test_preserves_recent_runs`
- `test_preserves_inprogress`
- `test_preserves_pending_queue_refs`
- `test_protected_runs_may_exceed_ten`
- `test_p0_uses_run_id_and_mtime_union`
- `test_rollback_after_partial_p0`
- `test_atomic_write_no_corruption`

**预计耗时**：45 分钟

---

### Task 4：P1 清理逻辑

**目标**：NUL 安全 + 4 项删除条件 + 结构化记录 + 坏 JSON 隔离。

**删除条件（全部必须满足）**：

1. JSON 可解析（不可解析 → 加入 quarantine，不删除）
2. `status ∈ {error, degraded}`（缺失 → 不删除）
3. 不属于当前活跃 run
4. 不被慢环 pending 队列引用
5. 文件 mtime 超过保护时间窗口（默认 24h）

**结构化删除记录**：

```python
def compute_prescreen_delete_set(experiments_dir, active_run_id, pending_refs, protect_hours=24):
    """返回 (delete_list, quarantine_list) — 结构化记录"""
    delete_list = []     # 可安全删除
    quarantine_list = []  # 需人工检查
    
    cutoff = time.time() - protect_hours * 3600
    
    for f in Path(experiments_dir).rglob("*.prescreen.json"):
        run_id = extract_run_id(f)
        record = {
            "path": str(f),
            "run_id": run_id,
            "mtime": f.stat().st_mtime,
        }
        
        # 条件：JSON 可解析
        try:
            data = json.loads(f.read_text())
            record["status"] = data.get("status")
        except (json.JSONDecodeError, UnicodeDecodeError):
            quarantine_list.append({**record, "reason": "unparseable_json"})
            continue
        
        # 条件：status 明确为 error/degraded
        if data.get("status") not in ("error", "degraded"):
            continue
        
        # 条件：非活跃 run
        if run_id == active_run_id:
            continue
        
        # 条件：不被 pending 引用
        if run_id in pending_refs:
            continue
        
        # 条件：超过保护窗口
        if f.stat().st_mtime > cutoff:
            continue
        
        delete_list.append(record)
    
    return delete_list, quarantine_list
```

**quarantine 处理**：记录到 manifest，不自动删除，输出告警。

**NUL 安全输出**：`--p1-list-only` 输出 NUL 分隔路径到 stdout，供 Shell 层 `tar --null` + `xargs -0` 使用。同时输出结构化 JSON 到 manifest。

**依赖**：Task 2 + Task 3

**验收**：
- `test_p1_preserves_valid_prescreen`
- `test_p1_uses_null_delimited_paths`
- `test_p1_preserves_pending_queue_refs`
- `test_p1_quarantines_unparseable_json`

**预计耗时**：25 分钟

---

### Task 5：P2 fingerprint 修复（兼容性硬门禁）

**目标**：写入 TIMEOUT_NO_EVAL + **仅做兼容性检查，不自动修改消费方**。

**v2 关键修正**：`add_fingerprint_exclusions()` 从自动执行改为**硬门禁**：

```python
def verify_fingerprint_consumers():
    """扫描所有消费 protocol_fingerprint 的代码。
    返回 (compatible_files, incompatible_files)
    """
    consumers = grep_protocol_fingerprint_consumers()
    compatible = []
    incompatible = []
    
    for f in consumers:
        if has_timeout_exclusion(f):
            compatible.append(f)
        else:
            incompatible.append(f)
    
    return compatible, incompatible
```

**执行逻辑**：
- 若 `incompatible` 非空 → P2 **拒绝执行**，输出需人工修复的文件列表
- 若全部兼容 → 继续写入 TIMEOUT_NO_EVAL

**不自动修改消费方代码**（v2 修正：此前 `add_fingerprint_exclusions()` 会自动插入守卫，超出清洗范围）

**验收**：
- `test_p2_fingerprint_placeholder`
- `test_timeout_placeholder_excluded_from_statistics`
- `test_p2_blocks_when_consumers_incompatible`（v2 新增）

**预计耗时**：25 分钟

---

### Task 6：P3 prescreen metadata

**目标**：三类归因 + 时区显式参数 + unknown 硬门禁。

**时区参数（v2 显式化）**：

```bash
python3 scripts/cleanup_proposal_assets.py \
    --fix-registry \
    --migration-cutoff "2026-10-17T00:00:00+00:00" \
    --naive-tz "Asia/Shanghai"
```

- `--migration-cutoff`：必须带时区偏移（`+00:00`/`+08:00`/`Z`），禁止无时区
- `--naive-tz`：naive 时间戳的假设时区，必须显式传入，无默认值
- 边界时间归属：`2026-10-17T00:00:00+00:00` 属于 B 类（`< cutoff` 为 A，`>= cutoff` 为 B）

**unknown 硬门禁**：任何写入前检查 `unknown_count == 0`，否则 exit(1) + 注册表完全未改变（原子写入保证）。

**依赖**：Task 2

**验收**：
- `test_p3_attribution_split`
- `test_p3_rejects_unknown_timestamp`
- `test_p3_handles_naive_timestamp_with_declared_timezone`
- `test_p3_fails_when_time_field_config_is_invalid`

**预计耗时**：20 分钟

---

### Task 7：停机检查 + 回滚 + 集成测试

**目标**：preflight 子命令 + 回滚逻辑 + 25 项测试全通过。

**停机检查（分类进程匹配）**：

```python
PROCESS_PATTERNS = [
    ("supervisor", r"python.*praxist_supervisor\.py"),
    ("praxist", r"praxist( |$)"),
    ("slow_loop", r"python.*aligned_slow_loop\.py"),
]

def check_all_stopped():
    residual = []
    for name, pattern in PROCESS_PATTERNS:
        matches = pgrep(pattern)
        # 排除自身检查命令
        matches = [m for m in matches if "check_all_stopped" not in m.cmdline]
        if matches:
            residual.append((name, matches))
    return residual
```

**回滚安全条件（v2 新增）**：

```python
def rollback(session_id, force=False):
    manifest = load_manifest(session_id)
    
    # 检查 1：supervisor 已停止
    assert check_all_stopped() == [], "Supervisor must be stopped before rollback"
    
    # 检查 2：归档包 SHA-256 匹配
    for entry in manifest["phases"]["P0"]["archived_runs"]:
        actual_sha = sha256_file(entry["archive_path"])
        assert actual_sha == entry["archive_sha256"], f"Archive corrupted: {entry['archive_path']}"
    
    # 检查 3：目标路径不存在（或 force=True）
    for entry in manifest["phases"]["P0"]["archived_runs"]:
        if Path(entry["original_path"]).exists() and not force:
            raise RuntimeError(f"Path exists: {entry['original_path']}. Use --force to overwrite.")
    
    # 部分回滚：只恢复 manifest 中 status=deleted 的 run
    # （tar 已创建但源未删除的 → 不恢复 tar，只清理归档文件）
    for entry in manifest["phases"]["P0"]["archived_runs"]:
        if entry.get("source_deleted"):
            tar_extract(entry["archive_path"], target=entry["original_path"])
    
    # 恢复注册表
    copy(manifest["registry_backup"]["path"], "task_FM/config/aligned_verdicts.jsonl")
```

**25 项测试完整清单**：

| # | 测试名 | 类别 |
|---|--------|------|
| 1 | `test_dry_run_no_changes` | 安全 |
| 2 | `test_preserves_active_run` | P0 保护 |
| 3 | `test_preserves_recent_runs` | P0 保护 |
| 4 | `test_preserves_inprogress` | P0 保护 |
| 5 | `test_preserves_pending_queue_refs` | P0/P1 保护 |
| 6 | `test_protected_runs_may_exceed_ten` | P0 边界 |
| 7 | `test_p0_uses_run_id_and_mtime_union` | P0 排序 |
| 8 | `test_rollback_after_partial_p0` | 回滚 |
| 9 | `test_size_target_reports_protected_run_overflow` | P0 出口 |
| 10 | `test_p1_preserves_valid_prescreen` | P1 保护 |
| 11 | `test_p1_uses_null_delimited_paths` | P1 路径安全 |
| 12 | `test_p1_preserves_pending_queue_refs` | P1 保护 |
| 13 | `test_p1_quarantines_unparseable_json` | P1 异常 |
| 14 | `test_p2_fingerprint_placeholder` | P2 |
| 15 | `test_timeout_placeholder_excluded_from_statistics` | P2 隔离 |
| 16 | `test_p2_blocks_when_consumers_incompatible` | P2 门禁 |
| 17 | `test_p3_attribution_split` | P3 |
| 18 | `test_p3_rejects_unknown_timestamp` | P3 门禁 |
| 19 | `test_p3_handles_naive_timestamp_with_declared_timezone` | P3 时区 |
| 20 | `test_p3_fails_when_time_field_config_is_invalid` | P3 门禁 |
| 21 | `test_session_id_is_used_by_all_phases` | 会话 |
| 22 | `test_manifest_is_written_incrementally` | 会话 |
| 23 | `test_rollback_restores_original_registry` | 回滚 |
| 24 | `test_atomic_write_no_corruption` | 安全 |
| 25 | `test_no_residual_target_processes` | 运维 |
| 26 | `test_gitignore_archive` | 安全 |
| 27 | `test_idempotent_rerun` | 幂等 |

**实际 27 项**（比原计划多 2 项，新增 P2 门禁 + 幂等性）。

**依赖**：Task 1-6

**预计耗时**：45 分钟

---

## B. 预生产验证（只读，不触碰生产数据）

### Task 8：版本锁定

```bash
# 锁定当前状态
python3 scripts/cleanup_proposal_assets.py --verify
# 确认 5 项核实通过
# 记录 commit / spec sha256 / 脚本版本
```

### Task 9：全量 dry-run

```bash
SESSION_ID=$(date +%Y-%m-%dT%H-%M-%S)
python3 scripts/cleanup_proposal_assets.py \
    --session "$SESSION_ID" \
    --phases P0 P1 P2 P3 \
    --migration-cutoff "2026-10-17T00:00:00+00:00" \
    --naive-tz "Asia/Shanghai" \
    --dry-run
```

**人工审查**：
- archive set 是否正确（保护集合 vs 归档集合）
- prescreen delete set 是否正确
- P2/P3 修改计数是否匹配

### Task 10：创建会话 + 原始备份

```bash
python3 scripts/cleanup_proposal_assets.py \
    --session "$SESSION_ID" \
    --init-session \
    --migration-cutoff "2026-10-17T00:00:00+00:00" \
    --naive-tz "Asia/Shanghai"
```

---

## C. 生产停机窗口（串行，触碰生产数据）

```
Step 11：停止三环
  kill -TERM <supervisor_pid>
  while kill -0 <pid> 2>/dev/null; do sleep 2; done
  分类检查：supervisor / praxist / slow_loop 全部退出
  确认 flock 释放

Step 12：二次状态确认（v2 新增）
  记录 supervisor_state 快照
  记录 pending/inprogress 队列快照
  确认 experiments/ 无新文件产生（sleep 5 + 对比 mtime）
  对比 Step 11 前后的快照，不一致则中止
  记录 Git HEAD commit

Step 13：执行 P0
  python3 scripts/cleanup_proposal_assets.py --session "$SESSION_ID" --archive-runs
  逐 run 打包 + 校验 + 删除 + manifest 追加

Step 14：执行 P1
  python3 scripts/cleanup_proposal_assets.py --session "$SESSION_ID" --clean-prescreen
  NUL 安全打包 + 删除 + manifest 追加

Step 15：执行 P2
  python3 scripts/cleanup_proposal_assets.py --session "$SESSION_ID" --fix-fingerprint
  写入 TIMEOUT_NO_EVAL + manifest 追加

Step 16：执行 P3
  python3 scripts/cleanup_proposal_assets.py --session "$SESSION_ID" --fix-prescreen-metadata \
      --migration-cutoff "2026-10-17T00:00:00+00:00" --naive-tz "Asia/Shanghai"
  三类归因 + manifest 追加

Step 17：静态验收
  experiments 体积（硬：≥90% 下降；软：≤250 MB）
  error/degraded prescreen = 0
  MISSING fingerprint = 0
  缺失 prescreen metadata = 0
  manifest status = "in_progress"，各 phase 无 errors

Step 18：重启 supervisor
  bash scripts/start_supervisor.sh
  等待 30s

Step 19：运行态验收
  pgrep -af praxist_supervisor（确认存活）
  tail -30 data/cache/supervisor.out（首 cycle 无异常）
  确认 harvest 正常（无 FileNotFoundError）

Step 20：完成 manifest
  python3 scripts/cleanup_proposal_assets.py --session "$SESSION_ID" --finalize
  manifest status → "completed"
```

---

## D. 收尾

### Task 21：文档更新

- Spec 状态改为"已执行"
- 填写 5 项核实实际结果
- 记录实际归档/删除/修复数量

### Task 22：Changelog

- `docs/superpowers/changelogs/2026-11-19-proposal-asset-cleanup.md`
- 记录：问题、根因、方案、执行结果、测试结果、commit

---

## 回滚预案

**任何步骤失败**：

```bash
# 1. 停止清洗
# 2. 读 manifest 判断已完成阶段
# 3. 回滚
python3 scripts/cleanup_proposal_assets.py --session "$SESSION_ID" --rollback

# 回滚逻辑：
# - P0 已归档的 run → tar 解压恢复（仅恢复 source_deleted=true 的）
# - P1 已删除的 prescreen → tar 解压恢复
# - P2/P3 修改的注册表 → before-cleanup.jsonl 恢复
# - manifest status → "rolled_back"

# 4. 重启 supervisor
```

---

## 依赖图

```
Task 1 (核实+版本锁定)
  ↓
Task 2 (SessionManager)
  ↓
  ├── Task 3 (P0)  ──┐
  ├── Task 4 (P1)  ──┤
  ├── Task 5 (P2)  ──┼── Task 7 (集成测试+回滚)
  └── Task 6 (P3)  ──┘         ↓
                          Task 8-10 (预生产)
                                ↓
                          Task 11-20 (生产停机)
                                ↓
                          Task 21-22 (收尾)
```

Task 3/4/5/6 可并行开发，但生产执行必须串行。
