# S1 Supervisor Split Spec 审核（对照本机 WSL 代码）

- 审核对象：`/home/abug/timesfm/docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md`（v3.1）
- 代码根：`/home/abug/timesfm`（DESKTOP-QO0RA3V / WSL Ubuntu-22.04）
- 日期：2026-10-11
- 结论：**有条件通过**——架构与附录 A 与现状高度一致，可进入实施；但须先修正若干计量误差与一处工作量低估，再开步骤 0。

## 已核验（与本机代码一致）

| 声明 | 实测 |
|------|------|
| `praxist_supervisor.py` 4574 行 | 4574 |
| 顶层函数 150 / 嵌套 10 / 模块赋值 57 / 导入别名 9 | 全部一致；别名名单亦一致 |
| `family_for` 嵌套于 `_maybe_enqueue_confirmations:522` | 是 |
| `is_valid_tier` 嵌套于 `build_snapshot:1150` | 是 |
| 关键行号（`_is_confirmable_failure:1859`、`_load_evaluator:1790`、`_verdict_sort_key:2151`、`collect_proposed_variant_ids:1320`、`_merge_save:3247`、`_ensure_tokens_baseline:3104`） | 一致 |
| 引用 `praxist_supervisor` 的测试文件数 32 | 32（名单与常见主测文件吻合） |
| `tests/test_supervisor.py` 1873 行 | 1873 |
| `VALID_TIER_VALUES = frozenset({"S","A","B","C","D"})` | 一致 |
| 文件头 `sys.path.insert(0, HERE)` | 存在 → 同级 `from sup_paths import ...` 可行 |
| `diagnose_three_loop.sh` 含 `maintenance.flag` | 是 → §5.1 协议有落点 |
| 附录 A.5 模块函数/赋值合计 150 / 57 | 加总正确 |

## 必须修正的计量误差

1. **公开顶层函数：声明 32，实测 34**（private 116，非 118）。多出的 2 个非 `_` 顶层函数也在当前文件中。§1.1、§6「32 个 public」、成功标准里的 hasattr 清单须改为 **34**，或以 `__all__` 精确定义“对外公开面”，二者写清并统一。
2. **`monkeypatch.setattr(<alias>, …)`：声明 238，实测 357**（仅统计对 `praxist_supervisor` 的 `as` 别名；其中 `test_supervisor.py` 独占 143）。§4.1/§4.2/§9 的「238+7」须改为 **357+7**，工时 120 min 明显偏低，建议按 ~357 处重估（约 1.5–2×）。
3. **`test_supervisor.py` 中 `sup.` 出现次数：声明 155，实测 157**（次要，建议顺手改）。
4. **import 别名文件数：`as sup` 声明 14，实测 13**；`S`/`sv`/`s` 与声明一致。§4.2 表改正即可。

## 设计评价（可保留）

- **向后兼容 shim + 按职责拆分 + 可逐步 revert**：适合高风险核心运行时。
- **N1/环 E/F 消解与附录 A 权威映射**：比只靠 §2.4 import 清单靠谱；§4.2 要求 AST 跟踪别名、禁止裸正则，方向正确。
- **步骤 0 提升 `is_valid_tier` 并参数化 `log`**：与实测闭包行为一致；明确「不要照抄旧 sketch 的 isinstance」是对的。
- **指纹纪律（§10）+ 迁移窗口（§5.1）**：生产安全必要项，建议实施 checklist 强制勾选。
- **可变全局（`_SHUTDOWN_REQUESTED` 等）**：文档已承认 shim 赋值无法穿透；实施时须保证生产路径一律从 `sup_lifecycle`（等归属模块）读写，测试按 §4.2 改 patch 目标。

## 实施前建议（非 blocker，但强烈建议）

1. 用附录 A 再跑一遍机械校验脚本：顶层名集合、行号、目标模块计数 vs A.5，CI 或实施 PR 的第一步产物。
2. Patch 迁移脚本先在 dry-run 打印「357 处目标模块分布」，人工抽查 `time`/`subprocess`/`rl`/`evaluate_goal`/`__file__` 特判。
3. `sup_evidence` ~700 行顶满成功标准：实施后若超标，优先再抽「基线重生簇」或「死亡族」子模块，而不是先动 loops。
4. `_fam_report_scope` 标注死导入可丢弃——丢弃前用 AST 确认零引用，并更新 `test_no_dead_code` 白名单。
5. 每步 commit 信息固定前缀 `S1-stepN:`，方便 §7 区间 revert。

## 总评

v3.1 已是可执行的拆分 SPEC：结构、依赖 DAG、兼容与测试迁移主线都站得住，且与本机当前 `praxist_supervisor.py` AST 现状对齐良好。  
**不要按文档里的 238 处 patch / 32 public 开干**——先改计量与工时，再进步骤 0；修正后可批准实施。
