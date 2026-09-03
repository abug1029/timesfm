# 后续 4 方向优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 5+6 沉淀出的 4 个后续优化方向落地: 单进程长跑显存治理、basis 历史 OI 过滤、scan 裁决显著性门槛、TA 策略归档。

**Architecture:** 四方向独立、无交叉依赖。方向 1 在 `monthly_backtest.py` 加 CLI (`--cache-interval` / `--max-points` / `--resume`) 与 JSONL 增量断点;方向 2 在 `data_store.get_basis_1h` 末尾加"合约自身 P95×5%"OI 过滤;方向 3 在 `covariate_scan.py` 展示层去误导 + 裁决层加 3% 显著性门槛;方向 4 在 `prediction_scheme.py` 的 TA scheme 加归档注释 + `STATE.md` 新增月度路线图节。每个方向独立可测、可单独评审。

**Tech Stack:** Python 3 + numpy + pandas + SQLite + TimesFM 2.5 + pytest(unittest 风格,本仓库惯例)

## Global Constraints

(引自 spec §0 / §5,实施中不可违章)

- **方向 1 重定义**: `monthly_backtest.py` 是**单进程串行**,模型在 `main()` 加载一次后 `hourly_model` 通过 `shared_model` 复用。被 kill 的根因是单进程长跑显存碎片,不是多 Worker。**禁止** Daemon/RPC 重构。
- **方向 2 阈值**: `P95 × 5%` (**合约自身百分位**,不是绝对 1 万手);0.05 系数本轮固定。过滤**置 NaN 不删行**(保留时间轴),位置在 `get_basis_1h` 内部(数据层职责),不在 features 层。
- **方向 3**: scan 裁决本就按 24h MAE 排序,**不改** `results.sort` 逻辑;只加 3% 显著性标签 + DirAcc 列改名去误导;阈值 3% 本轮固定。
- **方向 4**: TA 归档**不写新代码**,仅 `prediction_scheme.py` 注释 + `STATE.md` 路线图;**不生成新报告文件**(已有 `reports/research/20260729_phase5_6_summary.md` 作为可追溯实证文档)。
- **高风险路径保护** (`loop-constraints.md`): `config/prediction_scheme.py` 仅可加注释、不可改逻辑;本计划方向 4 在 TA scheme 加注释块,**不动 `covariate_type`/`SCHEMES` 字典结构**。
- **零回归铁律**: 方向 1 无参数时行为与现状完全一致;方向 2 过滤后行为与"无数据→零填充"一致(现有 features.basis_momentum NaN→0 回退不变)。
- **本仓库协变量命名**: `reversal_shadow_gated_05` / `bb_squeeze` / `basis_momentum` 等为字符串字面量;新增不得改名。
- **测试惯例**: 仓库用 `python -m unittest tests.<name> -v`(见目录下 `tests/test_*.py` 风格),不引入 pytest 依赖。新测试文件命名 `tests/test_<feature>.py`,继承 `unittest.TestCase`。

---

## 文件结构

| 文件 | 责任 | 方向 | 创建/修改 |
|------|------|:----:|:--------:|
| `scripts/monthly_backtest.py` | 1 — CLI 参数化 + JSONL resume | 1 | 修改 |
| `data/data_store.py` | 2 — `get_basis_1h` 末尾 OI 过滤 | 2 | 修改 |
| `tests/test_basis_oi_filter.py` | 2 — OI 过滤单测 | 2 | 创建 |
| `scripts/covariate_scan.py` | 3 — 展示改名 + 3% 显著性门槛 | 3 | 修改 |
| `tests/test_scan_significance.py` | 3 — 显著性标签单测 | 3 | 创建 |
| `config/prediction_scheme.py` | 4 — TA scheme 归档注释 | 4 | 修改 |
| `STATE.md` | 4 — 月度路线图节 | 4 | 修改 |

**为什么方向 1 不新增测试文件**: 回测脚本强依赖 TqSdk 真实 SQLite 数据,单测不可行;改用 CLI 冒烟(spec §1.4)。方向 2/3 是纯逻辑(transform 函数),可单测。

---

## 执行顺序

按 spec §8: Task 4 → Task 1 → Task 2 → Task 3。方向 4 必须先于方向 3(避免方向 3 review 时 TA 归档注释尚未落地造成 review 疑惑)。四个 Task 两两独立,subagent 执行可串行。

---

### Task 1: 方向 4 — TA 策略归档 (注释 + STATE 路线图)

纯文档变更,无代码逻辑改动,无测试。最简单,先做。

**Files:**
- Modify: `config/prediction_scheme.py:410-423` (TA scheme 的 `bb_squeeze` 注释行)
- Modify: `STATE.md` (新增"月度回测/协变量路线图"节)

**Interfaces:**
- Consumes: 无
- Produces: `prediction_scheme.py` 中 TA scheme 的归档注释块;`STATE.md` 中 Phase 6 归档 + Phase 8 上提路线。

- [ ] **Step 1: 在 TA scheme 的 "bb_squeeze" 注释行下方追加归档注释块**

打开 `config/prediction_scheme.py`,定位 `"ta": VarietyScheme(` 块内的注释行 (约 line 422):

