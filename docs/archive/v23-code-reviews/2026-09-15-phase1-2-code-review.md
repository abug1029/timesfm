# Phase 1–2 专家代码审核报告

- **日期**: 2026-09-15
- **对象**: WSL `/home/abug/timesfm` 分支 `feat/prediction-quality-redesign-v23`
- **范围**: `e22db35..4dabd95`（Task 1–6，8 个 commit，7 个文件 +884 行）
- **对照**:
  - 设计: `D:\FlyBuddy\docs\2026-09-14-prediction-quality-redesign-design.md`
  - 实施计划: `D:\FlyBuddy\timesfm\docs\superpowers\plans\2026-09-15-prediction-quality-redesign.md`
  - 执行日志: `D:\FlyBuddy\docs\superpowers\CHANGELOG-Phase1-2.md`
- **审核人**: 独立审核（对照 WSL 未提交工作区 + 已提交 diff + 复算）
- **结论**: **不建议合入。Task 7（registry）可以开；Task 8 必须传入真实 `STEP=2`；Task 9 之前必须先修 DM 和 FDR。**

---

## 0. 审核边界（先把现场说清楚）

### 0.1 两份 timesfm 不是同一棵树

| 位置 | Git | Phase 1–2 代码 |
|------|-----|----------------|
| WSL `/home/abug/timesfm` | 有，当前分支 `feat/prediction-quality-redesign-v23` | **有**（审核对象） |
| Windows `D:\FlyBuddy\timesfm` | **不是 git 仓库** | **没有** `statistical_tests.py` / `cov_family.py` |

计划里写 `STEP=24`，是对着 Windows 那份旧树读出来的。WSL 生产树已经是重叠抽样：

```
config/backtest_config.py
HORIZON = 24
STEP    = 2    # 每天评估约 3 次
EVAL_WINDOW_BARS = 1200  # 理论 n ≈ 589
```

`scripts/monthly_backtest.py` 的 `eval_indices` 用的就是这个 `STEP=2`。规格示例 `step=2` 反而和 WSL 真实回测一致；实施计划默认 `24/24` 和实现默认值都跟错了树。

### 0.2 工作区脏文件不属于 Phase 1–2

`git status` 里还有 48 个已跟踪改动（`praxist_goal.yaml` 仍是 `ev>0` + PF ratio、一堆 shell 路径、`task.yaml` 等）和若干未跟踪备份。它们 **不在** `e22db35..4dabd95` 里。本报告不把它们算进 Task 1–6 的对错，但它们是合入风险：下一轮 commit 很容易混进去。`praxist_goal.yaml` 未提交稿里还有 `run_budget_hour`（少了 s），那是另一条线的问题。

### 0.3 变更日志不能当审核

`CHANGELOG-Phase1-2.md` 写「状态：代码审核通过」「6/6 PASS」，文末又写「审核人：待指定」。这是执行者自报完成，不是独立审核。下文会逐条对日志里不实的句子。

### 0.4 测试我这边复跑过

```
cd /home/abug/timesfm
.venv/bin/python -m pytest tests/test_evaluation_metrics.py \
  tests/test_statistical_tests.py tests/test_cov_family.py \
  tests/test_evaluation_metrics_contract.py tests/test_vol_scaled_mae.py -q
# 58 passed in 2.54s
```

测试绿只说明「测了的断言成立」，不说明规格成立。下面几条都是测试没覆盖、实现却会错的路径。

---

## 1. 总评

Task 1–2（指标函数）和 Task 3 的 Inner Join **可以继续给 Task 7–8 用**。`calc_net_metrics` 没有被删，旧契约测试仍绿。

Task 4（DM）和 Task 5（BH-FDR）**相对规格未过关**，而且会改变晋级结果：

1. 方差退化时打出 `p=0.0`（规格要求保守 `1.0`）。
2. 未过门变体的小 p 值会把 BH 截断点往后推，让更弱的过门变体搭车。
3. 默认 `horizon=24, step=24` 既不读 `backtest_config`，也和 WSL 真实 `STEP=2` 不一致；`fallback_n_eff` 默认会把 588 点当成 588 个有效样本，而重叠抽样下应约为 73。

这三项不修，后面的 Supervisor FDR 结算是错的。

