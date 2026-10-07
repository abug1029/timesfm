# 2026-10-07 正期望协变量搜索 P2.7/P2.8/P2.9 落地

## 范围
- P2.7 晋升六条件，并为通过的节点向 `preregistry.jsonl` 追加恰好一行。
- P2.8 `known_verdicts`「未停止的树」节、族线索「仅当前协议」注记、`prompt_base.jinja2` 三字段教学。
- P2.9 `shadow`：树检查照常求值，只记「本会拒绝」，不改入队，不写 `search_commitments.jsonl`。
- `scripts/praxist_goal.yaml` 的 `search_policy` 仍是带引号的 `"off"`。
- P3 合入与重启、P4 shadow 观测、P5 enforce 本机未启动。活监督环在 `/home/abug/timesfm`，不在这台机器上。

## P2.7 晋升
- 新模块 `scripts/search_promote.py`：`evaluate_tree_promotion` 纯函数。六条件都成立才返回决定。`eval_end_ts` 缺失、无锁定样本量、`incremental_vs_incumbent` 不是 `pass`/`not_applicable`、`gate_pass` 不为真、`delta_post_shrunk` 不大于 0、`search_var_lr` 不可用、或 `n_required` 大于锁定 n，都返回 None。
- `n_confirm_required` 继承该品种最早一条带整数锁定样本量的预注册（jd 1199、sr 986），不按新的 `var_lr` 重算。`confirm_from_ts` 取该品种已有值与节点 `eval_end_ts` 的较晚者。
- `var_lr` 用裁决上冻结的 `search_var_lr`。`evaluator.build_summary` 在 `se` 可算时把 `compute_hac_se(d_t)` 写入该字段。`scripts/registry_lib.py` 把它登记进 `VERDICT_FIELDS_V2` 与可空集。
- `scripts/praxist_supervisor.py` 主循环在 `_sweep_search_stops` 之后调用 `_sweep_search_promotions`。本轮刚因预算、上界或家族死亡停下的树不再晋升。
- 追加预注册不调用 `register()` / `new_preregistration()`。见下方张力。
- 写入顺序：先 `event=promote`（`stop_reason=promoted`，树变为终态），再追加预注册一行。中途失败时下一轮不会对同一棵树再追加第二行。

## P2.8 同伴表面
- `render_open_trees`：没有未停止的树时写「无」。有树时列出 `tree_id`、品种、族、已用 ok 次数、预算 4、是否本轮扩展树，以及每个成员的 `near_miss`。扩展树存在时节末一句：本轮两份提案应为本轮扩展树的 exploit 与 falsifier。
- 物化时局部变量 `st` 曾盖住 `search_trees` 模块，树节调用会炸。该变量已改名为 `sym_status`。
- 族线索第二行：仅当前协议，旧协议已滤除；分母含描述性裁决。既有 `- 族: pass/total gate_pass` 写法保留。渲染文本不含 `%`。
- prompt 在既有 `success_delta` 条目之后、协变量池之前加入第 10 条。`success_delta` 原句未改，并写明搜索字段不代替它。

## P2.9 shadow
- `enforce` 构造拒绝生效的守卫。`shadow` 另构造一只守卫，把原因计入 `search_would_reject`，决策日志记 `search_shadow`。不拒绝、不把搜索字段带进队列、不写 commitments。`off` 不构造守卫。
- 同一轮内守卫的内存占座保留，使后到的提案能记到准确的「本会拒绝」原因。这只影响计数，不落盘。

## 与 spec 的两处张力（本切片不放宽）
1. **现任增量口径。** `incremental_vs_incumbent` 仍按 spec §6.4：`dm_status` 须在 `{ok, set_mismatch_ok}`，并要求 missingness 可接受。生产裁决多为 `set_mismatch_descriptive`，因此晋升条件 4 在生产上几乎恒不成立。P2.6 审核已要求忠实 spec。本切片不放宽。宿主若要晋升真正发生，需改 spec 或改口径后再开 `enforce`。
2. **预注册追加与 `register()`。** §6.6 要求样本量继承锁定值，同时 `var_lr` 取节点 `d_t` 的 `compute_hac_se`。`preregistry._locked_n` 要求 `n_confirm_required == n_required(var_lr, delta=0.08)`，这两件事不能同时通过 `register()`。S5 与 §6.6 是完成标准，所以直接追加 JSON。`due_confirmations` 按行派发，T15 已锁定。§9 写明与 v15 预注册读法冲突时以 v15 和 Q7 为准；此处没有改 `gate()`、`pass_variants()`、协议指纹或 Δ*=0.08。

## 测试
在本工作树用系统 `python3`（已装 numpy、pandas、pytest；无 torch）：

```
python3 -m pytest tests/test_search_promote_20261007.py tests/test_search_shadow_20261007.py tests/test_search_peer_surface_20261007.py tests/test_search_delta_post_20261006.py tests/test_search_policy_switch_20261006.py tests/test_known_verdicts_injection_20261005.py tests/test_search_tree_admission_20261006.py tests/test_search_tree_stop_rules_20261006.py -q --tb=line -p no:cacheprovider
```

审核补丁之后同一命令再跑，并加上 `tests/test_supervisor.py`、`tests/test_harvest_proposals.py`、`tests/test_success_delta_gate_20261005.py`、`tests/test_proposal_quality_gate.py`：246 passed、1 failed。

那 1 个失败是 `test_harvest_survivors_enter_slow_no_start_no_cycle`。本 diff 暂存之前的 HEAD 上同样失败，不是本切片引入的。

本机跑不了、未记为通过：
- `tests/test_search_incremental_incumbent_20261006.py` 17 个失败。`scripts.aligned_slow_loop` 导入 `monthly_backtest`，后者 `import torch`，本机没有 torch。测试把 `ImportError` 收成 `None` 再调用。该文件本切片未改。
- `tests/test_confirmation_wiring.py` 收集即因同样的 torch 导入失败。
- P2.6 changelog 里的全量 18 failed / 1771 passed 基线是在有 torch 的环境跑的。本机不能复现那份失败集。


## 审核后补上
- `known_verdicts` 改在停止巡检和晋升之后物化。本轮刚关闭的树不会再出现在同伴看到的「未停止的树」里。
- 预注册协变量键与裁决指纹键不一致时，不抄 `matrix_sha256`。键一致时仍整份复制。
- `_finite` 拒绝布尔，与 `search_trees._finite` 一致。

## 明确没做
- 未改 `gate()`、席位数 3、Δ*=0.08、协议指纹 `f02b2a43`。
- 未改 `dfd1f43` 的 `data_stale` 成功门（kline 年龄大于 3 个上海日历日才放行）。
- 未创建生产 `task_FM/config/search_commitments.jsonl`。
- 未合并 master，未推送，未 TERM，未重启监督环。
- P2.4–P2.6 的 NIT，以及低 T 不可逆 dominated 停止，仍延后。

## 相关文档
- spec: `docs/superpowers/specs/2026-10-05-positive-ev-factor-search-spec.md`
- plan: `docs/superpowers/plans/2026-10-05-positive-ev-factor-search-plan.md`
- 上一份 changelog: `docs/superpowers/changelogs/2026-10-06-positive-ev-factor-search-p24-p26.md`
