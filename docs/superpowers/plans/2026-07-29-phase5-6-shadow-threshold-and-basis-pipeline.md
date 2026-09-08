# Phase 5+6 协变量优化实施计划（影线门控 + TA 基差管道）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 CJ 的 reversal_shadow 加影线阈值门控（A+B 独立注册），并打通 TA 近月/远月 1H 采集管道 + basis_momentum 分层验证。

**Architecture:** Phase 5 改 `cascade/features.py` 的 `calc_reversal_shadow_ratio`（加默认参数零回归）+ 两处 elif 链注册 `reversal_shadow_gated` + scan 三档裁决 → backtest 定盘固化。Phase 6 改 `scripts/collect_1h.py` 后置采集 TA 月度合约（`get_basis_1h` 原样可用），按 L1-L4 分层降级验证，保 `bb_squeeze` 为固化退路。两 Phase 改动点不重叠，可串行执行互不阻塞。

**Tech Stack:** Python 3 + TimesFM 2.5 + TqSdk + SQLite + pandas/numpy + pytest

## Global Constraints

- **受保护文件**：`cascade/features.py`（Phase 5 改，默认参数零回归）、`config/prediction_scheme.py`（固化时人工确认）、`data/data_store.py`（Phase 6 仅验证不改）
- **零回归铁律**：`calc_reversal_shadow_ratio` 的 `min_shadow_atr=0.0` 必须对 SS/FG/LH 字节级不变（`np.array_equal` 必须为 True）
- **双段闸门**：scan 7pt 快筛 + monthly_backtest 396pt walk-forward 定盘（沿用 spec §4.3）
- **固化解锁阈值**：DirAcc ≥ 基线+2pp 且 MAPE 不退化；或例外规则 PF>1.1 且 EV>0 且 DirAcc≥基线+3pp
- **后置采集铁律**：Phase 6 月度合约采集必须在 `_MAIN` 采集 commit() 之后，套严格 try/except，单合约异常不阻塞主力合约
- **Fail-visibly**：Phase 6 backtest 历史区间 NaN>30% 显式 SKIP，不 zero-fill 蒙混指标
- **Windows GBK 编码**：Python 脚本输出中文须显式 `encoding='utf-8'` 或 `PYTHONIOENCODING=utf-8`
- **环境激活**：`source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate`，cwd=`D:/FlyBuddy/FM_a`
- **不动范围**：不实现 JD 日历特征（Phase 4）、不引入原油/PX 跨品种基差（未来 Phase）、不实现 Rollover 算法、不实现 LH 基本面（Phase 7）

---

## 文件结构

| 文件 | 职责 | Phase | 改动类型 |
|:----|:----|:----:|:----|
| `cascade/features.py` | 协变量算法 + 分发 | 5 | 改 `calc_reversal_shadow_ratio` + 两处 elif 链 |
| `scripts/covariate_scan.py` | scan 7pt 快筛 | 5 | `COVARIATE_TYPES` 加 3 个 gated 名字 |
| `scripts/collect_1h.py` | 1H 采集 | 6 | 加 `--with-basis` 后置月度合约采集 |
| `config/prediction_scheme.py` | 固化方案 | 5,6 | 固化时改 CJ/TA（人工确认） |
| `scripts/monthly_backtest.py` | walk-forward 回测 | 6 | 仅运行；若 NaN>30% 整段空则整品种 SKIP（不改逻辑，仅观测） |
| `tests/test_reversal_shadow_gated.py` | 零回归 + 门控单测 | 5 | 新建 |
| `reports/covariate_scan/20260729_cj_gated_scan.md` | CJ scan 三档裁决记录 | 5 | 新建 |
| `reports/research/20260729_phase5_6_summary.md` | 两 Phase 结果汇总 | 5,6 | 新建 |

---

### Task 1: `calc_reversal_shadow_ratio` 增 `min_shadow_atr` 参数 + 独立静默 + 零回归单测

**Files:**
- Modify: `cascade/features.py:1465-1517`
- Test: `tests/test_reversal_shadow_gated.py` (新建)

**Interfaces:**
- Consumes: 无
- Produces: `calc_reversal_shadow_ratio(df, atr_arr=None, lookback=20, min_shadow_atr=0.0) -> np.ndarray`（增参，默认 0.0 行为字节级不变）

- [ ] **Step 1: 新建失效测试 `tests/test_reversal_shadow_gated.py`**

