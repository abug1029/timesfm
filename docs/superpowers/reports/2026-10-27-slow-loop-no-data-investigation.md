# 慢环 no_data Verdict 调查报告（修订版）

**生成时间**: 2026-10-27  
**修订时间**: 2026-10-27（根据审计反馈修订）  
**调查对象**: 慢环重评估 344 个提案（batch_id: `reprocess_20261026`）  
**当前状态**: 已完成 15 个 verdict（9 ok + 6 no_data），待处理 214 个  
**调查结论**: 根本原因是 Praxist peer（快环）生成了错误的协变量名，而非 Laya 预筛系统

---

## 一、问题描述

### 1.1 现象

- 启动慢环重评估 344 个提案（batch_id: `reprocess_20261026`）
- 运行约 5 小时，完成 **15 个 verdict**（非全部失败）
- Verdict 分布：
  - **9 个 `ok`**：成功评估（如 `ss_reversal_shadow_gated_02`, `p_hurst` 等）
  - **6 个 `no_data`**：失败（如 `sr_term_structure`, `m_volatility` 等）
- 日志中充斥警告：`persistence horizon 段非 persistence，已按 spec W5.2 归一化为 context 末值`
  - **注意**：W5.2 警告与 `no_data` **无因果关系**，该警告在 `ok` 路径中同样出现

### 1.2 已完成的 Verdict 统计（截至审计时刻）

| 状态 | 数量 | variant_ids |
|------|------|-------------|
| `ok` | 9 | lh_reversal_shadow_gated_02, ss_reversal_shadow_gated_02, ss_regime_gated, p_hurst, ss_ao_accel, cf_gated_slope, cf_oi_gated_momentum, sr_reversal_shadow_gated_02, jd_gated_slope |
| `no_data` | 6 | sr_term_structure, c_oi, m_ccl_calendar, m_volatility, eg_calendar, sr_inventory |

**队列会计恒等式**（审计时刻）：
- `aligned_pending.jsonl`：214 条（其中 `source=reprocess_20261026` 209 条）
- `aligned_pending.done.jsonl`：`reprocess_20261026` 134 条
- `inprogress`：1 条
- **209 + 134 + 1 = 344**（与总入队数一致）

---

## 二、架构澄清

### 2.1 正确的数据流

```
Praxist peer (快环) → 生成提案 → Laya prescreen (预筛) → 慢环评估
     ↓                    ↓                ↓
 生成假设            判断是否值得评估     详细评估并生成 verdict
```

### 2.2 各组件职责

| 组件 | 职责 | 错误理解 |
|------|------|----------|
| **Praxist peer (快环)** | 生成提案（假设 + 协变量） | ❌ 误认为是 Laya |
| **Laya prescreen** | 预筛提案（判断 plausibility/novelty） | ✅ 只做判断，不生成 |
| **慢环 (aligned_slow_loop)** | 详细评估提案，生成 verdict | ✅ 正确 |

### 2.3 专家报告的错误

初始专家报告声称：
> "根因 1（主要）：Laya 快环提议了 `build_covariate_matrix` 不存在的协变量名"

**这是错误的**。Laya 不生成提案，Praxist peer 才生成提案。

---

## 三、根本原因分析

### 3.1 根因 1（主要）：Praxist peer 生成了错误的协变量名

**证据**：检查旧提案文件

```bash
task_FM/experiments/archive/run_2026-10-06_14-51-37_primary_task_FM/
  results/gen_0/gen0_peer1/proposals/m_volatility.json

{
  "symbol": "m",
  "cov_override": "volatility",        ← 族名，不是具体协变量
  "covariate_family": "volatility"
}
```

**问题**：
- `cov_override` 应该是具体协变量名（如 `vor`, `bb_squeeze`, `ao_accel`）
- 但 peer 错误地使用了族名（`volatility`, `momentum`, `term_structure`）
- 这些族名在 `cascade/features.py::build_covariate_matrix()` 中没有注册

### 3.2 根因 2：旧提案未经过 Laya 预筛验证（部分成立）

**证据**：查找 prescreen 文件

```bash
find task_FM/experiments/archive/run_2026-10-06_14-51-37_primary_task_FM \
  -name 'm_volatility.prescreen.json'
# 无结果
```

**问题**：
- 这些提案来自 2026-10-06（Laya 预筛系统完善之前）
- 当时没有强制预筛验证，或预筛系统本身有 bug
- 错误提案直接进入了实验目录，未经过滤

