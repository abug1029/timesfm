# 慢环 no_data 修复实施计划

**生成时间**: 2026-10-27  
**基于报告**: `docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation.md`（重审修订版，可信度 ~86%）  
**目标**: 修复慢环评估中的无效协变量问题，避免时间浪费

---

## 背景

### 问题总结

1. **Praxist peer 生成了错误的协变量名**：使用族名（如 `volatility`）而非具体协变量（如 `vor`）
2. **入队脚本无验证**：`enqueue_reprocess.py` 盲目将所有提案入队，包括无效提案
3. **慢环无 fail-fast**：遇到不支持的协变量时，仍跑满 588 个 eval points，浪费 10-15 分钟
4. **当前 pending 队列中约 11 个注定失败**：需要清理（全 batch 历史 doomed 约 31 个，但大部分已在 done 队列）

### 预期效果

- **避免 2.3 小时无效计算**（pending 中 11 个无效提案 × 12.5 分钟）
- **提高慢环评估效率**：预计完成时间从 ~1.7 天缩短到 ~1.6 天
- **防止未来生成错误提案**（peer 白名单约束，P1 长期任务）
- **快速诊断类似问题**（fail-fast 机制）

---

## 实施任务

### Task 1: P0-A - 入队脚本添加协变量验证

**目标**: 在 `scripts/enqueue_reprocess.py` 中添加协变量验证，过滤无效提案

**修改文件**:
- `scripts/enqueue_reprocess.py`

**实现步骤**:

1. **添加 `load_supported_covariates()` 函数**:
   ```python
   def load_supported_covariates():
       """从 covariate_pool.json 读取合法协变量名
       
       注意 covariate_pool.json 的实际 schema：
       - families: list[str] - 族名列表（用于禁止族名当 cov_override）
       - covariates: dict[str, dict] - key 是协变量名，value 包含 status/family/mechanism 等
       - 合法协变量的 status == "active"
       
       常见错误（审计发现）：
       - ❌ pool["families"].values() - families 是 list 不是 dict
       - ❌ cov.get("active") - 应该检查 cov_data.get("status") == "active"
       - ✅ pool.get("covariates", {}).items() + cov_data.get("status") == "active"
       """
       pool_path = Path("task_FM/config/covariate_pool.json")
       with open(pool_path) as f:
           pool = json.load(f)
       
       # covariates 是顶层 dict，key 是协变量名
       # 提取所有 status == "active" 的协变量名
       supported = set()
       for cov_name, cov_data in pool.get("covariates", {}).items():
           if cov_data.get("status") == "active":
               supported.add(cov_name)
       
       # 添加特殊别名
       supported.update({"slope_only", "none", "baseline"})
       
       # families 是族名列表，可用于「禁止族名当 cov_override」检查
       family_names = set(pool.get("families", []))
       
       return supported, family_names
   ```

2. **在 `main()` 函数中添加验证逻辑**:
   ```python
   def main(experiments_dir, verdict_path, queue_path, batch_id):
       # ... 现有代码 ...
       
       _SUPPORTED_COVARIATES, _FAMILY_NAMES = load_supported_covariates()
       
       # 在 filter_existing_verdicts 之后，添加协变量验证
       valid_proposals = []
       invalid_count = 0
       for proposal in filtered_proposals:
           # 检查是否是族名（常见错误）
           if proposal.cov_override in _FAMILY_NAMES:
               invalid_count += 1
               print(f"Warning: skipping {proposal.variant_id} - "
                     f"cov_override='{proposal.cov_override}' is a family name, not a covariate")
           # 检查是否在已注册协变量中
           elif proposal.cov_override not in _SUPPORTED_COVARIATES:
               invalid_count += 1
               print(f"Warning: skipping {proposal.variant_id} - "
                     f"cov_override='{proposal.cov_override}' not in registry")
           else:
               valid_proposals.append(proposal)
       
       stats["invalid_covariate"] = invalid_count
       stats["to_enqueue"] = len(valid_proposals)
       
       # ... 后续代码使用 valid_proposals 而不是 filtered_proposals ...
   ```

