# 提案资产清洗规范（Proposal Asset Cleanup Spec）

> **状态**：Draft  
> **创建日期**：2026-11-19  
> **审计基线**：commit `7a5877d`  
> **配套报告**：`docs/superpowers/reports/2026-11-19-proposal-asset-management-audit.md`

## 一、问题陈述

`task_FM/experiments/` 目录累积 **683 个 run、11,952 个提案文件、4.9 GB 磁盘**，无自动清理机制。同时裁决注册表存在 22 条 `MISSING protocol_fingerprint` 和 75 条无 prescreen metadata 的卫生问题。

**目标**：在不影响收割/慢环/监督环功能的前提下，将 experiments 磁盘占用从 4.9 GB 降至 ~2 GB，并修复注册表卫生问题。

## 二、清洗范围与优先级

| Phase | 目标 | 预估释放 | 风险 |
|-------|------|---------|------|
| **P0** | 归档已收割的旧 run（harvest 后无新提案产出） | ~3 GB | LOW |
| **P1** | 清理 `.prescreen.json` 文件 | ~200 MB | LOW |
| **P2** | 修复 22 条 MISSING fingerprint 裁决 | 0（卫生） | MEDIUM |
| **P3** | 补充 75 条无 prescreen metadata 裁决的标记 | 0（卫生） | LOW |
| **P4** | 建立长期清理策略（自动化或定期人工） | 持续 | LOW |

## 三、各 Phase 详细规范

### P0：旧 Run 归档

**判据**：满足以下全部条件的 run 目录可归档：
1. `run_id` 在 `supervisor_state.last_harvested_run_id` 之前（已收割）
2. run 目录中无 `results/gen_*/proposals/` 下的新文件（mtimes 全部早于最后一次 harvest cycle）
3. run 不是最近 10 个 run 之一（保留回滚缓冲）

**归档方式**：
```bash
# 归档目录（不删除，移至 archive）
mkdir -p task_FM/archive/proposals_pre_2026-11/
# 对每个符合条件的 run：
tar czf task_FM/archive/proposals_pre_2026-11/<run_id>.tar.gz \
    task_FM/experiments/<run_id>/
rm -rf task_FM/experiments/<run_id>/
```

**不归档**：
- 最近 10 个 run（保留快速回滚能力）
- 当前活跃 run（`supervisor_state.last_run_id`）
- 任何包含 `inprogress` 慢环 checkpoint 的 run

**验收**：
- `ls task_FM/experiments/run_*/ | wc -l` ≤ 10（或减少 60%+）
- `du -sh task_FM/experiments/` ≤ 2 GB
- `harvest_proposals`  dry-run 输出与归档前一致（所有合格提案仍可发现）

### P1：Prescreen 文件清理

**判据**：所有 `.prescreen.json` 文件可清理：
- prescreen 是 **fire-and-forget** 缓存，不影响裁决
- 监督环在下次 harvest 时会重新生成（如果 Laya 可用）
- 历史 prescreen 文件（2,979 个，100% error/degraded）无实际价值

**清理方式**：
```bash
find task_FM/experiments/ -name '*.prescreen.json' -delete
```

**替代方案（保留审计线索）**：
```bash
# 压缩归档后删除
tar czf task_FM/archive/prescreen_files_2026-11-19.tar.gz \
    $(find task_FM/experiments/ -name '*.prescreen.json')
find task_FM/experiments/ -name '*.prescreen.json' -delete
```

**验收**：
- `find task_FM/experiments/ -name '*.prescreen.json' | wc -l` = 0
- `harvest_proposals` 功能不受影响（prescreen 仅影响调度权重，不影响收割逻辑）

### P2：修复 MISSING fingerprint 裁决

**背景**：22 条 `status=timeout` 裁决缺少 `protocol_fingerprint`。这些是慢环评估超时导致 `build_summary` 未执行。

**方案 A（推荐）：标记为 `status=timeout_archived`**
```python
# 脚本：scripts/cleanup_missing_fingerprint_verdicts.py
# 读取 aligned_verdicts.jsonl
# 对 protocol_fingerprint 缺失的条目：
#   - 追加字段 "archived_reason": "timeout_no_fingerprint"
#   - 追加字段 "archived_at": "2026-11-19"
#   - 保留原 status 字段不变（审计追溯）
# 写回 aligned_verdicts.jsonl
```