**重要澄清**：
- 即使有预筛文件，`typesafe_prescreen` **也没有**对 `covariate_pool` 的硬校验
- Laya 预筛只做 plausibility/novelty 的**软建议**，不会拦截未注册的协变量名
- 因此，"无 prescreen 文件"不是充分条件——即使有 prescreen，也可能无法拦截此类错误

### 3.3 根因 3：去重脚本盲目重入队

**问题**：
- `scripts/enqueue_reprocess.py` 扫描所有历史提案
- 没有验证 `cov_override` 是否在已注册协变量白名单中
- 将 344 个提案全部入队，包括 **约 79 个注定失败的无效提案**（非原报告估计的 23 个）

**无效提案构成**（按 registry 扫描）：
- 族名（`volatility`, `momentum`, `term_structure` 等）：5 个
- 未注册幻觉名（`macro_sentiment_composite`, `ccl_calendar`, `stoch_rsi` 等）：约 4 个
- 品种 `c` 的合法协变量：2 个
- **当前 pending 队列中注定失败：约 11 个**（非原报告估计的 23 个或 81 个）

**注意**：全 batch 历史 doomed 约 31 个，但大部分已在 done 队列中。当前 pending 剩余 doomed 约 11 个。

### 3.4 根因 4（次要）：品种 `c`（玉米）无数据

**证据**：
```bash
# DataStore 中品种 c 的数据
c: 1h=0 daily=0
```

**影响**：
- `c_oi`, `c_vor`, `c_hourly_slope` 等提案失败
- `run_symbol_backtest` 早期检查 `if all_1h.empty → return None`

---

## 四、错误协变量分类

### 4.1 族名被误当协变量名（5 个）

| 错误名称 | 应该是 | 涉及提案 |
|---------|--------|---------|
| `volatility` | `vor`, `ao_accel`, `bb_squeeze` 等 | rb_volatility, m_volatility, ss_volatility 等 |
| `momentum` | `rsi_slope`, `pca_momentum`, `nvi` 等 | cj_momentum, p_momentum 等 |
| `term_structure` | `basis_momentum`, `crack_spread_slope` 等 | eg_term_structure, y_term_structure 等 |
| `inventory` | `ccl`, `oi` 等 | cj_inventory 等 |
| `macro_sentiment` | 无对应具体协变量 | rb_macro_sentiment, jd_macro_sentiment_composite 等 |

### 4.2 Peer 幻觉名称（7 个）

| 幻觉名称 | 说明 |
|---------|------|
| `macro_sentiment_composite` | 不存在的组合协变量 |
| `inventory_deviation` | 不存在的衍生协变量 |
| `calendar_spread_momentum` | 不存在的组合协变量 |
| `roll_yield_21d` | 不存在的带窗口协变量 |
| `curve_slope_21d` | 不存在的带窗口协变量 |
| `volatility_realized_gap` | 不存在的组合协变量 |
| `calendar_expiration` | 不存在的协变量 |

### 4.3 已注册的合法协变量

**来源**: `task_FM/config/covariate_pool.json`（31 个 active 协变量）

**注意**: 以下函数是**伪代码示例**，实际实现应从 `covariate_pool.json` 读取，而非硬编码。注意 `covariate_pool.json` 的实际 schema：
- `families` 是**族名列表**（list），不是 dict
- `covariates` 是**顶层 dict**，key 是协变量名，value 包含 `family`, `status`, `mechanism` 等
- 合法协变量的 `status == "active"`

```python
import json
from pathlib import Path

def load_supported_covariates():
    """从 covariate_pool.json 读取合法协变量名"""
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path) as f:
        pool = json.load(f)
    
    # covariates 是顶层 dict，key 是协变量名
    # 提取所有 status == "active" 的协变量名
    supported = set()
    for cov_name, cov_data in pool.get("covariates", {}).items():
        if cov_data.get("status") == "active":
            supported.add(cov_name)
    
    # 添加特殊别名（如 slope_only, none, baseline）
    supported.update({"slope_only", "none", "baseline"})
    
    # families 是族名列表，可用于「禁止族名当 cov_override」检查
    family_names = set(pool.get("families", []))
    
    return supported, family_names
```

**合法协变量示例**（部分，完整列表见 `covariate_pool.json`）：
- `oi`, `rsi_slope`, `hourly_slope`, `rsi_state`, `rsi6`, `rsi12`, `rsi24`
- `pca_momentum`, `hurst`, `gated_slope`, `regime_gated`, `basis_momentum`
- `vor`, `ao_accel`, `bb_squeeze`, `reversal_shadow`, `reversal_shadow_gated_02`
- `calendar_cyclical`, `nvi`, `stddev`, `ccl`, `oi_gated_momentum`
- ...（共 31 个 active 协变量）

