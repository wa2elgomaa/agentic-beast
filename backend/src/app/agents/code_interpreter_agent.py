"""Code Interpreter Agent — multi-step SQL + Python analytics pipeline.

Pipeline
--------
1. SQL generation  : ask LLM to produce a safe parameterized SELECT
2. SQL execution   : execute via ``execute_safe_sql`` (read-only, validated)
3. Code generation : ask LLM to write pandas/matplotlib code for the result data
4. Code execution  : run in ``code_interpreter_tool.execute_code`` (sandboxed)
5. Synthesis       : return rich response dict with output + optional chart

The agent is invoked when:
* The query involves complex analysis beyond a single aggregation (e.g. "break
  down by platform", "compare X with Y", "show a chart of …").
* The orchestrator detects a follow-up / chained question pattern.

All SQL is still routed through ``execute_safe_sql`` — only SELECT is allowed.
Charts are returned as base64 PNG strings (not stored in DB).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.analytics_agent import (
    enrich_rows_with_content_metadata,
    generate_analytics_sql,
    sanitize_rows_for_output,
)
from app.config import (
    get_agent_settings_registry,
    get_schema_registry,
    initialize_registries,
    settings,
)
from app.tools.code_interpreter_tool import execute_code
from app.tools.dbquery_tool import SQLValidationError, execute_safe_sql
from app.utilities.json_chat import generate_json_object

_logger = logging.getLogger(__name__)


def _ensure_registries_loaded() -> None:
    try:
        get_schema_registry()
    except RuntimeError:
        initialize_registries(config_dir=settings.config_dir)


def _build_code_gen_system_prompt() -> str:
    """Build code-generation prompt from live schema/settings registry."""
    _ensure_registries_loaded()
    schema_registry = get_schema_registry()
    settings_registry = get_agent_settings_registry()

    code_cfg = settings_registry.code_interpreter
    allowed_imports = ", ".join(code_cfg.get("allowed_imports", ["pandas", "matplotlib.pyplot", "json", "math"]))
    max_lines = int(code_cfg.get("max_code_lines", 30))

    metrics_preview = ", ".join(sorted(list(schema_registry.metrics.keys()))[:12])
    dims_preview = ", ".join(sorted(list(schema_registry.dimensions.keys()))[:10])

    return (
        "You are a Python data analyst working with a pandas DataFrame called df.\n"
        "The DataFrame contains rows returned from PostgreSQL analytics queries.\n"
        "Write concise Python code that answers the user question.\n\n"
        f"Known analytics metrics include: {metrics_preview}.\n"
        f"Known dimensions include: {dims_preview}.\n\n"
        "Rules:\n"
        f"1. Use only these libraries: {allowed_imports}.\n"
        "2. df is already defined. Do not redefine df or re-import pandas.\n"
        "3. Use print() for textual outputs.\n"
        "4. For charts, use plt and do not call plt.show() or plt.savefig().\n"
        f"5. Keep code short (< {max_lines} lines).\n"
        "6. Output ONLY raw Python code with no markdown fences."
    )


async def _generate_analysis_code(
    user_message: str,
    df_columns: list[str],
    sample_rows: list[dict],
    prior_question: str | None = None,
) -> str:
    """Ask the LLM to write pandas/matplotlib code for the given DataFrame."""
    if settings.ai_provider in ("openai", "strands"):
        model = (settings.openai_sql_model or "").strip() or settings.openai_model
    else:
        # Code generation requires strong instruction-following; fall back to best available
        model = (settings.ollama_sql_model or "").strip() or settings.ollama_model

    context = ""
    if prior_question:
        context = f"The user previously asked: '{prior_question}'\n"

    user_prompt = (
        f"{context}"
        f"User question: {user_message}\n\n"
        f"DataFrame columns: {', '.join(df_columns)}\n"
        f"Sample data (first 3 rows): {json.dumps(sample_rows[:3])}\n\n"
        "Write Python code to answer the question."
    )

    _ensure_registries_loaded()
    settings_registry = get_agent_settings_registry()
    code_cfg = settings_registry.code_interpreter

    messages = [
        {"role": "system", "content": _build_code_gen_system_prompt()},
        {"role": "user", "content": user_prompt},
    ]

    # Code generation returns raw Python, not JSON — use raw chat completion
    try:
        if settings.ai_provider in ("openai", "strands"):
            from openai import AsyncOpenAI  # noqa: PLC0415

            client = AsyncOpenAI(
                api_key=settings.effective_openai_api_key,
                base_url=settings.effective_openai_base_url,
            )
            response = await client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.1,
                max_tokens=600,
                timeout=float(code_cfg.get("timeout_seconds", 30.0)),
            )
            code = response.choices[0].message.content or ""
        else:
            import httpx  # noqa: PLC0415

            url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
            payload = {
                "model": model,
                "stream": False,
                "messages": messages,
            }
            async with httpx.AsyncClient(timeout=float(code_cfg.get("timeout_seconds", 30.0))) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
            code = data.get("message", {}).get("content", "") or ""
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Code generation failed", extra={"error": str(exc)})
        return ""

    # Strip markdown fences if the model wrapped the code
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        # Remove opening fence (```python or ```)
        lines = lines[1:] if lines[0].startswith("```") else lines
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()

    return code


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

async def run_code_interpreter(
    message: str,
    conversation_history: list[dict] | None = None,
) -> dict[str, Any]:
    """Run the full code interpreter pipeline for *message*.

    Returns a response dict compatible with the analytics response schema,
    extended with:
        code_output : str         — text printed by the generated code
        chart_b64   : str | None  — base64 PNG chart image (if produced)
        generated_code : str      — the Python code that was executed
        generated_sql  : str      — the SQL that was run
    """
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

    # ------------------------------------------------------------------
    # Step 1: Generate SQL (with prior context awareness)
    # ------------------------------------------------------------------
    try:
        sql_obj = await generate_analytics_sql(
            message,
            conversation_history=conversation_history,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Code interpreter: SQL gen failed", extra={"error": str(exc)})
        return {
            "query_type": "error",
            "resolved_subject": "sql_gen_error",
            "result_data": [],
            "insight_summary": "Could not generate a query for this request. Please rephrase.",
            "verification": str(exc),
            "generated_sql": None,
            "code_output": None,
            "chart_b64": None,
            "generated_code": None,
        }

    sql = sql_obj["sql"]
    params = sql_obj.get("params") or {}
    metric = sql_obj.get("metric")
    query_category = sql_obj.get("query_category", "metrics")

    # ------------------------------------------------------------------
    # Step 2: Execute SQL safely
    # ------------------------------------------------------------------
    try:
        db_result = await execute_safe_sql(sql, params=params)
        rows: list[dict] = db_result["rows"]

        # Preserve entity anchor for chained follow-ups.
        # If SQL filtered by top_beast_uuid but did not select beast_uuid,
        # add it to each row so next-turn context can still resolve "same video".
        top_beast_uuid = params.get("top_beast_uuid") if isinstance(params, dict) else None
        if top_beast_uuid and rows and "beast_uuid" not in rows[0]:
            rows = [{**row, "beast_uuid": str(top_beast_uuid)} for row in rows]
        rows = await enrich_rows_with_content_metadata(rows)
        rows = sanitize_rows_for_output(rows)
    except (SQLValidationError, SQLAlchemyError, Exception) as exc:  # noqa: BLE001
        _logger.warning("Code interpreter: SQL exec failed", extra={"error": str(exc)})
        return {
            "query_type": "error",
            "resolved_subject": "sql_exec_error",
            "result_data": [],
            "insight_summary": "The generated query could not be executed. Please try rephrasing.",
            "verification": str(exc)[:300],
            "generated_sql": sql,
            "code_output": None,
            "chart_b64": None,
            "generated_code": None,
        }

    if not rows:
        return {
            "query_type": query_category,
            "resolved_subject": metric or "unknown",
            "result_data": [],
            "insight_summary": "No data found for this query.",
            "verification": "Query executed successfully — zero rows returned.",
            "generated_sql": sql,
            "code_output": "",
            "chart_b64": None,
            "generated_code": None,
        }

    # ------------------------------------------------------------------
    # Step 3: Generate Python analysis code
    # ------------------------------------------------------------------
    df_columns = list(rows[0].keys()) if rows else []

    # Use the last user message as prior question context when available
    prior_question: str | None = None
    if conversation_history:
        for h in reversed(conversation_history[:-1]):  # exclude current message
            if h.get("role") == "user":
                prior_question = str(h.get("content", ""))[:200]
                break

    generated_code = await _generate_analysis_code(
        user_message=message,
        df_columns=df_columns,
        sample_rows=rows[:3],
        prior_question=prior_question,
    )

    # ------------------------------------------------------------------
    # Step 4: Execute code in sandbox
    # ------------------------------------------------------------------
    code_result: dict[str, Any] = {"output": "", "chart_b64": None, "error": None}
    if generated_code:
        code_result = execute_code(generated_code, data=rows)
        if code_result.get("error"):
            _logger.warning(
                "Code interpreter: sandbox error",
                extra={"error": code_result["error"][:300]},
            )

    # ------------------------------------------------------------------
    # Step 5: Build response with result_data from DB rows
    # ------------------------------------------------------------------
    from app.agents.analytics_agent import _rows_to_result_data  # noqa: PLC0415

    result_data = _rows_to_result_data(rows, query_category=query_category)

    # Build insight summary from code output or fall back to standard summary
    code_out = (code_result.get("output") or "").strip()
    if code_out:
        insight = code_out[:1000]
    else:
        from app.agents.analytics_agent import _build_insight_summary  # noqa: PLC0415
        insight = _build_insight_summary(
            metric, sql_obj.get("operation", "sum"), rows, query_category=query_category
        )

    _logger.info(
        "Code interpreter pipeline complete",
        extra={
            "rows": len(rows),
            "has_chart": bool(code_result.get("chart_b64")),
            "has_code_output": bool(code_out),
        },
    )

    return {
        "query_type": query_category,
        "resolved_subject": metric or "analysis",
        "result_data": result_data,
        "insight_summary": insight,
        "verification": (
            "Values sourced directly from PostgreSQL. "
            "Analysis performed by sandboxed Python code."
        ),
        "generated_sql": sql,
        "code_output": code_out or None,
        "chart_b64": code_result.get("chart_b64"),
        "generated_code": generated_code or None,
        # Store raw rows for next-turn context (same as analytics pipeline)
        "raw_rows": rows[:100],
        "metric": metric,
    }
