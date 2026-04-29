#!/usr/bin/env python3
"""Smoke test for SQLAgent.as_tool() and execute().
"""
import asyncio
import json
from app.agents.v1.sql_agent import get_agent

agent = get_agent()
tool = agent.as_tool()

cases = {
    "count_signups": "Count signups in January 2024.",
    "list_emails": "Return emails of users who signed up in 2024.",
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
        # Print the generated SQL
        try:
            sql = getattr(resp, 'generate_sql', None) or (resp.json() if hasattr(resp, 'json') else None)
            print('execute result:', sql)
        except Exception as e:
            print('execute parse error:', e)
    except Exception as e:
        print('execute error:', e)

print('\nDone')
