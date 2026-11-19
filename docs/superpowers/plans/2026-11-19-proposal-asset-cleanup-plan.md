# 提案资产清洗实施计划 v3（最终修订版）

> **日期**：2026-11-19  
> **依据规范**：`docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md`（v4 执行基线）  
> **审计基线**：commit `7a5877d`  
> **状态**：v3 — 最终修订版，待执行

---

## 〇、时间线分离

| 阶段 | 内容 | 预计耗时 | 触碰生产数据 |
|------|------|---------|------------|
| **A. 实现与测试** | Task 1-7：编写脚本 + 27 项测试 | ~3.5 小时 | **否** |
| **B. 预生产验证** | Task 8-9：版本锁定 + 开发环境 dry-run | ~15 分钟 | 只读 |
| **C. 生产停机窗口** | Task 10-19：停机 → 最终 dry-run → 清洗 → 验收 | ~45-75 分钟 | **是** |
| **D. 收尾** | Task 20-21：文档 + changelog | ~15 分钟 | 否 |

**总耗时**：开发 3.5h + 停机 45-75min + 收尾 15min ≈ **5-5.5 小时**

---

## A. 实现与测试阶段（不触碰生产数据）

### Task 1：前置核实 + 版本锁定

**交付物**：
- `--verify` 子命令 + 5 项硬门禁
- `verify_spec_version()` — 真实 commit 校验（无 `or True`）

**版本锁定逻辑（v3 修正）**：

```python
def verify_spec_version():
    spec_path = "docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md"
    baseline_commit = "7a5877d"
    
    # 1. 确认 baseline 是当前 HEAD 的祖先
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline_commit, "HEAD"],
        capture_output=True
    )
    assert result.returncode == 0, (
        f"Baseline {baseline_commit} is not an ancestor of HEAD. "
        f"Spec v4 was written against {baseline_commit}."
    )
    
    # 2. 记录版本信息（写入 manifest）
    current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode()
    spec_hash = sha256_file(spec_path)
    script_hash = sha256_file(__file__)
    
    return {
        "baseline_commit": baseline_commit,
        "current_commit": current_commit,
        "spec_version": "v4",
        "spec_sha256": spec_hash,
        "script_sha256": script_hash,
        "baseline_is_ancestor": True,
    }
```

**Git 工作区门禁（v3 新增）**：

```python
def verify_clean_working_tree():
    """关键代码和 spec 的修改已提交"""
    status = subprocess.check_output(["git", "status", "--short"]).decode()
    # 允许未跟踪文件（.omc/ 等），但 spec/脚本/config 路径必须干净
    critical_paths = ["scripts/", "docs/superpowers/specs/", "task_FM/config/"]
    for line in status.strip().split("\n"):
        if not line.strip():
            continue
        filepath = line[3:].strip()
        for cp in critical_paths:
            if filepath.startswith(cp):
                raise RuntimeError(
                    f"Uncommitted change in critical path: {filepath}. "
                    f"Commit or stash before cleanup."
                )
```

**验收**：`test_verify_*`（5 项核实 + 版本锁定 + 工作区门禁）

**预计耗时**：30 分钟

---

### Task 2：SessionManager + manifest

**交付物**：
- `SessionManager` 类（增量 manifest + 原始备份 + 阶段记录）
- 初始 manifest 结构（含 verification + version_info）

**registry 备份时机（v3 修正）**：

会话目录可提前创建，但**权威 registry 备份推迟到停机后**（Step 13）。Task 2 只创建骨架 manifest：

```json
{
  "session_id": "...",
  "status": "initialized",
  "registry_backup": null,
  "execution_plan": null
}
```

停机后由 Step 13 填充 `registry_backup` 和 `execution_plan`。

**验收**：`test_session_id_is_used_by_all_phases`, `test_manifest_is_written_incrementally`

**预计耗时**：25 分钟

---

### Task 3：P0 归档逻辑

**归档集合定义（v3 修正集合代数）**：

