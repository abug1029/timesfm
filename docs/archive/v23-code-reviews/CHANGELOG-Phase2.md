# Phase 2 Changelog - 统计检验层 (Task 3-6)

**日期**: 2026-09-15  
**分支**: `feat/prediction-quality-redesign-v23`  
**状态**: ✅ 完成，代码审核通过

---

## 变更摘要

Phase 2 实现了预测质量评估的统计检验层，包括时间戳归一化、Diebold-Mariano 检验、BH-FDR 多品种校正、协变量家族分类。

---

## Task 3: 时间戳归一化 + Inner Join 配对

### 文件变更
- **新增** `cascade/statistical_tests.py` (154 行)
- **新增** `tests/test_statistical_tests.py` (初始 5 个测试)

### 功能实现
1. **`safe_normalize_cutoff(ts)`**: 将各种格式的时间戳统一为 Unix 秒（Asia/Shanghai 时区）
   - 支持 str/int/float/None/numpy scalar
   - 自动检测毫秒（>1e12 → /1000）
   - tz-aware 转换为 Asia/Shanghai
   - tz-naive 假设 Asia/Shanghai

2. **`pair_dir_ok_series(variant, baseline)`**: 按归一化时间戳 Inner Join 配对 dir_ok 值
   - 支持 tuple 和 dict 两种输入格式
   - 按时间升序排序
   - dir_ok 转为 int (0/1)

### 代码审核修复 (commit cfb1cc3)
- **[HIGH]** 时区检测逻辑：改用 `dt.tzinfo` 检测而非字符计数
- **[MEDIUM]** ZoneInfo 移到模块顶部，避免重复导入
- **[MEDIUM]** 'Z' 替换只针对末尾
- **[MEDIUM]** numpy scalar 检测用 `ndim == 0`
- **[MEDIUM]** pair_dir_ok_series 输入验证
- **[LOW]** 移除 set() 冗余

### 测试结果
- 15/15 测试通过
- 覆盖边界情况：numpy scalar、空列表、缺失 key、短 tuple 等

### Commits
- `9fd5c95` - feat(stats): cutoff normalize and inner-join dir_ok pairing
- `cfb1cc3` - fix(stats): improve timezone detection and input validation

---

## Task 4: Diebold-Mariano 检验

### 文件变更
- **修改** `cascade/statistical_tests.py` (+80 行)
- **修改** `tests/test_statistical_tests.py` (+5 个测试)

### 功能实现
**`diebold_mariano_p(variant_values, baseline_values, horizon=24, step=24)`**: 单侧 DM 检验
- H0: variant 不优于 baseline
- H1: variant 优于 baseline

**关键实现**:
1. **Loss 转换**: `loss = 1 - dir_ok`（将"越高越好"转为"越低越好"）
2. **Newey-West HAC**: Bartlett 核，`/T` 归一化
3. **HLN 统计量**: `DM_adj = d_bar / sqrt(V)`
4. **单侧 p 值**: `scipy.stats.t.sf(-dm_adj, df=T-1)`

**边界条件**:
- T < 100 → 1.0（保守）
- d_bar > 0 → 1.0（variant 更差）
- V <= 1e-12 且 d_bar < -1e-12 → 0.0（完美显著）
- 相同序列 → 1.0

### 代码审核结果
- ✅ APPROVE
- Loss 转换正确
- Newey-West HAC / HLN 统计量正确

### 测试结果
- 5/5 专项测试通过
- 20/20 全部统计测试通过

### Commits
- `f14b3d5` - feat(stats): Diebold-Mariano test with HAC and HLN

---

## Task 5: BH-FDR 多品种校正

### 文件变更
- **修改** `cascade/statistical_tests.py` (+70 行)
- **修改** `tests/test_statistical_tests.py` (+6 个测试)

### 功能实现
**`bh_fdr_promote(verdicts, fdr_q=0.10, min_batch_size=4, bonferroni_alpha=0.025)`**: 按品种 BH-FDR 校正
- 按 symbol 分组独立计算
- K < 4 → Bonferroni（固定阈值 0.025）
- K >= 4 → BH-FDR 步进法
- gate_pass=False → fdr_pass=False

**关键实现**:
1. **去重**: variant_id 重复时后写覆盖
2. **排序**: (safe_p, variant_id) 保证确定性
3. **不修改入参**: 只返回 all_updates dict

### 代码审核结果
- ✅ APPROVE
- BH-FDR 算法正确
- Bonferroni fallback 正确

### 测试结果
- 6/6 专项测试通过
- 26/26 全部统计测试通过

### Commits
- `3fa0011` - feat(stats): per-symbol BH-FDR with Bonferroni small-batch fallback

---

## Task 6: 协变量家族分类

### 文件变更
- **新增** `config/covariate_pool.json` (16 行)
- **新增** `cascade/cov_family.py` (100 行)
- **新增** `tests/test_cov_family.py` (8 个测试)

### 功能实现
1. **`load_covariate_pool(pool_path=None)`**: 加载协变量池 JSON
   - 支持 dict 格式（covariates / pool）和 list 格式

2. **`resolve_cov_family(verdict, covariate_pool=None)`**: 三级回退解析
   - Level 1: 池精确匹配 name == cov_override
   - Level 2: 关键词启发式（正则 lookaround 边界匹配）
   - Level 3: "unknown"

**受控词表** (6 个族):
- momentum, volatility, inventory, calendar, term_structure, macro_sentiment

### 代码审核修复 (commit 4dabd95)
- **[HIGH]** 短关键词误匹配：改用 lookaround `(?<![a-zA-Z0-9])` / `(?![a-zA-Z0-9])`（不用 `\b`，因为 Python \b 把 _ 当 word char）
- **[MEDIUM]** 补充 5 个测试用例
- **[LOW]** 修正规格引用
- **[LOW]** 明确 "unknown" 过滤责任

### 测试结果
- 8/8 测试通过
- 覆盖：池格式、Level 1 回退、空输入、子串误匹配防护

### Commits
- `0f4c0db` - feat(eval): cov_family controlled vocabulary and resolver
- `4dabd95` - fix(eval): use word boundary matching for cov_family heuristics

---

## 技术亮点

1. **时区处理**: 统一 Asia/Shanghai，正确处理 tz-aware/naive
2. **数值安全**: 所有除法都有分母保护
3. **正则优化**: 预编译 pattern，lookaround 边界匹配
4. **防御性编程**: 输入验证、边界条件完备
5. **测试覆盖**: 34 个测试覆盖核心逻辑和边界情况

---

## 待审核项

- [ ] Phase 2 代码实现
- [ ] 代码审核修复
- [ ] 测试覆盖率
- [ ] 文档完整性

---

## 下一步

继续执行 **Phase 3: 数据管道层** (Task 7-8):
- Task 7: Registry 原子写 + v2 字段 + 墓碑
- Task 8: monthly_backtest 质量口径

---

**审核人**: 待指定  
**审核日期**: 待指定
