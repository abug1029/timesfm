# D4/D5/N10/E1 任务调研 Spec

> **日期**: 2026-10-08
> **状态**: **调研阶段**——提取自 `2026-10-08-open-issues-closure-spec.md`，供宿主逐项裁定
> **代码基线**: `c200210`（行号引用以该 commit 为准）
> **输入**: `2026-10-08-open-issues-closure-spec.md` §2 / §4 / §6 / §7 中 D4·D5·N10·E1 相关章节
> **目的**: 将四个任务的现状、建议方案、待定问题集中到一份调研文档，降低宿主审阅成本

---

## 1. 摘要

| 任务 | 性质 | 核心问题 | 建议方案 | 前置裁定 |
|------|------|----------|----------|----------|
| **D4** | 运维风险 | 有自愈脚本 `diagnose_three_loop.sh`，缺定时调度 | 收编现有脚本 + 配调度 + 维护窗口旗标 + 熔断 | Q7（脚本定位）、Q3（调度频率）、Q4（告警通道） |
| **D5** | 运维风险 | `start_new_session=True` 导致 supervisor 被杀后孤儿 run 持续烧算力 | 两段式写入 `active_runs.json` + flock 优先判据 + 重启前扫尾 | Q7、Q8（退出合同）、Q6（清理力度） |
| **N10** | 语义/机制欠账 | `tier` 一词承载三套语义（变体质量评级 / 品种目标判定 / 作业优先级） | 只做值域守卫，不改名 | Q2（是否改名） |
| **E1** | 证据链断裂 | 上游 `universe_eligibility.json` 不存在，KB 21/21 品种 `no_evidence` | 若活仓也没有，放弃 E1 | Q1（上游是否还在） |

**关键约束**：
- D4/D5 所有逻辑必须在 **WSL 环境内闭环**（不依赖 Windows Task Scheduler 以外的外部服务）
- Q4 告警通道：裁定为 **(b) 日志 + 桌面通知**
- T2（证据链闭合）已标「**未通过（被 Q1 阻塞）**」，不阻塞 T1/T3

---

## 2. D4 看门狗定时调度

### 2.1 问题现状

**已有资产**：`scripts/diagnose_three_loop.sh`（2026-09-21）已实现四条自愈分支：

| 分支 | 判据 | 动作 |
|------|------|------|
| S1 | supervisor 进程不存在 | `kill -TERM` + `start_supervisor.sh` |
| S2 | 心跳年龄 `HB_AGE > 12`（分钟） | 同上 |
| S3 | 近期 exit-126 | 同上 |
| S4 | 20 分钟无新 run（且慢环不在跑） | 同上 |

**心跳生产方**（已核实）：

| 位置 | 内容 |
|------|------|
| `praxist_supervisor.py:145` | `HEARTBEAT_PATH = <FM_ROOT>/data/cache/supervisor_heartbeat` |
| `:152` | `POLL_S = 300` |
| `:678-684` | `_write_heartbeat()` 定义 |
| `:4290` | 主循环每拍调用 `_write_heartbeat()` |

**缺失项**：

1. **无定时调度**——仓内无任何 cron / systemd / Task Scheduler 挂载记录
2. **无维护窗口旗标**——人工部署期间可能被自愈脚本 SIGTERM
3. **无熔断机制**——`start_supervisor.sh` 连续失败会形成重启风暴
4. **无孤儿扫尾挂钩**——自愈重启前不清理孤儿 run

### 2.2 建议方案

**收编 `diagnose_three_loop.sh` 为唯一自愈入口**（Q7=(a) 已裁定），四件事同批实施：

#### 2.2.1 调度（Q3=(a) 已裁定：15 分钟）

- **落点**：WSL 内闭环——三个选项：
  - **systemd user timer**：Linux 原生，WSL2 支持 systemd（需确认 Ubuntu-22.04 实例已启用）
  - **cron**：`crontab -e` 加 `*/15 * * * * /path/to/diagnose_three_loop.sh`
  - **shell 循环**：`while true; do ... sleep 900; done` 挂在一个 `setsid nohup` 孤儿进程里
