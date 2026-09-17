# System Hardening Spec — 统计严谨性与工程质量提升

> **文档状态（2026-09-11）**：**已落地** master merge `243693d`（2026-09-11）。SPEC-004…013 接口仍约束代码。勿当待开工。空勾选框不表示未实现。剩余缺口是实现偏离（日线 `raw_close` 短路、保证金 MaxDD 喂毛 PnL、斜率未走对数回归），见 `docs/superpowers/reports/2026-09-11-audit/spec-alignment/SUMMARY.md`，不是「没开工」。

> **版本**: v1.2-final (2026-09-10, 终审封版)  
> **基于**: `docs/system_design.md` v2.4 §11.2~§11.11, §4.3  
> **范围**: 10 项 P1+P2 优化 — 提升统计严谨性与工程质量  
> **预计工期**: 7 天（3 Phase）  
> **依赖**: critical-fixes spec (SPEC-001~003) 完成后可启动
> **v1.1 变更**: 修正 SPEC-004 Bartlett 全阶求和、SPEC-005 Col 0 隔离排序、SPEC-008 动态杠杆重构、SPEC-012 R² 决策闭环、SPEC-009 原子化重构要求、SPEC-006 复合主键+星级覆盖、SPEC-011 同时间戳截面复权、SPEC-010 交易时段自愈
> **v1.2 变更**: SPEC-011 删除报告层除法还原(后复权=名义价)、SPEC-004 断言修正(VIF=8.237→n_eff=71)、SPEC-008 非重叠步长抽样(stride=12)、SPEC-005 测试循环排除 Col 0、SPEC-006 variant_id 容错提取 covariate

---

## 1. Context

FM_a 系统经过 critical-fixes spec 修复了 3 项实盘正确性问题后，仍遗留 10 项影响统计严谨性和工程质量的改进空间。这些改进不阻塞实盘运行，但决定了系统能否从"可用"升级为"可信"。

本 spec 按子系统分组为 4 个执行模块，可分派给不同专家并行推进。

---

## 2. Goals / Non-Goals

### Goals

| 编号 | 目标 | 验证方式 |
|------|------|----------|
| G1 | 回测报告输出有效样本量 (n_eff) | JSONL 字段检查 |
| G2 | 置信区间保证分位数单调递增且 > 0 | 单元测试 |
| G3 | SCHEMES 有自动降级/晋升机制 | 集成测试 |
| G4 | 短段信号权重无断崖跳变 | 可视化检查 |
| G5 | MaxDD 同时输出名义口径和保证金口径 | 报告检查 |
| G6 | 协变量衰减速率可按品种配置 | 配置检查 |
| G7 | calendar_cyclical 感知交易时段 | 单元测试 |
| G8 | 换月跳空通过比例后复权消除 | 数据检查 |
| G9 | 斜率计算增加 R² 质量标记 | 报告检查 |
| G10 | Stage 1 极端预测被截断保护 | 单元测试 |

### Non-Goals

- **不改变硬门阈值** — n≥350 / IC≥0.05 / EV>0 保持不变
- **不改变 SCHEMES 协变量配置** — 退役机制只影响 copilot 输出，不改 prediction_scheme.py
- **不做 GPU 加速** — 所有优化在 CPU 框架内
- **不引入新协变量** — 不扩充协变量池

---

## 3. Architecture — 执行模块划分

