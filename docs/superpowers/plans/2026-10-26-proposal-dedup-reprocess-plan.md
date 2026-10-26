# 提案去重与慢环重评估 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 743 个唯一未评估提案去重后入队慢环评估，生成 verdict。

**Architecture:** 编写 Python 脚本扫描所有提案文件，按 `symbol_cov_override` 去重，排除已有 verdict 的提案，构造队列行写入 `aligned_pending.jsonl`，然后启动慢环评估。

**Tech Stack:** Python 3.11, pathlib, json, registry_lib (队列管理), aligned_slow_loop (慢环引擎)

**Spec:** `docs/superpowers/specs/2026-10-26-proposal-dedup-reprocess-spec.md`

## Global Constraints

- Python 版本：3.11（与项目一致）
- 队列文件路径：`data/cache/aligned_pending.jsonl`
- Verdict 文件路径：`task_FM/config/aligned_verdicts.jsonl`
- 批次标识：`source = "reprocess_20261026"`
- 慢环单耗时：~9 分钟（中位数）
- 总耗时估算：~4.6 天（743 个提案，单线程）

## Review Focus

1. **提案文件损坏**：JSON 解析失败时跳过该文件，不中断流程
2. **variant_id 冲突**：同一 `symbol_cov_override` 出现在多个 run 中时保留 mtime 最新的
3. **队列文件锁冲突**：使用 flock 获取锁，超时 30 秒报错退出
4. **幂等性**：重复运行脚本不会产生重复入队
5. **必填字段缺失**：提案文件缺少 `symbol` 或 `cov_override` 时跳过并记录警告

---

### Task 1: 提案扫描器

**Files:**
- Create: `scripts/scan_proposals.py`
- Test: `tests/test_scan_proposals.py`

**Interfaces:**
- Consumes: 提案文件路径列表
- Produces: `scan_proposals(paths: List[Path]) -> List[ProposalInfo]`

- [ ] **Step 1: Write the failing test for scanning valid proposals**

```python
# tests/test_scan_proposals.py
import pytest
from pathlib import Path
from scripts.scan_proposals import scan_proposals, ProposalInfo

def test_scan_valid_proposals(tmp_path):
    # 创建测试提案文件
    proposal1 = tmp_path / "prop1.json"
    proposal1.write_text('{"symbol": "ta", "cov_override": "momentum"}')
    
    proposal2 = tmp_path / "prop2.json"
    proposal2.write_text('{"symbol": "sh", "cov_override": "basis"}')
    
    result = scan_proposals([proposal1, proposal2])
    
    assert len(result) == 2
    assert result[0].symbol == "ta"
    assert result[0].cov_override == "momentum"
    assert result[0].variant_id == "ta_momentum"
    assert result[1].symbol == "sh"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_proposals.py::test_scan_valid_proposals -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scripts.scan_proposals'"

- [ ] **Step 3: Implement scan_proposals in scripts/scan_proposals.py**

```python
# scripts/scan_proposals.py
import json
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ProposalInfo:
    symbol: str
    cov_override: str
    variant_id: str
    file_path: Path
    mtime: datetime
    src_run: str

def scan_proposals(paths: list[Path]) -> list[ProposalInfo]:
    proposals = []
    for path in paths:
        try:
            data = json.loads(path.read_text())
            symbol = data.get("symbol")
            cov_override = data.get("cov_override")
            if not symbol or not cov_override:
                continue
            
            # 提取 src_run（从路径中提取 run 目录名）
            src_run = _extract_src_run(path)
            
            proposals.append(ProposalInfo(
                symbol=symbol,
                cov_override=cov_override,
                variant_id=f"{symbol}_{cov_override}",
                file_path=path,
                mtime=datetime.fromtimestamp(path.stat().st_mtime),
                src_run=src_run
            ))
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: skipping {path}: {e}")
            continue
    
    return proposals

def _extract_src_run(path: Path) -> str:
    # 从路径中提取 run 目录名
    # 例如：/path/to/experiments/run_2026-10-24_06-23-48_primary_task_FM/results/...
    for part in path.parts:
        if part.startswith("run_"):
            return part
    return "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_proposals.py::test_scan_valid_proposals -v`
Expected: PASS

- [ ] **Step 5: Write test for handling corrupted files**

```python
def test_scan_corrupted_files(tmp_path):
    valid = tmp_path / "valid.json"
    valid.write_text('{"symbol": "ta", "cov_override": "momentum"}')
    
    corrupted = tmp_path / "corrupted.json"
    corrupted.write_text("{invalid json")
    
    result = scan_proposals([valid, corrupted])
    
    assert len(result) == 1
    assert result[0].symbol == "ta"
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_scan_proposals.py::test_scan_corrupted_files -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/scan_proposals.py tests/test_scan_proposals.py
git commit -m "feat: add proposal scanner with error handling"
```