**方案 B：物理删除**
```python
# 直接移除无 fingerprint 的条目
# 不推荐——失去审计线索
```

**验收**：
- `aligned_verdicts.jsonl` 中无 `protocol_fingerprint` 缺失条目
- 归档条目可从 `aligned_verdicts.jsonl` 中按 `archived_reason` 过滤

### P3：补充 prescreen metadata 标记

**背景**：75 条裁决无 `metadata.prescreen`，可能是 Laya 不可用期间的产物。

**方案**：为这些条目补充 `"metadata.prescreen": {"status": "unavailable", "note": "prescreen service down at evaluation time"}`

**验收**：
- 所有 251 条裁决均有 `metadata.prescreen` 字段
- 补充字段不影响现有调度逻辑

### P4：长期清理策略

**自动清理（推荐）**：
在 `praxist_supervisor.py` 的每个 cycle 末尾添加：

```python
def _maybe_cleanup_prescreen(root):
    """每 50 cycle 清理一次 prescreen 文件（fire-and-forget 缓存）"""
    if state["cycles_done"] % 50 != 0:
        return
    # 删除超过 7 天的 .prescreen.json
    cutoff = time.time() - 7 * 86400
    for f in glob.glob(f"{root}/**/proposals/*.prescreen.json", recursive=True):
        if os.path.getmtime(f) < cutoff:
            os.remove(f)
```

**Run 归档自动化**：
- 每月或每 100 cycle，由宿主运行 `scripts/archive_old_runs.sh`
- 归档判据同 P0，脚本幂等

## 四、安全约束

1. **所有删除操作先 dry-run**：使用 `--dry-run` 或 `echo` 模式预览
2. **safe_clean.sh 白名单保护**：`task_FM/config/`、`.omc/`、`data/cache/`、`.env*` 不可触碰
3. **归档而非删除**：P0 run 归档到 `task_FM/archive/`，保留恢复能力
4. **supervisor 停机后执行**：P0/P1 在 supervisor 停止后操作，避免竞争
5. **回滚预案**：
   - P0：`tar xzf` 从归档恢复 run 目录
   - P1：prescreen 文件可从下次 harvest 重新生成
   - P2/P3：修改前备份 `aligned_verdicts.jsonl`

## 五、执行顺序

```
1. 停止 supervisor（kill -TERM → 等 exit）
2. 备份 aligned_verdicts.jsonl
3. P1：清理 prescreen 文件（风险最低，先做）
4. P0：归档旧 run（按 dry-run → 确认 → 执行）
5. P2：修复 MISSING fingerprint
6. P3：补充 prescreen metadata
7. 重启 supervisor
8. 验证：harvest dry-run + 裁决注册表一致性
```

## 六、出口条件

| 条件 | 验收命令 |
|------|---------|
| experiments ≤ 2 GB | `du -sh task_FM/experiments/` |
| run 目录 ≤ 10 个（活跃） | `ls -d task_FM/experiments/run_*/ \| wc -l` |
| 0 prescreen 文件残留 | `find task_FM/experiments/ -name '*.prescreen.json' \| wc -l` |
| 0 MISSING fingerprint | `python3 -c 'import json; ...'`（查 protocol_fingerprint） |
| harvest 功能正常 | `scripts/praxist_supervisor.py --dry-run`（验证 harvest 输出） |
| supervisor 正常重启 | `pgrep -af praxist_supervisor` + 首 cycle 日志正常 |

## 七、不做的事

- **不删除任何 `aligned_verdicts.jsonl` 条目**（只标记/归档）
- **不删除基线文件**（24 品种全保留）
- **不修改 `harvest_proposals` 逻辑**（本 spec 只清理资产，不改算法）
- **不触碰 `data/cache/`**（运行状态，由 safe_clean.sh 保护）
- **不在 supervisor 运行时执行 P0/P1**（避免文件竞争）

## 八、测试

清洗脚本（`scripts/cleanup_proposal_assets.py`）需包含：
1. `test_dry_run_no_changes`：dry-run 模式不修改任何文件
2. `test_preserves_active_run`：当前活跃 run 不被归档
3. `test_preserves_recent_runs`：最近 10 个 run 不被归档
4. `test_preserves_inprogress`：有 inprogress checkpoint 的 run 不被归档
5. `test_harvest_unchanged`：清洗后 harvest 输出与清洗前一致
6. `test_rollback`：从归档恢复后状态与清洗前一致
