#!/bin/bash
# Start peer using official Praxist path (no cascade bypass)
# Phase 2 C2: New peers should use this script, not cascade bypass
set -euo pipefail

cd /home/abug/timesfm

echo "Starting peer with official Praxist path..."
echo "Task: task_FM"
echo "Mode: daemonized"

praxist start --task-path task_FM --daemonize --json

echo "Peer started successfully."
echo "Check status: praxist status"
echo "View logs: tail -f task_FM/.praxist/logs/peer.log"