**Ready to merge:** No  
**Ready for Task 7:** Yes  
**Ready for Task 8:** Yes，但 `fallback_n_eff(n, HORIZON, STEP)` 必须显式传入 WSL 的 `STEP=2`  
**Ready for Task 9+:** No，先修 DM / FDR

---

## 2. 做得好的地方

- 只追加、不覆盖：`calc_net_metrics` / `metrics_from_backtest_points` / `compare_strategies` / `calc_vol_scaled_mae` 都还在。
- `safe_path_corr` 七层防护和规格一致；完全线性相关把断言改成 `<= 1.0` 是对的。
- `calc_prediction_quality`：零变动 `dir_ok=False`、端点 MAPE 分母 `max(base, 1.0)`、全平 `weighted_dir_acc=0.5`、返回 9 键且不含 `p_value`，符合计划。
- `pair_dir_ok_series`：Inner Join、按时间升序、后写覆盖，tuple/dict 都能吃，边界测试够用。
- `bh_fdr_promote` **没有改入参**（`fdr_pass` 不会写回原 dict），`variant_id` 后写覆盖也对。
- 协变量短词用 lookaround 而不是 Python `\b`，能挡住 `point` / `evolve` / `cabbage` 这类误匹配。
- DM 单测用了构造配对序列，没有用独立二项分布去赌 `p<0.05`。

---

## 3. 问题（按严重程度）

### 3.1 Critical — 必须在进 Task 9 之前修

#### C1. `diebold_mariano_p` 方差退化时返回 `p=0.0`

- **文件**: `cascade/statistical_tests.py` 约 197–202 行
- **现状**:

```python
if V <= 1e-12:
    if d_bar < -1e-12:
        return 0.0   # 实现：当作完美显著
    return 1.0
```

- **规格 / 计划**: `V <= 1e-12` 视为没有统计信息，**必须返回 1.0**，杜绝伪显著 `p=0`。
- **复算**（WSL，当前实现）:

| 输入 | 实现 p 值 | 规格应给出 |
|------|-----------|------------|
| 200 个 1 vs 200 个 0 | **0.0** | **1.0** |
| 相同序列 | 1.0 | 1.0（这条对） |

`test_diebold_mariano_p_clear_improvement` 用的就是「全 1 vs 全 0」这种零方差序列，断言 `p < 0.01`，等于把规格禁止的行为测成了正确。

- **为何严重**: `p=0` 的变体在 BH-FDR 里排第一，几乎一定 `fdr_pass=True`。HAC 用 `np.mean`（`/(T-j)`）时，Bartlett 核不一定半正定，V 可能数值上变成 0，不一定只有「全对打全错」才踩中。
- **修法**: 按规格 §4.2.2 重写：`d = v_ok - b_ok`；`d_bar<=0 → 1.0`；`gamma[j] = sum(...)/T`；`V/=T`；**`if V<=1e-12: return 1.0`**。删掉 `return 0.0`。换掉零方差的「显著改善」测试：一半点变体更好、一半打平。另加一条：常数差必须 `== 1.0`。

#### C2. `bh_fdr_promote` 未过门变体没有在排序时把 p 当成 1.0

- **文件**: `cascade/statistical_tests.py` 约 261–263、287–290 行
- **现状**: `safe_p` 只用真实 `p_value`；最后才 `fdr_pass = gate_pass and (i <= max_pass_idx)`。
- **规格**: `gate_pass=False` 时 **排序前** `safe_p=1.0`，仍计入 `K`，避免选择偏差，也避免它们把截断点 `k*` 往后推。
- **复算**（K=4, q=0.10）:

```
fail_tiny  p=0.001  gate=False
ok_med     p=0.04   gate=True
c          p=0.20   gate=True
d          p=0.20   gate=True
```

| 算法 | `ok_med` |
|------|----------|
| 当前实现 | **True**（被 fail 的小 p 抬了截断点） |
| 规格（fail 的 safe_p=1.0） | **False**（`k*=0`） |

现有 `test_bh_fdr_gate_fail_never_passes` 只断言 fail 自己不过，测不出污染。

- **修法**: 与规格 §4.2.3 一致，未过门 `safe_p=1.0` 再排序。补上上面这条污染用例。

---

### 3.2 Important — 应修，否则 Task 8/9 会把错默认值焊进管道

#### I1. DM 不是规格里的 Newey-West + HLN；默认 step 和真实抽样相反

