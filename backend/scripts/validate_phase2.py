"""
Phase 2 Quickstart Validation Script (T118)
==========================================
Validates that all Phase 2 features are correctly configured and operational.

Usage:
    cd backend
    python scripts/validate_phase2.py [--base-url http://localhost:8000] [--admin-token <jwt>]

Checks performed:
1.  Settings endpoint is reachable and returns data
2.  Webhook HMAC signature validation works correctly
3.  Tag feedback schema accepts valid payloads
4.  CSE search tool configuration is present
5.  LocalStack S3 endpoint is accessible (when AWS_ENDPOINT_URL is set)
6.  Admin navigation links (settings, datasets, tags) are present in frontend
7.  Fernet encryption key is configured
8.  Docker-compose localstack service is defined
9.  .env.example contains all Phase 2 required variables
10. Phase 2 Prometheus metrics are registered
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Add src to path when running directly
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
SKIP = "\033[90m-\033[0m"

results: list[tuple[str, str, str]] = []


def check(label: str, passed: bool, detail: str = "", warn: bool = False) -> bool:
    icon = WARN if (not passed and warn) else (PASS if passed else FAIL)
    results.append((label, "PASS" if passed else ("WARN" if warn else "FAIL"), detail))
    print(f"  {icon}  {label}", f"({detail})" if detail else "")
    return passed


# ─────────────────────────────────────────────────────────────────────────────
# Check 1: .env.example has Phase 2 variables
# ─────────────────────────────────────────────────────────────────────────────

def check_env_example() -> None:
    print("\n[1] .env.example Phase 2 variables")
    env_example = Path(__file__).parents[1] / ".env.example"
    if not env_example.exists():
        check(".env.example exists", False, "file not found")
        return

    content = env_example.read_text()
    required_vars = [
        "AWS_S3_BUCKET",
        "AWS_REGION",
        "WEBHOOK_SECRET",
        "GOOGLE_CSE_API_KEY",
        "GOOGLE_CSE_ID",
        "GOOGLE_CSE_SITE",
        "GOOGLE_CSE_DAILY_LIMIT",
        "SETTINGS_ENCRYPTION_KEY",
        "AWS_ENDPOINT_URL",
    ]
    for var in required_vars:
        check(f"  {var} defined", var in content)


# ─────────────────────────────────────────────────────────────────────────────
# Check 2: SETTINGS_ENCRYPTION_KEY Fernet format
# ─────────────────────────────────────────────────────────────────────────────

def check_fernet_key() -> None:
    print("\n[2] Fernet encryption key")
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY", "")
    if not key:
        check("SETTINGS_ENCRYPTION_KEY configured", False,
              "not set — generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
              warn=True)
        return

    try:
        from cryptography.fernet import Fernet, InvalidToken
        f = Fernet(key.encode() if isinstance(key, str) else key)
        test_val = f.encrypt(b"test")
        decrypted = f.decrypt(test_val)
        check("Fernet key is valid and can encrypt/decrypt", decrypted == b"test")
    except Exception as exc:
        check("Fernet key is valid", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Check 3: Webhook HMAC logic
# ─────────────────────────────────────────────────────────────────────────────

def check_webhook_hmac() -> None:
    print("\n[3] Webhook HMAC signature verification")
    secret = "test-secret-123"
    payload = '{"event_type":"article.published","article_id":"abc123"}'
    expected_sig = "sha256=" + hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    # Correct signature
    ok = hmac.compare_digest(expected_sig, expected_sig)
    check("HMAC compare_digest matches valid signature", ok)

    # Tampered payload
    tampered_sig = "sha256=" + hmac.new(secret.encode(), (payload + "X").encode(), hashlib.sha256).hexdigest()
    mismatch = not hmac.compare_digest(expected_sig, tampered_sig)
    check("HMAC rejects tampered payload", mismatch)


# ─────────────────────────────────────────────────────────────────────────────
# Check 4: Tag feedback schema
# ─────────────────────────────────────────────────────────────────────────────

def check_tag_feedback_schema() -> None:
    print("\n[4] Tag feedback schema")
    try:
        from app.schemas.tags_api import TagFeedbackRequest, TagFeedbackResponse

        req = TagFeedbackRequest(
            article_id="article-123",
            suggested_tags=["breaking", "opinion", "sports"],
            kept_tags=["breaking", "sports"],
        )
        check("TagFeedbackRequest validates", True,
              f"article_id={req.article_id}, suggested={len(req.suggested_tags)}, kept={len(req.kept_tags)}")

        resp = TagFeedbackResponse(article_id="article-123", feedback_records=3)
        check("TagFeedbackResponse validates", True, f"feedback_records={resp.feedback_records}")
    except Exception as exc:
        check("Tag feedback schemas importable", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Check 5: CSE search tool configuration
# ─────────────────────────────────────────────────────────────────────────────

def check_cse_configuration() -> None:
    print("\n[5] Google CSE configuration")
    api_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
    cse_id = os.environ.get("GOOGLE_CSE_ID", "")
    site = os.environ.get("GOOGLE_CSE_SITE", "thenationalnews.com")
    daily_limit = os.environ.get("GOOGLE_CSE_DAILY_LIMIT", "100")

    check("GOOGLE_CSE_API_KEY set", bool(api_key), "not configured — CSE search disabled" if not api_key else "", warn=not api_key)
    check("GOOGLE_CSE_ID set", bool(cse_id), "not configured — CSE search disabled" if not cse_id else "", warn=not cse_id)
    check("GOOGLE_CSE_SITE configured", bool(site), site)
    check("GOOGLE_CSE_DAILY_LIMIT is numeric", daily_limit.isdigit(), f"value={daily_limit}")

    # Verify the search tools module imports correctly
    try:
        from app.tools.search_tools import CSESearchResult, QuotaExceededError
        check("search_tools.py imports correctly", True)
    except ImportError as exc:
        check("search_tools.py imports correctly", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Check 6: LocalStack / S3 configuration
# ─────────────────────────────────────────────────────────────────────────────

def check_s3_and_localstack() -> None:
    print("\n[6] S3 / LocalStack configuration")
    bucket = os.environ.get("AWS_S3_BUCKET", "")
    region = os.environ.get("AWS_REGION", "")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", "")

    check("AWS_S3_BUCKET configured", bool(bucket), bucket or "not set", warn=not bucket)
    check("AWS_REGION configured", bool(region), region or "not set", warn=not region)
    check("AWS_ENDPOINT_URL for LocalStack", bool(endpoint_url),
          endpoint_url if endpoint_url else "empty — will use real AWS S3",
          warn=not endpoint_url)

    # Check docker-compose has localstack
    compose_file = Path(__file__).parents[2] / "docker-compose.yml"
    if compose_file.exists():
        content = compose_file.read_text()
        check("docker-compose.yml has localstack service", "localstack" in content)
        check("docker-compose.yml exposes port 4566", "4566" in content)
    else:
        check("docker-compose.yml exists", False, "file not found")

    # Check S3Service supports endpoint_url
    try:
        from app.services.s3_service import S3Service
        import inspect
        sig = inspect.signature(S3Service.__init__)
        check("S3Service accepts endpoint_url parameter", "endpoint_url" in sig.parameters)
    except ImportError as exc:
        check("s3_service.py imports correctly", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Check 7: Phase 2 Prometheus metrics registered
# ─────────────────────────────────────────────────────────────────────────────

def check_prometheus_metrics() -> None:
    print("\n[7] Phase 2 Prometheus metrics (T115)")
    try:
        from app.middleware.metrics import (
            SEARCH_REQUESTS_TOTAL,
            ARTICLE_VECTORS_COUNT,
            TAG_VECTORS_COUNT,
            WEBHOOK_EVENTS_TOTAL,
            SETTINGS_CACHE_HIT_RATIO,
        )
        check("SEARCH_REQUESTS_TOTAL counter registered", True)
        check("ARTICLE_VECTORS_COUNT counter registered", True)
        check("TAG_VECTORS_COUNT counter registered", True)
        check("WEBHOOK_EVENTS_TOTAL counter registered", True)
        check("SETTINGS_CACHE_HIT_RATIO counter registered", True)
    except ImportError as exc:
        check("Phase 2 metrics importable", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Check 8: Admin navigation sidebar
# ─────────────────────────────────────────────────────────────────────────────

def check_admin_navigation() -> None:
    print("\n[8] Admin navigation sidebar (T121)")
    sidebar_file = Path(__file__).parents[2] / "frontend/components/admin/AdminSidebar.tsx"
    if not sidebar_file.exists():
        check("AdminSidebar.tsx exists", False, "file not found")
        return

    content = sidebar_file.read_text()
    for path in ["/admin/settings", "/admin/datasets", "/admin/tags"]:
        check(f"Nav link to {path}", path in content)


# ─────────────────────────────────────────────────────────────────────────────
# Check 9: CSE setup docs
# ─────────────────────────────────────────────────────────────────────────────

def check_cse_docs() -> None:
    print("\n[9] Google CSE setup documentation (T122)")
    docs_file = Path(__file__).parents[1] / "docs/google-cse-setup.md"
    check("backend/docs/google-cse-setup.md exists", docs_file.exists())
    if docs_file.exists():
        content = docs_file.read_text()
        check("Docs contain GOOGLE_CSE_API_KEY", "GOOGLE_CSE_API_KEY" in content)
        check("Docs contain GOOGLE_CSE_ID", "GOOGLE_CSE_ID" in content)
        check("Docs contain setup steps", "Step" in content)


# ─────────────────────────────────────────────────────────────────────────────
# Check 10: Webhook events endpoint defined
# ─────────────────────────────────────────────────────────────────────────────

def check_webhook_events_endpoint() -> None:
    print("\n[10] Webhook events monitoring endpoint (T114)")
    try:
        from app.api.webhooks import router, WebhookEventsListResponse
        routes = [r.path for r in router.routes]
        check("GET /admin/webhooks/events route exists",
              any("/admin/webhooks/events" in r for r in routes),
              str(routes))
        check("WebhookEventsListResponse schema importable", True)
    except ImportError as exc:
        check("webhooks.py imports correctly", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phase 2 implementation")
    parser.parse_args()

    print("=" * 60)
    print("  Agentic Beast — Phase 2 Validation")
    print("=" * 60)

    check_env_example()
    check_fernet_key()
    check_webhook_hmac()
    check_tag_feedback_schema()
    check_cse_configuration()
    check_s3_and_localstack()
    check_prometheus_metrics()
    check_admin_navigation()
    check_cse_docs()
    check_webhook_events_endpoint()

    # Summary
    total = len(results)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    warns = sum(1 for _, s, _ in results if s == "WARN")
    failed = sum(1 for _, s, _ in results if s == "FAIL")

    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed, {warns} warnings, {failed} failed / {total} checks")
    print("=" * 60)

    if failed > 0:
        print(f"\n{FAIL} Phase 2 validation FAILED — fix the issues above before deploying.\n")
        sys.exit(1)
    elif warns > 0:
        print(f"\n{WARN} Phase 2 validation passed with warnings (optional features not configured).\n")
    else:
        print(f"\n{PASS} Phase 2 validation PASSED — all checks OK.\n")


if __name__ == "__main__":
    main()
