# M5 Supervisor Split Spec 审核报告

> **日期**: 2026-10-09
> **被审对象**: `specs/2026-10-09-m5-supervisor-split-spec.md`（v1.0，Draft → 待实施）
> **审核基线**: HEAD `1c7c7f5`（spec 提交）；实施前置链 `78f3187`(P1)→`89273e0`(P2)→`b07d501`(P1-P5 处置完成)
> **方法**: 声明逐项实测——行数/函数计数/grep 统计/monkeypatch 模式扫描/调用分布分析/CLI 参数核对；全部只读
> **结论一句话**: 拆分方向与 DAG 思路合理、基础数据大体准确、前置依赖（D4/D5）今日已真实成立，但存在 **4 项 Critical**：编号冲突（M5 已被占用）、「零测试修改」与 238 处 `setattr(sup)` 结构性冲突、归属表自含两处循环依赖、`is_valid_tier` 嵌套函数无法 re-export——**有条件不通过（Reject as-is）**，修正前置条件见 §6。

---

## 1. 事实核验表

| spec 声明 | 实测 | 判定 |
|---|---|---|
| `praxist_supervisor.py` 4574 行 | 4574 | ✓ |
| 函数总数 160（124 private + 36 public） | `def` 计数 160（顶层 150 + 嵌套 10） | ✓ |
| `test_supervisor.py` 1873 行 / 155 次 `sup.` 调用 | 1873 / 155 | ✓ |
| **141 个测试文件引用** | **tests/ 共 143 个 .py**（含 conftest.py、__init__.py），**实际引用 `praxist_supervisor` 的仅 32 个** | **✗ 误记**（141 = 143 − 2 系目录总数之误，见 M1） |
| `--dry-run --once` 验收可执行 | `main()` argparse 实有 `--dry-run`/`--once`（store_true） | ✓ |
| 前置依赖 D4/D5 已完成 | 2026-10-08 裁决处置链已落地：`78f3187` 旗标 4 小时（实测 `MAINT_FLAG_EXPIRE_HOURS=4`）、`89273e0`+`d34a69d` cron 调度已挂载（实测 crontab 1 条 diagnose）、`b07d501` 记 D4 delivered | ✓（裁决 P1/P2 当日已闭环，本声明今日成立） |
| 域 O 含 `ensure_baselines` | `:3988 def ensure_baselines` | ✓（但 §2.3 归 sup_evidence，跨域移动未标注，见 m2） |
| `_write_stop_json` | `:659 def` 存在 | ✓（§2.3 职责列表漏列，见 m1） |

## 2. Critical（阻塞实施）

### C1 编号冲突：M5 已被占用且已关闭

- 技术债清单 `2026-10-07-tech-debt-inventory.md:47`：**M5 = 「`n_eff` 实际是常数函数」**，已于 2026-10-07 溯源结案（设计使然：解析式 Bartlett 修正；closure-plan §Q1 记「M5 关闭，零改动」）。
- 本 spec 以 M5 指代 supervisor 拆分——编号错位。closure spec §70 明文警告过此类事故：「批准记录务必用 T1/T2/T3 或 E1，否则会把批准落到已关闭条目上」。
- **处置**：换编号（建议宿主定夺，如 M6 或新开 S 系列），并在 spec 状态头注明与已关闭 M5（n_eff）的区别。
- 顺带闭环：已关闭的 M5（n_eff 恒 73）恰好解释了 C1 诊断报告 P4 的 `n_eff=73 vs d_series_n_eff=588` 之谜——8 倍关系源于 Bartlett 自相关修正，属设计行为非缺陷。

### C2 「零测试修改」原则与 238 处 patch 结构性冲突

实测 patch 体量：

| 统计项 | 实测值 |
|---|---|
| `monkeypatch.setattr(sup, ...)` 总数（7 个测试文件） | **238** |
| 其中 test_supervisor.py | **148**（155 次 sup. 调用中 148 次是 patch） |
| 直接赋值 `sup._SHUTDOWN_REQUESTED = True/False` | **7 处**（test_supervisor.py 5 处 + test_fixes_20261003.py 2 处） |

机制性失败，非边缘 case：