---

### Task 2: 去重逻辑

**Files:**
- Modify: `scripts/scan_proposals.py`
- Test: `tests/test_scan_proposals.py`

**Interfaces:**
- Consumes: `List[ProposalInfo]`
- Produces: `deduplicate_proposals(proposals: List[ProposalInfo]) -> List[ProposalInfo]`

- [ ] **Step 1: Write the failing test for deduplication**

```python
# tests/test_scan_proposals.py
from scripts.scan_proposals import deduplicate_proposals

def test_deduplicate_by_variant_id():
    # 创建两个相同 variant_id 但不同 mtime 的提案
    prop1 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/old/run_2026-10-01/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 1),
        src_run="run_2026-10-01"
    )
    
    prop2 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/new/run_2026-10-20/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 20),
        src_run="run_2026-10-20"
    )
    
    result = deduplicate_proposals([prop1, prop2])
    
    assert len(result) == 1
    assert result[0].mtime == datetime(2026, 10, 20)  # 保留最新的
    assert result[0].src_run == "run_2026-10-20"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_proposals.py::test_deduplicate_by_variant_id -v`
Expected: FAIL with "ImportError: cannot import name 'deduplicate_proposals'"

- [ ] **Step 3: Implement deduplicate_proposals in scripts/scan_proposals.py**

```python
# scripts/scan_proposals.py (追加)
def deduplicate_proposals(proposals: list[ProposalInfo]) -> list[ProposalInfo]:
    seen = {}
    for prop in proposals:
        if prop.variant_id not in seen:
            seen[prop.variant_id] = prop
        elif prop.mtime > seen[prop.variant_id].mtime:
            seen[prop.variant_id] = prop
    
    return list(seen.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_proposals.py::test_deduplicate_by_variant_id -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scan_proposals.py tests/test_scan_proposals.py
git commit -m "feat: add deduplication logic keeping latest mtime"
```

---

### Task 3: Verdict 排除过滤器

**Files:**
- Create: `scripts/filter_verdicts.py`
- Test: `tests/test_filter_verdicts.py`

**Interfaces:**
- Consumes: `List[ProposalInfo]`, verdict 文件路径
- Produces: `filter_existing_verdicts(proposals: List[ProposalInfo], verdict_path: Path) -> List[ProposalInfo]`

- [ ] **Step 1: Write the failing test for verdict exclusion**

```python
# tests/test_filter_verdicts.py
import pytest
from pathlib import Path
from scripts.scan_proposals import ProposalInfo
from scripts.filter_verdicts import filter_existing_verdicts
from datetime import datetime

def test_filter_existing_verdicts(tmp_path):
    # 创建测试 verdict 文件
    verdict_file = tmp_path / "verdicts.jsonl"
    verdict_file.write_text('{"variant_id": "ta_momentum", "status": "ok"}\n')
    verdict_file.write_text('{"variant_id": "sh_basis", "status": "ok"}\n')
    
    proposals = [
        ProposalInfo("ta", "momentum", "ta_momentum", Path("/p1.json"), datetime.now(), "run1"),
        ProposalInfo("sh", "basis", "sh_basis", Path("/p2.json"), datetime.now(), "run1"),
        ProposalInfo("i", "oi", "i_oi", Path("/p3.json"), datetime.now(), "run1"),
    ]
    
    result = filter_existing_verdicts(proposals, verdict_file)
    
    assert len(result) == 1
    assert result[0].variant_id == "i_oi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_filter_verdicts.py::test_filter_existing_verdicts -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scripts.filter_verdicts'"

- [ ] **Step 3: Implement filter_existing_verdicts in scripts/filter_verdicts.py**

```python
# scripts/filter_verdicts.py
import json
from pathlib import Path
from scripts.scan_proposals import ProposalInfo

