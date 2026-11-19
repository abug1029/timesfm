# 提案资产清洗规范（Proposal Asset Cleanup Spec）

> **状态**：v2（审核修订版）  
> **创建日期**：2026-11-19  
> **审核修订**：2026-11-19（根据专家审核修订空间测算、三环耦合、P2/P3 矛盾、工程脚本四大类问题）  
> **审计基线**：commit `7a5877d`  
> **配套报告**：`docs/superpowers/reports/2026-11-19-proposal-asset-management-audit.md`

## 一、问题陈述

`task_FM/experiments/` 目录累积 **683 个 run、11,952 个提案文件、4.9 GB 磁盘**，无自动清理机制。同时裁决注册表存在 22 条 `MISSING protocol_fingerprint` 和 75 条无 prescreen metadata 的卫生问题。

**目标**：在不影响收割/慢环/监督环功能的前提下，将 experiments 磁盘占用从 4.9 GB 降至 **250 MB 以内**，并修复注册表卫生问题。

## 二、清洗范围与优先级

| Phase | 目标 | 预估释放 | 风险 |
|-------|------|---------|------|
| **P0** | 归档已收割的旧 run（保留最近 10 个） | ~4.7 GB（experiments 目录） | LOW→MEDIUM（见 §三修正） |
| **P1** | 清理 `.prescreen.json` 文件 | ~3-12 MB（2,979 文件 × <1 KB，含块对齐） | LOW |
| **P2** | 修复 22 条 MISSING fingerprint 裁决 | 0（卫生） | MEDIUM |
| **P3** | 补充 75 条无 prescreen metadata 裁决的标记 | 0（卫生） | LOW |
| **P4** | 建立长期清理策略（独立幂等脚本） | 持续 | LOW |

> **v2 修正**：原 P1 预估"释放 ~200 MB"系审计报告中"每个 < 1 KB"与"200 MB"的算术矛盾。2,979 个文件 × <1 KB = 逻辑体积 <3 MB，计入 4 KB 块对齐约 12 MB。P1 本质是卫生清理，不是空间释放手段。P0 归档后 experiments 目标体积为 ≤250 MB（10 run × 22 MB/run 上界），非 2 GB。

### 关于 WSL 虚拟磁盘膨胀

归档到 `task_FM/archive/` 仅改变目录分布，压缩包仍占用仓库所在 ext4 分区。**不释放 WSL2 `ext4.vhdx` 宿主空间**。若治理目标是缓解虚拟磁盘膨胀：
- 短期：归档目录指向宿主机外部挂载路径（如 `/mnt/d/FlyBuddy/shared/timesfm-archive/`）
- 长期：宿主侧执行 `diskpart compact vdisk` 或 `fstrim`

本规范默认归档到 `task_FM/archive/`（同分区），外部迁移方案见 §八。

## 三、各 Phase 详细规范

### 3.0 前置核实（v2 新增）

**在执行任何 Phase 之前，必须先核实以下两项架构事实：**

#### 核实 1：`harvest_proposals` 的去重状态持久化边界

```bash
# 检查 harvest_proposals 的去重是否依赖 experiments/ 目录扫描
grep -n 'dedup\|existing\|aligned_verdicts' scripts/sup_harvest.py
```

- **若去重依赖 `aligned_verdicts.jsonl`**（持久化注册表）：归档旧 run 不影响去重，验收条件可维持
- **若去重依赖 `experiments/` 目录扫描**：归档旧 run 会导致历史被拒提案的去重记忆丢失，必须修正验收条件为"对未收割活跃 run 的增量收割输出一致"，并在归档前将已拒提案的 variant_id 导出到持久化去重清单

#### 核实 2：慢环 pending 队列的存储位置与路径引用

```bash
# 检查慢环队列是否持有 run 目录路径引用
grep -n 'proposal_path\|run_dir\|experiment' scripts/aligned_slow_loop.py
```

- **若队列存储 proposal 文件的绝对路径**：归档引用路径的 run 会导致 `FileNotFoundError`
- **若队列存储 proposal 内容（已序列化）**：归档不影响

