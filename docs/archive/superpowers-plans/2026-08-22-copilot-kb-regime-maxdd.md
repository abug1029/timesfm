# Copilot 冒烟 + KB 验证 + Regime 路由 + MaxDD 影响评估

## Context

Phase 11-13 完成后系统经历了大量变更 (13 品种固化, SH 纳入, MaxDD 修复, dir_acc 刷新, KB 重建)。需要验证系统完整性，并评估两个中期方向的可行性。

---

## Task 1: Copilot 冒烟测试

**目标**: 验证 21 品种 scheme 变更后 Copilot 正常运行。

**关键发现**:
- Copilot 无 dry-run 模式，最轻量为 `--no-collect --no-refresh --no-vol-radar`
- 仍需加载 TimesFM 模型 + SQLite 访问
- KB 缺 L1 ECONOMIC_VERDICT.json → `vol_sensitivity` 全为 UNKNOWN

**步骤:**

1. 运行 KB 一致性测试:
```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_kb_schemes_consistency.py -v
```

2. Copilot 冒烟 (单品种快速验证):
```bash
PYTHONIOENCODING=utf-8 python scripts/copilot.py ss --no-collect --no-refresh --no-vol-radar
```

3. 如单品种通过，扩展至全品种:
```bash
PYTHONIOENCODING=utf-8 python scripts/copilot.py --three-star --no-collect --no-refresh --no-vol-radar
```

4. 检查输出: 21 品种均渲染成功，无 KeyError/AttributeError，credit_stars 与 SCHEMES 一致。

**验证标准**: Copilot 启动无报错，所有品种 CLI 表格正常渲染，研报 MD 文件生成成功。

---

## Task 2: KB 一致性验证

**目标**: 确保 KB 与 SCHEMES 完全对齐。

**已有工具**: `tests/test_kb_schemes_consistency.py` 检查 7 个维度:
1. KB 文件存在
2. 品种集合一致 (KB symbols == SCHEMES keys)
3. 协变量匹配 (KB covariate == SCHEMES covariate_types)
4. 星级匹配
5. DirAcc 匹配 (容差 0.01)
6. scheme_type 匹配
7. short_horizon_only 一致性

**步骤:**

1. 运行测试:
```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_kb_schemes_consistency.py -v
```

2. 如有失败 → 重建 KB:
```bash
PYTHONIOENCODING=utf-8 python scripts/build_knowledge_base.py
```

3. 验证重建后 KB 内容:
```bash
PYTHONIOENCODING=utf-8 python -c "
import json
with open('config/knowledge_base.json', encoding='utf-8') as f:
    kb = json.load(f)
syms = kb.get('symbols', {})
print(f'品种数: {len(syms)}')
print(f'含 SH: {\"sh\" in syms}')
# 检查 covariate 一致性
from config.prediction_scheme import SCHEMES
for sym in sorted(SCHEMES.keys()):
    s = SCHEMES[sym]
    expected = '+'.join(s.covariate_types) if s.covariate_types else s.covariate_type
    actual = syms[sym].get('covariate', '')
    if expected != actual:
        print(f'MISMATCH {sym}: KB={actual} SCHEME={expected}')
print('检查完成')
"
```

4. 记录已知问题: L1 ECONOMIC_VERDICT.json 缺失 → vol_sensitivity 全 UNKNOWN（不影响核心功能）。

**验证标准**: 7 项测试全部通过，KB 21 品种覆盖。

---

## Task 5: Regime 动态路由 POC

**目标**: 验证 Regime 动态路由能否突破弱信号品种天花板。

**现状**:
- ✅ Regime 分类器 (K-Means, 4 regimes) — 已完成
- ✅ 特征提取 (10 维 rolling features) — 已完成
- ✅ RealtimeRegimeClassifier (含 hysteresis) — 已完成
- ✅ `regime_gated` 元协变量 (Hurst 加权融合) — 已完成
- ❌ 动态路由未接入 `cascade_predict.py` — **未集成**
- ❌ 数据驱动 regime→covariate 映射 — **硬编码占位**
- ❌ Walk-forward 验证 — **placeholder**

**策略**: 分两步走

### Step 5a: 接入 RealtimeRegimeClassifier 到预测管线 (~1 天)

**修改文件**: `scripts/cascade_predict.py`

在 Stage 2 (hourly prediction) 之前插入:
```python
from cascade.realtime_regime_classifier import RealtimeRegimeClassifier

# 在 hourly_model.predict() 调用前
regime_clf = RealtimeRegimeClassifier()
regime_label = regime_clf.classify(hourly_data)
# 用 regime 选择协变量
regime_cov_map = { ... }  # 从 Phase 11/12 数据构建
cov_type = regime_cov_map.get(regime_label, scheme.covariate_type)
```

