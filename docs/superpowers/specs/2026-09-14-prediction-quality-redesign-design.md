# 纯预测质量评估重构设计

> **日期**: 2026-09-14
> **状态**: 设计已批准，待实施
> **作者**: 用户 + Claude (architectural brainstorming)

---

## 1. 动机

当前评估系统以 PF (Profit Factor) 为主指标，通过假设性开仓/平仓/滑点来衡量协变量的「盈利能力」。这引入了大量与预测质量无关的假设参数（持有期、滑点量、信号权重），导致：

1. **协变量比较不公平**：PF 受品种价格量级影响，跨品种不可比
2. **信号稀释**：方向对但幅度小的协变量，PF 被滑点吃掉，判为差
3. **迭代慢**：完整回测 589 点 × 滑点计算 × MaxDD 追踪，计算量大
4. **目标错位**：PF 衡量的是交易系统的输出，不是预测模型的输出

**核心洞察**：协变量真正能控制的是预测质量（方向准不准、点位偏多少），而非 PF。先优化预测质量，再验证其经济价值。

---

## 2. 设计目标

- **预测为主**：DirAcc（方向准确率）和 MAPE（点位误差）成为主评估指标
- **交易为辅**：完全删除 PF/EV/MaxDD/WinRate 的计算
- **零额外开销**：新指标从现有逐点数据直接计算，不需要更多模型推理
- **向后兼容**：旧 checkpoint 数据可迁移为 v2 verdict，不需要重跑回测

---

## 3. 新指标体系

### 3.1 逐点指标

每个评估点输出的指标：

| 指标 | 定义 | 状态 |
|------|------|------|
| `dir_ok` | `sign(delta_pred) == sign(delta_real)`，`delta_real` 极小（`< 1e-8`）时判 `False`（保守原则，见 §3.5） | 已有，保留 |
| `dir12_ok` | T+12 方向准确率 | 已有，保留 |
| `mae` | `mean(abs(pred_path - real_path))` | 已有，保留 |
| `mape` | `mean(abs(pred_path - real_path) / max(abs(real_path), 1.0)) * 100`（v19 分母下限保护，见 §3.6） | 已有，保留 |
| `mae_h1` | 前半路径 MAE | 已有，保留 |
| `mae_h2` | 后半路径 MAE | 已有，保留 |
| `coverage` | 80% 分位区间覆盖率 | 已有，保留 |
| `real_range` | 真实路径极差 | 已有，保留 |
| `endpoint_mape` | `abs(pred_end - real_end) / max(base, 1.0) * 100`（全价 MAPE，分母下限保护，非增量 MAPE） | **新增** |
| `endpoint_bias_pct` | `(delta_pred - delta_real) / max(base, 1.0) * 100`（百分比偏差，跨品种可比） | **新增** |
| `path_corr` | `safe_path_corr(pred_path, real_path)`（含零方差保护，见 §3.3） | **新增** |
| ~~`pnl`~~ | ~~position_sign * delta_real - slip~~ | **删除** |

> **v3→v4 修正**: `weighted_dir_acc` 已从逐点指标表移至聚合指标表（§3.2）。
> 逐点只有单次预测和真实变动，不存在累加和，`weighted_dir_acc` 纯属于 verdict 级聚合指标。

### 3.3 数值安全（已修正审阅缺陷）

#### path_corr 零方差保护

当预测路径或真实路径的标准差接近零时（平坦预测 / 停牌窄幅），Pearson 相关系数的分母为零。必须使用安全版本：

```python
def safe_path_corr(pred_path, real_path, eps=1e-8):
    """Pearson 相关系数安全版本。
    防范 None、极短路径、NaN 及零方差。
    返回 float 或 None（输入无效时）。
    """
    if pred_path is None or real_path is None:
        return None
    p = np.asarray(pred_path, dtype=float).ravel()  # v21: .ravel() 防 (24,1) 二维切片
    r = np.asarray(real_path, dtype=float).ravel()
    if len(p) < 2 or len(r) < 2 or len(p) != len(r):
        return None
    if not (np.all(np.isfinite(p)) and np.all(np.isfinite(r))):
        return 0.0  # NaN/Inf 存在 → 视为不相关
    std_p, std_r = np.std(p), np.std(r)
    if std_p < eps or std_r < eps:
        return 0.0  # 平坦路径 → 视为不相关
    corr = np.corrcoef(p, r)[0, 1]
    return float(corr) if np.isfinite(corr) else 0.0
```

聚合时 `path_corr` 的 null 处理（v15 加固）：使用安全聚合，空列表返回 Python `None`（JSON `null`），而非 `np.nan`：
```python
valid_corrs = [c for c in corrs if c is not None and np.isfinite(c)]
agg_path_corr = float(np.mean(valid_corrs)) if len(valid_corrs) > 0 else None
```

#### endpoint_mape 分母下限保护

`base` 为基准价格（恒正），但仍需下限截断防止极端低价资产放大误差：

```python
endpoint_mape = abs(pred_end - real_end) / max(base, 1.0) * 100
```

> **语义说明**: 这是「全价 MAPE」（误差相对于基准价格的比例），而非「增量 MAPE」（误差相对于价格变动量的比例）。两者含义不同：全价 MAPE 衡量预测价格偏离基准的程度，增量 MAPE 衡量预测变动量偏离真实变动量的程度。本系统使用全价 MAPE 因为它在所有品种上量纲一致且不受 base=0 影响。

### 3.4 weighted_dir_acc 定义（幅度加权方向准确率）

单纯 DirAcc 对「猜对小幅震荡」和「猜对大幅趋势」等权处理，可能选出在横盘中频繁猜中但趋势突破时大幅误判的协变量。

```python
_denom = sum(abs(delta_real_i) for i in active_points)
if _denom < 1e-8:
    weighted_dir_acc = 0.5  # 无变动 → 回退到随机基线
else:
    weighted_dir_acc = sum(abs(delta_real_i) * dir_ok_i for i in active_points) / _denom
```

- 当 `delta_real = 0`（无变动）的点不参与计算
- 大幅变动时方向正确的权重更高
- **仅作为诊断参考**，不参与门控（避免引入交易语义）
- 当 `weighted_dir_acc >> dir_acc` 时，说明协变量在大幅行情中表现好
- 当 `weighted_dir_acc << dir_acc` 时，说明协变量只在小幅震荡中猜对

### 3.5 `dir_ok` 零变动保护（v18 新增）

当真实行情价格完全未发生变动（`delta_real == 0`，如停牌、涨跌停锁死）时，`sign(delta_real) = 0`，方向判定退化。采用保守原则：**真实无变动时不计为命中**，避免虚假方向一致：

```python
# 逐点 dir_ok 计算（向量化版本）
eps = 1e-8
delta_real = np.asarray(delta_real, dtype=float)
delta_pred = np.asarray(delta_pred, dtype=float)

dir_ok = np.where(
    np.abs(delta_real) < eps,
    False,  # 真实行情无变动 → 不计为命中（保守原则）
    np.sign(delta_pred) == np.sign(delta_real)
)
```

> **设计说明**: 停牌/涨跌停场景下，模型无法真正「预测方向」（无方向可预测）。
> 保守判定为 `False` 避免虚高 DirAcc，与 `weighted_dir_acc` 的分母零保护（§3.4）语义一致。

### 3.6 路径 `mape` 分母下限保护（v18→v19 加固）

路径 `mape` 计算中 `abs(real_path)` 可能极小（零价格、价差合约），导致 `inf`/`nan`。与 `endpoint_mape` 统一，分母加下限截断：

```python
# 路径 mape 安全计算
mape = np.mean(
    np.abs(pred_path - real_path) / np.maximum(np.abs(real_path), 1.0)
) * 100
```

> **设计说明**: 分母下限 `1.0` 与 `endpoint_mape` 保持一致。对于低价资产（如农产品 < 1 元/单位），
> MAPE 值会偏大但不溢出；对于正常价格资产（> 1），MAPE 精确反映百分比误差。

### 3.2 聚合指标（verdict 级别）

| 指标 | 定义 | 角色 |
|------|------|------|
| `dir_acc` | `mean(dir_ok)` over active points | **主门控 + 主排序** |
| `endpoint_mape` | `mean(endpoint_mape)` | 副门控（幅度约束） |
| `endpoint_bias_pct` | `mean((delta_pred - delta_real) / max(base, 1.0) * 100)` | 百分比偏差诊断 |
| `path_corr` | `mean(path_corr)`，跳过 null 点 | 路径形状诊断，`float | null` |
| `weighted_dir_acc` | `sum(abs(delta_real) * dir_ok) / sum(abs(delta_real))` | 幅度加权方向诊断（仅观察，不参与门控） |
| `mae` | `mean(mae)` | 辅助 |
| `mape` | `mean(mape)` | 辅助 |
| `decay` | `mae_h2 / max(mae_h1, 1e-6)` | 诊断 |
| `n` | 有效评估点数 | 门控 |
| `n_eff` | Bartlett 有效样本量 | 门控 |
| ~~`PF`~~ | -- | **删除** |
| ~~`EV`~~ | -- | **删除** |
| ~~`MaxDD`~~ | -- | **删除** |
| ~~`WinRate`~~ | -- | **删除** |
| ~~`EV_ratio`~~ | -- | **删除** |

---

## 4. Gate 条件

### 4.1 新硬门（已修正审阅缺陷）