**在两项核实完成前，P0 不得执行。** 核实结果记录在本节下方。

> **核实 1 结果**：（待填写）  
> **核实 2 结果**：（待填写）

### P0：旧 Run 归档

**判据**：满足以下**全部**条件的 run 目录可归档：

1. `run_id` 不在最近 10 个 run 之列（按 mtime 排序，保留回滚缓冲）
2. run 不是当前活跃 run（`supervisor_state.last_run_id`）
3. run 目录中无 `inprogress` 慢环 checkpoint
4. **（v2 新增）** 慢环 pending 队列不引用该 run 下的任何提案路径
5. **（v2 新增）** run 已完成收割（`supervisor_state.last_harvested_run_id` 在该 run 之后）

**归档方式（v2 修正：原子打包 + 校验后删除）**：

```bash
#!/bin/bash
set -euo pipefail

ARCHIVE_DIR="task_FM/archive/proposals_pre_2026-11"
mkdir -p "$ARCHIVE_DIR"

# 用 find + tar 避免 ARG_MAX，逐 run 打包
for run_dir in "$RUN_LIST"; do
    run_id=$(basename "$run_dir")
    archive_path="$ARCHIVE_DIR/${run_id}.tar.gz"
    
    # 打包（用 -C 避免路径前缀问题）
    tar czf "$archive_path" -C "$(dirname "$run_dir")" "$run_id"
    
    # 校验：确认打包成功且非空
    if [ ! -s "$archive_path" ]; then
        echo "FATAL: archive failed for $run_id" >&2
        exit 1
    fi
    
    # 校验通过后才删除原目录
    rm -rf "$run_dir"
    echo "Archived: $run_id"
done
```

**不归档（v2 补全）**：
- 最近 10 个 run（mtime 排序）
- 当前活跃 run（`supervisor_state.last_run_id`）
- 有 inprogress 慢环 checkpoint 的 run
- **（v2 新增）** 慢环 pending 队列仍引用的 run
- 收割未完成的 run（`last_harvested_run_id` 之前未覆盖的）

**`.gitignore` 核查（v2 新增）**：

```bash
# 确认 task_FM/archive/ 在 .gitignore 中
grep -q 'task_FM/archive' .gitignore || echo 'task_FM/archive/' >> .gitignore
```

**验收**：
- `ls -d task_FM/experiments/run_*/ | wc -l` ≤ 10（**v2 修正：加了 `-d` 参数**）
- `du -sh task_FM/experiments/` ≤ 250 MB（**v2 修正：从 2 GB 降至 250 MB**）
- harvest dry-run 输出**对未归档活跃 run 的增量部分**与归档前一致（**v2 修正：不再要求全量一致，取决于核实 1 结果**）

### P1：Prescreen 文件清理

**判据**：所有位于**已归档 run 之外**的 `.prescreen.json` 文件可清理。

> **v2 修正**：
> 1. 执行顺序调整为 P0 之后（先归档旧 run，再清理剩余活跃 run 的 prescreen）
> 2. 空间预期修正为 3-12 MB
> 3. 打包避免 ARG_MAX：使用 `find ... -print0 | tar --null -czf ... -T -`

**清理方式**：

```bash
# 仅清理剩余活跃 run 的 prescreen（P0 已归档的 run 的 prescreen 已随 tar.gz 保留）
find task_FM/experiments/ -name '*.prescreen.json' -print0 | tar --null -czf \
    task_FM/archive/prescreen_files_2026-11-19.tar.gz -T -
find task_FM/experiments/ -name '*.prescreen.json' -delete
```

**验收**：
- `find task_FM/experiments/ -name '*.prescreen.json' | wc -l` = 0
- `du -sh task_FM/experiments/` 下降 3-12 MB

### P2：修复 MISSING fingerprint 裁决

**背景**：22 条 `status=timeout` 裁决缺少 `protocol_fingerprint`。根因：慢环评估 jd/sr 时超时，跳过了 `evaluator.build_summary()` 的指纹写入步骤。

