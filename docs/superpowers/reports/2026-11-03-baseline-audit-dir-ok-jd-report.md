# 基线数据完整性审核报告：dir_ok 不一致 + jd 死循环

> 审核日期：2026-11-02 ~ 2026-11-03
> 审核范围：FM_a 活仓 24 品种基线数据（`task_FM/config/baseline_points_{sym}_nocov.jsonl`）
> 触发：日常三环工作检查 + 用户要求专家审核所有改动
> 审核方式：sonnet scientist agent（数据完整性） + sonnet tracer agent（根因追溯）

---

## 1. 背景

### 1.1 会话起点

2026-11-02 用户要求"检查三环工作情况"。当时发现的初始状态：

| 环 | 状态 | 证据 |
|---|---|---|
| S1 Supervisor | 运行 13h48m | PID 787018，CPU 17.4%，RSS 1.95 GB |
| S2 快环 peer (Praxist) | 运行中 | task run_2026-11-01_22-08-40 |
| S3 慢环 Laya 预筛 | **完全失效** | `data/cache/supervisor.out` 内 **4870 条 503 HTTPError** |
| 衍生问题 | 噪声刷屏 | `scripts/hooks/on_generation_close.py` 不存在，每次 closing 刷 ENOENT |

### 1.2 用户要求

1. "搜索 laya 这个 503 的问题解决方案，之前处理过这个问题的，看来是没有解决？"
2. "用专家调研文件误删的原因，再决定解决方案"
3. "完成后用专家审核所有改动"
4. "基线重生是增量方式吗？不要全量重生，这个以前修改过的"
5. "用专家审核所有基线数据"

本报告覆盖问题 (1)-(5) 的全链路调查与修复。

---

## 2. 调查过程

### 2.1 阶段一：Laya 503 取证

**调查工具**：opus analyst agent

**关键发现**：

```
Git 拓扑：
*   6aadfe9 merge: accept backup data files      ← HEAD，含代码回退
|\
| * dbb68b5 Update baseline configs and cleanup  ← 备份机 root@LAPTOP 08:37
* | 356b885 data: sync runtime data files
* | 510db60 data: commit latest passed covariate verdicts
* | bd3b0b1 docs: update Laya prescreen documentation
|/
* 75b2fa0 fix: use LAYA_WARM_TIMEOUT after successful warmup  ← merge base (P1-P3 最终状态)
* b4933b8 feat: P1-P3 Laya prescreen improvements
```

**决定性证据**：
- `git cat-file -p dbb68b5`：单 parent `75b2fa0`，author `root@LAPTOP-ABUG`，**无 Co-Authored-By**（排除 Claude 自动化）
- `git merge-base 356b885 dbb68b5 = 75b2fa0`：备份机已有 P1-P3 代码，cleanup 主动删了
- `git diff dbb68b5 6aadfe9 -- code files = 0 行`：本机 merge 完全接受了备份侧的代码回退

**根因判定**：**(A) 备份机 root 人工 cleanup 误删 + (B) 本机 merge conflict resolution 错误**

**历史 pattern 复现**：
- 2026-10-29 06:20 `69f28f7`（备份机 cleanup）→ 10-29 06:39 `1380775`（本机手动恢复）
- 2026-11-01 08:37 `dbb68b5`（备份机 cleanup）→ 11-01 11:51 `6aadfe9`（本机 merge 接受）

### 2.2 阶段二：修复（4 commit）

#### Commit 1: `564687a` → 后续 rewrite 为 `54b06c5`

**内容**：从 merge-base `75b2fa0` 恢复被误删文件：
- `cascade/features.py`：`UnsupportedCovariateError`（P0-B fail-fast 自定义异常）
- `scripts/sup_loops.py`：`warmup_laya()` 在慢环入口调用
- `tests/test_enqueue_reprocess.py`、`test_fail_fast_unsupported_covariate.py`
- `docs/superpowers/plans/` 和 `changelogs/`：审计证据链

**注意**：`cascade/typesafe_prescreen.py` **未在此 commit 恢复**（由下一 commit 重新实现）。

#### Commit 2: `279a800` → 后续 rewrite 为 `cf2a149`

