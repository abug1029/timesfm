# Phase 8a: 跨品种 Crack Spread 协变量框架设计 (PX-TA 首验证)

> 状态: 待用户审核
> 涉及品种: TA (PTA) 为首验证标的, feedstock = PX (对二甲苯)
> 依赖: 无新模型; 复用现有 TimesFM XReg + monthly_backtest + covariate_scan
> 前置约束: SC 原油采集延后至 Phase 8b (独立子任务)
> 设计日期: 2026-07-31

---

## 0. 背景与动机

### 0.1 来源

Phase 6 实证 TA 单品种近远月基差 (basis_momentum) 不如 bb_squeeze:

- `config/prediction_scheme.py` TA 归档注 (line 426-429): "后续探索转 Phase 8 (跨品种原油/PX crack spread, 即盘面炼化利润维度)"
- `reports/research/20260729_phase5_6_summary.md §4.2`: "跨品种原油/PX 基差 (炼化利润维度) 仍是未来探索方向 (spec §8 Phase 8)"
- `reports/research/phase4d_conclusions.md D4`: "Crack Spread 季节性先验... crack spread 品种 (FU/BU 等) 多为能化, 按 A1 可能属工业需求驱动, 日历未必生效 - 勿假设, 必须实测"

结论: TA 短期价格驱动 = 成本端 (原油/PX) 跟涨跌 + 波动率爆发, 非单品种现货供需错配。下一步转 Phase 8: 跨品种 crack spread, 即**盘面炼化利润维度**。

### 0.2 核心交付物

Phase 8a 的交付物**不是"一个能跑的价差信号", 而是系统首个跨品种协变量框架**。验证三件事:

1. 双品种 store 对齐 (TA 为主表, PX left-join + ffill)
2. 时间轴 merge 策略 (截止感知, 防穿越)
3. ratio / transform 可配机制 (三模式, scan 数据裁决)

选 PX-TA (芳烃链 PTA 加工费) 因其数据现成、零采集风险。SC 裂解 (SC->FU/BU) 作为 Phase 8b 复用同一框架。

### 0.3 统计功效诚实约束

PX 2023-09-15 上市, 1H 仅 4785 bars (实测)。backtest walk-forward 有效 n ≈ 178 < 350, 触发 v2 Rule 5 underpowered 标记。这是框架的正确输出 ("参考但别重仓"), 非否决项。PX 数据每个交易日增加约 4 根 1H bar, 约 43 个交易日 (≈ 2 个月) 自然增长到 n ≥ 350。**Phase 8a 不固化** (见 §6)。

### 0.4 数据现实 (实测)

| 品种 | 1H bars | 起始 | 回测 n 估算 |
|------|---------|------|-------------|
| TA (PTA) | 13869 | 2016-01 | ~557 |
| PX | 4785 | 2023-09-15 | ~178 (underpowered) |
| FU / BU | 9998 | 2020-08 | ~395 |
| SC (原油) | - | 无 DB | Phase 8b 采集 |

---

## 1. 协变量设计

### 1.1 价差公式与三模式

底层价差 (统一):
```
spread = TA_close - 0.655 × PX_close
```
(0.655 = PTA 生产中 PX 单耗系数, 可配, 写入 config/crack_spread_pairs.py)

| Mode | 协变量 ID | 经济语义 | 数学变换 (显式) | Horizon 填充 |
|------|-----------|----------|------------------|--------------|
| **slope** (默认基准) | `crack_spread_slope` | 利润变化趋势 (趋势跟踪) | `slope = np.polyfit(range(L), spread[-L:], 1)[0]` (L=lookback=20, **对 spread 序列回归**, 非 TA/PX close); `slope_norm = slope / (rolling_std(spread, L) + EPS)`; `tanh(gain × slope_norm)` | 向 0 衰减 (decay_0) |
| level | `crack_spread_level` | 绝对利润区间 (供给侧) | `normed = spread / (rolling_std(spread, 120) + EPS)`; `tanh(gain × normed)` | 常数平铺 (constant) |
| zscore | `crack_spread_zscore` | 均值回归机会 (反转) | `z = (spread - rolling_mean(spread, L)) / (rolling_std(spread, L) + EPS)`; `tanh(gain × z)` | 向 0 衰减 (decay_0) |

设计要点:

