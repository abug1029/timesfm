# 协变量研究可信度重构 Spec（全局）

> 日期: 2026-09-24
> 上游: `FM_a_eg_jd_lh_expert_report.html`（2026-09-24）+ 宿主审核意见（同批次）
> 状态: **待宿主批准后实施**。实施计划另出（`docs/2026-09-24-covariate-credibility-impl-plan.md`）。
> 修订记录:
> - **v8（2026-09-24）** — 按第六轮专家审核收口两点定义 + 核验增强。① **协议兼容 ≠ 配对推断可用**：W1.5 拆 `protocol_compatible`（协议指纹一致）与 `pairing_valid`（cutoff 集合一致）；DM 只在**共同 cutoff** 上配对，落 `dm_common_count`/`dm_unmatched_variant`/`dm_unmatched_baseline`/`cutoff_set_hash`，`dm_status` 增 `cutoff_mismatch`；报告排序**禁止**把"协议兼容"写成"同样本直接排名"。② **`research_target_hash` 稳定化**：family 键第三要素改为研究对象稳定哈希 `hash(品种, 目标变量, 价格序列定义, 复权·换月规则版本)`，**不含**数据内容与截止时间；新增 cutoff / 修订历史 bar **不**创建新 family；与 experiment_fingerprint 的 `target_snapshot_hash`（数据快照、随运行变）用途区分。③ **核验固定黄金用例**：三套公式各固定可人工复算用例 + 负自相关/常数/样本不足/带宽边界；重叠预测相关结构明确是实测 HAC 还是仅情景规划。④ 测试增至 67 条。
> - **v9（2026-09-24）** — 按第七轮专家审核封锁 **DM 配对口径**。① **共同样本口径**：废止 v8 "`pairing_valid`=cutoff 集合一致"与"DM 用共同 cutoff"的自相矛盾——`pairing_valid` 改判**共同样本满足最低数量与信息条件**（`dm_common_count >= dm_min_common` 且共同 `n_eff >= effective_min_n`），集合完全一致只是特例；`dm_status` 细分 `ok` / `set_mismatch_ok` / `insufficient_common` / `no_common_cutoff`（合并原 `cutoff_mismatch`/`insufficient_pairs`）。② **确认集与配对口径统一**：`confirm_from_ts`＝预注册时两模型**共同可用 cutoff 起点**，注册后不因缺失滑动；确认性 DM 只在**确认集窗口的共同 cutoff**上算；`pair_set_hash`（实际配对集）与 `raw_cutoff_set_hash`（原始列表）分开。③ **W3.4 confirmed 显式依赖配对状态**：新增 `pairing_valid==True` 与 `dm_status ∈ {ok, set_mismatch_ok}` 两前置。④ **`research_target_hash` 锁序列化规范**（字段顺序/规范化/空值哨兵/schema 版本）。⑤ 测试 3 收窄为"协议兼容性"；65/66 改共同样本口径并递增；新增 68。测试增至 68 条。
> - **v10（2026-09-24）** — 按第八轮专家审核补齐**共同样本口径的缺失机制**。① **选择偏差防护**：`pairing_valid` 拆为**计算条件** `pairing_computable`（协议兼容 + `dm_min_common` + 配对差序列 ESS）与**确认有效性**（追加**缺失模式可接受**）；新增 `n_avail_variant`/`n_avail_baseline`/`n_missing_*`/`missing_rate_by_bucket`/`missing_pattern`/`missingness_verdict`；缺失原因不可判定或与状态相关 → 仅描述性、不可确认（`set_mismatch_descriptive`）。② **`confirm_from_ts` 改预注册固定时间边界**（非"未来共同可用首个观测点"，后者注册时不可知）：注册时锁定边界 → 评估边界后**预定 cutoff 序列** → 缺失按固定规则处理，禁止事后回推/移动起点。③ **`n_eff` 对象明确为配对差序列 `d_t`**：`dm_min_common`＝原始共同观测下限，`effective_min_n`＝`d_t` 的有效信息量下限（与 DM 同一 HAC/带宽口径），两者分别定义、分别报告（`d_series_n_eff`）。④ **状态与字段矩阵 + 确定性优先级**：逐状态规定 `p_value`/`delta_ci`/`pair_set_hash`/`pairing_valid` 是否可生成；新增 `protocol_mismatch` 并定优先级（首个匹配者胜），消除处理顺序歧义。⑤ **`research_target_hash` 字节级规范**：前缀**参与** SHA 输入、分隔符禁止出现在字段值、NFC 规范化、空串与缺失统一、`symbol` 规范拼写维护处；测试改为固定输入的**精确哈希值**。测试增至 70 条。
> - **v11（2026-09-24）** — 按第九轮专家审核做**收尾级修补**（架构不变，专家建议批准实施）。① **优先级链调整**：`set_mismatch_descriptive`（缺失不可接受 → **推断框架失效**）**前移**至 `d_bar_nonpositive`（均值非正 → **数据结果属性**）之前——失效原因优先级高于结果属性；矩阵中 `d_bar_nonpositive` 的 `pairing_valid` 由自指的"由缺失条件定"改为 **`True`**（到达此状态时缺失必已判定为可接受）。② **`random` 分支可达性脚注**：§7.8 裁定前 `missing_pattern` 实际可取值仅 `state_correlated` / `undeterminable`，`random` 需待判定方法固定后方可赋值（消除 W1.5 正文与 §7.8 保守默认之间的可达性缺口）。③ **测试 66 显式化缺失前提**（"按随机模式构造"），使断言 `set_mismatch_ok` 不随 §7.8 裁定结果失效。测试仍 70 条。
> - **v12（2026-09-24）** — 按第十轮专家审核做**实施层降级**（语义不变，压缩记账厚度）。专家判定核心使命（让"过门"具备证据含义）已完整闭合、spec 主体可批准，但三处**触发概率与防护收益不对称**的机制应降级：① **缺失机制字段收敛**：核心强制字段收敛为 `n_avail_variant`/`n_avail_baseline`/`n_common` + 布尔 `missingness_admissible`；`missing_rate_by_bucket`/`missing_pattern`/`n_missing_*` 降为 **L2 诊断**（§7.8 裁定前非强制采集）；守卫语义不变（不可证明随机即 `False`）。② **哈希层次约束**：§8.6 新增——除 `research_target_hash` / `protocol_fingerprint` 外其余哈希为**实现细节**，不进人工审阅界面与报告正文；golden 精确值测试只保留 `research_target_hash` 一处。③ **`dm_status` 收敛**：`d_bar_nonpositive` 降为诊断字段 `d_bar_le_zero`（其语义本已由 p 值表达），状态枚举 8→**7**，优先级链缩短；"首个匹配者胜"断言保留。测试仍 70 条。
> - **v13（2026-09-24）** — 按第十一轮专家审核做**跨章节命名同步**（唯一残余，语义不变；专家判定"补一处表格后即可终批"）。① **§1.2 字段分级表同步 v12**：A1 行补 `dm_common_count`（＝`n_common`）/`n_avail_variant`/`n_avail_baseline`/`missingness_admissible`/`d_series_n_eff`；明确 L2 诊断字段不进分级表。② **统一旧名**：W1.2 `meets_min_info` 的 `dm_pair_count` → `dm_common_count`（全文单一名）。③ **A1 vs §8.6 边界一句澄清**：A1 管 verdict 完整性（机器校验存在性），§8.6 管人机界面（哈希可否进报告正文），二者不矛盾。④ **§4.7 W6.5 重算清单**：增 `d_series_n_eff`；并澄清 `effective_min`（gate 阈值）与 `effective_min_n`（配对 ESS 下限）**同名不同物**，保留前者正确。测试仍 70 条。
> - **v15（2026-09-28）** — 按宿主裁定**三处结构性修订**。
>   ① **W6.5 字段改名**：为避开代码中已存在的 Signal-based `n_total`/`n_active`
>      （`evaluator.py:191-211` active_mask_metrics，143 行 registry 中 5 行已带
>      `n_active`，gated 硬门消费 `n_active` 做样本量判定），方向口径的分母字段改名为
>      **`n_dir_total` / `n_dir_active`**；`n_zero_move`/`n_roll_excluded`/
>      `n_zero_ratio`/`n_roll_ratio` 无冲突保持。重算清单与测试条目同步更名。
>   ② **审计集规模**：§1.1 L2「2–3 品种」改为 **7 品种**；§4.2 W2.3 引用与
>      测试条目同步更新。理由：审计集扩充到 7 品种（SS/SR/M/JD/LH/CJ/FU）
>      是为覆盖黑色系+能化+农产品全板块；spec 字面规模不足时按宿主裁定扩容。
>   ③ **§4.5 W5 追加 W5.5 裁定记录**（宿主 2026-09-28 裁定）：
>      · `rsi_state`/`hourly_slope` 确认 `self_referential`；
>      · `ccl`/`oi` 确认 `unknowable`；
>      · `calendar_cyclical` **有条件确认 `known_ahead`** —— 构造源限定为
>        「公告日之前的既定日历 + 截至构造时点已公告的调整」，核验判据为
>        「**公告时间戳 ≤ cutoff**」（与 D5 裁定相交）；
>      · `known_ahead_evidence.verified_by` 加**宿主/研究侧身份白名单**，
>        agent 身份写入即 schema 校验失败（用 schema 而非纪律防自证）；
>      · 六字段证据**注册时填、不可追溯补填**；历史缺证据 → 降级 `unknowable` + WARN；
>      · 降级须**填充行为同步降级**（标签降级 → 填充路径降为「填末值」，WARN 才有牙齿）；
>      · 升级**不追溯**（升级时点之后产生的裁决才可用该信息资格，历史裁决不追溯改变）。
> - **v14（2026-09-24）** — 按第十二轮专家审核**用文本修补消除 PR-A6/PR-A1 的作用域张力**（不靠章节优先级裁定）。① **W1.3 作用域标记**：窗口对齐根因修复（`eval_start` 按绝对 cutoff 时间戳对齐、checkpoint 键改 `(symbol, cutoff_ts)`）**属 PR-A1、受 D5 阻断**，不在 PR-A6 交付内；PR-A1 前状态机预期以 `insufficient_common`/`no_common_cutoff` 暴露漂移，**属 fail-loud 设计行为、非缺陷**，运维侧禁止过滤该 WARN。② **§8.0 反向指针**：PR-A6 行注明"含 `aligned_slow_loop.py` 键改造的窗口对齐部分随 PR-A1 受 D5 阻断"。③ **测试前提提示**：测试 65/66 构造的是 cutoff 列表差异，天然不依赖 PR-A1；任何隐含"对齐已正确"前提（如共享 checkpoint 键语义）的用例，其跑通条件在 PR-A1 之后，须在 plan 中注明，避免"D5 前绿、D5 后黄"的假信号。测试仍 70 条。
> - **v7（2026-09-24）** — 修三项实质问题。D5 与阶段 1 拆档（PR-A1 显式 `[D5 阻断]`）；L1 的 `pass` 与 L3 的 `confirmed` 分层；HAC/VIF 核验（名义 VIF ≠ Bartlett；三套公式分别验证）；`meets_min_info` 显式含 `n_eff >= 50`；family 边界结构化；`T_max` 时钟明确。
> - **v6（2026-09-24）** — 清除规则残留冲突。删除 W1.2 残留旧判据；`n_eff` 定为 L3 确认前置、不阻断 L1/L2 与探索；family 边界可执行化；样本量口径二选一；确认检验损失定义唯一（方向命中差）；A 级拆 A1/A2（不吃 L1 交付）；主口径按运行模式；`run_mode`/`run_label` 分离；测试编号重排 1–59。
> - **v5（2026-09-24）** — 按第三轮专家审核**收尾**（消除五处内部矛盾 + 精简）。① 入队规则统一（探索/确认双模式）；② family 注册截止；③ `p=1` 范围收紧；④ 样本量公式口径（`Var(d)` 边际方差，用 HAC 长程方差不得再乘 `VIF`；`31,000` 为规划情景示例）；⑤ 配对表述收紧（"同权重"只在 `model_fingerprint` 相同时）；⑥ `meets_min_info` 取代 `n_eff_status=="ok"`；⑦ 换月跨品种汇总须声明描述性/推断；⑧ 本轮硬门槛收束为三项；⑨ §6 精简；⑩ §1.5 文档标记约定。
> - **v4（2026-09-24）** — 按第二轮专家审核**收束**。术语错误废止（`z=1.645` 是显著性边界不是 MDE）；完成标准收束为三层；字段 A/B/C 三级；Jev 降为建议；三路消融限审计集；W4 只诊断；family 由研究问题定义；PR 四阶段。
> - **v3（2026-09-24）** — 按第一轮专家审核修订 13 项。**两处统计定义错误已废止**：① `mde_dir_acc` 用单样本标准误冒充增量门槛（拆为 `mde_vs_random` / `mde_vs_baseline`，后者与 DM 共用配对 HAC）；② 单一 `window_fingerprint` 要求"一致"与前向确认集矛盾（拆为 `protocol_fingerprint` / `sample_fingerprint`）。另补：`n_eff` 七类边界规则、family/封账/no-peek 的多重比较定义、确认独立性锁定、跨板块例外改为事前留档许可、指标分母口径与强制报告、W4 最低覆盖、`known_ahead` 证据格式、指纹规范序列化与 `experiment_fingerprint`、PR 依赖图重排。
> - **v2（2026-09-24）** — 补 §2.5 污染审计 + §4.7 W6 污染控制工作包（数据/思考链/治理三类污染）。
> 裁定记录（2026-09-24）: ① W6.1 — 接受"只读自身 kline ⇒ 全板块"自动判据；`L`/`PP` 归入能化链。② W6.8 — 仅登记为残余风险，不做诊断性检验。③ W6.5 — 历史 `dir_acc` 从 checkpoint 离线重算，历史 verdict 仍标 `legacy_untrusted`。
> 权威关系: 本文修订 v23 评估口径的**执行细节**（`n_eff` 口径、成功判定、留出协议、诊断字段），
> **不改 `gate()` 的质量筛选语义**。裁决公式唯一权威仍是
> `docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md`（下称 v23）。
> 范围: **全局**。适用于 `praxist_goal.yaml` 全部 24 个目标品种，不针对 EG/JD/LH 单点修补。

---

## 1. 目的与完成标准

专家报告把问题归因为"数据量不足 + 协变量覆盖不全 + 品种特性"，并建议"对 LH 的 NVI 精细调参以突破 0.50"。审核意见正确地指出：在评估口径未经审计前，这些结论都只是待检验假设。

本 spec 的目标不是提高过门数，而是**让"过门"重新具备证据含义**。

### 1.1 三层完成标准（v4 收束）

> **v3 的问题**：把诊断字段、流程门槛、治理机制一律升为"全局必需项"，列了 23 条完成标准 + 40 条测试，
> 结果更像完整的研究治理框架，而不只是"让实验变可信所需的最小改造"。
> 这会把**尚未验证的治理系统本身变成新的故障源**。v4 按"是否阻断错误结论"分三层。

**第一层 L1 — 三项硬门槛（本轮必交付）**

> **v5 收束**：v4 的 L1 有 6 项，实现者难以分辨本轮真正的"最小闭环"。v5 收敛为**三项**——
> 这三项没通过，结果就不应进入确认判定；其余全部移到 L2/L3 或诊断项。

**硬门 1 — 因果与对齐正确**

cutoff 语义（D5）、窗口与 checkpoint 键（X7）、`bfill`（D4）、换月标签处理（D1/D2）**经过验证**。

**硬门 2 — 比较对象正确**

同 cutoff 的**无协变量基线**（E7）；**显式记录 DM 配对状态**（E6，`dm_status` 不得静默为 `None`）；
**统计比较只在配对点上进行**。

**硬门 3 — 结果可追溯**

实际协变量矩阵指纹（C2）、协议版本（E9）、必要的分母与指标定义（X9/X10）。

**第二层 L2 — 诊断与第二阶段完成项（非硬门）**

- 三路消融：**仅在固定审计集**运行（§4.2 W2.3），不必为所有协变量类型与品种铺开。
- W4 族×品种**诊断矩阵**：保留为诊断报告，**不配套建设自动归档规则**（§4.4）。
- `proposer` / `peer` / `jev` 等元数据：**默认采集可以，不作 verdict 有效性门槛**（§1.2 C 级）。
- `known_ahead` 证据登记：**只对实际启用的未来已知特征强制要求**，不为未使用的协变量库条目先做全量治理（§4.5 W5.1）。
- `n_eff` 实测与边界规则：作为诊断与最低信息要求（§4.1 W1.2），不承担增量检验推导。

**第三层 L3 — 确认与多重比较（本轮不阻塞交付）**

- 预注册（机器可读 + 时间戳）+ 固定确认样本量 + family 校正（§4.3）。
- **24 品种自动分级等目标效应与功效目标明确后再做**（§7 开放问题 7），**不与测量修复捆成同一交付**（§4.6）。

### 1.2 字段三级（防 schema 膨胀）

> **v3 的问题**：所有字段必填 → 一个非关键元数据缺失就让整个 verdict 无效。v4 分三级，
> **治理分析类字段缺失不得使 verdict 无效**。

| 级别 | 含义 | 字段 | 缺失后果 |
|---|---|---|---|
| **A1 本轮必交付（L1）** | 三项硬门直接依赖 | `protocol_fingerprint`、`cov_fingerprint.matrix_sha256`、`dir_acc`/`dir_acc_full`/`dir_acc_ex_roll` + 分母计数、`dm_status`、`dm_common_count`（＝`n_common`）、`n_avail_variant`/`n_avail_baseline`、`missingness_admissible`、`d_series_n_eff`、`pair_set_hash`、`covariates_used`、`baseline_dir_acc`、`run_mode`/`run_label` | verdict **不完整**，不得进入成功判定 |
| **A2 确认阶段必需（L3）** | 阶段 3 实现后确认判定才需要 | `delta_ci_lo/hi`、`meets_min_info`、`detection_threshold_*`、`se_hac`、`n_required_for_target` | **探索运行可缺**（落 `null`）；**确认运行**缺则不得确认 |
| **B 复现必需** | 重算与追溯所需 | `sample_fingerprint` 各字段、`context_hash`、`model_fingerprint`、`git_rev`、`cov_fill_version` | verdict 有效，但**标记为不可复现** |
| **C 治理分析可选** | 仅用于提案来源分析 | `proposer_model`、`proposer_provider`、`peer_role`、`run_id`、`jev_*`、`cross_sector_*` | verdict **完全有效**，不得因此无效 |

**A1 字段的完整性由测试强制；A2 仅在确认运行强制；B 级缺失打 WARN；C 级缺失静默允许。**

> **v13 同步（字段分级表随 v12 收敛更新）**：① 新增强制字段 `n_avail_variant`/`n_avail_baseline`/`missingness_admissible`/`d_series_n_eff` 归 **A1**（进成功判定路径）；`missing_pattern`/`missing_rate_by_bucket`/`n_missing_*` 为 **L2 诊断**（§8.6），**不进**字段分级表、缺失不影响 verdict 有效性。② 旧名 `dm_pair_count` 已由 `dm_common_count`（＝`n_common`）取代，全文统一（含 W1.2 `meets_min_info` 公式）。③ **A1 与 §8.6 的边界**：A1 管的是 **verdict 完整性**（机器校验字段**是否存在**），§8.6 管的是 **人机界面**（哪些哈希**可出现在报告正文**）——`pair_set_hash` 同时是 A1 必交付字段与"不进报告正文"的实现细节，**二者不矛盾**：A1 字段的存在性由机器校验，**不等于**出现在报告正文。

> **v5 修正**：v4 把 `delta_ci_lo/hi` 放进单一 A 级，但三项 L1 硬门并不包含置信区间生成——
> 这会让 L1 交付被 L3 的统计产物阻断。故拆出 **A2（确认阶段必需）**，明确它**不阻断 L1 探索交付**。

### 1.3 与 §2 核实结论的对应

本 spec 保留 §2 的全部核实结论（它们是事实，不因分层而降级）。分层只影响**实施范围与优先级**，不影响**问题清单**。被降级为诊断项的内容在 §4 中逐条标注 `[L2 诊断]` 或 `[L3 延后]`。

### 1.4 两种运行模式（消除 v4 的入队矛盾）

