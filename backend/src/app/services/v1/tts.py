"""TTS service for synthesizing text into server events.

This module provides an async-compatible helper that mirrors the
previous `_generate_tts_events` logic from the runtime but is
extracted to allow reuse and separation of concerns.
"""
from __future__ import annotations

from typing import Any, List, Dict
import time
import base64
from app.services.multimodal.session_protocol import ServerEvent


async def generate_tts_events(session_id: str, text_response: str, tts_backend: Any) -> List[Dict[str, Any]]:
    """Generate streamed TTS events for a response.

    Returns a list of server-event payload dicts (audio_start, audio_chunk..., audio_end).
    """
    # Lazily import numpy only when needed
    import numpy as np
    from app.services.multimodal.polar_runtime import SENTENCE_SPLIT_RE

    def split_sentences(text: str):
        parts = SENTENCE_SPLIT_RE.split(text.strip())
        return [s.strip() for s in parts if s.strip()]

    sentences = split_sentences(text_response) or [text_response]
    started = time.time()
    events = [
        ServerEvent(
            type="audio_start",
            session_id=session_id,
            data={"sample_rate": tts_backend.sample_rate, "sentence_count": len(sentences)},
        ).as_payload()
    ]

    # Synthesize each sentence synchronously via executor in caller
    for index, sentence in enumerate(sentences):
        pcm = tts_backend.generate(sentence)
        pcm_int16 = (pcm * 32767).clip(-32768, 32767).astype(np.int16)
        events.append(
            ServerEvent(
                type="audio_chunk",
                session_id=session_id,
                data={"audio": base64.b64encode(pcm_int16.tobytes()).decode(), "index": index},
            ).as_payload()
        )

    tts_time = time.time() - started
    events.append(
        ServerEvent(type="audio_end", session_id=session_id, data={"tts_time": round(tts_time, 2)}).as_payload()
    )
    return events
