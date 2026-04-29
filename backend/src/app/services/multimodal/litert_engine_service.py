"""Shared LiteRT engine singleton.

Mirrors the global `engine` + `load_models()` pattern in polar/src/server.py so
that one Engine instance is created once and reused for every STT call, exactly
as the polar standalone server does.

Model resolution order (mirrors polar/src/server.py):
  1. VOICE_MODEL env / settings if it points to an existing local file
  2. basename of VOICE_MODEL inside MODELS_DIR
  3. HuggingFace Hub download (litert-community/gemma-4-E2B-it-litert-lm) using HF_TOKEN

Usage:
    from app.services.multimodal.litert_engine_service import get_litert_engine

    engine = await get_litert_engine()          # lazy-init, thread-safe
    conversation = engine.create_conversation(...)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import litert_lm  # type: ignore
    LITERT_AVAILABLE = True
except Exception:
    LITERT_AVAILABLE = False

# HF Hub coordinates (same as polar/src/server.py)
_HF_REPO = "litert-community/gemma-4-E2B-it-litert-lm"
_HF_FILENAME = "gemma-4-E2B-it.litertlm"

# Mirrors polar/src/server.py globals
_engine = None
_engine_lock = asyncio.Lock()


def _resolve_model_path() -> str:
    """Resolve the model path, downloading from HuggingFace Hub if necessary.

    Mirrors polar/src/server.py resolve_model_path():
      - If VOICE_MODEL points to an existing file, use it.
      - Otherwise download HF_REPO/HF_FILENAME using HF_TOKEN.
    """
    from app.config import settings  # local import to avoid circular deps at module init

    model_path = (getattr(settings, "voice_model", "") or "").strip()
    hf_token = (getattr(settings, "hf_token", "") or os.environ.get("HF_TOKEN", "")).strip() or None
    models_dir = (getattr(settings, "models_dir", "") or "/models").strip()

    # 1. Exact path exists
    if model_path and os.path.exists(model_path):
        return model_path

    # 2. Basename inside MODELS_DIR
    if model_path:
        candidate = Path(models_dir) / Path(model_path).name
        if candidate.exists():
            logger.info("Found model at %s", candidate)
            return str(candidate)

    # 3. HuggingFace Hub download (mirrors polar/src/server.py behaviour)
    logger.info(
        "Model not found locally — downloading %s/%s from HuggingFace Hub (first run only)…",
        _HF_REPO,
        _HF_FILENAME,
    )
    try:
        from huggingface_hub import hf_hub_download  # type: ignore

        Path(models_dir).mkdir(parents=True, exist_ok=True)
        downloaded = hf_hub_download(
            repo_id=_HF_REPO,
            filename=_HF_FILENAME,
            local_dir=models_dir,
            token=hf_token or None,
        )
        logger.info("Model downloaded to %s", downloaded)
        return downloaded
    except Exception as exc:
        raise FileNotFoundError(
            f"LiteRT model not found at '{model_path}' and HuggingFace download failed: {exc}. "
            f"Ensure HF_TOKEN is set and internet access is available, "
            f"or manually place the model at VOICE_MODEL path."
        ) from exc


def _load_engine_sync(model_path: str):
    """Blocking engine load — must be called in a thread executor.

    Mirrors polar_runtime.py: try GPU first, fall back to CPU if unavailable
    (e.g. inside a Docker container without GPU passthrough).
    """
    logger.info("[LiteRT] Loading engine from %s…", model_path)
    try:
        engine = litert_lm.Engine(
            model_path,
            backend=litert_lm.Backend.GPU,
            vision_backend=litert_lm.Backend.GPU,
            audio_backend=litert_lm.Backend.CPU,
        )
        engine.__enter__()
        logger.info("[LiteRT] Engine ready (GPU backend).")
        return engine
    except Exception as exc_gpu:
        logger.warning(
            "[LiteRT] GPU backend failed (%s) — falling back to CPU.", exc_gpu
        )

    engine = litert_lm.Engine(
        model_path,
        backend=litert_lm.Backend.CPU,
        vision_backend=litert_lm.Backend.CPU,
        audio_backend=litert_lm.Backend.CPU,
    )
    engine.__enter__()
    logger.info("[LiteRT] Engine ready (CPU backend).")
    return engine


async def get_litert_engine():
    """Return the shared LiteRT engine, initialising it on first call (lazy).

    Raises:
        RuntimeError      — litert_lm not installed
        FileNotFoundError — model file missing and HF download failed
    """
    global _engine

    if _engine is not None:
        return _engine

    async with _engine_lock:
        if _engine is not None:
            return _engine

        if not LITERT_AVAILABLE:
            raise RuntimeError(
                "litert_lm is not installed in this environment. "
                "Set VOICE_LLM_PROVIDER=openai in .env to use OpenAI Whisper instead."
            )

        model_path = _resolve_model_path()
        _engine = await asyncio.to_thread(_load_engine_sync, model_path)

    return _engine


async def close_litert_engine() -> None:
    """Gracefully tear down the engine (call during app shutdown)."""
    global _engine
    if _engine is not None:
        try:
            await asyncio.to_thread(_engine.__exit__, None, None, None)
        except Exception:
            pass
        finally:
            _engine = None

