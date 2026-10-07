#!/usr/bin/env bash
# backup_data_assets.sh — P0 数据资产异机备份（技术债批次 0+1 合并执行，2026-10-07 宿主裁定）
#
# 资产范围（plans/2026-10-07-tech-debt-closure-plan.md §2.1 + 2026-10-07 四项裁定）：
#   S1 不可重生：aligned_verdicts.jsonl(+.bak 族)、family_registry 备份、.omc/（决策留痕全目录）
#   S2 重生昂贵：baseline_points_*.jsonl、baseline_metrics.json
#   S3 状态类  ：supervisor_state/heartbeat/pid、aligned_pending*.jsonl(+lock)、
#                aligned_checkpoints/、supervisor_events.jsonl、session_unstick_state.json
#   敏感（裁定：明文包含）：.env、.env.praxist、.env.praxist.bak_*（保留 600 权限；
#                远端落 /root/timesfm-data/，仅 root 可读）
#   现场留证  ：git HEAD/status/log + 未提交改动补丁（git diff HEAD）+ 未跟踪小文件（<2MB）快照
#   明示出备（设计决定，见 MANIFEST）：data/cache/daily_pred/（预测产出可再生 ~170MB）、
#                .git/（git 层备份走 sync_backup.sh 另轨互补）、logs/
#
# 目的地（裁定：备份机）：chong@100.96.19.116 → WSL Ubuntu-24.04 /root/timesfm-data/
#   latest/ 镜像式切换（latest.tmp → mv 原子换名，旧 latest 保留至 latest.old 再清）
#   daily/YYYY-MM-DD/ 日快照（远端 cp，免重传），保留 180 天
#   传输机制：tar-over-ssh —— 远端 WSL 无 rsync（2026-10-07 实测只有 tar/md5sum），
#   经 "wsl -d Ubuntu-24.04 --" 包装（BACKUP_SYNC_GUIDE.md 通道），复用 ed25519 密钥
#
# 第二异地（Q2 裁定：默认层）：rclone 步内置；本机未装 rclone 或未配置 remote 时 WARN 跳过
#   （待宿主提供 S3 兼容端点+密钥后自动生效，无需改脚本——装 rclone + rclone config 即可）
#
# 快照语义：对追加中的 jsonl（verdicts/decisions/pending）取读取时点快照，尾部半行风险可接受
#
# ⚠️ 远端调用一律「单命令」铁律（2026-10-07 探针实证）：远端链路 sshd→cmd→wsl→sh 多层
#   重组会吃掉嵌套引号，复合命令（bash -c "a && b"）实测被拆坏；单命令无元字符则全链路可靠。
#   因此：无 rsh_block；远端校验用绝对路径清单 md5sums.remote.txt（md5sum -c 单命令可跑）。
#   另：远端 wsl 每次 stderr 打 UTF-16 代理告警（显示为乱码）——纯噪音，不影响功能。
#   tar 带 --owner=0 --group=0：远端落盘全部 root:root（含明文 .env 600 权限，root-only 更卫生）。
#
# 部署：仓内 scripts/ 为源；操作副本 /home/abug/bin/backup_data_assets.sh（cron 02:15 调用）。
#   ⚠️ 合入新版后必须重新部署：install -m 755 scripts/backup_data_assets.sh /home/abug/bin/
#
# 退出码：0 成功；1 失败（资产缺失/传输失败/md5 不符）——cron 日志与 LOG_FILE 可见
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/abug/timesfm}"
SSH_TARGET="${BACKUP_SSH_TARGET:-chong@100.96.19.116}"
REMOTE_ROOT="${BACKUP_REMOTE_ROOT:-/root/timesfm-data}"
RCLONE_NAME="${RCLONE_REMOTE_NAME:-timesfm-backup}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-180}"
DATE="$(date +%F)"
LOG_FILE="${LOG_FILE:-$REPO_ROOT/logs/backup_data_assets.log}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20)
WRAP="wsl -d Ubuntu-24.04 --"   # 远端 SSH 落 Windows shell，须包装进 WSL

mkdir -p "$(dirname "$LOG_FILE")"
STAGE="$(mktemp -d "$HOME/.backup-stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

