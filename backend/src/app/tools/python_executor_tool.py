"""Python executor tool for Strands analytics agent.

Provides a sandboxed ``python_repl`` Strands tool that the LLM uses to:
- Run pandas/SQL queries and print actual results
- Generate matplotlib charts that are captured as base64 PNG

Adapted from polar/StrandsDataAnalyst/strands_data_analyst/python_environment.py.

Security note: exec() globals restrict filesystem, network, and subprocess
access.  Only analytics-safe stdlib modules are permitted.
"""

from __future__ import annotations

import contextvars
import io
import threading
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Optional

from strands.tools import tool

# ---------------------------------------------------------------------------
# Per-request conversation ID (ContextVar)
#
# Strands' run_async() uses ``contextvars.copy_context().run(...)`` when it
# spawns its internal thread pool, so a ContextVar set in the calling coroutine
# (or asyncio.to_thread worker) propagates all the way into python_repl's tool
# thread.  This lets us key Redis assets by conversation_id without passing it
# explicitly through every layer.
# ---------------------------------------------------------------------------
_CONVERSATION_ID_VAR: contextvars.ContextVar[str] = contextvars.ContextVar(
    "analytics_conversation_id", default=""
)


def set_conversation_id(conv_id: str) -> None:
    """Bind the current conversation ID for downstream Redis asset storage."""
    _CONVERSATION_ID_VAR.set(conv_id)


def get_conversation_id() -> str:
    """Return the conversation ID bound to this context (empty string if unset)."""
    return _CONVERSATION_ID_VAR.get()


# ---------------------------------------------------------------------------
# Thread-local storage — still used for SQL results capture
# ---------------------------------------------------------------------------
_thread_local = threading.local()

# ---------------------------------------------------------------------------
# Process-level chart store — in-memory fallback when Redis is unavailable
#
# When Redis is up, chart data is stored per-conversation in Redis (via
# ConversationAssetService) and this global is bypassed.  When Redis is down
# (or conv_id is absent, e.g. in unit tests), this locked global list is used
# instead.
# ---------------------------------------------------------------------------
_LATEST_CHART: list = ["", ""]  # [chart_b64, caption]
_LATEST_CHART_LOCK = threading.Lock()


def store_latest_chart(b64: str, caption: str) -> None:
    """Store chart data — uses Redis keyed by conversation_id when available.

    Called from python_repl (any thread).  Falls back to the process-level
    global when Redis is unreachable or no conversation_id is bound.
    """
    conv_id = _CONVERSATION_ID_VAR.get()
    if conv_id:
        try:
            from app.services.conversation_asset_service import ConversationAssetService
            if ConversationAssetService.store_chart(conv_id, b64, caption):
                return  # Redis write succeeded — skip global fallback
        except Exception:
            pass  # Import or other error — fall through to global store

    # Fallback: process-level global (safe for single-process, low concurrency)
    with _LATEST_CHART_LOCK:
        _LATEST_CHART[0] = b64
        _LATEST_CHART[1] = caption


def pop_latest_chart(conversation_id: str = "") -> tuple[str, str]:
    """Return and clear the stored chart.

    When *conversation_id* is provided, reads from Redis first.  Falls back to
    the in-memory global (used by unit tests or when Redis is unavailable).
    """
    if conversation_id:
        try:
            from app.services.conversation_asset_service import ConversationAssetService
            result = ConversationAssetService.pop_chart(conversation_id)
            if result[0]:  # non-empty b64 means Redis had the chart
                return result
        except Exception:
            pass  # Fall through to global store

    # Fallback: process-level global
    with _LATEST_CHART_LOCK:
        b64 = _LATEST_CHART[0]
        caption = _LATEST_CHART[1]
        _LATEST_CHART[0] = ""
        _LATEST_CHART[1] = ""
        return b64, caption


def get_chart_state() -> tuple[Optional[str], Optional[str]]:
    """Return (chart_b64, chart_caption) without consuming them — legacy helper."""
    with _LATEST_CHART_LOCK:
        return _LATEST_CHART[0] or None, _LATEST_CHART[1] or None


def clear_chart_state(conversation_id: str = "") -> None:
    """Clear chart state before a new agent invocation.

    Clears Redis when *conversation_id* is given; also resets the global fallback.
    """
    if conversation_id:
        try:
            from app.services.conversation_asset_service import ConversationAssetService
            ConversationAssetService.clear(conversation_id)
        except Exception:
            pass

    with _LATEST_CHART_LOCK:
        _LATEST_CHART[0] = ""
        _LATEST_CHART[1] = ""


