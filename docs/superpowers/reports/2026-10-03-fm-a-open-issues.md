# FM_a 未决问题清单（v4 协议运行期）

- **报告日期**：2026-10-03（数据取至 10:05）
- **窗口**：2026-10-02 20:27 修复后重启（PID 416）→ 2026-10-03 10:05，约 13.6h
- **关联**：
  - 运行成果报告 `docs/superpowers/reports/2026-10-03-three-loop-v4-operations-report.md`
  - changelog `docs/superpowers/changelogs/2026-10-01-v4-stage2-done-stage3-start.md`
  - 计划 `docs/superpowers/plans/2026-09-30-v4-convergence-implementation-plan.md`
  - spec `docs/superpowers/specs/2026-09-24-covariate-research-credibility-design.md`（v15 §4.3 W3.6 / §4.7 W6.1）

## 摘要

| 级别 | 数量 | 关键项 |
|---|---|---|
| **P0** | 1 | `family_dead` 判据与确认机制耦合，提案池正被单调清空 |
| **P1** | 2 | 确认通道需 1.2–2.0 年才有首结果（按设计）；DM 显著候选的协变量为自指类 |
| **P2** | 4 | 红测试 2 处；SIGTERM 首次被忽略；agri 板块长期半退化 |
| 勘误 | 1 | `star` 字段全历史不存在（此前表述不成立，见 §4） |

---

## 1. P0：`family_dead` 判据与确认机制耦合 —— 提案池正被单调清空

### 1.1 机制

`_dead_families(snapshot, min_ok=4)`（`scripts/praxist_supervisor.py:1194`）判死条件为
「该 family 累计 **≥4 条 ok 裁决** 且 **0 个 pass**」。

其中 `pass` 来自 `pass_variants()`，其严格链（spec §4.3 W3.4）要求
`run_mode == "confirmation"` **且** `fdr_pass` **且** `p_value is not None`。

**在确认机制产出任何结果之前（本项目当前状态），`pass` 恒为 0**。
于是判据退化为「只要某 family 累积 4 条 ok 裁决即判死」，与 family 实际前景无关。

### 1.2 实测证据

- 已判死 family：**`term_structure`**（5 条 ok 裁决）
- 各 family 的 ok 裁决数：`momentum 15` / `inventory 13` / `volatility 8` / `term_structure 5` / `calendar 3`
- `family_dead` 拒收逐轮增长（阶段② 7 轮）：

| 轮次时间 | seen | family_dead | no_failure_delta | 可用候选 |
|---|---|---|---|---|
| 10-02 20:28 | 3,211 | 602 | 1,226 | 123 |
| 10-03 00:46 | 3,408 | 619 | 1,515 | 110 |
| 10-03 04:57 | 3,496 | 627 | 1,708 | 93 |
| 10-03 08:52 | 3,578 | **642** | **1,922** | **67** |

→ 13.6h 内 `family_dead` +40、`no_failure_delta` +696、可用候选 **−46%**。

### 1.3 影响

按此斜率，提案池将在数日内再次枯竭，重演 2026-10-02 已定位并修复的那一轮收割饿死
（根因为 `_harvest_rows` 用未过滤快照，已由 `045c7e2` 修复）。
两轮病因不同但后果相同：**收割入队率归零 → 慢环饿死 → 探索产出停滞**。

### 1.4 建议

1. `min_ok` 提高到有意义的量级（确认级裁决 ≥30 条量级）；
2. 或将判据改为「探索期全败 **且** 确认期已启动（该 family 存在 `run_mode=confirmation` 记录）」；
3. 过渡期豁免：确认产出为 0 的阶段不应触发 family 判死。

---

## 2. P1：确认通道需 1.2–2.0 年才有首结果（按设计，非故障）

- 首批 2 条预注册已注册（`task_FM/config/preregistry.jsonl`）：
  jd `daily_slope+vor` n_confirm_required=**1,199**；sr `daily_slope+vwap_deviation` n_confirm_required=**986**；`confirm_from_ts=2026-10-03 00:00:00`。
- 按 Q7 裁定 (a′) 的 live 密度外推：jd 约 2.0 年、sr 约 1.2 年。
- **耦合放大**：该空窗期正是 §1 的 `pass ≡ 0` 成立的前提，两问题互为因果。
- 建议：把 Q7 的「每季按实测 Var_LR 复核 Δ_min / 按 live 密度修订日历」制度化为周期任务；
  并为过渡期设计替代判据（见 §1.4.3）。

## 3. P1：DM 显著候选的协变量为自指类，前视安全性无法证明

| variant | p_value（单侧） | dir_acc | horizon_known | pairing_valid | missingness_admissible |
|---|---|---|---|---|---|
| `m_momentum_b06ddbcd88e3` | **0.0236** | 0.515 | self_referential | False | False |
| `lh_momentum_8c75bd7b917f` | **0.0374** | 0.531 | self_referential | False | False |

