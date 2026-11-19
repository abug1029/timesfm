# 提案资产清洗实施计划 v4（可执行版）

> **日期**：2026-11-19  
> **依据规范**：`docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md`（v4 执行基线）  
> **审计基线**：commit `7a5877d`  
> **状态**：v4 — 可执行版

---

## 〇、时间线

| 阶段 | 内容 | 耗时 | 触碰生产 |
|------|------|------|---------|
| **A. 实现与测试** | Task 1-7 | ~3.5h | 否 |
| **B. 预生产验证** | Task 8-9 | ~15min | 只读 |
| **C. 生产停机窗口** | Task 10-19 | ~45-75min | 是 |
| **D. 收尾** | Task 20-21 | ~15min | 否 |
| **总计** | | **~5-5.5h** | |

---

## A. 实现与测试

### Task 1：前置核实 + 版本锁定 + 工作区检查

**版本锁定（v4 修正：从 spec 文件实际解析）**：

```python
def verify_spec_version():
    spec_path = Path("docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md")
    content = spec_path.read_text()
    
    # 从 spec 正文解析版本（v4 spec 在标题行包含版本号）
    version_match = re.search(r'状态[：:]\s*v4', content)
    assert version_match, f"Spec version not v4 in {spec_path}"
    
    # baseline commit 校验
    baseline = "7a5877d"
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, "HEAD"],
        capture_output=True
    )
    assert result.returncode == 0, f"Baseline {baseline} not ancestor of HEAD"
    
    current = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode()
    
    return {
        "spec_version": "v4",
        "spec_sha256": sha256_file(spec_path),
        "script_sha256": sha256_file(__file__),
        "baseline_commit": baseline,
        "current_commit": current,
    }
```

**工作区门禁**：

```python
def verify_clean_working_tree():
    status = subprocess.check_output(["git", "status", "--short"]).decode()
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"]).decode()
    
    critical = ["scripts/", "docs/superpowers/specs/", "task_FM/config/"]
    for line in (status + staged).strip().split("\n"):
        if not line.strip():
            continue
        filepath = line.lstrip(" MADRCU").strip()
        if any(filepath.startswith(cp) for cp in critical):
            raise RuntimeError(f"Uncommitted change in critical path: {filepath}")
    
    # 记录完整快照用于生产前对比
    full_status = subprocess.check_output(["git", "status", "--short"]).decode()
    full_diff = subprocess.check_output(["git", "diff", "--binary"]).decode()
    return {"status_snapshot": full_status, "diff_snapshot": full_diff}
```

**预计耗时**：30 分钟

---

### Task 2：SessionManager

**会话初始化（v4 显式步骤）**：

```python
class SessionManager:
    def __init__(self, session_id):
        self.session_id = session_id
        self.archive_dir = Path(f"task_FM/archive/{session_id}")
        
        # 拒绝复用已完成的会话
        if self.archive_dir.exists():
            manifest = self._load_manifest()
            if manifest.get("status") == "completed":
                raise RuntimeError(f"Session {session_id} already completed")
    
    def init(self, version_info, verification):
        """创建会话骨架 + 初始 manifest"""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        (self.archive_dir / "runs").mkdir(exist_ok=True)
        (self.archive_dir / "prescreen").mkdir(exist_ok=True)
        
        manifest = {
            "session_id": self.session_id,
            "status": "initialized",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version_info": version_info,
            "verification": verification,
            "pre_cleanup": None,  # Step 12 填充
            "registry_backup": None,  # Step 13 填充
            "execution_plan": None,  # Step 14 填充
            "phases": {
                phase: {"status": "pending", "planned_count": 0,
                        "completed_count": 0, "failed_count": 0,
                        "items": [], "errors": []}
                for phase in ["P0", "P1", "P2", "P3"]
            }
        }
        self._write_manifest(manifest)
    
    def record_item(self, phase, item):
        """增量追加单个对象记录并立即落盘"""
        manifest = self._load_manifest()
        manifest["phases"][phase]["items"].append(item)
        self._write_manifest(manifest)
    
    def update_phase(self, phase, **kwargs):
        manifest = self._load_manifest()
        manifest["phases"][phase].update(kwargs)
        self._write_manifest(manifest)
    
    def finalize(self):
        manifest = self._load_manifest()
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._write_manifest(manifest)
```

**Phase/对象状态机（v4 新增）**：

```
Phase status: pending → running → completed | failed | rolled_back
Object status: planned → archived | deleted | verified | restored | failed
```