> **v4 的内部矛盾**：§1.1 L3 说"L3 未就绪时系统仍可运行、产出标 `exploratory_unconfirmed`"，
> 而 §4.3 W3.1 仍写"无有效预注册 → 不入队"。**两条不能同时成立。**

| 模式 | `run_mode`（机器字段） | `run_label`（展示标签） | 入队要求 | 可进确认 family / 成功判定 |
|---|---|---|---|---|
| **探索运行** | `"exploration"` | `exploratory_unconfirmed` | **无** `prereg_id` 亦可入队 | ❌ **不可** |
| **确认运行** | `"confirmation"` | `confirmed` / `refuted` / `underpowered` | **必须**有已锁定的 `prereg_id`，且按预定样本量与口径执行 | ✅ 可 |

- **`run_mode` 是唯一枚举字段**（取值 `exploration` / `confirmation`），成功判定读它。
- **`run_label` 是另一个字段**，供人读。**禁止**用标签充当机器判据，也**禁止**把机器枚举混入自然语言状态
  （v5 残留问题：表格用"探索运行"、公式用 `run_mode == "confirmation"`、标签写 `exploratory_unconfirmed`，
  三者混用会让实现者无法确定权威字段）。
- 每个 verdict 必须携带 `run_mode` 与 `run_label`；`run_mode="exploration"` 的 verdict
  **不得**出现在成功判定、品种分级，或任何"已确认"表述中。
- 探索运行**保留系统可运行性**：L3 未就绪时也能产出诊断、生成假设。
- **探索数据可以用于后续提出假设**；但**确认集只能使用注册后、且此前未用于筛选的 cutoff**——
  这样既保留可运行性，也避免把探索结果包装成确认结果。

### 1.5 文档标记约定（区分事实 / 规定 / 待决 / 建议）

> 本文同时包含四类内容。修订记录与"宿主已裁定"字样**不足以**防止读者把待决项当成已批准规则，
> 故全文按下列标记区分效力。

| 标记 | 含义 | 效力 |
|---|---|---|
| **【事实】** | 已核实的现状（§2 全部结论、代码与数据实测） | 可直接引用，附证据指针；不受批准状态影响 |
| **【规定】** | 本 spec 确立的规则（§4、§5、§6） | **批准后**生效 |
| **【待决】** | 需宿主裁定的开放问题（§7） | **尚未生效**，不得当作已批准规则 |
| **【建议】** | 实施路径与优先级（§8 与各处的"推荐"） | 可调整，不构成约束 |

- 正文中出现"宿主已裁定"的条目，表示该条已从【待决】转为【规定】；**未标注者按所在章节判断**。
- 状态行"待宿主批准后实施"的含义是：**§4–§6 的【规定】尚未生效**；§2 的【事实】**不受此限**。
- §7 的每一项在裁定前均为【待决】，**包括已写入 §4/§6 的对应默认值**——默认值只是"若批准则生效"的预设。

---

## 2. 核实结论

证据等级：✅ 宿主会话内直接验证 · 🔬 代理实测（命令已跑，结论待复现）· 📄 代码阅读

### 2.1 评估口径

| ID | 事项 | 报告/审核说法 | 核实结论 | 证据 | 处置 |
|---|---|---|---|---|---|
| E1 | 过门门槛 | 报告把 `DirAcc≥0.50` 当硬门 | **门槛 = `max(0.50, min(0.52, baseline))`**；8 品种中 6 个 = **0.5000**，正好等于硬币抛掷率（z=0.00） | ✅ `evaluator.py:397-417`、`baseline_metrics.json` | 门槛保留为**筛选器**；成功判定换口径（§4.3） |
| E2 | `n_eff` | 报告称 "Gate=73"（当成质量门槛计数） | **误读**。73 是 `fallback_n_eff(588,24,2)` 的配置常数（`h=12`, `factor=8.028`, `588/8.028→73`） | ✅ `evaluation_metrics.py:377-396` | 改实测；报告该列作废 |
| E3 | `n_eff>=50` 门 | — | **恒真**（73≥50），零筛选力 | ✅ 同上 | 并入 E2 |
| E4 | 统计晋升 | — | 143 条中 **0 条**由 DM+BH-FDR 晋升；最小 DM p = **0.0302**（`sr_calendar_cyclical`），**无一条过 0.025**；3 条 `fdr_pass=true` 全是 `migrated_v1` 迁移产物且 `p_value=null` | 🔬 + ✅（`fdr_pass` 计数已验） | 修 `migrated_pass` 后门（§4.1） |
| E5 | BH-FDR | 审核要求多重比较校正 | **从未真正运行**：58 批次、每批 1–2 个变体 → 恒触发 `K<min_batch_size=4` 降级分支 → 实际是固定 Bonferroni `p<=0.025` | 🔬 `statistical_tests.py:229-312` | 批次语义重定义（§4.3） |
| E6 | DM 静默失效 | — | **42/98 checkpoint 与基线零重叠 cutoff** → `len(v_series)>=100` 为假 → `p_value=None`，**无告警**。根因：窗口随数据末端滑动 + `STEP=2` 相位随 `total` 奇偶翻转 → n 在 588/589 间跳 | 🔬 `monthly_backtest.py:256-264`、`statistical_tests.py:98-148` | 加 `dm_status` 显式字段（§4.1） |
| E7 | 对照基线 | 审核要求"与无协变量 TimesFM 比较" | **基线是 `ccl` 协变量运行**，不是无协变量 | ✅ `praxist_supervisor.py:2006,2025` `gbp.generate(sym_lower, "ccl", root)` | 补无协变量基线（§4.1） |
| E8 | 不确定性 | 审核要求置信区间 | verdict **无 CI、无标准误**；全库唯一 bootstrap 属 A2 LGBM 子项目，不进 FM_a 门 | 🔬 | 补 CI（§4.1） |
| E9 | verdict 可比性 | — | 窗口 `eval_start = total - EVAL_WINDOW_BARS` 随数据滑动，checkpoint 按**位置索引**续跑 → 同一变体不同时间跑在**不同窗口**上 → 143 条 verdict **彼此不可比** | 🔬 `monthly_backtest.py:259`、`aligned_slow_loop.py:116-137` | 落窗口指纹；跨窗口比较一律禁止（§4.1） |

### 2.2 数据与价格序列

| ID | 事项 | 核实结论 | 证据 | 处置 |
|---|---|---|---|---|
| D1 | 复权 | **完全没有复权**。`detect_rolls_from_price_gaps` / `apply_backward_adjustment_robust` 存在但守卫自毁：`main_continuous_1d` 恒有 `raw_close` 列（实测 2606 行全 NULL、`adjustment_factor` 全 0.0）→ 分支永不执行；1H 路径也无复权 | 🔬 `data_store.py:418-425` | 换月跳变入 label，加 roll 守卫（§4.1） |
| D2 | 换月污染 | `HORIZON=24` 窗口跨换月时，拼接跳变进入 `Δreal` 与 `dir_ok` 端点；**评估侧无 roll 守卫**。实测 SR_MAIN 1H 有 3 根 |1-bar 收益|>3%（+5.08%、−3.65%、−5.52%） | 🔬 | 同 D1 |
| D3 | `xreg_factors` 表 | **死表**。`get_xreg_factors()` / `get_xreg_matrix()` 除自身定义与内部互调外**无任何调用者**；仓库自述"预测时不读取此表"。协变量实为从 `kline_1h` 实时计算 | ✅ | 报告"数据量对比"表作废（§2.4） |
| D4 | `bfill` 非因果 | `oi_smooth = oi_smooth.bfill()`、`scale = mad.bfill()` → 用**未来**值回填 context 内 NaN | 🔬 `features.py:644,1975` | 改因果填充（§4.1） |
| D5 | 1-bar 前视 | `dt` 是 bar **开盘**时间（tqsdk kline `datetime`），回测 cutoff 取该 bar 的 `dt`（开盘），但同索引协变量与目标用该 bar **收盘**值（1 小时后才知）。注释声称防前视，实际只防日期级 | 🔬 `tqsdk_fetcher.py:204`、`monthly_backtest.py:305-309` | 修或量化（§4.1） |
| D6 | 自引用协变量 | `daily_slope` / `rsi_state` 的 horizon 尾值来自 TimesFM 自己的日线预测输出 → 该协变量的未来段是模型自身输出的函数，非外生信息 | 🔬 | 登记 + 排除出"外生协变量"口径 |

### 2.3 协变量通路

| ID | 事项 | 核实结论 | 证据 | 处置 |
|---|---|---|---|---|
| C1 | 协变量是否进模型 | **进**。经 `past_future_covariates` 作为额外 variate 通道，走 variate attention；实测能改变点预测 | 🔬 `hourly_model.py:211-226`、`model.py:461-585` | 通路成立，无需重建 |
| C2 | 克隆根因 | **确定性，非假设**：① 常数协变量 = **数学精确 no-op**（per-variate RevIN `(x-μ)/σ`，常数→0，实测 diff=0.000000）；② 全 NaN 协变量静默变 0 = 精确 no-op（实测 diff=0.0）；③ 多条构造路径静默零填充（`features.py:1198/1336/1367/1443-1448/1501`） | 🔬 | fail-loud + 指纹（§4.2） |
| C3 | 零填充审计覆盖 | 唯一守卫只覆盖 6 类（rsi_state/ha_body/reversal_shadow/stddev/nvi/qstick）；**ccl/oi/basis/vor/crack_spread 未覆盖**——而克隆高发族恰是 ccl/nvi/vor/crack_spread | ✅（守卫范围已验） | 扩到全部类型（§4.2） |
| C4 | `xreg_fallback` | 该标志在实盘侧被追踪（`live_ledger.py` 落库、`copilot.py:729` 分支），但在**产出 verdict 的评估路径**（`task_FM/evaluations/fm_eval/`、`monthly_backtest.py`）**零引用** → 回退到无协变量的运行被写成"用了协变量"的 verdict | ✅ | 评估路径消费该标志（§4.2） |
| C5 | 结构性天花板 | 每个协变量的 horizon 尾部都是常数（zeros/末值/decay；实测 `hz_std=0, hz_uniq=1`）→ 经 RevIN 归一化为 ~0 → **未来段不含外生信息** | 🔬 | 见 §4.5（开放） |
| C6 | ablation 混淆 | 实测（cf, 480bar, H=24）：真实 vs 清零 = 52.97 tick（占价格 0.335%）；常数 vs 清零 = 0；**完全不带协变量 vs 清零 = 97.07 tick（占价格 0.615%）**——结构性通道效应 > 内容效应，且样本中**符号相反**。仓库自身 ablation 把两者混同，且 `visualize=False` → `baseline_forecast` **从不落盘** | 🔬 | 分离报告 + 落盘（§4.2） |

> 注：上表 C6 的 `0.615%` 是**占价格水平的比例**，与已废止的 MDE 数值 `0.615` 无关（后者见 §4.3 W3.5）。
| C7 | 死配置 | `prediction_scheme.py:132 xreg_covariates` 唯一消费者是打印语句；改它必然是静默 no-op | 🔬 | 删除或标注 |

### 2.4 对专家报告的裁定

报告的四条核心论据，逐条核实：

| 报告论据 | 裁定 |
|---|---|
| "三个品种 0 过门率，SR 68%" | **口径不可信**：门槛压在硬币率上，且 0 条经统计晋升。0% 与 68% 的差异不是品种差异，是噪声（E1/E4） |
| "数据量不足导致失败"（kline/xreg 行数表） | **论据失效**：`xreg_factors` 是死表（D3）；评估样本 `n=588` 对全部品种相同。报告该表整体作废 |
| "Metrics 克隆 → 协变量未被利用" | **结论方向错、机制对**：协变量确实进模型（C1），克隆来自常数/NaN 协变量的精确 no-op 与静默零填充（C2），不是"未被利用" |
| "LH 最接近阈值，精细调参可突破 0.50" | **反模式**：0.488 低于硬币率，0.012 = 0.2 SE。此为典型 p-hacking，**禁止**作为实施方向 |
| "Gate=73" | 误读（E2），该列作废 |
| 报告未涉及 | 复权缺失（D1）、DM 静默失效（E6）、基线非无协变量（E7）、verdict 不可比（E9）——均比报告所述更严重 |

### 2.5 污染审计

按三类污染重新扫了一遍。证据等级同 §2.1。

#### 2.5.1 数据污染

| ID | 污染 | 核实结论 | 证据 |
|---|---|---|---|
| X1 | 换月跳变入 label | 无复权 + 无 roll 守卫，拼接跳变进入 `Δreal` 与 `dir_ok` | D1/D2 |
| X2 | `bfill` 非因果 | 用未来值回填 context 内 NaN | D4 |
| X3 | 1-bar 前视 | cutoff 取 bar 开盘，同索引值取收盘 | D5 |
| X4 | **门槛跨品种不一致** | 6 个品种（cf/i/jm/ma/p/sh）**有 verdict 但无基线** → `gate()` 回退 `min_dir_acc=0.52`，比另 8 个品种的 **0.50 更严** → 同一 registry 并存两套门槛，`gate_pass` 跨品种不可比。且 `p` 的 3 条过门全部 `p_value=null`（无基线 → 无 DM 对照），本质是迁移产物 | ✅ 实测 |
| X5 | **`variant_id` 身份不稳定** | key = **请求的** `cov_override`，实际送入模型的矩阵可与之不同（C2/C3）→ 同名跨运行语义漂移 | C2/C3 |
| X6 | **registry 去重语义** | 按 `(batch_id, variant_id)` 去重 + `load_snapshot` **last-wins** → 同 `variant_id` 的多窗口记录被静默取一条 | E9 |
| X7 | **单条 verdict 内部可能混窗口** | checkpoint 按 `(symbol, idx)` **位置索引**续跑；窗口滑动后同一 `idx` 指向不同 cutoff → 一条 verdict 内部混合两个窗口的点。这比"跨 verdict 不可比"更严重：记录**自相矛盾** | E9 |
| X8 | **活表历史修订无防护** | `future_bar_guard.purge_future_bars` 只删 `date(dt) > max_allowed_daily_label(now)` 的**未来**行，不防**历史 bar 被修订**；`kline_1h` 由 `daily_update.py` 持续写入 | 📄 |
| X9 | **zero-move 强制判负** | `abs(delta_real) < eps → dir_ok=False`（零变动既非命中亦非失误，却被判负）。实测占比：sr 0.3% / rb **2.0%** / m 0.7% / cj 0.5% / eg 0.2% / jd 0.7% / lh 1.0% / ss 0.3% | ✅ 实测 |
| X10 | **`dir_acc` 同名两义** | gate 消费 full-sample 口径（零变动算 miss）；`calc_net_metrics` 另有 active-only `DirAcc`，而模块 docstring 宣传的是后者。同一名词两个含义 | 📄 |
| X11 | 预训练污染 | **风险低**。模型卡标注：Wikipedia Pageviews cutoff **Nov 2023**、Google Trends **EoY 2022**、GiftEvalPretrain（剔除与 fev-bench 重叠者）、合成数据。评估窗为 2026-01→2026-09，与已标注 cutoff 间隔 ≥2 年；且中国期货 1H 合约数据不太可能进入 Google 语料。**但 `GiftEvalPretrain` 自身 cutoff 未标注** → 残余风险，非零 | ✅ 模型卡 |

#### 2.5.2 思考链污染

| ID | 污染 | 核实结论 | 证据 |
|---|---|---|---|
| Y1 | **机制文本是装饰性的** | `crack_spread_*`（**裂解价差**，原油炼化概念）被评到 **LH 生猪、m 豆粕、cj 红枣、sr 白糖、ss 不锈钢、rb 螺纹钢** —— 这些品种与原油裂解无关。`mechanism` 仅要求 ≥40 字符、非空即 `+1.0` 分，**无任何"机制与协变量构造是否一致"的检验** | ✅ 实测 |
| Y2 | **Jev 判断被结果污染** | `_extract_relevant_history` 注入 Jev 的历史经 `v.get("gate_pass")` **过滤** → Jev 的合理性/新颖性建立在被选择偏差污染的集合上，**不是独立先验** | ✅ 代码 |
| Y3 | **`exploit` 角色被显式指示追噪声尾部** | 角色描述要求"在近门/过硬门未过 FDR 的变体上精炼 symbol×cov" → 搜索被制度性地导向噪声尾部 | 📄 |
| Y4 | **peer 被 best/near-miss 锚定** | `known_verdicts.inc.md` 注入 best `dir_acc` 与 near-miss 列表 → 假设从观测数字反推，机制文本成为事后叙事 | 📄 |
| Y5 | **提案模型无归属** | verdict schema **无** `model` / `provider` / `proposer` / `peer` 字段（实测探测全 ABSENT）→ primary（`claude-opus-4-7`）与 failover（`qwen3.7-plus`）的提案混入同一 registry，**无法归因、无法控制** | ✅ 实测 |
| Y6 | **协变量菜单被跨品种无差别枚举** | `oi` 出现在 11 个品种、`calendar_cyclical` / `ccl` 各 9 个、`bb_squeeze` / `nvi` 各 8 个 → 提案是菜单枚举，不是品种推理 | ✅ 实测 |

#### 2.5.3 治理与报告层污染

| ID | 污染 | 核实结论 |
|---|---|---|
| Z1 | **"探索次数"被当成绩** | 报告称"EG 探索最充分（24 次）"——尝试次数被表述为优点 |
| Z2 | **幸存者偏差进文档** | `results_summary.md` 只列 S/A 级；143 条真实分布（均值 0.4818、68.5% 低于 0.50）不可见 |
| Z3 | **tier 是 `dir_acc` 的再编码** | `neff_score` 只取 **7 或 10**（因 `n_eff` 是常数，近乎二值）→ 该分量几乎不 discriminate；S/A/B/C 标签制造虚假粒度 | ✅ 实测 |
| Z4 | **tier 含 `prescreen_score`** | tier 被 Jev 污染，而 Jev 又被 `gate_pass` 污染 → **环路** |
| Z5 | 报告把噪声理性化 | 专家报告"LH 最接近阈值，精细调参可突破 0.50" |
| Z6 | **`rb` 基线 0.396 远低于随机** | 与无复权/换月跳变耦合的**可检验假设**：换月拼接制造模型不可预测的大幅 `Δreal` → 压低 `dir_acc`。检验：剔除跨换月 cutoff 后重测 `rb` 基线；若显著回升则 D1/D2 是主因 |

**三条改变设计的发现**：Y1/Y6 → 需要**提案质量门**（W6.1）；Y2 → **Jev 必须结果盲化**（W6.2，直接修正 §4.3 W3.2 的设计）；X4 → **门槛一致性前置条件**（W6.6）。

---

## 3. 非目标

- **不**把 `gate()` 的 `effective_min` 改回全局 0.52 硬切（v23 已批准的品种自适应，回退会杀掉低基线品种的近门信号）。
- **不**修改 `.venv` / Praxist 发行源码。
- **不**新增基本面协变量数据通道（外部数据源、发布时滞登记）——宿主已划出本轮范围。
- **不**新增扣费后经济价值评估层（换手/回撤/风险暴露）——宿主已划出本轮范围。
- **不**恢复 PF/EV/MaxDD 进裁决链（v23 已退役）。
- **不**为单个品种（EG/JD/LH）做特调。全部改动按全局口径实施。
- **不**把"前向确认需要日历时间"当成拖延理由去继续刷变体；确认期内探索预算受 §4.3 约束。

---

## 4. 设计

### 4.1 W1 — 审计与不变量

**W1.1 修 `migrated_pass` 后门（E4）**

`registry_lib.pass_variants()` 现为 `gate_pass AND (fdr_pass OR migrated_pass)`。改为：

```
pass = gate_pass AND fdr_pass AND p_value is not None
```

`migrated_pass` 保留为**历史标记字段**（可读、可展示），但**退出成功判定**。历史 3 条迁移记录在新口径下自动降为"未检验"。禁止回填。

**层级与运行模式（v7 明确，防"L1 的 `pass` 被 L3 的 FDR 卡住"）**：

- **`gate_pass`（L1 质量筛选）**：由 `gate()` 计算，是**筛选器，不是科学结论**。L1/L2 与探索运行都产出它，但它**不**声称"通过统计学检验"。
- **`fdr_pass` + `p_value`（L3 统计判定）**：仅当 `run_mode="confirmation"` **且**统计组件（DM/BH-FDR）启用时才有值。
- **`pass_variants()`（登记层）**：只对**确认运行**的 verdict 有意义；`run_mode="exploration"` 的 verdict **恒为 False**（它没有 `p_value`）——这是**正确行为，不构成"阻断探索/L1/L2 交付"**。
- **`confirmed`（成功层，§4.3 W3.4）**：在 `pass_variants()` 之上追加**确认集与协议指纹**约束。

