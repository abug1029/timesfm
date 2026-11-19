# S1 Supervisor Split Spec 复审报告（v2.0）

> **日期**: 2026-10-10
> **被审对象**: `specs/2026-10-09-s1-supervisor-split-spec.md`（v2.0，commit `d11361c`）
> **前审**: `reports/2026-10-09-m5-supervisor-split-spec-review.md`（v1.0，Reject as-is，13 项修正要求）
> **方法**: 本轮较前审加深两层——(1) AST 全量调用图扫描（160 个顶层函数 × 全部 Name/Attribute 调用），(2) 测试引用面全量提取（32 文件的 setattr 目标 / 属性访问 / from-import / 别名形态）。所有行号均实测。
> **结论一句话**: 13 项前审要求 11 项到位、2 项部分到位；架构、测试策略、迁移窗口协议、指纹纪律全部成立。但 AST 全量扫描暴露 v1.0 抽查未达的层面：**「无循环依赖」声明对 spec 自身分组仍不成立（4 环 + 2 未声明边），shim/patch 映射仍缺 ~31 个测试引用符号**——第二次 Reject as-is（收窄为符号清单补全，不再有原则性缺陷）。

---

## 1. 前审 13 项逐项闭环表

| 前审项 | v2.0 响应 | 判定 |
|---|---|---|
| C1 换编号 | S1 新系列 + 头表/§11 与已关闭 M5（n_eff）显式切割 | ✓（残留：旧 M5 文件未废弃，见 N6） |
| C2 测试策略重写 | §4.1 方案 A：238+7 处脚本化迁移、语义零改动 | ✓ 原则成立（映射源不完备 → N2/N3/N4） |
| C3 归属修正 | VALID_TIER_VALUES+is_valid_tier→sup_evidence ✓；_log_decision→sup_lifecycle ✓；DAG 重画 | ✓ 两处原环已消；更深层面新发现 4 环（N1） |
| C4 is_valid_tier 提升 | §3.0 迁移步骤 0 | ✓ 方向成立（sketch 与实际不符 → N5） |
| M1 141→32 | §1.1/§6/§8 三处全部改 32 | ✓ |
| M2 shim 补全局 | 5 个具名全局已入 §2.4/__all__ | ◐ 部分（另有 ~31 个测试引用符号缺失 → N2） |
| M3 迁移窗口协议 | §5.1：flag 3h 续期 / cron 注释替代 / 冒烟+心跳验收 / 拉起验收 | ✓ |
| M4 工期重估 | §9 ~10 小时/2 工作日，含 patch 迁移 90min | ✓（N2 工作量并入后建议 +2h） |
| m1 清单统一 | 未做 | ✗（§2.3 与 §2.4 仍差 13 个符号，见 N7） |
| m2 跨域移动标注 | ensure_baselines / _valid_n_for_symbol 已标注 | ✓（新发现未标注跨域移动 → N7） |
| m3 域 D/E 重叠 | §1.2 注记「以职责边界为准」 | ✓ |
| m4 死代码闸门 | §4.3 适配说明 | ✓ |
| m5 指纹纪律 | §10 完整声明（不 bump + 逃生通道） | ✓ |

## 2. 新发现问题

### N1（Critical）：「无循环依赖」声明对 spec 自身分组仍不成立——4 环 + 2 未声明边

前审 C3 修复的是 spec 归属表自含的两处环；本轮 AST 全量扫描（函数级调用图）发现 spec 未指派的 ~25 个函数中隐藏着更深的结构问题：