- spec W5 要求低频数据按**实际公布时间**判定可用（`known_ahead`），自指类协变量需等价论证。
- `missingness_admissible=False` 是 §7.8 裁定前的**保守默认**（spec v12 降级约束要求如此），非缺陷。
- **唯一同时满足「过门 + known_ahead」的是 `cf_calendar_5bd18d23ae63`（dir_acc 0.576）**，
  但其 `p_value=None`（无共同 cutoff，DM 尚不可算）→ **最值得追加预注册的对象**。

## 4. 勘误：`star` 字段并非「v4 未产出」，而是**全历史都不存在**

此前报告（`2026-10-03-three-loop-v4-operations-report.md` §7.2）称
「`star` 字段 44/44 为 None：评级链在 v4 行未产出，与 gate_pass 脱节」——**该表述不成立**，现更正：

| 字段 | v4（44 行） | 旧代（188 行） |
|---|---|---|
| `star` 键是否存在 | **0/44（键不存在）** | 同样不存在（值全None） |
| `tier` 分布 | **S 6 / A 6 / B 21 / C 11** | — |
| `tier`（仅过门行） | **S 6 / A 4 / B 2 / C 1** | — |

- 真实评级由 `tier` 承载，写入点 `cascade/tier_classifier.py:133`。
- `--three-star` 只是历史 CLI 名，现映射「信用≥2星」（`scripts/cascade_predict.py:803`），与 `star` 字段无关。
- 结论：**不存在「评级链未产出」的问题**；`star` 是未使用的遗留字段名。

---

## 5. P2 清单

### 5.1 红测试 2 处（对方 agent 在飞提交的测试侧陈旧，不影响运行时）
| 测试 | 病因 |
|---|---|
| `tests/test_supervisor.py::test_maybe_enqueue_retests_gating_and_dedup` | fixture 裁决缺 `protocol_fingerprint`，被新的协议过滤正确排除（与 2.1 时 3 处 v3 pin 需升版同型） |
| `tests/test_no_dead_code.py::test_no_unaccounted_modules` | 一次性脚本 `scripts/write_first_preregistry.py` 已执行完（`preregistry.jsonl` 2 行已写）但零引用未挂账 |

### 5.2 SIGTERM 首次被忽略
2026-10-02 收机时第一次 SIGTERM 无效：180s 内 supervisor 继续收割并发起新 run；第二次 SIGTERM 生效（约 35s），最终 `exit_code 0`。与既有规程「约 90s干净退出」不符 → 信号处理路径待复核（疑似 handler 与主循环竞争）。

### 5.3 agri 板块长期半退化
`Sector partial degradation: agri has 5/10 symbols failed (50%)` 持续 46h+ 未变化。circuit-breaker 需板块全失败才拦（防饿死设计正确，spec §4.7 W6.1），提案流未断。**未决**：这 5 个品种为何系统性失败（数据缺失 / 协变量不适配 / 评估异常）未查。

---

## 6. 复核方法（可重放）

```bash
cd /home/abug/timesfm

# §1 family_dead 判死集合与 ok 计数
.venv/bin/python -c "import sys;sys.path.insert(0,'scripts');import praxist_supervisor as ps,registry_lib as rl;snap=rl.load_snapshot(ps.REGISTRY,only_protocol=ps._current_protocol_fingerprint());print(sorted(ps._dead_families(snap)))"

# §1 family_dead 拒收增长趋势
grep -o "'family_dead': [0-9]*" .omc/supervisor_decisions.jsonl | tail -7

# §4 star/tier 字段事实
.venv/bin/python -c "import json,collections;rows=[json.loads(l) for l in open('task_FM/config/aligned_verdicts.jsonl',encoding='utf-8') if l.strip()];v4=[r for r in rows if (r.get('protocol_fingerprint') or '').startswith('f02b2a43')];print('star键存在',sum(1 for r in v4 if 'star' in r),'/',len(v4));print('tier',dict(collections.Counter(r.get('tier') for r in v4)))"

# §5.1 红测试
.venv/bin/python -m pytest "tests/test_supervisor.py::test_maybe_enqueue_retests_gating_and_dedup" tests/test_no_dead_code.py -q

# 收割健康度（入队率 + 可用候选）
grep -c '"action": "harvested_proposals"' .omc/supervisor_decisions.jsonl
grep -c '"action": "harvest_empty"' .omc/supervisor_decisions.jsonl
```

## 7. 建议处置顺序

1. **§1 `family_dead`**（唯一正在持续损失产出，且与刚修好的收割口径同片区域，改动小、可测）
2. **§4 勘误**已在本报告与运行成果报告中同步更正
3. §5.1 红测试（树要绿）
4. §3 追加 `cf_calendar` 预注册（趁其未进入确认集）
5. §5.2 SIGTERM 路径复核 · §5.3 agri 品种失败根因

---
*报告生成：2026-10-03 10:05*