### Step 5b: 构建数据驱动 regime→covariate 映射 (~2-3 天)

对每个弱信号品种:
1. 提取 regime 特征 (regime_features.py)
2. K-Means 分类 regime
3. 对每个 regime 分别跑回测 (每个 regime × 每个协变量)
4. 选每个 regime 下 PF 最高的协变量
5. 生成 regime→covariate 映射表

**回测量**: 6 弱信号品种 × 4 regimes × 7 协变量 = 168 tests (~112h)

### Step 5c: Walk-forward 验证 (~1 天)

对比动态路由 vs 静态 baseline:
- 同窗口 walk-forward
- 对比 PF/EV/MaxDD
- 判定是否显著改善

**验证标准**: 至少 1 个弱信号品种动态路由 PF > 静态 baseline + 0.05。

**风险**: 回测量大 (168 tests)，且可能仍无法突破天花板 (P13 已证明组合优化无效)。建议先做 Step 5a (接入管线) 作为基础设施准备，Step 5b 选 1-2 个最有潜力的品种试点。

---

## Task 6: MaxDD 修复影响评估

**目标**: 量化 cumsum→cumprod 修复对所有品种 MaxDD 的影响。

**现状**:
- MaxDD 修复于 2026-08-21 (cumsum → cumprod)
- 194 个 JSONL 条目使用旧 cumsum 方法
- 29 个条目旧 MaxDD < -100% (物理不可能)
- 23 个条目在 -80%~-70% 临界区

**步骤:**

1. **编写对比脚本** `scripts/maxdd_impact_assessment.py`:
```python
"""对比 cumsum vs cumprod MaxDD 影响"""
import json, re, numpy as np
from pathlib import Path

def recalc_maxdd_cumprod(n, daily_returns):
    """从回测日志重建 cumprod MaxDD"""
    # 简化版: 直接用 JSONL 中的旧值做近似对比
    pass

# 1. 扫描所有 JSONL
# 2. 提取旧 MaxDD
# 3. 标记 < -100% 的异常值
# 4. 对关键品种重跑 monthly_backtest.py 获取新 MaxDD
# 5. 生成对比报告
```

2. **快速扫描** (不重跑回测):
```bash
PYTHONIOENCODING=utf-8 python -c "
import json, re, os
anomalies = []
for f in sorted(Path('reports/data_ops').glob('*.jsonl')):
    with open(f) as fh:
        for line in fh:
            d = json.loads(line.strip())
            m = re.search(r'[+-]?[0-9.]+', d.get('maxdd',''))
            if m:
                maxdd = float(m.group())
                if maxdd < -1.0:  # < -100%
                    anomalies.append((f.stem, d.get('label',''), maxdd))
print(f'旧 MaxDD < -100% 的条目: {len(anomalies)}')
for f, l, m in sorted(anomalies, key=lambda x: x[2]):
    print(f'  {f:30s} {l:25s} MaxDD={m:.2%}')
"
```

3. **关键品种重跑** (选 3-5 个 MaxDD 异常最严重的):
```bash
# JM, FG, UR (MaxDD 曾 < -100%)
PYTHONIOENCODING=utf-8 python scripts/monthly_backtest.py jm
PYTHONIOENCODING=utf-8 python scripts/monthly_backtest.py fg
PYTHONIOENCODING=utf-8 python scripts/monthly_backtest.py ur
```

4. **GREEN 状态翻转检查**: 对 13 个已固化品种检查 MaxDD 是否跨越 80% 红线。

5. **生成影响报告** `reports/research/20260822_maxdd_impact_assessment.md`。

**验证标准**: 所有旧 MaxDD < -100% 的条目在新方法下 > -100%，13 个 GREEN 品种无状态翻转。

---

## 执行顺序

```
Task 1 (Copilot 冒烟) ──→ Task 2 (KB 验证)
     ~1h                      ~0.5h
          │
          ↓
Task 6 (MaxDD 影响) ──→ Task 5 (Regime POC)
     ~2-3h                    ~3-5h (Step 5a + 试点)
```

Task 1/2 先做 (验证当前系统完整性)，Task 6 次之 (确认 MaxDD 修复无副作用)，Task 5 最后 (基础设施准备 + 试点)。

## 总时间估算

| Task | 耗时 | 类型 |
|:-----|:----:|:-----|
| 1 Copilot 冒烟 | ~1h | 验证 |
| 2 KB 验证 | ~0.5h | 验证 |
| 6 MaxDD 影响 | ~2-3h | 分析 |
| 5 Regime POC | ~3-5h | 开发 |
| **总计** | **~7-10h** | |
