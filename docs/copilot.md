# Copilot 主观交易领航员

## 定位

| 是 | 不是 |
|----|------|
| 盘中决策辅助（领航员） | 自动下单 / 自动驾驶 |
| 输出完整预测 + 风险标签 | Neutral 压平预测 |
| 展示历史 PF/DirAcc/星级 | 替代固化 `prediction_scheme` |

生产默认：`cascade_predict` 的 vol 压平仍 **OFF**。主观看盘优先：

```bash
python scripts/build_knowledge_base.py   # L1 或 SCHEMES 更新后
python scripts/copilot.py ss fu
python scripts/copilot.py --three-star
python scripts/copilot.py ss --no-refresh    # 不刷盘中 1H
python scripts/copilot.py ss --no-vol-radar  # 关闭波动雷达
```

## 数据流

1. `ensure_fresh_data`（可 `--no-collect` 跳过）
2. 可选 TqSdk 刷新 1H 截面（`--no-refresh` 关闭）
3. Stage1 日线 + Stage2 1H XReg（静态 scheme 协变量）
4. Vol 雷达：`VolRiskFilter.bind_for_symbol(..., mode=r1)` → **只读** evaluate
5. Rich CLI 仪表盘 + `reports/daily/YYYYMMDD_HHMM_<syms>.md`

日线特征用库内收盘；盘中不重算日线。

## 信用背书（knowledge_base）

源：`scripts/build_knowledge_base.py` → `config/knowledge_base.json`

| 字段用途 | 来源 |
|----------|------|
| DirAcc / MAPE / decay / coverage | `prediction_scheme.SCHEMES` |
| PF / EV / vol_sensitivity | L1 `ECONOMIC_VERDICT`（OFF 基线与 HELPS/HURTS 标签） |
| best_hold_period | scheme 类型 + 衰减启发式 |

高波文案按 `vol_sensitivity`：`HELPS` 偏观望、`HURTS` 提示趋势机会（非自动开仓）。

## 研报结构

Markdown 含：结论面板、T+1~T+24 点预测与 P10/P90、止损锚点（tick 整量化 + 方向自适应）、因子快照。

> 2026-09-10: 止损锚点从硬编码文案升级为 `generate_risk_bounds()` — 自动 tick snapping (floor/ceil/round)、价格下界保护、多空方向自适应。

## 与 variety_analysis 的关系

`scripts/variety_analysis.py` 默认融合 Copilot 预测章节；`--no-predict` 可只跑技术面+CCL。

## 纸面对账

弱正主盘（SS/SR/M/JD）的记预测 → 回填 → 周检，见 [paper_trading.md](./paper_trading.md)。

```bash
python scripts/copilot.py ss sr m jd
python scripts/paper_loop.py backfill
python scripts/paper_loop.py health
```

不要用 `--three-star` 当纸面入口（会带上边界 EG/RB）。  
面板「方向」目前仍是日线斜率；账本对账的是 T+24 终点符号。

## 注意

- 首次加载 TimesFM 较慢；多品种共享模型实例
- Windows 终端已强制 UTF-8，避免 GBK 崩溃
- 不要把 Copilot 的「建议」当成已过经济门禁的实盘网关