**方案（v2 统一）：标记归档 + 占位指纹**

```python
# 统一逻辑：
# 1. 追加 archived_reason / archived_at 字段（审计追溯）
# 2. 写入占位 protocol_fingerprint = "TIMEOUT_NO_EVAL"（满足零缺失验收）
# 3. 保留原 status 字段（不改为 timeout_archived，保持审计准确）

import json, datetime

ARCHIVED_FP = "TIMEOUT_NO_EVAL"
ARCHIVED_AT = "2026-11-19"

path = "task_FM/config/aligned_verdicts.jsonl"
backup = path + ".bak_p2"
shutil.copy2(path, backup)

rows = []
with open(path) as f:
    for line in f:
        d = json.loads(line)
        if not d.get("protocol_fingerprint"):
            d["protocol_fingerprint"] = ARCHIVED_FP
            d["archived_reason"] = "timeout_no_fingerprint"
            d["archived_at"] = ARCHIVED_AT
        rows.append(d)

with open(path, "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
```

**v2 关键修正**：
1. **写入占位指纹 `TIMEOUT_NO_EVAL`**：满足"0 MISSING fingerprint"验收条件，同时与真实 v4 指纹明确区分
2. **保留原 status 字段**：不改 `timeout`，保持审计准确
3. **下游读取器兼容性**：需验证 `evaluator.py`、`sup_harvest.py` 等消费方对 `TIMEOUT_NO_EVAL` 指纹的处理——应在去重/比较逻辑中视为"不可比"（与真实指纹隔离）
4. **阻断脏数据再生**：需跟进修复慢环超时异常处理，兜底写入当前协议指纹（即使评估超时也应记录 `protocol_fingerprint`）。同时跟进 R4（jd/sr 的 `aligned_max_points` 限制）

**验收**：
- `aligned_verdicts.jsonl` 中 `protocol_fingerprint` 缺失条目 = 0
- 含 `TIMEOUT_NO_EVAL` 的条目 = 22（与审计基线一致）
- 下游读取器对 `TIMEOUT_NO_EVAL` 不报错（grep 验证：`grep -r 'protocol_fingerprint' scripts/ | grep -v '.pyc'`，逐一检查消费逻辑）

### P3：补充 prescreen metadata 标记

**背景**：75 条裁决无 `metadata.prescreen`，两类成因：
- **A 类**：2026-10-17 TypeSafe→Laya 迁移前的历史遗留（迁移前裁决未回填）
- **B 类**：Laya 服务不可用期间产生（10 月宕机）

**方案（v2 修正：按时间戳区分归因）**：

```python
import json, datetime

MIGRATION_CUTOFF = datetime.datetime(2026, 10, 17, tzinfo=datetime.timezone.utc)

path = "task_FM/config/aligned_verdicts.jsonl"
rows = []
with open(path) as f:
    for line in f:
        d = json.loads(line)
        meta = d.setdefault("metadata", {})
        if "prescreen" not in meta:
            # 按裁决时间戳区分归因
            ts = d.get("timestamp") or d.get("evaluated_at", "")
            try:
                eval_dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                is_pre_migration = eval_dt < MIGRATION_CUTOFF
            except (ValueError, TypeError):
                is_pre_migration = False  # 无法解析时间戳时默认 B 类
            
            if is_pre_migration:
                meta["prescreen"] = {
                    "status": "unavailable",
                    "note": "pre_laya_migration_no_prescreen"
                }
            else:
                meta["prescreen"] = {
                    "status": "unavailable",
                    "note": "prescreen_service_down_at_evaluation_time"
                }
        rows.append(d)

with open(path, "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
```

**v2 关键修正**：
1. **按 `2026-10-17` 时间戳区分**：A 类（迁移前）标注 `pre_laya_migration_no_prescreen`，B 类（服务宕机）标注 `prescreen_service_down_at_evaluation_time`
2. **安全嵌套写入**：使用 `setdefault("metadata", {})["prescreen"] = ...`，不覆盖 `metadata` 下已有的其他字段
3. **不使用扁平点号键名**：写入嵌套字典，不写 `metadata.prescreen` 字符串键