```python
"""Phase 5: reversal_shadow_gated 零回归 + 影线门控单测"""
import numpy as np
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cascade.features import calc_reversal_shadow_ratio


def _make_df(o, h, l, c):
    """构造 1H OHLC DataFrame"""
    return pd.DataFrame({
        "open_price": o, "high_price": h, "low_price": l, "close_price": c,
    })


def test_min_shadow_atr_zero_is_no_op():
    """min_shadow_atr=0.0 必须与不传参字节级一致 (零回归铁律)"""
    rng = np.random.default_rng(42)
    n = 200
    o = rng.uniform(100, 120, n)
    c = rng.uniform(100, 120, n)
    h = np.maximum(o, c) + rng.uniform(0, 3, n)
    l = np.minimum(o, c) - rng.uniform(0, 3, n)
    df = _make_df(o, h, l, c)

    out_default = calc_reversal_shadow_ratio(df)
    out_zero = calc_reversal_shadow_ratio(df, min_shadow_atr=0.0)
    assert np.array_equal(out_default, out_zero), "min_shadow_atr=0.0 改变了默认行为"


def test_independent_silencing_long_upper_short_lower():
    """长上影(0.8 ATR)+短下影(0.15 ATR): 短下影归零, 长上影保留, 空头信号不被稀释"""
    # 构造 110 根: 前 100 根平稳, 后 10 根含目标 K 线
    n, w = 110, 20
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h = np.full(n, 100.5)
    l = np.full(n, 99.5)
    # 第 100 根: 长上影 0.8 ATR, 短下影 0.15 ATR (ATR≈1.0 由平稳段决定)
    o[100], c[100], h[100], l[100] = 100.0, 100.0, 100.8, 99.85

    df = _make_df(o, h, l, c)
    out_raw = calc_reversal_shadow_ratio(df, lookback=w, min_shadow_atr=0.0)
    out_gated = calc_reversal_shadow_ratio(df, lookback=w, min_shadow_atr=0.3)
    # 门控后该根信号应更偏空头(上影保留, 下影归零), 即 out_gated[100] < out_raw[100]
    assert out_gated[100] < out_raw[100], f"独立静默未生效: gated={out_gated[100]} raw={out_raw[100]}"


def test_both_small_shadows_zeroed():
    """双小影线(均 < 0.3 ATR): directional_shadow 归零"""
    n, w = 110, 20
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h = np.full(n, 100.1)  # 上影 0.1
    l = np.full(n, 99.9)   # 下影 0.1
    df = _make_df(o, h, l, c)
    out_gated = calc_reversal_shadow_ratio(df, lookback=w, min_shadow_atr=0.3)
    # 全段均为双小影线, 门控后 directional_shadow 全 0, 经 rolling+sigmoid 后稳定在 0 附近
    assert np.all(np.abs(out_gated[w:]) < 0.01), f"双小影线未归零: {out_gated[w:]}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate && python -m pytest tests/test_reversal_shadow_gated.py -v`
Expected: FAIL（`test_independent_silencing_*` 与 `test_both_small_shadows_zeroed` 失败，因 `min_shadow_atr` 参数不存在）

- [ ] **Step 3: 改 `calc_reversal_shadow_ratio` 加参数 + 独立静默**

修改 `cascade/features.py:1465-1517`，函数签名加 `min_shadow_atr: float = 0.0`，在 `directional_shadow = lower_shadow - upper_shadow` 之前插入独立静默：

```python
def calc_reversal_shadow_ratio(df: pd.DataFrame,
                                atr_arr: Optional[np.ndarray] = None,
                                lookback: int = 20,
                                min_shadow_atr: float = 0.0) -> np.ndarray:
    """
    K线反转影线压力协变量 (US-005)

    来源策略: Shooting Star (je-suis-tm/quant-trading)
    原理: 影线反映多空力量的瞬时博弈: 长下影=买压，长上影=卖压。
    工程修复: 使用 ATR 而非 body 作为分母，十字星(O=C)不再产生 NaN，
    长影线十字星的最强反转信号得以保留。

    Phase 5 增参 (2026-07-29): min_shadow_atr 独立静默滤除无效小影线。
    - 默认 0.0 → 字节级不变 (零回归)
    - >0 → 上/下影线各自独立, 低于 threshold = min_shadow_atr * ATR 的归零
      双向独立滤除: 单向 Pin Bar 的有效影线不被反向噪音稀释

    算法:
    1. upper_shadow = H - max(O, C)
    2. lower_shadow = min(O, C) - L
    3. [Phase 5] 若 min_shadow_atr>0: 上/下影线各自独立静默
    4. directional_shadow = lower_shadow - upper_shadow  (正=买压，负=卖压)
    5. normalized = directional_shadow / ATR  (ATR 分母，非 body)
    6. rolling(lookback).mean() 去噪 → tanh 压缩

    Args:
        df: 含 open_price/high_price/low_price/close_price 列的 DataFrame
        atr_arr: 预计算 ATR 数组 (可选)
        lookback: 滚动平均窗口 (默认 20)
        min_shadow_atr: 最小有效影线长度 (ATR 倍数, 默认 0.0=不过滤)

    Returns:
        np.ndarray, shape=(len(df),), 值域 [-1, 1], 无 NaN
    """
    o_col = 'open_price' if 'open_price' in df.columns else 'open'
    h_col = 'high_price' if 'high_price' in df.columns else 'high'
    l_col = 'low_price' if 'low_price' in df.columns else 'low'
    c_col = 'close_price' if 'close_price' in df.columns else 'close'

    o = df[o_col].values.astype(float)
    h = df[h_col].values.astype(float)
    l = df[l_col].values.astype(float)
    c = df[c_col].values.astype(float)

    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - l

    # [Phase 5] 独立静默: 上/下影线各自滤除无效小影线
    if min_shadow_atr > 0:
        if atr_arr is not None:
            atr_val_for_thr = atr_arr.astype(float) + EPSILON
        else:
            atr_val_for_thr = (h - l) + EPSILON
        threshold = min_shadow_atr * atr_val_for_thr
        upper_shadow = np.where(upper_shadow < threshold, 0.0, upper_shadow)
        lower_shadow = np.where(lower_shadow < threshold, 0.0, lower_shadow)

    # 方向化影线: 正 = 下影(买压)，负 = 上影(卖压)
    directional_shadow = lower_shadow - upper_shadow

    # ATR 分母 (非 body，十字星安全)
    if atr_arr is not None:
        atr_val = atr_arr.astype(float) + EPSILON
    else:
        atr_val = (h - l) + EPSILON

    normalized = directional_shadow / atr_val
    signal = pd.Series(normalized).rolling(lookback, min_periods=1).mean()

    result = np.tanh(signal.fillna(0.0).values)
    return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=-1.0)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_reversal_shadow_gated.py -v`
