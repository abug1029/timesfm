# S1: praxist_supervisor.py 模块拆分 SPEC

| 字段 | 值 |
|------|-----|
| **ID** | S1（新 S 系列：结构性重构；与已关闭的 **M5「n_eff 常数函数」** 完全不同——M5 已于 2026-10-07 溯源结案，见 `docs/superpowers/reports/2026-10-07-tech-debt-inventory.md:47`） |
| **日期** | 2026-10-09 |
| **版本** | v2.0（修订版，v1.0 经 expert review Reject as-is 后重写） |
| **作者** | Architect Agent |
| **状态** | Draft → 待实施 |
| **前置依赖** | D4/D5（已完成） |
| **目标文件** | scripts/praxist_supervisor.py（4574 行） |
| **风险等级** | 高（核心运行时，32 个测试文件引用） |

---

## 1. 现状分析

### 1.1 文件概况

| 指标 | 值 |
|------|-----|
| 总行数 | 4574 |
| 函数总数 | 160（124 private + 36 public） |
| 类数 | 0 |
| 测试引用 | **32 个测试文件**引用 `praxist_supervisor`（其中 test_supervisor.py 独占 1873 行 / 155 次 sup. 调用） |
| 外部导入 | registry_lib, goal_dsl, cascade.cov_family, cascade.experiment_fingerprint, search_trees, search_promote, cascade.statistical_tests |

### 1.2 功能分区扫描

通过对 160 个函数的行号分布、调用关系和职责分析，识别出以下 10 个逻辑域：

| 域 | 行号范围 | 函数数 | 职责 |
|----|----------|--------|------|
| A. FDR 与持久化 | 28-59 | 2 | fdr_pass_persistable, promote_batch_for_persistence |
| B. Praxist 二进制解析 | 60-82 | 2 | _resolve_praxist_bin, _praxist_bin, _praxist |
| C. 环境与配置 | 95-191 | 2 | _load_dotenv, _check_required_env |
| D. 研究家族管理 | 192-428 | 10 | family_key_for, register_family_member, dispatch_confirmation, finalize_confirmation 等 |
| E. 预注册与确认队列 | 332-620 | 8 | due_confirmations, confirmation_queue_row, _maybe_enqueue_confirmations 等 |
| F. 事件/信号/生命周期 | 621-758 | 9 | _emit_event, _write_heartbeat, _signal_handler, _shutdown_exit 等 |
| G. 状态/目标/符号 | 764-897 | 9 | load_state, save_state, load_goal, _goal_target_symbols 等 |
| H. LLM Provider 与 Failover | 897-1060 | 12 | _failover_configured, _llm_provider, _praxist_env, _model_argv 等 |
| I. 配额/预算/Token | 1061-1120, 3088-3180 | 11 | quota_gate, _read_cpu_hours, _token_budget_hit 等 |
| J. 快照/证据物化 | 1121-1743 | 20 | build_snapshot, materialize_known_verdicts, load_covariate_pool 等 |
| K. 提案收割与评分 | 1812-2150, 2631-2914 | 25 | harvest_proposals, _proposal_priority_score, _proposal_quality_gate 等 |
| L. 成功门/数据就绪 | 2375-2630 | 12 | _row_eval_end_ts, _current_window_anchor, _symbol_data_stale 等 |
| M. N/Step/Retest | 2915-3087 | 8 | _valid_n_for_symbol, plan_sample_retests, _log_decision |
| N. 快环决策 | 3224-3523 | 3 | decide_fast_loop, write_stop_report |
| O. 主循环/入口 | 3524-4574 | 15+ | main, _main_locked, _maybe_harvest, ensure_baselines 等 |

> 注：域 D（192-428）与域 E（332-620）行号有重叠——两域在确认队列函数上交叉，拆分时以职责边界为准，不以行号硬切割。

### 1.3 模块间依赖关系

