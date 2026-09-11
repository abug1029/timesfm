# 后续 4 方向优化设计 (2026-07-29)

> **文档状态（2026-09-11）**：**历史战役**。正文当考古。活 SCHEMES 以 `config/prediction_scheme.py` 为准。不要按本文改生产方案表。

> 状态: 历史战役（2026-09-11 标注；原文等待审阅）
> 来源: Phase 5+6 落地后的 4 个后续优化方向 (用户 2026-07-29 提案)
> 涉及品种: 全品种回测架构 / TA PTA / basis 历史数据
> 不涉及: Phase 4 (JD 日历) / Phase 7 (LH 基本面) / Phase 8/9 实现 (本轮仅归档与路线图)

---

## 0. 背景与根因重定义

Phase 5+6 协变量优化落地后,用户提出 4 个后续优化方向。经代码核对,**方向 1 的根因诊断与代码现状不符**,需先澄清:

- **用户原诊断**: "TimesFM 多进程 OOM,多 Worker 各自实例化 TimesFM"
- **代码现状**: `monthly_backtest.py` 是**单进程串行** — 模型在 `main()` 里加载一次,`hourly_model` 通过 `shared_model=daily_model.model` 复用,逐品种逐点 `for` 循环。无 `multiprocessing.Pool` / `Joblib` / 并发 `subprocess`。`covariate_scan.py` 的 `subprocess` 是**串行单品种隔离** (v3 避免状态污染),非并发 Worker。
- **重诊断**: 被 kill 的真实根因是单进程长跑 (396 评估点 × 27 品种) 的**显存碎片累积 + 偶发长尾评估点**,已有 `torch.cuda.empty_cache()` 每 10 点清一次但频率硬编码。

方向 1 据此重新定义为单进程长跑治理,而非 Daemon/RPC 重构。

---

## 1. 方向 1 — 单进程长跑显存碎片治理

### 1.1 目标

降低 `monthly_backtest.py` 被 kill 概率,并提供 OOM 排查与断点续跑能力。不改变现有非参数化路径的行为。

### 1.2 三件优化

**1.2.1 `--cache-interval N` 参数 (默认 10,保持现状)**

- `scripts/monthly_backtest.py:126` 的硬编码 `i % 10 == 0` 改为 CLI 参数 `--cache-interval`。
- 默认 10 与现状完全一致;资源紧张时可调小 (如 5)。
- 参数解析复用现有 `args` 列表风格 (与 `--cov-override` / `--combo` 一致),不引入 argparse。

**1.2.2 `--max-points N` 减量参数**

- `run_symbol_backtest` 的 `eval_indices` 在生成后做切片 `eval_indices = eval_indices[:max_points]` (None 时不切)。
- 用于 OOM 排查: 先短样本定位是哪个品种吃显存,而非全量跑完才被 kill。
- 不影响 `--summary` 路径 (该路径 early return)。

**1.2.3 `--resume <checkpoint>` 增量落盘**

采用 **JSONL (JSON Lines, `.jsonl`)** 格式,而非标准 JSON — 标准 JSON 不支持流式追加,覆写瞬间被 kill 会损坏整个 checkpoint 文件,断点续跑失效。JSONL 每行一条记录,`mode="a"` 追加是 O(1) 原子操作,抗崩溃能力极强,且无需全量加载历史到内存。

- 文件路径: `reports/monthly_backtest/checkpoint_<timestamp>.jsonl`。
- 每跑完**一个评估点**,追加一行:
  ```json
  {"symbol": "cf", "idx": 150, "mae": 2.31, "dir_acc": 0.5, ...}
  ```
  (字段精简到 resume 所需 + 该点核心指标,不写完整 pred/quant 张量;具体字段在 plan 阶段定。)
- 进程被 kill 后,下次带 `--resume <checkpoint.jsonl>` 启动:
  - 一次性读 checkpoint,按行 parse,构建 `completed = set((symbol, idx) for each line)` (内存 set,O(n) 一次,非反复查询文件)。
  - `run_symbol_backtest` 内部 `for i, idx in enumerate(eval_indices)` 时,`(symbol, idx) in completed` 则跳过。
- 无 `--resume` 时与现状完全一致 (不读 checkpoint,不写 checkpoint 之外的状态)。
- checkpoint 文件不影响 `history.json` (后者是月度归档的完整 summary,前者是中途每点断点)。
- checkpoint 删除: 完整回测成功后 (`main()` 末尾) 可选清理,本轮不强制 (避免误删)。

### 1.3 受影响文件

- `scripts/monthly_backtest.py` — 加 3 个 CLI 参数 + resume 读写逻辑
- 无新增模块

### 1.4 测试

