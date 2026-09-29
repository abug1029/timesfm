# 第六轮审计处置 — Changelog

- **日期**：2026-09-29
- **基线**：`eecf05a`
- **产出 commit**：`a068d92`（ponytail 批次 + 第六轮修复）、`381f31e`（spec-alignment 主体）、本文件所在 commit
- **状态**：3 个 commit 均**未推送**（`master...origin/master [ahead 3]`）
- **处置人**：主循环直接实施
- **完整报告**：`D:\FlyBuddy\fma-audit\2026-09-29-fma-sixth-audit-resolution.md`
- **被处置的审计**：`D:\FlyBuddy\fma-audit\2026-09-29-fma-sixth-audit-ponytail-artifacts.md`

---

## 一句话

审计对 ponytail 清理**本身**的判定成立且正确；问题全部在**证据质量与表述准确性**上。处置后 13 项预存在失败清零，全量 `1646 passed / 8 skipped / 1 xfailed / 0 failed`。

---

## 提交拆分

两批工作长期混在一个脏树里会污染 Phase 的 diff 归因与测试对账（审计建议 2 的理由），故拆为两个独立 commit。

### `a068d92` — ponytail 清理 + 第六轮修复

17 文件，+336 / −1659（净 −1323）

| 文件 | 变更 | 内容 |
|---|---|---|
| `audit_futures.py` | −361 | 删（2026-09-07 一次性脚本） |
| `audit_futures_v2.py` | −448 | 删 |
| `fix_audit_issues.py` | −98 | 删 |
| `fix_indicators.py` | −84 | 删 |
| `check_db.py` | −28 | 删 |
| `cascade/regime_classifier.py` | −324 | **删**（被 `realtime_regime_classifier.py` 取代）——活引用已清零，仅余本行的历史记录 |
| `cascade/neutral_ab_render.py` | −223 | **删**（合并入 `neutral_ab_report.py`）——活引用已清零，仅余本行的历史记录 |
| `cascade/neutral_ab_report.py` | +217/−2 | 合并 `render_markdown`（函数体逐字节一致） |
| `cascade/features.py` | +61/−54 | 合并 `calc_rolling_hurst` + `calc_rolling_hurst_raw`（11 个调用点全部核对） |
| `cascade/ccl_monitor.py` | −24 | 移除 `CCLAlert.format_report()` |
| `scripts/cascade_predict.py` | +17/−1 | 内联 `format_report` 到唯一调用点 |
| `scripts/regime_covariate_analysis.py` | +46/−1 | **重写并简化** `classify_market_regime` |
| `scripts/praxist_supervisor.py` | +25/−6 | K6 图例去重 + K7 惰性解析 + M4 截断 |
| `cascade/AGENTS.md` | +2/−3 | K4：更正两行指向已删文件的说明 |
| `tests/test_a2_p1_baseline.py` | +26 | 陈旧锁自愈 + pyarrow 守卫 |
| `tests/test_supervisor.py` | +5/−1 | K6：断言去重措辞 + 新增「图例不重复」守卫 |
| `tests/test_neutral_ab_report.py` | +1/−1 | K4：`renderer` 字段断言改指真实文件 |

**该树实测**：`13 failed / 96 passed / 1 skipped`（6 个相关文件），13 项全部预存在，本提交**零新增失败**。

### `381f31e` — spec-alignment Phase 1-10

37 文件，+3746 / −105。Phase 1-10 全部交付，15 个实施过程中发现的真实缺陷已修，4 个「因错误的原因通过」的测试已纠正。明细见 `2026-09-29-stage3-impl-and-prep.md`。

**全量实测**：`1646 passed / 8 skipped / 1 xfailed / 0 failed`（393.84s）。

---

## 审计条目逐项处置

| # | 严重度 | 核实 | 处置 |
|---|---|---|---|
| K1 | 中 | 成立，**前提需修正** | changelog 按实测数字重写并附勘误 |
| K2 | 低 | 成立 | 「内联」→「重写并简化，排序规则与原实现一致」+ 新旧差异说明 |
| K3 | 中 | 成立 | 拆 2 commit；工作树已干净 |
| K4 | 低 | 成立 | 3 处字符串 + AGENTS.md 2 行更正，`grep` 清零 |
| K5 | 低 | **已自动消解** | Phase 9 已改名 `test_eval_grid_uses_config_step`，读 config 不硬编码 |
| K6 | 低 | 成立 | 图例去重，条件统一为 `not (fdr_pass or migrated_pass)` |
| K7 | 低 | 成立 | `_praxist_bin()` 惰性解析，模块级只剩 `_PRAXIST = None` |
| K8 | 观察 | 成立，**定性需修正** | LFS 指针 vs 本地重生成输出，非代码变更；不动 |
| K9 | 观察 | 成立 | 未重启（用户选自行重启），已出 runbook |
| M4 | 中 | 成立，**影响被低估** | 截断只切尾部，超限显式标注 |

