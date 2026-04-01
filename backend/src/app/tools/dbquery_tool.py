"""Safe, read-only SQL execution tool with multi-layer security validation.

Security layers (defence-in-depth):
  1. Forbidden-keyword regex  — no DDL / DML tokens allowed
  2. sqlparse structural check — statement type must be SELECT
  3. Table whitelist           — only 'documents' table permitted
  4. Parameterized execution   — SQLAlchemy text() + bind-params (no interpolation)
  5. DB statement_timeout      — hard server-side query timeout
  6. Row cap                   — never returns more than MAX_ROWS rows

Retry contract:
  ``execute_safe_sql`` raises ``SQLValidationError`` (static) or
  ``sqlalchemy.exc.SQLAlchemyError`` (runtime) so callers can feed the
  sanitized error back to the LLM for SQL re-generation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import sqlparse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError  # noqa: F401 – re-exported for callers

from app.db.session import AsyncSessionLocal

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ROWS: int = 200
"""Hard upper bound on rows returned per query."""

STATEMENT_TIMEOUT_MS: int = 10_000
"""PostgreSQL statement_timeout in milliseconds (10 s)."""

_ALLOWED_TABLES: frozenset[str] = frozenset({"documents"})

_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|CREATE|EXEC(?:UTE)?|"
    r"GRANT|REVOKE|COPY|VACUUM|ANALYSE|ANALYZE|CALL|DO)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SQLValidationError(Exception):
    """Raised when a SQL statement fails static safety validation.

    Attributes:
        reason: Human-readable explanation of the failure.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_sql(sql: str) -> None:
    """Statically validate that *sql* is a safe, read-only SELECT.

    Checks (in order):
    1. Non-empty
    2. No forbidden DDL/DML keywords
    3. sqlparse type == SELECT
    4. Only references the ``documents`` table

    Args:
        sql: Raw SQL string to validate.

    Raises:
        SQLValidationError: If any check fails.
    """
    cleaned = sql.strip()
    if not cleaned:
        raise SQLValidationError("Empty SQL statement.")

    # --- 1. Forbidden keywords ---
    match = _FORBIDDEN_RE.search(cleaned)
    if match:
        raise SQLValidationError(f"Forbidden SQL keyword detected: '{match.group()}'.")

    # --- 2. Structural parse: must be SELECT ---
    parsed_stmts = sqlparse.parse(cleaned)
    if not parsed_stmts:
        raise SQLValidationError("sqlparse could not parse the SQL statement.")
    for stmt in parsed_stmts:
        stmt_type = stmt.get_type()
        if stmt_type != "SELECT":
            raise SQLValidationError(
                f"Only SELECT statements are allowed; detected type '{stmt_type}'."
            )

    # --- 3. Table whitelist ---
    sql_upper = cleaned.upper()
    from_tables = re.findall(r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql_upper)
    join_tables = re.findall(r"\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql_upper)
    referenced = {t.lower() for t in from_tables + join_tables}
    blocked = referenced - _ALLOWED_TABLES
    if blocked:
        raise SQLValidationError(
            f"Query references forbidden table(s): {', '.join(sorted(blocked))}. "
            "Only 'documents' is permitted."
        )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

async def execute_safe_sql(
    sql: str,
    params: dict[str, Any] | None = None,
    max_rows: int = 100,
) -> dict[str, Any]:
    """Execute a parameterized SELECT in a read-only, time-limited DB session.

    Args:
        sql: Parameterized SELECT statement with ``:param_name`` placeholders.
        params: Dict of bind-parameters matching ``:param_name`` occurrences.
        max_rows: Row cap; clamped to ``[1, MAX_ROWS]``.

    Returns:
        ``{"rows": [...], "row_count": int, "sql": <final sql>}``
        Each row is a plain ``dict[str, serializable_value]``.

    Raises:
        SQLValidationError: If static validation fails.
        SQLAlchemyError:    If the DB rejects the query (caller handles retry).
    """
    validate_sql(sql)  # raises SQLValidationError on failure

    capped = max(1, min(max_rows, MAX_ROWS))
    bound_params: dict[str, Any] = dict(params or {})

    # Inject or clamp LIMIT so the DB-level row cap is always enforced
    if re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql = re.sub(r"\bLIMIT\s+\d+", f"LIMIT {capped}", sql, flags=re.IGNORECASE)
    else:
        sql = sql.rstrip(";").rstrip() + f" LIMIT {capped}"

    _logger.info(
        "dbquery_tool: executing safe SQL",
        extra={"sql_preview": sql[:300], "params_keys": list(bound_params.keys())},
    )

    async with AsyncSessionLocal() as session:
        # DB-level timeout — any query exceeding this is cancelled by Postgres
        await session.execute(
            text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'")
        )
        result = await session.execute(text(sql), bound_params)
        keys = list(result.keys())
        raw_rows = result.fetchall()

    # Serialize to plain dicts (dates → ISO strings, etc.)
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        row: dict[str, Any] = {}
        for k, v in zip(keys, raw):
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
            elif isinstance(v, (int, float, str, bool, type(None))):
                row[k] = v
            else:
                row[k] = str(v)
        rows.append(row)

    _logger.info(
        "dbquery_tool: query complete",
        extra={"row_count": len(rows)},
    )
    return {"rows": rows, "row_count": len(rows), "sql": sql}
