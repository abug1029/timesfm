<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-08-08 | Updated: 2026-08-08 -->

# scripts

## Purpose

CLI 入口与实验编排：预测、月度回测、Vol/Neutral 全链路、A2 LGBM、协变量/星级实验、数据运维。

## Entry Matrix (选择正确入口)

| 场景 | 入口 | 备注 |
|------|------|------|
| 盘中主观 | `copilot.py` | 预测永不压平；Vol 仅预警 |
| 纸面对账 | `paper_loop.py` | status / backfill / health；主盘 SS/SR/M/JD；见 `docs/paper_trading.md` |
| 级联预测报告 | `cascade_predict.py` | Vol overlay **默认 OFF**；`--three-star`→`list_by_stars(2)` |
| 协变量固化回测 | `monthly_backtest.py` | **唯一**固化 WF 权威 |
| v2 判据解析 | `phase4d_parse_results.py` | 读 JSONL stdout 行 |
| Neutral 全链路 | `backtest_vol_gating_fullchain.py` | 评分 → `neutral_ab_report` |
| A2 LGBM 基线 | `a2_p1_orchestrator.py` + workers | 排他锁 + 幂等 JSONL |
| A2 残差叠加 | `a2_p2_orchestrator.py` | Track B 已 NO-GO 关闭 |
| 数据日更 | `daily_update.py` | 末尾唯一 `run_guard` |
| 调度采集 | `data_management.py` | 不二次 purge |

## Key Backtest Scripts

| File | Description |
|------|-------------|
| `monthly_backtest.py` | 标准 480/24/24 walk-forward；scheme 协变量；PF/EV 走 evaluation_metrics |
| `batch_f[1-4]_single_cov.sh` | Phase 11 单协变量穷举 (7cov×20var=131 tests); 使用 _batch_lib.sh 进程管理 |
| `batch_backtest.py` | 旧扫描器；**无 scheme / 无 PF**；报告路径曾写到 `D:/FlyBuddy/fm/`（错误树） |
| `backtest_1h.py` | 早期 1H WF；勿用于固化 |
| `a2_p1_runtime.py` | eval grid / lock / 幂等 append |
| `a2_p1_worker.py` / `a2_p1_lgbm_baseline.py` | LGBM WF（train ≤ t0-24） |
| `backtest_vol_gating_fullchain.py` | Neutral OFF vs ON |
| `two_star_candidate_runner.py` / `toxic_variety_runner.py` | 星级/有毒品种实验 |
| `covariate_scan_new.py` | scan（**不得单独指导固化**） |

## Process Management (2026-08-18 加固)

| File | Description |
|------|-------------|
| `_batch_lib.sh` | 共享进程管理库: 原子锁(set -C) + heartbeat 自校验 + EXIT safe-cleanup; **不自动清场** (MSYS winpid 与 Win32 进程树不兼容) |
| `_kill_batch.ps1` | 通用 batch 杀手: 双模式匹配 + 后代保护 ($protectedPids) + -DryRun/-ExcludePid; 手动在 nohup 前运行 |
| `_kill_phase4d.ps1` | Phase 4d 专用杀手 (遗留, 仍可用) |
| `_kill_cov_gap.ps1` | 协变量空白补测杀手 (遗留, 仍可用) |

## For AI Agents

### Working In This Directory

- 允许修改 scripts（长任务先 worktree / 小样本验证）。
- 固化决策：完整 `monthly_backtest` + v2 `verdict`；禁止 scan 顶替。
- 新指标请 import `cascade.evaluation_metrics`，勿本地重写。
- 并发写 JSONL 必须锁（参考 A2 `exclusive_result_lock`）；monthly checkpoint 目前**无锁**。
- 长时 batch 任务必须 `source scripts/_batch_lib.sh` + `batch_init`，禁止手写 `kill -0` Highlander。
- **启动顺序**: 先手动 `powershell -File scripts/_kill_batch.ps1` 清残留 → 再 `nohup bash scripts/batch_fX.sh`（batch_init 不自动清场，因 MSYS winpid 与 Win32 进程树不兼容）。

### Known Bugs / Traps (2026-08-08 audit)

| ID | Issue | Where |
|----|-------|-------|
| P0 | 日期级 cutoff → 同日 1H 泄漏 | 所有 `BacktestDataStore(sym, date)` 调用方 |
| P0 | 回测信号 `sign(T+24)` ≠ 实盘 `daily_slope` + `signal_weight` | monthly vs cascade_predict |
| P0 | `--resume` 跳过已完成点且**不回填** points → summarize 样本残缺 | monthly_backtest |
| P1 | checkpoint 只写 mae/dir_ok，无法重建 PF | monthly_backtest |
| P1 | checkpoint MAE 用 `pred - real[-1:]` 广播，公式错 | monthly ~L236 |
| P1 | batch 报告路径 `D:/FlyBuddy/fm/reports` | batch_backtest |
| P1 | vol fullchain OOS 仅 2026-04~07，与 monthly 全历史不可比 | fullchain |
| P2 | stdout `EV=` 实际是 **ev_ratio**；v2 判据按此解析 | monthly print + phase4d |

### Resume Correctness

- **A2**：按 `bar_idx` 跳过 pending，**结果文件已含完整行** → OK。
- **monthly `--resume`**：跳过点不进 `points[]`，若把 resume 后 summarize 当最终结果 → **错误**。应全量重跑或扩展 checkpoint 字段后 merge。

### Testing Requirements

```bash
python -m unittest tests.test_a2_p1_runtime tests.test_a2_p1_integrity tests.test_a2_p2_integrity tests.test_validation_criteria -v
```

## Dependencies

### Internal

- `cascade/*`, `config/*`, `data/*`

### External

- TimesFM venv: `D:\FlyBuddy\shared\timesfm\.venv\`

<!-- MANUAL: -->
