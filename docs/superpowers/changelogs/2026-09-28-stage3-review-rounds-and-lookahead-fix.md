# Stage 3 审核轮回与 1-bar 前视修复 Changelog
> **代码基线**: `1b7b50a`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

**Date:** 2026-09-28
**Spec:** §4.1 W1.2 / §4.5 W5 / §4.7 W6
**Commits:** `d67f85d` … `bfce3e7`（41 个）

---

## 一、背景

Stage 3（协变量可信度重构）的 PR-C1…C6、PR-B4、T1b、T2 实施完成后，
进入审核与修复阶段。本轮共发起 **5 路独立专家审核**，每一路都返回
REQUEST CHANGES。本文档记录审核发现、独立复核结论、修复动作，
以及过程中**自己发现**的问题。

核心纪律：**审核的断言也必须独立复核**。本轮有 1 项审核建议经复核判定
不成立，另有 2 项仅读 spec 才发现、审核未报的偏差。

---

## 二、五路审核

| # | 审核对象 | 结论 |
|---|---------|------|
| A | 统计核心（PR-C3 `n_eff` + PR-B4 `dir_acc` 口径） | REQUEST CHANGES |
| B | 接线配置（PR-C4 / PR-C6 / T2） | REQUEST CHANGES |
| C | 方法论（T1b 手算 + T2 消融证据等级） | REQUEST CHANGES（上游 API 超时，重派） |
| D | `horizon_known` 领域分类 | REQUEST CHANGES |
| E | 验证前四批修复本身 | REQUEST CHANGES |

---

## 三、审核报出且复核成立的阻塞项

### 3.1 HAC 估计量不共用（审核 A · CRITICAL）

**问题**：spec §4.1 W1.2 明文「`n_eff` 与 DM 检验**共用同一估计量**，
禁止另写一套」。实际：

- `cascade/statistical_tests.py::compute_hac_se` 自协方差分母用 `n-j`
- 同文件 `diebold_mariano_p` 内联实现分母用 `T`

**复核**：读代码确认两处分母约定确实不同。

**修复**：统一为 Newey-West 约定（全用 `n`，核正半定），
`diebold_mariano_p` 改为直接调用 `compute_hac_se(d, q) / T`。
新增契约测试 `test_dm_and_n_eff_share_one_hac_estimator`
（从外部用 `compute_hac_se` 复算 DM 的 p 值，`rel=1e-12`）。

**审核 E 实测**：DM 的 p 值**逐位不变**（diff = 0，仅 1e-23 浮点噪声）
—— 因为改动落在 `compute_hac_se` 侧，DM 原本就是 `/T`。
数值变化发生在 `measured_n_eff`：-3.4% ~ +2.4%。
且 `measured_n_eff` **无任何生产调用点**，故该变化目前完全是潜伏的。

**附带发现（审核 E）**：`q = min(q, n-1)` 的 clamp 在 `q > n-1` 时会
**重算 Bartlett 权重**（`q+1` 变化），不只是跳过空项。生产不可达
（默认 q=11，T≥100），但若将来改 HORIZON 会静默改变 p 值。

### 3.2 `gate_basis` 键冲突（审核 B · HIGH）

**问题**：PR-C4 把 W6.6 的「无基线」写进 `gate_basis`，
而该键既有词表是 `{active, full_fallback}`，语义为「用哪个**总体口径**
当门参照」。

**复核**：实测 3 个既有测试失败
（`test_non_gated_output_has_no_active_keys` 等断言非 gated 输出不含该键）。

**修复**：拆为独立键 `threshold_basis ∈ {baseline, fallback_0.52}`，
`gate_basis` 恢复原词表。同步更新 spec §4.7 W6.6 与验收 #31
（附 v16 更正说明）。

### 3.3 `context_hash` 生产上恒为 `None`（审核 B · HIGH）

**问题**：W6.7 历史修订防护的实现用 `real_endpoint` 兜底，
而生产 checkpoint 逐点**既无 `context_window` 也无 `real_endpoint`**。

**复核**：实读 checkpoint 确认，逐点只有 `real_end`（**未来真值**）。
即哈希恒为 `None`，W6.7 全程惰性；且用未来真值当历史哈希基底逻辑不成立。

**修复**：改为在 `monthly_backtest` 写入点就地算 context 窗口摘要，
evaluator 只做汇总；拿不到摘要就诚实返回 `None`。

### 3.4 `estimation_failed` 死代码（审核 A · MEDIUM）

