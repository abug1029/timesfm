# 提案资产清洗实施计划

> **日期**：2026-11-19  
> **依据规范**：`docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md`（v4 执行基线）  
> **审计基线**：commit `7a5877d`  
> **预计耗时**：2-3 小时（含测试 + 停机窗口）

---

## Task 0：前置核实（脚本化）

**目标**：将 §3.0 五项核实编码为 `scripts/cleanup_proposal_assets.py --verify` 子命令，输出结构化结果。

**交付物**：
- `scripts/cleanup_proposal_assets.py` 骨架（CLI 框架 + `--verify` 子命令）
- 核实函数：`verify_dedup_boundary()`, `verify_pending_queue()`, `verify_state_schema()`, `verify_time_field()`, `verify_fingerprint_consumers()`
- `VerificationResults` 数据类

**验收**：
- `python3 scripts/cleanup_proposal_assets.py --verify` 输出 5 项核实结果
- 任何一项失败时 exit(1) + 明确原因

**预计耗时**：30 分钟

---

## Task 1：P0 归档逻辑

**目标**：实现 `compute_archive_set()` + 原子打包 + 增量 manifest。

**交付物**：
- `compute_archive_set()` 函数（mtime ∪ run_id 并集 + 5 项保护判据）
- `archive_runs()` 函数（逐 run tar + 校验 + rm + manifest 追加）
- `has_inprogress_checkpoint()`, `is_harvested()`, `parse_run_id_ts()` 辅助函数

**依赖**：Task 0（需要 pending_queue_refs 和 state_schema）

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

## Task 2：P1 清理逻辑

**目标**：实现 NUL 安全 prescreen 清理（4 项删除条件）。

**交付物**：
- `compute_prescreen_delete_set()` 函数（status + active run + pending refs + 时间窗口）
- `generate_p1_list()` 函数（输出 NUL 分隔列表到 stdout）
- `clean_prescreen()` 函数（tar 备份 + xargs 删除 + manifest 追加）

**依赖**：Task 0 + Task 1（需要 pending_refs 和 active_run_id）

**验收**：
- `test_p1_preserves_valid_prescreen`
- `test_p1_uses_null_delimited_paths`
- `test_p1_preserves_pending_queue_refs`

**预计耗时**：20 分钟

---

## Task 3：P2 fingerprint 修复

**目标**：修复 22 条 MISSING fingerprint + TIMEOUT_NO_EVAL 统计隔离。

**交付物**：
- `execute_p2()` 函数（原子写入 + 占位指纹）
- `add_fingerprint_exclusions()` 函数（自动在消费方添加排除守卫）
- 消费方扫描结果记录到 manifest

**依赖**：Task 0（需要核实 5 结果）

**验收**：
- `test_p2_fingerprint_placeholder`
- `test_timeout_placeholder_excluded_from_statistics`

**预计耗时**：30 分钟

---

## Task 4：P3 prescreen metadata 补充

**目标**：按时间戳区分 A/B 类归因 + unknown 硬门禁。

**交付物**：
- `execute_p3()` 函数（parse_ts_safe + 三类归因 + assert unknown=0）
- `parse_ts_safe()` 函数（naive datetime 按时区配置补齐）

**依赖**：Task 0（需要核实 4 结果：time_field + timezone）

**验收**：
- `test_p3_attribution_split`
- `test_p3_rejects_unknown_timestamp`
- `test_p3_handles_naive_timestamp_with_declared_timezone`
- `test_p3_fails_when_time_field_config_is_invalid`

**预计耗时**：20 分钟

---

## Task 5：会话管理 + 回滚

**目标**：统一 SESSION_ID + 增量 manifest + 回滚逻辑。

**交付物**：
- `SessionManager` 类（创建会话目录 + manifest 增量写入 + 状态更新）
- `rollback()` 函数（读 manifest → 解压 tar → 恢复 before-cleanup.jsonl）
- `--rollback <session_id>` CLI 子命令

**依赖**：Task 1-4

**验收**：
- `test_session_id_is_used_by_all_phases`
- `test_manifest_is_written_incrementally`
- `test_rollback_restores_original_registry`
- `test_rollback_after_partial_p0`

**预计耗时**：30 分钟

---

## Task 6：停机检查 + 进程管理

**目标**：分类进程检查 + flock 确认。

**交付物**：
- `check_all_processes_stopped()` 函数（三类进程分别检查）
- `wait_for_process_exit()` 函数（kill -0 轮询）
- 集成到脚本的 `--preflight` 子命令

**依赖**：无

**验收**：
- `test_no_residual_target_processes`

**预计耗时**：15 分钟

---

## Task 7：集成测试 + dry-run

**目标**：全脚本集成测试 + dry-run 验证。

**交付物**：
- `tests/test_cleanup_proposal_assets.py`（25 项测试）
- dry-run 输出审查

**依赖**：Task 0-6

**验收**：
- 25/25 测试通过
- dry-run 输出与预期一致
- `test_dry_run_no_changes`
- `test_gitignore_archive`

**预计耗时**：30 分钟

---

## Task 8：文档更新

**目标**：更新 spec 状态为"已执行"，记录核实结果。

**交付物**：
- 规范中 5 项核实结果填入
- changelog：`docs/superpowers/changelogs/2026-11-19-proposal-asset-cleanup.md`

**依赖**：Task 7

**预计耗时**：15 分钟

---

## 执行时间线

```
T+0:00  Task 0: 前置核实（30 min）
T+0:30  Task 6: 停机检查（15 min，与 Task 1 并行）
T+0:30  Task 1: P0 归档逻辑（45 min）
T+1:15  Task 2: P1 清理逻辑（20 min）
T+1:35  Task 3: P2 fingerprint（30 min，与 Task 4 并行）
T+1:35  Task 4: P3 metadata（20 min）
T+2:05  Task 5: 会话管理 + 回滚（30 min）
T+2:35  Task 7: 集成测试（30 min）
T+3:05  Task 8: 文档更新（15 min）
T+3:20  完成
```

**总预计**：~3.5 小时（含并行）

---

## 执行窗口

**建议**：选择快环 run 间隙（约 1.5h/run 周期）执行。

```
1. 确认当前无活跃快环 run（supervisor_state.phase != "fast" 或 run 即将结束）
2. 确认慢环队列为空（pending = 0, inprogress = 0）
3. kill -TERM supervisor → 等待退出
4. 执行清洗
5. 重启 supervisor
```

---

## 回滚预案

**任何阶段失败**：
1. 停止清洗脚本
2. 读 `task_FM/archive/<session_id>/manifest.json`
3. 执行 `python3 scripts/cleanup_proposal_assets.py --rollback <session_id>`
4. 确认恢复后重启 supervisor

**数据零丢失保证**：
- 所有归档操作先 tar 后 rm，tar 校验通过才删
- 注册表用原子替换，中途异常不损坏
- 原始备份 `before-cleanup.jsonl` 在第一步创建

---

## 不做的事

- 不修改 `praxist_supervisor.py` 核心调度逻辑
- 不删除任何 `aligned_verdicts.jsonl` 条目
- 不删除基线文件
- 不在三环运行时执行
- 不手工 Shell 执行核心逻辑
