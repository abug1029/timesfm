# 审核：CHANGELOG 三环障碍修复（2026-10-16）

- 对象：`/home/abug/timesfm/docs/superpowers/changelogs/2026-10-16-obstacles-remediation.md`（1002 字节，mtime **2026-10-16 11:32 CST**，commit `b427fed`）
- 对照代码（只读）：`scripts/sup_loops.py`、`scripts/sup_memory_bridge.py`、`scripts/sup_paths.py`、`scripts/regenerate_missing_baselines.sh`、`scripts/aggregate_rejection_stats.py`、`task_FM/prompt_base.jinja2`、`task_FM/known_rejections.inc.md`、`task_FM/config/baseline_points_{pp,bz,eb}_nocov.jsonl`、`data/cache/gate_pass_stats.yaml`、`check_baseline_coverage.py`
- 对照规范/计划：SPEC v1.1（有条件通过）；计划 audit（有条件通过；Task3 须 Path + `sup_evidence._…`）
- 分支/HEAD：`fix/obstacles-remediation` @ `b427fed`（未宣称已合并/push）
- Box 镜像：`/workspace/shared/reviews/2026-10-16-obstacles-remediation-changelog-audit.md`
- 审核时间：**2026-10-16 12:35 CST**
- 结论：**有条件通过** — 三障碍主干（include+刷新、桥接落盘、pp/bz/eb 基线→100%）与所列四 commit **属实**；计划残留的 Path/限定名指纹在实现侧已处理或规避。但 CHANGELOG 过简，未披露桥接**输出路径/schema 相对 SPEC·计划偏离**、**尚无读者消费** `gate_pass_stats.yaml`，以及 `Path`/`REJECTIONS_INC` 死代码。修文档口径后再当「闭环完成」更稳。

## 1. 结论

实现方向与 SPEC/计划通过项对齐，**代码侧可视为障碍 1 / 4 已落地，障碍 2 的「写旁路 YAML」已落地**。CHANGELOG 作为交付说明：**功能与 commit 表大体属实，覆盖度 100% 可复跑证实**；对「Cross-Run Feedback」与验证勾选的表述偏乐观（生成≠被 peer/fast-loop 读取；路径≠SPEC 的 `run_dir/research_memory/ledgers/`）。建议补路径、schema、消费缺口与未合并状态后再标「完成闭环」。

## 2. CHANGELOG 摘要 vs 实况对照表

| # | CHANGELOG 声称 | 实况 | 判定 |
|---|---------------|------|------|
| 1 | 覆盖度 88.9% → **100%** | `check_baseline_coverage.py`：27/27，`coverage_ratio=1.0`，`gate_passed=true`，`uncovered=[]` | **属实** |
| 2 | 障碍1：改 `prompt_base.jinja2` / `sup_loops.py` / `sup_paths.py`；`1487c0d` | 该 commit：prompt 追加 known_rejections include；两处 materialize 后调 `aggregate_rejection_stats.main()`；`REJECTIONS_INC` 常量 | **属实** |
| 3 | 障碍2：新建 `sup_memory_bridge.py`；`sup_loops` 两处挂点；`8df4209` | 文件存在；`_maybe_finish_slow` / `_main_locked` 各 try-import-run；commit 文案一致 | **属实** |
| 4 | 障碍2 产出 `gate_pass_stats.yaml`「正常生成」 | 现网 `data/cache/gate_pass_stats.yaml`（2643B，~23 symbol，含 pass_count/fail_count/total/pass_rate，mtime 近） | **半属实**：文件在，但路径是 **`data/cache/`**，非 SPEC/计划的 **`<last_run_dir>/research_memory/ledgers/`**；现 last_run_dir 下 **无** ledgers/ |
| 5 | 障碍4：`regenerate_missing_baselines.sh`；pp/bz/eb「111K/51K/111K」；`2c1dae1` | 脚本存在且 `tee -a`；config 下三文件 **113436 / 51753 / 113595** 字节（≈111K/51K/111K）；commit 写入三 nocov jsonl | **属实**（体量四舍五入） |
| 6 | 拒收摘要「自动刷新正常」 | `known_rejections.inc.md` 标题正确；Generated at 2026-10-16T12:32…；挂点仍在；本轮窗「0 条拒收」但跨轮累计有内容 | **属实**（本轮空拒收不否定刷新链路） |
| 7 | 提交表：`ecd4df7` / `1487c0d` / `8df4209` / `2c1dae1` | 四 hash 均存在且 message 匹配；另有 **`b427fed` docs: add changelog** 未列入表（软） | **属实**（表不完整但不假） |
| 8 | 「修复 Cross-Run Feedback 缺失」 | 仅有**写端**；全仓除 bridge 外 **无** gate_pass_stats 读者；docstring 称供 fast-loop 参考，但未接线 | **过称 / 名实偏弱** |
| 9 | （未写）相对计划：Task3 Path + 指纹 | `sup_loops` 已 `from pathlib import Path`，但 **全文仅 import、零使用**；bridge 内指纹为 **`sup_evidence._current_protocol_fingerprint()`** ✅；挂点改为直接 `run()`，不再用 last_run_dir+Path | **计划残留已规避/部分落地**；CHANGELOG 未披露简化 |
| 10 | （未写）`REJECTIONS_INC` | `sup_paths.REJECTIONS_INC` 已加，但 aggregate 仍硬编码 OUTPUT_FILE，**常量未被引用** | **死代码**（功能仍通） |
| 11 | （未写）合并/部署 | 分支 `fix/obstacles-remediation`，工作区仍有运行态脏文件；CHANGELOG **未宣称** merge/push | **未过称** ✅ |
| 12 | YAML schema（未详述） | 实为 `# protocol_fingerprint` + `symbols:` 列表；**无** SPEC 伪码中的 `ledger_name` / entries 包装 | **与 SPEC 伪码不一致**（CHANGELOG 未承诺字段，软） |