def filter_existing_verdicts(
    proposals: list[ProposalInfo],
    verdict_path: Path
) -> list[ProposalInfo]:
    # 读取已有 verdict 的 variant_id
    existing_variant_ids = set()
    if verdict_path.exists():
        with open(verdict_path) as f:
            for line in f:
                try:
                    verdict = json.loads(line.strip())
                    existing_variant_ids.add(verdict["variant_id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    
    # 过滤掉已有 verdict 的提案
    return [p for p in proposals if p.variant_id not in existing_variant_ids]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_filter_verdicts.py::test_filter_existing_verdicts -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/filter_verdicts.py tests/test_filter_verdicts.py
git commit -m "feat: add verdict exclusion filter"
```

---

### Task 4: 队列行构造器

**Files:**
- Create: `scripts/enqueue_reprocess.py`
- Test: `tests/test_enqueue_reprocess.py`

**Interfaces:**
- Consumes: `List[ProposalInfo]`
- Produces: `construct_queue_row(proposal: ProposalInfo, batch_id: str) -> dict`

- [ ] **Step 1: Write the failing test for queue row construction**

```python
# tests/test_enqueue_reprocess.py
from datetime import datetime
from pathlib import Path
from scripts.scan_proposals import ProposalInfo
from scripts.enqueue_reprocess import construct_queue_row

def test_construct_queue_row():
    proposal = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/path/to/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 26, 12, 0, 0),
        src_run="run_2026-10-24_06-23-48_primary_task_FM"
    )
    
    row = construct_queue_row(proposal, batch_id="reprocess_20261026")
    
    assert row["variant_id"] == "ta_momentum"
    assert row["symbol"] == "ta"
    assert row["cov_override"] == "momentum"
    assert row["max_points"] == 600
    assert row["stage"] == "aligned"
    assert row["source"] == "reprocess_20261026"
    assert row["src_run"] == "run_2026-10-24_06-23-48_primary_task_FM"
    assert "enqueued_at" in row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_enqueue_reprocess.py::test_construct_queue_row -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scripts.enqueue_reprocess'"

- [ ] **Step 3: Implement construct_queue_row in scripts/enqueue_reprocess.py**

```python
# scripts/enqueue_reprocess.py
from datetime import datetime
from scripts.scan_proposals import ProposalInfo

def construct_queue_row(proposal: ProposalInfo, batch_id: str) -> dict:
    return {
        "variant_id": proposal.variant_id,
        "symbol": proposal.symbol,
        "cov_override": proposal.cov_override,
        "max_points": 600,
        "stage": "aligned",
        "checkpoint_path": "",
        "enqueued_at": datetime.utcnow().isoformat() + "Z",
        "src_run": proposal.src_run,
        "source": batch_id
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_enqueue_reprocess.py::test_construct_queue_row -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/enqueue_reprocess.py tests/test_enqueue_reprocess.py
git commit -m "feat: add queue row constructor"
```

---

### Task 5: 主入队脚本

**Files:**
- Modify: `scripts/enqueue_reprocess.py`
- Test: `tests/test_enqueue_reprocess.py`

**Interfaces:**
- Consumes: 实验目录路径、verdict 文件路径、队列文件路径、batch_id
- Produces: `main(experiments_dir: Path, verdict_path: Path, queue_path: Path, batch_id: str) -> dict`

- [ ] **Step 1: Write the failing test for main orchestration**

```python
# tests/test_enqueue_reprocess.py
def test_main_orchestration(tmp_path):
    # 创建测试环境
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir()
    
    # 创建提案文件
    run1 = exp_dir / "run_2026-10-01" / "results" / "gen_0" / "gen0_peer0" / "proposals"
    run1.mkdir(parents=True)
    (run1 / "ta_momentum.json").write_text('{"symbol": "ta", "cov_override": "momentum"}')
    
    run2 = exp_dir / "run_2026-10-20" / "results" / "gen_0" / "gen0_peer0" / "proposals"
    run2.mkdir(parents=True)
    (run2 / "ta_momentum.json").write_text('{"symbol": "ta", "cov_override": "momentum"}')
    (run2 / "sh_basis.json").write_text('{"symbol": "sh", "cov_override": "basis"}')
    
    # 创建 verdict 文件（ta_momentum 已有 verdict）
    verdict_file = tmp_path / "verdicts.jsonl"
    verdict_file.write_text('{"variant_id": "ta_momentum", "status": "ok"}\n')
    
    # 队列文件
    queue_file = tmp_path / "queue.jsonl"
    
    from scripts.enqueue_reprocess import main
    stats = main(exp_dir, verdict_file, queue_file, "reprocess_20261026")
    
    assert stats["total_files"] == 3
    assert stats["unique_proposals"] == 2
    assert stats["already_verdict"] == 1
    assert stats["to_enqueue"] == 1
    assert stats["enqueued"] == 1
    
    # 验证队列文件
    lines = queue_file.read_text().strip().split("\n")
    assert len(lines) == 1
    assert "sh_basis" in lines[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_enqueue_reprocess.py::test_main_orchestration -v`
Expected: FAIL with "ImportError: cannot import name 'main' from 'scripts.enqueue_reprocess'"

- [ ] **Step 3: Implement main in scripts/enqueue_reprocess.py**

