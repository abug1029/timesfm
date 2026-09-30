# dead-code 归档（2026-09-30）

依据：`docs/2026-09-30-dead-code-purge-spec.md`（v2 + (f) 勘误）+ 宿主裁定 (e)。
不删只归档：git mv 保留历史，`git log --follow` 可追溯。

## 代码归档目录（4 处）

| 目录 | 内容 | 规模 |
|------|------|------|
| `scripts/archive/2026-09-30-dead-code/` | D1 证据保留 6 件 + D2 一次性调查 22 件 + D3 脚手架 5 件 | 33 文件 / 6,971 行 |
| `scripts/archive/2026-09-30-a2-retired/` | A2 LGBM 脚本 10 件（CF-13，裁定 e） | 10 文件 / 3,032 行 |
| `cascade/archive/2026-09-30-a2-retired/` | `lgbm_features.py` | 1 文件 / 371 行 |
| `tests/archive/2026-09-30-a2-retired/` | A2 测试 5 件 | 5 文件 / 1,854 行 |

合计 49 文件 / 12,228 行。regen 三件套（`regenerate_all_baselines.py` / `regen_rb.py` /
`monitor_rb_regen.sh`）顺延 2.9：v4 重生波完成后归档并释放
`tests/test_no_dead_code.py` 的 `TEMPORARY_ALLOWLIST`。

## 防再堆积闸门

- `tests/test_no_dead_code.py`：AST 导入图挂账断言（scope 内每个模块必须被引用或进名单）
- `pytest.ini`：`testpaths=tests` + `norecursedirs`（archive / third_party / .venv）
- 挂账名单中的 `REVIEW_CANDIDATES`（6 件零引用零文档脚本）待 2.9 后宿主复核

## 本目录

本文档为轻量归档说明，不迁移历史报告；报告证据链见 `docs/superpowers/reports/`
与 `docs/superpowers/changelogs/`（勿删勿归档）。
