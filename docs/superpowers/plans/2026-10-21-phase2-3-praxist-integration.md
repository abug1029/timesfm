# Phase 2-3 Praxist 集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 2-3 的生成策略 / 多样性 / 提案卫生能力落到 Praxist 上游的 task 合同与 task-local plugin 体系，使新产生的候选默认不依赖「先写脏提案再 harvest 洗」才能进慢环队列。

**Architecture:** 本计划按 Spec 定义的优先级分三个阶段执行：Phase 0（P0 止血包 + C0 探查）、Phase 1（P1-A 提案卫生 + P1-B 生成策略/多样性）、Phase 2（P1-C 写盘路径对齐 + 可选 P2 垫片）。核心设计：将 `proposal_validator` 前移到 task evaluator 的 Step 0（Fail-fast 短路），**复用已有 Phase 2-3 库代码**（`proposal_validator.py` / `generation_strategy.py` / `diversity_metrics.py`），用 Generation-level Batch Bandit 模式消费反馈生成下一代 agenda，通过多 Role 硬隔离保障配额落地，并在 C1 兼容导入中引入全局幂等键防止重复消费。

**Tech Stack:** Python 3.11 + Praxist 上游框架 + SQLite + Jinja2 templates + pytest + cron

**Spec:** `docs/superpowers/specs/2026-10-21-phase2-3-praxist-integration-spec.md`

## Global Constraints

- **Praxist 边界**：禁止改 `.venv/.../site-packages/praxist/`；禁止无版本钉扎的 `sitecustomize` 永久方案；禁止长期 fork 全量 Praxist
- **Laya 红线**：全文与 PR 描述禁止「训练/进化 Laya」；违规标 P0；禁用词写进 `proposal_validator.py` 与静态检查测试
- **状态机边界**：`variants/` 与 `results/` 定义为非承诺沙盒暂存区（Uncommitted Scratch）；只有物化进入 `findings / frontier / 慢环队列` 才算正式"入库/写盘"
- **写盘前拦截**：`proposal_validator` 作为 `task evaluator` 的 Step 0 前置关卡，一旦不合法立即短路拒绝评估，不消耗算力，**输出 `validation_signal` 留痕供审计追溯**
- **Bandit 模式**：采用 Generation-level Batch Bandit（按代批式更新），禁止按逐次采样的在线 Bandit 语义验收
- **散度计算**：KL/JS 散度告警必须执行拉普拉斯平滑（ϵ=10⁻³）或改用 JS 散度；设置最小样本量门槛 N≥30
- **幂等键**：C1 兼容导入以规范化后的 `variant_id`（或 AST/内容哈希）作为全局幂等键，防止重复消费
- **并发互斥**：导入批处理脚本必须遵守 `local-pc.lock` 纪律
- **并行纪律**：流式启动 bot；本地 PC 写档走 `local-pc.lock`；**无用户明示不 commit/push**（所有 Task 最后一步为 `git status` / `git diff` 自检 + `local-pc.lock` 登记，**未经用户指令严禁执行 `git commit`**）
- **复用已有库代码**：`scripts/proposal_validator.py` / `scripts/generation_strategy.py` / `scripts/diversity_metrics.py` 已在 Phase 2-3 完成，禁止重写玩具函数替代；只做主路径接入

## Review Focus

1. **C0 冒烟验证未通过即启动代码编写** → 若本机 Praxist 版本过旧无法加载 task-local plugin，Week 1 A2/B2 代码将全部返工。测试：C0 报告必须包含 Plugin 加载能力验证与 Agenda Schema 验证两项冒烟测试结果。
2. **P0-3 改错目标文件** → 若误改 `-audit.md` 审计报告，造成篡改审计记录的合规事故。测试：验收时检查 `-audit.md` 原文保持不动，仅修改原始 Changelog 与 Ultragoal。
3. **evaluator Step 0 Fail-fast 未生效** → 非法候选仍消耗昂贵算力跑完评估才在物化前被拒。测试：构造一个含中英泄漏的非法提案，验证 evaluator 在 Step 0 短路拒绝，不产生 `results/` 输出，**且 `validation_signal` 已持久化**。
4. **B4 KL 散度零概率除零异常** → 单代样本量小（<30）或冷启动时某些桶频次为 0，标准 KL 散度抛出除零异常。测试：构造一个桶频次为 0 的 feedback 文件，验证散度计算使用拉普拉斯平滑或 JS 散度，不抛异常且不触发告警（因 N<30）。
5. **C1 双写重复消费** → 旧提案树导入与新路径 Peer 原生产出并存时，慢环重复消费同一候选。测试：构造一个已存在于慢环队列的提案，验证 C1 导入脚本通过幂等键去重，不重复入队。

---

## Phase 0: P0 止血包 + C0 探查（Week 0）

### Task 0-1: P0-1 监控 crontab 部署

