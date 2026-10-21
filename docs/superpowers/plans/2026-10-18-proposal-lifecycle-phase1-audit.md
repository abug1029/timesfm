# Phase 1 实施计划审核（第4轮再审）：提案生命周期

- 审核对象：`/home/abug/timesfm/docs/superpowers/plans/2026-10-18-proposal-lifecycle-phase1.md`
- 计划修订声明：2026-10-18「根据第3轮审核修订（P1-A 挂点修正 + P1-D 测试签名+参数+helper 修正；P0/P2 不变）」
- 计划 mtime：2026-10-18 15:51 Asia/Shanghai（晚于第3轮 audit 15:42 → 确有改动）
- 冻结 SPEC：`docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md`（Frozen；三审 **通过**）
- 上一轮：同路径本文件 / box `shared/reviews/...-phase1-audit.md`（**第3轮再审 · 通过**）
- 代码根：WSL `/home/abug/timesfm`（本轮 tip `d440e08`；harvest 锚点相对 `f2a9a7f` 无漂移）
- 日期：2026-10-18（Asia/Shanghai）
- 轮次：**第4轮再审**
- 结论：**通过**——四条 **P0 无回归**；相对第3轮，**正文未实质闭合 P1-A/D**（修订声明过满）。残留仍为编码 Task 5/7 时消化的非门禁项。可按 Task 1→11 开工，**不必再开计划门禁**。

---

## 0. 总评（相对第3轮的 delta）

| 维度 | 第3轮 | 第4轮 |
|------|-------|-------|
| P0-1..4 | 全闭合 | **仍闭合，无回归** |
| P1-A 作用域挂点 | 部分闭合 | **仍部分闭合**（声明「已修」；Edit 仍绑 `_cand`~717） |
| P1-B missing_id / unknown | 基本闭合 | **仍闭合** |
| P1-C Task8 API 名 | 闭合 | **仍闭合** |
| P1-D harvest 夹具 | 部分闭合 | **仍部分闭合**（声明「已修」；`priority=`×4、helper 仍未定义） |
| 新 P0 | 无 | **无** |

**声明 vs 正文**：头写「P1-A 挂点修正 + P1-D …修正」，但：
- 计划内 `priority_symbols` 出现次数 = **0**；`priority=[` = **4**
- `_patch_harvest_deps` / `_make_minimal_harvest_fixtures`：**仅调用、无 `def`**
- Task 5 Step 2(b) Edit 指令仍：「找到现有的 `_cand` 构造（约 717-730 行）」——重置块与 `_cand` 同挂，未钉到「schema 后、质量门前」

即：**mtime/修订行有更新，关键卫生项未落地**。不构成回退，亦不构成新阻断。

---

## 1. 已闭合 P0 回归核对（必须不回退）

| # | P0 | 本轮证据 | 判定 |
|---|-----|----------|------|
| 1 | `_cand` 注入 `proposal_id`/`version` | Global 禁 `"unknown"`；Task 5 Step 2(b) 显式键；Task 5/7/11 断言 | **仍闭合** |
| 2 | `_reject` 安全写 | Task 5 Step 2(c)：`_qs`/`_bd` 默认；`run_id=basename(run_dir)`；try/except 不改统计 | **仍闭合** |
| 3 | Task8 纯 + Task9 单写 VERDICTS_INC | Global「单一写者」；Task 8 `render_rejection_detail_section` 纯函数 + CLI→REJECTIONS_INC；Task 9 materialize 组装写盘 | **仍闭合** |
| 4 | join = status(verdicted) ⋈ verdicts | Task 9：`_proposal_verdict_causal_lines`；拒收读 `rejected_proposals.jsonl`；queue 仅可选加固 | **仍闭合** |

代码锚点（tip `d440e08`）与第3轮一致、挂点仍有效：

- schema 硬 v1：`sup_harvest.py:604-605` → Task 2 替换目标仍正确
- `_reject` 今日仅统计：`:566-568`；`quality_score` 于质量门后（~684+）
- `_cand` 今日无提案键：`:717-724`；`queue_enqueue` **整行** `json.dumps(r)` 写入（不按 `QUEUE_FIELDS` 裁剪）→ 追加键可落盘
- `rl.append_verdict` → Task 6；`aggregate_rejections` + `OUTPUT_FILE=REJECTIONS_INC` → Task 8
- `materialize_known_verdicts` → Task 9；`prompt_base.jinja2` 已 include → Task 10 不二次 include

---

## 2. 第3轮残留 P1 再核对

### P1-A · `_reject` 作用域 — **仍部分闭合（声明未兑现）**

计划仍写：

- 「每个 proposal 循环开头重置 `_qs/_bd/_proposal_id/...`」
- 「显式缺 proposal_id 拒收：schema 通过后、质量门前」
- 但 Edit：**绑在 `_cand` 构造约 717-730**

现网早期拒收（`unparseable_json` / `schema_mismatch` / `decision_abandon` 等）发生在 `:566` 闭包与 `:604` schema 处，远早于 `_cand`。闭包内对 `_proposal_id`/`_version`/`_symbol`/`_cov`/`_qs`/`_bd` 的引用在赋值前调用 → try 内 NameError → except 吞掉 → **统计仍增、早期拒收可能写不上盘**（与第3轮同类）。

**实现时**：把重置 + `missing_proposal_id` 检查钉在 **schema 通过之后、质量门之前**（约 `symbol=` 赋值同层），不要塞进 `_cand` 块。非计划阻断。

