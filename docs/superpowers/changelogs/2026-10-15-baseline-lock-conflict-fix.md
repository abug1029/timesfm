# 2026-10-15 基线重生锁冲突修复

## 变更摘要

修复基线重生过程中的并发锁冲突问题，引入冷却期和频率限制机制，优化重生阈值。

## 主要变更

- **Phase 1**: SymbolLock 类 + incremental 接入 SymbolLock（与 gbp 同路径 flock；gbp 内联锁未迁）+ metrics 同步
- **Phase 2**: 冷却期(2h) + 频率限制(24h) + breaker schema 扩展
- **Phase 3**: 阈值调整 168h → 336h + 覆盖度测量工具
- **Phase 4**: 集成验证通过（10 个测试，6.49s）

## 测试结果

10 passed in 6.49s

**测试环境**：
`PYTHONPATH=scripts:.`


## 文件清单

- scripts/lock_utils.py（新建）
- scripts/incremental_baseline.py（修改）
- scripts/sup_evidence.py（修改）
- scripts/check_baseline_coverage.py（新建）
- tests/test_lock_utils.py（新建）
- tests/test_regen_cooldown.py（新建）

## Git 提交

- 9c402bd Phase 1.1-1.2
- 165e285 Phase 1.4
- 73f1c80 Phase 2
- c6fcbe3 Phase 3
- 1fb1c6b Phase 4
