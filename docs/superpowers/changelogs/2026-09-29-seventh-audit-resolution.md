# 第七轮审计处置 — Changelog

- **日期**：2026-09-29
- **基线**：`eecf05a`
- **被处置的审计**：`D:\FlyBuddy\fma-audit\2026-09-29-fma-seventh-audit-stage3-impl.md`
- **完整报告**：`D:\FlyBuddy\fma-audit\2026-09-29-fma-seventh-audit-resolution.md`
- **审计采样时点**：HEAD = `eecf05a` + 49 个未提交文件 —— **即本轮修订开始前的树**
- **实测**：`.venv/bin/python -m pytest tests/ -q` → `1646 passed / 7 skipped / 1 xfailed / 0 failed`（775.45s，退役 smoke 后由 8 skip 降为 7 skip，passed 数不变）
- **产出 commit**：`a068d92`、`381f31e`、`4c347df`（前一轮）、本文件所在 commit

---

## 一句话

审计的两项主要判断成立：实现质量高、计划落实忠实；头条测试声明不实、流程纪律失守。但**L1 / L3 / L5 三项在本报告成文之前已被本轮工作消解** —— 那三个 commit 正是针对它们的对策。仍然成立并已处置的是 **L2(c)、L4、L6**。

---

## 逐条处置

| # | 严重度 | 审计判定 | 状态 |
|---|---|---|---|
| L1 | 高 | 头条测试声明不实（1641/0 vs 实测 1646/1/7/1） | **已消解** — changelog 钉实测值，commit 带 F1 三件套 |
| L2 | 高 | smoke 测试三重损坏 | **(a)(b) 已修 → (c) 已退役** |
| L3 | 高 | 混版本生产窗口正在发生 | **已消解（提交侧）** — 树已干净；supervisor 旧内存代码部分由用户保留决策 |
| L4 | 中 | Phase 7 状态虚高 | **已修** — 表格改 ⚠️，注明真接线延期 |
| L5 | 中 | `git add -A` 单巨提交违规 | **已消解** — 拆 3 笔，子模块 `:(exclude)third_party`；审计建议的 hunk 手术正是实际做法 |
| L6 | 低 | 数字卫生（155/144、13/14、143/170） | **已修** — 143→171、13→14、Phase 9 改「14 项中的 13 项」 |
| L7 | 观察 | `weight_fingerprint` 是路径+version.txt 弱化代理 | 不改，docstring 已声明承重假设 |
| L8 | 观察 | 新旧双身份系统并存、同名异签名 | 不改，退役时需防误用 |
| L9 | 观察 | 第六轮 K1 之谜部分解开（slow 计数=3） | 记录在案，教训不变：钉命令 |

---

## L2 拆解 —— 三条腿逐条确认

### (a) 09-18 陈旧锁 —— 已修

`reports/a2_p1.1_logs/a2-p1.1.orchestrator.lock`（pid 1003）与
`reports/a2_p1.1_results/ss.worker.lock`（pid 1018），持有者进程均已死 11 天，
该 run 未产出任何结果。已清除。

### (b) venv 缺 pyarrow —— 已查明真因

审计说「a2_p1 worker 在本机根本无法运行」，成立且更具体：

```
File "cascade/lgbm_features.py", line 340, in build_dense_feature_matrix
    market_df.to_parquet(tmp_path)
ImportError: Unable to find a usable engine; tried using: 'pyarrow', 'fastparquet'.
```

`reports/a2_p1.1_logs/ss.log` 中 2026-09-18 与 2026-09-29 两次 run 崩溃栈完全相同。

**这修正了第六轮对锁的定性**：锁不是「崩溃残留」的独立故障，而是缺依赖 → ImportError
→ worker 硬崩 → `exclusive_result_lock` 永不释放的**次生**现象。

### (c) 断言的 jsonl 无任何生产代码写入 —— 坐实，处置：退役

```
$ grep -rn "a2_p1_baseline_results" --include=*.py .
./tests/test_a2_p1_baseline.py:121:    out_jsonl = pathlib.Path("reports/a2_p1_baseline_results.jsonl")
```

全仓 `.py` 命中**仅此一处，即测试自身**。其余引用全在
`docs/archive/superpowers-{plans,specs}/2026-08-*`。`scripts/a2_p1_lgbm_baseline.py`
对 `jsonl` / `manifest` / `report_path` / `results_dir` / `json.dump` 的 grep **零命中**
—— 它是纯 orchestrator，产物由 worker 写到 `reports/a2_p1.1_results/` 与
`reports/research/`。盘上该文件亦不存在。

**该断言永远不可能通过。** 这不是「暂时失败」的测试，是结构性死掉的断言 ——
上一轮 changelog 那条教训（测试因错误的原因通过）的对偶：因错误的原因**永远失败**。