```python
def gate(s, min_n=350, min_n_eff=50, min_dir_acc=0.52,
         baseline_dir_acc=None):
    """纯预测质量硬门:
      - n >= 350: 名义样本量充分性
      - n_eff >= 50: 有效独立样本量充分性（Bartlett 校正后）
      - DirAcc >= effective_min: 品种自适应门槛（baseline 高时保持 0.52，baseline 低时放宽）
    注意: 不使用 abs()。dir_acc < 0.5 的变体（反向预测）直接拒绝。
    品种自适应: baseline 偏低时向下放宽（如 cf=0.51），
    baseline 偏高时仍保持 0.52 质量底线（不会反向加压）。

    **v14→v15 前置约束**: 调用 gate() 前，Supervisor 必须确保 baseline_metrics.json
    已加载且该品种条目存在。冷启动时由 Supervisor 在慢环启动前集中执行基线初始化
    （见 §9.4 基线预检协议），禁止在 gate() 内部触发基线生成。
    """
    # v23 修正: 根级字段完全 Null 安全（防残缺字典 TypeError）
    n = 0 if s.get("n") is None else int(s["n"])
    n_eff = 0 if s.get("n_eff") is None else int(s["n_eff"])
    dir_acc = 0.0 if s.get("dir_acc") is None else float(s["dir_acc"])
    # 品种自适应: max(0.50 随机底线, min(0.52 全局底线, baseline))
    # baseline 高 → min(0.52, 0.55) = 0.52 → max(0.50, 0.52) = 0.52 (不加压)
    # baseline 低 → min(0.52, 0.51) = 0.51 → max(0.50, 0.51) = 0.51 (放宽)
    if baseline_dir_acc is not None:
        effective_min = max(0.50, min(min_dir_acc, baseline_dir_acc))
    else:
        effective_min = min_dir_acc
    return (n >= min_n and n_eff >= min_n_eff and dir_acc >= effective_min)
```

> **v1→v2 修正说明**: 旧版使用 `ic = 2 * abs(dir_acc - 0.5)` 允许 dir_acc=0.40 的反向变体
> 以 IC=0.20 通过门控。新版改为单侧约束 `dir_acc >= 0.52`，彻底消除反向泄漏。

### 4.2 统计检验（v4 根本性修正：配对增量检验 + Benjamini-Hochberg FDR）

> **v3→v4 致命缺陷修正**: v3 的二项检验在 $n_{eff}=71$ 下标准误 $SE = 0.5/\sqrt{71} \approx 0.059$，
> 要求 DirAcc > 0.598 才能通过 $\alpha=0.05$ 的单侧检验。叠加 Bonferroni（$K=20$）后要求
> DirAcc > 0.667。在金融时序中 T+24 方向准确率达到 0.55~0.57 已是极强信号，此方案会导致
> **所有变体零晋级，系统死锁**。v4 彻底替换检验策略。

#### 4.2.1 静态门控（质量底线，非统计检验）

`gate()` 中的 `dir_acc >= 0.52` 是**质量底线**而非统计检验——仅过滤方向准确率低于随机的明显无效变体。不做统计显著性判断。

#### 4.2.2 统计检验：Diebold-Mariano 检验 + Newey-West HAC（慢环逐变体）

**核心思路**：变体与 Baseline 面对完全相同的评估时间点，逐点命中差构成配对样本。
DM 检验利用 Newey-West HAC 估计量校正重叠窗口自相关，**保留全量 588 点**，不丢弃数据。

> **v5→v6 致命修正**: v5/v6 的非重叠步长抽样将 588→49 点，McNemar 功效崩塌
> （变体需超额 16% 才显著，死锁重现）。v7 替换为 Diebold-Mariano 检验，
> 全样本利用 + HAC 方差估计，是时间序列预测对比的计量经济学黄金标准。

**零假设** $H_0$: 变体的 DirAcc 不优于 Baseline（即 $\bar{d} \leq 0$）

**逐点损失差**: $d_t = v\_ok_t - b\_ok_t \in \{-1, 0, 1\}$，$\bar{d} = DirAcc_v - DirAcc_b$

```python
import numpy as np
from scipy.stats import t as student_t

def diebold_mariano_p(variant_dir_ok_list, baseline_dir_ok_list,
                      horizon=24, step=2):
    """Diebold-Mariano 检验 + Newey-West HAC + HLN 有限样本校正。

    保留全量 T 个评估点，不丢弃数据。
    Newey-West HAC 自动校正预测窗口重叠导致的自相关。

    输入: 两个等长的 bool/0-1 列表（变体 vs baseline 的逐点方向正确性）
    输出: 单侧 p 值
    """
    v = np.asarray(variant_dir_ok_list, dtype=float)
    b = np.asarray(baseline_dir_ok_list, dtype=float)
    T = len(v)
    # 防卫性拦截: 长度不等或样本不足（与 §9.4 配对阈值统一为 100）
    if len(v) != len(b) or T < 100:
        return 1.0  # 样本不足

    # 逐点损失差
    d = v - b
    d_bar = np.mean(d)

    if d_bar <= 0:
        return 1.0  # 变体没有净改善

    # Newey-West HAC 方差估计
    # 滞后阶数 q = horizon // step - 1 (重叠窗口自相关长度)
    q = max(1, horizon // step - 1)
    gamma = np.zeros(q + 1)
    for j in range(q + 1):
        # 除以全长 T（非 T-j），保障 Bartlett 核半正定性
        gamma[j] = np.sum((d[j:] - d_bar) * (d[:T-j] - d_bar)) / T

    # Bartlett 核加权
    V = gamma[0]
    for j in range(1, q + 1):
        V += 2 * (1 - j / (q + 1)) * gamma[j]
    V /= T

    # 零方差防御: 数值退化视为无统计信息，保守返回 1.0（杜绝伪显著性 p=0.0）
    if V <= 1e-12:
        return 1.0

    # DM 统计量
    dm = d_bar / np.sqrt(V)

    # HLN 校正: 根号内增加非负下限保护（防止浮点下溢导致 NaN）
    h = horizon // step
    hln_inner = max(1e-6, (T + 1 - 2 * h + h * (h - 1) / T) / T)
    k_hln = np.sqrt(hln_inner)
    dm_adj = dm * k_hln

    # 单侧 p 值（v15: 使用生存函数 sf 避免浮点下溢，精确到 10^-300）
    p_value = float(student_t.sf(dm_adj, df=T - 1))
    return float(np.clip(p_value, 0.0, 1.0))
```

**功效分析**（全量 588 点 vs 下采样 49 点）：
- Baseline DirAcc=0.50, 变体 DirAcc=0.55: $\bar{d}=0.05$
- 588 点中约 100 个不一致点，其中 ~75 为变体改善
- DM 统计量约 2.0~2.5（HAC 校正后），单侧 p 约 0.01~0.02
- 可通过 BH-FDR（$q=0.10$）的阈值
- 对比下采样 49 点 McNemar（p≈0.30，完全无效）——DM 保留全量 588 点

**优势总结**:
1. **全样本利用**: 588 点全部参与，无信息损失
2. **HAC 消除自相关**: Newey-West 以 Bartlett 核加权 $q=11$ 阶滞后，严格处理 T+24 重叠
3. **HLN 小样本校正**: 有限样本校正因子避免过拟合
4. **功效合理**: DirAcc 提升 3~5% 即可显著，不会死锁

#### 4.2.3 多重检验校正：Benjamini-Hochberg FDR（Supervisor 批次结算）

Bonferroni 控制全族错误率（FWER），过于保守。对于协变量探索这类**发现优先**的场景，采用 Benjamini-Hochberg 控制假发现率（FDR）更为合适：

```python
def bh_fdr_promote(verdicts, fdr_q=0.10, min_batch_size=4, bonferroni_alpha=0.025):
    """按品种独立分组执行 Benjamini-Hochberg FDR 校正（含小批次 Bonferroni 降级）。

    **v12→v13 关键修正**: 不同品种信噪比差异巨大，混合排序会系统性绞杀低信噪比品种。
    按品种分组独立执行 FDR，保证每个品种有独立晋级通道。

    **v19→v20 落地修正**: 小批次约束从 docstring 伪代码提升为函数体正式逻辑。
    K < min_batch_size 时降级为固定 Bonferroni 阈值，防止 K=1 时 FDR 退化为无校正。
    """
    from collections import defaultdict
    if not verdicts:
        return {}

    # 按品种分组，并按 variant_id 去重（防止批次内重试产生重复行）
    symbol_groups = defaultdict(dict)
    for v in verdicts:
        sym = v.get("symbol", "default")
        vid = v.get("variant_id")
        if vid:
            symbol_groups[sym][vid] = v

    all_updates = {}

    for sym, sym_dict in symbol_groups.items():
        sym_verdicts = list(sym_dict.values())
        k_total = len(sym_verdicts)
        gate_pass_ids = {v["variant_id"] for v in sym_verdicts if v.get("gate_pass")}

        def safe_p(v):
            if v["variant_id"] not in gate_pass_ids:
                return 1.0
            p = v.get("p_value")
            return 1.0 if p is None else float(p)

        if k_total < min_batch_size:
            # v20 落地: 小批次降级 — 固定 Bonferroni 阈值
            for v in sym_verdicts:
                vid = v["variant_id"]
                is_pass = (safe_p(v) <= bonferroni_alpha) if vid in gate_pass_ids else False
                v["fdr_pass"] = is_pass
                all_updates[vid] = {"fdr_pass": is_pass}
        else:
            # 正常 BH-FDR 流程
            sorted_vs = sorted(sym_verdicts, key=lambda v: (safe_p(v), v["variant_id"]))
            # v18: variant_id 二级排序键保证幂等

            # 寻找最大截断点 k*
            max_k_star = 0
            for rank, v in enumerate(sorted_vs, 1):
                threshold = fdr_q * rank / k_total
                if safe_p(v) <= threshold:
                    max_k_star = rank

            # 生成更新字典
            for rank, v in enumerate(sorted_vs, 1):
                vid = v["variant_id"]
                is_pass = (rank <= max_k_star) if vid in gate_pass_ids else False
                v["fdr_pass"] = is_pass
                all_updates[vid] = {"fdr_pass": is_pass}

    return all_updates
```

