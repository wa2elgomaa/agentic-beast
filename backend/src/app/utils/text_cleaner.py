"""Text cleaning utility for data normalization.

Provides text cleaning functions for consistent text normalization
across all adaptors. Cleaning includes:
- Whitespace trimming
- Lowercase conversion
- Special character removal
- Unicode normalization
- Multiple space collapsing
"""

import re
import unicodedata


def clean_text(text: str) -> str:
    """Clean and normalize text for consistent processing.
    
    Args:
        text: Input text to clean
        
    Returns:
        Cleaned text ready for hashing and comparison
        
    Steps applied (in order):
        1. Trim leading/trailing whitespace
        2. Convert to lowercase
        3. Remove special characters (keep alphanumeric + spaces)
        4. Normalize unicode (NFKD)
        5. Collapse multiple spaces to single space
    """
    if not isinstance(text, str):
        text = str(text)
    
    # Step 1: Trim whitespace
    text = text.strip()
    
    # Step 2: Lowercase
    text = text.lower()
    
    # Step 3: Remove special characters (keep alphanumeric and spaces)
    # Keep only: a-z, 0-9, and spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # Step 4: Unicode normalization (NFKD)
    text = unicodedata.normalize('NFKD', text)
    
    # Step 5: Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def clean_and_truncate(text: str, max_length: int = 150) -> str:
    """Clean text and truncate to specified length.
    
    Args:
        text: Input text to clean
        max_length: Maximum length of output (default: 150 chars)
        
    Returns:
        Cleaned and truncated text
    """
    cleaned = clean_text(text)
    return cleaned[:max_length]