即：**L1 交付的是 `gate_pass` + A1 字段，不是 `pass`**。`pass` 是 L3 才计算的状态。二者分层，**不得**用一个 `pass` 同时承载"质量筛选"与"统计确认"。

**W1.2 `n_eff` 改实测（E2/E3）**

唯一家：`cascade/evaluation_metrics.py`。新增 `measured_n_eff(x)`，与 DM 检验**共用同一估计量**（`statistical_tests.py:154-227` 的 Newey-West Bartlett + HLN），**禁止**另写一套。

**带宽参数的唯一约定**（v3 把 `q` 写成 11 又与 `h=12` 并用，属定义混乱，此处统一）：

```
h = HORIZON // STEP = 24 // 2 = 12      # 重叠窗口数（求和项数参数）
q = h - 1                = 11            # 最大滞后阶数
VIF = 1 + 2 * Sum_{j=1..q} (1 - j/h)^2   # = 8.0278（名义值）
```

`h` 与 `q` 的这一定义在 **`n_eff` 实测、DM 检验、规划公式**三处**共享参数**；实现只允许有一个来源。

> **v7 关键更正（第 5 轮审核）**：这里 `(1 - j/h)^2` 的**平方**权重对应**重叠窗口的名义方差膨胀**
> （假设相关性按 `(1-j/h)` 线性衰减、方差平方累积），**不是**标准 Bartlett HAC 核（Bartlett 是**线性**权重 `1 - l/(L+1)`）。
> 因此：
> - `VIF = 8.0278` 是**名义 VIF**，**仅**用于无先导数据时的量级情景；
> - 它**不等于** DM 检验使用的 Bartlett 长程方差，**也不等于** `n_eff` 的实测分母；
> - **禁止**声称"规划 VIF = DM 长程方差"；三条路径各自用**自己的**估计量；
> - **"参数同源"（共享 `h`/`q`）≠ "统计量定义相同"**——印证 §5 阶段 3 核验必须分开验证三个公式，
>   不能只断言"没有第二套参数定义"。

**定义**：`n_eff = n * sigma0^2 / sigma_LR^2`，其中 `sigma0^2` 为样本方差，`sigma_LR^2` 为 Bartlett 核 HAC 长程方差（带宽 `q = 11`）。

**与 DM 的关系（v3 表述有误导，此处更正）**：`n_eff` 与 DM **共享 HAC 实现与带宽约定**，但**输入序列不同**——
`n_eff` 作用在**方向正确序列**（单变量 0/1），DM 作用在**配对损失差序列** `d_t = v_ok - b_ok`。
**二者不是同一个统计量**，数值不可互换。见 §4.3 W3.5 的用途边界。

**定位（v5 明确，消除"既称诊断又称成功门"的矛盾）**

> **v5 残留缺陷**：v4 把 `n_eff` 写成"只作诊断量"，同时又保留 `n_eff >= 50` 门并把它并入 `meets_min_info`，
> 于是它**实际成了确认成功的硬门**，与"L2 诊断、不作有效性门槛"直接冲突。v5 修正如下。

- `n_eff` 是**诊断量**，并作为 **L3 确认检验的前置条件**（`n_eff >= 50`，经 `meets_min_info` 表达）。
- **它不阻断 L1/L2 交付，也不影响探索运行产出的有效性**——探索运行照常入队、照常出 verdict，
  只是该 verdict **不能被确认**。
- 增量检验与样本量规划**一律直接基于配对差异序列的 HAC 方差**，不经过 `n_eff` 间接推导。
- **禁止**把 `n_eff` 同时描述为"诊断项"与"成功门"；它的**唯一门控作用域是 L3 确认判定**。

**必须显式定义的边界情形**（前一版缺失，导致公式在常数序列上 `0/0` 未定义，与测试要求矛盾）：

| 情形 | 确定性规则 | `n_eff_status` |
|---|---|---|
| `n < 30` | 不估计，返回 `None` | `insufficient_n` |
| `sigma0^2 == 0`（常数序列） | **先于除法判定**，`n_eff = 1`（常数序列只含 1 个独立观测，此为**约定**，非公式推论） | `degenerate_constant` |
| `sigma_LR^2 <= 0`（HAC 非正，小样本下可能） | 夹取 `sigma_LR^2 = sigma0^2` → `n_eff = n`，并打 WARN | `hac_nonpositive_clamped` |
| `sigma_LR^2 < sigma0^2`（负自相关） | `n_eff > n` → **夹取上限 `n_eff = n`** | `clamped_to_n` |
| 存在缺失值 | 成对删除（listwise），并落 `n_dropped` | — |
| gated active 子集 `n_active < 30` | 不估计，返回 `None`；硬门 **fail-closed** | `insufficient_n_active` |
| 结果非有限（NaN/Inf） | 返回 `None` + WARN | `nonfinite` |

**有限样本修正**：`n_eff` 取 `max(1, min(n, round(...)))`，即整数且落在 `[1, n]`。

**用途边界（关键，前一版混淆）**：

- `n_eff` **可以**用于：① **L3 确认判定**的最低信息要求（经 `meets_min_info` 表达，**不**阻断 L1/L2 与探索运行）；② `detection_threshold_vs_random`（单样本比例口径）。
- `n_eff` **不可以**用于：成功判定的增量检验。**配对差异的标准误不能由 `n_eff` 代入二项公式得到**——必须直接用配对序列 `d_t` 的 HAC 估计（见 §4.3 W3.5）。把 `n_eff` 塞进二项 SE 当作增量门槛是**错误**的。

**`meets_min_info` — 单一显式字段（替代 v4 的 `n_eff_status == "ok"`）**

> **v4 的缺陷**：成功判定要求 `n_eff_status == "ok"`，但常数方向序列返回 `degenerate_constant`——
> 即使这是**有意义的诊断结果**也会被一概挡掉。把所有非 `ok` 状态等同于"无效"是**过度苛刻**。

改为**一个显式布尔字段**表达"是否满足确认检验的最低信息要求"：

```
meets_min_info = (n >= min_n)
              and (n_eff >= 50)                  # 显式包含 L3 确认前置（实测 n_eff，非名义常数）
              and (dm_common_count >= min_pairs)     # v13 统一命名（原 dm_pair_count）
              and n_eff_status in VALID_ESTIMATE
```

> **v7 修正**：上一版布尔式有 `n_eff_status in VALID_ESTIMATE`，但**未显式**写入 `n_eff >= 50`，而正文又把后者列为 L3 确认前置——会形成"`meets_min_info=True` 却仍因 `n_eff` 不达标不得确认"的分叉。现把 `n_eff >= 50` **直接写进布尔式**，二者合一。

**防绕过**：`meets_min_info=False` 时，确认运行**只能**得到 `underpowered` / 不可判定；
**任何其他字段组合不得**促成确认。该不变量必须进入成功判定测试（§5.3）。

并**区分两类非 ok**（含义完全不同，报告必须分开呈现）：

| 类别 | 状态 | 含义 | 处置 |
|---|---|---|---|
| **统计上不可判定** | `degenerate_constant`、`insufficient_n_active` | 方向序列退化 / 有效子集过小——**数据没错，是信息不足** | `meets_min_info=False`，**如实报告为"信息不足"**，**不**当作评估错误 |
| **评估数据错误** | `nonfinite`、`insufficient_n`、任何 `status="error"` | 计算失败或数据非法 | `meets_min_info=False`，**标记为错误**，需修复后重跑 |

- 成功判定读 `meets_min_info`，**不**读 `n_eff_status`。
- `degenerate_constant` 必须是**可见的诊断结论**（例如"该变体在所有 cutoff 上方向恒定"），**不得**被静默归入错误。

**其他**：

- gated 协变量的 `n_eff` 必须在 **active 子集上独立重算**（关闭 `evaluator.py:269-274` 登记的开放问题 #4）。当前 `min(全量 ESS, n_active)` 被代码自述为"门偏松"，必须废止。
- verdict 同时落 `n_eff_nominal`（旧常数，仅供历史对比）与 `n_eff`（实测）+ `n_eff_status`。
  **成功判定不直接读 `n_eff_status`，只读 `meets_min_info`**（见下）。`n_eff_status` 仅作诊断与报告字段。
- `n_eff >= 50` 保留为 **L3 确认前置**（改用实测值）；**探索运行不受其阻断**。若实测 `n_eff` 使全部历史变体不达标，**如实反映**，不得放宽阈值救结果。

**W1.3 DM 显式状态（E6）**

`build_summary` 落 `dm_status ∈ {"ok", "set_mismatch_ok", "set_mismatch_descriptive", "insufficient_common", "no_common_cutoff", "protocol_mismatch", "no_baseline"}`（v12 收敛为 7 个，`d_bar_nonpositive` 降为诊断字段），
并落 `dm_common_count` / `dm_unmatched_variant` / `dm_unmatched_baseline` / `pair_set_hash` / `raw_cutoff_set_hash` / `d_series_n_eff` / `d_bar_le_zero`（诊断）/ `n_avail_variant` / `n_avail_baseline` / `missingness_admissible`；`missing_pattern` / `missing_rate_by_bucket` / `n_missing_*` 为 **L2 诊断**（§7.8 前非强制采集）（配对按共同 cutoff 内连接）。
`insufficient_common` / `no_common_cutoff` / `protocol_mismatch` 时 `p_value=null` **且 stderr 打 WARN**，并计入 supervisor 的可见统计（禁止静默）。

窗口对齐的根因必须一并修：`eval_start` 的奇偶漂移改为**按绝对 cutoff 时间戳对齐**，禁止用位置索引续跑 checkpoint（`aligned_slow_loop.py:116-137` 的 `(symbol, idx)` 键改为 `(symbol, cutoff_ts)`）。

> **作用域标记（v14，消除与 §8.0 的张力）**：上述**窗口对齐根因修复**（`eval_start` 按绝对 cutoff 时间戳对齐、checkpoint 键改 `(symbol, cutoff_ts)`）**属 PR-A1 作用域、受 D5 阻断**，**不在 PR-A6 交付内**。
> PR-A6 交付的仅是 `dm_status` **状态机 + 字段落盘 + fail-loud 告警**，其正确性**不依赖**对齐是否修好。
> **PR-A1 实施前，本节状态机预期以 `insufficient_common` / `no_common_cutoff` 形式暴露该未修复的漂移——此为 fail-loud 设计行为，非缺陷**；
> 运维侧**禁止**把这些 WARN 当噪音过滤（那会重新引入 E6 要根除的静默路径）。

**W1.4 无协变量基线（E7）**

新增 `baseline_points_{sym}_nocov.jsonl`：同一窗口、同一 cutoff、**不传 `past_future_covariates`** 的 TimesFM 运行。DM 检验的对照改为**该无协变量基线**；`ccl` 基线降级为"另一个协变量变体"，仅供诊断对照。

理由：审核意见明确要求"与无协变量的 TimesFM 比较"。用协变量运行当基线，等于在问"这个协变量比 ccl 好吗"，而非"协变量有没有用"。

**W1.5 指纹拆分与区间（E8/E9）— 修订**

> **前一版的缺陷（已废止）**：只有一个 `window_fingerprint`，且 W3.4 要求它"一致"。
> 但前向确认集随数据累积**必然**改变起止时间与样本数 → 该要求与 W3.3 直接矛盾，**无法同时满足**。

拆成两个指纹，**用途严格分离**：

**① `protocol_fingerprint`（协议指纹）— 决定"两次评估是否可比"**

包含一切**不随数据增长而改变**的不变量。两次评估的该指纹必须**逐字节相同**才可比：

| 组成 | 来源 |
|---|---|
| `HORIZON` / `STEP` / `CONTEXT_BARS` / `CONTEXT_DAYS` / `EVAL_WINDOW_BARS` | `config/backtest_config.py` |
| cutoff 约定（`bar_open` / `bar_close`） | D5 裁定结果 |
| 价格序列复权版本 + roll 守卫版本 | D1/D2 |
| `cov_fill_version` | W5 |
| 特征代码 `git_rev` + `covariate_pool_rev` | 代码/配置版本 |
| 模型指纹（权重哈希）+ 预测参数 | 模型层 |
| 指标定义版本（`dir_acc` 口径 + 零变动策略） | W6.5 |

**② `sample_fingerprint`（样本区间指纹）— 仅用于标记"这次实际评了哪些点"**

**必然**随数据累积而变，**不作为可比性条件**：

| 字段 | 含义 |
|---|---|
| `window_start_ts` / `window_end_ts` | 本次实际评估窗口首末 cutoff |
| `window_n` / `window_parity` | 名义点数与相位 |
| `cutoff_list_hash` | 本次 cutoff 序列的哈希 |
| `n_active` / `n_zero_move` / `n_roll_excluded` | 各类剔除计数 |
| `roll_in_horizon_count` | 跨换月 cutoff 数 |

**两层"可比"（v9 修订：协议兼容 ≠ 配对推断可用；DM 用共同样本口径）**

> v7 只规定"`protocol_fingerprint` 相同才可比"，但 DM 检验又要求变体与基线**在相同 cutoff 上配对**。
> **v8 曾把 `pairing_valid` 定为"cutoff 集合一致"，又与"DM 在共同 cutoff 上算"自相矛盾**——集合不一致
> 时应为配对无效，却允许对共同点算 DM。**v9 改为共同样本口径**：不要求集合完全相等，只要
> **共同样本满足最低数量与信息条件**即可配对；集合差异只记录未匹配点，不自动判推断无效。

| 层 | 定义 | 允许 |
|---|---|---|
| **协议兼容** `protocol_compatible` | `protocol_fingerprint` 相同 → 协议设置与指标口径相同 | 纳入同一协议下的**描述**、进一步核验 |
| **配对可计算** `pairing_computable` | 协议兼容 + 共同 cutoff 达 `dm_min_common` + **配对差序列 `d_t`** 的 ESS 达 `effective_min_n` | DM **算得出来**（技术条件） |
| **配对推断可用** `pairing_valid` | `pairing_computable` **且缺失模式可接受**（见下） | **DM 可用于确认**；集合完全一致是特例（更优）而非必要条件 |

**配对推断的落地要求（共同样本口径 + 缺失机制，v10）**：

- **DM 只用共同 cutoff**（按 `cutoff_ts` 内连接）：落 `dm_common_count`、`dm_unmatched_variant`、`dm_unmatched_baseline`。
- **`pairing_computable = protocol_compatible AND dm_common_count >= dm_min_common AND ess(d_t) >= effective_min_n`**
  - **`dm_min_common`**＝**原始共同观测数**下限（配置参数，默认 50）——回答"共同点够不够多"。
  - **`effective_min_n`**＝**配对差序列 `d_t`** 的有效信息量下限——**对象是 DM 实际使用的差序列**，不是共同 cutoff 上的原始预测点；估计口径（HAC/带宽/均值中心化/缺失处理）**必须与 DM 标准误一致**，落 `d_series_n_eff` 单独报告。
  - **两者分别定义、分别报告，不得合并成"同 gate 的 `n_eff>=50` 阶"**（gate 的 `n_eff` 是单模型序列 ESS，对象不同）。
- **缺失机制（选择偏差防护，v12 降级：核心强制 + 记账降 L2）**——共同点可能**非随机缺失**，内连接后样本可能偏离预注册确认集。
  - **核心（强制，进成功判定）**：`n_avail_variant` / `n_avail_baseline`（确认窗口内两边**各自**可用数）、`n_common`（＝`dm_common_count`）、**布尔 `missingness_admissible`**。
  - **L2 诊断（§7.8 裁定前非强制采集，不影响守卫）**：`missing_rate_by_bucket`（时间分桶 + 预定义状态分层的缺失率）、`missing_pattern ∈ {"random","state_correlated","undeterminable"}`、`n_missing_variant_only` / `n_missing_baseline_only`（单边缺失数）。**未采集不得放宽守卫**。
  - **规则**：仅当能**证明**缺失与状态独立 → `missingness_admissible=True`；否则 `False`。
  - **可达性脚注（v11 保留）**：判定"随机"本身需要**证明缺失与状态独立**，而该判定方法**尚待 §7 开放问题 8 裁定**。
    故在 §7.8 裁定前 `missingness_admissible` **恒为 False**（一切确认运行落 `descriptive_only`）——这是**有意的保守默认**，不是缺陷。
- **`pairing_valid = pairing_computable AND missingness_admissible`**。
  `missingness_admissible=False` 时 **DM 仍可算并报告，但只作描述性**，**不得**进入确认（`dm_status="set_mismatch_descriptive"`）。
- **`pair_set_hash`（实际配对集哈希）**：基于**最终进入配对差序列的 cutoff**（共同交集 ∩ 确认集窗口 ∩ 剔除非法点），
  不是未经筛选的原始列表；另存 `raw_cutoff_set_hash`（原始列表）供诊断比对。
- **报告排序禁止**把"协议兼容"写成"同样本可直接排名"——协议兼容但 cutoff 不同的两次运行，其 `dir_acc` 是**描述性排名**，**不等同**于成对的显著优劣。

**`dm_status` 状态与字段矩阵（v10，逐状态规定可生成字段）**

| `dm_status` | `p_value` | `delta_ci` | `pair_set_hash` | `pairing_valid` | 可确认 |
|---|---|---|---|---|---|
| `ok` | ✅ | ✅ | ✅ | True | ✅ |
| `set_mismatch_ok` | ✅ | ✅ | ✅ | True | ✅ |
| `set_mismatch_descriptive` | ✅（仅描述） | ✅（仅描述） | ✅ | **False** | ❌ |
| `insufficient_common` | null | null | ✅（交集） | False | ❌ |
| `no_common_cutoff` | null | null | null（空集哈希） | False | ❌ |
| `protocol_mismatch` | null | null | null | False | ❌ |
| `no_baseline` | null | null | null | False | ❌ |

> **v12 降级**：`d_bar_nonpositive` **不再是状态**——方向命中差均值 $\bar d \le 0$ 只是"本次检验方向未达条件"，
> 这在 DM 检验里**天然由 p 值表达**（p 值大即方向不成立）。降为**诊断字段** `d_bar_le_zero: bool`（照常落盘），
> 状态枚举 **8 → 7**。它**不参与**优先级链、**不改变** `dm_status`；`pairing_valid` 仍只由缺失条件定。

**状态判定优先级（首个匹配者胜，消除处理顺序歧义，v12 缩短）**：
`no_baseline` → `protocol_mismatch`（协议不兼容时**不进入**共同样本计算）→ `no_common_cutoff` → `insufficient_common`
→ `set_mismatch_descriptive`（缺失不可接受）→ `set_mismatch_ok` → `ok`。

> **顺序理由（v11 保留）**：`set_mismatch_descriptive` 位于两个"可确认"状态之前——选择偏差影响的是**推断有效性**（推断框架失效），
> 优先级高于"结果是否好看"。`d_bar_le_zero` 作为诊断字段**不占**优先级位置，故链更短。

**确认集与配对口径统一（v10：`confirm_from_ts` 是预注册固定时间边界）**：
确认集 = **预定 cutoff 序列**中 `cutoff >= confirm_from_ts` 的点 ∩ **两模型共同可用 cutoff 交集**。
`confirm_from_ts` 是**注册时锁定的固定时间边界**（基于日历/可评估起始约定），**不是**"未来实际共同可用 cutoff 的首个观测点"——
后者在注册时**不可知**（未来是否产出有效预测未知），若用它定义就会变成**事后回推**。流程固定为：
① 注册时锁定 `confirm_from_ts`；② 评估该边界之后的**预定 cutoff 序列**；③ 缺失按上述**固定规则**处理（内连接 + 缺失模式判定）；
④ **禁止**通过"寻找两边共同可用的首个点"来移动确认窗口。
**确认性 DM 只在确认集窗口的共同 cutoff 上算**；探索性（描述性）DM 可在全部共同 cutoff 上算，但不用于确认。

**可比性规则（收口）**：`protocol_compatible` 是纳入比较的**前提**；`pairing_computable` 是 DM 计算的**前提**；
`pairing_valid` 是**确认**的前提。三者**都需要，但不是同一个东西**。`sample_fingerprint` 不同属正常，不影响协议兼容。

