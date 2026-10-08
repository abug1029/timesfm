# FM_a 技术债清单
> **代码基线**: `38df4ac`（文中行号引用以该 commit 为准）（2026-10-08 D1 补记）

> **日期**: 2026-10-07
> **盘点范围**: supervisor 代码、peer 学习通道、资产保护、口径/文档/运维
> **盘点依据**: `docs/superpowers/reports/` 下所有诊断报告 + `docs/superpowers/specs/` 下未结案 spec + 代码核实
> **总条数**: 18 条（P0=4 / P1=3 / P2=6 / P3=5）
> **本次审核**: 2026-10-07 ~19:00 核实代码库，5 条已修复（L1/L5/D3/D8/D9）、L2 降级至 P2
> **第二次审核**: 2026-10-08 实施并核实 —— L2 / L3 / L4 / D2 收口、信用档退役、品种宇宙对齐；新增 6 项专项发现（N5-N10，见文末「2026-10-08 审核」）

---

## 🔴 P0：资产单点故障（不可恢复风险）

| # | 项 | 现状 | 风险 |
|---|---|---|---|
| A1 | `aligned_verdicts.jsonl` 从未进 git | `.gitignore:74` 排除（`d236671` 清 API key 的**副作用**，非有意排除） | remote + bundle 都没有裁决历史；磁盘故障 = 全失 |
| A2 | 三代备份**全在同盘** | 主仓 + 4 worktree + bundle 全在 `/home/abug/`（`/dev/sdd`） | 磁盘故障 = 全失 |
| A3 | `git clean -xdf` 一锅端 | 同时删原件 + 三代备份 | 最危险的单条命令，无回滚 |
| A4 | 异地备份未定 | bundle 在 `~/` 与主仓同盘 | 磁盘故障 / `git clean -xdf` 两场景无解 |

**建议**：A1-A4 合并处理——`aligned_verdicts.jsonl` 开独立 bare repo + cron rsync 到异盘 / 对象存储；禁用 `git clean -xdf` 改为白名单脚本。

---

## 🟠 P1：逻辑缺陷（影响产出质量）

| # | 项 | 现状 | 影响 |
|---|---|---|---|
| ~~L1~~ | ~~`_dead_families()` 误判~~ | ✅ **已修复**（2026-10-03）：docstring 明确 `set_mismatch_descriptive` 不计数；测试 `test_supervisor.py:1663/1678` 验证正确行为 | - |
| ~~L4~~ | ~~cadence 默认值漂移~~ | ✅ **已修复**（2026-10-08）：`_CADENCE_DEFAULTS` + `_cad_int()` 单源化，缺键回退打 WARN。**范围比原记录大**：`aligned_max_points` 曾在同一文件三处互相矛盾（签名 600 / 复测处 600 / 收割处 **400**） | - |
| ~~L5~~ | ~~data_stale 旁路验收测试~~ | ✅ **已补**（`tests/test_success_gate_stale_20261006.py`，5 个测试函数完整覆盖） | - |

**建议**：~~L4 半天修复~~ → ✅ 已完成（2026-10-08）。本节现仅 L2（已修复）与 L4（已修复）。

---

## 🟡 P2：peer 学习机制断裂（影响长期进化）

| # | 项 | 现状 | 影响 |
|---|---|---|---|
| ~~L2~~ | ~~`_has_prior_failure` 单键 OR~~ | ✅ **已修复**（2026-10-08）：改为 `(symbol, cov)` **配对 AND**。同 symbol 异 cov、异 symbol 同 cov 不再误拦。连带重写 6 个锁定旧语义的测试 | - |
| M1 | cross-run feedback channel 未实施 | `shared_store.db` / `research_memory.jsonl` / `cross_run_learning.jsonl` **全不存在** | peer 每次 run 从零开始，看不到历史 133 条 gate_pass 统计 |
| M2 | `## Locked this window` 未触发 | 函数 `_locked_section()` 存在（line 2494）但**零调用点** | peer 重复提案已锁死组合（当前 391 条里有大量重复探索） |
| M3 | 拒收理由不回写 peer | 18 道门拒收 → 只进 `supervisor_decisions.jsonl`；peer 输入只有 `known_verdicts.inc.md` + `covariate_menu.inc.md` | 91% 拒收来自 3 道纯规则门（`no_failure_delta` 57% / `family_dead` 18% / `dedup` 16%），peer 全看不到 |
| M4 | D4 `decision: abandon` 未实施 | spec 在 `2026-10-03-peer-memory-loop-closure-spec.md`，排 D1 之后 | falsifier 角色被迫产出正例提案才能表达反对（3651 份历史提案 JSON 均无该字段）|
| M5 | `n_eff` 实际是常数函数 | 所有裁决都显示 73（是 n=588 的常数函数）| peer 误以为 n_eff 是有效样本量 |