**预计耗时**：25 分钟

---

### Task 3：P0 归档逻辑

**归档包路径统一（v4 修正：方案 A — 相对 run 路径）**：

```python
# 打包：从 task_FM/experiments/ 目录打包 run_id
subprocess.run(
    ["tar", "czf", str(archive_path), "-C", "task_FM/experiments", run_id],
    check=True
)
# tar 成员格式：run_2026-09-15_.../...（不含 task_FM/ 前缀）
```

**回滚路径安全检查（v4 修正：与打包格式一致）**：

```python
def verify_tar_safety(archive_path, expected_run_id):
    """验证 tar 成员符合方案 A 约定"""
    members = subprocess.run(
        ["tar", "-tzf", str(archive_path)],
        capture_output=True, check=True
    ).stdout.decode().strip().split("\n")
    
    for m in members:
        assert not os.path.isabs(m), f"Absolute path: {m}"
        assert ".." not in m.split("/"), f"Path traversal: {m}"
        # 第一级目录必须是目标 run_id
        top_dir = m.split("/")[0]
        assert top_dir == expected_run_id, f"Unexpected top-level: {top_dir} != {expected_run_id}"
    
    # 回滚解压：
    # tar xzf archive_path -C task_FM/experiments
```

**幂等状态机（v4 修正：从注释升级为显式逻辑）**：

| 归档包 | 源目录 | manifest 记录 | 行为 |
|--------|--------|-------------|------|
| 不存在 | 存在 | 无 | 正常打包→校验→删除 |
| 存在,SHA 一致 | 存在 | planned(未删除) | 校验后删除源目录 |
| 存在,SHA 一致 | 不存在 | deleted | 跳过（已完成） |
| 存在,SHA 不一致 | 任意 | 任意 | **FATAL**：不覆盖，要求人工处理 |
| 不存在 | 不存在 | 有记录 | **FATAL**：归档丢失，要求人工恢复 |

```python
def archive_with_idempotency(run_dir, archive_path, manifest_entry=None):
    run_id = run_dir.name
    
    if archive_path.exists():
        existing_sha = sha256_file(archive_path)
        
        if manifest_entry and manifest_entry.get("archive_sha256") == existing_sha:
            # manifest 记录一致
            if not run_dir.exists():
                return "skip_already_done"  # 已完成
            elif not manifest_entry.get("source_deleted"):
                # tar 存在但源未删 → 校验后删除
                verify_archive(archive_path, expected_sha=existing_sha)
                shutil.rmtree(run_dir)
                return "completed_deferred_delete"
        
        # SHA 不一致 → 拒绝
        raise RuntimeError(
            f"Archive SHA mismatch for {run_id}: "
            f"existing={existing_sha}, expected={manifest_entry.get('archive_sha256', 'N/A')}"
        )
    
    if not run_dir.exists():
        raise RuntimeError(f"Source missing for {run_id}, no archive exists")
    
    # 正常流程：打包→校验→删除
    return archive_and_verify(run_dir, archive_path)
```

**排序稳定性（v4 修正）**：

```python
# mtime 排序：使用 (mtime, run_id_ts) 双键保证稳定
recent_by_mtime = sorted(
    all_runs,
    key=lambda r: (r.stat().st_mtime, parse_run_id_ts(r.name))
)[-keep_n:]

# run_id 排序
recent_by_id = sorted(
    all_runs,
    key=lambda r: parse_run_id_ts(r.name)
)[-keep_n:]

# 保留集合 = 并集
protected_recent = set(recent_by_mtime) | set(recent_by_id)

# manifest 输出排序列表（非 set，保证可复现）
manifest_data["recent_by_mtime"] = sorted(r.name for r in recent_by_mtime)
manifest_data["recent_by_run_id"] = sorted(r.name for r in recent_by_id)
```

**P0 集合代数（v4 修正）**：

```python
# 第一步：保留集合
protected_recent = set(recent_by_mtime) | set(recent_by_id)

# 第二步：基础候选 = 全部 - 保留集合
base_candidates = set(all_runs) - protected_recent

# 第三步：保护豁免（遍历基础候选）
protected_exemptions = {}
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

# 第四步：最终归档集合
archive_set = base_candidates - set(protected_exemptions.keys())

# 统一保留集合（供 P1 使用）
retained_runs = protected_recent | set(protected_exemptions.keys())
K = len(protected_exemptions)
```

**预计耗时**：45 分钟

---

