# oi_gated_momentum 实施计划

> 日期: 2026-09-18。上游: spec v2.1（`docs/2026-09-18-oi-gated-momentum-spec.md`，
> 宿主评审 Conditional Pass 已吸收）+ 宿主里程碑框架。状态: **计划待批**。
> 原则: 每步有阻断断言，断言不过不进下一步；全程不动快环 prompt/预算。

## 步骤一：数据层就绪与总持仓回填（spec §3.1/§7.1）

**目标**：`futures_m.db` 新表 `index_continuous_1d` 落数据，总持仓口径可用。

1. 新建 `scripts/fetch_index_continuous.py`（镜像现有采集脚本模式：
   TqSdk `KQ.i@m` 日线，复用 `.env.praxist`/现有 TQSDK 凭据与 fetcher）；
2. 回填 2016-01-05 → 今 → `index_continuous_1d`（dt, close_price, volume,
   open_interest）；之后并入 `daily_update.py` 每日增量（与现库同节奏）；
3. **数据质量阻断断言（不过不进步骤二）**：
   - `open_interest` 2016→今无空洞、无零值；
   - 提取历史主力换月关键日（12 月中旬 m01→m05、4 月中旬 m05→m09 等），断言
     ΔOI^tot_5d 极值在 ±25% 内——**绝对不允许**单合约口径 >100% 的脉冲突变；
   - 与 M_CONT 日历差集为空或逐日可解释（缺失日 → NaN 落表记录，禁 ffill）。

**交付**：表 + 采集脚本 + 断言脚本/测试 + 数据质量报告。
**风险**：KQ.i@m 历史 OI 深度不足（§7.1 开放问题）——触发即回退逐合约回填求和
方案（成本更高，需重新评审步骤一工作量）。

## 步骤二：独立模块开发与单元测试闭环（spec §4/§6.1）

**目标**：`cascade/oi_gated_momentum.py` 纯函数 + 全绿验收测试。

1. 实现 `compute_oi_gated_momentum`，**严格按 spec §4.1 标准实现口径**
   （定标算子显式 shift(1)，因子本体用当期 bar）；
2. §6.1 验收用例逐项落地，重点：
   - 四象限断言：减仓上涨/减仓下跌严格输出 0.0；
   - **标尺无样本内污染断言**（§4.1）：扰动 bar t 输入 → scale_p/scale_oi 逐位
     不变；扰动 t−1 → scale 变化；
   - 非对称定标抗扰：注入连续减仓 50%，scale_oi 不变；
   - pct_change(5) 算子钉死；NaN/inf/bool → NaN；分位数 ≤1e-6 → NaN；预热期 NaN；
   - 确定性逐位相等；
3. 测试文件 `tests/test_oi_gated_momentum.py`，与仓库测试风格一致。

**交付**：模块 + 测试（预计 ~10 用例）+ 全绿证据。
**门槛**：tests 全绿方可进步骤三。

## 步骤三：评估器通用改动与回归测试（spec §5/§6.3）

**目标**：aligned 评估器支持 gated 协变量，既有裁决零漂移。

1. 评估器增加通用 `"gated": true` 能力（covariate 配置声明 → 按 Signal≠0 掩码
   计算 active_dir_acc，落库 `active_dir_acc`、`n_active`、`n_total`；0 信号样本
   退出分母但计数保留）；
2. **通用开关而非按名特判**；n 门挂 n_active ≥ 350；
3. **回归门槛（阻断）**：运行慢环 PIN 测试套件 + 相邻回归，断言全库现存活跃
   协变量评估指标浮点精度内**逐位一致**（未声明 gated 的协变量路径零改动）；
4. 若 PIN 测试固化了 dir_acc 计算细节，按仓库流程同步改 PIN（记录在案，不静默）。

**交付**：评估器 diff + PIN 同步记录 + 回归全绿证据。

## 步骤四：协变量注册与慢环首跑（spec §5）

**目标**：注册入池 experimental，实测 n_active 落预期区间。

1. `scripts/extract_xreg.py` 注册 `oi_gated_momentum`（声明 `"gated": true`）；
2. `covariate_pool.json` 入池 status=**experimental**（menu 挂 host testing 栏，
   不进快环可提案范围）；
3. 提交慢环 aligned 评估首跑，核实：
   - **n_active 落 300~360 区间**（spec §7.3 预期）；若 <350 → 近失误自动复测
     通道窗口加深，不放宽 n 门；
   - active_dir_acc 结果无论过门与否，全部落 verdicts 留痕；
   - 对照诊断（raw momentum 基线）同表落库。
4. 首跑结果回报宿主，决定转 active 或 kill。

**交付**：入池 commit + 首跑 verdict + 汇报。

## 里程碑依赖与回滚

```
步骤一(数据) ──断言──► 步骤二(模块) ──测试全绿──► 步骤三(评估器) ──零漂移──► 步骤四(注册首跑)
     │                     │                        │
     └─ KQ.i@m 深度不足 ──► 回退逐合约回填          └─ 回归不过 ──► 停, 修复后重跑
```

- 每步独立 commit，可单独回滚；
- 全程 supervisor 不重启、快环不受影响（步骤四入池 experimental 后菜单自动再生，
  快环不可提案，无行为影响）；
- 步骤三评估器改动在 supervisor 运行中生效的时点：aligned 评估由慢环进程独立执行，
  下一次慢环拉起时自然加载新代码，无需重启 supervisor。