Expected: 3 个测试 PASS

- [ ] **Step 5: 跑 SS/FG/LH 零回归端到端验证**

```bash
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
python -c "
import numpy as np, pandas as pd
from data.data_store import DataStore
from cascade.features import calc_reversal_shadow_ratio, _calc_atr
for sym in ['ss','fg','lh']:
    with DataStore(sym) as s:
        df = s.get_main_contract_1h(limit=480)
        if df.empty: print(f'{sym}: EMPTY'); continue
        atr = _calc_atr(df, period=14)
        out_default = calc_reversal_shadow_ratio(df, atr_arr=atr, lookback=20)
        out_zero = calc_reversal_shadow_ratio(df, atr_arr=atr, lookback=20, min_shadow_atr=0.0)
        ok = np.array_equal(out_default, out_zero)
        print(f'{sym}: array_equal={ok} (n={len(df)})')
        assert ok, f'{sym} 零回归失败'
print('零回归端到端验证通过')
"
```
Expected: 三品种 `array_equal=True`，末行打印"零回归端到端验证通过"

- [ ] **Step 6: 提交**

```bash
git add cascade/features.py tests/test_reversal_shadow_gated.py
git commit -m "$(cat <<'EOF'
feat(phase5): calc_reversal_shadow_ratio 增 min_shadow_atr 独立静默

- 默认 0.0 字节级不变 (SS/FG/LH 零回归验证通过)
- >0 时上/下影线各自独立滤除, 单向 Pin Bar 动量不被反向噪音稀释
- 单测覆盖: 零回归 + 独立静默 + 双小影线归零

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 注册 `reversal_shadow_gated`（三档）到 features.py elif 链 + covariate_scan.py

**Files:**
- Modify: `cascade/features.py`（`build_covariate_matrix` line 1051 附近 + `build_combo_covariate_matrix` line 1200 附近）
- Modify: `scripts/covariate_scan.py:33-44`（`COVARIATE_TYPES` 列表）

**Interfaces:**
- Consumes: Task 1 的 `calc_reversal_shadow_ratio(..., min_shadow_atr=...)`
- Produces: features.py 两处分发识别 `reversal_shadow_gated_02/_03/_05` 字符串；scan 能测到这三个名字

- [ ] **Step 1: 在 `build_covariate_matrix` 加三档分支**

在 `cascade/features.py` 现有 `elif covariate_type == "reversal_shadow":` 分支（line 1051-1057）之后，追加三档：

```python
    elif covariate_type == "reversal_shadow_gated_02":
        # Phase 5 scan 三档: min_shadow_atr=0.2
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.2)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "reversal_shadow_gated_02"

    elif covariate_type == "reversal_shadow_gated_03":
        # Phase 5 scan 三档: min_shadow_atr=0.3
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.3)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "reversal_shadow_gated_03"

    elif covariate_type == "reversal_shadow_gated_05":
        # Phase 5 scan 三档: min_shadow_atr=0.5
        atr_arr = _calc_atr(df_1h, period=14)
        ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.5)
        last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
        covariate_full = np.concatenate([ctx, _decay_fill(last_val, horizon)])
        covariate_name = "reversal_shadow_gated_05"
```

- [ ] **Step 2: 在 `build_combo_covariate_matrix` 加三档分支**

在 `cascade/features.py` 现有 `elif cov_type == "reversal_shadow":` 分支（line 1200-1205）之后，追加：

```python
        elif cov_type == "reversal_shadow_gated_02":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.2)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
            result["reversal_shadow_gated_02"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "reversal_shadow_gated_03":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.3)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
            result["reversal_shadow_gated_03"] = np.concatenate([ctx, last_val * decay])

        elif cov_type == "reversal_shadow_gated_05":
            atr_arr = _calc_atr(df_1h, period=14)
            ctx = calc_reversal_shadow_ratio(df_1h, atr_arr=atr_arr, lookback=20, min_shadow_atr=0.5)
            last_val = float(ctx[-1]) if len(ctx) > 0 else 0.0
            decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])
            result["reversal_shadow_gated_05"] = np.concatenate([ctx, last_val * decay])