**Files:**
- Modify: `/home/abug/timesfm/crontab.txt`（新增或创建）
- Create: `/home/abug/timesfm/logs/`（目录，若不存在）

**Interfaces:**
- Consumes: `scripts/monitor_metrics.py`, `scripts/generate_weekly_report.py`
- Produces: crontab 条目，含 `mkdir -p` 与 `flock` 保护

- [ ] **Step 1: 创建 logs 目录**

```bash
mkdir -p /home/abug/timesfm/logs
```

- [ ] **Step 2: 编辑 crontab**

Run: `crontab -e`

添加以下条目：

```cron
0 2 * * * mkdir -p /home/abug/timesfm/logs && flock -n /tmp/tfm_mon.lock timeout 1800s bash -c 'cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/monitor_metrics.py collect' >> /home/abug/timesfm/logs/monitor_metrics.log 2>&1
0 3 * * 1 mkdir -p /home/abug/timesfm/logs && flock -n /tmp/tfm_weekly.lock timeout 3600s bash -c 'cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/generate_weekly_report.py --days 7' >> /home/abug/timesfm/logs/weekly_report.log 2>&1
```

- [ ] **Step 3: 验证 crontab 已加载**

Run: `crontab -l | grep monitor_metrics`
Expected: 显示包含 `flock -n /tmp/tfm_mon.lock` 的条目

- [ ] **Step 4: 手工 dry-run monitor_metrics.py**

Run: `cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/monitor_metrics.py collect`
Expected: 无 Traceback，`data/cache/metrics_history/` 出现新记录

- [ ] **Step 5: 本地变更自检（禁止 commit）**

```bash
git status
git diff crontab.txt
# 在 local-pc.lock 中登记本 Task 变更
echo "Task 0-1: crontab.txt modified at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 0-2: P0-2 quality_model.json 落盘与红线白名单

**Files:**
- Create: `data/cache/quality_model.json`（或等效路径）
- Modify: `scripts/sup_harvest.py`（若需放宽白名单）

**Interfaces:**
- Consumes: harvest 产出的提案文件
- Produces: `quality_model.json`，质量分具备非零方差（标准差 > 0.05）

- [ ] **Step 1: 检查 quality_model.json 是否存在**

Run: `ls -l /home/abug/timesfm/data/cache/quality_model.json`
Expected: 文件不存在或路径不同

- [ ] **Step 2: 落盘 quality_model.json**

根据现有 `proposal_validator.py` 或 `sup_harvest.py` 中的质量分计算逻辑，将模型参数序列化为 `quality_model.json`。

- [ ] **Step 3: 验证红线白名单放行 .json**

Run: `grep -n "quality_model" scripts/sup_harvest.py`
Expected: 白名单包含 `.json`，或代码能读取 `.json` 扩展名

- [ ] **Step 4: 实测质量分方差**

Run: 抽取最近 100 条提案，计算质量分标准差
Expected: 标准差 > 0.05，不再恒定为 0.5

- [ ] **Step 5: 本地变更自检（禁止 commit）**

```bash
git status
git diff data/cache/quality_model.json scripts/sup_harvest.py
echo "Task 0-2: quality_model.json + sup_harvest.py modified at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 0-3: P0-3 Changelog 与 Ultragoal 措辞修正

**Files:**
- Modify: 被审计的原始执行 Changelog 文档（如 `2026-10-20-phase2-3-execution-changelog.md` 或主 Changelog）
- Modify: Ultragoal 文档
- **禁止修改**: `2026-10-20-phase2-3-execution-changelog-audit.md`

**Interfaces:**
- Consumes: 原始 Changelog 与 Ultragoal
- Produces: 修正后的措辞："能力库已入库；主路径按 2026-10-21 方案推进中"

- [ ] **Step 1: 定位原始 Changelog**

Run: `ls docs/superpowers/changelogs/2026-10-20-*`
Expected: 找到原始 Changelog（不含 `-audit.md`）

- [ ] **Step 2: 修正原始 Changelog 措辞**

将所有"✅完成"或"Phase 2-3 验收完成"改为"库完成 / 主路径未闭环"。

- [ ] **Step 3: 修正 Ultragoal 措辞**

将对应状态表述改为"能力库已入库；主路径按 2026-10-21 方案推进中"。

- [ ] **Step 4: 验证 -audit.md 未修改**

Run: `git diff docs/superpowers/changelogs/2026-10-20-phase2-3-execution-changelog-audit.md`
Expected: 无 diff（文件未被修改）

- [ ] **Step 5: 本地变更自检（禁止 commit）**

