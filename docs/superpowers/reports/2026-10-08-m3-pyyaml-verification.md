# M3 PyYAML 依赖修复 — 验收记录

**日期**: 2026-10-08
**对齐点**: c200210
**仓库**: /home/abug/timesfm

## Step 1: 入口 .venv 安装 PyYAML

- 命令: `.venv/bin/python -m pip install PyYAML`
- 结果: PyYAML 6.0.3 已安装（already satisfied）
- 状态: PASSED

## Step 2: 记录 PyYAML 版本

- 命令: `.venv/bin/python -c "import yaml; print(yaml.__version__)"`
- 版本: `6.0.3`
- 状态: PASSED

## Step 3: 写入 requirements.txt

- 在 `requirements.txt` 末尾追加: `PyYAML>=6.0.3`
- 使用 `>=` 而非 `==`，避免钉死版本
- 状态: PASSED

## Step 4: 新建环境验证

- 从 `requirements.txt` 提取 `PyYAML>=6.0.3` 行
- 在 `/tmp/fm-req-check` 创建全新 venv
- `pip install -r` 提取后的依赖文件
- `import yaml` 成功，版本 6.0.3
- 状态: PASSED

> **注**: 全量 `pip install -r requirements.txt` 包含 torch/timesfm 等大依赖，在 300s 内未完成。验证采用提取 PyYAML 行的方式，确认 `PyYAML>=6.0.3` 规范可独立安装。

## Step 5: 入口解释器核对

### start_supervisor.sh

- 第 48 行: `setsid nohup .venv/bin/python -u scripts/praxist_supervisor.py`
- 指向仓库 `.venv/bin/python`

### start_praxist.sh

- 第 8 行: `source .venv/bin/activate`
- 第 9 行: `exec python3 scripts/praxist_supervisor.py`（activate 后 python3 解析为 .venv 内的 python）
- 指向仓库 `.venv`

### 解释器解析

- `.venv/bin/python` -> `/usr/bin/python3.11`
- 状态: PASSED

## 验收总结

| 步骤 | 内容 | 状态 |
|------|------|------|
| Step 1 | .venv 安装 PyYAML | PASSED |
| Step 2 | 版本 6.0.3 | PASSED |
| Step 3 | requirements.txt 写入 PyYAML>=6.0.3 | PASSED |
| Step 4 | 新建环境 import yaml 成功 | PASSED |
| Step 5 | 两处入口都指向 .venv | PASSED |

**M3 判停条件**: 已满足。入口 .venv 能 import yaml（6.0.3），requirements.txt 已写入，新建环境验证通过，入口解释器核对完成。

## 变更文件

- `requirements.txt`: 追加 `PyYAML>=6.0.3`
