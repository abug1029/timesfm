# 慢环 no_data 修复 — Changelog 代码审计报告

| 项 | 内容 |
|----|------|
| **审计日期** | 2026-10-27（Asia/Shanghai，约 15:05 CST） |
| **性质** | **Changelog 代码审计**（声称 vs 现码实证；**不改实现**） |
| **对象** | `docs/superpowers/changelogs/2026-10-27-slow-loop-no-data-fix-changelog.md` |
| **仓库** | `/home/abug/timesfm` @ `2c4c92b`（ahead origin 15；本修复链止于 `b63b4ad`，其后另有 docs/P1 提交） |
| **Commits 宣称链** | `257fcf3` → `da08fbe` → `03e3171` → `d45ad24` → `b63b4ad`（5 commits；docs changelog `782f3a8`） |
| **对照** | Plan audit MD5 `8653e978…`（有条件 ~80%；P0×3）；Plan MD5 `35a2f3bd…`；调查报告重审 audit `70cedaeb…` |
| **用户硬约束** | **Laya 只是判断模型，无法学习 / 训练 / 进化；不可改权重** |
| **审核状态** | **有条件通过** |
| **完成度** | **~87%**（相对「入队校验 + fail-fast 中断 + 清队」功能落地）；相对 changelog「3/3 fail-fast / 18/18 / 全部验收」则 **不得按字面验收** |
| **是否可宣称完成** | **可有条件宣称** P0-A / P0-B / P3 **功能已落地且队列无效条目已清**；**不可宣称** changelog 文内「P0-B 3/3」「test_combo_unsupported_raises」「全部验收标准满足」之测试字面 |

---

## §0 Changelog 双路径 MD5 / 分叉

| 路径 | mtime (CST) | 大小 | MD5 | 状态 |
|------|-------------|------|-----|------|
| **主证据**：`/home/abug/timesfm/docs/superpowers/changelogs/2026-10-27-slow-loop-no-data-fix-changelog.md` | 2026-10-27 **13:22** | 4846 B | `cdafcf12e7788453a2a5c33f8cdccee0` | 存在；文首称 5 commits 完成；验收全勾 |
| **D:\\FlyBuddy\\…\\changelogs\\同名**（`/mnt/d/FlyBuddy/…`） | — | — | — | **不存在**（该目录有旧 changelog / 前次 laya audit；**无本 slow-loop changelog 原件**） |

**裁定**：以 **WSL timesfm** 为唯一证据主路径。D: 缺副本 = 文档同步缺口（非内容分叉）。本 audit **覆盖写入** WSL 同目录 + D: changelogs + box reviews。

| 对照件 | MD5 |
|--------|-----|
| Plan（现） | `35a2f3bd6954f79ff5ef8ccd67a40aac`（仍含 `_REGISTERED_COVARIATES` 伪代码；实现未照抄） |
| Plan audit | `8653e978f2b38c005c36b73dd4168b62` |
| 本 audit（落档后三路径应同） | 见文末 |

---

## §1 一句话结论

五提交关键符号（`load_supported_covariates` 正确 schema、`UnsupportedCovariateError`、首点 `[FAIL-FAST]`→`return None`、清队锁/备份/原子替换）**确实落地**；bak 实证 **198→去 11**，现 pending **177 且无效残留 0**。Plan 审计 P0×3：**功能侧大体闭合 / 设计与测试债半闭**。Changelog **夸大** fail-fast「3/3」与虚构 `test_combo_unsupported_raises`。完成度 **~87%**；**可有条件宣称功能完成，不可按测试字面验收**。

---

## §2 Changelog 声称 vs 实证（逐 Task）

