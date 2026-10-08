#!/bin/bash
# 从备份拉取并比对差异
# Usage: ./pull_and_compare.sh

cd /home/abug/timesfm

echo "=== 1. 拉取远程更新 ==="
git fetch backup 2>&1 | grep -v "wsl:" | grep -v "警告" || true

echo ""
echo "=== 2. 同步状态 ==="
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse backup/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✓ 已同步 (both at ${LOCAL:0:7})"
    exit 0
fi

echo "✗ 存在差异"
echo ""

echo "=== 3. 远程有但本地没有的提交 ==="
REMOTE_ONLY=$(git log --oneline HEAD..backup/master)
if [ -z "$REMOTE_ONLY" ]; then
    echo "(无)"
else
    echo "$REMOTE_ONLY"
fi

echo ""
echo "=== 4. 本地有但远程没有的提交 ==="
LOCAL_ONLY=$(git log --oneline backup/master..HEAD)
if [ -z "$LOCAL_ONLY" ]; then
    echo "(无)"
else
    echo "$LOCAL_ONLY"
fi

echo ""
echo "=== 5. 文件差异统计 ==="
git diff --stat HEAD...backup/master

echo ""
echo "=== 操作建议 ==="
if [ -n "$REMOTE_ONLY" ] && [ -z "$LOCAL_ONLY" ]; then
    echo "远程领先，可执行: git merge backup/master 或 git pull backup master"
elif [ -z "$REMOTE_ONLY" ] && [ -n "$LOCAL_ONLY" ]; then
    echo "本地领先，可执行: git push backup master"
else
    echo "两边都有新提交，需要 merge: git merge backup/master"
fi