```python
# scripts/enqueue_reprocess.py (追加)
import json
from pathlib import Path
from scripts.scan_proposals import scan_proposals, deduplicate_proposals
from scripts.filter_verdicts import filter_existing_verdicts

def main(
    experiments_dir: Path,
    verdict_path: Path,
    queue_path: Path,
    batch_id: str
) -> dict:
    # Step 1: 扫描所有提案文件
    proposal_files = list(experiments_dir.rglob("*/proposals/*.json"))
    proposal_files = [f for f in proposal_files if not f.name.endswith(".prescreen.json")]
    
    all_proposals = scan_proposals(proposal_files)
    stats = {"total_files": len(proposal_files)}
    
    # Step 2: 去重
    unique_proposals = deduplicate_proposals(all_proposals)
    stats["unique_proposals"] = len(unique_proposals)
    
    # Step 3: 排除已有 verdict
    filtered_proposals = filter_existing_verdicts(unique_proposals, verdict_path)
    stats["already_verdict"] = stats["unique_proposals"] - len(filtered_proposals)
    stats["to_enqueue"] = len(filtered_proposals)
    
    # Step 4: 构造队列行并入队
    enqueued = 0
    failed = 0
    with open(queue_path, "a") as f:
        for proposal in filtered_proposals:
            try:
                row = construct_queue_row(proposal, batch_id)
                f.write(json.dumps(row) + "\n")
                enqueued += 1
            except Exception as e:
                print(f"Warning: failed to enqueue {proposal.variant_id}: {e}")
                failed += 1
    
    stats["enqueued"] = enqueued
    stats["failed"] = failed
    
    return stats
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_enqueue_reprocess.py::test_main_orchestration -v`
Expected: PASS

- [ ] **Step 5: Add CLI entry point**

```python
# scripts/enqueue_reprocess.py (追加)
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Enqueue proposals for reprocessing")
    parser.add_argument("--experiments-dir", type=Path, default=Path("task_FM/experiments"))
    parser.add_argument("--verdict-path", type=Path, default=Path("task_FM/config/aligned_verdicts.jsonl"))
    parser.add_argument("--queue-path", type=Path, default=Path("data/cache/aligned_pending.jsonl"))
    parser.add_argument("--batch-id", type=str, default="reprocess_20261026")
    
    args = parser.parse_args()
    stats = main(args.experiments_dir, args.verdict_path, args.queue_path, args.batch_id)
    
    print(json.dumps(stats, indent=2))
```

- [ ] **Step 6: Commit**

```bash
git add scripts/enqueue_reprocess.py tests/test_enqueue_reprocess.py
git commit -m "feat: add main orchestration and CLI entry point"
```

---

### Task 6: 集成测试与部署

**Files:**
- No new files
- Test: 手动运行验证

- [ ] **Step 1: 运行所有单元测试**

Run: `pytest tests/test_scan_proposals.py tests/test_filter_verdicts.py tests/test_enqueue_reprocess.py -v`
Expected: All tests PASS

- [ ] **Step 2: 运行入队脚本（dry-run）**

```bash
cd /home/abug/timesfm
python scripts/enqueue_reprocess.py \
  --experiments-dir task_FM/experiments \
  --verdict-path task_FM/config/aligned_verdicts.jsonl \
  --queue-path /tmp/test_queue.jsonl \
  --batch-id reprocess_20261026
```

Expected: 输出统计 JSON，验证 `to_enqueue ≈ 743`

- [ ] **Step 3: 验证队列文件**

```bash
wc -l /tmp/test_queue.jsonl
head -3 /tmp/test_queue.jsonl | jq .
```

Expected: 行数 ≈ 743，每行包含 `variant_id`, `symbol`, `cov_override` 等字段

- [ ] **Step 4: 实际入队**

```bash
cd /home/abug/timesfm
# 备份队列文件
cp data/cache/aligned_pending.jsonl data/cache/aligned_pending.jsonl.bak.$(date +%Y%m%d_%H%M%S)

# 执行入队
python scripts/enqueue_reprocess.py \
  --experiments-dir task_FM/experiments \
  --verdict-path task_FM/config/aligned_verdicts.jsonl \
  --queue-path data/cache/aligned_pending.jsonl \
  --batch-id reprocess_20261026
```

Expected: 统计报告显示 `enqueued ≈ 743`

- [ ] **Step 5: 启动慢环**

```bash
cd /home/abug/timesfm
setsid nohup python scripts/aligned_slow_loop.py \
  --batch-id reprocess_20261026 \
  >> logs/reprocess_20261026.log 2>&1 &

echo $!  # 记录 PID
```

Expected: 慢环启动，日志输出到 `logs/reprocess_20261026.log`

- [ ] **Step 6: 监控进度**

```bash
# 查看日志
tail -f logs/reprocess_20261026.log

# 查看队列状态
wc -l data/cache/aligned_pending.jsonl

# 24 小时后检查 verdict 数量
grep "reprocess_20261026" task_FM/config/aligned_verdicts.jsonl | wc -l
```

Expected: 24 小时后约 160 条新 verdict

- [ ] **Step 7: Commit**

```bash
git add scripts/enqueue_reprocess.py
git commit -m "feat: proposal dedup and reprocess pipeline complete"
```