```bash
git status
git diff docs/superpowers/changelogs/ docs/superpowers/ultragoal/
echo "Task 0-3: Changelog + Ultragoal modified at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 0-4: C0 运行时路径与版本探查（前置阻塞门）

**Files:**
- Create: `docs/superpowers/reports/2026-10-21-praxist-runtime-path-inventory.md`

**Interfaces:**
- Consumes: 本机 `.venv` 中的 Praxist 版本
- Produces: C0 报告，含 Plugin 加载能力验证 + Agenda Schema 验证两项冒烟测试结果

- [ ] **Step 1: 记录 Praxist 版本与路径**

Run: `cd /home/abug/timesfm && .venv/bin/python -c "import praxist,pkgutil; print(praxist.__file__, getattr(praxist,'__version__',None))"`

记录输出到报告。

- [ ] **Step 2: 探查 peer 实际创建的提案/variant 路径**

通过 strace 或 Praxist trajectory / 现有日志，记录 peer 实际写盘路径。

- [ ] **Step 3: 记录与上游文档路径的差集**

对比 `variants/`、`results/`、`findings/` 的实际差集。

- [ ] **Step 4: 检查是否已有 task-local plugin 或 task.yaml**

Run: `find /home/abug/timesfm -name ".praxist" -o -name "task.yaml" 2>/dev/null`

- [ ] **Step 5: 冒烟验证 1 — Plugin 加载能力**

创建一个空壳 `<task>/.praxist/plugins/test_plugin/`，验证当前 `.venv` 中的 Praxist 能否成功加载。

Run: 按 Praxist 文档创建空壳 plugin，启动 `praxist start --task-path <task>`，检查日志是否加载成功。

记录结果：PASS / FAIL。

- [ ] **Step 6: 冒烟验证 2 — Agenda Schema 验证**

提取当前版本 Peer 实际渲染 Prompt 时读取的 Agenda/Role 上下文结构，确认与上游最新文档一致。

记录结果：PASS / FAIL。

- [ ] **Step 7: 撰写 C0 报告**

产出：`docs/superpowers/reports/2026-10-21-praxist-runtime-path-inventory.md`

报告必须包含：
- Praxist 版本与路径
- peer 实际写盘路径
- 与上游文档路径的差集
- 冒烟验证 1 结果（PASS / FAIL）
- 冒烟验证 2 结果（PASS / FAIL）

- [ ] **Step 8: 本地变更自检（禁止 commit）**

```bash
git status
git diff docs/superpowers/reports/2026-10-21-praxist-runtime-path-inventory.md
echo "Task 0-4: C0 report created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 阻塞门**: C0 报告必须两项冒烟验证均 PASS，方可进入 Week 1 A2/B2 代码编写。若 FAIL，需先升级/对齐 Praxist 版本。

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

## Phase 1: P1-A 提案卫生 + P1-B 生成策略/多样性（Week 1-2）

### Task 1-1: A1 门禁规则清单对齐

**Files:**
- Create: `docs/superpowers/specs/proposal-gate-rules.md`

**Interfaces:**
- Consumes: `scripts/proposal_validator.py` 的规则 + Spec §3.2 + 审计 P0
- Produces: 规则清单文档，与 validator 测试一一对应

- [ ] **Step 1: 读取现有 proposal_validator.py 的规则**

Run: `cat scripts/proposal_validator.py | grep -A5 "def validate"`

提取所有校验规则。

- [ ] **Step 2: 对照 Spec §3.2 与审计 P0**

将规则整理为可声明合同（JSON Schema 或 task_audit 规则模块）：
- JSON/类型/中英泄漏
- stem / variant_id 口径
- Laya 禁用词（"训练 Laya"、"进化 Laya"）

- [ ] **Step 3: 撰写规则清单文档**

产出：`docs/superpowers/specs/proposal-gate-rules.md`

文档必须包含：
- 每条规则的名称、描述、预期行为
- 与 validator 测试的对应关系
- Laya 禁用词清单

- [ ] **Step 4: 本地变更自检（禁止 commit）**

```bash
git status
git diff docs/superpowers/specs/proposal-gate-rules.md
echo "Task 1-1: A1 rules doc created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-2: B1 反馈→agenda Schema 定义（输入侧可先冻结）

**Files:**
- Create: `docs/superpowers/specs/feedback-agenda-schema.md`

**Interfaces:**
- Consumes: `data/cache/bandit_feedback.jsonl`（由 sup_harvest 产出）
- Produces: feedback Schema（输入侧）+ agenda Schema 草案（输出侧，待 C0 确认后定稿）

- [ ] **Step 1: 定义输入侧 feedback Schema**

根据 `bandit_feedback.jsonl` 的实际字段，定义 JSON Schema。

- [ ] **Step 2: 定义输出侧 agenda Schema 草案**

根据上游文档 `agendas/research_agenda_gen*.yaml` 的结构，定义草案。

**注意**：输出侧 Schema 待 C0 冒烟验证 2 确认后定稿。

- [ ] **Step 3: 撰写 Schema 文档**

产出：`docs/superpowers/specs/feedback-agenda-schema.md`

- [ ] **Step 4: 本地变更自检（禁止 commit）**

```bash
git status
git diff docs/superpowers/specs/feedback-agenda-schema.md
echo "Task 1-2: B1 schema doc created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-3: A2 task_audit / plugin 骨架（复用 proposal_validator.py + validation_signal 留痕）

