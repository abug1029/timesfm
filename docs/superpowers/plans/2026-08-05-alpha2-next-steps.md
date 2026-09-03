# Alpha 2.0 推进计划 (2026-08-05)

**A2-P1 状态**: 代码完整，smoke 通过，但需全量运行得 gate 裁决。
**下一步**: 全量 20 品种 A2-P1 → GO/NO-GO 裁决 → 决定 A2-P2 是否启动。

---

## 一、当前状态盘点

### A2-P1 代码 ✅
- 9 commits on master (`9b8a3fc..4bddce0`)
- 13 个 unit test 通过
- Smoke test 通过（模型加载 + dense 矩阵 + LGBM + 三曲线 + gate + 报告）
- 实际产出物：`cascade/lgbm_features.py`、`scripts/a2_p1_lgbm_baseline.py`、3 个测试文件

### A2-P1 运行 ❌ 未完成
- **smoke 设计问题**: `--max-points 3` 样本太少，LGBM 训练集每个 eval 点 <50 触发 fallback → 输出 PF=0.0。需要 `--max-points >= 50` 才有意义。
- **全量运行未做**: 20 品种完整 A2-P1 运行未启动。
- **Gate 裁决未产出**: 需要全量运行后的报告才有 GO/NO-GO 结论。

### A2-P2/P3 ❌ 未启动
- A2-P2 (残差叠加架构): 依赖 A2-P1 GO 裁决。
- A2-P3 (Copilot 升维): 依赖 A2-P2 完成。
- Spec 已写 A2-P1；A2-P2/P3 spec 待 A2-P1 裁决后再做。

### P2 其他项
- **#8 LightGBM 天花板探针**: 现已由 A2-P1 覆盖（LGBM 基线探针就是做这个）。
- **#10 动态 Regime 路由**: 未启动。A2-P2/P3 优先级更高。
- **#11 测试覆盖**: ✅ 完成 (194/194 PASS，含 Phase 9 防回归)
- **#9 有毒品种专攻**: ✅ 完成 (AO 固化 hourly_slope+calendar, JD 确认最优)

### 代码债 (非 A2 相关)
- 主仓库有未提交改动: AGENTS.md, covariate_scan.py 删除, ralph/, phase10 jsonl 等 (与本 session 无关的历史遗留)
- 6 个 deferred minors: unused imports、docstring 不一致、test 覆盖 gap 等 (cosmetic，不阻塞功能)

---

## 二、推进计划

### Phase A: A2-P1 全量运行 + Gate 裁决 (优先级最高，预计 2-4 小时)

**目标**: 跑 20 品种 A2-P1，产出裁决报告。

**步骤**:
1. **修复 smoke 测试设计**: 改 `--max-points 10` → `--max-points 100`（或动态根据 dense_rows 自动选择）。确保 LGBM 有足够训练数据。
2. **启动全量运行**:
   ```bash
   # 全 20 品种, ~50 eval points per variety (396 dense rows)
   nohup D:/FlyBuddy/shared/timesfm/.venv/Scripts/python scripts/a2_p1_lgbm_baseline.py \
     ss rb i jm cf p m sp sr ao jd fu fg lh cj ur sh ma bu ta \
     --max-points 100 --dense-step 24 --refit-every 10 \
     > reports/a2_p1_full_run.log 2>&1 &
   ```
3. **监控**: 每 30 分钟查 `reports/a2_p1_baseline_results.jsonl` 看进度。
4. **产出**: `reports/research/2026-08-04_a2_p1_baseline_result.md` 完整裁决报告。

**预计时间**:
- 每品种 ~5-10 分钟（dense 矩阵 + LGBM 训练 + 三曲线）
- 20 品种 × 7 分钟 = ~2.5 小时
- 加 smoke 调试和验证 = 3-4 小时

### Phase B: Gate 裁决后决策

**如果 GO (多数品种 LGBM 显著优于 scheme)**:
→ 启动 A2-P2 spec/plan (残差叠加架构)
→ 预计工作量: 1 天 spec + 2-3 天实现

**如果 NO-GO (LGBM 未能显著超越 scheme)**:
→ 重新评估 Alpha 2.0 方向
→ 可能选项:
   - 接受天花板: 当前 xreg 已接近 SNR 极限
   - 转向 P2 #10 动态 Regime 路由 (不改模型，改特征选择)
   - 转向 Track A (Copilot 工程优化，V1 模型也能用)

### Phase C: 代码债清理 (可选，低优先级)

**6 个 deferred minors**:
- unused imports (T2, T3)
- docstring ratio/return 不一致 (T3)
- test coverage gap (T2, T5)
- dead code (T5)
- import 样式 (T6)

**预估**: 1 小时一次性 cleanup commit。

**历史遗留未提交改动**:
- AGENTS.md 修改
- scripts/covariate_scan.py 删除 (CLAUDE.md 还引用)
- ralph/ 产物
- phase10 jsonl 等

**预估**: 需要用户确认这些历史改动的处理方式 (commit / discard / 留作参考)。

### Phase D: P2 #10 动态 Regime 路由 (长期)

**当前状态**: 未启动。
**依赖**: Alpha 2.0 A2-P1 gate 裁决结果。
**优先级**: 低于 A2-P2/P3。
**预估**: 独立 spec/plan 周期，2-3 天。

---

## 三、立即执行建议

**优先级 1**: Phase A - 修复 smoke + 全量运行
- 修改 `scripts/a2_p1_lgbm_baseline.py` 的默认 `--max-points` 或 smoke 测试
- 启动全 20 品种运行 (后台)
- 产出裁决报告

**优先级 2**: Phase B - 基于 gate 裁决决策
- 如果 GO: 启动 A2-P2 spec/plan (brainstorming + writing-plans)
- 如果 NO-GO: 重新评估方向

**优先级 3**: Phase C - 代码债清理 (可在任何空闲时段做)

**优先级 4**: Phase D - P2 #10 (长期，不急)

---

## 四、Smoke 测试设计修复

当前问题: `--max-points 3` 让 LGBM 训练集每个 eval 点 <50 样本，触发 fallback。

修复方案:
- 将 smoke test 的 `--max-points 10` 改为 `--max-points 50` (确保最后 1-2 个 eval 点有足够训练数据)
- 或者动态调整: `max_points = max(50, dense_rows // 4)` 基于 dense 矩阵大小
- 或保持 smoke 小但只验证 pipeline 通 (不验证性能指标)

建议: 方案 1 (改 `--max-points 50`)。50 eval points 下，最后 1 个 eval 点有 ~49 个训练样本（仍 <50，但接近）。要真正测试 LGBM 学习能力，需要 ~100 eval points。

折中: smoke 改为 `--max-points 100` 做功能验证，接受 LGBM 在小样本下表现不稳；性能评估留给全量运行。
