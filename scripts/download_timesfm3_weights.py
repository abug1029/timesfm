#!/usr/bin/env python3
"""Download TimesFM-3.0 weights from HuggingFace"""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # CPU-only download

from huggingface_hub import snapshot_download

print("Downloading google/timesfm-3.0-pytorch ...")
path = snapshot_download(
    repo_id="google/timesfm-3.0-pytorch",
    cache_dir="/home/abug/.cache/huggingface/hub",
)
print(f"Downloaded to: {path}")
print("✅ Download complete")