**Files:**
- Create: `<task>/.praxist/plugins/proposal_gate/plugin.yaml`
- Create: `<task>/.praxist/plugins/proposal_gate/validate.py`
- Create: `tests/test_proposal_gate_plugin.py`

**Interfaces:**
- Consumes: `proposal-gate-rules.md`（A1 产出）+ `scripts/proposal_validator.py`（已有库代码）
- Produces: task-local plugin，在 evaluator Step 0 拦截非法提案，**输出 `validation_signal` 留痕**

- [ ] **Step 1: 写测试 — 合法提案通过**

```python
def test_valid_proposal_passes():
    proposal = {"variant_id": "v1", "stem": "test", "language": "en"}
    result = validate_proposal(proposal)
    assert result["valid"] is True
```

- [ ] **Step 2: 写测试 — 非法提案被拒（含 Fail-fast + validation_signal）**

```python
def test_invalid_proposal_rejected_with_signal():
    proposal = {"variant_id": "v2", "stem": "测试", "language": "zh"}  # 中英泄漏
    result = validate_proposal(proposal)
    assert result["valid"] is False
    assert result["reason"] == "chinese_leak"
    assert "validation_signal" in result  # 审计追溯留痕
```

- [ ] **Step 3: 写测试 — Laya 禁用词被拒**

```python
def test_laya_prohibited_words_rejected():
    proposal = {"variant_id": "v3", "description": "训练 Laya"}
    result = validate_proposal(proposal)
    assert result["valid"] is False
    assert result["reason"] == "laya_prohibited_word"
```

- [ ] **Step 4: 运行测试，验证失败**

Run: `pytest tests/test_proposal_gate_plugin.py -v`
Expected: FAIL（函数未定义）

- [ ] **Step 5: 实现 plugin.yaml**

```yaml
name: proposal_gate
version: 0.1.0
source: task_project
hooks:
  - stage: evaluator_pre
    entry: validate:validate_proposal
```

- [ ] **Step 6: 实现 validate.py — 复用 proposal_validator.py + validation_signal 落盘**

```python
import sys
import json
from datetime import datetime
sys.path.insert(0, "/home/abug/timesfm/scripts")
from proposal_validator import validate_proposal_dict  # 复用已有库代码

VALIDATION_SIGNAL_PATH = "<task>/validation_signals.jsonl"  # 审计追溯落盘路径

def validate_proposal(proposal: dict) -> dict:
    """Step 0 前置关卡：复用 proposal_validator.py，拦截非法提案 + validation_signal 留痕 + 落盘。"""
    valid, errors = validate_proposal_dict(proposal)  # 调用已有库代码
    if not valid:
        signal = {
            "variant_id": proposal.get("variant_id"),
            "errors": errors,
            "timestamp": datetime.now().isoformat()
        }
        # 落盘持久化，供审计追溯（Spec §2.3 要求）
        with open(VALIDATION_SIGNAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(signal, ensure_ascii=False) + "\n")
        return {
            "valid": False,
            "reason": errors[0] if errors else "unknown",
            "validation_signal": signal
        }
    return {"valid": True}
```

- [ ] **Step 7: 运行测试，验证通过**

Run: `pytest tests/test_proposal_gate_plugin.py -v`
Expected: PASS

- [ ] **Step 8: 本地变更自检（禁止 commit）**

```bash
git status
git diff <task>/.praxist/plugins/proposal_gate/ tests/test_proposal_gate_plugin.py
echo "Task 1-3: A2 plugin created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-4: B2 离线合成器（复用 GenerationStrategy + Batch Bandit）

**Files:**
- Create: `scripts/synthesize_agenda_from_feedback.py`
- Create: `tests/test_synthesize_agenda.py`

**Interfaces:**
- Consumes: `data/cache/bandit_feedback.jsonl` + `feedback-agenda-schema.md`（B1 产出）+ `scripts/generation_strategy.py`（已有库代码）
- Produces: `agendas/research_agenda_gen<N+1>.yaml`

- [ ] **Step 1: 写测试 — 给定 feedback 生成稳定 agenda**

```python
def test_synthesize_agenda_from_feedback():
    feedback = [{"bucket": "family_A", "reward": 0.8}, {"bucket": "family_B", "reward": 0.2}]
    agenda = synthesize_agenda(feedback)
    assert "bucket_weights" in agenda
    assert agenda["bucket_weights"]["family_A"] > agenda["bucket_weights"]["family_B"]
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `pytest tests/test_synthesize_agenda.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 synthesize_agenda_from_feedback.py — 复用 generation_strategy.py**

```python
import sys
sys.path.insert(0, "/home/abug/timesfm/scripts")
from generation_strategy import MultiArmedBandit, GenerationStrategy  # 复用已有库代码

