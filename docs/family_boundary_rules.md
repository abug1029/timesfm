# 研究 family 边界规则

spec `2026-09-24-covariate-research-credibility-design.md` §4.3 W3.6（v4/v5/v7/v8/v10）。
唯一实现：`cascade/research_family.py`。

> **命名注意**：本文件的 "family" 是**研究 family**（同一研究问题的确认检验集合）。
> `cascade/cov_family.py` 的 "family" 是**协变量 family**（momentum / volatility 等类型分组，
> 用于 BH 分组）。两者不是同一个概念，不可互换。

---

## 1. family 是什么

一个 family = **同一研究问题 + 同一预注册系列**内全部**确认检验**。

- **默认：一个品种 = 一个研究问题 = 一个 family**（同一 `protocol_fingerprint` 下）。
- **批次、运行、代际都不重置校正。** 按批次拆 family 等于可以多开批次拿到多个较小的校正
  family，从而规避校正 —— 这是 v3 的错误，v4 起禁止。
- **只有确认检验进 family。** 探索期结果不是检验，不产生 p 值声称，不进 family。
  这是"探索自由、确认严格"的分界线。

## 2. family 键

```
family_key          = (symbol, research_question)
research_question   = (预测目标, 预测任务/期限, research_target_hash)
research_target_hash = hash(品种, 目标变量, 价格序列定义, 复权/换月规则版本)
```

### research_target_hash 只哈希"研究目标本身"

**不含**观测数据内容与截止时间。理由：若哈希全量历史内容，新增一根 bar、历史数据修订
都会让哈希变化 → 同一研究问题被数据自然增长拆成多个 family，恰恰削弱防规避意图。

| 变化 | 是否开新 family |
|------|----------------|
| 新增 cutoff（数据向前生长） | ❌ 否 |
| 修订历史 bar | ❌ 否 |
| 复权版本内的小幅数据更新 | ❌ 否 |
| 换批次 / 换 run / 换代际 | ❌ 否 |
| `protocol_fingerprint` 中与研究问题无关的字段变化（如 `cov_fill_version`） | ❌ 否 |
| 目标变量定义变化 | ✅ 是 |
| 预测期限变化 | ✅ 是 |
| 价格序列定义变化 | ✅ 是 |
| 复权/换月**规则版本**变化 | ✅ 是 |

> **版本值 vs 内容**：`research_target_hash` 含复权/换月**规则版本**。Phase 5 补指纹字段时
> **只允许记录版本，不得改变版本值** —— 值变则所有现存 family 分裂（见计划 H6）。

### 与 target_snapshot_hash 的区分（v8）

| 字段 | 用途 | 性质 |
|------|------|------|
| `research_target_hash` | family 键：判断"是不是同一研究问题" | 稳定 |
| `target_snapshot_hash` | experiment_fingerprint：判断"实验记录可否合并" | 随运行变化 |

**二者不得混用。**

## 3. v10 序列化规范（锁死跨实现字节级确定性）

| 项 | 规定 |
|----|------|
| 输入顺序 | `symbol \| target_var \| price_series_def \| adjust_roll_rule_version`（固定、有序） |
| 前缀参与 | schema 前缀 `research_target_v1\|` **参与**最终 SHA-256 输入（是输入字节，不是元数据） |
| 分隔符 | `\|`（U+007C）；字段值禁止含 `\|`，出现即 **fail-loud**（不做静默替换，避免碰撞） |
| 规范化 | 全小写、去两端空白；枚举 token 用单一规范拼写（无别名）；Unicode **NFC** |

## 4. 封账、注册截止、未完成检验

- **终态四种**：`confirmed` / `refuted` / `abandoned` / `timeout`
- **注册截止（二者并用，先到者为准）**
  - 时间截止 `family_close_at` = family **首个成员注册后 90 天**
  - 成员上限 `family_max_members` = **20**
  - 截止后该 family 不再接纳新确认假设 —— 这是封账可达的**必要条件**
- **`T_max` = 180 天，从成员 `registered_at` 起算**（唯一、可验证的时钟；
  不是从"确认开始"或"确认集开放"起算）
- **封账**：全部成员到达终态时**一次性**运行 BH-FDR
- **封账上界** = `family_close_at + T_max`。注册截止（集合固定）+ 成员 T_max（每个成员一个
  终止点）二者缺一不可
- **未完成成员**：封账时未达终态的**立即**落 `timeout` + `p = 1`，不等待

### p = 1 的适用范围（v5 收紧）

**仅当**该假设**已进入确认 family、且在截止前未完成确认**时，才赋 `p = 1`。

探索中止、尚未注册确认的假设**不得**计入确认 family，也不赋 `p = 1` —— 它们根本不在 `K` 里。
否则会把探索期的正常中止误算成确认 family 成员，虚增 `K`。

### abandoned 与 timeout 仍计入 K

否则"结果不好就悄悄丢掉" = 缩小 K = p-hacking。

## 5. 跨品种范围（必须写进报告模板）

本 spec **默认不跨品种合并校正**：每个品种是独立研究问题，各自控制 FDR。

因此**结论范围仅限品种内**：报告**不得**产出跨品种聚合声称（如"24 个品种整体有效"）。
若日后需要跨品种结论，必须**另行定义**一个包含全部品种确认检验的 family 并重新校正。

代码常量：`cascade.research_family.family_report_scope()`

## 6. 新研究问题的启动要求

必须规定：
1. 与旧 family 的**关系**（独立问题 vs 旧问题的延续）
2. **报告范围**（新 family 的结论**不得**与旧 family 合并宣称）
3. **禁止**仅用新批次名 / 新 run 绕开校正
