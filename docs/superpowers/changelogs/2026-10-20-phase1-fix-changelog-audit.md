# Phase1 返工 Changelog 代码审计报告

| 项 | 内容 |
|---|---|
| 日期 | 2026-10-20（Asia/Shanghai） |
| 对象 changelog | `docs/superpowers/changelogs/2026-10-20-phase1-fix-changelog.md` |
| 对照计划 | `docs/superpowers/plans/2026-10-20-phase1-variant-registration-fix-plan.md` |
| 对照 SPEC | `docs/superpowers/specs/2026-10-19-proposals-evaluation-optimization-spec.md` v3.1 §5.1 |
| 仓路径 | `/home/abug/timesfm` |
| 审核状态 | **有条件通过** |
| 完成度 | **~58%**（相对修复计划 DoD / 放行 4 条件） |
| 能否宣称「Phase1 返工完成」 | **否**（相对 fix plan DoD）；相对本 fix-changelog 自述的 Pre-harvest 方案则「引擎层部分落地、文档与 C1 未闭合」 |

---

## §1 一句话结论

返工在 **M1 锁内重读幂等**、**M2/M3 净化+backfill 脚本与生产 registry 去 `run_T`**、**harvest 前 prune 钩子** 上有实证；但 **未关闭 fix plan 的 C1（peer 写盘前钩子）**，changelog 将「先写后删」称为与 SPEC §5.1「不落盘」**效果等价不成立**，测试清单文件名/条数与实测不符，且 **缺写盘钩子集成测**——**不得宣称相对修复计划的 Phase1 返工已完成**。

---

## §2 Changelog 声称 vs 代码实证

| # | Changelog 声称 | 实证 | 判定 |
|---|----------------|------|------|
| M1-a | `register()` 幂等 | `variant_registry.py`：锁内 `_reload_from_disk_unlocked()`，已存在则 return，不 append | ✅ |
| M1-b | 新增 `try_register` | 同文件：锁内 reload → 无则 append → True/False | ✅ |
| M1-c | 跨实例同 stem 单行 | 临时目录 4 线程复现：`true_count=1, lines=1`；单测 `test_cross_instance_same_stem_single_line` | ✅ |
| M1-d | `test_variant_registry`「7」个含幂等 | 实测该文件 **10** 个 `test_*`（含并发同 stem / load 去重）；套件合计见 §5 | ⚠️ 条数虚报 |
| M2-a | 新增 `scripts/backfill_variant_registry.py` | 文件存在；`--dry-run`/`--execute` 互斥；stem=`Path.stem` 与 harvest/prune 一致 | ✅ |
| M2-b | 扫描 ~796 唯一 stem 回填 | 脚本逻辑正确；**当前** live `run_*/results/**/proposals` = **0** 文件，无法复验「796」当日快照。现网 registry **1318** 唯一 stem（见 §6） | ⚠️ 历史数字不可复验；现网已大于 796 |
| M3-a | `_prune_duplicate_proposals` + `sup_loops` harvest 前调用 | `sup_harvest.py:42+`；`sup_loops.py` `_harvest_rows` 内 `n_pruned = ..._prune...` 后才 `harvest_proposals` | ✅ |
| M3-b | 已注册则 **删文件** | `try_register` False → `os.remove(sp)` | ✅（语义危险见 §4） |
| M3-c | harvest **不再需要**检查 registry | `harvest_proposals` 循环内 **无** `has_stem`/`register`（仅注释）；与 changelog 一致。钩点探查文仍写「708 行 has_stem 安全网」→ **文档过时** | ✅ 代码 / ⚠️ 探查文 |
| SPEC差 | 承认非写盘前；称效果等价 | 差异原因（praxist）有探查文支撑；**「效果等价」对磁盘生命周期不成立**（先写后删 ≠ 不写） | ⚠️/❌ 等价论 |
| 测试 | `test_pre_harvest_cleanup.py` 4 + 共 54 全过 | **不存在**该文件名；实为 `tests/test_prune_duplicate.py`（**5** 测）。实测 `pytest`：**58 passed**（10+5+4+39） | ❌ 清单错误 / ✅ 相关测全绿 |
| 交付物 | 五件套 | `variant_registry`/`backfill`/`sup_harvest`/`sup_loops`/`test_prune_duplicate` 均在；缺宣称的 `test_pre_harvest_cleanup.py` | ⚠️ |
| 状态 | 「完成，所有测试通过」 | 测试子集全绿，但相对 DoD **未完成** | ❌ 状态夸大 |
| Laya | （硬约束：不训练） | fix commit `3515959` 仅 7 文件 scripts/tests，**无** Laya/train/weight | ✅ |

