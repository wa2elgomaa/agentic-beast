"""Debug script: check analytics_data schema and run a sample top-5 query."""
import asyncio
import os
import sys
import types
from pathlib import Path

# Stub spacy so app imports don't fail
spacy_stub = types.ModuleType("spacy")
spacy_stub.load = lambda *a, **k: None
sys.modules["spacy"] = spacy_stub

# Load .env
env_file = Path(__file__).parent.parent / ".env"
for line in env_file.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def main():
    db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://beast:beast@localhost:5432/beast")
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        # List all tables
        result0 = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        print("=== All tables ===")
        tables = [r[0] for r in result0.fetchall()]
        for t in tables:
            print(f"  {t}")

        # Find a table that likely holds analytics/document data
        for tbl in tables:
            if any(kw in tbl.lower() for kw in ['analytic', 'document', 'post', 'content', 'media']):
                r = await conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
                print(f"\n  {tbl}: {r.scalar()} rows")
                # Show columns
                cols = await conn.execute(text(f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = '{tbl}'
                    ORDER BY ordinal_position
                """))
                for c in cols.fetchall():
                    print(f"    {c[0]}: {c[1]}")

    print("\nNow testing parse_query...")
    from app.nlp.intent_parser import parse_query
    try:
        parsed = await parse_query("What are the top 5 viewed videos")
        print(f"Parsed: {parsed}")
    except Exception as e:
        print(f"parse_query failed: {e}")

    print("\nNow testing run_analytics_query...")
    from app.agents.analytics_agent import run_analytics_query
    try:
        result = await run_analytics_query("What are the top 5 viewed videos", None)
        print(f"Result: {result}")
    except Exception as e:
        print(f"run_analytics_query failed: {e}")


asyncio.run(main())