**内容**：重新实现 Laya 预筛加固（与 P1-P3 设计不同）：
1. **`LAYA_SKIP_AUTH` 显式开关**：默认 True（Laya 模式 bypass API key）；`false`/`0`/`no` → False 恢复 TypeSafe 鉴权
2. **`warmup_laya` 时间驱动**：总窗口 180s，固定 10s 间隔，覆盖冷启动 122s 实测 + 50% 余量（vs P1-P3 指数退避 3 次 / 6s）
3. **健康检查 GET 探活**：每轮先 GET `/v1/systemone`（1s 超时，405 = 服务活），避免对死服务 POST

#### Commit 3: `7f4e609` → 后续 rewrite 为 `b2c780c`

**内容**：防复发机制
- `.gitattributes`：`cascade/` `scripts/` `tests/` `docs/superpowers/` 声明 `merge=protected-ours`
- `.git/config` 注册 `merge.protected-ours` driver（`driver = true`）
- `docs/BACKUP-MERGE-PROTOCOL.md`：备份机 cleanup 允许范围 + 本机 merge 检查清单

#### Commit 4: `bf3addc`（MINOR 跟进）

**内容**：
- `.gitattributes` 扩展保护范围：`data/*.py`、`task_FM/config/family_registry.jsonl`、`baseline_metrics.json`、`covariate_pool.json`
- `docs/runbook_praxist_three_loop.md` 同步新设计（warmup 时间驱动 + LAYA_SKIP_AUTH 说明）

### 2.3 阶段三：Code Review（sonnet code-reviewer）

**结论**：`PASS_WITH_FOLLOWUP`

**MAJOR finding**：commit `564687a` 的 message 与实际改动不符（声称恢复了 `typesafe_prescreen.py`，实际未恢复）。

**修复**：`git filter-branch --msg-filter` rewrite 两个 commit 的 message：
- `54b06c5 revert: restore P0-B fail-fast + slow-loop warmup/docs (NOT typesafe_prescreen)`
- `cf2a149 harden: Laya prescreen SKIP_AUTH + time-driven warmup + health check (re-impl)`

### 2.4 阶段四：基线全量重生问题

**用户质疑**："基线重生是增量方式吗？不要全量重生"

**调查发现**：`scripts/sup_evidence.py` 的 `ensure_baselines()` 三条路径全部调 `_regen_baseline_with_archive()` → `gbp.generate()`（全量）：

| 路径 | 触发条件 | 当时调用 |
|---|---|---|
| ① | metrics 缺失 / 行数 < 100 | 全量（保持不变） |
| ② | 协议指纹不匹配 | 全量（保持不变） |
| ③ | 基线末端落后 > 168h（占 90%+ 正常运行） | **改增量** |

**修复 commit**：`faa9dba perf: ensure_baselines 路径 ③ (reanchor) 改增量重生`

**新增辅助函数**：`_incremental_or_regen(sym_lower, points_path, root)`
- 先归档旧档
- 调 `incremental_baseline.incremental_generate()`（从 last_cutoff + 2h 续跑）
- 失败时降级到全量重生（保底）

**配套修改**：`incremental_baseline.py` 的 `incremental_generate` 返回值从 `bool` 改为 `new_cutoff`（供 circuit breaker 用）。

### 2.5 阶段五：增量重生 bug（588 点丢失）

**事故现象**：重启后 11 个品种基线被破坏：
- bu/cf/eg/fg/fu/i/jm/m/ma/oi = 47 行（旧 588 点丢失）
- ao = 61 行
- jd = 1 行

**根因**：`scripts/incremental_baseline.py` 写入逻辑
```python
all_points = result.get("points", [])   # ← 只含本轮新算点
for pt in all_points:
    fp.write(...)                        # ← 旧点被丢弃
```

`mb.run_symbol_backtest` 内部用 `resumed_points` 跳过已算点（性能），但返回的 `result["points"]` 只含新点，需外部合并。

**修复 commit**：`4c4d704 fix: incremental_baseline 合并 resumed_points 到写入文件`
- `all_points = resumed_as_points + new_points`
- 写入时按 cutoff 去重（防 overlap）

**数据恢复**：11 个品种从归档复制回 588 行（除 jd 归档本身只有 3 行）。

### 2.6 阶段六：scientist 全面审核

**审核结果**：`PASS_WITH_FOLLOWUP`（23/24 品种通过）

**关键发现**：
1. **jd 仅 3 行**（BLOCK）：归档本身只有 3 行，意味着 jd 历史上就一直残缺
2. **dir_ok 不一致**（MAJOR）：20 个品种 883 行 / 6.2% `dir_ok != (sign(delta_pred) == sign(delta_real))`