1. shim `from sup_X import Y` 是**值拷贝**。测试 `setattr(sup, "Y", mock)` 只改 shim 命名空间键；拆分后真实调用方在 `sup_X` 命名空间解析 `Y` → **patch 静默失效**（mock 未被使用，测试跑的是真实现——可能假绿可能假红）。
2. `sup._SHUTDOWN_REQUESTED = True` 是**模块属性赋值**——Python 模块协议只有 `__getattr__`（PEP 562），**没有 `__setattr__` 钩子**，任何 shim 设计都无法拦截转发。signal-handler 全局标志的零修改兼容**根本不存在**。
3. spec R2 只考虑了「路径常量 re-export」，对 238 处**函数 patch** 与可变全局赋值无任何机制。

**处置**（spec §4 须重写，二选一）：
- 方案 A（推荐，务实）：放弃零修改承诺，将 238 处 `setattr(sup, "X")` 脚本化改写为 `setattr(<X 实际所属模块>, "X")`，断言逻辑零改动；`_SHUTDOWN_REQUESTED` 同步改写。以「patch 目标机械迁移、测试语义零改动」为新原则。
- 方案 B（理论可行，脆弱）：子模块内对可 patch 符号统一延迟绑定（函数体内 `import praxist_supervisor as sup` + `sup.X()` 调用）。可行但要求全部调用点无遗漏（一处直接调用即埋雷），且 `_SHUTDOWN_REQUESTED` 赋值仍无解（须封装 get/set 函数——又是接口变更）。

### C3 归属表自含两处循环依赖，与 §3.2「无循环依赖」矛盾

| 暗雷 | 机制 |
|---|---|
| `VALID_TIER_VALUES → sup_harvest`（§3.3） | 唯一使用链是 `build_snapshot`（归 sup_evidence）内的 `is_valid_tier` 读它（`:25` 常量 + `:1150` 使用）。sup_evidence → sup_harvest 反向边，撞 DAG 的 sup_harvest → sup_evidence 正向边 = **环** |
| `_log_decision → sup_loops`（§2.3） | 实测 38 处调用分布：**sup_family 域 4 处**（FDR 函数，行号 <621）、**sup_evidence 1 处**、**sup_harvest 1 处**、sup_loops 自域 32 处。三个中层模块 → 顶层模块的反向边 ×3 = **环** |

R1 缓解「严格按 DAG 顺序创建」救不了**设计层**的依赖方向错误——按 spec 实施会在 import 时直接 ImportError（好情况）或被迫引入函数内延迟 import（坏情况，R1 风险兑现）。

**处置**：
- `VALID_TIER_VALUES` 与 `is_valid_tier` 一并归 **sup_evidence**（与唯一使用处同域）；
- `_log_decision` 归 **sup_lifecycle**（底层横切，与 `_emit_event` 同层）或独立 `sup_logging.py`；
- §3.2 DAG 图补充「横切依赖」注记后重新声明无环。

### C4 `is_valid_tier` 是嵌套函数，shim `__all__` 不可满足

- 实测 `:1150    def is_valid_tier(v):`——**`build_snapshot` 内部嵌套函数**（缩进确认），不是模块级符号。
- §2.4 shim 的 `__all__` 含 `"is_valid_tier"`，但 `from sup_XXX import` 清单中**没有任何模块提供它**——现状直接执行会 `AttributeError`（模块级 `__all__` 在 import 时不强制检查，但 `hasattr(sup, "is_valid_tier")` 验收与任何 `from praxist_supervisor import is_valid_tier` 都会失败）。
- **处置**：迁移步骤 0（spec 未列）——先把 `is_valid_tier` 从 `build_snapshot` 内提升为模块级函数（纯机械重构，`VALID_TIER_VALUES` 引用不变），单 commit + 全量测试，再做拆分。

## 3. Major（须修正）

### M1 「141 个测试文件」误记

- 141 = tests/ 目录 .py 总数 143 − conftest.py − __init__.py（实测对账成立）。**实际引用 `praxist_supervisor` 的测试文件 = 32 个**。
- 影响四处：§1.1（现状）、§4.1（零修改原则）、§6（成功标准「141 文件 0 修改」）、§8（修改清单）。
- 修正后**影响面缩小 4.4 倍**（利好），但 patch 密度问题（C2）更集中：238 处 patch 分布在 7 个文件，全部属于这 32 个。

### M2 shim 遗漏全局符号 re-export

- §3.3 全局变量归属表列了 `_PERSISTABLE_DM / VALID_TIER_VALUES / _PRAXIST / _SHUTDOWN_REQUESTED / _START_TIME`，但 §2.4 shim import 清单**一个都没有**。
- 实测后果：`tests/test_tier_domain_guard.py` 直接 `from praxist_supervisor import VALID_TIER_VALUES` → shim 缺该项即 ImportError，零测试修改当日破功。
- 注意：re-export 仅解决**读取**；`_SHUTDOWN_REQUESTED` 的**写入**（7 处直接赋值）无解，归 C2。

