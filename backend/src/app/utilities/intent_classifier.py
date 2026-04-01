"""IntentClassifier -- LLM-based intent classification via Ollama JSON mode.

Kept in utilities/ so it can be imported by both:
  - tools/classify_tool.py  (the @function_tool the orchestrator calls)
  - agents/classify_agent.py (which defines the classify_agent Agent object)

Dependency graph (no cycles):
  utilities/intent_classifier.py
       ^                  ^
  tools/classify_tool   agents/classify_agent
       ^
  agents/orchestrator
"""

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

# Three user-facing intents + unknown.
# analytics  — any quantitative / insight query (top-N, totals, comparisons,
#              publishing time, trends). Sub-routing happens inside AnalyticsAgent.
# tag_suggestions         — suggest or apply content tags.
# article_recommendations — recommend or retrieve articles / documents.
_VALID_INTENTS = [
    "analytics",
    "tag_suggestions",
    "article_recommendations",
    "unknown",
]


# ---------------------------------------------------------------------------
# Few-shot examples for the intent classifier (kept minimal for latency)
# ---------------------------------------------------------------------------
_INTENT_FEW_SHOT: list[dict] = [
    {"role": "user",      "content": "top 5 videos by views"},
    {"role": "assistant", "content": '{"intent": "analytics"}'},
    {"role": "user",      "content": "best day to post on TikTok"},
    {"role": "assistant", "content": '{"intent": "analytics"}'},
    {"role": "user",      "content": "suggest tags for this article"},
    {"role": "assistant", "content": '{"intent": "tag_suggestions"}'},
    {"role": "user",      "content": "recommend articles about AI"},
    {"role": "assistant", "content": '{"intent": "article_recommendations"}'},
    {"role": "user",      "content": "hello"},
    {"role": "assistant", "content": '{"intent": "unknown"}'},
]

_INTENT_SYSTEM_PROMPT = """\
You are a JSON-only intent classifier for a social media analytics platform.
Output ONLY a valid JSON object: {"intent": "<label>"}
No markdown, no explanation, no extra keys.

Intent labels (choose exactly one):
- analytics            : ANY question about data, metrics, numbers, performance, reach,
                         views, engagement, top content, best posting time, platform
                         comparison, trends, publishing schedule, or content analysis.
                         When in doubt between analytics and unknown, choose analytics.
- tag_suggestions      : user wants tag or label suggestions for a piece of content.
- article_recommendations : user wants article, document, or content recommendations.
- unknown              : greetings, off-topic, or truly ambiguous requests.

Rule: questions about "top N", "best", "compare", "when to post", "how many",
"total", "average", "views", "reach", "engagement" are ALWAYS analytics.\
"""


class IntentClassifier:
    """Intent classifier using Qwen2.5-Coder (or any configured model) via Ollama JSON-mode."""

    VALID_INTENTS = _VALID_INTENTS

    @staticmethod
    async def complex(message: str, context: dict | None = None) -> str:  # noqa: ARG002
        """Classify intent using Ollama JSON-mode with Qwen2.5-Coder.

        Uses a dedicated ``ollama_intent_model`` (default: qwen2.5-coder) so SQL
        generation and intent classification can use different models independently.
        Falls back to ``ollama_model`` if ``ollama_intent_model`` is not set.
        """
        import json  # noqa: PLC0415
        import httpx  # noqa: PLC0415

        # Prefer dedicated intent model; fall back gracefully
        intent_model = (settings.ollama_intent_model or "").strip() or settings.ollama_model
        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

        messages = [
            {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
            *_INTENT_FEW_SHOT,
            {"role": "user", "content": message},
        ]

        payload = {
            "model": intent_model,
            "format": "json",
            "stream": False,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            raw = data.get("message", {}).get("content", "{}")
            parsed = json.loads(raw)
            intent = parsed.get("intent", "unknown").strip().lower()

            if intent not in IntentClassifier.VALID_INTENTS:
                logger.warning(
                    "Ollama intent classifier returned invalid label — defaulting to 'unknown'",
                    intent=intent,
                    model=intent_model,
                )
                return "unknown"

            logger.info(
                "Intent classified",
                intent=intent,
                model=intent_model,
                message_snippet=message[:60],
            )
            return intent

        except Exception as exc:
            logger.error(
                "Ollama intent classification failed — defaulting to 'unknown'",
                error=str(exc),
                model=intent_model,
            )
            return "unknown"

    @staticmethod
    async def classify(message: str, context: dict | None = None) -> str:
        """Public entry point: classify intent using Ollama JSON-mode."""
        intent = await IntentClassifier.complex(message, context=context)
        logger.debug("Final intent", intent=intent)
        return intent
