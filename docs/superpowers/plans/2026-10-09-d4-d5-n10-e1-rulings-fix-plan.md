# D4/D5/N10/E1 裁决处置实施计划

**日期**: 2026-10-09  
**基于**: `reports/2026-10-08-d4-d5-n10-e1-q-rulings.md`  
**状态**: 待宿主批准后实施

---

## 0. 摘要

根据裁决记录，需处置 5 项问题：

| 优先级 | 任务 | 工作量 | 前置 |
|--------|------|--------|------|
| **P1** | 旗标过期 7天→4小时 | 0.5 天 | 无 |
| **P2** | 调度挂载 + 实弹演练 | 1 天 | P1 完成 |
| **P3** | Q2 勘误（守卫 docstring + spec） | 0.5 天 | 无 |
| **P4** | 数字勘误 21→23 + 措辞修正 | 0.5 天 | 无 |
| **P5** | 扩展名不一致入技术债 | 0.5 天 | 无 |

**关键约束**:
- P1/P2 完成前，D4 交付状态不得记「已完成」
- P2 需宿主裁定调度落点（WSL cron 推荐 vs Windows Task Scheduler）
- 所有改动须经 expert reviewer 审核

---

## 1. P1 — 旗标过期改回 4 小时

### 1.1 问题

- closure spec §4.1.3 原文裁定：T_expire = **4 小时**
- 实施取 7 天（168 小时），未附偏离理由
- 最坏暴露窗口放大 42 倍，弱化 fail-safe

### 1.2 修复方案

**步骤**:
1. 定位常量：搜索 `MAINT_FLAG_EXPIRE_DAYS` 或类似命名
2. 修改为 4 小时口径：
   - 选项 A：改名为 `MAINT_FLAG_EXPIRE_HOURS=4`
   - 选项 B：保持天数命名，改为 `MAINT_FLAG_EXPIRE_DAYS=0.167`（不推荐，浮点数不直观）
   - **推荐选项 A**
3. 更新相关注释和文档
4. 补充/更新单元测试：
   - 测试旗标 mtime = 3 小时前 → 未过期，自愈禁用
   - 测试旗标 mtime = 5 小时前 → 已过期，自愈恢复
5. 运行测试验证

**文件改动**:
- `scripts/diagnose_three_loop.sh`（常量定义 + 过期判断逻辑）
- `tests/test_diagnose_three_loop.py` 或对应测试文件（新增过期测试）

### 1.3 验证

- 单元测试通过
- 手动演练：创建旗标 → 等 5 小时（或 mock mtime）→ 验证自愈恢复

---

## 2. P2 — 调度挂载 + 实弹演练

### 2.1 问题

- 看门狗代码 100% 就绪，但**无任何定时触发**
- D4 生产未激活

### 2.2 宿主裁定事项

**调度落点选择**（二选一）：

| 选项 | 优点 | 缺点 |
|------|------|------|
| **WSL cron（推荐）** | 一行即挂载；crontab 已有 3 条存活任务证明通道可靠；符合调研 spec 的 WSL 闭环诉求 | WSL 重启后需确认 cron 服务自动启动 |
| Windows Task Scheduler | 符合 closure spec 原裁定；抗 WSL 重启 | 需 Windows 侧手工配置；补 A.1 文档；与调研 spec 的 WSL 闭环诉求矛盾 |

**请宿主裁定选择哪个选项。**

### 2.3 实施方案（以 WSL cron 为例）

**步骤**:
1. 编辑 crontab：`crontab -e`
2. 添加一行：`*/15 * * * * /home/abug/timesfm/scripts/diagnose_three_loop.sh >> /home/abug/timesfm/data/cache/diagnose.log 2>&1`
3. 保存并验证：`crontab -l` 确认条目存在
4. 等待 15 分钟，检查日志：`tail -f /home/abug/timesfm/data/cache/diagnose.log`
5. **实弹演练**：
   - 找到 supervisor PID：`pgrep -f "scripts/praxist_supervisor.py"`
   - 杀掉 supervisor：`kill -TERM <pid>`
   - 等待 ≈27 分钟（15 分钟调度 + 12 分钟心跳阈值）
   - 验证 supervisor 已恢复：`pgrep -f "scripts/praxist_supervisor.py"` 应返回新 PID
   - 检查日志：应看到「S1 supervisor down」+ 自愈动作
6. 补充文档（A.1）：
   - 说明调度配置方法
   - 说明如何查看日志
   - 说明如何临时禁用（删 crontab 条目）
   - 说明实弹演练方法

**文件改动**:
- WSL crontab（运行时配置，不进 git）
- `docs/superpowers/plans/2026-10-08-d4-watchdog-implementation.md` 或类似文档（补充调度配置章节）

### 2.4 验证

- crontab 条目存在
- 日志显示每 15 分钟执行一次
- 实弹演练成功：杀 supervisor → ≈27 分钟内恢复
- 文档完整

### 2.5 D4 交付状态

P2 完成后，D4 方可记「已交付」。

---

## 3. P3 — Q2 勘误

### 3.1 问题

**「值域守卫防止第三套语义混入」声明不成立**

- 归档代码 `two_star_critic.py:37-39` 的 `TIER_A/B/C` 是**品种集合常量**，不是 `"A"/"B"/"C"` 字面值
- 若真有人把组名 `"A"` 写入 `verdict["tier"]`，`"A" ∈ {S,A,B,C,D}`，守卫会放行
- **第三套语义的实际防线**是「写入方唯一 + two_star_critic 已退役」，而非值域

### 3.2 修复方案

