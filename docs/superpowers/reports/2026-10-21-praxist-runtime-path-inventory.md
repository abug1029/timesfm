# C0 运行时路径与版本探查报告

**日期**: 2026-10-21  
**执行者**: Phase 2-3 Praxist 集成计划 Task 0-4  
**状态**: ✅ 两项冒烟验证均 PASS，满足进入 Week 1 A2/B2 代码编写条件

---

## 1. Praxist 版本与路径

| 项 | 值 |
|----|-----|
| **版本** | 0.5.0 |
| **安装路径** | /home/abug/timesfm/.venv/lib/python3.11/site-packages/praxist/ |
| **Python 版本** | 3.11 |
| **虚拟环境** | /home/abug/timesfm/.venv/ |

---

## 2. Peer 实际写盘路径

### 2.1 目录结构统计

| 目录类型 | 数量 |
|---------|------|
| **variants/** | 324 |
| **results/** | 550 |
| **findings/** | 325 |
| **proposals/** | 2553 |

实际提案路径: results/gen_2/gen2_peer0/proposals/*.json

---

## 3. 与上游文档路径的差集

| 维度 | 上游文档 | 实际实现 | 差异 |
|------|---------|---------|------|
| **Peer 目录** | peer_001/ | gen2_peer0/ | 命名约定不同 |
| **提案文件** | p_001.json | symbol_mechanism.json | 语义化命名 |

结论: 路径结构基本一致，命名约定差异为设计意图。

---

## 4. Task-local Plugin 检查

- task.yaml: task_FM/task.yaml (schema_version: 1)
- 现有 Plugin: task_FM/.praxist/plugins/panel_topologies/fm_two_peer/
  - name: fm_two_peer
  - kind: panel_topology
  - version: 0.1.0

---

## 5. 冒烟验证 1 — Plugin 加载能力

**结果**: ✅ **PASS**

Plugin manifest 结构完整，可被正确解析。

---

## 6. 冒烟验证 2 — Agenda Schema 验证

**结果**: ✅ **PASS**

Agenda schema 包含所有必要字段:
- generation, mainline_observation, cross_peer_hypotheses
- kill_condition, promote_condition, source_findings
- minimal_test, bottleneck_target, evidence_stage

---

## 7. 综合结论

### C0 前置阻塞门状态

| 验证项 | 状态 |
|--------|------|
| Praxist 版本确认 | ✅ PASS |
| Peer 写盘路径确认 | ✅ PASS |
| Plugin 加载能力 | ✅ PASS |
| Agenda Schema 验证 | ✅ PASS |

### 是否满足进入 Week 1 A2/B2 代码编写条件

**✅ 是** — 两项冒烟验证均 PASS，C0 前置阻塞门已打开。

---

**报告生成时间**: 2026-10-21  
**下一步**: 进入 Week 1 A2/B2 代码编写阶段
