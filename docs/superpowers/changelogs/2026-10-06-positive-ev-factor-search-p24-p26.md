# 2026-10-06 正期望协变量搜索 P2.4/P2.5/P2.6 落地

## 会话恢复背景
- 上次会话因 bun 崩溃中断，P2.4 实现已完成（commit `7c8a7e0`）但专家审核被中断。
- 本次会话恢复 P2.4 审核 → P2.5 实现+审核 → P2.6 实现+审核。

## 提交
- **7c8a7e0** P2.4: 搜索树停止四规则——`evaluate_tree_stops` 巡检 + stop 落账接线 + P2.3 审核处置
- **3556eed** P2.5: `delta_post_shrunk` 落账 + `n_required` 途径 B（vif=1，长程方差）
- **9a62bde** P2.6: `incremental_vs_incumbent` 落账——现任增量 DM（spec §6.4/§5, T7/T14）
- **a047a20** changelog: P2.4/P2.5/P2.6 落地记录

## P2.4 要点（停止四规则）
- `scripts/search_trees.py`：`evaluate_tree_stops(index, snapshot, dead_families)` 纯函数（§6.5 条件序 first-hit：budget→dominated→family_dead；promoted 由 2.7 事件驱动不巡检）；dominated fail-closed（se 不可算节点不参与、现任 se 缺禁用、无现任下界 0、严格小于、δ 平手取 se 较大者保守）；M1 重放通道（崩溃窗口 A 的 root 重放——同 proposal_id 已是未停止树成员且该成员尚无当前协议裁决→幂等放行；已裁决成员陈旧重扫仍撞 busy）；M3 B/τ 读侧闸；N2 stop_reason 枚举写入闸。
- `scripts/praxist_supervisor.py`：`_sweep_search_stops(goal, log, snapshot)` enforce-only；主循环 materialize 后、同轮收割前插桩；N4 防御跳过；M2 docstring 勘误。
- 新测试 `tests/test_search_tree_stop_rules_20261006.py`（23 用例）。
- **专家审核 VERDICT PASS**（F1 MINOR：no_data 根经 M1 通道逐轮重放重评——判定非本提交引入、与既有非搜索 no_data 重试同型；F2-F5 NIT：T9 端到端联动缺单一测试、N1 批内 first-wins 无测试、M3 tau 字符串 fail-loud、M1 残余滥用面）。

## P2.5 要点（delta_post_shrunk + n_required 途径 B）
- `task_FM/evaluations/fm_eval/evaluator.py` build_summary 落 `delta_post_shrunk`（float）与并列 `se`（2.4 dominated 消费行内 se）；se 不可算→两者 null。
- `cascade/statistical_tests.py` 新增 `paired_delta_se`、`shrink_delta_post`、`n_required_via_long_run(d_t, delta_post)`；后者恒 vif=1、var_d=长程方差（T10 锁定）。
- `scripts/registry_lib.py` 登记 `se`/`delta_post_shrunk` 到 `VERDICT_FIELDS_V2`/`_NULLABLE`。
- 新测试 `tests/test_search_delta_post_20261006.py`（21 用例）。
- **核心解读**：se 可算按 spec §5 由 d_t 本身判定（T≥2 且长程方差有限正），与 dm_status/missingness 正交（生产 dm_status 多为 set_mismatch_descriptive，若按锚点收窄则 delta_post_shrunk 恒 null、2.4/2.7 永久休眠）。
- **专家审核 VERDICT PASS**（M1 核心解读裁定可接受；M2 低 T 不可逆 stop 风险留待 2.4/2.7 复核；M3 分期落账可接受；3×NIT）。

## P2.6 要点（现任增量 DM）
- `scripts/aligned_slow_loop.py` 新增 `find_incumbent`（现任定位：同品种+当前协议+status=ok+gate_pass=True+δ最大，tiebreak variant_id 字典序）、`load_incumbent_points_from_checkpoint`（现任 checkpoint 序列获取，协议指纹门，文件级弃读→None）、`compute_incremental_vs_incumbent`（复用 pair_dir_ok_series_with_diagnostics + diebold_mariano_p，严格 spec 判据）。
- `scripts/registry_lib.py` 登记 `incremental_vs_incumbent`（取值 ∈ {pass, fail, not_applicable}）。
- 新测试 `tests/test_search_incremental_incumbent_20261006.py`（23 用例）。
- **生产活性风险**：严格照 spec §6.4 的 `dm_status∈{ok, set_mismatch_ok}` 会让增量恒 fail（生产 169/376 行 set_mismatch_descriptive、missingness_admissible 默认 False），晋升永不发生。本实现忠实 spec 未放宽；**2.7 接线时宿主需裁定**是否调整口径或修订 spec。
- **专家审核 VERDICT PASS**（生产活性风险裁定为「忠实 spec、不构成 MAJOR、2.7 宿主裁定」；2×NIT：测试注释归因错误、TestGatePassUnaffected 覆盖偏浅）。

## 回归对照
| 阶段 | 全量 | 基线 | 新增 |
|------|------|------|------|
| P2.4 后 | 18F/1727P/5S/1X/9E | 18F/1727P | +23 新测试 |
| P2.5 后 | 18F/1748P/5S/1X/9E | 18F/1727P | +21 新测试 |
| P2.6 后 | 18F/1771P/5S/1X/9E | 18F/1748P | +23 新测试 |

失败集逐项恒等、零新增；协议指纹 `f02b2a43` 不变；`baseline_metrics.json` 零重生。

## 遗留（2.7 前置）
1. **生产活性风险**：现任增量 DM 的 `dm_status∈{ok, set_mismatch_ok}` 判据在生产几乎恒 fail，晋升门 2.7 接线前宿主需裁定是否调整 `missingness_admissible` 透传或修订 spec。
2. **低 T 不可逆 stop 风险**（P2.5 M2）：T∈[2,49) HAC 不稳定 + 2.4 dominated 停止不可逆，建议 2.7/2.4 复核是否将 se 可算下界对齐 dm_min_common(50)。
3. **NIT 修正**（可延后）：P2.4 F2-F5、P2.5 N1-N3、P2.6 N-1/N-2。
4. **晋升门 2.7**：六条件（spec §6.6）+ preregistry.jsonl 追加行（n 继承、键型 `["daily_slope", cov_override]`、指纹追加时点锁定）+ T8/T15/T16。

## 下一步
- P2.7 晋升判定 + prereg 追加（T8/T15/T16）+ 专家审核。
- P2.8 known_verdicts 树节 + 注记 + prompt 教学（§6.8/6.9）。
- P2.9 shadow 计数（T1）。
- P2.10 全量回归 + 指纹核对 + 失败集恒等。
- P3 合入部署 + 监督环重启核对。
- 专家总代码审核 + 收尾报告 + P4 shadow 交接。

## 相关文档
- **spec**: `docs/superpowers/specs/2026-10-05-positive-ev-factor-search-spec.md`
- **plan**: `docs/superpowers/plans/2026-10-05-positive-ev-factor-search-plan.md`
- **changelog**: `docs/superpowers/changelogs/2026-10-06-positive-ev-factor-search-p24-p26.md`（本文件）
- **todolist**: DevEco 会话状态（非仓库文件），通过 `todowrite` 工具维护
