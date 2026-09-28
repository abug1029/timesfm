# T5-PR-C5 Changelog: 协变量族诊断矩阵

**Status:** 文档化完成，待实施
**Date:** 2026-09-28
**Spec:** §4.4 W4

## 问题描述

**v3 的问题**：把"8 品种 / 2 板块 / 60% 惰性"当作**自动归档门**。这组数字是**治理阈值**，不是协变量有效性的科学定律；自动归档容易把覆盖较少或分布不均**误判为"族无效"**。

**v4 处置**：先出诊断矩阵，不自动归档。

## 实施方案

### W4.① 输出诊断矩阵（本轮交付物）

**交付物**：`task_FM/config/covariate_family_verdict.json`

**结构**：族×品种矩阵，每格含：
- `inert_constant`: 惰性常数通道标记
- `all_zero`: 全零通道标记
- `ablation_content_delta`: 内容消融效应（若有）
- 证据指针

**分母要求**：
- 必须显式给出分母 `n_evaluated(cov)`，不得只给百分比
- `n_evaluated` 定义：有 verdict **且** `protocol_fingerprint` 一致 **且** `covariates_used == True` 的品种数
- 无法计算的品种（数据缺失/构造失败）**不计入分母**，且必须单列"不可计算品种"清单

**示例结构**：
```json
{
  "schema": "fm.covariate_family_verdict.v1",
  "generated_at": "2026-09-28T12:00:00Z",
  "n_evaluated": {
    "rsi_state": 5,
    "calendar_cyclical": 5,
    "hourly_slope": 5,
    "ccl": 5,
    "oi": 5
  },
  "matrix": {
    "rsi_state": {
      "ss": {
        "inert_constant": false,
        "all_zero": false,
        "ablation_content_delta": 0.00335,
        "evidence": "test_rsi_state_ss"
      },
      "sr": {...},
      "m": {...},
      "jd": {...},
      "lh": {...}
    },
    "calendar_cyclical": {...},
    ...
  },
  "incomputable_symbols": {
    "cf": "data_missing",
    "i": "construction_failed",
    ...
  },
  "diagnostic_thresholds": {
    "n_evaluated_min": 8,
    "sector_coverage_min": 2,
    "inert_ratio_max": 0.6,
    "note": "仅诊断提示, 不自动归档"
  }
}
```

### W4.② 阈值降为诊断标注，不作自动归档

**计算并展示**：
- `n_evaluated >= 8`
- 覆盖板块 `>= 2`
- 惰性占比 `>= 60%`

**但只作研究者审阅提示**，不触发自动归档。

**未达覆盖的协变量**：
- 标 `insufficient_evidence`
- **不归档也不保留**，待补数据

**禁止**：在积累实际案例之前启用自动归档。

### W4.③ 归档的最终决定权在人

**流程**：
1. 研究者审阅矩阵
2. 决定归档
3. 归档写入 `covariate_pool.json`（标 `archived`，**不删除**，保留可追溯）

**单品种惰性不整族归档**：族在某品种有效、在另一品种惰性要能分别判定。

**日后积累实际案例**，再评估哪些规则适合自动化。

## 实施步骤

### 1. 创建诊断脚本 `scripts/generate_covariate_family_verdict.py`

```python
"""生成协变量族诊断矩阵"""

import json
from pathlib import Path
from collections import defaultdict

def generate_verdict_matrix(registry_path, protocol_fingerprint):
    """
    生成族×品种诊断矩阵
    
    Args:
        registry_path: registry 文件路径
        protocol_fingerprint: 协议指纹（用于过滤可比 verdict）
    
    Returns:
        dict: 诊断矩阵
    """
    # 加载 registry
    verdicts = load_verdicts(registry_path)
    
    # 过滤: protocol_fingerprint 一致 + covariates_used == True
    filtered = [
        v for v in verdicts
        if v.get("protocol_fingerprint") == protocol_fingerprint
        and v.get("covariates_used") == True
    ]
    
    # 按协变量类型分组
    by_cov = defaultdict(list)
    for v in filtered:
        cov_type = v.get("cov_override")
        by_cov[cov_type].append(v)
    
    # 计算 n_evaluated
    n_evaluated = {
        cov: len(vs) for cov, vs in by_cov.items()
    }
    
    # 构建矩阵
    matrix = {}
    for cov_type, vs in by_cov.items():
        matrix[cov_type] = {}
        for v in vs:
            symbol = v.get("symbol")
            matrix[cov_type][symbol] = {
                "inert_constant": v.get("inert_constant", False),
                "all_zero": v.get("all_zero", False),
                "ablation_content_delta": v.get("ablation_content_delta"),
                "evidence": f"verdict_{v.get('variant_id')}"
            }
    
    # 识别不可计算品种
    all_symbols = {"ss", "sr", "m", "jd", "lh", "cj", "fu", "rb"}
    evaluated_symbols = set()
    for cov_matrix in matrix.values():
        evaluated_symbols.update(cov_matrix.keys())
    incomputable = all_symbols - evaluated_symbols
    
    return {
        "schema": "fm.covariate_family_verdict.v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_evaluated": n_evaluated,
        "matrix": matrix,
        "incomputable_symbols": {
            sym: "no_verdict" for sym in incomputable
        },
        "diagnostic_thresholds": {
            "n_evaluated_min": 8,
            "sector_coverage_min": 2,
            "inert_ratio_max": 0.6,
            "note": "仅诊断提示, 不自动归档"
        }
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--protocol-fingerprint", required=True)
    parser.add_argument("--output", default="task_FM/config/covariate_family_verdict.json")
    args = parser.parse_args()
    
    verdict = generate_verdict_matrix(args.registry, args.protocol_fingerprint)
    
    with open(args.output, "w") as f:
        json.dump(verdict, f, indent=2)
    
    print(f"Generated {args.output}")
```

