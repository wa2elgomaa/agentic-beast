"""Response tool (v1) — refines and formats agent responses.

This tool centralizes behavior for transforming analytics results into
human-readable summaries and for packaging TTS metadata when the flow
originated from audio.
"""
from typing import Any, Dict

class ResponseTool:
    def __init__(self, tts_provider=None):
        self.tts_provider = tts_provider

    async def refine(self, result: Dict[str, Any], for_audio: bool = False) -> Dict[str, Any]:
        # Scaffold: if analytics, summarize result; otherwise echo.
        if result.get("intent") == "analytics":
            summary = result.get("note") or "Analytics results available."
            out = {"type": "analytics", "summary": summary, "data": result.get("result_data")}
        else:
            out = {"type": "chat", "summary": result.get("answer") or ""}

        if for_audio and self.tts_provider:
            # Placeholder for TTS metadata
            out["tts"] = {"sample_rate": 24000, "chunks": []}

        return out


def get_response_tool(tts_provider=None) -> ResponseTool:
    return ResponseTool(tts_provider=tts_provider)
