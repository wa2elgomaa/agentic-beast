"""IntentClassifier -- pure-logic intent classification, no agent imports.

Kept in tools/ so it can be imported by both:
  - tools/classify_tool.py  (the @function_tool the orchestrator calls)
  - agents/classify_agent.py (which defines the classify_agent Agent object)

Dependency graph (no cycles):
  tools/intent_classifier.py
       ^                  ^
  tools/classify_tool   agents/classify_agent
       ^
  agents/orchestrator
"""

import spacy
from spacy.matcher import Matcher

from app.logging import get_logger

logger = get_logger(__name__)

_VALID_INTENTS = [
    "query_metrics",
    "analytics",
    "publishing_insights",
    "ingestion",
    "tagging",
    "document_qa",
    "unknown",
]


class IntentClassifier:
    """Intent classifier: spaCy keyword matching with Agent SDK fallback."""

    INTENT_KEYWORDS = {
        "query_metrics": [
            # [{"LOWER": {"IN": ["top", "total", "sum", "average", "many", "count"]}}],
            # [{"LOWER": {"IN": ["views", "likes", "shares", "interactions", "comments", "metrics"]}}],
            # [{"LOWER": {"IN": ["reach", "impressions", "engagement", "followers", "interactions", "metrics", "views"]}}],
        ],
        "publishing_insights": [
            # [{"LOWER": {"IN": ["publish", "publishing", "post", "posting", "schedule"]}}],
            # [{"LOWER": "best"}, {"LOWER": {"IN": ["day", "time"]}}],
            # [{"LOWER": "when"}, {"LOWER": "to"}, {"LOWER": "publish"}],
            # [{"LOWER": "which"}, {"LOWER": {"IN": ["day", "time"]}}, {"LOWER": "is"}, {"LOWER": {"IN": ["best", "better"]}}],
        ],

        "analytics": [
            # [{"LOWER": {"IN": ["tag", "recommend", "trend", "peak", "worst"]}}],
            # [{"LOWER": "when"}, {"LOWER": "is"}, {"LOWER": "the"}, {"LOWER": "best"}],
        ],
        "ingestion": [
            # [{"LOWER": {"IN": ["ingest", "import", "upload", "process"]}}],
            # [{"LOWER": {"IN": ["excel", "gmail", "email"]}}],
        ],
        "tagging": [
            # [{"LOWER": {"IN": ["suggest", "recommendations", "categories"]}}],
            # [{"LOWER": "suggest"}, {"LOWER": "tags"}, {"LOWER": "for"}, {"LOWER": {"IN": ["story", "article"]}}],
        ],
        "document_qa": [
            # [{"LOWER": {"IN": ["policy", "guide", "procedure", "employee", "document", "search", "find", "qa", "question", "answer"]}}],
            # [{"LOWER": "what"}, {"LOWER": "is"}, {"LOWER": "our"}],
        ],
    }

    VALID_INTENTS = _VALID_INTENTS

    _nlp = None

    @classmethod
    def _get_nlp(cls):
        if cls._nlp is None:
            cls._nlp = spacy.load("en_core_web_md")
        return cls._nlp

    @staticmethod
    async def simple(message: str) -> str:
        """Classify intent using spaCy keyword/pattern matching.

        Returns the matched intent label, or 'unknown' if no pattern matches.
        """
        nlp = IntentClassifier._get_nlp()
        matcher = Matcher(nlp.vocab)
        doc = nlp(message)

        for label, pattern_list in IntentClassifier.INTENT_KEYWORDS.items():
            matcher.add(label, pattern_list)

        matches = matcher(doc)
        entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]

        if not matches:
            return "unknown"

        match_id, start, end = matches[0]
        intent_label = nlp.vocab.strings[match_id]
        confidence = 0.8 if entities else 0.6
        logger.debug(
            "spaCy intent classification",
            intent=intent_label,
            confidence=confidence,
            entities=entities,
        )
        return intent_label

    @staticmethod
    async def complex(message: str) -> str:
        """Classify intent using the Agent SDK (gpt-4o-mini).

        Used as fallback when spaCy pattern matching returns 'unknown'.
        Imported lazily to avoid circular imports at module load time.
        """
        # Late import: classify_agent lives in app.agents which imports orchestrator
        from app.agents.classify_agent import classify_agent  # noqa: PLC0415
        from agents import Runner  # noqa: PLC0415

        try:
            result = await Runner.run(classify_agent, message)
            intent = result.final_output.strip().lower()

            if intent not in IntentClassifier.VALID_INTENTS:
                logger.warning("Agent returned unknown intent, using 'unknown'", intent=intent)
                intent = "unknown"

            logger.debug("Agent intent classification", intent=intent)
            return intent

        except Exception as e:
            logger.error("Agent intent classification failed, using 'unknown'", error=str(e))
            return "unknown"

    @staticmethod
    async def classify(message: str) -> str:
        """Classify intent: spaCy first, Agent SDK fallback if result is 'unknown'.

        Args:
            message: User message text.

        Returns:
            Intent string (one of VALID_INTENTS, or 'unknown').
        """
        intent = await IntentClassifier.simple(message.lower())
        logger.debug(f"spaCy returned '{intent}', escalating to agent classifier")
        if intent == "unknown":
            intent = await IntentClassifier.complex(message)

        logger.debug("Final intent is", intent=intent)
        return intent
