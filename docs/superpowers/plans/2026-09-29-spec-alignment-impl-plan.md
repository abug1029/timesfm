# FM_a 对齐 Spec 实施计划（2026-09-29，rev2 — 含第五轮审计 H1-H6 修订 + Q1/Q2 裁定）

## Context

spec `2026-09-24-covariate-research-credibility-design.md`（v15，1586 行）定义了协变量研究可信度重构的完整蓝图，分四个阶段 14 个 PR。经核验（详见 `docs/superpowers/reports/2026-09-29-spec-implementation-audit.md`）：

- **阶段 1（硬门槛）**：基本交付，仅 PR-A5 协议指纹不覆盖数据窗口语义（⚠️）
- **阶段 2（诊断）**：基本交付，PR-B1 variant_id 未接线（⚠️）
- **阶段 3（统计实现）**：PR-C1 / PR-C2 **完全未交付**，PR-C5 / PR-C6 部分交付。**§8.3 出口核验 0/8 交付** —— 这是进入阶段 4 的硬阻塞（spec §8.5 约束 4）
- **阶段 4（预注册、品种分级）**：未实施；目标效应与功效未裁定（spec §8.5 约束 3 阻断 PR-D2）

**关键缺口**：PR-C1 / PR-C2 是 spec §8.3 的主体交付。它们未实现意味着「过门」仍不具备真正的证据含义 —— §1.1 L3 的"让'过门'重新具备证据含义"核心使命尚未闭合。

**本轮计划目标**：闭合阶段 3 出口核验 + 补齐阶段 3 残留项 + 处理已知风险项 + 为阶段 4 做准备。

---

## 关键文件参考

| 文件 | 职责 |
|------|------|
| `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md` | **唯一权威**（spec） |
| `cascade/statistical_tests.py` | 统计公式（HAC / DM / detection_threshold / n_required / family 封账） |
| `cascade/evaluation_metrics.py` | 评估指标（n_eff / dir_acc / meets_min_info） |
| `task_FM/evaluations/fm_eval/evaluator.py` | verdict 构建（build_summary）+ 指纹 |
| `scripts/praxist_supervisor.py` | supervisor + family 注册 |
| `scripts/registry_lib.py` | verdict schema + pass_variants |
| `cascade/features.py` | 协变量构造（需补 horizon_known 分支） |
| `cascade/hourly_model.py` | HourlyResult 字段（需补 horizon_exogenous） |
| `scripts/aligned_slow_loop.py` | verdict 落盘（需补 horizon_exogenous） |
| `task_FM/config/covariate_pool.json` | 协变量配置（horizon_known 分类已存在） |

---

## 阶段划分

按 spec §8.5 硬约束排序：

### Phase 1 — PR-C1（detection_threshold + n_required + 黄金用例）

**目标**：补 spec §8.3 的三个统计公式 + 配套黄金用例。

**文件**：
- `cascade/statistical_tests.py`：新增 `detection_threshold_vs_random(n_eff)`, `detection_threshold_vs_baseline(d_series)`, `n_required(var_d, vif, z_alpha, z_beta, delta)`
- `cascade/evaluation_metrics.py`：在 `build_summary` 消费点落字段
- `task_FM/evaluations/fm_eval/evaluator.py`：`build_summary()` 落 `detection_threshold_vs_random` / `_vs_baseline` / `se_hac` / `delta_ci_lo` / `delta_ci_hi` / `n_required_for_target`
- `scripts/registry_lib.py`：VERDICT_FIELDS_V2 登记新字段

**spec 公式（行号已核实）**：
```
detection_threshold_vs_random  = 0.5 + z_α * 0.5 / sqrt(n_eff)                  # spec 695
detection_threshold_vs_baseline = z_α * SE_HAC(d_bar), d_t = v_ok_t - b_ok_t      # spec 696
n_required = Var(d) * VIF * (z_α + z_β)² / Δ²                                      # spec 711
```

**黄金用例（spec 钦定，必须实现为测试）**：
- `detection_threshold_vs_random`（`n_eff=73`）= **0.596**（spec 1369）
- `detection_threshold_vs_baseline`（`rho=0.5`）= **≈0.096**（spec 1369）
- `n_required`（`Delta=0.02`, `rho=0.5`, 80% 功效）= **≈31,000 ±5%**（spec 1370）
- `detection_threshold_vs_baseline` **不等于** `baseline_dir_acc + 1.645*0.5/sqrt(n_eff)`（spec 1368）

