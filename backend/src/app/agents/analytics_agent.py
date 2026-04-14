"""Analytics agent backed by Strands.

Primary pipeline (new):
    run_sql_analytics_pipeline
        → generate_analytics_sql   (Ollama / deepseek-coder → {sql, params})
        → execute_safe_sql         (dbquery_tool — readonly, validated, parameterized)
        → build_analytics_response (response_agent — grounded narrative)
    Retries SQL generation up to MAX_SQL_RETRIES times on failure.

Fallback pipeline (existing):
    run_analytics_query → parse_query (StructuredQueryObject) → pre-built _impl tools
"""

import json
import logging
import re
from typing import Any, Optional

_logger = logging.getLogger(__name__)

from app.config import settings
from app.agents.response_agent import _format_number, _build_view_url, _safe_str  # noqa: E402
from app.utilities.json_chat import generate_json_object

from pydantic import BaseModel, field_validator


class AnalyticsAgentSchema__ResultDataItem(BaseModel):
  label: str
  value: str
  platform: Optional[str] = None
  content: Optional[str] = None
  title: Optional[str] = None
  published_at: Optional[str] = None

  @field_validator("content", mode="before")
  @classmethod
  def validate_content(cls, value: object) -> str:
    return _sanitize_output_text(value, max_len=480)

  @field_validator("title", mode="before")
  @classmethod
  def validate_title(cls, value: object) -> str:
    return _sanitize_output_text(value, max_len=240)


def _sanitize_output_text(value: object, max_len: int) -> str:
  if value is None:
    return ""

  normalized = str(value).replace("\r", " ").replace("\n", " ")
  normalized = "".join(ch for ch in normalized if ch.isprintable() or ch.isspace())
  normalized = " ".join(normalized.split())

  if len(normalized) <= max_len:
    return normalized
  return normalized[:max_len].rstrip()


class AnalyticsAgentSchema(BaseModel):
  query_type: str
  resolved_subject: str
  result_data: list[AnalyticsAgentSchema__ResultDataItem]
  insight_summary: str
  verification: str


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def get_strands_analytics_agent(selected_model: Optional[str] = None):
    """Return a Strands Agent for analytics queries with SQL-backed tools.

    Args:
        selected_model: Optional model identifier override.
    """
    from strands import Agent  # noqa: PLC0415
    from app.agents.agent_factory import get_model_provider  # noqa: PLC0415
    from app.tools.analytics_db_function_tools import (  # noqa: PLC0415
        list_available_data_db,
        query_metrics_db,
        get_top_content_db,
        get_publishing_insights_db,
    )

    model = get_model_provider(selected_model)

    system_prompt = ("""
        ### ROLE
          You are the Lead Data Intelligence Agent for the "Beast" Analytics Platform. Your sole purpose is to translate natural language into a VALID Structured Query Object for a Safe Executor. You are a logical engine, not a creative writer.

          ### DATA DICTIONARY (init.sql Schema)
          You MUST only use the following whitelisted columns from the `documents` table:
          - **Metrics**: `organic_interactions`, `total_interactions`, `total_reactions`, `total_comments`, `total_shares`, `engagements`, `total_reach`, `paid_reach`, `organic_reach`, `total_impressions`, `paid_impressions`, `organic_impressions`, `reach_engagement_rate`, `total_likes`, `video_views`, `total_video_view_time_sec`.
          - **Dimensions**: `platform`, `content_type`, `media_type`, `origin_of_the_content`, `profile_name`, `author_name`, `published_date`, `labels`.

          ### CRITICAL CONSTRAINTS
          1. **No Hallucinations**: If a user asks for a metric not listed above (e.g., "revenue"), return an error JSON: `{"error": "Unsupported metric"}`.
          2. **Deterministic Output**: You must ONLY output a JSON object. No conversational filler like "Sure, here is your query".
          3. **Time Formatting**: All dates must be in ISO 8601 format (YYYY-MM-DD).
          4. **Operation Mapping**: Map "average" to `average`, "sum" to `sum`, and "count" to `count`. Use `top_n` for ranking requests.

          ### OUTPUT SCHEMA
          Your output must strictly follow this JSON structure:
          {
            "metric": "string",
            "operation": "sum | average | max | min | top_n | count",
            "group_by": "string | null",
            "filters": {
              "column_name": "value" | {"from": "date", "to": "date"}
            },
            "time_window": {"from": "date", "to": "date"},
            "top_n": integer | null
          }

          ### FEW-SHOT EXAMPLES

          **User**: "What was the total organic reach on Instagram last month?"
          **Assistant**: 
          {
            "metric": "organic_reach",
            "operation": "sum",
            "group_by": null,
            "filters": {"platform": "Instagram"},
            "time_window": {"from": "2026-02-01", "to": "2026-02-28"},
            "top_n": null
          }

          **User**: "Show me the top 5 videos by view count."
          **Assistant**:
          {
            "metric": "video_views",
            "operation": "top_n",
            "group_by": null,
            "filters": {"content_type": "video"},
            "time_window": null,
            "top_n": 5
          }

          **User**: "Average engagement rate for LinkedIn posts tagged 'Product'?"
          **Assistant**:
          {
            "metric": "reach_engagement_rate",
            "operation": "average",
            "group_by": null,
            "filters": {"platform": "LinkedIn", "labels": "Product"},
            "time_window": null,
            "top_n": null
          }
          """
    )

    return Agent(
        name="AnalyticsAgent",
        model=model,
        tools=[
            list_available_data_db,
            query_metrics_db,
            get_top_content_db,
            get_publishing_insights_db,
        ],
        system_prompt=system_prompt,
        callback_handler=None,
    )


