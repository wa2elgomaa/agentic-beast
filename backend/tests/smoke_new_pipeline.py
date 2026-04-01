"""Quick smoke-test for the new SQL-generation pipeline components.

Run inside the container:
    docker exec beast-app python3 tests/smoke_new_pipeline.py
"""
import sys
sys.path.insert(0, "src")

import asyncio

# ---------------------------------------------------------------------------
# 1. Static imports
# ---------------------------------------------------------------------------
from app.tools.dbquery_tool import validate_sql, SQLValidationError, execute_safe_sql
from app.agents.response_agent import build_analytics_response, build_error_response
from app.agents.analytics_agent import generate_analytics_sql, run_sql_analytics_pipeline

print("✓  All new modules imported OK")

# ---------------------------------------------------------------------------
# 2. SQL validator — static checks (no DB needed)
# ---------------------------------------------------------------------------
def test_validator():
    validate_sql("SELECT id FROM documents LIMIT 5")
    print("✓  validate_sql: valid SELECT passes")
    try:
        validate_sql("DELETE FROM documents")
        print("✗  validate_sql: should have rejected DELETE")
        sys.exit(1)
    except SQLValidationError as e:
        print(f"✓  validate_sql: DELETE rejected — {e.reason}")
    try:
        validate_sql("SELECT * FROM users")
        print("✗  validate_sql: should have rejected users table")
        sys.exit(1)
    except SQLValidationError as e:
        print(f"✓  validate_sql: users table rejected — {e.reason}")
    validate_sql(
        "SELECT platform, SUM(video_views) AS v FROM documents GROUP BY platform ORDER BY v DESC LIMIT 10"
    )
    print("✓  validate_sql: aggregate SELECT passes")

test_validator()

# ---------------------------------------------------------------------------
# 3. response_agent — grounded row mapping (sync)
# ---------------------------------------------------------------------------
def test_response_agent():
    rows = [
        {"platform": "Instagram", "metric_value": 12345.0},
        {"platform": "TikTok", "metric_value": 9876.0},
    ]
    r = build_analytics_response(rows, "compare reach", metric="organic_reach", operation="compare", query_category="compare")
    assert r["query_type"] == "compare"
    assert len(r["result_data"]) == 2
    print(f"✓  response_agent compare: {r['insight_summary'][:80]}")
    pi_rows = [
        {"day_of_week": "Friday  ", "avg_interactions": 4200.0, "sample_size": 120},
        {"day_of_week": "Monday  ", "avg_interactions": 3100.0, "sample_size": 98},
    ]
    rp = build_analytics_response(pi_rows, "best day", metric="engagements", operation="average", query_category="publishing_insights")
    assert "Friday" in rp["insight_summary"]
    print(f"✓  response_agent publishing_insights: {rp['insight_summary'][:80]}")
    err = build_error_response("timeout", attempted_sqls=["SELECT 1"])
    assert err["query_type"] == "error"
    print(f"✓  build_error_response OK")

test_response_agent()

# ---------------------------------------------------------------------------
# 4 + 5. Async tests — single event loop for all
# ---------------------------------------------------------------------------
async def async_tests():
    # 4. execute_safe_sql – live DB
    result = await execute_safe_sql(
        "SELECT platform, COUNT(*) AS cnt FROM documents GROUP BY platform ORDER BY cnt DESC LIMIT :max_rows",
        params={"max_rows": 5},
    )
    print(f"✓  execute_safe_sql: {result['row_count']} rows — sample: {result['rows'][0] if result['rows'] else 'none'}")

    # 5. Full SQL pipeline via Ollama
    result = await run_sql_analytics_pipeline("top 3 videos by views")
    print(f"✓  run_sql_analytics_pipeline: query_type={result['query_type']}, rows={len(result['result_data'])}")
    print(f"   insight: {result['insight_summary'][:100]}")
    print(f"   verification: {result['verification'][:80]}")

asyncio.run(async_tests())

print("\n=== All smoke tests passed ===")