> **v4→v5 致命修正**: 旧版逐点独立判定 `v["p_value"] <= threshold` 违反 BH 单调性。
> 例如 Rank 2 的 p=0.011 > 阈值 0.010（False），但 Rank 3 的 p=0.012 <= 阈值 0.015（True），
> 导致「更显著的变体被淘汰，更弱的反而通过」。修正为标准截断点逻辑。

**数值示例**（$K=20$, $n_{eff}=71$, FDR $q=0.10$）:
- 排名 1（最小 p）: 阈值 = 0.10 × 1/20 = 0.005
- 排名 5: 阈值 = 0.10 × 5/20 = 0.025
- 排名 10: 阈值 = 0.10 × 10/20 = 0.050
- 排名 20（最大 p）: 阈值 = 0.10 × 20/20 = 0.100

对比 Bonferroni（全部要求 $p < 0.0025$），FDR 允许排名靠前的变体以宽松得多的阈值通过。

#### 4.2.4 职责分离与持久化

```
慢环（逐变体）                          Supervisor（批次结算）
────────────                          ──────────────────
1. 跑 walk-forward                     5. 收集本轮批次全部变体（batch_verdicts）
2. 逐点记录 dir_ok                     6. 按 batch_id 筛选本轮变体
3. 计算 dir_acc, n_eff                 7. updates = bh_fdr_promote(batch_verdicts)
4. 调用 diebold_mariano_p vs baseline   8. update_batch_verdicts(path, batch_id, updates)
5. 写入 verdict (p_value, fdr_pass=null)  → 原子覆写文件，持久化 fdr_pass
6. gate_pass 基于静态条件
```

**持久化回写**: 统一使用 `registry_lib.update_batch_verdicts()`（见 §8.5），
该函数内含排他锁 + 容错读取 + 原子替换，不在此处重复定义。

### 4.3 变化说明

- 旧门：`n >= 350 AND IC >= 0.05`（IC=0.05 对应 DirAcc>=0.525）
- 新门：`n >= 350 AND n_eff >= 50 AND DirAcc >= 0.52`（静态质量底线）+ Diebold-Mariano 检验 + BH-FDR 批次校正
- 不再需要 PF ratio > 1.05 或 EV > 0
- `min_dir_acc=0.52` 是质量底线（过滤明显无效变体），统计显著性由 DM 检验 + FDR 判定

---

## 5. 成功条件 (praxist_goal.yaml)

### 旧

```yaml
success_condition:
  - "len(symbols_hit & {1-star set}) >= 4"
  - "min(pass_variant_pf_ratios) > 1.05"
  - "len(families_hit) >= 1"
```

### 新

```yaml
success_condition:
  - "n_one_star_symbols_hit >= 4"
  - "n_unique_pass_variants >= 4"
  - "n_families_hit >= 1"
```

> **v14→v15 修正**: `all(v.fdr_pass and v.gate_pass)` 在 FDR 淘汰变体时自毁。改为数量检查。
> **v15→v16 修正**: 恢复品种集合约束，防止单品种 4 个微调变体即假达标。
> **v16→v17 修正**: `{1-star set}` 在 Python `eval()` 中为非法语法（连字符+空格），直接 `SyntaxError`。
> 改为 Supervisor 预计算标量变量，YAML 仅做原子级数值比较，消除运行时崩溃风险。
>
> **`pass_variants` 与派生标量变量的明确定义**（在 Supervisor 中固化）:
> ```python
> pass_variants = [
>     v for v in all_verdicts
>     if v.get("gate_pass") and (v.get("fdr_pass") or v.get("migrated_pass"))
> ]
> symbols_hit = {v["symbol"] for v in pass_variants}
> # v19 修正: 显式排除 "unknown"，防止非空字符串 truthy 导致假达标
> families_hit = {
>     v["cov_family"] for v in pass_variants
>     if v.get("cov_family") and v["cov_family"] != "unknown"
> }
> # ---- v17 新增: 预计算标量，供 YAML success_condition 原子比较 ----
> n_one_star_symbols_hit = len(symbols_hit & ONE_STAR_SYMBOLS_SET)
> n_unique_pass_variants = len({v["variant_id"] for v in pass_variants})
> # v20 新增: families_hit 也预计算为标量，YAML 彻底退化为纯数值比较
> n_families_hit = len(families_hit)
> ```
> 成功条件按 `variant_id` 去重，防止同变体重试多次导致假达标。
> `ONE_STAR_SYMBOLS_SET` 为 Supervisor 启动时从配置加载的 1★ 品种集合常量。

---

## 6. 任务配置 (praxist_task.yaml)

### 旧

```yaml
objective:
  primary: ev_after_slippage
  secondary: profit_factor
```

### 新

```yaml
objective:
  primary: dir_acc
  direction: maximize
  aux_metrics:
  - endpoint_mape
  - endpoint_bias_pct
  - path_corr
  - mape
  - n
  - n_eff
  - gate_pass

constraints:
  min_samples: 350
  min_n_eff: 50
  min_dir_acc: 0.52
  multiple_comparison: bh_fdr  # 可执行：Diebold-Mariano + Newey-West HAC + Benjamini-Hochberg FDR (q=0.10)
```

---

## 7. Verdict Schema v2

```json
{
  "schema": "fm.aligned_verdict.v2",
  "variant_id": "p_calendar_cyclical",
  "symbol": "p",
  "cov_override": "calendar_cyclical",
  "status": "ok",
  "stage": "aligned",
  "n": 588,
  "n_eff": 71,
  "dir_acc": 0.563,
  "endpoint_mape": 0.35,
  "endpoint_bias_pct": 0.15,
  "path_corr": 0.72,
  "weighted_dir_acc": 0.571,
  "mae": 45.2,
  "mape": 0.38,
  "decay": 1.15,
  "p_value": 0.037,
  "gate_pass": true,
  "fdr_pass": null,
  "migrated_pass": null,
  "batch_id": "gen_20260914_001",
  "metrics": {
    "dir_acc": 0.563,
    "endpoint_mape": 0.35,
    "endpoint_bias_pct": 0.15,
    "path_corr": 0.72,
    "weighted_dir_acc": 0.571,
    "n": 588,
    "n_eff": 71,
    "p_value": 0.037,
    "gate_pass": true,
    "fdr_pass": null,
    "migrated_pass": null,
    "batch_id": "gen_20260914_001"
  },
  "checkpoint_path": "...",
  "slow_loop_pid": 1234,
  "git_rev": "abc123",
  "decided_at": "2026-09-14T..."
}
```

### 7.1 Schema 类型约束（已修正审阅缺陷）

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `dir_acc` | `float` | 否 | 0.0~1.0 |
| `endpoint_mape` | `float` | 否 | >= 0.0 |
| `endpoint_bias_pct` | `float` | 否 | 百分比偏差 |
| `path_corr` | `float` | **是** | 旧数据迁移时可能为 null；聚合时跳过 null |
| `weighted_dir_acc` | `float` | 否 | 0.0~1.0 |
| `mae` | `float` | **是** | 路径 MAE（仅路径模式有值，端点模式为 null） |
| `mape` | `float` | **是** | 路径 MAPE（分母下限保护，仅路径模式有值） |
| `decay` | `float` | **是** | `mae_h2 / max(mae_h1, 1e-6)`，路径前后半段衰减比 |
| `n` | `int` | 否 | 有效评估点数 |
| `n_eff` | `int` | 否 | Bartlett 有效样本量 |
| `p_value` | `float` | **是** | 0.0~1.0；Diebold-Mariano 名义单侧 p 值（慢环写入）；迁移记录为 null |
| `fdr_pass` | `bool` | **是** | null=待 Supervisor 批次结算后填写；true/false=已裁定 |
| `migrated_pass` | `bool` | **是** | 标记是否为旧版数据迁移放行；新变体为 null 或 false |
| `batch_id` | `str` | 否 | 批次标识（如 "gen_20260914_001"），Supervisor 用于界定本轮变体集合 $K$ |
| `cov_family` | `str` | **否** | 协变量所属族类（受控词表，见下方），用于 `families_hit` 统计。**v17 起必填非空**，解析来源与枚举见 §7.2 |
| `gate_pass` | `bool` | 否 | 静态硬门结果（n, n_eff, dir_acc） |

### 7.2 `cov_family` 受控词表与解析来源（v17 新增）

`cov_family` 的取值限定为以下 6 个标准族类（受控词表），确保 `families_hit` 统计的一致性：

| 族类 | 含义 | 典型协变量 |
|------|------|-----------|
| `momentum` | 动量/趋势延续类 | ROC、EMA 交叉、RSI |
| `volatility` | 波动率/风险类 | ATR、Bollinger、realized vol |
| `inventory` | 库存/供需类 | 仓单、库存变化、产能利用率 |
| `calendar` | 日历/季节性类 | 月份虚拟变量、节假日、交割日历 |
| `term_structure` | 期限结构类 | 近远月价差、Back/Contango 斜率 |
| `macro_sentiment` | 宏观/情绪类 | VIX、美元指数、利率预期 |

**解析来源优先级**（慢环写入 verdict 时执行）:
1. **协变量池映射**（首选）: 若变体来自 `covariate_pool.json`，直接提取其预定义的 `family` 属性；
2. **Peer 结构化输出**: 若变体由 Peer 原创提出，Peer 必须在其 JSON 方案中显式包含 `cov_family` 字段，且值必须在上述受控词表中；
3. **兜底**: 若两处均缺失，`cov_family = "unknown"`（`"unknown"` 不纳入 `families_hit` 统计）。

> **v17 修正**: v16 中 `cov_family` 声明为 Schema 必填但无解析来源契约，
> Peer Prompt 也未规定标准枚举，导致 `families_hit` 统计口径不一致。
> v17 固化受控词表 + 双源解析优先级，消除歧义。

