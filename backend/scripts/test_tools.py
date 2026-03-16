"""Quick smoke test for analytics_function_tools."""
import json
import sys
import os

# Load env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from app.tools.analytics_function_tools import (
    _list_available_data_impl,
    _query_metrics_impl,
    _get_top_content_impl,
    _get_publishing_insights_impl,
    list_available_data,
    query_metrics,
    get_top_content,
    get_publishing_insights,
)

print("All imports OK")
print("Tool types:", type(list_available_data).__name__, type(query_metrics).__name__)

print("\n--- list_available_data ---")
result = json.loads(_list_available_data_impl())
print("Files:", [f["file"] for f in result.get("files", [])])
print("Total rows:", result.get("total_rows"))
print("Platforms:", result.get("platforms"))
metrics = result.get("available_metric_columns", [])
print("Sample metrics:", metrics[:8])

print("\n--- query_metrics: video_view_count by platform ---")
result = json.loads(_query_metrics_impl("video_view_count", group_by="platform", top_n=10))
print("Total:", result.get("total"))
print("Grouped rows:")
for r in result.get("rows", []):
    print(" ", r)

print("\n--- get_top_content: top 3 by video_view_count on tiktok ---")
result = json.loads(_get_top_content_impl("video_view_count", platform="tiktok", top_n=3))
for r in result.get("results", []):
    val = r.get("video_view_count", 0)
    print(f"  #{r['rank']}  {val:,.0f}  {r['content_snippet'][:60]}")

print("\n--- get_publishing_insights: instagram video_view_count ---")
result = json.loads(_get_publishing_insights_impl("instagram", "video_view_count"))
print("Best days:", result.get("best_days"))
print("Best hours utc:", result.get("best_hours_utc"))

print("\nAll smoke tests PASSED")
