#!/usr/bin/env python3
"""Run the v1 agents pipeline smoke test while safely loading backend/.env.

This script is safe to commit temporarily but should be removed after use
if you prefer not to keep a runner file in the repo.
"""
from pathlib import Path
import os
import sys


def load_env(path: str) -> None:
    p = Path(path)
    if not p.exists():
        print(f"No env file at {path}, skipping env load")
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
            # Strip inline comments
            if " #" in v:
                v = v.split(" #", 1)[0].rstrip()
            # Remove surrounding quotes
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            os.environ.setdefault(k, v)


def main():
    # Load backend/.env into the environment (without overriding already set vars)
    load_env("backend/.env")

    # Ensure backend/src is on PYTHONPATH
    repo_root = Path(__file__).resolve().parents[2]
    backend_src = repo_root / "backend" / "src"
    sys.path.insert(0, str(backend_src))

    # Run the v1 agents pipeline test file
    try:
        import pytest
    except Exception as e:
        print("pytest is not installed in the current environment:", e)
        sys.exit(2)

    rc = pytest.main(["-q", "tests/test_v1_agents_pipeline.py"])
    sys.exit(rc)


if __name__ == "__main__":
    main()
