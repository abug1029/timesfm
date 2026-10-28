# C1 诊断报告审阅意见

> **代码基线**: `3d28137`

> **日期**: 2026-10-08
> **被审对象**: `2026-10-08-c1-diagnostic-report.md`（C1 判停诊断报告，未跟踪文件）
> **审阅基线**: HEAD `a2cb889`；spec 对齐点 `c200210`；账本工作区 433 行（staged 回退态，HEAD 版本为 443 行）
> **方法**: 逐项交叉验证 —— git 历史/状态核对、账本 433 行逐行复算（Python 只读脚本）、`cascade/statistical_tests.py` 配对诊断函数走读、字段全集枚举、进程状态实测
> **结论一句话**: 报告的硬事实与核心结论（135 行无法判定、B 不适用、74 行单独一节）**全部核实成立**；但存在 1 处内部自相矛盾（P1，须修）、1 处验证依据写错文件（P2）、1 个紧迫的账本回退风险未闭环（P3，supervisor 恢复时序须先与宿主确认）。

---

## 1. 核实通过项（逐项实测）

| # | 报告声明 | 验证方式 | 结果 |
|---|---|---|---|
| 1 | HEAD `a2cb889`、对齐点 `c200210`、12 个后续提交（`cc02530..a2cb889`） | `git rev-parse` / `git rev-list --count` | ✓ 一致 |
| 2 | 账本 433 行（恢复后） | `wc -l` | ✓ 一致 |
| 3 | 当前指纹 218 行 = set_mismatch_descriptive 209 + no_common_cutoff 9 | 逐行复算 | ✓ 一致 |
| 4 | 74 行两侧为 0 / 135 行两侧 10-90 / 其他桶 0 行 | 逐行复算 | ✓ 一致 |
| 5 | unmatched 分布 13/13×76 + 10/10×38 + 16/16×21 = 135，两侧完全对称 | 逐行复算 | ✓ 一致 |
| 6 | 74 行成因 = `missingness_admissible=False` 提前返回，两侧 unmatched=0 为真实计算值 | `cascade/statistical_tests.py:399` 走读：提前返回发生在 `counts`（含 `dm_unmatched_*`）计算之后 | ✓ 成立 |
| 7 | 「若选 B 这 74 行会变为 ok」 | 代码推演：两侧差集为空 → `tail_ok`/`head_ok` 均为 True → `set_mismatch=False` → `"ok"` | ✓ 代码层面成立 |
| 8 | 90 点上界；头尾连续块才是筛选主判据 | `_MAX_UNMATCHED_DAYS=30 × _POINTS_PER_DAY=3`、`tail_ok`/`head_ok` 逻辑 | ✓ 一致 |
| 9 | 账本不含 cutoff 列表（唯一相关字段 `raw_cutoff_set_hash` 为 64 字符哈希） | 实测 433 行字段全集共 97 个字段，无任何 cutoff/dates 序列字段 | ✓ 成立 |
| 10 | DM 核心代码 c200210..HEAD 无变更，spec 数字有效 | `git diff --stat` 为空：`cascade/statistical_tests.py`、`task_FM/evaluations/fm_eval/evaluator.py`、`scripts/aligned_slow_loop.py`、`scripts/registry_lib.py` | ✓ 成立（但见 P2：报告所述验证文件有误） |
| 11 | 未出现「为通过而改 goal / 放宽门槛」的变更 | `git diff c200210..HEAD -- scripts/praxist_goal.yaml` 为空；`missingness_admissible` 默认参数随 DM 文件无变更证实 | ✓ 成立 |
| 12 | M2/M3 报告存在（`2026-10-08-m2-documentation-alignment.md`、`2026-10-08-m3-pyyaml-verification.md`，均未跟踪） | 文件在位；M3 各 Step 状态 PASSED 齐全 | ✓ 在位（M2 逐条 diff 声明未逐字复核） |

**注**：全部验证为只读操作，未修改任何文件。

## 2. 问题清单

### P1（高，须修）宿主出口条款内部自相矛盾

- 「宿主出口」节：`<A / C>`（B 被阻断不可选），且「默认建议出口 **C**」。
- 「B 路径说明」末尾：「宿主出口仍须选 A 或 C（**当前只能选 A**，因 B 被阻断）」。
- 两处直接冲突：被阻断的是 B 而非 C；「只能选 A」与「默认建议 C」不能并存，疑似模板残留或笔误。
- **处置**：将括号内改为「（A 或 C 可选，B 被阻断）」。宿主批准出口前必须先修正，否则批准动作有歧义。

### P2（中）Step 1 验证依据写错文件