> **v3→v4 修正说明**:
> 1. `bonferroni_p` 拆为 `p_value`（DM 名义 p 值）+ `fdr_pass`（BH-FDR 校正后是否晋级），消除字段语义歧义。
> 2. 新增 `batch_id` 字段，Supervisor 用于严格界定批次边界，防止跨轮次变体混合计算 FDR。
> 3. `path_corr` 的可空性显式声明为 `float | null`，聚合时 `np.nanmean()` 跳过 null 点。
> 4. `p_value` 统计方法更新：v6 使用 McNemar（下采样后 ~49 点），v7 替换为 Diebold-Mariano（全量 588 点 + Newey-West HAC），解决下采样功效崩塌问题。

---

## 8. 代码改动清单

### 8.1 cascade/evaluation_metrics.py

**删除**:
- `calc_net_metrics()` -- PF/EV/MaxDD/WinRate 计算核心
- `metrics_from_backtest_points()` -- 从 point 列表计算交易指标
- `compare_strategies()` -- 动态 vs 静态策略对比
- `print_metrics_comparison()` -- 对比打印
- `calc_margin_maxdd_robust()` -- 保证金 MaxDD

**保留**:
- `calc_vol_scaled_mae()` -- 波动率缩放 MAE（诊断用）

**新增**:
```python
def calc_prediction_quality(
    pred_endpoints, real_endpoints, base_prices,
    pred_paths=None, real_paths=None,
) -> dict:
    """纯预测质量指标。仅计算原始指标，不做统计检验。
    当 pred_paths=None 时（仅端点模式），返回字典中:
      path_corr=None, mae=None, mape=None, decay=None（聚合时按 null 处理）
    当 pred_paths 存在时，完整计算所有指标。
    Returns: dir_acc, endpoint_mape, endpoint_bias_pct, path_corr,
             weighted_dir_acc, mae, mape, decay, n
    注意: p_value 由 evaluator.py 通过 diebold_mariano_p() 计算，不在此函数。
    """
    # v17 新增: 入口强转 numpy array，防止上游传入原生 list 导致向量减法 TypeError
    p_end = np.asarray(pred_endpoints, dtype=float)
    r_end = np.asarray(real_endpoints, dtype=float)
    base = np.maximum(np.asarray(base_prices, dtype=float), 1.0)  # 分母下限保护
    if pred_paths is not None and real_paths is not None:
        p_paths = np.asarray(pred_paths, dtype=float)
        r_paths = np.asarray(real_paths, dtype=float)
        # v18 新增: 路径 mape 分母下限保护（与 endpoint_mape 统一）
        # mape = np.mean(np.abs(p_paths - r_paths) / np.maximum(np.abs(r_paths), 1.0)) * 100
        # v19 新增: decay 计算（前半/后半路径 MAE 比值）
        mid = p_paths.shape[-1] // 2 if p_paths.ndim > 1 else len(p_paths) // 2
        mae_h1 = np.mean(np.abs(p_paths[..., :mid] - r_paths[..., :mid]))
        mae_h2 = np.mean(np.abs(p_paths[..., mid:] - r_paths[..., mid:]))
        decay = float(mae_h2 / max(mae_h1, 1e-6))
    else:
        decay = None
    # ... 后续计算使用 p_end, r_end, base, p_paths, r_paths, decay ...

def safe_path_corr(pred_path, real_path, eps=1e-8):
    """Pearson 相关系数安全版本。
    None → None, 长度<2 → None, NaN → 0.0, 零方差 → 0.0。
    """
```

### 8.2 scripts/monthly_backtest.py

**改动**:
- `run_symbol_backtest()`: 删除 `pnl` 计算，新增 `endpoint_mape`/`endpoint_bias_pct`/`path_corr` 逐点计算
- **v21 新增: 逐点 `dir_ok` 同步更新**: 强制套用 §3.5 零变动保护（`abs(delta_real) < 1e-8` 判 `False`），确保 `point_dir_ok_list`（透传 DM 检验）与 `dir_acc`（静态 Gate）使用一致的判定逻辑，防止两者数值脱节
- `summarize()`: 替换 `metrics_from_backtest_points()` 为 `calc_prediction_quality()`
- **返回值新增 `point_dir_ok_list`**: 逐点 `(cutoff, dir_ok)` 列表，**作为字典键挂载**（非 Tuple 返回值，保持向后兼容）：`summary["point_dir_ok_list"] = [...]`
- `classify()`: 保留，去除 EV 相关分类逻辑

> **v5→v6 数据链路修正**: `summarize()` 的返回值不再仅是标量字典，
> 同时携带逐点明细序列，确保 evaluator 能获取配对检验所需的数据。

### 8.3 task_FM/evaluations/fm_eval/evaluator.py

**改动**:
- `gate()`: 改为单侧 `dir_acc >= effective_min`（不使用 abs），新增 `n_eff >= 50` 硬门
- **自适应 baseline 透传**: `build_summary()` 从 `task_FM/config/baseline_metrics.json` 读取该品种的 `baseline_dir_acc`，传入 `gate(s, baseline_dir_acc=...)`
- `map_summary()`: 输出 `dir_acc`/`endpoint_mape`/`endpoint_bias_pct`/`path_corr`/`weighted_dir_acc` 替代 `pf`/`ev`/`maxdd`
- `build_summary()`:
  - schema 升级为 `fm.aligned_verdict.v2`，`path_corr` 和 `p_value` 声明为 `float | null`
  - 新增 `p_value` 字段：接收 `point_dir_ok_list`（由 `summarize()` 透传），加载 baseline 逐点数据，按归一化时间戳 Inner Join 对齐后调用 `diebold_mariano_p()`。**冷启动防御**: 若 `baseline_points_{symbol}.jsonl` 不存在，记录 warning 并设 `p_value = None`。**数据生命周期**: `point_dir_ok_list` 仅驻留内存，DM 检验完成后必须 `summary.pop("point_dir_ok_list", None)`，**禁止持久化到 verdict JSONL**（防止单条 verdict 从 1KB 膨胀至 50KB）。
  - **v19 新增: `point_dir_ok_list` 类型对齐与 DM 输入解构**: `summarize()` 返回的 `point_dir_ok_list` 为 `[(cutoff_str, dir_ok_bool), ...]` 元组列表。evaluator 在调用 DM 检验前，必须先做时间戳归一化 + Inner Join + 排序，然后**解构提取纯 bool 序列**传入 `diebold_mariano_p()`：
    ```python
    # evaluator.py 内部配对与解构实现
    variant_points = summary["point_dir_ok_list"]  # [(cutoff_str, dir_ok), ...]
    baseline_points = load_baseline_points(symbol)  # [(cutoff_str, dir_ok), ...]

    # 1. 归一化时间戳
    # v22 修正: normalize_points 兼容 tuple 列表（内存中）和 dict 列表（JSONL 反序列化）
    def normalize_points(pts):
        res = {}
        for item in pts:
            if isinstance(item, dict):
                c, d = item.get("cutoff"), item.get("dir_ok")
            else:
                c, d = item[0], item[1]
            norm_c = safe_normalize_cutoff(c)
            if norm_c is not None and d is not None:
                res[norm_c] = int(d)
        return res

    v_map = normalize_points(variant_points)
    b_map = normalize_points(baseline_points)

    # 2. Inner Join（仅保留双方都有的时间点）
    common_ts = sorted(set(v_map.keys()) & set(b_map.keys()) - {None})
    paired_v = [v_map[ts] for ts in common_ts]  # 纯 int(0/1) 序列
    paired_b = [b_map[ts] for ts in common_ts]  # 纯 int(0/1) 序列

    # 3. 传入 DM 检验（纯数值序列，无字符串）
    if len(common_ts) >= 100:
        p_val = diebold_mariano_p(paired_v, paired_b)
    else:
        p_val = None
    ```
  - 新增 `batch_id` 字段（从当前运行上下文获取）
  - `fdr_pass` 初始化为 `null`

### 8.4 scripts/aligned_slow_loop.py

**改动**:
- `_no_data_verdict()`: schema 升级为 v2，删除 PF/EV/MaxDD 字段
- `run_aligned_candidate()`:
  - 删除 `_net_pnl_pts()` 和 `calc_margin_maxdd_robust()` 调用
  - `p_value` 由 `evaluator.build_summary()` 内部计算（调用 `diebold_mariano_p`），慢环不直接计算
  - `fdr_pass` 初始化为 `null`（待 Supervisor 批次结算）
  - `batch_id` 从运行上下文传入
