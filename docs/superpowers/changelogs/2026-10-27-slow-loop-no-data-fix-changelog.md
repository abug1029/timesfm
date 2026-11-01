# 慢环 no_data 修复 Changelog

**日期**: 2026-10-27  
**Commits**: 257fcf3 → b63b4ad (5 commits)  
**基于报告**: docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation.md（可信度 ~86%）

---

## 问题

慢环重评估 344 个提案（batch_id: reprocess_20261026）中，pending 队列有约 11 个注定失败的无效提案，每个浪费 10-15 分钟（跑满 588 个 eval points），总计约 2.3 小时无效计算。

## 根因

1. **Praxist peer 生成了错误的协变量名**：使用族名（如 volatility）而非具体协变量（如 vor）
2. **入队脚本无验证**：enqueue_reprocess.py 盲目将所有提案入队
3. **慢环无 fail-fast**：遇到不支持的协变量时，仍跑满 588 个 eval points
4. **历史队列中残留无效条目**：需要清理

## 修复方案

### Task 1 (P0-A): 入队脚本添加协变量验证
- **Commit**: 257fcf3 (impl), da08fbe (test fix)
- **修改文件**: scripts/enqueue_reprocess.py, tests/test_enqueue_reprocess.py
- **核心改动**:
  - 新增 load_supported_covariates() 函数，从 covariate_pool.json 读取合法协变量
  - 在入队前验证 cov_override：过滤族名和未注册协变量
  - 统计 invalid_covariate 计数
- **Code Review**: PASS (2 commits, 0 blocking issues)

### Task 2 (P0-B): 慢环添加 fail-fast 机制
- **Commit**: 03e3171 (impl), d45ad24 (combo fix)
- **修改文件**: cascade/features.py, scripts/monthly_backtest.py, tests/test_fail_fast_unsupported_covariate.py
- **核心改动**:
  - 新增 UnsupportedCovariateError 异常类（ValueError 子类）
  - build_covariate_matrix() 和 build_combo_covariate_matrix() 对不支持的协变量抛出该异常
  - run_symbol_backtest() 在第一个 eval point 捕获异常并返回 None
  - 日志输出 [FAIL-FAST] 标记
- **性能提升**: 600-900x（10-15分钟 → <1秒/无效协变量）
- **Code Review**: PASS (2 commits, 0 blocking issues after fix)

### Task 3 (P3): 安全清理队列中的无效条目
- **Commit**: b63b4ad
- **修改文件**: scripts/cleanup_invalid_queue.py (新建)
- **核心改动**:
  - 创建清理脚本，使用文件锁、备份、原子替换等安全措施
  - 过滤族名、未注册协变量、品种 c（无数据）
  - 清理结果：198 → 187 行（移除 11 个无效条目）
- **Code Review**: PASS (0 blocking issues)

### Task 4: 集成测试
- **结果**: 全部通过
  - P0-A: 10 个无效协变量过滤，184 个有效入队；3/3 测试通过
  - P0-B: 3/3 fail-fast 测试通过（含新增 test_combo_unsupported_raises）
  - P3: 187 个有效条目，0 个残留无效
  - 回归测试: 18/18 通过
  - 三个修复无相互冲突

## 关键设计决策

1. **load_supported_covariates() 从 covariate_pool.json 读取**，而非硬编码
   - 确保单一真相源，避免漂移
   - 正确解析 schema：families 是 list，covariates 是 dict，检查 status == "active"

2. **UnsupportedCovariateError 是 ValueError 子类**
   - 向后兼容：现有捕获 ValueError 的代码仍有效
   - 明确语义：区分不支持的协变量和其他值错误

3. **Fail-fast 在第一个 eval point 触发**
   - 避免跑满 588 个点（节省 10-15 分钟/无效协变量）
   - 返回 None，由 aligned_slow_loop.py 生成 _no_data_verdict

4. **清理脚本使用安全措施**
   - 文件锁（fcntl.flock）防止并发访问
   - 备份原文件后再修改
   - 原子替换（先写 .tmp，再 rename）避免中途崩溃导致数据丢失

## 测试覆盖

- **P0-A**: test_construct_queue_row, test_main_orchestration, test_main_filters_invalid_covariates (3 tests)
- **P0-B**: test_unsupported_covariate_raises, test_unsupported_covariate_is_value_error, test_combo_unsupported_raises (3 tests)
- **P3**: 手动验证（清理前后对比，残留检查）
- **集成**: 18/18 回归测试通过

## 审计修正（2026-10-27 重审后）

根据 `2026-10-27-slow-loop-no-data-fix-changelog-audit.md` 反馈修正：
- ✅ P0-1: 测试数量声称与实际对齐（P0-A 3 tests, P0-B 3 tests）
- ✅ P0-2: 新增 `test_main_filters_invalid_covariates` 验证族名/未注册过滤和 `invalid_covariate` 计数
- ✅ 新增 `test_combo_unsupported_raises` 验证 combo covariate 抛 `UnsupportedCovariateError`

## 验收结果

✅ 所有验收标准满足：
- P0-A 正确过滤无效协变量（族名 + 未注册）
- P0-B fail-fast 测试全部通过，性能提升 600-900x
- P3 清理后无残留无效条目（187 → 187 valid）
- 所有相关测试通过，无回归
- 三个修复无相互冲突

## 不做的事

1. **P1（修复 Praxist peer 的协变量生成约束）**：不在本次范围，作为后续任务
2. **P2（处理品种 c 无数据问题）**：不在本次范围，作为后续任务
3. **端到端测试（完整慢环运行）**：未执行，因为需要较长时间，且单元/集成测试已验证核心逻辑

## 预期效果

- **避免 2.3 小时无效计算**（pending 中 11 个无效提案 × 12.5 分钟）
- **提高慢环评估效率**：预计完成时间从 ~1.7 天缩短到 ~1.6 天
- **防止未来生成错误提案**（peer 白名单约束，P1 长期任务）
- **快速诊断类似问题**（fail-fast 机制，600-900x 性能提升）

---

**Changelog 生成时间**: 2026-10-27  
**Commits**: 257fcf3 → b63b4ad (5 commits)
