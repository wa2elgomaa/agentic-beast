"""Database query tool (v1) — executes SQL against the app DB session.

This tool expects to be called with a SQL string and a DB session helper.
"""
from typing import Any, Dict, List

class DBQueryTool:
    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory

    async def execute_sql(self, sql: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        # Scaffold: return a placeholder dataset
        return [{"_row": 1}]


def get_dbquery_tool(db_session_factory=None) -> DBQueryTool:
    return DBQueryTool(db_session_factory=db_session_factory)
