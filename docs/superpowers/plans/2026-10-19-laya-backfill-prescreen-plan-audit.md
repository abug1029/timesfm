# Audit: 2026-10-19-laya-backfill-prescreen-plan（再审 / v2）

| 项 | 值 |
|----|----|
| 对象 | `docs/superpowers/plans/2026-10-19-laya-backfill-prescreen-plan.md`（v2，mtime 2026-10-19 09:58 CST） |
| 类型 | 运维执行计划（跑现成 `scripts/backfill_prescreen.py` v2.1.0） |
| 对照 | 上次 audit（有条件通过 / 4×P0）；Frozen leak-fix SPEC；`cascade/typesafe_prescreen.py`；`scripts/backfill_prescreen.py`；`scripts/check_pd_chinese.py` |
| 审核时间 | 2026-10-19 10:41 CST（Asia/Shanghai） |
| 方法 | 静读 v2 plan；对照上次 P0/P1 清单逐条核销；抽查 CLI/`should_skip`/`queue_row`/strip；本机 `--dry-run --skip-laya-check --max 20000` |
| **结论** | **通过** |

---

## §1 一句话

v2 已消化上次全部 4×P0 与关键 P1：`--max` 显式、中文门改 `check_pd_chinese.py`、PID 赋值、5.2 脚本修复、pending 口径统一、variant_id 查 queue、坏批次回滚就位；本机干跑 `待处理: 6695` 与 plan「~6600 / ±10%」门一致。**可按正文开 Phase 0→1。**

---

## §2 范围与完成度（对照修订前后：P0 是否关闭）

| 上次 P0 | v2 处置 | 判定 |
|---------|---------|------|
| P0-1 漏 `--max` | Phase 1/3 显式 `--max 20000`；Phase 2 `--max 100`；§0/§9/§10 写明 default=500 陷阱 | ✅ 关闭 |
| P0-2 Phase 2.5 假绿 | 改为 `python3 scripts/check_pd_chinese.py`（源 proposal + `_build_state`）；删对 `.prescreen.json` 读 `proposal_summary` | ✅ 关闭 |
| P0-3 看门狗 PID | Phase 3：`... &` 后 `BACKFILL_PID=$!`；3.5 `kill -0 $BACKFILL_PID` | ✅ 关闭（见 P2 残留行） |
| P0-4 Phase 5.2 TypeError | `grep "完成:" \| tail -1 \| python3 -c` 读 stdin 再 `re.search` | ✅ 关闭 |

| Plan 声称 | 评估 |
|-----------|------|
| 清空积压 + 入队慢环 | ✅ 口径改为 effective≈6644，`--max 20000` 不截断 |
| 中文双重检查（2.5 + 4.5） | ✅ 均走 `check_pd_chinese.py` |
| 不扩 PrescreenStatus | ✅ 三值门；status 抽样收紧为仅三值 |
| harvest Phase 2b | ✅ 仍未纳入 |
| 断点续跑 / 看门狗 / 坏批次回滚 | ✅ state 路径对；§7 回滚已补 |

---

## §3 与 leak-fix 决策一致性

| 决策 | Plan v2 | 代码 HEAD | 判定 |
|------|---------|-----------|------|
| `_PD_MIN_LEN=12` | 4.5 / 2.5 走 `check_pd_chinese` → `_build_state` | `typesafe_prescreen.py` L38 | OK |
| 双道 strip + 空壳→`""` | 依赖已合入 | `_strip_chinese` / `_is_shell_pd` | OK |
| 不扩 `PrescreenStatus` | status ∈ {success,error,degraded} | Literal 三值 | OK |
| harvest Phase 2b | 未做 | 仅文件幂等 | OK（out-of-scope） |
| REGISTRY 去重 | 依赖现网 | `variant_id in existing` → skip | OK |

---

## §4 可行性 vs 真实 API（证据）

### 4.1 CLI `--max`（原 P0-1）✅

- 代码仍 `default=500`（`backfill_prescreen.py` L395）
- Plan Phase 1/3 已显式 `--max 20000`
- 本机实证（2026-10-19 10:41 CST）：

```text
参数: max=20000 workers=5 dry_run=True ...
扫描到 7389 个提案
待处理: 6695
... 共 6695 个
```

与 Phase 0 估算 ~6644 / PASS「~6600 ±10%」一致（6695 在窗内）。

### 4.2 中文门（原 P0-2）✅

