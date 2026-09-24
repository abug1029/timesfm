# 三环重启清理协议

> 目标：确保三环系统重启后，模型（peer agents）不会被历史状态残留误导。

## 问题清单

重启时以下状态标识可能导致模型误解：

### 1. Run-level 状态（最高优先级）
- **run.json**: `finalized_at`, `status: succeeded` → 模型认为运行已结束
- **orchestrator_status.json**: `finalized_at`, `generations_completed` → 模型认为任务完成
- **run_stop_report.json**: 存在即表示运行已停止

### 2. Peer-level 状态
- **peer_state.yaml**: 
  - `research_state: completed` → peer 认为无事可做
  - `research_state: hypotheses_authored` → peer 认为还在假设阶段
  - `last_session_id` 引用旧 session → 上下文错位
- **session_handoff.md**: 引用旧时间戳 → 时间线混乱
- **experiment_ledger.jsonl**: 历史记录 → 可能误认为已探索过

### 3. Supervisor-level 状态
- **supervisor_state.json**:
  - `user_paused: true` → supervisor 认为被用户暂停
  - `user_paused_at` 时间戳 → 混淆暂停时长
- **Lock 文件**: `supervisor.lock`, `aligned_slow_loop.lock` 等 → 可能阻塞新启动

## 快速重启（推荐）

```bash
cd /home/abug/timesfm
bash scripts/restart_three_loop_clean.sh
```

脚本自动执行：
1. 停止旧 supervisor 进程
2. 归档 run-level 状态（run.json, orchestrator_status.json, run_stop_report.json）
3. 归档 peer-level 状态（peer_state.yaml, session_handoff.md）
4. 清除 supervisor 暂停标志（user_paused）
5. 删除 lock 文件
6. 创建 RESTART_MARKER.md 告知 peer 这是新开始
7. 启动新 supervisor

## 手动清理步骤

如需手动执行：

### Phase 1: 停止旧进程
```bash
pkill -f praxist_supervisor.py
sleep 2
```

### Phase 2: 归档 run-level 状态
```bash
RUN_DIR=$(ls -td task_FM/experiments/run_*_primary_task_FM | head -1)
TS=$(date +%Y%m%d_%H%M%S)
mv "$RUN_DIR/run.json" "$RUN_DIR/run.json.archived_$TS"
mv "$RUN_DIR/orchestrator_status.json" "$RUN_DIR/orchestrator_status.json.archived_$TS"
mv "$RUN_DIR/run_stop_report.json" "$RUN_DIR/run_stop_report.json.archived_$TS"
```

### Phase 3: 归档 peer-level 状态
```bash
for peer_dir in "$RUN_DIR"/gen_*/peers/*/memory; do
  [ -d "$peer_dir" ] || continue
  mv "$peer_dir/peer_state.yaml" "$peer_dir/peer_state.yaml.archived_$TS"
  mv "$peer_dir/session_handoff.md" "$peer_dir/session_handoff.md.archived_$TS"
done
```

### Phase 4: 清除 supervisor 状态
```bash
python3 scripts/clear_supervisor_pause.py
rm -f data/cache/supervisor.lock data/cache/aligned_slow_loop.lock
```

### Phase 5: 启动新 supervisor
```bash
bash scripts/start_supervisor.sh
```

## 验证清单

重启后检查：
- [ ] 旧进程已停止
- [ ] run.json 已归档（不存在或为新版本）
- [ ] peer_state.yaml 已归档
- [ ] supervisor_state.json 中 `user_paused: false`
- [ ] lock 文件已删除
- [ ] RESTART_MARKER.md 已创建
- [ ] Supervisor 正常运行

## 相关文件

- `scripts/restart_three_loop_clean.sh` — 一键清洁重启脚本
- `scripts/clear_supervisor_pause.py` — 清除暂停标志辅助脚本
- `scripts/start_supervisor.sh` — canonical supervisor launcher