### 提交拆解（已核）

| Commit | 描述（CHANGELOG） | 实况要点 |
|--------|-------------------|----------|
| `ecd4df7` | chore: 准备执行障碍修复任务 | 空/文档向准备提交，属实 |
| `1487c0d` | feat: Peer 可见拒收摘要自动刷新 | +5 行：import + 两处 main() + include + REJECTIONS_INC |
| `8df4209` | feat: Cross-Run Feedback bridge | +sup_memory_bridge.py（80 行）+ 两挂点；**写 data/cache/gate_pass_stats.yaml** |
| `2c1dae1` | ops: regenerate pp/bz/eb baselines | +脚本 + 三 nocov jsonl（267/588/588 行） |
| `b427fed` | （表未列）docs: add changelog | 本 CHANGELOG 自身 |

## 3. 相对 SPEC / 计划缺口

| SPEC/计划项 | CHANGELOG/代码 | 意见 |
|-------------|----------------|------|
| Phase1 include + materialize 后刷拒收 | 已落地；验证勾选成立 | 对齐 |
| Phase2 写 gate_pass_stats.yaml | 已写，但路径改为稳定的 data/cache/ | **偏离 SPEC/计划路径**；对「跨 run」更合理，须改 SPEC/CHANGELOG 口径 |
| Phase2 经 last_run_dir + Path 挂点 | 挂点直接 run()；Path 闲置 | 简化可接受，文档应记 |
| 指纹 sup_evidence._… | bridge 内正确 | 对齐计划复审建议 |
| Phase3 tee -a + pp→bz→eb + --cov none | 脚本一致 | 对齐 |
| 库路径 db/futures_*.db | 三库存在；脚本未写错 data/ | OK |
| 验收：ledgers 下文件 | 现网无该路径；验的是 cache 文件 | CHANGELOG「正常生成」易误导后人去 ledgers 找 |
| Cross-Run / peer 可读 | 无 include、无 loader | **P0 写端完成，消费未做**——CHANGELOG 不宜暗示反馈已闭环 |
| 覆盖度 gate >95% → 100% | 复跑通过 | 对齐 |

## 4. 风险与建议

### Blocker（建议改 CHANGELOG / 对齐 SPEC 后再当「闭环基线」）

无代码级「功能未提交」Blocker。文档：

1. **写明桥接落点**：`data/cache/gate_pass_stats.yaml`（稳定旁路），并注明 **与 SPEC/计划 run_dir/…/ledgers/ 不一致**；或回改实现以符合 SPEC，二者择一。
2. **弱化「Cross-Run Feedback 已修复」**：改为「已落盘历史过门统计；peer/fast-loop **尚未读取**」——除非补消费端。

### P1

3. 删除或真正使用 `sup_loops` 的 Path 导入；`REJECTIONS_INC` 接到 aggregate（或删常量）。
4. CHANGELOG 补：分支名、HEAD/`b427fed`、输出路径、schema 摘要、未 merge。
5. 若保留 cache 路径，同步修订 SPEC v1.1 / 计划验收命令（勿再 ls …/ledgers/gate_pass_stats.yaml）。

### P2

6. 挂点侧 except 已用 Exception ✅；可考虑原子写（tmp+replace）——当前 write_text 非原子（软）。
7. 空指纹 registry 行在 only_protocol=fp 下被过滤——与计划 audit 已知软点一致，可在 CHANGELOG「已知限制」提一句。

## 5. 范围判定

- 只读 CHANGELOG 与上述代码/git/数据；audit 写入同目录 `2026-10-16-obstacles-remediation-audit.md` 与 box `…-changelog-audit.md`。
- 未改业务代码、未 commit/push、**未释放本机锁**（由父代理/总管释放）。

## 6. 摘要

**有条件通过。**  
宣称的四 commit、100% 覆盖度、拒收 include+刷新、桥接文件存在、pp/bz/eb 基线体量均与现网一致。主要保留意见：(1) 桥接路径/schema 偏离 SPEC·计划且 CHANGELOG 未披露；(2) 「Cross-Run Feedback」仅有写端无读者；(3) 闲置 Path/REJECTIONS_INC。障碍 1/4 可视为完成；障碍 2 建议改称「过门统计旁路已落盘」并补文档或消费端后再关单。