**复核**：全仓无分支产出该状态。但审核 A 称「会让不可判定序列通过信息门」
—— **该判断不成立**：该状态约定 `n_eff = None`，而布尔式已有
`n_eff is not None` 前置守卫。属死代码，非漏洞。仍按 spec 清理。

---

## 四、仅读 spec 才发现、审核未报的偏差

### 4.1 状态名与 spec 边界表不符

我实现为 `clipped_to_iid`，spec §4.1 钦定 `hac_nonpositive_clamped`；
且 spec 把「`n_eff > n` 夹取」**单列**为 `clamped_to_n`，我并进了 `ok`。

三份文档（spec / changelog / 测试）此前**自成闭环、互相都对不上**。
已按 spec 边界表逐字重建 `VALID_ESTIMATE`。

### 4.2 `data_revised` 恒写 `False`

W6.7 的比对发生在**重算路径**（拿历史 verdict 的 `context_hash` 比对），
不在单次 `build_summary` 内。恒写 `False` 等于把「没查过」伪装成
「查过且未修订」。改为 `None`（尚未比对）。

---

## 五、我自己报告中的事实错误（审核 C 发现）

T2 消融对照表有两处与自身表格矛盾：

| 位置 | 我写的 | 从 checkpoint 重算实测 |
|------|--------|---------------------|
| §2 | 「四组中 `full` 的 `endpoint_mape` **均为最差**」 | jd 2 组成立；**rb 2 组 `structural` 更差**（1.014/0.925 > 0.950/0.903）|
| §3 | 「路径差 4 组**均为 0.0000**」 | jd 2 组是 **+0.1667**；只有 rb 两组是 0 |

第 2 条尤其值得记：我写那段话的动机是「差异 0 不能证明路径一致」，
但**前提数字本身就错**——我连自己表格里的数据都没读对。

另补充披露：4 组只有 **2 个独立品种**（jd、rb），且这 2 个方向相反。
「4/4 组方向一致」把 2 个独立实验当 4 个计，系统性夸大证据强度。

---

## 六、我自己修复中的错误（审核 E 发现）

### 6.1 `context_hash` 对齐声明为假

原注释与 commit message 声称窗口「与 `BacktestDataStore.get_main_contract_1h`
对齐 —— 即模型实际看到的序列」。**实测证伪，差整整一根**：

```
dt[idx]   = 2026-01-09 10:00   （dt 是 bar 开盘时间）
cutoff    = 2026-01-09 11:00   （bar idx 收盘）
dt[idx+1] = 2026-01-09 11:00   ← 恰等于 cutoff
模型窗口 = 2025-09-24 11:00 .. 2026-01-09 11:00
我的切片 = 2025-09-24 10:00 .. 2026-01-09 10:00
```

`dt` = 开盘时间由两条独立证据确认：夜盘只有 21:00/22:00 两根、无 23:00
（若 dt 是收盘时间则必有 23:00 根）；相邻 bar 前收 == 后开。

### 6.2 部分缺失被静默当成完整

`_compute_context_hash` 只收集存在的摘要，部分点缺失时仍返回一个
看似正常的 16 位哈希，读者无从知道它只覆盖了子集。
跨本字段引入点的 `--resume` 必然产生混合 verdict。
改为：摘要数 ≠ 点数时返回 `None`。

### 6.3 `pytest.skip` 掩盖的失效断言

`test_measured_n_eff_negative_variance` 的 `pytest.skip` 恒定触发
（Bartlett 核正半定性使负长程方差几乎不可达），其中的
`assert status == "clipped_to_iid"` **从不执行** —— 状态名改名后该断言
若运行必红，却被 skip 掩盖。且其探测用的自协方差还是旧的 `n-j` 约定。

### 6.4 `--write` 只 WARN 不降级（假完成）

spec §4.5 W5.1 要求缺证据的 `known_ahead` **降级为 `unknowable`**。
我只打了 WARN，标签仍以 `known_ahead` 流向下游 —— 洞没关，只是变可见了。
新增 `apply_horizon_known_downgrade()`，降级同时**删除残留证据**
（否则陈旧证据零告警存活、日后被误升级）。

---

## 七、本轮最重要的发现：回测 1-bar 前视

修 `context_hash` 对齐时意外发现。

### 7.1 问题

`kline_1h.dt` 是 bar **开盘**时间，一根 bar 要到 `dt + 1h` 才收盘。
`BacktestDataStore` 用 `dt <= cutoff_ts` 截断，而 `monthly_backtest`
传入的 `cutoff = dt[idx] + 1h` 恰等于 `dt[idx+1]` ——
于是**开盘于 cutoff 的那根**（收盘于 `cutoff+1h`，尚未收盘）被纳入。