- 删除 `from cascade.evaluation_metrics import calc_margin_maxdd_robust`
- **v17 新增: 全局墓碑记录（Tombstone Record）**: `run_aligned_candidate()` 最外层包裹 `try/except`，即使回测因 OOM / 未捕获异常 / 硬件中断而崩溃，也必须向 `aligned_verdicts.jsonl` 写入一条带有当前 `batch_id`、`status: "error"`、`gate_pass: False`、`p_value: 1.0` 的失败 verdict，确保变体数量守恒，Supervisor 批次结算不会无限挂死等待。
- **v21 CPU 适配: 线程数压制（防 CPU 核心踩踏）**: 慢环进程入口处必须显式限制 OpenMP/MKL/PyTorch 线程数，防止多进程并发时线程争抢导致上下文切换开销远超计算收益：
  ```python
  # scripts/aligned_slow_loop.py 最顶端（v22 修正: 必须在所有 import 之前！）
  # OpenMP/MKL 在 import torch/numpy 时就已完成线程池初始化
  # import 之后再设 os.environ 完全无效
  import os
  os.environ["OMP_NUM_THREADS"] = "4"
  os.environ["MKL_NUM_THREADS"] = "4"

  import torch
  import numpy as np
  torch.set_num_threads(4)
  ```
  > **CPU 运行契约**: 本系统定位为 **纯 CPU 环境**，慢环 Worker 建议采用 **严格串行调度**（1 个跑完再跑下一个），让单个 Worker 充分打满单机 CPU 核心。若必须并发，每 Worker 线程数 = `总核数 // Worker数`。：
  ```python
  def make_error_tombstone(symbol, variant_id, batch_id, exc, cov_family="unknown"):
      """构造与 Schema v2 完全对齐的崩溃墓碑记录。
      包含 schema/stage/metrics 子字典，确保下游 update_batch_verdicts
      的 metrics 同步更新逻辑不会触发 KeyError。
      """
      return {
          "schema": "fm.aligned_verdict.v2",
          "variant_id": variant_id,
          "symbol": symbol,
          "batch_id": batch_id,
          "stage": "aligned",
          "status": "error",
          "error_message": str(exc)[:500],
          "gate_pass": False,
          "p_value": 1.0,           # 保守: 崩溃 → 视为不显著
          "fdr_pass": False,
          "migrated_pass": False,
          "cov_family": cov_family,
          "dir_acc": 0.0,
          "endpoint_mape": None,
          "endpoint_bias_pct": None,
          "path_corr": None,
          "weighted_dir_acc": 0.0,
          "mae": None,
          "mape": None,
          "decay": None,
          "n": 0,
          "n_eff": 0,
          "metrics": {               # v19 补齐: 与 Schema v2 根节点严格对齐
              "dir_acc": 0.0,
              "endpoint_mape": None,
              "endpoint_bias_pct": None,
              "path_corr": None,
              "weighted_dir_acc": 0.0,
              "mae": None,
              "mape": None,
              "decay": None,
              "n": 0,
              "n_eff": 0,
              "p_value": 1.0,
              "gate_pass": False,
              "fdr_pass": False,
              "migrated_pass": False,
              "batch_id": batch_id,
          },
      }

  def run_aligned_candidate(symbol, variant, batch_id, ...):
      try:
          # ... 正常回测流程 ...
          verdict = build_summary(...)
          append_verdict(verdicts_path, verdict)
      except Exception as exc:
          logger.error(f"Slow loop crash for {symbol}/{variant['variant_id']}: {exc}")
          tombstone = make_error_tombstone(
              symbol=symbol,
              variant_id=variant["variant_id"],
              batch_id=batch_id,
              exc=exc,
              cov_family=variant.get("cov_family", "unknown"),
          )
          append_verdict(verdicts_path, tombstone)
  ```

### 8.5 scripts/registry_lib.py

**改动**:
- `append_verdict()`: 适配 v2 字段
- 过滤逻辑：`v.get("ev", 0) > 0` 删除
- 加载逻辑：仅读取单一 `aligned_verdicts.jsonl`（v2 schema），不再有 v1 兼容
- 所有读取路径假设 `dir_acc`/`endpoint_mape`/`p_value` 存在（v2 保证）
- **新增 `update_batch_verdicts()`**: 带排他文件锁 + **原子替换**（写入 `.tmp` → `os.replace`），避免 `truncate()` 在进程中断时导致数据全量清空。`append_verdict()` 入参为文件路径（非句柄），内部自闭环管理锁：

```python
import fcntl
import json
import logging
import os

logger = logging.getLogger(__name__)

def _read_records_unlocked(verdicts_path):
    """内部无锁读取，供已持有排他锁的上下文安全复用。
    逐行 JSON 容错：坏行记录 warning 并跳过。
    严禁在已持锁上下文外直接调用（无锁保护）。
    """
    if not os.path.exists(verdicts_path):
        return []
    records = []
    with open(verdicts_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            raw = line.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as err:
                logger.error(f"Malformed JSON line {line_no} in {verdicts_path}: {err}")
    return records

def read_verdicts(verdicts_path):
    """对外只读接口：带共享锁 + 逐行 JSON 容错。
    首次运行时文件不存在 → 返回空列表。
    """
    lock_path = verdicts_path + ".lock"
    with open(lock_path, "a") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_SH)
        try:
            return _read_records_unlocked(verdicts_path)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

def append_verdict(verdicts_path, verdict):
    """追加 verdict：统一锁定 .lock 专用锁文件（排他锁）。
    v19 新增: 防重写入 — 若同 batch_id+variant_id 已存在墓碑记录，拒绝写入。
    v19 新增: 自动创建目录 + 进程级唯一临时文件名（防竞争）。
    """
    # v19: 确保目录存在
    os.makedirs(os.path.dirname(os.path.abspath(verdicts_path)), exist_ok=True)
    lock_path = verdicts_path + ".lock"
    with open(lock_path, "a") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            # v19: 防重检查 — 墓碑记录存在时拒绝僵尸 Worker 后写
            vid = verdict.get("variant_id")
            bid = verdict.get("batch_id")
            if vid and bid:
                existing = _read_records_unlocked(verdicts_path)
                # v21 修正: 批次唯一性约束 — 同一 batch_id+variant_id 仅允许写入一次
                # （无论已存在记录是 error/timeout/ok，均拒绝重复写入）
                if any(rec.get("variant_id") == vid and rec.get("batch_id") == bid
                       for rec in existing):
                    logger.warning(
                        f"Rejecting duplicate verdict write for {vid}/{bid}: "
                        f"record already exists in this batch"
                    )
                    return  # 拒绝写入
            with open(verdicts_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(verdict, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

def update_batch_verdicts(verdicts_path, batch_id, updates):
    """原子批次更新: 排他锁 → 内部无锁容错读取 → 更新 → 写 tmp → fsync → os.replace。
    v15 修正: 内部调用 _read_records_unlocked（非 read_verdicts），
    避免同一进程在不同 fd 上重入 flock 导致自我死锁。
    v15 修正: 循环变量统一为 records（修复 NameError: lines）。
    """
    lock_path = verdicts_path + ".lock"
    with open(lock_path, "a") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            records = _read_records_unlocked(verdicts_path)
            for v in records:
                vid = v.get("variant_id")
                if v.get("batch_id") == batch_id and vid in updates:
                    upd = updates[vid]
                    v.update(upd)
                    if "metrics" in v and isinstance(v["metrics"], dict):
                        v["metrics"].update(upd)
            tmp_path = f"{verdicts_path}.{os.getpid()}.{time.time_ns()}.tmp"
            # v19 修正: 进程级唯一临时文件名（防并发竞争覆盖）
            with open(tmp_path, "w", encoding="utf-8") as f:
                for v in records:
                    f.write(json.dumps(v, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, verdicts_path)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
```

### 8.6 scripts/praxist_supervisor.py

