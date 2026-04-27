import asyncio
import json
from pathlib import Path

"""
Orchestrator E2E test runner.

Edit the `PROMPTS` list or toggle `DRY_RUN`/`USE_WORKFLOW` and run with:

    PYTHONPATH=backend/src python tests/test_orchestrator_e2e.py

The script prints each response and saves structured results to
`tests/output/orchestrator_e2e.json`.
"""
from app.agents.v1.orchestrator_agent import get_agent


PROMPTS = [
    "What is the top 5 viewed videos on instagram",
    "Which day is the best to publish on tiktok",
    "What are the top video featuring \"Donald Trump\"",
    "Which videos got the most engagement last month?",
    "Can you analyze the sentiment of this text: I love sunny days but I hate the rain.",
    "Can you tell me a joke and also analyze the sentiment of this joke? The joke is: Why don't scientists trust atoms? Because they make up everything!"
]

# Toggle these when running locally
DRY_RUN = False
USE_WORKFLOW = True


async def run_prompts():
    agent = get_agent()
    results = []

    for prompt in PROMPTS:
        ctx = {"message": prompt, "dry_run": DRY_RUN, "use_workflow": USE_WORKFLOW}
        print(f"\n--- Prompt: {prompt}\n")
        try:
            # Prefer execute() if available on the agent
           resp = await agent.execute(ctx)

        except Exception as e:
            print("Execution error:", e)
            results.append({"prompt": prompt, "error": str(e)})
            continue

        try:
            resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else (resp.dict() if hasattr(resp, "dict") else resp)
        except Exception:
            resp_dict = {"response": str(resp)}

        print(json.dumps(resp_dict, indent=2, default=str))
        results.append({"prompt": prompt, "result": resp_dict})

    out_dir = Path("tests/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "orchestrator_e2e.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nSaved results to {out_path}\n")


def main():
    asyncio.run(run_prompts())


if __name__ == "__main__":
    main()