main() 调用 _main_locked()，后者协调以下功能域：
- 状态加载（load_state, load_goal）→ 域 G
- 预算计量（_read_cpu_hours, _token_budget_hit）→ 域 I
- 快照构建（build_snapshot）→ 域 J
- 收割调度（_maybe_harvest, _harvest_rows）→ 域 O
- 提案入队（_maybe_enqueue_confirmations）→ 域 E
- 快环决策（decide_fast_loop）→ 域 N+H+I
- 慢环管理（_maybe_start_slow_loop, _maybe_finish_slow）→ 域 O
- 事件/信号（_emit_event, _sleep_interruptible）→ 域 F

### 1.4 痛点

1. 4574 行单文件，定位功能需扫描全文件
2. 测试 monkeypatch 负担重：1873 行 test_supervisor.py 中 155 次 sup.X 调用
3. 全局路径变量集中定义（QUEUE, INPROGRESS, REGISTRY, STATE_PATH 等）
4. 交叉引用密集：decide_fast_loop 调用 provider 和 quota 域；_main_locked 调用几乎所有域

---

## 2. 目标架构

### 2.1 设计原则

1. 向后兼容第一：import praxist_supervisor as sup 后所有 36 个 public 函数可用
2. 零运行时依赖变更：不引入新包，不改变启动顺序
3. 可回滚：每次迁移一个域，单 commit 可 git revert
4. 内聚 > 行数均衡：按职责边界拆，不追求文件大小均匀
5. 常量集中：所有路径常量收拢到单一 sup_paths.py

### 2.2 目标模块图

```
scripts/
  praxist_supervisor.py        # 入口 + re-export shim (<200 行)
  sup_paths.py                 # 路径常量 + FM_ROOT (~40 行)
  sup_env.py                   # 环境加载 + Praxist 二进制 (~100 行)
  sup_state.py                 # 状态/目标/符号 (~150 行)
  sup_lifecycle.py             # 事件/信号/心跳/停机 + _log_decision (~180 行)
  sup_provider.py              # LLM provider + failover (~180 行)
  sup_harvest.py               # 提案收割 + 评分 + 质量门 (~500 行)
  sup_evidence.py              # 快照构建 + 证据物化 + baseline + VALID_TIER_VALUES + is_valid_tier (~620 行)
  sup_family.py                # 研究家族 + 确认队列 + FDR (~300 行)
  sup_loops.py                 # 快环决策 + 慢环 + 主循环 (~680 行)
```

### 2.3 模块职责

#### sup_paths.py (~40 行)
所有路径常量：FM_ROOT, HERE, QUEUE, INPROGRESS, REGISTRY, STATE_PATH, LOCK_PATH, VERDICTS_INC, POOL_PATH, BACKLOG_PATH, SYMBOL_STATUS_PATH, MENU_INC, REPORT_DIR, SEARCH_COMMITMENTS_PATH
依赖：os（stdlib）| 被依赖：所有其他模块

#### sup_env.py (~100 行)
_load_dotenv(), _check_required_env(), _resolve_praxist_bin(), _praxist_bin(), _praxist()
依赖：sup_paths | 被依赖：sup_loops, sup_provider

#### sup_state.py (~150 行)
load_state(), save_state(), load_goal(), _goal_target_symbols(), _assert_goal_symbols_contract(), _merge_save(), _cad_int(), _norm_search_policy()
依赖：sup_paths, yaml, json | 被依赖：几乎所有模块

#### sup_lifecycle.py (~180 行)
_emit_event(), _write_heartbeat(), _signal_handler(), _shutdown_exit(), _sleep_interruptible(), _atexit_handler(), _arm_handlers(), _mark_stop_emitted(), _write_stop_json(), parse_429_reset(), **_log_decision()**（横切日志函数，从域 M 移入此处，见 C3 修正），_SHUTDOWN_REQUESTED, _START_TIME
依赖：sup_paths | 被依赖：sup_loops, sup_harvest, sup_family, sup_evidence（通过 _log_decision 横切调用）

#### sup_provider.py (~180 行)
_failover_configured(), _llm_provider(), _llm_route(), _praxist_env(), _failover_model_name(), _failover_can_resume_same_run(), _model_argv(), _provider_state(), _run_active(), _active_run_meta(), _latest_429_reset()
依赖：sup_paths, sup_state, sup_env | 被依赖：sup_loops

