# Peer 学习反馈硬化（success_delta 门）T0-T3 Changelog

**Date:** 2026-10-05
**Spec:** docs/superpowers/plans/2026-10-05-peer-learning-feedback-hardening.md（计划 v2）
**Commits:** `4165554`（T0）→ `054de29`（T1）→ `318daca`（T2）→ `739a583`（T2b）→ `2089f1c`（T2c 审计修复）+ `7199738`（计划文档收口）

---

## 一、背景

慢环收割长期存在一个先例不对称：失败侧有 `failure_delta` 增量论证门
（`_has_prior_failure` → `no_failure_delta` 拒收），复测/预注册通道有结构性
豁免（不入 harvest_proposals），但**成功侧没有对应约束**——peer 反复对
已过 `gate_pass=True` 的 (symbol, cov) 组合提交同质复跑提案，挤占 24 品种
×慢环席位，且提案理由多为照抄旧结论，无增量论证。46h 战报
（`reports/2026-10-03-three-loop-v4-operations-report.md`）确认收割入队率
已从 50% 提到 100%，同质复跑成为下一个质量瓶颈。

## 二、变更总览（T0-T3）

| 任务 | Commit | 内容 |
|------|--------|------|
| T0 计划 v2 | `4165554` | 计划文档：门语义、逃逸阀、豁免边界、验收清单 |
| T1 注入通道硬化 | `054de29` | known_verdicts 计数带分母（`30/62 gate_pass` 式）+ 旧协议先验注记（2 组 34 条，仅上下文不进排名） |
| T2 success_delta 门 | `318daca` | harvest_proposals 内 `_success_delta_gate` + aligned_slow_loop 落章 `eval_end_ts` + prompt_base 规则 9/schema 字段 |
| T2b 拒收信息补全 | `739a583` | 拒收日志带先验 vid/分类/run_mode/eval_end_ts（v2-pass 口径 = fdr_pass ∧ p_value ∧ run_mode=confirmation） |
| T2c 审计修复 | `2089f1c` | checkpoint 解码异常面 OSError → (OSError, ValueError)，钉死 fail-open 契约 |

## 三、T2 门设计要点

- **位置**：dedup + PR-B6 之后、family/prescreen 之前——既有 reject 归因不变。
- **匹配口径**：成功侧 (symbol AND cov)——与失败侧 (symbol OR cov) 刻意不同；
  品种或协变量单侧成功不构成挤占席位的重复提案。
- **执法条件**：同组合当前窗已有 ok+gate_pass=True 先验，且复跑缺
  `success_delta`（<20 字）→ 拒收 `no_success_delta`。
- **逃逸阀 fail-open 不用墙钟**：锚 = 全部 ok 行 `eval_end_ts` 最大值
  （行字段优先，checkpoint 兜底 `data/cache/aligned_checkpoints/<vid>.jsonl`
  末行胜出）；`prior_ts != anchor`（窗口平移）或锚不可得 → 放行。
- **豁免边界**：`_maybe_enqueue_retests`/确认通道不入 harvest_proposals
  （毒化测试 `test_retest_bypasses_success_gate_structurally` 钉死）。
- **stats 可观察**：`success_gate_states` 分类计数（enforce / window_moved /
  anchor_unavailable / success_delta_ok），放行侧也计数供观察口径。

## 四、专家审核（2026-10-05，部署后当日）

对 T0-T2b 全部已提交 diff + 部署证据做 9 项核验，8 项通过，1 项确认 P1：

| # | 核验项 | 结论 |
|---|--------|------|
| 1 | new_covariate 提案是否可能误入成功门（cov=None 伪匹配） | ✅ 循环顶部即分流 backlog；空 cov 在 `missing_symbol_or_cov` 先行拒收 |
| 2 | `_row_eval_end_ts` 文件级 `except OSError` 异常面 | ❌ **P1**：UnicodeDecodeError（ValueError 子类）穿透 → 见 T2c |
| 3 | `eval_end_ts` 在 `_run_inner` 的定义先于使用 | ✅ :259 定义，:270/:311 使用，同作用域 |
| 4 | prompt_base.jinja2 可渲染性 | ✅ 渲染冒烟 OK（26728 字符，规则 9 + schema 字段在场） |
| 5 | 主循环异常兜底 | ⚠️ 佐证 P1：`_maybe_harvest` 在 :3831 裸调用（相邻 retests/confirmations 均有 try），门内异常即进程死 |
| 6 | docs 提交数字与冒烟输出一致性 | ✅ 21/28、118 可锚定、2 组 34 行、26h 逐项一致 |
| 7 | stats/缓存键无 None 污染 | ✅ symbol/cov 到门时必为非空串 |
| 8 | T2b 日志与 stats 可 join | ✅ 消息含拒收码 `(no_success_delta)` |
| 9 | 复测/确认结构性豁免维持 | ✅ 毒化测试在位 |

