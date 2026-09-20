"""CLI: quick end-to-end smoke test (build sanity, no pytest needed).

Runs the deterministic solver once against the in-process app and asserts the
challenge is solved with full score.
"""

from __future__ import annotations

import asyncio
import sys

from app.env import ArtifactRelayEnv
from solver.reference_solution import solve


async def _main() -> int:
    env = ArtifactRelayEnv(in_process=True)
    try:
        obs = await solve(env)
    finally:
        await env.close()
    grade = obs["grade"]
    ok = grade["solved"] and grade["score"] == grade["max_score"]
    print(f"smoke: solved={grade['solved']} score={grade['score']}/{grade['max_score']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