**区间（两个，不可混用）**：

| 字段 | 口径 | 用途 |
|---|---|---|
| `dir_acc_ci_lo` / `dir_acc_ci_hi` | 单样本比例，用**实测** `n_eff` 的二项 SE | 该模型准确率的**描述性**区间 |
| `delta_ci_lo` / `delta_ci_hi` | **配对** HAC SE（与 DM 同一估计量） | **增量**（相对基线）的推断区间；成功判定读这个 |

**排序与比较的守卫**：supervisor 与报告生成器必须按 `protocol_fingerprint` 过滤后再排序/比较（当前 `known_verdicts.inc.md` 的"best dir_acc"与 tier 排名会跨协议比较，必须加过滤）。`sample_fingerprint` 不同不得成为拒绝比较的理由。

**W1.6 价格序列缺陷裁定（D1/D2/D4/D5）**

- **复权（D1/D2）**：优先修守卫，让 `apply_backward_adjustment_robust` 在生产路径真正执行；1H 路径补 roll 处理。若短期无法修，则**必须**加 `roll_in_horizon` 守卫——跨换月的 cutoff 从 `dir_ok` 分母中剔除（或单独成组报告），且该剔除量必须落盘可见。
- **`bfill`（D4）**：`oi_smooth` / `scale` 的 `bfill` 改因果填充（`ffill` + 冷启动 NaN 显式处理）。禁止用未来值回填。
- **1-bar 前视（D5）**：二选一——(a) 把 cutoff 改为该 bar 的**收盘**时间（`dt + 1h`），使"cutoff 时点已知的信息"与所用值一致；(b) 若维持现状，必须在 verdict 落 `cutoff_convention="bar_open"` 并把该 1-bar 偏差**量化**进报告。推荐 (a)，因为它同时消除 D5 与 D6 的口径歧义。

**W1.7 死表与死配置（D3/C7）**

`xreg_factors` 表在 `data_store.py` 的方法 docstring 标注 `[DEAD TABLE — 预测路径不读取]`；所有分析脚本（含专家报告那类数据量对比）禁止引用其行数。`prediction_scheme.py:132 xreg_covariates` 删除或标注 `[DEAD CONFIG]`。

### 4.2 W2 — 协变量使用诊断

把审核意见的"协变量未利用"从**推断**变成**可验证事实**。

**W2.1 协变量指纹与实验身份（C2）— 修订**

**① `cov_fingerprint`（模型输入矩阵的规范哈希）**

```
{
  "keys": ["daily_slope", "ccl", "rsi_state"],   # 实际送入模型的**有序**键（顺序即通道顺序）
  "matrix_sha256": "<规范序列化后的字节哈希>",
  "n_channels": 3,
  "hash_version": "cov_matrix_hash_v1"
}
```

键取自 `hourly_model.py:211` 的 `covariate_keys`（**实际**集合），不是请求的 `cov_override`。

**规范序列化（必须显式定义，否则相同语义可能得到不同哈希）**：

| 项 | 规定 |
|---|---|
| 键顺序 | 保留 `hourly_model.py:211` 的**实际声明顺序**（顺序即通道语义，**不得排序**） |
| dtype | `float32`，小端 |
| NaN | 统一写成**规范静默 NaN**（`0x7FC00000`），消除不同 NaN payload 造成的哈希漂移 |
| `-0.0` | 归一为 `+0.0` |
| Inf | **禁止**出现在矩阵中；出现即 fail-loud（不得静默哈希） |
| 序列化 | `.astype('<f4').tobytes(order='C')`，再对 `keys` 与字节串按固定格式拼接后 sha256 |

**② 另需单独记录的版本/策略（不进矩阵哈希，但进协议指纹）**

`fill_strategy_version`、`feature_code_git_rev`、`covariate_pool_rev`、`cov_fill_version`（W5）。
否则会出现**输入语义变了但指纹没变**的情况。

**③ `experiment_fingerprint`（实验身份）— 新增**

`matrix_sha256` 相同足以判定"模型输入矩阵相同"，**不足以**判定"整个实验相同"——同一协变量指纹下仍可能把**不同实验**合并记录（模型权重、预测参数、context 窗口、目标序列、复权版本都可能是变量）。故：

```
experiment_fingerprint = sha256(
    protocol_fingerprint        # 协议不变量（W1.5）
  + cov_fingerprint.matrix_sha256
  + model_fingerprint           # 权重哈希 + 预测参数
  + target_snapshot_hash        # 本次实验所用目标数据的【快照内容】哈希（含复权版本）——与 family 键的 research_target_hash 用途不同（§4.3 W3.6 ①）
  + context_hash                # 本次 context 窗口内容哈希（W6.7）
)
```

**`variant_id` 由 `experiment_fingerprint` 派生**（见 W6.4），**不是**由 `cov_fingerprint` 单独派生。

**克隆判定**：`cov_fingerprint.matrix_sha256` 相同 = 同一输入，无论请求名是否不同。禁止再用"指标四舍五入相同"推断克隆。
**实验合并判定**：只有 `experiment_fingerprint` 相同才可视为同一条实验记录。

**W2.2 逐协变量有效性（C2/C3）**

verdict 新增 `cov_effective`，对每个实际键记录：`std`、`n_unique`、`nonzero_frac`、`horizon_std`、`horizon_n_unique`。

判定规则（确定性，写入代码而非文档）：

- `std == 0` 或 `n_unique == 1` → 该通道**必然 no-op**（RevIN），落 `inert_constant=true`
- `horizon_std == 0` → 未来段无外生信息，落 `horizon_flat=true`
- `nonzero_frac == 0` → 落 `all_zero=true`

**静默零填充改 fail-loud**：`features.py:1198/1336/1367/1443-1448/1501` 等路径在零填充时 `stderr` 打 WARN 并把该通道标记进 verdict。零填充审计测试覆盖**全部**协变量类型（关闭 C3 缺口），新增的协变量类型必须同步登记，否则测试失败。

**W2.3 消融范围与效应分离（C6）— v4 收窄**

> **v3 的问题**：要求评估路径"**强制**计算并落盘"三路对照 → 每个 verdict 都跑三路消融，成本与实现复杂度高。

**v4 分三级**：

| 场景 | 要求 |
|---|---|
| **常规变体** | 只需与**无协变量基线**配对（§1.1 L1 已强制），**不跑**三路消融 |
| **固定审计集**（§1.1 L2：7 品种 × 少量代表性协变量；SS/SR/M/JD/LH/CJ/FU，覆盖黑色系+能化+农产品板块） | 跑**完整三路**对照，确认通道结构影响 |
| **异常变体 / 进入确认候选的变体** | 补跑完整三路消融 |

**三路定义**（仅审计集与候选变体）：

- `ablation_content_delta`：真实协变量 vs **清零同形**（同通道数）→ 纯内容效应
- `ablation_structural_delta`：**完全不带协变量** vs 清零同形 → 纯结构性通道效应

- 报告必须**分开呈现**，**禁止**合并成"协变量贡献"。
- **审计集上**必须消除 `visualize=False` 导致的 `baseline_forecast=None`，否则三路无法计算。

理由：实测两者符号相反（C6），合并会把"多塞了通道"误读成"协变量有价值"。但该诊断**不需要每个变体都做**——审计集上确认结构影响即可。

**W2.4 `xreg_fallback` 贯通（C4）**

评估路径消费该标志：`xreg_fallback=True` 的 verdict 落 `covariates_used=false`，**不得**参与成功判定，且 supervisor 统计中单列。回退运行与真实协变量运行必须可区分。

### 4.3 W3 — 预注册与前向确认（Jev 仅建议）

**W3.1 预注册登记（取代自由文本）**

新文件 `task_FM/config/preregistry.jsonl`，append-only，是预注册的**唯一家**：

| 字段 | 说明 |
|---|---|
| `prereg_id` | 唯一 ID |
| `symbol` / `cov_fingerprint_keys` | 假设对象 |
| `mechanism` | 机制陈述 |
| `predicted_direction` | 方向 |
| `kill_condition` / `promote_condition` | **结构化**阈值（数值 + 字段名），非自由文本 |
| `registered_at` | **时间戳（UTC）**，写入后不可修改 |
| `confirm_from_ts` | 确认集起点 = **注册时锁定的固定时间边界**（日历/可评估起始约定），**非**未来实际共同可用 cutoff 的首个观测点；注册后不得移动、不得事后回推（v10，修时间可知性） |
| `jev` | Jev 三问输出快照（plausibility / novelty / effect_size）+ 判定 |
| `n_planned` | 该假设计划评估的点数 |

`_proposal_priority_score` 的 `+1.0` 非空字符串奖励**废除**。入队规则按**运行模式**区分（§1.4）：

- **探索运行**：无 `prereg_id` 亦可入队，产出标 `exploratory_unconfirmed`；
- **确认运行**：**必须**有已锁定的 `prereg_id`，否则不入队。

（v4 此处写"无有效预注册 → 不入队"，与 §1.1 L3 的"未就绪仍可运行"矛盾，v5 按运行模式拆开。）

**W3.2 Jev 定位 — v4 降级为建议，不作科学准入门**

> **v3 的错误**：把 Jev 设为"事前门"（`skip_suggested=True` → 拒绝入队）。
> 结果盲化能减少结果污染，但模型判断"合理性/新颖性"**仍是主观过滤**；
> 把它设为自动拒绝的闸门，会在统计评估**之前**引入一个**难以量化的选择机制**——
> 谁能进入统计家族，部分由一个不可审计的模型判断决定。这与本 spec"用确定性事实替代主观判断"的原则冲突。

**v4 的分工**：

| 角色 | 承担者 | 权限 |
|---|---|---|
| **可判定问题的拒绝** | **确定性规则** | **硬拒绝**：特征缺失、板块不匹配、`mechanism` 字段不完整、`applicable_sectors` 缺失（§4.7 W6.1） |
| **主观判断（合理性/新颖性）** | **Jev** | **仅建议**：写入 `preregistry` 的 `jev` 字段供**人工审阅**；**不拒绝入队**、**不进入成功判定**、**不决定哪些假设进入统计家族** |

- Jev 输出**必须结果盲**（`jev_blind`，上下文不含 `gate_pass`/`dir_acc`/`tier`/`fdr_pass`），否则它继承选择偏差。见 §4.7 W6.2。
- **`jev_*` 属 §1.2 的 C 级字段**：缺失、`degraded` 或超时**均不影响** verdict 有效性与入队。
- 降级路径：`TYPESAFE_API_KEY` 缺失或连续超时 → `status="degraded"`，记录但不阻断。
  （v3 的"降级为人工确认队列"取消——它已不是门，无需阻断。）

**W3.3 确认集定义（取代不存在的留出期）**

- 确认集 = `cutoff >= confirm_from_ts` 的评估点。**注册时该数据不存在**。
- **禁止**用切分现有 588 点来制造确认集：切分后确认集 `n_eff ≈ 29`，SE ≈ 0.093，需 DirAcc ≈ 0.68 才显著——等于确认不了任何东西，是假动作。
- 确认需要日历时间，这是本 spec 的**显式代价**，不是缺陷。
- 复测通道（`_retest_candidates`，checkpoint 只算新点）就是确认集的天然实现，无需新机制。

**W3.4 成功判定换口径**

```
confirmed = (run_mode == "confirmation"           # 确认运行（§1.4），非探索
             AND gate_pass                        # 质量筛选，保留
             AND fdr_pass                         # 统计晋升（真实检验）
             AND p_value is not None
             AND meets_min_info == True           # 最低信息要求（W1.2），非 n_eff_status=="ok"
             AND covariates_used == True          # 非 xreg_fallback
             AND protocol_fingerprint 一致         # 协议兼容（W1.5），非样本区间一致
             AND pairing_valid == True            # 配对推断可用（W1.5）：pairing_computable 且缺失模式可接受
             AND missingness_admissible == True   # v12：缺失非状态相关、原因可判定（§7.8 前恒为 False，保守默认）
             AND dm_status ∈ {"ok", "set_mismatch_ok"}    # DM 在共同 cutoff 上已计算；descriptive/insufficient/no_common/protocol_mismatch 不可确认
             AND 在确认集窗口的共同 cutoff 上，DM 显著优于无协变量基线)   # 该 DM 基于 pair_set_hash 记录的共同 cutoff 集合计算
```

`gate_pass` 退回 v23 §5 本来的角色——**质量筛选器，不是成功**。

**注意**：① 这里要求 `protocol_fingerprint`（协议兼容）**一致**，**不是**"样本与基线窗口完全一致"——确认集本就随数据累积而变（W1.5）。② DM 采用 **共同样本口径**：只要共同样本达标（`pairing_computable=True`）**且缺失可接受**（`missingness_admissible=True`）即可确认，集合不完全一致不自动判无效；但 DM 只在**确认集窗口的共同 cutoff**上算（`pair_set_hash`），集合差异（`dm_unmatched_*`）与缺失诊断（`n_avail_*`/`n_common`）必须保留供审计。**缺失原因不可判定或与市场状态相关 → 仅描述性，不得确认**（选择偏差防护）。③ `run_mode` 为 `exploration` 的 verdict（标 `exploratory_unconfirmed`）**一律不得**进入本判定（§1.4）。

**W3.5 检测边界与功效 — 术语更正（v4）**

> **v3 的术语错误（已废止）**：把 `z = 1.645` 算出的值称为 "MDE"（最小可检测效应）。
> `z = 1.645` 对应**单侧 5% 显著性**，**未指定检验功效**——它给出的是"在当前 n 下多大的效应会显著"，
> 即 **50% 功效下的检测边界**，**不是**通常意义上的 MDE（后者需指定目标功效）。
> 另：v3 内部还自相矛盾（§4.3 用 z=1.645 得 0.598，§4.6/§5 写 0.615 即误用 z=1.96 双侧）。

**① 术语与两个边界量（重命名）**

| 指标 | 定义 | 含义 |
|---|---|---|
| `detection_threshold_vs_random` | `0.5 + z_alpha * 0.5/sqrt(n_eff)` | 方向准确率**相对 0.5** 的显著性边界 |
| `detection_threshold_vs_baseline` | `z_alpha * SE_HAC(d_bar)`，`d_t = v_ok_t - b_ok_t` | 增量**相对无协变量基线**的显著性边界 |

`z_alpha = 1.645`（单侧 α=0.05，与 DM 同侧）。

**这两个量是"显著性边界"，不是 MDE。** 它们回答"多大效应会显著"，**不**回答"以 80% 功效能发现多大效应"。
**禁止**据此断言"某效应不可检出"或据此规划样本量——那需要下一条。

**② 样本量规划（需要目标功效）**

若要规划样本量，必须**指定目标功效** `1-beta`：

```
Var(d)      = 单点配对差值 d_t 的边际方差          # 不含自相关修正
Var_LR(d)   = Var(d) * VIF                        # 长程方差（含自相关）
SE(d_bar)   = sqrt(Var_LR(d) / n)
n_required  = Var(d) * VIF * (z_alpha + z_beta)^2 / Delta^2
```

**计算口径：两条途径，互斥，必须二选一（v5 明确）**

> v4 同时说"实际规划应优先从先导数据估计 HAC 方差"与"公式用边际方差乘固定 `VIF`"，
> 会让实现者**同时估 HAC 方差、再乘固定 VIF**——**重复调整**。故明确为二选一。

| 途径 | 何时用 | 公式 | 性质 |
|---|---|---|---|
| **A. 情景近似** | 尚无先导数据，仅估量级 | `Var(d)`（**单点边际方差**）× `VIF`（规划用相关性因子） | **情景近似**，必须标注为示例 |
| **B. 先导估计** | 已有先导配对数据 | **直接用** HAC 长程方差 `Var_LR(d)`，**不再乘 `VIF`** | 实证口径，**优先采用** |

- **禁止**两条途径混用（例如估了 HAC 长程方差又乘 `VIF`）。
- **阶段 3 核验必须专门覆盖这一点**：断言实现中**不存在**"长程方差 × `VIF`"的路径。
- 公式与代码只允许**一个** `Var(d)` 定义。

**确认检验的损失定义必须唯一（v5 补）**

> v4 把 `d_t = v_ok_t - b_ok_t` 称为"配对损失差"，但这是**方向命中差**（0-1 损失），
> 与 DM 文献中通常的"损失差"（如平方误差差）**不是一回事**。混称会让功效规划与检验口径不一致。

- **本 spec 的确认检验唯一采用方向命中差**：`d_t = v_ok_t - b_ok_t ∈ {-1, 0, 1}`，
  等价于 **0-1 方向损失**；DM 检验在该损失函数下成立。
- **功效规划、DM 检验、`detection_threshold_*` 三者必须使用同一损失定义。**
- 若日后需要检验**预测误差差**（MAE/RMSE 等），那是一个**独立检验**——须有自己的损失定义、
  自己的功效计算、自己的多重比较记账，**不得**与方向命中差混称"配对损失差"。

`z_beta = 0.8416`（80% 功效）。乘数从 1.645 变为 `z_alpha + z_beta = 2.4866`。

**规划情景表（明确标注为示例，非普遍结论）**

> 下表是"**在给定 `rho`、`VIF`、命中率假设下的规划示例**"，用于说明**量级**，
> **不是**"任何情况下都需要这么多点"的普遍结论。

（假设：`p_v≈p_b≈0.50`、`rho=0.5` → `Var(d)=0.25`、`VIF=8.028`、80% 功效；当前 `n=588`）

| 目标增量 `Delta` | `n_required`（示例） | 相对当前 |
|---|---|---|
| 0.02 | ≈ **31,000** | 53× |
| 0.05 | ≈ **5,000** | 8.5× |
| 0.10 | ≈ **1,240** | 2.1× |

**使用约束（v5 新增）**：

- **`VIF=8.028` 只是初始情景**（由 `HORIZON=24`、`STEP=2` 推出的名义值）。真实配对差异序列的方差、自相关、缺失结构与换月剔除比例因品种、时期而异，**不得**在实现中把它当作唯一常数。
- **实际规划应优先从先导数据估计**配对损失差的 HAC 方差，再据此计算所需样本量，并**对估计的不确定性做敏感性分析**。
- **必须区分两件事**：① "**需要很多样本**"是**资源与时间判断**；② "**无论如何都不可检出**"是**统计结论**。后者**不能**仅凭一张假设表得出。
- 因此本 spec **不**声称"0.50–0.52 波段普遍不可检出"。它只说明：**在给定假设下，该波段的量级远小于示例所需样本量**，故**在没有先导估计之前，不应把 0.51 一类小效应写成成功条件**（§7 开放问题 7）。

**③ `rho` 敏感性表 = 规划情景分析，不是实测证据（v3 定位错误）**

`rho` 是对"两模型正确分类事件相关性"的**假设**，且 `VIF` 是对自相关结构的**假设**；
它们**不能**代表所有品种、预测窗口与损失差序列的真实相关结构。因此：

- 该表**仅作规划情景分析**，**禁止**把其中数值写成全项目统一的"不可检出"结论。
- **实际评估时以配对序列的估计为准**（`SE_HAC(d_bar)` 实测），并**报告该估计的不确定性**（`delta_ci_lo/hi`）。
- 若实测 `SE_HAC` 与规划假设差异显著，**以实测为准**并说明假设为何不成立。

| `rho` | `Var(d)` | `SE(d_bar)` | `detection_threshold_vs_baseline`（α=0.05） |
|---|---|---|---|
| 0.0 | 0.500 | 0.0826 | 0.136 |
| 0.3 | 0.350 | 0.0691 | 0.114 |
| 0.5 | 0.250 | 0.0584 | 0.096 |
| 0.7 | 0.150 | 0.0453 | 0.074 |

`detection_threshold_vs_random`（`n_eff=73`）= 0.5 + 1.645 × 0.5/√73 = **0.596**。

**④ 落盘与报告**

verdict 落 `detection_threshold_vs_random`、`detection_threshold_vs_baseline`、`se_hac`（**实测**）、
`delta_ci_lo/hi`、`n_required_for_target`（若已声明目标效应与功效）。规划 `rho` 表只进规划文档，不进 verdict。

**W3.6 多重比较与序贯纪律 — 修订**