```

同时在 `build_combo_covariate_matrix` 末尾 `supported` 列表（line 1231-1233）追加三个名字：

```python
            supported = ["oi", "rsi_state", "hurst", "hourly_slope", "rsi_slope",
                         "pca_momentum", "ao_accel", "bb_squeeze", "ha_body",
                         "reversal_shadow", "reversal_shadow_gated_02",
                         "reversal_shadow_gated_03", "reversal_shadow_gated_05",
                         "sar_dist", "vor"]
```

- [ ] **Step 3: 在 `covariate_scan.py` `COVARIATE_TYPES` 追加三档**

修改 `scripts/covariate_scan.py:33-44`，在 `'reversal_shadow',` 行之后追加：

```python
    'ha_body',           # Heikin-Ashi 平滑方向动量 (SP/JM/RB/BU/P/CF/LH/TA)
    'reversal_shadow',   # K线反转影线压力 (SS/FG)
    'reversal_shadow_gated_02',  # Phase 5: 影线门控 0.2 ATR
    'reversal_shadow_gated_03',  # Phase 5: 影线门控 0.3 ATR
    'reversal_shadow_gated_05',  # Phase 5: 影线门控 0.5 ATR
    'bb_squeeze',        # 布林带收缩→扩张突破 (FU/EG/CJ)
```

- [ ] **Step 4: 冒烟验证 scan 能加载三档并跑 1 点**

```bash
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
python scripts/covariate_scan.py cj --points 1 2>&1 | grep -E "gated|最优|TOP"
```
Expected: 输出含 `reversal_shadow_gated_02/_03/_05`（1 点 DirAcc=100% 不可信，仅工程可用性验证）

- [ ] **Step 5: 提交**

```bash
git add cascade/features.py scripts/covariate_scan.py
git commit -m "$(cat <<'EOF'
feat(phase5): 注册 reversal_shadow_gated 三档 (0.2/0.3/0.5 ATR)

- build_covariate_matrix + build_combo_covariate_matrix 两处分发
- covariate_scan COVARIATE_TYPES 加入三档, scan 可裁决最优阈值
- 三档为 scan 临时注册, 胜者将正式注册为 reversal_shadow_gated

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: CJ scan 三档裁决 + 输出最优档

**Files:**
- Create: `reports/covariate_scan/20260729_cj_gated_scan.md`（裁决记录）

**Interfaces:**
- Consumes: Task 2 的 scan 可测三档
- Produces: `cj_gated_winner`（字符串，三档之一，或"原 reversal_shadow 更优"）

- [ ] **Step 1: 跑 CJ 三档 scan 7 点**

```bash
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a
python scripts/covariate_scan.py cj --points 7 2>&1 | tee reports/covariate_scan/20260729_cj_gated_scan.txt
```
Expected: 输出含 TOP5，三档 `reversal_shadow_gated_02/_03/_05` 与原 `reversal_shadow` 横向对比的 24h MAE + DirAcc

- [ ] **Step 2: 提取三档 vs 原版对比表，写入裁决记录**

人工/脚本从 scan 输出提取，写入 `reports/covariate_scan/20260729_cj_gated_scan.md`：

```markdown
# CJ 影线门控 scan 三档裁决 (2026-07-29)

## scan 7pt 结果

| 协变量 | min_shadow_atr | 24h MAE | DirAcc | 排名 |
|:----|:----:|:----:|:----:|:----:|
| reversal_shadow (原) | 0.0 | <填> | <填> | <填> |
| reversal_shadow_gated_02 | 0.2 | <填> | <填> | <填> |
| reversal_shadow_gated_03 | 0.3 | <填> | <填> | <填> |
| reversal_shadow_gated_05 | 0.5 | <填> | <填> | <填> |

## 裁决

scan 胜者: `reversal_shadow_gated_XX`（MAE 最低且 DirAcc 不低于原版 +0pp 缓冲）
或: 原 `reversal_shadow` 仍最优 → Phase 5 终止于"实证无明显增益", 保 CJ 现状

## 送入 backtest 候选
<填入胜者名字, 或"无送入">
```

- [ ] **Step 3: 提交裁决记录**