- **时延推算**：心跳阈值 12 分钟 + 调度间隔 15 分钟 = **最坏 ≈27 分钟**恢复
- **附带项**：`diagnose_three_loop.sh:29` 的 `pgrep -f "scripts/praxist_supervisor.py"` 比裸 `pgrep -f praxist_supervisor` 窄，收编时须决定是否放宽

#### 2.2.2 维护窗口旗标（须带过期）

`data/cache/maintenance.flag` 存在时**只报状态、不执行自愈**。

| 规则 | 取值 | 说明 |
|------|------|------|
| 过期判据 | 旗标 **mtime > 4 小时**即失效 | 用 mtime 而非内容 |
| 过期行为 | 自动视为不存在，自愈恢复执行 | fail-safe 方向选「恢复自愈」 |
| 忘删检测 | 过期事件走告警通道 | 让「忘了删」被看见 |

**⚠️ 旗标必须有过期机制**，否则「忘删旗标」使自愈**永久失效**——比不装看门狗更糟。

#### 2.2.3 熔断（防重启风暴）

| 规则 | 取值 | 说明 |
|------|------|------|
| 连续失败计数 | `data/cache/heal_fail.count` | 一次成功自愈即清零 |
| 熔断阈值 | **连续 3 次** | 3 次仍失败基本是环境问题 |
| 熔断动作 | 停止自动自愈 + 走告警 | 复用脚本既有 `NEEDS_HUMAN` 分支 |
| 解除 | 人工删计数文件；或 30 分钟后自动半开一次 | 半开 = 试一次 |
| 退避 | 未熔断时也按 1× → 2× → 4× 递增 | 避免短周期反复 SIGTERM |

#### 2.2.4 孤儿扫尾挂钩

在自愈分支里、执行 `start_supervisor.sh` **之前**插入扫尾（见 §3 D5）。

### 2.3 告警通道（Q4=(b) 已裁定）

**日志 + 桌面通知**：
- 日志：`logs/heal_events.log`（标准格式、可 grep）
- 桌面通知：WSL 内通过 `wsl-notify-send` 或 `/mnt/c/Windows/System32/Windows.SecurityCenter/WscNotify.exe` 发送 Windows 桌面通知
- 事件类型：自愈成功、自愈失败、熔断触发、旗标过期

---

## 3. D5 孤儿 run 回收

### 3.1 问题现状

| 证据 | 内容 |
|------|------|
| `praxist_supervisor.py:4139` | `subprocess.Popen([...], start_new_session=True)` |
| 同函数上下文 | `fresh["current_batch_id"] = batch_id` 已落 `supervisor_state.json`——**有 batch_id，无 pid** |
| `data/cache/active_runs.json` | **不存在** |
| 退出钩子 | 无 kill 逻辑 |

**风险量化**：`start_new_session=True` 使子进程脱离父进程会话与进程组，supervisor 被 OOM kill / 段错误后 `aligned_slow_loop.py` **继续跑**，按 `aligned_max_points=600` 的回测规模可跑数小时。

**部分缓解**：孤儿进程**不会产生重复裁决**（last-wins + prereg_id 去重）。所以是**算力浪费而非数据污染**。

### 3.2 既有机制（避免造第四套）

| 机制 | 位置 | 作用 | 触发 |
|------|------|------|------|
| **flock 判活** | `:3158-3167` `aligned_slow_loop.lock` | 慢环是否真在跑（持锁即在跑） | 监督环查询时 |
| **按批次清理** | `:4102` `cleanup_batch_workers(batch_id)` | 按 `--batch-id` 做 `pkill` | 批次结束时 |
| **退出不杀子进程** | `:696` `_shutdown_exit()` docstring | 干净退出时刻意不杀子进程 | 信号退出 |

### 3.3 建议方案

**Q8=(a) 已裁定**：不改 `:696` 退出合同，只做硬杀兜底。
**Q6=(a) 已裁定**：只回收本 supervisor 派发的 run。

#### 3.3.1 两段式写入（消除竞态窗口）

**⚠️ 若 `Popen` 之后才写入 pid，supervisor 恰在 Popen 与写入之间被硬杀 → 孤儿无记录**。

| 阶段 | 时机 | 写入内容 |
|------|------|----------|
| **① 意图** | `Popen` **之前** | `intent`：`batch_id` + 提案上下文 + 启动时刻（**无 pid**）→ 原子落盘 |
| **② 回填** | `Popen` 成功后 | 该 `intent` 补 `pid`，转正式记录 |
| **③ 清理** | 批次结束 / 正常退出 | 删除对应条目 |

