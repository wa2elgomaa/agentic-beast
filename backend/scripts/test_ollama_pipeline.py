"""Manual smoke-test for the anti-hallucination pipeline.

Tests:
  1. Ollama intent classification (JSON mode)
  2. parse_query() → StructuredQueryObject  (3 different queries)
  3. Full run_analytics_query() for those 3 queries
     — SQLAlchemy echo=True so the generated SQL is printed to stdout

Usage:
    cd backend
    DATABASE_ECHO=true python scripts/test_ollama_pipeline.py

Requires:
  - PostgreSQL running locally (DATABASE_URL in .env)
  - Ollama running locally on port 11434  (ollama serve)
  - deepseek-coder model pulled         (ollama pull deepseek-coder)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap

# ---------------------------------------------------------------------------
# Path & env setup — must happen BEFORE any app imports
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Force SQLAlchemy to echo SQL
os.environ["DATABASE_ECHO"] = "true"

# Fix empty OLLAMA_BASE_URL from .env — fall back to localhost
if not os.environ.get("OLLAMA_BASE_URL", "").strip():
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

import httpx

# ---------------------------------------------------------------------------
# Configure logging so SQLAlchemy echo goes to stdout
# ---------------------------------------------------------------------------
import logging
import sys as _sys

logging.basicConfig(
    stream=_sys.stdout,
    level=logging.INFO,
    format="[SQL] %(message)s",
)
# Suppress noisy loggers; only show SQLAlchemy engine statements
for _noisy in ("app", "strands", "httpx", "httpcore", "asyncio"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = os.environ["OLLAMA_BASE_URL"]
# Read model from env (already set by .env loader above)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-coder")

DIVIDER = "\n" + "=" * 70 + "\n"
SUBDIV  = "\n" + "-" * 50 + "\n"

def header(title: str) -> None:
    print(DIVIDER + f"  {title}" + DIVIDER)

def sub(title: str) -> None:
    print(SUBDIV + f"  {title}" + SUBDIV)


# ---------------------------------------------------------------------------
# Test 1 — Raw Ollama intent classification (JSON mode)
# ---------------------------------------------------------------------------

VALID_INTENTS = [
    "query_metrics", "analytics", "publishing_insights",
    "ingestion", "tagging", "document_qa", "unknown",
]

async def test_intent_classification() -> None:
    header("TEST 1 — Ollama Intent Classification (JSON mode)")
    print("  NOTE: deepseek-coder:latest here is 1B — too small for instruction-following.")
    print("  Using mistral:latest (7B) for intent, which is what should be used in production.")

    test_messages = [
        "What are the top 5 videos by views this month?",
        "Show me total organic reach on Instagram last week",
        "Which day is best to post on LinkedIn?",
    ]

    url = f"{OLLAMA_BASE_URL}/api/chat"
    valid_str = ", ".join(VALID_INTENTS)

    for msg in test_messages:
        print(f"\n  >>> Input:  {msg}")
        payload = {
            "model": "mistral",
            "format": "json",
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an intent classifier. "
                        "Output ONLY a valid JSON object — no markdown, no explanation.\n"
                        f"Valid intent values: {valid_str}\n"
                        'Output format: {"intent": "<one of the valid values>"}'
                    ),
                },
                {"role": "user", "content": msg},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            raw = data.get("message", {}).get("content", "{}")
            parsed = json.loads(raw)
            intent = parsed.get("intent", "MISSING").strip().lower()
            valid = "✅" if intent in VALID_INTENTS else "❌"
            print(f"      Raw JSON : {raw.strip()}")
            print(f"      Intent   : {intent}  {valid}")
        except Exception as exc:
            print(f"      ERROR: {exc}")


# ---------------------------------------------------------------------------
# Test 2 — parse_query() → StructuredQueryObject
# ---------------------------------------------------------------------------

ANALYTICS_QUERIES = [
    "What are the top 5 videos by video views?",
    "Show me total organic reach grouped by platform last month",
    "Average engagement rate for Instagram posts in February 2026",
]

async def test_parse_query() -> None:
    header("TEST 2 — parse_query() → StructuredQueryObject")

    from app.nlp.intent_parser import parse_query, UnsupportedQueryError

    for i, query in enumerate(ANALYTICS_QUERIES, 1):
        sub(f"Query {i}: {query}")
        try:
            sqo = await parse_query(query)
            print(textwrap.dedent(f"""\
                metric        : {sqo.metric}
                operation     : {sqo.operation}
                group_by      : {sqo.group_by}
                filters       : {sqo.filters}
                time_window   : {sqo.time_window}
                top_n         : {sqo.top_n}
            """))
        except UnsupportedQueryError as exc:
            print(f"  UnsupportedQueryError: {exc}")
        except Exception as exc:
            print(f"  ERROR: {exc}")


# ---------------------------------------------------------------------------
# Test 3 — run_analytics_query() with SQLAlchemy echo
# ---------------------------------------------------------------------------

async def test_run_analytics_query() -> None:
    header("TEST 3 — run_analytics_query() (SQLAlchemy echo=True shows SQL)")

    # Stub out spaCy so orchestrator/__init__ chain doesn't blow up
    import types
    spacy_stub = types.ModuleType("spacy")
    spacy_stub.Vocab = object
    spacy_stub.load = lambda *a, **kw: None
    spacy_stub.blank = lambda *a, **kw: None
    spacy_stub.util = types.ModuleType("spacy.util")
    spacy_stub.util.is_package = lambda *a: False
    spacy_stub.matcher = types.ModuleType("spacy.matcher")
    spacy_stub.matcher.Matcher = object
    sys.modules.setdefault("spacy", spacy_stub)
    sys.modules.setdefault("spacy.util", spacy_stub.util)
    sys.modules.setdefault("spacy.matcher", spacy_stub.matcher)

    from app.agents.analytics_agent import run_analytics_query  # noqa: PLC0415

    for i, query in enumerate(ANALYTICS_QUERIES, 1):
        sub(f"Query {i}: {query}")
        try:
            result = await run_analytics_query(query)
            print(f"\n  query_type        : {result.get('query_type')}")
            print(f"  resolved_subject  : {result.get('resolved_subject')}")
            print(f"  verification      : {result.get('verification')}")
            print(f"\n  insight_summary:\n    {result.get('insight_summary')}")

            rows = result.get("result_data", [])
            if rows:
                print(f"\n  result_data ({len(rows)} rows):")
                for r in rows[:5]:
                    print(f"    {r}")
                if len(rows) > 5:
                    print(f"    ... ({len(rows) - 5} more rows)")
            else:
                print("  result_data: (empty — no matching rows in DB)")
        except Exception as exc:
            import traceback
            print(f"  ERROR: {exc}")
            traceback.print_exc()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    print(f"\nOllama base URL : {OLLAMA_BASE_URL}")
    print(f"Ollama model    : {OLLAMA_MODEL}")
    print(f"Database echo   : {os.environ.get('DATABASE_ECHO')}")

    await test_intent_classification()
    await test_parse_query()
    await test_run_analytics_query()

    print(DIVIDER + "  ALL TESTS COMPLETE" + DIVIDER)


if __name__ == "__main__":
    asyncio.run(main())
