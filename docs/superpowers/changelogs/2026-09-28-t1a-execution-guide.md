# T1a 执行指南: Registry 复活 + nocov 基线重生

**状态:** PR-A1 已完成 (commit `6c94275`), D5 已修复 (commit `d621a1a`)
**预计时间:** ~70 分钟（7 品种基线重生）

## 前置条件

- [x] D5 修复: cutoff 改为 bar 收盘时间 (`d621a1a`)
- [x] PR-A1: 协议指纹加入 cutoff 约定 (`6c94275`)
- [x] 测试通过: `test_pr_a1_protocol_fingerprint.py` (4/4)

## 执行步骤

### 1. 验证当前基线状态

```bash
ls -lh task_FM/config/baseline_points_*_nocov.jsonl
# 期望: 仅 rb 存在 (1/8)
```

### 2. 启动 supervisor 触发基线重生

```bash
cd /home/abug/timesfm
scripts/start_supervisor.sh
```

supervisor 启动后会:
1. 检测到 7 个品种缺少 nocov 基线
2. 自动串行重生每个品种的基线 (~10 min/品种)
3. 生成 `baseline_points_{sym}_nocov.jsonl` (含 `protocol_fingerprint`)

### 3. 监控进度

```bash
# 查看已生成的基线
ls -lh task_FM/config/baseline_points_*_nocov.jsonl

# 查看 supervisor 日志
tail -f logs/supervisor.log | grep -i baseline
```

### 4. 验收标准

```bash
# 期望: 8 个 nocov 基线文件
ls task_FM/config/baseline_points_*_nocov.jsonl | wc -l  # 期望 8

# 每个基线首行须含 protocol_fingerprint
head -1 task_FM/config/baseline_points_m_nocov.jsonl | grep protocol_fingerprint
```

## 判据 A 验证

基线重生后，需验证 A1 字段确实被生产路径写入:

1. 检查新生成的裁决是否包含:
   - `protocol_fingerprint` (非空)
   - `dir_acc_full` / `dir_acc_ex_roll` (非空)
   - `run_mode` (应为 "exploration")
   - `dm_status` / `pair_set_hash` (有值)

2. 运行验证脚本 (待实现):
   ```bash
   python scripts/verify_t1a_criteria_a.py
   ```

## 判据 B' 验证

D5 已裁 (bar_close)，判据 B' 为**确定性达成**:

1. 至少 1 条裁决的 `pairing_valid=True` 且 `p_value` 非 None
2. `dm_status` 落入可配对状态

## 风险

- 复活后可能因其他门禁再次饿死
- 缓解: 首轮观察 `reject_reasons` 分布，任一 reason 占比 > 80% 立即暂停归因

## 回滚

如需回滚到旧协议指纹:
```bash
git revert 6c94275
# 重新生成基线 (旧协议指纹)
```
