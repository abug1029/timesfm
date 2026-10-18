# Laya 预筛中文泄漏修复 Spec 审核（三审）

- 审核对象：`/home/abug/timesfm/docs/superpowers/specs/2026-10-18-laya-chinese-leak-fix-spec.md`
- 对象状态头：`Conditional Pass · v3（post-audit-2 2026-10-18）`
- 代码根：WSL `/home/abug/timesfm`（machine `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`）
- 交叉文档：Frozen lifecycle `2026-10-18-proposal-lifecycle-management-spec.md`（PrescreenStatus 三值）；前审同路径 `…-spec-audit.md`（初审 + 再审）
- 日期：2026-10-18（Asia/Shanghai）
- 轮次：**三审**（相对 2026-10-18 再审轻条件）
- 结论：**通过**——再审 2 条轻条件均已闭合，PrescreenStatus 三值无回退，无新 P0；可冻结开 Phase 1。残留仅为数字刮词级 P2，不挡冻结。

---

## 0. 相对再审的差分总览

| 再审轻条件 | 再审级别 | 三审状态 | 证据（v3 草案 + 本机复跑） |
|------------|----------|----------|---------------------------|
| `_PD_MIN_LEN=8` vs「487」；典型 `"-> long, -> short"` core 长 9 漏判 | **P1-轻** | **已闭合** | §1.2 / §3.1：`_PD_MIN_LEN = 12`；空壳文案改为 ~473（26.3%，阈值=12）；典型样例 thr=12 → True |
| 收窄正则后全角标点残留；需钉死字符类 + 标点剥离 | **P1-轻** | **已闭合** | §3.1 钉死允许/禁止字符类；新增 `_FULLWIDTH_PUNCT` 二次清洗；§4.1 验收改为「0 东亚宽字符」+ 全角标点单测 |
| PrescreenStatus 扩枚举（初审 P0） | — | **仍闭合（无回退）** | §3.3 / §4.3 / §7 仍不扩；代码 `Literal["success","degraded","error"]` |

**本机复跑（v3 算法，1796 条含汉字 PD，8503 proposal 文件）**：

| 指标 | 值 |
|------|-----|
| thr<8 空壳 | 258（14.4%） |
| thr<12 空壳 | **496（27.6%）** |
| strip 后仍含验收禁止类（Han + CJK 标点 + 全角标点） | **0** |
| strip 后仍含 `\uff00–\uffef` 任意全角区 | **0** |
| strip 后仍含任意非 ASCII（如 `…` U+2026） | 65（不在禁止类内） |
| 典型 `"-> long, -> short"` | core=`longshort` 长 9；shell12=**True**，shell8=False |
| `"价差（利润） -> long"` | → `'-> long'`（全角括号已剥） |

> 说明：再审「新正则 + thr=12 → 473」未含全角二次清洗；v3 双道 strip 后空壳略升至 **496**。草案写 ~473 与实测差 ~23，属 P2 刮词（见 §3），不推翻「阈值=12 对齐典型空壳」的闭合判定。

---

## 1. 总评

| 维度 | 判定 | 摘要 |
|------|------|------|
| 问题陈述 | 强 | 泄漏点、脏源、v2/v3 修订轨迹清晰 |
| 与 Frozen lifecycle | **对齐** | 不扩 PrescreenStatus；三值无回退 |
| Phase 1 止血设计 | **强** | strip + 全角二次清洗 + 空壳回退（thr=12）+ timeout + best-effort language |
| 验收可执行性 | 强 | 字符类已钉死；空壳阈值与典型样例一致；门禁口径与禁止类一致 |
| 安全 / 运维 | 低风险 | 无新密钥面；§8 rollback 仍在 |

---

## 2. 轻条件闭合核验

### 2.1 空壳阈值（再审 P1-轻 → 闭合）

- 草案：`_PD_MIN_LEN = 12`（§3.1）；§1.2 / §4.1 同步为 ~473 / 阈值=12。
- 典型目标空壳 `"-> long, -> short"`：core 长 9，**thr=12 必判空壳**（再审漏判点已消）。
- 空壳回退仍为 `predicted_direction=""`（字段保留），注释已与代码一致（v3 修订）。

