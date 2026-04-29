"""Lightweight workflow engine for analytics workflows.

This engine provides minimal workflow execution semantics suitable for
the `AnalyticsAgent` refactor: sequential tasks, simple dependency
ordering, context propagation, dry-run, and safety limits.
"""
from typing import Any, Dict, List, Optional
import time
import logging

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


class WorkflowEngine:
    def __init__(self, *, max_steps: Optional[int] = None, task_timeout: Optional[float] = None):
        self.max_steps = max_steps or getattr(settings, "WORKFLOW_MAX_STEPS", 20)
        self.task_timeout = task_timeout or getattr(settings, "WORKFLOW_TASK_TIMEOUT", 300.0)

    async def run_workflow(self, workflow: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a simple workflow description.

        Expected workflow format (minimal):
        {
            "tasks": [
                {"id": "discover_schema", "type": "discover_schema"},
                {"id": "generate_sql", "type": "generate_sql"},
                {"id": "execute_sql", "type": "execute_sql"},
                {"id": "postprocess", "type": "postprocess"}
            ]
        }

        The engine runs tasks in order and accumulates `results` in a dict.
        """
        start = time.time()
        results: Dict[str, Any] = {}
        execution_order: List[str] = []
        steps = 0

        tasks = workflow.get("tasks", [])
        dry_run = bool(context.get("dry_run", True))

        for task in tasks:
            if steps >= self.max_steps:
                logger.warning("workflow: reached max_steps=%s", self.max_steps)
                break
            steps += 1
            task_id = task.get("id") or f"task_{steps}"
            execution_order.append(task_id)
            task_type = task.get("type")
            task_ctx = {**context, "workflow_results": results}

            logger.debug("workflow: running task %s type=%s dry_run=%s", task_id, task_type, dry_run)

            try:
                if task_type == "discover_schema":
                    # Generic behavior: prefer `context['schema']` supplied by
                    # the caller (analytics_agent). If not present, fall back
                    # to DB describer. This keeps the engine generic and
                    # caller-driven.
                    schema = task_ctx.get("schema") or task_ctx.get("schema_registry") or {}

                    if not schema:
                        try:
                            from app.tools import StrandsSQL
                            db = StrandsSQL(settings.database_url)
                            schema = db.describe_table_structured(task_ctx.get("table")) if task_ctx.get("table") else {}
                        except Exception:
                            schema = {}

                    results[task_id] = {"schema": schema}

                elif task_type == "generate_sql":
                    # Invoke SQLAgent if available to get generated SQL. Use
                    # schema_context supplied in the caller-provided context
                    # (or discovered above) and forward conversation history.
                    try:
                        from app.agents.v1.sql_agent import get_agent as get_sql_agent
                        agent = get_sql_agent()

                        schema_context: Dict[str, Any] = task_ctx.get("schema_context") or task_ctx.get("schema") or results.get("discover_schema", {}).get("schema", {})

                        sql_ctx = {
                            "message": task.get("prompt") or context.get("message", ""),
                            "table": task_ctx.get("table"),
                            "schema": results.get("discover_schema", {}).get("schema"),
                            "schema_context": schema_context,
                            "conversation_history": task_ctx.get("conversation_history") or task_ctx.get("history") or task_ctx.get("messages"),
                            "user_id": task_ctx.get("user_id") or task_ctx.get("user"),
                            "raw_context": task_ctx,
                        }

                        sql_result = await agent.execute(sql_ctx)
                        # Normalize
                        if hasattr(sql_result, "model_dump"):
                            r = sql_result.model_dump()
                        elif hasattr(sql_result, "dict"):
                            r = sql_result.dict()
                        else:
                            r = {"response_text": str(sql_result)}
                    except Exception as e:
                        logger.exception("generate_sql failed: %s", e)
                        r = {"error": str(e)}

                    results[task_id] = r

                elif task_type == "execute_sql":
                    if dry_run:
                        results[task_id] = {"status": "skipped", "reason": "dry_run"}
                    else:
                        try:
                            from app.tools import StrandsSQL
                            db = StrandsSQL(settings.database_url)
                            # Use SQL text from previous task
                            prev = results.get("generate_sql") or {}
                            sql_text = prev.get("response_text") or prev.get("generate_sql") or prev.get("sql")
                            if not sql_text:
                                raise RuntimeError("No SQL text produced to execute")
                            # execute via StrandsSQL execute_query if available
                                try:
                                    # Preferred StrandsSQL direct API
                                    rows = db.execute_query(sql_text)
                                    results[task_id] = {"rows": rows}
                                except Exception:
                                    # Try SQLAlchemy direct execution as a robust fallback
                                    try:
                                        from sqlalchemy import create_engine, text
                                        engine = create_engine(settings.database_url)
                                        with engine.connect() as conn:
                                            res = conn.execute(text(sql_text))
                                            try:
                                                rows = [dict(r) for r in res.fetchall()]
                                            except Exception:
                                                # Some DB drivers return rowcount-only or no fetch
                                                rows = []
                                        results[task_id] = {"rows": rows}
                                    except Exception:
                                        # Last resort: try the StrandsSQL tool interface
                                        try:
                                            db_tool = db.as_tool()
                                            tool_use = {"toolUseId": "db_execute", "input": {"query": sql_text}}
                                            rows = db_tool(tool_use)
                                            results[task_id] = {"rows": rows}
                                        except Exception as e_tool:
                                            logger.exception("execute_sql failed fallback: %s", e_tool)
                                            results[task_id] = {"error": str(e_tool)}
                        except Exception as e:
                            logger.exception("execute_sql failed: %s", e)
                            results[task_id] = {"error": str(e)}

                elif task_type == "postprocess":
                    # Minimal postprocessing: aggregate previous results into a summary
                    gen = results.get("generate_sql") or {}
                    exec_res = results.get("execute_sql") or {}
                    # SQLAgent may return structured keys such as `generate_sql`,
                    # `response_text`, or `sql`. Prefer `generate_sql` when present.
                    generated_sql = (
                        gen.get("generate_sql")
                        or gen.get("response_text")
                        or gen.get("sql")
                        or ""
                    )
                    summary = {
                        "generated_sql": generated_sql,
                        "rows_preview": (exec_res.get("rows")[:5] if isinstance(exec_res.get("rows"), list) else exec_res.get("rows"))
                    }
                    results[task_id] = summary

                else:
                    # Unknown task type: record and continue
                    results[task_id] = {"status": "unknown_task", "type": task_type}

            except Exception as e:
                logger.exception("workflow task %s failed: %s", task_id, e)
                results[task_id] = {"error": str(e)}

        duration = time.time() - start
        final_payload = results.get(tasks[-1].get("id")) if tasks else {}

        return {
            "status": "completed",
            "execution_order": execution_order,
            "task_results": results,
            "final_payload": final_payload,
            "duration": duration,
        }


def get_engine() -> WorkflowEngine:
    return WorkflowEngine()