3. **测试**:
   - 运行入队脚本，验证能正确过滤族名和未注册协变量
   - 检查统计信息中 `invalid_covariate` 计数

**验收标准**:
- ✅ 族名（如 `volatility`, `momentum`）被正确过滤
- ✅ 未注册协变量（如 `macro_sentiment_composite`）被正确过滤
- ✅ 合法协变量（如 `vor`, `rsi_slope`）正常入队
- ✅ 统计信息正确显示 `invalid_covariate` 计数

**预计工时**: 1-2 小时

---

### Task 2: P0-B - 慢环/回测添加 fail-fast 机制

**目标**: 在 `monthly_backtest.py` 或 `cascade/features.py` 中添加快速失败机制，遇到不支持的协变量时立即返回，避免跑满 588 个 eval points

**修改文件**:
- `scripts/monthly_backtest.py`（推荐）或 `cascade/features.py`

**实现步骤**:

1. **在 `run_symbol_backtest()` 中添加快速失败**:
   ```python
   def run_symbol_backtest(symbol, cov_override, ...):
       # 在第一个 eval point 就检测不支持的协变量
       try:
           # 尝试构建第一个点的协变量矩阵
           build_covariate_matrix(cov_override, ...)
       except ValueError as e:
           if "不支持 covariate_type" in str(e):
               # Fail-fast：立即返回，不继续跑 588 个点
               print(f"  [FAIL-FAST] cov_override='{cov_override}' not supported, skipping all eval points")
               return None  # 或返回特定的失败标记
       
       # ... 现有代码 ...
   ```

2. **或者在 `build_covariate_matrix()` 中抛出更明确的异常**:
   ```python
   def build_covariate_matrix(covariate_type, ...):
       if covariate_type not in _REGISTERED_COVARIATES:
           raise UnsupportedCovariateError(
               f"不支持 covariate_type='{covariate_type}'。"
               f"合法协变量见 task_FM/config/covariate_pool.json"
           )
       # ... 现有代码 ...
   ```

3. **定义新的异常类**（可选）:
   ```python
   class UnsupportedCovariateError(ValueError):
       """协变量未注册异常"""
       pass
   ```

4. **在 `aligned_slow_loop.py` 中处理该异常**:
   ```python
   try:
       result = run_symbol_backtest(...)
   except UnsupportedCovariateError as e:
       # 立即返回 no_data verdict，不浪费时间
       verdict = _no_data_verdict(row, batch_id=bid, reason="unsupported_covariate")
       rl.append_verdict(registry_path, verdict)
       continue
   ```

**测试**:
- 运行慢环，验证遇到不支持的协变量时立即返回
- 检查日志中是否有 `[FAIL-FAST]` 标记
- 验证 verdict 中 `status` 字段能区分 `no_data` 和 `unsupported_covariate`

**验收标准**:
- ✅ 遇到不支持的协变量时，立即返回（不跑满 588 个点）
- ✅ 日志中有明确的 `[FAIL-FAST]` 标记
- ✅ verdict 中能区分 `no_data` 和 `unsupported_covariate`（可选）
- ✅ 不影响正常协变量的评估流程

**预计工时**: 2-3 小时

---

### Task 3: P3 - 安全清理队列中的无效条目

**目标**: 安全地清理当前 pending 队列中约 11 个注定失败的提案

**修改文件**:
- 创建 `scripts/cleanup_invalid_queue.py`（新文件）

**实现步骤**:

1. **创建清理脚本**（使用与 Task 1 相同的 `load_supported_covariates()` 函数）

2. **运行清理**:
   ```bash
   # 1. 停止慢环
   pkill -f aligned_slow_loop
   
   # 2. 运行清理脚本
   python scripts/cleanup_invalid_queue.py
   
   # 3. 验证结果
   wc -l data/cache/aligned_pending.jsonl  # 应该减少约 11 行（非 81）
   
   # 4. 重启慢环（如需要）
   python -m scripts.aligned_slow_loop --batch-id reprocess_20261026
   ```