def synthesize_agenda(feedback: list[dict]) -> dict:
    """Generation-level Batch Bandit: 复用 MultiArmedBandit 按代批式更新桶权重。"""
    bandit = MultiArmedBandit()
    for item in feedback:
        bandit.update(item["bucket"], item["reward"])
    weights = bandit.get_weights()  # UCB 或 Thompson 采样
    return {"bucket_weights": weights}
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `pytest tests/test_synthesize_agenda.py -v`
Expected: PASS

- [ ] **Step 5: 本地变更自检（禁止 commit）**

```bash
git status
git diff scripts/synthesize_agenda_from_feedback.py tests/test_synthesize_agenda.py
echo "Task 1-4: B2 synthesizer created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-5: B4 diversity 报告进 metrics_history + KL/JS 散度告警

**Files:**
- Modify: `scripts/monitor_metrics.py`（或复用 `scripts/diversity_metrics.py`）
- Create: `tests/test_diversity_metrics.py`

**Interfaces:**
- Consumes: `data/cache/bandit_feedback.jsonl` + agenda 目标配额 + `scripts/diversity_metrics.py`（已有库代码）
- Produces: diversity 覆盖率趋势 + KL/JS 散度告警（含拉普拉斯平滑 + 最小样本量门槛 N≥30）

- [ ] **Step 1: 写测试 — KL 散度零概率平滑**

```python
def test_kl_divergence_with_zero_probability():
    p = [0.5, 0.5, 0.0]  # 某桶频次为 0
    q = [0.33, 0.33, 0.34]
    kl = compute_kl_divergence(p, q, epsilon=1e-3)  # 拉普拉斯平滑
    assert not np.isnan(kl)
    assert not np.isinf(kl)
```

- [ ] **Step 2: 写测试 — 最小样本量门槛**

```python
def test_minimum_sample_size():
    feedback = [{"bucket": "A"}] * 10  # N=10 < 30
    alert = compute_diversity_alert(feedback)
    assert alert["triggered"] is False  # 不触发告警
```

- [ ] **Step 3: 运行测试，验证失败**

Run: `pytest tests/test_diversity_metrics.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 compute_kl_divergence — 复用 diversity_metrics.py**

```python
import sys
sys.path.insert(0, "/home/abug/timesfm/scripts")
from diversity_metrics import compute_kl_divergence as _compute_kl  # 复用已有库代码

def compute_kl_divergence(p: list[float], q: list[float], epsilon: float = 1e-3) -> float:
    """KL 散度，带拉普拉斯平滑防除零。复用 diversity_metrics.py 实现。"""
    return _compute_kl(p, q, epsilon=epsilon)
```

- [ ] **Step 5: 实现 compute_diversity_alert**

```python
def compute_diversity_alert(feedback: list[dict], threshold: float = 0.3) -> dict:
    """N≥30 才触发告警。"""
    if len(feedback) < 30:
        return {"triggered": False, "reason": "sample_size_too_small"}
    # 计算 KL 散度
    kl = compute_kl_divergence(...)
    return {"triggered": kl > threshold, "kl": kl}
```

- [ ] **Step 6: 运行测试，验证通过**

Run: `pytest tests/test_diversity_metrics.py -v`
Expected: PASS

- [ ] **Step 7: 本地变更自检（禁止 commit）**

```bash
git status
git diff scripts/monitor_metrics.py tests/test_diversity_metrics.py
echo "Task 1-5: B4 diversity metrics created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-6: B3 接入 Generation Close 后钩 + Peer 渲染验证

**Files:**
- Create: `scripts/hooks/on_generation_close.py`
- Create: `tests/test_generation_close_hook.py`

**Interfaces:**
- Consumes: B2 合成器输出 + Praxist generation close 事件
- Produces: 新一代 agenda 文件被 Praxist 读取；Peer Prompt 渲染出新配额

- [ ] **Step 1: 写测试 — generation close 后合成器被调用**

```python
def test_on_generation_close_synthesizes_agenda():
    feedback = [{"bucket": "A", "reward": 0.8}]
    result = on_generation_close(feedback)
    assert "agenda_path" in result
    assert os.path.exists(result["agenda_path"])
```

- [ ] **Step 2: 写测试 — Peer Prompt 渲染出新配额**

```python
def test_peer_prompt_renders_new_quota():
    agenda = {"bucket_weights": {"A": 0.7, "B": 0.3}}
    prompt = render_peer_prompt(agenda)
    assert "A" in prompt and "70%" in prompt  # 配额被渲染进 Prompt
```

- [ ] **Step 3: 运行测试，验证失败**

Run: `pytest tests/test_generation_close_hook.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 on_generation_close.py**

