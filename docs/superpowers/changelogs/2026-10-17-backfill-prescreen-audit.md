# 第三遍复审：backfill_prescreen v2.0.1（对照上一审「有条件通过」残留）

| 项 | 值 |
|----|----|
| 对象 | `/home/abug/timesfm/scripts/backfill_prescreen.py`（550 行） |
| 修订 commit | `94f3931` fix(v2.0.1): 对齐现网 variant_id/dead/existing 契约（前序 `96dd396` / `7bac99e` / `1b511f1`） |
| HEAD（该文件） | `94f3931` |
| SCRIPT_VERSION | `2.0.1` |
| 复审时间 | 2026-10-17 21:52 CST（Asia/Shanghai） |
| 方法 | 对照上一审残留清单；`git show 94f3931`；静读 `should_skip`/`generate_variant_id`/REGISTRY 入队段；对照 `sup_harvest` W6.4 身份链与 `sup_loops._harvest_rows`；本地断言 `--force` 顺序；`vid` 与 harvest 同链比对；`python scripts/backfill_prescreen.py --dry-run --max 1 --skip-laya-check` |

---

## §1 结论

**通过。**

上一审残留的 B2（vid / REGISTRY dead·existing / stage）与 P1 `--force` **均已按现网契约修好**。B1/B3/B4 抽核仍成立。`--dry-run --max 1` EXIT=0（v2.0.1）。

软残留不影响「能否放量」判断：**可以 nohup 全量**（建议仍先 `--max 50~100` 观察一波入队/ dedup 日志，再拉满）。

---

## §2 缺口状态表（对照上一审）

| 缺口 | 上一审 | 本遍 | 证据 |
|------|--------|------|------|
| B1 `cooldown_hours` AttributeError | 已修复 | **仍成立** | 全文件无 `cooldown_hours`/`hashlib`/`md5`；dry-run 正常启动 |
| B2.1 `variant_id`=path-md5 | 部分 | **已修复** | `generate_variant_id` → `resolve_cov_family` + `sup_evidence._experiment_fp_for` + `build_variant_id`；`fam=="unknown" or fp is None` → `None` 拒入队。抽样 `ss`/`momentum_20`：`ss_momentum_9166e826d443` 与 harvest 同链 **match True** |
| B2.2 dead/existing 读队列 | 部分 | **已修复**（软差见下） | `rl.load_snapshot(sp.REGISTRY)` + `dead_variants`；日志语义「REGISTRY 已有…」。本机：`reg_n=503 dead=304`。不再对 queue 调 `load_snapshot` |
| B2.3 `stage=prescreen` | 部分 | **已修复** | 入队行 `"stage": "aligned"`，与 harvest 一致 |
| B3 `processed_set` 只标 success | 已修复 | **仍成立** | 仅 `status_label == "success"` 时 `add` |
| B4 `last_run` UTC | 已修复 | **仍成立** | 写/比均 `timezone.utc`；Z/naive 兜底仍在 |
| P1 `--force` 仍跳过 success 文件 | 部分 | **已修复** | `should_skip` **最先** `if force: return False`；断言：`force=True` + success 文件 + processed → **不跳过** |

---

## §3 抽核

### 3.1 身份链 vs harvest

| 侧 | 代码 |
|----|------|
| harvest survivors / peer（fp 段） | `fp=_experiment_fp_for`；不可得则 skip；`vid=build_variant_id(symbol, fam, fp)` |
| backfill v2.0.1 | 同链；不可得返回 `None`，调用方拒入队并标 `degraded` |

说明：peer harvest 的 `fam` 优先来自 covariate pool；backfill（及 survivors）用 `resolve_cov_family({"cov_override": ...})`。绝大多数 cov 一致；极端 pool 标注漂移为软差。

### 3.2 `--force` 顺序（本地断言）

```text
force=True  + success .prescreen.json + in processed → skip=False
force=False + success file              → skip=True
force=False + in processed              → skip=True
force=False + 无文件无 processed         → skip=False
→ should_skip_force_ok
```

### 3.3 Dry-run

```text
backfill_prescreen v2.0.1 启动
扫描到 6899 个提案
待处理: 1
Dry run 模式 ... EXIT:0
```

### 3.4 REGISTRY / 队列路径

| 项 | 实况 |
|----|------|
| 默认队列 | `sp.QUEUE` → `data/cache/aligned_pending.jsonl` |
| REGISTRY | `task_FM/config/aligned_verdicts.jsonl` |
| 入队 API | `rl.queue_enqueue(..., dead, existing)`（内部再对 pending `inq` 去重） |

---

## §4 残留（均为软 / P2）

1. **existing 组成与 harvest 不完全同构**：现网 `_harvest_rows` 用 `_active_protocol_snapshot(REGISTRY)` + `in_flight_ids(QUEUE, INPROGRESS)`；本脚本用全量 `load_snapshot` 键集、未显式并入 INPROGRESS。`queue_enqueue` 会挡 pending 内重复，但**正在 INPROGRESS 的 vid** 仍可能被再入 pending（竞态窗口小；当前 inflight≈7）。全量 REGISTRY 比 active-protocol 更保守（少重复、也可能挡旧协议可重试项）——对积压回填可接受。
2. **W6.4 拒入队与 success 落盘顺序**：`prescreen_and_save` 已写 success 后若 `variant_id is None`，返回 `degraded` 且不入 `processed_set`，但下次无 `--force` 会因 success 文件永久跳过 → 该提案既不入队也不再试。空 cov 等场景会触发（抽样 `rb`+`""` → `None`）。建议：拒入队时改写/删除 success 标记，或 force 语义文档写清。
3. **`stats.inc("success")` 在 vid 检查之前**：vid 失败时 success 计数虚高。
4. **`max_points=600` 硬编码**（harvest 取 cadence `aligned_max_points`）。
5. **批末一次性入队**：崩溃窗口内「已记 processed、未入队」仍可能（上一审 P2，未改）。

---

## §5 结论摘要

| 维度 | 结果 |
|------|------|
| 总评 | **通过** |
| 上一审 B1/B3/B4 | 抽核仍成立 |
| 上一审 B2（vid/REGISTRY/stage） | **已修复** |
| 上一审 P1 `--force` | **已修复** |
| dry-run | 通过（v2.0.1） |
| nohup 全量 ~6899 | **可以**；建议先 `--max 50~100` 看 REGISTRY dedup/入队日志，再放开。注意软残留 1–2 |
| 下一步（非门闩） | 可选：`existing |= in_flight_ids`；对齐 `_active_protocol_snapshot`；vid 拒收时处理 success 落盘；success 计数挪到 vid OK 之后 |

旁路镜像：`/workspace/shared/reviews/2026-10-17-backfill-prescreen-audit.md`