- **三模式平等实现为代码分支**, 交由 covariate_scan 24h MAE 数据裁决哪种最匹配当前 PTA 市场。默认 slope (动量斜率最抗过拟合、抗绝对值漂移)。
- **slope 回归对象明确**: 对 `spread` 序列做 lookback 期滚动线性回归, 非 TA_close 或 PX_close。消除语义歧义。
- **tanh 缩放**: slope / zscore 量级与 basis_momentum 差异大, 直接 tanh 会饱和丢失信息。三模式统一: 先归一化 (rolling_std), 再 `tanh(gain × normed)` (与 `calc_ao_acceleration` 的 MAD 缩放同思路, 保相对量级)。spread 是 1D 序列无 H/L/O, 故用 rolling_std 替代 ATR 更自然。**gain 为 tanh 前统一缩放因子 (默认 1.0, scan 可调), 三模式均适用。**
- 与现有 `calc_basis_momentum` 的 mode 机制 (slope/zscore) 完全对齐。

### 1.2 输入源与时间对齐

- `df_main` = 目标品种 (TA) 1H, 以 `dt` 列为基准时间轴 (TA 流动性更好、bar 更完整, 故为主表)
- `df_leg` = feedstock (PX) 1H, 按 `dt` **left-join** 到 df_main, 缺失 PX 价**前向填充 (ffill)**
- 对齐以 TA 为主表: TA 夜盘收盘/熔断停牌与 PX 的细微时间差异, 由 left-join + ffill 吸收 (PX 价粘性强, ffill 误差可忽略)
- merge 后 PX 仍缺失的 bar (早于 PX 首根 bar): spread = NaN -> 协变量填 0

### 1.3 ffill 间隙守卫

`calc_crack_spread` left-join + ffill 后, 加 ffill 间隙守卫:
```python
max_ffill_gap = 4   # 可配 (换月留 1 天缓冲, 默认 4 而非 3)
# 统计每根 bar 的 PX 是 ffill 来的还是真实命中
# 连续 ffill 超过 max_ffill_gap 的 bar -> spread 置 NaN -> 协变量填 0
```
防止换月/停牌时旧合约收盘价被 ffill 带到新合约 bar 上产生虚假价差跳变。

### 1.4 防穿越 (backtest 截止感知)

backtest 用 `BacktestDataStore(symbol, cutoff_date)` 模拟截止。**feedstock 读取必须同样截止**, 否则 TA 历史评估点会泄露未来 PX 价。

- feedstock fetch 继承目标 store 的 `cutoff_date` (`getattr(store, "cutoff_date", None)`)
- backtest 路径: 复用 `BacktestDataStore(fs_sym, cutoff).get_main_contract_1h(limit=480)` (已内置 cutoff 时刻主力合约选择 + end_date 截断, 返回截止前 480 根)
- production/scan 路径: `DataStore(fs_sym).get_main_contract_1h(limit=480)` (返回最新 480 根)

---

## 2. 代码落地位置

### 2.1 `cascade/features.py` - 底层纯函数 + 顶层分发

**新增纯函数** (约 90 行, 放在 `calc_basis_momentum` 附近):
```python
def calc_crack_spread(df_main: pd.DataFrame, df_leg: pd.DataFrame,
                      ratio: float = 0.655, mode: str = "slope",
                      lookback: int = 20, horizon: int = 24,
                      norm_window: int = 120, max_ffill_gap: int = 4,
                      gain: float = 1.0) -> np.ndarray:
    """
    跨品种裂解价差协变量 (纯函数, 不开 DB)

    1. 按 df_main['dt'] left-join df_leg, ffill PX 缺失, ffill 间隙守卫
    2. spread = df_main.close - ratio * df_leg.close
    3. mode 分支:
       - level:  spread / (rolling_std(spread, norm_window) + EPS), tanh, horizon=constant
       - slope:  polyfit 斜率 / (rolling_std + EPS), tanh, horizon=decay_0
       - zscore: (spread - rolling_mean) / (rolling_std + EPS), tanh, horizon=decay_0
    4. 缺失/守卫触发 -> 协变量填 0

    返回: np.ndarray shape (len(df_main) + horizon,), 无 NaN
    """
```

**注册到 `build_covariate_matrix` elif 链** (3 条):
```python
elif covariate_type == "crack_spread_slope":
    fs_sym, ratio = get_crack_pair(symbol)
    df_leg = (feedstock_cache or {}).get(fs_sym) if fs_sym else None
    covariate_full = calc_crack_spread(df_1h, df_leg, ratio, mode="slope", horizon=horizon)
    covariate_name = "crack_spread_slope"
elif covariate_type == "crack_spread_level":    # mode="level",  horizon=constant
    ...
elif covariate_type == "crack_spread_zscore":   # mode="zscore", horizon=decay_0
    ...
```