```python
from synthesize_agenda_from_feedback import synthesize_agenda
from jinja2 import Template

def on_generation_close(feedback: list[dict]) -> dict:
    """Generation close 后钩：调用 B2 合成器生成下一代 agenda。"""
    agenda = synthesize_agenda(feedback)
    agenda_path = f"agendas/research_agenda_gen{get_next_gen()}.yaml"
    write_yaml(agenda_path, agenda)
    return {"agenda_path": agenda_path}

def render_peer_prompt(agenda: dict) -> str:
    """将 agenda 配额渲染进 Peer Prompt — 使用 Jinja2 模板（C0 探查完成后）。"""
    # C0 探查完成后，改为渲染 <task>/ 下 Peer 实际使用的 Jinja2 模板
    template_path = "<task>/prompt_peer.jinja2"
    with open(template_path, "r", encoding="utf-8") as f:
        template = Template(f.read())
    return template.render(agenda=agenda)
```

**⚠️ C0 探查完成后，需确认 `<task>/prompt_peer.jinja2` 模板实际存在且能读取 agenda 配额。若模板不存在，则回退到字符串拼接方式。**

- [ ] **Step 5: 运行测试，验证通过**

Run: `pytest tests/test_generation_close_hook.py -v`
Expected: PASS

- [ ] **Step 6: 本地变更自检（禁止 commit）**

```bash
git status
git diff scripts/hooks/on_generation_close.py tests/test_generation_close_hook.py
echo "Task 1-6: B3 generation close hook created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-7: A3 门禁接入 Praxist 原生 task evaluator Step 0（非 sup_harvest 旁路）

**Files:**
- Modify: `<task>/evaluator.py`（或 Praxist task evaluator 配置）
- Modify: `<task>/.praxist/plugins/proposal_gate/validate.py`

**Interfaces:**
- Consumes: A2 plugin 产出
- Produces: 脏提案不进 frontier；evaluator Step 0 短路拒绝非法候选

- [ ] **Step 1: 写集成测试 — 脏提案不进 frontier（接入 Praxist 原生 evaluator）**

```python
def test_dirty_proposal_not_in_frontier_via_evaluator():
    proposal = {"variant_id": "dirty", "stem": "测试"}
    result = run_evaluator_step0(proposal)  # 调用 Praxist 原生 evaluator Step 0
    assert result["rejected"] is True
    assert not is_in_frontier("dirty")
    assert result["validation_signal"] is not None  # 留痕
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `pytest tests/test_integration.py::test_dirty_proposal_not_in_frontier_via_evaluator -v`
Expected: FAIL

- [ ] **Step 3: 接入 A2 plugin 到 Praxist 原生 evaluator Step 0**

在 Praxist task evaluator 配置中，将 A2 plugin 注册为 Step 0 前置关卡：

```python
# <task>/evaluator.py
from proposal_gate.validate import validate_proposal

def run_evaluator(proposal):
    # Step 0: 提案卫生预检（Fail-fast）
    result = validate_proposal(proposal)
    if not result["valid"]:
        return {"rejected": True, "validation_signal": result["validation_signal"]}
    # Step 1+: 跑昂贵模型评估
    ...
```

- [ ] **Step 4: 保留 harvest 旁路闸（A4 备用）**

在 `scripts/sup_harvest.py` 中保留 `validate_proposal_dict()` 调用，作为双闸的备用（A4）。

- [ ] **Step 5: 运行测试，验证通过**

Run: `pytest tests/test_integration.py::test_dirty_proposal_not_in_frontier_via_evaluator -v`
Expected: PASS

- [ ] **Step 6: 本地变更自检（禁止 commit）**

```bash
git status
git diff <task>/evaluator.py scripts/sup_harvest.py
echo "Task 1-7: A3 evaluator Step 0 integration at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-8: B6 多 Role 硬隔离配额

**Files:**
- Create: `<task>/roles/family_A.yaml`
- Create: `<task>/roles/family_B.yaml`
- Create: `tests/test_multi_role_isolation.py`

**Interfaces:**
- Consumes: agenda 桶权重
- Produces: 不同 Peer 只能生成指定家族/符号桶

- [ ] **Step 1: 写测试 — 多 Role 硬隔离**

```python
def test_multi_role_isolation():
    role_a = load_role("family_A")
    role_b = load_role("family_B")
    assert role_a["allowed_surface"]["families"] == ["family_A"]
    assert role_b["allowed_surface"]["families"] == ["family_B"]
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `pytest tests/test_multi_role_isolation.py -v`
Expected: FAIL

- [ ] **Step 3: 实现多 Role 配置**

```yaml
# <task>/roles/family_A.yaml
name: family_A
allowed_surface:
  families: ["family_A"]
  symbols: ["*"]  # 或指定子集
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `pytest tests/test_multi_role_isolation.py -v`
Expected: PASS

- [ ] **Step 5: 本地变更自检（禁止 commit）**

```bash
git status
git diff <task>/roles/ tests/test_multi_role_isolation.py
echo "Task 1-8: B6 multi-role isolation at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 1-9: Laya 禁用词静态检查测试（修复"可学习"误杀）

**Files:**
- Create: `tests/test_laya_prohibited_words.py`

