#!/usr/bin/env python3
"""Utility: connect to Gmail using local credentials and print preview response.

Usage:
  python scripts/print_gmail_preview.py [--max N] [--debug]

It reads credentials from settings.gmail_credentials_path if set, or from
the environment variable GMAIL_CREDENTIALS_PATH.
"""
import asyncio
import json
import os
import argparse

from pathlib import Path

from app.adapters.gmail_adapter import GmailAdapter
from app.config import settings


def load_oauth_from_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")
    data = json.loads(p.read_text())
    return data.get("gmail_oauth") or data


async def run(max_results: int, debug: bool):
    cred_path = os.environ.get("GMAIL_CREDENTIALS_PATH") or getattr(settings, "gmail_credentials_path", None)
    if not cred_path:
        raise RuntimeError("No credentials path set. Export GMAIL_CREDENTIALS_PATH or set settings.gmail_credentials_path.")

    oauth = load_oauth_from_file(cred_path)

    adapter = GmailAdapter(oauth_config=oauth)
    try:
        await adapter.connect()
        meta = await adapter.fetch_data(page=1, limit=max_results, return_meta=debug)
        # If not debug, fetch_data will return emails list instead of meta dict
        if isinstance(meta, dict):
            print(json.dumps(meta, indent=2, default=str))
        else:
            print(json.dumps({"emails": meta}, indent=2, default=str))
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=10, help="Max messages to fetch")
    parser.add_argument("--debug", action="store_true", help="Include raw messages in output if supported")
    args = parser.parse_args()
    asyncio.run(run(args.max, args.debug))