#### sup_harvest.py (~500 行)
harvest_proposals(), harvest_survivors(), _proposal_priority_score(), _proposal_quality_gate(), _sector_filter_check(), _covariate_filter_check(), _success_delta_gate(), _prescreen_async(), _cross_run_repeat_counts(), _append_backlog(), collect_proposed_variant_ids(), materialize_covariate_menu()
依赖：sup_paths, sup_state, sup_evidence, sup_lifecycle, search_trees, search_promote, registry_lib | 被依赖：sup_loops

#### sup_evidence.py (~620 行)
build_snapshot(), materialize_known_verdicts(), load_covariate_pool(), load_symbol_status(), ensure_baselines()（跨域移动：原域 O → 此处）, _baseline_protocol_fingerprint(), _current_protocol_fingerprint(), _archive_baseline_before_regen(), _valid_n_for_symbol()（跨域移动：原域 M → 此处）, _experiment_fp_for(), symbol_goal_tier(), _row_eval_end_ts(), _current_window_anchor(), _today_shanghai(), _kline_1h_max_dt(), _symbol_data_stale(),
**VALID_TIER_VALUES**（从域 A 移入此处，见 C3 修正）,
**is_valid_tier()**（从 build_snapshot 嵌套函数提升为模块级，见 C4）
依赖：sup_paths, sup_state, sup_lifecycle, registry_lib, goal_dsl, cascade.* | 被依赖：sup_harvest, sup_loops

#### sup_family.py (~300 行)
family_key_for(), family_for(), register_family_member(), seal_research_family(), dispatch_confirmation(), finalize_confirmation(), load_family_members(), save_family_members(), due_confirmations(), confirmation_queue_row(), load_preregistry(), fdr_pass_persistable(), promote_batch_for_persistence(), _maybe_enqueue_confirmations(), _finalize_confirmation_verdict()
依赖：sup_paths, sup_state, sup_lifecycle, registry_lib, cascade.cov_family, cascade.experiment_fingerprint | 被依赖：sup_loops

#### sup_loops.py (~680 行)
main(), _main_locked(), decide_fast_loop(), write_stop_report(), _maybe_harvest(), _harvest_rows(), _maybe_start_slow_loop(), _maybe_finish_slow(), wait_for_batch(), cleanup_batch_workers(), ensure_phase(), plan_sample_retests(), _maybe_enqueue_retests(), quota_gate(), _commit_search_accepts(), _sweep_search_stops(), _sweep_search_promotions(), _read_cpu_hours(), _read_token_m(), _token_spend_m(), _token_budget_hit(), _in_slow_window(), _deadline_passed(), _slow_loop_alive(), _queue_busy(), _slow_drain_complete()
依赖：所有其他 sup_* 模块 + search_promote, registry_lib, goal_dsl | 被依赖：无（顶层入口）

### 2.4 向后兼容层

praxist_supervisor.py 缩减为 re-export shim（约 120-180 行）：