### 2.7 阶段七：tracer 追溯 dir_ok 根因

**调查工具**：sonnet tracer agent

**CONFIRMED 根因**：写入 JSONL 的 `delta_pred` 与 `dir_ok` 基于不同定义

| 字段 | 来源 | 定义 |
|---|---|---|
| `delta_pred` | `monthly_backtest.py:506` → `signal_contract.py:93-103` | horizon 加权平均 delta |
| `dir_ok` | `monthly_backtest.py:520` | endpoint delta (`pred[-1] - base`) |

**下游假设**：`evaluation_metrics.py:422` `dir_ok = np.sign(delta_pred) == np.sign(delta_real)`，自然对不上。

**y/px/oi 零不一致的解释**：这三品种不在 `config/prediction_scheme.SCHEMES` 表，`signal_contract.py:63-80` scheme=None 时 `delta_pred = endpoint_delta`，与 `dir_ok` 同源 → 必然一致。

### 2.8 阶段八：jd 死循环分析

**现象**：每次重生都重复
```
[Done] JD 基线生成完成: n=588, dir_acc=0.474
[ERROR] jd 重锚删除了 >= 2026-10-03 的 cutoff ['2026-10-21 ...'] → 已从归档恢复旧档
```

**数据实证**：
- `DataStore('jd').get_main_contract_1h()`：10080 行，2018-07-10 → 2026-11-02（数据完整）
- `_latest_data_dt('jd')` = 2026-11-02 14:00（与 m/ao/rb 同）

**select_eval_indices 实际计算**：
```
CONTEXT_BARS=480, HORIZON=24, STEP=2, EVAL_WINDOW_BARS=1200
jd total=10080, left=8880, right=10055
dt[left]=2025-11-05, dt[right]=2026-10-27
→ 588 indices, first=2025-11-05, last=2026-10-26
```

**真因**：`monthly_backtest.run_symbol_backtest` 内部用 `DataStore.get_main_contract_1h()`，只返回**当前主合约**的 1H 数据。jd 主合约切换到 2026-10-21 交割的新合约，所以重生数据末端 = 2026-10-21（不是数据源的 2026-11-02）。

重生基线 cutoff 范围 = 2025-10-xx ~ 2026-10-21（旧合约尾巴 + 新合约全段）。旧档有 2026-10-03 ~ 2026-10-08 的 cutoff（更早的主合约数据）。守卫检查新档丢失了 10-03~10-08 → 回滚 → jd 永远 3 行。

---

## 3. 原因分析汇总

| 问题 | 根因 | 修复状态 |
|---|---|---|
| Laya 503 刷屏 | `dbb68b5` 备份 cleanup 误删 P1-P3 改进 + 本机 merge 误接受 | ✅ 已修（4 commit + message rewrite） |
| 备份机 cleanup 复发 | 无保护机制，每次 merge 都接受 backup 侧代码回退 | ✅ 已修（`.gitattributes` + 协议文档）|
| 基线全量重生慢 | `ensure_baselines` 路径 ③（占 90%+ 运行）调全量 `gbp.generate` | ✅ 已修（增量优先，失败降级全量）|
| 增量重生后基线丢失 | `incremental_baseline.py` 没合并 `resumed_points` 到写入文件 | ✅ 已修（合并 + cutoff 去重）|
| dir_ok 不一致 6.2% | `monthly_backtest.py:566` 写入加权 delta，但 `dir_ok` 用 endpoint | ⏸ 影响评估中（用户决定） |
| jd 永远 3 行 | 主合约切换导致重生数据跨不过合约边界 + 守卫回滚 | ⏸ 用户决定先不处理 |

---

## 4. 关键代码位置

