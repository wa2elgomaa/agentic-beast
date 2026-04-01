#!/usr/bin/env python3
"""Full API verification: all 3 intents + 7 analytics sub-queries.

Usage:
    python3 verify_api.py
"""
import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000/api/v1/chat"
TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiI2MjVjYTBjZi01NjQ1LTRlZDAtODlkYi0xYTE5MjMzNjA0ZGEiLCJ1c2VybmFtZSI6ImFkbWluIiwiZXhwIjoxNzc1MTA5MTc2LCJpYXQiOjE3NzUwMjI3NzZ9"
    ".XiDpnEEhsTjnuTRKt2Z1ioD7Vym2g7mOaMV8JHwrw2c"
)

TESTS = [
    # (label, message, expected_operation_or_query_type_substring)
    # ── analytics ──────────────────────────────────────────────────────────────
    ("ANALYTICS-1 top_n",              "top 5 videos by views",                                    "metrics"),
    ("ANALYTICS-2 top_n+platform",     "What are the top 5 TikTok videos by video views?",         "metrics"),
    ("ANALYTICS-3 top_n+keyword",      "Give me top 3 videos featuring Donald Trump",              "metrics"),
    ("ANALYTICS-4 publishing_insights","When is the best day to post on Instagram?",               "publishing_insights"),
    ("ANALYTICS-5 compare",            "Compare organic reach on Instagram and TikTok",            "compare"),
    ("ANALYTICS-6 aggregate_sum",      "What was the total organic reach last month?",             "metrics"),
    ("ANALYTICS-7 best_week",          "What are the best days to publish during the week?",       "publishing_insights"),
    # ── tag_suggestions ────────────────────────────────────────────────────────
    ("TAG-1 suggestions",              "Suggest tags for an article about AI regulation and policy", None),
    # ── article_recommendations ────────────────────────────────────────────────
    ("DOCS-1 recommendations",         "Recommend articles related to social media strategy",       None),
]


def chat(message: str) -> dict:
    body = json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        BASE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main():
    passed = 0
    failed = 0

    for label, message, expected_type in TESTS:
        print(f"\n{'─'*60}")
        print(f"[{label}]")
        print(f"  Q: {message}")
        try:
            resp = chat(message)

            # The API wraps the result in data.operation_data or data.analytics_content
            op_data = resp.get("data", {})
            analytics = (
                op_data.get("analytics_content")
                or op_data.get("operation_data")
                or op_data
            )

            query_type  = analytics.get("query_type",        op_data.get("query_type", "—"))
            rows        = analytics.get("result_data",       op_data.get("result_data", []))
            summary     = analytics.get("insight_summary",   op_data.get("insight_summary", ""))
            verification= analytics.get("verification",      "")

            print(f"  query_type  : {query_type}")
            print(f"  rows        : {len(rows)}")
            print(f"  summary     : {str(summary)[:120]}")
            if verification:
                print(f"  verification: {verification[:80]}")

            # Print first 2 result rows for visibility
            for row in rows[:2]:
                print(f"    → {row}")

            # Check pass condition
            ok = True
            if expected_type and expected_type not in str(query_type):
                print(f"  ⚠  Expected query_type to contain '{expected_type}', got '{query_type}'")
                ok = False
            if query_type == "error":
                print(f"  ✗  FAILED — query_type=error")
                ok = False

            if ok:
                print(f"  ✓  PASSED")
                passed += 1
            else:
                failed += 1

        except Exception as exc:
            print(f"  ✗  EXCEPTION: {exc}")
            failed += 1

    print(f"\n{'═'*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TESTS)} tests")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
