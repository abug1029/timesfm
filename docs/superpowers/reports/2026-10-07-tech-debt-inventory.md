# FM_a 技术债清单

> **日期**: 2026-10-07
> **盘点范围**: supervisor 代码、peer 学习通道、资产保护、口径/文档/运维
> **盘点依据**: `docs/superpowers/reports/` 下所有诊断报告 + `docs/superpowers/specs/` 下未结案 spec + 代码核实
> **总条数**: 23 条（P0=4 / P1=5 / P2=5 / P3=9）

---

## 🔴 P0：资产单点故障（不可恢复风险）

| # | 项 | 现状 | 风险 |
|---|---|---|---|
| A1 | `aligned_verdicts.jsonl` 从未进 git | `.gitignore:76` 是 `d236671` 清 API key 的**副作用**，非有意排除 | remote + bundle 都没有裁决历史；磁盘故障 = 全失 |
| A2 | 三代备份**全在同盘** | v1 原始 / v2 封存 / v2 逐 cycle 都在 `/home/abug/` | 磁盘故障 = 全失 |
| A3 | `git clean -xdf` 一锅端 | 同时删原件 + 三代备份 | 最危险的单条命令，无回滚 |
| A4 | 异地备份未定 | bundle 在 `~/` 与主仓同盘 | 磁盘故障 / `git clean -xdf` 两场景无解 |

**建议**：A1-A4 合并处理——`aligned_verdicts.jsonl` 开独立 bare repo + cron rsync 到异盘 / 对象存储；禁用 `git clean -xdf` 改为白名单脚本。

---

## 🟠 P1：逻辑缺陷（影响产出质量）

| # | 项 | 现状 | 影响 |
|---|---|---|---|
| L1 | `_dead_families()` 误判 | 把 `set_mismatch_descriptive` 计入死亡阈值 → `term_structure` 5 条全判死 | peer 提案被 `family_dead` 硬拦 |
| L2 | `_has_prior_failure` 单键 OR | 同 symbol **或**同 cov 命中即判失败（非配对）| 污染半径比文档描述大 |
| L3 | `GOAL_SYMBOLS_SET` 9 个 vs `goal.yaml` 24 个 | 后者只用于开局基线预检 | 语义分裂 |
| L4 | `survivors_per_cycle` 默认值 | yaml 3、代码默认 2，但**键不存在时**才生效 | 边缘条件易错 |
| L5 | data_stale 旁路（dfd1f43）| 设计正确但未写验收测试 | 10/8 后旁路自动失效无监控；下次长假可能复现 |

**建议**：L1 是最高 ROI 的修复（一行改动，影响面大）；L2-L4 收口到 runtime_contract；L5 补一个 `test_data_stale_holiday.py`。

---

## 🟡 P2：peer 学习机制断裂（影响长期进化）

| # | 项 | 现状 | 影响 |
|---|---|---|---|
| M1 | cross-run feedback channel 未实施 | `shared_store.db` / `research_memory.jsonl` / `cross_run_learning.jsonl` **全不存在** | peer 每次 run 从零开始，看不到历史 133 条 gate_pass 统计 |
| M2 | `## Locked this window` 未触发 | 函数存在但未写入 peer prompt | peer 重复提案已锁死组合（当前 391 条里有大量重复探索） |
| M3 | 拒收理由不回写 peer | 18 道门拒收 → 只进 `supervisor_decisions.jsonl`；peer 输入只有 `known_verdicts.inc.md` + `covariate_menu.inc.md` | 91% 拒收来自 3 道纯规则门（`no_failure_delta` 57% / `family_dead` 18% / `dedup` 16%），peer 全看不到 |
| M4 | D4 `decision: abandon` 未实施 | spec 在 `2026-10-03-peer-memory-loop-closure-spec.md`，排 D1 之后 | falsifier 角色被迫产出正例提案才能表达反对（3651 份历史提案 JSON 均无该字段）|
| M5 | `n_eff` 实际是常数函数 | 所有裁决都显示 73（是 n=588 的常数函数）| peer 误以为 n_eff 是有效样本量 |

**建议**：M1-M5 是同一问题的五个切面（参考 `2026-10-05-peer-learning-gap-analysis.md` T1-T3 + spec D1-D4）。下一 sprint 整体实施。

---

## 🟢 P3：口径 / 文档 / 运维债（慢性腐烂）

| # | 项 | 现状 |
|---|---|---|
| D1 | 行号腐烂 | peer 提示词内嵌规格行号；代码一天 9 笔合入 → 行号全移 |
| D2 | `star` 字段全历史不存在 | 评级由 `tier` 承载（`cascade/tier_classifier.py`），但文档多处还提 `star` |
| D3 | `user_paused` 死标志 | 全仓无代码读；`clear_supervisor_pause.py` 与 `restart_three_loop_clean.sh` 清它 = 空转 |
| D4 | WSL 看门狗未重建 | 被系统内存压力回收后无恢复；supervisor 异常退出无人重启 |
| D5 | supervisor ↔ run 追踪断裂 | `start_new_session=True` 派发 run；父进程死 → run 孤儿还在烧 token |
| D6 | `praxist_control_plane.md` 消歧 | `docs/superpowers/specs/` 里那份与 `docs/runtime_contract.md` 同名不同物 |
| D7 | specs 积压 13 个 | `docs/superpowers/specs/` 大部分无结案标记 |
| D8 | A2 Track B 死代码 | `cascade/lgbm_features.py` 依赖 pyarrow（未装）；测试已退役（`b8a6d36`）；复活代价高 |
| D9 | `write_first_preregistry.py` 未挂账 | 一次性脚本，出处不明 |

---

## 汇总

| 优先级 | 数量 | 主要特征 |
|---|---|---|
| 🔴 P0 资产单点 | 4 | 不可恢复风险，需立刻处理 |
| 🟠 P1 逻辑缺陷 | 5 | 影响当前产出质量，1 周内 |
| 🟡 P2 peer 学习 | 5 | 影响长期进化，下一 sprint |
| 🟢 P3 慢性腐烂 | 9 | 文档/运维/口径，可观察 |
| **合计** | **23** | |

---

## 建议处置顺序

1. **P0 资产保护**（1-2 天）：独立 bare repo + cron rsync + 禁用 `git clean -xdf`
2. **P1 L1 `_dead_families` 修复**（半天）：一行改动、ROI 最高
3. **P1 L5 data_stale 验收测试**（半天）：为下次长假做准备
4. **P2 peer 学习 T1-T3 + D1-D4**（一周）：整体实施
5. **P3 慢性腐烂**：见缝插针，优先 D3/D5（运维风险）

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
**盘点者**: Claude Code（主会话）
**下次盘点触发**: 下次长假或 peer 学习 sprint 启动时
