# 协变量组合路径补齐与 HL 循环准备 (2026-09-11)

## 会话目标

继续 WSL TimesFM 项目的协变量组合策略工作，为启发式探索（HL 循环）奠定基础。

## 完成的工作

### 1. 问题识别

**协变量池状态** (task_FM/config/covariate_pool.json):
- 注册总数: 30 个协变量
- 家族分布: 9 个 (volatility, trend, structure, oscillator, positioning, calendar, volume, statistical, price_action)

**路径支持差异**:
- 单路径 build_covariate_matrix: 支持全部 30 个
- 组合路径 build_combo_covariate_matrix: 只支持 26 个

**缺失的 4 个协变量**:
1. basis_momentum (structure) - 基差动量，期限结构变化速度
2. ccl (positioning) - 仓差线，主力资金净持仓方向
3. gated_slope (trend) - Hurst 门控斜率，趋势市放大/震荡市缩小
4. regime_gated (statistical) - 体制自适应融合，根据 Hurst 动态加权 PCA/RSI/OI

### 2. 实现补齐

**修改文件**: cascade/features.py

在 build_combo_covariate_matrix 函数中添加 4 个 elif 分支（~80 行代码）：

- basis_momentum: 从 store.get_basis_1h() 读取基差，计算 rolling slope (window=48)，Horizon 向 0 衰减
- ccl: 从 df_1h[ccl_value] 读取仓差，调用 calc_ccl_pct() 归一化，Horizon 填零
- gated_slope: daily_slope x Hurst 门控因子 (sigmoid 映射 H -> [0.3, 2.0])
- regime_gated: 根据 Hurst 动态加权 PCA/RSI/OI 融合

**更新 supported 列表**: 新增 4 个协变量到支持列表

### 3. 测试更新

**修改文件**: tests/test_combo_parity.py

添加参数化测试 test_combo_new_covariates 验证 4 个新协变量
更新 test_combo_unsupported_raises 使用真正不支持的协变量名称

### 4. 测试结果

35 个协变量相关测试全部通过:
- test_covariate_pool.py: 6 tests
- test_new_covariates.py: 16 tests  
- test_combo_parity.py: 13 tests (含新增 4 个)

### 5. Git 提交

commit 9653264
feat(features): 补齐 combo 路径 4 个缺失协变量 (basis_momentum/ccl/gated_slope/regime_gated)

- build_combo_covariate_matrix 现在支持全部 30 个注册协变量
- 新增 ~80 行实现代码，遵循单路径逻辑
- 更新 supported 列表和错误消息
- 添加参数化测试 test_combo_new_covariates
- 35 个协变量相关测试全部通过

Co-Authored-By: Claude Code <noreply@anthropic.com>

3 files changed, 459 insertions(+), 3 deletions(-)

## 当前状态

组合路径支持全部 30 个注册协变量，可以开始启发式探索。

## 基线指标（SS 不锈钢）

ss_vor (最佳单协变量):
- PF: 1.123
- EV: 11.06
- IC: 0.060
- MaxDD: -35.25%
- DirAcc: 53%
- n: 396
- gate_pass: true

## 下一步：启发式探索（HL 循环）

### 候选组合假设（按优先级）

1. vor + oi (波动率 + 持仓)
   经济含义: VOR 捕捉投机活跃度，OI 捕捉资金流向
   
2. vor + ccl (波动率 + 仓差)
   经济含义: VOR 活跃度 + CCL 主力资金方向
   
3. vor + gated_slope (波动率 + 门控趋势)
   经济含义: 波动率 + Hurst 自适应趋势
   
4. vor + regime_gated (波动率 + 体制自适应)
   经济含义: 波动率 + 元信号

### 测试命令

cd /home/abug/timesfm
source .praxist-venv/bin/activate
python3 scripts/monthly_backtest.py --symbol ss --combo "vor,oi" --max-points 400

### 接受门槛

- Sortino: 严格高于基线
- PF: >= 1.067 (1.123 - 5%)
- EV: >= 10.51 (11.06 - 5%)
- MaxDD: <= -33.25% (-35.25% + 2pp)
- DirAcc: >= 50% (53% - 3pp)
- n: >= 50

### 反过拟合纪律

- 每个改动必须有经济含义
- 禁止窄坑过滤
- 禁止未来函数
- 保证样本量
- 训练/验证分离

## 下次会话继续

重启电脑后，继续 HL 循环:

cd /home/abug/timesfm
source .praxist-venv/bin/activate
python3 scripts/monthly_backtest.py --symbol ss --combo "vor,oi" --max-points 400

查看结果:
tail -20 task_FM/config/aligned_verdicts.jsonl | python3 -m json.tool

---
会话结束时间: 2026-09-11 12:30
