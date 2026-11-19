# 技术债收口 Spec（2026-11-19 批次）

> **状态**：待宿主审批  
> **创建日期**：2026-11-19  
> **登记册**：`docs/superpowers/plans/tech-debt-register.md`（2026-11-19 重写版，TD-01…TD-20）  
> **实施计划**：`docs/superpowers/plans/2026-11-19-tech-debt-closure-plan.md`  
> **审计来源**：2026-11-19 四路复审（代码静态审计 / docs 时效审计 / 研究路径审计 / 提案资产审计）  
> **执行窗口**：WSL 本机（`/root/timesfm`），无人值守；宿主侧事项只交付执行包，不在本窗口内

---

## 一、问题陈述

2026-11-19 全面复审确认四类债务：

1. **环境不可复现（P0）**：requirements.txt 缺 scipy/sklearn/tqsdk（+测试侧 pytest/jinja2），按清单装完即 ImportError；本机 `.venv` 因此缺失，三环在本机两次拉起失败（2026-10-08/10-13 stop_report）。
2. **闸门与调用图失真（P1）**：死代码闸门存在自引用漏洞（自带 usage 示例的脚本可自证被引用），25 项孤儿脚本未挂账；`data/main_chain.py` 弃用标注与活跃调用矛盾；模型包 import 口径 timesfm/timesfm3 分裂。
3. **卫生债（P2）**：登记册条目滞后（E1 已消解仍挂账）、悬空文档引用、占位指标、重复实现、`.deprecated` 文件滞留等 11 项。
4. **流程/文档债（P3）**：`BACKUP-MERGE-PROTOCOL.md` 拼接损坏、jd 运维注记未并入 runbook、changelog 自述与提交行为矛盾 + 仓库外历史重写未留裁定记录。

另有**宿主侧执行项**（提案资产清洗 v4 执行、三环重启 + followup 验收闭合）：spec/plan 已就绪（`2026-11-19-proposal-asset-cleanup-spec.md` v4），但清洗脚本尚未实现，且执行必须宿主停机窗口——本 spec 只负责把脚本实现出来并交付执行包。

## 二、设计原则

1. **冻结路径红线（loop-constraints 内化）**：本批次不修改 `config/prediction_scheme.py`、`cascade/features.py`、`cascade/daily_model.py`、`cascade/hourly_model.py`、`data/config.py`、`aligned_verdicts.jsonl`（手写）、`.env*`。涉及其中的债务（TD-06 的模型 import、TD-10 的指标权威、TD-14 的 numba）只做登记与人工确认清单，不改码。
2. **裁定先行**：删除/归档运行脚本前必须有宿主对 cron/外部调用面的确认（TD-16 R-6）。无人值守窗口只做：登记、挂账、无依赖的归档、新文件、测试。
3. **闸门持续有效**：孤儿处置以 REVIEW_CANDIDATES 挂账替代直接删除，闸门测试必须全程绿。
4. **单一脚本原则**（沿 asset-cleanup spec v4）：清洗逻辑全部在 `scripts/cleanup_proposal_assets.py`，测试可脱离真实 experiments/ 数据运行（fixture 构造）。
5. **可回滚**：所有修改走 git；文档归档沿用 git mv；requirements/venv 变更不动宿主。
6. **失败上报**：单任务重试 ≤3 次，超限即停并上报（loop-constraints Budget 纪律）。

## 三、范围

### 窗口内（WSL 无人值守）

