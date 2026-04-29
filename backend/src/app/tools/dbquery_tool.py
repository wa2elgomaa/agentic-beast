"""
strands-sql — General-purpose SQL tool for Strands agents.
Supports PostgreSQL, MySQL, and SQLite via SQLAlchemy.
"""

from __future__ import annotations

import os
import re
import textwrap
from typing import Any, Literal
from strands.tools import tool
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
import sqlglot
from sqlglot import exp
from pydantic import BaseModel, Field, model_validator


class SqlDatabaseInput(BaseModel):
    """Validated input for the sql_database tool."""

    action: Literal["list_tables", "describe_table", "schema_summary", "query", "execute"]

    sql: str | None = Field(None, description="SQL string for query/execute actions.")
    table: str | None = Field(None, description="Table name for describe_table action.")

    connection_string: str | None = Field(
        None, description="SQLAlchemy connection string. Falls back to DATABASE_URL env var."
    )

    read_only: bool = Field(True, description="Block write queries when True.")
    max_rows: int = Field(500, ge=1, le=10_000, description="Max rows returned by query.")
    timeout: int = Field(30, ge=1, le=300, description="Query timeout in seconds.")
    output_format: Literal["json", "markdown"] = Field(
        "markdown", description="Output format for query results."
    )

    allowed_tables: list[str] | None = Field(
        None, description="Allowlist — only these tables are accessible."
    )
    blocked_tables: list[str] | None = Field(
        None, description="Blocklist — these tables are never accessible."
    )
    params: dict | None = Field(
        None,
        description="Bound parameter values for :param_name placeholders in the SQL string.",
    )

    @model_validator(mode="after")
    def check_sql_provided(self) -> SqlDatabaseInput:
        if self.action in ("query", "execute") and not self.sql:
            raise ValueError(f"'sql' is required when action='{self.action}'.")
        if self.action == "describe_table" and not self.table:
            raise ValueError("'table' is required when action='describe_table'.")
        return self
    

# ---------------------------------------------------------------------------
# Engine cache — one engine per connection string, reused across tool calls
# ---------------------------------------------------------------------------
_ENGINE_CACHE: dict[str, Engine] = {}


def _normalize_sync_url(connection_string: str) -> str:
    """Replace async drivers (asyncpg, aiopg) with sync equivalents for use with sync create_engine."""
    return (
        connection_string
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgresql+aiopg://", "postgresql+psycopg2://")
        .replace("postgres+asyncpg://", "postgresql+psycopg2://")
    )


def _get_engine(connection_string: str, timeout: int) -> Engine:
    sync_url = _normalize_sync_url(connection_string)
    key = sync_url
    if key not in _ENGINE_CACHE:
        _ENGINE_CACHE[key] = create_engine(
            sync_url,
            poolclass=NullPool,
            pool_pre_ping=True,
            connect_args=_timeout_args(sync_url, timeout),
        )
    return _ENGINE_CACHE[key]


def _timeout_args(connection_string: str, timeout: int) -> dict:
    """Return driver-specific timeout connect_args."""
    cs = connection_string.lower()
    if cs.startswith("postgresql") or cs.startswith("postgres"):
        return {"connect_timeout": timeout, "options": f"-c statement_timeout={timeout * 1000}"}
    if cs.startswith("mysql"):
        return {"connect_timeout": timeout, "read_timeout": timeout, "write_timeout": timeout}
    return {}


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------
_WRITE_PATTERN = re.compile(
    r"^\s*(insert|update|delete|drop|create|alter|truncate|replace|merge|call|exec)\b",
    re.IGNORECASE,
)
_COMMENT_PATTERN = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)


def _is_write_query(sql: str) -> bool:
    # Strip line comments and block comments before checking
    cleaned = re.sub(r"--[^\n]*", "", sql)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()
    return bool(
        re.match(
            r"(insert|update|delete|drop|create|alter|truncate|replace|merge|call|exec)\b",
            cleaned,
            re.IGNORECASE,
        )
    )