### M4 —— 本轮唯一有实质数据价值的发现

`materialize_known_verdicts` 排序键是 `(gate_pass 优先, dir_acc 降序)`，截断却是 `items[:20]`。**被切掉的正是「已解出、不要再提」的集合本身**，直接违反该文件自己的表头契约。

对活仓真实 171 行 registry 实测：

| | 修复前 | 修复后 |
|---|---|---|
| 进 peer 提示词的 `gate_pass=True` | **20 / 42** | **43 / 43** |
| 被静默吞掉的「已解出」条目 | **22** | 0 |
| 尾部 DEAD 条目 | — | 37（上限 80） |

### K7 的验证

```
# 隐藏 praxist 二进制后
import OK with no praxist binary
module has eager PRAXIST const? False
raises only at call time: praxist binary not found (tried PRAXIST_BIN, ...)
```

---

## 审计未列出的新发现

### A. ~~审计的 `1491/14/5/1` 是在 `git worktree` 里采的~~ —— **指控不成立，已撤回**

> **勘误（2026-09-29，第八轮审计 N1）**：我误读了第六轮报告抬头的「本轮通过 `git worktree` 在 HEAD 做对照实验」与「worktree 收集 1347 vs 活树 1511」，据此推断全量实跑发生在 worktree 内。复核该轮 `audit56.sh` 后确认这是错的：
>
> - 第 2 行 `cd /home/abug/timesfm`（活仓）
> - 第 3-9 行 worktree **仅**用于诊断「纯 HEAD 下 8 个 supervisor 测试文件为何收集失败」，第 8 行即 `git worktree remove --force`
> - 第 11-12 行全量实跑标题明写 `FULL SUITE on live tree (ground truth, tests/ scoped)`，cwd 为活仓
>
> 算术亦印证：1491+14+5+1 = **1511** = 活仓收集数；worktree 因缺 praxist 二进制只能收集 **1347** 项，那组数字在 worktree 内**算术上不可能产出**。
>
> **K1 本身仍然成立** —— ponytail changelog 的 `1486/13 (236s)` 确实不可复现。错的只是我对差异原因的解释。
>
> **根因（我自己的）**：从报告的**方法描述**推断了**执行位置**，没有去读执行脚本。取证纪律是「读脚本，不读转述」—— 我这次恰好违反了它刚写给我的那条规矩。

### B. 陈旧锁的真因是 pyarrow 未装

审计把两个 2026-09-18 的锁判为「崩溃残留」。查 `reports/a2_p1.1_logs/ss.log` 发现该 run 死于：

```
File "cascade/lgbm_features.py", line 340, in build_dense_feature_matrix
    market_df.to_parquet(tmp_path)
ImportError: Unable to find a usable engine; tried using: 'pyarrow', 'fastparquet'.
```

venv 未装 pyarrow → ImportError 让 worker 硬崩 → 锁永不释放。锁是缺依赖的**次生**现象。

处置：锁已清（两处，持有者 PID 1003 / 1018 均已死 11 天、该 run 未产出任何结果）；测试加 `pytest.importorskip("pyarrow")`，与该文件既有的 `importorskip("lightgbm")` 同一约定。`cascade/lgbm_features.py` 是归档轨道（AGENTS.md 已标注 A2 Track B 已关），无生产入口 import。

同时给测试加 `_clear_stale_locks()` 前置：只清**持有者进程已死**的锁，活着的锁（含属于其他用户的进程）保留 —— 与 `exclusive_result_lock`「不自动清理 stale lock，由用户显式决定」的契约一致。

### C. K8 的定性

子模块脏的 4 个文件是 LFS 指针（各 131 字节）与本地重生成内容（PNG 头正常，`tEXtSoftware: Matplotlib 3.10.9`）的差异，属运行 example 的产物，对 FM_a 零影响。还原只会把 PNG 换回指针。故意不动。

### D. 审计的 `a2_p1×3` 与实测 `×2` 不符