#### 3.3.2 flock 优先判据

| 情形 | 含义 | 处置 |
|------|------|------|
| json 有 pid，但 flock 显示未持锁 | 记账在、进程不在（或 pid 已复用） | **不杀**，直接清条目 |
| flock 持锁，但 json 无对应 pid | 记账丢失，进程真在跑 | **杀**，pid 由 `/proc` 反查 |
| 两者一致 | 正常 | 按 json 的 pid 条目处置 |

**结论**：**flock 是权威**（内核事实），json 只是「杀哪个 pid」的线索。

#### 3.3.3 防误杀

- 记录 `pid` + 进程创建时刻（Linux `/proc/<pid>/stat` 第 22 字段）
- pid 复用时跳过
- 批次号兜底时须校验 worktree 路径（Q6 裁定附带要求）

#### 3.3.4 扫尾位置

`diagnose_three_loop.sh` 自愈分支内、调 `start_supervisor.sh` **之前**插入扫尾。
遇到无 pid 的 `intent`（① 已写、② 未回填即被杀）：以 flock + `/proc` 进程树反查定位；查不到则仅清该 `intent`。

---

## 4. N10 tier 三重语义消歧

### 4.1 问题现状

| 位置 | 语义 | 粒度 | 取值 |
|------|------|------|------|
| `cascade/tier_classifier.py:138` | 变体级质量评级（105 分制） | variant | `S/A/B/C/D` |
| `praxist_supervisor.py:1114/1196` | 品种级目标判定 | symbol | `可预测/当前不可验证/需更多样本` |
| ~~`two_star_critic.py:37-39`~~ | 作业优先级批次 | symbol | `A/B/C` —— **已于 2026-10-08 随信用档退役归档** |

**已埋雷**：`praxist_supervisor.py:1148` 与 `:1167` 用 `v.get("tier") in ["A", "B"]` 读取裁决。
- 写入方目前唯一（`aligned_slow_loop.py:554` ← `tier_classifier`），故当前不冲突
- 但第三套语义（硬编码 `"A"/"B"/"C"`）与第一套的 `A`/`B` **字面完全相同**
- 一旦有人把那种值写进 verdict，会被**静默当作变体级 A 级**，污染 goal 阶段统计

### 4.2 建议方案

**Q2=(b) 已裁定**：只做值域守卫，不改名。

#### 4.2.1 值域守卫（无条件先做）

```python
# 守卫键名为现有 tier（不改名）
assert v["tier"] in {"S", "A", "B", "C", "D"}, f"Invalid tier: {v['tier']}"
```

- 与改名解耦，成本低
- 无论是否改名都能防混用
- **守卫键名必须是 `tier`**，不能写 `variant_tier`（否则读不到字段、恒失败）

#### 4.2.2 指纹判断（初稿错误，已纠正）

`variant_tier` 改名**不会触发协议指纹纪律**：
- `docs/fingerprint_component_mapping.md` 定义的 `protocol_fingerprint` 只有七项
- 其中不含任何裁决字段名
- 改名不改 `protocol_fingerprint`，不需 bump 指纹

#### 4.2.3 批次 D（改名）已取消

Q2=(b) → 批次 D 取消 → Q9 不适用。`tier_classifier.py:13` 的表述保留。

---

## 5. E1 经济判决缺失

### 5.1 问题现状

| 证据 | 内容 |
|------|------|
| `reports/phase1/full_universe_neutral_r1_ops/ECONOMIC_VERDICT.json` | **不存在** |
| `config/knowledge_base.json` | 21/21 品种 `evidence_grade = no_evidence` |
| `scripts/l1_economic_verdict.py` | 生成器存在；`:46` `--out` 默认 `ECONOMIC_VERDICT.md` |
| `scripts/build_knowledge_base.py:23` | `DEFAULT_L1` 默认读 `ECONOMIC_VERDICT.json` |
| **默认参数不一致** | 生成器写 `.md`、KB 读 `.json`——与「文件缺失」相互独立的第二个缺陷 |
| 上游 `:42` | `--eligibility` 默认 `reports/phase1/universe_eligibility.json`，**本工作区不存在** |

