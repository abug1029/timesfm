# T5-PR-C6 Changelog: horizon 尾填充分类系统（W5）

**Status:** 文档化完成，待实施
**Date:** 2026-09-28
**Spec:** §4.5 W5

## 问题描述

**事实（C5）**: 每个协变量的 horizon 尾段都是常数（zeros / 末值 / decay），实测 `hz_std=0, hz_uniq=1`。经 per-variate RevIN 后常数尾归一化为 ~0，**未来段不含任何外生信息**。

**宿主裁定**: 本轮修。这是现有架构缺陷，不是"新增基本面协变量通道"。

## 实施方案

### W5.1 协变量按"未来可知性"强制分类

`task_FM/config/covariate_pool.json` 每个条目**必须**新增 `horizon_known`，取值为受控词表四选一：

| `horizon_known` | 含义 | horizon 填充策略 | 是否算外生信息 |
|---|---|---|---|
| `known_ahead` | cutoff 时点**确实已知**未来值 | 填**真实未来值** | ✅ 是 |
| `persistence` | 未来不可知，但可用末值延续近似 | 填**末值** | ❌ 否 |
| `self_referential` | 未来值来自**模型自身输出** | 现状保留，但**必须标记** | ❌ 否 |
| `unknowable` | 既不可知也无法近似 | 填**末值** + 标记 | ❌ 否 |

**唯一家**: 该分类只写在 `covariate_pool.json`，代码、文档、报告一律读它。

### `known_ahead` 的证据格式（必填）

```json
known_ahead_evidence: {
  "source": "<数据来源>",
  "publication_rule": "<何时可得>",
  "publication_lag": "<公布到可用的时滞>",
  "reconstructable": "<历史可重建方式>",
  "verified_by": "<具名>",
  "verified_at": "<ISO 日期>"
}
```

缺 `known_ahead_evidence` 的协变量**不得**标 `known_ahead`——降级为 `unknowable` 并打 WARN。

### W5.2 填充实现

- `known_ahead` 类：从 cutoff 时点可确定的来源取未来值
- 其余三类：填末值（替代当前 zeros/decay），并落 `horizon_fill="persistence"`
- `horizon_std > 0` 只允许出现在 `known_ahead` 类

### W5.3 前视防护

修 horizon 填充最容易引入前视。必须有不变量：
- 任何 `known_ahead` 取值路径必须经过 `cutoff_ts` 守卫
- 单元测试必须包含"cutoff 后 1 小时的数据不可见"断言

## 实施步骤

### 1. 修改 `covariate_pool.json`

为每个协变量添加 `horizon_known` 字段：

```json
{
  "rsi_state": {
    "horizon_known": "self_referential",
    ...
  },
  "calendar_cyclical": {
    "horizon_known": "known_ahead",
    "known_ahead_evidence": {
      "source": "交易所交易日历",
      "publication_rule": "每年12月公布次年日历",
      "publication_lag": "0",
      "reconstructable": "可用 cutoff 时点当时的日历信息复原",
      "verified_by": "Claude Code",
      "verified_at": "2026-09-28"
    },
    ...
  },
  "hourly_slope": {
    "horizon_known": "self_referential",
    ...
  },
  "ccl": {
    "horizon_known": "unknowable",
    ...
  },
  "oi": {
    "horizon_known": "unknowable",
    ...
  }
}
```

### 2. 修改 `cascade/features.py`

在 horizon 填充逻辑中读取 `horizon_known` 分类：

```python
def _fill_horizon(covariate_type, horizon, cov_pool):
    cov_config = cov_pool.get(covariate_type, {})
    horizon_known = cov_config.get("horizon_known")
    
    if horizon_known == "known_ahead":
        # 从 cutoff 时点可确定的来源取未来值
        # 必须有 known_ahead_evidence
        evidence = cov_config.get("known_ahead_evidence")
        if not evidence:
            raise ValueError(f"{covariate_type} marked known_ahead but missing evidence")
        # ... 填充真实未来值
    elif horizon_known in ("persistence", "unknowable"):
        # 填末值
        return np.full(horizon, last_value)
    elif horizon_known == "self_referential":
        # 现状保留，但标记
        return current_implementation()
    else:
        raise ValueError(f"Unknown horizon_known: {horizon_known}")
```

### 3. 添加校验

在加载 `covariate_pool.json` 时校验：
- 每个协变量必须有 `horizon_known` 字段
- `known_ahead` 必须有 `known_ahead_evidence`
- `horizon_known` 必须是四个受控值之一

### 4. 测试

- 测试 `known_ahead` 协变量有证据时正常填充
- 测试 `known_ahead` 协变量无证据时抛错
- 测试其他三类填充末值
- 测试前视防护不变量

## 预计工作量

- 配置修改: 0.5 天
- 代码实现: 1 天
- 测试: 0.5 天
- **总计: 2 天**

## 依赖

- 不依赖 T1a（可并行实施）
- 需要理解当前 horizon 填充逻辑

## 风险

1. **前视偏差风险**: 修改 horizon 填充最容易引入前视，必须有严格的不变量测试
2. **兼容性风险**: 修改后旧协变量配置需要补充 `horizon_known` 字段
3. **性能风险**: 无明显性能风险

## 验收标准

1. `covariate_pool.json` 所有协变量都有 `horizon_known` 字段
2. `known_ahead` 协变量都有 `known_ahead_evidence`
3. horizon 填充逻辑根据 `horizon_known` 分类处理
4. 前视防护不变量测试通过
5. 所有现有测试通过

## 审核结论

**T5-PR-C6 文档化完成**。实施推迟，需 2 天工作量。