| 文件 | 关键函数/行 | 作用 |
|---|---|---|
| `scripts/sup_evidence.py` | `ensure_baselines()` (1479-1607) | 基线完整性检查 + 重生触发 |
| `scripts/sup_evidence.py` | `_incremental_or_regen()` (1425-1448) | 路径 ③ 增量优先入口 |
| `scripts/sup_evidence.py` | `_guard_confirm_from_ts_after_regen()` (1378) | v9 修订② 守卫 |
| `scripts/incremental_baseline.py` | `incremental_generate()` (36-126) | 增量重生主体 |
| `scripts/monthly_backtest.py` | `run_symbol_backtest()` (295) | 单品种回测 |
| `scripts/monthly_backtest.py` | `select_eval_indices()` (267) | 评估点选择 |
| `scripts/monthly_backtest.py` | line 506 / 518 / 520 / 566 | dir_ok 不一致根因位置 |
| `cascade/signal_contract.py` | 63-80 / 93-103 | scheme=None vs 加权 delta_pred |
| `cascade/typesafe_prescreen.py` | `_parse_laya_skip_auth()` / `warmup_laya()` / `_prescreen_impl()` | Laya 加固 |
| `cascade/evaluation_metrics.py` | 422 | 下游 `dir_ok = sign(delta_pred) == sign(delta_real)` |
| `config/backtest_config.py` | 51-58 | CONTEXT_BARS=480, HORIZON=24, EVAL_WINDOW_BARS=1200 |

---

## 5. Commit 链

```
4c4d704 fix: incremental_baseline 合并 resumed_points 到写入文件       ← 增量 bug 修复
faa9dba perf: ensure_baselines 路径 ③ (reanchor) 改增量重生             ← 增量重生集成
bf3addc follow-up: extend protected-ours to data/config.py + update runbook
b2c780c chore: add .gitattributes protected-ours driver + backup merge protocol
cf2a149 harden: Laya prescreen SKIP_AUTH + time-driven warmup + health check (re-impl)
54b06c5 revert: restore P0-B fail-fast + slow-loop warmup/docs (NOT typesafe_prescreen)
6aadfe9 merge: accept backup data files (newer runtime data)            ← 事故 merge
```

---

## 6. 运维验证

### 6.1 Supervisor 状态（2026-11-02 重启后）

- 新 PID：914705（已启动，运行正常）
- 重启后 503 错误：**0 条**（vs 重启前 4870 条）
- 增量重生生效：
  ```
  [INFO] AO 合并: 588 旧点 + 63 新点 = 651 点
  [INFO] AO 写入 651 个唯一 cutoff 点
  [DONE] AO 基线已更新, new_cutoff=2026-10-28 23:00:00
  ```

### 6.2 基线数据完整性（24 品种）

| 项 | 状态 |
|---|---|
| 行数 | 23/24 品种 ≥ 588 ✅ |
| jd | 3 行 ⚠️（历史遗留，待处理） |
| 协议指纹 | 全部匹配 v4 `f02b2a433fd5...` ✅ |
| cutoff 单调 | 24/24 ✅ |
| 重复 cutoff | 0 ✅ |
| JSON 解析 | 0 错误 ✅ |
| dir_ok 不一致 | 883 行 / 6.2%（20 品种）⚠️（根因已确认，待修复）|

### 6.3 待人工处理项

1. **备份机 merge driver 注册**（SSH 被拒，需用户在 `chong@100.96.19.116` 手动执行）：
   ```bash
   cd /root/timesfm
   git config merge.protected-ours.name 'protected: keep current-branch version on conflict'
   git config merge.protected-ours.driver true
   ```

2. **dir_ok 修复决策**（影响评估进行中，待用户决策）

3. **jd 重生决策**（用户选择先不处理）

---

## 7. 附录：验证命令清单

