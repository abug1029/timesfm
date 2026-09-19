# Task 7：评估指标、硬门、回测入口

- 任务：全系统审核计划 Task 7（只审代码+磁盘，不改生产代码，不 push，不启动 Praxist）
- 活仓：WSL `/home/abug/timesfm`
- 审核日：2026-09-11
- 消费：IC/EV/gate 合同；Task 1 矛盾 2/3/5
- 对照：`cascade/evaluation_metrics.py`、`config/backtest_config.py`、`config/praxist_task.yaml`、`scripts/monthly_backtest.py`、`scripts/aligned_slow_loop.py`、`task_FM/evaluations/fm_eval/evaluator.py`、`docs/validation_criteria.md`、`tests/test_evaluation_metrics_contract.py`、`tests/test_backtest_cutoff.py`、`tests/test_verdict_registry.py`、`tests/test_praxist_fm_evaluator.py`、`tests/test_system_hardening.py`、`scripts/registry_lib.py`、`scripts/praxist_supervisor.py`、`scripts/praxist_goal.yaml`、`loop-constraints.md`、`docs/praxist.md`、`docs/system_design.md` §7、`docs/AGENTS.md`、`task_FM/config/aligned_verdicts.jsonl`

**本子代理无 LSP 诊断通道。** 替代证据：通读上列文件 + 磁盘 26 行 verdict 对账 + `.praxist-venv` 下 `pytest tests/test_praxist_fm_evaluator.py tests/test_evaluation_metrics_contract.py tests/test_verdict_registry.py tests/test_system_hardening.py` → **65 passed**（14.06s）。

---

## 结论先行

活代码的秤和硬门布尔值是清楚的，不要按 `docs/system_design.md` §7 的示例去改。

| 项 | 活事实 |
|----|--------|
| **IC** | `2 * abs(dir_acc - 0.5)`。`evaluation_metrics.py` 只有 DirAcc，没有 Pearson / `corrcoef`。 |
| **gate_pass 布尔** | `n >= 350 and ic >= 0.05`。**不含 EV。** |
| **EV>0** | 经济目标 / 最终裁决 / `pass_variants()`，不是 `evaluator.gate()` 的布尔条件。 |
| **STEP / 窗口** | `STEP=2`，`EVAL_WINDOW_BARS=1200`，`CONTEXT_BARS=480`，`HORIZON=24`。 |
| **理论 n** | `len(range(0, 1200-24+1, 2)) = 589`，不是 600。磁盘最高 **588**。 |
| **主回测入口** | 慢环唯一调用 `monthly_backtest.run_symbol_backtest`；唯一写 `aligned_verdicts.jsonl` 的是 `aligned_slow_loop.py`。 |
| **磁盘「亏钱仍过硬门」** | 仍在：`i_oi`（ev=−2.46）和 `m_ccl`（ev=−3.64）都是 `gate_pass=true`。经济过门实质只有 `ss_vor`。 |

Task 1 矛盾 2/3/5 **全部在代码+磁盘上成立**。不要把 yaml/`system_design` 里的 `ev>0` 当成「`gate()` 忘了写」去改布尔语义。

---

## 1. 公式对账（唯一实现）

语义约定以 `cascade/evaluation_metrics.py` 文首为准（L3–17）。这是全项目「唯一秤」。

### 1.1 PF

- **实现**：`evaluation_metrics.py:90-99`。`pos = net[net>0]`，`neg = net[net<0]`，`PF = sum(pos) / abs(sum(neg))`；无亏损且有盈利 → `99.99`。
- **净盈亏**：`evaluation_metrics.py:82-88`。`gross = dirs * rets`；`dirs==0` 不扣滑点、不扣手续费；活跃单 `net = gross - tick_size * slippage_ticks`。
- **滑点**：`config/backtest_config.py:144` `SLIPPAGE_TICKS = 2`（双边合计 2 tick）。与秤文首一致。
- **调用**：`monthly_backtest.summarize` L453–454 → `metrics_from_backtest_points` → `calc_net_metrics`。verdict 的 `pf` 来自这里。
- **system_design §7.2**（L487–506）伪代码与活代码同构。**无分叉。**