**处置：退役 `test_smoke_ss_end_to_end`**（用户裁定）。理由链完整：

- 断言指向无人写入的路径 → 结构性失效
- 执行路径 `cascade/lgbm_features.py` 属 A2 Track B，`cascade/AGENTS.md` 已标注
  「**已关**、生产入口不 import、仅 A2 脚本与测试仍引用」
- venv 无 pyarrow / fastparquet，该路径在本机不可执行

一并移除、且只服务于该测试的三样：pyarrow `importorskip` 守卫、
`_clear_stale_locks()` 助手、无用的 `subprocess` 局部导入。**无死代码残留**
（grep 确认三者皆无，文件 5 passed / 0 skipped）。

退役的是「一条永不通过的断言」，不是覆盖 —— 同文件其余 5 个测试针对
`train_lgbm_walkforward` 与 `evaluate_gate` 的真实逻辑，全部保留且通过。
退役原因已写入文件尾部注释，防止后人盲目「恢复」。

---

## L4 / L6 的具体修订

`docs/superpowers/changelogs/2026-09-29-stage3-impl-and-prep.md`：

| 位置 | 原文 | 改为 |
|---|---|---|
| Phase 表第 7 行 | `PR-B1 \| experiment_fingerprint + fail-loud \| ✅` | `⚠️ 模块就绪、fail-loud 已退役；**supervisor variant_id 真接线延期**（见「故意未做」）` |
| Phase 表第 9 行 | `卫生 \| 修复全部 13 预存在失败 \| ✅` | `修复 14 项预存在失败中的 13 项 \| ✅ 第 14 项（smoke）转为 skip` |
| 抬头测试行 | `13 项预存在失败 → 0 失败` | `eecf05a 基线有 **14** 项预存在失败 → 0 失败。13 项由 Phase 9 修复；第 14 项（smoke）转为 skip` |
| 第六轮附录 C | `13 vs 14 的差异来自 smoke 是否计入` | 明确基线总数是 **14**；`a068d92` 树测得 13 是因为 smoke 当时已转 skip |

### 13 → 14 的依据（跨轮对账）

第六轮 K3 提到陈旧锁 mtime 为 **2026-09-18**，早于基线 commit `eecf05a`（2026-09-29）。
故 `eecf05a` 上 smoke 即已失败，**基线预存在失败总数为 14，不是 13**。
第七轮实测的「1 failed」正是这第 14 项 —— 两轮审计在此对上。

---

## 本轮未采信的判断（附理由）

审计末尾的「未解取证问题」（09-18 原始锁在 13:00-15:26 之间重新出现在 `reports/`），
本轮不追究：

- `reports/` 未被 git 跟踪，无历史可查
- seal 归档副本 mtime 为 09-24，并非拷贝源
- 时间窗与 supervisor 15:13 慢环重叠属**相关性而非因果**
- 锁已清除、该测试已退役 → **该取证问题的实际影响已归零**

继续追查的期望收益低于其成本。若要追查，需先说明它还关系到什么。

---

## 留给用户的事项

1. **推送**（可选）：本轮修订后共 4 个 commit，均 `ahead`，未推送。
2. **重启 supervisor**：L3 的另一半 —— PID 22703 仍跑 09-28 的内存代码。用户已裁定自行重启。
   - Runbook：`D:\FlyBuddy\.omc\artifacts\sixth-audit-supervisor-restart-runbook.md`
   - 重启后最该核对：
     - `grep -c "v1 legacy: pass by ev>0" task_FM/known_verdicts.inc.md` → 应为 **1**（K6）
     - `grep -c "gate_pass=True" task_FM/known_verdicts.inc.md` → 应为 **43**（M4，此前 20）

---

## 文档索引

| 类型 | 路径 |
|---|---|
| **本 changelog** | `docs/superpowers/changelogs/2026-09-29-seventh-audit-resolution.md` |
| 完整处置报告 | `D:\FlyBuddy\fma-audit\2026-09-29-fma-seventh-audit-resolution.md` |
| 被处置的审计 | `D:\FlyBuddy\fma-audit\2026-09-29-fma-seventh-audit-stage3-impl.md` |
| 第六轮处置报告 | `D:\FlyBuddy\fma-audit\2026-09-29-fma-sixth-audit-resolution.md` |
| 第六轮 changelog | `docs/superpowers/changelogs/2026-09-29-sixth-audit-resolution.md` |
| Stage 3 changelog（本轮修订） | `docs/superpowers/changelogs/2026-09-29-stage3-impl-and-prep.md` |
| 重启 runbook | `D:\FlyBuddy\.omc\artifacts\sixth-audit-supervisor-restart-runbook.md` |