```bash
# 503 错误统计（新 supervisor 启动后）
NEWSTART=$(grep -n 'Supervisor launched: PID 914705' data/cache/supervisor.out | tail -1 | cut -d: -f1)
tail -n +$NEWSTART data/cache/supervisor.out | grep -cE '503 Server Error'

# 增量重生进度
tail -n +$NEWSTART data/cache/supervisor.out | grep -E '合并:|写入.*唯一|基线已更新|降级到全量'

# 24 品种基线行数
wc -l task_FM/config/baseline_points_*_nocov.jsonl

# 当前协议指纹
.venv/bin/python -c "import sys; sys.path.insert(0, 'task_FM/evaluations/fm_eval'); \
  from evaluator import compute_protocol_fingerprint; print(compute_protocol_fingerprint())"

# dir_ok 不一致率（每品种）
.venv/bin/python -c "
import json, numpy as np, glob
for fn in sorted(glob.glob('task_FM/config/baseline_points_*_nocov.jsonl')):
    sym = fn.split('baseline_points_')[1].split('_nocov')[0]
    with open(fn) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    incon = sum(1 for pt in lines if pt['dir_ok'] != (bool(np.sign(pt['delta_pred']) == np.sign(pt['delta_real'])) if abs(pt['delta_real']) > 1e-8 else False))
    print(f'{sym:3s}: n={len(lines)}, incon={incon} ({incon/len(lines)*100:.1f}%)')
"

# jd 数据末端
.venv/bin/python -c "
import sys; sys.path.insert(0, 'scripts')
import sup_state
for sym in ['m', 'ao', 'jd', 'rb']:
    print(f'{sym}: latest_data_dt={sup_state._latest_data_dt(sym)}')
"

# jd select_eval_indices 实际计算
.venv/bin/python -c "
import sys; sys.path.insert(0, 'scripts'); sys.path.insert(0, '.')
from data.data_store import DataStore
from config.backtest_config import CONTEXT_BARS, HORIZON, STEP, EVAL_WINDOW_BARS
import pandas as pd
from scripts.monthly_backtest import select_eval_indices
for sym in ['jd', 'm']:
    store = DataStore(sym)
    h1 = store.get_main_contract_1h(limit=99999)
    store.close()
    total = len(h1)
    left = max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)
    right = total - HORIZON - 1
    dts = pd.to_datetime(h1['dt'])
    idx = select_eval_indices(dts.tolist(), eval_start_ts=None, max_points=None)
    print(f'{sym}: total={total}, left={left} dt={dts.iloc[left]}, right={right} dt={dts.iloc[right]}, n_eval={len(idx)}')
"
```

---


---

## 8. 报告元信息

- **作者**：opus analyst（取证）+ sonnet code-reviewer（审核）+ sonnet scientist（数据审核）+ sonnet tracer（根因追溯）+ 主 session 协调
- **时长**：~8 小时（2026-11-02 08:00 ~ 16:00）
- **commits**：6 个修复 commit + 3 次 message rewrite
- **测试**：43/43 passed（39 prescreen + 4 fail-fast）
- **报告路径**：`/home/abug/timesfm/docs/superpowers/reports/2026-11-03-baseline-audit-dir-ok-jd-report.md`
- **Windows 路径**：`\\wsl.localhost\Ubuntu-22.04\home\abug\timesfm\docs\superpowers\reports\2026-11-03-baseline-audit-dir-ok-jd-report.md`

---

## 9. delta_pred 加权→endpoint 变更：下游影响评估

> 评估者：sonnet analyst agent
> 评估时间：2026-11-03

### 9.1 影响总结

**影响：中等（M）**。6.25% 的行（883/14138）存在 `delta_pred`（加权）与 `dir_ok`（endpoint）符号不一致。修复影响 PF/EV/MaxDD 等经济指标的数值（因 `metrics_from_backtest_points` 读 `delta_pred` 符号决定持仓方向），但**不影响 dir_acc**（由 `calc_prediction_quality` 独立从 `pred_end` 重算）。影响幅度在品种级别差异大：p/cf/cj 约 10-13%，oi/px/y 为 0%。

### 9.2 受影响代码路径

| file:line | 用途 | 依赖类型 | 改后影响 |
|---|---|---|---|
| `cascade/evaluation_metrics.py:192` | `metrics_from_backtest_points`：`dirs = np.sign(p["delta_pred"])` → PF/EV/MaxDD | 直接读 JSONL delta_pred | **中**：6.25% 点翻转持仓方向 |
| `cascade/evaluation_metrics.py:414-425` | `calc_prediction_quality`：dir_acc | **不读 JSONL**，自己从 pred_end 重算 | **无** |
| `scripts/monthly_backtest.py:566` | 写入 JSONL `delta_pred` 字段 | 写入端 | 源头修复 |
| `scripts/generate_baseline_points.py:151` | 写入基线 JSONL `delta_pred` | 透传 `mb.run_symbol_backtest` 返回值 | **自动生效**（源头修复后无需改） |
| `scripts/incremental_baseline.py:120` | 增量基线写入 `delta_pred` | 透传 `mb.run_symbol_backtest` 返回值 | **自动生效**（源头修复后无需改） |
| `scripts/short_variety_diagnostic.py:174` | PF12 计算：`sign = np.sign(p["delta_pred"])` | 读 JSONL | 中 |
| `scripts/batch_backtest.py:60` | 独立批回测 | 已用端点 `pred[-1] - base` | **[DEPRECATED] 已对齐** |
| `cascade/neutral_ab_report.py:301` | `n_active_from_points`：`abs(delta_pred) > EPS` | 读绝对值 | 极小 |
| `cascade/vol_gating_replay.py:108,119` | Vol gating on/off 对比 | 读 points | 小 |
| `scripts/sup_harvest.py` | 慢环收割 | **不读 delta_pred** | 无 |