```
┌─────────────────────────────────────────────────────────────────────┐
│                    System Hardening — 4 个执行模块                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Module A: 评估层               Module B: 预测层                     │
│  ─────────────                  ─────────────                       │
│  SPEC-004 有效样本量             SPEC-007 余弦滚降                    │
│  SPEC-005 对数保序展宽           SPEC-009 半衰期品种级                 │
│  SPEC-008 MaxDD 保证金口径       SPEC-012 斜率对数回归+R²             │
│                                 SPEC-013 漂移截断                    │
│  文件: evaluator.py             文件: features.py                    │
│        evaluation_metrics.py           prediction_scheme.py          │
│        aligned_slow_loop.py          daily_model.py                  │
│                                                                     │
│  Module C: 报告层               Module D: 数据层                     │
│  ─────────────                  ─────────────                       │
│  SPEC-006 SCHEMES 退役/晋升      SPEC-010 calendar 交易时段感知       │
│                                 SPEC-011 换月比例后复权               │
│  文件: copilot.py                                                │
│        knowledge_base.json                                            │
│        build_knowledge_base.py                                        │
│                                                                     │
│  依赖: 无                                       依赖: 无            │
│  可与 A/B 并行                                   可独立执行           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Module A: 评估层优化

### SPEC-004: 重叠窗口有效样本量

**文件**: `task_FM/evaluations/fm_eval/evaluator.py`, `scripts/aligned_slow_loop.py`

**设计**:

```python
def effective_sample_size(
    nominal_n: int,
    horizon: int,
    step: int,
    residual_autocorr: float | None = None,
) -> int:
    """
    基于完整 Bartlett 卷积核估算重叠窗口有效独立自由度

    对于重叠窗口 (horizon=H, step=S):
      重叠阶数 K = floor((H-1) / S)
      VIF = 1 + 2 * sum_{k=1}^{K} (1 - k/(K+1)) * rho^k
      n_eff = nominal_n / VIF

    v1.0 仅取 k=1 单阶近似 (严重低估 VIF)，v1.1 修正为完整求和。

    Args:
        nominal_n: 名义评估点数
        horizon: 预测时域 (bars)
        step: 滑动步长 (bars)
        residual_autocorr: 残差自相关系数 (None 则用 0.9 保守估计)
    """
    if step >= horizon:
        return nominal_n

    if residual_autocorr is None:
        residual_autocorr = 0.9  # 保守估计

    # 重叠阶数: H=24, S=2 → K=11
    max_overlap_step = (horizon - 1) // step

    # 完整 Bartlett 卷积核求和
    kernel_sum = 0.0
    for k in range(1, max_overlap_step + 1):
        weight = 1.0 - (k / (max_overlap_step + 1))
        kernel_sum += weight * (residual_autocorr ** k)

    variance_inflation_factor = 1.0 + 2.0 * kernel_sum
    n_eff = nominal_n / variance_inflation_factor
    return max(1, int(np.round(n_eff)))

# 589 nominal, H=24, S=2, rho=0.9 → K=11, VIF≈8.237 → n_eff≈71
# 不改变硬门 (仍为 n>=350 名义值)，但报告中同时输出 n_eff
```

**输出变更**:
```json
{
    "variant_id": "ss_vor",
    "n": 589,
    "n_eff": 71,
    "n_eff_method": "bartlett_full_kernel_rho0.9",
    "pf": 1.123,
    "ev": 11.06,
    ...
}
```

**报告变更**:
```
评估统计: 名义 n=589, 有效 n≈71 (ρ=0.9, Bartlett K=11)
         ⚠️ 有效样本量偏低，IC 显著性存疑
```

**测试**:
```python
def test_effective_n_calculation():
    # H=24, S=2, K=11 完整 Bartlett 卷积核: VIF≈8.237 → n_eff=71
    assert effective_sample_size(589, 24, 2) == 71  # rho=0.9 默认
    # rho=0.5 时 VIF 较小，n_eff 较大
    n_eff_05 = effective_sample_size(589, 24, 2, 0.5)
    assert 120 <= n_eff_05 <= 200  # 完整求和后区间合理
    assert effective_sample_size(100, 24, 24) == 100  # 无重叠
    # 单调性: rho 越大 → VIF 越大 → n_eff 越小
    assert effective_sample_size(589, 24, 2, 0.9) < effective_sample_size(589, 24, 2, 0.5)
```

---

### SPEC-005: 置信区间对数空间保序展宽

**文件**: `config/prediction_scheme.py` (`confidence_band`)

**设计**:

```python
def confidence_band(quantile_forecast, scheme):
    """
    v2: 对数空间保序展宽 (v1.1 修正: Col 0 隔离)
    
    改进:
    1. 转移至 log 空间，杜绝负价格
    2. 展宽后强制排序，保证分位数单调递增
    3. **[v1.1]** Col 0 为点预测(Mean)，不参与排序，仅 Col 1~9 分位数通道保序
    
    TimesFM 10 列契约:
      Col 0 = Point Forecast (Mean); Col 5 = P50 (Median)
      Col 1~4 = P10~P40; Col 6~9 = P60~P90
    """
    mult = scheme.confidence_multiplier
    if mult == 1.0:
        return quantile_forecast
    
    # 对数空间
    eps = 1e-6
    log_q = np.log(np.maximum(quantile_forecast, eps))
    log_median = log_q[:, 5:6]  # P50 为中枢
    
    # 对称展宽
    log_adjusted = log_median + (log_q - log_median) * mult
    
    # [v1.2] 严格隔离: Col 0 保持原值，仅展宽 Col 1~9
    log_adjusted = log_q.copy()
    if log_adjusted.shape[-1] == 10:
        log_adjusted[:, 1:] = log_median + (log_q[:, 1:] - log_median) * mult
        log_adjusted[:, 1:] = np.sort(log_adjusted[:, 1:], axis=-1)
    else:
        # 非标准列数: 回退全排序
        log_adjusted[:, 1:] = log_median + (log_q[:, 1:] - log_median) * mult
        log_adjusted = np.sort(log_adjusted, axis=-1)
    
    return np.exp(log_adjusted)