- `python scripts/monthly_backtest.py cf --max-points 10` 跑通 → 证明切片逻辑正确,且只跑 10 个评估点。
- 人为 Ctrl+C 中断后查看 `checkpoint_*.json` 落盘 → 证明增量落盘有效。
- `python scripts/monthly_backtest.py cf --resume <checkpoint>` 续跑 → 证明跳过已完成点。
- 不写单测 (回测脚本依赖 TqSdk 数据,单测不可行;用 CLI 冒烟验证)。

---

## 2. 方向 2 — 历史流动性过滤器 (basis OI 过滤)

### 2.1 目标

防止 TqSdk 对过期合约返回的"伪有效"远端 K 线 (零成交、极低 OI、挂单价) 污染长程 basis 回测。

### 2.2 现状

`data/data_store.py:get_basis_1h`:
- 选合约时用 `AVG(open_interest)` 排序 (data_store.py:419)。
- JOIN 出的历史每个 bar 直接 `basis = (near_close - far_close) / far_close` (data_store.py:486),**不检查当 bar 的 OI**。

### 2.3 设计: 合约自身百分位法

**位置**: `get_basis_1h` 内部 (数据层职责,非 features 层)。

**步骤**:

1. 选出 `near_contract` / `far_contract` 后 (现有逻辑不变)。
2. 各查一次该合约全周期 `open_interest` 序列,用 `np.percentile(oi_series, 95)` 算 P95。
   - 实现用 Python 层 (不用 SQLite 百分位,SQLite 无原生 `PERCENTILE`);OI 序列 ≤ 8000 行,无性能问题。
3. JOIN 后 (现有 SQL 不变) 在 Python 层加一列:
   ```python
   valid = (df["near_oi"] >= near_p95 * 0.05) & (df["far_oi"] >= far_p95 * 0.05)
   ```
4. `df["basis"] = (df["near_close"] - df["far_close"]) / df["far_close"]`。
5. `df.loc[~valid, "basis"] = np.nan` (置 NaN 不删行,保留时间轴完整)。
6. `features.py:basis_momentum` 读到 NaN 后走现有零填充回退 (已确认该路径存在)。

**阈值**: `P95 × 5%` (合约自身百分位),不写死绝对值,适应品种间 OI 量级差异 (螺纹 vs 玻璃)。0.05 系数本轮固定,后续可暴露为参数。

### 2.4 受影响文件

- `data/data_store.py` — `get_basis_1h` 加 P95 计算 + OI 过滤
- `tests/test_basis_oi_filter.py` — 新增单测

### 2.5 测试

`tests/test_basis_oi_filter.py` 构造 mock DataStore:
- 近月合约: OI 全程 10000。
- 远月合约: 早期 OI=1 (挂单价),后期 OI=10000。
- 断言: 早期 bar 的 `basis` 为 NaN,后期 bar 的 `basis` 为正常值。
- 边界: P95 计算用全周期 OI (含早期低 OI),确保早期 1 手不被自己抬高 P95。

---

## 3. 方向 3 — Scan 裁决加显著性门槛

### 3.1 目标

防止读者被 scan 输出的 DirAcc 误导,并防止微弱 MAE 差异 (如 0.074pp) 在小样本下被当成"胜者"。

### 3.2 现状

`scripts/covariate_scan.py`:
- 裁决本就按 24h MAE 排序 (`results.sort(key=lambda x: x[1])`,line 183)。
- DirAcc 只是打印展示 (line 191-192 TOP5 表),**不参与裁决**。
- 真正问题: (a) DirAcc 印在汇总表里,读者误以为它是裁决依据;(b) 微弱差异被当成胜利 (TA basis vs bb_squeeze 差 0.074pp)。

### 3.3 设计: 两层

**3.3.1 展示层去误导**

- TOP5 / 汇总表里 DirAcc 列改名 `DirAcc(展示)`,表头加注脚 `"不参与裁决"`。
- 汇总报告 stdout 末尾加说明: `"裁决锚点: 24h MAE 相对下降率 vs 基线"`。

**3.3.2 裁决层加显著性门槛**

- 定义 `baseline_mae` = 当品种当前固化方案的 MAE:
  - 优先从 `config.prediction_scheme.get_scheme(symbol).covariate_type` 读对应协变量的 MAE;
  - 退化为 `ccl` 协变量的 MAE (若该品种无固化方案)。
- `best` 仍是 MAE 最低 (sort 逻辑不变),输出时增加判定:
  ```python
  rel_drop = (baseline_mae - best_mae) / baseline_mae
  if rel_drop >= 0.03:
      label = "显著改善"
  else:
      label = f"无显著改善(<{int(0.03*100)}%)"
  ```
- 阈值 3% 本轮固定;不改 `best` / `results.sort` 核心,只在输出/推荐配置处加标签。
- `推荐配置更新` 区块 (line 282-284) 在每行末尾追加 `# {label}`。

### 3.4 受影响文件

- `scripts/covariate_scan.py` — 展示改名 + 显著性门槛
- `tests/test_scan_significance.py` — 新增单测

