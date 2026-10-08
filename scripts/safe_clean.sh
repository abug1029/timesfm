#!/usr/bin/env bash
# safe_clean.sh — git clean 白名单包装（技术债批次 1，2026-10-07）
#
# 裸 `git clean -xdf` 会一锅端以下 gitignored 数据资产，**一律禁止**（AGENTS.md 禁令）：
#   裁决史 aligned_verdicts.jsonl(+.bak) / 基线 baseline_points_* 与 metrics /
#   决策留痕 .omc/ / 队列与检查点 data/cache/ / .env 系列 / logs/ 运行日志
# 清理必须走本脚本：白名单内一律保留，白名单外照常清理。
#
# 用法：
#   safe_clean.sh            dry-run（默认；自带白名单自检——命中保护路径即 FATAL 退出）
#   safe_clean.sh --apply    实际执行（信任排除项；执行前务必先跑一次 dry-run 目检）
#
# 部署：仓内 scripts/ 为源；操作副本 <FM_ROOT>/bin/safe_clean.sh（合入新版后重新 install）
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MODE="${1:-}"
PROTECT_RE='task_FM/config/|\.omc/|data/cache/|(^|/)\.env|(^|/)logs/'
EXCLUDES=(-e 'task_FM/config/' -e '.omc/' -e 'data/cache/' -e 'logs/' -e '.env' -e '.env.*')

case "$MODE" in
  ""|-n|--dry-run)
    echo "== DRY-RUN（--apply 才执行）: $REPO_ROOT =="
    OUT="$(git -C "$REPO_ROOT" clean -xdnf "${EXCLUDES[@]}")"
    ;;
  --apply)
    echo "== APPLY: $REPO_ROOT（白名单保护中）=="
    exec git -C "$REPO_ROOT" clean -xdf "${EXCLUDES[@]}"
    ;;
  *)
    echo "用法: $0 [--apply|-n|--dry-run]" >&2
    exit 2
    ;;
esac

if [ -n "$OUT" ]; then
  echo "$OUT"
  if echo "$OUT" | grep -Eq "$PROTECT_RE"; then
    echo "FATAL: dry-run 命中白名单保护路径——排除项失效，禁止 --apply，请人工核查" >&2
    exit 1
  fi
  echo "-- 以上为将清理项；零保护路径命中 --"
else
  echo "(无可清理项)"
fi