**约束**（spec §8.3 / §4.3 W3.5）：
- 三套公式分别验证（n_eff ESS / DM 标准误 / 功效规划）—— **禁止**一套通过即三套通过
- **不得存在**「长程方差 × VIF」混用路径 —— 须写源码断言测试（spec 1329）
- 黄金用例 docstring 强制字段：带宽约定、均值中心化、样本方差分母、有限样本修正
- 边界用例各一：负自相关 / 常数序列 / 有效样本不足 / 带宽边界
- 重叠预测：实测 HAC vs 名义 VIF 区分 —— 断言名义 VIF 不得用于检验校正

**测试文件**：`tests/test_detection_threshold.py` + `tests/test_n_required.py`

**验收**：
- 黄金值测试全部通过（与 spec 钦定值比对，相对容差 ≤ 1%）
- `n_required` 公式断言 `Var(d) * VIF`（情景近似）与 `Var_LR(d)`（先导估计）二选一，**不**同时
- `detection_threshold_vs_baseline` 与 DM 同源（共用配对 HAC）

---

### Phase 2 — PR-C2（family 定义 + 封账 + T_max + p=1）

**目标**：实现 spec §4.3 W3.6 的多重比较纪律。

**文件**：
- `scripts/praxist_supervisor.py`：新增 family 注册逻辑（`register_family` / `seal_family`）
- `cascade/statistical_tests.py`：追加 `family_bh_fdr(family_id)`（不修改现有函数）
- `scripts/registry_lib.py`：VERDICT_FIELDS_V2 登记 `family_key` / `family_status` / `p_value_family_adjusted`
- 新增 `task_FM/config/preregistry.jsonl` 的 family 字段
- 新增 `docs/family_boundary_rules.md`（跨品种范围声明）

**spec 要求（spec 787-830）**：
- **family 定义**：一个 family = 同一研究问题 + 同一预注册系列内全部确认检验
- **默认**：一品种一 family（同一 protocol_fingerprint 下）
- **只有确认检验进 family**；探索期结果不进
- **封账**：全部成员到达终态（`confirmed`/`refuted`/`abandoned`/`timeout`）时一次性跑 BH-FDR
- **注册截止**（二者并用，先到者为准）：
  - `family_close_at`：默认首成员注册后 90 天
  - `family_max_members`：默认 20
- **T_max**：单成员从注册起算 180 天（spec v7）
- **封账上界**：family 最晚于 `family_close_at + T_max` 封账
- **未完成检验**：family 封账时仍未达终态的成员立即落 `timeout` + `p=1`
- **p=1 适用范围**（spec v5）：仅当假设已进入确认 family 且截止前未完成

**family 键（spec v8）**：
```
family_key = (symbol, research_question)
research_question = (预测目标, 预测任务/期限, research_target_hash)
research_target_hash = hash(品种, 目标变量, 价格序列定义, 复权规则版本, 换月规则版本)
```

**关键约束**：
- `research_target_hash` 只哈希"研究目标本身"，**不含**观测数据内容与截止时间
- 新增 cutoff / 修订历史 bar **不**创建新 family
- `protocol_fingerprint` 中与"研究问题"无关的字段变化（如 cov_fill_version）**不**开启新 family
- 新 family 仅当 `research_question` 三要素任一变化

**测试文件**：`tests/test_family_sealing.py`

**验收**：
- family 注册（确认检验进 / 探索不进）
- `family_close_at` 90 天截止生效
- `family_max_members` 20 上限生效
- 先到者为准
- 全成员终态 → 一次性 BH-FDR
- 未达终态 → `p=1`
- `research_target_hash` 在新增 cutoff 时不变，在换目标变量时变化

---

### Phase 3 — PR-C6 补 W5.2 / W5.3 / W5.5③ 代码路径（宿主已裁定）

**目标**：让 `horizon_known` 标签真正驱动填充策略，不是「只校验、不生效」的字段。

**文件**：
- `cascade/features.py`：
  - 新增 `_get_horizon_known(covariate_type)` 读 `covariate_pool.json`
  - 修改各协变量构造函数的 horizon 段填充，按 `horizon_known` 分支：
    - `known_ahead`：填真实未来值（spec W5.2）
    - 其他三类：填末值（persistence）
  - 加 `horizon_exogenous` 字段：`horizon_known == "known_ahead"` 时 True，否则 False
  - 加加载时断言（W5.5③）：`(horizon_known == "known_ahead") iff (走 known_ahead 填充路径)`
  - **H5 修订**：落盘标记 `horizon_fill` 字段（值为 `"persistence"` 或 `"real_future"`），与已有的 `horizon_flat` 并列