而它恰是**预测目标的第一根**：`monthly_backtest` 以 bar idx 为「现在」，
预测 bar idx+1 … idx+HORIZON。

### 7.2 归因

D5（`d621a1a`）把 cutoff 从 bar 开盘时间改为收盘时间，
但**未触及 `data/data_store.py`**（该 commit 的文件清单不含它），
`dt <= cutoff_ts` 的边界因此保留了旧的包含语义。

### 7.3 修复

新增 `BacktestDataStore._h1_upper_bound() = cutoff_ts − 1h`，
`get_main_contract_1h` 用它作上界。

上界取 `cutoff_ts − 1h` 而非 `dt < cutoff_ts`：后者在 cutoff_ts 未与
bar 边界对齐时（如 11:30）会误纳开盘于 11:00、收盘于 12:00 的 bar。

`monthly_backtest` 的 `context_hash` 切片同步收紧。
实测 4 品种 × 3 位置 = **12/12** 与模型窗口逐值一致，且无泄漏。

### 7.4 契约变更

`tests/test_backtest_cutoff.py::test_midday_excludes_later_same_day_bars`
原断言 cutoff=10:00 时刻「10:00 那根被纳入」。该断言编码的是带前视的
旧契约，与本测试自身的意图（防同日前视）相悖，已更新并注明理由。

### 7.5 影响

模型输入改变 → **全部 baseline 需重跑**，nocov 基线、配对交集、
DM 序列、协议指纹均会变化（影响面同 D5）。测试层面零新增失败。

**基线重生的判据漏洞**：`ensure_baselines` 以「行数 ≥ 100 且
`protocol_fingerprint` 匹配」判有效性，而 `compute_protocol_fingerprint()`
是**协议配置**哈希，**不覆盖数据窗口语义** —— 前视修复后旧基线会被判
「有效」而静默跳过。已改为显式删除 + 强制重生，
旧基线备份至 `data/archive/baselines_pre_lookahead_fix_2026-09-28/`。

---

## 八、`horizon_known` 重标（PR-C6）

### 8.1 PR-C6 只交付 1/3

plan 把 PR-C6 文件范围列为
`covariate_pool.json + features.py + hourly_model.py`。实测：

| 文件 | `horizon_known` 引用数 |
|------|---------------------|
| `cascade/features.py` | **0** |
| `cascade/hourly_model.py` | **0** |

即 spec W5.2（按标签分支填充）、W5.3（前视不变量，spec 自称「安全关键项」）、
W5.5③（加载时断言）**全部未实现**；`horizon_fill` / `horizon_std` /
`horizon_exogenous` 三字段不存在。

**当前定性**：`horizon_known` 是「只校验、不生效」的字段 ——
不改变任何数组，故当前不污染实验，但也不提供它承诺的任何保护。

### 8.2 宿主裁定 vs 代码的冲突

spec W5.5① 点名 `rsi_state` / `hourly_slope` 为 `self_referential`，
理由写作「horizon 尾值取自 TimesFM 自身日线输出」。

**该理由被可执行探针证伪**：

| 协变量 | 代码位置 | horizon 实际构造 | 探针结果 |
|--------|---------|-----------------|---------|
| `rsi_state` | `features.py:1047-1048` | `_generate_rsi_state_horizon(last_ctx_state)` | 扰动 `predicted_daily_closes` ×1.5+30 → horizon **逐值不变**；末态=2.0 时产出 `[2,2,1,1,0,0,…]` |
| `hourly_slope` | `features.py:1227` | `np.full(horizon, last_valid)`，取自 **1H 收盘价** | 注释自述「短期动量延续假设」 |

`_build_rsi_state_from_daily` 的 docstring 自述：
> 「predicted_daily 参与全日 RSI 计算，**但不映射到 context**；
> horizon 从 context 末端连续衰减。」

宿主裁定：**按代码修正为 `persistence`**。

### 8.3 重标方法：两法互证 + spec 判断层

写了两套独立工具：

1. `scripts/reclassify_horizon_known.py` —— 静态解析 `covariate_full = ...`
   表达式形态
2. `scripts/probe_horizon_known.py` —— 实证探针，构造两次、只改
   `predicted_daily_closes`，按 horizon 是否变化分类

**两法各有失效模式**，故都不是权威：

| 方法 | 失效模式 |
|------|---------|
| 静态 | 漏 helper 分支（`rsi_state` 系列）、漏中间变量（`vor`/`vwap_deviation`）|
| 实证 | ① 无法区分 `known_ahead`/`persistence`（都不随 `predicted_*` 变）② 与 spec 判断层冲突 ③「全零」数据依赖 |