- 报告称 diff 了 `scripts/praxist_supervisor.py` 中含 `dm_unmatched` 的 DM 相关函数——但 **supervisor.py 中不存在 `dm_unmatched` 标识符**（grep 实测零匹配）。
- 该计算实际位于：`cascade/statistical_tests.py:312`（`pair_dir_ok_series_with_diagnostics`）、`task_FM/evaluations/fm_eval/evaluator.py`、`scripts/aligned_slow_loop.py`、`scripts/registry_lib.py`。
- 结论碰巧成立（上述 4 文件 diff 全为空），但按报告所述路径（仅 supervisor.py）**无法复现**「dm_unmatched 无变更」的声明。
- **处置**：Step 1 补记实际核对的文件清单（4 文件 + goal yaml），防止日后复核者走错路径。

### P3（中，紧迫）账本回退风险未闭环

- 事实链：HEAD 账本 = **443 行**（c200210..HEAD 间 10 条已提交裁决）；工作区被 `git checkout c200210 --` 回退至 **433 行**（staged）。
- 报告未记录：(a) 恢复前工作区实际行数（是否存在未提交追加行被覆盖）；(b) 「与工作区未提交改动隔离」的具体操作（备份/stash 均未写明）。
- **紧迫点**：审阅时点实测 WSL 存在 2026-10-08 21:16 启动的「等待 supervisor 恢复」循环（30 分钟窗口）。supervisor 一旦在账本仍为 433 行回退态时被拉起并追加，新行将直接接在 433 行之后——已提交的第 434-443 行在工作区消失，账本出现 **10 行时间线空洞**，后续任何 `git add + commit` 都会呈现「删 10 行 + 追加 N 行」的 diff，实质破坏 append-only 契约。
- **处置**（时序约束）：
  1. 恢复 supervisor 之前，先 `git checkout HEAD -- task_FM/config/aligned_verdicts.jsonl` 回到 443 行完整态；
  2. 诊断用的 433 行口径如需保留，改用只读副本（如 `cp` 至 `/tmp`）实现，不再回退工作区文件本身；
  3. 在原报告补记恢复前行数与隔离方式；若已发生覆盖丢失，从 git 历史恢复。

### P4（低）`n_eff: 73` 与 `d_series_n_eff: 588` 并存未解释

- 74 行一节同时引用两字段（8 倍差异），未说明 `n_eff` 的计算口径（来自 evaluator 侧，与 DM 配对的 `d_series_n_eff=len(d)` 不同源）。
- **处置**：补一句口径来源说明，或删去 `n_eff` 引用，避免读者误当作 DM 样本量。

### P5（低）字段搜索关键词未覆盖 `dates`

- Step 3 自述搜索「包含 cutoff/point_seq/time 的字段」，该关键词集不含 `dates`——而代码 B 路径（`missingness_admissible=True`）确会输出 `unmatched_variant_dates` / `unmatched_baseline_dates`。
- 实测 433 行全部走提前返回路径，无 dates 类字段落账本，**结论不受影响**；但「关键词过滤」方法本身留有死角。
- **处置**：把实测字段全集（97 字段清单）列为附录证据，使「账本不含 cutoff 列表」不可辩驳。

### P6（信息）对称性信号可作为日后先验

- 附录已观察 unmatched 两侧完全对称（variant=baseline）且取值离散（仅 10/13/16 三值）。该模式与「端块/窗口边界截断」假设相容，与「随机窗内缺口」（取值应更连续分布）不太相容。
- 报告正确地未据此下结论（维持「无法判定」）；建议将此观察作为「日后补入口重评 B」时的先验记入附录。

### P7（信息）`raw_cutoff_set_hash` 的正向验证价值

- 报告只写了「哈希不可反推」，未提**正向验证**路径：日后补只读重算入口后，重建 cutoff union 集合并做 SHA-256，与账本 `raw_cutoff_set_hash` 比对，即可零成本校验重算正确性。
- **处置**：写入 B 路径重启（补入口立项）的注意事项。

## 3. 对宿主出口决策的输入

1. 分类结论「B 不适用：无法判定」的证据链经独立复核完整成立，**可提交宿主批准**。
2. 批准前置条件：P1 出口歧义修正（明确「A 或 C 可选，默认建议 C」）。
3. 时序约束：P3 处置第 1、2 步（账本回到 443 行完整态 / 诊断口径改用副本）完成之前，**不要恢复 supervisor**。
4. 出口建议：维持原报告默认建议 **C**（理由与分类结论一致：无法判定）；宿主若取保守默认可选 A。审阅意见不改变 A/C 之间的选择权归属。

## 4. 审阅边界声明

- 本审阅全部为只读操作；未修改账本、代码与原报告。
- M2 报告的逐条文档 diff 声明未逐字复核（仅确认文件在位与 M3 各 Step PASSED）。
- 审阅时点账本工作区为 433 行 staged 回退态（P3 所述风险正是在该状态下成立）；本文件落档后如 supervisor 已恢复并追加，行数以实际为准，P3 处置第 3 条仍然适用。
