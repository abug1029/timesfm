# TypeSafe 协变量提案预筛实施记录

## 2026-09-22 — 实施完成

**Task 1**: 核心模块 + 38 测试 ✅ (commit 31d5309)
**Task 2**: 环境配置 + 慢环集成 + 触发端调用 + 3 集成测试 ✅ (commit f19ff0d)
**Task 3**: 人工历史数据验证脚本 ✅

### 文件清单
| 文件 | 操作 |
|------|------|
| `cascade/typesafe_prescreen.py` | 新增 — 核心模块 (421 行) |
| `tests/test_typesafe_prescreen.py` | 新增 — 38 单元测试 |
| `tests/test_slow_loop_prescreen.py` | 新增 — 3 集成测试 |
| `data/config.py` | 修改 — get_typesafe_api_key() |
| `task_FM/task.yaml` | 修改 — TYPESAFE_API_KEY 环境变量 |
| `scripts/aligned_slow_loop.py` | 修改 — prescreen metadata 注入 |
| `scripts/praxist_supervisor.py` | 修改 — prescreen 触发端调用 |
| `scripts/validate_typesafe_prescreen.py` | 新增 — 人工验证脚本 |

### 测试结果
- 41 tests passed, 0 failed
- 人工验证脚本可正常运行（需 TYPESAFE_API_KEY 才真正调用 API）

---

## 2026-09-22 后续 — SDK 适配 + Phase 2/3 + 技术债

**commit cc856cb** — typesafe-sdk v0.7.1 API 适配
-  → ,  → 
- →, →, →(float→int)
-  → , 模型名  → 
- 41 测试全绿

**commit b78f72f** — Phase 2: Jev prescreen 调度降权/奖励
- : 读 .prescreen.json 调整 
- invalid→-100, redundant+弱→-30, 低可信→-20; skip=False+高效果→+10, 新颖+高可信→+5
-  传 
- 12 新测试

**commit 98651b4** — Phase 3: Jev 判断质量追踪器
- : 扫描带 prescreen 的 verdict
- 指标: 高可信过门率/skip过门率/novelty dir_acc区分度/effect_size分桶
- 门禁 50 样本, 不足不产出调度建议
- 输出 

**commit cbd155f** — 技术债修复: supervisor prescreen 改 fire-and-forget
- : daemon 线程异步, 消除 N proposal 线性阻塞
- 防看门狗 S3 误判 + peer 等待超时
- 3 新测试

### 生产验证 (Jev 真实调用)
- API Key 已写入  (TYPESAFE_API_KEY)
- 5 历史 proposal 验证: JD/RB 完全一致, SS/CF/M 边界偏离 (Jev 判断 vs 人类预期差异)
- Jev prescreen 已实际写盘到 production results ()
- 当前总裁决 123 条, 带 prescreen metadata 0 条 (旧 verdict, 集成前生成)

### 待数据积累 (Phase 2.3 / Phase 3 自动校准)
- 需 ≥50 条带 prescreen 的新 verdict 才能触发质量校准
- Phase 2.3 (peer 反馈文件) 依赖 Jev 判断可信验证, 当前 0/50 暂缓


---

## 2026-09-22 后续 — SDK 适配 + Phase 2/3 + 技术债

**commit cc856cb** — typesafe-sdk v0.7.1 API 适配
- client.judge() → client.system_one(), result.data.answers → result.answers
- NoulAnswer.probability_yes→.noul, ChoiceAnswer.value→.choice, ScoreAnswer.level_index→.score(float→int)
- Score(levels=) → Score(criteria=), 模型名 jev → jev-latest
- 41 测试全绿

**commit b78f72f** — Phase 2: Jev prescreen 调度降权/奖励
- _apply_prescreen_score(): 读 .prescreen.json 调整 _proposal_priority_score
- invalid→-100, redundant+弱→-30, 低可信→-20; skip=False+高效果→+10, 新颖+高可信→+5
- harvest_proposals 传 proposal_path=sp
- 12 新测试

**commit 98651b4** — Phase 3: Jev 判断质量追踪器
- scripts/track_prescreen_quality.py: 扫描带 prescreen 的 verdict
- 指标: 高可信过门率/skip过门率/novelty dir_acc区分度/effect_size分桶
- 门禁 50 样本, 不足不产出调度建议
- 输出 reports/research/prescreen_quality_report.md

**commit cbd155f** — 技术债修复: supervisor prescreen 改 fire-and-forget
- _prescreen_async(): daemon 线程异步, 消除 N proposal 线性阻塞
- 防看门狗 S3 误判 + peer 等待超时
- 3 新测试

### 生产验证 (Jev 真实调用)
- API Key 已写入 .env.praxist (TYPESAFE_API_KEY)
- 5 历史 proposal 验证: JD/RB 完全一致, SS/CF/M 边界偏离 (Jev 判断 vs 人类预期差异)
- Jev prescreen 已实际写盘到 production results
- 当前总裁决 123 条, 带 prescreen metadata 0 条 (旧 verdict, 集成前生成)

### 待数据积累 (Phase 2.3 / Phase 3 自动校准)
- 需 ≥50 条带 prescreen 的新 verdict 才能触发质量校准
- Phase 2.3 (peer 反馈文件) 依赖 Jev 判断可信验证, 当前 0/50 暂缓