# ---------------------------------------------------------------------------
# Pre-execution analytics: parse → SQL → format (no LLM-generated numbers)
# ---------------------------------------------------------------------------

def _build_insight_summary(
    metric: str | None,
    operation: str,
    rows: list[dict],
    query_category: str = "metrics",
) -> str:
    """Build a grounded summary string using only real DB values."""
    if not rows:
        subject = metric or "publishing insights"
        return f"No data found for '{subject}'."

    # Publishing insights: rows have day_of_week + avg_interactions
    if query_category == "publishing_insights" or "day_of_week" in rows[0]:
        platform_label = rows[0].get("platform", "all platforms") if len(rows) > 0 else "all platforms"
        lines = []
        for r in rows[:7]:
            day = (r.get("day_of_week") or "?").strip()
            avg = r.get("avg_interactions", 0)
            sample = r.get("sample_size", 0)
            lines.append(f"  {day}: avg {avg:,.0f} interactions ({sample} posts)")
        return "Best days to publish:\n" + "\n".join(lines)

    metric_label = (metric or "value").replace("_", " ").title()

    def _row_metric_value(row: dict) -> float:
        raw = row.get("value", row.get("metric_value", 0))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    if operation == "top_n":
        lines = []
        for i, r in enumerate(rows[:10], start=1):
            name = r.get("title") or r.get("beast_uuid") or r.get("content_id") or "Unknown"
            val = _row_metric_value(r)
            platform = r.get("platform", "")
            suffix = f" ({platform})" if platform else ""
            lines.append(f"{i}. {name}{suffix}: {val:,.0f}")
        return f"Top {len(rows)} by {metric_label}:\n" + "\n".join(lines)

    # Compare / grouped by platform
    if query_category == "compare" or (rows and "platform" in rows[0]):
        lines = []
        for r in rows:
            plat = r.get("platform") or r.get(
                next((k for k in r if k not in ("value",)), "group"), "?")
            val = _row_metric_value(r)
            lines.append(f"  {plat}: {val:,.0f}")
        return f"{metric_label} by platform:\n" + "\n".join(lines)

    if len(rows) == 1:
        val = _row_metric_value(rows[0])
        return f"Total {metric_label}: {val:,.0f}"

    total = sum(_row_metric_value(r) for r in rows)
    top = max(rows, key=_row_metric_value)
    top_label = next(
        (
            str(top.get(k, ""))
            for k in ("platform", "media_type", "content_type", "published_date")
            if top.get(k)
        ),
        "Unknown",
    )
    return (
        f"{metric_label} summary ({len(rows)} groups): "
        f"Total={total:,.0f}, Highest={_row_metric_value(top):,.0f} ({top_label})"
    )


def _rows_to_result_data(rows: list[dict], query_category: str = "metrics") -> list[dict]:
    """Normalise DB rows to the AnalyticsAgentSchema__ResultDataItem shape."""
    result = []
    for r in rows:
        if query_category == "publishing_insights":
            label = (r.get("day_of_week") or "Unknown").strip()
            result.append({
                "label": label,
                "value": str(round(r.get("avg_interactions", 0))),
                "platform": r.get("platform"),
                "content": str(r.get("sample_size", "")),
                "title": None,
            })
        else:
            label = (
                r.get("title")
                or r.get("platform")
                or r.get("published_date")
                or r.get("content_type")
                or r.get("media_type")
                or r.get("beast_uuid")
                or r.get("content_id")
                or "Unknown"
            )

            # Build canonical fields: title from title then content; description from content column
            raw_title = (r.get("title") or "").strip()
            if raw_title:
                title_field = _safe_str(raw_title)
            else:
                title_field = _safe_str(r.get("content") or "")

            content_field = _safe_str(r.get("content") or "")
            view_url = _build_view_url(_safe_str(r.get("platform")), r.get("content_id"))
            formatted_value = _format_number(r.get("value", r.get("metric_value", 0)))

            result.append(
                {
                    "label": str(label),
                    "value": formatted_value,
                    "platform": r.get("platform"),
                    "content": content_field,
                    "title": title_field,
                    "view_url": view_url,
                }
            )
    return result