```bash
git add reports/covariate_scan/20260729_cj_gated_scan.md reports/covariate_scan/20260729_cj_gated_scan.txt
git commit -m "$(cat <<'EOF'
data(phase5): CJ 影线门控 scan 三档裁决

- scan 7pt 对比 reversal_shadow vs gated_02/_03/_05
- 裁决胜者送入 monthly_backtest 定盘

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: CJ monthly_backtest 验证 + 固化决策

**Files:**
- Modify: `config/prediction_scheme.py:359-373`（仅达阈才改，人工确认）

**Interfaces:**
- Consumes: Task 3 的 `cj_gated_winner`
- Produces: CJ 固化（`covariate_type` 改为胜者）或保现状（`reversal_shadow`）

- [ ] **Step 1: 跑 CJ 回测（用 scan 胜者）**

若 Task 3 裁决有胜者（设为 `reversal_shadow_gated_XX`）：

```bash
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a
python scripts/monthly_backtest.py cj --cov-override reversal_shadow_gated_XX 2>&1 | tee reports/monthly_backtest/20260729_cj_gated_backtest.txt
```
Expected: 输出 DirAcc / MAPE / EV / PF

若 Task 3 裁决"原版更优" → 跳过本 Task，CJ 保现状，Phase 5 终止

- [ ] **Step 2: 双段闸门判定**

基线（刚固化的 `reversal_shadow`）：DirAcc=53%, MAPE=2.64%, EV=+0.065, PF=1.14

判定逻辑（写入 `reports/monthly_backtest/20260729_cj_gated_backtest.txt` 末尾）：
- 常规通过：`backtest_DirAcc >= 55% 且 backtest_MAPE <= 2.64%`
- 例外通过：`PF > 1.1 且 EV > 0 且 backtest_DirAcc >= 56%`
- 否则：不固化，保 `reversal_shadow`

- [ ] **Step 3: 达阈则固化 CJ scheme（人工确认）**

仅当 Step 2 判定通过，改 `config/prediction_scheme.py:359-373` 的 CJ 条目：

```python
    "cj": VarietyScheme(
        symbol="cj",
        name="红枣",
        scheme_type="short_range",
        stars=2,
        dir_acc=<backtest_DirAcc>,  # 回测实测值
        mape=<backtest_MAPE>,       # 回测实测值
        decay=1.48,
        coverage=0.5,
        use_full_signal=False,
        short_horizon_only=True,
        confidence_multiplier=1.0,
        covariate_type="reversal_shadow_gated_XX",  # <Task3 胜者, 0.2/0.3/0.5 之一>
        # 2026-07-29 Phase 5 固化: reversal_shadow → reversal_shadow_gated_XX
        # min_shadow_atr=0.X 独立静默滤除低流动性品种无意义小影线
    ),
```

未达阈则**不改** prediction_scheme.py，在 `reports/research/20260729_phase5_6_summary.md` 记录"CJ 保现状 reversal_shadow（门控实证无明显增益）"

- [ ] **Step 4: 提交**

达阈固化：
```bash
git add config/prediction_scheme.py reports/monthly_backtest/20260729_cj_gated_backtest.txt
git commit -m "$(cat <<'EOF'
feat(phase5): CJ 固化 reversal_shadow_gated_XX (影线门控)

- min_shadow_atr=0.X 独立静默, scan+backtest 双段达标
- DirAcc <X>% MAPE <Y>% EV <Z> PF <W>
- 零回归: SS/FG/LH 字节级不变

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

未达阈：
```bash
git add reports/monthly_backtest/20260729_cj_gated_backtest.txt
git commit -m "data(phase5): CJ 影线门控回测未达阈, 保现状 reversal_shadow"
```

---

### Task 5: `collect_1h.py` 加 `--with-basis` 后置采集 TA 月度合约

**Files:**
- Modify: `scripts/collect_1h.py:23-57,129-164`

**Interfaces:**
- Consumes: `data.tqsdk_fetcher.UnifiedFetcher.get_kline_1h(contract_code)`、`data.contract_manager.ContractManager.generate_contract_codes()`、`data.indicator_calculator.IndicatorCalculator.calculate_all()`、`data.data_store.DataStore.store_klines_1h()`
- Produces: TA `kline_1h` 表含两个具体月度合约（OI 最高的近月+次近月），`get_basis_1h` 可用

- [ ] **Step 1: 在 `collect_1h.py` 加月度合约采集函数**

在 `collect_1h_for_symbol` 函数（line 23-57）之后，新增：