# ---------------------------------------------------------------------------
# Thread-local SQL results capture (populated by the sql_database wrapper tool)
# ---------------------------------------------------------------------------

def get_sql_results_state() -> list:
    """Return the SQL rows captured from the last sql_database tool invocation."""
    return list(getattr(_thread_local, "sql_results", []))


def clear_sql_results_state() -> None:
    """Clear thread-local SQL results before a new agent invocation."""
    _thread_local.sql_results = []


def capture_sql_results(rows: list) -> None:
    """Append *rows* to the thread-local SQL results accumulator.

    Called by the capturing wrapper in analytics_agent; accumulates across
    multiple sql_database tool calls within one agent turn.
    """
    existing: list = getattr(_thread_local, "sql_results", [])
    existing.extend(rows)
    _thread_local.sql_results = existing


# ---------------------------------------------------------------------------
# Allowed built-ins for the exec sandbox
# ---------------------------------------------------------------------------
_SAFE_BUILTINS = {
    k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
    for k in (
        "abs", "all", "any", "bin", "bool", "bytes", "callable", "chr",
        "dict", "dir", "divmod", "enumerate", "filter", "float", "format",
        "frozenset", "getattr", "globals", "hasattr", "hash", "hex", "id",
        "int", "isinstance", "issubclass", "iter", "len", "list", "locals",
        "map", "max", "min", "next", "object", "oct", "ord", "pow", "print",
        "property", "range", "repr", "reversed", "round", "set", "setattr",
        "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple",
        "type", "vars", "zip", "__name__", "__build_class__", "__import__",
    )
    if (isinstance(__builtins__, dict) and k in __builtins__)
    or (not isinstance(__builtins__, dict) and hasattr(__builtins__, k))
}

# Pre-import analytics modules so they're available in the sandbox without
# allowing open-ended __import__ calls.
import matplotlib  # noqa: E402  (must come after stdlib imports)
matplotlib.use("Agg")  # headless — prevents plt.show() from crashing in server environments
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sqlalchemy  # noqa: E402

_SAFE_GLOBALS: dict[str, Any] = {
    "__builtins__": _SAFE_BUILTINS,
    # Analytics libraries
    "pd": pd,
    "np": np,
    "matplotlib": matplotlib,
    "plt": plt,
    "sqlalchemy": sqlalchemy,
}


# ---------------------------------------------------------------------------
# PythonExecutor
# ---------------------------------------------------------------------------