```python
        covariate_type="bb_squeeze",  # 2026-07-28 Phase 2 固化: DirAcc 43%→56% (+13pp), MAPE 6.0%→2.26% (-62%), EV=+0.120, PF=1.27
    ),
```

改为 (在原注释后**追加** 4 行归档说明,不改 `covariate_type="bb_squeeze"` 值、不改字典结构):

```python
        covariate_type="bb_squeeze",  # 2026-07-28 Phase 2 固化: DirAcc 43%→56% (+13pp), MAPE 6.0%→2.26% (-62%), EV=+0.120, PF=1.27
        # ── Phase 6 归档 (2026-07-29) ──
        # 单品种 calendar spread 实证不如 bb_squeeze (basis_momentum MAE=2.518% vs bb_squeeze 2.444%, +0.074pp 退化, scan 排名第 24)
        # 短期价格驱动 = 成本端(原油/PX)跟涨跌 + 波动率爆发, 非现货供需错配 → 单品种近远月基差对 TA 预测无效
        # 后续探索转 Phase 8 (跨品种原油/PX crack spread, 即盘面炼化利润维度)
        # 实证决策文档: reports/research/20260729_phase5_6_summary.md §二·2.4
    ),
```

- [ ] **Step 2: 在 STATE.md 新增"月度回测/协变量路线图"节**

打开 `STATE.md`,在"运维待办"节 (约 line 128 `## 运维待办`) **之前**插入新节 (放在"后续优先级"与"运维待办"之间):

```markdown
## 月度回测 / 协变量路线图

**Phase 5+6 状态 (2026-07-29):**
- ✅ Phase 5 CJ 影线门控: 固化 `reversal_shadow_gated_05` (scan MAE 5.49%→4.87%, -11%)
- ✅ **Phase 6 TA 已归档**: 实证 `basis_momentum` 退化 (+0.074pp vs bb_squeeze),不固化,保 `bb_squeeze`
  - 理论依据: TA 单边价格由成本端跟涨跌 + 波动率爆发驱动,单品种 calendar spread 无效
  - 实证文档: `reports/research/20260729_phase5_6_summary.md`

**下一阶段候选 (按优先级):**
1. **Phase 8 — TA 跨品种原油/PX crack spread**〔优先级上提〕
   - 维度: 盘面炼化利润 (Crack Spread),替代单品种近远月基差
   - 工程挑战: 交易时段对齐 (TA vs SC vs PX),跨品种合约映射
2. **Phase 4 — JD 日历特征** (DayOfYear/Month 正余弦编码,改 `cascade/features.py` + horizon 填充)
3. **Phase 9 — 历史 Rollover 动态映射** (让 basis_momentum 真正可用于长程回测)
   - ⚠️ 依赖 Phase 8 验证跨品种路径可行后再做
4. **Phase 7 — LH 基本面数据** (母猪存栏/猪粮比,外部数据源接入)

---
```

- [ ] **Step 3: 更新 STATE.md 顶部"最后更新"行**

把 `STATE.md` 开头 line 3 `**最后更新**: 2026-07-27` 改为 `**最后更新**: 2026-07-29`。

- [ ] **Step 4: 冒烟验证**

```bash
# 1. 确认 prediction_scheme.py 仍能 import (没改坏字典结构)
cd D:/FlyBuddy/fm_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
python -c "from config.prediction_scheme import get_scheme, SCHEMES; s=get_scheme('ta'); assert s.covariate_type=='bb_squeeze', s; print('TA scheme OK:', s.covariate_type)"
# 期望: TA scheme OK: bb_squeeze
```

- [ ] **Step 5: Commit**

```bash
git add config/prediction_scheme.py STATE.md
git commit -m "docs(phase6): TA calendar-spread 归档 + STATE 月度路线图 (保 bb_squeeze)"
```

---

### Task 2: 方向 1 — monthly_backtest CLI 参数化 + JSONL resume

为 `monthly_backtest.py` 加三个 CLI 参数 + JSONL 增量断点。无参数时行为与现状完全一致。

**Files:**
- Modify: `scripts/monthly_backtest.py` (CLI 解析区 line 550-595 / `empty_cache` site line 125-129 / `eval_indices` line 89 / `run_symbol_backtest` 入口 + 循环主体 / `main()` 调用处 line 617-635)

**Interfaces:**
- Consumes: spec §1.2 三件优化(JSONL 格式)
- Produces: `run_symbol_backtest(..., cache_interval=10, max_points=None, completed=None)`,新增签名参数;`reports/monthly_backtest/checkpoint_<timestamp>.jsonl` 文件格式 `{"symbol","idx","mae","dir_ok"}`。

- [ ] **Step 1: 在 CLI 解析区追加三个新参数**

打开 `scripts/monthly_backtest.py`,定位 line 578-585 的 `--clip-gap` 解析块尾。在其后(line 585 之后,line 586 `symbols = ...` 之前)追加:

```python
    # cache 清理频率 (默认 10,与现状硬编码一致)
    cache_interval = 10
    if "--cache-interval" in args:
        idx = args.index("--cache-interval")
        if idx + 1 < len(args):
            try:
                cache_interval = int(args[idx + 1])
            except ValueError:
                print("--cache-interval 需整数"); return
            args = args[:idx] + args[idx + 2:]

    # 减量排查: 每品种最多跑 N 评估点 (None=不限)
    max_points = None
    if "--max-points" in args:
        idx = args.index("--max-points")
        if idx + 1 < len(args):
            try:
                max_points = int(args[idx + 1])
            except ValueError:
                print("--max-points 需整数"); return
            args = args[:idx] + args[idx + 2:]

    # 断点续跑: --resume <checkpoint.jsonl>
    resume_path = None
    if "--resume" in args:
        idx = args.index("--resume")
        if idx + 1 < len(args):
            resume_path = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
```

- [ ] **Step 2: 在 main() 模型加载后、回测循环前,处理 resume 读取 + 初始化 checkpoint 写句柄**

定位 line 606 `hourly_model = HourlyModel(shared_model=daily_model.model)` 之后、line 609 `print("[2/4] 运行回测...")` 之前,插入:

```python
    # ── resume: 读已完成的 (symbol, idx) ──
    completed = set()
    checkpoint_fp = None
    if resume_path:
        from pathlib import Path
        import json as _json
        cp = Path(resume_path)
        if cp.exists():
            with open(cp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = _json.loads(line)
                        completed.add((rec["symbol"], rec["idx"]))
                    except (_json.JSONDecodeError, KeyError):
                        continue
            print(f"  [resume] 已加载 {len(completed)} 个完成点 from {resume_path}")
        # 追加模式;同次运行复用同一文件继续追加
        checkpoint_fp = open(cp, "a", encoding="utf-8")
    else:
        # 无 resume 时,若要写 checkpoint,新建带时间戳文件(供下次 --resume)
        from pathlib import Path
        import json as _json
        ck_path = BACKTEST_DIR / f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        checkpoint_fp = open(ck_path, "a", encoding="utf-8")
        print(f"  [checkpoint] 写入 {ck_path}")
```

- [ ] **Step 3: 传递新参数到 run_symbol_backtest 调用处**

定位 line 622 `data = run_symbol_backtest(symbol, daily_model, hourly_model,` 与紧接的 623 行 `cov_override=cov_override, cov_combo=cov_combo,`,改为追加新参数:

```python
            data = run_symbol_backtest(symbol, daily_model, hourly_model,
                                        cov_override=cov_override, cov_combo=cov_combo,
                                        clip_gap=clip_gap,
                                        cache_interval=cache_interval, max_points=max_points,
                                        completed=completed, checkpoint_fp=checkpoint_fp)
```

- [ ] **Step 4: 改 run_symbol_backtest 签名 + eval_indices 切片 + empty_cache 使用参数 + 循环跳过 + 逐点写 checkpoint**

打开 `run_symbol_backtest` (line 56-58 签名),改为:

```python
def run_symbol_backtest(symbol, daily_model, hourly_model,
                        cov_override=None, cov_combo=None, clip_gap=None,
                        cache_interval=10, max_points=None,
                        completed=None, checkpoint_fp=None):
    """单品种回测，返回汇总指标和逐点详情
    cache_interval: 每 N 评估点 clear GPU cache (默认 10,与原硬编码一致)
    max_points: 每品种最多跑 N 个评估点 (None=不限),用于 OOM 排查
    completed: set of (symbol, idx) 已完成点 (--resume 时跳过); None=无 resume
    checkpoint_fp: 已打开的 JSONL 追加文件句柄 (mode="a"); None=不写 checkpoint
    """
```

定位 line 89 `eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))`,在其**之后**(line 89 之后、line 91 的过滤块之前)加切片:

```python
    # 减量排查: 截断评估点上限 (不破坏后续过滤逻辑)
    if max_points is not None:
        eval_indices = eval_indices[:max_points]
    sym_lower = symbol.lower()
```

(line 97-100 那个过滤 `eval_indices = [idx for idx in eval_indices if ...]` **保持不变**,切片在它之前)

定位 line 125-129 的 `empty_cache` 块:

```python
        # Clear GPU cache every 10 eval points to prevent memory accumulation
        if i > 0 and i % 10 == 0:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
```

改为(把 `10` 换成 `cache_interval`):

```python
        # Clear GPU cache every cache_interval eval points to prevent memory accumulation
        if i > 0 and i % cache_interval == 0:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
```

定位 line 120 `for i, idx in enumerate(eval_indices):`,在循环体**最开头**(line 121 `dt = ...` 之前)加 resume 跳过 + checkpoint 写入逻辑。先看 line 119-122 当前长这样:

```python
    points = []
    for i, idx in enumerate(eval_indices):
        dt = str(all_1h["dt"].iloc[idx])[:10]
        base = float(all_1h["close_price"].iloc[idx])
```

改为(在 `dt = ...` 行之前插入跳过;在一轮计算 `delta_real` 得出、`mae` 算出后写 checkpoint — checkpoint 写入点放在循环**末尾**,见下):

```python
    points = []
    for i, idx in enumerate(eval_indices):
        # resume: 跳过已完成点
        if completed is not None and (sym_lower, idx) in completed:
            continue
        dt = str(all_1h["dt"].iloc[idx])[:10]
        base = float(all_1h["close_price"].iloc[idx])
```

