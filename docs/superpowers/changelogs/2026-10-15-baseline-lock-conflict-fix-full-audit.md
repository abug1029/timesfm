# 审核：2026-10-15 基线锁冲突修复 - 完整实施记录

- 对象：`/home/abug/timesfm/docs/superpowers/changelogs/2026-10-15-baseline-lock-conflict-fix-full.md`（mtime **2026-10-15 20:48 CST**；3328B）
- 对照代码（WSL SSOT）：`/home/abug/timesfm` — `scripts/lock_utils.py`、`incremental_baseline.py`、`sup_evidence.py`、`generate_baseline_points.py`、`check_baseline_coverage.py`、`tests/test_lock_utils.py`、`tests/test_regen_cooldown.py`
- 对照规范/计划：`D:\FlyBuddy\docs\fm-baseline-lock-fix-spec.md`（v1.2-final）、`fm-baseline-lock-fix-implementation-plan.md`（v2，第三遍 audit **有条件通过**）
- 对照 git：`master` @ `bff45e2`；功能合并为 **`299c764`**（非文中 858e2a5）
- Box 镜像：`/workspace/shared/reviews/2026-10-15-baseline-lock-conflict-fix-full-audit.md`
- 审核时间：2026-10-15 20:57 CST

## 1. 结论

**有条件通过。**  
代码主干（SymbolLock 供 incremental、metrics `result→summarize+vid`、breaker 内存表 str→dict、冷却 2h / 频率 24h、阈值 336h、10 测可复现）**属实且对齐计划残留门槛 B2/B3**。但记录把「计划有条件通过 + Phase 1.3 未做 + 覆盖度定义偏离 SPEC」写成「全部专家评审通过 / 统一锁 / 可部署」，**审批与完整性口径偏夸**；合并 hash 写错。修订文档后再当验收基线更稳。

## 2. 声称 vs 实况

| # | 实施记录声称 | 实况 | 判定 |
|---|-------------|------|------|
| 1 | Phase 0–4 完成；7 文件；**603+/82-** | merge `299c764` 七文件 numstat **603/82** | **属实** |
| 2 | `lock_utils.py` 新建 62 行；`SymbolLock`；路径 `task_FM/config/.{sym}.lock` | 62 行；fcntl LOCK_NB 轮询；超时 RuntimeError「锁冲突」 | **属实** |
| 3 | incremental 加锁 + metrics 同步 | `with SymbolLock`；`_update_baseline_metrics(..., result=)`；`mb.summarize` + `vid=compute_protocol_fingerprint()`；`.metrics.lock`；jsonl 降级不写 mape | **属实**（B2 已落地） |
| 4 | **统一锁机制** | incremental 用 SymbolLock；**gbp 仍内联 fcntl，从未出现在本分支 diff**（计划 Phase 1.3 / 验收「gbp 迁移到 SymbolLock」未做） | **偏夸**（路径同构可互斥，代码未统一） |
| 5 | Phase 2：冷却 2h + 频率 24h + breaker 扩展 | `_STALL_COOLDOWN_HOURS=2`、`_FREQUENCY_LIMIT_HOURS=24`；`_RECENTLY_REGENED_NO_ADVANCE: dict[str,dict]`；**`_load_regen_breaker(root)` / `_save_regen_breaker(root)` 签名保持**；`_stall_still_blocks` 读 dict-or-str；ensure 在 stall 后查 cooldown/frequency | **属实**（B3 嫁接正确） |
| 6 | 阈值 168→336；覆盖度 **88.9%（24/27）** | 常量 336；脚本现跑 24/27、uncovered pp/bz/eb | **数字属实**；见下「定义偏离」 |
| 7 | 覆盖度工具 | `check_baseline_coverage.py` 53 行；**实际判据仅为 metrics `n>0`**；docstring/SPEC ADR-7 要求「确认窗 cutoff 且基线末端 ≥ cutoff」；SPEC 门闩覆盖度 **>95%** | **半属实**（工具有、定义弱、未达 SPEC 阈值） |
| 8 | 测试 10 全过（6.49s） | 5 lock + 5 cooldown；`PYTHONPATH=scripts:. .venv/bin/pytest …` → **10 passed**（本机约 13s）；裸 `.venv/bin/pytest` 下 cooldown 因 `import registry_lib` **5 fail** | **有条件属实**（缺环境说明） |
| 9 | Phase 4：并发 A 持锁→B 等→A 释→B 得；无残留 | `test_symbol_lock_concurrent/timeout` 只断言 **B 在 A 持锁时失败**；**无**「释放后 B 成功获取」断言；cleanup/exception 测有 | **偏夸** |
| 10 | fg/cj jsonl **588**；metrics n=588、vid=f02b2a43… | `baseline_points_{fg,cj}_nocov.jsonl` 各 588；metrics 五键齐全、同 vid 前缀 | **属实** |
| 11 | 合并 master commit **858e2a5** | **合并是 `299c764`**；`858e2a5` 仅为短 CHANGELOG 文档提交；其后还有 `bff45e2` 本完整记录 | **错误** |
| 12 | 审批：**全部专家评审通过**；各 Phase「专家评审 ✅」 | 仓内 **无** 本批 `docs/superpowers/reviews/*baseline-lock*`；FlyBuddy plan audit 为 **有条件通过**；「专家」无独立产物可核 | **过称** |
| 13 | 文件表 incremental **+154/-76** | Phase1 numstat **+160/-76**（merge 侧展示 236 为变更合计口径） | **数字不准** |
| 14 | Phase 5 可部署；待授权 push/重启 | 已在 master；未宣称已 push；与「待授权」一致 | **属实**（部署未做） |

