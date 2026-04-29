import json
import asyncio
from pathlib import Path

import sys

# Ensure backend src is importable when run from repo root with PYTHONPATH

from app.agents.v1.analytics_agent import get_agent


QUERIES = [
    "What is the top 5 viewed videos on instagram",
    "Which day is the best to publish on tiktok",
    "What are the top video featuring \"Donald Trump\"",
]


async def run_queries():
    agent = get_agent()
    results = []
    for q in QUERIES:
        # Enable real DB execution (will attempt to run generated SQL)
        ctx = {"message": q, "dry_run": False, "use_workflow": True}
        print(f"\n--- Query: {q}\n")
        try:
            resp = await agent.execute(ctx)
        except Exception as e:
            print(f"Execution error: {e}")
            results.append({"query": q, "error": str(e)})
            continue

        # resp is a Pydantic model (AnalyticsAgentSchema)
        try:
            resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
        except Exception:
            resp_dict = {"response_text": str(resp)}

        print(json.dumps(resp_dict, indent=2))
        results.append({"query": q, "result": resp_dict})

    out_dir = Path("tests/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "analytics_queries.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved results to {out_path}\n")


def main():
    asyncio.run(run_queries())


if __name__ == "__main__":
    main()