**步骤**:
1. 修改 `is_valid_tier()` docstring：
   - 原文可能写「防止第三套语义混入」
   - 改为「防止非法值（第二套中文语义、None、数字等）；第三套语义防线是写入方唯一性 + two_star_critic 已退役」
2. 修改调研 spec §4.2.1：
   - 原文：「值域守卫防止第三套语义混入」
   - 改为：「值域守卫防止非法值；第三套语义防线是写入方唯一性 + two_star_critic 已退役且其本身从不写 verdict」
3. 检查其他相关文档是否有类似不实声明，一并修正

**文件改动**:
- `cascade/tier_classifier.py` 或 `is_valid_tier()` 所在文件（docstring）
- `docs/superpowers/specs/2026-10-08-d4-d5-n10-e1-research-spec.md` §4.2.1

### 3.3 验证

- docstring 准确描述守卫能力边界
- spec 文档一致
- 无其他不实声明

---

## 4. P4 — 数字勘误 + 措辞修正

### 4.1 问题

1. KB 品种数：调研 spec 写 21/21，实测 23/23
2. 调研 spec §1「关键约束」语病：「不依赖 Windows Task Scheduler 以外的外部服务」表述有歧义

### 4.2 修复方案

**步骤**:
1. 搜索调研 spec 中所有「21/21」，改为「23/23」
2. 修改 §1「关键约束」：
   - 原文：「D4/D5 所有逻辑必须在 WSL 环境内闭环，不依赖 Windows Task Scheduler 以外的外部服务」
   - 改为：「D4/D5 所有逻辑必须在 WSL 环境内闭环，不依赖外部服务（Windows 侧工具仅在调度落点选择时使用，且为可选项）」
   - 或更清晰的表述：「D4/D5 核心逻辑在 WSL 内闭环；调度落点可选 WSL cron（推荐）或 Windows Task Scheduler」

**文件改动**:
- `docs/superpowers/specs/2026-10-08-d4-d5-n10-e1-research-spec.md` 多处

### 4.3 验证

- 全文搜索「21」确认无遗漏
- 措辞清晰无歧义

---

## 5. P5 — 扩展名不一致入技术债

### 5.1 问题

- `l1_economic_verdict.py` `--out` 默认 `ECONOMIC_VERDICT.md`
- `build_knowledge_base.py:23` `DEFAULT_L1` 读 `.json`
- 即使上游齐备、生成器跑通，默认参数也对不上
- 若日后重启 E1，这是第一修复项

### 5.2 修复方案

**步骤**:
1. 在技术债清单中新增条目：
   - ID: E1-EXT-MISMATCH（或类似）
   - 描述：生成器默认输出 `.md`，KB 默认读取 `.json`，扩展名不一致
   - 优先级：高（E1 重启前置修复项）
   - 修复方案：改生成器 `--out` 默认值为 `.json`（与 KB 读取方一致）
   - 影响范围：`l1_economic_verdict.py`、`build_knowledge_base.py`
2. 若已有技术债清单文件，追加条目；若无，创建新文件

**文件改动**:
- `docs/superpowers/plans/tech-debt-register.md` 或类似文件（新增条目）

### 5.3 验证

- 技术债条目清晰
- 修复方案明确
- 优先级标注正确

---

## 6. 实施顺序

```
P1（旗标过期） ──→ P2（调度挂载）
P3（Q2 勘误） ──→ 独立
P4（数字勘误） ──→ 独立
P5（技术债） ──→ 独立
```

**关键路径**: P1 → P2（P2 依赖 P1 完成）

**建议批次**:
- **批次 1**：P1 + P3 + P4 + P5（可并行，无依赖）
- **批次 2**：P2（依赖 P1 完成，需宿主裁定调度落点）

---

## 7. 验证与审核

### 7.1 每个任务的验收标准

| 任务 | 验收标准 |
|------|---------|
| P1 | 单元测试通过；手动演练旗标过期逻辑正确 |
| P2 | crontab 条目存在；实弹演练成功（杀 supervisor → ≈27 分钟内恢复）；文档完整 |
| P3 | docstring + spec 准确描述守卫能力边界 |
| P4 | 全文无「21/21」；措辞清晰 |
| P5 | 技术债条目清晰完整 |

### 7.2 Expert Review

每个任务完成后派发 expert reviewer 审核：
- P1/P2：重点审核代码逻辑 + 实弹演练证据
- P3/P4：重点审核文档准确性
- P5：重点审核技术债条目完整性

---

## 8. 待宿主裁定事项

1. **P2 调度落点选择**：WSL cron（推荐） vs Windows Task Scheduler？
2. **P2 实弹演练时间窗口**：何时进行？（需 ≈30 分钟，期间 supervisor 会被杀掉）

---

## 9. 交付状态更新

| 任务 | 当前状态 | 处置后状态 |
|------|---------|-----------|
| D4 看门狗 | 代码就绪，调度未挂载 | P1/P2 完成后记「已交付」 |
| D5 孤儿回收 | ✅ 已交付 | 维持 |
| N10 tier 消歧 | ✅ 已交付（值域守卫） | P3 完成后勘误闭环 |
| E1 经济判决 | ✅ 已放弃（Q1=(c)） | P5 完成后技术债登记 |

---

## 10. 下一步

1. **宿主批准本计划**
2. **宿主裁定 P2 调度落点**
3. **实施批次 1**：P1 + P3 + P4 + P5
4. **实施批次 2**：P2（需宿主确认实弹演练时间）
5. **每个任务完成后 expert review**
6. **P1/P2 完成后，D4 记「已交付」**

---

**文档完成时间**: 2026-10-09  
**基于**: `reports/2026-10-08-d4-d5-n10-e1-q-rulings.md`  
**状态**: 待宿主批准 + 裁定 P2 调度落点