**`build_combo_covariate_matrix` 同步加 3 条** (combo 成员, 与现有 `calendar_cyclical` / `basis_momentum` 同级)。

**`supported` 列表** (两处) 追加 `"crack_spread_slope"`, `"crack_spread_level"`, `"crack_spread_zscore"`。

**签名变更** (通用 context, 非 crack_spread 专属):
```python
def build_covariate_matrix(symbol, store, ..., covariate_type="ccl",
                           feedstock_cache: Optional[dict] = None):
def build_combo_covariate_matrix(symbol, store, ..., covariate_types=None,
                                 feedstock_cache: Optional[dict] = None):
```
- `feedstock_cache: dict[str, pd.DataFrame]` 是**所有未来跨品种协变量的通用 extension point**, 签名只膨胀一次。
- 非 crack_spread 路径完全不感知它 (默认 None, 从不触碰) -> 零回归。
- `calc_crack_spread` 仍是纯函数 (只收 df, 不开 DB)。

### 2.2 `config/crack_spread_pairs.py` - 新配置文件 (非高风险路径)

```python
"""跨品种 crack spread 品种配对配置 (Phase 8a)"""
from typing import Optional, Tuple

CRACK_SPREAD_PAIRS = {
    "ta": {"feedstock": "px", "ratio": 0.655},
    # Phase 8b 预留 (SC 采集就绪后):
    # "fu": {"feedstock": "sc", "ratio": ...},   # 需 bbl->吨换算
    # "bu": {"feedstock": "sc", "ratio": ...},
}

def get_crack_pair(symbol: str) -> Optional[Tuple[str, float]]:
    """返回 (feedstock_sym, ratio) 或 None"""
    cfg = CRACK_SPREAD_PAIRS.get(symbol.lower())
    if cfg is None:
        return None
    return (cfg["feedstock"], cfg["ratio"])
```
独立文件, 避免触碰 `prediction_scheme.py` (高风险路径, 仅允许加注释)。

### 2.3 `cascade/hourly_model.py` - DI 咽喉点 (启用重构: BacktestDataStore 下沉)

**所有三条路径 (生产 cascade_predict / scan / backtest) 都汇聚于 `hourly_model.predict()`**, 在此注入一次, 三路径同时覆盖。

咽喉点构建 `feedstock_cache`, 按 store 类型分支截止:
```python
# hourly_model.predict() 内, 构建协变量前:
feedstock_cache = None
if _needs_feedstock(covariate_type, covariate_types):      # 检测 crack_spread_*
    fs_sym, ratio = get_crack_pair(symbol)
    if fs_sym:
        feedstock_cache = {fs_sym: _fetch_feedstock_1h(fs_sym, store)}
# 传入 build_*(..., feedstock_cache=feedstock_cache)
```

**`_fetch_feedstock_1h(fs_sym, target_store, limit=480)` 截止分支:**
```python
def _fetch_feedstock_1h(fs_sym, target_store, limit=480):
    cutoff = getattr(target_store, "cutoff_date", None)
    if cutoff and cutoff != "9999-12-31":        # backtest 路径
        with BacktestDataStore(fs_sym, cutoff) as s:   # 复用截止语义
            return s.get_main_contract_1h(limit=limit) # 返回"截止前 480 根"
    else:                                         # production/scan 路径
        with DataStore(fs_sym) as s:
            return s.get_main_contract_1h(limit=limit) # 返回"最新 480 根"
```

**预热不足 warn**: 返回前检查 `len(df) < norm_window + horizon` (120+24=144)。backtest 早期评估点 (如 2023-10, PX 刚上市) feedstock 可能不足 144 根 -> 打印 warn, 协变量前段填 0 (rolling 预热期天然 NaN->0), 不阻断。

**启用重构: BacktestDataStore 下沉**
- 现状: `BacktestDataStore` 定义在 `scripts/backtest_1h.py:35-70`, 是 `DataStore` 子类。
- 问题: cascade (更低层) 需 import 它, 但 cascade 不能 import scripts (依赖方向反)。
- 修复: 将 `BacktestDataStore` **从 `scripts/backtest_1h.py` 下沉到 `data/data_store.py`** (它本属数据层)。
- **实施前先 grep 全部 import 点**: `grep -r "BacktestDataStore" --include="*.py"` 确认完整列表 (已知 `scripts/backtest_1h.py` + `scripts/monthly_backtest.py`, 可能含 `tests/test_backtest*.py`)。漏改一处即 ImportError。
- 更新所有 import 为 `from data.data_store import BacktestDataStore`。
- 零回归守卫: 仅改 import 路径, 类实现不变; 现有 backtest 流程/单测全跑一遍确认。