_TOP_N_RE = re.compile(r"\btop\s+(\d+)\b|\bgive\s+me\s+(\d+)\b|\bshow\s+(?:me\s+)?(\d+)\b", re.IGNORECASE)
_KEYWORD_RE = re.compile(
    r"\bfeaturing\s+(.+?)(?:\s+(?:last|this|in|on|during|from|between|$)|\s*$)"
    r"|\babout\s+(.+?)(?:\s+(?:last|this|in|on|during|from|between|$)|\s*$)"
    r"|\brelated\s+to\s+(.+?)(?:\s+(?:last|this|in|on|during|from|between|$)|\s*$)",
    re.IGNORECASE,
)


def _post_process_sqo(sqo, message: str):
    """Override parsed SQO fields where simple regex is more reliable than the LLM."""
    # Top-N: if message clearly says "top N" / "give me N" / "show N"
    m = _TOP_N_RE.search(message)
    if m:
        n = int(next(g for g in m.groups() if g))
        sqo.operation = "top_n"
        sqo.top_n = n

    # Keyword: if message uses "featuring X", "about X", "related to X"
    if sqo.keyword is None:
        km = _KEYWORD_RE.search(message)
        if km:
            sqo.keyword = next((g.strip() for g in km.groups() if g), None)

    return sqo


