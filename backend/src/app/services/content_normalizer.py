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
    def _is_url_only(text: str) -> bool:
        """Check if text contains only URLs and whitespace.

        Args:
            text: Text to check

        Returns:
            True if text is only URLs/whitespace, False otherwise
        """
        if not text.strip():
            return False
        # Remove URLs and whitespace, check if anything remains
        temp = re.sub(ContentNormalizer.URL_PATTERN, '', text).strip()
        return not temp

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL by replacing special characters with dashes.

        Args:
            url: Raw URL string

        Returns:
            Normalized URL with special chars replaced by dashes

        Examples:
            >>> ContentNormalizer._normalize_url("https://t.co/ABC123")
            'https-t-co-ABC123'
        """
        # Convert to lowercase
        normalized = url.lower()
        # Replace special characters with dashes: [:?#[]@!$&'()*+,;=/ etc]
        normalized = re.sub(r'[^a-z0-9-]', '-', normalized)
        # Collapse consecutive dashes
        normalized = re.sub(r'-+', '-', normalized)
        # Strip leading/trailing dashes
        normalized = normalized.strip('-')
        return normalized

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

            >>> text = "https://t.co/ABC123"
            >>> cleaned, hash_val = ContentNormalizer.normalize(text)
            >>> cleaned
            'https-t-co-ABC123'
        """
        if not text or not isinstance(text, str):
            return ("", hashlib.sha256("".encode()).hexdigest())

        # Check if text is URL-only BEFORE cleaning
        is_url_only = ContentNormalizer._is_url_only(text)

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

        # Step 7: If result is empty but input was URL-only, normalize the URL instead
        if not cleaned and is_url_only:
            cleaned = ContentNormalizer._normalize_url(text)

        # Step 8: Truncate to 500 characters (DB VARCHAR limit)
        cleaned = cleaned[:500]

        # Step 9: Generate SHA256 hash for fast matching
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