`cascade/statistical_tests.py` 约 128–210 行，对照 `config/backtest_config.py` 第 55 行。

| 项 | 规格 §4.2.2 | 实现 |
|----|-------------|------|
| 差分 | `d = v_ok - b_ok`（越大越好） | `loss=1-ok` 再相减（符号相反，靠 `-dm_adj` 把 p 值翻回来） |
| 滞后阶 | `q = max(1, horizon//step - 1)`；WSL 真实 step=2 → **q=11** | `h = horizon//step`；默认 step=24 → **只算 lag 0** |
| γ | `sum / T`（半正定） | `np.mean` = `/(T-j)` |
| HLN | `k_hln = sqrt((T+1-2h+h(h-1)/T)/T)`，`dm_adj = dm * k_hln` | **没有 HLN**，`dm_adj = d_bar/sqrt(V)` |
| 单侧 p | `t.sf(dm_adj, T-1)` | `t.sf(-dm_adj, T-1)` |

变更日志写「HLN 统计量正确」「Newey-West `/T` 归一化」——前一句是假的，后一句只做了一半。

计划把默认写成 24/24，是因为读了 Windows 旧树。实现跟了计划，没读 `backtest_config`。后果：

- `fallback_n_eff(588)` 默认得到 **588**，重叠抽样下规格公式应约为 **73**。
- `n_eff >= 50` 的硬门在默认路径上等于没设。
- Task 9 若按规格片段 `diebold_mariano_p(paired_v, paired_b)` 不传 step，HAC 会按非重叠来算。

**修法**: 函数体按 §4.2.2；默认值从 `config.backtest_config` 读 `HORIZON`/`STEP`（WSL 现在是 24/2），或强制调用方传入、禁止静默默认 24。

说明：实施计划「禁止抄 step=2」这条，对 **WSL 这棵树是错的**。以 WSL 生产配置为准，不要再把 Windows 旧树的 `STEP=24` 写进后续任务。

#### I2. `safe_normalize_cutoff` 不吃 `pd.Timestamp` / `datetime`

- **文件**: `cascade/statistical_tests.py` 约 31–69 行
- **规格 §9.4**: 用 `pd.Timestamp`，时区 naive→上海、aware→`tz_convert`。
- **复算**: `safe_normalize_cutoff(pd.Timestamp("2024-06-15 09:00:00"))` → **`None`**；`datetime(...)` 同样 `None`。
- **后果**: Inner Join 静默丢点；配对不足 100 就把 `p_value=None`，整批无法晋级。checkpoint / pandas 回测很可能会给 Timestamp，不是纯字符串。
- **另**: 字符串先 `float(ts)`，`"20240615"` 会变成 unix `20240615`（1970 年某天）。规格要求 `isdigit` 且长度 ≥ 9 才当 unix。毫秒阈值规格是 `> 1e11`，实现是 `> 1e12`（2024 年毫秒时间戳两者都能过，边角才有差）。

**修法**: 按 §9.4 用 pandas；补 Timestamp / datetime 用例。

#### I3. `resolve_cov_family` 的池格式测试是假绿；启发式词表和规格 §9.3 不一致

- `tests/test_cov_family.py` 的 `test_pool_format_pool_key` 传入 `{"pool": [{"name": "test_atr", "family": "volatility"}]}`。`resolve_cov_family` 只读 `covariates`，Level 1 是空的，靠 Level 2 的 `"atr"` 才绿。
- 复算：`{"pool": [{"name": "custom_x", "family": "calendar"}]}` → **`"unknown"`**。
- 空池下 `roc_x` / `ema_cross` / `holiday` / `spread_x` 全是 `"unknown"`（规格 §9.3 能命中）。

**修法**: Level 1 兼容 `covariates` / `pool` / list（与 `load_covariate_pool` 一致）；启发式以 §9.3 为底，再保留 lookaround。测试要用启发式匹配不到的名字来验证池键。

#### I4. `calc_prediction_quality` 路径条数少于端点时会 `IndexError`

端点长度有 `ValueError`，路径循环 `for i in range(n): p_paths[i]` 没有同样检查。Task 8 若漏字段会在慢环里炸，而不是墓碑友好的错误。

---

### 3.3 Minor

