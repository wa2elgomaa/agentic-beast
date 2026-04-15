"""Datetime helpers for consistent UTC handling."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime for DB TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)