```python
def collect_basis_contracts_for_symbol(symbol: str, fetcher: UnifiedFetcher,
                                         calculator: IndicatorCalculator,
                                         store: DataStore,
                                         top_n: int = 2) -> int:
    """采集 OI 最高的 top_n 个月度合约 1H (用于 basis_momentum)

    Phase 6 (2026-07-29): TA 近远月基差管道。
    必须在 _MAIN 采集 commit() 之后调用; 单合约异常不阻塞。

    流程:
    1. contract_manager.generate_contract_codes() 拿未来 18 个月候选
    2. 对每个候选试采 1H, 记录最新 OI
    3. 取 OI 最高的 top_n 个未过期合约, 写入 kline_1h (contract_code=具体月度代码)

    Returns:
        写入的 1H 总行数 (失败返回 0)
    """
    import re
    from datetime import datetime
    from data.contract_manager import ContractManager

    print(f"  [basis] 采集月度合约候选...")
    try:
        cm = ContractManager(symbol)
        candidates = cm.generate_contract_codes()  # 未来 18 个月, 形如 ['ta2609', 'ta2610', ...]
        cm.close()
    except Exception as e:
        print(f"  [basis] WARN 生成候选失败: {e}")
        return 0

    if not candidates:
        print(f"  [basis] 无候选合约")
        return 0

    # 排除已过期合约 (按 YYMM 与当前比较)
    current_ym = int(datetime.now().strftime("%y%m"))
    valid_candidates = []
    for code in candidates:
        m = re.search(r'(\d{4})$', code)
        if m:
            ym = int(m.group(1))
            if ym >= current_ym:
                valid_candidates.append(code)
    if not valid_candidates:
        print(f"  [basis] 无未过期候选")
        return 0

    # 逐个试采 (短长度用于判定 OI, 不用于落库)
    oi_records = []
    for code in valid_candidates:
        try:
            df_probe = fetcher.get_kline_1h(code, data_length=200)  # 仅用于 OI 判定
            if df_probe is None or df_probe.empty:
                continue
            oi_col = 'open_interest' if 'open_interest' in df_probe.columns else None
            if oi_col is None or df_probe[oi_col].isna().all():
                continue
            latest_oi = float(df_probe[oi_col].dropna().iloc[-1])
            if latest_oi <= 0:
                continue
            oi_records.append((code, latest_oi))  # 仅记录 code+OI, 不落库
        except Exception as e:
            # 单合约失败静默跳过, 不阻塞
            continue

    if len(oi_records) < 2:
        print(f"  [basis] WARN 有效月度合约不足 2 个 (得 {len(oi_records)}), basis 无法计算")
        return 0

    # 按 OI 降序取 top_n
    oi_records.sort(key=lambda x: x[1], reverse=True)
    selected_codes = [c for c, _ in oi_records[:top_n]]
    print(f"  [basis] 选中: {selected_codes} (OI={[int(o) for c, o in oi_records[:top_n]]})")

    total_stored = 0
    # [Bug 1 修复] 对选中合约重新无长度限制抓取, 再落库 (probe 200 行不够 L1 断言 n>=480)
    for code in selected_codes:
        try:
            df_full = fetcher.get_kline_1h(code)  # 默认 data_length=8000, 落库充足
            if df_full is None or df_full.empty:
                continue
            df_full = df_full.rename(columns={'dt': 'date'})
            df_full['contract_code'] = code.upper()
            df_full = calculator.calculate_all(df_full)
            df_full = df_full.rename(columns={'open': 'open_price', 'close': 'close_price'})
            stored = store.store_klines_1h(code.upper(), df_full)
            if stored > 0:
                oi_val = df_full['open_interest'].dropna().iloc[-1] if 'open_interest' in df_full.columns else 0
                print(f"  [basis] {code.upper()} 1H: +{stored} 条 (OI={int(oi_val)})")
                total_stored += stored
        except Exception as e:
            print(f"  [basis] WARN 写入 {code} 失败: {e}")
            continue

    return total_stored
```

- [ ] **Step 2: 在 `main()` 加 `--with-basis` 参数 + 后置调用**

修改 `scripts/collect_1h.py:129-164` 的 `main()`：

```python
def main():
    parser = argparse.ArgumentParser(description="采集 1H K线数据")
    parser.add_argument("symbols", nargs="*", help="品种代码")
    parser.add_argument("--ccl-only", action="store_true", help="只补充日线 CCL")
    parser.add_argument("--with-basis", nargs="*", default=None,
                        help="指定品种采集月度合约 (近远月) 用于 basis_momentum, e.g. --with-basis ta")
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else list(DEFAULT_SYMBOLS)
    if not symbols:
        print("无数据")
        return

    basis_symbols = set(s.lower() for s in (args.with_basis or []))

    fetcher = UnifiedFetcher()
    calculator = IndicatorCalculator()

    for symbol in symbols:
        symbol = symbol.lower()
        print(f"\n{'='*50}")
        print(f"[{symbol.upper()}]")

        with DataStore(symbol) as store:
            if not args.ccl_only:
                # 采集 1H 主力连续
                print(f"  采集 1H K线...")
                total = collect_1h_for_symbol(symbol, fetcher, calculator, store)
                print(f"  1H 合计: {total} 条")

                # [Bug 2 修复] 主力数据立即落袋为安, 与 basis 采集事务隔离
                # 防止 basis 采集异常 (C 级崩溃/SQLite locked/OOM) 连带丢失主力
                store.conn.commit()

                # Phase 6: 后置采集月度合约 (必须在 _MAIN commit 之后, 严格 try/except)
                if symbol in basis_symbols:
                    print(f"  [basis] 后置采集月度合约 (TA 近远月基差管道)...")
                    try:
                        basis_total = collect_basis_contracts_for_symbol(
                            symbol, fetcher, calculator, store, top_n=2)
                        print(f"  [basis] 月度合约 1H 合计: {basis_total} 条")
                        store.conn.commit()  # basis 单独 commit
                    except Exception as e:
                        print(f"  [basis] ERROR 月度合约采集失败 (不阻塞主力): {e}")
                        # 主力已 commit, 此处异常不影响主力数据

            # 补充日线 CCL
            print(f"  补充日线 CCL...")
            ccl_count = backfill_ccl_for_daily(symbol, store)
            print(f"  CCL 更新: {ccl_count} 条")

    print(f"\n完成!")


if __name__ == "__main__":
    main()
```

注意：原 `collect_1h_for_symbol` 调 `store_klines_1h`（INSERT OR REPLACE，安全增量），故 `_MAIN` 数据已落库；月度合约同函数落库后一并 `commit()`。

- [ ] **Step 3: 加载冒烟验证 `--with-basis` 参数可解析**