### 2.4 `scripts/covariate_scan.py` - Scan 注册 + effective n

`COVARIATE_TYPES` 追加 3 档:
```python
'crack_spread_slope', 'crack_spread_level', 'crack_spread_zscore',
```
scan 走 `hourly_model.predict` 同一咽喉点, DI 自动生效, 无需改 scan 主逻辑。scan 7pt 评估点都在 PX 覆盖窗口内 (2023-09 后), 无 underpowered 问题。

**effective_n 实现** (parse_results / backtest 报告阶段):
- feedstock 首根 bar 日期 (PX = 2023-09-15) 是 feedstock DB 的**固定属性**, parse_results 独立查询一次 (`DataStore('px').get_main_contract_1h(limit=1023)['dt'].min()`), 不经 per-call cache 流转。
- `effective_n = count(eval_point.cutoff_date >= feedstock_first_bar)`
- v2 Rule 5 判定用 effective_n (非 total n)。scan/backtest 报告同时列两者。
- scan 7pt 评估点都在 PX 覆盖窗口内 (2023-09 后), effective_n = total_n = 7; backtest walk-forward 覆盖 TA 全史, effective_n ≈ 178 < total_n。

---

## 3. 跨品种对齐与防穿越细则

| 风险 | 处理 |
|------|------|
| TA/PX 夜盘时间差 | df_main (TA) 时间轴 left-join, PX ffill |
| PX 早于首根 bar (2023-09 前) | spread=NaN -> 协变量填 0; backtest 这些点退化为基线等效 |
| backtest PX 未来泄露 | feedstock fetch 继承 `store.cutoff_date`, 复用 BacktestDataStore 截止语义 |
| ffill 连续超 4 根 (换月/停牌) | max_ffill_gap 守卫 -> spread NaN -> 协变量 0 |
| feedstock 无配对 (如 scan SS) | `get_crack_pair` 返回 None -> feedstock_df=None -> crack_spread 退化为零填充 + 警告 (scan 跳过该品种的 crack_spread 档) |

**有效 n 诚实报告**: backtest 走 TA 全史 (2016+), 但 crack_spread 仅在 PX 覆盖窗口 (2023-09+) 有信号。parse_results / backtest 报告**同时列 total n 与 effective n (feedstock 覆盖内)**, v2 Rule 5 判定用 effective n。

---

## 4. 测试验收

### 4.1 `tests/test_crack_spread.py` (新增)

- **公式正确性**: `spread = TA - 0.655·PX` (手算 fixture)
- **对齐**: TA 时间轴为主, left-join + ffill (PX 缺失 bar 用前值)
- **部分重叠不对齐**: TA 10 根 bar (含 3 根 PX 没有的夜盘 bar), PX 7 根。验证 left-join+ffill 后 3 根 TA bar 用的是 PX 最后已知值, spread 计算正确
- **ffill 间隙超限**: 连续 6 根 PX 缺失 (>max_ffill_gap=4) -> 这 6 根 spread=NaN -> 协变量=0
- **level 模式**: rolling ATR 归一化 + tanh + horizon 常数
- **slope 模式**: 回归斜率 (对 spread, 非 close) + rolling_std 归一化 + tanh + horizon 向 0 衰减
- **slope tanh 不饱和**: 构造大斜率 fixture, 验证 rolling_std 归一化后 tanh 输出未全压缩到 ±1
- **zscore 模式**: (x-mu)/sigma + tanh + horizon 向 0 衰减
- **PX 全缺 (早于首根)**: 协变量全 0, 不 crash
- **无配对品种**: feedstock_cache=None / get_crack_pair=None -> 零填充 + 不 crash
- **零回归**: 非 crack_spread 类型, `feedstock_cache=None`, 输出与现状字节级一致

### 4.2 Scan 冒烟
```bash
python -m unittest tests.test_crack_spread -v
python scripts/covariate_scan.py ta --points 3   # 3 档 crack_spread_* 进结果表
```

### 4.3 Backtest 三模式矩阵

三模式: baseline=bb_squeeze (TA 现固化) / replace=crack_spread_slope / additive=bb_squeeze+crack_spread_slope。

`monthly_backtest.py` 默认走 TA 现有 scheme (bb_squeeze), 跑 replace/additive 需**显式 covariate 覆盖**。**裁定: 用 CLI flag (`--covariate crack_spread_slope` / `--combo bb_squeeze,crack_spread_slope`), 不临时编辑 prediction_scheme.py** (与高风险路径保护一致, 避免 git diff 污染)。三模式各跑一次, 应用 v2 判据, 报告 effective n。