- `check_pd_chinese.py`：对源 proposal 调 `_build_state`，查 `state["proposal_summary"]["predicted_direction"]` 东亚宽字符
- **不再**读 `.prescreen.json` 的不存在字段 → 假绿路径已切断
- 注：该脚本扫全量源提案（含 strip 生效性），作 2.5 硬门语义正确（代码路径门，非「仅试点 100 输出」门）

### 4.3 看门狗 PID（原 P0-3）✅

```bash
... setsid nohup python3 scripts/backfill_prescreen.py ... &
BACKFILL_PID=$!
echo "PID: $BACKFILL_PID"
```

最终赋值正确。Phase 3 开头多一行无用的 `BACKFILL_PID=$!`（在 `&` 之前）→ **P2 噪音**，不阻断。

### 4.4 Phase 5.2（原 P0-4）✅

stdin 单行 + `re.search(r"success=(\d+).*?failed=(\d+)", line)` — 不再对 list 调用。

### 4.5 Pending 口径 / ETA（原 P1）✅

§0 写明：无文件 6075 + retry(degraded+error≈620) − state processed 51 ≈ 6644；workers=2 → ~10h。干跑 6695 校准通过。

### 4.6 variant_id / 抽样 / 回滚（原 P1）✅

- variant_id：查 `aligned_pending.jsonl` 最近 100 行，非落盘空字段
- status / 5.6 抽样：按 mtime 窗（非 `sorted(glob)[-100:]`）
- §7 坏批次回滚：按 `enqueued_at` 剔除；占位 `2026-10-19TXX` 需执行时替换（操作说明，非 blocker）

### 4.7 queue lifecycle 缺口（原 P1 residual）

`queue_row` 仍无 `proposal_id`/`version`（代码 L359–369 仅有 variant_id/symbol/cov_override/.../`_proposal_path`）。Plan §0「已知缺口」已记录；慢环 withdrawn 跳过不崩溃。**不升 P0**；若本周依赖撤回链，另开编码前置。

### 4.8 日志双写（原 P1 → 降级）

`setup_logging()` 仍写 `logs/backfill_prescreen_{UTC}.log`；plan redirect `logs/backfill_${LOG_SUFFIX}.log`。看门狗盯后者 → 可运维。标 **P2** 说明即可。

---

## §5 问题清单

### 原 P0（全部关闭）

1. ✅ `--max` 显式传参
2. ✅ 中文门改 `check_pd_chinese.py`
3. ✅ `BACKFILL_PID=$!`（后赋值）
4. ✅ 5.2 `re.search` 修复

### 仍开 / 新开

**无新 P0。**

#### P1（非阻断；已知 residual）

5. queue 行缺 `proposal_id`/`version`（已文档化；撤回链对 backfill 行失效）

#### P2（可顺手改 plan 文案，不挡执行）

6. Phase 3 在 `nohup ... &` **之前** dual 写了一次 `BACKFILL_PID=$!` — 删掉以免误导
7. Phase 2.5 status 抽样：`now = os.path.getmtime(".")` 应用 `time.time()`（目录 mtime 不稳定；过松时可能纳入过多历史文件，门禁仍能跑但不「最近 30min」）
8. 双日志：注明盯 `backfill_${LOG_SUFFIX}.log`；或只 redirect
9. workers=2 理由已改为限流 — OK；与脚本 default 5 的差异已说明

---

## §6 非阻断确认（正面）

- glob / STATE_FILE / `queue_enqueue` / `--dry-run` / `--skip-laya-check` / `--timeout-min` / `--workers` 与脚本一致
- REGISTRY + in_flight 去重仍在；strip 在 Laya 调用前生效
- `PrescreenStatus` 未扩
- 慢环接手与 claim 链方向正确
- dry-run 6695 与 plan PASS 窗对齐

---

## §7 结论与放行条件

**通过。**

上次 4×P0 均已在 v2 关闭；关键 P1（口径、中文门、variant_id、回滚、PID、5.2）已落地。剩余为文档化 residual（lifecycle 字段）与 P2 文案毛刺，**不阻挡 Phase 0→1→2 试点**。

**放行**：可按 plan 正文执行；执行 Phase 3 前建议顺手删掉前置废 `BACKFILL_PID=$!` 行，并将 §7 回滚时间戳换成实际 `enqueued_at` 下限。lifecycle `proposal_id`/`version` 若本周要撤回能力，另开编码任务，不挡本 backfill。
