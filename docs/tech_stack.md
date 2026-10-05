# 技术栈与环境

> 依赖、运行环境、目录职责的集中说明。
> 上游：`requirements.txt`（2026-09-01 WSL 迁移时固化）
>
> 最后核实：2026-10-05，commit `ee01b56`。

---

## 1. 运行环境

| 项 | 值 |
|----|---|
| 宿主 | **WSL2 Ubuntu-22.04** |
| 仓库 | `/home/abug/timesfm`（**唯一权威源**，Windows 侧无副本） |
| Python | **3.11.15**（仓内 `.venv`） |
| 内存 | 约 7.7 GiB（Swap 以 `free -h` 为准） |
| CPU | 8 vCPU |
| remote | `github.com/abug1029/timesfm` |

```bash
cd /home/abug/timesfm
source .venv/bin/activate
```

> ⚠️ **Windows 侧的 `D:\FlyBuddy\timesfm\` 与 `D:\FlyBuddy\FM_a\` 均已不存在**（2026-09-29 核实）。
> 一切读写走 WSL 仓。

---

## 2. 依赖（`requirements.txt`）

| 包 | 版本约束 | 为什么 |
|----|---------|-------|
| `timesfm` | ≥ 3.0.0 | 时序基础模型（**仅慢环加载**） |
| `torch` | ≥ 2.0 | **CPU 版**（本机无 GPU） |
| `pandas` | ≥ 2.0 | 见下方说明 |
| `numpy` | **< 3** | 兼容性 |
| `pyarrow` | — | parquet 缓存 |

> ⚠️ **`requirements.txt` 的 pandas 注释已过期**（2026-10-05 核实）：注释称「必须 <3，
> 因 `cascade/` 用了 pandas 3 已移除的 `'H'` 频率别名」，但——
> ① `requirements.txt` 的**约束行并没有 `<3` 上界**（只有 `>=2.0`）；
> ② 代码实际用的是**小写** `freq='h'`（`cascade/features.py`）与 `freq='1h'`
> （`cascade/data_validator.py`），**没有 `'H'`**；
> ③ 实测安装版本为 **pandas 3.0.5**。
>
> 即该约束**当前不成立**。若将来真要限制 `<3`，需先修正注释与约束行使其一致——
> 不要仅凭这条过期注释就拒绝升级。

**安装 torch（CPU）**：
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 未安装的

`pyarrow` / `fastparquet` 曾导致 LGBM 路径不可用 —— **LGBM 已于 2026-09-30 归档**
（`cascade/archive/2026-09-30-a2-retired/lgbm_features.py`），不再是活跃路径。

### 外部服务

| 服务 | 用途 | 变量 |
|------|------|------|
| 文华财经 TqSdk | 行情采集 | `.env` |
| TypeSafe System One (Jev) | 协变量预筛（软建议） | `TYPESAFE_API_KEY`（在 `.env.praxist`） |
| LLM 主路 | peer 假设生成 | Ark |
| LLM 备路 | 429 failover | DashScope（Anthropic 兼容端点） |

> 🔒 **密钥只进 `.env.praxist` / `.env`**，绝不写进 `task_FM/task.yaml` 或可提交文件。
> 2026-09-06 曾发生 API key 泄露（commit `d236671` 清理）。

### 不可修改的东西

| 对象 | 原因 |
|------|------|
| **`.venv` 里的 Praxist 源码** | 升级会丢；用 `task.yaml` 的 `praxist_plugins` 声明拓扑 / roles / audit |
| **`third_party/timesfm-3.0-official`** | submodule，官方代码 |
| **`cascade/horizon_fill.py` 的分类逻辑** | horizon 契约**唯一家** |

---

## 3. 目录职责

| 目录 | 职责 |
|------|------|
| `cascade/` | 级联预测：日线/1H 模型、特征、协变量族、horizon 契约、family 状态机、统计检验 |
| `config/` | 生产 SCHEMES、品种配置、回测参数 |
| `data/` | 数据管理、配置常量、防护 |
| `scripts/` | CLI 入口、supervisor、回测、采集 |
| `task_FM/` | **Praxist 任务包**（科学合同 + 运行产物；手写合同见其 `AGENTS.md`） |
| `tests/` | pytest |
| `db/` | 每品种一个 SQLite |
| `docs/` | 本手册（L0/L1）+ `superpowers/` 证据层（L2） |
| `data/assets/` | **运行产物归档**（append-only） |
| `data/archive/` | 历史封存包 |

> **规模会漂移，不写死数字。** 实时查：
> ```bash
> ls <dir>/*.py | wc -l                        # 某目录 py 数
> ls db/futures_*.db | wc -l                  # 数据库数
> find docs -name '*.md' -not -path '*/archive/*' | wc -l   # 在用文档数
> du -sh data/assets data/archive             # 产物体积
> ```

各目录另有 `AGENTS.md` 路由（`cascade/` · `config/` · `data/` · `scripts/` · `tests/` · `task_FM/` · `docs/`）。

---

## 4. 关键入口命令

```bash
# 生产级联预测
python scripts/cascade_predict.py ss

# 主观交易领航员（盘中入口）
python scripts/copilot.py ss fu

# 数据采集
python scripts/data_management.py --1h          # 单品种（如 --1h ss）
python scripts/data_management.py --1h --daily   # 全品种

# 三环（生产监督环）
scripts/start_supervisor.sh          # canonical launcher
# ⚠️ 没有 stop_supervisor.sh —— 停法是 kill -TERM，再等 supervisor_stopped 事件
#    （详见 runbook_praxist_three_loop.md「启动 / 停止」）

# 月度回测
python scripts/monthly_backtest.py

# 单测
python -m pytest tests/ -q
```

> 完整启停与故障速查见 [runbook_praxist_three_loop.md](./runbook_praxist_three_loop.md)
> 与 [runbook.md](./runbook.md)。

---

## 5. 模型权重

| 路径 | 说明 |
|------|------|
| `models/timesfm-3.0-pytorch` | HF hub id `google/timesfm-3.0-pytorch` |
| `models/backup-2.5-200m-pytorch/` | **回退路径**（2.5 权重保留） |

解析入口：`data/config.py::get_timesfm_model_path`（支持 `FM_MODEL_DIR` 等环境变量覆盖）。

**预测岗与 PRAXIST 权重隔离**——两者不可共用。

---

## 6. 测试与质量门

```bash
python -m pytest tests/ -q
```

`agentic-qe` 钩子在同一子项目累计改满 5 个源文件时提醒跑该项目的 pytest。

---

## 7. 已知环境约束

| 约束 | 影响 |
|------|------|
| 本机**无 GPU** | TimesFM 只能 CPU 推理，慢环成本受限 |
| 内存 ~7.7 GiB | TimesFM **仅慢环加载**，peer 零 TimesFM（方案 A） |
| 并发受 `flock` 限制 | eval 同时最多 1–2 个 |
