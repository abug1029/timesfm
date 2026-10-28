# 数据更新系统修复及固化计划

> **关联调研**：
> - 数据更新架构调研（Explore agent, 2026-10-11）
> - 数据更新历史演变调研（Explore agent, 2026-10-11）
> 
> **计划日期**：2026-10-11
> **计划状态**：待审阅
> **预计工时**：~3 小时（含测试）

## 1. 问题总结

### 1.1 性能问题
`data_management.py --1h --daily` 超时预算 **75 分钟**，实际跑 20+ 分钟：

| 脚本 | 行为 | 耗时预算 | 问题 |
|---|---|---|---|
| `collect_1h.py` | 拉 10000 bars/symbol（全量），写入是 INSERT OR REPLACE（增量安全） | 22 min | 拉取量浪费 |
| `pull_history_1h.py` | **全量 DELETE + INSERT 10000 bars/symbol** | 29 min | **应移除** |
| `daily_update.py` | daily 真增量，但 1H 步骤（`collect_1h_main_only`）做 DELETE + INSERT 10000 bars | 24 min | 与 collect_1h 重复劳动 |

### 1.2 历史根因
- **2026-07-15 Lesson #11** 已记录 "DELETE 全表 + INSERT 是定时炸弹"，`collect_1h.py` 修复为增量模式
- **但 `daily_update.py` 的 `collect_1h_main_only()` 未同步修复**，仍保留全量 DELETE + INSERT
- **2026-09-03 初始提交** `data_management.py` 的 `collect_1h()` 先调增量版再调全量版（`pull_history_1h.py`），使增量修复**完全无效**
- **历史教训未固化**：仅停留在 memory 文件，未落实到代码注释、测试、文档

### 1.3 退化防护缺失
- ❌ 无测试验证增量行为
- ❌ 无文档规定"数据更新必须增量"的设计原则
- ❌ 无 CI 门禁检查 DELETE 模式
- ❌ 全量退化完全依赖人工审查（已连续 6 次犯同型错误）

## 2. 修复清单

### P0-A：`daily_update.py` 的 `collect_1h_main_only()` 对齐增量模式

**文件**：`scripts/daily_update.py:155-172`

**当前代码**（全量 DELETE + INSERT）：
```python
def collect_1h_main_only(symbol: str, fetcher, store):
    main_code = f"{symbol.upper()}_MAIN"
    df = fetcher.get_main_continuous_kline(symbol, dur_sec=3600, data_length=10000)
    if not df.empty:
        store.conn.execute('DELETE FROM kline_1h WHERE contract_code = ?', (main_code,))
        return store.store_klines_1h(main_code, df)
    return 0
```

**修复后**（对齐 `collect_1h.py` 增量模式）：
```python
def collect_1h_main_only(symbol: str, fetcher, store):
    """增量拉取主力连续 1H 数据。
    
    设计原则：INSERT OR REPLACE + MIN_1H_ROWS 保护 + 防御性 DELETE 仅清 dt > new_max。
    参考：collect_1h.py 的 collect_1h_for_symbol()（2026-07-15 Lesson #11 修复）。
    """
    main_code = f"{symbol.upper()}_MAIN"
    
    # 1. 查当前最新 dt，按需拉取（每日 ~10 根 1H bar，3 天只需 30 根）
    latest_dt = store.get_latest_kline_1h_dt(main_code)  # 需新增此方法
    if latest_dt:
        gap_days = (datetime.now() - latest_dt).days
        data_length = max(100, gap_days * 10 + 50)  # 留 50 根余量
    else:
        data_length = 10000  # 首次建仓
    
    df = fetcher.get_main_continuous_kline(symbol, dur_sec=3600, data_length=data_length)
    if df.empty:
        return 0
    
    # 2. INSERT OR REPLACE（增量安全）
    stored = store.store_klines_1h(main_code, df)
    
    # 3. MIN_1H_ROWS 保护（防 TqSdk 网络异常返回部分数据）
    MIN_1H_ROWS = 500
    if stored < MIN_1H_ROWS:
        logging.warning(f"{symbol}: 1H 数据仅 {stored} 行 < {MIN_1H_ROWS}，跳过写入")
        return 0
    
    # 4. 防御性 DELETE：仅清理异常未来 bar（dt > new_max）
    new_max = df['datetime'].max()
    store.conn.execute(
        'DELETE FROM kline_1h WHERE contract_code = ? AND dt > ?',
        (main_code, str(new_max))
    )
    
    return stored
```

**依赖**：需在 `data/data_store.py` 新增 `get_latest_kline_1h_dt(contract_code)` 方法。

---

### P0-B：`data_management.py` 移除 `pull_history_1h.py` 调用

**文件**：`scripts/data_management.py:137-155`

