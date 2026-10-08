# 评估口径（唯一权威）

> **本文是评估阈值与判定的唯一事实源。** 其他**规范层文档**
> （`AGENTS.md` / `CLAUDE.md` / `STATE.md` / `runtime_contract.md` / `system_design.md` / `praxist.md`）
> **不得独立复述阈值数字**，只能链接本文。
> `superpowers/` 下的历史 spec/changelog/报告（L2 证据层）可含原始数字作为历史快照。
>
> 上游设计论证：[superpowers/specs/2026-09-14-prediction-quality-redesign-design.md](./superpowers/specs/2026-09-14-prediction-quality-redesign-design.md)（v23）
> 实现：[../task_FM/evaluations/fm_eval/evaluator.py](../task_FM/evaluations/fm_eval/evaluator.py)
> 统计：[../cascade/statistical_tests.py](../cascade/statistical_tests.py)
>
> 最后核实：2026-10-05，commit `ee01b56`。**本文不钉活快照**——阈值以代码为准。

---

## 1. 为什么需要这份文档

阈值曾散落在 **18 个文件**里（spec / changelog / 审计报告 / 三份 AGENTS.md / STATE.md）。
改一次阈值要同步 18 处，漏一处就产生矛盾——历史上已发生过：

- `docs/AGENTS.md` 与 `STATE.md` 都写「≥2★ 含 SS（8 品种）」，代码实为 7 品种
- `CLAUDE.md` 写「171 条裁决缺全部新字段、尚未接线」，实际早已接线

**教训**：重复陈述即腐烂。本文只留一份，其余改引用。

---

## 2. 硬门（`gate()`）

`evaluator.gate(s, min_n=350, min_n_eff=50, min_dir_acc=0.52, baseline_dir_acc=None)`

| 判据 | 阈值 | 代码 |
|------|------|------|
| 样本量 `n` | ≥ **350** | `gate(min_n=350)` |
| 有效样本 `n_eff` | ≥ **50** | `gate(min_n_eff=50)` |
| 方向准确率 `dir_acc` | ≥ `effective_min` | `compute_effective_min()`（`task_FM/evaluations/fm_eval/evaluator.py`） |

### 2.1 自适应门槛 `effective_min`

```
effective_min = max(0.50, min(0.52, baseline_dir_acc))
```

基线差时门槛跟着降。**基线缺失时按 0.52 读**。
所以「dir_acc 低于字面 0.52 仍过门」是**设计**，不是 bug。

新 verdict 落盘 `baseline_dir_acc` / `effective_min` 两个字段。
**旧行缺这两字段时按「未知门槛」读，不要假设恒为 0.52。**

### 2.2 fail-closed（非有限值一律拒）

`gate()` 对 `NaN` / `inf` **返回 False**，不比较：

```python
if not (math.isfinite(n) and math.isfinite(n_eff) and math.isfinite(dir_acc)):
    return False
```

理由：`NaN` 的比较恒为 False，若直接比较会让 `n=NaN` **绕过**硬门（fail-open）；
`dir_acc=inf` 数学上无意义。审计 bug #1 / #2 的修复。

同样地，`effective_sample_size()` 在 `step <= 0` 时**显式抛 ValueError**
（审计 bug #7），不再以 `ZeroDivisionError` 崩溃。

---

## 3. 有效样本量 `n_eff`（Bartlett）

`effective_sample_size(nominal_n, horizon, step, residual_autocorr=None)`

- `step >= horizon` → 无重叠，直接返回 `nominal_n`
- 默认自相关 `residual_autocorr = 0.9`
- 全核 Bartlett 权重：`max_overlap_step = (horizon - 1) // step`
- 方差膨胀因子 `VIF = 1 + 2·Σ(1−k/(m+1))·ρ^k`
- `n_eff = max(1, int(nominal_n / VIF))`

---

## 4. 统计裁决

### 4.1 DM 检验（Diebold-Mariano）

`diebold_mariano_p(...)` —— Newey-West HAC + HLN 小样本校正。

配对序列是**方向判定差**：`d_t = dir_ok_variant − dir_ok_baseline`。

### 4.2 BH-FDR（per-symbol）

`bh_fdr_promote(verdicts, fdr_q=0.10, min_batch_size=4, bonferroni_alpha=0.025)`

| 条件 | 校正方式 |
|------|---------|
| `K < 4` | Bonferroni，α = **0.025** |
| `K >= 4` | BH-FDR，q = **0.10** |

**per-symbol 分组**——不是全局校正。`gate_pass=False → fdr_pass=False`（永不过）。
重复 `variant_id` 取最后一次写入。