### M3 与已挂载看门狗的交互缺失（拆分窗口风险）

- P2 处置后 cron 每 15 分钟跑 `diagnose_three_loop.sh`（实测 crontab 1 条）。拆分中途任意 commit 状态下若触发 S1/S2 重启，**supervisor 会加载半拆分代码**。
- `maintenance.flag` 现为 **4 小时**过期（P1 修正产物），而 spec 时间估算 **~5 小时**——旗标必然在拆分中途过期，自愈恢复执行。
- 实测 supervisor 当前**未运行**（ps 0 进程）——这是天然安全窗口，但 spec 未利用也未声明。
- **处置**：spec 增补「迁移窗口协议」：拆分前置 `maintenance.flag` + 每 3 小时 `touch` 续期（或临时注释 cron 行）；全量测试通过后先拉起 supervisor 冒烟、再撤旗标；把「拆分完成后 supervisor 正常运行 ≥1 个心跳周期」纳入验收。

### M4 时间估算不含 C2-C4 处置

- ~5 小时仅覆盖机械搬移。238 处 patch 点审计/改写（方案 A）+ 嵌套函数提升（C4）+ 归属修正（C3）+ 中途修雷，实际工期预计翻倍（~10 小时 / 2 个工作日）。估算应按选定的 C2 方案重排。

## 4. Minor

| # | 问题 |
|---|---|
| m1 | §2.3 职责列表与 §2.4 shim import 清单不一致（`_write_stop_json`、`_symbol_n_table`、`_prior_success_class`、`_dead_families` 等出现在 import 而不在职责列表）——建议以单一权威清单（建议自动生成：AST 扫描顶层符号）为准 |
| m2 | 跨域移动未标注（`ensure_baselines` 域 O → sup_evidence；域 I 配额函数 → sup_loops） |
| m3 | §1.2 域 D（192-428）与域 E（332-620）行号重叠——分区扫描精度问题 |
| m4 | 死代码闸门（`tests/test_no_dead_code.py` AST）适配未提——拆分后 4574 行迁往 9 个新文件，若闸门含文件白名单须同步更新 |
| m5 | 缺「指纹纪律」声明——拆分不动 gate 语义，应显式声明 `protocol_fingerprint` 不 bump（仓库惯例：任何触碰 verdict/gate 路径的 spec 均须声明，closure-plan §4） |

## 5. 已核实为正确/合理的部分

- 拆分动机成立（4574 行 / 160 函数 / 全局路径集中 / 交叉引用密集）。
- 10 域划分与「内聚 > 行数均衡」原则合理；`sup_paths` 收拢路径常量方向正确。
- 每步单 commit 可 revert、DAG 分步创建、`--dry-run --once` 输出比对验收——机制健全。
- 基础统计（行数/函数数/主测试 1873 行 155 调用）准确；CLI 参数真实存在。
- 前置依赖 D4/D5 声明在今日已真实成立（昨日裁决 P1-P5 已由 `78f3187`..`b07d501` 全部处置，实测旗标 4 小时、cron 已挂载、D4 delivered）。

## 6. 结论与前置条件

**Reject as-is（有条件不通过）**。拆分值得做，但当前 spec 直接实施会在步骤 7-10（evidence/harvest/family/loops 迁移）集中踩雷。修订要求：

1. **换编号**（C1），与已关闭 M5（n_eff）切割；
2. **重写 §4 测试策略**（C2）：明确选定方案 A（推荐：patch 目标脚本化改写 + 语义零改动）或方案 B，并给出 238 处 patch 点的清单化验证步骤；
3. **修正 §3.3 归属**（C3）：`VALID_TIER_VALUES`+`is_valid_tier` → sup_evidence；`_log_decision` → sup_lifecycle；重画 DAG；
4. **补迁移步骤 0**（C4）：`is_valid_tier` 提升为模块级函数（独立 commit）；
5. **补迁移窗口协议**（M3）：maintenance.flag 续期安排 + supervisor 停机窗口利用 + 完成后拉起验收；
6. **全局数字勘误**（M1/M2）：141→32（四处）、shim 补全局符号 re-export 清单；
7. 补指纹纪律声明（m5）。

修订版经复核后可进入实施。

**审核者签名**: _______________  **日期**: 2026-10-09
