# 清理与修复日志 2026-09-19

## 1. /workspace Permission denied 修复

**问题**：`scripts/praxist_assets_archive.py:18` 默认路径 `PRAXIST_ASSETS_ROOT=/workspace/shared/praxist_assets`，WSL 下 `/workspace` 不存在，每次 harvest/slow_loop 都报 Permission denied。

**修复**：默认路径改为 repo 本地 `data/assets/`（`Path(__file__).resolve().parents[1] / "data" / "assets"`）。已 `.gitignore`。

**验证**：`from scripts.praxist_assets_archive import ASSETS` → `/home/abug/timesfm/data/assets` ✓

## 2. 磁盘清理

| 操作 | 清理量 | 说明 |
|---|---|---|
| `data/cache/daily_pred/` >7天 .pkl | 6,694 文件 / ~53M | Sep 8~12 旧预测缓存 |
| `logs/supervisor_20260914_*.log` | 9 个空文件 | Sep 14 旧实例残留 |
| `docs/superpowers/reports/` 旧报告 | 5 文件 → `docs/archive/superpowers-reports-pre-0919/` | Sep 7~11 旧报告 |
| `aligned_checkpoints/` DEAD/HOLD 品种 | 45 文件 / 14M → `_archived_dead_hold/` | eg(25) + jd(11) + lh(9) |

## 3. 归档操作（本次会话）

| 操作 | 量 | 说明 |
|---|---|---|
| `task_FM/experiments/run_2026-09-{07..17}_*` → `docs/archive/peer-proposals-pre-0918/` | 146 runs / 128M | 9-18 前 peer 提案归档 |

## 4. 清理后磁盘

| 目录 | 清理前 | 清理后 |
|---|---|---|
| `data/cache/daily_pred/` | 118M (14,873) | 65M (8,179) |
| `data/cache/aligned_checkpoints/` | 32M (113) | 19M (68) |
| `task_FM/experiments/` | 296M | 168M |
| `logs/` | 9 个空文件 | 0 |

## 5. 未执行（低优先级）

- 小红书/闲鱼记忆文件归档（4+1 个 .md）——非磁盘问题，保留备查
- `data/cache/slow_loop.out` truncate（2.6M，暂不影响）

---
*2026-09-19 18:30 UTC+8*
