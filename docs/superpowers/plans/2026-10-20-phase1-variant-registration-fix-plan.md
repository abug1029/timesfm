# Phase 1 返工修复计划：写盘前 variant 登记

| 项 | 内容 |
|---|---|
| 对象 | Phase 1 Task 1 返工（C1 + M1–M4） |
| 依据 | 用户审核结论 CONDITIONAL_APPROVE ~68%；实施审核 `reports/2026-10-20-phase1-variant-registration-diagnosis-implementation-audit.md` |
| 对照 SPEC | `specs/2026-10-19-proposals-evaluation-optimization-spec.md` v3.1 §5.1 |
| 硬约束 | **Laya 只是判断模型，无法学习** — 本计划不触及 Laya 权重/训练 |
| 状态 | 待执行 |
| 日期 | 2026-10-20（Asia/Shanghai） |

---

## §0 一句话目标

把「写盘前登记」钩回 **peer/生成写盘前**（非 harvest 扫描环），修跨实例幂等并净化/回填生产 registry，改正 changelog 虚假验收；Task 2/3 已采纳产出不重做。

---

## §1 问题清单 → 本计划映射

| ID | 问题 | 严重度 | 本计划 Task |
|----|------|--------|-------------|
| C1 | 登记挂在 `sup_harvest` 扫描环，非 peer 写盘前；「不落盘」为假 | CRITICAL | T1 |
| M1 | `register` 锁内不重读 JSONL → 同 stem 跨实例多行 | MAJOR | T2 |
| M2 | 生产 registry 仅 ~21 条，796 live 缺 ~780 | MAJOR | T3 |
| M3 | registry 含 `run_T` 测试污染 | MAJOR | T3 |
| M4 | changelog 声称「重复 stem 不落盘」虚假 | MAJOR | T4 |
| （放行#4） | 缺同 stem 并发测 + 写盘钩子集成测 | 放行条件 | T5 |

**不在本计划**：Task 2 归档、Task 3 诊断（已 ~90–95%，仅可选 P2 跟进）。

**根因（须写进 IMPLEMENTATION）**：harvest 是事后扫描已落盘文件；真正「写盘前」在 peer 响应解析后、写入 `results/**/proposals/*.json` 之前。peer 写入由 **praxist / 外部框架** 完成，须定位其输出处理层或本仓可挂的结果回调，而不是继续改 harvest 当主钩子。

---

## §2 非目标

- 不重做队列去重（`registry_lib.queue_enqueue` / harvest `_reject("dedup")` 保留为第二道）。
- 不训练/微调 Laya；不把诊断反馈写成 Laya 学习。
- 不重跑 Task 2 归档（live 已 796/0% 冗余，除非修复期间又堆积再评估）。
- 不把 harvest 侧 `has_stem → continue` 删光后再无写盘钩子（过渡期可保留为第二道，见 T1.4）。

---

## §3 Task 分解

### T1 — C1：写盘前钩子（CRITICAL，挡闭环）

**目标**：在真正写出 `proposals/*.json` 之前调用 `VariantRegistry.has_stem`；若已存在则 **跳过写盘**；新 stem 在 **成功写盘后**（或写盘事务提交前持锁）`register`。

**步骤**

1. **定位钩点**（先探查，再改代码）  
   - 在 WSL 仓与 praxist 相关路径搜索：`proposals/*.json` 写入、`json.dump`/`write_text`、peer result callback、`save_proposal`、praxist output handler。  
   - 产出短文：`docs/superpowers/reports/2026-10-20-phase1-writepath-hook-locus.md`（路径 + 调用栈 + 推荐 1 个挂点）。  
   - 若钩点在 **仓外** praxist：列出最小补丁（文件/函数）与本仓可暴露的 API（例如 `scripts/variant_registry.py` 的 CLI：`check` / `register`）。

