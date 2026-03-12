import spacy
from spacy.matcher import Matcher

from app.logging import get_logger
from app.providers.base import Message
from app.providers.openai_provider import OpenAIProvider


logger = get_logger(__name__)

class IntentClassifier:
    """Simple intent classifier based on keywords."""


    INTENT_KEYWORDS = {
        "query_metrics": [
            [{"LOWER": {"IN": ["total", "sum", "average", "many", "count"]}}],
            [{"LOWER": {"IN": ["views", "likes", "shares", "interactions", "comments", "metrics"]}}],
            [{"LOWER": {"IN": ["reach", "impressions", "engagement", "followers"]}}]
        ],
        "analytics": [
            [{"LOWER": {"IN": ["tag", "recommend", "why", "trend", "peak", "worst"]}}],
            [{"LOWER": "when"}, {"LOWER": "is"}, {"LOWER": "the"}, {"LOWER": "best"}]
        ],
        "ingestion": [
            [{"LOWER": {"IN": ["ingest", "import", "upload", "process"]}}],
            [{"LOWER": {"IN": ["excel", "gmail", "email"]}}]
        ],
        "tagging": [
            [{"LOWER": {"IN": ["best", "suggest", "recommendations", "categories"]}}],
            [{"LOWER": "suggest"}, {"LOWER": "tags"}, {"LOWER": "for"}, {"LOWER": {"IN": ["story", "article"]}}]
        ],
        "document_qa": [
            [{"LOWER": {"IN": ["policy", "how", "guide", "procedure", "employee", "document", "search", "find", "qa", "question", "answer"]}}],
            [{"LOWER": "what"}, {"LOWER": "is"}, {"LOWER": "our"}]
        ]
    }

    VALID_INTENTS = list(INTENT_KEYWORDS.keys())

    _nlp = None

    @classmethod
    def _get_nlp(cls):
        if cls._nlp is None:
            cls._nlp = spacy.load("en_core_web_md")
        return cls._nlp

    @staticmethod
    async def simple(message: str) -> str:

        nlp = IntentClassifier._get_nlp()
        matcher = Matcher(nlp.vocab)
        doc = nlp(message)

        for label, pattern_list in IntentClassifier.INTENT_KEYWORDS.items():
            matcher.add(label, pattern_list)

        # 2. Extract Matches and Entities
        matches = matcher(doc)
        entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
        
        # 3. Calculate Confidence & Intent
        if not matches:
            return "general"  # No specific intent matched, fallback to general

        # Use the first match as the primary intent for this stage
        match_id, start, end = matches[0]
        intent_label = nlp.vocab.strings[match_id]
        
        # Simple heuristic for confidence: based on token coverage or entity presence
        confidence = 0.8 if entities else 0.6

        # return {
        #     "intent": intent_label,
        #     "confidence": confidence,
        #     "entities": entities,
        #     "fallback_required": confidence < confidence_threshold
        # }
        print(f"Simple intent classification result: {intent_label} with confidence {confidence:.2f} and entities {entities}")
        return intent_label
    
    @staticmethod
    async def complex(message: str) -> str:
        """Classify user message using OpenAI to determine intent.

        Args:
            message: User message text.

        Returns:
            Intent classification string.
        """
        valid_intents = ", ".join(IntentClassifier.VALID_INTENTS)
        system_prompt = (
            f"You are an intent classifier. Given a user message, respond with exactly one of "
            f"these intents and nothing else: {valid_intents}.\n"
            "Choose the intent that best matches the user's request. "
            "If none match well, respond with 'general'."
        )

        try:
            provider = OpenAIProvider()
            response = await provider.complete(
                messages=[
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=message),
                ],
                temperature=0,
                max_tokens=20,
            )
            intent = response.content.strip().lower()

            if intent not in IntentClassifier.VALID_INTENTS:
                logger.warning("OpenAI returned unknown intent, falling back to general", intent=intent)
                intent = "general"

            logger.debug("Intent classified via OpenAI", intent=intent)
            return intent

        except Exception as e:
            logger.error("OpenAI intent classification failed, falling back to general", error=str(e))
            return "general"


    # @staticmethod
    # def simple(message: str) -> str:
    #     """Classify user message to determine intent.

    #     Args:
    #         message: User message text.

    #     Returns:
    #         Intent classification string.
    #     """
    #     message_lower = message.lower()

    #     # Check each intent's keywords
    #     for intent, keywords in IntentClassifier.INTENT_KEYWORDS.items():
    #         if intent != "general":  # Skip fallback
    #             for keyword in keywords:
    #                 if keyword in message_lower:
    #                     logger.debug("Intent classified", intent=intent, keyword=keyword)
    #                     return intent

    #     # Default to general if no specific intent matched
    #     logger.debug("Intent classified as general")
    #     return "general"

    @staticmethod
    async def classify(message: str) -> str:
        """Classify user message to determine intent.

        Args:
            message: User message text.

        Returns:
            Intent classification string.
        """
        message_lower = message.lower()

        # Check each intent's keywords
        intent  = await IntentClassifier.simple(message_lower)
        if not intent:
            intent = await IntentClassifier.complex(message_lower)

        # Default to general if no specific intent matched
        logger.debug("Intent classified as general")
        return str(intent) or "general"