```python
#!/usr/bin/env python3
from sup_paths import FM_ROOT, HERE, QUEUE, INPROGRESS, REGISTRY, STATE_PATH, LOCK_PATH, VERDICTS_INC, POOL_PATH, BACKLOG_PATH, SYMBOL_STATUS_PATH, MENU_INC, REPORT_DIR, SEARCH_COMMITMENTS_PATH
from sup_env import _load_dotenv, _check_required_env, _praxist, _PRAXIST
from sup_state import load_state, save_state, load_goal, _merge_save, _goal_target_symbols, _assert_goal_symbols_contract, _cad_int, _norm_search_policy
from sup_lifecycle import _emit_event, _write_heartbeat, _signal_handler, _shutdown_exit, _sleep_interruptible, _atexit_handler, _arm_handlers, _mark_stop_emitted, _write_stop_json, parse_429_reset, _log_decision, _SHUTDOWN_REQUESTED, _START_TIME
from sup_provider import _failover_configured, _llm_provider, _llm_route, _praxist_env, _failover_model_name, _failover_can_resume_same_run, _model_argv, _provider_state, _run_active, _active_run_meta, _latest_429_reset
from sup_harvest import harvest_proposals, harvest_survivors, _proposal_priority_score, _proposal_quality_gate, _sector_filter_check, _covariate_filter_check, _success_delta_gate, _prescreen_async, _cross_run_repeat_counts, _append_backlog, collect_proposed_variant_ids, materialize_covariate_menu
from sup_evidence import build_snapshot, materialize_known_verdicts, load_covariate_pool, load_symbol_status, ensure_baselines, symbol_goal_tier, _valid_n_for_symbol, _experiment_fp_for, _symbol_n_table, _baseline_protocol_fingerprint, _current_protocol_fingerprint, _row_eval_end_ts, _current_window_anchor, _today_shanghai, _kline_1h_max_dt, _symbol_data_stale, _prior_success_class, _prior_success_row, _locked_success_rows, _locked_window_lines, VALID_TIER_VALUES, is_valid_tier
from sup_family import family_key_for, family_for, register_family_member, seal_research_family, dispatch_confirmation, finalize_confirmation, load_family_members, save_family_members, due_confirmations, confirmation_queue_row, load_preregistry, fdr_pass_persistable, promote_batch_for_persistence, _maybe_enqueue_confirmations, _finalize_confirmation_verdict, _requested_covariate, _confirmation_is_final, _confirm_data_ready, _merge_family_members, _stamp_member, _seal_if_all_terminal, _dead_families, _is_confirmable_failure, _PERSISTABLE_DM
from sup_loops import main, decide_fast_loop, write_stop_report, ensure_phase, quota_gate, _main_locked, _maybe_harvest, _harvest_rows, _maybe_start_slow_loop, _maybe_finish_slow, wait_for_batch, cleanup_batch_workers, plan_sample_retests, _maybe_enqueue_retests, _append_jsonl, _read_cpu_hours, _read_token_m, _token_spend_m, _token_budget_hit, _ensure_tokens_baseline, _in_slow_window, _deadline_passed, _slow_loop_alive, _queue_busy, _slow_drain_complete, _retest_candidates, _active_protocol_snapshot

__all__ = [
    "main", "decide_fast_loop", "write_stop_report", "ensure_phase",
    "quota_gate", "build_snapshot", "harvest_proposals", "harvest_survivors",
    "materialize_known_verdicts", "materialize_covariate_menu",
    "collect_proposed_variant_ids", "load_covariate_pool", "load_symbol_status",
    "load_state", "save_state", "load_goal", "load_preregistry",
    "load_family_members", "save_family_members",
    "family_key_for", "family_for", "register_family_member",
    "seal_research_family", "dispatch_confirmation", "finalize_confirmation",
    "due_confirmations", "confirmation_queue_row",
    "fdr_pass_persistable", "promote_batch_for_persistence",
    "parse_429_reset", "ensure_baselines", "symbol_goal_tier",
    "plan_sample_retests", "wait_for_batch", "cleanup_batch_workers",
    "is_valid_tier", "VALID_TIER_VALUES",
    "FM_ROOT", "HERE", "QUEUE", "INPROGRESS", "REGISTRY", "STATE_PATH",
    "LOCK_PATH", "VERDICTS_INC", "POOL_PATH", "BACKLOG_PATH",
    "SYMBOL_STATUS_PATH", "MENU_INC", "REPORT_DIR", "SEARCH_COMMITMENTS_PATH",
    "_SHUTDOWN_REQUESTED", "_START_TIME", "_PRAXIST", "_PERSISTABLE_DM",
]

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

---

## 3. 拆分方案

### 3.0 迁移步骤 0（C4 前置：提升 is_valid_tier 为模块级函数）

在正式拆分前，先将 `is_valid_tier` 从 `build_snapshot` 内部（行 1150）提升为模块级函数。此步骤是纯机械重构：

```python
# 当前（嵌套函数，:1150）:
def build_snapshot(...):
    def is_valid_tier(v):
        return isinstance(v, dict) and v.get("tier") in VALID_TIER_VALUES

