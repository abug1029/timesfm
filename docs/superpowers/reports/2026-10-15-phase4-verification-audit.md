# 审核：2026-10-15 Phase4 集成验证报告

- 对象：`/home/abug/timesfm/docs/superpowers/reports/2026-10-15-phase4-verification.md`（mtime **2026-10-15 20:17 CST**；1489B；随 `1fb1c6b` 入库）
- 对照代码/数据：SymbolLock 测试、`sup_evidence` 冷却测、`baseline_metrics.json`、`baseline_points_{fg,cj}_nocov.jsonl`、`check_baseline_coverage.py`
- Box 镜像：`/workspace/shared/reviews/2026-10-15-phase4-verification-audit.md`
- 审核时间：2026-10-15 20:57 CST

## 1. 结论

**有条件通过。**  
报告作为 Phase4 证据：**fg/cj 基线与 metrics、阈值 336、覆盖度 24/27、10 单元测（正确环境下）** 可复核；但 **并发叙事强于测试断言**、把 10 测全挂在「冷却」节、覆盖度定义与 SPEC 不符，且 **未记录 PYTHONPATH / 测试写 live breaker 的副作用**。不宜单独支撑「无条件 Phase4 通过 → 可全量部署」而不读代码侧缺口（gbp 未迁 SymbolLock）。

## 2. 验证项对照

| # | 报告声称 | 实况 | 判定 |
|---|----------|------|------|
| 1 | 并发：A 获锁→B 等待→A 释放→B 获锁；无死锁无残留 | 单测仅「持锁时子进程超时失败」+ exception 清理；**无释放后成功交接** | **部分支持** |
| 2 | fg：588 行；n=588；vid=f02b2a43… | `…_fg_nocov.jsonl` 588；metrics 含 n/vid/dir_acc/endpoint_mape/n_eff | **属实** |
| 3 | cj：同上 | 同上，同 vid | **属实** |
| 4 | 「冷却+频率」下 **10** 测全过（6.49s）；列出 5 个 cooldown 名 | 实为 **5 lock + 5 cooldown**；列出的 5 名均存在且逻辑正确；需 `PYTHONPATH=scripts:.` | **数字属实、归类误导、缺环境** |
| 5 | `_BASELINE_STALENESS_MAX_H` 336 已生效 | `sup_evidence.py` L1221 = 336 | **属实** |
| 6 | 覆盖度 24/27=88.9%，pp/bz/eb 未覆盖 | 现跑一致 | **数字属实**；定义仅为 `n>0`，**≠** SPEC「cutoff 窗」；**<95%** 门闩 |
| 7 | 结论：锁/冷却/阈值/灰度均正常 → Phase4 通过 | 核心功能大体正常；gbp 双实现与覆盖度定义未披露 | **偏乐观** |
| 8 | 下一步：合并 master、重启、48h 监控 | 报告入库后已合并 `299c764`；重启仍待授权 | **当时表述合理** |

## 3. 证据强度

- **强**：fg/cj 文件与 metrics；常量 336；冷却/频率/兼容单测源码。
- **中**：10 passed（环境依赖；本审核复跑约 13s）。
- **弱**：跨进程「完整握手」故事；覆盖度作为 SPEC 验收。
- **缺失**：gbp 与 SymbolLock 双轨；测试对 `data/cache/baseline_regen_breaker.json` 的写污染（`root='.'` + `_save_regen_breaker`）。

## 4. 风险与建议

1. 改写 §1 并发为与断言一致，或补交接用例。
2. §3 改为「锁 5 + 冷却 5 = 10」并写 PYTHONPATH；测试改 tempfile，避免清 live breaker。
3. §4 注明覆盖度算法与 SPEC 差异及未达 95%。
4. 结论增加「Phase1.3 gbp→SymbolLock 未做，互斥依赖同路径 flock」。

## 5. 结论摘要

**有条件通过。** 灰度数据与阈值/单测主干可支撑「功能已接线」；并发与覆盖度表述需降级，且不能掩盖计划 Phase1.3 缺口。