**改动**:
- 成功条件判断：`pass_variant_pf_ratios` -> `len(pass_variants) >= 4`（pass_variants = gate_pass + fdr_pass/migrated_pass）
- 变体状态分类：从 PF/EV 改为 DirAcc/endpoint_MAPE
- prompt 中引用 PF/EV 的部分全部替换
- **新增批次 FDR 结算**: 慢环全部 verdict 产出后，按 `batch_id` 筛选本轮变体，调用 `bh_fdr_promote()` 写入 `fdr_pass`，再调用 `registry_lib.update_batch_verdicts()` 原子覆写持久化
- **单一 verdict 文件**: 只读写 `aligned_verdicts.jsonl`（已迁移为 v2 schema）
- **v17 新增: 批次超时熔断（Batch Timeout Circuit Breaker）**: Supervisor 为每个批次设定动态超时时间。超时后以实际收集到的有效变体集合执行 FDR 结算，未就绪变体补记为超时淘汰（`status: "timeout"`, `fdr_pass: False`, `p_value: 1.0`）。防止慢环因外部不可控因素导致 Supervisor 无限挂死：
  ```python
  # v21 CPU 适配: 动态超时（非固定 2h），按变体数量估算
  # CPU 环境单变体 588 点 × 1.2s/点 ≈ 12min，预留 20min 缓冲
  ESTIMATED_PER_VARIANT_TIMEOUT_CPU = 20 * 60  # 秒
  BATCH_MIN_TIMEOUT = 3600  # 最低 1 小时

  def get_batch_timeout(expected_variants):
      """根据变体数量动态计算批次超时时间，防止 CPU 回测误杀。"""
      k = len(expected_variants)
      return max(BATCH_MIN_TIMEOUT, k * ESTIMATED_PER_VARIANT_TIMEOUT_CPU)

  def make_timeout_tombstone(variant_id, batch_id, symbol="unknown"):
      """构造超时墓碑记录，与 Schema v2 完全对齐。"""
      return {
          "schema": "fm.aligned_verdict.v2",
          "variant_id": variant_id,
          "symbol": symbol,
          "batch_id": batch_id,
          "stage": "aligned",
          "status": "timeout",
          "gate_pass": False,
          "p_value": 1.0,
          "fdr_pass": False,
          "migrated_pass": False,
          "cov_family": "unknown",
          "dir_acc": 0.0,
          "endpoint_mape": None,
          "endpoint_bias_pct": None,
          "path_corr": None,
          "weighted_dir_acc": 0.0,
          "mae": None,
          "mape": None,
          "decay": None,
          "n": 0,
          "n_eff": 0,
          "metrics": {
              "dir_acc": 0.0, "endpoint_mape": None, "endpoint_bias_pct": None,
              "path_corr": None, "weighted_dir_acc": 0.0, "mae": None,
              "mape": None, "decay": None, "n": 0, "n_eff": 0,
              "p_value": 1.0, "gate_pass": False, "fdr_pass": False,
              "migrated_pass": False, "batch_id": batch_id,
          },
      }

  def wait_for_batch(batch_id, expected_variants, verdicts_path,
                     worker_pids=None, timeout=None):
      """等待批次变体收集完毕或超时。
      expected_variants: 本批次预期变体列表（dict 含 variant_id/symbol，或纯 ID 字符串）。
      worker_pids: 本批次关联的 Worker 进程 PID 列表（超时后清理用）。
      timeout: 动态超时（秒），默认按 get_batch_timeout() 计算。
      """
      if timeout is None:
          timeout = get_batch_timeout(expected_variants)
      expected_ids = {
          v["variant_id"] if isinstance(v, dict) else v
          for v in expected_variants
      }
      expected_count = len(expected_ids)
      start = time.monotonic()
      while time.monotonic() - start < timeout:
          records = read_verdicts(verdicts_path)
          batch_records = [v for v in records if v.get("batch_id") == batch_id]
          # v19 修正: 基于去重 ID 集合判定（而非 len(batch_records) 行数），
          # 防止重试/双写导致行数虚高提前退出
          done_ids = {
              v["variant_id"] for v in batch_records
              if v.get("variant_id") in expected_ids
          }
          if len(done_ids) >= expected_count:
              return batch_records
          time.sleep(30)  # 30s 轮询间隔

      # v18 修正: 超时熔断 — 补记 timeout tombstones
      # v23 修正: 超时跳出后执行最后一次刷新读取，消除 30s sleep 期间的数据盲区
      # 防止变体在最后一刻入库却被误判为超时
      records = read_verdicts(verdicts_path)
      batch_records = [v for v in records if v.get("batch_id") == batch_id]
      done_ids = {
          v["variant_id"] for v in batch_records
          if v.get("variant_id") in expected_ids
      }
      missing_ids = expected_ids - done_ids

      if not missing_ids:
          return batch_records  # 最后一秒刚好入库，避免误杀熔断

      logger.warning(
          f"Batch {batch_id} timeout: {len(done_ids)}/{expected_count}, "
          f"missing: {missing_ids}"
      )

      # v20 落地: 优先清理僵尸 Worker 进程组（避免后续写冲突）
      if worker_pids:
          cleanup_batch_workers(worker_pids, batch_id)

      # 写入墓碑记录
      for vid in missing_ids:
          sym = "unknown"
          for ev in expected_variants:
              if isinstance(ev, dict) and ev.get("variant_id") == vid:
                  sym = ev.get("symbol", "unknown")
                  break
          timeout_verdict = make_timeout_tombstone(vid, batch_id, symbol=sym)
          append_verdict(verdicts_path, timeout_verdict)

      return [v for v in read_verdicts(verdicts_path) if v.get("batch_id") == batch_id]

  def cleanup_batch_workers(worker_pids, batch_id):
      """超时后清理批次关联的 Worker 进程组（整组清理，含防自杀与 PGID 缓存保护）。
      v22 修正: 子进程若未脱离父进程组（PGID 继承），killpg 会杀死 Supervisor 自身！
      v23 修正: 第一轮 SIGTERM 后组长进程可能已退出，第二轮必须用缓存的 PGID 杀残留。
      Supervisor 启动 Worker 时应加 start_new_session=True 使其脱离父进程组。
      """
      import signal
      current_pgid = os.getpgrp()
      target_pgids = set()    # 独立进程组 → 用 killpg
      standalone_pids = set() # 继承父进程组 → 用 kill 单进程

      # 第一轮: 收集 PGID 并发送 SIGTERM
      for pid in worker_pids:
          try:
              pgid = os.getpgid(pid)
              if pgid == current_pgid:
                  standalone_pids.add(pid)
                  os.kill(pid, signal.SIGTERM)
              else:
                  target_pgids.add(pgid)
                  os.killpg(pgid, signal.SIGTERM)
          except (ProcessLookupError, PermissionError):
              pass

      time.sleep(30)

      # 第二轮: 使用缓存的 target_pgids 强制 SIGKILL
      # （即使组长 PID 已死，缓存的 PGID 仍可杀掉残留子进程）
      for pgid in target_pgids:
          try:
              os.killpg(pgid, signal.SIGKILL)
              logger.warning(f"Force-killed zombie process group PGID={pgid} for batch {batch_id}")
          except (ProcessLookupError, PermissionError):
              pass

      for pid in standalone_pids:
          try:
              os.kill(pid, signal.SIGKILL)
          except (ProcessLookupError, PermissionError):
              pass
  ```

> **v22 进程启动契约**: Supervisor 启动慢环 Worker 时**必须**使用 `start_new_session=True`，
> 确保子进程建立独立进程组（PGID ≠ Supervisor PGID），使 `killpg` 安全生效：
> ```python
> proc = subprocess.Popen(cmd, start_new_session=True)  # 关键!
> ```

> **v19 新增: 僵尸 Worker 防线说明**: `append_verdict` 已内置防重检查（同 batch_id+variant_id
> 存在墓碑时拒绝写入），作为第二层防线。`cleanup_batch_workers` 为第一层防线（进程清理）。

### 8.7 scripts/praxist_goal.yaml

**改动**: `success_condition` 从 PF ratio 改为 `len(pass_variants) >= 4`（pass_variants 定义见 §5）

### 8.8 config/praxist_task.yaml

**改动**: `objective.primary` 从 `ev_after_slippage` 改为 `dir_acc`

### 8.9 cascade/signal_contract.py

**改动**:
- `position_from_forecast()` 保留但删除 `position_sign` 的交易语义
- `_trade_label()` 函数删除
- 其他模块引用适配

### 8.10 scripts/generate_baseline_points.py（新增脚本）

**新增**: 生成品种级基线逐点数据文件 `baseline_points_{symbol}.jsonl`。
- 使用 `cov_override="ccl"` 对该品种运行完整 walk-forward 回测
- 输出逐点 `(cutoff, dir_ok, delta_pred, delta_real)` 记录
- 同时更新 `baseline_metrics.json` 中的标量汇总（DirAcc, endpoint_MAPE）
- 在 Supervisor 启动阶段的前置预检中调用（见 §9.4 基线预检协议），**禁止在慢环内调用**

---

## 9. 迁移方案（v3：单文件策略，废除双文件运行时合并）

### 9.1 迁移策略（已修正审阅缺陷）

**废除运行时双文件合并**。原因：若 v1 verdict 在运行时被直接加载，下游代码访问 `v["dir_acc"]` 等 v2 字段会触发 `KeyError` 崩溃。

**新策略**: 强制离线全量转码，运行时仅面向单文件。

```
升级流程（一次性，严格顺序）:
1. 停止 supervisor
2. 备份原文件: cp aligned_verdicts.jsonl aligned_verdicts.jsonl.bak_v1
   （必须先备份，确保原文件安全）
3. 运行 migrate_verdicts_v1_to_v2.py
   → 读取 aligned_verdicts.jsonl.bak_v1 (v1)
   → 逐条从 checkpoint 数据重算 v2 指标
   → checkpoint 缺失时: 记录 warning，该条标记 status="migration_failed" 跳过
   → 写入临时文件 aligned_verdicts.jsonl.tmp
4. 原子替换: mv aligned_verdicts.jsonl.tmp aligned_verdicts.jsonl
   （mv 是原子操作，不存在中间态）
5. 验证: wc -l aligned_verdicts.jsonl 确认行数合理
6. 重启 supervisor（仅读写 aligned_verdicts.jsonl，v2 schema）
```

> **v3→v4 修正**: 旧版步骤 3→4 顺序颠倒（先重命名再备份），会导致原 v1 文件被覆盖销毁。
> 修正为：先备份（步骤 2）→ 写入临时文件（步骤 3）→ 原子替换（步骤 4）。
> 新增 checkpoint 缺失容错（步骤 3）：单条失败不中断全量迁移。

运行时不再有 v1/v2 冲突仲裁问题——只有一个文件、一个 schema。

### 9.2 旧 checkpoint 数据

现有 checkpoint JSONL 包含足够的字段重算 v2 指标：
- `pred_end`, `real_end`, `base` -> 可算 `endpoint_mape`, `endpoint_bias_pct`
- `delta_pred`, `delta_real` -> 可算 `dir_ok`, `weighted_dir_acc`
- 无 `pred_path`/`real_path` 存储 -> `path_corr` 无法从旧数据重算

**旧数据 null 处理**: 迁移时 `path_corr` 写入 JSON `null`（不是字符串 `"N/A"`）。旧 checkpoint 无 baseline 逐点对齐数据，`p_value` 写入 `null`（DM 检验需要逐点 baseline dir_ok，旧数据不可得）。`fdr_pass` 写入 `null`。`batch_id` 写入 `"migrated_v1"`。

**迁移 `n_eff` 保留规则（v15 新增，v20 固化补算公式）**: `n` 和 `n_eff` 必须直接从旧 v1 verdict 中读取（`v1["n_eff"]`），不得从 checkpoint 重新计算（checkpoint 不含自相关统计量）。若旧 verdict 中 `n_eff` 缺失，使用以下 Bartlett 公式从旧 `n` 和默认 `horizon=24, step=2` 补算：

```python
def fallback_n_eff(n, horizon=24, step=2):
    """Bartlett 有效样本量退化公式。
    当旧 verdict 缺少 n_eff 时，从 n + 已知自相关参数补算。
    n=588, horizon=24, step=2 → h=12 → n_eff ≈ 73。
    """
    h = max(1, horizon // step)  # h = 12
    # Bartlett 核自相关膨胀因子
    factor = 1.0 + 2.0 * sum((1.0 - j / h) ** 2 for j in range(1, h))
    return max(1, int(n / factor))  # 588 / 8.08 ≈ 72
```

**迁移记录晋级兼容规则（v8 新增，v9 修正为规范化转码）**:

