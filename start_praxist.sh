#!/bin/bash
cd /home/abug/timesfm
set -a
source .env.praxist
set +a
echo "PRIMARY_MODEL="
echo "ANTHROPIC_BASE_URL="
source .praxist-venv/bin/activate
exec python3 scripts/praxist_supervisor.py --goal scripts/praxist_goal.yaml --once