**Interfaces:**
- Consumes: 仓库所有 Python 文件与 Jinja2 模板
- Produces: CI 自动扫描，违规即 fail；**不误杀"不可学习"合规声明**

- [ ] **Step 1: 写测试 — 扫描仓库禁止 Laya 禁用词（修复中文 `\b` 失效 + 绑定 Laya 上下文）**

```python
import re

def test_no_laya_prohibited_words_in_codebase():
    # 修复：中文无 \b 词边界（汉字都属于 \w），必须用非 \b 方式匹配
    # 修复："可学习" 必须绑定 Laya 上下文，否则会误杀 TimesFM 模型代码中的 "可学习参数"
    prohibited_patterns = [
        r"(?:训练|进化|微调|优化)\s*Laya",  # 匹配 "训练Laya" / "训练 Laya" / "进化Laya" 等
        r"Laya[^\n]{0,15}(?<!不)可学习",     # Laya 后 15 字符内出现 "可学习"（且前面不是 "不"）
        r"(?<!不)可学习[^\n]{0,15}Laya",     # "可学习" 后 15 字符内出现 Laya（且前面不是 "不"）
    ]
    violations = scan_codebase_with_regex(prohibited_patterns)
    assert len(violations) == 0, f"Found prohibited words: {violations}"
```

**⚠️ 扫描函数中记得跳过 `tests/test_laya_prohibited_words.py` 自身，避免测试文件扫到自己的模式列表。**

- [ ] **Step 2: 运行测试，验证失败（若存在违规）**

Run: `pytest tests/test_laya_prohibited_words.py -v`
Expected: FAIL（若代码中存在违规词）

- [ ] **Step 3: 修复违规**

替换所有违规词为合规表述。

- [ ] **Step 4: 运行测试，验证通过**

Run: `pytest tests/test_laya_prohibited_words.py -v`
Expected: PASS

- [ ] **Step 5: 本地变更自检（禁止 commit）**

```bash
git status
git diff tests/test_laya_prohibited_words.py
echo "Task 1-9: Laya static check at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

## Phase 2: P1-C 写盘路径对齐（Week 3）

### Task 2-1: C1 兼容导入（含幂等键 + 并发互斥，修复文件锁模式）

**Files:**
- Create: `scripts/import_legacy_proposals.py`
- Create: `tests/test_import_legacy.py`

**Interfaces:**
- Consumes: 旧提案树
- Produces: finding 兼容结构或慢环队列，以 `variant_id` 为幂等键

- [ ] **Step 1: 写测试 — 幂等键去重**

```python
def test_idempotency_key_deduplication():
    proposal = {"variant_id": "v1", "stem": "test"}
    import_proposal(proposal)
    import_proposal(proposal)  # 重复导入
    assert count_in_queue("v1") == 1  # 不重复入队
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `pytest tests/test_import_legacy.py::test_idempotency_key_deduplication -v`
Expected: FAIL

- [ ] **Step 3: 实现 import_legacy_proposals.py**

```python
def import_proposal(proposal: dict):
    """以 variant_id 为幂等键，防止重复消费。"""
    variant_id = proposal["variant_id"]
    if already_in_queue(variant_id):
        return  # 跳过
    # 规范化 → validator → 写入 finding 兼容结构
    ...
```

- [ ] **Step 4: 实现 local-pc.lock 并发互斥（修复：使用 "a+" 模式 + 统一路径）**

```python
import fcntl

# 修复：使用 "a+" 模式避免 O_TRUNC 清空锁文件；路径与团队规范一致
LOCK_PATH = "/home/abug/timesfm/.local-pc.lock"  # 统一路径
with open(LOCK_PATH, "a+") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    try:
        import_proposal(proposal)
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
```

- [ ] **Step 5: 运行测试，验证通过**

Run: `pytest tests/test_import_legacy.py -v`
Expected: PASS

- [ ] **Step 6: 本地变更自检（禁止 commit）**

```bash
git status
git diff scripts/import_legacy_proposals.py tests/test_import_legacy.py
echo "Task 2-1: C1 legacy import at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 2-2: C2 新 peer 默认走官方路径（含配置入口）

**Files:**
- Modify: 文档（`docs/`）
- Create: `scripts/start_peer_official.sh`（配置 --task-path 标准启动入口）

**Interfaces:**
- Consumes: C0 报告
- Produces: 文档化新候选默认路径 + 配置标准启动入口；旁路标 deprecated

- [ ] **Step 1: 创建标准启动脚本**

```bash
#!/bin/bash
# scripts/start_peer_official.sh
cd /home/abug/timesfm
praxist start --task-path <task> --daemonize --json
```

- [ ] **Step 2: 更新文档 — 新实验只开 --task-path 标准环**

在 `docs/` 中写明：新实验默认使用 `scripts/start_peer_official.sh`（封装 `praxist start --task-path <task>`），不再使用 cascade 旁路。

- [ ] **Step 3: 标记旁路为 deprecated**

在相关代码与文档中标注：cascade 旁路只读历史，不再写入。

- [ ] **Step 4: 本地变更自检（禁止 commit）**

```bash
git status
git diff docs/ scripts/start_peer_official.sh
echo "Task 2-2: C2 official path config at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