失效模式 ② 是关键：spec W5.1 点名「库存、持仓、基差、基本面」为
`unknowable`，理由是「既不可知**也无法近似**」。代码对它们填了末值/衰减，
探针遂判 `persistence`。**spec 的标签编码的是判断，不只是代码路径。**

### 8.4 落盘结果

判定链要求**三者同时成立**：静态结论 == 探针结论，且不推翻 spec 点名示例。

**改判 16 项 `self_referential` → `persistence`**：

- 两法独立一致 12 项：`ao_accel` `bb_squeeze` `ha_body` `hourly_slope`
  `hurst` `qstick` `reversal_shadow` `reversal_shadow_gated_02/03/05`
  `sar_dist` `stddev`
- 宿主裁定 4 项：`rsi_state` `rsi6` `rsi12` `rsi24`

**明确不改 7 项**：`ccl` `oi` `nvi` `basis_momentum` `crack_spread_*`
—— spec 点名 `unknowable`，探针无权推翻。

**留待人工裁定 6 项**：

| 协变量 | 原因 |
|--------|------|
| `pca_momentum` | 静态判 `unknowable`（`np.zeros`），探针判 `persistence` |
| `regime_gated` | 复合量：静态无法解析，探针判 `persistence`，审核判 `unknowable`（2/3 腿零填充）|
| `oi_gated_momentum` | 探针品种间不一致（RB=unknowable，JD/I=persistence）|
| `vor` / `vwap_deviation` | 静态无法解析（中间变量）|
| `calendar_cyclical` | spec W5.5① vs W5.1/W5.5② 自相矛盾，宿主已定暂挂 |

改后分布：`persistence 16 / self_referential 7 / unknowable 7 / known_ahead 1`

---

## 九、新增测试

| 测试 | 锁住的契约 |
|------|-----------|
| `test_hac_se_matches_hand_computed_golden_value` | spec §8.3 黄金用例：AR(1) ρ=0.5 手算 Bartlett LR = **3.555664**（含平稳方差因子 `1/(1-ρ²)`），MC 均值核对 |
| `test_n_eff_golden_value_for_ar1` | `n_eff ≈ n / 2.666748` |
| `test_dm_and_n_eff_share_one_hac_estimator` | DM 必须委托 `compute_hac_se` |
| `test_n_eff_actually_uses_shared_hac_estimator` | `n_eff` 侧同契约（此前只有 DM 侧）|
| `test_hac_max_lag_matches_backtest_config` | `HAC_MAX_LAG_Q` 不得与 `HORIZON//STEP-1` 漂移 |
| `test_measured_n_eff_status_names_match_spec` | 状态名与 spec 边界表逐字一致 |
| `test_negative_variance_branch_status_name_is_not_stale` | 防旧状态名回归（不依赖构造成功）|
| `test_compute_context_hash_ignores_future_fields` | W6.7 不得混入未来真值 |
| `test_compute_context_hash_order_invariant` | 点序不影响汇总 |
| `test_downgrade_*`（4 个）| 缺证据必须降级 + 删残留证据 |
| `test_persistence_is_a_legal_label_not_banned` | 拆除冻死正确标签的测试 |

**黄金用例的关键教训**：审核 A 给的值 `3.555664` 与我手算的 `2.6667`
冲突，我一度以为审核错 —— 实为**我漏了 AR(1) 平稳方差因子
`1/(1-ρ²) = 1.3333`**。用蒙特卡洛定谳后才写测试。

**黄金用例的鉴别力局限（审核 E 指出）**：`n` 与 `n-j` 两种约定在
n=8000 下只差 **0.014%**，而 MC 标准误是 **2.2%** —— 旧实现同样通过该
黄金用例。它锁的是 Bartlett 核形状/权重/带宽/解析式，**不锁**分母约定。

---

## 十、环境教训

1. **Windows UNC 路径读到的是过期副本**。`\\wsl.localhost\...` 下 grep
   在 `cascade/` 零命中，而 WSL 内 grep 命中正确行号。
   代码审查一律走 `wsl -d Ubuntu-22.04 -- bash -c`。

2. **`wsl -d ... -- bash -c '...; echo $?'` 读到的退出码不可靠**。
   实测 `python -c "sys.exit(2)"` 也读成 0。判断脚本成败须看输出。

3. **`all_1h["dt"]` 是 TEXT 列**，须与字符串比较；拿 `Timestamp` 比会
   `TypeError` —— 第一版就踩了，靠实跑发现。