async def run_analytics_query(
    message: str,
    selected_model: Optional[str] = None,  # noqa: ARG001 — kept for API compat
    conversation_history: list[dict] | None = None,
) -> dict:
    """Pre-execution analytics pipeline.

    1. Parse the user query → StructuredQueryObject via Ollama JSON mode.
    2. Route to the correct SQL _impl based on query_category.
    3. Build a grounded response — the LLM never generates numbers.
    """
    import json  # noqa: PLC0415

    from app.nlp.intent_parser import UnsupportedQueryError, parse_query  # noqa: PLC0415
    from app.tools.analytics_db_function_tools import (  # noqa: PLC0415
        get_publishing_insights_db_impl,
        get_top_content_db_impl,
        query_metrics_db_impl,
    )

    # ------------------------------------------------------------------
    # Step 1: structured parse
    # ------------------------------------------------------------------
    try:
        sqo = await parse_query(message, conversation_history=conversation_history)
    except UnsupportedQueryError as exc:
        return {
            "query_type": "error",
            "resolved_subject": "parse_error",
            "result_data": [],
            "insight_summary": "Could not parse your query. Please rephrase.",
            "verification": str(exc),
        }

    # Apply regex overrides for fields where Mistral is inconsistent
    sqo = _post_process_sqo(sqo, message)
    _logger.info("Parsed Structured Query Object", extra=sqo.dict())
    
    _logger.info(
        f"run_analytics_query: parsed SQO : {sqo.metric}",
        extra={
            "query_category": sqo.query_category,
            "metric": sqo.metric,
            "operation": sqo.operation,
            "group_by": sqo.group_by,
            "filters": sqo.filters,
            "time_window": sqo.time_window,
            "top_n": sqo.top_n,
            "keyword": sqo.keyword,
        },
    )

    time_from = (sqo.time_window or {}).get("from")
    time_to = (sqo.time_window or {}).get("to")
    platform_filter = sqo.filters.get("platform")

    # ------------------------------------------------------------------
    # Step 2: route by query_category
    # ------------------------------------------------------------------

    # --- Publishing insights (best day/time to post) ---
    if sqo.query_category == "publishing_insights":
        raw = await get_publishing_insights_db_impl(
            platform=platform_filter,
            days=90,
        )
        try:
            db_result = json.loads(raw)
        except json.JSONDecodeError:
            db_result = {"rows": []}
        rows = db_result.get("rows", [])
        insight = _build_insight_summary(None, "publishing_insights", rows, query_category="publishing_insights")
        return {
            "query_type": "publishing_insights",
            "resolved_subject": f"best_posting_time{'_' + platform_filter if platform_filter else ''}",
            "result_data": _rows_to_result_data(rows, query_category="publishing_insights"),
            "raw_rows": rows[:100],
            "metric": None,
            "insight_summary": insight,
            "verification": "Values sourced directly from PostgreSQL — no LLM-generated numbers.",
        }

    # --- Metric required for all remaining paths ---
    if sqo.metric is None:
        return {
            "query_type": "error",
            "resolved_subject": "unsupported_metric",
            "result_data": [],
            "insight_summary": (
                "The metric you requested is not in the analytics schema. "
                f"Available metrics include: {', '.join(sorted(['video_views', 'total_reach', 'organic_reach', 'total_interactions', 'engagements']))} and more."
            ),
            "verification": "Metric not in whitelist.",
        }

    # --- Compare (group by platform, no single-platform filter) ---
    if sqo.query_category == "compare" or sqo.operation == "compare":
        raw = await query_metrics_db_impl(
            metric=sqo.metric,
            aggregation="sum",
            platform=None,
            start_date=time_from,
            end_date=time_to,
            group_by="platform",
            limit=settings.db_default_limit,
        )
        try:
            db_result = json.loads(raw)
        except json.JSONDecodeError:
            db_result = {"rows": []}
        rows = db_result.get("rows", [])
        insight = _build_insight_summary(sqo.metric, "compare", rows, query_category="compare")
        return {
            "query_type": "compare",
            "resolved_subject": sqo.metric,
            "result_data": _rows_to_result_data(rows, query_category="compare"),
            "raw_rows": rows[:100],
            "metric": sqo.metric,
            "insight_summary": insight,
            "verification": "Values sourced directly from PostgreSQL — no LLM-generated numbers.",
        }

    # --- Top-N (with optional keyword / platform filter) ---
    # Treat as top_n if operation is top_n OR if top_n count was explicitly set
    if sqo.operation == "top_n" or (sqo.top_n and sqo.top_n > 0):
        raw = await get_top_content_db_impl(
            metric=sqo.metric,
            platform=platform_filter,
            start_date=time_from,
            end_date=time_to,
            keyword=sqo.keyword,
            limit=sqo.top_n or 10,
        )
    else:
        raw = await query_metrics_db_impl(
            metric=sqo.metric,
            aggregation=sqo.operation,
            platform=platform_filter,
            profile_id=sqo.filters.get("profile_id"),
            start_date=time_from,
            end_date=time_to,
            group_by=sqo.group_by,
            limit=sqo.top_n or 20,
        )

    try:
        db_result = json.loads(raw)
    except json.JSONDecodeError:
        db_result = {"rows": []}

    rows = db_result.get("rows", [])
    _logger.info("run_analytics_query: DB rows", extra={"rows_count": len(rows)})

    # ------------------------------------------------------------------
    # Step 3: build grounded response (no LLM for numeric values)
    # ------------------------------------------------------------------
    insight = _build_insight_summary(sqo.metric, sqo.operation, rows, query_category=sqo.query_category)
    result_data = _rows_to_result_data(rows, query_category=sqo.query_category)

    return {
        "query_type": sqo.operation,
        "resolved_subject": sqo.metric,
        "result_data": result_data,
        "raw_rows": rows[:100],
        "metric": sqo.metric,
        "insight_summary": insight,
        "verification": "Values sourced directly from PostgreSQL — no LLM-generated numbers.",
    }


# ===========================================================================
# SQL-generation pipeline  (new primary path)
# ===========================================================================

MAX_SQL_RETRIES: int = settings.sql_generation_max_retries
"""How many times to re-ask the LLM for a corrected SQL before returning error."""

# ---------------------------------------------------------------------------
# Dynamic prompt builders (schema + intent registry driven)
# ---------------------------------------------------------------------------


def _ensure_registries_loaded() -> None:
    from app.config import get_schema_registry, initialize_registries, settings  # noqa: PLC0415

    try:
        get_schema_registry()
    except RuntimeError:
        initialize_registries(config_dir=settings.config_dir)


