# 技术债清单

> **代码基线**: `69c5cca`

本文件登记已识别但暂未修复的技术债务。每条记录包含优先级、修复方案和前置条件，供后续重启时按序处理。

---

## E1-EXT-MISMATCH: 经济判决生成器与 KB 扩展名不一致

**优先级**: 高（E1 重启前置修复项）
**发现日期**: 2026-10-09
**发现来源**: Q1 核实（批次 E）
**状态**: 待修复

### 问题描述

- `l1_economic_verdict.py` 的 `--out` 参数默认值为 `ECONOMIC_VERDICT.md`
- `build_knowledge_base.py:23` 的 `DEFAULT_L1` 默认读取 `ECONOMIC_VERDICT.json`
- 即使上游 `universe_eligibility.json` 齐备、生成器跑通，默认参数也对不上
- 生成器产出永远不被 KB 读取

### 修复方案

改生成器 `--out` 默认值为 `.json`（与 KB 读取方一致）

### 影响范围

- `scripts/l1_economic_verdict.py`
- `scripts/build_knowledge_base.py`

### 前置条件

- E1 重启（Q1 当前裁定为 (c) 放弃）
- 上游 `universe_eligibility.json` 重建或找到

### 参考资料

- `docs/superpowers/reports/2026-10-08-d4-d5-n10-e1-q-rulings.md` §1
- `docs/superpowers/specs/2026-10-08-open-issues-closure-spec.md` §2.3