### 4.3 fdr_pass 落盘前置条件

`praxist_supervisor.py::fdr_pass_persistable()` —— 只有**确认运行 + 缺失可接受 +
DM 可确认**时，`fdr_pass=True` 才允许写入：

```
run_mode == "confirmation"
  ∧ missingness_admissible is True
  ∧ dm_status ∈ {"ok", "set_mismatch_ok"}
```

---

## 5. 已退役出裁决链的字段

| 字段 | 状态 |
|------|------|
| **PF / EV / MaxDD / IC** | **仅经济报表字段，不参与裁决** |
| 方向准确率绝对门槛（原 Phase 1） | 已退役 |
| `tier >= 8` | 已退役 |
| 固化判据 v2 的 Rule1–Rule5（MaxDD 一票否决 / EV 翻正绿通） | 已退役 |

> MaxDD 曾出现 **-265% / -134%** —— 那是 2026-08-21 修复前（`cascade/evaluation_metrics.py`
> cumprod+clamp）的旧口径，**不是当前值**。历史日志中见到不代表现状。

⚠️ **EV 单位歧义**：`monthly` stdout 打印 `EV_ratio=`（**无量纲**）；
`evaluation_metrics["EV"]` 是**价格点**。文档中的 EV 案例多为前者。

---

## 6. 裁决三态

| 态 | 含义 |
|----|------|
| `v2_pass` | 过门 |
| `hard-gate-but-losing` | 硬门统计过了但经济为负 |
| 变体级 `DEAD` | `materialize_known_verdicts` 判定家族死亡 |

### ⚠️ 两套 DEAD，别混名

| | 粒度 | 位置 | 判据 |
|---|------|------|------|
| **变体级 DEAD** | variant | verdict 的 `gate_pass` | 家族封账时判定 |
| **品种级 `SYMBOL_DEAD` / `HOLD`** | symbol | `config/symbol_status.json` | 人手改 JSON |

**家族死亡判据**（`scripts/praxist_supervisor.py` 的 `_dead_families(snapshot, min_ok=4)`）：
只数 `dm_status ∈ {ok, set_mismatch_ok}` 的 ok 行；`n_ok ≥ 4` 且 `gate_pass == 0`。
`insufficient_common` / `no_common_cutoff` / `set_mismatch_descriptive` 等**描述性 DM 不计数**
——它们不代表「试过且失败」。

---

## 7. protocol_fingerprint（跨协议可比性）

七组件，任一变化即基线不可比：

| # | 组件 | 承载 |
|---|------|------|
| 1 | `CONTEXT_BARS` / `CONTEXT_DAYS` | `backtest_config` |
| 2 | `EVAL_WINDOW_BARS` | 同上 |
| 3 | `STEP` | 同上 |
| 4 | `HORIZON` | 同上 |
| 5 | cutoff 约定（`bar_close`） | `compute_protocol_fingerprint()` |
| 6 | cov_fill 版本（`v2`） | `COV_FILL_VERSION` |
| 7 | adj_rule（`v1`）+ roll_guard（`v1`） | `ADJUSTMENT_RULE_VERSION` / `ROLL_GUARD_VERSION` |

映射表：[fingerprint_component_mapping.md](./fingerprint_component_mapping.md)

**版本定义**：`task_FM/evaluations/fm_eval/evaluator.py` 的 `PROTOCOL_FINGERPRINT_VERSION`。`scripts/restart_readiness_check.py` 有 assert 守着。
**bump 后必须重生基线**——`ensure_baselines` 自动比对。

### ⚠️ 指纹不覆盖数据窗口语义

2026-09-28 的 1-bar 前视 bug：`kline_1h.dt` 是**开盘时间**，
`dt <= cutoff` 会把目标首根放进训练集。修法 `_h1_upper_bound = cutoff_ts − 1h`。

**协议指纹完全测不出这类问题**——协议没变，数据语义变了。
→ 修数据窗口类 bug 必须**强制重生**，不能指望指纹 bump 兜底。

---

## 8. 活跃视图：按指纹过滤历史行

`aligned_verdicts.jsonl` 混着多代协议的裁决。**读的时候必须按当前指纹过滤**，
否则会把旧协议的行当现行结论。

历史演进（**已发生的事实，非活快照**）：
`protocol_v1` → `v2` → `v3` → `v4`。每次 bump 都留下旧指纹的行。

---

## 9. 变更记录

| 日期 | 内容 |
|------|------|
| 2026-10-05 | 初版。收拢 18 处散落的阈值口径。事实全部实测自 commit `ee01b56` |