```python
def compute_archive_set(all_runs, state, pending_refs, keep_n=10):
    # 第一步：计算保留集合（mtime ∪ run_id 并集）
    recent_by_mtime = set(sorted(all_runs, key=mtimes)[-keep_n:])
    recent_by_id = set(sorted(all_runs, key=run_id_ts)[-keep_n:])
    protected_recent = recent_by_mtime | recent_by_id  # 最多 20 个
    
    # 第二步：从非近期 run 中计算保护豁免
    base_candidates = set(all_runs) - protected_recent
    
    protected_exemptions = {}  # run_id → [reasons]
    for run in base_candidates:
        reasons = []
        if run.name == state.get("last_run_id"):
            reasons.append("active_run")
        if has_inprogress_checkpoint(run):
            reasons.append("inprogress_checkpoint")
        if run.name in pending_refs:
            reasons.append("pending_queue_ref")
        if not is_harvested(run.name, state.get("last_harvested_run_id")):
            reasons.append("unharvested")
        if reasons:
            protected_exemptions[run.name] = reasons
    
    # 第三步：最终归档集合
    archive_set = base_candidates - set(protected_exemptions.keys())
    
    # K = 受保护豁免 run 数量（不含已在 protected_recent 中的）
    K = len(protected_exemptions)
    
    return {
        "recent_by_mtime": [r.name for r in recent_by_mtime],
        "recent_by_run_id": [r.name for r in recent_by_id],
        "protected_recent": [r.name for r in protected_recent],
        "protected_exemptions": protected_exemptions,  # {run_id: [reasons]}
        "archive_candidates": [r.name for r in archive_set],
        "K": K,
        "total_retained": len(protected_recent) + K,
    }
```

**manifest 记录每个豁免 run 的具体原因**（v3 修正）。

**tar 校验标准（v3 强化）**：

```python
def archive_and_verify(run_dir, archive_path):
    """打包 + 完整校验"""
    run_id = run_dir.name
    original_size = dir_size(run_dir)
    
    # 1. 打包
    subprocess.run(["tar", "czf", str(archive_path), "-C", str(run_dir.parent), run_id], check=True)
    
    # 2. 非空
    assert archive_path.stat().st_size > 0
    
    # 3. tar 可读 + 条目数
    result = subprocess.run(["tar", "-tzf", str(archive_path)], capture_output=True, check=True)
    entries = result.stdout.decode().strip().split("\n")
    assert len(entries) > 0
    
    # 4. SHA-256
    archive_sha = sha256_file(archive_path)
    
    # 5. 幂等检查：若已存在相同 SHA 的归档，跳过
    # （再次运行时不重复打包/删除）
    
    # 6. 校验通过后才删除源目录
    shutil.rmtree(run_dir)
    
    # 7. 确认删除成功
    assert not run_dir.exists()
    
    return {
        "run_id": run_id,
        "archive_path": str(archive_path),
        "original_size_bytes": original_size,
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_file_count": len(entries),
        "archive_sha256": archive_sha,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "source_deleted": True,
    }
```

**验收**：8 项测试（含 `test_atomic_archive_no_source_loss`，v3 拆分）

**预计耗时**：45 分钟

---

### Task 4：P1 清理逻辑

**删除条件**（5 项必须全满足）：

1. JSON 可解析（不可解析 → quarantine）
2. `status ∈ {error, degraded}`（缺失 → 不删除）
3. 不属于当前活跃 run
4. 不被慢环 pending 队列引用
5. 文件 mtime 超过保护窗口（默认 24h）

**P0/P1 保护一致性（v3 新增）**：若某 run 因 pending/inprogress 被 P0 保护，P1 也不删除该 run 内的任何 prescreen 文件。

**结构化记录**：

```python
def compute_prescreen_delete_set(experiments_dir, active_run_id, pending_refs, p0_protected_runs, protect_hours=24):
    delete_list = []
    quarantine_list = []
    
    cutoff = time.time() - protect_hours * 3600
    
    for f in experiments_dir.rglob("*.prescreen.json"):
        run_id = extract_run_id(f)
        record = {"path": str(f), "run_id": run_id, "mtime": f.stat().st_mtime}
        
        # P0 保护一致性
        if run_id in p0_protected_runs:
            continue
        
        # JSON 可解析
        try:
            data = json.loads(f.read_text())
            record["status"] = data.get("status")
        except (json.JSONDecodeError, UnicodeDecodeError):
            quarantine_list.append({**record, "reason": "unparseable_json"})
            continue
        
        if data.get("status") not in ("error", "degraded"):
            continue
        if run_id == active_run_id:
            continue
        if run_id in pending_refs:
            continue
        if f.stat().st_mtime > cutoff:
            continue
        
        delete_list.append(record)
    
    return delete_list, quarantine_list
```