### Task 4：P1 清理逻辑

**P1 使用统一 retained_runs（v4 修正）**：

```python
def compute_prescreen_delete_set(experiments_dir, retained_runs, pending_refs, protect_hours=24):
    """
    retained_runs = protected_recent ∪ protected_exemptions（来自 P0 的 compute_archive_set 输出）
    P0 与 P1 使用同一套保留集合，生命周期边界一致。
    """
```

**P1 tar 打包统一路径基准（v4 修正）**：

```bash
# 从项目根目录打包，使用 task_FM/experiments/ 相对路径
# NUL 列表中的路径格式：task_FM/experiments/run_xxx/results/.../file.prescreen.json
tar --null -czf "$ARCHIVE_DIR/prescreen/prescreen.tar.gz" \
    -C . --null -T "$NUL_LIST"
# tar 成员格式：task_FM/experiments/...（含完整相对路径）
# 回滚：tar xzf ... -C .
```

**P1 完整 9 步校验**：

```python
def clean_prescreen(delete_list, archive_dir):
    # 1. 生成 NUL 列表
    nul_list = "\0".join(item["path"] for item in delete_list)
    
    # 2. 记录数量和总字节
    total_bytes = sum(item.get("size_bytes", 0) for item in delete_list)
    
    # 3. 创建 tar（相对路径，从项目根）
    archive_path = archive_dir / "prescreen" / "prescreen.tar.gz"
    write_nul_file(delete_list, "/tmp/p1_delete.0")
    subprocess.run(
        ["tar", "--null", "-czf", str(archive_path), "-C", ".", "--null", "-T", "/tmp/p1_delete.0"],
        check=True
    )
    
    # 4. tar 可读
    result = subprocess.run(["tar", "-tzf", str(archive_path)], capture_output=True, check=True)
    tar_entries = result.stdout.decode().strip().split("\n")
    
    # 5. 文件数比对
    assert len(tar_entries) == len(delete_list), \
        f"Tar entries ({len(tar_entries)}) != delete list ({len(delete_list)})"
    
    # 6. SHA-256
    archive_sha = sha256_file(archive_path)
    
    # 7. 写入 manifest
    session.record_item("P1", {
        "archive_path": str(archive_path),
        "file_count": len(delete_list),
        "total_bytes": total_bytes,
        "archive_sha256": archive_sha,
    })
    
    # 8. 删除
    subprocess.run(["xargs", "-0", "-r", "rm", "-f"], input=nul_list.encode(), check=True)
    
    # 9. 确认删除
    for item in delete_list:
        assert not Path(item["path"]).exists(), f"Still exists: {item['path']}"
```

**预计耗时**：25 分钟

---

### Task 5：P2 fingerprint 修复

**指纹比较语义（v4 修正）**：

```python
TIMEOUT_PLACEHOLDER = "TIMEOUT_NO_EVAL"

def is_comparable_fingerprint(fp):
    """判断指纹是否可参与统计/去重/比较"""
    return bool(fp) and fp != TIMEOUT_PLACEHOLDER

def fingerprint_equal(a, b):
    """两个指纹是否相等（仅可比较的指纹才相等）"""
    if not is_comparable_fingerprint(a) or not is_comparable_fingerprint(b):
        return False
    return a == b
```

**测试修正**：

```python
# 正确语义：
assert is_comparable_fingerprint("f02b2a43")
assert not is_comparable_fingerprint("TIMEOUT_NO_EVAL")
assert not is_comparable_fingerprint("")
assert not is_comparable_fingerprint(None)

# fingerprint_equal 不满足自反性对于 TIMEOUT_NO_EVAL（因为不可比较）：
assert fingerprint_equal("f02b2a43", "f02b2a43")  # 真实指纹自反
assert not fingerprint_equal("TIMEOUT_NO_EVAL", "TIMEOUT_NO_EVAL")  # 不可比较
assert not fingerprint_equal("TIMEOUT_NO_EVAL", "f02b2a43")  # 混合

# 统计隔离：
assert stats["v4_count"] == 229
assert stats["timeout_count"] == 22
assert stats["total"] == 251
assert "TIMEOUT_NO_EVAL" not in stats["unique_fingerprints"]
```

**行为级验证**（fixture 测试）：