## 五、T2c 修复（P1）

**缺陷链**：checkpoint 含非 UTF-8 字节（崩溃撕裂多字节字符；10-01 WSL VM
回收强杀为实证场景）→ text 迭代器按块解码抛 UnicodeDecodeError →
`except OSError` 不捕 → `_current_window_anchor` → `harvest_proposals` →
主循环裸调用 → **监督环进程死亡**；每次 harvest 重读 checkpoint →
**持续崩溃循环**。违反门 fail-open 设计契约（"门不得破坏 harvest"）。

**修复（最小 diff）**：文件级异常面 `OSError` → `(OSError, ValueError)`。

**语义钉死**（测试 7 两分支）：字节级损坏的 checkpoint = 不可靠证据 →
文件级弃读 → 该行无锚 → `anchor_unavailable` 放行。统一向 fail-open
收敛，不承诺撕裂点前部分读保留（text 按块解码，撕裂波及块内先行行）。

**TDD**：测试 7 先行 RED（UnicodeDecodeError 精确复现审计链路）→ 修复
转绿；test 5 边界补强（恰好 20 字放行，阈值语义 `>=`）。门测试 7/7 +
相邻 harvest 套件 45/45；全量回归 18F+9E=27 与基线**逐项恒等**
（IDENTICAL_FAILURE_SET，node-ID 级 diff 为空），1640 passed（+1 = 新测试）。

## 六、部署证据

- **重启 #1**（T2/T2b 上线）：TERM PID 403 → exit_code 0（uptime 93659.5s
  ≈ 26h）→ 新 PID 77504；首份快照验收全绿。
- **重启 #2**（T2b 上线后例行）：TERM 77504 → exit_code 0（uptime 3197.4s）
  → PID 80450；孤儿批次 batch_de14feb8 自然跑完，裁决由 checkpoint 兜底锚定。
- **重启 #3**（T2c 上线）：TERM 80450 → exit_code 0（uptime 5933.5s）→
  **PID 87698**（run_id 700dab95c528），启动 40s 内完成首 tick 物化
  （generated_at=20:03:04）。
- **fp 恒定**：三次重启 `protocol_fp8=f02b2a43` 不变（评估语义未动）；
  `baseline_metrics.json` 与 HEAD 零 diff（mtime 保持 10-03）——**零基线重生**。
- **慢环孤儿处理**：TERM 不杀慢环（子进程自然跑完），重启间隔内其裁决
  不丢失。

## 七、真实数据冒烟（T2 上线前）

- 118/118 条 v4 裁决行经 checkpoint 兜底全部可锚定（anchor=2026-09-30
  15:00:00），0 条 anchor_unavailable——**部署即生效，无空窗期**。
- 50 个已成功组合：21 个现窗执法 / 28 个窗口平移放行（与"评估窗 10-08
  开闸"的节奏一致；开闸后执法面将扩大）。

## 八、观察项（10-05 → 10-19 两周窗口）

1. **转述带戳**：peer 提案的 success_delta 是否引用具体先验 vid 与窗口
   （而非泛泛而谈）。
2. **拒收分布**：`no_success_delta` 与 `success_gate_states` 计数是否符合
   21/28 初始比例及其演化。
3. **队列健康**：慢环队列无饿死（enforce 不清空供给侧）。
4. **10-08 开闸归因**：若执法面陡增，先查 eval_end_ts 窗口断点再下结论。
5. **T2b 日志**：`success_gate:` 拒收行的先验分类分布（v2-pass vs
   hard-gate-but-losing vs exploration）。