3. **验证**:
   - 检查备份文件是否创建
   - 检查清理后的队列行数（预期减少约 11 行）
   - 验证清理的条目确实是无效的

**验收标准**:
- ✅ 备份文件创建成功
- ✅ 无效条目被正确移除（约 11 个，非 81 个）
- ✅ 有效条目保留完整
- ✅ 慢环能正常重启并继续处理

**预计工时**: 1 小时

---

### Task 4: 集成测试与验证

**目标**: 验证所有修复是否正常工作

**测试步骤**:

1. **测试 P0-A（入队验证）**:
   ```bash
   # 准备测试数据（包含无效协变量的提案）
   python -m scripts.enqueue_reprocess \
     --experiments-dir task_FM/experiments \
     --verdict-path task_FM/config/aligned_verdicts.jsonl \
     --queue-path /tmp/test_queue.jsonl \
     --batch-id test_validation
   
   # 检查输出
   grep "Warning: skipping" logs/*.log  # 应该看到族名/未注册协变量被跳过
   ```

2. **测试 P0-B（fail-fast）**:
   ```bash
   # 手动构造一个包含无效协变量的队列条目
   echo '{"variant_id":"test_volatility","symbol":"m","cov_override":"volatility",...}' \
     >> data/cache/aligned_pending.jsonl
   
   # 运行慢环（单次）
   python -m scripts.aligned_slow_loop --once --batch-id test_failfast
   
   # 检查日志
   grep "FAIL-FAST" logs/*.log  # 应该看到快速失败标记
   ```

3. **测试 P3（清理）**:
   ```bash
   # 停止慢环
   pkill -f aligned_slow_loop
   
   # 运行清理
   python scripts/cleanup_invalid_queue.py
   
   # 验证
   wc -l data/cache/aligned_pending.jsonl  # 应该减少
   ls -lh data/cache/aligned_pending.jsonl.bak.*  # 应该看到备份
   ```

4. **端到端测试**:
   ```bash
   # 完整流程：入队 → 清理 → 慢环评估
   python -m scripts.enqueue_reprocess --batch-id e2e_test
   python scripts/cleanup_invalid_queue.py
   python -m scripts.aligned_slow_loop --batch-id e2e_test
   
   # 检查结果
   tail -20 logs/reprocess_*.log
   ```

**验收标准**:
- ✅ P0-A 能正确过滤无效协变量
- ✅ P0-B 能快速失败，不浪费时间
- ✅ P3 能安全清理队列
- ✅ 端到端流程正常工作

**预计工时**: 2-3 小时

---

## 实施顺序

```
Task 1 (P0-A) → Task 2 (P0-B) → Task 3 (P3) → Task 4 (集成测试)
   1-2h           2-3h            1h              2-3h
```

**总预计工时**: 6-9 小时

**依赖关系**:
- Task 1 和 Task 2 可以并行开发
- Task 3 依赖 Task 1（使用相同的 `load_supported_covariates()` 函数）
- Task 4 依赖 Task 1/2/3 全部完成

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| `covariate_pool.json` schema 变更 | 高 | 使用 `load_supported_covariates()` 函数封装，便于维护 |
| fail-fast 误杀合法协变量 | 中 | 仔细测试，确保只拦截真正不支持的协变量 |
| P3 清理脚本并发冲突 | 中 | 使用文件锁 + 原子替换 |
| 慢环重启后状态丢失 | 低 | 使用 checkpoint 机制（已有） |

---

## 后续工作（P1/P2，不在本次计划范围）

### P1: 修复 Praxist peer 的协变量生成约束

- 在 peer prompt 中明确列出 31 个已注册协变量名白名单
- 禁止使用族名作为 `cov_override`
- 添加验证逻辑，确保生成的协变量名在 `covariate_pool.json` 中

**预计工时**: 4-6 小时（需修改 Praxist 代码）

### P2: 处理品种 `c` 无数据问题

