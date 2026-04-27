#!/usr/bin/env python3
"""Smoke runner that calls `execute()` on v1 agents.

Loads `backend/.env` (non-destructively) then instantiates and runs each
agent's `execute()` coroutine, printing the structured outputs.

This file is safe to remove after use.
"""
from pathlib import Path
import os
import sys
import asyncio


def load_env(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if " #" in v:
                v = v.split(" #", 1)[0].rstrip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            os.environ.setdefault(k, v)


def setup_path():
    repo_root = Path(__file__).resolve().parents[1]
    backend_src = repo_root / "backend" / "src"
    sys.path.insert(0, str(backend_src))


async def run_agents():
    # Import here after PYTHONPATH is configured
    from app.agents.v1.classify_agent import ClassifyAgent
    from app.agents.v1.chat_agent import ChatAgent
    from app.agents.v1.orchestrator_agent import OrchestratorAgent
    from app.agents.v1.analytics_agent import AnalyticsAgent

    agents = [
        ("classify", ClassifyAgent(), {"message": "What is the user's intent if they ask for sales data?"}),
        ("chat", ChatAgent(), {"message": "Say hello and introduce yourself."}),
        ("analytics", AnalyticsAgent(), {"message": "Generate SQL to count signups in January 2024"}),
        ("orchestrator", OrchestratorAgent(), {"message": "Route: Produce an analytics report for signups"}),
    ]

    for name, agent, ctx in agents:
        try:
            print(f"\n--- Running {name}.execute() ---")
            result = await agent.execute(ctx)
            print("Result:", result)
        except Exception as e:
            print(f"{name}.execute() raised:", type(e).__name__, e)


def main():
    load_env("backend/.env")
    setup_path()
    asyncio.run(run_agents())


if __name__ == "__main__":
    main()