```python
def test_p2_behavioral_statistical_isolation():
    fixture = create_fixture(v4_count=229, timeout_count=22)
    
    # 统计样本数 = 229（不含 TIMEOUT）
    stats = compute_statistics(fixture)
    assert stats["sample_count"] == 229
    
    # 去重结果不含 TIMEOUT
    dedup = run_dedup(fixture)
    assert all(is_comparable_fingerprint(v["protocol_fingerprint"]) for v in dedup)
    
    # 清洗前后 v4 统计一致
    pre = compute_statistics([v for v in fixture if is_comparable_fingerprint(v["protocol_fingerprint"])])
    assert pre["sample_count"] == 229
    
    # 非目标字段不变
    assert all("symbol" in v and "status" in v for v in fixture)
```

**预计耗时**：25 分钟

---

### Task 6：P3 + Task 7：停机检查 + 回滚 + 集成测试

**P3** 不变（v3 已完善）。

**回滚安全（v4 强化）**：

```python
def rollback(session_id, force=False):
    # 1. 进程检查
    assert check_all_stopped() == [], "Stop all processes first"
    
    # 2. Registry 原子恢复
    backup = manifest["registry_backup"]
    assert sha256_file(backup["path"]) == backup["sha256"]
    atomic_replace(backup["path"], "task_FM/config/aligned_verdicts.jsonl")
    
    # 3. P0 恢复（tar 安全检查）
    for item in manifest["phases"]["P0"]["items"]:
        if item.get("status") != "deleted":
            continue  # 只恢复已删除的
        target = Path(item["original_path"])
        if target.exists() and not force:
            raise RuntimeError(f"Exists: {target}")
        verify_tar_safety(item["archive_path"], expected_run_id=item["run_id"])
        subprocess.run(
            ["tar", "xzf", item["archive_path"], "-C", "task_FM/experiments"],
            check=True
        )
    
    # 4. P1 恢复（同 tar 安全检查）
    # ...
    
    # 5. 更新 manifest
    manifest["status"] = "rolled_back"
```

**27+12 = 39 项测试**（v4 新增 12 项）：

新增测试：
- `test_p0_archive_tar_prefix_matches_rollback_policy`
- `test_p0_archive_sha_mismatch_blocks`
- `test_p0_source_not_deleted_not_skipped`
- `test_execution_plan_used_by_all_phases`
- `test_production_session_initialized`
- `test_p2_comparable_fingerprint_reflexive`
- `test_p2_rejects_non_timeout_missing`
- `test_p1_uses_retained_runs_from_p0`
- `test_manifest_records_partial_phase_state`
- `test_rollback_rejects_unsafe_tar_prefix`
- `test_manifest_hash_mismatch_blocks`
- `test_deterministic_archive_set_mtime_ties`

**预计耗时**：45 + 20 + 45 = 110 分钟

---

## B. 预生产验证

### Task 8：版本锁定 + 工作区检查
### Task 9：开发环境 dry-run（`--session "test-..."`）

---

## C. 生产停机窗口（v4 修正步骤顺序）

```
Step 10：生成 SID + 初始化正式会话
  SESSION_ID="prod-$(date +%Y-%m-%dT%H-%M-%S)"
  python3 scripts/cleanup_proposal_assets.py \
      --session "$SESSION_ID" --init-session \
      --migration-cutoff "2026-10-17T00:00:00+00:00" \
      --naive-tz "Asia/Shanghai"
  # manifest status = "initialized"

Step 11：停止三环
  kill -TERM <supervisor_pid>
  轮询等待
  分类检查（supervisor/praxist/slow_loop 全部退出）
  确认 flock 释放

Step 12：停机后状态快照（第一次）
  记录 supervisor_state + SHA-256
  记录 pending/inprogress 队列 + SHA-256
  记录 experiments/ 目录清单 + SHA-256
  sleep 5 → 再次记录 → 对比一致

Step 13：权威 registry 备份 + 执行计划生成
  备份 aligned_verdicts.jsonl → archive/<SID>/before-cleanup.jsonl
  计算 SHA-256 → manifest.registry_backup
  
  生成 execution_plan.json（不可变）：
  - P0 archive candidates + protected exemptions（含原因）
  - P1 delete set + quarantine set
  - P2/P3 预期计数
  - 状态哈希锁定（state/queue/experiments SHA-256）
  - 生成时间
  
  → manifest.execution_plan = sha256(execution_plan.json)
  
  人工审查 execution_plan.json

Step 14-17：执行 P0-P3（全部传入 --plan execution_plan.json）
  python3 ... --session "$SID" --archive-runs --plan execution_plan.json
  python3 ... --session "$SID" --clean-prescreen --plan execution_plan.json
  python3 ... --session "$SID" --fix-fingerprint --plan execution_plan.json
  python3 ... --session "$SID" --fix-prescreen-metadata --plan execution_plan.json \
      --migration-cutoff "2026-10-17T00:00:00+00:00" --naive-tz "Asia/Shanghai"
  
  每个阶段验证：
  - session ID 一致
  - execution plan hash 一致
  - 状态哈希未变
  - 实际数量与计划一致
  - 不一致则拒绝执行

Step 18：静态验收
  硬：全归档 + 全记录 + 卫生归零
  软：≤250 MB（未达成记录原因）

Step 19：重启 + 运行态验收
  bash scripts/start_supervisor.sh
  确认存活 + 首 cycle 正常
  manifest status → "completed"
```

