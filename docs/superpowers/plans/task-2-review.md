# Task 2 Review — monthly_backtest CLI 参数化 + JSONL resume

**BASE:** `03836f0` → **HEAD:** `3cff1ea`
**Diff:** `scripts/monthly_backtest.py` (+91/-4), 单文件改动

---

## Spec Compliance: PASS (附 1 条 Important finding)

逐 Step 核对 plan:

| Step | 内容 | 结果 |
|------|------|------|
| 1 | CLI 解析 (`--cache-interval` / `--max-points` / `--resume`) | ✅ 默认值一致 (10 / None / None),手写 `args.index()` 风格一致,错误处理一致 |
| 2 | resume 读 JSONL + checkpoint 写句柄 | ⚠️ `if resume_path` 分支完全匹配 plan;`else` 分支也匹配 plan 原文,**但与零回归铁律冲突**(见下) |
| 3 | `run_symbol_backtest` 调用处加 4 个新参数 | ✅ line 702-706,参数名与默认值完全一致 |
| 4 | 签名 + `eval_indices[:max_points]` + `empty_cache` 参数化 + 循环跳过 + JSONL 写入 | ✅ 全部齐全 |
| 5 | `main()` 末尾 + 提前 return 处均 `close()` | ✅ line 741-742 (提前 return) + line 790-791 (正常结束) |

### Step 4 细节核对

- **签名** (line 56-59): `cache_interval=10, max_points=None, completed=None, checkpoint_fp=None` ✅
- **eval_indices 切片** (line 97-100): `if max_points is not None: eval_indices = eval_indices[:max_points]`,在过滤块 (line 108-111) 之前 ✅
- **sym_lower** (line 100): `sym_lower = symbol.lower()` 在过滤块之前定义,后续 resume key 和 JSONL 都用到 ✅
- **empty_cache** (line 140): `i % cache_interval == 0` ✅
- **resume 跳过** (line 132-134): `if completed is not None and (sym_lower, idx) in completed: continue` ✅
- **JSONL 写入** (line 233-241):
  - 位于 `points.append({...})` (line 222-232) 之后、`except` (line 244) 之前 ✅
  - 四字段 schema `{symbol, idx, mae, dir_ok}` ✅
  - `flush()` 每点调用 ✅
  - `pred` / `real` / `base` / `sym_lower` 均可达 ✅
  - `_mae_pt` 计算: `np.mean(np.abs(pred - real[-1:])) / base * 100` — 仅对最后一个 horizon 点算 MAE,符合 plan 设计 ✅
  - `dir_ok`: `np.sign(pred[-1] - base) == np.sign(real[-1] - base)` — T+24 方向判断 ✅

---

## Task Quality: PASS

- 代码风格与仓库一致 (手写 CLI 解析、无 argparse)
- 无并发 / Daemon / multiprocessing
- 异常路径不写 checkpoint (符合设计: 异常点不计入已完成)
- `import json as _json` / `from pathlib import Path` 局部 import 避免顶层依赖变更 ✅
- 提前 return 和正常结束两处都 `close()`,无句柄泄漏 ✅

---

## 冒烟验证实际输出

### Step 8 (无参数 import + 签名检查)

```
import OK
run_symbol_backtest signature: ('symbol', 'daily_model', 'hourly_model', 'cov_override', 'cov_combo', 'clip_gap', 'cache_interval', 'max_points', 'completed', 'checkpoint_fp')
  cache_interval = 10
  max_points = None
  completed = None
  checkpoint_fp = None
```

✅ 默认值全部与 plan / 零回归要求一致。

### Step 6 (cf --max-points 5 --cache-interval 2) — 来自 report

```
[1/1] CF...   [cov=ha_body]
  [1/5] 2020-12-01... done
  [2/5] 2020-12-04... done
  ...
5pts DirAcc=60%(ref) MAPE=1.08% ...
[checkpoint] 写入 D:\FlyBuddy\fm_a\reports\monthly_backtest\checkpoint_20260729_123125.jsonl
```

✅ 只跑 5 点,checkpoint 文件生成。

### JSONL 内容验证 (已落盘)