---

## §3 vs 修复计划 T1–T5 / SPEC §5.1 / 放行条件

| 项 | 计划要求 | 返工实际 | 判定 |
|----|----------|----------|------|
| T1 C1 | peer/生成 **写盘前** 挂 Registry；同 stem **不产生第二文件** | 采用 Pre-harvest Cleanup；探查文确认写盘在 praxist `findings_ingest.py`，**本仓未改 praxist**。计划原文：「未挂上前不算 C1 关闭」 | ❌ C1 未关 |
| T1.4 | harvest 方案 A/B；勿在「解析后立刻 register」导致拒稿终身不入队 | 方案 A 方向：harvest **不再** register；但 **prune 在收割成功前就 try_register 占位** → 拒稿 stem 仍终身占用 | ⚠️ 半到位 |
| T2 M1 | 锁内 reload；并发唯一行；load 唯一 stem 数 | 已实现；并发复现通过；`load` 返回 `len(self._stems)` | ✅ |
| T3 M2/M3 | 测例隔离生产路径；净化 `run_T`；backfill；备份入 changelog | 测例 monkeypatch path；生产 backup=`variant_registry.jsonl.backup_20261020`（21 行含 20×`run_T`）→ 现网 1318/0×`run_T`；**fix-changelog 未写备份路径** | ✅ 实质 / ⚠️ 文档 |
| T4 M4 | 旧 changelog 取消虚假「不落盘已完成」 | 诊断 changelog 已改为「有条件完成 / Pre-harvest」；仍勾选「重复 stem 在 harvest 前被删除」且宣称效果等价 | ⚠️ 改善但仍偏满 |
| T5 | 跨实例并发 + **写盘钩子集成**（第二次无第二文件） | 有并发单测；**无**「生成写盘路径第二次不落盘」集成测（仅有 prune 删已落盘文件测） | ❌ 放行#4 不全 |
| SPEC §5.1 | 「peer 生成后、写盘前查询；已存在则跳过写盘」 | 未满足字面；第二道 harvest 去重仍在（`_reject("dedup")`） | ❌ 字面未对齐 |
| DoD#1–4 | 四条全满足才可重审 Task1 | #1 C1 ❌；#2 M4 部分；#3 M1+净化 ✅ 偏；#4 测试不全 ❌ | **DoD 未满足** |

推荐执行顺序 T2→T3→T1→T5→T4：代码侧近似按此做了 T2/T3/「T1 替代」/部分 T5，但 **真正 T1 与 T5 写盘集成未做**。

---

## §4 逻辑与风险清单

### P0
1. **C1 仍未关闭，却以「完成」表述返工** — 相对 fix plan / SPEC，主目标「写盘前不落盘」未达成；仅事后删除。对外宣称「Phase1 返工完成」会造成与上次同类的虚假验收。
2. **「效果等价」表述错误（产品语义）** — 磁盘上重复文件仍由 praxist 写出，占用 IO/空间直至下一轮 harvest；在 harvest 周期之间冗余可再次堆积。与 SPEC P0「禁止落盘重复」不等价。

