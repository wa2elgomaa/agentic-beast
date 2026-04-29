#!/usr/bin/env python3
"""Smoke test for ClassifyAgent.as_tool() and execute().
"""
import asyncio
import json
from app.agents.v1.classify_agent import get_agent

agent = get_agent()
tool = agent.as_tool()

cases = {
    "analytics": "Write a SQL query to count signups in January 2024.",
    "general": "What's the weather like today in Paris?",
    "unknown": "asdjkl qwerty 12345",
}

print("Tool type:", type(tool))

for name, msg in cases.items():
    print('\n--- CASE:', name, '---')
    # Call via tool if it's callable
    if callable(tool):
        try:
            out = tool({"input": {"message": msg}})
            print('tool raw output:', out)
            # If content text present, try to parse
            try:
                content = out.get('content', [])
                if content:
                    text = content[0].get('text')
                    try:
                        parsed = json.loads(text)
                        print('tool parsed JSON:', parsed)
                    except Exception:
                        print('tool text:', text)
            except Exception:
                pass
        except Exception as e:
            print('tool call error:', e)
    else:
        print('tool not callable; skipping tool invocation')

    # Call execute() directly
    try:
        try:
            resp = asyncio.run(agent.execute({"message": msg}))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            resp = loop.run_until_complete(agent.execute({"message": msg}))
        print('execute result:', getattr(resp, 'intent', None) or (resp.json() if hasattr(resp, 'json') else resp))
    except Exception as e:
        print('execute error:', e)

print('\nDone')
