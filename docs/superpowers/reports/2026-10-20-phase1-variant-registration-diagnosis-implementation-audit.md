# Phase 1 实施审核：写盘前 variant 登记 + 磁盘归档 + 低效诊断

**日期**: 2026-10-20（Asia/Shanghai）  
**审核对象**: `changelogs/2026-10-20-phase1-variant-registration-diagnosis-changelog.md` + 声称源码/测试  
**对照**: SPEC v3.1 `specs/2026-10-19-proposals-evaluation-optimization-spec.md`（三审通过）  
**硬约束**: Laya 只是判断模型、无法学习  
**machineId**: `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`  
**审核状态**: **有条件通过**（完成度约 **72%**）

---

## §1 一句话

Task 2 归档与 Task 3 诊断大体落地且数字可复现；**Task 1 把「写盘前登记」错挂到 harvest 扫描侧**，验收「重复 stem 不落盘」不成立，生产 `variant_registry.jsonl` 仅 21 条测试污染、未覆盖 796 唯一 stem——须补 peer 写盘钩子并回填/净化 registry 后再宣称 Phase 1 完成。

---

## §2 Changelog 声称 vs 代码实证（逐项）

| 声称 | 实证 | 判定 |
|------|------|------|
| 新增 `scripts/variant_registry.py`（JSONL + flock 幂等） | 文件存在；JSONL 字段 `stem/first_seen/run_id` 正确；同实例幂等 OK | ✅ 组件在 |
| 修改 `sup_paths.VARIANT_REGISTRY_PATH` | `data/cache/variant_registry.jsonl` 已定义 | ✅ |
| 「写盘前」登记；重复 stem **不落盘** | **仅** `sup_harvest.harvest_proposals` 扫描循环：`has_stem → continue`；全仓无 peer 写盘钩子；`VariantRegistry` 引用仅 harvest/paths/registry 三处 | ❌ **P0** 与 SPEC/计划/验收文案不符 |
| harvest 启动加载 + `registry_hit` + 解析后 `register` | 代码在 `sup_harvest.py` ~584–677 行存在；`_reject("dedup")` 仍保留 | ✅ 钩在 harvest（但挂错层） |
| 第一次 harvest 注册 796；后续跳过重复 | 生产 registry：**21 stems**，且多为 `run_T` 测试桩；live 796 中 **780 不在 registry** | ❌ 生产未生效 |
| 跨实例并发安全 / 幂等 | 复现：4 线程同 stem → **JSONL 写出 4 行**（锁内未重读文件，只查本实例 `_stems`） | ❌ **P1** 竞态 |
| Task 2：归档 6593、保留 796、冗余 0%、prescreen 不动 | live 提案 **796/796/0%**；manifest **6593**；archive run 子目录 ~206 | ✅ |
| Task 2 脚本 dry-run/execute/rollback | 三种模式存在；默认 dry-run；manifest 防重复执行 | ✅（小 P2：argparse `--dry-run default=True` 怪异但行为可用） |
| Task 3：eg/stddev/ccl 诊断 + 小样本仅观察 | `diagnose_low_efficiency.py` + 报告存在；复算 eg 47/1=2.1%、stddev 17/2、ccl 31/5，与 changelog 一致；ma/fu/px/jm 标小样本 | ✅ |
| 未训练/微调 Laya | changelog/报告「禁止事项」表述正确；代码无 Laya 权重更新 | ✅ |
| 未重做队列去重 | `seen_vids` + `_reject("dedup")` 仍在 | ✅ |
| 测试 7+39+4+8=58 全过 | `.venv`：`test_variant_registry` 7 + `test_archive` 8 + harvest 39+4 = **58 passed** | ✅ |
| Code review PASS / 无 BLOCK | 无法复核外部 reviewer；本审核另见 P0/P1 | ⚠️ 以本审核为准 |

---

## §3 vs SPEC Phase 1 对齐

| SPEC / 计划要求 | 实施 | 对齐 |
|-----------------|------|------|
| §5.1 **钩子在生成写盘，非 harvest**；harvest 仅第二道防线 | 只改了 harvest；IMPLEMENTATION.md 也自承「harvest 扫描前跳过」 | ❌ P0 |
| 计划验收：「peer 写盘前检查」「重复 stem 不落盘」「不修改 harvest 核心逻辑」 | 改了 harvest 核心扫描环；无 peer 写盘检查 | ❌ P0 |
| 清理磁盘冗余（归档） | 已执行，冗余 0.0% | ✅ |
| 诊断 eg / stddev / ccl；勿把 lh/basis_momentum 当 0% 诊断靶 | 靶正确；lh 在报告中为 45.5%「良好」 | ✅ |
| 唯一 variant 口径；小样本不砍探索 | 报告按 `variant_id` 去重；n&lt;10 观察 | ✅ |
| Laya 不可学习 | 未主张训练 Laya；建议落在外环采样/规则 | ✅ |
| 不重做队列去重 | 保留 | ✅ |