## 3. 与计划残留门槛对照

| 计划第三遍残留 | 代码落地 | 记录是否诚实写出 |
|----------------|----------|------------------|
| B2 result→summarize+vid | ✅ | 未细写，但 metrics 同步条目可覆盖 |
| B3 保持 `_load/_save_regen_breaker(root)`；表 str→dict；stall 读 data_end | ✅ | 未写签名，结论正确 |
| M4 Phase1.5 gbp `--cov none` | gbp 本批未改；CLI 仍 `required=True` | 记录未涉及 1.5 命令 |
| Phase 1.3 gbp→SymbolLock | ❌ 未做 | 写成「统一锁」掩盖缺口 |

## 4. 跨文档一致性

| 点 | 完整记录 | 短 CHANGELOG | Phase4 报告 |
|----|----------|--------------|-------------|
| 10 tests / 6.49s | ✅ | ✅ | ✅（却挂在「冷却」节下列 5 名） |
| 合并 hash | 错写 858e2a5 | 未写合并 | 写「下一步合并」（报告生成时尚未合） |
| 专家全过 | 强宣称 | 无 | 「状态通过」无专家字样 |
| gbp 迁移 | 暗示统一 | Phase1 一句话 | 无 |
| 覆盖度 88.9% | ✅ | 有工具无数字 | ✅ |

## 5. 风险与建议

### Blocker（文档 / 验收口径）

1. **勿写「全部专家评审通过」**：改为「计划有条件通过后实施；代码侧 Phase0–4 已合入 master@299c764」；或附真实 review 路径。
2. **明示 Phase 1.3 未做**：gbp 仍双份锁实现；互斥靠同路径 flock，非 SymbolLock 单源。补迁移或降级「统一」措辞为「incremental 接入 SymbolLock，与 gbp 锁路径兼容」。
3. **覆盖度**：按 SPEC 重写测量（cutoff 窗）或改 SPEC/ADR；当前 88.9% **不可**当作「>95% 门闩已过」。

### P1

4. 修正合并 hash → `299c764`；incremental 行数 → +160/-76。
5. 测试文档补 `PYTHONPATH=scripts:.`（或改 import / conftest）；**测试禁止用 root=`.'` 写 live `baseline_regen_breaker.json`**（本审核复跑已使 cache 仅剩 `test_freq` 键——需运维恢复 breaker，测试改 tempfile）。
6. 并发验收补「释放后第二进程可获取」或改写 Phase4 叙事，避免过度描述。

### P2

7. 标题/状态与短 CHANGELOG 对齐「可部署（待 push/重启授权）」。
8. gbp 与 SymbolLock 行为差（错误文案、删锁文件时机）可后续一轮统一。

## 6. 结论摘要

**有条件通过。** 实现核心与 B2/B3 对齐，10 测在正确 PYTHONPATH 下可过，fg/cj 灰度数据属实；但 **专家全过、统一锁、覆盖度定义/阈值、合并 hash** 四类口径问题须改文档（并恢复被测污的 breaker）后再当正式验收记录。