```bash
# 示意 (具体 CLI 由 plan 确定):
python scripts/monthly_backtest.py ta --covariate crack_spread_slope        # replace
python scripts/monthly_backtest.py ta --combo bb_squeeze,crack_spread_slope # additive
```

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| PX n≈178 underpowered | v2 Rule 5 自动标记; 诚实报告 effective n; Phase 8a 不固化 |
| TA/PX 会话差异致对齐偏差 | left-join + ffill; level 模式 long-cycle 归一化吸收绝对漂移 |
| 换月 ffill 失真 | max_ffill_gap=4 守卫, 超限置 NaN |
| ratio 0.655 近似误差 | 写入 config 可调; scan 可后续测 ratio 变体 (0.65/0.66) |
| tanh 饱和丢信息 | slope/zscore 统一 rolling_std 归一化后再 tanh |
| 框架通用性 | calc_crack_spread 参数化 (feedstock/product/ratio/mode); 8b SC-FU/BU 仅加 config 条目 |
| BacktestDataStore 下沉回归 | 仅改 import 路径, 类实现不变; 现有 backtest 单测守卫 |
| 高风险路径保护 | 新增 `config/crack_spread_pairs.py`, 不改 `prediction_scheme.py` |

---

## 6. 验收标准

- [ ] `tests/test_crack_spread.py` 全 PASS (含零回归 + 边界用例)
- [ ] `covariate_scan.py ta --points 3` exit 0, 3 档 crack_spread_* 进结果表
- [ ] scan 输出 3 档 MAE **合理性人工确认**: 若 crack_spread_slope MAE 显著劣于 random/基线 (如 >基线 1.5×), 需人工判定是 bug 还是"TA 上确无 PX-TA 信号" (两者都是有效结论, 但须确认非实现错误)
- [ ] 现有协变量 (bb_squeeze/ha_body/...) 单测不回归
- [ ] backtest 三模式矩阵跑通 (baseline=bb_squeeze / replace=crack_spread_slope / additive=bb_squeeze+crack_spread_slope), 应用 v2 判据
- [ ] 报告诚实列 effective n (~178) 与 underpowered 标记
- [ ] **Phase 8a 不固化** `prediction_scheme.py` -- 即使 scan MAE 优、backtest v2 PASS, 因 n<350 underpowered, 仅记录结论, 固化延后至 n≥350 或 Phase 8b

> 固化延后理由: 用户"参考但别重仓"原则 + 高风险路径保护 (不轻改 prediction_scheme.py)。框架与信号验证是 8a 的全部交付。

---

## 7. Phase 8b 展望 (本 spec 范围外, 框架须支持)

- **SC 原油采集**: config 加 SC (INE 上海国际能源交易中心), 采集脚本适配 (TqSdk 权限 / 合约映射 / 夜盘)
- **SC-FU/BU**: 复用 `calc_crack_spread`, config 加 `{"fu": {"feedstock": "sc", "ratio": ...}, "bu": {...}}`
- **单位换算**: bbl↔吨 (密度), SC 为 CNY/bbl、FU/BU 为 CNY/ton, 汇率敏感
- **会话对齐**: INE 夜盘 vs 内盘 1H 时间戳对齐
- **双线对比**: PX-TA vs SC-FU 信号相关性分析

---

## 8. 架构决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 标的 | PX-TA 先行, SC 后补 | 架构风险与数据风险解耦; PX 零采集风险 |
| 信号 | 三模式可配, 默认 slope | 数据裁决, 不押注单一经济解释; 抗过拟合 |
| 对齐 | TA 主表 left-join + ffill | TA 流动性好 bar 完整; PX 粘性强 ffill 误差小 |
| 防穿越 | feedstock 继承 cutoff_date | 跨品种回测最易踩的坑 |
| DI 注入点 | hourly_model.predict 咽喉点 | 三路径汇聚单点, 写一次覆盖全部 |
| 签名 | feedstock_cache 通用 context | 非 crack_spread 专属, 签名只膨胀一次, 未来跨品种协变量复用 |
| BacktestDataStore | 下沉到 data 层 | 解 cascade->scripts 层洁癖; 类实现不变 |
| 配置 | 独立 crack_spread_pairs.py | 不碰高风险 prediction_scheme.py |
| 固化 | 8a 不固化 | underpowered 诚实; 高风险路径保护 |

---

> **文档状态**: 设计完成, 待用户审核。审核通过后进入 `writing-plans` 生成实施计划。