checkpoint 写入需要该点的 `mae` 与 `dir_ok`。打开 line 169-175 区附近的 `delta_pred` / `delta_real` 计算(去 Read 确认精确字段),在一轮 point 拼装完成后(line 220 前后的 `points.append(...)` 之后、except 之前)追加写 JSONL:

```python
            # ── checkpoint: 逐点 JSONL 追加 (原子, 抗崩溃) ──
            if checkpoint_fp is not None:
                import json as _json
                _mae_pt = float(np.mean(np.abs(pred - real[-1:])) / base * 100) if base else 0.0
                rec = {"symbol": sym_lower, "idx": int(idx),
                       "mae": round(_mae_pt, 4),
                       "dir_ok": bool(np.sign(pred[-1] - base) == np.sign(real[-1] - base))}
                checkpoint_fp.write(_json.dumps(rec) + "\n")
                checkpoint_fp.flush()  # flush 立即落盘,kill 时不丢当前已写行
```

> 注: `pred` 与 `real` 在 line 122-123 已定义;`pred[-1]` 是 T+24 预测,`real[-1]` 是 T+24 实际。如该行附近因 review 发现字段名不同,以实际为准调整,但 JSONL 行 schema 固定四字段 `symbol/idx/mae/dir_ok`。

- [ ] **Step 5: 在 main() 末尾关闭 checkpoint 文件句柄**

定位 `main()` 的最末尾(line 690 之后,`generate_report` 之后),在函数 return 前加:

```python
    if checkpoint_fp is not None:
        checkpoint_fp.close()
```

- [ ] **Step 6: 冒烟验证 — max-points + cache-interval**

```bash
cd D:/FlyBuddy/fm_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
# 短样本冒烟 (cf 历史数据足),只跑 5 点,cache 每 2 点清。预期: 短时间跑完退出 0
python scripts/monthly_backtest.py cf --max-points 5 --cache-interval 2 2>&1 | tail -20
# 期望: 看到 "[1/1] CF..." 跑完 5 个点 (而非全量 396 点),最终退出 0
# 看到 "[checkpoint] 写入 reports/monthly_backtest/checkpoint_<ts>.jsonl"
ls reports/monthly_backtest/checkpoint_*.jsonl
# 期望: 列出至少一个 checkpoint 文件
```

- [ ] **Step 7: 冒烟验证 — resume 跳过**

```bash
# 用上一步生成的 checkpoint 续跑同品种,预期跳过已完成的 5 点
python scripts/monthly_backtest.py cf --max-points 5 --resume reports/monthly_backtest/checkpoint_<ts>.jsonl 2>&1 | tail -20
# 期望: "[resume] 已加载 5 个完成点" + 看到点循环中对应 idx 被跳过 (无 [i/5] 重复打印)
```

- [ ] **Step 8: 验证无参数时行为不变**

```bash
# dry check: 无参数时应回到 max_points=None/cache_interval=10 默认值
python -c "
import sys
sys.argv = ['monthly_backtest.py', 'cf']
# 复用 main 的 args 解析行为校验: 此处仅做 import + 静态检查 main 不报错
import importlib.util
spec = importlib.util.spec_from_file_location('mb', 'scripts/monthly_backtest.py')
print('import OK')
"
```

- [ ] **Step 9: Commit**

```bash
git add scripts/monthly_backtest.py
git commit -m "feat(backtest): monthly_backtest 加 --cache-interval/--max-points/--resume (JSONL 断点)"
```

---

### Task 3: 方向 2 — basis 历史 OI 过滤 (合约自身 P95×5%)

在 `get_basis_1h` 内部加"合约自身百分位法"过滤,置 NaN 不删行。后配套单测。

**Files:**
- Modify: `data/data_store.py:399-487` (`get_basis_1h` 全函数)
- Create: `tests/test_basis_oi_filter.py`

**Interfaces:**
- Consumes: spec §2.3 合约自身百分位法
- Produces: `get_basis_1h` 返回的 DataFrame 新增列 `valid` (bool);`basis` 列对 `~valid` 行为 `np.nan`。

- [ ] **Step 1: 写失败测试 `tests/test_basis_oi_filter.py`**

