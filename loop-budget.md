# Loop Budget — FM_a 期货预测系统

> Primary loop: **FM_a Triage** (30m cadence)

## Daily limits

| Loop | Max runs/day | Max tokens/day | Max sub-agent spawns/run |
|------|--------------|----------------|--------------------------|
| FM_a Triage | 不限 | **无限制** (Unlimited Plan) | 不限 |

## On budget exceed

> 不适用 — 无限量 Coding Plan，无 token 上限。

## Kill switch

- Command or issue label: `loop-pause-all`
- Resume only after human clears the flag in STATE.md

## Notes

- Token 预算检查已禁用（Coding Plan 无限量）
- 仍保留 loop-run-log.md 用于运行可观测性
- 如果循环产生噪音或无意义输出，人工可随时 kill
