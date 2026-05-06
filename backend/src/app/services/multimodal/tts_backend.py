"""Platform-aware TTS backend loader for multimodal chat."""

from __future__ import annotations

import os
import platform
import sys

import numpy as np


def is_apple_silicon() -> bool:
    """Return whether the host is Apple Silicon."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


class TTSBackend:
    """Unified TTS interface."""

    sample_rate: int = 24000

    def generate(self, text: str, voice: str = "af_heart", speed: float = 1.1) -> np.ndarray:
        raise NotImplementedError


class MLXBackend(TTSBackend):
    """mlx-audio backend (Apple Silicon GPU via MLX)."""

    def __init__(self):
        from mlx_audio.tts.generate import load_model

        self._model = load_model("mlx-community/Kokoro-82M-bf16")
        self.sample_rate = self._model.sample_rate
        list(self._model.generate(text="Hello", voice="af_heart", speed=1.0))

    def generate(self, text: str, voice: str = "af_heart", speed: float = 1.1) -> np.ndarray:
        results = list(self._model.generate(text=text, voice=voice, speed=speed))
        return np.concatenate([np.array(result.audio) for result in results])


class ONNXBackend(TTSBackend):
    """kokoro-onnx backend (ONNX Runtime, CPU)."""

    def __init__(self):
        import kokoro_onnx
        from huggingface_hub import hf_hub_download

        model_path = hf_hub_download("fastrtc/kokoro-onnx", "kokoro-v1.0.onnx")
        voices_path = hf_hub_download("fastrtc/kokoro-onnx", "voices-v1.0.bin")

        self._model = kokoro_onnx.Kokoro(model_path, voices_path)
        self.sample_rate = 24000

    def generate(self, text: str, voice: str = "af_heart", speed: float = 1.1) -> np.ndarray:
        pcm, _ = self._model.create(text, voice=voice, speed=speed)
        return pcm


class NullTTSBackend(TTSBackend):
    """No-op backend used when no TTS library is installed.

    Returns a single silent PCM frame so the audio_start / audio_end
    handshake still fires and the frontend does not hang waiting.
    """

    sample_rate: int = 24000

    def generate(self, text: str, voice: str = "af_heart", speed: float = 1.1) -> np.ndarray:
        # Return 0.1 s of silence rather than crashing
        return np.zeros(int(self.sample_rate * 0.1), dtype=np.float32)


def load_tts_backend(preferred_backend: str = "auto") -> TTSBackend:
    """Load the best available TTS backend for the current platform."""
    if preferred_backend in {"auto", "mlx"} and is_apple_silicon() and not os.environ.get("KOKORO_ONNX"):
        try:
            return MLXBackend()
        except ImportError:
            if preferred_backend == "mlx":
                raise

    try:
        return ONNXBackend()
    except (ImportError, Exception):
        if preferred_backend in {"onnx"}:
            raise

    # Last resort — silent backend so the server stays running without TTS deps
    return NullTTSBackend()