class PythonExecutor:
    """Manages a shared exec namespace and produces a Strands @tool.

    Usage inside build_analytics_agent():

        executor = PythonExecutor()
        python_repl_tool = executor.get_tool()
        # ... build Agent with tools=[sql_database_tool, python_repl_tool]
        executor.clear_state()          # before agent(message)
        result = agent(message)
        assets, caption = get_chart_state()  # on same thread
    """

    def __init__(self) -> None:
        # Shared execution namespace — persists across multiple python_repl
        # calls within one agent invocation (mirrors Polar's REPL semantics).
        self.state: dict[str, Any] = dict(_SAFE_GLOBALS)
        # Inject sync DATABASE_URL so python_repl code can use sqlalchemy without os.environ
        try:
            from app.config import settings as _settings  # local import to avoid circular deps
            self.state["DATABASE_URL"] = _settings.database_url.replace(
                "postgresql+asyncpg://", "postgresql+psycopg2://"
            )
        except Exception:
            pass

    def clear_state(self) -> None:
        """Reset the exec namespace and thread-local chart + SQL data."""
        self.state = dict(_SAFE_GLOBALS)
        clear_chart_state()
        clear_sql_results_state()

    def _capture_chart(self) -> None:
        """If the LLM left a matplotlib Figure in ``visualization``, save it to disk."""
        fig = self.state.get("visualization")
        if fig is None:
            return
        try:
            import os
            import uuid
            import matplotlib.figure
            if not isinstance(fig, matplotlib.figure.Figure):
                return
            chart_dir = os.environ.get("CHART_DIR", "data/charts")
            os.makedirs(chart_dir, exist_ok=True)
            filename = f"{uuid.uuid4()}.png"
            filepath = os.path.join(chart_dir, filename)
            fig.savefig(filepath, format="png", bbox_inches="tight", dpi=150)
            chart_caption = str(self.state.get("visualization_caption", "Analytics chart"))
            _thread_local.assets = f"/static/charts/{filename}"
            _thread_local.chart_caption = chart_caption
        except Exception as _exc:  # noqa: S110 — chart saving must never crash the agent
            import logging as _logging
            _logging.getLogger(__name__).warning("_capture_chart failed: %s", _exc)

    def get_tool(self):  # noqa: ANN201
        """Return the ``python_repl`` Strands @tool bound to this executor."""
        executor_self = self  # capture for closure

        @tool
        def python_repl(code: str) -> str:
            """Execute Python code in a shared analytics sandbox.

            Use this tool to:
            - Query the database with pandas: pd.read_sql_query(sql, connection)
            - Manipulate DataFrames
            - Generate matplotlib charts (store in ``visualization`` variable)

            Variables persist across multiple calls within one agent turn.
            Always print actual results — never guess or fabricate values.

            Args:
                code: Python code to execute.

            Returns:
                Captured stdout/stderr from the execution.
            """
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            try:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    exec(code, executor_self.state)  # noqa: S102
            except Exception as exc:
                stderr_buf.write(f"\n[ExecutionError] {type(exc).__name__}: {exc}")
            finally:
                executor_self._capture_chart()

            stdout_out = stdout_buf.getvalue()
            stderr_out = stderr_buf.getvalue()

            if stdout_out or stderr_out:
                parts = []
                if stdout_out:
                    parts.append(f"STDOUT:\n{stdout_out}")
                if stderr_out:
                    parts.append(f"STDERR:\n{stderr_out}")
                return "\n".join(parts)
            return "Code executed successfully."

        return python_repl

    def get_chart_tool(self):  # noqa: ANN201
        """Return the ``generate_chart`` Strands @tool bound to this executor."""
        executor_self = self

        @tool
        def generate_chart(
            labels: list,
            values: list,
            title: str = "",
            caption: str = "",
            chart_type: str = "bar",
            x_label: str = "",
            y_label: str = "",
            color: str = "steelblue",
        ) -> str:
            """Generate a chart from explicitly provided data lists.

            Use this tool AFTER calling sql_database to visualise query results.
            Pass the label and value columns you want to plot — do NOT use
            python_repl for charting. The chart is automatically captured and
            delivered to the user.

            Args:
                labels: List of category / x-axis label strings.
                values: List of numeric values corresponding to each label.
                title: Chart title shown at the top (use a descriptive sentence).
                caption: Short subtitle / description for the chart.
                chart_type: Chart style: 'bar' (default), 'line', or 'pie'.
                x_label: X-axis label text.
                y_label: Y-axis label text.
                color: Bar/line colour name or hex code. Default 'steelblue'.

            Returns:
                Confirmation message.
            """

            import matplotlib  # noqa: PLC0415
            matplotlib.use("Agg")
            import matplotlib.pyplot as _plt  # noqa: PLC0415

            fig, ax = _plt.subplots(figsize=(10, 5))

            ctype = (chart_type or "bar").lower()
            if ctype == "line":
                ax.plot(labels, values, color=color, marker="o")
            elif ctype == "pie":
                ax.pie(values, labels=labels, autopct="%1.1f%%")
            else:
                ax.bar(labels, values, color=color)

            chart_title = title or caption
            if chart_title:
                ax.set_title(chart_title)
            if x_label:
                ax.set_xlabel(x_label)
            if y_label:
                ax.set_ylabel(y_label)
            _plt.xticks(rotation=30, ha="right")
            _plt.tight_layout()

            import os as _os
            import uuid as _uuid
            chart_dir = _os.environ.get("CHART_DIR", "data/charts")
            _os.makedirs(chart_dir, exist_ok=True)
            _filename = f"{_uuid.uuid4()}.png"
            _filepath = _os.path.join(chart_dir, _filename)
            fig.savefig(_filepath, format="png", bbox_inches="tight", dpi=150)
            _plt.close(fig)

            executor_self.state["_assets"] = f"/static/charts/{_filename}"
            executor_self.state["visualization_caption"] = caption or title
            # Also write to thread-local so OrchestratorAgent.get_chart_state() works
            # regardless of whether AnalyticsAgent or OrchestratorAgent reads the result.
            _thread_local.assets = f"/static/charts/{_filename}"
            _thread_local.chart_caption = caption or title

            return (
                f"Chart '{chart_title}' generated: {len(labels)} data points. "
                f"Caption: {caption or title}"
            )

        return generate_chart
