#!/usr/bin/env bash
# =============================================================================
# cleanup_experiments.sh — experiments 目录瘦身脚本
#
# 用途:
#   task_FM/experiments/ 下 run_* 目录随时间累积大量中间产物（peer_workspaces、
#   trajectory.jsonl、graph/、artifacts/、shared_store.db 等），可安全瘦身。
#   本脚本按目录名排序（目录名含时间戳，天然可排序），保留最新 3 个 run_* 目录
#   完整不动，其余 run 目录内的可删项移动到 experiments/_trash/<runname>/ 下。
#
# 两段式设计:
#   1) --apply 阶段不直接 rm，而是把命中项 mv 到 experiments/_trash/<runname>/
#      （保持 run 内相对路径结构，幂等：已移过的项自动跳过）。
#   2) --purge 阶段才真正 rm -rf experiments/_trash。即回收磁盘需要用户确认后
#      手动再跑一次 `cleanup_experiments.sh --purge`。
#   无参数 = dry-run：只打印将删清单和体积统计，不做任何修改。
#
# supervisor 依赖原因（以下内容绝不可删，本脚本也不会碰它们）:
#   - results/                  : harvest_survivors 读取
#   - gen_*/generation_results.json : _read_token_m 读取
#   - logs/                     : _latest_429_reset 读取
#   - shared_findings/、run_summary.json、orchestrator_status.json、
#     run 根下的 *.json / task_spec.yaml 等元数据文件: run 状态与审计依赖
#   另: --apply 前自动跳过 supervisor 当前活跃 run（从 /proc 里 praxist.run
#   进程 cmdline 的 --run-dir 提取）；_trash 目录自身不算 run。
#
# 已知取舍（审核登记 2026-09-17）:
#   - gems/ 是 praxist 框架 per-run 状态，supervisor 不读取；移走后该 run
#     无法重放其 gem 库（两段式 _trash 有缓冲）。
#   - shared_store.db 被 scripts/praxist_session_unstick.py:187 读取（解卡
#     调试用）；purge 后对已清理 run 的解卡调试不可用。
#   - 活跃 run 快照在脚本启动时取一次；--apply 执行期间若 supervisor 新启
#     run，仅靠"最新 3 个"保底（apply 窗口内连启 >=3 个新 run 才会误伤，
#     概率极低）。
#
# 用法:
#   cleanup_experiments.sh            # dry-run（默认）
#   cleanup_experiments.sh --apply    # 把可删项移入 experiments/_trash/
#   cleanup_experiments.sh --purge    # 永久删除 experiments/_trash/（不可恢复）
# =============================================================================

set -euo pipefail

EXPROOT=/home/abug/timesfm/task_FM/experiments
TRASH="$EXPROOT/_trash"
KEEP_LATEST=3

# run 目录内允许移动的项（目录或文件），其余一切不碰
PURGEABLE_ITEMS=(
    peer_workspaces
    trajectory.jsonl
    graph
    artifacts
    shared_store.db
    shared_store.db-shm
    shared_store.db-wal
    gems
)

MODE=dry-run
case "${1:-}" in
    "")          MODE=dry-run ;;
    --apply)     MODE=apply ;;
    --purge)     MODE=purge ;;
    -h|--help)   sed -n '2,40p' "$0" | grep -E '^#(\s|$)' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: 未知参数: $1 (用法: $0 [--apply|--purge])" >&2; exit 2 ;;
esac

log() { echo "[cleanup_experiments] $*"; }

# ---------------------------------------------------------------------------
# --purge: 直接删除 _trash（独立两段式的第二段）
# ---------------------------------------------------------------------------
if [[ "$MODE" == "purge" ]]; then
    if [[ ! -d "$TRASH" ]]; then
        log "--purge: $TRASH 不存在，无需删除"
        exit 0
    fi
    size=$(du -sh "$TRASH" 2>/dev/null | cut -f1)
    log "--purge: 永久删除 $TRASH ($size) ..."
    rm -rf "$TRASH"
    log "--purge: 完成"
    exit 0
fi