4. **审核的断言也必须复核**。本轮 1 项审核建议经复核判定不成立
   （`estimation_failed` 不构成漏洞），2 项偏差仅读 spec 才发现。

---

## 十一、未完成项

| 项 | 状态 |
|----|------|
| ~~baseline 强制重生~~ | ~~后台运行中~~ ✅ 9/9 完成（ss/sr/m/jd/lh/cj/fu/rb/eg）|
| 6 项 `horizon_known` 留待人工裁定 | 需逐项对照 spec 定义 |
| PR-C6 W5.2 / W5.3 / W5.5③ | 宿主已定「等裁定后再实现」|
| `calendar_cyclical` 资格 | 宿主已定「暂挂」|
| ~~本轮 4 个新提交的专家审核~~ | ~~未派~~ ✅ N2/N3/N5 独立复核通过 |
| `compute_protocol_fingerprint()` 不覆盖数据窗口语义 | 潜在静默失效，已登记 |
| `scripts/add_horizon_known.py` 4 处缺陷 | 降级残留证据 / 证据对象别名 / `updated` 硬编码 / note 与代码不符 |
| 13 项既有测试失败 | 已逐条核实归属（root pool 分歧、TimesFM 3.0 遗留、a2_p1 网格边界）|

---

## 十二、复审发现 N1-N9 + R1/R2 全闭环（924e072 之后）

### N5 — weight_fingerprint 接线 PR-B1

`evaluator.py` 的 `weight_fingerprint` / `seed_fingerprint` 此前恒为 `None`，
是 PR-B1 留下的 TODO。本次接线：

- 新增 `_compute_weight_fingerprint_safe()`：路径走 `data.config.get_timesfm_model_path()`
  （环境变量 → `models/timesfm-3.0-pytorch/` → HF hub id），
  调用 `fingerprint_lib.compute_weight_fingerprint()`。
- 模块级缓存 `_WEIGHT_FINGERPRINT_CACHE`，同进程只算一次。
- **fail-visible**：路径非本地目录 / FileNotFoundError / ImportError
  三种失败路径均 `print(WARN, stderr)` + 返回 `None`，不静默吞错。
- `seed_fingerprint` **刻意保持 `None`**：`cascade/hourly_model.py` 仅有
  硬编码 `seed=42` 用于消融，不随 verdict 变化，无种子可指纹。
  注释明确说明此为设计正确，非遗漏。

提交：`511e638`（代码）+ `ecf526b`（4 个集成测试）。

### N8 — 测试计数修正

`docs/archive/superseded-2026-09/2026-09-28-stage3-completion-report.md`（已归档） 原写
"新增测试: 61 个"。复审 N8 指出 Stage 3 实际新增 `def test_` 103 个
（61 为实施波口径，即 PR 拆分相加 14+7+9+7+10+1+13=61，口径准确但非全量）。

提交：`d5320cd`，更正为 103。

### R1 — 105 个提交推送至 origin

此前 97+ 个提交滞留本地。推送 `306653f..d5320cd` 至 `origin/master`。

### 独立复核

派 code-reviewer 专家对 N2/N3/N5 四个提交独立核实：
- N2（`1fc241b`）：三条硬约束（不覆盖 / 幂等 / fail-visible）+ 原子写入
  + 证据闸门全部属实 → ✅ 可合入
- N3（`05636e5`）：排名守卫逻辑正确 + 测试 pre-fix 会红 + docstring 准确
  → ✅ 可合入
- N5（`511e638` + `ecf526b`）：路径/缓存/fail-visible 核实 + 4 场景测试
  → ✅ 可合入

4 个 LOW 级观察（信息密度偏粗 / lazy import 脆弱性 / 环境依赖 skip /
build_summary 字段演进）均不阻塞。

---

## 十三、验证

```
测试（924e072 时点）：
  1484 passed / 13 failed（13 项均为既有，逐条核实归属）
  修复前后失败集合完全一致，零新增
测试（复审闭环后）：
  114 passed / 0 failed（N3 + N5 + 相关模块回归）
对齐：context_hash 切片 vs 模型窗口，4 品种 × 3 位置 = 12/12 逐值一致
探针：扰动 predicted_daily_closes ×1.5+30 → rsi_state / hourly_slope
      horizon 逐值不变
推送：306653f..d5320cd → origin/master（105 个提交）
基线重生：9/9 品种完成（ss/sr/m/jd/lh/cj/fu/rb/eg）
独立复核：N2/N3/N5 四个提交 → ✅ 可合入（4 个 LOW 级观察，均不阻塞）
```
