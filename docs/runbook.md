# FM_a 运维手册 (Runbook)

## 环境

| 项 | 值 |
|----|-----|
| 项目根 | `D:\FlyBuddy\FM_a`（须在此目录启动，或保证 import 路径含根） |
| Python | `D:\FlyBuddy\shared\timesfm\.venv\` |
| TqSdk | `.env` 中 `TQSDK_ACCOUNT` / `TQSDK_PASSWORD` |
| 数据库 | `db/futures_<symbol>.db` |

```bash
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
cd D:/FlyBuddy/FM_a
```

路径解析：`data.config.FM_ROOT` + `resolve_under_root()` — **模型/配置文件不依赖进程 cwd**。

## 日常采集

| 场景 | 命令 |
|------|------|
| 日线+1H 全品种 | `python scripts/data_management.py --daily --1h` |
| 仅 1H | `python scripts/data_management.py --1h` |
| 校验+卫生 | `python scripts/data_management.py --validate` |
| 直调日线 | `python scripts/daily_update.py ss fu` |

### Timeout（全品种 n≈26）

| 子脚本 | 约秒数 |
|--------|------:|
| collect_1h | 1170 |
| pull_history_1h | 1560 |
| daily_update | 1300 |

公式见 `scripts/data_management.py` 中 `_timeout_for`。日志会打印 `timeout set to Xs`。

### 幽灵 K 线防护

| 规则 | 说明 |
|------|------|
| 语义 | `data.trading_calendar.max_allowed_daily_label`（会话感知） |
| 入口 | `data.future_bar_guard.run_guard` **唯一**批量入口 |
| 调用点 | `scripts/daily_update.py` 结束时；`--validate` 无采集时也会跑 |
| 失败 | daily_update **exit 2**；validate 失败亦 exit 2 |
| CLI | `python -m data.future_bar_guard [--dry-run] [--strict]` |

- **周五夜盘**：允许「下周一」交易日标签（进行中 bar 不删）
- **周六日**：上界=上周五 → 清掉未完成的下周一 partial（日线+1H）
- **不含法定节假日日历**（长假后需人工关注）

## 健康检查

```bash
python -m data.cli status
python scripts/data_health_check.py
python -m unittest tests.test_future_bar_guard tests.test_vol_threshold_contract -v
```

## 故障速查

| 现象 | 排查 |
|------|------|
| `VolRiskFilter model not found` | 是否在错误盘符/无 models pkl；路径应解析到 `FM_ROOT/models/...` |
| daily_update exit 2 | `run_guard` 报错；看 stderr / 库锁 |
| 采集 timeout | 看日志 timeout 秒数；可直调 `daily_update.py` / `collect_1h.py` |
| TqSdk Event loop closed | 多为清理噪音；exit code 0 且有业务输出时调度层可判成功 |
| 周末日线停在「周一」且量很小 | 应被 guard 清掉；跑 `python -m data.future_bar_guard` |

## Live Ledger（Phase L）

预测事件账本（与行情 `futures_*.db` 分离）：

| 路径 | 说明 |
|------|------|
| `db/live_ledger.db` | SQLite WAL；表 `prediction_runs` |
| `cascade/live_ledger.py` | insert / query / backfill / health API |
| `scripts/ledger_backfill.py` | 从 1H 回填 actual |
| `scripts/live_cov_health.py` | 分层统计 + candidates |

```bash
# Copilot 成功推理后自动写入 source=copilot
python scripts/copilot.py ss --no-collect

# 回填未完成 runs
python scripts/ledger_backfill.py --all-unfilled --limit 50

# Phase S 健康 / 弱 cov 候选
python scripts/live_cov_health.py --json-out reports/live_cov_health/latest.json
```

## A2-P1 完整性工具（2026-08-07 硬化）

> 全部为纯磁盘操作，**不加载 TimesFM 模型，不启动真实回测**。

| 工具 | 命令 | 说明 |
|------|------|------|
| 扫描 | `python scripts/a2_p1_restore_manifest.py --dry-run` | 扫描主目录 + 备份目录，打印 20 品种状态 |
| 去重 | `python scripts/a2_p1_restore_manifest.py --canonicalize` | 对重复写入的 JSONL 按 `bar_idx` 去重，写 `.canonical` 文件 |
| 恢复 | `python scripts/a2_p1_restore_manifest.py --restore` | 从备份恢复缺失文件到主目录（`apply=True` 才写磁盘） |
| 报告 | `python scripts/a2_p1_generate_report.py --run-id {a2-p1,a2-p1.1}` | 生成 fail-closed 门禁裁决报告 |
| 编排 | `python scripts/a2_p1_orchestrator.py --run-id {a2-p1,a2-p1.1}` | 调度 Worker 子进程运行回测（带品种级隔离 + 断点续跑） |
| Manifest | `python scripts/a2_p1_restore_manifest.py --write-manifest` | 生成 `reports/a2_p1_manifest.json` 磁盘事实清单 |

**结果目录：**
- 主目录：`reports/a2_p1_results/`
- 备份目录：`reports/a2_p1_results_backup/`
- 日志目录：`reports/a2_p1_logs/`
- Manifest：`reports/a2_p1_manifest.json`

**状态定义：**
- `complete` — 唯一 bar 数 = 396（预期值），无重复
- `partial` — 有数据但唯一 bar 数 < 396
- `duplicated` — 存在重复写入（并发追加导致），需 `--canonicalize` 去重
- `missing` — 主目录和备份目录均无文件

## A2-P2 残差叠加工具（2026-08-07 完成）

> A2-P2 测试 LGBM 残差叠加架构，已于 2026-08-07 执行完毕，裁决为 0/5 GO。

| 工具 | 命令 | 说明 |
|------|------|------|
| 报告 | `python scripts/a2_p2_generate_report.py --run-id a2-p2` | 生成三曲线对比裁决报告（pure/scheme/stacked） |
| 编排 | `python scripts/a2_p2_orchestrator.py --run-id a2-p2` | 调度 Worker 子进程运行残差训练回测 |

**结果目录：**
- 结果：`reports/a2_p2_results/`（5 品种 JSONL）
- 日志：`reports/a2_p2_logs/`
- 裁决报告：`reports/research/20260807_a2_p2_verdict.md`

**技术要点：**
- 复用 A2-P1 TimesFM 缓存（`reports/a2_p1_features/`）
- A2-P2 允许部分 bar 的 scheme 失败（验证逻辑分 run_id 处理）
- 报告生成器扫描实际结果文件而非使用全部 SYMBOLS

## 相关产物目录

| 路径 | 用途 |
|------|------|
| `db/live_ledger.db` | Live 预测账本 |
| `reports/daily/` | Copilot 研报 |
| `reports/data_ops/` | 采集/审计日志 |
| `reports/phase1/` | Neutral / R1 回测 |
| `models/` | vol / regime pkl + `operational_thr.json` |
