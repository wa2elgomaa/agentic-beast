import json
import asyncio
from pathlib import Path

import sys

# Ensure backend src is importable when run from repo root with PYTHONPATH

from app.agents.v1.orchestrator_agent import OrchestratorAgent


QUERIES = [
    "What is the top 5 viewed videos on instagram",
    "Which day of the week has the highest total video views for TikTok? Group TikTok videos by day of week (Monday-Sunday) using the published_date column, sum the video_views for each day, and show a bar chart.",
    "What are the top video featuring \"Donald Trump\"",
    "Compare the total video_views for videos featuring 'Donald Trump' on TikTok vs Facebook. Sum video_views grouped by platform and show a bar chart comparing the two platforms.",
    "Which hour of the day has the highest total video views for TikTok? Group TikTok videos by hour extracted from published_time, sum the video_views per hour, and show a bar chart. Also identify any patterns in the data.",
]

# A follow-up sequence to verify is_followup wiring:
# The second message intentionally uses a pronoun reference so the classifier
# should return followup=True and seed the analytics agent with prior history.
FOLLOWUP_SEQUENCE = [
    {
        "message": "What is the top 5 viewed videos on instagram",
        "conversation_history": [],
    },
    {
        "message": "What about the same for YouTube?",
        "conversation_history": [
            {"role": "user", "content": "What is the top 5 viewed videos on instagram"},
            {"role": "assistant", "content": "The top 5 viewed videos on Instagram are..."},
        ],
    },
]


async def run_queries():
    orchestrator = OrchestratorAgent()
    results = []

    print("\n" + "="*60)
    print("STANDARD QUERIES (via OrchestratorAgent)")
    print("="*60)

    for q in QUERIES:
        ctx = {"message": q, "conversation_history": []}
        print(f"\n--- Query: {q}\n")
        try:
            resp = await orchestrator.execute(ctx)
        except Exception as e:
            print(f"Execution error: {e}")
            results.append({"query": q, "error": str(e)})
            continue

        try:
            resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
        except Exception:
            resp_dict = {"response_text": str(resp)}

        print(json.dumps(resp_dict, indent=2))
        results.append({"query": q, "result": resp_dict})

    print("\n" + "="*60)
    print("FOLLOW-UP SEQUENCE TEST (verifying is_followup wiring)")
    print("="*60)

    followup_results = []
    for turn in FOLLOWUP_SEQUENCE:
        print(f"\n--- Message: {turn['message']}")
        print(f"    history turns: {len(turn['conversation_history'])}\n")
        try:
            resp = await orchestrator.execute(turn)
        except Exception as e:
            print(f"Execution error: {e}")
            followup_results.append({"message": turn["message"], "error": str(e)})
            continue

        try:
            resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
        except Exception:
            resp_dict = {"response_text": str(resp)}

        print(json.dumps(resp_dict, indent=2))
        followup_results.append({"message": turn["message"], "result": resp_dict})

    out_dir = Path("tests/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "analytics_queries.json"
    out_path.write_text(json.dumps({"standard": results, "followup": followup_results}, indent=2))
    print(f"\nSaved results to {out_path}\n")


def main():
    asyncio.run(run_queries())


if __name__ == "__main__":
    main()
