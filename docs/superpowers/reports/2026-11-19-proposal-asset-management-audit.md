# FM_a 提案资产管理审计报告

> **日期**：2026-11-19  
> **审计范围**：`task_FM/experiments/`（提案文件）、`task_FM/config/aligned_verdicts.jsonl`（裁决注册表）、基线资产、预筛资产  
> **审计时 commit**：`7a5877d`  
> **审计触发**：全工作区 git 梳理 + FM_a 备份同步后的资产盘点  

---

## 〇、项目背景

### 0.1 FM_a 是什么

FM_a 是一个**期货价格方向预测研究系统**，部署在 WSL2 Ubuntu-22.04（`/home/abug/timesfm`）。它的核心任务是：对 24 个中国期货品种，用 **TimesFM 3.0**（Google 时间序列基础模型）做 walk-forward 1 小时级联预测，并通过统计检验判断每个品种的"可预测性"是否达到科学显著性标准。

FM_a 隶属于 FlyBuddy 工作区，是 **FM（期货预测）系列**的生产版本。上游模型库 `shared/timesfm/` 提供 TimesFM 3.0 权重，FM_a 在其上构建了完整的**两阶段级联预测管线**：

| 阶段 | 模块 | 职责 |
|------|------|------|
| **Stage 1** | `cascade/daily_model.py` | 日线级 TimesFM 3.0 预测 22 日走势，提取 horizon_slope 特征 |
| **Stage 2** | `cascade/hourly_model.py` | 以日线斜率 + 协变量（CCL/OI/RSI 等）做 1H 级联预测 |

**数据流**：TqSdk（CTP 期货行情客户端）→ SQLite（每品种独立库）→ 技术指标计算 → TimesFM 预测 → 统计评估 → 裁决落库

### 0.2 三环架构（Praxist 集成）

2026 年 9 月起，FM_a 集成了 **Praxist 0.5.0**（Sapient Intelligence 的多 Agent 研究控制平面），构建了**三环自主探索架构**：

```
监督环 (scripts/praxist_supervisor.py)       0 token，纯 Python 调度
   ├─ 快环 (praxist start --task-path task_FM)  烧 LLM token，~1.5h/run
   │    └─ 2 个 peer agent（exploit + falsifier）并行产出协变量假设提案
   └─ 慢环 (scripts/aligned_slow_loop.py)       0 token，纯 CPU，唯一验证器
        └─ 加载 TimesFM 做 walk-forward 基线回测，输出 dir_acc / DM 检验 / FDR
```

**三环协作机制**：

1. **快环（Peer Agent）**：每轮 run 产出若干结构化提案（`fm.hypothesis_proposal.v1` schema），每个提案包含一个协变量假设（如"加入 NVI 指标可提升铁矿石预测"）+ 机制说明（≥40 字）
2. **监督环（Harvest）**：每 cycle 扫描全部 run 目录的提案，经过 20+ 道质量门（去重/死族/机制长度/失败增量等），合格者入队到慢环
3. **慢环（Aligned Slow Loop）**：逐个评估入队提案——用 TimesFM 做带/不带该协变量的 walk-forward 回测对比，输出 `dir_acc`（方向准确率）、DM 检验 p 值、BH-FDR 校正，最终判定 `gate_pass=True/False`

**目标品种**：24 个中国期货品种（m/ss/sr/cj/jd/lh/eg/rb/i/p/y/cf/bu/fu/ta/ma/fg/ur/px/oi/sh/sp/ao/jm），覆盖农产品/能源/金属/金融四大板块。

### 0.3 项目目标

FM_a 的终极目标是回答一个问题：**哪些期货品种的价格方向在统计意义上"可预测"？**

成功条件（`scripts/praxist_goal.yaml`）：`all_symbols_pass_phase1`——所有 24 个品种都至少有一个协变量变体通过了严格的统计检验门槛：

| 硬门 | 值 | 含义 |
|------|-----|------|
| n ≥ 350 | 最少 350 个 walk-forward 预测点 | 统计功效保障 |
| n_eff ≥ 50 | Bartlett 有效样本 ≥ 50 | 自相关校正后仍有效 |
| dir_acc ≥ effective_min | max(0.50, min(0.52, baseline_dir_acc)) | 方向准确率超过动态门槛 |
| DM p < 0.05 | Diebold-Mariano 检验显著 | 优于无协变量基线 |
| BH-FDR pass | Benjamini-Hochberg 多重校正通过 | 控制假发现率 |

预算上限：`max_cycles=2000`，`cpu_hours=2000`，`deadline=2028-10-02`。

### 0.4 技术背景

**TimesFM 3.0**：Google Research 的时间序列基础模型（`google/timesfm-3.0-200m-pytorch`），2 亿参数 Transformer，在大规模时间序列上预训练。FM_a 用其做 zero-shot 预测，再通过协变量增强。本地权重 ~883 MB，CPU-only 推理（无 GPU，7.7 GiB RAM）。