- `statistical_tests.py` 在函数中间才 `from scipy.stats import t`；测试文件也在中段 import。能跑，不干净。
- 参数名叫 `variant_losses`，文档又说传入 `dir_ok` 再内部 `1-x`。Task 9 若按名字再转一次 loss，检验会反号。应改回规格名 `variant_dir_ok_list`。
- 缺 `symbol` 时分组键用 `"unknown"`，规格是 `"default"`。
- `fallback_n_eff` / `diebold_mariano_p` 没有从 `backtest_config` 读常量。
- 脏工作区不要和 Phase 1–2 的修丁混提交。

---

## 4. 变更日志 vs 代码

| 日志说法 | 实际 |
|----------|------|
| Task 4「HLN 统计量正确」 | **没有** Harvey–Leybourne–Newbold 因子 |
| Task 4「Newey-West `/T` 归一化」 | `V/=T` 有，γ 用了 `np.mean`=`/(T-j)` |
| Task 4「`V<=1e-12` 且更好 → `p=0.0` 完美显著」 | 与规格「杜绝伪显著 p=0」**相反**，还写成了设计决策 |
| Task 4「Loss 转换正确」 | 规格是 `d = v_ok - b_ok`，没有 loss 转换 |
| Task 5「BH-FDR 算法正确」 | 未过门变体没有在排序时 `safe_p=1.0` |
| Task 6 `pool` 键测试 | 假绿，靠 `"atr"` 启发式 |
| 「6/6 PASS」「代码审核通过」 | 自我审核；Task 4–5 规格未过 |
| 「34 个测试」 | 本阶段相关 pytest 一共 58（含旧契约）；新测试大约 47 |
| 「审核人: 待指定」同时又写 APPROVE | 自相矛盾 |

Task 1–2 的功能描述基本属实。`calc_net_metrics` 未删、58 测试绿，这两点没写错。

---

## 5. 建议的修复顺序（不要和 Task 7 搅在一起）

1. **重写 `diebold_mariano_p`**（C1 + I1）：规格差分、γ/`T`、q、HLN、`V<=1e-12 → 1.0`；默认跟 `backtest_config`（24/2）。
2. **改 `bh_fdr_promote` 的 `safe_p`**（C2）+ 污染测试。
3. **时间戳走 pandas**（I2）+ Timestamp 用例。
4. **协变量家族 Level 1 真正吃 `pool`/list**（I3）+ 修假绿测试。
5. 路径长度校验（I4）。
6. 把 changelog 里的 APPROVE 拿掉，或在本文档之后加一节「已按审核返工」。
7. 脏工作区 `stash` 或另开分支，再提修丁。

Task 7（registry 原子写）不依赖 DM/FDR，可以并行。Task 8 可以开，但 `n_eff` 必须 `fallback_n_eff(n, HORIZON, STEP)` 且 `STEP` 来自 WSL 配置。Task 9 不要在 1–2 修好前开工。

---

## 6. 已核对、确认干净的部分

- `safe_path_corr` 行为与规格一致。
- `calc_prediction_quality` 的 dir_ok / MAPE 地板 / weighted 回退 / 9 键契约。
- `fallback_n_eff` 公式本身（在传入正确 `step` 时）与规格 Bartlett 一致；错的是默认参数，不是公式。
- `pair_dir_ok_series` Inner Join 与排序。
- `bh_fdr_promote` 不修改入参、后写去重、小批次 Bonferroni 阈值 0.025、按品种分组。
- 旧 `calc_net_metrics` 契约测试未回归。

未能评估：真实 588 点 walk-forward 上的 DM 功效（本阶段没有夹具，也不该在修公式前跑）。

---

## 7. 对执行日志「待审核项」的勾选建议

| 项 | 本报告判定 |
|----|------------|
| Phase 1–2 代码实现 | 部分完成：指标层过关，检验层未过规格 |
| 代码审核修复 | 执行者对 Task 3/6 的修补有效；Task 4/5 的「审核通过」作废 |
| 测试覆盖率 | 数量够，关键负面路径（p=0、FDR 污染、Timestamp、pool 键）没测到 |
| 文档完整性 | changelog 有多处与代码/规格不符 |
| 关键设计决策确认 | **不接受**「方差崩了就 p=0」；**不接受**「loss 转换」作为对规格的替代，除非单独改规格并论证 HAC 半正定 |

审核完成。不要把本文件里的 Critical 项带到 Phase 3 的 evaluator / Supervisor。