### 2.2 字符类 + 全角标点（再审 P1-轻 → 闭合）

- §3.1 **验收字符类**：允许 ASCII / 拉丁扩展 / 半角通用标点；禁止 Han、CJK 标点、全角标点区。
- 实现：`_ZH`（汉字+CJK 标点）+ `_FULLWIDTH_PUNCT`（全角标点，保留全角数字/字母）——本机 range check：`Ａ–Ｚａ–ｚ０–９` 不被剥，`（）` 等被剥。
- 复跑：**验收禁止类残留 = 0**（再审 369 全角区残留已消）。
- §4.1 新增「全角标点清洗」行；集成/门禁口径改为「0 东亚宽字符」，不再用模糊「0 CJK」。

### 2.3 PrescreenStatus 无回退

- 代码：`cascade/typesafe_prescreen.py` L31 仍三值。
- 草案：§3.3 skip / 可选 degraded+note；§4.3 验收「未扩」；§7 明示不做 `duplicate`。

---

## 3. 残留（P2，不挡冻结）

1. **空壳计数刮词**：§1.2/§4.1 写 ~473；完整 v3 双道 strip + thr=12 本机为 **496**。建议实施前改成 ~496，或在 commit 说明「含全角二次清洗后重算」。不挡 Phase 1。
2. **「纯英文」措辞 vs 钉死字符类**：§4.1 首行仍写「纯英文 + 半角符号」，而字符类允许拉丁扩展，且全角字母/数字有意保留；另有 65 条残留通用标点（`…` 等，不在禁止类）。门禁以「东亚宽字符」为准即可；首行可改为「无东亚宽字符」。
3. **`_ZH` 未覆盖 CJK 扩展区**（`\u3400`–`\u4DBF` 等）：实测脏样本主在 BMP 统一表意区，边缘 P2。
4. 状态头仍 Conditional Pass；冻结后改 Approved/Frozen。

---

## 4. 方案完整性（三审）

### 已覆盖且可执行

1. 下游 `_strip_chinese` + `_is_shell_pd` + `_build_state` 止血
2. 全角标点二次清洗 + 验收字符类钉死
3. 空壳 thr=12 + 回退空串
4. `language: en` best-effort
5. 去重不扩枚举；harvest = Phase 2b
6. timeout 统一；rollback；风险表含空壳与全角项

### 相对再审不再作为条件

- 空壳阈值与「487」错位 —— **关闭**（改为 12 / ~473 量级）
- 全角标点 / 字符类未钉死 —— **关闭**（二次清洗 + 禁止类 + 实测 0 残留）

---

## 5. 修复清单（三审）

### 无开 Phase 1 前阻断项

（无）

### 可选 P2（实施时顺手或 commit 说明）

1. 将空壳验收数从 ~473 更新为本机双道 strip 后的 ~496。
2. §4.1 首行「纯英文」对齐「无东亚宽字符」口径。
3. 冻结后改状态头。

---

## 6. 建议实施顺序

1. **冻结本 v3 草案**（或顺手改 P2 刮词后冻结）。
2. **Phase 1**：`_strip_chinese` / `_FULLWIDTH_PUNCT` / `_is_shell_pd(thr=12)` / `_build_state` / timeout / best-effort `language` + 单测/集成/门禁。
3. **Phase 2**：backfill pre-check skip（不扩枚举）；harvest 仅 Phase 2b。
4. **Phase 3**：prompt English-only + 10 seed。

---

## 7. 结论句

**通过。** 再审全部轻条件已闭合：`_PD_MIN_LEN=12` 与典型空壳对齐；验收字符类钉死并经 `_FULLWIDTH_PUNCT` 二次清洗，本机禁止类残留为 0；PrescreenStatus 三值无回退、无新 P0。可作 Phase 1 冻结基线。残留仅空壳计数 ~473 vs 实测 ~496、以及「纯英文」措辞等 P2，不挡开工。