**验收**：
- 所有 251 条裁决均有 `metadata.prescreen` 字段
- A 类（pre-migration）与 B 类（service-down）数量之和 = 75
- 补充字段不影响现有调度逻辑（prescreen 是软建议，只影响调度权重）

### P4：长期清理策略

**方案（v2 修正：独立幂等脚本，不改核心调度代码）**：

创建 `scripts/cleanup_proposal_assets.py`，功能：
- `--dry-run`：预览将归档/清理的内容
- `--archive-runs`：执行 P0 归档
- `--clean-prescreen`：执行 P1 清理
- `--fix-registry`：执行 P2+P3 修复
- `--rollback`：从备份恢复

```python
#!/usr/bin/env python3
"""
scripts/cleanup_proposal_assets.py — 提案资产清洗（幂等）

用法：
    python scripts/cleanup_proposal_assets.py --dry-run
    python scripts/cleanup_proposal_assets.py --archive-runs --keep 10
    python scripts/cleanup_proposal_assets.py --clean-prescreen
    python scripts/cleanup_proposal_assets.py --fix-registry
    python scripts/cleanup_proposal_assets.py --rollback 2026-11-19T17-00-00
"""
```

**不修改 `praxist_supervisor.py`**（v2 修正：原方案在监督环中嵌入清理逻辑违反"不改核心调度代码"边界）。长期清理由 cron 或宿主定期手动执行独立脚本。

**自动清理的安全约束（v2 新增）**：
- 不清理仍在活跃 run 中的 prescreen 文件（避免触发 Laya 重复请求）
- 不清理最近 N 天内的任何文件（N 可配置，默认 7）
- 每次执行前检查 supervisor 是否已停机
- 所有操作记录到 `logs/cleanup_<timestamp>.log`

## 四、安全约束

1. **所有删除操作先 dry-run**：`scripts/cleanup_proposal_assets.py --dry-run`
2. **safe_clean.sh 白名单保护**：`task_FM/config/`、`.omc/`、`data/cache/`、`.env*` 不可触碰
3. **归档而非删除**：P0 run 归档到 `task_FM/archive/`（已加入 `.gitignore`），保留恢复能力
4. **原子操作**：打包成功后才删除原目录（`set -euo pipefail` + 校验返回码）
5. **停机后执行**：P0/P1 在 supervisor 及全部子进程停止后操作（见 §五）
6. **`.gitignore` 核查**：`task_FM/archive/` 必须在 `.gitignore` 中
7. **回滚预案**：
   - P0：`tar xzf` 从归档恢复 run 目录
   - P1：prescreen 文件从归档 tar.gz 恢复
   - P2/P3：操作前自动创建 `.bak_p2` / `.bak_p3` 备份

## 五、执行顺序（v2 修正）

```
1. 停止三环全部进程（v2 修正：从仅停 supervisor 扩展为全进程组）
   a. kill -TERM <supervisor_pid>
   b. 等待 supervisor 退出（确认 exit_code=0）
   c. 确认无残留进程：
      pgrep -af 'praxist_supervisor|praxist|aligned_slow_loop'
      # 若有残留：kill -TERM <pid>，等待；仍残留则 kill -KILL
   d. 确认慢环 flock 释放：
      flock -n data/cache/aligned_slow_loop.lock echo "lock free"

2. 核实架构事实（§3.0）
   a. 核实 harvest_proposals 去重边界
   b. 核实慢环 pending 队列存储方式

3. 备份 aligned_verdicts.jsonl

4. P0：归档旧 run（v2 修正：先做 P0）
   - 用 find + tar 逐 run 打包
   - 校验后 rm -rf

5. P1：清理 prescreen 文件（v2 修正：P0 之后）
   - find + tar 打包（避免 ARG_MAX）
   - find -delete

6. P2：修复 MISSING fingerprint

7. P3：补充 prescreen metadata

8. 验证（第六章出口条件）

9. 重启三环
   a. bash scripts/start_supervisor.sh
   b. 确认 supervisor + praxist + slow_loop 进程正常启动
   c. 检查首 cycle 日志无异常
```