**建议**：L2 + M1-M5 是同一问题的六个切面（参考 `2026-10-05-peer-learning-gap-analysis.md` T1-T3 + spec D1-D4）。下一 sprint 整体实施。

---

## 🟢 P3：口径 / 文档 / 运维债（慢性腐烂）

| # | 项 | 现状 |
|---|---|---|
| D1 | 行号腐烂 | peer 提示词内嵌规格行号；代码一天 9 笔合入 → 行号全移 |
| ~~D2~~ | ~~`star` 字段全历史不存在~~ | ✅ **已完成 + 范围扩大**（2026-10-08）：
|      |      | **本条原描述只对了一半** —— verdict 上的 `star` 字段确实自始不存在，但品种信用星（`SCHEMES[].stars` → `credit_stars`，CF-10 A 锁定唯一源）是**活跃子系统**，文档里 `list_by_stars(2)` / `1★` 全是正确术语。清理时若照单全清会删掉活跃子系统。
|      |      | 已处置：`n_one_star_symbols_hit` → `n_goal_symbols_hit`；信用档整体退役（`scheme.stars` / `list_by_stars()` / KB `credit_stars` 全删）；信心分级改由 L1 PF/EV 派生（`evidence_grade`）；`two_star_*` 归档 |
| ~~D3~~ | ~~`user_paused` 死标志~~ | ✅ **已清理**：`restart_three_loop_clean.sh` 不存在；`clear_supervisor_pause.py` 在 `scripts/archive/2026-09-30-dead-code/`；active 代码无引用 |
| D4 | WSL 看门狗未重建 | 被系统内存压力回收后无恢复；supervisor 异常退出无人重启 |
| D5 | supervisor ↔ run 追踪断裂 | `start_new_session=True` 派发 run；父进程死 → run 孤儿还在烧 token |
| D6 | `praxist_control_plane.md` 消歧 | ✅ **部分完成**：`docs/runtime_contract.md` line 5 已加消歧注记 `⚠️ **同名不同物**`；但 `docs/superpowers/specs/praxist_control_plane.md` 仍未归档 |
| D7 | specs 积压 13 个 | `docs/superpowers/specs/` 大部分无结案标记 |
| ~~D8~~ | ~~A2 Track B 死代码~~ | ✅ **已删除**：`cascade/lgbm_features.py` 不存在 |
| ~~D9~~ | ~~`write_first_preregistry.py` 未挂账~~ | ✅ **已挂账**：`tests/test_no_dead_code.py` 已加入 `TEMPORARY_ALLOWLIST`，出处记录为"一次性人工命令" |

---

## 汇总

| 优先级 | 数量 | 主要特征 |
|---|---|---|
| 🔴 P0 资产单点 | 4 | 不可恢复风险，需立刻处理 |
| 🟠 P1 逻辑缺陷 | 3（原 5，2 已关闭） | 影响当前产出质量，1 周内 |
| 🟡 P2 peer 学习 | 6（原 5，+L2 降级） | 影响长期进化，下一 sprint |
| 🟢 P3 慢性腐烂 | 5（原 9，4 已关闭） | 文档/运维/口径，可观察 |
| **合计** | **18**（原 23） | |

### 2026-10-08 审核后（本次）

| 优先级 | 原数 | 处置后 | 说明 |
|---|---:|---:|---|
| 🔴 P0 资产单点 | 4 | 4 | 本次未处理（需运行时环境；口径已改为主仓推 `origin`） |
| 🟠 P1 逻辑缺陷 | 3 | **0** | L2 / L4 已修复，L1 / L5 此前已修 |
| 🟡 P2 peer 学习 | 6 | 4 | L2 移出（已修）→ M1 / M3 / M4 / M5 未处理 |
| 🟢 P3 慢性腐烂 | 5 | 4 | D2 已完成；D1 / D4 / D5 / D7 未处理 |
| **合计** | **18** | **12** | 本次关闭 6 条（L2 / L4 / D2 + 此前 L1 / L5 / D3） |

---

## 2026-10-08 审核：实施结论与新增发现

> 本节记录本次实施时的代码核实结论。**清单若干说法已被证伪**，以本节与代码为准。

### 已关闭

| 条目 | 状态 | 实施要点 |
|---|---|---|
| L2 | ✅ 已修复 | `_has_prior_failure` 改 `(symbol, cov)` 配对 AND。属准入语义，verdict schema 未变，**协议指纹不动** |
| L3 | ✅ 新增条目并修复 | 见 N5 |
| L4 | ✅ 已修复 | 见上方 P1 节；另发现 `run_budget_hours` 代码默认 2.0 vs yaml 1.5（同类漂移，未纳入） |
| D2 | ✅ 已完成 | 见上方 P3 节 |