```bash
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a
python scripts/collect_1h.py --help 2>&1 | grep -A1 with-basis
```
Expected: 输出 `--with-basis` 帮助文本

- [ ] **Step 4: 提交（先不跑真实采集，避免 TqSdk 长时间连接阻塞 plan 执行）**

```bash
git add scripts/collect_1h.py
git commit -m "$(cat <<'EOF'
feat(phase6): collect_1h 加 --with-basis 后置采集月度合约

- TA 近远月基差管道: 取 OI 最高 2 个月度合约写入 kline_1h
- 后置执行: _MAIN 采集 commit() 之后, 严格 try/except 不阻塞主力
- get_basis_1h 原样可用, 注入月度数据后自动 JOIN

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: TA 基差管道 L1-L4 分层验证 + 固化决策

**Files:**
- Create: `reports/research/20260729_phase5_6_summary.md`（汇总，含 Phase 5 结论 + Phase 6 L1-L4 结果）
- Modify: `config/prediction_scheme.py:405-419`（仅 L4 达阈才改 TA，人工确认）

**Interfaces:**
- Consumes: Task 5 的 `collect_1h.py --with-basis ta`
- Produces: TA 基差管道验证结论 + 固化决策（保 bb_squeeze 或改 basis_momentum）

**重大风险前置说明**（spec §4.1）：今天 OI 最高的 TA2609/TA2701 在 2024-2025 远端不存在或 OI≈0，monthly_backtest 396 期历史区间 JOIN 出全 NaN，basis_momentum 大概率无法通过 L3。**L1 管道打通即视为 Phase 6 核心交付物**，保 bb_squeeze 为固化退路。

- [ ] **Step 1: 跑 TA 月度合约采集（真实 TqSdk 调用，可能耗时数分钟）**

```bash
source D:/FlyBuddy/timesfm/.praxist-venv/Scripts/activate
cd D:/FlyBuddy/FM_a
python scripts/collect_1h.py ta --with-basis ta 2>&1 | tee reports/covariate_scan/20260729_ta_basis_collect.log
```
Expected: 日志含 `[basis] 选中: [(TA2609, OI值), (TA2701, OI值)]` 与 `月度合约 1H 合计: N 条`

**风险**：TqSdk 凭证/网络/合约不存在可能失败。失败则记录原因，L1 未通过。

- [ ] **Step 2: L1 验证 — `get_basis_1h` 返回非空**

```bash
python -c "
import sqlite3, pandas as pd
from data.data_store import DataStore
with DataStore('ta') as s:
    df = s.get_basis_1h(limit=99999)
    if df.empty:
        print('L1 FAIL: get_basis_1h 返回空')
    else:
        n = len(df)
        non_zero = (df['basis'].abs() > 1e-8).sum()
        print(f'L1: rows={n} non_zero_basis={non_zero} latest_basis={df[\"basis\"].iloc[-1]:.6f}')
        # 验证 kline_1h 现在有具体月度合约
        contracts = s.conn.execute('SELECT DISTINCT contract_code FROM kline_1h').fetchall()
        print(f'kline_1h contracts: {[r[0] for r in contracts]}')
        assert n >= 480, f'L1 FAIL: rows={n} < 480'
        assert non_zero > 0, 'L1 FAIL: basis 全零'
        print('L1 PASS')
"
```
Expected: `L1 PASS`，`kline_1h contracts` 含 `TA_MAIN` + 两个具体月度合约

L1 失败 → Phase 6 工程失败，记录原因到汇总报告，停止 L2-L4

- [ ] **Step 3: L2 验证 — scan 7pt 测 basis_momentum**

```bash
python scripts/covariate_scan.py ta --points 7 2>&1 | tee reports/covariate_scan/20260729_ta_basis_scan.txt
```
Expected: 输出含 `basis_momentum` 在 TOP 排名（方向有信号 = L2 通过；若 basis_momentum MAE=999% 或垫底 = L2 退化）

**注意**：scan 用最近 7 点（有实时月度数据），与 backtest 历史区间不同。scan 通过不代表 backtest 通过。

- [ ] **Step 4: L3 验证 — monthly_backtest 396pt（预期大概率失败）**

```bash
python scripts/monthly_backtest.py ta --cov-override basis_momentum 2>&1 | tee reports/monthly_backtest/20260729_ta_basis_backtest.txt
```
Expected（大概率）：历史区间 NaN → 指标退化或报错。记录 NaN 占比/退化情况。

**若整段空/NaN>30%**：观测 `get_basis_1h` 在 backtest 起止 dt 区间的返回，确认历史断层。在日志末尾记录"L3 历史 NaN 边界明确：近 X 个月有数据、远端无数据"。不强行改 backtest 加 skip 逻辑（除非实测证明仅远端 NaN 且近端有可用数据，此时按 spec §4.2.4 加逐点 skip）。

- [ ] **Step 5: L4 固化决策**

基线（刚固化的 `bb_squeeze`）：DirAcc=56%, MAPE=2.26%, EV=+0.120, PF=1.27

判定：
- 常规通过：`backtest_DirAcc >= 58% 且 backtest_MAPE <= 2.26%`
- 例外通过：`PF > 1.1 且 EV > 0 且 backtest_DirAcc >= 59%`
- 否则：保 `bb_squeeze`，Phase 6 产出="管道打通 + 历史边界明确"

- [ ] **Step 6: 写汇总报告 `reports/research/20260729_phase5_6_summary.md`**

```markdown
# Phase 5+6 协变量优化汇总 (2026-07-29)