- `cascade/hourly_model.py`：`HourlyResult` 新增 `horizon_exogenous: bool = False`
- `scripts/aligned_slow_loop.py`：verdict 落 `horizon_exogenous`
- `scripts/registry_lib.py`：VERDICT_FIELDS_V2 登记 `horizon_exogenous`

**测试文件**：`tests/test_horizon_known_branching.py`

**spec 要求**（spec 942-1078）：
- **W5.2**：按 `horizon_known` 标签分支填充（`known_ahead` 填真实未来值，其他三类填末值）
- **W5.3**：前视防护（spec 自称「安全关键项」）
  1. `features.py` 的 horizon 填充函数**只接受** `horizon_known` 参数决定分支，**不**接受协变量名
  2. 对每个 `horizon_known != "known_ahead"` 的协变量，断言 horizon 段**逐值等于** context 末值
  3. 对每个 `known_ahead` 协变量，断言 horizon 值**可由 cutoff 时点已知输入重算**（构造用例：改变 cutoff 之后的数据，horizon 填充值不得改变）
  4. verdict 落 `horizon_exogenous`
- **W5.5③**：加载时断言 `(horizon_known == "known_ahead") iff (走 known_ahead 填充路径)`

**验收**：
- 全部 `horizon_known != "known_ahead"` 协变量的 horizon 段逐值等于 context 末值
- `known_ahead` 协变量的 horizon 段可由 cutoff 时点已知输入重算
- 加载时断言生效：违反即拒绝

**⚠️ 影响面**：W5 会改变协变量的输入矩阵，因此**全部历史 verdict 不可与新 verdict 比较**（spec W5 注）。`cov_fill_version` 必须 bump，`protocol_fingerprint` 必须变化。

**⚠️ H1 修订（第五轮审计）**：`ensure_baselines()` 在指纹失配时**自动重生**基线且无归档。本 Phase 的 cov_fill bump 与 Phase 5 的指纹 bump 必须**合并为一次部署**，避免两次静默重生。若必须分批，本 Phase 落地前**必须先归档 9 份基线**到 `data/archive/baselines_pre_cov_fill_bump_YYYYMMDD/`。

---

### Phase 4 — PR-C5 族诊断矩阵落盘

**目标**：跑 `generate_covariate_family_verdict.py`，输出族×品种诊断矩阵。

**文件**：
- `scripts/generate_covariate_family_verdict.py`：已有，跑之
- 输出：`task_FM/config/covariate_family_verdict.json`

**验收**：
- 文件存在且 schema 符合 `fm.covariate_family_verdict.v1`
- 每格含 `inert_constant` / `all_zero` / `ablation_content_delta`（若有）/ 证据指针
- 显式给出分母 `n_evaluated(cov)`

---

### Phase 5 — PR-A5 协议指纹补数据窗口语义

**目标**：让旧基线在前视修复后自动失效，防止 `ensure_baselines` 误判。

**文件**：
- `task_FM/evaluations/fm_eval/evaluator.py`：`compute_protocol_fingerprint()` 加入数据窗口语义字段
- bump `PROTOCOL_FINGERPRINT_VERSION`

**spec 要求**（spec 412-422）：
protocol_fingerprint 应包含：
- HORIZON / STEP / CONTEXT_BARS / CONTEXT_DAYS / EVAL_WINDOW_BARS
- **cutoff 约定**（bar_open / bar_close）—— 已有
- **价格序列复权版本 + roll 守卫版本**（D1/D2）—— **缺**
- cov_fill_version
- 特征代码 git_rev + covariate_pool_rev
- 模型指纹（权重哈希）+ 预测参数
- 指标定义版本（dir_acc 口径 + 零变动策略）

**缺口**：
1. 价格序列复权版本 + roll 守卫版本
2. **H3 修订**：CONTEXT_BARS / CONTEXT_DAYS（属 spec 七组件表第 1 项，变则不可比，当前守卫抓不到）

**H3 修订交付物**：
- `compute_protocol_fingerprint()` 补 `context_bars` + `context_days` 组件
- 交付"spec 七组件 → 承载方映射表"：

