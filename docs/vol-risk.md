# Vol 风控与 Phase 1 状态

**快照日期：2026-09-10**（v2 布朗运动 CI 扩散已上线）（细节以 `STATE.md` 与 `reports/phase1/` 为准）

## 红线

| 项 | 状态 |
|----|------|
| Absolute Risk Overlay / Neutral 压平 | **默认 OFF** |
| 全宇宙 L1 ops 经济门禁 | **FAIL**（ΔEV ≈ −10.8） |
| L2 扩宇宙 | **暂停** |
| black 独立 R1 模型 | **未训**（resolve → R0 `vol_risk_filter_v2.pkl`，`model_source=r0_fallback_black`） |

## 组件

| 组件 | 路径 |
|------|------|
| 熔断实现 | `cascade/vol_risk_filter.py` (v1 压平 + v2 布朗运动CI扩散) |
| 操作 thr | `models/operational_thr.json`：chem **0.65** / agri **0.45** / black **0.55** |
| R1 chem | `models/vol_risk_filter_chem.pkl` |
| R1 agri | `models/vol_risk_filter_agri.pkl` |
| R0 | `models/vol_risk_filter_v2.pkl` |
| 板块表 | `config/sector_map.py`（唯一） |
| A/B 评分 | `cascade/neutral_ab_report.py`（唯一） |
| L1 ops 产物 | `reports/phase1/full_universe_neutral_r1_ops/` |

## 阈值优先级（ThrPolicy）

`CLI 全局 thr` > `CLI 板块 thr` > `operational_thr.json` > pkl operational > IS calibrated > default 0.55

Agri IS calibrated ≈ 0.62 **高于** OOS 分数上沿 → **禁止**把 IS cal 当生产 thr；用 operational 0.45。

## L1 ops 摘要（2026-07-25）

| 门禁 | 结果 |
|------|------|
| HURTS ≤ 15% | 通过（10%） |
| mean EV ON ≥ OFF | **未过** |
| MaxDD 改善 | 通过 |

代表 HELPS：CF / FU / MA / JD；宇宙 EV 杀手：LH 100% veto（ΔEV 约 −345）。

## 实验开关（非默认）

```bash
# 仅研究：压平 overlay
python scripts/cascade_predict.py fu --vol-filter-neutral --vol-thr 0.65

# 训练 R1（默认 all = chem+agri，不训 black）
python scripts/train_vol_risk_sector.py --sector all
# python scripts/train_vol_risk_sector.py --sector black_metals --force  # 需授权
```

## 可选后续（产品决策，非默认执行）

1. HELPS 白名单 / 排除 LH 后子集经济复判  
2. Agri 分数校准或「有害高波」标签重定义  
3. 法定节假日交易日历  
4. Copilot Paper Trading 打磨  

## 与 Copilot 的关系

盘中 **不要** 默认打开压平网关。Copilot 复用同一 Vol 模型做**雷达**，预测点位保持模型原输出。见 [copilot.md](./copilot.md)。