> **v8→v9 修正**: v8 版保留了 `fdr_pass: null` 依赖下游 `is_pass_variant()` 兼容判定。
> 但这与 §5 成功条件 `all(v.fdr_pass and v.gate_pass)` 冲突——null 穿透导致全局目标永远失败。
> 改为在迁移脚本中一步到位规范化：通过门控的历史变体直接写入 `fdr_pass: true`。

```python
# migrate_verdicts_v1_to_v2.py 中的 fdr_pass 赋值逻辑
if v1_verdict.get("gate_pass") and new_v2_gate_pass:
    # 历史优秀变体：直接裁定为通过
    verdict["fdr_pass"] = True
    verdict["migrated_pass"] = True  # 标记为迁移裁定（与正常 FDR 裁定区分）
else:
    verdict["fdr_pass"] = False
    verdict["migrated_pass"] = False
```

这样全系统 Schema 均严格保持布尔确定性（无 `null` 穿透），§5 成功条件和下游筛选逻辑无需任何特判。

> **v4→v5 修正**: 旧版写 `p_value 从 dir_acc + n_eff 重算（compute_p_value）` 是废弃逻辑。
> v5 的 p_value 来自 DM 检验，需要逐点 baseline dir_ok 序列，旧 checkpoint 无法提供。
> 迁移记录的 p_value 必须为 `null`，不得混入非配对的假 p 值。

### 9.3 迁移脚本

```python
# scripts/migrate_verdicts_v1_to_v2.py
"""从旧 checkpoint 数据重新计算 v2 指标。
- path_corr: null（无原始路径数据）
- weighted_dir_acc: 从 delta_real + dir_ok 重算
- p_value: null（DM 检验需要逐点 baseline dir_ok，旧数据不可得）
- fdr_pass: 根据 (v1_gate_pass AND v2_static_gate_pass) 赋 True/False
- migrated_pass: True/False（标记迁移裁定，与正常 FDR 裁定区分）
- batch_id: "migrated_v1"
- gate_pass: 按新 gate 条件重新判定（n, n_eff, dir_acc）
- 容错: checkpoint 缺失时记录 warning，该条标记 status="migration_failed"
- 输出: aligned_verdicts.jsonl.tmp → 原子替换 aligned_verdicts.jsonl
"""

# v19 新增: cov_family 回溯映射（防止迁移记录全部为 "unknown" 导致 families_hit 空集）
def resolve_cov_family(v1_verdict, covariate_pool):
    """从协变量池反查 cov_family，三级回退：
    1. covariate_pool.json 中按 cov_override 精确匹配 family
    2. 变体 ID 命名规则启发式（如 *_calendar_* → "calendar"）
    3. 无法匹配 → "unknown"
    """
    cov = v1_verdict.get("cov_override", "")
    # v22 修正: 容错 covariate_pool 结构 — 可能是 list 或 dict
    if isinstance(covariate_pool, dict):
        pool_entries = list(covariate_pool.get(
            "covariates", covariate_pool.get("pool", covariate_pool.values())
        ))
    else:
        pool_entries = covariate_pool
    # Level 1: 协变量池精确匹配
    for entry in pool_entries:
        if isinstance(entry, dict) and entry.get("name") == cov and "family" in entry:
            return entry["family"]
    # Level 2: 命名启发式（v20 修正: 同时检索 cov_override + variant_id）
    search_text = f"{cov} {v1_verdict.get('variant_id', '')}".lower()
    name_hints = {
        "momentum": ["roc", "ema_cross", "rsi", "momentum"],
        "volatility": ["atr", "bollinger", "realized_vol"],
        "inventory": ["warehouse", "inventory", "stockpile"],
        "calendar": ["calendar", "month", "holiday", "seasonal"],
        "term_structure": ["spread", "contango", "backstructure", "basis"],
        "macro_sentiment": ["vix", "dollar", "rate", "sentiment"],
    }
    for family, keywords in name_hints.items():
        if any(kw in search_text for kw in keywords):
            return family
    # Level 3: 无法识别
    return "unknown"
```

### 9.4 Baseline 逐点存储协议（v5 新增，v15 加固预检与并发锁）

Diebold-Mariano 检验需要变体与 Baseline 在**完全相同的时间点**上的逐点 dir_ok 序列。仅存储标量 DirAcc 不够。

**存储方案**:
- 标量汇总: `task_FM/config/baseline_metrics.json`（品种级 DirAcc/endpoint_MAPE）
- 逐点明细: `task_FM/config/baseline_points_{symbol}.jsonl`

每条记录格式:
```json
{"cutoff": "2024-06-15 09:00:00", "dir_ok": true, "delta_pred": 12.5, "delta_real": 8.3}
```

**时间戳归一化协议（v6→v7 新增，v14 加固，v15 加排序）**:
- 回测引擎内部可能混合使用 `pd.Timestamp`、ISO 字符串（带 `T`）或不同精度
- 在加载 baseline 逐点文件和变体逐点序列时，**统一归一化为 Unix 整数时间戳**：
  ```python
  def safe_normalize_cutoff(ts):
      """安全时间戳归一化。强制 UTC+8 固定时区，消除跨环境漂移。
      None/畸变值 → None（Join 时跳过）。
      系统运行时区: Asia/Shanghai (UTC+8)。
      """
      if ts is None:
          return None
      # v21 修正: 若已经是秒级整数时间戳，直接返回（避免 pd.Timestamp 按纳秒解析）
      # pd.Timestamp(1718413200) 默认单位是纳秒 → 1970-01-01 00:00:01.718...
      # 导致所有时间点坍缩为整数 1，Inner Join 匹配全部归零
      # v22 修正: 兼容 int / float / numpy 标量，并区分秒级与毫秒级
      if isinstance(ts, (int, float, np.integer, np.floating)):
          val = float(ts)
          if val > 1e11:     # 毫秒级 Unix 时间戳（如 1718413200000）
              return int(val / 1000)
          elif val > 1e8:    # 秒级 Unix 时间戳（如 1718413200 或 1718413200.0）
              return int(val)
      # v23 修正: 兼容纯数字字符串（如 "1718413200"）
      if isinstance(ts, str) and ts.strip().replace(".", "", 1).isdigit() and len(ts.strip()) >= 9:
          ts = float(ts.strip())  # 转为 float 后重新进入上方数值分支
          return int(ts) if ts < 1e11 else int(ts / 1000)
      try:
          t = pd.Timestamp(ts)
          if t.tzinfo is None:
              # v19 修正: tz-naive → 直接假定 Asia/Shanghai 本地时间
              # （避免 tz_localize(None) 对 tz-aware 硬剥离导致 8h 漂移）
              t = t.tz_localize("Asia/Shanghai")
          else:
              # v19 修正: tz-aware → 正确时区转换（非硬剥离）
              # 例: 2024-06-15 01:00:00+00:00 → 09:00:00+08:00（正确对齐）
              t = t.tz_convert("Asia/Shanghai")
          return int(t.timestamp())
      except Exception:
          return None
  ```
- Inner Join 使用归一化后的整数时间戳匹配，跳过 `ts is None` 的记录
- 若有效配对样本量 $< 100$，触发降级（见下方第 6 条）

**对齐协议**:
1. Baseline 回测在首次运行时生成 `baseline_points_{symbol}.jsonl`（使用 `cov_override="ccl"`）
2. 慢环在计算 `diebold_mariano_p` 前，按归一化时间戳与 Baseline 逐点文件做 **Inner Join**
3. 仅保留双方都存在的配对点，确保等长且时间同步
4. **时序排序（v15 新增，HAC 数学前提）**: 配对完成后必须按时间戳升序排序，
   保障 Newey-West HAC 滞后自协方差的数学有效性：
   ```python
   paired.sort(key=lambda x: x["timestamp"])
   ```
5. **基线配对校验（v17 修正，废除慢环内自愈）**: 慢环仅以只读方式加载 Baseline。
   若 Baseline 文件缺失或有效配对样本量 < 100（覆盖率不足），慢环记录 WARNING 并置 `p_value = None`，该变体在本轮 FDR 自动判负。**绝对禁止在慢环中调用 `generate_baseline_points.py`**。所有缺失基线必须在 Supervisor 启动阶段的前置预检中串行补全。
6. 若配对点数 < 100，记录 warning，`p_value` 设为 `null`。因缺乏充分样本支撑统计检验，批次结算时该变体 `safe_p` 返回 1.0 垫底，`fdr_pass` 裁定为 `False`——该变体**无法晋级**

**首次生成 Baseline 逐点数据**:
```bash
python scripts/generate_baseline_points.py --symbol ss --cov ccl
# 输出: task_FM/config/baseline_points_ss.jsonl (588 条)
```

**基线预检协议（v15 新增，消除因果倒置）**:

基线就绪检查必须在变体回测**之前**完成，不在 `gate()` 或 `evaluator` 内部触发：

```
Supervisor 启动流程:
1. 读取 baseline_metrics.json
2. 检查所有 priority_symbols 是否均有基线条目
   v19 修正: 双重要求 — 同时校验标量 JSON 和逐点 JSONL:
   a. baseline_metrics.json 包含该 symbol 且数值有效
   b. task_FM/config/baseline_points_{symbol}.jsonl 存在且有效行数 >= 100
   （防止仅标量存在但逐点文件损坏/丢失导致慢环 p_value 全部降级为 None）
3. 缺失或校验不通过的品种 → 串行执行 generate_baseline_points.py（品种间加 .lock 排他锁）
   **v21 CPU 适配: 心跳日志**: CPU 环境下单品种基线生成约需 10~15 分钟。
   生成脚本每完成 50 个评估点必须输出进度日志，防止外部看门狗误判进程挂死：
   `[Progress] Baseline generation for {sym}: {done}/{total} points done...`
4. 基线全部就绪 → 启动慢环
5. 慢环内 evaluator 仅做读取，不再触发基线生成
```