| Task | 内容 | 对应 TD |
|---|---|---|
| T1 | requirements.txt 依赖契约修复 + 头部注释修正 + pyarrow 核实 | TD-01 |
| T2 | `.venv` 重建（CPU torch）+ 烟测 | TD-02 |
| T3 | 全量测试基线（对照 2026-10-03 的 1557 passed 基准） | TD-02 验收 |
| T4 | 死代码闸门自引用修复 + 新测试 | TD-03 |
| T5 | 孤儿全量挂账 REVIEW_CANDIDATES（不删文件） | TD-04 |
| T6 | 卫生批：scripts/AGENTS.md 悬空引用、`.deprecated` 文件归档 | TD-08 / TD-13 |
| T7 | 文档债批：BACKUP-MERGE-PROTOCOL 恢复重写、jd 注记并入 runbook、README 索引修正 | TD-18 / TD-19 |
| T8 | `cleanup_proposal_assets.py` 实现 + 25 项测试（spec v4 全集） | TD-17.1（实现半） |
| T9 | 宿主执行包 + 裁定请求清单成文 | TD-16 / TD-17 |

### 窗口外（宿主，需裁定/停机）

- 资产清洗执行（P0-P3 对真实 experiments/）+ 三环重启 + followup 验收闭合（TD-17）
- 孤儿归档执行（等 R-6 cron 清单）
- laya 优化线 / v23-retest 台账 / positive-ev P5 / peer-memory D1+D4 / jd-sr max_points（TD-16 R-1…R-5）
- `main_chain.py` 方向裁定（TD-05）
- 模型 import 统一涉及 daily/hourly_model 的部分（TD-06，人工确认）

## 四、硬门禁

1. T2 完成前不得开始 T3/T4/T8 的测试类验收（无解释器依赖）
2. T4/T5 之后 `tests/test_no_dead_code.py` 全绿（新名单下）
3. T8 的 25 项测试全绿，且 `--dry-run` 在无 experiments 目录时安全退出（fixture 化）
4. 每个任务收尾时 `git status` 干净、分批 commit
5. push 前必须告知（loop-constraints Push 纪律）；本 spec 批准时即视为告知授权

## 五、出口条件

| 条件 | 类型 | 验收方式 |
|---|---|---|
| requirements 自洽：按新清单装完可 import 全部活代码第三方 | **硬** | 新 venv 内 import 烟测脚本 |
| 全量测试基线记录且无新增失败 | **硬** | pytest 基线写入 plan 执行日志（与 1557 基准差异清单） |
| 闸门自引用漏洞关闭 | **硬** | `test_gate_catches_self_reference` 绿 |
| 孤儿 25 项全部有名有据地挂账 | **硬** | REVIEW_CANDIDATES 清单 + 闸门绿 |
| 卫生批完成（悬空引用清零 / .deprecated 归档） | **硬** | grep 验证 |
| BACKUP-MERGE-PROTOCOL 恢复且内容与 .gitattributes 机制一致 | **硬** | 人工可读 + 路径表完整 |
| jd 注记并入 runbook、原件归档、引用回填 | **硬** | grep 验证 |
| cleanup 脚本 25 测试全绿 | **硬** | pytest tests/test_cleanup_proposal_assets.py |
| 宿主执行包成文（清洗步骤 + 重启步骤 + 裁定请求 R-1…R-6） | **硬** | 文档存在且被 README 索引 |
| 引用完整性：全仓在用文档 grep 无断链 | **硬** | 复审脚本 |

## 六、回滚

- 全部改动 git 化，单 commit 粒度回滚
- `.venv` 重建失败不影响仓内容（rm -rf .venv 即回滚）
- cleanup 脚本自带 `--rollback <session_id>`（spec v4 §八），但本窗口只交付实现不执行

## 七、测试

- T3 全量基线：`python -m pytest tests/ -q`（排除 archive；记录 pass/fail/skip/xfailed）
- T4：新增 `test_gate_catches_self_reference`
- T8：`tests/test_cleanup_proposal_assets.py` 按 asset-cleanup spec v4 §九 25 项全量实现
- 收尾：引用完整性 grep + `git log` 审阅

## 八、安全约束

1. 不触冻结路径（§二.1 全表）
2. 不删除任何脚本/服务文件（只挂账）
3. 不执行对真实 `task_FM/experiments/` 的任何写操作（本机本无该目录）
4. 不 push 未告知（本 spec 被批准 = 已告知）
5. token 预算纪律沿用 loop-constraints：无界计划的快停快报