### 1.2 EV 与 EV_ratio（单位必须拆开）

| 字段 | 公式 | 单位 | 出处 |
|------|------|------|------|
| `EV` | `mean(net_pnl)` | 价格点 | `evaluation_metrics.py:116`；verdict `ev`；`metrics.ev_after_slippage` |
| `EV_ratio` | `EV / mean(\|price_move\|)` | 无量纲 | `evaluation_metrics.py:117-119`；`summarize` L477 |

- `docs/AGENTS.md:52-54`：**Note on EV unit** 仍写「monthly stdout 打印的 `EV=` 实际是 EV_ratio」。活代码已经改名：`monthly_backtest.py:937-939` 打印 `EV_ratio=`，并注明「勿写成 EV=（价格点 EV 见 `s['ev']`）」。文档慢一拍，代码已修。
- `docs/validation_criteria.md` 案例（EV +0.167、−0.029）是 **EV_ratio 量级**，不是 verdict 价格点（`ss_vor` ev=+11.06）。
- `docs/system_design.md:510-512` 把 EV 写成 `mean(net)` 价格点，与秤一致；它没写 EV_ratio。
- **system_design §7.1 表**把 EV>0 列成「硬门条件」——那是经济层，不是 `gate_pass` 布尔。见 §2。

### 1.3 IC 与 DirAcc（矛盾 2：Pearson vs `2×|dir_acc−0.5|`）

**DirAcc（秤）** — `evaluation_metrics.py:139-147`：

```
active_mask = (dirs != 0) & (rets != 0)
DirAcc = mean(sign(dirs) == sign(rets))   # 仅活跃且价格有动
```

零变动不送分；空仓不罚。`DirAcc_legacy` 保留旧规则。`evaluation_metrics.py` **没有** Pearson、`np.corrcoef`、IC 字段。

**IC（评估器）** — 两处同一公式：

1. `evaluator.py:199-203` `gate()`：`ic = 2 * abs(m.get("dir_acc", 0.5) - 0.5)`
2. `aligned_slow_loop.py:96`：`v.setdefault("ic", round(2 * abs(float(v.get("dir_acc", 0.5)) - 0.5), 10))`

`build_summary` 不写 `ic`；慢环用 `setdefault` 补进 verdict。磁盘 26 行全部满足 `ic == 2*|dir_acc-0.5|`（抽查 ss_vor / i_oi / m_vor / cj_oi / m_ccl 全匹配）。

| 文档 | 写法 | 判定 |
|------|------|------|
| `loop-constraints.md:48` | `ic=2×\|dir_acc−0.5\|` | 与代码一致（权威） |
| `docs/praxist.md:94` | 同上 | 与代码一致 |
| `docs/system_design.md:485` | `corr(预测, 实际)` | **错合同**。评估器不算相关。 |

`tests/test_praxist_fm_evaluator.py:23-28` 用 `diracc=0.54`（IC=0.08）断言过门，**没有**显式断言「IC=2×|DirAcc−0.5|」也没有「EV<0 仍过布尔门」。合同靠磁盘锁住，单测没锁住。

**绝对值含义：** `i_oi` dir_acc=0.467 **低于随机**，IC=0.066 仍过硬门。公式把「反着做也有信息」算进 IC；亏钱要靠 EV 层拦。这是设计，不是实现错误。

### 1.4 MaxDD：名义 vs 保证金 / stride=12

| 口径 | 公式 | 写入 | 覆盖 |
|------|------|------|------|
| **名义 MaxDD** | `r_t=net/base`，`equity=cumprod(1+r)`，`DD=(eq-peak)/peak`，下限 −1 | verdict `maxdd` ← `summarize.max_dd` ← `calc_net_metrics` L121–137 | 26/26 |
| **MaxDD_legacy** | `cumsum` + `(|peak|+1)` 分母 | 只在秤里，verdict 不写 | — |
| **保证金 MaxDD** | SPEC-008：`stride = horizon // step = 12` 组不重叠子序列，12% 保证金、30% 资金占用，平均 MaxDD | verdict `margin_maxdd` ← `aligned_slow_loop.py:102-113` ← `calc_margin_maxdd_robust` L278–340 | **仅最近 3 行**（2026-09-11） |