## 六、出口条件

| 条件 | 验收命令 |
|------|---------|
| experiments ≤ 250 MB | `du -sh task_FM/experiments/` |
| run 目录 ≤ 10 个（活跃） | `ls -d task_FM/experiments/run_*/ \| wc -l` |
| 0 prescreen 文件残留 | `find task_FM/experiments/ -name '*.prescreen.json' \| wc -l` |
| 0 MISSING fingerprint | `python3 -c 'import json; ...'`（`TIMEOUT_NO_EVAL` 不算缺失） |
| 0 缺失 prescreen metadata | 所有条目均有 `metadata.prescreen` |
| harvest 功能正常 | `scripts/praxist_supervisor.py --dry-run` |
| supervisor 正常重启 | `pgrep -af praxist_supervisor` + 首 cycle 日志正常 |
| 全进程组正常 | `pgrep -af 'praxist_supervisor\|praxist\|aligned_slow_loop'` 均存在 |

## 七、不做的事

- **不删除任何 `aligned_verdicts.jsonl` 条目**（只标记/归档）
- **不删除基线文件**（24 品种全保留）
- **不修改 `harvest_proposals` 算法逻辑**（本 spec 只清理资产，不改算法）
- **不修改 `praxist_supervisor.py` 核心调度代码**（v2 修正：P4 独立脚本化）
- **不触碰 `data/cache/`**（运行状态，由 safe_clean.sh 保护）
- **不在三环运行时执行 P0/P1**（避免文件竞争）
- **不将 `task_FM/archive/` 提交到 Git**（已加入 `.gitignore`）

## 八、外部归档方案（可选）

若需真正释放 WSL 虚拟磁盘空间：

```bash
# 方案 A：归档到宿主机 Windows 挂载盘
EXTERNAL_ARCHIVE="/mnt/d/FlyBuddy/shared/timesfm-archive"
mkdir -p "$EXTERNAL_ARCHIVE"
# P0 打包时直接写入外部路径
tar czf "$EXTERNAL_ARCHIVE/proposals_pre_2026-11/<run_id>.tar.gz" ...

# 方案 B：WSL 虚拟磁盘压缩（宿主侧）
# Windows PowerShell（管理员）：
# Optimize-VHD -Path "C:\...\ext4.vhdx" -Mode Full
# 或 diskpart:
# select vdisk file="C:\...\ext4.vhdx"
# compact
```

## 九、跟进项（清洗之外的技术债）

| # | 跟进项 | 关联 |
|---|--------|------|
| 1 | 慢环超时异常处理兜底写入 `protocol_fingerprint` | P2 根因修复 |
| 2 | jd/sr 的 `aligned_max_points` 提升（600 → 800-1000）或品种独立上限 | R4 根因修复 |
| 3 | Laya 服务不可达时的可观测性告警 | R5 |

## 十、测试

统一脚本 `scripts/cleanup_proposal_assets.py` 需包含：

1. `test_dry_run_no_changes`：dry-run 模式不修改任何文件
2. `test_preserves_active_run`：当前活跃 run 不被归档
3. `test_preserves_recent_runs`：最近 10 个 run 不被归档
4. `test_preserves_inprogress`：有 inprogress checkpoint 的 run 不被归档
5. `test_preserves_pending_queue_refs`：慢环 pending 队列引用的 run 不被归档（v2 新增）
6. `test_harvest_unchanged`：清洗后 harvest 对未归档 run 的增量输出与清洗前一致
7. `test_rollback`：从备份恢复后状态与清洗前一致
8. `test_p2_fingerprint_placeholder`：P2 执行后 0 MISSING + 22 个 TIMEOUT_NO_EVAL
9. `test_p3_attribution_split`：P3 执行后 A 类/B 类归因正确
10. `test_gitignore_archive`：`task_FM/archive/` 在 `.gitignore` 中