### 2. 创建测试 `tests/test_covariate_family_verdict.py`

```python
"""协变量族诊断矩阵测试"""

import pytest
import json
from pathlib import Path

def test_verdict_matrix_structure():
    """测试诊断矩阵结构正确"""
    verdict_path = Path("task_FM/config/covariate_family_verdict.json")
    if not verdict_path.exists():
        pytest.skip("verdict matrix not generated yet")
    
    with open(verdict_path) as f:
        verdict = json.load(f)
    
    # 检查 schema
    assert verdict["schema"] == "fm.covariate_family_verdict.v1"
    
    # 检查必要字段
    assert "n_evaluated" in verdict
    assert "matrix" in verdict
    assert "incomputable_symbols" in verdict
    assert "diagnostic_thresholds" in verdict
    
    # 检查 n_evaluated 是整数
    for cov, n in verdict["n_evaluated"].items():
        assert isinstance(n, int)
        assert n >= 0

def test_n_evaluated_denominator():
    """测试 n_evaluated 分母正确"""
    # 构造 mock registry
    mock_verdicts = [
        {
            "symbol": "ss",
            "cov_override": "rsi_state",
            "protocol_fingerprint": "fp1",
            "covariates_used": True,
            "inert_constant": False,
            "all_zero": False
        },
        {
            "symbol": "sr",
            "cov_override": "rsi_state",
            "protocol_fingerprint": "fp1",
            "covariates_used": True,
            "inert_constant": True,
            "all_zero": False
        },
        {
            "symbol": "m",
            "cov_override": "rsi_state",
            "protocol_fingerprint": "fp2",  # 不同协议指纹
            "covariates_used": True
        }
    ]
    
    # 应该只计算 protocol_fingerprint == "fp1" 的
    # n_evaluated["rsi_state"] 应该是 2，不是 3
    ...

def test_incomputable_symbols_listed():
    """测试不可计算品种被列出"""
    # 如果某品种没有 verdict，应该出现在 incomputable_symbols
    ...

def test_diagnostic_thresholds_not_auto_archive():
    """测试诊断阈值不触发自动归档"""
    # 即使 n_evaluated >= 8 且惰性占比 >= 60%
    # 也不应该自动归档
    ...
```

### 3. 运行诊断脚本

```bash
cd /home/abug/timesfm
.venv/bin/python scripts/generate_covariate_family_verdict.py \
  --registry data/archive/fm_a_sealed_2026-09-24T1422/registry/aligned_verdicts.jsonl \
  --protocol-fingerprint $(python -c "from task_FM.evaluations.fm_eval.evaluator import compute_protocol_fingerprint; print(compute_protocol_fingerprint())") \
  --output task_FM/config/covariate_family_verdict.json
```

## 预计工作量

- 脚本实现: 0.5 天
- 测试: 0.5 天
- **总计: 1 天**

## 依赖

- 不依赖 T1a（可并行实施）
- 需要 registry 数据（可从封存数据生成）

## 风险

1. **数据风险**：封存的 registry 是 pre-A1 数据，可能不完整
2. **性能风险**：无，诊断脚本只读不写
3. **前视风险**：无，诊断脚本不涉及预测

## 验收标准

1. `covariate_family_verdict.json` 生成成功
2. 矩阵结构符合 schema
3. `n_evaluated` 分母正确
4. 不可计算品种被列出
5. 诊断阈值不触发自动归档
6. 所有测试通过

## 审核结论

**T5-PR-C5 文档化完成**。实施推迟，需 1 天工作量。