**P1 完整校验链（v3 新增 9 步）**：

```
1. 生成 NUL 分隔列表 + 结构化 JSON
2. 记录文件数量和总字节数
3. 创建 tar（相对路径，禁止绝对路径和 ..）
4. tar -tzf 校验可读
5. 比较 tar 内文件数 = 清单数量
6. 计算 SHA-256
7. 写入 manifest
8. xargs -0 rm 删除
9. 确认原路径不存在
```

**验收**：4 项测试（含 `test_p1_quarantines_unparseable_json`）

**预计耗时**：25 分钟

---

### Task 5：P2 fingerprint 修复

**交付物**：
- `execute_p2()` — 写入 TIMEOUT_NO_EVAL
- `verify_fingerprint_consumers()` — 兼容性检查（**仅报告，不修改**）

**行为级验证（v3 新增）**：

```python
def behavioral_verify_timeout_exclusion():
    """使用 fixture 验证统计隔离"""
    fixture = load_fixture("229_v4_verdicts_plus_22_timeout.jsonl")
    
    # 1. 统计样本数
    stats = compute_statistics(fixture)
    assert stats["sample_count"] == 229, "TIMEOUT_NO_EVAL leaked into statistics"
    
    # 2. 去重不包含 TIMEOUT_NO_EVAL
    dedup_result = run_dedup(fixture)
    assert not any(v["protocol_fingerprint"] == "TIMEOUT_NO_EVAL" for v in dedup_result)
    
    # 3. 协议相等性比较
    assert not fingerprint_equal("TIMEOUT_NO_EVAL", "TIMEOUT_NO_EVAL")
    
    # 4. 清洗前后 v4 统计一致
    pre_stats = compute_statistics(original_fixture)
    post_stats = compute_statistics(fixture)
    assert pre_stats == post_stats
```

**门禁**：静态检查 + 行为测试都通过才执行 `--fix-fingerprint`。

**验收**：3 项测试（含 `test_p2_blocks_when_consumers_incompatible`, `test_p2_behavioral_statistical_isolation`）

**预计耗时**：25 分钟

---

### Task 6：P3 prescreen metadata

**时区参数（显式，无默认）**：

```bash
--migration-cutoff "2026-10-17T00:00:00+00:00"  # 必须带时区
--naive-tz "Asia/Shanghai"                        # 必须显式传入
```

- 边界 `2026-10-17T00:00:00+00:00` 属于 **B 类**（`< cutoff` 为 A，`>= cutoff` 为 B）
- unknown → assert 中止，注册表完全未改变

**验收**：4 项测试

**预计耗时**：20 分钟

---

### Task 7：停机检查 + 回滚 + 集成测试

**停机检查（分类匹配）**：

```python
PROCESS_PATTERNS = [
    ("supervisor", r"python.*praxist_supervisor\.py"),
    ("praxist", r"praxist( |$)"),
    ("slow_loop", r"python.*aligned_slow_loop\.py"),
]
```

**回滚安全（v3 强化）**：

