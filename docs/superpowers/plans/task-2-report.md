# Task 2 报告 — monthly_backtest CLI 参数化 + JSONL resume

## 改了哪些文件

| 文件 | 改动 |
|------|------|
| `scripts/monthly_backtest.py` | 加 3 个 CLI 参数 + JSONL checkpoint 机制 |

仅一个文件。未创建新测试文件 (plan §方向 1 说明回测脚本强依赖 TqSdk 真实 SQLite 数据, 单测不可行)。

## 每处改动一句话摘要

1. **`run_symbol_backtest` 签名 (line 56-67)**: 新增 4 个 keyword 参数 `cache_interval=10, max_points=None, completed=None, checkpoint_fp=None`,均带安全默认值。
2. **`eval_indices` 切片 (line 92-95)**: `max_points is not None` 时 `eval_indices = eval_indices[:max_points]`,在过滤块之前(line 99 过滤块不动)。同时定义 `sym_lower = symbol.lower()` 供 resume key 使用。
3. **`empty_cache` 参数化 (line 139-143)**: 把 `i % 10` 改为 `i % cache_interval`。无参数时默认 10,与原硬编码一致。
4. **resume 跳过 (line 132-134)**: 循环开头 `if completed is not None and (sym_lower, idx) in completed: continue`。
5. **JSONL checkpoint 写入 (line 220-229) — Step 4 实际写入点**: 在 `points.append({...})` (line 208-218) 之后、`if i < 3` print (line 219) 之前插入。写入 schema 固定四字段 `{"symbol","idx","mae","dir_ok"}`,每点 `flush()` 一次。
6. **CLI 参数解析 (line 587-618)**: 在 `--clip-gap` 之后、`symbols = ...` 之前追加 `--cache-interval` / `--max-points` / `--resume` 三块,沿用仓库 `sys.argv.index()` 手写风格,无 argparse。
7. **resume 读取 + checkpoint 句柄初始化 (line 615-637)**: 在 `hourly_model = HourlyModel(...)` (line 614) 之后、`print("[2/4] 运行回测...")` 之前。`--resume` 指定 path 时读 JSONL 到 `completed` set 并以 `"a"` 模式打开同文件;无 `--resume` 时新建带时间戳 checkpoint 文件。
8. **`run_symbol_backtest` 调用处 (line 644-648)**: 追加 `cache_interval=, max_points=, completed=, checkpoint_fp=` 4 个参数透传。
9. **`main()` 末尾关闭 checkpoint (line 741-745 + line 797-799)**: 提前 return 处 (`if not summary_list`) 和正常结束处 (`print("\n完成。")` 后) 都加 `checkpoint_fp.close()`。

### Step 4 checkpoint 写入点选择理由

plan 给的"line 220 前后的 `points.append(...)` 之后、except 之前"指向准确。我精确定位到 `points.append({...})` 在 line 208-218 的 try 块内,写 checkpoint 插在 line 218 之后 / line 219 的调试 print 之前。**关键变量在此处均可达**: `pred` 在 line 164 `pred = hourly_result.point_forecast` 赋值, `real` 在 line 123 赋值, `base` 在 line 122 赋值, `sym_lower` 在 line 94 (新加) 定义。写入在 `except Exception` (line 233) 之前,异常路径不写 checkpoint (符合 plan 设计: 异常点不计入已完成)。`flush()` 在每点写后立即调用,进程被 kill 时已写 JSONL 行不丢。

## Step 6/7/8 冒烟验证实际输出

### Step 6 (cf --max-points 5 --cache-interval 2)
```
[1/1] CF...   [cov=ha_body]
  [1/5] 2020-12-01... daily=7.9s hourly=8.3s pred_shape=(24,) dir_ok mae mae_h cov=24 done
  [2/5] 2020-12-04... daily=1.6s hourly=1.4s ...
  [3/5] 2020-12-10... ...
5pts DirAcc=60%(ref) MAPE=1.08% decay=1.35x EV=-0.276 PF=0.57 MaxDD=-3.50% WR=40%
[checkpoint] 写入 D:\FlyBuddy\fm_a\reports\monthly_backtest\checkpoint_20260729_123125.jsonl
```
exit code 0。只跑 5 点 (而非全量 ~396 点)。`checkpoint_*.jsonl` 文件生成。

### checkpoint JSONL 内容 (5 行)
```
{"symbol": "cf", "idx": 480, "mae": 0.3773, "dir_ok": true}
{"symbol": "cf", "idx": 504, "mae": 0.3928, "dir_ok": true}
{"symbol": "cf", "idx": 528, "mae": 1.8139, "dir_ok": false}
{"symbol": "cf", "idx": 552, "mae": 2.3593, "dir_ok": false}
{"symbol": "cf", "idx": 576, "mae": 0.092, "dir_ok": true}
```
四字段 schema 完全符合 plan。

### Step 7 (resume 跳过验证)
```
[resume] 已加载 5 个完成点 from reports/monthly_backtest/checkpoint_20260729_123125.jsonl
[2/4] 运行回测...
  [1/1] CF...   [cov=ha_body]
FAIL       ← 因为 5 个点全跳过,summarize 返回 None
```
exit code 0。5 个 idx 全部命中 `completed` set,循环内全部 `continue` 跳过,无 `[i/5]` 重复打印,checkpoint 文件行数仍为 5 (未追加)。

### Step 8 (无参数 import OK)
```
import OK
run_symbol_backtest signature: ('symbol', 'daily_model', 'hourly_model', 'cov_override', 'cov_combo', 'clip_gap', 'cache_interval', 'max_points', 'completed', 'checkpoint_fp')
```
签名正确,默认值 `cache_interval=10, max_points=None, completed=None, checkpoint_fp=None` 保证无参数时行为与现状一致。

## concerns

1. **Step 4 实际行号 vs plan 描述差异**: plan 描述 "line 220 前后的 points.append 之后、except 之前",实际 `points.append` 在 line 208-218 (而非 ~220),写 checkpoint 插入点 line 220-229。差异是 plan 作者对行号估算的 ±10 行漂移,定位逻辑 (append 后、except 前、pred/real/base 均可达) 与 plan 设计意图完全一致,**零实质偏差**。

2. **Step 2 "无 resume 也写 checkpoint" — 偏离零回归铁律的边界判断**:
   - plan Step 2 设计为无 `--resume` 时也自动新建带时间戳的 checkpoint 文件并 print 一行 `[checkpoint] 写入 ...`。这是**新增的副作用**,严格说违反用户简报"无参数时行为与现状完全一致"的零回归铁律。
   - **缓解**: 该副作用仅是 stdout 增加一行 + 一个 jsonl 文件 (不影响回测结果、不影响 history.json、不影响月度报告)。且功能上是 plan 的核心目标 (供下次 --resume 使用,实质为方向 1 的设计意图)。
   - **裁决建议**: 我倾向认为这是 plan 设计的本意,不是回归 — "无参数时行为不变"指的是回测结果不变,checkpoint 副作用是 plan 明确要求的新行为。是否算回归交由 reviewer 裁决。若 reviewer 不接受,最小修改是把 else 块改为 `checkpoint_fp = None`(不写 checkpoint),只在 `--resume` 时打开句柄。

3. **无其他 concerns**。所有改动逻辑符合 plan 步骤,三个冒烟验证全部通过。

## commit hash

`3cff1ea` — `feat(backtest): monthly_backtest 加 --cache-interval/--max-points/--resume (JSONL 断点)`