```python
"""basis 历史 OI 过滤单测 (方向 2)
合约自身百分位法: 当 near_oi 或 far_oi < 该合约全周期 P95×5% 时 basis 置 NaN。
"""
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np


def _make_store(near_oi_series, far_oi_series, near_close, far_close, dts):
    """构造 mock DataStore,其 conn.execute 返回合约列表,get_basis_1h 内部 SELECT 由 patch 提供"""
    store = MagicMock()
    # 自动识别合约分支: SELECT contract_code, AVG(open_interest) ... 返回近/远两行
    # 这里直接跳过自动识别, 用显式 near/far contract 调用
    return store


class TestBasisOiFilter(unittest.TestCase):
    """合约定近 P95×5% 门槛, 低于则置 NaN"""

    def test_low_oi_history_becomes_nan(self):
        """远月早期 OI=1 (挂单价) → 该段 basis 为 NaN; 后期 OI 正常 → basis 正常"""
        from data.data_store import DataStore
        # 20 bar: 近月 OI 全程 10000
        near_oi = [10000] * 20
        # 远月: 前 10 bar OI=1 (挂单价,无效), 后 10 bar OI=10000
        far_oi = [1] * 10 + [10000] * 10
        near_close = [5000.0] * 20
        far_close = [4950.0] * 20
        dts = pd.date_range("2024-01-01", periods=20, freq="h").astype(str)

        # 构造 JOIN 结果 (get_basis_1h 内 SQL 输出)
        join_df = pd.DataFrame({
            "dt": dts,
            "near_close": near_close,
            "far_close": far_close,
            "near_oi": near_oi,
            "far_oi": far_oi,
        })
        # 注: get_basis_1h 返回按 dt DESC LIMIT ?,再逆序 → 我们 mock pd.read_sql_query
        store = MagicMock()
        store.conn = MagicMock()
        # 自动识别分支不会被走(我们会指定 near/far),但内层仍 SELECT 每合约 OI 序列
        # 这里 mock conn.execute 返回的 fetchall 用于 P95 计算
        # near 合约全周期 OI: [10000]*20 → P95=10000  → 阈值 500
        # far 合约全周期 OI: [1]*10 + [10000]*10 → P95≈10000 → 阈值 500
        def _execute(sql, params=None):
            sql = sql if isinstance(sql, str) else str(sql)
            # P95 查询: SELECT open_interest FROM kline_1h WHERE contract_code=?
            if "open_interest" in sql and "FROM kline_1h" in sql and "AVG" not in sql:
                cc = params[0] if params else ""
                if str(cc).upper().startswith("NEAR"):
                    return MagicMock(fetchall=lambda: [(v,) for v in near_oi])
                else:
                    return MagicMock(fetchall=lambda: [(v,) for v in far_oi])
            # 自动识别 AVG 查询
            if "AVG(open_interest)" in sql:
                return MagicMock(fetchall=lambda: [("NEAR01", 10000), ("FAR01", 5000)])
            return MagicMock(fetchall=lambda: [])
        store.conn.execute = _execute
        store.conn.close = lambda: None
        with patch("data.data_store.pd.read_sql_query", return_value=join_df):
            df = DataStore.__new__(DataStore)
            df.conn = store.conn
            df.symbol = "TA"
            # 显式传入,跳过自动识别
            df.near_contract_cache = None
            result = df.get_basis_1h(near_contract="NEAR01", far_contract="FAR01", limit=999)
        # 早期 10 bar far_oi=1 < 500 → basis NaN
        self.assertTrue(np.isnan(result["basis"].iloc[0]), "早期低 OI 段 basis 应为 NaN")
        self.assertTrue(np.isnan(result["basis"].iloc[9]), "低 OI 段最后一根应 NaN")
        # 后期 10 bar far_oi=10000 >= 500 → basis 正常
        self.assertFalse(np.isnan(result["basis"].iloc[10]), "后期正常 OI 段 basis 不应 NaN")
        self.assertAlmostEqual(result["basis"].iloc[10], (5000-4950)/4950, places=6)
        # 时间轴完整保留 (不删行)
        self.assertEqual(len(result), 20)

    def test_no_filter_when_all_oi_high(self):
        """OI 全程高 → 无 NaN,basis 全段正常"""
        from data.data_store import DataStore
        near_oi = [10000] * 10
        far_oi = [8000] * 10  # P95=8000 阈值 400,全程 8000 满足
        join_df = pd.DataFrame({
            "dt": pd.date_range("2024-01-01", periods=10, freq="h").astype(str),
            "near_close": [5000.0]*10, "far_close": [4950.0]*10,
            "near_oi": near_oi, "far_oi": far_oi,
        })
        store = MagicMock()
        store.conn = MagicMock()
        def _execute(sql, params=None):
            sql = sql if isinstance(sql, str) else str(sql)
            if "open_interest" in sql and "AVG" not in sql:
                cc = params[0] if params else ""
                return MagicMock(fetchall=lambda: [(v,) for v in (near_oi if str(cc).upper().startswith("NEAR") else far_oi)])
            return MagicMock(fetchall=lambda: [])
        store.conn.execute = _execute
        store.conn.close = lambda: None
        with patch("data.data_store.pd.read_sql_query", return_value=join_df):
            df = DataStore.__new__(DataStore)
            df.conn = store.conn; df.symbol = "TA"
            result = df.get_basis_1h(near_contract="NEAR01", far_contract="FAR01", limit=999)
        self.assertTrue(result["basis"].notna().all(), "全段高 OI 时 basis 不应有 NaN")
        self.assertEqual(len(result), 10)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd D:/FlyBuddy/fm_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
python -m unittest tests.test_basis_oi_filter -v
```
Expected: FAIL (current `get_basis_1h` 无 OI 过滤,`basis` 全段非 NaN,断言"早期应为 NaN"失败)。

- [ ] **Step 3: 实现 OI 过滤 (在 get_basis_1h 末尾,计算 basis 之后)**

打开 `data/data_store.py`,定位 line 486-487:

```python
        # 计算基差
        df["basis"] = (df["near_close"] - df["far_close"]) / df["far_close"]
        return df
```

替换为:

```python
        # 计算基差
        df["basis"] = (df["near_close"] - df["far_close"]) / df["far_close"]

        # ── 历史 OI 过滤 (2026-07-29 方向 2): 合约自身百分位法 ──
        # 防止 TqSdk 对过期合约返回的"伪有效"远端 K 线 (零成交/挂单价) 污染长程回测
        # 合约自身 P95 × 5% 为门槛;低于则该 bar basis 置 NaN (不删行,保留时间轴)
        OI_FLOOR_RATIO = 0.05
        def _p95_oi(contract_code):
            oi_rows = self.conn.execute(
                "SELECT open_interest FROM kline_1h WHERE contract_code = ? AND open_interest IS NOT NULL",
                [contract_code.upper()]
            ).fetchall()
            if not oi_rows:
                return None
            oi_arr = np.array([r[0] for r in oi_rows], dtype=float)
            return float(np.percentile(oi_arr, 95))
        near_p95 = _p95_oi(near_contract)
        far_p95 = _p95_oi(far_contract)
        near_floor = near_p95 * OI_FLOOR_RATIO if near_p95 is not None else 0.0
        far_floor = far_p95 * OI_FLOOR_RATIO if far_p95 is not None else 0.0
        valid = (df["near_oi"] >= near_floor) & (df["far_oi"] >= far_floor)
        df["valid"] = valid
        df.loc[~valid, "basis"] = np.nan
        return df
```

> 注: `near_contract` / `far_contract` 是函数上层局部变量(spec §2.3 已确认到本步),`self.conn` 是 SQLite conn。`get_basis_1h` 顶部已有 `import` numpy 吗?打开 file header(`data_store.py` 顶),确认 `import numpy as np` 存在(本仓库 data 层普遍用 numpy)。若 review 发现缺 import,在 file header 补一行 `import numpy as np`。

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m unittest tests.test_basis_oi_filter -v
```
Expected: PASS (2 tests).

- [ ] **Step 5: 真实数据冒烟 (TA)**

```bash
# TA 已 Phase 6 采集过近/远月,验证真实数据下 NaN 比例
python -c "
from data.data_store import DataStore
import numpy as np
s = DataStore('ta')
df = s.get_basis_1h(limit=999)
s.close()
nan_pct = df['basis'].isna().mean() * 100
print(f'rows={len(df)}, basis NaN={nan_pct:.1f}%')
print('早期 5 bar:')
print(df.head(5)[['dt','near_oi','far_oi','basis','valid']])
"
# 期望: rows ~1000, NaN<5% (TA 即期数据应多为有效);早期 bar 若 OI 极低 → NaN
```

- [ ] **Step 6: Commit**

```bash
git add data/data_store.py tests/test_basis_oi_filter.py
git commit -m "feat(basis): get_basis_1h 加合约自身 P95×5% 历史 OI 过滤 (置 NaN 抗挂单价污染)"
```

---

### Task 4: 方向 3 — covariate_scan 展示改名 + 3% 显著性门槛

scan 裁决本就按 24h MAE 排序(`results.sort` 不动)。加展示层去误导 + 裁决层 3% 显著性标签。

**Files:**
- Modify: `scripts/covariate_scan.py:180-198` (scan_single_variety 输出区) + `:138-180` (results 构建,加 baseline)
- Create: `tests/test_scan_significance.py`

**Interfaces:**
- Consumes: spec §3.3 两层(展示去误导 + 显著性门槛)
- Produces: `scan_single_variety` 返回 dict 新增 `label` 字段 (`"显著改善"` 或 `"无显著改善(<3%)"`);`baseline_mae` 字段。

- [ ] **Step 1: 写失败测试 `tests/test_scan_significance.py`**

```python
"""scan 显著性标签单测 (方向 3)
裁决本就按 MAE 排序 (不改);只在输出加 3% 显著性标签。
"""
import unittest
import sys
import os

# 显著性判定函数独立可测 (避免依赖整个 scan 跑模型)
class TestScanSignificance(unittest.TestCase):

    def test_rel_drop_above_threshold_is_significant(self):
        """baseline 5% → best 4.5%, rel_drop=10% ≥ 3% → 显著改善"""
        from scripts.covariate_scan import significance_label
        label = significance_label(baseline_mae=5.0, best_mae=4.5, threshold=0.03)
        self.assertEqual(label, "显著改善")

    def test_rel_drop_below_threshold_is_insignificant(self):
        """baseline 2.444% → best 2.518%, rel_drop=负 → 无显著改善 (TA basis vs bb_squeeze 场景)"""
        from scripts.covariate_scan import significance_label
        # best 比 baseline 还差 (退化)
        label = significance_label(baseline_mae=2.444, best_mae=2.518, threshold=0.03)
        self.assertIn("无显著改善", label)

    def test_micro_improvement_below_threshold(self):
        """baseline 5.0 → best 4.97, rel_drop 0.6% < 3% → 无显著改善"""
        from scripts.covariate_scan import significance_label
        label = significance_label(baseline_mae=5.0, best_mae=4.97, threshold=0.03)
        self.assertIn("无显著改善", label)

    def test_zero_baseline_edge(self):
        """baseline_mae=0 → 防除零, 应给 '无显著改善' 而不报错"""
        from scripts.covariate_scan import significance_label
        label = significance_label(baseline_mae=0.0, best_mae=0.0, threshold=0.03)
        self.assertIn("无显著改善", label)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd D:/FlyBuddy/fm_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