```python
def rollback(session_id, force=False):
    # 1. supervisor 必须已停止
    assert check_all_stopped() == []
    
    # 2. 原子恢复 registry（tempfile + fsync + os.replace）
    backup_path = manifest["registry_backup"]["path"]
    backup_sha = manifest["registry_backup"]["sha256"]
    assert sha256_file(backup_path) == backup_sha, "Backup corrupted"
    
    fd, tmp = tempfile.mkstemp(dir="task_FM/config", suffix=".tmp")
    with os.fdopen(fd, "wb") as out:
        with open(backup_path, "rb") as inp:
            shutil.copyfileobj(inp, out)
        os.fsync(fd)
    os.replace(tmp, "task_FM/config/aligned_verdicts.jsonl")
    
    # 3. 恢复 P0 归档的 run（tar 路径安全检查）
    for entry in manifest["phases"]["P0"]["archived_runs"]:
        if not entry.get("source_deleted"):
            continue  # tar 存在但源未删 → 只清归档
        
        target = Path(entry["original_path"])
        if target.exists() and not force:
            raise RuntimeError(f"Path exists: {target}. Use --force.")
        
        # tar 安全检查
        verify_tar_safety(entry["archive_path"])  # 禁止绝对路径和 ..
        tar_extract(entry["archive_path"], target)
    
    # 4. 恢复 P1 删除的 prescreen
    # （同 tar 安全检查 + 解压）
    
    # 5. 更新 manifest
    manifest["status"] = "rolled_back"
```

**tar 安全检查**：

```python
def verify_tar_safety(archive_path):
    members = subprocess.run(["tar", "-tzf", archive_path], capture_output=True, check=True)
    for m in members.stdout.decode().strip().split("\n"):
        assert not os.path.isabs(m), f"Absolute path in tar: {m}"
        assert ".." not in m.split("/"), f"Path traversal in tar: {m}"
        assert m.startswith("task_FM/"), f"Unexpected path prefix: {m}"
```

**失败状态拆分（v3 新增）**：

```
失败在重启前（Step 11-17）：
  停止清洗 → rollback → 静态验收 → 重启

失败在重启后（Step 18-19）：
  停止新启动的三环 → 保存新 cycle 状态快照
  → 若已有新 run/registry 写入 → 人工确认是否允许回滚
  → rollback → 验收 → 重启
```

**27 项测试完整清单**：

| # | 测试名 | 类别 |
|---|--------|------|
| 1 | `test_dry_run_no_changes` | 安全 |
| 2 | `test_preserves_active_run` | P0 |
| 3 | `test_preserves_recent_runs` | P0 |
| 4 | `test_preserves_inprogress` | P0 |
| 5 | `test_preserves_pending_queue_refs` | P0/P1 |
| 6 | `test_protected_runs_may_exceed_ten` | P0 边界 |
| 7 | `test_p0_uses_run_id_and_mtime_union` | P0 排序 |
| 8 | `test_p0_exempt_runs_have_reasons` | P0 审计 |
| 9 | `test_rollback_after_partial_p0` | 回滚 |
| 10 | `test_size_target_reports_overflow` | P0 出口 |
| 11 | `test_p1_preserves_valid_prescreen` | P1 |
| 12 | `test_p1_uses_null_delimited_paths` | P1 路径 |
| 13 | `test_p1_preserves_pending_queue_refs` | P1 |
| 14 | `test_p1_quarantines_unparseable_json` | P1 异常 |
| 15 | `test_p1_respects_p0_protection` | P1/P0 一致 |
| 16 | `test_p2_fingerprint_placeholder` | P2 |
| 17 | `test_timeout_placeholder_excluded_from_statistics` | P2 隔离 |
| 18 | `test_p2_blocks_when_consumers_incompatible` | P2 门禁 |
| 19 | `test_p2_behavioral_statistical_isolation` | P2 行为 |
| 20 | `test_p3_attribution_split` | P3 |
| 21 | `test_p3_rejects_unknown_timestamp` | P3 门禁 |
| 22 | `test_p3_handles_naive_timestamp` | P3 时区 |
| 23 | `test_p3_fails_on_invalid_config` | P3 门禁 |
| 24 | `test_session_id_used_by_all_phases` | 会话 |
| 25 | `test_manifest_incremental` | 会话 |
| 26 | `test_rollback_restores_registry` | 回滚 |
| 27 | `test_rollback_atomic_registry_write` | 回滚安全 |

**统一验收**：`pytest -q tests/test_cleanup_proposal_assets.py` → **27 passed**

**预计耗时**：45 分钟

---

## B. 预生产验证（只读）

### Task 8：版本锁定 + Git 工作区检查

```bash
python3 scripts/cleanup_proposal_assets.py --verify
git status --short  # 确认关键路径无未提交修改
```

### Task 9：开发环境 dry-run