### 3.5 测试

`tests/test_scan_significance.py` mock 一组 results:
- 断言 `rel_drop < 0.03` 时输出"无显著改善"标签。
- 断言 `rel_drop >= 0.03` 时输出"显著改善"标签。
- 断言 sort 逻辑 (按 MAE) 未变。

---

## 4. 方向 4 — TA 策略归档

### 4.1 目标

把 Phase 6 的 TA 实证结论回写到代码注释与 STATE 待办,把后续算力导向 Phase 8 (跨品种 crack spread)。不写新代码,纯文档层归档。

### 4.2 设计

**4.2.1 `config/prediction_scheme.py` 的 TA scheme 注释**

```python
# TA: bb_squeeze 固化 (Phase 6 已归档)
# 单品种 calendar spread 实证不如 bb_squeeze (MAE 2.518% vs 2.444%, +0.074pp 退化)
# 短期价格驱动 = 成本端跟涨跌 + 波动率爆发, 非现货供需错配
# 后续探索转 Phase 8 (跨品种原油/PX crack spread)
```

**4.2.2 `STATE.md` 待办调整**

- Phase 6 标记: "已完成 + 归档 (实证: 不固化 basis_momentum, 保 bb_squeeze)"。
- Phase 8 (跨品种原油/PX crack spread) 优先级上提,移到"下一阶段候选"顶部。
- Phase 9 (Rollover) 保留在路线图,标注"依赖 Phase 8 验证跨品种路径可行后再做"。

**4.2.3 不生成新报告**

`reports/research/20260729_phase5_6_summary.md` 已作为可追溯的实证决策文档,本轮不再新建归档报告,避免重复文档。

### 4.3 受影响文件

- `config/prediction_scheme.py` — TA scheme 注释
- `STATE.md` — Phase 6/8/9 路线图调整
- 无测试 (纯文档变更)

---

## 5. 范围与 Out of Scope

**In scope**:
- 方向 1: monthly_backtest.py 三件 CLI 参数化
- 方向 2: get_basis_1h OI 过滤 + 单测
- 方向 3: covariate_scan.py 展示层 + 显著性门槛 + 单测
- 方向 4: prediction_scheme.py 注释 + STATE.md 路线图

**Out of scope (本轮不做)**:
- Daemon/RPC 推理服务 (方向 1 重定义后已排除)
- Phase 4 (JD 日历特征) — 独立 spec
- Phase 7 (LH 基本面) — 独立 spec
- Phase 8 (跨品种 crack spread) — 本轮仅在方向 4 归档,实现独立 spec
- Phase 9 (Rollover) — 依赖 Phase 8
- backtest 脚本的多进程架构改造 (无并发,不涉及)

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 方向 2 OI 过滤误杀早期正常合约 | 用合约自身 P95×5%,非绝对值;P95 用全周期 OI 算,早期低 OI 不抬高 P95 |
| 方向 2 零填充回退掩盖过滤效果 | features.basis_momentum 现有 NaN→0 回退不变,过滤置 NaN 后行为与"无数据"一致,符合预期 |
| 方向 3 显著性门槛改变固化决策 | 不改裁决逻辑 (仍按 MAE),只在输出加标签;固化仍需人工审阅 scan 结果 |
| 方向 1 resume checkpoint 格式损坏 | JSONL 逐行追加 (`mode="a"`,O(1) 原子),覆写瞬间被 kill 不会损坏已写记录;不支持标准 JSON 流式追加 |
| 方向 1 --max-points 改变评估点数影响 MAE | MAE 是均值,样本减少可能方差变大;仅用于 OOM 排查,不用于固化决策 |

---

## 7. 验收标准

- 方向 1: `--max-points 10 cf` 跑通且只跑 10 点;`--resume` 续跑跳过已完成点;无参数时行为与现状一致;checkpoint 为 `.jsonl` 格式,Ctrl+C 后可见逐行追加、无文件损坏。
- 方向 2: `tests/test_basis_oi_filter.py` 通过;TA `get_basis_1h` 返回的早期低 OI bar 的 `basis` 为 NaN。
- 方向 3: `tests/test_scan_significance.py` 通过;scan 输出含"显著改善/无显著改善"标签;DirAcc 列改名。
- 方向 4: prediction_scheme.py 含归档注释;STATE.md 路线图更新。

---

## 8. 执行顺序建议

1. 方向 4 (文档归档,最简单,无依赖)
2. 方向 1 (CLI 参数化,独立,无依赖)
3. 方向 2 (数据层,需 TA 真实数据验证)
4. 方向 3 (需 baseline_mae 读取逻辑,依赖 prediction_scheme 不变 — 方向 4 已先做注释不改逻辑,无冲突)

四个方向两两独立,可并行实现;方向 4 必须先于方向 3 完成 (避免方向 3 review 时 TA 注释尚未落地造成混淆)。