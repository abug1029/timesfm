# Regression Baselines

本目录存放回归测试基线，用于验证各批次实施后"零新增失败"。

## 基线列表

| 基线 | Tag | Commit | 失败数 | 说明 |
|------|-----|--------|--------|------|
| baseline-2026-10-08 | baseline-2026-10-08 | cf1f7b6 | 11 | 待解决问题 spec 实施前基线 |

## 使用方法

实施完成后，在同环境（WSL Ubuntu-22.04, Python 3.11, .venv）运行：

```bash
.venv/bin/pytest --tb=no -q 2>&1 | grep -E '^FAILED|^ERROR' | sort > /tmp/new_failures.txt
diff <(sort docs/superpowers/baselines/baseline-YYYY-MM-DD-failures.txt) /tmp/new_failures.txt
```

若 diff 输出为空，则零新增失败。若有新增，需逐条分析是否为实施引入。

## 注意事项

- 基线失败多为预存在缺陷（缺 torch/sklearn/数据），非本轮实施目标
- 逐条比对 ID，非仅数量（数量相同但 ID 不同仍算新增）
- 每个批次完成后都应验证零新增
