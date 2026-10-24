# Laya 预筛调用优化 Changelog

**日期**: 2026-10-24  
**作者**: FM研  
**状态**: 完成（Day 1 P0 + Day 2 P1 全闭环）  
**Commits**: `6d13936` → `5fd2958` → `8e0916c` → `d8f741c` → `d2ab765` → `bda45d9`  
**Spec**: `docs/superpowers/specs/2026-10-23-laya-prescreen-optimization-spec.md`  
**Plan**: `docs/superpowers/plans/2026-10-24-laya-prescreen-optimization.md`

---

## 问题

Laya 预筛服务在高负载时频繁 503（85/94 失败），但客户端熔断器仅覆盖 timeout，不覆盖 503 → 熔断永远不打开。同时 state 含中文板块名 + 历史模板 → 触发 checkpoint 切换惩罚。

## 根因

1. `_call_laya` 把所有异常（含 503）吞掉后统一抛 `ConnectionError`
2. `_prescreen_impl` 仅对 `TimeoutError` 调 `_record_timeout()`
3. 503 / `ConnectionError` 走 `Exception` 分支，**永不触发熔断**
4. `_build_state` 注入中文 `SECTOR_NAMES` + `_extract_relevant_history` 含中文模板

## 修复方案

### Day 1 P0（3 commits）
- **Task 1** (`6d13936`): 统一 failure 分类 + 503 进熔断
  - 新增 `LayaUnavailableError`，`_call_laya` 503 re-raise 不试第二端点
  - `_prescreen_impl` 五分支捕获（503 / timeout / connection / auth / unknown）
  - `_record_failure(reason)` 统一入口
- **Task 2** (`5fd2958`): 三态熔断器（CLOSED→OPEN→HALF_OPEN + 探针锁）
  - `CircuitBreaker` 类 + `threading.Lock` + `_parse_bool_env`
  - 改写旧测 `test_half_open_resets_on_expire`
- **Task 3** (`8e0916c`): timeout 分档（10s + 5s fallback）
  - `_TIMEOUT_PRIMARY=10.0` + `_TIMEOUT_FALLBACK=5.0`

### Day 2 P1（3 commits）
- **Task 4** (`d8f741c`): state 关键路径英文化（sector + history）
  - `SECTOR_NAMES_EN`（不改共享 `SECTOR_NAMES`）
  - `_build_state` 用英文 sector + `_extract_relevant_history` 模板英文化
- **Task 5** (`d2ab765` + `bda45d9`): 队列感知退避（滑动窗口 p80 > 20s 跳过，< 15s 恢复）
  - `_latency_window` + `_latency_lock` + 滞后防抖
  - **修复**: p80 热身期（n=5-9）索引错误

## 关键设计决策

1. **`LayaUnavailableError` vs `LayaTimeoutError`**: 503 立即 re-raise 不试第二端点（共享队列）
2. **三态熔断 + 探针锁**: HALF_OPEN 仅允许 1 个探针，防惊群
3. **`SECTOR_NAMES_EN` 不替换 `SECTOR_NAMES`**: 中文 value 仍供其他模块使用
4. **Scope 收窄**: Task 4 仅英文化 `sector` + `history`，不动 `contract_details` / `covariate_menu`
5. **p80 分档计算**: `n>=10` 用 `sorted[-3]`，`n<10` 用 `int(n*0.8)-1`

## 测试覆盖

- **新测试文件**: 5 个（`test_laya_failure_classification.py` / `test_circuit_breaker.py` / `test_laya_timeout_tiers.py` / `test_laya_state_english_only.py` / `test_laya_queue_backoff.py`）
- **新测试数**: ~20 个
- **全量测试**: 100 passed, 0 failed

## 验收结果

- [x] 503 / timeout / ConnectionError 全部触发熔断
- [x] 连续 3 次 failure → OPEN
- [x] OPEN 5 分钟后 → HALF_OPEN（仅 1 个探针）
- [x] HALF_OPEN 探针成功 → CLOSED；失败 → OPEN
- [x] `sector` + `history` 无中文字符
- [x] 503 快速失败 < 1s（不试第二端点）
- [x] 预筛失败不影响慢环回测（软降级 `status="degraded"`）
- [x] 日志可追溯（延迟、状态、熔断器状态、failure 原因）
- [x] 配置项可回滚（`LAYA_CIRCUIT_BREAKER_ENABLED` / `THRESHOLD` / `DURATION`）
- [x] 队列感知退避：p80 > 20s 跳过，p80 < 15s 恢复（滞后防抖）

## 不做的事

- 不修改服务端（不碰 Laya `serve.py` / worker / 队列）
- 不硬阻断慢环（预筛仍是软建议模式）
- 不引入新依赖（只用现有 `requests`）
- 不动 `SECTOR_NAMES`（中文 value 保留）
- 不动 `contract_details` / `covariate_menu`（scope 收窄）

## 回滚方案

若优化后预筛成功率下降，可：
1. 设 `LAYA_CIRCUIT_BREAKER_ENABLED=false` 关闭熔断
2. 调整 `LAYA_CIRCUIT_BREAKER_THRESHOLD` / `DURATION`
3. `git revert bda45d9 d2ab765 d8f741c 8e0916c 5fd2958 6d13936`（按逆序）
