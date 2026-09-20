# CHANGELOG — 预测质量重构合入 master（2026-09-16）

- **仓库**: WSL `/home/abug/timesfm` → GitHub `abug1029/timesfm`
- **合并方式**: fast-forward `e22db35..4ab3102`（无冲突，master 自 merge-base 无分叉）
- **规模**: 56 文件，+7032/-451
- **同步验证**: master == feat/prediction-quality-redesign-v23 == origin/master == `4ab3102`；三向 0 差；工作区全净

## 合入内容（6 个收尾 commit）

| Commit | 内容 | 审核 |
|--------|------|------|
| `c7c8255` | Task 1: D 系列缺陷修复（自适应门接入慢环、DirAcc 别名、6 族词表对齐、慢环去经济秤、wait_for_batch 单扫、fail-hard） | ✅ 审核通过（93 passed，5 项残留已修） |
| `908484e` | Task 13: 契约与 Peer 文案切 DirAcc + BH-FDR（task.yaml/校验器/goal 标量/8 个 peer 文件/known_verdicts 生成器） | ✅ 审核通过（65 passed + validate exit 0，4 项已修） |
| `c5c578a` | Task 14: v1→v2 离线迁移脚本（原子写、行数守恒、STEP=24 语义、墓碑形态 failed 行） | ✅ 审核通过（40 passed，M1-M3+L4-L7 已修） |
| `44da5a3` | Task 15: 端到端夹具测试（baseline→DM→registry→FDR→snapshot→goal 五链路） | ✅ 审核通过（196 passed 复算） |
| `946a4ea` | e2e BH 注释修正（审核 M1） | — |
| `4ab3102` | 仓库卫生：1409 行完整 v23 规格落库、9 份审核报告归档、.gitignore、删 10 个 .bak | — |

## 测试终态

15 文件套件 `-m "not slow"`: **199 passed, 1 deselected, 2 xfailed**（120s）

## 运维备忘

1. ~~**生产 supervisor 未重启**——重启后才加载新代码；重启前建议按迁移 SOP 处理旧 registry~~
   ✅ **已执行（2026-09-16 21:58）**：无生产进程确认 → `aligned_verdicts.jsonl.bak_v1` 备份（9 行 v1）→
   `migrate_verdicts_v1_to_v2.py` 迁移（9 进 9 出，ok 9 / failed 0）→ 11 项完整性检验全通过
   （行数守恒、全 v2 schema、status=ok、validate_verdict 零错误、12 项核心指标齐全、
   30 活跃协变量池 6 族词表、逐行协变量→族→gate 重判一致、pass_variants=3 条、
   min_pass_variant_dir_acc=0.531、备份完好 v1、行序与 variant_id 保持）。
   **迁移后 pass_variants**: p_calendar_cyclical(0.563) / p_oi(0.568) / cf_rsi6(0.531)。
   supervisor 现可随时重启加载新代码
2. **基线生成**：首次运行 `ensure_baselines` 会为 8 个目标品种生成 baseline（ccl 协变量，真实模型加载），冷启动耗时较长
3. **安全**: remote URL 中的明文 GitHub PAT 已移除（改走 Windows GCM 凭据管理器）；
   ⚠️ **该 PAT 曾内嵌 URL 且出现在会话记录中，强烈建议到 GitHub Settings → Developer settings 吊销轮换**
4. Windows 侧 `D:\FlyBuddy\timesfm` 按用户决策保持不动（WSL + GitHub 为唯一权威源）

**执行**: 双专家审核工作流（executor 实施 → code-reviewer 审核 → 修复 → commit），全程 WSL 内操作