# 提升后（模块级）:
def is_valid_tier(v):
    return isinstance(v, dict) and v.get("tier") in VALID_TIER_VALUES

def build_snapshot(...):
    # 直接引用模块级 is_valid_tier，行为不变
```

| 操作 | 验证 | 回滚 |
|------|------|------|
| 单 commit：提升 is_valid_tier 到模块级 + 全量测试 | pytest tests/ -x -q | git revert |

### 3.1 迁移步骤（10 步 + 步骤 0）

| 步骤 | 操作 | 验证 | 回滚 |
|------|------|------|------|
| **0** | 提升 is_valid_tier 为模块级函数（C4 前置） | pytest tests/ -x -q | git revert |
| 1 | 创建 sup_paths.py | pytest tests/ -x -q | git revert |
| 2 | praxist_supervisor.py 中 from sup_paths import 替换路径 | 同上 | 同上 |
| 3 | 创建 sup_env.py | 同上 | 同上 |
| 4 | 创建 sup_state.py | 同上 | 同上 |
| 5 | 创建 sup_lifecycle.py | 同上 | 同上 |
| 6 | 创建 sup_provider.py | 同上 | 同上 |
| 7 | 创建 sup_evidence.py | 同上 | 同上 |
| 8 | 创建 sup_harvest.py | 同上 | 同上 |
| 9 | 创建 sup_family.py | 同上 | 同上 |
| 10 | 创建 sup_loops.py + shim 化 | 全量 32 个测试文件 | 同上 |

### 3.2 跨模块依赖 DAG（修正版，C3 修正后无环）

```
sup_paths ← sup_env, sup_state, sup_lifecycle
  |             |           |           |
  |      sup_provider ← sup_evidence ← sup_harvest
  |             |           |            |
  └──────── sup_family ← sup_loops
                     （依赖 sup_lifecycle 横切 _log_decision）