实测 2 项（`test_eval_grid_matches_worker_boundary`、`test_eval_grid_step_24`）。13 项总数以本次实测为准。

---

## 13 项预存在失败（`a068d92` 树实测）

| 测试文件 | 数 | 根因 | 处置（均在 `381f31e`） |
|---|---|---|---|
| `test_timesfm_model_path.py` | 6 | 硬编码模型 2.5，实际 3.0 | 改为 `data.config` 单一真相 |
| `test_index_continuous_quality.py` | 2 | 数据新鲜度，外部回填依赖 | graceful skip |
| `test_a2_p1_integrity.py` | 2 | config `STEP` 为 2，测试硬编码 24 | 改为读 config |
| `test_cov_family.py` | 1 | 根 pool 缺 `oi_gated_momentum` | 补入根 pool |
| `test_extract_xreg_oi_gated.py` | 2 | covariate status experimental→active | 改为 active |
| `test_a2_p1_baseline.py` | 0（skip） | 需 pyarrow | `importorskip` |

---

## 顺手更正的文档失真

| 文件 | 失真 | 更正 |
|---|---|---|
| `.omc/artifacts/ponytail-audit-changelog-2026-09-29.md` | 测试数字 `1486/13 (236s)` 不可复现 | 换为独立复跑值 `1491/14/5/1 (381.95s)`。该勘误**不含** worktree 说法（第八轮 N1(c) 已核实）|
| 同上 | 「7 文件 1343 行」算术错 | 7 文件实为 **1566** 行；1343 是前 6 个死码文件的和 |
| 同上 | `classify_market_regime` 标为「内联」 | 改为「重写并简化」+ 新旧差异说明 |
| `docs/superpowers/changelogs/2026-09-29-stage3-impl-and-prep.md` | `1641/0`、`143 历史裁决` | 换为实测 `1646/8/1/0`；registry 实为 **171** 条且全为 pre-A1（0 条具备新字段） |

---

## 本轮自身的两处失误（留档以免重复）

1. **误判 commit 1 损坏。** 验证 M4 时读 `git diff` 后一度断定 `a068d92` 把 `verdicts_truncated` 块错误复制进 `_effective_clue_lines`，准备 amend。复核 HEAD 与工作树后确认：两者都只有 1 处标记，位于 `materialize_known_verdicts` 第 846 行，commit 1 无需修改 —— 那次 diff 读法有误。
   工作树里的重复块是真的：由 `git stash` 往返引入，已清除，并因此重跑全量确认 0 失败。
   **教训：stash 往返后必须重跑验证，不能假设恢复无损。**
2. **沿用未核实的「内联」标签。** K2 的根子是第一轮按 diff 大小写标签，未核对旧实现其实是 16 行包装类。**断言代码行为前应先读旧实现。**

---

## 留给用户的两件事

1. **推送**（可选）：3 个 commit 均为 `ahead 3`，未推送。
2. **重启 supervisor**：PID 22703 仍在跑 09-28 的内存代码（处置时已 21 小时 / 171 cycles）。用户选择自行重启。
   - Runbook：`D:\FlyBuddy\.omc\artifacts\sixth-audit-supervisor-restart-runbook.md`
   - 重启后最该立刻核对的两条：
     - `grep -c "v1 legacy: pass by ev>0" task_FM/known_verdicts.inc.md` → 应为 **1**（K6）
     - `grep -c "gate_pass=True" task_FM/known_verdicts.inc.md` → 应为 **43**（M4，此前只有 20）

---

## 文档索引

| 类型 | 路径 |
|---|---|
| **本 changelog** | `docs/superpowers/changelogs/2026-09-29-sixth-audit-resolution.md` |
| 完整处置报告 | `D:\FlyBuddy\fma-audit\2026-09-29-fma-sixth-audit-resolution.md` |
| 被处置的审计 | `D:\FlyBuddy\fma-audit\2026-09-29-fma-sixth-audit-ponytail-artifacts.md` |
| 重启 runbook | `D:\FlyBuddy\.omc\artifacts\sixth-audit-supervisor-restart-runbook.md` |
| ponytail changelog（已勘误） | `D:\FlyBuddy\.omc\artifacts\ponytail-audit-changelog-2026-09-29.md` |
| spec-alignment changelog | `docs/superpowers/changelogs/2026-09-29-stage3-impl-and-prep.md` |
| Spec v15 | `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md` |
| Plan rev2 | `docs/archive/superpowers-plans/2026-09-29-spec-alignment-impl-plan.md`（已归档） |
