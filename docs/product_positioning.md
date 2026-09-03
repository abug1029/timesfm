# 产品定位（可交易 Alpha 健康度）

**裁决**: CF-05 **A**（2026-08-08 ultragoal G001）

## 是什么

FM_a / Copilot 是 **主观期货交易的结构辅助**：级联预测路径、加权 1H **可交易方向**、信用星级、波动预警。

## 不是什么

- 不是自动下单系统  
- 不是保证 DirAcc≥65% 的 alpha 黑箱  
- 不是默认启用的 Vol 压平网关  

## 可交易方向（CF-01 A）

| 名称 | 定义 | 用途 |
|------|------|------|
| **可交易方向** | `sign(weighted_1H − base)` via `signal_weight` / short_horizon | 回测仓位、报告主方向、汇总排序 |
| **日线状态** | `daily_slope` vs `trend_threshold_pct` | 仅副标签 / regime 提示 |

实现：`cascade/signal_contract.position_from_forecast`。

## 生产红线

- Vol / Neutral 压平默认 **OFF**  
- 预测输出 **永不因 Overlay 静默压平**（Copilot）  
- **无真实 3 星**；CLI `--three-star` = 信用 `stars≥2`（2026-08-08 新口径 20/20 表：`reports/research/20260808_g005e_results.md`）  
