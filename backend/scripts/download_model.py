#!/usr/bin/env python3
"""
Lightweight model downloader for Gemma 4 E2B from Hugging Face Hub.
Downloads to /models volume mount.

Exit codes:
  0 = success
  1 = download failed
  2 = argument/env error
"""
import os
import sys
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("Error: huggingface-hub not installed", file=sys.stderr)
    sys.exit(2)

def main():
    # Config
    repo = "litert-community/gemma-4-E2B-it-litert-lm"
    local_dir = "/models"
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    
    # Validate
    if not token:
        print("Warning: HF_TOKEN not set. Downloads may be rate-limited.", file=sys.stderr)
    
    Path(local_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"Downloading {repo} to {local_dir}...", file=sys.stderr)
        path = snapshot_download(
            repo,
            local_dir=local_dir,
            token=token,
            resume_download=True,
        )
        print(f"✓ Downloaded to {path}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
