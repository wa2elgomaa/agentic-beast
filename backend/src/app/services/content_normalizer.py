"""Content normalization and cleaning for deduplication matching.

This service provides utilities to normalize and clean content text by removing:
- URLs (http://, https://, www.)
- HTML tags and entities
- Special characters (keeping only alphanumeric + spaces)
- Extra whitespace

The cleaned content is used to generate a hash for fast matching across platforms.
"""

import hashlib
import re
from typing import Tuple


class ContentNormalizer:
    """Normalize content for deduplication and cross-platform matching."""

    # Regex patterns for cleaning
    URL_PATTERN = r'https?://\S+|www\.\S+'
    HTML_TAG_PATTERN = r'<[^>]+>'
    SPECIAL_CHAR_PATTERN = r'[^a-z0-9\s]'

    @staticmethod
    def normalize(text: str) -> Tuple[str, str]:
        """Clean content value and generate hash for matching.

        Args:
            text: Raw content text to normalize (e.g., post content, title, etc.)

        Returns:
            Tuple of (cleaned_text, hash_value)
            - cleaned_text: String with URLs, HTML, special chars removed, lowercase, 500 char limit
            - hash_value: SHA256 hash of cleaned text for O(1) lookup

        Examples:
            >>> text = "Check out my viral video! https://tiktok.com/video/123 #trending"
            >>> cleaned, hash_val = ContentNormalizer.normalize(text)
            >>> cleaned
            'check out my viral video trending'
            >>> len(hash_val)
            64

            >>> text = "<p>Post content here...!!!</p>"
            >>> cleaned, hash_val = ContentNormalizer.normalize(text)
            >>> cleaned
            'post content here'
        """
        if not text or not isinstance(text, str):
            return ("", hashlib.sha256("".encode()).hexdigest())

        # Step 1: Remove URLs (http://, https://, www.*)
        cleaned = re.sub(ContentNormalizer.URL_PATTERN, '', text)

        # Step 2: Remove HTML tags
        cleaned = re.sub(ContentNormalizer.HTML_TAG_PATTERN, '', cleaned)

        # Step 3: Remove HTML entities (e.g., &nbsp;, &lt;)
        cleaned = re.sub(r'&\w+;', '', cleaned)

        # Step 4: Convert to lowercase
        cleaned = cleaned.lower()

        # Step 5: Remove special characters, keep only alphanumeric + spaces
        cleaned = re.sub(ContentNormalizer.SPECIAL_CHAR_PATTERN, '', cleaned)

        # Step 6: Normalize whitespace (collapse multiple spaces)
        cleaned = ' '.join(cleaned.split()).strip()

        # Step 7: Truncate to 500 characters (DB VARCHAR limit)
        cleaned = cleaned[:500]

        # Step 8: Generate SHA256 hash for fast matching
        hash_value = hashlib.sha256(cleaned.encode()).hexdigest()

        return (cleaned, hash_value)

    @staticmethod
    def get_hash(text: str) -> str:
        """Get just the hash without cleaned text (lighter operation).

        Args:
            text: Raw content text

        Returns:
            SHA256 hash as hex string
        """
        _, hash_value = ContentNormalizer.normalize(text)
        return hash_value

    @staticmethod
    def get_cleaned(text: str) -> str:
        """Get just cleaned text without hash.

        Args:
            text: Raw content text

        Returns:
            Cleaned text string
        """
        cleaned, _ = ContentNormalizer.normalize(text)
        return cleaned

    @staticmethod
    def is_similar(text1: str, text2: str) -> bool:
        """Quick check if two texts normalize to same content.

        Args:
            text1: First content text
            text2: Second content text

        Returns:
            True if both texts produce same hash
        """
        hash1 = ContentNormalizer.get_hash(text1)
        hash2 = ContentNormalizer.get_hash(text2)
        return hash1 == hash2


__all__ = ["ContentNormalizer"]