> **v15 修正**: 旧版将基线自愈挂在 evaluator 内部（§8.3 冷启动防御），导致冷启动时
> gate() 先于基线存在执行，baseline_dir_acc=None → 全部套用 0.52 严格门槛 → 低基线
> 品种变体被误杀。v15 将基线初始化提拉至 Supervisor 启动阶段，确保 gate() 执行时
> baseline_metrics.json 已完整可用。

---

## 10. Peer 智能体 Prompt 重构（已修正审阅缺陷）

### 旧核心

> Author covariate hypotheses to optimize PF. Gate: n>=350, IC>=0.05, EV>0, PF ratio>1.05.

### 新核心

> Author covariate hypotheses to optimize prediction accuracy. Primary metric: DirAcc (direction accuracy at T+24). Gate: n>=350, n_eff>=50, DirAcc >= adaptive_baseline_min (0.50~0.52 depending on symbol baseline). Statistical significance is assessed via Diebold-Mariano test (Newey-West HAC) vs baseline with Benjamini-Hochberg FDR correction. Secondary diagnostics: endpoint_MAPE, path_corr, endpoint_bias_pct, weighted_dir_acc.
>
> Each proposal must specify:
> - mechanism: how the covariate improves direction prediction (qualitative reasoning, not fake numeric predictions)
> - which aspect of residual the covariate is expected to reduce (trend reversal detection, momentum persistence, mean-reversion timing, etc.)
> - why this covariate should improve DirAcc relative to the static baseline (ccl)

### Baseline 定义（v3 新增，v4 修正）

> **Baseline = 静态基线**，即该品种在无协变量（`cov_override: "ccl"`）条件下的 DirAcc/endpoint_MAPE。
>
> 完整基线表在 `task_FM/config/baseline_metrics.json` 中维护，首次运行时从 `ccl` 协变量的回测结果自动生成。
>
> **为什么用静态基线而非动态基线**:
> 1. 可重复性：每个 peer 看到相同的参考点，假设可横向比较
> 2. 避免漂移：动态基线随代际变化，第 1 代和第 5 代的 "+0.02" 含义不同
> 3. 简化 peer 推理：peer 只需知道 "ccl 的 DirAcc 是多少，我的协变量为什么能更好"
>
> **v4 修正**: 不再要求 peer 输出硬性浮点数预测（如 `predicted DirAcc > baseline +0.02`）。
> LLM 无法可靠预测具体数值，强制此类格式会导致机械性捏造。
> 改为要求 peer 提供**定性机制论证**：说明协变量影响哪个维度的残差，以及为什么。

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| DirAcc 只看方向不看幅度 | `weighted_dir_acc` 作为诊断参考；`endpoint_mape` 约束点位误差 |
| 方向准但不赚钱的协变量被选入 | 接受：本系统定位是预测系统，交易由上层决策 |
| path_corr 无法从旧 checkpoint 迁移 | 旧 verdicts 设 `path_corr: null`（JSON null），聚合时跳过 |
| path_corr 零方差/None 导致崩溃 | `safe_path_corr()` 含 None/长度/NaN/零方差全链路保护 |
| 反向预测变体绕过门控 | Gate 改为单侧 `dir_acc >= 0.52`，不使用 abs() |
| 统计检验误用名义 $n$ 导致假阳性 | DM 检验 + Newey-West HAC 消除自相关，全量 588 点保留 |
| 下采样 McNemar 功效崩塌（588→49 死锁） | 废除下采样，替换为 DM 检验（全样本 + HAC） |
| Bonferroni 导致系统死锁（v4 致命） | 替换为 BH-FDR + DM 检验 |
| 逐变体 verdict 无法获取全局 $K$ | $K=K_{total}$（含未过门变体以 p=1.0 占位），消除选择偏差 |
| Supervisor 批次结算无持久化回写 | `update_batch_verdicts()` 原子替换（.tmp→os.replace），非 truncate |
| `truncate()` 覆写导致进程中断数据丢失 | 写入 .tmp → fsync → os.replace，原文件不受损 |
| `append_verdict` 文件句柄外溢 | 入参改为文件路径，内部自闭环管理锁 |
| 时间戳字符串比对脆弱（Inner Join 零匹配） | 统一归一化为 Unix 整数时间戳 |
| `endpoint_bias` 绝对值跨品种不可比 | 改为 `endpoint_bias_pct`（除以 base 的百分比偏差） |
| `fdr_pass` 未过门变体保持 null 悬挂态 | 批次结算时显式赋 `False` |
| v1/v2 混合读取导致 KeyError | 废除双文件合并；强制离线迁移后单文件运行 |
| 迁移 SOP 步骤颠倒导致数据丢失 | 先备份再写入临时文件再原子替换 |
| checkpoint 缺失导致迁移中断 | 单条容错：记录 warning，标记 `migration_failed`，继续下一条 |
| `weighted_dir_acc` 分母为零 | 分母 < 1e-8 时回退到 0.5 |
| `decay` 分母为零 | `mae_h2 / max(mae_h1, 1e-6)` |
| Peer 输出虚假数值预测 | 改为定性机制论证，不强制数值承诺 |
| endpoint_mape 极端低价资产放大误差 | 分母下限截断 `max(base, 1.0)` |
| Baseline 定义歧义 | 静态基线 = 无协变量回测结果，写入 `baseline_metrics.json` |
| `tz_localize(None)` 对 tz-naive 抛 TypeError → 静默归零 → Inner Join 零匹配（v17 致命） | 先检查 `t.tzinfo is not None`，仅 tz-aware 才剥离 |
| `{1-star set}` YAML 表达式导致 `eval()` SyntaxError（v17 致命） | Supervisor 预计算标量 `n_one_star_symbols_hit`，YAML 仅做原子比较 |
| §9.4 第 5 条慢环自愈与预检协议自相矛盾 → 并发抢写 Baseline | 废除慢环内自愈，统一为「预检负责生成，慢环只读降级」 |
| 慢环 OOM / 崩溃 → Supervisor 批次结算无限挂死（v17 致命） | 全局 Tombstone Record（`status: "error"`, `p_value: 1.0`）+ 批次超时熔断（2h） |
| `calc_prediction_quality` 入参原生 list → 向量减法 TypeError | 函数入口 `np.asarray(..., dtype=float)` 统一强转 |
| `cov_family` 缺解析来源契约 → `families_hit` 统计口径不一致 | 受控词表 6 族 + 双源解析优先级（协变量池 > Peer 输出 > "unknown"） |
| `wait_for_batch` 引用未定义 `expected_variants` / `make_timeout_tombstone` → NameError（v18 致命） | 入参改为 `expected_variants` 集合 + 内联 Tombstone 构造函数 |
| Tombstone 缺少 `schema`/`stage`/`metrics` 字段 → 下游 `metrics.update()` KeyError（v18 致命） | Tombstone 与 Schema v2 完全对齐，包含 `metrics` 嵌套字典 |
| `delta_real == 0` 时 `dir_ok` 判定退化 → 虚假方向一致（v18 统计） | `abs(delta_real) < 1e-8` 时判 `False`（保守原则），新增 §3.5 |
| BH-FDR 多个 `p=1.0` 并列 → Timsort 顺序不确定 → 跨运行结果不可复现（v18 统计） | 二级排序键 `(safe_p(v), v["variant_id"])` 保证幂等 |
| `tz_localize(None)` 硬剥离 tz-aware 导致 8h 时间漂移 → Inner Join 归零（v19 致命） | tz-naive → `tz_localize("Asia/Shanghai")`；tz-aware → `tz_convert("Asia/Shanghai")` |
| `families_hit` 统计中 `"unknown"` 为非空字符串 → truthy 假达标（v19 逻辑） | 显式排除 `v["cov_family"] != "unknown"` |
| `wait_for_batch` 用 `len(batch_records)` 行数判定 → 重试双写导致提前退出（v19 致命） | 改为基于 `done_ids` 去重 ID 集合判定 |
| `point_dir_ok_list` 含字符串 cutoff 透传 DM → `np.asarray(float)` 崩溃（v19 致命） | evaluator 内部归一化 + Inner Join + 解构为纯 bool/int 序列 |
| 超时熔断后僵尸 Worker 后写冲突记录（v19 并发） | `append_verdict` 防重检查 + Worker 进程组 SIGTERM/SIGKILL |
| 单品种 $K<4$ FDR 失去多重检验控制（v19 统计） | 降级为 Bonferroni 固定阈值 $\alpha=0.025$ |
| 路径 `mape` 分母 `abs(real_path)` 为零 → `inf`/`nan`（v19 数值） | 分母下限 `np.maximum(..., 1.0)` |
| 基线预检仅查标量 JSON 不查逐点 JSONL → 慢环 p_value 全降级（v19 运维） | 双重要求：`baseline_metrics.json` + `baseline_points.jsonl` 行数 ≥ 100 |
| 固定 `.tmp` 文件名并发竞争覆盖（v19 并发） | `f"{verdicts_path}.{pid}.{time_ns()}.tmp"` 进程级唯一 |
| 迁移历史 verdict `cov_family` 全为 `"unknown"` → `families_hit` 空集（v19 迁移） | 三级回退：协变量池精确匹配 → 命名启发式 → `"unknown"` |
| Tombstone `metrics` 字典缺字段 → 下游 `metrics[key]` KeyError（v19 契约） | metrics 与 Schema v2 根节点严格对齐，缺省 `None` |

---

## 12. 不在范围内

- 不改变模型架构（TimesFM 2.5 级联不变）
- 不改变数据管道（DataStore、features.py 不变）
- 不改变协变量池（covariate_pool.json 不变）
- 不改变 signal_weight 方案（scheme 保留，但只用于 weighted_pred 计算，不用于交易）
- 不改变模型训练流程