def _build_schema_context() -> str:
    """Build schema context dynamically from SchemaRegistry."""
    from app.config import get_schema_registry  # noqa: PLC0415

    _ensure_registries_loaded()
    schema = get_schema_registry()

    metric_lines = []
    for metric, cfg in sorted(schema.metrics.items()):
        aliases = ", ".join(cfg.get("aliases", [])[:4])
        agg = ",".join(cfg.get("aggregations", ["sum"]))
        metric_lines.append(f"- {metric} (aggs: {agg}; aliases: {aliases})")

    dimension_lines = []
    for dim, cfg in sorted(schema.dimensions.items()):
        aliases = ", ".join(cfg.get("aliases", [])[:4])
        dimension_lines.append(f"- {dim} (aliases: {aliases})")

    table_name = schema.table_name
    default_limit = schema.constraints.get("default_limit", 10)
    max_limit = schema.constraints.get("max_limit", 100)

    metrics_text = "\n".join(metric_lines)
    dimensions_text = "\n".join(dimension_lines)

    return (
        f"Table: {table_name} (PostgreSQL)\n\n"
        "Allowed metric columns (numeric, use for aggregation/ordering):\n"
        f"{metrics_text}\n\n"
        "Allowed dimension columns (use for GROUP BY / WHERE / ORDER BY):\n"
        f"{dimensions_text}\n\n"
        "Other useful columns: title (text), content (text), beast_uuid (uuid), content_id (text), "
        "published_date (date), platform (text)\n"
        "CRITICAL: When grouping (GROUP BY), EVERY non-aggregated column in SELECT must be in GROUP BY.\n"
        "Example correct query: SELECT beast_uuid, MAX(title), SUM(metric) FROM documents "
        "GROUP BY beast_uuid  (title will be aggregated automatically).\n"
        "Example INCORRECT: SELECT platform, published_date, SUM(metric) FROM documents GROUP BY platform "
        "(missing published_date in GROUP BY).\n"
        f"Default limit: {default_limit}; absolute max limit: {max_limit}."
    )


def _build_sql_gen_system_prompt() -> str:
    schema_context = _build_schema_context()
    return (
        "You are an expert PostgreSQL query generator for a social media analytics platform. "
        "Your ONLY output is a raw JSON object — no markdown, no explanation, no code fences.\n\n"
        f"{schema_context}\n\n"
        "Output schema (ALL fields required):\n"
        "{\n"
        '  "sql": "SELECT ... FROM documents WHERE ... LIMIT :max_rows",\n'
        '  "params": {"param_name": "value", ...},\n'
        '  "metric": "<metric_column_name or null>",\n'
        '  "operation": "<sum|average|max|min|top_n|count|compare>",\n'
        '  "query_category": "<metrics|publishing_insights|compare>"\n'
        "}\n\n"
        "Rules:\n"
        "1. ONLY SELECT from the documents table. Never use INSERT/UPDATE/DELETE/DROP/ALTER/CREATE.\n"
        "2. Use :param_name placeholders for ALL user-supplied filter values — NEVER interpolate strings.\n"
        "3. ALWAYS include LIMIT :max_rows in SQL and set params.max_rows.\n"
        "4. For top-N: ORDER BY metric_value DESC LIMIT :max_rows and include title/content/beast_uuid.\n"
        "5. For publishing insights, aggregate by day using published_date and engagements.\n"
        "6. For platform filter: LOWER(platform) = LOWER(:platform).\n"
        "7. For keyword filter: (title ILIKE :keyword OR content ILIKE :keyword), with %term%.\n"
        "8. For date range: published_date BETWEEN :start_date::date AND :end_date::date.\n"
        "9. For compare queries: GROUP BY platform and ORDER BY metric_value DESC.\n"
        "10. query_category must be one of metrics | publishing_insights | compare.\n"
        "11. CRITICAL GROUP BY RULE: Every non-aggregated column in SELECT must be in GROUP BY. "
        "   Aggregated columns (SUM, MAX, AVG, MIN, COUNT) do NOT go in GROUP BY.\n"
        "12. CONTEXTUAL FILTERING: When you see [PRIOR QUERY CONTEXT] with a TOP RESULT beast_uuid:\n"
        "    - If user says 'first', 'top', 'the one with most...', use WHERE beast_uuid = :top_beast_uuid\n"
        "    - Example: User says 'compare top video across platforms' → WHERE beast_uuid = :top_beast_uuid GROUP BY platform\n"
        "    - Extract the beast_uuid value from the prior context and pass it in params.\n"
        "13. Alias aggregated values as metric_value whenever practical."
    )


