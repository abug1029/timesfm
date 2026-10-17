# Changelog: 基线重生锁冲突修复 + SC 品种移除 + 增量生成

**日期**：2026-10-14  
**commit**：3dea3d4  
**影响范围**：基线重生流程、品种配置、运维脚本

## 问题摘要

### 问题 1：基线重生锁冲突（P0）

**现象**：多个 ensure_baselines 进程并发运行导致品种锁冲突  
**修复**：scripts/sup_evidence.py 添加 _acquire_ensure_lock() 全局锁

### 问题 2：SQLite 数据库锁定（P1）

**现象**：daily_update.py 和 ensure_baselines 报 database is locked  
**修复**：data/db.py init_db() 添加 timeout=30.0 + data/data_store.py 添加写路径重试

### 问题 3：进程互斥（P1）

**现象**：多个 daily_update.py 实例并发运行  
**修复**：scripts/daily_update.py 添加进程互斥锁

### 问题 4：品种锁等待逻辑（P1）

**现象**：品种锁获取失败立即抛异常  
**修复**：scripts/generate_baseline_points.py 品种锁等待改为最多 1 小时

## 新增功能

### SC 品种移除

- 删除 db/futures_sc.db（8.8 MB）
- 删除所有 SC 基线文件和配置
- data/config.py 移除 SC 配置
- 品种数量从 25 减少到 24

### 新增运维脚本

- scripts/cleanup_baseline_locks.sh：清理残留锁文件
- scripts/check_baseline_progress.py：检查基线重生进度
- scripts/incremental_baseline.py：增量基线生成

## 基线重生结果

**进度**：24/24 (100%)  
**所有品种基线末端**：2026-10-08 10:00（超过确认窗 2026-10-03）

## 文件变更统计

- 84 文件变更
- +27,465 行新增
- -5,732 行删除
- 3 个新脚本
- 1 个品种移除（SC）