**Praxist 0.5.0**：多 Agent 研究控制平面（[论文](https://arxiv.org/abs/2608.25955)），提供 peer session、代际编排、证据保留。FM_a 只用它的快环（peer 产出提案），慢环验证在 Praxist 外部。

**Laya System-1 预筛**：2026-10-17 从 TypeSafe Jev 迁移至 Laya（HTTP POST，模型 `laya-rl-agent`），对 peer 提案做三问预筛（机制可信度/新颖度/预期效果），软建议模式（不阻断慢环）。

**协议指纹（v4 `f02b2a43`）**：七组件哈希，确保裁决的可复现性——数据窗口、模型版本、评估器参数、协变量池等全部钉死。指纹不同 = 裁决不可比。

---

## 一、本次审计的缘由

### 1.1 直接触发

2026-11-19 全工作区 git 梳理（17 个仓库扫描 + 14 个 commit/push），FM_a 备份同步时做了 rebase（44 commits，1 处冲突解决）。同步完成后顺带检查了 CodeGraph 索引状态，发现索引停留在 2026-10-05（45 天前，311 commits 未索引），触发全量重建。重建后进一步检查了提案资产的磁盘占用和健康度。

### 1.2 根本原因

**提案资产自 2026-09 项目启动以来从未清理过**。三环系统持续运行 254 个 cycle，产出 683 个 run、11,952 个提案文件，`task_FM/experiments/` 累积到 **4.9 GB**。没有自动清理机制，也没有定期审计。

### 1.3 审计目标

1. 摸清提案资产全貌（数量、质量、磁盘占用）
2. 识别卫生问题（MISSING fingerprint、无 prescreen metadata）
3. 制定清洗规范（配套 spec 文档），将磁盘从 4.9 GB 降至 ~2 GB
4. 建立长期清理策略，防止再次堆积

---

## 二、资产全景

| 资产类别 | 数量 | 磁盘占用 | 说明 |
|---------|------|---------|------|
| **快环 run 目录** | 683 个 run | **4.9 GB** | 2026-09 至今 |
| **提案文件** | 11,952 个 JSON | 含在上述 4.9G 中 | 每 run 约 17 个 |
| **Prescreen 文件** | 2,979 个 `.prescreen.json` | 含在上述 4.9G 中 | 100% error/degraded |
| **慢环已裁决** | 2,070 条（done 队列） | — | 历史累计 |
| **裁决注册表** | 251 条 | 约 200 KB | 含 191 个唯一 variant_id |
| **基线文件** | 24 品种 x 588 点 = 14,112 点 | ~144 KB | 全部 v4 指纹 |
| **预注册** | 2 条（jd=1199, sr=986） | — | 确认样本 |
| **协变量积压** | 23 条 | — | 新想法待实现 |

---

## 三、裁决质量分析

### 3.1 状态分布

| 状态 | 数量 | 占比 | 含义 |
|------|------|------|------|
| ok | 185 | 73.7% | 正常评估完成 |
| insufficient_data | 44 | 17.5% | 数据不足（jd 22 + sr 22） |
| timeout | 22 | 8.8% | 慢环评估超时（jd 11 + sr 11） |

**发现**：`insufficient_data` 和 `timeout` 全部集中在 **jd**（鸡蛋）和 **sr**（白糖）——这两个品种的预注册样本量最大（1199/986），慢环 `aligned_max_points=600` 限制导致评估窗口不足。这是预注册设计（大样本保障统计功效）与慢环实现（固定 600 点上限）之间的 gap。

### 3.2 门禁通过率

| 指标 | 值 |
|------|-----|
| gate_pass=True | 96 条（38.2%） |
| gate_pass=False | 155 条（61.8%） |

**gate_pass 品种分布（16/24 品种有通过）：**

| 品种 | pass 数 | 品种 | pass 数 |
|------|---------|------|---------|
| i（铁矿石） | 18 | cj（红枣） | 18 |
| ur（尿素） | 10 | ao | 7 |
| ta（PTA） | 7 | sp（纸浆） | 6 |
| ss（不锈钢） | 6 | jm（焦煤） | 5 |
| y（豆油） | 5 | sh（烧碱） | 4 |
| fg（玻璃） | 2 | p（棕榈油） | 2 |
| lh（生猪） | 2 | m（豆粕） | 2 |
| px（对二甲苯） | 1 | sr（白糖） | 1 |

**8 个品种零通过**：bu、cf、eg、fu、jd、ma、oi、rb。这些品种的 dir_acc 始终未达到 effective_min 门槛，说明现有协变量池对它们的预测力不足。

### 3.3 预测精度分布

| 统计量 | baseline_dir_acc |
|--------|-----------------|
| 样本数 | 229（仅 v4 指纹条目） |
| 最小值 | 0.3656 |
| 最大值 | 0.5918 |
| 中位数 | **0.4915** |
| 均值 | 0.4879 |

**发现**：均值接近硬币率（0.5），说明大部分裁决处于边界附近。`effective_min` 动态门槛（0.50~0.52）设计合理——既不过松（让噪音通过）也不过严（扼杀微弱信号）。

### 3.4 协议指纹一致性

| 指纹 | 数量 | 占比 |
|------|------|------|
| v4 `f02b2a43` | 229 | 91.2% |
| **MISSING** | 22 | 8.8% |

**发现**：22 条 MISSING 条目对应全部 22 条 `timeout` 裁决——慢环评估超时导致 `evaluator.build_summary()` 未执行，`protocol_fingerprint` 未写入。这些条目不影响运行但属于卫生问题：它们占据注册表空间却无法参与后续的去重和比较。

### 3.5 Prescreen 覆盖

| 指标 | 数量 |
|------|------|
| 有 prescreen metadata | 176（70.1%） |
| 无 prescreen metadata | 75（29.9%） |

无 metadata 的 75 条原因：Laya 服务不可用时产生（10 月曾有长时间宕机）；2026-10-17 TypeSafe→Laya 迁移前的遗留（旧裁决未回填 prescreen）。

---

## 四、磁盘健康度

| 路径 | 占用 | 评估 |
|------|------|------|
| `task_FM/experiments/` | **4.9 GB** | 偏大 |
| 单 run 平均 | ~7.2 MB | 正常 |
| 最大单 run | 22 MB | 正常 |
| `task_FM/config/baseline_*` | ~144 KB | 健康 |
| `aligned_verdicts.jsonl` | ~200 KB | 健康 |

**4.9 GB 的 experiments 是主要磁盘消耗**。683 个 run x 7.2 MB/run 约等于 4.9 GB，构成：

- 提案文件（JSON）：~11,952 个，每个 1-5 KB
- Prescreen 文件（`.prescreen.json`）：~2,979 个，每个 < 1 KB
- Run 日志（`.log`）：每个 run ~1-2 MB
- Praxist 中间产物（checkpoint、evidence）：每 run ~3-5 MB

---

## 五、收割效率分析

```
快环产出提案 11,952 个（683 run x ~17 提案/run）
  | harvest 质量门过滤（20+ 道门）
  | 拒绝原因：dedup / dead_family / no_failure_delta / mechanism_too_short /
  |           symbol_dead / cov_archived / sector_blocked / quality_below_threshold / ...
慢环入队 = 2,070 个（17.3% 通过 harvest）
  | 慢环评估（TimesFM walk-forward 基线回测 + DM 检验 + BH-FDR）
裁决注册 251 条（2.1% 完成评估并写入注册表）
  | gate 判据（dir_acc + n_eff + DM + FDR）
gate_pass=True 96 条（0.8% 最终确认）
```

**全链路转化率**：11,952 → 96 = **0.8%**。

这是**设计意图**——三环架构的核心价值就在于严格筛选。快环大量探索（peer 发散思维），慢环严格验证（统计显著性）。0.8% 的通过率说明：

- 快环的去重门有效（大量重复提案被过滤）
- 慢环的评估门有效（大部分提案的协变量确实不显著）
- 最终确认的 96 条变体是有统计支撑的

---

## 六、风险与问题

| # | 级别 | 问题 | 影响 |
|---|------|------|------|
| R1 | **HIGH** | experiments 4.9 GB 持续增长（~20 MB/cycle），无清理机制 | 磁盘压力，WSL 虚拟磁盘膨胀 |
| R2 | MEDIUM | 22 条 timeout 裁决 MISSING fingerprint | 注册表卫生，影响去重准确性 |
| R3 | MEDIUM | 75 条裁决无 prescreen metadata | 可审计性降低，无法回溯预筛判断 |
| R4 | LOW | jd/sr 各 33 条 insufficient_data/timeout | 预注册样本（1199/986）vs max_points（600）gap 过大 |
| R5 | LOW | Laya 服务刚恢复（2026-11-19），prescreen 100% degraded 历史文件未重评 | 不影响运行，但新 cycle 的 prescreen 将恢复正常 |

---

## 七、建议

1. **执行提案资产清洗**（见配套 spec `docs/superpowers/specs/2026-11-19-proposal-asset-cleanup-spec.md`）
   - P0：归档旧 run（保留最近 10 个），释放 ~3 GB
   - P1：清理 prescreen 文件（2,979 个），释放 ~200 MB
   - P2：标记 22 条 MISSING fingerprint 裁决
   - P3：补充 75 条无 prescreen metadata 裁决的标记
   - P4：建立长期自动清理策略

2. **修复 jd/sr 的 max_points gap**：考虑将 `aligned_max_points` 从 600 提升至 800-1000，或为这两个品种设独立上限

3. **建立定期审计机制**：每月或每 100 cycle 跑一次资产盘点（可自动化为诊断脚本的一部分）

4. **监控 Laya 服务健康**：预筛服务不可达时应有告警（当前是静默降级，设计合理但缺乏可观测性）
