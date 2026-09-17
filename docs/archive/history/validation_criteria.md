# 模型固化判据 (Validation Criteria) v2 · 2026-07-30

> 适用范围: FM_a 级联预测协变量固化实验 (Phase 4 起)。
> 替代旧版"纯 OR 三选一"判据 (`MAPE_REL_DROP=0.03 OR DIRACC_DELTA=3pp OR PF_REL_GAIN=0.10`)。
> 实现参考: `scripts/phase4d_parse_results.py`。

## 1. 背景

Phase 4d (calendar_cyclical 固化) 回测暴露了 v1 "纯 OR 判据" 的结构性漏洞:

- **SP 案例 (Additive 模式)**: MAPE 相对降 -6.8% 达标, 但 PF 1.40→1.38 (-1.4%)、EV +0.167→+0.157 (-0.010) 微降, 仍被旧判据放行为 PASS。
- **SR 案例 (Additive 模式)**: DirAcc +2pp (差 1pp 未达 3pp 门槛), 但 MaxDD -19.55%→-9.81% (腰斩, 相对改善 50%), EV +0.076→+0.093 (+22%); 旧判据因 DirAcc 差 1pp 给出 FAIL, 漏掉了"回撤大幅改善"的实质价值。
- **CF 案例 (Additive 模式)**: EV 从 -0.029 翻正到 +0.043 (策略级胜利, 从亏损转盈利), 旧判据仅因 DirAcc +5pp 达标, 未识别"EV 翻正"的质变优先级。
- **UR 案例**: n=303 < 350, MaxDD/PF 全维恶化给出负结果, 但样本量不足 350, 统计功效不足, 不应作为最终否决依据。

根因: MaxDD 与精度指标 (MAPE/DirAcc) 完全正交 (一个协变量可以提精度同时翻倍回撤), EV 捕获非对称盈亏 (DirAcc 同值可对应相反 EV), 旧判据两者都未纳入。

## 2. 五条新规则

### Rule 1 — MaxDD 一票否决 (Veto)

无论精度指标如何提升, **MaxDD 相对恶化 > 20% 直接否决**。

公式:
```
MaxDD_relative_worsen = (|MaxDD_new| − |MaxDD_baseline|) / |MaxDD_baseline|
```

注: MaxDD 为负值, 公式用绝对值 |·| (回撤幅度), 正值=恶化。
- 例: baseline MaxDD = −35%, new MaxDD = −50% (回撤加深)
- 相对恶化 = (|−50| − |−35|) / |−35| = (50 − 35) / 35 = +42.9% > 20% -> **否决**
- 例: baseline MaxDD = −20%, new MaxDD = −22% -> 相对恶化 = (|−22| − |−20|) / |−20| = (22 − 20) / 20 = +10% (恶化 10%) -> 不否决

### Rule 2 — 盈利保护 (Profit Guard)

当常规达标中**仅 MAPE 单项达标** (DirAcc 和 PF 均未达标) 时, 强制要求 **PF 相对退化 ≤ 2%**, 否则否决。

公式:
```
PF_relative_degrade = (PF_baseline − PF_new) / PF_baseline
```

- PF_relative_degrade > 0.02 → 否决
- 若 DirAcc 达标或 PF 达标任一成立, Rule 2 不触发
- 典型触发场景: SP Additive (MAPE -6.8% 达标, 但 PF -1.4% 退化; 1.4% < 2% → 险过)

### Rule 3 — EV 质变绿色通道 (EV Green Channel)

若 baseline EV < 0 且 new EV > 0 (**从亏损翻正到盈利**), 自动解锁固化资格, 直接 PASS, 无视其他常规指标 (仍受 Rule 1 约束: MaxDD 不能恶化 >20%)。

- 语义: 策略从"长期亏钱"变"长期赚钱"是质变, 优先级高于任何精度指标。
- 典型案例: CF Additive (EV -0.029 → +0.043) → Rule 3 PASS。

### Rule 4 — MaxDD 回撤绿色通道 (MaxDD Green Channel)

在 **EV 不显著退化** (`EV_new ≥ EV_baseline − 0.01`) 前提下, 若 MaxDD 绝对改善或相对改善任一达标, 自动解锁固化资格:

- 绝对改善: `|MaxDD_new| ≤ |MaxDD_baseline| − 10pp` (MaxDD 绝对值下降 ≥ 10 个百分点)
- 相对改善: `(|MaxDD_baseline| − |MaxDD_new|) / |MaxDD_baseline| ≥ 0.30` (MaxDD 绝对值相对改善 ≥ 30%)

公式:
```
MaxDD_relative_improve = (|MaxDD_baseline| − |MaxDD_new|) / |MaxDD_baseline|
```

- 典型案例: SR Additive (MaxDD -19.55%→-9.81%, 绝对改善 9.74pp 接近 10pp, 相对改善 = (19.55−9.81)/19.55 = 49.8% ≥30%; EV +0.076→+0.093 未退化) → Rule 4 PASS。
- 与 Rule 1 的区别: Rule 1 是"恶化太多就否决"; Rule 4 是"改善足够多就直接过"。

