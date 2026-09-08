# Praxist Peer 评估失败诊断与解决方案

> 日期: 2026-09-08
> 状态: 待执行

---

## 问题描述

Praxist peer agents 在 Gen 1 中无法执行评估，所有评估尝试被 delete guard 阻止：

```
WARNING: delete guard denied Bash tool use:
Praxist delete guard blocked Python runtime introspection
that could bypass peer-local file safety.
```

**影响**: Gen 1 findings = 0，peers 无法产出有效评估结果。
**不影响**: Slow Loop (aligned_backtest) 正常运行，因为它由 supervisor 直接启动，不经过 delete guard。

---

## 根因分析

### 双层防线架构

```
Peer Bash 命令
    │
    ▼
┌─────────────────────────────────────────────┐
│ Layer 1: PreToolUse Shell Guard             │
│ 文件: praxist/plugins/.../delete_guard.py   │
│ 检查: 命令字符串模式匹配                      │
│ 阻止: python -c + introspection patterns    │
└────────────────────┬────────────────────────┘
                     │ (pass)
                     ▼
┌─────────────────────────────────────────────┐
│ Layer 2: Python sitecustomize.py            │
│ 注入到 peer 的 Python 环境                   │
│ 拦截: builtins.open, os.remove 等           │
│ 限制: 写入只能在 PRAXIST_SAFE_DELETE_ROOTS  │
│ 信任: PRAXIST_TRUSTED_PROJECT_ROOTS         │
└─────────────────────────────────────────────┘
```

### Layer 1 阻止规则（shell 级）

**硬阻止（当 escape_context=True 时）**:
```python
hard_introspection_escape = [
    "sys.modules", ".modules", "modules[", "modules.",
    "__globals__", "__defaults__", "__code__",
    "exec(", "eval(", "sitecustomize",
]
soft_introspection_escape = [
    "globals()", "locals()", "vars(", "dir(",
]
```

**触发条件 `escape_context`**:
```python
escape_context = protected_target OR direct_delete OR shell_delete OR shell_escape
```

其中 `shell_escape` 包含: `__import__(`, `getattr(`, `os.system`, `subprocess`, `popen(`

### Layer 2 阻止规则（Python 级）

sitecustomize.py 在 Python 解释器启动时自动加载，拦截所有文件 I/O：
- 写入只允许在 `PRAXIST_SAFE_DELETE_ROOTS`（peer workspace + tmp）
- `PRAXIST_TRUSTED_PROJECT_ROOTS` 定义可信项目根（只读）
- 拦截 `builtins.open` 的写模式调用

### Peer 失败的具体原因

Peer 尝试的命令：
```bash
python3 -c "import sys; sys.path.insert(0, '/home/abug/timesfm/scripts')"
```

**被阻止原因**:
1. `python3 -c` 触发 sitecustomize 注入
2. `sys.path.insert(0, ...)` 修改 Python 路径 → 被视为 "runtime introspection"
3. `import monthly_backtest` 尝试加载项目模块 → sitecustomize 可能阻止对项目文件的读取

**核心矛盾**: Peer 需要 import 项目模块来运行评估，但 delete guard 将 import 视为安全威胁。

---

## 完整限制清单

| # | 限制来源 | 配置/代码 | 限制内容 | 合理性 |
|---|---------|----------|---------|:---:|
| 1 | `delete_guard.py` | `_PYTHON_DELETE_PATTERNS` | 阻止 rmtree/os.remove/write_text 等 | ✅ 合理 |
| 2 | `delete_guard.py` | `_PYTHON_SHELL_ESCAPE_PATTERNS` | 阻止 `__import__(`/`subprocess`/`os.system` | ✅ 合理 |
| 3 | `delete_guard.py` | `hard_introspection_escape` | 阻止 `exec(`/`eval(`/`sys.modules` | ✅ 合理 |
| 4 | `delete_guard.py` | `soft_introspection_escape` | 阻止 `globals()`/`locals()`/`dir(` | ⚠️ 过严 |
| 5 | `delete_guard.py` | `sitecustomize` | 拦截 Python 级文件 I/O | ✅ 合理 |
| 6 | `task.yaml` | `writable_roots: []` | Peer 零写入根 | ⚠️ 过严 |
| 7 | `task.yaml` | `protected_child_paths` | 保护 evaluations/roles/ 目录 | ✅ 合理 |
| 8 | `task.yaml` | `tools: []` | 无自定义工具 | ⚠️ 关键缺失 |
| 9 | `prompt_base.jinja2` | 路径引用 | 使用旧路径 `/root/timesFM_fu/` | ❌ 错误 |