> **前一版的缺陷（已废止）**：把 BH-FDR 的 `K` 换成"全局计划数 `n_planned_total`"。
> 这**不足以**定义多重比较：没有定义检验家族、没有封账时点、没有处理
> 陆续到达的检验、未完成的预注册、被放弃/取消的假设，以及确认集逐步累积带来的**序贯检验**问题。

**① 检验家族（family）的定义 — v4 更正（批次不得定义家族）**

> **v3 的错误**：把 family 定义为"同一品种 + **同一批次** + 同一协议"。
> **批次是行政概念**——按批次拆家族等于可以通过多开批次得到多个较小的校正家族，从而**规避校正**。

- 一个 family = **同一研究问题 + 同一预注册系列**内全部**确认检验**。
- **默认：一个品种 = 一个研究问题 = 一个 family**（在同一 `protocol_fingerprint` 下）。
  **批次、运行、代际都不重置校正。**
- **只有确认检验进 family**。探索期结果**不是检验**，不产生 p 值声称，不进 family——这是"探索自由、确认严格"的分界。
- 每个假设在 family 中**恰好一个** p 值：其在确认集上的 DM 检验（W3.5 的配对口径）。

**跨品种错误率范围必须显式声明**（v3 缺失）：

- 本 spec **默认不跨品种合并校正**：每个品种是独立研究问题，各自控制 FDR。
- 因此**结论范围仅限品种内**：报告**不得**产出跨品种聚合声称（如"24 个品种整体有效"）。
  若日后需要跨品种结论，必须**另行定义**一个包含全部品种确认检验的 family 并重新校正。
- 该范围声明必须写进报告模板，与结果同时呈现。

**② 封账、注册截止、未完成检验的 p 值（v4 只靠 `T_max`，**不足以**保证封账）**

> **v4 的缺陷**：只给**单个成员**设 `T_max`。若同一 family 持续接收新成员，成员到期时间不断后移，
> "全部成员终态"的时刻**永远不会到来**——**单成员能超时 ≠ 整族能封账**。

- family 在**全部成员到达终态**时封账，**一次性**运行 BH-FDR。终态四种：`confirmed` / `refuted` / `abandoned` / `timeout`。
- **必须给 family 设注册截止**（二者并用，**先到者为准**）：
  - **时间截止** `family_close_at`：默认 family **首个成员注册后 90 天**；
  - **成员上限** `family_max_members`：默认 **20**。
  **截止后该 family 不再接纳新确认假设。** 这是封账可达的**必要条件**。
- **`T_max` 的起算点（v7 明确，单一时钟）**：从**成员注册时间**（`registered_at`）起算，默认 **180 天**。
  **不是**从"确认开始"或"确认集开放"起算——采用注册时间这一**唯一、可验证**的时钟，避免时钟分叉。
- **已注册但从未获得确认数据的成员**：在 `family_close_at` 封账时若仍未达终态，**立即**落 `timeout` + `p=1`，不等待。
- **封账上界（显式）**：`family_close_at` 时成员集合**固定**；任何成员注册 ≤ `family_close_at`，
  且每个成员在其自身注册后 `T_max` 内到终态，故 **family 最晚于 `family_close_at + T_max` 封账**。
  注册截止（使集合固定）+ 成员 `T_max`（给每个成员一个终止点）二者缺一不可。
- **`p = 1` 的适用范围（v5 收紧）**：**仅当**该假设**已进入确认 family、且在截止前未完成确认**时，才赋 `p = 1`。
  **探索中止、尚未注册确认的假设不得计入确认 family**，也不赋 `p=1`——它们根本不在 `K` 里（§1.4 运行模式）。
  这条区分是必须的，否则会把探索期的正常中止误算成确认 family 的成员，虚增 `K`。
- **`abandoned` 与 `timeout` 仍计入 `K`**。否则"结果不好就悄悄丢掉"= 缩小 `K` = p-hacking。
- **新研究问题必须启动新 family**，且必须规定：① 与旧 family 的**关系**（独立问题 vs 旧问题的延续）；
  ② **报告范围**（新 family 的结论**不得**与旧 family 合并宣称）；
  ③ **禁止**仅用新批次名 / 新 run 绕开校正（见 ①：批次不重置校正）。

**family 边界规则（v7 结构化，取代"实质变化"）**

> v5/v6 用"同一品种 + 同一预测目标 + 同一 `protocol_fingerprint`"+"实质变化"来表达新 family 边界，
> 但"协议指纹任一变化就开新 family"与"实质变化才可"两种读法并存，**留下解释空间**。v7 改为结构化字段判定。

定义 family 键：

```
family_key = (symbol, research_question)
research_question = (预测目标, 预测任务/期限, research_target_hash)

# research_target_hash：研究对象的稳定标识
#   = hash(品种, 目标变量, 价格序列定义, 复权规则版本, 换月规则版本)
```

**`research_target_hash` 必须是稳定定义，不是全量历史内容哈希（v8 修正）**

> v7 把第三要素写成"目标序列哈希"，未限定含义。若它是"截至本次运行的全量历史内容哈希"，
> 那么新增一根 bar、历史数据修订、复权版本变化都会哈希变化 → **同一研究问题被数据自然增长拆成多个 family**，
> 恰恰削弱"换批次/协议版本/模型权重不能重置校正"的防规避意图。

- **`research_target_hash` 只哈希"研究目标本身"**：品种、目标变量、价格序列**定义**、复权/换月**规则版本**。
  **不包括**观测数据内容与截止时间。
- **观测数据内容与截止时间**：另存为 `data_version` / `sample_fingerprint`，**不进** `research_question`。
- **因此**：新增 cutoff、修订历史 bar、复权版本内的小幅数据更新，**不**创建新 family（`research_question` 不变）；
  只有**目标变量定义、预测期限、价格序列定义、复权/换月规则版本**变化才创建新 family。
- **与 `experiment_fingerprint` 中 `target_snapshot_hash` 的用途区分**（v8）：
  - `research_target_hash`（family 键用）= **研究问题身份**，稳定；
  - `target_snapshot_hash`（experiment_fingerprint 用，§4.2 W2.1③）= **本次实验所用数据快照**的内容哈希，随运行变化。
  **二者不得混用**：前者决定"是不是同一研究问题"，后者决定"实验记录可否合并"。

**`research_target_hash` 序列化规范（v10，锁死跨实现字节级确定性）**

| 项 | 规定 |
|---|---|
| 输入顺序 | `symbol \| target_var \| price_series_def \| adjust_roll_rule_version`（固定，有序） |
| 前缀参与 | schema 前缀 `research_target_v1\|` **参与**最终 SHA-256 输入（是输入字节的一部分，不是元数据） |
| 分隔符 | `\|`（U+007C）；字段值为枚举/规范化 id，**禁止**含 `\|`；出现即 **fail-loud**（不做静默替换，避免碰撞） |
| 规范化 | 全小写、去两端空白；枚举 token 用**单一规范拼写**（无别名）；Unicode 做 **NFC** 规范化；顺序无关列表先排序再拼 |
| 空串 / 缺失 | **不区分**——两者统一编码为哨兵 `__none__`（**不用** Python `None` 的字符串，避免 "None" vs "none" 分叉） |
| `symbol` 规范拼写 | 由**品种主数据表**（`config/sector_map.py` 为唯一权威源）维护；哈希前必须过该规范化函数 |
| 算法 | `sha256`，UTF-8，规范字节后哈希 |

- 字段含义：`symbol`（规范化品种 id）；`target_var`（目标变量枚举 token）；`price_series_def`（价格序列定义枚举：OHLC/close、合约族、周期）；`adjust_roll_rule_version`（复权+换月**规则版本号**，semver 字符串）。
- **不变**：新增 cutoff、历史 bar 修订、复权版本内小幅数据更新 → `research_target_hash` 不变。
- **随运行变**：同一 family 下实验数据快照 → `target_snapshot_hash` 变（`research_target_hash` 不变）。
- **测试（§5.3 61 扩展）**：新增 cutoff/修订 bar → `research_target_hash` 不变且 `target_snapshot_hash` 变；**给定一组固定输入，断言其精确 SHA-256 值**（golden hash，不是"两实现相同"）——空串与缺失同值、含 `\|` 触发 fail-loud、NFC 与 NFD 输入同值。

- **同一 `family_key` ⇒ 同一 family。** 新 family **仅当 `research_question` 三要素任一变化**。
- **`protocol_fingerprint` 中与"研究问题"无关的字段变化**（如 `cov_fill_version`、指标版本、模型权重、特征代码版本）：
  **不**开启新 family——否则协议升级就会重置多重比较、规避校正。
- **"新批次"、"新 run"、更换协变量组合、更换协变量族**：**不**构成新 family。
- 判定是**结构化字段比较**（确定性），**不是**人工裁量"实质变化"。
- 开启新 family 时，`preregistry` 必须记录 `research_question` 三要素的**旧值 → 新值**（可审计）。

**边界测试（§5.3）**：换 `cov_fill_version` 不产生新 family；换 `HORIZON` 产生新 family；换目标序列产生新 family；换协变量组合不产生新 family。
- `preregistry` 每条记录**必须**最终落到一个终态。这是强制机制，不是建议。
- `K` 取**该 family 的成员数**，不是全局计划数。`n_planned_total` 仍登记，但**仅用于资源控制，不是 BH 的 K**。

**③ 序贯问题：默认 no-peek + 固定确认样本量**

- 注册时按 W3.5 的功效计算**预定** `n_confirm_required`；达到后**只测一次**。**禁止中途查看确认数据**——no-peek 是预注册的核心，反复查看会使名义 α 失效。
- 若确认数据到达慢于预期，允许**提前封账**并如实落 `n_confirm_actual < n_confirm_required`，结论标 `underpowered`；**不得**因"再多看一点"而反复查看。
- 若宿主确需中期查看，必须改用有明确错误率控制的**序贯方案**（如 O'Brien-Fleming alpha spending），且该方案**必须在注册时声明**并预先固定查看次数与边界。**本 spec 默认 no-peek**；序贯方案不在默认范围。

**④ 预算**

`praxist_goal.yaml` 的 `max_cycles: 999999` / `cpu_hours: 999999` / `token_budget_m: 999999` / `deadline: 2099-12-31` 是**无界搜索**，与预注册纪律直接冲突，改为按 §4.6 的阶段预算。

**⑤ 探索自由**

未预注册的变体**可以继续探索**，但**不计入成功判定**，且必须落 `prereg_id=null` 以示区分。探索结果的报告必须标注"非检验"。

**W3.7 确认独立性锁定（新增）**

> **前一版的缺陷**：只规定"确认集 = 注册后的 cutoff"，但没规定注册后**是否还能继续调参**。
> 若允许，确认集就会逐渐变成新的探索集。

- **注册时冻结**：协变量集合（`cov_fingerprint`）、模型指纹、预测参数、`HORIZON`、指标定义版本、`n_confirm_required` 一并写入 `preregistry`，写入后**不可修改**。
- **任何改动 → 新 preregistration**：改协变量、改参数、改 horizon、换模型，一律生成**新** `prereg_id`；新确认集只能使用**尚未观察**的 cutoff。**禁止**沿用旧 `prereg_id` 的确认数据。
- **确认期内禁止**用确认集结果做任何选择（调参、筛选模型、挑协变量）。一旦发生，该 `prereg_id` 作废并标 `refuted_by_contamination`。
- **数据可用性按实际发布时间判定**：低频数据（库存、存栏、月报）以其**实际公布时间**决定在某个 cutoff 是否可用，**不得**按观测日期或数据所属期间。这是防"发布滞后前视"的唯一正确口径，也是 W5 `known_ahead` 判定的事实基础。

### 4.4 W4 — 协变量库诊断（v4 延后自动归档）`[L2 诊断]`

> **v3 的问题**：把"8 品种 / 2 板块 / 60% 惰性"当作**自动归档门**。
> 这组数字是**治理阈值**，不是协变量有效性的科学定律；自动归档容易把覆盖较少或分布不均**误判为"族无效"**。

**v4 处置：先出诊断矩阵，不自动归档。**

**① 输出诊断矩阵（本轮交付物）**

- `task_FM/config/covariate_family_verdict.json`：**族×品种矩阵**，每格含
  `inert_constant` / `all_zero` / `ablation_content_delta`（若有）/ 证据指针。
- **必须显式给出分母** `n_evaluated(cov)`，不得只给百分比。
  `n_evaluated` 定义：有 verdict **且** `protocol_fingerprint` 一致 **且** `covariates_used == True` 的品种数。
- 无法计算的品种（数据缺失/构造失败）**不计入分母**，且必须单列"不可计算品种"清单。

**② 阈值降为诊断标注，不作自动归档**

- `n_evaluated >= 8`、覆盖板块 `>= 2`、惰性占比 `>= 60%` 仍**计算并展示**，但只作**研究者审阅提示**。
- 未达覆盖的协变量标 `insufficient_evidence`（**不归档也不保留**，待补数据）。
- **禁止**在积累实际案例之前启用自动归档。

**③ 归档的最终决定权在人**

- 研究者审阅矩阵后决定归档；归档写入 `covariate_pool.json`（标 `archived`，**不删除**，保留可追溯）。
- **单品种惰性不整族归档**（族在某品种有效、在另一品种惰性要能分别判定）。
- 日后积累实际案例，再评估哪些规则适合自动化。

### 4.5 W5 — horizon 尾填充（**已裁定：纳入本轮修**）

**事实（C5）**：每个协变量的 horizon 尾段都是常数（zeros / 末值 / decay），实测 `hz_std=0, hz_uniq=1`。经 per-variate RevIN 后常数尾归一化为 ~0，**未来段不含任何外生信息**。协变量只能通过 context 编码间接影响预测——C6 实测的内容效应（0.335%）就是在该天花板下的表现。

**宿主裁定：本轮修。** 这是**现有架构缺陷**，不是"新增基本面协变量通道"，故不违反 §3 范围。

#### W5.1 协变量按"未来可知性"强制分类

`task_FM/config/covariate_pool.json` 每个条目**必须**新增 `horizon_known`，取值为**受控词表**四选一。缺失即校验失败（禁止默认值兜底）：

| `horizon_known` | 含义 | horizon 填充策略 | 是否算外生信息 |
|---|---|---|---|
| `known_ahead` | cutoff 时点**确实已知**未来值（日历、合约到期日、已公布的排产/节假日） | 填**真实未来值** | ✅ 是 |
| `persistence` | 未来不可知，但可用末值延续近似 | 填**末值** | ❌ 否（RevIN 下 ~0，必须标记） |
| `self_referential` | 未来值来自**模型自身输出**（现状：`daily_slope`、`rsi_state` 取自 TimesFM 日线预测） | 现状保留，但**必须标记** | ❌ 否（自引用，不得当外生） |
| `unknowable` | 既不可知也无法近似（库存、持仓、基差、基本面） | 填**末值** + 标记 | ❌ 否 |

**唯一家**：该分类只写在 `covariate_pool.json`，代码、文档、报告一律读它。禁止在 `features.py` 里按协变量名硬编码判断。

**`known_ahead` 的证据格式（必填，缺失即校验失败）**

`known_ahead` 是四类中**唯一引入未来信息**的一类，准入必须有可核验的证据：

```
known_ahead_evidence: {
  source:           "<数据来源，如 交易所交易日历 / 合约挂牌公告>",
  publication_rule: "<何时可得：如 每年12月公布次年日历>",
  publication_lag:  "<公布到可用的时滞>",
  reconstructable:  "<历史可重建方式：能否用 cutoff 时点当时可得的信息复原该未来值>",
  verified_by:      "<具名>",
  verified_at:      "<ISO 日期>"
}
```

- `reconstructable` 必须说明**用 cutoff 时点当时可得的信息**能否复原，**不是**"今天能不能查到"。
- **日历特征必须区分两类**：
  - **固定日历**（周末、法定节假日安排）→ 可标 `known_ahead`；
  - **交易所临时调整**（临时更改交易时段、临时休市、夜盘调整）→ **不是** `known_ahead`，除非当时已公告；默认按 `unknowable` 处理。
- 缺 `known_ahead_evidence` 的协变量**不得**标 `known_ahead`——降级为 `unknowable` 并打 WARN，**不得静默**。

#### W5.2 填充实现

- `known_ahead` 类：从**cutoff 时点可确定的来源**取未来值。日历类可由 `generate_trading_dates` 直接生成；合约到期类由合约日历生成。**禁止**从任何含未来数据的表取值。
- 其余三类：填末值（替代当前 zeros/decay），并落 `horizon_fill="persistence"`。
- **`horizon_std > 0` 只允许出现在 `known_ahead` 类**。其余类 `horizon_std == 0` 是**预期行为**，落 `horizon_flat=true` 并计入 §4.2 的有效性字段。

#### W5.3 前视防护（本工作包的安全关键项）

修 horizon 填充**最容易引入前视**。必须有不变量：

1. `features.py` 的 horizon 填充函数**只接受** `horizon_known` 参数决定分支，不接受协变量名。
2. 新增测试：对每个 `horizon_known != "known_ahead"` 的协变量，断言其 horizon 段**逐值等于** context 末值（即确实是 persistence，而非泄漏了真值）。
3. 新增测试：对每个 `known_ahead` 协变量，断言其 horizon 值**可由 cutoff 时点已知的输入重算得出**（构造用例：改变 cutoff 之后的数据，horizon 填充值不得改变）。
4. 变体评估若使用了 `known_ahead` 协变量，verdict 落 `horizon_exogenous=true`；否则 `false`。§4.3 的成功判定**不因该字段加分**——它只用于诊断"这次评估是否真的拿到了未来信息"。

#### W5.4 验收标准 — v4 修订

> **v3 的两处缺陷**：① 未定义"显著"；② 把"统计证据"与"实际意义阈值"混在同一个判定里。
> 另需明确：本项是**架构诊断验收**，**不等同于**方向预测成功。

**比较设计（必须配对）**：同一 `protocol_fingerprint`、**同一组 cutoff**、同一 context 窗口、同一预测协议，**只改** horizon 尾填充策略。**禁止**跨窗口比较。

**"配对"的可辩护定义（v5 收紧）**：要求写成"**在同一 cutoff、同一目标、同一预测协议下，成对比较预测误差或命中结果**"；**只有当模型权重确实相同时**才声明"同权重"（`model_fingerprint` 逐字节相同）。若尾填充策略的改变导致了模型调用路径变化（例如协变量张量形状改变），则**不得**把"共享权重"当作默认事实，必须实测确认。

**两个独立条件**（v4：分开呈现，不合并）：

| # | 条件 | 性质 | 判据 |
|---|---|---|---|
| 1 | **统计证据** | 效应能否与零分辨 | 配对 HAC 95% CI **下界 > 0** |
| 2 | **实际意义** | 效应是否大到值得关心 | `|ablation_content_delta| >= floor` |

**两者都满足**才通过；但**报告必须分开陈述**——条件 1 不成立是"**无证据**"，条件 1 成立而条件 2 不成立是"**有证据但效应过小**"，二者含义完全不同。

**`floor` 的定义（v3 未定义清楚）**：

- 单位：占**该 cutoff 价格水平**的比例（`price` 取该 cutoff 的 `base`，见 `monthly_backtest.py:309`）。
- 跨 cutoff 聚合：取审计集内各 cutoff 的**中位数**，并报告四分位区间。
- **必须在运行前预注册**；`floor` 属**架构诊断阈值**，**不得**用作自动归档条件（见 §4.4）。

**验收清单**：

1. 至少一个 `known_ahead` 协变量（预期 `calendar_cyclical`）满足 `horizon_std > 0`。
2. 该协变量的 `ablation_content_delta` 按上述**两个独立条件**判定。
3. **若不通过 → 如实报告**：说明该架构下外生信息的可达增益有限，W5 的收益上限被证实。**禁止**改 `floor`、换比较设计或加 cutoff 来凑通过。
4. 全部非 `known_ahead` 协变量的 `horizon_flat` 标记与实际一致（不得有漏标）。

**性质声明**：本项通过**只**说明"尾填充使协变量在预测期产生了可分辨的输入效应"，
**不**说明方向预测变准，**不**构成成功判定的一部分（成功判定见 §4.3 W3.4）。

**注**：W5 会改变协变量的输入矩阵，因此 **W5 落地后全部历史 verdict 不可与新 verdict 比较**。§4.1 W1.5 的窗口指纹必须扩展一位 `cov_fill_version`，跨版本比较一律禁止。