### Rule 5 — 小样本标记 (Underpowered)

- **有效门槛**: `n ≥ 350` 为统计有效样本量。
- **n < 350 且结果为负面** (FAIL): 标记为 `UNDERPOWERED`, 不作最终否决依据, 需补数据重测。
- **n < 350 但结果为正面** (PASS/Green): 仍标记 `underpowered-note` 提醒, 但不阻断判定 (正向结果在小样本下更可能是过拟合而非漏检, 固化需谨慎但不拒绝)。
- 典型案例: UR n=303, 所有模式均 FAIL → UNDERPOWERED, 待补数据复测。

## 3. 保留的常规达标维度 (Ordinary Pass)

以下三者任一达标即满足常规维度 (仍受 Rule 1/Rule 2 约束):

| 维度 | 阈值 | 公式 |
|------|------|------|
| MAPE 相对下降 | ≥ 3% | `(MAPE_base − MAPE_new) / MAPE_base ≥ 0.03` |
| DirAcc 绝对提升 | ≥ +3pp | `DirAcc_new − DirAcc_base ≥ 3` |
| PF 相对提升 | ≥ +10% | `(PF_new − PF_base) / PF_base ≥ 0.10` |

## 4. 判定流程

按以下顺序评估, 命中即提前返回:

```
1. 绿色通道优先 (Rule 3 / Rule 4)
   ├─ 若 Rule 3 命中 (EV 翻正) 且 Rule 1 未否决 → GREEN-EV PASS
   ├─ 若 Rule 4 命中 (MaxDD 大幅改善且 EV 未退化) 且 Rule 1 未否决 → GREEN-MAXDD PASS
   └─ 否则继续

2. 常规达标 (MAPE / DirAcc / PF 任一 ≥ 阈值)
   ├─ 未达标 → FAIL (进入 Step 4 样本量检查)
   └─ 达标 → 进入 Step 3

3. 否决检查 (对常规达标品种)
   ├─ Rule 1 MaxDD 恶化 > 20% → FAIL (MaxDD veto)
   ├─ Rule 2 仅 MAPE 单项达标且 PF 退化 > 2% → FAIL (profit guard)
   └─ 否则 → PASS (ordinary)

4. 样本量标记 (Rule 5)
   ├─ n < 350 且结果为 FAIL → UNDERPOWERED (不作最终否决)
   └─ n ≥ 350 → 维持原判定
```

## 5. ASCII 状态标记

输出中使用以下 ASCII 状态码 (禁用 Unicode 符号以兼容 GBK 控制台):

| 标记 | 含义 |
|------|------|
| `PASS` | 常规达标 (MAPE/DirAcc/PF 任一, 未触发 Rule 1/2) |
| `GREEN-EV` | Rule 3 EV 翻正通道 |
| `GREEN-MAXDD` | Rule 4 MaxDD 改善通道 |
| `FAIL` | 未达标或被否决 |
| `UNDERPOWERED` | n<350 的负面结果, 需补数据 |
| `R1-VETO` | Rule 1 MaxDD 恶化 >20% 否决标注 |
| `R2-GUARD` | Rule 2 PF 退化 >2% 否决标注 |

## 6. Phase 4d 案例回顾

应用 v2 判据对 Phase 4d 实测数据的判定:

| 品种 | 模式 | n | 关键变化 | v2 判定 | 命中规则 |
|------|------|---|----------|---------|----------|
| CF | Additive | 396 | EV -0.029→+0.043; MaxDD -35.19→-34.83 (持平) | GREEN-EV | Rule 3 翻正 |
| SR | Additive | 396 | MaxDD -19.55→-9.81 (改善 49.8%); EV +0.076→+0.093 | GREEN-MAXDD | Rule 4 MaxDD 改善 |
| SP | Additive | 396 | MAPE -6.8% 达标; PF -1.4% 退化 (<2%) | PASS | 常规 MAPE; Rule 2 险过 |
| SP | Replace | 396 | MAPE -1.0% 未达; MaxDD -33.76->-66.44 (恶化 96.8%) | FAIL | 常规未达 (MaxDD 亦恶化; 若精度达标会触发 R1-VETO) |
| M | Replace | 396 | MAPE -28.6% / DirAcc +4pp / PF +9.7% | PASS | 常规 MAPE+DirAcc |
| UR | Additive | 303 | 全维变差 (MaxDD -57.71→-76.31 恶化 32%) | UNDERPOWERED | Rule 5 n<350 负结果 |
| JD | Replace | 396 | MaxDD -49->-34 (改善 31%); EV +0.042->+0.045 未退化; 精度持平 | GREEN-MAXDD | Rule 4 MaxDD 改善 (已固化) |

## 7. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1 | 2026-06 | 纯 OR 三选一 (MAPE/DirAcc/PF) |
| v2 | 2026-07-30 | 引入 MaxDD 一票否决、EV/MaxDD 绿色通道、PF 盈利保护、小样本标记 (Phase 4d 升级) |
