"""Multimodal message parser and classifier wrapper.

Provides a small abstraction that normalizes incoming client events into a
`ParsedMessage` dict and performs intent classification (multimodal-aware)
using the existing `IntentClassifier` utility.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.logging import get_logger
from app.utilities.intent_classifier import IntentClassifier

logger = get_logger(__name__)


def normalize_client_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw client websocket/REST event into a simple message dict.

    Expected input shapes vary; this function extracts text, image URLs, and
    other attachments into a common structure consumed by downstream code.
    """
    text = ""
    images: List[str] = []
    attachments: List[Dict[str, Any]] = []
    modality = "text"

    if not isinstance(event, dict):
        return {"text": "", "images": [], "attachments": [], "modality": modality}

    # Common shapes
    if "text" in event:
        text = str(event.get("text") or "")
        modality = "text"

    # Some clients send `content` or `message`
    if not text:
        for key in ("content", "message", "transcript"):
            if key in event and isinstance(event.get(key), str):
                text = str(event.get(key) or "")
                modality = "text"
                break

    # Images or attachments
    if "images" in event and isinstance(event.get("images"), list):
        images = [str(u) for u in event.get("images") if u]
        modality = "image" if images else modality

    if "attachments" in event and isinstance(event.get("attachments"), list):
        attachments = event.get("attachments")

    return {"text": text, "images": images, "attachments": attachments, "modality": modality}


async def parse_and_classify(event: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return parsed message plus intent classification.

    Result keys:
        - text, images, attachments, modality
        - intent (legacy label), confidence, reasoning, raw_intent, model
    """
    parsed = normalize_client_event(event)
    try:
        classification = await IntentClassifier.classify_detailed(parsed.get("text", ""), context=context)
    except Exception as exc:
        logger.warning("Intent classification failed", error=str(exc))
        classification = {
            "intent": "unknown",
            "confidence": 0.0,
            "reasoning": "classification_failed",
            "raw_intent": "",
            "model": "",
        }

    return {**parsed, **classification}


__all__ = ["parse_and_classify", "normalize_client_event"]
