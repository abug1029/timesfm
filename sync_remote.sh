#!/bin/bash
# 简化版同步脚本：拉取并合并远程更新
cd /home/abug/timesfm

echo "拉取远程更新..."
git fetch backup --quiet 2>/dev/null

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse backup/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✓ 已同步"
    exit 0
fi

echo "合并中..."
git stash push -m "auto-stash" --quiet 2>/dev/null
git merge backup/master --no-edit --quiet 2>/dev/null
STASH_RESULT=$?
git stash pop --quiet 2>/dev/null

if [ $STASH_RESULT -eq 0 ]; then
    echo "✓ 同步完成 ($(git rev-parse HEAD | cut -c1-7))"
else
    echo "✗ 合并失败，请手动处理"
    exit 1
fi