def _sanitize_error(exc: Exception) -> str:
    """Return a safe error message that doesn't leak internal stack details."""
    msg = str(exc)
    msg = re.sub(r'File ".*?"', 'File "<hidden>"', msg)
    if len(msg) > 400:
        msg = msg[:400] + "... [truncated]"
    return msg

def _extract_tables(sql: str) -> set[str]:
    try:
        parsed = sqlglot.parse_one(sql)
        return {table.name for table in parsed.find_all(exp.Table)}
    except Exception:
        return set()


def _check_table_access(
    table: str,
    allowed_tables: list[str] | None,
    blocked_tables: list[str] | None,
) -> str | None:
    if allowed_tables is not None and table.lower() not in [t.lower() for t in allowed_tables]:
        return f"Access denied: table '{table}' is not in allowed_tables."
    if blocked_tables and table.lower() in [t.lower() for t in blocked_tables]:
        return f"Access denied: table '{table}' is blocked."
    return None


def _check_sql_table_access(
    sql: str,
    allowed_tables: list[str] | None,
    blocked_tables: list[str] | None,
) -> str | None:
    if not allowed_tables and not blocked_tables:
        return None

    tables = _extract_tables(sql)

    for tbl in tables:
        err = _check_table_access(tbl, allowed_tables, blocked_tables)
        if err:
            return err

    return None


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _rows_to_markdown(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    if not rows:
        return "*(no rows)*"
    col_widths = [
        max(len(c), max((len(str(r[i])) for r in rows), default=0)) for i, c in enumerate(columns)
    ]
    header = " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(columns))
    separator = "-+-".join("-" * w for w in col_widths)
    data_rows = [
        " | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(columns))) for row in rows
    ]
    return "\n".join([header, separator] + data_rows)


def _format_results(
    columns: list[str],
    rows: list[tuple[Any, ...]],
    output_format: str,
    max_rows: int,
    truncated: bool,
) -> str:
    note = f"\n\n⚠️  Results truncated to {max_rows} rows." if truncated else ""
    if output_format == "markdown":
        return _rows_to_markdown(columns, rows) + note
    import json
    result = [dict(zip(columns, row)) for row in rows]
    return json.dumps(result, default=str, indent=2) + note


# ---------------------------------------------------------------------------
# Action implementations (internal)
# ---------------------------------------------------------------------------

def _list_tables(
    engine: Engine,
    allowed_tables: list[str] | None,
    blocked_tables: list[str] | None,
) -> str:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    views = inspector.get_view_names()
    all_objects = [("table", t) for t in tables] + [("view", v) for v in views]

    filtered = []
    for kind, name in all_objects:
        if allowed_tables and name.lower() not in [t.lower() for t in allowed_tables]:
            continue
        if blocked_tables and name.lower() in [t.lower() for t in blocked_tables]:
            continue
        filtered.append((kind, name))

    if not filtered:
        return "No accessible tables or views found."
    return "\n".join(f"[{kind}] {name}" for kind, name in filtered)


def _describe_table(
    engine: Engine,
    table: str,
    allowed_tables: list[str] | None,
    blocked_tables: list[str] | None,
) -> str:
    err = _check_table_access(table, allowed_tables, blocked_tables)
    if err:
        return err

    inspector = inspect(engine)
    try:
        columns = inspector.get_columns(table)
        pk_info = inspector.get_pk_constraint(table)
        fk_info = inspector.get_foreign_keys(table)
    except Exception as exc:
        return f"Error describing table: {_sanitize_error(exc)}"

    pk_cols = set(pk_info.get("constrained_columns", []))
    lines = [f"Table: {table}", "", "Columns:"]
    for col in columns:
        flags = []
        if col["name"] in pk_cols:
            flags.append("PK")
        if not col.get("nullable", True):
            flags.append("NOT NULL")
        flag_str = "  [" + ", ".join(flags) + "]" if flags else ""
        default = f"  default={col['default']}" if col.get("default") is not None else ""
        lines.append(f"  {col['name']}  {col['type']}{flag_str}{default}")

    if fk_info:
        lines += ["", "Foreign Keys:"]
        for fk in fk_info:
            cols = ", ".join(fk["constrained_columns"])
            ref_table = fk["referred_table"]
            ref_cols = ", ".join(fk["referred_columns"])
            lines.append(f"  ({cols}) → {ref_table}({ref_cols})")

    return "\n".join(lines)


def _schema_summary(
    engine: Engine,
    allowed_tables: list[str] | None,
    blocked_tables: list[str] | None,
    max_tables: int = 30,
) -> str:
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()

    visible = []
    for t in all_tables:
        if allowed_tables and t.lower() not in [x.lower() for x in allowed_tables]:
            continue
        if blocked_tables and t.lower() in [x.lower() for x in blocked_tables]:
            continue
        visible.append(t)

    truncated_tables = len(visible) > max_tables
    visible = visible[:max_tables]

    lines = []
    for table in visible:
        try:
            columns = inspector.get_columns(table)
            pk_info = inspector.get_pk_constraint(table)
            pk_cols = set(pk_info.get("constrained_columns", []))
            col_parts = []
            for col in columns:
                marker = "*" if col["name"] in pk_cols else ""
                col_parts.append(f"{marker}{col['name']}:{col['type']}")
            lines.append(f"{table}({', '.join(col_parts)})")
        except Exception:
            lines.append(f"{table}(schema unavailable)")

    summary = "\n".join(lines)
    if truncated_tables:
        summary += f"\n\n... (showing {max_tables} of {len(all_tables)} tables)"
    return summary


def _run_query(
    engine: Engine,
    sql: str,
    allowed_tables: list[str] | None,
    blocked_tables: list[str] | None,
    max_rows: int,
    output_format: str,
    timeout: int,
    params: dict | None = None,
) -> str:
    err = _check_sql_table_access(sql, allowed_tables, blocked_tables)
    if err:
        return err

    try:
        sql = sql.strip()
        with engine.connect() as conn:
            result = conn.execute(text(sql).execution_options(timeout=timeout), params or {})
            columns = list(result.keys())
            rows: list[tuple[Any, ...]] = [tuple(row) for row in result.fetchmany(max_rows + 1)]
            truncated = len(rows) > max_rows
            rows = rows[:max_rows]
            return _format_results(columns, rows, output_format, max_rows, truncated)
    except Exception as exc:
        return f"Query error: {_sanitize_error(exc)}"


def _run_execute(
    engine: Engine,
    sql: str,
    allowed_tables: list[str] | None,
    blocked_tables: list[str] | None,
    timeout: int,
) -> str:
    err = _check_sql_table_access(sql, allowed_tables, blocked_tables)
    if err:
        return err

    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql).execution_options(timeout=timeout))
            rowcount = result.rowcount
            return f"OK. Rows affected: {rowcount if rowcount >= 0 else 'unknown'}"
    except Exception as exc:
        return f"Execute error: {_sanitize_error(exc)}"