**当前代码**：
```python
def collect_1h(symbols: list[str] = None) -> list[dict]:
    syms = symbols or DEFAULT_SYMBOLS
    n = len(syms)
    results = []

    # 1. 增量采集（从各合约）
    t1 = _timeout_for("collect_1h.py", n)
    print(f"[INFO] Starting 1H collection for {n} symbols (timeout set to {t1}s)...")
    r = run_script("collect_1h.py", syms, timeout=t1)
    results.append(r)

    # 2. 拉取主力连续历史 1H（{_MAIN} 合约，用于回测和精度对比）
    t2 = _timeout_for("pull_history_1h.py", n)
    print(f"[INFO] Starting pull_history_1h for {n} symbols (timeout set to {t2}s)...")
    r2 = run_script("pull_history_1h.py", syms, timeout=t2)
    results.append(r2)

    return results
```

**修复后**：
```python
def collect_1h(symbols: list[str] = None) -> list[dict]:
    """采集 1H 数据（增量模式）。
    
    设计原则：仅调用 collect_1h.py（增量安全），不调用 pull_history_1h.py（全量 DELETE+INSERT）。
    pull_history_1h.py 仅用于首次建仓或灾难恢复，不应被日常流程调度。
    参考：2026-07-15 Lesson #11 "DELETE 全表 + INSERT 是定时炸弹"。
    """
    syms = symbols or DEFAULT_SYMBOLS
    n = len(syms)
    results = []

    # 增量采集（INSERT OR REPLACE，安全）
    t1 = _timeout_for("collect_1h.py", n)
    print(f"[INFO] Starting 1H collection for {n} symbols (timeout set to {t1}s)...")
    r = run_script("collect_1h.py", syms, timeout=t1)
    results.append(r)

    # ⚠️ 已移除 pull_history_1h.py 调用（全量 DELETE+INSERT，覆盖增量修复）
    # 如需全量重建历史，手动运行：python scripts/pull_history_1h.py

    return results
```

**同步更新**：`_timeout_for()` 函数中移除 `pull_history_1h.py` 的 timeout 预算（节省 29 分钟）。

---

### P1：`pull_history_1h.py` 加 MIN_ROWS 保护 + 文档标注

**文件**：`scripts/pull_history_1h.py:52-64`

**当前代码**：
```python
# 先删除旧的 _MAIN 数据
deleted = store.conn.execute(
    "DELETE FROM kline_1h WHERE contract_code = ?", (contract_code,)
).rowcount
store.conn.commit()

# 写入新数据
stored = store.store_klines_1h(contract_code, df)
```

**修复后**：
```python
"""
⚠️ DESIGN RISK: 本脚本做全量 DELETE + INSERT，仅用于首次建仓或灾难恢复。
不应被日常流程（data_management.py / daily_update.py）调度。
日常 1H 采集请用 collect_1h.py（增量模式，INSERT OR REPLACE）。

参考：2026-07-15 Lesson #11 "DELETE 全表 + INSERT 模式在数据采集场景都是定时炸弹"。
"""

# 先删除旧的 _MAIN 数据
deleted = store.conn.execute(
    "DELETE FROM kline_1h WHERE contract_code = ?", (contract_code,)
).rowcount
store.conn.commit()

# 写入新数据
stored = store.store_klines_1h(contract_code, df)

# MIN_ROWS 保护（防 TqSdk 网络异常返回部分数据）
MIN_ROWS = 500
if stored < MIN_ROWS:
    logging.error(
        f"{contract_code}: 全量重建仅写入 {stored} 行 < {MIN_ROWS}，"
        f"可能 TqSdk 网络异常，已摧毁 {deleted} 行历史数据！"
    )
    # 不回滚（已 commit），但记录严重错误
```

---

### 固化 1：代码注释（3 处 DESIGN RISK 警告）

| 文件 | 位置 | 注释内容 |
|---|---|---|
| `scripts/daily_update.py` | `collect_1h_main_only()` 函数头 | ⚠️ 已修复为增量模式，禁止退回全量 DELETE |
| `scripts/data_management.py` | `collect_1h()` 函数头 | ⚠️ 已移除 `pull_history_1h.py` 调用，禁止恢复 |
| `scripts/pull_history_1h.py` | 文件头 | ⚠️ 仅初始化/灾难恢复用，禁止被日常流程调度 |

---

### 固化 2：测试防护（3 个测试）

**测试 1**：`tests/test_data_update_incremental.py`
- 断言 `daily_update.py` 中 `collect_1h_main_only` 不包含裸 `DELETE FROM kline_1h WHERE contract_code = ?`（必须带 `AND dt > ?` 限定）
- 断言 `data_management.py` 的 `collect_1h()` 不调用 `pull_history_1h.py`
- 用 mock 验证 `store_klines_1h` 被调用时使用的是 INSERT OR REPLACE 模式

**测试 2**：`tests/test_no_full_wipe.py`
- AST 闸门：扫描所有 `scripts/*.py`，检测 `DELETE FROM kline` 模式
- 任何不含 `dt >` 或 `date >` 限定条件的 DELETE 语句必须带 `# ALLOWED: <原因>` 注释
- 否则 fail（与 `test_no_dead_code.py` 类似）