| # | 结构 | 证据（实测行号） | 修正 |
|---|---|---|---|
| 环 A | loops ↔ family | main:4530 → `_maybe_enqueue_confirmations`(sup_family) → :508 `_active_protocol_snapshot`(spec 归 sup_loops) | `_active_protocol_snapshot`(:3029) → **sup_evidence**（内部仅调 `_current_protocol_fingerprint`，evidence 自洽） |
| 环 B | loops ↔ state | load_state:774 `return _ensure_tokens_baseline(st)`，而 :3104 def 归 sup_loops | `_ensure_tokens_baseline` + `_read_token_m`（+`_token_spend_m`）→ **sup_state** |
| 环 C | lifecycle ↔ family | `_now_iso`(:325, 行号在 family 段, spec 未指派) 被 `_emit_event`:628 / `_write_stop_json`:659 / `_write_heartbeat`:681 / `_log_decision`:3081 调用 | `_now_iso` → **sup_lifecycle** |
| 环 D | loops ↔ evidence | ensure_baselines:3988(spec 归 sup_evidence) → 基线重生簇 `_regen_baseline_with_archive`:3968 / `_baseline_reanchor_reason`:3888 / `_guard_confirm_from_ts_after_regen`:3920 / `_prereg_confirm_from_ts`:3876（全部未指派，行号在 O 段默认 loops） | 基线重生簇整体 → **sup_evidence** |
| 边 E | evidence → family | `_has_prior_failure`:1550 → `_is_confirmable_failure`:1859（spec §2.4 归 sup_family）；叠加 family→evidence（见边 G）即成环 | `_is_confirmable_failure` → **sup_evidence**（唯一调用方在 evidence） |
| 边 F | evidence → family | materialize_known_verdicts:1348 → `_dead_family_lines`:1907 → `_family_confirmatory_counts`:1870；同时 harvest_proposals:2631 → `_dead_families`:1893 → 同簇；spec §2.4 把 `_dead_families` 归 sup_family | 死亡族簇（`_dead_families`/`_dead_family_lines`/`_family_confirmatory_counts`）→ **sup_evidence**（harvest→evidence 已声明） |

另三条未声明边（消环后加声明即可，无环）：

| # | 边 | 证据 | 修正 |
|---|---|---|---|
| 边 G | family → evidence | _maybe_enqueue_confirmations:521 → `load_covariate_pool` | family deps 补 evidence |
| 边 H | provider → lifecycle | _latest_429_reset:1049 → `parse_429_reset`:758 | `parse_429_reset` → **sup_provider**（语义更贴切），或 provider deps 补 lifecycle |
| 边 I | evidence/harvest → 未指派 | `_load_evaluator`:1790 被 harvest_proposals:2631 与 `_symbol_n_table`:2987（spec 归 sup_evidence）双向调用 | `_load_evaluator` → **sup_evidence**（不可落 sup_harvest，否则 evidence→harvest 环） |

**根因与修正要求**：spec 符号清单仅覆盖 ~135/160 个函数，未指派函数中至少 10 个产生跨模块边。要求：AST 生成**完整符号→模块映射表（160 函数 + 全部模块级全局/常量/import 别名）作为 spec 附录 A**；上表 9 项修正直接采纳；§3.2 DAG 按附录 A 重画后再声明无环。

### N2（Critical）：shim 与 patch 映射仍缺 ~31 个测试引用符号（M2 修复不完整）

对 32 个测试文件全量提取 `sup.X` 引用面（64 个 distinct 属性访问 + 52 个 distinct setattr 目标），比对 §2.4 的 135 符号清单：

- **setattr 目标缺 12**（§4.2 迁移脚本以 §2.4 为映射源 → 这些必然漏改）：`CROSS_MATRIX_MAX_ROWS`:2138、`EVENTS_PATH`:147、`FAMILY_REGISTRY`:188、`HEARTBEAT_PATH`:148、`PREREGISTRY_PATH`:189、`STATE_MD`:146、`STOP_REPORT_JSON`:149、`_STOP_EMITTED`:154、`_latest_data_dt`、`_load_evaluator`:1790、`evaluate_goal`(:12 import 自 goal_dsl)、`rl`(:11)
- **属性访问另缺 19**：`GOAL_SYMBOLS_SET`:1807、`OLD_PRIORS_MAX_ROWS`:2139、`RETEST_GATE_N`:171、`_CADENCE_DEFAULTS`、`_CONFIRMATION_NOTICE`(+TTL_S)、`_CONFIRM_DATA_CACHE`、`_CONFIRM_REDISPATCH`(+TTL_S)、`_archive_baseline_before_regen`、`_baseline_reanchor_reason`、`_effective_clue_lines`、`_family_confirmatory_counts`、`_guard_confirm_from_ts_after_regen`、`_has_prior_failure`、`_load_goal_symbols`、`lock`、`subprocess`、`time` 等
- **shim 引用不存在的模块级符号 2**：
  - `family_for`——:522 实测为 `_maybe_enqueue_confirmations` 内的**嵌套闭包**（4 空格缩进，捕获 `pool`），与 is_valid_tier 同类问题但**步骤 0 未覆盖**。修正：从 §2.3 sup_family 职责列表与 §2.4 import 删除（闭包随宿主函数整体迁移即可）
  - `is_valid_tier`——预期缺失（步骤 0 提升后存在 ✓，非问题）

