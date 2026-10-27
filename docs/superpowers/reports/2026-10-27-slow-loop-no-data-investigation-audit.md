# 慢环 no_data 调查报告 — 重审审计（调查报告审计）

| 项 | 内容 |
|----|------|
| **日期** | 2026-10-27（Asia/Shanghai） |
| **性质** | **重审**（相对 t152u / 前次 audit MD5 `3ae845313b09a312a9f1606cc73dd63c`，可信度 ~74%） |
| **对象** | `/home/abug/timesfm/docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation.md` |
| **对象标题** | 「慢环 no_data Verdict 调查报告（修订版）」 |
| **仓库 / commit** | `/home/abug/timesfm` @ `b87a04a`；报告仍为工作区文件（未要求入库） |
| **修订前报告 MD5** | `9c5edb18a3606429d0b87d7444354311` |
| **修订后报告 MD5** | `e77a039ed014e76066760d8f3ba75098`（已变；mtime 2026-10-27 10:35:26 CST） |
| **审核性质** | 修订点 vs 前次 P0/P1 闭合；声称 vs 现码/队列实证；只读 + 覆盖写本 `*-audit.md` |
| **状态** | 有条件采纳修订稿定性与修复方向 |
| **可信度** | **~86%**（↑ 自 ~74%） |
| **是否可按修订稿采纳** | **定性/根因/优先级：可有条件采纳**；**P0-A/P3 伪代码不可照抄**（与真实 `covariate_pool.json` schema 不兼容） |

授权：用户 t154u；锁由总管授予 New Bot；**不** commit/push/删除/改实现/改源报告。本执行子代理**不释锁**（父任务明确要求）。

---

## §0 路径 / MD5 / 修订差分摘要

| 路径 | 存在 | MD5 / 说明 |
|------|------|------------|
| WSL 报告（修订版） | ✅ | `e77a039ed014e76066760d8f3ba75098`（主证据；较旧稿已变） |
| WSL 本 audit（覆盖） | 写入目标 | 与 box 镜像同文 |
| `/workspace/shared/reviews/2026-10-27-slow-loop-no-data-investigation-audit.md` | 镜像 | 落档后核 MD5 |
| `D:\FlyBuddy\docs\superpowers\reports\` | ❌ | 目录仍不存在；**跳过 D: 副本** |

相对旧稿（`9c5edb18…`）的关键修订（报告 §8.4 自陈 + 全文核对）：

1. §1.1：删「全部 no_data」→ **15 = 9 ok + 6 no_data**
2. 队列会计：214 / 209+134+1=344；注定失败 **23→~81**
3. W5.2：显式写明与 no_data **无因果**
4. 去掉「源码已定义 `_SUPPORTED_COVARIATES`」假主张 → 改为从 `covariate_pool.json` 读取
5. 澄清 typesafe_prescreen **无硬白名单**
6. 新增 **P0-B fail-fast**；P3 改为带锁/备份/原子替换

对照快照（重审时刻，Asia/Shanghai **2026-10-27 10:42 CST**；队列相对前次略推进）：

- `batch_id=reprocess_20261026` verdict：**15**（ok **9** / no_data **6**）——与修订稿一致
- pending 总 **210** / RP **205**（修订稿写 214/209，属审计时刻快照，可接受漂移）
- done_RP **138**（稿 134）；inprogress **1**；**205+138+1=344** 恒等仍成立
- `covariate_pool.json`：`families`=**list[6]**；`covariates`=**dict[31]** 且 `status=="active"`

---

## §1 一句话

修订稿已闭合前次叙事层 P0（全 no_data、W5.2 误绑、伪常量假主张、缺 fail-fast、23 低估），主根因链仍成立；但 **P0-A/P3 的 `load_supported_covariates` 与真实 pool schema 不兼容（照抄会 AttributeError / 空集合）**，且 **「注定失败 ~81」相对现 batch registry 扫描仍偏高（实证唯一 doomed ≈31）**——**可按修订稿推进方向，不可照抄伪代码与 81 清队预期**。

---

## §2 前次 P0 / P1 闭合表

| ID | 前次要求 | 修订稿处置 | 重审实证 | 闭合 |
|----|----------|------------|----------|------|
| **P0-1** | 否定 §1.1「全部 no_data」；改为 15=9ok+6no_data | §1.1/1.2 已改；variant 列表与现 verdict 一致 | 现码 15：ok9+no_data6；no_data cov 与表一致 | **已修** |
| **P0-2** | 入队白名单用 `covariate_pool.json`（+别名），勿照抄伪常量 | 意图正确；§4.3/P0-A 改为读 pool | **伪代码错误**：`families` 实际为 list 非 dict；合法名在顶层 `covariates` dict；字段为 `status:"active"` 非 `active:true`。`pool["families"].values()` → `AttributeError` | **部分**（方向✅，实现片段❌） |
| **P0-3** | 补评估侧 fail-fast（未知 cov 勿跑满 ~588） | 新增 P0-B | 现码仍无 fail-fast（属建议未落地，报告层已补） | **已修**（报告层） |
| **P0-4** | 按 registry 重估无效集合后再清队列 | 23→~81；P3 按 registry 过滤 | 全 batch 唯一 doomed：**31**（family18+unreg10+symbol_c3）；pending 剩余 doomed≈**11**。~81 仍高估 | **部分** |
| P1-peer | peer prompt 白名单 | 仍为 P1 | 未加深实证（可接受） | **仍开**（建议项） |
| P1-prescreen | 本地硬门、不训练 Laya | §3.2/§8.2 已澄清软建议 | 与现架构一致 | **已修**（表述） |
| P1-品种 c | 退役或修数 | 仍为 P2 | 链路仍可信；本轮未复现 `c:1h=0` 命令 | **仍开** |
| P2-正文自洽 | 计数与 §1.1/§5.2 一致 | 大体已修 | **§7 路径表仍写 pending「333 条」**——残留笔误 | **部分** |
| P2-P3 安全 | 停消费/锁/备份 | P3 已改安全版 | 设计合理；但同载入函数 schema 错 | **部分** |
| P2-W5.2 分节 | 勿与 no_data 同因 | §1.1 已标明无因果 | 通过 | **已修** |

---

## §3 主张 vs 实证表（修订稿抽检）

| # | 主张（修订稿） | 实证 | 判定 |
|---|--------------|------|------|
| 1 | 15 verdict：9 ok + 6 no_data | 现 `aligned_verdicts.jsonl` 同 batch 一致；variant 集合一致 | ✅ |
| 2 | 209+134+1=344 | 现 205+138+1=344；恒等仍成立，分量漂移正常 | ✅ |
| 3 | 主根因：peer 族名/幻觉名作 `cov_override` | `m_volatility.json`：`cov_override=volatility`；features `else: raise ValueError(不支持…)`；六族名不在 31 active keys | ✅ |
| 4 | 非 Laya 生成；Laya 只判断 | `typesafe_prescreen` 软建议；提案在 peer `proposals/` | ✅；**Laya 硬约束通过** |
| 5 | 无 prescreen 非充分条件 | 稿已写明；与前次 audit 一致 | ✅ |
| 6 | enqueue 无白名单 | `enqueue_reprocess.py` 仍无 pool/whitelist | ✅ |
| 7 | 从 pool 读 31 active + 别名 | 31 active ✅；但示例加载代码 **读错结构** | ⚠️ |
| 8 | 注定失败 ~79/~81 | registry 扫描全 batch 唯一 doomed **≈31**；pending 剩余 **≈11** | ❌ 量级仍偏 |
| 9 | §5.2「有效≈133=214−81」 | 按现 pending_rp：205−11≈**194** 更近；稿算术基于高估 doomed | ❌ |
| 10 | §7 pending「333 条」 | 与 §1/§5（214）及现码（210）矛盾 | ❌ 残留 |
| 11 | §4.1「族名 12 个」/§4.2「幻觉 9 个」 | 表列分别为 5 行族名、7 行幻觉；「12/9」与表长度不一致 | ⚠️ |
| 12 | P0-B fail-fast | 报告应做；现码未实现（预期） | ✅ 作为建议 |
| 13 | P3 安全清理 | 锁/备份/原子替换方向对；依赖错误 loader | ⚠️ |

---

## §4 根因链（重审后仍建议采纳）

```
Praxist peer 写出 cov_override ∈ {族名} ∪ {未注册幻觉名}
    → 无本地 registry 硬门 → enqueue_reprocess 盲入队（344）
    → monthly_backtest 多点调用 build_covariate_matrix
    → ValueError（未知类型）未 fail-fast → 近满点空转
    → summarize 无有效点 → status=no_data
