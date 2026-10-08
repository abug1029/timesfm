#!/bin/bash
# Git sync script for timesfm backup
# Usage: ./sync_backup.sh [push|pull|fetch|status]

set -e

REPO_DIR="/home/abug/timesfm"

cd "$REPO_DIR"

case "${1:-status}" in
    push)
        echo "=== Pushing to backup ==="
        git push backup master 2>&1 | grep -E "(Counting|Writing|remote:|To |Everything)" || true
        echo "✓ Push complete"
        ;;
    pull)
        echo "=== Pulling from backup ==="
        git pull backup master 2>&1 | grep -E "(remote:|From |Already|Updating)" || true
        echo "✓ Pull complete"
        ;;
    fetch)
        echo "=== Fetching from backup ==="
        git fetch backup 2>&1 | grep -E "(remote:|From |\*)" || true
        echo "✓ Fetch complete"
        ;;
    status)
        echo "=== Local status ==="
        git status --short --branch
        echo ""
        echo "=== Sync status ==="
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git ls-remote backup master 2>/dev/null | awk '/refs\/heads\/master/ {print $1}')
        if [ -z "$REMOTE" ]; then
            echo "? Cannot reach remote"
        elif [ "$LOCAL" = "$REMOTE" ]; then
            echo "✓ In sync (both at ${LOCAL:0:7})"
        else
            echo "✗ Out of sync"
            echo "  Local:  ${LOCAL:0:7}"
            echo "  Remote: ${REMOTE:0:7}"
        fi
        ;;
    *)
        echo "Usage: $0 {push|pull|fetch|status}"
        exit 1
        ;;
esac