# ---------------------------------------------------------------------------
# TOOL_SPEC + low-level tool handler (used by StrandsSQL.as_tool and get_tool)
# ---------------------------------------------------------------------------

TOOL_SPEC = {
    "name": "sql_database",
    "description": textwrap.dedent("""\
        General-purpose SQL tool. Supports list_tables, describe_table,
        schema_summary, query (SELECT), and execute (write, if enabled).
        Works with PostgreSQL, MySQL, and SQLite via SQLAlchemy.
    """),
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_tables", "describe_table", "schema_summary", "query", "execute"],
                    "description": "The action to perform.",
                },
                "sql": {
                    "type": "string",
                    "description": "SQL string for 'query' or 'execute' actions.",
                },
                "table": {
                    "type": "string",
                    "description": "Table name for 'describe_table' action.",
                },
                "connection_string": {
                    "type": "string",
                    "description": "SQLAlchemy connection string. Falls back to DATABASE_URL env var.",
                },
                "read_only": {
                    "type": "boolean",
                    "description": "Block write queries. Default true.",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Max rows returned by 'query'. Default 500.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Query timeout in seconds. Default 30.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "markdown"],
                    "description": "Output format for query results. Default 'markdown'.",
                },
                "allowed_tables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Allowlist of table names the agent may access.",
                },
                "blocked_tables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Blocklist of table names the agent may not access.",
                },
            },
            "required": ["action"],
        }
    },
}