并行：symbol=c（即便 cov 合法）→ 无 1h → 同墓碑
```

主链 ✅；W5.2 已正确降级为无关警告 ✅。

---

## §5 本轮 P0 / P1 / P2

### P0（按修订稿开工前必须改文档/补丁细节）

1. **重写 `load_supported_covariates`**：以顶层 `pool["covariates"]` 为准，收 `status == "active"` 的 key；`families` 仅为族名 list（可用于「禁止族名当 cov_override」）；别名 `slope_only/none/baseline` 可保留。**禁止** `pool["families"].values()` / `cov.get("active")` 写法。
2. **重估清队数量**：按上项 registry 扫描 pending，预期剔除量级约 **十余条**（现 ~11），不是 81；全 batch 历史 doomed ≈31 仅作说明，勿当作当前 pending 删除数。
3. **回修 §7「333」** 与 §4 标题「12/9」等残留不一致（或删虚数改「见表」）。

### P1

1. Peer 白名单与 typesafe **本地硬门**（不训练 Laya）——稿已列，仍待做。
2. 品种 `c` 退役或修数——保持。
3. fail-fast 落地时定义明确 status（如 `unsupported_covariate`），避免与真 `no_data` 混淆。

### P2

1. 报告入库前再刷一版队列快照时间戳。
2. 若需要 D: 镜像，先建 `docs/superpowers/reports/`。

---

## §6 结论

| 问题 | 答案 |
|------|------|
| 修订稿是否闭合前次叙事 P0？ | **基本是**（1/3 全闭；2/4 部分） |
| 主根因与「非 Laya」？ | **仍成立；硬约束通过** |
| 是否可按修订稿整份执行补丁？ | **否**（loader schema 错；81 清队预期错） |
| 是否可按修订稿开工？ | **可以**：按 §5 P0 改加载函数与剔除数后实施 P0-A/B + 安全 P3 |

**可信度 ~86%。** 建议把修订稿当「已校正的问题定位 + 修复路线图」采纳；实现时以本重审 §5 的 pool 解析与 doomed 量级为准。

---

**Audit 落档**（覆盖）：

- `/home/abug/timesfm/docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation-audit.md`
- `/workspace/shared/reviews/2026-10-27-slow-loop-no-data-investigation-audit.md`

（D: `docs/superpowers/reports/` 不存在，本轮未写 D: 副本。）

**调查人员（源报告）**: AI Agent (oh-my-claudecode:analyst)  
**审计 / 重审**: New Bot（执行子代理）