`docs/system_design.md:515-531` 名义复利公式与活代码同构。

**缺口：**

1. `aligned_slow_loop.py:105` 把 `p["pnl"]` 传给参数名 `net_pnl_pts`。`monthly_backtest.py:355` 的 `pnl = position_sign * delta_real` 是 **毛 PnL，未扣滑点**。名义 MaxDD 走净盈亏。两套 MaxDD 成本口径不一致。
2. `position_sign` 与 `sign(delta_pred)` 在 `signal_contract.py:71-72, 86` 同源（都是 `sign(weighted-base)`），方向本身不打架。
3. 旧 23 行 verdict 的 `n_eff` / `margin_maxdd` 为 null。G5「同时输出名义+保证金」只对 09-11 之后的慢环生效。
4. 名义 MaxDD 不进 `gate()`。`i_oi` maxdd=−81.67%、`m_ccl` maxdd=−82.88% 仍 `gate_pass=true`。system_design 「> −40%」只是建议。

`tests/test_evaluation_metrics_contract.py` 锁住名义 MaxDD 复利与 −100% 下限；`tests/test_system_hardening.py::TestSPEC008MarginMaxDD` 锁住 stride 函数本身。没有测试断言慢环传入的是净 PnL。

### 1.5 其它秤字段

- **WinRate**：仅 `dirs != 0`（L150–154）。
- **n**：`len(net)` 含空仓；**n_dir**：活跃且价格有动。
- **动态 vs 静态**：`compare_strategies` L208–247 要求 `PF_dyn > PF_static AND EV_dyn > 0`。这是 SCHEMES 固化辅助门，**不是** Praxist `gate_pass`。
- **validation_criteria.md v2**（MAPE/DirAcc/PF + MaxDD 绿通）是 SCHEMES 固化门，Task 1 已标明 ≠ Praxist `gate_pass`。本任务确认：慢环 `gate()` 不读 v2。

---

## 2. gate_pass（矛盾 3）

### 2.1 布尔公式（代码）

```
# evaluator.py:199-203
ic = 2 * abs(dir_acc - 0.5)
gate_pass = (n >= 350) and (ic >= 0.05)
```

`build_summary` L163 调用 `gate(s, min_n=350, min_ic=0.05)`。没有 `ev`、没有 PF、没有 MaxDD、没有 `n_eff`。

### 2.2 分层（不要混名）

| 层 | 条件 | 代码 |
|----|------|------|
| **布尔 `gate_pass`** | n≥350 且 IC≥0.05 | `evaluator.gate` |
| **经济过门 `pass_variants`** | `gate_pass and ev>0` | `registry_lib.py:39-45` |
| **最终裁决 / 目标** | 再加 PF/incumbent>1.05 | `loop-constraints.md:48`；`praxist_goal.yaml` `min(pass_variant_pf_ratios)>1.05` |
| **近失误复测** | gate=False 且仅 n<350，且 ic≥0.05、ev>0、PF 比>1.05 | `praxist_supervisor.py:758-774`（`cj_oi` 原型） |

`config/praxist_task.yaml:19-20` 把 `full_walkforward.gate` 写成 `["n>=350", "ic>=0.05", "ev>0"]`。这是 **最终裁决合同**，`evaluator.gate()` **不解析** 这份 yaml 列表。`scripts/praxist_validate_task.py` 只校验 `objective.primary == ev_after_slippage`。

`docs/system_design.md:537-544` 伪代码 `return (n>=350) and (ic>=0.05) and (ev>0)` 并把函数名叫 `gate_pass`——**与活布尔同名不同义**。

`docs/praxist.md:91-95` 把三条都列成「硬门」，同页 L115 又承认「硬门只判 n+ic」。文档自相矛盾；代码站在 n+ic。