2. **接入 API（本仓）**  
   - 保证 `VariantRegistry` 对外稳定接口：  
     - `has_stem(stem) -> bool`（跨进程可见：读盘或共享状态）  
     - `try_register(stem, run_id) -> bool`（True=首次占位成功；False=已存在）  
   - 推荐语义：**先 try_register 占位，再写盘；写盘失败则 unreserve/补偿**（或写盘成功后再 register，但须接受极窄竞态窗口——须在 IMPLEMENTATION 写明取舍）。  
   - **推荐默认**：锁内 `reload_stems_from_disk` → 若无则 append 占位 → 释放锁 → 写盘 → 失败则标记/删除占位行（T2 一并做）。

3. **挂接**  
   - 在探查确定的写盘路径调用上述 API。  
   - 验收：「同 stem 第二次生成 **不产生新 JSON 文件**」（用临时目录或 dry-run 目录实证）。

4. **harvest 角色调整**  
   - 保留 harvest 内 registry 为 **第二道**（加速扫描 / 防漏网），但：  
     - 不得再把「仅 harvest 跳过」写成「写盘前登记完成」。  
     - **修正终身跳过语义（与实施审核 P1-2）**：仅在「成功入队或明确采纳」时 register；或 `has_stem` 命中时改为「跳过重复文件但仍允许同 stem 新文件走质量门」——产品默认建议：  
       - **写盘前**：防重复落盘（主目标）。  
       - **harvest**：对已 register 且已成功收割的 stem 跳过；**不要**在「解析后立刻 register」导致被拒 stem 终身不入队。  
   - 具体改法二选一（IMPLEMENTATION 钉死一种）：  
     - **A（推荐）**：harvest **不再** `register`；只读 registry；register 仅写盘路径 + backfill。  
     - **B**：harvest 仅在 `queue_enqueue` 成功后 `register`。

**验收**

- [ ] 文档写明真实钩点路径（仓内或 praxist）。  
- [ ] 集成测：同 stem 第二次 **文件不落盘**。  
- [ ] SPEC §5.1 对齐：主钩子在生成写盘，harvest 非唯一防线。

---

### T2 — M1：跨实例幂等

**目标**：同 stem 多进程/多线程 `register` → JSONL **唯一一行**。

**步骤**

1. 在 `register` / `try_register` 持 flock 期间：  
   - `reload` 文件内全部 stem 到集合（或尾部增量+全量校验）。  
   - 若 stem 已在盘上 → 返回 False，不 append。  
   - 否则 append 一行并 flush。  
2. 删除或修正「只查本实例 `_stems`」的双检逻辑。  
3. `load()` 的 `count` 改为 **唯一 stem 数**（去重），避免重复行导致虚高。

**验收**

- [ ] 复现脚本：4 线程同 stem → JSONL 行数 == 1（或唯一 stem == 1）。  
- [ ] 单测见 T5。

---

### T3 — M2 + M3：净化 + backfill 生产 registry

**目标**：生产 `data/cache/variant_registry.jsonl` 无测试桩；覆盖现网 live 唯一 stem（≈796，以当日为准）。

**步骤**

1. **隔离测试**（防再污染）  
   - 所有测例必须 monkeypatch `VARIANT_REGISTRY_PATH` 到 tmp（已有则审计缺口并补全）。  
   - 禁止测例写默认生产路径。  
2. **净化**  
   - 备份现文件 → 删除 `run_T` / 测试桩 stem → 或整文件替换为 backfill 产物。  
3. **Backfill**  
   - 脚本（新建或扩展）：扫描 live `proposals/*.json`（归档后目录），按与写盘相同的 **stem 规则** 写入 registry。  
   - Dry-run 打印 will_add / already / conflict。  
   - Execute 后：`unique_stems(registry) == unique_stems(live)`（允许说明已知差异）。  
4. **与 T1 顺序**：建议 **先 T2 → T3 backfill → 再开 T1 生产钩子**，避免脏数据下占位。

**验收**

- [ ] registry 无 `run_T`。  
- [ ] live 未登记数 → 0（或文档记录 ≤N 条例外及原因）。  
- [ ] 备份路径写入 changelog。

---

### T4 — M4：修正 changelog / 文档诚实度