---

## 解决方案

### 方案 1: 修复 prompt 模板（让 peer 用正确方式调用评估）

**根因**: Prompt 教 peer 用 `python3 -c "import ..."` 做探索，触发了 guard。

**修复**: 将评估调用改为直接执行脚本文件（不触发 introspection 检测）：

```bash
# ❌ 错误方式（触发 guard）
python3 -c "import sys; sys.path.insert(0, '...'); import monthly_backtest"

# ✅ 正确方式（直接执行脚本）
/home/abug/timesfm/.praxist-venv/bin/python \
    evaluations/fm_eval/run.py \
    --output-dir results/gen_1/peer0/test/diagnostic \
    --candidate candidate.json
```

**涉及文件**:
- `task_FM/prompt_base.jinja2` — 更新评估调用示例
- `task_FM/roles/peer_generalist/skill.md` — 更新评估入口说明

### 方案 2: 添加评估工具到 task.yaml（绕过 Bash guard）

给 peer 一个 first-class 的评估工具，不经过 Bash 解释：

```yaml
# task.yaml 中添加
tools:
  - name: run_evaluation
    description: "Run FM evaluation with candidate config"
    command: "{python} evaluations/fm_eval/run.py --output-dir {output_dir} --candidate {candidate_file}"
```

**优点**: 完全绕过 delete guard，peer 有专用工具
**缺点**: 需要 praxist 支持 tools 配置（需确认）

### 方案 3: 扩展 TRUSTED_PROJECT_ROOTS（允许读取项目文件）

通过环境变量告诉 sitecustomize 信任项目根目录：

```yaml
# task.yaml runtime_environment.env 中添加
env:
  PRAXIST_TRUSTED_PROJECT_EXTRA_ROOTS: "/home/abug/timesfm"
```

**优点**: 允许 peer 读取项目文件（import 模块），仍然阻止写入
**缺点**: 扩大了信任边界

### 方案 4: 放宽 writable_roots（允许写入 results/）

```yaml
# task.yaml 修改
runtime_environment:
  writable_roots: [results]  # 从 [] 改为 [results]
```

**优点**: peer 可以在 results/ 下写入候选文件和评估结果
**缺点**: 低风险，results/ 本就是临时输出目录

### 方案 5: 修复 prompt 中的绝对路径

当前 prompt 使用旧路径 `/root/timesFM_fu/`，需要更新为当前环境路径。

---

## 推荐执行顺序

| 优先级 | 方案 | 工作量 | 风险 |
|:---:|------|:---:|:---:|
| 1 | 方案 1: 修复 prompt 模板 | S | 低 |
| 2 | 方案 4: 放宽 writable_roots | S | 低 |
| 3 | 方案 3: 扩展 trusted roots | S | 中 |
| 4 | 方案 5: 修复绝对路径 | S | 低 |
| 5 | 方案 2: 添加评估工具 | M | 需确认 praxist 支持 |

**预计总时间**: 30 分钟

---

## 验证方法

修复后，peer 应能成功执行：
```bash
# 写入候选文件
echo '{"symbol":"rb","cov_override":"rsi_state","max_points":3,"stage":"diagnostic"}' \
    > candidate.json

# 运行评估（不触发 guard）
/home/abug/timesfm/.praxist-venv/bin/python \
    evaluations/fm_eval/run.py \
    --output-dir results/test/ \
    --candidate candidate.json

# 预期输出: evaluation_summary.json 包含 status: "ok"
```