### 2.3 磁盘验证（26 行）

`task_FM/config/aligned_verdicts.jsonl` 共 26 行。`gate_pass` 与 `n>=350 and ic>=0.05` **逐行一致**。

抽查合同要求的四行 + 09-11 新增亏钱过门：

| variant | n | dir_acc | ic | ev | pf | maxdd | gate_pass | 布尔公式 | 备注 |
|---------|---|---------|----|----|----|-------|-----------|----------|------|
| **ss_vor** | 396 | 0.53 | 0.06 | **+11.06** | 1.123 | −0.3525 | **true** | 过 | 唯一经济过门 |
| **i_oi** | 396 | 0.467 | 0.066 | **−2.46** | 0.818 | −0.8167 | **true** | 过 | 反着做仍有 IC，EV 为负 |
| **m_vor** | 396 | 0.524 | 0.048 | +8.71 | 1.303 | −0.2768 | **false** | 拦 | IC 差 0.002，赚钱也死 |
| **cj_oi** | 324 | 0.54 | 0.08 | +19.46 | 1.133 | −0.6293 | **false** | 拦 | 只差 n；复测原型 |
| **m_ccl** | 396 | 0.544 | 0.088 | **−3.64** | 0.839 | −0.8288 | **true** | 过 | 2026-09-11 又一例亏钱过门 |

`gate_pass=true` 共 **3** 条：`ss_vor`、`i_oi`、`m_ccl`。`pass_variants()`（再要 ev>0）只剩 **ss_vor**。

「亏钱仍过硬门」**仍在**，而且比 `STATE.md` / `docs/praxist.md` 写的 `i_oi` 多了 `m_ccl`。

Peer 提示（`praxist_supervisor.py:484`）把 `gate_pass=True` 说成「already solved, do NOT re-propose」。`i_oi` / `m_ccl` 会被当成已解决。目标统计走 `pass_variants()` 不受影响，但物化给 peer 的名单会误导。交 Task 8 看 materializer。

---

## 3. 采样网格（矛盾 5）

### 3.1 活配置

`config/backtest_config.py:52-57`（git `ee1f176`，2026-09-10，STEP 24→2）：

```
CONTEXT_BARS = 480
CONTEXT_DAYS = 250
HORIZON = 24
HORIZON_DAYS = 22
STEP = 2
EVAL_WINDOW_BARS = 1200
```

`monthly_backtest.py:220-226`：

```
eval_start = max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)
eval_indices = list(range(eval_start, total - HORIZON + 1, STEP))
if max_points is not None:
    eval_indices = eval_indices[:max_points]
```

之后按日线充足性再滤（`min_daily_required = max(CONTEXT_DAYS - HORIZON_DAYS, 100)` = 228）。

### 3.2 理论 n

窗口足够长（`total >= 1680`，使 `eval_start = total-1200 ≥ 480`）且 `max_points` 不截断：

```
len(range(0, 1200 - 24 + 1, 2)) = len(range(0, 1177, 2)) = 589
```

注释 `backtest_config.py:57`「600 点 × STEP=2」漏了 **HORIZON 截尾**（最后 23 根无法形成完整 T+24）。研究文档 Task 4 已标 R9「从未精确成立」。`tests/test_system_hardening.py:14-16` 用 **589** 作为 SPEC-004 名义 n，与网格公式一致。

`n_eff`（Bartlett，ρ=0.9，K=11，VIF≈8.236）：589 → 71；396 → 48。磁盘 09-11 三行 `n_eff=48` 与 `effective_sample_size(396, 24, 2)` 一致。`n_eff` **不进** `gate()`。STEP=2 重叠后，名义 n=350 对应有效样本大约 40 量级——统计功效叙事与硬门名义阈值是两套数。

### 3.3 上限

