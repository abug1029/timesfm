# PRAXIST LLM / TimesFM 环境变量（FM_a）

本文件只列**变量名与用途**，不含密钥明文。密钥放在仓库根目录 `.env.praxist`（已 gitignore）。

## 启动前

```bash
cd /workspace/repos/timesfm-abug1029
set -a
source .env.praxist
set +a
```

`task_FM/task.yaml` 的 `runtime_environment.env.ANTHROPIC_API_KEY` 应为空；由进程环境注入。

## 必需 / 常用

| 变量 | 用途 | 备注 |
|------|------|------|
| `ANTHROPIC_BASE_URL` | Anthropic 兼容网关 | 当前任务用 Volcengine Ark coding endpoint |
| `ANTHROPIC_API_KEY` | 网关鉴权 | **仅** `.env.praxist`；勿写入 yaml / 报告 |
| `ANTHROPIC_AUTH_TOKEN` | 备选鉴权名 | `praxist_supervisor._praxist_env` 会映射到 `ANTHROPIC_API_KEY` |
| `VOLCENGINE_API_KEY` | Volc 直连时 | 若网关另要 Volc key 再填；否则可空 |
| `FM_TIMESFM_MODEL_PATH` | TimesFM 本地权重根 | 默认 `/workspace/repos/timesfm-abug1029/models/timesfm-2.5-200m-pytorch` |
| `TIMESFM_WEIGHTS_DIR` | 指纹 / 兼容别名 | 可与上者同路径 |
| `PRAXIST_BIN` | praxist 可执行文件 | 默认 `/home/box/.praxist-venv/bin/praxist` |
| `CUDA_VISIBLE_DEVICES` | 设备 | task.yaml 默认 `""`（CPU） |

## 可选

| 变量 | 用途 |
|------|------|
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | 若改用 OpenAI 兼容供应商 |
| `TIMESFM_MODEL_PATH` | 与 `FM_TIMESFM_MODEL_PATH` 兼容别名 |

## 隔离说明

- **预测岗** `timesFM_fu`：自有权重 / HF cache。
- **PRAXIST / 本仓**：必须用 `models/timesfm-2.5-200m-pytorch` 本地副本；`get_timesfm_model_path()` 优先 env 与本地目录，避免 runtime 解析 bare HF id 到共享 cache。


## 429 Failover（DashScope）

主用仍是 Volcengine Ark（`ANTHROPIC_*` / `PRIMARY_*`）。当 supervisor 在快环中检测到 Ark **429 / 5h quota** 且已配置 failover 时：

1. `stop` 当前 run
2. 将 state `llm_provider`（兼写 `llm_route`）设为 `failover`
3. `_praxist_env(failover)` 用 `FAILOVER_*` / `ANTHROPIC_FAILOVER_*` 覆盖 `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY`
4. 以 `FAILOVER_MODEL` / `ANTHROPIC_FAILOVER_MODEL`（默认 `qwen3.7-plus`）带 **`--model` argv** 做 `resume`（或无 run_dir 时 `start`）——**有 failover 时不只 `wait_quota`**
5. 同时写入 env `PRAXIST_MODEL` / `MODEL`（praxist `start` 也会从 `PRAXIST_MODEL` 解析模型）
6. 若 failover resume 失败 → `paused_429=true`，等待 Ark reset
7. **切回 Ark**：下一次 **新** `run_started`（Ark 配额窗 OK）默认 `llm_provider=primary`；或手动把 `data/cache/supervisor_state.json` 的 `llm_provider`/`llm_route` 设为 `primary` 后 source `.env.praxist` 再 resume/start

| 变量 | 用途 |
|------|------|
| `PRIMARY_ANTHROPIC_BASE_URL` | Ark 主用网关（恢复时写回） |
| `PRIMARY_ANTHROPIC_API_KEY` | Ark 主用 key |
| `PRIMARY_MODEL` | 主用模型（默认 `claude-opus-4-7`；经 `--model` + `PRAXIST_MODEL`） |
| `FAILOVER_ANTHROPIC_BASE_URL` / `ANTHROPIC_FAILOVER_BASE_URL` | DashScope：`https://coding.dashscope.aliyuncs.com/apps/anthropic` |
| `FAILOVER_ANTHROPIC_API_KEY` / `ANTHROPIC_FAILOVER_API_KEY` | DashScope key（仅 `.env.praxist`；备份 `~/.config/dashscope-coding-key` chmod 600） |
| `FAILOVER_MODEL` / `ANTHROPIC_FAILOVER_MODEL` | 备用模型，默认 `qwen3.7-plus` |

### 模型如何传到 praxist

- **今日主用**：`claude-opus-4-7`（`PRIMARY_MODEL`；praxist 默认亦为此）
- **Failover**：`qwen3.7-plus`
- **接线优先序**：supervisor start/resume **argv `--model <name>`**（明确覆盖）→ 同时设 env `PRAXIST_MODEL`（praxist CLI 也会读）→ 不改 `task.yaml`
- **BASE_URL**：勿在 `task_FM/task.yaml` `runtime_environment.env` 写死；由 process env + `scripts/praxist_llm_env_hook.py`（`.pth` 安装）让 `anthropic_messages` 透传 `ANTHROPIC_BASE_URL`。重装 praxist 后跑 `scripts/install_praxist_llm_env_hook.py`。


### Praxist model_provider compatibility (DashScope)

Praxist `model_provider:anthropic_messages` validates `--model` against
`compatible_model_patterns` in its plugin manifest (default: only `claude-*`).
That is why failover with `FAILOVER_MODEL=qwen3.7-plus` failed:

`startup failed: model 'qwen3.7-plus' is not compatible with model_provider:anthropic_messages`

**Keep** `model_provider:anthropic_messages` (required by `agent_runtime:claude_sdk`).
**Keep** DashScope Anthropic endpoint + model id `qwen3.7-plus` (Coding Plan allowlist).
**Fix** by widening patterns via `scripts/install_praxist_llm_env_hook.py`
(patches site-packages `anthropic_messages/plugin.yaml` to also allow
`qwen*`, `kimi-*`, `glm-*`, `MiniMax-*`). Re-run the installer after any praxist reinstall.

**Resume identity:** Praxist refuses `resume` when `--model` changes
(e.g. `claude-opus-4-7` → `qwen3.7-plus`) or when task_project / task.yaml
hashes drift. Supervisor failover therefore **starts a fresh run** on DashScope
unless the existing run already used the failover model id.

密钥勿写入 yaml / 报告 / commit / chat。

## 待用户确认

1. `.env.praxist` 中的 `ANTHROPIC_API_KEY` 是否仍有效（已从 yaml 迁出）。
2. 是否还需要单独的 `VOLCENGINE_API_KEY`（视网关要求）。
3. 是否启用 GPU（非空 `CUDA_VISIBLE_DEVICES`）。
