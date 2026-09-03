# PRAXIST 整合方案 — FM_a (timesFM_fu)

**日期**: 2026-09-01  
**状态**: 方案稿（待人工批准后逐阶段执行）  
**输入材料**: 用户提供的 PRAXIST 适配分析 + 本机事实核查  
**仓库**: https://github.com/sapientinc/PRAXIST (5.8k★, Fair Source 1.0)

---

## 0. 结论

**引入 PRAXIST 本体作为候选搜索控制平面，但按阶段、带红线边界地引入；P0 概念移植先行，且 P0 独立有价值。**

原分析建议"概念移植优于系统引入"，其三大硬约束中有两条基于过时环境，现已失效：

| 原分析假设 | 当前实际 (2026-09-01 核查) | 影响 |
|---|---|---|
| 硬约束1: Windows 不支持，只能 WSL，生态在 Windows 侧 | **已于 2026-09-01 迁移 Linux** `/root/timesFM_fu`，CPython 3.12 独立 venv，TimesFM 2.5 权重已缓存，测试 502 通过。PRAXIST 测试环境恰为 Linux CPython 3.11/3.12 | **解除** |
| 硬约束3: CPU-only + 单写入者 JSONL → 并行度实质为 1，废掉核心优势 | 部分成立但需重新理解：PRAXIST 的并发在 **agent 端**（peers 是 LLM 探索，不占本机 CPU）；本机瓶颈只在评估器执行（串行队列）。并发探索能力保留，只是评估吞吐受限 | **降级为吞吐约束** |
| 硬约束2: 红线冲突（禁改 SCHEMES/cascade/data.config） | **仍然成立**。解法不是放宽红线，而是用 PRAXIST 的职责边界机制：peers 只在允许路径产候选，固化映射为"建议包 + 人工执行" | **成立，按 §3 适配** |

另有一条原分析未提的资源约束：**磁盘仅剩 8.4GB**（jax CUDA 全家桶 ~3GB 占用，TimesFM CPU 推理本不需要它），安装前应回收。

**预期管理**：Phase 13/15/B1 的裁决已表明瓶颈是弱信号天花板。PRAXIST 不创造信号——它加速**证伪**、保证**证据链完整性**（预注册/溯源/成熟度门），把"诊断好看→全量翻车"这类事故变成制度上不可能。这是它在本项目的真实价值，不是"必然找出 GREEN"。

---

## 1. 事实核查修正（相对用户输入材料）

- **"证据五分法"**：README 仅述三通道（incubator / frontier / Gems）+ 证据成熟度规则（evidence maturity rules）。五分法（canonical_state / validation_signal / derived_view / audit_snapshot / partial_output）可能来自更深文档，方案按 README 口径设计，机制等价。
- **B1 裁决（2026-09-01）**：磁盘上未找到记录（STATE.md 最后更新 2026-08-29，loop-run-log.md 无 B1）。**作为用户输入接受**，其教训（"诊断须加经济口径判据：诊断 PF 好看但全量 0/11 GREEN"）已吸收进 §2 契约设计，与 Phase 13/15 的 0 GREEN 结论同构。
- **许可证**：Fair Source 1.0 确认。年收入 <$1M 免费商用；**对外发布研究结果须保留 "Praxist by Sapient Intelligence" 署名**（内部使用无署名义务）。
- **运行方式**：CLI（`praxist status/stop/resume/doctor`）+ 代理技能（Codex/Claude Code takeover）。FM_a 环境 Claude Code 已在用，takeover 路径可行。

---

## 2. 任务包设计（FM_a 侧唯一需要新建的东西）

PRAXIST 要求任务项目自持评估器与契约。FM_a 已有的资产几乎全部对口：

| PRAXIST 契约要素 | FM_a 现状 | 动作 |
|---|---|---|
| 可运行项目 | cascade_predict.py 全链路（XReg 已装，2026-09-01 端到端验证通过） | 无 |
| 可度量目标 | PF / EV(扣滑点) / MaxDD / n≥350 / IC≥0.05，GREEN 判据成文 | 无 |
| 主指标+方向 | EV_after_slippage 为主、PF 为次（与 G004/Phase 11 裁决口径一致） | 写入契约文件 |
| 基线溯源 | `reports/backtest_registry.md`（141 实验）+ SCHEMES 当前固化 | 写入契约 |
| 证据成熟度规则 | **缺失**（B1 教训根源） | 新建预注册契约 |
| 代际关闭策略 | **缺失** | 新建 |
| 评估器 | `scripts/monthly_backtest.py` walk-forward（FM_a 所有，不动） | 无 |

**新建文件 `config/praxist_task.yaml`（草案要点）：**

```yaml
objective:
  primary: ev_after_slippage          # 扣滑点 EV，主指标
  secondary: profit_factor
constraints:
  min_samples: 350                    # n>=350
  min_ic: 0.05                        # IC>=0.05
  maxdd_caliber: cumprod_clamp        # cascade/evaluation_metrics.py 2026-08-21 修复后口径
  multiple_comparison: bonferroni     # 多重比较校正
  green_requires_full_walkforward: true   # 诊断 PF 不作数 (B1/Phase13/15 教训)
baseline_provenance: reports/backtest_registry.md
evidence_maturity:
  - stage: diagnostic                 # 诊断级: 短窗口, 只产 incubator 证据
    gate: none
  - stage: full_walkforward           # 只有全量 WF 通过才可成为 Gem 债选
    gate: [n>=350, ic>=0.05, ev>0]
generation_close_policy: sealed      # 代际关闭后晚到结果不重写裁决
write_paths:                          # peers 唯一可写区
  - scripts/praxist_ws/
  - reports/praxist/
```