| Task / 声称 | Changelog | 实证 | 判定 |
|-------------|-----------|------|------|
| **Task1** `257fcf3`+`da08fbe` 入队校验 | `[x]`；loader+过滤+`invalid_covariate` | `load_supported_covariates`：`families`=list；`covariates` dict + `status=="active"`；别名 `slope_only/none/baseline`；`main` 跳过族名/未注册并计数 | ✅ **落地**（schema 正确） |
| Task1 测试 | 写 2 tests；fixture 修正 | `momentum`→`ao_accel`，`basis`→`basis_momentum`；本机 `.venv`：**2 passed** | ⚠️ **绿测已修**；**未**断言族名/未注册被 skip / `invalid_covariate`（plan P0-2 仅半闭） |
| Task1「10 无效过滤，184 有效入队」 | 集成结果 | 属实施当时口述；本轮未重放全量 enqueue；逻辑路径存在 | ⚠️ **不可独立复核数字**（非阻塞） |
| **Task2** `03e3171`+`d45ad24` fail-fast | 异常类 + features 抛出 + 首点捕获 return None + `[FAIL-FAST]` | `UnsupportedCovariateError(ValueError)`；single `else` 与 combo 未知分支均 raise；`monthly_backtest` 在 **eval 循环内** `except UnsupportedCovariateError` 且 **仅 `i==0`** 时 `return None` | ✅ **功能落地**；⚠️ **非** plan-audit 推荐的「循环前 supported 集校验」（首点仍跑 `daily_predict` 再在 hourly 路径抛错） |
| Task2「3/3」含 `test_combo_unsupported_raises` | 明文 3 tests | 文件仅 **2** 个 `def test_`（raise + issubclass）；**不存在** `test_combo_unsupported_raises`；`d45ad24` 提交说明自写 **2/2**；无 `run_symbol_backtest` 返回 None 的单测 | ❌ **夸大（本轮 P0）** |
| Task2「600-900x / \<1s」 | 性能宣称 | 未在本轮计时复现；机制上可避免满窗 588 点，但首点仍含 daily 预测开销 | ⚠️ **方向可信 / 数字未证** |
| **Task3** `b63b4ad` 清队 | 198→187 移 11；锁/备份/原子替换；含品种 `c` | 脚本存在；`fcntl`+`.bak.`+`.tmp` rename；过滤 fam/unreg/`symbol=="c"`。最新 bak `…130335`：**198 行 / bad=11（fam2+unreg8+c1）**；现 pending：**177 行 / bad=0**（清后继续被消费，故非 187） | ✅ **清队生效**；⚠️ 行数叙事停在 187，现为 177（消费差额，非回潮） |
| **Task4** 集成 18/18 | 全通过 | 本轮可复现：enqueue+fail_fast **4 passed**；再加 combo_parity+covariate_pool+filter → **31 passed**。changelog「18/18」**未绑定文件清单**，无法对上 | ⚠️ **相关测绿 / 18 口径不明** |
| **不做** P1 peer / P2 品种 c / 端到端慢环 | 列出 | 范围内未改 peer（另有后续提交 `2c4c92b` feat P1 whitelist，**晚于** changelog 链，不计入本 changelog 验收） | ✅ 相对本 changelog 范围 |
| 文首「实施完成」+「所有验收标准满足」 | 状态 | 功能高；测试声明与 3/3 不符 | ⚠️ **功能可认 / 验收句不可照抄** |

---

## §3 相对 plan 审计 P0×3 闭合表

| 前次项（plan audit P0） | 本审实证 | 闭合？ |
|------------------------|----------|--------|
| **P0-1** Task2：循环前用 supported 集校验并**整次中断**；勿错签名/虚构 `_REGISTERED_COVARIATES` | 未照抄虚构常量；改为 features `UnsupportedCovariateError` + 首点 catch→`return None`。**未**在循环前用 pool supported 集预检；`i>0` 遇同类异常仍继续记 error | ⚠️ **功能半闭 / 设计未按 P0 全文**（整次中断在 `i==0` 路径成立） |
| **P0-2** 更新 `test_enqueue_reprocess` fixture；新增族名/未注册 skip 与 `invalid_covariate` 断言 | fixture 已改为真实 active；**无** skip/`invalid_covariate` 新断言 | ⚠️ **半闭**（防红已闭；正向过滤测未补） |
| **P0-3** 统一 ~11：入队≈10；含 `symbol=c` 归清队 | enqueue 不拦 `c`；cleanup 拦 fam+unreg+`c`；bak 恰 11 | ✅ **已闭** |