**结论**：Phase 1 的 **磁盘清理 + 诊断** 对齐 SPEC；**写盘前登记** 名实不符，属于把「读盘/收割加速」做成了「写盘防冗余」的替代品——能降 harvest 重复扫描成本，**不能**阻止 peer 继续落盘重复 JSON。

---

## §4 逻辑 / Bug 清单

### P0（放行前必改）

1. **登记挂错层**：SPEC/计划明确 peer **写盘前**；实现只在 harvest `glob` 后跳过。验收「不落盘」为假。后续冗余会再次堆积。  
2. **Changelog / 验收勾选过度声明**：将 harvest 侧跳过写成「写盘前登记已完成」。须改正文与勾选，或补齐真正写盘钩子后再勾。

### P1（强烈建议下一迭代前）

1. **`register` 跨实例不幂等**：锁内双检只看本实例 `_stems`，不重读 JSONL → 同 stem 可多行（本机复现 4 行）。`load()` 的 `count` 亦可能 &gt; 唯一 stem。  
2. **解析成功即永久 `register`，且命中即 `continue`**：被质量门/schema 拒绝的 stem 也登记；之后更好的同 stem 新文件永不入队。与「仅防重复落盘」语义不同，更像「stem 终身一次收割」。  
3. **生产 registry 未回填**：仅 21 条 `run_T` 测试污染；780/796 live stem 未登记。应：清空或隔离测试污染 → 一次性 backfill 现网 796 → 再开 peer 钩子。  
4. **测试污染生产路径**：`variant_registry.jsonl` 含 `run_T`；说明曾有未隔离写入。harvest 测试现已 monkeypatch，但生产文件需净化。

### P2

1. `has_stem` 无跨进程可见性（依赖启动时 `load`）；长 harvest 期间他进程新注册不可见。  
2. 归档 `copy2`+`unlink` 非原子；execute 与 manifest 存在 TOCTOU。  
3. 诊断报告 `fdr_pass` 一行（gate_pass 中仅 4）可疑，宜复核计数口径。  
4. 诊断脚本硬编码 symbol/family 列表（changelog 已记 LOW）。  
5. IMPLEMENTATION.md 与 changelog 口径打架（前者诚实写 harvest，后者写写盘前）。

---

## §5 测试与缺口

**已跑（本机 `.venv`，2026-10-20）**  
- `tests/test_variant_registry.py`：7 passed  
- `tests/test_archive_proposals.py`：8 passed  
- `tests/test_harvest_proposals.py` + `test_harvest_status_integration.py`：43 passed  

**缺口**  
- 无 **peer 写盘路径** 单测（因为根本没实现）  
- `test_concurrent_safety` 用 **不重叠** stem 区间，**测不出** 同 stem 跨实例重复写（已用独立脚本复现 BUG）  
- 无「拒绝后同 stem 再来应否入队」的产品语义测试  
- 无生产 registry 回填/净化的验收步骤  

---

## §6 结论与放行

| 维度 | 评分 |
|------|------|
| Task 1 写盘前登记 | ~40%（库在、钩错、生产未覆盖） |
| Task 2 磁盘归档 | ~95% |
| Task 3 低效诊断 | ~90% |
| Changelog 诚实度 | 偏低（Task 1 验收文案） |
| **Phase 1 整体** | **~72%** |

**结论: 有条件通过**

**放行条件（满足前不要开 Phase 2 的「依赖写盘登记已防冗余」假设）**  
1. 在真正的 peer/生成 **写盘前** 接入 `VariantRegistry.has_stem` / `register`（harvest 保留为第二道，或改为仅统计、避免「终身跳过未入队 stem」）。  
2. 修正 changelog 验收表述；删除或改写「不落盘已完成」。  
3. 修复 `register` 锁内重读；净化并 backfill 生产 registry 至 ≈796。  
4. 补同 stem 跨实例并发测试 + 写盘钩子测试。  

Task 2/3 产出（归档结果、诊断报告数字、Laya 红线）**可以采纳**；Task 1 需返工后再算 Phase 1 闭环。

---

## 附录：本机关键复算（Asia/Shanghai）

```
live_files=796  unique_stems=796  redundancy=0.0  manifest_lines=6593
registry_stems=21  live_not_in_reg=780  registry_refs=[sup_harvest, sup_paths, variant_registry]
unique_verdicts≈568  gate_pass=183
eg: 47/1=2.1%  stddev: 17/2  ccl: 31/5
race(same stem, 4 threads): JSONL lines=4 (BUG)
pytest: 58/58 named Phase1 tests passed
```
