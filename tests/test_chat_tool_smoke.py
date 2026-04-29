#!/usr/bin/env python3
"""Smoke test for ChatAgent.as_tool() and execute().
"""
import asyncio
import json
from app.agents.v1.chat_agent import get_agent

agent = get_agent()
tool = agent.as_tool()

cases = {
    "greeting": "Hi there! How are you?",
    "info": "Tell me about the project roadmap.",
}

print("Tool type:", type(tool))

for name, msg in cases.items():
    print('\n--- CASE:', name, '---')
    if callable(tool):
        try:
            out = tool({"input": {"message": msg}})
            print('tool raw output:', out)
            content = out.get('content', [])
            if content:
                text = content[0].get('text')
                try:
                    parsed = json.loads(text)
                    print('tool parsed JSON:', parsed)
                except Exception:
                    print('tool text:', text)
        except Exception as e:
            print('tool call error:', e)
    else:
        print('tool not callable; skipping tool invocation')

    try:
        try:
            resp = asyncio.run(agent.execute({"message": msg}))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            resp = loop.run_until_complete(agent.execute({"message": msg}))
        print('execute result:', getattr(resp, 'response_text', None) or (resp.json() if hasattr(resp, 'json') else resp))
    except Exception as e:
        print('execute error:', e)

print('\nDone')