#### W5.5 宿主裁定记录（v15 追加，2026-09-28）

> 本节记录 W5 分类的具体裁定与可执行校验规则。W5.1–W5.4 是通用框架；本节是首个落地案例。

**① 分类逐项确认**：

| 协变量 | `horizon_known` | 依据 |
|--------|----------------|------|
| `calendar_cyclical` | `known_ahead`（**有条件**） | 构造源限定为「公告日之前的既定日历 + 截至构造时点已公告的调整」。核验判据：**公告时间戳 ≤ cutoff**（与 D5 裁定相交） |
| `rsi_state` | `self_referential` | horizon 尾值取自 TimesFM 自身日线输出（PR-B5 消融实证） |
| `hourly_slope` | `self_referential` | 同上 |
| `ccl` | `unknowable` | 库存类，cutoff 时点无未来可得来源 |
| `oi` | `unknowable` | 持仓类，cutoff 时点无未来可得来源 |

**② `known_ahead_evidence` 六字段的填写与准入规则**：

- **填写人**：宿主（研究侧身份）。agent 身份写入 `verified_by` 即 schema 校验失败。
- **合法取值白名单**：`verified_by ∈ {host, designated_researcher}`（可扩但须显式登记）。
- **填写时机**：协变量**首次注册**进协变量库时填。不可追溯补填。
- **降级规则**：历史已注册条目缺证据 → 降级 `unknowable` + WARN。
- **升级**：补齐宿主确认后允许升级回 `known_ahead`，但**升级时点之后产生的裁决才可用该信息资格**；历史裁决不追溯改变。

**③ 降级的可执行语义（schema 与填充路径一致）**：

- 分类值驱动填充策略（spec W5.2 表格第三列的映射）。
- 标签降级时填充行为**必须同步降为「填末值」**（即 `persistence` 路径）。
- **禁止**：分类标 `unknowable` 但仍走 `known_ahead` 的「填真实未来值」代码分支。
- 校验入口：协变量加载时断言 `(horizon_known == "known_ahead") iff (走 known_ahead 填充路径)`。

**④ calendar_cyclical 构造源的核验规则**：

- 每个日历调整记录必须带**公告时间戳**（`announced_at`）。
- 构造时断言：`announced_at <= cutoff` 的条目才参与 `calendar_cyclical` 构造。
- 不满足则降级 `unknowable` + WARN。
- `known_ahead_evidence.source` 须写明数据来源（如 "exchange X holiday calendar + exchange公告存档"）。

**⑤ Schema 校验（PR-C6 实施项）**：

- `known_ahead_evidence.verified_by ∈ {host, designated_researcher}`，否则注册失败。
- `horizon_known ∈ {known_ahead, persistence, self_referential, unknowable}`。
- `horizon_known == known_ahead` 时 `known_ahead_evidence` 六字段**全部必填**。
- 校验失败 → 降级 `unknowable` + WARN（不进注册但可继续运行）。

### 4.6 阶段二 — 品种分级（全局 24 品种）

按 W1–W4 落地后的新口径重跑，对全部 24 个目标品种出统一判定：

| 判定 | 条件 | 处置 |
|---|---|---|
| **可预测** | 存在 ≥N 个 `confirmed` 变体，且按裁定后的目标效应与功效可分辨 | 正常目标 |
| **需更多样本** | 效应量疑似存在，但当前 `n` 不足以按目标功效分辨 | 给出**所需 n 与预计日历周期**（按 §4.3 W3.5② 公式），不靠刷变体 |
| **当前不可验证** | 即使累积到可用历史也无法按目标功效分辨（如短历史品种实测 `n_eff` 过低） | **停止探索**，如实报告边界 |

**N 由该品种自身功效计算得出**，不是全局常数——短历史品种的 N 更高（更难确认）或直接判为不可验证。

**品种状态改为派生**：`symbol_status.json` 的手写 `DEAD`/`HOLD`（现为 eg=DEAD、jd/lh=HOLD）退休，改由上述判定**计算**得出，代码可复现。手写状态是临时绷带，与"全局统一口径"直接冲突。

**成功条件重写**（`praxist_goal.yaml`）：从 `n_gate_pass_variants >= 10` 改为 `n_confirmed_variants >= N(该品种)`。现 Phase 1 的 `avg_dir_acc_gate_pass >= 0.51` 同样作废——0.51 作为**绝对水平**低于 `detection_threshold_vs_random`（0.596），作为**相对基线的增量**（约 0.01）又低于规划情景下的 `detection_threshold_vs_baseline`（0.074–0.136，α=0.05）。**两条路径都不达标**（§4.3 W3.5）。

> **重写前必须完成 §7 开放问题 7（目标效应与功效）的裁定**：`N(该品种)` 与分级门槛都取决于该裁定；未裁定前不得写入 `praxist_goal.yaml`（§8.5 硬约束 3）。

### 4.7 W6 — 污染控制与提案质量门

治 §2.5 的三类污染。**本工作包与 W1–W5 同等优先**：W1–W5 修的是"测量"，W6 修的是"被测量的对象本身如何被生成"。

#### W6.1 提案质量门（治 Y1 / Y6）— 宿主已裁定；**属后续提案治理** `[L2/L3 后续，不与三项硬门绑定]`

> **v5 定位**：本项的通用类/板块专属类分类与检验较细，属**提案治理**范畴。
> 若本轮只做测量修复（三项硬门，§1.1），**可以延后实施**——它**不属于** L1 硬门，
> 也不阻塞 L1 交付。实际启用板块门时再落地。

`mechanism` 从"≥40 字符"改为**可证伪的结构化声明**，四个必填字段：

| 字段 | 要求 |
|---|---|
| `driver` | 驱动变量（必须是该协变量构造中真实存在的量） |
| `channel` | 传导路径（从 driver 到该品种价格的因果链） |
| `expected_sign` | 预期符号 |
| `test_point` | 可观测的检验点（若机制为真，应在何处看到什么） |

**W6.1a 协变量按构造来源分两类（宿主已裁定：接受自动判据）**

判据是**构造来源**，可从 `features.py` 逐行核验，不需要逐个协变量人工裁定：

| 类别 | 判据 | `applicable_sectors` |
|---|---|---|
| **通用类** | 构造函数**只读目标品种自身**的 kline 列（价格/持仓/成交/仓单）→ 机制上对所有品种成立 | `["*"]`（全板块） |
| **板块专属类** | 构造函数需要**外部或关联市场**数据 | **必须枚举**板块 |

**通用类（`["*"]`）**：`oi`、`ccl`、`nvi`、`vor`、`stddev`、`bb_squeeze`、`hurst`、`rsi6/12/24`、`rsi_slope`、`rsi_state`、`ha_body`、`qstick`、`ao_accel`、`reversal_shadow`（含 `_gated_02/03/05`）、`vwap_deviation`、`hourly_slope`、`gated_slope`、`regime_gated`、`calendar_cyclical`、`pca_momentum`、`daily_slope`。

**板块专属类**：`crack_spread_level/slope/zscore`、`basis_momentum`、以及未来任何跨品种代理类。

**W6.1b 板块词表补齐（前置条件，宿主已裁定 L/PP 归入能化链）**

`sector_map.py` 现状**不足以支撑本检查**：

| 问题 | 现状 |
|---|---|
| 只有 3 个板块 | `black_metals` / `energy_chem` / `agri` |
| 24 目标品种中 4 个不在任何板块 | **y（豆油）、px（对二甲苯）、oi（菜油）、sc（原油）** → `sector_of()` 返回 `"other"` |
| L、PP 未收录 | 宿主已裁定二者归**能化链** |

**处置**：扩充 `config/sector_map.py`，使 24 个目标品种**全部**有归属，并把 `l`、`pp` 并入 `energy_chem`：

- `energy_chem` 增：`l`、`pp`、`px`、`sc`
- `agri` 增：`y`、`oi`

**风险与必做检查**：`sector_map.py` 自述"全项目唯一板块表"，且被 **Regime / VolRisk R1 / Neutral A/B Domain-Shift 审计**共用。扩充会改变这些消费者的行为（原先落入 `"other"` 的品种将获得板块归属）。因此：

- **必须**对上述三个消费者做影响检查并出证据（哪些判定会变、变成什么）；
- **禁止**为绕开影响而在 `features.py` 或 harvest 里另硬编码一套板块集合（违反"唯一板块表"约定）。

**W6.1c `other` 板块策略**

若 `sector_of(symbol) == "other"`（词表扩充后应为空集，但必须防御）：

- **禁止**因 `other` 而拒绝**全部**协变量（那会让该品种永久无法入队）。
- 策略：`other` 品种**只接受通用类**（`["*"]`）协变量；板块专属类一律拒绝并落 `reject_reasons.sector_unknown`。
- 该情况必须**落盘可见**（stderr WARN + 计数），不得静默。

**W6.1d 判定逻辑 — 修订**

- harvest 时校验：`applicable_sectors == ["*"]` **或** `sector_of(symbol) ∈ applicable_sectors`。不匹配 → **拒绝入队**。
- 缺失 `applicable_sectors` 即校验失败（**禁止**默认"全部适用"兜底）。

**跨板块例外的 v4 处置（简化）**

> v3 一度允许"文本非空即通过"（把 Y1 带回来），后又升级为复杂许可治理。
> v4 采用**最简规则**，避免为罕见需求建设复杂治理。

- **默认规则：不匹配即拒绝，无例外。**
- **确有业务需要时**，由**人工审核**在 `covariate_pool.json` 该协变量条目下新增明确许可：
  `cross_sector_approved: [{symbol_or_sector, approved_by, approved_at, basis}]`
- 闸门检查的是**已留档的许可记录**，**不是**提案里的自由文本——**提案无法自我授权**。缺 `approved_by` / `approved_at` 任一 → 许可无效。
- **`basis` 是审计要求，不是代码可验证条件**：代码无法判断"理由是否可复核"，故**不得**假装它是确定性门。测试只断言字段**存在**，不断言其内容质量。
- 许可**按品种或板块**逐条授予，不是全局开关。
- `cross_sector_*` 属 §1.2 的 **C 级字段**，其存在与否不影响 verdict 有效性。

这一条直接拦掉 `crack_spread` 类提案（原油炼化 ≠ 生猪/白糖/螺纹钢/红枣/豆粕/不锈钢）。**禁止**用 LLM 判断"机制是否合理"来替代该检查——sector 匹配是确定性事实（§6 决策 12）。

#### W6.2 Jev 结果盲化（治 Y2）— **v4 降级为建议通道**

`_extract_relevant_history` 现注入 `gate_pass=True` 过滤后的历史。这使 Jev 的"合理性/新颖性"建立在被污染的选择结果上，**Jev 因此不是独立先验**。

**v4 处置**：保留结果盲化（成本低、减少污染），但 **Jev 不再是门**——它只产出建议：

| 调用 | 上下文 | 用途 | 权限 |
|---|---|---|---|
| `jev_blind` | **结果盲**：只给机制文本、品种 sector、协变量的**构造定义**；**不得**含 `gate_pass` / `dir_acc` / `tier` / `fdr_pass` / near-miss 列表 | 写入 `preregistry.jev` 供**人工审阅** | **仅建议**，不拒绝、不参与成功判定 |
| `jev_informed` | 现行含战绩上下文 | 仅诊断 | 禁止进入任何判定路径 |

- **确定性规则负责拒绝**（§4.7 W6.1），Jev 不承担拒绝职责。
- `jev_informed` 的输出与建议字段物理隔离（不同键名 + 测试断言不可互读）。
- **`jev_*` 为 C 级字段**：缺失不使 verdict 无效。

理由：用被污染的历史去"预筛"，是把选择偏差洗成看似独立的判断；而即便盲化，**模型判断仍是主观过滤**，作为自动拒绝闸门会在统计评估前引入不可量化的选择机制。

#### W6.3 提案归属（治 Y5）— v4 降为 C 级可选

verdict 记录 `proposer_model`、`proposer_provider`、`run_id`、`peer_role`。

> **v3 的错误**：要求"缺失即校验失败"。但当前研究**并不比较提案模型**，
> 这些字段**不是验证预测结果的必要字段**——非关键元数据缺失不应让整个 verdict 无效。

- 归入 **§1.2 C 级（治理分析可选）**：缺失**不使** verdict 无效，也不影响入队与成功判定。
- 价值：使"opus 提案 vs qwen failover 提案"可分解——**仅当**日后要做提案来源分析时才需要。
- 采集成本低，故**默认采集**；但**不作强制**。

#### W6.4 身份与去重（治 X5 / X6 / X7）— 修订

- `variant_id` 改为**由 `experiment_fingerprint` 派生**（§4.2 W2.1③）：`{symbol}_{cov_family}_{experiment_fingerprint[:12]}`。请求名降级为 `cov_requested` 仅保留可读性。**禁止**用请求名作身份键。
  - 注意：派生自 `experiment_fingerprint` 而非 `cov_fingerprint`——模型权重、目标序列、context 变化都构成不同实验，必须换 id。
- `load_snapshot` 的 last-wins 改为**按 `protocol_fingerprint` + `experiment_fingerprint` 分组**；同一 `variant_id` 在不同 `sample_fingerprint` 下视为**不同记录**，禁止静默覆盖。
- checkpoint 键从 `(symbol, idx)` 改为 `(symbol, cutoff_ts, experiment_fingerprint)`；`protocol_fingerprint` 或 `cov_fill_version` 变化即**作废重算**，禁止复用位置索引。

#### W6.5 指标口径统一（治 X9 / X10 / Z3）— **宿主已裁定：重算**

**① `dir_acc` 分母口径与强制报告（前一版只说"剔除"，未规定报告与选定规则）**

- `dir_acc` 只保留**一个**定义。零变动点（`|Δreal| < eps`）从分母**剔除**——零变动既非命中亦非失误，判负会机械压低 `dir_acc`（rb 实测 2.0%）。
- **必须同时落盘并报告**（缺任一项即 verdict 不完整）：

| 字段 | 含义 |
|---|---|
| `n_dir_total` | 名义点数（剔除前） |
| `n_dir_active` | 实际进入 `dir_acc` 分母的点数 |
| `n_zero_move` | 零变动剔除数 |
| `n_roll_excluded` | 跨换月剔除数（若启用 roll 守卫） |
| `n_zero_ratio` / `n_roll_ratio` | 上述两者占 `n_dir_total` 的比例 |
| `dir_acc` | **主口径**（预注册约定，见下） |
| `dir_acc_full` | 不剔除任何点的原始口径 |
| `dir_acc_ex_roll` | 仅剔除跨换月、不剔零变动 |

- **主口径选定规则（v5 修正：不阻断 L1 交付）**：
  - **探索运行**：使用**固定默认值**（剔零变动、**不**剔跨换月）并**记录在 verdict 中**，**不要求**预注册——**不阻断 L1 交付**。
  - **确认运行**：必须在 `preregistry` **运行前**声明主口径，否则**不得确认**。
  - 跨换月一律作为**敏感性**单列报告。
- **禁止**只剔跨换月就当作主口径——不同品种/不同阶段的换月频率不同，会造成样本构成差异，使跨品种比较失真。
- 报告必须**同时呈现**主口径与敏感性口径，并列出各类剔除数与比例。

**③ 换月不能靠"默认不剔除"解决（v4 补）**

> v3 把主口径设为"不剔跨换月"，同时承认 `roll_in_horizon` 是标签污染风险——**这自相矛盾**：
> 默认不剔除不等于问题不存在。

必须先判定换月对 label 的影响属于**哪一类**：

| 情形 | 判据 | 处置 |
|---|---|---|
| **label 不可解释** | 跨换月 cutoff 的 `Δreal` 主要由**拼接跳变**贡献，而非真实价格变动 | **数据有效性问题**：修复（复权）或**排除**该 cutoff，**不得**留在主口径 |
| **仅敏感性** | 已复权/已修正，跨换月不改变 `Δreal` 的经济含义 | 可留在主口径，但**必须证明它不主导结果** |

**"证明不主导"的可操作定义**：报告 `dir_acc` 与 `dir_acc_ex_roll` 两值，给出两者差值及其**配对 CI**；
仅当差值在多数品种上不显著、且量级远小于目标效应时，才可称"不主导"。**禁止**仅凭"默认不剔除"结案。

**量化前置**：必须先测出跨换月 cutoff 的**占比**（`n_roll_ratio`）与其对 `dir_acc` 的影响；
占比不可忽略时，一律按"数据有效性问题"处理（即修复或排除），不得降级为敏感性。

**② 其他**

- active-only 口径**改名** `active_dir_acc`，仅 gated 路径使用，消除同名两义。
- tier 的 `neff_score` 改用实测 `n_eff`；若实测后仍近乎常数（现只取 7 或 10），**从 tier 中移除该项**，而不是留一个不 discriminate 的分量制造虚假粒度。
- tier 的 `prescreen_score` 改用 `jev_blind`（W6.2），切断 Z4 环路。

**历史 verdict 的重算（宿主裁定：重算）**

重算是**离线后处理，不需要重跑模型**：checkpoint（`data/cache/aligned_checkpoints/<variant_id>.jsonl`）逐点存有 `delta_real` 与 `dir_ok`，基线文件（`baseline_points_*.jsonl`）同样。因此 143 条 verdict 的新口径 `dir_acc` 可在秒级重算完成。

- 重算脚本必须**幂等**且**只写新字段**（`dir_acc_v2` / `n_zero_move`），**不覆盖**原 `dir_acc`——保留原值以便对照口径差异。
- 重算覆盖：`dir_acc`、`dir_acc_full`、`dir_acc_ex_roll`、`n_dir_active`、`n_zero_move`、`n_roll_excluded`、`n_zero_ratio`、`n_roll_ratio`、`effective_min`、`gate_pass`、`detection_threshold_vs_random`、`detection_threshold_vs_baseline`、`dir_acc_ci_lo/hi`、`delta_ci_lo/hi`、`d_series_n_eff`（**有基线时可算，否则 `null`**）。
  > **v13 命名澄清（勿混淆）**：`effective_min` 是 **gate 的品种自适应阈值**（v23：`max(0.50, min(0.52, baseline_dir_acc))`），**不是** W1.5 的 `effective_min_n`（配对差序列 ESS 下限）——二者**同名不同物**，重算清单保留 `effective_min` 正确，另**增** `d_series_n_eff` 以覆盖 v10 后的配对口径。

**必须同时说清（不得混淆）**：重算**只解决口径，不解决窗口漂移**。历史 verdict 不可比的主因是 X7（checkpoint 按位置索引续跑 → 单条记录内部可能混两个窗口）与 E9（窗口随数据末端滑动）。**重算救不了这个**。因此：

- 历史 verdict 重算后仍标记 `legacy_untrusted`，**仅用于探索记录，不得用于选型或成功判定**；
- 要让历史 verdict 恢复"可参与选型"，必须按新协议**重跑慢环**（143 变体 × 588 点），属另一个量级的预算，**需宿主单独批准**，不在本 spec 默认范围。

#### W6.6 门槛一致性前置条件（治 X4）

成功判定**要求** `baseline_dir_acc is not None`。无基线的 verdict 落 `gate_basis="fallback_0.52"`，**不参与跨品种比较，也不参与成功判定**，直到无协变量基线补齐。PR-A4 的 `baseline_points_{sym}_nocov.jsonl` 必须覆盖全部**有 verdict 的品种**（当前缺 cf/i/jm/ma/p/sh 六个），而不只是现有 8 个。

#### W6.7 历史修订防护（治 X8）

verdict 落 `context_hash`：该 cutoff 的 context 窗口（480 bar 的收盘序列）内容哈希。后续重算发现哈希变化 → 该 verdict 标记 `data_revised=true` 并**退出成功判定**。`future_bar_guard` 只防未来行，历史修订必须靠哈希自证。

#### W6.8 预训练污染登记（治 X11）— **宿主已裁定：仅登记**

登记为**残余风险**，附模型卡证据（Wikipedia Pageviews cutoff **Nov 2023**、Google Trends **EoY 2022** vs 评估窗 **2026-01→2026-09**，间隔 ≥2 年；`GiftEvalPretrain` 自身 cutoff 未标注）。

**宿主裁定：仅登记，不做诊断性检验，不阻塞阶段二。**

