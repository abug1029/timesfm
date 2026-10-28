# S1 Supervisor 拆分 Spec v3.0 第三轮审阅报告

- **审阅对象**: `docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md` v3.0（commit `c871f34`，824 行，2026-10-10）
- **方法**: AST 全量机器核验（9 段自动检查：附录 A 逐行 diff / 行号勘误 / 环检测 / shim 分析 / 测试面映射）+ 调用方取证 grep + 运行状态实测
- **结论**: **Reject as-is（第三次）**。问题面已从 v2.0 的「符号清单缺失」收窄至「映射表内部一致性」：附录 A.1/A.2/A.3 达到机器验证的完备与准确（150/10/57，零缺失、零行号错误），N1-N7 全部落地；但 §3.2 核心声明「无循环依赖」被附录 A 自身映射推翻（2 个真环、4 条违例边），§2.4 shim 与附录 A 存在 2 处归属冲突 + 24 个符号缺口，§4.2 映射源覆盖率声明不实。修订量为机械级（约 5 行 A.1 + shim 补齐 + 2 个表重算），无需再动架构。

## 一、上轮（v2.0 复审 N1-N7）响应核验

| # | v3.0 响应 | 核验 |
|---|-----------|------|
| N1 九项归属修正 | §2.3 + A.1 全部落地 | ✅ 机器验证：A.1 150/150 完备、行号零错误、九项归属与声明一致 |
| N2 符号清单 | 附录 A（A.1-A.5）建立 | ✅ A.1/A.2/A.3 完备；⚠️ A.5 统计未随 A.1 同步（F4） |
| N3 别名 patch | §4.2 双策略（patch 源模块 / 循环 patch 全模块） | ✅ 策略成立；⚠️ stdlib 别名清单有幻影漏真（F3/F5） |
| N4 四别名扫描 | §4.2 四别名表（14+13+1+1） | ✅ 与实测一致；⚠️ 裸正则有假阳性（F6） |
| N5 is_valid_tier | 步骤 0 提升 + shim re-export + §4.4/§4.5 验证 | ✅ 全链落地 |
| N6 旧 M5 归档 | specs/archive/ + 2 行废弃头 | ✅ |
| N7 _praxist:1028 标注 | A.1 归 sup_env，shim 一致 | ✅ |

## 二、机器核验通过项

- A.1：150 顶层函数 100% 覆盖、零多余、**行号零错误**
- A.2：10 嵌套函数全覆盖，宿主归属一致（is_valid_tier→build_snapshot→sup_evidence；family_for→_maybe_enqueue_confirmations→sup_family）
- A.3：57 模块级赋值全覆盖、行号零错误
- A.4：9 别名全部真实存在（零幻影别名），rl 引用列正确
- §2.4 与 A.1 归属一致性：182 个 from-import 中仅 2 处冲突（见 F2）

## 三、Critical（阻塞放行）

### F1 §3.2「无循环依赖」声明为假——附录 A 自身映射含 2 个真环（4 条违例边）

按 spec 自己声明的 DAG（:306-314）与 A.1 映射，机器检测到 4 条违例边：

**环 E（evidence ↔ harvest）**：
- `_prior_success_row:2352`(evidence) → `_verdict_sort_key`(A.1=harvest)
- `materialize_known_verdicts:1348`(evidence) → `collect_proposed_variant_ids`(A.1=harvest)
- 反向边：harvest deps 含 evidence（spec :132 声明）
- §3.2 环消解表（:317-327）无此环任何行

**环 F（evidence ↔ family）**：
- `_prereg_confirm_from_ts:3876`(evidence) → `load_preregistry`(family)
- `_baseline_reanchor_reason:3888`(evidence) → `_latest_data_dt`(family)
- 反向边：边 G（family → evidence，spec :151 声明）
- 环 D 消解只移动了基线重生簇的位置，A.1 自己的注（→ load_preregistry / → _latest_data_dt）就记录着未消除的 family 边

**消解方案（本轮已验证自洽）**：

| 函数 | A.1 现归属 | 建议 | 验证 |
|------|-----------|------|------|
| `_verdict_sort_key:2151` | sup_harvest | → sup_evidence | 调用方 _latest_verdict_per_symbol(harvest→evidence ✓)、_prior_success_row(evidence 内 ✓)；自身仅 isinstance |
| `collect_proposed_variant_ids:1320` | sup_harvest | → sup_evidence | 调用方 materialize_known_verdicts(evidence ✓)、_maybe_finish_slow:4319 / _main_locked:4417(loops→evidence ✓)；自身仅 open/set |
| `load_preregistry:390` | sup_family | → sup_state | 调用方 _maybe_enqueue_confirmations:505(family→state ✓)、_sweep_search_promotions:3679(loops→state ✓)、_prereg_confirm_from_ts:3880(evidence→state ✓)；自身仅 open+yaml |
| `_latest_data_dt:450` | sup_family | → sup_state | 调用方 _confirm_data_ready:485(family→state ✓)、_baseline_reanchor_reason:3901(evidence→state ✓)；自身仅 DataStore 惰性导入 |