**Plan 正文**：仍保留 `_REGISTERED_COVARIATES` / 错签名草稿；**实现未照抄** → 不把「plan 未改」记为实现失败，记为文档债（P1）。

---

## §4 Laya 硬约束

| 检查 | 结果 |
|------|------|
| changelog / 五提交 / 入队·清队·fail-fast 路径含学习·训练·微调·进化·改 Laya 权重 | **无** |
| 根因归属 | Praxist peer 错名；修复在 enqueue / backtest / features / 清队 |
| features 内「权重」字样 | PCA/regime 融合权重（既有），**非** Laya |

**Laya 硬约束：通过。**

---

## §5 本轮 P0 / P1 / P2

### P0（挡「按 changelog 字面验收」；不挡「功能有条件完成」）

1. **Changelog 测试夸大**：删除或改正「3/3」「`test_combo_unsupported_raises`」；与现文件 **2 tests** / `d45ad24`「2/2」对齐。建议补：`build_combo` 抛 `UnsupportedCovariateError` 单测；可选 `run_symbol_backtest` 首点 fail-fast→`None`（mock predict/build）。
2. **（建议升 P0 若要坚持 DoD）** 补 enqueue：族名 / 未注册 → skip 且 `invalid_covariate` 计数断言（闭合 plan P0-2 余量）。

### P1

1. fail-fast 改为（或兼）**进入 eval 循环前**用与 enqueue 相同的 `load_supported_covariates` 预检，避免首点 `daily_predict` 空转；`i>0` 亦应整次中断。
2. 抽取共享 `load_supported_covariates`（enqueue / cleanup / 预检三处现拷贝）。
3. 可选：区分 `unsupported_covariate` vs 真 `no_data` verdict status。
4. Changelog「18/18」改为可复现命令+文件列表；同步 D: changelog 副本。
5. Plan 正文删掉 `_REGISTERED_COVARIATES` 伪代码，改为与现码一致的异常路径说明。

### P2

1. 记录清队后 pending 从 187→177 为慢环消费，勿在复盘时当成「又混入无效」。
2. 后续 `2c4c92b` P1 peer 白名单不在本 changelog 范围，宜另开 changelog/审计。

---

## §6 可否宣称完成

| 宣称 | 可否 |
|------|------|
| 「入队校验 + fail-fast 中断满窗 + 安全清队」**功能已落地** | ✅ **可以（有条件）** |
| 「pending 无效 cov/族名/c 已清，现残留 0」 | ✅ **可以**（本轮实扫） |
| Changelog「P0-B 3/3 / test_combo_unsupported_raises / 全部验收标准满足」 | ❌ **不可以** |
| 「Day 级问题全闭环且无需再改」 | ❌ **否**（测试债 + 预检设计债仍在） |
| 授权下一阶段改实现 / commit | **本审计不授权**；维持 standing：不 commit/push/删除/改实现 |

---

## §7 本轮命令摘录（只读）

- 五 hash 均在库；`git status` ahead 15（含无关脏文件，审计未改）。
- `.venv/bin/pytest tests/test_enqueue_reprocess.py tests/test_fail_fast_unsupported_covariate.py` → **4 passed**。
- 扩跑 + `test_combo_parity` + `test_covariate_pool` + `test_covariate_filter` → **31 passed**。
- pending：177 / bad=0；bak `aligned_pending.jsonl.bak.20261027_130335`：198 / bad=11。

---

**审计生成时间**: 2026-10-27 15:05 CST（Asia/Shanghai）  
**本 audit 落档**: WSL changelogs / D: changelogs / `/workspace/shared/reviews/` 同名  