**证据链三层**：

```
universe_eligibility.json                          ← 本工作区不存在
   ↓ l1_economic_verdict.py --eligibility
ECONOMIC_VERDICT.{json,md}                        ← 两者均不存在
   ↓ build_knowledge_base --l1
knowledge_base.json                                ← 在，但 21/21 no_evidence
```

### 5.2 建议方案

**Q1 已裁定**：先在活仓核实 `universe_eligibility.json`；缺失则 (c) 放弃。

**T2 状态**：已标「**未通过（被 Q1 阻塞）**」——活仓 `reports/phase1/universe_eligibility.json` 不存在，走 (c) 放弃 E1，不放宽判据。

**若活仓也没有**：
- KB 永久 `no_evidence`
- copilot 只能说「经济证据缺失」
- **不为让 `evidence_grade` 好看而放宽判据**
- T2 不阻塞 T1/T3 交付

**若活仓存在**：
- 修扩展名不一致（生成器写 `.md`、KB 读 `.json`）
- 跑生成器 + 重建 KB
- `evidence_grade` 的判据（PF≥1.05/1.20 + EV>0）已实施且不重议

---

## 6. 实施顺序与依赖

### 6.1 裁定依赖图

```
Q7 ──→ Q3            先定脚本定位，才谈调度频率
Q10 ──→ M3 ──→ Q5    窗口定义是 M3 的开工门槛
Q2 ──→ 值域守卫键名    Q2=(b) 已定 → 守卫查 tier
Q1  ──→ E1 全部工作    Q1 已定 → 活仓核实后决定
Q8 / Q6 ──→ D5 孤儿回收  均已裁定
Q4  ──→ 告警           Q4=(b) 已裁定
```

### 6.2 批次顺序（仅 D4/D5/N10/E1）

| 批次 | 内容 | 工作量 | 前置 |
|------|------|--------|------|
| **0** | ~~Q7 裁定~~ **已完成** | — | — |
| **A** | D4 调度 + 维护窗口旗标 + 熔断 | 0.5 天 | Q7✓ Q3✓ Q4✓ |
| **A2** | D5 孤儿兜底（`active_runs.json` + 重启前扫尾） | 1 天 | Q7✓ Q8✓ Q6✓ |
| **B** | N10 值域守卫 | 0.5 天 | Q2✓ |
| **E** | E1 证据链恢复（或放弃） | 1-2 天 | Q1✓；须在主环境核实 |

**并行关系**：A / B 无依赖可并行；A → A2 有严格顺序；E 须在主环境。

**验收提醒**：A / A2 的演练判据按修正后时限（≈27 分钟量级）。

---

## 7. 风险与注意事项

### 7.1 D4 风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 旗标忘删 → 自愈永久失效 | **高** | 4 小时过期 + 过期告警 |
| 重启风暴（连续失败反复 SIGTERM） | **高** | 熔断 3 次 + 退避 |
| 两支看门狗抢着重启 | **中** | Q7=(a) 收编为唯一入口 |
| WSL 重启后调度丢失 | **低** | systemd timer 可设 `Persistent=true`；shell 循环走 `setsid nohup` |

### 7.2 D5 风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| Popen 与写入之间的竞态 → 孤儿无记录 | **中** | 两段式写入（先意图后回填） |
| pid 复用 → 误杀无关进程 | **中** | 记录 pid + 进程创建时刻 |
| 扫尾 kill 误杀他人 run | **中** | Q6=(a) 只回收本 supervisor 派发的 + worktree 路径校验 |
| flock 与 json 不一致 | **低** | flock 优先定性 |

### 7.3 N10 风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 第三套语义混入 → 静默污染统计 | **中** | 值域守卫 |
| 守卫键名写错 → 恒失败 | **低** | 守卫查现有 `tier`，不改名 |

### 7.4 E1 风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 活仓也没有上游 → T2 不通过 | **已知** | 显式标「未通过（被 Q1 阻塞）」，不阻塞 T1/T3 |
| 为凑 T2 而放宽判据 | **中** | §3.3 明确禁止 |

### 7.5 回滚预案

每项变更都必须能退回到「本次变更之前」的状态，且退路是删一个文件 / 禁一个任务：