```

**无循环依赖**。修正说明：
- `VALID_TIER_VALUES` + `is_valid_tier` → **sup_evidence**（与唯一使用处 build_snapshot 同域，消除了 sup_evidence ← sup_harvest 反向边）
- `_log_decision` → **sup_lifecycle**（横切底层函数，sup_family / sup_evidence / sup_harvest / sup_loops 均可依赖 sup_lifecycle，消除了三个中层模块 → sup_loops 的反向边）

### 3.3 全局变量归属（修正版，C3 修正 + M2 补充）

| 变量 | 目标模块 | 说明 |
|------|----------|------|
| _PRAXIST | sup_env | Praxist 二进制路径缓存 |
| _SHUTDOWN_REQUESTED | sup_lifecycle | 关机信号标志 |
| _START_TIME | sup_lifecycle | 启动时间戳 |
| _PERSISTABLE_DM | sup_family | 持久化决策矩阵 |
| VALID_TIER_VALUES | **sup_evidence**（C3 修正，原属 sup_harvest） | 有效 tier 值集合 |

> shim 必须 re-export 以上全部全局符号（M2 修正），见 §2.4。

---

## 4. 测试策略（C2 修正版）

### 4.1 新原则：Patch 目标机械迁移，测试语义零改动

v1.0 的「零测试修改」原则已被评审证实不可行：
- 7 个测试文件共 **238 处** `monkeypatch.setattr(sup, ...)` + **7 处** `sup._SHUTDOWN_REQUESTED = True/False`
- Shim `from sup_X import Y` 是值拷贝，`setattr(sup, "Y", mock)` 只改 shim 命名空间，拆分后真实调用方在 sup_X 命名空间解析 → **patch 静默失效**
- 模块属性赋值无 `__setattr__` 钩子（PEP 562），shim 设计无法拦截 `_SHUTDOWN_REQUESTED` 直接赋值

**新原则**：238+7 处 patch 点脚本化改写为 `setattr(<Y 实际所属模块>, "Y", mock)`，测试逻辑本身零改动。

### 4.2 Patch 迁移清单

| patch 目标 | 数量 | 目标模块 | 涉及文件 |
|---|---|---|---|
| `monkeypatch.setattr(sup, "函数名", ...)` | 238 | 按函数实际所属模块（sup_lifecycle / sup_evidence / sup_harvest / sup_family / sup_provider / sup_loops） | 7 个测试文件 |
| `sup._SHUTDOWN_REQUESTED = True/False` | 7 | sup_lifecycle | test_supervisor.py (5), test_fixes_20261003.py (2) |

迁移方式：编写一次性 Python 脚本，AST 扫描 32 个测试文件，识别所有 `import praxist_supervisor as sup` 后的 `sup.X` 访问，根据 §2.4 shim import 清单映射到实际模块，生成改写补丁。脚本执行后人工审查 diff 确认仅 patch 目标变更、测试逻辑不变。

### 4.3 死代码闸门适配（m4 补充）

`tests/test_no_dead_code.py` 使用 AST 扫描检测死代码。拆分后源文件从 1 个变为 10 个（praxist_supervisor.py + 9 sup_*.py）。若该测试含文件白名单，须同步更新以包含所有新模块。

### 4.4 每步验证

1. pytest tests/test_supervisor.py -x -q
2. pytest tests/ -x -q --tb=short（全部 32 个引用文件 + 其他测试）
3. 验证 36+ 个 public 符号可通过 hasattr(sup, name) 访问
4. 验证路径常量可被 monkeypatch
5. 验证 patch 迁移后 238+7 处全部指向实际模块

### 4.5 新增测试

tests/test_sup_modules.py：
- 验证所有新模块可独立导入
- 验证 shim 导出完整性（len(sup.__all__) >= 55）
- 验证无循环导入
- 验证全局符号 re-export（`_SHUTDOWN_REQUESTED`, `_START_TIME`, `_PRAXIST`, `_PERSISTABLE_DM`, `VALID_TIER_VALUES` 均可通过 `from praxist_supervisor import X` 获取）

---

## 5. 风险评估

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | 循环导入 | 低（已修正 DAG） | 高 | 严格按 §3.2 DAG 顺序创建 |
| R2 | monkeypatch 路径失效 | 低（已脚本化迁移） | 高 | §4.2 脚本迁移 + assert 验证 |
| R3 | sup_loops.py 仍过大 | 高 | 低 | 可接受（≤700 行） |
| R4 | 短暂不可用 | 低 | 高 | 每步单 commit 可 revert |
| R5 | 生产启动失败 | 低 | 极高 | 迁移窗口协议（§5.1） |
| R6 | __all__ 遗漏 | 低 | 中 | 自动校验脚本 |
| R7 | 全局状态跨模块 | 低 | 中 | 统一定义在 sup_lifecycle，shim re-export |
| R8 | 测试非标准 import | 低 | 中 | 拆分前 AST 扫描所有 32 个测试文件 |
| R9 | 迁移窗口 watchdog 触发重启 | 中 | 高 | §5.1 协议：flag 续期 + supervisor 停机 |

### 5.1 迁移窗口协议（M3 新增）

拆分过程须遵守以下协议，防止 cron 看门狗（diagnose_three_loop.sh, 每 15 分钟）在代码半拆分状态下触发 supervisor 重启：

1. **拆分前**：
   - 确认 supervisor 未运行（`pgrep -f praxist_supervisor` → 0 进程）——当前实测即如此
   - 创建 `maintenance.flag` 或临时注释 crontab 中的 diagnose 行（`crontab -e` 注释 1 条）
   - 若使用 flag：每 3 小时 `touch /home/abug/timesfm/maintenance.flag` 续期（flag 过期 = 4 小时，P1 修正产物）

2. **拆分中**：
   - 每步单 commit，任一 commit 状态不可用于生产
   - 全量测试通过后方可进入下一步

3. **拆分后**：
   - 全量 pytest 通过 + `--dry-run --once` 输出与拆分前一致
   - 拉起 supervisor：`.venv/bin/python scripts/praxist_supervisor.py --once` 冒烟
   - 确认 ≥1 个心跳周期正常运行（_write_heartbeat 文件写入成功）
   - 撤销维护模式（恢复 crontab 或移除 maintenance.flag）
   - 正常启动 supervisor 并验证 PID 存活

---

## 6. 成功标准

| 标准 | 目标 |
|------|------|
| 测试通过率 | 100%（32 个引用文件，patch 目标已迁移） |
| praxist_supervisor.py 行数 | ≤ 200 行 |
| 最大子模块行数 | ≤ 700 行 |
| --dry-run --once 输出 | 与拆分前一致 |
| 无循环导入 | 验证通过 |
| 36+ 个 public 符号 | hasattr 全 True |
| 全局符号 re-export | `_SHUTDOWN_REQUESTED`, `_START_TIME`, `_PRAXIST`, `_PERSISTABLE_DM`, `VALID_TIER_VALUES` 均可 import |

---

## 7. 回滚方案

```bash
# 全量回滚
git revert <拆分开始>..<拆分结束> --no-edit
# 单步回滚
git revert <具体步骤commit> --no-edit
# 验证
.venv/bin/python -m pytest tests/test_supervisor.py -x -q
```

---

## 8. 文件清单

### 新增
| 文件 | 行数 |
|------|------|
| scripts/sup_paths.py | ~40 |
| scripts/sup_env.py | ~100 |
| scripts/sup_state.py | ~150 |
| scripts/sup_lifecycle.py | ~180 |
| scripts/sup_provider.py | ~180 |
| scripts/sup_harvest.py | ~500 |
| scripts/sup_evidence.py | ~620 |
| scripts/sup_family.py | ~300 |
| scripts/sup_loops.py | ~680 |
| tests/test_sup_modules.py | ~50 |

### 修改
| 文件 | 说明 |
|------|------|
| scripts/praxist_supervisor.py | 4574 → ≤200 行（re-export shim） |
| **32 个测试文件**（引用 praxist_supervisor） | Patch 目标机械迁移（~245 处 `sup.X` → `actual_module.X`），测试逻辑零改动 |
| tests/test_no_dead_code.py | 文件白名单更新（如有） |

---

## 9. 时间估算（M4 修正版）

| 步骤 | 时间 |
|------|------|
| **步骤 0：is_valid_tier 提升**（C4） | 20 min |
| sup_paths | 15 min |
| sup_env | 15 min |
| sup_state | 20 min |
| sup_lifecycle（含 _log_decision 移入） | 30 min |
| sup_provider | 25 min |
| sup_evidence（含 VALID_TIER_VALUES + is_valid_tier） | 50 min |
| sup_harvest | 45 min |
| sup_family | 30 min |
| sup_loops + shim | 60 min |
| **238+7 处 patch 脚本化迁移**（C2） | 90 min |
| 全量测试 + 修补 | 60 min |
| 迁移窗口协议执行 + 冒烟 | 30 min |
| **总计** | **~10 小时 / 2 个工作日** |

---

## 10. 指纹纪律声明（m5 新增）

本次拆分 **不修改任何 gate/verdict 语义**，所有函数行为、阈值、裁决逻辑保持与拆分前完全一致。因此：

- `protocol_fingerprint` / `_current_protocol_fingerprint` / `_baseline_protocol_fingerprint` **不会 bump**
- 拆分是纯结构性重构（reorganize），不是语义变更（change）
- 若实施过程中意外触碰 verdict 路径或门限计算，须独立 commit + 显式说明 + 触发重生

---

## 11. 参考资料

- scripts/praxist_supervisor.py - 当前 4574 行单文件
- tests/test_supervisor.py - 1873 行主测试
- docs/superpowers/specs/2026-10-08-d4-d5-n10-e1-research-spec.md - D4/D5 前置依赖
- docs/superpowers/reports/2026-10-07-tech-debt-inventory.md - 技术债清单（含已关闭 M5 n_eff）
- docs/superpowers/reports/2026-10-09-m5-supervisor-split-spec-review.md - v1.0 expert review（Reject as-is，13 项修正要求）
- docs/superpowers/plans/2026-10-07-tech-debt-closure-plan.md - 技术债关闭计划

---

*SPEC v2.0, 2026-10-09, S1 Supervisor Split（v1.0 为 M5 编号，经 expert review 修订后重新编号为 S1）*