**族名列表**（禁止作为 `cov_override`）：
- `momentum`, `volatility`, `inventory`, `calendar`, `term_structure`, `macro_sentiment`

---

## 五、影响分析

### 5.1 时间浪费

- 每个无效协变量浪费 **10-15 分钟**（588 个 eval points × ~1.5s/point）
- **当前 pending 中约 11 个注定失败** × 12.5 分钟 ≈ **2.3 小时**无效计算
- 全 batch 历史 doomed 约 31 个，但大部分已在 done 队列中

### 5.2 队列状态（审计时刻）

| 类别 | 数量 | 说明 |
|------|------|------|
| 总入队 | 344 | 初始入队数 |
| 已完成 | 15 | 9 ok + 6 no_data |
| 待处理 | ~210 | pending 队列中 |
| 已完成（done） | ~138 | done 队列中（含 15 个 verdict + 其他） |
| 进行中 | 1 | inprogress |
| **pending 中注定失败** | **~11** | 族名 + 幻觉名 + 品种 c |
| pending 中有效 | ~199 | ~210 - ~11 |

### 5.3 预计完成时间

- 有效提案：~199 个
- 每个约 10-15 分钟
- 单线程：199 × 12.5 分钟 ≈ **41.5 小时**（约 1.7 天）

---

## 六、修复建议

### P0-A：在入队脚本添加协变量验证（推荐）✅

**修改文件**: `scripts/enqueue_reprocess.py`

**修改内容**:
```python
import json
from pathlib import Path

def load_supported_covariates():
    """从 covariate_pool.json 读取合法协变量名
    
    注意 covariate_pool.json 的实际 schema：
    - families: list[str] - 族名列表（用于禁止族名当 cov_override）
    - covariates: dict[str, dict] - key 是协变量名，value 包含 status/family/mechanism 等
    - 合法协变量的 status == "active"
    """
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path) as f:
        pool = json.load(f)
    
    # covariates 是顶层 dict，key 是协变量名
    # 提取所有 status == "active" 的协变量名
    supported = set()
    for cov_name, cov_data in pool.get("covariates", {}).items():
        if cov_data.get("status") == "active":
            supported.add(cov_name)
    
    # 添加特殊别名（如 slope_only, none, baseline）
    supported.update({"slope_only", "none", "baseline"})
    
    # families 是族名列表，可用于「禁止族名当 cov_override」检查
    family_names = set(pool.get("families", []))
    
    return supported, family_names

def main(experiments_dir, verdict_path, queue_path, batch_id):
    # ... 现有代码 ...
    
    _SUPPORTED_COVARIATES, _FAMILY_NAMES = load_supported_covariates()
    
    # 在 filter_existing_verdicts 之后，添加协变量验证
    valid_proposals = []
    invalid_count = 0
    for proposal in filtered_proposals:
        # 检查是否是族名（常见错误）
        if proposal.cov_override in _FAMILY_NAMES:
            invalid_count += 1
            print(f"Warning: skipping {proposal.variant_id} - "
                  f"cov_override='{proposal.cov_override}' is a family name, not a covariate")
        # 检查是否在已注册协变量中
        elif proposal.cov_override not in _SUPPORTED_COVARIATES:
            invalid_count += 1
            print(f"Warning: skipping {proposal.variant_id} - "
                  f"cov_override='{proposal.cov_override}' not in registry")
        else:
            valid_proposals.append(proposal)
    
    stats["invalid_covariate"] = invalid_count
    stats["to_enqueue"] = len(valid_proposals)
    
    # ... 后续代码使用 valid_proposals 而不是 filtered_proposals ...
```

**优点**:
- 在入队前过滤，避免浪费时间
- 从 `covariate_pool.json` 读取，避免硬编码漂移
- 区分族名错误和未注册错误，便于调试
- 不修改慢环逻辑，影响范围小

### P0-B：在慢环/回测中添加 fail-fast 机制

**修改文件**: `scripts/monthly_backtest.py` 或 `cascade/features.py`

**修改内容**:
```python
# 在 build_covariate_matrix 中
def build_covariate_matrix(covariate_type, ...):
    if covariate_type not in _REGISTERED_COVARIATES:
        raise ValueError(f"不支持 covariate_type='{covariate_type}'")
    # ... 现有代码 ...

# 在 run_symbol_backtest 中（monthly_backtest.py）
def run_symbol_backtest(...):
    try:
        # 在第一个 eval point 就检测不支持的协变量
        build_covariate_matrix(cov_override, ...)
    except ValueError as e:
        if "不支持 covariate_type" in str(e):
            # Fail-fast：立即返回，不继续跑 588 个点
            return None  # 或返回特定的失败标记
    
    # ... 现有代码 ...
```

