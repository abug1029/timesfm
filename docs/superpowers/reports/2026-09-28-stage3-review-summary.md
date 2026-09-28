# Stage 3 专家审核汇总（2026-09-28）

> 本文件汇总 Stage 3 期间所有专家审核的结论、发现与处置。
> 对应 audit R5（「审核 APPROVE 无仓库工件」）的修补。

---

## 审核记录一览

| 审核对象 | 提交 | 审核方 | 结论 | 关键发现 |
|---------|------|--------|------|---------|
| **D5 修复**（cutoff 改 bar 收盘时间） | `d621a1a` | oh-my-claudecode:code-reviewer | APPROVE | 10 个脚本修复一致；5 个补全（`c318091`） |
| **PR-A1**（协议指纹加 cutoff 约定） | `6c94275` | oh-my-claudecode:code-reviewer | APPROVE | protocol_v2 升级正确；默认值 bar_close 与 D5 一致 |
| **T7**（板块部分退化 WARN） | `5dde4dc` | oh-my-claudecode:code-reviewer | APPROVE | 50% 阈值预警逻辑正确 |
| **T3 v2**（dir_acc 口径改档） | `2d38839` | oh-my-claudecode:code-reviewer | **REQUEST CHANGES** | 方向 8/8 通过；但发现 **2 HIGH**：`n_active`/`n_total`/`active_dir_acc` 已被占用（Signal-based）；schema 常量指错 |
| **PR-C1/PR-C2**（T5 计划统计语义） | `becd2bf` | oh-my-claudecode:code-reviewer | **REQUEST CHANGES** | **4 HIGH**：D3 违规在 PR-C1 中逐字存活；2 个测试必然失败；`compute_n_required` NameError；h/q 三处定义 |
| **M4**（T1a 验证脚本） | `59c7d3b` | oh-my-claudecode:code-reviewer | **REQUEST CHANGES** | **2 HIGH**：`pair_set_hash` 假 FAIL；判别器自指导致静默误诊 |

---

## Stage 3 复核修正提交

| 提交 | 内容 |
|------|------|
| `12e0850` | T3 v2 字段命名冲突修正（嵌套 `dir_acc_caliber`）+ PR-C1 D3 违规整节删除 + PR-C2 T_max + abandoned 修正 |
| `f754762` | M4 复核修正：`pair_set_hash` 改为「键存在」判定 + 时间基判别器 + `A1_NOT_WIRED` 状态 |
| `becd2bf` | D2/D3/D7 修正（PR-C1 VIF→实测 HAC、q=11、close_family 删除、D5 changelog 补至 10 脚本）|
| `59c7d3b` | M4 验证脚本实现（21 测试）|
| `2d38839` | T3 v2 改档初版（后被 `12e0850` 部分推翻）|

---

## 后续宿主裁定（2026-09-28）

四笔裁定由宿主本人作出，落实为 `ac979ef`：

| 裁定 | 内容 | spec 位置 |
|------|------|----------|
| **M3** | 重置 eg/jd/lh 为 ACTIVE（旧 DEAD/HOLD 判定基于已证伪口径） | `symbol_status.json` |
| **T3 字段改名** | spec §4.7 W6.5 `n_total`/`n_active` → `n_dir_total`/`n_dir_active`（避开 Signal-based 冲突） | spec v15 §4.7 W6.5 |
| **M6** | 审计集规模 2–3 → **7 品种**（SS/SR/M/JD/LH/CJ/FU）；spec §1.1 L2 字面修订 | spec v15 §1.1 L2 |
| **M5** | `horizon_known` 分类 + `verified_by` 白名单 + 降级/升级语义 | spec v15 §4.5 W5.5 |

---

## T1a 实测发现的代码缺陷（v5 新增）

| 项 | 内容 | 处置 |
|----|------|------|
| **ensure_baselines 不校验协议指纹** | 原实现只按 `n_lines<100` 判断；PR-A1 升级指纹后，rb 的旧基线（588 行 / protocol_v1）被**静默保留**，与其他 7 份新基线跨协议不可比 | 已修：`d4e7097` 增加 `_baseline_protocol_fingerprint` + `_current_protocol_fingerprint` + 13 测试 |
| **验收判据缺指纹一致性层** | 原判据 `ls \| wc -l = 8` 通过，但指纹一致性失败 | 已修：plan v5 追加验收命令（`sort -u \| wc -l` 必须 = 1）|

---

## 审核机制评估

**有效性证据**：
- Stage 2 自我纠正：v1 被退回，4 个 CRITICAL 空转被修正（`a038f76`）
- Stage 3 三路复核全部 **REQUEST CHANGES**：每路复核都发现了**实质性**问题（方向性错误、测试必然失败、假 FAIL 路径、静默误诊）
- T1a 实测发现 `ensure_baselines` 指纹校验缺口：**plan 的验收判据本身存在盲区**

**结论**：「核验—退回—修正」机制**真实有效**。每轮复核都在防止虚假闭合。

---

## 提交总览（本会话 2026-09-28）

```
ac979ef  落实四项裁定（M3 重置 / T3 字段改名 / M6 审计集 / M5 horizon_known）
d4e7097  ensure_baselines 协议指纹校验（T1a 实测发现）
f754762  M4 复核修正（假 FAIL + 静默误诊）
12e0850  三路复核修正（T3 / PR-C1 / PR-C2）
becd2bf  D2/D3/D7 修正
59c7d3b  M4 验证脚本（21 测试）
2d38839  T3 v2 改档
84d2263  T3 文档化（后被 `2d38839` 修正方向）
7dc7585  M4 验证脚本补 M2 孤儿项
18b56ad  D8/M2/M5/M6 修正
becd2bf  D2/D3/D7 修正
6c63c66  Stage 3 最终报告
... 以及早期 D5/PR-A1/T7/T3/T4 等
```

**未推送提交**：~65（origin 落后，待 PAT 吊销后 push）