# ---------------------------------------------------------------------------
# 检测 supervisor 当前活跃 run（从 praxist.run 进程 cmdline 提取 --run-dir）
# ---------------------------------------------------------------------------
declare -A ACTIVE_RUNS=()
for pid in $(pgrep -f 'praxist\.run' 2>/dev/null || true); do
    if [[ -r "/proc/$pid/cmdline" ]]; then
        run_dir=$(tr '\0' '\n' < "/proc/$pid/cmdline" \
            | awk 'p=="--run-dir"{print; exit} {p=$1}')
        if [[ -n "$run_dir" && "$run_dir" == "$EXPROOT"/run_* ]]; then
            ACTIVE_RUNS["$(basename "$run_dir")"]=1
        fi
    fi
done

# ---------------------------------------------------------------------------
# 枚举 run_* 目录，确定保留集（最新 3 个 + 活跃 run）
# ---------------------------------------------------------------------------
mapfile -t all_runs < <(find "$EXPROOT" -maxdepth 1 -mindepth 1 -type d \
    -name 'run_*' | sort)
if [[ ${#all_runs[@]} -eq 0 ]]; then
    log "未找到任何 run_* 目录，无事可做"
    exit 0
fi

declare -A KEEP=()
for run in "${all_runs[@]: -$KEEP_LATEST}"; do
    KEEP["$(basename "$run")"]=1
done
for name in "${!ACTIVE_RUNS[@]}"; do
    KEEP["$name"]=1
done

# ---------------------------------------------------------------------------
# dry-run / apply 主循环
# ---------------------------------------------------------------------------
total_bytes=0
n_items=0
plan_tmp=$(mktemp)
trap 'rm -f "$plan_tmp"' EXIT

for run in "${all_runs[@]}"; do
    name=$(basename "$run")
    [[ -n "${KEEP[$name]:-}" ]] && continue

    for item in "${PURGEABLE_ITEMS[@]}"; do
        src="$run/$item"
        dst="$TRASH/$name/$item"
        [[ -e "$src" ]] || continue          # 幂等：已移过则跳过
        if [[ -e "$dst" ]]; then
            log "WARN: 目标已存在，跳过 $src"
            continue
        fi
        size=$(du -sk "$src" 2>/dev/null | cut -f1 || echo 0)
        echo -e "${size}\t$src" >> "$plan_tmp"
        total_bytes=$(( total_bytes + size * 1024 ))
        n_items=$(( n_items + 1 ))
    done
done

# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
human_size() {
    numfmt --to=iec --suffix=B "${1:-0}" 2>/dev/null || echo "${1}B"
}

kept_list=$(printf '%s\n' "${all_runs[@]: -$KEEP_LATEST}" | xargs -n1 basename | tr '\n' ' ')
log "模式: $MODE | run 目录总数: ${#all_runs[@]} | 保留最新 $KEEP_LATEST 个: $kept_list"
if [[ ${#ACTIVE_RUNS[@]} -gt 0 ]]; then
    log "活跃 run（supervisor praxist.run 检测到，跳过）: ${!ACTIVE_RUNS[*]}"
else
    log "活跃 run: 无"
fi
echo

if [[ "$MODE" == "dry-run" ]]; then
    if [[ $n_items -eq 0 ]]; then
        log "dry-run: 无可删项（可能已全部清理过）"
    else
        log "dry-run: 将删清单（$n_items 项，预计回收 $(human_size "$total_bytes")）:"
        sort -rn "$plan_tmp" | awk -F'\t' '{
            printf "  %8s  %s\n", $1>=1048576 ? sprintf("%.1fGB",$1/1048576) : $1>=1024 ? sprintf("%.0fMB",$1/1024) : sprintf("%.0fKB",$1), $2
        }'
    fi
    echo
    log "dry-run 未删除任何东西。确认无误后执行: $0 --apply"
    log "--apply 后磁盘空间尚未释放，需再手动执行: $0 --purge"
    exit 0
fi

# MODE == apply
if [[ $n_items -eq 0 ]]; then
    log "--apply: 无可删项（幂等，无需操作）"
    exit 0
fi

moved_bytes=0
moved_items=0
while IFS=$'\t' read -r size src; do
    rel=${src#"$EXPROOT"/}                          # run_xxx/item
    dst="$TRASH/$rel"
    mkdir -p "$(dirname "$dst")"
    mv "$src" "$dst"
    moved_bytes=$(( moved_bytes + size * 1024 ))
    moved_items=$(( moved_items + 1 ))
    log "  moved: $rel"
done < "$plan_tmp"

log "--apply 完成: 移动 $moved_items 项，共 $(human_size "$moved_bytes") -> $TRASH"
log "磁盘空间尚未释放。确认后执行: $0 --purge"