### P1-B · `missing_proposal_id` vs `"unknown"` — **仍闭合**

Global + Task 5 显式拒收 + 禁哨兵；语义与 SPEC 一致。挂点顺序依赖 P1-A 实现时注意。

### P1-C · Task 8 测试 API — **仍闭合**

`import … as ars` → `ars.OUTPUT_FILE` / `aggregate_rejections`；与现网一致。

### P1-D · harvest 夹具签名 — **仍部分闭合（声明未兑现）**

| 调用点 | 状态 |
|--------|------|
| Task 5 `test_cand_contains_proposal_id_and_version` | **仍** `harvest_proposals(tmpdir, top_k=10, priority=[])`（缺位置参） |
| Task 5 `test_missing_proposal_id_rejected` / Task 7 ×2 | 位置参齐，关键字仍 **`priority=`** |
| 全计划 | `priority_symbols` **0 次**；现网签名为 `priority_symbols=`（`:524`）→ 照抄 TypeError |
| `_patch_harvest_deps` / `_make_minimal_harvest_fixtures` | Task 5/7 **调用但计划中无定义** |

建议：编码时直接复用 `tests/test_harvest_proposals.py` 的 `_harvest` / `_make_run` / `_prop`，勿照抄残缺示例。非门禁。

---

## 3. 与冻结 SPEC 一致性（再确认）

| 决定 | 计划 | 判定 |
|------|------|------|
| Model A 事件日志 | Architecture + Task 3 | **一致** |
| soft degraded，Phase 1 不改 harvest 入队 | Global + Task 11 | **一致** |
| 拒收详情 → verdicts.inc；rejections 仅计数 | Global + Task 8/9 | **一致** |
| schema `{v1,v2}`，v2 强制 version | Task 2 | **一致** |
| verdict schema 不改 | Global + Task 6 | **一致** |
| join：status/rejected ⋈ verdicts | Task 9 | **一致** |
| 侧车锁 `path+".lock"` | Task 3/4 | **一致** |

---

## 4. 本轮新观察（均非 P0）

### P1（同第3轮；编码 Task 5/7 消化）

1. **P1-A 挂点**：循环变量重置与缺 id 拒收必须在 schema 后、质量门前。
2. **P1-D 残余**：补全首测签名；`priority` → `priority_symbols`；补 helper 或改用现有 `_harvest`。
3. **修订声明过满**：头称 A/D 已修，正文未改——后续若再改计划，请改正文而非只改修订行。

### P2（可选，无回归）

- `QUEUE_FIELDS` 文档仍未列 `proposal_id`/`version`（行为不挡）。
- Task 6：旧 queue 行缺 `proposal_id` 时可为 None 仍写 verdicted——过渡可接受。
- Task 9 行预算测 / Task 5 `test_degraded_no_reject` 仍有 `pass`——可接受（验收在 Task 11）。

---

## 5. 修正清单（第4轮）

### P0

无（四条均无回归）。

### P1（非门禁；Task 5/7 同批消化）

1. 将 `_qs/_bd/_proposal_id/...` 重置与缺 id 拒收钉到正确控制流位置（勿仅贴 `_cand`）。  
2. 修好 Task 5 首测签名；统一 `priority_symbols`；定义或替换未给出的 fixture helper。

### P2

同第3轮（QUEUE_FIELDS 文档；可选清空 `pass` 测）。

---

## 6. 建议结论

**通过。**

可按 Task 1→11 顺序开工；**不必再改计划才能进 Task 5**，也**不必再开第五轮计划门禁**。相对第3轮：P0/P1-B/C 无回退；声称的 P1-A/D 修正**未写入正文**——编码时按第3轮同款实现提示消化即可。无需重开 SPEC。

---

## 7. 证据摘录（短）

```text
# 计划头（第4轮）
修订状态：…P1-A 挂点修正 + P1-D 测试签名+参数+helper 修正
计划 mtime 15:51 > 第3轮 audit 15:42

# 声明未兑现（计数）
priority_symbols 出现次数 = 0
priority=[ 出现次数 = 4
def _patch_harvest_deps / def _make_minimal_harvest_fixtures = 无

# Task 5(b)（仍）
找到现有的 `_cand` 构造（约 717-730 行）…
# 每个 proposal 循环开头重置…（与 _cand 同块，非真循环头）

# Task 5 首测（仍）
harvest_proposals(tmpdir, top_k=10, priority=[])

# P0-4 Task 9（仍）
因果链 status(verdicted) ⋈ aligned_verdicts；queue 仅可选加固

# 代码 tip d440e08
sup_harvest.py:523-525 签名 priority_symbols=；:566 _reject；:604 schema；:717 _cand
registry_lib.queue_enqueue 整行写入（不裁 QUEUE_FIELDS）
tests/test_harvest_proposals.py: _harvest / _make_run / _prop 可复用
```

---

## 8. 路径

| 产物 | 路径 |
|------|------|
| 本审核（WSL，覆盖写） | `/home/abug/timesfm/docs/superpowers/plans/2026-10-18-proposal-lifecycle-phase1-audit.md` |
| box 副本 | `/workspace/shared/reviews/2026-10-18-proposal-lifecycle-phase1-audit.md` |
| 审核对象 | `.../plans/2026-10-18-proposal-lifecycle-phase1.md` |
| 冻结 SPEC | `.../specs/2026-10-18-proposal-lifecycle-management-spec.md` |
