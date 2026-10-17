# 2026-10-16 FM_a 障碍 4/5/6 修复 — pp/bz/eb 基线重生 + 集成验证

> **执行时间**：2026-10-16
> **执行人**：Claude Code (executor agent)
> **状态**：进行中

---

## 一、执行摘要

修复覆盖度瓶颈：pp/bz/eb 三品种基线缺失导致覆盖度仅 88.9%，未达 SPEC 门闩 >95%。

**目标**：
- Task 4：pp/bz/eb 基线重生 → 覆盖度 100%
- Task 5：supervisor 重启 + 桥接器/拒收摘要自动刷新验证
- Task 6：CHANGELOG + 文档更新

---

## 二、Task 4：pp/bz/eb 基线重生

### 背景

- `data/config.py` DEFAULT_SYMBOLS 包含 27 品种（含 pp/bz/eb）
- `config/backtest_config.py` SYMBOLS 仅 22 品种（不含 pp/bz/eb）
- 基线覆盖度 88.9%（24/27），SPEC 门闩 >95% 未通过
- pp/eb 各 10024 根 1H bars，bz 2138 根（数据充足）

### 实施步骤

1. **创建重生脚本** `scripts/regenerate_missing_baselines.sh`
   - 顺序处理 pp → bz → eb
   - 每品种检查已有基线（幂等跳过）
   - 调用 `generate_baseline_points.py --symbol X --cov none --root .`
   - 输出日志到 `logs/baseline_regen_pp_bz_eb_*.log`

2. **孤儿化执行**
   ```bash
   setsid nohup bash scripts/regenerate_missing_baselines.sh </dev/null &>>logs/...
   ```

3. **预计耗时**
   - PP: 588 点 × ~8s ≈ 80 分钟
   - BZ: ~120 点 × ~8s ≈ 16 分钟
   - EB: 588 点 × ~8s ≈ 80 分钟
   - 总计：约 3 小时

### 验收标准

- [ ] 3 个基线文件生成：`baseline_points_{pp,bz,eb}_nocov.jsonl`
- [ ] 覆盖度 100%（27/27）
- [ ] 基线末端 >= 2026-10-03 00:00:00（确认窗起点）

---

## 三、Task 5：集成验证（待执行）

### 计划步骤

1. 停止 supervisor（`kill -TERM 402`）
2. 等待 `supervisor_stopped{signal_received, exit_code: 0}`
3. 重启 supervisor
4. 监控日志 30 分钟
5. 验证桥接器自动调用
6. 验证拒收摘要自动刷新
7. **合并到 master（需用户确认）**

### 验收标准

- [ ] supervisor 运行正常（phase=fast/slow 正常切换）
- [ ] 桥接器自动调用（harvested_proposals 日志）
- [ ] 拒收摘要自动刷新（known_rejections.inc.md 更新）

---

## 四、Task 6：文档更新（进行中）

### 已完成

- [x] CHANGELOG 创建（本文件）

### 待完成

- [ ] 提交文档更新
- [ ] **推送到远程（需用户显式授权）**

---

## 五、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 重生耗时超预期 | 中 | 低 | 后台执行，不阻塞其他工作 |
| supervisor 重启失败 | 低 | 高 | 保留日志，回滚到旧版本 |
| 基线末端未达确认窗 | 低 | 中 | 检查数据末端，必要时增量重生 |

---

## 六、相关文件

- `scripts/regenerate_missing_baselines.sh` — 重生脚本
- `logs/baseline_regen_pp_bz_eb_*.log` — 重生日志
- `task_FM/config/baseline_points_{pp,bz,eb}_nocov.jsonl` — 基线输出
- `scripts/check_baseline_coverage.py` — 覆盖度检查

---

## 七、Git 提交记录

（待完成后补充）