| 旋钮 | 值 | 作用 |
|------|----|------|
| 硬门阈值 | **n≥350** | `gate()`；不是 396/588/600 |
| `STAGE_POINTS["aligned"]` | `(350, 600)` | `evaluator.py:139-141` max_points 合法区间 |
| `praxist_goal.yaml` `aligned_max_points` | **600** | 慢环入队深度 |
| `_harvest_rows` 缺省 | `cad.get(..., 400)` `praxist_supervisor.py:1292` | goal 有 600 时不触发；goal 缺键会退回 400 |
| 理论网格 | **589** | 见上 |
| 磁盘最高 | **588** | `m_oi` / `eg_nvi` / `eg_ha_body`（日线过滤掉 1 点） |

### 3.4 磁盘 n 分布（26 行）

| n | 条数 | 代表 | 原因 |
|---|------|------|------|
| 396 | 21 | ss_vor, i_oi, m_vor, m_ccl, … | 09-09 及更早：STEP=24 全历史≈396；09-11：`max_points=396` 截断新网格 |
| **588** | 3 | m_oi, eg_nvi, eg_ha_body | STEP=2 + 窗口 1200，`max_points=600` 未截断 |
| 324 | 1 | cj_oi | 短历史 / 日线过滤；近失误 |
| 142 | 1 | sh_nvi | 短历史 |

时间线：

- `ss_vor` decided `2026-09-09T03:56`，**早于** 配置改 STEP 的文件 mtime（09-09 19:24）和 commit `ee1f176`（09-10 06:23）。n=396 是旧网格实现值，即使当时 `max_points=600`。
- `m_oi` decided `2026-09-10T02:41`，文件已改 STEP=2，n=588。
- 09-11 的 `m_ccl` / `sh_*`：`aligned_pending.done.jsonl` 里 `max_points=396`（且 `stage=None`），新网格被 **人工/旧队列行** 截到 396。不是理论 589。

**不要把 396 当现行采样合同，也不要把 600 当已实现 n。** 硬门仍是 350。

### 3.5 evaluator 硬顶

`evaluator.py:139-141`：`aligned: (350, 600)`。注释写「2026-09-09 用户批 500→600」（git `feedf44`）。`validate_candidate` 拒绝 max_points 越界。诊断档 `(1, 6)` 永不过硬门（n≪350）。

---

## 4. 主回测入口是否仍是 monthly_backtest

**是。** 生产 walk-forward 引擎是 `scripts/monthly_backtest.py::run_symbol_backtest`。

- 慢环：`aligned_slow_loop.py:9` `import monthly_backtest as mb`，L75–81 调 `mb.run_symbol_backtest`，L85 `mb.summarize`，L113 `registry_lib.append_verdict`。`loop-constraints.md:16-19`：verdict 唯一写入方是慢环。
- 诊断评估：`task_FM/evaluations/fm_eval/run.py` `do_evaluate` 同样走 `monthly_backtest`（`test_praxist_fm_evaluator.py:43-61` 锁了 live key 别名）。
- CLI：`python scripts/monthly_backtest.py [symbols]`。

其它脚本 **不是** Praxist 裁决入口：

| 脚本 | 角色 |
|------|------|
| `scripts/backtest_1h.py` / `batch_backtest.py` | 文首 DEPRECATED，固化禁用 |
| `scripts/a2_p1_runtime.py` | **复制同一网格公式**（L154–156），LGBM 基线，不写 aligned_verdicts |
| `scripts/covariate_scan_new.py` | `range(CONTEXT_BARS, total-H+1, STEP)`，**无 EVAL_WINDOW 截断** |
| `scripts/backtest_vol_gating.py` | 本地 `STEP=6` |

结论：Praxist 全量 WF **唯一入口**仍是 `monthly_backtest.py`。网格公式有一份生产实现、一份 A2 复制、一份扫描器旧网格。扫描器若被误当固化依据会偏大窗口。

`tests/test_backtest_cutoff.py` 锁的是 cutoff 时间戳（防同日 1H 穿越），不是本任务的门公式。前视归 Task 5。

---

## 5. Findings

### I-01 — Important — `gate_pass` 布尔不含 EV；磁盘亏钱过门（i_oi + m_ccl）