**测试 3**：`tests/test_data_management_no_full_wipe.py`
- 集成测试：mock TqSdk 返回 48 行（模拟网络异常）
- 验证历史数据不被清空（MIN_1H_ROWS 保护生效）

---

### 固化 3：CLAUDE.md 新增"数据采集设计原则"章节

**位置**：CLAUDE.md "数据管理策略" 章节（~L450）

```markdown
### 数据采集设计原则（不可退化）

1. **1H 数据必须增量更新**：`store_klines_1h()` 内部用 `INSERT OR REPLACE`，
   外层禁止 `DELETE FROM kline_1h WHERE contract_code = ?`（无 dt 限定）。
   参考：`collect_1h.py` 的 `collect_1h_for_symbol()`（2026-07-15 Lesson #11 修复）。

2. **全量拉取仅限初始化**：`pull_history_1h.py` 仅用于首次建仓或灾难恢复，
   不应被日常流程（`data_management.py` / `daily_update.py`）调度。
   如需全量重建，手动运行并确认 TqSdk 连接稳定。

3. **数据量保护阈值**：任何 1H 采集函数必须有 `MIN_1H_ROWS` 保护（默认 500），
   低于阈值跳过写入（防 TqSdk 网络异常返回部分数据）。

4. **单一采集路径**：同一数据关切（1H 采集）只能有一个实现。
   不得在 `collect_1h.py` / `daily_update.py` / `pull_history_1h.py` 各自实现。
   当前权威实现：`collect_1h.py`（增量模式）。

5. **测试防护**：`tests/test_no_full_wipe.py` AST 闸门检测裸 DELETE 模式，
   CI 门禁必须通过。任何退化必须显式标注 `# ALLOWED: <原因>`。
```

---

### 固化 4：`data/AGENTS.md` 新增"采集策略"小节

引用 CLAUDE.md 上述原则，补充数据管线-specific 细节（如 TqSdk 连接方式、MIN_ROWS 阈值选择依据）。

## 3. 实施顺序

| 步骤 | 任务 | 验证 | 预计耗时 |
|---|---|---|---|
| 1 | P0-A：`daily_update.py` 增量模式对齐 | pytest 通过 + 手动验证数据不丢失 | 30 min |
| 2 | P0-B：`data_management.py` 移除 `pull_history_1h.py` 调用 | pytest 通过 + 手动跑 `--1h` 验证耗时降到 5 min 内 | 15 min |
| 3 | P1：`pull_history_1h.py` 加 MIN_ROWS 保护 + 文档 | pytest 通过 + 手动跑验证保护生效 | 15 min |
| 4 | 固化 1：代码注释（3 处 DESIGN RISK） | 人工 review | 10 min |
| 5 | 固化 2：测试防护（3 个测试） | pytest 通过 | 45 min |
| 6 | 固化 3：CLAUDE.md 新增原则章节 | 人工 review | 10 min |
| 7 | 固化 4：`data/AGENTS.md` 新增采集策略小节 | 人工 review | 10 min |
| 8 | 集成测试：`data_management.py --1h --daily` | 耗时 < 10 min + 数据正确 | 30 min |
| 9 | git commit + PR | code-reviewer 审核 | 15 min |

**总计**：~3 小时

## 4. 验证标准（DoD）

- ✅ pytest 全通过（含 3 个新增测试）
- ✅ `data_management.py --1h --daily` 耗时 < 10 分钟（从 75 分钟预算降到 10 分钟）
- ✅ AST 闸门 `test_no_full_wipe.py` 通过（无裸 DELETE 模式）
- ✅ CLAUDE.md 和 data/AGENTS.md 已更新
- ✅ code-reviewer APPROVE

## 5. 风险与回滚

| 风险 | 应对 |
|---|---|
| P0-A 新增 `get_latest_kline_1h_dt()` 方法可能影响其他 caller | 仅在 `collect_1h_main_only()` 调用，无其他依赖 |
| P0-B 移除 `pull_history_1h.py` 后，首次建仓用户不知道怎么跑 | 在注释和 CLAUDE.md 明确说明手动运行方式 |
| 测试可能误报（合法的 DELETE 被标记） | AST 闸门允许 `# ALLOWED: <原因>` 注释豁免 |
| 修复引入回归 | git revert HEAD 即可，所有改动都是增量补丁 |

## 6. 待用户确认

- [ ] 同意范围（P0+P1+4 个固化项）
- [ ] 同意 MIN_1H_ROWS = 500 阈值
- [ ] 同意 `data_length` 按需拉取逻辑（`gap_days * 10 + 50`）
- [ ] 同意 AST 闸门检测裸 DELETE 模式

---

**审阅后回复「开始执行」即可进入实施阶段。**