| 变更 | 停用动作 | 停用后影响 |
|------|----------|------------|
| 调度任务 | 禁用 systemd timer / 杀 shell 循环 | 回到「无自动自愈」现状（即当前生产状态，不更糟） |
| `maintenance.flag` | 删除即恢复自愈 | 过期事件已在日志 |
| 扫尾 kill | 置 `D5_DISABLED=1` 环境旗标 | 回到「不回收孤儿」 |
| 熔断 | 删 `heal_fail.count` 即恢复 | 计数文件保留至人工确认 |

**演练要求**：A / A2 的验收**必须包含一次实际停用再恢复**。

---

## 8. 待宿主裁定事项汇总

以下事项在原始 spec 中已裁定，本调研文档直接引用裁定结果：

| # | 问题 | 裁定 | 来源 |
|---|------|------|------|
| **Q1** | 经济判决上游是否还在 | 活仓核实；缺失则 (c) 放弃，T2 标阻塞 | §10 批准记录 |
| **Q2** | verdict 的 `tier` 是否改名 | **(b) 只做值域守卫，不改名** | §10 批准记录 |
| **Q3** | 调度落点与频率 | **(a) 15 分钟调度** | §10 批准记录 |
| **Q4** | 心跳停更告警通道 | **(b) 日志 + 桌面通知** | §10 批准记录 |
| **Q6** | 孤儿回收清理力度 | **(a) 只回收本 supervisor 派发的 run** | §10 批准记录 |
| **Q7** | `diagnose_three_loop.sh` 定位 | **(a) 收编为唯一自愈入口** | §10 批准记录 |
| **Q8** | 是否改写 `:696` 退出合同 | **(a) 不改，只做硬杀兜底** | §10 批准记录 |
| **Q9** | 裁决行 schema 改名历史兼容 | **不适用**（Q2=b 后无需回答） | §10 批准记录 |

**所有 D4/D5/N10/E1 相关裁定已完成**，可直接进入实施。

---

## 9. 下一步

1. **批次 A**（0.5 天）：实施 D4 调度 + 维护窗口旗标 + 熔断
   - 确定 WSL 内调度方案（systemd timer 优先）
   - 修改 `diagnose_three_loop.sh` 增加维护窗口旗标检查 + 过期逻辑
   - 增加熔断计数 + 退避逻辑
   - 配置告警通道（日志 + 桌面通知）

2. **批次 A2**（1 天）：实施 D5 孤儿兜底
   - 在 `praxist_supervisor.py` 实现两段式写入 `active_runs.json`
   - 在 `diagnose_three_loop.sh` 自愈分支插入扫尾逻辑
   - flock 优先判据 + pid 创建时刻防误杀
   - worktree 路径校验

3. **批次 B**（0.5 天）：实施 N10 值域守卫
   - 在 `aligned_slow_loop.py` 写入 verdict 处加 `assert v["tier"] in {S,A,B,C,D}`
   - 在 `praxist_supervisor.py:1148/1167` 读取处加同样的守卫
   - 单测：混入非法值必须失败

4. **批次 E**（1-2 天）：E1 证据链
   - 在活仓核实 `universe_eligibility.json` 是否存在
   - 存在 → 修扩展名不一致 + 跑生成器 + 重建 KB
   - 不存在 → 放弃 E1，T2 标「未通过（被 Q1 阻塞）」

5. **演练**（+1 天）：
   - 杀 supervisor → 验证 ≈27 分钟内恢复
   - 硬杀 supervisor → 验证孤儿 run 在同一量级内消失
   - 置 maintenance.flag → 验证不误重启 + 过期后自动恢复
   - 触发熔断 → 验证连续 3 次失败后停止自愈
   - 实际停用再恢复 → 验证回滚路径可用

---

## 相关文档

- `specs/2026-10-08-open-issues-closure-spec.md` —— 完整 spec（本调研的源）
- `reports/2026-10-07-tech-debt-inventory.md` —— 输入清单
- `plans/2026-10-07-tech-debt-closure-plan.md` —— 收口总计划
- `docs/runtime_contract.md` —— 运行合同
- `docs/fingerprint_component_mapping.md` —— 协议指纹定义（N10 指纹判断依据）
