# 正期望协变量搜索实施计划

- **日期**：2026-10-05
- **关联 spec**：`docs/superpowers/specs/2026-10-05-positive-ev-factor-search-spec.md`（含同日两次修订）
- **状态**：P1 已在 master（`e007a6c`）。P2.1–P2.9 代码在 `feat/positive-ev-factor-search`，`search_policy` 仍为 `"off"`。P3 合入部署、P4 shadow 观测、P5 enforce 未启动，由宿主执行。
- **进度（2026-10-07）**：晋升、树节与 shadow 计数已有测试。晋升不放宽 `incremental_vs_incumbent`。预注册追加不走 `register()`。本机无 torch，P2.6 现任增量测试与全量失败集基线未在此复跑。记录见 `docs/superpowers/changelogs/2026-10-07-positive-ev-factor-search-p27-p29.md`。
- **全程原则**：TDD（先红后绿）；全量回归与失败集基线逐项恒等后方可合入；监督环运行时不动活仓、不改 `.venv` 里的 Praxist；`search_policy` 键只有宿主改；提交中文、工作树隔离、线性历史。

---

## P0 宿主批准（门槛）

宿主批准 spec 修订版。不批准则保持 `search_policy: off`，活仓行为与今日相同，本计划不启动。批准前不改收割、不改确认、不重启监督环。

## P1 T2d 前置：裁决行 `eval_end_ts` 的 checkpoint 兜底

**内容**：慢环写 `aligned_verdicts.jsonl` 行时，锚还原为 `None` 的（首跑无历史 checkpoint），取该 variant 当前协议 checkpoint 末行锚回填；checkpoint 损坏照 T2c 文件级弃读（仍 `None`）。

**为什么先行**：spec 6.6 条件 6 依赖 `eval_end_ts`，没有兜底时晋升整条 fail-closed。附带收益：成功门（T2）在首跑节点从「锚不可得放行」变为「可窗口判定」——这是 T2 设计语义的补全，属预期收紧，需在观测里确认。

**验收**：
- 新测试：首跑无历史 → 行内 `eval_end_ts` = checkpoint 末行锚；checkpoint 损坏 → `None`（T2c 语义不变）。
- 成功门窗口判定在首跑节点生效的行为有测试锁定。
- 既有回归与失败集基线逐项恒等；协议指纹 `f02b2a43` 不变。

**部署**：工作树 → 合入 → 指纹核对 → TERM + 重启。默认按序单独部署（变更归因清晰、成功门改进早上线）；若宿主想省一次重启，可与 P2 合并为一次部署——批准本计划时择一。

## P2 主实施：搜索树全部条款（工作树 `feat/positive-ev-factor-search`）

按 spec §6 实施，§7 T1-T18 全部锁定。子任务：

| 子任务 | 内容 | 对应测试 |
|---|---|---|
| 2.1 | `search_policy` 开关读取（off/shadow/enforce，缺省 off） | T1 |
| 2.2 | 提案三字段解析；树资格检查（9 个拒绝原因码）；检查钉在管道最前；本轮扩展树仲裁（accept 最早、平手按 `tree_id` 字典序） | T2、T4、T11、T12、T17、T18 |
| 2.3 | `search_commitments.jsonl` 读写（accept/stop/promote，append-only，B/τ 随事件记录） | T3、T9 |
| 2.4 | 停止四规则（预算 / 晋升 / 上界低于现任下界 / 家族死亡联动） | T9、T13 |
| 2.5 | `delta_post_shrunk` 落账；`n_required` 途径 B（`vif=1`，`var_d`=长程方差） | T5、T6、T10 |
| 2.6 | 现任增量 DM；`incremental_vs_incumbent` 落账；现任序列不可得=fail | T7、T14 |
| 2.7 | 晋升判定六条件；`preregistry.jsonl` 追加行（n 继承、键型 `["daily_slope", cov_override]`、指纹追加时点锁定） | T8、T15、T16 |
| 2.8 | known_verdicts「未停止的树」节；族线索「仅当前协议」注记；`prompt_base.jinja2` 三字段教学（含 `success_delta` 的既有字段说明不动）；不另做摘要文件 | spec 6.8/6.9 |
| 2.9 | shadow 档：树检查求值、只计数与决策日志、不改入队、不写 commitments | T1 后半 |