```bash
python3 scripts/cleanup_proposal_assets.py \
    --session "test-$(date +%s)" \
    --phases P0 P1 P2 P3 \
    --migration-cutoff "2026-10-17T00:00:00+00:00" \
    --naive-tz "Asia/Shanghai" \
    --dry-run
```

**目的**：验证脚本行为正确，**不作为生产执行依据**（生产 dry-run 在停机后重做）。

---

## C. 生产停机窗口（串行）

```
Step 10：停止三环
  kill -TERM <supervisor_pid>
  轮询等待进程消失
  分类检查：supervisor / praxist / slow_loop 全部退出
  确认 flock 释放

Step 11：停机后状态快照（第一次）
  记录 supervisor_state.json 快照 + SHA-256
  记录 pending/inprogress 队列快照
  记录 experiments/ 目录清单 + mtime 快照
  sleep 5 → 再次记录 → 对比两次快照一致（无新文件/新队列）

Step 12：权威 registry 备份 + 执行计划生成（v3 修正时机）
  备份 aligned_verdicts.jsonl → task_FM/archive/<sid>/before-cleanup.jsonl
  计算 SHA-256 写入 manifest
  
  生成 execution_plan.json（不可变快照）：
  - P0 archive candidates + protected exemptions（含原因）
  - P1 delete set + quarantine set
  - P2/P3 修改计数预期
  - 队列/状态/目录的 SHA-256 哈希
  - 生成时间
  
  人工审查 execution_plan.json

Step 13：执行 P0
  python3 ... --session "$SID" --archive-runs --plan execution_plan.json
  脚本验证当前状态哈希 == execution_plan 中的哈希（不一致则拒绝执行）

Step 14：执行 P1
  python3 ... --session "$SID" --clean-prescreen

Step 15：执行 P2
  python3 ... --session "$SID" --fix-fingerprint

Step 16：执行 P3
  python3 ... --session "$SID" --fix-prescreen-metadata \
      --migration-cutoff "2026-10-17T00:00:00+00:00" --naive-tz "Asia/Shanghai"

Step 17：静态验收
  硬条件：
    - 所有不受保护的 run 均已归档
    - 未归档 run 均有明确保护原因（manifest 记录）
    - experiments 体积已记录
    - error/degraded prescreen = 0
    - MISSING fingerprint = 0
    - 缺失 prescreen metadata = 0
  目标条件：
    - experiments ≤ 250 MB（软目标）
    - 若未达成：manifest 记录受保护 run 大小及原因

Step 18：重启 supervisor
  bash scripts/start_supervisor.sh

Step 19：运行态验收
  确认 supervisor 存活
  首 cycle 日志无异常
  确认 harvest 正常
  manifest status → "completed"
```

---

## D. 收尾

### Task 20：文档更新
### Task 21：Changelog

---

## 出口条件优先级（v3 明确）

| 优先级 | 条件 | 类型 |
|--------|------|------|
| **P0 硬** | 所有不受保护的 run 均已归档 | 必须 |
| **P0 硬** | 未归档 run 均有 manifest 记录的保护原因 | 必须 |
| **P0 硬** | error/degraded prescreen = 0 | 必须 |
| **P0 硬** | MISSING fingerprint = 0 | 必须 |
| **P0 硬** | 缺失 prescreen metadata = 0 | 必须 |
| **P1 目标** | experiments ≤ 250 MB | 软目标 |
| **P1 目标** | 体积下降 ≥ 90% | 软目标 |

目标条件未达成时：manifest 记录受保护 run 列表、各自大小、未达成原因。**不阻塞执行。**

---

## 依赖图

```
Task 1 (核实+版本锁定+工作区检查)
  ↓
Task 2 (SessionManager)
  ↓
  ├── Task 3 (P0)  ──┐
  ├── Task 4 (P1)  ──┤  可并行开发
  ├── Task 5 (P2)  ──┤
  └── Task 6 (P3)  ──┘
         ↓
    Task 7 (集成测试 27 项 + 回滚)
         ↓
    Task 8-9 (预生产: verify + dry-run)
         ↓
    Task 10-19 (生产停机: 串行 10 步)
         ↓
    Task 20-21 (文档 + changelog)
```