| spec 七组件 | 承载方 | 当前状态 |
|---|---|---|
| CONTEXT_BARS / CONTEXT_DAYS | protocol_fingerprint | **缺（H3 补）** |
| EVAL_WINDOW_BARS / STEP / HORIZON | protocol_fingerprint | ✅ 已有 |
| cutoff 约定 | protocol_fingerprint | ✅ 已有 |
| 复权版本 + roll 守卫版本 | protocol_fingerprint | **缺（本 Phase 补）** |
| cov_fill_version | protocol_fingerprint | ✅ 已有 |
| 特征代码 git_rev + pool_rev | protocol_fingerprint | ✅ 已有 |
| 模型指纹 + 预测参数 | experiment_fingerprint（Phase 7） | **缺（Phase 7 补）** |

- **H3 修订**：Phase 7 一并退役 `fingerprint_lib.py` 的静默回退（L217-259：`compute_variant_id` 失败时回退到 `{symbol}_{cov}`，违反 W6.4 fail-loud）

**验收**：
- 指纹包含复权版本 + roll 守卫版本 + CONTEXT_BARS/DAYS
- bump 后 `ensure_baselines` 自动触发重生（实证确认）
- **H6 修订**：指纹 bump 后 `research_target_hash` 不变的断言（复权/换月版本**值**不变，否则所有现存 family 分裂）

---

### Phase 6 — §8.3 出口核验（依赖 Phase 1 + Phase 3）

**目标**：完成 spec §8.3 的 8 项核验交付物。

**文件**：
- 新增 `docs/superpowers/reports/2026-09-29-stage3-verification-record.md`（独立记录文件）
- 新增 `tests/test_statistical_verification.py`（黄金用例）

**8 项核验**：
1. ✅ 已知自相关序列手算长程方差（Phase 1 完成）
2. ✅ 负自相关 / 边界滞后 / 重叠预测场景（Phase 1 完成）
3. ✅ 三套公式分别验证（Phase 1 完成）
4. ✅ 断言"长程方差 × VIF"混用路径不存在（Phase 1 完成）
5. ✅ 黄金用例写明带宽约定等（Phase 1 完成）
6. ✅ 黄金用例枚举（Phase 1 完成）
7. ✅ 重叠预测：实测 HAC vs 名义 VIF 区分（Phase 1 完成）
8. ✅ 手算对账记录（独立记录文件）

**验收**：
- 8 项全部有对应交付物
- 独立记录文件可被第三方复现

---

### Phase 7 — PR-B1 variant_id 接线（T6 登记项）

**目标**：让 `variant_id` 真正由 `experiment_fingerprint` 派生，消除身份漂移。

**文件**：
- `scripts/praxist_supervisor.py`：`_build_variant_id()` 改由 `experiment_fingerprint` 派生
- `scripts/registry_lib.py`：兼容旧格式与新格式

**spec 要求**（spec W6.4）：
- `variant_id` 改为由 `experiment_fingerprint` 派生：`{symbol}_{cov_family}_{experiment_fingerprint[:12]}`
- 请求名降级为 `cov_requested` 仅保留可读性
- 禁止用请求名作身份键

**H4 修订**：
- `compute_experiment_fingerprint` **当前全仓无定义**（Phase 7 从零建），工作量与风险需在排期中反映
- 验收增加：`experiment_fingerprint[:12]`（48-bit）在本仓预期变体量级下的碰撞论证
- 设计注记：`experiment_fingerprint` 的组成（模型权重 + 目标序列 + context 配置，per W2.1(3)/W6.4）须写入交付物

**⚠️ 兼容性**：143 条历史裁决全为旧格式。须设计向后兼容：
- `load_snapshot` 能识别两种格式
- 新格式 verdict 与旧格式 verdict 共存时，旧格式标 `legacy_variant_id=true`

---

### Phase 8 — Stage 4 前置（需用户裁定）

**目标**：为进入阶段 4 做准备。

**前置裁定**（spec §8.5 约束 3）：
- **目标效应与功效**（§7 Q7）：决定 `N(该品种)` 与分级门槛
- **family 封账缺失判定方法**（§7 Q8）：`missingness_admissible` 当前恒 False（保守默认）

**待实施**（待裁定后）：
- PR-D1：机器可读预注册 + no-peek + 预算纪律
- PR-D2：品种分级 + `symbol_status` 退休

**本计划不实施 PR-D1/D2**（依赖前置裁定）。

