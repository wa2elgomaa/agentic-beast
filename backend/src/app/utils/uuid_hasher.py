"""UUID hashing utility for deterministic deduplication identifiers.

Generates deterministic UUIDs from text using SHA256 hashing,
enabling reliable duplicate detection across multiple imports.
"""

import hashlib
import uuid
from typing import Tuple


def generate_beast_uuid(text: str, max_length: int = 150) -> Tuple[str, str]:
    """Generate deterministic beast_uuid from text.
    
    Args:
        text: Input text to hash (typically cleaned identifier)
        max_length: Number of characters to use (default: 150)
        
    Returns:
        Tuple of (hex_hash, uuid_str)
        - hex_hash: SHA256 hash as hex string (64 chars)
        - uuid_str: Hash converted to UUID format
        
    Properties:
        - Deterministic: Same input always produces same hash
        - Enables matching across multiple imports
        - First 150 chars used for hashing
    """
    if not isinstance(text, str):
        text = str(text)
    
    # Take first max_length characters
    truncated = text[:max_length]
    
    # Generate SHA256 hash
    hash_object = hashlib.sha256(truncated.encode('utf-8'))
    hex_hash = hash_object.hexdigest()  # 64-char hex string
    
    # Convert to UUID format (use first 32 hex chars)
    # Format: 8-4-4-4-12 for standard UUID
    uuid_str = str(uuid.UUID(hex=hex_hash[:32]))
    
    return hex_hash, uuid_str


def get_beast_uuid(text: str, max_length: int = 150) -> str:
    """Get beast_uuid as UUID string (convenience method).
    
    Args:
        text: Input text to hash
        max_length: Number of characters to use (default: 150)
        
    Returns:
        UUID string representation
    """
    _, uuid_str = generate_beast_uuid(text, max_length)
    return uuid_str


def get_beast_uuid_hex(text: str, max_length: int = 150) -> str:
    """Get beast_uuid as hex string (convenience method).
    
    Args:
        text: Input text to hash
        max_length: Number of characters to use (default: 150)
        
    Returns:
        SHA256 hash as hex string
    """
    hex_hash, _ = generate_beast_uuid(text, max_length)
    return hex_hash