### Task 2-3: C3 拆除旁路写（停止 peer 直接写未经验证提案）

**Files:**
- Modify: `scripts/sup_harvest.py`（或 cascade 旁路代码）
- Create: `tests/test_no_bypass_write.py`

**Interfaces:**
- Consumes: C2 标准启动入口
- Produces: peer 不再直接写未经验证提案到生产队列目录

- [ ] **Step 1: 写测试 — 旁路写已拆除**

```python
def test_no_bypass_write_to_production_queue():
    # 验证 cascade 旁路代码不再直接写生产队列
    result = run_cascade_bypass(proposal)
    assert not is_in_production_queue(proposal["variant_id"])
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `pytest tests/test_no_bypass_write.py -v`
Expected: FAIL

- [ ] **Step 3: 拆除旁路写**

在 cascade 旁路代码中，移除直接写生产队列的逻辑，改为只读历史或完全禁用。

- [ ] **Step 4: 运行测试，验证通过**

Run: `pytest tests/test_no_bypass_write.py -v`
Expected: PASS

- [ ] **Step 5: 本地变更自检（禁止 commit）**

```bash
git status
git diff scripts/sup_harvest.py tests/test_no_bypass_write.py
echo "Task 2-3: C3 bypass write removed at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

## Optional: P2 sitecustomize 临时垫片（仅在 C0 证明必要时）

### Task 3-1: P2 最小垫片（若 C0 冒烟验证 FAIL）

**Files:**
- Create: `.runtime_guards/python_site/sitecustomize.py`

**Interfaces:**
- Consumes: C0 报告（证明本机 Praxist 无法通过 Task 合同拦截）
- Produces: 最小拦截垫片，钉死 `praxist==x.y.z`

**前置条件**: C0 报告证明本机 Praxist 版本无法通过 Task 合同或 Evaluator Step 0 拦截脏提案，且短期无法升级。

- [ ] **Step 1: 钉死 praxist 版本**

在 `requirements.txt` 中钉死 `praxist==x.y.z`。

- [ ] **Step 2: 实现最小垫片**

```python
# sitecustomize.py
import praxist

# 只实现最小拦截：validate / register
original_function = praxist.some_function
def patched_function(*args, **kwargs):
    # 拦截逻辑
    return original_function(*args, **kwargs)
praxist.some_function = patched_function
```

- [ ] **Step 3: 写拆除 issue**

在 issue tracker 中创建拆除 issue，写明：**拆除条件 = A3+B3 合并且 C2 默认路径切换完成**。

- [ ] **Step 4: 本地变更自检（禁止 commit）**

```bash
git status
git diff .runtime_guards/python_site/sitecustomize.py requirements.txt
echo "Task 3-1: P2 shim created at $(date)" >> /home/abug/timesfm/.local-pc.lock
```

**⚠️ 未经用户指令严禁执行 `git commit`。**

---

## 验收清单

完成所有 Task 后，逐项验收：

- [ ] P0-1 crontab 已装且连续 ≥3 天有 metrics_history
- [ ] P0-2 quality_model.json 存在，质量分标准差 > 0.05
- [ ] P0-3 Changelog 与 Ultragoal 措辞已修正，`-audit.md` 未动
- [ ] C0 报告两项冒烟验证均 PASS
- [ ] A1 规则清单文档已对齐
- [ ] B1 feedback-agenda schema 已定义（输入侧冻结）
- [ ] A2 task-local plugin 在 evaluator Step 0 拦截非法提案，**复用 proposal_validator.py + validation_signal 留痕**
- [ ] B2 离线合成器**复用 GenerationStrategy/MultiArmedBandit**，采用 Batch Bandit 模式
- [ ] B4 diversity 报告进 metrics_history，KL/JS 散度告警已接入（**复用 diversity_metrics.py**）
- [ ] **B3 generation close 后钩已接入，Peer Prompt 渲染出新配额**
- [ ] A3 门禁接入 **Praxist 原生 evaluator Step 0**（非 sup_harvest 旁路）
- [ ] A4 harvest 双闸文档写明主/备
- [ ] **B6 多 Role 硬隔离配额已配置**
- [ ] A9 Laya 禁用词静态检查测试通过（**不误杀"不可学习"**）
- [ ] C1 兼容导入采用幂等键 + 并发互斥（**文件锁 "a+" 模式 + 统一路径**）
- [ ] C2 新 peer 默认走官方路径，**含配置启动入口**
- [ ] **C3 旁路写已拆除**
- [ ] （可选 P2）若存在 sitecustomize：有版本钉与拆除 issue
- [ ] **全篇无 git commit 违规（仅 git status/diff + local-pc.lock 登记）**

---

**文档结束**