### N3（High）：模块别名 patch 语义弱化未处理

实证：`test_confirm_bugs_20261003.py:95` 与 `test_fixes_20261003.py:149`：

```python
monkeypatch.setattr(sup, "rl", type("RL", (), {...}))  # 整体替换 rl 别名为假命名空间
```

拆分后 `rl.` 绑定存在于多个 sup_* 模块（registry_lib 被 family/evidence/harvest/loops 共用），单点 patch 只影响一个模块 → **假 RL 静默漏网到其余模块，测试大概率假绿**。§4.2 的「单目标机械映射」对别名类不适用。修正（spec 须写明别名策略）：别名类 patch 改为 patch 源模块本身（`monkeypatch.setattr(rl, "read_rows", ...)` 逐属性），或测试夹具循环 patch 全部 sup_* 模块的同名绑定。同类风险：`subprocess`/`time`/`lock`。

### N4（High）：§4.2 脚本只识别 `sup` 别名，漏 15 个文件

实测 import 形态：`as S` **13 个文件**、`as sup` 14 个、`as sv` 1 个、内联 `as s` 1 个。§4.2 只写了「import praxist_supervisor as sup 后的 sup.X 访问」→ AST 脚本必须按全部 4 种别名扫描，否则 15 个文件静默漏改。

### N5（Medium）：§3.0 sketch 与实际函数体不符，「纯机械重构」声明不成立

实际 :1150-1160（实测）与 sketch 两处实质差异：

1. 实际**无** `isinstance(v, dict)` 检查（直接 `v.get("tier")`）——照抄 sketch 实施反而引入语义变更；
2. 实际命中非法值时调用 `_log_decision(log, "tier_domain_violation", ...)`——**`log` 是 build_snapshot 作用域的闭包变量**。提升到模块级必须引入 `log` 参数（`is_valid_tier(v, log)`）并同步 build_snapshot 内调用点，不是纯机械复制。

修正：§3.0 sketch 更正为实际函数体 + log 参数化方案；验证项补「tier_domain_violation 日志路径仍有测试覆盖」。

### N6（Medium）：旧 M5 spec 未废弃——C1 修复不完整

`2026-10-09-m5-supervisor-split-spec.md` 仍是活的「Draft → 待实施」状态（含 141 文件等已勘误旧数据），与 S1 v2.0 并存形成双 spec 歧义。修正：旧档头部加「**Superseded by S1 v2.0，勿实施**」并整体划线，或 `git mv` 到 `specs/archive/`。

### N7（Low）

- m1 残留：§2.3 与 §2.4 仍不一致——sup_evidence 5 个（`_symbol_n_table` 等）、sup_family 8 个（`_dead_families` 等）符号出现在 import 而不在职责列表；随附录 A 一并消解
- 未标注跨域移动（m2 类）：`_praxist` 实际定义 :1028（H/provider 段）而 §2.3 归 sup_env（provider→env 边已声明，无环）；`harvest_survivors`:1254（J 段）→ sup_harvest；`_sector_filter_check`:2208 等_gap 段函数 → sup_harvest
- §1.2 域表存在未覆盖区间（1744-1811、2151-2374、3181-3223，含 16 个函数），随附录 A 一并消解

## 3. 结论与处置建议

**第二次 Reject as-is（收窄）**。与 v1.0 的原则性缺陷（错误原则、错误归属、错误事实基线）不同，v2.0 的架构、方案 A 测试策略、迁移窗口协议、指纹纪律**全部成立**；剩余问题集中在**符号清单的完备性**——本质是 §2.4/§4.2 的数据质量问题，可机械修复：

1. 生成附录 A：完整符号→模块映射（160 函数 + 模块级全局 + import 别名），采纳 §N1 的 9 项归属修正；
2. §2.4 shim 按附录 A 补全 ~31 个缺失符号、删除 `family_for`；§4.2 映射源同步切换为附录 A；
3. §4.2 脚本扫描范围扩至 4 种别名（S/sup/sv/s）；
4. 补别名 patch 策略（N3）；
5. §3.0 sketch 更正（N5）；
6. 废弃旧 M5 spec（N6）。

**处置选项（供宿主裁定）**：上述 1-6 落地后可 (a) 出第三版全文复核，或 (b) 鉴于修正全部为机械性、无架构争议，豁免第三轮全文复核、仅复核附录 A 与 §2.4 diff 后直接进实施。

**审核者签名**: _______________  **日期**: 2026-10-10
