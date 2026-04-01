"""Inspect and fix the platform column in the documents table.

Run with:
    python scripts/fix_platform_column.py [--dry-run]
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://beast:beast@localhost:5432/beast"
)

# ---------------------------------------------------------------------------
# URL → canonical platform name mapping (order matters — more specific first)
# ---------------------------------------------------------------------------
URL_TO_PLATFORM = [
    ("twitter.com",   "X"),
    ("x.com",         "X"),
    ("facebook.com",  "Facebook"),
    ("instagram.com", "Instagram"),
    ("linkedin.com",  "LinkedIn"),
    ("youtube.com",   "YouTube"),
    ("tiktok.com",    "TikTok"),
    ("snapchat.com",  "Snapchat"),
    ("pinterest.com", "Pinterest"),
    ("threads.net",   "Threads"),
]


async def inspect(conn):
    """Print a summary of what values are in the platform column."""
    cases = "\n".join(
        f"WHEN platform ILIKE '%{host}%' THEN '{name}'"
        for host, name in URL_TO_PLATFORM
    )
    sql = f"""
        SELECT
            CASE
                {cases}
                WHEN platform NOT ILIKE 'http%%' THEN platform
                ELSE 'UNMATCHED: ' || LEFT(platform, 60)
            END AS mapped_name,
            COUNT(*) AS cnt
        FROM documents
        WHERE platform IS NOT NULL
        GROUP BY mapped_name
        ORDER BY cnt DESC
    """
    result = await conn.execute(text(sql))
    rows = result.fetchall()

    total = sum(r[1] for r in rows)
    print(f"\nDistinct mapped platform values ({total} total rows with platform):\n")
    for name, cnt in rows:
        bar = "█" * min(40, int(40 * cnt / max(total, 1)))
        print(f"  {cnt:>7}  {bar:<40}  {name}")
    print()
    return rows


async def fix(conn, dry_run: bool):
    """Update platform column: replace URLs with canonical platform names."""
    cases = "\n            ".join(
        f"WHEN platform ILIKE '%{host}%' THEN '{name}'"
        for host, name in URL_TO_PLATFORM
    )
    sql = f"""
        UPDATE documents
        SET platform = CASE
            {cases}
            ELSE platform
        END
        WHERE platform ILIKE 'http%%'
    """

    if dry_run:
        # Count how many rows would be updated
        count_sql = "SELECT COUNT(*) FROM documents WHERE platform ILIKE 'http%%'"
        result = await conn.execute(text(count_sql))
        count = result.scalar()
        print(f"[DRY RUN] Would update {count} rows.")
    else:
        result = await conn.execute(text(sql))
        print(f"Updated {result.rowcount} rows.")
        await conn.commit()


async def main():
    dry_run = "--dry-run" in sys.argv

    engine = create_async_engine(DB_URL, echo=False)
    async with engine.connect() as conn:
        print("=== BEFORE ===")
        await inspect(conn)

        await fix(conn, dry_run=dry_run)

        if not dry_run:
            print("\n=== AFTER ===")
            await inspect(conn)

    await engine.dispose()
    if dry_run:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    asyncio.run(main())
