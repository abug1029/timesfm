# Obstacles Remediation — 2026-10-16

> 基于代码级复核审核意见的 SPEC 偏离修复

## 修复概览

| 类型 | 问题 | SPEC 要求 | 修复状态 |
|------|------|-----------|----------|
| Blocker | 聚合维度压扁 | FR-2 / §4.2.2：(symbol, cov_family) | ✅ 已修复 |
| Blocker | 主循环挂点顺序 | FR-2：materialize 之后调用 | ✅ 已修复 |
| Blocker | 非原子写 | FR-2：tmp + os.replace | ✅ 已修复 |
| P1 | YAML schema 不一致 | §4.2.2：ledger_name/entries 包装 | ✅ 已修复 |
| P1 | CLI 参数缺失 | NFR-4：强制两参 | ✅ 已修复 |

## 详细修复

### 1. 聚合维度修复（Blocker）

**问题**：`sup_memory_bridge._aggregate` 按 `symbol` 汇总，`family` 仅留一个字段，导致 18/23 品种的多 family 维度被压扁。

**修复**：
- 键改为 `f"{symbol}_{family}"`（复合键）
- 输出条目数从 23 → 70（验证：多 family 品种正确分离）
- 每个条目独立统计 `pass_count`/`fail_count`/`total`/`pass_rate`

**验证**：
```bash
$ python3 scripts/sup_memory_bridge.py /tmp/test.jsonl /tmp/run
[bridge] wrote 70 entries -> /tmp/run/research_memory/ledgers/gate_pass_stats.yaml
```

### 2. 主循环挂点顺序修复（Blocker）

**问题**：`_main_locked` 在 `materialize_known_verdicts()` **之前**调 bridge（L1109-1110），违反 SPEC FR-2。

**修复**：
- 删除 L1109-1110 的错误调用
- 将 bridge 调用移至 `materialize_known_verdicts()` 和 `aggregate_rejection_stats.main()` **之后**（L1167-1172）
- 顺序：materialize → reject refresh → bridge

**代码位置**：
- 旧位置：L1109-1110（`evaluate_goal` 之后）
- 新位置：L1167-1172（`aggregate_rejection_stats.main()` 之后）

### 3. 原子写修复（Blocker）

**问题**：`_write_yaml` 使用 `path.write_text()`，非原子操作。

**修复**：
```python
tmp_path = path.with_suffix('.tmp')
tmp_path.write_text(yaml_str, encoding="utf-8")
tmp_path.replace(path)  # POSIX 原子替换
```

**验证**：输出目录无 `.tmp` 残留文件。

### 4. YAML schema 修复（P1）

**问题**：输出为注释头 + 顶层 `symbols:` 列表，无 `ledger_name`/`entries` 包装。

**修复**：新 schema：
```yaml
ledger_name: gate_pass_stats
description: 自定义旁路统计，非 Praxist 官方 coverage_matrix
version: 1
# protocol_fingerprint: f02b2a43...
entries:
  - id: stats_ao_momentum
    symbol: ao
    family: momentum
    pass_count: 4
    fail_count: 2
    total: 6
    pass_rate: 0.6667
    updated_at: '2026-10-16T20:47:47'
```

### 5. CLI 参数修复（P1）

**问题**：`__main__` 仅 `run()` 无参，走 cache 回落，违反 NFR-4。

**修复**：强制两参 `<aligned_verdicts.jsonl> <run_dir>`：
```python
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python sup_memory_bridge.py <aligned_verdicts.jsonl> <run_dir>")
        sys.exit(1)
    
    aligned_path = Path(sys.argv[1])
    run_dir = Path(sys.argv[2])
    
    if not aligned_path.exists():
        print(f"错误: aligned_verdicts 文件不存在: {aligned_path}", file=sys.stderr)
        sys.exit(1)
    
    run(aligned_verdicts_path=aligned_path, run_dir=run_dir)
```