@tool(name='sql_database', description=TOOL_SPEC["description"], inputSchema=TOOL_SPEC["inputSchema"]["json"])
def sql_database_tool(
    action: Literal["list_tables", "describe_table", "schema_summary", "query", "execute"],
    sql: str | None = None,
    table: str | None = None,
    connection_string: str | None = None,
    read_only: bool = True,
    max_rows: int = 500,
    timeout: int = 30,
    output_format: Literal["json", "markdown"] = "markdown",
    allowed_tables: list[str] | None = None,
    blocked_tables: list[str] | None = None,
    params: dict | None = None,
) -> dict:
    """Low-level Strands tool handler. Prefer StrandsSQL for direct usage."""
    try:
        validated = SqlDatabaseInput(
            action=action,
            sql=sql,
            table=table,
            connection_string=connection_string,
            read_only=read_only,
            max_rows=max_rows,
            timeout=timeout,
            output_format=output_format,
            allowed_tables=allowed_tables,
            blocked_tables=blocked_tables,
            params=params,
        )
    except Exception as exc:
        return {"status": "error", "content": [{"text": f"Invalid input: {exc}"}]}

    conn_str = validated.connection_string or os.environ.get("DATABASE_URL")
    if not conn_str:
        return {
            "status": "error",
            "content": [{"text": "No connection string provided. Set DATABASE_URL or pass connection_string."}],
        }

    if validated.read_only and validated.action == "execute":
        return {"status": "error", "content": [{"text": "Write queries are blocked. Set read_only=False to enable execute."}]}

    if validated.read_only and validated.action == "query" and validated.sql and _is_write_query(validated.sql):
        return {
            "status": "error",
            "content": [{"text": "Write statement detected in read_only mode. Use action='execute' with read_only=False."}],
        }

    try:
        engine = _get_engine(conn_str, validated.timeout)
    except Exception as exc:
        return {"status": "error", "content": [{"text": f"Connection failed: {_sanitize_error(exc)}"}]}

    try:
        if validated.action == "list_tables":
            result = _list_tables(engine, validated.allowed_tables, validated.blocked_tables)

        elif validated.action == "describe_table":
            if not validated.table:
                result = "Error: 'table' parameter is required for describe_table."
            else:
                result = _describe_table(engine, validated.table, validated.allowed_tables, validated.blocked_tables)

        elif validated.action == "schema_summary":
            result = _schema_summary(engine, validated.allowed_tables, validated.blocked_tables)

        elif validated.action == "query":
            if not validated.sql:
                result = "Error: 'sql' parameter is required for query."
            else:
                result = _run_query(
                    engine,
                    validated.sql,
                    validated.allowed_tables,
                    validated.blocked_tables,
                    validated.max_rows,
                    validated.output_format,
                    validated.timeout,
                    params=validated.params,
                )

        elif validated.action == "execute":
            if not validated.sql:
                result = "Error: 'sql' parameter is required for execute."
            else:
                result = _run_execute(engine, validated.sql, validated.allowed_tables, validated.blocked_tables, validated.timeout)
        else:
            result = f"Unknown action: {validated.action}"

    except Exception as exc:
        result = f"Unexpected error: {_sanitize_error(exc)}"

    return {"status": "success", "content": [{"text": result}]}
