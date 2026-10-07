# FM_a 技术债清单

> **日期**: 2026-10-07
> **盘点范围**: supervisor 代码、peer 学习通道、资产保护、口径/文档/运维
> **盘点依据**: `docs/superpowers/reports/` 下所有诊断报告 + `docs/superpowers/specs/` 下未结案 spec + 代码核实
> **总条数**: 18 条（P0=4 / P1=3 / P2=6 / P3=5）
> **本次审核**: 2026-10-07 ~19:00 核实代码库，5 条已修复（L1/L5/D3/D8/D9）、L2 降级至 P2

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
| L4 | `survivors_per_cycle` 默认值 | yaml=3（`praxist_goal.yaml`）、代码默认=2（`cad.get("survivors_per_cycle", 2)`），**键不存在时**才生效 | 边缘条件易错 |
| ~~L5~~ | ~~data_stale 旁路验收测试~~ | ✅ **已补**（`tests/test_success_gate_stale_20261006.py`，5 个测试函数完整覆盖） | - |

**建议**：L4 半天修复，对齐 yaml 和代码默认值。

---

## 🟡 P2：peer 学习机制断裂（影响长期进化）

| # | 项 | 现状 | 影响 |
|---|---|---|---|
| L2 | `_has_prior_failure` 单键 OR | 同 symbol **或**同 cov 命中即判失败（非配对）；**2026-10-03 已收窄**：只认可 `_is_confirmable_failure`（描述性行不计入），污染半径显著缩小但仍存在 | 中等 |
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
| D2 | `star` 字段全历史不存在 | 评级由 `tier` 承载（`cascade/tier_classifier.py`），但文档多处还提 `star` |
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
**盘点者**: Claude Code（主会话）
**下次盘点触发**: 下次长假或 peer 学习 sprint 启动时