四处移位后全图零违例边（环 E/F 消解），§3.2 环表需新增环 E / 环 F 两行。

### F2 §2.4 shim 与附录 A 冲突 ×2 + 24 个符号缺口

**归属冲突（shim vs A.1）**：
- `_success_delta_gate`：shim=sup_harvest，A.1=sup_evidence。**A.1 正确**——调用方 _locked_success_rows:2573(evidence) + harvest_proposals:2631(harvest)；内部调用 5 个函数全部 evidence 域内（_current_window_anchor/_prior_success_class/_prior_success_row/_row_eval_end_ts/_symbol_data_stale）。按 shim 实施即给环 E 加第三条边。
- `_merge_save`：shim=sup_state，A.1=sup_loops。两属均 DAG 合法（13 个调用点全部在 loops 域：:3070/:3302/:3329/:3369/:3388/:3398/:3420/:3473/:3492/:3749/:4454/:4517/:4537；自身仅调 load_state+save_state），但必须统一，否则 shim `from sup_state import _merge_save` 直接 ImportError。建议 A.1 改 sup_state（语义内聚 + shim 零改动）。

**20 个 `__all__` 幽灵名**（在 `__all__` 但从未 from-import → shim 命名空间不存在 → `sup.X` AttributeError）：
- ←sup_paths：PHASES、POLL_S
- ←sup_state：GOAL_SYMBOLS_SET、_CADENCE_DEFAULTS、_GOAL_YAML_DEFAULT、_GOAL_SYMBOLS_CACHE、_ev_mod_for_goal
- ←sup_provider：parse_429_reset
- ←sup_harvest：CROSS_MATRIX_MAX_ROWS、OLD_PRIORS_MAX_ROWS、MIN_QUALITY_SCORE、COV_CROSS_FAIL_MIN、COV_FAIL_WINDOW、SYMBOL_FAIL_WINDOW
- ←sup_evidence：LOCKED_WINDOW_MAX_ROWS、STALE_DATA_DAYS、SUCCESS_DELTA_MIN_CHARS、_BASELINE_STALENESS_MAX_H、_FP_TARGET_CACHE、_FP_WEIGHTS_CACHE

**4 个双缺符号**（from-import 与 `__all__` 均无、测试有引用、全部 A.1=sup_loops）：
_token_budget_hit、_commit_search_accepts、_sweep_search_stops、_sweep_search_promotions

**测试面合计**：上述 24 个符号中 **10 个**被 32 个测试文件直接引用（setattr 或属性读），拆分即红。

### F3 shim 缺 stdlib 模块属性与 evaluate_goal re-export

- `monkeypatch.setattr(sup.time, "sleep", ...)` / `setattr(sup.subprocess, "Popen", ...)`：test_supervisor.py 内 **11 处**。shim 未 `import time/subprocess` → `sup.time` AttributeError。修复：shim 补两行 import（模块对象是单例，`setattr(sup.time, ...)` 天然全局传播，零测试修改即可工作）。
- `sup.evaluate_goal(conds, snap)` 直接调用：test_supervisor.py:1130/:1136。shim 内 evaluate_goal 出现 0 次 → AttributeError。修复：shim 补 `from goal_dsl import evaluate_goal`（:1837 的 setattr 走 §4.2 N3 策略迁移）。
- `s.logging = result`（模块级 logging 替换）：test_prescreen_score.py:184-186（该文件即四别名表中的 `as s`）。§4.2 stdlib 别名清单写「rl, subprocess, time, **lock** 等」——**lock 是幻影**（实测来自字符串字面量 `"sup.lock"`，test_supervisor.py:13），**漏了 logging**（真实模块属性替换）。

## 四、Major

### F4 A.5 统计表 7/9 模块与 A.1/A.3 计算值不符

sup_loops 42 vs 实际 27（差 15）；sup_evidence 34 vs 41；sup_family 20 vs 23；sup_harvest 14 vs 16；sup_state 10 vs 12；sup_paths 21 vs 23；sup_provider 14 vs 15；sup_lifecycle 赋值 7 vs 6。总数（150/57/10）对但分布错——A.5 是 N1 修正应用前的陈旧快照，:820 的「sup_loops 42 个」注释同病。修法：从 A.1/A.3/A.2 程序化重生成。

### F5 §4.2 映射源覆盖率声明不实

「附录 A 覆盖所有 ~245 个可测试引用符号」——实测 129 个 distinct 测试引用符号中 **10 个无法经附录 A 映射**：time/subprocess/logging（stdlib 属性 patch，需特判）；evaluate_goal（缺 A.4 行）；`__file__`（源码自省测试，见 F7）；use_full_signal/short_horizon_only/update/lock（假阳性，见 F6）。另 245=150+57+9+29 的算式中「29 模块级常量/缓存」与「57 赋值」重叠（前者是后者子集），口径不清。

### F6 §4.2 迁移脚本正则假阳性（会改坏测试）