### 新增发现（清单未列）

- **N5（清单低估）**：目标品种集原有**三份**副本，不止两份 —— yaml(24) / `GOAL_SYMBOLS_SET` 硬编码(9) / `build_snapshot` 内 `TARGET_SYMBOLS` 硬编码(24)。已全部单源化到 yaml，`ALLOWED_SYMBOLS` 亦改为从 yaml 派生（fail loud）。
- **N6**：旧 9 个集合自称「1★ 信用品种」，但实测 1★ 恰 **14** 个、≥2★ **7** 个 —— 它与任何一档信用星都对不上，是**第三套独立口径**，并非 yaml 的子集漂移。
- **N7（清单说错）**：候选准入门 `ALLOWED_SYMBOLS`(21) 的内容**恰好等于 `SCHEMES`(21)**，而非目标(24)。造成双向割裂：`oi`/`px`/`y` 是攻坚目标却被准入门挡死（**goal 要求达标却无法产出任何候选**），`jm` 能过门但不被 goal 统计（孤儿）。已裁定归一并删除 `sc`、补入 `jm`。
- **N8（比清单严重）**：KB 全表 PF/EV 为 null 使 `INCUMBENT_PF` 恒空，`ratio = pf / INCUMBENT_PF.get(sym, 1.0)` **静默把「相对 incumbent 超 105%」改写成「PF 绝对值 > 1.05」** → 退化裁决被过度复测。且 KB 是静态提交产物，**永不自愈**。已按裁定 C+a 删除该判据。
- **N9**：信用档被 CF-10 A 钉为 KB `credit_stars` 唯一源，反而把 2026-08 冻结值固化成「唯一事实源」—— L1 证据 0/21 全缺失时仍输出 1~3 星，用陈旧值冒充信心。已退役。
- **N10**：`tier` 一词有三套重载语义：`tier_classifier`(变体级 S/A/B/C/D) / `supervisor`(品种级 可预测/当前不可验证/需更多样本) / `two_star_critic`(硬编码 A/B/C 作业批次)。已埋雷：`supervisor:1149` 用 `v.get("tier") in ["A","B"]` 读裁决，若第三套语义被写入 verdict 会被静默当作变体级 A。**待处置**。

### 建议处置顺序（更新）

1. **P3 D4 / D5**（运维风险：supervisor 被回收无人拉起 / 父死子孤烧 token）—— 唯一仍在 P0/P1/P2/P3 里属"无人值守也会出事"的
2. **P0 A1-A4**（需运行时环境执行）
3. **N10 tier 语义澄清**（改名消歧 + 语义隔离守卫；`variant_tier` 改名涉及裁决字段，需走协议指纹评估）
4. **P2 M1 / M3 / M4 / M5**（peer 学习 sprint，3-4 天）
5. **P3 D1 / D7**（见缝插针）

---

## 2026-10-08 审核

---

## 建议处置顺序

1. **P0 资产保护**（1-2 天）：独立 bare repo + cron rsync + 禁用 `git clean -xdf`
2. **P1 L4 `survivors_per_cycle` 默认值对齐**（半天）：yaml=3 / 代码默认=2 不一致
3. **P2 整体**（一周）：L2 + M1-M5 + D1-D4（peer 学习 T1-T3 + spec D1-D4）
4. **P3 慢性腐烂**：见缝插针，优先 D4/D5（运维风险）

---

## 相关文档

- `docs/superpowers/reports/2026-10-05-peer-learning-gap-analysis.md` — peer 学习断裂分析
- `docs/superpowers/specs/2026-10-03-peer-memory-loop-closure-spec.md` — D1-D4 闭合 spec
- `docs/superpowers/reports/2026-10-06-holiday-success-gate-deadlock-diagnosis.md` — 10-06 死锁诊断
- `docs/superpowers/changelogs/2026-10-06-holiday-success-gate-data-stale.md` — dfd1f43 changelog
- `docs/superpowers/reports/2026-10-03-fm-a-open-issues.md` — 10-03 未决问题清单
- `docs/superpowers/plans/2026-10-03-three-loop-open-closure.md` — 10-03 闭合计划

---

**报告生成**: 2026-10-07 ~07:30
**本次审核**: 2026-10-07 ~19:00（核实代码库，更新 5 条已关闭/降级）
**第二次审核**: 2026-10-08（实施 L2/L3/L4/D2 + 信用档退役 + 宇宙对齐；关闭 6 条、新增 N5-N10；详见「2026-10-08 审核」节与 `changelogs/2026-10-08-tech-debt-p1-closure-credit-star-retirement.md`）
**盘点者**: Claude Code（主会话）
**下次盘点触发**: 下次长假或 peer 学习 sprint 启动时