### 9.3 分品种翻转率明细（按翻转率降序）

| 品种 | 行数 | 翻转数 | 翻转率 |
|---|---|---|---|
| p | 588 | 76 | **12.93%** |
| cf | 637 | 70 | **10.99%** |
| cj | 591 | 63 | **10.66%** |
| lh | 591 | 53 | 8.97% |
| sp | 588 | 49 | 8.33% |
| m | 637 | 51 | 8.01% |
| sh | 588 | 47 | 7.99% |
| ss | 588 | 44 | 7.48% |
| eg | 637 | 44 | 6.91% |
| fu | 637 | 44 | 6.91% |
| bu | 637 | 43 | 6.75% |
| jm | 637 | 43 | 6.75% |
| i | 637 | 39 | 6.12% |
| rb | 588 | 36 | 6.12% |
| ao | 651 | 38 | 5.84% |
| ta | 588 | 33 | 5.61% |
| fg | 637 | 31 | 4.87% |
| ma | 637 | 31 | 4.87% |
| ur | 591 | 26 | 4.40% |
| sr | 637 | 22 | 3.45% |
| oi | 637 | 0 | 0.00% |
| px | 588 | 0 | 0.00% |
| y | 588 | 0 | 0.00% |
| jd | 3 | 0 | 0.00% |

### 9.4 受影响统计指标

| 指标 | 影响幅度 | 说明 |
|---|---|---|
| **dir_acc** | **无** | `calc_prediction_quality` 从 pred_end 独立计算 |
| **PF** | **中（1-5%）** | 翻转点 gross 符号反转 |
| **EV** | **中（1-5%）** | 翻转点 net 均值偏移 |
| **MaxDD** | **中（1-5%）** | 翻转点改变 equity curve |
| **WinRate** | **中** | 翻转点胜负反转 |
| **endpoint_mape/bias** | **无** | 独立计算 |
| **慢环收割** | **无** | 不读 delta_pred |

### 9.5 重生成本

- 每品种 1-3 分钟
- 24 品种总计 30-60 分钟（3 个零翻转品种可跳过，实际 21 品种 25-50 分钟）
- 重生期间慢环**不受影响**：慢环读基线只用于 `baseline_dir_acc` 和 DM test，都不依赖 `delta_pred`
- 基线重生是原子替换（temp file → rename）

### 9.6 推荐方案（adversarial-reviewer 修订版）

> 修订来源：adversarial-reviewer opus 审核（2026-11-03），原报告声称需改 3 个文件，实际只需 **1 个文件 1 行**。

**方案 A（推荐）：修复 + 重生**

1. **修改 `monthly_backtest.py:566`**：`float(delta_pred)` → `float(_delta_pred_endpoint)`（唯一源头）
2. ~~`generate_baseline_points.py:151`~~ 不需改（透传 `mb.run_symbol_backtest` 返回值）
3. ~~`short_variety_diagnostic.py:332`~~ 不需改（非基线管道，是独立诊断工具）
4. 重生 21 个受影响品种（跳过 oi/px/y/jd）
5. 不需要暂停慢环（`sup_harvest.py` 不读 delta_pred）

**执行顺序**：
1. 改代码 → 跑单品种测试（选翻转率最高的 `p`）确认修复正确
2. 分批重生：先 3 个高翻转率品种（p/cf/cj）验证 → 确认无误后批量剩余 18 个
3. 全量一致性终验：24 品种应 0 不一致行
4. 不需要在重启 supervisor 前完成（`ensure_baselines` 路径③ 增量触发会自动处理）
5. 重生不会触发 ensure_baselines 守卫回滚（重生后行数 ≥ 旧档，protocol_fingerprint 不变）

**理由**：
- 修复成本低（**1 行代码变更**）
- 重生成本可控（25-50 分钟，增量模式）
- 修复后 delta_pred 与 dir_ok 语义一致，消除 6.25% 的逻辑矛盾
- PF/EV/MaxDD 数值更准确（与经济含义对齐：持仓方向 = endpoint 方向）