def _build_sql_gen_few_shot() -> list[dict[str, str]]:
    """Build few-shot examples from intent registry examples + schema defaults."""
    from app.config import get_intent_registry, get_schema_registry  # noqa: PLC0415

    _ensure_registries_loaded()
    intents = get_intent_registry()
    schema = get_schema_registry()

    metric_default = "video_views" if "video_views" in schema.metrics else next(iter(schema.metrics.keys()), "video_views")
    compare_metric = "organic_reach" if "organic_reach" in schema.metrics else metric_default

    examples = intents.get_intent_example_queries("analytics")
    top_example = examples[0] if examples else "Show me top 5 content by views"
    publishing_example = examples[1] if len(examples) > 1 else "When is the best day to post on Instagram?"
    compare_example = examples[2] if len(examples) > 2 else "Compare performance by platform"

    return [
        {"role": "user", "content": top_example},
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "sql": (
                        "SELECT beast_uuid, "
                        "MAX(NULLIF(title, '')) AS title, MAX(content) AS content, "
                        f"SUM({metric_default}) AS metric_value "
                        "FROM documents "
                        "GROUP BY beast_uuid "
                        "ORDER BY metric_value DESC LIMIT :max_rows"
                    ),
                    "params": {"max_rows": 5},
                    "metric": metric_default,
                    "operation": "top_n",
                    "query_category": "metrics",
                }
            ),
        },
        {"role": "user", "content": publishing_example},
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "sql": (
                        "SELECT TRIM(TO_CHAR(published_date, 'Day')) AS day_of_week, "
                        "AVG(COALESCE(engagements, 0)) AS avg_interactions, "
                        "COUNT(*) AS sample_size "
                        "FROM documents "
                        "WHERE LOWER(platform) = LOWER(:platform) "
                        "GROUP BY TRIM(TO_CHAR(published_date, 'Day')) "
                        "ORDER BY avg_interactions DESC LIMIT :max_rows"
                    ),
                    "params": {"platform": "Instagram", "max_rows": 7},
                    "metric": "engagements",
                    "operation": "average",
                    "query_category": "publishing_insights",
                }
            ),
        },
        {"role": "user", "content": compare_example},
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "sql": (
                        f"SELECT platform, SUM({compare_metric}) AS metric_value "
                        "FROM documents "
                        "GROUP BY platform "
                        "ORDER BY metric_value DESC LIMIT :max_rows"
                    ),
                    "params": {"max_rows": 10},
                    "metric": compare_metric,
                    "operation": "compare",
                    "query_category": "compare",
                }
            ),
        },
        # Contextual follow-up example: referencing prior results
        {
            "role": "user",
            "content": (
                "[PRIOR QUERY CONTEXT]\n"
                "The user's last analytics query used this SQL:\n"
                "SELECT beast_uuid, MAX(NULLIF(title, '')) AS title, SUM(video_views) AS metric_value "
                "FROM documents GROUP BY beast_uuid ORDER BY metric_value DESC LIMIT :max_rows\n"
                "Metric analysed: video_views\n"
                "Columns returned: beast_uuid, title, metric_value\n"
                "RESULTS (ranked by display order):\n"
                "  [1st/TOP] {\"beast_uuid\": \"11111111-1111-1111-1111-111111111111\", \"title\": \"Viral Post\", \"metric_value\": \"50000\"}\n"
                "  [2nd] {\"beast_uuid\": \"22222222-2222-2222-2222-222222222222\", \"title\": \"Trending Clip\", \"metric_value\": \"35000\"}\n"
                "  [3rd] {\"beast_uuid\": \"33333333-3333-3333-3333-333333333333\", \"title\": \"Featured Video\", \"metric_value\": \"28000\"}\n"
                "KEY REFERENCE: The TOP RESULT has beast_uuid='11111111-1111-1111-1111-111111111111'.\n"
                "When the user says 'first', 'top', or 'most...', use this beast_uuid in WHERE clause.\n"
                "Example: WHERE beast_uuid = '11111111-1111-1111-1111-111111111111' then GROUP BY platform to show across platforms.\n"
                "\n"
                "User follow-up: compare the first video on all platforms"
            ),
        },
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "sql": (
                        "SELECT platform, SUM(video_views) AS metric_value "
                        "FROM documents WHERE beast_uuid = :top_beast_uuid "
                        "GROUP BY platform ORDER BY metric_value DESC LIMIT :max_rows"
                    ),
                    "params": {"top_beast_uuid": "11111111-1111-1111-1111-111111111111", "max_rows": 10},
                    "metric": "video_views",
                    "operation": "compare",
                    "query_category": "compare",
                }
            ),
        },
    ]


# ---------------------------------------------------------------------------
# SQL generator: Ollama → {sql, params, metric, operation, query_category}
# ---------------------------------------------------------------------------

