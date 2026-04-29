"""Shared helpers for resolving multimodal model specifications.

This centralizes HF download and local-path resolution so adapters and
runtime services do not duplicate logic and avoid circular imports.
"""
from pathlib import Path
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)


def resolve_model_spec(model_spec: Optional[str], models_dir: Optional[str] = None, hf_token: Optional[str] = None) -> Optional[str]:
    """Resolve a model specifier into a usable local path.

    - If `model_spec` is a path that exists, return it.
    - If `model_spec` contains '/', treat it as a HF Hub spec and attempt
      to download the given filename into `models_dir` (or repo models dir).
    - If `model_spec` is falsy, return None.
    - On failure to download, return the original `model_spec` so callers
      can decide how to proceed.
    """
    if not model_spec:
        return None

    try:
        # Absolute/local path check
        if os.path.exists(model_spec):
            return model_spec

        # models_dir may be provided as string; ensure Path
        if models_dir:
            models_dir_path = Path(models_dir)
        else:
            # default to repository-level 'models' directory
            repo_root = Path(__file__).resolve().parents[5]
            models_dir_path = repo_root / "models"

        # Check for file already present in models_dir
        candidate = models_dir_path / model_spec
        if candidate.exists():
            return str(candidate)
        candidate_basename = models_dir_path / Path(model_spec).name
        if candidate_basename.exists():
            return str(candidate_basename)

        # If spec doesn't look like HF repo/file, return as-is
        if "/" not in model_spec:
            return model_spec

        # Otherwise attempt HF download
        try:
            from huggingface_hub import hf_hub_download

            models_dir_path.mkdir(parents=True, exist_ok=True)
            repo_id, filename = model_spec.rsplit("/", 1)
            logger.info("Downloading model from HF Hub", extra={"repo": repo_id, "filename": filename, "target_dir": str(models_dir_path)})
            path = hf_hub_download(repo_id=repo_id, filename=filename, cache_dir=str(models_dir_path), token=hf_token)
            return path
        except Exception as exc:  # pragma: no cover - network/download
            logger.warning("Failed to download model from HF Hub; returning spec as-is", extra={"spec": model_spec, "error": str(exc)})
            return model_spec
    except Exception as exc:
        logger.exception("Error resolving model spec", extra={"spec": model_spec, "error": str(exc)})
        return model_spec


def _resolve_model_path(model_name: Optional[str], models_dir: Optional[str] = None, hf_token: Optional[str] = None) -> Optional[str]:
    """Compatibility wrapper expected by runtime: same semantics as resolve_model_spec.

    Args:
        model_name: local path or HF spec (repo/filename)
        models_dir: directory to store downloaded models
        hf_token: Hugging Face token
    Returns:
        Local path to model or None/empty string on failure.
    """
    try:
        return resolve_model_spec(model_name, models_dir=models_dir, hf_token=hf_token)
    except Exception:
        logger.exception("_resolve_model_path failed", extra={"model_name": model_name})
        return None
