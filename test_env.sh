#!/bin/bash
cd ~/timesfm
set -a
source .env.praxist
set +a
echo "ANTHROPIC_BASE_URL="
echo "ANTHROPIC_API_KEY_SET=YES"
echo "MODEL="
echo "FM_TIMESFM_MODEL_PATH="
echo "PRAXIST_BIN="
echo "PATH_check=praxist_bin_OK"
echo "MODEL_DIR=model_dir_OK"