async def generate_analytics_sql(
    message: str,
    conversation_history: list[dict] | None = None,
    error_hint: str | None = None,
) -> dict[str, Any]:
    """Ask configured provider to generate a parameterized SELECT JSON object.

    Args:
        message:              User's natural-language analytics query.
        conversation_history: Prior turns for context.
        error_hint:           Previous SQL error to include as correction hint.

    Returns:
        ``{"sql": str, "params": dict, "metric": str|None,
           "operation": str, "query_category": str}``

    Raises:
        UnsupportedQueryError: If provider is unreachable or returns invalid JSON.
    """
    from app.config import settings  # noqa: PLC0415
    from app.nlp.intent_parser import UnsupportedQueryError  # noqa: PLC0415

    # Prefer dedicated SQL model by provider; fall back to provider default model.
    if settings.ai_provider in ("openai", "strands"):
        sql_model = (settings.openai_sql_model or "").strip() or settings.openai_model
    else:
        sql_model = (settings.ollama_sql_model or "").strip() or settings.ollama_model

    messages: list[dict] = [
        {"role": "system", "content": _build_sql_gen_system_prompt()},
        *_build_sql_gen_few_shot(),
    ]

    # Inject structured prior-query context for chained questions.
    # e.g. "Break them down by platform?" needs to know the previous SQL and metric.
    prior_context_block: str | None = None
    if conversation_history:
        for h in reversed(conversation_history):
            if h.get("role") == "assistant" and h.get("prior_sql"):
                prior_sql = h["prior_sql"]
                prior_metric = h.get("prior_metric", "")
                prior_rows = h.get("prior_rows", [])
                # Build a ranked, explicitly-labeled sample for contextual filtering
                col_sample = ""
                if prior_rows:
                    cols = list(prior_rows[0].keys())
                    col_sample = f"\nColumns returned: {', '.join(cols)}\n"
                    col_sample += "RESULTS (ranked by display order):\n"

                    # Format first 3 rows with explicit ranking
                    for idx, row in enumerate(prior_rows[:3], start=1):
                        row_formatted = {c: str(row.get(c, ""))[:40] for c in cols}
                        rank_label = "[1st/TOP]" if idx == 1 else f"[{idx}nd]" if idx == 2 else f"[{idx}rd]"
                        col_sample += f"  {rank_label} {json.dumps(row_formatted)}\n"

                    # Extract first result's beast_uuid for explicit guidance
                    first_row = prior_rows[0]
                    first_beast_uuid = first_row.get("beast_uuid", "")
                    if first_beast_uuid:
                        col_sample += f"\nKEY REFERENCE: The TOP RESULT has beast_uuid='{first_beast_uuid}'.\n"
                        col_sample += "When the user says 'first', 'top', or 'the one with most...', use this beast_uuid in a WHERE clause.\n"
                        col_sample += f"Example: WHERE beast_uuid = '{first_beast_uuid}' then GROUP BY platform to show across platforms."

                prior_context_block = (
                    f"[PRIOR QUERY CONTEXT]\n"
                    f"The user's last analytics query used this SQL:\n{prior_sql}\n"
                    f"Metric analysed: {prior_metric}{col_sample}\n"
                    f"Use this as the basis for the follow-up question below. "
                    f"Modify or extend the SQL to answer the follow-up — do NOT start from scratch."
                )
                break  # only need the most recent analytics turn

    # Include recent plain conversation messages for textual continuity
    if conversation_history:
        for h in conversation_history[-4:]:
            role = h.get("role", "user")
            content = str(h.get("content", ""))
            messages.append({"role": role, "content": content[:400]})

    # Inject error hint so the LLM can self-correct
    user_content = message
    if prior_context_block:
        user_content = f"{prior_context_block}\n\nUser follow-up: {message}"
    if error_hint:
        base = user_content  # may already include prior_context_block
        user_content = (
            f"{base}\n\n"
            f"[CORRECTION NEEDED] Your previous SQL failed with this error:\n"
            f"{error_hint}\n"
            "Please fix the SQL and return corrected JSON."
        )

    messages.append({"role": "user", "content": user_content})

    try:
        result = await generate_json_object(
            messages=messages,
            model=sql_model,
            timeout_seconds=float(settings.agent_analytics_timeout_seconds),
            purpose="analytics_sql_generation",
        )
    except Exception as exc:
        raise UnsupportedQueryError(str(exc)) from exc

    raw_sql = result.get("sql") or ""
    if isinstance(raw_sql, dict):
        # Model nested the SQL — try common sub-keys before giving up
        raw_sql = (
            raw_sql.get("query")
            or raw_sql.get("sql")
            or raw_sql.get("statement")
            or ""
        )
    sql = str(raw_sql).strip()
    if not sql:
        raise UnsupportedQueryError("SQL generation returned empty sql field")

    # The model sometimes returns params as a JSON-encoded string rather than an
    # object — coerce it to a plain dict in either case.
    raw_params = result.get("params")
    if isinstance(raw_params, str):
        try:
            raw_params = json.loads(raw_params)
        except (json.JSONDecodeError, ValueError):
            raw_params = {}
    params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}

    _logger.info(
        "generate_analytics_sql: SQL generated",
        extra={
            "model": sql_model,
            "metric": result.get("metric"),
            "operation": result.get("operation"),
            "query_category": result.get("query_category"),
            "sql_preview": sql[:200],
        },
    )

    return {
        "sql": sql,
        "params": params,
        "metric": result.get("metric"),
        "operation": result.get("operation", "sum"),
        "query_category": result.get("query_category", "metrics"),
    }


