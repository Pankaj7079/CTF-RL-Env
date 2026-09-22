# CLI: reset the challenge to a clean attempt.
#   uv run python scripts/reset.py                 # in-process DB
#   AR_BASE_URL=http://localhost:8000 ... reset.py # a running server

from __future__ import annotations

import asyncio
import os

import httpx
from app.database import reset_challenge


async def _main() -> None:
    base_url = os.environ.get("AR_BASE_URL")
    if base_url:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            resp = await client.post("/_internal/reset")
            print(resp.json())
    else:
        attempt_id = await reset_challenge()
        print({"attempt_id": attempt_id})


if __name__ == "__main__":
    asyncio.run(_main())