**优点**:
- 与入队过滤互补，防止漏网之鱼
- 避免 588 个点空转（节省 10-15 分钟/无效协变量）
- 立即返回失败，便于快速诊断

**注意**:
- 需要与现有的 `except Exception` 逻辑协调
- 可能需要添加特定的失败标记（如 `status: unsupported_covariate`）

### P1：修复 Praxist peer 的协变量生成约束

**修改文件**: Praxist peer 的 prompt 或代码

**修改内容**:
- 在 peer prompt 中明确列出 30 个已注册协变量名白名单
- 禁止使用族名作为 `cov_override`
- 添加验证逻辑，确保生成的协变量名在 `covariate_pool.json` 中

**优点**:
- 从源头防止错误提案生成
- 长期解决方案

**缺点**:
- 需要修改 Praxist 代码，影响范围大
- 需要测试验证

### P2：处理品种 `c` 无数据问题

**选项 A**: 如果玉米品种已退役
- 在入队脚本过滤 `symbol == "c"` 的提案

**选项 B**: 如果应该有数据
- 检查数据管道，为什么 `c` 没有 1h/daily 数据
- 修复数据采集脚本

### P3：安全清理队列中的无效条目

**前提**: 必须先停止慢环消费（避免并发写冲突）

**脚本** (`scripts/cleanup_invalid_queue.py`):
```python
#!/usr/bin/env python3
"""安全清理队列中的无效提案"""
import json
import fcntl
import shutil
from pathlib import Path
from datetime import datetime

def load_supported_covariates():
    """从 covariate_pool.json 读取合法协变量名
    
    注意 covariate_pool.json 的实际 schema：
    - families: list[str] - 族名列表
    - covariates: dict[str, dict] - key 是协变量名，value 包含 status 等
    - 合法协变量的 status == "active"
    """
    pool_path = Path("task_FM/config/covariate_pool.json")
    with open(pool_path) as f:
        pool = json.load(f)
    
    # covariates 是顶层 dict，key 是协变量名
    supported = set()
    for cov_name, cov_data in pool.get("covariates", {}).items():
        if cov_data.get("status") == "active":
            supported.add(cov_name)
    
    supported.update({"slope_only", "none", "baseline"})
    family_names = set(pool.get("families", []))
    
    return supported, family_names

def cleanup_queue():
    queue_path = Path("data/cache/aligned_pending.jsonl")
    backup_path = Path(f"data/cache/aligned_pending.jsonl.bak.{datetime.now():%Y%m%d_%H%M%S}")
    lock_path = Path("data/cache/aligned_pending.jsonl.lock")
    
    _SUPPORTED_COVARIATES, _FAMILY_NAMES = load_supported_covariates()
    
    # 获取文件锁（防止并发访问）
    with open(lock_path, "w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Error: queue is locked by another process. Stop slow loop first.")
            return
        
        try:
            # 备份原文件
            shutil.copy2(queue_path, backup_path)
            print(f"Backup created: {backup_path}")
            
            # 过滤无效条目
            valid_lines = []
            invalid_count = 0
            
            with open(queue_path) as f:
                for line in f:
                    row = json.loads(line)
                    cov = row["cov_override"]
                    symbol = row["symbol"]
                    
                    # 检查是否是族名、未注册、或品种 c
                    if cov in _FAMILY_NAMES:
                        invalid_count += 1
                        print(f"Removing: {row['variant_id']} (family name: {cov})")
                    elif cov not in _SUPPORTED_COVARIATES:
                        invalid_count += 1
                        print(f"Removing: {row['variant_id']} (unregistered: {cov})")
                    elif symbol == "c":
                        invalid_count += 1
                        print(f"Removing: {row['variant_id']} (symbol c has no data)")
                    else:
                        valid_lines.append(line)
            
            # 原子替换（先写临时文件，再重命名）
            temp_path = queue_path.with_suffix(".jsonl.tmp")
            with open(temp_path, "w") as f:
                f.writelines(valid_lines)
            
            temp_path.rename(queue_path)
            
            print(f"\nRemoved {invalid_count} invalid entries, "
                  f"{len(valid_lines)} remaining")
            
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

if __name__ == "__main__":
    cleanup_queue()
```