# ---------------------------------------------------------------------------
# Primary pipeline: SQL-gen → safe execute → response_agent (with retry)
# ---------------------------------------------------------------------------

async def run_sql_analytics_pipeline(
    message: str,
    conversation_history: list[dict] | None = None,
) -> dict[str, Any]:
    """Primary analytics pipeline: LLM SQL generation + safe execution + response shaping.

    Flow:
        1. generate_analytics_sql → {sql, params, metric, operation, query_category}
        2. execute_safe_sql       → {rows, row_count}         (raises on failure)
        3. build_analytics_response → client AnalyticsResponseContent dict

    On SQL validation or DB execution failure the LLM is asked to self-correct;
    up to MAX_SQL_RETRIES re-attempts are made.  On exhaustion, returns error dict.
    """
    from app.agents.response_agent import build_analytics_response, build_error_response  # noqa: PLC0415
    from app.nlp.intent_parser import UnsupportedQueryError  # noqa: PLC0415
    from app.tools.dbquery_tool import SQLValidationError, execute_safe_sql  # noqa: PLC0415
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

    attempted_sqls: list[str] = []
    error_hint: str | None = None
    last_error: str = "Unknown error"

    for attempt in range(MAX_SQL_RETRIES + 1):
        try:
            sql_obj = await generate_analytics_sql(
                message,
                conversation_history=conversation_history,
                error_hint=error_hint,
            )
            sql = sql_obj["sql"]
            params = sql_obj.get("params") or {}
            attempted_sqls.append(sql)

            db_result = await execute_safe_sql(sql, params=params)
            rows = db_result["rows"]

            _logger.info(
                "run_sql_analytics_pipeline: success",
                extra={
                    "attempt": attempt + 1,
                    "row_count": len(rows),
                    "metric": sql_obj.get("metric"),
                },
            )

            # Build the normal analytics response and attach the generated SQL
            resp = build_analytics_response(
                rows=rows,
                original_message=message,
                metric=sql_obj.get("metric"),
                operation=sql_obj.get("operation", "sum"),
                query_category=sql_obj.get("query_category", "metrics"),
                attempted_sqls=attempted_sqls,
            )
            # Include the final generated SQL (for debugging/visibility)
            resp["generated_sql"] = sql
            # Preserve raw rows so follow-up prompts can reference stable IDs
            # (e.g. beast_uuid from the "first" top-N result).
            resp["raw_rows"] = rows[:100]
            if sql_obj.get("metric"):
                resp["metric"] = sql_obj.get("metric")
            _logger.info("run_sql_analytics_pipeline: generated_sql", extra={"sql_preview": sql[:400]})
            return resp

        except UnsupportedQueryError as exc:
            last_error = f"SQL generation error: {exc}"
            _logger.warning(
                f"run_sql_analytics_pipeline: SQL gen failed (attempt {attempt + 1})",
                extra={"error": str(exc)},
            )
            error_hint = last_error

        except SQLValidationError as exc:
            last_error = f"SQL validation: {exc.reason}"
            _logger.warning(
                f"run_sql_analytics_pipeline: validation failed (attempt {attempt + 1})",
                extra={"error": exc.reason, "sql": attempted_sqls[-1] if attempted_sqls else ""},
            )
            error_hint = last_error

        except SQLAlchemyError as exc:
            # Sanitize — do not expose full DB error to the client
            safe_msg = str(exc)[:300]
            last_error = f"DB execution error: {safe_msg}"
            _logger.warning(
                f"run_sql_analytics_pipeline: DB error (attempt {attempt + 1})",
                extra={"error": safe_msg},
            )
            error_hint = last_error

    _logger.error(
        "run_sql_analytics_pipeline: all retries exhausted",
        extra={"attempts": len(attempted_sqls), "last_error": last_error},
    )
    err = build_error_response(last_error, attempted_sqls=attempted_sqls)
    # Surface any attempted SQLs for debugging
    err["generated_sqls"] = attempted_sqls
    return err