- **文档合同：** `loop-constraints.md:48` 最终裁决含 EV>0；`praxist_task.yaml:20` 把 `ev>0` 写进 full_walkforward gate 列表；`docs/system_design.md:537-544` 把三条件写进名为 `gate_pass` 的函数。
- **代码/磁盘：** `evaluator.py:199-203` 只判 n+ic。`i_oi` ev=−2.46、`m_ccl` ev=−3.64 均为 `gate_pass=true`。`registry_lib.pass_variants` 才是 `gate_pass and ev>0`。
- **建议：** 文档把两扇门改名（例如 `gate_pass` vs `econ_pass`）。更新 STATE / praxist 快照补 `m_ccl`。**不要**在不改 materializer 语义的情况下给 `gate()` 加 EV。Peer 提示「gate_pass=True = already solved」交 Task 8。

### I-02 — Important — `system_design` §7.1 把 IC 写成 Pearson

- **文档合同：** `docs/system_design.md:485` `corr(预测, 实际)`。
- **代码/磁盘：** 秤只有 DirAcc；IC 只在 `evaluator.gate` 与慢环 `setdefault`。26 行 ic 全部是 `2×|dir_acc−0.5|`。
- **建议：** 改 §7.1 公式为 loop-constraints 原文。禁止按 Pearson 去改 `evaluation_metrics.py`。

### I-03 — Important — 保证金 MaxDD 吃的是毛 PnL

- **文档合同：** SPEC-008 / `calc_margin_maxdd_robust(net_pnl_pts=...)`。
- **代码：** `aligned_slow_loop.py:105` 传入 `p["pnl"]` = `position_sign * delta_real`（`monthly_backtest.py:355`），未减滑点。名义 MaxDD 走净。
- **磁盘：** `m_ccl` maxdd=−0.8288 vs margin_maxdd=−0.3067（重叠窗口放大名义回撤，再叠加口径差）。
- **建议：** 慢环传入 `gross - tick*slip`（或从 `calc_net_metrics` 拿逐点 net）。加单测锁「margin 输入含滑点」。不要改 `gate()`。

### I-04 — Important — 注册表混着旧网格 n=396 和新网格 n=588

- **文档合同：** 硬门 n≥350；goal 上限 600。
- **磁盘：** 同一 jsonl：ss_vor 的 396（STEP=24 时代）与 m_oi 的 588（STEP=2）并排；09-11 的 m_ccl 又被 `max_points=396` 截回。跨 variant 比 n / IC 功效不可比。
- **建议：** STATE 写明「396=旧网格或 max_points 截断；588≈现行理论 589」。重跑经济候选（至少 ss_vor）再用新网格。不要把 396 写进新合同。

### I-05 — Important — 单测没锁「EV<0 仍 gate_pass」和 IC 公式本身

- **代码：** `tests/test_praxist_fm_evaluator.py:23-40` 只测 n 不足失败；默认样本 ev=0.9。
- **磁盘：** 合同靠 i_oi / m_ccl 锁住。重构 `gate()` 时单测不会拦住「误加 ev>0」或「改成 Pearson」。
- **建议：** 加两例：`n=380, dir_acc=0.467, ev=-2 → True`；`dir_acc=0.54 → ic==0.08`。本任务不落地。

### M-01 — Minor — 配置注释把理论 n 写成 600

- `backtest_config.py:57`：「600 点 × STEP=2」。活公式是 589。`system_design.md:782-783` 附录数值对（STEP=2 / 1200），没写 589。
- **建议：** 注释改成 `len(range(0, EVAL_WINDOW-HORIZON+1, STEP)) = 589`。

### M-02 — Minor — `docs/AGENTS.md` EV 单位注记过时

- L52–54 仍说 stdout 打印 `EV=` 其实是 EV_ratio。`monthly_backtest.py:937-939` 已打印 `EV_ratio=`。
- **建议：** 改成「stdout 打印 `EV_ratio=`；verdict/`evaluation_metrics["EV"]` 是价格点」。

### M-03 — Minor — harvest 缺省 400 vs goal 600