log()  { echo "[$(date '+%F %T')] $*" | tee -a "$LOG_FILE" >&2; }
fail() { log "FAIL: $*"; exit 1; }
rssh() { ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$WRAP $*"; }   # 单命令铁律，见头注

log "==== 备份开始（stage: $STAGE）===="
cd "$REPO_ROOT"

# ---------- 1. 资产收集（绝不写入 REPO_ROOT） ----------
A="$STAGE/assets"
mkdir -p "$A/task_FM/config" "$A/.omc" "$A/data/cache"

# S1 不可重生
[ -f task_FM/config/aligned_verdicts.jsonl ] || fail "S1 缺失: aligned_verdicts.jsonl"
cp -p task_FM/config/aligned_verdicts.jsonl "$A/task_FM/config/"
cp -p task_FM/config/aligned_verdicts.jsonl.bak* "$A/task_FM/config/" 2>/dev/null || true
cp -p task_FM/config/family_registry.jsonl.bak* "$A/task_FM/config/" 2>/dev/null || true
[ -f .omc/supervisor_decisions.jsonl ] || fail "S1 缺失: .omc/supervisor_decisions.jsonl"
cp -rp .omc/. "$A/.omc/"

# S2 重生昂贵
ls task_FM/config/baseline_points_*.jsonl >/dev/null 2>&1 || fail "S2 缺失: baseline_points_*"
cp -p task_FM/config/baseline_points_*.jsonl "$A/task_FM/config/"
[ -f task_FM/config/baseline_metrics.json ] || fail "S2 缺失: baseline_metrics.json"
cp -p task_FM/config/baseline_metrics.json "$A/task_FM/config/"

# S3 状态类（计划 §2.1 精确范围）
for f in supervisor_state.json supervisor_heartbeat supervisor_heartbeat.json supervisor.pid \
         aligned_pending.jsonl aligned_pending.inprogress.jsonl aligned_pending.done.jsonl \
         aligned_pending.jsonl.lock supervisor_events.jsonl session_unstick_state.json; do
  if [ -e "data/cache/$f" ]; then cp -p "data/cache/$f" "$A/data/cache/"; fi
done
[ -d data/cache/aligned_checkpoints ] || fail "S3 缺失: aligned_checkpoints/"
cp -rp data/cache/aligned_checkpoints "$A/data/cache/"

# 敏感（2026-10-07 宿主裁定：明文包含）
for f in .env .env.praxist; do
  [ -f "$f" ] || fail "敏感资产缺失: $f"
  cp -p "$f" "$A/"
done
cp -p .env.praxist.bak_* "$A/" 2>/dev/null || true

# ---------- 2. 现场留证（git 状态 + 未提交补丁 + 未跟踪小文件） ----------
{
  echo "git 快照 @ $(date '+%F %T')"
  echo "branch: $(git rev-parse --abbrev-ref HEAD)"
  echo "head:   $(git rev-parse HEAD)"
  echo
  git log --oneline -5
  echo
  git status --porcelain
} > "$STAGE/git_state.txt"
git diff HEAD > "$STAGE/uncommitted.patch"
git ls-files --others --exclude-standard | while IFS= read -r f; do
  if [ -f "$f" ] && [ "$(stat -c%s -- "$f")" -lt 2097152 ]; then
    mkdir -p "$STAGE/untracked/$(dirname "$f")"
    cp -p -- "$f" "$STAGE/untracked/$f"
  fi
done

# ---------- 3. MANIFEST + md5 ----------
N_ASSETS=$(find "$A" -type f | wc -l)
SZ_ASSETS=$(du -sh "$A" | cut -f1)
{
  echo "P0 数据资产备份快照 — $DATE"
  echo "源:     $REPO_ROOT @ $(git rev-parse --short HEAD)"
  echo "目的地: $SSH_TARGET → WSL Ubuntu-24.04 $REMOTE_ROOT/{latest,daily/$DATE}/（root-only）"
  echo "依据:   plans/2026-10-07-tech-debt-closure-plan.md §2 + 2026-10-07 宿主四项裁定"
  echo "        （批次0并入批次1 / 备份机 tar-over-ssh / .env 系列明文包含 / 一次性全量+里程碑增量+cron）"
  echo "规模:   资产文件 $N_ASSETS 个 / $SZ_ASSETS"
  echo "校验:   md5sums.txt（./ 相对路径，人读）+ md5sums.remote.txt（latest/ 绝对路径，远端 md5sum -c 用）"
  echo
  echo "—— 文件清单 ——"
  (cd "$STAGE" && { find assets untracked -type f -printf '%10s  %p\n' 2>/dev/null || true; } | sort -k2)
  echo
  echo "—— 明示出备（设计决定，非遗漏）——"
  echo "  data/cache/daily_pred/（预测产出可再生，~170MB）"
  echo "  .git/（git 层备份走 sync_backup.sh，另轨互补）"
  echo "  logs/（可丢运行日志）"
  echo "  rclone 第二异地层: $(command -v rclone >/dev/null 2>&1 && echo '已安装' || echo '未安装')（Q2 裁定默认层，待宿主端点+密钥）"
} > "$STAGE/MANIFEST.txt"

(cd "$STAGE" && find . -type f ! -name md5sums.txt ! -name md5sums.remote.txt -print0 | sort -z | xargs -0 -r md5sum > md5sums.txt)
# 远端校验清单：绝对路径版（远端 md5sum -c 单命令可跑，免 cd 复合命令）
sed "s|  \./|  $REMOTE_ROOT/latest/|" "$STAGE/md5sums.txt" > "$STAGE/md5sums.remote.txt"

# ---------- 4. 传输（tar-over-ssh；latest.tmp 原子切换） ----------
log "传输: $N_ASSETS 个资产 / $SZ_ASSETS → $SSH_TARGET:$REMOTE_ROOT"
rssh "mkdir -p $REMOTE_ROOT/daily" || fail "远端 mkdir 失败"
rssh "rm -rf $REMOTE_ROOT/latest.tmp" || fail "远端清场失败"
rssh "mkdir -p $REMOTE_ROOT/latest.tmp" || fail "远端建 staging 失败"
if ! tar --owner=0 --group=0 -czf - -C "$STAGE" . | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$WRAP tar xzf - -C $REMOTE_ROOT/latest.tmp"; then
  fail "tar 传输失败"
fi
rssh "mv $REMOTE_ROOT/latest $REMOTE_ROOT/latest.old" || true   # 首次运行无 latest，容忍
rssh "mv $REMOTE_ROOT/latest.tmp $REMOTE_ROOT/latest" || fail "latest 切换失败"
rssh "rm -rf $REMOTE_ROOT/latest.old" || true

# ---------- 5. 远端全量 md5 校验（单命令 + 绝对路径清单） ----------
if ! VOUT=$(rssh "md5sum -c $REMOTE_ROOT/latest/md5sums.remote.txt --quiet"); then
  log "md5 校验失败明细: $VOUT"
  fail "远端 md5 校验不通过"
fi
log "远端 md5sum -c 全量校验通过"

# ---------- 6. 日快照 + 保留期清扫 ----------
rssh "rm -rf $REMOTE_ROOT/daily/$DATE" || fail "日快照清场失败"
rssh "cp -a $REMOTE_ROOT/latest $REMOTE_ROOT/daily/$DATE" || fail "日快照失败"
rssh "find $REMOTE_ROOT/daily -mindepth 1 -maxdepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +" || fail "保留期清扫失败"
log "日快照 daily/$DATE/ 落位；保留期 ${RETENTION_DAYS} 天清扫完成"

# ---------- 7. rclone 第二异地（Q2 裁定：默认层；未配置则 WARN 跳过） ----------
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -qx "$RCLONE_NAME:"; then
  rclone copy "$STAGE" "${RCLONE_NAME}:timesfm-data/latest" --transfers 4 >> "$LOG_FILE" 2>&1 || fail "rclone latest 失败"
  rclone copy "$STAGE" "${RCLONE_NAME}:timesfm-data/daily/$DATE" --transfers 4 >> "$LOG_FILE" 2>&1 || fail "rclone daily 失败"
  log "rclone 第二异地层同步完成"
else
  log "WARN: rclone 第二异地层未配置（缺 rclone 二进制或 remote '$RCLONE_NAME'），Q2 裁定待端点+密钥，本轮跳过"
fi

log "==== 备份成功: latest/ + daily/$DATE/ + md5 全过；资产 $N_ASSETS 个 / $SZ_ASSETS ===="
echo "backup OK: $N_ASSETS files ($SZ_ASSETS) → $SSH_TARGET:$REMOTE_ROOT/daily/$DATE/"
