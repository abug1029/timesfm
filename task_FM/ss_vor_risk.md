# ss_vor 风险登记

> 登记日期: 2026-09-17。性质: **风险敞口披露**，非缺陷修复。

## 风险定性

ss_vor 是当前**唯一固化进 SCHEMES（stars=2, covariate_type=vor）但在 aligned_verdicts.jsonl（27 条）中无对应条目**的学说。其既有数字（PF=1.123 / EV=+11.06 / n=396）是 v22 口径产物，仅存在于 STATE.md（已加「旧口径线索·非证据」标签）与 SCHEMES 注释行，**不构成 v23 证据**。

## 消费方

- config/prediction_scheme.py 的 SCHEMES["ss"]（stars=2、covariate=vor、dir_acc=0.530）
- config/knowledge_base.json（SS 条目 covariate=vor / credit_stars=2；2026-09-17 重建后 PF/EV 已降级为 null）
- monthly_backtest / three_star_predict（按 SCHEMES 固化方案取协变量）

## 已同步的标注

- prompt_base.jinja2：已改写为「v22 时代遗留候选，不得引用回测数字」。
- STATE.md：v22 数字已加「旧口径线索·非证据」标签。
- config/knowledge_base.json：scripts/build_knowledge_base.py 增加 L1 缺失显式降级（mode=schemes_snapshot_no_L1），全表 PF/EV=null。

## 处置：v23 复测入队

复测已通过慢环**文件队列机制**登记（无需重启 supervisor；运行中的 supervisor 每轮经 _queue_busy() 感知队列非空，自动排入 slow 相位）：

- 队列：data/cache/aligned_pending.jsonl，行内容：variant_id=ss_vor, symbol=ss, cov_override=vor, max_points=600, stage=aligned, source=ss_vor_v23_retest（写入走 registry_lib.queue_enqueue 带锁追加）
- 消费：scripts/aligned_slow_loop.py 经 queue_claim 认领执行，裁决追加回 task_FM/config/aligned_verdicts.jsonl
- 口径：max_points=600 满足 v23 350-600 硬门约束；复测按 v23 评估（DirAcc/DM/BH-FDR），不复现 v22 PF/EV

复测完成前，ss_vor 的 SCHEMES 固化与 KB ★2 展示**不作为 v23 证据使用**。