**目标**：文案与实现一致。

**步骤**

1. 修订 `changelogs/2026-10-20-phase1-variant-registration-diagnosis-changelog.md`：  
   - 取消或改写「重复 stem 不落盘 / 写盘前登记已完成」。  
   - 诚实写：v1 仅 harvest 第二道；返工见本 fix plan + 后续 changelog。  
2. 对齐 `IMPLEMENTATION.md`（若有）：统一「主钩子在写盘 / harvest 为第二道」。  
3. 本 fix 合并后再追加新 changelog 条目勾选真实验收。

**验收**

- [ ] 旧虚假勾选已改；读者不会以为「不落盘」已在 harvest-only 版本成立。

---

### T5 — 测试补强（放行条件 #4）

1. **同 stem 跨实例并发**：多进程或多线程同时 `register(same_stem)` → 唯一行。  
2. **写盘钩子集成**：mock/临时目录下，第一次写成功并 register；第二次 `has_stem`/`try_register` 失败且 **无第二文件**。  
3. **（推荐）拒绝语义**：若选 T1 方案 A/B，各补 1 个测例锁定「被拒 stem 是否可再入队」。  
4. 回归：既有 `test_variant_registry` / harvest / archive 全绿。

---

## §4 推荐执行顺序

```text
T2（幂等） → T3（净化+backfill） → T1.1 探查钩点 → T1.2–T1.4 挂接
    → T5 测试 → T4 改旧 changelog + 写新 changelog
```

并行许可：T4 初稿可与 T2 并行；T1.1 探查可与 T2 并行。

---

## §5 风险与回滚

| 风险 | 缓解 |
|------|------|
| 钩点在仓外 praxist，本仓无法单独合入 | 探查文档给出最小外仓 PR；本仓先交付 CLI + 幂等 + backfill，钩子以外仓 PR 为准，**未挂上前不算 C1 关闭** |
| try_register 后写盘失败留下占位 | 补偿删除或 `status=pending_write` 字段；超时清理脚本 |
| backfill stem 规则与写盘不一致 | 与写盘同一 `stem_from_path` / `stem_from_proposal` 函数，禁止两套字符串逻辑 |
| 改 harvest 注册时机影响在途收割 | 方案 A 最安全；若选 B，先 staging dry-run |

**回滚**：保留 registry 备份；写盘钩子用 feature flag（如 `VARIANT_REGISTRY_ENFORCE=1`）默认关闭直至集成测通过。

---

## §6 完成定义（DoD）= 原放行 4 条件

1. **C1**：peer/生成写盘前接入 VariantRegistry；实证同 stem 不落盘第二份文件。  
2. **M4**：changelog 虚假验收已改。  
3. **M1+M2+M3**：锁内重读幂等；生产 registry 净化并无缺口 backfill。  
4. **测试**：同 stem 跨实例并发 + 写盘钩子集成测通过。

全部满足后：Phase 1 Task 1 可重审；再开依赖「写盘登记已防冗余」的 Phase 2 假设。

---

## §7 产出物清单

| 产出 | 路径（预期） |
|------|----------------|
| 本计划 | `docs/superpowers/plans/2026-10-20-phase1-variant-registration-fix-plan.md` |
| 钩点探查 | `docs/superpowers/reports/2026-10-20-phase1-writepath-hook-locus.md` |
| 返工 changelog | `docs/superpowers/changelogs/2026-10-20-phase1-variant-registration-fix-changelog.md`（执行后） |
| 代码 | `scripts/variant_registry.py`、写盘钩子、可选 `scripts/backfill_variant_registry.py`；harvest 注册时机调整 |
| 测试 | `tests/test_variant_registry.py` 扩展 + 写盘钩子集成测 |

---

## §8 与 Laya / SPEC 边界

- 本计划 **只** 做库存卫生与写盘防冗余。  
- 不修改 Laya 调用、不引入「学习机制」。  
- 诊断（Task 3）结论可继续指导外环采样优先级；不在本 fix 范围重跑诊断。