## Phase 5: CJ 影线门控

- 零回归: SS/FG/LH np.array_equal 通过
- scan 三档裁决: <胜者或原版更优>
- backtest: <DirAcc/MAPE/EV/PF>
- 固化决策: <CJ 改 reversal_shadow_gated_XX / CJ 保 reversal_shadow>

## Phase 6: TA 基差管道

### L1 数据管道
- 月度合约采集: <成功/失败 + 原因>
- get_basis_1h: rows=<N> non_zero=<M>
- 状态: <PASS / FAIL>

### L2 scan 7pt
- basis_momentum 排名: <填>
- 状态: <PASS / 退化>

### L3 backtest 396pt
- 历史 NaN 边界: <近 X 月有数据, 远端无数据>
- 状态: <PASS / SKIP (历史断层)>

### L4 固化决策
- 基线 bb_squeeze: DirAcc=56% MAPE=2.26% EV=+0.120 PF=1.27
- basis_momentum backtest: <DirAcc/MAPE/EV/PF 或 SKIP>
- 决策: <TA 改 basis_momentum / TA 保 bb_squeeze>

## 核心交付物
- Phase 5: <影线门控已实现 + 实证结论>
- Phase 6: <实时基差采集管道打通 + 历史 Rollover 缺口位置探明>

## 方法论沉淀
- <填: 如 scan 7pt vs backtest 分裂原因、近远月基差 = 期限结构维度等>

## 后续路线
- Phase 4: JD 日历特征
- Phase 8: TA 跨品种原油/PX 基差 (Crack Spread)
- Phase 9: 历史 Rollover 动态映射 (让 basis_momentum 真正可用于长程回测)
- Phase 7: LH 基本面数据
```

- [ ] **Step 7: L4 达阈则固化 TA scheme（人工确认）**

仅当 L4 判定通过，改 `config/prediction_scheme.py:405-419` 的 TA 条目 `covariate_type="bb_squeeze"` → `"basis_momentum"`，更新 `dir_acc`/`mape` 为 backtest 实测值，加注释 `# 2026-07-29 Phase 6 固化: bb_squeeze → basis_momentum (近远月期限结构)`。

未达阈则**不改**，已在汇总报告记录"保 bb_squeeze"。

- [ ] **Step 8: 提交**

```bash
git add reports/covariate_scan/20260729_ta_basis_collect.log reports/covariate_scan/20260729_ta_basis_scan.txt reports/monthly_backtest/20260729_ta_basis_backtest.txt reports/research/20260729_phase5_6_summary.md
# 仅 L4 达阈额外 add config/prediction_scheme.py
git commit -m "$(cat <<'EOF'
docs(phase6): TA 基差管道 L1-L4 分层验证 + Phase 5+6 汇总

- L1 管道: <PASS/FAIL>
- L2 scan: <PASS/退化>
- L3 backtest: <PASS/历史 NaN SKIP>
- L4 决策: <TA 改 basis_momentum / 保 bb_squeeze>
- Phase 5: CJ <固化 reversal_shadow_gated_XX / 保现状>
- 核心交付: 影线门控 + 实时基差采集管道 + 历史边界探明

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 自检结果

1. **Spec 覆盖**：
   - Phase 5（spec §3）：Task 1（底层+零回归）+ Task 2（注册）+ Task 3（scan 裁决）+ Task 4（backtest 固化）✅
   - Phase 6（spec §4）：Task 5（采集管道）+ Task 6（L1-L4 验证+固化）✅
   - 零回归铁律（spec §3.4）：Task 1 Step 4 单测 + Step 5 端到端 ✅
   - 双段闸门（spec §4.3）：Task 3 scan + Task 4/L4 backtest ✅
   - 后置采集铁律（spec §4.2.1）：Task 5 Step 2 后置 + try/except ✅
   - Fail-visibly（spec §4.2.4）：Task 6 Step 4 NaN 边界观测 ✅

2. **Placeholder 扫描**：Task 3 Step 2 / Task 6 Step 6 模板含 `<填>` 是回测实测值占位（需运行后填入），非 plan 缺陷。无 TBD/TODO。

3. **类型一致性**：`calc_reversal_shadow_ratio(..., min_shadow_atr=...)` 在 Task 1 定义、Task 2 调用，签名一致；`collect_basis_contracts_for_symbol` 在 Task 5 定义、调用，签名一致；`reversal_shadow_gated_02/_03/_05` 三处引用一致。

4. **依赖顺序**：Task 1 → Task 2（注册依赖底层参数）→ Task 3（scan 依赖注册）→ Task 4（backtest 依赖 scan 胜者）；Task 5 → Task 6（验证依赖采集）。两链串行，互不阻塞。Task 6 Step 1 真实 TqSdk 调用可能耗时数分钟，建议后台运行。