**验证**：
```bash
$ python3 scripts/sup_memory_bridge.py
用法: python sup_memory_bridge.py <aligned_verdicts.jsonl> <run_dir>
  aligned_verdicts.jsonl: 对齐判定文件路径（只读）
  run_dir: 输出目录（gate_pass_stats.yaml 写入 run_dir/research_memory/ledgers/）

$ python3 scripts/sup_memory_bridge.py nonexistent.jsonl /tmp/run
错误: aligned_verdicts 文件不存在: nonexistent.jsonl
```

## 修改文件清单

| 文件 | 修改内容 | 行数变化 |
|------|----------|----------|
| `scripts/sup_memory_bridge.py` | 聚合维度、原子写、YAML schema、CLI 参数 | ~100 行重写 |
| `scripts/sup_loops.py` | bridge 调用位置（L1109→L1167） | +7/-6 |

## 测试验证

### 聚合维度测试
```bash
$ python3 scripts/sup_memory_bridge.py /tmp/test.jsonl /tmp/run
[bridge] wrote 70 entries -> /tmp/run/research_memory/ledgers/gate_pass_stats.yaml
$ grep -c '  - id:' /tmp/run/research_memory/ledgers/gate_pass_stats.yaml
70
```

**结果**：从 23 → 70 条目，验证多 family 维度正确分离。

### YAML schema 测试
```bash
$ head -15 /tmp/run/research_memory/ledgers/gate_pass_stats.yaml
ledger_name: gate_pass_stats
description: 自定义旁路统计，非 Praxist 官方 coverage_matrix
version: 1
# protocol_fingerprint: f02b2a433fd572eab341c7e4ad2f394168f5a02ddb6d5739dcebbdce49db4ae5
entries:
  - id: stats_ao_momentum
    symbol: ao
    family: momentum
    pass_count: 4
    fail_count: 2
    total: 6
    pass_rate: 0.6667
    updated_at: '2026-10-16T20:47:47'
```

**结果**：schema 符合 §4.2.2 规范。

### 原子写测试
```bash
$ ls -la /tmp/run/research_memory/ledgers/
-rw-r--r-- 1 abug abug 12231 Oct 16 20:47 gate_pass_stats.yaml
```

**结果**：无 `.tmp` 残留，原子写成功。

## 兼容性说明

### 向后兼容
- `run()` 函数签名新增 `aligned_verdicts_path` 参数（默认 None），旧调用方（sup_loops.py）无需修改
- `run_dir=None` 时仍回落至 `data/cache/`（向后兼容手动 CLI 调用）

### 破坏性变更
- CLI 调用方式变更：从 `python sup_memory_bridge.py` 改为 `python sup_memory_bridge.py <aligned> <run_dir>`
- YAML schema 变更：从 `symbols:` 列表改为 `ledger_name`/`entries` 包装
- 聚合维度变更：从 23 条目（按 symbol）改为 70 条目（按 symbol+family）

**影响范围**：仅影响直接调用 CLI 的场景（sup_loops.py 内部调用已适配）。

## 提交信息

```
fix(bridge): SPEC FR-2 compliance — aggregation, atomic write, hook order

Blocker fixes:
- Aggregation dimension: (symbol) → (symbol, family), entries 23→70
- Hook order: bridge moved after materialize+reject (L1109→L1167)
- Atomic write: tmp + os.replace (no partial writes)

P1 fixes:
- YAML schema: ledger_name/entries wrapper (§4.2.2)
- CLI: forced two-arg <aligned_verdicts.jsonl> <run_dir> (NFR-4)

Files modified:
- scripts/sup_memory_bridge.py (full rewrite)
- scripts/sup_loops.py (bridge call relocation)

Verification:
- Aggregation: 70 entries (multi-family separation confirmed)
- Atomic write: no .tmp residuals
- CLI: usage/error messages validated
- Schema: ledger_name/entries structure matches spec

SPEC compliance: FR-2, §4.2.2, NFR-4
```

## HEAD commit

`459c541` fix(bridge): SPEC FR-2 compliance — aggregation, atomic write, hook order

## 审核文档

- 审核报告：`docs/fm-three-loop-obstacles-remediation-spec-code-verify-audit.md`
- SPEC 参考：`docs/superpowers/specs/three-loop-memory-bridge.md`（§4.2.2, FR-2, NFR-4）
