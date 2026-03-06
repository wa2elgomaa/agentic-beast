"""Embedding service for generating vector embeddings locally."""

from typing import List

from sentence_transformers import SentenceTransformer

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """Service for generating embeddings using sentence-transformers."""

    def __init__(self):
        """Initialize embedding model."""
        logger.info(
            "Loading embedding model",
            model=settings.embedding_model,
            device=settings.embedding_device,
        )
        self.model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
        logger.info("Embedding model loaded successfully")

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return []

        try:
            embedding = self.model.encode(text, convert_to_tensor=False)
            return embedding.tolist()
        except Exception as e:
            logger.error("Error generating embedding", error=str(e), text_length=len(text))
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (batch processing)."""
        if not texts:
            logger.warning("Empty text list provided for batch embedding")
            return []

        try:
            # Filter out empty texts
            valid_texts = [t for t in texts if t and t.strip()]
            if not valid_texts:
                return [[] for _ in texts]

            embeddings = self.model.encode(
                valid_texts,
                batch_size=settings.embedding_batch_size,
                convert_to_tensor=False,
            )

            # Map back to original list length, filling empty texts with empty embeddings
            result = []
            valid_idx = 0
            for text in texts:
                if text and text.strip():
                    result.append(embeddings[valid_idx].tolist())
                    valid_idx += 1
                else:
                    result.append([])

            logger.info(
                "Batch embeddings generated",
                batch_size=len(texts),
                valid_count=len(valid_texts),
            )
            return result

        except Exception as e:
            logger.error("Error generating batch embeddings", error=str(e), batch_size=len(texts))
            raise

    def cosine_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings."""
        from numpy import dot
        from numpy.linalg import norm

        if not embedding1 or not embedding2:
            return 0.0

        try:
            # Normalize vectors
            norm1 = norm(embedding1)
            norm2 = norm(embedding2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            # Calculate cosine similarity
            similarity = dot(embedding1, embedding2) / (norm1 * norm2)
            return float(similarity)

        except Exception as e:
            logger.error("Error calculating cosine similarity", error=str(e))
            return 0.0


# Global embedding service instance
_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