- 确定玉米品种是否应该退役
- 如果退役：在入队脚本过滤 `symbol == "c"`
- 如果保留：修复数据管道，补充 `c` 的 1h/daily 数据

**预计工时**: 2-4 小时

---

## 关键文件路径

| 文件 | 作用 |
|------|------|
| `scripts/enqueue_reprocess.py` | 入队脚本（Task 1 修改） |
| `scripts/monthly_backtest.py` | 回测脚本（Task 2 修改） |
| `scripts/cleanup_invalid_queue.py` | 清理脚本（Task 3 新建） |
| `task_FM/config/covariate_pool.json` | 协变量池（31 个 active） |
| `data/cache/aligned_pending.jsonl` | 待评估队列 |
| `logs/reprocess_20261026.log` | 慢环日志 |

---

## 重要修订说明（根据审计报告 2026-10-27）

### 修订 1：`load_supported_covariates()` 函数 schema 修正

**审计发现的问题**：
- ❌ 错误写法：`pool["families"].values()` - `families` 是 list 不是 dict，会导致 `AttributeError`
- ❌ 错误写法：`cov.get("active")` - 应该检查 `cov_data.get("status") == "active"`
- ✅ 正确写法：`pool.get("covariates", {}).items()` + `cov_data.get("status") == "active"`

**`covariate_pool.json` 实际 schema**：
```json
{
  "families": ["momentum", "volatility", "inventory", "calendar", "term_structure", "macro_sentiment"],
  "covariates": {
    "oi": {"status": "active", "family": "inventory", "mechanism": "..."},
    "rsi_slope": {"status": "active", "family": "momentum", "mechanism": "..."},
    ...
  }
}
```

**关键区别**：
- `families`：list[str]，族名列表（禁止作为 `cov_override`）
- `covariates`：dict[str, dict]，key 是协变量名，value 包含 `status`/`family`/`mechanism` 等
- 合法协变量：`status == "active"` 的条目

### 修订 2：清队数量预期修正

**审计发现的问题**：
- ❌ 原估计：~81 个 doomed（高估）
- ✅ 实际：pending 中约 11 个，全 batch 历史 doomed 约 31 个（大部分已在 done 队列）

**修订原因**：
- 全 batch 历史 doomed 约 31 个（18 族名 + 10 幻觉名 + 3 品种 c）
- 但大部分已在 done 队列中（已完成 138 条）
- 当前 pending 队列 ~210 条，其中注定失败约 11 条
- 清理脚本只清理 pending 中的无效条目，预期减少约 11 行

### 修订 3：预期效果修正

**修订前**：避免 ~81 个无效提案 × 12.5 分钟 ≈ 16.9 小时  
**修订后**：避免 11 个无效提案 × 12.5 分钟 ≈ 2.3 小时

---

## 验收清单

- [ ] Task 1: P0-A 入队验证实现并测试通过
- [ ] Task 2: P0-B fail-fast 机制实现并测试通过
- [ ] Task 3: P3 清理脚本实现并测试通过
- [ ] Task 4: 集成测试全部通过
- [ ] 代码提交并推送到备份仓库
- [ ] 更新报告文档，记录实施结果

---

**计划路径**: `/home/abug/timesfm/docs/superpowers/plans/2026-10-27-slow-loop-no-data-fix-plan.md`

**计划制定人员**: AI Agent  
**基于报告**: `2026-10-27-slow-loop-no-data-investigation.md`（重审修订版，可信度 ~86%）  
**计划状态**: ✅ 已根据审计反馈修订（2026-10-27）  
**审计报告**: `2026-10-27-slow-loop-no-data-investigation-audit.md`（可信度 ~86%）

**关键修订**：
1. ✅ 修正 `load_supported_covariates()` 函数 schema（families 是 list，covariates 是 dict）
2. ✅ 修正清队数量预期：~11 个（非 ~81 个）
3. ✅ 修正预期效果：避免 2.3 小时无效计算（非 16.9 小时）
