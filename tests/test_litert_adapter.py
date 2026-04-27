import asyncio
import base64

import numpy as np
import pytest

from app.providers.litert_adapter import LiteRTAdapter


class FakeTTSBackend:
    sample_rate = 16000

    def generate(self, text: str):
        # return a short float32 numpy waveform (mono)
        t = np.linspace(0, 0.01, int(self.sample_rate * 0.01), endpoint=False)
        pcm = 0.1 * np.sin(2 * np.pi * 440 * t)
        return pcm.astype(np.float32)


class FakeRuntime:
    def __init__(self):
        self._tts_backend = FakeTTSBackend()

    async def _ensure_runtime_loaded(self):
        return None

    def _split_sentences(self, text: str):
        return [text]


@pytest.mark.asyncio
async def test_litert_stream_tts_monotonic_events(monkeypatch):
    fake = FakeRuntime()

    # Patch the runtime accessor used by the adapter
    import app.providers.litert_adapter as adapter_mod

    monkeypatch.setattr(adapter_mod, "get_LiteRT_runtime_service", lambda: fake)

    adapter = LiteRTAdapter(model="test-model")
    events = []
    async for ev in adapter.stream_tts("hello world"):
        events.append(ev)

    # Expect at least audio_start, one audio_chunk, audio_end
    types = [e.get("type") for e in events]
    assert "audio_start" in types
    assert "audio_chunk" in types
    assert "audio_end" in types

    # Validate the audio_chunk payload decodes to non-empty bytes
    for e in events:
        if e.get("type") == "audio_chunk":
            data = e.get("data") or {}
            b64 = data.get("audio")
            assert b64 is not None
            decoded = base64.b64decode(b64)
            assert len(decoded) > 0
            break
