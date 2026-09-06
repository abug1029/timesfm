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

## 待用户确认

1. `.env.praxist` 中的 `ANTHROPIC_API_KEY` 是否仍有效（已从 yaml 迁出）。
2. 是否还需要单独的 `VOLCENGINE_API_KEY`（视网关要求）。
3. 是否启用 GPU（非空 `CUDA_VISIBLE_DEVICES`）。