---

### Phase 9 — 诊断卫生（P7-P10）

**目标**：补齐第三轮审计的 F1 / F6 / F7 发现。

**P7：测试套件密封化**（F7）
- 修复 `test_timesfm_model_path*` × 6（环境依赖）
- 修复 `test_index_continuous_quality*` × 2（数据依赖）
- 修复 `test_extract_xreg_oi_gated*` × 2（pool 状态依赖）

**P8：pool provenance**（F6）
- `task_FM/config/covariate_pool.json` 为经宿主裁定或探针重标的项补 `horizon_known_ruling` 字段

**P9：测试声明三件套**（F1）
- changelog 的测试声明补 commit hash + 完整命令 + 逐项清单

**P10：审计报告移交**
- 三轮审计报告复制到 WSL `docs/superpowers/reports/`

---


### Phase 10 — Supervisor 重启与加载验证（H2 新增）

**目标**：确保磁盘上的代码变更被活进程加载。

**背景**：第四轮 G1 发现活进程 PID 22703（自 09-28 18:51 起）未加载 N3 守卫与复测分派修复。本计划 Phase 2/7 直接改 `praxist_supervisor.py`，若不重启则磁盘 != 内存。

**步骤**：
1. 全部 Phase 实施完成后，选择维护窗口
2. `supervisor stop`（或 kill + 等待优雅退出）
3. 归档当前日志：`logs/supervisor_pre_restart_YYYYMMDD.log`
4. `scripts/start_supervisor.sh` 重启
5. 验证重启后日志出现：
   - N3 守卫加载证据
   - 复测分派逻辑激活
   - 新 family 逻辑加载
   - `ensure_baselines` 使用新的归档+重生路径（H1 修订）
6. 观察至少一个完整快环+慢环周期无异常

**验收**：
- 新 PID 出现在日志中
- 上述加载证据全部出现
- 无 crash / traceback

---

## 执行顺序与依赖

```
Phase 1 (PR-C1)  ──┐
                    ├──→ Phase 6 (§8.3 核验)
Phase 2 (PR-C2)  ──┘
Phase 3 (PR-C6)  ─────→ Phase 6
Phase 4 (PR-C5)  ─────→ 独立
Phase 5 (PR-A5)  ─────→ 独立（但影响基线）
Phase 7 (PR-B1)  ─────→ 独立
Phase 8 (Stage 4) ← 依赖用户裁定（Q1 已裁定 Δ=0.10）
Phase 9 (卫生)   ─────→ 独立，可并行
Phase 10 (重启)  ─────→ 全部 Phase 完成后（H2）
```

**并行度**：
- Phase 1 / 2 / 3 / 4 / 5 / 7 / 9 可并行（不同文件）
- Phase 6 依赖 Phase 1 + 3
- Phase 8 依赖用户裁定

**建议批次**：
- **批次 1（阻塞项）**：Phase 1 + 2 + 3 并行（⚠️ Phase 3 落地前须先归档基线，见 H1）
- **批次 2**：Phase 4 + 5 + 7 并行（⚠️ Phase 5 须与 Phase 3 合并为一次重生）
- **批次 3**：Phase 6（Phase 1 + 3 完成后；含实测再估门验证 Δ=0.10）
- **批次 4**：Phase 8（Q1 已裁定 Δ=0.10，可启动）
- **批次 5**：Phase 9（可穿插在任意批次）
- **批次 6**：Phase 10（全部完成后重启 supervisor，H2）

---

## 验证策略

每个 Phase 完成后：
1. 跑相关测试套件（`pytest tests/ -k <phase_scope> --tb=short -q`）
2. 提交（commit message 以 `feat(<PR-id>):` 开头）
3. 派 code-reviewer 复核

Phase 6 完成后：
1. 全量测试套件（`pytest tests/ --continue-on-collection-errors -q`）
2. 独立记录文件可被第三方复现
3. 派 auditor 复核 §8.3 核验完整性

---

## 开放问题（待用户裁定）

### Q1：目标效应与功效（spec §7 Q7）

#### ✅ 已裁定（第五轮审计 2026-09-29）

**Δ = 0.10 作为阶段 4 确认目标**，组合 spec §7-Q7 的 (a)+(c) 两路。