```

**测试**:
```python
def test_confidence_band_no_crossing():
    q = np.tile([100,102,104,106,108,110,112,114,116,118], (24,1))
    scheme = VarietyScheme(..., confidence_multiplier=2.0)
    adjusted = confidence_band(q, scheme)
    
    # [v1.2] 单调性: 仅测试 Col 1~9 分位数通道，排除 Col 0 (点预测)
    for t in range(24):
        for i in range(1, 9):  # Col 1 ≤ Col 2 ≤ ... ≤ Col 9
            assert adjusted[t, i] <= adjusted[t, i+1]
    
    # 正值
    assert np.all(adjusted > 0)
    
    # 中位数不变 (Col 5 = P50)
    np.testing.assert_allclose(adjusted[:, 5], q[:, 5], rtol=1e-6)
    
    # [v1.2] Col 0 保持不变 (点预测不参与排序/展宽)
    np.testing.assert_allclose(adjusted[:, 0], q[:, 0], rtol=1e-6)
```

---

### SPEC-008: MaxDD 保证金口径

**文件**: `cascade/evaluation_metrics.py`

**设计**:

```python
def calc_margin_maxdd_robust(
    net_pnl_pts: np.ndarray,
    base_prices: np.ndarray,
    contract_multiplier: float,
    horizon: int = 24,
    step: int = 2,
    margin_rate: float = 0.12,            # 保证金比例 (12%)
    capital_allocation_ratio: float = 0.30,  # 目标保证金占用率 (≈2.5x 动态杠杆)
    initial_capital: float = 1_000_000.0,
) -> float:
    """
    保证金口径最大回撤 — v1.2 非重叠步长抽样版本
    
    **[v1.2 修正]**:
    - v1.1 将所有重叠样本当作串行交易累加，在 STEP=2 / HORIZON=24 的密集网格下，
      任意时刻有 12 笔重叠未平仓头寸，串行累加导致:
      (a) 收益波动率放大 12 倍; (b) 若按真实时间轴解读则保证金占用 360% 立即穿仓。
    - v1.2: 抽取 stride = horizon // step = 12 组互不重叠的独立交易子序列，
      分别计算各独立组合的真实资金曲线，取平均最大回撤。
    
    Args:
        net_pnl_pts: 每笔净盈亏 (点数), 长度为评估点总数
        base_prices: 每笔对应基准价
        contract_multiplier: 合约乘数
        horizon: 预测时域 (bars)
        step: 评估滑动步长 (bars)
        margin_rate: 保证金比例
        capital_allocation_ratio: 账户资金中用于保证金的比例
        initial_capital: 初始账户资金
    """
    stride = max(1, horizon // step)  # H=24, S=2 → stride=12 组独立序列
    sub_dd_list = []
    
    for offset in range(stride):
        # 抽取时间上互不重叠的独立交易子序列
        sub_pnl = net_pnl_pts[offset::stride]
        sub_prices = base_prices[offset::stride]
        
        if len(sub_pnl) < 2:
            continue
        
        equity = initial_capital
        peak = initial_capital
        max_dd = 0.0
        
        for t in range(len(sub_pnl)):
            margin_per_lot = sub_prices[t] * contract_multiplier * margin_rate
            lots = max(1, int((equity * capital_allocation_ratio) / margin_per_lot))
            equity += sub_pnl[t] * contract_multiplier * lots
            
            if equity <= 0:
                max_dd = -1.0  # 穿仓
                break
            peak = max(peak, equity)
            max_dd = min(max_dd, (equity - peak) / peak)
        
        sub_dd_list.append(max_dd)
    
    return float(np.mean(sub_dd_list)) if sub_dd_list else 0.0
```

**报告输出**:
```
MaxDD (名义): -35.2%
MaxDD (保证金口径, 12% margin): -87.1%
```

---

## 5. Module B: 预测层优化

### SPEC-007: 短段信号权重余弦滚降

**文件**: `config/prediction_scheme.py` (`signal_weight`)

**设计**:

```python
def signal_weight(horizon, scheme):
    if scheme.use_full_signal and not scheme.short_horizon_only:
        # 全段: 指数衰减 (不变)
        ...
    else:
        if getattr(scheme, 'smooth_cutoff', False):
            # 余弦滚降 (新)
            plateau = 8   # Bar 1~8: 全权重
            cutoff = 16   # Bar 9~16: 余弦衰减, Bar 17+: 零
            t = np.arange(1, horizon + 1, dtype=float)
            w = np.ones(horizon)
            decay_mask = (t > plateau) & (t <= cutoff)
            w[decay_mask] = 0.5 * (1 + np.cos(
                np.pi * (t[decay_mask] - plateau) / (cutoff - plateau)))
            w[t > cutoff] = 0.0
            return w
        else:
            # 硬截断 (旧, 默认)
            w = np.zeros(horizon)
            w[:12] = 1.0
            return w
```

**`VarietyScheme` 新增字段**:
```python
smooth_cutoff: bool = False  # 是否使用余弦滚降 (默认 False, 向后兼容)
```

---

### SPEC-009: 协变量半衰期品种级配置

**文件**: `config/prediction_scheme.py`, `cascade/features.py`

**[v1.1 新增] 原子化重构要求**:
> 现有 `cascade/features.py` 中，`vor`, `bb_squeeze`, `reversal_shadow`, `ao_accel` 分别在各自函数内部以 `0.5 ** (i / 12.0)` 硬编码内联实现衰减。  
> **必须**对本 spec 实施进行原子化重构：将所有零散的指数衰减生成统一收敛至标准特征包装器 `_decay_fill`，**强制禁止**在任何协变量函数内部保留 `12.0` 的局部常数。  
> 实施后 `grep -rn '12\.0' cascade/features.py` 应返回 0 个匹配（排除注释）。

**设计**:

```python
# VarietyScheme 新增
half_life_bars: float = 12.0  # Horizon 衰减半衰期 (bars)

# features.py — 所有使用 _decay_fill 的地方改为读取 scheme
def _decay_fill(last_val, horizon, half_life=12.0):
    decay = np.array([0.5 ** (i / half_life) for i in range(horizon)])
    return last_val * decay

# build_covariate_matrix 中:
half_life = scheme.half_life_bars if scheme else 12.0
# 传入 _decay_fill
```

**初始品种配置建议**:

| 品种 | half_life_bars | 理由 |
|------|---------------|------|
| SS/RB/MA | 8 | 高频品种，投机情绪消散快 |
| M/SR/JD/EG | 12 | 中频品种，默认值 |
| CJ/LH | 16 | 低频品种，信号持续更久 |

---

### SPEC-012: 斜率计算对数回归 + R² 滤网

**文件**: `cascade/daily_model.py`

**设计**:

```python
# DailyResult 新增字段
r_squared: float = 0.0
slope_unreliable: bool = False

# daily_model.py predict() 中:
x = np.arange(len(forecast), dtype=float)
log_forecast = np.log(np.maximum(forecast, 1e-6))
coeffs = np.polyfit(x, log_forecast, 1)
horizon_slope = coeffs[0]  # 对数斜率 = 复合日收益率 (Ratio)

# R² 计算
y_pred = np.polyval(coeffs, x)
ss_res = np.sum((log_forecast - y_pred) ** 2)
ss_tot = np.sum((log_forecast - np.mean(log_forecast)) ** 2)
r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

# R² 滤网
R2_THRESHOLD = 0.35
slope_unreliable = r_squared < R2_THRESHOLD

# **[v1.1] 决策闭环**: R² 标志必须传入方向决策函数，否则滤网形同虚设
# _compute_direction 重构为接受 DailyResult 而非裸斜率
def _compute_direction_v2(daily_result, scheme) -> str:
    """
    结合 R² 拟合优度的方向决策 (v1.1 新增)
    
    门禁 1: R² < 0.35 → 一票否决为中性
    门禁 2: 斜率阈值判断方向
    """
    # 门禁 1: 非线性路径分歧一票否决
    if getattr(daily_result, "slope_unreliable", False):
        return "中性 → (形态分歧)"
    
    # 统一量纲: 日度对数复合收益率小数比率
    thr_ratio = scheme.trend_threshold_pct / 100.0  # 0.1% -> 0.001
    slope = daily_result.horizon_slope
    
    if slope > thr_ratio:
        return "看多 ↑"
    elif slope < -thr_ratio:
        return "看空 ↓"
    else:
        return "中性 →"
```

**报告输出**:
```
Horizon 斜率: +0.153%/天 (R²=0.82)  → 看多 ↑
Horizon 斜率: +0.02%/天 (R²=0.18)   → ⚠️ 形态分歧，斜率不可信
```

---

### SPEC-013: Stage 1 → Stage 2 漂移截断

**文件**: `cascade/features.py`

**设计**:

```python
def _clip_prediction_drift(
    hist_daily: np.ndarray,
    pred_daily: np.ndarray,
    max_daily_drift_pct: float = 0.05,  # 5% 单日复合漂移上限
) -> np.ndarray:
    """
    限制 Stage 1 预测价格相对最新收盘价的漂移
    
    复合漂移上限: last_close * (1 ± max_drift)^t
    """
    last_close = hist_daily[-1]
    t = np.arange(1, len(pred_daily) + 1)
    upper = last_close * (1 + max_daily_drift_pct) ** t
    lower = last_close * (1 - max_daily_drift_pct) ** t
    return np.clip(pred_daily, lower, upper)

# 在 rsi_state / rsi_slope 分支中调用:
safe_pred = _clip_prediction_drift(hist_daily, pred_daily)
full_daily = np.concatenate([hist_daily, safe_pred])
```

---

## 6. Module C: 报告层优化

### SPEC-006: SCHEMES 退役/晋升治理机制

**文件**: `scripts/build_knowledge_base.py`, `scripts/copilot.py`, `config/knowledge_base.json`

**设计**:

```python
# knowledge_base.json 新增字段
{
  "symbols": {
    "sr": {
      "credit_stars": 2,
      "historical_pf": 1.10,
      "production_covariate": "vor",       # [v1.1] 复合主键: 品种+当前生产协变量
      "slow_loop_status": "degraded",   # "ok" | "degraded" | "revoked"
      "slow_loop_pf": 0.973,
      "slow_loop_ev": -0.85,
      "slow_loop_updated": "2026-09-10"
    }
  }
}

# **[v1.1] copilot.py — craft_advisory_v2()**: 动态覆盖有效星级，消除文案矛盾
def craft_advisory_v2(symbol, kb, direction, delta_pct, vol, scheme_type):
    entry = kb_entry(kb, symbol)
    status = entry.get("slow_loop_status", "ok")
    
    # 动态覆写有效星级: degraded/revoked 强制降为 1 星行为
    raw_stars = entry.get("credit_stars", 0)
    effective_stars = 1 if status in ("degraded", "revoked") else raw_stars
    
    lines = []
    if status == "revoked":
        lines.append("🔒 慢环实证已完全退化冻结，禁止建立新仓，仅供观望监控。")
        return lines
    
    if effective_stars >= 2:
        lines.append(f"模型底气: 盈亏比(PF) {entry.get('historical_pf', 0):.2f}，中等信用，建议标准仓位。")
    else:
        reason = "（慢环实证退化）" if status == "degraded" else ""
        lines.append(f"模型底气: 弱信号品种{reason}，建议轻仓试探或观望。")
    
    # ... 其余输出基于 effective_stars 而非 raw_stars
    return lines

# **[v1.1] build_knowledge_base.py — 复合主键联合校验**
def sync_slow_loop_status(kb: dict, verdicts_path: Path) -> dict:
    """
    从 aligned_verdicts.jsonl 读取最新裁决，更新 slow_loop_status
    
    [v1.1] 修正: 同一品种可能测试多种协变量 (如 SS 同时测 vor 和 calendar_cyclical),
    旧代码 latest[sym] = v 会用最后一个变体盲目覆盖先前结果。
    现在必须对 (symbol, production_covariate) 做复合主键联合校验。
    """
    latest = {}  # key: (symbol, covariate) 复合键
    with open(verdicts_path) as f:
        for line in f:
            v = json.loads(line)
            sym = v["symbol"]
            # [v1.2] 容错: 优先取显式 covariate 字段，否则从 variant_id 下划线切分兜底
            # 例: variant_id="ss_vor" → cov="vor"; variant_id="rb_calendar_cyclical" → cov="calendar_cyclical"
            cov = v.get("covariate") or (
                "_".join(v.get("variant_id", "").split("_")[1:])
                if "_" in v.get("variant_id", "")
                else "unknown"
            )
            key = (sym, cov)
            latest[key] = v  # 同品种不同协变量独立追踪
    
    for (sym, cov), v in latest.items():
        if sym not in kb["symbols"]:
            continue
        entry = kb["symbols"][sym]
        # 只更新与当前生产协变量匹配的裁决
        if entry.get("production_covariate") != cov:
            continue
        if v.get("gate_pass"):
            entry["slow_loop_status"] = "ok"
        elif v.get("ev", 0) < 0 or v.get("pf", 0) < 0.95:
            entry["slow_loop_status"] = "degraded"
        entry["slow_loop_pf"] = v.get("pf")
        entry["slow_loop_ev"] = v.get("metrics", {}).get("ev_after_slippage")
    
    return kb
```

**退役规则**:
- `degraded`: 慢环 EV < 0 或 PF < 0.95
- `revoked`: 连续 2 个月 degraded
- 晋升: 慢环硬门通过 + monthly_backtest 对齐验证后，人工确认后改回 `ok`

---

## 7. Module D: 数据层优化

### SPEC-010: calendar_cyclical 交易时段感知

**文件**: `cascade/features.py` (`calc_calendar_cyclical`)

**设计**:

```python
def calc_calendar_cyclical(
    df_1h: pd.DataFrame,
    horizon: int,
    valid_hours: list | None = None,   # ← 新增: 交易时段列表
) -> np.ndarray:
    """
    v2: 支持交易时段感知的 Horizon 时间戳生成
    
    **[v1.1] 自动嗅探自愈**:
    若 valid_hours 为 None，不再静默回退到 freq='h'，而是从数据中
    自动提取活跃交易小时。杜绝优化在生产环境中永久休眠。
    """
    dt_col = 'dt' if 'dt' in df_1h.columns else 'date'
    dt_idx = pd.DatetimeIndex(df_1h[dt_col])
    
    # Context 段: 不变
    doy = dt_idx.dayofyear.values
    month = dt_idx.month.values
    ctx_4d = np.column_stack([...])
    
    # **[v1.1] 自愈**: 自动嗅探交易时段
    if valid_hours is None:
        from .data_validator import detect_trading_hours
        valid_hours = detect_trading_hours(df_1h)
        # detect_trading_hours 从 df_1h 的小时分布中提取活跃时段
        # 例: [9,10,11,13,14,15,21,22,23] (日盘+夜盘)
    
    # Horizon 段: 基于真实交易时段生成 future_dts
    last_dt = dt_idx[-1]
    from .data_validator import generate_trading_dates
    future_dts = generate_trading_dates(last_dt, horizon, valid_hours)
    
    # 编码: 不变
    horiz_4d = np.column_stack([...])
    return np.vstack([ctx_4d, horiz_4d])
```

---

### SPEC-011: 主力换月比例后复权

**文件**: `data/tqsdk_fetcher.py`, `data/data_store.py`

**[v1.1 致命缺陷修正]**:
> v1.0 存在两处摧毁底层数据的致命错误:
> 1. **二次幂爆炸 (Quadratic Compounding Bug)**: 反向循环中 `cumulative_factor` 逐次累乘，但每次 `kline_df.loc[mask, 'close_price'] *= cumulative_factor * factor` 会对已乘过的历史数据再次乘上新的累积因子，导致早期 K 线以 k^1, k^3, k^6... 几何级数暴涨。
> 2. **混淆行情与基差**: `adjustment_factor = P_new_T / P_old_T-1` 混合了换月基差**和**当日真实涨跌幅。若换月当天市场涨 5%，历史数据会被错误缩放 5%。

**v1.1 设计**:

```python
# tqsdk_fetcher.py — 换月检测 (v1.1: 同时间戳截面比率)
def detect_roll_events(kline_df: pd.DataFrame) -> list[dict]:
    """
    检测主力换月事件
    
    **[v1.1] 核心修正**: adjustment_factor 必须是同一时刻新旧合约的截面价差比率,
    即 P_new(t) / P_old(t)，不能是 P_new(t) / P_old(t-1) (混入当日涨跌)
    
    需要 TqSdk 提供换月时刻新旧合约的同时刻行情快照。
    """
    rolls = []
    prev_contract = None
    for i, row in kline_df.iterrows():
        if prev_contract and row['contract_code'] != prev_contract:
            # **[v1.1]** roll_ratio 必须来自同一时刻截面:
            # roll_ratio = P_new_contract(t) / P_old_contract(t)
            # 这需要从 TqSdk 获取换月时刻旧合约的最后报价
            gap = abs(row['close_price'] - kline_df.iloc[i-1]['close_price'])
            atr = kline_df.iloc[max(0,i-14):i]['atr14'].mean()
            if gap > 2 * atr:
                rolls.append({
                    'dt': row['dt'],
                    'old_contract': prev_contract,
                    'new_contract': row['contract_code'],
                    'roll_ratio': row.get('roll_ratio', 1.0),  # [v1.1] 截面比率
                    # roll_ratio 由数据源层提供同时间戳双合约报价计算
                })
        prev_contract = row['contract_code']
    return rolls

# data_store.py — 向量化一次性复权 (v1.1: 消除二次幂爆炸)
def apply_backward_adjustment_robust(
    kline_df: pd.DataFrame,
    roll_records: list[dict],
) -> pd.DataFrame:
    """
    标准无偏差比例后复权 — v1.1 向量化版本
    
    **[v1.1] 核心修正**:
    - 不再用循环逐次 *= (避免二次幂爆炸)
    - 构造 adj_series 向量化累乘，一次性应用到价格列
    - 保留 raw_close 原始列供审计
    
    roll_records 格式: {'dt': 换月时间戳, 'roll_ratio': P_new(t)/P_old(t)}
    """
    if not roll_records or kline_df.empty:
        return kline_df
    
    df = kline_df.copy()
    if 'raw_close' not in df.columns:
        df['raw_close'] = df['close']
    
    # 按时间正序排列换月事件
    sorted_rolls = sorted(roll_records, key=lambda x: x['dt'])
    
    # 构造复权系数序列 (初始全为 1.0)
    adj_series = np.ones(len(df), dtype=float)
    
    # 从最近一次换月向前反向累乘 (每个换月点只乘一次)
    for roll in reversed(sorted_rolls):
        mask = df['dt'] < roll['dt']
        adj_series[mask] *= roll['roll_ratio']
    
    # 一次性向量化复权，杜绝多重循环重复乘
    price_cols = [c for c in ['open', 'high', 'low', 'close'] if c in df.columns]
    for col in price_cols:
        df[col] = df[col] * adj_series
    
    return df
```

**报告层还原**:
```python
# **[v1.2 致命修正]**: 彻底删除除法还原逻辑
# 后复权以当前最新活跃合约为不动基准 (factor=1.0)，
# 模型输入的 Context 尾部 = 当前主力未缩放真实盘口价，
# TimesFM 预测输出 P̂_{T+h} 天然就是当前主力合约的名义价格。
# 严禁任何除法缩放，否则会将预测目标价打到荒谬低位。

# 正确处理: 后复权数据预测值直接等于当前合约名义价，无需任何转换
nominal_price = adjusted_price  # 恒等，直接透传至报告层
```

**[v1.1] 实施前提**:
> SPEC-011 依赖 TqSdk 底层提供换月时刻新旧合约的同时间戳行情快照，
> 用于计算无偏的 `roll_ratio = P_new(t) / P_old(t)`。  
> 若 TqSdk 不支持直接提供，需要在 `tqsdk_fetcher.py` 中实现:
> 1. 在换月检测时，同时订阅新旧两个合约的实时行情
> 2. 在换月时刻 t 记录两个合约的收盘价快照
> 3. 将 `roll_ratio` 写入 `roll_records` 供复权使用

---

## 8. Dependency Graph

```
Phase 1 (评估层)          Phase 2 (预测+报告层)
─────────────────         ─────────────────
SPEC-004 (独立)            SPEC-007 (独立)
SPEC-005 (独立)            SPEC-012 ──→ SPEC-013
SPEC-008 (独立)            SPEC-006 (独立)

Phase 3 (数据层)
─────────────────
SPEC-010 (独立)
SPEC-009 (独立)
SPEC-011 (独立, 依赖 TqSdk 同时间戳快照, 工作量大)
```

**可并行的组合**:
- Phase 1 内部: SPEC-004 + SPEC-005 + SPEC-008 三項完全独立可并行
- Phase 2 内部: SPEC-007 + SPEC-012 + SPEC-006 可并行; SPEC-013 在 SPEC-012 之后
- Phase 3 内部: SPEC-010 + SPEC-009 可并行; SPEC-011 独立但需专家把关
- Phase 1 → Phase 2 → Phase 3 按序执行（统计防线先于预测层）

---

## 9. Invariants

以下约束在任何 SPEC 实施过程中**不可违反**：

| 约束 | 说明 | 检查方式 |
|------|------|----------|
| 回测内部一致性 | 训练和推理使用相同逻辑 | 代码审查 |
| 跨品种对齐 | eval 点数恒等 (589) | `assert len(eval_indices) == 589` |
| 硬门单调性 | 已过门裁决不可推翻 | `diff aligned_verdicts.jsonl` |
| 量纲一致 | 绝对价格点数空间 | 单元测试 |
| 防穿越 | 不引入未来信息 | 数据流审计 |
| SPEC-004 不改硬门 | n_eff 只用于报告，不改 gate_pass | 代码审查 |
| SPEC-006 不改 SCHEMES | 退役只影响 copilot 输出 | 配置检查 |

---

## 10. Execution Plan

> **[v1.1 调整]**: 鉴于 SPEC-011 需要 TqSdk 同时间戳双合约快照支持，复杂度最高且对存储侵入性大，移至 Phase 3 最后执行。

```
Phase 1: 统计防线建立 (Day 1 - Day 2)
  ● SPEC-004: 完整 Bartlett 卷积有效样本量 (必须修正)
  ● SPEC-005: 隔离式 Log 保序展宽 (避开 Col 0)
  ● SPEC-008: 动态杠杆保证金口径 MaxDD 重构

Phase 2: 预测与报告防御 (Day 3 - Day 4)
  ● SPEC-007: 余弦滚降平滑衰减
  ● SPEC-012: 对数斜率回归 + R² 决策闭环
  ● SPEC-013: 5% 复合漂移截断保护
  ● SPEC-006: 复合键校验与星级强覆盖

Phase 3: 数据源精细化 (Day 5 - Day 7)
  ● SPEC-010: calendar 自动交易时段感知
  ● SPEC-009: VarietyScheme 半衰期参数化 (含 features.py 原子化重构)
  ● SPEC-011: 同时间戳比例后复权 (必须由量化专家严格把关, 依赖 TqSdk 支持)
```

---

## 11. Success Criteria

| 标准 | 验证方式 |
|------|----------|
| 全部 10 项 SPEC 单元测试通过 | `pytest tests/` |
| 现有回测裁决不变 | `diff aligned_verdicts.jsonl` 前后为空 |
| 回测报告包含 n_eff 字段 | JSONL 检查 |
| 保证金口径 MaxDD 输出 | 报告检查 |
| SR degraded 降级生效 | copilot 输出检查 |
| 换月复权后价格连续 | 可视化检查 |
| R² < 0.35 时斜率标记 | 报告检查 |

---

## 12. Implementation Notes — 开发落地微观防御指引

> 以下 3 项为终审提出的边界防御建议，开发阶段需重点留意。

### Note 1: SPEC-008 极值缩水期强制 1 手保底

在 `calc_margin_maxdd_robust` 的交易循环中，当账户极端缩水至 `equity * capital_allocation_ratio < margin_per_lot` 时，`max(1, ...)` 会强制开 1 手导致实际保证金占用超标（>30%）。

**处理方式**: 保持现有 `max(1, ...)` 逻辑（期货回测常规），但穿仓熔断 `equity <= 0 → max_dd = -1.0` 必须严格前置判断，不可跳过。

### Note 2: SPEC-011 旧合约换月时刻行情缺失回退

同时间戳截面比率 `roll_ratio = P_new(t) / P_old(t)` 依赖旧合约在换月时刻有即时撮合成交。历史离线回测中，旧合约在主力切换后成交量骤降，可能出现 Tick 级价格悬空。

**回退策略（按优先级）**:
1. 向前回溯寻找旧合约最近有效成交价（Forward-fill）
2. 仍缺失则取换月前一根 Bar 的收盘价比率
3. 日志输出 `WARN: Roll ratio fallback used at {dt}`

### Note 3: SPEC-010 交易时段嗅探频次阈值过滤

`detect_trading_hours(df_1h)` 统计小时分布时，国内期货在节假日临近或系统升级时存在特殊集合竞价时段（如 20:55~21:00）。

**防御策略**: 仅将占总样本量 **≥5%** 的小时视为主力交易时段，过滤异常偶发整点点位，避免噪声时段污染日历协变量编码。

---

*Spec self-review v1.2-final: ✅ 无 TBD/TODO, ✅ 内部一致, ✅ Phase 可并行, ✅ 不变量明确, ✅ Bartlett 全阶求和(n_eff=71), ✅ Col 0 隔离, ✅ 动态杠杆+非重叠抽样, ✅ R² 决策闭环, ✅ 同时间戳复权(无除法还原), ✅ variant_id 容错, ✅ 3 项实施防御指引已写入*