```json
{"symbol": "cf", "idx": 480, "mae": 0.3773, "dir_ok": true}
{"symbol": "cf", "idx": 504, "mae": 0.3928, "dir_ok": true}
{"symbol": "cf", "idx": 528, "mae": 1.8139, "dir_ok": false}
{"symbol": "cf", "idx": 552, "mae": 2.3593, "dir_ok": false}
{"symbol": "cf", "idx": 576, "mae": 0.092, "dir_ok": true}
```

✅ 四字段 schema 完全正确,5 行对应 5 个评估点。

### Step 7 (resume 跳过) — 来自 report

```
[resume] 已加载 5 个完成点 from ...checkpoint_20260729_123125.jsonl
[2/4] 运行回测...
  [1/1] CF...   [cov=ha_body]
FAIL  (5 点全跳过, summarize 返回 None, exit 0)
```

✅ 5 个 idx 全部跳过,无重复 `[i/5]` 打印,checkpoint 未追加新行。

---

## Findings

### Important-1: `else` 分支无 `--resume` 时自动新建 checkpoint 文件 — 违反零回归铁律

**位置:** line 682-686

```python
    else:
        # 无 resume 时, 若要写 checkpoint, 新建带时间戳文件 (供下次 --resume)
        ck_path = BACKTEST_DIR / f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        checkpoint_fp = open(ck_path, "a", encoding="utf-8")
        print(f"  [checkpoint] 写入 {ck_path}")
```

**问题:**
- **新增文件副作用**: 无参数运行时在 `reports/monthly_backtest/` 下产生一个 `checkpoint_<ts>.jsonl` 空文件 (0 行),现有工作流不预期此文件。
- **新增 stdout 行**: `[checkpoint] 写入 ...` — 现有运行无此行,可能干扰 Monitor 工具的日志匹配。
- **违反零回归铁律**: 用户简报明确要求 "无参数时行为与现状完全一致",此处新增了可观测的副作用。

**Plan 原文与零回归的矛盾:**
Plan Step 2 确实写了 "无 resume 时,若要写 checkpoint,新建带时间戳文件"。但 Global Constraints 的零回归铁律是无条件的。Plan 内部的矛盾不应由 implementer 单方面裁决 — implementer 已正确标出此 concern 并提交 reviewer。

**裁决: reject plan 此设计,要求修改。**

理由:
1. 零回归铁律是 spec 顶层约束,优先级高于 plan 步骤细节。
2. "供下次 --resume 使用" 的理由不成立 — 用户若要从零开始跑,本不需要 checkpoint;若需要断点续跑,会显式传 `--resume`。自动创建文件是 over-eager 行为。
3. 每次无参数运行都留一个空 JSONL,长此以往 `reports/monthly_backtest/` 会堆满无用文件。

**修复方案 (implementer 已建议,最小改动):**
将 `else` 块改为:

```python
    else:
        checkpoint_fp = None
```

这样仅 `--resume` 时打开句柄,无参数时 `checkpoint_fp` 保持 `None`,整个 checkpoint 写入逻辑 (`if checkpoint_fp is not None`) 自然跳过。

---

## Implementer Concern 裁决

| Concern | 裁决 | 理由 |
|---------|------|------|
| Concern #1: Step 4 行号 ±10 漂移 | **Accept (无实质偏差)** | plan 已注明"以实际为准",定位逻辑 (append 后、except 前、变量可达) 完全一致 |
| Concern #2: 无 `--resume` 也写 checkpoint | **Reject — 要求改 else 块为 `checkpoint_fp = None`** | 违反零回归铁律 (新增文件 + stdout 副作用),见 Important-1 |

---

## 总结

| 维度 | 结论 |
|------|------|
| Spec compliance | PASS (5/5 Step 均实现,逻辑正确) |
| Task quality | PASS (代码质量高,风格一致) |
| Findings | 1 Important (else 分支零回归违反) |
| 冒烟验证 | 3/3 通过 (Step 6/7/8),JSONL schema 正确 |
| Concern 裁决 | #1 Accept,#2 Reject 要求改 |

## Verdict: 需修复 R1

Implementer 将 `else` 块改为 `checkpoint_fp = None` 后即可 APPROVED。改动量: 2 行 (删 `ck_path` 和 `open` 行,改 `checkpoint_fp = None`)。改后无需重跑冒烟(无参数时不再产生 checkpoint 文件,stdout 少一行)。
