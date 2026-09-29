# 三环系统成果展示格式规范

> 本文档定义了三环系统成果的标准展示格式，确保一致性和可读性。

## 标准展示结构

### 1. 总体统计 (必须)

```
【总体统计】
总评估数: {total_evaluations}
过门变体: {gate_pass_count} ({gate_pass_rate:.1f}%)
  S 级 (卓越): {tier_s_count}
  A 级 (优秀): {tier_a_count}
  B 级 (良好): {tier_b_count}
```

**说明**: 
- 总评估数: 所有经过慢环评估的变体总数
- 过门率: gate_pass=True 的变体占比
- 等级分布: S/A/B 三级，S 级最高

---

### 2. 品种成果汇总 (必须)

```
【品种成果汇总】
品种     过门数      平均DirAcc     S级     A级     B级     FDR通过   
cf       1          0.531         0       1       0       1
cj       8          0.511         0       3       5       0
m        7          0.511         0       1       6       0
p        3          0.565         1       2       0       2
rb       6          0.514         3       3       0       0
sr       13         0.528         4       9       0       0
ss       4          0.544         2       2       0       0
```

**说明**:
- 按品种字母顺序排列
- 平均 DirAcc: 该品种所有过门变体的方向准确率平均值
- FDR通过: 通过 False Discovery Rate 严格检验的变体数

---

### 3. 顶级成果列表 (必须)

```
【顶级成果 (S级 + A级)】
排名   变体ID                          品种   DirAcc   等级   协变量                     FDR
1      sr_calendar_cyclical           sr     0.617    S      calendar_cyclical         ❌
2      p_oi                           p      0.568    A      oi                        ✅
...
```

**说明**:
- 仅展示 S 级和 A 级变体
- 按 DirAcc 降序排列
- 必须包含: 排名、变体ID、品种、DirAcc、等级、协变量、FDR状态
- FDR 状态用 ✅/❌ 表示

---

### 4. FDR 严格检验通过变体 (可选，如有则必须展示)

```
【FDR 严格检验通过变体】
排名   变体ID                          品种   DirAcc   等级   协变量
1      p_oi                           p      0.568    A      oi
2      p_calendar_cyclical            p      0.563    A      calendar_cyclical
3      cf_rsi6                        cf     0.531    A      rsi6
```

**说明**:
- 仅当有 FDR 通过的变体时展示
- 按 DirAcc 降序排列
- FDR 通过是最严格的质量标准，代表统计学上的强证据

---

## 格式化规则

### 数值精度
- DirAcc: 保留 3 位小数 (如 0.617)
- 百分比: 保留 1 位小数 (如 29.4%)
- 计数: 整数

### 对齐方式
- 品种代码: 左对齐，4 字符宽
- 变体ID: 左对齐，35 字符宽
- 数值: 右对齐或居中
- 等级: 居中，4 字符宽

### 符号约定
- FDR 通过: ✅
- FDR 未通过: ❌
- 缺失数据: N/A 或 -

---

## 快速查询命令

### 生成完整报告
```bash
python3 scripts/generate_results_report.py
```

### 查询特定品种
```bash
python3 scripts/query_results.py --symbol sr
```

### 查询顶级成果
```bash
python3 scripts/query_results.py --tier S,A --top 10
```

---

## 文件位置

- 报告模板: `docs/RESULTS_FORMAT_TEMPLATE.md` (本文件)
- 最新报告: `docs/results_summary.md`
- 原始数据: `task_FM/config/aligned_verdicts.jsonl`

---

## 更新日志

- 2026-09-24: 初始版本，定义标准展示格式