理由（记入 spec 以备后查）：评估窗内**时间分半**无法证伪泄漏——若泄漏均匀分布在整个窗内，早期与晚期表现不会有系统性差异，该检验只能给出"无迹象"，不能给出"没有"，却会消耗一次评估预算。既然已标注 cutoff 与评估窗间隔 ≥2 年、且中国期货 1H 合约数据不太可能进入 Google 公开语料，登记为残余风险是诚实的处置。

**唯一保留项**：若日后出现"模型在某品种上异常强"且无机制解释，本条作为**首选怀疑方向**重新审视（届时可改用"跨期对照"——用明确早于评估窗的时段做对照，比时间分半有信息量）。

---

## 5. 测试要求

每个行为必须有**失败先于实现**的测试（仓库既有风格：`tests/test_praxist_fm_evaluator.py`、`tests/test_supervisor.py`、`tests/test_covariate_audit.py`）。

**测试按 §1.1 三层组织：L1 必须先全绿才可进入 L2，L2 全绿才可进入 L3。**

### 5.1 L1 — 评估可信（硬门槛）

1. `pass_variants` 在 `p_value=None` 时返回 False，即使 `migrated_pass=True`。
2. `dm_status∈{"insufficient_common","no_common_cutoff"}` 时 `p_value is None` **且** stderr 有 WARN（不得静默）。
3. **协议兼容性只由协议指纹决定**：两 verdict `protocol_fingerprint` 相同、`sample_fingerprint` 不同 → **协议兼容**（可比，v3 会误拒）；但**配对推断可用性**单独由共同 cutoff 决定（测试 65/66），不再由"协议指纹相同"混同。
4. **协议指纹变化即不可比**：改动 `cov_fill_version` 或 cutoff 约定后两 verdict **不可比**，排序函数拒绝并列。
5. `bfill` 移除后，含 NaN 的 context 不再用未来值填充（构造用例断言）。
6. **换月量化**：跨换月 cutoff 的占比 `n_roll_ratio` 被落盘；`dir_acc` 与 `dir_acc_ex_roll` 两值 + 差值配对 CI 均被产出。
7. **主口径预注册**：`preregistry` 未声明主口径即校验失败；断言主口径**不是**"仅剔跨换月"。
8. **指标报告完整性**（A 级字段）：缺 `n_dir_total`/`n_dir_active`/`n_zero_move`/`n_roll_excluded`/`n_zero_ratio`/`n_roll_ratio`/`dir_acc`/`dir_acc_full`/`dir_acc_ex_roll` 任一项 → verdict **不完整**，不得进入成功判定。
9. **字段分级**：A 级缺失 → 不完整；B 级缺失 → verdict **有效**但标"不可复现" + WARN；**C 级缺失 → verdict 完全有效**（v3 会误判无效）。
10. **`n_eff` 边界**：常数序列返回 **1** 且 `n_eff_status="degenerate_constant"`（不得 `0/0` 或 NaN）；`n<30` → `None`/`insufficient_n`；`sigma_LR^2<=0` 夹取为 `sigma0^2` + WARN；`n_eff <= n` 恒成立。
11. `measured_n_eff` 对已知自相关序列返回与解析值一致的估计。
12. gated 协变量的 `n_eff` 在 active 子集上独立重算，与全量值不同。
13. **带宽一致**：`h=12`、`q=11`、`VIF=8.0278` 在 `n_eff`、DM、规划公式三处**同源**（断言无第二处定义）。
14. **`run_mode` 双模式（§1.4）**：无 `prereg_id` 的探索运行**可以入队**且标 `exploratory_unconfirmed`（断言**不被阻断**）；`run_mode="exploration"` 的 verdict **不进入**成功判定、品种分级。
15. **`meets_min_info` 替代 `n_eff_status`**：成功判定只读 `meets_min_info`；`degenerate_constant` 归入"**统计上不可判定**"（信息不足，可见诊断）而**非**"评估数据错误"；`nonfinite`/`insufficient_n` 归入"错误"。
16. **`Var(d)` 口径**：断言 `n_required` 使用**边际方差 × `VIF`**；传入已含 HAC 的长程方差时**不再乘 `VIF`**（防重复调整）。
17. **配对定义**：断言仅在 `model_fingerprint` 逐字节相同时才写"同权重"声明；协变量输入改变模型调用路径（张量形状变化）时**不写**该声明。

### 5.2 L2 — 输入可信

18. `cov_fingerprint.matrix_sha256` 对"请求不同名但实际矩阵相同"的两变体返回**相同**哈希；真实不同矩阵返回不同哈希。
19. **协变量指纹规范化**：`-0.0` 与 `+0.0` 得**同一**哈希；不同 NaN payload 得**同一**哈希；含 Inf 时 **fail-loud**；调换键顺序**改变**哈希（顺序是语义）。
20. **实验指纹**：协变量矩阵相同但模型权重不同 → `experiment_fingerprint` 与 `variant_id` 均不同。
21. **W6.4**：请求不同名但矩阵相同的两提案得到**同一** `variant_id`；同 `variant_id` 跨窗口不被静默覆盖；`(symbol, cutoff_ts, experiment_fingerprint)` 变化即重算。
22. 常数协变量 → `inert_constant=true`；全 NaN 协变量 → 同样标记（二者都不得静默通过）。
23. 零填充路径触发 WARN 并在 verdict 留痕；零填充审计覆盖**全部**协变量类型（新增类型未登记则测试失败）。
24. `xreg_fallback=True` → `covariates_used=false` 且不参与成功判定。
25. **消融范围**：常规变体**不**跑三路消融；审计集跑三路；`ablation_content_delta` 与 `ablation_structural_delta` **分开落盘**，断言未被合并成单一"协变量贡献"字段。
26. **W6.1**：`crack_spread_*` 对 `lh`/`m`/`sr`/`rb`/`ss`/`cj` 被拒绝入队，对 `eg`/`sc`/`l`/`pp`/`px` 被接受；通用类协变量在所有品种均被接受；`applicable_sectors` 缺失即校验失败。
27. **W6.1b**：`sector_of()` 对全部 24 目标品种**均不返回 `"other"`**；`l`/`pp`/`px`/`sc` 归 `energy_chem`，`y`/`oi` 归 `agri`。
28. **W6.1c**：构造 `sector_of()=="other"` 的品种，断言它**仍能接受通用类**协变量，板块专属类被拒并落 `sector_unknown`。
29. **跨板块许可**：无 `cross_sector_approved` 记录的错配提案被**拒绝**；缺 `approved_by`/`approved_at` → 许可无效。**`basis` 只断言字段存在，不断言内容质量**（代码无法验证"理由可复核"）。
30. **W6.5 重算**：重算的 `dir_acc_v2` 与原 `dir_acc` 在零变动点为 0 时相等；rb 重算后上升（约 +2pp）；脚本幂等；原 `dir_acc` **未被覆盖**。
31. **W6.6**：`baseline_dir_acc is None` 的 verdict 落 `gate_basis="fallback_0.52"` 且不参与成功判定与跨品种比较。
32. **W6.7**：context 内容变化后重算的 verdict 落 `data_revised=true` 并退出成功判定。
33. **W6.8**：预训练风险登记字段存在；**断言无诊断性检验被强制执行**（已裁定仅登记）。
34. **`known_ahead` 证据**：缺 `known_ahead_evidence` → 降级 `unknowable` + WARN（不静默）；交易所临时调整类不被判为 `known_ahead`。
35. **W5.4 两条件独立**：构造"CI 下界 > 0 但未达 `floor`"的用例，断言判定为"**有证据但效应过小**"而非"通过"；构造"达 `floor` 但 CI 含 0"，断言判为"**无证据**"。
36. **W5.4 比较配对**：跨窗口或跨模型权重的比较被**拒绝**。

### 5.3 L3 — 确认与多重比较

37. **预注册**：无有效 `prereg_id` 的提案不入队；`registered_at` 写入后不可修改（写保护测试）。
38. **确认锁定**：修改已注册参数（协变量/模型/`HORIZON`/指标版本）生成**新** `prereg_id`；沿用旧 id 且参数变更 → 校验失败。
39. **发布时间口径**：低频数据在其**实际公布时间**之前的 cutoff 上不可见（构造用例：推后公布时间，断言该值在更早 cutoff 不出现）。
40. **no-peek**：确认集达 `n_confirm_required` 前读取确认数据被拒并落审计；提前封账落 `n_confirm_actual < n_confirm_required` 且标 `underpowered`。
41. **family 记账**：3 个 `confirmed` + 1 个 `abandoned` → `K=4`；断言 `abandoned` 未被排除。
42. **未完成检验赋 `p=1`**：`abandoned` 与 `timeout` 成员在 BH 校正中 `p=1`（断言它们计入 `K` 但不被误判显著）。
43. **终态时限兜底**：注册后超过 `T_max=180 天` 未达终态的成员**自动落 `timeout` 且 `p=1`**；断言 family 因此**总能封账**（防死锁）。
44. **终态强制**：`preregistry` 中缺终态记录导致校验失败。
45. **批次不重置校正**：同一品种分属不同 `batch_id` 的确认检验**落在同一 family**（断言 `batch_id` 不是 family 键）。
46. **跨品种范围声明**：报告模板含"结论范围仅限品种内、不做跨品种聚合声称"的声明字段；缺该字段即报告校验失败。
47. **Jev 不承担门控**：`skip_suggested=True` **不**阻止入队；`status="degraded"` **不**阻断；缺 `jev_*` 字段**不**使 verdict 无效。
48. **确定性规则承担拒绝**：缺特征、板块不匹配、`mechanism` 四字段不完整、`applicable_sectors` 缺失 → **拒绝入队**（这些不依赖 Jev）。
49. **`detection_threshold_vs_baseline` 与 DM 同源**：由配对序列 `d_t` 的 HAC 标准误算出；断言它**不等于** `baseline_dir_acc + 1.645*0.5/sqrt(n_eff)`（防回归到错误公式）。
50. **`detection_threshold_vs_random`** 在 `n_eff=73` 时 ≈ **0.596**；与 `detection_threshold_vs_baseline`（`rho=0.5` 时 ≈ 0.096）**不相等**且都被落盘。
51. **功效公式**：`n_required = Var(d)*VIF*(z_alpha+z_beta)^2/Delta^2`；`Delta=0.02`、`rho=0.5`、80% 功效时 ≈ **31,000**（±5%）。
52. **`rho` 表只进规划文档**：断言 `rho` 敏感性表**不出现在** verdict 或成功判定路径中。
53. **W4 只诊断不归档**：某协变量仅 5 品种有效评估 → 标 `insufficient_evidence`，但**不触发自动归档**；报告含显式分母 `n_evaluated`；归档动作只能由人写入 `covariate_pool.json` 触发。
54. **W6.3 归属字段可选**：缺 `proposer_model`/`peer_role` 的 verdict **有效**（C 级）。
55. **L3 未就绪时的合法状态**：未配置 `preregistry` 时系统仍运行，且产出的结果被标 `exploratory_unconfirmed`，**不得**出现在成功判定中。
56. **family 注册截止 → 封账可达**：构造持续接收新成员的 family，断言到达 `family_close_at`（或 `family_max_members`）后**不再接纳**新成员，并在 `T_max` 内封账——证明仅靠成员 `T_max` **不足**。
57. **`p=1` 范围**：已进入确认 family 且截止前未完成 → `p=1` 且计入 `K`；**探索中止 / 尚未注册确认的假设 → 不计入 `K`、不赋 `p=1`**。
58. **新 family 不得绕开校正**：新研究问题启动新 family 时，断言报告范围字段存在，且新旧 family 结论**不得合并宣称**；断言仅改 `batch_id` **不**重置校正。
59. **`31,000` 只在规划文档**：断言该数值**不出现在** verdict、成功判定路径或任何"普遍结论"表述中。
60. **确认不能绕过 `meets_min_info`**：`meets_min_info=False`（含 `n_eff < 50`）时，**枚举其他字段组合**，断言确认路径全部得 `underpowered` / 不可判定，**无任何组合**可促成 `confirmed`。
61. **family 稳定哈希边界**：新增 cutoff / 修订历史 bar **不**创建新 family（`research_target_hash` 稳定）；换 `cov_fill_version` / 指标版本 / 模型权重**不**创建；换 `HORIZON` / 目标变量定义 / 价格序列定义 / 复权·换月规则版本**创建**新 family；换协变量组合**不**创建（按 `family_key` 断言）。**v9 扩展**：新增 cutoff/修订 bar 时断言 `target_snapshot_hash` 改变而 `research_target_hash` 不变；同字段在不同实现/复现中序列化出**同一** `research_target_hash`（序列化规范锁死）。
62. **D5 分界**：D5 未裁定时，PR-A1 未实施，但阶段 1 其余 PR（换月、`bfill`、基线、指纹、`dm_status`）**可交付**；PR-A1 的评估路径（cutoff / 样本对齐 / 评价标签）**不**被无意启用。
63. **阶段 1 的 `pass` 不被 L3 卡住**：探索运行的 verdict `pass_variants()` **恒为 False**（无 `p_value`），断言这是**正确行为**且**不阻断** L1 交付；`gate_pass` 为 True 且 A1 字段齐全的 L1 verdict 被**允许产出**。
64. **阶段 3 核验（三套公式分别验证）**：已知自相关序列手算长程方差 vs 代码一致；负自相关与边界滞后不崩；`n_eff`、DM SE、功效规划三套公式**分别**验证，断言"参数同源 **不替代** 统计量定义验证"。
65. **协议兼容 vs 配对推断分层（共同样本口径，v10）**：`protocol_fingerprint` 相同但 cutoff 列表不同的两个 verdict → `protocol_compatible=True`；断言系统**先交后配**（禁止按位置直接相减）。**分情形**：`pairing_computable` 达标（`dm_common_count >= dm_min_common` 且 **`ess(d_t) >= effective_min_n`**）**且缺失 `admissible`** → `pairing_valid=True`、`dm_status="set_mismatch_ok"`、DM 在共同点算且 p 值有效；`ess(d_t)` 或 `dm_common_count` 不足 → `pairing_valid=False`、`dm_status="insufficient_common"`、`p_value=null`；无共同点 → `dm_status="no_common_cutoff"`；协议不兼容 → `dm_status="protocol_mismatch"`、**不进入**共同样本计算。
66. **DM 只算共同 cutoff（记账，v10）**：构造"变体多 2 个 cutoff、基线多 1 个 cutoff"且 `pairing_computable` 达标的用例，**缺失按随机模式构造**（`missing_pattern="random"` → `admissible`，v11 显式化前提；若 §7.8 裁定前 `random` 不可赋值，则本用例改用"缺失经裁定方法证明可接受"的等价前提），断言 `dm_common_count` / `dm_unmatched_variant` / `dm_unmatched_baseline` / `n_avail_variant` / `n_avail_baseline` 被正确记录、`dm_status="set_mismatch_ok"`，DM 只在共同点上算且 p 值有效；断言 `pair_set_hash` 基于最终配对集、与 `raw_cutoff_set_hash` 不同。
67. **黄金用例（每套公式）**：`n_eff`（实测 ESS）、DM SE、功效规划各自**固定 ≥1 个可人工复算的小型黄金用例**（给定完整序列、参数、**精确预期值**），另设负自相关 / 常数序列 / 有效样本不足 / 带宽边界用例。**v10 增**：`ess(d_t)` 的黄金用例须与 DM 标准误**同一 HAC/带宽口径**（断言二者用同一估计量，`d_series_n_eff` 与 gate 的 `n_eff` **分别**计算、不混用）。
68. **确认集起点为预注册固定边界（v10）**：断言 `confirm_from_ts` 在注册时锁定且此后**逐字节不变**；断言确认集 = **预定 cutoff 序列**中 `>= confirm_from_ts` 的点，**不**通过"寻找两边共同可用首个点"来构造；两变体窗口内各有缺口时，确认性 DM 只在共同 cutoff 上算（`pair_set_hash` 反映交集），无共同点/共同不足 → `underpowered` / 不可确认。
69. **选择偏差防护（缺失可接受性）**：① 随机缺失用例（经 §7.8 方法证明独立）→ `missingness_admissible=True`，共同样本达标即 `pairing_valid=True` 可确认；② 构造**模型输出缺失与市场状态相关**的用例（某状态段变体系统性无输出）→ 即使 `dm_common_count` 与 `ess(d_t)` **均达标**，也断言 `missingness_admissible=False`、`pairing_valid=False`、`dm_status="set_mismatch_descriptive"`，**不得**判为可确认；③ 缺失原因不可判定 → 同样 `False`；④ **v12**：断言 §7.8 裁定前 `missingness_admissible` 恒为 `False`（保守默认），且未采集 L2 诊断字段**不改变**该结论。
70. **`dm_status` 字段矩阵与优先级确定性**：对每个 `dm_status` 断言其可生成字段与矩阵一致（尤其 `p_value`/`delta_ci` 为 `null` 的情形、`pair_set_hash` 何时为空集哈希）；对同一组输入，断言无论处理顺序如何，状态判定**首个匹配者胜**（`no_baseline`→`protocol_mismatch`→`no_common_cutoff`→`insufficient_common`→`set_mismatch_descriptive`→`set_mismatch_ok`→`ok`，v12 链），结果**唯一**。**v12 增**：构造"均值非正 **且** 缺失不可接受"的用例，断言 `dm_status="set_mismatch_descriptive"`（状态只由缺失条件定）且 `d_bar_le_zero=True` 作为**诊断字段**落盘；断言 `d_bar_le_zero` **不改变** `dm_status` 与 `pairing_valid`。

---

## 6. Key Decisions

> **v5 精简**：v4 的 §6 有 33+ 条，其中混入了**已废止的旧裁决**（旧 Jev 事前门、旧 MDE 数值、旧自动归档门、
> `p=1` 的旧理由），会让读者把作废规定当成现行。v5 只保留**当前有效**的裁决，
> 并删去与 §4 重复的规则复述。已废止内容见文件头「修订记录」。

### 6.1 范围与分层

1. **本轮硬门槛只有三项**——因果与对齐、比较对象、结果可追溯（§1.1 L1）。三者未过，结果不得进入确认判定。其余（消融、W4 诊断矩阵、元数据、`known_ahead` 登记、`n_eff` 实测）为 L2 诊断或 L3 后续，**不作 verdict 有效性门槛**。
2. **探索与确认拆为两种运行模式**（§1.4）：探索运行无 `prereg_id` 亦可入队，产出标 `exploratory_unconfirmed`，**不得**进入成功判定、品种分级或任何"已确认"表述。这样既保留系统可运行性，也避免把探索结果包装成确认结果。
3. **字段分 A/B/C 三级**：A 成功判定必需、B 复现必需、C 治理分析可选。**C 级缺失不使 verdict 无效**（§1.2）。
4. **24 品种自动分级延后**，等目标效应与功效目标明确后再做，不与测量修复捆成同一交付（§1.1 L3 / §4.6）。
5. **接受"多数品种当前不可验证"是合法结果**，也是止住预算空转的唯一诚实路径。禁止为让结果好看而放宽阈值。

### 6.2 统计口径

6. **增量检验必须配对**：同一 cutoff、同一目标、同一预测协议下成对比较预测误差或命中结果。**"同权重"只在 `model_fingerprint` 逐字节相同时才可声明**——若协变量输入改变了模型调用路径（如张量形状），不得默认共享权重（§4.3 W3.5）。
7. **`z=1.645` 是显著性边界，不是 MDE**（未指定功效）。样本量规划必须显式指定目标功效（§4.3 W3.5）。
8. **`Var(d)` 是单点边际方差**，相关性由 `VIF` 承担；**若直接使用已含 HAC 的长程方差，则不得再乘 `VIF`**（重复调整）。公式与代码只允许一个 `Var(d)` 定义（§4.3 W3.5②）。
9. **`31,000` 等数字是规划情景示例，不是普遍结论**。"**需要很多样本**"是资源与时间判断，"**不可检出**"是统计结论——后者不能仅凭一张假设表得出（§4.3 W3.5②）。
10. **`VIF=8.028` 只是初始情景**，不得作为实现中的唯一常数；实际规划应优先从**先导数据**估计配对损失差的 HAC 方差，并对估计不确定性做敏感性分析（§4.3 W3.5②）。
11. **`rho` 敏感性表只作规划情景**，不进 verdict、不作全项目结论；实际评估以配对序列实测 `SE_HAC` 为准并报告其不确定性（§4.3 W3.5③）。
12. **成功判定读 `meets_min_info`（单一显式字段），不读 `n_eff_status`**；必须区分"**统计上不可判定**"（信息不足，如常数方向序列）与"**评估数据错误**"（需修复重跑）——前者是有意义的诊断结论，不得被一概当作无效（§4.1 W1.2）。