**验收**：T1-T18 全绿；全量回归与失败集基线逐项恒等；指纹 `f02b2a43` 不变；`off` 下行为与今日相同（S1）；子提案撞 `no_success_delta` 的叠加场景（复跑已过门组合需带 `success_delta`）在 prompt 教学示例中有提示。

## P3 合入与部署

rebase/FF 合入 master → TERM 旧进程 → 重启 → 核对：

- 协议指纹 `f02b2a43` 恒定；`baseline_metrics.json` 零重生；
- K6 图例行 = 1；旧协议排除行数与合入前一致；
- 首 tick 物化正常（含新节：无树时写「无」；族线索注记到位）。

## P4 shadow 观测（宿主把键改 `shadow`）

**内容**：`shadow` 至少一轮（一个完整 fast→slow 周期），出观测报告：`search_role_missing` 占比及逐轮变化、三字段出现率、树节与族线索注记渲染正确性。

**通过判据（宿主裁量）**：`search_role_missing` 占比降下去——建议次轮接近 0（同伴看到教学后 1-2 轮内学会）。不过门槛不开 `enforce`，继续 shadow 或回 `off`。

## P5 enforce 打开（宿主把键改 `enforce`）

首轮观测并出报告：

- 拒绝分布按 `(reason, tree_id)` 分桶——区分「同伴没学会」与「树约束拒收」；
- 双席占用与「不回填非法提案」行为；`no_success_delta` 与树约束叠加情况；
- `search_commitments.jsonl` 增长速率（每轮至多 2 条 accept + 停止/晋升判断记录，预期增长缓慢）；
- 家族死亡联动后无双席空转（T13 的生产行为确认）。

---

## 回滚

- 任何时刻宿主把 `search_policy` 改回 `off`：收割行为回到今日（S1）。
- 代码级回滚走 git revert（线性历史，单分支）。
- `preregistry.jsonl` 追加行不回滚：append-only，误晋升由确认终态自然封账（与既有 2 行同等地位）。
- `search_commitments.jsonl` 首行写入后 `B`/`τ` 冻结（spec §8）；此前如需调整，先改 spec 再重新批准。

## 风险与观测点

| 风险 | 缓解 |
|---|---|
| enforce 后子提案撞 `no_success_delta`（复跑已过门 (symbol, cov) 需带 `success_delta`） | 2.8 的 prompt 教学在树节示例中提示；P5 按分桶观测 |
| 同伴长期学不会新字段 → enforce 空转 | P4 shadow 门槛为此而设；不过门槛不开 enforce |
| 多树并存时仲裁争议 | T17 锁定；6.8 树节明示本轮扩展树 |
| 首个 enforce 周期出现意外拒绝模式 | off→shadow→enforce 三段式；每段有报告；宿主随时可退 `off` |
| T2d 使成功门在首跑节点收紧，短期拒绝数上升 | P1 部署后对比 `no_success_delta` 与窗口拒绝分布，属预期语义补全，报告里注明 |

## 与既有工作的衔接

- T2c（2089f1c）已在线：checkpoint 文件级弃读语义是 T2d 与 6.4「现任序列不可得=fail」的共同基础。
- 监督环现 PID 87698（run_id 700dab95c528）；重启按既有流程（TERM → 干净退出确认 → 重启 → 首 tick 物化与指纹核对）。
- 本计划不开 `graph_maintainers`/`frontier_lanes`，不改 `.venv` Praxist，不引入公式搜索（spec §4）。
- 推送时机由宿主定：当前 master 本地领先 origin（spec 两次修订 + 本计划 + 后续实施提交）。