### P1
1. **`try_register` 发生在成功入队 / 质量门之前** — 首次扫到的文件即使随后被 schema/质量/dedup 拒绝，stem 已占位；同 stem 更优提案会被 prune **直接删文件**，无法再入队（对齐修复计划「终身跳过」担忧；T1.4 未按推荐钉死）。
2. **glob 顺序决定「幸存者」** — 同 stem 多文件时保留先扫到的，未必是「最新」或「质量最好」（Task2 归档语义若期望最新版，此处未保证）。
3. **live 提案现为 0** — harvest 可扫路径下无 `proposals/*.json`；`_corrupted_backups` 下 42 个不参与 prune/harvest 模式。无法复验「保留 796 唯一」盘态；archive 仍 6593 文件 / 383 unique（归档堆冗余 94.2%，预期内但说明「全库唯一 796」与现 archive 不完全同集）。
4. **Changelog 测试清单错误** — 错名 `test_pre_harvest_cleanup.py`、少计 `test_variant_registry`、总 54≠58，削弱可审计性。
5. **backfill `--execute` 批量 append 不经 `try_register` 锁内逐条去重** — 并发双执行可能重复行；`load` 会去重计数，但 JSONL 可能多行（现网 `dup_stems=0`，当前健康）。

### P2
1. 钩点探查文仍写 harvest `has_stem` 安全网，与代码不一致。
2. 无 `VARIANT_REGISTRY_ENFORCE` feature flag（计划回滚项未做）。
3. fix-changelog 未记录 registry 备份路径（备份文件实际存在）。

---

## §5 测试实证

命令（仓内 `.venv`，只读生产 registry）：

```text
.venv/bin/python -m pytest tests/test_variant_registry.py \
  tests/test_prune_duplicate.py \
  tests/test_harvest_status_integration.py \
  tests/test_harvest_proposals.py -q --tb=line
```

| 文件 | Changelog | 实测 `test_*` 数 | 结果 |
|------|-----------|-----------------|------|
| test_variant_registry.py | 7 | **10** | pass |
| test_harvest_proposals.py | 39 | 39 | pass |
| test_harvest_status_integration.py | 4 | 4 | pass |
| test_pre_harvest_cleanup.py | 4 | **文件不存在** | — |
| test_prune_duplicate.py | （未列） | **5** | pass |
| **合计** | **54** | **58** | **58 passed in 26.22s** |

额外：临时目录 4 线程同 stem `try_register` → JSONL 1 行（与 T5 并发项一致）。

**缺失**：写盘路径「第二次不产生文件」集成测（T5 / 放行#4）。

---

## §6 生产 registry / 磁盘状态快照（只读）

| 指标 | 值 |
|------|-----|
| `data/cache/variant_registry.jsonl` | 1318 行 / **1318** 唯一 stem / 坏行 0 / 重复 stem 行 0 |
| `run_T` 行数 | **0** |
| 备份 `variant_registry.jsonl.backup_20261020` | 21 行 / 21 唯一 / **20× run_T**（净化前快照） |
| live `experiments/run_*/results/**/proposals/*.json` | **0** 文件 / 0 unique |
| 非 archive 其它提案（均在 `_corrupted_backups`） | 42 文件 |
| `experiments/archive/**/proposals/*.json` | 6593 文件 / 383 unique / 冗余约 94.2% |
| changelog「问题段仍写 89.2%」 | 指初始问题基线；Task2 曾称 live 0%——**当前 live 空，无法用新 live 冗余率替换** |

---

## §7 结论与放行建议

1. **审核状态：有条件通过（~58%）** — M1 与 registry 净化/backfill 工具链可合并保留；Pre-harvest prune 可作为 **过渡第二道**，但 **不能** 替代 SPEC §5.1 / fix plan C1。
2. **不得宣称「Phase1 返工（相对修复计划 DoD）已完成」。** 建议状态改为：「M1/M2/M3 引擎落地；C1 因 praxist 未挂写盘前钩子 → 仍 CONDITIONAL；待外仓 PR 或等价写前拦截 + 写盘集成测」。
3. **放行建议**
   - **可接受合并/保留**：幂等 registry、`try_register`、backfill 脚本、prune 作为加速清理（需改文档口径）。
   - **阻塞「关闭 C1 / 全量放行」**：praxist 写前钩或本仓可证的「第二文件不落盘」；修正终身占位语义（仅成功入队或写成功后 register，或允许质量门后覆盖策略）；修正两份 changelog 测试清单与「效果等价」措辞；补 T5 写盘集成测。
4. **硬约束**：本次返工 **未触及 Laya 训练**（commit `3515959` 文件列表已核）。

---

*审计执行：New Bot 执行子代理；本机 machineId `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`；未 commit/push/删生产数据；未释锁。*