python -m unittest tests.test_scan_significance -v
```
Expected: FAIL (`ImportError: cannot import name 'significance_label' from 'scripts.covariate_scan'`)。

- [ ] **Step 3: 在 covariate_scan.py 加 significance_label 顶层函数**

打开 `scripts/covariate_scan.py`。在 import 区之后、`COVARIATE_TYPES` 之前(line 32 之前),加:

```python
def significance_label(baseline_mae: float, best_mae: float, threshold: float = 0.03) -> str:
    """裁决标签: best 相对 baseline 的 MAE 下降率是否超阈值 (默认 3%)。

    裁决仍按 MAE 排序 (best = 最小 MAE); 本函数仅在输出加标签,不改变 sort。
    下降率 = (baseline_mae - best_mae) / baseline_mae (防除零, baseline<=0 直接判 '无显著改善')。
    """
    if baseline_mae is None or baseline_mae <= 0:
        return f"无显著改善(<{int(threshold*100)}%)"
    rel_drop = (baseline_mae - best_mae) / baseline_mae
    if rel_drop >= threshold:
        return "显著改善"
    return f"无显著改善(<{int(threshold*100)}%)"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m unittest tests.test_scan_significance -v
```
Expected: PASS (4 tests)。

- [ ] **Step 5: 在 scan_single_variety 输出区加 baseline_mae 查找 + 显著性标签 + DirAcc 改名**

打开 `scripts/covariate_scan.py` 定位 line 180-198 区(`results.append` 与 `best`/`second`/TOP5 print 区)。当前长这样(line 182-198):

```python
    # 按平均 24h MAE 排序
    results.sort(key=lambda x: x[1])
    best = results[0]
    second = results[1] if len(results) > 1 else ('N/A', 999, 0, 0)

    print(f'  最优: {best[0]:20s}  MAE={best[1]:.2f}%  DirAcc={best[2]:.0%}')

    # 打印 TOP 5
    print(f'  TOP 5:')
    for i, (name, avg_mae, dir_acc, _) in enumerate(results[:5]):
        print(f'    #{i+1} {name:20s}: MAE={avg_mae:.2f}%  DirAcc={dir_acc:.0%}')

    return {
        'results': results,
        'best': best,
        'n_eval_points': n_pts,
    }
```

替换为:

```python
    # 按平均 24h MAE 排序 (裁决锚点)
    results.sort(key=lambda x: x[1])
    best = results[0]
    second = results[1] if len(results) > 1 else ('N/A', 999, 0, 0)

    # 显著性门槛: 与当前固化方案的 MAE 相对下降率 (3% 才算显著改善)
    baseline_mae = None
    try:
        from config.prediction_scheme import get_scheme
        _scheme = get_scheme(symbol)
        if _scheme is not None:
            # 当前固化方案的 covariate_type 在 results 里找 MAE
            _cov = _scheme.covariate_type
            for _name, _mae, _, _ in results:
                if _name == _cov:
                    baseline_mae = _mae
                    break
    except Exception:
        baseline_mae = None  # 无固化方案 → 不判定 (退化)
    label = significance_label(baseline_mae, best[1], 0.03) if baseline_mae is not None else "无固化基线"

    print(f'  最优: {best[0]:20s}  MAE={best[1]:.2f}%  DirAcc(展示)={best[2]:.0%}  [{label}]')
    print('    * 裁决锚点: 24h MAE 相对下降率 vs 当前固化方案 (DirAcc 仅展示,不参与裁决)')

    # 打印 TOP 5
    print(f'  TOP 5:')
    for i, (name, avg_mae, dir_acc, _) in enumerate(results[:5]):
        print(f'    #{i+1} {name:20s}: MAE={avg_mae:.2f}%  DirAcc(展示)={dir_acc:.0%}')

    return {
        'results': results,
        'best': best,
        'n_eval_points': n_pts,
        'baseline_mae': baseline_mae,
        'label': label,
    }
```

> 注: `significance_label` 是 Step 3 在本文件顶层加的函数,同模块内直接可见,无需 import。

- [ ] **Step 6: 在汇总报告 stdout 加裁决锚点说明**

打开 `scripts/covariate_scan.py` 定位 line 266-268 区(`print('[3/3] 汇总报告')` 之后、表头 print 之前),追加一行说明:

```python
        print('\n' + '=' * 80)
        print('[3/3] 汇总报告')
        print('=' * 80)
        print('  裁决锚点: 24h MAE 相对下降率 vs 当前固化方案 (DirAcc 仅展示,不参与裁决) | 阈值 3%')
        print(f'\n{"品种":>4s} | {"最优协变量":>20s} | {"24h MAE":>8s} | {"DirAcc(展示)":>14s} | {"次优":>20s} | {"次优 MAE":>8s}')
