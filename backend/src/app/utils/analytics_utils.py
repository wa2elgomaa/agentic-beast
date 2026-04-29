import json
from jinja2 import Template


def build_schema_context() -> str:
    """Build schema context dynamically from SchemaRegistry."""
    from app.config import get_schema_registry , initialize_registries # noqa: PLC0415
    initialize_registries()
    schema = get_schema_registry()

    required_fields = []
    required_fields.extend(
        f"- {field}" for field in sorted(schema.required_fields)
    )

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
    required_fields_text = "\n".join(required_fields)

    return (
        f"Table: {table_name} (PostgreSQL)\n\n"
        "Allowed metric columns (numeric, use for aggregation/ordering):\n"
        f"{metrics_text}\n\n"
        "Allowed dimension columns (use for GROUP BY / WHERE / ORDER BY):\n"
        f"{dimensions_text}\n\n"
        "REQUIRED FIELDS — MANDATORY in every SELECT that returns content/video rows:\n"
        f"{required_fields_text}\n"
        "When GROUP BY beast_uuid, include them as: beast_uuid (group key), "
        "MAX(content) AS content, MAX(title) AS title, MAX(view_on_platform) AS view_on_platform, "
        "MAX(platform) AS platform, MAX(published_date::text) AS published_date.\n\n"
        "Other useful columns: content_id (text), link_url (text url)\n"
        "CRITICAL: When grouping (GROUP BY), EVERY non-aggregated column in SELECT must be in GROUP BY.\n"
        "Example correct query: SELECT beast_uuid, MAX(content), SUM(metric) FROM documents "
        "GROUP BY beast_uuid  (content will be aggregated automatically).\n"
        "Example INCORRECT: SELECT platform, published_date, SUM(metric) FROM documents GROUP BY platform "
        "(missing published_date in GROUP BY).\n"
        f"Default limit: {default_limit}; absolute max limit: {max_limit}."
    )


def build_sql_gen_system_prompt() -> str:
    schema_context = build_schema_context()
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
        "4. REQUIRED FIELDS: For any query returning individual content/video rows (top-N, listings, record-level), "
        "ALWAYS SELECT: beast_uuid, MAX(content) AS content, MAX(title) AS title, "
        "MAX(view_on_platform) AS view_on_platform, MAX(platform) AS platform, "
        "MAX(published_date::text) AS published_date. "
        "Always GROUP BY beast_uuid for content-level queries. "
        "For top-N: ORDER BY metric_value DESC LIMIT :max_rows.\n"
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

def build_sql_gen_few_shot() -> list[dict[str, str]]:
    """Build few-shot examples from intent registry examples + schema defaults."""
    from app.config import get_intent_registry, get_schema_registry  # noqa: PLC0415

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
                        "MAX(content) AS content, MAX(title) AS title, "
                        "MAX(view_on_platform) AS view_on_platform, "
                        "MAX(platform) AS platform, "
                        "MAX(published_date::text) AS published_date, "
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
                "SELECT beast_uuid, MAX(content) AS content, MAX(title) AS title, MAX(view_on_platform) AS view_on_platform, "
                "MAX(platform) AS platform, MAX(published_date::text) AS published_date, SUM(video_views) AS metric_value "
                "FROM documents GROUP BY beast_uuid ORDER BY metric_value DESC LIMIT :max_rows\n"
                "Metric analysed: video_views\n"
                "Columns returned: beast_uuid, content, title, view_on_platform, platform, published_date, metric_value\n"
                "RESULTS (ranked by display order):\n"
                "  [1st/TOP] {\"beast_uuid\": \"11111111-1111-1111-1111-111111111111\", \"content\": \"Viral Post\", \"view_on_platform\": \"https://example.com/video/1\", \"metric_value\": \"50000\"}\n"
                "  [2nd] {\"beast_uuid\": \"22222222-2222-2222-2222-222222222222\", \"content\": \"Trending Clip\", \"view_on_platform\": \"https://example.com/video/2\", \"metric_value\": \"35000\"}\n"
                "  [3rd] {\"beast_uuid\": \"33333333-3333-3333-3333-333333333333\", \"content\": \"Featured Video\", \"view_on_platform\": \"https://example.com/video/3\", \"metric_value\": \"28000\"}\n"
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
