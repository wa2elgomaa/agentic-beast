"""Webhook HMAC security utilities for signature verification."""

import hmac
import hashlib
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


def verify_hmac_signature(
    payload_bytes: bytes,
    signature_header: Optional[str],
    secret: str,
    header_name: str = "X-TNN-Signature"
) -> bool:
    """Verify HMAC-SHA256 signature of webhook payload.
    
    Args:
        payload_bytes: Raw webhook payload bytes.
        signature_header: Value of the X-TNN-Signature header (format: "sha256=...")
        secret: HMAC secret key (from WEBHOOK_SECRET config).
        header_name: Name of the signature header (default: X-TNN-Signature).
        
    Returns:
        True if signature is valid, False otherwise.
    """
    if not signature_header or not secret:
        logger.warning("Missing signature or secret for HMAC verification")
        return False

    # Compute expected signature: sha256=<hex>
    expected_signature = "sha256=" + hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(signature_header, expected_signature)
    
    if not is_valid:
        logger.warning("HMAC signature verification failed", header_name=header_name)
    else:
        logger.debug("HMAC signature verification successful")

    return is_valid


def generate_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for a webhook payload (for testing).
    
    Args:
        payload_bytes: Raw webhook payload bytes.
        secret: HMAC secret key.
        
    Returns:
        Signature string in format "sha256=<hex>".
    """
    return "sha256=" + hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