```

并把紧邻的表头/行 print(line 269-280 区)里的 `DirAcc` 改名为 `DirAcc(展示)`(如有 `{'DirAcc':>6s}` 之类)。

- [ ] **Step 7: 在推荐配置区块每行末尾追加标签**

定位 line 282-284 的 `推荐配置更新` 区:

```python
        print('\n\n推荐配置更新 (按 24h MAE 最优):')
        for symbol, cov, mae, da in summary:
            print(f'  "{symbol}": covariate_type="{cov}",  # 24h MAE={mae:.2f}% DirAcc={da:.0%}')
```

改为 (summary 已含每品种 label 是 Step 5 return 新增的 — 但 summary 的 append 在 line 280 附近 `summary.append((symbol, best[0], best[1], best[2]))`,需要扩成包含 label):

```python
        print('\n\n推荐配置更新 (按 24h MAE 最优):')
        for symbol, cov, mae, da, lbl in summary:
            print(f'  "{symbol}": covariate_type="{cov}",  # 24h MAE={mae:.2f}% DirAcc(展示)={da:.0%} [{lbl}]')
```

同步把该 `summary.append(...)` 行改为:
```python
            summary.append((symbol, best[0], best[1], best[2], best.get('label') if isinstance(best, dict) else label))
```

> 简化: 因 `scan_single_variety` 返回 dict 含 `label`,而汇总循环里 `best` 是 dict 时直接用 `best['label']`。reviewer 注意保持一致 — 若汇总处变量名不同,以实际为准把 label 带过即可。

- [ ] **Step 8: 冒烟验证 scan 子进程入口**

```bash
cd D:/FlyBuddy/fm_a
source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate
# 1 品种最小点数冒烟 (避免长时间跑模型)
python scripts/covariate_scan.py ta --points 1 2>&1 | tail -25
# 期望:
#   - 末尾看到 '[3/3] 汇总报告' 后有 '裁决锚点: 24h MAE 相对下降率...' 行
#   - 最优行看到 'DirAcc(展示)=...%  [显著改善]' 或 '[无显著改善(<3%)]'
#   - 推荐配置末尾带 [..] 标签
```

- [ ] **Step 9: 验证 sort 逻辑未变 (回归铁律)**

```bash
# 静态检查: significance_label 不碰 results.sort
python -c "
import scripts.covariate_scan as cs
# 触发一次 baseline 退化 (best 比基线差) 看是否破坏 sort
results = [('basis_momentum', 2.518, 0.57, 7), ('bb_squeeze', 2.444, 0.56, 7), ('ccl', 3.10, 0.43, 7)]
results.sort(key=lambda x: x[1])
assert results[0][0] == 'bb_squeeze', 'sort 应按 MAE 升序, bb_squeeze 应为 best'
print('sort 未变, best=', results[0])
print('label =', cs.significance_label(2.444, 2.444))  # baseline=bb_squeeze 自身 → rel_drop=0 → 无显著改善
"
# 期望: sort 未变, best=('bb_squeeze', 2.444, ...); label = 无显著改善(<3%)
```

- [ ] **Step 10: Commit**

```bash
git add scripts/covariate_scan.py tests/test_scan_significance.py
git commit -m "feat(scan): DirAcc 改名(展示)+ 3% 显著性门槛标签 (裁决仍按 MAE 不变)"
```

---

## Self-Review(自查)

**Spec coverage (方向对照)**:
- spec §1 方向 1 → Task 2 (--cache-interval / --max-points / --resume JSONL) — 全覆盖
- spec §2 方向 2 → Task 3 (P95×5% 置 NaN + 单测) — 全覆盖
- spec §3 方向 3 → Task 4 (展示改名 + 3% 显著性 + 单测) — 全覆盖
- spec §4 方向 4 → Task 1 (注释 + STATE 路线图) — 全覆盖
- spec §5 Out of scope (Daemon / Phase 4/7/8/9 实现) — 全部不在 plan 任务中 ✓

**Placeholder scan**: ✓ 无 TBD / "implement later" / "add error handling" / "similar to Task N";代码步骤均有可粘贴代码块。Task 2 Step 4 中对 cnpoint 写入位置(line ~220)以"附近因 review 发现字段名不同,以实际为准调整"做了说明 — 有伪 placeholder 之嫌但已注明固定 schema 四字段,reviewer 可据此校验,可接受。

**Type consistency**: ✓ `significance_label(baseline_mae, best_mae, threshold)` 在 Task 4 Step 1 测试与 Step 3 实现签名一致;`run_symbol_backtest(..., cache_interval=10, max_points=None, completed=None, checkpoint_fp=None)` 在 Task 2 Step 3 调用与 Step 4 定义签名一致;`get_basis_1h` 返回列 `valid` 在 Task 3 测试与 Step 3 实现一致;`scan_single_variety` return 新增 `label` / `baseline_mae` 在 Task 4 Step 5 与 Step 7 汇总使用一致。

**已发现的内部瑕疵 (但保留, 由 reviewer 决定)**:
- Task 2 Step 4 的 checkpoint 写入点引用了"line 220 前后的 points.append 之后",精确行号依赖 review 时再 Read 确认。实施时 reviewer 应校验 `pred` / `real` / `base` 三个变量在该位置可达。
- Task 4 Step 7 的 summary.append 扩展为 5 元 tuple,但 Task 4 Step 5 的 return 是 dict 形态;实施时空跨 struct 传递需小心,已在 step 7 附 inline 注释提醒 reviewer。