---

## D. 收尾

Task 20：文档更新  
Task 21：Changelog

---

## 出口条件优先级

| 优先级 | 条件 | 类型 |
|--------|------|------|
| P0 | 所有不受保护 run 已归档 | 硬 |
| P0 | 未归档 run 有 manifest 记录的保护原因 | 硬 |
| P0 | error/degraded prescreen = 0 | 硬 |
| P0 | MISSING fingerprint = 0 | 硬 |
| P0 | 缺失 prescreen metadata = 0 | 硬 |
| P1 | experiments ≤ 250 MB | 软 |
| P1 | 体积下降 ≥ 90% | 软 |

---

## 测试清单（39 项）

| # | 测试名 | 类别 |
|---|--------|------|
| 1 | `test_dry_run_no_changes` | 安全 |
| 2 | `test_preserves_active_run` | P0 |
| 3 | `test_preserves_recent_runs` | P0 |
| 4 | `test_preserves_inprogress` | P0 |
| 5 | `test_preserves_pending_queue_refs` | P0/P1 |
| 6 | `test_protected_runs_may_exceed_ten` | P0 |
| 7 | `test_p0_uses_run_id_and_mtime_union` | P0 |
| 8 | `test_p0_exempt_runs_have_reasons` | P0 |
| 9 | `test_rollback_after_partial_p0` | 回滚 |
| 10 | `test_size_target_reports_overflow` | P0 |
| 11 | `test_p1_preserves_valid_prescreen` | P1 |
| 12 | `test_p1_uses_null_delimited_paths` | P1 |
| 13 | `test_p1_preserves_pending_queue_refs` | P1 |
| 14 | `test_p1_quarantines_unparseable_json` | P1 |
| 15 | `test_p1_uses_retained_runs_from_p0` | P1/P0 |
| 16 | `test_p2_fingerprint_placeholder` | P2 |
| 17 | `test_timeout_placeholder_excluded_from_statistics` | P2 |
| 18 | `test_p2_blocks_when_consumers_incompatible` | P2 |
| 19 | `test_p2_behavioral_statistical_isolation` | P2 |
| 20 | `test_p2_comparable_fingerprint_reflexive` | P2 |
| 21 | `test_p2_rejects_non_timeout_missing` | P2 |
| 22 | `test_p3_attribution_split` | P3 |
| 23 | `test_p3_rejects_unknown_timestamp` | P3 |
| 24 | `test_p3_handles_naive_timestamp` | P3 |
| 25 | `test_p3_fails_on_invalid_config` | P3 |
| 26 | `test_session_id_used_by_all_phases` | 会话 |
| 27 | `test_manifest_incremental` | 会话 |
| 28 | `test_rollback_restores_registry` | 回滚 |
| 29 | `test_atomic_archive_no_source_loss` | 原子 |
| 30 | `test_atomic_registry_write_no_corruption` | 原子 |
| 31 | `test_p0_archive_tar_prefix_matches_rollback` | 路径 |
| 32 | `test_p0_archive_sha_mismatch_blocks` | 幂等 |
| 33 | `test_p0_source_not_deleted_not_skipped` | 幂等 |
| 34 | `test_execution_plan_used_by_all_phases` | 计划 |
| 35 | `test_production_session_initialized` | 会话 |
| 36 | `test_manifest_records_partial_phase_state` | 状态 |
| 37 | `test_rollback_rejects_unsafe_tar_prefix` | 安全 |
| 38 | `test_manifest_hash_mismatch_blocks` | 安全 |
| 39 | `test_deterministic_archive_set_mtime_ties` | 稳定 |

**验收**：`pytest -q tests/test_cleanup_proposal_assets.py` → **39 passed**
