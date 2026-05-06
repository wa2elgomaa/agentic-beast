#!/usr/bin/env python3
"""
Model downloader for the Beast backend.

Downloads two models into the shared /models volume:
  1. LiteRT voice model (Gemma 4 E2B) — for TTS/voice agent
  2. Qwen2.5-7B-Instruct GGUF — for llama-cpp inference server (all chat/analytics agents)

Exit codes:
  0 = success
  1 = download failed
  2 = argument/env error
"""
import os
import sys
from pathlib import Path

try:
    from huggingface_hub import snapshot_download, hf_hub_download
except ImportError:
    print("Error: huggingface-hub not installed", file=sys.stderr)
    sys.exit(2)


LOCAL_DIR = "/models"
TOKEN = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def download_litert_voice():
    """Download Gemma 4 E2B LiteRT model for the voice agent."""
    repo = "litert-community/gemma-4-E2B-it-litert-lm"
    target = Path(LOCAL_DIR) / "gemma-4-E2B-it.litertlm"

    if target.exists():
        print(f"✓ Voice model already present: {target}", file=sys.stderr)
        return 0

    print(f"Downloading voice model {repo} → {LOCAL_DIR}...", file=sys.stderr)
    try:
        path = snapshot_download(
            repo,
            local_dir=LOCAL_DIR,
            token=TOKEN,
            resume_download=True,
        )
        print(f"✓ Voice model downloaded to {path}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Warning: voice model download failed: {e}", file=sys.stderr)
        return 1


def download_gguf():
    """Download Qwen2.5-7B-Instruct Q4_K_M GGUF for llama-cpp."""
    repo = "bartowski/Qwen2.5-7B-Instruct-GGUF"
    filename = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    target = Path(LOCAL_DIR) / filename

    if target.exists():
        print(f"✓ GGUF model already present: {target}", file=sys.stderr)
        return 0

    print(f"Downloading {filename} from {repo}...", file=sys.stderr)
    try:
        path = hf_hub_download(
            repo_id=repo,
            filename=filename,
            local_dir=LOCAL_DIR,
            token=TOKEN,
            resume_download=True,
        )
        print(f"✓ GGUF model downloaded to {path}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: GGUF model download failed: {e}", file=sys.stderr)
        return 1


def download_gemma_e4b_gguf():
    """Download Gemma 4 E4B-it Q4_K_M GGUF for llama-cpp."""
    repo = "ggml-org/gemma-4-E4B-it-GGUF"
    filename = "gemma-4-E4B-it-Q4_K_M.gguf"
    target = Path(LOCAL_DIR) / filename

    if target.exists():
        print(f"✓ Gemma E4B GGUF already present: {target}", file=sys.stderr)
        return 0

    print(f"Downloading {filename} from {repo}...", file=sys.stderr)
    try:
        path = hf_hub_download(
            repo_id=repo,
            filename=filename,
            local_dir=LOCAL_DIR,
            token=TOKEN,
            resume_download=True,
        )
        print(f"✓ Gemma E4B GGUF downloaded to {path}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Warning: Gemma E4B GGUF download failed: {e}", file=sys.stderr)
        return 1


def main():
    if not TOKEN:
        print("Warning: HF_TOKEN not set. Downloads may be rate-limited.", file=sys.stderr)

    Path(LOCAL_DIR).mkdir(parents=True, exist_ok=True)

    rc_voice = download_litert_voice()
    rc_gguf = download_gguf()
    download_gemma_e4b_gguf()  # optional — non-fatal if missing

    # GGUF (Qwen) is required for llama-cpp; other failures are non-fatal
    if rc_gguf != 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
