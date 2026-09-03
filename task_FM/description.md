# FM_a 协变量搜索 toy 任务包

冻结的 FM_a 评估管线 (monthly_backtest.py 单品种 walk-forward) 上搜索协变量候选。
评估器与裁决口径归 FM_a 所有, 预注册见 config/praxist_task.yaml。

候选三字段扩展为四字段 {symbol, cov_override, max_points, stage}:
diagnostic 档 max_points 1..6 (快筛), aligned 档 350..500 (近全量, 可过预注册硬门 n>=350, IC>=0.05).