**裁定依据**（审计独立推算）：
- Δ=0.02 → n≈31,000 → 需 ≈7 年，不可行
- Δ=0.05 → n≈5,000 → 需 ≈12 个月，超过 T_max=180 天，确认机制永远开张不了
- **Δ=0.10 → n≈1,240 → 需 ≈54 天，与 T_max=180 自洽**

**执行条件**：
1. **实测再估门**：Phase 6 交付 HAC 机器后，必须用 T2 消融已有的配对序列实测 Var_LR/SE_HAC(d_bar)，重算 n_required。若实测口径下 Δ=0.10 在 T_max 内不可达，须回到宿主重裁。
2. **N(symbol) 计算口径**：按 Δ=0.10 + 该品种实测 HAC 方差计算；0.51 绝对门与 0.01 级相对门一律作废（spec §4.6）。
3. **结论表述约束**：确认报告必须含限定语（"本检验仅能排除 ≥0.10 的效应"）。
4. **长期收紧路径**：随 n 增长（每品种每月 +360 点），当实测支撑 Δ=0.05 时（约 n≥5,000，预计一年后），由宿主裁定收紧。

### Q2：Phase 5（PR-A5）的基线失效处置

#### ✅ 已裁定（第五轮审计 2026-09-29）

**备份 + bump + 强制重生**，且与 Phase 3 合并为一次重生。

**关键实证**（改变选项格局的事实）：
- `ensure_baselines()` 判据是"行数>=100 **且 protocol_fingerprint 匹配**"；任一不满足即**自动串行重生**，没有"用户决定"环节。
- 因此"保留对照"选项在活循环里**不可实现**——不备份就 bump，"对照"会被自动重生直接抹掉。

**执行条件**：
1. **合并重生（H1）**：Phase 3（cov_fill bump）与 Phase 5（指纹 bump）合并为一次部署、一次重生。
2. **重生前强制归档**：沿用前视修复的归档模式（`data/archive/baselines_pre_fingerprint_bump_YYYYMMDD/`）。
3. **版本值稳定断言（H6）**：Phase 5 只记录复权/换月规则版本，不得改变版本值。

---

## 预计工作量

| Phase | 主要工作 | 预计 |
|-------|---------|------|
| 1 (PR-C1) | 3 公式 + 黄金用例 + 测试 | 2 天 |
| 2 (PR-C2) | family 注册 + 封账 + 测试 | 2 天 |
| 3 (PR-C6) | horizon_known 代码路径 + 测试 | 1.5 天 |
| 4 (PR-C5) | 跑脚本 + 输出 | 0.5 天 |
| 5 (PR-A5) | 协议指纹补字段 + 基线处置 | 1 天 |
| 6 (核验) | 独立记录 + 复核 | 1 天 |
| 7 (PR-B1) | variant_id 接线 + 兼容 | 1.5 天 |
| 8 (Stage 4) | 待裁定 | — |
| 9 (卫生) | 测试密封 + provenance + 移交 | 1 天 |
| 10 (重启) | supervisor 重启 + 加载验证 | 0.5 天 |
| **合计** | — | **~11.5 天**（Phase 8 不计） |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| Phase 1 / 2 实施后与 Phase 3 冲突 | 文件所有权明确分工：Phase 1 拥有 statistical_tests.py + evaluation_metrics.py；Phase 2 拥有 supervisor.py；Phase 3 拥有 features.py + hourly_model.py |
| Phase 3 改变输入矩阵导致历史 verdict 不可比 | cov_fill_version bump + protocol_fingerprint 变化 + 显式 warn |
| Phase 5 bump 后基线失效 | ensure_baselines 自动重生无归档 → 合并 Phase 3+5 一次部署，重生前强制归档（H1/Q2） |
| supervisor 磁盘!=内存 | 全部完成后维护窗口重启 + 加载验证（H2，Phase 10） |
| Phase 7 experiment_fingerprint 从零建 | 碰撞论证 + 组成设计注记前置（H4） |
| 配额耗尽 | 批次化执行，关键 Phase 优先；卫生项可延后 |
| 阶段 4 前置未裁定 | Phase 8 不启动，保持现状 |

---

## 纪律

- 每 Phase 完成后独立复核（派 code-reviewer）
- 不跨 Phase 修改已交付内容（除非发现 bug）
- spec 是唯一权威；spec 与实现冲突时，以 spec 为准，修改实现
- 任何「阶段已完成」声明必须核对 spec §8 的 PR 清单 + §8.3 核验项清单
- **不**让「报告 vs 代码」审计漏掉「报告 vs spec」缺口