**不推荐方案 B（不修复）**：6.25% 不一致率意味着 PF/EV/MaxDD 持续系统性偏差，p/cf/cj 超过 10% 影响品种评级和 gate 决策。

**不推荐方案 C（仅修代码不重生）**：新旧数据混合导致 PF/EV/MaxDD 时间序列不可比。

### 9.7 历史 verdicts 可比性（adversarial-reviewer 补充）

已落库的 `aligned_verdicts.jsonl` 包含基于加权 `delta_pred` 的 PF/EV/MaxDD 计算结果。
修复后新 verdict 使用端点 `delta_pred`，两者数值**不可直接对比**。

**预期影响**：
- 翻转率高的品种（p 12.9%、cf 11.0%、cj 10.7%）的 verdict PF/EV 会有可感知偏移
- 翻转率低的品种（sr 3.5%、ur 4.4%）偏移较小
- dir_acc **不受影响**（独立计算）

**处理建议**：
- 偏移属**预期行为**（修正当初的语义错误），无需 recompute 历史
- 如需对齐历史趋势线，可选 recompute 受影响品种的 verdicts（成本较高）
- 报告 §6.2 应补充说明这一变更

### 9.8 验证命令清单（adversarial-reviewer 补充）

```bash
# Step 0: 修改前基线（记录不一致率）
.venv/bin/python -c "
import json, glob, numpy as np
for fn in sorted(glob.glob('task_FM/config/baseline_points_*_nocov.jsonl')):
    sym = fn.split('baseline_points_')[1].split('_nocov')[0]
    with open(fn) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    incon = sum(1 for pt in lines if pt['dir_ok'] != (
        bool(np.sign(pt['delta_pred']) == np.sign(pt['delta_real']))
        if abs(pt['delta_real']) > 1e-8 else False))
    print(f'{sym:3s}: {len(lines):4d} pts, {incon:3d} incon ({incon/max(1,len(lines))*100:.1f}%)')
"

# Step 1: 改代码后单品种验证（p 翻转率最高）
.venv/bin/python -c "
from scripts.incremental_baseline import incremental_generate
result = incremental_generate('p')
print(f'p regenerated: {result}')
"

# Step 2: 验证 p 一致性（应 0 不一致）
.venv/bin/python -c "
import json, numpy as np
fn = 'task_FM/config/baseline_points_p_nocov.jsonl'
with open(fn) as f:
    lines = [json.loads(l) for l in f if l.strip()]
incon = sum(1 for pt in lines if pt['dir_ok'] != (
    bool(np.sign(pt['delta_pred']) == np.sign(pt['delta_real']))
    if abs(pt['delta_real']) > 1e-8 else False))
print(f'p: incon={incon} (expected 0)')
assert incon == 0, f'Still {incon} inconsistent rows'
print('PASS: delta_pred now consistent with dir_ok')
"

# Step 3: 验证 protocol_fingerprint 不变（应输出 f02b2a433fd5...）
.venv/bin/python -c "
from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint
print(compute_protocol_fingerprint())
"

# Step 4: 批量重生剩余 20 品种
.venv/bin/python -c "
from scripts.incremental_baseline import incremental_generate
for sym in ['cf','cj','lh','sp','m','sh','ss','eg','fu','bu','jm','i','rb','ao','ta','fg','ma','ur','sr']:
    r = incremental_generate(sym)
    print(f'{sym}: {r}')
"

# Step 5: 全量一致性终验
.venv/bin/python -c "
import json, glob, numpy as np
total_incon = 0
for fn in sorted(glob.glob('task_FM/config/baseline_points_*_nocov.jsonl')):
    sym = fn.split('baseline_points_')[1].split('_nocov')[0]
    with open(fn) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    incon = sum(1 for pt in lines if pt['dir_ok'] != (
        bool(np.sign(pt['delta_pred']) == np.sign(pt['delta_real']))
        if abs(pt['delta_real']) > 1e-8 else False))
    total_incon += incon
    if incon > 0:
        print(f'FAIL {sym}: incon={incon}')
if total_incon == 0:
    print(f'ALL 24 VARIETIES PASS: 0 inconsistent rows')
else:
    print(f'FAIL: {total_incon} total inconsistent rows')
"
```