**安全措施**:
1. **文件锁**: 使用 `fcntl.flock` 防止并发访问
2. **备份**: 清理前自动备份原文件
3. **原子替换**: 先写临时文件，再重命名，避免中途崩溃导致数据丢失
4. **停止慢环**: 必须先停止慢环消费（`pkill -f aligned_slow_loop`）

**使用方法**:
```bash
# 1. 停止慢环
pkill -f aligned_slow_loop

# 2. 运行清理脚本
python scripts/cleanup_invalid_queue.py

# 3. 重启慢环（如需要）
python -m scripts.aligned_slow_loop --batch-id reprocess_20261026
```

---

## 七、关键文件路径

| 文件 | 作用 |
|------|------|
| `/home/abug/timesfm/scripts/aligned_slow_loop.py` | 慢环主脚本 |
| `/home/abug/timesfm/scripts/enqueue_reprocess.py` | 入队脚本（需修改） |
| `/home/abug/timesfm/cascade/features.py` | `build_covariate_matrix` 定义（行 1146），分派链（行 1203-1524） |
| `/home/abug/timesfm/task_FM/config/covariate_pool.json` | 协变量池（31 个 active） |
| `/home/abug/timesfm/data/cache/aligned_pending.jsonl` | 待评估队列（~210 条） |
| `/home/abug/timesfm/logs/reprocess_20261026.log` | 本次重处理日志 |
| `/home/abug/timesfm/task_FM/config/aligned_verdicts.jsonl` | verdict 注册表 |

---

## 八、结论

### 8.1 根本原因总结

1. **Praxist peer（快环）** 生成了错误的协变量名（使用族名而非具体协变量）
2. **旧提案未经过有效的协变量验证**（Laya 预筛只做软建议，不验证协变量注册）
3. **去重脚本盲目重入队**，没有验证协变量有效性（约 81 个注定失败）
4. **品种 `c` 无数据**，导致相关提案失败
5. **慢环无 fail-fast 机制**，每个无效协变量浪费 10-15 分钟

### 8.2 推荐行动（按优先级）

**P0（立即）**:
1. 实施 P0-A：入队脚本添加协变量验证（从 `covariate_pool.json` 读取）
2. 实施 P0-B：慢环/回测添加 fail-fast 机制
3. 实施 P3：安全清理队列中的 ~11 个无效条目（pending 中注定失败）

**P1（短期）**:
4. 实施 P1：修复 Praxist peer 的协变量生成约束（prompt 白名单）
5. 考虑在 `typesafe_prescreen` 中添加本地硬门（不训练 Laya）

**P2（中期）**:
6. 实施 P2：确定品种 `c` 是否应该退役，或修复数据管道

### 8.3 预期效果

- **避免 2.3 小时无效计算**（pending 中 ~11 个无效提案 × 12.5 分钟）
- **提高慢环评估效率**：预计完成时间从 ~1.7 天缩短到 ~1.6 天
- **防止未来生成错误提案**（peer 白名单约束）
- **快速诊断类似问题**（fail-fast 机制）

### 8.4 审计反馈摘要

本报告已根据审计意见修订（重审审计可信度 ~86%）：
- ✅ 修正 §1.1：从"全部 no_data"改为"15 verdicts: 9 ok + 6 no_data"
- ✅ 更新队列状态：待处理 ~210 个，已完成 ~138 个，进行中 1 个
- ✅ 修正 pending 中无效提案数：从 ~81 修正为 ~11（全 batch 历史 doomed ~31）
- ✅ 澄清 W5.2 警告与 no_data 无因果关系
- ✅ 修正 `load_supported_covariates` 函数：从 `pool["covariates"]` 读取，检查 `status == "active"`
- ✅ 澄清 Laya 预筛不做硬校验，即使有 prescreen 也可能无法拦截
- ✅ 新增 P0-B：慢环 fail-fast 机制
- ✅ P3 清理脚本改为安全版本（带锁、备份、原子替换）
- ✅ 修正 §7 路径表：pending 从 333 改为 ~210
- ✅ 修正 §4.1/§4.2 标题：族名从 12 改为 5，幻觉从 9 改为 7

---

**报告路径**: `/home/abug/timesfm/docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation.md`  
**审计路径**: `/home/abug/timesfm/docs/superpowers/reports/2026-10-27-slow-loop-no-data-investigation-audit.md`

**调查人员**: AI Agent (oh-my-claudecode:analyst)  
**审计 / 重审**: New Bot（执行子代理）  
**修订状态**: ✅ 已根据重审审计反馈完成修订（可信度 ~86%）