---

## 3. 红线适配：职责边界映射

loop-constraints.md 红线不变，映射到 PRAXIST 职责边界：

| FM_a 红线 | PRAXIST 侧适配 |
|---|---|
| 禁自动修改 prediction_scheme.py / cascade/*.py / data/config.py | peers 只能在 `scripts/praxist_ws/` 产候选配置（JSON/YAML 实验定义）与假设文档 |
| 回测启动须用户批准 | 评估队列由人触发（每代开始时人工放行该代评估预算）；或一次性批准"每代 ≤N 次 full WF" |
| db/ 只增不删 | evaluator 是只读消费方，天然满足 |
| 固化（Gems）| **不等于**写 SCHEMES。Gem = "固化建议包"（证据包+建议 diff），由人执行并更新 loop-constraints 白名单外文件 |

### 资源适配

- **评估串行队列**：peers 并行提候选（agent 端，不占本机 CPU），评估按单写入者约束串行执行。每代评估预算需实测后定（P1 实测 `monthly_backtest.py` 单次全量 WF 时长）
- **内存 1.9GB**：TimesFM 推理峰值 ~1.5GB，评估期间不得并行其它重活；PRAXIST 控制平面本身轻量
- **磁盘**：安装 PRAXIST 前 `pip uninstall` 清掉 `nvidia-*` / `jax-cuda*`（TimesFM CPU 推理不需要，回收 ~3GB）
- **网络**：huggingface.co 直连通畅（hf-mirror 反而失败）

---

## 4. 分阶段实施

### P0 — 概念移植（0.5–1 天，**无论是否引入本体都执行**）

1. **预注册评估契约**（直接对应 B1/Phase13/15 教训）
   - `loop-constraints.md` 新增条款："任何诊断性回测启动前，先在任务文件中写死最终裁决口径（全量 WF、扣滑点 EV>0、IC≥0.05、多重比较校正），评估代码与口径同 commit 落盘"
   - 产物：`config/praxist_task.yaml` 骨架 + 各 Phase 任务文件模板
2. **canonical_state 语义化**
   - STATE.md 声明为唯一事实所有者（唯一事实所有者原则）
   - `reports/` 全部标注 derived_view，报告规则写明"冲突时以 STATE.md + 磁盘回测产物（JSONL/predictions.json）为准"
   - 解决 SH 滞后文档类事故的制度性解法
3. **Pareto 前沿展示**（若开新 Phase）
   - 候选按 PF/EV/MaxDD/n 做 Pareto 前沿展示
   - 强制每代议程含 1 个"与当前最优正交"的探索性假设（QD 门）

### P1 — 安装与任务包脚手架（0.5 天）

```bash
# 磁盘回收 (~3GB)
.venv/bin/pip uninstall -y $(.venv/bin/pip list --format=freeze | grep -iE 'nvidia|jax-cuda' | cut -d= -f1)
# 安装 praxist CLI (独立 venv, 与 FM_a .venv 隔离)
python3.12 -m venv /root/.praxist-venv
/root/.praxist-venv/bin/pip install praxist
praxist doctor
```

- 用数据最少的品种（SH 或 M）做 toy task：`praxist examples install` 脚手架 + `config/praxist_task.yaml`
- 验收：`praxist doctor` 全绿；toy task 可被 takeover 技能识别为 runnable

### P2 — 试运行 2–3 代（1–2 天）

- M 或 SH 单品种，代际预算封顶（如每代 ≤6 次评估）
- **验收标准（go/no-go）：**
  - 证据包包含：预注册口径、usage 记录（缺失时记 `usage_unknown` 而非静默置零）、代际关闭时间戳
  - 评估队列串行不爆内存（评估期 RSS <1.7GB）
  - peers 全程未写红线路径（用 git status 审计）
  - 每代产出 ≥1 个正交假设（QD 门生效）
- **No-go 判据**：证据包质量低于手工 Phase 流程，或控制平面自身维护成本 > 收益

### P3 — 正式启用（若 P2 通过）

- 用于下一轮协变量搜索（若开新 Phase；Phase 15b/Q1 后暂无既定 Phase）
- 固化仍人工：Gem → 建议包 → 人改 SCHEMES → monthly_backtest 复验
- 对外发布任何结果时保留署名义务

---

## 5. 不做 / 警惕

1. **不让 PRAXIST 直接改红线文件**——它只管编排和证据协议，SCHEMES/cascade 的人工确认语义不变
2. **不指望解决弱信号天花板**——Phase 13/15 的 0 GREEN 是信号存在性问题，PRAXIST 优化的是搜索纪律与证据链，不保证找到信号
3. **不引入 cron/常驻进程**——FM_a 是 Predict-then-Collect 策略，PRAXIST run 也按需启动，用 `praxist stop/resume` 管理，避免与采集窗口撞内存
4. **磁盘水位**：83% 已用，任何阶段安装新依赖前先查 `df -h`

---

## 6. 与现有文档的关系

- 本方案是**提案文档**（derived_view），不自动变更任何红线
- P0-1 若执行，预注册条款写入 `loop-constraints.md`（自定义规则区）
- P0-2 执行时 STATE.md 头部加"canonical_state 声明"；报告规则补 derived_view 标注规则
- 试运行产物放 `reports/praxist/`（新增目录，allowed paths）