`(?:sup|S|sv|s)\.(\w+)` 会把局部变量 s 的属性访问误判为 supervisor 引用并尝试改写。实证：
- test_prc4_threshold_revision.py:259 `s.update(over)`（s 是局部 dict）
- test_signal_mode_mutex.py:17/19/25/27 `s.short_horizon_only` / `s.use_full_signal`（s 是局部 symbol 行）
- 字符串字面量亦被命中：`"%s_%s.json"`（test_harvest_proposals.py:32）、`"sup.lock"`（test_supervisor.py:13）

迁移脚本必须 AST import 追踪（识别每个文件的 supervisor import 别名绑定）而非裸正则；§4.2 写「正则/AST」未定取舍，应强制 AST。

### F7 源码自省测试未处置

test_search_tree_stop_rules_20261006.py:479 `open(S.__file__)` 读源码并断言 `'_sweep_search_stops(goal, log, snap["variants"])' in src`。拆分后 S.__file__ 指向 shim（不含该调用文本）→ 必红。处置：迁移脚本将此类测试改指向 sup_loops.__file__（搬移代码保留调用原文，机械可修）；spec 需新增此测试类别的处置条目。

### F8 文档状态与计数不一致

- public 数三处不一致：:23「118 private + 32 public（函数）」vs :80「36 个 public 函数」vs :400/:461「36+ 个 public 符号」。32 为函数实数，应统一口径。
- §5.1 :435「当前实测即如此（0 进程）」：本审阅期间该前提翻转两次（10-10 上午 PID 306 在跑，审阅结束时 0 进程）。协议缺「若在运行：SIGTERM 优雅停止 → 等待退出 → 确认 0 进程」前置步骤，且未提迁移窗口内暂停 cron 自动重启（R9 只覆盖 watchdog 续期）。

## 五、Minor

- A.4 引用列三处错误：ef 声称{evidence}实际{evidence,family,harvest}；st 声称{harvest,loops}实际{evidence,harvest,loops,provider,state}；_fam_report_scope 声称{family}实际零函数引用（死导入，拆分可直接丢弃并在 A.4 标注）
- A.4 缺 4 个非 stdlib 模块级 import 行：evaluate_goal、ALLOWED_FAMILIES、resolve_cov_family、search_promote
- 函数级惰性导入（DataStore：:463/:2925/:2969 `from data.data_store import DataStore`）随宿主函数自动迁移，无需附录 A 覆盖——建议 §3.0 加一句说明，避免实施者困惑
- 假阳性 json/lock 已定性（字符串字面量），F5/F6 覆盖

## 六、处置建议（spec 作者可直接执行）

1. **F1**：A.1 改 4 行（_verdict_sort_key、collect_proposed_variant_ids → sup_evidence；load_preregistry、_latest_data_dt → sup_state）；§3.2 环表新增环 E / 环 F 行；§2.4 对应 from-import 行
2. **F2**：A.1 改 1 行（_merge_save → sup_state）；shim 补 24 个符号 from-import（20 幽灵 + 4 双缺，归属见 F2 列表）
3. **F3**：shim 补 `import time`、`import subprocess`、`from goal_dsl import evaluate_goal`；§4.2 stdlib 别名清单改「rl, subprocess, time, logging」
4. **F4**：A.5 + :820 注释程序化重生成
5. **F5/F6**：§4.2 新增「附录 A 之外特判表」（time/subprocess/logging/evaluate_goal/__file__ 五类）；迁移脚本强制 AST import 追踪
6. **F7**：§4.2 新增源码自省测试处置条目（改指 sup_loops.__file__）
7. **F8**：public 数统一口径；§5.1 补「若在运行先优雅停止」步骤
8. **复审范围**：修订后无需全文复审——仅复核 A.1 diff（5 行）、§2.4 shim 块、§3.2 新增环表行、§4.2 特判表；按第七节方法重建核验脚本复跑，预期输出：违例边 0、归属冲突 0、SHIM_GAP 0、unmapped 仅剩已定性假阳性

## 七、审阅方法与可复现性

- 附录 A 解析：bold 模块名（`**sup_lifecycle**`）需 `\*{0,2}` 前缀容忍（A.1 有 17 行带 N1 注记为 bold 格式；初次解析漏掉这 17 行曾造成「A.1 缺 17 函数」的假象）
- 环检测：A.1+A.3 符号→模块映射 × AST 顶层函数调用图 × spec 声明依赖表（§1.3/§3.2）
- shim 分析：提取 §2.4 python 代码块，from-import 名单 × `__all__` × 附录 A 三方对账
- 测试面：`grep -hoP 'setattr\((?:sup|S|sv|s),\s*"\K[^"]+'` + 属性访问正则，129 distinct
- 调用方取证：load_preregistry / _latest_data_dt / _verdict_sort_key / collect_proposed_variant_ids / _merge_save / _success_delta_gate 及基线重生簇全量 grep + AST 内部调用集
- 运行状态：pgrep 实测两次（PID 306 → 0 进程）