- `praxist_supervisor.py:1292` `cad.get("aligned_max_points", 400)`；函数签名默认 600。goal 现为 600，活路径安全。goal 缺键会入队 400。Task 4 R3 已记。
- 09-11 队列行 `max_points=396` 来自 done 文件（stage=None），不是这两个默认值。

### M-04 — Minor — `n_eff` 只记录、不进门

- SPEC-004 与 `aligned_slow_loop.py:99-101` 已写 n_eff。`gate()` 仍用名义 n。重叠 STEP=2 下 n_eff≈n/8.24。
- **建议：** 文档写清「硬门名义 n；n_eff 是诊断」。若要把功效门槛改成 n_eff，那是合同变更，不是漏实现。

### M-05 — Minor — DirAcc 先四舍五入到 3 位再算 IC

- `summarize` L467 `round(DirAcc, 3)` → `gate` / `setdefault ic`。`m_vor` 0.524 → ic=0.048，卡在 0.05 下。未观察到因舍入翻转的过门；边界品种有理论风险。

---

## 6. Task 1 矛盾 2/3/5 回写

| # | Task 1 判定 | Task 7 代码+磁盘 |
|---|-------------|------------------|
| 2 IC Pearson vs 2×\|dir_acc−0.5\| | 矛盾成立，合同站 dir_acc | **证实。** 秤无 Pearson；两处 IC 公式一致；26 行磁盘匹配。 |
| 3 gate_pass 是否含 EV | 同名两扇门 | **证实。** 布尔不含 EV；`pass_variants` 含。i_oi 仍在，并多 m_ccl。 |
| 5 硬门 n 396 vs 600 vs 实际 | 门限不打架，数字打架 | **证实。** 阈值 350；理论 589；磁盘最高 588；396 是旧网格或 max_points 截断。 |

---

## 7. 做得对的地方

- 净指标集中在 `evaluation_metrics.calc_net_metrics`，`summarize` 不再手算 PF/EV/MaxDD/DirAcc。
- IC 公式在 `gate()` 与慢环写入处相同；磁盘可逐行复算。
- `pass_variants()` 已经把经济过门从布尔里拆出来，目标统计不会把 i_oi 算进 `symbols_hit`。
- monthly stdout 已改 `EV_ratio=`，避免和价格点 EV 混名。
- SPEC-004/008 有单测（n_eff=71，stride MaxDD）；名义 MaxDD 复利与 −100% 下限有合同测试。
- 慢环是唯一 verdict 写入方；`monthly_backtest.run_symbol_backtest` 仍是唯一生产 WF 引擎。

---

## 8. 建议（只建议，不落地）

1. 文档：§7.1 IC 改 loop-constraints 原文；§7.3 伪代码改成 n+ic，另写 `econ_pass = gate_pass and ev>0`。yaml 列表标明「最终裁决，非 `evaluator.gate`」。
2. STATE / praxist：补 `m_ccl` 亏钱过门；写清 396/588/589/600。
3. 慢环：保证金 MaxDD 改吃净 PnL。
4. 单测：锁 IC 公式与「EV<0 仍 True」。
5. **不要**给 `gate()` 加 EV>0，除非同步改 peer 提示和 `dead_variants` 语义。

---

## 回传摘要

- **status:** DONE_WITH_CONCERNS
- **path:** `docs/superpowers/reports/2026-09-11-audit/task-7-eval-gates.md`
- **counts:** 磁盘 26 行；`gate_pass=true` 3（ss_vor / i_oi / m_ccl）；经济过门 1（ss_vor）；pytest 65 passed
- **实际 gate_pass 布尔：** `(n >= 350) and (2*|dir_acc-0.5| >= 0.05)`，不含 EV
- **实际 IC：** `2 * abs(dir_acc - 0.5)`（evaluator.py:201 与 aligned_slow_loop.py:96）
- **实际 STEP/n：** STEP=2，EVAL_WINDOW_BARS=1200，理论 n=589，磁盘最高 588，常见旧值/截断 396；硬门阈值仍是 350