### 6.3 多重比较与确认

13. **family 由研究问题定义，不由批次定义**：批次是行政概念，按批次拆家族等于可以多开批次规避校正，故**批次/运行/代际都不重置校正**；默认一品种一 family（§4.3 W3.6①）。
14. **family 必须设注册截止**（时间 90 天 / 成员 20，先到者为准）——这是**封账可达的必要条件**。仅给成员设 `T_max` 不足：若 family 持续接收新成员，"全部成员终态"的时刻永不到来（§4.3 W3.6②）。
15. **`p=1` 仅适用于"已进入确认 family、且截止前未完成确认"的成员**；探索中止与尚未注册确认的假设**不在 `K` 内**，也不赋 `p=1`（§4.3 W3.6②）。`abandoned`/`timeout` 计入 `K`。
16. **新研究问题启动新 family**，须声明与旧 family 的关系及报告范围；**禁止**用新批次名绕开校正（§4.3 W3.6②）。
17. **跨品种错误率范围显式声明**；默认不合并校正，故**结论仅限品种内**，报告不得产出跨品种聚合声称（§4.3 W3.6①）。
18. **默认 no-peek + 固定确认样本量**；序贯方案须在注册时固定查看次数与边界（§4.3 W3.6③）。
19. **确认期冻结预测规则**；任何改动生成新 `prereg_id` 且只用**未观察** cutoff；低频数据按**实际发布时点**判定可用性（§4.3 W3.7）。

### 6.4 数据、身份与治理

20. **可比性只由 `protocol_fingerprint` 决定**；`sample_fingerprint` 随前向数据累积变化属正常，**不构成**拒绝比较的理由（§4.1 W1.5）。
21. **`variant_id` 由 `experiment_fingerprint` 派生**（含模型、目标序列、context），不由协变量指纹单独派生；克隆判定用 `matrix_sha256`，且哈希须**规范序列化**（键序保留、float32 小端、规范 NaN、`-0.0` 归一、Inf fail-loud）（§4.2 W2.1）。
22. **换月不能靠"默认不剔除"解决**：先判性质（数据有效性问题 → 修复或排除；仅敏感性 → 须证明不主导）。跨品种汇总**必须声明是描述性审计结论还是正式推断**——后者需跨品种不确定性处理，属"结论仅限品种内"的**显式例外**（§4.7 W6.5③）。
23. **拒绝由确定性规则承担**（特征缺失、板块不匹配、机制字段不完整、`applicable_sectors` 缺失）；**Jev 仅建议**，不拒绝、不参与成功判定、不决定统计家族（§4.3 W3.2 / §4.7 W6.2）。
24. **协变量适用性按构造来源判定**：只读目标品种自身 kline 的协变量对所有品种成立（`["*"]`），无需逐项裁定；需要外部/关联市场数据的才须枚举板块（§4.7 W6.1a）。
25. **`sector_map.py` 须补齐 24 目标品种并纳入 `l`/`pp`**，且扩充须过既有消费者（Regime/VolRisk/Domain-Shift）的影响检查——不得为绕开影响而另起一套板块集合（§4.7 W6.1b）。
26. **跨板块不匹配即拒绝**；例外须**事前留档**（`approved_by`/`approved_at`）；`basis` 是**审计要求**，不是代码可验证门（§4.7 W6.1d）。
27. **W4 只出诊断矩阵，归档权在人**；阈值（8 品种/2 板块/60%）是治理阈值而非科学定律，不作自动归档条件（§4.4）。
28. **三路消融只在固定审计集与异常/确认候选变体上运行**（§4.2 W2.3）。
29. **预训练污染只登记为残余风险**，不做诊断性检验（时间分半无法证伪泄漏却要消耗评估预算）（§4.7 W6.8）。
30. **品种状态改派生**，取代手写 `symbol_status.json`（§4.6）。

---

## 7. 开放问题

宿主可裁定，不挡 W1/W2 实施：

1. **D5 1-bar 前视 — 现为 PR-A1 与 PR-D2 的正式前置门槛**（v3 只列为"开放问题"，但 PR-D2 又要求它完成，形成死锁）。必须二选一后才可实施：

   - **选项 A（推荐）**：cutoff 改为该 bar 的**收盘**时间（`dt + 1h`），使"cutoff 时点已知的信息"与所用值一致。
   - **选项 B**：维持现状，但 verdict 落 `cutoff_convention="bar_open"` 并把 1-bar 偏差**量化**进报告。

   **选定后的连带处置必须一并规定**（前一版缺失）：无论选 A 还是 B，都要明确——
   - 选 A 会改变**全部** cutoff 语义，故：窗口重算、checkpoint 作废（键含 `cutoff_ts`，见 W6.4）、特征时间戳对齐规则重定、**全部历史 verdict 标记为不可比**（`protocol_fingerprint` 变化，W1.5），需按新协议重跑才能恢复可比；
   - 选 B 则 `protocol_fingerprint` 不变，历史 verdict 的**协议可比性**保留，但必须落 `cutoff_convention` 并量化偏差；
   - 两种选项都必须更新 `generate_baseline_points.py` 与无协变量基线，否则基线与变体的 cutoff 语义不一致。

   在裁定前，PR-A1 与 PR-D2 **均不得实施**（阶段 1 其余项可并行）。
2. **历史 143 条 verdict 的处置 — 已裁定：重算 + 标记**（详见 §4.7 W6.5）：从 checkpoint **离线重算** `dir_acc_v2` 等字段（不重跑模型、不覆盖原值），使历史数值在**新口径下**可比；但历史 verdict 仍标 `legacy_untrusted`，**仅作探索记录，不得用于选型或成功判定**——因为窗口漂移（X7/E9）**未**被重算解决。若要恢复"可参与选型"，需按新协议**重跑慢环**，属另一量级预算，**需单独批准**。
3. **`praxist_goal.yaml` 的 24 品种目标集**：若阶段二判定多数品种"当前不可验证"，是否把目标集收缩到"可预测"品种？本 spec 不预设。
4. **文档漂移**：`docs/runbook_praxist_three_loop.md:147` 仍写着旧的 `n_one_star_symbols_hit >= 4` 成功条件，与 live `praxist_goal.yaml`（per-symbol 三阶段）不一致。建议随本 spec 一并修正。
5. **W5 的四类归属**：`covariate_pool.json` 的 `horizon_known` 初版分类由谁定？建议由宿主/研究侧逐协变量确认（尤其 `known_ahead` 的准入——它直接决定是否引入未来信息，宁可保守）。本 spec 只定词表与不变量，不代填分类。
6. **`sector_map.py` 扩充的影响检查结果**：扩充会让原先落入 `"other"` 的品种（y/px/oi/sc）获得板块归属，可能改变 Regime / VolRisk R1 / Neutral A/B Domain-Shift 的既有判定。W6.1b 要求出影响证据；若证据显示判定发生**实质变化**（而非仅新增归属），需宿主裁定是否接受该变化，或改为仅对 W6.1 生效的独立词表（后者违反"唯一板块表"约定，不推荐）。
7. **目标效应与目标功效（最关键的一项）**：§4.3 W3.5 的**规划情景示例**（**明确为示例，非普遍结论**）显示——0.02 增量约需 **31,000** 个评估点、0.05 约需 5,000、0.10 约需 1,240，而当前只有 **588**。必须裁定走哪条路：

   - **(a) 上调目标效应**到可检出量级（例如只追求 ≥0.05 的增量），据此重写 §4.6 的品种分级标准；
   - **(b) 按功效累积样本量**——需要多长的日历时间？（`STEP=2` 下 5,000 点约需 10,000 根 1H bar，远超现有历史，实际不可行；若可行需说明如何获得）
   - **(c) 接受"只能检出大效应"**，把品种分级的判定门槛与结论表述一并改为"仅能排除大效应"，不再宣称小效应无效。

   **裁定前应先用先导数据估计配对损失差的 HAC 方差**（§4.3 W3.5②），据实测算，而非依赖示例假设。
   **本 spec 不预设**。但在裁定前，§4.6 的品种分级与 `praxist_goal.yaml` 的成功条件**不得**按 0.51 一类小效应目标设定——在示例假设下其量级远超当前样本。
8. **缺失模式分层的预定义（v10 新增）**：§4.1 W1.5 的缺失诊断要求"按**预定义市场状态分层**"计算缺失率（L2 诊断项），但"预定义市场状态"的具体分桶尚未确定。需裁定：① 分桶用什么（复用既有 Regime / VolRisk 判定，还是独立的时间分桶）；② **缺失与状态是否独立的判定方法**（卡方/比例检验？阈值？最小桶样本？）——它直接决定 `missingness_admissible`，进而决定能否确认；③ 分桶与判定规则**必须在注册时固定**（不得事后挑选分桶使缺失"看起来随机"）。**在裁定前**，W1.5 的缺失判定按保守默认执行：除非能证明缺失与状态**独立**，否则 `missingness_admissible=False` → `descriptive_only`（宁可只作描述性，不可误判可确认）。

---

## 8. 实施顺序与 PR 切分

> **v4 重排**：v3 的 Wave 表与 Key Decisions 不一致（PR12 行漏了 PR17），且按 PR 号顺序实施会把
> **尚未验证的统计公式直接固化进自动化门控**。v4 改为四阶段，每阶段有**独立核验**，
> **阶段 3 核验通过前不得让统计量驱动自动成功门或品种等级**。

### 8.0 批准边界（本轮可先放行的范围）

> 按四轮审核的收敛，**建议分步批准**：

1. **阶段 1 拆成两档批准**（消除 v6 的"先批准阶段 1"与"PR-A1 被 D5 阻断"的冲突）：
   - **D5 裁定前可批准**：PR-A2（换月）、PR-A3（`bfill`）、PR-A4（无协变量基线）、PR-A5（指纹）、PR-A6（`dm_status`）+ 最小追溯字段（A1）+ 探索运行标记（`run_mode`/`run_label`）；
     - **PR-A6 反向指针（v14）**：PR-A6 **仅**交付 `dm_status` 状态机 + 字段落盘 + fail-loud 告警；其中**含 `aligned_slow_loop.py` 键改造的窗口对齐部分随 PR-A1 受 D5 阻断**，不在 PR-A6 交付内（见 §4.1 W1.3 作用域标记）。
   - **D5 裁定后才批准**：**PR-A1**（cutoff 语义 + checkpoint 键，会改变 cutoff/样本对齐/评价标签，直接受 D5 阻断）、使用受 cutoff 影响的基线或评估逻辑、以及 PR-D2（品种分级）。
2. **阶段 2**（输入指纹、消融）作为**诊断完成项**推进，**不作硬门**（§1.1 L2）。
3. **阶段 3/4**（自动统计门控、品种分级）**等** `meets_min_info`、确认检验损失定义、family 归属、样本量口径**全部统一并经核验后**再启用（§8.5 硬约束 4）。

### 8.1 阶段 1 — 三项硬门槛 `[L1]`

对应 §1.1 的三项硬门：

| 硬门 | 覆盖 PR |
|---|---|
| **硬门 1 — 因果与对齐正确** | PR-A1（cutoff/窗口/checkpoint）、PR-A2（换月）、PR-A3（`bfill`） |
| **硬门 2 — 比较对象正确** | PR-A4（无协变量基线）、PR-A6（`dm_status` + 去 `migrated_pass` 后门） |
| **硬门 3 — 结果可追溯** | PR-A5（协议/样本指纹 + 可比性守卫） |

| PR | 标题 | 主要文件 |
|---|---|---|
| PR-A1 | **cutoff 与窗口语义**（`[D5 阻断]`：会改变 cutoff / 样本对齐 / 评价标签，必须待 D5 裁定）+ checkpoint 键改 `cutoff_ts` | `monthly_backtest.py`, `aligned_slow_loop.py`, `data_store.py` |
| PR-A2 | 换月：复权守卫修复 + roll 量化与性质判定（W6.5③） | `data_store.py`, `monthly_backtest.py` |
| PR-A3 | `bfill` 因果化 | `features.py` |
| PR-A4 | **同 cutoff 无协变量基线**（覆盖全部有 verdict 的品种，含缺基线的 cf/i/jm/ma/p/sh） | `generate_baseline_points.py`, `praxist_supervisor.py` |
| PR-A5 | `protocol_fingerprint` / `sample_fingerprint` + 可比性守卫 | `evaluator.py`, 报告生成器 |
| PR-A6 | DM 显式 `dm_status` + 成功判定去 `migrated_pass` 后门 | `evaluator.py`, `registry_lib.py`, `statistical_tests.py` |

**核验（阶段 1 出口）**：取 2–3 个品种、**固定窗口与 cutoff**，**手算核对一小批预测点**，
证明对齐与基线配对正确。产出是"对齐与配对可信"的证据，**不是研究结论**。

### 8.2 阶段 2 — 诊断与第二阶段完成项 `[L2 诊断，非硬门]`

| PR | 标题 | 主要文件 |
|---|---|---|
| PR-B1 | `cov_fingerprint`（规范序列化）+ `experiment_fingerprint` + 身份派生 + 去重分组 | `hourly_model.py`, `registry_lib.py`, `evaluator.py` |
| PR-B2 | 缺失/常数诊断 + 零填充 fail-loud + 审计覆盖全部协变量类型 | `features.py`, `evaluator.py` |
| PR-B3 | `xreg_fallback` 贯通评估路径 | `evaluator.py`, `monthly_backtest.py`, `aligned_slow_loop.py` |
| PR-B4 | 单一 `dir_acc` 口径（三值 + 分母报告）+ 历史离线重算 | `evaluation_metrics.py`, `evaluator.py`, 重算脚本 |
| PR-B5 | 三路消融（**仅固定审计集**） | `hourly_model.py`, `monthly_backtest.py` |
| PR-B6 | 提案质量门（两类判据 + `sector_map.py` 补齐 + 影响检查 + 跨板块留档许可） | `sector_map.py`, `covariate_pool.json`, `praxist_supervisor.py` |

**核验（阶段 2 出口）**：用少量代表性协变量做完整消融，确认输入**确实改变模型**，
并区分内容效应与通道效应。若消融显示输入不变，则"协变量有效"类结论一律不得成立。

### 8.3 阶段 3 — 统计实现（定义未定前不驱动自动门）`[L3 前置]`

| PR | 标题 | 主要文件 |
|---|---|---|
| PR-C1 | `detection_threshold_*` + 配对 HAC + `n_required` 功效公式 | `statistical_tests.py`, `evaluation_metrics.py` |
| PR-C2 | family 定义 + 封账 + 未完成检验 `p=1` + `T_max` 兜底 + 跨品种范围声明 | `praxist_supervisor.py`, `statistical_tests.py`, 报告模板 |
| PR-C3 | `n_eff` 实测（七类边界）+ 定位收窄为诊断与最低信息门槛 | `evaluation_metrics.py` |
| PR-C4 | 门槛一致性 + 历史修订防护 + 预训练登记 | `evaluator.py`, `registry_lib.py`, `docs/` |
| PR-C5 | 协变量族**诊断矩阵**（只诊断，不自动归档） | `covariate_family_verdict.json`, 诊断脚本 |
| PR-C6 | horizon 尾填充（W5）：`horizon_known` 分类 + 证据格式 + 前视不变量 | `covariate_pool.json`, `features.py`, `hourly_model.py` |

**核验（阶段 3 出口）**：**先用历史或模拟序列验证统计实现**，覆盖下列**每一项**（v7 强调"**参数同源 ≠ 统计量定义相同**"）：

- 用**已知自相关序列**手算长程方差，与代码结果比较；
- 验证**负自相关、边界滞后、重叠预测**场景；
- **分别**验证三套公式——`n_eff`（实测 ESS）、DM 标准误、功效规划——**不让一套参数通过就当作三套都过**；
- 断言实现中**不存在**"长程方差 × `VIF`"的混用路径（§4.3 W3.5 二选一）；
- 不把"没有第二套参数定义"当成"统计量定义已验证"；
- **固定黄金用例**：每套公式固定 ≥1 个**可人工复算**的小型用例（完整序列 + 参数 + **精确预期值**），
  并在用例中写明 **带宽约定、均值中心化、样本方差分母、有限样本修正**；负自相关 / 常数序列 / 有效样本不足 / 带宽边界各一（见 §5.3 测试 67）；
- **重叠预测的相关结构**：明确是**实测 HAC 估计**（若用于确认）还是**仅情景规划**（名义 VIF）——
  **禁止**把名义 VIF 当作检验校正。

**在定义未定之前，禁止让这些统计量驱动自动成功门或品种等级。**

### 8.4 阶段 4 — 预注册、前向确认、品种分级 `[L3]`

| PR | 标题 | 主要文件 |
|---|---|---|
| PR-D1 | 机器可读预注册 + 确认锁定 + no-peek + 预算纪律 | `praxist_supervisor.py`, `preregistry.jsonl`, `praxist_goal.yaml` |
| PR-D2 | 阶段二 品种分级 + 成功条件重写 + `symbol_status` 退休 | `praxist_goal.yaml`, `praxist_supervisor.py` |

### 8.5 依赖与硬约束（唯一权威）

1. **阶段 4 的前置 = 阶段 1–3 全部 PR 完成 + §7 开放问题 1（D5）已裁定 + §7 开放问题 7（目标效应与功效）已裁定。**
   不逐项罗列，以本条为准。
2. **D5 未裁定 → PR-A1 与 PR-D2 均不得实施**（阶段 1 其余项可并行）。
3. **目标效应未裁定 → PR-D2 不得实施**：否则会把 0.51 一类小效应目标写进成功条件，而 §4.3 W3.5 的规划示例显示其量级远超当前样本。
4. **阶段 3 核验未通过 → 不得进入阶段 4**：统计实现未经核对就上门控会把错误固化。
5. **阶段 2 核验未通过（消融显示输入不变）→ 阶段 4 不得宣称任何协变量有效。**
6. **阶段 2 是诊断项，不阻塞阶段 1 的交付**（§1.1：L2 不作 verdict 有效性门槛）。
7. 每个 PR 必须带绿测试，禁止把"下一步再写测试"写进 diff。

### 8.6 实施层降级约束（v12，唯一权威）

> 第十轮专家审核判定：核心使命已闭合，但三处机制的**触发概率与防护收益不对称**。以下约束**保留 v11 的语义严密性，压缩记账厚度**——
> 降级的是采集/报告/测试的**运维成本**，不是守卫本身。实现时**不得**以"简化"为由放宽任何守卫语义。

1. **缺失机制**：核心强制字段仅 `n_avail_variant` / `n_avail_baseline` / `n_common` + 布尔 `missingness_admissible`（进成功判定）。
   `missing_rate_by_bucket` / `missing_pattern` / `n_missing_*` 为 **L2 诊断**，§7.8 裁定前**非强制采集**。
   **守卫不变**：不可证明随机 → `missingness_admissible=False` → `descriptive_only`。
2. **哈希层次**：`research_target_hash` 与 `protocol_fingerprint` 是**语义身份**，可进人工审阅与报告正文；
   其余哈希（`sample_fingerprint` / `experiment_fingerprint` / `cov_fingerprint.matrix_sha256` / `target_snapshot_hash` /
   `pair_set_hash` / `raw_cutoff_set_hash` / `context_hash`）均为**实现细节**，**不进**任何人工审阅界面与报告正文（仅供机器比对与审计留档）。
   **golden 精确值测试只保留 `research_target_hash` 一处**；其余哈希断言"同输入同值、异输入异值"即可（测试 19/21 已是相对断言，符合本条）。
3. **`dm_status`**：枚举 **7 个**（`d_bar_nonpositive` 已降为诊断字段 `d_bar_le_zero`）；优先级链以 §4.1 W1.5 为准，**首个匹配者胜**断言保留。
   `d_bar_le_zero` 只落盘、**不改变**状态与 `pairing_valid`。
4. **不得反向回涨**：本轮之后若再引入新的状态/字段/哈希层，须先给出"**触发概率 × 防护收益 > 复杂度成本**"的论证，
   并优先放入 L2 诊断而非成功判定路径——避免重演 v8–v11 的复杂度回涨。
