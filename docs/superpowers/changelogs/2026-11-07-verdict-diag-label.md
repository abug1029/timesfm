# Changelog: 裁决诊断标签

> **代码基线**: `5b02284`
> 日期：2026-11-07
> 规格：`docs/superpowers/specs/2026-11-07-verdict-diag-label-spec.md`
> 施工单：`docs/superpowers/plans/2026-11-07-verdict-diag-label.md`
> 缘起：`docs/superpowers/reports/2026-11-07-cogalpha-three-loop-borrow-report.md` 第 4.1 节与第 7 节

## TL;DR

`known_verdicts.inc.md` 在 Effective clues 之后多了一节「诊断样本」。每个目标品种一行正面、一行反面。句子只根据已经落盘的字段生成，不把提案者事前写的机制当成失败原因。

硬门、收割、协议指纹、目标文件和提示词都没有改。监督环没有重启。正在运行的进程要等下一次物化，这一节才会出现在磁盘上的线索文件里。

## 做了什么

- `format_verdict_diag_label`：一行裁决对应一句互斥标签。未过硬门时，无效裁决和不可确认的 DM 先于方向数字。三个方向字段缺任何一个，写成「不足以归因」。
- 过硬门且 DM 不可确认时，先于 p 值判断。描述性 p 值即使很小，也不写成「本行 DM p ≤ 0.05」。过硬门不是确认成功，硬门本身不读 DM。
- `select_symbol_diag_pair`：正面先取过硬门里方向准确率最高的一行，否则取近失。反面先在本品种剩下的可确认失败里挑，本品种没有了才按同一协变量跨品种。没有正面时，本品种只有一个协变量才允许跨品种。
- 选入的行必须同时有有限的 `dir_acc`、`baseline_dir_acc`、`effective_min`。同分时品种名按 `casefold()` 比较，再比 `variant_id`。同一条字典不会既当本品种的正面又当本品种的反面。
- `materialize_known_verdicts` 在 `lines.extend(clue_lines)` 之后、未停止的树之前插入这一节。只使用当前主协议指纹的行。`repeat_n` 至少为 2 才写「同协变量可确认失败」。

## 明确没做

- 不改 `scripts/sup_harvest.py`，不改 `gate()`，不改 `task_FM/prompt_base.jinja2`，不改 `scripts/praxist_goal.yaml`。
- 标签不写进 `aligned_verdicts.jsonl`，不进入协议指纹，不重生基线。
- 不做冻结池里的措辞轮换，不实现前缀截断或未来扰动检验。
- 不把「已失败 variant 的再次提案率」当作这次的验收。那是线索上线之后才能比的运行指标。

## 提交

| Commit | 说明 |
|---|---|
| `0080849` | 诊断标签与单测 |
| `98219cf` | 先选本品种正反样本，再考虑跨品种 |
| `beac572` | 品种名比较改为 `casefold()` |
| `5b02284` | 把诊断样本写入线索文件 |

合入方式：活仓 `master` 从 `d3e2679` 快进到 `5b02284`。没有推送。

## 测试

`tests/test_verdict_diag_label.py` 与 `tests/test_known_verdicts_injection_20261005.py` 在合并后的 `master` 上一起是 39 项通过。没有跑全库。

## 文档

操作文档改为点名「诊断样本」：`docs/praxist.md`、`docs/runbook_praxist_three_loop.md`、`docs/glossary.md`、`docs/system_design.md`、`docs/README.md`、`task_FM/AGENTS.md`。标签全文仍以规格为准，阈值数字仍只在 `docs/evaluation.md`。
